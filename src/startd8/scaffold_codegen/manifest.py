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

_TOP_KEYS = {
    "app", "persistence", "logging", "migrations", "container",
    "extra_dependencies", "deployment",
}

# Deployment-mode enum (DEPLOYMENT_MODE_REQUIREMENTS.md FR-CFG-1). Exactly two declared modes in v1
# (NR-2): `installed` (single-user, local-first — today's behavior, the default) vs `deployed`
# (multi-user, shared compute/persistence). Strict: any other value fails loud, never silently
# coerced. Tier-B `deployment.tenant` is intentionally NOT accepted yet (added when that increment
# ships), keeping the strict-key discipline this module already enforces.
_VALID_DEPLOYMENT_MODES = frozenset({"installed", "deployed"})
_DEPLOYMENT_KEYS = {"mode"}
DEFAULT_DEPLOYMENT_MODE = "installed"


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
    # FR-CFG-1/2: the single declared source of truth for installed-vs-deployed. Defaults to
    # `installed` so an absent `deployment:` block reproduces today's behavior exactly.
    deployment_mode: str = DEFAULT_DEPLOYMENT_MODE


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
    deployment = data.get("deployment") or {}
    for name, block in (
        ("app", app), ("persistence", persistence), ("logging", logging_),
        ("migrations", migrations_), ("container", container), ("deployment", deployment),
    ):
        if not isinstance(block, dict):
            raise ValueError(f"app.yaml: `{name}` must be a mapping")

    extra_deps = data.get("extra_dependencies") or []
    if not isinstance(extra_deps, list) or not all(isinstance(d, str) for d in extra_deps):
        raise ValueError("app.yaml: `extra_dependencies` must be a list of strings")

    # Strict on deployment sub-keys (mirrors the top-level discipline; never an LLM fallback).
    unknown_dep = set(deployment) - _DEPLOYMENT_KEYS
    if unknown_dep:
        raise ValueError(f"app.yaml: `deployment` has unknown keys {sorted(unknown_dep)}")
    deployment_mode = str(deployment.get("mode", DEFAULT_DEPLOYMENT_MODE))
    if deployment_mode not in _VALID_DEPLOYMENT_MODES:
        raise ValueError(
            f"app.yaml: `deployment.mode` must be one of {sorted(_VALID_DEPLOYMENT_MODES)}, "
            f"got {deployment_mode!r}"
        )

    return AppManifest(
        name=str(app.get("name", "app")),
        package=str(app.get("package", "app")),
        db_path=str(persistence.get("path", "./data/app.db")),
        log_file=str(logging_.get("file", "./data/logs/app.log")),
        migrations=bool(migrations_.get("enabled", True)),
        dockerfile=bool(container.get("dockerfile", True)),
        python_version=str(app.get("python_version", "3.11")),
        extra_dependencies=tuple(extra_deps),
        deployment_mode=deployment_mode,
    )
