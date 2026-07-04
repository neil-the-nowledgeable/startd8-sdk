# OpenAPI Role 1 — Static API Contract Artifacts (Requirements)

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-18
**Status:** Planned against `backend_codegen`; ready for CRP / implementation
**Owner:** SDK / backend_codegen
**Motivated by:** `OPENAPI_LEVERAGE_ANALYSIS.md` Role 1 — make the API contract a first-class $0
artifact instead of a runtime-only byproduct
**Paired plan:** `OPENAPI_ROLE1_PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real `backend_codegen`
> pipeline, `boot_smoke`, and `deploy_harness/smoke.py`. **7 corrections** — past the 30% bar, so
> v0.1 was appropriately premature.

| v0.1 assumption | Planning discovery | Impact |
|---------------|-------------------|--------|
| Snapshot **live** `/openapi.json` as the owned artifact | Offline `--check` must not boot the app; every other owned artifact uses static re-render + byte-compare (`drift.py`) | FR-1/FR-2: emit a **schema-projected static contract**; runtime `/openapi.json` is a **conformance check** (boot-smoke), not the drift source |
| Pure `openapi.json` on disk | `# GENERATED` drift headers are Python/comment-based (`_headers.py`); JSON has no comment header slot | FR-1: primary artifact is **`app/openapi_contract.py`** exporting `ROUTE_MANIFEST` + `OPENAPI_SPEC` dicts; optional `openapi.json` export is a **write-only convenience**, not separately drift-tracked |
| Typed **TypeScript** client is v1 | Architecture is Python-first (`IDEAL_TARGET_ARCHITECTURE`); TS is an escape hatch | FR-6 **deferred** to Phase 1d; v1 ships Python `httpx` stub only if Phase 1c lands in same increment |
| Mock server / Prism is v1 | `deploy_harness/smoke.py` already round-trips against a **live** server; mock adds dep + duplicate surface | FR-7 **removed** from v1 (non-goal) |
| OpenAPI schema resolution must be built fresh | `deploy_harness/smoke.py` already implements `$ref`/`allOf`/body synthesis (FR-9) — 300+ lines, unit-tested | FR-8: **extract** to `startd8/openapi_contract/schema_resolve.py` in Phase 2; v1 emitter is schema-driven, not spec-parser-driven |
| `boot_smoke` already validates routes | `run_boot_smoke()` accepts `expected_routes` but **`cli_generate` and postmortem never pass it** — only a unit test does | FR-4 is a **confirmed quick win**: wire manifest → `expected_routes` with ~10 lines |
| Full FastAPI OpenAPI parity required | CRUD paths are fully determined by `render_routers` (`/{entity}/`, `/{entity}/{id}`); optional surfaces (AI, pages, flows) are **conditionally emitted** like `assembler` | FR-3: v1 spec covers **schema-derived CRUD + health**; optional surfaces added only when the same manifest inputs that trigger their emission are present |
| Default-on is obvious | Default-on changes every app's artifact tree (like health endpoint's `fastapi-main` churn) | OQ-1 → **default-on** (applicational completion; one regen is cheap) — same call as health endpoint OQ-2 |

**Resolved open questions:**
- **OQ-1 → Default-on.** API contract artifacts emit for every `generate backend` run; existing apps
  drift until regenerated (accepted cost).
- **OQ-2 → Conformance, not identity.** Static `OPENAPI_SPEC` must match live `/openapi.json` on
  **paths + methods** for schema-derived routes; framework metadata (tags, operationId) is
  best-effort, checked by contract tests not byte-equality to live spec.
- **OQ-3 → `openapi-spec-validator` optional gate.** Run during `--gate` only; absent ⇒ `unavailable`
  ⇒ non-pass (never silent PASS).
- **OQ-4 → Single module, multiple exports.** `ROUTE_MANIFEST` (tuple list for boot-smoke) and
  `OPENAPI_SPEC` (dict for external tooling) live in one owned file to minimize drift surface.

