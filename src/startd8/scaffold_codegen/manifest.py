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
    "extra_dependencies", "deployment", "telemetry",
}

# Deployment-mode enum (DEPLOYMENT_MODE_REQUIREMENTS.md FR-CFG-1). Exactly two declared modes in v1
# (NR-2): `installed` (single-user, local-first — today's behavior, the default) vs `deployed`
# (multi-user, shared compute/persistence). Strict: any other value fails loud, never silently
# coerced. Tier-B `deployment.tenant` is intentionally NOT accepted yet (added when that increment
# ships), keeping the strict-key discipline this module already enforces.
_VALID_DEPLOYMENT_MODES = frozenset({"installed", "deployed"})
_VALID_TELEMETRY_PATTERNS = frozenset({"http", "grpc", "db", "messaging"})
# Tier B (M3): `deployment.tenant: {model, owner_field}` declares per-principal data isolation
# (FR-TEN-2). Both sub-keys required when the block is present; the SCHEMA-level validation (the
# model + owner_field actually exist) happens at generation time in backend_codegen, since this
# plumbing parser is schema-agnostic. **No synthesis** — the owner FK must already be in the schema.
_DEPLOYMENT_KEYS = {"mode", "tenant"}
_TENANT_KEYS = {"model", "owner_field"}
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
    # Tier B / FR-TEN-2: the declared tenant isolation (both None unless `deployment.tenant` is set).
    # `tenant_model` = the principal/owner model; `tenant_owner_field` = the FK field name on scoped
    # entities (an entity is row-scoped to the principal iff it has a field of this name).
    tenant_model: Optional[str] = None
    tenant_owner_field: Optional[str] = None
    telemetry_enabled: bool = False
    telemetry_otlp_endpoint: str = "http://127.0.0.1:4318"
    telemetry_service_name: Optional[str] = None
    telemetry_patterns: Tuple[str, ...] = ()

    @property
    def has_tenant(self) -> bool:
        """True iff a `deployment.tenant` isolation contract is declared (Tier B)."""
        return self.tenant_model is not None and self.tenant_owner_field is not None


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

    # Tier B: `deployment.tenant` (optional). When present, both model + owner_field are required
    # strings; schema existence is validated downstream (backend_codegen), not here.
    tenant_model: Optional[str] = None
    tenant_owner_field: Optional[str] = None
    tenant = deployment.get("tenant")
    if tenant is not None:
        if not isinstance(tenant, dict):
            raise ValueError("app.yaml: `deployment.tenant` must be a mapping {model, owner_field}")
        unknown_tenant = set(tenant) - _TENANT_KEYS
        if unknown_tenant:
            raise ValueError(f"app.yaml: `deployment.tenant` has unknown keys {sorted(unknown_tenant)}")
        tenant_model = tenant.get("model")
        tenant_owner_field = tenant.get("owner_field")
        if not (isinstance(tenant_model, str) and tenant_model):
            raise ValueError("app.yaml: `deployment.tenant.model` is required (the principal model)")
        if not (isinstance(tenant_owner_field, str) and tenant_owner_field):
            raise ValueError("app.yaml: `deployment.tenant.owner_field` is required (the owner FK field)")

    telemetry_enabled = False
    telemetry_otlp_endpoint = "http://127.0.0.1:4318"
    telemetry_service_name: Optional[str] = None
    telemetry_patterns: Tuple[str, ...] = ()
    telemetry = data.get("telemetry")
    if telemetry is not None:
        if not isinstance(telemetry, dict):
            raise ValueError("app.yaml: `telemetry` must be a mapping")
        unknown_telemetry = set(telemetry) - {"enabled", "otlp_endpoint", "service_name", "patterns"}
        if unknown_telemetry:
            raise ValueError(f"app.yaml: `telemetry` has unknown keys {sorted(unknown_telemetry)}")
        telemetry_enabled = bool(telemetry.get("enabled", False))
        telemetry_otlp_endpoint = str(telemetry.get("otlp_endpoint", telemetry_otlp_endpoint))
        svc = telemetry.get("service_name")
        if svc is not None:
            if not isinstance(svc, str) or not svc:
                raise ValueError("app.yaml: `telemetry.service_name` must be a non-empty string")
            telemetry_service_name = svc
        raw_patterns = telemetry.get("patterns") or []
        if not isinstance(raw_patterns, list) or not all(isinstance(p, str) for p in raw_patterns):
            raise ValueError("app.yaml: `telemetry.patterns` must be a list of strings")
        bad = [p for p in raw_patterns if p not in _VALID_TELEMETRY_PATTERNS]
        if bad:
            raise ValueError(
                f"app.yaml: `telemetry.patterns` invalid {bad}; "
                f"allowed: {sorted(_VALID_TELEMETRY_PATTERNS)}"
            )
        telemetry_patterns = tuple(dict.fromkeys(raw_patterns))

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
        tenant_model=tenant_model,
        tenant_owner_field=tenant_owner_field,
        telemetry_enabled=telemetry_enabled,
        telemetry_otlp_endpoint=telemetry_otlp_endpoint,
        telemetry_service_name=telemetry_service_name,
        telemetry_patterns=telemetry_patterns,
    )
