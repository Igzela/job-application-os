"""BOSS Zhipin page extraction with optional Scrapling support.

The public ``parse_*`` functions preserve the old lightweight parser API.
Richer callers should use ``extract_boss_job_list`` and
``classify_boss_page`` to get extractor choice, selector attempts, page-state
classification, and fallback diagnostics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List

from bs4 import BeautifulSoup

from .extraction import (
    ExtractedJobCard,
    ExtractionDiagnostics,
    PageClassification,
    PageExtractionResult,
    SelectorAttempt,
)
from .scrapling_runtime import create_selector

try:
    from scrapling.parser import Selector
except ImportError:
    Selector = None


BOSS_ORIGIN = "https://www.zhipin.com"

CARD_SELECTORS = [
    "li.job-card-box",
    "[class*='job-card-box']",
    "[class*='job-card-wrap']",
    ".job-card-wrapper",
    ".search-job-result li",
    "[data-job-card]",
    "article[data-job-id]",
    "[class*='job-card']",
]

TITLE_SELECTORS = [
    "a.job-name",
    ".job-name",
    "[class*='job-name']",
    "[data-role='job-title']",
    "[data-job-title]",
    "[class*='job-title'] a",
    "[class*='job-title']",
]

COMPANY_SELECTORS = [
    ".boss-name",
    ".company-name",
    "[data-company]",
    "[class*='company-name']",
    "[class*='company'] a",
    "[class*='company']",
]

SALARY_SELECTORS = [
    ".job-salary",
    "[class*='job-salary']",
    "[data-salary]",
    "[class*='salary']",
]

LOCATION_SELECTORS = [
    ".company-location",
    ".job-area",
    "[data-location]",
    "[class*='location']",
    "[class*='area']",
]

TAG_SELECTORS = [
    ".tag-list li",
    "[class*='tag-list'] li",
    "[class*='tag'] li",
    "[data-tag]",
]

LINK_SELECTORS = [
    "a[href*='job_detail']",
    "a.job-name",
    "[class*='job-name']",
]


@dataclass(frozen=True)
class BossJob:
    job_id: str
    title: str
    company: str
    salary: str
    location: str
    tags: List[str] = field(default_factory=list)
    url: str = ""


def scrapling_available() -> bool:
    return Selector is not None


def parse_job_list(html: str) -> List[BossJob]:
    """Parse job listing page HTML into structured job data."""
    result = extract_boss_job_list(html)
    return [
        BossJob(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            salary=job.salary,
            location=job.location,
            tags=list(job.tags),
            url=job.url,
        )
        for job in result.jobs
    ]


def extract_boss_job_list(
    html: str,
    *,
    url: str = "",
    title: str = "",
    use_scrapling: bool | None = None,
    adaptive: bool = True,
    adaptive_store: str = "~/.jobos/scrapling.db",
    adaptive_percentage: int = 40,
) -> PageExtractionResult:
    """Extract BOSS job cards and classify the page state.

    ``use_scrapling=None`` means "use Scrapling when installed". Passing
    ``False`` forces the BeautifulSoup fallback for fixture replay and tests.
    """
    classification = classify_boss_page(html, url=url, title=title)
    attempts: list[SelectorAttempt] = []
    warnings: list[str] = []
    allow_scrapling = scrapling_available() if use_scrapling is None else use_scrapling

    if allow_scrapling and Selector is not None:
        try:
            jobs, adaptive_recovered = _parse_with_scrapling(
                html,
                attempts,
                url=url or BOSS_ORIGIN,
                adaptive=adaptive,
                adaptive_store=adaptive_store,
                adaptive_percentage=adaptive_percentage,
            )
        except Exception as exc:
            warnings.append(f"scrapling_failed: {exc}")
            jobs = []
            adaptive_recovered = False
        if jobs:
            classification = _normal_classification(classification, len(jobs))
            return _result(
                jobs,
                classification,
                "scrapling",
                attempts,
                warnings,
                False,
                adaptive_enabled=adaptive,
                adaptive_recovered=adaptive_recovered,
            )
        if classification.state in ("login_required", "verification_required", "access_limited", "empty"):
            return _result([], classification, "scrapling", attempts, warnings, False)
        warnings.append("scrapling_found_no_jobs")

    fallback_attempts: list[SelectorAttempt] = []
    fallback_jobs = _parse_with_bs4(html, fallback_attempts)
    attempts.extend(fallback_attempts)
    fallback_used = allow_scrapling and Selector is not None
    extractor = "beautifulsoup" if not fallback_used else "beautifulsoup_fallback"
    if fallback_jobs:
        classification = _normal_classification(classification, len(fallback_jobs))
    elif classification.state == "normal":
        classification = PageClassification(
            state="page_shape_changed",
            reason="No job cards matched known selectors on a page that otherwise looked like BOSS results.",
            recovery="Capture the page HTML and add/update selectors or Scrapling fixtures.",
            signals={**classification.signals, "job_count": 0},
        )
    return _result(fallback_jobs, classification, extractor, attempts, warnings, fallback_used)


def classify_boss_page(html: str, *, url: str = "", title: str = "") -> PageClassification:
    """Classify BOSS page state using stable recovery-oriented labels."""
    soup = BeautifulSoup(html or "", "html.parser")
    body_text = _compact_text(soup.get_text(" "))
    lower = body_text.lower()
    signals: dict[str, Any] = {
        "url": url,
        "title": title,
        "text_length": len(body_text),
    }
    card_count = _count_any_bs4(soup, CARD_SELECTORS)
    salary_nodes = _count_any_bs4(soup, SALARY_SELECTORS)
    result_containers = _count_any_bs4(soup, [".search-job-result", "[class*='job-list']", "[class*='job-result']"])
    detail_containers = _count_any_bs4(soup, [".job-detail-header", ".job-sec-text", "[class*='job-detail']"])
    signals.update(
        {
            "card_count": card_count,
            "salary_node_count": salary_nodes,
            "result_container_count": result_containers,
            "detail_container_count": detail_containers,
        }
    )

    if _has_any(body_text, ["安全验证", "滑块验证", "请输入验证码", "验证后继续访问", "拖动"]):
        return PageClassification(
            state="verification_required",
            reason="BOSS security verification or captcha text was detected.",
            recovery="Solve the verification in the browser, then retry the import or submit attempt.",
            signals=signals,
        )
    if _has_any(body_text, ["访问受限", "异常访问", "访问过于频繁", "forbidden", "access denied", "403"]):
        return PageClassification(
            state="access_limited",
            reason="The page appears to be rate-limited or access-limited.",
            recovery="Pause automation and retry later from the logged-in browser session.",
            signals=signals,
        )
    if _has_any(
        body_text,
        ["登录后查看", "立即登录", "登录/注册", "扫码登录", "账号密码登录", "未登录"],
    ):
        return PageClassification(
            state="login_required",
            reason="Login prompt text was detected.",
            recovery="Log into BOSS Zhipin in the browser and retry.",
            signals=signals,
        )
    if card_count > 0 or detail_containers > 0:
        return PageClassification(
            state="normal",
            reason="Known BOSS job selectors matched.",
            signals=signals,
        )
    if _has_any(body_text, ["暂无职位", "没有找到", "无搜索结果", "未找到相关", "no results"]):
        return PageClassification(
            state="empty",
            reason="The page indicates an empty result set.",
            recovery="Try a broader keyword or different city.",
            signals=signals,
        )
    if result_containers or salary_nodes:
        return PageClassification(
            state="page_shape_changed",
            reason="Result-like containers exist, but no known job-card selector matched.",
            recovery="Replay the captured HTML fixture and update selectors.",
            signals=signals,
        )
    return PageClassification(
        state="empty",
        reason="No job-card or result-container signals were detected.",
        recovery="Confirm the page loaded the expected BOSS result or detail view.",
        signals=signals,
    )


def parse_job_detail(html: str) -> dict:
    """Parse job detail page into structured data."""
    if Selector is None:
        return _parse_job_detail_bs4(html)

    page = Selector(html)
    result = {}

    title_el = _first_scrapling(page, [".job-detail-header .name", "[class*='job-name']", "[class*='name']"])
    result["title"] = _text(title_el)

    salary_el = _first_scrapling(page, [".job-detail-header .salary", "[class*='salary']"])
    result["salary"] = _text(salary_el)

    desc_el = _first_scrapling(page, [".job-sec-text", ".detail-content", "[class*='job-detail']"])
    result["description"] = _text(desc_el)

    info_els = _all_scrapling(page, [".job-info .tag-list li", "[class*='info-tag'] li"])
    result["info_tags"] = [_text(t) for t in info_els if _text(t)]

    return result


def parse_chat_page(html: str) -> dict:
    """Parse BOSS chat page for form fields."""
    if Selector is None:
        soup = BeautifulSoup(html or "", "html.parser")
        greeting = _first_bs4(soup, [".chat-editor textarea", "[class*='editor'] textarea", "textarea"])
        return {"greeting_input": _attr_bs4(greeting, "placeholder") if greeting else ""}

    page = Selector(html)
    greeting_el = _first_scrapling(page, [".chat-editor textarea", "[class*='editor'] textarea", "textarea"])
    return {"greeting_input": _attr(greeting_el, "placeholder") or ""}


def _parse_with_scrapling(
    html: str,
    attempts: list[SelectorAttempt],
    *,
    url: str,
    adaptive: bool,
    adaptive_store: str,
    adaptive_percentage: int,
) -> tuple[list[ExtractedJobCard], bool]:
    page = create_selector(
        html,
        url=url,
        adaptive=adaptive,
        storage_file=adaptive_store,
    )
    cards = _first_non_empty_scrapling(page, CARD_SELECTORS, attempts, "job_cards")
    recovered = False
    if not cards and adaptive:
        cards = page.css(
            CARD_SELECTORS[0],
            identifier="boss.job_cards",
            adaptive=True,
            percentage=adaptive_percentage,
        )
        attempts.append(
            SelectorAttempt(
                "scrapling",
                CARD_SELECTORS[0],
                len(cards),
                "job_cards",
                adaptive=True,
            )
        )
        recovered = bool(cards)
    elif cards and adaptive:
        page.css(
            CARD_SELECTORS[0],
            identifier="boss.job_cards",
            auto_save=True,
        )
    jobs: list[ExtractedJobCard] = []
    seen: set[str] = set()
    for card in cards:
        title_el = _first_scrapling(card, TITLE_SELECTORS, attempts, "title")
        title = _text(title_el)
        if not title:
            continue
        link_el = _first_scrapling(card, LINK_SELECTORS, attempts, "link")
        job_url = _normalize_url(_attr(link_el, "href"))
        job_id = _job_id_from_url(job_url) or _attr(card, "data-job-id")
        job = ExtractedJobCard(
            job_id=job_id,
            title=title,
            company=_text(_first_scrapling(card, COMPANY_SELECTORS, attempts, "company")),
            salary=_normalize_salary(_text(_first_scrapling(card, SALARY_SELECTORS, attempts, "salary"))),
            location=_text(_first_scrapling(card, LOCATION_SELECTORS, attempts, "location")),
            tags=_unique_texts(_all_scrapling(card, TAG_SELECTORS, attempts, "tags")),
            url=job_url,
        )
        key = job.url or f"{job.title}|{job.company}|{job.salary}"
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)
    return jobs, recovered


def _parse_with_bs4(html: str, attempts: list[SelectorAttempt] | None = None) -> list[ExtractedJobCard]:
    soup = BeautifulSoup(html or "", "html.parser")
    cards = _first_non_empty_bs4(soup, CARD_SELECTORS, attempts, "job_cards")
    jobs: list[ExtractedJobCard] = []
    seen: set[str] = set()
    for card in cards:
        title_el = _first_bs4(card, TITLE_SELECTORS, attempts, "title")
        title = _text_bs4(title_el)
        if not title:
            continue
        link_el = _first_bs4(card, LINK_SELECTORS, attempts, "link")
        job_url = _normalize_url(_attr_bs4(link_el, "href"))
        job_id = _job_id_from_url(job_url) or _attr_bs4(card, "data-job-id")
        job = ExtractedJobCard(
            job_id=job_id,
            title=title,
            company=_text_bs4(_first_bs4(card, COMPANY_SELECTORS, attempts, "company")),
            salary=_normalize_salary(_text_bs4(_first_bs4(card, SALARY_SELECTORS, attempts, "salary"))),
            location=_text_bs4(_first_bs4(card, LOCATION_SELECTORS, attempts, "location")),
            tags=_unique_texts(_all_bs4(card, TAG_SELECTORS, attempts, "tags")),
            url=job_url,
        )
        key = job.url or f"{job.title}|{job.company}|{job.salary}"
        if key in seen:
            continue
        seen.add(key)
        jobs.append(job)
    return jobs


def _parse_job_detail_bs4(html: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    return {
        "title": _text_bs4(_first_bs4(soup, [".job-detail-header .name", "[class*='job-name']", "[class*='name']"])),
        "salary": _text_bs4(_first_bs4(soup, [".job-detail-header .salary", "[class*='salary']"])),
        "description": _text_bs4(_first_bs4(soup, [".job-sec-text", ".detail-content", "[class*='job-detail']"])),
        "info_tags": _unique_texts(_all_bs4(soup, [".job-info .tag-list li", "[class*='info-tag'] li"])),
    }


def _result(
    jobs: list[ExtractedJobCard],
    classification: PageClassification,
    extractor: str,
    attempts: list[SelectorAttempt],
    warnings: list[str],
    fallback_used: bool,
    *,
    adaptive_enabled: bool = False,
    adaptive_recovered: bool = False,
) -> PageExtractionResult:
    return PageExtractionResult(
        jobs=jobs,
        classification=classification,
        diagnostics=ExtractionDiagnostics(
            extractor=extractor,
            page_state=classification.state,
            scrapling_available=scrapling_available(),
            fallback_used=fallback_used,
            selector_attempts=attempts,
            item_count=len(jobs),
            warnings=warnings,
            adaptive_enabled=adaptive_enabled,
            adaptive_recovered=adaptive_recovered,
        ),
    )


def _normal_classification(current: PageClassification, count: int) -> PageClassification:
    return PageClassification(
        state="normal",
        reason=current.reason or "Job cards were extracted.",
        signals={**current.signals, "job_count": count},
    )


def _first_non_empty_scrapling(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt],
    purpose: str,
) -> list[Any]:
    for selector in selectors:
        matches = list(root.css(selector) or [])
        attempts.append(SelectorAttempt("scrapling", selector, len(matches), purpose))
        if matches:
            return matches
    return []


def _first_scrapling(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt] | None = None,
    purpose: str = "",
) -> Any:
    matches = _first_non_empty_scrapling(
        root,
        selectors,
        attempts if attempts is not None else [],
        purpose,
    )
    return matches[0] if matches else None


def _all_scrapling(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt] | None = None,
    purpose: str = "",
) -> list[Any]:
    found: list[Any] = []
    for selector in selectors:
        matches = list(root.css(selector) or [])
        if attempts is not None:
            attempts.append(SelectorAttempt("scrapling", selector, len(matches), purpose))
        found.extend(matches)
    return found


def _first_non_empty_bs4(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt] | None,
    purpose: str,
) -> list[Any]:
    for selector in selectors:
        matches = list(root.select(selector))
        if attempts is not None:
            attempts.append(SelectorAttempt("beautifulsoup", selector, len(matches), purpose))
        if matches:
            return matches
    return []


def _first_bs4(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt] | None = None,
    purpose: str = "",
) -> Any:
    matches = _first_non_empty_bs4(root, selectors, attempts, purpose)
    return matches[0] if matches else None


def _all_bs4(
    root: Any,
    selectors: Iterable[str],
    attempts: list[SelectorAttempt] | None = None,
    purpose: str = "",
) -> list[Any]:
    found: list[Any] = []
    for selector in selectors:
        matches = list(root.select(selector))
        if attempts is not None:
            attempts.append(SelectorAttempt("beautifulsoup", selector, len(matches), purpose))
        found.extend(matches)
    return found


def _count_any_bs4(root: Any, selectors: Iterable[str]) -> int:
    seen: set[int] = set()
    for selector in selectors:
        for match in root.select(selector):
            seen.add(id(match))
    return len(seen)


def _text(el: Any) -> str:
    if el is None:
        return ""
    if hasattr(el, "__iter__") and not isinstance(el, str):
        el = next(iter(el), None)
    if el is None:
        return ""
    return _compact_text(getattr(el, "text", "") or "")


def _attr(el: Any, name: str) -> str:
    if el is None:
        return ""
    if hasattr(el, "__iter__") and not isinstance(el, str):
        el = next(iter(el), None)
    if el is None:
        return ""
    return (getattr(el, "attrib", None) or {}).get(name, "")


def _text_bs4(el: Any) -> str:
    if el is None:
        return ""
    return _compact_text(el.get_text(" "))


def _attr_bs4(el: Any, name: str) -> str:
    if el is None:
        return ""
    return el.get(name, "") or ""


def _unique_texts(elements: Iterable[Any]) -> list[str]:
    values: list[str] = []
    for element in elements:
        text = _text(element) if not hasattr(element, "get_text") else _text_bs4(element)
        if text and text not in values:
            values.append(text)
    return values


def _normalize_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BOSS_ORIGIN + href
    return href


def _job_id_from_url(url: str) -> str:
    if not url or "/job_detail/" not in url:
        return ""
    return url.rstrip("/").split("/")[-1].split("?")[0]


def _normalize_salary(value: str) -> str:
    return "".join("▯" if 0xE000 <= ord(ch) <= 0xF8FF else ch for ch in value)


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _has_any(text: str, needles: Iterable[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)
