"""Automation loop planning and dry-run execution.

The loop planner turns the current job state into a deterministic list of
pipeline actions. The dry-run executor runs only non-browser stages and leaves
structured run evidence in ``pipeline_runs/<run_id>/``.
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from .pipeline import (
    DRY_RUN_STAGES as PIPELINE_DRY_RUN_STAGES,
    PIPELINE_STAGES,
    action_for_job,
    remaining_dry_run_stages,
    transition_job,
)
from .run_ledger import (
    PLAN_FILENAME,
    RunLedger,
)
from .runtime_state import load_json_state, save_json_state
from .workspace import (
    PIPELINE_RUNS_DIR,
    application_dir,
    jobs_normalized_dir,
    load_state,
    pipeline_runs_dir,
    predictions_dir,
    save_state,
)

RUN_ID_FORMAT = "%Y%m%d-%H%M%S"
STAGES = PIPELINE_STAGES
DRY_RUN_STAGES = PIPELINE_DRY_RUN_STAGES
TERMINAL_SUCCESS_EVENTS = {"stage_succeeded", "job_skipped"}


def _load_state(state_dir: Path) -> dict[str, Any]:
    return load_state(state_dir)


def _write_state(state_dir: Path, state: dict[str, Any]) -> None:
    save_state(state_dir, state)


def default_run_dir(state_dir: str | Path, now: datetime | None = None) -> Path:
    """Return the conventional run directory for a new pipeline run."""
    if now is None:
        now = datetime.now()
    return pipeline_runs_dir(state_dir) / now.strftime(RUN_ID_FORMAT)


def build_loop_plan(state_dir: str | Path, max_jobs: int | None = 10) -> dict[str, Any]:
    """Build a deterministic read-only pipeline plan from ``.job-state.json``."""
    state_dir = Path(state_dir)
    state = _load_state(state_dir)
    limit = max_jobs if max_jobs is not None else 10
    if limit < 0:
        raise ValueError("max_jobs must be non-negative")

    stages: dict[str, list[dict[str, Any]]] = {stage: [] for stage in STAGES}
    candidates: list[tuple[int, str, dict[str, Any]]] = []

    for job_id, job in sorted(state.get("jobs", {}).items()):
        planned = action_for_job(job)
        if planned is None:
            continue
        stage = planned.stage
        action = {
            "job_id": job_id,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "status": job.get("status", "imported"),
            **planned.to_action_fields(),
        }
        candidates.append((STAGES.index(stage), stage, action))

    selected = sorted(candidates, key=lambda item: (item[0], item[2]["job_id"]))[:limit]
    for _, stage, action in selected:
        stages[stage].append(action)

    return {
        "schema_version": 1,
        "max_jobs": limit,
        "stages": stages,
        "summary": {
            "total_actions": len(selected),
            "by_stage": {stage: len(actions) for stage, actions in stages.items()},
        },
        "run_directory": {
            "root": PIPELINE_RUNS_DIR,
            "pattern": f"{PIPELINE_RUNS_DIR}/YYYYMMDD-HHMMSS/",
            "files": ["plan.json", "events.jsonl", "summary.json", "artifacts/"],
        },
    }


def write_loop_plan(
    state_dir: str | Path,
    output: str | Path | None = None,
    max_jobs: int | None = 10,
) -> Path:
    """Write a loop plan to disk and return the output path."""
    state_dir = Path(state_dir)
    if output is None:
        output_path = default_run_dir(state_dir) / PLAN_FILENAME
    else:
        output_path = Path(output)
        if not output_path.is_absolute():
            output_path = state_dir / output_path

    plan = build_loop_plan(state_dir, max_jobs=max_jobs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json_state(output_path, plan)
    return output_path


def _resolve_run_dir(state_dir: Path, output: str | Path | None) -> Path:
    if output is None:
        return default_run_dir(state_dir)
    run_dir = Path(output)
    if not run_dir.is_absolute():
        run_dir = state_dir / run_dir
    return run_dir


def classify_error(exc: BaseException | str) -> str:
    """Return stable error class for loop summaries and resume."""
    message = str(exc).lower()
    if isinstance(exc, FileNotFoundError):
        if "application pack" in message or "applications" in message:
            return "missing_pack"
        if "prediction" in message:
            return "missing_prediction"
        if "job" in message or "normalized" in message:
            return "missing_job"
        return "missing_state"
    if isinstance(exc, KeyError):
        return "missing_state"
    if "no application pack" in message or "application pack" in message:
        return "missing_pack"
    if "no prediction" in message or "prediction" in message:
        return "missing_prediction"
    if "validation" in message or "unsupported" in message:
        return "validation_failed"
    if "pack" in message:
        return "pack_failed"
    if "browser" in message or "cdp" in message:
        return "browser_connect_failed"
    if "url" in message:
        return "no_url"
    if "chat" in message:
        return "no_chat_button"
    if "fill" in message:
        return "fill_failed"
    if "send" in message:
        return "send_failed"
    return "unknown"


def _load_job_data(state_dir: Path, job_id: str, job_entry: dict[str, Any]) -> dict[str, Any]:
    import yaml

    normalized = jobs_normalized_dir(state_dir)
    yaml_path = normalized / f"{job_id}.yaml"
    json_path = normalized / f"{job_id}.json"
    if yaml_path.exists():
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    elif json_path.exists():
        data = json.loads(json_path.read_text(encoding="utf-8"))
    else:
        data = {"job_id": job_id, **job_entry}
    data.setdefault("job_id", job_id)
    return data


def _job_extraction_context(job_entry: dict[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if job_entry.get("extractor"):
        context["extractor"] = job_entry["extractor"]
    if job_entry.get("page_state"):
        context["page_state"] = job_entry["page_state"]
    diagnostics = job_entry.get("extraction_diagnostics")
    if isinstance(diagnostics, dict):
        context["extraction_diagnostics"] = {
            key: value
            for key, value in diagnostics.items()
            if key in ("extractor", "page_state", "fallback_used", "item_count", "warnings", "classification")
        }
    return context


def _load_rubric(state_dir: Path, profile: dict[str, Any]) -> dict[str, Any]:
    rubric_path = state_dir / "rubrics" / "v0_student_internship.md"
    if rubric_path.exists():
        from .rubric_manager import load_rubric

        return load_rubric(str(rubric_path))
    return {"target_roles": profile.get("target_roles", [])}


def _next_prediction_version(state_dir: Path, job_id: str) -> int:
    existing = sorted(predictions_dir(state_dir).glob(f"{job_id}_v*.json"))
    return len(existing) + 1


def _run_score(state_dir: Path, job_id: str) -> dict[str, Any]:
    from .profile_loader import load_evidence_bank, load_profile
    from .scorer import score_job

    state = _load_state(state_dir)
    jobs = state.setdefault("jobs", {})
    if job_id not in jobs:
        raise KeyError(f"Job {job_id} not found in state")
    profile = load_profile(str(state_dir))
    evidence = load_evidence_bank(str(state_dir))
    rubric = _load_rubric(state_dir, profile)
    job_data = _load_job_data(state_dir, job_id, jobs[job_id])
    scores = score_job(job_data, profile, evidence, rubric)
    transition_job(jobs[job_id], "scored")
    jobs[job_id]["scores"] = {
        key: value for key, value in scores.items() if key not in ("skipped", "skip_reason")
    }
    _write_state(state_dir, state)
    return {"final_score": scores.get("final_score")}


def _run_predict(state_dir: Path, job_id: str) -> dict[str, Any]:
    from .predictor import create_prediction, load_prediction, save_prediction
    from .profile_loader import load_profile

    state = _load_state(state_dir)
    jobs = state.setdefault("jobs", {})
    if job_id not in jobs:
        raise KeyError(f"Job {job_id} not found in state")
    job_entry = jobs[job_id]
    scores = job_entry.get("scores", {})
    if "final_score" not in scores:
        raise KeyError(f"Job {job_id} has no final_score")

    try:
        prediction = load_prediction(job_id, predictions_dir(state_dir))
    except FileNotFoundError:
        profile = load_profile(str(state_dir))
        version = _next_prediction_version(state_dir, job_id)
        prediction = create_prediction(
            {"job_id": job_id, **job_entry, "version": version},
            scores,
            profile,
        )
        save_prediction(prediction, predictions_dir(state_dir))

    transition_job(jobs[job_id], "predicted")
    _write_state(state_dir, state)
    return {"decision": prediction.decision, "version": prediction.version}


def _run_pack(state_dir: Path, job_id: str) -> dict[str, Any]:
    from .pack_generator import generate_workspace_pack

    result = generate_workspace_pack(state_dir, job_id)
    return {
        "files": sorted(result.pack.files),
        "warnings": len(result.warnings),
    }


def _run_validate(state_dir: Path, job_id: str) -> dict[str, Any]:
    from .evidence_markers import generate_evidence_report
    from .profile_loader import load_evidence_bank

    pack_dir = application_dir(state_dir, job_id)
    if not pack_dir.exists():
        raise FileNotFoundError(f"No application pack for {job_id}")
    pack_files = {
        path.name: path.read_text(encoding="utf-8")
        for path in pack_dir.iterdir()
        if path.is_file()
    }
    state = _load_state(state_dir)
    jobs = state.setdefault("jobs", {})
    if job_id not in jobs:
        raise KeyError(f"Job {job_id} not found in state")
    evidence = load_evidence_bank(str(state_dir))
    job_data = _load_job_data(state_dir, job_id, jobs[job_id])
    report = generate_evidence_report(pack_files, evidence, job_data)
    if report.get("unsupported"):
        raise ValueError(f"Validation failed: {len(report['unsupported'])} unsupported claims")
    transition_job(jobs[job_id], "validated")
    jobs[job_id]["validation"] = {
        "supported": len(report.get("supported", [])),
        "weak": len(report.get("weak", [])),
        "unsupported": 0,
    }
    _write_state(state_dir, state)
    return jobs[job_id]["validation"]


STAGE_RUNNERS = {
    "score": _run_score,
    "predict": _run_predict,
    "pack": _run_pack,
    "validate": _run_validate,
}


def _remaining_stages(status: str) -> list[str]:
    return remaining_dry_run_stages(status)


def _planned_jobs_for_dry_run(plan: dict[str, Any]) -> list[str]:
    job_ids: list[str] = []
    for stage in DRY_RUN_STAGES:
        for action in plan.get("stages", {}).get(stage, []):
            job_id = action.get("job_id")
            if job_id and job_id not in job_ids:
                job_ids.append(job_id)
    return job_ids


def _resume_stage_state(events: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    state: dict[tuple[str, str], str] = {}
    for event in events:
        job_id = event.get("job_id")
        stage = event.get("stage")
        event_type = event.get("event")
        if job_id and stage and event_type in TERMINAL_SUCCESS_EVENTS | {"stage_failed"}:
            state[(job_id, stage)] = event_type
    return state


def _summarize_events(run_dir: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": 1,
        "run_dir": str(run_dir),
        "total_events": len(events),
        "jobs": {},
        "counts": {
            "started": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "retried": 0,
        },
        "by_stage": {stage: {"succeeded": 0, "failed": 0} for stage in DRY_RUN_STAGES},
        "by_error_class": {},
        "by_extractor": {},
        "by_page_state": {},
    }
    for event in events:
        event_type = event.get("event")
        if event_type == "stage_started":
            summary["counts"]["started"] += 1
        elif event_type == "stage_succeeded":
            summary["counts"]["succeeded"] += 1
            stage = event.get("stage")
            if stage in summary["by_stage"]:
                summary["by_stage"][stage]["succeeded"] += 1
        elif event_type == "stage_failed":
            summary["counts"]["failed"] += 1
            stage = event.get("stage")
            if stage in summary["by_stage"]:
                summary["by_stage"][stage]["failed"] += 1
            error_class = event.get("error_class", "unknown")
            summary["by_error_class"][error_class] = (
                summary["by_error_class"].get(error_class, 0) + 1
            )
        elif event_type == "job_skipped":
            summary["counts"]["skipped"] += 1
        elif event_type == "job_retried":
            summary["counts"]["retried"] += 1

        extractor = event.get("extractor")
        if extractor:
            summary["by_extractor"][extractor] = summary["by_extractor"].get(extractor, 0) + 1
        page_state = event.get("page_state")
        if page_state:
            summary["by_page_state"][page_state] = summary["by_page_state"].get(page_state, 0) + 1

        job_id = event.get("job_id")
        if job_id:
            summary["jobs"].setdefault(job_id, {"events": 0, "status": "pending"})
            summary["jobs"][job_id]["events"] += 1
            if extractor:
                summary["jobs"][job_id]["extractor"] = extractor
            if page_state:
                summary["jobs"][job_id]["page_state"] = page_state
            if event_type == "stage_succeeded" and event.get("stage") == "validate":
                summary["jobs"][job_id]["status"] = "completed"
            elif event_type == "stage_failed":
                summary["jobs"][job_id]["status"] = "failed"
            elif event_type == "job_skipped":
                summary["jobs"][job_id]["status"] = "skipped"
    return summary


def run_loop(
    state_dir: str | Path,
    *,
    dry_run: bool = False,
    output: str | Path | None = None,
    max_jobs: int | None = 10,
    resume: str | Path | None = None,
) -> dict[str, Any]:
    """Execute automation loop and return final summary.

    ``dry_run`` is required for now; browser submit stages are intentionally
    not executed by this function.
    """
    if not dry_run:
        raise NotImplementedError("loop-run currently supports --dry-run only")

    state_dir = Path(state_dir)
    if resume is not None:
        run_dir = Path(resume)
        if not run_dir.is_absolute():
            run_dir = state_dir / run_dir
        plan_path = run_dir / PLAN_FILENAME
        if not plan_path.exists():
            raise FileNotFoundError(f"No plan.json found in resume dir: {run_dir}")
        ledger = RunLedger.open(run_dir)
        plan = load_json_state(plan_path, {})
        existing_events = ledger.load_events()
        resume_state = _resume_stage_state(existing_events)
    else:
        run_dir = _resolve_run_dir(state_dir, output)
        plan = build_loop_plan(state_dir, max_jobs=max_jobs)
        ledger = RunLedger(
            run_dir=run_dir,
            mode="dry_run",
            run_id=run_dir.name,
        )
        ledger.write_plan(plan)
        existing_events = []
        resume_state = {}

    planned_jobs = _planned_jobs_for_dry_run(plan)
    if max_jobs is not None:
        planned_jobs = planned_jobs[:max_jobs]

    for job_id in planned_jobs:
        state = _load_state(state_dir)
        job_entry = state.get("jobs", {}).get(job_id)
        if job_entry is None:
            ledger.append_event(
                {
                    "event": "stage_failed",
                    "job_id": job_id,
                    "stage": "score",
                    "error_class": "missing_job",
                    "error": f"Job {job_id} not found in state",
                },
            )
            continue

        stages = _remaining_stages(job_entry.get("status", "imported"))
        extraction_context = _job_extraction_context(job_entry)
        if not stages:
            ledger.append_event(
                {
                    "event": "job_skipped",
                    "job_id": job_id,
                    "reason": "no_non_browser_stage_pending",
                    **extraction_context,
                },
            )
            continue

        for stage in stages:
            previous = resume_state.get((job_id, stage))
            if previous == "stage_succeeded":
                ledger.append_event(
                    {
                        "event": "job_skipped",
                        "job_id": job_id,
                        "stage": stage,
                        "reason": "completed",
                        **extraction_context,
                    },
                )
                continue
            if previous == "stage_failed":
                ledger.append_event(
                    {"event": "job_retried", "job_id": job_id, "stage": stage, **extraction_context},
                )

            ledger.append_event(
                {"event": "stage_started", "job_id": job_id, "stage": stage, **extraction_context},
            )
            try:
                result = STAGE_RUNNERS[stage](state_dir, job_id)
            except Exception as exc:
                ledger.append_event(
                    {
                        "event": "stage_failed",
                        "job_id": job_id,
                        "stage": stage,
                        "error_class": classify_error(exc),
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                        **extraction_context,
                    },
                )
                break
            else:
                ledger.append_event(
                    {
                        "event": "stage_succeeded",
                        "job_id": job_id,
                        "stage": stage,
                        "result": result,
                        **extraction_context,
                    },
                )

    events = ledger.load_events()
    summary = _summarize_events(run_dir, events)
    ledger.write_summary(summary)
    return summary
