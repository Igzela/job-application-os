import json
import yaml
from pathlib import Path

from .llm.provider import get_llm_adapter
from .llm.conversation import Conversation
from .llm.prompts import INTRO_SYSTEM, ONBOARDING_COLLECT


PROFILE_DIR = Path(__file__).parent.parent / "profile"


def run_onboarding(config: dict | None = None) -> dict:
    """交互式引导用户完成求职信息收集

    Returns:
        完整的用户画像字典
    """
    llm = get_llm_adapter(config)
    history_path = PROFILE_DIR / "conversation_history.json"
    conv = Conversation(llm, history_path)

    print("\n🤖 你好！我是你的求职AI助手。")
    print("我会通过聊天帮你完善求职信息，整个过程大概5-10分钟。")
    print("输入 'quit' 随时退出，下次可以继续。\n")

    rounds = 0
    max_rounds = 30

    while rounds < max_rounds:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n已保存进度，下次运行 `job init` 可以继续。")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("已保存进度，下次运行 `job init` 可以继续。")
            break

        if not user_input:
            continue

        reply = conv.chat(user_input, system=INTRO_SYSTEM)
        print(f"\nAI: {reply}\n")

        rounds += 1

        # 检查是否收集完成
        if "[ONBOARDING_COMPLETE]" in reply:
            profile = _extract_profile(llm, conv.messages)
            _save_profile(profile)
            print("✅ 信息收集完成！你的求职档案已保存。")
            print("运行 `job start` 开始全自动求职流程。")
            return profile

    # 超时或退出，尝试提取已有信息
    if conv.messages:
        profile = _extract_profile(llm, conv.messages)
        if any(v for v in profile.values() if v):
            _save_profile(profile)
            print("已保存当前进度。")
            return profile

    return {}


def _extract_profile(llm, messages: list[dict]) -> dict:
    """从对话历史中提取结构化信息"""
    # 把对话历史压缩成一段文本
    conversation_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in messages
        if m["role"] in ("user", "assistant")
    )

    result = llm.chat(
        [{"role": "user", "content": f"对话记录：\n{conversation_text}"}],
        system=ONBOARDING_COLLECT,
        temperature=0.2,
    )

    try:
        return json.loads(result)
    except json.JSONDecodeError:
        return {}


def _save_profile(profile: dict):
    """保存profile到YAML文件"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # base.yaml
    base = profile.get("base", {})
    if base:
        _merge_yaml(PROFILE_DIR / "base.yaml", base)

    # skills.yaml
    skills = profile.get("skills", {})
    if skills:
        _merge_yaml(PROFILE_DIR / "skills.yaml", {"skills": skills})

    # availability.yaml
    avail = profile.get("availability", {})
    if avail:
        _merge_yaml(PROFILE_DIR / "availability.yaml", avail)


def _merge_yaml(path: Path, data: dict):
    """合并YAML文件（保留已有字段）"""
    existing = {}
    if path.exists():
        with open(path) as f:
            existing = yaml.safe_load(f) or {}

    merged = _deep_merge(existing, data)

    with open(path, "w") as f:
        yaml.dump(merged, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        elif value is not None:
            result[key] = value
    return result
