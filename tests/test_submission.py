"""Tests for shared submit attempt record helpers."""

from __future__ import annotations

import json
from pathlib import Path

from jobos.submission import (
    classify_submit_error,
    new_submit_attempt_record,
    submit_attempt_path,
    submit_attempt_result_update,
    write_submit_attempt,
)


def test_new_submit_attempt_record_has_canonical_shape() -> None:
    record = new_submit_attempt_record(
        job_id="j1",
        url="https://www.zhipin.com/job/1",
        platform="boss",
        mode="dry_run",
        started_at="2026-06-17T00:00:00+00:00",
    )

    assert record == {
        "schema_version": 1,
        "job_id": "j1",
        "url": "https://www.zhipin.com/job/1",
        "platform": "boss",
        "mode": "dry_run",
        "started_at": "2026-06-17T00:00:00+00:00",
        "status": "started",
        "result": None,
        "error": None,
        "error_class": None,
        "screenshot_paths": [],
        "page_state": None,
        "extractor": None,
        "page_diagnostics": [],
        "recovery_signals": [],
    }


def test_submit_attempt_result_update_classifies_error_and_screenshots() -> None:
    update = submit_attempt_result_update(
        submitted=False,
        submitted_at=None,
        fields_filled={},
        page_title=None,
        page_url=None,
        screenshot_path="/tmp/error.png",
        error="Could not find chat button",
        finished_at="2026-06-17T00:01:00+00:00",
    )

    assert update["status"] == "failed"
    assert update["error_class"] == "no_chat_button"
    assert update["screenshot_paths"] == ["/tmp/error.png"]
    assert update["result"]["screenshot_path"] == "/tmp/error.png"


def test_submit_attempt_result_update_can_include_live_submit_metadata() -> None:
    update = submit_attempt_result_update(
        submitted=True,
        submitted_at="2026-06-17T00:01:00+00:00",
        fields_filled={"招呼语": "你好"},
        page_title="BOSS job detail",
        page_url="https://zhipin.com/job/1",
        screenshot_path="/tmp/post.png",
        error=None,
        finished_at="2026-06-17T00:01:01+00:00",
        submit_phase="post_send",
        success_signals=["sent_state"],
        screenshot_paths={"pre_submit": "/tmp/pre.png", "post_submit": "/tmp/post.png"},
    )

    assert update["status"] == "succeeded"
    assert update["screenshot_paths"] == ["/tmp/pre.png", "/tmp/post.png"]
    assert update["result"]["submit_phase"] == "post_send"
    assert update["result"]["success_signals"] == ["sent_state"]
    assert update["result"]["screenshot_paths"] == {
        "pre_submit": "/tmp/pre.png",
        "post_submit": "/tmp/post.png",
    }


def test_submit_attempt_path_uses_workspace_submit_attempts_dir(tmp_path: Path) -> None:
    path = submit_attempt_path(
        tmp_path,
        "j1",
        stamp="20260617T000000000000Z",
    )

    assert path == tmp_path / "applications" / "j1" / "submit_attempts" / "20260617T000000000000Z.json"


def test_write_submit_attempt_writes_json_with_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "attempt.json"
    record = {"job_id": "j1", "status": "started"}

    returned = write_submit_attempt(path, record)

    assert returned == str(path)
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(path.read_text(encoding="utf-8")) == record


def test_classify_submit_error_returns_stable_classes() -> None:
    assert classify_submit_error(None) is None
    assert classify_submit_error("No job URL found") == "no_url"
    assert classify_submit_error("Could not find chat button") == "no_chat_button"
    assert classify_submit_error("textarea missing") == "fill_failed"
    assert classify_submit_error("send failed") == "send_failed"
    assert classify_submit_error("Browser crashed") == "browser_connect_failed"
    assert classify_submit_error("unknown") == "submit_failed"
