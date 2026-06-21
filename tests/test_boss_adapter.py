"""Tests for public BOSS browser adapter helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jobos import submitter
from jobos.boss_adapter import (
    BossSubmitResult,
    click_chat_button,
    click_send,
    fill_greeting,
    find_boss_tab,
    human_delay,
    classify_page_submit_success,
    submit_boss_application,
    take_screenshot,
)


def test_submitter_private_helper_aliases_delegate_to_public_adapter() -> None:
    assert submitter._human_delay is human_delay
    assert submitter._find_boss_tab is find_boss_tab
    assert submitter._click_chat_button is click_chat_button
    assert submitter._fill_greeting is fill_greeting
    assert submitter._click_send is click_send
    assert submitter._take_screenshot is take_screenshot


def test_find_boss_tab_returns_first_zhipin_page() -> None:
    non_boss = MagicMock()
    non_boss.url = "https://example.com"
    boss = MagicMock()
    boss.url = "https://www.zhipin.com/web/geek/job_detail/123.html"
    context = MagicMock()
    context.pages = [non_boss, boss]

    assert find_boss_tab(context) is boss


def test_take_screenshot_returns_none_on_failure(tmp_path: Path) -> None:
    page = MagicMock()
    page.screenshot.side_effect = RuntimeError("screenshot failed")

    assert take_screenshot(page, tmp_path / "shot.png") is None


def test_classify_page_submit_success_uses_html_signals() -> None:
    page = MagicMock()
    page.content.return_value = "<html><body>聊天记录：你好 已发送 星河科技</body></html>"
    page.locator.return_value.count.return_value = 0

    success = classify_page_submit_success(page, "你好", "星河科技")

    assert success.success
    assert "message_echo" in success.signals
    assert "sent_state" in success.signals
    assert "expected_company_chat" in success.signals


def test_classify_page_submit_success_uses_visible_sent_state() -> None:
    page = MagicMock()
    page.content.return_value = "<html><body>聊天窗口</body></html>"
    locator = page.locator.return_value
    locator.count.return_value = 1
    locator.first.is_visible.return_value = True

    success = classify_page_submit_success(page, "你好", "")

    assert success.success
    assert success.signals == ["sent_state"]
    assert success.diagnostics["visible_sent_state"] is True


def test_orchestrator_does_not_import_submitter_private_helpers() -> None:
    source = Path("jobos/orchestrator.py").read_text(encoding="utf-8")

    assert "from .submitter import _click_chat_button" not in source
    assert "from .submitter import _click_send" not in source
    assert "from .submitter import _fill_greeting" not in source
    assert "from .submitter import _take_screenshot" not in source


def test_submit_boss_application_owns_attempt_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    page = MagicMock()
    page.url = "https://www.zhipin.com/job/1"
    page.title.return_value = "BOSS job"
    page.content.return_value = "<html><body><button>立即沟通</button></body></html>"
    monkeypatch.setattr("jobos.boss_adapter.click_chat_button", lambda _page: False)
    monkeypatch.setattr(
        "jobos.boss_adapter.take_screenshot",
        lambda _page, path: str(path),
    )

    result = submit_boss_application(
        page,
        job_id="j1",
        job_url=page.url,
        company="星河科技",
        greeting="你好",
        state_dir=tmp_path,
        dry_run=False,
        confirm=True,
        validated=True,
        navigate=False,
    )

    assert isinstance(result, BossSubmitResult)
    assert result.status == "no_chat_button"
    attempt = json.loads(Path(result.attempt_path).read_text(encoding="utf-8"))
    assert attempt["error_class"] == "no_chat_button"
    assert attempt["page_diagnostics"]


def test_submit_boss_application_requires_validation_before_live_send(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="validated"):
        submit_boss_application(
            MagicMock(),
            job_id="j1",
            job_url="https://www.zhipin.com/job/1",
            company="星河科技",
            greeting="你好",
            state_dir=tmp_path,
            dry_run=False,
            confirm=True,
            validated=False,
        )


def test_submit_paths_delegate_to_high_level_boss_adapter() -> None:
    submitter_source = Path("jobos/submitter.py").read_text(encoding="utf-8")
    orchestrator_source = Path("jobos/orchestrator.py").read_text(encoding="utf-8")

    assert "submit_boss_application(" in submitter_source
    assert "submit_boss_application(" in orchestrator_source


def test_browser_runtime_has_no_fingerprint_spoofing() -> None:
    browser_source = Path("jobos/browser.py").read_text(encoding="utf-8")
    policy_source = Path("jobos/anti_detect.py").read_text(encoding="utf-8")

    assert "patchright" not in browser_source
    assert "AutomationControlled" not in browser_source
    assert "user_agent" not in policy_source
    assert "geolocation" not in policy_source
