"""Tests for the todo CLI commands.

Uses typer.testing.CliRunner to invoke commands in-process and inspect output.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
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
        ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"],
    )
    return data_dir


def test_version_command(runner: CliRunner):
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_init_creates_data_dir_project_file_and_config(fake_home: Path, runner: CliRunner):
    data_dir = fake_home / "tasks"
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"],
    )
    assert result.exit_code == 0, result.stdout

    # Data dir created
    assert data_dir.is_dir()

    # List file created with the right shape
    project_file = data_dir / "work.yaml"
    assert project_file.is_file()
    parsed = yaml.safe_load(project_file.read_text())
    # New format: project metadata block + tasks list
    assert parsed["project"]["name"] == "work"
    assert parsed["project"]["status"] == "todo"
    assert parsed["tasks"] == []

    # Config saved
    loaded = cfg.load_config()
    assert loaded.data_dir == str(data_dir)
    assert loaded.default_project == "work"
    assert loaded.ui_port == 8765


def test_init_with_custom_project_name(fake_home: Path, runner: CliRunner):
    data_dir = fake_home / "tasks"
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-project", "personal", "--yes"],
    )
    assert result.exit_code == 0
    assert (data_dir / "personal.yaml").is_file()
    assert cfg.load_config().default_project == "personal"


def test_init_does_not_clobber_existing_project_file(fake_home: Path, runner: CliRunner):
    """Re-running init should not overwrite an existing project file's tasks."""
    data_dir = fake_home / "tasks"
    data_dir.mkdir(parents=True)
    existing = data_dir / "work.yaml"
    existing.write_text(yaml.safe_dump({
        "project": {"name": "work", "status": "todo"},
        "tasks": [{"id": 1, "name": "keep me", "priority": 1}],
    }))

    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"],
    )
    assert result.exit_code == 0

    parsed = yaml.safe_load(existing.read_text())
    assert parsed["tasks"] == [{"id": 1, "name": "keep me", "priority": 1}]


