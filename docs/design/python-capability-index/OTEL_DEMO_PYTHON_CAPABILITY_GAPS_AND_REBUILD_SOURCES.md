# OTel Demo Python — Capability Gaps & Cross-Language Rebuild Sources

> **Date:** 2026-06-18  
> **Baseline:** [PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md](../PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md) · [otel-demo-python-coverage.json](./otel-demo-python-coverage.json)  
> **OTel Demo ref:** `open-telemetry/opentelemetry-demo` tag **2.2.0**  
> **Audience:** Prime Contractor benchmark corpus, Plan Ingestion / Query Prime derivation, Python capability-index expansion

---

## Executive summary

OTel Demo Python sources cover **56.0%** of the Python capability index (mean of four dimensions). Coverage is **wide but shallow**: five §5 patterns appear, but two are single-file, HTTP is mostly false-positive `.get(` hits, and **messaging / Redis / Connect / GraphQL / CLI** are absent entirely.

The demo’s **non-Python services** already implement the missing depth. The highest-value Python rebuilds port patterns from:

| Priority | Source service | Language | Rebuild as Python to close |
| --- | --- | --- | --- |
| **P0** | **accounting** | C# | Kafka consumer + PostgreSQL ORM (`PY-OTEL-5.4`, deepen `PY-OTEL-5.5`) |
| **P0** | **checkout** (Kafka producer path) | Go | Kafka producer spans (`PY-OTEL-5.4`) |
| **P1** | **email** | Ruby | Real HTTP server + flags (`PY-OTEL-5.1`, deepen flags) |
| **P1** | **cart** | C# | Valkey/Redis client (`PY-OTEL-5.5` redis branch) |
| **P1** | **llm** + **product-reviews** merge | Python→Python | Full GenAI RPC (`PY-OTEL-5.6`, unblocks `AskProductAIAssistant` seed) |
| **P2** | **fraud-detection** | Kotlin | Second Kafka consumer + async |
| **P2** | **product-catalog** | Go | Instrumented Postgres (`otelsql` → SQLAlchemy/asyncpg patterns) |
| **P2** | **payment** | Node.js | Leaf gRPC + FlagdProvider reference for locust depth |
| **P3** | **frontend** | TypeScript | FastAPI/Starlette BFF (HTTP client + server, async) |
| **P3** | **quote** | PHP | Additional gRPC leaf for MicroPrime diversity |

**Prime Contractor gap:** both existing Python OTel seeds (`recommendation`, `product-reviews`) are **structural-only** (`behavioral_eligible: false`). No Python OTel seed runs Track-2 behavioral scoring today. Rebuilds should target **leaf, dependency-free Python services** where possible (e.g. a ported `payment`-class leaf, or a kafka-free accounting slice).

**Plan Ingestion gap:** Query Prime / ContextCore derivation needs import-pattern evidence for **Kafka, Redis, SQLAlchemy/asyncpg** — absent from Python sources. Ports from **accounting**, **cart**, and **product-catalog** supply the static allowlists Plan Ingestion consumes.

---

## Part 1 — Capabilities used the least

### 1.1 Not used at all (0 files in Python corpus)

#### Communication patterns (10/15 absent)

| ID | Pattern |
| --- | --- |
| `PY-OTEL-5.2-HTTP-METRICS` | HTTP metrics (instrumentation-only) |
| `PY-OTEL-5.3-CONNECT` | Connect RPC |
| `PY-OTEL-5.4-MESSAGING` | Messaging (Kafka, Celery, …) |
| `PY-OTEL-5.6-GRAPHQL` | GraphQL |
| `PY-OTEL-5.6-FAAS` | FaaS |
| `PY-OTEL-5.7-CICD` | CI/CD |
| `PY-OTEL-5.7-CLI` | CLI (`click` / `typer` / `argparse`) |
| `PY-OTEL-5.1-DNS` | DNS |
| `PY-OTEL-5.1-OBJECT-STORE` | Object stores (S3, GCS, …) |
| `PY-OTEL-5.1-CLOUD-SDK` | Cloud provider SDKs |

#### Manifest kinds (3/9 absent)

