"""Smoke tests for operational shell scripts."""

from __future__ import annotations

from pathlib import Path


SCRIPTS = [
    "scripts/audit_env.sh",
    "scripts/check_architecture.sh",
    "scripts/local_ci.sh",
    "scripts/pipeline_dry_run.sh",
]


def test_operational_scripts_exist_and_explain_actions() -> None:
    root = Path(__file__).parent.parent
    for rel in SCRIPTS:
        path = root / rel
        text = path.read_text(encoding="utf-8")
        assert path.exists()
        assert "echo" in text
        assert "rm -rf" not in text
        assert "git reset" not in text
        assert "git clean" not in text


def test_operational_scripts_are_executable() -> None:
    root = Path(__file__).parent.parent
    for rel in SCRIPTS:
        path = root / rel
        assert path.stat().st_mode & 0o111


def test_architecture_guard_is_read_only() -> None:
    root = Path(__file__).parent.parent
    text = (root / "scripts" / "check_architecture.py").read_text(
        encoding="utf-8"
    )

    assert "git reset" not in text
    assert "git clean" not in text
    assert "unlink(" not in text
