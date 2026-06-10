"""
evidence_markers.py — Verify claims against the evidence bank and annotate them.

Provides three capabilities:
  1. find_evidence_source() — locate which evidence entry supports a claim
  2. mark_claim() — append an HTML comment with the evidence source (or UNSUPPORTED)
  3. generate_evidence_report() — full audit of a pack's claims vs evidence
"""

from __future__ import annotations

import re
from typing import Set


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
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _extract_keywords(text: str) -> Set[str]:
    """Extract significant words (3+ chars, not stop words) from text."""
    return {
        w.lower()
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]+", text)
        if len(w) >= 3 and w.lower() not in _STOP_WORDS
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
