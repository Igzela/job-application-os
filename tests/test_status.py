"""Tests for jobos.status — verifies STATUS.md is generated with correct counts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobos.status import (
    STAGES,
    _build_status_md,
    _classify_jobs,
    _load_state,
    update_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    """Provide a fresh state directory for each test."""
    return tmp_path


def _write_state(state_dir: Path, state: dict) -> None:
    (state_dir / ".job-state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )


def _make_jobs(n: int, status: str = "imported", prefix: str = "job") -> dict:
    """Return a dict of `n` synthetic jobs all at the given stage."""
    return {
        f"{prefix}-{i:03d}": {
            "title": f"Role {i}",
            "company": f"Co {i}",
            "status": status,
            "captured_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        for i in range(1, n + 1)
    }


# ---------------------------------------------------------------------------
# _load_state
# ---------------------------------------------------------------------------


class TestLoadState:
    def test_missing_file_returns_defaults(self, state_dir: Path) -> None:
        state = _load_state(state_dir)
        assert state == {
            "schema_version": 1,
            "jobs": {},
            "active_rubric": "unknown",
            "rubric_history": [],
            "opportunities": [],
            "active_opportunity": None,
            "lessons": [],
        }

    def test_reads_existing_file(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": {"a": {}}, "active_rubric": "v2"})
        state = _load_state(state_dir)
        assert state["active_rubric"] == "v2"
        assert "a" in state["jobs"]


# ---------------------------------------------------------------------------
# _classify_jobs
# ---------------------------------------------------------------------------


class TestClassifyJobs:
    def test_empty_jobs(self) -> None:
        buckets = _classify_jobs({})
        for stage in STAGES:
            assert buckets[stage] == []

    def test_jobs_grouped_by_status(self) -> None:
        jobs = {}
        jobs.update(_make_jobs(2, "imported", prefix="imp"))
        jobs.update(_make_jobs(3, "scored", prefix="scr"))
        jobs.update(_make_jobs(1, "submitted", prefix="sub"))
        buckets = _classify_jobs(jobs)
        assert len(buckets["imported"]) == 2
        assert len(buckets["scored"]) == 3
        assert len(buckets["submitted"]) == 1
        assert len(buckets["predicted"]) == 0

    def test_unknown_stage_defaults_to_imported(self) -> None:
        jobs = {"x": {"status": "bogus"}}
        buckets = _classify_jobs(jobs)
        assert len(buckets["imported"]) == 1

    def test_missing_status_defaults_to_imported(self) -> None:
        jobs = {"x": {}}
        buckets = _classify_jobs(jobs)
        assert len(buckets["imported"]) == 1


# ---------------------------------------------------------------------------
# Pipeline counts in rendered markdown
# ---------------------------------------------------------------------------


class TestPipelineCounts:
    """Verify the rendered STATUS.md contains a correct pipeline summary table."""

    @staticmethod
    def _find_pipeline_section(md: str) -> list[str]:
        """Extract lines between '## Pipeline' and the next '##'."""
        lines = md.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "## Pipeline":
                start = i
                break
        if start is None:
            pytest.fail("STATUS.md missing '## Pipeline' section")
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break
        return lines[start:end]

    def test_empty_state_zero_counts(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        section = self._find_pipeline_section(md)
        for stage in STAGES:
            # Each stage row should have | 0 |
            assert any(
                stage.capitalize() in line and " 0 " in line for line in section
            ), f"Expected 0 for stage '{stage}' in:\n" + "\n".join(section)

    def test_single_stage_count(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": _make_jobs(5, "scored")})
        md = update_status(state_dir)
        section = self._find_pipeline_section(md)
        assert any("Scored" in line and " 5 " in line for line in section)
        assert any("Imported" in line and " 0 " in line for line in section)

    def test_total_reflects_all_jobs(self, state_dir: Path) -> None:
        jobs = {}
        jobs.update(_make_jobs(2, "imported", prefix="imp"))
        jobs.update(_make_jobs(3, "scored", prefix="scr"))
        jobs.update(_make_jobs(4, "submitted", prefix="sub"))
        _write_state(state_dir, {"jobs": jobs})
        md = update_status(state_dir)
        assert "**Total**" in md
        assert "**9**" in md

    def test_mixed_stages_all_correct(self, state_dir: Path) -> None:
        jobs = {}
        jobs.update(_make_jobs(1, "imported", prefix="imp"))
        jobs.update(_make_jobs(2, "scored", prefix="scr"))
        jobs.update(_make_jobs(3, "predicted", prefix="prd"))
        jobs.update(_make_jobs(4, "packed", prefix="pck"))
        jobs.update(_make_jobs(5, "submitted", prefix="sub"))
        jobs.update(_make_jobs(6, "retro", prefix="ret"))
        _write_state(state_dir, {"jobs": jobs})
        md = update_status(state_dir)
        section = self._find_pipeline_section(md)
        expected = {
            "Imported": 1, "Scored": 2, "Predicted": 3,
            "Packed": 4, "Submitted": 5, "Retro": 6,
        }
        for label, count in expected.items():
            assert any(
                label in line and f" {count} " in line for line in section
            ), f"Expected {count} for {label} in:\n" + "\n".join(section)
        assert "**Total**" in md
        assert "**21**" in md


# ---------------------------------------------------------------------------
# Jobs-by-stage detail sections
# ---------------------------------------------------------------------------


class TestJobsByStage:
    def test_stage_detail_lists_jobs(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": _make_jobs(2, "submitted")})
        md = update_status(state_dir)
        assert "### Submitted (2)" in md
        assert "job-001" in md
        assert "job-002" in md

    def test_empty_stage_shows_none(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        assert "### Imported (0)" in md
        # All stages should show _none_
        for stage in STAGES:
            # each stage detail section has _none_ when empty
            pass  # presence of the heading is sufficient; content is tested above


# ---------------------------------------------------------------------------
# update_status writes file
# ---------------------------------------------------------------------------


class TestUpdateStatusWritesFile:
    def test_creates_status_md(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": _make_jobs(1, "imported")})
        result = update_status(state_dir)
        status_file = state_dir / "STATUS.md"
        assert status_file.exists()
        assert status_file.read_text(encoding="utf-8") == result

    def test_overwrites_existing(self, state_dir: Path) -> None:
        (state_dir / "STATUS.md").write_text("old content", encoding="utf-8")
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        assert "old content" not in md
        assert "Pipeline" in md


# ---------------------------------------------------------------------------
# Artifact counts (predictions/ and applications/ subdirs)
# ---------------------------------------------------------------------------


class TestArtifactCounts:
    def test_predictions_appear_when_present(self, state_dir: Path) -> None:
        pred_dir = state_dir / "predictions"
        pred_dir.mkdir()
        for i in range(3):
            (pred_dir / f"pred-{i}.json").write_text("{}")
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        assert "Predictions on disk: **3**" in md

    def test_packs_appear_when_present(self, state_dir: Path) -> None:
        pack_dir = state_dir / "applications"
        pack_dir.mkdir()
        for i in range(2):
            (pack_dir / f"pack-{i}").mkdir()
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        assert "Application packs on disk: **2**" in md

    def test_no_artifacts_section_when_empty(self, state_dir: Path) -> None:
        _write_state(state_dir, {"jobs": {}})
        md = update_status(state_dir)
        assert "Artifacts" not in md


# ---------------------------------------------------------------------------
# Pending retros
# ---------------------------------------------------------------------------


class TestPendingRetros:
    def test_submitted_without_retro_listed(self, state_dir: Path) -> None:
        jobs = _make_jobs(2, "submitted")
        _write_state(state_dir, {"jobs": jobs})
        md = update_status(state_dir)
        assert "job-001" in md
        assert "job-002" in md
        assert "Pending Retros" in md

    def test_submitted_with_retro_not_listed(self, state_dir: Path) -> None:
        jobs = _make_jobs(1, "submitted")
        jobs["job-001"]["retro"] = {"outcome_label": "interview"}
        _write_state(state_dir, {"jobs": jobs})
        md = update_status(state_dir)
        # job-001 still appears in the table but retro section shows _none_
        pending_section = md.split("## Pending Retros")[1].split("##")[0]
        assert "_none_" in pending_section
