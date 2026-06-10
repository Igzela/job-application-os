"""Tests for jobos.action_planner — action plan generation and red-flag detection."""

import pytest

from jobos.action_planner import ActionPlan, create_plan


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_opportunity(**overrides):
    base = {
        "id": "opp-001",
        "name": "小红书内容创作",
        "category": "content",
        "description": "在小红书上发布生活方式内容，积累粉丝后变现",
        "source": "self",
    }
    base.update(overrides)
    return base


def _make_profile(**overrides):
    base = {
        "skills": ["写作", "内容创作", "小红书运营"],
        "available_hours_per_week": 15,
        "experience": ["1年自媒体运营"],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_basic_content_plan(self):
        plan = create_plan(_make_opportunity(), _make_profile())
        assert isinstance(plan, ActionPlan)
        assert plan.opportunity_id == "opp-001"
        assert plan.opportunity_name == "小红书内容创作"
        assert "发3篇内容看数据" in plan.verification_first_step
        assert len(plan.two_week_checklist) == 14
        assert plan.expected_hours_per_week > 0
        assert plan.expected_first_income_days > 0
        assert plan.expected_income_range != ""
        assert plan.created_at.endswith("Z")
        assert plan.warnings == []

    def test_freelance_plan(self):
        plan = create_plan(
            _make_opportunity(category="freelance", name="闲鱼接单"),
            _make_profile(),
        )
        assert "闲鱼挂一个最简服务" in plan.verification_first_step

    def test_tool_plan(self):
        plan = create_plan(
            _make_opportunity(category="tool", name="Chrome插件"),
            _make_profile(),
        )
        assert "MVP" in plan.verification_first_step

    def test_annotation_plan(self):
        plan = create_plan(
            _make_opportunity(category="annotation", name="数据标注"),
            _make_profile(),
        )
        assert "注册平台" in plan.verification_first_step

    def test_training_plan(self):
        plan = create_plan(
            _make_opportunity(category="training", name="Python教学"),
            _make_profile(),
        )
        assert "免费教" in plan.verification_first_step

    def test_cross_border_plan(self):
        plan = create_plan(
            _make_opportunity(category="cross-border", name="Fiverr接单"),
            _make_profile(),
        )
        assert "Fiverr" in plan.verification_first_step

    def test_unknown_category_uses_default(self):
        plan = create_plan(
            _make_opportunity(category="unknown_cat", name="神秘项目"),
            _make_profile(),
        )
        assert plan.verification_first_step != ""
        assert len(plan.two_week_checklist) == 14


# ---------------------------------------------------------------------------
# Red lines A1-A6
# ---------------------------------------------------------------------------

class TestHardRedLines:
    def test_A1_requires_upfront_payment(self):
        plan = create_plan(_make_opportunity(description="需要先交500元保证金才能开始"))
        assert any("A1" in w for w in plan.warnings)
        assert any("先付款" in w or "保证金" in w for w in plan.warnings)

    def test_A2_brush_order(self):
        plan = create_plan(_make_opportunity(description="帮商家刷单刷好评"))
        assert any("A2" in w for w in plan.warnings)

    def test_A3_pyramid_structure(self):
        plan = create_plan(_make_opportunity(description="通过拉人头发展下线赚佣金"))
        assert any("A3" in w for w in plan.warnings)

    def test_A4_unrealistic_income(self):
        plan = create_plan(_make_opportunity(description="日入过千零风险躺赚"))
        assert any("A4" in w for w in plan.warnings)

    def test_A5_sensitive_info(self):
        plan = create_plan(_make_opportunity(description="需要提供身份证正反面和银行卡"))
        assert any("A5" in w for w in plan.warnings)

    def test_A6_off_platform_payment(self):
        plan = create_plan(_make_opportunity(description="直接微信转账不走平台"))
        assert any("A6" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# Suspect signals B1-B6
# ---------------------------------------------------------------------------

class TestSuspectSignals:
    def test_B1_franchise_fee(self):
        plan = create_plan(_make_opportunity(description="需要交代理费才能开始"))
        assert any("B1" in w for w in plan.warnings)

    def test_B2_urgency(self):
        plan = create_plan(_make_opportunity(description="名额有限最后3个位置"))
        assert any("B2" in w for w in plan.warnings)

    def test_B3_screenshot_flex(self):
        plan = create_plan(_make_opportunity(description="看这些到账截图收益截图"))
        assert any("B3" in w for w in plan.warnings)

    def test_B4_zero_skill(self):
        plan = create_plan(_make_opportunity(description="无需经验有手就行小白也能做"))
        assert any("B4" in w for w in plan.warnings)

    def test_B5_training_fee(self):
        plan = create_plan(_make_opportunity(description="需要购买培训资料费500元"))
        assert any("B5" in w for w in plan.warnings)

    def test_B6_referral_income(self):
        plan = create_plan(_make_opportunity(description="推荐一个人给你100元返现"))
        assert any("B6" in w for w in plan.warnings)


# ---------------------------------------------------------------------------
# Clean input — no false positives
# ---------------------------------------------------------------------------

class TestCleanInput:
    def test_legitimate_content_opportunity_no_warnings(self):
        plan = create_plan(
            _make_opportunity(
                description="在小红书发布生活方式内容，通过品牌合作变现"
            ),
            _make_profile(),
        )
        assert plan.warnings == []

    def test_legitimate_freelance_no_warnings(self):
        plan = create_plan(
            _make_opportunity(
                category="freelance",
                description="在闲鱼提供P图服务，按单收费",
            ),
            _make_profile(),
        )
        assert plan.warnings == []

    def test_legitimate_tool_no_warnings(self):
        plan = create_plan(
            _make_opportunity(
                category="tool",
                description="开发一个Chrome插件提高工作效率",
            ),
            _make_profile(),
        )
        assert plan.warnings == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_opportunity(self):
        plan = create_plan({})
        assert isinstance(plan, ActionPlan)
        assert plan.opportunity_id == "unknown"
        assert len(plan.two_week_checklist) == 14

    def test_none_profile(self):
        plan = create_plan(_make_opportunity(), None)
        assert isinstance(plan, ActionPlan)

    def test_missing_category_infers_from_text(self):
        plan = create_plan({
            "name": "短视频创作",
            "description": "在抖音发短视频积累粉丝",
        })
        assert "发3篇内容看数据" in plan.verification_first_step

    def test_to_dict_roundtrip(self):
        plan = create_plan(_make_opportunity(), _make_profile())
        d = plan.to_dict()
        restored = ActionPlan.from_dict(d)
        assert restored.opportunity_id == plan.opportunity_id
        assert restored.two_week_checklist == plan.two_week_checklist
        assert restored.created_at == plan.created_at

    def test_frozen_dataclass(self):
        plan = create_plan(_make_opportunity())
        with pytest.raises(AttributeError):
            plan.opportunity_id = "changed"  # type: ignore[misc]

    def test_checklist_always_14_items(self):
        for cat in ("content", "freelance", "tool", "annotation", "training", "cross-border"):
            plan = create_plan(_make_opportunity(category=cat))
            assert len(plan.two_week_checklist) == 14, f"Category {cat} has {len(plan.two_week_checklist)} items"

    def test_stop_loss_mentions_hours(self):
        plan = create_plan(_make_opportunity())
        assert "20" in plan.stop_loss_line

    def test_stop_loss_with_red_flags_mentions_stop(self):
        plan = create_plan(_make_opportunity(description="先交钱刷单"))
        assert "停止" in plan.stop_loss_line

    def test_ai_leverage_has_items(self):
        plan = create_plan(_make_opportunity(category="content"))
        assert len(plan.ai_leverage_points) >= 3

    def test_multiple_red_flags_all_detected(self):
        plan = create_plan(_make_opportunity(
            description="刷单日入过千，先交保证金，拉人头有奖励"
        ))
        red_ids = [w.split("]")[0].lstrip("[") for w in plan.warnings]
        assert "A2" in red_ids
        assert "A3" in red_ids
        assert "A4" in red_ids


# ---------------------------------------------------------------------------
# Prediction fields
# ---------------------------------------------------------------------------

class TestPredictionBaseline:
    def test_prediction_fields_present(self):
        plan = create_plan(_make_opportunity(category="content"))
        assert isinstance(plan.expected_hours_per_week, float)
        assert isinstance(plan.expected_first_income_days, int)
        assert isinstance(plan.expected_income_range, str)
        assert plan.expected_hours_per_week > 0
        assert plan.expected_first_income_days > 0

    def test_different_categories_different_predictions(self):
        content = create_plan(_make_opportunity(category="content"))
        annotation = create_plan(_make_opportunity(category="annotation"))
        assert content.expected_first_income_days != annotation.expected_first_income_days or \
               content.expected_income_range != annotation.expected_income_range

    def test_created_at_is_iso8601(self):
        plan = create_plan(_make_opportunity())
        assert "T" in plan.created_at
        assert plan.created_at.endswith("Z")
