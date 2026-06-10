import os
import re
import hashlib
from datetime import datetime, timezone

import yaml


def import_job(file_path: str, jobs_dir: str) -> dict:
    """Read a text/markdown job description, extract structured fields,
    write normalized YAML, and return the job data dict."""

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

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
        "source_file": os.path.basename(file_path),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "raw_content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
    }

    os.makedirs(jobs_dir, exist_ok=True)
    out_path = os.path.join(jobs_dir, f"{job_id}.yaml")
    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(job_data, f, default_flow_style=False, sort_keys=False)

    return job_data


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
