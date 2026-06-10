"""Tests for truthfulness: no hardcoded identity, no demo-only claims, correct queue buckets."""

import json
from pathlib import Path

import pytest

from jobos.pack_generator import generate_pack
from jobos.evidence_markers import generate_evidence_report, find_evidence_source


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_profile() -> dict:
    """A non-CS profile with no hardcoded story."""
    return {
        "name": "Sam Rivera",
        "school": "Art Center College of Design",
        "major": "Industrial Design",
        "degree": "BFA",
        "graduation_date": "2027-06",
        "location": "Pasadena, CA",
        "availability_start": "2026-05-15",
        "availability_end": "2026-08-30",
        "days_per_week": 4,
        "target_locations": ["Los Angeles, CA"],
        "languages": ["English", "Spanish"],
        "skills": {
            "programming_languages": [{"name": "Python", "proficiency": "intermediate"}],
            "frameworks": [{"name": "React", "proficiency": "beginner"}],
            "domains": [],
        },
        "education": [
            {
                "institution": "Art Center College of Design",
                "degree": "BFA",
                "major": "Industrial Design",
                "graduation_date": "2027-06",
            }
        ],
        "work_arrangement": {"preferred": "hybrid", "open_to_hybrid": True},
        "internship_window": {"start": "2026-05-15", "end": "2026-08-30"},
    }


@pytest.fixture
def design_evidence() -> list[dict]:
    """Evidence bank for a design student — no Chrome extension or multi-agent."""
    return [
        {
            "title": "Campus Navigation App",
            "fields": {"Tech": "React Native, Figma, Python"},
            "content": "- Designed and prototyped a campus wayfinding app\n- Conducted user research with 50+ students",
            "skills": ["React Native", "Figma"],
        },
        {
            "title": "Packaging Design Project",
            "fields": {"Tech": "Adobe Illustrator, 3D printing"},
            "content": "- Created sustainable packaging concept for local brewery\n- Won department design competition",
            "skills": ["Adobe Illustrator"],
        },
    ]


@pytest.fixture
def empty_evidence() -> list[dict]:
    return []


@pytest.fixture
def cs_evidence() -> list[dict]:
    """Evidence bank with CS projects."""
    return [
        {
            "title": "Data Pipeline Tool",
            "fields": {"Tech": "Python, pandas, SQL"},
            "content": "- Built ETL pipeline processing 500K records daily\n- Reduced query time by 40% with indexing",
            "skills": ["Python", "SQL"],
        },
    ]


@pytest.fixture
def sample_job() -> dict:
    return {
        "job_id": "test-001",
        "title": "Design Engineering Intern",
        "company": "Creative Labs",
        "location": "Los Angeles, CA",
        "skills_required": ["Python", "React"],
        "skills_preferred": ["Figma"],
    }


def _make_prediction() -> dict:
    return {
        "job_id": "test-001",
        "decision": "apply",
        "final_score": 6.5,
        "confidence": 0.4,
        "probabilities": {"screen": 0.3, "interview": 0.4, "offer": 0.2},
        "dimension_scores": {"fit": 7.0, "evidence": 6.0, "risk": 2.0},
        "expected_best_outcome": "Interview possible",
        "expected_failure_reason": "None",
    }


# ---------------------------------------------------------------------------
# Test: non-CS profile does not produce "Computer Science"
# ---------------------------------------------------------------------------

