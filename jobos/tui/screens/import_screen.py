"""Import screen — file import, paste JD, BOSS search."""

import json
import re
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Static, TextArea

from jobos.workspace import jobs_normalized_dir, jobs_raw_dir, load_state, save_state


class ImportScreen(Screen):
    """导入职位描述"""

    CSS = """
    #import-section {
        padding: 1;
    }
    .import-group {
        margin: 1 0;
    }
    #result-area {
        margin: 1 0;
        min-height: 3;
    }
    .field-label {
        text-style: bold;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("📥 导入职位", classes="section-title")

        with Vertical(id="import-section"):
            # File import
            yield Static("从文件导入", classes="field-label")
            with Horizontal(classes="import-group"):
                yield Input(placeholder="文件路径...", id="file-input")
                yield Button("导入", id="btn-file", variant="primary")

            # Paste JD
            yield Static("粘贴JD文本", classes="field-label")
            yield TextArea(id="paste-area")
            yield Button("导入粘贴内容", id="btn-paste", variant="primary")

            # BOSS search
            yield Static("BOSS直聘搜索", classes="field-label")
            with Horizontal(classes="import-group"):
                yield Input(placeholder="关键词 (如 Python开发)", id="boss-keyword")
                yield Input(placeholder="城市代码 (默认全国)", id="boss-city", value="100010000")
                yield Button("搜索", id="btn-boss", variant="success")

            yield Static("", id="result-area")

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
            self._show_result("❌ 请输入文件路径", error=True)
            return

        try:
            from jobos.importer import import_job
            root = Path(self.state_dir)
            data = import_job(path, str(jobs_normalized_dir(root)))

            # Update state
            state = load_state(root)
            state["jobs"][data["job_id"]] = {
                "title": data["title"],
                "company": data["company"],
                "location": data.get("location", ""),
                "status": "imported",
                "captured_at": data.get("imported_at", ""),
            }
            save_state(root, state)
            self._show_result(f"✅ 导入成功: {data['title']} @ {data['company']}")
        except Exception as e:
            self._show_result(f"❌ 导入失败: {e}", error=True)

    def _import_paste(self):
        text = self.query_one("#paste-area").text
        if not text.strip():
            self._show_result("❌ 请粘贴JD文本", error=True)
            return

        try:
            from jobos.importer import import_job
            import tempfile

            root = Path(self.state_dir)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, dir=str(root)) as f:
                f.write(text)
                tmp = f.name

            try:
                data = import_job(tmp, str(jobs_normalized_dir(root)))

                state = load_state(root)
                state["jobs"][data["job_id"]] = {
                    "title": data["title"],
                    "company": data["company"],
                    "location": data.get("location", ""),
                    "status": "imported",
                    "captured_at": data.get("imported_at", ""),
                }
                save_state(root, state)
                self._show_result(f"✅ 导入成功: {data['title']} @ {data['company']}")
            finally:
                Path(tmp).unlink(missing_ok=True)
        except Exception as e:
            self._show_result(f"❌ 导入失败: {e}", error=True)

    def _boss_search(self):
        keyword = self.query_one("#boss-keyword").value.strip()
        if not keyword:
            self._show_result("❌ 请输入搜索关键词", error=True)
            return

        self._show_result("🔍 连接BOSS直聘...")
        try:
            from jobos.boss_import import import_from_boss
            city = self.query_one("#boss-city").value.strip() or "100010000"
            jobs = import_from_boss(keyword, city, 9222)

            if not jobs:
                self._show_result(f"未找到 '{keyword}' 相关职位")
                return

            # Save jobs
            root = Path(self.state_dir)
            raw_dir = jobs_raw_dir(root)
            raw_dir.mkdir(parents=True, exist_ok=True)

            state = load_state(root)

            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            for i, job in enumerate(jobs):
                slug = re.sub(r"[^a-z0-9]+", "-", job["title"].lower()).strip("-")[:40]
                job_id = f"{ts}-boss-{i:03d}-{slug}"
                raw_path = raw_dir / f"{job_id}.json"
                raw_path.write_text(json.dumps(job, indent=2, ensure_ascii=False) + "\n")
                state["jobs"][job_id] = {
                    "title": job["title"],
                    "company": job["company"],
                    "location": job.get("city_code", city),
                    "status": "imported",
                    "source": "boss_zhipin",
                    "keyword": keyword,
                    "link": job.get("link", ""),
                }

            save_state(root, state)
            self._show_result(f"✅ 搜索到 {len(jobs)} 个职位并已导入")
        except Exception as e:
            self._show_result(f"❌ 搜索失败: {e}", error=True)

    def _show_result(self, msg: str, error: bool = False):
        widget = self.query_one("#result-area")
        style = "color: red;" if error else "color: green;"
        widget.update(f"[{style}]{msg}[/{style}]" if error else f"[green]{msg}[/green]")
