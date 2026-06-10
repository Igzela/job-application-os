"""Rubric lifecycle manager for the Job Application OS.

Handles loading, versioning, bumping, and activating rubrics. The bump
process creates a candidate rubric, re-scores all historical jobs that
have retro data, and produces a comparison report -- without silently
replacing the active rubric.

Rubric files live in a ``rubrics/`` directory as Markdown documents.
State (active rubric name, history) is tracked in a JSON state file.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

_DEFAULT_STATE: dict[str, Any] = {
    "active_rubric": None,
    "rubric_history": [],
}


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return dict(_DEFAULT_STATE)
    return json.loads(state_path.read_text(encoding="utf-8"))


def _save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Rubric loading
# ---------------------------------------------------------------------------

def load_rubric(rubric_path: str | Path) -> dict[str, Any]:
    """Load a rubric Markdown file and return a structured dict.

    The returned dict contains:
        - ``name``: stem of the file (e.g. ``v0_student_internship``)
        - ``path``: absolute path to the source file
        - ``content``: full raw Markdown text
        - ``weights``: extracted weight mapping if parseable, else empty dict
        - ``loaded_at``: ISO-8601 timestamp

    Args:
        rubric_path: Path to a rubric Markdown file.

    Returns:
        Structured rubric dict.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    rubric_path = Path(rubric_path).resolve()
    if not rubric_path.is_file():
        raise FileNotFoundError(f"Rubric file not found: {rubric_path}")

    content = rubric_path.read_text(encoding="utf-8")
    weights = _extract_weights(content)

    return {
        "name": rubric_path.stem,
        "path": str(rubric_path),
        "content": content,
        "weights": weights,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_weights(content: str) -> dict[str, float]:
    """Best-effort extraction of dimension weights from rubric Markdown.

    Looks for patterns like ``weight: 30%`` or ``(weight: 20%)`` in the
    content and maps dimension headings to their weights.
    """
    import re

    weights: dict[str, float] = {}
    # Match patterns like "### 1. Skill Match (weight: 30%)" or inline "weight: 30%"
    pattern = re.compile(
        r"#+\s*\d*\.?\s*(.+?)\s*\(?\s*weight:\s*(\d+(?:\.\d+)?)\s*%\s*\)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(content):
        dimension = re.sub(r"[^a-z0-9]+", "_", match.group(1).strip().lower()).strip("_")
        weight = float(match.group(2)) / 100.0
        weights[dimension] = weight

    return weights


# ---------------------------------------------------------------------------
# Active rubric get/set
# ---------------------------------------------------------------------------

def get_active_rubric(state_path: str | Path) -> str | None:
    """Return the name of the currently active rubric, or None.

    Args:
        state_path: Path to the JSON state file (e.g. ``.job-state.json``).

    Returns:
        Rubric name string or None if no rubric is active.
    """
    state = _load_state(Path(state_path))
    return state.get("active_rubric")


def set_active_rubric(state_path: str | Path, rubric_name: str) -> None:
    """Activate a rubric by name and record the transition in history.

    Args:
        state_path: Path to the JSON state file.
        rubric_name: Name (stem) of the rubric to activate. Must correspond
            to a file in the rubrics directory.

    Raises:
        FileNotFoundError: if no rubric file matching ``rubric_name`` exists
            in the rubrics directory adjacent to the state file.
    """
    state_path = Path(state_path).resolve()
    rubric_file = _resolve_rubric_file(state_path, rubric_name)

    if not rubric_file.is_file():
        raise FileNotFoundError(
            f"No rubric file found for name {rubric_name!r} at {rubric_file}"
        )

    state = _load_state(state_path)
    previous = state.get("active_rubric")

    state["active_rubric"] = rubric_name
    state.setdefault("rubric_history", []).append({
        "from": previous,
        "to": rubric_name,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    })

    _save_state(state_path, state)


def _resolve_rubric_file(state_path: Path, rubric_name: str) -> Path:
    """Resolve the rubric file path from a name and state file location.

    Assumes rubrics live in a ``rubrics/`` directory at the project root
    (parent of the state file's directory if the state file is at the root,
    or the state file's directory itself).
    """
    # Try rubrics/ next to the state file first
    candidate = state_path.parent / "rubrics" / f"{rubric_name}.md"
    if candidate.is_file():
        return candidate
    # Try rubrics/ one level up (state file inside a subdirectory)
    candidate = state_path.parent.parent / "rubrics" / f"{rubric_name}.md"
    return candidate


# ---------------------------------------------------------------------------
# Rubric bump (candidate creation + comparison)
# ---------------------------------------------------------------------------

def bump_rubric(
    new_rubric_path: str | Path,
    jobs_dir: str | Path,
    predictions_dir: str | Path,
    retros_dir: str | Path,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a rubric candidate and compare it against the active rubric.

    This function:
      1. Loads the new rubric candidate.
      2. Loads the currently active rubric (if any).
      3. Re-scores every historical job that has retro data using BOTH rubrics.
      4. Produces a comparison report showing ranking changes.
      5. Saves the candidate to the rubrics directory.
      6. Does NOT activate the new rubric -- the caller must explicitly
         call ``set_active_rubric`` after reviewing the report.

    Args:
        new_rubric_path: Path to the new rubric candidate Markdown file.
        jobs_dir: Directory containing job JSON files.
        predictions_dir: Directory containing prediction JSON files.
        retros_dir: Directory containing retro JSON files.
        state_path: Path to the state file. If None, inferred from the
            project structure (looks for ``.job-state.json``).

    Returns:
        A comparison report dict with keys:
            - ``candidate``: info about the new rubric
            - ``active_rubric``: name of the current active rubric (or None)
            - ``jobs_scored``: number of jobs re-scored
            - ``ranking_old``: old ranking (list of job_id, score pairs)
            - ``ranking_new``: new ranking (list of job_id, score pairs)
            - ``movements``: list of per-job rank change details
            - ``summary``: human-readable summary text

    Raises:
        FileNotFoundError: if the new rubric file does not exist.
    """
    new_rubric_path = Path(new_rubric_path).resolve()
    jobs_dir = Path(jobs_dir).resolve()
    predictions_dir = Path(predictions_dir).resolve()
    retros_dir = Path(retros_dir).resolve()

    if state_path is None:
        state_path = _infer_state_path(new_rubric_path)
    state_path = Path(state_path).resolve()

    # Load candidate
    candidate = load_rubric(new_rubric_path)

    # Load active rubric (may be None)
    state = _load_state(state_path)
    active_name = state.get("active_rubric")
    active_rubric: dict[str, Any] | None = None
    if active_name:
        active_file = _resolve_rubric_file(state_path, active_name)
        if active_file.is_file():
            active_rubric = load_rubric(active_file)

    # Save candidate to rubrics directory (does NOT activate it)
    rubrics_dir = _resolve_rubric_file(state_path, "placeholder").parent
    rubrics_dir.mkdir(parents=True, exist_ok=True)
    candidate_dest = rubrics_dir / new_rubric_path.name
    if not candidate_dest.exists():
        shutil.copy2(new_rubric_path, candidate_dest)
        candidate["path"] = str(candidate_dest)

    # Gather historical jobs with retro data
    scored_jobs = _gather_scored_jobs(jobs_dir, predictions_dir, retros_dir)

    if not scored_jobs:
        return {
            "candidate": candidate,
            "active_rubric": active_name,
            "jobs_scored": 0,
            "ranking_old": [],
            "ranking_new": [],
            "movements": [],
            "summary": "No historical jobs with retro data found. Nothing to compare.",
        }

    # Score all jobs with both rubrics
    from jobos.scorer import score_job
    from jobos.profile_loader import load_profile, load_evidence_bank

    # Infer project root from jobs_dir
    project_root = jobs_dir.parent if jobs_dir.name in ("jobs", "data") else jobs_dir
    profile = load_profile(project_root)
    evidence = load_evidence_bank(project_root)

    old_scores: list[tuple[str, float]] = []
    new_scores: list[tuple[str, float]] = []

    for job_data in scored_jobs:
        job_id = job_data["job_id"]

        # Score with active rubric (or zeros if none)
        if active_rubric:
            old_result = score_job(job_data, profile, evidence, active_rubric)
            old_final = old_result["final_score"]
        else:
            old_final = 0.0

        # Score with candidate rubric
        new_result = score_job(job_data, profile, evidence, candidate)
        new_final = new_result["final_score"]

        old_scores.append((job_id, old_final))
        new_scores.append((job_id, new_final))

    # Sort descending by score
    old_ranking = sorted(old_scores, key=lambda x: x[1], reverse=True)
    new_ranking = sorted(new_scores, key=lambda x: x[1], reverse=True)

    # Compute movements
    old_rank_map = {jid: rank for rank, (jid, _) in enumerate(old_ranking)}
    new_rank_map = {jid: rank for rank, (jid, _) in enumerate(new_ranking)}

    movements = []
    for job_id in set(old_rank_map) | set(new_rank_map):
        old_rank = old_rank_map.get(job_id)
        new_rank = new_rank_map.get(job_id)
        old_score = next(s for j, s in old_ranking if j == job_id) if old_rank is not None else None
        new_score = next(s for j, s in new_ranking if j == job_id) if new_rank is not None else None

        delta = None
        if old_rank is not None and new_rank is not None:
            delta = old_rank - new_rank  # positive = moved up

        movements.append({
            "job_id": job_id,
            "old_rank": old_rank,
            "new_rank": new_rank,
            "old_score": old_score,
            "new_score": new_score,
            "rank_change": delta,
            "score_change": round(new_score - old_score, 2) if old_score is not None and new_score is not None else None,
        })

    movements.sort(key=lambda m: m.get("rank_change") or 0, reverse=True)

    summary = _build_summary(candidate, active_name, movements, old_ranking, new_ranking)

    return {
        "candidate": candidate,
        "active_rubric": active_name,
        "jobs_scored": len(scored_jobs),
        "ranking_old": old_ranking,
        "ranking_new": new_ranking,
        "movements": movements,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Internal helpers for bump
# ---------------------------------------------------------------------------

def _infer_state_path(rubric_path: Path) -> Path:
    """Try to find .job-state.json relative to the rubric file."""
    # Walk up from rubric path looking for .job-state.json
    current = rubric_path.parent
    for _ in range(5):
        candidate = current / ".job-state.json"
        if candidate.exists():
            return candidate
        current = current.parent
    # Default: assume project root is parent of rubrics/
    return rubric_path.parent.parent / ".job-state.json"


def _gather_scored_jobs(
    jobs_dir: Path,
    predictions_dir: Path,
    retros_dir: Path,
) -> list[dict[str, Any]]:
    """Load all jobs that have both a prediction and a retro entry."""
    if not retros_dir.is_dir():
        return []

    retro_job_ids = set()
    for retro_file in retros_dir.glob("*.json"):
        try:
            retro_data = json.loads(retro_file.read_text(encoding="utf-8"))
            retro_job_ids.add(retro_data.get("job_id", retro_file.stem))
        except (json.JSONDecodeError, KeyError):
            continue

    if not retro_job_ids:
        return []

    jobs: list[dict[str, Any]] = []
    if not jobs_dir.is_dir():
        return []

    for job_file in jobs_dir.glob("*.json"):
        try:
            job_data = json.loads(job_file.read_text(encoding="utf-8"))
            job_id = job_data.get("job_id", job_file.stem)
            if job_id in retro_job_ids:
                jobs.append(job_data)
        except (json.JSONDecodeError, KeyError):
            continue

    return jobs


def _build_summary(
    candidate: dict[str, Any],
    active_name: str | None,
    movements: list[dict[str, Any]],
    old_ranking: list[tuple[str, float]],
    new_ranking: list[tuple[str, float]],
) -> str:
    """Build a human-readable comparison summary."""
    lines: list[str] = []
    lines.append(f"Rubric bump comparison: {candidate['name']}")
    lines.append(f"  vs active: {active_name or '(none)'}")
    lines.append(f"  jobs compared: {len(movements)}")
    lines.append("")

    # Top movers
    promoted = [m for m in movements if (m.get("rank_change") or 0) > 0]
    demoted = [m for m in movements if (m.get("rank_change") or 0) < 0]

    if promoted:
        lines.append(f"Promoted ({len(promoted)} jobs moved up):")
        for m in promoted[:5]:
            lines.append(
                f"  {m['job_id']}: rank {m['old_rank']} -> {m['new_rank']} "
                f"(score {m['old_score']:.1f} -> {m['new_score']:.1f}, "
                f"+{m['rank_change']} positions)"
            )
        if len(promoted) > 5:
            lines.append(f"  ... and {len(promoted) - 5} more")
        lines.append("")

    if demoted:
        lines.append(f"Demoted ({len(demoted)} jobs moved down):")
        for m in demoted[-5:]:
            lines.append(
                f"  {m['job_id']}: rank {m['old_rank']} -> {m['new_rank']} "
                f"(score {m['old_score']:.1f} -> {m['new_score']:.1f}, "
                f"{m['rank_change']} positions)"
            )
        if len(demoted) > 5:
            lines.append(f"  ... and {len(demoted) - 5} more")
        lines.append("")

    # Top-3 comparison
    lines.append("Top 3 old ranking:")
    for rank, (jid, score) in enumerate(old_ranking[:3], 1):
        lines.append(f"  {rank}. {jid} ({score:.1f})")
    lines.append("")
    lines.append("Top 3 new ranking:")
    for rank, (jid, score) in enumerate(new_ranking[:3], 1):
        lines.append(f"  {rank}. {jid} ({score:.1f})")
    lines.append("")
    lines.append(
        "NOTE: The new rubric has been saved as a candidate but is NOT active. "
        "Review this report, then call set_active_rubric() to promote it."
    )

    return "\n".join(lines)
