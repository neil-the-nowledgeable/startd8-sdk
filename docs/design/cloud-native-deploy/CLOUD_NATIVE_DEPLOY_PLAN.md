# Cloud-Native Deployment Artifacts — Implementation Plan

**Version:** 1.1 (Post-CRP — R1–R5 triage folded into milestones)
**Date:** 2026-06-20
**Tracks:** `CLOUD_NATIVE_DEPLOY_REQUIREMENTS.md` (v0.3)

---

## 1. Planning Discoveries (fed back into requirements §0)

| Requirements assumed (v0.1) | Code reality | Impact |
|---|---|---|
| FR-CND-2: a `/health`+liveness endpoint must be ADDED | **Already emitted** — `health_renderer.py` → `app/health.py` (kind `fastapi-health`): `GET /health` (readiness, `SELECT 1` via get_session) + `GET /health/live` (liveness); mounted in `crud_generator.py:385`. The deploy harness already probes the bare `/health`. | **FR-CND-2 narrows to "wire K8s probes to the existing paths"** — zero app-code change. |
| FR-CND-4: new OTel bootstrap code needed | **Already emitted** — `telemetry_renderer.py` → `app/telemetry.py` when `telemetry.enabled`; `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, and `ENV`→`deployment.environment` are all **env-overridable at runtime**. | **FR-CND-4 narrows to "enable telemetry in app.yaml + set deploy-time env to the cluster collector"** — code exists. |
| New `app.yaml` block shape unknown (OQ-1) | `AppManifest` (`manifest.py`) is strict-keyed with sibling blocks `app/persistence/logging/migrations/container/deployment/telemetry/messaging`; unknown keys hard-error (no LLM fallback). | **Add a new strict `deploy:` block** (k8s settings) parallel to `container:`/`deployment:`. Don't overload `container:`. |
| Home module unknown (OQ-2) | `scaffold_codegen` already owns app.yaml-derived plumbing (pyproject/logging/alembic/**Dockerfile**) via `ScaffoldFileProvider` + `SCAFFOLD_RENDERERS` + `#`-comment GENERATED headers + drift. | **Emit the K8s/Gateway/ESO manifests as new scaffold output kinds** (optionally a `scaffold_codegen/k8s/` submodule) reusing the provider/drift/header. No new provider plumbing. |
| Much of "cloud-native" is unbuilt | health ✓, OTel env-config ✓, container/0.0.0.0 bind ✓ (FR-NET), auth seam ✓ (auth-seam-jwt), settings ✓ (FR-CFG-7), tenancy ✓ (M3). | **The capability is mostly a MANIFEST LAYER that wires together things the app already exposes** — far smaller than v0.1 implied. ~40% of FRs narrowed from "build app code" to "emit manifests pointing at existing surfaces." |
| EKS vs GKE may need separate code paths (OQ-7) | Structural manifests (Deployment/Service/HTTPRoute/ExternalSecret) are identical; only operator bindings differ (ECR vs Artifact Registry; AWS Secrets Mgr vs GCP Secret Mgr SecretStore; gateway class). | **One artifact set; cloud-specifics are operator bindings** (ConfigMap/env/SecretStore ref) — FR-CND-10 confirmed feasible, no fork. |
| SDK could run the deploy (OQ-8) | The SDK never provisions/touches operator cloud creds; `secrets/` hydrates env, deploy harness stays in a local sandbox. `kubectl apply`/image build+push touch the operator's cluster + registry. | **`startd8 deploy k8s` is RENDER-ONLY ($0):** emit manifests; `kubectl apply`/build/push are operator-run (documented runbook). Mirrors "SDK emits, operator deploys." |
| App-exposed MCP is in scope (FR-CND-8) | No generated-app-CRUD→MCP bridge exists; `MCPGateway` fronts skills/workflows, not generated app routes. Building it is a separate, large capability. | **Defer FR-CND-8** to a later increment (tracked stretch). v1 = the app is gateway-/HTTP-ready, not MCP-exposing. |

> ~50% of v0.1 FRs revised (2 narrowed to wiring-only, 1 deferred, render-only reframe, no-fork confirmation).
> Past the 30% bar — the substrate was richer than assumed; the real work is the manifest layer + a render command.

## 2. Approach (milestones)

**M0 — Manifest model + `deploy:` block.** Add a strict `deploy:` block to `AppManifest`
(`scaffold_codegen/manifest.py`): replicas, resource requests/limits, gateway listener ref,
secret-store ref name, image placeholder. Strict-keyed, mode-aware (deploy artifacts emit only in
`deployed` mode, like `settings.py`/`auth.py`).

**M1 — Vendor-neutral manifest renderers** (`scaffold_codegen/k8s/`, new output kinds; reuse
`ScaffoldFileProvider`/drift/header):
- `k8s-deployment` → `deploy/deployment.yaml` — container from the existing Dockerfile image
  (`image:` is an operator-bound placeholder), env from ConfigMap+Secret, **liveness probe
  `/health/live` + readiness probe `/health`** (FR-CND-2 wired, not built), resource limits.
- `k8s-service` → `deploy/service.yaml`.
- `k8s-configmap` → `deploy/configmap.yaml` — non-secret env incl. `OTEL_EXPORTER_OTLP_ENDPOINT`
  (cluster collector), `OTEL_SERVICE_NAME`, `ENV` (FR-CND-4 wired).
- `k8s-httproute` → `deploy/httproute.yaml` — Gateway API `HTTPRoute` referencing an operator-owned
  `Gateway`/listener (FR-CND-3). Standard `gateway.networking.k8s.io`, never Gloo CRDs.
- `k8s-externalsecret` → `deploy/externalsecret.yaml` — ESO `ExternalSecret` referencing an
  operator-owned `SecretStore` (name is a `deploy:` binding), keys = provider API keys + `DATABASE_URL`
  (FR-CND-5). **Default backend = Doppler** (ESO Doppler provider) — consistent with the SDK's existing
  `secrets/doppler.py` + env-hydration model, so secrets flow identically dev (`doppler run`) →
  in-cluster (Doppler→K8s Secret→pod env), zero app change. `deploy.secrets.backend` selects
  `eso-doppler` (default) / `doppler-operator` (opt-in `DopplerSecret` CRD) / `eso-aws|eso-gcp`. SDK
  emits the reference, never the store/values; the Doppler service token is an operator bootstrap
  (infra-contract prerequisite).
- `deploy-infra-contract` → `deploy/infra-contract.yaml` — the **IaC/orchestration seam** (FR-CND-11):
  machine-readable list of what the app needs the cluster/cloud to provide (cluster+namespace,
  registry, SecretStore + expected keys, Gateway/listener, OTLP collector, min CRD versions). The
  three-layer boundary in one artifact: **SDK emits this → Terraform/StackGen provision from it →
  Kestra/Argo/CI orchestrate apply.** Optional Terraform variables stub (inputs only, not resources).
  Per Mottainai/NR: the SDK does NOT generate the Terraform resources or the pipeline itself.

**M2 — `startd8 deploy k8s --render` (RENDER-ONLY, $0).** CLI that emits the `deploy/` tree from
`app.yaml`; `--check` drift like `generate backend`. No `kubectl`, no build/push. Wireframe surfaces
the deploy artifacts + operator-bound placeholders.

**M3 — Coherence + bucket guard.** Extend `scaffold_codegen/coherence.py`: ERROR if `deploy:` present
without `deployment.mode: deployed`; WARN if `ExternalSecret` keys reference secrets with no
SecretStore binding; surface "operator must bind: image, host, SecretStore, gateway" advisory.

**M4 — Optional agent integration (FR-CND-7, opt-in, separated).** Behind a `deploy.agentgateway: true`
flag: emit a reference agentgateway target / kagent workload reference. Clearly vendor-specific,
outside the vendor-neutral core. (FR-CND-8 app-exposed MCP stays deferred.)

