# Deterministic Contract Standards — Coverage Matrix (most coverage, least work)

> **Date:** 2026-06-19  
> **Map:** [DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md](../deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md), [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](../OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md) §4–§5, StartD8 5 `LanguageProfiles`  
> **Baseline:** shipped `backend_codegen` + `frontend_codegen` (Prisma keystone), `scaffold_codegen`, `migration_codegen` (CLI only), `deploy_harness/smoke.py` (OpenAPI body synth), benchmark `demo.proto` corpus  
> **Question answered:** Which contract standards close the most **deterministic assembly + polyglot + OTel landscape** gaps for the least implementation work?

---

## 1. How to read this doc

"Coverage" = dimensions unlocked: HTTP API surface, RPC stubs, async messaging, SQL migrations, JSON Schema reuse, OTel instrumentation patterns, skip-hook ownership, drift gates, benchmark corpus fit.

"Work" = effort to **ship owned $0 emitters + gates** (not merely to *use* the standard at runtime).

Scoring legend:

- **Coverage:** ★ (1 gap) → ★★★★★ (many gaps / whole landscape section)
- **Work:** ⚡ (hours) → 🔨 (half-day) → 🔨🔨 (1–2 days) → 🔨🔨🔨 (multi-day / per-language ramp)

**Keystone rule:** Prisma `schema.prisma` remains the data SOT; other standards are **projections** or **explicit overlays** — never competing keystones.

---

## 2. The map — contract standards → coverage

| Standard / technology | Landscape / SDK § unlocked | Closes baseline gap | Shipped today | Coverage | Work |
| --- | --- | --- | --- | ---: | ---: |
| **Prisma schema** (keystone) | Data model, CRUD spine | — (baseline) | ✅ `backend_codegen`, `frontend_codegen` | ★★★★★ | — |
| **OpenAPI 3** (static output, Role 1) | §5.2 HTTP; harness smoke; typed clients | Runtime-only `/openapi.json`; `expected_routes` never auto-wired | 📋 specced (`OPENAPI_ROLE1_*`); **not implemented** | ★★★★ | 🔨🔨 |
| **JSON Schema** (shared resolver) | OpenAPI components; smoke synth; test fixtures | Logic duplicated in `deploy_harness/smoke.py` only | ⚡ partial (smoke functions, not shared lib) | ★★★ | ⚡ |
| **Alembic / SQL DDL** (contract deltas) | §5.5 database lifecycle | Scaffold emits ini/env; **no owned revision chain** | ⚡ `migration_codegen` + `generate migrate` CLI; no provider/drift | ★★★ | 🔨 |
| **Protocol Buffers + gRPC** | §5.3 RPC; polyglot benchmark corpus | LLM-authored `.proto` + build-time stubs; no `ProtoStubProvider` | ⚡ vendored `demo_pb2`; lang dep hints only | ★★★★★ | 🔨🔨🔨 |
| **OTel semconv templates** | §2–§6 signals + §5 patterns | SDK `otel_conventions.py` is pipeline-only; apps lack bootstrap | ⚡ lang profile import templates; observability artifacts are post-deploy | ★★★★ | 🔨🔨 |
| **AsyncAPI + CloudEvents** | §5.4 messaging | No Kafka/event contract layer | ❌ | ★★★★ | 🔨🔨🔨 |
| **W3C Trace Context** (middleware) | §4.2 propagation | Implicit in framework; not owned artifact | ⚡ framework default | ★★ | ⚡ |
| **OTLP / Collector YAML** | §4.1, §7.1 | Manual compose | ⚡ `observability/artifact_generator` (Grafana/Loki) | ★★ | 🔨 |
| **GraphQL SDL** | §5.6 GraphQL | Not in greenfield spine | ❌ | ★★ | 🔨🔨🔨 |
| **OpenFeature / flagd** | §5.6 feature flags | Not in spine | ❌ | ★★ | 🔨🔨 |

Legend: ✅ shipped · 📋 designed · ⚡ partial · ❌ absent

---

## 3. Quick-win tiers (ranked by coverage ÷ work)

### Tier 0 — Hours (extract / wire existing code)

