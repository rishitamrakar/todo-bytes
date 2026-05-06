"""Task model — the shape of a single todo entry."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


STATUS_OPEN = "open"
STATUS_DONE = "done"
VALID_STATUSES = {STATUS_OPEN, STATUS_DONE}


@dataclass
class Task:
    id: int
    name: str
    priority: int
    status: str = STATUS_OPEN
    due: Optional[date] = None
    tags: list[str] = field(default_factory=list)
    project: Optional[str] = None
    created: datetime = field(default_factory=datetime.now)
    done_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Serialise to a yaml-friendly dict (preserves date/datetime types)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Task":
        """Build a Task from a yaml-loaded dict, with sensible defaults."""
        return cls(
            id=int(raw["id"]),
            name=str(raw["name"]),
            priority=int(raw.get("priority", 1)),
            status=str(raw.get("status", STATUS_OPEN)),
            due=raw.get("due"),
            tags=list(raw.get("tags") or []),
            project=raw.get("project"),
            created=raw.get("created") or datetime.now(),
            done_at=raw.get("done_at"),
        )
