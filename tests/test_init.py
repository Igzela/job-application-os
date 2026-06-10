import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from argparse import Namespace

import pytest

from jobos.cli import _cmd_init


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """Run _cmd_init inside a temporary directory."""
    monkeypatch.chdir(tmp_path)
    args = Namespace()
    _cmd_init(args)
    return tmp_path


# -- Files that must be created at the project root --

@pytest.mark.parametrize(
    "filename",
    [
        "PROFILE.md",
        "RUBRIC.md",
        "WORKFLOW.md",
        "STATUS.md",
        ".job-state.json",
    ],
)
def test_init_creates_root_file(project_dir, filename):
    path = project_dir / filename
    assert path.exists(), f"{filename} was not created"
    assert path.is_file(), f"{filename} is not a regular file"


# -- Directories that must be created at the project root --

@pytest.mark.parametrize(
    "dirname",
    [
        "profile",
        "jobs",
        "predictions",
        "applications",
        "retros",
        "rubrics",
        "adapters",
        "tools",
    ],
)
def test_init_creates_directory(project_dir, dirname):
    path = project_dir / dirname
    assert path.exists(), f"directory {dirname}/ was not created"
    assert path.is_dir(), f"{dirname} exists but is not a directory"


# -- Content sanity checks --

def test_job_state_json_is_valid_json(project_dir):
    content = (project_dir / ".job-state.json").read_text()
    data = json.loads(content)
    assert isinstance(data, dict)


def test_job_state_json_has_jobs_key(project_dir):
    data = json.loads((project_dir / ".job-state.json").read_text())
    assert "jobs" in data


def test_job_state_json_has_active_rubric_key(project_dir):
    data = json.loads((project_dir / ".job-state.json").read_text())
    assert "active_rubric" in data


def test_profile_md_starts_with_heading(project_dir):
    content = (project_dir / "PROFILE.md").read_text()
    assert content.startswith("#"), "PROFILE.md should start with a markdown heading"


def test_rubric_md_starts_with_heading(project_dir):
    content = (project_dir / "RUBRIC.md").read_text()
    assert content.startswith("#"), "RUBRIC.md should start with a markdown heading"


def test_workflow_md_starts_with_heading(project_dir):
    content = (project_dir / "WORKFLOW.md").read_text()
    assert content.startswith("#"), "WORKFLOW.md should start with a markdown heading"


def test_status_md_starts_with_heading(project_dir):
    content = (project_dir / "STATUS.md").read_text()
    assert content.startswith("#"), "STATUS.md should start with a markdown heading"


# -- Idempotency: running init twice must not fail --

def test_init_is_idempotent(project_dir):
    args = Namespace()
    _cmd_init(args)  # second invocation in the same directory
    # all artifacts should still exist
    for name in ["PROFILE.md", "RUBRIC.md", "WORKFLOW.md", "STATUS.md", ".job-state.json"]:
        assert (project_dir / name).exists()
    for name in ["profile", "jobs", "predictions", "applications", "retros", "rubrics", "adapters", "tools"]:
        assert (project_dir / name).is_dir()
