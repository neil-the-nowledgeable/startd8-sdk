# Tier-1 Deterministic Contract Standards — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-19
**Status:** Planned — pre-implementation; ready for CRP
**Owner:** SDK / contract codegen
**Motivated by:** [CONTRACT_STANDARDS_COVERAGE_MATRIX.md](./CONTRACT_STANDARDS_COVERAGE_MATRIX.md)
**Paired plan:** [TIER1_CONTRACT_STANDARDS_PLAN.md](./TIER1_CONTRACT_STANDARDS_PLAN.md)
**HTTP detail (by reference):** [OPENAPI_ROLE1_REQUIREMENTS.md](../deterministic-openapi/OPENAPI_ROLE1_REQUIREMENTS.md)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real codebase
> (`backend_codegen`, `migration_codegen`, `deploy_harness/smoke.py`, `scaffold_codegen`,
> `LanguageProfiles`, benchmark `demo.proto`). **9 corrections** — v0.1 was appropriately premature.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|-------------------|--------|
| OpenAPI Role 1 needs a new spec | `OPENAPI_ROLE1_REQUIREMENTS.md` v0.2 + plan already exist; **`openapi_contract_renderer.py` not on disk** | Workstream **A adopts** existing FR-1…FR-10 verbatim; Tier-1 program tracks **implementation**, not re-spec |
| JSON Schema needs a greenfield parser | `deploy_harness/smoke.py` already implements `$ref`/`allOf`/synth (~300 lines, unit-tested) | Workstream **B = extract first** (`startd8/schema_contract/`); Prisma projection **consumes** shared resolver |
| Migrations are unbuilt | `migration_codegen/generator.py` + `startd8 generate migrate` **already ship**; tests exist | Workstream **C = provider + drift + baseline**, not a new delta engine |
| Migrations should auto-run on every `generate backend` | `next_revision()` writes files; auto-emit surprises operators mid-sprint | FR-C3: **`generate migrate`** remains explicit; `--check` surfaces pending state from backend drift |
| Proto Tier-1 means protoc-owned `*_pb2.*` bytes | C#/Java generate stubs at **`dotnet build` / Gradle** time; owning bytes fights toolchain | FR-E1: Tier-1 owns **skeleton + build manifest + health**; protoc output stays **compile-gate verified**, not drift-owned |
| Full `.proto` parser required | `go_parser.py` regex pattern works for benchmark `demo.proto` shape | FR-E2: **minimal proto extractor** (services, rpcs, messages, fields) — sufficient for skeleton emit |
| OTel Tier-1 = AST auto-instrumentation | Python capability index is **hypothesis-only**; false positives on `.get(` | FR-D1: v1 is **`app.yaml`-declared patterns** only; AST-driven emit deferred Tier 2 |
| OTel = new artifact_generator | `observability/artifact_generator` is **post-deploy Grafana/Loki** — different layer | FR-D2: app bootstrap lives in **`scaffold_codegen` + `app/telemetry.py`**; does not extend artifact_generator |
| Full AsyncAPI 3.x parser in Tier-1 | No parser, no corpus; Kafka gap is **pattern** not spec compliance | FR-F1: **`events.yaml` overlay** (channels + payload refs); AsyncAPI validator Tier 2 |
| Six independent providers | Shared **JSON Schema type algebra** must feed OpenAPI + smoke + events payloads | FR-B1: `schema_contract` is a **library**, not a provider; providers consume it |

**Resolved open questions:**
- **OQ-1 → Prisma remains sole data keystone.** OpenAPI, JSON Schema, migrations, events overlay are projections/overlays.
- **OQ-2 → Default-on for OpenAPI + migration baseline** (applicational completion); proto/events **opt-in via manifest** (polyglot/brownfield).
- **OQ-3 → Sequencing:** Tier 0 extract → OpenAPI M0–M2 → migration provider → OTel scaffold → proto skeleton → events overlay.
- **OQ-4 → Language ramp:** Python first for OTel templates + events; proto skeleton **Python + Go** in Tier-1; Java/C#/Node follow Tier-1.1.
- **OQ-5 → Single `DeterministicFileProvider` per family** (`openapi`, `migration`, `proto-skeleton`, `events`) registered on existing entry-point group.

