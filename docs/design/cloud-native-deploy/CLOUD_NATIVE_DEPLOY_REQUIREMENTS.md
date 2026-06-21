# Cloud-Native Deployment Artifacts (Generated Apps → EKS/GKE behind agentgateway/kagent) — Requirements

**Version:** 0.3.1 (Post-CRP + cap-dev-pipe integration seam — FR-CND-30)
**Date:** 2026-06-20
**Status:** Ready for implementation
**Owner:** StartD8 SDK / scaffold_codegen + backend_codegen (bucket-1 $0 deterministic; bucket-4 boundary held)
**Builds on:** `docs/design/deployment-mode/` (the `deployed` tier) + `docs/design/auth-seam-jwt/` (Bearer/JWT seam) + `docs/design/local-deploy-harness/`
**Pilot:** StartDate (`strtd8`) — deploy the SDK-generated StartDate app to AWS (EKS) or GCP (GKE)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real code
> (`health_renderer.py`, `telemetry_renderer.py`, `scaffold_codegen/manifest.py`+`provider.py`,
> deployment-mode FR-NET/FR-OBS). See `CLOUD_NATIVE_DEPLOY_PLAN.md` §1. Central correction: **most
> of the "cloud-native" substrate already exists in the generated app** — this capability is mostly
> a vendor-neutral MANIFEST LAYER wiring together surfaces the app already exposes, plus a
> render-only command. The build is far smaller than v0.1 implied.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| FR-CND-2: must ADD a `/health`+liveness endpoint | Already emitted — `app/health.py` serves `GET /health` (readiness, `SELECT 1`) + `GET /health/live` (liveness); deploy harness already probes `/health`. | FR-CND-2 narrows to **wiring K8s probes to existing paths** (no app change). |
| FR-CND-4: new OTel bootstrap code needed | Already emitted — `app/telemetry.py` with `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME`/`ENV` all env-overridable. | FR-CND-4 narrows to **enable telemetry + set deploy-time env** to the cluster collector. |
| New manifest home + app.yaml shape unknown | `scaffold_codegen` already owns app.yaml-derived plumbing (incl. `Dockerfile`) via `ScaffoldFileProvider`+drift+header; `AppManifest` is strict-keyed. | Emit K8s/Gateway/ESO as **new scaffold output kinds**; add a strict **`deploy:` block**. No new provider plumbing. |
| EKS vs GKE need separate paths (OQ-7) | Structural manifests identical; only operator bindings differ (registry, SecretStore backend, gateway class). | FR-CND-10 confirmed — **one artifact set, no fork**. |
| SDK could run the deploy (OQ-8) | SDK never touches operator cloud creds; `kubectl`/build/push are operator territory. | **`startd8 deploy k8s` is render-only ($0)**; apply/build/push are an operator runbook. |
| FR-CND-8 (app-exposed MCP) in scope | No generated-app-CRUD→MCP bridge exists; `MCPGateway` fronts skills/workflows, not app routes — a separate large capability. | **FR-CND-8 deferred** to a later increment (tracked stretch). |

**Resolved open questions:**
- **OQ-1 → New `deploy:` block** in `AppManifest` (strict-keyed, parallel to `container:`/`deployment:`).
- **OQ-2 → New output kinds in `scaffold_codegen`** (optional `k8s/` submodule), reusing the provider/drift/header.
- **OQ-3 → YES, `/health` + `/health/live` already exist.** FR-CND-2 = wiring only.
- **OQ-4 → YES, OTLP endpoint is env-configurable.** FR-CND-4 = env + enable only.
- **OQ-5 → Plain manifests in v1**; kustomize base+overlay (and any IaC layer — see OQ-9) deferred.
- **OQ-6 → FR-CND-8 deferred** (app-exposed MCP) to a later increment.
- **OQ-7 → No fork** — EKS/GKE differences are operator bindings, not SDK code.
- **OQ-8 → Render-only CLI** + operator runbook; pilot ladder = local harness + a cluster-smoke rung (operator-run).
- **OQ-9 (new, for CRP).** Should the infra-needs contract (FR-CND-11) render an optional Terraform
  **variables stub** in v1, or stay tool-neutral YAML only? And: do we validate the contract against
  StackGen/Terraform consumption in the pilot, or document the hand-off and defer integration?

---

## 1. Problem Statement

The `deployed` tier (DEPLOYMENT_MODE) gives a generated app a container (`Dockerfile`, `0.0.0.0` bind),
a centralized-OTel posture, an auth seam, settings, and (declared) tenancy. **It stops at the
container.** To actually run that app on EKS/GKE — behind the agentgateway/kagent stack discussed for
the SDK's own MCP — an operator still hand-writes every Kubernetes manifest, the gateway route, the
secret wiring, and the probe/telemetry plumbing. That is structural deployment skeleton (the same
"who routes to it / where do secrets come from / how does the cluster health-check it" that the
determinism thesis says should be *generated*, bucket 1), not company content (bucket 4).

The goal: a generated app should **emit the cloud-native artifacts needed to deploy to a private
cloud (EKS/GKE) behind agentgateway/kagent** — deterministically, `$0`, drift-checked, and
**vendor-neutral** (standard Kubernetes + Gateway API + External Secrets, never Gloo-/cloud-specific
CRDs), with operator-owned values (image registry, domain, cluster policy, IdP, SecretStore) **bound
at deploy time, not baked**. StartDate is the pilot and the acceptance surface.

### Gap table (what the `deployed` tier already gives vs what K8s-behind-gateway needs)

| Concern | `deployed` tier today | Gap for EKS/GKE + agentgateway |
|---------|----------------------|--------------------------------|
| Container | `Dockerfile`, `0.0.0.0:8000` (scaffold) | No K8s Deployment/Service wrapping it |
| Health | (assumed none — to verify) | K8s liveness/readiness probes |
| Routing | none | Gateway API `HTTPRoute` to the gateway listener |
| Telemetry | OTel posture declared (assumed code TBD) | OTLP → in-cluster collector wiring |
| Secrets | SDK `secrets/` backend (doppler/local) | K8s `ExternalSecret`/`ConfigMap` from cloud secret mgr |
| Identity | Bearer/JWT seam (auth-seam-jwt) | HTTPRoute/gateway terminates auth, forwards identity |
| Agent surface | none | (optional) agentgateway/kagent integration; app-exposed MCP |
| Cloud neutrality | n/a | One artifact set for EKS *and* GKE; cloud-specifics operator-bound |

---

## 2. Requirements

- **FR-CND-1 (K8s workload manifests).** A `deployed` app SHALL emit standard Kubernetes
  `Deployment` + `Service` manifests wrapping the existing container, with resource requests/limits
  and env sourced from a generated `ConfigMap` (non-secret) and `Secret`/`ExternalSecret` (secret).
- **FR-CND-2 (Health probes — narrowed v0.2).** The manifests SHALL wire Kubernetes readiness
  (`GET /health`) + liveness (`GET /health/live`) probes to the app's **already-emitted** endpoints
  (`app/health.py`). No app-code change — manifest wiring only.
- **FR-CND-3 (Gateway API routing — clarified v0.3 R2-F2/R2-S4/R4-F2/R4-S2).** A `deployed` app SHALL
  emit a **vendor-neutral** Gateway API `HTTPRoute` **only** in the default core — the `Gateway`/listener
  is an **operator-owned infra-contract prerequisite, NOT an emitted object** (a `Gateway` stub is
  gated behind opt-in `deploy.emit_gateway_stub: true`, off by default). The `HTTPRoute` SHALL set
  explicit `hostnames` bound from `deploy.hostnames` (never default `*`, which hijacks/collides on a
  shared Gateway) and its `parentRef` (listener name/namespace/sectionName) SHALL come from a
  `deploy:` binding, not be hardcoded. So kgateway / agentgateway / Gloo / any Gateway-API
  implementation routes to it without app changes.
- **FR-CND-4 (OTel → cluster collector — narrowed v0.2).** The emitted ConfigMap SHALL set the
  app's **existing** env knobs (`OTEL_EXPORTER_OTLP_ENDPOINT`→cluster collector, `OTEL_SERVICE_NAME`,
  `ENV`→`deployment.environment`); `telemetry.enabled` in `app.yaml` activates `app/telemetry.py`.
  No new telemetry code — config wiring only.
