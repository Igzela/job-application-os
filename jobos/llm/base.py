from typing import Protocol, Any


class LLMAdapter(Protocol):
    """统一的LLM接口，支持Anthropic和OpenAI协议"""

    def chat(self, messages: list[dict], system: str = "", temperature: float = 0.7) -> str:
        """发送对话消息，返回文本响应"""
        ...

    def summarize_jd(self, jd_text: str) -> dict:
        """分析JD，提取关键信息"""
        ...

    def improve_greeting(self, greeting: str, context: dict) -> str:
        """优化招呼语"""
        ...

    def improve_cover_letter(self, cover_letter: str, context: dict) -> str:
        """优化求职信"""
        ...

    def rewrite_resume_bullet(self, bullet: str, context: dict) -> str:
        """重写简历要点"""
        ...

    def explain_score(self, scores: dict, job_data: dict) -> str:
        """解释评分结果"""
        ...
