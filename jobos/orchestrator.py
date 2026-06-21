import json
import time
import dataclasses
from datetime import datetime, timezone
from pathlib import Path

from .llm.provider import get_llm_adapter
from .llm.job_analyzer import analyze_match, generate_greeting, check_scam
from .profile_loader import load_profile, load_evidence_bank
from .boss_parser import parse_job_list
from .automation_policy import DailyRateLimiter, is_business_hours
from .config import load_config
from .boss_adapter import human_delay, submit_boss_application
from .live_pipeline import (
    build_search_keywords,
    extract_detail_from_html,
    is_duplicate_job,
    load_contact_state,
    merge_detail_page_fields,
    record_contacted_job,
    rewrite_greeting_once,
    validate_greeting,
)
from .run_ledger import RunLedger


def _job_to_dict(job) -> dict:
    """将BossJob dataclass或dict统一转为dict"""
    if isinstance(job, dict):
        return job
    if dataclasses.is_dataclass(job) and not isinstance(job, type):
        return {k: v for k, v in dataclasses.asdict(job).items() if v is not None}
    return dict(job)


def run_full_pipeline(
    state_dir: str | Path,
    cdp_port: int = 9222,
    max_jobs: int = 10,
    dry_run: bool = False,
    config: dict | None = None,
    search_keyword: str = "",
    headless: bool = False,
) -> dict:
    """全流程自动化求职

    Returns:
        投递结果汇总
    """
    state_dir = Path(state_dir)

    # 加载profile
    profile = load_profile(state_dir)
    if not profile.get("name"):
        print("❌ 未找到求职档案。请先运行 `job init` 完成信息收集。")
        return {"error": "no_profile"}

    # 加载evidence
    evidence = load_evidence_bank(state_dir)

    # 获取LLM
    llm = get_llm_adapter(config)
    app_config = load_config()
    min_score_to_apply = int(app_config.get("scoring", {}).get("min_score_to_apply", 60))

    # Safety policy: live actions only during configured operating hours.
    if not dry_run and not is_business_hours():
        print("⚠️ 当前非工作时间 (8:00-22:00)，仅支持 dry-run 模式")
        dry_run = True

    run_id = datetime.now(timezone.utc).strftime("live-%Y%m%d-%H%M%S-%f")
    ledger = RunLedger.create(
        state_dir,
        mode="dry_run" if dry_run else "live",
        run_id=run_id,
        plan={
            "requested_max_jobs": max_jobs,
            "search_keyword": search_keyword,
            "stages": ["search", "analyze", "validate", "submit"],
        },
    )
    ledger.append_event({"event": "run_started", "stage": "search"})

    def finish(summary: dict) -> dict:
        for result in summary.get("results", []):
            status = result.get("status", "unknown")
            job = result.get("job") or {}
            event = (
                "stage_succeeded"
                if status in {"submitted", "dry_run", "already_contacted"}
                else "job_skipped"
                if status.startswith("skipped") or status in {
                    "low_match",
                    "scam_rejected",
                    "high_risk",
                    "greeting_invalid",
                    "daily_limit",
                }
                else "stage_failed"
            )
            ledger.append_event(
                {
                    "event": event,
                    "stage": "submit",
                    "job_id": job.get("job_id") or _job_id_for_artifacts(job),
                    "status": status,
                    "error": result.get("error"),
                    "page_state": result.get("page_state"),
                    "extractor": result.get("extractor"),
                    "attempt_path": result.get("attempt_path"),
                }
            )
        summary = {**summary, "run_dir": str(ledger.run_dir)}
        ledger.write_summary(summary)
        return summary

    # 每日限额检查
    rate_limiter = DailyRateLimiter(
        max_submissions=20,
        state_file=state_dir / ".daily_limits.json",
    )

    print(f"\n🚀 求职系统启动")
    print(f"   求职者: {profile.get('name', '未知')}")
    print(f"   目标: {search_keyword or '自动搜索'}")
    print(f"   模式: {'模拟运行' if dry_run else '真实投递'}")
    print(f"   最大投递: {max_jobs} 个")
    print(f"   投递阈值: {min_score_to_apply}/100")
    print(f"   今日已投: {rate_limiter.submissions}/{rate_limiter.max_submissions} 个\n")

    # Step 1: 连接浏览器并搜索
    print("🔍 Step 1: 连接浏览器...")
    try:
        page = _connect_browser(cdp_port, headless)
    except Exception as e:
        print(f"❌ 浏览器连接失败: {e}")
        print("   请确保Chrome已启动并开启CDP端口")
        ledger.append_event(
            {
                "event": "stage_failed",
                "stage": "browser_connect",
                "error_class": "browser_connect_failed",
                "error": str(e),
            }
        )
        return finish({"error": "browser_connect_failed", "results": []})

    # Step 2: 搜索职位
    print("🔍 Step 2: 搜索职位...")
    search_config = app_config.get("search", {})
    keywords = build_search_keywords(search_keyword or profile.get("target_role", ""), search_config)
    max_per_keyword = int(search_config.get("max_candidates_per_keyword", search_config.get("max_results", 20)))
    max_total_candidates = int(search_config.get("max_total_candidates", max_per_keyword * max(1, len(keywords))))
    contact_state = load_contact_state(state_dir)

    # Step 3: 逐个分析和投递
    results = []
    submitted = 0
    analyzed = 0
    total_found = 0
    searched_keywords: list[str] = []

    for keyword in keywords:
        if submitted >= max_jobs or analyzed >= max_total_candidates:
            break
        if not dry_run and not rate_limiter.can_submit():
            results.append({"status": "daily_limit", "keyword": keyword})
            break

        searched_keywords.append(keyword)
        jobs = _search_jobs(page, keyword)
        total_found += len(jobs)
        if not jobs:
            print(f"   未找到职位: {keyword}")
            continue
        print(f"   关键词 {keyword}: 找到 {len(jobs)} 个职位")

        for i, job in enumerate(jobs[:max_per_keyword]):
            if submitted >= max_jobs:
                print(f"   ✅ 已达到本次投递上限 ({max_jobs})")
                break
            if analyzed >= max_total_candidates:
                print(f"   ⚠️ 已达到候选预算 ({max_total_candidates})")
                break

            job_dict = _job_to_dict(job)
            job_dict["keyword"] = keyword
            job_dict["source"] = job_dict.get("source") or "boss_zhipin"
            analyzed += 1
            print(f"📋 [{analyzed}/{max_total_candidates}] {job_dict.get('title', '未知')} - {job_dict.get('company', '未知')}")

            duplicate = is_duplicate_job(job_dict, contact_state)
            if duplicate.duplicate:
                print(f"   ⏭️ 跳过重复职位: {duplicate.reason}")
                results.append({
                    "job": job_dict,
                    "status": "skipped_duplicate",
                    "skip_reason": duplicate.reason,
                    "matched_contact": duplicate.matched,
                    "keyword": keyword,
                })
                continue

            # 3a: 详情页提取，先于反诈/评分/招呼语
            print("   📄 详情页提取...")
            job_dict = _extract_detail_for_candidate(page, job_dict, keyword, app_config)
            if job_dict.get("detail_extraction_failed"):
                print(f"   ⚠️ 详情页提取失败，跳过: {job_dict.get('detail_error', '')[:80]}")
                results.append({
                    "job": job_dict,
                    "status": "detail_extraction_failed",
                    "error": job_dict.get("detail_error", ""),
                    "page_state": job_dict.get("page_state"),
                    "extractor": job_dict.get("extractor"),
                    "keyword": keyword,
                })
                continue

            if job_dict.get("communication_state") in ("already_contacted", "message_sent"):
                print(f"   ⏭️ 已沟通过: {job_dict.get('communication_state')}")
                contact_state = record_contacted_job(state_dir, job_dict, status=job_dict["communication_state"])
                results.append({
                    "job": job_dict,
                    "status": "already_contacted",
                    "skip_reason": job_dict.get("communication_state"),
                    "page_state": job_dict.get("page_state"),
                    "extractor": job_dict.get("extractor"),
                    "keyword": keyword,
                })
                continue

            # 3b: 反诈检查
            print("   🔒 反诈检查...")
            try:
                scam_result = check_scam(llm, json.dumps(job_dict, ensure_ascii=False))
            except Exception as e:
                print(f"   ⚠️ 反诈检查失败，跳过该职位: {e}")
                results.append({"job": job_dict, "status": "scam_check_error", "error": str(e), "keyword": keyword})
                continue
            if scam_result.get("is_scam"):
                print(f"   ❌ 拒绝: {scam_result.get('reasoning', '诈骗风险')}")
                results.append({"job": job_dict, "status": "scam_rejected", "reason": scam_result, "keyword": keyword})
                continue
            if scam_result.get("risk_level") == "high":
                print(f"   ⚠️ 高风险: {scam_result.get('reasoning', '')[:50]}...")
                results.append({"job": job_dict, "status": "high_risk", "reason": scam_result, "keyword": keyword})
                continue

            # 3c: 匹配度分析
            print("   📊 匹配度分析...")
            try:
                match_result = analyze_match(llm, job_dict, profile)
            except Exception as e:
                print(f"   ⚠️ 匹配度分析失败，跳过该职位: {e}")
                results.append({"job": job_dict, "status": "match_error", "error": str(e), "keyword": keyword})
                continue
            score = match_result.get("total_score", 0)
            print(f"   得分: {score}/100 ({match_result.get('verdict', '未知')})")

            if score < min_score_to_apply:
                print(f"   ⏭️ 跳过: 匹配度不足")
                results.append({"job": job_dict, "status": "low_match", "score": score, "keyword": keyword})
                continue

            # 3d: 生成并校验招呼语
            print("   ✍️ 生成个性化招呼语...")
            evidence_text = _get_relevant_evidence(evidence, job_dict)
            try:
                greeting = generate_greeting(llm, job_dict, profile, evidence_text)
            except Exception as e:
                print(f"   ⚠️ 招呼语生成失败，跳过该职位: {e}")
                results.append({"job": job_dict, "status": "greeting_error", "score": score, "error": str(e), "keyword": keyword})
                continue
            validation = validate_greeting(greeting, job_dict, profile, evidence)
            if not validation.valid:
                try:
                    greeting = rewrite_greeting_once(llm, greeting, job_dict, profile, evidence)
                    validation = validate_greeting(greeting, job_dict, profile, evidence)
                except Exception as e:
                    validation = validation
                    print(f"   ⚠️ 招呼语重写失败: {e}")
                if not validation.valid:
                    print(f"   ⏭️ 招呼语安全校验失败: {','.join(validation.reasons)}")
                    results.append({
                        "job": job_dict,
                        "status": "greeting_invalid",
                        "score": score,
                        "skip_reason": "greeting_safety",
                        "greeting_validation": validation.__dict__,
                        "keyword": keyword,
                    })
                    continue
            print(f"   招呼语: {greeting[:60]}...")

            # 3e: 投递
            if dry_run:
                print(f"   ✅ [模拟] 投递成功")
                results.append({"job": job_dict, "status": "dry_run", "score": score, "greeting": greeting, "keyword": keyword})
                submitted += 1
            else:
                if not rate_limiter.can_submit():
                    print(f"   ⚠️ 已达每日投递上限 ({rate_limiter.max_submissions})")
                    results.append({"job": job_dict, "status": "daily_limit", "keyword": keyword})
                    break

                print("   📤 投递中...")
                submit_result = _submit_candidate(page, job_dict, greeting, state_dir)
                results.append({"job": job_dict, "score": score, "greeting": greeting, "keyword": keyword, **submit_result})
                if submit_result.get("status") == "submitted":
                    submitted += 1
                    rate_limiter.record_submission()
                    contact_state = record_contacted_job(state_dir, job_dict, status="submitted")
                else:
                    print(f"   ❌ 投递失败: {submit_result.get('status')}")

            # Apply deterministic pacing between live submissions.
            if not dry_run and submitted < max_jobs and i < len(jobs[:max_per_keyword]) - 1:
                wait = int(app_config.get("submit", {}).get("min_delay", 30))
                print(f"   ⏳ 等待 {wait} 秒...\n")
                time.sleep(wait)

    if total_found == 0:
        print("❌ 未找到职位")
        return finish(
            {
                "error": "no_jobs",
                "searched_keywords": searched_keywords,
                "results": results,
            }
        )

    # 汇总
    summary = {
        "total_found": total_found,
        "analyzed": analyzed,
        "submitted": submitted,
        "searched_keywords": searched_keywords,
        "candidate_budget": max_total_candidates,
        "min_score_to_apply": min_score_to_apply,
        "results": results,
    }

    print(f"\n📊 汇总")
    print(f"   找到: {summary['total_found']} 个职位")
    print(f"   分析: {summary['analyzed']} 个")
    print(f"   投递: {summary['submitted']} 个")

    summary = finish(summary)
    print(f"\n📁 结果已保存到: {summary['run_dir']}")
    return summary


