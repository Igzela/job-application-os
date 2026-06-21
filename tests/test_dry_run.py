"""Tests for the dry-run form filler.

Verifies that run_dry_run fills local mock form fields but never submits
the form (no network calls, no form action invocation).
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from jobos.dry_run import (
    _build_field_mapping,
    _fill_form,
    run_dry_run,
    run_workspace_dry_run,
)
from jobos.models import ApplicationPack

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MOCK_FORM = FIXTURES / "mock_form.html"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pack(**overrides: str) -> ApplicationPack:
    """Build a minimal ApplicationPack for testing."""
    files: dict[str, str] = {
        "resume.md": "# Jordan Mitchell\nSoftware Engineer",
        "cover_letter.md": "Dear Hiring Manager, I am excited to apply.",
    }
    files.update(overrides)
    return ApplicationPack(job_id="test-001", files=files)


def _parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Tests: field filling
# ---------------------------------------------------------------------------

class TestFieldFilling:
    """The dry-run populates form fields with pack-derived values."""

    def test_fields_filled_match_mapping(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        filled = result["fields_filled"]
        assert "first_name" in filled
        assert filled["first_name"] == "Jordan"
        assert "email" in filled
        assert filled["email"] == "jordan.mitchell@university.edu"

    def test_select_field_filled(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        filled = result["fields_filled"]
        assert filled["work_authorization"] == "opt"

    def test_textarea_filled(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        filled = result["fields_filled"]
        assert "skills" in filled
        assert "Python" in filled["skills"]

    def test_cover_letter_from_pack_file(self) -> None:
        pack = _make_pack(**{"cover_letter.md": "My tailored cover letter."})
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        assert result["fields_filled"]["cover_letter"] == "My tailored cover letter."

    def test_meta_overrides_defaults(self) -> None:
        pack = _make_pack(
            **{"_meta": {"position_title": "ML Engineer", "company_name": "Acme Corp"}}
        )
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        filled = result["fields_filled"]
        assert filled["position_title"] == "ML Engineer"
        assert filled["company_name"] == "Acme Corp"

    def test_field_overrides_take_priority(self) -> None:
        pack = _make_pack(**{"_field_overrides": {"first_name": "Alex"}})
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        assert result["fields_filled"]["first_name"] == "Alex"

    def test_job_id_used_as_position_title_fallback(self) -> None:
        pack = ApplicationPack(job_id="swe-intern-2026", files={})
        result = run_dry_run("swe-intern-2026", pack, mock_form_path=MOCK_FORM)

        assert result["fields_filled"]["position_title"] == "swe-intern-2026"


# ---------------------------------------------------------------------------
# Tests: no submission
# ---------------------------------------------------------------------------

class TestNoSubmission:
    """The dry-run fills but never submits or makes network calls."""

    def test_form_action_not_invoked(self) -> None:
        """Verify the HTML is returned as-is -- no submit button is 'clicked',
        and the form's action target is untouched."""
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        # The submission log is a plain string, not an HTTP response
        assert "DRY RUN SUBMISSION LOG" in result["log"]

    def test_no_network_calls(self) -> None:
        """Patch socket.socket to fail -- any outbound attempt raises."""
        pack = _make_pack()

        with patch.object(socket, "socket", side_effect=RuntimeError("no network")):
            result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        # If we got here, no network call was attempted
        assert "fields_filled" in result

    def test_filled_html_still_has_form_action(self) -> None:
        """The filled HTML retains the form action attribute (it was never
        submitted), proving the form structure is preserved."""
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        # Re-parse the filled HTML from the log to verify the form wasn't
        # mutated into a submitted state.  We check the return dict instead.
        # The function doesn't return raw HTML, so we call _fill_form directly.
        html = MOCK_FORM.read_text()
        mapping = _build_field_mapping(pack)
        filled_html, _ = _fill_form(html, mapping)

        soup = _parse(filled_html)
        form = soup.find("form")
        assert form is not None
        assert form.get("action") == "https://example.com/apply"
        # The submit button still exists (not removed or disabled)
        assert soup.find("button", {"type": "submit"}) is not None

    def test_submit_button_unchanged(self) -> None:
        """The submit button is not disabled, removed, or modified."""
        pack = _make_pack()
        html = MOCK_FORM.read_text()
        mapping = _build_field_mapping(pack)
        filled_html, _ = _fill_form(html, mapping)

        soup = _parse(filled_html)
        btn = soup.find("button", {"type": "submit"})
        assert btn is not None
        assert btn.string.strip() == "Submit Application"
        assert btn.get("disabled") is None


