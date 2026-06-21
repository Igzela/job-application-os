"""Job scoring engine with 6-dimension scoring and hard gates.

Dimensions: fit, evidence, opportunity, strategic, friction, risk (each 0-10).
Final score: 0.30*fit + 0.25*evidence + 0.20*opportunity + 0.15*strategic - 0.10*friction - 0.20*risk

Hard gates (skip or penalize):
- availability conflict   -> risk penalty
- missing required skill  -> evidence penalty
- unrelated job           -> skip entirely
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _keywords_from(text: str) -> set[str]:
    tokens = _normalize(text).split()
    stopwords = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "this", "that",
        "these", "those", "it", "its", "we", "our", "you", "your", "they",
        "their", "i", "my", "me", "he", "she", "his", "her", "him",
        "not", "no", "as", "if", "so", "than", "too", "very", "just",
        "about", "above", "after", "again", "all", "also", "am", "any",
        "because", "before", "between", "both", "each", "few", "more",
        "most", "other", "some", "such", "only", "own", "same", "into",
        "over", "under", "up", "down", "out", "off", "then", "once", "here",
        "there", "when", "where", "why", "how", "what", "which", "who",
        "whom", "while", "during", "through", "between", "until", "against",
    }
    return {t for t in tokens if len(t) > 2 and t not in stopwords}


def _overlap(a: set[str], b: set[str]) -> float:
    """Jaccard-like overlap score 0-1."""
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, value))


def _extract_skill_names(profile: dict) -> set[str]:
    """Extract all skill names from a profile, handling both flat list and nested YAML formats.

    Flat format (tests): profile["skills"] = ["Python", "JavaScript", ...]
    YAML format (real):  profile["skills"]["programming_languages"][0]["name"] = "Python"
    """
    raw = profile.get("skills", [])
    names: set[str] = set()

    if isinstance(raw, list):
        # Flat list of strings
        for item in raw:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict):
                names.add(item.get("name", ""))
    elif isinstance(raw, dict):
        # Nested YAML: {programming_languages: [{name: "Python", ...}], frameworks: [...], domains: [...]}
        for category in ("programming_languages", "frameworks", "domains", "tools"):
            for entry in raw.get(category, []):
                if isinstance(entry, dict):
                    name = entry.get("name", "")
                    if name:
                        names.add(name)
                    # Also add tools
                    for tool in entry.get("tools", []):
                        if tool:
                            names.add(tool)
                elif isinstance(entry, str):
                    names.add(entry)

    # Also pull from languages list
    for lang in profile.get("languages", []):
        if isinstance(lang, str):
            names.add(lang)

    return {n for n in names if n}


def _extract_evidence_text(evidence: list[dict]) -> set[str]:
    """Extract searchable keywords from evidence bank entries."""
    kw: set[str] = set()
    for item in evidence:
        if isinstance(item, str):
            kw |= _keywords_from(item)
        elif isinstance(item, dict):
            kw |= _keywords_from(item.get("description", ""))
            kw |= _keywords_from(item.get("title", ""))
            kw |= _keywords_from(item.get("content", ""))
            for skill in item.get("skills", []):
                kw |= _keywords_from(skill)
            # Also search fields dict values
            fields = item.get("fields", {})
            if isinstance(fields, dict):
                for v in fields.values():
                    kw |= _keywords_from(str(v))
    return kw


# ---------------------------------------------------------------------------
# Hard gates
# ---------------------------------------------------------------------------

def _check_hard_gates(job_data: dict, profile: dict, rubric: dict) -> tuple[bool, dict[str, float]]:
    """Return (should_skip, penalties) where penalties are dimension overrides.

    should_skip=True means the job is entirely unrelated and should not be scored.
    Penalties are absolute values to subtract from the relevant dimension.
    """
    skip = False
    penalties: dict[str, float] = {}

    job_desc = job_data.get("description", "")
    job_title = job_data.get("title", "")
    job_text = f"{job_title} {job_desc}"

    # Gate 1: unrelated job — skip entirely
    target_roles = rubric.get("target_roles", profile.get("target_roles", []))
    if target_roles:
        role_keywords = set()
        for role in target_roles:
            role_keywords |= _keywords_from(role)
        job_keywords = _keywords_from(job_text)
        overlap = _overlap(role_keywords, job_keywords)
        if overlap < 0.05:
            skip = True

    # Gate 2: availability conflict -> risk penalty
    availability = profile.get("availability", {})
    conflicts = availability.get("conflicts", [])
    if conflicts:
        start = job_data.get("start_date", "")
        for conflict in conflicts:
            if _date_conflict(start, conflict):
                penalties["risk"] = penalties.get("risk", 0) + 3.0
                break

    # Gate 2b: days-per-week conflict
    avail_start = availability.get("start", profile.get("availability_start", ""))
    avail_end = availability.get("end", profile.get("availability_end", ""))
    profile_days = profile.get("days_per_week")
    wa = availability.get("work_arrangement", profile.get("work_arrangement", {}))
    weekly_cap = profile.get("weekly_capacity", {})
    if not profile_days and weekly_cap:
        profile_days = weekly_cap.get("days_per_week")

    job_days = job_data.get("required_days_per_week")
    if profile_days and job_days:
        try:
            if int(job_days) > int(profile_days):
                penalties["risk"] = penalties.get("risk", 0) + 2.0
        except (ValueError, TypeError):
            pass

    # Gate 2c: date window conflict
    job_start = job_data.get("start_date", "")
    job_duration = job_data.get("duration", "")
    if avail_start and job_start and job_start > avail_end:
        penalties["risk"] = penalties.get("risk", 0) + 3.0

    # Gate 3: missing required skill -> evidence penalty
    required_skills = rubric.get("required_skills", profile.get("required_skills", []))
    if required_skills:
        candidate_skills = _extract_skill_names(profile)
        candidate_kw: set[str] = set()
        for s in candidate_skills:
            candidate_kw |= _keywords_from(s)
        for req in required_skills:
            req_kw = _keywords_from(req)
            if not req_kw & candidate_kw:
                penalties["evidence"] = penalties.get("evidence", 0) + 2.0

    return skip, penalties


def _date_conflict(start_date: str, conflict: dict) -> bool:
    """Simple date overlap check. Returns True if conflict overlaps with job start."""
    if not start_date:
        return False
    c_start = conflict.get("start", "")
    c_end = conflict.get("end", "")
    if not c_start or not c_end:
        return False
    return c_start <= start_date <= c_end


# ---------------------------------------------------------------------------
# Dimension scorers (mock/deterministic mode — keyword-based, no LLM)
# ---------------------------------------------------------------------------

def _score_fit(job_data: dict, profile: dict, rubric: dict) -> float:
    """Fit: skill overlap + location match + role alignment."""
    job_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
    job_kw = _keywords_from(job_text)

    # Skill overlap — handle both flat list and nested YAML
    candidate_skill_names = _extract_skill_names(profile)
    candidate_skills: set[str] = set()
    for skill in candidate_skill_names:
        candidate_skills |= _keywords_from(skill)
    skill_score = _overlap(candidate_skills, job_kw) * 10

    # Location match
    location_score = 0.0
    preferred_locations = profile.get("preferred_locations", [])
    job_location = job_data.get("location", "")
    if preferred_locations and job_location:
        if any(loc.lower() in job_location.lower() for loc in preferred_locations):
            location_score = 3.0
        elif "remote" in job_location.lower() or "remote" in job_text.lower():
            location_score = 2.0
    elif job_location and ("remote" in job_location.lower() or "remote" in job_text.lower()):
        location_score = 2.5

    # Role alignment
    target_roles = rubric.get("target_roles", profile.get("target_roles", []))
    role_score = 0.0
    if target_roles:
        role_kw = set()
        for role in target_roles:
            role_kw |= _keywords_from(role)
        role_score = _overlap(role_kw, job_kw) * 5

    return _clamp(skill_score * 0.5 + location_score * 0.25 + role_score * 0.25)


def _score_evidence(job_data: dict, profile: dict, rubric: dict) -> float:
    """Evidence: how well candidate's proven experience maps to requirements."""
    requirements = job_data.get("requirements", job_data.get("description", ""))
    req_kw = _keywords_from(requirements)

    # Gather evidence keywords from both profile experience and evidence bank
    evidence_items = profile.get("experience", []) + profile.get("evidence", [])
    evidence_kw = _extract_evidence_text(evidence_items)

    # Also pull keywords from profile skill names
    for skill_name in _extract_skill_names(profile):
        evidence_kw |= _keywords_from(skill_name)

    overlap = _overlap(evidence_kw, req_kw)
    # Scale: 0 overlap -> 2, full overlap -> 10
    return _clamp(2.0 + overlap * 8.0)


