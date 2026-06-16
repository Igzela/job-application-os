"""Tests for read-only automation loop planning."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from jobos.cli import _cmd_loop_plan
from jobos.loop import build_loop_plan, default_run_dir, write_loop_plan


class _Args:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = {
        "jobs": {
            "job-pack": {"status": "predicted", "title": "Pack", "company": "Co"},
            "job-submit": {"status": "validated", "title": "Submit", "company": "Co"},
            "job-retro": {
                "status": "submitted",
                "title": "Retro",
                "company": "Co",
                "retro": {"status_3d": "ack_received", "status_14d": None},
            },
            "job-score": {"status": "imported", "title": "Score", "company": "Co"},
            "job-predict": {"status": "scored", "title": "Predict", "company": "Co"},
            "job-validate": {"status": "packed", "title": "Validate", "company": "Co"},
            "job-done": {"status": "skipped", "title": "Done", "company": "Co"},
        },
        "active_rubric": "v0",
    }
    (tmp_path / ".job-state.json").write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )
    return tmp_path


class TestLoopPlan:
    def test_groups_actions_by_pipeline_stage(self, state_dir: Path):
        plan = build_loop_plan(state_dir, max_jobs=10)

        assert list(plan["stages"].keys()) == [
            "score", "predict", "pack", "validate", "submit", "retro",
        ]
        assert [a["job_id"] for a in plan["stages"]["score"]] == ["job-score"]
        assert [a["job_id"] for a in plan["stages"]["predict"]] == ["job-predict"]
        assert [a["job_id"] for a in plan["stages"]["pack"]] == ["job-pack"]
        assert [a["job_id"] for a in plan["stages"]["validate"]] == ["job-validate"]
        assert [a["job_id"] for a in plan["stages"]["submit"]] == ["job-submit"]
        assert [a["job_id"] for a in plan["stages"]["retro"]] == ["job-retro"]
        assert plan["stages"]["retro"][0]["missing_windows"] == [
            "status_14d",
            "status_30d",
        ]

    def test_max_jobs_limits_by_stage_order_then_job_id(self, state_dir: Path):
        plan = build_loop_plan(state_dir, max_jobs=3)

        assert [a["job_id"] for a in plan["stages"]["score"]] == ["job-score"]
        assert [a["job_id"] for a in plan["stages"]["predict"]] == ["job-predict"]
        assert [a["job_id"] for a in plan["stages"]["pack"]] == ["job-pack"]
        assert plan["summary"]["total_actions"] == 3
        assert plan["stages"]["validate"] == []

    def test_plan_is_deterministic(self, state_dir: Path):
        assert build_loop_plan(state_dir, max_jobs=10) == build_loop_plan(state_dir, max_jobs=10)

    def test_write_plan_does_not_mutate_state(self, state_dir: Path):
        state_path = state_dir / ".job-state.json"
        before = state_path.read_bytes()

        output = write_loop_plan(
            state_dir=state_dir,
            output="pipeline_runs/test-run/plan.json",
            max_jobs=10,
        )

        assert output == state_dir / "pipeline_runs" / "test-run" / "plan.json"
        assert output.exists()
        assert state_path.read_bytes() == before

    def test_default_run_dir_uses_documented_convention(self, state_dir: Path):
        run_dir = default_run_dir(state_dir, now=datetime(2026, 6, 15, 5, 45, 30))

        assert run_dir == state_dir / "pipeline_runs" / "20260615-054530"

    def test_negative_max_jobs_raises(self, state_dir: Path):
        with pytest.raises(ValueError, match="max_jobs"):
            build_loop_plan(state_dir, max_jobs=-1)

    def test_cli_writes_requested_output(self, state_dir: Path, monkeypatch, capsys):
        monkeypatch.chdir(state_dir)

        _cmd_loop_plan(_Args(max_jobs=2, output="pipeline_runs/cli-run/plan.json"))

        output = state_dir / "pipeline_runs" / "cli-run" / "plan.json"
        assert output.exists()
        plan = json.loads(output.read_text(encoding="utf-8"))
        assert plan["summary"]["total_actions"] == 2
        assert "Loop plan written:" in capsys.readouterr().out
