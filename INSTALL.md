# Installation Guide

## Quick Install (Recommended)

### Using pipx (Isolated Environment)

```bash
# 1. Install pipx (one-time setup)
brew install pipx  # macOS
# or: pip install --user pipx
pipx ensurepath    # Add to PATH

# 2. Install startd8
pipx install startd8

# Or install from local source
pipx install -e /path/to/startd8-sdk-project
```

**That's it!** startd8 is now installed in its own isolated environment.

### Using the Install Script

```bash
# Install with pipx (recommended)
./install.sh pipx

# Or install with standard pip
./install.sh pip
```

## Why pipx?

- ✅ **Complete isolation** - Won't conflict with your other Python projects
- ✅ **Easy updates** - `pipx upgrade startd8`
- ✅ **Clean uninstall** - `pipx uninstall startd8`
- ✅ **Standard tool** - Used by popular tools like `black`, `pytest`, `poetry`

## Alternative: Standard pip Installation

If you need to import startd8 as a library in your Python code:

```bash
cd startd8-sdk-project
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

**Note:** Use a virtual environment to avoid conflicts:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Verify Installation

```bash
# Check installation
startd8 --help

# Run the TUI
startd8 tui

# List templates
startd8 templates
```

## Troubleshooting

### pipx not found

```bash
# Install pipx
brew install pipx  # macOS
# or
pip install --user pipx

# Add to PATH
pipx ensurepath
source ~/.zshrc  # or restart terminal
```

### Command not found after pipx install

```bash
# Check pipx installation
pipx list

# Verify PATH includes pipx
echo $PATH | grep pipx

# Reinstall
pipx reinstall startd8
```

### Permission errors

```bash
# Fix pipx permissions
pipx ensurepath
chmod +x ~/.local/bin/startd8
```

## Updating

```bash
# Update startd8 (pipx)
pipx upgrade startd8

# Update startd8 (pip)
pip install --upgrade -e /path/to/startd8-sdk-project
```

## Uninstalling

```bash
# Uninstall (pipx)
pipx uninstall startd8

# Uninstall (pip)
pip uninstall startd8
```

## Development Installation

For contributors who want to edit the source code:

```bash
# Clone repository
git clone <repository-url>
cd startd8-sdk-project

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

## Next Steps

After installation:

1. **Set API keys** (if using real agents):
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   export OPENAI_API_KEY="sk-..."
   ```

2. **Initialize a workspace**:
   ```bash
   startd8 init
   ```

3. **Try the TUI**:
   ```bash
   startd8 tui
   ```

4. **Read the docs**:
   - [Quick Start Guide](../QUICKSTART.md)
   - [Setup Guide](../SETUP_GUIDE.md)
   - [Full README](README.md)

