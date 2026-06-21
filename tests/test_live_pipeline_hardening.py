"""Focused tests for live BOSS pipeline hardening helpers."""

from __future__ import annotations

import json
from pathlib import Path

from jobos.live_pipeline import (
    build_search_keywords,
    classify_boss_contact_state,
    classify_submit_success,
    extract_detail_from_html,
    is_duplicate_job,
    iter_keyword_candidates,
    merge_detail_page_fields,
    record_contacted_job,
    validate_greeting,
)


DETAIL_HTML = """
<html><body>
  <div class="job-detail-header">
    <span class="name">Python后端开发</span>
    <span class="salary">20-30K</span>
    <p class="location-address">深圳</p>
  </div>
  <div class="company-name">星河科技</div>
  <div class="boss-name">王女士</div>
  <div class="job-sec-text">
    岗位职责：负责 FastAPI 服务开发。
    任职要求：熟悉 Python、Django、PostgreSQL。
  </div>
  <button>继续沟通</button>
</body></html>
"""


def test_detail_page_extracts_and_merges_full_fields() -> None:
    candidate = {
        "title": "Python开发",
        "company": "",
        "salary": "",
        "link": "https://www.zhipin.com/web/geek/job_detail/detail123.html",
    }

    detail = extract_detail_from_html(
        DETAIL_HTML,
        url=candidate["link"],
        title="BOSS job detail",
        use_scrapling=False,
    )
    merged = merge_detail_page_fields(candidate, detail, keyword="Python后端")

    assert merged["title"] == "Python后端开发"
    assert merged["company"] == "星河科技"
    assert merged["salary"] == "20-30K"
    assert "FastAPI" in merged["description"]
    assert "Python" in merged["requirements"]
    assert merged["location"] == "深圳"
    assert merged["recruiter"] == "王女士"
    assert merged["communication_state"] == "already_contacted"
    assert merged["detail_extractor"] == "beautifulsoup"
    assert merged["page_state"] == "normal"
    assert merged["keyword"] == "Python后端"


def test_detail_page_failure_merges_diagnostics_without_aborting() -> None:
    candidate = {"title": "Python开发", "link": "https://example.test/job"}
    detail = extract_detail_from_html("", url=candidate["link"], use_scrapling=False)

    merged = merge_detail_page_fields(candidate, detail)

    assert merged["title"] == "Python开发"
    assert merged["detail_extraction_failed"] is True
    assert merged["detail_diagnostics"]["page_state"] == "empty"


def test_greeting_validator_blocks_wrong_identity_and_recruiter_claim() -> None:
    profile = {"name": "张嘉桓", "skills": {"programming_languages": [{"name": "Python"}]}}
    job = {"title": "Python后端", "company": "星河科技"}
    evidence = [{"title": "AI Agent使用经验", "content": "熟练使用Claude Code进行代码开发"}]

    result = validate_greeting("你好，我是小李，招聘顾问，帮你推荐岗位", job, profile, evidence)

    assert not result.valid
    assert "wrong_identity" in result.reasons
    assert "recruiter_claim" in result.reasons


def test_greeting_validator_allows_supported_short_message() -> None:
    profile = {"name": "张嘉桓", "skills": {"programming_languages": [{"name": "Python"}]}}
    job = {"title": "Python后端", "company": "星河科技"}
    evidence = [{"title": "AI Agent使用经验", "content": "使用Claude Code进行代码开发"}]

    result = validate_greeting(
        "你好，我是张嘉桓，关注Python后端方向。熟悉Python和AI工具链，希望交流这个岗位。",
        job,
        profile,
        evidence,
    )

    assert result.valid
    assert result.reasons == []


def test_duplicate_contact_state_skips_url_and_company_title(tmp_path: Path) -> None:
    contacted = record_contacted_job(
        tmp_path,
        {"job_id": "boss-1", "url": "https://zhipin.com/job/1", "company": "星河科技", "title": "Python后端"},
        status="submitted",
    )

    by_url = is_duplicate_job({"url": "https://zhipin.com/job/1"}, contacted)
    by_pair = is_duplicate_job({"company": "星河科技", "title": "Python后端"}, contacted)

    assert by_url.duplicate
    assert by_url.reason == "duplicate_url"
    assert by_pair.duplicate
    assert by_pair.reason == "duplicate_company_title"


