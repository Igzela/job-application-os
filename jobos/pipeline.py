"""Shared pipeline status, stage, and action rules.

This module is intentionally pure: it should not read files, write files, or
call browser/LLM code. Workflow Modules use it to interpret job state the same
way across planning, queues, submit selection, and UI surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

PIPELINE_STAGES = ("score", "predict", "pack", "validate", "submit", "retro")
DRY_RUN_STAGES = ("score", "predict", "pack", "validate")
RETRO_WINDOWS = ("status_3d", "status_14d", "status_30d")

JOB_STATUSES = (
    "imported",
    "scored",
    "predicted",
    "packed",
    "validated",
    "ready_to_submit",
    "submitted",
    "retro",
    "skipped",
)

QUEUE_BUCKETS = (
    "unscored",
    "unpredicted",
    "unpacked",
    "unsubmitted",
    "waiting_3d",
    "waiting_14d",
    "waiting_30d",
)

SUBMIT_CANDIDATE_STATUSES = (
    "predicted",
    "packed",
    "validated",
    "ready_to_submit",
)

_ACTION_BY_STATUS = {
    "imported": ("score", "score"),
    "scored": ("predict", "predict"),
    "predicted": ("pack", "pack"),
    "packed": ("validate", "validate-pack"),
    "validated": ("submit", "submit"),
    "ready_to_submit": ("submit", "submit"),
}

_QUEUE_BUCKET_BY_STATUS = {
    "imported": ("unscored",),
    "scored": ("unpredicted",),
    "predicted": ("unpacked",),
    "packed": ("unsubmitted",),
    "validated": ("unsubmitted",),
    "ready_to_submit": ("unsubmitted",),
}

_VALID_TRANSITIONS = {
    "imported": ("scored", "skipped"),
    "scored": ("predicted", "skipped"),
    "predicted": ("packed", "skipped"),
    "packed": ("validated", "ready_to_submit", "skipped"),
    "validated": ("packed", "ready_to_submit", "submitted", "skipped"),
    "ready_to_submit": ("packed", "submitted", "skipped"),
    "submitted": ("retro",),
    "retro": (),
    "skipped": (),
}


@dataclass(frozen=True)
class PipelineAction:
    """Next action derived from a job status."""

    stage: str
    action: str
    metadata: dict[str, Any]

    def to_action_fields(self) -> dict[str, Any]:
        """Return fields merged into loop plan action records."""
        return {"action": self.action, **self.metadata}


class PipelineTransitionError(ValueError):
    """Raised when a job lifecycle or live-submit invariant is violated."""


def status_for_job(job: Mapping[str, Any]) -> str:
    """Return a job status with the workspace default applied."""
    return str(job.get("status") or "imported")


def is_known_status(status: str) -> bool:
    """Return whether ``status`` is a defined pipeline status."""
    return status in JOB_STATUSES


def action_for_job(job: Mapping[str, Any]) -> PipelineAction | None:
    """Return the next pipeline action for a job, or ``None`` if none is due."""
    status = status_for_job(job)
    planned = _ACTION_BY_STATUS.get(status)
    if planned is not None:
        stage, action = planned
        return PipelineAction(stage=stage, action=action, metadata={})

    if status == "submitted":
        retro = job.get("retro") or {}
        missing = [window for window in RETRO_WINDOWS if retro.get(window) is None]
        if missing:
            return PipelineAction(
                stage="retro",
                action="retro",
                metadata={"missing_windows": missing},
            )

    return None


def remaining_dry_run_stages(status: str) -> list[str]:
    """Return non-browser stages still due from ``status``."""
    action = action_for_job({"status": status})
    if action is None or action.stage not in DRY_RUN_STAGES:
        return []
    start = DRY_RUN_STAGES.index(action.stage)
    return list(DRY_RUN_STAGES[start:])


def queue_buckets_for_job(job: Mapping[str, Any]) -> tuple[str, ...]:
    """Return queue buckets that should include ``job``."""
    status = status_for_job(job)
    direct = _QUEUE_BUCKET_BY_STATUS.get(status)
    if direct is not None:
        return direct

    if status == "submitted":
        retro = job.get("retro") or {}
        buckets = []
        for window in RETRO_WINDOWS:
            if retro.get(window) is None:
                buckets.append(f"waiting_{window.removeprefix('status_')}")
        return tuple(buckets)

    return ()


def is_submit_candidate_status(status: str) -> bool:
    """Return whether batch submit should consider jobs in ``status``.

    ``predicted`` and ``packed`` are retained for compatibility with existing
    batch-submit workflows that already have application packs on disk.
    """
    return status in SUBMIT_CANDIDATE_STATUSES


def is_valid_transition(from_status: str, to_status: str) -> bool:
    """Return whether a status transition is allowed by the pipeline rules."""
    return to_status in _VALID_TRANSITIONS.get(from_status, ())


def transition_job(job: MutableMapping[str, Any], to_status: str) -> str:
    """Apply a valid lifecycle transition and return the resulting status."""
    from_status = status_for_job(job)
    if from_status == to_status:
        return to_status
    if not is_valid_transition(from_status, to_status):
        raise PipelineTransitionError(
            f"Invalid job status transition: {from_status} -> {to_status}"
        )
    job["status"] = to_status
    return to_status


def record_external_submission(job: MutableMapping[str, Any]) -> str:
    """Record an already-completed external submission as workspace truth."""
    status = status_for_job(job)
    if status in {"submitted", "retro"}:
        return status
    if not is_known_status(status) or status == "skipped":
        raise PipelineTransitionError(
            f"Cannot record external submission from status: {status}"
        )
    job["status"] = "submitted"
    return "submitted"


def assert_live_submission_ready(job: Mapping[str, Any]) -> None:
    """Reject live submission unless evidence validation completed cleanly."""
    status = status_for_job(job)
    if status not in {"validated", "ready_to_submit"}:
        raise PipelineTransitionError(
            "Live submission requires validated or ready_to_submit status"
        )
    validation = job.get("validation")
    if not isinstance(validation, Mapping):
        raise PipelineTransitionError(
            "Live submission requires persisted evidence validation"
        )
    unsupported = validation.get("unsupported")
    if unsupported != 0:
        raise PipelineTransitionError(
            f"Live submission blocked by unsupported claims: {unsupported}"
        )
