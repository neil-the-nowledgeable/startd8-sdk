# Deployment Environments (dev/test/prod) — Requirements

**Version:** 0.3 (Post-CRP R1 — triage applied)
**Date:** 2026-06-21
**Status:** Ready for implementation
**Owner:** StartD8 SDK / scaffold_codegen (bucket-1 $0 deterministic)
**Builds on:** `docs/design/deployment-mode/` (mode) + `docs/design/cloud-native-deploy/` (the `deploy/` tree)

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against `settings_renderer.py` / `telemetry_renderer.py` / `renderers.py` /
> `deploy_renderer.py` produced one dominant correction (see `DEPLOY_ENVIRONMENTS_PLAN.md` §1): **the
> generated app is already fully environment-driven at runtime** — every env-varying value reads from
> `os.environ`. So this capability is a *config-emission* layer (declaration grammar + base+overlays +
> per-env contract), **not app code**. ~40% of FRs narrow from "build" to "emit config."

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Per-env values need app wiring (FR-ENV-3/4) | App already reads `DATABASE_URL`/pool/`HOST`/`OTEL_*`/`ENV`/secrets-backend from `os.environ`. | **FR-ENV-4 satisfied by construction** — zero `settings.py`/app change. |
| `ENV→deployment.environment` must be built (FR-ENV-6) | Already wired (`telemetry.py`; `.env.example` ENV is binary today). | FR-ENV-6 narrows to **setting the per-env `ENV` value** (consumption exists). |
| Mechanism unknown (OQ-1) | M1 `deploy/` tree is a clean base; cloud-native OQ-5 deferred kustomize overlays — this is its justification. | **kustomize base + `deploy/overlays/{env}/`** patching only varying values. |
| Secrets-per-env unknown (OQ-5) | `deploy.secrets.backend` (M0) + Doppler configs (dev/stg/prd) map 1:1 to environments. | **Environment ↔ Doppler config**; overlay patches the SecretStore/ExternalSecret ref. |
| installed gets environments (OQ-3) | installed = single-user local, no `deploy/` tree. | **Environments apply to `deployed` only**; installed is single-local. |

**Resolved open questions:**
- **OQ-1 → kustomize base + per-env overlays** under `deploy/overlays/{env}/`.
- **OQ-2 → `deploy.environments:`** strict sub-block in the existing `deploy:` block.
- **OQ-3 → installed is single-local**; environments are deployed-only.
- **OQ-4 → No app/`settings.py` change** — already env-driven (the headline correction).
- **OQ-5 → environment ↔ Doppler config** + per-env OTLP/ENV; overlays carry them; SDK emits refs, not values.
- **OQ-6 → default `dev/test/prod`, names extensible** (arbitrary set supported).

---

## 1. Problem Statement

`deployment.mode` (installed|deployed) sets the structural *shape*; the cloud-native `deploy/` tree
(M1) emits one config. But real operations run the **same deployed app in multiple environments —
dev, test, prod** — that differ only in **values**: which database, which OTLP collector, replica
count, resource sizing, hostnames, secrets scope, log level, autoscaling. Today `ENV` is binary
(mode-derived `development|production`); there is no way to declare environments or emit their
per-environment config. Operators hand-write three variants — which defeats the determinism thesis:
*environment config is structural plumbing, not company content, and should be generated.*

**Environment is ORTHOGONAL to mode:** mode = topology/security shape; environment = which values. A
`deployed` app runs in dev *or* test *or* prod with one shape and three value-sets.

### Gap table

| Concern | Today | Gap |
|---------|-------|-----|
| Environment axis | `ENV` binary (mode-derived dev/prod) | No dev/test/prod declaration |
| Per-env values | one ConfigMap / `.env.example` | No per-env replicas/resources/hostnames/OTLP/secrets/log-level |
| Secrets per env | one SecretStore ref | No env→Doppler-config mapping |
| Emission | one `deploy/` tree | No base + per-env overlays |
| Contract | one binding set | No per-env operator bindings |

---

## 2. Requirements

- **FR-ENV-1 (Declared environments).** `app.yaml` SHALL declare a set of environments (default
  `dev`/`test`/`prod`, names extensible) and their per-environment value overrides.
