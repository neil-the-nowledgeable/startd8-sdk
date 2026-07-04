# OpenAPI Role 2 — Implementation Plan

**Version:** 1.2 (Post-implementation — M0–M3 + Role 1 conditional routes)
**Date:** 2026-06-19
**Status:** Shipped on `feat/openapi-role2-input` — ready to merge to main

---

## 0. Planning Discoveries (raw — feeds requirements §0)

| v0.1 assumed | Planning revealed (codebase-grounded) | Impact |
|--------------|--------------------------------------|--------|
| New parallel contract artifact for overlay | Role 1 already owns `app/openapi_contract.py`; `drift.py` is single-kind re-render | **Merge into existing module** — one drift surface, one skip-hook kind |
| Role 2 generates custom route handlers | `crud_generator.render_main` mounts project-owned `user_routers` only; `IDEAL_TARGET_ARCHITECTURE` §3 puts non-CRUD logic in LLM bucket | v1 is **contract-only** for overlay routes; handlers stay in `user_routers.py` (bucket 3) |
| Need new OpenAPI parser from scratch | `openapi-spec-validator` already in `[dev]` (Role 1 M2); `openapi_contract/schema_resolve.py` resolves `$ref` | Validate overlay + merge with existing resolver; no `prance` in v1 |
| Conditional routes = duplicate Role 1 work | `assembler` emits AI/pages/flows/import paths from **six** manifest types; replicating each in `openapi_contract_renderer` is N×complexity | **Split responsibility:** manifest-derived conditional routes **shipped in Role 1** (FR-3); **overlay = net-new / user / brownfield** paths only |
| `api.yaml` might replace Prisma projection | `render_openapi_contract` is 100% Prisma-driven; collision with CRUD would break drift truth | Base-always-wins merge; overlay **additive only** |
| Brownfield ingest is v1 | `imports.yaml` / `pages.yaml` use closed YAML grammars + round-trip parsers — brownfield OpenAPI is open-ended | **Defer FR-12** to Phase 2; v1 is authored overlay only |
| Auth/pagination need implementation | No auth middleware gen in backend_codegen today (`auth_renderer` is deployed seam only) | Declare metadata in merged spec only; **no auth enforcement gen** in v1 |
| New drift pattern needed | `drift.py` already has `imports-sha256`, `pages-sha256`, `forms-sha256` + `_IMPORTS_KINDS` | Add `api-sha256` + `header_api_overlay()` following `header_imports` exactly |
| CLI needs new input threading | `cli_generate.py:242-266` reads 7 optional manifests into `render_backend()` / `check_drift()` | Add `--api` to read loop + thread `api_text` through assembler + drift (same as `--imports`) |
| Client gen for all overlay routes | `openapi_client_renderer` imports DTOs from `app.tables` only | Generate client methods only when operation `$ref` resolves to Prisma-derived schema names |
| Reconciliation is heavy formal methods | `owned_file_in_sync` + contract tests already catch router drift | v1 reconciliation = **structural checks** (collision, ref target exists, validator pass) — sufficient for gate |

**Quick wins surfaced by planning (not evident pre-requirements):**
1. **Overlay-as-manifest-only (M0)** — merge paths into `ROUTE_MANIFEST` without httpx client changes → immediate boot-smoke + C-6 value for `user_routers` documenters.
2. **`api-sha256` drift** — copy-paste `imports.yaml` pattern (~40 lines in `_headers.py` + `drift.py`) — unlocks `--check` for overlay edits day one.
3. **Reuse `extract_openapi_spec_from_text` AST path** — reconciliation tests can load merged module without import pollution (Role 1 M4 hardening).
4. **Wireframe slot** — `assembly-inputs.yaml` already lists manifests; adding `api: api.yaml` is doc + wireframe read — no codegen architecture change.
5. **Role 1 conditional-route debt ↓** — teams can declare AI/import routes in overlay *for contract purposes* while manifest emission catches up (validation-only mode in OQ-2). **Role 1 FR-3 conditional projection now ships** alongside overlay.

---

## 1. Files touched (grounded)