def test_init_refuses_overwrite_without_yes(fake_home: Path, runner: CliRunner):
    """If config already exists and --yes is not given, prompt should default to No."""
    data_dir = fake_home / "tasks"
    runner.invoke(app, ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"])

    # Second run without --yes, simulating user pressing Enter (defaults to No)
    result = runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-project", "work"],
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
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-project", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "data_dir" in result.stdout
    assert "default_project" in result.stdout
    assert "ui_port" in result.stdout


def test_config_set_updates_field(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-project", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "set", "default_project", "personal"])
    assert result.exit_code == 0
    assert cfg.load_config().default_project == "personal"


def test_config_set_rejects_unknown_key(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-project", "work", "--yes"],
    )
    result = runner.invoke(app, ["config", "set", "bogus_key", "value"])
    assert result.exit_code == 1
    assert "Unknown config key" in result.stdout


def test_config_set_rejects_bad_port(fake_home: Path, runner: CliRunner):
    runner.invoke(
        app,
        ["init", "--data-dir", str(fake_home / "tasks"), "--default-project", "work", "--yes"],
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
    assert tasks[0].due.date() == date.today()


def test_add_with_iso_date_and_tags(ready_to_use, runner: CliRunner):
    result = runner.invoke(
        app,
        ["add", "big task", "--due", "2026-12-31", "--tag", "work", "--tag", "blog"],
    )
    assert result.exit_code == 0
    task = store.load_tasks("work", cfg.load_config())[0]
    assert task.due.date() == date(2026, 12, 31)
    assert task.tags == ["work", "blog"]
    assert task.project == "work"  # auto-set to the active project


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
    runner.invoke(app, ["add", "detailed task"])
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 0
    assert "detailed task" in result.stdout
    assert "work" in result.stdout  # project auto-set to active project


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
    assert store.load_tasks("work", cfg.load_config())[0].due.date() == date(2026, 8, 1)


def test_edit_clears_due_date(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "x", "--due", "2026-08-01"])
    result = runner.invoke(app, ["edit", "1", "--due", "clear"])
    assert result.exit_code == 0
    assert store.load_tasks("work", cfg.load_config())[0].due is None


def test_edit_does_not_change_project(ready_to_use, runner: CliRunner):
    """Project is auto-set and not user-editable via CLI edit — it stays as the parent project name."""
    runner.invoke(app, ["add", "x"])
    result = runner.invoke(app, ["edit", "1", "--name", "renamed"])
    assert result.exit_code == 0
    task = store.load_tasks("work", cfg.load_config())[0]
    assert task.project == "work"


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


# ---------- project management commands ----------

def test_projects_show_when_only_default(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["projects", "show"])
    assert result.exit_code == 0
    assert "work" in result.stdout


def test_projects_create_then_show(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["projects", "create", "personal"])
    assert result.exit_code == 0
    assert "personal" in result.stdout
    listing = runner.invoke(app, ["projects", "show"])
    assert "personal" in listing.stdout
    assert "work" in listing.stdout


def test_projects_create_rejects_duplicate(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["projects", "create", "work"])
    assert result.exit_code == 1
    assert "already exists" in result.stdout


def test_projects_delete_with_yes_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    result = runner.invoke(app, ["projects", "delete", "personal", "--yes"])
    assert result.exit_code == 0
    assert "Deleted" in result.stdout


def test_projects_delete_refuses_default(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["projects", "delete", "work", "--yes"])
    assert result.exit_code == 1
    assert "default project" in result.stdout.lower()


def test_projects_delete_confirms_when_no_yes(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    # Simulate user pressing Enter (defaults to No)
    result = runner.invoke(app, ["projects", "delete", "personal"], input="\n")
    assert result.exit_code == 1
    assert "Aborted" in result.stdout


def test_projects_delete_missing(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["projects", "delete", "nonexistent", "--yes"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


# ---------- todo use ----------

def test_use_switches_default_project(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    result = runner.invoke(app, ["use", "personal"])
    assert result.exit_code == 0
    assert cfg.load_config().default_project == "personal"


def test_use_rejects_missing_project(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["use", "nonexistent"])
    assert result.exit_code == 1
    assert "does not exist" in result.stdout
    assert "todo projects create" in result.stdout
    # default project should be unchanged
    assert cfg.load_config().default_project == "work"


# ---------- --project flag on task commands ----------

def test_add_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    result = runner.invoke(app, ["add", "personal task", "--project", "personal"])
    assert result.exit_code == 0
    work_tasks = store.load_tasks("work", cfg.load_config())
    personal_tasks = store.load_tasks("personal", cfg.load_config())
    assert work_tasks == []
    assert len(personal_tasks) == 1
    assert personal_tasks[0].name == "personal task"


def test_list_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "work-task"])  # default project
    runner.invoke(app, ["add", "personal-task", "--project", "personal"])
    result = runner.invoke(app, ["list", "--project", "personal"])
    assert result.exit_code == 0
    assert "personal-task" in result.stdout
    assert "work-task" not in result.stdout


def test_done_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "finish me", "--project", "personal"])
    result = runner.invoke(app, ["done", "1", "--project", "personal"])
    assert result.exit_code == 0
    task = store.load_tasks("personal", cfg.load_config())[0]
    assert task.status == STATUS_DONE


def test_rm_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "a", "--project", "personal"])
    runner.invoke(app, ["add", "b", "--project", "personal"])
    result = runner.invoke(app, ["rm", "1", "--project", "personal"])
    assert result.exit_code == 0
    assert len(store.load_tasks("personal", cfg.load_config())) == 1


def test_edit_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "old", "--project", "personal"])
    result = runner.invoke(app, ["edit", "1", "--name", "new", "--project", "personal"])
    assert result.exit_code == 0
    assert store.load_tasks("personal", cfg.load_config())[0].name == "new"


