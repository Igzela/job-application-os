"""Shared page extraction contracts and diagnostics."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


PageState = Literal[
    "normal",
    "login_required",
    "verification_required",
    "access_limited",
    "empty",
    "page_shape_changed",
]


@dataclass(frozen=True)
class PageClassification:
    """Stable page-state signal used by import, loop, and submit reports."""

    state: PageState
    reason: str = ""
    recovery: str = ""
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(asdict(self))


@dataclass(frozen=True)
class SelectorAttempt:
    """One selector probe made by an extractor."""

    extractor: str
    selector: str
    count: int
    purpose: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractedJobCard:
    """Normalized job card extracted from a listing page."""

    job_id: str = ""
    title: str = ""
    company: str = ""
    salary: str = ""
    location: str = ""
    tags: list[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _drop_empty(asdict(self))


@dataclass(frozen=True)
class ExtractionDiagnostics:
    """Diagnostics explaining which extractor handled a page and why."""

    extractor: str
    page_state: PageState
    scrapling_available: bool
    fallback_used: bool = False
    selector_attempts: list[SelectorAttempt] = field(default_factory=list)
    item_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["selector_attempts"] = [
            attempt.to_dict() if hasattr(attempt, "to_dict") else attempt
            for attempt in self.selector_attempts
        ]
        return _drop_empty(data)


@dataclass(frozen=True)
class PageExtractionResult:
    """Complete result for a page extraction pass."""

    jobs: list[ExtractedJobCard]
    classification: PageClassification
    diagnostics: ExtractionDiagnostics

    def to_dict(self) -> dict[str, Any]:
        return {
            "jobs": [job.to_dict() for job in self.jobs],
            "classification": self.classification.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
        }


def _drop_empty(data: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in data.items()
        if value not in ("", None, [], {})
    }
