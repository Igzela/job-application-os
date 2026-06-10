"""BOSS Zhipin adapter -- Python wrapper for the CDP-based Node.js scraper.

Calls read-boss.mjs via subprocess, parses JSON output, returns structured
job data. Prerequisites: Node.js 22+, Chrome running with --remote-debugging-port,
user logged into BOSS Zhipin.
"""

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ADAPTER_DIR = Path(__file__).resolve().parent / "adapters" / "boss"
SCRIPT_PATH = ADAPTER_DIR / "read-boss.mjs"


def import_from_boss(
    keyword: str,
    city_code: str = "100010000",
    port: int = 9222,
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
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
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

    diagnostics = data.get("diagnostics", {})
    if diagnostics.get("blocked"):
        raise PermissionError(
            f"BOSS security verification: {diagnostics['blocked']}"
        )
    if diagnostics.get("maybeNeedLogin"):
        raise PermissionError(
            f"BOSS login required: {diagnostics['maybeNeedLogin']}"
        )

    items = data.get("items", [])
    jobs = []
    for item in items:
        jobs.append({
            "title": item.get("title", ""),
            "company": item.get("company", ""),
            "salary": item.get("salary", ""),
            "tags": item.get("tags", []),
            "link": item.get("link", ""),
            "source": "boss_zhipin",
            "keyword": keyword,
            "city_code": city_code,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        })

    return jobs
