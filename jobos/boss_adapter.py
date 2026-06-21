"""BOSS Zhipin browser adapter.

The public submit interface owns BOSS page actions, success classification,
diagnostics, screenshots, and submit-attempt persistence.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

CHAT_BUTTON_SELECTORS = [
    '.btn-startchat',
    '[class*="startchat"]',
    'button.btn-startchat',
    'button:has-text("立即沟通")',
    'button:has-text("沟通")',
]
GREETING_SELECTORS = [
    '[contenteditable="true"]',
    '.chat-input',
    '.chat-editor textarea',
    '[class*="chat"] textarea',
    '.job-chat textarea',
    'textarea[placeholder*="招呼"]',
    'textarea[placeholder*="您好"]',
    '#chat-input',
]
SEND_BUTTON_SELECTORS = [
    '.send-message',
    '[class*="send-message"]',
    'button:has-text("发送")',
    '.chat-editor button[class*="send"]',
    '[class*="send-btn"]',
    'button:has-text("发送")',
]


def human_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> float:
    """Apply deterministic action pacing and return the delay used."""
    delay = max(0.0, min_sec)
    time.sleep(delay)
    return delay


def find_boss_tab(context) -> Optional[object]:
    """Return first open BOSS Zhipin tab in a browser context."""
    for page in context.pages:
        try:
            url = page.url
            if url and "zhipin.com" in url:
                return page
        except Exception:
            continue
    return None


def open_boss_job_page(page, job_url: str) -> None:
    """Navigate to a BOSS job page and wait for SPA rendering."""
    page.goto(job_url, wait_until="domcontentloaded", timeout=30000)


def click_chat_button(page) -> bool:
    """Click BOSS start-chat button if visible."""
    for selector in CHAT_BUTTON_SELECTORS:
        try:
            locator = page.locator(selector)
            btn = locator.first
            count = locator.count()
            if isinstance(count, int) and count == 0:
                print(f"   🔍 {selector}: count=0", file=sys.stderr)
                continue

            visible = btn.is_visible(timeout=3000)
            print(f"   🔍 {selector}: count={count}, visible={visible}", file=sys.stderr)
            if visible:
                btn.scroll_into_view_if_needed()
                btn.click()
                return True
        except Exception as e:
            print(f"   ⚠️ {selector}: {str(e)[:50]}", file=sys.stderr)
            continue
    return False


def fill_greeting(page, greeting_text: str) -> bool:
    """Fill the BOSS chat greeting field."""
    for selector in GREETING_SELECTORS:
        try:
            textarea = page.locator(selector).first
            if textarea.is_visible(timeout=5000):
                textarea.click()
                textarea.fill(greeting_text)
                return True
        except Exception:
            continue
    return False


def click_send(page) -> bool:
    """Click BOSS send button if visible."""
    for selector in SEND_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                return True
        except Exception:
            continue
    return False


def take_screenshot(page, path: Path) -> Optional[str]:
    """Take screenshot and return path string, or None on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


def safe_page_content(page) -> str:
    """Return page HTML, or empty string when unavailable."""
    try:
        content = page.content()
        return content if isinstance(content, str) else ""
    except Exception:
        return ""


def boss_message_sent(page) -> bool:
    """Return whether BOSS visible UI already says message was sent."""
    try:
        sent = page.locator('.status.success:has-text("已发送"), text=已发送')
        return sent.count() > 0 and sent.first.is_visible(timeout=1000)
    except Exception:
        return False


def classify_page_submit_success(page, greeting: str, expected_company: str = ""):
    """Classify BOSS submit success from page HTML and visible sent state."""
    from .live_pipeline import classify_submit_success

    success = classify_submit_success(safe_page_content(page), greeting, expected_company)
    if boss_message_sent(page) and "sent_state" not in success.signals:
        signals = [*success.signals, "sent_state"]
        return type(success)(
            success=True,
            signals=signals,
            diagnostics={**success.diagnostics, "visible_sent_state": True},
        )
    return success


@dataclass(frozen=True)
class BossSubmitResult:
    job_id: str
    status: str
    dry_run: bool
    submitted: bool
    fields_filled: dict[str, str]
    submitted_at: str | None = None
    error: str | None = None
    page_title: str | None = None
    page_url: str | None = None
    screenshot_path: str | None = None
    attempt_path: str | None = None
    submit_phase: str | None = None
    success_signals: list[str] = field(default_factory=list)
    screenshot_paths: dict[str, str] = field(default_factory=dict)
    page_state: str | None = None
    extractor: str | None = None
    recovery_signals: list[str] = field(default_factory=list)
    page_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_pipeline_record(self) -> dict[str, Any]:
        """Return the live-pipeline result shape."""
        record = {
            "status": self.status,
            "submit_phase": self.submit_phase,
            "success_signals": self.success_signals,
            "screenshot_paths": self.screenshot_paths,
            "page_state": self.page_state,
            "extractor": self.extractor,
            "recovery_signals": self.recovery_signals,
            "page_diagnostics": self.page_diagnostics,
            "attempt_path": self.attempt_path,
        }
        if self.error:
            record["error"] = self.error
        return record


def capture_page_diagnostics(page, phase: str) -> dict[str, Any]:
    """Classify the current BOSS page for an attempt record."""
    from .boss_parser import classify_boss_page, parse_chat_page, scrapling_available

    html = safe_page_content(page)
    if not html:
        return {"phase": phase, "error": "content_unavailable"}
    try:
        page_url = getattr(page, "url", "")
        title_fn = getattr(page, "title", None)
        page_title = title_fn() if callable(title_fn) else ""
        classification = classify_boss_page(html, url=page_url, title=page_title)
        return {
            "phase": phase,
            "extractor": "scrapling" if scrapling_available() else "beautifulsoup",
            "page_state": classification.state,
            "classification": classification.to_dict(),
            "recovery": classification.recovery,
            "chat_fields": parse_chat_page(html),
        }
    except Exception as exc:
        return {"phase": phase, "error": f"classification_failed: {exc}"}


