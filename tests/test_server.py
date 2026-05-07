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
    """Init config + a 'work' project, then return a FastAPI TestClient."""
    data_dir = fake_home / "tasks"
    data_dir.mkdir(parents=True)
    (data_dir / "work.yaml").write_text(yaml.safe_dump({
        "project": {"name": "work", "status": "todo"},
        "tasks": [],
    }))
    config = cfg.Config(data_dir=str(data_dir), default_project="work", ui_port=8765)
    cfg.save_config(config)
    return TestClient(create_app())


# ---------- root + static ----------

def test_root_serves_index_html(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "todo-bytes" in response.text


# ---------- GET /api/projects ----------

def test_get_projects_returns_default_and_summary(client: TestClient):
    response = client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert data["default"] == "work"
    assert any(l["name"] == "work" for l in data["projects"])


def test_get_projects_shows_counts(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "a"})
    client.post("/api/tasks", json={"project": "work", "name": "b"})
    response = client.get("/api/projects")
    work_project = next(p for p in response.json()["projects"] if p["name"] == "work")
    assert work_project["open"] == 2
    assert work_project["done"] == 0


# ---------- POST /api/projects ----------

def test_create_project(client: TestClient):
    response = client.post("/api/projects", json={"name": "personal"})
    assert response.status_code == 201
    assert response.json()["name"] == "personal"
    listing = client.get("/api/projects").json()["projects"]
    assert any(l["name"] == "personal" for l in listing)


def test_create_project_rejects_duplicate(client: TestClient):
    response = client.post("/api/projects", json={"name": "work"})
    assert response.status_code == 409


# ---------- DELETE /api/projects/{name} ----------

def test_delete_non_default_project(client: TestClient):
    client.post("/api/projects", json={"name": "personal"})
    response = client.delete("/api/projects/personal")
    assert response.status_code == 200
    listing = client.get("/api/projects").json()["projects"]
    assert all(l["name"] != "personal" for l in listing)


def test_delete_default_project_refused(client: TestClient):
    response = client.delete("/api/projects/work")
    assert response.status_code == 400


def test_delete_missing_project(client: TestClient):
    response = client.delete("/api/projects/nope")
    assert response.status_code == 404


# ---------- project metadata endpoints ----------

def test_get_project_returns_metadata_and_counts(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "a"})
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


def test_get_projects_includes_project_status(client: TestClient):
    client.patch("/api/projects/work", json={"status": "in-progress"})
    response = client.get("/api/projects")
    work = next(l for l in response.json()["projects"] if l["name"] == "work")
    assert work["status"] == "in-progress"
    assert "completion_pct" in work


def test_patch_project_sets_tags(client: TestClient):
    response = client.patch("/api/projects/work", json={"tags": ["work", "client-A"]})
    assert response.status_code == 200
    assert response.json()["tags"] == ["work", "client-A"]


def test_get_projects_includes_project_tags(client: TestClient):
    client.patch("/api/projects/work", json={"tags": ["work"]})
    response = client.get("/api/projects")
    work = next(l for l in response.json()["projects"] if l["name"] == "work")
    assert work["tags"] == ["work"]


# ---------- task description + notes ----------

def test_create_task_with_description_and_notes(client: TestClient):
    payload = {
        "project": "work",
        "name": "big task",
        "description": "Auth bug from PR #234",
        "notes": "- looked at module X\n- found root cause\n- testing fix",
    }
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["description"] == "Auth bug from PR #234"
    assert "root cause" in body["notes"]