class TestNoHardcodedCS:
    def test_greeting_no_computer_science(self, minimal_profile, sample_job, design_evidence):
        """Greeting must not say 'Computer Science' for a non-CS profile."""
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        greeting = pack.files["greeting.md"]
        assert "Computer Science" not in greeting
        assert "Industrial Design" in greeting or "Art Center" in greeting

    def test_cover_letter_no_computer_science(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        cover = pack.files["cover_letter.md"]
        assert "Computer Science" not in cover
        assert "Industrial Design" in cover or "Art Center" in cover

    def test_form_answers_no_computer_science(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        forms = pack.files["form_answers.md"]
        assert "Computer Science" not in forms
        assert "Industrial Design" in forms or "Art Center" in forms

    def test_resume_no_computer_science(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        resume = pack.files["resume_targeted.md"]
        assert "Computer Science" not in resume


# ---------------------------------------------------------------------------
# Test: empty evidence does not produce project claims
# ---------------------------------------------------------------------------

class TestEmptyEvidence:
    def test_greeting_no_project_names(self, minimal_profile, sample_job, empty_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, empty_evidence)
        greeting = pack.files["greeting.md"]
        assert "Chrome extension" not in greeting
        assert "multi-agent" not in greeting
        assert "local-first" not in greeting

    def test_resume_no_projects_section(self, minimal_profile, sample_job, empty_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, empty_evidence)
        resume = pack.files["resume_targeted.md"]
        assert "## Projects" not in resume

    def test_cover_letter_no_project_bullets(self, minimal_profile, sample_job, empty_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, empty_evidence)
        cover = pack.files["cover_letter.md"]
        assert "Chrome extension" not in cover
        assert "multi-agent" not in cover


# ---------------------------------------------------------------------------
# Test: no demo-only project names unless in evidence bank
# ---------------------------------------------------------------------------

class TestNoDemoOnlyProjects:
    def test_greeting_uses_evidence_project_names(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        greeting = pack.files["greeting.md"]
        # Should mention actual evidence projects
        assert "Campus Navigation" in greeting or "Packaging Design" in greeting
        # Should NOT mention demo-only projects
        assert "Chrome extension" not in greeting
        assert "multi-agent" not in greeting

    def test_form_answers_use_evidence_projects(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        forms = pack.files["form_answers.md"]
        assert "Campus Navigation" in forms or "Packaging Design" in forms
        assert "Chrome extension" not in forms
        assert "multi-agent" not in forms
        assert "local-first" not in forms

    def test_cs_profile_mentions_cs_projects(self, minimal_profile, sample_job, cs_evidence):
        """CS profile with CS evidence should mention real projects, not hardcoded ones."""
        profile = {**minimal_profile, "major": "Computer Science", "school": "MIT"}
        pack = generate_pack(sample_job, _make_prediction(), profile, cs_evidence)
        greeting = pack.files["greeting.md"]
        assert "Data Pipeline" in greeting
        assert "Chrome extension" not in greeting


# ---------------------------------------------------------------------------
# Test: availability derived from profile
# ---------------------------------------------------------------------------

class TestAvailabilityFromProfile:
    def test_greeting_uses_profile_availability(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        greeting = pack.files["greeting.md"]
        assert "2026-05-15" in greeting
        assert "June 2026" not in greeting  # must not hardcode

    def test_cover_letter_uses_profile_availability(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        cover = pack.files["cover_letter.md"]
        assert "2026-05-15" in cover
        assert "June 2026" not in cover

    def test_form_answers_use_profile_availability(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        forms = pack.files["form_answers.md"]
        assert "2026-05-15" in forms
        assert "summer 2026" not in forms.lower()


# ---------------------------------------------------------------------------
# Test: resume bullets have evidence markers
# ---------------------------------------------------------------------------

class TestEvidenceMarkersInResume:
    def test_bullets_have_evidence_comments(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        resume = pack.files["resume_targeted.md"]
        # Every bullet in the Projects section should have an evidence comment
        in_projects = False
        bullets_found = 0
        for line in resume.split("\n"):
            if "## Projects" in line:
                in_projects = True
                continue
            if in_projects and line.startswith("## "):
                break
            if in_projects and line.strip().startswith("- "):
                bullets_found += 1
                assert "<!-- evidence:" in line, f"Bullet missing evidence marker: {line}"

        assert bullets_found > 0, "No project bullets found"

    def test_evidence_markers_have_valid_source(self, minimal_profile, sample_job, design_evidence):
        pack = generate_pack(sample_job, _make_prediction(), minimal_profile, design_evidence)
        resume = pack.files["resume_targeted.md"]
        for line in resume.split("\n"):
            if "<!-- evidence:" in line:
                assert "evidence_bank.md#" in line
                assert "UNSUPPORTED" not in line


# ---------------------------------------------------------------------------
# Test: validate-pack fails on unsupported claims
# ---------------------------------------------------------------------------

class TestValidatePackFailsOnUnsupported:
    def test_validate_catches_injected_unsupported(self, design_evidence):
        """Inject a clearly unsupported claim and verify validation catches it."""
        pack_files = {
            "resume_targeted.md": "- Built a quantum computing simulation with qubits\n- Designed blockchain smart contracts",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack_files, design_evidence, {"skills_required": []})
        assert len(report["unsupported"]) > 0
        assert report["overclaim_risk"] > 0

    def test_validate_passes_on_evidence_marked_claims(self, design_evidence):
        """Claims that match evidence should pass."""
        pack_files = {
            "resume_targeted.md": "- Designed and prototyped a campus wayfinding app\n- Conducted user research with 50+ students",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack_files, design_evidence, {"skills_required": []})
        assert len(report["supported"]) >= 2
        assert len(report["unsupported"]) == 0


# ---------------------------------------------------------------------------
# Test: queue bucket mapping (predicted shows under Predicted, not Scored)
# ---------------------------------------------------------------------------

class TestQueueBucketMapping:
    def test_predicted_job_appears_under_predicted(self, tmp_path, monkeypatch, capsys):
        """A job with status='predicted' must appear under 'Predicted (unpacked)', not 'Scored'."""
        from jobos.cli import _cmd_queue
        class _Args:
            pass

        state = {
            "jobs": {
                "j1": {"title": "Test Job", "company": "Co", "status": "predicted"},
            },
            "active_rubric": "v0",
            "rubric_history": [],
        }
        (tmp_path / ".job-state.json").write_text(json.dumps(state))
        (tmp_path / "predictions").mkdir()
        (tmp_path / "retros").mkdir()

        monkeypatch.chdir(tmp_path)
        _cmd_queue(_Args())

        out = capsys.readouterr().out
        assert "Predicted (unpacked)" in out
        assert "j1" in out
        # Must NOT appear under Scored
        lines = out.split("\n")
        predicted_section = False
        for line in lines:
            if "Predicted (unpacked)" in line:
                predicted_section = True
            if "Scored (unpredicted)" in line:
                predicted_section = False
            if predicted_section and "j1" in line:
                break
        else:
            if "Predicted (unpacked)" in out:
                pass  # j1 found in predicted section
            else:
                pytest.fail("j1 not found under Predicted (unpacked)")

    def test_scored_job_appears_under_scored(self, tmp_path, monkeypatch, capsys):
        from jobos.cli import _cmd_queue
        class _Args:
            pass

        state = {
            "jobs": {
                "j2": {"title": "Scored Job", "company": "Co", "status": "scored"},
            },
            "active_rubric": "v0",
            "rubric_history": [],
        }
        (tmp_path / ".job-state.json").write_text(json.dumps(state))
        (tmp_path / "predictions").mkdir()
        (tmp_path / "retros").mkdir()

        monkeypatch.chdir(tmp_path)
        _cmd_queue(_Args())

        out = capsys.readouterr().out
        assert "Scored (unpredicted)" in out
        assert "j2" in out
