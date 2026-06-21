"""
evidence_markers.py — Verify claims against the evidence bank and annotate them.

Provides three capabilities:
  1. find_evidence_source() — locate which evidence entry supports a claim
  2. mark_claim() — append an HTML comment with the evidence source (or UNSUPPORTED)
  3. generate_evidence_report() — full audit of a pack's claims vs evidence
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

import yaml


class EvidenceReportInputError(ValueError):
    """Raised when workspace evidence report inputs are missing."""


# ---------------------------------------------------------------------------
# Shared internals (mirrors pack_generator._build_evidence_corpus)
# ---------------------------------------------------------------------------

_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "been", "have", "has", "had", "not", "but", "can", "will",
    "would", "could", "should", "may", "might", "shall", "into", "your",
    "our", "their", "its", "his", "her", "you", "who", "what", "when",
    "where", "how", "which", "than", "then", "them", "they", "each",
    "more", "also", "about", "other", "such", "only", "very", "some",
    "any", "all", "most", "used", "using", "via", "able", "well",
}


def _title_to_slug(title: str) -> str:
    """Convert an evidence bank heading to a URL-friendly slug.

    "Project 1: DeepSeek Boss Helper" -> "project-1-deepseek-boss-helper"
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w]+", "-", slug, flags=re.UNICODE)
    slug = slug.replace("_", "-")
    return slug.strip("-")


