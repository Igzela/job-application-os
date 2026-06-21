"""Job Application OS — Textual TUI"""

import json
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Input, OptionList, Static, Button, TextArea
from textual.widgets.option_list import Option

from jobos.pipeline import action_for_job
from jobos.workspace import (
    APPLICATIONS_DIR,
    JOBS_DIR,
    PREDICTIONS_DIR,
    RETROS_DIR,
    jobs_normalized_dir,
    jobs_raw_dir,
    load_state,
    save_state,
    state_path as workspace_state_path,
)

PENDING_ACTION_LABELS = {
    "score": "需打分",
    "predict": "需预测",
    "pack": "需打包",
    "validate": "需校验",
    "submit": "需投递",
    "retro": "需复盘",
}


class Sidebar(Static):
    def compose(self) -> ComposeResult:
        yield OptionList(
            Option("📊 总览", id="dashboard"),
            Option("📋 职位", id="jobs"),
            Option("📥 导入", id="import"),
            Option("🤖 AI", id="llm"),
            Option("👤 档案", id="profile"),
            Option("⚙️ 设置", id="settings"),
        )


class StatusBar(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def on_mount(self):
        self._update()

    def _update(self):
        state_file = workspace_state_path(self.state_dir)
        if not state_file.exists():
            self.update("求职操作系统 — 无数据")
            return
        try:
            state = load_state(self.state_dir)
            jobs = state.get("jobs", {})
            total = len(jobs)
            submitted = sum(1 for j in jobs.values() if j.get("status") == "submitted")
            self.update(f"  职位: {total}个  │  已投递: {submitted}个  │  待处理: {total - submitted}个")
        except Exception:
            self.update("求职操作系统")


# ── Dashboard ──

class Dashboard(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📊 求职系统总览", classes="section-title")
        yield DataTable(id="pipeline-table")
        yield Static("⏳ 待处理", classes="section-title")
        yield DataTable(id="pending-table")
        yield Static("🏥 健康检查", classes="section-title")
        yield Static("加载中...", id="health-text")

    def on_mount(self):
        self._load_pipeline()
        self._load_pending()
        self._load_health()

    def _load_state(self) -> dict:
        return load_state(self.state_dir)

    def _load_pipeline(self):
        state = self._load_state()
        jobs = state.get("jobs", {})
        counts = {}
        for j in jobs.values():
            s = j.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1

        t = self.query_one("#pipeline-table", DataTable)
        t.add_columns("阶段", "数量")
        for label, key in [("📥 导入", "imported"), ("📊 打分", "scored"),
                           ("🔮 预测", "predicted"), ("📦 打包", "packed"),
                           ("📤 投递", "submitted")]:
            c = counts.get(key, 0)
            if c > 0:
                t.add_row(label, str(c))
        if not counts:
            t.add_row("(空)", "0")

    def _load_pending(self):
        state = self._load_state()
        t = self.query_one("#pending-table", DataTable)
        t.add_columns("职位", "公司", "操作")
        has_pending = False
        for j in state.get("jobs", {}).values():
            planned = action_for_job(j)
            if planned is None:
                continue
            label = PENDING_ACTION_LABELS.get(planned.stage)
            if label is None:
                continue
            t.add_row(j.get("title", "?")[:20], j.get("company", "?")[:15], label)
            has_pending = True
        if not has_pending:
            t.add_row("(无待处理)", "", "")

    def _load_health(self):
        root = Path(self.state_dir)
        checks = []
        for name in ("base.yaml", "skills.yaml"):
            checks.append(f"{'✅' if (root / 'profile' / name).exists() else '❌'} profile/{name}")
        checks.append(f"{'✅' if workspace_state_path(root).exists() else '❌'} state file")
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
            checks.append("✅ Chrome CDP")
        except Exception:
            checks.append("❌ Chrome CDP")
        self.query_one("#health-text").update("  ".join(checks))


# ── Jobs ──

class JobList(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📋 职位列表", classes="section-title")
        yield DataTable(id="job-table")

    def on_mount(self):
        f = workspace_state_path(self.state_dir)
        if not f.exists():
            return
        state = load_state(self.state_dir)
        t = self.query_one("#job-table", DataTable)
        t.add_columns("ID", "职位", "公司", "状态", "分数")
        for jid, j in state.get("jobs", {}).items():
            scores = j.get("scores", {})
            score = scores.get("final_score", "-")
            if isinstance(score, float):
                score = f"{score:.1f}"
            t.add_row(jid[:12], j.get("title", "?")[:25], j.get("company", "?")[:15],
                       j.get("status", "?"), str(score))


# ── Import ──

class ImportView(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📥 导入职位", classes="section-title")
        yield Static("文件路径:")
        with Horizontal():
            yield Input(placeholder="JD文件路径...", id="file-input")
            yield Button("导入文件", id="btn-file", variant="primary")
        yield Static("或粘贴JD:")
        yield TextArea(id="paste-area")
        yield Button("导入粘贴", id="btn-paste", variant="primary")
        yield Static("BOSS搜索:")
        with Horizontal():
            yield Input(placeholder="关键词", id="boss-kw")
            yield Button("搜索导入", id="btn-boss", variant="success")
        yield Static("", id="import-result")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-file":
            self._import_file()
        elif event.button.id == "btn-paste":
            self._import_paste()
        elif event.button.id == "btn-boss":
            self._boss_search()

    def _import_file(self):
        path = self.query_one("#file-input").value.strip()
        if not path:
            self.query_one("#import-result").update("[red]请输入路径[/red]")
            return
        try:
            from jobos.importer import import_job
            root = Path(self.state_dir)
            data = import_job(path, str(jobs_normalized_dir(root)))
            state = load_state(root)
            state["jobs"][data["job_id"]] = {"title": data["title"], "company": data["company"],
                                               "status": "imported", "location": data.get("location", "")}
            save_state(root, state)
            self.query_one("#import-result").update(f"[green]✅ {data['title']} @ {data['company']}[/green]")
        except Exception as e:
            self.query_one("#import-result").update(f"[red]❌ {e}[/red]")

    def _import_paste(self):
        text = self.query_one("#paste-area").text.strip()
        if not text:
            self.query_one("#import-result").update("[red]请粘贴JD[/red]")
            return
        try:
            import tempfile
            from jobos.importer import import_job
            root = Path(self.state_dir)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=str(root)) as f:
                f.write(text)
                tmp = f.name
            try:
                data = import_job(tmp, str(jobs_normalized_dir(root)))
                state = load_state(root)
                state["jobs"][data["job_id"]] = {"title": data["title"], "company": data["company"],
                                                   "status": "imported"}
                save_state(root, state)
                self.query_one("#import-result").update(f"[green]✅ {data['title']}[/green]")
            finally:
                Path(tmp).unlink(missing_ok=True)
        except Exception as e:
            self.query_one("#import-result").update(f"[red]❌ {e}[/red]")

    def _boss_search(self):
        kw = self.query_one("#boss-kw").value.strip()
        if not kw:
            self.query_one("#import-result").update("[red]请输入关键词[/red]")
            return
        self.query_one("#import-result").update("🔍 搜索中...")
        try:
            from jobos.boss_import import import_from_boss
            import re
            from datetime import datetime, timezone
            jobs = import_from_boss(kw, "100010000", 9222)
            if not jobs:
                self.query_one("#import-result").update(f"未找到 '{kw}' 相关职位")
                return
            root = Path(self.state_dir)
            raw_dir = jobs_raw_dir(root)
            raw_dir.mkdir(parents=True, exist_ok=True)
            state = load_state(root)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            for i, job in enumerate(jobs):
                slug = re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-")[:40]
                jid = f"{ts}-boss-{i:03d}-{slug}"
                (raw_dir / f"{jid}.json").write_text(json.dumps(job, indent=2, ensure_ascii=False))
                state["jobs"][jid] = {"title": job["title"], "company": job["company"],
                                       "status": "imported", "source": "boss_zhipin", "link": job.get("link", "")}
            save_state(root, state)
            self.query_one("#import-result").update(f"[green]✅ 导入 {len(jobs)} 个职位[/green]")
        except Exception as e:
            self.query_one("#import-result").update(f"[red]❌ {e}[/red]")


# ── LLM Chat ──

class LLMView(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir
        self.conv = None

    def compose(self) -> ComposeResult:
        yield Static("🤖 AI助手", classes="section-title")
        yield ScrollableContainer(
            Static("👋 你好！输入消息开始对话。", id="chat-history"),
            id="chat-scroll",
        )
        with Horizontal():
            yield Input(placeholder="输入消息...", id="chat-input")
            yield Button("发送", id="btn-send", variant="primary")

    def on_mount(self):
        try:
            from jobos.llm.provider import get_llm_adapter
            from jobos.llm.conversation import Conversation
            llm = get_llm_adapter()
            hpath = Path(self.state_dir) / "profile" / "chat_history.json"
            self.conv = Conversation(llm, hpath)
        except Exception as e:
            self.query_one("#chat-history").update(f"LLM初始化失败: {e}")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-send":
            self._send()

    def on_input_submitted(self, event):
        if event.input.id == "chat-input":
            self._send()

    def _send(self):
        text = self.query_one("#chat-input").value.strip()
        if not text:
            return
        self.query_one("#chat-input").value = ""
        history = self.query_one("#chat-history")
        history.update(history.renderable + f"\n\n🧑 你: {text}")

        if not self.conv:
            return
        try:
            from jobos.llm.prompts import INTRO_SYSTEM
            reply = self.conv.chat(text, system=INTRO_SYSTEM)
            history.update(history.renderable + f"\n\n🤖 AI: {reply}")
        except Exception as e:
            history.update(history.renderable + f"\n\n❌ 错误: {e}")


# ── Profile ──

class ProfileView(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir
        self.current_file = "base.yaml"

    def compose(self) -> ComposeResult:
        yield Static("👤 求职档案 (按1-4切换文件)", classes="section-title")
        yield TextArea(id="profile-editor")
        with Horizontal():
            yield Button("1 基本", id="f1")
            yield Button("2 技能", id="f2")
            yield Button("3 时间", id="f3")
            yield Button("4 经历", id="f4")
            yield Button("保存", id="btn-save", variant="primary")
        yield Static("", id="save-status")

    def on_mount(self):
        self._load("base.yaml")

    def on_button_pressed(self, event: Button.Pressed):
        files = {"f1": "base.yaml", "f2": "skills.yaml", "f3": "availability.yaml", "f4": "evidence_bank.md"}
        if event.button.id in files:
            self._load(files[event.button.id])
        elif event.button.id == "btn-save":
            self._save()

    def _load(self, name: str):
        self.current_file = name
        path = Path(self.state_dir) / "profile" / name
        content = path.read_text() if path.exists() else f"# {name}\n"
        self.query_one("#profile-editor").load_text(content)
        self.query_one("#save-status").update(f"📂 {name}")

    def _save(self):
        path = Path(self.state_dir) / "profile" / self.current_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.query_one("#profile-editor").text)
        self.query_one("#save-status").update(f"[green]✅ 已保存 {self.current_file}[/green]")


# ── Settings ──

class SettingsView(Static):
    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("⚙️ 设置", classes="section-title")
        yield Button("刷新健康检查", id="btn-health")
        yield Static("加载中...", id="health-output")
        yield Static("")
        yield Static("🚀 全流程启动", classes="section-title")
        with Horizontal():
            yield Input(placeholder="搜索关键词", id="pipe-kw")
            yield Button("模拟运行", id="btn-dry", variant="warning")
            yield Button("真实投递", id="btn-live", variant="error")
        yield ScrollableContainer(Static("点击按钮启动", id="pipe-output"))

    def on_mount(self):
        self._health()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-health":
            self._health()
        elif event.button.id == "btn-dry":
            self._pipeline(True)
        elif event.button.id == "btn-live":
            self._pipeline(False)

    def _health(self):
        root = Path(self.state_dir)
        lines = []
        for d in ["profile", JOBS_DIR, PREDICTIONS_DIR, APPLICATIONS_DIR]:
            lines.append(f"{'✅' if (root / d).is_dir() else '❌'} {d}/")
        import urllib.request
        try:
            urllib.request.urlopen("http://localhost:9222/json/version", timeout=2)
            lines.append("✅ Chrome CDP")
        except Exception:
            lines.append("❌ Chrome CDP")
        self.query_one("#health-output").update("  ".join(lines))

    def _pipeline(self, dry_run: bool):
        out = self.query_one("#pipe-output")
        kw = self.query_one("#pipe-kw").value.strip()
        out.update("🚀 启动中...")
        try:
            from jobos.orchestrator import run_full_pipeline
            result = run_full_pipeline(self.state_dir, cdp_port=9222, max_jobs=5,
                                       dry_run=dry_run, search_keyword=kw)
            lines = [f"找到 {result.get('total_found', 0)} | 投递 {result.get('submitted', 0)}"]
            for r in result.get("results", []):
                j = r.get("job", {})
                lines.append(f"  {j.get('title', '?')[:25]} — {r.get('status', '?')}")
            out.update("\n".join(lines))
        except Exception as e:
            out.update(f"❌ {e}")


# ── Main App ──

class JobOSApp(App):
    CSS = """
    Screen { layout: horizontal; }
    #sidebar { width: 16; height: 100%; border-right: solid $primary; padding: 1 0; }
    #sidebar OptionList { height: 100%; }
    #main-area { width: 1fr; height: 1fr; padding: 0 1; overflow-y: auto; }
    #status-bar { dock: bottom; height: 1; background: $primary; color: $text; }
    .section-title { text-style: bold; color: $primary; margin: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("q", "quit", "退出"),
        Binding("d", "nav('dashboard')", "总览"),
        Binding("j", "nav('jobs')", "职位"),
        Binding("i", "nav('import')", "导入"),
        Binding("a", "nav('llm')", "AI"),
        Binding("p", "nav('profile')", "档案"),
        Binding("s", "nav('settings')", "设置"),
    ]

    def __init__(self, state_dir: str | Path = "."):
        super().__init__()
        self.state_dir = str(Path(state_dir).resolve())

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar(id="sidebar")
            yield Vertical(id="main-area")
        yield StatusBar(self.state_dir, id="status-bar")
        yield Footer()

    def on_mount(self):
        self._show("dashboard")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        self._show(event.option_id)

    def action_nav(self, screen_id: str):
        self.query_one("#sidebar OptionList").highlighted = {
            "dashboard": 0, "jobs": 1, "import": 2, "llm": 3, "profile": 4, "settings": 5
        }.get(screen_id, 0)
        self._show(screen_id)

    def _show(self, name: str):
        main = self.query_one("#main-area")
        main.remove_children()
        views = {
            "dashboard": lambda: Dashboard(self.state_dir),
            "jobs": lambda: JobList(self.state_dir),
            "import": lambda: ImportView(self.state_dir),
            "llm": lambda: LLMView(self.state_dir),
            "profile": lambda: ProfileView(self.state_dir),
            "settings": lambda: SettingsView(self.state_dir),
        }
        if name in views:
            main.mount(views[name]())
