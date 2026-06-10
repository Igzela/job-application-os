"""Semi-automatic application submitter with Playwright browser automation.

Supports two modes:

1. **Single job submission** via ``auto_submit_single`` -- opens a BOSS Zhipin
   job detail page, clicks the chat button, fills the greeting, takes
   screenshots, and optionally sends.

2. **Batch submission** via ``auto_submit_batch`` -- iterates through jobs in
   ``predicted`` or ``packed`` status, calling ``auto_submit_single`` for each
   with random delays for anti-detection.

By default operates in dry-run mode: loads pack files, navigates to the target
site, takes screenshots, and returns what *would* be submitted without
clicking send.  Only when ``dry_run=False`` **and** ``confirm=True`` does the
submitter actually click the send button.

Anti-detection:
- Random 2-5 s delay between UI actions (``_human_delay``).
- Random 30-120 s delay between jobs in batch mode.
- Patchright is used instead of vanilla Playwright (removes webdriver flag).
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Platform field mappings
# ---------------------------------------------------------------------------

# boss platform: pack filename -> form field name
BOSS_FIELD_MAP: Dict[str, str] = {
    "greeting.md": "招呼语",
    "resume_targeted.md": "简历",
    "cover_letter.md": "求职信",
    "form_answers.md": "附加信息",
}

PLATFORM_MAPS: Dict[str, Dict[str, str]] = {
    "boss": BOSS_FIELD_MAP,
}

# BOSS Zhipin selectors -- best-effort, may need updating if the site changes
CHAT_BUTTON_SELECTORS = [
    'button.btn-startchat',
    'button:has-text("立即沟通")',
    '.btn-startchat',
    '[class*="startchat"]',
    'button:has-text("沟通")',
]
GREETING_SELECTORS = [
    '.chat-editor textarea',
    '[class*="chat"] textarea',
    '.job-chat textarea',
    'textarea[placeholder*="招呼"]',
    'textarea[placeholder*="您好"]',
    '#chat-input',
]
SEND_BUTTON_SELECTORS = [
    'button:has-text("发送")',
    '.chat-editor button[class*="send"]',
    '[class*="send-btn"]',
    'button:has-text("发送")',
]


def get_platform_fields(platform: str) -> Dict[str, str]:
    """Return the pack-file -> form-field mapping for *platform*.

    Raises ValueError if the platform is unknown.
    """
    mapping = PLATFORM_MAPS.get(platform)
    if mapping is None:
        known = ", ".join(sorted(PLATFORM_MAPS))
        raise ValueError(
            f"Unknown platform {platform!r}. Known platforms: {known}"
        )
    return mapping


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubmitResult:
    job_id: str
    platform: str
    dry_run: bool
    fields_filled: Dict[str, str]  # field_name -> value
    screenshot_path: Optional[str] = None
    submitted: bool = False
    submitted_at: Optional[str] = None
    error: Optional[str] = None
    page_title: Optional[str] = None
    page_url: Optional[str] = None


@dataclass
class BatchSummary:
    total_attempted: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    results: List[SubmitResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_pack_files(app_dir: Path) -> Dict[str, str]:
    """Load all files from an application pack directory."""
    files: Dict[str, str] = {}
    if not app_dir.is_dir():
        return files
    for p in app_dir.iterdir():
        if p.is_file():
            files[p.name] = p.read_text(encoding="utf-8")
    return files


def _human_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> float:
    """Sleep a random duration between *min_sec* and *max_sec*.

    Returns the actual delay so callers can log or assert it.
    """
    delay = random.uniform(min_sec, max_sec)
    time.sleep(delay)
    return delay


def _find_boss_tab(context) -> Optional[object]:
    """Find an existing BOSS Zhipin tab in the browser *context*.

    Searches all open pages for one whose URL contains ``zhipin.com``.
    Returns the page object or ``None``.
    """
    for page in context.pages:
        try:
            url = page.url
            if url and "zhipin.com" in url:
                return page
        except Exception:
            continue
    return None


def _open_job_page(page, job_url: str) -> None:
    """Navigate *page* to *job_url* and wait for network idle."""
    page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
    # Extra wait for SPA to finish rendering
    _human_delay(1.5, 3.0)


def _click_chat_button(page) -> bool:
    """Find and click the 'start chat' button on a BOSS job page.

    Returns True if a button was found and clicked.
    """
    for selector in CHAT_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                _human_delay()
                return True
        except Exception:
            continue
    return False


def _fill_greeting(page, greeting_text: str) -> bool:
    """Find the chat greeting textarea and fill it with *greeting_text*.

    Returns True if a textarea was found and filled.
    """
    for selector in GREETING_SELECTORS:
        try:
            textarea = page.locator(selector).first
            if textarea.is_visible(timeout=5000):
                textarea.fill(greeting_text)
                _human_delay()
                return True
        except Exception:
            continue
    return False


def _click_send(page) -> bool:
    """Find and click the 'send' button in the chat window.

    Returns True if a send button was found and clicked.
    """
    for selector in SEND_BUTTON_SELECTORS:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=3000):
                btn.click()
                _human_delay()
                return True
        except Exception:
            continue
    return False


def _take_screenshot(page, path: Path) -> Optional[str]:
    """Take a screenshot and return the path string, or None on failure."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core logic -- single submission
