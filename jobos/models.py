"""Domain models using stdlib dataclasses only. No Pydantic dependency."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_score(name: str, value: float) -> float:
    """Clamp a score to the 0-10 range and return it."""
    if not (0.0 <= value <= 10.0):
        raise ValueError(f"{name} must be between 0 and 10, got {value}")
    return value


_DECISION_OPTIONS = {"apply", "skip", "save_for_later"}


def _validate_decision(value: str) -> str:
    if value not in _DECISION_OPTIONS:
        raise ValueError(
            f"decision must be one of {_DECISION_OPTIONS}, got {value!r}"
        )
    return value


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_value(v: Any) -> Any:
    """Best-effort conversion for from_dict round-tripping."""
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _coerce_value(target_type: Any, v: Any) -> Any:
    """Coerce a raw dict value to the declared field type."""
    if v is None:
        return v
    origin = getattr(target_type, "__origin__", None)
    # Optional[X] is Union[X, None]
    if origin is not None:
        args = getattr(target_type, "__args__", ())
        # handle List[X]
        if origin is list and isinstance(v, list):
            inner = args[0] if args else str
            return [_coerce_value(inner, item) for item in v]
        # handle Dict[K, V]
        if origin is dict and isinstance(v, dict):
            kt = args[0] if args else str
            vt = args[1] if args else str
            return {str(k): _coerce_value(vt, val) for k, val in v.items()}
        # handle Optional (Union[X, None])
        if origin is type(Optional[int]):  # Union
            # pick the non-None arg
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                return _coerce_value(non_none[0], v)
    # primitives
    if target_type in (int, float, str, bool):
        return target_type(v)
    return v


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

@dataclass
class Job:
    job_id: str
    title: str
    company: str
    source: str
    location: str
    work_type: str
    required_days_per_week: Optional[int] = None
    duration: Optional[str] = None
    salary: Optional[str] = None
    jd_text: str = ""
    skills_required: List[str] = field(default_factory=list)
    skills_preferred: List[str] = field(default_factory=list)
    deadline: Optional[str] = None
    apply_url: str = ""
    captured_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        known = {f.name for f in fields(cls)}
        return cls(**{k: _coerce_value(f.type, v) for (k, v), f in
                      ((item, next(f for f in fields(cls) if f.name == item[0]))
                       for item in d.items() if item[0] in known)})


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

@dataclass
class Prediction:
    job_id: str
    company: str = ""
    role: str = ""
    source: str = ""
    resume_version: str = ""
    application_pack_version: str = ""
    created_at: str = field(default_factory=_now_iso)
    fit: float = 0.0
    evidence: str = ""
    opportunity: float = 0.0
    strategic: float = 0.0
    friction: float = 0.0
    risk: float = 0.0
    final_score: float = 0.0
    reply_7d_probability: float = 0.0
    interview_14d_probability: float = 0.0
    positive_signal_30d_probability: float = 0.0
    expected_best_outcome: str = ""
    expected_failure_reason: str = ""
    confidence: float = 0.0
    decision: str = "skip"
    reasons: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        score_fields = [
            "fit", "opportunity", "strategic", "friction", "risk",
            "final_score", "reply_7d_probability",
            "interview_14d_probability", "positive_signal_30d_probability",
            "confidence",
        ]
        for name in score_fields:
            _validate_score(name, getattr(self, name))
        _validate_decision(self.decision)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Prediction":
        known = {f.name for f in fields(cls)}
        filtered = {k: _coerce_value(f.type, v)
                    for (k, v), f in
                    ((item, next(f for f in fields(cls) if f.name == item[0]))
                     for item in d.items() if item[0] in known)}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Retro
# ---------------------------------------------------------------------------

@dataclass
class Retro:
    job_id: str
    submitted_at: Optional[str] = None
    status_3d: Optional[str] = None
    status_14d: Optional[str] = None
    status_30d: Optional[str] = None
    reply_time_hours: Optional[float] = None
    interview_received: bool = False
    offer_received: bool = False
    rejection_received: bool = False
    ghosted: bool = False
    outcome_label: Optional[str] = None
    prediction_error: Optional[str] = None
    rubric_note_candidate: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Retro":
        known = {f.name for f in fields(cls)}
        filtered = {k: _coerce_value(f.type, v)
                    for (k, v), f in
                    ((item, next(f for f in fields(cls) if f.name == item[0]))
                     for item in d.items() if item[0] in known)}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# ApplicationPack
# ---------------------------------------------------------------------------

@dataclass
class ApplicationPack:
    job_id: str
    created_at: str = field(default_factory=_now_iso)
    files: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ApplicationPack":
        known = {f.name for f in fields(cls)}
        filtered = {k: _coerce_value(f.type, v)
                    for (k, v), f in
                    ((item, next(f for f in fields(cls) if f.name == item[0]))
                     for item in d.items() if item[0] in known)}
        return cls(**filtered)