- **FR-ENV-2 (Orthogonal to mode — guarded v0.3 R1-F7).** Environment SHALL be independent of
  `deployment.mode`. A `deployed` app supports N environments; `installed` is a single local
  environment. Declaring `deploy.environments` while `deployment.mode: installed` SHALL be a strict
  **build error** (environments are deployed-only), never silently ignored.
- **FR-ENV-3 (Per-environment value set — TWO binding planes, corrected v0.3 R1-F1).** Each
  environment MAY override values across **two distinct planes** that must not be conflated:
  - **(a) App env-vars** (bound via ConfigMap, read by the app from `os.environ`):
    `OTEL_EXPORTER_OTLP_ENDPOINT`, `ENV`, log level, `DATABASE_URL`, secrets scope (Doppler config).
  - **(b) Kubernetes object fields** (patched into the manifests, NOT `os.environ`): `replicas`,
    `resources`, `autoscaling`/HPA, `hostnames`.
  The `database_ref` SHALL be routed by secret-ness (R1-F5/OQ-7): a credential-bearing DSN → the
  per-env `ExternalSecret` (never a ConfigMap); a non-secret DSN (host/port/IAM-auth) → a named
  binding in the per-env contract (FR-ENV-9).
- **FR-ENV-4 (Runtime binding, not baked — satisfied by construction, v0.2).** Environment-varying
  values SHALL be bound at runtime, not baked into app code. **Already true:** the generated app reads
  all such values from `os.environ` (`settings.py`/`telemetry.py`); this capability supplies the
  values via overlays and requires **no app-code change**.
- **FR-ENV-5 (Base + overlays emission).** The capability SHALL emit one environment-agnostic base
  (the `deploy/` tree) plus per-environment **kustomize overlays** under `deploy/overlays/{env}/`
  that patch only the varying values (ConfigMap env, replicas/resources, hostnames, ExternalSecret
  ref) — one base, N overlays.
- **FR-ENV-6 (ENV → deployment.environment — narrowed v0.2).** Each environment's overlay SHALL set
  the `ENV` value; the app **already** maps `ENV` → OTel `deployment.environment` + log posture, so
  this is a value-binding, not new wiring. The binary mode-derived default becomes one of N.
- **FR-ENV-7 (Secrets per environment — base-leak guard added v0.3 R1-F2).** Each environment SHALL
  map to a secrets scope — for the default Doppler backend, an environment ↔ Doppler **config** (e.g.
  dev→`dev`, prod→`prd`) bound to the per-env `ExternalSecret`/`SecretStore` ref. The SDK emits the
  reference, never the values. The Doppler **project/config identifier** SHALL appear ONLY in the
  per-env overlay's SecretStore ref — **never in the base** $0 artifacts (a project id in the base
  couples it to one tenant and breaks SOTTO byte-identity).
- **FR-ENV-8 (Determinism + SOTTO — golden-tree test, hardened v0.3 R1-F3/R1-S4).** No environments
  declared → the **entire emitted tree byte-identical** to the current M1 output — asserted by a
  golden-tree zero-diff test, including the **absence of any base `kustomization.yaml`** when no
  environments are declared (not merely "no overlays"). Overlay emission SHALL be deterministically
  ordered (environments + per-overlay `resources`/`patches` lists in a fixed order) so re-render is
  byte-stable regardless of manifest key insertion order (R1-S7).
- **FR-ENV-11 (No silently-overridable baked default — added v0.3 R1-F4).** For any env-var the
  overlay is expected to own (OTLP endpoint, `ENV`), the generated app module SHALL NOT carry a
  non-empty generation-time literal default that would silently win when an overlay omits the key —
  a missing per-env value SHALL fail loud (or be coherence-flagged), not fall back to a stale baked
  endpoint.
- **FR-ENV-12 (Kustomize patch contract — added v0.3 R1-S2).** Overlays SHALL declare their patch
  mechanism per artifact (ConfigMap `data` + Deployment `replicas`/`resources` → strategic-merge;
  JSON6902 only where strategic-merge cannot target). The toolchain floor is `kubectl ≥ 1.14`
  (in-tree kustomize via `apply -k`); no standalone-kustomize fallback emitter (OQ-8).