def submit_boss_application(
    page,
    *,
    job_id: str,
    job_url: str,
    company: str,
    greeting: str,
    state_dir: str | Path,
    dry_run: bool = True,
    confirm: bool = False,
    validated: bool = False,
    navigate: bool = True,
) -> BossSubmitResult:
    """Execute one diagnosed BOSS submit transaction."""
    from .submission import (
        new_submit_attempt_record,
        submit_attempt_path,
        submit_attempt_result_update,
        utc_now,
        write_submit_attempt,
    )
    from .workspace import application_dir

    live = not dry_run and confirm
    if live and not validated:
        raise ValueError("Live BOSS submission requires validated content")

    state_dir = Path(state_dir)
    attempt_path = submit_attempt_path(state_dir, job_id)
    attempt = new_submit_attempt_record(
        job_id=job_id,
        url=job_url,
        platform="boss",
        mode="live" if live else "dry_run",
    )
    write_submit_attempt(attempt_path, attempt)
    screenshot_dir = application_dir(state_dir, job_id)
    screenshots: dict[str, str] = {}
    diagnostics: list[dict[str, Any]] = []
    fields_filled: dict[str, str] = {}

    def capture(phase: str) -> dict[str, Any]:
        diagnostic = capture_page_diagnostics(page, phase)
        diagnostics.append(diagnostic)
        return diagnostic

    def finish(
        status: str,
        phase: str,
        *,
        submitted: bool = False,
        error: str | None = None,
        success_signals: list[str] | None = None,
    ) -> BossSubmitResult:
        signals = success_signals or []
        submitted_at = utc_now() if submitted else None
        title_fn = getattr(page, "title", None)
        page_title = title_fn() if callable(title_fn) else None
        page_url = getattr(page, "url", None)
        screenshot_path = next(
            (
                screenshots.get(name)
                for name in ("post_submit", "pre_send", "pre_submit", "error")
                if screenshots.get(name)
            ),
            None,
        )
        last = diagnostics[-1] if diagnostics else {}
        recovery = list(
            dict.fromkeys(
                diagnostic.get("recovery")
                for diagnostic in diagnostics
                if diagnostic.get("recovery")
            )
        )
        attempt.update(
            submit_attempt_result_update(
                submitted=submitted,
                submitted_at=submitted_at,
                fields_filled=fields_filled,
                page_title=page_title,
                page_url=page_url,
                screenshot_path=screenshot_path,
                error=error,
                submit_phase=phase,
                success_signals=signals,
                screenshot_paths=screenshots,
            )
        )
        attempt["page_state"] = last.get("page_state")
        attempt["extractor"] = last.get("extractor")
        attempt["page_diagnostics"] = diagnostics
        attempt["recovery_signals"] = recovery
        write_submit_attempt(attempt_path, attempt)
        return BossSubmitResult(
            job_id=job_id,
            status=status,
            dry_run=dry_run,
            submitted=submitted,
            submitted_at=submitted_at,
            fields_filled=dict(fields_filled),
            error=error,
            page_title=page_title,
            page_url=page_url,
            screenshot_path=screenshot_path,
            attempt_path=str(attempt_path),
            submit_phase=phase,
            success_signals=signals,
            screenshot_paths=dict(screenshots),
            page_state=last.get("page_state"),
            extractor=last.get("extractor"),
            recovery_signals=recovery,
            page_diagnostics=list(diagnostics),
        )

    if not job_url:
        return finish("no_url", "input", error="No job URL found in job data")

    try:
        if navigate:
            open_boss_job_page(page, job_url)
        screenshots["pre_submit"] = take_screenshot(
            page,
            screenshot_dir / "pre_submit_screenshot.png",
        ) or ""
        capture("pre_submit")

        existing = classify_page_submit_success(page, greeting, company)
        if existing.success:
            screenshots["post_submit"] = take_screenshot(
                page,
                screenshot_dir / "post_submit_screenshot.png",
            ) or ""
            return finish(
                "submitted",
                "pre_existing_success",
                submitted=True,
                success_signals=existing.signals,
            )

        if not click_chat_button(page):
            capture("chat_button_missing")
            return finish(
                "no_chat_button",
                "chat_button",
                error="Could not find chat button",
            )
        if not greeting or not fill_greeting(page, greeting):
            capture("fill_failed")
            return finish("fill_failed", "fill", error="Could not fill greeting")

        fields_filled["招呼语"] = greeting
        screenshots["pre_send"] = take_screenshot(
            page,
            screenshot_dir / "pre_send_screenshot.png",
        ) or ""
        capture("pre_send")
        if not live:
            return finish("dry_run", "pre_send")

        if not click_send(page):
            capture("send_click_failed")
            return finish("send_failed", "send", error="Send click failed")

        screenshots["post_submit"] = take_screenshot(
            page,
            screenshot_dir / "post_submit_screenshot.png",
        ) or ""
        capture("post_send")
        success = classify_page_submit_success(page, greeting, company)
        if not success.success:
            return finish(
                "send_unverified",
                "post_send",
                error="Send clicked but success was not verified",
            )
        return finish(
            "submitted",
            "post_send",
            submitted=True,
            success_signals=success.signals,
        )
    except Exception as exc:
        screenshots["error"] = take_screenshot(
            page,
            screenshot_dir / "error_screenshot.png",
        ) or ""
        capture("error")
        return finish("error", "exception", error=str(exc))