def _connect_browser(cdp_port: int, headless: bool):
    from .browser import get_browser
    result = get_browser(cdp_port=cdp_port, headless=headless)

    # get_browser returns (playwright, browser, context, page) tuple
    if isinstance(result, tuple):
        pw, browser, context, page = result
    else:
        browser = result
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

    # 优先找到已有的BOSS页面（可能已登录）
    boss_pages = []
    for p in context.pages:
        try:
            if "zhipin.com" in p.url:
                boss_pages.append(p)
        except Exception:
            continue

    if boss_pages:
        # 优先选择有搜索结果的页面
        for p in boss_pages:
            if "query=" in p.url or "job" in p.url:
                print(f"   📄 找到已有搜索页面: {p.url[:60]}...")
                return p
        # 否则返回第一个BOSS页面
        print(f"   📄 找到已有BOSS页面: {boss_pages[0].url[:60]}...")
        return boss_pages[0]

    # 没有找到已有页面，打开新页面
    page = context.new_page()
    page.goto("https://www.zhipin.com/web/geek/job-recommend")
    human_delay(3.0, 6.0)
    return page


def _extract_detail_for_candidate(page, job_dict: dict, keyword: str, app_config: dict) -> dict:
    job_url = job_dict.get("url") or job_dict.get("link", "")
    if not job_url:
        detail = extract_detail_from_html("", url="", use_scrapling=app_config.get("extraction", {}).get("use_scrapling", True))
        return merge_detail_page_fields(job_dict, detail, keyword=keyword)
    try:
        page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        html = page.content()
        title_fn = getattr(page, "title", None)
        page_title = title_fn() if callable(title_fn) else ""
        detail = extract_detail_from_html(
            html,
            url=getattr(page, "url", job_url),
            title=page_title,
            use_scrapling=app_config.get("extraction", {}).get("use_scrapling", True),
        )
        return merge_detail_page_fields(job_dict, detail, keyword=keyword)
    except Exception as exc:
        detail = extract_detail_from_html("", url=job_url, use_scrapling=app_config.get("extraction", {}).get("use_scrapling", True))
        merged = merge_detail_page_fields(job_dict, detail, keyword=keyword)
        merged["detail_extraction_failed"] = True
        merged["detail_error"] = str(exc)
        return merged