### NEW modules
- **`backend_codegen/api_overlay_manifest.py`**
  - `parse_api_overlay(text) -> ApiOverlay` — load YAML, minimal structural validation
  - `validate_overlay_dict(spec) -> list[str]` — delegate to `openapi_spec_validator` when present
  - `reconcile_overlay(base_spec, overlay, schema) -> ReconcileResult` — FR-6 rules
  - `merge_openapi_specs(base, overlay) -> dict` — additive merge

- **`backend_codegen/openapi_contract_renderer.py`** (MODIFY heavily)
  - `render_openapi_contract(..., api_text: Optional[str] = None)`
  - Call merge after `_build_openapi_spec`
  - Use `header_api_overlay(source, schema_sha, api_sha, kind)` when `api_text` given

- **`backend_codegen/_headers.py`** (MODIFY)
  - `header_api_overlay(...)` — schema-sha256 + api-sha256 (imports precedent)

- **`backend_codegen/drift.py`** (MODIFY)
  - `_HEADER_API_SHA_RE`, `_API_OVERLAY_KINDS = frozenset({"python-openapi-contract"})` 
  - `owned_file_in_sync(..., api_text=...)` threading
  - Re-render lambda passes `api_text`

- **`tests/unit/backend_codegen/test_api_overlay.py`** — parse, merge, reconcile, collision cases

### MODIFIED modules
- **`assembler.py`** — `api_text` param → `render_openapi_contract(..., api_text=api_text)`
- **`cli_generate.py`** — `--api` option + read loop + drift/check/gate threading
- **`test_emitter.py`** — optional reconciliation test block when api overlay baked in tests
- **`openapi_client_renderer.py`** — optional overlay ops with Prisma DTO refs (Phase 1d / M3)

### UNCHANGED (v1)
- **`crud_generator.py`** — no auto `user_routers` stub emission
- **`ai_layer.py` / `pages_generator.py`** — manifest route emission unchanged

---

## 2. Per-requirement implementation steps

| FR | Step |
|----|------|
| FR-1 | `--api` CLI + `parse_api_overlay`; accept OpenAPI 3.0 YAML (full doc or paths-only wrapper) |
| FR-2 | `validate_overlay_dict` in generate path; gate uses existing `validate_openapi_spec_dict` on **merged** spec |
| FR-3 | `merge_openapi_specs`: base paths preserved; overlay adds new keys only |
| FR-4 | Single `openapi_contract.py` output; `ROUTE_MANIFEST` rebuilt from merged paths |
| FR-5 | `header_api_overlay` + drift `api-sha256` check |
| FR-6 | `reconcile_overlay` before merge; check exits 2 with diagnostics |
| FR-7 | `test_openapi_reconciliation.py` emitter or extend `render_openapi_contract_tests` |
| FR-8 | Automatic via merged `ROUTE_MANIFEST` (Role 1 wiring) |
| FR-9 | Unit test: wireframe + trivial overlay does not break `select_crud_resource` |
| FR-10 | M3: scan merged spec for overlay ops with `{Entity}{Create,Read,Update}` refs |
| FR-11 | `--export-openapi` already reads contract module — merged spec exports for free (FR-11) |
| FR-12 | Regression: `render_openapi_contract(schema)` == `render_openapi_contract(schema, api_text=None)` |
| FR-D1 | **Shipped** — `startd8 openapi normalize` (M4) |
| FR-O1 | M2 optional: validation-only declared paths + warn-not-error |

---

## 3. Sequencing (milestones)

### M0 — Overlay merge + route manifest (smallest shippable)
- `api_overlay_manifest.py` parse + merge (paths only)
- `render_openapi_contract(..., api_text)` merges into `ROUTE_MANIFEST`
- `api-sha256` drift header + `drift.py` threading
- `--api` CLI flag
- Unit tests: merge additive paths; collision fails; absent overlay byte-identical (SOTTO)
- **Value:** custom routes in contract; boot-smoke sees `user_routers` paths once mounted

### M1 — Reconciliation gate + merged OPENAPI_SPEC
- Full `reconcile_overlay` (refs, params)
- `--check` / generate fail on collision
- Extend contract tests
- Merged spec passes `openapi-spec-validator` on `--gate`

### M2 — Validation-only manifest paths (optional quick win — FR-O1)
- Overlay may declare paths manifests already emit; warn if not in base and not additive
- Document relationship to Role 1 conditional-route backlog (complement, not replace)