**Quick wins surfaced by planning (not evident pre-plan):**
1. **Auto-wire `boot_smoke` `expected_routes`** — immediate C-6 strengthening, no new user-facing concept.
2. **Route manifest alone** (Phase 1a) delivers ~70% of Role 1 value before OpenAPI dict or client exist.
3. **Contract test comparing `app.routes` to `ROUTE_MANIFEST`** reuses `test_emitter`'s TestClient pattern — catches hand-edited routers without parsing OpenAPI at all.

---

## 1. Problem Statement

Generated all-Python apps (`startd8 generate backend`) produce a FastAPI OpenAPI document at
runtime (`GET /openapi.json`), but the SDK never **materializes, owns, or drift-checks** that
contract offline. Downstream consumers re-derive API knowledge independently:

| Component | Current state | Gap |
|-----------|--------------|-----|
| Drift / `--check` | Tracks `.py` spine files against Prisma | No check that the **public API surface** matches the schema projection |
| `boot_smoke` (C-6) | Asserts `/openapi.json` serves; `expected_routes` optional | Expected routes **never auto-derived** — misses route-regression class |
| `deploy_harness/smoke` | Parses **live** spec for CRUD round-trip | Logic is harness-local; no shared owned contract |
| Typed client (documented promise) | Unimplemented | IDEAL_TARGET_ARCHITECTURE §4 escape hatch unrealized |
| Prime skip-hook | Owns `.py` artifacts | No API-contract artifact to skip against for integration glue |

The API contract is **applicational completion** (bucket 1 — deterministic, $0 LLM): derivable from
the same Prisma keystone that already drives `render_routers`.

---

## 2. Goals & Non-Goals

**Goals**
- Emit an owned, drift-checkable **static API contract** from the Prisma schema (+ existing optional
  manifests), $0 LLM.
- Auto-wire `boot_smoke` with schema-derived expected routes.
- Add contract tests that catch router/surface drift before runtime smoke.
- Preserve SOTTO: conditional surfaces mirror `assembler` emission rules exactly.
- Optional: minimal OpenAPI 3.0 dict + Python `httpx` client stub (Phase 1c/1d).

**Non-Goals (v1)**
- Snapshotting live `/openapi.json` as the drift source of truth.
- Mock server / Prism / WireMock generation.
- TypeScript client generation (deferred).
- Full FastAPI OpenAPI parity (framework metadata, every optional mount).
- OpenAPI-as-input / brownfield (Role 2).
- Inter-context client promotion (Role 3).

---

## 3. Requirements

### Static contract emission
- **FR-1** Emit **`app/openapi_contract.py`** as an owned artifact (kind `python-openapi-contract`)
  containing:
  - `ROUTE_MANIFEST: tuple[tuple[str, str], ...]` — sorted `(method, path)` pairs projected from the
    schema (+ conditionally from the same manifest inputs `assembler` uses: health always; pages/AI/
    flows/editors/imports only when their manifest is present).
  - `OPENAPI_SPEC: dict[str, Any]` — a minimal OpenAPI 3.0.3 document covering the same route set,
    with `components.schemas` reusing the entity Create/Read/Update model names from the generated
    spine.
  Provenance via `header_standard` + `schema-sha256`; byte-stable on regen.
- **FR-2** Register the artifact in `CANONICAL_LAYOUT`, `assembler.render_backend()`, and
  `drift._renderers()` following the `health_renderer` / `derived.render_export` precedent.
  Schema-only kind → default drift re-render path; `provider.py` unchanged.

