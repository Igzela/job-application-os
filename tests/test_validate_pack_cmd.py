"""Tests for validate-pack command and evidence markers."""

import json
from pathlib import Path

import pytest

from jobos.evidence_markers import (
    find_evidence_source,
    mark_claim,
    generate_evidence_report,
)


@pytest.fixture
def sample_evidence() -> list[dict]:
    return [
        {
            "title": "Project 1: Chrome Extension",
            "fields": {"Tech": "Vue 3, JavaScript, Chrome Extension API"},
            "content": "- Built a Chrome extension from scratch with popup UI\n- Integrated REST API for real-time data",
            "skills": ["JavaScript", "Vue 3"],
        },
        {
            "title": "Project 2: Data Analysis",
            "fields": {"Tech": "Python, pandas, matplotlib"},
            "content": "- Analyzed 100K+ record datasets using pandas\n- Created visualizations with matplotlib",
            "skills": ["Python", "pandas"],
        },
    ]


class TestFindEvidenceSource:
    def test_found(self, sample_evidence):
        src = find_evidence_source("Built a Chrome extension from scratch", sample_evidence)
        assert src is not None
        assert "chrome-extension" in src

    def test_not_found(self, sample_evidence):
        src = find_evidence_source("Quantum computing research with qubits", sample_evidence)
        assert src is None

    def test_returns_slug(self, sample_evidence):
        src = find_evidence_source("Analyzed datasets using pandas", sample_evidence)
        assert "data-analysis" in src


class TestMarkClaim:
    def test_supported(self, sample_evidence):
        result = mark_claim("Built a Chrome extension", sample_evidence)
        assert "<!-- evidence: evidence_bank.md#" in result
        assert "UNSUPPORTED" not in result

    def test_unsupported(self, sample_evidence):
        result = mark_claim("Quantum computing qubits", sample_evidence)
        assert "UNSUPPORTED" in result


class TestGenerateReport:
    def test_supported_claims(self, sample_evidence):
        pack = {
            "resume_targeted.md": "- Built a Chrome extension from scratch with popup UI\n- Analyzed 100K+ datasets using pandas",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack, sample_evidence, {})
        assert len(report["supported"]) >= 2

    def test_unsupported_claims(self, sample_evidence):
        pack = {
            "resume_targeted.md": "- Quantum computing research with qubits\n- Blockchain smart contract development",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack, sample_evidence, {})
        assert len(report["unsupported"]) >= 2

    def test_missing_jd_skills(self, sample_evidence):
        pack = {"resume_targeted.md": "- Built a Chrome extension", "greeting.md": "", "cover_letter.md": ""}
        job_data = {"skills_required": ["Python", "Kubernetes"]}
        report = generate_evidence_report(pack, sample_evidence, job_data)
        assert "Kubernetes" in report["missing_jd_skills"]

    def test_overclaim_risk(self, sample_evidence):
        pack = {
            "resume_targeted.md": "- Quantum computing\n- Blockchain\n- Neural interfaces",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack, sample_evidence, {})
        assert report["overclaim_risk"] > 0.5

    def test_weak_claim_low_overlap(self, sample_evidence):
        pack = {
            "resume_targeted.md": "- JavaScript development with Vue framework for browser extension",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack, sample_evidence, {})
        # Should be either supported or weak, not unsupported
        total = len(report["supported"]) + len(report["weak"])
        assert total >= 1

    def test_clean_pack_no_warnings(self, sample_evidence):
        pack = {
            "resume_targeted.md": "- Built a Chrome extension from scratch\n- Analyzed datasets using pandas",
            "greeting.md": "",
            "cover_letter.md": "",
        }
        report = generate_evidence_report(pack, sample_evidence, {"skills_required": []})
        assert len(report["unsupported"]) == 0
        assert report["overclaim_risk"] == 0.0