def _score_opportunity(job_data: dict, profile: dict, rubric: dict) -> float:
    """Opportunity: career growth, company prestige, comp alignment."""
    score = 5.0  # baseline

    job_text = f"{job_data.get('title', '')} {job_data.get('description', '')}"
    growth_keywords = [
        "senior", "lead", "principal", "staff", "director", "head",
        "growth", "scale", "impact", "ownership", "leadership",
    ]
    growth_hits = sum(1 for kw in growth_keywords if kw in job_text.lower())
    score += min(growth_hits * 0.5, 2.5)

    # Comp alignment
    target_comp = profile.get("target_compensation")
    job_comp = job_data.get("salary_max") or job_data.get("salary")
    if target_comp and job_comp:
        try:
            ratio = float(job_comp) / float(target_comp)
            if ratio >= 1.0:
                score += 1.5
            elif ratio >= 0.9:
                score += 0.5
            else:
                score -= 1.0
        except (ValueError, ZeroDivisionError):
            pass

    return _clamp(score)


def _score_strategic(job_data: dict, profile: dict, rubric: dict) -> float:
    """Strategic: alignment with career trajectory, network value, brand."""
    score = 5.0

    job_text = f"{job_data.get('title', '')} {job_data.get('description', '')} {job_data.get('company', '')}"
    company = job_data.get("company", "")

    # Brand signal
    target_companies = profile.get("target_companies", [])
    if target_companies and company:
        if any(tc.lower() in company.lower() for tc in target_companies):
            score += 2.0

    # Network signal
    referrals = profile.get("referral_companies", [])
    if referrals and company:
        if any(r.lower() in company.lower() for r in referrals):
            score += 1.0

    # Strategic keywords
    strategic_kw = ["mission", "values", "culture", "diversity", "sustainability"]
    hits = sum(1 for kw in strategic_kw if kw in job_text.lower())
    score += min(hits * 0.3, 1.0)

    return _clamp(score)


