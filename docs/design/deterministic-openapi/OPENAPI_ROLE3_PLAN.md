# OpenAPI Role 3 — Inter-Context Seam (Implementation Plan)

**Version:** 0.2 (M0–M3 shipped — paired with Requirements v0.2)
**Date:** 2026-06-19
**Status:** ✅ Shipped on `main` (2026-06-19) — see `OPENAPI_ROLE3_NEXT_STEPS.md`
**Paired requirements:** `OPENAPI_ROLE3_REQUIREMENTS.md`

---

## 0. Prerequisites (shipped)

| Milestone | Status |
|-----------|--------|
| Role 1 — static `openapi_contract.py`, `ApiClient` CRUD, boot-smoke wiring | ✅ main |
| Role 2 — `api.yaml` overlay, validation-only mode, overlay `ApiClient` methods | ✅ main |
| Role 1 FR-3 — conditional manifest→contract projection | ✅ main |
| Shared `openapi_contract/schema_resolve.py` | ✅ main |

---

## 1. Files touched (M0+M1)

### NEW
- `backend_codegen/context_manifest.py` — parse `contexts.yaml`, `filter_spec_for_client`, `contract_sha256`
- `backend_codegen/context_client_renderer.py` — `clients/{id}_client.py` emission
- `tests/unit/backend_codegen/test_context_manifest.py`
- `tests/unit/backend_codegen/test_context_client.py`

### MODIFIED
- `assembler.py` — `contexts_text` + `render_context_clients()` emission
- `cli_generate.py` — `--contexts` flag; thread `contexts_text` + `project_root` through generate/check
- `drift.py` — `python-context-client` kind; `contexts-sha256` + `contract-sha256` headers
- `_headers.py` — `header_context_client()`
- `provider.py` — `_read_contexts()`; skip-hook threading
- `wireframe/inputs.py` — catalog key `contexts` → `prisma/contexts.yaml`
- `wireframe/plan.py` — claim `clients/{id}_client.py` when contexts manifest planned

### REUSED (no fork)
- `openapi_contract_renderer._project_openapi` — local producer spec source
- `openapi_client_renderer` — `_entity_methods`, `_overlay_client_methods`
- `validators/openapi_spec_gate.extract_openapi_spec_from_project` — M0 export conformance

---

## 2. Sequencing

### M0 — Producer promotion hardening ✅
- `--export-openapi` = merged spec (Role 2 v1)
- Conformance test: exported canonical JSON ≡ AST-extracted `OPENAPI_SPEC`
- Documented in Requirements §FR-2

### M1 — Context manifest + consumer client ✅ (this PR)
- `contexts.yaml` grammar (OQ-1 closed)
- Emit `clients/{id}_client.py` with `contract-sha256` header (OQ-2, OQ-4)
- Default `routes: crud` filter (OQ-3)
- Drift + skip-hook threading (FR-5)
- Unit tests: parse, render, drift, FR-7 method paths ⊆ manifest

### M2 — Cross-context smoke ✅
- `deploy_harness/context_smoke.py` — `run_context_client_smoke` via generated client + `select_crud_resource`
- Emit `tests/test_cross_context_smoke.py` when `contexts.yaml` present (in-process TestClient shim)
- Drift kind `python-tests-cross-context` (schema + contexts hashes)
- FR-6 integration test template

### M2b — Inter-context OTel (OQ-5) ✅
- `context_otel_renderer.py` → `clients/_context_otel.py` (`trace_outbound_request`)
- Generated context clients route HTTP through `_request()` with CLIENT spans
- Drift kind `python-context-otel`; `http_client.py` unchanged (in-process spine)

### M3 — Wireframe + assembly-inputs ✅
- Catalog keys `imports`, `api`, `contexts` in `CONVENTION_PATHS` + wireframe claims
- `ASSEMBLY_INPUTS_TEMPLATE.md` v0.2 — full manifest inventory + Role 3 remote smoke notes

### M2c — Remote/deployed producer smoke ✅
- `run_outbound_context_smokes` + `run_remote_producer_smoke` in `context_smoke.py`
- Deploy harness `context_smoke` ladder stage; env `STARTD8_CONTEXT_<ID>_BASE_URL`
- Generated remote smoke tests in `test_cross_context_smoke.py`

### M4 — Two-app seam fixture ✅
- `docs/design/deterministic-openapi/fixtures/two-app-seam/` (producer export + consumer pin)
- `tests/unit/backend_codegen/test_openapi_role3_m4_fixture.py` (5 tests)
- `scripts/openapi_role3_m4_smoke.sh` — one-command smoke

### Deferred → see `OPENAPI_ROLE3_NEXT_STEPS.md`

M4 two-app fixture, M5 cross-repo contract filter, bucket-3 Prime integration wiring.

---

## 3. Key design decisions (closed)

| Decision | Resolution |
|----------|------------|
| Manifest location | `prisma/contexts.yaml` + assembly-inputs key `contexts` |
| Client layout | `clients/{producer}_client.py` per producer; `http_client.py` unchanged |
| Route filter | Default `crud`: entity CRUD + overlay ops with Prisma DTO JSON refs |
| Hash | `contract-sha256 = sha256(canonical_json(filtered_spec))` |
| Stale policy | Fail-closed on `--check` (installed and deployed) |

---

## 4. Test plan (M0+M1)

**Unit**
- `test_context_manifest.py` — parse grammar, `filter_spec_for_client`
- `test_context_client.py` — render, drift, FR-7 paths ⊆ manifest, backend emission
- `test_export_openapi_*` — export writes merged spec (existing + M0 canonical check)

**Integration (M2)**
- Loopback producer → export → consumer client → smoke round-trip

---

## 5. Effort

| Milestone | Status |
|-----------|--------|
| M0 (promotion verify) | ✅ |
| M1 (manifest + client) | ✅ this branch |
| M2 (cross-context smoke) | ✅ |
| M2c (remote producer smoke) | ✅ |
| M3 (assembly-inputs docs) | ✅ |
| M4 (two-app fixture) | ✅ |

---

*Plan v0.2 — M0–M4 + P2 shipped on `feat/openapi-role3-integration`. Next: `OPENAPI_ROLE3_NEXT_STEPS.md` (P3 / M5).*
