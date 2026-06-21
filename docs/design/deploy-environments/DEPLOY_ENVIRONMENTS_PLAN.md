# Deployment Environments — Implementation Plan

**Version:** 1.1 (Post-CRP R1 — deltas folded)
**Date:** 2026-06-21
**Tracks:** `DEPLOY_ENVIRONMENTS_REQUIREMENTS.md` (v0.3)

---

## 1. Planning Discoveries (fed back into requirements §0)

| Requirements assumed (v0.1) | Code reality | Impact |
|---|---|---|
| Per-env values need new app wiring (FR-ENV-3/4) | The generated app **already reads every env-varying value from `os.environ`**: `DATABASE_URL`, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`, `HOST` (`settings_renderer.py:49-79`), `OTEL_*`/`ENV` (`telemetry_renderer.py:90-94`), `STARTD8_SECRETS_BACKEND`, `STARTD8_DEPLOYMENT_MODE`. | **FR-ENV-4 is already satisfied by construction** — zero app/`settings.py` change. The whole capability is a *config-emission* layer, not app code. |
| `ENV → deployment.environment` must be built (FR-ENV-6) | Already wired: `telemetry.py` sets `deployment.environment = os.environ.get("ENV", "development")`; `.env.example` sets `ENV` (binary, mode-derived) (`renderers.py:269`). | **FR-ENV-6 narrows to "set the per-env `ENV` value"** — the consumption already exists; today's binary default just becomes one of N. |
| Mechanism unknown (OQ-1) | The M1 `deploy/` tree is a clean **base**; cloud-native OQ-5 explicitly deferred kustomize base+overlays — this capability is its justification. | **kustomize base (`deploy/`) + `deploy/overlays/{env}/`** patching ConfigMap + replicas/resources/hostnames/ExternalSecret ref. One base, N overlays. |
| Secrets-per-env unknown (OQ-5) | `deploy.secrets.backend` (M0) + per-env ExternalSecret/SecretStore ref; Doppler has configs (dev/stg/prd) 1:1 with environments. | **Environment ↔ Doppler config**; the overlay patches the `SecretStore`/`ExternalSecret` ref. SDK emits the ref, never values. |
| Declaration shape unknown (OQ-2) | `AppManifest` is strict-keyed; `deploy:` block (M0) already exists with reserved keys. | Add a strict **`deploy.environments:`** sub-block (parallel to the rest of `deploy:`). |
| installed gets environments (OQ-3) | installed = single-user local (no `deploy/` tree at all). | **installed is single-local**; environments apply to `deployed` only (overlays live under `deploy/`). |

> ~40% of FRs narrow from "build" to "emit config that drives the existing runtime knobs." The app is
> already environment-ready; the work is the declaration grammar + overlay emission + per-env contract.

## 2. Approach (milestones)

**M0 — `deploy.environments` grammar.** Strict sub-block in `AppManifest` (`manifest.py`): a mapping
of env-name → overrides (`env`, `replicas`, `resources`, `hostnames`, `otlp_endpoint`, `log_level`,
`secrets_config`, `autoscaling`, `database_ref`). Default set `dev/test/prod` when `deploy:` present
and `environments:` omitted. Strict-keyed; unknown env keys error.

**M1 — Overlay renderers (`deploy_renderer.py`).** Emit `deploy/kustomization.yaml` (base) + per-env
`deploy/overlays/{env}/kustomization.yaml` + `deploy/overlays/{env}/configmap-patch.yaml`
(ENV/OTLP/log-level), `replicas-patch.yaml`, and the per-env ExternalSecret/SecretStore ref.
Environment-agnostic base; overlays carry only the varying values. Registered in `SCAFFOLD_RENDERERS`
for $0 drift; emitted only in `deployed` mode with environments declared (SOTTO when absent).

**M2 — Per-env infra-contract.** Extend `infra-contract.yaml` with an `environments:` section listing
each env's operator bindings (DB, OTLP, SecretStore/Doppler config, hostnames).

**M3 — Wireframe + coherence.** Wireframe surfaces declared environments + per-env unbound bindings;
coherence WARNs on an environment missing a required binding (e.g. prod with no DB ref).

**M4 — StartDate pilot.** Render dev/test/prod overlays from StartDate's base.

## 2A. CRP R1 Deltas (v1.1 — dispositions in requirements Appendix A)

- **M0:** error on `installed` + `deploy.environments` (R1-F7); mark `database_ref` secret vs non-secret (R1-F5).
- **M1 (expanded):** overlays patch **both planes** — ConfigMap `data` (ENV/OTLP/log-level) AND
  Deployment `replicas`/`resources` + HPA (R1-S1), each with an explicit patch type (strategic-merge;
  JSON6902 only where needed — R1-S2/FR-ENV-12). Deterministic overlay ordering (envs + per-overlay
  `resources`/`patches` lists fixed — R1-S7). Doppler project/config only in the overlay SecretStore
  ref, **never the base** (R1-F2). Emit empty (not stale-literal) defaults for overlay-owned OTLP/ENV
  so a missing key fails loud (R1-F4/FR-ENV-11).
- **M2:** per-env contract routes non-secret DB refs as named bindings; secret DSNs → ExternalSecret (R1-F5).
- **M3:** per-environment coherence — WARN when an env omits a required binding (prod w/o DB ref) and
  when a declared override has no overlay key set (baked-default-bypass guard, R1-S5/S6).

## 3. Validation

- M0: `deploy.environments` parses; default dev/test/prod; strict unknown-key error.
- M1: base + N overlays emitted; `kustomize build deploy/overlays/prod` yields valid manifests
  (gated, requires kustomize); installed/no-environments → no overlays (byte-identical, SOTTO);
  byte-stable; drift-owned.
- M2: contract lists per-env bindings (secret DSN→ExternalSecret, non-secret→named binding).
- M4: StartDate `kustomize build` per env differs only in the declared values.
- **SOTTO (R1-F3/S4):** golden-tree zero-diff when `environments` absent — incl. NO base
  `kustomization.yaml`; render twice → byte-identical overlays (R1-S7).
- **Base-leak guard (R1-S3):** grep the emitted base for any env name / hostname / replica count /
  Doppler config literal → must be empty.
- Validation references `kubectl apply -k` (in-tree kustomize, ≥1.14), not a standalone binary.

## 4. Risks

| Risk | Mitigation |
|---|---|
| Per-env values baked into base (determinism leak) | Base is env-agnostic; only overlays carry values; drift test on base |
| kustomize not installed | render-only ($0); `kustomize build` is a gated/operator step |
| Env value drift from app reality | Overlays patch the same env-var names the app reads (shared constant source) |
| Secret config mis-scoped across envs | env↔Doppler-config is an explicit per-env binding in the contract; operator owns values |

## 5. Out of scope
- CI/CD promotion/approval flow (Kestra/Argo/CI).
- Secret values; per-env app code.
- Non-kustomize templating engines (Helm) — possible later.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

> **Triage (v1.1, 2026-06-21):** all 7 S-suggestions ACCEPTED → §2A deltas. 0 rejected.

### Appendix A: Applied Suggestions

| ID | Suggestion | Delta (§2A) | Date |
|----|------------|-------------|------|
| R1-S1 | Patch resources/autoscaling/HPA, not just CM+replicas | M1 (both planes) | 2026-06-21 |
| R1-S2 | Specify patch mechanism (strategic-merge/JSON6902) | M1 + FR-ENV-12 | 2026-06-21 |
| R1-S3 | Base-leak guard validation | §3 | 2026-06-21 |
| R1-S4 | Golden-tree byte-identity SOTTO | §3 | 2026-06-21 |
| R1-S5 | Baked-default-bypass risk + coherence | M3 + FR-ENV-11 | 2026-06-21 |
| R1-S6 | Per-env coherence WARN + DB-ref routing | M2/M3 | 2026-06-21 |
| R1-S7 | Deterministic overlay ordering | M1 + §3 | 2026-06-21 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1 plan suggestions accepted | 2026-06-21 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-21

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-21 16:05:00 UTC
- **Scope**: Plan review weighted to the sponsor focus file — base/overlay determinism split, kustomize patch correctness, secrets-per-env, drift/byte-stability, and the "no app change" claim. Code-verified against the M1 `deploy_renderer.py` base tree.

##### Executive summary
- The headline "already env-driven, no app change" claim is **verified for the env-var plane** but overstated: `replicas`/`resources`/`autoscaling` (FR-ENV-3) are k8s manifest fields, not `os.environ` reads — M1 must patch them into the Deployment/HPA, which the plan does not yet enumerate.
- M1 says "ENV/OTLP/log-level via configmap-patch" but does not specify the **patch type** (strategic-merge vs JSON6902); strategic-merge on a ConfigMap `data` map is the only safe form for additive keys and must be stated to avoid clobbering the base.
- The OTLP endpoint has a **baked literal default** in telemetry.py; if an overlay omits it the per-env binding is silently bypassed (silent-degradation). Plan §4 risk table should add this.
- SOTTO byte-identity (FR-ENV-8) is asserted but the validation §3 says only "no overlays" — needs a golden-tree zero-diff assertion, including that the base `kustomization.yaml` itself is absent when no environments are declared.
- OQ-7 (per-env DB ref) and OQ-8 (kustomize fallback) are still open in the plan; recommend resolving both (split secret/non-secret DB ref; `kubectl -k` floor, no fallback emitter).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | M1 must enumerate patching `replicas`/`resources`/`autoscaling` into the Deployment/HPA objects (strategic-merge patch on the base Deployment), separately from the ConfigMap env patch — these are not os.environ reads and the current M1 bullet only names configmap-patch + replicas-patch. | "configmap-patch.yaml (ENV/OTLP/log-level), replicas-patch.yaml, and the per-env ExternalSecret/SecretStore ref" omits resources and autoscaling/HPA, which FR-ENV-3 promises; without them the overlay can't bind them. | §2 M1 | Render overlay for an env declaring resources+autoscaling; assert a Deployment resources patch and an HPA patch exist and `kustomize build` applies them. |
| R1-S2 | Interfaces | high | Specify the kustomize patch mechanism per artifact: ConfigMap `data` → strategic-merge (additive keys), `replicas` → strategic-merge on Deployment, ExternalSecret ref swap → strategic-merge or `kustomization.yaml` `configMapGenerator`/`secretGenerator` as appropriate. State that JSON6902 is used only where strategic-merge can't target (e.g. list element by index). | M1 says "patch" without a mechanism; strategic-merge vs JSON6902 correctness is focus #4 and a common source of silent overlay no-ops or base clobbering. | §2 M1 | Unit-assert each overlay patch declares its type; `kustomize build` output equals expected merged manifest for each env. |
| R1-S3 | Security | high | Add a base-leak guard step to M1/validation: assert the emitted **base** (`deploy/` + `deploy/kustomization.yaml`) contains no per-env value and no Doppler project/config literal — only sentinels/refs live in overlays. | Focus #1/#2: the determinism thesis depends on an airtight base; a single per-env value or secrets-tenant id in the base breaks SOTTO and couples the base to one environment. | §3 Validation (new bullet) + §4 Risks (existing "baked into base" row) | grep base tree for any env name, hostname, replica count, or Doppler config literal → must be empty. |
| R1-S4 | Validation | high | Strengthen §3 SOTTO validation from "no overlays" to a golden-tree **byte-identical** diff: render with and without `deploy.environments`; when absent, the full tree (incl. no base `kustomization.yaml`) must equal the committed M1 golden exactly. | "installed/no-environments → no overlays (byte-identical, SOTTO)" is not a strong enough check; a stray base kustomization.yaml or reordered key would pass it but break byte-identity. | §3 Validation, M1 line | Golden-tree test asserting zero diff when environments absent. |
| R1-S5 | Risks | medium | Add a risk row: env-varying values with a non-empty baked default (OTLP endpoint, ENV) silently bypass the overlay if the overlay omits them. Mitigation: emit empty defaults in the app module for overlay-owned values + a coherence check that every declared env sets the keys it claims to override. | telemetry.py bakes the OTLP endpoint literal; a forgotten overlay key uses the stale default instead of failing loud (Context Correctness by Construction violation). | §4 Risks | Coherence test: declared env overriding otlp_endpoint but overlay missing the ConfigMap key → WARN/ERROR. |
| R1-S6 | Ops | medium | M3 coherence should WARN per-environment (not just globally) when an env is missing a required binding (e.g. prod with no DB ref / no secrets_config), and surface it per-env in the wireframe. Resolve OQ-7 routing (secret DSN → ExternalSecret, non-secret → contract binding) in M2. | §2 M3 mentions "prod with no DB ref" but the grammar/contract split for secret vs non-secret DB refs (OQ-7) is unresolved; coherence needs the rule to know what "missing" means. | §2 M2/M3 | Fixtures: prod missing DB ref → WARN names the env; secret DSN → ExternalSecret only; non-secret → contract binding. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Data | medium | M1 must define deterministic ordering for overlay emission: environments rendered in a stable (declared or sorted) order, and per-overlay `kustomization.yaml` `resources`/`patches` lists in fixed order, so re-render is byte-stable across runs and dict iteration. | Focus #6: per-env ordering/naming nondeterminism is the classic drift source; "literal YAML, no dict-ordering" is claimed for the base but overlays add a new ordered dimension (the env map). | §2 M1 / §3 Validation | Render twice; assert byte-identical overlay tree; assert env order independent of manifest key insertion order. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan milestone(s) that address it. Reviewer: claude-opus-4-8-1m, 2026-06-21.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-ENV-1 (Declared environments) | M0 (`deploy.environments` grammar) | Full | — |
| FR-ENV-2 (Orthogonal to mode) | M0 (deployed-only, strict-keyed) | Partial | No specified disposition for the illegal combo `installed` + `environments` (should error) — see R1-F7. |
| FR-ENV-3 (Per-environment value set) | M0 grammar + M1 overlay renderers | Partial | M1 emits configmap-patch + replicas-patch only; `resources` and `autoscaling`/HPA patches not enumerated (R1-S1); env-var plane vs k8s-field plane not separated (R1-F1). |
| FR-ENV-4 (Runtime binding, not baked) | M1 (overlays supply values; no app change) | Partial | True for env-var plane; baked OTLP/ENV literal defaults can silently bypass overlay (R1-S5/R1-F4); replicas/resources are not env reads at all. |
| FR-ENV-5 (Base + overlays emission) | M1 (kustomize base + `overlays/{env}/`) | Partial | Patch mechanism (strategic-merge vs JSON6902) unspecified (R1-S2); base-leak guard not in validation (R1-S3). |
| FR-ENV-6 (ENV → deployment.environment) | M1 (overlay sets `ENV` value) | Full | — (consumption verified in telemetry.py; value-binding only). |
| FR-ENV-7 (Secrets per environment) | M1 (per-env ExternalSecret/SecretStore ref) | Partial | No explicit rule barring Doppler project/config literal from the base (R1-F2); secret vs non-secret DB-ref routing (OQ-7) unresolved (R1-F5/R1-S6). |
| FR-ENV-8 (Determinism + SOTTO) | M1 (SOTTO when absent) + §3/§4 | Partial | Validation says "no overlays" not byte-identical golden-tree diff (R1-S4/R1-F3); overlay emission ordering nondeterminism risk (R1-S7). |
| FR-ENV-9 (Per-env infra-contract) | M2 (`environments:` in infra-contract) | Partial | Contract content depends on OQ-7 secret/non-secret split being resolved (R1-F5). |
| FR-ENV-10 (StartDate pilot) | M4 | Full | — |
| OQ-7 (per-env DB ref) | (open) | Missing | No plan position; recommend secret→ExternalSecret, non-secret→contract binding (R1-F5/R1-S6). |
| OQ-8 (kustomize fallback) | §5 out-of-scope (Helm) | Partial | `kubectl -k` floor not stated; recommend no fallback emitter, document min kubectl ≥1.14 (R1-F6). |
