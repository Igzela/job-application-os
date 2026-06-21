"""Tests for shared pipeline status and action rules."""

from __future__ import annotations

import pytest

from jobos.pipeline import (
    PipelineTransitionError,
    action_for_job,
    assert_live_submission_ready,
    is_submit_candidate_status,
    is_valid_transition,
    queue_buckets_for_job,
    remaining_dry_run_stages,
    transition_job,
)


def test_action_for_job_maps_status_to_next_pipeline_stage() -> None:
    cases = {
        "imported": ("score", "score", {}),
        "scored": ("predict", "predict", {}),
        "predicted": ("pack", "pack", {}),
        "packed": ("validate", "validate-pack", {}),
        "validated": ("submit", "submit", {}),
        "ready_to_submit": ("submit", "submit", {}),
    }

    for status, (stage, action, metadata) in cases.items():
        planned = action_for_job({"status": status})

        assert planned is not None
        assert planned.stage == stage
        assert planned.action == action
        assert planned.metadata == metadata


def test_action_for_submitted_job_tracks_missing_retro_windows() -> None:
    planned = action_for_job(
        {
            "status": "submitted",
            "retro": {"status_3d": "ack_received", "status_14d": None},
        }
    )

    assert planned is not None
    assert planned.stage == "retro"
    assert planned.action == "retro"
    assert planned.metadata == {
        "missing_windows": ["status_14d", "status_30d"],
    }


def test_action_for_terminal_or_unknown_status_returns_none() -> None:
    assert action_for_job({"status": "submitted", "retro": {"status_3d": "x", "status_14d": "y", "status_30d": "z"}}) is None
    assert action_for_job({"status": "retro"}) is None
    assert action_for_job({"status": "skipped"}) is None
    assert action_for_job({"status": "mystery"}) is None


def test_remaining_dry_run_stages_are_ordered_from_current_status() -> None:
    assert remaining_dry_run_stages("imported") == ["score", "predict", "pack", "validate"]
    assert remaining_dry_run_stages("scored") == ["predict", "pack", "validate"]
    assert remaining_dry_run_stages("predicted") == ["pack", "validate"]
    assert remaining_dry_run_stages("packed") == ["validate"]
    assert remaining_dry_run_stages("validated") == []
    assert remaining_dry_run_stages("submitted") == []


def test_queue_buckets_for_job_uses_shared_status_rules() -> None:
    assert queue_buckets_for_job({"status": "imported"}) == ("unscored",)
    assert queue_buckets_for_job({"status": "scored"}) == ("unpredicted",)
    assert queue_buckets_for_job({"status": "predicted"}) == ("unpacked",)
    assert queue_buckets_for_job({"status": "packed"}) == ("unsubmitted",)
    assert queue_buckets_for_job({"status": "validated"}) == ("unsubmitted",)
    assert queue_buckets_for_job({"status": "ready_to_submit"}) == ("unsubmitted",)
    assert queue_buckets_for_job(
        {
            "status": "submitted",
            "retro": {"status_3d": None, "status_14d": "done", "status_30d": None},
        }
    ) == ("waiting_3d", "waiting_30d")
    assert queue_buckets_for_job({"status": "retro"}) == ()


def test_submit_candidate_statuses_preserve_dry_run_compatibility() -> None:
    assert is_submit_candidate_status("predicted")
    assert is_submit_candidate_status("packed")
    assert is_submit_candidate_status("validated")
    assert is_submit_candidate_status("ready_to_submit")
    assert not is_submit_candidate_status("imported")
    assert not is_submit_candidate_status("submitted")


def test_pipeline_transition_validity_is_defined_in_one_place() -> None:
    assert is_valid_transition("imported", "scored")
    assert is_valid_transition("scored", "predicted")
    assert is_valid_transition("predicted", "packed")
    assert is_valid_transition("packed", "validated")
    assert is_valid_transition("packed", "ready_to_submit")
    assert is_valid_transition("validated", "packed")
    assert is_valid_transition("ready_to_submit", "packed")
    assert is_valid_transition("validated", "submitted")
    assert is_valid_transition("ready_to_submit", "submitted")
    assert is_valid_transition("submitted", "retro")
    assert is_valid_transition("imported", "skipped")

    assert not is_valid_transition("imported", "submitted")
    assert not is_valid_transition("skipped", "submitted")
    assert not is_valid_transition("submitted", "packed")
    assert not is_valid_transition("retro", "packed")
    assert not is_valid_transition("mystery", "submitted")


def test_transition_job_applies_valid_transition() -> None:
    job = {"status": "packed"}

    transition_job(job, "validated")

    assert job["status"] == "validated"


def test_transition_job_rejects_invalid_transition_without_mutating() -> None:
    job = {"status": "imported"}

    with pytest.raises(PipelineTransitionError, match="imported.*submitted"):
        transition_job(job, "submitted")

    assert job["status"] == "imported"


def test_live_submission_requires_successful_evidence_validation() -> None:
    assert_live_submission_ready(
        {
            "status": "validated",
            "validation": {"supported": 4, "weak": 1, "unsupported": 0},
        }
    )

    with pytest.raises(PipelineTransitionError, match="validated"):
        assert_live_submission_ready({"status": "packed"})

    with pytest.raises(PipelineTransitionError, match="unsupported"):
        assert_live_submission_ready(
            {
                "status": "validated",
                "validation": {"unsupported": 1},
            }
        )
