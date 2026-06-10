"""Shared pytest fixtures for the Job Application OS test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.models import Prediction as ModelPrediction
from jobos.predictor import FunnelProbabilities, Prediction as PredictorPrediction


# ---------------------------------------------------------------------------
# sample_profile — mirrors the merged output of profile_loader.load_profile()
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_profile() -> dict:
    return {
        "name": "Alex Chen",
        "school": "University of California, Berkeley",
        "major": "Computer Science",
        "degree": "Bachelor of Science",
        "graduation_date": "2027-05-15",
        "location": "Berkeley, CA",
        "target_locations": [
            "San Francisco, CA",
            "Seattle, WA",
            "New York, NY",
            "Austin, TX",
        ],
        "availability_start": "2026-06-01",
        "availability_end": "2026-08-15",
        "days_per_week": 5,
        "languages": ["English", "Mandarin"],
        "skills": [
            "Python",
            "JavaScript",
            "React",
            "pandas",
            "NumPy",
            "scikit-learn",
            "TensorFlow",
            "SQL",
        ],
        "target_roles": [
            "Software Engineer Intern",
            "Machine Learning Intern",
            "Data Analyst Intern",
        ],
        "target_companies": ["Google", "Meta", "Stripe"],
        "referral_companies": ["Google"],
        "preferred_locations": [
            "San Francisco, CA",
            "Seattle, WA",
        ],
        "target_compensation": 45.0,
        "has_referral": False,
        "evidence_items": [
            "DeepSeek Boss Helper project",
            "React dashboard for campus dining",
            "Kaggle competition top 10%",
        ],
        "experience": [
            "Built a full-stack web app with React and Node.js",
            "Developed ML pipeline for recommendation system",
        ],
        "availability": {
            "conflicts": [],
        },
    }


# ---------------------------------------------------------------------------
# sample_jd_text — a realistic job description string
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_jd_text() -> str:
    return (
        "Software Engineer Intern — Summer 2026\n\n"
        "Company: Acme Labs\n"
        "Location: San Francisco, CA (Hybrid)\n"
        "Duration: 10 weeks\n"
        "Compensation: $50/hr\n\n"
        "About the Role:\n"
        "We are looking for a motivated Software Engineer Intern to join our "
        "platform team. You will work on building scalable backend services "
        "and data pipelines that power our core product.\n\n"
        "Requirements:\n"
        "- Currently enrolled in a BS/MS in Computer Science or related field\n"
        "- Proficiency in Python or JavaScript\n"
        "- Familiarity with React, SQL, or similar tools\n"
        "- Strong communication skills\n\n"
        "Nice to Have:\n"
        "- Experience with machine learning frameworks (TensorFlow, PyTorch)\n"
        "- Previous internship experience\n\n"
        "Apply via our careers page. Cover letter optional."
    )


# ---------------------------------------------------------------------------
# sample_job_data — dict form as consumed by scorer.score_job() and predictor
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_job_data(sample_jd_text: str) -> dict:
    return {
        "job_id": "acme-swe-intern-2026",
        "title": "Software Engineer Intern",
        "company": "Acme Labs",
        "source": "LinkedIn",
        "location": "San Francisco, CA",
        "work_type": "hybrid",
        "description": sample_jd_text,
        "salary": "50",
        "salary_max": "50",
        "type": "internship",
        "company_size": "250",
        "application_method": "careers page",
        "rubric_version": "v0",
        "start_date": "2026-06-15",
        "requirements": (
            "Proficiency in Python or JavaScript. "
            "Familiarity with React, SQL. "
            "Strong communication skills."
        ),
        "skills_required": ["Python", "JavaScript", "React", "SQL"],
        "skills_preferred": ["TensorFlow", "PyTorch"],
    }


# ---------------------------------------------------------------------------
# sample_scores — output of scorer.score_job()
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_scores() -> dict:
    return {
        "fit": 7.2,
        "evidence": 6.8,
        "opportunity": 6.5,
        "strategic": 5.5,
        "friction": 3.0,
        "risk": 2.5,
        "final_score": 5.82,
        "skipped": False,
        "skip_reason": None,
        "penalties": {},
    }


# ---------------------------------------------------------------------------
# sample_prediction — a PredictorPrediction (frozen dataclass from predictor.py)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_prediction() -> PredictorPrediction:
    return PredictorPrediction(
        job_id="acme-swe-intern-2026",
        created_at="2026-06-10T12:00:00+00:00",
        rubric_version="v0",
        dimension_scores={
            "fit": 7.2,
            "evidence": 6.8,
            "opportunity": 6.5,
            "strategic": 5.5,
            "friction": 3.0,
            "risk": 2.5,
        },
        final_score=5.82,
        probabilities=FunnelProbabilities(
            screen=0.35,
            interview=0.42,
            offer=0.28,
        ),
        expected_best_outcome="competitive offer likely; strong comp package",
        expected_failure_reason="no strong failure signals",
        confidence=0.34,
        evidence_count=3,
        decision="save_for_later",
        notes="",
        version=1,
    )


# ---------------------------------------------------------------------------
# tmp_state_dir — a tmpdir with the full state directory structure initialized
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory with the expected subdirectory
    structure and an empty .job-state.json."""
    state_file = tmp_path / ".job-state.json"
    state_file.write_text(
        json.dumps({"jobs": {}, "active_rubric": "v0", "rubric_history": []}),
        encoding="utf-8",
    )
    (tmp_path / "predictions").mkdir()
    (tmp_path / "packs").mkdir()
    (tmp_path / "retros").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# mock_evidence — list of evidence items as consumed by scorer.score_job()
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_evidence() -> list[dict]:
    return [
        {
            "title": "DeepSeek Boss Helper",
            "description": (
                "Built a full-stack AI assistant using Python, React, and "
                "FastAPI. Integrated LLM APIs for real-time chat and "
                "document retrieval."
            ),
            "type": "project",
            "tech": ["Python", "React", "FastAPI", "OpenAI API"],
        },
        {
            "title": "Campus Dining Dashboard",
            "description": (
                "Developed an interactive React dashboard for visualizing "
                "campus dining hall traffic patterns using D3.js and "
                "real-time polling."
            ),
            "type": "project",
            "tech": ["React", "D3.js", "Node.js"],
        },
        {
            "title": "Kaggle Tabular Competition",
            "description": (
                "Placed in the top 10% of a Kaggle tabular data competition "
                "using gradient boosting and feature engineering with pandas."
            ),
            "type": "achievement",
            "tech": ["Python", "pandas", "scikit-learn", "XGBoost"],
        },
    ]
