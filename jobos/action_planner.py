"""Action planner — generates a 2-week execution plan for an opportunity.

Given an opportunity dict and a user profile, produces an ActionPlan with
5 mandatory blocks: verification step, 2-week checklist, income expectation,
stop-loss line, and AI leverage points.  Includes a prediction baseline for
retroactive comparison.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿㐀-䶿\s]", " ", text.lower())


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF)


def _segment_cjk(text: str) -> list[str]:
    """Extract 2-4 char CJK n-grams and ASCII tokens from text."""
    tokens: list[str] = []
    buf = ""
    for ch in text:
        if _is_cjk(ch):
            buf += ch
        else:
            if buf:
                for n in (3, 2):
                    for i in range(len(buf) - n + 1):
                        tokens.append(buf[i : i + n])
                buf = ""
            if ch.isalnum():
                buf += ch
            else:
                if buf:
                    tokens.append(buf)
                    buf = ""
    if buf:
        if _is_cjk(buf[0]):
            for n in (3, 2):
                for i in range(len(buf) - n + 1):
                    tokens.append(buf[i : i + n])
        else:
            tokens.append(buf)
    return tokens


def _keywords_from(text: str) -> set[str]:
    normalized = _normalize(text)
    stopwords = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "this", "that",
        "these", "those", "it", "its", "we", "our", "you", "your", "they",
        "their", "i", "my", "me", "he", "she", "his", "her", "him",
        "not", "no", "as", "if", "so", "than", "too", "very", "just",
        "about", "above", "after", "again", "all", "also", "am", "any",
        "because", "before", "between", "both", "each", "few", "more",
        "most", "other", "some", "such", "only", "own", "same", "into",
        "over", "under", "up", "down", "out", "off", "then", "once", "here",
        "there", "when", "where", "why", "how", "what", "which", "who",
        "whom", "while", "during", "through", "between", "until", "against",
    }
    tokens = _segment_cjk(normalized)
    return {t for t in tokens if len(t) >= 2 and t not in stopwords}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Constants — category templates
# ---------------------------------------------------------------------------

_CATEGORY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "content": {
        "verification_first_step": "发3篇内容看数据",
        "checklist": [
            "Day 1: 确定目标平台和内容方向，研究同领域Top10账号",
            "Day 2: 写第1篇内容并发布，记录初始数据",
            "Day 3: 分析第1篇数据，调整标题/封面策略",
            "Day 4: 写第2篇内容并发布",
            "Day 5: 写第3篇内容并发布，对比3篇数据",
            "Day 6: 复盘数据，确定最佳内容类型",
            "Day 7: 写第4-5篇，聚焦数据最好的方向",
            "Day 8: 建立内容模板，提高产出效率",
            "Day 9: 尝试不同发布时间，记录效果",
            "Day 10: 与3个同领域创作者互动/评论",
            "Day 11: 写第6-7篇，使用AI辅助提效",
            "Day 12: 梳理粉丝反馈，调整内容策略",
            "Day 13: 写第8篇，测试付费内容/广告位",
            "Day 14: 总结2周数据，决定是否继续投入",
        ],
        "income_expectation": "第2-4周见第一笔收入（平台分成/广告），预期200-1000元/月起步，属于'时间换小钱'积累型",
        "expected_hours_per_week": 15.0,
        "expected_first_income_days": 21,
        "expected_income_range": "200-1000元/月",
    },
    "freelance": {
        "verification_first_step": "闲鱼挂一个最简服务",
        "checklist": [
            "Day 1: 确定最简服务定义（1小时内可交付的），定价9.9-49元",
            "Day 2: 在闲鱼/淘宝发布服务，写好标题和描述",
            "Day 3: 在3个相关社群发布服务信息",
            "Day 4: 优化商品图片和描述，提高点击率",
            "Day 5: 主动找5个潜在客户私聊推荐",
            "Day 6: 完成第1单（哪怕免费），收集好评",
            "Day 7: 用AI批量生成服务变体描述",
            "Day 8: 拓展到第2个平台（如猪八戒/Fiverr）",
            "Day 9: 优化服务流程，缩短交付时间",
            "Day 10: 提价测试（在原价基础上加30%）",
            "Day 11: 收集3个客户评价，用于新客户转化",
            "Day 12: 建立标准服务SOP文档",
            "Day 13: 尝试 upsell 高价服务包",
            "Day 14: 总结2周数据，计算时薪，决定方向",
        ],
        "income_expectation": "第1-2周内可能出单，预期500-3000元/月，属于'技能换钱'，单价随好评逐步提升",
        "expected_hours_per_week": 12.0,
        "expected_first_income_days": 7,
        "expected_income_range": "500-3000元/月",
    },
    "tool": {
        "verification_first_step": "做一个MVP landing page",
        "checklist": [
            "Day 1: 用1句话定义工具解决的核心痛点",
            "Day 2: 搭建landing page（Carrd/Notion），收集邮箱",
            "Day 3: 在3个目标用户社群发布landing page",
            "Day 4: 记录注册/访问数据，判断需求真伪",
            "Day 5: 搭建最小可用版本（1个核心功能）",
            "Day 6: 让3个种子用户试用，收集反馈",
            "Day 7: 根据反馈修复最痛的问题",
            "Day 8: 在ProductHunt/独立开发者社区发布",
            "Day 9: 写一篇'我做了XX工具'的推广文章",
            "Day 10: 添加简单的付费功能/定价",
            "Day 11: 用AI生成用户引导和帮助文档",
            "Day 12: 分析用户行为数据，找转化瓶颈",
            "Day 13: 优化定价页，测试不同价格点",
            "Day 14: 总结2周数据，决定是否继续开发",
        ],
        "income_expectation": "第3-6周可能有付费用户，预期0-5000元/月（波动大），属于'产品换钱'，需要持续迭代",
        "expected_hours_per_week": 20.0,
        "expected_first_income_days": 28,
        "expected_income_range": "0-5000元/月",
    },
    "annotation": {
        "verification_first_step": "注册平台完成第一个任务",
        "checklist": [
            "Day 1: 注册2-3个标注平台（如Scale AI/百度众测），完成入门测试",
            "Day 2: 完成第1个标注任务，记录用时和收入",
            "Day 3: 完成5个任务，摸索提效方法",
            "Day 4: 用AI辅助预标注，提高速度",
            "Day 5: 完成10个任务，计算时薪",
            "Day 6: 申请更高单价的任务类型",
            "Day 7: 总结第1周数据，时薪是否达标",
            "Day 8: 注册更多平台，对比单价",
            "Day 9: 批量处理同类任务，流程化",
            "Day 10: 尝试团队任务/邀请奖励",
            "Day 11: 专注最高时薪的任务类型",
            "Day 12: 建立个人标注质量评分",
            "Day 13: 申请平台高级认证",
            "Day 14: 总结2周数据，确定最优平台和任务类型",
        ],
        "income_expectation": "第1周内见钱，预期500-2000元/月，属于'时间换小钱'，时薪通常15-40元",
        "expected_hours_per_week": 15.0,
        "expected_first_income_days": 3,
        "expected_income_range": "500-2000元/月",
    },
    "training": {
        "verification_first_step": "免费教1个人看反馈",
        "checklist": [
            "Day 1: 确定教学主题和目标学员画像",
            "Day 2: 在社交媒体发帖，免费招1个学员",
            "Day 3: 第1次教学，记录学员问题和反馈",
            "Day 4: 根据反馈调整教学内容",
            "Day 5: 第2次教学，加入互动环节",
            "Day 6: 让学员写评价/推荐",
            "Day 7: 用AI生成课程大纲和练习题",
            "Day 8: 设计付费课程结构（3-5节课）",
            "Day 9: 在知识付费平台发布课程",
            "Day 10: 招募第2-3个付费学员",
            "Day 11: 收集付费学员反馈，优化课程",
            "Day 12: 建立学员社群，提高复购",
            "Day 13: 设计进阶课程/1v1辅导包",
            "Day 14: 总结2周数据，确定课程定价和方向",
        ],
        "income_expectation": "第2-3周开始收费，预期300-2000元/月，属于'知识换钱'，单价随口碑逐步提升",
        "expected_hours_per_week": 10.0,
        "expected_first_income_days": 14,
        "expected_income_range": "300-2000元/月",
    },
    "cross-border": {
        "verification_first_step": "Fiverr上架一个服务",
        "checklist": [
            "Day 1: 注册Fiverr/Upwork账号，完善个人资料",
            "Day 2: 研究同类服务定价和描述，找差异化切入点",
            "Day 3: 创建第1个Gig，定价$5-15起步",
            "Day 4: 用AI优化Gig描述和标签（英文SEO）",
            "Day 5: 在Reddit/Twitter推广服务",
            "Day 6: 主动在Upwork投3个相关项目",
            "Day 7: 完成第1单（可亏本），收集5星评价",
            "Day 8: 根据第1单经验优化服务描述",
            "Day 9: 创建第2个Gig变体，测试不同需求",
            "Day 10: 分析竞品定价，调整价格策略",
            "Day 11: 建立标准交付流程和模板",
            "Day 12: 尝试Fiverr Promoted Gigs功能",
            "Day 13: 积累到10个评价后提价20%",
            "Day 14: 总结2周数据，确定主力服务和定价",
        ],
        "income_expectation": "第1-3周可能出单，预期$100-500/月，属于'跨境技能换钱'，美元结算有汇率优势",
        "expected_hours_per_week": 12.0,
        "expected_first_income_days": 10,
        "expected_income_range": "$100-500/月",
    },
}

_DEFAULT_TEMPLATE: Dict[str, Any] = {
    "verification_first_step": "找1个潜在客户验证需求",
    "checklist": [
        "Day 1: 明确服务/产品定义，确定目标客户",
        "Day 2: 找到3个目标客户，发送介绍",
        "Day 3: 跟进反馈，记录客户痛点",
        "Day 4: 根据反馈调整服务定义",
        "Day 5: 完成第1个小单/免费试做",
        "Day 6: 收集反馈和评价",
        "Day 7: 用AI优化服务描述和流程",
        "Day 8: 拓展获客渠道（+1个平台）",
        "Day 9: 优化交付流程，缩短时间",
        "Day 10: 提价测试",
        "Day 11: 复盘数据，确定核心服务",
        "Day 12: 建立标准SOP",
        "Day 13: 尝试upsell或拓展服务线",
        "Day 14: 总结2周数据，决定方向",
    ],
    "income_expectation": "第2-4周可能见收入，预期300-2000元/月，具体取决于服务类型和客户获取效率",
    "expected_hours_per_week": 12.0,
    "expected_first_income_days": 14,
    "expected_income_range": "300-2000元/月",
}

_AI_LEVERAGE_BY_CATEGORY: Dict[str, List[str]] = {
    "content": [
        "用AI批量生成内容选题和大纲",
        "AI辅助撰写初稿，人工润色发布",
        "AI分析竞品内容数据，找爆款规律",
        "AI生成多平台分发的改写版本",
    ],
    "freelance": [
        "AI生成服务描述和营销文案",
        "AI辅助完成重复性交付工作",
        "AI自动化客户沟通模板",
        "AI分析竞品定价策略",
    ],
    "tool": [
        "AI辅助写代码，加速MVP开发",
        "AI生成用户文档和帮助中心",
        "AI分析用户反馈，提取核心需求",
        "AI生成营销文案和landing page",
    ],
    "annotation": [
        "AI辅助预标注，提高任务完成速度",
        "AI自动化质检，减少返工",
        "AI生成标注指南速查表",
    ],
    "training": [
        "AI生成课程大纲和练习题",
        "AI辅助批改学员作业",
        "AI生成课程营销文案",
        "AI整理学员常见问题FAQ",
    ],
    "cross-border": [
        "AI优化英文服务描述和SEO",
        "AI翻译和本地化服务内容",
        "AI生成客户沟通模板（英文）",
        "AI分析海外平台竞品数据",
    ],
}

_DEFAULT_AI_LEVERAGE: List[str] = [
    "AI辅助生成营销和推广内容",
    "AI自动化重复性工作流程",
    "AI分析数据，辅助决策",
]


# ---------------------------------------------------------------------------
# Hard red lines — if detected, the plan should warn
# ---------------------------------------------------------------------------

_HARD_RED_LINES: List[Dict[str, Any]] = [
    {
        "id": "A1",
        "keywords": ["先付款", "先交钱", "预付", "保证金", "押金", "会员费", "入会费"],
        "message": "要求你先付款才能开始 — 这是诈骗核心标志",
    },
    {
        "id": "A2",
        "keywords": ["刷单", "刷好评", "刷信誉", "刷流水", "套现"],
        "message": "涉及刷单/刷好评 — 违法且通常是骗局",
    },
    {
        "id": "A3",
        "keywords": ["拉人头", "发展下线", "裂变奖金", "层级佣金", "无限代"],
        "message": "收入主要来自拉人而非销售 — 传销结构",
    },
    {
        "id": "A4",
        "keywords": ["日入过千", "日赚万元", "躺赚", "零风险", "稳赚", "保底月入"],
        "message": "承诺高额零风险收入 — 违反基本经济逻辑",
    },
    {
        "id": "A5",
        "keywords": ["银行卡", "身份证正反面", "手持身份证", "密码", "验证码"],
        "message": "索要敏感个人信息/证件 — 身份盗用风险",
    },
    {
        "id": "A6",
        "keywords": ["私下转账", "个人账户", "不走平台", "微信直接转", "支付宝直接转"],
        "message": "要求绕过平台私下交易 — 失去所有保障",
    },
]

_SUSPECT_SIGNALS: List[Dict[str, Any]] = [
    {
        "id": "B1",
        "keywords": ["代理费", "加盟费", "授权费", "技术转让费"],
        "message": "需要付费获取'资格'或'授权'",
    },
    {
        "id": "B2",
        "keywords": ["名额有限", "最后X个", "即将截止", "限时优惠"],
        "message": "制造紧迫感逼迫快速决策",
    },
    {
        "id": "B3",
        "keywords": ["截图收益", "晒单", "到账截图", "收入截图"],
        "message": "用收益截图作为主要说服手段",
    },
    {
        "id": "B4",
        "keywords": ["不需要技能", "无需经验", "有手就行", "小白也能"],
        "message": "声称零门槛高收入 — 要么骗局要么时薪极低",
    },
    {
        "id": "B5",
        "keywords": ["培训费", "课程费", "资料费", "工具费"],
        "message": "在开始前要求购买培训/资料",
    },
    {
        "id": "B6",
        "keywords": ["推荐奖励", "邀请返现", "推荐一个人给", "拉一个朋友"],
        "message": "收入主要来自推荐他人而非实际工作",
    },
]


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionPlan:
    opportunity_id: str
    opportunity_name: str
    verification_first_step: str
    two_week_checklist: List[str]
    income_expectation: str
    stop_loss_line: str
    ai_leverage_points: List[str]
    expected_hours_per_week: float
    expected_first_income_days: int
    expected_income_range: str
    created_at: str
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ActionPlan:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_plan(opportunity: dict, profile: dict | None = None) -> ActionPlan:
    """Generate an ActionPlan from an opportunity dict and user profile."""
    profile = profile or {}
    opp_id = str(opportunity.get("id", opportunity.get("opportunity_id", "unknown")))
    opp_name = str(opportunity.get("name", opportunity.get("title", opp_id)))
    category = _detect_category(opportunity)

    template = _CATEGORY_TEMPLATES.get(category, _DEFAULT_TEMPLATE)
    ai_leverage = _AI_LEVERAGE_BY_CATEGORY.get(category, _DEFAULT_AI_LEVERAGE)

    warnings = _check_red_flags(opportunity)

    stop_loss = _build_stop_loss_line(opportunity, warnings)

    return ActionPlan(
        opportunity_id=opp_id,
        opportunity_name=opp_name,
        verification_first_step=template["verification_first_step"],
        two_week_checklist=list(template["checklist"]),
        income_expectation=template["income_expectation"],
        stop_loss_line=stop_loss,
        ai_leverage_points=list(ai_leverage),
        expected_hours_per_week=float(template["expected_hours_per_week"]),
        expected_first_income_days=int(template["expected_first_income_days"]),
        expected_income_range=template["expected_income_range"],
        created_at=_now_iso(),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_category(opportunity: dict) -> str:
    """Detect opportunity category from its fields."""
    category = opportunity.get("category", "")
    if category in _CATEGORY_TEMPLATES:
        return category

    text = " ".join(
        str(v) for v in opportunity.values() if isinstance(v, (str, int, float))
    )
    text_lower = _normalize(text)

    category_phrases: Dict[str, list[str]] = {
        "content": ["content", "blog", "video", "tiktok", "douyin", "xiaohongshu",
                     "公众号", "自媒体", "短视频", "写作", "创作", "粉丝", "流量",
                     "youtube", "bilibili", "抖音", "小红书", "快手"],
        "freelance": ["freelance", "接单", "外包", "众包", "闲鱼", "设计", "翻译",
                       "p图", "代写", "陪聊", "跑腿"],
        "tool": ["saas", "app", "小程序", "工具", "plugin", "extension", "api",
                 "landing", "mvp", "独立开发", "产品", "chrome插件"],
        "annotation": ["标注", "annotation", "labeling", "数据标注", "众包标注",
                        "百度众测", "scale ai", "remotasks", "众测"],
        "training": ["培训", "教学", "课程", "辅导", "家教", "训练营", "教练",
                      "知识付费", "咨询"],
        "cross-border": ["fiverr", "upwork", "跨境", "海外", "出海", "freelancer",
                          "美元", "dollar", "外币"],
    }

    best_cat = ""
    best_score = 0
    for cat, phrases in category_phrases.items():
        hits = sum(1 for p in phrases if p in text_lower)
        if hits > best_score:
            best_score = hits
            best_cat = cat

    return best_cat if best_score > 0 else ""


def _check_red_flags(opportunity: dict) -> List[str]:
    """Check for hard red lines and suspect signals in opportunity text."""
    text = " ".join(
        str(v) for v in opportunity.values() if isinstance(v, (str, int, float))
    )
    text_lower = text.lower()
    warnings: List[str] = []

    for line in _HARD_RED_LINES:
        for kw in line["keywords"]:
            if kw.lower() in text_lower:
                warnings.append(f"[{line['id']}] {line['message']}")
                break

    for sig in _SUSPECT_SIGNALS:
        for kw in sig["keywords"]:
            if kw.lower() in text_lower:
                warnings.append(f"[{sig['id']}] {sig['message']}")
                break

    return warnings


def _build_stop_loss_line(opportunity: dict, warnings: List[str]) -> str:
    """Build a context-aware stop-loss line."""
    has_red = any(w.startswith("[A") for w in warnings)
    has_suspect = any(w.startswith("[B") for w in warnings)

    parts: List[str] = []

    if has_red:
        parts.append("立即停止 — 存在硬性红线，不值得冒险")

    parts.append("累计投入超过20小时零正反馈 → 停止")
    parts.append("任何要求先付款/交押金的情况 → 立即停止")
    parts.append("遇到要求提供身份证/银行卡信息 → 立即停止并举报")

    if has_suspect:
        parts.append("存在可疑信号，投入上限减半（10小时零正反馈即停）")

    return " | ".join(parts)
