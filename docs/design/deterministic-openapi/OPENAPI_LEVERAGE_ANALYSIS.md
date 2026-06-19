# OpenAPI Leverage for Deterministic Generation — Design Analysis

**Date:** 2026-06-18
**Status:** Strategy / design analysis (charter-level; Role 1 requirements + plan are paired siblings)
**Builds on:**
`deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`,
`IDEAL_TARGET_ARCHITECTURE.md`
**Paired docs:** `OPENAPI_ROLE1_REQUIREMENTS.md`, `OPENAPI_ROLE1_PLAN.md`

> **Thesis.** Generated FastAPI apps already *produce* OpenAPI at runtime (`GET /openapi.json`), and
> two SDK subsystems already *consume* that live document (`validators/boot_smoke.py`,
> `deploy_harness/smoke.py`). The unrealized leverage is making the API contract a **first-class,
> deterministic, $0-owned artifact** projected from the same Prisma keystone — so drift, tests,
> clients, and harness gates share one offline source of truth instead of re-deriving paths ad hoc
> at boot time.

---

## 1. Current state

### 1.1 The generation pipeline (single direction)

```
prisma/schema.prisma  ──($0 deterministic)──▶  models ▸ tables ▸ routers ▸ main ▸ HTMX ▸ derived
        │                                              │
        │                                              └── FastAPI serves /openapi.json at runtime
        │                                                   (byproduct — not consumed by codegen)
        └── optional manifests (views/pages/ai_passes/imports/…) conditionally widen the spine
```

`backend_codegen/assembler.py` projects one schema (+ optional manifests) into the full app spine.
Every CRUD path, response model, and router mount is **mechanically derivable** from that input —
the same property that makes Pydantic models and route smoke tests deterministic today.

### 1.2 Where OpenAPI is already used (runtime-only)

| Consumer | What it does | Limitation |
|----------|--------------|------------|
| `validators/boot_smoke.py` | Boots app in subprocess; asserts `/openapi.json` returns 200; optionally checks `expected_routes` | `expected_routes` is **never auto-populated** in `cli_generate` or postmortem — only manual in tests |
| `deploy_harness/smoke.py` | Fetches **live** `/openapi.json`; selects a list+create resource; synthesizes POST body via `$ref`/`allOf` resolution; round-trips CRUD | Requires running server; logic is harness-local, not reusable as an owned artifact |
| `deploy_harness/server.py` | Probes `/health` → `/openapi.json` → `/` for liveness | Framework liveness only — not a contract gate |
| `backend_codegen/ai_layer.py` tests | Assert `/openapi.json` survives AI edge cases | Runtime assertion, not offline contract |

**Gap:** OpenAPI is a **runtime probe surface**, not an **owned contract layer**. The SDK generates
the code that *implies* a spec, but never materializes, drift-checks, or reuses that spec offline.

### 1.3 What the charter already promised

`DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` §2(a) lists OpenAPI as a generalization target
alongside protobuf/gRPC. `IDEAL_TARGET_ARCHITECTURE.md` §4 states that FastAPI auto-generates
OpenAPI and that a typed client is "generated for free" if a rich-client surface is needed. That
promise is **documented but unimplemented**.

---

## 2. Three roles OpenAPI can play

### Role 1 — OpenAPI as an **output** consumed by new $0 generators *(this doc's implementation scope)*

Treat the API contract as a **derived artifact** — sibling to `app/export.py`, `app/ai_schemas.py`,
and `tests/test_contract.py`. New deterministic emitters project a static contract from the Prisma
schema (+ the same optional manifests `assembler` already threads). Consumers:

| Capability | Value | Determinism |
|------------|-------|-------------|
| **Static route/path manifest** | Auto-wire `boot_smoke` `expected_routes`; strengthen C-6 gate | Schema-only projection; no runtime boot for drift |
| **Minimal static OpenAPI document** | Drift-checkable public API surface; external tooling input | Projected subset (CRUD + health + declared optional surfaces) |
| **OpenAPI contract tests** | Assert served paths match the owned manifest (catches router drift) | Extends `test_emitter.py` pattern |
| **Typed client stub** | Python `httpx` client for inter-context / escape-hatch JS later | Generated from static spec, not live fetch |
| **Harness reuse** | Extract `deploy_harness/smoke.py` schema resolution into shared module | Same `$ref`/`allOf` logic, two call sites |

**Why static projection, not live snapshot?** Planning against the real pipeline shows that
snapshotting live `/openapi.json` during `generate --check` would require booting the app (deps,
subprocess, non-deterministic ordering) — violating the offline drift model every other owned
artifact uses. FastAPI's full OpenAPI builder also encodes framework details ($ref naming, tag
ordering) that are **not** stable projection targets. The correct primitive is a **schema-derived
static emitter** (like `render_routers`), with runtime `/openapi.json` as a **conformance check**
at gate time (boot-smoke), not the source of truth.

### Role 2 — OpenAPI as an **input** contract *(deferred — larger design lift)*

Accept OpenAPI (or an `api.yaml` overlay) as a sibling source-of-truth to Prisma for **endpoint
surface** — non-CRUD routes, auth schemes, pagination, error envelopes. Enables brownfield
onboarding and raises the deterministic ceiling for LLM-authored endpoints. Requires explicit
two-contract reconciliation (Prisma = data, OpenAPI = surface). See §5 open questions.

### Role 3 — OpenAPI as the **inter-context seam** *(shipped on `main` — v0.3)*