**M5 — StartDate pilot (FR-PILOT-1).** Generate StartDate's app + `deploy/` tree; produce a runbook:
build→push to ECR/Artifact Registry → `kubectl apply` → rollout → probe via agentgateway → smoke.
Extend the local-deploy-harness graded ladder conceptually to a cluster-smoke rung (operator-run).

## 2A. CRP Milestone Deltas (v1.1 — R1–R5 triage)

The accepted S-suggestions expand the milestones. New artifact kinds and guards (dispositions: Appendix A):

- **M0 `deploy:` block** gains: `port`, `hostnames`, `namespace`, `image{digest|tag,allowMutableTag,registry.pullSecretRef}`, `resources`, `trust_gateway`, `emit_gateway_stub`, `autoscaling`, `secrets.backend`, plus a **DNS-1123 name sanitizer** (R5-S1) and a **shared `app_surfaces` constants** module for port/health-paths/env (R1-S4/R2-S2). [FR-CND-17/18]
- **M1 new/expanded kinds:** `k8s-networkpolicy` (gateway-only ingress **+ egress allowlist**, R1-S1/R3-S3); `k8s-serviceaccount` (`automountServiceAccountToken:false`, R3-S2); `k8s-job` migrate (Alembic `upgrade head`, R2-S1); `k8s-pdb` (R4-S3); opt-in `k8s-hpa` (R5-S3); `deploy-runbook` → `deploy/README.md` (R5-S2). `k8s-deployment` gains hardened `securityContext` + non-root Dockerfile `USER` (R3-S1), shared label set + selector coupling (R3-S5), `startupProbe`/`terminationGracePeriodSeconds`/resources (R2-S9/R3-S7/R4-S4), Downward-API + `OTEL_RESOURCE_ATTRIBUTES` (R5-S5), ConfigMap-checksum annotation [v1.1] (R3-S8). `k8s-service` → ClusterIP-only by default (R1-S1). `k8s-httproute` → explicit `hostnames` + binding `parentRef`, excludes `/health*` (R4-S2/R3-S6). `k8s-externalsecret` → `creationPolicy:Owner` + `refreshInterval` (R4-S5/R2-S7). `render_logging` → stdout in deployed mode (R4-S1). `deploy-infra-contract` → `schemaVersion` + JSON Schema + exhaustive prereqs incl. CNI/PSS/namespace/metrics-server/DB-budget (R2-S8/R3-S4/R5-S6/S7).
- **M2 entry point unified (R2-S6):** `generate scaffold` emits `deploy/` when `deployment.mode: deployed` (one drift surface via `ScaffoldFileProvider`); `startd8 deploy k8s` = focused alias + `--render`/`--check`. Wireframe gains a `deploy/` section listing kinds + unbound placeholders (R2-S5). `--emit-tfvars-stub` opt-in (OQ-9).
- **M3 guards strengthened:** ERROR (not WARN) on dangling SecretStore; **vendor-neutrality `apiVersion` allowlist** lint (R1-S3); coherence ERROR `deployed-decode-only-no-gateway-ack` (R2-S3); non-pullable image sentinel + `:latest`-without-ack ERROR (R1-S8/R5-S4); DB-connection-budget warn/error (R5-S7).
- **M0 drift ownership (R2-S10):** register `deploy/*.yaml` GENERATED headers in `SCAFFOLD_RENDERERS`/`is_owned_scaffold_file`; **byte-stable serialization** discipline + render-twice test (R3-S6).
- **M5 pilot:** machine-readable `cluster-smoke-spec.json` PASS predicate (R1-S5/R2-S4); runbook seeds Doppler token before apply (R1-S2); reuse generated `deploy/README.md`.

## 3. Validation

```bash
PYTHONPATH=$PWD/src .venv/bin/pytest tests/unit/scaffold_codegen/ -v        # manifest + renderers + drift
# every emitted YAML must parse + pass `kubectl --dry-run=client` (gated, operator env) and a vendor-neutral schema check
PYTHONPATH=$PWD/src .venv/bin/python -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('deploy/*.yaml')]"
```
- All manifests `yaml.safe_load` clean; drift `--check` in_sync; installed mode emits NO `deploy/` (byte-identical-when-absent, SOTTO).
- Gateway API objects validate against `gateway.networking.k8s.io`; ExternalSecret against `external-secrets.io`.
- StartDate: `deploy/` renders, operator runbook applies cleanly to a test EKS/GKE namespace.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Operator-bound values get baked (bucket-4 leak) | Placeholders via ConfigMap/`deploy:` bindings + M3 guard; never bake registry/host/account/secret |
| Gateway API version skew | Pin `v1` `HTTPRoute`; document min Gateway-API version; keep listener ref operator-owned |
| ESO not installed in cluster | M3 WARN + runbook prerequisite list (ESO, Gateway-API CRDs, collector, IdP) |
| Manifest layer drifts from app reality (port/health path) | Renderers read the SAME constants as health/main/settings; drift test cross-checks port + `/health` path |
| Scope creep into a deploy orchestrator | Render-only CLI; apply/build/push stay operator-run (documented) |

## 5. Out of scope (deferred / operator)
- App-exposed MCP surface (FR-CND-8) — later increment.
- Helm/kustomize templating (v1 = plain manifests; overlays = v2, OQ-5).
- Cluster provisioning, IdP/SecretStore/gateway install — operator.
- Mesh/mTLS (Ambient/ztunnel) — optional operator layer, not emitted.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

> **Triage summary (v1.1, 2026-06-20):** All 29 plan suggestions (R1–R5) ACCEPTED, folded into the
> §2A Milestone Deltas. Each S-item maps to the requirement FR it serves (Appendix A of the
> requirements doc holds the F-side). 0 rejected.

### Appendix A: Applied Suggestions