- **FR-CND-5 (Secrets via ESO — Doppler as default backend, v0.2).** The app SHALL source provider
  API keys + DB credentials at runtime from `os.environ`, populated in-cluster via a **vendor-neutral**
  `ExternalSecret` (External Secrets Operator) referencing an **operator-owned `SecretStore`** — the
  SDK emits the reference, never the store or the values. **The default `SecretStore` backend SHALL
  be Doppler** (ESO has a first-class Doppler provider), since Doppler is already the org's secrets
  manager and the SDK already ships a Doppler backend (`src/startd8/secrets/doppler.py`,
  `docs/design/doppler-secrets/`). This is end-to-end consistent: the SDK + generated app already use
  an **env-hydration** model (`os.getenv`, never a central getter), so secrets flow identically in dev
  (`doppler run`) and in-cluster (Doppler → K8s Secret → pod env) **with zero app-code change**.
  A `deploy.secrets.backend` binding SHALL select: `eso-doppler` (default), `doppler-operator`
  (opt-in, emits the Doppler K8s Operator `DopplerSecret` CRD — vendor-specific, like FR-CND-7), or
  `eso-aws`/`eso-gcp` (cloud-native secret manager) for shops not standardizing on Doppler. The
  emitted `ExternalSecret` SHALL set `target.creationPolicy: Owner` (GC the K8s Secret with the
  ExternalSecret — R4-F5) and a `refreshInterval`; rotated upstream secrets reach pods only via
  refresh + a pod restart (reloader annotation or runbook step) — SDK documents, does not orchestrate
  (R2-F7). Doppler **project/config** identifiers are `deploy:`-block bindings surfaced in the
  infra-contract, **never written into the emitted `ExternalSecret`/`SecretStore` reference body**
  (else an operator-bound value is baked into a $0 artifact — R1-F2).
- **FR-CND-6 (Gateway-ready identity — fail-CLOSED, hardened v0.3 R1-F3/R1-S1/R2-F5/R2-S3).** The
  Bearer/JWT seam (auth-seam-jwt, decode-only, trusts an upstream verifier) SHALL be the contract
  agentgateway terminates and forwards. Because a decode-only seam reachable WITHOUT a verifying
  gateway is a silent **auth bypass**, the deterministic artifacts SHALL make direct (non-gateway)
  exposure **fail closed**: by default emit an **internal-only Service (ClusterIP)** + a
  **NetworkPolicy denying ingress** except from the gateway namespace/selector, and emit **no
  internet-facing Service**. An operator may instead assert `deploy.trust_gateway: true` to
  acknowledge an external verifier; the coherence guard (FR-CND-9/M3) SHALL **ERROR** when the auth
  seam is emitted in `deployed` mode with neither the network guard nor the ack (code
  `deployed-decode-only-no-gateway-ack`), cross-referencing `AUTH_SEAM_JWT_REQUIREMENTS.md` FR-JWT-9
  (`VERIFIED_UPSTREAM=False`). The app code is unchanged between "direct" and "behind-gateway"; the
  **network layer**, not the app, enforces the trust boundary.
- **FR-CND-7 (Optional agent integration).** The capability SHALL OPTIONALLY emit reference
  agentgateway/kagent integration (e.g., a kagent-managed workload reference or an agentgateway
  target) — opt-in, vendor-specific, and clearly separated from the vendor-neutral core.
- **FR-CND-8 (App-exposed MCP — DEFERRED v0.2).** A generated app MAY later expose its own MCP
  surface (CRUD/actions as agent-accessible tools) so the app itself can sit behind agentgateway as
  an MCP server, mirroring the SDK's `MCPGateway`. **Deferred to a later increment** — no
  generated-app-CRUD→MCP bridge exists today; it is a separate large capability, not v1 scope.
- **FR-CND-9 (Determinism + bucket line).** All emitted artifacts SHALL be owned/`$0`/drift-checked
  (DeterministicFileProvider pattern), carry the GENERATED header, and be **vendor-neutral reference
  scaffolds**: operator-owned values (image registry/tag, domain/host, replica count, SecretStore,
  IdP issuer, cluster policy) are bound at deploy time (env/ConfigMap/overlay), never baked.
- **FR-CND-10 (Cloud-target neutrality).** The same artifact set SHALL deploy to EKS and GKE; the
  only differences SHALL be operator bindings (registry, secret store backend, ingress/gateway
  class), not separate SDK code paths.
- **FR-CND-11 (Infra-needs contract — the IaC/orchestration seam, added v0.2).** The capability
  SHALL emit a machine-readable **infra-needs contract** (`deploy/infra-contract.yaml`) enumerating
  what the app requires the cluster/cloud to provide — cluster + namespace, container registry, a
  `SecretStore` and the secret keys it expects, a Gateway-API `Gateway`/listener, an OTLP collector
  endpoint, the **Doppler project/config** (default SecretStore backend, FR-CND-5) and — flagged as a
  one-time operator prerequisite — the **Doppler service-token bootstrap** (the single secret seeded
  into the cluster via Terraform/cloud-secret-manager/sealed-secret to break the chicken-and-egg),
  and min CRD/versions (Gateway-API, ESO/Doppler-operator). This is the **seam to provisioning IaC and
  pipeline orchestration**, NOT the provisioning itself: per Mottainai/bucket-4, the SDK does not
  reimplement Terraform/StackGen (infra provisioning) or Kestra/Argo/CI (deploy orchestration) — it
  emits the contract those mature tools consume. The contract MAY render an optional Terraform
  **variables stub** (the inputs, not the resources) to ease hand-off.
- **FR-PILOT-1 (StartDate pilot).** The acceptance surface is the SDK-generated **StartDate** app:
  generate → emit cloud-native artifacts → deploy to EKS or GKE behind agentgateway → graded boot
  ladder (the local-deploy-harness ladder, extended to a cluster) passes.

## 2A. CRP-Accepted Additions (v0.3 — R1–R5 multi-model triage)

> Five models (claude-opus-4-8 ×2, composer-2.5, gemini-3.1-pro, gpt-5.5) converged on real
> production gaps with no contradictions. Amendments to FR-CND-3/5/6 are applied inline above.
> The new FRs below are grouped by theme; **[v1]** = core, **[opt-in]** = behind a `deploy:` flag,
> **[v1.1]** = accepted but phased after first deploy. Per-suggestion dispositions: Appendix A.

**Security / hardening**
- **FR-CND-12 (Pod hardening) [v1].** The Deployment SHALL emit a hardened `securityContext`
  (`runAsNonRoot`, non-zero `runAsUser`, `allowPrivilegeEscalation:false`, `readOnlyRootFilesystem`
  + writable `emptyDir` for temp, `capabilities.drop:[ALL]`, `seccompProfile:RuntimeDefault`) and the
  Dockerfile SHALL add a non-root `USER`, so the default tree is admissible under the **restricted
  PodSecurity Standard**. A dedicated `ServiceAccount` with `automountServiceAccountToken:false` SHALL
  be emitted (the app never calls the K8s API). (R3-F1/R3-S1/R3-S2)
- **FR-CND-13 (NetworkPolicy ingress+egress) [v1].** The fail-closed NetworkPolicy (FR-CND-6) SHALL
  pair its gateway-only **ingress** with an **egress allowlist** — DB, OTLP collector, secret backend
  (Doppler/cloud SM), LLM provider APIs, DNS — with targets sourced from the infra-contract
  (operator-bound, not baked); a deny-ingress policy that omits egress is an outage. (R3-F2/R3-S3)
- **FR-CND-14 (Image binding) [v1].** Deployable image refs SHALL be immutable (`@sha256:` digest
  preferred, or tag + explicit `deploy.image.allowMutableTag:true` ack — `:latest` without ack →
  coherence ERROR), the unbound placeholder SHALL be a **non-pullable sentinel** (M3 ERRORs if it
  survives to a non-render context), and `imagePullSecrets` SHALL be surfaced as operator-bound when a
  private registry is used. (R1-S8/R5-F5/R5-S4)
