# OpenAPI Role 2 — API Surface Overlay (Requirements)

**Version:** 0.3 (Post-implementation — M0–M3 complete)
**Date:** 2026-06-19
**Status:** Shipped on `feat/openapi-role2-input` — ready to merge to main
**Owner:** SDK / backend_codegen
**Motivated by:** `OPENAPI_LEVERAGE_ANALYSIS.md` Role 2 — accept OpenAPI as an **input** contract
sibling to Prisma for endpoint surface beyond schema-derived CRUD
**Builds on:** `OPENAPI_ROLE1_REQUIREMENTS.md` (shipped on main at `e8487788`)
**Paired plan:** `OPENAPI_ROLE2_PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against `openapi_contract_renderer`,
> `assembler`, `drift.py`, `crud_generator.render_main`, and Role 1 consumers. **9 corrections** —
> past the 30% bar; v0.1 was appropriately premature.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|-------------------|--------|
| New parallel owned artifact for overlay input | Role 1 already centralizes `ROUTE_MANIFEST` + `OPENAPI_SPEC` in `app/openapi_contract.py`; second file would fork drift | FR-4: **merge into existing** `python-openapi-contract` module — single drift surface |
| Role 2 emits custom route handlers | `render_main` mounts project-owned `user_routers` only; IDEAL_TARGET §3 assigns non-CRUD **logic** to bucket 3 | Removed implicit handler gen; overlay is **contract declaration** — implement in `user_routers.py` |
| Need substantial new OpenAPI parser | Role 1 added `openapi-spec-validator` + `openapi_contract/schema_resolve.py` | FR-2/FR-6 use existing validator + resolver; **no `prance`/`openapi-core` in v1** |
| Overlay might override CRUD paths | Prisma projection is the drift truth for schema-derived routes | FR-3: **additive-only merge** — overlay cannot replace base paths or schemas (collision ⇒ error) |
| Role 1 conditional-route debt solved here | Six manifest types (`ai_passes`, `pages`, `views` forms/flows/editors, `imports`) each emit routes differently | **Split:** manifest→contract projection **shipped in Role 1 FR-3**; overlay covers **net-new / user / brownfield** paths in v1 |
| Brownfield ingest is v1 (FR-12) | `imports.yaml` uses closed grammar + round-trip parser; external OpenAPI is open-ended | FR-12 **deferred to Phase 2** (`openapi normalize` helper) |
| Auth/pagination need generated middleware | `auth_renderer` is deployed seam only; no auth middleware codegen exists | Auth/pagination/error envelopes: **declare in merged spec only** — no enforcement gen in v1 |
| Drift needs new architecture | `drift.py` already threads `imports-sha256`, `pages-sha256`, `forms-sha256` with matching headers | FR-5: copy **`api-sha256`** pattern from `header_imports` (~40 lines) |
| Client gen for every overlay route | `openapi_client_renderer` only knows Prisma `{Entity}{Create,Read,Update}` DTOs | FR-10 **narrowed:** client methods only when overlay op `$ref` resolves to Prisma-derived schema names |
| Reconciliation requires heavy formalism | Contract tests + `owned_file_in_sync` already catch surface drift at test time | FR-6: v1 structural reconciliation (collision, resolvable refs, validator) — sufficient for gate |

**Resolved open questions:**
- **OQ-1 → Path-item overlay with optional wrapper.** Author may supply a minimal OpenAPI doc
  (`paths` + optional `components.schemas`); parser injects `openapi: 3.0.3` + `info` defaults when
  absent. Not a full replacement document.
- **OQ-2 → Additive net-new default; validation-only optional (M2).** Overlay v1 **adds** paths not
  in the Prisma+health base. Optional M2 mode allows declaring manifest-emitted paths for
  **contract validation** (warn if declared but not mounted) without owning their emission.
- **OQ-3 → `openapi-spec-validator` + existing `schema_resolve`.** Sufficient for v1 merge/reconcile;
  defer heavier parsers until brownfield ingest (Phase 2).
- **OQ-4 → Resolved in Role 1 FR-3.** Manifest-derived conditional routes land in
  `openapi_contract_renderer` when manifests exist. Overlay complements — does not replace — that work.
- **OQ-5 → Phase 2.** v1 is **authored** `api.yaml` only; normalize/ingest CLI deferred.

**Quick wins surfaced by planning (not evident pre-plan):**
1. **M0 overlay-as-manifest-only** — merge paths into `ROUTE_MANIFEST` with zero client/handler work
   → boot-smoke + C-6 immediately covers documented `user_routers` paths.
2. **`api-sha256` drift** — copy `imports.yaml` threading → `--check` catches overlay edits day one.
3. **`--export-openapi` free win** — merged spec exports automatically once FR-4 holds (no new flag).
4. **Wireframe / `assembly-inputs.yaml` slot** — declare `api: api.yaml` beside other manifests; no
   architectural change, just input wiring.
5. **Validation-only overlay (M2)** — teams can list `/ai/*` or `/import` in overlay for contract
   completeness while Role 1 manifest projection catches up.

---

## 1. Problem Statement

Role 1 made the API contract a **deterministic output** projected from `schema.prisma` (CRUD +
health). The SDK still cannot **declare or reconcile** API surface that is not mechanically
derivable from the data contract:

| Component | Current state | Gap |
|-----------|--------------|-----|
| CRUD + health routes | Owned in `app/openapi_contract.py` (Role 1) | Complete for schema-derived subset |
| Custom / non-CRUD HTTP routes | Project-owned `app/user_routers.py` seam | No manifest input; absent from `ROUTE_MANIFEST`; boot-smoke blind |
| Conditional surfaces (AI, pages, flows, imports) | Emitted when manifests present | Role 1 FR-3 conditional projection in `openapi_contract_renderer` |
| Auth / pagination / error envelopes | Not modeled | Need declared shape for integration/brownfield docs |
| Brownfield onboarding | Concierge survey triage only | No adoptable overlay path |
| Two-contract discipline | Prisma = data; runtime OpenAPI = byproduct | No explicit reconciliation when surface ≠ projection |

Role 2 raises the **declarative ceiling** for routes and DTO shapes — not handler bodies (bucket 3).

---

## 2. Goals & Non-Goals

**Goals**
- Optional **`api.yaml`** overlay as second input to `generate backend`.
- **Additive merge** into Role 1's `OPENAPI_SPEC` + `ROUTE_MANIFEST` (single owned file).
- Structural **reconciliation** against Prisma-derived base (collision-free, resolvable refs).
- `api-sha256` drift threading (imports precedent).
- Preserve **SOTTO**: absent `api.yaml` ⇒ byte-identical Role 1 output.

**Non-Goals (v1)**
- Handler implementation for overlay routes (`user_routers` / Prime / bucket 3).
- Prisma schema generation from OpenAPI.
- Auth middleware implementation from `securitySchemes`.
- Replacing manifest-driven route **emission** (AI/pages/flows/imports).
- Brownfield auto-ingest without human review (Phase 2).
- TS client / mock servers.

---

## 3. Requirements

### Input contract
- **FR-1** Optional **`api.yaml`** input. CLI: `startd8 generate backend --api <path>`. Absent ⇒ no
  overlay processing. Accept OpenAPI 3.0 YAML (minimal `paths` overlay or fuller doc).
- **FR-2** Validate overlay structure; validate **merged** spec with `openapi-spec-validator` on
  `--gate` (Role 1 rule: unavailable ⇒ non-pass). Malformed overlay or failed reconciliation ⇒
  exit 2 on generate/check.

### Merge semantics
- **FR-3** Prisma+health projection (Role 1) is immutable **base**. Overlay **adds** paths and
  `components.schemas` entries only. Duplicate path keys or schema names ⇒ reconciliation error.
- **FR-4** Output remains **`app/openapi_contract.py`** (`python-openapi-contract`) containing merged
  `ROUTE_MANIFEST` + `OPENAPI_SPEC`. Rebuild manifest from merged `paths` (sorted, stable).
- **FR-5** When overlay present, provenance header includes **`api-sha256`** (two-input drift, mirror
  `imports-sha256`). `drift.py` + `cli_generate --check` thread `api_text` like `--imports`.

### Reconciliation (two-contract)
- **FR-6** Pre-merge reconciliation gate:
  - No `(method, path)` collision between base and overlay.
  - Overlay `$ref` to `#/components/schemas/{Name}` where `{Name}` matches `{Entity}{Create|Read|Update}`
    must reference entities in the Prisma schema.
  - Path operations with `{param}` segments declare matching `parameters`.
- **FR-7** Emit reconciliation coverage in generated tests (extend `test_openapi_contract.py` or
  sibling `test_openapi_reconciliation.py`): merged refs resolve; no internal manifest/spec path skew.

### Consumer wiring
- **FR-8** Merged `ROUTE_MANIFEST` feeds `boot_smoke` automatically (Role 1 `expected_routes_from_contract`).
- **FR-9** Merged wireframe `OPENAPI_SPEC` remains compatible with `select_crud_resource` (unit test).

### Client / tooling
- **FR-10** *(Phase M3 — optional)* Extend `clients/http_client.py` for overlay operations whose
  request/response schemas `$ref` Prisma-derived DTO names. Inline-only schemas ⇒ no client method.
- **FR-11** `--export-openapi` writes the **merged** spec (no new flag).

### SOTTO / regression
- **FR-12** Absent `api.yaml`, `render_openapi_contract` output is **byte-identical** to Role 1
  (regression test).

### Deferred (Phase 2)
- **FR-D1** `startd8 openapi normalize <openapi.json> --out api.yaml` — human-reviewed brownfield
  ingest (strip framework noise → overlay subset).

### Optional quick win (M2)
- **FR-O1** *Validation-only mode:* overlay may **declare** paths that manifest emission already
  owns (e.g. `/ai/*`, `/import`) for contract completeness; generator emits a **warning** (not error)
  when declared path is missing from merged manifest base and not additive. Does not emit those routes.

---

## 4. Non-Requirements

- Business logic in overlay route handlers.
- Auto-generated `user_routers.py` stubs.
- WebSocket / callbacks / full OpenAPI 3.1.
- Generating Prisma from OpenAPI.

---

## 5. Open Questions (remaining)

- **OQ-6:** Exact `api.yaml` authoring template for wireframe/concierge extraction — closed grammar
  vs freeform OpenAPI subset? *(Lean: freeform subset + validator; add concierge template later.)*
- **OQ-7:** Trailing-slash normalization policy for overlay paths vs CRUD `/{entity}/` convention.
  *(Lean: normalize to CRUD convention on ingest; reject mixed duplicates.)*

---

## 6. Success Metrics

| Metric | Target |
|--------|--------|
| Custom route in overlay appears in `ROUTE_MANIFEST` | M0 |
| `--check` fails on overlay/schema collision | M1 |
| Absent overlay byte-identical to Role 1 | FR-12 regression |
| Merged spec passes `--gate` validator | M1 |
| `select_crud_resource` still works on wireframe + trivial overlay | FR-9 |
| Cost | $0 LLM; same skip-hook kind |

---

*v0.2 — Post-planning self-reflective update. 2 requirements deferred (brownfield ingest, handler gen),
3 narrowed (client, auth, reconciliation), 4 added (SOTTO regression, api-sha256, validation-only mode,
merged export), 5 open questions resolved.*
