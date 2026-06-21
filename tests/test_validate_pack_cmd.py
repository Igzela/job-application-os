"""Tests for validate-pack command and evidence markers."""

import json
from pathlib import Path

import pytest

from jobos.application_pack import load_application_pack
from jobos.evidence_markers import (
    find_evidence_source,
    generate_evidence_report,
    generate_workspace_evidence_report,
    mark_claim,
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

    def test_supports_chinese_evidence_and_slug(self):
        evidence = [
            {
                "title": "雅思成绩",
                "fields": {},
                "content": "- 雅思总分 6.5\n- Demonstrated: 英语读写能力、国际视野",
            }
        ]

        source = find_evidence_source("雅思总分 6.5", evidence)

        assert source == "evidence_bank.md#雅思成绩"


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

    def test_chinese_exact_evidence_is_supported(self):
        evidence = [
            {
                "title": "吉林省2026大学生创新训练计划",
                "fields": {},
                "content": (
                    "- 参加吉林省2026大学生创新训练计划\n"
                    "- Demonstrated: 创新能力、项目经验"
                ),
            }
        ]
        pack = {
            "resume_targeted.md": (
                "- 参加吉林省2026大学生创新训练计划\n"
                "- Demonstrated: 创新能力、项目经验\n"
            ),
            "greeting.md": "",
            "cover_letter.md": "",
        }

        report = generate_evidence_report(pack, evidence, {})

        assert report["unsupported"] == []

    def test_profile_fact_is_supported_without_evidence(self):
        pack = {
            "resume_targeted.md": "**Work Arrangement:** on-site\n",
            "greeting.md": "",
            "cover_letter.md": "",
        }

        report = generate_evidence_report(
            pack,
            [],
            {},
            profile_data={"work_arrangement": "on-site"},
        )

        assert report["unsupported"] == []
        assert report["supported"][0]["source"] == "profile"


def test_generate_workspace_evidence_report_loads_pack_and_job_data(tmp_path: Path):
    import yaml

    job_id = "validate-workspace"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "resume_targeted.md").write_text(
        "- Quantum computing research with qubits\n",
        encoding="utf-8",
    )
    (pack_dir / "greeting.md").write_text("", encoding="utf-8")
    (pack_dir / "cover_letter.md").write_text("", encoding="utf-8")
    (tmp_path / "jobs" / "normalized").mkdir(parents=True)
    (tmp_path / "jobs" / "normalized" / f"{job_id}.yaml").write_text(
        yaml.safe_dump({"job_id": job_id, "skills_required": ["Python"]}),
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {job_id: {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )

    report = generate_workspace_evidence_report(tmp_path, job_id)

    assert len(report["unsupported"]) == 1
    assert report["missing_jd_skills"] == ["Python"]


def test_generate_workspace_evidence_report_records_unsupported_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_id = "unsupported-workspace"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "resume_targeted.md").write_text(
        "- Quantum computing research with qubits\n",
        encoding="utf-8",
    )
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "evidence_bank.md").write_text(
        "Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {job_id: {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobos.profile_loader.load_evidence_bank",
        lambda _root: [
            {
                "title": "Python API",
                "content": "Built a Python API",
                "skills": ["Python"],
                "fields": {},
            }
        ],
    )

    report = generate_workspace_evidence_report(tmp_path, job_id)

    state = json.loads((tmp_path / ".job-state.json").read_text(encoding="utf-8"))
    assert len(report["unsupported"]) == 1
    assert state["jobs"][job_id]["status"] == "packed"
    assert state["jobs"][job_id]["validation"]["unsupported"] == 1
    report_path = pack_dir / "validation_report.json"
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["job_id"] == job_id
    assert len(persisted["unsupported"]) == 1
    assert report["report_path"] == str(report_path)
    loaded = load_application_pack(
        pack_dir,
        require_manifest=True,
        verify_sources=True,
    )
    assert loaded.job_id == job_id


def test_generate_workspace_evidence_report_marks_clean_pack_validated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_id = "clean-workspace"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "resume_targeted.md").write_text(
        "- Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {job_id: {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobos.profile_loader.load_evidence_bank",
        lambda _root: [
            {
                "title": "Python API",
                "content": "Built a Python API",
                "skills": ["Python"],
                "fields": {},
            }
        ],
    )

    report = generate_workspace_evidence_report(tmp_path, job_id)

    state = json.loads((tmp_path / ".job-state.json").read_text(encoding="utf-8"))
    assert report["unsupported"] == []
    assert state["jobs"][job_id]["status"] == "validated"
    assert state["jobs"][job_id]["validation"]["unsupported"] == 0


def test_generate_workspace_evidence_report_writes_source_backed_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_id = "legacy-clean"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "resume_targeted.md").write_text(
        "- Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / "jobs" / "normalized").mkdir(parents=True)
    (tmp_path / "jobs" / "normalized" / f"{job_id}.yaml").write_text(
        "job_id: legacy-clean\nskills_required: []\n",
        encoding="utf-8",
    )
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "base.yaml").write_text(
        "name: Test\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "skills.yaml").write_text(
        "skills: [Python]\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "availability.yaml").write_text(
        "available: true\n",
        encoding="utf-8",
    )
    (tmp_path / "profile" / "evidence_bank.md").write_text(
        "Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {job_id: {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobos.profile_loader.load_evidence_bank",
        lambda _root: [
            {
                "title": "Python API",
                "content": "Built a Python API",
                "skills": ["Python"],
                "fields": {},
            }
        ],
    )

    report = generate_workspace_evidence_report(tmp_path, job_id)

    assert report["unsupported"] == []
    assert (pack_dir / "manifest.json").exists()
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {"other": {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )
    load_application_pack(pack_dir, require_manifest=True, verify_sources=True)


def test_generate_workspace_evidence_report_writes_manifest_without_state_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    job_id = "untracked-clean"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "resume_targeted.md").write_text(
        "- Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "evidence_bank.md").write_text(
        "Built a Python API\n",
        encoding="utf-8",
    )
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {}}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "jobos.profile_loader.load_evidence_bank",
        lambda _root: [
            {
                "title": "Python API",
                "content": "Built a Python API",
                "skills": ["Python"],
                "fields": {},
            }
        ],
    )

    report = generate_workspace_evidence_report(tmp_path, job_id)

    assert report["unsupported"] == []
    assert (pack_dir / "manifest.json").exists()
    load_application_pack(pack_dir, require_manifest=True, verify_sources=True)
