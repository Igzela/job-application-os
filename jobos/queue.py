"""Pipeline queue -- shows what needs doing next.

Reads .job-state.json and returns jobs grouped by the action they are waiting on.
Each bucket is a list of {job_id, title, company, status} dicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


_STATE_FILENAME = ".job-state.json"


def _load_state(state_dir: Path) -> Dict[str, Any]:
    path = state_dir / _STATE_FILENAME
    if not path.exists():
        return {"jobs": {}, "active_rubric": "unknown", "rubric_history": [], "opportunities": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _entry(job_id: str, job: Dict[str, Any]) -> Dict[str, str]:
    return {
        "job_id": job_id,
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "status": job.get("status", "imported"),
    }


def get_queue(state_dir: str | Path) -> Dict[str, List[Dict[str, str]]]:
    """Return the pipeline queue grouped by action bucket.

    Buckets:
        unscored      -- status == "imported"
        unpredicted   -- status == "scored"
        unpacked      -- status == "predicted"
        unsubmitted   -- status == "packed"
        waiting_3d    -- status == "submitted" and retro.status_3d is None
        waiting_14d   -- status == "submitted" and retro.status_14d is None
        waiting_30d   -- status == "submitted" and retro.status_30d is None

    Args:
        state_dir: Root directory containing .job-state.json.

    Returns:
        Dict mapping bucket name to a list of {job_id, title, company, status}.
    """
    state_dir = Path(state_dir)
    state = _load_state(state_dir)

    buckets: Dict[str, List[Dict[str, str]]] = {
        "unscored": [],
        "unpredicted": [],
        "unpacked": [],
        "unsubmitted": [],
        "waiting_3d": [],
        "waiting_14d": [],
        "waiting_30d": [],
        "opp_candidate": [],
        "opp_verifying": [],
        "opp_planning": [],
    }

    for job_id, job in state.get("jobs", {}).items():
        status = job.get("status", "imported")

        if status == "imported":
            buckets["unscored"].append(_entry(job_id, job))
        elif status == "scored":
            buckets["unpredicted"].append(_entry(job_id, job))
        elif status == "predicted":
            buckets["unpacked"].append(_entry(job_id, job))
        elif status == "packed":
            buckets["unsubmitted"].append(_entry(job_id, job))
        elif status == "submitted":
            retro = job.get("retro") or {}
            if retro.get("status_3d") is None:
                buckets["waiting_3d"].append(_entry(job_id, job))
            if retro.get("status_14d") is None:
                buckets["waiting_14d"].append(_entry(job_id, job))
            if retro.get("status_30d") is None:
                buckets["waiting_30d"].append(_entry(job_id, job))

    for opp in state.get("opportunities", []):
        opp_status = opp.get("status", "candidate")
        opp_entry = {
            "job_id": opp.get("id", opp.get("name", "?")),
            "title": opp.get("name", ""),
            "company": opp.get("category", ""),
            "status": opp_status,
        }
        if opp_status == "candidate":
            buckets["opp_candidate"].append(opp_entry)
        elif opp_status == "verifying":
            buckets["opp_verifying"].append(opp_entry)
        elif opp_status == "planning":
            buckets["opp_planning"].append(opp_entry)

    return buckets
