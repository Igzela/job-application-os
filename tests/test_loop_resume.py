"""Tests for loop-run resume behavior."""

from __future__ import annotations

import json
from pathlib import Path

from jobos.loop import build_loop_plan, run_loop


def _write_state(base: Path, jobs: dict) -> None:
    (base / ".job-state.json").write_text(
        json.dumps({"jobs": jobs}, indent=2) + "\n",
        encoding="utf-8",
    )


def _events(run_dir: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_resume_skips_completed_stages_and_retries_failed_stage(tmp_path: Path, monkeypatch) -> None:
    _write_state(tmp_path, {"job-a": {"status": "imported", "title": "A", "company": "Co"}})
    run_dir = tmp_path / "pipeline_runs" / "resume-run"
    calls: list[str] = []

    def ok(stage: str):
        def _run(_state_dir: Path, _job_id: str) -> dict:
            calls.append(stage)
            return {"ok": True}

        return _run

    def fail_pack(_state_dir: Path, _job_id: str) -> dict:
        calls.append("pack")
        raise RuntimeError("pack failed")

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": ok("score"), "predict": ok("predict"), "pack": fail_pack, "validate": ok("validate")},
    )

    first = run_loop(tmp_path, dry_run=True, output=run_dir)
    assert first["counts"]["failed"] == 1
    assert calls == ["score", "predict", "pack"]

    calls.clear()
    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": ok("score"), "predict": ok("predict"), "pack": ok("pack"), "validate": ok("validate")},
    )

    second = run_loop(tmp_path, dry_run=True, resume=run_dir)
    events = _events(run_dir)

    assert calls == ["pack", "validate"]
    assert second["counts"]["retried"] == 1
    assert any(e["event"] == "job_skipped" and e.get("stage") == "score" for e in events)
    assert any(e["event"] == "job_retried" and e.get("stage") == "pack" for e in events)
    assert second["jobs"]["job-a"]["status"] == "completed"


def test_resume_skips_completed_job(tmp_path: Path, monkeypatch) -> None:
    _write_state(tmp_path, {"job-a": {"status": "packed", "title": "A", "company": "Co"}})
    run_dir = tmp_path / "pipeline_runs" / "done-run"
    calls: list[str] = []

    def validate(_state_dir: Path, _job_id: str) -> dict:
        calls.append("validate")
        return {"ok": True}

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": validate, "predict": validate, "pack": validate, "validate": validate},
    )

    run_loop(tmp_path, dry_run=True, output=run_dir)
    calls.clear()
    summary = run_loop(tmp_path, dry_run=True, resume=run_dir)

    assert calls == []
    assert summary["counts"]["skipped"] >= 1


def test_resume_retries_pending_stage_without_terminal_event(tmp_path: Path, monkeypatch) -> None:
    _write_state(tmp_path, {"job-a": {"status": "imported", "title": "A", "company": "Co"}})
    run_dir = tmp_path / "pipeline_runs" / "pending-run"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        json.dumps(build_loop_plan(tmp_path), indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "events.jsonl").write_text(
        json.dumps({"event": "stage_started", "job_id": "job-a", "stage": "score"}) + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    def ok(stage: str):
        def _run(_state_dir: Path, _job_id: str) -> dict:
            calls.append(stage)
            return {"ok": True}

        return _run

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {stage: ok(stage) for stage in ("score", "predict", "pack", "validate")},
    )

    summary = run_loop(tmp_path, dry_run=True, resume=run_dir)

    assert calls == ["score", "predict", "pack", "validate"]
    assert summary["jobs"]["job-a"]["status"] == "completed"
