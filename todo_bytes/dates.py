"""Friendly date parsing for --due flags.

Accepts:
  - today, tomorrow
  - weekday names: mon/monday, tue/tuesday, ... (next occurrence; same-day picks next week)
  - ISO format: 2026-05-10
"""

from __future__ import annotations

from datetime import date, timedelta


_WEEKDAYS = {
    "mon": 0, "monday": 0,
    "tue": 1, "tuesday": 1,
    "wed": 2, "wednesday": 2,
    "thu": 3, "thursday": 3,
    "fri": 4, "friday": 4,
    "sat": 5, "saturday": 5,
    "sun": 6, "sunday": 6,
}


def parse_due(text: str, today: date | None = None) -> date:
    """Parse a friendly date string into a date object. Raises ValueError on bad input."""
    if not text or not text.strip():
        raise ValueError("Empty date input")

    cleaned = text.strip().lower()
    today = today or date.today()

    if cleaned == "today":
        return today
    if cleaned == "tomorrow":
        return today + timedelta(days=1)
    if cleaned in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[cleaned])
    return _parse_iso_date(text)


def _next_weekday(today: date, target_weekday: int) -> date:
    """Return the next date that falls on `target_weekday` (0=Mon..6=Sun).

    If today is already that weekday, returns 7 days from now (next week's same day).
    """
    days_ahead = (target_weekday - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _parse_iso_date(text: str) -> date:
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(
            f"Could not parse date: {text!r}. "
            f"Use today, tomorrow, a weekday name, or YYYY-MM-DD."
        )
