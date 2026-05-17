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
- User says "mark X done / reopen X / put X on hold / move X to project Y"
- User asks "show me my projects / how am I tracking on project Y"
- User wants a daily / weekly review
- User wants to sync tasks to Google Calendar

If the user is working in a different system (Jira, Linear, etc.), use the matching skill for that — `todo-bytes` is for personal local tasks.

## Quick reference

### Setup (run once)

```bash
todo init                              # interactive: pick data dir + default project
```

### Add tasks

```bash
todo add "Write the launch post"
todo add "Pay rent" --due tomorrow
todo add "Call dentist" --due 2026-05-15 --tag personal --tag health
todo add "Standup" --due "tomorrow 9am"               # natural date + time
todo add "Fix bug" --description "Auth issue from PR #234"
todo add "Review PR" --project work                   # specific project
todo add "Read paper" -p reading -t research          # short flags
```

### List tasks

```bash
todo list                              # active tasks (todo + in-progress), default project
todo list --today                      # due today
todo list --overdue                    # past due, not done
todo list --tomorrow                   # due tomorrow
todo list --week                       # due this week
todo list --next-week                  # due next week
todo list --no-due                     # tasks with no due date
todo list --done                       # completed (last 7 days)
todo list --all                        # everything regardless of status

# Cross-project (NEW)
todo list --all-projects               # tasks from every project, sorted by due then priority
todo list -A --today                   # short form of --all-projects
todo list -A --overdue --json          # great for LLM "show me everything urgent"

# Filters compose
todo list --today --tag work
todo list --overdue --tag urgent
todo list --project personal --week
```

### View / edit one task

```bash
todo show <id>                         # full details (or --json for structured)
todo show <id> --project personal      # if not in default project

todo edit <id> --name "New name"
todo edit <id> --due 2026-05-20
todo edit <id> --due "tomorrow 6pm"    # natural date + time
todo edit <id> --due clear             # remove due date
todo edit <id> --tag work --tag urgent # replaces existing tags
todo edit <id> --tag clear             # clear all tags
todo edit <id> --description "..."     # or 'clear'
todo edit <id> --status hold           # any of: todo, in-progress, done, hold, cancelled
todo edit <id> --priority 1            # move to top of priority order (1-indexed)
todo edit <id> --priority 3            # move to position 3
todo notes <id>                        # open $EDITOR for multi-line notes
```

### Task state changes

```bash
todo done <id>                         # mark done (sets status=done, stamps done_at)
todo reopen <id>                       # undo done — sets status=todo, clears done_at
todo rm <id>                           # delete
todo move <id> --to personal           # move between projects
```

### Projects

```bash
todo projects show                     # list all with counts + default marker
todo projects show work                # single project full details
todo projects show --json              # structured output

todo projects create <name>
todo projects delete <name>            # refuses to delete default
todo projects edit <name> --description "Day job" --status in-progress --tag office
todo projects edit <name> --due 2026-12-31 --tag clear

todo use <name>                        # set default project
```

### Google Calendar sync

```bash
todo sync setup                        # one-time interactive wizard
todo sync now                          # manual refresh of the ICS file
todo sync now --to /custom/path.ics    # one-off export to custom path
todo sync disable                      # stop auto-sync
```

Sync is one-way (todo-bytes is the source of truth). After setup, every task save auto-updates the ICS file. Subscribers (Google Calendar / Apple Calendar) poll the URL every few hours.

### Config

```bash
todo config show
todo config set data_dir <path>
todo config set default_project <name>
todo config set ui_port <number>
```

### Web UI (only when the user explicitly wants to see it)

```bash
todo ui                                # opens browser
todo ui --port 8888 --no-browser       # custom port, no browser
```

## Date formats accepted by `--due`

Bare dates (no time) become **end-of-day** (23:59:59):

- `today`, `tomorrow`
- Weekday names: `monday`, `tue`, `wednesday`, `thu`, …
- ISO date: `2026-05-20`

Date + time forms (any of these):

- `"today 6pm"`, `"today 18:00"`
- `"tomorrow 9am"`, `"tomorrow 09:30"`
- `"monday 9am"`, `"fri 17:00"`
- `"2026-05-10 6pm"`, `"2026-05-10 18:30"`
- ISO datetime: `2026-05-20T18:30`

AM/PM and 24h forms both work. `12am` is midnight, `12pm` is noon.

`clear` (on `edit` only) removes the due date.

## Task statuses

- `todo` (default) — not started
- `in-progress` — being worked on
- `done` — completed
- `hold` — paused / blocked
- `cancelled` — abandoned

Change status via:
- `todo done <id>` (shortcut for status=done, stamps done_at)
- `todo reopen <id>` (shortcut for status=todo, clears done_at)
- `todo edit <id> --status hold` (any of the 5 values)

Status changes automatically sync `done_at`: going to `done` sets it to now; any other status clears it.

## Task fields