def test_show_with_project_flag(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "detailed", "--project", "personal"])
    result = runner.invoke(app, ["show", "1", "--project", "personal"])
    assert result.exit_code == 0
    assert "detailed" in result.stdout
    # task.project is auto-set to the parent project
    assert "personal" in result.stdout


def test_per_project_ids_are_independent_via_cli(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "work-1"])
    runner.invoke(app, ["add", "work-2"])
    runner.invoke(app, ["add", "personal-1", "--project", "personal"])
    runner.invoke(app, ["add", "personal-2", "--project", "personal"])
    work_tasks = store.load_tasks("work", cfg.load_config())
    personal_tasks = store.load_tasks("personal", cfg.load_config())
    assert [t.id for t in work_tasks] == [1, 2]
    assert [t.id for t in personal_tasks] == [1, 2]


# ---------- view filters ----------

def test_list_today_filters_to_today_only(ready_to_use, runner: CliRunner):
    today_str = date.today().isoformat()
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
    runner.invoke(app, ["add", "due-today", "--due", today_str])
    runner.invoke(app, ["add", "due-tomorrow", "--due", tomorrow_str])
    runner.invoke(app, ["add", "no-due"])
    result = runner.invoke(app, ["list", "--today"])
    assert result.exit_code == 0
    assert "due-today" in result.stdout
    assert "due-tomorrow" not in result.stdout
    assert "no-due" not in result.stdout


def test_list_overdue_picks_past_open_only(ready_to_use, runner: CliRunner):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today_str = date.today().isoformat()
    runner.invoke(app, ["add", "missed", "--due", yesterday])
    runner.invoke(app, ["add", "on-time", "--due", today_str])
    runner.invoke(app, ["add", "no-due"])
    result = runner.invoke(app, ["list", "--overdue"])
    assert result.exit_code == 0
    assert "missed" in result.stdout
    assert "on-time" not in result.stdout
    assert "no-due" not in result.stdout


def test_list_tomorrow(ready_to_use, runner: CliRunner):
    tomorrow_str = (date.today() + timedelta(days=1)).isoformat()
    runner.invoke(app, ["add", "do-tomorrow", "--due", tomorrow_str])
    runner.invoke(app, ["add", "do-today", "--due", date.today().isoformat()])
    result = runner.invoke(app, ["list", "--tomorrow"])
    assert result.exit_code == 0
    assert "do-tomorrow" in result.stdout
    assert "do-today" not in result.stdout


def test_list_no_due(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "no-due-task"])
    runner.invoke(app, ["add", "with-due", "--due", "2026-12-31"])
    result = runner.invoke(app, ["list", "--no-due"])
    assert result.exit_code == 0
    assert "no-due-task" in result.stdout
    assert "with-due" not in result.stdout


def test_list_done_shows_done_tasks(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "finish-me"])
    runner.invoke(app, ["add", "keep-open"])
    runner.invoke(app, ["done", "1"])
    result = runner.invoke(app, ["list", "--done"])
    assert result.exit_code == 0
    assert "finish-me" in result.stdout
    assert "keep-open" not in result.stdout


def test_list_all_shows_open_and_done(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "open-task"])
    runner.invoke(app, ["add", "done-task"])
    runner.invoke(app, ["done", "2"])
    result = runner.invoke(app, ["list", "--all"])
    assert result.exit_code == 0
    assert "open-task" in result.stdout
    assert "done-task" in result.stdout
    # --all view shows status column
    assert "open" in result.stdout.lower()
    assert "done" in result.stdout.lower()


def test_list_rejects_two_view_flags(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["list", "--today", "--tomorrow"])
    assert result.exit_code == 1
    assert "only one view" in result.stdout.lower()


