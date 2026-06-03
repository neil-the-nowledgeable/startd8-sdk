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


def controlled_corpus_path(data_dir: Optional[Path] = None) -> Path:
    """Path to the persistent Controlled Corpus registry (CONTROLLED_CORPUS FR-1).

    Project-scoped, mirroring the exemplar-registry convention.
    """
    return resolve_data_dir(data_dir) / "controlled-corpus.json"


def corpus_content_dir(data_dir: Optional[Path] = None) -> Path:
    """Durable proven-content store for the deterministic provider (FR-9).

    Project-scoped, sibling to controlled-corpus.json under .startd8/.
    """
    return resolve_data_dir(data_dir) / "corpus-content"


def shared_corpus_path() -> Path:
    """Path to the (future) cross-project shared domain corpus (CONTROLLED_CORPUS OQ-5).

    v1 does NOT implement shared-corpus promotion (see Non-Requirements); this stub
    reserves the user-scoped location so the v2 promotion boundary has a home.
    """
    return default_config_dir() / "corpus" / "shared-corpus.json"

