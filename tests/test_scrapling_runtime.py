"""Tests for optional Scrapling runtime workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from jobos.boss_parser import extract_boss_job_list
from jobos.scrapling_runtime import capabilities
from jobos.scrapling_runtime import ScraplingCapabilityError, fetch_page
from jobos.scrapling_workflows import fetch_to_workspace


def test_capabilities_reports_parser() -> None:
    detected = capabilities()

    assert isinstance(detected.parser, bool)
    assert isinstance(detected.fetchers, bool)
    assert isinstance(detected.spiders, bool)


def test_fetch_to_workspace_writes_replay_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    @dataclass
    class Response:
        url: str = "https://example.test/final"
        status: int = 200
        html_content: str = "<html><title>Example</title></html>"

    monkeypatch.setattr(
        "jobos.scrapling_workflows.fetch_page",
        lambda *_args, **_kwargs: Response(),
    )

    result = fetch_to_workspace(tmp_path, "https://example.test/start")

    assert Path(result.html_path).read_text(encoding="utf-8") == Response.html_content
    assert Path(result.metadata_path).exists()


def test_dynamic_fetch_reports_missing_browser(monkeypatch) -> None:
    class MissingBrowser:
        adaptive = False

        @staticmethod
        def fetch(*_args, **_kwargs):
            raise RuntimeError("Executable doesn't exist at /tmp/chromium")

    class HttpFetcher:
        adaptive = False

    monkeypatch.setattr(
        "jobos.scrapling_runtime._load_fetchers",
        lambda: (HttpFetcher, MissingBrowser),
    )
    monkeypatch.setattr(
        "jobos.scrapling_runtime._validate_browser_path",
        lambda: "/tmp/chromium",
    )

    with pytest.raises(ScraplingCapabilityError, match="scrapling install"):
        fetch_page("https://example.test", engine="dynamic")


def test_dynamic_fetch_reports_missing_chromium(tmp_path: Path, monkeypatch) -> None:
    class DynamicFetcher:
        adaptive = False

    class HttpFetcher:
        adaptive = False

    missing_chromium = tmp_path / "chromium"
    monkeypatch.setattr(
        "jobos.scrapling_runtime._load_fetchers",
        lambda: (HttpFetcher, DynamicFetcher),
    )
    monkeypatch.setattr("jobos.browser.CHROMIUM_PATH", str(missing_chromium))

    with pytest.raises(ScraplingCapabilityError, match="Chromium not found"):
        fetch_page("https://example.test", engine="dynamic")


def test_boss_parser_adaptively_recovers_changed_card(
    tmp_path: Path,
) -> None:
    if not capabilities().parser:
        pytest.skip("Scrapling parser is optional")
    store = tmp_path / "adaptive.db"
    original = """
    <html><body><ul class="search-job-result">
      <li class="job-card-box">
        <a class="job-name" href="/job_detail/a.html">Python Engineer</a>
        <span class="boss-name">Acme</span>
        <span class="job-salary">20-30K</span>
      </li>
    </ul></body></html>
    """
    changed = """
    <html><body><ul class="vacancy-results">
      <li class="vacancy-box">
        <a class="job-name" href="/job_detail/a.html">Python Engineer</a>
        <span class="boss-name">Acme</span>
        <span class="job-salary">20-30K</span>
      </li>
    </ul></body></html>
    """
    extract_boss_job_list(
        original,
        url="https://www.zhipin.com/jobs",
        use_scrapling=True,
        adaptive_store=str(store),
    )

    result = extract_boss_job_list(
        changed,
        url="https://www.zhipin.com/jobs",
        use_scrapling=True,
        adaptive_store=str(store),
    )

    assert result.jobs[0].title == "Python Engineer"
    assert result.diagnostics.adaptive_recovered
    assert any(attempt.adaptive for attempt in result.diagnostics.selector_attempts)
