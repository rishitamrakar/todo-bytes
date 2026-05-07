"""Filter and sort tasks for different views.

All functions are pure — they take a list of tasks and return a filtered list.
Date-based functions accept an injectable `today` so tests are deterministic.

Week definition: Monday–Sunday (EU default). Monday = weekday 0, Sunday = 6.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from todo_bytes.models import ACTIVE_STATUSES, STATUS_DONE, Task


# ---------- predicates ----------

def is_open(task: Task) -> bool:
    """Active = todo or in-progress. Hold and cancelled are not 'open' for daily work."""
    return task.status in ACTIVE_STATUSES


def is_done(task: Task) -> bool:
    return task.status == STATUS_DONE


# ---------- week helpers ----------

def week_bounds(today: date) -> tuple[date, date]:
    """Return (Monday, Sunday) of the week containing `today`."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def next_week_bounds(today: date) -> tuple[date, date]:
    monday, sunday = week_bounds(today)
    return monday + timedelta(days=7), sunday + timedelta(days=7)


# ---------- date filters (orthogonal — status not baked in) ----------
#
# Each filter only checks the due date. Status filtering is a separate axis,
# composed via filter_by_statuses(). This lets the UI / API mix any date
# filter with any status set independently.

def _due_date(task: Task) -> Optional[date]:
    """Date part of task.due (or None). Filters compare on date, not exact datetime.

    Defensive: handles both date and datetime in case a Task is constructed
    directly (e.g. in unit tests) with a plain date.
    """
    if task.due is None:
        return None
    if isinstance(task.due, datetime):
        return task.due.date()
    return task.due  # already a plain date


def filter_today(tasks: list[Task], today: date | None = None) -> list[Task]:
    today = today or date.today()
    return [t for t in tasks if _due_date(t) == today]


def filter_overdue(tasks: list[Task], today: date | None = None) -> list[Task]:
    today = today or date.today()
    return [t for t in tasks if _due_date(t) is not None and _due_date(t) < today]


def filter_tomorrow(tasks: list[Task], today: date | None = None) -> list[Task]:
    today = today or date.today()
    tomorrow = today + timedelta(days=1)
    return [t for t in tasks if _due_date(t) == tomorrow]


def filter_this_week(tasks: list[Task], today: date | None = None) -> list[Task]:
    today = today or date.today()
    monday, sunday = week_bounds(today)
    return [t for t in tasks if _due_date(t) is not None and monday <= _due_date(t) <= sunday]


def filter_next_week(tasks: list[Task], today: date | None = None) -> list[Task]:
    today = today or date.today()
    monday, sunday = next_week_bounds(today)
    return [t for t in tasks if _due_date(t) is not None and monday <= _due_date(t) <= sunday]


def filter_no_due(tasks: list[Task]) -> list[Task]:
    return [t for t in tasks if t.due is None]


def filter_in_date_range(tasks: list[Task], start: date, end: date) -> list[Task]:
    """Tasks whose due date falls in [start, end] inclusive on both ends.

    For datetime tasks the date part is compared, so a task due
    2026-05-12T18:30 is included when end=2026-05-12.
    """
    if start > end:
        start, end = end, start  # be forgiving on swapped bounds
    return [t for t in tasks if _due_date(t) is not None and start <= _due_date(t) <= end]


# ---------- status filter ----------

def filter_by_statuses(tasks: list[Task], statuses: list[str] | set[str] | None) -> list[Task]:
    """Keep tasks whose status is in the given set. None / empty = pass-through."""
    if not statuses:
        return tasks
    allowed = set(statuses)
    return [t for t in tasks if t.status in allowed]


# ---------- status-based filters ----------

def filter_done_recent(tasks: list[Task], days: int = 7, now: datetime | None = None) -> list[Task]:
    """Tasks marked done within the last `days` days."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=days)
    return [t for t in tasks if is_done(t) and t.done_at is not None and t.done_at >= cutoff]


def filter_all(tasks: list[Task]) -> list[Task]:
    """Open + done together. Used for the --all view."""
    return list(tasks)


# ---------- attribute filters (compose with the above) ----------

def filter_by_tag(tasks: list[Task], tags: list[str]) -> list[Task]:
    """Match tasks that have ALL of the given tags."""
    if not tags:
        return tasks
    required = set(tags)
    return [t for t in tasks if required.issubset(set(t.tags))]


def filter_by_project(tasks: list[Task], project: str) -> list[Task]:
    if not project:
        return tasks
    return [t for t in tasks if t.project == project]


# ---------- sorting ----------

def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda t: t.priority)


def sort_by_due_then_priority(tasks: list[Task]) -> list[Task]:
    """For multi-day views — due first (None last), then priority."""
    return sorted(
        tasks,
        key=lambda t: (t.due is None, t.due or datetime.max, t.priority),
    )


def sort_by_done_at_desc(tasks: list[Task]) -> list[Task]:
    """Most-recently-done first."""
    return sorted(
        tasks,
        key=lambda t: t.done_at or datetime.min,
        reverse=True,
    )