# ---------------------------------------------------------------------------

def auto_submit_single(
    page,
    job_data: Dict[str, str],
    pack_files: Dict[str, str],
    state_dir: str,
    dry_run: bool = True,
    confirm: bool = False,
) -> SubmitResult:
    """Open a BOSS Zhipin job page, fill the greeting, and optionally send.

    Parameters
    ----------
    page:
        A Playwright/Patchright page object (already connected to a browser).
    job_data:
        Dict with at least ``job_id``, ``title``, ``company``, and ``link``.
    pack_files:
        Pack file contents keyed by filename (e.g. ``{"greeting.md": "..."}``).
    state_dir:
        Project root / state directory for saving screenshots.
    dry_run:
        If True, navigate and screenshot but never click send.
    confirm:
        If True AND ``dry_run=False``, actually click the send button.

    Returns
    -------
    SubmitResult
    """
    job_id = job_data.get("job_id", "unknown")
    job_url = job_data.get("link", "")
    platform = "boss"
    greeting_text = pack_files.get("greeting.md", "")

    if not job_url:
        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=dry_run,
            fields_filled=pack_files,
            error="No job URL found in job data",
        )

    fields_filled: Dict[str, str] = {}
    screenshot_dir = Path(state_dir) / "applications" / job_id

    try:
        # 1. Navigate to job page
        _open_job_page(page, job_url)

        pre_screenshot = _take_screenshot(
            page, screenshot_dir / "pre_submit_screenshot.png"
        )

        # 2. Click the "start chat" button
        chat_clicked = _click_chat_button(page)
        if not chat_clicked:
            return SubmitResult(
                job_id=job_id,
                platform=platform,
                dry_run=dry_run,
                fields_filled=fields_filled,
                screenshot_path=pre_screenshot,
                error="Could not find 'start chat' button on page",
                page_title=page.title(),
                page_url=page.url,
            )

        _human_delay()

        # 3. Fill greeting text
        if greeting_text:
            filled = _fill_greeting(page, greeting_text)
            if filled:
                fields_filled["招呼语"] = greeting_text
            # If we can't find the textarea, that's OK -- we still screenshot

        # 4. Pre-send screenshot
        pre_send_screenshot = _take_screenshot(
            page, screenshot_dir / "pre_send_screenshot.png"
        )

        # 5. Send if confirmed
        submitted = False
        submitted_at = None
        if not dry_run and confirm:
            sent = _click_send(page)
            if sent:
                submitted = True
                submitted_at = datetime.now(timezone.utc).isoformat()
                _take_screenshot(
                    page, screenshot_dir / "post_send_screenshot.png"
                )

        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=dry_run,
            fields_filled=fields_filled,
            screenshot_path=pre_send_screenshot or pre_screenshot,
            submitted=submitted,
            submitted_at=submitted_at,
            page_title=page.title(),
            page_url=page.url,
        )

    except Exception as e:
        error_screenshot = _take_screenshot(
            page, screenshot_dir / "error_screenshot.png"
        )
        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=dry_run,
            fields_filled=fields_filled,
            screenshot_path=error_screenshot,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Core logic -- batch submission
