"""Tests for the semi-automatic submitter module.

Verifies prepare_submission, submit_application, platform field mapping,
dry-run mode, and error handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobos.submitter import (
    BOSS_FIELD_MAP,
    PLATFORM_MAPS,
    SubmitResult,
    get_platform_fields,
    prepare_submission,
    submit_application,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pack_dir(base: Path, job_id: str, files: dict[str, str] | None = None) -> Path:
    """Create a fake application pack directory with given files."""
    app_dir = base / "applications" / job_id
    app_dir.mkdir(parents=True, exist_ok=True)
    if files is None:
        files = {
            "greeting.md": "Hello, I am interested in this role.",
            "resume_targeted.md": "# Resume\n\nSkills: Python, React",
            "cover_letter.md": "Dear Hiring Team,\nI would like to apply.",
            "form_answers.md": "Q: Why us?\nA: Great company.",
        }
    for name, content in files.items():
        (app_dir / name).write_text(content, encoding="utf-8")
    return app_dir


# ---------------------------------------------------------------------------
# Tests: platform field mapping
# ---------------------------------------------------------------------------

class TestPlatformMapping:
    """Platform field maps are correct and complete."""

    def test_boss_map_keys(self) -> None:
        """Boss map covers the expected pack file names."""
        expected_files = {"greeting.md", "resume_targeted.md", "cover_letter.md", "form_answers.md"}
        assert set(BOSS_FIELD_MAP.keys()) == expected_files

    def test_boss_map_values(self) -> None:
        """Boss map values are the expected Chinese form field names."""
        assert BOSS_FIELD_MAP["greeting.md"] == "开场白/招呼语"
        assert BOSS_FIELD_MAP["resume_targeted.md"] == "简历内容"
        assert BOSS_FIELD_MAP["cover_letter.md"] == "求职信"
        assert BOSS_FIELD_MAP["form_answers.md"] == "常见问题回答"

    def test_get_platform_fields_boss(self) -> None:
        result = get_platform_fields("boss")
        assert result == BOSS_FIELD_MAP

    def test_get_platform_fields_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown platform"):
            get_platform_fields("nonexistent_platform")

    def test_platform_maps_registered(self) -> None:
        assert "boss" in PLATFORM_MAPS


# ---------------------------------------------------------------------------
# Tests: prepare_submission
# ---------------------------------------------------------------------------

class TestPrepareSubmission:
    """prepare_submission loads pack files and maps to platform fields."""

    def test_dry_run_returns_correct_fields(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-001")
        result = prepare_submission("job-001", "boss", str(tmp_path))

        assert result.dry_run is True
        assert result.job_id == "job-001"
        assert result.platform == "boss"
        assert result.submitted is False
        assert result.error is None

    def test_fields_filled_mapping(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-002")
        result = prepare_submission("job-002", "boss", str(tmp_path))

        assert "开场白/招呼语" in result.fields_filled
        assert "简历内容" in result.fields_filled
        assert "求职信" in result.fields_filled
        assert "常见问题回答" in result.fields_filled
        assert "interested" in result.fields_filled["开场白/招呼语"]

    def test_missing_pack_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No application pack found"):
            prepare_submission("nonexistent-job", "boss", str(tmp_path))

    def test_partial_pack_files(self, tmp_path: Path) -> None:
        """Only files that exist in the pack are mapped; missing ones are skipped."""
        _make_pack_dir(tmp_path, "job-003", files={
            "greeting.md": "Hi there!",
            # missing resume_targeted.md, cover_letter.md, form_answers.md
        })
        result = prepare_submission("job-003", "boss", str(tmp_path))

        assert len(result.fields_filled) == 1
        assert result.fields_filled["开场白/招呼语"] == "Hi there!"

    def test_unknown_platform_raises(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-004")
        with pytest.raises(ValueError, match="Unknown platform"):
            prepare_submission("job-004", "linkedin", str(tmp_path))

    def test_screenshot_path_none(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-005")
        result = prepare_submission("job-005", "boss", str(tmp_path))
        assert result.screenshot_path is None


# ---------------------------------------------------------------------------
# Tests: submit_application
# ---------------------------------------------------------------------------

class TestSubmitApplication:
    """submit_application dry-run and error paths."""

    def test_dry_run_default(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-010")
        result = submit_application("job-010", "boss", str(tmp_path))

        assert result.dry_run is True
        assert len(result.fields_filled) == 4

    def test_dry_run_explicit(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-011")
        result = submit_application("job-011", "boss", str(tmp_path), dry_run=True)
        assert result.dry_run is True

    def test_no_confirm_raises_value_error(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-012")
        with pytest.raises(ValueError, match="--confirm"):
            submit_application("job-012", "boss", str(tmp_path), dry_run=False, confirm=False)

    def test_confirm_raises_not_implemented(self, tmp_path: Path) -> None:
        _make_pack_dir(tmp_path, "job-013")
        with pytest.raises(NotImplementedError, match="not implemented"):
            submit_application("job-013", "boss", str(tmp_path), dry_run=False, confirm=True)

    def test_missing_pack_in_submit(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            submit_application("missing", "boss", str(tmp_path))


# ---------------------------------------------------------------------------
# Tests: SubmitResult dataclass
# ---------------------------------------------------------------------------

class TestSubmitResult:
    """SubmitResult is a proper frozen dataclass."""

    def test_frozen(self) -> None:
        r = SubmitResult(
            job_id="x", platform="boss", dry_run=True,
            fields_filled={"a": "b"},
        )
        with pytest.raises(AttributeError):
            r.job_id = "y"  # type: ignore[misc]

    def test_default_values(self) -> None:
        r = SubmitResult(
            job_id="x", platform="boss", dry_run=True,
            fields_filled={},
        )
        assert r.screenshot_path is None
        assert r.submitted is False
        assert r.submitted_at is None
        assert r.error is None
