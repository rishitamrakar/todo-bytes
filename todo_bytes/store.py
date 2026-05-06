"""Read/write task lists stored as yaml files in the user's data dir.

Each list lives in `<data_dir>/<list_name>.yaml` and looks like:

    list: work
    tasks:
      - id: 1
        name: ...
        ...
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from todo_bytes.config import Config, load_config
from todo_bytes.models import STATUS_DONE, STATUS_OPEN, Task


class TaskNotFoundError(Exception):
    """Raised when a task id cannot be found in a list."""


class ListNotFoundError(Exception):
    """Raised when a list yaml file does not exist."""


# ---------- paths ----------

def list_file_path(list_name: str, config: Config | None = None) -> Path:
    """Return the path of the yaml file for a given list."""
    cfg = config or load_config()
    return Path(cfg.data_dir) / f"{list_name}.yaml"


# ---------- load / save ----------

def load_tasks(list_name: str, config: Config | None = None) -> list[Task]:
    """Load all tasks for a list. Raises ListNotFoundError if the file is missing."""
    path = list_file_path(list_name, config)
    if not path.exists():
        raise ListNotFoundError(f"List '{list_name}' not found at {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    return [Task.from_dict(t) for t in (raw.get("tasks") or [])]


def save_tasks(list_name: str, tasks: list[Task], config: Config | None = None) -> None:
    """Write tasks back to disk, preserving the list name as a top-level key."""
    path = list_file_path(list_name, config)
    payload = {
        "list": list_name,
        "tasks": [t.to_dict() for t in tasks],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))


# ---------- helpers ----------

def next_task_id(tasks: list[Task]) -> int:
    return (max((t.id for t in tasks), default=0)) + 1


def next_priority(tasks: list[Task]) -> int:
    """New tasks go to the bottom of the list."""
    return (max((t.priority for t in tasks), default=0)) + 1


def find_task(tasks: list[Task], task_id: int) -> Task:
    for task in tasks:
        if task.id == task_id:
            return task
    raise TaskNotFoundError(f"Task #{task_id} not found")


# ---------- CRUD ----------

def add_task(
    list_name: str,
    name: str,
    due=None,
    tags: Optional[list[str]] = None,
    project: Optional[str] = None,
    config: Config | None = None,
) -> Task:
    """Append a new task to a list. Returns the created Task."""
    tasks = load_tasks(list_name, config)
    task = Task(
        id=next_task_id(tasks),
        name=name,
        priority=next_priority(tasks),
        status=STATUS_OPEN,
        due=due,
        tags=tags or [],
        project=project,
        created=datetime.now(),
        done_at=None,
    )
    tasks.append(task)
    save_tasks(list_name, tasks, config)
    return task


def update_task(list_name: str, task_id: int, config: Config | None = None, **fields) -> Task:
    """Update one or more fields on an existing task. Returns the updated Task."""
    tasks = load_tasks(list_name, config)
    task = find_task(tasks, task_id)
    _apply_field_updates(task, fields)
    save_tasks(list_name, tasks, config)
    return task


ALLOWED_UPDATE_FIELDS = {"name", "due", "tags", "project", "priority", "status"}


def _apply_field_updates(task: Task, fields: dict) -> None:
    """Set the given fields on a task.

    Caller is responsible for passing only the fields they want to change.
    Passing None is meaningful — it clears the field (e.g. project=None to remove).
    """
    for key, value in fields.items():
        if key not in ALLOWED_UPDATE_FIELDS:
            raise KeyError(f"Cannot update unknown field: {key}")
        setattr(task, key, value)


def delete_task(list_name: str, task_id: int, config: Config | None = None) -> None:
    tasks = load_tasks(list_name, config)
    find_task(tasks, task_id)  # raises if missing
    remaining = [t for t in tasks if t.id != task_id]
    save_tasks(list_name, remaining, config)


def mark_done(list_name: str, task_id: int, config: Config | None = None) -> Task:
    tasks = load_tasks(list_name, config)
    task = find_task(tasks, task_id)
    task.status = STATUS_DONE
    task.done_at = datetime.now()
    save_tasks(list_name, tasks, config)
    return task
