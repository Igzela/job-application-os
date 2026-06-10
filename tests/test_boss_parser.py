"""Tests for BOSS Zhipin page parser."""

from __future__ import annotations

import pytest

from jobos.boss_parser import (
    BossJob,
    parse_job_list,
    parse_job_detail,
    parse_chat_page,
    _text,
    _attr,
)


SAMPLE_JOB_LIST_HTML = """
<html><body>
<div class="job-card-wrapper">
  <div class="job-name"><a href="/job_detail/abc123.html">Python开发工程师</a></div>
  <div class="company-name"><a href="/company/123">字节跳动</a></div>
  <div class="salary">25-50K</div>
  <div class="job-area">北京</div>
  <div class="tag-list"><li>Python</li><li>Django</li></div>
</div>
<div class="job-card-wrapper">
  <div class="job-name"><a href="/job_detail/def456.html">前端工程师</a></div>
  <div class="company-name"><a href="/company/456">阿里巴巴</a></div>
  <div class="salary">30-60K</div>
  <div class="job-area">杭州</div>
  <div class="tag-list"><li>React</li><li>TypeScript</li></div>
</div>
</body></html>
"""

SAMPLE_JOB_DETAIL_HTML = """
<html><body>
<div class="job-detail-header">
  <span class="name">Python开发工程师</span>
  <span class="salary">25-50K</span>
</div>
<div class="job-sec-text">负责后端服务开发，要求3年Python经验</div>
<div class="job-info"><div class="tag-list"><li>全职</li><li>3-5年</li><li>本科</li></div></div>
</body></html>
"""


class TestParseJobList:
    def test_parses_multiple_jobs(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert len(jobs) == 2

    def test_extracts_title(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert jobs[0].title == "Python开发工程师"
        assert jobs[1].title == "前端工程师"

    def test_extracts_company(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert jobs[0].company == "字节跳动"

    def test_extracts_salary(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert jobs[0].salary == "25-50K"

    def test_extracts_location(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert jobs[0].location == "北京"

    def test_extracts_tags(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert "Python" in jobs[0].tags
        assert "Django" in jobs[0].tags

    def test_extracts_url(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert "job_detail/abc123" in jobs[0].url

    def test_extracts_job_id(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert "abc123" in jobs[0].job_id

    def test_empty_html(self) -> None:
        jobs = parse_job_list("<html><body></body></html>")
        assert jobs == []

    def test_frozen_dataclass(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        with pytest.raises(AttributeError):
            jobs[0].title = "new"  # type: ignore[misc]


class TestParseJobDetail:
    def test_extracts_title(self) -> None:
        detail = parse_job_detail(SAMPLE_JOB_DETAIL_HTML)
        assert detail["title"] == "Python开发工程师"

    def test_extracts_salary(self) -> None:
        detail = parse_job_detail(SAMPLE_JOB_DETAIL_HTML)
        assert detail["salary"] == "25-50K"

    def test_extracts_description(self) -> None:
        detail = parse_job_detail(SAMPLE_JOB_DETAIL_HTML)
        assert "Python" in detail["description"]

    def test_extracts_info_tags(self) -> None:
        detail = parse_job_detail(SAMPLE_JOB_DETAIL_HTML)
        assert "全职" in detail["info_tags"]

    def test_empty_html(self) -> None:
        detail = parse_job_detail("<html></html>")
        assert detail["title"] == ""


class TestParseChatPage:
    def test_returns_dict(self) -> None:
        result = parse_chat_page("<html></html>")
        assert isinstance(result, dict)


class TestHelpers:
    def test_text_none(self) -> None:
        assert _text(None) == ""

    def test_text_list(self) -> None:
        class FakeEl:
            text = "hello"
        assert _text([FakeEl()]) == "hello"

    def test_attr_none(self) -> None:
        assert _attr(None, "href") == ""
