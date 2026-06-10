"""Markdown report generator for the Job Application OS.

Reads .job-state.json, retro files, and prediction files to produce a
comprehensive report on pipeline health, outcomes, scoring patterns,
and skill gaps.

Usage::

    from jobos.report import generate_report
    md = generate_report("/path/to/project")
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Pipeline stages in order
STAGES = ["imported", "scored", "predicted", "packed", "submitted"]


# ---------------------------------------------------------------------------
# State / file loading
# ---------------------------------------------------------------------------

def _load_state(state_dir: Path) -> Dict[str, Any]:
    path = state_dir / ".job-state.json"
    if not path.exists():
        return {"jobs": {}, "active_rubric": "unknown", "rubric_history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_retros(state_dir: Path) -> List[Dict[str, Any]]:
    retro_dir = state_dir / "retros"
    if not retro_dir.is_dir():
        return []
    retros: List[Dict[str, Any]] = []
    for p in retro_dir.glob("*.json"):
        try:
            retros.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return retros


def _load_predictions(state_dir: Path) -> List[Dict[str, Any]]:
    pred_dir = state_dir / "predictions"
    if not pred_dir.is_dir():
        return []
    preds: List[Dict[str, Any]] = []
    for p in sorted(pred_dir.glob("*.json")):
        try:
            preds.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return preds


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _count_by_stage(jobs: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {s: 0 for s in STAGES}
    for job in jobs.values():
        stage = job.get("status", "imported")
        if stage in counts:
            counts[stage] += 1
    return counts


def _retro_outcome_counts(retros: List[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate outcome flags across all retro records."""
    counts = {
        "reply": 0,
        "interview": 0,
        "offer": 0,
        "rejection": 0,
        "ghosted": 0,
    }
    for retro in retros:
        # Check boolean flags first
        if retro.get("interview_received"):
            counts["interview"] += 1
        if retro.get("offer_received"):
            counts["offer"] += 1
        if retro.get("rejection_received"):
            counts["rejection"] += 1
        if retro.get("ghosted"):
            counts["ghosted"] += 1
        # Any non-None status window counts as a reply
        for key in ("status_3d", "status_14d", "status_30d"):
            if retro.get(key) is not None:
                counts["reply"] += 1
                break
    return counts


def _top_scoring_job_types(
    jobs: Dict[str, Any],
    limit: int = 5,
) -> List[tuple[str, float, int]]:
    """Group jobs by company, compute average final_score, return top N.

    Returns list of (label, avg_score, count) tuples sorted by avg_score desc.
    """
    by_company: Dict[str, List[float]] = {}
    for job in jobs.values():
        scores = job.get("scores", {})
        final = scores.get("final_score")
        if final is None:
            continue
        company = job.get("company", "Unknown")
        by_company.setdefault(company, []).append(float(final))

    ranked = sorted(
        by_company.items(),
        key=lambda kv: sum(kv[1]) / len(kv[1]),
        reverse=True,
    )
    return [
        (company, round(sum(scores) / len(scores), 2), len(scores))
        for company, scores in ranked[:limit]
    ]


def _most_common_missing_skills(
    jobs: Dict[str, Any],
    limit: int = 10,
) -> List[tuple[str, int]]:
    """Extract skills mentioned in score penalties across all jobs.

    Penalty keys in scores.penalties that relate to skills are stored as
    dimension penalties. We also scan the penalty reason strings for skill
    names. Since the scorer records penalties as dimension overrides
    (e.g. {"evidence": 2.0}), we look at jobs with evidence penalties and
    cross-reference with the job's required skills that aren't in the
    candidate profile.

    Fallback: scan prediction reason strings for skill-gap keywords.
    """
    skill_counter: Counter[str] = Counter()

    for job in jobs.values():
        scores = job.get("scores", {})
        penalties = scores.get("penalties", {})
        # If evidence was penalized, the missing skills are likely the
        # job's required skills minus the candidate's known skills.
        # We approximate by counting skill mentions in the job's
        # skills_required that triggered the penalty.
        if penalties.get("evidence", 0) > 0:
            required = job.get("skills_required", [])
            if isinstance(required, list):
                for skill in required:
                    if isinstance(skill, str):
                        skill_counter[skill] += 1

        # Also check prediction reasons for missing-skill signals
        reasons = job.get("prediction_reasons", [])
        if isinstance(reasons, list):
            for reason in reasons:
                if isinstance(reason, str) and "skill" in reason.lower():
                    # Try to extract skill name from reason text
                    # e.g. "Missing required skill: Python"
                    parts = reason.split(":")
                    if len(parts) > 1:
                        skill_counter[parts[-1].strip()] += 1

    return skill_counter.most_common(limit)


