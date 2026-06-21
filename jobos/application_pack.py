"""Application pack persistence and integrity verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from .models import ApplicationPack
from .runtime_state import load_json_state, save_json_state


MANIFEST_FILENAME = "manifest.json"
PROFILE_SOURCE_FILENAMES = (
    "base.yaml",
    "education.yaml",
    "skills.yaml",
    "availability.yaml",
    "evidence_bank.md",
)


class PackIntegrityError(ValueError):
    """Raised when an application pack is incomplete or modified."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_record(path: Path) -> dict[str, Any]:
    path = path.resolve()
    data = path.read_bytes()
    return {
        "path": str(path),
        "sha256": _sha256(data),
        "size": len(data),
    }


def _validate_pack_filename(filename: str) -> None:
    if Path(filename).name != filename:
        raise PackIntegrityError(f"Invalid pack filename: {filename}")


def write_pack_manifest(
    pack_dir: str | Path,
    *,
    job_id: str,
    files: Mapping[str, str],
    created_at: str,
    sources: Mapping[str, str | Path] | None = None,
    validation: Mapping[str, Any] | None = None,
) -> Path:
    """Write a manifest for text files already persisted in ``pack_dir``."""
    pack_dir = Path(pack_dir)
    file_records: dict[str, dict[str, Any]] = {}
    for filename in files:
        _validate_pack_filename(filename)
        path = pack_dir / filename
        data = path.read_bytes()
        file_records[filename] = {
            "sha256": _sha256(data),
            "size": len(data),
        }
    source_records: dict[str, dict[str, Any]] = {}
    for name, path in (sources or {}).items():
        source_path = Path(path)
        if not source_path.is_file():
            raise PackIntegrityError(f"Application pack source missing: {name}")
        source_records[name] = _source_record(source_path)
    manifest_path = pack_dir / MANIFEST_FILENAME
    save_json_state(
        manifest_path,
        {
            "job_id": job_id,
            "created_at": created_at,
            "files": file_records,
            "sources": source_records,
            "validation": dict(validation or {}),
        },
    )
    return manifest_path


