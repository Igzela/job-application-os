"""Tests for versioned, atomic runtime JSON state."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.automation_policy import DailyRateLimiter
from jobos.live_pipeline import load_contact_state, record_contacted_job
from jobos.runtime_state import RuntimeStateError, load_json_state, save_json_state


def test_runtime_state_round_trips_with_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"

    save_json_state(path, {"items": ["a"]})

    assert load_json_state(path, {"items": []}) == {
        "schema_version": 1,
        "items": ["a"],
    }
    assert not list(tmp_path.glob(".runtime.json.*.tmp"))


def test_runtime_state_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(RuntimeStateError, match="Invalid JSON"):
        load_json_state(path, {"items": []})


def test_contact_state_uses_versioned_runtime_state(tmp_path: Path) -> None:
    state = record_contacted_job(
        tmp_path,
        {
            "job_id": "j1",
            "url": "https://zhipin.com/job/1",
            "company": "Acme",
            "title": "Engineer",
        },
    )

    assert state["schema_version"] == 1
    assert load_contact_state(tmp_path)["jobs"]["j1"]["company"] == "Acme"


def test_daily_rate_limiter_persists_versioned_state(tmp_path: Path) -> None:
    path = tmp_path / ".daily_limits.json"
    limiter = DailyRateLimiter(state_file=path)

    limiter.record_submission()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["submissions"] == 1
