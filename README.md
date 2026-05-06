# todo-bytes

Minimal todo app — tasks live in a YAML file, manage via CLI or a tiny browser UI.

> **Status:** Early development. Phase 1 (setup + config) is in place. CLI for tasks and the browser UI are coming next.

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
todo init                # one-time setup — pick a data dir, create your first list
todo config show         # see where things live
```

More commands (CLI for tasks, web UI) land in upcoming phases.

## Design notes

```
You / Pi  →  CLI (todo)   ─┐
                           ├─→  core (store, models, views)  →  YAML files
UI (browser) → FastAPI    ─┘
```

- **CLI and UI share the same core** — no duplicate logic.
- **Data dir is picked by you** — keeps source code separate from your tasks.
- **YAML per list** — `work.yaml`, `personal.yaml`, etc., all in your data dir.

## License

MIT — see [LICENSE](LICENSE).
