"""Cloud-native deploy manifests (CLOUD_NATIVE_DEPLOY M1) — the vendor-neutral ``deploy/`` tree.

Emitted only in ``deployment.mode: deployed``. Standard Kubernetes + Gateway API + External Secrets
(never Gloo-/cloud-vendor CRDs in the core — FR-CND-9/28): Deployment, Service (ClusterIP), ConfigMap
(non-secret env), ExternalSecret (Doppler default, FR-CND-5), HTTPRoute (FR-CND-3), NetworkPolicy
(gateway-only ingress + egress allowlist, FR-CND-13), and the machine-readable infra-needs contract
(FR-CND-11/26 — the seam to Terraform/StackGen + Kestra/Argo). Operator-owned values (image digest,
registry, hostnames, SecretStore, gateway listener) are **bound at deploy time, not baked** (FR-CND-9).

Deterministic, ``$0``, byte-stable (literal YAML, no dict-ordering), drift-checked via the same
``#``-comment header + ``DEPLOY_RENDERERS`` map the rest of scaffold_codegen uses.
"""

from __future__ import annotations

import re
from typing import List, Tuple

import yaml

from ..frontend_codegen.schema_renderer import schema_sha256
from .manifest import AppManifest, parse_app_manifest

# Operator-bound sentinels — obviously non-pullable / non-routable so a survive-to-apply is caught
# (FR-CND-14). The operator binds these at deploy time (kustomize overlay / edit / CI substitution).
_IMAGE_SENTINEL = "REPLACE_ME-unbound-image:set-deploy.image"
_HOST_SENTINEL = "REPLACE_ME.example.com"
_GATEWAY_SENTINEL = "REPLACE_ME-gateway"
_SECRETSTORE_SENTINEL = "REPLACE_ME-secretstore"


def _header(kind: str, sha: str) -> str:
    """The ``#``-comment GENERATED/provenance header (valid atop YAML); hashes app.yaml."""
    return (
        "# GENERATED from app.yaml — do not edit by hand; regenerate via `startd8 generate scaffold`.\n"
        f"# startd8-artifact: {kind}\n"
        "# Source of truth: the app manifest.\n"
        f"# manifest-sha256: {sha}"
    )


def _dns1123(name: str) -> str:
    """DNS-1123-safe object name from ``app.name`` (FR-CND-18): lowercase, ``a-z0-9-``, ≤63, trimmed.

    On truncation a stable 6-char hash of the full sanitized name is appended so two long names that
    differ only past char 63 do not collide into the same K8s object name.
    """
    s = re.sub(r"[^a-z0-9-]+", "-", (name or "app").lower()).strip("-")
    if not s:
        return "app"
    if len(s) <= 63:
        return s
    return (s[:56].strip("-") + "-" + schema_sha256(s)[:6])


def _secret_store(m: AppManifest) -> str:
    """ESO SecretStore *kind* implied by the chosen backend (the store itself is operator-owned)."""
    return {
        "eso-doppler": "Doppler",
        "eso-aws": "AWS Secrets Manager",
        "eso-gcp": "GCP Secret Manager",
        "doppler-operator": "Doppler (native operator)",
    }.get(m.deploy_secrets_backend or "eso-doppler", "Doppler")


# --- individual manifests ----------------------------------------------------------------------

def render_k8s_deployment(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    body = f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
    app.kubernetes.io/managed-by: startd8
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {name}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {name}
    spec:
      serviceAccountName: {name}
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: {_IMAGE_SENTINEL}   # operator-bound (deploy.image digest preferred)
          ports:
            - containerPort: 8000
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          envFrom:
            - configMapRef:
                name: {name}-config
            - secretRef:
                name: {name}-secrets
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8000
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 256Mi
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {{}}
"""
    return _header("scaffold-k8s-deployment", sha) + "\n\n" + body


def render_k8s_service(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    body = f"""\
apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
spec:
  type: ClusterIP   # internal-only; the gateway is the only ingress (FR-CND-6)
  selector:
    app.kubernetes.io/name: {name}
  ports:
    - port: 80
      targetPort: 8000
"""
    return _header("scaffold-k8s-service", sha) + "\n\n" + body


def render_k8s_serviceaccount(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    body = f"""\
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
automountServiceAccountToken: false
"""
    return _header("scaffold-k8s-serviceaccount", sha) + "\n\n" + body


def render_k8s_configmap(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    svc = m.telemetry_service_name or m.name
    # Non-secret env only. Secrets (DATABASE_URL, provider API keys) live in the ExternalSecret.
    body = f"""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}-config
  labels:
    app.kubernetes.io/name: {name}
