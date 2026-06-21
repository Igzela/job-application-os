# Browser Setup

## 核心原则

抓取以 Scrapling 为主。登录、人工验证、最终提交保留用户可接管 CDP。

## 允许的浏览器配置

| 组件 | 版本 | 说明 |
|------|------|------|
| **Scrapling** | 0.4.x | 抓取、动态渲染、stealth、Spider |
| **Chromium** | 系统安装 | 路径: `/opt/chromium/chrome-linux/chrome` |

## 职责

- Scrapling HTTP/Dynamic/Stealth：抓取、解析、crawl。
- 用户 CDP：登录、人工验证码、最终提交。
- 自动 Cloudflare/Turnstile solver：关闭。

## 代码中的强制执行

所有浏览器启动都通过 `jobos/browser.py` 的 `CHROMIUM_PATH` 常量：

```python
# jobos/browser.py
CHROMIUM_PATH = "/opt/chromium/chrome-linux/chrome"
```

`jobos/scrapling_runtime.py` 自动注入 `executable_path=CHROMIUM_PATH`。

## 三种浏览器引擎

| 引擎 | 底层 | 用途 |
|------|------|------|
| `http` | curl_cffi | HTTP 请求，TLS 指纹模拟 |
| `dynamic` | Scrapling + Chromium | JS 渲染 |
| `stealth` | Scrapling + Chromium | 指纹保护；不自动处理验证码 |

## 新 Agent 接入指南

任何新 Agent（Claude Code、Codex、其他 AI）接入本项目时，必须遵守：

1. **读取本文档** (`docs/BROWSER_SETUP.md`)
2. **优先使用系统 Chromium**
3. **不要修改 `CHROMIUM_PATH`** — 除非有明确理由并更新本文档
4. **StealthyFetcher 通过 `jobos/scrapling_runtime.py`**

## 验证命令

```bash
# 检查 Chromium 是否存在
ls -la /opt/chromium/chrome-linux/chrome

# 检查 StealthyFetcher 是否可用
python3 -c "from jobos.scrapling_runtime import capabilities; c = capabilities(); print(f'Stealth: {c.stealth}')"

# 测试 stealth 引擎
python3 -c "
from jobos.scrapling_runtime import fetch_page
page = fetch_page('https://www.example.com', engine='stealth', headless=True, timeout=30)
print(f'Status: {page.status}')
"
```

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| `Executable doesn't exist` | Chromium 路径错误 | 检查 `/opt/chromium/chrome-linux/chrome` 是否存在 |
| `StealthyFetcher is unavailable` | optional extra 未安装 | 在虚拟环境安装 `.[scrapling]` |
| `Executable doesn't exist` | Chromium 路径错误 | 检查 `CHROMIUM_PATH` |

## 相关文件

- `jobos/browser.py` — 浏览器连接管理，定义 `CHROMIUM_PATH`
- `jobos/scrapling_runtime.py` — Scrapling 运行时，自动注入 `executable_path`
- `jobos/stealth_browser.py` — BOSS 优化的 StealthyFetcher 封装
- `ARCHITECTURE.md` — 系统架构文档