| ID | Suggestion | Milestone delta (§2A) | Date |
|----|------------|------------------------|------|
| R1-S1 | Fail-closed network rung (ClusterIP + NetworkPolicy / `trust_gateway`) | M1 `k8s-networkpolicy`, `k8s-service` ClusterIP; M3 ack guard | 2026-06-20 |
| R1-S2 | Doppler token bootstrap as ordered runbook step | M5 runbook + contract | 2026-06-20 |
| R1-S3 | M3 ERROR on dangling store + vendor allowlist lint | M3 guards | 2026-06-20 |
| R1-S4 | Concrete drift SoT for port/health/env | M0 `app_surfaces` constants | 2026-06-20 |
| R1-S5 | M5 cluster-smoke PASS predicate | M5 `cluster-smoke-spec.json` | 2026-06-20 |
| R1-S6 | OQ-9 → milestone (YAML default + opt-in tfvars) | M2 `--emit-tfvars-stub` | 2026-06-20 |
| R1-S7 | Secret classification single list | M1 ConfigMap/ExternalSecret split | 2026-06-20 |
| R1-S8 | Non-pullable image sentinel | M3 image guard | 2026-06-20 |
| R1-S9 | HTTPRoute `parentRef` from `deploy:` binding | M1 `k8s-httproute`; M0 block | 2026-06-20 |
| R2-S1 | Alembic migrate Job before readiness | M1 `k8s-job`; M5 ordering | 2026-06-20 |
| R2-S2 | Shared constants + PORT three-way | M0 `app_surfaces`; M1 renderers | 2026-06-20 |
| R2-S3 | FR-JWT-9 → coherence ERROR | M3 `deployed-decode-only-no-gateway-ack` | 2026-06-20 |
| R2-S4 | HTTPRoute-only; gateway stub opt-in | M1 scope; M0 `emit_gateway_stub` | 2026-06-20 |
| R2-S5 | Wireframe `deploy/` section | M2 wireframe | 2026-06-20 |
| R2-S6 | Unify entry point (scaffold emits deploy/) | M2 entry-point unification | 2026-06-20 |
| R2-S7 | ExternalSecret `refreshInterval` + restart | M1 `k8s-externalsecret` | 2026-06-20 |
| R2-S8 | infra-contract `schemaVersion` + JSON Schema | M1 `deploy-infra-contract` | 2026-06-20 |
| R2-S9 | `startupProbe` on `/health/live` | M1 `k8s-deployment` | 2026-06-20 |
| R2-S10 | Register `deploy/*.yaml` in drift ownership | M0 drift ownership | 2026-06-20 |
| R3-S1 | Hardened `securityContext` + non-root Dockerfile | M1 `k8s-deployment` + Dockerfile | 2026-06-20 |
| R3-S2 | Dedicated SA, no token automount | M1 `k8s-serviceaccount` | 2026-06-20 |
| R3-S3 | NetworkPolicy egress allowlist | M1 `k8s-networkpolicy` egress | 2026-06-20 |
| R3-S4 | CNI-enforcement prerequisite | M1 `deploy-infra-contract` | 2026-06-20 |
| R3-S5 | Shared labels; selector ⊆ pod labels | M1 deployment/service labels | 2026-06-20 |
| R3-S6 | Byte-stable YAML + render-twice test | M0 serialization; §3 | 2026-06-20 |
| R3-S7 | `terminationGracePeriodSeconds` + SIGTERM drain | M1 `k8s-deployment`; M5 | 2026-06-20 |
| R3-S8 | ConfigMap-checksum pod annotation [v1.1] | M1 `k8s-deployment` (phased) | 2026-06-20 |
| R4-S1 | stdout logging in deployed mode | M1 `render_logging` | 2026-06-20 |
| R4-S2 | HTTPRoute explicit `hostnames` | M1 `k8s-httproute` | 2026-06-20 |
| R4-S3 | PodDisruptionBudget | M1 `k8s-pdb` | 2026-06-20 |
| R4-S4 | Resource requests/limits defaults | M1 `k8s-deployment`; M0 block | 2026-06-20 |
| R4-S5 | ExternalSecret `creationPolicy: Owner` | M1 `k8s-externalsecret` | 2026-06-20 |
| R5-S1 | DNS-1123 name sanitizer | M0/M1 naming helper | 2026-06-20 |
| R5-S2 | `deploy/README.md` operator handoff | M1 `deploy-runbook` | 2026-06-20 |
| R5-S3 | Opt-in HPA | M1 `k8s-hpa` (opt-in) | 2026-06-20 |
| R5-S4 | Immutable image + `imagePullSecrets` | M0 image block; M3 guard | 2026-06-20 |
| R5-S5 | Downward-API + `OTEL_RESOURCE_ATTRIBUTES` | M1 `k8s-deployment` env | 2026-06-20 |
| R5-S6 | Explicit namespace binding + preflight | M0 `deploy.namespace`; README | 2026-06-20 |
| R5-S7 | DB connection budget | M1 contract; M3 advisory | 2026-06-20 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1–R5 plan suggestions accepted; R3-S8 phased to v1.1, R5-S3 HPA opt-in (not rejected) | 2026-06-20 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-20

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — weighted to sponsor focus (secrets bootstrap, JWT-behind-gateway footgun, vendor-neutrality boundary, bucket-1/4 line, determinism/drift, ops prereqs, pilot acceptance, OQ-9). Companion F-suggestions + focus-ask answers (incl. OQ-9 recommendation) are in the requirements file's Appendix C. Requirements coverage matrix is appended at the end of this plan.

##### Executive summary (top risks / gaps)

- **Highest risk: M1 `k8s-httproute` + decode-only JWT seam (FR-CND-6) has no fail-closed plan** — if the rendered Service/route is ever reachable without a gateway terminating auth, the app trusts any token. The plan needs a NetworkPolicy / internal-only Service rung. (R1-S1)
- **Doppler service-token bootstrap (M1/M5) is named but has no concrete operator runbook step** — the chicken-and-egg break is hand-waved; M5 runbook must seed it before `kubectl apply`. (R1-S2)
- **M3 coherence guard is too weak** — it WARNs on missing SecretStore binding; it should ERROR on secret keys with no store, and should assert the vendor-neutrality allowlist on the default tree. (R1-S3)
- **The §4 "manifest drifts from app reality" cross-check is asserted but not specified** — no concrete shared-constant source or test is named for port/`/health` path/env names. (R1-S4)
- **M5 pilot lacks a defined PASS predicate** — "smoke" is unscoped; the cluster-smoke rung needs a single documented acceptance gate. (R1-S5)
- **OQ-9 unresolved in the plan** — no milestone owns the tfvars-stub decision; recommend tool-neutral YAML default + opt-in stub (see requirements R1-F5). (R1-S6)
- **ConfigMap/Secret classification is implicit** — M1 `k8s-configmap` vs `k8s-externalsecret` split needs a declared secret-key list to avoid a credential landing in the ConfigMap. (R1-S7)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Security | critical | Add a fail-closed network rung to M1: emit an internal-only Service (ClusterIP) plus a NetworkPolicy that denies ingress except from the gateway namespace/selector, OR require a `deploy.trust_gateway` ack that M3 ERRORs without. Document that no internet-facing Service is emitted by default. | The decode-only JWT seam (FR-CND-6) is an auth bypass if the app is reachable without the gateway in front; the plan currently emits Deployment/Service/HTTPRoute with no guard against direct exposure. | M1 (new `k8s-networkpolicy` kind) + M3 guard | Apply default tree without a Gateway; confirm pod is not reachable from outside the gateway selector; M3 ERRORs if `trust_gateway` unacknowledged. |
| R1-S2 | Ops | high | M5 runbook must include the Doppler service-token bootstrap as an explicit ordered step BEFORE `kubectl apply` (seed via Terraform/cloud-secret-manager/sealed-secret), and the infra-contract consumer must verify the token exists. Today M1's `deploy-infra-contract` lists it only as a "prerequisite." | The chicken-and-egg (ESO needs the Doppler token to fetch secrets, but the token itself must arrive out-of-band) is the named focus risk; without a runbook step the first apply fails opaquely. | M5 runbook list + M1 `deploy-infra-contract` | Runbook step ordering test / dry-run; contract marks the token `operator-provided` and absence is detectable pre-apply. |
| R1-S3 | Security | high | Strengthen M3: change "WARN if ExternalSecret keys reference secrets with no SecretStore binding" to ERROR, and add a vendor-neutrality allowlist check — the default (non-opt-in) `deploy/` tree must contain only allowlisted `apiVersion`s; any vendor CRD (Doppler-operator `DopplerSecret`, Gloo, kagent/agentgateway) only under its opt-in flag. | A dangling ExternalSecret with no store is a deploy-time failure, not a warning; and the vendor-neutrality "clean line" (focus area 3) is only enforceable via an allowlist assertion, which M3 is the natural home for. | M3 (coherence + bucket guard) | Unit test: dangling-store app.yaml → coherence exit nonzero; default tree apiVersions ∈ allowlist; opt-in flags introduce CRDs only when set. |
| R1-S4 | Validation | high | Specify the §4 drift cross-check concretely: name the single source of truth the renderers read for port, `/health` + `/health/live` paths, and env-var names (e.g. the same constants `health_renderer.py`/`telemetry_renderer.py`/`settings` emit), and add a test that fails if a manifest probe path or container port diverges from that source. | §4 risk row asserts "renderers read the SAME constants" but neither the constant module nor the cross-check test is named; this is the determinism/drift focus area and the most likely silent breakage (probe points at a path the app no longer serves). | §3 Validation + §4 Risks row | Test mutates the app's health path constant and asserts the manifest renderer + drift `--check` catch the mismatch. |
| R1-S5 | Validation | medium | Define M5's cluster-smoke PASS predicate explicitly: which graded-ladder rungs are required (boot→health→smoke) and the single pass gate (e.g. readiness probe green AND one authenticated request through agentgateway returns 2xx). | "rollout → probe via agentgateway → smoke" is unscoped; FR-PILOT-1 acceptance needs a documented predicate or the pilot can be declared passing on any subset. | M5 + §3 Validation | Pilot record lists each required rung's result; PASS is one boolean predicate. |
| R1-S6 | Architecture | medium | Assign OQ-9 to a milestone: default M1/M2 output is tool-neutral YAML contract only; add optional `startd8 deploy k8s --emit-tfvars-stub` (inputs-only, byte-identical-when-absent per SOTTO); M5 documents the StackGen/Terraform hand-off rather than integrating it. | OQ-9 is the only open question and currently owned by no milestone; deferring the decision blocks the bucket-1/4 boundary from being implementable. Recommendation matches requirements R1-F5. | M1/M2 (flag) + M5 (hand-off doc) + resolve OQ-9 | Default render has no `.tf*`; with the flag, only variable declarations emitted; absence byte-identical. |
| R1-S7 | Data | medium | M1 must declare the secret-vs-non-secret env classification as a single explicit list so `k8s-configmap` and `k8s-externalsecret` partition deterministically; known-secret keys (provider API keys, `DATABASE_URL`) must never appear in the ConfigMap. | The split is implied across two renderers; a misclassification silently bakes a credential into a $0 ConfigMap (FR-CND-9 / FR-CND-5 leak). | M1 `k8s-configmap` / `k8s-externalsecret` | Test: secret-key allowlist never appears in `configmap.yaml`; classification is one shared list consumed by both renderers. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Add a risk row + mitigation for the `image:` placeholder: M1 says the image is "an operator-bound placeholder," but a placeholder that is a syntactically valid image ref (e.g. `REPLACE_ME:latest`) can be `kubectl apply`-ed and silently pull-fail or pull a squatted image. Use an obviously-invalid sentinel and have M3 ERROR if it survives to a non-render context. | An apply-able-but-wrong image placeholder is a classic deploy footgun and undermines "operator binds at deploy time"; the §4 risk table omits it. | §4 Risks + M3 guard | Test: rendered `image:` is a non-pullable sentinel; M3 flags an unbound image; runbook requires binding before apply. |
| R1-S9 | Interfaces | low | Clarify the M1 `k8s-httproute` ↔ operator `Gateway` contract: the plan emits an `HTTPRoute` referencing an operator-owned Gateway/listener, but does not state how the listener name/namespace/sectionName is supplied (a `deploy:` binding) vs hardcoded. | An HTTPRoute with a hardcoded `parentRef` is an operator-bound value baked in (FR-CND-9); the binding seam needs to be explicit at the interface level. | M1 `k8s-httproute` + `deploy:` block (M0) | Two app.yamls differing only in gateway listener ref produce HTTPRoutes differing only in `parentRef`; nothing else baked. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C had no prior suggestions.

