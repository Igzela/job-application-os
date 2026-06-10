"""Tests for jobos.opportunity_finder — tier classification, scam checks, opportunity generation."""

import pytest

from jobos.opportunity_finder import (
    Opportunity,
    ScamVerdict,
    VERDICT_CLEAN,
    VERDICT_SCAM,
    VERDICT_SUSPECT,
    CATEGORIES,
    check_scam,
    classify_tier,
    find_opportunities,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_profile(**overrides):
    base = {
        "skills": ["Python", "AI tools", "ChatGPT"],
        "experience": ["2 years freelance copywriting"],
        "bio": "Learning AI tools for content creation",
        "tier": "",
    }
    base.update(overrides)
    return base


def _t0_profile():
    return _make_profile(
        skills=["beginner"],
        experience=["just started learning"],
        bio="I am a beginner with no experience, want to try AI",
        tier="T0",
    )


def _t1_profile():
    return _make_profile(
        skills=["ChatGPT", "Midjourney", "copywriting", "design"],
        experience=["Freelance designer using AI tools"],
        tier="T1",
    )


def _t2_profile():
    return _make_profile(
        skills=["Python", "JavaScript", "React", "API development"],
        experience=["3 years software engineering"],
        tier="T2",
    )


def _t3_profile():
    return _make_profile(
        skills=["domain expert", "consultant", "specialist"],
        experience=["10 years industry expert in healthcare AI"],
        bio="Senior consultant and industry specialist",
        tier="T3",
    )


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_basic_returns_list(self):
        result = find_opportunities(_make_profile())
        assert isinstance(result, list)
        assert len(result) > 0

    def test_all_results_are_opportunities(self):
        result = find_opportunities(_t1_profile())
        for opp in result:
            assert isinstance(opp, Opportunity)

    def test_opportunities_have_required_fields(self):
        result = find_opportunities(_t2_profile())
        for opp in result:
            assert opp.id.startswith("opp-")
            assert opp.name
            assert opp.category in CATEGORIES
            assert opp.for_tier in ("T0", "T1", "T2", "T3")
            assert opp.money_source
            assert opp.verdict in (VERDICT_CLEAN, VERDICT_SUSPECT, VERDICT_SCAM)
            assert opp.verify_first_step
            assert opp.income_expectation
            assert opp.reasoning_chain
            assert opp.cross_verification
            assert opp.status == "candidate"
            assert opp.found_at

    def test_direction_filters_categories(self):
        all_opps = find_opportunities(_t1_profile())
        content_opps = find_opportunities(_t1_profile(), direction="content")
        assert len(content_opps) <= len(all_opps)
        for opp in content_opps:
            assert opp.category == "content"


# ---------------------------------------------------------------------------
# Tests: scam checker A1-A6 (hard red lines)
# ---------------------------------------------------------------------------

class TestScamRedLines:
    def test_a1_upfront_fee(self):
        v = check_scam("You must pay an upfront fee to start training")
        assert v.label == VERDICT_SCAM
        assert "A1" in v.triggered_rules

    def test_a2_guaranteed_income(self):
        v = check_scam("This opportunity offers guaranteed income with no risk")
        assert v.label == VERDICT_SCAM
        assert "A2" in v.triggered_rules

    def test_a3_pyramid_recruit(self):
        v = check_scam("You need to recruit others and bring in friends for bonus")
        assert v.label == VERDICT_SCAM
        assert "A3" in v.triggered_rules

    def test_a4_crypto_payment(self):
        v = check_scam("Please send crypto to this wallet address")
        assert v.label == VERDICT_SCAM
        assert "A4" in v.triggered_rules

    def test_a5_no_experience_needed(self):
        v = check_scam("No experience needed, anyone can do it, zero skill required")
        assert v.label == VERDICT_SCAM
        assert "A5" in v.triggered_rules

    def test_a6_act_now(self):
        v = check_scam("Act now, limited spots available, expires today")
        assert v.label == VERDICT_SCAM
        assert "A6" in v.triggered_rules


# ---------------------------------------------------------------------------
# Tests: scam checker B1-B6 (suspect signals)
# ---------------------------------------------------------------------------

class TestScamSuspect:
    def test_b1_dm_for_details(self):
        v = check_scam("Great opportunity, dm for details on whatsapp only")
        assert v.label == VERDICT_SUSPECT
        assert "B1" in v.triggered_rules

    def test_b2_easy_money(self):
        v = check_scam("This is easy money, passive income while you sleep")
        assert v.label == VERDICT_SUSPECT
        assert "B2" in v.triggered_rules

    def test_b3_vague_description(self):
        v = check_scam("Vague description, details later, can't explain here")
        assert v.label == VERDICT_SUSPECT
        assert "B3" in v.triggered_rules

    def test_b4_new_company(self):
        v = check_scam("Brand new platform, just launched, no reviews yet")
        assert v.label == VERDICT_SUSPECT
        assert "B4" in v.triggered_rules

    def test_b5_commission_only(self):
        v = check_scam("Commission only, no base pay, pure commission structure")
        assert v.label == VERDICT_SUSPECT
        assert "B5" in v.triggered_rules

    def test_b6_unrealistic_rate(self):
        v = check_scam("Earn 500 per hour, make 1000 per day with this method")
        assert v.label == VERDICT_SUSPECT
        assert "B6" in v.triggered_rules


# ---------------------------------------------------------------------------
# Tests: clean input — no false positives
# ---------------------------------------------------------------------------

class TestCleanInput:
    def test_clean_text_verdict(self):
        v = check_scam("Freelance copywriting service using AI tools for small businesses")
        assert v.label == VERDICT_CLEAN
        assert v.triggered_rules == []

    def test_template_opportunities_are_clean(self):
        opps = find_opportunities(_t2_profile())
        for opp in opps:
            assert opp.verdict == VERDICT_CLEAN


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_profile(self):
        result = find_opportunities({})
        assert result == []

    def test_none_profile(self):
        result = find_opportunities(None)
        assert result == []

    def test_empty_direction_returns_all_tier_categories(self):
        result = find_opportunities(_t1_profile(), direction=None)
        cats = {opp.category for opp in result}
        assert len(cats) >= 2

    def test_invalid_direction_returns_empty(self):
        result = find_opportunities(_t1_profile(), direction="nonexistent")
        assert result == []

    def test_scam_verdict_serialization(self):
        v = check_scam("clean normal text")
        d = v.to_dict()
        restored = ScamVerdict.from_dict(d)
        assert restored.label == v.label
        assert restored.triggered_rules == v.triggered_rules

    def test_opportunity_serialization(self):
        opps = find_opportunities(_t2_profile())
        assert len(opps) > 0
        d = opps[0].to_dict()
        restored = Opportunity.from_dict(d)
        assert restored.id == opps[0].id
        assert restored.name == opps[0].name
        assert restored.category == opps[0].category

    def test_tier_classification_explicit(self):
        assert classify_tier({"tier": "T0"}) == "T0"
        assert classify_tier({"tier": "T3"}) == "T3"

    def test_tier_classification_from_skills(self):
        p = {"skills": ["Python", "JavaScript", "developer"], "experience": []}
        tier = classify_tier(p)
        assert tier in ("T2", "T3")

    def test_tier_classification_default(self):
        assert classify_tier({}) == "T0"

    def test_deterministic_output(self):
        r1 = find_opportunities(_t1_profile())
        r2 = find_opportunities(_t1_profile())
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.category == b.category
            assert a.name == b.name
            assert a.for_tier == b.for_tier
