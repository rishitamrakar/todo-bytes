# Developer guide

Everything you need if you want to hack on todo-bytes.

## Dev setup

```bash
git clone https://github.com/rishitamrakar/todo-bytes.git
cd todo-bytes
make install-dev          # creates .venv with dev + ui extras
source .venv/bin/activate
make test                 # run the test suite
make test-cov             # run tests with coverage report
```

Tests run against an isolated fake `HOME` directory — they never touch your real `~/.config/todo-bytes` or your data dir.

## Design

```
You / Pi  →  CLI (todo)   ─┐
                           ├─→  core (store, models, views)  →  YAML files
UI (browser) → FastAPI    ─┘
```

- **Core-first.** `store.py`, `models.py`, `views.py` are the contract. CLI, FastAPI, and (future) MCP are thin adapters around the same core. No logic duplication.
- **CLI and UI share the same core** — calls are direct (no HTTP between them).
- **Data dir is picked by the user** — source code stays separate from data.
- **YAML per project** — `work.yaml`, `personal.yaml`, etc.
- **Per-project IDs** — each project counts from 1.

## Project layout

```
todo_bytes/
├── cli.py              # Typer CLI entry point
├── server.py           # FastAPI app (web UI backend)
├── store.py            # YAML read/write, project + task CRUD
├── models.py           # Task dataclass, status constants
├── views.py            # Pure filter + sort functions
├── dates.py            # Friendly date parsing (today, tomorrow, weekday names)
├── config.py           # Global config (load/save/update)
├── web/                # Static frontend (HTML, CSS, JS, SVG)
└── skills/
    └── todo-bytes/     # Agent skill shipped with the package
        └── SKILL.md
```

Tests live in `tests/` and mirror the module layout.

## Schema versioning & migrations

Every yaml file is stamped with a `schema_version` at the top:

```yaml
schema_version: 1
project:
  name: work
  ...
tasks:
  - ...
```

This is the **on-disk format version**, separate from the app version (semver):

- **App version** (`1.0.0`, `1.1.0`, `1.0.1`, ...) follows semver — patch for fixes, minor for new features, major for breaking changes.
- **Schema version** only bumps when the yaml format breaks in an incompatible way. Adding a new optional field (e.g. `task.notes`) does **not** bump the schema.
- All `1.x.y` releases read and write `schema_version: 1`.
- A future `schema_version: 2` will ship with a `todo migrate` command that converts `1` → `2` in place, with a backup.
- Missing `schema_version` is treated as `1` (forward-compat for legacy files).
- An unknown / future `schema_version` raises a clear error telling you to upgrade.

You never need to edit `schema_version` by hand.

## Versioning policy

App semver and on-disk schema version are independent:

| Change | App version | Schema version |
|---|---|---|
| Bug fix | 1.0.0 → 1.0.1 | 1 |
| New feature, no format break | 1.0.0 → 1.1.0 | 1 |
| Breaking yaml format change | 1.0.0 → 2.0.0 | 2 |

`schema_version: 1` stays for all 1.x.y releases. Only bumps on real format breaks.

## Conventions

- **Functions stay small** — one function does one thing, 5–15 lines is the target.
- **Config-driven** — no hardcoded values; defaults live in `config.py` constants.
- **No `print()`** in core — use Rich's `Console` from the CLI side, or return values from core for the API side.
- **Tests use the `fake_home` fixture** — never touch the real `~/.config`.

## Running a single test file

```bash
pytest tests/test_store.py -v
pytest tests/test_cli.py::test_skill_install_copies_folder -v
```

## Releasing

1. Bump `version` in `pyproject.toml` and `todo_bytes/__init__.py` (if mirrored there).
2. Bump `schema_version` in `store.py` only if the YAML format breaks.
3. Update relevant docs.
4. Tag and push:
   ```bash
   git tag v1.x.y
   git push --tags
   ```
