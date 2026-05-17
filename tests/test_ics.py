"""Tests for the iCalendar (.ics) exporter.

Covers shape (header / footer / event count), field mapping, edge cases
(escaping, all-day vs timed, done tasks), and the CLI command.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from todo_bytes import ics
from todo_bytes.cli import app
from todo_bytes.models import Task


def make_task(**kwargs) -> Task:
    """Build a Task with sensible defaults so tests stay short."""
    defaults = {
        "id": 1,
        "name": "Write blog post",
        "priority": 1,
        "project": "work",
        "tags": [],
        "status": "todo",
        "description": None,
        "notes": None,
        "due": datetime(2026, 5, 20, 23, 59, 59),  # end-of-day = all-day
        "created": datetime(2026, 5, 1, 10, 0, 0),
        "done_at": None,
    }
    defaults.update(kwargs)
    return Task(**defaults)


# ---------- shape ----------

def test_render_ics_returns_valid_envelope():
    out = ics.render_ics([])
    assert out.startswith("BEGIN:VCALENDAR\r\n")
    assert out.endswith("END:VCALENDAR\r\n")
    assert "VERSION:2.0" in out
    assert "PRODID:" in out


def test_render_ics_includes_calendar_name():
    out = ics.render_ics([], calendar_name="my tasks")
    assert "X-WR-CALNAME:my tasks" in out


def test_empty_task_list_produces_no_events():
    out = ics.render_ics([])
    assert "BEGIN:VEVENT" not in out


def test_task_without_due_is_skipped():
    out = ics.render_ics([make_task(due=None)])
    assert "BEGIN:VEVENT" not in out


def test_one_task_produces_one_event():
    out = ics.render_ics([make_task()])
    assert out.count("BEGIN:VEVENT") == 1
    assert out.count("END:VEVENT") == 1


# ---------- field mapping ----------

def test_summary_uses_task_name():
    out = ics.render_ics([make_task(name="Buy milk")])
    assert "SUMMARY:Buy milk" in out


def test_uid_is_stable_and_uses_project_and_id():
    a = ics.render_ics([make_task(id=7, project="home")])
    b = ics.render_ics([make_task(id=7, project="home")])
    assert "UID:todo-bytes-home-7@todo-bytes" in a
    # UID is stable across re-exports — calendars update events in place
    # rather than duplicating them.
    a_uid_line = [l for l in a.splitlines() if l.startswith("UID:")][0]
    b_uid_line = [l for l in b.splitlines() if l.startswith("UID:")][0]
    assert a_uid_line == b_uid_line


def test_uid_slugifies_project_name_with_spaces():
    # Spaces and non-alphanumerics in project names get turned into hyphens
    # so UIDs stay portable across calendar clients.
    out = ics.render_ics([make_task(id=1, project="May 2026")])
    assert "UID:todo-bytes-May-2026-1@todo-bytes" in out
    assert "UID:todo-bytes-May 2026-1" not in out  # no raw space


def test_tags_become_categories():
    out = ics.render_ics([make_task(tags=["work", "urgent"])])
    assert "CATEGORIES:work,urgent" in out


def test_description_combines_description_and_notes():
    task = make_task(description="Quick brief", notes="- bullet 1\n- bullet 2")
    out = ics.render_ics([task])
    # Both pieces should appear in the DESCRIPTION value (joined).
    desc_line = [l for l in out.splitlines() if l.startswith("DESCRIPTION:")][0]
    assert "Quick brief" in desc_line
    assert "bullet 1" in desc_line
    assert "bullet 2" in desc_line


def test_description_always_includes_provenance():
    out = ics.render_ics([make_task(project="home", id=42)])
    assert "todo-bytes: home #42" in out


# ---------- all-day vs timed ----------

def test_end_of_day_due_renders_as_all_day_event():
    out = ics.render_ics([make_task(due=datetime(2026, 5, 20, 23, 59, 59))])
    assert "DTSTART;VALUE=DATE:20260520" in out
    # DTEND for all-day events is the day after (exclusive end).
    assert "DTEND;VALUE=DATE:20260521" in out


def test_timed_due_renders_with_floating_local_time():
    out = ics.render_ics([make_task(due=datetime(2026, 5, 20, 14, 30, 0))])
    # No Z suffix, no TZID — floating local time so subscribing calendars
    # render in the viewer's own timezone.
    assert "DTSTART:20260520T143000" in out
    assert "DTEND:20260520T150000" in out  # 30-minute slot


def test_all_day_event_has_no_valarm():
    # We skip VALARM for all-day events — see ics.py for reasoning.
    out = ics.render_ics([make_task(due=datetime(2026, 5, 20, 23, 59, 59))])
    assert "BEGIN:VALARM" not in out


def test_timed_event_has_valarm_at_start():
    out = ics.render_ics([make_task(due=datetime(2026, 5, 20, 14, 30, 0))])
    assert "BEGIN:VALARM" in out
    assert "TRIGGER:-PT0M" in out


# ---------- status ----------

def test_active_task_is_confirmed():
    out = ics.render_ics([make_task(status="todo")])
    assert "STATUS:CONFIRMED" in out


def test_done_task_is_cancelled_and_has_no_alarm():
    out = ics.render_ics([make_task(status="done", due=datetime(2026, 5, 20, 14, 30, 0))])
    assert "STATUS:CANCELLED" in out
    assert "BEGIN:VALARM" not in out


def test_cancelled_task_is_cancelled():
    out = ics.render_ics([make_task(status="cancelled")])
    assert "STATUS:CANCELLED" in out


# ---------- escaping ----------

def test_special_characters_are_escaped():
    out = ics.render_ics([make_task(name="Meet John, Mary; bring notes\nplease")])
    # Per RFC 5545, "," and ";" and newline must be escaped in TEXT values.
    summary = [l for l in out.splitlines() if l.startswith("SUMMARY:")][0]
    assert "\\," in summary
    assert "\\;" in summary
    assert "\\n" in summary
    assert "\n" not in summary  # raw newline not allowed inside a value


# ---------- DTSTAMP ----------

def test_dtstamp_is_utc():
    out = ics.render_ics([make_task()])
    dtstamp = [l for l in out.splitlines() if l.startswith("DTSTAMP:")][0]
    # RFC 5545 requires DTSTAMP in UTC — ends with 'Z'.
    assert dtstamp.endswith("Z")


# ---------- Google Drive URL helpers ----------

def test_extract_drive_file_id_from_file_share_link():
    url = "https://drive.google.com/file/d/1AbC2dEfGh3IjKlMnOpQrStUvWxYz/view?usp=sharing"
    assert ics.extract_drive_file_id(url) == "1AbC2dEfGh3IjKlMnOpQrStUvWxYz"


def test_extract_drive_file_id_from_open_link():
    url = "https://drive.google.com/open?id=1AbC2dEfGh3IjKlMnOpQrStUvWxYz"
    assert ics.extract_drive_file_id(url) == "1AbC2dEfGh3IjKlMnOpQrStUvWxYz"


def test_extract_drive_file_id_returns_none_for_non_drive_url():
    assert ics.extract_drive_file_id("https://example.com/foo") is None
    assert ics.extract_drive_file_id("") is None


def test_drive_direct_download_url_format():
    url = ics.drive_direct_download_url("ABC123")
    assert url == "https://drive.google.com/uc?export=download&id=ABC123"


# ---------- CLI integration ----------

@pytest.fixture
def ready_to_use(fake_home: Path, runner: CliRunner) -> Path:
    """Run `todo init` and add a couple of tasks so export has something to work with."""
    data_dir = fake_home / "tasks"
    runner.invoke(
        app,
        ["init", "--data-dir", str(data_dir), "--default-project", "work", "--yes"],
    )
    runner.invoke(app, ["add", "Write post", "--due", "2026-05-20"])
    runner.invoke(app, ["add", "No due here"])  # skipped on export
    return data_dir


def test_sync_now_writes_ics_file_to_default_location(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["sync", "now"])
    assert result.exit_code == 0, result.stdout
    ics_path = ready_to_use / "tasks.ics"
    assert ics_path.exists()
    text = ics_path.read_text()
    assert "BEGIN:VCALENDAR" in text
    assert text.count("BEGIN:VEVENT") == 1  # the no-due task is skipped


def test_sync_now_writes_to_custom_path(ready_to_use: Path, runner: CliRunner, tmp_path: Path):
    custom = tmp_path / "subdir" / "my-tasks.ics"
    result = runner.invoke(app, ["sync", "now", "--to", str(custom)])
    assert result.exit_code == 0, result.stdout
    assert custom.exists()
    # Parent dir was created on the fly.
    assert custom.parent.is_dir()


def test_sync_now_reports_count_and_skipped(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["sync", "now"])
    assert result.exit_code == 0
    assert "1" in result.stdout  # 1 exported
    assert "skipped" in result.stdout  # 1 task without due was skipped


def test_sync_now_rejects_unknown_project(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["sync", "now", "--project", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.stdout.lower()


# ---------- auto-export ----------

from todo_bytes import config as cfg  # noqa: E402  (kept near tests that use it)


def test_auto_export_writes_on_task_save(ready_to_use: Path, runner: CliRunner, tmp_path: Path):
    """After `todo sync setup` configures ics_export_path, any task save
    (add, edit, done, etc.) should refresh the ICS file automatically."""
    target = tmp_path / "auto.ics"
    # Simulate what `sync setup` would do: set the config.
    config = cfg.load_config()
    config.ics_export_path = str(target)
    cfg.save_config(config)

    # Initially no file at the target.
    assert not target.exists()

    # Add a task. The save hook should write the ICS automatically.
    result = runner.invoke(app, ["add", "Triggered task", "--due", "2026-06-01"])
    assert result.exit_code == 0
    assert target.exists(), "Auto-export should have written the file on task save"
    text = target.read_text()
    assert "Triggered task" in text


def test_no_auto_export_when_not_configured(ready_to_use: Path, runner: CliRunner, tmp_path: Path):
    """Adding a task without ics_export_path set should NOT write any ICS."""
    accidental = tmp_path / "should-not-exist.ics"
    config = cfg.load_config()
    assert config.ics_export_path is None  # default
    runner.invoke(app, ["add", "Quiet task", "--due", "2026-06-01"])
    assert not accidental.exists()


def test_sync_disable_clears_config(ready_to_use: Path, runner: CliRunner, tmp_path: Path):
    target = tmp_path / "will-disable.ics"
    config = cfg.load_config()
    config.ics_export_path = str(target)
    cfg.save_config(config)

    result = runner.invoke(app, ["sync", "disable"])
    assert result.exit_code == 0
    assert "disabled" in result.stdout.lower()
    assert cfg.load_config().ics_export_path is None


def test_sync_disable_when_already_off_is_a_noop(ready_to_use: Path, runner: CliRunner):
    result = runner.invoke(app, ["sync", "disable"])
    assert result.exit_code == 0
    assert "already off" in result.stdout.lower()
