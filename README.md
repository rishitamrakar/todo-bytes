<p align="center">
  <img src="todo_bytes/web/logo.svg" alt="todo-bytes logo" width="96" />
</p>

# todo-bytes

A minimal todo app. Tasks live in plain YAML files on your disk. Drive everything from a `todo` CLI or a small browser UI.

> **Status:** v1.1.0 — feature-complete for v1.

## Why

- **Plain text first** — YAML is git-friendly, hand-editable, syncs via Dropbox/iCloud.
- **No database, no cloud, no lock-in** — your tasks are just files.
- **Multi-project** — separate `work`, `personal`, `side-projects` projects, each with its own YAML file.
- **One CLI everywhere** — same commands for you, scripts, cron, or AI agents (Claude, Pi).

## Install

```bash
pipx install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
todo init
```

That's it. `[ui]` adds the web UI — drop it if you only want the CLI.

## Quick start

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

### Web UI

```bash
todo ui                                     # http://127.0.0.1:8765
```

Sidebar with all projects, due-date chips and status filter at the top, drag rows to reorder priority, light/dark theme — full add/edit/done from the browser.

### For AI agents (Pi, Claude Code)

todo-bytes ships with an agent skill. Install it where your agent looks for skills:

```bash
todo skill install                          # → ~/.agents/skills/todo-bytes/
todo skill install --dir ~/my-skills        # → custom location
```

The agent reads `SKILL.md` and uses the `todo` CLI to manage your tasks for you.

## Where things live

| What | Path |
|---|---|
| Code (the `todo` command) | `~/.local/pipx/venvs/todo-bytes/` (managed by pipx) |
| Global config | `~/.config/todo-bytes/config.yaml` |
| Your tasks (data) | `<data_dir>/<project-name>.yaml` (you pick `data_dir` at `todo init`) |

Upgrades only touch the code. Your config and tasks are never touched.

## More docs

- **[INSTALL.md](INSTALL.md)** — full install, upgrade, uninstall, multi-machine setup
- **[docs/DEVELOPER.md](docs/DEVELOPER.md)** — dev setup, design notes, schema versioning, contributing

## License

MIT — see [LICENSE](LICENSE).
