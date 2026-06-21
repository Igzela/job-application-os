"""Tests for Scrapling stealth integration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from jobos.scrapling_runtime import (
    ScraplingCapabilityError,
    fetch_page,
    stealth_session,
)


class _Items(list):
    def to_jsonl(self, path):
        Path(path).write_text("", encoding="utf-8")


def _crawl_result(*, proxies=None):
    return SimpleNamespace(
        completed=True,
        items=_Items(),
        stats=SimpleNamespace(
            requests_count=0,
            failed_requests_count=0,
            proxies=list(proxies or []),
        ),
    )


def test_stealth_fetch_passes_options(monkeypatch) -> None:
    captured = {}

    def fake_fetch(url, **kwargs):
        captured.update(url=url, **kwargs)
        return SimpleNamespace(status=200, html_content="<html></html>")

    monkeypatch.setattr("jobos.scrapling_runtime._fetch_stealth", fake_fetch)

    fetch_page("https://example.com", engine="stealth", headless=False, timeout=60)

    assert captured["url"] == "https://example.com"
    assert captured["headless"] is False


def test_stealth_session_enters_and_closes(monkeypatch) -> None:
    events = []

    class FakeStealthySession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *_args):
            events.append("exit")

    monkeypatch.setattr(
        "jobos.scrapling_runtime._load_stealth_session",
        lambda: FakeStealthySession,
    )
    monkeypatch.setattr(
        "jobos.scrapling_runtime._validate_browser_path",
        lambda: "/tmp/chromium",
    )

    with stealth_session(headless=False) as session:
        assert session.kwargs["headless"] is False
        assert session.kwargs["timeout"] == 60000

    assert events == ["enter", "exit"]


def test_stealth_requires_capability(monkeypatch) -> None:
    def failing_fetch(*_args, **_kwargs):
        raise ScraplingCapabilityError("StealthyFetcher is unavailable")

    monkeypatch.setattr("jobos.scrapling_runtime._fetch_stealth", failing_fetch)

    with pytest.raises(ScraplingCapabilityError, match="StealthyFetcher"):
        fetch_page("https://example.com", engine="stealth")


def test_boss_stealth_fetch_uses_explicit_timeout_once(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        "jobos.config.load_config",
        lambda: {
            "stealth": {"timeout": 60, "solve_cloudflare": False},
            "proxy": {"url_env": "JOBOS_PROXY_URL"},
        },
    )
    monkeypatch.setattr(
        "jobos.config.resolve_proxy_url",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "jobos.scrapling_runtime.fetch_page",
        lambda url, **kwargs: captured.update(url=url, **kwargs),
    )

    from jobos.stealth_browser import fetch_boss_page

    fetch_boss_page("https://example.test", timeout=30)

    assert captured["timeout"] == 30


def test_config_has_stealth_proxy_and_spider_defaults() -> None:
    from jobos.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["stealth"]["solve_cloudflare"] is False
    assert DEFAULT_CONFIG["stealth"]["block_webrtc"] is True
    assert DEFAULT_CONFIG["stealth"]["hide_canvas"] is True
    assert DEFAULT_CONFIG["proxy"]["url_env"] == "JOBOS_PROXY_URL"
    assert DEFAULT_CONFIG["spider"]["max_pages"] == 50


def test_stealth_crawl_registers_async_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registered = {}

    class FakeManager:
        def add(self, name, session, *, default=False, lazy=False):
            registered.update(
                name=name,
                session=session,
                default=default,
                lazy=lazy,
            )

    class FakeSpider:
        def __init__(self, crawldir=None, interval=300):
            self.configure_sessions(FakeManager())

        def configure_sessions(self, manager):
            raise AssertionError("subclass must configure session")

        def start(self):
            return _crawl_result()

    class FakeAsyncStealthySession:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(
        "jobos.scrapling_workflows._load_spider_runtime",
        lambda: (FakeSpider, object, FakeAsyncStealthySession, object),
    )
    monkeypatch.setattr(
        "jobos.scrapling_workflows._validate_browser_path",
        lambda: "/tmp/chromium",
    )

    from jobos.scrapling_workflows import crawl_to_workspace

    crawl_to_workspace(
        tmp_path,
        "https://example.test",
        stealth=True,
        stealth_options={"timeout": 60},
    )

    assert registered["name"] == "stealth"
    assert registered["default"] is True
    assert isinstance(registered["session"], FakeAsyncStealthySession)
    assert registered["session"].kwargs["timeout"] == 60000


def test_crawl_summary_redacts_proxy_credentials(
    tmp_path: Path,
    monkeypatch,
) -> None:
    secret = "http://alice:secret@example.test:8080"

    class FakeSpider:
        def __init__(self, crawldir=None, interval=300):
            pass

        def start(self):
            return _crawl_result(proxies=[secret])

    monkeypatch.setattr(
        "jobos.scrapling_workflows._load_spider_runtime",
        lambda: (FakeSpider, object, object, object),
    )

    from jobos.scrapling_workflows import crawl_to_workspace

    result = crawl_to_workspace(tmp_path, "https://example.test", proxy=secret)
    summary_text = (
        Path(result["items_path"]).parent / "summary.json"
    ).read_text(encoding="utf-8")

    assert secret not in summary_text
    assert '"proxy_enabled": true' in summary_text


def test_crawl_cli_uses_config_defaults(tmp_path: Path, monkeypatch) -> None:
    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "jobos.config.load_config",
        lambda: {
            "spider": {
                "max_pages": 7,
                "concurrency": 2,
                "download_delay": 0.5,
                "robots_txt_obey": False,
                "stealth": True,
            },
            "stealth": {"solve_cloudflare": False, "block_ads": False},
            "proxy": {"url_env": "JOBOS_PROXY_URL"},
        },
    )
    monkeypatch.setattr(
        "jobos.config.load_env_values",
        lambda: {"JOBOS_PROXY_URL": "http://alice:secret@proxy.test:8080"},
    )
    monkeypatch.setattr(
        "jobos.scrapling_workflows.crawl_to_workspace",
        lambda *_args, **kwargs: (
            captured.update(kwargs)
            or {"completed": True, "items": 0, "items_path": "items.jsonl"}
        ),
    )

    from jobos.cli import _cmd_scrapling_crawl

    _cmd_scrapling_crawl(
        SimpleNamespace(
            url="https://example.test",
            max_pages=None,
            concurrency=None,
            delay=None,
            stealth=None,
            proxy_env=None,
        )
    )

    assert captured["max_pages"] == 7
    assert captured["concurrency"] == 2
    assert captured["download_delay"] == 0.5
    assert captured["robots_txt_obey"] is False
    assert captured["stealth"] is True
    assert captured["proxy"].endswith("@proxy.test:8080")
    assert captured["stealth_options"]["block_ads"] is False
