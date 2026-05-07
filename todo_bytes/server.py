"""FastAPI server for the todo-bytes web UI.

Imports the same core (store, views, config) that the CLI uses — no duplicate
logic. Started by `todo ui`, served on the port from config (default 8765).
"""

from __future__ import annotations

import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

StatusLiteral = Literal["todo", "in-progress", "done", "hold", "cancelled"]

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from todo_bytes import config as cfg
from todo_bytes import store, views


WEB_DIR = Path(__file__).parent / "web"


# ---------- request models ----------

class CreateTaskRequest(BaseModel):
    list: str  # the project to add to (legacy field name kept for now)
    name: str
    due: Optional[datetime] = None
    tags: list[str] = []
    description: Optional[str] = None
    notes: Optional[str] = None


class UpdateTaskRequest(BaseModel):
    name: Optional[str] = None
    due: Optional[datetime] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = None
    priority: Optional[int] = None
    status: Optional[StatusLiteral] = None
    description: Optional[str] = None
    notes: Optional[str] = None


class ReorderRequest(BaseModel):
    ids: list[int]


class CreateListRequest(BaseModel):
    name: str


class UpdateProjectRequest(BaseModel):
    description: Optional[str] = None
    status: Optional[StatusLiteral] = None
    due: Optional[datetime] = None
    tags: Optional[list[str]] = None


# ---------- app factory ----------

def create_app() -> FastAPI:
    """Build the FastAPI app. Factory pattern so tests can spin up isolated copies."""
    app = FastAPI(title="todo-bytes UI", version="0.1.0")
    _mount_static_files(app)
    _register_root_route(app)
    _register_list_routes(app)
    _register_task_routes(app)
    _register_reorder_route(app)
    return app


# ---------- static + root ----------

def _mount_static_files(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


def _register_root_route(app: FastAPI) -> None:
    @app.get("/")
    def serve_index():
        return FileResponse(WEB_DIR / "index.html")


# ---------- list endpoints ----------

def _register_list_routes(app: FastAPI) -> None:
    @app.get("/api/lists")
    def get_lists():
        config = cfg.load_config()
        names = store.all_projects(config)
        return {
            "lists": [store.project_summary(n, config) for n in names],
            "default": config.default_list,
        }

    @app.get("/api/projects/{project_name}")
    def get_project(project_name: str):
        config = cfg.load_config()
        try:
            return store.project_summary(project_name, config)
        except store.ProjectNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))

    @app.patch("/api/projects/{project_name}")
    def patch_project(project_name: str, payload: UpdateProjectRequest):
        fields = payload.model_dump(exclude_unset=True)
        config = cfg.load_config()
        try:
            store.update_project(project_name, config=config, **fields)
        except store.ProjectNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return store.project_summary(project_name, config)

    @app.post("/api/lists", status_code=201)
    def create_list_endpoint(payload: CreateListRequest):
        config = cfg.load_config()
        try:
            store.create_list(payload.name, config)
        except store.ListAlreadyExistsError as err:
            raise HTTPException(status_code=409, detail=str(err))
        return store.list_summary(payload.name, config)

    @app.delete("/api/lists/{list_name}")
    def delete_list_endpoint(list_name: str):
        config = cfg.load_config()
        try:
            store.delete_list(list_name, config)
        except store.CannotDeleteDefaultListError as err:
            raise HTTPException(status_code=400, detail=str(err))
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return {"ok": True}


# ---------- task endpoints ----------

def _register_task_routes(app: FastAPI) -> None:
    @app.get("/api/tasks")
    def get_tasks(
        list: str,
        due: Optional[str] = None,
        due_from: Optional[str] = None,
        due_to: Optional[str] = None,
        statuses: Optional[list[str]] = Query(default=None),
    ):
        """Orthogonal date + status filters.

        - `due` (optional): today | tomorrow | week | next-week | overdue |
          no-due | custom. Omitted = no date filter (all dates).
        - `due_from` / `due_to` (ISO YYYY-MM-DD): required when due=custom.
        - `statuses` (repeatable): subset of todo|in-progress|done|hold|cancelled.
          Omitted = all statuses pass through.
        """
        config = cfg.load_config()
        tasks = _load_or_404(list, config)
        filtered = _apply_filters(tasks, due, due_from, due_to, statuses)
        sorted_tasks = _sort_for_filters(filtered, due, statuses)
        return {"list": list, "tasks": [t.to_dict() for t in sorted_tasks]}

    @app.post("/api/tasks", status_code=201)
    def create_task(payload: CreateTaskRequest):
        config = cfg.load_config()
        try:
            task = store.add_task(
                list_name=payload.list,
                name=payload.name,
                due=payload.due,
                tags=payload.tags,
                description=payload.description,
                notes=payload.notes,
                config=config,
            )
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return task.to_dict()

    @app.patch("/api/tasks/{list_name}/{task_id}")
    def update_task_endpoint(list_name: str, task_id: int, payload: UpdateTaskRequest):
        fields = payload.model_dump(exclude_unset=True)
        _manage_done_at_for_status_change(fields)
        config = cfg.load_config()
        try:
            task = store.update_task(list_name, task_id, config=config, **fields)
        except store.TaskNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return task.to_dict()

    @app.delete("/api/tasks/{list_name}/{task_id}")
    def delete_task_endpoint(list_name: str, task_id: int):
        config = cfg.load_config()
        try:
            store.delete_task(list_name, task_id, config=config)
        except store.TaskNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return {"ok": True}

    @app.post("/api/tasks/{list_name}/{task_id}/done")
    def mark_done_endpoint(list_name: str, task_id: int):
        config = cfg.load_config()
        try:
            task = store.mark_done(list_name, task_id, config=config)
        except store.TaskNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return task.to_dict()

    @app.post("/api/tasks/{list_name}/{task_id}/reopen")
    def reopen_endpoint(list_name: str, task_id: int):
        config = cfg.load_config()
        try:
            task = store.reopen_task(list_name, task_id, config=config)
        except store.TaskNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        except store.ListNotFoundError as err:
            raise HTTPException(status_code=404, detail=str(err))
        return task.to_dict()


