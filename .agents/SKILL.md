---
name: todo-bytes
description: Manage personal tasks and projects via the `todo` CLI. Use when the user mentions tasks, todos, reminders, projects, due dates, or wants to plan, capture, complete, or review work.
triggers:
  - todo
  - todos
  - task
  - tasks
  - remind me
  - what's on my plate
  - what's due
  - due today
  - mark done
  - complete
  - project
  - plan my day
---

# todo-bytes — agent usage skill

A local YAML-backed todo app. Tasks live in plain YAML files, one file per project, in the user's chosen data dir. Everything is driven by the `todo` CLI.

## When to use

- User says "add a task / remind me / capture this"
- User asks "what's on my plate / what's due today / show overdue"
- User says "mark X done / move X to in-progress"
- User asks "show me my projects / how am I tracking on project Y"
- User wants a daily / weekly review

If the user is working in a different system (Jira, Linear, etc.), use the matching skill for that — `todo-bytes` is for personal local tasks.

## Quick reference

```bash
# Initial setup (run once, then never again)
todo init                              # interactive: pick data dir + default project

# Add a task to the default project
todo add "Write the launch post"
todo add "Pay rent" --due tomorrow
todo add "Call dentist" --due 2026-05-15 --tag personal --tag health
todo add "Fix bug" --description "Auth issue from PR #234"

# Add to a specific project (not the default)
todo add "Review PR" --project work
todo add "Read paper" -p reading -t research

# List tasks in the default project
todo list                              # active tasks (todo + in-progress), sorted by priority
todo list --today                      # due today only
todo list --overdue                    # past due, not done
todo list --tomorrow                   # due tomorrow
todo list --week                       # due this week
todo list --next-week                  # due next week
todo list --no-due                     # tasks with no due date
todo list --done                       # completed tasks (most recent first)
todo list --all                        # everything regardless of status

# Filters compose with views
todo list --today --tag work           # today's work tasks
todo list --overdue --tag urgent
todo list --project personal --week    # this week in 'personal' project

# Other task commands
todo show <id>                         # full details: name, status, due, tags, description, notes, created
todo done <id>                         # mark done
todo rm <id>                           # delete
todo edit <id> --name "New name"
todo edit <id> --due 2026-05-20
todo edit <id> --due clear             # remove due date
todo edit <id> --tag work --tag urgent # replaces existing tags
todo edit <id> --tag clear             # clear all tags
todo edit <id> --description "Updated context"
todo edit <id> --description clear     # remove description

# Projects (renamed from "lists" but `lists` subcommand still works)
todo lists show                        # all projects with task counts + default marker
todo lists create <name>
todo lists delete <name>               # refuses to delete the default project
todo use <name>                        # set default project

# Config
todo config show
todo config set data_dir <path>
todo config set default_list <name>
todo config set ui_port <number>

# Web UI (only if you want to show the user a visual view)
todo ui                                # opens browser
todo ui --port 8888 --no-browser       # custom port, don't auto-open
```

## Date formats accepted by `--due`

- `today`, `tomorrow`
- Weekday names: `monday`, `tue`, `wednesday`, `thu`, …
- ISO date: `2026-05-20`
- ISO datetime: `2026-05-20T18:30`
- `clear` (only on `edit`) to remove the due date

Bare dates default to **end of day** (23:59:59), so `--due 2026-05-20` means "by end of that day".

## Task statuses

- `todo` (default) — not started
- `in-progress` — being worked on
- `done` — completed
- `hold` — paused / blocked
- `cancelled` — abandoned

