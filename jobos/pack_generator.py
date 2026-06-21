"""
pack_generator.py — Generate an ApplicationPack from job data, prediction, profile, and evidence.

Each pack contains markdown files:
  jd.md             — raw job description
  prediction.md     — prediction summary
  resume_targeted.md — conservative targeted resume (evidence-only claims)
  greeting.md       — Chinese-style greeting for internship platforms
  cover_letter.md   — short cover letter
  form_answers.md   — common form Q&A
  submit_checklist.md — requires human confirmation before submission

The resume MUST only contain facts traceable to profile or evidence_bank.
validate_pack() flags any unsupported claims.
"""

from __future__ import annotations

import re
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from .models import ApplicationPack, Job, Prediction
from .profile_loader import (
    load_evidence_bank,
    load_profile,
    validate_profile_consistency,
)
from .evidence_markers import find_evidence_source, generate_evidence_report


@dataclass(frozen=True)
class WorkspacePackResult:
    """Result of generating and saving a pack from workspace state."""
    pack: ApplicationPack
    warnings: list[str]
    pack_dir: Path


class PackInputError(ValueError):
    """Raised when workspace state lacks data required for pack generation."""


@dataclass(frozen=True)
class CandidateFacts:
    """Normalized profile/evidence facts used by pack renderers."""
    name: str
    first_name: str
    email: str
    location: str
    languages: list[str]
    education: list[dict]
    school: str
    study: str
    graduation_date: str
    gpa: str
    programming_languages: list[str]
    frameworks: list[str]
    programming_language_labels: list[str]
    framework_labels: list[str]
    domain_labels: list[str]
    availability_start: str
    availability_end: str
    days_per_week: Any
    work_arrangement: Any
    work_preference: str
    target_locations: list[str]
    constraints: list[str]
    project_names: list[str]


def _skill_names(entries: Any) -> list[str]:
    if not isinstance(entries, list):
        return []
    names: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("name"):
            names.append(entry["name"])
        elif isinstance(entry, str):
            names.append(entry)
    return names


