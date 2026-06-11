# Deployment Mode (Installed vs Deployed) — Implementation Plan

**Version:** 1.0 (Draft — discoveries fed back into Requirements v0.2 §0)
**Date:** 2026-06-11
**Status:** Draft
**Pairs with:** `DEPLOYMENT_MODE_REQUIREMENTS.md` v0.2

> This plan stress-tests the requirements by mapping each to real files. Discoveries that contradict
> or simplify the requirements are captured in §1 and flow back into Requirements v0.2 (§0).

---

## 1. Planning Discoveries (feed Requirements §0)

| # | Requirements v0.1 assumed | Planning revealed | Impact on requirements |
|---|---------------------------|-------------------|------------------------|
| D1 | Mode is a generation input hashed into many artifacts (FR-DET-1, FR-CFG-3a) | The backend **drift/skip-hook path is schema-only**: `provider.py:is_in_sync` reads `schema.prisma`, never `app.yaml`; `render_db`/`render_main` take `(schema_text, source_file)` only. Threading mode into backend bytes means widening the drift input set (like `completeness_text`/`forms_text`/`display_text` already do via the `_renderers()` closure) **and** teaching the provider + `--check` to read `app.yaml`. Non-trivial cross-cut. | Minimize byte-affecting mode surface. Prefer runtime env reads inside already-emitted files over new generation inputs wherever security doesn't require baking. |
| D2 | `main.py` would change shape by mode (bind, layers) | `render_main` is **deliberately frozen**: every optional layer (AI, pages, flows, polish, `user_routers`) mounts via a **tolerant `try/except ModuleNotFoundError` import** so main.py's drift hash never moves. This is the idiomatic extension seam. | Add deployed-mode layers (auth, tenancy middleware) the **same way** — as new optional modules main.py already tolerantly imports — so main.py stays byte-identical. Don't rewrite main.py per mode. |
| D3 | Persistence needs structural divergence for Postgres (FR-PER-2) | `render_db` **already** runtime-branches `if engine.dialect.name == "sqlite"` for pragmas and works against Postgres today via `DATABASE_URL`. The only deployed gaps are (a) pool config and (b) not auto-`create_all`. | FR-PER-2 is largely **overspecified** — persistence is already mode-agnostic at runtime. Narrow to: pool sizing + create_all gate, both achievable as **runtime env reads inside db.py** (near-zero drift). |
| D4 | Migration-vs-createall is structural (FR-PER-3) | `init_db()` is called from main.py's frozen lifespan; gating it by reading mode **inside db.py** keeps main.py byte-identical and adds one env-conditional branch to db.py. | Reclassify FR-PER-3 as a **runtime binding** (FR-CFG-3b) with a mode-derived default, not structural. |
| D5 | Bind host is structural-ish (FR-NET-1) | Bind is set by the run command (uvicorn CLI / Dockerfile), not by app code. | FR-NET-1 default is emitted into the **run command / Dockerfile** (scaffold), and/or a `settings.py` default — runtime binding, mode-derived default. |
| D6 | One `deployment.mode` could subsume OTel `deployment_environment` (OQ-5) | They are **orthogonal axes**: mode = topology/security shape (installed/deployed); environment = telemetry tag (dev/staging/prod). installed+dev and deployed+prod both valid. | Keep separate; mode sets a default for the OTel tag but does not replace it. |
| D7 | Deterministic auth mechanism is shippable at $0 (FR-IDN-2, OQ-3) | Rolling a real credential/session system deterministically is a **security liability** to ship naively. The repo's idiom is the `user_routers.py` **seam**. | Narrow FR-IDN-2: deployed mode emits a **principal-resolution dependency + a `require_principal` guard + the seam + a reference (non-production) scaffold**, NOT a credential store. Real auth = operator (bucket 4). |
| D8 | Tenant scoping is "part of the generated code shape" (FR-TEN-2/3) | True structural item: it changes **router query bodies** (`select(E)` → `select(E).where(E.owner == principal)`), per-entity templates, and smoke tests. This is the **only large-blast-radius** dimension and needs the schema to declare the owner relationship (OQ-2). | Split into a **second increment (Tier B)**; v1 pilot defers tenancy. Require explicit `deployment.tenant` declaration; **no silent owner-column synthesis** (it would mutate the human-owned schema contract). |
| D9 | A runtime "mode signal" is enough (FR-CFG-4) | There is **no settings/config module** emitted today; several env reads (mode, pool, create_all gate, bind default) want one home. | **Add a requirement**: emit a small owned `app/settings.py` centralizing mode + env reads (new owned `$0.00-skip` kind). |
| D10 | `migrations.enabled` vs mode (OQ-6) | `AppManifest.migrations: bool` already exists and drives Alembic emission in scaffold_codegen. | Mode sets the **default** for migrations; the coherence guard (FR-CFG-5) reconciles explicit conflicts (`deployed` + `migrations:false` → error/warn). Keep fields independent. |

