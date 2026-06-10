"""Milestone 4B: Verify no unsupported defaults in generated packs."""

import pytest

from jobos.pack_generator import generate_pack


def _prediction() -> dict:
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


def _job() -> dict:
    return {
        "job_id": "test-001",
        "title": "Intern",
        "company": "Acme",
        "location": "NYC",
        "skills_required": [],
    }


def _minimal_profile() -> dict:
    """Profile with NO work_arrangement and NO notice constraint."""
    return {
        "name": "Alex",
        "school": "State U",
        "major": "Biology",
        "degree": "BS",
        "graduation_date": "2027-05",
        "location": "Somewhere",
        "skills": {"programming_languages": [], "frameworks": [], "domains": []},
        "education": [{"institution": "State U", "degree": "BS", "major": "Biology"}],
    }


# ---------------------------------------------------------------------------
# submit_checklist uses correct command syntax
# ---------------------------------------------------------------------------

class TestChecklistCommandSyntax:
    def test_mark_submitted_has_job_flag(self):
        pack = generate_pack(_job(), _prediction(), _minimal_profile(), [])
        checklist = pack.files["submit_checklist.md"]
        assert "job mark-submitted --job test-001 --channel" in checklist

    def test_mark_submitted_has_channel_placeholder(self):
        pack = generate_pack(_job(), _prediction(), _minimal_profile(), [])
        checklist = pack.files["submit_checklist.md"]
        assert "<manual/channel>" in checklist


# ---------------------------------------------------------------------------
# Missing notice period → TODO
# ---------------------------------------------------------------------------

class TestMissingNoticePeriod:
    def test_no_constraint_produces_todo(self):
        profile = _minimal_profile()
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "TODO: Confirm notice period" in forms
        assert "At least 2 weeks" not in forms

    def test_empty_constraints_produces_todo(self):
        profile = {**_minimal_profile(), "constraints": []}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "TODO: Confirm notice period" in forms

    def test_unrelated_constraint_produces_todo(self):
        profile = {**_minimal_profile(), "constraints": ["Must be enrolled full-time"]}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "TODO: Confirm notice period" in forms


# ---------------------------------------------------------------------------
# Missing work_arrangement → TODO
# ---------------------------------------------------------------------------

class TestMissingWorkArrangement:
    def test_no_work_arrangement_produces_todo(self):
        profile = _minimal_profile()
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "TODO: Confirm work arrangement" in forms
        assert "flexible" not in forms.lower()
        assert "open to remote" not in forms.lower()

    def test_empty_work_arrangement_produces_todo(self):
        profile = {**_minimal_profile(), "work_arrangement": {}}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "TODO: Confirm work arrangement" in forms


# ---------------------------------------------------------------------------
# Explicit values still work
# ---------------------------------------------------------------------------

class TestExplicitValues:
    def test_explicit_notice_constraint(self):
        profile = {**_minimal_profile(), "constraints": ["Requires at least 3 weeks notice"]}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "at least 3 weeks notice" in forms.lower()
        # Notice section should NOT have TODO
        notice_section = forms.split("How much notice")[1] if "How much notice" in forms else ""
        assert "TODO" not in notice_section

    def test_explicit_work_arrangement(self):
        profile = {**_minimal_profile(), "work_arrangement": {"preferred": "hybrid", "open_to_hybrid": True}}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "hybrid" in forms.lower()
        # Work arrangement section should NOT have TODO
        wa_section = forms.split("work arrangement")[1].split("**")[0] if "work arrangement" in forms.lower() else ""
        assert "TODO" not in wa_section

    def test_explicit_work_arrangement_remote_only(self):
        profile = {**_minimal_profile(), "work_arrangement": {"preferred": "remote", "open_to_remote": True}}
        pack = generate_pack(_job(), _prediction(), profile, [])
        forms = pack.files["form_answers.md"]
        assert "remote" in forms.lower()
        wa_section = forms.split("work arrangement")[1].split("**")[0] if "work arrangement" in forms.lower() else ""
        assert "TODO" not in wa_section
