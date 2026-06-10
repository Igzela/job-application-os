"""Tests for LLM adapter mock mode — deterministic, no network calls."""

import pytest

from jobos.llm.mock import MockLLMAdapter
from jobos.llm.provider import get_llm_adapter


class TestMockLLMAdapter:
    def test_deterministic(self):
        """Calling the same method twice returns identical results."""
        m = MockLLMAdapter()
        jd = "Software Engineer Intern at Acme Labs. Requirements: Python, React."
        r1 = m.summarize_jd(jd)
        r2 = m.summarize_jd(jd)
        assert r1 == r2

    def test_summarize_jd_returns_dict(self):
        m = MockLLMAdapter()
        result = m.summarize_jd("Some JD text")
        assert isinstance(result, dict)
        assert "summary" in result
        assert "key_skills" in result
        assert "seniority" in result

    def test_improve_greeting_passthrough(self):
        m = MockLLMAdapter()
        greeting = "Hello, I am interested in this position."
        assert m.improve_greeting(greeting, {}) == greeting

    def test_improve_cover_letter_passthrough(self):
        m = MockLLMAdapter()
        letter = "Dear Hiring Team, I am writing to apply."
        assert m.improve_cover_letter(letter, {}) == letter

    def test_rewrite_bullet_passthrough(self):
        m = MockLLMAdapter()
        bullet = "Built a Chrome extension with Vue 3"
        assert m.rewrite_resume_bullet(bullet, {}) == bullet

    def test_explain_score_contains_dimensions(self):
        m = MockLLMAdapter()
        scores = {"fit": 7.0, "evidence": 6.5, "final_score": 5.8}
        result = m.explain_score(scores, {})
        assert "fit" in result
        assert "evidence" in result
        assert "final_score" in result


class TestProvider:
    def test_get_adapter_returns_mock_by_default(self):
        adapter = get_llm_adapter()
        assert isinstance(adapter, MockLLMAdapter)

    def test_get_adapter_mock_config(self):
        adapter = get_llm_adapter({"provider": "mock"})
        assert isinstance(adapter, MockLLMAdapter)

    def test_get_adapter_unsupported_raises(self):
        with pytest.raises(NotImplementedError):
            get_llm_adapter({"provider": "openai"})
