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
    "extra_dependencies", "deployment", "telemetry", "messaging", "deploy",
}

# Cloud-native deploy block (CLOUD_NATIVE_DEPLOY_REQUIREMENTS.md M0). Strict-keyed like every other
# block. Most fields are consumed by the (future) manifest renderers; `trust_gateway` is wired now
# because the coherence guard's fail-closed identity check (FR-CND-6) reads it.
_DEPLOY_KEYS = {
    "trust_gateway", "secrets", "target_cloud", "namespace", "hostnames",
    "replicas", "port", "image", "resources", "autoscaling", "emit_gateway_stub",
    "environments",
}
_DEPLOY_SECRETS_KEYS = {"backend"}
# DEPLOY_ENVIRONMENTS M0 — per-environment override keys, split into the two binding planes
# (FR-ENV-3): app env-vars (ConfigMap, read from os.environ) vs k8s object fields (manifest patches).
_ENV_OVERRIDE_KEYS = {
    "env", "log_level", "otlp_endpoint", "secrets_config", "database_ref",   # app env-var plane
    "replicas", "resources", "hostnames", "autoscaling",                     # k8s-field plane
}
# FR-CND-5: default `eso-doppler`; `doppler-operator` opt-in CRD; cloud-native secret managers.
_VALID_SECRETS_BACKENDS = frozenset({"eso-doppler", "doppler-operator", "eso-aws", "eso-gcp"})

# Deployment-mode enum (DEPLOYMENT_MODE_REQUIREMENTS.md FR-CFG-1). Exactly two declared modes in v1
# (NR-2): `installed` (single-user, local-first — today's behavior, the default) vs `deployed`
# (multi-user, shared compute/persistence). Strict: any other value fails loud, never silently
# coerced. Tier-B `deployment.tenant` is intentionally NOT accepted yet (added when that increment
# ships), keeping the strict-key discipline this module already enforces.
_VALID_DEPLOYMENT_MODES = frozenset({"installed", "deployed"})
_VALID_TELEMETRY_PATTERNS = frozenset({"http", "grpc", "db", "messaging"})
_VALID_MESSAGING_BACKENDS = frozenset({"aiokafka", "kafka-python"})
# Tier B (M3): `deployment.tenant: {model, owner_field}` declares per-principal data isolation
# (FR-TEN-2). Both sub-keys required when the block is present; the SCHEMA-level validation (the
# model + owner_field actually exist) happens at generation time in backend_codegen, since this
# plumbing parser is schema-agnostic. **No synthesis** — the owner FK must already be in the schema.
_DEPLOYMENT_KEYS = {"mode", "tenant"}
_TENANT_KEYS = {"model", "owner_field"}
DEFAULT_DEPLOYMENT_MODE = "installed"


