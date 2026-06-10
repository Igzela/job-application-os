"""End-to-end integration test: full pipeline from init through bump-rubric.

Uses deterministic fixtures, no API keys, no network calls.
Covers: init → import → score → predict → pack → dry-run → mark-submitted → retro → status → bump-rubric
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobos.cli import _cmd_init, _cmd_import, _cmd_score, _cmd_predict
from jobos.cli import _cmd_pack, _cmd_dry_run, _cmd_mark_submitted
from jobos.cli import _cmd_retro, _cmd_retro_freeform, _cmd_status, _cmd_bump_rubric


class _Args:
    """Minimal argparse namespace."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create a fully-populated project directory and cd into it.

    Copies profile fixtures and sample rubric so all CLI commands work.
    """
    # Copy profile fixtures
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()

    fixtures = Path(__file__).parent.parent / "profile"
    for name in ("base.yaml", "skills.yaml", "education.yaml", "availability.yaml"):
        src = fixtures / name
        if src.exists():
            (profile_dir / name).write_text(src.read_text())

    # Copy evidence bank
    ev_src = fixtures / "evidence_bank.md"
    if ev_src.exists():
        (profile_dir / "evidence_bank.md").write_text(ev_src.read_text())

    # Copy rubric
    rubrics_dir = tmp_path / "rubrics"
    rubrics_dir.mkdir()
    rubric_src = Path(__file__).parent.parent / "rubrics" / "v0_student_internship.md"
    if rubric_src.exists():
        (rubrics_dir / "v0_student_internship.md").write_text(rubric_src.read_text())

    # Copy mock form
    adapters_dir = tmp_path / "adapters" / "local_mock_form"
    adapters_dir.mkdir(parents=True)
    mock_src = Path(__file__).parent / "fixtures" / "mock_form.html"
    if mock_src.exists():
        (adapters_dir / "application_form.html").write_text(mock_src.read_text())

    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def sample_jd_file(project_dir: Path) -> Path:
    """Write a sample JD file for import."""
    jd_path = project_dir / "sample_jd.md"
    jd_path.write_text(
        "# Software Engineer Intern\n\n"
        "Company: Acme Labs\n"
        "Location: San Francisco, CA\n\n"
        "Requirements:\n"
        "- Python, JavaScript, React\n"
        "- SQL, data analysis\n\n"
        "About the role:\n"
        "Build scalable backend services and data pipelines.\n"
    )
    return jd_path


class TestFullPipeline:
    """Run the full E2E pipeline: init → import → score → predict → pack → dry-run → mark-submitted → retro → status → bump-rubric."""

    def test_step1_init(self, project_dir: Path):
        """Init creates all directories and files."""
        args = _Args()
        _cmd_init(args)

        assert (project_dir / ".job-state.json").exists()
        assert (project_dir / "PROFILE.md").exists()
        assert (project_dir / "jobs" / "normalized").is_dir()
        assert (project_dir / "predictions").is_dir()
        assert (project_dir / "retros").is_dir()

    def test_step2_import(self, project_dir: Path, sample_jd_file: Path):
        """Import normalizes JD and writes YAML."""
        _cmd_init(_Args())

        args = _Args(file=str(sample_jd_file))
        _cmd_import(args)

        # Check YAML was written
        norm_dir = project_dir / "jobs" / "normalized"
        yaml_files = list(norm_dir.glob("*.yaml"))
        assert len(yaml_files) == 1

        data = yaml.safe_load(yaml_files[0].read_text())
        assert data["title"] == "Software Engineer Intern"
        assert data["company"] == "Acme Labs"
        assert "Python" in data["skills"]

        # Check state updated
        state = json.loads((project_dir / ".job-state.json").read_text())
        assert len(state["jobs"]) == 1
        job_id = list(state["jobs"].keys())[0]
        assert state["jobs"][job_id]["status"] == "imported"

    def test_step3_score(self, project_dir: Path, sample_jd_file: Path):
        """Score produces all dimensions and updates state."""
        _cmd_init(_Args())
        args = _Args(file=str(sample_jd_file))
        _cmd_import(args)

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        args = _Args(job=job_id)
        _cmd_score(args)

        state = json.loads((project_dir / ".job-state.json").read_text())
        scores = state["jobs"][job_id].get("scores", {})
        for dim in ("fit", "evidence", "opportunity", "strategic", "friction", "risk"):
            assert dim in scores, f"Missing dimension: {dim}"
            assert 0.0 <= scores[dim] <= 10.0
        assert "final_score" in scores
        assert state["jobs"][job_id]["status"] == "scored"

    def test_step4_predict(self, project_dir: Path, sample_jd_file: Path):
        """Prediction is immutable and updates state."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_score(_Args(job=job_id))
        _cmd_predict(_Args(job=job_id, new_version=False))

        # Check prediction file exists
        pred_files = list((project_dir / "predictions").glob(f"{job_id}_v*.json"))
        assert len(pred_files) == 1

        pred = json.loads(pred_files[0].read_text())
        assert pred["job_id"] == job_id
        assert pred["decision"] in ("apply", "skip", "save_for_later")
        assert 0.0 <= pred["final_score"] <= 10.0

        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state["jobs"][job_id]["status"] == "predicted"

        # Second predict without --new-version should fail
        with pytest.raises(SystemExit):
            _cmd_predict(_Args(job=job_id, new_version=False))

        # With --new-version should succeed
        _cmd_predict(_Args(job=job_id, new_version=True))
        pred_files = list((project_dir / "predictions").glob(f"{job_id}_v*.json"))
        assert len(pred_files) == 2

    def test_step5_pack(self, project_dir: Path, sample_jd_file: Path):
        """Pack generates all required files."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_score(_Args(job=job_id))
        _cmd_predict(_Args(job=job_id, new_version=False))
        _cmd_pack(_Args(job=job_id))

        pack_dir = project_dir / "applications" / job_id
        assert pack_dir.is_dir()

        required_files = [
            "jd.md", "prediction.md", "resume_targeted.md",
            "greeting.md", "cover_letter.md", "form_answers.md",
            "submit_checklist.md",
        ]
        for fname in required_files:
            fpath = pack_dir / fname
            assert fpath.exists(), f"Missing pack file: {fname}"
            content = fpath.read_text()
            assert len(content) > 10, f"Pack file {fname} is too short"

        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state["jobs"][job_id]["status"] == "packed"

    def test_step6_dry_run(self, project_dir: Path, sample_jd_file: Path):
        """Dry-run fills mock form without submitting."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_score(_Args(job=job_id))
        _cmd_predict(_Args(job=job_id, new_version=False))
        _cmd_pack(_Args(job=job_id))
        _cmd_dry_run(_Args(job=job_id))

        # No form submission happened — we just verify it didn't crash
        # and the pack dir still exists
        assert (project_dir / "applications" / job_id).is_dir()

    def test_step7_mark_submitted(self, project_dir: Path, sample_jd_file: Path):
        """Mark submission records metadata."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_mark_submitted(_Args(job=job_id, channel="greenhouse"))

        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state["jobs"][job_id].get("submitted_at") is not None
        assert state["jobs"][job_id].get("submission_channel") == "greenhouse"
        assert "retro" in state["jobs"][job_id]

    def test_step8_retro(self, project_dir: Path, sample_jd_file: Path):
        """Retro records status at 3d/14d/30d."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_mark_submitted(_Args(job=job_id, channel="lever"))
        _cmd_retro(_Args(job=job_id, status_3d="ack_received", status_14d=None, status_30d=None))

        retro_file = project_dir / "retros" / f"{job_id}.json"
        assert retro_file.exists()
        retro = json.loads(retro_file.read_text())
        assert retro["status_3d"] == "ack_received"
        assert retro["interview_received"] is False

        # Record 14d with interview
        _cmd_retro(_Args(job=job_id, status_3d=None, status_14d="phone_screen", status_30d=None))
        retro = json.loads(retro_file.read_text())
        assert retro["status_14d"] == "phone_screen"
        assert retro["interview_received"] is True

    def test_step9_status(self, project_dir: Path, sample_jd_file: Path):
        """Status updates STATUS.md with correct counts."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_status(_Args())

        status_md = (project_dir / "STATUS.md").read_text()
        assert "Pipeline" in status_md
        assert "1" in status_md  # one job imported

    def test_step10_bump_rubric(self, project_dir: Path, sample_jd_file: Path):
        """Bump-rubric creates comparison report without overwriting active rubric."""
        _cmd_init(_Args())
        _cmd_import(_Args(file=str(sample_jd_file)))

        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_score(_Args(job=job_id))
        _cmd_predict(_Args(job=job_id, new_version=False))
        _cmd_mark_submitted(_Args(job=job_id, channel="email"))
        _cmd_retro(_Args(job=job_id, status_3d="ack", status_14d="interview", status_30d="offer"))

        # Create a candidate rubric
        candidate_rubric = project_dir / "rubrics" / "v1_candidate.md"
        candidate_rubric.write_text(
            "# Rubric v1 Candidate\n\n"
            "### 1. Skill Match (weight: 35%)\n"
            "### 2. Evidence (weight: 25%)\n"
            "### 3. Opportunity (weight: 20%)\n"
            "### 4. Strategic (weight: 10%)\n"
            "### 5. Friction (weight: 5%)\n"
            "### 6. Risk (weight: 5%)\n"
        )

        _cmd_bump_rubric(_Args(new_rubric=str(candidate_rubric)))

        # Active rubric should NOT have changed
        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state.get("active_rubric") == "v0_student_internship"

    def test_full_pipeline_sequential(self, project_dir: Path, sample_jd_file: Path):
        """Run all steps in sequence end-to-end."""
        # Step 1: Init
        _cmd_init(_Args())
        assert (project_dir / ".job-state.json").exists()

        # Step 2: Import
        _cmd_import(_Args(file=str(sample_jd_file)))
        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        # Step 3: Score
        _cmd_score(_Args(job=job_id))
        state = json.loads((project_dir / ".job-state.json").read_text())
        assert "scores" in state["jobs"][job_id]
        assert state["jobs"][job_id]["scores"]["final_score"] > 0

        # Step 4: Predict
        _cmd_predict(_Args(job=job_id, new_version=False))
        pred_files = list((project_dir / "predictions").glob(f"{job_id}_v*.json"))
        assert len(pred_files) == 1

        # Step 5: Pack
        _cmd_pack(_Args(job=job_id))
        pack_dir = project_dir / "applications" / job_id
        assert len(list(pack_dir.glob("*.md"))) == 7

        # Step 6: Dry-run
        _cmd_dry_run(_Args(job=job_id))

        # Step 7: Mark submitted
        _cmd_mark_submitted(_Args(job=job_id, channel="manual"))
        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state["jobs"][job_id].get("submitted_at") is not None

        # Step 8: Retro
        _cmd_retro(_Args(job=job_id, status_3d="ack", status_14d="interview", status_30d="offer"))
        retro = json.loads((project_dir / "retros" / f"{job_id}.json").read_text())
        assert retro["offer_received"] is True

        # Step 9: Status
        _cmd_status(_Args())
        assert (project_dir / "STATUS.md").exists()

        # Step 10: Bump rubric
        candidate = project_dir / "rubrics" / "v1_test.md"
        candidate.write_text("# V1 Test\n\n### 1. Fit (weight: 30%)\n### 2. Evidence (weight: 25%)\n")
        _cmd_bump_rubric(_Args(new_rubric=str(candidate)))
        state = json.loads((project_dir / ".job-state.json").read_text())
        assert state["active_rubric"] == "v0_student_internship"  # unchanged


class TestRetroFreeformCLI:
    """CLI integration for job retro-freeform command."""

    def test_retro_freeform_writes_files(self, project_dir: Path) -> None:
        """Full pipeline: init → import → retro-freeform → verify files."""
        _cmd_init(_Args())

        # Create a sample JD file since init doesn't include one
        raw_dir = project_dir / "jobs" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        jd_path = raw_dir / "sample_jd.md"
        jd_path.write_text("# Software Engineer Intern\n\nCompany: TestCo\nLocation: Remote\n")

        _cmd_import(_Args(file=str(jd_path)))

        # Find job ID from state
        state = json.loads((project_dir / ".job-state.json").read_text())
        job_id = list(state["jobs"].keys())[0]

        _cmd_retro_freeform(_Args(
            job=job_id,
            text="Applied, no response after 5 days.",
            lesson=["Always follow up", "Tailor resume to JD keywords"],
        ))

        # Verify retro file
        retro_path = project_dir / "retros" / f"{job_id}.json"
        assert retro_path.exists()
        data = json.loads(retro_path.read_text())
        assert len(data["freeform_retros"]) == 1
        assert data["freeform_retros"][0]["text"] == "Applied, no response after 5 days."
        assert "Always follow up" in data["freeform_retros"][0]["lessons"]

        # Verify lessons.md
        lessons_path = project_dir / "lessons.md"
        assert lessons_path.exists()
        content = lessons_path.read_text()
        assert "- Always follow up" in content
        assert "- Tailor resume to JD keywords" in content
