# Installing todo-bytes

## Requirements

- Python 3.11 or newer
- An installer that isolates the `todo` command from your system Python. Pick one:
  - [`uv`](https://docs.astral.sh/uv/) (recommended — fast, can run tools without installing)
  - [`pipx`](https://pipx.pypa.io/stable/) (classic, widely used)

If you don't have either:
```bash
brew install uv         # or: brew install pipx && pipx ensurepath
```

## Install from the repo

Both installers work the same way — pick whichever you have.

### With uv (recommended)

```bash
# CLI only
uv tool install git+https://github.com/rishitamrakar/todo-bytes.git

# CLI + Web UI (FastAPI + uvicorn)
uv tool install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

### With pipx

```bash
# CLI only
pipx install git+https://github.com/rishitamrakar/todo-bytes.git

# CLI + Web UI (FastAPI + uvicorn)
pipx install 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'
```

### From a local clone

```bash
cd /path/to/todo-bytes
uv tool install '.[ui]'      # or: pipx install '.[ui]'
```

### Try without installing (uv only)

`uvx` runs the tool in a temporary environment — nothing gets installed permanently.

```bash
uvx --from git+https://github.com/rishitamrakar/todo-bytes.git todo --help
uvx --from git+https://github.com/rishitamrakar/todo-bytes.git todo list
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
~/.local/share/uv/tools/todo-bytes/    # if installed with uv
~/.local/pipx/venvs/todo-bytes/        # if installed with pipx
```

This is managed by your installer (uv or pipx). You never touch it directly. It contains the installed Python package plus all its dependencies (typer, pyyaml, rich, ...). Each tool lives in its own isolated environment so dependencies never clash.

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

Both installers re-pull from git on upgrade. Your tasks and config are **not** touched.

### With uv

```bash
uv tool upgrade todo-bytes
```

### With pipx

For pipx git installs, plain `pipx upgrade` does not re-pull from git. Use `reinstall` instead:

```bash
pipx reinstall todo-bytes
```

### If upgrade fails — force install over the top

Use the `[ui]` form if you want the web UI:

```bash
# uv
uv tool install --force 'todo-bytes[ui] @ git+https://github.com/rishitamrakar/todo-bytes.git'

# pipx
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
# uv
uv tool install --force 'git+https://github.com/rishitamrakar/todo-bytes.git@<branch-name>'

# pipx
pipx install --force git+https://github.com/rishitamrakar/todo-bytes.git@<branch-name>
```

## Uninstall

```bash
uv tool uninstall todo-bytes        # if installed with uv
pipx uninstall todo-bytes           # if installed with pipx
```

Your data dir and config file are not touched. Remove them manually if you want a clean slate:
```bash
rm -rf ~/.config/todo-bytes
rm -rf ~/my-todos       # only if you used the default
```

## Dev install (for hacking on the source)

### With uv (recommended — faster)

```bash
git clone https://github.com/rishitamrakar/todo-bytes.git
cd todo-bytes
uv venv
source .venv/bin/activate
uv pip install -e ".[dev,ui]"
todo version
```

### With plain pip

```bash
git clone https://github.com/rishitamrakar/todo-bytes.git
cd todo-bytes
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
todo version
```
