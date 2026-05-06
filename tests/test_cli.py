"""Tests for the todo CLI commands.

Uses typer.testing.CliRunner to invoke commands in-process and inspect output.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from todo_bytes import __version__
from todo_bytes import config as cfg
from todo_bytes.cli import app


def test_version_command(runner: CliRunner):
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_init_creates_data_dir_list_file_and_config(fake_home: Path, runner: CliRunner):
    data_dir = fake_home / "tasks"
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-list", "work", "--yes"],
    )
    assert result.exit_code == 0, result.stdout

    # Data dir created
    assert data_dir.is_dir()

    # List file created with the right shape
    list_file = data_dir / "work.yaml"
    assert list_file.is_file()
    parsed = yaml.safe_load(list_file.read_text())
    assert parsed == {"list": "work", "tasks": []}

    # Config saved
    loaded = cfg.load_config()
    assert loaded.data_dir == str(data_dir)
    assert loaded.default_list == "work"
    assert loaded.ui_port == 8765


def test_init_with_custom_list_name(fake_home: Path, runner: CliRunner):
    data_dir = fake_home / "tasks"
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-list", "personal", "--yes"],
    )
    assert result.exit_code == 0
    assert (data_dir / "personal.yaml").is_file()
    assert cfg.load_config().default_list == "personal"


def test_init_does_not_clobber_existing_list_file(fake_home: Path, runner: CliRunner):
    """Re-running init should not overwrite an existing list file's tasks."""
    data_dir = fake_home / "tasks"
    data_dir.mkdir(parents=True)
    existing = data_dir / "work.yaml"
    existing.write_text(yaml.safe_dump({"list": "work", "tasks": [{"id": 1, "name": "keep me"}]}))

    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-list", "work", "--yes"],
    )
    assert result.exit_code == 0

    parsed = yaml.safe_load(existing.read_text())
    assert parsed["tasks"] == [{"id": 1, "name": "keep me"}]


def test_init_refuses_overwrite_without_yes(fake_home: Path, runner: CliRunner):
    """If config already exists and --yes is not given, prompt should default to No."""
    data_dir = fake_home / "tasks"
    runner.invoke(app, ["init", "--data-dir", str(data_dir), "--default-list", "work", "--yes"])

    # Second run without --yes, simulating user pressing Enter (defaults to No)
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-list", "work"],
        input="\n",
    )
    assert result.exit_code == 1
    assert "Aborted" in result.stdout


def test_config_show_errors_when_no_config(fake_home: Path, runner: CliRunner):
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 1
    assert "todo init" in result.stdout


def test_config_show_prints_all_fields(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-list", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "data_dir" in result.stdout
    assert "default_list" in result.stdout
    assert "ui_port" in result.stdout


def test_config_set_updates_field(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-list", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "set", "default_list", "personal"])
    assert result.exit_code == 0
    assert cfg.load_config().default_list == "personal"


def test_config_set_rejects_unknown_key(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-list", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "set", "bogus_key", "value"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.stdout


def test_config_set_rejects_bad_port(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-list", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "set", "ui_port", "not_a_number"])
    assert result.exit_code == 1
    assert "Invalid value" in result.stdout
