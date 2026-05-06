"""Global config for todo-bytes.

Config lives at ~/.config/todo-bytes/config.yaml and tells the CLI:
  - where the user's task data dir is
  - which list is the default
  - which port the UI runs on
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import yaml


DEFAULT_LIST = "work"
DEFAULT_UI_PORT = 8765


def get_config_dir() -> Path:
    """Where the global config lives. Recomputed each call so tests can override HOME."""
    return Path.home() / ".config" / "todo-bytes"


def get_config_file() -> Path:
    return get_config_dir() / "config.yaml"


def get_default_data_dir() -> Path:
    return Path.home() / "my-todos"


@dataclass
class Config:
    data_dir: str
    default_list: str
    ui_port: int

    @classmethod
    def defaults(cls) -> "Config":
        return cls(
            data_dir=str(get_default_data_dir()),
            default_list=DEFAULT_LIST,
            ui_port=DEFAULT_UI_PORT,
        )


def config_exists() -> bool:
    return get_config_file().exists()


def load_config() -> Config:
    """Read config from disk. Raises FileNotFoundError if not set up yet."""
    config_file = get_config_file()
    if not config_exists():
        raise FileNotFoundError(
            f"No config found at {config_file}. Run `todo init` first."
        )
    raw = yaml.safe_load(config_file.read_text()) or {}
    return Config(
        data_dir=raw.get("data_dir", str(get_default_data_dir())),
        default_list=raw.get("default_list", DEFAULT_LIST),
        ui_port=int(raw.get("ui_port", DEFAULT_UI_PORT)),
    )


def save_config(config: Config) -> None:
    """Write config to disk, creating parent dirs if needed."""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_config_file().write_text(yaml.safe_dump(asdict(config), sort_keys=False))


def update_config(key: str, value: str) -> Config:
    """Update a single config field and save."""
    config = load_config()
    if not hasattr(config, key):
        raise KeyError(f"Unknown config key: {key}")
    typed_value = _coerce_value(key, value)
    setattr(config, key, typed_value)
    save_config(config)
    return config


def _coerce_value(key: str, value: str):
    """Convert raw string input into the right type for the field."""
    if key == "ui_port":
        return int(value)
    return value
