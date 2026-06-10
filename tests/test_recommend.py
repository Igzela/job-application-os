"""Tests for job recommend command and recommend module."""

import json
from pathlib import Path

import pytest

from jobos.recommend import recommend_jobs


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    state = tmp_path / ".job-state.json"
    state.write_text(json.dumps({"jobs": {}, "active_rubric": "v0", "rubric_history": []}))
    (tmp_path / "predictions").mkdir()
    (tmp_path / "retros").mkdir()
    return tmp_path


def _add_job(state_dir: Path, job_id: str, status: str = "predicted", scores: dict = None):
    state_path = state_dir / ".job-state.json"
    state = json.loads(state_path.read_text())
    entry = {"title": f"Job {job_id}", "company": "Co", "status": status}
    if scores:
        entry["scores"] = scores
    state["jobs"][job_id] = entry
    state_path.write_text(json.dumps(state, indent=2) + "\n")


def _add_prediction(state_dir: Path, job_id: str, final_score: float, decision: str, risk: float = 2.0, evidence: float = 5.0):
    pred = {
        "job_id": job_id,
        "final_score": final_score,
        "decision": decision,
        "dimension_scores": {"fit": 5.0, "evidence": evidence, "risk": risk},
        "probabilities": {"screen": 0.3, "interview": 0.4, "offer": 0.2},
    }
    (state_dir / "predictions" / f"{job_id}_v1.json").write_text(json.dumps(pred))


class TestRecommend:
    def test_empty_state(self, state_dir: Path):
        results = recommend_jobs(state_dir, top_n=5)
        assert results == []

    def test_ranks_by_score(self, state_dir: Path):
        _add_job(state_dir, "j1")
        _add_job(state_dir, "j2")
        _add_prediction(state_dir, "j1", 7.0, "apply")
        _add_prediction(state_dir, "j2", 9.0, "apply")
        results = recommend_jobs(state_dir, top_n=5)
        assert len(results) == 2
        assert results[0]["job_id"] == "j2"
        assert results[1]["job_id"] == "j1"

    def test_excludes_skipped_by_default(self, state_dir: Path):
        _add_job(state_dir, "j1")
        _add_job(state_dir, "j2")
        _add_prediction(state_dir, "j1", 7.0, "apply")
        _add_prediction(state_dir, "j2", 1.0, "skip")
        results = recommend_jobs(state_dir, top_n=5, include_skipped=False)
        assert len(results) == 1
        assert results[0]["job_id"] == "j1"

    def test_includes_skipped_with_flag(self, state_dir: Path):
        _add_job(state_dir, "j1")
        _add_job(state_dir, "j2")
        _add_prediction(state_dir, "j1", 7.0, "apply")
        _add_prediction(state_dir, "j2", 1.0, "skip")
        results = recommend_jobs(state_dir, top_n=5, include_skipped=True)
        assert len(results) == 2

    def test_top_n_limits_results(self, state_dir: Path):
        for i in range(5):
            _add_job(state_dir, f"j{i}")
            _add_prediction(state_dir, f"j{i}", float(i + 5), "apply")
        results = recommend_jobs(state_dir, top_n=2)
        assert len(results) == 2

    def test_uses_prediction_data(self, state_dir: Path):
        _add_job(state_dir, "j1")
        _add_prediction(state_dir, "j1", 8.5, "apply", risk=1.0, evidence=8.0)
        results = recommend_jobs(state_dir, top_n=1)
        assert results[0]["final_score"] == 8.5
        assert results[0]["risk"] == 1.0