**Net:** the byte-affecting (generation-time) surface is far smaller than v0.1 implied. Two tiers emerge:

- **Tier A (v1 pilot) — low blast radius, mostly runtime:** mode declaration + `settings.py` + db.py pool/create_all gate + bind/Dockerfile default + secrets/OTel default + coherence guard + wireframe surfacing + auth *seam scaffold* (optional module).
- **Tier B (increment 2) — high blast radius, structural:** tenant-scoped queries in routers/templates/tests; requires `deployment.tenant` declaration. Deferred.

This is the reflective loop working: >30% of the v0.1 requirements get reclassified or narrowed (D3, D4, D5, D7, D8) — confirming they were premature.

---

## 2. Architecture of the Change

```
app.yaml  deployment: { mode: installed|deployed, tenant?: {...} }   (Tier B uses tenant)
   │
   ├─ scaffold_codegen/manifest.py  ── AppManifest.deployment_mode (new field) ──┐
   │                                                                             │
   ├─ generate backend ── coherence guard (mode × DSN × migrations) ── fail-fast │
   │                                                                             ▼
   └─ backend_codegen ──► emits owned app/settings.py  (mode constant + env reads)
                          │
                          ├─ db.py reads settings: pool sizing + create_all gate  (runtime)
                          ├─ main.py UNCHANGED (tolerant import of optional app/auth.py seam)
                          ├─ Dockerfile/run default bind from mode                 (scaffold)
                          └─ (Tier B) routers/templates/tests gain tenant scoping  (deferred)
```

Guiding principle from D1/D2: **bake only what security requires; bind everything else at runtime.**

---

> **Implementation status (2026-06-11):** **A1 DONE** (`AppManifest.deployment_mode` enum + strict
> parse, 5 tests). **A2 DONE at the library layer** (`settings_renderer.render_settings` + deployed-only
> emission in `render_backend` + `python-settings` self-embedded-mode drift branch + provider skip-hook
> + exports). **A9 core DONE** (`tests/unit/backend_codegen/test_deployment_mode.py`, 11 tests incl. the
> FR-CFG-7a skip-hook-without-`app.yaml` proof; 410 backend/scaffold/wireframe tests green). Discoveries
> **D11** (settings.py deployed-only) and **D12** (mode-sha256 redundant) folded into Requirements
> §3.A. **Remaining for M0/M1:** CLI `generate backend` reading `app.yaml`'s `deployment_mode`
> (+`--mode`); checked-in golden trees (R1-S4); A3–A8.

## 3. Work Breakdown — Tier A (v1 pilot)

### Step A1 — Mode declaration & manifest (FR-CFG-1/2)
- `scaffold_codegen/manifest.py`: add `deployment` to `_TOP_KEYS`; add `AppManifest.deployment_mode: str = "installed"`; parse `data["deployment"]["mode"]`, validate enum, strict on unknown keys.
- Add a tiny shared `deployment_mode` accessor usable by both scaffold and backend codegen (avoid scatter — FR-CFG-2).

### Step A2 — Owned `app/settings.py` (FR-CFG-4, D9)
- New renderer `render_settings()` in `backend_codegen` → `app/settings.py` (new owned kind `python-settings`).
- Emits: `DEPLOYMENT_MODE = "<baked from app.yaml>"` constant + helpers that read env (`STARTD8_DEPLOYMENT_MODE` for *validation only*, `DATABASE_URL`, pool size, bind default).
- This file **does** vary by mode → it is the one new generation input that must be drift-hashed. **Per R1-S1 / FR-CFG-7a, registering in `drift._renderers()` alone is NOT sufficient** — that feeds the `--check` CLI, not the schema-only skip-hook (`owned_file_in_sync`). `render_settings()` MUST **self-embed** `# startd8-mode:` + `mode-sha256:` in the header so the skip-hook re-renders from the file's own header with no `app.yaml`. (See Step A9.)
- FR-CFG-4 validation (**directional fail-closed, R1-S7**): on startup, if env `STARTD8_DEPLOYMENT_MODE` says `deployed` but the binary is `installed`-shaped → **refuse to start** (non-zero); reverse → warn and continue; matching/absent → OK. Never silently switch structural shape.