def test_patch_task_updates_description_and_notes(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    response = client.patch(
        "/api/tasks/work/1",
        json={"description": "updated", "notes": "- a\n- b"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["description"] == "updated"
    assert body["notes"] == "- a\n- b"


# ---------- POST /api/tasks ----------

def test_create_task_minimal(client: TestClient):
    response = client.post("/api/tasks", json={"project": "work", "name": "first"})
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["name"] == "first"
    assert body["status"] == "todo"


def test_create_task_with_all_fields(client: TestClient):
    payload = {
        "project": "work",
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


def test_create_task_in_missing_project(client: TestClient):
    response = client.post("/api/tasks", json={"project": "nope", "name": "x"})
    assert response.status_code == 404


# ---------- GET /api/tasks ----------

def test_get_tasks_no_filters_returns_everything(client: TestClient):
    """With no due / statuses params, all tasks pass through (orthogonal default)."""
    client.post("/api/tasks", json={"project": "work", "name": "a"})
    client.post("/api/tasks", json={"project": "work", "name": "b"})
    response = client.get("/api/tasks", params={"project": "work"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 2


def test_get_tasks_due_today_filter(client: TestClient):
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    client.post("/api/tasks", json={"project": "work", "name": "do today", "due": today})
    client.post("/api/tasks", json={"project": "work", "name": "do tomorrow", "due": tomorrow})
    response = client.get("/api/tasks", params={"project": "work", "due": "today"})
    names = [t["name"] for t in response.json()["tasks"]]
    assert names == ["do today"]


def test_get_tasks_due_today_includes_done_tasks(client: TestClient):
    """Date filter is orthogonal to status — done tasks due today still match.
    Caller filters by status separately when they want to hide them."""
    today = date.today().isoformat()
    client.post("/api/tasks", json={"project": "work", "name": "open today", "due": today})
    client.post("/api/tasks", json={"project": "work", "name": "done today", "due": today})
    client.post("/api/tasks/work/2/done")
    response = client.get("/api/tasks", params={"project": "work", "due": "today"})
    names = sorted(t["name"] for t in response.json()["tasks"])
    assert names == ["done today", "open today"]


def test_get_tasks_filter_by_statuses(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "todo task"})
    client.post("/api/tasks", json={"project": "work", "name": "done task"})
    client.post("/api/tasks/work/2/done")
    response = client.get("/api/tasks", params=[("project", "work"), ("statuses", "done")])
    names = [t["name"] for t in response.json()["tasks"]]
    assert names == ["done task"]


def test_get_tasks_filter_by_multiple_statuses(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "todo task"})
    client.post("/api/tasks", json={"project": "work", "name": "hold task"})
    client.patch("/api/tasks/work/2", json={"status": "hold"})
    response = client.get(
        "/api/tasks",
        params=[("project", "work"), ("statuses", "todo"), ("statuses", "hold")],
    )
    names = sorted(t["name"] for t in response.json()["tasks"])
    assert names == ["hold task", "todo task"]


def test_get_tasks_custom_date_range_inclusive(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "day-1", "due": "2026-05-04"})
    client.post("/api/tasks", json={"project": "work", "name": "day-2", "due": "2026-05-06"})
    client.post("/api/tasks", json={"project": "work", "name": "day-3", "due": "2026-05-08"})
    response = client.get(
        "/api/tasks",
        params={"project": "work", "due": "custom", "due_from": "2026-05-04", "due_to": "2026-05-06"},
    )
    names = sorted(t["name"] for t in response.json()["tasks"])
    assert names == ["day-1", "day-2"]


def test_get_tasks_custom_range_requires_both_bounds(client: TestClient):
    response = client.get("/api/tasks", params={"project": "work", "due": "custom", "due_from": "2026-05-04"})
    assert response.status_code == 400
    assert "due_to" in response.json()["detail"]


def test_get_tasks_invalid_due_filter(client: TestClient):
    response = client.get("/api/tasks", params={"project": "work", "due": "bogus"})
    assert response.status_code == 400


def test_get_tasks_missing_project(client: TestClient):
    response = client.get("/api/tasks", params={"project": "nope"})
    assert response.status_code == 404


# ---------- PATCH /api/tasks/{project}/{id} ----------

def test_patch_task_changes_name(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "original"})
    response = client.patch("/api/tasks/work/1", json={"name": "renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_patch_task_clears_project_with_null(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    response = client.patch("/api/tasks/work/1", json={"project": None})
    assert response.status_code == 200
    assert response.json()["project"] is None


def test_patch_task_skips_omitted_fields(client: TestClient):
    """Fields not in the payload should not be touched."""
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    # Set tags via patch
    client.patch("/api/tasks/work/1", json={"tags": ["keep"]})
    response = client.patch("/api/tasks/work/1", json={"name": "renamed"})
    body = response.json()
    assert body["name"] == "renamed"
    assert body["tags"] == ["keep"]  # untouched


def test_patch_task_missing(client: TestClient):
    response = client.patch("/api/tasks/work/99", json={"name": "x"})
    assert response.status_code == 404


# ---------- DELETE /api/tasks/{project}/{id} ----------

def test_delete_task(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    response = client.delete("/api/tasks/work/1")
    assert response.status_code == 200
    listing = client.get("/api/tasks", params={"project": "work"}).json()["tasks"]
    assert listing == []


def test_delete_task_missing(client: TestClient):
    response = client.delete("/api/tasks/work/99")
    assert response.status_code == 404


# ---------- POST /api/tasks/{project}/{id}/done ----------

def test_mark_task_done(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "finish me"})
    response = client.post("/api/tasks/work/1/done")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["done_at"] is not None


def test_mark_done_missing_task(client: TestClient):
    response = client.post("/api/tasks/work/99/done")
    assert response.status_code == 404


# ---------- POST /api/projects/{project}/reorder ----------

def test_reorder_updates_priority_by_position(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "a"})
    client.post("/api/tasks", json={"project": "work", "name": "b"})
    client.post("/api/tasks", json={"project": "work", "name": "c"})
    # New order: c, a, b
    response = client.post("/api/projects/work/reorder", json={"ids": [3, 1, 2]})
    assert response.status_code == 200
    config = cfg.load_config()
    tasks = {t.id: t.priority for t in store.load_tasks("work", config)}
    assert tasks[3] == 1
    assert tasks[1] == 2
    assert tasks[2] == 3


def test_reorder_missing_project(client: TestClient):
    response = client.post("/api/projects/nope/reorder", json={"ids": [1, 2]})
    assert response.status_code == 404


def test_reorder_partial_ids_only_affects_those(client: TestClient):
    """If reorder payload doesn't include all ids, untouched tasks keep their priority."""
    client.post("/api/tasks", json={"project": "work", "name": "a"})  # priority 1
    client.post("/api/tasks", json={"project": "work", "name": "b"})  # priority 2
    client.post("/api/tasks", json={"project": "work", "name": "c"})  # priority 3
    response = client.post("/api/projects/work/reorder", json={"ids": [2, 1]})
    assert response.status_code == 200
    config = cfg.load_config()
    tasks = {t.id: t.priority for t in store.load_tasks("work", config)}
    assert tasks[2] == 1
    assert tasks[1] == 2
    assert tasks[3] == 3  # untouched


# ---------- All Projects cross-project task actions (regression for 7.0) ----------
#
# In the All Projects view the UI must address each task by its own project,
# not by the '__all__' sentinel. These tests pin that contract: actions on
# tasks in a non-default project must succeed; the sentinel must never be
# accepted as a real project name.

def test_cross_project_task_actions_target_correct_project(client: TestClient):
    client.post("/api/projects", json={"name": "personal"})
    client.post("/api/tasks", json={"project": "work", "name": "work task"})
    client.post("/api/tasks", json={"project": "personal", "name": "personal task"})
    # Edit, mark done, reopen, delete — each addressed by the task's own project.
    assert client.patch("/api/tasks/personal/1", json={"name": "renamed"}).status_code == 200
    assert client.post("/api/tasks/personal/1/done").status_code == 200
    assert client.post("/api/tasks/personal/1/reopen").status_code == 200
    assert client.delete("/api/tasks/personal/1").status_code == 200
    # The work task is untouched.
    work_tasks = client.get("/api/tasks", params={"project": "work"}).json()["tasks"]
    assert len(work_tasks) == 1
    assert work_tasks[0]["name"] == "work task"


def test_all_projects_sentinel_is_not_a_real_project(client: TestClient):
    # The UI uses '__all__' as a sentinel for the cross-project view.
    # The backend must reject it as a project name so a UI bug surfaces clearly.
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    assert client.patch("/api/tasks/__all__/1", json={"name": "y"}).status_code == 404
    assert client.delete("/api/tasks/__all__/1").status_code == 404
    assert client.post("/api/tasks/__all__/1/done").status_code == 404
    assert client.post("/api/tasks/__all__/1/reopen").status_code == 404


# ---------- POST /api/tasks/{project}/{id}/move ----------

def test_move_task_endpoint_returns_new_task(client: TestClient):
    client.post("/api/projects", json={"name": "personal"})
    client.post("/api/tasks", json={"project": "work", "name": "to move"})
    response = client.post("/api/tasks/work/1/move", json={"to_project": "personal"})
    assert response.status_code == 200
    body = response.json()
    assert body["project"] == "personal"
    assert body["name"] == "to move"


def test_move_task_endpoint_removes_from_source(client: TestClient):
    client.post("/api/projects", json={"name": "personal"})
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    client.post("/api/tasks/work/1/move", json={"to_project": "personal"})
    work_tasks = client.get("/api/tasks", params={"project": "work"}).json()["tasks"]
    personal_tasks = client.get("/api/tasks", params={"project": "personal"}).json()["tasks"]
    assert work_tasks == []
    assert len(personal_tasks) == 1


def test_move_task_endpoint_to_missing_project(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    response = client.post("/api/tasks/work/1/move", json={"to_project": "nope"})
    assert response.status_code == 404


def test_move_task_endpoint_to_same_project_rejected(client: TestClient):
    client.post("/api/tasks", json={"project": "work", "name": "x"})
    response = client.post("/api/tasks/work/1/move", json={"to_project": "work"})
    assert response.status_code == 400


def test_move_task_endpoint_missing_task(client: TestClient):
    client.post("/api/projects", json={"name": "personal"})
    response = client.post("/api/tasks/work/99/move", json={"to_project": "personal"})
    assert response.status_code == 404
