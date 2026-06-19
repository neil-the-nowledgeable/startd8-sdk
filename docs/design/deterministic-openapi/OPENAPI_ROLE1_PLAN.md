# OpenAPI Role 1 — Implementation Plan

**Version:** 1.0 (paired with Requirements v0.2)
**Date:** 2026-06-18
**Status:** Planned — pre-implementation

---

## 0. Planning Discoveries (fed §0 of the requirements)

| v0.1 assumed | Planning revealed | Impact |
|--------------|-------------------|--------|
| Live `/openapi.json` snapshot | `drift.py` is 100% offline re-render; boot_smoke is the runtime gate | Static emitter + runtime conformance check; not snapshot-as-SOT |
| `openapi.json` owned file | `# GENERATED` headers don't work on JSON | `app/openapi_contract.py` with dict exports (`ai_schemas` precedent) |
| TS client v1 | Python-first stack; no `frontend_codegen` client path exists | Defer TS; optional Python `httpx` in Phase 1d |
| Mock server v1 | `deploy_harness/smoke.py` already live-round-trips | Removed from scope |
| Build new OpenAPI resolver | `smoke.py` has `_deref`, `resolve_schema`, `synthesize_body`, `select_crud_resource` | Phase 2 extract; Phase 1 emitter is Prisma-driven |
| `expected_routes` already wired | `cli_generate.py:424` calls `run_boot_smoke(str(out))` with **no** routes | Phase 1a quick win |
| Emitter is independent of manifests | `assembler.py` conditionally emits AI/pages/flows/editors/imports | Emitter must accept same optional texts as `render_backend()` |

---

## 1. Files touched (grounded in `health_renderer.py` / `derived.py` / `test_emitter.py`)

### NEW modules
- **`backend_codegen/openapi_contract_renderer.py`**
  - `render_openapi_contract(schema_text, source_file, *, tenant_owner_field, pages_text, manifest_text, views_text, imports_text) -> str`
  - Internal helpers:
    - `_crud_routes(schema, tenant_owner_field) -> list[tuple[str,str]]` — mirrors `crud_generator._entity_block` / `_pk_field` rules
    - `_health_routes() -> [("GET","/health"), ("GET","/health/live")]`
    - `_conditional_routes(...)` — pages/AI/flows/editors/import-surface paths; **empty when manifest absent**
    - `_build_openapi_spec(routes, schema) -> dict` — minimal OAS 3.0.3 (paths, components.schemas for Create/Read/Update)
  - Header: `header_standard(source_file, schema_sha256(schema_text), "python-openapi-contract")`
  - Body exports: `ROUTE_MANIFEST`, `OPENAPI_SPEC`, helper `route_paths() -> list[str]` for boot_smoke

- **`backend_codegen/openapi_contract_tests.py`** (or section in `test_emitter.py`)
  - `render_openapi_contract_tests(schema_text, source_file, **manifest_kwargs) -> str`
  - Kind: `python-tests-openapi-contract`
  - Tests:
    1. `test_route_manifest_matches_app` — walk `app.routes`, compare to `ROUTE_MANIFEST`
    2. `test_manifest_covers_schema_crud` — emitter completeness (no missing entities)
    3. `test_openapi_spec_paths_match_manifest` — `OPENAPI_SPEC["paths"].keys()` vs manifest
  - Reuse `_SHIM` + TestClient pattern from `render_route_smoke_tests`

### MODIFIED modules
- **`crud_generator.py`** — `CANONICAL_LAYOUT["python-openapi-contract"] = "app/openapi_contract.py"`; optional `python-openapi-client` path
- **`assembler.py`** — emit contract module + tests after `fastapi-health`, before UI (contract is API-layer)
- **`drift.py`** — register kinds in `_renderers()`:
  - `"python-openapi-contract": lambda s, sf, e: render_openapi_contract(s, sf, **kwargs)` — kwargs threaded via the same manifest reads `owned_file_in_sync` already does
  - `"python-tests-openapi-contract": lambda s, sf, e: render_openapi_contract_tests(s, sf, **kwargs)`
