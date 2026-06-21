"""Explicit browser readiness check for BOSS Zhipin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .boss_adapter import capture_page_diagnostics
from .browser import get_browser, wait_for_page_content
from .runtime_state import save_json_state


BOSS_CHECK_URL = "https://www.zhipin.com/web/geek/job?query=Python"


@dataclass(frozen=True)
class BrowserCheckResult:
    ok: bool
    page_state: str
    page_title: str = ""
    page_url: str = ""
    screenshot_path: str | None = None
    html_path: str | None = None
    diagnostics_path: str | None = None
    recovery: str = ""
    error: str | None = None


def check_boss_browser(
    state_dir: str | Path,
    *,
    cdp_port: int | None = 9222,
    headless: bool = False,
) -> BrowserCheckResult:
    """Connect, open a read-only BOSS search page, classify, and screenshot."""
    pw = browser = context = page = None
    try:
        pw, browser, context, page = get_browser(
            cdp_port=cdp_port,
            headless=headless,
        )
        page.goto(
            BOSS_CHECK_URL,
            wait_until="domcontentloaded",
            timeout=30000,
        )
        wait_for_page_content(page)

        screenshot_dir = Path(state_dir) / "browser_checks"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / "boss_browser_check.png"
        html_path = screenshot_dir / "boss_browser_check.html"
        diagnostics_path = screenshot_dir / "boss_browser_check.json"
        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")

        diagnostics = capture_page_diagnostics(page, "browser_check")
        page_state = str(diagnostics.get("page_state") or "error")
        save_json_state(
            diagnostics_path,
            {
                **diagnostics,
                "page_title": page.title(),
                "page_url": page.url,
                "screenshot_path": str(screenshot_path),
                "html_path": str(html_path),
            },
        )
        return BrowserCheckResult(
            ok=page_state == "normal",
            page_state=page_state,
            page_title=page.title(),
            page_url=page.url,
            screenshot_path=str(screenshot_path),
            html_path=str(html_path),
            diagnostics_path=str(diagnostics_path),
            recovery=str(diagnostics.get("recovery") or ""),
            error=str(diagnostics.get("error") or "") or None,
        )
    except Exception as exc:
        return BrowserCheckResult(
            ok=False,
            page_state="connection_failed",
            page_title=page.title() if page is not None else "",
            page_url=page.url if page is not None else "",
            error=str(exc),
        )
    finally:
        try:
            if browser is not None:
                browser.close()
            elif context is not None:
                context.close()
        except Exception:
            pass
        try:
            if pw is not None:
                pw.stop()
        except Exception:
            pass
