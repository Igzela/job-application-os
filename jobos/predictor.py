"""
predictor.py — immutable predictions for the Job Application OS.

Stage 3 of the pipeline: given a scored job and candidate profile, produce a
prediction with probability estimates, confidence, and a go/no-go decision.

Predictions are written once and never overwritten. To revise, create a new
version (caller passes --new-version or increments the version suffix).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Decision thresholds ──────────────────────────────────────────────────────

APPLY_THRESHOLD = 5.0
SKIP_THRESHOLD = 3.0


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FunnelProbabilities:
    """Per-stage probability of advancing past each funnel gate."""
    screen: float      # P(get past initial resume screen)
    interview: float   # P(reach interview stage)
    offer: float       # P(receive an offer)

    @property
    def overall(self) -> float:
        """Compound probability of screen -> interview -> offer."""
        return self.screen * self.interview * self.offer


@dataclass(frozen=True)
class Prediction:
    """Immutable prediction record for a single job application."""
    job_id: str
    created_at: str                        # ISO-8601
    rubric_version: str
    dimension_scores: Dict[str, float]     # e.g. {"skill_match": 8, ...}
    final_score: float                     # weighted rubric output, 0-10
    probabilities: FunnelProbabilities
    expected_best_outcome: str             # e.g. "Offer at $45/hr, return pipeline"
    expected_failure_reason: str           # e.g. "Weak company signal, likely ghost"
    confidence: float                      # 0.0 - 1.0
    evidence_count: int                    # how many evidence items informed this
    decision: str                          # "apply" | "skip" | "save_for_later"
    notes: str = ""
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["probabilities"] = asdict(self.probabilities)
        d["probabilities"]["overall"] = self.probabilities.overall
        return d


# ── Probability model ────────────────────────────────────────────────────────

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _estimate_probabilities(
    final_score: float,
    scores: Dict[str, float],
    profile: Dict[str, Any],
) -> FunnelProbabilities:
    """
    Estimate P(screen), P(interview), P(offer) from the final score and
    dimension breakdown.

    Heuristic model (calibrate with retro data as the loop closes):
    - Base rates assume a cold application with no referral.
    - Each 1 point above 5.0 in final_score boosts all stages.
    - Evidence dimension directly boosts screen probability (ATS keyword hit).
    - Strategic dimension boosts interview (narrative fit).
    - Risk and friction depress offer probability.
    """
    # Base rates for a "baseline" score of 5.0
    base_screen = 0.20
    base_interview = 0.35
    base_offer = 0.25

    # Score lift: each point above/below 5 shifts probabilities
    score_delta = final_score - 5.0
    screen_lift = score_delta * 0.06
    interview_lift = score_delta * 0.05
    offer_lift = score_delta * 0.04

    # Dimension-specific boosts
    evidence = scores.get("evidence", 5.0)
    strategic = scores.get("strategic", 5.0)
    risk = scores.get("risk", 5.0)
    friction = scores.get("friction", 5.0)

    # Evidence above 6 helps get past ATS / screen
    if evidence > 6:
        screen_lift += (evidence - 6) * 0.03
    # Strategic alignment helps in interviews
    if strategic > 6:
        interview_lift += (strategic - 6) * 0.02
    # High friction and risk depress offer conversion
    if friction > 6:
        offer_lift -= (friction - 6) * 0.03
    if risk > 6:
        offer_lift -= (risk - 6) * 0.04

    # Referral bonus (if profile says they have one)
    referral_bonus = 0.10 if profile.get("has_referral") else 0.0

    p_screen = _clamp(base_screen + screen_lift + referral_bonus)
    p_interview = _clamp(base_interview + interview_lift + referral_bonus * 0.5)
    p_offer = _clamp(base_offer + offer_lift)

    return FunnelProbabilities(
        screen=round(p_screen, 3),
        interview=round(p_interview, 3),
        offer=round(p_offer, 3),
    )


def _estimate_confidence(evidence_count: int) -> float:
    """
    Confidence grows with the amount of evidence gathered.

    0 evidence items -> 0.10 (barely a guess)
    5 items          -> ~0.55
    10+ items        -> ~0.85 (saturates)
    """
    if evidence_count <= 0:
        return 0.10
    return round(_clamp(0.10 + evidence_count * 0.08, hi=0.95), 2)


def _decide(final_score: float) -> str:
    if final_score >= APPLY_THRESHOLD:
        return "apply"
    if final_score < SKIP_THRESHOLD:
        return "skip"
    return "save_for_later"


def _infer_best_outcome(
    final_score: float,
    probabilities: FunnelProbabilities,
    scores: Dict[str, float],
) -> str:
    """Summarize the optimistic scenario based on score profile."""
    p_offer = probabilities.offer
    compensation = scores.get("compensation", 5.0)
    company = scores.get("company_signal", 5.0)
    opportunity = scores.get("opportunity", 5.0)

    parts: List[str] = []
    if p_offer >= 0.15:
        parts.append("competitive offer likely")
    elif p_offer >= 0.05:
        parts.append("offer possible with strong follow-up")
    else:
        parts.append("low offer probability")

    if compensation >= 7:
        parts.append("strong comp package")
    if company >= 7:
        parts.append("brand-name signal for resume")
    if opportunity >= 7:
        parts.append("significant career growth")

    return "; ".join(parts) if parts else "marginal upside"


def _infer_failure_reason(
    final_score: float,
    probabilities: FunnelProbabilities,
    scores: Dict[str, float],
) -> str:
    """Summarize the most likely failure mode."""
    risk = scores.get("risk", 5.0)
    friction = scores.get("friction", 5.0)
    fit = scores.get("skill_match", scores.get("fit", 5.0))
    evidence = scores.get("evidence", 5.0)
    p_screen = probabilities.screen

    reasons: List[str] = []
    if p_screen < 0.15:
        reasons.append("unlikely to pass initial screen")
    if risk >= 7:
        reasons.append("high-risk company signals")
    if friction >= 7:
        reasons.append("application friction may deter completion")
    if fit <= 4:
        reasons.append("weak skill alignment")
    if evidence <= 3:
        reasons.append("insufficient evidence to support application")

    return "; ".join(reasons) if reasons else "no strong failure signals"


# ── Public API ───────────────────────────────────────────────────────────────

def create_prediction(
    job_data: Dict[str, Any],
    scores: Dict[str, float],
    profile: Dict[str, Any],
) -> Prediction:
    """
    Create an immutable Prediction from scored job data and candidate profile.

    Args:
        job_data: Must contain at minimum ``job_id``. May also contain
            ``rubric_version``, ``company``, ``role``, and ``notes``.
        scores: Dimension scores as {dimension_name: float}. Must include
            ``final_score`` (the weighted rubric output). Other expected keys
            match the rubric dimensions (skill_match, role_fit, compensation,
            company_signal, location_remote, timing_duration, evidence,
            strategic, friction, risk -- any subset is fine).
        profile: Candidate profile dict. ``has_referral`` (bool) boosts
            probability estimates. ``evidence_items`` (list) counts toward
            confidence.

    Returns:
        A frozen Prediction instance.

    Raises:
        KeyError: if ``job_data`` lacks ``job_id`` or ``scores`` lacks
            ``final_score``.
    """
    job_id = job_data["job_id"]
    final_score = scores["final_score"]

    probabilities = _estimate_probabilities(final_score, scores, profile)

    evidence_count = len(profile.get("evidence_items", []))
    confidence = _estimate_confidence(evidence_count)

    decision = _decide(final_score)
    best_outcome = _infer_best_outcome(final_score, probabilities, scores)
    failure_reason = _infer_failure_reason(final_score, probabilities, scores)

    return Prediction(
        job_id=job_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        rubric_version=job_data.get("rubric_version", "v0"),
        dimension_scores={k: v for k, v in scores.items() if k != "final_score"},
        final_score=round(final_score, 2),
        probabilities=probabilities,
        expected_best_outcome=best_outcome,
        expected_failure_reason=failure_reason,
        confidence=confidence,
        evidence_count=evidence_count,
        decision=decision,
        notes=job_data.get("notes", ""),
        version=job_data.get("version", 1),
    )


def save_prediction(prediction: Prediction, predictions_dir: Path | str) -> Path:
    """
    Persist a prediction as an immutable JSON file.

    The file is named ``{job_id}_v{version}.json`` inside ``predictions_dir``.

    Raises:
        FileExistsError: if a file for this job_id + version already exists.
            The error message suggests using ``--new-version`` to create a
            revised prediction instead of overwriting.
    """
    predictions_dir = Path(predictions_dir)
    predictions_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{prediction.job_id}_v{prediction.version}.json"
    filepath = predictions_dir / filename

    if filepath.exists():
        raise FileExistsError(
            f"Prediction already exists: {filepath}\n"
            f"Predictions are immutable. To revise, use --new-version to "
            f"create a new prediction with an incremented version number."
        )

    filepath.write_text(json.dumps(prediction.to_dict(), indent=2, ensure_ascii=False))
    return filepath


def load_prediction(job_id: str, predictions_dir: Path | str) -> Prediction:
    """
    Load the highest-version prediction for a given job_id.

    Raises:
        FileNotFoundError: if no prediction files exist for this job_id.
    """
    predictions_dir = Path(predictions_dir)
    if not predictions_dir.is_dir():
        raise FileNotFoundError(f"Predictions directory not found: {predictions_dir}")

    candidates = sorted(
        predictions_dir.glob(f"{job_id}_v*.json"),
        key=lambda p: p.stem,
    )

    if not candidates:
        raise FileNotFoundError(
            f"No prediction found for job_id={job_id} in {predictions_dir}"
        )

    # Highest version is last after sorting by filename
    latest = candidates[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))

    probs_data = data.pop("probabilities", {})
    probs = FunnelProbabilities(
        screen=probs_data.get("screen", 0.0),
        interview=probs_data.get("interview", 0.0),
        offer=probs_data.get("offer", 0.0),
    )

    return Prediction(
        job_id=data["job_id"],
        created_at=data["created_at"],
        rubric_version=data["rubric_version"],
        dimension_scores=data["dimension_scores"],
        final_score=data["final_score"],
        probabilities=probs,
        expected_best_outcome=data["expected_best_outcome"],
        expected_failure_reason=data["expected_failure_reason"],
        confidence=data["confidence"],
        evidence_count=data["evidence_count"],
        decision=data["decision"],
        notes=data.get("notes", ""),
        version=data.get("version", 1),
    )