def _pending_retro_queue(
    jobs: Dict[str, Any],
) -> List[Dict[str, str]]:
    """List submitted jobs with incomplete retro tracking."""
    pending: List[Dict[str, str]] = []
    for job_id, job in jobs.items():
        if job.get("status") != "submitted":
            continue
        retro = job.get("retro", {})
        if not retro:
            continue
        if retro.get("complete"):
            continue
        due: List[str] = []
        for window, key in [("3d", "status_3d"), ("14d", "status_14d"), ("30d", "status_30d")]:
            if retro.get(key) is None:
                due.append(window)
        if due:
            pending.append({
                "job_id": job_id,
                "company": job.get("company", "?"),
                "title": job.get("title", "?"),
                "pending_windows": ", ".join(due),
            })
    return pending


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_table(headers: List[str], rows: List[List[str]]) -> str:
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def _fmt(cells: List[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, col_widths)) + " |"

    sep = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"
    lines = [_fmt(headers), sep]
    for row in rows:
        lines.append(_fmt(row))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(state_dir: str | Path) -> str:
    """Generate a markdown report summarizing the job application pipeline.

    Reads .job-state.json, retros/, and predictions/ to produce a report
    covering pipeline counts, retro outcomes, top-scoring companies,
    missing skill gaps, rubric version, and the pending retro queue.

    Args:
        state_dir: Path to the project root containing .job-state.json.

    Returns:
        The generated markdown string. Also writes it to
        ``reports/report.md`` inside state_dir.
    """
    state_dir = Path(state_dir)
    state = _load_state(state_dir)
    jobs = state.get("jobs", {})
    retros = _load_retros(state_dir)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    active_rubric = state.get("active_rubric", "unknown")

    lines: List[str] = []
    lines.append("# Job Application OS Report")
    lines.append("")
    lines.append(f"> Generated: {now}")
    lines.append("")

    # -- Pipeline counts -------------------------------------------------------
    lines.append("## Pipeline Overview")
    lines.append("")
    by_stage = _count_by_stage(jobs)
    rows = [[s.capitalize(), str(by_stage[s])] for s in STAGES]
    rows.append(["**Total**", f"**{len(jobs)}**"])
    lines.append(_render_table(["Stage", "Count"], rows))
    lines.append("")

    # -- Retro outcomes --------------------------------------------------------
    lines.append("## Outcome Summary")
    lines.append("")
    if retros:
        outcomes = _retro_outcome_counts(retros)
        rows = [
            ["Replies", str(outcomes["reply"])],
            ["Interviews", str(outcomes["interview"])],
            ["Offers", str(outcomes["offer"])],
            ["Rejections", str(outcomes["rejection"])],
            ["Ghosted", str(outcomes["ghosted"])],
            ["**Retros recorded**", f"**{len(retros)}**"],
        ]
        lines.append(_render_table(["Metric", "Count"], rows))
    else:
        lines.append("_No retro data recorded yet._")
    lines.append("")

    # -- Top scoring companies -------------------------------------------------
    lines.append("## Top Scoring Companies")
    lines.append("")
    top = _top_scoring_job_types(jobs)
    if top:
        rows = [[name, f"{avg:.2f}", str(cnt)] for name, avg, cnt in top]
        lines.append(_render_table(["Company", "Avg Score", "Jobs"], rows))
    else:
        lines.append("_No scored jobs yet._")
    lines.append("")

    # -- Missing skills --------------------------------------------------------
    lines.append("## Most Common Missing Skills")
    lines.append("")
    missing = _most_common_missing_skills(jobs)
    if missing:
        rows = [[skill, str(cnt)] for skill, cnt in missing]
        lines.append(_render_table(["Skill", "Penalty Count"], rows))
    else:
        lines.append("_No skill gaps detected._")
    lines.append("")

    # -- Active rubric ---------------------------------------------------------
    lines.append("## Rubric")
    lines.append("")
    lines.append(f"- **Active version:** `{active_rubric}`")
    history = state.get("rubric_history", [])
    if history:
        lines.append(f"- **History:** {len(history)} prior version(s)")
        for entry in history[-3:]:
            frm = entry.get("from", "?")
            to = entry.get("to", "?")
            ts = entry.get("changed_at", "?")
            lines.append(f"  - `{frm}` -> `{to}` ({ts})")
    lines.append("")

    # -- Pending retro queue ---------------------------------------------------
    lines.append("## Pending Retro Queue")
    lines.append("")
    pending = _pending_retro_queue(jobs)
    if pending:
        rows = [
            [p["job_id"], p["company"], p["title"], p["pending_windows"]]
            for p in pending
        ]
        lines.append(_render_table(
            ["Job ID", "Company", "Role", "Pending Windows"], rows,
        ))
    else:
        lines.append("_All retros complete or no submitted jobs._")
    lines.append("")

    md = "\n".join(lines)

    # Write to reports/report.md
    reports_dir = state_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "report.md").write_text(md, encoding="utf-8")

    return md
