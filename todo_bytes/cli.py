"""todo-bytes CLI entry point.

Setup:
  todo init                         — interactive setup
  todo config show                  — print current config
  todo config set <key> <value>     — update a config field

Projects:
  todo projects show                — list all projects with task counts
  todo projects create <name>       — create a new project
  todo projects delete <name>       — delete a project
  todo use <name>                   — set the default project

Agent skill:
  todo skill install [--dir <path>] — copy the agent skill folder out
                                       (default: ~/.agents/skills/)

Tasks (operate on the default project):
  todo add "task name" [--due ...] [--tag ...] [--project ...]
  todo list
  todo show <id>
  todo done <id>
  todo rm <id>
  todo edit <id> [--name ...] [--due ...] [--tag ...] [--project ...]
"""

from __future__ import annotations

import json
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
    DEFAULT_PROJECT,
    DEFAULT_UI_PORT,
    config_exists,
    get_config_file,
    get_default_data_dir,
    load_config,
    save_config,
    update_config,
)
from todo_bytes.dates import parse_due
from todo_bytes.models import END_OF_DAY, STATUS_DONE, Task, VALID_STATUSES
from todo_bytes import ics, views
from todo_bytes.store import (
    CURRENT_SCHEMA_VERSION,
    CannotDeleteDefaultProjectError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    TaskNotFoundError,
    add_task,
    all_projects,
    create_project,
    delete_project,
    delete_task,
    find_task,
    move_task,
    project_exists,
    project_summary,
    load_tasks,
    mark_done,
    reopen_task,
    set_task_priority,
    update_project,
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
projects_app = typer.Typer(help="Manage projects.", no_args_is_help=True)
app.add_typer(projects_app, name="projects")
skill_app = typer.Typer(help="Install the agent skill that ships with todo-bytes.", no_args_is_help=True)
app.add_typer(skill_app, name="skill")
sync_app = typer.Typer(help="Sync tasks to Google Calendar (one-way, read-only).", no_args_is_help=True)
app.add_typer(sync_app, name="sync")

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
    default_project: str = typer.Option(None, "--default-project", help="Name of the default project."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
):
    """Set up todo-bytes — pick a data dir and create your first project."""
    if config_exists() and not yes:
        _confirm_overwrite_or_exit(get_config_file())

    chosen_data_dir = data_dir or _prompt_data_dir()
    chosen_project = default_project or _prompt_default_project()

    data_path = Path(chosen_data_dir).expanduser().resolve()
    _create_data_dir(data_path)
    _create_empty_project_file(data_path, chosen_project)

    config = Config(
        data_dir=str(data_path),
        default_project=chosen_project,
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


def _prompt_default_project() -> str:
    return typer.prompt(
        "Default project name?",
        default=DEFAULT_PROJECT,
    )


def _create_data_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Data dir ready: {path}")


def _create_empty_project_file(data_dir: Path, project_name: str) -> None:
    project_file = data_dir / f"{project_name}.yaml"
    if project_file.exists():
        console.print(f"[dim]· Project file already exists: {project_file}[/dim]")
        return
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "description": None,
            "status": "todo",
            "due": None,
            "created": datetime.now(),
            "tags": [],
        },
        "tasks": [],
    }
    project_file.write_text(yaml.safe_dump(payload, sort_keys=False))
    console.print(f"[green]✓[/green] Created project file: {project_file}")


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
    """Update a single config field. Example: todo config set default_project personal"""
    try:
        updated = update_config(key, value)
    except FileNotFoundError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(code=1)
    except KeyError as err:
        console.print(f"[red]{err}[/red]")
        console.print("Valid keys: data_dir, default_project, ui_port")
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


# ---------- project management commands ----------

