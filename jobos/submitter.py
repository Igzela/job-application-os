"""Semi-automatic application submitter with Playwright browser automation.

Supports two modes:

1. **Single job submission** via ``auto_submit_single`` -- opens a BOSS Zhipin
   job detail page, clicks the chat button, fills the greeting, takes
   screenshots, and optionally sends.

2. **Batch submission** via ``auto_submit_batch`` -- iterates through jobs in
   pipeline-approved submit candidate statuses, calling ``auto_submit_single``
   for each with configured pacing.

By default operates in dry-run mode: loads pack files, navigates to the target
site, takes screenshots, and returns what *would* be submitted without
clicking send.  Only when ``dry_run=False`` **and** ``confirm=True`` does the
submitter actually click the send button.

Live mode remains explicit, rate-limited, and diagnosed.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .boss_adapter import (
    click_chat_button,
    click_send,
    fill_greeting,
    find_boss_tab,
    human_delay,
    open_boss_job_page,
    submit_boss_application,
    take_screenshot,
)
from .pipeline import (
    SUBMIT_CANDIDATE_STATUSES,
    assert_live_submission_ready,
    is_submit_candidate_status,
    transition_job,
)
from .workspace import (
    application_dir,
    load_state,
    save_state,
    state_path as workspace_state_path,
)


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
    attempt_path: Optional[str] = None
    success_signals: List[str] = field(default_factory=list)


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
    if not app_dir.is_dir():
        return {}
    from .application_pack import load_application_pack

    return load_application_pack(app_dir).files


def _boss_dry_run_page_error(page) -> str | None:
    """Return a browser-smoke error when BOSS did not load usable content."""
    from .boss_parser import classify_boss_page

    page_url = getattr(page, "url", "")
    title_fn = getattr(page, "title", None)
    page_title = title_fn() if callable(title_fn) else ""
    html = page.content()
    classification = classify_boss_page(html, url=page_url, title=page_title)
    text_length = int(classification.signals.get("text_length") or 0)
    if text_length == 0 and not page_title.strip():
        return "BOSS page did not load visible content"
    if classification.state in {
        "access_limited",
        "login_required",
        "verification_required",
    }:
        return f"BOSS page blocked: {classification.state}: {classification.reason}"
    return None


_human_delay = human_delay
_find_boss_tab = find_boss_tab
_open_job_page = open_boss_job_page
_click_chat_button = click_chat_button
_fill_greeting = fill_greeting
_click_send = click_send
_take_screenshot = take_screenshot


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
        A Playwright page object (already connected to a browser).
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
    live = not dry_run and confirm
    if live:
        assert_live_submission_ready(job_data)
    result = submit_boss_application(
        page,
        job_id=job_id,
        job_url=job_data.get("url") or job_data.get("link", ""),
        company=job_data.get("company", ""),
        greeting=pack_files.get("greeting.md", ""),
        state_dir=state_dir,
        dry_run=dry_run,
        confirm=confirm,
        validated=live,
    )
    return SubmitResult(
        job_id=result.job_id,
        platform="boss",
        dry_run=result.dry_run,
        fields_filled=result.fields_filled,
        screenshot_path=result.screenshot_path,
        submitted=result.submitted,
        submitted_at=result.submitted_at,
        error=result.error,
        page_title=result.page_title,
        page_url=result.page_url,
        attempt_path=result.attempt_path,
        success_signals=result.success_signals,
    )


def auto_submit_workspace_job(
    state_dir: str,
    job_id: str,
    cdp_port: int | None = 9222,
    headless: bool = False,
    dry_run: bool = True,
    confirm: bool = False,
) -> SubmitResult:
    """Load one workspace job and run BOSS auto-submit with browser cleanup."""
    root = Path(state_dir)
    if not workspace_state_path(root).exists():
        raise FileNotFoundError("No .job-state.json found. Run `job init` first.")

    state = load_state(root)
    job_info = state.get("jobs", {}).get(job_id)
    if not job_info:
        raise ValueError(f"Job {job_id} not found in state.")
    if not (job_info.get("url") or job_info.get("link")):
        raise ValueError(f"Job {job_id} has no job URL.")
    if not dry_run and confirm:
        assert_live_submission_ready(job_info)

    from .application_pack import (
        load_application_pack,
        load_live_application_pack,
    )

    if not dry_run and confirm:
        pack_files = load_live_application_pack(
            application_dir(root, job_id),
            job_id=job_id,
            expected_validation=job_info["validation"],
        ).files
    else:
        pack_files = load_application_pack(
            application_dir(root, job_id),
            job_id=job_id,
        ).files
    if not pack_files:
        raise FileNotFoundError(
            f"No application pack for {job_id}. Run `job pack` first."
        )

    pw, browser, _context, page = _connect_browser(cdp_port, headless)
    try:
        return auto_submit_single(
            page=page,
            job_data={"job_id": job_id, **job_info},
            pack_files=pack_files,
            state_dir=str(root),
            dry_run=dry_run,
            confirm=confirm,
        )
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
    submissions for configured pacing.

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
    state_path = workspace_state_path(state_dir)
    if not state_path.exists():
        summary = BatchSummary()
        summary.errors.append("No .job-state.json found. Run `job init` first.")
        return summary

    state = load_state(state_dir)
    all_jobs = state.get("jobs", {})

    summary = BatchSummary()
    live = not dry_run and confirm

    # Dry-run may inspect legacy candidates. Live mode requires clean validation.
    ready_jobs = []
    for job_id, job_info in all_jobs.items():
        status = job_info.get("status", "")
        if is_submit_candidate_status(status):
            candidate = {"job_id": job_id, **job_info}
            if live:
                try:
                    assert_live_submission_ready(job_info)
                    from .application_pack import load_live_application_pack

                    pack_files = load_live_application_pack(
                        application_dir(state_dir, job_id),
                        job_id=job_id,
                        expected_validation=job_info["validation"],
                    ).files
                except ValueError as exc:
                    summary.errors.append(f"{job_id}: {exc}")
                    continue
                if not pack_files:
                    summary.errors.append(f"{job_id}: No application pack found")
                    continue
                candidate["_pack_files"] = pack_files
            ready_jobs.append(candidate)

    if not ready_jobs:
        if not summary.errors:
            expected = ", ".join(f"'{status}'" for status in SUBMIT_CANDIDATE_STATUSES)
            summary.errors.append(f"No jobs in {expected} status found.")
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

        for i, job_info in enumerate(ready_jobs):
            job_id = job_info["job_id"]

            # Load pack files
            pack_files = job_info.pop("_pack_files", None)
            if pack_files is None:
                app_dir = application_dir(state_dir, job_id)
                from .application_pack import load_application_pack

                pack_files = load_application_pack(
                    app_dir,
                    job_id=job_id,
                    require_manifest=False,
                ).files

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
                    transition_job(state["jobs"][job_id], "submitted")
                    state["jobs"][job_id]["submitted_at"] = result.submitted_at or ""
                    save_state(state_dir, state)

            # Random delay between jobs (skip after last job)
            if i < len(ready_jobs) - 1:
                delay = max(0, interval_min)
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
    app_dir = application_dir(state_dir, job_id)

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
            from .browser import wait_for_page_content

            wait_for_page_content(page)
            screenshot_dir = application_dir(state_dir, job_id)
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(screenshot_dir / "dry_run_screenshot.png")
            page.screenshot(path=screenshot_path)
            page_error = _boss_dry_run_page_error(page)
            return SubmitResult(
                job_id=job_id,
                platform=platform,
                dry_run=True,
                fields_filled=result.fields_filled,
                screenshot_path=screenshot_path,
                error=page_error,
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

        screenshot_dir = application_dir(state_dir, job_id)
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