| ID | Kind | Why absent |
| --- | --- | --- |
| `PY-MAN-006` | `property` | No `@property` methods |
| `PY-MAN-007` | `constant` | No `UPPER_CASE` module constants detected |
| `PY-MAN-009` | `type_alias` | No `TypeAlias` nodes |

#### Language composites (2/10 absent)

| ID | Composite | Meaning |
| --- | --- | --- |
| `PY-LC-007` | `generator` | No `yield` / streaming |
| `PY-LC-008` | `pattern_match` | No `match`/`case` (3.10+) |

#### AST nodes

**74 of 132** catalogued node types never appear (56% unused). Notable absences: `AsyncWith`, `While`, `Yield`, `Match`, `AnnAssign`, `TypeAlias`, `Assert`, `NamedExpr`.

---

### 1.2 Used, but rarest (communication patterns)

| Rank | Pattern | Files | Where |
| ---: | --- | ---: | --- |
| 1 | **Database** `PY-OTEL-5.5-DATABASE` | **1** | `product-reviews/database.py` |
| 2 | **GenAI** `PY-OTEL-5.6-GENAI` | **1** | `product-reviews/product_reviews_server.py` |
| 3 | **RPC/gRPC** `PY-OTEL-5.3-RPC` | **3** | locustfile, product-reviews server, recommendation server |
| 4 | **Feature flags** `PY-OTEL-5.6-FEATURE-FLAGS` | **4** | llm, locust, both gRPC servers |
| 5 | **HTTP** `PY-OTEL-5.1-HTTP` | **6** | everywhere except `metrics.py` stubs |

### 1.3 Used, but rarest (manifest kinds)

| Rank | Kind | Files |
| ---: | --- | ---: |
| 1 | `async_function`, `async_method` | **1** — `locustfile.py` only |
| 2 | `class`, `method` | **4** — gRPC servers, logger, locust |
| 3 | `function`, `variable` | **8** — every analyzed file |

### 1.4 Files with zero communication patterns

Both `metrics.py` files (18–24 lines) — OTel counters via `meter.create_counter` only; outside the §5 crosswalk.

---

## Part 2 — Shallowest implementations among *used* capabilities

Depth = evidence channels: **import-only** < **import + call** < **import + call + decorator**, plus false-positive risk.

### 2.1 Shallowest → deepest (used §5 patterns)

| Rank | Pattern | Shallowest site | Why shallow |
| ---: | --- | --- | --- |
| **1** | **HTTP** | `logger.py`, `database.py`, both gRPC servers | Matched **only** on `.get(` — `dict.get` / `os.environ.get`, not HTTP clients |
| **2** | **RPC** | `locustfile.py` | **`import grpc` only** — no channel/stub/server calls |
| **3** | **Feature flags** | `locustfile.py` | **`import openfeature` only** — no evaluation calls |
| **4** | **HTTP** | `locustfile.py` | Real `requests`/`urllib3` + `.get`/`.post`, but load-gen client only |
| **5** | **GenAI** | `product_reviews_server.py` | Single `openai` import + one `chat.completions.create` |
| **6** | **Feature flags** | `llm/app.py`, gRPC servers | Import + `get_boolean_value` — adequate demo wiring |
| **7** | **Database** | `database.py` | `psycopg2` + `connect`/`cursor`/`execute` — small but complete |
| **8** | **HTTP** | `llm/app.py` | **Deepest HTTP** — Flask import, `@route`/`@get`/`@post`, call sites |
| **9** | **RPC** | gRPC servers | **Deepest RPC** — servicer classes, `grpc.server`, health checks, protobuf |

### 2.2 Summary (used patterns)

| Pattern | Corpus depth | Shallowest file | Deepest file |
| --- | --- | --- | --- |
| HTTP | Wide, **mostly shallow** (4/6 false `.get(` hits) | `logger.py` | `llm/app.py` |
| RPC | **Bimodal** | `locustfile.py` (import-only) | `product_reviews_server.py` |
| Feature flags | **Bimodal** | `locustfile.py` (import-only) | `llm/app.py` / gRPC servers |
| Database | Single-file, solid | — | `database.py` |
| GenAI | Single-file, minimal | — | `product_reviews_server.py` |

### 2.3 Non-communication shallow use

