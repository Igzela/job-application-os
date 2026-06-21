"""Profile editor screen."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Static, TextArea


class ProfileScreen(Screen):
    """档案编辑"""

    CSS = """
    #profile-section {
        height: 1fr;
        padding: 1;
    }
    .profile-tab {
        height: 1fr;
    }
    #save-status {
        height: 1;
        margin: 1 0;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir
        self.current_file = "base.yaml"

    def compose(self) -> ComposeResult:
        yield Static("👤 求职档案编辑", classes="section-title")

        with Vertical(id="profile-section"):
            yield Static("选择文件: [1]base.yaml  [2]skills.yaml  [3]availability.yaml  [4]evidence_bank.md",
                         id="file-tabs")
            yield TextArea(id="profile-editor")
            yield Button("保存", id="btn-save", variant="primary")
            yield Static("", id="save-status")

    def on_mount(self):
        self._load_file("base.yaml")

    def on_key(self, event):
        if event.key == "1":
            self._load_file("base.yaml")
        elif event.key == "2":
            self._load_file("skills.yaml")
        elif event.key == "3":
            self._load_file("availability.yaml")
        elif event.key == "4":
            self._load_file("evidence_bank.md")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-save":
            self._save_file()

    def _load_file(self, filename: str):
        self.current_file = filename
        path = Path(self.state_dir) / "profile" / filename
        if path.exists():
            content = path.read_text()
        else:
            content = f"# {filename}\n\n"
        self.query_one("#profile-editor").load_text(content)
        self.query_one("#save-status").update(f"📂 {filename}")

    def _save_file(self):
        path = Path(self.state_dir) / "profile" / self.current_file
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.query_one("#profile-editor").text
        path.write_text(content)
        self.query_one("#save-status").update(f"✅ 已保存 {self.current_file}")
