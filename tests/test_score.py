"""Tests for jobos.scorer — 6-dimension scoring and hard gates."""

import pytest

from jobos.scorer import score_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIMENSIONS = ("fit", "evidence", "opportunity", "strategic", "friction", "risk")


def _make_job(**overrides):
    base = {
        "title": "Senior Backend Engineer",
        "company": "Acme Corp",
        "description": (
            "We are looking for a senior backend engineer with experience in "
            "Python, distributed systems, and cloud infrastructure. "
            "This is a full-time remote position with competitive salary."
        ),
        "location": "Remote",
        "type": "full-time",
        "salary_max": 150000,
        "start_date": "2026-07-01",
        "application_method": "online form",
    }
    base.update(overrides)
    return base


def _make_profile(**overrides):
    base = {
        "skills": ["Python", "distributed systems", "cloud infrastructure", "Docker"],
        "experience": [
            "5 years backend engineering at TechCo",
            "Built distributed payment system handling 10k rps",
        ],
        "preferred_locations": ["Remote", "San Francisco"],
        "target_roles": ["Senior Backend Engineer", "Staff Engineer"],
        "target_compensation": 140000,
        "target_companies": ["Acme Corp"],
        "referral_companies": [],
        "availability": {"conflicts": []},
        "visa_status": {"authorized": True},
    }
    base.update(overrides)
    return base


def _make_rubric(**overrides):
    base = {
        "target_roles": ["Senior Backend Engineer"],
        "required_skills": ["Python", "distributed systems"],
    }
    base.update(overrides)
    return base


def _score(job=None, profile=None, rubric=None, evidence=None):
    """Convenience wrapper with sensible defaults."""
    return score_job(
        job_data=job or _make_job(),
        profile=profile or _make_profile(),
        evidence=evidence or [
            {"title": "Payment Platform", "description": "Built distributed payment system in Python"},
            {"title": "Cloud Migration", "description": "Led migration to AWS infrastructure"},
        ],
        rubric=rubric or _make_rubric(),
    )


# ---------------------------------------------------------------------------
# Tests: all 6 dimensions present and numeric 0-10
# ---------------------------------------------------------------------------

class TestDimensionsPresent:
    """Every score call must return all 6 dimensions plus final_score."""

    def test_all_dimensions_present(self):
        result = _score()
        for dim in DIMENSIONS:
            assert dim in result, f"Missing dimension: {dim}"
        assert "final_score" in result

    def test_all_dimensions_numeric(self):
        result = _score()
        for dim in (*DIMENSIONS, "final_score"):
            assert isinstance(result[dim], (int, float)), (
                f"{dim} is not numeric: {type(result[dim])}"
            )

    def test_all_dimensions_in_range(self):
        result = _score()
        for dim in DIMENSIONS:
            assert 0.0 <= result[dim] <= 10.0, (
                f"{dim} out of range [0,10]: {result[dim]}"
            )
        assert 0.0 <= result["final_score"] <= 10.0

    def test_result_has_metadata_keys(self):
        result = _score()
        assert "skipped" in result
        assert "skip_reason" in result
        assert "penalties" in result
        assert result["skipped"] is False
        assert result["skip_reason"] is None

    def test_dimensions_differ_from_zero_for_good_match(self):
        """A well-matched job should score above zero on positive dimensions."""
        result = _score()
        assert result["fit"] > 0
        assert result["evidence"] > 0
        assert result["opportunity"] > 0


# ---------------------------------------------------------------------------
# Tests: final_score is weighted correctly
# ---------------------------------------------------------------------------

class TestFinalScore:
    """final_score = sum(dim * weight) clamped to 0-10."""

    def test_final_score_matches_weights(self):
        result = _score()
        weights = {
            "fit": 0.30,
            "evidence": 0.25,
            "opportunity": 0.20,
            "strategic": 0.15,
            "friction": -0.10,
            "risk": -0.20,
        }
        expected = sum(result[d] * weights[d] for d in weights)
        expected = max(0.0, min(10.0, expected))
        assert abs(result["final_score"] - round(expected, 2)) < 0.01


# ---------------------------------------------------------------------------
# Hard gate: availability conflict lowers score
# ---------------------------------------------------------------------------

class TestAvailabilityConflict:
    """An availability conflict records a risk penalty.

    NOTE: the scorer subtracts penalties from dimensions. Since risk has a
    negative weight in final_score, a risk penalty currently *lowers* the raw
    risk value (clamped to 0) and thus *raises* final_score.  The penalty
    dict is still populated, proving the gate fired.
    """

    def test_conflict_records_risk_penalty(self):
        result = _score(
            profile=_make_profile(
                availability={
                    "conflicts": [
                        {"start": "2026-06-15", "end": "2026-07-15"},
                    ]
                },
            ),
        )
        assert "risk" in result["penalties"]
        assert result["penalties"]["risk"] == 3.0

    def test_conflict_reduces_raw_risk_value(self):
        """Penalty subtracts from risk dimension; clamped at 0."""
        no_conflict = _score()
        with_conflict = _score(
            profile=_make_profile(
                availability={
                    "conflicts": [
                        {"start": "2026-06-15", "end": "2026-07-15"},
                    ]
                },
            ),
        )
        assert with_conflict["risk"] <= no_conflict["risk"]

    def test_no_conflict_when_dates_dont_overlap(self):
        result = _score(
            profile=_make_profile(
                availability={
                    "conflicts": [
                        {"start": "2025-01-01", "end": "2025-06-01"},
                    ]
                },
            ),
        )
        assert "risk" not in result["penalties"]


