"""Tests for job paste (stdin import) command."""

import json
from pathlib import Path

import pytest

from jobos.cli import _cmd_paste


class _Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch) -> Path:
    """Set up a project directory with init done."""
    (tmp_path / "profile").mkdir()
    (tmp_path / "jobs" / "normalized").mkdir(parents=True)
    (tmp_path / "predictions").mkdir()
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {}, "active_rubric": "v0", "rubric_history": []})
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestPaste:
    def test_paste_reads_stdin(self, project_dir: Path, monkeypatch, capsys):
        """Paste imports JD text from stdin."""
        jd_text = "# Data Science Intern\n\nCompany: DataCo\nLocation: NYC\n\nRequirements:\n- Python, pandas\n"
        monkeypatch.setattr("sys.stdin.read", lambda: jd_text)

        _cmd_paste(_Args())

        state = json.loads((project_dir / ".job-state.json").read_text())
        assert len(state["jobs"]) == 1
        job_id = list(state["jobs"].keys())[0]
        assert state["jobs"][job_id]["title"] == "Data Science Intern"
        assert state["jobs"][job_id]["company"] == "DataCo"

    def test_paste_creates_normalized_yaml(self, project_dir: Path, monkeypatch):
        jd_text = "# Backend Engineer\n\nCompany: ServerCo\nRequirements:\n- Go, Docker\n"
        monkeypatch.setattr("sys.stdin.read", lambda: jd_text)

        _cmd_paste(_Args())

        yaml_files = list((project_dir / "jobs" / "normalized").glob("*.yaml"))
        assert len(yaml_files) == 1

    def test_paste_updates_state(self, project_dir: Path, monkeypatch):
        jd_text = "# QA Engineer\n\nCompany: TestCo\n"
        monkeypatch.setattr("sys.stdin.read", lambda: jd_text)

        _cmd_paste(_Args())

        state = json.loads((project_dir / ".job-state.json").read_text())
        assert len(state["jobs"]) == 1
        job_entry = list(state["jobs"].values())[0]
        assert job_entry["status"] == "imported"
        assert job_entry["source_file"] == "stdin"

    def test_paste_empty_stdin_exits(self, project_dir: Path, monkeypatch):
        monkeypatch.setattr("sys.stdin.read", lambda: "")
        with pytest.raises(SystemExit) as exc:
            _cmd_paste(_Args())
        assert exc.value.code == 1
