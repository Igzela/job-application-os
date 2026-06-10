"""Job recommender -- rank predicted jobs by composite quality signals.

Reads .job-state.json and predictions/*.json to produce a ranked shortlist
of the most promising applications.

Composite score weights:
    0.40 * final_score  (0-10, higher is better)
    0.25 * (10 - risk)  (low risk is better)
    0.20 * evidence      (high evidence is better)
    0.15 * availability_match (derived from status + hard-gate penalties)

Decision filtering: jobs with decision == "skip" are excluded unless
include_skipped=True.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


_STATE_FILENAME = ".job-state.json"
_PREDICTIONS_DIR = "predictions"


def _load_state(state_dir: Path) -> Dict[str, Any]:
    path = state_dir / _STATE_FILENAME
    if not path.exists():
        return {"jobs": {}, "active_rubric": "unknown", "rubric_history": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_latest_prediction(predictions_dir: Path, job_id: str) -> Optional[Dict[str, Any]]:
    """Load the highest-version prediction file for a job_id.

    Prediction files follow the pattern {job_id}_v{version}.json.
    Returns None if no prediction file exists.
    """
    if not predictions_dir.is_dir():
        return None

    candidates = sorted(
        predictions_dir.glob(f"{job_id}_v*.json"),
        key=lambda p: p.stem,
    )
    if not candidates:
        return None

    latest = candidates[-1]
    return json.loads(latest.read_text(encoding="utf-8"))


def _availability_match(prediction: Dict[str, Any]) -> float:
    """Derive an availability/fit proxy (0-10) from prediction signals.

    Uses the inverse of friction and a penalty for low fit.  This captures
    how well the candidate's availability and logistics align with the role.
    """
    # Pull dimension_scores if present (predictor.py format)
    dim = prediction.get("dimension_scores", {})
    friction = dim.get("friction", 5.0)
    fit = dim.get("fit", dim.get("skill_match", 5.0))

    # Low friction + high fit = good availability match
    match = (10.0 - friction) * 0.5 + fit * 0.5
    return max(0.0, min(10.0, match))


def _build_reason(
    final_score: float,
    risk: float,
    evidence: float,
    avail: float,
    decision: str,
    expected_best: str,
) -> str:
    """Build a human-readable recommendation reason string."""
    parts: List[str] = []

    if final_score >= 7.0:
        parts.append(f"strong overall fit ({final_score:.1f}/10)")
    elif final_score >= 5.0:
        parts.append(f"moderate fit ({final_score:.1f}/10)")

    if risk <= 3.0:
        parts.append("low risk")
    elif risk >= 7.0:
        parts.append("high risk")

    if evidence >= 7.0:
        parts.append("strong evidence alignment")
    elif evidence <= 3.0:
        parts.append("weak evidence")

    if avail >= 7.0:
        parts.append("good availability match")

    if expected_best:
        parts.append(expected_best)

    return "; ".join(parts) if parts else decision


def recommend_jobs(
    state_dir: str | Path,
    top_n: int = 5,
    include_skipped: bool = False,
) -> List[Dict[str, Any]]:
    """Return the top N jobs ranked by composite quality.

    Composite = 0.40*final_score + 0.25*(10-risk) + 0.20*evidence + 0.15*availability_match

    Args:
        state_dir: Root directory containing .job-state.json and predictions/.
        top_n: Number of top jobs to return.
        include_skipped: If False, exclude jobs where decision == "skip".

    Returns:
        List of dicts, each containing:
            job_id, title, company, final_score, risk, evidence,
            recommendation_reason
    """
    state_dir = Path(state_dir)
    state = _load_state(state_dir)
    predictions_dir = state_dir / _PREDICTIONS_DIR

    scored: List[Dict[str, Any]] = []

    for job_id, job in state.get("jobs", {}).items():
        status = job.get("status", "imported")
        # Only consider jobs that have been predicted (or later stages)
        if status not in ("predicted", "packed", "submitted"):
            continue

        pred = _load_latest_prediction(predictions_dir, job_id)
        if pred is None:
            continue

        decision = pred.get("decision", "skip")
        if decision == "skip" and not include_skipped:
            continue

        final_score = float(pred.get("final_score", 0.0))
        risk = float(pred.get("risk", pred.get("dimension_scores", {}).get("risk", 5.0)))
        evidence = float(pred.get("evidence", pred.get("dimension_scores", {}).get("evidence", 5.0)))
        avail = _availability_match(pred)

        composite = (
            0.40 * final_score
            + 0.25 * (10.0 - risk)
            + 0.20 * evidence
            + 0.15 * avail
        )

        expected_best = pred.get("expected_best_outcome", "")

        scored.append({
            "job_id": job_id,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "final_score": round(final_score, 2),
            "risk": round(risk, 2),
            "evidence": round(evidence, 2),
            "composite": round(composite, 3),
            "recommendation_reason": _build_reason(
                final_score, risk, evidence, avail, decision, expected_best,
            ),
        })

    scored.sort(key=lambda x: x["composite"], reverse=True)

    # Drop the internal composite key from output
    results: List[Dict[str, Any]] = []
    for entry in scored[:top_n]:
        del entry["composite"]
        results.append(entry)

    return results
