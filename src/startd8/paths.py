"""
Default directory conventions for Startd8.

Decision C (stabilization): split project data vs user config.

- Project data (prompts/responses/benchmarks/jobs): `./.startd8`
- User config (API keys, TUI settings, user templates): `~/.startd8`
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def default_data_dir() -> Path:
    """Default directory for project-scoped data."""
    return Path.cwd() / ".startd8"


def default_config_dir() -> Path:
    """Default directory for user-scoped configuration."""
    return Path.home() / ".startd8"


def resolve_data_dir(data_dir: Optional[Path]) -> Path:
    """Resolve an optional data directory to a concrete Path."""
    return Path(data_dir) if data_dir is not None else default_data_dir()


def resolve_config_dir(config_dir: Optional[Path]) -> Path:
    """Resolve an optional config directory to a concrete Path."""
    return Path(config_dir) if config_dir is not None else default_config_dir()

