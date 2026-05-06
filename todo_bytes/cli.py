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
from datetime import date
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
from todo_bytes.models import STATUS_DONE, STATUS_OPEN, Task
from todo_bytes.store import (
    ListNotFoundError,
    TaskNotFoundError,
    add_task,
    delete_task,
    find_task,
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
        console.print(f"[dim]· List file already exists: {list_file}[/dim]")
        return
    payload = {"list": list_name, "tasks": []}
    list_file.write_text(yaml.safe_dump(payload, sort_keys=False))
    console.print(f"[green]✓[/green] Created list file: {list_file}")


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


# ---------- task commands ----------

@app.command("add")
def add_cmd(
    name: str = typer.Argument(..., help="What needs doing."),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow, weekday, or YYYY-MM-DD"),
    tag: list[str] = typer.Option(None, "--tag", "-t", help="Tag (repeatable)."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project name."),
):
    """Add a new task to the default list."""
    config = _load_config_or_exit()
    due_date = _parse_due_or_exit(due) if due else None
    try:
        task = add_task(
            list_name=config.default_list,
            name=name,
            due=due_date,
            tags=tag or [],
            project=project,
            config=config,
        )
    except ListNotFoundError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Added [bold]#{task.id}[/bold] {task.name}")


@app.command("list")
def list_cmd():
    """Show all open tasks in the default list."""
    config = _load_config_or_exit()
    tasks = _load_tasks_or_exit(config.default_list, config)
    open_tasks = [t for t in tasks if t.status == STATUS_OPEN]
    if not open_tasks:
        console.print("[dim]No open tasks. Add one with [cyan]todo add \"...\"[/cyan][/dim]")
        return
    console.print(_render_tasks_table(open_tasks, config.default_list))


@app.command("show")
def show_cmd(task_id: int = typer.Argument(..., help="Task id.")):
    """Show full details of a single task."""
    config = _load_config_or_exit()
    tasks = _load_tasks_or_exit(config.default_list, config)
    try:
        task = find_task(tasks, task_id)
    except TaskNotFoundError as err:
        _exit_with_error(str(err))
    console.print(_render_task_details(task))


@app.command("done")
def done_cmd(task_id: int = typer.Argument(..., help="Task id to mark done.")):
    """Mark a task as done."""
    config = _load_config_or_exit()
    try:
        task = mark_done(config.default_list, task_id, config=config)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Done: [bold]#{task.id}[/bold] {task.name}")


@app.command("rm")
def rm_cmd(task_id: int = typer.Argument(..., help="Task id to delete.")):
    """Delete a task."""
    config = _load_config_or_exit()
    try:
        delete_task(config.default_list, task_id, config=config)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[yellow]✖[/yellow] Removed [bold]#{task_id}[/bold]")


@app.command("edit")
def edit_cmd(
    task_id: int = typer.Argument(..., help="Task id to edit."),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow, weekday, YYYY-MM-DD, or 'clear' to remove"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Replaces existing tags. Use 'clear' to remove all."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Use 'clear' to remove."),
):
    """Edit fields on an existing task."""
    config = _load_config_or_exit()
    fields = _build_edit_fields(name=name, due=due, tag=tag, project=project)
    if not fields:
        _exit_with_error("Nothing to edit. Pass --name, --due, --tag, or --project.")
    try:
        task = update_task(config.default_list, task_id, config=config, **fields)
    except (ListNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    except KeyError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Updated [bold]#{task.id}[/bold]")


# ---------- task command helpers ----------

def _parse_due_or_exit(text: str) -> date:
    try:
        return parse_due(text)
    except ValueError as err:
        _exit_with_error(str(err))


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
    project: Optional[str],
) -> dict:
    """Build the kwargs dict for update_task from CLI options.

    'clear' is a magic value to remove a field (set due/project to None, tags to []).
    """
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if due is not None:
        fields["due"] = None if due.lower() == "clear" else _parse_due_or_exit(due)
    if tag is not None:
        fields["tags"] = [] if tag == ["clear"] else list(tag)
    if project is not None:
        fields["project"] = None if project.lower() == "clear" else project
    return fields


# ---------- rendering ----------

def _render_tasks_table(tasks: list[Task], list_name: str) -> Table:
    table = Table(title=f"Open tasks — {list_name}", title_style="bold")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Task")
    table.add_column("Due")
    table.add_column("Tags", style="cyan")
    table.add_column("Project", style="magenta")
    for task in sorted(tasks, key=lambda t: t.priority):
        table.add_row(
            str(task.id),
            task.name,
            str(task.due) if task.due else "",
            ", ".join(task.tags) if task.tags else "",
            task.project or "",
        )
    return table


def _render_task_details(task: Task) -> Table:
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    table.add_row("id", str(task.id))
    table.add_row("name", task.name)
    table.add_row("status", task.status)
    table.add_row("priority", str(task.priority))
    table.add_row("due", str(task.due) if task.due else "")
    table.add_row("tags", ", ".join(task.tags) if task.tags else "")
    table.add_row("project", task.project or "")
    table.add_row("created", str(task.created))
    table.add_row("done_at", str(task.done_at) if task.done_at else "")
    return table


if __name__ == "__main__":
    app()
