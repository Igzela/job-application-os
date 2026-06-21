import json
import os
from pathlib import Path

from .base import LLMAdapter
from .mock import MockLLMAdapter


def _read_claude_config() -> dict:
    """从Claude Code配置文件读取API key、URL和model"""
    config_path = Path.home() / ".claude" / "settings.json"
    if not config_path.exists():
        return {}

    try:
        with open(config_path) as f:
            data = json.load(f)
        env = data.get("env", {})
        return {
            "api_key": env.get("ANTHROPIC_AUTH_TOKEN", ""),
            "base_url": env.get("ANTHROPIC_BASE_URL", ""),
            "model": env.get("ANTHROPIC_DEFAULT_SONNET_MODEL_NAME", ""),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def get_llm_adapter(config: dict | None = None) -> LLMAdapter:
    """获取LLM适配器

    Priority: explicit config, process environment, Job OS .env, config.yaml,
    then deterministic mock. Claude Code config is read only when explicitly
    enabled with ``use_claude_config=True``.
    """
    if config is None:
        config = {}

    use_local_config = config.get("use_local_config", True)
    from ..config import load_config, load_env_values

    env = {**load_env_values(), **dict(os.environ)}

    yaml_config = {}
    if use_local_config:
        yaml_config = load_config(environ=env).get("llm", {})

    provider = (
        config.get("provider")
        or env.get("JOBOS_PROVIDER")
        or yaml_config.get("provider")
        or ""
    )

    if provider == "mock":
        return MockLLMAdapter.create()

    api_key_env = config.get("api_key_env") or yaml_config.get(
        "api_key_env",
        "JOBOS_API_KEY",
    )
    api_key = (
        config.get("api_key")
        or env.get("JOBOS_API_KEY")
        or env.get(api_key_env, "")
    )
    base_url = (
        config.get("base_url")
        or env.get("JOBOS_BASE_URL")
        or yaml_config.get("base_url", "")
    )
    model = (
        config.get("model")
        or env.get("JOBOS_MODEL")
        or yaml_config.get("model", "")
    )
    max_tokens = (
        config.get("max_tokens")
        or env.get("JOBOS_MAX_TOKENS")
        or yaml_config.get("max_tokens", 4096)
    )

    if config.get("use_claude_config"):
        claude_config = _read_claude_config()
        if not api_key:
            api_key = claude_config.get("api_key", "")
        if not base_url:
            base_url = claude_config.get("base_url", "")
        if not model:
            model = claude_config.get("model", "")

    if api_key and not provider:
        if "anthropic" in base_url.lower() or "claude" in base_url.lower():
            provider = "anthropic"
        else:
            provider = "openai"

    if not api_key or not base_url:
        return MockLLMAdapter.create()

    if provider == "anthropic":
        from .anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter.create(api_key=api_key, base_url=base_url, model=model or None)

    if provider == "openai":
        from .openai_adapter import OpenAIAdapter
        return OpenAIAdapter.create(
            api_key=api_key,
            base_url=base_url,
            model=model or None,
            max_tokens=int(max_tokens),
        )

    raise ValueError(f"Unknown provider: {provider}. Supported: anthropic, openai")