@projects_app.command("show")
def projects_show_cmd(
    as_json: bool = typer.Option(False, "--json", help="Output structured JSON instead of a table."),
):
    """Show all projects with their task counts."""
    config = _load_config_or_exit()
    names = all_projects(config)
    if as_json:
        payload = [project_summary(n, config=config) for n in names]
        _print_json({"projects": payload, "default": config.default_project})
        return
    if not names:
        console.print("[dim]No projects yet. Create one with [cyan]todo projects create <name>[/cyan][/dim]")
        return
    console.print(_render_projects_table(names, config))


@projects_app.command("create")
def projects_create_cmd(name: str = typer.Argument(..., help="Name of the new project.")):
    """Create a new empty project."""
    config = _load_config_or_exit()
    try:
        create_project(name, config=config)
    except ProjectAlreadyExistsError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Created project [bold]{name}[/bold]")


@projects_app.command("edit")
def projects_edit_cmd(
    name: str = typer.Argument(..., help="Name of the project to edit."),
    description: Optional[str] = typer.Option(
        None, "--description", help="Short description. Use 'clear' to remove."
    ),
    status: Optional[str] = typer.Option(
        None, "--status", "-s", help="todo, in-progress, done, hold, cancelled"
    ),
    due: Optional[str] = typer.Option(
        None,
        "--due",
        "-d",
        help="today, tomorrow 6pm, weekday, YYYY-MM-DD, or 'clear'",
    ),
    tag: Optional[list[str]] = typer.Option(
        None, "--tag", "-t", help="Replaces existing tags. Use 'clear' to remove all."
    ),
):
    """Edit a project's metadata (description, status, due, tags)."""
    config = _load_config_or_exit()
    _validate_status_or_exit(status)
    fields = _build_project_edit_fields(
        description=description, status=status, due=due, tag=tag
    )
    if not fields:
        _exit_with_error(
            "Nothing to edit. Pass --description, --status, --due, or --tag."
        )
    try:
        update_project(name, config=config, **fields)
    except ProjectNotFoundError as err:
        _exit_with_error(str(err))
    except KeyError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Updated project [bold]{name}[/bold]")


def _build_project_edit_fields(
    description: Optional[str],
    status: Optional[str],
    due: Optional[str],
    tag: Optional[list[str]],
) -> dict:
    fields: dict = {}
    if description is not None:
        fields["description"] = None if description.lower() == "clear" else description
    if status is not None:
        fields["status"] = status
    if due is not None:
        fields["due"] = None if due.lower() == "clear" else _parse_due_or_exit(due)
    if tag is not None:
        fields["tags"] = [] if tag == ["clear"] else list(tag)
    return fields


