"""LLM Chat and Analysis screens."""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, RadioSet, RadioButton, Static

from jobos.workspace import load_state


class LLMChatScreen(Screen):
    """AI对话界面"""

    CSS = """
    #chat-history {
        height: 1fr;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }
    #chat-input-row {
        height: 3;
        margin: 1 0;
    }
    #chat-input {
        width: 1fr;
    }
    #provider-row {
        height: auto;
        margin: 0 0 1 0;
    }
    .chat-msg {
        margin: 0 0 1 0;
    }
    .chat-user {
        color: $accent;
    }
    .chat-ai {
        color: $success;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir
        self.llm = None
        self.conv = None

    def compose(self) -> ComposeResult:
        yield Static("🤖 AI助手", classes="section-title")

        with Horizontal(id="provider-row"):
            yield Label("Provider: ")
            yield RadioSet(
                RadioButton("Anthropic", value=True, id="p-anthropic"),
                RadioButton("OpenAI", id="p-openai"),
                RadioButton("Mock", id="p-mock"),
                id="providers",
            )

        yield ScrollableContainer(
            Static("👋 你好！我是求职AI助手。输入消息开始对话。\n", classes="chat-msg chat-ai"),
            id="chat-history",
        )

        with Horizontal(id="chat-input-row"):
            yield Input(placeholder="输入消息...", id="chat-input")
            yield Button("发送", id="btn-send", variant="primary")

    def on_mount(self):
        self._init_llm()

    def _init_llm(self):
        try:
            from jobos.llm.provider import get_llm_adapter
            self.llm = get_llm_adapter()

            provider = "mock"
            radio_set = self.query_one("#providers")
            for i, rb in enumerate(radio_set.query(RadioButton)):
                if rb.value:
                    provider = ["anthropic", "openai", "mock"][i]
                    break

            if provider != "mock":
                self.llm = get_llm_adapter({"provider": provider})

            from jobos.llm.conversation import Conversation
            history_path = Path(self.state_dir) / "profile" / "chat_history.json"
            self.conv = Conversation(self.llm, history_path)
        except Exception as e:
            self._append_chat("系统", f"LLM初始化失败: {e}")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-send":
            self._send_message()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "chat-input":
            self._send_message()

    def _send_message(self):
        input_widget = self.query_one("#chat-input")
        text = input_widget.value.strip()
        if not text:
            return

        if text.lower() in ("quit", "exit"):
            self.app.pop_screen()
            return

        self._append_chat("你", text, is_user=True)
        input_widget.value = ""

        if not self.conv:
            self._init_llm()
        if not self.conv:
            return

        try:
            from jobos.llm.prompts import INTRO_SYSTEM
            reply = self.conv.chat(text, system=INTRO_SYSTEM)
            self._append_chat("AI", reply)
        except Exception as e:
            self._append_chat("系统", f"错误: {e}")

    def _append_chat(self, speaker: str, text: str, is_user: bool = False):
        history = self.query_one("#chat-history")
        css_class = "chat-user" if is_user else "chat-ai"
        prefix = "🧑" if is_user else "🤖"
        history.mount(Static(f"{prefix} {speaker}: {text}", classes=f"chat-msg {css_class}"))
        history.scroll_end()


class LLMAnalysisScreen(Screen):
    """职位LLM分析"""

    CSS = """
    #analysis-input {
        margin: 1 0;
    }
    #analysis-result {
        height: 1fr;
        border: solid $primary;
        padding: 1;
        overflow-y: auto;
    }
    """

    def __init__(self, state_dir: str, **kwargs):
        super().__init__(**kwargs)
        self.state_dir = state_dir

    def compose(self) -> ComposeResult:
        yield Static("🤖 AI职位分析", classes="section-title")
        with Horizontal(id="analysis-input"):
            yield Input(placeholder="输入 job_id...", id="job-id-input")
            yield Button("分析", id="btn-analyze", variant="primary")
        yield ScrollableContainer(
            Static("输入job_id后点击分析", id="analysis-result"),
        )

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn-analyze":
            self._analyze_job()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "job-id-input":
            self._analyze_job()

    def _analyze_job(self):
        job_id = self.query_one("#job-id-input").value.strip()
        if not job_id:
            return

        result_widget = self.query_one("#analysis-result")
        result_widget.update("分析中...")

        try:
            from jobos.llm.provider import get_llm_adapter
            from jobos.llm.job_analyzer import analyze_match, check_scam, generate_greeting
            from jobos.profile_loader import load_profile

            llm = get_llm_adapter()
            profile = load_profile(self.state_dir)

            # Load job
            state = load_state(self.state_dir)
            job = state.get("jobs", {}).get(job_id)
            if not job:
                result_widget.update(f"❌ 未找到职位: {job_id}")
                return

            lines = [f"职位: {job.get('title', '?')} @ {job.get('company', '?')}", ""]

            # Scam check
            scam = check_scam(llm, json.dumps(job, ensure_ascii=False))
            risk = scam.get("risk_level", "unknown")
            emoji = {"low": "✅", "medium": "⚠️", "high": "❌"}.get(risk, "❓")
            lines.append(f"🔒 反诈: {emoji} {risk}")
            if scam.get("red_flags"):
                lines.append(f"   红线: {scam['red_flags']}")
            lines.append("")

            # Match
            match = analyze_match(llm, job, profile)
            lines.append(f"📊 匹配: {match.get('total_score', '?')}/100 ({match.get('verdict', '?')})")
            if match.get("strengths"):
                lines.append(f"   优势: {', '.join(match['strengths'])}")
            if match.get("weaknesses"):
                lines.append(f"   劣势: {', '.join(match['weaknesses'])}")
            lines.append("")

            # Greeting
            greeting = generate_greeting(llm, job, profile)
            lines.append(f"✉️ 招呼语:\n{greeting}")

            result_widget.update("\n".join(lines))
        except Exception as e:
            result_widget.update(f"❌ 分析失败: {e}")
