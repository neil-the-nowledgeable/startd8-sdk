# OTel Demo Python Rebuild (Steps 1–6) — OpenAPI-Leveraged Requirements

**Version:** 0.1 (Pre-planning — post OpenAPI Role 1+2 merge review)
**Date:** 2026-06-19
**Status:** Planned — ready for CRP / cap-dev-pipe
**Owner:** SDK / otel-demo-corpus + backend_codegen
**Builds on:**
[OTEL_DEMO_PYTHON_CAPABILITY_GAPS_AND_REBUILD_SOURCES.md](../python-capability-index/OTEL_DEMO_PYTHON_CAPABILITY_GAPS_AND_REBUILD_SOURCES.md),
[TIER1_CORPUS_REQUIREMENTS.md](./TIER1_CORPUS_REQUIREMENTS.md),
[OPENAPI_LEVERAGE_ANALYSIS.md](../deterministic-openapi/OPENAPI_LEVERAGE_ANALYSIS.md) (Roles 1–3)
**Companion plan:** [OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md](./OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md)
**Implementation branch:** `feat/otel-python-rebuild-openapi` (from `feat/otel-demo-corpus`)

---

## 0. OpenAPI leverage review (recent changes)

Planning Steps 1–6 against the **shipped** OpenAPI stack (merged via PR #28–#29 on
`feat/otel-demo-corpus`) and the **planned** Role 3 inter-context seam.

### 0.1 Shipped — Role 1 (static contract output)

| Capability | Location | Relevance to Steps 1–6 |
| --- | --- | --- |
| `app/openapi_contract.py` | `openapi_contract_renderer.py` | Owned `ROUTE_MANIFEST` + `OPENAPI_SPEC` dict — drift-checked offline |
| Contract tests | `test_emitter.render_openapi_contract_tests` | Catches router/surface drift without booting app |
| Spec validation gate | `validators/openapi_spec_gate.py` | `--gate` uses `openapi-spec-validator`; absent ⇒ non-pass |
| Typed httpx client | `openapi_client_renderer.py` → `clients/http_client.py` | Consumer for HTTP steps (email, locust, BFF) |
| Boot-smoke wiring | `boot_smoke` reads `ROUTE_MANIFEST` | Auto `expected_routes` — no manual route lists |
| Schema resolution | `openapi_contract/schema_resolve.py` | Shared with deploy harness smoke CRUD |
| `--export-openapi` | `cli_generate.py` | JSON export for cross-repo / OTel fixture handoff |

**Design constraint carried forward:** static projection is SOT; live `/openapi.json` is
**conformance only** — not the drift authority (`OPENAPI_ROLE1_REQUIREMENTS.md` FR-1).

### 0.2 Shipped — Role 2 (api.yaml overlay input)

| Capability | Location | Relevance to Steps 1–6 |
| --- | --- | --- |
| `api.yaml` overlay merge | `openapi_contract_renderer.render_openapi_contract(..., api_text=)` | Declare **non-CRUD HTTP routes** without forking drift |
| Additive merge | `merge_openapi_specs` | Base Prisma CRUD preserved; overlay adds paths only |
| Validation-only mode | overlay without handler gen | Contract-first for brownfield ports (email Sinatra route) |
| Conditional routes (Role 1 FR-3) | `_conditional_routes()` in contract renderer | AI/pages/flows paths when manifests exist |
| Overlay client methods | `openapi_client_renderer` | httpx methods when `$ref` resolves to Prisma DTOs |

**Design constraint:** overlay declares **surface** (bucket 1); handler bodies stay bucket 3
(`user_routers.py` / Prime integration pass) per `IDEAL_TARGET_ARCHITECTURE.md` §3.

### 0.3 Planned — Role 3 (inter-context seam)

Role 3 (`OPENAPI_ROLE3_REQUIREMENTS.md`, branch `feat/openapi-role3-context` on worktree
`startd8-openapi-role1`) adds `contexts.yaml`, producer-hash consumer clients, and cross-context
deploy smoke. Steps 1–6 **prime** this seam: OTel Demo is a polyglot mesh where Python services
consume HTTP (email) and gRPC (payment, cart) from other contexts.

| Role 3 FR | Step beneficiary |
| --- | --- |
| FR-1 inter-context manifest | Checkout (producer) → email (consumer); frontend → product-reviews |
| FR-3 consumer client gen | Locust load-gen typed client to email HTTP (replaces shallow import-only HTTP) |
| FR-4 producer contract hash | Pin OTel fixture specs across rebuild iterations |