**Quick wins surfaced by planning (not evident pre-plan):**
1. **Extract `smoke.py` resolver** — zero new algorithm work; immediately unblocks OpenAPI FR-10 + shared tests.
2. **OpenAPI M0 (`ROUTE_MANIFEST` only)** — ~70% of Role-1 user value before `OPENAPI_SPEC` dict exists.
3. **`generate migrate --check` hooked from `generate backend --check`** — migration pending visible with no new CLI command.
4. **Baseline Alembic revision on first migrate** — scaffold already emits `alembic/` plumbing but empty `versions/`; one call closes SQL lifecycle gap.
5. **Reuse `LanguageProfile` grpc/otel import templates** in proto/OTel emitters — don't duplicate dep strings from `languages/*.py`.

---

## 1. Problem Statement

StartD8's deterministic cascade owns the **Prisma → app spine** (models, CRUD, HTMX, scaffold) but stops short of the **contract standards layer** that polyglot microservices and the OTel landscape require. OpenAPI is runtime-only; JSON Schema logic is harness-local; migrations are CLI-orphaned; gRPC remains LLM-authored; app OTel bootstrap is absent; messaging has no contract path.

| Component | Current state | Gap |
|-----------|--------------|-----|
| HTTP / OpenAPI | FastAPI serves live spec; Role 1 **specced, not built** | No owned route manifest, drift, or contract tests |
| JSON Schema | `smoke.py` only | Duplicated logic; no Prisma DTO projection |
| SQL migrations | `migration_codegen` + `generate migrate` | Not on provider registry; no baseline auto-emit; drift ignores revisions |
| gRPC / proto | Benchmark vendored stubs; lang dep hints | No skeleton provider; LLM owns service shape |
| OTel app instrumentation | Pipeline `otel_conventions.py` only | Generated apps lack pattern bootstrap |
| Async / events | — | §5.4 messaging uncovered |

**Objective:** Fully implement **Tier 1** from the coverage matrix — six workstreams sharing a JSON Schema kernel — maximizing $0 owned assembly across the 5 LanguageProfiles.

---

## 2. Goals & Non-Goals

**Goals**
- Shared **`schema_contract`** library extracted from harness code.
- **OpenAPI Role 1** implemented per paired spec (static emitter, boot_smoke, contract tests).
- **Migration provider** with drift, baseline revision, `--check` integration.
- **`app.yaml` OTel bootstrap** + pattern templates (HTTP, gRPC, DB) for Python apps.
- **Proto skeleton provider** (Python + Go v1) with health check wiring.
- **`events.yaml` overlay** emitting Python Kafka producer/consumer stubs.
- All new artifacts: provenance headers, `DeterministicFileProvider` registration, compile/build gates.

**Non-Goals (Tier 1)**
- OpenAPI Role 2/3 (input contract, inter-context promotion).
- protoc-output byte ownership for Java/C#/Node.
- Full AsyncAPI 3.x ingest + validator.
- AST-inferred OTel instrumentation.
- GraphQL SDL provider.
- TypeScript OpenAPI client (deferred per Role 1 spec).

---

## 3. Requirements by workstream

### Workstream A — OpenAPI Role 1 (by reference + program tracking)

Tier-1 **implements** the existing spec without modification:

- **FR-A1** Satisfy **FR-1 through FR-10** in `OPENAPI_ROLE1_REQUIREMENTS.md` v0.2.
- **FR-A2** Milestones M0–M2 from `OPENAPI_ROLE1_PLAN.md` are Tier-1 **exit criteria** for workstream A; M3 (httpx client) optional same increment.
- **FR-A3** OpenAPI emitter **must import** `schema_contract` for `components.schemas` field typing (no duplicate scalar maps).

### Workstream B — JSON Schema shared kernel