`todo done <id>` sets status to `done` and stamps `done_at`. Status changes between others (e.g. `todo` ↔ `in-progress` ↔ `hold`) are done via `todo edit <id>` (and the value is set via the web UI, since CLI doesn't expose `--status` directly today).

## Task fields the agent should know

| Field | Meaning | How it's set |
|---|---|---|
| `id` | Per-project integer (each project counts from 1) | Auto |
| `name` | What the task is | `--name` on add/edit |
| `priority` | Position in the project (lower = top) | Auto on add; reorder via UI drag |
| `status` | `todo` / `in-progress` / `done` / `hold` / `cancelled` | `todo done`; UI status dropdown |
| `due` | Due datetime, end-of-day default | `--due` |
| `tags` | List of strings | `--tag` (repeatable) |
| `project` | Parent project (read-only, auto-set) | Inherited from `--project` |
| `description` | Short summary / context | `--description` |
| `notes` | Longer free-form text (multi-line, bullets typed manually with `- `) | UI only for now |
| `created` | When task was created | Auto |
| `done_at` | When task was completed | Auto on `todo done` |

## Common agent flows

**"What's on my plate today?"**
```bash
todo list --today
```
For all projects: loop over `todo lists show` projects and run `todo list --today --project <name>`, or just open the UI's "All Projects" view.

**"Add 'Review pricing doc' for tomorrow with tag work"**
```bash
todo add "Review pricing doc" --due tomorrow --tag work
```
(Goes to default project unless `--project` is specified.)

**"Show me everything overdue"**
```bash
todo list --overdue
```

**"Mark task 5 done"**
```bash
todo done 5
```
If the task is in a non-default project: `todo done 5 --project <name>`.

**"What projects do I have?"**
```bash
todo lists show
```
Returns project names with open / done / total counts and a `★` marker on the default.

**"Plan my day" (review)**
1. `todo list --overdue` — what's slipping
2. `todo list --today` — what's due
3. `todo list --no-due` — uncommitted work that could be promoted
4. Suggest a focused list of 3-5 items to do today

## Output format notes

The CLI uses Rich for formatted output (tables, colors). The output is human-readable but parseable for an agent:

- `todo list` → table with columns `id`, `name`, `due`, `tags`, `priority`, `status`
- `todo show <id>` → key-value table
- `todo lists show` → table with `name`, `open`, `done`, `total`, default marker
- Errors: red, prefixed with `[red]✗[/red]` (Rich tag in source; renders as colored text)
- Successes: green, prefixed with `✓`

When the agent needs structured data, it can parse the table output. There is no `--json` flag yet (deferred — see roadmap).

### Agent tip — terminal width

Rich auto-sizes tables to the terminal. In a non-TTY agent shell (e.g. running `todo` via a Bash tool), it falls back to a narrow default (~80 cols), which wraps long task names across multiple rows and looks truncated.

**Always prefix `todo list` / `todo show` with `COLUMNS=200`** when running from an agent:

```bash
COLUMNS=200 todo list --all
COLUMNS=200 todo show 3
```

Bump higher (e.g. `COLUMNS=240`) if task names are very long.

## Where data lives

- **Config:** `~/.config/todo-bytes/config.yaml` — points at data dir, default project, UI port
- **Data:** the user-chosen data dir (see `todo config show`). One YAML file per project (e.g. `work.yaml`, `personal.yaml`).

The agent should never edit YAML files directly. Use the CLI — it preserves schema versioning and atomic writes.

## Multi-project model

- Each project has its own YAML file with metadata (name, description, status, due, tags) + a `tasks:` list.
- Task IDs are **per-project** (each project counts from 1 independently).
- `task.project` is auto-set to the parent project — the agent doesn't pick it directly. To "move a task between projects" — not supported yet (see roadmap).

## Default project

If `--project / -p` is omitted, the configured default project is used. Check it with `todo config show` or set with `todo use <name>`.

## What this skill does NOT cover

- Shared/team task lists — todo-bytes is single-user local
- Recurring tasks — not in v1
- Sub-tasks / dependencies — not in v1
- Calendar sync — not in v1

If the user asks for any of these, say it's not supported and offer the closest workaround (e.g. for recurring tasks: a tag like `recurring` + a manual recreate after `todo done`).

## Errors the agent should handle gracefully

- `Project '<name>' not found` → suggest `todo lists show` to see real project names
- `Task <id> not found in <project>` → suggest `todo list` to list current ids
- `Cannot delete '<name>' — it is the default project` → suggest `todo use <other>` first
- `<file> declares schema_version=N, but this build only understands up to M` → user needs to upgrade todo-bytes (`pipx install --force ...`)
