import json
from pathlib import Path

from .base import LLMAdapter


class Conversation:
    """管理多轮对话上下文"""

    def __init__(self, llm: LLMAdapter, history_path: str | Path | None = None):
        self.llm = llm
        self.messages: list[dict] = []
        self.history_path = Path(history_path) if history_path else None
        if self.history_path and self.history_path.exists():
            self._load_history()

    def chat(self, user_msg: str, system: str = "") -> str:
        """发送用户消息，获取回复"""
        self.messages.append({"role": "user", "content": user_msg})
        reply = self.llm.chat(self.messages, system=system)
        self.messages.append({"role": "assistant", "content": reply})
        if self.history_path:
            self._save_history()
        return reply

    def add_system(self, msg: str):
        """添加系统消息"""
        self.messages.append({"role": "system", "content": msg})

    def clear(self):
        """清空对话历史"""
        self.messages.clear()

    def _save_history(self):
        if self.history_path:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_path, "w") as f:
                json.dump(self.messages, f, ensure_ascii=False, indent=2)

    def _load_history(self):
        try:
            with open(self.history_path) as f:
                self.messages = json.load(f)
        except (json.JSONDecodeError, OSError):
            self.messages = []
