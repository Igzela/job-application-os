"""Versioned and atomic JSON persistence for mutable runtime state."""

from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping


SCHEMA_VERSION = 1


class RuntimeStateError(ValueError):
    """Raised when persisted runtime state cannot be read safely."""


@contextmanager
def _state_lock(path: Path) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _normalized(
    data: Mapping[str, Any],
    default: Mapping[str, Any],
) -> dict[str, Any]:
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise RuntimeStateError(
            f"Unsupported runtime state schema version: {version}"
        )
    result = copy.deepcopy(dict(default))
    result.update(copy.deepcopy(dict(data)))
    result["schema_version"] = SCHEMA_VERSION
    return result


def load_json_state(
    path: str | Path,
    default: Mapping[str, Any],
) -> dict[str, Any]:
    """Load versioned JSON state, returning a fresh default when absent."""
    path = Path(path)
    if not path.exists():
        return _normalized({}, default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeStateError(f"Invalid JSON runtime state: {path}") from exc
    except OSError as exc:
        raise RuntimeStateError(f"Cannot read runtime state: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeStateError(f"Runtime state must be a JSON object: {path}")
    return _normalized(data, default)


def _write_json_unlocked(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload["schema_version"] = SCHEMA_VERSION
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def save_json_state(path: str | Path, data: Mapping[str, Any]) -> None:
    """Atomically persist versioned JSON state under an advisory lock."""
    path = Path(path)
    with _state_lock(path):
        _write_json_unlocked(path, data)


def update_json_state(
    path: str | Path,
    default: Mapping[str, Any],
    update: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Load, mutate, and atomically save one state file under one lock."""
    path = Path(path)
    with _state_lock(path):
        state = load_json_state(path, default)
        update(state)
        _write_json_unlocked(path, state)
        return state
