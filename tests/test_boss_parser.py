"""Tests for BOSS Zhipin page parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobos.boss_parser import (
    BossJob,
    classify_boss_page,
    extract_boss_job_list,
    parse_job_list,
    parse_job_detail,
    parse_chat_page,
    scrapling_available,
    _text,
    _attr,
)


SAMPLE_JOB_LIST_HTML = """
<html><body>
<li class="job-card-box">
  <div class="job-info">
    <div class="job-title clearfix">
      <a href="/job_detail/abc123.html" class="job-name">Python开发工程师</a>
      <span class="job-salary">25-50K</span>
    </div>
    <ul class="tag-list"><li>3-5年</li><li>本科</li></ul>
  </div>
  <div class="job-card-footer">
    <a class="boss-info"><span class="boss-name">字节跳动</span></a>
    <span class="company-location">北京</span>
  </div>
</li>
<li class="job-card-box">
  <div class="job-info">
    <div class="job-title clearfix">
      <a href="/job_detail/def456.html" class="job-name">前端工程师</a>
      <span class="job-salary">30-60K</span>
    </div>
    <ul class="tag-list"><li>1-3年</li><li>本科</li></ul>
  </div>
  <div class="job-card-footer">
    <a class="boss-info"><span class="boss-name">阿里巴巴</span></a>
    <span class="company-location">杭州</span>
  </div>
</li>
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


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


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
        assert "字节跳动" in jobs[0].company

    def test_extracts_salary(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert jobs[0].salary == "25-50K"

    def test_extracts_location(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert "北京" in jobs[0].location

    def test_extracts_tags(self) -> None:
        jobs = parse_job_list(SAMPLE_JOB_LIST_HTML)
        assert "3-5年" in jobs[0].tags
        assert "本科" in jobs[0].tags

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


class TestBossExtraction:
    def test_fallback_replays_normal_fixture(self) -> None:
        result = extract_boss_job_list(
            _fixture("boss_job_list_normal.html"),
            use_scrapling=False,
        )

        assert result.classification.state == "normal"
        assert result.diagnostics.extractor == "beautifulsoup"
        assert result.jobs[0].title == "Python Developer"
        assert result.jobs[0].company == "ByteDance"
        assert result.jobs[0].url.endswith("/job_detail/normal123.html")

    def test_fallback_handles_mutated_dom_variant(self) -> None:
        result = extract_boss_job_list(
            _fixture("boss_job_list_mutated.html"),
            use_scrapling=False,
        )

        assert result.classification.state == "normal"
        assert result.jobs[0].title == "AI Platform Engineer"
        assert result.jobs[0].company == "Example AI"
        assert "LLM" in result.jobs[0].tags

    @pytest.mark.skipif(not scrapling_available(), reason="Scrapling is optional")
    def test_scrapling_matches_fallback_on_normal_fixture(self) -> None:
        html = _fixture("boss_job_list_normal.html")
        fallback = extract_boss_job_list(html, use_scrapling=False)
        scrapling = extract_boss_job_list(html, use_scrapling=True)

        assert scrapling.diagnostics.extractor == "scrapling"
        assert scrapling.diagnostics.selector_attempts
        assert [job.to_dict() for job in scrapling.jobs] == [
            job.to_dict() for job in fallback.jobs
        ]

    @pytest.mark.skipif(not scrapling_available(), reason="Scrapling is optional")
    def test_scrapling_handles_mutated_fixture(self) -> None:
        result = extract_boss_job_list(
            _fixture("boss_job_list_mutated.html"),
            use_scrapling=True,
        )

        assert result.classification.state == "normal"
        assert result.diagnostics.extractor == "scrapling"
        assert result.jobs[0].job_id == "mutated123.html"

    @pytest.mark.parametrize(
        ("fixture_name", "state"),
        [
            ("boss_login.html", "login_required"),
            ("boss_verification.html", "verification_required"),
            ("boss_access_limited.html", "access_limited"),
            ("boss_empty.html", "empty"),
            ("boss_page_shape_changed.html", "page_shape_changed"),
        ],
    )
    def test_classifies_recovery_states(self, fixture_name: str, state: str) -> None:
        classification = classify_boss_page(_fixture(fixture_name))

        assert classification.state == state
        assert classification.recovery


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
