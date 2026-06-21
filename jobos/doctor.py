"""Workspace health checks for Job Application OS."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .application_pack import MANIFEST_FILENAME, load_application_pack
from .run_ledger import list_run_ledgers
from .runtime_state import load_json_state
from .workspace import (
    APPLICATIONS_DIR,
    JOBS_DIR,
    PREDICTIONS_DIR,
    RETROS_DIR,
    load_state,
    state_path,
)


@dataclass(frozen=True)
class DoctorCheck:
    label: str
    ok: bool
    detail: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class DoctorReport:
    checks: list[DoctorCheck]

    @property
    def all_ok(self) -> bool:
        return all(
            check.ok or check.severity == "warning"
            for check in self.checks
        )


def _pack_checks(root: Path) -> list[DoctorCheck]:
    applications = root / APPLICATIONS_DIR
    failures: list[str] = []
    legacy: list[str] = []
    if applications.is_dir():
        for pack_dir in sorted(path for path in applications.iterdir() if path.is_dir()):
            if not (pack_dir / MANIFEST_FILENAME).exists():
                legacy.append(pack_dir.name)
                continue
            try:
                load_application_pack(
                    pack_dir,
                    require_manifest=True,
                    verify_sources=True,
                )
            except (OSError, ValueError) as exc:
                failures.append(f"{pack_dir.name}: {exc}")
    return [
        DoctorCheck(
            "Application Pack integrity",
            not failures,
            "; ".join(failures),
        ),
        DoctorCheck(
            "Application Pack manifests",
            not legacy,
            f"Legacy packs: {', '.join(legacy)}" if legacy else "",
            severity="warning",
        ),
    ]


def _run_ledger_check(root: Path) -> DoctorCheck:
    runs_root = root / "pipeline_runs"
    limit = sum(1 for path in runs_root.iterdir() if path.is_dir()) if runs_root.is_dir() else 0
    corrupt = [
        run.run_id
        for run in list_run_ledgers(root, limit=limit)
        if run.status == "corrupt"
    ]
    return DoctorCheck(
        "Run Ledger integrity",
        not corrupt,
        f"Corrupt runs: {', '.join(corrupt)}" if corrupt else "",
        severity="warning",
    )


def _runtime_state_check(root: Path) -> DoctorCheck:
    state_files = {
        ".daily_limits.json": {"date": "", "submissions": 0, "replies": 0},
        ".job-contact-state.json": {"jobs": {}, "urls": {}, "company_titles": {}},
        "auto_reply_state.json": {
            "replied": {},
            "stats": {"total_replied": 0, "total_skipped": 0},
        },
    }
    failures: list[str] = []
    for filename, default in state_files.items():
        path = root / filename
        if not path.exists():
            continue
        try:
            load_json_state(path, default)
        except (OSError, ValueError) as exc:
            failures.append(f"{filename}: {exc}")
    return DoctorCheck(
        "Runtime state integrity",
        not failures,
        "; ".join(failures),
    )


def _profile_consistency_check(root: Path) -> DoctorCheck:
    from .profile_loader import load_profile, validate_profile_consistency

    try:
        errors = validate_profile_consistency(load_profile(root))
    except (OSError, ValueError, TypeError) as exc:
        errors = [str(exc)]
    return DoctorCheck(
        "Profile identity consistency",
        not errors,
        "; ".join(errors),
    )


def run_doctor(
    state_dir: str | Path,
    *,
    version_info: Sequence[int] | None = None,
    version_text: str | None = None,
) -> DoctorReport:
    """Check whether a workspace has the files needed for local workflows."""
    root = Path(state_dir)
    version_info = version_info or sys.version_info
    version_text = version_text or sys.version.split()[0]
    checks: list[DoctorCheck] = []

    required_dirs = [
        "profile",
        JOBS_DIR,
        PREDICTIONS_DIR,
        APPLICATIONS_DIR,
        RETROS_DIR,
        "rubrics",
    ]
    for directory in required_dirs:
        checks.append(DoctorCheck(f"Directory {directory}/", (root / directory).is_dir()))

    for name in ("base.yaml", "skills.yaml", "availability.yaml"):
        checks.append(
            DoctorCheck(
                f"Profile file profile/{name}",
                (root / "profile" / name).exists(),
            )
        )
    checks.append(_profile_consistency_check(root))

    workspace_state_path = state_path(root)
    if workspace_state_path.exists():
        try:
            state = load_state(root)
        except (OSError, ValueError) as exc:
            checks.append(
                DoctorCheck("Workspace state integrity", False, str(exc))
            )
            checks.append(DoctorCheck("Active rubric (state unreadable)", False))
        else:
            checks.append(DoctorCheck("Workspace state integrity", True))
            active = state.get("active_rubric")
            rubric_ok = bool(active and (root / "rubrics" / f"{active}.md").exists())
            checks.append(DoctorCheck(f"Active rubric ({active})", rubric_ok))
    else:
        checks.append(DoctorCheck("Workspace state integrity", False, "Missing .job-state.json"))
        checks.append(DoctorCheck("Active rubric (no state file)", False))

    checks.extend(_pack_checks(root))
    checks.append(_run_ledger_check(root))
    checks.append(_runtime_state_check(root))

    mock_ok = (
        (root / "tests" / "fixtures" / "mock_form.html").exists()
        or (root / "adapters" / "local_mock_form" / "application_form.html").exists()
    )
    checks.append(DoctorCheck("Mock form fixture", mock_ok))

    py_ok = tuple(version_info[:2]) >= (3, 11)
    checks.append(DoctorCheck(f"Python >= 3.11 (current: {version_text})", py_ok))
    checks.append(
        DoctorCheck("Live BOSS mode requires explicit confirmation", True)
    )

    return DoctorReport(checks=checks)
