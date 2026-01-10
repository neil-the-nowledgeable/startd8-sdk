# UV Guide for startd8-mcp-builder

Practical commands for managing Python deps with **uv** in this project.

## Install uv (one-time)
```bash
brew install uv
```

## Project Quickstart
```bash
cd /Users/neilyashinsky/Documents/Startd8/mcp/startd8-mcp-builder
uv sync                 # create .venv and install deps from pyproject.toml
source .venv/bin/activate
python3 test_server.py  # run a quick smoke test
```

## Common Tasks

### Add dependencies
```bash
uv add package-name              # add runtime dep
uv add --dev pytest pytest-asyncio  # add dev deps (goes to dependency-groups.dev)
```

### Remove dependencies
```bash
uv remove package-name
uv remove --dev pytest
```

### Update dependencies
```bash
uv sync --upgrade       # update all
uv add package-name@latest  # bump a single dep
```

### Lockfile
uv writes a lockfile (`uv.lock`). Commit it for reproducible installs.

### Virtual environment
- Created at `.venv/` by `uv sync`
- Activate: `source .venv/bin/activate`
- Deactivate: `deactivate`

### Run scripts
```bash
source .venv/bin/activate
python3 startd8_mcp.py
python3 test_server.py
```

### Clean & reinstall
```bash
rm -rf .venv uv.lock
uv sync
```

## pyproject.toml Basics
- `[project]` lists runtime deps.
- `[tool.uv.dependency-groups]` holds dev deps (replaces deprecated dev-dependencies).
- `uv sync` reads both and installs into `.venv`.

## Troubleshooting
- **Command not found:** `brew install uv`
- **Wrong Python:** ensure `requires-python = ">=3.11"` is satisfied; `python3 --version`
- **Stale env:** remove `.venv/` and re-run `uv sync`

That’s it—`uv sync` is your main entry point for keeping deps in sync. 🚀