data:
  ENV: "production"
  HOST: "0.0.0.0"
  PORT: "8000"
  OTEL_SERVICE_NAME: "{svc}"
  # operator binds the in-cluster collector endpoint:
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector.observability:4318"
"""
    return _header("scaffold-k8s-configmap", sha) + "\n\n" + body


def render_k8s_externalsecret(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    # ESO ExternalSecret — vendor-neutral; the SecretStore (default Doppler) is operator-owned.
    body = f"""\
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {name}-secrets
  labels:
    app.kubernetes.io/name: {name}
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: {_SECRETSTORE_SENTINEL}   # operator-owned SecretStore ({_secret_store(m)})
    kind: SecretStore
  target:
    name: {name}-secrets
    creationPolicy: Owner
  dataFrom:
    - find:
        name:
          regexp: ".*"   # operator scopes to this app's keys (DATABASE_URL, provider API keys)
"""
    return _header("scaffold-k8s-externalsecret", sha) + "\n\n" + body


def render_k8s_httproute(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    # Gateway API v1 — parentRef + hostnames are operator-bound; /health* is NOT publicly routed.
    body = f"""\
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
spec:
  parentRefs:
    - name: {_GATEWAY_SENTINEL}   # operator-owned Gateway listener (deploy.gateway)
  hostnames:
    - {_HOST_SENTINEL}            # operator-bound (deploy.hostnames); never default '*'
  rules:
    # Probes are kubelet-internal (the Service is ClusterIP; kubelet reaches the pod directly), so
    # /health and /health/live are NOT routed here. Readiness runs a DB SELECT 1 — the operator's
    # gateway MUST NOT expose /health* externally (FR-CND-16).
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - name: {name}
          port: 80
"""
    return _header("scaffold-k8s-httproute", sha) + "\n\n" + body


def render_k8s_networkpolicy(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    # Fail-closed reachability (FR-CND-13): ingress only from the gateway namespace; egress allowlist
    # (DNS + the operator-bound DB / OTLP / secret backend / provider APIs). Requires a CNI that
    # enforces NetworkPolicy (infra-contract prerequisite).
    body = f"""\
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {name}
  labels:
    app.kubernetes.io/name: {name}
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: {name}
  policyTypes: ["Ingress", "Egress"]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: gateway-system   # operator-bound gateway namespace
  egress:
    - to: []
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # operator widens egress to the DB / OTLP collector / secret backend / provider APIs
    - to: []
      ports:
        - protocol: TCP
          port: 443
        - protocol: TCP
          port: 5432
        - protocol: TCP
          port: 4318
"""
    return _header("scaffold-k8s-networkpolicy", sha) + "\n\n" + body


def render_infra_contract(manifest_text: str) -> str:
    m = parse_app_manifest(manifest_text)
    name = _dns1123(m.name)
    sha = schema_sha256(manifest_text)
    backend = m.deploy_secrets_backend or "eso-doppler"
    cloud = m.deploy_target_cloud or "operator-choice"
    # The IaC/orchestration seam (FR-CND-11/26): what the operator must provision, with status.
    # Tool-neutral YAML (OQ-9). schemaVersion lets consumers (cap-dev-pipe gate, Terraform/StackGen)
    # fail-closed on major skew.
    body = f"""\
schemaVersion:
  major: 1
  minor: 0
