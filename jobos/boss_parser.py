"""BOSS Zhipin page parser using Scrapling's adaptive Selector.

Parses job listings, job details, and form elements from BOSS pages.
Uses adaptive element relocation so it survives minor page redesigns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from scrapling.parser import Selector
except ImportError:
    Selector = None


@dataclass(frozen=True)
class BossJob:
    job_id: str
    title: str
    company: str
    salary: str
    location: str
    tags: List[str] = field(default_factory=list)
    url: str = ""


def parse_job_list(html: str) -> List[BossJob]:
    """Parse job listing page HTML into structured job data.

    Uses Scrapling's Selector for adaptive CSS selection.
    Falls back to basic regex if Scrapling is not installed.
    """
    if Selector is None:
        return _fallback_parse(html)

    page = Selector(html)
    jobs: List[BossJob] = []

    cards = page.css("li.job-card-box") or page.css("[class*='job-card']")
    if not cards:
        cards = page.css(".job-card-wrapper") or page.css(".search-job-result li")

    for card in cards:
        title_el = card.css("a.job-name") or card.css(".job-name") or card.css("[class*='job-name']")
        company_el = card.css(".boss-name") or card.css(".company-name") or card.css("[class*='company']")
        salary_el = card.css(".job-salary") or card.css("[class*='salary']")
        location_el = card.css(".company-location") or card.css(".job-area") or card.css("[class*='area']")
        tag_els = card.css(".tag-list li") or card.css("[class*='tag'] li")
        link_el = card.css("a[href*='job_detail']") or card.css("a.job-name")

        title = _text(title_el)
        company = _text(company_el)
        if not title:
            continue

        job_url = ""
        if link_el:
            href = _attr(link_el, "href")
            if href:
                job_url = f"https://www.zhipin.com{href}" if href.startswith("/") else href

        job_id = ""
        if job_url and "/job_detail/" in job_url:
            job_id = job_url.rstrip("/").split("/")[-1].split("?")[0]

        jobs.append(BossJob(
            job_id=job_id,
            title=title,
            company=company,
            salary=_text(salary_el),
            location=_text(location_el),
            tags=[_text(t) for t in tag_els if _text(t)],
            url=job_url,
        ))

    return jobs


def parse_job_detail(html: str) -> dict:
    """Parse job detail page into structured data."""
    if Selector is None:
        return {}

    page = Selector(html)
    result = {}

    title_el = page.css(".job-detail-header .name") or page.css("[class*='job-name']")
    result["title"] = _text(title_el)

    salary_el = page.css(".job-detail-header .salary") or page.css("[class*='salary']")
    result["salary"] = _text(salary_el)

    desc_el = page.css(".job-sec-text") or page.css(".detail-content") or page.css("[class*='job-detail']")
    result["description"] = _text(desc_el)

    info_els = page.css(".job-info .tag-list li") or page.css("[class*='info-tag'] li")
    result["info_tags"] = [_text(t) for t in info_els if _text(t)]

    return result


def parse_chat_page(html: str) -> dict:
    """Parse BOSS chat page for form fields."""
    if Selector is None:
        return {}

    page = Selector(html)
    result = {}

    greeting_el = page.css(".chat-editor textarea") or page.css("[class*='editor'] textarea")
    result["greeting_input"] = _attr(greeting_el, "placeholder") or ""

    return result


def _text(el) -> str:
    if el is None:
        return ""
    if hasattr(el, "__iter__") and not isinstance(el, str):
        el = next(iter(el), None)
    if el is None:
        return ""
    return (el.text or "").strip()


def _attr(el, name: str) -> str:
    if el is None:
        return ""
    if hasattr(el, "__iter__") and not isinstance(el, str):
        el = next(iter(el), None)
    if el is None:
        return ""
    return (el.attrib or {}).get(name, "")


def _fallback_parse(html: str) -> List[BossJob]:
    """Minimal regex fallback when Scrapling is not installed."""
    import re
    jobs = []
    pattern = r'class="job-name[^"]*"[^>]*>.*?<a[^>]*href="(/job_detail/[^"]+)"[^>]*>(.*?)</a>'
    for match in re.finditer(pattern, html, re.DOTALL):
        url_path = match.group(1)
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        job_id = url_path.rstrip("/").split("/")[-1].split("?")[0]
        jobs.append(BossJob(
            job_id=job_id, title=title,
            company="", salary="", location="",
            url=f"https://www.zhipin.com{url_path}",
        ))
    return jobs