### Surface projection rules
- **FR-3** v1 **mandatory** routes in the manifest:
  - CRUD: for each entity with a single-column PK — `GET/POST /{entity}/`, `GET/PATCH/DELETE
    /{entity}/{item_id}`; for keyless entities — `GET/POST /{entity}/` only (mirrors
    `crud_generator._entity_block`).
  - Health: `GET /health`, `GET /health/live` (always emitted since health is default-on).
  - **Conditional** (only when the triggering manifest is present during generation):
    - Pages nav/router paths when `pages.yaml` given.
    - AI router paths when `ai_passes.yaml` given.
    - Flow/editor/import-surface paths when `views.yaml` / `imports.yaml` declare them.
  Tenant-scoped path prefixes follow the same `tenant_owner_field` rules as `render_routers`.

### Consumer wiring
- **FR-4** `validators/boot_smoke.run_boot_smoke()` MUST import `ROUTE_MANIFEST` from the generated
  module (when the file exists) and pass it as `expected_routes` (path strings only). Missing file ⇒
  today's behavior (no expected-route check). `cli_generate backend --boot-smoke` benefits without new
  flags.
- **FR-5** Emit **`tests/test_openapi_contract.py`** (kind `python-tests-openapi-contract`) asserting:
  - Every `(method, path)` in `ROUTE_MANIFEST` is served by the mounted app (TestClient / route walk).
  - No schema-derived CRUD path is missing from the manifest (bidirectional for the schema-derived
    subset — catches emitter bugs).
  - `OPENAPI_SPEC["paths"]` keys match the manifest path set.

### Gate / validation
- **FR-6** When `startd8 generate backend --gate` is used, validate `OPENAPI_SPEC` with
  `openapi-spec-validator` if installed; result `unavailable` if not installed ⇒ **non-pass** (never
  silent PASS). Validation failure ⇒ exit 2.
- **FR-7** *(Phase 1d — same increment if low risk)* Emit **`clients/http_client.py`** (kind
  `python-openapi-client`) — a minimal typed `httpx` wrapper with one function per schema-derived
  CRUD operation. Deferred if Phase 1c spec shape churns during implementation.

### CLI / UX
- **FR-8** `startd8 generate backend` emits contract artifacts **by default** (no new flag). Existing
  apps show drift on `--check` until regenerated (accepted; same as health endpoint).
- **FR-9** Optionally write `openapi.json` (pretty-printed `OPENAPI_SPEC`) alongside the app when
  `--export-openapi` is passed — convenience export only; drift authority remains
  `app/openapi_contract.py`.

### Harness alignment
- **FR-10** `deploy_harness/smoke.select_crud_resource()` SHOULD succeed on the static
  `OPENAPI_SPEC` for a wireframe-generated app (unit test with the emitted spec dict — no server).
  Proves the static spec is smoke-harness-compatible.

---

## 4. Non-Requirements

- Business logic in endpoint handlers.
- Auth scheme modeling beyond `optional` (v1).
- WebSocket/event surface.
- Generating the Prisma schema from OpenAPI (Role 2).
- Committing `openapi.json` as the canonical owned file.

---

## 5. Open Questions (remaining)

- **OQ-5** Should `render_main` gain an explicit `from .openapi_contract import OPENAPI_SPEC` mount
  hook, or is export-only sufficient for v1? *(Lean: export-only; FastAPI already builds live spec.)*
- **OQ-6 → Resolved (2026-07-04).** `components.schemas` uses the shared `schema_contract` CRUD
  subset (Create/Read/Update); OpenAPI contract renderer imports `object_schema` / `model_names` —
  zero duplicate resolver.

---

## 6. Success Metrics

| Metric | Target |
|--------|--------|
| Drift check catches hand-edited `routers.py` path | `--check` fails via `test_openapi_contract` or manifest mismatch |
| Boot-smoke route coverage | Zero manual `expected_routes` in CLI/postmortem paths |
| Cost | $0 LLM; skip-hook recognizes owned kinds |
| Regression | Full `backend_codegen` test suite green; ruff/black clean |

---

*v0.2 — Post-planning self-reflective update. 3 requirements deferred/removed (live snapshot, mock
server, TS client), 4 added (static emitter, boot_smoke wiring, bidirectional contract test, harness
compat test), 4 open questions resolved.*