- **FR-ENV-9 (Per-env infra-contract).** The infra-needs contract SHALL enumerate per-environment
  operator bindings (DB, OTLP collector, SecretStore/Doppler config, hostnames).
- **FR-ENV-10 (StartDate pilot).** StartDate SHALL render dev/test/prod overlays from one base.

## 3. Non-Requirements

- NOT a secrets value store — operator owns the per-env secret values (Doppler/cloud SM).
- NOT environment-specific app CODE — the app reads `os.environ`; environments change values only.
- NOT CI/CD environment promotion / approval orchestration (Kestra/Argo/CI).
- NOT changing `deployment.mode` semantics; environment is a new orthogonal axis.
- NOT a fixed dev/test/prod-only set — names are extensible (though dev/test/prod is the default).

## 4. Open Questions

> OQ-1..OQ-6 resolved by the planning pass — see §0. **OQ-7/OQ-8 RESOLVED by CRP R1:**
> - **OQ-7 → split by secret-ness** (R1-F5): credentialed DSN → ExternalSecret (overlay); non-secret
>   DSN → named binding in the per-env contract. Folded into FR-ENV-3/7/9.
> - **OQ-8 → no fallback emitter** (R1-F6): `kubectl ≥ 1.14` in-tree kustomize (`apply -k`) is the
>   floor; a parallel plain-ConfigMap emitter would double the drift surface. Folded into FR-ENV-12.
>
> No open questions remain.

---

*v0.2 — Post-planning self-reflective update. FR-ENV-4 satisfied-by-construction, FR-ENV-6 narrowed,
mechanism resolved to kustomize base+overlays, 6 OQs resolved.*

*v0.3 — Post-CRP R1 triage (claude-opus-4-8-1m). 14 suggestions ACCEPTED (0 rejected). Key
correction: the "no app change" headline was overstated — **replicas/resources/autoscaling are
Kubernetes object fields, not `os.environ` reads** → FR-ENV-3 split into two binding planes (R1-F1).
Plus base-leak guard (no Doppler project in base, R1-F2), golden-tree SOTTO (R1-F3), no
silently-overridable baked OTLP default (R1-F4/FR-ENV-11), installed+environments guard (R1-F7),
patch-mechanism + kubectl floor (FR-ENV-12), OQ-7/OQ-8 resolved. Dispositions in Appendix A.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

> **Triage (v0.3, 2026-06-21):** all 14 R1 suggestions (7 F + 7 S) ACCEPTED, 0 rejected. They
> converge on: the two-binding-planes correction, base-leak/SOTTO rigor, and patch-mechanism
> specificity.

### Appendix A: Applied Suggestions

| ID | Suggestion | Disposition (where merged) | Date |
|----|------------|----------------------------|------|
| R1-F1 | Split FR-ENV-3 into env-var vs k8s-field planes | → FR-ENV-3 (inline) | 2026-06-21 |
| R1-F2 | Forbid Doppler project/config literal in base | → FR-ENV-7 (inline) | 2026-06-21 |
| R1-F3 | Golden-tree byte-identity SOTTO test | → FR-ENV-8 (inline) | 2026-06-21 |
| R1-F4 | No silently-overridable baked OTLP/ENV default | → FR-ENV-11 (new) | 2026-06-21 |
| R1-F5 | Secret/non-secret DB-ref routing (OQ-7) | → FR-ENV-3/7/9; OQ-7 resolved | 2026-06-21 |
| R1-F6 | kubectl ≥1.14 floor, no fallback (OQ-8) | → FR-ENV-12; OQ-8 resolved | 2026-06-21 |
| R1-F7 | installed + environments → build error | → FR-ENV-2 (inline) | 2026-06-21 |
| R1-S1 | M1 patch resources/autoscaling/HPA (not just CM+replicas) | → plan M1 | 2026-06-21 |
| R1-S2 | Specify patch mechanism (strategic-merge/JSON6902) | → FR-ENV-12 + plan M1 | 2026-06-21 |
| R1-S3 | Base-leak guard validation step | → plan §3/§4 | 2026-06-21 |
| R1-S4 | Golden-tree byte-identity validation | → FR-ENV-8 + plan §3 | 2026-06-21 |
| R1-S5 | Risk row + coherence for baked-default bypass | → FR-ENV-11 + plan M3/§4 | 2026-06-21 |
| R1-S6 | Per-env coherence WARN + OQ-7 routing | → plan M2/M3 | 2026-06-21 |
| R1-S7 | Deterministic overlay ordering | → FR-ENV-8 + plan M1 | 2026-06-21 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1 suggestions accepted | 2026-06-21 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-21

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-21 16:05:00 UTC
- **Scope**: Requirements review weighted to the sponsor focus file — determinism/SOTTO base-vs-overlay split, secrets-per-env, orthogonality to mode, kustomize correctness, and stress-testing the "already env-driven, no app change" claim. Code-verified against `settings_renderer.py`, `telemetry_renderer.py`, `renderers.py`, `deploy_renderer.py`.