def test_contact_state_classifies_already_contacted_boss_text() -> None:
    assert classify_boss_contact_state("继续沟通") == "already_contacted"
    assert classify_boss_contact_state("已发送") == "message_sent"


def test_submit_success_requires_strong_signal() -> None:
    ok = classify_submit_success("聊天记录：你好，我是张嘉桓", "你好，我是张嘉桓", "星河科技")
    sent = classify_submit_success("页面提示 已发送", "任意招呼语", "星河科技")
    failed = classify_submit_success("发送按钮仍可见", "你好", "星河科技")

    assert ok.success
    assert "message_echo" in ok.signals
    assert sent.success
    assert "sent_state" in sent.signals
    assert not failed.success


def test_search_keywords_and_candidate_budget_rotation() -> None:
    keywords = build_search_keywords(
        "Python后端",
        {"keywords": ["Python后端", "Django", "FastAPI"], "max_candidates_per_keyword": 2},
    )

    seen = list(iter_keyword_candidates(keywords, max_per_keyword=2, max_total=5))

    assert keywords == ["Python后端", "Django", "FastAPI"]
    assert seen == [
        ("Python后端", 0),
        ("Python后端", 1),
        ("Django", 0),
        ("Django", 1),
        ("FastAPI", 0),
    ]


def test_live_pipeline_max_jobs_counts_successful_submissions(tmp_path: Path, monkeypatch) -> None:
    from jobos import orchestrator

    class Page:
        url = ""

        def goto(self, url, **_kwargs):
            self.url = url

        def content(self):
            return DETAIL_HTML.replace("<button>继续沟通</button>", "<button>立即沟通</button>")

        def title(self):
            return "BOSS job detail"

        def screenshot(self, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("shot", encoding="utf-8")

    class Limiter:
        submissions = 0
        max_submissions = 20

        def __init__(self, **_kwargs):
            pass

        def can_submit(self):
            return True

        def record_submission(self):
            self.submissions += 1

    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "base.yaml").write_text("name: 张嘉桓\n", encoding="utf-8")

    searched: list[str] = []

    def search(_page, keyword):
        searched.append(keyword)
        return {
            "Python后端": [{"title": "Too weak", "company": "A", "link": "https://zhipin.com/job/low"}],
            "Django": [{"title": "Python后端", "company": "星河科技", "link": "https://zhipin.com/job/good"}],
        }.get(keyword, [])

    monkeypatch.setattr(orchestrator, "_connect_browser", lambda *_args, **_kwargs: Page())
    monkeypatch.setattr(orchestrator, "_search_jobs", search)
    monkeypatch.setattr(orchestrator, "load_profile", lambda _state_dir: {"name": "张嘉桓"})
    monkeypatch.setattr(orchestrator, "load_evidence_bank", lambda _state_dir: [])
    monkeypatch.setattr(orchestrator, "get_llm_adapter", lambda _config: object())
    monkeypatch.setattr(orchestrator, "is_business_hours", lambda: True)
    monkeypatch.setattr(orchestrator, "DailyRateLimiter", Limiter)
    monkeypatch.setattr(orchestrator, "check_scam", lambda *_args, **_kwargs: {"is_scam": False, "risk_level": "low"})
    monkeypatch.setattr(
        orchestrator,
        "analyze_match",
        lambda _llm, job, _profile: {"total_score": 50 if "low" in job.get("link", "") else 90, "verdict": "推荐"},
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_greeting",
        lambda *_args, **_kwargs: "你好，我是张嘉桓，关注Python后端方向。熟悉Python和AI工具链，希望交流这个岗位。",
    )
    monkeypatch.setattr(
        orchestrator,
        "load_config",
        lambda: {
            "search": {"keywords": ["Django"], "max_candidates_per_keyword": 5, "max_total_candidates": 5},
            "scoring": {"min_score_to_apply": 60},
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "_submit_candidate",
        lambda *_args, **_kwargs: {
            "status": "submitted",
            "submit_phase": "post_send",
            "success_signals": ["sent_state"],
            "screenshot_paths": {},
            "page_state": "normal",
            "extractor": "beautifulsoup",
            "recovery_signals": [],
        },
    )

    result = orchestrator.run_full_pipeline(tmp_path, max_jobs=1, dry_run=False, search_keyword="Python后端")

    assert result["submitted"] == 1
    assert result["analyzed"] == 2
    assert searched == ["Python后端", "Django"]
    run_dir = Path(result["run_dir"])
    assert (run_dir / "plan.json").exists()
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "summary.json").exists()
    assert not (tmp_path / "pipeline_results.json").exists()