def _score_friction(job_data: dict, profile: dict, rubric: dict) -> float:
    """Friction: application difficulty, visa issues, relocation, commute."""
    score = 3.0  # baseline friction

    # Relocation required
    preferred = profile.get("preferred_locations", [])
    job_loc = job_data.get("location", "")
    if preferred and job_loc:
        if not any(loc.lower() in job_loc.lower() for loc in preferred):
            if "remote" not in job_loc.lower():
                score += 2.0

    # Visa / sponsorship
    if "visa" in str(job_data).lower() or "sponsorship" in str(job_data).lower():
        if not profile.get("visa_status", {}).get("authorized", True):
            score += 3.0

    # Long application process
    app_method = job_data.get("application_method", "")
    if "cover letter" in app_method.lower() or "essay" in app_method.lower():
        score += 1.0

    return _clamp(score)


def _score_risk(job_data: dict, profile: dict, rubric: dict) -> float:
    """Risk: startup instability, contract role, mismatch red flags."""
    score = 2.0  # baseline risk

    job_type = job_data.get("type", "").lower()
    if "contract" in job_type or "temporary" in job_type or "temp" in job_type:
        score += 2.0

    company_size = job_data.get("company_size", "")
    if company_size:
        try:
            size = int(company_size)
            if size < 10:
                score += 2.0
            elif size < 50:
                score += 1.0
        except ValueError:
            pass

    # Red flags in description
    red_flags = ["fast-paced", "wear many hats", "must be willing to", "unpaid"]
    desc = job_data.get("description", "").lower()
    hits = sum(1 for flag in red_flags if flag in desc)
    score += min(hits * 0.5, 2.0)

    return _clamp(score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "fit": 0.30,
    "evidence": 0.25,
    "opportunity": 0.20,
    "strategic": 0.15,
    "friction": -0.10,
    "risk": -0.20,
}


