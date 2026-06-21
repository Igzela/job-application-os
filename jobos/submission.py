"""Shared submit attempt record helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .workspace import submit_attempts_dir


def utc_now() -> str:
    """Return current UTC timestamp as ISO-8601 text."""
    return datetime.now(timezone.utc).isoformat()


def classify_submit_error(error: str | None) -> str | None:
    """Return stable submit error class."""
    if not error:
        return None
    message = error.lower()
    if "url" in message:
        return "no_url"
    if "chat" in message:
        return "no_chat_button"
    if "fill" in message or "textarea" in message:
        return "fill_failed"
    if "send" in message:
        return "send_failed"
    if "browser" in message or "cdp" in message:
        return "browser_connect_failed"
    return "submit_failed"


def submit_attempt_path(
    state_dir: str | Path,
    job_id: str,
    *,
    stamp: str | None = None,
) -> Path:
    """Return canonical submit attempt path for ``job_id``."""
    if stamp is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return submit_attempts_dir(state_dir, job_id) / f"{stamp}.json"


def new_submit_attempt_record(
    *,
    job_id: str,
    url: str,
    platform: str,
    mode: str,
    started_at: str | None = None,
) -> dict[str, Any]:
    """Return canonical started submit attempt record."""
    return {
        "schema_version": 1,
        "job_id": job_id,
        "url": url,
        "platform": platform,
        "mode": mode,
        "started_at": started_at or utc_now(),
        "status": "started",
        "result": None,
        "error": None,
        "error_class": None,
        "screenshot_paths": [],
        "page_state": None,
        "extractor": None,
        "page_diagnostics": [],
        "recovery_signals": [],
    }


def submit_attempt_result_update(
    *,
    submitted: bool,
    submitted_at: str | None,
    fields_filled: Mapping[str, str],
    page_title: str | None,
    page_url: str | None,
    screenshot_path: str | None,
    error: str | None,
    finished_at: str | None = None,
    submit_phase: str | None = None,
    success_signals: Sequence[str] | None = None,
    screenshot_paths: Mapping[str, str | None] | Sequence[str] | None = None,
) -> dict[str, Any]:
    """Return canonical fields for finishing a submit attempt record."""
    result = {
        "submitted": submitted,
        "submitted_at": submitted_at,
        "fields_filled": dict(fields_filled),
        "page_title": page_title,
        "page_url": page_url,
        "screenshot_path": screenshot_path,
    }
    if submit_phase is not None:
        result["submit_phase"] = submit_phase
    if success_signals is not None:
        result["success_signals"] = list(success_signals)
    if screenshot_paths is not None:
        result["screenshot_paths"] = (
            {key: value for key, value in screenshot_paths.items() if value}
            if isinstance(screenshot_paths, Mapping)
            else [path for path in screenshot_paths if path]
        )

    top_screenshot_paths = [screenshot_path] if screenshot_path else []
    if screenshot_paths is not None:
        top_screenshot_paths = (
            [value for value in screenshot_paths.values() if value]
            if isinstance(screenshot_paths, Mapping)
            else [path for path in screenshot_paths if path]
        )

    return {
        "finished_at": finished_at or utc_now(),
        "status": "failed" if error else "succeeded",
        "result": result,
        "error": error,
        "error_class": classify_submit_error(error),
        "screenshot_paths": top_screenshot_paths,
    }


def write_submit_attempt(path: Path, record: Mapping[str, Any]) -> str:
    """Persist submit attempt record as deterministic JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(path)
