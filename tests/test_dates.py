"""Tests for todo_bytes.dates — friendly date parsing."""

from __future__ import annotations

from datetime import date

import pytest

from todo_bytes.dates import parse_due


def test_today():
    today = date(2026, 5, 6)
    assert parse_due("today", today=today) == today


def test_tomorrow():
    today = date(2026, 5, 6)
    assert parse_due("tomorrow", today=today) == date(2026, 5, 7)


def test_weekday_full_name():
    # 2026-05-06 is a Wednesday. "friday" should be 2 days later.
    today = date(2026, 5, 6)
    assert parse_due("friday", today=today) == date(2026, 5, 8)


def test_weekday_short_name():
    today = date(2026, 5, 6)  # Wed
    assert parse_due("fri", today=today) == date(2026, 5, 8)
    assert parse_due("mon", today=today) == date(2026, 5, 11)


def test_weekday_same_day_jumps_to_next_week():
    """If today is Wednesday and user says 'wednesday', they mean *next* Wed, not today."""
    today = date(2026, 5, 6)  # Wed
    assert parse_due("wed", today=today) == date(2026, 5, 13)


def test_iso_date():
    assert parse_due("2026-05-10") == date(2026, 5, 10)


def test_case_insensitive():
    today = date(2026, 5, 6)
    assert parse_due("TODAY", today=today) == today
    assert parse_due("Tomorrow", today=today) == date(2026, 5, 7)
    assert parse_due("FRIDAY", today=today) == date(2026, 5, 8)


def test_strips_whitespace():
    today = date(2026, 5, 6)
    assert parse_due("  today  ", today=today) == today


def test_empty_raises():
    with pytest.raises(ValueError):
        parse_due("")


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_due("not-a-date")


def test_bad_iso_raises():
    with pytest.raises(ValueError):
        parse_due("2026-13-01")  # invalid month