| Capability | Observation |
| --- | --- |
| `PY-LC-005` decorator | Meaningful only in `llm/app.py` (Flask routes); elsewhere mostly Locust `@task` |
| `PY-LC-009` type_annotation | `arg` nodes only; almost no `AnnAssign`/`TypeAlias` |
| `PY-MAN-003/005` async | Locust Playwright user only — test plumbing, not service I/O |
| OTel metrics (uncatalogued) | `metrics.py` thinnest observability layer — 2 counters, no in-module spans |

---

## Part 3 — OTel Demo non-Python service inventory

Twelve languages in the full demo; **Python is 3 of ~20 runnable services** (recommendation, product-reviews, llm, load-generator — load-gen is traffic, not a backend).

| Service | Language | Primary §5 patterns exercised | Notes |
| --- | --- | --- | --- |
| **accounting** | C# (.NET) | **Messaging**, **Database** | Kafka consumer on `orders` topic; EF Core + PostgreSQL |
| **ad** | Java | RPC, Feature flags | gRPC leaf; flagd |
| **cart** | C# | RPC, **Database (Redis/Valkey)** | StackExchange.Redis; OTel Redis instrumentation |
| **checkout** | Go | RPC, **Messaging**, Feature flags | 6× gRPC fan-out; **Kafka producer** with semconv attrs |
| **currency** | C++ | RPC | gRPC leaf; FX conversion |
| **email** | Ruby | **HTTP**, Feature flags | Sinatra HTTP `/send_order_confirmation`; flagd; OTel logs/metrics |
| **fraud-detection** | Kotlin | **Messaging**, Feature flags | Kafka consumer; `kafkaQueueProblems` flag |
| **frontend** | TypeScript | **HTTP**, RPC (client) | Next.js BFF; gRPC-Web/clients to mesh |
| **frontend-proxy** | Envoy (config) | HTTP proxy | Infra — not app code |
| **image-provider** | nginx | HTTP static | Infra |
| **payment** | Node.js | RPC, Feature flags | gRPC leaf; `@openfeature/flagd-provider` |
| **product-catalog** | Go | RPC, **Database**, Feature flags, Connect* | Postgres via `otelsql`; flagd via Connect RPC dep |
| **quote** | PHP | RPC, HTTP (ReactPHP/Slim) | gRPC + async HTTP server |
| **shipping** | Rust | RPC | gRPC leaf |
| **flagd-ui** | Elixir | Feature flags (UI) | Phoenix — not a port target |
| **react-native-app** | TypeScript | Mobile HTTP | Out of Prime Contractor scope |

\*Connect RPC appears in `product-catalog` go.mod (`connectrpc.com/connect`, flagd Connect provider) — not evidenced in Python.

---

## Part 4 — Gap → source service → Python rebuild map

Maps **Part 1 absences** and **Part 2 shallow sites** to non-Python services whose logic can be **re-authored in Python** to expand capability-index coverage and SDK workflow fixtures.

### 4.1 Part 1 gaps (unused capabilities)