- **FR-CND-15 (Secret classification) [v1].** Secret-vs-non-secret env partitioning SHALL be a single
  declared list consumed by both the ConfigMap and ExternalSecret renderers; known-secret keys
  (provider API keys, `DATABASE_URL`) SHALL never appear in `configmap.yaml`. `.env.example` keys for
  `deployed` mode SHALL be a subset of the ConfigMap+ExternalSecret key union. (R1-F8/R1-S7/R2-F8)
- **FR-CND-16 (Health not publicly routed) [v1].** The `HTTPRoute` SHALL NOT publicly route
  `/health` / `/health/live` (probes are kubelet-internal); readiness runs `SELECT 1`, so public
  exposure is an unauthenticated DB-touch. (R3-F6)

**Determinism / correctness**
- **FR-CND-17 (Shared-surface SoT + drift) [v1].** Port, `/health` + `/health/live` paths, and
  env-var names SHALL come from one shared-constant source the k8s renderers read; `containerPort`,
  probe ports, and Service `targetPort` SHALL derive from one declared `deploy.port` (honoring a
  `PORT` env). A drift test SHALL fail if a manifest probe path / port diverges from that source.
  YAML serialization SHALL be **byte-stable** (declared key order, no timestamps/run-dependent values,
  stable list order); render-twice → byte-identical. (R1-S4/R2-F3/R2-S2/R3-F5/R3-S6)
- **FR-CND-18 (Naming + labels) [v1].** Every K8s object name derived from `app.name` SHALL be
  DNS-1123-safe (lowercase, `a-z0-9-`, ≤63 chars, trimmed, stable hash on truncation/collision). A
  single label set (`app.kubernetes.io/{name,instance,version,part-of,managed-by}`) SHALL be shared by
  the Deployment pod template and Service `selector` so the selector matches pods by construction.
  (R5-F1/R5-S1/R3-F4/R3-S5)
- **FR-CND-19 (Drift ownership) [v1].** All `deploy/*.yaml` SHALL register in the scaffold drift
  ownership map (`SCAFFOLD_RENDERERS` / `is_owned_scaffold_file`) so the skip-hook + `--check` cover
  them; `deployed`-only emission stays byte-identical-when-absent (SOTTO). (R2-S10)

**Ops / rollout**
- **FR-CND-20 (Cloud-native logging) [v1].** In `deployed` mode the app SHALL log to **stdout**
  (StreamHandler), not a RotatingFileHandler to a local file (invisible to `kubectl logs`, fills
  ephemeral disk). (R4-F1/R4-S1)
- **FR-CND-21 (Migrations before readiness) [v1].** The artifacts SHALL include a one-shot Alembic
  `upgrade head` mechanism (a `migrate` Job, or a documented init pattern) and a runbook ordering
  (migrate → wait → Deployment), since readiness `/health` runs `SELECT 1` and an empty schema fails
  opaquely. (R2-F1/R2-S1)
- **FR-CND-22 (Rollout safety) [v1].** The Deployment SHALL set explicit resource requests/limits
  (sensible defaults, overridable in `deploy:`), a `startupProbe` on `/health/live` (generous
  `failureThreshold` for DB/migration warmup), `terminationGracePeriodSeconds` + documented uvicorn
  SIGTERM drain (readiness→503 before kill), and a `PodDisruptionBudget`. A ConfigMap-checksum
  pod-template annotation **[v1.1]** rolls pods on config change. (R4-F3/F4/R4-S3/S4/R2-S9/R3-S7/R3-S8)
- **FR-CND-23 (K8s OTel attribution) [v1].** Beyond the existing env wiring (FR-CND-4), the Deployment
  SHALL inject Downward-API env (`POD_NAME`/`POD_NAMESPACE`/`NODE_NAME`) and set
  `OTEL_RESOURCE_ATTRIBUTES` with `k8s.namespace.name`/`k8s.pod.name`/`k8s.node.name`/`service.version`;
  the infra-contract SHALL state whether `OTEL_EXPORTER_OTLP_ENDPOINT` is base vs full-traces URL and
  the protocol (the app appends `/v1/traces`). (R5-F4/R5-S5/R2-F6/R2-S6-otlp)
- **FR-CND-24 (Namespace safety) [v1].** Namespaced manifests SHALL carry `metadata.namespace` from
  `deploy.namespace`, and the generated handoff SHALL preflight that the current `kubectl` namespace
  matches. (R5-F6/R5-S6)
- **FR-CND-25 (Autoscaling) [opt-in].** An opt-in `HorizontalPodAutoscaler` (`autoscaling/v2`,
  min/max + CPU/mem targets from `deploy.autoscaling`) MAY be emitted; `metrics-server` becomes an
  infra-contract prerequisite when enabled. (R5-F3/R5-S3)

**Contract / handoff / acceptance**
- **FR-CND-26 (Exhaustive, versioned infra-contract) [v1].** FR-CND-11's contract SHALL be
  machine-checkable with a top-level `schemaVersion` + shipped JSON Schema, and SHALL enumerate each
  prereq as `{name, kind, min_version?, status}` — adding: IdP issuer/JWKS URL (FR-CND-6), OTLP
  protocol/port, Gateway listener hostname/TLS, **CNI-with-NetworkPolicy-enforcement**, target
  **PodSecurity Standard level**, `imagePullSecrets`, `metrics-server` (when HPA), **namespace**, and
  a **DB connection budget** (`replicas × per_pod_pool_size` vs operator DB cap → coherence
  warn/error). (R1-F6/R3-F3/R3-S4/R2-S8/R5-F7/R5-S7)
- **FR-CND-27 (Operator handoff README) [v1].** A deterministic `deploy/README.md` (RUNBOOK) SHALL be
  emitted: apply order (namespace/prereqs → secrets/token → migrate Job → app), placeholder
  checklist, preflight + smoke + rollback commands, and the render-only boundary. Contains commands
  and checks, never secrets/account values. (R5-F2/R5-S2)
- **FR-CND-28 (Vendor-neutrality conformance) [v1].** The default (non-opt-in) `deploy/` tree SHALL
  contain only allowlisted `apiVersion`s (`apps/v1`, `v1`, `gateway.networking.k8s.io/v1`,
  `external-secrets.io/*`); any vendor CRD (Gloo, `DopplerSecret`, kagent/agentgateway, etc.) appears
  ONLY under its opt-in flag — enforced by an M3 lint, and M3 ERRORs (not WARNs) on an ExternalSecret
  with no SecretStore binding. (R1-F7/R1-S3)
- **FR-CND-30 (Machine-readable coherence verdict — added v0.3.1, cross-repo seam) [v1].** The M3
  coherence guard SHALL be exposed as a machine-readable check — `scripts/check_deploy_coherence.py
  --json <project>` returning `{schemaVersion, verdict, findings[], unbound_bindings}` with exit codes
  `0` ok / `1` soft / `2` skip (no `deploy/`) / `3` hard, and each `CoherenceFinding` SHALL carry a
  **severity tier** (`security` | `operational`) at source in `scaffold_codegen/coherence.py`. This is
  the Keiyaku seam the **cap-dev-pipe deploy-coherence gate** consumes (returncode+JSON, like
  `check_seed_quality.py`), so the generation orchestrator can fail-closed on a `deployed` run without
  importing SDK code. Security-tier findings (e.g. `deployed-decode-only-no-gateway-ack`, FR-CND-6)
  are non-overridable downstream. **See `cap-dev-pipe/design/DEPLOY_INTEGRATION_REQUIREMENTS.md`
  REQ-CDP-DEPLOY-6/7/10.** Contract robustness (cap-dev-pipe CRP R1): `findings[].severityTier` is a
  **required** field (3-value `security|operational|advisory`); the consumer treats an absent tier,
  malformed JSON, or `schemaVersion` major-skew as **HARD/fail-closed**, so the SDK MUST emit a
  well-formed versioned verdict with the tier on every finding (a dropped field becomes a security
  regression, not a cosmetic one).
