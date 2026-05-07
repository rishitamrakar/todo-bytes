<p align="center">
  <img src="todo_bytes/web/logo.svg" alt="todo-bytes logo" width="96" />
</p>

# todo-bytes

Minimal todo app — tasks live in a YAML file, manage via CLI or a tiny browser UI.

> **Status:** Phases 1–5 are in place — setup, task CRUD, multiple lists, view filters, and a lightweight web UI with drag-to-reorder.

## What it is

- Tasks live in plain **YAML files** on your disk — no database, no cloud, no lock-in.
- One **`todo` CLI** for everything (add, list, edit, mark done).
- A **lightweight web UI** for viewing and reordering tasks (drag-drop priority).
- Source code and your task data are kept **separate** — pick any folder you want as your data dir.
- Works great as a back-end for an AI agent (e.g. Claude / pi) — the agent just shells out to `todo`.

## Why

I wanted something that is:
- Plain text first (yaml = git-friendly, hand-editable, syncs via Dropbox/iCloud easily).
- Multi-list — separate `work`, `personal`, `side-projects` lists.
- One-command setup, then forget about it.
- Scriptable from anywhere — CLI, UI, AI agent, cron — all using the same commands.

## Install

```bash
pipx install git+https://github.com/rishitamrakar/todo-bytes.git
todo init
```

That's it. See [INSTALL.md](INSTALL.md) for full setup details.

## Quick start

### Tasks (default list)
```bash
todo init                                    # one-time setup
todo add "write blog post" --due tomorrow --tag blog --project rb
todo add "review PR" --due today --tag work
todo list                                    # show open tasks
todo show 1                                  # full details
todo done 2                                  # mark done
todo edit 1 --name "new name" --due 2026-08-01
todo rm 1                                    # delete
```

### Multiple lists
```bash
todo lists show                              # see all lists with task counts
todo lists create personal                   # add a new list
todo lists delete personal                   # delete (asks for confirmation)
todo use personal                            # switch default list

# Use --list (or -l) to target a specific list on any task command
todo add "buy groceries" --list personal
todo list --list personal
todo done 1 --list personal
```

Every task command supports `--list <name>` (or `-l`). Without it, the configured default list is used.
Each list keeps its own task IDs (work has 1, 2, 3... and personal has 1, 2, 3... independently).

### Views (filter `todo list`)
```bash
todo list --today                            # due today
todo list --overdue                          # past due, still open
todo list --tomorrow                         # due tomorrow
todo list --week                             # this week (Mon–Sun)
todo list --next-week                        # next week
todo list --no-due                           # open tasks with no due date
todo list --done                             # done in last 7 days
todo list --all                              # everything (open + done)

# Tag and project filters compose with any view
todo list --tag work                         # all open tasks tagged work
todo list --today --tag work                 # today's work tasks only
todo list --tag work --tag blog              # AND match: must have both
todo list --week --project rb                # rb tasks due this week
todo list --today --list personal            # combine with --list
```

Only one view flag at a time (`--today --tomorrow` will error). `--tag` and `--project` can be added on top of any view.

### Dates
Dates accept: `today`, `tomorrow`, weekday names (`mon`, `friday`, ...), or ISO `YYYY-MM-DD`.
Use `--due clear` / `--project clear` / `--tag clear` to remove a field on edit.

### Config
```bash
todo config show                             # see where things live
todo config set default_list personal        # change default list (same as `todo use`)
todo config set data_dir ~/Dropbox/todos     # change where tasks live
```

### Web UI
```bash
todo ui                                      # starts on http://127.0.0.1:8765 and opens browser
todo ui --port 9000                          # custom port
todo ui --no-browser                         # don't open a browser tab
```

The UI has a sidebar with all lists (counts + default marker), top tabs for every view, and full add/edit/done/delete from the browser. Drag rows by the `⋮⋮` handle to reorder priority on the **Open** view — changes persist back to the YAML file instantly.

**Requires the `[ui]` extras** (FastAPI + uvicorn). See [INSTALL.md](INSTALL.md#install-from-the-repo) for the full install command.

## Where things live

Three separate places, each with one job:

| What | Path | What's in it |
|---|---|---|
| **Code** (the `todo` command) | `~/.local/pipx/venvs/todo-bytes/` (managed by pipx) | Python package + its dependencies |
| **Global config** | `~/.config/todo-bytes/config.yaml` | `data_dir`, `default_list`, `ui_port` |
| **Your tasks (data)** | `<data_dir>/<list-name>.yaml` (you pick `data_dir` at `todo init`) | All your tasks, plain YAML |

The global config tells the CLI **where** your data lives. You can edit it by hand, or use `todo config show` / `todo config set`.

Upgrades only touch the code. Your config and tasks are never touched. See [INSTALL.md — Upgrading](INSTALL.md#upgrading-to-the-latest-version) for the upgrade command.

## Design notes

```
You / Pi  →  CLI (todo)   ─┐
                           ├─→  core (store, models, views)  →  YAML files
UI (browser) → FastAPI    ─┘
```

- **CLI and UI share the same core** — no duplicate logic.
- **Data dir is picked by you** — keeps source code separate from your tasks.
- **YAML per list** — `work.yaml`, `personal.yaml`, etc., all in your data dir.

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

## Development

```bash
make install-dev      # creates .venv with dev + ui extras
source .venv/bin/activate
make test             # run the test suite
make test-cov         # run tests with coverage report
```

Tests run against an isolated fake `HOME` directory — they never touch your real `~/.config/todo-bytes` or your data dir.

## License

MIT — see [LICENSE](LICENSE).
