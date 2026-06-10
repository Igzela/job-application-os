from .base import LLMAdapter


class MockLLMAdapter:
    @classmethod
    def create(cls) -> "MockLLMAdapter":
        return cls()

    def summarize_jd(self, jd_text: str) -> dict:
        return {"summary": jd_text[:200], "key_skills": [], "seniority": "intern"}

    def improve_greeting(self, greeting: str, context: dict) -> str:
        return greeting

    def improve_cover_letter(self, cover_letter: str, context: dict) -> str:
        return cover_letter

    def rewrite_resume_bullet(self, bullet: str, context: dict) -> str:
        return bullet

    def explain_score(self, scores: dict, job_data: dict) -> str:
        lines = [f"{key}: {value}" for key, value in scores.items()]
        return "Scores:\n" + "\n".join(lines)