- **`validators/boot_smoke.py`** — before subprocess boot, try:
  ```python
  from app.openapi_contract import ROUTE_MANIFEST
  expected = [p for _, p in ROUTE_MANIFEST]
  ```
  Import failure ⇒ `expected_routes=None` (backward compatible)
- **`cli_generate.py`** — optional `--export-openapi` writes `out/openapi.json`; `--gate` runs spec validator
- **`backend_codegen/__init__.py`** — export `render_openapi_contract` if package re-exports renderers

### UNCHANGED
- **`provider.py`** — header-based `owns()`; new kinds auto-recognized once in `_renderers()`
- **`deploy_harness/smoke.py`** — Phase 2 extract only; Phase 1 adds unit test importing emitted `OPENAPI_SPEC`

### Phase 1d (optional same PR)
- **`backend_codegen/openapi_client_renderer.py`** — `render_http_client(...) -> str` → `clients/http_client.py`
- One `httpx` function per CRUD op; imports `OPENAPI_SPEC` for path templates

---

## 2. Per-requirement implementation steps

| FR | Step |
|----|------|
| FR-1 | `render_openapi_contract` emits `ROUTE_MANIFEST` + `OPENAPI_SPEC` in one module |
| FR-2 | `CANONICAL_LAYOUT` + `assembler` + `drift._renderers()` registration |
| FR-3 | `_crud_routes` mirrors `_entity_block`; conditional routes behind same `if manifest_text` guards as assembler |
| FR-4 | `boot_smoke.py` imports `ROUTE_MANIFEST`; extract path list |
| FR-5 | `render_openapi_contract_tests` with bidirectional manifest check |
| FR-6 | `cli_generate --gate`: try `openapi_spec_validator.validate(OPENAPI_SPEC)`; catch ImportError → unavailable |
| FR-7 | Phase 1d client renderer (defer if spec unstable) |
| FR-8 | Default emit in `render_backend` — no flag |
| FR-9 | `--export-openapi` pretty-prints JSON to project root |
| FR-10 | Unit test: `select_crud_resource(OPENAPI_SPEC)` returns a resource on wireframe schema output |

---

## 3. Sequencing (milestones)

### M0 — Route manifest only (can ship independently) ⏱ smallest increment
- `render_openapi_contract` with **only** `ROUTE_MANIFEST` (no `OPENAPI_SPEC` yet)
- `boot_smoke` wiring
- Unit tests: manifest paths match `crud_generator` expectations per entity
- **Value:** FR-4 satisfied; C-6 strengthened

### M1 — Full contract module (target MVP)
- Add `OPENAPI_SPEC` dict builder
- `assembler` + `drift` + contract tests (FR-5)
- Golden/drift tests for `app/openapi_contract.py`

### M2 — Gate + export + harness compat
- `--gate` spec validation (FR-6)
- `--export-openapi` (FR-9)
- FR-10 unit test against `select_crud_resource`

### M3 — Python client stub (optional)
- `clients/http_client.py` emitter (FR-7)
- Only if M1 spec is stable

### M4 — Shared resolver extract (follow-on, not blocking)
- Move `deploy_harness/smoke.py` schema resolution → `startd8/openapi_contract/schema_resolve.py`
- Update harness + client emitter to import shared module

---

## 4. Key implementation details

### 4.1 CRUD path projection (must match `render_routers`)

From `crud_generator.py`:
- Router `prefix="/{entity_lower}"` → paths `/{entity}/`, `/{entity}/{item_id}`
- Keyless entity (no PK): list + create only
- Tenant-scoped: same paths (scoping is handler logic, not path shape)

### 4.2 OpenAPI spec minimal shape