def _extract_keywords(text: str) -> Set[str]:
    """Extract significant Latin, CJK, and numeric claim tokens."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    words = re.findall(
        r"[a-zA-Z][a-zA-Z0-9+#.]+|[\u3400-\u9fff]+|\d+(?:\.\d+)?",
        text,
    )
    return {
        word.lower()
        for word in words
        if (
            (re.match(r"[a-zA-Z]", word) and len(word) >= 3)
            or re.match(r"[\u3400-\u9fff]", word)
            or re.match(r"\d", word)
        )
        and word.lower() not in _STOP_WORDS
    }


def _build_evidence_corpus(evidence: list[dict]) -> dict:
    """Build lookup structures from evidence bank for claim verification.

    Returns:
        {
            "skills": set of lowercase skill names,
            "technologies": set of lowercase tech/tool names,
            "titles": set of project titles,
            "raw_texts": list of full text blocks (lowercase),
            "fields_flat": dict of all flattened field key-value pairs,
            "entries": list of (entry, slug, combined_text) tuples,
        }
    """
    skills: Set[str] = set()
    technologies: Set[str] = set()
    titles: Set[str] = set()
    raw_texts: list[str] = []
    fields_flat: dict[str, str] = {}
    entries: list[tuple[dict, str, str]] = []

    for entry in evidence:
        title = entry.get("title", "")
        titles.add(title.lower().strip())
        slug = _title_to_slug(title)

        content = entry.get("content", "")
        raw_texts.append(content.lower())

        entry_skills = entry.get("skills", [])
        for s in entry_skills:
            skills.add(s.lower().strip())

        entry_fields_flat: list[str] = []
        fields = entry.get("fields", {})
        if isinstance(fields, dict):
            for k, v in fields.items():
                fields_flat[k.lower().strip()] = v.lower().strip()
                entry_fields_flat.append(v.lower())
                for item in re.split(r"[,;]", v):
                    item = item.strip().lower()
                    if item:
                        technologies.add(item)

        # Per-entry combined text for source attribution
        combined = " ".join(
            [title.lower(), content.lower()] + entry_fields_flat + [s.lower() for s in entry_skills]
        )
        entries.append((entry, slug, combined))

    return {
        "skills": skills,
        "technologies": technologies,
        "titles": titles,
        "raw_texts": raw_texts,
        "fields_flat": fields_flat,
        "entries": entries,
    }


def _keyword_overlap(claim: str, text: str) -> float:
    """Return the fraction of claim keywords found in text (0.0-1.0)."""
    words = _extract_keywords(claim)
    if not words:
        return 1.0  # nothing to verify
    hits = sum(1 for w in words if w in text)
    return hits / len(words)


def _flatten_profile_text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_profile_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_profile_text(item) for item in value)
    if value is None:
        return ""
    return str(value).lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_evidence_source(claim: str, evidence: list[dict]) -> str | None:
    """Search evidence bank entries for support of *claim*.

    Returns a source string like ``"evidence_bank.md#project-1-deepseek-boss-helper"``
    if the claim is supported (>= 30 % keyword overlap), or ``None``.
    """
    corpus = _build_evidence_corpus(evidence)

    best_slug: str | None = None
    best_overlap: float = 0.0

    for _entry, slug, combined in corpus["entries"]:
        overlap = _keyword_overlap(claim, combined)
        if overlap > best_overlap:
            best_overlap = overlap
            best_slug = slug

    if best_overlap >= 0.30 and best_slug:
        return f"evidence_bank.md#{best_slug}"
    return None


def mark_claim(claim: str, evidence: list[dict]) -> str:
    """Return *claim* with an HTML comment annotating its evidence status.

    Appends ``<!-- evidence: evidence_bank.md#slug -->`` when supported, or
    ``<!-- evidence: UNSUPPORTED -->`` when not.
    """
    source = find_evidence_source(claim, evidence)
    if source:
        return f"{claim} <!-- evidence: {source} -->"
    return f"{claim} <!-- evidence: UNSUPPORTED -->"


def generate_evidence_report(
    pack_files: dict[str, str],
    evidence: list[dict],
    job_data: dict,
    profile_data: dict | None = None,
) -> dict:
    """Audit every claim in *pack_files* against the evidence bank.

    Returns::

        {
            "supported":    [{"claim": str, "source": str}],
            "unsupported":  [{"claim": str, "file": str}],
            "weak":         [{"claim": str, "source": str, "reason": str}],
            "missing_jd_skills": [str],
            "overclaim_risk": float,   # 0.0-1.0
        }
    """
    corpus = _build_evidence_corpus(evidence)
    profile_text = _flatten_profile_text(profile_data or {})

    supported: list[dict] = []
    unsupported: list[dict] = []
    weak: list[dict] = []

    # ------------------------------------------------------------------
    # Extract claims from claim-bearing pack files only
    # ------------------------------------------------------------------
    # Only validate files that contain candidate-authored claims.
    # jd.md, prediction.md, form_answers.md, submit_checklist.md are
    # metadata or boilerplate — not candidate claims.
    _CLAIM_FILES = {"resume_targeted.md", "greeting.md", "cover_letter.md"}
    all_claim_texts: list[str] = []

    for filename, text in pack_files.items():
        if filename not in _CLAIM_FILES:
            continue
        for claim in _extract_claims_from_markdown(text):
            all_claim_texts.append(claim)

            best_slug: str | None = None
            best_overlap: float = 0.0

            for _entry, slug, combined in corpus["entries"]:
                overlap = _keyword_overlap(claim, combined)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_slug = slug

            if best_overlap >= 0.30 and best_slug:
                source = f"evidence_bank.md#{best_slug}"
                if best_overlap < 0.50:
                    weak.append({
                        "claim": claim,
                        "source": source,
                        "reason": f"Low keyword overlap ({best_overlap:.0%})",
                    })
                else:
                    supported.append({"claim": claim, "source": source})
            elif profile_text and _keyword_overlap(claim, profile_text) >= 0.50:
                supported.append({"claim": claim, "source": "profile"})
            else:
                unsupported.append({"claim": claim, "file": filename})

    # ------------------------------------------------------------------
    # Missing JD skills — skills in the job description not in any pack file
    # ------------------------------------------------------------------
    required_skills = job_data.get("skills_required", [])
    all_pack_text = " ".join(pack_files.values()).lower()

    missing_jd_skills: list[str] = []
    for skill in required_skills:
        if skill.lower().strip() not in all_pack_text:
            missing_jd_skills.append(skill)

    # ------------------------------------------------------------------
    # Overclaim risk
    # ------------------------------------------------------------------
    total_claims = len(supported) + len(unsupported) + len(weak)
    overclaim_risk = len(unsupported) / max(total_claims, 1)

    return {
        "supported": supported,
        "unsupported": unsupported,
        "weak": weak,
        "missing_jd_skills": missing_jd_skills,
        "overclaim_risk": round(overclaim_risk, 4),
    }


def generate_workspace_evidence_report(state_dir: str | Path, job_id: str) -> dict:
    """Generate an evidence report from saved workspace pack and job data."""
    from .application_pack import (
        load_application_pack,
        update_pack_validation,
        workspace_pack_sources,
    )
    from .pipeline import transition_job
    from .profile_loader import load_evidence_bank, load_profile
    from .runtime_state import save_json_state
    from .workspace import (
        application_dir,
        jobs_normalized_dir,
        load_state,
        save_state,
    )

    state_dir = Path(state_dir)
    pack_dir = application_dir(state_dir, job_id)
    if not pack_dir.exists():
        raise EvidenceReportInputError(
            f"No application pack for {job_id}. Run `job pack` first."
        )

    pack_files = load_application_pack(pack_dir, job_id=job_id).files
    evidence = load_evidence_bank(state_dir)
    profile = load_profile(state_dir)

    state = load_state(state_dir)
    job_entry = state.get("jobs", {}).get(job_id, {})
    job_yaml = jobs_normalized_dir(state_dir) / f"{job_id}.yaml"
    if job_yaml.exists():
        job_data = yaml.safe_load(job_yaml.read_text(encoding="utf-8")) or {}
    else:
        job_data = job_entry

    report = generate_evidence_report(
        pack_files,
        evidence,
        job_data,
        profile_data=profile,
    )
    report_path = pack_dir / "validation_report.json"
    save_json_state(
        report_path,
        {
            "job_id": job_id,
            **report,
        },
    )
    report["report_path"] = str(report_path)
    validation = {
        "supported": len(report["supported"]),
        "weak": len(report["weak"]),
        "unsupported": len(report["unsupported"]),
    }
    if job_id in state.get("jobs", {}):
        job = state["jobs"][job_id]
        job["validation"] = validation
        if validation["unsupported"] == 0:
            transition_job(job, "validated")
        save_state(state_dir, state)
    update_pack_validation(
        pack_dir,
        job_id=job_id,
        sources=workspace_pack_sources(state_dir, job_id),
        validation=validation,
    )
    return report


# ---------------------------------------------------------------------------
# Claim extraction (reused from validate_pack logic, centralized here)
# ---------------------------------------------------------------------------

def _extract_claims_from_markdown(text: str) -> list[str]:
    """Pull individual claim strings from a markdown document.

    Claims are:
      - Bullet points (``- ...``)
      - Bold-field value lines (``**Key:** value``)
      - Lines containing skill/experience assertions in prose
    """
    claims: list[str] = []
    current_section = ""

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()
            continue

        if not stripped or stripped.startswith(">") or stripped.startswith("---"):
            continue

        # Bold-field lines: "**Languages:** Python, JS"
        if stripped.startswith("**") and ":" in stripped and not stripped.startswith("- "):
            colon_idx = stripped.index(":")
            value_part = stripped[colon_idx + 1 :].strip().rstrip("*").strip()
            if value_part:
                claims.append(value_part)
            continue

        # Bullet points
        if stripped.startswith("- "):
            claim = stripped[2:]
            if claim.startswith("[") or claim.startswith("Available") or claim.startswith("Open to"):
                continue
            claims.append(claim)
            continue

        # Prose lines with experience assertions
        lower = stripped.lower()
        if any(kw in lower for kw in ("hands-on", "experience with", "built", "developed", "proficient")):
            claims.append(stripped)

    return claims