| # | Win | Unlocks | Why it's cheap |
| --- | --- | --- | --- |
| 0.1 | **Extract `smoke.py` schema resolver** → `startd8/schema_contract/` | Shared JSON Schema `$ref`/`allOf`/synth for OpenAPI + tests + harness | ~300 lines already written + unit-tested |
| 0.2 | **OpenAPI `ROUTE_MANIFEST` + boot_smoke wiring** (Role 1 M0) | C-6 route regression; auto `expected_routes` | ~10-line consumer change; emitter mirrors `crud_generator` |
| 0.3 | **`generate migrate --check` in backend drift path** | Surfaces pending schema deltas at `--check` time | CLI + `next_revision()` already exist |
| 0.4 | **`app.yaml` OTel bootstrap block** in scaffold | OTLP endpoint + resource attrs; aligns with OTel Demo compose | Extend existing `scaffold_codegen/renderers.py` |

**Tier 0 payoff:** shared schema kernel + immediate C-6 strengthening + migration visibility — **before** any new contract family.

### Tier 1 — Half-day to 2 days (full Tier-1 program — this doc's requirements scope)

| # | Win | Unlocks | Effort note |
| --- | --- | --- | --- |
| 1.1 | **OpenAPI Role 1 full module** (`openapi_contract.py` + contract tests) | Owned HTTP surface; FR-10 harness compat; optional `httpx` client | Adopt `OPENAPI_ROLE1_PLAN.md` M0–M2 |
| 1.2 | **Prisma → JSON Schema projection** (entity DTOs) | Single type algebra for OpenAPI components + smoke + fixtures | Reuse `_PY_SCALAR` / prisma_parser; feeds 1.1 |
| 1.3 | **Migration provider + baseline revision** | Owned Alembic chain; drift on `alembic/versions/*.py` | Wire `migration_codegen` into provider registry |
| 1.4 | **OTel pattern templates** (manifest-declared HTTP/gRPC/DB) | §5.1–§5.5 app instrumentation bootstrap | Python-first; extend per LanguageProfile |
| 1.5 | **Proto service skeleton provider** (not protoc output) | gRPC server stub + health + build manifest for 5 langs | Regex proto parse like `go_parser`; protoc stays build gate |
| 1.6 | **`events.yaml` minimal overlay** (AsyncAPI-shaped, not full parser) | §5.4 Kafka producer/consumer stubs (Python first) | Channel + payload ref; defer AsyncAPI 3.x validator |

### Tier 2 — Multi-day (defer until Tier 1 lands)

| # | Win | Unlocks | Why heavier |
| --- | --- | --- | --- |
| 2.1 | **Full AsyncAPI 3.x ingest** | Brownfield event contracts | Parser + reconciliation with Prisma |
| 2.2 | **protoc-owned stub files** (all languages) | Byte-stable `*_pb2.py` / Go pb | Toolchain pinning per language; C#/Java build-time gen |
| 2.3 | **AST-driven OTel auto-instrumentation** | Zero-config pattern detection | Needs resolver; build on Python capability index |
| 2.4 | **GraphQL SDL provider** | §5.6 GraphQL | New keystone overlay + resolver codegen |
| 2.5 | **OpenAPI Role 2** (input contract) | Brownfield HTTP surface | Two-contract reconciliation |

---

## 4. Two lenses

### 4.1 Applicational completion (bucket 1 — $0 LLM)

Ranked by gap closed per unit work:

1. **OpenAPI Role 1** (1.1) — completes the HTTP contract layer the spine already implies.
2. **JSON Schema shared kernel** (0.1 + 1.2) — DRY for OpenAPI, smoke, tests (biggest hidden duplication today).
3. **Migration provider** (1.3) — `migration_codegen` exists but is invisible to drift/skip-hook.
4. **Proto skeleton provider** (1.5) — highest polyglot ROI; scoped to skeleton not protoc output.
5. **OTel templates** (1.4) — manifest-driven; avoids premature AST inference.
6. **events.yaml overlay** (1.6) — closes messaging gap incrementally.

### 4.2 OTel landscape alignment

Ranked by §5 pattern coverage:

1. **HTTP** — OpenAPI Role 1 (1.1).
2. **RPC/gRPC** — proto skeleton (1.5).
3. **Database** — migration provider (1.3) + SQLAlchemy bootstrap in OTel templates (1.4).
4. **Messaging** — events overlay (1.6).
5. **Propagation** — W3C middleware snippet in OTel templates (0.4).

