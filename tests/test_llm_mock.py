"""Tests for LLM adapter mock mode — deterministic, no network calls."""

import os
import pytest
from unittest.mock import patch

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

    def test_chat_returns_string(self):
        m = MockLLMAdapter()
        result = m.chat([{"role": "user", "content": "hello"}])
        assert isinstance(result, str)


class TestProvider:
    def test_get_adapter_returns_mock_by_default(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "jobos.config.load_env_values",
            return_value={},
        ):
            adapter = get_llm_adapter({"use_local_config": False})
            assert isinstance(adapter, MockLLMAdapter)

    def test_get_adapter_mock_config(self):
        adapter = get_llm_adapter({"provider": "mock"})
        assert isinstance(adapter, MockLLMAdapter)

    def test_get_adapter_explicit_api_key_returns_real(self):
        adapter = get_llm_adapter({
            "provider": "anthropic",
            "api_key": "test-key",
            "base_url": "https://api.anthropic.com",
        })
        from jobos.llm.anthropic_adapter import AnthropicAdapter
        assert isinstance(adapter, AnthropicAdapter)

    def test_get_adapter_openai_returns_real(self):
        adapter = get_llm_adapter({
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "https://api.openai.com",
        })
        from jobos.llm.openai_adapter import OpenAIAdapter
        assert isinstance(adapter, OpenAIAdapter)

    def test_get_adapter_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_llm_adapter({"provider": "unknown", "api_key": "k", "base_url": "http://x"})

    def test_get_adapter_env_fallback(self):
        with patch.dict(os.environ, {"JOBOS_PROVIDER": "mock"}):
            adapter = get_llm_adapter({"use_local_config": False})
            assert isinstance(adapter, MockLLMAdapter)

    def test_get_adapter_does_not_read_claude_config_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "jobos.config.load_env_values",
            return_value={},
        ), patch("jobos.llm.provider._read_claude_config") as read_claude:
            adapter = get_llm_adapter({"use_local_config": False})

        assert isinstance(adapter, MockLLMAdapter)
        read_claude.assert_not_called()

    def test_process_environment_overrides_yaml_config(self):
        with patch.dict(os.environ, {"JOBOS_PROVIDER": "mock"}), patch(
            "jobos.config.load_config",
            return_value={
                "llm": {
                    "provider": "anthropic",
                    "api_key_env": "JOBOS_API_KEY",
                    "base_url": "https://api.anthropic.com",
                }
            },
        ):
            adapter = get_llm_adapter()

        assert isinstance(adapter, MockLLMAdapter)
