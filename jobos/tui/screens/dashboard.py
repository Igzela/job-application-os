"""Dashboard screen — pipeline overview, pending actions, health checks."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Static

from jobos.pipeline import action_for_job
from jobos.workspace import load_state, state_path as workspace_state_path

PENDING_ACTION_LABELS = {
    "score": "需要打分",
    "predict": "需要预测",
    "pack": "需要打包",
    "validate": "需要校验",
    "submit": "需要投递",
    "retro": "需要复盘",
}


class DashboardScreen(Screen):
    """总览：pipeline漏斗 + 待处理 + 健康检查"""

    CSS = """
    #pipeline-stats {
        height: auto;
        margin: 1 0;
    }
    #pipeline-stats Table {
        height: auto;
    }
    #pending-section {
        height: auto;
        margin: 1 0;
    }
    #health-section {
        height: 3;
        margin: 1 0;
    }
    .section-title {
        text-style: bold;
        color: $primary;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📊 求职系统总览", classes="section-title")

        # Pipeline stats
        yield DataTable(id="pipeline-stats")

        # Pending actions
        yield Static("⏳ 待处理", classes="section-title")
        yield DataTable(id="pending-section")

        # Health
        yield Static("🏥 健康检查", classes="section-title")
        yield Static("加载中...", id="health-section")

    def on_mount(self):
        self._load_stats()
        self._load_pending()
        self._load_health()

    def _load_state(self) -> dict:
        return load_state(self.state_dir)

    def _load_stats(self):
        state = self._load_state()
        jobs = state.get("jobs", {})

        # Count by status
        counts = {}
        for job in jobs.values():
            status = job.get("status", "unknown")
            counts[status] = counts.get(status, 0) + 1

        table = self.query_one("#pipeline-stats", DataTable)
        table.add_columns("阶段", "数量")
        stages = [
            ("📥 导入", "imported"),
            ("📊 打分", "scored"),
            ("🔮 预测", "predicted"),
            ("📦 打包", "packed"),
            ("📤 投递", "submitted"),
            ("🔄 复盘", "retro"),
        ]
        for label, key in stages:
            count = counts.get(key, 0)
            if count > 0:
                table.add_row(label, str(count))
        if not any(counts.get(k) for _, k in stages):
            table.add_row("(空)", "0")

    def _load_pending(self):
        state = self._load_state()
        jobs = state.get("jobs", {})

        table = self.query_one("#pending-section", DataTable)
        table.add_columns("职位", "公司", "操作")

        pending = []
        for job in jobs.values():
            planned = action_for_job(job)
            if planned is None:
                continue
            label = PENDING_ACTION_LABELS.get(planned.stage)
            if label is None:
                continue
            pending.append((job.get("title", "?"), job.get("company", "?"), label))

        for title, company, action in pending[:10]:
            table.add_row(title[:20], company[:15], action)

        if not pending:
            table.add_row("(无)", "", "")

    def _load_health(self):
        root = Path(self.state_dir)
        checks = []

        # Profile
        for name in ("base.yaml", "skills.yaml"):
            ok = (root / "profile" / name).exists()
            checks.append((f"profile/{name}", ok))

        # State file
        ok = workspace_state_path(root).exists()
        checks.append(("state file", ok))

        # Chrome CDP
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
            checks.append(("Chrome CDP", True))
        except Exception:
            checks.append(("Chrome CDP", False))

        lines = []
        for label, ok in checks:
            mark = "✅" if ok else "❌"
            lines.append(f"  {mark} {label}")

        self.query_one("#health-section").update("\n".join(lines))
