"""Friendly date parsing for --due flags.

Accepts (returns datetime):
  - today, tomorrow                          → end of that day (23:59:59)
  - weekday names: mon/monday, tue/tuesday   → end of that day
  - ISO date: 2026-05-10                     → end of that day
  - ISO datetime: 2026-05-10T15:30           → exact time
  - ISO datetime: 2026-05-10 15:30           → exact time

Also accepts a date + time combo (LLM / human-friendly):
  - today 6pm, today 18:00
  - tomorrow 9am, tomorrow 09:30
  - monday 9am, fri 17:00
  - 2026-05-10 6pm, 2026-05-10 18:30
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from todo_bytes.models import END_OF_DAY


_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def parse_due(text: str, today: date | None = None) -> datetime:
    """Parse a friendly date(time) string. Returns datetime. Raises ValueError on bad input.

    Bare dates (today / tomorrow / weekday / YYYY-MM-DD) become end-of-day datetimes.
    Explicit datetimes (YYYY-MM-DDTHH:MM) keep the given time.
    A date + time combo like `tomorrow 6pm` or `monday 09:30` becomes that
    specific datetime.
    """
    if not text or not text.strip():
        raise ValueError("Empty date input")

    today = today or date.today()
    date_part, time_part = _split_date_and_time(text.strip())
    base_date = _parse_date_part(date_part, today)
    if time_part is None:
        return _parse_date_only_or_iso(date_part, base_date)
    return datetime.combine(base_date, time_part)


def _split_date_and_time(text: str) -> tuple[str, time | None]:
    """Split a string like 'tomorrow 6pm' or '2026-05-10 18:00' into the
    date portion and a parsed time. ISO datetimes (with 'T') stay together.
    Returns (date_text, parsed_time_or_None).
    """
    if "T" in text:
        return text, None
    parts = text.rsplit(" ", 1)
    if len(parts) == 2 and _looks_like_time(parts[1]):
        return parts[0], _parse_time(parts[1])
    return text, None


def _parse_date_part(date_text: str, today: date) -> date:
    """Parse just the date portion: today / tomorrow / weekday / YYYY-MM-DD.

    For ISO datetimes (with 'T') we return the date component; the caller
    handles the time separately via _parse_date_only_or_iso.
    """
    cleaned = date_text.strip().lower()
    if cleaned == "today":
        return today
    if cleaned == "tomorrow":
        return today + timedelta(days=1)
    if cleaned in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[cleaned])
    # Fall back to ISO. For 'YYYY-MM-DDTHH:MM' we just need the date part.
    iso_form = date_text.strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(iso_form).date()
    except ValueError:
        raise ValueError(
            f"Could not parse date: {date_text!r}. "
            f"Use today, tomorrow, a weekday name, YYYY-MM-DD, or YYYY-MM-DDTHH:MM."
        )


def _parse_date_only_or_iso(original: str, base_date: date) -> datetime:
    """For inputs without an explicit time half (no '6pm' etc.):
    - ISO datetime in the original (e.g. '2026-05-10T15:30') keeps its time
    - everything else (today / tomorrow / weekday / bare YYYY-MM-DD) is end-of-day

    We detect ISO datetime by trying to parse it directly — simple words like
    'TODAY' contain a 'T' but aren't ISO, so a substring check isn't enough.
    """
    try:
        parsed = datetime.fromisoformat(original.strip())
        # fromisoformat returns midnight for date-only strings; we only
        # want to keep it if a time was actually specified.
        if parsed.time() != time(0, 0):
            return parsed
    except ValueError:
        pass
    return _end_of(base_date)


# Time formats we accept: '6pm', '6am', '6:30pm', '18:00', '09:30', '9am'.
_TIME_RE = re.compile(
    r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm)?$",
    re.IGNORECASE,
)


def _looks_like_time(text: str) -> bool:
    return bool(_TIME_RE.match(text.strip()))


def _parse_time(text: str) -> time:
    """Parse '6pm', '6:30pm', '18:00', etc. Returns a time. Raises on bad input."""
    m = _TIME_RE.match(text.strip())
    if not m:
        raise ValueError(f"Could not parse time: {text!r}")
    hour = int(m.group("hour"))
    minute = int(m.group("minute") or 0)
    meridiem = (m.group("meridiem") or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour < 24) or not (0 <= minute < 60):
        raise ValueError(f"Time out of range: {text!r}")
    return time(hour, minute)


def _end_of(d: date) -> datetime:
    return datetime.combine(d, END_OF_DAY)


def _next_weekday(today: date, target_weekday: int) -> date:
    """Return the next date that falls on `target_weekday` (0=Mon..6=Sun).

    If today is already that weekday, returns 7 days from now (next week's same day).
    """
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)