def write_application_pack(
    pack_dir: str | Path,
    pack: ApplicationPack,
    *,
    sources: Mapping[str, str | Path] | None = None,
    validation: Mapping[str, Any] | None = None,
) -> Path:
    """Persist pack text files and their integrity manifest."""
    pack_dir = Path(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in pack.files.items():
        _validate_pack_filename(filename)
        (pack_dir / filename).write_text(content, encoding="utf-8")
    return write_pack_manifest(
        pack_dir,
        job_id=pack.job_id,
        files=pack.files,
        created_at=pack.created_at,
        sources=sources,
        validation=validation,
    )


def workspace_pack_sources(
    state_dir: str | Path,
    job_id: str,
) -> dict[str, Path]:
    """Return source files that determine a generated workspace Pack."""
    root = Path(state_dir)
    sources: dict[str, Path] = {}

    for suffix in (".yaml", ".json"):
        job_source = root / "jobs" / "normalized" / f"{job_id}{suffix}"
        if job_source.is_file():
            sources["job"] = job_source
            break

    profile_dir = root / "profile"
    for filename in PROFILE_SOURCE_FILENAMES:
        source = profile_dir / filename
        if source.is_file():
            sources[f"profile/{source.stem}"] = source

    prediction_files = sorted((root / "predictions").glob(f"{job_id}_v*.json"))
    if prediction_files:
        sources["prediction"] = prediction_files[-1]

    return sources


def load_application_pack(
    pack_dir: str | Path,
    *,
    job_id: str | None = None,
    require_manifest: bool = False,
    verify_sources: bool = False,
) -> ApplicationPack:
    """Load a pack and verify manifest-listed files and optional sources."""
    pack_dir = Path(pack_dir)
    if not pack_dir.is_dir():
        if require_manifest:
            raise PackIntegrityError(f"Application pack manifest missing: {pack_dir}")
        return ApplicationPack(job_id=job_id or pack_dir.name, files={})
    manifest_path = pack_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        if require_manifest:
            raise PackIntegrityError(f"Application pack manifest missing: {pack_dir}")
        files = {
            path.name: path.read_text(encoding="utf-8")
            for path in pack_dir.iterdir()
            if path.is_file() and path.suffix in {".md", ".txt"}
        }
        return ApplicationPack(job_id=job_id or pack_dir.name, files=files)

    manifest = load_json_state(manifest_path, {})
    manifest_job_id = str(manifest.get("job_id") or job_id or pack_dir.name)
    if job_id and manifest_job_id != job_id:
        raise PackIntegrityError(
            f"Application pack job_id mismatch: {manifest_job_id} != {job_id}"
        )
    records = manifest.get("files")
    if not isinstance(records, dict):
        raise PackIntegrityError(f"Invalid application pack manifest: {manifest_path}")

    if verify_sources:
        source_records = manifest.get("sources")
        if not isinstance(source_records, dict) or not source_records:
            raise PackIntegrityError(
                f"Invalid application pack source records: {manifest_path}"
            )
        for name, record in source_records.items():
            if not isinstance(record, dict):
                raise PackIntegrityError(
                    f"Invalid application pack source record: {name}"
                )
            source_path = Path(str(record.get("path") or ""))
            if not source_path.is_file():
                raise PackIntegrityError(
                    f"Application pack source missing: {name}"
                )
            if _sha256(source_path.read_bytes()) != record.get("sha256"):
                raise PackIntegrityError(
                    f"Application pack source changed: {name}"
                )

    files: dict[str, str] = {}
    for filename, record in records.items():
        try:
            _validate_pack_filename(str(filename))
        except PackIntegrityError as exc:
            raise PackIntegrityError(f"Invalid pack file record: {filename}") from exc
        if not isinstance(record, dict):
            raise PackIntegrityError(f"Invalid pack file record: {filename}")
        path = pack_dir / filename
        if not path.is_file():
            raise PackIntegrityError(f"Application pack file missing: {filename}")
        data = path.read_bytes()
        if _sha256(data) != record.get("sha256"):
            raise PackIntegrityError(f"Application pack file changed: {filename}")
        files[filename] = data.decode("utf-8")

    return ApplicationPack(
        job_id=manifest_job_id,
        created_at=str(manifest.get("created_at") or ""),
        files=files,
    )


def _validation_summary(
    validation: Any,
    *,
    source: str,
) -> dict[str, int]:
    if not isinstance(validation, Mapping):
        raise PackIntegrityError(
            f"Invalid application pack validation summary: {source}"
        )
    summary: dict[str, int] = {}
    for key in ("supported", "weak", "unsupported"):
        value = validation.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PackIntegrityError(
                f"Invalid application pack validation count {key}: {source}"
            )
        summary[key] = value
    return summary


def load_live_application_pack(
    pack_dir: str | Path,
    *,
    job_id: str,
    expected_validation: Mapping[str, Any],
) -> ApplicationPack:
    """Load a source-verified Pack and enforce its persisted validation."""
    pack_dir = Path(pack_dir)
    pack = load_application_pack(
        pack_dir,
        job_id=job_id,
        require_manifest=True,
        verify_sources=True,
    )
    manifest_path = pack_dir / MANIFEST_FILENAME
    manifest = load_json_state(manifest_path, {})
    actual = _validation_summary(
        manifest.get("validation"),
        source=str(manifest_path),
    )
    if actual["unsupported"] != 0:
        raise PackIntegrityError(
            "Live submission blocked by Application Pack unsupported claims: "
            f"{actual['unsupported']}"
        )
    expected = _validation_summary(
        expected_validation,
        source="workspace state",
    )
    if actual != expected:
        raise PackIntegrityError(
            "Application Pack validation mismatch with workspace state"
        )
    return pack


def update_pack_validation(
    pack_dir: str | Path,
    *,
    job_id: str,
    validation: Mapping[str, Any],
    sources: Mapping[str, str | Path] | None = None,
) -> None:
    """Persist validation summary, creating a manifest for a legacy pack."""
    pack_dir = Path(pack_dir)
    manifest_path = pack_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        pack = load_application_pack(pack_dir, job_id=job_id)
        write_application_pack(
            pack_dir,
            pack,
            sources=sources,
            validation=validation,
        )
        return
    manifest = load_json_state(manifest_path, {})
    manifest["validation"] = dict(validation)
    if sources is not None:
        manifest["sources"] = {
            name: _source_record(Path(path))
            for name, path in sources.items()
        }
    save_json_state(manifest_path, manifest)
