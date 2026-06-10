"""Dry-run form filler for local testing.

Loads a local mock HTML form, fills fields using pack data, captures what
would be submitted as a log dict.  Never submits anything over the network.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .models import ApplicationPack

logger = logging.getLogger(__name__)

# Default mock form lives next to this package
_DEFAULT_FORM = Path(__file__).resolve().parent / "adapters" / "local_mock_form" / "application_form.html"


def _build_field_mapping(pack: ApplicationPack) -> Dict[str, str]:
    """Derive a flat field_name -> value mapping from pack metadata.

    The mapping is intentionally heuristic: it looks for well-known keys in
    pack.files (where values are file content strings) and in extra metadata
    keys that callers may attach.  Unknown keys are ignored gracefully.
    """
    mapping: Dict[str, str] = {}

    # Try to pull structured metadata that callers commonly attach.
    # These are not part of the dataclass schema but callers may stash them
    # in pack.files under special sentinel keys or pass them separately.
    meta = pack.files.get("_meta", None)

    # Common direct mappings (pack.files keys -> form field names).
    # The "files" dict maps filename -> content; we also support a special
    # "_field_overrides" dict for explicit form-field overrides.
    overrides: Dict[str, str] = pack.files.get("_field_overrides", {})  # type: ignore[assignment]

    # Default sample values so the mock form is always filled
    defaults: Dict[str, str] = {
        "first_name": "Jordan",
        "last_name": "Mitchell",
        "email": "jordan.mitchell@university.edu",
        "phone": "(555) 234-8901",
        "linkedin": "https://linkedin.com/in/jordanmitchell",
        "github": "https://github.com/jmitchell-dev",
        "location": "Boston, MA",
        "university": "Northeastern University",
        "degree": "B.S.",
        "major": "Computer Science",
        "gpa": "3.72 / 4.0",
        "graduation_date": "May 2027",
        "coursework": "Data Structures, Algorithms, Operating Systems, Database Systems, Machine Learning, Software Engineering, Computer Networks",
        "experience": (
            "Software Engineering Intern at DataFlow Analytics (Summer 2025): "
            "Built internal dashboard with React/TypeScript for 12 microservices. "
            "Automated API data ingestion with Python, saving 8 hrs/week. "
            "Teaching Assistant for CS 2100 Algorithms since Jan 2025."
        ),
        "skills": "Python, Java, C++, JavaScript, TypeScript, SQL, React, Node.js, Flask, Spring Boot, PyTorch, Git, Docker, PostgreSQL, MongoDB, AWS",
        "position_title": "",
        "company_name": "",
        "how_heard": "linkedin",
        "work_authorization": "opt",
        "cover_letter": "",
        "additional_notes": "",
        "start_date": "Summer 2026",
        "salary_expectation": "",
    }

    # Layer: defaults < overrides
    mapping.update(defaults)
    mapping.update(overrides)

    # Fill position/company from pack metadata if available
    if meta and isinstance(meta, dict):
        if "position_title" in meta:
            mapping["position_title"] = meta["position_title"]
        if "company_name" in meta:
            mapping["company_name"] = meta["company_name"]
        if "cover_letter" in meta:
            mapping["cover_letter"] = meta["cover_letter"]
        if "salary_expectation" in meta:
            mapping["salary_expectation"] = meta["salary_expectation"]

    # If cover_letter file exists in pack, use its content
    if "cover_letter.txt" in pack.files:
        mapping["cover_letter"] = pack.files["cover_letter.txt"]
    if "cover_letter.md" in pack.files:
        mapping["cover_letter"] = pack.files["cover_letter.md"]

    # Use pack.job_id as a hint for position_title if still empty
    if not mapping.get("position_title") and pack.job_id:
        mapping["position_title"] = pack.job_id

    return mapping


def _fill_form(html: str, field_values: Dict[str, str]) -> tuple[str, Dict[str, str]]:
    """Fill form fields in *html* with *field_values*.  Return (filled_html, filled_fields).

    Only <input>, <textarea>, and <select> elements whose ``name`` appears in
    *field_values* are touched.  Returns a dict of {name: value} for every
    field that was actually filled.
    """
    soup = BeautifulSoup(html, "html.parser")
    filled: Dict[str, str] = {}

    # Inputs (text, email, tel, url, hidden, etc.)
    for tag in soup.find_all("input"):
        name = tag.get("name")
        if name and name in field_values:
            tag["value"] = field_values[name]
            filled[name] = field_values[name]

    # Textareas
    for tag in soup.find_all("textarea"):
        name = tag.get("name")
        if name and name in field_values:
            tag.string = field_values[name]
            filled[name] = field_values[name]

    # Selects
    for tag in soup.find_all("select"):
        name = tag.get("name")
        if name and name in field_values:
            value = field_values[name]
            # Mark the matching <option> as selected
            for option in tag.find_all("option"):
                if option.get("value") == value:
                    option["selected"] = "selected"
                elif "selected" in option.attrs:
                    del option["selected"]
            filled[name] = value

    return str(soup), filled


def _build_submission_log(filled_fields: Dict[str, str], pack: ApplicationPack) -> str:
    """Build a human-readable log of what *would* be submitted."""
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines = [
        f"=== DRY RUN SUBMISSION LOG ===",
        f"Timestamp : {timestamp}",
        f"Job ID    : {pack.job_id}",
        f"Pack created: {pack.created_at}",
        f"Fields filled: {len(filled_fields)}",
        "",
        "--- Field Values ---",
    ]
    for name, value in sorted(filled_fields.items()):
        preview = value if len(value) <= 120 else value[:117] + "..."
        lines.append(f"  {name}: {preview}")

    lines.append("")
    lines.append("--- Pack Files ---")
    for fname, content in pack.files.items():
        if fname.startswith("_"):
            continue  # skip internal sentinel keys
        size = len(content)
        lines.append(f"  {fname} ({size} chars)")

    lines.append("")
    lines.append("=== END DRY RUN ===")
    return "\n".join(lines)


def run_dry_run(
    job_id: str,
    pack: ApplicationPack,
    mock_form_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Load a local mock HTML form, fill fields from *pack*, return a report.

    This function never submits anything.  It parses the mock form, fills
    every recognisable field, and returns a dict describing what *would* have
    been submitted.

    Parameters
    ----------
    job_id:
        The job identifier (used for logging; must match pack.job_id or the
        pack value takes precedence).
    pack:
        An :class:`ApplicationPack` whose ``files`` dict supplies field
        values.  Special keys ``_field_overrides`` (dict of name->value) and
        ``_meta`` (dict with ``position_title``, ``company_name``, etc.) are
        recognised.
    mock_form_path:
        Path to the HTML form file.  Defaults to
        ``adapters/local_mock_form/application_form.html`` shipped with this
        package.

    Returns
    -------
    dict
        ``fields_filled``  -- dict of {field_name: value} for every field that
                              was populated.
        ``log``            -- human-readable submission log string.
        ``screenshot_note``-- note explaining no screenshot was taken (dry run).
    """
    form_path = Path(mock_form_path) if mock_form_path else _DEFAULT_FORM

    if not form_path.exists():
        raise FileNotFoundError(
            f"Mock form not found at {form_path}. "
            "Provide a valid mock_form_path or create the default form."
        )

    html = form_path.read_text(encoding="utf-8")
    field_values = _build_field_mapping(pack)

    filled_html, filled_fields = _fill_form(html, field_values)

    # Log any form fields we did NOT fill (informational)
    soup = BeautifulSoup(html, "html.parser")
    all_names: List[str] = []
    for tag in soup.find_all(["input", "textarea", "select"]):
        n = tag.get("name")
        if n and not n.startswith("_"):
            all_names.append(n)
    unfilled = sorted(set(all_names) - set(filled_fields))
    if unfilled:
        logger.info("Unfilled form fields: %s", ", ".join(unfilled))

    log = _build_submission_log(filled_fields, pack)

    return {
        "fields_filled": filled_fields,
        "log": log,
        "screenshot_note": (
            "Dry-run mode: no screenshot captured. "
            "In production, a screenshot of the filled form would be taken "
            "before submission."
        ),
    }
