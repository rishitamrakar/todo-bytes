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

```bash
pipx install git+https://github.com/<your-user>/todo-bytes.git
```

Or, if you've cloned the repo locally:
```bash
cd /path/to/todo-bytes
pipx install .
```

Verify:
```bash
todo version
```

## First-time setup

Run the interactive setup:
```bash
todo init
```

You'll be asked:
1. **Where should your tasks live?** — a directory on your disk where the yaml files will be stored. Default is `~/my-todos`. You can put this in Dropbox/iCloud/a git repo for sync.
2. **Default list name?** — name of your first list. Default is `work`.

After init, you'll have:
```
~/.config/todo-bytes/config.yaml      ← global config (data dir, default list, UI port)
<your-data-dir>/work.yaml             ← your first task list
```

## Non-interactive setup

```bash
todo init --data-dir ~/Dropbox/todos --default-list personal --yes
```

## Updating config later

```bash
todo config show                          # see current config
todo config set data_dir ~/new/path       # change data dir
todo config set default_list personal     # change default list
todo config set ui_port 9000              # change UI port
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
git clone <repo-url>
cd todo-bytes
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ui]"
todo version
```