| Field | Meaning | How to set it |
|---|---|---|
| `id` | Per-project integer (each project starts from 1) | Auto |
| `name` | What the task is | `--name` on add/edit |
| `priority` | Position in priority order (1 = top) | Auto on add; `todo edit --priority N` to move; UI drag |
| `status` | `todo` / `in-progress` / `done` / `hold` / `cancelled` | `todo edit --status` / `done` / `reopen` |
| `due` | Due datetime, end-of-day default | `--due` (see date formats above) |
| `tags` | List of strings | `--tag` (repeatable) |
| `project` | Parent project (read-only here) | Set via `--project` on add, or `todo move` |
| `description` | Short summary / context | `--description` |
| `notes` | Multi-line free-form text | `todo notes <id>` opens $EDITOR |
| `created` | When task was created | Auto |
| `done_at` | When task was completed | Auto (synced with status) |

## Common agent flows

**"What's on my plate today?"**
```bash
todo list --today                      # default project only
todo list -A --today --json            # across all projects, structured
```

**"What's overdue right now?"**
```bash
todo list -A --overdue --json
```

**"Add 'Standup prep' for tomorrow at 9am tagged work"**
```bash
todo add "Standup prep" --due "tomorrow 9am" --tag work
```

**"Mark task 5 done"**
```bash
todo done 5
# Non-default project:
todo done 5 --project personal
```

**"I marked 5 done by mistake, undo it"**
```bash
todo reopen 5
```

**"Put 5 on hold, I'm blocked"**
```bash
todo edit 5 --status hold
```

**"Move task 5 to the personal project"**
```bash
todo move 5 --to personal
```

**"Make task 5 the top priority"**
```bash
todo edit 5 --priority 1
```

**"What projects do I have? How am I tracking on 'work'?"**
```bash
todo projects show                     # all projects overview
todo projects show work --json         # full details for one project
```

**"Plan my day" (review)**
1. `todo list -A --overdue --json` — what's slipping across everything
2. `todo list -A --today --json` — what's due today
3. `todo list --no-due` — uncommitted work that could be promoted
4. Suggest a focused list of 3-5 items

**"Sync my tasks to Google Calendar"**
```bash
todo sync setup
```
Interactive wizard — walks the user through file path, sharing on Drive, and Google Calendar subscribe. After that, auto-sync runs on every task save.

## Output format

The CLI uses Rich tables by default (good for humans). For agent / programmatic use, **always prefer `--json`** when supported:

```bash
todo list --json
todo show <id> --json
todo projects show --json
todo projects show <name> --json
```

JSON output is clean, structured, and round-trips through the YAML store.

`--json` is supported on: `list`, `show`, `projects show`.
Not yet on: `add`, `edit`, `done`, `reopen`, `move` (these print short success lines).

### Agent tip — terminal width (only for non-JSON output)

When parsing Rich tables, run with `COLUMNS=200` (or higher) so long task names don't wrap:

```bash
COLUMNS=200 todo list --all
COLUMNS=200 todo show 3
```

But if you're parsing programmatically, just use `--json` and skip this.

## Where data lives

- **Config:** `~/.config/todo-bytes/config.yaml` — data dir, default project, UI port, optional `ics_export_path`
- **Data:** the user-chosen data dir (see `todo config show`). One YAML file per project (e.g. `work.yaml`, `personal.yaml`)
- **ICS feed (if sync set up):** wherever the user configured (typically inside Google Drive folder)

The agent should never edit YAML files directly. Use the CLI — it preserves schema versioning and atomic writes.

## Multi-project model

- Each project has its own YAML file with metadata (name, description, status, due, tags) + a `tasks:` list
- Task IDs are **per-project** (each project counts from 1 independently)
- `task.project` is auto-set; use `todo move <id> --to <other>` to change it
- `--all-projects` / `-A` on `todo list` is the cross-project view

## Default project

If `--project` / `-p` is omitted, the configured default project is used. Check with `todo config show` or change with `todo use <name>`.

## What this skill covers

- ✅ Task CRUD (add / list / show / edit / done / reopen / rm)
- ✅ Status changes (todo / in-progress / done / hold / cancelled)
- ✅ Priority via `--priority N` or UI drag
- ✅ Move tasks between projects
- ✅ Project CRUD (create / show / edit / delete)
- ✅ Multi-line notes via `todo notes` ($EDITOR)
- ✅ Google Calendar / Apple Calendar sync (one-way ICS feed)
- ✅ JSON output for structured parsing

## What this skill does NOT cover

- Shared/team task lists — single-user local tool
- Recurring tasks — workaround: use a tag like `recurring` and recreate after `todo done`
- Sub-tasks / dependencies — not supported
- Two-way Google Tasks sync — only one-way ICS subscription is supported

## Errors the agent should handle gracefully

- `Project '<name>' not found` → suggest `todo projects show` to see real project names
- `Task <id> not found in <project>` → suggest `todo list` to list current ids
- `Cannot delete '<name>' — it is the default project` → suggest `todo use <other>` first
- `Source and target projects must differ` (on move) → the user already has the task there
- `<file> declares schema_version=N, but this build only understands up to M` → user needs to upgrade: `uv tool install --force 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'`