@projects_app.command("delete")
def projects_delete_cmd(
    name: str = typer.Argument(..., help="Name of the project to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
):
    """Delete a project. Refuses if it is the current default."""
    config = _load_config_or_exit()
    _confirm_project_delete_or_exit(name, config, skip=yes)
    try:
        delete_project(name, config)
    except CannotDeleteDefaultProjectError as err:
        _exit_with_error(str(err))
    except ProjectNotFoundError as err:
        _exit_with_error(str(err))
    console.print(f"[yellow]✖[/yellow] Deleted project [bold]{name}[/bold]")


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


# ---------- sync (Google Calendar via Drive) ----------

@sync_app.command("setup")
def sync_setup_cmd():
    """Walk through one-time setup to sync tasks to Google Calendar.

    What this does:
      1. Pick a path inside your Google Drive folder for tasks.ics
      2. Write the file there (Drive desktop syncs it to the cloud)
      3. Walk you through making the file public + getting a share link
      4. Convert the share link to a direct-download URL automatically
      5. Show you the exact URL to paste into Google Calendar
      6. Save config so every future task save updates the file (auto-sync)
    """
    config = _load_config_or_exit()
    _print_sync_intro()
    target_path = _prompt_for_sync_path(config)
    _write_initial_export(target_path, config)
    public_url = _prompt_for_drive_share_link()
    _persist_sync_config(config, target_path)
    _print_subscribe_instructions(public_url)


@sync_app.command("now")
def sync_now_cmd(
    to: Optional[Path] = typer.Option(
        None,
        "--to",
        "-t",
        help="Override output path. Default: the configured ics_export_path.",
    ),
    project: Optional[str] = typer.Option(
        None,
        "--project",
        "-p",
        help="Only export this project. Default: all projects.",
    ),
):
    """Write the ICS feed now (manual sync).

    Usually you don't need this — auto-sync runs on every task save after
    `todo sync setup`. Use this to force a refresh or for one-off exports
    to a custom path.
    """
    config = _load_config_or_exit()
    output_path = to or _resolve_default_sync_path(config)
    tasks = _collect_tasks_for_export(project, config)
    text = ics.render_ics(tasks)
    _write_ics_file(output_path, text)
    _report_export(output_path, tasks)


@sync_app.command("disable")
def sync_disable_cmd():
    """Turn off auto-sync. The ICS file stays where it is; we just stop updating it."""
    config = _load_config_or_exit()
    if not config.ics_export_path:
        console.print("[dim]Auto-sync is already off.[/dim]")
        return
    old_path = config.ics_export_path
    config.ics_export_path = None
    save_config(config)
    console.print(
        f"[green]✓[/green] Auto-sync disabled. File at [cyan]{old_path}[/cyan] left in place."
    )


# ---------- sync internals ----------

def _print_sync_intro() -> None:
    console.print("[bold]todo-bytes → Google Calendar sync[/bold]\n")
    console.print(
        "This is a [dim]one-way[/dim], read-only feed. todo-bytes is the source of truth.\n"
        "After setup, every task save auto-updates the calendar feed.\n"
    )


def _prompt_for_sync_path(config: Config) -> Path:
    detected = _detect_google_drive_dir()
    if detected:
        default_path = detected / "tasks.ics"
        console.print(f"[dim]Found Google Drive folder:[/dim] {detected}")
    else:
        default_path = Path(config.data_dir) / "tasks.ics"
        console.print(
            "[yellow]Couldn't auto-detect Google Drive.[/yellow] If you don't have the\n"
            "Google Drive desktop app installed, you'll need it for auto-sync to work.\n"
            "Install: https://www.google.com/drive/download/\n"
        )
    raw = typer.prompt("Where should I write tasks.ics?", default=str(default_path))
    return Path(raw).expanduser()


def _detect_google_drive_dir() -> Optional[Path]:
    """Find a Google Drive folder we can write to.

    Modern macOS Drive lives under ~/Library/CloudStorage/GoogleDrive-<email>/My Drive
    Older Drive used ~/Google Drive. We try both.
    """
    home = Path.home()
    cloud_storage = home / "Library" / "CloudStorage"
    if cloud_storage.exists():
        for entry in cloud_storage.iterdir():
            if entry.name.startswith("GoogleDrive-"):
                my_drive = entry / "My Drive"
                if my_drive.exists():
                    return my_drive
    legacy = home / "Google Drive"
    if legacy.exists():
        return legacy
    return None


def _write_initial_export(target_path: Path, config: Config) -> None:
    tasks = _collect_tasks_for_export(None, config)
    text = ics.render_ics(tasks)
    _write_ics_file(target_path, text)
    console.print(
        f"[green]✓[/green] Wrote [bold]{sum(1 for t in tasks if t.due)}[/bold] tasks to "
        f"[cyan]{target_path}[/cyan]\n"
    )


def _prompt_for_drive_share_link() -> str:
    console.print("[bold]Now make the file public on Google Drive:[/bold]")
    console.print("  1. Open [link]https://drive.google.com[/link] in your browser")
    console.print("  2. Find tasks.ics, right-click → [bold]Share[/bold]")
    console.print("  3. Under 'General access', pick [bold]Anyone with the link[/bold] → Viewer")
    console.print("  4. Click [bold]Copy link[/bold]\n")
    while True:
        share_url = typer.prompt("Paste the Drive share link here").strip()
        file_id = ics.extract_drive_file_id(share_url)
        if file_id:
            return ics.drive_direct_download_url(file_id)
        console.print(
            "[red]✗[/red] That doesn't look like a Drive share link. "
            "Should look like [dim]https://drive.google.com/file/d/...[/dim]\n"
        )


def _persist_sync_config(config: Config, target_path: Path) -> None:
    config.ics_export_path = str(target_path)
    save_config(config)
    console.print("[green]✓[/green] Auto-sync enabled. Every task save will update the file.\n")


def _print_subscribe_instructions(public_url: str) -> None:
    console.print("[bold]Last step — subscribe in Google Calendar:[/bold]")
    console.print("  1. Open [link]https://calendar.google.com[/link]")
    console.print("  2. Left sidebar → [bold]Other calendars[/bold] → [bold]+[/bold] → [bold]From URL[/bold]")
    console.print("  3. Paste this URL and click 'Add calendar':\n")
    console.print(f"     [cyan]{public_url}[/cyan]\n")
    console.print(
        "[dim]Note: Google polls subscribed URLs every few hours, so changes may take "
        "a while to appear. Reminders fire at task due times though.[/dim]"
    )


def _resolve_default_sync_path(config: Config) -> Path:
    if config.ics_export_path:
        return Path(config.ics_export_path)
    return Path(config.data_dir) / "tasks.ics"


def _collect_tasks_for_export(project: Optional[str], config: Config) -> list[Task]:
    if project:
        if not project_exists(project, config):
            _exit_with_error(f"Project '{project}' not found.")
        return load_tasks(project, config)
    out: list[Task] = []
    for name in all_projects(config):
        out.extend(load_tasks(name, config))
    return out


def _write_ics_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _report_export(path: Path, tasks: list[Task]) -> None:
    with_due = sum(1 for t in tasks if t.due is not None)
    skipped = len(tasks) - with_due
    msg = f"[green]✓[/green] Exported [bold]{with_due}[/bold] tasks to [cyan]{path}[/cyan]"
    if skipped:
        msg += f" [dim]({skipped} skipped — no due date)[/dim]"
    console.print(msg)


# ---------- skill install ----------

DEFAULT_SKILLS_DIR = Path.home() / ".agents" / "skills"
SKILL_FOLDER_NAME = "todo-bytes"


@skill_app.command("install")
def skill_install_cmd(
    dir: Optional[str] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Parent dir to copy the skill folder into. Defaults to ~/.agents/skills/",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Overwrite existing skill folder without asking."),
):
    """Copy the agent skill folder shipped with todo-bytes into a directory.

    The skill ships inside the package so pipx-installed users have it.
    This command copies it out to wherever your agent (Pi, Claude Code, etc.)
    looks for skills.
    """
    source = _locate_packaged_skill()
    target_parent = Path(dir).expanduser().resolve() if dir else DEFAULT_SKILLS_DIR
    target = target_parent / SKILL_FOLDER_NAME
    _confirm_skill_overwrite_or_exit(target, skip=yes)
    _copy_skill_folder(source, target)
    console.print(f"[green]✓[/green] Skill installed at [bold]{target}[/bold]")


