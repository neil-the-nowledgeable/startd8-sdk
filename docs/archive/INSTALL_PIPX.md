# Installing startd8 with pipx

## Quick Start

```bash
# 1. Install pipx (one-time setup)
brew install pipx
pipx ensurepath  # Adds pipx to your PATH

# 2. Install startd8 in isolated environment
pipx install startd8

# 3. Use it!
startd8 tui
```

## Why pipx?

- ✅ **Isolated** - Won't conflict with your other Python projects
- ✅ **Clean** - Easy to uninstall: `pipx uninstall startd8`
- ✅ **Updated** - Easy to upgrade: `pipx upgrade startd8`
- ✅ **Standard** - Used by popular tools like `black`, `pytest`, `poetry`

## Development Installation

If you're developing startd8 itself:

```bash
# Install from local source
pipx install -e /path/to/startd8-sdk-project

# Or install in editable mode for development
cd /path/to/startd8-sdk-project
pipx inject startd8 -e .
```

## Troubleshooting

### pipx not found
```bash
# Add to your shell profile (~/.zshrc or ~/.bash_profile)
export PATH="$HOME/.local/bin:$PATH"
source ~/.zshrc  # or restart terminal
```

### Check installation
```bash
pipx list
# Should show: startd8 0.2.0

which startd8
# Should show: /Users/yourname/.local/bin/startd8
```