---

## 5. Recommended sequence (coverage curve)

```
Week 0 ── Tier 0 (0.1→0.4): schema_contract extract, OpenAPI M0, migrate --check hook, OTel scaffold block
          → shared kernel + C-6 + migration visibility                    [~1 day, highest ROI]
          │
Week 1 ── Tier 1.1–1.3: OpenAPI full module, JSON Schema projection, migration provider
          → HTTP contract owned + SQL lifecycle owned                     [~3 days]
          │
Week 2 ── Tier 1.4–1.5: OTel pattern templates (Python), proto skeleton (Python + Go)
          → instrumentation bootstrap + RPC benchmark path              [~3–4 days]
          │
Week 3 ── Tier 1.6: events.yaml overlay (Python Kafka stubs)
          → §5.4 messaging pattern                                        [~2 days]
          │
Later  ── Tier 2 on demand (full AsyncAPI, protoc-owned stubs, GraphQL, Role 2)
```

**~70% of Tier-1 value is reachable by end of Week 1** — mostly wiring and projection from the existing Prisma keystone.

---

## 6. Coverage delta — before vs after Tier 1

| Dimension | Baseline (today) | After Tier 0 | After Tier 1 (full) |
| --- | --- | --- | --- |
| Data keystone | Prisma → models/CRUD/HTMX/Zod | same | same |
| HTTP contract | runtime `/openapi.json` only | + route manifest + boot_smoke | + owned OpenAPI dict + contract tests |
| JSON Schema | harness-local | shared `schema_contract` | + Prisma DTO projection |
| SQL migrations | alembic plumbing only | `--check` pending hint | owned revisions + drift provider |
| gRPC / proto | LLM + vendored stubs | same | skeleton provider + health (Py/Go+) |
| OTel app bootstrap | none | scaffold OTLP block | pattern templates (HTTP/gRPC/DB) |
| Messaging | none | none | `events.yaml` → Kafka stubs (Python) |
| Skip-hook kinds | 5 providers | same | + openapi, migration, proto-skeleton, events |
| OTel landscape §5 | HTTP (partial), gRPC (benchmark only) | + propagation config | + DB lifecycle, messaging stubs |

---

## 7. Caveats

- **OpenAPI Role 1 is specced separately** — this matrix treats it as Tier-1 workstream A; do not fork a second spec (`OPENAPI_ROLE1_REQUIREMENTS.md` remains authoritative for HTTP details).
- **protoc output ≠ owned artifact** for Java/C# — build-time generation stays the compile gate; Tier 1 owns **skeleton + manifest**, not `*_pb2.java` bytes.
- **AsyncAPI full compliance** is Tier 2 — Tier 1 uses a minimal `events.yaml` overlay to avoid a second parser keystone.
- **Default-on churn** — new owned kinds change every app's artifact tree (same acceptance as health endpoint default-on).

---

## 8. Bottom line

| Want the most deterministic coverage for the least work? Do this first: |
| --- |
| **1. Extract shared JSON Schema resolver + ship OpenAPI Role 1 M0–M2** → HTTP surface owned, harness DRY, C-6 auto-wired. |
| **2. Register migration revisions on the provider registry** → SQL lifecycle joins the drift model. |
| **3. Add manifest OTel bootstrap + proto skeleton provider (Python/Go)** → instrumentation + RPC without full protoc ownership. |
| **4. Introduce `events.yaml` overlay last** → messaging closes §5.4 incrementally. |

---

## 9. References

1. [DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md](../deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md) — kernel thesis  
2. [OPENAPI_ROLE1_REQUIREMENTS.md](../deterministic-openapi/OPENAPI_ROLE1_REQUIREMENTS.md) — HTTP workstream detail  
3. [OPENAPI_ROLE1_PLAN.md](../deterministic-openapi/OPENAPI_ROLE1_PLAN.md) — HTTP implementation plan  
4. [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](../OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md) — pattern coverage axes  
5. [PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md](../PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md) — static→OTel crosswalk  
6. `src/startd8/migration_codegen/generator.py` — additive Alembic delta engine (shipped, unwired to provider)  
7. `src/startd8/deploy_harness/smoke.py` — JSON Schema resolution (extract candidate)
