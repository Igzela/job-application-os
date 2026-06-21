"""BOSS Zhipin adapter -- Python wrapper for the CDP-based Node.js scraper.

Calls read-boss.mjs via subprocess, parses JSON output, returns structured
job data. Prerequisites: Node.js 22+, Chrome running with --remote-debugging-port,
user logged into BOSS Zhipin.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .boss_parser import classify_boss_page, extract_boss_job_list
from .workspace import jobs_raw_dir, load_state, save_state

ADAPTER_DIR = Path(__file__).resolve().parent / "adapters" / "boss"
SCRIPT_PATH = ADAPTER_DIR / "read-boss.mjs"


@dataclass(frozen=True)
class BossWorkspaceImportResult:
    jobs: list[dict]
    job_ids: list[str]

    @property
    def imported(self) -> int:
        return len(self.job_ids)


def import_from_boss(
    keyword: str,
    city_code: str = "100010000",
    port: int = 9222,
    use_scrapling: bool | None = True,
    record_diagnostics: bool | None = True,
    include_html_snapshot: bool = True,
    html_snapshot_limit: int = 250000,
    adaptive: bool = True,
    adaptive_store: str = "~/.jobos/scrapling.db",
    adaptive_percentage: int = 40,
) -> list[dict]:
    """Import jobs from BOSS Zhipin via CDP adapter.

    Prerequisites: Chrome running with --remote-debugging-port=9222, user
    logged into BOSS Zhipin.

    Returns list of job dicts with: title, company, salary, tags, link.
    """
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "Node.js not found. Install Node.js 22+ to use the BOSS adapter."
        )

    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(
            f"Adapter script not found: {SCRIPT_PATH}. "
            "Expected jobos/adapters/boss/read-boss.mjs"
        )

    cmd = [node, str(SCRIPT_PATH), keyword, city_code, str(port)]
    env = os.environ.copy()
    env["JOBOS_BOSS_INCLUDE_HTML"] = "1" if include_html_snapshot else "0"
    env["JOBOS_BOSS_HTML_LIMIT"] = str(html_snapshot_limit)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "BOSS adapter timed out (30s). Chrome may be unresponsive "
            "or the page took too long to load."
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "Cannot connect to Chrome debug port" in stderr:
            raise ConnectionError(
                f"Cannot connect to Chrome on port {port}. "
                "Start Chrome with: bash jobos/adapters/boss/launch-chrome.sh"
            )
        raise RuntimeError(f"BOSS adapter failed (exit {result.returncode}): {stderr}")

    stdout = result.stdout.strip()
    if not stdout:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"BOSS adapter returned invalid JSON: {e}\nOutput: {stdout[:500]}"
        )

    if not isinstance(data, dict) or "items" not in data:
        raise RuntimeError(
            f"BOSS adapter returned unexpected structure: {type(data)}"
        )

    if use_scrapling is None:
        extraction_config = _load_extraction_config()
        use_scrapling = extraction_config.get("use_scrapling", True)
    if record_diagnostics is None:
        extraction_config = _load_extraction_config()
        record_diagnostics = extraction_config.get("record_diagnostics", True)

    diagnostics = data.get("diagnostics", {})
    html = data.get("html") or ""
    if html:
        classification = classify_boss_page(
            html,
            url=data.get("url", ""),
            title=data.get("title", ""),
        )
        if classification.state == "verification_required":
            raise PermissionError(
                f"BOSS security verification: {classification.reason}"
            )
        if classification.state == "login_required":
            raise PermissionError(f"BOSS login required: {classification.reason}")
        if classification.state == "access_limited":
            raise PermissionError(f"BOSS access limited: {classification.reason}")

    if diagnostics.get("blocked"):
        raise PermissionError(
            f"BOSS security verification: {diagnostics['blocked']}"
        )
    if diagnostics.get("maybeNeedLogin"):
        raise PermissionError(
            f"BOSS login required: {diagnostics['maybeNeedLogin']}"
        )
    if diagnostics.get("accessLimited"):
        raise PermissionError(
            f"BOSS access limited: {diagnostics['accessLimited']}"
        )

    extraction = None
    if html:
        extraction = extract_boss_job_list(
            html,
            url=data.get("url", ""),
            title=data.get("title", ""),
            use_scrapling=use_scrapling,
            adaptive=adaptive,
            adaptive_store=adaptive_store,
            adaptive_percentage=adaptive_percentage,
        )
        items = [
            {
                "title": job.title,
                "company": job.company,
                "salary": job.salary,
                "tags": job.tags,
                "link": job.url,
            }
            for job in extraction.jobs
        ]
    else:
        items = data.get("items", [])

    if not items and not html:
        classification = None
    elif extraction is not None:
        classification = extraction.classification
    else:
        classification = None

    jobs = []
    for item in items:
        job = {
            "title": item.get("title", ""),
            "company": item.get("company", ""),
            "salary": item.get("salary", ""),
            "tags": item.get("tags", []),
            "link": item.get("link", ""),
            "source": "boss_zhipin",
            "keyword": keyword,
            "city_code": city_code,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        }
        if record_diagnostics:
            job.update(_diagnostic_fields(extraction, diagnostics, classification))
        jobs.append(job)

    return jobs


def import_boss_jobs_to_workspace(
    state_dir: str | Path,
    keyword: str,
    city_code: str = "100010000",
    port: int = 9222,
    *,
    use_scrapling: bool | None = True,
    record_diagnostics: bool | None = True,
    include_html_snapshot: bool = True,
    html_snapshot_limit: int = 250000,
    adaptive: bool = True,
    adaptive_store: str = "~/.jobos/scrapling.db",
    adaptive_percentage: int = 40,
) -> BossWorkspaceImportResult:
    """Import BOSS jobs and persist raw JSON plus state entries."""
    jobs = import_from_boss(
        keyword,
        city_code,
        port,
        use_scrapling=use_scrapling,
        record_diagnostics=record_diagnostics,
        include_html_snapshot=include_html_snapshot,
        html_snapshot_limit=html_snapshot_limit,
        adaptive=adaptive,
        adaptive_store=adaptive_store,
        adaptive_percentage=adaptive_percentage,
    )
    if not jobs:
        return BossWorkspaceImportResult(jobs=[], job_ids=[])

    raw_dir = jobs_raw_dir(state_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    state = load_state(state_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job_ids: list[str] = []

    for i, job in enumerate(jobs):
        slug = re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-")[:40]
        job_id = f"{ts}-boss-{i:03d}-{slug}"
        raw_path = raw_dir / f"{job_id}.json"
        raw_path.write_text(
            json.dumps(job, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        state["jobs"][job_id] = {
            "title": job["title"],
            "company": job["company"],
            "location": job.get("city_code", city_code),
            "status": "imported",
            "captured_at": job.get("imported_at", ""),
            "source": "boss_zhipin",
            "keyword": keyword,
            "link": job.get("link", ""),
        }
        if job.get("extractor"):
            state["jobs"][job_id]["extractor"] = job["extractor"]
        if job.get("page_state"):
            state["jobs"][job_id]["page_state"] = job["page_state"]
        if job.get("extraction_diagnostics"):
            state["jobs"][job_id]["extraction_diagnostics"] = job[
                "extraction_diagnostics"
            ]
        job_ids.append(job_id)

    save_state(state_dir, state)
    return BossWorkspaceImportResult(jobs=jobs, job_ids=job_ids)


def _load_extraction_config() -> dict[str, Any]:
    try:
        from .config import load_config

        return load_config().get("extraction", {})
    except Exception:
        return {}


def _diagnostic_fields(extraction, node_diagnostics: dict, classification) -> dict[str, Any]:
    if extraction is None:
        page_state = node_diagnostics.get("pageState") or "normal"
        return {
            "extractor": "node_cdp",
            "page_state": page_state,
            "extraction_diagnostics": {
                "extractor": "node_cdp",
                "page_state": page_state,
                "item_count": node_diagnostics.get("cardCount"),
                "node_diagnostics": node_diagnostics,
            },
        }

    data = extraction.diagnostics.to_dict()
    data["classification"] = extraction.classification.to_dict()
    if node_diagnostics:
        data["node_diagnostics"] = node_diagnostics
    return {
        "extractor": extraction.diagnostics.extractor,
        "page_state": extraction.classification.state,
        "extraction_diagnostics": data,
    }
