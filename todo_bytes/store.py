"""Read/write project files.

A project is a yaml file in the data dir. Each file looks like:

    schema_version: 1
    project:
      name: work
      description: My work tasks
      status: in-progress
      due: 2026-12-31T23:59:59
      created: 2026-05-06T17:30:00
    tasks:
      - id: 1
        name: ...
        ...

The project metadata block is required. The yaml file stem (work.yaml)
must match `project.name`.

Schema versioning policy:
- `schema_version` is the on-disk yaml format version. It only changes
  when the format breaks in an incompatible way — not for new optional
  fields. App version (semver) and schema version are independent.
- v1.x.y app releases all read/write `schema_version: 1`.
- A future schema bump (e.g. introducing per-entry note timestamps in
  a way that breaks existing yaml) becomes `schema_version: 2` and
  ships with a `todo migrate` command.
- Missing `schema_version` is treated as 1 (forward-compat for files
  written before this field existed).
- An unknown / future `schema_version` raises a clear error telling
  the user to upgrade or run `todo migrate`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from todo_bytes.config import Config, load_config
from todo_bytes.models import (
    ACTIVE_STATUSES,
    STATUS_DONE,
    STATUS_TODO,
    Project,
    Task,
)

# On-disk yaml schema version. Bump only on a breaking format change.
# See module docstring for the policy.
CURRENT_SCHEMA_VERSION = 1


# ---------- errors ----------

class TaskNotFoundError(Exception):
    """Raised when a task id cannot be found in a project."""


class ProjectNotFoundError(Exception):
    """Raised when a project yaml file does not exist."""


class ProjectAlreadyExistsError(Exception):
    """Raised when trying to create a project that already exists."""


class CannotDeleteDefaultProjectError(Exception):
    """Raised when trying to delete the project that is currently the default."""


class UnsupportedSchemaVersionError(Exception):
    """Raised when a project file declares a schema_version this build can't read."""


# ---------- paths ----------

def project_file_path(project_name: str, config: Config | None = None) -> Path:
    """Return the path of the yaml file for a given project."""
    cfg = config or load_config()
    return Path(cfg.data_dir) / f"{project_name}.yaml"


# ---------- project management ----------

def all_projects(config: Config | None = None) -> list[str]:
    """Return all project names in the data dir, sorted alphabetically."""
    cfg = config or load_config()
    data_dir = Path(cfg.data_dir)
    if not data_dir.exists():
        return []
    return sorted(p.stem for p in data_dir.glob("*.yaml"))


def project_exists(project_name: str, config: Config | None = None) -> bool:
    return project_file_path(project_name, config).exists()


def load_project(project_name: str, config: Config | None = None) -> Project:
    """Load just the project metadata. Raises ProjectNotFoundError if missing."""
    raw = _load_yaml_or_raise(project_name, config)
    return Project.from_dict(raw.get("project") or {"name": project_name})


