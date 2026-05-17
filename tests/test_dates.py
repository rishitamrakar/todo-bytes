"""Tests for todo_bytes.dates — friendly date parsing.

parse_due now returns datetime. Bare dates default to end-of-day (23:59:59).
Explicit ISO datetimes keep the given time.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from todo_bytes.dates import parse_due


def _eod(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time().replace(hour=23, minute=59, second=59))


def test_today():
    today = date(2026, 5, 6)
    assert parse_due("today", today=today) == _eod(today)


def test_tomorrow():
    today = date(2026, 5, 6)
    assert parse_due("tomorrow", today=today) == _eod(date(2026, 5, 7))


def test_weekday_full_name():
    today = date(2026, 5, 6)  # Wed
    assert parse_due("friday", today=today) == _eod(date(2026, 5, 8))


def test_weekday_short_name():
    today = date(2026, 5, 6)
    assert parse_due("fri", today=today) == _eod(date(2026, 5, 8))
    assert parse_due("mon", today=today) == _eod(date(2026, 5, 11))


def test_weekday_same_day_jumps_to_next_week():
    today = date(2026, 5, 6)  # Wed
    assert parse_due("wed", today=today) == _eod(date(2026, 5, 13))


def test_iso_date_becomes_end_of_day_datetime():
    assert parse_due("2026-05-10") == _eod(date(2026, 5, 10))


def test_iso_datetime_with_t_separator():
    assert parse_due("2026-05-10T15:30") == datetime(2026, 5, 10, 15, 30)


def test_iso_datetime_with_space_separator():
    assert parse_due("2026-05-10 15:30") == datetime(2026, 5, 10, 15, 30)


def test_case_insensitive():
    today = date(2026, 5, 6)
    assert parse_due("TODAY", today=today) == _eod(today)
    assert parse_due("Tomorrow", today=today) == _eod(date(2026, 5, 7))
    assert parse_due("FRIDAY", today=today) == _eod(date(2026, 5, 8))


def test_strips_whitespace():
    today = date(2026, 5, 6)
    assert parse_due("  today  ", today=today) == _eod(today)


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_due("")


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_due("not-a-date")


def test_bad_iso_raises():
    with pytest.raises(ValueError):
        parse_due("2026-13-01")  # invalid month


# ---------- friendlier date+time combos ----------

def test_today_with_pm_time():
    today = date(2026, 5, 6)
    assert parse_due("today 6pm", today=today) == datetime(2026, 5, 6, 18, 0)


def test_today_with_am_time():
    today = date(2026, 5, 6)
    assert parse_due("today 9am", today=today) == datetime(2026, 5, 6, 9, 0)


def test_tomorrow_with_24h_time():
    today = date(2026, 5, 6)
    assert parse_due("tomorrow 18:00", today=today) == datetime(2026, 5, 7, 18, 0)


def test_weekday_with_time():
    today = date(2026, 5, 6)  # Wednesday
    # Next Friday = 2026-05-08, at 9:30am
    assert parse_due("friday 9:30am", today=today) == datetime(2026, 5, 8, 9, 30)


def test_iso_date_with_pm_time():
    assert parse_due("2026-05-10 6pm") == datetime(2026, 5, 10, 18, 0)


def test_12pm_is_noon():
    today = date(2026, 5, 6)
    assert parse_due("today 12pm", today=today) == datetime(2026, 5, 6, 12, 0)


def test_12am_is_midnight():
    today = date(2026, 5, 6)
    assert parse_due("today 12am", today=today) == datetime(2026, 5, 6, 0, 0)


def test_invalid_time_falls_back_to_date_only_or_raises():
    # '99pm' isn't a valid time and isn't a valid bare time word, so the
    # whole thing should fail to parse (rather than silently dropping the time).
    with pytest.raises(ValueError):
        parse_due("today 99pm")