# ---------------------------------------------------------------------------

def auto_submit_batch(
    state_dir: str,
    cdp_port: int = 9222,
    max_jobs: int = 5,
    interval_min: int = 30,
    interval_max: int = 120,
    dry_run: bool = True,
    confirm: bool = False,
) -> BatchSummary:
    """Iterate through predicted/packed jobs and submit each one.

    Loads ``.job-state.json``, finds jobs in ``predicted`` or ``packed``
    status, and calls :func:`auto_submit_single` for each.  Random delay
    between ``interval_min`` and ``interval_max`` seconds is applied between
    submissions for anti-detection.

    Parameters
    ----------
    state_dir:
        Project root / state directory.
    cdp_port:
        Chrome debug port for CDP connection.
    max_jobs:
        Maximum number of jobs to process in this batch.
    interval_min:
        Minimum seconds between job submissions.
    interval_max:
        Maximum seconds between job submissions.
    dry_run:
        If True, never click send.
    confirm:
        If True AND ``dry_run=False``, click send.

    Returns
    -------
    BatchSummary
    """
    state_path = Path(state_dir) / ".job-state.json"
    if not state_path.exists():
        summary = BatchSummary()
        summary.errors.append("No .job-state.json found. Run `job init` first.")
        return summary

    state = json.loads(state_path.read_text(encoding="utf-8"))
    all_jobs = state.get("jobs", {})

    # Filter to jobs that are ready for submission
    ready_jobs = []
    for job_id, job_info in all_jobs.items():
        status = job_info.get("status", "")
        if status in ("predicted", "packed"):
            ready_jobs.append({"job_id": job_id, **job_info})

    if not ready_jobs:
        summary = BatchSummary()
        summary.errors.append("No jobs in 'predicted' or 'packed' status found.")
        return summary

    # Limit to max_jobs
    ready_jobs = ready_jobs[:max_jobs]

    # Connect browser
    from .browser import get_browser

    pw, browser, context, page = get_browser(cdp_port=cdp_port, headless=False)
    try:
        # Check for existing BOSS tab
        boss_tab = _find_boss_tab(context)
        if boss_tab is not None:
            page = boss_tab

        summary = BatchSummary()

        for i, job_info in enumerate(ready_jobs):
            job_id = job_info["job_id"]

            # Load pack files
            app_dir = Path(state_dir) / "applications" / job_id
            pack_files = _load_pack_files(app_dir)

            if not pack_files:
                summary.total_attempted += 1
                summary.total_failed += 1
                summary.errors.append(f"{job_id}: No application pack found")
                continue

            result = auto_submit_single(
                page=page,
                job_data=job_info,
                pack_files=pack_files,
                state_dir=state_dir,
                dry_run=dry_run,
                confirm=confirm,
            )

            summary.total_attempted += 1
            summary.results.append(result)

            if result.error:
                summary.total_failed += 1
                summary.errors.append(f"{job_id}: {result.error}")
            else:
                summary.total_succeeded += 1

                # Update job status in state
                if not dry_run and result.submitted:
                    state["jobs"][job_id]["status"] = "submitted"
                    state["jobs"][job_id]["submitted_at"] = result.submitted_at or ""
                    state_path.write_text(
                        json.dumps(state, indent=2, ensure_ascii=False) + "\n"
                    )

            # Random delay between jobs (skip after last job)
            if i < len(ready_jobs) - 1:
                delay = random.uniform(interval_min, interval_max)
                print(
                    f"  Waiting {delay:.0f}s before next job...",
                    file=sys.stderr,
                )
                time.sleep(delay)

        return summary

    finally:
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Legacy single-job submission (preserved for backward compat)
# ---------------------------------------------------------------------------

def _connect_browser(
    cdp_port: Optional[int],
    headless: bool,
):
    """Return ``(pw, browser, context, page)`` via CDP or standalone launch."""
    from .browser import get_browser
    return get_browser(cdp_port=cdp_port, headless=headless)


