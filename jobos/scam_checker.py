from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _keywords_from(text: str) -> set[str]:
    tokens = _normalize(text).split()
    return {t for t in tokens if len(t) > 1}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Rule definitions
# ---------------------------------------------------------------------------

_HARD_RULES: list[tuple[str, str, list[str]]] = [
    ("A1", "入门费", ["入门费", "培训费", "会员费", "保证金", "押金", "激活码", "购买课程", "设备费", "先交钱", "先付"]),
    ("A2", "收入承诺", ["日入千元", "月入过万", "躺赚", "被动收入", "保底收益", "稳赚不赔", "轻松月入", "零风险高回报", "日赚", "月赚"]),
    ("A3", "拉人头", ["拉人头", "邀请返利", "层级分佣", "发展下线", "团队奖励", "裂变", "分销", "拉新"]),
    ("A4", "资金走账", ["刷单", "走账", "过账", "代付", "跑分", "租借银行卡", "出租收款码", "资金中转", "代收款"]),
    ("A5", "卖课", ["教你赚钱", "副业课程", "赚钱训练营", "暴利项目", "月入X万教程", "赚钱教程", "副业教程"]),
    ("A6", "灰色项目", ["代写论文", "虚假广告", "刷好评", "平台漏洞", "爬取个人信息", "灰色项目", "撸羊毛"]),
]

_SUSPECT_RULES: list[tuple[str, str, list[str]]] = [
    ("B1", "无第三方验证", ["没有真实反馈", "只有推广帖", "无第三方验证"]),
    ("B2", "远超市场价", ["高薪日结", "远超市场价", "天价报酬"]),
    ("B3", "私聊交易", ["加微信", "QQ群", "私聊交易", "不走平台"]),
    ("B4", "限时施压", ["限时", "名额有限", "今天不付就没了", "最后X个名额", "仅限今天"]),
    ("B5", "试做任务", ["试做任务", "先做一单试试", "入群领取", "免费体验"]),
    ("B6", "匿名雇主", ["公司查不到", "无营业执照", "匿名雇主"]),
]

_INCOME_EXPECTATIONS: dict[str, str] = {
    "high-risk": "本条目存在明显诈骗特征，不建议投入任何资金或时间。合法兼职收入通常在每小时15-50元人民币。",
    "suspect": "收入信息未经验证，建议先小额试水并要求第三方担保。市场正常兼职收入在每小时15-50元人民币。",
    "feasible": "收入需根据实际技能和市场行情评估，建议参考同类岗位的公开招聘薪资。",
}

_VERIFY_STEPS: dict[str, str] = {
    "high-risk": "立即停止接触，不要支付任何费用。可向当地劳动监察部门或12315投诉平台举报。",
    "suspect": "要求对方提供营业执照、公司官网和第三方评价，先尝试小额交易验证真实性和付款流程。",
    "feasible": "在天眼查/企查查核实公司信息，要求签署正式合同或协议。",
}


# ---------------------------------------------------------------------------
# ScamVerdict
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScamVerdict:
    name: str
    verdict: str
    red_flags: list[str]
    suspect_flags: list[str]
    reason: str
    verify_first_step: str
    income_expectation: str
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ScamVerdict:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_opportunity(
    name: str,
    description: str,
    profile: dict[str, Any] | None = None,
) -> ScamVerdict:
    combined = f"{name} {description}"
    red_hits: list[str] = []
    suspect_hits: list[str] = []

    for code, label, keywords in _HARD_RULES:
        if _contains_any(combined, keywords):
            red_hits.append(f"{code}: {label}")

    for code, label, keywords in _SUSPECT_RULES:
        if _contains_any(combined, keywords):
            suspect_hits.append(f"{code}: {label}")

    if red_hits:
        verdict = "high-risk"
    elif suspect_hits:
        verdict = "suspect"
    else:
        verdict = "feasible"

    parts: list[str] = []
    if red_hits:
        parts.append(f"触发红线: {', '.join(red_hits)}")
    if suspect_hits:
        parts.append(f"可疑信号: {', '.join(suspect_hits)}")
    if not parts:
        parts.append("未发现明显的诈骗或可疑特征")
    reason = "; ".join(parts)

    return ScamVerdict(
        name=name,
        verdict=verdict,
        red_flags=red_hits,
        suspect_flags=suspect_hits,
        reason=reason,
        verify_first_step=_VERIFY_STEPS[verdict],
        income_expectation=_INCOME_EXPECTATIONS[verdict],
        checked_at=_now_iso(),
    )
