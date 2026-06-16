"""Safety tests for browser profile handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jobos import browser


def test_launch_standalone_uses_isolated_profile(monkeypatch) -> None:
    calls = {}

    class Chromium:
        def launch_persistent_context(self, **kwargs):
            calls.update(kwargs)
            context = MagicMock()
            context.pages = []
            context.new_page.return_value = object()
            return context

    class Playwright:
        chromium = Chromium()

        def stop(self):
            pass

    class SyncPlaywright:
        def start(self):
            return Playwright()

    monkeypatch.setattr(browser, "_get_sync_playwright", lambda: SyncPlaywright)
    monkeypatch.setattr(browser, "CHROME_PROFILE_DIR", "/home/user/.config/google-chrome")

    browser.launch_standalone()

    assert calls["user_data_dir"] == browser.USER_DATA_DIR
    assert "google-chrome" not in calls["user_data_dir"]
    assert f"--profile-directory={browser.PROFILE_DIRECTORY}" in calls["args"]


def test_get_browser_does_not_fallback_when_cdp_requested(monkeypatch) -> None:
    monkeypatch.setattr(browser, "connect_cdp", MagicMock(side_effect=RuntimeError("cdp down")))
    launch = MagicMock()
    monkeypatch.setattr(browser, "launch_standalone", launch)

    with pytest.raises(ConnectionError, match="CDP"):
        browser.get_browser(cdp_port=9222)

    launch.assert_not_called()


def test_get_browser_allows_isolated_standalone_when_no_cdp_requested(monkeypatch) -> None:
    expected = (object(), None, object(), object())
    launch = MagicMock(return_value=expected)
    monkeypatch.setattr(browser, "launch_standalone", launch)

    assert browser.get_browser(cdp_port=None) == expected
    launch.assert_called_once()
