"""Semi-automatic application submitter with Playwright browser automation.

By default operates in dry-run mode: loads pack files, maps them to platform
form fields, navigates to the target site, takes a screenshot, and returns
what *would* be submitted without touching any form elements.

When ``dry_run=False`` and ``confirm=True``, the submitter fills form fields
on the real page.  The final click-to-submit is intentionally commented out
for safety until the workflow is battle-tested.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


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


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _load_pack_files(app_dir: Path) -> Dict[str, str]:
    """Load all files from an application pack directory."""
    files: Dict[str, str] = {}
    for p in app_dir.iterdir():
        if p.is_file():
            files[p.name] = p.read_text(encoding="utf-8")
    return files


def prepare_submission(
    job_id: str,
    platform: str,
    state_dir: str,
) -> SubmitResult:
    """Prepare application data for submission (dry-run mode).

    Loads pack files from ``<state_dir>/applications/<job_id>/`` and maps
    them to platform form fields.  Returns a :class:`SubmitResult` with
    ``dry_run=True`` and the fields that would be filled.

    Does NOT open a browser or submit anything.

    Raises
    ------
    FileNotFoundError
        If the application pack directory does not exist.
    ValueError
        If the platform is unknown.
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


def _connect_browser(
    cdp_port: Optional[int],
    headless: bool,
):
    """Return ``(pw, browser, context, page)`` via CDP or standalone launch.

    Delegates to :func:`jobos.browser.get_browser` which tries CDP first
    and falls back to standalone with persistent user data.
    """
    from .browser import get_browser

    return get_browser(cdp_port=cdp_port, headless=headless)


def submit_application(
    job_id: str,
    platform: str,
    state_dir: str,
    dry_run: bool = True,
    confirm: bool = False,
    cdp_port: Optional[int] = 9222,
    headless: bool = False,
) -> SubmitResult:
    """Submit application to *platform*.

    Parameters
    ----------
    job_id:
        The job identifier.
    platform:
        Target platform (e.g. ``"boss"``).
    state_dir:
        Path to the project root / state directory.
    dry_run:
        If True (default), only prepare, navigate, and screenshot.
    confirm:
        If True AND ``dry_run=False``, fill form fields on the real page.
    cdp_port:
        Chrome debug port to connect to via CDP.  When ``None`` a standalone
        headless Chromium is launched instead.
    headless:
        Only used when launching standalone (ignored with CDP).

    Returns
    -------
    SubmitResult

    Raises
    ------
    FileNotFoundError
        If the application pack directory does not exist.
    ValueError
        If the platform is unknown or if ``dry_run=False`` without ``confirm=True``.
    """
    # Always prepare first (validates pack exists and platform is known)
    result = prepare_submission(job_id, platform, state_dir)

    if dry_run:
        # Navigate and screenshot even in dry-run
        pw, browser, context, page = None, None, None, None
        try:
            pw, browser, context, page = _connect_browser(cdp_port, headless)
            page.goto("https://www.zhipin.com", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)  # wait for SPA to fully render
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

    # Non-dry-run requires explicit confirmation
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

    # Confirmed live submission: fill form fields
    pw, browser, context, page = None, None, None, None
    try:
        pw, browser, context, page = _connect_browser(cdp_port, headless)
        page.goto("https://www.zhipin.com", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)  # wait for SPA to fully render

        # Fill each mapped field on the page
        # BOSS Zhipin uses input/textarea elements; selectors are best-effort
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
                    # Field may not exist on this particular page; skip
                    pass
            else:
                fields_actually_filled[field_name] = content

        screenshot_dir = Path(state_dir) / "applications" / job_id
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(screenshot_dir / "submit_screenshot.png")
        page.screenshot(path=screenshot_path)

        # NOTE: The actual submit button click is intentionally commented out.
        # Uncomment and verify selectors before enabling real submission.
        # page.click('button[type="submit"], .submit-btn, .btn-submit')

        return SubmitResult(
            job_id=job_id,
            platform=platform,
            dry_run=False,
            fields_filled=fields_actually_filled,
            screenshot_path=screenshot_path,
            submitted=False,  # Not actually submitted until click is enabled
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
