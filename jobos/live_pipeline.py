"""Hardening helpers for the live BOSS application pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup

from .boss_parser import classify_boss_page, parse_job_detail, scrapling_available


CONTACT_STATE_FILE = ".job-contact-state.json"
DEFAULT_GREETING_MAX_LENGTH = 100


@dataclass(frozen=True)
class DetailExtraction:
    fields: dict[str, Any]
    extractor: str
    page_state: str
    diagnostics: dict[str, Any]
    error: str = ""


@dataclass(frozen=True)
class GreetingValidation:
    valid: bool
    reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DuplicateCheck:
    duplicate: bool
    reason: str = ""
    matched: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubmitSuccess:
    success: bool
    signals: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def extract_detail_from_html(
    html: str,
    *,
    url: str = "",
    title: str = "",
    use_scrapling: bool | None = None,
) -> DetailExtraction:
    """Extract BOSS detail-page fields with parser diagnostics."""
    classification = classify_boss_page(html, url=url, title=title)
    extractor = "scrapling" if (use_scrapling is not False and scrapling_available()) else "beautifulsoup"
    diagnostics: dict[str, Any] = {
        "extractor": extractor,
        "page_state": classification.state,
        "classification": classification.to_dict(),
    }

    if not html or classification.state != "normal":
        return DetailExtraction(
            fields={},
            extractor=extractor,
            page_state=classification.state,
            diagnostics=diagnostics,
            error=classification.reason or "detail_page_not_extractable",
        )

    try:
        parsed = parse_job_detail(html)
        fields = _enrich_detail_fields(html, parsed)
    except Exception as exc:
        diagnostics["error"] = str(exc)
        return DetailExtraction(
            fields={},
            extractor=extractor,
            page_state=classification.state,
            diagnostics=diagnostics,
            error=str(exc),
        )

    if not any(fields.get(key) for key in ("description", "requirements", "title")):
        return DetailExtraction(
            fields={},
            extractor=extractor,
            page_state=classification.state,
            diagnostics=diagnostics,
            error="no_detail_fields_extracted",
        )
    diagnostics["field_count"] = sum(1 for value in fields.values() if value)
    return DetailExtraction(fields=fields, extractor=extractor, page_state=classification.state, diagnostics=diagnostics)


def merge_detail_page_fields(
    candidate: dict[str, Any],
    detail: DetailExtraction,
    *,
    keyword: str = "",
    source: str = "boss_zhipin",
) -> dict[str, Any]:
    """Merge detail-page data over search-card data without dropping diagnostics."""
    merged = dict(candidate)
    for key, value in detail.fields.items():
        if value not in ("", None, [], {}):
            merged[key] = value
    merged["detail_extractor"] = detail.extractor
    merged["extractor"] = detail.extractor
    merged["page_state"] = detail.page_state
    merged["detail_diagnostics"] = detail.diagnostics
    merged["source"] = merged.get("source") or source
    if keyword:
        merged["keyword"] = keyword
    if detail.error:
        merged["detail_extraction_failed"] = True
        merged["detail_error"] = detail.error
    return merged


def validate_greeting(
    greeting: str,
    job: dict[str, Any],
    profile: dict[str, Any],
    evidence: Iterable[dict[str, Any]] | str | None = None,
    *,
    max_length: int = DEFAULT_GREETING_MAX_LENGTH,
) -> GreetingValidation:
    """Block risky BOSS greeting text before send."""
    text = _compact(greeting)
    allowed = _allowed_fact_text(job, profile, evidence)
    reasons: list[str] = []

    if not text:
        reasons.append("empty")
    if len(text) > max_length:
        reasons.append("too_long")

    name = str(profile.get("name") or "").strip()
    for match in re.finditer(r"我是([^，,。！!\s]{1,12})", text):
        claimed = match.group(1).strip()
        if name and claimed and claimed not in name and name not in claimed:
            reasons.append("wrong_identity")

    if _has_any(text, ["招聘顾问", "猎头", "headhunter", "recruiter", "HR", "人事", "招聘专员"]):
        reasons.append("recruiter_claim")

    if _has_any(text, ["保证", "包过", "刷单", "返利", "加微信", "躺赚", "兼职日结", "急招", "群发"]):
        reasons.append("spammy_or_risky_wording")

    company = str(job.get("company") or "")
    for company_name in re.findall(r"(阿里|腾讯|字节|美团|华为|百度|小米|京东|网易|星河科技)", text):
        if company_name != company and company_name not in allowed:
            reasons.append("unrelated_company")
            break

    unsupported = _unsupported_project_claims(text, allowed)
    if unsupported:
        reasons.append("unsupported_claim")

    unique_reasons = list(dict.fromkeys(reasons))
    return GreetingValidation(
        valid=not unique_reasons,
        reasons=unique_reasons,
        diagnostics={"length": len(text), "unsupported_claims": unsupported},
    )


def rewrite_greeting_once(
    llm,
    greeting: str,
    job: dict[str, Any],
    profile: dict[str, Any],
    evidence: Iterable[dict[str, Any]] | str | None = None,
    *,
    max_length: int = DEFAULT_GREETING_MAX_LENGTH,
) -> str:
    """Ask the configured LLM for one constrained greeting rewrite."""
    evidence_text = _evidence_to_text(evidence)
    system = (
        "你是求职者本人写BOSS招呼语。只能使用用户档案和证据库事实。"
        "禁止自称HR、招聘顾问、猎头、人事。禁止编造项目、公司、经历。"
        f"输出中文，{max_length}字以内，只输出招呼语。"
    )
    message = {
        "role": "user",
        "content": (
            f"原招呼语：{greeting}\n"
            f"职位：{json.dumps(job, ensure_ascii=False)}\n"
            f"求职者：{json.dumps(profile, ensure_ascii=False)}\n"
            f"证据库：{evidence_text[:1200]}"
        ),
    }
    return str(llm.chat([message], system=system, temperature=0.2)).strip()


def classify_boss_contact_state(text_or_html: str) -> str:
    """Classify current BOSS communication state from visible text/HTML."""
    text = _visible_text(text_or_html)
    if _has_any(text, ["继续沟通", "已沟通", "聊过", "沟通过"]):
        return "already_contacted"
    if _has_any(text, ["已发送", "发送成功"]):
        return "message_sent"
    if _has_any(text, ["立即沟通", "打招呼", "开聊"]):
        return "not_contacted"
    return "unknown"


def load_contact_state(state_dir: str | Path) -> dict[str, Any]:
    path = Path(state_dir) / CONTACT_STATE_FILE
    if not path.exists():
        return {"jobs": {}, "urls": {}, "company_titles": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"jobs": {}, "urls": {}, "company_titles": {}}
    data.setdefault("jobs", {})
    data.setdefault("urls", {})
    data.setdefault("company_titles", {})
    return data


def save_contact_state(state_dir: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    path = Path(state_dir) / CONTACT_STATE_FILE
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return state


def record_contacted_job(
    state_dir: str | Path,
    job: dict[str, Any],
    *,
    status: str = "contacted",
) -> dict[str, Any]:
    state = load_contact_state(state_dir)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "job_id": job.get("job_id") or "",
        "url": _job_url(job),
        "company": job.get("company") or "",
        "title": job.get("title") or "",
        "status": status,
        "timestamp": now,
    }
    if record["job_id"]:
        state["jobs"][record["job_id"]] = record
    if record["url"]:
        state["urls"][record["url"]] = record
    pair = _company_title_key(record)
    if pair:
        state["company_titles"][pair] = record
    return save_contact_state(state_dir, state)


def is_duplicate_job(job: dict[str, Any], state: dict[str, Any], *, match_company_title: bool = True) -> DuplicateCheck:
    job_id = str(job.get("job_id") or "")
    url = _job_url(job)
    if job_id and job_id in state.get("jobs", {}):
        return DuplicateCheck(True, "duplicate_job_id", state["jobs"][job_id])
    if url and url in state.get("urls", {}):
        return DuplicateCheck(True, "duplicate_url", state["urls"][url])
    if match_company_title:
        pair = _company_title_key(job)
        if pair and pair in state.get("company_titles", {}):
            return DuplicateCheck(True, "duplicate_company_title", state["company_titles"][pair])
    return DuplicateCheck(False)


def classify_submit_success(
    text_or_html: str,
    greeting: str,
    expected_company: str = "",
) -> SubmitSuccess:
    text = _visible_text(text_or_html)
    signals: list[str] = []
    contact_state = classify_boss_contact_state(text)
    if contact_state in ("message_sent", "already_contacted"):
        signals.append("sent_state" if contact_state == "message_sent" else "already_contacted_state")
    if greeting and _compact(greeting) in _compact(text):
        signals.append("message_echo")
    if expected_company and expected_company in text and _has_any(text, ["沟通", "聊天", "已发送"]):
        signals.append("expected_company_chat")
    signals = list(dict.fromkeys(signals))
    return SubmitSuccess(success=bool(signals), signals=signals, diagnostics={"contact_state": contact_state})


def build_search_keywords(primary_keyword: str, search_config: dict[str, Any]) -> list[str]:
    configured = search_config.get("keywords") or []
    keywords = [primary_keyword, *configured] if primary_keyword else list(configured)
    if not keywords:
        keywords = ["Python后端", "Python开发", "后端开发", "Django", "FastAPI", "AI应用开发"]
    result: list[str] = []
    for keyword in keywords:
        keyword = str(keyword).strip()
        if keyword and keyword not in result:
            result.append(keyword)
    return result


def iter_keyword_candidates(keywords: Iterable[str], *, max_per_keyword: int, max_total: int):
    seen = 0
    for keyword in keywords:
        for index in range(max_per_keyword):
            if seen >= max_total:
                return
            seen += 1
            yield keyword, index


def _enrich_detail_fields(html: str, parsed: dict[str, Any]) -> dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    description = parsed.get("description") or _text(_first(soup, [".job-sec-text", ".detail-content", "[class*='job-detail']"]))
    fields = {
        "title": parsed.get("title") or _text(_first(soup, [".job-detail-header .name", "[class*='job-name']", ".name"])),
        "salary": parsed.get("salary") or _text(_first(soup, [".job-detail-header .salary", "[class*='salary']"])),
        "description": description,
        "requirements": _extract_requirements(description),
        "location": _text(_first(soup, [".location-address", ".job-address", ".job-area", "[class*='location']", "[class*='address']"])),
        "company": _text(_first(soup, [".company-name", "[class*='company-name']", "[class*='company'] a"])),
        "recruiter": _text(_first(soup, [".boss-name", ".recruiter-name", "[class*='boss-name']", "[class*='recruiter']"])),
        "contact_hints": _contact_hints(soup),
        "job_status": _job_status(soup.get_text(" ")),
        "communication_state": classify_boss_contact_state(soup.get_text(" ")),
    }
    if parsed.get("info_tags"):
        fields["info_tags"] = parsed["info_tags"]
    fields["full_jd"] = description
    return fields


def _first(soup, selectors: list[str]):
    for selector in selectors:
        found = soup.select_one(selector)
        if found:
            return found
    return None


def _text(node) -> str:
    return _compact(node.get_text(" ")) if node else ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _visible_text(text_or_html: str) -> str:
    text = str(text_or_html or "")
    if "<" in text and ">" in text:
        return _compact(BeautifulSoup(text, "html.parser").get_text(" "))
    return _compact(text)


def _has_any(text: str, needles: Iterable[str]) -> bool:
    lower = text.lower()
    return any(needle.lower() in lower for needle in needles)


def _extract_requirements(description: str) -> str:
    text = _compact(description)
    match = re.search(r"(任职要求|岗位要求|职位要求|要求)[:：]?(.*)", text)
    return _compact(match.group(2)) if match else ""


def _contact_hints(soup: BeautifulSoup) -> list[str]:
    text = soup.get_text(" ")
    hints = []
    for needle in ("微信", "电话", "邮箱", "沟通", "聊天", "继续沟通", "已发送"):
        if needle in text:
            hints.append(needle)
    return hints


def _job_status(text: str) -> str:
    if _has_any(text, ["停止招聘", "职位已关闭", "已下线"]):
        return "closed"
    if _has_any(text, ["继续沟通", "已发送", "立即沟通", "打招呼"]):
        return "open"
    return "unknown"


def _allowed_fact_text(
    job: dict[str, Any],
    profile: dict[str, Any],
    evidence: Iterable[dict[str, Any]] | str | None,
) -> str:
    return "\n".join(
        [
            json.dumps(job, ensure_ascii=False, default=str),
            json.dumps(profile, ensure_ascii=False, default=str),
            _evidence_to_text(evidence),
        ]
    )


def _evidence_to_text(evidence: Iterable[dict[str, Any]] | str | None) -> str:
    if not evidence:
        return ""
    if isinstance(evidence, str):
        return evidence
    return "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in evidence)


def _unsupported_project_claims(text: str, allowed_text: str) -> list[str]:
    claims: list[str] = []
    for match in re.finditer(r"(做过|负责过|参与过)([^。；;，,]{2,30}?项目)", text):
        claim = match.group(2)
        if claim not in allowed_text:
            claims.append(claim)
    return claims


def _job_url(job: dict[str, Any]) -> str:
    return str(job.get("url") or job.get("link") or "").strip()


def _company_title_key(job: dict[str, Any]) -> str:
    company = _compact(job.get("company") or "")
    title = _compact(job.get("title") or "")
    return f"{company}|{title}" if company and title else ""
