"""BOSS Zhipin adapter -- Python wrapper for the CDP-based Node.js scraper.

Calls read-boss.mjs via subprocess, parses JSON output, returns structured
job data. Prerequisites: Node.js 22+, Chrome running with --remote-debugging-port,
user logged into BOSS Zhipin.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .boss_parser import classify_boss_page, extract_boss_job_list

ADAPTER_DIR = Path(__file__).resolve().parent / "adapters" / "boss"
SCRIPT_PATH = ADAPTER_DIR / "read-boss.mjs"


def import_from_boss(
    keyword: str,
    city_code: str = "100010000",
    port: int = 9222,
    use_scrapling: bool | None = True,
    record_diagnostics: bool | None = True,
    include_html_snapshot: bool = True,
    html_snapshot_limit: int = 250000,
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