| Python gap (Part 1) | Best non-Python source(s) | Rebuild target | Prime / Plan value |
| --- | --- | --- | --- |
| **`PY-OTEL-5.4-MESSAGING`** | **checkout** (Go producer), **accounting** (C# consumer), **fraud-detection** (Kotlin consumer) | `accounting` as Python `aiokafka`/`confluent_kafka` consumer; checkout producer as Python module or sidecar | Plan Ingestion: `_PROTOCOL_METRICS` / kafka import allowlist; Prime: first Python messaging MicroPrime exemplar |
| **`PY-OTEL-5.5-DATABASE` (Redis branch)** | **cart** (C# Valkey) | Python `redis`/`valkey` cart store behind gRPC | Query Prime Redis patterns; new `CartService` Python seed candidate |
| **`PY-OTEL-5.5-DATABASE` (Postgres depth)** | **product-catalog** (Go `otelsql`), **accounting** (C# EF + Npgsql) | Extend `database.py` → SQLAlchemy/asyncpg + pool metrics | Deepens existing Python DB; Plan Ingestion SQL tier routing |
| **`PY-OTEL-5.3-CONNECT`** | **product-catalog** (Connect flagd provider in go.mod) | Python `connect-python` flagd client (if library viable) | Niche; lower priority than Kafka |
| **`PY-OTEL-5.6-GRAPHQL`** | *(none in demo app code)* | — | No demo source; would be net-new, not a port |
| **`PY-OTEL-5.6-FAAS` / `PY-OTEL-5.7-CICD` / CLI / DNS / object-store / cloud-SDK** | *(none)* | — | Not exercised by any demo service |
| **`PY-OTEL-5.2-HTTP-METRICS`** | All services (instrumentation) | Python OTel HTTP instrumentation hooks in ported services | Instrumentation config, not application AST |
| **`PY-MAN-006/007/009`** | **cart** (constants), **accounting** (entities), **frontend** (types) | Add `@property`, `UPPER_CASE` config, `TypeAlias` to ported modules | Manifest-kind index lift |
| **`PY-LC-007/008`** | **checkout** (generators uncommon); no `match` in demo | Add streaming response or `match` dispatch in new Python service | AST catalog completeness |

### 4.2 Part 2 gaps (shallow used capabilities)

| Shallow Python site (Part 2) | Source to port depth from | Rebuild action |
| --- | --- | --- |
| HTTP false positives in gRPC servers (`dict.get`) | **email** (Ruby Sinatra), **frontend** (TS HTTP routes) | Port **email** as Python **FastAPI/Starlette** HTTP service; fix crosswalk false positives separately |
| RPC import-only in `locustfile.py` | **checkout** (Go — 6 gRPC clients), **payment** (Node leaf server) | Add Python integration-test client module with real stub calls (or port **payment** as Python leaf seed) |
| Feature flags import-only in `locustfile.py` | **payment** (Node `FlagdProvider`), **email** (Ruby flagd) | Mirror `get_boolean_value` / hook patterns in locust or ported email |
| GenAI minimal (1 call, 1 file) | **llm** (Flask, same language) + **product-reviews** OpenAI path | **Merge**: implement `AskProductAIAssistant` in `product_reviews_server.py` using `llm/app.py` patterns; add to seeds (currently omitted per FR-3) |
| Database single 91-line module | **accounting** + **product-catalog** | Expand to multi-table ORM, migrations, connection pooling |
| Thin `metrics.py` | **cart** (Redis metrics), **email** (confirmation counter), **payment** (charge metrics) | Richer `create_counter`/`create_histogram` + semconv names in ported services |

---

## Part 5 — Recommended Python rebuild sequence

Ordered by **capability-index lift × Prime Contractor / Plan Ingestion fit**.

### Wave 0 — Same language, no port (days)

| # | Action | Closes |
| --- | --- | --- |
| 0.1 | Wire `AskProductAIAssistant` in `product_reviews_server.py` from `llm/app.py` | GenAI depth; optional seed RPC |
| 0.2 | Replace HTTP false-positive matcher (require HTTP import for `PY-OTEL-5.1-HTTP`) | Measurement hygiene |
| 0.3 | Deepen `locustfile.py` flag/RPC calls to match payment patterns | Part 2 shallow sites |

### Wave 1 — High-value ports (1–2 weeks each)

| # | Port source → Python | New Python artifact | Workflow unlock |
| --- | --- | --- | --- |
| 1.1 | **accounting** (C#) → `src/accounting-py/` | Kafka consumer + SQLAlchemy/Postgres | **Messaging** index; Plan Ingestion kafka+sql patterns; structural seed |
| 1.2 | **email** (Ruby) → `src/email-py/` | FastAPI/Starlette + flagd + confirmation handler | **Real HTTP server**; leaf HTTP seed; behavioral candidate if no deps |
| 1.3 | **cart** (C#) → `src/cart-py/` | gRPC + `redis` store | Redis DB crosswalk; Python `CartService` seed |

### Wave 2 — Depth + behavioral Python seeds (2+ weeks)

| # | Port source → Python | Closes |
| --- | --- | --- |
| 2.1 | **payment** (Node) → Python leaf gRPC | First **behavioral-eligible** Python OTel seed (leaf, no deps) |
| 2.2 | **checkout** Kafka producer slice → Python | Producer-side messaging spans |
| 2.3 | **fraud-detection** (Kotlin) → Python consumer | Second consumer pattern; async + flags |
| 2.4 | **product-catalog** Postgres patterns → extend product-reviews DB layer | Instrumented SQL, connection metrics |

### Wave 3 — Optional breadth

| # | Source | Notes |
| --- | --- | --- |
| 3.1 | **quote** (PHP) | Extra gRPC leaf for MicroPrime; low pattern novelty |
| 3.2 | **frontend** BFF (TS) → FastAPI | HTTP client mesh; large surface |
| 3.3 | **shipping** (Rust) | gRPC leaf only — payment-class port is cheaper |

### Do not port (poor ROI for Python capability index)

| Service | Reason |
| --- | --- |
| frontend-proxy, image-provider | Infra/config, not Python AST patterns |
| flagd-ui | Elixir UI |
| react-native-app | Mobile TS; outside Prime Contractor Python scope |
| currency (C++) | High port cost; RPC-only; payment Python leaf suffices |

---

## Part 6 — SDK workflow alignment

### 6.1 Prime Contractor

| Current state | Gap | Rebuild addresses |
| --- | --- | --- |
| 2 Python OTel seeds: `recommendation`, `product-reviews` | Both **`behavioral_eligible: false`** (downstream gRPC / Postgres deps) | Port **payment**-class **leaf** Python gRPC service |
| `AskProductAIAssistant` omitted from product-reviews seed | GenAI / LLM dep | Wave 0.1 merge from `llm/` |
| No Python messaging tasks | Kafka absent from Python corpus | Wave 1.1 accounting port |
| MicroPrime messaging/Redis steps under-exercised | No Python kafka/redis exemplars | cart + accounting ports |

### 6.2 Plan Ingestion / Query Prime

| Derivation input needed | Today (Python) | Source service for port |
| --- | --- | --- |
| Kafka import signatures | ❌ | checkout, accounting, fraud-detection |
| Redis/Valkey signatures | ❌ | cart |
| SQLAlchemy/asyncpg depth | ⚠️ psycopg2 only | product-catalog, accounting |
| HTTP server frameworks | ⚠️ Flask in llm only | email (Sinatra → FastAPI) |
| Feature-flag call patterns | ⚠️ partial | payment, email |

Handoff payload: Tier-0 `observed_names` + ported Python sources feed ContextCore `_PROTOCOL_METRICS` / `_DATABASE_IMPORT_PATTERNS` extension ([derivation-handoff.md](../otel-demo-corpus/derivation-handoff.md)).

---

## Part 7 — Coverage projection (estimate)

If Waves 0–1 land:

| Dimension | Today | Projected |
| --- | ---: | ---: |
| communication_patterns | 33.3% (5/15) | **~53%** (8/15) — +messaging, +redis DB, deeper HTTP |
| ast_nodes | 43.9% | **~50%** — async, AnnAssign, With, generators |
| language_composites | 80.0% | **~90%** — generator if streaming added |
| manifest_kinds | 66.7% | **~89%** — property, constant, type_alias |
| **Overall index** | **56.0%** | **~70%** |

Messaging alone closes the largest single Part 1 gap; email port fixes the largest Part 2 false-positive cluster.

---

## Related artifacts

- [otel-demo-python-coverage.md](./otel-demo-python-coverage.md) — per-file `hyp(f)` report
- [PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md](../PYTHON_AST_COMMUNICATION_CAPABILITY_INDEX.md) §9.3 — resolver usage
- [OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md](../otel-demo-corpus/OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md) — Steps 1–6 requirements (OpenAPI-leveraged)
- [OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md](../otel-demo-corpus/OTEL_PYTHON_REBUILD_OPENAPI_PLAN.md) — implementation plan
- [TIER1_CORPUS_REQUIREMENTS.md](../otel-demo-corpus/TIER1_CORPUS_REQUIREMENTS.md) — behavioral eligibility constraints
- [OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md](../OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md) — landscape overlap baseline

---

*Generated analysis for OTel Demo tag 2.2.0. Re-run resolver after ports: `python3 scripts/analyze_otel_demo_python_coverage.py`.*
