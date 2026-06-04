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


def controlled_corpus_path(project_root: Optional[Path] = None) -> Path:
    """Path to the persistent Controlled Corpus registry (CONTROLLED_CORPUS FR-1).

    Project-scoped under ``<project_root>/.startd8/`` (or cwd's ``.startd8/`` when no
    root is given). The arg is the PROJECT ROOT — the ``.startd8`` segment is appended
    here, so callers pass ``project_root`` (not the data dir). Live-run fix: previously
    wrote to ``<project_root>/controlled-corpus.json`` (root pollution).
    """
    base = (Path(project_root) if project_root is not None else Path.cwd()) / ".startd8"
    return base / "controlled-corpus.json"


def corpus_content_dir(project_root: Optional[Path] = None) -> Path:
    """Durable proven-content store for the deterministic provider (FR-9).

    Project-scoped, sibling to controlled-corpus.json under ``<project_root>/.startd8/``.
    """
    base = (Path(project_root) if project_root is not None else Path.cwd()) / ".startd8"
    return base / "corpus-content"


def shared_corpus_path() -> Path:
    """Path to the (future) cross-project shared domain corpus (CONTROLLED_CORPUS OQ-5).

    v1 does NOT implement shared-corpus promotion (see Non-Requirements); this stub
    reserves the user-scoped location so the v2 promotion boundary has a home.
    """
    return default_config_dir() / "corpus" / "shared-corpus.json"