def test_list_with_tag_filter(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "alpha-task", "--tag", "work"])
    runner.invoke(app, ["add", "beta-task", "--tag", "personal"])
    runner.invoke(app, ["add", "gamma-task", "--tag", "work", "--tag", "blog"])
    result = runner.invoke(app, ["list", "--tag", "work"])
    assert result.exit_code == 0
    assert "alpha-task" in result.stdout
    assert "gamma-task" in result.stdout
    assert "beta-task" not in result.stdout


def test_list_with_tag_and_match(ready_to_use, runner: CliRunner):
    runner.invoke(app, ["add", "only-work", "--tag", "work"])
    runner.invoke(app, ["add", "work-and-blog", "--tag", "work", "--tag", "blog"])
    result = runner.invoke(app, ["list", "--tag", "work", "--tag", "blog"])
    assert result.exit_code == 0
    assert "work-and-blog" in result.stdout
    assert "only-work" not in result.stdout


def test_list_with_project_flag_targets_correct_project(ready_to_use, runner: CliRunner):
    """--project on `todo list` selects which project's tasks to show."""
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "work-task"])
    runner.invoke(app, ["add", "personal-task", "--project", "personal"])
    result = runner.invoke(app, ["list", "--project", "personal"])
    assert result.exit_code == 0
    assert "personal-task" in result.stdout
    assert "work-task" not in result.stdout


def test_list_view_combined_with_project_flag(ready_to_use, runner: CliRunner):
    """--today should respect --project."""
    runner.invoke(app, ["projects", "create", "personal"])
    today_str = date.today().isoformat()
    runner.invoke(app, ["add", "work-today", "--due", today_str])
    runner.invoke(app, ["add", "personal-today", "--due", today_str, "--project", "personal"])
    result = runner.invoke(app, ["list", "--today", "--project", "personal"])
    assert result.exit_code == 0
    assert "personal-today" in result.stdout
    assert "work-today" not in result.stdout


def test_list_empty_view_friendly_message(ready_to_use, runner: CliRunner):
    result = runner.invoke(app, ["list", "--today"])
    assert result.exit_code == 0
    assert "Nothing matches --today" in result.stdout


# ---------- todo ui error path ----------

def test_ui_missing_extras_message_includes_ui_marker(
    ready_to_use, runner: CliRunner, monkeypatch
):
    """If the [ui] extras are missing, the error message must literally contain
    `[ui]` so users can copy-paste the install command.

    Rich console treats `[ui]` as a markup tag, so the brackets need to be
    escaped — this test is the regression guard for that bug.
    """
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "todo_bytes.server":
            raise ModuleNotFoundError("No module named 'fastapi'", name="fastapi")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(app, ["ui"])
    assert result.exit_code == 1
    assert "[ui]" in result.stdout
    assert "todo-bytes[ui]" in result.stdout


# ---------- todo skill install ----------

def test_skill_install_copies_folder(tmp_path: Path, runner: CliRunner):
    target_parent = tmp_path / "agents" / "skills"
    result = runner.invoke(app, ["skill", "install", "--dir", str(target_parent), "--yes"])
    assert result.exit_code == 0
    skill_md = target_parent / "todo-bytes" / "SKILL.md"
    assert skill_md.is_file()
    assert "name: todo-bytes" in skill_md.read_text()


def test_skill_install_overwrites_with_yes(tmp_path: Path, runner: CliRunner):
    target_parent = tmp_path
    runner.invoke(app, ["skill", "install", "--dir", str(target_parent), "--yes"])
    # Stub a stale file inside the existing folder
    stale = target_parent / "todo-bytes" / "stale.txt"
    stale.write_text("old")
    result = runner.invoke(app, ["skill", "install", "--dir", str(target_parent), "--yes"])
    assert result.exit_code == 0
    assert not stale.exists()  # overwrite removed the stale file
    assert (target_parent / "todo-bytes" / "SKILL.md").is_file()


