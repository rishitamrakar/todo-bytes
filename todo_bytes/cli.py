"""todo-bytes CLI entry point.

Phase 1 commands:
  todo init                         — interactive setup
  todo config show                  — print current config
  todo config set <key> <value>     — update a config field

Phase 2 commands (operate on the default list):
  todo add "task name" [--due ...] [--tag ...] [--project ...]
  todo list
  todo show <id>
  todo done <id>
  todo rm <id>
  todo edit <id> [--name ...] [--due ...] [--tag ...] [--project ...]
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

from todo_bytes import __version__
from todo_bytes.config import (
    Config,
    DEFAULT_LIST,
    DEFAULT_UI_PORT,
    config_exists,
    get_config_file,
    get_default_data_dir,
    load_config,
    save_config,
    update_config,
)
from todo_bytes.dates import parse_due
from todo_bytes.models import END_OF_DAY, STATUS_DONE, Task
from todo_bytes import views
from todo_bytes.store import (
    CannotDeleteDefaultListError,
    ListAlreadyExistsError,
    ListNotFoundError,
    TaskNotFoundError,
    add_task,
    all_lists,
    create_list,
    delete_list,
    delete_task,
    find_task,
    list_exists,
    list_summary,
    load_tasks,
    mark_done,
    update_task,
)


app = typer.Typer(
    name="todo",
    help="todo-bytes — a minimal yaml-based todo app.",
    no_args_is_help=True,
    add_completion=False,
)
config_app = typer.Typer(help="Show or update todo-bytes config.", no_args_is_help=True)
app.add_typer(config_app, name="config")
lists_app = typer.Typer(help="Manage task lists.", no_args_is_help=True)
app.add_typer(lists_app, name="lists")

console = Console()


# ---------- top level ----------

@app.command()
def version():
    """Print version."""
    console.print(f"todo-bytes {__version__}")


# ---------- init ----------

@app.command()
def init(
    data_dir: str = typer.Option(None, "--data-dir", help="Where task yaml files live."),
    default_list: str = typer.Option(None, "--default-list", help="Name of the default list."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
):
    """Set up todo-bytes — pick a data dir and create your first list."""
    if config_exists() and not yes:
        _confirm_overwrite_or_exit(get_config_file())

    chosen_data_dir = data_dir or _prompt_data_dir()
    chosen_list = default_list or _prompt_default_list()

    data_path = Path(chosen_data_dir).expanduser().resolve()
    _create_data_dir(data_path)
    _create_empty_list_file(data_path, chosen_list)

    config = Config(
        data_dir=str(data_path),
        default_list=chosen_list,
        ui_port=DEFAULT_UI_PORT,
    )
    save_config(config)
    _print_init_summary(config)


def _confirm_overwrite_or_exit(config_file: Path) -> None:
    console.print(f"[yellow]Config already exists at {config_file}[/yellow]")
    if not typer.confirm("Overwrite existing config?", default=False):
        console.print("Aborted.")
        raise typer.Exit(code=1)


def _prompt_data_dir() -> str:
    return typer.prompt(
        "Where should your tasks live?",
        default=str(get_default_data_dir()),
    )


def _prompt_default_list() -> str:
    return typer.prompt(
        "Default list name?",
        default=DEFAULT_LIST,
    )


def _create_data_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Data dir ready: {path}")


def _create_empty_list_file(data_dir: Path, list_name: str) -> None:
    list_file = data_dir / f"{list_name}.yaml"
    if list_file.exists():
        console.print(f"[dim]· Project file already exists: {list_file}[/dim]")
        return
    payload = {
        "project": {
            "name": list_name,
            "description": None,
            "status": "todo",
            "due": None,
            "created": datetime.now(),
        },
        "tasks": [],
    }
    list_file.write_text(yaml.safe_dump(payload, sort_keys=False))
    console.print(f"[green]✓[/green] Created project file: {list_file}")


def _print_init_summary(config: Config) -> None:
    console.print(f"[green]✓[/green] Config saved to {get_config_file()}")
    console.print()
    console.print("[bold]You're set.[/bold] Try:")
    console.print(f"  [cyan]todo config show[/cyan]")
    console.print(f"  [cyan]todo add \"my first task\"[/cyan]   [dim](coming in phase 2)[/dim]")


# ---------- config ----------

@config_app.command("show")
def config_show():
    """Print current config."""
    config = _load_config_or_exit()
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("config_file", str(get_config_file()))
    for key, value in asdict(config).items():
        table.add_row(key, str(value))
    console.print(table)


@config_app.command("set")
def config_set(key: str, value: str):
    """Update a single config field. Example: todo config set default_list personal"""
    try:
        updated = update_config(key, value)
    except FileNotFoundError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(code=1)
    except KeyError as err:
        console.print(f"[red]{err}[/red]")
        console.print("Valid keys: data_dir, default_list, ui_port")
        raise typer.Exit(code=1)
    except ValueError as err:
        console.print(f"[red]Invalid value for {key}: {err}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]✓[/green] {key} = {getattr(updated, key)}")


def _load_config_or_exit() -> Config:
    try:
        return load_config()
    except FileNotFoundError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(code=1)


# ---------- list management commands ----------

@lists_app.command("show")
def lists_show_cmd():
    """Show all task lists with their counts."""
    config = _load_config_or_exit()
    names = all_lists(config)
    if not names:
        console.print("[dim]No lists yet. Create one with [cyan]todo lists create <name>[/cyan][/dim]")
        return
    console.print(_render_lists_table(names, config))


@lists_app.command("create")
def lists_create_cmd(name: str = typer.Argument(..., help="Name of the new list.")):
    """Create a new empty task list."""
    config = _load_config_or_exit()
    try:
        path = create_list(name, config)
    except ListAlreadyExistsError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Created list [bold]{name}[/bold] at {path}")


@lists_app.command("delete")
def lists_delete_cmd(
    name: str = typer.Argument(..., help="Name of the list to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    """Delete a task list. Refuses if it is the current default."""
    config = _load_config_or_exit()
    _confirm_list_delete_or_exit(name, config, skip=yes)
    try:
        delete_list(name, config)
    except CannotDeleteDefaultListError as err:
        _exit_with_error(str(err))
    except ListNotFoundError as err:
        _exit_with_error(str(err))
    console.print(f"[yellow]✖[/yellow] Deleted list [bold]{name}[/bold]")


@app.command("ui")
def ui_cmd(
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Port to run on. Defaults to ui_port from config."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a browser tab automatically."),
):
    """Start the web UI on http://127.0.0.1:<port>."""
    config = _load_config_or_exit()
    target_port = port or config.ui_port
    try:
        from todo_bytes.server import run_server
    except ModuleNotFoundError as err:
        # Note: square brackets must be escaped (\[) so Rich's markup parser
        # doesn't treat [ui] as a style tag and silently drop it.
        _exit_with_error(
            f"Web UI dependencies are not installed ({err.name}). "
            f"Reinstall with the \\[ui] extras:\n"
            f"  pipx install --force 'todo-bytes\\[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'"
        )
    console.print(f"[green]Starting UI on[/green] http://127.0.0.1:{target_port}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    run_server(port=target_port, open_browser=not no_browser)


@app.command("use")
def use_cmd(name: str = typer.Argument(..., help="List to set as default.")):
    """Set the default list. Future commands without --list will use this one."""
    config = _load_config_or_exit()
    if not list_exists(name, config):
        _exit_with_error(
            f"List '{name}' does not exist. Create it first with `todo lists create {name}`."
        )
    from todo_bytes.config import update_config
    update_config("default_list", name)
    console.print(f"[green]✓[/green] Default list is now [bold]{name}[/bold]")


# ---------- task commands ----------

@app.command("add")
def add_cmd(
    name: str = typer.Argument(..., help="What needs doing."),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow, weekday, YYYY-MM-DD, or YYYY-MM-DDTHH:MM"),
    tag: list[str] = typer.Option(None, "--tag", "-t", help="Tag (repeatable)."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project to add the task to. Defaults to the configured default project."),
):
    """Add a new task."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    due_date = _parse_due_or_exit(due) if due else None
    try:
        task = add_task(
            list_name=target_project,
            name=name,
            due=due_date,
            tags=tag or [],
            config=config,
        )
    except ListNotFoundError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Added [bold]#{task.id}[/bold] {task.name} [dim](project: {target_project})[/dim]")


@app.command("list")
def list_cmd(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Which project to show. Defaults to the configured default project."),
    today: bool = typer.Option(False, "--today", help="Open tasks due today."),
    overdue: bool = typer.Option(False, "--overdue", help="Open tasks past due."),
    tomorrow: bool = typer.Option(False, "--tomorrow", help="Open tasks due tomorrow."),
    week: bool = typer.Option(False, "--week", help="Open tasks due this week (Mon\u2013Sun)."),
    next_week: bool = typer.Option(False, "--next-week", help="Open tasks due next week."),
    no_due: bool = typer.Option(False, "--no-due", help="Open tasks with no due date."),
    done: bool = typer.Option(False, "--done", help="Tasks done in the last 7 days."),
    all_tasks: bool = typer.Option(False, "--all", help="All tasks (open + done) in this project."),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Only tasks with this tag (repeatable for AND match)."),
):
    """Show tasks. Without filter flags, shows all open tasks."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    tasks = _load_tasks_or_exit(target_project, config)

    view_flags = {
        "today": today, "overdue": overdue, "tomorrow": tomorrow,
        "week": week, "next-week": next_week, "no-due": no_due,
        "done": done, "all": all_tasks,
    }
    view_name = _pick_view_or_exit(view_flags)

    filtered = _apply_view(tasks, view_name)
    filtered = views.filter_by_tag(filtered, tag or [])
    sorted_tasks = _sort_for_view(filtered, view_name)

    if not sorted_tasks:
        console.print(_empty_view_message(view_name, target_project))
        return
    console.print(_render_tasks_table(sorted_tasks, target_project, view_name))


@app.command("show")
def show_cmd(
    task_id: int = typer.Argument(..., help="Task id."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Show full details of a single task."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    tasks = _load_tasks_or_exit(target_project, config)
    try:
        task = find_task(tasks, task_id)
    except TaskNotFoundError as err:
        _exit_with_error(str(err))
    console.print(_render_task_details(task))


@app.command("done")
def done_cmd(
    task_id: int = typer.Argument(..., help="Task id to mark done."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Mark a task as done."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    try:
        task = mark_done(target_project, task_id, config=config)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Done: [bold]#{task.id}[/bold] {task.name}")


@app.command("rm")
def rm_cmd(
    task_id: int = typer.Argument(..., help="Task id to delete."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Delete a task."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    try:
        delete_task(target_project, task_id, config=config)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[yellow]✖[/yellow] Removed [bold]#{task_id}[/bold]")


@app.command("edit")
def edit_cmd(
    task_id: int = typer.Argument(..., help="Task id to edit."),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow, weekday, YYYY-MM-DD, YYYY-MM-DDTHH:MM, or 'clear' to remove"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Replaces existing tags. Use 'clear' to remove all."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Which project the task lives in. Defaults to the configured default project."),
):
    """Edit fields on an existing task."""
    config = _load_config_or_exit()
    target_project = _resolve_list(project, config)
    fields = _build_edit_fields(name=name, due=due, tag=tag)
    if not fields:
        _exit_with_error("Nothing to edit. Pass --name, --due, or --tag.")
    try:
        task = update_task(target_project, task_id, config=config, **fields)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    except KeyError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Updated [bold]#{task.id}[/bold]")


# ---------- task command helpers ----------

def _resolve_list(list_name: Optional[str], config: Config) -> str:
    """Return the target list — either the explicit --list value or the default."""
    return list_name or config.default_list


# ---------- view selection helpers ----------

DEFAULT_VIEW = "open"  # used when no view flag is passed


def _pick_view_or_exit(view_flags: dict[str, bool]) -> str:
    """Return the chosen view name. Errors if more than one view flag is set."""
    active = [name for name, on in view_flags.items() if on]
    if len(active) > 1:
        _exit_with_error(
            f"Pick only one view at a time. Got: {', '.join('--' + n for n in active)}"
        )
    return active[0] if active else DEFAULT_VIEW


def _apply_view(tasks: list[Task], view_name: str) -> list[Task]:
    """Apply the date/status filter that corresponds to a view name."""
    view_map = {
        "open": lambda ts: [t for t in ts if views.is_open(t)],
        "today": views.filter_today,
        "overdue": views.filter_overdue,
        "tomorrow": views.filter_tomorrow,
        "week": views.filter_this_week,
        "next-week": views.filter_next_week,
        "no-due": views.filter_no_due,
        "done": views.filter_done_recent,
        "all": views.filter_all,
    }
    return view_map[view_name](tasks)


def _sort_for_view(tasks: list[Task], view_name: str) -> list[Task]:
    if view_name in {"week", "next-week", "all"}:
        return views.sort_by_due_then_priority(tasks)
    if view_name == "done":
        return views.sort_by_done_at_desc(tasks)
    return views.sort_by_priority(tasks)


def _empty_view_message(view_name: str, list_name: str) -> str:
    if view_name == "open":
        return f"[dim]No open tasks in '{list_name}'. Add one with [cyan]todo add \"...\"[/cyan][/dim]"
    return f"[dim]Nothing matches --{view_name} in '{list_name}'.[/dim]"


def _confirm_list_delete_or_exit(name: str, config: Config, skip: bool) -> None:
    if skip:
        return
    summary = list_summary(name, config) if list_exists(name, config) else None
    msg = f"Delete list '{name}'"
    if summary and summary["total"] > 0:
        msg += f" with {summary['total']} task(s)"
    msg += "?"
    if not typer.confirm(msg, default=False):
        console.print("Aborted.")
        raise typer.Exit(code=1)


def _parse_due_or_exit(text: str):
    try:
        return parse_due(text)
    except ValueError as err:
        _exit_with_error(str(err))


def _format_due(due) -> str:
    """Show just the date if time is the end-of-day default, else show date + time."""
    if due is None:
        return ""
    if due.time() == END_OF_DAY:
        return due.date().isoformat()
    return due.strftime("%Y-%m-%d %H:%M")


def _load_tasks_or_exit(list_name: str, config: Config) -> list[Task]:
    try:
        return load_tasks(list_name, config=config)
    except ListNotFoundError as err:
        _exit_with_error(str(err))


def _exit_with_error(message: str):
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _build_edit_fields(
    name: Optional[str],
    due: Optional[str],
    tag: Optional[list[str]],
) -> dict:
    """Build the kwargs dict for update_task from CLI options.

    'clear' is a magic value to remove a field (None for due, [] for tags).
    """
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if due is not None:
        fields["due"] = None if due.lower() == "clear" else _parse_due_or_exit(due)
    if tag is not None:
        fields["tags"] = [] if tag == ["clear"] else list(tag)
    return fields


# ---------- rendering ----------

VIEW_TITLES = {
    "open": "Open tasks",
    "today": "Due today",
    "overdue": "Overdue",
    "tomorrow": "Due tomorrow",
    "week": "Due this week",
    "next-week": "Due next week",
    "no-due": "Open tasks (no due date)",
    "done": "Done (last 7 days)",
    "all": "All tasks",
}


def _render_tasks_table(tasks: list[Task], list_name: str, view_name: str = "open") -> Table:
    title_prefix = VIEW_TITLES.get(view_name, "Tasks")
    table = Table(title=f"{title_prefix} — {list_name}", title_style="bold")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Task")
    if view_name == "all":
        table.add_column("Status")
    table.add_column("Due")
    table.add_column("Tags", style="cyan")
    table.add_column("Project", style="magenta")
    for task in tasks:
        row = [str(task.id), task.name]
        if view_name == "all":
            row.append(task.status)
        row.extend([
            _format_due(task.due),
            ", ".join(task.tags) if task.tags else "",
            task.project or "",
        ])
        table.add_row(*row)
    return table


def _render_task_details(task: Task) -> Table:
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("id", str(task.id))
    table.add_row("name", task.name)
    table.add_row("status", task.status)
    table.add_row("priority", str(task.priority))
    table.add_row("due", _format_due(task.due))
    table.add_row("tags", ", ".join(task.tags) if task.tags else "")
    table.add_row("project", task.project or "")
    table.add_row("created", str(task.created))
    table.add_row("done_at", str(task.done_at) if task.done_at else "")
    return table


def _render_lists_table(names: list[str], config: Config) -> Table:
    table = Table(title="Lists", title_style="bold")
    table.add_column("Name")
    table.add_column("Open", justify="right", style="cyan")
    table.add_column("Done", justify="right", style="dim")
    table.add_column("Default", justify="center")
    for name in names:
        summary = list_summary(name, config)
        is_default = "✓" if name == config.default_list else ""
        table.add_row(name, str(summary["open"]), str(summary["done"]), is_default)
    return table


if __name__ == "__main__":
    app()