When a bounded context splits from the modular monolith (`IDEAL_TARGET_ARCHITECTURE` §6), the
in-process Pydantic contract promotes to a served OpenAPI spec and the SDK generates the consuming
context's typed client. Shipped path: `prisma/contexts.yaml` → `clients/{id}_client.py` +
`app/context_clients.py` (P2) + cross-context smoke + pinned-contract filtering for divergent
schemas (M5). Python-homogeneous services use OpenAPI; polyglot uses gRPC/proto (`ProtoStubProvider`).

**Docs:** `OPENAPI_ROLE3_REQUIREMENTS.md` (v0.3), `OPENAPI_ROLE3_PLAN.md`, fixtures under
`docs/design/deterministic-openapi/fixtures/{two-app-seam,cross-repo-seam}/`.

---

## 3. Architectural fit (additive, not a rewrite)

```
prisma/schema.prisma (+ optional manifests)
        │
        ├── existing spine (models, routers, HTMX, …)     [$0, owned, drift-checked]
        │
        └── NEW: openapi_codegen layer
                ├── app/openapi_contract.py   (static SPEC dict + ROUTE_MANIFEST)
                ├── tests/test_openapi_contract.py
                └── (optional) clients/python_client.py
                        │
                        ├── drift.py _renderers() registration
                        ├── assembler.py emit (conditional on manifest / default-on TBD)
                        ├── PydanticSQLModelProvider owns() unchanged (header-based)
                        └── boot_smoke reads ROUTE_MANIFEST → expected_routes
```

| Existing seam | OpenAPI Role 1 plugs in |
|---------------|-------------------------|
| `DeterministicFileProvider` + registry | New artifact kinds in `drift._renderers()`; same `PydanticSQLModelProvider` |
| Provenance headers (`_headers.py`) | `header_standard` on `.py` contract module (JSON-in-Python pattern) |
| `test_emitter.py` | New `render_openapi_contract_tests()` |
| `validators/boot_smoke.py` | Import `ROUTE_MANIFEST` from generated module when present |
| `deploy_harness/smoke.py` | Future: import shared `openapi_schema` resolution module |
| SOTTO (absent ⇒ byte-identical) | Default-on vs opt-in is a product call — see Role 1 requirements OQ-1 |

---

## 4. Sequencing recommendation

| Phase | Deliverable | Rationale |
|-------|-------------|-----------|
| **1a** | `render_api_manifest` + drift + boot_smoke wiring | Highest leverage, lowest risk; fixes a real gap (`expected_routes` never auto-populated) |
| **1b** | `render_openapi_contract_tests` | Extends proven `test_emitter` pattern; catches router/surface drift |
| **1c** | Minimal static OpenAPI 3.0 emitter (`OPENAPI_SPEC` dict) | Enables external tooling + future client gen |
| **1d** | Python `httpx` typed client emitter | Fulfills IDEAL_TARGET_ARCHITECTURE §4 escape hatch |
| **2** | Extract shared schema-resolution from `deploy_harness/smoke.py` | DRY for harness + codegen |
| **3** | Role 2 (OpenAPI-as-input) | ✅ Shipped — `api.yaml` overlay merge |
| **4** | Role 3 (inter-context promotion) | ✅ Shipped on `main` (M0–M5 + P2) — `OPENAPI_ROLE3_*`, `scripts/openapi_role3_{m4,m5}_smoke.sh` |

---

## 5. Risks and non-goals

**Non-goals (Role 1)**
- Business-logic endpoint bodies (bucket 3 / LLM scope).
- Mock server generation (deploy harness already does live smoke; mock is redundant in v1).
- Full FastAPI OpenAPI parity (tags, duplicate operationIds, framework `$ref` naming).
- OpenAPI-as-input / brownfield (Role 2).

**Risks**
- **Conditional surfaces:** optional manifests (AI, pages, flows, imports) change the route set —
  the static emitter must mirror `assembler`'s conditional emission exactly or drift lies.
- **JSON without `# GENERATED` headers:** pure `.json` files don't fit the drift header model;
  the Python-dict-in-`.py` pattern (`ai_schemas` precedent) avoids this.
- **Spec validity gate:** `openapi-spec-validator` adds a dependency; gate must fail loud when
  absent (same rule as `ts_toolchain` / boot-smoke `unavailable`).

**Open questions (cross-role)**
- **OQ-A:** Default-on emission (like health endpoint) vs opt-in `openapi.yaml` manifest?
- **OQ-B:** How much of FastAPI's live `/openapi.json` must the static spec match? (Answer for v1:
  paths + methods + core schemas for CRUD entities; framework metadata best-effort.)
- **OQ-C:** Parser reuse for Role 2 — `openapi-spec-validator` + loader vs bespoke?

---

## 6. Success criteria

Role 1 is successful when:

1. `startd8 generate backend` emits an owned, drift-checkable API contract artifact ($0 LLM).
2. `startd8 generate backend --check` catches a hand-edited router path without a schema change.
3. `startd8 generate backend --boot-smoke` auto-asserts schema-derived routes (no manual list).
4. The deploy-harness smoke-CRUD path and the static emitter agree on list+create resource selection
   for a generated wireframe app.
5. No regression to SOTTO: projects without the feature (if opt-in) remain byte-identical.

---

*This analysis informed Role 1–3 implementation. Role 1–3 are shipped on `main`; see
`OPENAPI_ROLE3_NEXT_STEPS.md` for deferred polyglot tracks.*
