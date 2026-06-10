"""Tests for jobos.retro — submission recording, retro tracking, and retro files."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from jobos.retro import (
    record_submission,
    record_retro,
    record_freeform_retro,
    get_pending_retros,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    """Create a minimal .job-state.json with one job pre-populated."""
    state = {
        "jobs": {
            "alpha-001": {
                "title": "SWE",
                "company": "Acme",
                "status": "predicted",
            }
        },
        "active_rubric": "v0",
        "rubric_history": [],
    }
    (tmp_path / ".job-state.json").write_text(
        json.dumps(state, indent=2) + "\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# record_submission
# ---------------------------------------------------------------------------

class TestRecordSubmission:
    def test_sets_retro_fields_in_state(self, state_dir: Path) -> None:
        job = record_submission("alpha-001", "greenhouse", state_dir)

        retro = job["retro"]
        assert retro["status_3d"] is None
        assert retro["status_14d"] is None
        assert retro["status_30d"] is None
        assert retro["complete"] is False
        assert retro["submitted_at"] is not None

    def test_sets_due_dates_at_correct_offsets(self, state_dir: Path) -> None:
        before = datetime.now(timezone.utc)
        job = record_submission("alpha-001", "lever", state_dir)
        after = datetime.now(timezone.utc)

        retro = job["retro"]
        for key, days in [
            ("check_3d_due", 3),
            ("check_14d_due", 14),
            ("check_30d_due", 30),
        ]:
            due = datetime.fromisoformat(retro[key])
            assert before + timedelta(days=days) <= due <= after + timedelta(days=days)

    def test_persists_submission_channel(self, state_dir: Path) -> None:
        record_submission("alpha-001", "referral", state_dir)

        raw = json.loads((state_dir / ".job-state.json").read_text())
        assert raw["jobs"]["alpha-001"]["submission_channel"] == "referral"

    def test_raises_on_unknown_job(self, state_dir: Path) -> None:
        with pytest.raises(KeyError, match="not found"):
            record_submission("nonexistent", "email", state_dir)


# ---------------------------------------------------------------------------
# record_retro
# ---------------------------------------------------------------------------

class TestRecordRetro:
    def _submit(self, state_dir: Path) -> None:
        record_submission("alpha-001", "greenhouse", state_dir)

    def test_records_3d_status_in_state(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro("alpha-001", state_dir, status_3d="ack_received")

        state = json.loads((state_dir / ".job-state.json").read_text())
        assert state["jobs"]["alpha-001"]["retro"]["status_3d"] == "ack_received"

    def test_records_14d_status_in_state(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro("alpha-001", state_dir, status_14d="phone_screen")

        state = json.loads((state_dir / ".job-state.json").read_text())
        assert state["jobs"]["alpha-001"]["retro"]["status_14d"] == "phone_screen"

    def test_records_30d_status_in_state(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro("alpha-001", state_dir, status_30d="offer")

        state = json.loads((state_dir / ".job-state.json").read_text())
        assert state["jobs"]["alpha-001"]["retro"]["status_30d"] == "offer"

    def test_marks_complete_when_all_three_filled(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro(
            "alpha-001", state_dir,
            status_3d="ack_received",
            status_14d="phone_screen",
            status_30d="offer",
        )

        state = json.loads((state_dir / ".job-state.json").read_text())
        assert state["jobs"]["alpha-001"]["retro"]["complete"] is True

    def test_not_complete_with_partial_statuses(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro("alpha-001", state_dir, status_3d="ack_received")

        state = json.loads((state_dir / ".job-state.json").read_text())
        assert state["jobs"]["alpha-001"]["retro"]["complete"] is False

    def test_raises_if_no_submission(self, state_dir: Path) -> None:
        with pytest.raises(KeyError, match="no submission recorded"):
            record_retro("alpha-001", state_dir, status_3d="ack_received")

    def test_raises_on_unknown_job(self, state_dir: Path) -> None:
        with pytest.raises(KeyError, match="not found"):
            record_retro("nonexistent", state_dir, status_3d="ack_received")

    # -- retro file creation --

    def test_creates_retro_file(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_3d="ack_received")

        assert path.exists()
        assert path == state_dir / "retros" / "alpha-001.json"

    def test_retro_file_has_job_id(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_3d="ack_received")
        data = json.loads(path.read_text())

        assert data["job_id"] == "alpha-001"

    def test_retro_file_records_statuses(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro(
            "alpha-001", state_dir,
            status_3d="ack_received",
            status_14d="phone_screen",
            status_30d="offer",
        )
        data = json.loads(path.read_text())

        assert data["status_3d"] == "ack_received"
        assert data["status_14d"] == "phone_screen"
        assert data["status_30d"] == "offer"

    def test_retro_file_sets_offer_flag(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_30d="offer")
        data = json.loads(path.read_text())

        assert data["offer_received"] is True

    def test_retro_file_sets_rejection_flag(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_30d="rejected")
        data = json.loads(path.read_text())

        assert data["rejection_received"] is True

    def test_retro_file_sets_ghosted_flag(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_30d="ghosted")
        data = json.loads(path.read_text())

        assert data["ghosted"] is True

    def test_retro_file_sets_interview_flag(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro("alpha-001", state_dir, status_14d="phone_screen")
        data = json.loads(path.read_text())

        assert data["interview_received"] is True

    def test_retro_file_outcome_label_is_latest_status(self, state_dir: Path) -> None:
        self._submit(state_dir)
        path = record_retro(
            "alpha-001", state_dir,
            status_3d="ack_received",
            status_14d="phone_screen",
        )
        data = json.loads(path.read_text())

        assert data["outcome_label"] == "phone_screen"

    def test_incremental_update_preserves_existing_statuses(self, state_dir: Path) -> None:
        self._submit(state_dir)
        record_retro("alpha-001", state_dir, status_3d="ack_received")
        record_retro("alpha-001", state_dir, status_14d="phone_screen")

        path = state_dir / "retros" / "alpha-001.json"
        data = json.loads(path.read_text())

        assert data["status_3d"] == "ack_received"
        assert data["status_14d"] == "phone_screen"
        assert data["status_30d"] is None


# ---------------------------------------------------------------------------
# get_pending_retros
# ---------------------------------------------------------------------------

class TestGetPendingRetros:
    def test_empty_when_no_submissions(self, state_dir: Path) -> None:
        assert get_pending_retros(state_dir) == []

    def test_returns_job_with_due_window(self, state_dir: Path) -> None:
        record_submission("alpha-001", "greenhouse", state_dir)

        # Back-date the 3-day due date so it is overdue
        state = json.loads((state_dir / ".job-state.json").read_text())
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        state["jobs"]["alpha-001"]["retro"]["check_3d_due"] = past
        (state_dir / ".job-state.json").write_text(
            json.dumps(state, indent=2) + "\n",
        )

        pending = get_pending_retros(state_dir)
        assert len(pending) == 1
        assert pending[0]["job_id"] == "alpha-001"
        assert "3d" in pending[0]["due_windows"]

    def test_skips_completed_retros(self, state_dir: Path) -> None:
        record_submission("alpha-001", "greenhouse", state_dir)
        record_retro(
            "alpha-001", state_dir,
            status_3d="ack_received",
            status_14d="phone_screen",
            status_30d="offer",
        )

        assert get_pending_retros(state_dir) == []

    def test_skips_windows_already_recorded(self, state_dir: Path) -> None:
        record_submission("alpha-001", "greenhouse", state_dir)

        # Back-date 3d due but record its status
        state = json.loads((state_dir / ".job-state.json").read_text())
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        state["jobs"]["alpha-001"]["retro"]["check_3d_due"] = past
        state["jobs"]["alpha-001"]["retro"]["status_3d"] = "ack_received"
        (state_dir / ".job-state.json").write_text(
            json.dumps(state, indent=2) + "\n",
        )

        pending = get_pending_retros(state_dir)
        # 3d is filled, so it should not appear in due_windows
        assert all("3d" not in p["due_windows"] for p in pending)


# ---------------------------------------------------------------------------
# record_freeform_retro
# ---------------------------------------------------------------------------

class TestRecordFreeformRetro:
    def test_creates_retro_file(self, state_dir: Path) -> None:
        path = record_freeform_retro(
            "alpha-001",
            "Applied via greenhouse, no response yet.",
            ["Always follow up after 3 days"],
            state_dir,
        )

        assert path.exists()
        assert path == state_dir / "retros" / "alpha-001.json"

    def test_retro_file_has_job_id(self, state_dir: Path) -> None:
        path = record_freeform_retro(
            "alpha-001", "Some text", ["Lesson A"], state_dir
        )
        data = json.loads(path.read_text())

        assert data["job_id"] == "alpha-001"

    def test_retro_file_has_freeform_entries(self, state_dir: Path) -> None:
        path = record_freeform_retro(
            "alpha-001",
            "Retro text here",
            ["Lesson 1", "Lesson 2"],
            state_dir,
        )
        data = json.loads(path.read_text())

        assert len(data["freeform_retros"]) == 1
        entry = data["freeform_retros"][0]
        assert entry["text"] == "Retro text here"
        assert entry["lessons"] == ["Lesson 1", "Lesson 2"]
        assert "recorded_at" in entry

    def test_appends_to_existing_retro(self, state_dir: Path) -> None:
        record_freeform_retro("alpha-001", "First retro", ["L1"], state_dir)
        path = record_freeform_retro(
            "alpha-001", "Second retro", ["L2"], state_dir
        )
        data = json.loads(path.read_text())

        assert len(data["freeform_retros"]) == 2
        assert data["freeform_retros"][0]["text"] == "First retro"
        assert data["freeform_retros"][1]["text"] == "Second retro"

    def test_creates_lessons_md(self, state_dir: Path) -> None:
        record_freeform_retro(
            "alpha-001",
            "Some retro",
            ["Always follow up", "Tailor resume"],
            state_dir,
        )

        lessons_path = state_dir / "lessons.md"
        assert lessons_path.exists()
        content = lessons_path.read_text()
        assert "- Always follow up" in content
        assert "- Tailor resume" in content

    def test_appends_to_existing_lessons_md(self, state_dir: Path) -> None:
        record_freeform_retro("alpha-001", "Retro 1", ["Lesson A"], state_dir)
        record_freeform_retro("alpha-002", "Retro 2", ["Lesson B"], state_dir)

        content = (state_dir / "lessons.md").read_text()
        assert "- Lesson A" in content
        assert "- Lesson B" in content

    def test_lessons_md_has_header(self, state_dir: Path) -> None:
        record_freeform_retro(
            "alpha-001", "Retro", ["A lesson"], state_dir
        )
        content = (state_dir / "lessons.md").read_text()
        assert content.startswith("# Lessons Learned")

    def test_updated_at_is_set(self, state_dir: Path) -> None:
        path = record_freeform_retro(
            "alpha-001", "text", ["lesson"], state_dir
        )
        data = json.loads(path.read_text())
        assert "updated_at" in data
