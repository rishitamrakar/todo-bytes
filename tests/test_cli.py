"""Tests for the todo CLI commands.

Uses typer.testing.CliRunner to invoke commands in-process and inspect output.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from todo_bytes import __version__
from todo_bytes import config as cfg
from todo_bytes import store
from todo_bytes.cli import app
from todo_bytes.models import STATUS_DONE, STATUS_OPEN


@pytest.fixture
def ready_to_use(fake_home: Path, runner: CliRunner) -> Path:
    """Run `todo init` so the CLI is ready for task commands."""
    data_dir = fake_home / "tasks"
    runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-list", "work", "--yes"],
    )
    return data_dir


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


# ---------- task commands ----------

def test_add_simple_task(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["add", "first task"])
    assert result.exit_code == 0
    assert "#1" in result.stdout
    tasks = store.load_tasks("work", cfg.load_config())
    assert len(tasks) == 1
    assert tasks[0].name == "first task"
    assert tasks[0].status == STATUS_OPEN


def test_add_with_due_today(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["add", "do today", "--due", "today"])
    assert result.exit_code == 0
    tasks = store.load_tasks("work", cfg.load_config())
    assert tasks[0].due == date.today()


def test_add_with_iso_date_and_tags_and_project(ready_to_use, runner: CliRunner):
    result = runner.invoke(
        app,
        ["add", "big task", "--due", "2026-12-31", "--tag", "work", "--tag", "blog", "--project", "rb"],
    )
    assert result.exit_code == 0
    task = store.load_tasks("work", cfg.load_config())[0]
    assert task.due == date(2026, 12, 31)
    assert task.tags == ["work", "blog"]
    assert task.project == "rb"


def test_add_with_bad_due_fails(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["add", "x", "--due", "not-a-date"])
    assert result.exit_code == 1
    assert "Could not parse date" in result.stdout


def test_list_empty_shows_friendly_message(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No open tasks" in result.stdout


def test_list_shows_added_tasks(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "alpha"])
    runner.invoke(app, ["add", "beta"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "alpha" in result.stdout
    assert "beta" in result.stdout


def test_list_hides_done_tasks(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "keep open"])
    runner.invoke(app, ["add", "finish me"])
    runner.invoke(app, ["done", "2"])
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "keep open" in result.stdout
    assert "finish me" not in result.stdout


def test_show_existing_task(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "detailed task", "--project", "rb"])
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 0
    assert "detailed task" in result.stdout
    assert "rb" in result.stdout


def test_show_missing_task_fails(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["show", "99"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


def test_done_marks_task(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "finish me"])
    result = runner.invoke(app, ["done", "1"])
    assert result.exit_code == 0
    task = store.load_tasks("work", cfg.load_config())[0]
    assert task.status == STATUS_DONE
    assert task.done_at is not None


def test_done_missing_task_fails(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["done", "42"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


def test_rm_deletes_task(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "a"])
    runner.invoke(app, ["add", "b"])
    result = runner.invoke(app, ["rm", "1"])
    assert result.exit_code == 0
    tasks = store.load_tasks("work", cfg.load_config())
    assert len(tasks) == 1
    assert tasks[0].name == "b"


def test_rm_missing_task_fails(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["rm", "42"])
    assert result.exit_code == 1


def test_edit_changes_name(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "original"])
    result = runner.invoke(app, ["edit", "1", "--name", "renamed"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].name == "renamed"


def test_edit_changes_due_date(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x"])
    result = runner.invoke(app, ["edit", "1", "--due", "2026-08-01"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].due == date(2026, 8, 1)


def test_edit_clears_due_date(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x", "--due", "2026-08-01"])
    result = runner.invoke(app, ["edit", "1", "--due", "clear"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].due is None


def test_edit_clears_project(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x", "--project", "rb"])
    result = runner.invoke(app, ["edit", "1", "--project", "clear"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].project is None


def test_edit_replaces_tags(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x", "--tag", "old1", "--tag", "old2"])
    result = runner.invoke(app, ["edit", "1", "--tag", "new1", "--tag", "new2"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].tags == ["new1", "new2"]


def test_edit_with_no_fields_fails(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x"])
    result = runner.invoke(app, ["edit", "1"])
    assert result.exit_code == 1
    assert "Nothing to edit" in result.stdout


def test_edit_missing_task_fails(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["edit", "42", "--name", "x"])
    assert result.exit_code == 1


def test_task_commands_fail_without_init(fake_home: Path, runner: CliRunner):
    """If the user hasn't run init, task commands should error clearly."""
    result = runner.invoke(app, ["add", "x"])
    assert result.exit_code == 1
    assert "todo init" in result.stdout