#### Review Round R2 — composer-2.5 — 2026-06-20

- **Reviewer**: composer-2.5
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — second pass (go deeper, not wider). Focus on operational deploy-time failures R1 did not name, cross-artifact consistency (wireframe ↔ generate ↔ deploy), and second-order interactions with R1 suggestions. Companion F-suggestions in the requirements file's Appendix C. Requirements coverage matrix R2 appended at the end of this plan.

##### Executive summary (top risks / gaps)

- **Alembic migration gap (critical ops):** M1 emits Deployment only; `coherence.py` ERRORs on `deployed` without migrations, but nothing runs `alembic upgrade head` before readiness probes hit `/health` (`SELECT 1`) — first deploy will flap or fail. (R2-S1)
- **Health/port constants duplicated across four modules** — R1-S4 names a SoT but not that `/health` paths appear in `health_renderer.py`, `openapi_contract_renderer._health_routes()`, `test_emitter.py`, and `deploy_harness/server.py`; `PORT` diverges between Dockerfile (`8000` hardcoded) and `run.sh` (`${PORT:-8000}`). (R2-S2)
- **FR-CND-3 vs plan contradiction:** requirements say emit a "Gateway/listener stub"; plan says operator-owned Gateway only — unresolved ownership of Gateway objects. (R2-S4)
- **Wireframe does not surface `deploy/`** despite M2 claiming wireframe surfaces deploy artifacts — operators lack pre-generation visibility of operator-bound placeholders. (R2-S5)
- **Two generation entry points** (`generate scaffold` vs `startd8 deploy k8s`) risk duplicate drift surfaces. (R2-S6)
- **ESO secret rotation unaddressed** — no `refreshInterval` or pod-restart-on-rotation story. (R2-S7)
- **Auth-seam `VERIFIED_UPSTREAM=False` not wired into M3** — decode-only posture should ERROR in coherence when `deploy.trust_gateway` is absent (extends R1-S1). (R2-S3)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Ops | critical | Add M1 `k8s-job` → `deploy/migrate-job.yaml` (one-shot Alembic `upgrade head`) OR document init-container pattern in M5 runbook. M5 runbook ordering: apply migrate Job → wait complete → apply Deployment. | `evaluate_coherence` ERRORs on `deployed` + `migrations: false` (`coherence.py:69-74`); readiness probe runs `SELECT 1` on `/health` — empty schema fails before operator understands why. R1 did not name who runs migrations. | M1 (`k8s-job` kind) + M5 runbook | Integration test: Job completes; Deployment readiness passes only after schema at head. |
| R2-S2 | Validation | high | Extend R1-S4: extract shared `app_surfaces` constants (health paths, default port) consumed by k8s renderers and drift cross-check. Anchor on `openapi_contract_renderer._health_routes()` + Dockerfile/run.sh port (`renderers.py:118-119` vs `136`). Include `containerPort`, Service `targetPort`, and probe ports in the same source. | §4 asserts "renderers read the SAME constants" but paths are duplicated in four modules; `PORT` env override in `run.sh` can desync from probe `containerPort`. | §3 Validation + M1 renderers | Mutate shared constant → manifest drift `--check` fails; change `deploy.port` → containerPort + probes + Service align. |
| R2-S3 | Security | high | Wire auth-seam FR-JWT-9 into M3: when `deployed` + auth seam emitted + no `deploy.trust_gateway` ack (R1-S1), `evaluate_coherence` ERROR citing decode-only / `VERIFIED_UPSTREAM=False` posture — mirrors wireframe advisory in `wireframe/plan.py:_deployment_section`. | R1-S1 proposes NetworkPolicy but not coherence integration with the auth-seam trust model already specified in `AUTH_SEAM_JWT_REQUIREMENTS.md` FR-JWT-9. | M3 (extend `evaluate_coherence`) | deployed + auth, no `trust_gateway` → coherence exit nonzero with code `deployed-decode-only-no-gateway-ack`. |
| R2-S4 | Architecture | medium | Resolve Gateway stub contradiction: plan M1 SHALL emit **HTTPRoute only** in the default core; Gateway is an infra-contract prerequisite, not an emitted object. If a stub is ever needed, gate behind `deploy.emit_gateway_stub: true` (opt-in, off by default). Amend requirements FR-CND-3 in tandem (see R2-F2). | Requirements FR-CND-3 says "referenceable `Gateway`/listener stub"; plan M1 says "operator-owned `Gateway`", "never Gloo CRDs" — contradictory emission scope. | M1 scope note + FR-CND-3 cross-ref | Default `deploy/` tree has no `kind: Gateway`; lint passes R1-S3/F7 allowlist. |
| R2-S5 | Interfaces | medium | M2: add wireframe `deploy/` section (extend `wireframe/plan.py`) listing `deploy/*.yaml` output kinds + operator placeholders (`image`, `parentRef`, SecretStore) with advisory status — same pattern as `_scaffold_section`. | M2 says "Wireframe surfaces the deploy artifacts" but `wireframe/plan.py` has `_deployment_section` only; no `deploy/` claims. End-user quick win before cluster spend. | M2 + `wireframe/plan.py` | `startd8 wireframe` on `deployment.mode: deployed` lists deploy artifacts and unbound placeholders. |
| R2-S6 | Architecture | medium | Unify generation entry point: **`generate scaffold` emits `deploy/` when `deployment.mode: deployed`**; `startd8 deploy k8s` is alias + `--check` only. One drift surface via existing `ScaffoldFileProvider`. | M1 lives in `scaffold_codegen`; M2 adds separate CLI — two commands risk divergent ownership and skip-hook gaps. | M2 CLI design + M1 integration | One command regenerates Dockerfile + `deploy/`; `scaffold_in_sync` covers all owned kinds. |
| R2-S7 | Ops | medium | M1 `k8s-externalsecret`: emit `refreshInterval` (e.g. `1h`); infra-contract documents pod restart on secret rotation (Stakater reloader annotation or operator runbook step). | Rotated Doppler/cloud secrets won't reach running pods without refresh + restart; silent stale-credential failures post-deploy. | M1 `k8s-externalsecret` + `deploy-infra-contract` | ExternalSecret manifest includes `refreshInterval`; contract lists rotation/restart expectation. |
| R2-S8 | Architecture | medium | M1 `deploy-infra-contract`: add top-level `schemaVersion` + ship `infra-contract.schema.json` for consumer validation (supports OQ-9 YAML-first hand-off). | Machine-checkable contract (R1-F6) needs versioned evolution; StackGen/Terraform consumers need schema, not prose. | M1 `deploy-infra-contract` | Contract validates against JSON Schema in unit tests; version bump is explicit. |
| R2-S9 | Ops | low | M1 `k8s-deployment`: add `startupProbe` on `/health/live` with generous `failureThreshold` so DB warmup + migration window don't kill the pod before readiness. | Readiness hits DB-dependent `/health`; cold start without startupProbe causes rollout flakes even with R2-S1 migrate Job if ordering is loose. | M1 `k8s-deployment` | Rendered Deployment includes startupProbe; paths match R2-S2 constants. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S10 | Validation | medium | M0 task: extend `is_owned_scaffold_file` / `SCAFFOLD_RENDERERS` in `scaffold_codegen/drift.py` for `deploy/*.yaml` GENERATED headers — otherwise prime-contractor skip-hook and `generate scaffold --check` won't cover k8s output. | Plan reuses `ScaffoldFileProvider` but new kinds must register in drift ownership or artifacts drift undetected. | M0 + `drift.py` | `scaffold_in_sync` true/false for `deploy/deployment.yaml`; owned-file detection recognizes k8s header kinds. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1 suggestions):

