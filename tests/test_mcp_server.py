"""Tests for the MCP server.

Strategy: the MCP server is a thin shim over the CLI. We test it by:
  1. End-to-end (a few key tools): run against a real fake_home + todo
     setup, verify the CLI is actually invoked and tasks change on disk.
  2. Unit (the rest): patch subprocess.run and assert the right args are
     passed. Fast, deterministic, no Python startup per call.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from todo_bytes import mcp_server
from todo_bytes.cli import app as cli_app


# ---------- helpers ----------

@pytest.fixture
def fake_todo_runs(monkeypatch):
    """Capture subprocess.run calls and return canned output.

    Yields a list that gets appended-to with (args, kwargs) for each call,
    plus a setter for the next return value.
    """
    calls = []
    next_result = {
        "stdout": "",
        "stderr": "",
        "returncode": 0,
    }

    def fake_run(args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return MagicMock(
            stdout=next_result["stdout"],
            stderr=next_result["stderr"],
            returncode=next_result["returncode"],
        )

    monkeypatch.setattr(mcp_server.subprocess, "run", fake_run)
    monkeypatch.setattr(mcp_server, "_find_todo_binary", lambda: "/fake/todo")
    yield {"calls": calls, "set_result": lambda **kw: next_result.update(kw)}


@pytest.fixture
def ready_to_use(fake_home: Path, runner: CliRunner) -> Path:
    """Real `todo init` + a couple of tasks for end-to-end tests."""
    data_dir = fake_home / "tasks"
    runner.invoke(
        cli_app,
        ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"],
    )
    return data_dir


# ---------- _run_todo / _parse_cli_output ----------

def test_run_todo_parses_json_output(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"tasks": [{"id": 1, "name": "x"}]}')
    result = mcp_server._invoke(["list", "--json"])
    assert result == {"tasks": [{"id": 1, "name": "x"}]}


def test_run_todo_wraps_non_json_success_as_message(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2713 Done: #1 hello")
    result = mcp_server._invoke(["done", "1"])
    assert result == {"ok": True, "message": "\u2713 Done: #1 hello"}


def test_run_todo_raises_on_nonzero_exit(fake_todo_runs):
    fake_todo_runs["set_result"](returncode=1, stdout="Task 99 not found")
    with pytest.raises(RuntimeError, match="Task 99 not found"):
        mcp_server._invoke(["show", "99"])


def test_run_todo_handles_empty_stdout(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="")
    assert mcp_server._invoke(["something"]) == {"ok": True}


# ---------- list_tasks ----------

def test_list_tasks_default_uses_open_view_and_json(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"tasks": []}')
    mcp_server.list_tasks()
    args = fake_todo_runs["calls"][0]["args"]
    assert "list" in args and "--json" in args
    # 'open' is the default view; we don't pass --open as a flag
    assert "--open" not in args


def test_list_tasks_with_view(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"tasks": []}')
    mcp_server.list_tasks(view="overdue")
    args = fake_todo_runs["calls"][0]["args"]
    assert "--overdue" in args


def test_list_tasks_all_projects_flag(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"tasks": []}')
    mcp_server.list_tasks(all_projects=True)
    args = fake_todo_runs["calls"][0]["args"]
    assert "-A" in args
    # When all_projects is set, we ignore --project (so the call is unambiguous).
    assert "--project" not in args


def test_list_tasks_with_project_and_tags(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"tasks": []}')
    mcp_server.list_tasks(project="personal", tag=["work", "urgent"])
    args = fake_todo_runs["calls"][0]["args"]
    assert "--project" in args and "personal" in args
    # tag appears twice
    assert args.count("--tag") == 2


# ---------- add_task / mark_done / reopen ----------

def test_add_task_passes_all_options(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2713 Added #1 Test")
    mcp_server.add_task(
        name="Standup",
        due="tomorrow 9am",
        tags=["work"],
        project="work",
        description="daily",
    )
    args = fake_todo_runs["calls"][0]["args"]
    assert "add" in args and "Standup" in args
    assert "--due" in args and "tomorrow 9am" in args
    assert "--tag" in args and "work" in args
    assert "--project" in args
    assert "--description" in args and "daily" in args


def test_mark_done_invokes_done_subcommand(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2713 Done: #5")
    mcp_server.mark_done(5)
    args = fake_todo_runs["calls"][0]["args"]
    assert args[-2:] == ["done", "5"] or "done" in args and "5" in args


def test_reopen_task_invokes_reopen(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u21bb Reopened #5")
    mcp_server.reopen_task(5)
    args = fake_todo_runs["calls"][0]["args"]
    assert "reopen" in args and "5" in args


# ---------- update_task ----------

def test_update_task_requires_at_least_one_field(fake_todo_runs):
    with pytest.raises(ValueError, match="at least one field"):
        mcp_server.update_task(1)
    # No subprocess call should have happened.
    assert fake_todo_runs["calls"] == []


def test_update_task_status_change(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2713 Updated #1")
    mcp_server.update_task(1, status="hold")
    args = fake_todo_runs["calls"][0]["args"]
    assert "edit" in args and "--status" in args and "hold" in args


def test_update_task_priority_change(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2713 Updated #3")
    mcp_server.update_task(3, priority=1)
    args = fake_todo_runs["calls"][0]["args"]
    assert "--priority" in args and "1" in args


# ---------- move / delete ----------

def test_move_task(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u279c Moved")
    mcp_server.move_task(2, to_project="personal")
    args = fake_todo_runs["calls"][0]["args"]
    assert "move" in args and "2" in args
    assert "--to" in args and "personal" in args


def test_delete_task(fake_todo_runs):
    fake_todo_runs["set_result"](stdout="\u2716 Removed #4")
    mcp_server.delete_task(4)
    args = fake_todo_runs["calls"][0]["args"]
    assert "rm" in args and "4" in args


# ---------- projects ----------

def test_list_projects(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"projects": [], "default": "work"}')
    mcp_server.list_projects()
    args = fake_todo_runs["calls"][0]["args"]
    assert args[-3:] == ["projects", "show", "--json"] or (
        "projects" in args and "show" in args and "--json" in args
    )


def test_project_summary_single(fake_todo_runs):
    fake_todo_runs["set_result"](stdout='{"name": "work", "open": 3}')
    mcp_server.project_summary("work")
    args = fake_todo_runs["calls"][0]["args"]
    assert "projects" in args and "show" in args and "work" in args and "--json" in args


# ---------- end-to-end (real CLI, real disk) ----------

def test_end_to_end_add_list_done(ready_to_use: Path, monkeypatch):
    """Drive the MCP server against the real installed CLI. Confirms the
    full path works: tool -> subprocess -> todo CLI -> store -> yaml.
    """
    # Force MCP to use the same `todo` from this venv (it's on PATH via pip install -e .).
    # No mocking — these tools actually invoke `todo` and read/write yaml.

    # Add a task via MCP
    add_result = mcp_server.add_task(name="from MCP", due="2026-06-01")
    assert add_result.get("ok") is True

    # List should now include it
    list_result = mcp_server.list_tasks()
    names = [t["name"] for t in list_result["tasks"]]
    assert "from MCP" in names

    task_id = next(t["id"] for t in list_result["tasks"] if t["name"] == "from MCP")

    # Mark done, then verify it's gone from the default open view
    mcp_server.mark_done(task_id)
    after = mcp_server.list_tasks()
    assert task_id not in [t["id"] for t in after["tasks"]]

    # Reopen, should reappear
    mcp_server.reopen_task(task_id)
    after_reopen = mcp_server.list_tasks()
    assert task_id in [t["id"] for t in after_reopen["tasks"]]


def test_end_to_end_unknown_task_raises(ready_to_use: Path):
    with pytest.raises(RuntimeError, match="not found"):
        mcp_server.show_task(9999)
