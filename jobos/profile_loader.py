"""Load and merge profile YAML files and evidence bank from the profile/ directory."""

import re
from pathlib import Path

import yaml


_PROFILE_FILES = ("base.yaml", "education.yaml", "skills.yaml", "availability.yaml")


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
