"""Tests for prediction immutability in predictor.py."""

import json

import pytest

from jobos.predictor import (
    Prediction,
    create_prediction,
    load_prediction,
    predict_workspace_job,
    save_prediction,
)


# -- Fixtures -----------------------------------------------------------------

SAMPLE_JOB_DATA = {
    "job_id": "acme-backend-2026",
    "rubric_version": "v1",
    "company": "Acme",
    "role": "Backend Engineer",
}

SAMPLE_SCORES = {
    "skill_match": 7.0,
    "role_fit": 6.5,
    "compensation": 7.0,
    "company_signal": 5.0,
    "location_remote": 8.0,
    "timing_duration": 6.0,
    "evidence": 7.0,
    "strategic": 6.0,
    "friction": 3.0,
    "risk": 4.0,
    "final_score": 6.5,
}

SAMPLE_PROFILE = {
    "has_referral": False,
    "evidence_items": ["resume", "cover_letter", "portfolio"],
}


@pytest.fixture()
def predictions_dir(tmp_path):
    return tmp_path / "predictions"


def _make_prediction():
    return create_prediction(SAMPLE_JOB_DATA, SAMPLE_SCORES, SAMPLE_PROFILE)


# -- Tests --------------------------------------------------------------------


class TestPredictionIsImmutable:
    """save_prediction writes an immutable file; the returned data round-trips."""

    def test_save_creates_file(self, predictions_dir):
        pred = _make_prediction()
        path = save_prediction(pred, predictions_dir)

        assert path.exists()
        assert path.name == f"{pred.job_id}_v{pred.version}.json"

    def test_saved_file_contains_valid_json(self, predictions_dir):
        pred = _make_prediction()
        path = save_prediction(pred, predictions_dir)

        data = json.loads(path.read_text())
        assert data["job_id"] == pred.job_id
        assert data["final_score"] == pred.final_score
        assert data["version"] == pred.version
        assert "probabilities" in data
        assert "overall" in data["probabilities"]

    def test_frozen_dataclass_rejects_mutation(self):
        pred = _make_prediction()
        with pytest.raises(AttributeError):
            pred.decision = "skip"  # type: ignore[misc]

    def test_load_round_trips(self, predictions_dir):
        pred = _make_prediction()
        save_prediction(pred, predictions_dir)

        loaded = load_prediction(pred.job_id, predictions_dir)
        assert loaded.job_id == pred.job_id
        assert loaded.final_score == pred.final_score
        assert loaded.decision == pred.decision
        assert loaded.version == pred.version


class TestRePredictWithoutNewVersionRaises:
    """Saving the same job_id + version twice must raise FileExistsError."""

    def test_duplicate_save_raises(self, predictions_dir):
        pred = _make_prediction()
        save_prediction(pred, predictions_dir)

        with pytest.raises(FileExistsError, match="immutable"):
            save_prediction(pred, predictions_dir)

    def test_error_message_suggests_new_version(self, predictions_dir):
        pred = _make_prediction()
        save_prediction(pred, predictions_dir)

        with pytest.raises(FileExistsError, match="--new-version"):
            save_prediction(pred, predictions_dir)


class TestNewVersionCreatesV2:
    """--new-version path: bump version, save as _v2 file alongside _v1."""

    def test_v2_file_created(self, predictions_dir):
        v1 = _make_prediction()
        save_prediction(v1, predictions_dir)

        # Simulate --new-version: bump version in job_data
        v2_job_data = {**SAMPLE_JOB_DATA, "version": 2}
        v2 = create_prediction(v2_job_data, SAMPLE_SCORES, SAMPLE_PROFILE)
        v2_path = save_prediction(v2, predictions_dir)

        assert v2_path.exists()
        assert "_v2.json" in v2_path.name

    def test_v1_still_exists_after_v2(self, predictions_dir):
        v1 = _make_prediction()
        v1_path = save_prediction(v1, predictions_dir)

        v2_job_data = {**SAMPLE_JOB_DATA, "version": 2}
        v2 = create_prediction(v2_job_data, SAMPLE_SCORES, SAMPLE_PROFILE)
        save_prediction(v2, predictions_dir)

        assert v1_path.exists(), "v1 must not be removed or overwritten"

    def test_load_returns_highest_version(self, predictions_dir):
        v1 = _make_prediction()
        save_prediction(v1, predictions_dir)

        v2_job_data = {**SAMPLE_JOB_DATA, "version": 2}
        v2 = create_prediction(v2_job_data, SAMPLE_SCORES, SAMPLE_PROFILE)
        save_prediction(v2, predictions_dir)

        loaded = load_prediction(SAMPLE_JOB_DATA["job_id"], predictions_dir)
        assert loaded.version == 2

    def test_v1_and_v2_have_independent_versions(self, predictions_dir):
        v1 = _make_prediction()
        save_prediction(v1, predictions_dir)

        v2_job_data = {**SAMPLE_JOB_DATA, "version": 2}
        v2 = create_prediction(v2_job_data, SAMPLE_SCORES, SAMPLE_PROFILE)
        save_prediction(v2, predictions_dir)

        v1_loaded = load_prediction(SAMPLE_JOB_DATA["job_id"], predictions_dir)
        # load_prediction returns the latest; read v1 directly
        v1_file = predictions_dir / f"{SAMPLE_JOB_DATA['job_id']}_v1.json"
        v1_data = json.loads(v1_file.read_text())
        assert v1_data["version"] == 1
        assert v1_loaded.version == 2


def test_predict_workspace_job_writes_prediction_and_updates_state(tmp_path):
    job_id = SAMPLE_JOB_DATA["job_id"]
    (tmp_path / ".job-state.json").write_text(
        json.dumps(
            {
                "jobs": {
                    job_id: {
                        "title": SAMPLE_JOB_DATA["role"],
                        "company": SAMPLE_JOB_DATA["company"],
                        "status": "scored",
                        "scores": SAMPLE_SCORES,
                    }
                },
                "active_rubric": SAMPLE_JOB_DATA["rubric_version"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = predict_workspace_job(tmp_path, job_id)

    state = json.loads((tmp_path / ".job-state.json").read_text(encoding="utf-8"))
    assert result.path.exists()
    assert result.path.name == f"{job_id}_v1.json"
    assert result.prediction.final_score == SAMPLE_SCORES["final_score"]
    assert result.created_new_version is False
    assert state["jobs"][job_id]["status"] == "predicted"


def test_predict_workspace_job_new_version_preserves_existing_prediction(tmp_path):
    job_id = SAMPLE_JOB_DATA["job_id"]
    (tmp_path / ".job-state.json").write_text(
        json.dumps(
            {
                "jobs": {
                    job_id: {
                        "title": SAMPLE_JOB_DATA["role"],
                        "company": SAMPLE_JOB_DATA["company"],
                        "status": "scored",
                        "scores": SAMPLE_SCORES,
                    }
                },
                "active_rubric": SAMPLE_JOB_DATA["rubric_version"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    first = predict_workspace_job(tmp_path, job_id)
    second = predict_workspace_job(tmp_path, job_id, new_version=True)

    assert first.path.exists()
    assert second.path.exists()
    assert second.path.name == f"{job_id}_v2.json"
    assert second.prediction.version == 2
    assert second.created_new_version is True
