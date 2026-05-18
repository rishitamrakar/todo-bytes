# Changelog

All notable changes to **todo-bytes** ship here. Versioning follows [SemVer](https://semver.org/); the on-disk schema version is tracked separately (see `plan.md`).

## [1.2.0] — 2026-05-17

The "agent-first" release. todo-bytes is now fully usable from any LLM agent (Pi via shell, Claude Code via MCP) with one-way Google Calendar sync for visibility.

### Added

#### Google Calendar sync
- `todo sync setup` — interactive wizard that auto-detects Google Drive, writes the ICS file, walks you through the share-link step, and saves the config
- `todo sync now` — manual one-off export to a custom path
- `todo sync disable` — turn off auto-sync
- Auto-export on every task save once configured (new `ics_export_path` config field)
- iCalendar generator (RFC 5545) with VALARMs at due times, stable per-task UIDs so re-exports update events in place

#### Claude Code MCP server
- `[mcp]` extra ships a fully MCP-compatible server (`todo-bytes-mcp`)
- 10 native tools exposed to Claude: `add_task`, `list_tasks`, `show_task`, `mark_done`, `reopen_task`, `update_task`, `move_task`, `delete_task`, `list_projects`, `project_summary`
- Architecture: thin shim over the `todo` CLI — same code path every agent uses, no logic duplication
- Setup: `claude mcp add todo-bytes -- todo-bytes-mcp`

#### CLI completeness (full parity with API)
- `todo reopen <id>` — undo a done/cancelled task back to `todo`
- `todo edit --status <s>` — change to any of the 5 statuses, auto-syncs `done_at`
- `todo edit --priority N` — move task to 1-indexed position
- `todo move <id> --to <project>` — move between projects via CLI
- `todo projects edit <name>` — update description, status, due, tags
- `todo projects show <name>` — single-project detail view
- `todo list --all-projects` / `-A` — cross-project task view
- `todo notes <id>` — opens `$EDITOR` for multi-line notes
- `todo upgrade` — wraps `uv tool install --force ...` so you don't have to remember the long command

#### Agent-friendly output
- `--json` flag on `todo list`, `todo show`, `todo projects show` — structured output for LLMs and scripts

#### Friendlier date parsing
- `--due "tomorrow 6pm"`, `"monday 9am"`, `"2026-05-10 18:30"` now parse correctly
- Both AM/PM and 24h forms supported

#### UI
- Filter / view selections now persist in localStorage (no reset on page refresh)
- Grouped task view when no due filter (Overdue / Today / Tomorrow / This week / Later / No due)
- Within-section drag-reorder merges into global priority order
- Status filter is now client-side only — progress bar reflects due-filtered tasks but ignores status filter
- Clearer chip labels: `Due: Any`, `Status: 3 of 5 / All / None`
- Stacked task row layout (title on top, meta below)
- Tag colour rotation (4 muted variants, deterministic by tag name)
- Visual polish: palette swap, typography scale, hover/active polish, logo gradient chip, quick-tip card

### Refactored
- `store.reorder_tasks` + `store.set_task_priority` extracted from `server.py` so CLI can call them directly
- `store.update_task` auto-syncs `done_at` when status changes — all callers (CLI, API, MCP) get consistent behaviour for free

### Tests
- 298 tests pass (up from 214 in v1.1.0). New coverage:
  - 32 for ICS generator + Drive URL helpers + auto-export hook
  - 38 for new CLI commands (reopen, edit --status/--priority, move, projects edit, projects show single, list --all-projects, --json output)
  - 20 for MCP server (subprocess mocks + end-to-end real-CLI flows)

### Infra
- GitHub Actions CI — `pytest` on every PR, required status check

## [1.1.0] — 2026-05-08

First public release. See `notes/phases-1-8-history.md` for the full pre-1.0 history.
