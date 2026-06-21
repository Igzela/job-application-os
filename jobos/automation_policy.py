"""Conservative policy controls for live browser automation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .runtime_state import load_json_state, update_json_state


CHINA_TZ = timezone(timedelta(hours=8))


def is_business_hours() -> bool:
    """Return whether live actions are allowed by the local time policy."""
    hour = datetime.now(CHINA_TZ).hour
    return 8 <= hour < 22


def is_active_hours() -> bool:
    """Return whether message polling is allowed by the local time policy."""
    hour = datetime.now(CHINA_TZ).hour
    return 9 <= hour < 21


class DailyRateLimiter:
    """Persist and enforce daily submission and reply limits."""

    def __init__(
        self,
        max_submissions: int = 20,
        max_replies: int = 30,
        state_file: str | Path | None = None,
    ) -> None:
        self.max_submissions = max_submissions
        self.max_replies = max_replies
        self.state_file = Path(state_file) if state_file is not None else None
        self._load()

    def _load(self) -> None:
        if self.state_file:
            data = load_json_state(
                self.state_file,
                {
                    "date": datetime.now(CHINA_TZ).strftime("%Y-%m-%d"),
                    "submissions": 0,
                    "replies": 0,
                },
            )
            self.today = data.get("date", "")
            self.submissions = int(data.get("submissions", 0))
            self.replies = int(data.get("replies", 0))
        else:
            self.today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")
            self.submissions = 0
            self.replies = 0

    def _check_day(self) -> None:
        today = datetime.now(CHINA_TZ).strftime("%Y-%m-%d")
        if today != self.today:
            self.today = today
            self.submissions = 0
            self.replies = 0

    def can_submit(self) -> bool:
        self._check_day()
        return self.submissions < self.max_submissions

    def can_reply(self) -> bool:
        self._check_day()
        return self.replies < self.max_replies

    def record_submission(self) -> None:
        self._check_day()
        if self.state_file is None:
            self.submissions += 1
            return

        def increment(state: dict) -> None:
            if state.get("date") != self.today:
                state.update(date=self.today, submissions=0, replies=0)
            state["submissions"] = int(state.get("submissions", 0)) + 1

        state = update_json_state(self.state_file, {}, increment)
        self.submissions = state["submissions"]
        self.replies = int(state.get("replies", 0))

    def record_reply(self) -> None:
        self._check_day()
        if self.state_file is None:
            self.replies += 1
            return

        def increment(state: dict) -> None:
            if state.get("date") != self.today:
                state.update(date=self.today, submissions=0, replies=0)
            state["replies"] = int(state.get("replies", 0)) + 1

        state = update_json_state(self.state_file, {}, increment)
        self.replies = state["replies"]
        self.submissions = int(state.get("submissions", 0))
