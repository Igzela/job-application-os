"""Opportunity finder: tier-based template matching for AI side-income.

Reads a user profile, classifies their tier (T0-T3), filters the 6-category
taxonomy, generates template Opportunities with reasoning chains, and runs
scam-check heuristics on each.  Does NOT do web search — that's the agent's job.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers (mirrored from scorer.py)
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _keywords_from(text: str) -> set[str]:
    tokens = _normalize(text).split()
    stopwords = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "this", "that",
        "these", "those", "it", "its", "we", "our", "you", "your", "they",
        "their", "i", "my", "me", "he", "she", "his", "her", "him",
    }
    return {t for t in tokens if len(t) > 2 and t not in stopwords}


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union) if union else 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Scam-check heuristics (A1-A6 hard red lines, B1-B6 suspect signals)
# ---------------------------------------------------------------------------

# A-series: hard red lines — verdict = "scam"
_A_RED_LINES: list[tuple[str, list[str]]] = [
    ("A1", ["upfront fee", "prepay", "deposit required", "pay to start",
            "training fee", "enrollment fee", "membership fee"]),
    ("A2", ["guaranteed income", "100% guaranteed", "risk free", "no risk",
            "earn guaranteed"]),
    ("A3", ["recruit others", "bring in friends", "pyramid", "mlm",
            "multi level", "referral bonus for recruiting"]),
    ("A4", ["crypto wallet", "send crypto", "wire transfer first",
            "gift card", "western union"]),
    ("A5", ["no experience needed", "anyone can do it", "zero skill",
            "no skill required", "effortless money"]),
    ("A6", ["act now", "limited spots", "expires today", "hurry",
            "only 3 left", "last chance"]),
]

# B-series: suspect signals — verdict = "suspect"
_B_SUSPECT: list[tuple[str, list[str]]] = [
    ("B1", ["dm for details", "contact privately", "whatsapp only",
            "telegram only", "pm me"]),
    ("B2", ["too good to be true", "easy money", "get rich", "passive income",
            "money while you sleep"]),
    ("B3", ["vague description", "details later", "more info on call",
            "can't explain here"]),
    ("B4", ["new company", "just launched", "brand new platform",
            "no reviews yet"]),
    ("B5", ["commission only", "no base pay", "pure commission",
            "earn per sale only"]),
    ("B6", ["unrealistic rate", "500 per hour", "1000 per day",
            "earn 10k monthly"]),
]

VERDICT_CLEAN = "clean"
VERDICT_SUSPECT = "suspect"
VERDICT_SCAM = "scam"


@dataclass(frozen=True)
class ScamVerdict:
    label: str  # "clean" | "suspect" | "scam"
    triggered_rules: List[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ScamVerdict:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def check_scam(text: str) -> ScamVerdict:
    """Run heuristic scam checks on a text blob. Returns ScamVerdict."""
    lower = text.lower()
    triggered: list[str] = []

    for rule_id, patterns in _A_RED_LINES:
        if any(p in lower for p in patterns):
            triggered.append(rule_id)

    if triggered:
        return ScamVerdict(
            label=VERDICT_SCAM,
            triggered_rules=triggered,
            reasoning=f"Hard red lines triggered: {', '.join(triggered)}",
        )

    for rule_id, patterns in _B_SUSPECT:
        if any(p in lower for p in patterns):
            triggered.append(rule_id)

    if triggered:
        return ScamVerdict(
            label=VERDICT_SUSPECT,
            triggered_rules=triggered,
            reasoning=f"Suspect signals triggered: {', '.join(triggered)}",
        )

    return ScamVerdict(label=VERDICT_CLEAN, reasoning="No scam signals detected")


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

_TIERS = ("T0", "T1", "T2", "T3")

_TIER_KEYWORDS: dict[str, list[str]] = {
    "T3": ["domain expert", "industry expert", "consultant", "specialist",
            "professional", "years experience", "senior", "lead", "manager"],
    "T2": ["python", "javascript", "programming", "coding", "developer",
            "software", "engineer", "api", "github", "react", "node"],
    "T1": ["chatgpt", "midjourney", "stable diffusion", "ai tool",
            "prompt", "canva", "notion", "copywriting", "translation",
            "design", "video editing", "voiceover"],
    "T0": ["beginner", "newbie", "no experience", "just started",
            "learning", "curious", "want to try"],
}


def classify_tier(profile: dict[str, Any]) -> str:
    """Classify user into T0-T3 from profile dict. Defaults to T0."""
    if not profile:
        return "T0"

    tier_hint = profile.get("tier", "")
    if tier_hint in _TIERS:
        return tier_hint

    text_parts: list[str] = []
    for key in ("skills", "experience", "bio", "description", "background"):
        val = profile.get(key)
        if isinstance(val, list):
            text_parts.extend(str(v) for v in val)
        elif isinstance(val, str):
            text_parts.append(val)

    blob = _keywords_from(" ".join(text_parts))

    for tier in reversed(_TIERS):
        tier_kw = _keywords_from(" ".join(_TIER_KEYWORDS[tier]))
        if _overlap(blob, tier_kw) > 0.05:
            return tier

    return "T0"


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, dict[str, Any]] = {
    "content": {
        "name": "AI Content Creation Monetization",
        "name_zh": "内容创作变现",
        "description": "Ads, platform revenue share, knowledge monetization",
        "min_tier": "T0",
        "keywords": ["content", "writing", "blog", "video", "ads", "monetize",
                      "knowledge", "course", "youtube", "xiaohongshu", "douyin"],
    },
    "freelance": {
        "name": "AI-Assisted Skill Services",
        "name_zh": "技能服务外包",
        "description": "Copywriting, translation, PPT, design, video, voiceover",
        "min_tier": "T1",
        "keywords": ["freelance", "copywriting", "translation", "ppt", "design",
                      "video", "voiceover", "fiverr", "upwork", "service"],
    },
    "tool": {
        "name": "AI Tool B-Side Delivery",
        "name_zh": "AI工具B端交付",
        "description": "Digital humans, e-commerce images, customer service bots",
        "min_tier": "T1",
        "keywords": ["tool", "b2b", "enterprise", "digital human", "ecommerce",
                      "customer service", "chatbot", "automation", "saas"],
    },
    "annotation": {
        "name": "Data Annotation / Model Evaluation",
        "name_zh": "数据标注/模型评测",
        "description": "Labeling data, evaluating model outputs",
        "min_tier": "T0",
        "keywords": ["annotation", "labeling", "data", "evaluation", "review",
                      "model", "training data", "quality"],
    },
    "training": {
        "name": "AI Training / Coaching",
        "name_zh": "AI培训/教练",
        "description": "Teaching AI skills, corporate training (high barrier)",
        "min_tier": "T2",
        "keywords": ["training", "coaching", "teaching", "workshop", "course",
                      "mentor", "corporate", "curriculum"],
    },
    "cross-border": {
        "name": "Cross-border / Information Arbitrage",
        "name_zh": "跨境/信息差",
        "description": "Leveraging information gaps across markets",
        "min_tier": "T1",
        "keywords": ["cross-border", "arbitrage", "overseas", "global",
                      "international", "information gap", "import", "export"],
    },
}

_TIER_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def _categories_for_tier(tier: str, direction: str | None = None) -> list[str]:
    """Return category keys accessible to the given tier, optionally filtered."""
    tier_level = _TIER_ORDER.get(tier, 0)
    result = []
    for cat_key, cat in CATEGORIES.items():
        min_level = _TIER_ORDER.get(cat["min_tier"], 0)
        if tier_level >= min_level:
            if direction and direction != cat_key:
                continue
            result.append(cat_key)
    return result


# ---------------------------------------------------------------------------
# Opportunity dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Opportunity:
    id: str
    name: str
    category: str
    for_tier: str
    money_source: str
    verdict: str  # ScamVerdict label
    verify_first_step: str
    income_expectation: str
    reasoning_chain: str
    cross_verification: str
    status: str = "candidate"
    found_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> Opportunity:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Template generators per category
# ---------------------------------------------------------------------------

def _template_content(tier: str) -> dict[str, str]:
    return {
        "name": "AI-Assisted Content Monetization",
        "money_source": "Platform ad revenue share, knowledge payments, sponsored content",
        "verify_first_step": "Pick one platform (e.g. Xiaohongshu/YouTube), post 5 AI-assisted articles/videos, measure engagement after 7 days",
        "income_expectation": "T0: 15-50 CNY/hr equivalent; T1+: scales with audience, 500-5000 CNY/month after 3 months",
        "reasoning_chain": "Low barrier to entry -> AI reduces content creation time 3-5x -> platforms pay for engagement -> consistent posting builds audience",
        "cross_verification": "Check platform monetization thresholds; verify ad revenue rates on creator forums; compare with existing creators in niche",
    }


def _template_freelance(tier: str) -> dict[str, str]:
    return {
        "name": "AI-Assisted Freelance Services",
        "money_source": "Direct client payments via freelance platforms (Fiverr, Upwork, local equivalents)",
        "verify_first_step": "Create profile on one platform, list 3 AI-assisted services, send 10 proposals in first week",
        "income_expectation": "T1: 50-200 CNY/hr; T2: 100-500 CNY/hr for technical services",
        "reasoning_chain": "AI amplifies output quality and speed -> clients pay for deliverables not process -> freelance platforms provide demand -> repeat clients compound",
        "cross_verification": "Check platform fee structure; verify average rates for similar services; test with small paid gig first",
    }


def _template_tool(tier: str) -> dict[str, str]:
    return {
        "name": "AI Tool B-Side Delivery",
        "money_source": "Monthly retainers or per-project fees from businesses needing AI tooling",
        "verify_first_step": "Identify 3 local businesses, offer free 1-week AI tool demo (e.g. automated customer replies), measure time saved",
        "income_expectation": "T1: 1000-5000 CNY/month per client; T2+: 5000-20000 CNY/month for custom solutions",
        "reasoning_chain": "Businesses need AI but lack expertise -> you bridge the gap -> recurring need creates retainer income -> referrals expand client base",
        "cross_verification": "Talk to 3 business owners about AI pain points; check competitor pricing; verify tool reliability for production use",
    }


def _template_annotation(tier: str) -> dict[str, str]:
    return {
        "name": "Data Annotation / Model Evaluation",
        "money_source": "Per-task payments from annotation platforms (Scale AI, Appen, local equivalents)",
        "verify_first_step": "Register on 2 annotation platforms, complete qualification tests, take first 10 paid tasks",
        "income_expectation": "T0: 15-40 CNY/hr; T1+: 30-80 CNY/hr for specialized evaluation",
        "reasoning_chain": "AI companies need human judgment -> annotation is always in demand -> low barrier but consistency matters -> specialized domains pay more",
        "cross_verification": "Check platform payment history on forums; verify task availability in your timezone; test with small batch first",
    }


def _template_training(tier: str) -> dict[str, str]:
    return {
        "name": "AI Training / Coaching",
        "money_source": "Course sales, corporate workshop fees, coaching subscriptions",
        "verify_first_step": "Create a 30-min free workshop on a specific AI skill, post recording, measure sign-ups for paid version",
        "income_expectation": "T2: 2000-10000 CNY/month from courses; T3: 10000-50000 CNY/month for corporate training",
        "reasoning_chain": "Deep AI knowledge is rare -> businesses will pay to upskill teams -> content scales (record once, sell many) -> reputation compounds",
        "cross_verification": "Check existing course pricing on platforms; verify demand via search volume; test with free content first to gauge interest",
    }


def _template_cross_border(tier: str) -> dict[str, str]:
    return {
        "name": "Cross-border / Information Arbitrage",
        "money_source": "Margin on cross-market transactions, consulting fees for market entry",
        "verify_first_step": "Identify one product/service cheaper in market A than B, list on accessible platform, measure demand for 2 weeks",
        "income_expectation": "T1: 500-3000 CNY/month arbitrage; T2+: 5000-20000 CNY/month for systematic plays",
        "reasoning_chain": "Information gaps exist between markets -> AI helps identify and bridge them -> language is no longer a barrier -> first-mover advantage in niche gaps",
        "cross_verification": "Verify price differential with real transactions; check import/export regulations; test with small inventory first",
    }


_TEMPLATES: dict[str, Any] = {
    "content": _template_content,
    "freelance": _template_freelance,
    "tool": _template_tool,
    "annotation": _template_annotation,
    "training": _template_training,
    "cross-border": _template_cross_border,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_opportunities(
    profile: dict[str, Any],
    direction: str | None = None,
) -> list[Opportunity]:
    """Find template opportunities matching the user's profile.

    Args:
        profile: User profile dict with keys like skills, experience, tier, etc.
        direction: Optional category filter (one of the 6 category keys).

    Returns:
        List of Opportunity dataclass instances, scam-checked.
    """
    if not profile:
        return []

    tier = classify_tier(profile)
    categories = _categories_for_tier(tier, direction)

    opportunities: list[Opportunity] = []
    for cat_key in categories:
        cat = CATEGORIES[cat_key]
        template_fn = _TEMPLATES[cat_key]
        tmpl = template_fn(tier)

        scam_text = f"{tmpl['name']} {tmpl['money_source']} {tmpl['verify_first_step']}"
        verdict = check_scam(scam_text)

        opp = Opportunity(
            id=f"opp-{cat_key}-{uuid.uuid4().hex[:8]}",
            name=tmpl["name"],
            category=cat_key,
            for_tier=tier,
            money_source=tmpl["money_source"],
            verdict=verdict.label,
            verify_first_step=tmpl["verify_first_step"],
            income_expectation=tmpl["income_expectation"],
            reasoning_chain=tmpl["reasoning_chain"],
            cross_verification=tmpl["cross_verification"],
        )
        opportunities.append(opp)

    return opportunities