##### Sponsor focus asks (answered first, per focus-file template)

**Ask 5 — "already env-driven" claim: is there ANY env-varying value the app does NOT read from `os.environ`?**
- **Summary answer:** Partial — yes, two classes leak past the claim.
- **Rationale:** (1) FR-ENV-3 lists `replicas`, `resources`, and `autoscaling` as per-env overrides, but these are **never** `os.environ` reads in the app — they are pure Kubernetes object fields (Deployment `.spec.replicas`, container `resources`, HPA). The "app reads everything from `os.environ`" claim is true only for the env-var subset (`DATABASE_URL`/pool/`HOST`/`OTEL_*`/`ENV`/secrets-backend, verified `settings_renderer.py:49-79`, `telemetry_renderer.py:90-94`). (2) `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_SERVICE_NAME` are read from env **but fall back to a generation-time literal default** baked into `telemetry.py` (`endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT', {endpoint!r})`). If an overlay omits the ConfigMap entry, the baked default silently wins — so "bound at runtime" is conditional on the overlay always setting it.
- **Assumptions / conditions:** none — both are verifiable in the cited source.
- **Suggested improvements:** Split FR-ENV-3 into two binding planes (app env-vars vs k8s manifest fields) — see R1-F1. Add a requirement that any env-varying OTLP value the overlay is expected to own must NOT also carry a non-empty baked literal default (see R1-F4).

