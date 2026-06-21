"""Tests for shared dry-run and live pipeline run evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.run_ledger import RunLedger, list_run_ledgers


def test_run_ledger_writes_plan_events_and_summary(tmp_path: Path) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="live",
        run_id="live-test",
        plan={"stages": {"submit": [{"job_id": "j1"}]}},
    )

    ledger.append_event(
        {"event": "stage_started", "job_id": "j1", "stage": "submit"}
    )
    ledger.append_event(
        {"event": "stage_succeeded", "job_id": "j1", "stage": "submit"}
    )
    ledger.write_summary({"counts": {"succeeded": 1}})

    assert ledger.run_dir == tmp_path / "pipeline_runs" / "live-test"
    plan = json.loads((ledger.run_dir / "plan.json").read_text(encoding="utf-8"))
    summary = json.loads(
        (ledger.run_dir / "summary.json").read_text(encoding="utf-8")
    )
    events = ledger.load_events()
    assert plan["mode"] == "live"
    assert summary["mode"] == "live"
    assert summary["run_id"] == "live-test"
    assert [event["event"] for event in events] == [
        "stage_started",
        "stage_succeeded",
    ]


def test_run_ledger_opens_existing_run_for_resume(tmp_path: Path) -> None:
    created = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="resume-test",
        plan={"stages": {}},
    )
    created.append_event({"event": "stage_started", "stage": "score"})

    resumed = RunLedger.open(created.run_dir)

    assert resumed.mode == "dry_run"
    assert resumed.load_events()[0]["stage"] == "score"


def test_append_event_owns_timestamp_and_schema_version(tmp_path: Path) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="metadata-test",
        plan={"stages": {}},
    )

    event = ledger.append_event(
        {
            "event": "stage_started",
            "timestamp": "caller-supplied",
            "schema_version": 99,
        }
    )

    loaded = ledger.load_events()[0]
    assert event["schema_version"] == 1
    assert loaded["schema_version"] == 1
    assert event["timestamp"] != "caller-supplied"
    assert loaded["timestamp"] != "caller-supplied"


def test_run_ledger_create_rejects_invalid_mode(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid Run Ledger mode"):
        RunLedger.create(
            tmp_path,
            mode="preview",
            run_id="bad-mode",
            plan={"stages": {}},
        )


def test_list_run_ledgers_marks_invalid_mode_corrupt(tmp_path: Path) -> None:
    run_dir = tmp_path / "pipeline_runs" / "bad-mode"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        '{"schema_version": 1, "mode": "preview"}\n',
        encoding="utf-8",
    )

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "bad-mode"
    assert runs[0].status == "corrupt"
    assert "Invalid Run Ledger mode" in str(runs[0].error)


def test_list_run_ledgers_marks_empty_mode_corrupt(tmp_path: Path) -> None:
    run_dir = tmp_path / "pipeline_runs" / "empty-mode"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        '{"schema_version": 1, "mode": ""}\n',
        encoding="utf-8",
    )

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "empty-mode"
    assert runs[0].status == "corrupt"
    assert "Invalid Run Ledger mode" in str(runs[0].error)


def test_list_run_ledgers_treats_missing_mode_as_legacy_dry_run(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "pipeline_runs" / "legacy-mode"
    run_dir.mkdir(parents=True)
    (run_dir / "plan.json").write_text(
        '{"schema_version": 1, "stages": {}}\n',
        encoding="utf-8",
    )

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "legacy-mode"
    assert runs[0].mode == "dry_run"
    assert runs[0].status == "planned"


def test_list_run_ledgers_reports_complete_running_and_corrupt(
    tmp_path: Path,
) -> None:
    complete = RunLedger.create(
        tmp_path,
        mode="live",
        run_id="20260620-030000",
        plan={"stages": {}},
    )
    complete.append_event({"event": "stage_succeeded", "stage": "submit"})
    complete.write_summary({"counts": {"succeeded": 1, "failed": 0}})

    running = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="20260620-020000",
        plan={"stages": {}},
    )
    running.append_event({"event": "stage_started", "stage": "score"})

    corrupt_dir = tmp_path / "pipeline_runs" / "20260620-010000"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "plan.json").write_text("{broken", encoding="utf-8")

    runs = list_run_ledgers(tmp_path)

    assert [run.run_id for run in runs] == [
        "20260620-030000",
        "20260620-020000",
        "20260620-010000",
    ]
    assert runs[0].status == "completed"
    assert runs[0].succeeded == 1
    assert runs[1].status == "running"
    assert runs[2].status == "corrupt"
    assert runs[2].error


def test_list_run_ledgers_marks_plan_without_events_as_planned(
    tmp_path: Path,
) -> None:
    RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="20260620-planned",
        plan={"stages": {"score": []}},
    )

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-planned"
    assert runs[0].status == "planned"


def test_list_run_ledgers_marks_run_without_plan_corrupt(tmp_path: Path) -> None:
    run_dir = tmp_path / "pipeline_runs" / "20260620-empty"
    run_dir.mkdir(parents=True)

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-empty"
    assert runs[0].status == "corrupt"
    assert "plan.json" in str(runs[0].error)


def test_list_run_ledgers_marks_non_object_event_corrupt(
    tmp_path: Path,
) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="20260620-bad-event",
        plan={"stages": {}},
    )
    (ledger.run_dir / "events.jsonl").write_text('"oops"\n', encoding="utf-8")

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-bad-event"
    assert runs[0].status == "corrupt"
    assert "event record" in str(runs[0].error)


def test_list_run_ledgers_marks_non_object_summary_counts_corrupt(
    tmp_path: Path,
) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="20260620-bad-counts",
        plan={"stages": {}},
    )
    ledger.write_summary({"counts": ["bad"]})

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-bad-counts"
    assert runs[0].status == "corrupt"
    assert "summary counts" in str(runs[0].error)


def test_list_run_ledgers_marks_non_integer_summary_counts_corrupt(
    tmp_path: Path,
) -> None:
    ledger = RunLedger.create(
        tmp_path,
        mode="dry_run",
        run_id="20260620-bad-count",
        plan={"stages": {}},
    )
    ledger.write_summary({"counts": {"succeeded": ["bad"]}})

    runs = list_run_ledgers(tmp_path)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-bad-count"
    assert runs[0].status == "corrupt"
    assert "summary count succeeded" in str(runs[0].error)


def test_list_run_ledgers_filters_mode_and_limit(tmp_path: Path) -> None:
    for run_id, mode in [
        ("20260620-030000", "live"),
        ("20260620-020000", "dry_run"),
        ("20260620-010000", "live"),
    ]:
        ledger = RunLedger.create(
            tmp_path,
            mode=mode,
            run_id=run_id,
            plan={"stages": {}},
        )
        ledger.write_summary({"counts": {}})

    runs = list_run_ledgers(tmp_path, mode="live", limit=1)

    assert len(runs) == 1
    assert runs[0].run_id == "20260620-030000"
    assert runs[0].mode == "live"


def test_list_run_ledgers_rejects_invalid_mode_filter(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid Run Ledger mode"):
        list_run_ledgers(tmp_path, mode="preview")


def test_list_run_ledgers_understands_live_summary_shape(tmp_path: Path) -> None:
    successful = RunLedger.create(
        tmp_path,
        mode="live",
        run_id="live-success",
        plan={"stages": []},
    )
    successful.write_summary(
        {
            "submitted": 2,
            "results": [
                {"status": "submitted"},
                {"status": "submitted"},
                {"status": "low_match"},
            ],
        }
    )
    failed = RunLedger.create(
        tmp_path,
        mode="live",
        run_id="live-failed",
        plan={"stages": []},
    )
    failed.write_summary({"error": "browser_connect_failed", "results": []})

    runs = {run.run_id: run for run in list_run_ledgers(tmp_path)}

    assert runs["live-success"].status == "completed"
    assert runs["live-success"].succeeded == 2
    assert runs["live-failed"].status == "failed"
    assert runs["live-failed"].failed == 1
