"""Tests for the workspace state and artifact path module."""

from __future__ import annotations

import json
from pathlib import Path

from jobos import workspace


def test_missing_state_returns_fresh_defaults(tmp_path: Path) -> None:
    state = workspace.load_state(tmp_path)

    assert state["jobs"] == {}
    assert state["active_rubric"] == "unknown"
    assert state["rubric_history"] == []
    assert state["opportunities"] == []
    assert state["active_opportunity"] is None
    assert state["lessons"] == []

    state["jobs"]["j1"] = {"status": "imported"}
    assert workspace.load_state(tmp_path)["jobs"] == {}


def test_load_state_preserves_existing_file(tmp_path: Path) -> None:
    state_path = tmp_path / ".job-state.json"
    state_path.write_text(
        json.dumps({"jobs": {"j1": {"status": "packed"}}, "active_rubric": "v2"}),
        encoding="utf-8",
    )

    state = workspace.load_state(tmp_path)

    assert state["jobs"]["j1"]["status"] == "packed"
    assert state["active_rubric"] == "v2"


def test_save_state_writes_utf8_json_with_trailing_newline(tmp_path: Path) -> None:
    workspace.save_state(
        tmp_path,
        {"jobs": {"j1": {"company": "字节跳动"}}, "active_rubric": "v1"},
    )

    text = workspace.state_path(tmp_path).read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert "字节跳动" in text
    assert json.loads(text)["jobs"]["j1"]["company"] == "字节跳动"


def test_save_state_file_preserves_explicit_path(tmp_path: Path) -> None:
    explicit_path = tmp_path / "custom-state.json"

    workspace.save_state_file(explicit_path, {"jobs": {"j1": {"status": "retro"}}})

    assert explicit_path.exists()
    assert workspace.load_state_file(explicit_path)["jobs"]["j1"]["status"] == "retro"
    assert not workspace.state_path(tmp_path).exists()


def test_artifact_paths_resolve_under_workspace_root(tmp_path: Path) -> None:
    assert workspace.state_path(tmp_path) == tmp_path / ".job-state.json"
    assert workspace.predictions_dir(tmp_path) == tmp_path / "predictions"
    assert workspace.applications_dir(tmp_path) == tmp_path / "applications"
    assert workspace.application_dir(tmp_path, "j1") == tmp_path / "applications" / "j1"
    assert workspace.pipeline_runs_dir(tmp_path) == tmp_path / "pipeline_runs"
    assert workspace.jobs_raw_dir(tmp_path) == tmp_path / "jobs" / "raw"
    assert workspace.jobs_normalized_dir(tmp_path) == tmp_path / "jobs" / "normalized"
    assert workspace.retros_dir(tmp_path) == tmp_path / "retros"


def test_count_predictions_counts_json_files_only(tmp_path: Path) -> None:
    pred_dir = tmp_path / "predictions"
    pred_dir.mkdir()
    (pred_dir / "j1_v1.json").write_text("{}", encoding="utf-8")
    (pred_dir / "j2_v1.json").write_text("{}", encoding="utf-8")
    (pred_dir / "notes.md").write_text("not a prediction", encoding="utf-8")

    assert workspace.count_predictions(tmp_path) == 2


def test_count_application_packs_counts_application_directories(tmp_path: Path) -> None:
    app_dir = tmp_path / "applications"
    app_dir.mkdir()
    (app_dir / "j1").mkdir()
    (app_dir / "j2").mkdir()
    (app_dir / "README.md").write_text("not a pack", encoding="utf-8")

    assert workspace.count_application_packs(tmp_path) == 2


def test_initialize_workspace_creates_required_layout_and_state(tmp_path: Path) -> None:
    result = workspace.initialize_workspace(tmp_path)

    assert result.root == tmp_path
    assert workspace.state_path(tmp_path).exists()
    assert (tmp_path / "PROFILE.md").exists()
    assert (tmp_path / "jobs" / "raw").is_dir()
    assert (tmp_path / "jobs" / "normalized").is_dir()
    assert (tmp_path / "applications").is_dir()
    assert (tmp_path / "adapters" / "boss_assist").is_dir()
    assert workspace.load_state(tmp_path)["active_rubric"] == "v0_student_internship"


def test_initialize_workspace_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / "PROFILE.md").write_text("custom profile", encoding="utf-8")

    workspace.initialize_workspace(tmp_path)
    workspace.initialize_workspace(tmp_path)

    assert (tmp_path / "PROFILE.md").read_text(encoding="utf-8") == "custom profile"