**Worktree note:** `~/Documents/dev/startd8-openapi-role1` was **6 commits behind** `origin/main`
at planning time — refresh before merging Role 3 with this rebuild track.

### 0.4 Planning discoveries (OpenAPI × OTel rebuild)

| Assumption | Discovery | Impact |
| --- | --- | --- |
| All six steps need OpenAPI codegen | Steps **1, 2, 4, 6** are **gRPC-primary** (proto contract) | OpenAPI applies to HTTP adjuncts + consumer clients; gRPC uses `ProtoStubProvider` / seeds |
| Email port is ad-hoc FastAPI | Role 2 **validation-only overlay** fits Sinatra `POST /send_order_confirmation` exactly | Step 3 = schema.prisma spine + `api.yaml` overlay + bucket-3 handler |
| Locust HTTP depth = edit locustfile only | Role 1 **ApiClient** + Role 3 consumer gen gives typed `.post()` with contract hash | Step 3 consumer + Wave 0.3 locust deepening share one client artifact |
| Kafka ports need OpenAPI | Kafka has **no** OTel §5 OpenAPI mapping | Steps 1–2 close **capability-index messaging** + Plan Ingestion imports; OpenAPI optional `/health` only |
| Payment port = duplicate Node | Python **leaf gRPC** seed unlocks first **behavioral-eligible** Python OTel cell | Step 6 uses proto seed pattern (existing matrix), not OpenAPI |
| product-reviews GenAI = inline OpenAI only | `llm/app.py` is **Flask HTTP**; merge can expose **both** gRPC RPC + HTTP summary route via overlay | Step 5 splits: gRPC in server, HTTP in overlay or separate context |

---

## 1. Problem statement

OTel Demo Python sources cover **56%** of the Python capability index but miss **messaging**,
**Redis**, and **deep HTTP**, and both Python OTel benchmark seeds are **structural-only**
(`behavioral_eligible: false`). Non-Python services already implement the missing patterns.

Steps 1–6 port those patterns into Python **reference implementations** inside the SDK repo
(fixtures + seeds + capability-index corpus), leveraging the new OpenAPI stack where the ported
surface is HTTP and the existing proto stack where it is gRPC.

| Gap (from gap analysis) | Step | OpenAPI role |
| --- | --- | --- |
| No messaging (`PY-OTEL-5.4`) | 1, 2 | Adjunct health only |
| Shallow HTTP (false `.get(` hits) | 3 | **Role 2 overlay + Role 1 contract** |
| No Redis DB branch | 4 | — (gRPC + redis client) |
| GenAI omitted from seeds | 5 | Optional HTTP overlay for llm routes |
| No behavioral Python OTel seed | 6 | — (gRPC proto) |
| Plan Ingestion import patterns | 1–4 | `api.yaml` + static spec feed query enrichment |
| Prime Contractor Python depth | 3, 6 | HTTP seed + leaf gRPC seed |

**Goal:** six incremental Python ports (or merges) that raise capability-index coverage toward **~70%**,
produce Prime Contractor / Plan Ingestion fixtures, and use OpenAPI Roles 1–2 (and Role 3 where
ready) for every HTTP boundary — without duplicating the Tier 1 mistake of claiming Kafka benchmark cells.

---

## 2. Scope — the six steps

