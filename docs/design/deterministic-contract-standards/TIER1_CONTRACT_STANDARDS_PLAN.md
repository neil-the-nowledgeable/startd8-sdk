# Tier-1 Deterministic Contract Standards — Implementation Plan

**Version:** 1.1 (post-reflective update — paired with Requirements v0.2)
**Date:** 2026-06-19
**Status:** Planned — pre-implementation

---

## 0. Planning Discoveries (fed §0 of requirements)

| v0.1 assumed | Planning revealed | Plan impact |
|--------------|-------------------|-------------|
| Build OpenAPI from scratch | Spec + plan exist; no `openapi_contract_renderer.py` on disk | Workstream A = execute `OPENAPI_ROLE1_PLAN.md` |
| New JSON Schema implementation | `smoke.py:55–329` is production-quality | Workstream B0 = move, don't rewrite |
| New migration engine | `migration_codegen/generator.py` complete; CLI at `cli_generate.py:764` | Provider wrapper only |
| Auto-migrate on backend gen | Operators expect explicit migrate | Hook `--check` only |
| Own protoc outputs | Java/C# compile-time gen | Skeleton + manifest; protoc in gate |
| OTel via artifact_generator | Different subsystem | `scaffold_codegen` + `app/telemetry.py` |
| AsyncAPI parser | No deps, no tests | `events.yaml` minimal DSL |
| 6 parallel tracks | Shared schema types block OpenAPI + events | B before A M1 |

---

## 1. Architecture

```
prisma/schema.prisma (keystone)
        │
        ├── backend_codegen (existing spine)
        │
        ├── schema_contract/          ← NEW library (Workstream B)
        │     ├── resolve.py          ← extracted from deploy_harness/smoke.py
        │     └── prisma_json_schema.py
        │
        ├── openapi_contract_renderer ← Workstream A (OPENAPI_ROLE1_PLAN)
        │
        ├── migration_codegen         ← existing engine
        │     └── migration_provider  ← NEW provider (Workstream C)
        │
        ├── scaffold_codegen          ← extend app.yaml telemetry (Workstream D)
        │     └── telemetry_renderer.py
        │
        ├── proto_codegen/            ← NEW (Workstream E)
        │     ├── proto_parser.py
        │     └── skeleton_renderers/{python,go}.py
        │
        └── events_codegen/           ← NEW (Workstream F)
              ├── manifest.py         ← events.yaml parser
              └── kafka_renderers.py

Entry points (deterministic_providers):
  pydantic-sqlmodel (existing)
  openapi-contract      ← wraps openapi kinds OR extends backend provider
  migration             ← NEW
  proto-skeleton        ← NEW
  events                ← NEW
```

---

## 2. Files touched (grounded in codebase)

### NEW packages / modules

| Path | Workstream | Purpose |
|------|------------|---------|
| `src/startd8/schema_contract/__init__.py` | B | Public API: `resolve_schema`, `synthesize_body`, `select_crud_resource`, `prisma_dto_schemas` |
| `src/startd8/schema_contract/resolve.py` | B | Lifted from `deploy_harness/smoke.py` |
| `src/startd8/schema_contract/prisma_json_schema.py` | B | Prisma → JSON Schema DTO projection |
| `src/startd8/backend_codegen/openapi_contract_renderer.py` | A | Per `OPENAPI_ROLE1_PLAN.md` |
| `src/startd8/backend_codegen/openapi_contract_tests.py` | A | Contract tests emitter |
| `src/startd8/migration_codegen/provider.py` | C | `MigrationFileProvider` |
| `src/startd8/scaffold_codegen/telemetry_renderer.py` | D | `app/telemetry.py` + env snippets |
| `src/startd8/proto_codegen/` | E | Parser + skeleton renderers |
| `src/startd8/events_codegen/` | F | `events.yaml` → Kafka stubs |

### MODIFIED modules

| Path | Change |
|------|--------|
| `src/startd8/deploy_harness/smoke.py` | Import from `schema_contract`; delete duplicated functions |
| `src/startd8/backend_codegen/assembler.py` | Emit openapi contract + tests (A) |
| `src/startd8/backend_codegen/drift.py` | Register openapi kinds; thread manifest kwargs |
| `src/startd8/backend_codegen/crud_generator.py` | `CANONICAL_LAYOUT` entries |
| `src/startd8/validators/boot_smoke.py` | AST-extract `ROUTE_MANIFEST` (A FR-4) |
| `src/startd8/cli_generate.py` | `--check` calls migrate pending probe (C) |
| `src/startd8/scaffold_codegen/manifest.py` | `telemetry:` + `messaging.backend` fields (D, F) |
| `src/startd8/scaffold_codegen/renderers.py` | Conditional OTel env in compose/Dockerfile (D) |
| `src/startd8/scaffold_codegen/provider.py` | Own telemetry kinds (D) |
| `pyproject.toml` | New entry points: `migration`, `proto-skeleton`, `events` |

### UNCHANGED (consume only)