def _submit_candidate(page, job_dict: dict, greeting: str, state_dir: Path) -> dict:
    job_id = job_dict.get("job_id") or _job_id_for_artifacts(job_dict)
    job_url = job_dict.get("url") or job_dict.get("link", "")
    result = submit_boss_application(
        page,
        job_id=job_id,
        job_url=job_url,
        company=job_dict.get("company", ""),
        greeting=greeting,
        state_dir=state_dir,
        dry_run=False,
        confirm=True,
        validated=True,
        navigate=False,
    )
    return result.to_pipeline_record()


def _job_id_for_artifacts(job_dict: dict) -> str:
    raw = job_dict.get("url") or job_dict.get("link") or f"{job_dict.get('company', '')}-{job_dict.get('title', '')}"
    return "live-" + "".join(ch if ch.isalnum() else "-" for ch in str(raw))[:80].strip("-")


def _search_jobs(page, keyword: str) -> list[dict]:
    """在BOSS上搜索职位"""
    # 检查当前页面是否已经在搜索结果
    current_url = page.url
    if keyword and keyword not in current_url:
        url = f"https://www.zhipin.com/web/geek/job?query={keyword}&city=101280600"
        page.goto(url)
        human_delay(4.0, 8.0)
    elif "zhipin.com" in current_url:
        print(f"   📄 使用当前页面: {current_url[:80]}...")
        human_delay(2.0, 4.0)  # 短暂等待页面加载

    html = page.content()

    # 检查登录状态
    if "登录" in html[:2000] or "login" in html[:2000].lower():
        # 更精确的登录检测 - 检查是否有登录弹窗或按钮
        if "立即登录" in html or "扫码登录" in html or "账号密码登录" in html:
            print("   ⚠️ 页面需要登录，请先在浏览器中登录 BOSS 直聘")
            return []

    jobs = parse_job_list(html)
    if not jobs:
        print(f"   ⚠️ 未解析到职位，页面标题: {page.title()}")
        # 检查是否有职位列表容器
        if "job-list" in html or "search-job-result" in html:
            print("   💡 检测到职位列表容器，但解析失败")
        # 保存HTML用于调试
        debug_path = Path("/tmp/boss_debug.html")
        debug_path.write_text(html[:10000])
        print(f"   📄 调试HTML已保存到: {debug_path}")

    return jobs


def _get_relevant_evidence(evidence: list[dict], job: dict) -> str:
    """获取与职位相关的经历"""
    if not evidence:
        return ""

    job_text = json.dumps(job, ensure_ascii=False).lower()
    relevant = []

    for ev in evidence:
        ev_text = json.dumps(ev, ensure_ascii=False).lower()
        # 简单关键词匹配
        ev_skills = ev.get("skills", [])
        if any(s.lower() in job_text for s in ev_skills):
            relevant.append(ev)

    if not relevant:
        # 返回最近的3个经历
        return "\n".join(
            f"- {ev.get('title', '')}: {ev.get('content', '')[:200]}"
            for ev in evidence[:3]
        )

    return "\n".join(
        f"- {ev.get('title', '')}: {ev.get('content', '')[:200]}"
        for ev in relevant[:5]
    )
