# Installing todo-bytes

## Requirements

- Python 3.11 or newer
- [`pipx`](https://pipx.pypa.io/stable/) (recommended) — installs the `todo` command globally without polluting your system Python.

If you don't have pipx:
```bash
brew install pipx
pipx ensurepath
```

## Install from the repo

### CLI only (recommended for most users)

```bash
pipx install git+https://github.com/rishitamrakar/todo-bytes.git
```

### CLI + Web UI

The web UI needs FastAPI and uvicorn. Install with the `[ui]` extras:

```bash
pipx install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

### From a local clone

```bash
cd /path/to/todo-bytes
pipx install '.[ui]'        # or just `pipx install .` for CLI only
```

### Verify
```bash
todo version
```

## Starting the web UI

```bash
todo ui                     # starts on the port from config (default 8765), opens browser
todo ui --port 9000         # custom port
todo ui --no-browser        # don't auto-open a browser tab
```

The UI runs on `http://127.0.0.1:<port>` and reads/writes the same YAML files as the CLI — changes from one show up in the other instantly. Press `Ctrl+C` in the terminal to stop the server.

If you installed without the `[ui]` extras, `todo ui` will print the exact reinstall command for you.

## First-time setup

Run the interactive setup:
```bash
todo init
```

You'll be asked:
1. **Where should your tasks live?** — a directory on your disk where the yaml files will be stored. Default is `~/my-todos`. You can put this in Dropbox/iCloud/a git repo for sync.
2. **Default project name?** — name of your first project. Default is `work`.

After init, you'll have:
```
~/.config/todo-bytes/config.yaml      ← global config (data dir, default project, UI port)
<your-data-dir>/work.yaml             ← your first project file
```

## Non-interactive setup

```bash
todo init --data-dir ~/Dropbox/todos --default-project personal --yes
```

## Updating config later

```bash
todo config show                          # see current config
todo config set data_dir ~/new/path       # change data dir
todo config set default_project personal  # change default project
todo config set ui_port 9000              # change UI port
```

## Where things live

Three separate places. Each has one job and is independent of the others.

### 1. Code (the `todo` command itself)

```
~/.local/pipx/venvs/todo-bytes/
```

This is managed by `pipx`. You never touch it directly. It contains the installed Python package plus all its dependencies (typer, pyyaml, rich, ...). Each pipx-installed tool lives in its own venv so dependencies never clash.

### 2. Global config

```
~/.config/todo-bytes/config.yaml
```

A tiny yaml file with three settings:

```yaml
data_dir: /Users/you/my-todos      # where your task yaml files are
default_project: work              # which project `todo` uses when --project is not passed
ui_port: 8765                      # which port the web UI runs on
```

It's created the first time you run `todo init`. You can read it with `todo config show`, change it with `todo config set <key> <value>`, or just open it in any editor.

### 3. Your tasks (the data)

```
<data_dir>/<project-name>.yaml
```

Where `<data_dir>` is whatever you picked at `todo init`. One yaml file per project:

```
~/my-todos/
├── work.yaml
├── personal.yaml
└── side-projects.yaml
```

This is **your data**. Plain text. Hand-editable. Git-friendly. Put `data_dir` inside Dropbox/iCloud/a private git repo to sync across machines.

### What this separation gives you

- **Upgrades never touch your tasks or config.** pipx only swaps the code venv.
- **Uninstalling `todo-bytes` leaves your data intact.** You'd have to delete `~/.config/todo-bytes/` and your data dir manually if you wanted a clean slate.
- **Multiple machines, same tasks.** Point `data_dir` at the same Dropbox folder on each machine, install `todo-bytes` on each, done.

## Upgrading to the latest version

For pipx git installs, plain `pipx upgrade` does not re-pull from git. Use `reinstall` instead:

```bash
pipx reinstall todo-bytes
```

This re-runs the install from the original git URL, so it pulls the latest `main`. Your tasks and config are **not** touched.

If `reinstall` fails for any reason, force-install over the top (use the `[ui]` form if you want the web UI):

```bash
pipx install --force git+https://github.com/rishitamrakar/todo-bytes.git
# or with web UI:
pipx install --force 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

Verify:
```bash
todo version
todo --help            # should show the latest commands
todo list              # your existing tasks should still be there
```

### Try a feature branch before it's merged

```bash
pipx install --force git+https://github.com/rishitamrakar/todo-bytes.git@<branch-name>
```

## Uninstall

```bash
pipx uninstall todo-bytes
```

Your data dir and config file are not touched. Remove them manually if you want a clean slate:
```bash
rm -rf ~/.config/todo-bytes
rm -rf ~/my-todos       # only if you used the default
```

## Dev install (for hacking on the source)

```bash
git clone https://github.com/rishitamrakar/todo-bytes.git
cd todo-bytes
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
todo version
```
