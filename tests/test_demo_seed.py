"""Tests for job demo-seed command."""

import json
from pathlib import Path

import pytest

from jobos.cli import _cmd_demo_seed
from jobos.demo_seed import seed_demo_workspace


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def empty_dir(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestDemoSeed:
    def test_seed_demo_workspace_returns_created_paths(self, empty_dir: Path):
        result = seed_demo_workspace(empty_dir)

        assert result.profile_dir == empty_dir / "profile"
        assert result.rubric_path.exists()
        assert result.sample_jd_path.exists()

    def test_creates_profile_files(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        assert (empty_dir / "profile" / "base.yaml").exists()
        assert (empty_dir / "profile" / "skills.yaml").exists()
        assert (empty_dir / "profile" / "education.yaml").exists()
        assert (empty_dir / "profile" / "availability.yaml").exists()
        assert (empty_dir / "profile" / "evidence_bank.md").exists()

    def test_creates_rubric(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        assert (empty_dir / "rubrics" / "v0_student_internship.md").exists()

    def test_creates_sample_jd(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        jd = empty_dir / "jobs" / "raw" / "sample_swe_intern.md"
        assert jd.exists()
        content = jd.read_text()
        assert "Software Engineer" in content
        assert "Acme Labs" in content

    def test_creates_mock_form(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        form = empty_dir / "adapters" / "local_mock_form" / "application_form.html"
        assert form.exists()
        assert "<form" in form.read_text()

    def test_creates_state_file(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        state = json.loads((empty_dir / ".job-state.json").read_text())
        assert "jobs" in state
        assert state["active_rubric"] == "v0_student_internship"

    def test_is_idempotent(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        _cmd_demo_seed(_Args())  # second run should not fail
        assert (empty_dir / "profile" / "base.yaml").exists()

    def test_creates_required_directories(self, empty_dir: Path):
        _cmd_demo_seed(_Args())
        for d in ("profile", "jobs", "predictions", "applications", "retros", "rubrics"):
            assert (empty_dir / d).is_dir()