- **FR-CND-29 (Pilot acceptance predicate) [v1].** FR-PILOT-1 SHALL define a machine-readable
  `cluster-smoke-spec.json` mapping the local-harness ladder (discover→install→boot→health→smoke) to
  cluster checks (rollout ready, `/health` green, one authenticated request through agentgateway →
  2xx); PASS = all required stages pass (one boolean predicate), comparable across EKS/GKE.
  (R1-F4/R1-S5/R2-F4)

- **FR-CND-12-OQ9 (OQ-9 resolved → stated requirement) [v1].** The infra-contract is **tool-neutral
  YAML by default**; an optional `--emit-tfvars-stub` renders inputs-only (no resources),
  byte-identical-when-absent (SOTTO); the pilot **documents** the StackGen/Terraform hand-off rather
  than validating against it (coupling acceptance to a bucket-4 tool the SDK doesn't own is wrong).
  (R1-F5/R1-S6)

## 3. Non-Requirements

- NOT a cluster provisioner — operator owns EKS/GKE, the gateway install, the IdP, the SecretStore.
- NOT Gloo-/cloud-vendor CRDs in the core — vendor-neutral Gateway API + ESO only (vendor extras are FR-CND-7, opt-in).
- NOT baking secrets, cloud account IDs, registries, or domains.
- NOT a Helm/kustomize templating engine in v1 (plain manifests; templating deferred — see OQ-5).
- NOT the SDK's own MCP deployment (that was the prior architecture discussion; this is *generated-app* deployment).
- NOT runtime hot-switching of topology (inherits DEPLOYMENT_MODE NR-3).
- **NOT an IaC engine or a deploy orchestrator (Mottainai).** The SDK does NOT reimplement
  Terraform/StackGen (cluster/VPC/IAM/registry/SecretStore/gateway provisioning — bucket-4 operator)
  or Kestra/Argo/CI (build→push→apply→smoke orchestration). It emits the app-layer manifests + the
  infra-needs contract (FR-CND-11) those tools consume. Leverage the mature layer; don't recreate it.

## 4. Open Questions

> OQ-1..OQ-8 were **resolved by the planning pass — see §0** for resolutions. **OQ-9 RESOLVED by CRP
> (R1-F5/R1-S6) → FR-CND-12-OQ9**: tool-neutral YAML default + opt-in `--emit-tfvars-stub`; pilot
> documents the StackGen/Terraform hand-off, does not validate against it. Secrets-backend resolved in
> FR-CND-5 (default `eso-doppler`).

- **OQ-1.** New `app.yaml` block (`deploy:` / `k8s:`) or extend the existing `container:` block?
- **OQ-2.** New `k8s_codegen` module + its own DeterministicFileProvider, or new output kinds inside `scaffold_codegen`?
- **OQ-3.** Does a generated app already expose `/health` (+ liveness) for probes, or must it be added (FR-CND-2)?
- **OQ-4.** Is the generated app's OTLP endpoint already env-configurable, or is new telemetry code needed (FR-CND-4)?
- **OQ-5.** v1 output: plain manifests, or kustomize base+overlays (to make operator bindings cleaner)?
- **OQ-6.** App-exposed MCP (FR-CND-8): in v1 or deferred to a later increment?
- **OQ-7.** How much EKS-vs-GKE divergence is genuinely structural vs operator-bound (FR-CND-10)?
- **OQ-8.** Pilot ladder: extend the local-deploy-harness graded ladder to a real cluster, or a separate cluster-smoke?

---

*v0.2 — Post-planning self-reflective update. 2 requirements narrowed to wiring-only (FR-CND-2/4),
1 deferred (FR-CND-8 app-MCP), 1 added (FR-CND-11 infra-needs contract / IaC seam), render-only
reframe, EKS/GKE no-fork confirmed, 8 open questions resolved, 1 new (OQ-9) for CRP. Three-layer
boundary set: SDK = app-layer manifests + infra contract (bucket 1); Terraform/StackGen = provisioning
(bucket 4); Kestra/Argo/CI = orchestration. Mottainai: leverage mature layers, don't recreate them.*

*v0.3 — Post-CRP multi-model triage (R1–R5: claude-opus-4-8 ×2, composer-2.5, gemini-3.1-pro,
gpt-5.5). 34 F-suggestions ACCEPTED (0 rejected): FR-CND-3/5/6 amended inline (fail-closed identity
is the critical fix), 18 new FRs added (FR-CND-12..29 + OQ9), OQ-9 resolved. Dispositions in
Appendix A. The big lesson: v0.2 had the right boundaries but under-specified production K8s mechanics
(pod hardening, NetworkPolicy egress, migrations, stdout logging, naming/labels, drift SoT).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

> **Triage summary (v0.3, 2026-06-20):** All 34 requirements suggestions (R1–R5) ACCEPTED — a
> rare zero-reject outcome reflecting strong cross-model convergence (and that the v0.2 spec, while
> sound on boundaries, under-specified production K8s mechanics). 2 critical (fail-closed identity,
> migrations) + 3 high folded as inline amendments / FRs; OQ-9 resolved. None rejected; the only
> phased item (FR-CND-22 ConfigMap-checksum) is tagged v1.1.

### Appendix A: Applied Suggestions

| ID | Suggestion | Disposition (where merged) | Date |
|----|------------|----------------------------|------|
| R1-F1 | Doppler service-token bootstrap acceptance criteria | → FR-CND-26 (contract `{name,kind,status}`, MUST-NOT-appear) | 2026-06-20 |
| R1-F2 | Doppler project/config = `deploy:` binding, not baked | → FR-CND-5 (inline) | 2026-06-20 |
| R1-F3 | Fail-CLOSED FR-CND-6 (NetworkPolicy / `trust_gateway` ack) | → FR-CND-6 (inline, critical) | 2026-06-20 |
| R1-F4 | Pilot PASS predicate (required rungs + gate) | → FR-CND-29 | 2026-06-20 |
| R1-F5 | OQ-9 → stated FR (YAML default + opt-in tfvars) | → FR-CND-12-OQ9 (OQ-9 resolved) | 2026-06-20 |
| R1-F6 | Exhaustive machine-checkable prereqs | → FR-CND-26 | 2026-06-20 |
| R1-F7 | Vendor-neutrality `apiVersion` allowlist | → FR-CND-28 | 2026-06-20 |
| R1-F8 | Secret-vs-non-secret classification list | → FR-CND-15 | 2026-06-20 |
| R2-F1 | Alembic migration mechanism before readiness | → FR-CND-21 (critical) | 2026-06-20 |
| R2-F2 | HTTPRoute-only; Gateway not emitted in core | → FR-CND-3 (inline) | 2026-06-20 |
| R2-F3 | Port three-way alignment from one source | → FR-CND-17 | 2026-06-20 |
| R2-F4 | Machine-readable `cluster-smoke-spec.json` | → FR-CND-29 | 2026-06-20 |
| R2-F5 | Cross-ref FR-JWT-9; coherence ERROR on no ack | → FR-CND-6 (inline) | 2026-06-20 |
| R2-F6 | OTLP base-vs-full URL + protocol semantics | → FR-CND-23 | 2026-06-20 |
| R2-F7 | ExternalSecret `refreshInterval` + restart-on-rotation | → FR-CND-5 (inline) | 2026-06-20 |
| R2-F8 | `.env.example` ↔ ConfigMap/ExternalSecret key parity | → FR-CND-15 | 2026-06-20 |
| R3-F1 | Pod hardening (restricted PSS) | → FR-CND-12 | 2026-06-20 |
| R3-F2 | NetworkPolicy egress allowlist | → FR-CND-13 | 2026-06-20 |
| R3-F3 | CNI-enforcement + PodSecurity-level prereqs | → FR-CND-26 | 2026-06-20 |
| R3-F4 | Shared label set; selector ⊆ pod labels | → FR-CND-18 | 2026-06-20 |
| R3-F5 | Byte-stable YAML serialization | → FR-CND-17 | 2026-06-20 |
| R3-F6 | `/health` not publicly routed | → FR-CND-16 | 2026-06-20 |
| R4-F1 | stdout logging in deployed mode | → FR-CND-20 (critical) | 2026-06-20 |
| R4-F2 | HTTPRoute explicit `hostnames` (not `*`) | → FR-CND-3 (inline) | 2026-06-20 |
| R4-F3 | PodDisruptionBudget | → FR-CND-22 | 2026-06-20 |
| R4-F4 | Resource requests/limits defaults | → FR-CND-22 | 2026-06-20 |
| R4-F5 | ExternalSecret `creationPolicy: Owner` | → FR-CND-5 (inline) | 2026-06-20 |
| R5-F1 | DNS-1123-safe naming | → FR-CND-18 | 2026-06-20 |
| R5-F2 | Generated `deploy/README.md` operator handoff | → FR-CND-27 | 2026-06-20 |
| R5-F3 | Opt-in HPA | → FR-CND-25 (opt-in) | 2026-06-20 |
| R5-F4 | Downward-API + `OTEL_RESOURCE_ATTRIBUTES` k8s.* | → FR-CND-23 | 2026-06-20 |
| R5-F5 | Immutable image + `imagePullSecrets` | → FR-CND-14 | 2026-06-20 |
| R5-F6 | Explicit namespace binding + preflight | → FR-CND-24 | 2026-06-20 |
| R5-F7 | DB connection budget + coherence warn | → FR-CND-26 | 2026-06-20 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1–R5 suggestions accepted; FR-CND-22 ConfigMap-checksum + FR-CND-25 HPA accepted as phased/opt-in (not rejected) | 2026-06-20 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-20

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — weighted to the sponsor focus areas (secrets/ESO/Doppler bootstrap, JWT-behind-gateway footgun, vendor-neutrality boundary, bucket-1/4 Mottainai line, determinism/drift, ops prereqs, pilot acceptance, OQ-9). Dual-document review; this round is requirements-only. Plan S-suggestions + coverage matrix live in the plan file's Appendix C / coverage matrix.

##### Sponsor focus asks (answered first)

**Ask 1 — Is `eso-doppler` default sound, and is the FR-CND-11 Doppler service-token bootstrap handled safely? Any leak path violating FR-CND-9?**
- **Summary answer:** Default is sound; the bootstrap seam is *named* but **under-specified**, and there is a latent FR-CND-9 leak risk via the Doppler *project/config* identifiers.
- **Rationale:** FR-CND-5 correctly keeps the SDK emitting only the `ExternalSecret` reference, never the store or values, which matches the env-hydration model. But FR-CND-11 lists "the **Doppler project/config**" as contract content — these are operator-owned bindings, and if the renderer writes them *into the emitted `ExternalSecret`/`SecretStore` ref* rather than the contract-only, that is an operator-bound value baked into a deterministic artifact (FR-CND-9 violation). The service-token bootstrap is mentioned as a one-time prerequisite but never given an acceptance criterion (who seeds it, where it must NOT appear, how absence is detected).
- **Assumptions / conditions:** Doppler project/config names are treated as operator bindings, not constants.
- **Suggested improvements:** see R1-F1 (bootstrap acceptance criteria) and R1-F2 (project/config must be a `deploy:` binding, not baked). 

**Ask 2 — Is "no app change direct vs behind-gateway" (FR-CND-6) safe? Footgun if exposed direct-to-internet without a gateway?**
- **Summary answer:** **No — this is a fail-OPEN footgun as written.** A decode-only JWT seam that trusts an upstream verifier becomes an auth bypass the moment the app is reachable without that verifier in front.
- **Rationale:** FR-CND-6 says the route "SHALL assume upstream identity verification (decode-only seam), with no app change between 'direct' and 'behind-gateway.'" If the same artifact set is applied without a Gateway/agentgateway terminating auth (or with a Service of type LoadBalancer / a misconfigured route), the app decodes but does not *verify* the JWT — any attacker-minted token is trusted. There is no requirement that the deployment fail closed in this state.
- **Assumptions / conditions:** none — this is the defining risk of a decode-only seam.
- **Suggested improvements:** see R1-F3 (fail-closed requirement + a `deploy:` assertion that traffic is gateway-fronted, e.g. require an internal-only Service / NetworkPolicy denying non-gateway ingress, or an explicit `deploy.trust_gateway: true` acknowledgement that surfaces a coherence WARN/ERROR).

**Ask — OQ-9 (Terraform variables stub in v1, or tool-neutral YAML only?).**
- **Summary answer:** **Tool-neutral YAML only in v1; render the Terraform variables stub behind an explicit opt-in flag, and do NOT validate against StackGen/Terraform consumption in the pilot — document the hand-off.**
- **Rationale:** The infra-needs contract (FR-CND-11) is the bucket-1/bucket-4 seam; a `.tfvars`-shaped stub starts pulling Terraform-specific schema assumptions into the neutral core, which erodes the "leverage the mature layer, don't recreate it" Mottainai line (NR, §3). A single canonical YAML contract with a documented, optional `--emit-tfvars-stub` (inputs only, byte-identical-when-absent per SOTTO) preserves neutrality while easing hand-off for Terraform shops. Validating against live StackGen/Terraform in the pilot couples acceptance to an external tool the SDK explicitly does not own (bucket 4) and would inflate FR-PILOT-1 scope.
- **Assumptions / conditions:** the stub is derived purely from the YAML contract (no new inputs), and its absence changes no other byte.
- **Suggested improvements:** see R1-F5 (make OQ-9 a stated FR with the opt-in default) — and the plan-side S-suggestion R1-S6.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Security | high | Add explicit acceptance criteria for the Doppler service-token bootstrap in FR-CND-11: name the seeding mechanism (Terraform/cloud-secret-manager/sealed-secret), state that the token MUST NOT appear in any SDK-emitted artifact, and define how the contract signals the token as an UNMET operator prerequisite (vs a satisfied one). | FR-CND-11 currently calls the bootstrap "a one-time operator prerequisite" with no testable boundary — "handled safely" is asserted, not verifiable. | FR-CND-11, after "...to break the chicken-and-egg" | Grep all emitted artifacts for any token-shaped value; contract lists the bootstrap secret with `status: operator-provided` and absence is detectable. |
| R1-F2 | Security | high | Require the Doppler project/config (and any SecretStore identifiers) to be `deploy:`-block bindings surfaced in the infra-contract, NOT written into the emitted `ExternalSecret`/`SecretStore` reference body. | FR-CND-11 lists "Doppler project/config" as contract content while FR-CND-9 forbids baking operator-owned values; without this, the project/config name leaks into a deterministic artifact. | FR-CND-5 (binding) + FR-CND-9 (explicit "Doppler project/config" added to the operator-bound list) | Drift test: two app.yamls differing only in Doppler project produce byte-identical `externalsecret.yaml`; project name appears only in the contract/ConfigMap. |
| R1-F3 | Security | critical | FR-CND-6 must state a fail-CLOSED posture when no gateway terminates auth: the deterministic artifacts SHALL make direct (non-gateway) exposure either impossible-by-default (internal-only Service + NetworkPolicy denying non-gateway ingress) or loudly flagged (a required `deploy.trust_gateway` acknowledgement that coherence ERRORs without). | As written, "no app change direct vs behind-gateway" + decode-only = silent auth bypass if the app is ever reachable without the verifier. This is the highest-severity gap in the doc. | FR-CND-6, replace "with no app change between 'direct' and 'behind-gateway'" with the fail-closed clause | Apply manifests without a Gateway in front in a test ns; confirm the app is NOT internet-reachable OR coherence/check fails; attacker-minted token is rejected at the network layer. |
| R1-F4 | Validation | high | FR-PILOT-1 must define the minimum acceptance evidence: which rungs of the local-harness graded ladder (discover→install→boot→health→smoke) are REQUIRED at the cluster-smoke rung, and what counts as PASS (e.g. readiness probe green + one authenticated smoke request through agentgateway returns 2xx). | "graded boot ladder ... passes" is untestable without naming the required rungs and the pass bar; an operator could declare any rung sufficient. | FR-PILOT-1, after "extended to a cluster" | Pilot run record shows each required rung result; PASS gate is a single documented predicate. |
| R1-F5 | Architecture | medium | Promote OQ-9 to a stated requirement: v1 emits tool-neutral YAML contract by default; an optional `--emit-tfvars-stub` renders inputs-only (no resources), byte-identical-when-absent; pilot documents the StackGen/Terraform hand-off rather than integrating/validating it. | OQ-9 is the only open question; leaving it open blocks the bucket-1/4 boundary from being testable and risks the stub leaking Terraform schema into the neutral core. | New FR-CND-12 (or fold into FR-CND-11) + resolve OQ-9 in §0/§4 | Default render contains no `.tf`/`.tfvars`; with the flag, stub holds only variable declarations; absence is byte-identical. |
| R1-F6 | Ops | medium | FR-CND-11's prerequisite enumeration should be made exhaustive and machine-checkable: add the IdP issuer/JWKS URL (needed by the gateway for FR-CND-6), the OTLP collector's protocol/port (not just "endpoint"), and the Gateway listener's hostname/TLS expectation — each tagged operator-provided with a min-version where a CRD is involved. | The focus file asks whether ops prereqs are exhaustive; today FR-CND-11 names categories but not the fields an operator actually needs to satisfy (issuer URL, collector protocol, listener TLS), so the contract under-surfaces deploy-time blockers. | FR-CND-11 prerequisite list | Contract schema lists each prereq with `{name, kind, min_version?, status}`; a stub cluster missing any one is reported by the contract consumer. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | medium | State a vendor-neutrality conformance criterion: the core (non-opt-in) artifact set SHALL contain ONLY `apiVersion`s in an allowlist (`apps/v1`, `v1`, `gateway.networking.k8s.io/v1`, `external-secrets.io/*`); any vendor CRD (`gloo`, `getambassador`, Doppler-operator `DopplerSecret`, kagent/agentgateway) appears ONLY under an explicit opt-in flag. | FR-CND-3/7 describe the intent prose-only; "is the line clean?" (focus area 3) is unverifiable without an enumerable allowlist that a drift/lint test can assert against. | FR-CND-9 or a new FR (vendor-neutrality conformance) | Lint the default `deploy/` tree: every `apiVersion` ∈ allowlist; flip `deploy.secrets.backend: doppler-operator` and confirm the CRD appears only then. |
| R1-F8 | Data | low | FR-CND-1's `ConfigMap` vs `Secret`/`ExternalSecret` split needs an explicit classification rule (which env keys are non-secret vs secret), so the split is deterministic rather than per-renderer judgement. | "non-secret" vs "secret" is asserted but the partitioning rule is implicit; a misclassification (e.g. `DATABASE_URL` landing in the ConfigMap) is a silent credential leak into a $0 artifact. | FR-CND-1 | Test: known-secret keys (provider API keys, `DATABASE_URL`) never appear in `configmap.yaml`; classification is a single declared list. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.

#### Review Round R2 — composer-2.5 — 2026-06-20

- **Reviewer**: composer-2.5
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — second pass. Operational deploy-time acceptance criteria, cross-doc consistency (auth-seam ↔ deploy), and extensions to R1 untriaged items. Plan S-suggestions + coverage matrix R2 in the plan file's Appendix C / end of plan.

##### Sponsor focus asks (second-pass deltas)

**Ask 1 — Secrets path (extends R1):**
- **Summary answer:** Partial — ESO seam remains sound; add **ESO `refreshInterval` + rotation restart** and **`.env.example` ↔ ConfigMap/ExternalSecret key parity** as acceptance criteria.
- **Rationale:** FR-CND-5 covers fetch-at-deploy; rotated in-cluster secrets won't reach pods without refresh + restart (R2-S7). `render_env_example` (`scaffold_codegen/renderers.py:252-284`) documents env keys that ConfigMap/ExternalSecret must partition consistently with R1-F8.
- **Assumptions / conditions:** Rotation handled operator-side (reloader or runbook), not SDK-orchestrated.
- **Suggested improvements:** R2-F7 (rotation acceptance); endorse R1-F1/F2.

**Ask 4 — Bucket-1/4 line (extends R1):**
- **Summary answer:** Yes, with gap — **Alembic migration mechanism** must be in requirements, not only coherence ERROR on missing migrations.
- **Rationale:** FR-CFG-5 (via coherence) requires migrations in `deployed` mode, but FR-CND-1 names only Deployment/Service — no requirement for who runs `alembic upgrade head` before readiness.
- **Assumptions / conditions:** Job preferred over init-container for observability of migration failure.
- **Suggested improvements:** R2-F1.

**Ask 5 — Determinism / drift (extends R1):**
- **Summary answer:** R1-S4 direction correct; extend with **PORT three-way** (`containerPort`, probes, Service `targetPort`) and explicit SoT module.
- **Rationale:** FR-CND-1 says "wrapping the existing container" but does not require port/probe alignment when `PORT` env overrides default 8000.
- **Assumptions / conditions:** Port declared in `deploy:` block or shared constant.
- **Suggested improvements:** R2-F3; endorse R1-F8.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Ops | critical | Add acceptance criterion: emitted artifacts **SHALL** include a one-shot migration mechanism (Job or documented init pattern) OR runbook-mandated ordered apply such that schema is at Alembic head **before** Deployment readiness is expected. Extends FR-CND-2 probe wiring — probes assume DB exists. | FR-CND-2 wires probes to `/health` (DB `SELECT 1`); coherence ERRORs on `deployed` without migrations — but FR-CND-1 never names who runs migrations. First deploy fails opaquely. | FR-CND-1 or new FR-CND-13 (migration Job) | Pilot runbook shows ordered apply; readiness fails on empty DB without prior migration step. |
| R2-F2 | Architecture | medium | Amend FR-CND-3: HTTPRoute references **operator-provided** Gateway via `deploy.gateway.*` bindings; SDK **SHALL NOT** emit `Gateway` resources in the default core set. Remove or gate "referenceable `Gateway`/listener stub" behind `deploy.emit_gateway_stub: true` (opt-in, off). | FR-CND-3 says emit "HTTPRoute (and a referenceable `Gateway`/listener stub)" while plan M1 says operator-owned Gateway only — contradictory and risks baking operator Gateway config (FR-CND-9). | FR-CND-3, second sentence | Default artifact lint: no `kind: Gateway`; HTTPRoute `parentRef` from `deploy:` binding only. |
| R2-F3 | Data | medium | FR-CND-1 **SHALL** require `containerPort`, Service `targetPort`, and probe ports derive from the same declared port (`deploy.port` or shared constant), honoring `PORT` env if set in ConfigMap. | "Wrapping the existing container" does not bind port alignment; Dockerfile hardcodes 8000 (`renderers.py:118`) while `run.sh` uses `${PORT:-8000}` — probe/port drift is silent. | FR-CND-1, after resource requests/limits | Change `deploy.port` → containerPort + probes + Service `targetPort` update together; drift test catches mismatch. |
| R2-F4 | Validation | high | FR-PILOT-1 **SHALL** require a machine-readable `cluster-smoke-spec.json` mapping harness `Stage` enum (`deploy_harness/ladder.py`: discover→install→boot→health→smoke) to cluster checks (rollout ready, `/health`, authenticated agentgateway 2xx). PASS = all required stages `pass`. Extends R1-F4. | R1-F4 names rungs in prose; without a structured artifact the pilot record is not machine-greppable or comparable across EKS/GKE runs. | FR-PILOT-1 | Pilot artifact includes spec + per-stage results; single boolean PASS predicate. |
| R2-F5 | Security | high | FR-CND-6 **SHALL** cross-reference auth-seam FR-JWT-9: when auth seam is emitted in `deployed` mode, deploy artifacts **SHALL** enforce gateway-fronted traffic **or** explicit `deploy.trust_gateway` operator acknowledgement (coherence ERROR without). Extends R1-F3. | FR-CND-6 and FR-JWT-9 are separate docs today; decode-only trust model is not wired into deploy acceptance. | FR-CND-6 + cross-ref to `AUTH_SEAM_JWT_REQUIREMENTS.md` FR-JWT-9 | Same as R1-F3 + coherence ERROR code when auth + no ack. |
| R2-F6 | Ops | medium | FR-CND-11 / FR-CND-4: infra-contract **SHALL** specify whether `OTEL_EXPORTER_OTLP_ENDPOINT` is base URL vs full traces URL and protocol (`http/protobuf` default), because `app/telemetry.py` appends `/v1/traces` (`telemetry_renderer.py:98`). Extends R1-F6. | R1-F6 adds protocol/port category; the generated app mutates the endpoint — contract must match or traces silently fail. | FR-CND-11 prerequisite list + FR-CND-4 | ConfigMap value + contract field document base-vs-full URL; pilot collector receives spans. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F7 | Ops | low | FR-CND-5 **SHALL** state that `ExternalSecret` includes `refreshInterval` and that operators **SHALL** restart workloads (or use a reloader) when upstream secrets rotate — stale pod env is a post-deploy failure mode. | ESO fetches secrets asynchronously; without refresh + restart, rotated API keys/DB URLs won't reach running pods. | FR-CND-5, after ExternalSecret reference | Emitted ExternalSecret has `refreshInterval`; contract documents restart expectation. |
| R2-F8 | Validation | low | Add acceptance: `.env.example` keys for `deployed` mode (`render_env_example`) **SHALL** be a subset-check against ConfigMap + ExternalSecret key union — no key documented in `.env.example` missing from the deploy env surface. | End-user discovers env vars from `.env.example`; silent omission from ConfigMap/ExternalSecret breaks dev→cluster parity. | FR-CND-1 or FR-CND-9 | Test: every `deployed` `.env.example` key appears in ConfigMap or ExternalSecret classification list. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1 suggestions):

