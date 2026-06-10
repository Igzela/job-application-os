"""Tests for the job description importer."""

import os
import tempfile

import pytest
import yaml

from jobos.importer import import_job


SAMPLE_JD = """\
# Senior Python Developer

Company: Acme Corp
Location: San Francisco, CA

## Requirements

Skills: Python, FastAPI, PostgreSQL, Docker, Kubernetes

We are looking for a senior developer to join our platform team.
Must have 5+ years experience with Python and cloud infrastructure.
"""


@pytest.fixture
def sample_jd_text():
    return SAMPLE_JD


@pytest.fixture
def jd_file(sample_jd_text, tmp_path):
    """Write sample JD to a temp file and return its path."""
    p = tmp_path / "senior-python-dev.txt"
    p.write_text(sample_jd_text, encoding="utf-8")
    return str(p)


@pytest.fixture
def jobs_dir(tmp_path):
    return str(tmp_path / "jobs" / "normalized")


def test_import_returns_required_fields(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)

    required_keys = {
        "job_id",
        "title",
        "company",
        "location",
        "skills",
        "source_file",
        "imported_at",
        "raw_content_hash",
    }
    assert required_keys == set(data.keys()), f"Missing keys: {required_keys - set(data.keys())}"


def test_import_extracts_title(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    assert data["title"] == "Senior Python Developer"


def test_import_extracts_company(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    assert data["company"] == "Acme Corp"


def test_import_extracts_location(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    assert data["location"] == "San Francisco, CA"


def test_import_extracts_skills(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    assert data["skills"] == ["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes"]


def test_import_generates_valid_job_id(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    job_id = data["job_id"]
    # format: <timestamp>-<slug>
    assert "-" in job_id
    assert len(job_id) > 10


def test_import_writes_yaml(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)

    yaml_path = os.path.join(jobs_dir, f"{data['job_id']}.yaml")
    assert os.path.isfile(yaml_path)

    with open(yaml_path, encoding="utf-8") as f:
        written = yaml.safe_load(f)
    assert written["job_id"] == data["job_id"]
    assert written["title"] == data["title"]


def test_import_source_file(jd_file, jobs_dir):
    data = import_job(jd_file, jobs_dir)
    assert data["source_file"] == "senior-python-dev.txt"


def test_import_raw_content_hash_is_stable(jd_file, jobs_dir):
    d1 = import_job(jd_file, jobs_dir)
    d2 = import_job(jd_file, jobs_dir)
    assert d1["raw_content_hash"] == d2["raw_content_hash"]


def test_import_minimal_jd(tmp_path, jobs_dir):
    """Importer handles a JD with no extractable fields gracefully."""
    p = tmp_path / "minimal.txt"
    p.write_text("Just a plain text blob with no structure.", encoding="utf-8")

    data = import_job(str(p), jobs_dir)

    assert data["title"] == "Unknown Title"
    assert data["company"] == "Unknown Company"
    assert data["location"] == "Unknown"
    assert data["skills"] == []