**Ask 7 (OQ-7) — per-env DB ref: overlay-only via ExternalSecret, or also named bindings in the contract?**
- **Summary answer:** Both, split by secret-ness.
- **Rationale:** A DSN containing credentials must never be a non-secret ConfigMap value (would be a $0-artifact leak per FR-ENV-7's "emits the ref, never the values"). A non-secret DSN (host/port/dbname, IAM/cloud-auth) is safely a named binding in the per-env contract (FR-ENV-9). The contract already exists as the operator seam, so surfacing the non-secret case there costs nothing and avoids forcing every DB ref through ExternalSecret.
- **Assumptions / conditions:** the grammar can mark a `database_ref` as secret vs non-secret.
- **Suggested improvements:** see R1-F5 (require FR-ENV-3/7 to state the secret/non-secret routing rule explicitly).

**Ask 8 (OQ-8) — kustomize fallback for clusters without kustomize?**
- **Summary answer:** No separate fallback renderer; rely on `kubectl apply -k` (kustomize is built into kubectl ≥1.14) and document the floor.
- **Rationale:** `kubectl -k` ships kustomize in-tree, so "no kustomize binary" is effectively a non-issue for any supported cluster; a parallel plain-ConfigMap emitter would double the renderer surface, double the drift-owned artifacts, and create a second source of per-env truth (a Mottainai/determinism cost). The risk is real only for pre-1.14 kubectl, which is out of support.
- **Assumptions / conditions:** state a minimum `kubectl`/kustomize version as a documented floor; the SDK render step never shells out to kustomize (render is $0, `kustomize build` is the operator's gated step).
- **Suggested improvements:** see R1-F6 (add the version floor as an explicit requirement/assumption).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | Split FR-ENV-3 into two binding planes: app-level env-vars (DATABASE_URL/pool/HOST/OTEL_*/ENV/secrets-config — bound via ConfigMap, read from os.environ) vs Kubernetes object fields (replicas/resources/autoscaling — patched into Deployment/HPA, NOT os.environ). | "Each environment MAY override: replicas, resources, ... OTEL_..., the database reference" conflates two mechanisms; FR-ENV-4's "satisfied by construction / reads from os.environ" is only true for the first plane. replicas/resources/autoscaling are never env reads. | FR-ENV-3 sentence listing the override set | Verify each listed override maps to either a ConfigMap key the app reads OR a documented manifest field; no item is unmapped. |
| R1-F2 | Security | high | FR-ENV-7 must forbid the Doppler **project** name (not just values) from appearing in any $0 ConfigMap/base artifact; only the per-env config name on an ExternalSecret/SecretStore ref is permitted, and even that must be in the overlay, never the base. | Focus #2 (FR-CND-9 leak): "emits the reference, never the values" addresses values but is silent on whether the Doppler project/config identifier itself may sit in the base. A project name in the base would couple the base to one secrets tenant and break SOTTO byte-identity-when-absent. | FR-ENV-7, after "emits the reference, never the values" | grep emitted base tree for any Doppler project/config literal → must be absent; only overlay SecretStore refs carry config name. |
| R1-F3 | Validation | high | FR-ENV-8 (determinism/SOTTO) needs a concrete acceptance criterion: with `deploy.environments` omitted, the entire emitted tree (including deploy/) must be **byte-identical** to the current M1 output, asserted by a golden-tree diff, not just "no overlays." | "byte-identical to today" is stated but untestable as written; SOTTO regressions (e.g. a base kustomization.yaml emitted even when no environments) are exactly the kind of leak that slips through without a golden assertion. | FR-ENV-8 | Golden-tree test: render with/without `environments:`; assert zero-diff when absent. |
| R1-F4 | Risks | medium | Add a requirement: env-varying OTLP/ENV values that an overlay is expected to own MUST NOT carry a non-empty generation-time literal default in the app module; the baked default must be empty/None so a missing overlay entry fails loud rather than silently using a stale endpoint. | telemetry.py bakes `OTEL_EXPORTER_OTLP_ENDPOINT` default as a literal at gen time; if an overlay forgets it, the per-env binding is silently bypassed — a "Context Correctness by Construction" silent-degradation path. | New FR near FR-ENV-4/6 | Render telemetry module; assert the OTLP-endpoint default literal is empty when telemetry is overlay-driven; missing ENV-var → loud failure not stale default. |
| R1-F5 | Data | medium | FR-ENV-3 / FR-ENV-7 must state the secret/non-secret routing rule for `database_ref`: credential-bearing DSN → ExternalSecret (overlay), non-secret DSN → named binding in per-env contract (FR-ENV-9). Resolves OQ-7. | OQ-7 is open; without an explicit rule the implementer may route a credentialed DSN through a non-secret ConfigMap (leak) or force every DSN through ExternalSecret (over-constrains IAM/cloud-auth DBs). | FR-ENV-3 (database reference) + FR-ENV-7 | Two fixtures (secret DSN, non-secret DSN); assert secret → ExternalSecret only, non-secret → contract binding; neither lands in base ConfigMap. |
| R1-F6 | Ops | low | Record the OQ-8 resolution as an explicit assumption: minimum tooling is `kubectl` ≥1.14 (in-tree kustomize via `apply -k`); no standalone-kustomize fallback emitter. | OQ-8 is open and the answer drives whether M1 doubles its renderer surface; pinning the floor closes it and prevents a later reviewer re-opening the fallback question. | §4 Open Questions / §0 resolved list | Doc states the version floor; plan §3 validation references `kubectl apply -k` (not just `kustomize build`). |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | medium | FR-ENV-2 orthogonality claim needs a guard: define behavior when `deploy.environments` is declared while `deployment.mode: installed`. Should error (environments are deployed-only per OQ-3), not silently ignore. | Orthogonality to mode (focus #3) is asserted but the illegal combination (installed + environments) has no specified disposition — silent-ignore would violate strict-keyed manifest expectations and confuse operators. | FR-ENV-2 | Manifest fixture: installed + environments → strict validation error with a clear message. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.
