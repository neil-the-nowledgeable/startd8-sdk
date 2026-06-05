"""Manifest-driven scaffold generator (class-2 determinism — project plumbing).

The second deterministic-generation class: project plumbing that is derivable from a small declared
``app.yaml`` (not the schema) — ``pyproject.toml`` (the #1 rebuild blocker), rotating file logging,
the Alembic baseline (``t-migrations``), and a ``Dockerfile``. Owned, $0 LLM, drift-checked,
build-gated; registered on the shared ``deterministic_providers`` entry-point group.
"""

from __future__ import annotations

from .drift import is_owned_scaffold_file, scaffold_in_sync
from .manifest import AppManifest, parse_app_manifest
from .provider import ScaffoldFileProvider
from .renderers import (
    SCAFFOLD_RENDERERS,
    render_alembic_env,
    render_alembic_ini,
    render_dockerfile,
    render_env_example,
    render_logging,
    render_pyproject,
    render_scaffold,
)

__all__ = [
    "AppManifest",
    "parse_app_manifest",
    "render_scaffold",
    "render_pyproject",
    "render_logging",
    "render_dockerfile",
    "render_alembic_ini",
    "render_alembic_env",
    "render_env_example",
    "SCAFFOLD_RENDERERS",
    "scaffold_in_sync",
    "is_owned_scaffold_file",
    "ScaffoldFileProvider",
]
