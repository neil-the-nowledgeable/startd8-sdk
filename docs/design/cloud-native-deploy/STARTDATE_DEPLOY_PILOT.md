# StartDate Deployment Pilot (D) — Plan, Runbook & Acceptance

**Version:** 0.1
**Date:** 2026-06-21
**Status:** Ready to execute (capability complete; pilot is validation + operator hand-off)
**Owner:** StartD8 SDK / StartDate (`strtd8`)
**Validates:** `cloud-native-deploy` FR-PILOT-1, `deploy-environments` FR-ENV-10, the cap-dev-pipe
deploy-coherence gate (REQ-CDP-DEPLOY-*), and `local-deploy-harness` (boot ladder).

---

## 1. Purpose

Prove the **deployment configuration capability** end-to-end on the real StartDate app: from one
`app.yaml` declaration, the `$0` deterministic cascade emits the app + `deploy/` base + per-env
kustomize overlays + infra-contract; the coherence gates fail closed without a gateway/secret-scope
ack; cap-dev-pipe enforces them; the operator binds + applies per environment. This is the
acceptance surface for everything built this cycle — **nothing new is generated here; D exercises it.**

What D establishes:
- A generated deployed app is **cloud-deployable to EKS/GKE behind agentgateway** with no hand-written manifests.
- **dev/test/prod** come from one base via overlays, differing only in declared values.
- The fail-closed gates (decode-only-no-gateway, secret-scope) actually block a misconfigured deploy.
- The infra-needs contract is a sufficient hand-off to the provisioning/orchestration layers.

---

## 2. Scope — the matrix

| Axis | Values exercised |
|------|------------------|
| **Mode** | `installed` (baseline, byte-identical-when-absent check) · `deployed` (the pilot) |
| **Environment** | `dev` · `test` · `prod` (one base, three overlays) |
| **Cloud** | one of EKS *or* GKE (same artifacts; operator bindings differ) |
| **Secrets** | Doppler (`eso-doppler`) — config per env (dev→`dev`, test→`tst`, prod→`prd`) |
| **Gateway** | agentgateway in front (`deploy.trust_gateway: true`) |

**Non-goals (inherited):** D does not provision the cluster (Terraform/StackGen), run the deploy
pipeline (Kestra/Argo/CI), or author StartDate's real content (bucket 4). The SDK render is `$0` and
render-only; `kubectl apply -k` is the operator's step.

---

## 3. Prerequisites (clear before executing)

**SDK / pipeline state**
- [ ] Primary SDK checkout synced to `origin/main` (currently diverged + dirty — commit/stash the
      bias-audit oracle work first, then `git pull --ff-only origin main`). The cap-dev-pipe gate
      reads `SDK_ROOT=~/Documents/dev/startd8-sdk`, so the deploy-coherence check script must be
      present there. *(Until then, run with `SDK_ROOT` pointed at an up-to-date checkout.)*
- [ ] Pre-existing broken goldens on `origin/main` regenerated or quarantined (wireframe
      `test_plan.py` ×18, `test_deployment_section.py` ×3, openapi golden ×2) so the pilot run isn't
      noise-masked. These are unrelated to the deploy capability.
- [ ] Context committed (`CLAUDE.md` Two-Gen-Paths + capability-index v1.7.0) — optional, hygiene.

**Cluster (operator-provided, from `deploy/infra-contract.yaml`)**
- [ ] EKS or GKE cluster + a target namespace allowing the **restricted** PodSecurity Standard.
- [ ] **CNI with NetworkPolicy enforcement** (else the fail-closed reachability guard is a no-op).
- [ ] Gateway-API CRDs (≥ v1) + a Gateway/listener; **agentgateway** as the listener that verifies JWTs.
- [ ] **External Secrets Operator** + a Doppler `SecretStore` per env; the Doppler **service token**
      seeded once (the chicken-and-egg bootstrap — via Terraform/cloud-secret-manager/sealed-secret).
- [ ] In-cluster **OTLP collector** endpoint.
- [ ] Container registry (ECR / Artifact Registry) + image pull secret if private.
- [ ] `kubectl ≥ 1.14` (in-tree kustomize via `apply -k`).

---

## 4. Authoring inputs (the only human step on the SDK side)

StartDate's `app.yaml` declares the posture (real 15-model `schema.prisma` already exists):

