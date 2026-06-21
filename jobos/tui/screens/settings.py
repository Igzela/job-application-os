"""Settings screen — health checks, rubric management, pipeline start."""

import json
import subprocess
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static, TextArea

from jobos.workspace import APPLICATIONS_DIR, JOBS_DIR, PREDICTIONS_DIR, RETROS_DIR


class SettingsScreen(Screen):
    """设置"""

    CSS = """
    #health-list {
        height: auto;
        margin: 1 0;
    }
    #pipeline-output {
        height: 1fr;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }
    #pipeline-input {
        margin: 1 0;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("⚙️ 设置", classes="section-title")

        # Health check
        yield Static("🏥 工作区健康检查", classes="section-title")
        yield Button("刷新检查", id="btn-health", variant="default")
        yield ScrollableContainer(
            Static("点击刷新检查", id="health-list"),
        )

        # Full pipeline
        yield Static("🚀 全流程启动", classes="section-title")
        with Horizontal(id="pipeline-input"):
            yield Input(placeholder="搜索关键词", id="pipeline-keyword")
            yield Input(placeholder="最大职位数", id="pipeline-max", value="10")
            yield Button("模拟运行", id="btn-pipeline-dry", variant="warning")
            yield Button("真实投递", id="btn-pipeline-live", variant="error")

        yield ScrollableContainer(
            Static("点击按钮启动全流程", id="pipeline-output"),
        )

    def on_mount(self):
        self._run_health_check()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-health":
            self._run_health_check()
        elif event.button.id == "btn-pipeline-dry":
            self._run_pipeline(dry_run=True)
        elif event.button.id == "btn-pipeline-live":
            self._run_pipeline(dry_run=False)

    def _run_health_check(self):
        root = Path(self.state_dir)
        checks = []

        required_dirs = ["profile", JOBS_DIR, PREDICTIONS_DIR, APPLICATIONS_DIR, RETROS_DIR, "rubrics"]
        for d in required_dirs:
            ok = (root / d).is_dir()
            checks.append((f"📁 {d}/", ok))

        for name in ("base.yaml", "skills.yaml"):
            ok = (root / "profile" / name).exists()
            checks.append((f"📄 profile/{name}", ok))

        # Chrome
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
            checks.append(("🌐 Chrome CDP", True))
        except Exception:
            checks.append(("🌐 Chrome CDP", False))

        # Python
        import sys
        checks.append((f"🐍 Python {sys.version.split()[0]}", sys.version_info >= (3, 11)))

        lines = []
        for label, ok in checks:
            mark = "✅" if ok else "❌"
            lines.append(f"{mark} {label}")

        self.query_one("#health-list").update("\n".join(lines))

    def _run_pipeline(self, dry_run: bool):
        output = self.query_one("#pipeline-output")
        keyword = self.query_one("#pipeline-keyword").value.strip()
        max_jobs = self.query_one("#pipeline-max").value.strip() or "10"

        mode = "模拟" if dry_run else "真实"
        output.update(f"🚀 启动全流程 [{mode}]...\n关键词: {keyword}\n最大职位: {max_jobs}\n\n加载中...")

        try:
            from jobos.orchestrator import run_full_pipeline
            result = run_full_pipeline(
                state_dir=self.state_dir,
                cdp_port=9222,
                max_jobs=int(max_jobs),
                dry_run=dry_run,
                search_keyword=keyword,
            )

            lines = [f"✅ 完成！"]
            lines.append(f"找到: {result.get('total_found', 0)} 个职位")
            lines.append(f"分析: {result.get('analyzed', 0)} 个")
            lines.append(f"投递: {result.get('submitted', 0)} 个")
            lines.append("")

            for r in result.get("results", []):
                status = r.get("status", "?")
                job = r.get("job", {})
                score = r.get("score", "-")
                emoji = {
                    "dry_run": "✅", "submitted": "📤", "low_match": "⏭️",
                    "scam_rejected": "🚫", "high_risk": "⚠️", "error": "❌",
                }.get(status, "❓")
                lines.append(f"  {emoji} {job.get('title', '?')[:25]} — {status} (分数:{score})")

            output.update("\n".join(lines))
        except Exception as e:
            output.update(f"❌ 流程失败: {e}")
