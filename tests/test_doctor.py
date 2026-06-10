"""Tests for job doctor command."""

import json
from pathlib import Path

import pytest

from jobos.cli import _cmd_doctor


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def healthy_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a fully-populated project directory."""
    for d in ("profile", "jobs", "predictions", "applications", "retros", "rubrics"):
        (tmp_path / d).mkdir()

    (tmp_path / "profile" / "base.yaml").write_text("name: Test\n")
    (tmp_path / "profile" / "skills.yaml").write_text("skills: []\n")
    (tmp_path / "profile" / "availability.yaml").write_text("available: true\n")

    (tmp_path / "rubrics" / "v0_student_internship.md").write_text("# Rubric\n")

    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {}, "active_rubric": "v0_student_internship", "rubric_history": []})
    )

    fixtures_dir = tmp_path / "adapters" / "local_mock_form"
    fixtures_dir.mkdir(parents=True)
    (fixtures_dir / "application_form.html").write_text("<form></form>")

    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestDoctor:
    def test_doctor_passes_healthy(self, healthy_dir: Path, capsys):
        """All checks pass on a healthy workspace."""
        _cmd_doctor(_Args())
        out = capsys.readouterr().out
        assert "All checks passed" in out
        assert "✓" in out
        assert "✗" not in out

    def test_doctor_detects_missing_profile(self, healthy_dir: Path, capsys):
        (healthy_dir / "profile" / "base.yaml").unlink()
        with pytest.raises(SystemExit) as exc:
            _cmd_doctor(_Args())
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "✗" in out
        assert "base.yaml" in out

    def test_doctor_detects_missing_rubric(self, healthy_dir: Path, capsys):
        (healthy_dir / "rubrics" / "v0_student_internship.md").unlink()
        with pytest.raises(SystemExit) as exc:
            _cmd_doctor(_Args())
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "✗" in out

    def test_doctor_checks_python_version(self, healthy_dir: Path, capsys):
        _cmd_doctor(_Args())
        out = capsys.readouterr().out
        assert "Python" in out

    def test_doctor_detects_no_live_adapter(self, healthy_dir: Path, capsys):
        _cmd_doctor(_Args())
        out = capsys.readouterr().out
        assert "No live-platform adapter" in out
        assert "✓" in out
