"""Generate iCalendar (.ics) feeds from todo-bytes tasks.

Used for read-only subscription in Google Calendar / Apple Calendar.
Tasks with a due date become VEVENTs with a VALARM at due time. Tasks
without a due date are silently skipped (no calendar slot).

Mapping:
- task.name                     -> SUMMARY
- task.due (end-of-day = 23:59) -> all-day VEVENT, 9am reminder on that day
- task.due (other time)         -> 30-min VEVENT starting at due, at-time reminder
- task.description + task.notes -> DESCRIPTION (concatenated)
- task.tags                     -> CATEGORIES
- task.status in (done, cancel) -> STATUS:CANCELLED, no VALARM (no nag for closed tasks)
- task.id + task.project        -> stable UID so re-exports update events instead of duplicating

Times are emitted as floating (local-time) values. Subscribing calendars
render them in the viewer's local timezone, which matches todo-bytes' own
convention (datetimes are stored naive = local).

DTSTAMP is UTC (RFC 5545 §3.8.7.2 requires it).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, TYPE_CHECKING

from todo_bytes.models import Task

if TYPE_CHECKING:
    from todo_bytes.config import Config

PROD_ID = "-//rishibytes//todo-bytes//EN"
DONE_STATUSES = {"done", "cancelled"}


def render_ics(tasks: Iterable[Task], calendar_name: str = "todo-bytes") -> str:
    """Render the iCalendar text for the given tasks.

    Tasks without a `due` are skipped (calendars need a date to show them).
    """
    lines = _calendar_header(calendar_name)
    stamp = _utc_now_stamp()
    for task in tasks:
        if task.due is None:
            continue
        lines.extend(_render_event(task, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def auto_export_if_configured(config: "Config") -> None:
    """Write the ICS feed to `config.ics_export_path` if it's set.

    Called from store after every successful task save so the calendar
    stays fresh without the user remembering to run anything. Silent on
    failure — a sync hiccup must not break the underlying save operation.
    """
    if not config.ics_export_path:
        return
    try:
        # Local imports to avoid a cycle (store imports ics, ics shouldn't
        # pull store at module load).
        from todo_bytes import store
        tasks: list[Task] = []
        for name in store.all_projects(config):
            tasks.extend(store.load_tasks(name, config))
        text = render_ics(tasks)
        path = Path(config.ics_export_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    except Exception:
        # Auto-export is best-effort. If anything goes wrong (disk full,
        # path no longer writable, etc.) we don't want to fail the save.
        # The user can re-run `todo sync now` to see the real error.
        pass


# ---------- Google Drive helpers ----------

import re

_DRIVE_FILE_ID_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
_DRIVE_OPEN_ID_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def extract_drive_file_id(share_url: str) -> str | None:
    """Pull the file ID out of a Google Drive share URL.

    Accepts either of Drive's common share-link formats:
      - https://drive.google.com/file/d/<ID>/view?usp=sharing
      - https://drive.google.com/open?id=<ID>
    Returns None if the URL doesn't look like a Drive share link.
    """
    for pattern in (_DRIVE_FILE_ID_RE, _DRIVE_OPEN_ID_RE):
        match = pattern.search(share_url)
        if match:
            return match.group(1)
    return None


def drive_direct_download_url(file_id: str) -> str:
    """Build the direct-download URL that Google Calendar can subscribe to."""
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ---------- internals ----------

def _calendar_header(name: str) -> list[str]:
    return [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PROD_ID}",
        f"X-WR-CALNAME:{_escape(name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]


def _render_event(task: Task, stamp: str) -> list[str]:
    out = [
        "BEGIN:VEVENT",
        f"UID:{_uid(task)}",
        f"DTSTAMP:{stamp}",
        f"SUMMARY:{_escape(task.name)}",
    ]
    out.extend(_render_when(task))
    description = _build_description(task)
    if description:
        out.append(f"DESCRIPTION:{_escape(description)}")
    if task.tags:
        out.append(f"CATEGORIES:{','.join(_escape(t) for t in task.tags)}")
    out.extend(_render_status_and_alarm(task))
    out.append("END:VEVENT")
    return out


def _render_when(task: Task) -> list[str]:
    if _is_end_of_day(task.due):
        date_str = task.due.strftime("%Y%m%d")
        next_day = (task.due + timedelta(days=1)).strftime("%Y%m%d")
        return [
            f"DTSTART;VALUE=DATE:{date_str}",
            f"DTEND;VALUE=DATE:{next_day}",
        ]
    return [
        f"DTSTART:{_floating_dt(task.due)}",
        f"DTEND:{_floating_dt(task.due + timedelta(minutes=30))}",
    ]


def _render_status_and_alarm(task: Task) -> list[str]:
    if task.status in DONE_STATUSES:
        return ["STATUS:CANCELLED"]
    out = ["STATUS:CONFIRMED"]
    # Only embed a VALARM for timed events. All-day events get the
    # calendar's default reminder (firing at midnight from a VALARM is
    # useless, and positive-duration triggers aren't reliably handled
    # across calendar clients).
    if not _is_end_of_day(task.due):
        out.extend(_valarm_at_start())
    return out


def _valarm_at_start() -> list[str]:
    return [
        "BEGIN:VALARM",
        "TRIGGER:-PT0M",
        "ACTION:DISPLAY",
        "DESCRIPTION:Task due",
        "END:VALARM",
    ]


def _build_description(task: Task) -> str:
    parts = []
    if task.description:
        parts.append(task.description.strip())
    if task.notes:
        parts.append(task.notes.strip())
    parts.append(f"todo-bytes: {task.project} #{task.id}")
    return "\n\n".join(parts)


def _uid(task: Task) -> str:
    # Stable per (project, id). Same task across re-exports = same UID =
    # calendar updates the event in place instead of creating duplicates.
    # Project names can contain spaces — we slugify to keep UIDs safe across
    # calendar clients (some don't like whitespace in identifiers).
    return f"todo-bytes-{_slugify(task.project)}-{task.id}@todo-bytes"


def _slugify(text: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-")


def _is_end_of_day(dt: datetime) -> bool:
    return dt.hour == 23 and dt.minute == 59


def _floating_dt(dt: datetime) -> str:
    """Format as a floating local-time value (no TZID, no Z suffix)."""
    return dt.strftime("%Y%m%dT%H%M%S")


def _utc_now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11 TEXT value rules."""
    return (
        text.replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
    )
