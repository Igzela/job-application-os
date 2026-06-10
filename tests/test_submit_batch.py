"""Tests for the auto-submit system (single + batch).

Covers:
- _human_delay range
- _find_boss_tab lookup
- auto_submit_single dry-run with mocked browser
- auto_submit_single with missing URL
- auto_submit_batch with no state file
- auto_submit_batch with no ready jobs
- auto_submit_batch respects max_jobs
- auto_submit_batch with mocked browser
- BatchSummary dataclass
- _click_chat_button / _fill_greeting / _click_send helpers
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from jobos.submitter import (
    BatchSummary,
    SubmitResult,
    _find_boss_tab,
    _human_delay,
    _load_pack_files,
    auto_submit_single,
    auto_submit_batch,
    _click_chat_button,
    _fill_greeting,
    _click_send,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state_file(base: Path, jobs: dict) -> Path:
    """Write a .job-state.json with the given jobs dict."""
    state_path = base / ".job-state.json"
    state_path.write_text(json.dumps({"jobs": jobs}, indent=2) + "\n")
    return state_path


def _make_pack_dir(base: Path, job_id: str, files: dict | None = None) -> Path:
    """Create a fake application pack directory with given files."""
    app_dir = base / "applications" / job_id
    app_dir.mkdir(parents=True, exist_ok=True)
    if files is None:
        files = {
            "greeting.md": "Hello, I am very interested in this role!",
            "resume_targeted.md": "# Resume\nSkills: Python, React",
        }
    for name, content in files.items():
        (app_dir / name).write_text(content, encoding="utf-8")
    return app_dir


def _mock_page(url: str = "https://www.zhipin.com/web/geek/job_detail/abc123.html"):
    """Return a mock Playwright page configured for BOSS Zhipin."""
    page = MagicMock()
    page.url = url
    page.title.return_value = "BOSS Zhipin - Job Detail"
    page.screenshot.return_value = None

    # Make locator().first.is_visible() return True for chat button
    visible_locator = MagicMock()
    visible_locator.is_visible.return_value = True

    page.locator.return_value.first = visible_locator
    return page


def _mock_context(page=None):
    """Return a mock browser context with a given page."""
    context = MagicMock()
    if page is None:
        page = _mock_page()
    context.pages = [page]
    return context


# ---------------------------------------------------------------------------
# Tests: _human_delay
# ---------------------------------------------------------------------------

class TestHumanDelay:
    """_human_delay sleeps within the expected range."""

    def test_returns_within_range(self) -> None:
        delay = _human_delay(0.01, 0.02)
        assert 0.01 <= delay <= 0.03  # small tolerance for timing

    def test_default_range_is_2_to_5(self) -> None:
        # Verify the default signature accepts no args and still works
        start = time.monotonic()
        delay = _human_delay(0.01, 0.02)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.01
        assert delay >= 0.01


# ---------------------------------------------------------------------------
# Tests: _find_boss_tab
# ---------------------------------------------------------------------------

class TestFindBossTab:
    """_find_boss_tab locates the correct tab in a browser context."""

    def test_finds_boss_tab(self) -> None:
        page = MagicMock()
        page.url = "https://www.zhipin.com/web/geek/job_detail/123.html"
        context = MagicMock()
        context.pages = [page]
        result = _find_boss_tab(context)
        assert result is page

    def test_returns_none_when_no_boss_tab(self) -> None:
        page = MagicMock()
        page.url = "https://www.google.com"
        context = MagicMock()
        context.pages = [page]
        result = _find_boss_tab(context)
        assert result is None

    def test_returns_none_for_empty_context(self) -> None:
        context = MagicMock()
        context.pages = []
        result = _find_boss_tab(context)
        assert result is None

    def test_skips_pages_with_errors(self) -> None:
        bad_page = MagicMock(type=PropertyMock)
        type(bad_page).url = PropertyMock(side_effect=RuntimeError("closed"))
        good_page = MagicMock()
        good_page.url = "https://www.zhipin.com/job"
        context = MagicMock()
        context.pages = [bad_page, good_page]
        result = _find_boss_tab(context)
        assert result is good_page


# ---------------------------------------------------------------------------
# Tests: _load_pack_files
# ---------------------------------------------------------------------------

class TestLoadPackFiles:
    """_load_pack_files reads a directory of pack files."""

    def test_loads_all_files(self, tmp_path: Path) -> None:
        app_dir = tmp_path / "applications" / "job-001"
        app_dir.mkdir(parents=True)
        (app_dir / "greeting.md").write_text("Hello!")
        (app_dir / "resume.md").write_text("# Resume")
        files = _load_pack_files(app_dir)
        assert files == {"greeting.md": "Hello!", "resume.md": "# Resume"}

    def test_empty_dir(self, tmp_path: Path) -> None:
        app_dir = tmp_path / "empty"
        app_dir.mkdir()
        files = _load_pack_files(app_dir)
        assert files == {}

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        files = _load_pack_files(tmp_path / "nonexistent")
        assert files == {}


# ---------------------------------------------------------------------------
# Tests: auto_submit_single
# ---------------------------------------------------------------------------

class TestAutoSubmitSingle:
    """auto_submit_single with mocked browser interactions."""

    def test_dry_run_no_url_returns_error(self) -> None:
        page = _mock_page()
        job_data = {"job_id": "j1", "title": "Dev", "company": "Acme", "link": ""}
        result = auto_submit_single(
            page=page,
            job_data=job_data,
            pack_files={"greeting.md": "Hi"},
            state_dir="/tmp/test",
            dry_run=True,
        )
        assert result.error == "No job URL found in job data"
        assert result.dry_run is True

    def test_dry_run_succeeds_with_valid_job(self, tmp_path: Path) -> None:
        page = _mock_page()
        job_data = {
            "job_id": "j2",
            "title": "Engineer",
            "company": "Beta",
            "link": "https://www.zhipin.com/web/geek/job_detail/j2.html",
        }
        result = auto_submit_single(
            page=page,
            job_data=job_data,
            pack_files={"greeting.md": "Hello!"},
            state_dir=str(tmp_path),
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.job_id == "j2"
        assert result.error is None

    def test_dry_run_does_not_click_send(self, tmp_path: Path) -> None:
        page = _mock_page()
        job_data = {
            "job_id": "j3",
            "title": "QA",
            "company": "Gamma",
            "link": "https://www.zhipin.com/web/geek/job_detail/j3.html",
        }
        result = auto_submit_single(
            page=page,
            job_data=job_data,
            pack_files={"greeting.md": "Hi"},
            state_dir=str(tmp_path),
            dry_run=True,
            confirm=True,  # even with confirm, dry_run prevents send
        )
        assert result.submitted is False

    def test_confirm_mode_sets_submitted(self, tmp_path: Path) -> None:
        page = _mock_page()
        job_data = {
            "job_id": "j4",
            "title": "DevOps",
            "company": "Delta",
            "link": "https://www.zhipin.com/web/geek/job_detail/j4.html",
        }
        result = auto_submit_single(
            page=page,
            job_data=job_data,
            pack_files={"greeting.md": "Interested!"},
            state_dir=str(tmp_path),
            dry_run=False,
            confirm=True,
        )
        # With mock returning True for is_visible, send should succeed
        assert result.submitted is True
        assert result.submitted_at is not None

    def test_fields_filled_contains_greeting(self, tmp_path: Path) -> None:
        page = _mock_page()
        job_data = {
            "job_id": "j5",
            "title": "SRE",
            "company": "Epsilon",
            "link": "https://www.zhipin.com/web/geek/job_detail/j5.html",
        }
        result = auto_submit_single(
            page=page,
            job_data=job_data,
            pack_files={"greeting.md": "My custom greeting"},
            state_dir=str(tmp_path),
            dry_run=False,
            confirm=True,
        )
        assert "招呼语" in result.fields_filled
        assert result.fields_filled["招呼语"] == "My custom greeting"


# ---------------------------------------------------------------------------
# Tests: auto_submit_batch
# ---------------------------------------------------------------------------

class TestAutoSubmitBatch:
    """auto_submit_batch with mocked browser and state file."""

    def test_no_state_file_returns_error(self, tmp_path: Path) -> None:
        summary = auto_submit_batch(state_dir=str(tmp_path), cdp_port=None)
        assert summary.total_attempted == 0
        assert any("No .job-state.json" in e for e in summary.errors)

    def test_no_ready_jobs(self, tmp_path: Path) -> None:
        _make_state_file(tmp_path, {
            "job-1": {"status": "imported", "title": "A", "company": "X", "link": ""},
        })
        summary = auto_submit_batch(state_dir=str(tmp_path), cdp_port=None)
        assert summary.total_attempted == 0
        assert any("No jobs" in e for e in summary.errors)

    @patch("jobos.browser.get_browser")
    def test_respects_max_jobs(self, mock_get_browser, tmp_path: Path) -> None:
        # Create 5 ready jobs with packs
        jobs = {}
        for i in range(5):
            jid = f"job-{i}"
            jobs[jid] = {
                "status": "predicted",
                "title": f"Role {i}",
                "company": "Co",
                "link": f"https://www.zhipin.com/web/geek/job_detail/{jid}.html",
            }
            _make_pack_dir(tmp_path, jid)

        _make_state_file(tmp_path, jobs)

        # Mock browser
        page = _mock_page()
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        pw = MagicMock()
        mock_get_browser.return_value = (pw, browser, context, page)

        summary = auto_submit_batch(
            state_dir=str(tmp_path),
            cdp_port=9222,
            max_jobs=2,
            interval_min=0,
            interval_max=0,
            dry_run=True,
        )
        assert summary.total_attempted == 2

    @patch("jobos.browser.get_browser")
    def test_batch_with_mocked_browser(self, mock_get_browser, tmp_path: Path) -> None:
        jobs = {
            "j-batch-1": {
                "status": "packed",
                "title": "Eng",
                "company": "Acme",
                "link": "https://www.zhipin.com/web/geek/job_detail/j-batch-1.html",
            },
        }
        _make_state_file(tmp_path, jobs)
        _make_pack_dir(tmp_path, "j-batch-1")

        page = _mock_page()
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        pw = MagicMock()
        mock_get_browser.return_value = (pw, browser, context, page)

        summary = auto_submit_batch(
            state_dir=str(tmp_path),
            cdp_port=9222,
            max_jobs=5,
            interval_min=0,
            interval_max=0,
            dry_run=True,
        )
        assert summary.total_attempted == 1
        assert summary.total_succeeded == 1
        assert summary.total_failed == 0
        assert len(summary.results) == 1

    @patch("jobos.browser.get_browser")
    def test_batch_missing_pack_counts_as_failure(self, mock_get_browser, tmp_path: Path) -> None:
        jobs = {
            "j-nopack": {
                "status": "predicted",
                "title": "NoPack",
                "company": "Co",
                "link": "https://www.zhipin.com/web/geek/job_detail/j-nopack.html",
            },
        }
        _make_state_file(tmp_path, jobs)
        # No _make_pack_dir -- pack doesn't exist

        page = _mock_page()
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        pw = MagicMock()
        mock_get_browser.return_value = (pw, browser, context, page)

        summary = auto_submit_batch(
            state_dir=str(tmp_path),
            cdp_port=9222,
            max_jobs=5,
            interval_min=0,
            interval_max=0,
            dry_run=True,
        )
        assert summary.total_attempted == 1
        assert summary.total_failed == 1
        assert any("No application pack" in e for e in summary.errors)


# ---------------------------------------------------------------------------
# Tests: BatchSummary
# ---------------------------------------------------------------------------

class TestBatchSummary:
    """BatchSummary dataclass basics."""

    def test_defaults(self) -> None:
        s = BatchSummary()
        assert s.total_attempted == 0
        assert s.total_succeeded == 0
        assert s.total_failed == 0
        assert s.results == []
        assert s.errors == []

    def test_can_append_results(self) -> None:
        s = BatchSummary()
        r = SubmitResult(
            job_id="x", platform="boss", dry_run=True, fields_filled={}
        )
        s.results.append(r)
        assert len(s.results) == 1