def _skill_label(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return ""
    name = entry.get("name", "")
    proficiency = entry.get("proficiency", "")
    return f"{name} ({proficiency})" if name and proficiency else name


def _domain_label(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return ""
    name = entry.get("name", "")
    proficiency = entry.get("proficiency", "")
    tools = entry.get("tools", [])
    label = f"{name} ({proficiency})" if name and proficiency else name
    if tools:
        label += f" [{', '.join(tools)}]"
    return label


def derive_candidate_facts(profile: dict, evidence: list[dict]) -> CandidateFacts:
    """Normalize repeated candidate facts from profile and evidence bank data."""
    raw_name = profile.get("name", "")
    name = raw_name or "Candidate"
    education = profile.get("education", [])
    if not isinstance(education, list):
        education = []
    primary_education = education[0] if education else {}

    school = primary_education.get("institution", "") or profile.get("school", "")
    study = (
        primary_education.get("major", "")
        or primary_education.get("degree", "")
        or profile.get("major", "")
    )
    graduation_date = (
        primary_education.get("graduation_date", "")
        or profile.get("graduation_date", "")
    )
    gpa = str(primary_education.get("gpa", "") or "")

    skills_data = profile.get("skills", {})
    if not isinstance(skills_data, dict):
        skills_data = {}
    programming_languages = _skill_names(skills_data.get("programming_languages", []))
    frameworks = _skill_names(skills_data.get("frameworks", []))
    programming_language_entries = skills_data.get("programming_languages", [])
    framework_entries = skills_data.get("frameworks", [])
    domain_entries = skills_data.get("domains", [])

    internship_window = profile.get("internship_window", {})
    if not isinstance(internship_window, dict):
        internship_window = {}
    availability_window = internship_window
    if not availability_window:
        availability = profile.get("availability", {})
        if isinstance(availability, dict):
            availability_window = availability
    availability_start = (
        profile.get("availability_start", "")
        or availability_window.get("start", "")
        or availability_window.get("availability_start", "")
    )
    availability_end = (
        profile.get("availability_end", "")
        or availability_window.get("end", "")
        or availability_window.get("availability_end", "")
    )
    weekly_capacity = profile.get("weekly_capacity", {})
    if not isinstance(weekly_capacity, dict):
        weekly_capacity = {}
    days_per_week = profile.get("days_per_week", "") or weekly_capacity.get(
        "days_per_week",
        "",
    )

    work_arrangement = profile.get("work_arrangement", {})
    if isinstance(work_arrangement, dict):
        work_preference = work_arrangement.get("preferred", "")
    else:
        work_preference = str(work_arrangement)

    languages = [
        text
        for text in (_format_language(language) for language in profile.get("languages", []))
        if text
    ]

    return CandidateFacts(
        name=name,
        first_name=raw_name.split()[0] if raw_name else "there",
        email=profile.get("email", ""),
        location=profile.get("location", ""),
        languages=languages,
        education=education,
        school=school,
        study=study,
        graduation_date=graduation_date,
        gpa=gpa,
        programming_languages=programming_languages,
        frameworks=frameworks,
        programming_language_labels=[
            label for label in (_skill_label(entry) for entry in programming_language_entries) if label
        ],
        framework_labels=[
            label for label in (_skill_label(entry) for entry in framework_entries) if label
        ],
        domain_labels=[
            label for label in (_domain_label(entry) for entry in domain_entries) if label
        ],
        availability_start=availability_start,
        availability_end=availability_end,
        days_per_week=days_per_week,
        work_arrangement=work_arrangement,
        work_preference=work_preference,
        target_locations=profile.get("target_locations", []),
        constraints=profile.get("constraints", []),
        project_names=[entry.get("title", "") for entry in evidence if entry.get("title")],
    )


# ---------------------------------------------------------------------------
# Evidence indexing — build a searchable set of factual tokens from evidence
# ---------------------------------------------------------------------------

def _build_evidence_corpus(evidence: list[dict]) -> dict:
    """Build lookup structures from evidence bank for claim verification.

    Returns:
        {
            "skills": set of lowercase skill names,
            "technologies": set of lowercase tech/tool names,
            "titles": set of project titles,
            "raw_texts": list of full text blocks (lowercase),
            "fields_flat": dict of all flattened field key-value pairs,
        }
    """
    skills: Set[str] = set()
    technologies: Set[str] = set()
    titles: Set[str] = set()
    raw_texts: List[str] = []
    fields_flat: Dict[str, str] = {}

    for entry in evidence:
        title = entry.get("title", "")
        titles.add(title.lower().strip())

        content = entry.get("content", "")
        raw_texts.append(content.lower())

        fields = entry.get("fields", {})
        for k, v in fields.items():
            fields_flat[k.lower().strip()] = v.lower().strip()
            # Split comma-separated tech lists
            for item in re.split(r"[,;]", v):
                item = item.strip().lower()
                if item:
                    technologies.add(item)

        entry_skills = entry.get("skills", [])
        for s in entry_skills:
            skills.add(s.lower().strip())

    return {
        "skills": skills,
        "technologies": technologies,
        "titles": titles,
        "raw_texts": raw_texts,
        "fields_flat": fields_flat,
    }


def _evidence_supports_claim(claim: str, corpus: dict) -> bool:
    """Check if a textual claim has any supporting evidence in the corpus.

    Uses keyword overlap: extracts significant words (3+ chars) from the claim
    and checks if a threshold appears in evidence texts.
    """
    stop_words = {
        "the", "and", "for", "with", "that", "this", "from", "are", "was",
        "were", "been", "have", "has", "had", "not", "but", "can", "will",
        "would", "could", "should", "may", "might", "shall", "into", "your",
        "our", "their", "its", "his", "her", "you", "who", "what", "when",
        "where", "how", "which", "than", "then", "them", "they", "each",
        "more", "also", "about", "other", "such", "only", "very", "some",
        "any", "all", "most", "used", "using", "via", "able", "well",
    }

    words = set(
        w.lower()
        for w in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.]+", claim)
        if len(w) >= 3 and w.lower() not in stop_words
    )

    if not words:
        return True  # nothing to verify

    all_text = " ".join(corpus["raw_texts"])
    all_skills = " ".join(corpus["skills"])
    all_tech = " ".join(corpus["technologies"])
    combined = f"{all_text} {all_skills} {all_tech} {' '.join(corpus['titles'])}"

    hits = sum(1 for w in words if w in combined)
    # Require at least 30% of claim words to appear in evidence
    return hits / len(words) >= 0.30


# ---------------------------------------------------------------------------
# Generators — each returns a markdown string
# ---------------------------------------------------------------------------

def _generate_jd(job_data: dict) -> str:
    """Raw job description markdown."""
    title = job_data.get("title", "Unknown Position")
    company = job_data.get("company", "Unknown Company")
    location = job_data.get("location", "")
    work_type = job_data.get("work_type", "")
    salary = job_data.get("salary", "")
    jd_text = job_data.get("jd_text", "")
    required = job_data.get("skills_required", [])
    preferred = job_data.get("skills_preferred", [])
    url = job_data.get("apply_url", "")

    parts = [f"# {title} at {company}\n"]
    if location:
        parts.append(f"**Location:** {location}")
    if work_type:
        parts.append(f"**Work Type:** {work_type}")
    if salary:
        parts.append(f"**Salary:** {salary}")
    if url:
        parts.append(f"**Apply:** {url}")
    parts.append("")

    if jd_text:
        parts.append("## Job Description\n")
        parts.append(jd_text)
        parts.append("")

    if required:
        parts.append("## Required Skills\n")
        for s in required:
            parts.append(f"- {s}")
        parts.append("")

    if preferred:
        parts.append("## Preferred Skills\n")
        for s in preferred:
            parts.append(f"- {s}")

    return "\n".join(parts)


def _generate_prediction_summary(prediction: dict) -> str:
    """Prediction summary markdown."""
    lines = ["# Application Prediction\n"]

    decision = prediction.get("decision", "skip")
    final_score = prediction.get("final_score", 0.0)
    confidence = prediction.get("confidence", 0.0)

    lines.append(f"**Decision:** {decision.upper()}")
    lines.append(f"**Final Score:** {final_score:.1f}/10")
    lines.append(f"**Confidence:** {confidence:.0%}")
    lines.append("")

    # Probabilities — handle both predictor.py (nested) and models.py (flat)
    probs = prediction.get("probabilities", {})
    if isinstance(probs, dict):
        p_screen = probs.get("screen", prediction.get("reply_7d_probability", 0))
        p_interview = probs.get("interview", prediction.get("interview_14d_probability", 0))
        p_offer = probs.get("offer", prediction.get("positive_signal_30d_probability", 0))
    else:
        p_screen = prediction.get("reply_7d_probability", 0)
        p_interview = prediction.get("interview_14d_probability", 0)
        p_offer = prediction.get("positive_signal_30d_probability", 0)

    lines.append("## Funnel Probabilities\n")
    lines.append(f"| Stage | Probability |")
    lines.append(f"|-------|-------------|")
    lines.append(f"| Pass screen | {p_screen:.0%} |")
    lines.append(f"| Reach interview | {p_interview:.0%} |")
    lines.append(f"| Receive offer | {p_offer:.0%} |")
    lines.append("")

    best = prediction.get("expected_best_outcome", "")
    failure = prediction.get("expected_failure_reason", "")
    if best:
        lines.append(f"**Best outcome:** {best}")
    if failure:
        lines.append(f"**Likely failure:** {failure}")
    lines.append("")

    # Dimension scores
    dim_scores = prediction.get("dimension_scores", {})
    if dim_scores:
        lines.append("## Dimension Scores\n")
        for k, v in dim_scores.items():
            label = k.replace("_", " ").title()
            lines.append(f"- **{label}:** {v:.1f}/10")
        lines.append("")

    reasons = prediction.get("reasons", [])
    if reasons:
        lines.append("## Reasons\n")
        for r in reasons:
            lines.append(f"- {r}")
        lines.append("")

    notes = prediction.get("notes", "")
    if notes:
        lines.append(f"## Notes\n\n{notes}")

    return "\n".join(lines)


def _format_language(language: Any) -> str:
    """Return a display string for profile language entries."""
    if isinstance(language, str):
        return language
    if isinstance(language, dict):
        name = language.get("name") or language.get("language") or ""
        level = language.get("level") or language.get("proficiency") or ""
        if name and level:
            return f"{name} ({level})"
        return str(name or level)
    return str(language)


def _generate_resume(
    profile: dict,
    evidence: list[dict],
    job_data: dict,
) -> tuple[str, list[str]]:
    """Generate a conservative targeted resume using only profile + evidence facts.

    Returns (markdown_text, list_of_warnings) where warnings flag any section
    that may need review.
    """
    facts = derive_candidate_facts(profile, evidence)
    warnings: List[str] = []
    lines: List[str] = []

    # --- Name and contact ---
    lines.append(f"# {facts.name}")
    contact_parts = []
    if facts.location:
        contact_parts.append(facts.location)
    if facts.email:
        contact_parts.append(facts.email)
    if facts.languages:
        contact_parts.append(", ".join(facts.languages))
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    # --- Education ---
    edu_list = facts.education
    if edu_list:
        lines.append("## Education\n")
        for edu in edu_list:
            inst = edu.get("institution", "")
            degree = edu.get("degree", "")
            major = edu.get("major", "")
            grad = edu.get("graduation_date", "")
            gpa = edu.get("gpa", None)
            honors = edu.get("honors", [])
            coursework = edu.get("relevant_coursework", [])
            activities = edu.get("activities", [])

            degree_line = f"**{inst}** -- {degree}, {major}"
            if grad:
                degree_line += f" (Expected {grad})"
            lines.append(degree_line)
            if gpa is not None:
                lines.append(f"GPA: {gpa}")
            if honors:
                lines.append(f"Honors: {', '.join(honors)}")
            if coursework:
                lines.append(f"Relevant Coursework: {', '.join(coursework)}")
            if activities:
                lines.append(f"Activities: {', '.join(activities)}")
            lines.append("")
    else:
        warnings.append("No education data found in profile.")

    # --- Skills ---
    if (
        facts.programming_language_labels
        or facts.framework_labels
        or facts.domain_labels
    ):
        lines.append("## Skills\n")
        if facts.programming_language_labels:
            lines.append(f"**Languages:** {', '.join(facts.programming_language_labels)}")
        if facts.framework_labels:
            lines.append(f"**Frameworks:** {', '.join(facts.framework_labels)}")
        if facts.domain_labels:
            lines.append(f"**Domains:** {', '.join(facts.domain_labels)}")
        lines.append("")

    # --- Projects (from evidence bank) ---
    if evidence:
        lines.append("## Projects\n")
        for entry in evidence:
            title = entry.get("title", "")
            fields = entry.get("fields", "")
            content = entry.get("content", "")
            entry_skills = entry.get("skills", [])

            # Derive slug for evidence marker
            import re as _re
            entry_title_slug = "evidence_bank.md#" + _re.sub(
                r"[^a-z0-9]+", "-", title.lower()
            ).strip("-") if title else "evidence_bank.md"

            lines.append(f"### {title}\n")

            # Render structured fields
            if isinstance(fields, dict):
                for k, v in fields.items():
                    lines.append(f"**{k}:** {v}")
                lines.append("")

            # Render concrete outcomes from content
            # Extract bullet-like lines from content
            concrete_lines = []
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- "):
                    concrete_lines.append(stripped)

            if concrete_lines:
                lines.append("**Key Outcomes:**")
                for bullet in concrete_lines:
                    # Add evidence provenance marker
                    claim_text = bullet[2:] if bullet.startswith("- ") else bullet
                    source = find_evidence_source(claim_text, evidence)
                    if source:
                        lines.append(f"{bullet} <!-- evidence: {source} -->")
                    else:
                        lines.append(f"{bullet} <!-- evidence: {entry_title_slug} -->")
                lines.append("")

            if entry_skills:
                lines.append(f"**Skills:** {', '.join(entry_skills)}")
                lines.append("")
    else:
        warnings.append("No evidence bank entries found. Resume has no project section.")

    # --- Availability ---
    if facts.availability_start or facts.availability_end:
        lines.append("## Availability\n")
        if facts.availability_start and facts.availability_end:
            lines.append(f"Available {facts.availability_start} to {facts.availability_end}")
        elif facts.availability_start:
            lines.append(f"Available from {facts.availability_start}")
        lines.append("")

    # --- Work arrangement ---
    wa = facts.work_arrangement
    if wa:
        if isinstance(wa, dict):
            prefs = []
            if wa.get("open_to_remote"):
                prefs.append("Remote")
            if wa.get("open_to_hybrid"):
                prefs.append("Hybrid")
            if wa.get("open_to_onsite"):
                prefs.append("On-site")
            preferred = wa.get("preferred", "")
            if prefs:
                lines.append(f"**Work Arrangement:** {' / '.join(prefs)}" +
                             (f" (preferred: {preferred})" if preferred else ""))
        else:
            lines.append(f"**Work Arrangement:** {wa}")

    resume_text = "\n".join(lines)
    return resume_text, warnings


def _generate_greeting(job_data: dict, profile: dict, evidence: list[dict]) -> str:
    """Greeting message derived entirely from profile and evidence bank."""
    facts = derive_candidate_facts(profile, evidence)
    company = job_data.get("company", "")
    title = job_data.get("title", "open position")

    # Build greeting from derived data
    lines = [f"Hello! I'm {facts.first_name}"]
    if facts.study and facts.school:
        lines[0] += f", a {facts.study} student at {facts.school}"
    elif facts.school:
        lines[0] += f", a student at {facts.school}"
    if facts.graduation_date:
        lines[0] += f" (expected graduation {facts.graduation_date})"
    lines[0] += f". I'm very interested in the {title} role at {company}."

    # Evidence-based experience summary
    if evidence:
        project_names = facts.project_names[:3]
        if project_names:
            lines.append(
                f"\nRelevant evidence includes: {', '.join(project_names)}."
            )
    elif facts.programming_languages:
        lines.append(
            f"\nTechnical focus: {', '.join(facts.programming_languages[:3])}."
        )

    if facts.availability_start:
        lines.append(f"\nI'm available starting {facts.availability_start} and am excited about the opportunity to contribute to your team.")
    else:
        lines.append("\nI'm excited about the opportunity to contribute to your team.")

    lines.append("Looking forward to hearing from you!")

    return "\n".join(lines)


def _generate_cover_letter(job_data: dict, profile: dict, evidence: list[dict]) -> str:
    """Short cover letter — every claim derived from profile or evidence bank."""
    facts = derive_candidate_facts(profile, evidence)
    company = job_data.get("company", "your company")
    title = job_data.get("title", "the open position")

    highlights = evidence[:2] if evidence else []

    lines = [f"Dear Hiring Team,\n"]

    # Intro — derive degree/major from profile, never hardcode
    if facts.study and facts.school:
        lines.append(
            f"I am writing to express my interest in the {title} position at {company}. "
            f"As a {facts.study} student at {facts.school}, I bring a strong foundation in "
            f"technical problem-solving.\n"
        )
    elif facts.school:
        lines.append(
            f"I am writing to express my interest in the {title} position at {company}. "
            f"As a student at {facts.school}, I bring relevant technical experience.\n"
        )
    else:
        lines.append(
            f"I am writing to express my interest in the {title} position at {company}. "
            f"I bring relevant technical experience and a strong work ethic.\n"
        )

    if highlights:
        lines.append("Here are projects that demonstrate my relevant experience:\n")
        for entry in highlights:
            title_e = entry.get("title", "A project")
            fields = entry.get("fields", {})
            tech = fields.get("Tech", "") if isinstance(fields, dict) else ""
            content = entry.get("content", "")

            outcome = ""
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- "):
                    outcome = stripped[2:]
                    break

            bullet = f"- **{title_e}**"
            if tech:
                bullet += f" ({tech})"
            if outcome:
                bullet += f": {outcome}"
            lines.append(bullet)
        lines.append("")

    # Availability — from profile only
    if facts.availability_start:
        lines.append(f"I am available starting {facts.availability_start} and eager to contribute to your team.\n")
    else:
        lines.append("I am eager to contribute to your team.\n")

    lines.append("Thank you for your consideration.\n")
    lines.append(f"Best regards,\n{facts.name}")

    return "\n".join(lines)


def _generate_form_answers(job_data: dict, profile: dict, evidence: list[dict]) -> str:
    """Common form Q&A — every answer derived from profile and evidence bank."""
    facts = derive_candidate_facts(profile, evidence)
    company = job_data.get("company", "")
    title = job_data.get("title", "")

    lines = ["# Form Answers\n"]

    # Q: Why this company?
    lines.append(f"**Q: Why {company}?**")
    lines.append(
        f"A: I'm drawn to {company}'s work and believe the {title} role aligns well "
        f"with my technical background.\n"
    )

    # Q: Why this role?
    lines.append(f"**Q: Why this role?**")
    all_skills = facts.programming_languages + facts.frameworks
    skill_str = ", ".join(all_skills[:4]) if all_skills else "relevant technologies"
    lines.append(
        f"A: The {title} position matches my skills in {skill_str} "
        f"and offers an opportunity to apply what I've learned.\n"
    )

    # Q: Tell us about yourself — derive from profile + evidence, never hardcode
    lines.append("**Q: Tell us about yourself.**")
    intro = f"A: I'm"
    if facts.study and facts.school:
        intro += f" a {facts.study} student at {facts.school}"
    elif facts.school:
        intro += f" a student at {facts.school}"
    else:
        intro += " a motivated student"
    intro += f" (expected {facts.graduation_date})" if facts.graduation_date else ""
    intro += f" with a {facts.gpa} GPA." if facts.gpa else "."

    if facts.project_names:
        intro += f" I've worked on projects including {', '.join(facts.project_names[:3])}."
    intro += "\n"
    lines.append(intro)

    # Q: Availability — from profile only
    lines.append("**Q: When are you available?**")
    if facts.availability_start:
        end_str = facts.availability_end or "the end of the internship window"
        dpw = f", {facts.days_per_week} days/week" if facts.days_per_week else ""
        lines.append(f"A: I'm available from {facts.availability_start} to {end_str}{dpw}.\n")
    else:
        lines.append("A: Please see my profile for availability details.\n")

    # Q: Work arrangement preference
    lines.append("**Q: Preferred work arrangement?**")
    if facts.work_preference:
        lines.append(f"A: I prefer {facts.work_preference} but am open to other arrangements.\n")
    else:
        lines.append("A: TODO: Confirm work arrangement preference before submitting.\n")

    # Q: Location
    lines.append("**Q: Current location / willing to relocate?**")
    if facts.location and facts.target_locations:
        lines.append(f"A: Currently based in {facts.location}. Willing to relocate to {', '.join(facts.target_locations)}.\n")
    elif facts.location:
        lines.append(f"A: Based in {facts.location}.\n")
    else:
        lines.append("A: Please see my profile for location details.\n")

    # Q: Notice period
    lines.append("**Q: How much notice do you need?**")
    notice = None
    for c in facts.constraints:
        if "notice" in c.lower():
            notice = c
            break
    if notice:
        lines.append(f"A: {notice}\n")
    else:
        lines.append("A: TODO: Confirm notice period before submitting.\n")

    return "\n".join(lines)


def _generate_submit_checklist(job_data: dict, prediction: dict) -> str:
    """Submission checklist requiring human confirmation."""
    company = job_data.get("company", "Unknown")
    title = job_data.get("title", "Unknown")
    decision = prediction.get("decision", "skip")
    final_score = prediction.get("final_score", 0.0)
    url = job_data.get("apply_url", "")

    lines = [
        "# Submit Checklist\n",
        f"**Job:** {title} at {company}",
        f"**Prediction Decision:** {decision.upper()} (score: {final_score:.1f}/10)",
        "",
        "---",
        "",
        "## Pre-Submit Review (HUMAN CONFIRMATION REQUIRED)\n",
        "Do NOT submit until every item below is checked:\n",
        "- [ ] I have reviewed `resume_targeted.md` and confirmed all claims are accurate",
        "- [ ] I have reviewed `cover_letter.md` and it reads naturally",
        "- [ ] I have reviewed `greeting.md` if using a platform messaging feature",
        "- [ ] I have reviewed `form_answers.md` for accuracy",
        "- [ ] I have verified the application URL is correct and accessible",
        "- [ ] I have checked for any platform-specific requirements (file format, size limits)",
        "- [ ] I understand this is a real submission and accept responsibility",
        "",
    ]

    if url:
        lines.append(f"**Application URL:** {url}")
        lines.append("")

    # Decision-specific warnings
    if decision == "skip":
        lines.append(
            "> **WARNING:** The prediction recommends SKIP for this role (score < 3.0). "
            "> Proceed only if you have additional context not captured in the prediction.\n"
        )
    elif decision == "save_for_later":
        lines.append(
            "> **NOTE:** The prediction recommends SAVE FOR LATER (score 3.0-5.0). "
            "> Consider whether the timing or your interest level has changed.\n"
        )

    lines.append("---\n")
    lines.append(
        "Once all items are checked, run:\n"
        "```\n"
        f"job mark-submitted --job {job_data.get('job_id', '<job_id>')} --channel <manual/channel>\n"
        "```\n"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pack(
    job_data: dict,
    prediction: dict,
    profile: dict,
    evidence: list[dict],
) -> ApplicationPack:
    """Create an ApplicationPack with all generated markdown files.

    Args:
        job_data: Job dict (from Job.to_dict() or raw import).
        prediction: Prediction dict (from Prediction.to_dict()).
        profile: Merged profile dict (from load_profile()).
        evidence: Evidence bank entries (from load_evidence_bank()).

    Returns:
        ApplicationPack with files dict mapping filename -> markdown content.
    """
    job_id = job_data.get("job_id", "unknown")

    jd_md = _generate_jd(job_data)
    pred_md = _generate_prediction_summary(prediction)
    resume_md, resume_warnings = _generate_resume(profile, evidence, job_data)
    greeting_md = _generate_greeting(job_data, profile, evidence)
    cover_md = _generate_cover_letter(job_data, profile, evidence)
    forms_md = _generate_form_answers(job_data, profile, evidence)
    checklist_md = _generate_submit_checklist(job_data, prediction)

    # Append resume warnings as a header if any
    if resume_warnings:
        warning_header = (
            "> **Resume Warnings (review before submission):**\n"
            + "\n".join(f"> - {w}" for w in resume_warnings)
            + "\n\n---\n\n"
        )
        resume_md = warning_header + resume_md

    files = {
        "jd.md": jd_md,
        "prediction.md": pred_md,
        "resume_targeted.md": resume_md,
        "greeting.md": greeting_md,
        "cover_letter.md": cover_md,
        "form_answers.md": forms_md,
        "submit_checklist.md": checklist_md,
    }

    return ApplicationPack(job_id=job_id, files=files)


def validate_pack(pack: ApplicationPack, evidence: list[dict]) -> List[str]:
    """Validate that all factual claims in the pack are supported by evidence.

    Checks resume_targeted.md for claims not traceable to the evidence bank.
    Returns a list of warning strings. Empty list means all claims are supported.

    This is a heuristic check — it flags text that appears novel relative to
    the evidence corpus. False positives are possible; the goal is to catch
    fabricated or hallucinated content before submission.
    """
    warnings: List[str] = []
    corpus = _build_evidence_corpus(evidence)

    resume_text = pack.files.get("resume_targeted.md", "")
    if not resume_text:
        warnings.append("resume_targeted.md is empty or missing.")
        return warnings

    # Split resume into sections and check each bullet/claim
    current_section = ""
    for line in resume_text.split("\n"):
        stripped = line.strip()

        # Track current section
        if stripped.startswith("#"):
            current_section = stripped.lstrip("#").strip()
            continue

        # Skip non-claim lines
        if not stripped or stripped.startswith(">") or stripped.startswith("---"):
            continue
        if stripped.startswith("**") and ":" in stripped and not stripped.startswith("- "):
            # This is a field header like "**Languages:** Python, JS" — check the values
            colon_idx = stripped.index(":")
            value_part = stripped[colon_idx + 1:].strip().rstrip("*").strip()
            if value_part and not _evidence_supports_claim(value_part, corpus):
                warnings.append(
                    f"[{current_section}] Unsupported claim in field: {stripped}"
                )
            continue

        # Check bullet points (project outcomes, etc.)
        if stripped.startswith("- "):
            claim = stripped[2:]
            # Skip meta-lines that are just formatting
            if claim.startswith("[") or claim.startswith("Available") or claim.startswith("Open to"):
                continue
            if not _evidence_supports_claim(claim, corpus):
                warnings.append(
                    f"[{current_section}] Potentially unsupported claim: {claim}"
                )

    # Also check cover letter for unsupported claims
    cover_text = pack.files.get("cover_letter.md", "")
    if cover_text:
        for line in cover_text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- **"):
                # Bullet in cover letter referencing a project
                if not _evidence_supports_claim(stripped, corpus):
                    warnings.append(
                        f"[cover_letter.md] Potentially unsupported claim: {stripped}"
                    )

    # Check greeting for unsupported claims
    greeting_text = pack.files.get("greeting.md", "")
    if greeting_text:
        # Greeting mentions skills and projects — check key claims
        for line in greeting_text.split("\n"):
            stripped = line.strip()
            if "hands-on experience" in stripped.lower() or "built" in stripped.lower():
                if not _evidence_supports_claim(stripped, corpus):
                    warnings.append(
                        f"[greeting.md] Potentially unsupported claim: {stripped}"
                    )

    return warnings


# ---------------------------------------------------------------------------
# Convenience: full pipeline from base_dir
# ---------------------------------------------------------------------------

def generate_pack_from_dir(
    job_data: dict,
    prediction: dict,
    base_dir: str,
) -> tuple[ApplicationPack, List[str]]:
    """Generate pack and validate it in one call.

    Args:
        job_data: Job dict.
        prediction: Prediction dict.
        base_dir: Path to project root (contains profile/ directory).

    Returns:
        (pack, warnings) where warnings is the output of validate_pack().
    """
    profile = load_profile(base_dir)
    evidence = load_evidence_bank(base_dir)

    pack = generate_pack(job_data, prediction, profile, evidence)
    warnings = validate_pack(pack, evidence)

    return pack, warnings


def generate_workspace_pack(state_dir: str | Path, job_id: str) -> WorkspacePackResult:
    """Generate, validate, save, and mark an application pack for a workspace job."""
    from .application_pack import workspace_pack_sources, write_application_pack
    from .pipeline import PipelineTransitionError, transition_job
    from .predictor import load_prediction
    from .workspace import (
        application_dir,
        jobs_normalized_dir,
        load_state,
        predictions_dir,
        save_state,
    )

    state = load_state(state_dir)
    if job_id not in state["jobs"]:
        raise PackInputError(f"Job {job_id} not found.")

    job_entry = state["jobs"][job_id]
    job_yaml = jobs_normalized_dir(state_dir) / f"{job_id}.yaml"
    if job_yaml.exists():
        job_data = yaml.safe_load(job_yaml.read_text(encoding="utf-8")) or {}
    else:
        job_data = {"job_id": job_id, **job_entry}

    profile = load_profile(state_dir)
    profile_errors = validate_profile_consistency(profile)
    if profile_errors:
        raise PackInputError(
            "Profile identity conflict: " + "; ".join(profile_errors)
        )
    try:
        transition_job(job_entry, "packed")
    except PipelineTransitionError as exc:
        raise PackInputError(str(exc)) from exc
    job_entry.pop("validation", None)

    try:
        prediction = load_prediction(job_id, predictions_dir(state_dir))
    except FileNotFoundError as exc:
        raise PackInputError(
            f"No prediction for {job_id}. Run `job predict` first."
        ) from exc

    evidence = load_evidence_bank(state_dir)
    pack = generate_pack(job_data, prediction.to_dict(), profile, evidence)
    report = generate_evidence_report(
        pack.files,
        evidence,
        job_data,
        profile_data=profile,
    )
    warnings = [
        f"[{item['file']}] Unsupported claim: {item['claim']}"
        for item in report["unsupported"]
    ]
    warnings.extend(
        f"Weak claim: {item['claim']} ({item['reason']})"
        for item in report["weak"]
    )

    pack_dir = application_dir(state_dir, job_id)
    write_application_pack(
        pack_dir,
        pack,
        sources=workspace_pack_sources(state_dir, job_id),
    )

    job_entry["pack_warnings"] = warnings
    save_state(state_dir, state)

    return WorkspacePackResult(pack=pack, warnings=warnings, pack_dir=pack_dir)