def prepare_submission(
    job_id: str,
    platform: str,
    state_dir: str,
) -> SubmitResult:
    """Prepare application data for submission (dry-run mode).

    Loads pack files from ``<state_dir>/applications/<job_id>/`` and maps
    them to platform form fields.  Returns a :class:`SubmitResult` with
    ``dry_run=True`` and the fields that would be filled.
    """
    state = Path(state_dir)
    app_dir = state / "applications" / job_id

    if not app_dir.is_dir():
        raise FileNotFoundError(
            f"No application pack found for job {job_id!r}. "
            f"Expected directory: {app_dir}"
        )

    field_map = get_platform_fields(platform)
    pack_files = _load_pack_files(app_dir)

    fields_filled: Dict[str, str] = {}
    for pack_filename, form_field_name in field_map.items():
        content = pack_files.get(pack_filename)
        if content:
            fields_filled[form_field_name] = content

    return SubmitResult(
        job_id=job_id,
        platform=platform,
        dry_run=True,
        fields_filled=fields_filled,
    )


def submit_application(
    job_id: str,
    platform: str,
    state_dir: str,
    dry_run: bool = True,
    confirm: bool = False,
    cdp_port: Optional[int] = 9222,
    headless: bool = False,
) -> SubmitResult:
    """Submit application to *platform* (legacy single-job interface).

    For the new auto-submit flow, use ``auto_submit_single`` or
    ``auto_submit_batch`` instead.
    """
    result = prepare_submission(job_id, platform, state_dir)

    if dry_run:
        pw, browser, context, page = None, None, None, None
        try:
            pw, browser, context, page = _connect_browser(cdp_port, headless)
            page.goto(
                "https://www.zhipin.com",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            time.sleep(3)
            screenshot_dir = Path(state_dir) / "applications" / job_id
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(screenshot_dir / "dry_run_screenshot.png")
            page.screenshot(path=screenshot_path)
            return SubmitResult(
                job_id=job_id,
                platform=platform,
                dry_run=True,
                fields_filled=result.fields_filled,
                screenshot_path=screenshot_path,
                page_title=page.title(),
                page_url=page.url,
            )
        except Exception as e:
            return SubmitResult(
                job_id=job_id,
                platform=platform,
                dry_run=True,
                fields_filled=result.fields_filled,
                error=str(e),
            )
        finally:
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

    if not confirm:
        print("Fields that would be submitted:", file=sys.stderr)
        for field_name, value in result.fields_filled.items():
            preview = value[:80] + ("..." if len(value) > 80 else "")
            print(f"  {field_name}: {preview}", file=sys.stderr)
        print(
            "\nAborted: pass --confirm to proceed with submission.",
            file=sys.stderr,
        )
        raise ValueError(
            "Submission requires --confirm flag. "
            "Review the fields above and re-run with --confirm."
        )

    pw, browser, context, page = None, None, None, None
    try:
        pw, browser, context, page = _connect_browser(cdp_port, headless)
        page.goto(
            "https://www.zhipin.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(3)

        boss_selectors = {
            "招呼语": 'textarea[name="greeting"], textarea.greeting-input, #greeting',
            "简历": 'input[type="file"][name="resume"], .resume-upload input[type="file"]',
            "求职信": 'textarea[name="coverLetter"], textarea.cover-letter, #coverLetter',
            "附加信息": 'textarea[name="additionalInfo"], textarea.additional-info',
        }

        fields_actually_filled: Dict[str, str] = {}
        for field_name, content in result.fields_filled.items():
            selector = boss_selectors.get(field_name)
            if selector:
                try:
                    element = page.locator(selector).first
                    if element.is_visible(timeout=3000):
                        element.fill(content)
                        fields_actually_filled[field_name] = content
                except Exception:
                    pass
            else:
                fields_actually_filled[field_name] = content

        screenshot_dir = Path(state_dir) / "applications" / job_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(screenshot_dir / "submit_screenshot.png")
        page.screenshot(path=screenshot_path)

        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=False,
            fields_filled=fields_actually_filled,
            screenshot_path=screenshot_path,
            submitted=False,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            page_title=page.title(),
            page_url=page.url,
        )
    except Exception as e:
        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=False,
            fields_filled=result.fields_filled,
            error=str(e),
        )
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