- **FR-B1** Extract pure functions from `deploy_harness/smoke.py` into **`startd8/schema_contract/`**:
  - `resolve_schema`, `synthesize_body`, `select_crud_resource`, `_deref`, format/enum/nullable handling.
  - Harness imports the library; smoke behavior unchanged (regression tests required).
- **FR-B2** Add **`prisma_to_json_schema.py`**: project each entity's Create/Read/Update DTO to JSON Schema objects using the same rules as OpenAPI emitter (single source of scalar/required/nullable mapping).
- **FR-B3** Unit tests: fixture specs exercising each mandatory JSON Schema feature from harness FR-9; Prisma wireframe golden schemas.

### Workstream C — Migration provider

- **FR-C1** New kinds: `alembic-revision` (files under `alembic/versions/*.py` with `# startd8-artifact:` header).
- **FR-C2** New **`MigrationFileProvider`** on `deterministic_providers` entry point; `owns()` / `is_in_sync()` via re-render from embedded snapshot chain (`migration_codegen.latest_snapshot` + `plan_migration`).
- **FR-C3** `startd8 generate backend --check` invokes **`generate migrate --check`** logic; exit message names pending revision when schema delta exists.
- **FR-C4** Document + test **baseline path**: first `startd8 generate migrate` on fresh scaffold emits initial revision from full schema (uses existing `plan_migration(..., None)`).
- **FR-C5** Migration notes (drops, type changes) surface in CLI stdout; never silently auto-migrate destructive ops (preserve existing `plan_migration` safety).

### Workstream D — OTel app bootstrap + pattern templates

- **FR-D1** Extend **`app.yaml`** schema (`scaffold_codegen/manifest.py`) with optional `telemetry:` block:
  - `enabled: bool`, `otlp_endpoint: str`, `service_name: str`, `patterns: list[str]` where values ∈ `{http, grpc, db, messaging}`.
- **FR-D2** Emit **`app/telemetry.py`** (kind `python-app-telemetry`) when `telemetry.enabled` — OTLP exporter bootstrap, resource attrs, W3C propagator; mirrors OTel Demo defaults (4317 gRPC or 4318 HTTP configurable).
- **FR-D3** For each declared pattern, emit deterministic import + middleware/hook snippets:
  - `http` → FastAPI OTel middleware instrumentation imports.
  - `grpc` → server interceptor imports (stub-compatible with workstream E).
  - `db` → SQLAlchemy/SQLModel instrumentor import block.
  - `messaging` → placeholder hook when workstream F present.
- **FR-D4** Register kinds in scaffold provider + drift; default **`telemetry.enabled: false`** (SOTTO — absent block ⇒ no telemetry files).
- **FR-D5** Extend **`scaffold_codegen`** compose/env template with optional OTLP env vars when telemetry enabled.

### Workstream E — Proto skeleton provider