def score_job(
    job_data: dict[str, Any],
    profile: dict[str, Any],
    evidence: list[dict[str, Any]],
    rubric: dict[str, Any],
) -> dict[str, Any]:
    """Score a job across 6 dimensions and compute a weighted final score.

    Args:
        job_data: Job posting data (title, description, company, location, etc.)
        profile: Candidate profile (skills, experience, preferences, etc.)
            Handles both flat-list format (tests) and nested YAML format (real).
        evidence: List of evidence items (projects, achievements, references).
        rubric: Scoring rubric config (required_skills, target_roles, etc.)

    Returns:
        Dict with keys: fit, evidence, opportunity, strategic, friction, risk,
        final_score, skipped (bool), skip_reason (str or None), penalties (dict).
    """
    # Merge evidence into profile for scorers
    merged_profile = {**profile, "evidence": evidence}

    # Normalize availability: YAML has top-level keys, tests may nest under "availability"
    if "availability" not in merged_profile:
        merged_profile["availability"] = {}
    avail = merged_profile["availability"]
    # Pull from YAML top-level if availability dict is empty
    if not avail.get("conflicts") and not avail.get("start"):
        iw = profile.get("internship_window", {})
        if iw:
            avail.setdefault("start", iw.get("start", ""))
            avail.setdefault("end", iw.get("end", ""))
        wa = profile.get("work_arrangement", {})
        if wa:
            avail.setdefault("work_arrangement", wa)

    # Normalize preferred_locations from YAML top-level
    if "preferred_locations" not in merged_profile:
        tl = profile.get("target_locations", [])
        if tl:
            merged_profile["preferred_locations"] = tl

    # Hard gates
    should_skip, penalties = _check_hard_gates(job_data, merged_profile, rubric)

    if should_skip:
        return {
            "fit": 0.0,
            "evidence": 0.0,
            "opportunity": 0.0,
            "strategic": 0.0,
            "friction": 10.0,
            "risk": 10.0,
            "final_score": 0.0,
            "skipped": True,
            "skip_reason": "Unrelated job — below relevance threshold",
            "penalties": penalties,
        }

    # Score each dimension
    dimensions = {
        "fit": _score_fit(job_data, merged_profile, rubric),
        "evidence": _score_evidence(job_data, merged_profile, rubric),
        "opportunity": _score_opportunity(job_data, merged_profile, rubric),
        "strategic": _score_strategic(job_data, merged_profile, rubric),
        "friction": _score_friction(job_data, merged_profile, rubric),
        "risk": _score_risk(job_data, merged_profile, rubric),
    }

    # Apply penalties
    for dim, penalty in penalties.items():
        if dim in dimensions:
            dimensions[dim] = _clamp(dimensions[dim] - penalty)

    # Weighted final score
    final_score = sum(dimensions[d] * _WEIGHTS[d] for d in _WEIGHTS)
    final_score = _clamp(final_score, 0.0, 10.0)

    return {
        **dimensions,
        "final_score": round(final_score, 2),
        "skipped": False,
        "skip_reason": None,
        "penalties": penalties,
    }


def score_workspace_job(state_dir: str | Path, job_id: str) -> dict[str, Any]:
    """Score a normalized workspace job and update workspace state."""
    import yaml

    from .pipeline import transition_job
    from .profile_loader import load_evidence_bank, load_profile
    from .workspace import jobs_normalized_dir, load_state, save_state

    state_dir = Path(state_dir)
    yaml_path = jobs_normalized_dir(state_dir) / f"{job_id}.yaml"
    json_path = jobs_normalized_dir(state_dir) / f"{job_id}.json"
    if yaml_path.exists():
        job_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    elif json_path.exists():
        job_data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"Job {job_id} not found in jobs/normalized/")

    profile = load_profile(state_dir)
    evidence = load_evidence_bank(state_dir)
    rubric_path = state_dir / "rubrics" / "v0_student_internship.md"
    rubric = {"target_roles": profile.get("target_roles", [])}
    if rubric_path.exists():
        from .rubric_manager import load_rubric

        rubric = load_rubric(str(rubric_path))

    scores = score_job(job_data, profile, evidence, rubric)
    state = load_state(state_dir)
    if job_id in state["jobs"]:
        transition_job(state["jobs"][job_id], "scored")
        state["jobs"][job_id]["scores"] = {
            key: value
            for key, value in scores.items()
            if key not in ("skipped", "skip_reason")
        }
        save_state(state_dir, state)
    return scores