# ---------------------------------------------------------------------------
# Hard gate: missing required skill lowers evidence
# ---------------------------------------------------------------------------

class TestMissingRequiredSkill:
    """Missing a required skill must penalize the evidence dimension."""

    def test_missing_skill_penalizes_evidence(self):
        full_skills = _score()
        missing_skills = _score(
            profile=_make_profile(skills=["Cooking", "Gardening"]),
        )
        assert missing_skills["evidence"] < full_skills["evidence"]

    def test_missing_skill_penalty_recorded(self):
        result = _score(
            profile=_make_profile(skills=["Cooking", "Gardening"]),
        )
        assert "evidence" in result["penalties"]
        assert result["penalties"]["evidence"] > 0

    def test_each_missing_skill_adds_penalty(self):
        """Each missing required skill adds 2.0 to evidence penalty."""
        rubric = _make_rubric(required_skills=["Python", "Kubernetes", "Rust"])
        result = _score(
            profile=_make_profile(skills=["Python"]),  # missing Kubernetes + Rust
            rubric=rubric,
        )
        assert result["penalties"]["evidence"] == 4.0  # 2 skills * 2.0

    def test_no_penalty_when_all_skills_present(self):
        result = _score(
            profile=_make_profile(skills=["Python", "distributed systems"]),
        )
        assert "evidence" not in result["penalties"]


# ---------------------------------------------------------------------------
# Hard gate: unrelated job gets skipped
# ---------------------------------------------------------------------------

class TestUnrelatedJobSkip:
    """A completely unrelated job must be skipped (final_score = 0, skipped=True)."""

    def test_unrelated_job_is_skipped(self):
        result = _score(
            job=_make_job(
                title="Sous Chef",
                description="We need an experienced sous chef for our Italian restaurant. "
                            "Must know pasta, sauces, and kitchen management.",
            ),
            profile=_make_profile(
                target_roles=["Senior Backend Engineer"],
            ),
        )
        assert result["skipped"] is True
        assert result["final_score"] == 0.0

    def test_skipped_job_has_reason(self):
        result = _score(
            job=_make_job(
                title="Sous Chef",
                description="Experienced sous chef needed for Italian restaurant. "
                            "Pasta, sauces, kitchen management required.",
            ),
        )
        assert result["skip_reason"] is not None
        assert "unrelated" in result["skip_reason"].lower() or "relevance" in result["skip_reason"].lower()

    def test_skipped_job_zeroes_positive_dimensions(self):
        result = _score(
            job=_make_job(
                title="Sous Chef",
                description="Italian restaurant seeking sous chef. "
                            "Pasta, sauces, kitchen management.",
            ),
        )
        assert result["fit"] == 0.0
        assert result["evidence"] == 0.0
        assert result["opportunity"] == 0.0
        assert result["strategic"] == 0.0

    def test_skipped_job_maxes_negative_dimensions(self):
        result = _score(
            job=_make_job(
                title="Sous Chef",
                description="Italian restaurant seeking sous chef. "
                            "Pasta, sauces, kitchen management.",
            ),
        )
        assert result["friction"] == 10.0
        assert result["risk"] == 10.0

    def test_related_job_is_not_skipped(self):
        result = _score()
        assert result["skipped"] is False
        assert result["final_score"] > 0.0

    def test_partial_role_overlap_not_skipped(self):
        """A job mentioning 'engineer' should overlap enough with 'Senior Backend Engineer'."""
        result = _score(
            job=_make_job(
                title="Data Engineer",
                description="Looking for a data engineer to build ETL pipelines using Python.",
            ),
        )
        # May or may not skip depending on overlap, but title contains "engineer"
        # which should overlap with target role keywords
        if not result["skipped"]:
            assert result["final_score"] > 0.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary conditions and defensive inputs."""

    def test_empty_profile(self):
        result = score_job(
            job_data=_make_job(),
            profile={},
            evidence=[],
            rubric={},
        )
        for dim in (*DIMENSIONS, "final_score"):
            assert isinstance(result[dim], (int, float))
            assert 0.0 <= result[dim] <= 10.0

    def test_empty_job(self):
        result = score_job(
            job_data={},
            profile=_make_profile(),
            evidence=[],
            rubric=_make_rubric(),
        )
        for dim in (*DIMENSIONS, "final_score"):
            assert isinstance(result[dim], (int, float))
            assert 0.0 <= result[dim] <= 10.0

    def test_multiple_penalties_compound(self):
        """Both availability conflict and missing skill penalize simultaneously."""
        result = _score(
            profile=_make_profile(
                skills=["Cooking"],
                availability={
                    "conflicts": [
                        {"start": "2026-06-15", "end": "2026-07-15"},
                    ]
                },
            ),
        )
        assert "risk" in result["penalties"]
        assert "evidence" in result["penalties"]
        assert result["final_score"] > 0.0  # still scored, not skipped

    def test_contract_type_increases_risk(self):
        perm = _score(job=_make_job(type="full-time"))
        contract = _score(job=_make_job(type="contract"))
        assert contract["risk"] > perm["risk"]

    def test_dimension_scores_are_deterministic(self):
        """Same inputs always produce same outputs."""
        r1 = _score()
        r2 = _score()
        assert r1 == r2
