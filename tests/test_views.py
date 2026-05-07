"""Tests for todo_bytes.views — pure filter and sort functions."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from todo_bytes import views
from todo_bytes.models import STATUS_DONE, STATUS_OPEN, Task


# ---------- helpers ----------

def make_task(id_: int, name: str = "x", due=None, status=STATUS_OPEN,
              priority: int = 1, tags=None, project=None, done_at=None) -> Task:
    # Tests pass plain dates for convenience — coerce to end-of-day datetime here
    # so Task is internally consistent (Task.due is Optional[datetime]).
    if isinstance(due, date) and not isinstance(due, datetime):
        due = datetime.combine(due, time(23, 59, 59))
    return Task(
        id=id_, name=name, priority=priority, status=status,
        due=due, tags=tags or [], project=project,
        created=datetime.now(), done_at=done_at,
    )


# Wednesday for predictable week math
WED = date(2026, 5, 6)


# ---------- predicates ----------

def test_is_open_and_is_done():
    assert views.is_open(make_task(1, status=STATUS_OPEN)) is True
    assert views.is_open(make_task(1, status=STATUS_DONE)) is False
    assert views.is_done(make_task(1, status=STATUS_DONE)) is True


# ---------- week bounds ----------

def test_week_bounds_wednesday():
    monday, sunday = views.week_bounds(WED)
    assert monday == date(2026, 5, 4)
    assert sunday == date(2026, 5, 10)


def test_week_bounds_monday():
    """Monday belongs to its own week, not the previous one."""
    monday, sunday = views.week_bounds(date(2026, 5, 4))
    assert monday == date(2026, 5, 4)
    assert sunday == date(2026, 5, 10)


def test_week_bounds_sunday():
    monday, sunday = views.week_bounds(date(2026, 5, 10))
    assert monday == date(2026, 5, 4)
    assert sunday == date(2026, 5, 10)


def test_next_week_bounds():
    monday, sunday = views.next_week_bounds(WED)
    assert monday == date(2026, 5, 11)
    assert sunday == date(2026, 5, 17)


# ---------- filter_today ----------

def test_filter_today_is_pure_date_filter():
    """Date filters are orthogonal to status — a done task due today still matches."""
    tasks = [
        make_task(1, due=WED),
        make_task(2, due=WED + timedelta(days=1)),
        make_task(3, due=WED, status=STATUS_DONE),  # done but due today — still included
        make_task(4, due=None),
    ]
    result = views.filter_today(tasks, today=WED)
    assert sorted(t.id for t in result) == [1, 3]


# ---------- filter_overdue ----------

def test_filter_overdue_excludes_today():
    tasks = [
        make_task(1, due=WED - timedelta(days=1)),  # yesterday
        make_task(2, due=WED - timedelta(days=5)),  # 5 days ago
        make_task(3, due=WED),                      # today — not overdue
        make_task(4, due=WED + timedelta(days=1)),  # tomorrow
    ]
    result = views.filter_overdue(tasks, today=WED)
    assert sorted(t.id for t in result) == [1, 2]


def test_filter_overdue_includes_all_statuses():
    """Pure date filter: a done task with a past due date is still 'overdue' by date.
    Caller composes filter_by_statuses() to narrow if needed."""
    tasks = [
        make_task(1, due=WED - timedelta(days=2), status=STATUS_DONE),
        make_task(2, due=WED - timedelta(days=2)),
    ]
    result = views.filter_overdue(tasks, today=WED)
    assert sorted(t.id for t in result) == [1, 2]


# ---------- filter_tomorrow ----------

def test_filter_tomorrow():
    tasks = [
        make_task(1, due=WED),
        make_task(2, due=WED + timedelta(days=1)),
        make_task(3, due=WED + timedelta(days=2)),
    ]
    result = views.filter_tomorrow(tasks, today=WED)
    assert [t.id for t in result] == [2]


# ---------- filter_this_week ----------

def test_filter_this_week_includes_monday_through_sunday():
    tasks = [
        make_task(1, due=date(2026, 5, 3)),   # last Sun — out
        make_task(2, due=date(2026, 5, 4)),   # Mon — in
        make_task(3, due=date(2026, 5, 6)),   # Wed — in
        make_task(4, due=date(2026, 5, 10)),  # Sun — in
        make_task(5, due=date(2026, 5, 11)),  # next Mon — out
    ]
    result = views.filter_this_week(tasks, today=WED)
    assert sorted(t.id for t in result) == [2, 3, 4]


def test_filter_this_week_excludes_no_due():
    tasks = [make_task(1, due=None)]
    assert views.filter_this_week(tasks, today=WED) == []


# ---------- filter_next_week ----------

def test_filter_next_week():
    tasks = [
        make_task(1, due=date(2026, 5, 10)),  # this Sun — out
        make_task(2, due=date(2026, 5, 11)),  # next Mon — in
        make_task(3, due=date(2026, 5, 17)),  # next Sun — in
        make_task(4, due=date(2026, 5, 18)),  # week after — out
    ]
    result = views.filter_next_week(tasks, today=WED)
    assert sorted(t.id for t in result) == [2, 3]


# ---------- filter_no_due ----------

def test_filter_no_due_returns_all_statuses():
    """Pure date filter — no-due-date matches regardless of status."""
    tasks = [
        make_task(1, due=None),
        make_task(2, due=WED),
        make_task(3, due=None, status=STATUS_DONE),
    ]
    result = views.filter_no_due(tasks)
    assert sorted(t.id for t in result) == [1, 3]


# ---------- filter_in_date_range (custom range) ----------

def test_filter_in_date_range_inclusive_on_both_ends():
    start = date(2026, 5, 4)
    end = date(2026, 5, 6)
    tasks = [
        make_task(1, due=date(2026, 5, 3)),  # day before start — out
        make_task(2, due=start),               # start — in
        make_task(3, due=date(2026, 5, 5)),    # mid — in
        make_task(4, due=end),                 # end — in
        make_task(5, due=date(2026, 5, 7)),    # day after end — out
        make_task(6, due=None),                # no due — out
    ]
    result = views.filter_in_date_range(tasks, start, end)
    assert sorted(t.id for t in result) == [2, 3, 4]


def test_filter_in_date_range_single_day():
    """start == end means the single date is the whole range."""
    target = date(2026, 5, 6)
    tasks = [
        make_task(1, due=target),
        make_task(2, due=date(2026, 5, 5)),
        make_task(3, due=date(2026, 5, 7)),
    ]
    result = views.filter_in_date_range(tasks, target, target)
    assert [t.id for t in result] == [1]


def test_filter_in_date_range_handles_swapped_bounds():
    """If start > end, treat them as a range anyway. Forgiving on caller error."""
    tasks = [make_task(1, due=date(2026, 5, 5))]
    result = views.filter_in_date_range(tasks, date(2026, 5, 7), date(2026, 5, 4))
    assert [t.id for t in result] == [1]


def test_filter_in_date_range_includes_datetime_within_end_day():
    """A task due 2026-05-12T18:30 is included when end=2026-05-12 (date compare)."""
    end = date(2026, 5, 12)
    tasks = [make_task(1, due=datetime(2026, 5, 12, 18, 30))]
    result = views.filter_in_date_range(tasks, date(2026, 5, 10), end)
    assert [t.id for t in result] == [1]


# ---------- filter_by_statuses ----------

def test_filter_by_statuses_keeps_only_matching():
    tasks = [
        make_task(1, status="todo"),
        make_task(2, status="in-progress"),
        make_task(3, status=STATUS_DONE),
        make_task(4, status="hold"),
    ]
    result = views.filter_by_statuses(tasks, ["todo", "hold"])
    assert sorted(t.id for t in result) == [1, 4]


def test_filter_by_statuses_none_or_empty_is_passthrough():
    """None / empty status set means 'no filter' — all tasks pass through."""
    tasks = [
        make_task(1, status="todo"),
        make_task(2, status=STATUS_DONE),
    ]
    assert sorted(t.id for t in views.filter_by_statuses(tasks, None)) == [1, 2]
    assert sorted(t.id for t in views.filter_by_statuses(tasks, [])) == [1, 2]


# ---------- filter_done_recent ----------

def test_filter_done_recent_default_7_days():
    now = datetime(2026, 5, 6, 12, 0)
    tasks = [
        make_task(1, status=STATUS_DONE, done_at=now - timedelta(days=1)),  # in
        make_task(2, status=STATUS_DONE, done_at=now - timedelta(days=8)),  # out (>7d)
        make_task(3, status=STATUS_OPEN),                                   # out (open)
        make_task(4, status=STATUS_DONE, done_at=None),                     # out (no done_at)
    ]
    result = views.filter_done_recent(tasks, now=now)
    assert [t.id for t in result] == [1]


def test_filter_done_recent_custom_window():
    now = datetime(2026, 5, 6, 12, 0)
    tasks = [
        make_task(1, status=STATUS_DONE, done_at=now - timedelta(days=20)),
        make_task(2, status=STATUS_DONE, done_at=now - timedelta(days=40)),
    ]
    result = views.filter_done_recent(tasks, days=30, now=now)
    assert [t.id for t in result] == [1]


# ---------- filter_all ----------

def test_filter_all_returns_everything():
    tasks = [
        make_task(1, status=STATUS_OPEN),
        make_task(2, status=STATUS_DONE),
    ]
    assert len(views.filter_all(tasks)) == 2


# ---------- filter_by_tag ----------

def test_filter_by_tag_single():
    tasks = [
        make_task(1, tags=["work"]),
        make_task(2, tags=["personal"]),
        make_task(3, tags=["work", "blog"]),
    ]
    result = views.filter_by_tag(tasks, ["work"])
    assert sorted(t.id for t in result) == [1, 3]


def test_filter_by_tag_and_match_for_multiple():
    tasks = [
        make_task(1, tags=["work"]),
        make_task(2, tags=["work", "blog"]),
        make_task(3, tags=["blog"]),
    ]
    result = views.filter_by_tag(tasks, ["work", "blog"])
    assert [t.id for t in result] == [2]


def test_filter_by_tag_empty_returns_all():
    tasks = [make_task(1), make_task(2)]
    assert len(views.filter_by_tag(tasks, [])) == 2


# ---------- filter_by_project ----------

def test_filter_by_project():
    tasks = [
        make_task(1, project="personal"),
        make_task(2, project="home"),
        make_task(3, project=None),
    ]
    result = views.filter_by_project(tasks, "personal")
    assert [t.id for t in result] == [1]


def test_filter_by_project_empty_returns_all():
    tasks = [make_task(1, project="personal"), make_task(2)]
    assert len(views.filter_by_project(tasks, "")) == 2


# ---------- sorting ----------

def test_sort_by_priority():
    tasks = [
        make_task(1, priority=3),
        make_task(2, priority=1),
        make_task(3, priority=2),
    ]
    result = views.sort_by_priority(tasks)
    assert [t.id for t in result] == [2, 3, 1]


def test_sort_by_due_then_priority_puts_no_due_last():
    tasks = [
        make_task(1, due=date(2026, 5, 10), priority=2),
        make_task(2, due=None, priority=1),
        make_task(3, due=date(2026, 5, 8), priority=5),
        make_task(4, due=date(2026, 5, 8), priority=1),  # same date, lower priority first
    ]
    result = views.sort_by_due_then_priority(tasks)
    assert [t.id for t in result] == [4, 3, 1, 2]


def test_sort_by_done_at_desc():
    now = datetime(2026, 5, 6, 12, 0)
    tasks = [
        make_task(1, done_at=now - timedelta(days=2)),
        make_task(2, done_at=now - timedelta(hours=1)),
        make_task(3, done_at=now - timedelta(days=5)),
    ]
    result = views.sort_by_done_at_desc(tasks)
    assert [t.id for t in result] == [2, 1, 3]
