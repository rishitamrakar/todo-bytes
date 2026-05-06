"""Tests for todo_bytes.store — yaml read/write and CRUD on tasks."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from todo_bytes import config as cfg
from todo_bytes import store
from todo_bytes.models import STATUS_DONE, STATUS_OPEN, Task


# ---------- shared fixture ----------

@pytest.fixture
def setup_list(fake_home: Path):
    """Init config + an empty 'work' list, return the loaded Config."""
    data_dir = fake_home / "tasks"
    data_dir.mkdir(parents=True)
    (data_dir / "work.yaml").write_text(yaml.safe_dump({
        "project": {"name": "work", "status": "todo"},
        "tasks": [],
    }))
    config = cfg.Config(data_dir=str(data_dir), default_list="work", ui_port=8765)
    cfg.save_config(config)
    return config


# ---------- list_file_path ----------

def test_list_file_path(setup_list):
    config = setup_list
    assert store.list_file_path("work", config) == Path(config.data_dir) / "work.yaml"


# ---------- load / save ----------

def test_load_empty_list(setup_list):
    assert store.load_tasks("work", setup_list) == []


def test_load_missing_list_raises(setup_list):
    with pytest.raises(store.ListNotFoundError):
        store.load_tasks("nonexistent", setup_list)


def test_save_then_load_roundtrip(setup_list):
    task = Task(
        id=1, name="hello", priority=1,
        due=datetime(2026, 5, 10, 23, 59, 59),
        tags=["work", "blog"], project="rb",
    )
    store.save_tasks("work", [task], setup_list)
    loaded = store.load_tasks("work", setup_list)
    assert len(loaded) == 1
    assert loaded[0].id == 1
    assert loaded[0].name == "hello"
    assert loaded[0].due == datetime(2026, 5, 10, 23, 59, 59)
    assert loaded[0].tags == ["work", "blog"]
    assert loaded[0].project == "rb"


# ---------- helpers ----------

def test_next_task_id_empty():
    assert store.next_task_id([]) == 1


def test_next_task_id_increments():
    tasks = [Task(id=1, name="a", priority=1), Task(id=5, name="b", priority=2)]
    assert store.next_task_id(tasks) == 6


def test_next_priority_empty():
    assert store.next_priority([]) == 1


def test_next_priority_appends_to_bottom():
    tasks = [Task(id=1, name="a", priority=1), Task(id=2, name="b", priority=3)]
    assert store.next_priority(tasks) == 4


def test_find_task_returns_match():
    tasks = [Task(id=1, name="a", priority=1), Task(id=2, name="b", priority=2)]
    assert store.find_task(tasks, 2).name == "b"


def test_find_task_raises_when_missing():
    with pytest.raises(store.TaskNotFoundError):
        store.find_task([], 99)


# ---------- add ----------

def test_add_task_assigns_id_and_priority(setup_list):
    t1 = store.add_task("work", "first", config=setup_list)
    t2 = store.add_task("work", "second", config=setup_list)
    assert t1.id == 1 and t1.priority == 1
    assert t2.id == 2 and t2.priority == 2


def test_add_task_with_all_fields(setup_list):
    task = store.add_task(
        "work", "with stuff",
        due=datetime(2026, 5, 10, 23, 59, 59),
        tags=["a", "b"],
        config=setup_list,
    )
    assert task.due == datetime(2026, 5, 10, 23, 59, 59)
    assert task.tags == ["a", "b"]
    assert task.project == "work"  # auto-set to parent project name
    assert task.status == STATUS_OPEN
    assert task.done_at is None
    assert isinstance(task.created, datetime)


def test_add_task_persists_to_disk(setup_list):
    store.add_task("work", "persisted", config=setup_list)
    raw = yaml.safe_load(store.list_file_path("work", setup_list).read_text())
    assert len(raw["tasks"]) == 1
    assert raw["tasks"][0]["name"] == "persisted"


# ---------- update ----------

def test_update_task_changes_field(setup_list):
    task = store.add_task("work", "original", config=setup_list)
    updated = store.update_task("work", task.id, config=setup_list, name="renamed")
    assert updated.name == "renamed"
    # Persisted
    assert store.load_tasks("work", setup_list)[0].name == "renamed"


def test_update_task_partial_update(setup_list):
    """Only the fields passed in kwargs should change — other fields are untouched."""
    store.add_task("work", "keep me", config=setup_list)
    store.update_task("work", 1, config=setup_list, name="new name")
    task = store.find_task(store.load_tasks("work", setup_list), 1)
    assert task.name == "new name"
    assert task.project == "work"  # auto-set, untouched by partial update


def test_update_task_none_clears_field(setup_list):
    """Passing None *is* meaningful — it clears the field. Callers control what to pass."""
    store.add_task("work", "x", config=setup_list)
    store.update_task("work", 1, config=setup_list, due=None)
    task = store.find_task(store.load_tasks("work", setup_list), 1)
    assert task.due is None


def test_update_unknown_field_raises(setup_list):
    store.add_task("work", "x", config=setup_list)
    with pytest.raises(KeyError):
        store.update_task("work", 1, config=setup_list, bogus_field="x")


def test_update_missing_task_raises(setup_list):
    with pytest.raises(store.TaskNotFoundError):
        store.update_task("work", 999, config=setup_list, name="x")


# ---------- delete ----------

def test_delete_task_removes_it(setup_list):
    store.add_task("work", "a", config=setup_list)
    store.add_task("work", "b", config=setup_list)
    store.delete_task("work", 1, setup_list)
    remaining = store.load_tasks("work", setup_list)
    assert len(remaining) == 1
    assert remaining[0].id == 2


def test_delete_missing_task_raises(setup_list):
    with pytest.raises(store.TaskNotFoundError):
        store.delete_task("work", 99, setup_list)


# ---------- mark done ----------

def test_mark_done_sets_status_and_timestamp(setup_list):
    store.add_task("work", "do me", config=setup_list)
    done = store.mark_done("work", 1, setup_list)
    assert done.status == STATUS_DONE
    assert isinstance(done.done_at, datetime)


def test_mark_done_persists(setup_list):
    store.add_task("work", "do me", config=setup_list)
    store.mark_done("work", 1, setup_list)
    reloaded = store.find_task(store.load_tasks("work", setup_list), 1)
    assert reloaded.status == STATUS_DONE
    assert reloaded.done_at is not None


def test_mark_done_missing_task_raises(setup_list):
    with pytest.raises(store.TaskNotFoundError):
        store.mark_done("work", 99, setup_list)


# ---------- list management ----------

def test_all_lists_empty(fake_home: Path):
    config = cfg.Config(data_dir=str(fake_home / "empty"), default_list="work", ui_port=8765)
    cfg.save_config(config)
    assert store.all_lists(config) == []


def test_all_lists_returns_sorted_names(setup_list):
    config = setup_list
    store.create_list("personal", config)
    store.create_list("side-projects", config)
    assert store.all_lists(config) == ["personal", "side-projects", "work"]


def test_list_exists(setup_list):
    assert store.list_exists("work", setup_list) is True
    assert store.list_exists("nope", setup_list) is False


def test_create_list_creates_yaml_file(setup_list):
    path = store.create_list("personal", setup_list)
    assert path.is_file()
    raw = yaml.safe_load(path.read_text())
    assert raw["project"]["name"] == "personal"
    assert raw["project"]["status"] == "todo"
    assert raw["tasks"] == []


def test_create_list_rejects_duplicate(setup_list):
    with pytest.raises(store.ListAlreadyExistsError):
        store.create_list("work", setup_list)


def test_delete_list_removes_yaml_file(setup_list):
    config = setup_list
    store.create_list("personal", config)
    store.delete_list("personal", config)
    assert not store.list_exists("personal", config)


def test_delete_list_refuses_default(setup_list):
    with pytest.raises(store.CannotDeleteDefaultListError):
        store.delete_list("work", setup_list)  # default in setup_list is 'work'


def test_delete_list_missing_raises(setup_list):
    with pytest.raises(store.ListNotFoundError):
        store.delete_list("nonexistent", setup_list)


def test_list_summary_counts(setup_list):
    config = setup_list
    store.add_task("work", "a", config=config)
    store.add_task("work", "b", config=config)
    store.add_task("work", "c", config=config)
    store.mark_done("work", 2, config)
    summary = store.list_summary("work", config)
    assert summary == {"name": "work", "open": 2, "done": 1, "total": 3}


def test_list_summary_empty_list(setup_list):
    summary = store.list_summary("work", setup_list)
    assert summary == {"name": "work", "open": 0, "done": 0, "total": 0}


def test_per_list_ids_are_independent(setup_list):
    config = setup_list
    store.create_list("personal", config)
    a = store.add_task("work", "work-1", config=config)
    b = store.add_task("work", "work-2", config=config)
    c = store.add_task("personal", "personal-1", config=config)
    d = store.add_task("personal", "personal-2", config=config)
    assert (a.id, b.id) == (1, 2)
    assert (c.id, d.id) == (1, 2)  # independent counter


# ---------- schema versioning ----------

def test_save_writes_current_schema_version(setup_list):
    """Every save must stamp schema_version so future migrations have a clear marker."""
    config = setup_list
    store.add_task("work", "a", config=config)
    raw = yaml.safe_load((Path(config.data_dir) / "work.yaml").read_text())
    assert raw["schema_version"] == store.CURRENT_SCHEMA_VERSION


def test_load_treats_missing_schema_version_as_v1(setup_list):
    """Legacy yaml files without schema_version must still load (forward-compat)."""
    config = setup_list
    path = Path(config.data_dir) / "work.yaml"
    # Setup fixture deliberately wrote no schema_version — confirm load works
    assert "schema_version" not in yaml.safe_load(path.read_text())
    tasks = store.load_tasks("work", config)
    assert tasks == []  # loads cleanly, no error


def test_load_rejects_future_schema_version(setup_list):
    """A yaml file from a newer build must raise a clear error, not silently misread."""
    config = setup_list
    path = Path(config.data_dir) / "work.yaml"
    payload = yaml.safe_load(path.read_text())
    payload["schema_version"] = store.CURRENT_SCHEMA_VERSION + 5
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(store.UnsupportedSchemaVersionError) as exc:
        store.load_tasks("work", config)
    assert "todo migrate" in str(exc.value)
