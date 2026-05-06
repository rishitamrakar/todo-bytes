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


CONFIG_DIR = Path.home() / ".config" / "todo-bytes"
CONFIG_FILE = CONFIG_DIR / "config.yaml"

DEFAULT_DATA_DIR = Path.home() / "my-todos"
DEFAULT_LIST = "work"
DEFAULT_UI_PORT = 8765


@dataclass
class Config:
    data_dir: str
    default_list: str
    ui_port: int

    @classmethod
    def defaults(cls) -> "Config":
        return cls(
            data_dir=str(DEFAULT_DATA_DIR),
            default_list=DEFAULT_LIST,
            ui_port=DEFAULT_UI_PORT,
        )


def config_exists() -> bool:
    return CONFIG_FILE.exists()


def load_config() -> Config:
    """Read config from disk. Raises FileNotFoundError if not set up yet."""
    if not config_exists():
        raise FileNotFoundError(
            f"No config found at {CONFIG_FILE}. Run `todo init` first."
        )
    raw = yaml.safe_load(CONFIG_FILE.read_text()) or {}
    return Config(
        data_dir=raw.get("data_dir", str(DEFAULT_DATA_DIR)),
        default_list=raw.get("default_list", DEFAULT_LIST),
        ui_port=int(raw.get("ui_port", DEFAULT_UI_PORT)),
    )


def save_config(config: Config) -> None:
    """Write config to disk, creating parent dirs if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(yaml.safe_dump(asdict(config), sort_keys=False))


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