app: {name}
target_cloud: {cloud}
bindings:
  - name: container_image
    kind: image
    status: operator-provided
    note: immutable digest preferred (FR-CND-14)
  - name: container_registry
    kind: registry
    status: operator-provided
  - name: secret_store
    kind: secretstore
    backend: {backend}
    status: operator-provided
    note: ESO SecretStore (default Doppler project/config) — token bootstrap is a one-time seed
  - name: gateway_listener
    kind: gateway-api
    status: operator-provided
  - name: hostnames
    kind: dns
    status: operator-provided
  - name: otlp_collector
    kind: otlp
    status: operator-provided
prerequisites:
  - name: gateway-api-crds
    min_version: v1
  - name: external-secrets-operator
  - name: cni-networkpolicy-enforcement
  - name: pod-security-standard
    note: namespace must allow the restricted profile
"""
    # M2: per-environment operator bindings (deployed + environments only). DB ref is routed by
    # secret-ness (FR-ENV-3/R1-F5): a credentialed DSN → ExternalSecret; a non-secret DSN → here.
    if m.has_environments:
        env_lines = ["environments:"]
        for s in m.deploy_environment_specs:  # already sorted (byte-stable)
            env_lines.append(f"  - name: {s.name}")
            env_lines.append("    bindings:")
            env_lines.append(f"      - {{name: secrets_config, kind: secretstore-config, "
                             f"value: {s.secrets_config or 'operator-provided'}, status: operator-provided}}")
            env_lines.append(f"      - {{name: otlp_collector, kind: otlp, "
                             f"value: {s.otlp_endpoint or 'inherits-base'}, status: operator-provided}}")
            host = ",".join(s.hostnames) if s.hostnames else "operator-provided"
            env_lines.append(f"      - {{name: hostnames, kind: dns, value: {host}, status: operator-provided}}")
            db = "non-secret-binding" if s.database_ref else "via-externalsecret"
            env_lines.append(f"      - {{name: database, kind: database, routing: {db}, status: operator-provided}}")
        body += "\n".join(env_lines) + "\n"
    return _header("scaffold-infra-contract", sha) + "\n\n" + body


# --- DEPLOY_ENVIRONMENTS M1: base + per-env kustomize overlays ---------------------------------
# Environment is orthogonal to mode (deployed-only). One env-agnostic base + per-env overlays patch
# ONLY the varying values across the two binding planes (FR-ENV-3): app env-vars via a ConfigMap
# strategic-merge patch; k8s object fields (replicas/resources/HPA) via Deployment patch / HPA add.
# The Doppler config appears ONLY in the overlay's ExternalSecret ref, never the base (FR-ENV-7).

_BASE_RESOURCES = (
    "deployment.yaml", "service.yaml", "serviceaccount.yaml", "configmap.yaml",
    "externalsecret.yaml", "httproute.yaml", "networkpolicy.yaml",
)


def _env_overrides(manifest_text: str, env: str) -> dict:
    """The validated per-env override mapping (parse_app_manifest enforces the strict grammar)."""
    parse_app_manifest(manifest_text)  # validate (raises on a bad manifest)
    data = yaml.safe_load(manifest_text or "") or {}
    envs = ((data.get("deploy") or {}).get("environments")) or {}
    return envs.get(env) or {}


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(pad + line if line.strip() else line for line in text.splitlines(keepends=True))


def _yaml_block(value: object) -> str:
    """Deterministic YAML for a nested override value (sorted keys, block style)."""
    return yaml.safe_dump(value, sort_keys=True, default_flow_style=False).rstrip("\n")


def render_base_kustomization(manifest_text: str) -> str:
    """``deploy/kustomization.yaml`` — the base. Emitted ONLY when environments are declared (SOTTO)."""
    sha = schema_sha256(manifest_text)
    res = "\n".join(f"  - {r}" for r in _BASE_RESOURCES)
    body = "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n" + res + "\n"
    return _header("scaffold-k8s-base-kustomization", sha) + "\n\n" + body


def render_overlay_configmap(manifest_text: str, env: str) -> str:
    m = parse_app_manifest(manifest_text)
    o = _env_overrides(manifest_text, env)
    sha = schema_sha256(manifest_text)
    lines = [f'  ENV: "{o.get("env", env)}"']  # FR-ENV-6: per-env deployment.environment
    if "log_level" in o:
        lines.append(f'  LOG_LEVEL: "{o["log_level"]}"')
    if "otlp_endpoint" in o:
        lines.append(f'  OTEL_EXPORTER_OTLP_ENDPOINT: "{o["otlp_endpoint"]}"')
    body = (
        f"apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: {_dns1123(m.name)}-config\ndata:\n"
        + "\n".join(lines) + "\n"
    )
    return _header(f"scaffold-k8s-overlay-configmap@{env}", sha) + "\n\n" + body


def render_overlay_deployment(manifest_text: str, env: str) -> str:
    """Deployment strategic-merge patch for the k8s-field plane (replicas/resources)."""
    m = parse_app_manifest(manifest_text)
    o = _env_overrides(manifest_text, env)
    sha = schema_sha256(manifest_text)
    name = _dns1123(m.name)
    spec = ""
    if "replicas" in o:
        spec += f"  replicas: {int(o['replicas'])}\n"
    if "resources" in o:
        res = _indent(_yaml_block({"resources": o["resources"]}), 10)
        spec += "  template:\n    spec:\n      containers:\n        - name: app\n" + res + "\n"
    body = f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {name}\nspec:\n" + spec
    return _header(f"scaffold-k8s-overlay-deployment@{env}", sha) + "\n\n" + body


def render_overlay_externalsecret(manifest_text: str, env: str) -> str:
    """ExternalSecret patch — per-env Doppler config (the ONLY place the config name appears)."""
    m = parse_app_manifest(manifest_text)
    o = _env_overrides(manifest_text, env)
    sha = schema_sha256(manifest_text)
    body = (
        f"apiVersion: external-secrets.io/v1beta1\nkind: ExternalSecret\nmetadata:\n"
        f"  name: {_dns1123(m.name)}-secrets\nspec:\n  secretStoreRef:\n"
        f"    name: {o['secrets_config']}   # per-env secrets scope (e.g. Doppler config); operator-owned\n"
    )
    return _header(f"scaffold-k8s-overlay-externalsecret@{env}", sha) + "\n\n" + body


def render_overlay_hpa(manifest_text: str, env: str) -> str:
    m = parse_app_manifest(manifest_text)
    o = _env_overrides(manifest_text, env)
    sha = schema_sha256(manifest_text)
    name = _dns1123(m.name)
    a = o.get("autoscaling") or {}
    body = (
        f"apiVersion: autoscaling/v2\nkind: HorizontalPodAutoscaler\nmetadata:\n  name: {name}\nspec:\n"
        f"  scaleTargetRef:\n    apiVersion: apps/v1\n    kind: Deployment\n    name: {name}\n"
        f"  minReplicas: {int(a.get('min', 1))}\n  maxReplicas: {int(a.get('max', 3))}\n"
        f"  metrics:\n    - type: Resource\n      resource:\n        name: cpu\n"
        f"        target:\n          type: Utilization\n          averageUtilization: {int(a.get('cpu', 80))}\n"
    )
    return _header(f"scaffold-k8s-overlay-hpa@{env}", sha) + "\n\n" + body


def render_overlay_kustomization(manifest_text: str, env: str) -> str:
    o = _env_overrides(manifest_text, env)
    sha = schema_sha256(manifest_text)
    resources = ["  - ../../"]
    if "autoscaling" in o:
        resources.append("  - hpa.yaml")
    patches = ["  - path: configmap-patch.yaml"]
    if "replicas" in o or "resources" in o:
        patches.append("  - path: deployment-patch.yaml")
    if "secrets_config" in o:
        patches.append("  - path: externalsecret-patch.yaml")
    body = (
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nresources:\n"
        + "\n".join(resources) + "\npatches:\n" + "\n".join(patches) + "\n"
    )
    return _header(f"scaffold-k8s-overlay-kustomization@{env}", sha) + "\n\n" + body


# Overlay re-render dispatch (env-parameterized; drift handles the `@env` kind suffix).
_OVERLAY_FILE_RENDERERS = {
    "scaffold-k8s-overlay-kustomization": render_overlay_kustomization,
    "scaffold-k8s-overlay-configmap": render_overlay_configmap,
    "scaffold-k8s-overlay-deployment": render_overlay_deployment,
    "scaffold-k8s-overlay-externalsecret": render_overlay_externalsecret,
    "scaffold-k8s-overlay-hpa": render_overlay_hpa,
}


def rerender_overlay(kind: str, manifest_text: str) -> str | None:
    """Re-render an `@env`-suffixed overlay file for drift; None if the kind is not an overlay."""
    if "@" not in kind:
        return None
    base_kind, _, env = kind.partition("@")
    fn = _OVERLAY_FILE_RENDERERS.get(base_kind)
    return fn(manifest_text, env) if (fn and env) else None


def render_deploy_overlays(manifest_text: str) -> Tuple[Tuple[str, str], ...]:
    """Base kustomization + per-env overlays. Deployed mode with environments declared only (SOTTO)."""
    m = parse_app_manifest(manifest_text)
    if m.deployment_mode != "deployed" or not m.has_environments:
        return ()
    out: List[Tuple[str, str]] = [("deploy/kustomization.yaml", render_base_kustomization(manifest_text))]
    for env in m.deploy_environments:  # already sorted (byte-stable, R1-S7)
        o = _env_overrides(manifest_text, env)
        base = f"deploy/overlays/{env}/"
        out.append((base + "kustomization.yaml", render_overlay_kustomization(manifest_text, env)))
        out.append((base + "configmap-patch.yaml", render_overlay_configmap(manifest_text, env)))
        if "replicas" in o or "resources" in o:
            out.append((base + "deployment-patch.yaml", render_overlay_deployment(manifest_text, env)))
        if "secrets_config" in o:
            out.append((base + "externalsecret-patch.yaml", render_overlay_externalsecret(manifest_text, env)))
        if "autoscaling" in o:
            out.append((base + "hpa.yaml", render_overlay_hpa(manifest_text, env)))
    return tuple(out)


# --- aggregator + drift map --------------------------------------------------------------------

DEPLOY_RENDERERS = {
    "scaffold-k8s-base-kustomization": render_base_kustomization,
    "scaffold-k8s-deployment": render_k8s_deployment,
    "scaffold-k8s-service": render_k8s_service,
    "scaffold-k8s-serviceaccount": render_k8s_serviceaccount,
    "scaffold-k8s-configmap": render_k8s_configmap,
    "scaffold-k8s-externalsecret": render_k8s_externalsecret,
    "scaffold-k8s-httproute": render_k8s_httproute,
    "scaffold-k8s-networkpolicy": render_k8s_networkpolicy,
    "scaffold-infra-contract": render_infra_contract,
}


def render_deploy_tree(manifest_text: str) -> Tuple[Tuple[str, str], ...]:
    """The whole ``deploy/`` tree as ``(relative_path, text)`` pairs. Deployed mode only."""
    m = parse_app_manifest(manifest_text)
    if m.deployment_mode != "deployed":
        return ()
    out: List[Tuple[str, str]] = [
        ("deploy/deployment.yaml", render_k8s_deployment(manifest_text)),
        ("deploy/service.yaml", render_k8s_service(manifest_text)),
        ("deploy/serviceaccount.yaml", render_k8s_serviceaccount(manifest_text)),
        ("deploy/configmap.yaml", render_k8s_configmap(manifest_text)),
        ("deploy/externalsecret.yaml", render_k8s_externalsecret(manifest_text)),
        ("deploy/httproute.yaml", render_k8s_httproute(manifest_text)),
        ("deploy/networkpolicy.yaml", render_k8s_networkpolicy(manifest_text)),
        ("deploy/infra-contract.yaml", render_infra_contract(manifest_text)),
    ]
    out.extend(render_deploy_overlays(manifest_text))  # base kustomization + per-env overlays (M1)
    return tuple(out)
