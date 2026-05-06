"""Task and Project models — the data shapes used throughout todo-bytes."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time
from typing import Optional


STATUS_TODO = "todo"
STATUS_IN_PROGRESS = "in-progress"
STATUS_DONE = "done"
STATUS_HOLD = "hold"
STATUS_CANCELLED = "cancelled"

# All valid status values.
VALID_STATUSES = {STATUS_TODO, STATUS_IN_PROGRESS, STATUS_DONE, STATUS_HOLD, STATUS_CANCELLED}

# What counts as "open" / actively being worked on. Used by the default
# Open view, all the date-based filters (today/overdue/...), and is_active().
ACTIVE_STATUSES = {STATUS_TODO, STATUS_IN_PROGRESS}

# Backwards-compat alias — old yaml files have status: open. We treat them as todo.
STATUS_OPEN = STATUS_TODO  # legacy alias, keeps old code working

# When a user gives just a date (no time), we treat the task as due at the
# end of that day. Cleaner semantics: "due 2026-05-10" means "by end of
# 2026-05-10", not "midnight at the start of 2026-05-10".
END_OF_DAY = time(23, 59, 59)


@dataclass
class Project:
    """A project = a folder of related tasks. One yaml file per project.

    `name` matches the yaml file stem (e.g. work.yaml → name='work').
    Other fields are user-editable metadata.

    `tags` are free-form labels for grouping projects (e.g. ['work', 'client-A']).
    Sidebar filters use them to show/hide projects orthogonally to status.
    """
    name: str
    description: Optional[str] = None
    status: str = "todo"  # todo | in-progress | done | hold | cancelled
    due: Optional[datetime] = None
    created: datetime = field(default_factory=datetime.now)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Project":
        if not raw or "name" not in raw:
            raise ValueError("Project must have a name")
        return cls(
            name=str(raw["name"]),
            description=raw.get("description"),
            status=_normalise_status(raw.get("status")),
            due=coerce_due(raw.get("due")),
            created=raw.get("created") or datetime.now(),
            tags=list(raw.get("tags") or []),
        )


@dataclass
class Task:
    id: int
    name: str
    priority: int
    status: str = STATUS_OPEN
    due: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    project: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    created: datetime = field(default_factory=datetime.now)
    done_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialise to a yaml-friendly dict (preserves date/datetime types)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        """Build a Task from a yaml-loaded dict, with sensible defaults.

        - Old `due` (plain date) becomes end-of-day datetime.
        - Old `status: open` becomes `todo` (auto-migration).
        - description / notes default to None for older yaml without them.
        """
        return cls(
            id=int(raw["id"]),
            name=str(raw["name"]),
            priority=int(raw.get("priority", 1)),
            status=_normalise_status(raw.get("status")),
            due=coerce_due(raw.get("due")),
            tags=list(raw.get("tags") or []),
            project=raw.get("project"),
            description=raw.get("description"),
            notes=raw.get("notes"),
            created=raw.get("created") or datetime.now(),
            done_at=raw.get("done_at"),
        )


def _normalise_status(value) -> str:
    """Map old status values to the new vocabulary. Unknown values fall back to todo."""
    if value is None:
        return STATUS_TODO
    text = str(value).strip().lower()
    if text == "open":
        return STATUS_TODO
    if text in VALID_STATUSES:
        return text
    return STATUS_TODO


def coerce_due(value) -> Optional[datetime]:
    """Accept None, date, or datetime. Returns None or datetime (end-of-day for plain dates)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, END_OF_DAY)
    raise TypeError(f"Unsupported due type: {type(value).__name__}")
