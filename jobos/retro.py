"""Retro tracking for the Job Application OS.

Stage 6 of the pipeline: record submissions, collect outcome data at 3/14/30-day
marks, and identify jobs that still need retro updates.

State lives in two places:
- .job-state.json  — per-job submission metadata (date, channel, retro status)
- retros/{job_id}.json — individual retro outcome files
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workspace import load_state, retros_dir, save_state

# -- State file helpers -------------------------------------------------------

# Retro check windows (days after submission)
_WINDOW_3D = 3
_WINDOW_14D = 14
_WINDOW_30D = 30


def _load_state(state_dir: Path) -> Dict[str, Any]:
    return load_state(state_dir)


def _save_state(state_dir: Path, state: Dict[str, Any]) -> None:
    save_state(state_dir, state)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retros_dir(state_dir: Path) -> Path:
    return retros_dir(state_dir)


# -- Public API ---------------------------------------------------------------

def record_submission(
    job_id: str,
    channel: str,
    state_dir: str | Path,
) -> Dict[str, Any]:
    """Record that a job application was submitted.

    Updates .job-state.json with submission metadata and initializes retro
    tracking for the job.

    Args:
        job_id: Unique identifier for the job application.
        channel: Submission channel (e.g. "greenhouse", "lever", "email",
            "referral", "linkedin", "workday").
        state_dir: Root directory containing .job-state.json.

    Returns:
        The updated job entry dict from the state file.

    Raises:
        KeyError: if the job_id does not exist in .job-state.json jobs.
    """
    from .pipeline import record_external_submission

    state_dir = Path(state_dir)
    state = _load_state(state_dir)

    if job_id not in state["jobs"]:
        raise KeyError(
            f"job_id={job_id!r} not found in state. "
            f"Import and score the job before recording submission."
        )

    now = _now_iso()
    job = state["jobs"][job_id]
    record_external_submission(job)
    job["submitted_at"] = now
    job["submission_channel"] = channel
    job["retro"] = {
        "submitted_at": now,
        "check_3d_due": (datetime.now(timezone.utc) + timedelta(days=_WINDOW_3D)).isoformat(),
        "check_14d_due": (datetime.now(timezone.utc) + timedelta(days=_WINDOW_14D)).isoformat(),
        "check_30d_due": (datetime.now(timezone.utc) + timedelta(days=_WINDOW_30D)).isoformat(),
        "status_3d": None,
        "status_14d": None,
        "status_30d": None,
        "complete": False,
    }

    _save_state(state_dir, state)
    return job


def record_retro(
    job_id: str,
    state_dir: str | Path,
    status_3d: Optional[str] = None,
    status_14d: Optional[str] = None,
    status_30d: Optional[str] = None,
) -> Path:
    """Record retro outcome data for a submitted application.

    Creates or updates a retro file in retros/{job_id}.json and marks the
    corresponding check windows as filled in .job-state.json.

    Args:
        job_id: Unique identifier for the job application.
        state_dir: Root directory containing .job-state.json and retros/.
        status_3d: Outcome at the 3-day mark (e.g. "auto_reject", "ack_received",
            "oa_sent", None if no update yet).
        status_14d: Outcome at the 14-day mark (e.g. "phone_screen",
            "interview_scheduled", "ghosted", None).
        status_30d: Outcome at the 30-day mark (e.g. "offer", "rejected",
            "ghosted", "withdrawn", None).

    Returns:
        Path to the retro file.

    Raises:
        KeyError: if the job_id does not exist in state or has no submission.
    """
    state_dir = Path(state_dir)
    state = _load_state(state_dir)

    if job_id not in state["jobs"]:
        raise KeyError(f"job_id={job_id!r} not found in state.")

    job = state["jobs"][job_id]
    retro_meta = job.get("retro")
    if not retro_meta:
        raise KeyError(
            f"job_id={job_id!r} has no submission recorded. "
            f"Call record_submission() first."
        )

    # Update state-side retro tracking
    if status_3d is not None:
        retro_meta["status_3d"] = status_3d
    if status_14d is not None:
        retro_meta["status_14d"] = status_14d
    if status_30d is not None:
        retro_meta["status_30d"] = status_30d

    # Mark complete if all three windows are filled
    if all([
        retro_meta.get("status_3d"),
        retro_meta.get("status_14d"),
        retro_meta.get("status_30d"),
    ]):
        from .pipeline import transition_job

        retro_meta["complete"] = True
        transition_job(job, "retro")

    _save_state(state_dir, state)

    # Write / update the retro file
    retro_dir = _retros_dir(state_dir)
    retro_dir.mkdir(parents=True, exist_ok=True)
    retro_path = retro_dir / f"{job_id}.json"

    # Load existing retro file or start fresh
    if retro_path.exists():
        retro_data = json.loads(retro_path.read_text(encoding="utf-8"))
    else:
        retro_data = {
            "job_id": job_id,
            "submitted_at": retro_meta.get("submitted_at"),
            "status_3d": None,
            "status_14d": None,
            "status_30d": None,
            "reply_time_hours": None,
            "interview_received": False,
            "offer_received": False,
            "rejection_received": False,
            "ghosted": False,
            "outcome_label": None,
            "prediction_error": None,
            "rubric_note_candidate": None,
            "created_at": _now_iso(),
        }

    if status_3d is not None:
        retro_data["status_3d"] = status_3d
    if status_14d is not None:
        retro_data["status_14d"] = status_14d
    if status_30d is not None:
        retro_data["status_30d"] = status_30d

    # Derive boolean flags from status strings
    all_statuses = [
        retro_data.get("status_3d"),
        retro_data.get("status_14d"),
        retro_data.get("status_30d"),
    ]
    flat = " ".join(s for s in all_statuses if s).lower()

    if any(kw in flat for kw in ("interview", "phone_screen", "onsite", "oa")):
        retro_data["interview_received"] = True
    if "offer" in flat:
        retro_data["offer_received"] = True
    if "reject" in flat or "rejected" in flat:
        retro_data["rejection_received"] = True
    if "ghost" in flat:
        retro_data["ghosted"] = True

    # Set outcome_label from the latest non-None status
    for status in reversed(all_statuses):
        if status is not None:
            retro_data["outcome_label"] = status
            break

    retro_data["updated_at"] = _now_iso()

    retro_path.write_text(json.dumps(retro_data, indent=2, ensure_ascii=False) + "\n")
    return retro_path


def record_freeform_retro(
    job_id: str,
    text: str,
    lessons: List[str],
    state_dir: str | Path,
) -> Path:
    """Record a freeform retrospective with extracted lessons.

    Writes to retros/<job_id>.json (appends to existing retro if present).
    Appends lessons to lessons.md in the state directory.

    Args:
        job_id: Unique identifier for the job application.
        text: Freeform retrospective text.
        lessons: List of lesson strings extracted from the retro.
        state_dir: Root directory containing retros/ and lessons.md.

    Returns:
        Path to the retro file.
    """
    state_dir = Path(state_dir)

    retro_dir = _retros_dir(state_dir)
    retro_dir.mkdir(parents=True, exist_ok=True)
    retro_path = retro_dir / f"{job_id}.json"

    # Load existing retro file or start fresh
    if retro_path.exists():
        retro_data = json.loads(retro_path.read_text(encoding="utf-8"))
    else:
        retro_data = {
            "job_id": job_id,
            "created_at": _now_iso(),
        }

    # Append freeform entry
    freeform_entries = retro_data.get("freeform_retros", [])
    freeform_entries.append({
        "text": text,
        "lessons": lessons,
        "recorded_at": _now_iso(),
    })
    retro_data["freeform_retros"] = freeform_entries
    retro_data["updated_at"] = _now_iso()

    retro_path.write_text(json.dumps(retro_data, indent=2, ensure_ascii=False) + "\n")

    # Append lessons to lessons.md
    lessons_path = state_dir / "lessons.md"
    existing = lessons_path.read_text(encoding="utf-8") if lessons_path.exists() else "# Lessons Learned\n\n"
    new_lines = []
    for lesson in lessons:
        new_lines.append(f"- {lesson}")
    if new_lines:
        existing += "\n".join(new_lines) + "\n"
    lessons_path.write_text(existing, encoding="utf-8")

    return retro_path


def get_pending_retros(state_dir: str | Path) -> List[Dict[str, Any]]:
    """List jobs that need retro updates.

    A job needs a retro update if:
    - It has been submitted (retro tracking initialized).
    - Its retro is not yet complete (not all 3 windows filled).
    - At least one check window is past due.

    Each entry includes the job_id, which windows are due, and the due dates.

    Args:
        state_dir: Root directory containing .job-state.json.

    Returns:
        List of dicts with keys: job_id, due_windows (list of "3d"/"14d"/"30d"),
        statuses (current values for each window).
    """
    state_dir = Path(state_dir)
    state = _load_state(state_dir)
    now = datetime.now(timezone.utc)

    pending: List[Dict[str, Any]] = []

    for job_id, job in state.get("jobs", {}).items():
        retro_meta = job.get("retro")
        if not retro_meta:
            continue
        if retro_meta.get("complete"):
            continue

        due_windows: List[str] = []
        statuses: Dict[str, Optional[str]] = {}

        for window, key_due, key_status in [
            ("3d", "check_3d_due", "status_3d"),
            ("14d", "check_14d_due", "status_14d"),
            ("30d", "check_30d_due", "status_30d"),
        ]:
            due_str = retro_meta.get(key_due)
            status = retro_meta.get(key_status)
            statuses[window] = status

            if status is not None:
                continue  # already recorded

            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str)
                    if now >= due_dt:
                        due_windows.append(window)
                except ValueError:
                    due_windows.append(window)

        if due_windows:
            pending.append({
                "job_id": job_id,
                "due_windows": due_windows,
                "statuses": statuses,
            })

    return pending
