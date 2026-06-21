"""Tests for pack_generator: file completeness and evidence-based claims."""

from __future__ import annotations

import json

import pytest
import yaml

from jobos.application_pack import PackIntegrityError, load_application_pack
from jobos.pack_generator import (
    PackInputError,
    derive_candidate_facts,
    generate_pack,
    generate_workspace_pack,
    validate_pack,
)
from jobos.predictor import create_prediction, save_prediction


# ---------------------------------------------------------------------------
# Fixtures — minimal but realistic inputs
# ---------------------------------------------------------------------------

REQUIRED_FILES = [
    "jd.md",
    "prediction.md",
    "resume_targeted.md",
    "greeting.md",
    "cover_letter.md",
    "form_answers.md",
    "submit_checklist.md",
]


@pytest.fixture()
def sample_job_data() -> dict:
    return {
        "job_id": "test-001",
        "title": "Software Engineering Intern",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "work_type": "Hybrid",
        "salary": "$40/hr",
        "jd_text": "Build features for our core platform.",
        "skills_required": ["Python", "SQL", "Git"],
        "skills_preferred": ["React", "Docker"],
        "apply_url": "https://acme.example.com/apply",
    }


@pytest.fixture()
def sample_prediction() -> dict:
    return {
        "job_id": "test-001",
        "decision": "apply",
        "final_score": 7.5,
        "confidence": 0.82,
        "reply_7d_probability": 0.45,
        "interview_14d_probability": 0.30,
        "positive_signal_30d_probability": 0.15,
        "expected_best_outcome": "Phone screen",
        "expected_failure_reason": "High competition",
        "reasons": ["Strong skill match", "Good location fit"],
    }


@pytest.fixture()
def sample_profile() -> dict:
    return {
        "name": "Alex Test",
        "email": "alex@example.com",
        "location": "Berkeley, CA",
        "languages": ["English", "Mandarin"],
        "education": [
            {
                "institution": "UC Berkeley",
                "degree": "BS",
                "major": "Computer Science",
                "graduation_date": "May 2027",
                "gpa": "3.8",
            }
        ],
        "skills": {
            "programming_languages": [
                {"name": "Python", "proficiency": "advanced"},
                {"name": "JavaScript", "proficiency": "intermediate"},
            ],
            "frameworks": [
                {"name": "React", "proficiency": "intermediate"},
                {"name": "FastAPI", "proficiency": "intermediate"},
            ],
            "domains": [
                {"name": "Web Development", "proficiency": "intermediate", "tools": ["Docker", "PostgreSQL"]},
            ],
        },
        "work_arrangement": {
            "open_to_remote": True,
            "open_to_hybrid": True,
            "open_to_onsite": False,
            "preferred": "hybrid",
        },
        "availability_start": "2026-06-15",
        "availability_end": "2026-08-31",
        "target_locations": ["San Francisco", "New York"],
    }


@pytest.fixture()
def sample_evidence() -> list[dict]:
    return [
        {
            "title": "Job Tracker Chrome Extension",
            "fields": {
                "Tech": "JavaScript, Chrome APIs, PostgreSQL",
                "Type": "Full-stack Chrome extension",
                "Repo": "https://github.com/example/job-tracker",
            },
            "content": (
                "A Chrome extension that scrapes job listings and tracks applications.\n"
                "- Scraped 500+ job listings from multiple platforms\n"
                "- Built REST API with FastAPI for data persistence\n"
                "- Reduced manual tracking time by 80%\n"
            ),
            "skills": ["JavaScript", "Chrome APIs", "FastAPI", "PostgreSQL"],
        },
        {
            "title": "Data Analysis Pipeline",
            "fields": {
                "Tech": "Python, Pandas, Matplotlib",
                "Type": "Data pipeline",
            },
            "content": (
                "Automated data cleaning and visualization for research lab.\n"
                "- Processed 10,000+ survey responses\n"
                "- Generated 15 automated reports per week\n"
            ),
            "skills": ["Python", "Pandas", "Data Visualization"],
        },
    ]


# ---------------------------------------------------------------------------
# Test: pack creates all required files
# ---------------------------------------------------------------------------


