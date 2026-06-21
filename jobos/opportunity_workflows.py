"""Workspace workflows for side-income opportunity commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .action_planner import ActionPlan, create_plan
from .opportunity_finder import Opportunity, find_opportunities
from .profile_loader import load_profile
from .scam_checker import ScamVerdict, check_opportunity
from .workspace import load_state, save_state, state_path


@dataclass(frozen=True)
class ScamCheckWorkflowResult:
    verdict: ScamVerdict
    written: bool


@dataclass(frozen=True)
class FindOpportunitiesWorkflowResult:
    opportunities: list[Opportunity]
    written: int


@dataclass(frozen=True)
class PlanOpportunityWorkflowResult:
    plan: ActionPlan


class OpportunityWorkflowError(ValueError):
    """Raised when opportunity workflow inputs are invalid."""


class OpportunityNotFoundError(OpportunityWorkflowError):
    def __init__(self, opportunity_name: str, available: list[str]) -> None:
        super().__init__(
            f"Opportunity '{opportunity_name}' not found in .job-state.json"
        )
        self.available = available


def record_scam_check(
    state_dir: str | Path,
    name: str,
    description: str,
) -> ScamCheckWorkflowResult:
    """Run scam check and persist feasible/suspect opportunities."""
    verdict = check_opportunity(name, description)
    if verdict.verdict not in ("feasible", "suspect"):
        return ScamCheckWorkflowResult(verdict=verdict, written=False)

    state = load_state(state_dir)
    opportunities = state.get("opportunities", [])
    opportunities.append(
        {
            "name": verdict.name,
            "verdict": verdict.verdict,
            "red_flags": verdict.red_flags,
            "suspect_flags": verdict.suspect_flags,
            "reason": verdict.reason,
            "verify_first_step": verdict.verify_first_step,
            "income_expectation": verdict.income_expectation,
            "checked_at": verdict.checked_at,
            "status": "candidate",
        }
    )
    state["opportunities"] = opportunities
    save_state(state_dir, state)
    return ScamCheckWorkflowResult(verdict=verdict, written=True)


def find_workspace_opportunities(
    state_dir: str | Path,
    direction: str | None = None,
) -> FindOpportunitiesWorkflowResult:
    """Find profile-matched opportunities and append them to workspace state."""
    profile = load_profile(state_dir)
    opportunities = find_opportunities(profile, direction)
    if not opportunities:
        return FindOpportunitiesWorkflowResult(opportunities=[], written=0)

    state = load_state(state_dir)
    existing = state.get("opportunities", [])
    for opportunity in opportunities:
        existing.append(opportunity.to_dict())
    state["opportunities"] = existing
    save_state(state_dir, state)
    return FindOpportunitiesWorkflowResult(
        opportunities=opportunities,
        written=len(opportunities),
    )


def plan_workspace_opportunity(
    state_dir: str | Path,
    opportunity_name: str,
) -> PlanOpportunityWorkflowResult:
    """Create and persist an action plan for an existing opportunity."""
    root = Path(state_dir)
    if not state_path(root).exists():
        raise OpportunityWorkflowError("No .job-state.json found. Run init first.")

    state = load_state(root)
    opportunities: list[dict[str, Any]] = state.get("opportunities", [])
    target = next(
        (opp for opp in opportunities if opp.get("name") == opportunity_name),
        None,
    )
    if target is None:
        available = [opp.get("name", "?") for opp in opportunities]
        raise OpportunityNotFoundError(opportunity_name, available)

    profile = load_profile(root)
    plan = create_plan(target, profile)
    state["active_opportunity"] = plan.to_dict()
    save_state(root, state)
    return PlanOpportunityWorkflowResult(plan=plan)
