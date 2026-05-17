"""Global config for todo-bytes.

Config lives at ~/.config/todo-bytes/config.yaml and tells the CLI:
  - where the user's task data dir is
  - which project is the default
  - which port the UI runs on
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import yaml


DEFAULT_PROJECT = "work"
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
    default_project: str
    ui_port: int
    # If set, every task save also writes an iCalendar feed to this path.
    # Configured via `todo sync setup`. None means auto-sync is off.
    ics_export_path: Optional[str] = None

    @classmethod
    def defaults(cls) -> "Config":
        return cls(
            data_dir=str(get_default_data_dir()),
            default_project=DEFAULT_PROJECT,
            ui_port=DEFAULT_UI_PORT,
            ics_export_path=None,
        )


def config_exists() -> bool:
    return get_config_file().exists()


def load_config() -> Config:
    """Read config from disk. Raises FileNotFoundError if not set up yet.

    Backward-compat: pre-v1.2 configs used the key 'default_list'. We read
    either 'default_project' (new) or 'default_list' (legacy) and write the
    new key on next save — so existing configs migrate transparently.
    """
    config_file = get_config_file()
    if not config_exists():
        raise FileNotFoundError(
            f"No config found at {config_file}. Run `todo init` first."
        )
    raw = yaml.safe_load(config_file.read_text()) or {}
    return Config(
        data_dir=raw.get("data_dir", str(get_default_data_dir())),
        default_project=raw.get("default_project") or raw.get("default_list") or DEFAULT_PROJECT,
        ui_port=int(raw.get("ui_port", DEFAULT_UI_PORT)),
        # New field in v1.2 — default None for older configs.
        ics_export_path=raw.get("ics_export_path"),
    )


def save_config(config: Config) -> None:
    """Write config to disk, creating parent dirs if needed.

    Drops unset (None) fields so config files stay clean — e.g. users who
    haven't run `todo sync setup` don't see a stray `ics_export_path: null`
    line in their config.
    """
    get_config_dir().mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in asdict(config).items() if v is not None}
    get_config_file().write_text(yaml.safe_dump(payload, sort_keys=False))


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
