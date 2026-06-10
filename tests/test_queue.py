"""Tests for job queue command and queue module."""

import json
from pathlib import Path

import pytest

from jobos.queue import get_queue


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / ".job-state.json"
    state.write_text(json.dumps({"jobs": {}, "active_rubric": "v0", "rubric_history": []}))
    (tmp_path / "predictions").mkdir()
    (tmp_path / "retros").mkdir()
    return tmp_path


def _add_job(state_dir: Path, job_id: str, status: str, retro: dict = None):
    state_path = state_dir / ".job-state.json"
    state = json.loads(state_path.read_text())
    entry = {"title": f"Job {job_id}", "company": "Co", "status": status}
    if retro:
        entry["retro"] = retro
    state["jobs"][job_id] = entry
    state_path.write_text(json.dumps(state, indent=2) + "\n")


class TestQueue:
    def test_empty_state(self, state_dir: Path):
        q = get_queue(state_dir)
        for key in ("unscored", "unpredicted", "unpacked", "unsubmitted",
                     "waiting_3d", "waiting_14d", "waiting_30d"):
            assert q[key] == []

    def test_classifies_imported_as_unscored(self, state_dir: Path):
        _add_job(state_dir, "j1", "imported")
        q = get_queue(state_dir)
        assert len(q["unscored"]) == 1
        assert q["unscored"][0]["job_id"] == "j1"

    def test_classifies_scored_as_unpredicted(self, state_dir: Path):
        _add_job(state_dir, "j1", "scored")
        q = get_queue(state_dir)
        assert len(q["unpredicted"]) == 1

    def test_classifies_predicted_as_unpacked(self, state_dir: Path):
        _add_job(state_dir, "j1", "predicted")
        q = get_queue(state_dir)
        assert len(q["unpacked"]) == 1

    def test_classifies_packed_as_unsubmitted(self, state_dir: Path):
        _add_job(state_dir, "j1", "packed")
        q = get_queue(state_dir)
        assert len(q["unsubmitted"]) == 1

    def test_classifies_submitted_by_retro_window(self, state_dir: Path):
        _add_job(state_dir, "j1", "submitted", retro={
            "status_3d": None, "status_14d": None, "status_30d": None,
            "check_3d_due": "2020-01-01T00:00:00",
            "check_14d_due": "2020-01-01T00:00:00",
            "check_30d_due": "2020-01-01T00:00:00",
        })
        q = get_queue(state_dir)
        assert len(q["waiting_3d"]) == 1
        assert len(q["waiting_14d"]) == 1
        assert len(q["waiting_30d"]) == 1

    def test_mixed_states(self, state_dir: Path):
        _add_job(state_dir, "j1", "imported")
        _add_job(state_dir, "j2", "scored")
        _add_job(state_dir, "j3", "packed")
        q = get_queue(state_dir)
        assert len(q["unscored"]) == 1
        assert len(q["unpredicted"]) == 1
        assert len(q["unsubmitted"]) == 1
