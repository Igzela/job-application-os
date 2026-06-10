"""Tests for bump_rubric: comparison report generation and active rubric preservation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.rubric_manager import bump_rubric, get_active_rubric, set_active_rubric


# ---------------------------------------------------------------------------
# Fixtures — minimal filesystem scaffolding
# ---------------------------------------------------------------------------

@pytest.fixture()
def project(tmp_path: Path) -> dict:
    """Create a minimal project tree and return paths dict.

    Layout:
        tmp_path/
          rubrics/
            v0_student_internship.md   (active rubric)
          jobs/
            job-alpha.json
            job-beta.json
          predictions/
          retros/
            retro-alpha.json
            retro-beta.json
          profile/
            base.yaml
          .job-state.json
    """
    root = tmp_path
    rubrics_dir = root / "rubrics"
    jobs_dir = root / "jobs"
    predictions_dir = root / "predictions"
    retros_dir = root / "retros"
    profile_dir = root / "profile"

    for d in (rubrics_dir, jobs_dir, predictions_dir, retros_dir, profile_dir):
        d.mkdir()

    # Active rubric (v0)
    v0 = rubrics_dir / "v0_student_internship.md"
    v0.write_text(
        "# v0 Rubric\n\n"
        "### 1. Skill Match (weight: 30%)\n\nScore skill overlap.\n\n"
        "### 2. Role Fit (weight: 20%)\n\nScore role alignment.\n\n"
        "### 3. Compensation (weight: 15%)\n\nScore pay.\n\n"
        "### 4. Company Signal (weight: 15%)\n\nScore brand.\n\n"
        "### 5. Location (weight: 10%)\n\nScore location.\n\n"
        "### 6. Timing (weight: 10%)\n\nScore timing.\n",
        encoding="utf-8",
    )

    # Candidate rubric (v1) — lives outside rubrics/ initially
    v1 = root / "v1_candidate.md"
    v1.write_text(
        "# v1 Candidate Rubric\n\n"
        "### 1. Skill Match (weight: 25%)\n\nScore skill overlap.\n\n"
        "### 2. Role Fit (weight: 25%)\n\nScore role alignment.\n\n"
        "### 3. Compensation (weight: 20%)\n\nScore pay.\n\n"
        "### 4. Company Signal (weight: 10%)\n\nScore brand.\n\n"
        "### 5. Location (weight: 10%)\n\nScore location.\n\n"
        "### 6. Timing (weight: 10%)\n\nScore timing.\n",
        encoding="utf-8",
    )

    # Profile
    profile_dir / "base.yaml".replace("", "")  # touch trick — just write directly
    (profile_dir / "base.yaml").write_text(
        "name: Test Candidate\n"
        "skills:\n  - Python\n  - JavaScript\n  - React\n"
        "target_roles:\n  - backend engineer\n  - data analyst\n"
        "preferred_locations:\n  - remote\n  - San Francisco\n"
        "target_compensation: 50000\n"
        "target_companies:\n  - Acme Corp\n",
        encoding="utf-8",
    )

    # Jobs
    for jid, company, title in [
        ("job-alpha", "Acme Corp", "Backend Engineer Intern"),
        ("job-beta", "StartupXYZ", "Data Analyst Intern"),
    ]:
        (jobs_dir / f"{jid}.json").write_text(
            json.dumps({
                "job_id": jid,
                "title": title,
                "company": company,
                "description": "Python JavaScript data analysis internship",
                "location": "remote",
                "salary_max": 45000,
            }),
            encoding="utf-8",
        )

    # Retros (required for bump to find jobs)
    for jid in ("job-alpha", "job-beta"):
        (retros_dir / f"retro-{jid}.json").write_text(
            json.dumps({"job_id": jid, "outcome_label": "interview"}),
            encoding="utf-8",
        )

    # State file — activate v0
    state_path = root / ".job-state.json"
    state_path.write_text(
        json.dumps({"active_rubric": "v0_student_internship", "rubric_history": []}),
        encoding="utf-8",
    )

    return {
        "root": root,
        "rubrics_dir": rubrics_dir,
        "jobs_dir": jobs_dir,
        "predictions_dir": predictions_dir,
        "retros_dir": retros_dir,
        "state_path": state_path,
        "v0_path": v0,
        "v1_path": v1,
    }


# ---------------------------------------------------------------------------
# Tests: comparison report structure
# ---------------------------------------------------------------------------

class TestBumpRubricReport:
    """bump_rubric returns a comparison report with expected keys and content."""

    def test_report_has_required_keys(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert "candidate" in report
        assert "active_rubric" in report
        assert "jobs_scored" in report
        assert "ranking_old" in report
        assert "ranking_new" in report
        assert "movements" in report
        assert "summary" in report

    def test_report_candidate_info(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        candidate = report["candidate"]
        assert candidate["name"] == "v1_candidate"
        assert "content" in candidate
        assert "weights" in candidate
        assert isinstance(candidate["weights"], dict)

    def test_report_active_rubric_name(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert report["active_rubric"] == "v0_student_internship"

    def test_report_lists_jobs_scored(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert report["jobs_scored"] == 2
        assert len(report["ranking_old"]) == 2
        assert len(report["ranking_new"]) == 2

    def test_report_movements_have_rank_change(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_per_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        ) if False else bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        for movement in report["movements"]:
            assert "job_id" in movement
            assert "old_rank" in movement
            assert "new_rank" in movement
            assert "rank_change" in movement
            assert "score_change" in movement

    def test_report_summary_mentions_candidate_name(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert "v1_candidate" in report["summary"]

    def test_report_summary_contains_note_about_activation(self, project: dict) -> None:
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert "NOT active" in report["summary"]
        assert "set_active_rubric" in report["summary"]


# ---------------------------------------------------------------------------
# Tests: active rubric is NOT overwritten
# ---------------------------------------------------------------------------

class TestBumpRubricPreservesActiveRubric:
    """bump_rubric must not change the active rubric in the state file."""

    def test_active_rubric_unchanged_after_bump(self, project: dict) -> None:
        before = get_active_rubric(project["state_path"])

        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        after = get_active_rubric(project["state_path"])
        assert before == after == "v0_student_internship"

    def test_active_rubric_content_unchanged_after_bump(self, project: dict) -> None:
        original_content = project["v0_path"].read_text(encoding="utf-8")

        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert project["v0_path"].read_text(encoding="utf-8") == original_content

    def test_state_history_not_appended_by_bump(self, project: dict) -> None:
        state = json.loads(project["state_path"].read_text(encoding="utf-8"))
        history_len_before = len(state.get("rubric_history", []))

        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        state_after = json.loads(project["state_path"].read_text(encoding="utf-8"))
        assert len(state_after.get("rubric_history", [])) == history_len_before


# ---------------------------------------------------------------------------
# Tests: candidate rubric saved to rubrics/ but not activated
# ---------------------------------------------------------------------------

class TestBumpRubricCandidateSaved:
    """The candidate is copied into rubrics/ but stays inactive."""

    def test_candidate_copied_to_rubrics_dir(self, project: dict) -> None:
        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        # The candidate's path in the report points to the saved copy
        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        saved_path = Path(report["candidate"]["path"])
        assert saved_path.exists()
        assert saved_path.name == "v1_candidate.md"
        assert saved_path.read_text(encoding="utf-8") == project["v1_path"].read_text(
            encoding="utf-8"
        )

    def test_candidate_not_activated(self, project: dict) -> None:
        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert get_active_rubric(project["state_path"]) == "v0_student_internship"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestBumpRubricEdgeCases:

    def test_no_retros_returns_empty_comparison(self, project: dict) -> None:
        """With no retro files, bump returns a report with zero jobs scored."""
        empty_retros = project["root"] / "empty_retros"
        empty_retros.mkdir()

        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=empty_retros,
            state_path=project["state_path"],
        )

        assert report["jobs_scored"] == 0
        assert report["ranking_old"] == []
        assert report["ranking_new"] == []
        assert report["movements"] == []
        assert "No historical jobs" in report["summary"]

    def test_no_active_rubric_graceful(self, project: dict) -> None:
        """When no rubric is active, old scores default to zero."""
        # Clear active rubric
        state_path = project["state_path"]
        state_path.write_text(
            json.dumps({"active_rubric": None, "rubric_history": []}),
            encoding="utf-8",
        )

        report = bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=state_path,
        )

        assert report["active_rubric"] is None
        assert report["jobs_scored"] == 2
        # Old scores should all be 0.0 since no active rubric
        for jid, score in report["ranking_old"]:
            assert score == 0.0

    def test_candidate_not_overwritten_if_already_exists(self, project: dict) -> None:
        """If the candidate already exists in rubrics/, it is not overwritten."""
        candidate_dest = project["rubrics_dir"] / "v1_candidate.md"
        candidate_dest.write_text("pre-existing content", encoding="utf-8")

        bump_rubric(
            new_rubric_path=project["v1_path"],
            jobs_dir=project["jobs_dir"],
            predictions_dir=project["predictions_dir"],
            retros_dir=project["retros_dir"],
            state_path=project["state_path"],
        )

        assert candidate_dest.read_text(encoding="utf-8") == "pre-existing content"

    def test_missing_rubric_file_raises(self, project: dict) -> None:
        """bump_rubric raises FileNotFoundError for a nonexistent rubric."""
        with pytest.raises(FileNotFoundError):
            bump_rubric(
                new_rubric_path=project["root"] / "nonexistent.md",
                jobs_dir=project["jobs_dir"],
                predictions_dir=project["predictions_dir"],
                retros_dir=project["retros_dir"],
                state_path=project["state_path"],
            )
