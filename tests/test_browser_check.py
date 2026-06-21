"""Tests for explicit BOSS browser readiness checks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jobos.browser_check import BrowserCheckResult, check_boss_browser
from jobos.cli import _cmd_browser_check


def _browser_session():
    pw = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()
    page.title.return_value = "BOSS Job Search"
    page.url = "https://www.zhipin.com/web/geek/job?query=Python"
    page.content.return_value = "<html><body>Python jobs</body></html>"
    return pw, browser, context, page


@patch("jobos.browser_check.capture_page_diagnostics")
@patch("jobos.browser_check.get_browser")
def test_browser_check_reports_normal_page_ready(
    mock_get_browser,
    mock_diagnostics,
    tmp_path: Path,
) -> None:
    session = _browser_session()
    mock_get_browser.return_value = session
    mock_diagnostics.return_value = {
        "page_state": "normal",
        "recovery": "",
    }

    result = check_boss_browser(tmp_path, cdp_port=None, headless=True)

    assert result.ok is True
    assert result.page_state == "normal"
    assert result.screenshot_path.endswith("boss_browser_check.png")
    assert result.html_path.endswith("boss_browser_check.html")
    assert result.diagnostics_path.endswith("boss_browser_check.json")
    assert Path(result.html_path).exists()
    assert Path(result.diagnostics_path).exists()
    session[1].close.assert_called_once()
    session[0].stop.assert_called_once()


@patch("jobos.browser_check.capture_page_diagnostics")
@patch("jobos.browser_check.get_browser")
def test_browser_check_reports_login_required(
    mock_get_browser,
    mock_diagnostics,
    tmp_path: Path,
) -> None:
    session = _browser_session()
    mock_get_browser.return_value = session
    mock_diagnostics.return_value = {
        "page_state": "login_required",
        "recovery": "Log into BOSS Zhipin in the browser and retry.",
    }

    result = check_boss_browser(tmp_path, cdp_port=9222)

    assert result.ok is False
    assert result.page_state == "login_required"
    assert "Log into BOSS" in result.recovery


@patch("jobos.browser_check.check_boss_browser")
@patch("jobos.cli._get_root")
def test_cmd_browser_check_standalone_exits_on_blocker(
    mock_root,
    mock_check,
    tmp_path: Path,
) -> None:
    mock_root.return_value = tmp_path
    mock_check.return_value = BrowserCheckResult(
        ok=False,
        page_state="login_required",
        page_title="BOSS",
        page_url="https://www.zhipin.com/",
        screenshot_path="/tmp/boss.png",
        recovery="Log in and retry.",
    )

    with pytest.raises(SystemExit) as exc:
        _cmd_browser_check(
            SimpleNamespace(
                port=9222,
                standalone_browser=True,
                headless=True,
            )
        )

    assert exc.value.code == 1
    assert mock_check.call_args.kwargs["cdp_port"] is None