def create_project(
    project_name: str,
    description: Optional[str] = None,
    config: Config | None = None,
) -> Project:
    """Create a new empty project file with sensible default metadata."""
    if project_exists(project_name, config):
        raise ProjectAlreadyExistsError(f"Project '{project_name}' already exists")
    project = Project(name=project_name, description=description, status=STATUS_TODO)
    path = project_file_path(project_name, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_project_file(path, project, [])
    return project


def delete_project(project_name: str, config: Config | None = None) -> None:
    """Delete a project file. Refuses if it's the configured default project."""
    cfg = config or load_config()
    if project_name == cfg.default_project:
        raise CannotDeleteDefaultProjectError(
            f"Cannot delete '{project_name}' — it is the default project. "
            f"Switch default first with `todo use <other-project>`."
        )
    path = project_file_path(project_name, cfg)
    if not path.exists():
        raise ProjectNotFoundError(f"Project '{project_name}' not found at {path}")
    path.unlink()


def update_project(
    project_name: str,
    config: Config | None = None,
    **fields,
) -> Project:
    """Update project metadata fields and save."""
    project = load_project(project_name, config)
    tasks = load_tasks(project_name, config)
    _apply_project_field_updates(project, fields)
    path = project_file_path(project_name, config)
    _write_project_file(path, project, tasks)
    return project


def project_summary(project_name: str, config: Config | None = None) -> dict:
    """Return a dict with project metadata + task counts + completion percent."""
    project = load_project(project_name, config)
    tasks = load_tasks(project_name, config)
    open_count = sum(1 for t in tasks if t.status in ACTIVE_STATUSES)
    done_count = sum(1 for t in tasks if t.status == STATUS_DONE)
    total = len(tasks)
    completed_total = open_count + done_count
    completion_pct = round((done_count / completed_total) * 100) if completed_total else 0
    return {
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "due": project.due,
        "created": project.created,
        "tags": list(project.tags),
        "open": open_count,
        "done": done_count,
        "total": total,
        "completion_pct": completion_pct,
    }


# ---------- task load / save ----------

def load_tasks(project_name: str, config: Config | None = None) -> list[Task]:
    """Load all tasks for a project."""
    raw = _load_yaml_or_raise(project_name, config)
    return [Task.from_dict(t) for t in (raw.get("tasks") or [])]


def save_tasks(project_name: str, tasks: list[Task], config: Config | None = None) -> None:
    """Save tasks back to disk, preserving project metadata."""
    project = load_project(project_name, config)
    path = project_file_path(project_name, config)
    _write_project_file(path, project, tasks)


# ---------- task helpers ----------

def next_task_id(tasks: list[Task]) -> int:
    return (max((t.id for t in tasks), default=0)) + 1


def next_priority(tasks: list[Task]) -> int:
    return (max((t.priority for t in tasks), default=0)) + 1


def find_task(tasks: list[Task], task_id: int) -> Task:
    for task in tasks:
        if task.id == task_id:
            return task
    raise TaskNotFoundError(f"Task #{task_id} not found")


# ---------- task CRUD ----------

def add_task(
    project_name: str,
    name: str = "",
    due=None,
    tags: Optional[list[str]] = None,
    description: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    config: Config | None = None,
) -> Task:
    """Append a new task to a project. Returns the created Task.

    `task.project` is auto-set to the parent project's name — it is no
    longer a free-form user input.
    """
    if not project_name:
        raise ValueError("Project name is required")
    tasks = load_tasks(project_name, config)
    task = Task(
        id=next_task_id(tasks),
        name=name,
        priority=next_priority(tasks),
        status=status or STATUS_TODO,
        due=due,
        tags=tags or [],
        project=project_name,  # auto-set
        description=description,
        notes=notes,
        created=datetime.now(),
        done_at=None,
    )
    tasks.append(task)
    save_tasks(project_name, tasks, config)
    return task


def update_task(project_name: str, task_id: int, config: Config | None = None, **fields) -> Task:
    tasks = load_tasks(project_name, config)
    task = find_task(tasks, task_id)
    _apply_field_updates(task, fields)
    save_tasks(project_name, tasks, config)
    return task


def delete_task(project_name: str, task_id: int, config: Config | None = None) -> None:
    tasks = load_tasks(project_name, config)
    find_task(tasks, task_id)
    remaining = [t for t in tasks if t.id != task_id]
    save_tasks(project_name, remaining, config)


def mark_done(project_name: str, task_id: int, config: Config | None = None) -> Task:
    tasks = load_tasks(project_name, config)
    task = find_task(tasks, task_id)
    task.status = STATUS_DONE
    task.done_at = datetime.now()
    save_tasks(project_name, tasks, config)
    return task


def reopen_task(project_name: str, task_id: int, config: Config | None = None) -> Task:
    tasks = load_tasks(project_name, config)
    task = find_task(tasks, task_id)
    task.status = STATUS_TODO
    task.done_at = None
    save_tasks(project_name, tasks, config)
    return task


def move_task(
    from_project: str,
    task_id: int,
    to_project: str,
    config: Config | None = None,
) -> Task:
    """Move a task from one project to another.

    The task gets a new ID and priority in the target project (appended at
    the bottom). All other fields (name, due, tags, status, done_at,
    created, description, notes) are preserved. Duplicate names across
    projects are allowed by design.

    Returns the moved task with its new ID + project.
    """
    if from_project == to_project:
        raise ValueError("Source and target projects must differ")
    if not project_exists(to_project, config):
        raise ProjectNotFoundError(f"Project '{to_project}' does not exist")

    source_tasks = load_tasks(from_project, config)
    task = find_task(source_tasks, task_id)
    moved = _rehome_task(task, to_project, config)
    _remove_and_save(source_tasks, task_id, from_project, config)
    return moved


def _rehome_task(task: Task, to_project: str, config: Config | None) -> Task:
    target_tasks = load_tasks(to_project, config)
    task.id = next_task_id(target_tasks)
    task.priority = next_priority(target_tasks)
    task.project = to_project
    target_tasks.append(task)
    save_tasks(to_project, target_tasks, config)
    return task


def _remove_and_save(tasks: list[Task], task_id: int, project: str, config: Config | None) -> None:
    remaining = [t for t in tasks if t.id != task_id]
    save_tasks(project, remaining, config)


# ---------- internals ----------

ALLOWED_TASK_FIELDS = {"name", "due", "tags", "project", "priority", "status", "done_at", "description", "notes"}
ALLOWED_PROJECT_FIELDS = {"description", "status", "due", "tags"}


def _apply_field_updates(task: Task, fields: dict) -> None:
    """Set the given fields on a task. None is meaningful (clears the field)."""
    for key, value in fields.items():
        if key not in ALLOWED_TASK_FIELDS:
            raise KeyError(f"Cannot update unknown field: {key}")
        setattr(task, key, value)


def _apply_project_field_updates(project: Project, fields: dict) -> None:
    for key, value in fields.items():
        if key not in ALLOWED_PROJECT_FIELDS:
            raise KeyError(f"Cannot update unknown project field: {key}")
        setattr(project, key, value)


def _load_yaml_or_raise(project_name: str, config: Config | None) -> dict:
    path = project_file_path(project_name, config)
    if not path.exists():
        raise ProjectNotFoundError(f"Project '{project_name}' not found at {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    _check_schema_version(raw, path)
    return raw


def _check_schema_version(raw: dict, path: Path) -> None:
    """Reject yaml files written by a newer, incompatible schema version.

    Missing field is treated as 1 (forward-compat for legacy files).
    """
    version = raw.get("schema_version", 1)
    if version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"{path} declares schema_version={version}, but this build only "
            f"understands up to {CURRENT_SCHEMA_VERSION}. Upgrade todo-bytes "
            f"or run `todo migrate`."
        )


def _write_project_file(path: Path, project: Project, tasks: list[Task]) -> None:
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "project": project.to_dict(),
        "tasks": [t.to_dict() for t in tasks],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False))


# Keep legacy ALLOWED_UPDATE_FIELDS name working
ALLOWED_UPDATE_FIELDS = ALLOWED_TASK_FIELDS
