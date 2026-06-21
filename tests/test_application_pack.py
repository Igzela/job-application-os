"""Tests for application pack manifests and integrity verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.application_pack import (
    PackIntegrityError,
    load_application_pack,
    load_live_application_pack,
    update_pack_validation,
    write_pack_manifest,
    write_application_pack,
    workspace_pack_sources,
)
from jobos.models import ApplicationPack


def test_application_pack_manifest_records_hashes(tmp_path: Path) -> None:
    pack = ApplicationPack(
        job_id="j1",
        files={
            "greeting.md": "Hello",
            "resume_targeted.md": "# Resume",
        },
    )

    write_application_pack(tmp_path, pack)

    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    loaded = load_application_pack(tmp_path, require_manifest=True)
    assert manifest["schema_version"] == 1
    assert manifest["job_id"] == "j1"
    assert set(manifest["files"]) == {"greeting.md", "resume_targeted.md"}
    assert loaded.files == pack.files


def test_application_pack_loader_rejects_tampered_file(tmp_path: Path) -> None:
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})
    write_application_pack(tmp_path, pack)
    (tmp_path / "greeting.md").write_text("Changed", encoding="utf-8")

    with pytest.raises(PackIntegrityError, match="greeting.md"):
        load_application_pack(tmp_path, require_manifest=True)


def test_application_pack_loader_rejects_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "profile.yaml"
    source.write_text("name: Before\n", encoding="utf-8")
    pack_dir = tmp_path / "applications" / "j1"
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})
    write_application_pack(pack_dir, pack, sources={"profile": source})
    source.write_text("name: After\n", encoding="utf-8")

    with pytest.raises(PackIntegrityError, match="source changed.*profile"):
        load_application_pack(
            pack_dir,
            require_manifest=True,
            verify_sources=True,
        )


def test_application_pack_writer_rejects_missing_explicit_source(
    tmp_path: Path,
) -> None:
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})

    with pytest.raises(PackIntegrityError, match="source missing.*profile"):
        write_application_pack(
            tmp_path,
            pack,
            sources={"profile": tmp_path / "missing.yaml"},
        )


def test_pack_manifest_writer_rejects_path_traversal_filename(
    tmp_path: Path,
) -> None:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")

    with pytest.raises(PackIntegrityError, match="Invalid pack filename"):
        write_pack_manifest(
            pack_dir,
            job_id="j1",
            files={"../outside.md": "outside"},
            created_at="2026-06-20T00:00:00+00:00",
        )


def test_application_pack_loader_requires_source_records_for_live(
    tmp_path: Path,
) -> None:
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})
    write_application_pack(tmp_path, pack)

    with pytest.raises(PackIntegrityError, match="source records"):
        load_application_pack(
            tmp_path,
            require_manifest=True,
            verify_sources=True,
        )


def test_workspace_pack_sources_ignore_unrelated_workspace_state(
    tmp_path: Path,
) -> None:
    (tmp_path / ".job-state.json").write_text(
        json.dumps({"jobs": {"other": {"status": "packed"}}}) + "\n",
        encoding="utf-8",
    )
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "evidence_bank.md").write_text(
        "Built a Python API\n",
        encoding="utf-8",
    )

    sources = workspace_pack_sources(tmp_path, "untracked")

    assert "workspace_state" not in sources
    assert "profile/evidence_bank" in sources


def test_update_pack_validation_refreshes_source_records(
    tmp_path: Path,
) -> None:
    old_source = tmp_path / "old-state.json"
    old_source.write_text("old\n", encoding="utf-8")
    new_source = tmp_path / "evidence_bank.md"
    new_source.write_text("new\n", encoding="utf-8")
    pack = ApplicationPack(job_id="j1", files={"resume_targeted.md": "Hello"})
    write_application_pack(tmp_path, pack, sources={"workspace_state": old_source})

    update_pack_validation(
        tmp_path,
        job_id="j1",
        sources={"profile/evidence_bank": new_source},
        validation={"supported": 0, "weak": 0, "unsupported": 1},
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["sources"]) == {"profile/evidence_bank"}
    load_application_pack(tmp_path, require_manifest=True, verify_sources=True)


def test_live_pack_loader_rejects_manifest_unsupported_claims(
    tmp_path: Path,
) -> None:
    source = tmp_path / "job.yaml"
    source.write_text("title: Engineer\n", encoding="utf-8")
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})
    write_application_pack(
        tmp_path / "pack",
        pack,
        sources={"job": source},
        validation={"supported": 0, "weak": 0, "unsupported": 2},
    )

    with pytest.raises(PackIntegrityError, match="unsupported claims: 2"):
        load_live_application_pack(
            tmp_path / "pack",
            job_id="j1",
            expected_validation={"supported": 0, "weak": 0, "unsupported": 0},
        )


def test_live_pack_loader_rejects_state_manifest_validation_mismatch(
    tmp_path: Path,
) -> None:
    source = tmp_path / "job.yaml"
    source.write_text("title: Engineer\n", encoding="utf-8")
    pack = ApplicationPack(job_id="j1", files={"greeting.md": "Hello"})
    write_application_pack(
        tmp_path / "pack",
        pack,
        sources={"job": source},
        validation={"supported": 2, "weak": 0, "unsupported": 0},
    )

    with pytest.raises(PackIntegrityError, match="validation mismatch"):
        load_live_application_pack(
            tmp_path / "pack",
            job_id="j1",
            expected_validation={"supported": 1, "weak": 0, "unsupported": 0},
        )