def test_skill_install_refuses_without_yes_when_target_exists(
    tmp_path: Path, runner: CliRunner
):
    target_parent = tmp_path
    runner.invoke(app, ["skill", "install", "--dir", str(target_parent), "--yes"])
    # Second run without --yes, simulate user pressing Enter (= No)
    result = runner.invoke(app, ["skill", "install", "--dir", str(target_parent)], input="\n")
    assert result.exit_code == 1
    assert "Aborted" in result.stdout


# ---------- reopen / status / priority / move / projects edit ----------

import json

from todo_bytes.models import STATUS_HOLD, STATUS_IN_PROGRESS


def test_reopen_clears_done_status_and_done_at(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Reopen me"])
    runner.invoke(app, ["done", "1"])
    # Confirm it went to done first
    tasks = store.load_tasks("work")
    assert tasks[0].status == STATUS_DONE
    assert tasks[0].done_at is not None

    result = runner.invoke(app, ["reopen", "1"])
    assert result.exit_code == 0, result.stdout
    tasks = store.load_tasks("work")
    assert tasks[0].status == STATUS_OPEN
    assert tasks[0].done_at is None


def test_reopen_unknown_task_errors(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["reopen", "999"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


def test_edit_status_changes_status_and_clears_done_at(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Pause this"])
    runner.invoke(app, ["done", "1"])
    # Now edit status to hold — done_at should clear automatically.
    result = runner.invoke(app, ["edit", "1", "--status", "hold"])
    assert result.exit_code == 0, result.stdout
    task = store.load_tasks("work")[0]
    assert task.status == STATUS_HOLD
    assert task.done_at is None


def test_edit_status_to_done_sets_done_at(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Finish via edit"])
    result = runner.invoke(app, ["edit", "1", "--status", "done"])
    assert result.exit_code == 0
    task = store.load_tasks("work")[0]
    assert task.status == STATUS_DONE
    assert task.done_at is not None


def test_edit_rejects_invalid_status(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Whatever"])
    result = runner.invoke(app, ["edit", "1", "--status", "bogus"])
    assert result.exit_code != 0
    assert "invalid status" in result.stdout.lower()


def test_edit_priority_moves_task_to_top(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "a"])
    runner.invoke(app, ["add", "b"])
    runner.invoke(app, ["add", "c"])
    # c is currently last; move it to top (position 1)
    result = runner.invoke(app, ["edit", "3", "--priority", "1"])
    assert result.exit_code == 0, result.stdout
    tasks = sorted(store.load_tasks("work"), key=lambda t: t.priority)
    assert [t.name for t in tasks] == ["c", "a", "b"]


def test_edit_priority_clamps_to_valid_range(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "a"])
    runner.invoke(app, ["add", "b"])
    # Position 99 should clamp to last
    result = runner.invoke(app, ["edit", "1", "--priority", "99"])
    assert result.exit_code == 0
    tasks = sorted(store.load_tasks("work"), key=lambda t: t.priority)
    assert [t.name for t in tasks] == ["b", "a"]


def test_edit_with_no_options_errors(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Plain"])
    result = runner.invoke(app, ["edit", "1"])
    assert result.exit_code != 0
    assert "nothing to edit" in result.stdout.lower()


def test_move_task_between_projects(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "Move me"])
    result = runner.invoke(app, ["move", "1", "--to", "personal"])
    assert result.exit_code == 0, result.stdout
    # Gone from source
    assert store.load_tasks("work") == []
    # Arrived in target with a fresh id
    target_tasks = store.load_tasks("personal")
    assert len(target_tasks) == 1
    assert target_tasks[0].name == "Move me"
    assert target_tasks[0].project == "personal"


def test_move_to_same_project_errors(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "Stay put"])
    result = runner.invoke(app, ["move", "1", "--to", "work"])
    assert result.exit_code != 0
    assert "differ" in result.stdout.lower() or "same" in result.stdout.lower()


def test_move_to_unknown_project_errors(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "x"])
    result = runner.invoke(app, ["move", "1", "--to", "nope"])
    assert result.exit_code != 0


def test_projects_edit_updates_description_status_due_tags(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(
        app,
        [
            "projects", "edit", "work",
            "--description", "Day job",
            "--status", "in-progress",
            "--due", "2026-12-31",
            "--tag", "office",
            "--tag", "finn",
        ],
    )
    assert result.exit_code == 0, result.stdout
    summary = store.project_summary("work")
    assert summary["description"] == "Day job"
    assert summary["status"] == STATUS_IN_PROGRESS
    assert "office" in summary["tags"] and "finn" in summary["tags"]


def test_projects_edit_clear_description(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "edit", "work", "--description", "text"])
    result = runner.invoke(app, ["projects", "edit", "work", "--description", "clear"])
    assert result.exit_code == 0
    assert store.project_summary("work")["description"] is None


def test_projects_edit_no_options_errors(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["projects", "edit", "work"])
    assert result.exit_code != 0
    assert "nothing to edit" in result.stdout.lower()


def test_projects_edit_unknown_project_errors(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["projects", "edit", "nope", "--description", "x"])
    assert result.exit_code != 0


# ---------- --json output ----------

def test_list_json_returns_structured_payload(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "First", "--due", "2026-06-01"])
    runner.invoke(app, ["add", "Second"])
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project"] == "work"
    assert payload["view"] == "open"
    assert len(payload["tasks"]) == 2
    names = {t["name"] for t in payload["tasks"]}
    assert names == {"First", "Second"}


def test_show_json_returns_single_task(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["add", "detail check"])
    result = runner.invoke(app, ["show", "1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == 1
    assert payload["name"] == "detail check"


def test_projects_show_json_includes_default_marker(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "side"])
    result = runner.invoke(app, ["projects", "show", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["default"] == "work"
    names = {p["name"] for p in payload["projects"]}
    assert names == {"work", "side"}


# ---------- projects show <name> single project detail ----------

def test_projects_show_single_renders_details(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, [
        "projects", "edit", "work",
        "--description", "Day job",
        "--status", "in-progress",
    ])
    result = runner.invoke(app, ["projects", "show", "work"])
    assert result.exit_code == 0
    assert "Day job" in result.stdout
    assert "in-progress" in result.stdout


def test_projects_show_single_json_returns_full_summary(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "edit", "work", "--description", "Day job"])
    runner.invoke(app, ["add", "one"])
    runner.invoke(app, ["add", "two"])
    runner.invoke(app, ["done", "1"])
    result = runner.invoke(app, ["projects", "show", "work", "--json"])
    assert result.exit_code == 0
    summary = json.loads(result.stdout)
    assert summary["name"] == "work"
    assert summary["description"] == "Day job"
    assert summary["open"] == 1
    assert summary["done"] == 1
    assert summary["completion_pct"] == 50


def test_projects_show_unknown_errors(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["projects", "show", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


# ---------- list --all-projects ----------

def test_list_all_projects_combines_tasks(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "work task", "--project", "work"])
    runner.invoke(app, ["add", "home task", "--project", "personal"])
    result = runner.invoke(app, ["list", "--all-projects", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["project"] == "__all__"
    names = {t["name"] for t in payload["tasks"]}
    assert names == {"work task", "home task"}


def test_list_all_projects_respects_view_filter(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "due today", "--due", "today", "--project", "work"])
    runner.invoke(app, ["add", "due next month", "--due", "2027-06-01", "--project", "personal"])
    result = runner.invoke(app, ["list", "--all-projects", "--today", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    names = [t["name"] for t in payload["tasks"]]
    assert names == ["due today"]


def test_list_all_projects_short_flag(ready_to_use: Path, runner: CliRunner):
    runner.invoke(app, ["projects", "create", "personal"])
    runner.invoke(app, ["add", "a", "--project", "work"])
    runner.invoke(app, ["add", "b", "--project", "personal"])
    # -A is the short form of --all-projects
    result = runner.invoke(app, ["list", "-A", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["tasks"]) == 2