### Step A3 — db.py persistence posture (FR-PER-1/2/3, FR-CON-1, D3/D4)
- `render_db()`: import from `.settings`; keep SQLite pragmas under the existing dialect branch; add pool args when deployed (runtime read); gate `create_all` in `init_db()` so deployed does NOT auto-create against shared DB (loud "run alembic upgrade head" instead).
- db.py gains mode-awareness via **runtime env read**, not a new generation input → **zero drift** for db.py if written to read settings at runtime. (Decision point: settings constant is baked, db.py reads it at runtime → db.py bytes unchanged by mode. Prefer this.)

### Step A4 — Bind default & container shape (FR-NET-1/2, D5)
- `scaffold_codegen/renderers.py:render_dockerfile()`: bind `127.0.0.1` vs `0.0.0.0` from `manifest.deployment_mode`; for installed, emit a local run script (`run.sh`/console entry) instead of presenting a public-server container as primary.
- **R1-S5 (verify, don't assume):** turn "scaffold drift already hashes the manifest … Verify" into a concrete task — confirm `AppManifest.deployment_mode` is actually folded into the scaffold `manifest-sha256` that lands in the Dockerfile header, and add a test asserting installed vs deployed Dockerfiles carry **different** embedded scaffold SHAs and that `--check` flips on a mode change. If the SHA does not cover `deployment_mode`, two mode-differing Dockerfiles collide on one hash → silent drift hole (violates FR-DET-1). *(Note: A1 already added `deployment_mode` to `AppManifest`; the manifest-text the scaffold hashes must include the `deployment:` block — verify the hash is over the resolved manifest, not a subset.)*

### Step A5 — Secrets & observability defaults (FR-SEC-1, FR-OBS-1, D6)
- Tie mode to the **default** secrets backend (`local` vs expect `doppler`) and OTel posture, reusing the existing `secrets/` switch — mode only changes the default, never overrides explicit operator config. Keep `deployment.mode` orthogonal to OTel `deployment_environment`; set default, don't subsume.

### Step A6 — Auth seam scaffold (FR-IDN-1/2/3, D7)
- Installed: nothing emitted (today's behavior).
- Deployed: emit optional `app/auth.py` (new owned kind `python-auth-seam`) providing a `get_principal` dependency + `require_principal` guard wired to the existing `user_routers.py` seam — a **reference scaffold**, clearly marked not-production, policy left to operator. main.py tolerantly imports it (D2) → main.py unchanged.

### Step A7 — Coherence guard (FR-CFG-5, D10) — **normative matrix (R1-S3/R1-S2)**
- In `generate backend` (and `wireframe`): evaluate the declared mode against DSN/migrations/bind/auth-tenant using the **normative severity matrix now in FR-CFG-5** (ERROR/WARN/OK), not "e.g." examples. Implement one decision per matrix row.
- **R1-S2 (auth-without-isolation):** when `deployed` + auth seam emitted (A6) + **no** `deployment.tenant` (B1 deferred) → emit a loud **WARN** (not ERROR — single-owner deployed is legal) and have A8 print "authenticated, NOT tenant-isolated."
- Validation: one build test per matrix row asserting the exact severity (exit code / log level) and message string.

### Step A8 — Wireframe surfacing (FR-CFG-6, FR-CLI-2)
- `startd8 wireframe`: print declared mode + resolved per-dimension posture (persistence/bind/auth/secrets/observability) and any coherence warnings. $0, read-only.

### Step A9 — Drift, gates, tests (FR-DET-1..4) — **hardened by R1-S1/S4/S6**
- Register `python-settings` (and `python-auth-seam` when deployed) in `provider.py` owned kinds + `drift._renderers()`.
- **R1-S1 (skip-hook re-derivation — CRITICAL):** `_renderers()` feeds `check_drift` (the full `--check` CLI), **not** `owned_file_in_sync` (the schema-only skip-hook). So registering in `_renderers()` does NOT make `settings.py` skip-hook-verifiable. Per **FR-CFG-7a**, have `render_settings()` self-embed `# startd8-mode:` + `mode-sha256:` in the header, and ensure the drift re-render reads mode from the **on-disk file's header** (the `embedded_ai_agent_spec` precedent at drift.py:221) so `owned_file_in_sync(schema_text, content)` re-renders byte-identically with no `app.yaml`. Test: `PydanticSQLModelProvider.is_in_sync` returns `True` for an in-sync `deployed` `settings.py` with a `ProviderContext` resolving `schema.prisma` but **no** `app.yaml`.
- **R1-S4 (golden fixtures):** create and check in an `installed` golden tree AND a `deployed` golden tree under `tests/.../fixtures/`; CI asserts regenerate == golden byte-for-byte (the R4 keystone is otherwise asserted-not-tested). This is the M0 regression artifact.
- **R1-S6 (db.py↔settings contract gate, HAYAI):** extend `gates.py` to assert at **generation time** that db.py imports the exact symbols settings.py exports (`DEPLOYMENT_MODE`, pool accessor, create_all gate) — a settings rename otherwise breaks db.py only at app boot, not at `generate`/`--check`. Gate test: mutate a settings export name → gate fails at generation.
- **R1-S7 (directional fail-closed):** `render_settings()`'s FR-CFG-4 runtime validation must implement the directional rule — env `deployed` vs `installed`-binary → refuse to start (non-zero); reverse → warn. Runtime test asserts the exit codes.
- Other tests: idempotency per mode (installed == golden = regression guard; deployed in_sync); per-row coherence-matrix severity; wireframe output incl. the two auth advisories; reference-auth-seam-unreplaced gate (FR-IDN-2 marker).

## 4. Work Breakdown — Tier B (increment 2, deferred)

### Step B1 — Tenant declaration (OQ-2)
- `deployment.tenant: { model: User, owner_field: owner_id }` in app.yaml; validate the referenced model/field exist in the schema; **no synthesis**.

### Step B2 — Scoped queries (FR-TEN-2/3, D8)
- `render_routers()` + per-entity htmx templates: thread an owner predicate into list/detail/update/delete query paths via the principal dependency.
- This widens the backend drift input set to include `tenant` config → follow the `completeness_text` threading precedent in `_renderers()`.

### Step B3 — Isolation tests (FR-TEN-3)
- Extend route smoke/contract tests: a cross-principal read MUST be denied.

---

## 5. Sequencing & Milestones

1. **M0 — manifest + settings + regression** (A1, A2, A9-regression): mode declared, `installed` output byte-identical to today, `deployed` emits settings.py. Proves the determinism spine.
2. **M1 — operational posture** (A3, A4, A5, A7, A8): persistence/bind/secrets/observability defaults + coherence guard + wireframe. The "operationally deployable" slice, almost all runtime.
3. **M2 — auth seam** (A6): deployed-mode auth scaffold + seam.
4. **M3 (later) — Tier B tenancy** (B1–B3): the one heavy structural increment, behind explicit declaration.

Pilot recommendation (OQ-7): ship **M0+M1** as the deterministic v1 pilot on `backend_codegen`; M2 close behind; M3 separately.

---

## 6. Risks

- **R1 — Drift input widening (D1).** Teaching the backend drift/skip-hook to read `app.yaml` for the one mode-varying file (settings.py) is the riskiest cross-cut; mitigate by keeping settings.py the *only* byte-varying file and having db.py/main.py read it at runtime.
- **R2 — Shipping insecure auth (D7).** Mitigate by scaffolding a seam, not a credential store; mark non-production; lean on `user_routers.py`.
- **R3 — Tenancy correctness (D8).** Server-side enforcement + denial tests; defer to M3 so v1 isn't blocked.
- **R4 — Installed regression.** M0 must prove `installed` == today byte-for-byte before anything else — now backed by a checked-in golden tree (R1-S4), not just an assertion.
- **R5 — Auth without isolation (R1-S2/R1-F2).** The M2-before-M3 window authenticates without row-scoping (horizontal priv-esc that looks safe). Mitigate by the FR-CFG-5 WARN + emitted banner + wireframe advisory; do not let a `deployed`+auth+no-tenant build pass silently.
- **R6 — Drift invisibility (R1-S5).** If `deployment_mode` is not in the scaffold manifest SHA, mode-differing Dockerfiles collide on one hash. Mitigate by the explicit hash-coverage test in A4.

---

*Plan v1.0 — paired with Requirements v0.3. Discoveries D1–D10 fed Requirements §0 (v0.2); CRP R1
suggestions R1-S1..S7 all applied (Appendix A) and reflected in Steps A2/A4/A7/A9 + Risks R5/R6 (v0.3).*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Skip-hook can't re-derive baked mode; self-embed mode + `mode_sha` or `--check`-only | CRP R1 | **Applied** → Step A2 + A9 rewritten: `render_settings()` self-embeds `# startd8-mode:`/`mode-sha256:` (ai-agent-spec precedent); test asserts `is_in_sync` true with no `app.yaml`. Mirrors req FR-CFG-7a. | 2026-06-11 |
| R1-S2 | Guard `deployed`+auth+no-tenant (WARN + wireframe banner) | CRP R1 | **Applied** → Step A7 WARN row + A8 advisory; Risk R5 added. Mirrors req FR-IDN-4. | 2026-06-11 |
| R1-S3 | Replace A7 "e.g." with normative severity matrix | CRP R1 | **Applied** → A7 points to the FR-CFG-5 matrix; per-row severity tests. | 2026-06-11 |
| R1-S4 | Name a checked-in golden-tree fixture for R4/M0 | CRP R1 | **Applied** → A9 adds installed + deployed golden trees, CI byte-diff; this is the M0 regression artifact. | 2026-06-11 |
| R1-S5 | Verify `deployment_mode` is in the scaffold Dockerfile SHA | CRP R1 | **Applied** → A4 "Verify" became a concrete hash-coverage task + test; Risk R6 added. | 2026-06-11 |
| R1-S6 | Generation-time db.py↔settings.py interface gate (HAYAI) | CRP R1 | **Applied** → A9 `gates.py` extension; gate test on a settings rename. | 2026-06-11 |
| R1-S7 | Plan must pin directional fail-closed for FR-CFG-4 | CRP R1 | **Applied** → A2 + A9 directional rule; runtime exit-code test. Mirrors req FR-CFG-4/R1-F5. | 2026-06-11 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-11

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-11 17:56:55 UTC
- **Scope**: Adversarial dual-document review weighted on the three sponsor focus boundaries — (1) determinism spine vs schema-only skip-hook; (2) deployed auth-seam-without-tenancy topology; (3) coherence-guard completeness. Plan (S-prefix) stream.

##### Executive summary (top risks / gaps)

- **Blocking:** The determinism spine in Step A2/A9 understates the cross-cut. `provider.is_in_sync` → `owned_file_in_sync(schema_text, content)` (drift.py:271) passes **only** `schema_text`; the `completeness_text`/`forms_text` precedent A2 leans on is threaded **only into the full `--check` path**, never into `owned_file_in_sync`. So the skip-hook cannot re-derive the baked mode for `settings.py` without reading `app.yaml` — exactly the R1/R6 risk, but Step A2's "register it in `drift._renderers()`" does not by itself close the skip-hook gap.
- **Blocking:** Step A6 (auth seam, M2) ships authentication before Step B2 (tenant scoping, M3), so a deployed app can authenticate users while every query stays global — false multi-user safety. Not surfaced in §6 Risks.
- **High:** Step A7 coherence guard is specified by example ("e.g.") with no severity table; A7 and the requirements disagree on whether `deployed`+loopback and env-vs-baked mismatch are errors or warnings.
- **High:** No regression-fixture artifact is named for R4/M0 ("`installed` == today byte-for-byte"); without a checked-in golden tree the spine's keystone claim is untestable in CI.
- **Medium:** Step A4 changes Dockerfile bytes by mode but asserts "scaffold drift already hashes the manifest … Verify" — the verification is deferred, not planned; if the manifest SHA does not actually cover `deployment_mode`, installed/deployed Dockerfiles collide on the same hash.
- **Medium:** `settings.py` is read by `db.py` at runtime (A3) but A3 also says db.py "bytes unchanged by mode" — yet if `settings.py` import path or symbol names are wrong, db.py breaks silently with no generation-time gate; no gate asserts the db.py↔settings.py contract.

##### Plan Suggestions (S-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | critical | Step A2/A9 must add an explicit skip-hook task: teach `owned_file_in_sync` (or a `python-settings`-specific branch) to re-derive mode from the `settings.py` **self-embedded** mode constant + `mode_sha` header, so `provider.is_in_sync` verifies it **without** reading `app.yaml`; OR consciously exclude `python-settings` from `owns()` and verify it only via `--check`. Name which. | A2 says "register it in `drift._renderers()`" but `_renderers()` feeds `check_drift` (full CLI), not `owned_file_in_sync` (skip-hook). The skip-hook passes only `schema_text`; mode is not in the schema. As written, M0's "proves the determinism spine" claim is unverified for the actual $0.00-skip path. | Step A2 and Step A9 (add skip-hook subtask) | Test `PydanticSQLModelProvider.is_in_sync` returns `True` for an in-sync `deployed` `settings.py` with a `ProviderContext` that resolves `schema.prisma` but **no** `app.yaml`. |
| R1-S2 | Security | high | Add a Tier-A guard task: when `deployment.mode: deployed` and the auth seam is emitted (A6) but no `deployment.tenant` block exists (B1 deferred), the coherence guard (A7) emits a loud WARNING and the wireframe (A8) prints "authenticated, NOT tenant-isolated." | M2 precedes M3 (§5), so the pilot window ships auth without row-scoping. Without a guard, a deployed app presents `require_principal` (looks safe) while all queries are global — horizontal priv-esc. §6 R2 only covers "insecure auth mechanism," not "auth without isolation." | Step A7 (extend combos) and Step A8 (wireframe line); add R5 to §6 Risks | Generate deployed app, auth on, no tenant; assert build WARNING + wireframe banner; assert no ERROR (single-owner deployed is legal). |
| R1-S3 | Risks | high | Replace Step A7's "e.g." combo list with a normative severity matrix (combo → ERROR/WARN/OK) covering: `installed`+Postgres-DSN, `deployed`+SQLite-file-DSN, `deployed`+`migrations:false`, `deployed`+loopback-bind, `deployed`+auth-without-tenant, env-vs-baked mismatch. Pin each severity. | A7 currently lists three examples with no severities; FR-CFG-5/OQ-6/FR-NET-1/FR-CFG-4 disagree on warn-vs-error. An implementer cannot build the guard from examples, and inconsistent severities will diverge from the requirements. | Step A7 (replace prose with table) | One build test per matrix row asserting exact exit code / log level / message. |
| R1-S4 | Validation | high | M0 (§5) must name a **checked-in golden-tree fixture** for the `installed`==today regression (R4) and a `deployed` golden tree, both byte-asserted in CI, before A3–A8 land. | §5 M0 and §6 R4 assert "byte-for-byte == today" as the keystone but no plan step creates or stores the golden artifact; "regression guard" in A9 is unscoped. Without a frozen fixture the spine claim is asserted, not tested. | Step A9 / §5 M0 (add fixture subtask) | CI diff of regenerated `installed` tree vs committed golden = empty; same for `deployed`. |
| R1-S5 | Ops | medium | Step A4 must replace "scaffold drift already hashes the manifest … Verify" with a concrete check that `AppManifest.deployment_mode` is actually included in the scaffold manifest SHA that lands in the Dockerfile header — and add a test that installed vs deployed Dockerfiles produce **different** drift hashes. | If the manifest SHA does not cover the new `deployment_mode` field, two mode-differing Dockerfiles hash identically and `--check` cannot detect a mode flip on the container shape — a silent drift hole (violates FR-DET-1 "no mode-dependent output may be invisible to drift"). | Step A4 (turn "Verify" into a task) | Generate installed + deployed; assert the two Dockerfiles' embedded scaffold SHAs differ and `--check` flips on mode change. |
| R1-S6 | Interfaces | medium | Add a generation-time gate (Step A9 / `gates.py`) asserting the `db.py`↔`settings.py` contract: db.py imports the exact symbols settings.py exports (`DEPLOYMENT_MODE`, pool accessor, create_all gate). A3 makes db.py depend on settings at runtime but keeps db.py byte-frozen, so a settings rename breaks db.py with no generation-time signal. | A3 deliberately freezes db.py bytes and routes mode through a runtime import; a drift in the settings interface would only surface at app boot, not at `generate`/`--check` time, undercutting HAYAI (don't defer enforcement). | Step A9 (gates.py extension) | Gate test: mutate a settings export name; assert the gate fails at generation, not at runtime. |
| R1-S7 | Architecture | medium | Step A2's FR-CFG-4 runtime validation ("warn / refuse") must specify the **directional fail-closed rule** in the plan: env claims `deployed` but binary is `installed`-shaped → refuse to start; reverse → warn. Mirror requirements R1-F5. | A2 carries the same undecided "warn / refuse" as FR-CFG-4. The dangerous direction (env expects isolation the installed binary lacks) must fail-closed; leaving it to implementer discretion risks a silent security downgrade. | Step A2 (FR-CFG-4 bullet) | Runtime test: installed app + `STARTD8_DEPLOYMENT_MODE=deployed` exits non-zero. |

##### Endorsements & Disagreements

- No prior untriaged rounds exist (Appendix C was empty before R1) — no endorsements or disagreements to record.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirements section/FR to the plan step(s) that address it. Coverage: **Covered** (full, clear steps) / **Partial** (mentioned, detail/edge-case missing) / **Gap** (not addressed).

| Requirement (FR / section) | Plan Step(s) | Coverage | Notes / Gap |
| ---- | ---- | ---- | ---- |
| FR-CFG-1 declared mode enum | A1 | Covered | manifest parse + enum validate. |
| FR-CFG-2 single source of truth | A1 (shared accessor) | Covered | shared `deployment_mode` accessor named. |
| FR-CFG-3 gen-time vs runtime split | §2 + §8 table | Covered | classification explicit. |
| FR-CFG-4 runtime mode signal / env validate | A2 | Partial | "warn/refuse" undecided — directional fail-closed rule unspecified (R1-S7/R1-F5). |
| FR-CFG-5 coherence guard | A7 | Partial | "e.g." examples, no severity matrix; missing loopback + auth-without-tenant (R1-S3/R1-F3). |
| FR-CFG-6 wireframe visibility | A8 | Covered | mode + per-dimension posture printed. |
| FR-CFG-7 emitted `settings.py` (single byte-varying) | A2, A9 | Partial | skip-hook re-derivation of baked mode unspecified — the load-bearing gap (R1-S1/R1-F1). |
| FR-PER-1 installed SQLite/WAL | A3 | Covered | pragmas under existing dialect branch. |
| FR-PER-2 deployed pool sizing | A3 | Covered | runtime read from settings. |
| FR-PER-3 create_all gate | A3 | Covered | runtime gate in `init_db()`. |
| FR-IDN-1 installed no auth | A6 | Covered | nothing emitted. |
| FR-IDN-2 deployed auth seam | A6 | Partial | "not-production" marker not machine-detectable; no auth-without-isolation guard (R1-F4/R1-F2). |
| FR-IDN-3 policy not generated | A6 | Covered | seam to `user_routers.py`. |
| FR-TEN-1/2/3 tenancy | B1–B3 | Partial (deferred) | Tier B; deferral leaves M2–M3 window unsafe — no warning planned (R1-S2/R1-F2). |
| FR-CON-1 concurrency | A3 | Covered | pool config when deployed. |
| FR-NET-1 bind default by mode | A4 | Partial | `deployed`+loopback coherence severity unassigned (R1-S3). |
| FR-NET-2 container shape | A4 | Partial | Dockerfile mode-hash inclusion unverified ("Verify" deferred, R1-S5). |
| FR-SEC-1 secrets default by mode | A5 | Covered | reuses `secrets/` switch. |
| FR-DAT-1 data lifecycle | A3 (createall/Alembic) | Partial | backup/retention seams only referenced, not stepped. |
| FR-OBS-1 observability posture | A5 | Covered | OTel default, orthogonal axis. |
| FR-DET-1 mode hashed input | A2, A9 | Partial | skip-hook vs `--check` divergence makes "no invisible mode output" unproven (R1-S1/R1-S5). |
| FR-DET-2 idempotency per mode | A9, §5 M0 | Partial | no checked-in golden fixture named (R1-S4). |
| FR-DET-3 new owned kinds registered | A9 | Covered | `python-settings`, `python-auth-seam` registered. |
| FR-DET-4 gates extended | A9 | Partial | gates assert mode constant; db.py↔settings interface gate missing (R1-S6); reference-auth gate missing (R1-F4). |
| FR-CLI-1 honor declared mode | A1, A7 | Covered | no new flag; app.yaml source of truth. |
| FR-CLI-2 wireframe surfaces mode | A8 | Covered | — |
| §6 Acceptance (skip-hook $0.00 path) | (none) | Gap | acceptance proves `--check` in_sync but not `provider.is_in_sync` skip path (R1-F6). |
