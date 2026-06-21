#!/usr/bin/env python3
"""Fail when high-value architecture constraints regress."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
JOBOS = ROOT / "jobos"


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def main() -> int:
    errors: list[str] = []
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in JOBOS.rglob("*.py")
        if "__pycache__" not in path.parts
    }

    forbidden = {
        "patchright": "browser fingerprint masking",
        "AutomationControlled": "browser automation flag masking",
        "pipeline_results.json": "legacy non-ledger live output",
    }
    for path, source in sources.items():
        for token, reason in forbidden.items():
            if token in source:
                errors.append(f"{path.relative_to(ROOT)}: forbidden {reason}: {token}")

    for path, source in sources.items():
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                rendered = ast.unparse(target)
                if re.search(r"\[['\"]status['\"]\]$", rendered):
                    if path.name == "pipeline.py" or rendered.startswith("summary"):
                        continue
                    errors.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: "
                        "job status must change through jobos.pipeline"
                    )

    required_ignores = {
        ".job-state.json",
        ".daily_limits.json",
        ".job-contact-state.json",
        "auto_reply_state.json",
        "applications/",
        "jobs/",
        "predictions/",
        "pipeline_runs/",
        ".env",
        "*.pem",
        "*.key",
    }
    ignores = set(
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    for pattern in sorted(required_ignores - ignores):
        errors.append(f".gitignore: missing {pattern}")

    tracked_generated = [
        path
        for path in _tracked_files()
        if "__pycache__/" in path
        or path.endswith(".pyc")
        or path == ".job-state.json"
    ]
    for path in tracked_generated:
        errors.append(f"tracked generated/workspace file: {path}")

    if errors:
        print("architecture guard failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
