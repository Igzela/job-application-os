"""Tests for job report command and report module."""

import json
from pathlib import Path

import pytest

from jobos.report import generate_report


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / ".job-state.json"
    state.write_text(json.dumps({"jobs": {}, "active_rubric": "v0", "rubric_history": []}))
    (tmp_path / "predictions").mkdir()
    (tmp_path / "retros").mkdir()
    (tmp_path / "profile").mkdir()
    return tmp_path


def _add_job(state_dir: Path, job_id: str, status: str, retro: dict = None, scores: dict = None):
    state_path = state_dir / ".job-state.json"
    state = json.loads(state_path.read_text())
    entry = {"title": f"Job {job_id}", "company": "Co", "status": status}
    if retro:
        entry["retro"] = retro
    if scores:
        entry["scores"] = scores
    state["jobs"][job_id] = entry
    state_path.write_text(json.dumps(state, indent=2) + "\n")


class TestReport:
    def test_empty_state(self, state_dir: Path):
        md = generate_report(state_dir)
        assert "0" in md or "none" in md.lower() or "No jobs" in md

    def test_counts_by_stage(self, state_dir: Path):
        _add_job(state_dir, "j1", "imported")
        _add_job(state_dir, "j2", "scored")
        _add_job(state_dir, "j3", "packed")
        md = generate_report(state_dir)
        assert "3" in md  # total

    def test_retro_counts(self, state_dir: Path):
        _add_job(state_dir, "j1", "submitted", retro={
            "status_3d": "ack", "status_14d": "interview", "status_30d": "offer",
        })
        md = generate_report(state_dir)
        assert "offer" in md.lower() or "1" in md

    def test_pending_retros(self, state_dir: Path):
        _add_job(state_dir, "j1", "submitted", retro={
            "status_3d": "ack", "status_14d": None, "status_30d": None,
            "check_14d_due": "2020-01-01T00:00:00", "check_30d_due": "2020-01-01T00:00:00",
        })
        md = generate_report(state_dir)
        assert "j1" in md or "pending" in md.lower()

    def test_writes_file(self, state_dir: Path):
        generate_report(state_dir)
        report_file = state_dir / "reports" / "report.md"
        assert report_file.exists()
        assert len(report_file.read_text()) > 50

    def test_with_mixed_data(self, state_dir: Path):
        _add_job(state_dir, "j1", "imported")
        _add_job(state_dir, "j2", "scored", scores={"final_score": 7.5, "fit": 8.0})
        _add_job(state_dir, "j3", "submitted", retro={"status_3d": "ack", "status_14d": None, "status_30d": None,
                                                        "check_14d_due": "2020-01-01", "check_30d_due": "2020-01-01"})
        md = generate_report(state_dir)
        assert "**Total**" in md
        assert "7.5" in md  # score in top scoring section
        assert "j3" in md   # pending retro
