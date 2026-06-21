"""Configuration system — Hermes-style.

Single config.yaml + .env for secrets.
CLI: job config show|set|get|path|env-path|wizard
"""

import os
import re
import copy
import yaml
from pathlib import Path

CONFIG_DIR = Path.home() / ".jobos"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ENV_FILE = CONFIG_DIR / ".env"

DEFAULT_CONFIG = {
    "_config_version": 1,

    "llm": {
        "provider": "anthropic",
        "model": "mimo-v2.5",
        "base_url": "",
        "api_key_env": "JOBOS_API_KEY",
        "temperature": 0.7,
        "max_tokens": 4096,
        "timeout": 120,
    },

    "browser": {
        "cdp_url": "http://localhost:9222",
        "user_data_dir": "/tmp/chrome-boss",
        "headless": False,
    },

    "submit": {
        "min_delay": 30,
        "max_delay": 120,
        "action_delay_min": 2,
        "action_delay_max": 5,
    },

    "search": {
        "default_city": "100010000",
        "max_results": 20,
        "keywords": [
            "Python后端",
            "Python开发",
            "后端开发",
            "Django",
            "FastAPI",
            "AI应用开发",
        ],
        "max_candidates_per_keyword": 20,
        "max_total_candidates": 100,
    },

    "extraction": {
        "use_scrapling": True,
        "record_diagnostics": True,
        "include_html_snapshot": True,
        "html_snapshot_limit": 250000,
    },

    "scoring": {
        "min_score_to_apply": 60,
    },

    "display": {
        "language": "zh",
        "show_score_bars": True,
    },
}


def _expand_env(value: str, environ: dict[str, str] | None = None) -> str:
    """Expand ${VAR} or $VAR in string values."""
    if not isinstance(value, str):
        return value
    environ = environ if environ is not None else dict(os.environ)

    def replacer(m):
        var = m.group(1) or m.group(2)
        return environ.get(var, m.group(0))

    return re.sub(r"\$\{(\w+)\}|\$(\w+)", replacer, value)


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_env_values(path: str | Path | None = None) -> dict[str, str]:
    """Parse the Job OS env file without mutating process environment."""
    path = Path(path) if path is not None else ENV_FILE
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'\"")
            if key:
                values[key] = val
    return values


def load_config(environ: dict[str, str] | None = None) -> dict:
    """Load config with deep merge over defaults."""
    resolved_env = {
        **load_env_values(),
        **(dict(os.environ) if environ is None else environ),
    }

    if not CONFIG_FILE.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    with open(CONFIG_FILE) as f:
        user = yaml.safe_load(f) or {}

    merged = _deep_merge(DEFAULT_CONFIG, user)

    # Expand env vars in string values
    def expand(obj):
        if isinstance(obj, str):
            return _expand_env(obj, resolved_env)
        elif isinstance(obj, dict):
            return {k: expand(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [expand(v) for v in obj]
        return obj

    return expand(merged)


def save_config(config: dict):
    """Save config to YAML file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def set_config_value(key: str, value: str):
    """Set a config value using dot-notation.

    Examples:
        set_config_value("llm.provider", "openai")
        set_config_value("llm.model", "gpt-4o")
        set_config_value("browser.headless", "true")
    """
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]

    # Auto-cast
    last_key = keys[-1]
    if value.lower() in ("true", "false"):
        target[last_key] = value.lower() == "true"
    else:
        try:
            target[last_key] = int(value)
        except ValueError:
            try:
                target[last_key] = float(value)
            except ValueError:
                target[last_key] = value

    save_config(config)
    return config


def get_config_value(key: str, default=None):
    """Get a config value using dot-notation."""
    config = load_config()
    keys = key.split(".")
    target = config
    for k in keys:
        if isinstance(target, dict) and k in target:
            target = target[k]
        else:
            return default
    return target


def config_wizard():
    """Interactive config wizard."""
    print("\n╔══════════════════════════════════════╗")
    print("║       求职操作系统 — 配置向导          ║")
    print("╚══════════════════════════════════════╝\n")

    config = load_config()

    # LLM
    print("━━━ LLM配置 ━━━\n")
    print("支持的provider: anthropic / openai")
    print(f"当前provider: {config['llm']['provider']}")
    p = input(f"Provider [{config['llm']['provider']}]: ").strip()
    if p:
        config["llm"]["provider"] = p

    print(f"当前model: {config['llm']['model']}")
    m = input(f"Model [{config['llm']['model']}]: ").strip()
    if m:
        config["llm"]["model"] = m

    print(f"当前base_url: {config['llm']['base_url'] or '(未配置)'}")
    u = input("Base URL (留空保持不变): ").strip()
    if u:
        config["llm"]["base_url"] = u

    print(f"\nAPI Key存放在 .env 文件中: {ENV_FILE}")
    key = input("API Key (留空跳过，稍后手动编辑.env): ").strip()
    if key:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Append or update
        env_content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
        if "JOBOS_API_KEY=" in env_content:
            env_content = re.sub(r"JOBOS_API_KEY=.*", f"JOBOS_API_KEY={key}", env_content)
        else:
            env_content += f"\nJOBOS_API_KEY={key}\n"
        ENV_FILE.write_text(env_content.strip() + "\n")
        print(f"✅ API Key 已保存到 {ENV_FILE}")

    # Browser
    print("\n━━━ 浏览器配置 ━━━\n")
    print(f"当前CDP地址: {config['browser']['cdp_url']}")
    c = input("CDP地址 (留空保持不变): ").strip()
    if c:
        config["browser"]["cdp_url"] = c

    # Submit
    print("\n━━━ 投递配置 ━━━\n")
    print(f"当前投递间隔: {config['submit']['min_delay']}-{config['submit']['max_delay']}秒")
    lo = input("最小间隔秒数 (留空保持不变): ").strip()
    if lo:
        config["submit"]["min_delay"] = int(lo)
    hi = input("最大间隔秒数 (留空保持不变): ").strip()
    if hi:
        config["submit"]["max_delay"] = int(hi)

    save_config(config)
    print(f"\n✅ 配置已保存到 {CONFIG_FILE}")
    print(f"   如需修改API Key，编辑 {ENV_FILE}")


def print_config():
    """Pretty-print current config."""
    config = load_config()
    # Mask API key
    def mask(obj):
        if isinstance(obj, dict):
            return {k: ("***" if "key" in k.lower() and isinstance(v, str) and v else mask(v))
                    for k, v in obj.items()}
        elif isinstance(obj, list):
            return [mask(v) for v in obj]
        return obj

    print(yaml.dump(mask(config), allow_unicode=True, default_flow_style=False, sort_keys=False))
