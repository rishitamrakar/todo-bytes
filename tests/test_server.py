"""Tests for the FastAPI web UI endpoints.

Each test runs against an isolated fake HOME (via the existing fake_home
fixture) so they never touch the real config or data dir.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from todo_bytes import config as cfg
from todo_bytes import store
from todo_bytes.models import STATUS_DONE, STATUS_TODO
from todo_bytes.server import create_app


@pytest.fixture
def client(fake_home: Path) -> TestClient:
    """Init config + a 'work' list, then return a FastAPI TestClient."""
    data_dir = fake_home / "tasks"
    data_dir.mkdir(parents=True)
    (data_dir / "work.yaml").write_text(yaml.safe_dump({
        "project": {"name": "work", "status": "todo"},
        "tasks": [],
    }))
    config = cfg.Config(data_dir=str(data_dir), default_list="work", ui_port=8765)
    cfg.save_config(config)
    return TestClient(create_app())


# ---------- root + static ----------

def test_root_serves_index_html(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "todo-bytes" in response.text


# ---------- GET /api/lists ----------

def test_get_lists_returns_default_and_summary(client: TestClient):
    response = client.get("/api/lists")
    assert response.status_code == 200
    data = response.json()
    assert data["default"] == "work"
    assert any(l["name"] == "work" for l in data["lists"])


def test_get_lists_shows_counts(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "a"})
    client.post("/api/tasks", json={"list": "work", "name": "b"})
    response = client.get("/api/lists")
    work_list = next(l for l in response.json()["lists"] if l["name"] == "work")
    assert work_list["open"] == 2
    assert work_list["done"] == 0


# ---------- POST /api/lists ----------

def test_create_list(client: TestClient):
    response = client.post("/api/lists", json={"name": "personal"})
    assert response.status_code == 201
    assert response.json()["name"] == "personal"
    listing = client.get("/api/lists").json()["lists"]
    assert any(l["name"] == "personal" for l in listing)


def test_create_list_rejects_duplicate(client: TestClient):
    response = client.post("/api/lists", json={"name": "work"})
    assert response.status_code == 409


# ---------- DELETE /api/lists/{name} ----------

def test_delete_non_default_list(client: TestClient):
    client.post("/api/lists", json={"name": "personal"})
    response = client.delete("/api/lists/personal")
    assert response.status_code == 200
    listing = client.get("/api/lists").json()["lists"]
    assert all(l["name"] != "personal" for l in listing)


def test_delete_default_list_refused(client: TestClient):
    response = client.delete("/api/lists/work")
    assert response.status_code == 400


def test_delete_missing_list(client: TestClient):
    response = client.delete("/api/lists/nope")
    assert response.status_code == 404


# ---------- project metadata endpoints ----------

def test_get_project_returns_metadata_and_counts(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "a"})
    response = client.get("/api/projects/work")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "work"
    assert body["status"] == "todo"
    assert body["open"] == 1
    assert body["done"] == 0
    assert body["completion_pct"] == 0


def test_get_project_missing(client: TestClient):
    response = client.get("/api/projects/nope")
    assert response.status_code == 404


def test_patch_project_updates_description_and_status(client: TestClient):
    response = client.patch(
        "/api/projects/work",
        json={"description": "My main work tasks", "status": "in-progress"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "My main work tasks"
    assert body["status"] == "in-progress"


def test_patch_project_invalid_status(client: TestClient):
    response = client.patch("/api/projects/work", json={"status": "bogus"})
    assert response.status_code == 422  # Pydantic Literal rejects invalid status


def test_patch_project_missing(client: TestClient):
    response = client.patch("/api/projects/nope", json={"description": "x"})
    assert response.status_code == 404


def test_get_lists_includes_project_status(client: TestClient):
    client.patch("/api/projects/work", json={"status": "in-progress"})
    response = client.get("/api/lists")
    work = next(l for l in response.json()["lists"] if l["name"] == "work")
    assert work["status"] == "in-progress"
    assert "completion_pct" in work


def test_patch_project_sets_tags(client: TestClient):
    response = client.patch("/api/projects/work", json={"tags": ["work", "client-A"]})
    assert response.status_code == 200
    assert response.json()["tags"] == ["work", "client-A"]


def test_get_lists_includes_project_tags(client: TestClient):
    client.patch("/api/projects/work", json={"tags": ["work"]})
    response = client.get("/api/lists")
    work = next(l for l in response.json()["lists"] if l["name"] == "work")
    assert work["tags"] == ["work"]


# ---------- POST /api/tasks ----------

def test_create_task_minimal(client: TestClient):
    response = client.post("/api/tasks", json={"list": "work", "name": "first"})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["name"] == "first"
    assert body["status"] == "todo"


def test_create_task_with_all_fields(client: TestClient):
    payload = {
        "list": "work",
        "name": "big task",
        "due": "2026-12-31T23:59:59",
        "tags": ["work", "blog"],
    }
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["due"].startswith("2026-12-31")
    assert body["tags"] == ["work", "blog"]
    assert body["project"] == "work"  # auto-set to the parent project


def test_create_task_in_missing_list(client: TestClient):
    response = client.post("/api/tasks", json={"list": "nope", "name": "x"})
    assert response.status_code == 404


# ---------- GET /api/tasks ----------

def test_get_tasks_open_view_default(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "a"})
    client.post("/api/tasks", json={"list": "work", "name": "b"})
    response = client.get("/api/tasks", params={"list": "work"})
    assert response.status_code == 200
    data = response.json()
    assert data["view"] == "open"
    assert len(data["tasks"]) == 2


def test_get_tasks_today_filter(client: TestClient):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    client.post("/api/tasks", json={"list": "work", "name": "do today", "due": today})
    client.post("/api/tasks", json={"list": "work", "name": "do tomorrow", "due": tomorrow})
    response = client.get("/api/tasks", params={"list": "work", "view": "today"})
    names = [t["name"] for t in response.json()["tasks"]]
    assert names == ["do today"]


def test_get_tasks_invalid_view(client: TestClient):
    response = client.get("/api/tasks", params={"list": "work", "view": "bogus"})
    assert response.status_code == 400


def test_get_tasks_missing_list(client: TestClient):
    response = client.get("/api/tasks", params={"list": "nope"})
    assert response.status_code == 404


# ---------- PATCH /api/tasks/{list}/{id} ----------

def test_patch_task_changes_name(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "original"})
    response = client.patch("/api/tasks/work/1", json={"name": "renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_patch_task_clears_project_with_null(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "x", "project": "rb"})
    response = client.patch("/api/tasks/work/1", json={"project": None})
    assert response.status_code == 200
    assert response.json()["project"] is None


def test_patch_task_skips_omitted_fields(client: TestClient):
    """Fields not in the payload should not be touched."""
    client.post("/api/tasks", json={"list": "work", "name": "x"})
    # Set tags via patch
    client.patch("/api/tasks/work/1", json={"tags": ["keep"]})
    response = client.patch("/api/tasks/work/1", json={"name": "renamed"})
    body = response.json()
    assert body["name"] == "renamed"
    assert body["tags"] == ["keep"]  # untouched


def test_patch_task_missing(client: TestClient):
    response = client.patch("/api/tasks/work/99", json={"name": "x"})
    assert response.status_code == 404


# ---------- DELETE /api/tasks/{list}/{id} ----------

def test_delete_task(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "x"})
    response = client.delete("/api/tasks/work/1")
    assert response.status_code == 200
    listing = client.get("/api/tasks", params={"list": "work"}).json()["tasks"]
    assert listing == []


def test_delete_task_missing(client: TestClient):
    response = client.delete("/api/tasks/work/99")
    assert response.status_code == 404


# ---------- POST /api/tasks/{list}/{id}/done ----------

def test_mark_task_done(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "finish me"})
    response = client.post("/api/tasks/work/1/done")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["done_at"] is not None


def test_mark_done_missing_task(client: TestClient):
    response = client.post("/api/tasks/work/99/done")
    assert response.status_code == 404


# ---------- POST /api/lists/{list}/reorder ----------

def test_reorder_updates_priority_by_position(client: TestClient):
    client.post("/api/tasks", json={"list": "work", "name": "a"})
    client.post("/api/tasks", json={"list": "work", "name": "b"})
    client.post("/api/tasks", json={"list": "work", "name": "c"})
    # New order: c, a, b
    response = client.post("/api/lists/work/reorder", json={"ids": [3, 1, 2]})
    assert response.status_code == 200
    config = cfg.load_config()
    tasks = {t.id: t.priority for t in store.load_tasks("work", config)}
    assert tasks[3] == 1
    assert tasks[1] == 2
    assert tasks[2] == 3


def test_reorder_missing_list(client: TestClient):
    response = client.post("/api/lists/nope/reorder", json={"ids": [1, 2]})
    assert response.status_code == 404


def test_reorder_partial_ids_only_affects_those(client: TestClient):
    """If reorder payload doesn't include all ids, untouched tasks keep their priority."""
    client.post("/api/tasks", json={"list": "work", "name": "a"})  # priority 1
    client.post("/api/tasks", json={"list": "work", "name": "b"})  # priority 2
    client.post("/api/tasks", json={"list": "work", "name": "c"})  # priority 3
    response = client.post("/api/lists/work/reorder", json={"ids": [2, 1]})
    assert response.status_code == 200
    config = cfg.load_config()
    tasks = {t.id: t.priority for t in store.load_tasks("work", config)}
    assert tasks[2] == 1
    assert tasks[1] == 2
    assert tasks[3] == 3  # untouched