- **R1-F1, R1-F2** — Doppler bootstrap + project/config binding; still highest-priority security items.
- **R1-F3** — fail-closed FR-CND-6; R2-F5 extends with FR-JWT-9 cross-ref.
- **R1-F4** — pilot PASS predicate; R2-F4 adds machine-readable spec.
- **R1-F5** — OQ-9 resolution; unchanged.
- **R1-F6** — exhaustive infra-contract prereqs; R2-F6 adds OTLP URL semantics.
- **R1-F7, R1-F8** — vendor allowlist + secret classification; unchanged.

**Disagreements:** none.

#### Review Round R3 — claude-opus-4-8 — 2026-06-20

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — third pass. New surface R1/R2 did not touch: container/pod hardening for PodSecurity admission, NetworkPolicy egress as the load-bearing half of the R1-F3 fail-closed posture, K8s label coupling, serialization determinism, and unauthenticated health exposure. Plan S-suggestions + coverage matrix R3 in the plan file.

##### Sponsor focus asks (third-pass deltas)

**Ask 2 — Identity behind the gateway (extends R1-F3 / R2-F5):**
- **Summary answer:** The fail-closed direction is right, but **incomplete in two ways**: (a) a deny-ingress NetworkPolicy without an egress allowlist is an outage, and (b) NetworkPolicy is unenforced on some CNIs, making the guarantee nominal.
- **Rationale:** R1-F3 requires a NetworkPolicy/internal-only Service; it does not require the egress rules the app needs (DB, OTLP, secret backend, provider APIs, DNS) nor a cluster capability (CNI enforcement). Both are needed for the posture to be real and non-breaking.
- **Assumptions / conditions:** egress targets come from the infra-contract (operator-bound), not baked.
- **Suggested improvements:** R3-F2 (egress allowlist), R3-F3 (CNI prerequisite).

