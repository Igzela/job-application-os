"""Tests for dry-run automation loop execution."""

from __future__ import annotations

import json
from pathlib import Path

from jobos.application_pack import load_application_pack
from jobos.cli import _cmd_loop_run
from jobos.loop import run_loop


class _Args:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


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


def test_loop_run_dry_run_writes_events_and_summary(tmp_path: Path, monkeypatch) -> None:
    _write_state(
        tmp_path,
        {
            "job-a": {"status": "imported", "title": "A", "company": "Co"},
            "job-b": {"status": "packed", "title": "B", "company": "Co"},
        },
    )

    calls: list[tuple[str, str]] = []

    def runner(stage: str):
        def _run(_state_dir: Path, job_id: str) -> dict:
            calls.append((job_id, stage))
            return {"ok": True}

        return _run

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {stage: runner(stage) for stage in ("score", "predict", "pack", "validate")},
    )

    summary = run_loop(
        tmp_path,
        dry_run=True,
        output="pipeline_runs/test-run",
        max_jobs=10,
    )

    run_dir = tmp_path / "pipeline_runs" / "test-run"
    assert (run_dir / "plan.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    assert ("job-a", "score") in calls
    assert ("job-a", "validate") in calls
    assert ("job-b", "validate") in calls
    assert not any(stage == "submit" for _, stage in calls)
    assert summary["counts"]["failed"] == 0
    assert summary["by_stage"]["validate"]["succeeded"] == 2


def test_loop_run_continues_after_per_job_failure(tmp_path: Path, monkeypatch) -> None:
    _write_state(
        tmp_path,
        {
            "job-a": {"status": "predicted", "title": "A", "company": "Co"},
            "job-b": {"status": "packed", "title": "B", "company": "Co"},
        },
    )

    def pack(_state_dir: Path, _job_id: str) -> dict:
        raise ValueError("pack exploded")

    def validate(_state_dir: Path, job_id: str) -> dict:
        return {"job_id": job_id}

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": validate, "predict": validate, "pack": pack, "validate": validate},
    )

    summary = run_loop(tmp_path, dry_run=True, output="pipeline_runs/fail-run")
    events = _events(tmp_path / "pipeline_runs" / "fail-run")

    assert summary["counts"]["failed"] == 1
    assert summary["by_error_class"]["pack_failed"] == 1
    assert any(e["job_id"] == "job-b" and e["event"] == "stage_succeeded" for e in events)


def test_loop_run_cli_prints_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    _write_state(tmp_path, {"job-a": {"status": "packed", "title": "A", "company": "Co"}})
    monkeypatch.chdir(tmp_path)

    def validate(_state_dir: Path, _job_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": validate, "predict": validate, "pack": validate, "validate": validate},
    )

    _cmd_loop_run(_Args(dry_run=True, max_jobs=10, output="pipeline_runs/cli-run", resume=None))

    out = capsys.readouterr().out
    assert "Loop run written:" in out
    assert "Succeeded: 1" in out


def test_loop_pack_writes_source_verifiable_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from jobos.predictor import create_prediction, save_prediction

    job_id = "job-pack"
    _write_state(
        tmp_path,
        {
            job_id: {
                "status": "predicted",
                "title": "Engineer",
                "company": "Acme",
            },
        },
    )
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "base.yaml").write_text("name: Test\n", encoding="utf-8")
    (tmp_path / "profile" / "skills.yaml").write_text("skills: []\n", encoding="utf-8")
    (tmp_path / "profile" / "availability.yaml").write_text(
        "available: true\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "evidence_bank.md").write_text(
        "- Built Python tools\n",
        encoding="utf-8",
    )
    job_yaml = tmp_path / "jobs" / "normalized" / f"{job_id}.yaml"
    job_yaml.parent.mkdir(parents=True)
    job_yaml.write_text(
        "title: Engineer\ncompany: Acme\nskills_required: [Python]\n",
        encoding="utf-8",
    )
    predictions_dir = tmp_path / "predictions"
    predictions_dir.mkdir()
    prediction = create_prediction(
        {"job_id": job_id, "version": 1},
        {"final_score": 8.0, "skill_match": 8.0},
        {"evidence_items": ["Built Python tools"]},
    )
    save_prediction(prediction, predictions_dir)

    summary = run_loop(
        tmp_path,
        dry_run=True,
        output="pipeline_runs/source-pack",
        max_jobs=1,
    )

    assert summary["counts"]["failed"] == 0
    load_application_pack(
        tmp_path / "applications" / job_id,
        require_manifest=True,
        verify_sources=True,
    )


def test_loop_run_records_extraction_diagnostics(tmp_path: Path, monkeypatch) -> None:
    _write_state(
        tmp_path,
        {
            "job-a": {
                "status": "packed",
                "title": "A",
                "company": "Co",
                "extractor": "scrapling",
                "page_state": "normal",
                "extraction_diagnostics": {
                    "extractor": "scrapling",
                    "page_state": "normal",
                    "fallback_used": False,
                    "item_count": 1,
                },
            }
        },
    )

    def validate(_state_dir: Path, _job_id: str) -> dict:
        return {"ok": True}

    monkeypatch.setattr(
        "jobos.loop.STAGE_RUNNERS",
        {"score": validate, "predict": validate, "pack": validate, "validate": validate},
    )

    summary = run_loop(tmp_path, dry_run=True, output="pipeline_runs/extraction-run")
    events = _events(tmp_path / "pipeline_runs" / "extraction-run")

    assert any(event.get("extractor") == "scrapling" for event in events)
    assert any(event.get("page_state") == "normal" for event in events)
    assert summary["by_extractor"]["scrapling"] >= 1
    assert summary["by_page_state"]["normal"] >= 1
    assert summary["jobs"]["job-a"]["extractor"] == "scrapling"
