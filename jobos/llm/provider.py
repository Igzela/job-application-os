import json
import os
from pathlib import Path

from .base import LLMAdapter
from .mock import MockLLMAdapter


def _load_env_file():
    """Load .env file if it exists."""
    env_file = Path.home() / ".jobos" / ".env"
    if not env_file.exists():
        return
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception:
        pass


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

    优先级：
    1. config参数（显式传入）
    2. jobos config.yaml (via job config set)
    3. 环境变量 (JOBOS_API_KEY, JOBOS_BASE_URL, JOBOS_PROVIDER, JOBOS_MODEL)
    4. Claude Code配置文件 (~/.claude/settings.json)
    5. Mock（无API时的降级）
    """
    # 加载 .env 文件
    _load_env_file()

    if config is None:
        config = {}

    use_local_config = config.get("use_local_config", True)

    # 从config.yaml读取默认值
    yaml_config = {}
    if use_local_config:
        try:
            from ..config import load_config as _load_config
            yaml_config = _load_config().get("llm", {})
        except Exception:
            yaml_config = {}

    provider = config.get("provider") or yaml_config.get("provider") or os.environ.get("JOBOS_PROVIDER", "")

    # mock provider always returns MockLLMAdapter
    if provider == "mock":
        return MockLLMAdapter.create()

    api_key = config.get("api_key") or os.environ.get("JOBOS_API_KEY", "")
    base_url = config.get("base_url") or yaml_config.get("base_url") or os.environ.get("JOBOS_BASE_URL", "")
    model = config.get("model") or yaml_config.get("model") or os.environ.get("JOBOS_MODEL", "")
    max_tokens = config.get("max_tokens") or yaml_config.get("max_tokens") or os.environ.get("JOBOS_MAX_TOKENS", 4096)

    # 如果没配置，尝试从Claude Code配置读取
    if not api_key or not base_url or not model:
        claude_config = _read_claude_config()
        if not api_key:
            api_key = claude_config.get("api_key", "")
        if not base_url:
            base_url = claude_config.get("base_url", "")
        if not model:
            model = claude_config.get("model", "")

    # 如果有key但没指定provider，自动检测
    if api_key and not provider:
        if "anthropic" in base_url.lower() or "claude" in base_url.lower():
            provider = "anthropic"
        else:
            provider = "openai"

    # 没有API配置，返回Mock
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
