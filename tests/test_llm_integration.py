"""Tests for LLM integration: adapters, conversation, job analyzer, orchestrator."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from jobos.llm.mock import MockLLMAdapter
from jobos.llm.conversation import Conversation
from jobos.llm.prompts import INTRO_SYSTEM, JOB_MATCH_SYSTEM, GREETING_SYSTEM, SCAM_CHECK_SYSTEM
from jobos.llm.job_analyzer import analyze_match, generate_greeting, check_scam, explain_scores
from jobos.llm.provider import get_llm_adapter, _read_claude_config


class TestReadClaudeConfig:
    def test_reads_existing_config(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "settings.json"
        config_file.write_text(json.dumps({
            "env": {
                "ANTHROPIC_AUTH_TOKEN": "test-token-123",
                "ANTHROPIC_BASE_URL": "https://api.example.com/anthropic",
            }
        }))
        with patch("jobos.llm.provider.Path.home", return_value=tmp_path):
            result = _read_claude_config()
        assert result["api_key"] == "test-token-123"
        assert result["base_url"] == "https://api.example.com/anthropic"

    def test_returns_empty_on_missing(self, tmp_path):
        with patch("jobos.llm.provider.Path.home", return_value=tmp_path):
            result = _read_claude_config()
        assert result == {}


class TestConversation:
    def test_chat_appends_messages(self):
        llm = MockLLMAdapter()
        conv = Conversation(llm)
        reply = conv.chat("hello")
        assert len(conv.messages) == 2
        assert conv.messages[0]["role"] == "user"
        assert conv.messages[1]["role"] == "assistant"

    def test_chat_with_system(self):
        llm = MockLLMAdapter()
        conv = Conversation(llm)
        reply = conv.chat("hello", system="Be helpful")
        assert isinstance(reply, str)

    def test_clear(self):
        llm = MockLLMAdapter()
        conv = Conversation(llm)
        conv.chat("hello")
        conv.clear()
        assert len(conv.messages) == 0

    def test_save_and_load_history(self, tmp_path):
        history_path = tmp_path / "history.json"
        llm = MockLLMAdapter()

        conv = Conversation(llm, history_path)
        conv.chat("hello")

        assert history_path.exists()

        conv2 = Conversation(llm, history_path)
        assert len(conv2.messages) == 2

    def test_add_system(self):
        llm = MockLLMAdapter()
        conv = Conversation(llm)
        conv.add_system("system message")
        assert conv.messages[0]["role"] == "system"


class TestPrompts:
    def test_intro_system_has_chinese(self):
        assert "求职" in INTRO_SYSTEM

    def test_job_match_returns_json(self):
        assert "JSON" in JOB_MATCH_SYSTEM

    def test_greeting_has_requirements(self):
        assert "100" in GREETING_SYSTEM

    def test_scam_check_has_red_lines(self):
        assert "A1" in SCAM_CHECK_SYSTEM
        assert "B1" in SCAM_CHECK_SYSTEM


class TestJobAnalyzer:
    def test_analyze_match_returns_dict(self):
        llm = MockLLMAdapter()
        job = {"title": "Python Dev", "skills": ["Python", "Django"]}
        profile = {"skills": {"programming_languages": [{"name": "Python"}]}}
        result = analyze_match(llm, job, profile)
        assert isinstance(result, dict)

    def test_generate_greeting_returns_string(self):
        llm = MockLLMAdapter()
        job = {"title": "Backend Dev", "company": "TestCo"}
        profile = {"skills": {"programming_languages": [{"name": "Python"}]}}
        result = generate_greeting(llm, job, profile)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_check_scam_returns_dict(self):
        llm = MockLLMAdapter()
        result = check_scam(llm, "Normal job description with Python requirements")
        assert isinstance(result, dict)
        assert "is_scam" in result

    def test_explain_scores_returns_string(self):
        llm = MockLLMAdapter()
        scores = {"total_score": 75, "breakdown": {"skill_match": 80}}
        job = {"title": "Dev"}
        profile = {"name": "Test"}
        result = explain_scores(llm, scores, job, profile)
        assert isinstance(result, str)


class TestOrchestrator:
    def test_no_profile_returns_error(self, tmp_path):
        from jobos.orchestrator import run_full_pipeline
        result = run_full_pipeline(str(tmp_path))
        assert result.get("error") == "no_profile"


class TestCLICommands:
    def test_start_help(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-c", "from jobos.cli import main; import sys; sys.argv=['job','start','--help']; main()"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "keyword" in result.stdout.lower() or "search" in result.stdout.lower()

    def test_chat_help(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-c", "from jobos.cli import main; import sys; sys.argv=['job','chat','--help']; main()"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_analyze_help(self):
        import subprocess
        result = subprocess.run(
            ["python3", "-c", "from jobos.cli import main; import sys; sys.argv=['job','analyze','--help']; main()"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--job" in result.stdout


class TestLLMAdapterInterface:
    def test_mock_implements_all_methods(self):
        m = MockLLMAdapter()
        assert hasattr(m, "chat")
        assert hasattr(m, "summarize_jd")
        assert hasattr(m, "improve_greeting")
        assert hasattr(m, "improve_cover_letter")
        assert hasattr(m, "rewrite_resume_bullet")
        assert hasattr(m, "explain_score")

    def test_anthropic_adapter_has_all_methods(self):
        from jobos.llm.anthropic_adapter import AnthropicAdapter
        a = AnthropicAdapter(api_key="test", base_url="https://test.com")
        assert hasattr(a, "chat")
        assert hasattr(a, "summarize_jd")
        assert hasattr(a, "improve_greeting")
        assert hasattr(a, "improve_cover_letter")
        assert hasattr(a, "rewrite_resume_bullet")
        assert hasattr(a, "explain_score")

    def test_openai_adapter_has_all_methods(self):
        from jobos.llm.openai_adapter import OpenAIAdapter
        a = OpenAIAdapter(api_key="test", base_url="https://test.com")
        assert hasattr(a, "chat")
        assert hasattr(a, "summarize_jd")
        assert hasattr(a, "improve_greeting")
        assert hasattr(a, "improve_cover_letter")
        assert hasattr(a, "rewrite_resume_bullet")
        assert hasattr(a, "explain_score")
