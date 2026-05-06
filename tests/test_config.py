"""Tests for todo_bytes.config — the module that handles global config on disk."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from todo_bytes import config as cfg


def test_defaults_returns_expected_values(fake_home: Path):
    defaults = cfg.Config.defaults()
    assert defaults.data_dir == str(fake_home / "my-todos")
    assert defaults.default_list == "work"
    assert defaults.ui_port == 8765


def test_config_exists_is_false_when_no_file(fake_home: Path):
    assert cfg.config_exists() is False


def test_load_config_raises_when_missing(fake_home: Path):
    with pytest.raises(FileNotFoundError):
        cfg.load_config()


def test_save_then_load_roundtrip(fake_home: Path):
    original = cfg.Config(
        data_dir=str(fake_home / "tasks"),
        default_list="personal",
        ui_port=9000,
    )
    cfg.save_config(original)

    assert cfg.config_exists() is True
    loaded = cfg.load_config()
    assert loaded == original


def test_save_creates_config_dir(fake_home: Path):
    cfg.save_config(cfg.Config.defaults())
    assert (fake_home / ".config" / "todo-bytes").is_dir()
    assert (fake_home / ".config" / "todo-bytes" / "config.yaml").is_file()


def test_saved_yaml_is_human_readable(fake_home: Path):
    cfg.save_config(cfg.Config(data_dir="/x", default_list="work", ui_port=8765))
    raw = cfg.get_config_file().read_text()
    parsed = yaml.safe_load(raw)
    assert parsed == {"data_dir": "/x", "default_list": "work", "ui_port": 8765}


def test_update_config_changes_single_field(fake_home: Path):
    cfg.save_config(cfg.Config.defaults())
    updated = cfg.update_config("default_list", "personal")
    assert updated.default_list == "personal"
    # Persisted on disk too
    assert cfg.load_config().default_list == "personal"


def test_update_config_coerces_ui_port_to_int(fake_home: Path):
    cfg.save_config(cfg.Config.defaults())
    updated = cfg.update_config("ui_port", "9999")
    assert updated.ui_port == 9999
    assert isinstance(updated.ui_port, int)


def test_update_config_rejects_unknown_key(fake_home: Path):
    cfg.save_config(cfg.Config.defaults())
    with pytest.raises(KeyError):
        cfg.update_config("bogus_key", "value")


def test_update_config_rejects_bad_port_value(fake_home: Path):
    cfg.save_config(cfg.Config.defaults())
    with pytest.raises(ValueError):
        cfg.update_config("ui_port", "not_a_number")


def test_load_config_uses_defaults_for_missing_fields(fake_home: Path):
    """If yaml is missing some fields, defaults should fill in."""
    cfg.get_config_dir().mkdir(parents=True, exist_ok=True)
    cfg.get_config_file().write_text("data_dir: /custom/path\n")

    loaded = cfg.load_config()
    assert loaded.data_dir == "/custom/path"
    assert loaded.default_list == "work"  # default
    assert loaded.ui_port == 8765  # default


def test_paths_follow_home_env(fake_home: Path):
    """Sanity check: HOME env override flows through to the path helpers."""
    assert cfg.get_config_dir() == fake_home / ".config" / "todo-bytes"
    assert cfg.get_config_file() == fake_home / ".config" / "todo-bytes" / "config.yaml"
    assert cfg.get_default_data_dir() == fake_home / "my-todos"