- **R1-S1 / R1-F3** — fail-closed network posture for decode-only JWT; highest severity; R2-S3 extends with coherence wiring.
- **R1-S4** — concrete drift cross-check; R2-S2 extends with shared constants module and PORT alignment.
- **R1-S7 / R1-F8** — secret vs non-secret classification list; prevents ConfigMap credential leak.
- **R1-S2 / R1-F1** — Doppler bootstrap runbook ordering + acceptance criteria.
- **R1-S6 / R1-F5** — OQ-9 YAML default + opt-in tfvars stub; R2-S8 adds schema versioning.
- **R1-S8** — non-pullable `image:` sentinel.
- **R1-S3 / R1-F7** — vendor-neutrality allowlist in M3.

**Disagreements:** none — all R1 items remain valid; R2 extends rather than contradicts.

#### Review Round R3 — claude-opus-4-8 — 2026-06-20

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — third pass. R1/R2 covered the auth/secrets/drift/pilot surface; R3 goes deeper into **pod-level hardening, NetworkPolicy egress (second-order with R1-S1), K8s label coupling, and YAML serialization determinism** — all unaddressed in A/B/C. Companion F-suggestions in the requirements file's Appendix C; Requirements Coverage Matrix R3 at end of this plan.

##### Executive summary (top risks / gaps)