| Step | Source (OTel Demo) | Target | Primary index / workflow unlock |
| ---: | --- | --- | --- |
| **1** | `accounting` (C#) | `fixtures/otel-demo/accounting-py/` | Messaging consumer + SQLAlchemy; Plan Ingestion kafka/sql |
| **2** | `checkout` Kafka producer (Go) | `fixtures/otel-demo/checkout-kafka-py/` | Messaging producer spans; structural fixture only (NR-2) |
| **3** | `email` (Ruby Sinatra) | `fixtures/otel-demo/email-py/` + **`api.yaml`** | Real HTTP server; OpenAPI contract + ApiClient; capability HTTP depth |
| **4** | `cart` (C#) | `fixtures/otel-demo/cart-py/` | Redis/Valkey; gRPC `CartService` Python seed candidate |
| **5** | `llm` → `product-reviews` (Python) | Extend fixture + seed RPC | GenAI depth; optional `AskProductAIAssistant` seed |
| **6** | `payment` (Node) | `fixtures/otel-demo/payment-py/` | First **behavioral-eligible** Python OTel gRPC seed |

Fixtures live under `fixtures/otel-demo/` (or `examples/otel-demo-python/`) as **SDK-owned**
reference ports — not modifications to the upstream `opentelemetry-demo` clone.

---

## 3. Functional requirements

### Cross-cutting (all steps)

- **FR-X1 — Fixture isolation.** Ports MUST NOT modify upstream OTel Demo; sources are read-only
  references (tag `2.2.0`). Provenance header cites source file + commit/tag.
- **FR-X2 — Capability resolver regression.** After each step, `analyze_otel_demo_python_coverage.py`
  MUST be runnable against the **union** of fixture tree + existing demo Python (or fixture-only mode);
  document dimension delta in step PR.
- **FR-X3 — Contamination firewall.** Fixture code and seeds MUST pass `firewall.py` OTel corpus
  tokens rules when used as benchmark seeds (no OB bleed).
- **FR-X4 — Bucket separation.** Deterministic skeleton (bucket 1) vs integration handlers (bucket 3)
  MUST follow `IDEAL_TARGET_ARCHITECTURE.md`; OpenAPI overlay never emits business logic bodies.

### Step 1 — accounting-py (Kafka consumer + Postgres)

- **FR-1.1** Implement Kafka consumer on topic `orders` mirroring `accounting/Consumer.cs` behavior
  (protobuf parse, optional DB persist).
- **FR-1.2** Use `confluent_kafka` or `aiokafka` with static signatures matching
  `communication-crosswalk.json` `PY-OTEL-5.4-MESSAGING`.
- **FR-1.3** SQLAlchemy + asyncpg/psycopg2 models for `OrderEntity` / line items / shipping —
  deepening `PY-OTEL-5.5-DATABASE` beyond `product-reviews/database.py`.
- **FR-1.4** Emit Plan Ingestion handoff snippet: kafka + sqlalchemy import signatures for
  `derivation-handoff.md` extension.
- **FR-1.5** Structural-only benchmark metadata (`behavioral_eligible: false` — broker dep per NR-2).

### Step 2 — checkout-kafka-py (producer slice)

- **FR-2.1** Extract producer path from `checkout/main.go` (`kafka.CreateKafkaProducer`, order event publish).
- **FR-2.2** Python module with semconv-flavored span attributes matching Go (`messaging.kafka.*`).
- **FR-2.3** Document as **pattern fixture**, not gRPC seed (checkout remains Go in seeds-otel).
- **FR-2.4** NO benchmark cell registration (Tier 1 NR-2).

### Step 3 — email-py (OpenAPI-centric HTTP port)

- **FR-3.1** Model service as **deterministic FastAPI app**: minimal `schema.prisma` (OrderConfirmation
  DTO or empty tenant spine) + **`api.yaml` overlay** declaring `POST /send_order_confirmation`
  (request/response schemas from Ruby handler).
- **FR-3.2** MUST emit `app/openapi_contract.py` via `startd8 generate backend` pipeline; merged spec
  passes `openapi_spec_gate` on `--gate`.
- **FR-3.3** Handler body for confirmation email in bucket 3 (`user_routers.py` or fixture equivalent)
  mirroring `email/email_server.rb` (flagd, counter, trace attrs).
- **FR-3.4** Generate `clients/http_client.py` (Role 1) with typed `post_send_order_confirmation`;
  use in locust / integration test to replace shallow HTTP detections (Wave 0.3).
- **FR-3.5** OpenFeature/flagd calls MUST match `PY-OTEL-5.6-FEATURE-FLAGS` with import **and** call hits.
- **FR-3.6** FastAPI/Starlette imports MUST satisfy `PY-OTEL-5.1-HTTP` without false `.get(`-only match
  (resolver tightening in Wave 0.2 coordinated here).
- **FR-3.7** When Role 3 lands: declare checkout→email in `contexts.yaml`; consumer client carries
  producer `contract-sha256`.

### Step 4 — cart-py (gRPC + Redis)

- **FR-4.1** Port `CartService` gRPC surface from `cart/src/services/CartService.cs`.
- **FR-4.2** Valkey/Redis store mirroring `ValkeyCartStore.cs` — `redis` import signatures for DB crosswalk.
- **FR-4.3** Optional Python OTel seed extension (`seed-cart-py.json`) — structural-only (Valkey dep).
- **FR-4.4** gRPC via grpcio — deepen `PY-OTEL-5.3-RPC` with full server + stub calls (not import-only).

### Step 5 — llm → product-reviews merge (GenAI)

- **FR-5.1** Implement `AskProductAIAssistant` RPC in product-reviews fixture using patterns from
  `llm/app.py` (OpenAI + flagd + summary JSON).
- **FR-5.2** Update `gen_otel_benchmark_seeds.py` to **optionally** include RPC behind flag
  `--include-genai-rpc` (default off preserves FR-3 Tier 1 honesty).
- **FR-5.3** Optionally expose llm HTTP routes via `api.yaml` on a sibling fixture for dual HTTP+gRPC GenAI.
- **FR-5.4** Capability resolver MUST show `PY-OTEL-5.6-GENAI` with import + call in ≥2 files or
  ≥2 call sites after merge.

### Step 6 — payment-py (leaf gRPC — behavioral seed)

- **FR-6.1** Port `payment/charge.js` Charge RPC to Python grpcio server (leaf — no downstream gRPC).
- **FR-6.2** Flagd provider wiring matching Node (`get_boolean_value` / charge path).
- **FR-6.3** Register **`seed-payment-py.json`** (or repoint existing payment seed to Python target) with
  **`behavioral_eligible: true`**.
- **FR-6.4** Track-2 behavioral suite hook: reuse/extend `charge_suite.py` ground truth against Python server.
- **FR-6.5** Proto contract from `seeds-otel/demo.proto` — no OpenAPI on critical path.

---

## 4. Non-requirements

- **NR-1** — Does NOT modify upstream `open-telemetry/opentelemetry-demo` repository.
- **NR-2** — Does NOT register Kafka paths as benchmark matrix cells (Tier 1 NR-2 preserved).
- **NR-3** — Does NOT require Role 3 shipped before Steps 1–6; Step 3 FR-3.7 is conditional.
- **NR-4** — Does NOT port currency (C++), shipping (Rust), frontend-proxy, flagd-ui.
- **NR-5** — Does NOT implement ContextCore derivation tables in-repo (handoff snippets only).
- **NR-6** — Does NOT generate GraphQL (no demo source); GraphQL lane stays separate benchmark track.
- **NR-7** — Does NOT pool OTel rebuild scores with OB leaderboard.

---

## 5. Acceptance

| # | Criterion | Evidence |
| --- | --- | --- |
| A1 | Steps 1–6 fixtures exist with provenance headers | `fixtures/otel-demo/*/README.md` |
| A2 | Step 3 `startd8 generate backend --check` passes on email-py wireframe | CI log |
| A3 | Step 3 merged `OPENAPI_SPEC` validates; `POST /send_order_confirmation` in manifest | `test_openapi_contract.py` |
| A4 | Capability index overall ≥ **65%** after Steps 1–4 (resolver report) | `otel-demo-python-coverage.json` |
| A5 | Step 6 seed `behavioral_eligible: true`; dry-run cell scores Track-2 | matrix dry-run |
| A6 | Plan Ingestion handoff updated with kafka/redis/sql/fastapi signatures | `derivation-handoff.md` |
| A7 | Prime Contractor can run product-reviews + payment-py seeds without contamination fail | firewall probe |

---

## 6. Open questions

| ID | Question | Lean default |
| --- | --- | --- |
| OQ-1 | Fixture root: `fixtures/otel-demo/` vs `examples/`? | `fixtures/otel-demo/` (benchmark-adjacent) |
| OQ-2 | Step 3: empty Prisma spine vs minimal Order entity? | Minimal Order DTO entity for schema projection |
| OQ-3 | Step 5: enable GenAI RPC in seeds by default? | Off by default; `--include-genai-rpc` flag |
| OQ-4 | Merge Role 3 before Step 3 consumer client? | Step 3 uses Role 1 client; Role 3 upgrades hash pinning |
| OQ-5 | Resolver false-positive fix (HTTP `.get(`) — separate PR or Step 3? | Step 3 PR includes matcher tighten (Wave 0.2) |

---

*Steps traced to [OTEL_DEMO_PYTHON_CAPABILITY_GAPS_AND_REBUILD_SOURCES.md](../python-capability-index/OTEL_DEMO_PYTHON_CAPABILITY_GAPS_AND_REBUILD_SOURCES.md) Part 5 recommended sequence (P0–P2 items 1–6).*
