"""Browser connection manager with anti-detection stealth.

Uses Patchright (patched Playwright) instead of vanilla Playwright.
Patchright removes navigator.webdriver and other automation markers.

Default: connect to an already-running Chrome via CDP (port 9222).
Standalone launch is opt-in with cdp_port=None and always uses an isolated profile.

Chromium path: /opt/chromium/chrome-linux/chrome
Persistent user data: /tmp/chrome-boss (isolated from the user's real Chrome)
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional, Tuple


def _get_sync_playwright():
    """Get sync_playwright module."""
    try:
        from patchright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        from playwright.sync_api import sync_playwright
        return sync_playwright


def _get_async_playwright():
    """Get async_playwright module."""
    try:
        from patchright.async_api import async_playwright
        return async_playwright
    except ImportError:
        from playwright.async_api import async_playwright
        return async_playwright


def _is_in_async_context():
    """Check if we're running inside an asyncio event loop."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False

CHROMIUM_PATH = "/opt/chromium/chrome-linux/chrome"
DEFAULT_CDP_PORT = 9222
USER_DATA_DIR = os.environ.get(
    "JOBOS_BROWSER_USER_DATA_DIR",
    os.path.expanduser("~/.jobos-chrome-profile"),
)
PROFILE_DIRECTORY = os.environ.get("JOBOS_BROWSER_PROFILE_DIRECTORY", "Profile 1")

# Never use ~/.config/google-chrome or other user profiles here. Automation must
# not open a real browser profile because Chromium can rewrite cookie/session DBs.
CHROME_PROFILE_DIR = None

STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--disable-ipc-flooding-protection",
    "--disable-backgrounding-occluded-windows",
    "--enable-features=NetworkService,TrustTokens",
    "--blink-settings=primaryHoverType=2,availableHoverTypes=2,primaryPointerType=4,availablePointerTypes=4",
]


def connect_cdp(port: int = DEFAULT_CDP_PORT) -> Tuple:
    """Connect to user's Chrome via CDP."""
    sync_playwright = _get_sync_playwright()
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
        context = browser.contexts[0]
        return pw, browser, context
    except Exception:
        # Clean up the playwright instance if connection fails
        try:
            pw.stop()
        except Exception:
            pass
        raise


def launch_standalone(headless: bool = False) -> Tuple:
    """Launch Chromium with stealth flags and isolated persistent user data."""
    sync_playwright = _get_sync_playwright()
    pw = sync_playwright().start()
    try:
        user_data_dir = USER_DATA_DIR
        print(f"   使用隔离浏览器配置: {USER_DATA_DIR} ({PROFILE_DIRECTORY})")

        # Use launch_persistent_context for persistent user data
        context = pw.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=headless,
            executable_path=CHROMIUM_PATH,
            args=STEALTH_ARGS + [
                f"--remote-debugging-port={DEFAULT_CDP_PORT}",
                f"--profile-directory={PROFILE_DIRECTORY}",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        # Return None for browser since we're using persistent context
        return pw, None, context, page
    except Exception:
        # Clean up the playwright instance if launch fails
        try:
            pw.stop()
        except Exception:
            pass
        raise


def get_browser(
    cdp_port: Optional[int] = DEFAULT_CDP_PORT,
    headless: bool = False,
) -> Tuple:
    """Return a browser session.

    With a CDP port, connect only to an already-running browser and fail if it
    is unavailable. Passing ``cdp_port=None`` explicitly opts into isolated
    standalone Chromium.

    Returns (pw, browser, context, page_or_none).
    """
    if cdp_port:
        try:
            pw, browser, context = connect_cdp(cdp_port)
            page = context.pages[0] if context.pages else context.new_page()
            return pw, browser, context, page
        except Exception as exc:
            raise ConnectionError(
                f"CDP browser unavailable on port {cdp_port}. "
                "Start Chrome explicitly with remote debugging, or pass cdp_port=None "
                "to launch isolated standalone Chromium."
            ) from exc
    pw, browser, context, page = launch_standalone(headless=headless)
    return pw, browser, context, page