- `OPENAPI_ROLE1_REQUIREMENTS.md` — authoritative for FR-A*
- `migration_codegen/generator.py` — delta logic frozen
- `observability/artifact_generator.py` — post-deploy layer
- `languages/*.py` grpc/otel templates — read for FR-E4 / FR-D3

---

## 3. Sequencing & milestones

### Tier 0 — Shared kernel + quick wins (~1 day)

| Step | Deliverable | FR | Effort |
|------|-------------|-----|--------|
| T0.1 | Extract `schema_contract/resolve.py`; update smoke imports; regression tests | B1 | ⚡ 2h |
| T0.2 | OpenAPI **M0**: `ROUTE_MANIFEST` + boot_smoke AST extractor | A (M0), FR-4 | ⚡ 3h |
| T0.3 | `generate backend --check` → migrate pending hint | C3 | ⚡ 1h |
| T0.4 | `app.yaml` `telemetry:` schema + disabled default | D1 | ⚡ 2h |

**Tier 0 exit:** smoke tests green; boot_smoke auto-routes on wireframe; migrate pending visible.

### M1 — OpenAPI Role 1 MVP (~1.5 days)

Execute `OPENAPI_ROLE1_PLAN.md` M1–M2:

| Step | Deliverable | FR |
|------|-------------|-----|
| M1.1 | `prisma_json_schema.py`; wire into openapi emitter | B2, A3 |
| M1.2 | Full `openapi_contract.py` + `OPENAPI_SPEC` | A1 FR-1…3 |
| M1.3 | `assembler` + `drift` registration | A1 FR-2 |
| M1.4 | `test_openapi_contract.py` emitter | A1 FR-5 |
| M1.5 | `--gate` openapi-spec-validator; `--export-openapi` | A1 FR-6, FR-9 |
| M1.6 | FR-10: `select_crud_resource(OPENAPI_SPEC)` unit test | A1 FR-10 |

### M2 — Migration provider (~0.5 day)

| Step | Deliverable | FR |
|------|-------------|-----|
| M2.1 | `MigrationFileProvider` + entry point | C1, C2 |
| M2.2 | Re-render sync via snapshot chain | C2 |
| M2.3 | Integration: wireframe baseline via `generate migrate` | C4 |
| M2.4 | `--check` integration test | C3 |

### M3 — OTel app bootstrap (~1 day)

| Step | Deliverable | FR |
|------|-------------|-----|
| M3.1 | `telemetry_renderer.py` → `app/telemetry.py` | D2 |
| M3.2 | Pattern snippets for http/grpc/db | D3 |
| M3.3 | Scaffold drift + provider owns | D4 |
| M3.4 | OTLP env in Dockerfile/compose template | D5 |
| M3.5 | Integration: local collector smoke (optional manual) | D* |

### M4 — Proto skeleton Python + Go (~1.5 days)

| Step | Deliverable | FR |
|------|-------------|-----|
| M4.1 | `proto_parser.py` — `demo.proto` golden tests | E2 |
| M4.2 | Python skeleton renderer + health | E3 |
| M4.3 | Go skeleton renderer + health | E3 |
| M4.4 | Manifest/seed opt-in wiring | E7 |
| M4.5 | `ProtoSkeletonProvider` + drift | E1, E5 |
| M4.6 | Compile gate on skeleton | E6 |
| M4.7 | Benchmark seed integration test (PI-003 class) | E* |

### M5 — Events overlay (~1 day)

| Step | Deliverable | FR |
|------|-------------|-----|
| M5.1 | `events.yaml` parser | F1 |
| M5.2 | Python producer + consumer stubs | F2 |
| M5.3 | CloudEvents constants + JSON Schema payload | F3, F4 |
| M5.4 | `EventsFileProvider` | F5 |
| M5.5 | Serialization contract test | F6 |

**Tier-1 program exit:** M1 + M2 + M3 + M4 + M5 complete; Tier 0 prerequisites satisfied.

---

## 4. Per-requirement traceability

| FR | Milestone step |
|----|----------------|
| FR-A1…A3 | M1 (OPENAPI_ROLE1_PLAN) |
| FR-B1 | T0.1 |
| FR-B2 | M1.1 |
| FR-B3 | M1.1 + T0.1 tests |
| FR-C1…C5 | M2 |
| FR-D1…D5 | T0.4 + M3 |
| FR-E1…E7 | M4 |
| FR-F1…F6 | M5 |
| FR-X1…X4 | Cross-cutting in each milestone PR |

---

## 5. Key implementation details

### 5.1 schema_contract extraction (T0.1)

Move these symbols verbatim from `deploy_harness/smoke.py`:

- `_deref`, `resolve_schema`, `_is_nullable`, `_primary_type`, `synthesize_body`, `select_crud_resource`
- Keep `_STRING_FORMATS`, `_MAX_REF_DEPTH` as module constants
- `smoke.py` becomes thin HTTP wrapper calling library

### 5.2 OpenAPI + schema_contract (M1)

`openapi_contract_renderer._build_openapi_spec`:

