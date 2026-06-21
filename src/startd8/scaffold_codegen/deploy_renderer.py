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
    """DNS-1123-safe object name from ``app.name`` (FR-CND-18): lowercase, ``a-z0-9-``, ≤63, trimmed."""
    s = re.sub(r"[^a-z0-9-]+", "-", (name or "app").lower()).strip("-")
    s = s[:63].strip("-")
    return s or "app"


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
    return _header("scaffold-infra-contract", sha) + "\n\n" + body


# --- aggregator + drift map --------------------------------------------------------------------

DEPLOY_RENDERERS = {
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
    return tuple(out)
