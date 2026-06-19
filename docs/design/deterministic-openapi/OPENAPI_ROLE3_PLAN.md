# OpenAPI Role 3 — Inter-Context Seam (Implementation Plan)

**Version:** 0.1 (Pre-planning — paired with Requirements v0.1)
**Date:** 2026-06-19
**Status:** Planned — ready for CRP / reflective loop
**Paired requirements:** `OPENAPI_ROLE3_REQUIREMENTS.md`

---

## 0. Prerequisites (shipped)

| Milestone | Status |
|-----------|--------|
| Role 1 — static `openapi_contract.py`, `ApiClient` CRUD, boot-smoke wiring | ✅ main |
| Role 2 — `api.yaml` overlay, validation-only mode, overlay `ApiClient` methods | ✅ `feat/openapi-role2-input` |
| Role 1 FR-3 — conditional manifest→contract projection | ✅ same branch |
| Shared `openapi_contract/schema_resolve.py` | ✅ main (M4 extract) |

---

## 1. Files likely touched

### NEW
- `backend_codegen/context_manifest.py` — parse inter-context manifest
- `backend_codegen/context_client_renderer.py` — consumer client from remote/merged spec snapshot
- `tests/unit/backend_codegen/test_context_client.py`
- `tests/integration/test_cross_context_smoke.py` (or extend deploy harness)

### MODIFIED
- `assembler.py` — optional `--contexts` emission path
- `cli_generate.py` — read contexts manifest; thread through drift
- `drift.py` — `contract-sha256` or composite producer hash header
- `wireframe/plan.py` — optional contexts slot in assembly inputs
- `deploy_harness/smoke.py` — optional `ApiClient` path beside in-process TestClient

### REUSED (no fork)
- `openapi_contract_renderer._project_openapi` — producer spec source
- `openapi_client_renderer` — method emission patterns
- `openapi_contract/schema_resolve.select_crud_resource` — smoke resource selection

---

## 2. Sequencing

### M0 — Producer promotion hardening (~0.5 day)
- Verify `--export-openapi` = merged spec (CRUD + conditional + overlay) — **done in Role 2 v1**
- Add conformance test: exported JSON ≡ AST-extracted `OPENAPI_SPEC`
- Document promotion workflow in Role 3 requirements

### M1 — Context manifest + consumer client (~1 day)
- `contexts.yaml` grammar (producer id, base_url template, route filter)
- Emit `clients/{producer}_client.py` with producer hash header
- Drift + skip-hook threading
- Unit tests: method paths ⊆ producer manifest

### M2 — Cross-context smoke (~0.5 day)
- Harness invokes producer via `ApiClient` + `select_crud_resource`
- Installed mode: loopback; deployed: env-based base URL
- FR-6 integration test template

### M3 — Wireframe + assembly inputs (~0.25 day)
- `assembly-inputs.yaml` slot for `contexts`
- Wireframe claims consumer client paths when manifest present

### Deferred
- TypeScript consumer emit
- gRPC/proto promotion
- Auth middleware enforcement

---

## 3. Key design decisions (to close in CRP)

| Decision | Lean default |
|----------|--------------|
| Manifest location | `prisma/contexts.yaml` sibling to other manifests |
| Client layout | `clients/{producer}_client.py` per producer; keep `http_client.py` for local CRUD |
| Route filter | CRUD + explicitly listed overlay paths only (avoid HTML/HTMX routes in client) |
| Hash | `contract-sha256 = sha256(canonical_json(OPENAPI_SPEC))` embedded in consumer header |
| Stale policy | Fail-closed on `--check` (same as all owned artifacts) |

---

## 4. Risks

| Risk | Mitigation |
|------|------------|
| HTML routes in manifest pollute typed client | Route filter in manifest; default CRUD-only |
| Producer/consumer repo split | Hash pin + documented regen workflow |
| Duplicate client logic | Extract shared method emitter from `openapi_client_renderer` |
| OTel scope creep | OQ-5 — span naming optional follow-on |

---

## 5. Test plan

**Unit**
- Parse `contexts.yaml` strict grammar
- Consumer client methods match producer spec subset
- Drift detects producer hash change

**Integration**
- Loopback: generate producer app → export spec → generate consumer client → smoke round-trip
- Conditional + overlay producer spec propagates to consumer methods

---

## 6. Effort estimate

| Milestone | Effort | Value |
|-----------|--------|-------|
| M0 (promotion verify) | ~0.25 day | Foundation |
| M1 (manifest + client) | ~1 day | Core Role 3 |
| M2 (cross-context smoke) | ~0.5 day | End-to-end proof |
| M3 (wireframe) | ~0.25 day | Discoverability |

**Recommended first PR:** M0+M1 (manifest + consumer client, no harness yet).

---

*Plan v0.1 — scaffold for reflective requirements loop. Do not implement until Requirements v0.2 CRP pass.*
