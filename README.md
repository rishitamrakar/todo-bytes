# todo-bytes

Minimal todo app — tasks live in a YAML file, manage via CLI or a tiny browser UI.

> **Status:** Early development. Phase 1 (setup + config) and Phase 2 (task CRUD on default list) are in place. Multiple lists, view filters, and the browser UI are coming next.

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
pipx install git+https://github.com/<your-user>/todo-bytes.git
todo init
```

That's it. See [INSTALL.md](INSTALL.md) for full setup details.

## Quick start

```bash
todo init                                    # one-time setup
todo add "write blog post" --due tomorrow --tag blog --project rb
todo add "review PR" --due today --tag work
todo list                                    # show open tasks
todo show 1                                  # full details
todo done 2                                  # mark done
todo edit 1 --name "new name" --due 2026-08-01
todo rm 1                                    # delete
todo config show                             # see where things live
```

Dates accept: `today`, `tomorrow`, weekday names (`mon`, `friday`, ...), or ISO `YYYY-MM-DD`.
Use `--due clear` / `--project clear` / `--tag clear` to remove a field on edit.

More commands (multiple lists, view filters, web UI) land in upcoming phases.

## Design notes

```
You / Pi  →  CLI (todo)   ─┐
                           ├─→  core (store, models, views)  →  YAML files
UI (browser) → FastAPI    ─┘
```

- **CLI and UI share the same core** — no duplicate logic.
- **Data dir is picked by you** — keeps source code separate from your tasks.
- **YAML per list** — `work.yaml`, `personal.yaml`, etc., all in your data dir.

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
