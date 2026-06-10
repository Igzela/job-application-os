"""Browser connection manager with anti-detection stealth.

Uses Patchright (patched Playwright) instead of vanilla Playwright.
Patchright removes navigator.webdriver and other automation markers.

Default: connect to user's Chrome via CDP (port 9222).
Fallback: launch standalone Chromium with stealth flags.

Chromium path: /opt/chromium/chrome-linux/chrome
Persistent user data: /tmp/chrome-boss (keeps login state across sessions)
"""

from __future__ import annotations

from typing import Optional, Tuple

try:
    from patchright.sync_api import sync_playwright
except ImportError:
    from playwright.sync_api import sync_playwright

CHROMIUM_PATH = "/opt/chromium/chrome-linux/chrome"
DEFAULT_CDP_PORT = 9222
USER_DATA_DIR = "/tmp/chrome-boss"

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
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}")
    context = browser.contexts[0]
    return pw, browser, context


def launch_standalone(headless: bool = False) -> Tuple:
    """Launch Chromium with stealth flags and persistent user data."""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=headless,
        executable_path=CHROMIUM_PATH,
        user_data_dir=USER_DATA_DIR,
        args=STEALTH_ARGS + [
            f"--remote-debugging-port={DEFAULT_CDP_PORT}",
        ],
    )
    context = browser.new_context()
    page = context.new_page()
    return pw, browser, context, page


def get_browser(
    cdp_port: Optional[int] = DEFAULT_CDP_PORT,
    headless: bool = False,
) -> Tuple:
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
    pw, browser, context, page = launch_standalone(headless=headless)
    return pw, browser, context, page
