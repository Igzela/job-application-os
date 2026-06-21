"""Job Queue and Job Detail screens."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen
from textual.widgets import DataTable, Static

from jobos.workspace import load_state, state_path as workspace_state_path


class JobQueueScreen(Screen):
    """职位列表"""

    CSS = """
    #job-table {
        height: 1fr;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📋 职位列表", classes="section-title")
        yield DataTable(id="job-table")

    def on_mount(self):
        self._load_jobs()

    def _load_jobs(self):
        state_file = workspace_state_path(self.state_dir)
        if not state_file.exists():
            return

        state = load_state(self.state_dir)
        jobs = state.get("jobs", {})

        table = self.query_one("#job-table", DataTable)
        table.add_columns("ID", "职位", "公司", "状态", "分数", "来源")

        for job_id, job in jobs.items():
            scores = job.get("scores", {})
            score = scores.get("final_score", "-")
            if isinstance(score, float):
                score = f"{score:.1f}"

            table.add_row(
                job_id[:12],
                (job.get("title", "?"))[:25],
                (job.get("company", "?"))[:15],
                job.get("status", "?"),
                str(score),
                job.get("source", job.get("source_file", "?"))[:10],
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.row_key:
            job_id = str(event.row_key.value)
            self.app.push_screen(JobDetailScreen(self.state_dir, job_id))


class JobDetailScreen(Screen):
    """职位详情"""

    CSS = """
    #detail-content {
        height: 1fr;
        padding: 1;
    }
    .field-label {
        text-style: bold;
        color: $primary;
    }
    """

    def __init__(self, state_dir: str, job_id: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir
        self.job_id = job_id

    def compose(self) -> ComposeResult:
        yield Static(f"📋 职位详情 — {self.job_id}", classes="section-title")
        yield ScrollableContainer(
            Static("加载中...", id="detail-content"),
        )

    def on_mount(self):
        self._load_detail()

    def _load_detail(self):
        state_file = workspace_state_path(self.state_dir)
        if not state_file.exists():
            return

        state = load_state(self.state_dir)
        job = state.get("jobs", {}).get(self.job_id, {})

        lines = []
        lines.append(f"职位: {job.get('title', '未知')}")
        lines.append(f"公司: {job.get('company', '未知')}")
        lines.append(f"地点: {job.get('location', '未知')}")
        lines.append(f"状态: {job.get('status', '未知')}")
        lines.append(f"来源: {job.get('source', '未知')}")
        lines.append("")

        # Scores
        scores = job.get("scores", {})
        if scores:
            lines.append("── 评分 ──")
            for dim in ["fit", "evidence", "opportunity", "strategic", "friction", "risk"]:
                val = scores.get(dim, "-")
                if isinstance(val, float):
                    bar = "█" * int(val) + "░" * (10 - int(val))
                    lines.append(f"  {dim:12s} {bar} {val:.1f}")
            if "final_score" in scores:
                lines.append(f"  {'总分':12s} {scores['final_score']:.2f}")
            lines.append("")

        # Retro
        retro = job.get("retro", {})
        if retro:
            lines.append("── 复盘 ──")
            for key in ["status_3d", "status_14d", "status_30d"]:
                val = retro.get(key, "")
                if val:
                    lines.append(f"  {key}: {val}")
            lines.append("")

        # Link
        if job.get("link"):
            lines.append(f"链接: {job['link']}")

        self.query_one("#detail-content").update("\n".join(lines))
