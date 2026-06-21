"""Tests for deterministic configuration resolution."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from jobos import config


def test_load_env_values_does_not_mutate_process_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("JOBOS_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("JOBOS_API_KEY", raising=False)

    values = config.load_env_values()

    assert values["JOBOS_API_KEY"] == "file-key"
    assert "JOBOS_API_KEY" not in os.environ


def test_load_config_expands_from_env_file_without_global_mutation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"
    config_file.write_text(
        yaml.safe_dump({"llm": {"base_url": "${JOBOS_BASE_URL}"}}),
        encoding="utf-8",
    )
    env_file.write_text(
        "JOBOS_BASE_URL=https://llm.example.test\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_FILE", config_file)
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("JOBOS_BASE_URL", raising=False)

    loaded = config.load_config()

    assert loaded["llm"]["base_url"] == "https://llm.example.test"
    assert "JOBOS_BASE_URL" not in os.environ
