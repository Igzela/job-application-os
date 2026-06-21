"""Workspace-backed LLM job analysis workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .llm.base import LLMAdapter
from .llm.job_analyzer import analyze_match, check_scam, explain_scores
from .profile_loader import load_profile
from .workspace import jobs_normalized_dir, jobs_raw_dir, load_state, state_path


@dataclass(frozen=True)
class JobAnalysisResult:
    job_data: dict[str, Any]
    scam: dict[str, Any]
    match: dict[str, Any]
    explanation: str


class JobAnalysisInputError(ValueError):
    """Raised when workspace data required for job analysis is missing."""


def _load_workspace_job_data(state_dir: str | Path, job_id: str) -> dict[str, Any]:
    root = Path(state_dir)
    if not state_path(root).exists():
        raise JobAnalysisInputError("No .job-state.json found. Run `job init` first.")

    state = load_state(root)
    job_entry = state.get("jobs", {}).get(job_id)
    if not job_entry:
        raise JobAnalysisInputError(f"Job {job_id} not found.")

    job_yaml = jobs_normalized_dir(root) / f"{job_id}.yaml"
    job_json = jobs_raw_dir(root) / f"{job_id}.json"
    if job_yaml.exists():
        return yaml.safe_load(job_yaml.read_text(encoding="utf-8")) or {}
    if job_json.exists():
        return json.loads(job_json.read_text(encoding="utf-8"))
    return {"job_id": job_id, **job_entry}


def analyze_workspace_job(
    state_dir: str | Path,
    job_id: str,
    llm: LLMAdapter,
) -> JobAnalysisResult:
    """Analyze a workspace job with the supplied LLM adapter."""
    job_data = _load_workspace_job_data(state_dir, job_id)
    profile = load_profile(state_dir)
    scam = check_scam(llm, json.dumps(job_data, ensure_ascii=False))
    match = analyze_match(llm, job_data, profile)
    explanation = explain_scores(llm, match, job_data, profile)
    return JobAnalysisResult(
        job_data=job_data,
        scam=scam,
        match=match,
        explanation=explanation,
    )
