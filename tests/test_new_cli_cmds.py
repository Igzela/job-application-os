"""Integration tests for the 3 new CLI commands: scam-check, find, plan."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from jobos.cli import _cmd_scam_check, _cmd_find, _cmd_plan


class _Args:
    """Minimal argparse-like namespace."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# scam-check
# ---------------------------------------------------------------------------

class TestScamCheckHappy:
    """scam-check with a clean opportunity writes to state."""

    def test_feasible_verdict_printed(self, tmp_path, capsys):
        state_path = tmp_path / ".job-state.json"
        state_path.write_text(json.dumps({"jobs": {}, "opportunities": []}))
        with patch("jobos.cli._get_root", return_value=tmp_path):
            _cmd_scam_check(_Args(name="Content Creator", description="Write blog posts about tech"))
        out = capsys.readouterr().out
        assert "feasible" in out

    def test_feasible_written_to_state(self, tmp_path):
        state_path = tmp_path / ".job-state.json"
        state_path.write_text(json.dumps({"jobs": {}, "opportunities": []}))
        with patch("jobos.cli._get_root", return_value=tmp_path):
            _cmd_scam_check(_Args(name="Content Creator", description="Write blog posts about tech"))
        state = json.loads(state_path.read_text())
        assert len(state["opportunities"]) == 1
        assert state["opportunities"][0]["verdict"] == "feasible"


class TestScamCheckHighRisk:
    """scam-check with red flags should NOT write to state."""

    def test_high_risk_verdict(self, tmp_path, capsys):
        state_path = tmp_path / ".job-state.json"
        state_path.write_text(json.dumps({"jobs": {}, "opportunities": []}))
        with patch("jobos.cli._get_root", return_value=tmp_path):
            _cmd_scam_check(_Args(name="Easy Job", description="需要交入门费和培训费"))
        out = capsys.readouterr().out
        assert "high-risk" in out

    def test_high_risk_not_written_to_state(self, tmp_path):
        state_path = tmp_path / ".job-state.json"
        state_path.write_text(json.dumps({"jobs": {}, "opportunities": []}))
        with patch("jobos.cli._get_root", return_value=tmp_path):
            _cmd_scam_check(_Args(name="Easy Job", description="需要交入门费和培训费"))
        state = json.loads(state_path.read_text())
        assert len(state["opportunities"]) == 0


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------

class TestFind:
    """find command loads profile and writes opportunities."""

    def test_find_writes_opportunities(self, tmp_state_dir, sample_profile):
        state_path = tmp_state_dir / ".job-state.json"
        # Write profile files
        profile_dir = tmp_state_dir / "profile"
        profile_dir.mkdir(exist_ok=True)
        import yaml
        (profile_dir / "base.yaml").write_text(yaml.dump(sample_profile))

        with patch("jobos.cli._get_root", return_value=tmp_state_dir):
            _cmd_find(_Args(direction=None))
        state = json.loads(state_path.read_text())
        assert len(state["opportunities"]) > 0
        # Each should have required fields
        for opp in state["opportunities"]:
            assert "name" in opp
            assert "verdict" in opp
            assert "category" in opp


class TestFindWithDirection:
    """find with --direction filters to one category."""

    def test_find_content_only(self, tmp_state_dir, sample_profile):
        state_path = tmp_state_dir / ".job-state.json"
        profile_dir = tmp_state_dir / "profile"
        profile_dir.mkdir(exist_ok=True)
        import yaml
        (profile_dir / "base.yaml").write_text(yaml.dump(sample_profile))

        with patch("jobos.cli._get_root", return_value=tmp_state_dir):
            _cmd_find(_Args(direction="content"))
        state = json.loads(state_path.read_text())
        opps = state["opportunities"]
        assert len(opps) >= 1
        for opp in opps:
            assert opp["category"] == "content"


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------

class TestPlan:
    """plan command finds opportunity by name and creates an ActionPlan."""

    def test_plan_writes_active_opportunity(self, tmp_state_dir, sample_profile):
        state_path = tmp_state_dir / ".job-state.json"
        profile_dir = tmp_state_dir / "profile"
        profile_dir.mkdir(exist_ok=True)
        import yaml
        (profile_dir / "base.yaml").write_text(yaml.dump(sample_profile))

        # Seed an opportunity
        state = json.loads(state_path.read_text())
        state["opportunities"] = [{
            "id": "opp-content-12345678",
            "name": "AI-Assisted Content Monetization",
            "category": "content",
            "for_tier": "T1",
            "money_source": "Platform ad revenue share",
            "verdict": "clean",
            "verify_first_step": "Post 5 articles",
            "income_expectation": "500-5000 CNY/month",
            "reasoning_chain": "Low barrier",
            "cross_verification": "Check platform thresholds",
            "status": "candidate",
            "found_at": "2026-06-10T00:00:00Z",
        }]
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        with patch("jobos.cli._get_root", return_value=tmp_state_dir):
            _cmd_plan(_Args(opportunity="AI-Assisted Content Monetization"))
        state = json.loads(state_path.read_text())
        assert state["active_opportunity"] is not None
        plan = state["active_opportunity"]
        assert plan["opportunity_name"] == "AI-Assisted Content Monetization"
        assert len(plan["two_week_checklist"]) == 14


class TestPlanNotFound:
    """plan with a non-existent opportunity name should exit with error."""

    def test_plan_not_found_exits(self, tmp_state_dir):
        state_path = tmp_state_dir / ".job-state.json"
        state = json.loads(state_path.read_text())
        state["opportunities"] = []
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        with patch("jobos.cli._get_root", return_value=tmp_state_dir):
            with pytest.raises(SystemExit, match="1"):
                _cmd_plan(_Args(opportunity="Nonexistent Opportunity"))