- **Pods run as root with no securityContext** — the Dockerfile (`renderers.py:113-119`) has no `USER` directive and M1's `k8s-deployment` declares no `securityContext`; the manifests will be **rejected by any namespace enforcing the restricted PodSecurity Standard**, and run privileged where they aren't. R1/R2 never touched container hardening. (R3-S1)
- **R1-S1's deny-ingress NetworkPolicy will break the app unless egress is explicit** — a fail-closed policy that omits egress to the DB, OTLP collector, Doppler/secret-backend API, LLM provider APIs, and DNS silently kills the running app. Second-order interaction R1 did not analyze. (R3-S3)
- **R1-S1's fail-closed guarantee is false on CNIs that ignore NetworkPolicy** (e.g. default flannel) — the infra-contract must list "CNI with NetworkPolicy enforcement" as a prerequisite or the security posture is theater. (R3-S4)
- **Service selector ↔ Deployment pod-label coupling is unspecified** — a mismatch makes the Service route to zero endpoints silently; no recommended `app.kubernetes.io/*` labels declared. (R3-S5)
- **YAML serialization determinism is assumed, not specified** — $0 drift-checked artifacts require byte-stable output (sorted keys, no timestamps, stable list order); nothing names the serializer discipline. (R3-S6)
- **No graceful-shutdown story** — no `terminationGracePeriodSeconds` / uvicorn SIGTERM drain; rolling updates will drop in-flight requests. (R3-S7)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Security | high | M1 `k8s-deployment` SHALL emit a hardened `securityContext` (`runAsNonRoot: true`, `runAsUser` non-zero, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`); the Dockerfile SHALL add a non-root `USER`. Provide a writable `emptyDir` for any runtime temp paths. | Dockerfile (`renderers.py:113-119`) has no `USER` (runs as root); Deployment has no `securityContext`. Restricted PodSecurity Standard namespaces reject this manifest outright; otherwise it runs privileged. | M1 `k8s-deployment` + `render_dockerfile` | Apply default tree to a `pod-security.kubernetes.io/enforce: restricted` namespace → admits cleanly; container runs as non-root. |
| R3-S2 | Security | medium | M1 SHALL emit a dedicated `ServiceAccount` with `automountServiceAccountToken: false` (the generated app never calls the K8s API), and reference it from the Deployment. | The default ServiceAccount auto-mounts a token into every pod — needless K8s-API credential exposure for an app that doesn't use it. | M1 (new `k8s-serviceaccount` kind) + `k8s-deployment` | Rendered pod has no projected SA token; Deployment references the dedicated SA. |
| R3-S3 | Ops | high | If M1 adopts R1-S1's NetworkPolicy, it SHALL emit a paired **egress** allowlist: DB (from `DATABASE_URL` host/port), OTLP collector, secret-backend API (Doppler/cloud SM), LLM provider APIs, and DNS (`kube-dns` UDP/TCP 53). A deny-all-ingress NetworkPolicy in many CNIs flips the pod to deny-all-egress too. | R1-S1 analyzes ingress only; a fail-closed policy without egress allows is an outage, not security. The egress targets are operator-bound (from the infra-contract), not baked. | M1 `k8s-networkpolicy` (egress section) + `deploy-infra-contract` | Apply policy; confirm app reaches DB/OTLP/secret API/provider; remove an egress rule → that dependency fails (proves enforcement). |
| R3-S4 | Ops | high | `deploy-infra-contract` SHALL list **"CNI with NetworkPolicy enforcement"** as an operator prerequisite, because R1-S1's fail-closed posture is silently a no-op on CNIs that ignore NetworkPolicy (e.g. default flannel). | The entire decode-only-JWT fail-closed argument (R1-S1/F3) rests on the NetworkPolicy actually being enforced; that's a cluster capability, not a manifest guarantee. | `deploy-infra-contract` prerequisite list (extends R1-F6) | Contract entry `{name: cni-networkpolicy, status: operator-provided}`; runbook notes the verification step. |
| R3-S5 | Interfaces | high | M1 SHALL declare a single label set (`app.kubernetes.io/name`, `instance`, `version`, `part-of`, `managed-by`) consumed by both the Deployment pod template and the Service `selector`, so they cannot diverge; Service `selector` == pod `labels` by construction. | A Service whose selector doesn't match the Deployment's pod labels routes to zero endpoints and fails silently — a classic hand-wired-manifest bug the generator should make impossible. | M1 `k8s-deployment` / `k8s-service` (shared label source) | Test: Service selector keys/values ⊆ Deployment pod-template labels; HTTPRoute backendRef resolves to a ready endpoint. |
| R3-S6 | Validation | medium | §3 SHALL specify byte-stable YAML serialization: sorted/declared key order, no timestamps or run-dependent values, deterministic list ordering, fixed indentation. Add a test that renders twice and asserts byte-identical output. | FR-CND-9 makes these artifacts `$0`/drift-checked; non-deterministic dict/key ordering would make `--check` flap. R1-S4 covers app-reality drift, not serialization stability. | §3 Validation + M1 renderer discipline | Render `deploy/` twice in one process and across a fresh import; assert byte-identical; drift `--check` stable. |
| R3-S7 | Ops | medium | M1 `k8s-deployment` SHALL set `terminationGracePeriodSeconds` and the runbook/seam SHALL document uvicorn SIGTERM draining (readiness flips to 503 on shutdown so the Service removes the pod before kill). | Without graceful shutdown, every rolling update / scale-down drops in-flight requests — a zero-downtime-deploy footgun not covered by R2-S9 startupProbe (which is startup only). | M1 `k8s-deployment` + M5 runbook | Rolling update under load drops zero requests; SIGTERM → readiness 503 → endpoint removed → drain → exit. |
| R3-S8 | Ops | low | M1 SHALL annotate the Deployment pod template with a checksum of the rendered ConfigMap, so a config change rolls the pods (parallels R2-S7's secret-rotation restart for non-secret config). | A ConfigMap edit alone does not restart pods; env changes silently don't take effect until an unrelated rollout. | M1 `k8s-deployment` (annotation) | Change a ConfigMap value → pod-template checksum annotation changes → `kubectl apply` triggers a rollout. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2 suggestions this reviewer agrees with):

- **R1-S1 / R1-F3** — fail-closed network posture; R3-S3 (egress) and R3-S4 (CNI prerequisite) are the load-bearing complements without which R1-S1 is either an outage or a no-op.
- **R2-S1 / R2-F1** — Alembic migrate Job; pairs with R3-S7 graceful shutdown for safe rollouts.
- **R2-S2 / R2-F3** — shared constants + PORT three-way; R3-S5 extends the same "single source" discipline to labels.
- **R1-S3 / R1-F7** — vendor-neutrality allowlist; R3-S1's securityContext keys stay within `apps/v1`/`v1` (no CRD), preserving the allowlist.
- **R2-S8** — infra-contract schemaVersion; R3-S4's CNI prerequisite is a new contract field that benefits from versioning.

**Disagreements:** none — R3 is additive and second-order to R1/R2.

#### Review Round R4 — gemini-3.1-pro — 2026-06-20

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — fourth pass. Focus on critical operational gaps in logging, routing conflicts on shared gateways, resource bounds, and disruption budgets. Companion F-suggestions in the requirements file's Appendix C; Requirements Coverage Matrix R4 at end of this plan.

##### Executive summary (top risks / gaps)

- **Logs are written to a local file, invisible to `kubectl logs`** — `render_logging` configures a `RotatingFileHandler` to `./data/logs/app.log`. In a container, this fills the ephemeral disk and hides logs from aggregators (Promtail/Fluentbit). (R4-S1)
- **`HTTPRoute` without `hostnames` will conflict on a shared Gateway** — if the route defaults to `*`, it risks hijacking traffic or conflicting with other apps. (R4-S2)
- **No PodDisruptionBudget (PDB)** — node drains or cluster upgrades can evict all replicas simultaneously, causing an outage. (R4-S3)
- **No resource requests/limits defined** — unbounded pods risk noisy neighbor issues or unpredictable OOMKills. (R4-S4)
- **Orphaned K8s Secrets** — `ExternalSecret` needs `creationPolicy: Owner` to ensure the generated K8s Secret is garbage collected when the `ExternalSecret` is deleted. (R4-S5)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Ops | critical | `render_logging` MUST emit a `StreamHandler(sys.stdout)` instead of `RotatingFileHandler` when `deployment.mode == "deployed"`. | In a cloud-native environment, logs written to a local file are ephemeral, fill up the container disk, and are invisible to `kubectl logs` and log aggregators. | M1 (update `render_logging` in `scaffold_codegen/renderers.py`) | `generate scaffold` in `deployed` mode produces `logging_config.py` that logs to stdout. |
| R4-S2 | Interfaces | high | M1 `k8s-httproute` SHALL require a `hostnames` field bound from `deploy.hostnames` in `app.yaml`. | An `HTTPRoute` without `hostnames` defaults to `*`, which will conflict with other routes on a shared operator-owned Gateway. | M1 `k8s-httproute` | `deploy/httproute.yaml` includes `hostnames` matching the `app.yaml` binding. |
| R4-S3 | Ops | medium | M1 SHALL emit a `PodDisruptionBudget` (PDB) with `minAvailable: 1` (or `maxUnavailable: 1` if replicas > 1) to protect the app during node drains. | R2 identified PDB as a "Quick win" but didn't formalize it. Without a PDB, cluster upgrades or node drains can evict all replicas simultaneously, causing an outage. | M1 (new `k8s-pdb` kind) | `deploy/pdb.yaml` is emitted and references the same pod selector as the Service. |
| R4-S4 | Ops | medium | M1 `k8s-deployment` SHALL enforce explicit resource requests and limits, with sensible defaults (e.g., CPU 100m/500m, Memory 128Mi/256Mi) in the `deploy:` block. | Unbounded pods can consume all node resources (noisy neighbor) or be unpredictably OOMKilled. | M1 `k8s-deployment` + M0 `deploy:` block | `deploy/deployment.yaml` contains `resources.requests` and `resources.limits`. |
| R4-S5 | Security | low | M1 `k8s-externalsecret` SHALL set `target.creationPolicy: Owner`. | Ensures the generated Kubernetes `Secret` is garbage collected when the `ExternalSecret` is deleted, preventing orphaned credentials in the cluster. | M1 `k8s-externalsecret` | `deploy/externalsecret.yaml` includes `creationPolicy: Owner`. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2/R3 suggestions this reviewer agrees with):

- **R3-S1 / R3-F1** — PodSecurity Standard hardening; essential for modern K8s environments.
- **R3-S3 / R3-F2** — NetworkPolicy egress allowlist; critical to prevent self-inflicted outages.
- **R3-S5 / R3-F4** — Service selector ↔ Deployment label coupling; prevents silent routing failures.
- **R3-S7** — Graceful shutdown; essential for zero-downtime deployments.

**Disagreements:** none — R4 is additive and addresses operational gaps missed in prior rounds.

#### Review Round R5 — gpt-5.5 — 2026-06-20

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-20 (UTC)
- **Scope**: Plan quality (S-prefix) — fifth pass. Prior rounds covered auth, secrets, pod hardening, logging, resource bounds, and disruption basics; R5 focuses on **operator handoff UX, Kubernetes naming/namespace footguns, autoscaling, immutable image binding, OTel Kubernetes attribution, and DB connection budgeting**.

##### Executive summary (top risks / gaps)

- **Kubernetes resource names are not specified as DNS-1123-safe** — `app.name` can legally contain characters/lengths Kubernetes rejects, so an otherwise valid app can render manifests that fail at `kubectl apply`. (R5-S1)
- **The operator handoff is scattered across prose and `infra-contract.yaml`** — v1 should emit a short `deploy/README.md` with apply order, placeholder checklist, preflight commands, and rollback instructions. This is low effort and high end-user value. (R5-S2)
- **No autoscaling option exists** despite replicas/resources being in `deploy:` — after R4-S4 resource requests, an opt-in HPA is a small increment that turns static replicas into production-capable scaling. (R5-S3)
- **Image binding lacks immutability and pull-secret semantics** — R1-S8 catches unbound placeholder images, but not mutable tags, digest pins, or private-registry credentials. (R5-S4)
- **OTel resource attributes lack Kubernetes identity** — `telemetry_renderer.py` emits only `service.name` and `deployment.environment`; traces/logs will be harder to correlate to namespace/pod/node in Grafana/Tempo. (R5-S5)
- **Namespace safety is implicit** — applying manifests into the wrong current `kubectl` namespace is a common operator failure mode. (R5-S6)
- **Replica count has no database connection budget guard** — scaling pods can exhaust Postgres connection limits unless the infra-contract budgets connections per replica. (R5-S7)

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Validation | high | M0/M1 SHALL define a deterministic DNS-1123 resource-name sanitizer for all K8s object names derived from `app.name`: lowercase, `a-z0-9-`, max 63 chars, trim leading/trailing hyphens, and append a short stable hash on truncation/collision. | `app.yaml` names can include underscores, uppercase, spaces, or long strings that Kubernetes rejects. A generated app should not make the operator discover this only at `kubectl apply`. | M0 `deploy:` model + M1 shared naming helper | Unit tests: `"Start Date SDK!!!"` and a 100-char name render valid, stable names; two colliding truncations get different hash suffixes. |
| R5-S2 | Ops | high | M1 SHALL emit `deploy/README.md` (or `deploy/RUNBOOK.md`) as an operator handoff pack: apply order (namespace/prereqs → secrets/token → migration Job → app manifests), placeholder checklist, preflight commands, smoke command, rollback command, and explicit "SDK does not run kubectl/build/push" boundary. | The infra-contract is machine-readable but not enough for a human operator. R1/R2 mention runbooks mostly for the pilot; each generated deploy tree should carry a copy-pasteable handoff. | M1 new `deploy-runbook` output kind + M5 pilot reuse | Golden test for README sections; StartDate pilot uses only generated README plus operator values to deploy. |
| R5-S3 | Ops | medium | Add opt-in `k8s-hpa` output: `deploy/autoscaling.yaml` using `autoscaling/v2`, `minReplicas`, `maxReplicas`, and CPU/memory targets from `deploy.autoscaling`; list `metrics-server` as an infra-contract prerequisite when enabled. | M0 already plans replicas and R4-S4 resource requests/limits; HPA is the next low-hanging production capability and should stay opt-in to preserve simple defaults. | M1 optional `k8s-hpa` + M0 `deploy.autoscaling` | With autoscaling absent, no HPA emitted; when enabled, HPA references the Deployment and `infra-contract.yaml` lists metrics-server. |
| R5-S4 | Security | high | Extend image binding: require immutable image references for deployable artifacts (`@sha256:` digest preferred, or tag plus explicit `allowMutableTag: true` ack), and support `imagePullSecrets` as an operator-bound `deploy.registry.pullSecretRef`. | R1-S8 catches an unbound placeholder but not mutable `:latest` or private registries. Mutable tags undermine reproducibility; missing pull secret causes `ImagePullBackOff` only after apply. | M0 `deploy.image` block + M3 guard + M1 Deployment | `:latest` without ack → coherence ERROR; digest image passes; private registry fixture renders `imagePullSecrets`. |
| R5-S5 | Ops | medium | M1 `k8s-deployment` SHALL add Downward API env vars (`POD_NAME`, `POD_NAMESPACE`, `NODE_NAME`) and set `OTEL_RESOURCE_ATTRIBUTES` with `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name`, `service.name`, `service.version`, and `deployment.environment`. | `telemetry_renderer.py` currently creates OTel resources with only `service.name` and `deployment.environment`, which weakens trace/log correlation once multiple generated apps run in one cluster. | M1 `k8s-configmap`/Deployment env + FR-CND-4 validation | Rendered Deployment includes Downward API env; a pilot trace contains namespace/pod attributes in Tempo. |
| R5-S6 | Ops | medium | M1 SHALL make namespace binding explicit: either all namespaced manifests include `metadata.namespace: {{deploy.namespace}}` from the `deploy:` block, or the generated README/preflight fails if `kubectl config view --minify` namespace does not match the infra-contract namespace. | Applying to the wrong current namespace is a common operator footgun; FR-CND-11 names namespace as a prereq but the plan does not say how rendered manifests prevent default-namespace drift. | M0 `deploy.namespace`, M1 manifests, `deploy/README.md` | Changing `deploy.namespace` updates every namespaced object; README preflight includes namespace check. |
| R5-S7 | Data | medium | `deploy-infra-contract` SHALL include a database connection budget: `{replicas, per_pod_pool_size, max_expected_connections}` and a warning/error when the declared replicas can exceed the operator-provided DB connection cap. | Scaling replicas without a DB connection budget can exhaust Postgres connections; this is a cross-layer operational failure not caught by health probes. | M1 `deploy-infra-contract` + M3 coherence advisory | Fixture with replicas=10 and DB cap=20 warns/errors when per-pod pool would exceed cap. |

##### Endorsements & Disagreements

**Endorsements** (prior untriaged R1/R2/R3/R4 suggestions this reviewer agrees with):

- **R2-S5 / R2-F4** — wireframe and cluster-smoke artifacts; R5-S2 complements them with a human operator handoff.
- **R4-S4 / R4-F4** — resource requests/limits; R5-S3 depends on this for HPA correctness.
- **R1-S8** — non-pullable image sentinel; R5-S4 extends the same image-binding guard to digest immutability and pull secrets.
- **R2-S8** — infra-contract schema version; R5-S6/R5-S7 add fields that need versioned contract evolution.
- **R4-S1** — stdout logging; R5-S5 improves the telemetry side of the same observability story.

**Disagreements:** none — R5 is additive and focuses on operator usability plus scale-time failures.

---

## Requirements Coverage Matrix — R1

Analysis only (informs orchestrator triage). Maps each requirement to the plan milestone(s) that address it. Coverage: **Covered** / **Partial** / **Gap**.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s Deployment+Service, ConfigMap/Secret) | M0 (`deploy:` block), M1 (`k8s-deployment`, `k8s-service`, `k8s-configmap`, `k8s-externalsecret`) | Partial | Secret-vs-non-secret env classification rule is implicit — see R1-S7 / R1-F8. |
| FR-CND-2 (health probes wired to existing paths) | M1 (`k8s-deployment` liveness `/health/live` + readiness `/health`) | Covered | Drift cross-check against the app's actual path is asserted but unspecified — see R1-S4. |
| FR-CND-3 (Gateway API HTTPRoute, vendor-neutral) | M1 (`k8s-httproute`, `gateway.networking.k8s.io/v1`) | Partial | Operator `Gateway`/listener `parentRef` binding seam not specified — see R1-S9; vendor-neutrality allowlist not enforced — see R1-S3 / R1-F7. |
| FR-CND-4 (OTel → cluster collector, config-only) | M1 (`k8s-configmap` OTLP env) | Partial | Contract surfaces only "endpoint," not protocol/port — see R1-F6. |
| FR-CND-5 (Secrets via ESO, Doppler default) | M1 (`k8s-externalsecret`, `deploy.secrets.backend`) | Partial | Doppler project/config could leak into the emitted artifact (FR-CND-9) — see R1-F2; service-token bootstrap under-specified — see R1-S2 / R1-F1. |
| FR-CND-6 (gateway-ready decode-only identity) | M1 (route/config assumes upstream verify) | Gap | No fail-closed posture for direct (non-gateway) exposure — the critical finding, see R1-S1 / R1-F3. |
| FR-CND-7 (optional agentgateway/kagent, opt-in) | M4 (`deploy.agentgateway` flag) | Covered | Ensure CRDs gated behind the flag are caught by the allowlist check — see R1-S3 / R1-F7. |
| FR-CND-8 (app-exposed MCP) | (deferred — §5 out of scope) | Covered | Explicitly deferred; no plan obligation in v1. |
| FR-CND-9 (determinism + bucket line, no baked operator values) | M3 (bucket guard), §4 risks | Partial | `image:` placeholder footgun (R1-S8); project/config leak (R1-F2); enforcement is prose, not an allowlist test (R1-S3). |
| FR-CND-10 (EKS/GKE no-fork) | §1 discovery, M1 (one artifact set) | Covered | Confirmed structural; differences are operator bindings. |
| FR-CND-11 (infra-needs contract / IaC seam) | M1 (`deploy-infra-contract`) | Partial | Prereq fields not exhaustive/machine-checkable (R1-F6); OQ-9 tfvars-stub decision unassigned (R1-S6 / R1-F5). |
| FR-PILOT-1 (StartDate pilot acceptance) | M5 (runbook + cluster-smoke rung) | Partial | No defined required rungs / PASS predicate — see R1-S5 / R1-F4. |
| OQ-9 (open: tfvars stub vs YAML-only) | (unassigned) | Gap | Recommend tool-neutral YAML default + opt-in `--emit-tfvars-stub`; document hand-off, don't validate against StackGen in pilot — see R1-S6 / R1-F5. |

---

## Requirements Coverage Matrix — R2

Analysis only (informs orchestrator triage). Second-pass gaps building on R1.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s workload manifests) | M0, M1 | Partial | R1-S7 secret split; **R2-S1 migrate Job missing**; R2-S9 startupProbe. |
| FR-CND-2 (health probes) | M1 | Partial | R1-S4 drift SoT; **R2-S2 extends** with shared constants + PORT three-way alignment. |
| FR-CND-3 (Gateway API HTTPRoute) | M1 | Partial | R1-S9 parentRef binding; **R2-S4 Gateway stub contradiction** — default emits HTTPRoute only. |
| FR-CND-4 (OTel → collector) | M1 | Partial | R1-F6 protocol/port; **R2-F6** OTLP `/v1/traces` suffix semantics (`telemetry_renderer.py`). |
| FR-CND-5 (ESO / Doppler) | M1 | Partial | R1 bootstrap + leak paths; **R2-S7** refreshInterval + rotation restart story. |
| FR-CND-6 (decode-only identity) | M1, M3 | Gap | R1-S1 NetworkPolicy; **R2-S3** coherence ↔ FR-JWT-9 `VERIFIED_UPSTREAM`. |
| FR-CND-7 (opt-in agentgateway) | M4 | Covered | R1-S3 allowlist catches opt-in CRDs. |
| FR-CND-8 (app MCP) | (deferred) | Covered | No v1 obligation. |
| FR-CND-9 (determinism / bucket line) | M3 | Partial | R1 enforcement items; **R2-S6** single entry point reduces drift surface; **R2-S10** drift ownership registration. |
| FR-CND-10 (EKS/GKE no-fork) | M1 | Covered | Unchanged from R1. |
| FR-CND-11 (infra contract) | M1 | Partial | R1-F6 prereq fields; **R2-S8** schemaVersion + JSON Schema; **R2-S7** rotation in contract. |
| FR-PILOT-1 (StartDate pilot) | M5 | Partial | R1-S5 PASS predicate; **R2-F4** machine-readable `cluster-smoke-spec.json`. |
| OQ-9 | M1/M2 | Partial | R1-S6 resolution; R2-S8 schema supports YAML-first consumer hand-off. |

---

## Requirements Coverage Matrix — R3

Analysis only (informs orchestrator triage). Third-pass gaps — pod hardening, NetworkPolicy egress, label coupling, serialization determinism — orthogonal to R1/R2.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s workload manifests) | M0, M1 | Partial | **R3-S1 securityContext / non-root**, **R3-S2 ServiceAccount**, **R3-S5 Service↔pod label coupling**, **R3-S8 ConfigMap checksum** all unaddressed by R1/R2. |
| FR-CND-3 (Gateway API HTTPRoute) | M1 | Partial | R2-S4 Gateway ownership; **R3-F6** — HTTPRoute must not publicly expose DB-touching `/health`. |
| FR-CND-6 (decode-only identity) | M1, M3 | Gap | R1-S1 ingress + R2-S3 coherence; **R3-S3 egress** + **R3-S4 CNI enforcement** make the fail-closed posture real rather than nominal. |
| FR-CND-9 (determinism / bucket line) | M3, §4 | Partial | R1/R2 enforcement items; **R3-S6 byte-stable YAML serialization** is a precondition for `--check` not flapping. |
| FR-CND-11 (infra contract) | M1 | Partial | R1-F6 + R2-S8; **R3-S4** adds CNI-NetworkPolicy-enforcement; **R3-S3** egress targets are operator-bound contract fields. |
| (cross-cutting) Rollout safety | M1, M5 | Gap | **R3-S7 graceful shutdown** (terminationGracePeriod + SIGTERM drain) — neither R1 nor R2 covered zero-downtime rollout. |
| (cross-cutting) PodSecurity admission | M1, M3 | Gap | **R3-S1/F1** — restricted PodSecurity Standard namespaces reject the current (root, no securityContext) manifest. |

---

## Requirements Coverage Matrix — R4

Analysis only (informs orchestrator triage). Fourth-pass gaps — logging, routing conflicts, resource bounds, disruption budgets.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s workload manifests) | M0, M1 | Partial | **R4-S1 stdout logging**, **R4-S4 resource requests/limits**, **R4-S3 PodDisruptionBudget** all unaddressed by prior rounds. |
| FR-CND-3 (Gateway API HTTPRoute) | M1 | Partial | **R4-S2 hostnames binding** missing; defaulting to `*` risks conflicts. |
| FR-CND-5 (ESO / Doppler) | M1 | Partial | **R4-S5 creationPolicy: Owner** missing; risks orphaned secrets. |

---

## Requirements Coverage Matrix — R5

Analysis only (informs orchestrator triage). Fifth-pass gaps — operator handoff UX, naming/namespace safety, autoscaling, image immutability, OTel attribution, and DB connection budgeting.

| Requirement | Plan milestone(s) | Coverage | Gap / note |
| ---- | ---- | ---- | ---- |
| FR-CND-1 (K8s workload manifests) | M0, M1 | Partial | **R5-S1 DNS-1123 naming**, **R5-S3 opt-in HPA**, **R5-S4 immutable image/pull secret**, and **R5-S6 namespace binding** are not covered by R1-R4. |
| FR-CND-3 (Gateway API HTTPRoute) | M1 | Partial | R4-S2 hostnames; **R5-S6 namespace safety** prevents apply-to-default-namespace mistakes for all namespaced objects. |
| FR-CND-4 (OTel → collector) | M1 | Partial | R2-S6 endpoint semantics; **R5-S5 Kubernetes OTel resource attributes** are still missing. |
| FR-CND-9 (determinism / bucket line) | M0, M3 | Partial | R3-S6 serialization; **R5-S1 stable name sanitization** and **R5-S4 immutable image policy** protect determinism at apply/runtime. |
| FR-CND-11 (infra contract) | M1 | Partial | R1/R2/R3 prereqs; **R5-S3 metrics-server**, **R5-S6 namespace**, and **R5-S7 DB connection budget** add missing operator-facing contract fields. |
| FR-PILOT-1 (StartDate pilot) | M5 | Partial | R2-F4 cluster-smoke spec; **R5-S2 generated deploy README** gives the operator a copy-pasteable handoff for the pilot and future apps. |