def test_live_pipeline_skips_duplicate_before_apply(tmp_path: Path, monkeypatch) -> None:
    from jobos import orchestrator

    class Page:
        url = ""

        def goto(self, url, **_kwargs):
            self.url = url

        def content(self):
            return DETAIL_HTML

        def title(self):
            return "BOSS job detail"

        def screenshot(self, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("shot", encoding="utf-8")

    record_contacted_job(
        tmp_path,
        {"job_id": "dup-1", "url": "https://zhipin.com/job/dup", "company": "星河科技", "title": "Python后端"},
    )

    monkeypatch.setattr(orchestrator, "_connect_browser", lambda *_args, **_kwargs: Page())
    monkeypatch.setattr(
        orchestrator,
        "_search_jobs",
        lambda _page, _keyword: [{"job_id": "dup-1", "title": "Python后端", "company": "星河科技", "link": "https://zhipin.com/job/dup"}],
    )
    monkeypatch.setattr(orchestrator, "load_profile", lambda _state_dir: {"name": "张嘉桓"})
    monkeypatch.setattr(orchestrator, "load_evidence_bank", lambda _state_dir: [])
    monkeypatch.setattr(orchestrator, "get_llm_adapter", lambda _config: object())
    monkeypatch.setattr(orchestrator, "is_business_hours", lambda: True)
    monkeypatch.setattr(orchestrator, "load_config", lambda: {"search": {"keywords": []}, "scoring": {"min_score_to_apply": 60}})

    result = orchestrator.run_full_pipeline(tmp_path, max_jobs=1, dry_run=False, search_keyword="Python后端")

    assert result["submitted"] == 0
    assert result["results"][0]["status"] == "skipped_duplicate"
    assert result["results"][0]["skip_reason"] == "duplicate_job_id"


def test_live_submit_candidate_persists_shared_attempt_record(tmp_path: Path, monkeypatch) -> None:
    from jobos import orchestrator

    class Page:
        url = "https://zhipin.com/job/live-1"

        def content(self):
            return "<html><body><button>立即沟通</button></body></html>"

        def title(self):
            return "BOSS job detail"

    monkeypatch.setattr("jobos.boss_adapter.click_chat_button", lambda _page: False)
    monkeypatch.setattr(
        "jobos.boss_adapter.take_screenshot",
        lambda _page, path: str(path),
    )

    result = orchestrator._submit_candidate(
        Page(),
        {"job_id": "live-1", "company": "星河科技", "title": "Python后端", "link": "https://zhipin.com/job/live-1"},
        "你好，我是张嘉桓。",
        tmp_path,
    )

    assert result["status"] == "no_chat_button"
    assert result["attempt_path"]
    attempt = json.loads(Path(result["attempt_path"]).read_text(encoding="utf-8"))
    assert attempt["schema_version"] == 1
    assert attempt["job_id"] == "live-1"
    assert attempt["platform"] == "boss"
    assert attempt["mode"] == "live"
    assert attempt["status"] == "failed"
    assert attempt["error_class"] == "no_chat_button"
    assert attempt["result"]["submit_phase"] == "chat_button"
    assert attempt["page_diagnostics"]
