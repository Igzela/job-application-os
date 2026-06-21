"""Shared plan, event, and summary persistence for pipeline runs."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .runtime_state import load_json_state, save_json_state
from .workspace import pipeline_runs_dir


PLAN_FILENAME = "plan.json"
EVENTS_FILENAME = "events.jsonl"
SUMMARY_FILENAME = "summary.json"
RUN_MODES = {"dry_run", "live"}
_MISSING = object()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_mode(mode: str) -> str:
    if mode not in RUN_MODES:
        raise ValueError(f"Invalid Run Ledger mode: {mode}")
    return mode


@dataclass(frozen=True)
class RunLedger:
    run_dir: Path
    mode: str
    run_id: str

    @classmethod
    def create(
        cls,
        state_dir: str | Path,
        *,
        mode: str,
        run_id: str,
        plan: Mapping[str, Any],
    ) -> "RunLedger":
        mode = _validate_mode(mode)
        run_dir = pipeline_runs_dir(state_dir) / run_id
        ledger = cls(run_dir=run_dir, mode=mode, run_id=run_id)
        ledger.write_plan(plan)
        return ledger

    @classmethod
    def open(cls, run_dir: str | Path) -> "RunLedger":
        run_dir = Path(run_dir)
        plan_path = run_dir / PLAN_FILENAME
        if not plan_path.is_file():
            raise FileNotFoundError(f"Run Ledger plan missing: {plan_path}")
        plan = load_json_state(plan_path, {})
        raw_mode = plan.get("mode", _MISSING)
        mode = "dry_run" if raw_mode is _MISSING else str(raw_mode)
        if raw_mode is not _MISSING:
            _validate_mode(mode)
        return cls(
            run_dir=run_dir,
            mode=mode,
            run_id=str(plan.get("run_id") or run_dir.name),
        )

    def write_plan(self, plan: Mapping[str, Any]) -> None:
        save_json_state(
            self.run_dir / PLAN_FILENAME,
            {
                **dict(plan),
                "mode": self.mode,
                "run_id": self.run_id,
            },
        )

    def append_event(self, event: Mapping[str, Any]) -> dict[str, Any]:
        record = {
            **dict(event),
            "schema_version": 1,
            "timestamp": _timestamp(),
        }
        path = self.run_dir / EVENTS_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(f"{path.name}.lock")
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(record, ensure_ascii=False, sort_keys=True)
                        + "\n"
                    )
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        return record

    def load_events(self) -> list[dict[str, Any]]:
        path = self.run_dir / EVENTS_FILENAME
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError(
                        f"Run Ledger event record must be an object: "
                        f"{path}:{line_number}"
                    )
                events.append(event)
        return events

    def write_summary(self, summary: Mapping[str, Any]) -> None:
        save_json_state(
            self.run_dir / SUMMARY_FILENAME,
            {
                **dict(summary),
                "mode": self.mode,
                "run_id": self.run_id,
                "run_dir": str(self.run_dir),
            },
        )


@dataclass(frozen=True)
class RunOverview:
    run_id: str
    mode: str
    status: str
    run_dir: Path
    succeeded: int = 0
    failed: int = 0
    started_at: str | None = None
    error: str | None = None


def _summary_count(
    counts: Mapping[str, Any],
    key: str,
    default: Any,
    summary_path: Path,
) -> int:
    try:
        return int(counts.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Run Ledger summary count {key} must be an integer: "
            f"{summary_path}"
        ) from exc


def _run_overview(run_dir: Path) -> RunOverview:
    try:
        ledger = RunLedger.open(run_dir)
        events = ledger.load_events()
        summary_path = run_dir / SUMMARY_FILENAME
        summary = (
            load_json_state(summary_path, {})
            if summary_path.exists()
            else {}
        )
        counts = summary.get("counts") or {}
        if not isinstance(counts, MappingABC):
            raise ValueError(
                f"Run Ledger summary counts must be an object: {summary_path}"
            )
        summary_error = summary.get("error")
        succeeded = _summary_count(
            counts,
            "succeeded",
            summary.get("submitted", 0),
            summary_path,
        )
        failed = _summary_count(
            counts,
            "failed",
            1 if summary_error else 0,
            summary_path,
        )
        if summary_error:
            status = "failed"
        elif summary_path.exists():
            status = "completed"
        elif events:
            status = "running"
        else:
            status = "planned"
        return RunOverview(
            run_id=ledger.run_id,
            mode=ledger.mode,
            status=status,
            run_dir=run_dir,
            succeeded=succeeded,
            failed=failed,
            started_at=events[0].get("timestamp") if events else None,
            error=str(summary_error) if summary_error else None,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return RunOverview(
            run_id=run_dir.name,
            mode="unknown",
            status="corrupt",
            run_dir=run_dir,
            error=str(exc),
        )


def list_run_ledgers(
    state_dir: str | Path,
    *,
    limit: int = 10,
    mode: str | None = None,
) -> list[RunOverview]:
    """Return recent Run Ledgers without failing on one corrupt run."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    if mode is not None:
        mode = _validate_mode(mode)
    root = pipeline_runs_dir(state_dir)
    if not root.is_dir() or limit == 0:
        return []

    runs = [
        _run_overview(path)
        for path in root.iterdir()
        if path.is_dir()
    ]
    if mode is not None:
        runs = [run for run in runs if run.mode == mode]
    runs.sort(key=lambda run: run.run_id, reverse=True)
    return runs[:limit]
