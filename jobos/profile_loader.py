"""Load and merge profile YAML files and evidence bank from the profile/ directory."""

import re
from pathlib import Path

import yaml


_PROFILE_FILES = ("base.yaml", "education.yaml", "skills.yaml", "availability.yaml")


def _normalized_identity(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _year(value: object) -> str:
    match = re.search(r"\b(19|20)\d{2}\b", str(value or ""))
    return match.group(0) if match else ""


def validate_profile_consistency(profile: dict) -> list[str]:
    """Return conflicts between base identity fields and primary education."""
    education = profile.get("education")
    if not isinstance(education, list) or not education:
        return []
    primary = education[0]
    if not isinstance(primary, dict):
        return ["education[0] must be an object"]

    errors: list[str] = []
    pairs = (
        ("school", profile.get("school"), primary.get("institution")),
        ("major", profile.get("major"), primary.get("major")),
    )
    for label, base_value, education_value in pairs:
        base_normalized = _normalized_identity(base_value)
        education_normalized = _normalized_identity(education_value)
        if (
            base_normalized
            and education_normalized
            and base_normalized != education_normalized
        ):
            errors.append(
                f"{label} conflicts: {base_value!s} != {education_value!s}"
            )

    base_year = _year(profile.get("graduation_date"))
    education_year = _year(primary.get("graduation_date"))
    if base_year and education_year and base_year != education_year:
        errors.append(
            "graduation year conflicts: "
            f"{base_year} != {education_year}"
        )
    return errors


def load_profile(base_dir: str | Path) -> dict:
    """Merge base.yaml, education.yaml, skills.yaml, availability.yaml into one dict.

    Files are merged in order listed above.  Later keys overwrite earlier ones
    at the top level; nested dicts are merged recursively so partial overrides
    work as expected.
    """
    base_dir = Path(base_dir)
    profile_dir = base_dir / "profile"
    merged: dict = {}

    for name in _PROFILE_FILES:
        path = profile_dir / name
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            continue
        _deep_merge(merged, data)

    return merged


def load_evidence_bank(base_dir: str | Path) -> list[dict]:
    """Parse evidence_bank.md into a list of evidence entry dicts.

    Each entry has:
        - title: section heading text (e.g. "Project 1: DeepSeek Boss Helper")
        - fields: dict of bold-label fields (Type, Repo, Tech, Role, etc.)
        - content: full markdown body of the section
    """
    base_dir = Path(base_dir)
    path = base_dir / "profile" / "evidence_bank.md"
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    entries: list[dict] = []

    # Split on H2 headings (## ...)
    sections = re.split(r"^## ", text, flags=re.MULTILINE)

    for section in sections[1:]:  # skip preamble before first ##
        lines = section.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""

        # Parse bold-label fields at the top of the body
        fields: dict[str, str] = {}
        content_lines: list[str] = []
        in_header = True
        for line in body.split("\n"):
            if in_header and re.match(r"^\*\*[^*]+\*\*:", line):
                m = re.match(r"^\*\*([^*]+)\*\*:\s*(.*)", line)
                if m:
                    fields[m.group(1).strip()] = m.group(2).strip()
            else:
                in_header = False
                content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Extract skills from inline code in the "Skills demonstrated" line
        skills: list[str] = []
        skills_match = re.search(r"Skills demonstrated.*?$", content, re.MULTILINE)
        if skills_match:
            tail = content[skills_match.start():]
            skills = re.findall(r"`([^`]+)`", tail)

        entry: dict = {
            "title": heading,
            "fields": fields,
            "content": content,
        }
        if skills:
            entry["skills"] = skills
        entries.append(entry)

    return entries


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (mutates base, returns it)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base
