"""Tests for job doctor command."""

import json
from pathlib import Path

import pytest

from jobos.cli import _cmd_doctor
from jobos.doctor import run_doctor
from jobos.application_pack import write_application_pack
from jobos.models import ApplicationPack


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
    def test_run_doctor_returns_structured_report(self, healthy_dir: Path):
        report = run_doctor(healthy_dir, version_info=(3, 14), version_text="3.14.0")

        assert report.all_ok is True
        assert any(check.label.startswith("Active rubric") for check in report.checks)

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

    def test_doctor_detects_conflicting_profile_identity(
        self,
        healthy_dir: Path,
    ) -> None:
        (healthy_dir / "profile" / "base.yaml").write_text(
            "name: Test\nschool: 长春理工大学\nmajor: 过程装备与控制工程\n",
            encoding="utf-8",
        )
        (healthy_dir / "profile" / "education.yaml").write_text(
            "education:\n"
            "  - institution: University of California, Berkeley\n"
            "    major: Computer Science\n",
            encoding="utf-8",
        )

        report = run_doctor(healthy_dir)

        check = next(
            check for check in report.checks
            if check.label == "Profile identity consistency"
        )
        assert check.ok is False
        assert "school" in check.detail
        assert "major" in check.detail
        assert report.all_ok is False

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

    def test_doctor_reports_explicit_live_mode(self, healthy_dir: Path, capsys):
        _cmd_doctor(_Args())
        out = capsys.readouterr().out
        assert "Live BOSS mode requires explicit confirmation" in out
        assert "✓" in out

    def test_doctor_reports_corrupt_workspace_state_without_crashing(
        self,
        healthy_dir: Path,
    ):
        (healthy_dir / ".job-state.json").write_text("{broken", encoding="utf-8")

        report = run_doctor(healthy_dir)

        assert report.all_ok is False
        check = next(
            check for check in report.checks
            if check.label == "Workspace state integrity"
        )
        assert check.ok is False
        assert check.severity == "error"
        assert "Invalid JSON" in check.detail

    def test_doctor_detects_tampered_pack(self, healthy_dir: Path):
        pack_dir = healthy_dir / "applications" / "j1"
        write_application_pack(
            pack_dir,
            ApplicationPack(job_id="j1", files={"greeting.md": "Hello"}),
        )
        (pack_dir / "greeting.md").write_text("Changed", encoding="utf-8")

        report = run_doctor(healthy_dir)

        check = next(
            check for check in report.checks
            if check.label == "Application Pack integrity"
        )
        assert check.ok is False
        assert "j1" in check.detail
        assert report.all_ok is False

    def test_doctor_warns_for_legacy_pack_without_failing(
        self,
        healthy_dir: Path,
    ):
        pack_dir = healthy_dir / "applications" / "legacy"
        pack_dir.mkdir()
        (pack_dir / "greeting.md").write_text("Hello", encoding="utf-8")

        report = run_doctor(healthy_dir)

        check = next(
            check for check in report.checks
            if check.label == "Application Pack manifests"
        )
        assert check.severity == "warning"
        assert check.ok is False
        assert "legacy" in check.detail
        assert report.all_ok is True

    def test_doctor_cli_warns_without_failing(
        self,
        healthy_dir: Path,
        capsys,
    ):
        pack_dir = healthy_dir / "applications" / "legacy"
        pack_dir.mkdir()
        (pack_dir / "greeting.md").write_text("Hello", encoding="utf-8")

        _cmd_doctor(_Args())

        out = capsys.readouterr().out
        assert "! Application Pack manifests" in out
        assert "All blocking checks passed." in out

    def test_doctor_warns_for_corrupt_run_without_failing(
        self,
        healthy_dir: Path,
    ):
        run_dir = healthy_dir / "pipeline_runs" / "broken-run"
        run_dir.mkdir(parents=True)
        (run_dir / "plan.json").write_text("{broken", encoding="utf-8")

        report = run_doctor(healthy_dir)

        check = next(
            check for check in report.checks
            if check.label == "Run Ledger integrity"
        )
        assert check.severity == "warning"
        assert check.ok is False
        assert "broken-run" in check.detail
        assert report.all_ok is True

    def test_doctor_detects_corrupt_daily_limit_state(
        self,
        healthy_dir: Path,
    ):
        (healthy_dir / ".daily_limits.json").write_text(
            "{broken",
            encoding="utf-8",
        )

        report = run_doctor(healthy_dir)

        check = next(
            check for check in report.checks
            if check.label == "Runtime state integrity"
        )
        assert check.ok is False
        assert ".daily_limits.json" in check.detail
        assert report.all_ok is False
