import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yaml


def import_job(file_path: str, jobs_dir: str) -> dict:
    """Read a text/markdown job description, extract structured fields,
    write normalized YAML, and return the job data dict."""

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    return import_job_text(content, jobs_dir, source_file=os.path.basename(file_path))


def import_job_text(content: str, jobs_dir: str | Path, *, source_file: str = "stdin") -> dict:
    """Import raw job description text into normalized YAML."""
    if not content.strip():
        raise ValueError("No job description text")

    title = _extract_field(content, r"(?:^|\n)#+\s*(.+)") or "Unknown Title"
    company = _extract_field(
        content, r"(?:company|employer|organi[sz]ation)\s*[:\-]\s*(.+)", re.IGNORECASE
    ) or "Unknown Company"
    location = _extract_field(
        content, r"(?:location|based in|office)\s*[:\-]\s*(.+)", re.IGNORECASE
    ) or "Unknown"
    skills = _extract_list(
        content,
        r"(?:skills?|technologies?|requirements?|qualifications?)\s*[:\-]\s*(.+)",
        re.IGNORECASE,
    )

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    job_id = f"{ts}-{slug}"

    job_data = {
        "job_id": job_id,
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "skills": skills,
        "source_file": source_file,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "raw_content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
    }

    os.makedirs(jobs_dir, exist_ok=True)
    out_path = os.path.join(jobs_dir, f"{job_id}.yaml")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(job_data, f, default_flow_style=False, sort_keys=False)

    return job_data


def import_pasted_job(state_dir: str | Path, jd_text: str) -> dict:
    """Import pasted JD text and update workspace state."""
    from .workspace import jobs_normalized_dir, load_state, save_state

    state_dir = Path(state_dir)
    data = import_job_text(jd_text, jobs_normalized_dir(state_dir), source_file="stdin")
    state = load_state(state_dir)
    state["jobs"][data["job_id"]] = {
        "title": data["title"],
        "company": data["company"],
        "location": data.get("location", ""),
        "status": "imported",
        "captured_at": data.get("imported_at", ""),
        "source_file": "stdin",
    }
    save_state(state_dir, state)
    return data


def _extract_field(text: str, pattern: str, flags=0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _extract_list(text: str, pattern: str, flags=0) -> list[str]:
    m = re.search(pattern, text, flags)
    if not m:
        return []
    raw = m.group(1)
    items = re.split(r"[,;]\s*", raw)
    return [item.strip().strip("*- ") for item in items if item.strip()]