```yaml
app:
  name: startdate
deployment:
  mode: deployed
  tenant: { model: User, owner_field: ownerId }   # if multi-tenant
persistence:
  path: postgresql://...    # operator binds DATABASE_URL at deploy
migrations: { enabled: true }
telemetry: { enabled: true }
deploy:
  trust_gateway: true       # agentgateway verifies JWTs (clears FR-CND-6 fail-closed)
  target_cloud: gke         # or eks
  secrets: { backend: eso-doppler }
  environments:
    dev:  { secrets_config: dev, replicas: 1, otlp_endpoint: http://otel-collector.observability:4318 }
    test: { secrets_config: tst, replicas: 1 }
    prod: { secrets_config: prd, replicas: 3, resources: { limits: { cpu: "1", memory: 512Mi } },
            autoscaling: { min: 3, max: 10, cpu: 70 }, hostnames: [app.startdate.example] }
```

Note: every env pins `secrets_config` → no `env-inconsistent-secrets-scope` WARN (M3).

---

## 5. Runbook (the pilot steps)

1. **Render ($0, SDK):** `startd8 generate backend|scaffold|views` → emits `app/`, `deploy/` base
   tree, `deploy/overlays/{dev,test,prod}/`, `deploy/infra-contract.yaml`. No LLM, no `kubectl`.
2. **$0 deployability gate (CI):** `cd .cap-dev-pipe && ./run-cap-delivery.sh --stop-after export`
   → the deploy-coherence gate runs (no LLM/prime spend). A missing gateway ack or inconsistent
   secret scope **HARD-fails here** (REQ-CDP-DEPLOY-8). Provenance records the posture + verdict.
3. **Hand-off (operator):** read `deploy/README.md` + `infra-contract.yaml`; provision the §3
   prerequisites (Terraform/StackGen); seed the Doppler token.
4. **Apply per env (operator):** build → push image to the registry; `kubectl apply -k deploy/overlays/dev`
   (then `test`, then `prod`). Rollout waits for readiness (`/health` SELECT 1).
5. **Smoke through the gateway:** one authenticated request via agentgateway → `2xx`; `kubectl logs`
   shows stdout JSON; a pilot trace in Tempo carries `k8s.namespace/pod` + `deployment.environment`.

---

## 6. Acceptance predicate (FR-CND-29)

A machine-readable `cluster-smoke-spec.json` per environment; **PASS = all required stages pass**:

| Stage | Required | Pass condition |
|-------|----------|----------------|
| render | ✓ | `deploy/` + 3 overlays + infra-contract emitted; `generate ... --check` in-sync |
| gate | ✓ | deploy-coherence verdict `ok`/`soft`-acked; HARD on a deliberately-broken variant |
| install | ✓ | image pulls; pods admitted under restricted PSS |
| boot | ✓ | rollout Ready; readiness `/health` green |
| smoke | ✓ | authenticated request via agentgateway → 2xx; `/health` NOT externally routable |
| isolation (if tenant) | ✓ | cross-principal read denied (Postgres-gated) |

Negative checks (the teeth): an overlay with `trust_gateway` removed → gate HARD-fails; a mismatched
`schemaVersion` in the contract → consumer fail-closes; `installed` + `environments` → build error.

---

## 7. Three-layer hand-off (where D ends)

```
SDK (this pilot)         → app + deploy/ + overlays + infra-contract   [$0, render-only]
Terraform / StackGen     → provision cluster/VPC/IAM/registry/SecretStore/gateway/collector
Kestra / Argo / CI       → build → push → kubectl apply -k → smoke
agentgateway / kagent    → runtime: verify JWT, route, govern
```

D proves the **first arrow** and validates the contract that feeds the rest. The other arrows are
operator-owned and out of SDK scope (Mottainai: leverage the mature layers).

---

## 8. Open questions

- **OQ-D1.** Cloud target for the pilot — EKS or GKE? (Drives the operator bindings, not the artifacts.)
- **OQ-D2.** Is the StartDate app multi-tenant for the pilot (exercise `deployment.tenant` + the
  cross-principal isolation check), or single-owner for v1?
- **OQ-D3.** Run the cluster-smoke manually for D, or wire it into the local-deploy-harness as a new
  `cluster` rung now?

---

*v0.1 — D is execution/validation of a complete capability, not new generation. The SDK's job is the
first hand-off arrow; the pilot's value is proving the contract + gates hold on the real StartDate app.*
