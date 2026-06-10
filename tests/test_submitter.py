"""Tests for the semi-automatic submitter module.

Verifies prepare_submission, submit_application, platform field mapping,
dry-run mode with browser interaction, and error handling.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from jobos.submitter import (
    BOSS_FIELD_MAP,
    PLATFORM_MAPS,
    SubmitResult,
    get_platform_fields,
    prepare_submission,
    submit_application,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pack_dir(base: Path, job_id: str, files: dict[str, str] | None = None) -> Path:
    """Create a fake application pack directory with given files."""
    app_dir = base / "applications" / job_id
    app_dir.mkdir(parents=True, exist_ok=True)
    if files is None:
        files = {
            "greeting.md": "Hello, I am interested in this role.",
            "resume_targeted.md": "# Resume\n\nSkills: Python, React",
            "cover_letter.md": "Dear Hiring Team,\nI would like to apply.",
            "form_answers.md": "Q: Why us?\nA: Great company.",
        }
    for name, content in files.items():
        (app_dir / name).write_text(content, encoding="utf-8")
    return app_dir


def _mock_browser_env():
    """Return mocked (pw, browser, context, page) tuple."""
    pw = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()

    page.title.return_value = "BOSS Zhipin - Job Search"
    page.url = "https://www.zhipin.com/"
    page.screenshot.return_value = None

    context.pages = [page]
    pw.chromium.connect_over_cdp.return_value = browser
    browser.contexts = [context]

    return pw, browser, context, page


def _mock_standalone_env():
    """Return mocked standalone launch tuple."""
    pw = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()

    page.title.return_value = "BOSS Zhipin - Job Search"
    page.url = "https://www.zhipin.com/"
    page.screenshot.return_value = None

    pw.chromium.launch.return_value = browser
    browser.new_context.return_value = context
    context.new_page.return_value = page

    return pw, browser, context, page


# ---------------------------------------------------------------------------
# Tests: platform field mapping
# ---------------------------------------------------------------------------

class TestPlatformMapping:
    """Platform field maps are correct and complete."""

    def test_boss_map_keys(self) -> None:
        """Boss map covers the expected pack file names."""
        expected_files = {"greeting.md", "resume_targeted.md", "cover_letter.md", "form_answers.md"}
        assert set(BOSS_FIELD_MAP.keys()) == expected_files

    def test_boss_map_values(self) -> None:
        """Boss map values are the expected Chinese form field names."""
        assert BOSS_FIELD_MAP["greeting.md"] == "招呼语"
        assert BOSS_FIELD_MAP["resume_targeted.md"] == "简历"
        assert BOSS_FIELD_MAP["cover_letter.md"] == "求职信"
        assert BOSS_FIELD_MAP["form_answers.md"] == "附加信息"

    def test_get_platform_fields_boss(self) -> None:
        result = get_platform_fields("boss")
        assert result == BOSS_FIELD_MAP

    def test_get_platform_fields_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown platform"):
            get_platform_fields("nonexistent_platform")

    def test_platform_maps_registered(self) -> None:
        assert "boss" in PLATFORM_MAPS


# ---------------------------------------------------------------------------
# Tests: prepare_submission
# ---------------------------------------------------------------------------

class TestPrepareSubmission:
    """prepare_submission loads pack files and maps to platform fields."""

    def test_dry_run_returns_correct_fields(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-001")
        result = prepare_submission("job-001", "boss", str(tmp_path))

        assert result.dry_run is True
        assert result.job_id == "job-001"
        assert result.platform == "boss"
        assert result.submitted is False
        assert result.error is None

    def test_fields_filled_mapping(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-002")
        result = prepare_submission("job-002", "boss", str(tmp_path))

        assert "招呼语" in result.fields_filled
        assert "简历" in result.fields_filled
        assert "求职信" in result.fields_filled
        assert "附加信息" in result.fields_filled
        assert "interested" in result.fields_filled["招呼语"]

    def test_missing_pack_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No application pack found"):
            prepare_submission("nonexistent-job", "boss", str(tmp_path))

    def test_partial_pack_files(self, tmp_path: Path) -> None:
        """Only files that exist in the pack are mapped; missing ones are skipped."""
        _make_pack_dir(tmp_path, "job-003", files={
            "greeting.md": "Hi there!",
            # missing resume_targeted.md, cover_letter.md, form_answers.md
        })
        result = prepare_submission("job-003", "boss", str(tmp_path))

        assert len(result.fields_filled) == 1
        assert result.fields_filled["招呼语"] == "Hi there!"

    def test_unknown_platform_raises(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-004")
        with pytest.raises(ValueError, match="Unknown platform"):
            prepare_submission("job-004", "linkedin", str(tmp_path))

    def test_screenshot_path_none(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-005")
        result = prepare_submission("job-005", "boss", str(tmp_path))
        assert result.screenshot_path is None


# ---------------------------------------------------------------------------
# Tests: submit_application
# ---------------------------------------------------------------------------

class TestSubmitApplication:
    """submit_application dry-run and error paths."""

    @patch("jobos.browser.sync_playwright")
    def test_dry_run_default(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-010")
        result = submit_application("job-010", "boss", str(tmp_path), cdp_port=None)

        assert result.dry_run is True
        assert len(result.fields_filled) == 4

    @patch("jobos.browser.sync_playwright")
    def test_dry_run_explicit(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-011")
        result = submit_application("job-011", "boss", str(tmp_path), dry_run=True, cdp_port=None)
        assert result.dry_run is True

    def test_no_confirm_raises_value_error(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-012")
        with pytest.raises(ValueError, match="--confirm"):
            submit_application("job-012", "boss", str(tmp_path), dry_run=False, confirm=False)

    @patch("jobos.browser.sync_playwright")
    def test_confirm_fills_fields(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-013")
        result = submit_application(
            "job-013", "boss", str(tmp_path),
            dry_run=False, confirm=True, cdp_port=None,
        )
        assert result.dry_run is False
        assert result.submitted is False  # click not enabled yet
        assert result.page_title == "BOSS Zhipin - Job Search"
        assert result.page_url == "https://www.zhipin.com/"

    def test_missing_pack_in_submit(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            submit_application("missing", "boss", str(tmp_path))

    @patch("jobos.browser.sync_playwright")
    def test_dry_run_captures_screenshot(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-020")
        result = submit_application("job-020", "boss", str(tmp_path), cdp_port=None)

        assert result.screenshot_path is not None
        assert "dry_run_screenshot.png" in result.screenshot_path
        page.screenshot.assert_called_once()

    @patch("jobos.browser.sync_playwright")
    def test_dry_run_captures_page_title(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        page.title.return_value = "BOSS Zhipin - Search Results"
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-021")
        result = submit_application("job-021", "boss", str(tmp_path), cdp_port=None)

        assert result.page_title == "BOSS Zhipin - Search Results"

    @patch("jobos.browser.sync_playwright")
    def test_cdp_port_uses_connect_over_cdp(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_browser_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-022")
        result = submit_application(
            "job-022", "boss", str(tmp_path),
            dry_run=True, cdp_port=9222,
        )

        pw.chromium.connect_over_cdp.assert_called_once_with("http://localhost:9222")
        assert result.dry_run is True

    @patch("jobos.browser.sync_playwright")
    def test_standalone_mode_uses_launch(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-023")
        result = submit_application("job-023", "boss", str(tmp_path), dry_run=True, cdp_port=None)

        pw.chromium.launch.assert_called_once()
        assert result.dry_run is True

    @patch("jobos.browser.sync_playwright")
    def test_browser_crash_returns_error(self, mock_pw_cls, tmp_path: Path) -> None:
        mock_pw_cls.return_value.start.side_effect = RuntimeError("Browser crashed")

        _make_pack_dir(tmp_path, "job-024")
        result = submit_application("job-024", "boss", str(tmp_path), dry_run=True)

        assert result.error is not None
        assert "Browser crashed" in result.error

    @patch("jobos.browser.sync_playwright")
    def test_screenshot_path_format(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-025")
        result = submit_application("job-025", "boss", str(tmp_path), cdp_port=None)

        assert result.screenshot_path is not None
        path = Path(result.screenshot_path)
        assert path.name == "dry_run_screenshot.png"
        assert "job-025" in str(path)

    @patch("jobos.browser.sync_playwright")
    def test_browser_cleanup_on_success(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-026")
        submit_application("job-026", "boss", str(tmp_path), cdp_port=None)

        browser.close.assert_called_once()
        pw.stop.assert_called_once()

    @patch("jobos.browser.sync_playwright")
    def test_browser_cleanup_on_failure(self, mock_pw_cls, tmp_path: Path) -> None:
        pw, browser, context, page = _mock_standalone_env()
        page.goto.side_effect = TimeoutError("Navigation timeout")
        mock_pw_cls.return_value.start.return_value = pw

        _make_pack_dir(tmp_path, "job-027")
        result = submit_application("job-027", "boss", str(tmp_path), cdp_port=None)

        browser.close.assert_called_once()
        pw.stop.assert_called_once()
        assert result.error is not None


# ---------------------------------------------------------------------------
# Tests: SubmitResult dataclass
# ---------------------------------------------------------------------------

class TestSubmitResult:
    """SubmitResult is a proper frozen dataclass."""

    def test_frozen(self) -> None:
        r = SubmitResult(
            job_id="x", platform="boss", dry_run=True,
            fields_filled={"a": "b"},
        )
        with pytest.raises(AttributeError):
            r.job_id = "y"  # type: ignore[misc]

    def test_default_values(self) -> None:
        r = SubmitResult(
            job_id="x", platform="boss", dry_run=True,
            fields_filled={},
        )
        assert r.screenshot_path is None
        assert r.submitted is False
        assert r.submitted_at is None
        assert r.error is None
        assert r.page_title is None
        assert r.page_url is None
