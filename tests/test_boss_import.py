"""Tests for the BOSS Zhipin adapter (boss_import.py and CLI integration)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jobos.boss_import import import_boss_jobs_to_workspace, import_from_boss


FIXTURES = Path(__file__).parent / "fixtures"


SAMPLE_OUTPUT = {
    "url": "https://www.zhipin.com/web/geek/job?query=AIGC&city=100010000",
    "title": "BOSS Zhipin Search",
    "items": [
        {
            "title": "AIGC Algorithm Engineer",
            "salary": "▯▯-▯▯K",
            "company": "ByteDance",
            "tags": ["3-5 years", "Bachelor", "PyTorch"],
            "link": "https://www.zhipin.com/job_detail/123.html",
        },
        {
            "title": "Senior AIGC Product Manager",
            "salary": "▯▯-▯▯K",
            "company": "Alibaba",
            "tags": ["5-10 years", "Master"],
            "link": "https://www.zhipin.com/job_detail/456.html",
        },
    ],
    "diagnostics": {
        "cardCount": 2,
        "salaryObfuscated": "2 salary values have obfuscated digits",
    },
}

EMPTY_OUTPUT = {
    "url": "https://www.zhipin.com/web/geek/job?query=xyz&city=100010000",
    "title": "BOSS Zhipin Search",
    "items": [],
    "diagnostics": {"cardCount": 0},
}

LOGIN_REQUIRED_OUTPUT = {
    "url": "https://www.zhipin.com/",
    "title": "BOSS Zhipin",
    "items": [],
    "diagnostics": {"maybeNeedLogin": "Appears not logged in."},
}

BLOCKED_OUTPUT = {
    "url": "https://www.zhipin.com/",
    "title": "BOSS Zhipin",
    "items": [],
    "diagnostics": {"blocked": "Security verification detected."},
}


def _mock_subprocess(stdout="", returncode=0, stderr=""):
    mock_result = MagicMock()
    mock_result.stdout = stdout
    mock_result.returncode = returncode
    mock_result.stderr = stderr
    return mock_result


class TestImportFromBoss:
    """Unit tests for import_from_boss()."""

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_returns_jobs_on_success(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(SAMPLE_OUTPUT))
        jobs = import_from_boss("AIGC")
        assert len(jobs) == 2
        assert jobs[0]["title"] == "AIGC Algorithm Engineer"
        assert jobs[0]["company"] == "ByteDance"
        assert jobs[0]["salary"] == "▯▯-▯▯K"
        assert jobs[0]["source"] == "boss_zhipin"
        assert jobs[0]["keyword"] == "AIGC"
        assert jobs[1]["company"] == "Alibaba"

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_returns_empty_list_when_no_results(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(EMPTY_OUTPUT))
        jobs = import_from_boss("nonexistent_term_xyz")
        assert jobs == []

    @patch("jobos.boss_import.shutil.which", return_value=None)
    def test_raises_when_node_not_found(self, mock_which):
        with pytest.raises(RuntimeError, match="Node.js not found"):
            import_from_boss("AIGC")

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_raises_on_chrome_connection_failure(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(
            stdout="",
            returncode=1,
            stderr="Cannot connect to Chrome debug port 9222. Run ./launch-chrome.sh first.",
        )
        with pytest.raises(ConnectionError, match="Cannot connect to Chrome"):
            import_from_boss("AIGC")

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_raises_on_login_required(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(LOGIN_REQUIRED_OUTPUT))
        with pytest.raises(PermissionError, match="login required"):
            import_from_boss("AIGC")

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_raises_on_security_blocked(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(BLOCKED_OUTPUT))
        with pytest.raises(PermissionError, match="security verification"):
            import_from_boss("AIGC")

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_raises_on_invalid_json(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess("not json at all")
        with pytest.raises(RuntimeError, match="invalid JSON"):
            import_from_boss("AIGC")

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_passes_keyword_city_port_to_subprocess(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(EMPTY_OUTPUT))
        import_from_boss("LLM", city_code="101010100", port=9333)
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[2] == "LLM"
        assert cmd[3] == "101010100"
        assert cmd[4] == "9333"

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_jobs_have_required_fields(self, mock_run, mock_which):
        mock_run.return_value = _mock_subprocess(json.dumps(SAMPLE_OUTPUT))
        jobs = import_from_boss("AIGC")
        for job in jobs:
            for field in ("title", "company", "salary", "tags", "link", "source", "keyword", "city_code", "imported_at"):
                assert field in job, f"Missing field: {field}"
            assert isinstance(job["tags"], list)

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_uses_python_extractor_when_html_is_available(self, mock_run, mock_which):
        output = {
            "url": SAMPLE_OUTPUT["url"],
            "title": SAMPLE_OUTPUT["title"],
            "items": [],
            "diagnostics": {"cardCount": 1, "pageState": "normal"},
            "html": (FIXTURES / "boss_job_list_normal.html").read_text(encoding="utf-8"),
        }
        mock_run.return_value = _mock_subprocess(json.dumps(output))

        jobs = import_from_boss("AIGC", use_scrapling=False)

        assert len(jobs) == 1
        assert jobs[0]["title"] == "Python Developer"
        assert jobs[0]["extractor"] == "beautifulsoup"
        assert jobs[0]["page_state"] == "normal"
        assert jobs[0]["extraction_diagnostics"]["item_count"] == 1

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_html_login_state_raises_permission_error(self, mock_run, mock_which):
        output = {
            "url": "https://www.zhipin.com/",
            "title": "BOSS Login",
            "items": [],
            "diagnostics": {},
            "html": (FIXTURES / "boss_login.html").read_text(encoding="utf-8"),
        }
        mock_run.return_value = _mock_subprocess(json.dumps(output))

        with pytest.raises(PermissionError, match="login required"):
            import_from_boss("AIGC", use_scrapling=False)


class TestBossWorkspaceImport:
    @patch("jobos.boss_import.import_from_boss")
    def test_writes_raw_files_and_state(self, mock_import, tmp_path):
        mock_import.return_value = [
            {
                "title": "AIGC Algorithm Engineer",
                "company": "ByteDance",
                "salary": "30-40K",
                "tags": ["Python"],
                "link": "https://www.zhipin.com/job_detail/123.html",
                "city_code": "100010000",
                "imported_at": "2026-06-17T00:00:00+00:00",
                "extractor": "node_cdp",
                "page_state": "normal",
                "extraction_diagnostics": {"item_count": 1},
            }
        ]
        (tmp_path / ".job-state.json").write_text(
            json.dumps({"jobs": {}, "active_rubric": "v0"}) + "\n",
            encoding="utf-8",
        )

        result = import_boss_jobs_to_workspace(tmp_path, "AIGC")

        state = json.loads((tmp_path / ".job-state.json").read_text(encoding="utf-8"))
        raw_files = list((tmp_path / "jobs" / "raw").glob("*boss*.json"))
        assert result.imported == 1
        assert len(raw_files) == 1
        assert len(state["jobs"]) == 1
        job = next(iter(state["jobs"].values()))
        assert job["source"] == "boss_zhipin"
        assert job["extractor"] == "node_cdp"


class TestBossImportCLI:
    """Integration tests for the `job boss-import` CLI command."""

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_cli_imports_jobs_and_writes_state(self, mock_run, mock_which, tmp_path, monkeypatch, capsys):
        mock_run.return_value = _mock_subprocess(json.dumps(SAMPLE_OUTPUT))

        # Set up workspace
        (tmp_path / "jobs" / "raw").mkdir(parents=True)
        state = {"jobs": {}, "active_rubric": "v0"}
        (tmp_path / ".job-state.json").write_text(json.dumps(state))

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["job", "boss-import", "--keyword", "AIGC"])

        from jobos.cli import main
        main()

        captured = capsys.readouterr()
        assert "Imported 2 jobs" in captured.out
        assert "AIGC Algorithm Engineer" in captured.out
        assert "ByteDance" in captured.out

        # Check state was updated
        state = json.loads((tmp_path / ".job-state.json").read_text())
        boss_jobs = [v for v in state["jobs"].values() if v.get("source") == "boss_zhipin"]
        assert len(boss_jobs) == 2
        assert all(job.get("extractor") == "node_cdp" for job in boss_jobs)

        # Check raw files were written
        raw_files = list((tmp_path / "jobs" / "raw").glob("*boss*"))
        assert len(raw_files) == 2

    @patch("jobos.boss_import.shutil.which", return_value=None)
    def test_cli_exits_when_node_missing(self, mock_which, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["job", "boss-import", "--keyword", "AIGC"])

        from jobos.cli import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Node.js not found" in captured.err

    @patch("jobos.boss_import.shutil.which", return_value="/usr/bin/node")
    @patch("jobos.boss_import.subprocess.run")
    def test_cli_prints_no_results_message(self, mock_run, mock_which, tmp_path, monkeypatch, capsys):
        mock_run.return_value = _mock_subprocess(json.dumps(EMPTY_OUTPUT))

        (tmp_path / "jobs" / "raw").mkdir(parents=True)
        state = {"jobs": {}, "active_rubric": "v0"}
        (tmp_path / ".job-state.json").write_text(json.dumps(state))

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("sys.argv", ["job", "boss-import", "--keyword", "xyz_nonexistent"])

        from jobos.cli import main
        main()

        captured = capsys.readouterr()
        assert "No jobs found" in captured.out
