"""Browser connection manager for Playwright + CDP.

Default: connect to user's Chrome via CDP (port 9222).
Fallback: launch standalone Chromium.

Chromium path: /opt/chromium/chrome-linux/chrome
Persistent user data: /tmp/chrome-boss (keeps login state across sessions)
"""

from __future__ import annotations

from typing import Optional, Tuple

from playwright.sync_api import sync_playwright

CHROMIUM_PATH = "/opt/chromium/chrome-linux/chrome"
DEFAULT_CDP_PORT = 9222
USER_DATA_DIR = "/tmp/chrome-boss"


def connect_cdp(
    port: int = DEFAULT_CDP_PORT,
) -> Tuple:  # (pw, browser, context)
    """Connect to user's Chrome via CDP."""
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
    context = browser.contexts[0]
    return pw, browser, context


def launch_standalone(
    headless: bool = False,
) -> Tuple:  # (pw, browser, context, page)
    """Launch Chromium with persistent user data."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        executable_path=CHROMIUM_PATH,
        user_data_dir=USER_DATA_DIR,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={DEFAULT_CDP_PORT}",
        ],
    )
    context = browser.new_context()
    page = context.new_page()
    return pw, browser, context, page


def get_browser(
    cdp_port: Optional[int] = DEFAULT_CDP_PORT,
    headless: bool = False,
) -> Tuple:  # (pw, browser, context, page)
    """Smart browser getter: try CDP first, then standalone.

    Returns (pw, browser, context, page_or_none).
    """
    if cdp_port:
        try:
            pw, browser, context = connect_cdp(cdp_port)
            page = context.pages[0] if context.pages else context.new_page()
            return pw, browser, context, page
        except Exception:
            pass
    # Fallback to standalone
    pw, browser, context, page = launch_standalone(headless=headless)
    return pw, browser, context, page
