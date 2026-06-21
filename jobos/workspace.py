"""Workspace state and artifact layout helpers.

This module owns the project-local state file and canonical artifact paths.
Workflow modules should depend on this small interface instead of duplicating
``.job-state.json`` and directory names.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime_state import load_json_state, save_json_state


STATE_FILENAME = ".job-state.json"
PREDICTIONS_DIR = "predictions"
APPLICATIONS_DIR = "applications"
PIPELINE_RUNS_DIR = "pipeline_runs"
JOBS_DIR = "jobs"
JOBS_RAW_DIR = "raw"
JOBS_NORMALIZED_DIR = "normalized"
RETROS_DIR = "retros"
SUBMIT_ATTEMPTS_DIR = "submit_attempts"

DEFAULT_STATE: dict[str, Any] = {
    "schema_version": 1,
    "jobs": {},
    "active_rubric": "unknown",
    "rubric_history": [],
    "opportunities": [],
    "active_opportunity": None,
    "lessons": [],
}

INITIAL_STATE: dict[str, Any] = {
    "schema_version": 1,
    "jobs": {},
    "active_rubric": "v0_student_internship",
    "rubric_history": [],
    "opportunities": [],
    "active_opportunity": None,
    "lessons": [],
}

WORKSPACE_DIRECTORIES = (
    "profile",
    f"{JOBS_DIR}/{JOBS_RAW_DIR}",
    f"{JOBS_DIR}/{JOBS_NORMALIZED_DIR}",
    "jobs/skipped",
    "jobs/saved",
    PREDICTIONS_DIR,
    APPLICATIONS_DIR,
    RETROS_DIR,
    "rubrics",
    "adapters/manual_paste",
    "adapters/local_mock_form",
    "adapters/boss_assist",
    "tools",
    "tests/fixtures",
)

WORKSPACE_TEMPLATES = {
    "PROFILE.md": "# User Profile\n\nFill in your profile in `profile/` directory.\n",
    "RUBRIC.md": "# Job Scoring Rubric\n\nActive rubric: see `rubrics/` directory.\n",
    "WORKFLOW.md": "# Workflow\n\n1. Import JD\n2. Score\n3. Predict\n4. Pack\n5. Submit (manual)\n6. Retro\n7. Bump rubric\n",
    "STATUS.md": "# Status\n\nRun `job status` to update.\n",
}


@dataclass(frozen=True)
class WorkspaceInitResult:
    root: Path
    directories: tuple[Path, ...]
    files: tuple[Path, ...]
    state_created: bool


def default_state() -> dict[str, Any]:
    """Return a fresh default workspace state."""
    return copy.deepcopy(DEFAULT_STATE)


def initial_state() -> dict[str, Any]:
    """Return state written by ``job init`` for a new workspace."""
    return copy.deepcopy(INITIAL_STATE)


def state_path(state_dir: str | Path) -> Path:
    return Path(state_dir) / STATE_FILENAME


def load_state_file(
    path: str | Path,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a workspace state file, or return a fresh default when absent."""
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default) if default is not None else default_state()

    return load_json_state(
        path,
        default if default is not None else default_state(),
    )


def load_state(state_dir: str | Path) -> dict[str, Any]:
    """Load workspace state, or return defaults when the state file is absent."""
    return load_state_file(state_path(state_dir))


def save_state_file(path: str | Path, state: dict[str, Any]) -> None:
    """Persist workspace state at an explicit file path."""
    path = Path(path)
    save_json_state(path, state)


def save_state(state_dir: str | Path, state: dict[str, Any]) -> None:
    """Persist workspace state as UTF-8 JSON with a trailing newline."""
    save_state_file(state_path(state_dir), state)


def initialize_workspace(root: str | Path) -> WorkspaceInitResult:
    """Create the standard Job Application OS workspace layout idempotently."""
    root = Path(root)
    created_dirs: list[Path] = []
    created_files: list[Path] = []

    for directory in WORKSPACE_DIRECTORIES:
        path = root / directory
        path.mkdir(parents=True, exist_ok=True)
        created_dirs.append(path)

    for name, content in WORKSPACE_TEMPLATES.items():
        path = root / name
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created_files.append(path)

    path = state_path(root)
    state_created = False
    if not path.exists():
        save_state(root, initial_state())
        created_files.append(path)
        state_created = True

    return WorkspaceInitResult(
        root=root,
        directories=tuple(created_dirs),
        files=tuple(created_files),
        state_created=state_created,
    )


def predictions_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / PREDICTIONS_DIR


def applications_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / APPLICATIONS_DIR


def application_dir(state_dir: str | Path, job_id: str) -> Path:
    return applications_dir(state_dir) / job_id


def pipeline_runs_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / PIPELINE_RUNS_DIR


def jobs_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / JOBS_DIR


def jobs_raw_dir(state_dir: str | Path) -> Path:
    return jobs_dir(state_dir) / JOBS_RAW_DIR


def jobs_normalized_dir(state_dir: str | Path) -> Path:
    return jobs_dir(state_dir) / JOBS_NORMALIZED_DIR


def retros_dir(state_dir: str | Path) -> Path:
    return Path(state_dir) / RETROS_DIR


def submit_attempts_dir(state_dir: str | Path, job_id: str) -> Path:
    return application_dir(state_dir, job_id) / SUBMIT_ATTEMPTS_DIR


def count_predictions(state_dir: str | Path) -> int:
    directory = predictions_dir(state_dir)
    if not directory.is_dir():
        return 0
    return len(list(directory.glob("*.json")))


def count_application_packs(state_dir: str | Path) -> int:
    directory = applications_dir(state_dir)
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.iterdir() if path.is_dir())
