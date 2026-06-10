"""Semi-automatic application submitter.

Framework for preparing and (eventually) submitting job applications.
By default operates in dry-run mode: loads pack files, maps them to
platform form fields, and returns what *would* be submitted.

Actual browser automation is NOT implemented.  Real submission would
require Playwright + platform-specific adapters.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# Platform field mappings
# ---------------------------------------------------------------------------

# boss platform: pack filename -> form field name
BOSS_FIELD_MAP: Dict[str, str] = {
    "greeting.md": "开场白/招呼语",
    "resume_targeted.md": "简历内容",
    "cover_letter.md": "求职信",
    "form_answers.md": "常见问题回答",
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


def submit_application(
    job_id: str,
    platform: str,
    state_dir: str,
    dry_run: bool = True,
    confirm: bool = False,
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
        If True (default), only prepare and return what would be submitted.
    confirm:
        If True AND ``dry_run=False``, proceed with real submission.
        Actual submission is NOT IMPLEMENTED and raises ``NotImplementedError``.

    Returns
    -------
    SubmitResult

    Raises
    ------
    FileNotFoundError
        If the application pack directory does not exist.
    ValueError
        If the platform is unknown or if ``dry_run=False`` without ``confirm=True``.
    NotImplementedError
        If ``dry_run=False`` and ``confirm=True`` (real submission not implemented).
    """
    # Always prepare first (validates pack exists and platform is known)
    result = prepare_submission(job_id, platform, state_dir)

    if dry_run:
        return result

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

    # Actual submission not implemented
    raise NotImplementedError(
        "Real platform submission is not implemented. "
        "This is a framework for data preparation. "
        "Actual submission would require Playwright + platform-specific adapters."
    )
