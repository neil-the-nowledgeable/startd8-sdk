"""Strict parse of ``app.yaml`` — the manifest-derived plumbing source of truth (REQ-SCAF-1/2).

Class-2 determinism: the project plumbing (pyproject, logging, alembic, Dockerfile) is a function of
a few declared project choices, not of the schema. ``app.yaml`` declares those choices; every field
has a lean default so an absent/empty manifest still yields a runnable default scaffold. Unknown keys
fail loud (never an LLM fallback), mirroring ``ai_passes.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import yaml

_TOP_KEYS = {"app", "persistence", "logging", "migrations", "container", "extra_dependencies"}


@dataclass(frozen=True)
class AppManifest:
    """The resolved project-plumbing choices (all defaulted)."""

    name: str = "app"
    package: str = "app"
    db_path: str = "./data/app.db"
    log_file: str = "./data/logs/app.log"
    migrations: bool = True
    dockerfile: bool = True
    python_version: str = "3.11"
    # G4: owned-glue runtime deps (e.g. reportlab/pypdf for an owned PDF path) declared in app.yaml,
    # so an app that adds an owned capability can flow its deps through the generate path.
    extra_dependencies: Tuple[str, ...] = ()


def parse_app_manifest(text: Optional[str]) -> AppManifest:
    """Parse ``app.yaml`` into an :class:`AppManifest`. Absent/empty → all defaults. Strict on keys."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("app.yaml must be a mapping")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise ValueError(f"app.yaml has unknown top-level keys {sorted(unknown)}")

    app = data.get("app") or {}
    persistence = data.get("persistence") or {}
    logging_ = data.get("logging") or {}
    migrations_ = data.get("migrations") or {}
    container = data.get("container") or {}
    for name, block in (
        ("app", app), ("persistence", persistence), ("logging", logging_),
        ("migrations", migrations_), ("container", container),
    ):
        if not isinstance(block, dict):
            raise ValueError(f"app.yaml: `{name}` must be a mapping")

    extra_deps = data.get("extra_dependencies") or []
    if not isinstance(extra_deps, list) or not all(isinstance(d, str) for d in extra_deps):
        raise ValueError("app.yaml: `extra_dependencies` must be a list of strings")

    return AppManifest(
        name=str(app.get("name", "app")),
        package=str(app.get("package", "app")),
        db_path=str(persistence.get("path", "./data/app.db")),
        log_file=str(logging_.get("file", "./data/logs/app.log")),
        migrations=bool(migrations_.get("enabled", True)),
        dockerfile=bool(container.get("dockerfile", True)),
        python_version=str(app.get("python_version", "3.11")),
        extra_dependencies=tuple(extra_deps),
    )