### M3 — Client extension (optional — FR-10) ✅
- `openapi_client_renderer` reads merged spec; emit methods for overlay ops with Prisma DTO refs
- Schema-only client byte-identical when overlay has no Prisma `$ref` ops

### M3b — Role 1 conditional route projection ✅
- `_conditional_routes()` in `openapi_contract_renderer` mirrors `assembler` manifest guards
- Manifest kwargs threaded through contract/client renderers + drift + contract tests

### M4 — Brownfield normalize ✅
- `startd8 openapi normalize` — human-in-the-loop ingest

---

## 4. Key implementation details

### 4.1 Merge algorithm (additive)

```python
def merge_openapi_specs(base: dict, overlay: dict) -> dict:
    merged = copy.deepcopy(base)
    for path, item in overlay.get("paths", {}).items():
        if path in merged["paths"]:
            raise ReconcileError(f"collision: {path}")
        merged["paths"][path] = item
    merged_schemas = merged.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in overlay.get("components", {}).get("schemas", {}).items():
        if name in merged_schemas:
            raise ReconcileError(f"schema collision: {name}")
        merged_schemas[name] = schema
    return merged
```

### 4.2 `api.yaml` authoring shape (lean v1)

```yaml
openapi: 3.0.3
info:
  title: App overlay
  version: 0.0.0
paths:
  /webhooks/stripe:
    post:
      summary: Stripe webhook (implemented in user_routers)
      responses:
        "200":
          description: OK
```

Paths-only overlay without `info` allowed if parser injects defaults.

### 4.3 Drift threading (copy `imports` pattern)

From `cli_generate.py` and `drift.owned_file_in_sync`:
- Read `api_text` when `--api` given
- `openapi_contract.py` header includes `# api-sha256: ...` when present
- `owned_file_in_sync` compares embedded hash vs `schema_sha256(api_text)`

### 4.4 Reconciliation vs contract tests

| Check | When | Mechanism |
|-------|------|-----------|
| Collision | generate/check | `reconcile_overlay` pre-merge |
| Ref targets | generate/check | names match `_model_names(schema)` + `{Create,Read,Update}` suffix rules |
| Mounted routes | test (generated app) | existing `test_openapi_contract.py` walks `app.routes` |
| Spec validity | `--gate` | `validate_openapi_spec_dict(merged)` |

---

## 5. Risks

| Risk | Mitigation |
|------|------------|
| Overlay/base path normalization (`/foo` vs `/foo/`) | Normalize trailing slashes same as `crud_generator` (`/{entity}/` convention); document |
| Merged spec fails validator on minimal overlay | Unit test minimal overlay + wireframe base |
| Drift kwargs not threaded to skip-hook | Copy `--imports` test in `test_cli_backend.py` |
| Scope creep into handler gen | Non-requirements + plan explicitly defer `user_routers` emission |
| Role 1 conditional routes still missing | **Resolved** — FR-3 conditional projection shipped; M2 validation-only mode complements |

---

## 6. Test plan

**Unit**
- Parse minimal `api.yaml`
- Merge adds paths to manifest
- Collision raises
- Invalid `$ref` raises
- Absent overlay: byte-identical to Role 1 output
- `api-sha256` drift detects overlay edit
- `select_crud_resource` still works on merged wireframe spec

**Integration**
- `generate backend --api fixtures/api.yaml --check` in-sync
- Hand-edit overlay → `--check` stale
- `--gate` passes on merged spec

---

## 7. Effort estimate

| Milestone | Effort | Value |
|-----------|--------|-------|
| M0 (merge + manifest + drift + CLI) | ~1 day | **Highest leverage** — contract completeness for custom routes |
| M1 (reconciliation + gate) | ~0.5 day | Fail-closed two-contract discipline |
| M2 (validation-only duplicates) | ~0.25 day | Bridges manifest/overlay gap |
| M3 (client extension) | ~0.5 day | Escape hatch for typed overlay consumers |
| M4 (brownfield normalize) | ~1 day | Deferred |

**Recommended first PR:** M0+M1 (contract merge + reconciliation; no client extension).

---

*Plan v1.1 — paired with Requirements v0.2. Offer CRP review before implementation.*