@dataclass(frozen=True)
class EnvironmentSpec:
    """One declared deploy environment (DEPLOY_ENVIRONMENTS). Scalar override values live here (for
    coherence + the per-env contract); nested k8s-field values (resources/autoscaling) are read raw
    by the overlay renderer. All-hashable so AppManifest stays hashable."""

    name: str
    env: Optional[str] = None
    log_level: Optional[str] = None
    otlp_endpoint: Optional[str] = None
    secrets_config: Optional[str] = None
    database_ref: Optional[str] = None
    hostnames: Tuple[str, ...] = ()
    has_replicas: bool = False
    has_resources: bool = False
    has_autoscaling: bool = False


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
    messaging_backend: str = "aiokafka"
    # Cloud-native deploy posture (M0). `deploy_trust_gateway` acknowledges that a verifying gateway
    # fronts the app — it clears the FR-CND-6 fail-closed identity ERROR (default False = fail-closed).
    deploy_trust_gateway: bool = False
    deploy_secrets_backend: Optional[str] = None
    deploy_target_cloud: Optional[str] = None
    # DEPLOY_ENVIRONMENTS: declared environments (sorted for byte-stability, R1-S7). Empty = none
    # (SOTTO → no overlays). Each spec carries the scalar per-env overrides.
    deploy_environment_specs: Tuple[EnvironmentSpec, ...] = ()

    @property
    def deploy_environments(self) -> Tuple[str, ...]:
        """The declared environment names (sorted)."""
        return tuple(s.name for s in self.deploy_environment_specs)

    @property
    def has_environments(self) -> bool:
        return len(self.deploy_environment_specs) > 0

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

    # Cloud-native deploy block (M0) — strict-keyed; only the few fields needed now are extracted,
    # the rest are validated-and-reserved for the manifest renderers (cloud-native M1).
    deploy_trust_gateway = False
    deploy_secrets_backend: Optional[str] = None
    deploy_target_cloud: Optional[str] = None
    deploy_environment_specs: Tuple[EnvironmentSpec, ...] = ()
    deploy = data.get("deploy")
    if deploy is not None:
        if not isinstance(deploy, dict):
            raise ValueError("app.yaml: `deploy` must be a mapping")
        unknown_deploy = set(deploy) - _DEPLOY_KEYS
        if unknown_deploy:
            raise ValueError(f"app.yaml: `deploy` has unknown keys {sorted(unknown_deploy)}")
        deploy_trust_gateway = bool(deploy.get("trust_gateway", False))
        secrets = deploy.get("secrets")
        if secrets is not None:
            if not isinstance(secrets, dict):
                raise ValueError("app.yaml: `deploy.secrets` must be a mapping")
            unknown_sec = set(secrets) - _DEPLOY_SECRETS_KEYS
            if unknown_sec:
                raise ValueError(f"app.yaml: `deploy.secrets` has unknown keys {sorted(unknown_sec)}")
            backend = secrets.get("backend")
            if backend is not None:
                if backend not in _VALID_SECRETS_BACKENDS:
                    raise ValueError(
                        f"app.yaml: `deploy.secrets.backend` must be one of "
                        f"{sorted(_VALID_SECRETS_BACKENDS)}, got {backend!r}"
                    )
                deploy_secrets_backend = backend
        tc = deploy.get("target_cloud")
        if tc is not None:
            deploy_target_cloud = str(tc)
        # DEPLOY_ENVIRONMENTS M0: `deploy.environments` is a mapping env-name → per-env overrides.
        # Strict-keyed (env names + override keys). Absent → no environments (SOTTO; no overlays).
        environments = deploy.get("environments")
        if environments is not None:
            if not isinstance(environments, dict):
                raise ValueError(
                    "app.yaml: `deploy.environments` must be a mapping {env-name: {overrides}}"
                )
            specs = []
            for env_name, overrides in environments.items():
                if not (isinstance(env_name, str) and env_name):
                    raise ValueError("app.yaml: `deploy.environments` keys must be non-empty strings")
                ov = overrides or {}
                if not isinstance(ov, dict):
                    raise ValueError(
                        f"app.yaml: `deploy.environments.{env_name}` must be a mapping of overrides"
                    )
                unknown_env = set(ov) - _ENV_OVERRIDE_KEYS
                if unknown_env:
                    raise ValueError(
                        f"app.yaml: `deploy.environments.{env_name}` has unknown keys {sorted(unknown_env)}"
                    )
                hostnames = ov.get("hostnames") or []
                if not isinstance(hostnames, list) or not all(isinstance(h, str) for h in hostnames):
                    raise ValueError(
                        f"app.yaml: `deploy.environments.{env_name}.hostnames` must be a list of strings"
                    )
                specs.append(EnvironmentSpec(
                    name=env_name,
                    env=ov.get("env"),
                    log_level=ov.get("log_level"),
                    otlp_endpoint=ov.get("otlp_endpoint"),
                    secrets_config=ov.get("secrets_config"),
                    database_ref=ov.get("database_ref"),
                    hostnames=tuple(hostnames),
                    has_replicas="replicas" in ov,
                    has_resources="resources" in ov,
                    has_autoscaling="autoscaling" in ov,
                ))
            # Sorted by name for byte-stability regardless of YAML key insertion order (R1-S7).
            deploy_environment_specs = tuple(sorted(specs, key=lambda s: s.name))

    messaging_backend = "aiokafka"
    messaging = data.get("messaging")
    if messaging is not None:
        if not isinstance(messaging, dict):
            raise ValueError("app.yaml: `messaging` must be a mapping")
        unknown_msg = set(messaging) - {"backend"}
        if unknown_msg:
            raise ValueError(f"app.yaml: `messaging` has unknown keys {sorted(unknown_msg)}")
        messaging_backend = str(messaging.get("backend", messaging_backend))
        if messaging_backend not in _VALID_MESSAGING_BACKENDS:
            raise ValueError(
                f"app.yaml: `messaging.backend` must be one of {sorted(_VALID_MESSAGING_BACKENDS)}, "
                f"got {messaging_backend!r}"
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
        tenant_model=tenant_model,
        tenant_owner_field=tenant_owner_field,
        telemetry_enabled=telemetry_enabled,
        telemetry_otlp_endpoint=telemetry_otlp_endpoint,
        telemetry_service_name=telemetry_service_name,
        telemetry_patterns=telemetry_patterns,
        messaging_backend=messaging_backend,
        deploy_trust_gateway=deploy_trust_gateway,
        deploy_secrets_backend=deploy_secrets_backend,
        deploy_target_cloud=deploy_target_cloud,
        deploy_environment_specs=deploy_environment_specs,
    )
