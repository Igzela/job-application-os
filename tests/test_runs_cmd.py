"""Tests for run history CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from jobos.cli import _cmd_runs
from jobos.run_ledger import RunLedger


class _Args:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def test_runs_command_prints_recent_run_status(tmp_path: Path, capsys) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="live",
        run_id="live-20260620",
        plan={"stages": {}},
    )
    ledger.write_summary({"counts": {"succeeded": 2, "failed": 1}})

    with patch("jobos.cli._get_root", return_value=tmp_path):
        _cmd_runs(_Args(limit=10, mode=None))

    output = capsys.readouterr().out
    assert "live-20260620" in output
    assert "live" in output
    assert "completed" in output
    assert "2 succeeded" in output
    assert "1 failed" in output


def test_runs_command_handles_empty_workspace(tmp_path: Path, capsys) -> None:
    with patch("jobos.cli._get_root", return_value=tmp_path):
        _cmd_runs(_Args(limit=10, mode=None))

    assert "No pipeline runs found." in capsys.readouterr().out