```python
{
  "openapi": "3.0.3",
  "info": {"title": "<AppName>", "version": "0.0.0"},
  "paths": {
    "/items/": {
      "get": {"responses": {"200": {"description": "OK"}}},
      "post": {"requestBody": {...}, "responses": {"200": {...}}},
    },
    "/items/{item_id}": { "get": ..., "patch": ..., "delete": ... },
  },
  "components": {
    "schemas": {
      "ItemCreate": {"type": "object", "properties": {...}, "required": [...]},
      "ItemRead": {...},
    }
  },
}
```

Entity field types mapped via existing `_PY_SCALAR` / Prisma parser — **not** via importing generated `models.py` (keeps emitter offline-safe).

### 4.3 Drift threading for conditional routes

`owned_file_in_sync()` already receives `manifest_text`, `pages_text`, `views_text`, `imports_text`.
The openapi contract renderer MUST receive the same kwargs in `drift._renderers()` lambdas — copy the
pattern used for `fastapi-web-forms` / AI kinds. **If kwargs are not threaded, freshly-generated
contract files ERROR → False → fall through to LLM** (the FR-ED-16 lesson).

### 4.4 `boot_smoke` import strategy

Boot smoke runs in a **subprocess** with `project_root` on `sys.path`. The import of
`app.openapi_contract` happens in the **parent** before spawn, reading the file statically:

```python
def _expected_routes_from_project(project_root: str) -> Optional[List[str]]:
    contract = Path(project_root) / "app" / "openapi_contract.py"
    if not contract.is_file():
        return None
    # Parse ROUTE_MANIFEST via ast.literal_eval on the tuple literal, OR
    # exec-module in isolated import — prefer AST extraction to avoid import side effects
```

AST extraction is safer (no `app.main` import chain). Planning insight: **do not import `app` in the
parent process** — use regex/AST on the generated file to extract `ROUTE_MANIFEST` literal.

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Conditional-route drift kwargs not threaded | Copy AI/forms `_renderers()` lambda pattern exactly; add skip-hook test |
| `OPENAPI_SPEC` shape incompatible with `select_crud_resource` | FR-10 unit test in M2 before claiming harness compat |
| `openapi-spec-validator` not in dev deps | `--gate` treats ImportError as unavailable/non-pass; add to `[dev]` optional extra |
| Default-on churn on existing golden trees | Update golden trees in same PR; document FR-8 regen note |
| AST parsing of `ROUTE_MANIFEST` fragile | Emit manifest as a simple literal tuple assigned at module level; test AST extractor |

---

## 6. Test plan

**Unit**
- `render_openapi_contract` byte-stable for wireframe schema
- Per-entity path set matches `crud_generator` expectations
- Conditional routes: absent `ai_passes.yaml` ⇒ no AI paths in manifest
- `owned_file_in_sync` True after fresh render
- AST route extractor returns expected paths
- `select_crud_resource(emitted_OPENAPI_SPEC)` succeeds (FR-10)

**Integration**
- `startd8 generate backend --check` on fresh app → in-sync
- Hand-edit `routers.py` prefix → `--check` fails (via contract test or manifest)
- `--boot-smoke` reports missing routes when a path is deleted from routers

**Regression**
- Full `tests/unit/backend_codegen/` green
- `test_boot_smoke.py` updated for AST extractor path

---

## 7. Effort estimate

| Milestone | Effort | Value |
|-----------|--------|-------|
| M0 (manifest + boot_smoke) | ~0.5 day | **Quick win** — immediate C-6 improvement |
| M1 (full contract + tests) | ~1 day | Core Role 1 MVP |
| M2 (gate + export + FR-10) | ~0.5 day | External tooling readiness |
| M3 (httpx client) | ~0.5 day | Escape hatch fulfillment |
| M4 (shared extract) | ~0.5 day | DRY; not blocking |

**Recommended first PR:** M0+M1 together (the manifest alone is too thin to justify a provider kind;
ship the full module).

---

*Plan v1.0 — paired with Requirements v0.2. Ready for CRP review (`/new-cnvrg-rvw-prmpt`) before
implementation.*