# ---------- list management commands ----------

def test_lists_show_when_only_default(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["lists", "show"])
    assert result.exit_code == 0
    assert "work" in result.stdout


def test_lists_create_then_show(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["lists", "create", "personal"])
    assert result.exit_code == 0
    assert "personal" in result.stdout
    listing = runner.invoke(app, ["lists", "show"])
    assert "personal" in listing.stdout
    assert "work" in listing.stdout


def test_lists_create_rejects_duplicate(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["lists", "create", "work"])
    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_lists_delete_with_yes_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    result = runner.invoke(app, ["lists", "delete", "personal", "--yes"])
    assert result.exit_code == 0
    assert "Deleted" in result.stdout


def test_lists_delete_refuses_default(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["lists", "delete", "work", "--yes"])
    assert result.exit_code == 1
    assert "default list" in result.stdout


def test_lists_delete_confirms_when_no_yes(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    # Simulate user pressing Enter (defaults to No)
    result = runner.invoke(app, ["lists", "delete", "personal"], input="\n")
    assert result.exit_code == 1
    assert "Aborted" in result.stdout


def test_lists_delete_missing(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["lists", "delete", "nonexistent", "--yes"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


# ---------- todo use ----------

def test_use_switches_default_list(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    result = runner.invoke(app, ["use", "personal"])
    assert result.exit_code == 0
    assert cfg.load_config().default_list == "personal"


def test_use_rejects_missing_list(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["use", "nonexistent"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout
    assert "todo lists create" in result.stdout
    # default list should be unchanged
    assert cfg.load_config().default_list == "work"


# ---------- --list flag on task commands ----------

def test_add_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    result = runner.invoke(app, ["add", "personal task", "--list", "personal"])
    assert result.exit_code == 0
    work_tasks = store.load_tasks("work", cfg.load_config())
    personal_tasks = store.load_tasks("personal", cfg.load_config())
    assert work_tasks == []
    assert len(personal_tasks) == 1
    assert personal_tasks[0].name == "personal task"


def test_list_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "work-task"])  # default list
    runner.invoke(app, ["add", "personal-task", "--list", "personal"])
    result = runner.invoke(app, ["list", "--list", "personal"])
    assert result.exit_code == 0
    assert "personal-task" in result.stdout
    assert "work-task" not in result.stdout


def test_done_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "finish me", "--list", "personal"])
    result = runner.invoke(app, ["done", "1", "--list", "personal"])
    assert result.exit_code == 0
    task = store.load_tasks("personal", cfg.load_config())[0]
    assert task.status == STATUS_DONE


def test_rm_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "a", "--list", "personal"])
    runner.invoke(app, ["add", "b", "--list", "personal"])
    result = runner.invoke(app, ["rm", "1", "--list", "personal"])
    assert result.exit_code == 0
    assert len(store.load_tasks("personal", cfg.load_config())) == 1


def test_edit_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "old", "--list", "personal"])
    result = runner.invoke(app, ["edit", "1", "--name", "new", "--list", "personal"])
    assert result.exit_code == 0
    assert store.load_tasks("personal", cfg.load_config())[0].name == "new"


def test_show_with_list_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "detailed", "--list", "personal", "--project", "rb"])
    result = runner.invoke(app, ["show", "1", "--list", "personal"])
    assert result.exit_code == 0
    assert "detailed" in result.stdout
    assert "rb" in result.stdout


def test_per_list_ids_are_independent_via_cli(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["lists", "create", "personal"])
    runner.invoke(app, ["add", "work-1"])
    runner.invoke(app, ["add", "work-2"])
    runner.invoke(app, ["add", "personal-1", "--list", "personal"])
    runner.invoke(app, ["add", "personal-2", "--list", "personal"])
    work_tasks = store.load_tasks("work", cfg.load_config())
    personal_tasks = store.load_tasks("personal", cfg.load_config())
    assert [t.id for t in work_tasks] == [1, 2]
    assert [t.id for t in personal_tasks] == [1, 2]