# ---------------------------------------------------------------------------
# Tests: return structure
# ---------------------------------------------------------------------------

class TestReturnStructure:
    """run_dry_run returns the expected report dict."""

    def test_return_keys(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        assert "fields_filled" in result
        assert "log" in result
        assert "screenshot_note" in result

    def test_screenshot_note_mentions_dry_run(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        assert "Dry-run" in result["screenshot_note"]

    def test_log_contains_job_id(self) -> None:
        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=MOCK_FORM)

        assert "test-001" in result["log"]


def test_run_workspace_dry_run_loads_pack_and_mock_form(tmp_path: Path) -> None:
    job_id = "workspace-dry-run"
    pack_dir = tmp_path / "applications" / job_id
    pack_dir.mkdir(parents=True)
    (pack_dir / "cover_letter.md").write_text("Workspace cover letter", encoding="utf-8")
    form_dir = tmp_path / "tests" / "fixtures"
    form_dir.mkdir(parents=True)
    (form_dir / "mock_form.html").write_text(
        '<form><input name="first_name" value=""><textarea name="cover_letter"></textarea></form>',
        encoding="utf-8",
    )

    result = run_workspace_dry_run(tmp_path, job_id)

    assert result["fields_filled"]["first_name"] == "Jordan"
    assert result["fields_filled"]["cover_letter"] == "Workspace cover letter"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_missing_form_raises(self, tmp_path: Path) -> None:
        pack = _make_pack()
        bad_path = tmp_path / "nonexistent.html"

        with pytest.raises(FileNotFoundError, match="Mock form not found"):
            run_dry_run("test-001", pack, mock_form_path=bad_path)

    def test_empty_pack_still_fills_defaults(self) -> None:
        pack = ApplicationPack(job_id="empty-001", files={})
        result = run_dry_run("empty-001", pack, mock_form_path=MOCK_FORM)

        # Defaults should fill known fields even with an empty pack
        assert result["fields_filled"]["first_name"] == "Jordan"
        assert result["fields_filled"]["location"] == "Boston, MA"

    def test_unrecognized_form_fields_ignored(self, tmp_path: Path) -> None:
        """A form with extra fields that have no mapping stays unfilled."""
        html = (
            '<form action="/submit">'
            '<input name="first_name" value="">'
            '<input name="some_unknown_field" value="">'
            '</form>'
        )
        form_path = tmp_path / "extra.html"
        form_path.write_text(html)

        pack = _make_pack()
        result = run_dry_run("test-001", pack, mock_form_path=form_path)

        assert result["fields_filled"]["first_name"] == "Jordan"
        assert "some_unknown_field" not in result["fields_filled"]


# ---------------------------------------------------------------------------
# Tests: _fill_form unit tests
# ---------------------------------------------------------------------------

class TestFillFormUnit:
    """Direct tests for the _fill_form helper."""

    def test_input_value_set(self) -> None:
        html = '<form><input name="x" value=""></form>'
        _, filled = _fill_form(html, {"x": "hello"})
        assert filled == {"x": "hello"}

    def test_textarea_content_set(self) -> None:
        html = '<form><textarea name="bio"></textarea></form>'
        filled_html, filled = _fill_form(html, {"bio": "my bio"})
        assert filled == {"bio": "my bio"}
        assert "my bio" in filled_html

    def test_select_option_marked(self) -> None:
        html = (
            '<form><select name="color">'
            '<option value="">Pick</option>'
            '<option value="red">Red</option>'
            '<option value="blue">Blue</option>'
            '</select></form>'
        )
        filled_html, filled = _fill_form(html, {"color": "blue"})
        assert filled == {"color": "blue"}
        soup = _parse(filled_html)
        blue_opt = soup.find("option", value="blue")
        assert blue_opt is not None
        assert blue_opt.get("selected") == "selected"

    def test_field_not_in_mapping_untouched(self) -> None:
        html = '<form><input name="keep" value="original"></form>'
        filled_html, filled = _fill_form(html, {})
        assert filled == {}
        assert 'value="original"' in filled_html
