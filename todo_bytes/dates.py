"""Friendly date parsing for --due flags.

Accepts (returns datetime):
  - today, tomorrow                          → end of that day (23:59:59)
  - weekday names: mon/monday, tue/tuesday   → end of that day
  - ISO date: 2026-05-10                     → end of that day
  - ISO datetime: 2026-05-10T15:30           → exact time
  - ISO datetime: 2026-05-10 15:30           → exact time
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

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
    """
    if not text or not text.strip():
        raise ValueError("Empty date input")

    cleaned = text.strip().lower()
    today = today or date.today()

    if cleaned == "today":
        return _end_of(today)
    if cleaned == "tomorrow":
        return _end_of(today + timedelta(days=1))
    if cleaned in _WEEKDAYS:
        return _end_of(_next_weekday(today, _WEEKDAYS[cleaned]))
    return _parse_iso(text)


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


def _parse_iso(text: str) -> datetime:
    """Try ISO datetime first, then ISO date (which becomes end-of-day datetime).

    Note: datetime.fromisoformat accepts date-only strings on Python 3.11+ and
    returns midnight. We want end-of-day for date-only input, so we detect
    'no time component' explicitly.
    """
    cleaned = text.strip()
    has_time = ("T" in cleaned) or (" " in cleaned and ":" in cleaned)
    iso_form = cleaned.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(iso_form)
    except ValueError:
        raise ValueError(
            f"Could not parse date: {text!r}. "
            f"Use today, tomorrow, a weekday name, YYYY-MM-DD, or YYYY-MM-DDTHH:MM."
        )
    if not has_time:
        return _end_of(parsed.date())
    return parsed