# ---------- reorder ----------

def _register_reorder_route(app: FastAPI) -> None:
    @app.post("/api/lists/{list_name}/reorder")
    def reorder_tasks(list_name: str, payload: ReorderRequest):
        config = cfg.load_config()
        tasks = _load_or_404(list_name, config)
        _apply_new_priorities(tasks, payload.ids)
        store.save_tasks(list_name, tasks, config)
        return {"ok": True}


def _apply_new_priorities(tasks: list, ordered_ids: list[int]) -> None:
    """Set task.priority from the position in `ordered_ids`. Tasks not in the list keep their priority."""
    id_to_priority = {tid: i + 1 for i, tid in enumerate(ordered_ids)}
    for task in tasks:
        if task.id in id_to_priority:
            task.priority = id_to_priority[task.id]


def _manage_done_at_for_status_change(fields: dict) -> None:
    """If the PATCH body sets status, also keep done_at in sync.

    Going to done   → set done_at to now (if not already set)
    Going off done  → clear done_at
    """
    if "status" not in fields:
        return
    new_status = fields["status"]
    if new_status == "done":
        fields.setdefault("done_at", datetime.now())
    else:
        fields["done_at"] = None


# ---------- helpers shared by routes ----------

def _load_or_404(list_name: str, config: cfg.Config) -> list:
    try:
        return store.load_tasks(list_name, config)
    except store.ListNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err))


DATE_FILTERS = {
    "today": views.filter_today,
    "tomorrow": views.filter_tomorrow,
    "week": views.filter_this_week,
    "next-week": views.filter_next_week,
    "overdue": views.filter_overdue,
    "no-due": lambda ts: views.filter_no_due(ts),
}
MULTI_DAY_FILTERS = {"week", "next-week", "custom", "overdue"}


def _apply_filters(
    tasks: list,
    due: Optional[str],
    due_from: Optional[str],
    due_to: Optional[str],
    statuses: Optional[list[str]],
) -> list:
    """Apply the date filter then the status filter. Order doesn't matter
    semantically (both are 'AND') but date-first keeps the working set small."""
    filtered = _apply_date_filter(tasks, due, due_from, due_to)
    return views.filter_by_statuses(filtered, statuses)


def _apply_date_filter(
    tasks: list,
    due: Optional[str],
    due_from: Optional[str],
    due_to: Optional[str],
) -> list:
    if due is None:
        return tasks  # no date filter
    if due == "custom":
        return _apply_custom_range(tasks, due_from, due_to)
    if due not in DATE_FILTERS:
        raise HTTPException(status_code=400, detail=f"Unknown due filter: {due}")
    return DATE_FILTERS[due](tasks)


def _apply_custom_range(tasks: list, due_from: Optional[str], due_to: Optional[str]) -> list:
    if not due_from or not due_to:
        raise HTTPException(
            status_code=400,
            detail="due=custom requires both due_from and due_to (YYYY-MM-DD)",
        )
    try:
        start = date.fromisoformat(due_from)
        end = date.fromisoformat(due_to)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid date in due_from / due_to: {err}")
    return views.filter_in_date_range(tasks, start, end)


def _sort_for_filters(tasks: list, due: Optional[str], statuses: Optional[list[str]]) -> list:
    """Multi-day views sort by due-then-priority. A done-only status filter
    sorts by done_at desc. Everything else sorts by priority."""
    if due in MULTI_DAY_FILTERS:
        return views.sort_by_due_then_priority(tasks)
    if statuses and set(statuses) == {"done"}:
        return views.sort_by_done_at_desc(tasks)
    return views.sort_by_priority(tasks)


# ---------- runner (used by `todo ui`) ----------

def run_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    """Start the FastAPI server with uvicorn and optionally open a browser tab."""
    import uvicorn

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