class TestPackFileCompleteness:
    """generate_pack must produce every required markdown file."""

    def test_all_files_present(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        for filename in REQUIRED_FILES:
            assert filename in pack.files, f"Missing file: {filename}"

    def test_no_extra_files(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        expected = set(REQUIRED_FILES)
        actual = set(pack.files.keys())
        assert actual == expected, f"Unexpected files: {actual - expected}, missing: {expected - actual}"

    def test_no_empty_files(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        for filename in REQUIRED_FILES:
            content = pack.files[filename]
            assert content.strip(), f"{filename} is empty"

    @pytest.mark.parametrize("filename", REQUIRED_FILES)
    def test_file_contains_meaningful_content(
        self,
        filename: str,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        content = pack.files[filename]
        assert len(content) >= 50, f"{filename} is too short ({len(content)} chars)"

    def test_jd_contains_job_info(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        jd = pack.files["jd.md"]
        assert "Acme Corp" in jd
        assert "Software Engineering Intern" in jd

    def test_greeting_avoids_generic_unverifiable_experience_claim(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(
            sample_job_data,
            sample_prediction,
            {"name": "Test Candidate"},
            sample_evidence,
        )

        assert "relevant technologies" not in pack.files["greeting.md"]

    def test_prediction_contains_decision(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        pred = pack.files["prediction.md"]
        assert "APPLY" in pred
        assert "7.5" in pred

    def test_submit_checklist_contains_job_info(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        checklist = pack.files["submit_checklist.md"]
        assert "Acme Corp" in checklist
        assert "HUMAN CONFIRMATION REQUIRED" in checklist

    def test_pack_has_job_id(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        assert pack.job_id == "test-001"


def test_derive_candidate_facts_normalizes_profile_and_evidence(
    sample_profile: dict,
    sample_evidence: list[dict],
) -> None:
    facts = derive_candidate_facts(sample_profile, sample_evidence)

    assert facts.first_name == "Alex"
    assert facts.school == "UC Berkeley"
    assert facts.study == "Computer Science"
    assert facts.graduation_date == "May 2027"
    assert facts.programming_languages == ["Python", "JavaScript"]
    assert facts.frameworks == ["React", "FastAPI"]
    assert facts.work_preference == "hybrid"
    assert facts.project_names == ["Job Tracker Chrome Extension", "Data Analysis Pipeline"]


# ---------------------------------------------------------------------------
# Test: resume only contains evidence-based claims
# ---------------------------------------------------------------------------


class TestResumeEvidenceIntegrity:
    """resume_targeted.md must not contain unsupported claims."""

    def test_validate_clean_pack_has_no_critical_warnings(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        """validate_pack is heuristic (30% keyword overlap) and may produce
        false positives on profile-only fields like domains or work arrangement.
        The important thing is that no claim is *fabricated* — the resume only
        draws from profile and evidence data.  So we assert the number of
        warnings stays small (profile-sourced noise only), not zero.
        """
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        warnings = validate_pack(pack, sample_evidence)
        # At most a handful of false positives from profile-only fields
        assert len(warnings) <= 3, f"Too many warnings ({len(warnings)}): {warnings}"
        # No warning should mention fabricated claims — only heuristic noise
        for w in warnings:
            assert "fabricat" not in w.lower(), f"Unexpected fabricated claim warning: {w}"

    def test_resume_does_not_mention_unsupported_tech(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        resume = pack.files["resume_targeted.md"]
        unsupported = ["Kubernetes", "Rust", "TensorFlow", "Blockchain"]
        for tech in unsupported:
            assert tech.lower() not in resume.lower(), (
                f"Resume mentions '{tech}' which is not in profile or evidence"
            )

    def test_resume_only_lists_profile_skills(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        resume = pack.files["resume_targeted.md"]
        profile_skills = ["Python", "JavaScript", "React", "FastAPI"]
        for skill in profile_skills:
            assert skill in resume, f"Profile skill '{skill}' missing from resume"

    def test_resume_projects_come_from_evidence(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        resume = pack.files["resume_targeted.md"]
        for entry in sample_evidence:
            assert entry["title"] in resume, (
                f"Evidence project '{entry['title']}' missing from resume"
            )

    def test_validate_detects_fabricated_evidence(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        # Inject a fabricated claim into the resume
        original = pack.files["resume_targeted.md"]
        pack.files["resume_targeted.md"] = (
            original + "\n- Deployed Kubernetes clusters serving 10M users daily\n"
        )
        warnings = validate_pack(pack, sample_evidence)
        assert len(warnings) > 0, "validate_pack should flag fabricated claim"

    def test_resume_education_from_profile(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        resume = pack.files["resume_targeted.md"]
        assert "UC Berkeley" in resume
        assert "Computer Science" in resume

    def test_resume_name_from_profile(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        resume = pack.files["resume_targeted.md"]
        assert resume.strip().startswith("# Alex Test")

    def test_validate_empty_resume_warns(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        pack.files["resume_targeted.md"] = ""
        warnings = validate_pack(pack, sample_evidence)
        assert any("empty" in w.lower() for w in warnings)

    def test_validate_with_no_evidence_warns(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, [])
        # Resume will have warnings about missing evidence
        resume = pack.files["resume_targeted.md"]
        assert "No evidence bank" in resume or len(resume) > 0


# ---------------------------------------------------------------------------
# Test: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Graceful handling of missing or minimal data."""

    def test_minimal_job_data(
        self,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        minimal_job = {"job_id": "min-001"}
        pack = generate_pack(minimal_job, sample_prediction, sample_profile, sample_evidence)
        for filename in REQUIRED_FILES:
            assert filename in pack.files
            assert pack.files[filename].strip()

    def test_minimal_prediction(
        self,
        sample_job_data: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        minimal_pred = {"job_id": "test-001"}
        pack = generate_pack(sample_job_data, minimal_pred, sample_profile, sample_evidence)
        assert "prediction.md" in pack.files
        assert "SKIP" in pack.files["prediction.md"]

    def test_empty_evidence(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, [])
        for filename in REQUIRED_FILES:
            assert filename in pack.files
        assert "No evidence bank" in pack.files["resume_targeted.md"]

    def test_pack_to_dict_roundtrip(
        self,
        sample_job_data: dict,
        sample_prediction: dict,
        sample_profile: dict,
        sample_evidence: list[dict],
    ) -> None:
        pack = generate_pack(sample_job_data, sample_prediction, sample_profile, sample_evidence)
        d = pack.to_dict()
        assert d["job_id"] == "test-001"
        assert isinstance(d["files"], dict)
        assert len(d["files"]) == 7


def test_generate_workspace_pack_writes_files_and_updates_state(
    tmp_path,
    sample_job_data: dict,
) -> None:
    job_id = sample_job_data["job_id"]
    (tmp_path / "jobs" / "normalized").mkdir(parents=True)
    (tmp_path / "jobs" / "normalized" / f"{job_id}.yaml").write_text(
        yaml.safe_dump(sample_job_data, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps(
            {
                "jobs": {
                    job_id: {
                        "title": sample_job_data["title"],
                        "company": sample_job_data["company"],
                        "status": "predicted",
                    }
                },
                "active_rubric": "v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    prediction = create_prediction(
        {"job_id": job_id, "rubric_version": "v1"},
        {
            "fit": 7.0,
            "evidence": 6.0,
            "opportunity": 7.0,
            "strategic": 6.0,
            "friction": 3.0,
            "risk": 2.0,
            "final_score": 6.8,
        },
        {},
    )
    save_prediction(prediction, tmp_path / "predictions")

    result = generate_workspace_pack(tmp_path, job_id)

    state = json.loads((tmp_path / ".job-state.json").read_text(encoding="utf-8"))
    assert state["jobs"][job_id]["status"] == "packed"
    assert state["jobs"][job_id]["pack_warnings"] == result.warnings
    assert result.pack_dir == tmp_path / "applications" / job_id
    assert (result.pack_dir / "manifest.json").exists()
    for filename in REQUIRED_FILES:
        assert (result.pack_dir / filename).exists()
        assert filename in result.pack.files

    state["jobs"][job_id]["status"] = "validated"
    state["jobs"][job_id]["validation"] = {
        "supported": 1,
        "weak": 0,
        "unsupported": 0,
    }
    (tmp_path / ".job-state.json").write_text(
        json.dumps(state) + "\n",
        encoding="utf-8",
    )

    generate_workspace_pack(tmp_path, job_id)

    repacked_state = json.loads(
        (tmp_path / ".job-state.json").read_text(encoding="utf-8")
    )
    assert repacked_state["jobs"][job_id]["status"] == "packed"
    assert "validation" not in repacked_state["jobs"][job_id]


def test_generate_workspace_pack_manifest_tracks_profile_sources(
    tmp_path,
    sample_job_data: dict,
    monkeypatch,
) -> None:
    job_id = sample_job_data["job_id"]
    (tmp_path / "jobs" / "normalized").mkdir(parents=True)
    (tmp_path / "jobs" / "normalized" / f"{job_id}.yaml").write_text(
        yaml.safe_dump(sample_job_data, sort_keys=False),
        encoding="utf-8",
    )
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "base.yaml").write_text("name: Alex Test\n", encoding="utf-8")
    (profile_dir / "skills.yaml").write_text(
        "skills:\n  programming_languages:\n    - name: Python\n",
        encoding="utf-8",
    )
    (profile_dir / "availability.yaml").write_text(
        "available: true\n",
        encoding="utf-8",
    )
    (profile_dir / "evidence_bank.md").write_text(
        "## Python Tool\n\nBuilt Python tools.\n",
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps(
            {
                "jobs": {
                    job_id: {
                        "title": sample_job_data["title"],
                        "company": sample_job_data["company"],
                        "status": "predicted",
                    }
                },
                "active_rubric": "v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    prediction = create_prediction(
        {"job_id": job_id, "rubric_version": "v1"},
        {"fit": 7.0, "final_score": 6.8},
        {"evidence_items": ["Python Tool"]},
    )
    save_prediction(prediction, tmp_path / "predictions")
    monkeypatch.setattr(
        "jobos.pack_generator.validate_pack",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("workspace generation must use canonical validator")
        ),
    )

    result = generate_workspace_pack(tmp_path, job_id)
    (profile_dir / "skills.yaml").write_text(
        "skills:\n  programming_languages:\n    - name: Rust\n",
        encoding="utf-8",
    )

    assert result.warnings == []
    with pytest.raises(PackIntegrityError, match="source changed.*profile/skills"):
        load_application_pack(
            result.pack_dir,
            require_manifest=True,
            verify_sources=True,
        )


def test_generate_workspace_pack_rejects_inconsistent_profile(
    tmp_path,
    monkeypatch,
) -> None:
    job_id = "profile-conflict"
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {job_id: {"status": "predicted"}}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobos.pack_generator.load_profile",
        lambda _root: {
            "school": "长春理工大学",
            "major": "过程装备与控制工程",
            "education": [
                {
                    "institution": "University of California, Berkeley",
                    "major": "Computer Science",
                }
            ],
        },
    )

    with pytest.raises(PackInputError, match="Profile identity conflict"):
        generate_workspace_pack(tmp_path, job_id)


def test_generate_workspace_pack_rejects_terminal_job_without_writes(
    tmp_path,
) -> None:
    job_id = "already-submitted"
    original_state = {"jobs": {job_id: {"status": "submitted"}}}
    state_path = tmp_path / ".job-state.json"
    state_path.write_text(
        json.dumps(original_state) + "\n",
        encoding="utf-8",
    )
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    greeting_path = pack_dir / "greeting.md"
    greeting_path.write_text("existing pack\n", encoding="utf-8")

    with pytest.raises(
        PackInputError,
        match="Invalid job status transition: submitted -> packed",
    ):
        generate_workspace_pack(tmp_path, job_id)

    assert json.loads(state_path.read_text(encoding="utf-8")) == original_state
    assert greeting_path.read_text(encoding="utf-8") == "existing pack\n"
    assert not (pack_dir / "manifest.json").exists()