def _locate_packaged_skill() -> Path:
    source = Path(__file__).parent / "skills" / SKILL_FOLDER_NAME
    if not source.is_dir():
        _exit_with_error(f"Packaged skill folder not found at {source}")
    return source


def _confirm_skill_overwrite_or_exit(target: Path, skip: bool) -> None:
    if not target.exists() or skip:
        return
    if not typer.confirm(f"Skill folder already exists at {target}. Overwrite?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(code=1)


def _copy_skill_folder(source: Path, target: Path) -> None:
    import shutil
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


@app.command("use")
def use_cmd(name: str = typer.Argument(..., help="Project to set as default.")):
    """Set the default project. Future commands without --project will use this one."""
    config = _load_config_or_exit()
    if not project_exists(name, config):
        _exit_with_error(
            f"Project '{name}' does not exist. Create it first with `todo projects create {name}`."
        )
    from todo_bytes.config import update_config
    update_config("default_project", name)
    console.print(f"[green]✓[/green] Default project is now [bold]{name}[/bold]")


# ---------- task commands ----------

@app.command("add")
def add_cmd(
    name: str = typer.Argument(..., help="What needs doing."),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow, weekday, YYYY-MM-DD, or YYYY-MM-DDTHH:MM"),
    tag: list[str] = typer.Option(None, "--tag", "-t", help="Tag (repeatable)."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Project to add the task to. Defaults to the configured default project."),
    description: Optional[str] = typer.Option(None, "--description", help="Short description / context for the task."),
):
    """Add a new task."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    due_date = _parse_due_or_exit(due) if due else None
    try:
        task = add_task(
            project_name=target_project,
            name=name,
            due=due_date,
            tags=tag or [],
            description=description,
            config=config,
        )
    except ProjectNotFoundError as err:
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
    as_json: bool = typer.Option(False, "--json", help="Output structured JSON instead of a table."),
):
    """Show tasks. Without filter flags, shows all open tasks."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
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

    if as_json:
        _print_json({
            "project": target_project,
            "view": view_name,
            "tasks": [t.to_dict() for t in sorted_tasks],
        })
        return
    if not sorted_tasks:
        console.print(_empty_view_message(view_name, target_project))
        return
    console.print(_render_tasks_table(sorted_tasks, target_project, view_name))


@app.command("show")
def show_cmd(
    task_id: int = typer.Argument(..., help="Task id."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    as_json: bool = typer.Option(False, "--json", help="Output structured JSON instead of a table."),
):
    """Show full details of a single task."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    tasks = _load_tasks_or_exit(target_project, config)
    try:
        task = find_task(tasks, task_id)
    except TaskNotFoundError as err:
        _exit_with_error(str(err))
    if as_json:
        _print_json(task.to_dict())
        return
    console.print(_render_task_details(task))


@app.command("done")
def done_cmd(
    task_id: int = typer.Argument(..., help="Task id to mark done."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Mark a task as done."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    try:
        task = mark_done(target_project, task_id, config=config)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Done: [bold]#{task.id}[/bold] {task.name}")


@app.command("reopen")
def reopen_cmd(
    task_id: int = typer.Argument(..., help="Task id to reopen."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Reopen a done/cancelled task back to 'todo'."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    try:
        task = reopen_task(target_project, task_id, config=config)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[green]↻[/green] Reopened [bold]#{task.id}[/bold] {task.name}")


@app.command("move")
def move_cmd(
    task_id: int = typer.Argument(..., help="Task id to move."),
    to: str = typer.Option(..., "--to", "-t", help="Target project name."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Source project. Defaults to the configured default project."),
):
    """Move a task from one project to another.

    The task keeps its name, due, tags, status, etc. but gets a new id and
    priority in the target project (appended at the bottom).
    """
    config = _load_config_or_exit()
    source_project = _resolve_project(project, config)
    try:
        moved = move_task(source_project, task_id, to, config=config)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    except ValueError as err:
        _exit_with_error(str(err))
    console.print(
        f"[green]➜[/green] Moved [bold]{moved.name}[/bold] to "
        f"[cyan]{to}[/cyan] as [bold]#{moved.id}[/bold]"
    )


@app.command("rm")
def rm_cmd(
    task_id: int = typer.Argument(..., help="Task id to delete."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Delete a task."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    try:
        delete_task(target_project, task_id, config=config)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    console.print(f"[yellow]✖[/yellow] Removed [bold]#{task_id}[/bold]")


@app.command("edit")
def edit_cmd(
    task_id: int = typer.Argument(..., help="Task id to edit."),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="today, tomorrow 6pm, monday 9am, YYYY-MM-DD, YYYY-MM-DDTHH:MM, or 'clear'"),
    tag: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Replaces existing tags. Use 'clear' to remove all."),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Which project the task lives in. Defaults to the configured default project."),
    description: Optional[str] = typer.Option(None, "--description", help="Short description. Use 'clear' to remove."),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="todo, in-progress, done, hold, cancelled"),
    priority: Optional[int] = typer.Option(None, "--priority", help="Move to this 1-indexed position (1 = top)."),
):
    """Edit fields on an existing task."""
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    _validate_status_or_exit(status)
    fields = _build_edit_fields(
        name=name, due=due, tag=tag, description=description, status=status
    )
    if not fields and priority is None:
        _exit_with_error(
            "Nothing to edit. Pass --name, --due, --tag, --description, --status, or --priority."
        )
    try:
        task = _apply_edits(target_project, task_id, fields, priority, config)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))
    except KeyError as err:
        _exit_with_error(str(err))
    console.print(f"[green]✓[/green] Updated [bold]#{task.id}[/bold]")


@app.command("notes")
def notes_cmd(
    task_id: int = typer.Argument(..., help="Task id to edit notes for."),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
):
    """Open $EDITOR to edit a task's notes (multi-line).

    Closing the editor without saving leaves notes unchanged. Saving an
    empty file clears the notes.
    """
    config = _load_config_or_exit()
    target_project = _resolve_project(project, config)
    task = _load_task_or_exit(target_project, task_id, config)
    current = task.notes or ""
    edited = typer.edit(current, extension=".md")
    if edited is None:
        console.print("[dim]No changes (editor closed without saving).[/dim]")
        return
    new_notes = edited.rstrip("\n")
    if new_notes == current:
        console.print("[dim]No changes.[/dim]")
        return
    update_task(target_project, task_id, config=config, notes=new_notes or None)
    console.print(f"[green]✓[/green] Updated notes for [bold]#{task_id}[/bold]")


def _load_task_or_exit(project_name: str, task_id: int, config: Config) -> Task:
    try:
        tasks = load_tasks(project_name, config)
        return find_task(tasks, task_id)
    except (ProjectNotFoundError, TaskNotFoundError) as err:
        _exit_with_error(str(err))


def _validate_status_or_exit(status: Optional[str]) -> None:
    if status is not None and status not in VALID_STATUSES:
        _exit_with_error(
            f"Invalid status: {status!r}. Pick one of: {', '.join(sorted(VALID_STATUSES))}"
        )


def _apply_edits(
    project: str,
    task_id: int,
    fields: dict,
    priority: Optional[int],
    config: Config,
) -> Task:
    """Apply field updates and (optionally) a priority change. Both go to
    different store functions so we run them in turn and return the latest
    state of the task."""
    task = None
    if fields:
        task = update_task(project, task_id, config=config, **fields)
    if priority is not None:
        task = set_task_priority(project, task_id, priority, config=config)
    return task


# ---------- task command helpers ----------

def _resolve_project(project_name: Optional[str], config: Config) -> str:
    """Return the target project — either the explicit --project value or the default."""
    return project_name or config.default_project


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


# CLI views compose the new orthogonal date filters with an active-status
# filter so the day-to-day commands keep their existing "hide done" feel.
# The UI uses the orthogonal filters directly for full control.

from todo_bytes.models import ACTIVE_STATUSES


def _active_only(tasks: list[Task]) -> list[Task]:
    return views.filter_by_statuses(tasks, ACTIVE_STATUSES)


def _apply_view(tasks: list[Task], view_name: str) -> list[Task]:
    """Apply the date/status filter that corresponds to a view name.

    For day-to-day views (open / today / overdue / tomorrow / week / next-week
    / no-due) the CLI keeps showing only active tasks (todo + in-progress).
    `done` and `all` are explicit overrides.
    """
    view_map = {
        "open": _active_only,
        "today": lambda ts: _active_only(views.filter_today(ts)),
        "overdue": lambda ts: _active_only(views.filter_overdue(ts)),
        "tomorrow": lambda ts: _active_only(views.filter_tomorrow(ts)),
        "week": lambda ts: _active_only(views.filter_this_week(ts)),
        "next-week": lambda ts: _active_only(views.filter_next_week(ts)),
        "no-due": lambda ts: _active_only(views.filter_no_due(ts)),
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


def _empty_view_message(view_name: str, project_name: str) -> str:
    if view_name == "open":
        return f"[dim]No open tasks in '{project_name}'. Add one with [cyan]todo add \"...\"[/cyan][/dim]"
    return f"[dim]Nothing matches --{view_name} in '{project_name}'.[/dim]"


def _confirm_project_delete_or_exit(name: str, config: Config, skip: bool) -> None:
    if skip:
        return
    summary = project_summary(name, config) if project_exists(name, config) else None
    msg = f"Delete project '{name}'"
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


def _load_tasks_or_exit(project_name: str, config: Config) -> list[Task]:
    try:
        return load_tasks(project_name, config=config)
    except ProjectNotFoundError as err:
        _exit_with_error(str(err))


def _exit_with_error(message: str):
    console.print(f"[red]{message}[/red]")
    raise typer.Exit(code=1)


def _build_edit_fields(
    name: Optional[str],
    due: Optional[str],
    tag: Optional[list[str]],
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> dict:
    """Build the kwargs dict for update_task from CLI options.

    'clear' is a magic value to remove a field (None for due/description, [] for tags).
    """
    fields: dict = {}
    if name is not None:
        fields["name"] = name
    if due is not None:
        fields["due"] = None if due.lower() == "clear" else _parse_due_or_exit(due)
    if tag is not None:
        fields["tags"] = [] if tag == ["clear"] else list(tag)
    if description is not None:
        fields["description"] = None if description.lower() == "clear" else description
    if status is not None:
        fields["status"] = status
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


def _print_json(payload) -> None:
    """Print a payload as JSON to stdout. Used by `--json` flags.

    datetime / date / Path values aren't natively JSON-serialisable; we
    `default=str` them which produces ISO format strings — the same format
    our YAML store uses, so round-trips are clean.
    """
    print(json.dumps(payload, default=str, indent=2))


def _render_tasks_table(tasks: list[Task], project_name: str, view_name: str = "open") -> Table:
    title_prefix = VIEW_TITLES.get(view_name, "Tasks")
    table = Table(title=f"{title_prefix} — {project_name}", title_style="bold")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Task")
    table.add_column("Status")
    table.add_column("Due")
    table.add_column("Tags", style="cyan")
    table.add_column("Project", style="magenta")
    for task in tasks:
        table.add_row(
            str(task.id),
            task.name,
            task.status,
            _format_due(task.due),
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
    table.add_row("due", _format_due(task.due))
    table.add_row("tags", ", ".join(task.tags) if task.tags else "")
    table.add_row("project", task.project or "")
    table.add_row("description", task.description or "")
    table.add_row("notes", task.notes or "")
    table.add_row("created", str(task.created))
    table.add_row("done_at", str(task.done_at) if task.done_at else "")
    return table


def _render_projects_table(names: list[str], config: Config) -> Table:
    table = Table(title="Projects", title_style="bold")
    table.add_column("Name")
    table.add_column("Open", justify="right", style="cyan")
    table.add_column("Done", justify="right", style="dim")
    table.add_column("Default", justify="center")
    for name in names:
        summary = project_summary(name, config)
        is_default = "✓" if name == config.default_project else ""
        table.add_row(name, str(summary["open"]), str(summary["done"]), is_default)
    return table


if __name__ == "__main__":
    app()
