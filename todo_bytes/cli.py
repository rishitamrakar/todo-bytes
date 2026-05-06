"""todo-bytes CLI entry point.

Phase 1 commands:
  todo init                         — interactive setup
  todo config show                  — print current config
  todo config set <key> <value>     — update a config field
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

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


if __name__ == "__main__":
    app()