- **FR-E1** New **`proto_codegen/`** package with **`ProtoSkeletonProvider`** (entry point `proto-skeleton`).
- **FR-E2** Minimal **`parse_proto()`** extracting `service`, `rpc`, `message`, scalar field types from `.proto` text (benchmark `demo.proto` + single-service protos are conformance fixtures).
- **FR-E3** For each `(proto_file, service_name, language)` declared in seed/manifest, emit **owned skeleton** files:
  - Python: `*_server.py` gRPC servicer stub + `grpc.health.v1` registration + `serve()` entry.
  - Go: `*_server.go` skeleton + health service registration.
  - (Tier-1.1: Java, C#, Node — same pattern; not blocking Tier-1 exit.)
- **FR-E4** Emit/update **build manifest fragments** using existing `LanguageProfile` grpc dependency templates (`languages/go.py`, `csharp.py`, etc.) — no duplicated dep strings.
- **FR-E5** Drift: re-render skeleton from proto text hash; **do not** own protoc-generated `*_pb2.*` outputs.
- **FR-E6** Gate: language `syntax_check` / compile on skeleton; optional `grpc_tools.protoc` check when `.proto` present (unavailable ⇒ non-pass).
- **FR-E7** Opt-in: manifest key `grpc.services: [{proto, service, language}]` or seed task metadata `transport_protocol: grpc`.

### Workstream F — Events overlay (AsyncAPI-shaped minimal)

- **FR-F1** New optional manifest **`events.yaml`**:
  ```yaml
  channels:
    order_paid:
      direction: publish  # publish | subscribe
      topic: orders.paid
      payload: OrderRead  # Prisma model name OR inline schema_contract ref
  ```
- **FR-F2** Emit **`app/events/`** Python modules (kinds `python-events-producer`, `python-events-consumer`) using `aiokafka` or `kafka-python` imports per scaffold `app.yaml` `messaging.backend` (default `aiokafka`).
- **FR-F3** Payload serialization uses **`schema_contract` + prisma_to_json_schema** for Prisma-ref payloads.
- **FR-F4** CloudEvents envelope attributes (`type`, `source`, `id`, `specversion`) emitted as constants on producer stub.
- **FR-F5** Register **`EventsFileProvider`**; opt-in only (missing `events.yaml` ⇒ byte-identical absent).
- **FR-F6** Contract tests: producer stub serializes payload matching JSON Schema; no live broker required.

---

## 4. Cross-cutting requirements

- **FR-X1** All new renderers follow **`_headers.py` / provenance** conventions (`schema-sha256` or `proto-sha256` or manifest hash).
- **FR-X2** Conditional kwargs threading in `drift._renderers()` must mirror `assembler` manifest guards (lesson FR-ED-16).
- **FR-X3** Absent toolchain for gates ⇒ **`unavailable` ⇒ non-pass**, never silent PASS.
- **FR-X4** Tier-1 exit: full unit test suite green; each workstream has ≥1 integration test on wireframe/golden fixture.
- **FR-X5** Update **`docs/capability-index/`** capability entries for new `$0` codegen kinds (follow capability-index skill separately).

---

## 5. Non-Requirements

- Replacing Prisma with OpenAPI/AsyncAPI as data SOT.
- Live DB migration execution (`alembic upgrade`) — operator-owned (FR-MG-4 preserved).
- Kafka broker in unit tests.
- Generating real business logic inside gRPC handlers or event consumers.
- Polyglot events (Python only v1).

---

## 6. Open Questions (remaining)

- **OQ-6** Should OpenAPI `components.schemas` reference **`prisma_to_json_schema` output** directly or a trimmed CRUD subset? *(Lean: CRUD subset matching Create/Read/Update only.)*
- **OQ-7** Proto skeleton: **one file per service** or **one file per RPC** for MicroPrime compatibility? *(Lean: one servicer class per service, RPC methods as stubs.)*
- **OQ-8** ✅ RESOLVED (shipped): default is **`aiokafka`** (async FastAPI alignment); OTel instrumentation is **backend-driven** — `kafka-python` uses the official `KafkaInstrumentor`, while `aiokafka` (no upstream auto-instrumentor) emits import-guarded **manual** PRODUCER/CONSUMER spans + W3C tracecontext via the CloudEvents envelope.

---

## 7. Success Metrics

| Metric | Target |
|--------|--------|
| OpenAPI Role 1 | FR-A1 satisfied; boot_smoke auto-routes; contract tests in CI |
| schema_contract | Harness + OpenAPI + events share one module; zero duplicate resolver |
| Migrations | Fresh app baseline revision; `--check` reports pending delta |
| OTel bootstrap | Wireframe app with `telemetry.enabled` exports traces to local collector |
| Proto skeleton | Benchmark seed generates compiling Python+Go gRPC server skeleton from `demo.proto` |
| Events overlay | `events.yaml` wireframe produces importable producer module + schema-valid payload |
| Cost | All Tier-1 artifacts $0 LLM skip-hook eligible when in-sync |

---

*v0.2 — Post-planning self-reflective update. 2 workstreams narrowed (migrations wiring not rewrite; proto skeleton not protoc bytes), 1 deferred (AST OTel), 1 simplified (events overlay not AsyncAPI parser), 5 quick wins added, 5 open questions resolved, 3 remaining.*
