<p align="center">
  <img src="todo_bytes/web/logo.svg" alt="todo-bytes logo" width="96" />
</p>

<p align="center">
  <a href="https://github.com/rishitamrakar/todo-bytes/releases/latest"><img src="https://img.shields.io/github/v/release/rishitamrakar/todo-bytes?label=release&color=blue" alt="Latest release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT" /></a>
</p>

# todo-bytes

A minimal todo app. Tasks live in plain YAML files on your disk. Drive everything from a small browser UI or a `todo` CLI.

> **Status:** v1.1.0 — feature-complete for v1. See [Releases](https://github.com/rishitamrakar/todo-bytes/releases) for version history.

## Why

- **Plain text first** — YAML is git-friendly, hand-editable, syncs via Dropbox/iCloud.
- **No database, no cloud, no lock-in** — your tasks are just files.
- **Multi-project** — separate `work`, `personal`, `side-projects` projects, each with its own YAML file.
- **One CLI everywhere** — same commands for you, scripts, cron, or AI agents (Claude, Pi).

## Install

Pick one based on whether you want the web UI:

```bash
# CLI + web UI (recommended)
pipx install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'

# CLI only (smaller install, no FastAPI/uvicorn)
pipx install git+https://github.com/rishitamrakar/todo-bytes.git
```

## First-time setup

```bash
todo init                                   # asks where tasks live + default project name
```

That's it. After this you can use the web UI or the CLI — they share the same data.

## Web UI

```bash
todo ui                                     # opens http://127.0.0.1:8765 in your browser
```

<p align="center">
  <img src="docs/screenshots/ui.png" alt="todo-bytes web UI" width="900" />
</p>

What it gives you:
- Sidebar with all projects (status dot + counts + default marker) and an `All Projects` cross-project view
- Top bar with **due-date chips** (Today / Tomorrow / Week / Next Week / Overdue / No due / Custom range) and a **status filter**
- Click `+ Add task` to open a side panel with all fields editable
- Click any task to edit in the same side panel — change project from the dropdown to move tasks between projects
- Drag rows to reorder priority — saved instantly to YAML
- Light / dark theme toggle

## CLI

For scripts, cron, agents, or when you just want to type:

```bash
todo add "write blog post" --due tomorrow --tag blog
todo add "review PR" --due today --tag work
todo list                                   # open tasks
todo done 1                                 # mark done
todo edit 2 --due 2026-08-01
todo rm 2                                   # delete
```

### Multiple projects

```bash
todo projects show                          # all projects + counts
todo projects create personal               # new project
todo use personal                           # switch default
todo add "buy groceries" --project personal
```

Use `--project <name>` (or `-p`) on any task command. Each project keeps its own IDs (work has 1, 2, 3... and personal has 1, 2, 3...).

### Filter what you see

```bash
todo list --today                           # due today
todo list --overdue                         # past due
todo list --week                            # this week
todo list --tag work                        # tagged 'work'
todo list --today --tag work                # combine
```

Other view flags: `--tomorrow`, `--next-week`, `--no-due`, `--done`, `--all`.

Dates accept `today`, `tomorrow`, weekday names (`mon`, `friday`...), or ISO `YYYY-MM-DD`.

## For AI agents (Pi, Claude Code)

todo-bytes ships with an agent skill. Install it where your agent looks for skills:

```bash
todo skill install                          # default → ~/.agents/skills/todo-bytes/
todo skill install --dir ~/my-skills        # custom parent dir
todo skill install --dir .                  # install in current dir
```

The default path is created recursively if it doesn't exist. The agent reads `SKILL.md` and uses the `todo` CLI to manage your tasks for you.

## Upgrading

```bash
pipx reinstall todo-bytes                   # pulls latest from git
```

If reinstall fails, force install over the top:

```bash
pipx install --force 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

Upgrades only touch the code. Your config and tasks are never touched.

## Where things live

| What | Path |
|---|---|
| Code (the `todo` command) | `~/.local/pipx/venvs/todo-bytes/` (managed by pipx) |
| Global config | `~/.config/todo-bytes/config.yaml` |
| Your tasks (data) | `<data_dir>/<project-name>.yaml` (you pick `data_dir` at `todo init`) |

## More docs

- **[INSTALL.md](INSTALL.md)** — full install, upgrade, uninstall, multi-machine setup
- **[docs/DEVELOPER.md](docs/DEVELOPER.md)** — dev setup, design notes, schema versioning, contributing

## License

MIT — see [LICENSE](LICENSE).
