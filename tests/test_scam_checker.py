"""Tests for jobos.scam_checker — anti-scam rule engine."""

import pytest

from jobos.scam_checker import ScamVerdict, check_opportunity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _check(name="测试兼职", description="正常工作内容", profile=None):
    return check_opportunity(name=name, description=description, profile=profile)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_returns_scam_verdict(self):
        result = _check()
        assert isinstance(result, ScamVerdict)

    def test_verdict_is_feasible_for_clean_input(self):
        result = _check(description="客服岗位，需要基本电脑操作，按时计薪")
        assert result.verdict == "feasible"
        assert result.red_flags == []
        assert result.suspect_flags == []

    def test_fields_populated(self):
        result = _check()
        assert result.name == "测试兼职"
        assert isinstance(result.reason, str) and len(result.reason) > 0
        assert isinstance(result.verify_first_step, str) and len(result.verify_first_step) > 0
        assert isinstance(result.income_expectation, str) and len(result.income_expectation) > 0
        assert isinstance(result.checked_at, str) and "T" in result.checked_at


# ---------------------------------------------------------------------------
# Hard red lines A1-A6
# ---------------------------------------------------------------------------

class TestHardRedLines:
    def test_a1_entry_fee(self):
        r = _check(description="需缴纳入门费200元")
        assert r.verdict == "high-risk"
        assert any("A1" in f for f in r.red_flags)

    def test_a2_income_promise(self):
        r = _check(description="日入千元不是梦")
        assert r.verdict == "high-risk"
        assert any("A2" in f for f in r.red_flags)

    def test_a3_recruitment_rebate(self):
        r = _check(description="邀请返利，拉人头奖励丰厚")
        assert r.verdict == "high-risk"
        assert any("A3" in f for f in r.red_flags)

    def test_a4_fund_passthrough(self):
        r = _check(description="需要刷单走账")
        assert r.verdict == "high-risk"
        assert any("A4" in f for f in r.red_flags)

    def test_a5_selling_courses(self):
        r = _check(description="教你赚钱的副业课程")
        assert r.verdict == "high-risk"
        assert any("A5" in f for f in r.red_flags)

    def test_a6_illegal_activity(self):
        r = _check(description="代写论文，刷好评")
        assert r.verdict == "high-risk"
        assert any("A6" in f for f in r.red_flags)


# ---------------------------------------------------------------------------
# Suspect signals B1-B6
# ---------------------------------------------------------------------------

class TestSuspectSignals:
    def test_b1_no_third_party(self):
        r = _check(description="只有推广帖，没有真实反馈")
        assert r.verdict == "suspect"
        assert any("B1" in f for f in r.suspect_flags)

    def test_b2_above_market(self):
        r = _check(description="高薪日结，天价报酬")
        assert r.verdict == "suspect"
        assert any("B2" in f for f in r.suspect_flags)

    def test_b3_private_chat(self):
        r = _check(description="加微信私聊交易")
        assert r.verdict == "suspect"
        assert any("B3" in f for f in r.suspect_flags)

    def test_b4_pressure_tactics(self):
        r = _check(description="名额有限，仅限今天")
        assert r.verdict == "suspect"
        assert any("B4" in f for f in r.suspect_flags)

    def test_b5_trial_tasks(self):
        r = _check(description="先做一单试试，免费体验")
        assert r.verdict == "suspect"
        assert any("B5" in f for f in r.suspect_flags)

    def test_b6_unverifiable_employer(self):
        r = _check(description="公司查不到，无营业执照")
        assert r.verdict == "suspect"
        assert any("B6" in f for f in r.suspect_flags)


# ---------------------------------------------------------------------------
# Clean input: no false positives
# ---------------------------------------------------------------------------

class TestCleanInput:
    def test_normal_job_no_flags(self):
        r = _check(
            name="Python后端开发",
            description="负责后端API开发，要求Python和数据库经验，按月发薪，五险一金",
        )
        assert r.verdict == "feasible"
        assert r.red_flags == []
        assert r.suspect_flags == []

    def test_freelance_clean(self):
        r = _check(
            name="自由翻译",
            description="英中翻译工作，按字数计费，通过平台结算",
        )
        assert r.verdict == "feasible"

    def test_multiple_clean_descriptions(self):
        descriptions = [
            "超市收银员，日薪120元",
            "线上问卷填写，每份5元",
            "家教辅导，每小时80元",
        ]
        for desc in descriptions:
            r = _check(description=desc)
            assert r.verdict == "feasible", f"False positive for: {desc}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_description(self):
        r = _check(description="")
        assert r.verdict == "feasible"

    def test_none_profile(self):
        r = _check(profile=None)
        assert isinstance(r, ScamVerdict)

    def test_empty_profile(self):
        r = _check(profile={})
        assert isinstance(r, ScamVerdict)

    def test_empty_name(self):
        r = _check(name="", description="正常工作")
        assert r.verdict == "feasible"

    def test_name_with_red_flag_keyword(self):
        r = _check(name="入门费项目", description="")
        assert r.verdict == "high-risk"

    def test_multiple_red_flags(self):
        r = _check(description="入门费200元，日入千元，拉人头奖励")
        assert r.verdict == "high-risk"
        assert len(r.red_flags) >= 3

    def test_red_flag_overrides_suspect(self):
        r = _check(description="入门费，加微信私聊交易")
        assert r.verdict == "high-risk"
        assert len(r.red_flags) >= 1


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_round_trip(self):
        original = _check(description="入门费，日入千元")
        d = original.to_dict()
        restored = ScamVerdict.from_dict(d)
        assert restored == original

    def test_from_dict_ignores_extra_keys(self):
        d = {
            "name": "test",
            "verdict": "feasible",
            "red_flags": [],
            "suspect_flags": [],
            "reason": "ok",
            "verify_first_step": "check",
            "income_expectation": "normal",
            "checked_at": "2026-01-01T00:00:00Z",
            "extra_key": "ignored",
        }
        v = ScamVerdict.from_dict(d)
        assert v.name == "test"