```python
from startd8.schema_contract.prisma_json_schema import entity_schemas

components = {"schemas": entity_schemas(schema_text)}
# paths built from _crud_routes; requestBody $ref → components/schemas/{Entity}Create
```

Single scalar map: define once in `prisma_json_schema.py`; openapi emitter imports only.

### 5.3 Migration provider sync (M2)

```python
def is_in_sync(path, content, context):
    # Read prisma from context.source_anchors
    # Parse revision's embedded snapshot from content OR re-render via next_revision
    expected = render_revision_from_chain(...)
    return content == expected
```

Only own files matching `# startd8-artifact: alembic-revision`.

### 5.4 OTel telemetry renderer (M3)

When `telemetry.enabled`:

```python
# app/telemetry.py — pattern imports gated by manifest list
if "http" in patterns:
    lines.append("from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor")
```

Reuse resource attribute keys from `otel_conventions.py` where applicable; add `service.name` from manifest.

### 5.5 Proto parser scope (M4)

Regex/line-based extraction sufficient for v1:

- `service Name { rpc Method (Req) returns (Resp); }`
- `message Name { type field = N; }`

Conformance fixtures: `scripts/gen_ob_benchmark_seeds.py` `demo.proto`, single-service protos from C# prime reqs.

### 5.6 events.yaml (M5)

Minimal parser (PyYAML already in SDK deps via scaffold):

```yaml
channels:
  order_paid:
    direction: publish
    topic: orders.paid
    payload: OrderRead
```

Producer emits JSON via `json.dumps(schema_contract.sample_instance(payload_schema))`.

---

## 6. Risks

| Risk | Mitigation |
|------|------------|
| OpenAPI + migration default-on churn | Single PR updates golden trees; document regen in CHANGELOG |
| schema_contract extract breaks smoke | Run existing smoke unit tests before/after T0.1 |
| Proto parser too naive for real protos | Scope v1 to benchmark shapes; document unsupported constructs |
| OTel optional deps bloat pyproject | `[otel]` extra; scaffold manifest gates imports |
| Events stub without broker gives false confidence | FR-F6 schema-only tests; integration marked manual |
| Drift kwargs not threaded (FR-ED-16) | Copy AI/forms lambda pattern in every new `_renderers()` entry |

---

## 7. Test plan

**Unit**
- `tests/unit/schema_contract/` — resolver fixtures from smoke tests
- `tests/unit/backend_codegen/test_openapi_contract.py` — per OPENAPI_ROLE1_PLAN §6
- `tests/unit/migration_codegen/test_provider.py` — sync true/false
- `tests/unit/scaffold_codegen/test_telemetry.py` — enabled/disabled SOTTO
- `tests/unit/proto_codegen/` — parser + skeleton goldens
- `tests/unit/events_codegen/` — payload serialization

**Integration**
- Wireframe: `generate backend` → openapi contract in-sync
- Wireframe: schema add field → `generate migrate` → provider in-sync
- Benchmark seed: proto skeleton compiles (Python subprocess compile / go build)

**Regression**
- Full `tests/unit/deploy_harness/` after schema_contract extract
- `tests/unit/backend_codegen/` suite
- Skip-hook provider recognition tests extended

---

## 8. Effort estimate

| Milestone | Effort | Cumulative value |
|-----------|--------|------------------|
| Tier 0 | ~1 day | ★★★★ quick wins |
| M1 OpenAPI | ~1.5 days | ★★★★★ HTTP contract owned |
| M2 Migration | ~0.5 day | ★★★ SQL lifecycle |
| M3 OTel bootstrap | ~1 day | ★★★★ instrumentation |
| M4 Proto skeleton | ~1.5 days | ★★★★★ polyglot RPC |
| M5 Events | ~1 day | ★★★★ messaging |
| **Total Tier 1** | **~6.5 days** | Full matrix Tier-1 row |

**Recommended PR slicing:**
1. PR1: Tier 0 + M1 (schema kernel + OpenAPI) — largest user-visible jump
2. PR2: M2 + M3 (migration + OTel)
3. PR3: M4 (proto skeleton Py/Go)
4. PR4: M5 (events overlay)

---

## 9. Reflective insights applied to requirements (summary)

Planning changed Tier-1 scope in five material ways — captured in requirements §0:

1. **Extract before emit** — schema_contract precedes OpenAPI M1.
2. **Wire before rewrite** — migration engine exists; provider is the work.
3. **Skeleton before protoc** — polyglot RPC without owning generated pb bytes.
4. **Manifest before AST** — OTel patterns declared in app.yaml, not inferred.
5. **Overlay before AsyncAPI** — events.yaml closes Kafka gap without a parser keystone.

These reduce Tier-1 from ~10 days (v0.1 estimate) to **~6.5 days** with higher confidence.

---

*Plan v1.1 — paired with TIER1_CONTRACT_STANDARDS_REQUIREMENTS v0.2. Ready for CRP review (`/new-cnvrg-rvw-prmpt`) before implementation.*