**Ask 6 — Ops prerequisites (extends R1-F6):**
- **Summary answer:** Add **CNI-with-NetworkPolicy-enforcement** and **PodSecurity Standard level** of the target namespace to the prerequisite contract.
- **Rationale:** A `restricted`-PSS namespace rejects a root/no-securityContext pod (R3-F1); an unenforced-NetworkPolicy CNI nullifies R1-F3. Both are deploy-time blockers the contract currently omits.
- **Assumptions / conditions:** none.
- **Suggested improvements:** R3-F1, R3-F3.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Security | high | FR-CND-1/FR-CND-9 SHALL require a hardened pod posture: non-root container (`USER` in Dockerfile + `runAsNonRoot`), `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, dropped capabilities, and `seccompProfile: RuntimeDefault`, so the default artifact set is admissible under the **restricted PodSecurity Standard**. | The generated Dockerfile runs as root and the Deployment declares no `securityContext`; a `restricted`-PSS namespace rejects the manifest, and elsewhere it runs privileged. Unaddressed by R1/R2. | FR-CND-1 (workload manifests) + FR-CND-9 | Apply default tree to a `pod-security.kubernetes.io/enforce: restricted` namespace → admitted; container is non-root with read-only rootfs. |
| R3-F2 | Security | high | FR-CND-6/FR-CND-9: if the deterministic artifacts include a NetworkPolicy (R1-F3 fail-closed), it SHALL include an **egress allowlist** for the DB, OTLP collector, secret backend (Doppler/cloud SM), LLM provider APIs, and DNS — targets sourced from the infra-contract, not baked. | A deny-all-ingress NetworkPolicy commonly flips the pod to deny-all-egress; without explicit egress the running app loses its DB/telemetry/secrets/providers. R1-F3 specified ingress only. | FR-CND-6 (fail-closed clause) + FR-CND-11 (egress targets) | Apply policy; app reaches all dependencies; deleting one egress rule breaks exactly that dependency (proves the rule, not the CNI). |
| R3-F3 | Ops | medium | FR-CND-11 SHALL enumerate **CNI-with-NetworkPolicy-enforcement** and the **target-namespace PodSecurity Standard level** as operator prerequisites. | R1-F3's security guarantee is a no-op on CNIs that ignore NetworkPolicy (e.g. default flannel), and R3-F1's manifest is rejected by a `restricted` namespace — both are deploy-time blockers the contract omits. | FR-CND-11 prerequisite list (extends R1-F6) | Contract lists `{cni-networkpolicy, pod-security-level}` with `status: operator-provided`; a missing-capability cluster is flagged pre-apply. |
| R3-F4 | Data | medium | FR-CND-1 SHALL require a single recommended-label set (`app.kubernetes.io/name|instance|version|part-of|managed-by`) shared by the Deployment pod template and the Service `selector`, so the selector matches pods by construction. | A Service selector that doesn't match pod labels routes to zero endpoints and fails silently — the generator should make this impossible, not leave it to per-renderer judgement. | FR-CND-1, after Deployment/Service | Service `selector` ⊆ pod-template labels; backend has ≥1 ready endpoint; HTTPRoute resolves. |
| R3-F5 | Validation | medium | FR-CND-9 SHALL require **byte-stable** YAML serialization (declared key order, no timestamps/run-dependent values, deterministic list ordering) — the precondition for `$0` drift-checking to be meaningful. | "Owned/`$0`/drift-checked" presumes byte-stability; non-deterministic mapping/list ordering makes `--check` flap with no real change. R1-S4 covers app-reality drift, not serialization. | FR-CND-9 (determinism clause) | Render twice (same process + fresh import) → byte-identical; `--check` reports in-sync on an untouched tree. |
| R3-F6 | Security | low | FR-CND-3 SHALL state that the emitted `HTTPRoute` does **not** publicly route `/health` and `/health/live`; probes are kubelet-internal. Readiness `/health` runs `SELECT 1`, so public exposure is an unauthenticated DB-touch endpoint (info-leak / light DoS). | `app/health.py` readiness hits the DB; if the HTTPRoute matches `/` it also exposes `/health` through the gateway with no auth. Probes don't need gateway routing (kubelet calls the pod directly). | FR-CND-3 (route path scoping) | HTTPRoute path rules exclude `/health*`, or doc states probes are kubelet-only; external GET `/health` is not routable. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2 suggestions):

- **R1-F3 / R2-F5** — fail-closed FR-CND-6; R3-F2 (egress) + R3-F3 (CNI prereq) are required to make it real and non-breaking.
- **R1-F6** — exhaustive machine-checkable prereqs; R3-F3 adds CNI + PodSecurity level.
- **R2-F1** — Alembic migration mechanism; pairs with rollout-safety items.
- **R1-F8 / R2-F3** — secret classification + port alignment; R3-F4 extends the same single-source discipline to labels.

**Disagreements:** none — R3 is additive and second-order to R1/R2.

#### Review Round R4 — gemini-3.1-pro — 2026-06-20

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — fourth pass. Focus on cloud-native logging, routing conflicts, resource bounds, and disruption budgets. Plan S-suggestions + coverage matrix R4 in the plan file.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | critical | FR-CND-1 SHALL require that application logs are emitted to standard output (`stdout`) rather than a local file. | Cloud-native observability relies on container runtimes capturing stdout/stderr. File-based logging breaks `kubectl logs` and log aggregation. | FR-CND-1 (workload manifests) | Deployed app logs are visible via `kubectl logs`. |
| R4-F2 | Interfaces | high | FR-CND-3 SHALL state that the emitted `HTTPRoute` must specify explicit `hostnames` bound from operator configuration, rather than defaulting to `*`. | Prevents route hijacking or conflicts on a shared Gateway. | FR-CND-3 (Gateway API routing) | `HTTPRoute` includes `hostnames` field. |
| R4-F3 | Ops | medium | FR-CND-1 SHALL require the emission of a `PodDisruptionBudget` to ensure high availability during cluster maintenance. | Formalizes the requirement for disruption tolerance during node drains. | FR-CND-1 | `deploy/pdb.yaml` is emitted. |
| R4-F4 | Ops | medium | FR-CND-1 SHALL require explicit resource requests and limits for the container. | Prevents noisy neighbor issues and ensures predictable scheduling. | FR-CND-1 | `Deployment` includes `resources` block. |
| R4-F5 | Security | low | FR-CND-5 SHALL require the `ExternalSecret` to manage the lifecycle of the target `Secret` (e.g., via `creationPolicy: Owner`). | Prevents orphaned secrets from lingering in the cluster after the `ExternalSecret` is removed. | FR-CND-5 (Secrets via ESO) | `ExternalSecret` includes `creationPolicy: Owner`. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2/R3 suggestions):

- **R3-F1** — PodSecurity Standard hardening.
- **R3-F2** — NetworkPolicy egress allowlist.
- **R3-F4** — Service selector ↔ Deployment label coupling.

**Disagreements:** none — R4 is additive.

#### Review Round R5 — gpt-5.5 — 2026-06-20

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-20 (UTC)
- **Scope**: Requirements quality (F-prefix) — fifth pass. Focus on fresh gaps not covered by R1-R4: Kubernetes name validity, operator handoff UX, autoscaling, immutable image binding, OTel Kubernetes attribution, namespace safety, and database connection budgeting. Plan S-suggestions + coverage matrix R5 live in the plan file.

##### Sponsor focus asks (fifth-pass deltas)

**Ask 4 — Bucket-1/bucket-4 seam (extends R1/R2):**
- **Summary answer:** The render-only boundary is right, but the end-user handoff should be a generated artifact, not scattered prose.
- **Rationale:** FR-CND-11 gives machines the infra-needs contract, but operators need a concise apply order, placeholder checklist, smoke command, rollback command, and boundary reminder. This stays bucket 1 because it is deterministic documentation generated from the same app/deploy contract; it does not provision infrastructure or run `kubectl`.
- **Assumptions / conditions:** The README contains commands and checks, not secrets or cloud account values.
- **Suggested improvements:** R5-F2.

**Ask 6 — Ops prerequisites (extends R1-F6/R3-F3):**
- **Summary answer:** Add metrics-server, namespace binding, image-pull-secret, and database connection-cap fields to the infra-needs contract.
- **Rationale:** Prior rounds added Gateway/ESO/CNI/PodSecurity prereqs. The next apply-time failures are HPA without metrics-server, private images without pull secrets, wrong `kubectl` namespace, and replica counts that exhaust DB connections.
- **Assumptions / conditions:** These are operator-bound fields surfaced in `infra-contract.yaml`, not SDK-provisioned resources.
- **Suggested improvements:** R5-F3, R5-F5, R5-F6, R5-F7.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Validation | high | FR-CND-1/FR-CND-9 SHALL require deterministic DNS-1123-safe naming for every Kubernetes object derived from `app.name`: lowercase, `a-z0-9-`, max 63 chars, trim leading/trailing hyphens, and stable hash suffix on truncation/collision. | Kubernetes rejects names with uppercase, underscores, spaces, or excessive length. This is an easy pre-apply failure to prevent deterministically. | FR-CND-1 (workload manifests) + FR-CND-9 (determinism) | App names with spaces/uppercase/100 chars render valid stable names; collision fixture gets distinct suffixes. |
| R5-F2 | Ops | high | FR-CND-11/FR-PILOT-1 SHALL require a generated `deploy/README.md` (or `RUNBOOK.md`) containing apply order, operator placeholder checklist, prereq checks, smoke command, rollback command, and the render-only boundary. | The machine-readable contract helps tools; the operator needs a concise generated handoff to avoid misordered apply, missing placeholders, and unclear rollback. | FR-CND-11 + FR-PILOT-1 | StartDate pilot can be executed from generated README plus operator values; README contains all required sections. |
| R5-F3 | Ops | medium | FR-CND-1 SHALL support an opt-in `HorizontalPodAutoscaler` (`autoscaling/v2`) with `minReplicas`, `maxReplicas`, and CPU/memory targets; FR-CND-11 SHALL list metrics-server as a prereq when enabled. | R4-F4 adds resource requests/limits; HPA is the low-hanging scale feature that uses them. It should be opt-in to avoid adding cluster requirements for simple deployments. | FR-CND-1 + FR-CND-11 | No HPA when absent; enabling autoscaling emits HPA and infra-contract `metrics-server` prereq. |
| R5-F4 | Ops | medium | FR-CND-4 SHALL require Kubernetes OTel attribution: Downward API env for pod/namespace/node and `OTEL_RESOURCE_ATTRIBUTES` including `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name`, `service.version`, and `deployment.environment`. | Current telemetry resource construction only includes `service.name` and `deployment.environment`; multi-app clusters need pod/namespace attribution for Tempo/Grafana correlation. | FR-CND-4 | Pilot trace contains namespace/pod/node attributes; Deployment includes Downward API env. |
| R5-F5 | Security | high | FR-CND-9 SHALL require deployable image references to be immutable (`@sha256:` digest preferred) or require an explicit `allowMutableTag: true` acknowledgement; FR-CND-11 SHALL surface `imagePullSecrets` as operator-provided when a private registry is used. | R1-S8 catches unbound placeholders but not mutable tags or private registry auth. Mutable tags undermine reproducibility; missing pull secrets produce `ImagePullBackOff` after apply. | FR-CND-9 + FR-CND-11 | `:latest` without ack fails coherence; digest passes; private registry fixture renders `imagePullSecrets` and contract field. |
| R5-F6 | Ops | medium | FR-CND-11 SHALL require explicit namespace binding: generated manifests either carry `metadata.namespace` from `deploy.namespace`, or the generated README/preflight verifies the current `kubectl` namespace matches the contract. | Applying into the wrong namespace is a common operator footgun; FR-CND-11 names namespace but does not make the apply behavior safe. | FR-CND-11 | Changing `deploy.namespace` updates all namespaced objects or README preflight blocks wrong namespace. |
| R5-F7 | Data | medium | FR-CND-11 SHALL include a DB connection budget (`replicas`, `per_pod_pool_size`, `max_expected_connections`, optional `operator_db_connection_cap`) and require a warning/error when replica count can exceed the DB cap. | Scaling pods can exhaust Postgres connections even if health probes pass initially. This is a cross-layer operational failure that belongs in the infra-needs seam. | FR-CND-11 | Fixture with replicas × pool size above cap produces coherence warning/error; contract records the computed budget. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2/R3/R4 suggestions):

- **R2-F4** — machine-readable pilot smoke spec; R5-F2 adds the human operator handoff around it.
- **R4-F4** — resource requests/limits; R5-F3 builds opt-in HPA on top.
- **R1-F5** — YAML-first infra contract; R5-F6/R5-F7 add fields that preserve that seam without provisioning.
- **R4-F1** — stdout logging; R5-F4 completes the observability story with K8s trace attribution.
- **R1-F3 / R2-F5 / R3-F2** — fail-closed gateway posture; R5-F6 reduces namespace mistakes that can undermine those manifests operationally.

**Disagreements:** none — R5 is additive and focuses on operator usability plus scale-time risks.
