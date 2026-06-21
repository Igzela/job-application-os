"""Auto-reply module for BOSS Zhipin recruiter messages.

Polls the BOSS Zhipin chat page for unread messages, generates
context-aware replies using the LLM, and sends them back.
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from .browser import get_browser
from .llm.provider import get_llm_adapter
from .llm.job_analyzer import generate_reply
from .automation_policy import DailyRateLimiter, is_business_hours
from .boss_adapter import human_delay as _human_delay
from .runtime_state import load_json_state, save_json_state


# BOSS Zhipin chat selectors
CHAT_LIST_SELECTORS = [
    '.chat-item',
    '[class*="chat-list"] li',
    '.session-list .session-item',
    '[class*="session-item"]',
]
UNREAD_SELECTORS = [
    '.unread-dot',
    '.badge',
    '[class*="unread"]',
    '[class*="badge"]',
]
MSG_CONTENT_SELECTORS = [
    '.message-content .text',
    '.chat-message .content',
    '[class*="msg-content"]',
    '[class*="message-text"]',
]
REPLY_TEXTAREA_SELECTORS = [
    '.chat-editor textarea',
    '[class*="chat"] textarea',
    'textarea[placeholder*="输入"]',
    '#chat-input',
]
SEND_BUTTON_SELECTORS = [
    'button:has-text("发送")',
    '.chat-editor button[class*="send"]',
    '[class*="send-btn"]',
]


def poll_messages(page):
    """Read BOSS Zhipin chat list, find chats with unread messages."""
    if "chat" not in page.url:
        page.goto(
            "https://www.zhipin.com/web/geek/chat",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        time.sleep(3)

    chats = []
    for selector in CHAT_LIST_SELECTORS:
        try:
            items = page.locator(selector).all()
            if not items:
                continue
            for item in items:
                try:
                    has_unread = False
                    for unread_sel in UNREAD_SELECTORS:
                        try:
                            unread = item.locator(unread_sel).first
                            if unread.is_visible(timeout=500):
                                has_unread = True
                                break
                        except Exception:
                            continue
                    if not has_unread:
                        continue
                    text = item.inner_text()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    recruiter_name = lines[0] if lines else "未知"
                    company = lines[1] if len(lines) > 1 else ""
                    last_message = lines[-1] if len(lines) > 2 else ""
                    chats.append({
                        "chat_id": f"chat_{len(chats)}",
                        "element_index": len(chats),
                        "recruiter_name": recruiter_name,
                        "company": company,
                        "last_message": last_message,
                        "unread": True,
                    })
                except Exception:
                    continue
            if chats:
                break
        except Exception:
            continue
    return chats


def read_conversation(page, element_index=0):
    """Click on a chat and read the conversation history."""
    messages = []
    for selector in CHAT_LIST_SELECTORS:
        try:
            items = page.locator(selector).all()
            if element_index < len(items):
                items[element_index].click()
                _human_delay(2.0, 4.0)
                break
        except Exception:
            continue
    for selector in MSG_CONTENT_SELECTORS:
        try:
            msg_elements = page.locator(selector).all()
            if msg_elements:
                for msg in msg_elements:
                    try:
                        text = msg.inner_text().strip()
                        if text:
                            parent_class = msg.evaluate(
                                "el => el.parentElement?.className || ''"
                            )
                            role = (
                                "me"
                                if any(
                                    k in parent_class.lower()
                                    for k in ["self", "mine", "right", "send"]
                                )
                                else "recruiter"
                            )
                            messages.append({"role": role, "text": text})
                    except Exception:
                        continue
                if messages:
                    break
        except Exception:
            continue
    return messages


def send_reply(page, reply_text):
    """Fill and send a reply in the current chat."""
    for selector in REPLY_TEXTAREA_SELECTORS:
        try:
            textarea = page.locator(selector).first
            if textarea.is_visible(timeout=3000):
                textarea.click()
                textarea.fill(reply_text)
                for send_sel in SEND_BUTTON_SELECTORS:
                    try:
                        btn = page.locator(send_sel).first
                        if btn.is_visible(timeout=2000):
                            btn.click()
                            _human_delay()
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def _load_reply_state(state_dir):
    state_file = state_dir / "auto_reply_state.json"
    return load_json_state(
        state_file,
        {"replied": {}, "stats": {"total_replied": 0, "total_skipped": 0}},
    )


def _save_reply_state(state_dir, state):
    state_file = state_dir / "auto_reply_state.json"
    save_json_state(state_file, state)


def run_auto_reply_loop(
    state_dir,
    config=None,
    profile=None,
    interval=60,
    max_replies=20,
    dry_run=True,
    cdp_port=9222,
    headless=False,
):
    """Main auto-reply loop: poll messages, generate replies, send."""
    state_dir = Path(state_dir)
    if profile is None:
        from .profile_loader import load_profile

        profile = load_profile(state_dir)

    # Safety policy: outside operating hours, force dry-run.
    if not dry_run and not is_business_hours():
        print("⚠️ 当前非工作时间 (9:00-21:00)，自动切换为模拟运行模式")
        dry_run = True

    llm = get_llm_adapter(config)
    reply_state = _load_reply_state(state_dir)
    rate_limiter = DailyRateLimiter(
        max_replies=30,
        state_file=state_dir / ".daily_limits.json",
    )

    print(f"\n🤖 自动回复系统启动")
    print(f"   求职者: {profile.get('name', '未知')}")
    print(f"   检查间隔: {interval} 秒")
    print(f"   最大回复: {max_replies} 条")
    print(f"   模式: {'模拟运行' if dry_run else '真实回复'}")
    print(f"   今日已回复: {rate_limiter.replies}/{rate_limiter.max_replies} 条\n")

    print("🔍 连接浏览器...")
    try:
        result = get_browser(cdp_port=cdp_port, headless=headless)
        if isinstance(result, tuple):
            pw, browser, context, page = result
        else:
            browser = result
            context = (
                browser.contexts[0] if browser.contexts else browser.new_context()
            )
            page = context.new_page()
    except Exception as e:
        print(f"❌ 浏览器连接失败: {e}")
        return {"error": "browser_connect_failed"}

    replied_count = 0
    round_num = 0

    try:
        while replied_count < max_replies:
            # Pause live replies outside operating hours.
            if not dry_run and not is_business_hours():
                print(f"\n🌙 非工作时间，暂停自动回复 (9:00-21:00)")
                time.sleep(300)
                continue

            round_num += 1
            print(f"\n--- 第 {round_num} 轮检查 ---")
            page.goto(
                "https://www.zhipin.com/web/geek/chat",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            _human_delay(3.0, 6.0)
            unread_chats = poll_messages(page)
            print(f"   发现 {len(unread_chats)} 条未读消息")

            if not unread_chats:
                print(f"   ⏳ 等待 {interval} 秒后重新检查...")
                time.sleep(interval)
                continue

            for chat in unread_chats:
                if replied_count >= max_replies:
                    break
                # 每日限额检查
                if not dry_run and not rate_limiter.can_reply():
                    print(f"   ⚠️ 已达每日回复上限 ({rate_limiter.max_replies})")
                    break
                chat_key = f"{chat['recruiter_name']}_{chat['company']}"
                if chat_key in reply_state.get("replied", {}):
                    last = reply_state["replied"][chat_key]
                    last_time = datetime.fromisoformat(
                        last.get("timestamp", "2000-01-01")
                    )
                    if (datetime.now(timezone.utc) - last_time).seconds < 3600:
                        print(
                            f"   ⏭️ 跳过 {chat['recruiter_name']} (最近已回复)"
                        )
                        reply_state["stats"]["total_skipped"] = (
                            reply_state["stats"].get("total_skipped", 0) + 1
                        )
                        continue

                print(f"\n💬 处理: {chat['recruiter_name']} @ {chat['company']}")
                messages = read_conversation(page, chat.get("element_index", 0))
                print(f"   读取到 {len(messages)} 条消息")

                if not messages:
                    print("   ⚠️ 无法读取消息，跳过")
                    continue

                last_recruiter_msg = ""
                for msg in reversed(messages):
                    if msg["role"] == "recruiter":
                        last_recruiter_msg = msg["text"]
                        break

                if not last_recruiter_msg:
                    print("   ⚠️ 未找到招聘者消息，跳过")
                    continue

                print(f"   🤖 生成回复...")
                job_context = {
                    "company": chat["company"],
                    "recruiter": chat["recruiter_name"],
                }
                conversation_text = "\n".join(
                    f"{'招聘者' if m['role']=='recruiter' else '我'}: {m['text']}"
                    for m in messages[-10:]
                )
                reply = generate_reply(
                    llm, last_recruiter_msg, job_context, profile, conversation_text
                )
                print(f"   回复内容: {reply[:80]}...")

                if dry_run:
                    print(f"   ✅ [模拟] 回复已生成")
                else:
                    print(f"   📤 发送中...")
                    sent = send_reply(page, reply)
                    if sent:
                        print(f"   ✅ 回复成功")
                    else:
                        print(f"   ❌ 回复失败")
                        continue

                replied_count += 1
                reply_state["replied"][chat_key] = {
                    "last_reply": reply[:200],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "recruiter": chat["recruiter_name"],
                    "company": chat["company"],
                }
                reply_state["stats"]["total_replied"] = (
                    reply_state["stats"].get("total_replied", 0) + 1
                )
                _save_reply_state(state_dir, reply_state)
                if not dry_run:
                    rate_limiter.record_reply()
                _human_delay(5.0, 15.0)

            print(f"\n⏳ 等待 {interval} 秒后重新检查...")
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    finally:
        try:
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass

    summary = {
        "total_replied": replied_count,
        "rounds": round_num,
        "state": reply_state["stats"],
    }
    print(f"\n📊 自动回复汇总")
    print(f"   总回复: {replied_count} 条")
    print(f"   检查轮次: {round_num}")
    _save_reply_state(state_dir, reply_state)
    return summary
