<p align="center">
  <img src="todo_bytes/web/logo.svg" alt="todo-bytes logo" width="96" />
</p>

<p align="center">
  <a href="https://github.com/rishitamrakar/todo-bytes/releases/latest"><img src="https://img.shields.io/github/v/release/rishitamrakar/todo-bytes?label=release&color=blue" alt="Latest release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT" /></a>
</p>

# todo-bytes

A simple todo app. Your tasks live in plain YAML files on your disk. Use the web UI or the `todo` CLI — same data, your choice.

## Install

```bash
brew install uv
uv tool install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

> Prefer pipx? See [INSTALL.md](INSTALL.md).

## Set up

```bash
todo init
```

It asks where to keep your tasks and the name of your first project. Done.

## Use the web UI

```bash
todo ui
```

Opens `http://127.0.0.1:8765` in your browser.

<p align="center">
  <img src="docs/screenshots/ui.png" alt="todo-bytes web UI" width="900" />
</p>

## Or use the CLI

```bash
todo add "write blog post" --due tomorrow
todo list                       # open tasks
todo done 1                     # mark done
todo edit 2 --due 2026-08-01
todo rm 2
```

More commands: `todo --help`.

## For AI agents (Pi, Claude Code)

```bash
todo skill install              # installs to ~/.agents/skills/todo-bytes/
```

Your agent can now manage tasks for you using the `todo` CLI.

## Upgrade

```bash
uv tool upgrade todo-bytes
```

Your tasks and config are never touched.

## More

- **[INSTALL.md](INSTALL.md)** — full install options (uv, pipx, dev), upgrade, uninstall, where files live
- **[docs/DEVELOPER.md](docs/DEVELOPER.md)** — dev setup, design notes, contributing

## License

MIT — see [LICENSE](LICENSE).
