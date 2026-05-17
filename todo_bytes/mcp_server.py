"""MCP server for todo-bytes — exposes the CLI as Claude Code tools.

Architecture: this is a thin shim over the `todo` CLI. Every tool invokes
the same `todo` command a user would type, with `--json` for structured
output. That makes the CLI the single contract for agents — Pi, Claude
Code, scripts, cron all use the same code path.

Why subprocess instead of `from todo_bytes import store`?
- Same code path the user runs in their terminal → if it works there, it
  works here (and vice versa for debugging).
- The CLI already validates inputs, handles config loading, manages
  errors with clear messages. No need to reimplement.
- 50-100ms subprocess overhead is invisible inside an LLM round-trip.

Installed via `pip install todo-bytes[mcp]`. Wired into Claude Code:
    claude mcp add todo-bytes -- todo-bytes-mcp
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("todo-bytes")


# ---------- CLI invocation ----------

def _run_todo(args: list[str]) -> dict:
    """Run `todo <args>` and return parsed JSON output.

    Raises RuntimeError with the CLI's error message on non-zero exit.
    Falls back to a plain {"output": ...} dict when the CLI prints
    non-JSON (e.g. `todo done` prints "✓ Done: #1 ...").
    """
    todo_path = _find_todo_binary()
    result = subprocess.run(
        [todo_path, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Errors land on stdout (rich prints there) or stderr; check both.
        error_text = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(error_text or f"todo {' '.join(args)} failed")
    return _parse_cli_output(result.stdout)


def _find_todo_binary() -> str:
    """Locate the `todo` CLI. Falls back to running it via the same Python
    interpreter the MCP server is using if `todo` isn't on PATH.

    This matters because the MCP server is launched by Claude Code in a
    fresh shell, which may not inherit the user's PATH (especially on
    GUI-launched apps on macOS).
    """
    path = shutil.which("todo")
    if path:
        return path
    return sys.executable  # caller must prepend ["-m", "todo_bytes.cli"]


def _build_args(base_args: list[str]) -> list[str]:
    """Prepend `-m todo_bytes.cli` when we fell back to the Python interpreter."""
    if _find_todo_binary() == sys.executable:
        return ["-m", "todo_bytes.cli", *base_args]
    return base_args


def _invoke(base_args: list[str]) -> dict:
    return _run_todo(_build_args(base_args))


def _parse_cli_output(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        return {"ok": True}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # `todo done`, `todo add`, etc. print human-readable success lines.
        # Return them verbatim so the LLM can confirm to the user.
        return {"ok": True, "message": text}


# ---------- tools ----------

@mcp.tool()
def list_tasks(
    project: Optional[str] = None,
    all_projects: bool = False,
    view: str = "open",
    tag: Optional[list[str]] = None,
) -> dict:
    """List tasks.

    Args:
        project: Which project (defaults to the user's configured default project).
        all_projects: If True, list tasks from every project. Overrides `project`.
        view: One of 'open' (default), 'today', 'overdue', 'tomorrow', 'week',
              'next-week', 'no-due', 'done', 'all'.
        tag: Filter to tasks with all these tags (repeatable AND match).
    """
    args = ["list", "--json"]
    if all_projects:
        args.append("-A")
    elif project:
        args.extend(["--project", project])
    if view and view != "open":
        args.append(f"--{view}")
    for t in (tag or []):
        args.extend(["--tag", t])
    return _invoke(args)


@mcp.tool()
def show_task(task_id: int, project: Optional[str] = None) -> dict:
    """Show full details of one task (name, status, due, tags, description, notes, created)."""
    args = ["show", str(task_id), "--json"]
    if project:
        args.extend(["--project", project])
    return _invoke(args)


@mcp.tool()
def add_task(
    name: str,
    due: Optional[str] = None,
    tags: Optional[list[str]] = None,
    project: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Add a new task.

    Args:
        name: What needs doing.
        due: A date or date+time. Accepts 'today', 'tomorrow', 'tomorrow 6pm',
             'monday 9am', 'fri 17:00', YYYY-MM-DD, YYYY-MM-DDTHH:MM.
             Bare dates default to end-of-day (23:59).
        tags: Tags for the task.
        project: Project to add to (defaults to the user's default project).
        description: Short context note.
    """
    args = ["add", name]
    if due:
        args.extend(["--due", due])
    for t in (tags or []):
        args.extend(["--tag", t])
    if project:
        args.extend(["--project", project])
    if description:
        args.extend(["--description", description])
    return _invoke(args)


@mcp.tool()
def mark_done(task_id: int, project: Optional[str] = None) -> dict:
    """Mark a task as done. Auto-stamps done_at."""
    args = ["done", str(task_id)]
    if project:
        args.extend(["--project", project])
    return _invoke(args)


@mcp.tool()
def reopen_task(task_id: int, project: Optional[str] = None) -> dict:
    """Reopen a done/cancelled task back to 'todo' (clears done_at)."""
    args = ["reopen", str(task_id)]
    if project:
        args.extend(["--project", project])
    return _invoke(args)


@mcp.tool()
def update_task(
    task_id: int,
    project: Optional[str] = None,
    name: Optional[str] = None,
    due: Optional[str] = None,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[int] = None,
) -> dict:
    """Edit fields on an existing task.

    Args:
        task_id: ID of the task to edit.
        project: Source project (defaults to the user's default project).
        name: New task name.
        due: New due date. Pass 'clear' to remove. Accepts natural forms
             like 'tomorrow 6pm', 'monday 9am'.
        tags: Replace the task's tags. Pass ['clear'] to remove all.
        description: New description. Pass 'clear' to remove.
        status: One of 'todo', 'in-progress', 'done', 'hold', 'cancelled'.
                Auto-syncs done_at.
        priority: 1-indexed target position in priority order (1 = top).
    """
    args = _build_update_task_args(
        task_id=task_id, project=project, name=name, due=due,
        tags=tags, description=description, status=status, priority=priority,
    )
    if len(args) <= 2:  # only ['edit', task_id], no actual fields
        raise ValueError("Pass at least one field to update.")
    return _invoke(args)


def _build_update_task_args(
    task_id: int,
    project: Optional[str],
    name: Optional[str],
    due: Optional[str],
    tags: Optional[list[str]],
    description: Optional[str],
    status: Optional[str],
    priority: Optional[int],
) -> list[str]:
    args: list[str] = ["edit", str(task_id)]
    if name:
        args.extend(["--name", name])
    if due:
        args.extend(["--due", due])
    for t in (tags or []):
        args.extend(["--tag", t])
    if description:
        args.extend(["--description", description])
    if status:
        args.extend(["--status", status])
    if priority is not None:
        args.extend(["--priority", str(priority)])
    if project:
        args.extend(["--project", project])
    return args


@mcp.tool()
def delete_task(task_id: int, project: Optional[str] = None) -> dict:
    """Delete a task permanently. Confirm with the user before calling."""
    args = ["rm", str(task_id)]
    if project:
        args.extend(["--project", project])
    return _invoke(args)


@mcp.tool()
def move_task(
    task_id: int,
    to_project: str,
    from_project: Optional[str] = None,
) -> dict:
    """Move a task from one project to another. Gets a new ID in the target."""
    args = ["move", str(task_id), "--to", to_project]
    if from_project:
        args.extend(["--project", from_project])
    return _invoke(args)


@mcp.tool()
def list_projects() -> dict:
    """List all projects with task counts and the default-project marker."""
    return _invoke(["projects", "show", "--json"])


@mcp.tool()
def project_summary(name: str) -> dict:
    """Get full details for one project (description, status, due, tags, counts, completion %)."""
    return _invoke(["projects", "show", name, "--json"])


# ---------- entry point ----------

def main() -> None:
    """Run the MCP server over stdio. Invoked by Claude Code on connect."""
    mcp.run()


if __name__ == "__main__":
    main()
