# Online Boutique × OTel Programming Landscape — Overlap Catalog

> **Date:** 2026-06-18  
> **Baseline:** [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](./OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md) (OTel spec-defined landscape)  
> **Subject:** [Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo) (`GoogleCloudPlatform/microservices-demo`, package `hipstershop`, Apache-2.0)  
> **Scope:** What the demo **actually exercises** vs what the OTel landscape **defines but OB omits**. Default deployment unless noted; optional observability via `kustomize/components/google-cloud-operations`.

---

## 1. Executive summary

Online Boutique is an 11-service e-commerce microservices demo. It is a **narrow but deep slice** of the OTel programming landscape: multi-language gRPC mesh, HTTP edge, one datastore (Redis), Kubernetes deployment, and (when enabled) OTLP traces/metrics through a Collector gateway to a cloud backend.

| Landscape dimension | OB exercises | OB omits (examples) |
| --- | ---: | --- |
| First-class OTel SDK languages (§3.1) | **5 / 12** | C++, Erlang, Kotlin, PHP, Ruby, Rust, Swift |
| Telemetry signals (§2) | Traces, metrics (optional path) | Logs pipeline, baggage demos, profiles, events |
| Wire protocol (§4.1) | OTLP/gRPC → Collector | OTLP/HTTP from apps, Jaeger/Zipkin native export |
| Context propagation (§4.2) | W3C Trace Context (when tracing on) | B3-only, Baggage-heavy flows, X-Ray |
| Application patterns (§5) | HTTP, gRPC/RPC, Redis | Messaging, SQL DBs, GraphQL, FaaS, object stores, CloudEvents |
| Resource / platform semconv (§6) | Service, container, K8s, process | Cloud resource attrs (unless on GKE + ops overlay), browser/mobile |
| Collector topology (§7) | Gateway collector, OTLP receiver | Agent DaemonSet, sidecar, span-metrics connector, multi-backend fan-out |
| Instrumentation modes (§3.3) | Manual / library instrumentation in services | Zero-code operator injection, eBPF |

**Overlap character:** OB is the canonical **multi-language gRPC + HTTP + Redis + K8s** reference app. It does **not** showcase the full breadth of OTel semconv domains (messaging, SQL, FaaS, GenAI, etc.). The fork [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) (`oteldemo`) extends OB toward a fuller landscape exercise — summarized in §8.

---

## 2. Online Boutique service inventory

Eleven processes; nine implement gRPC backends from shared `protos/demo.proto` (StartD8 benchmark seeds use these nine). Two are HTTP-only clients of the mesh.

| Service | Language | OTel SDK (§3.1) | Primary role | Inter-service protocol | Datastore / deps |
| --- | --- | --- | --- | --- | --- |
| **frontend** | Go | Go | HTTP web UI + BFF | gRPC → many; HTTP server | Session IDs (in-memory) |
| **cartservice** | C# | .NET | Cart CRUD | gRPC server | **Redis** |
| **productcatalogservice** | Go | Go | Product list/search | gRPC server | `products.json` file |
| **currencyservice** | Node.js | JavaScript | FX conversion | gRPC server | ECB rates data file |
| **paymentservice** | Node.js | JavaScript | Mock charge | gRPC server | — (leaf) |
| **shippingservice** | Go | Go | Quote + ship | gRPC server | — (leaf) |
| **emailservice** | Python | Python | Order email (mock) | gRPC server | Jinja2 template |
| **checkoutservice** | Go | Go | Order orchestrator | gRPC client ×6 | — |
| **recommendationservice** | Python | Python | Product recommendations | gRPC + gRPC client | → productcatalog |
| **adservice** | Java | Java | Contextual ads | gRPC server | — (leaf) |
| **loadgenerator** | Python | Python | Locust traffic | HTTP → frontend | — |

**Proto contract:** 9 services · 15 RPCs · package `hipstershop` (see `docs/design/controlled-corpus/CORPUS_INVENTORY.md`).

---

## 3. Overlap by landscape-catalog section

Each subsection maps to a section in [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](./OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md).

### 3.1 §2 — Telemetry signals

| Signal | In OB application code? | In OB + google-cloud-operations overlay? | Landscape notes |
| --- | --- | --- | --- |
| **Traces** | Instrumentation hooks in services; **off by default** | **Yes** — `ENABLE_TRACING=1`, export via Collector | Distributed paths: checkout fan-out, frontend BFF |
| **Metrics** | Stats hooks; **off by default** | **Partial** — `ENABLE_STATS=1`; README notes trace-first maturity | RPC/HTTP metrics when libraries emit semconv instruments |
| **Logs** | App logging (stdout); not unified OTel logs | Not wired through Collector logs pipeline | Landscape §2 logs stable; OB doesn't demo log correlation |
| **Baggage** | Not a demo focus | Same | Propagator exists in OTel defaults; OB doesn't exercise custom baggage |
| **Profiles** | Cloud Profiler hooks in some services (Google Cloud) | Profiler agent role separate from OTel profiles signal | Landscape profiles = development |
| **Events** | — | — | Not used |

**Span kinds exercised (when tracing on):** `SERVER` / `CLIENT` on gRPC and HTTP paths; `INTERNAL` inside orchestrators (checkout, frontend).

---

### 3.2 §3 — Language SDKs

| Landscape language | Present in OB? | Services |
| --- | --- | --- |
| **Go** | Yes | frontend, productcatalog, shipping, checkout |
| **C# / .NET** | Yes | cartservice |
| **JavaScript (Node.js)** | Yes | currencyservice, paymentservice |
| **Python** | Yes | emailservice, recommendationservice, loadgenerator |
| **Java** | Yes | adservice |
| C++ | No | (OTel Demo: currency, frontend-proxy, image-provider) |
| Ruby | No | (OTel Demo: email) |
| Rust | No | (OTel Demo: shipping) |
| Kotlin | No | (OTel Demo: fraud-detection) |
| PHP | No | (OTel Demo: quote) |
| Erlang/Elixir | No | (OTel Demo: flagd-ui) |
| TypeScript | No | (OTel Demo: frontend, react-native-app) |
| Swift, Rust, Kotlin, etc. | No | — |

**SDK language keys emitted (`telemetry.sdk.language`):** `go`, `dotnet`, `nodejs`, `python`, `java` — five of eleven well-known values in landscape §6.5 / resource semconv.

**Instrumentation mode overlap:**

| Mode | OB |
| --- | --- |
| Manual / library instrumentation | **Yes** — per-service OpenTelemetry or OpenCensus/Google stats & trace libraries (varies by language) |
| Zero-code auto-instrumentation | **No** |
| Kubernetes Operator injection | **No** |
| eBPF (OBI) | **No** |

---

### 3.3 §4 — Wire protocols and propagation

#### OTLP (§4.1)

| Element | OB overlap |
| --- | --- |
| **OTLP/gRPC** | **Yes** — services set `COLLECTOR_SERVICE_ADDR=opentelemetrycollector:4317` (kustomize overlay) |
| **OTLP/HTTP** | **No** from application SDKs (Collector may support HTTP receiver; apps use gRPC) |
| Compression / Export retry | Collector-side; apps delegate to SDK batch export |

#### Propagation (§4.2)

| Propagator | OB overlap |
| --- | --- |
| **W3C Trace Context** | **Yes** — standard for gRPC/HTTP inter-service calls when tracing enabled |
| **W3C Baggage** | Default in OTel composite; **not meaningfully used** in OB business logic |
| B3, Jaeger, OpenCensus binary | **No** (unless legacy library defaults — not the demo's documented path) |

#### Legacy bridges (§4.3)

| Bridge | OB overlap |
| --- | --- |
| OpenCensus → OTel | **Historical** — some Google Cloud samples bridged OpenCensus to Cloud Trace |
| Jaeger / Zipkin direct | **No** in default OB overlay (Collector exports to `googlecloud`, not Jaeger) |
| Prometheus scrape | **No** as primary app export path |

---

### 3.4 §5 — Application communication patterns

#### Pattern coverage matrix

| Pattern (landscape §5) | OB uses? | Where / how |
| --- | --- | --- |
| **HTTP** (§5.2) | **Yes** | frontend HTTP server; loadgenerator → frontend; user → frontend |
| **RPC / gRPC** (§5.3) | **Yes** | All inter-service calls; `rpc.system=grpc`; 9 services from `demo.proto` |
| Connect / Dubbo / JSON-RPC | No | — |
| **Messaging** (§5.4) | **No** | No Kafka, RabbitMQ, SQS, Pub/Sub in base OB |
| **Database — Redis** (§5.5) | **Yes** | cartservice → Redis (`db.system=redis` when instrumented) |
| **Database — SQL** | **No** | No PostgreSQL/MySQL in base OB |
| MongoDB, Elasticsearch, DynamoDB | No | — |
| **GraphQL** (§5.6) | No | — |
| **FaaS** | No | — |
| **Feature flags** | No | (OTel Demo: flagd) |
| **GenAI** | No | (OTel Demo: llm, product-reviews AI RPC) |
| **CloudEvents** | No | — |
| **Object stores (S3)** | No | — |
| **Cloud provider SDK spans** | **Partial** | GKE deployment; explicit AWS/GCP SDK semconv not a demo focus |
| **DNS** | Incidental | K8s service discovery only |
| **CI/CD semconv** | No | — |

#### gRPC service graph (semconv-relevant edges)

```
loadgenerator ──HTTP──► frontend ──HTTP──► (users)
                          │
          ┌───────────────┼───────────────┬──────────────┐
          ▼               ▼               ▼              ▼
        ad (gRPC)    currency (gRPC)   cart (gRPC)   checkout (gRPC)
          │               │               │              │
          │               │               ▼              ├──► productcatalog (gRPC)
          │               │            Redis             ├──► currency (gRPC)
          │               │                              ├──► cart (gRPC)
          │               │                              ├──► shipping (gRPC)
          │               │                              ├──► payment (gRPC)
          │               │                              └──► email (gRPC)
          │               │
          ▼               ▼
     (leaf)           (leaf)          recommendation ──gRPC──► productcatalog
```

**Checkout** is the richest distributed trace: one `PlaceOrder` spans **6 downstream gRPC calls** — the best OB exemplar for RPC client/server semconv chains (landscape §5.3 metrics: `rpc.server.duration`, etc.).

#### Expected semconv attribute namespaces (when instrumented)

| Call path | Landscape domain | Representative attributes / metrics |
| --- | --- | --- |
| User → frontend | HTTP §5.2 | `http.route`, `http.request.method`, `http.server.duration` |
| frontend → * | RPC §5.3 | `rpc.system=grpc`, `rpc.service`, `rpc.method`, `rpc.grpc.status_code` |
| cart → Redis | Database §5.5 | `db.system=redis`, `db.operation` |
| checkout → 6 services | RPC client spans | Nested CLIENT spans under orchestrator SERVER/INTERNAL |

---

### 3.5 §6 — Runtime and platform architectures

| Resource / platform (landscape §6) | OB overlap |
| --- | --- |
| **service.*** | **Yes** — each pod/deployment names a microservice (`cartservice`, …) |
| **telemetry.sdk.*** | **Yes** — five languages export SDK identity |
| **container.*** | **Yes** — each service is containerized (Docker) |
| **k8s.*** | **Yes** — primary deployment target (GKE, Kind, Minikube) |
| **host / process** | **Incidental** — node-level attrs via Collector or cloud agent |
| **deployment.environment** | Configurable via env / manifest |
| **cloud.provider=gcp** | **When on GKE** + google-cloud-operations overlay |
| **browser / mobile** | **No** — web UI is server-rendered Go, not browser OTel SDK |
| **Runtime metrics** (`jvm.*`, `go.*`, …) | **Possible** via instrumentation; not the demo's headline |

---

### 3.6 §7 — Collector architecture patterns

Default OB **without** observability overlay: **no Collector** (landscape §7.2 "in-process / SDK only" at most).

With **`kustomize/components/google-cloud-operations`**:

| Topology (§7.2) | OB overlap |
| --- | --- |
| In-process SDK only | Default (tracing off) |
| **Gateway collector** | **Yes** — single `opentelemetrycollector` Deployment receives OTLP |
| Agent / DaemonSet | **No** |
| Sidecar per pod | **No** |
| Agent + Gateway tier | **No** |

| Pipeline (§7.1) | OB overlay config |
| --- | --- |
| Receivers | `otlp` (gRPC `:4317`) |
| Processors | None in template (`processors: []`) |
| Exporters | `googlecloud` (traces + metrics → GCP APIs) |
| Connectors | **No** (OTel Demo adds span-metrics connector) |
| Multi-backend fan-out | **No** (OTel Demo: Jaeger, Prometheus, OpenSearch, Grafana) |

This is a **minimal** subset of landscape §7.3 receiver/exporter inventory.

---

### 3.7 §8–§10 — Semconv index, instrumentation matrix, configuration

#### Semconv domains touched vs untouched

| Domain (landscape §8) | OB |
| --- | --- |
| General, Trace, Exceptions | **Yes** (typical spans) |
| Resource / Service | **Yes** |
| HTTP | **Yes** |
| RPC / gRPC | **Yes** (core) |
| Database (Redis) | **Yes** (cart only) |
| Messaging, GraphQL, FaaS, CloudEvents, Object stores, CI/CD, Feature flags, GenAI | **No** |
| System / Runtime | **Partial** (depends on agent/collector config) |
| OpenTelemetry SDK (self-telemetry) | **No** |

#### Protocol × language matrix (landscape §9) — OB cells filled

| Protocol | Go | .NET | Java | Node.js | Python |
| --- | --- | --- | --- | --- | --- |
| HTTP server | frontend | — | — | — | — |
| HTTP client | — | — | — | — | loadgenerator |
| gRPC server | productcatalog, shipping, checkout | — | ad | currency, payment | email, recommendation |
| gRPC client | frontend, checkout, recommendation | — | — | — | — |
| Redis client | — | cart | — | — | — |

Five languages × three protocol classes (HTTP, gRPC, Redis) — aligns with StartD8 `_OTEL_SDK_MAP` / `_PROTOCOL_METRICS` derivation targets (HTTP + gRPC + Redis detection).

#### Environment variables (landscape §10) — OB overlay

| Variable | OB usage |
| --- | --- |
| `COLLECTOR_SERVICE_ADDR` | `opentelemetrycollector:4317` |
| `ENABLE_TRACING` | `"1"` when overlay enabled |
| `ENABLE_STATS` | `"1"` when overlay enabled |
| `OTEL_SERVICE_NAME` | Implicit via service deployment name / library defaults |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | Not documented in OB README — libraries follow their default semconv generation |

---

## 4. Per-service landscape overlap scorecard

Legend: **●** exercises · **○** partial / optional · **—** absent

| Service | Traces | Metrics | HTTP semconv | gRPC semconv | DB semconv | K8s resource | OTLP export |
| --- | --- | --- | --- | --- | --- | --- | --- |
| frontend | ● | ○ | ● server, ● client | ● | — | ● | ○ |
| cartservice | ● | ○ | — | ● | ● Redis | ● | ○ |
| productcatalogservice | ● | ○ | — | ● | — | ● | ○ |
| currencyservice | ● | ○ | — | ● | — | ● | ○ |
| paymentservice | ● | ○ | — | ● | — | ● | ○ |
| shippingservice | ● | ○ | — | ● | — | ● | ○ |
| emailservice | ● | ○ | — | ● | — | ● | ○ |
| checkoutservice | ●● (deepest trace) | ○ | — | ●● | — | ● | ○ |
| recommendationservice | ● | ○ | — | ● | — | ● | ○ |
| adservice | ● | ○ | — | ● | — | ● | ○ |
| loadgenerator | ○ | — | ● client | — | — | ● | ○ |

●● = best single request for end-to-end trace depth (checkout orchestration).

---

## 5. Gaps — landscape defined, Online Boutique silent

Grouped by why the gap matters for StartD8 / code-observability work.

### 5.1 Language breadth

OB covers **5 SDK languages**. Missing from OB but in landscape §3.1: **C++, Ruby, Rust, Kotlin, PHP, Erlang, Swift, TypeScript**. Any tooling validated only on OB under-tests those SDK export paths and runtime semconv (`cpython.*` vs `jvm.*`, etc.).

### 5.2 Async and data-plane patterns

- **No messaging** (§5.4) — no `PRODUCER`/`CONSUMER` spans, no Kafka semconv.
- **No SQL** (§5.5) — Redis-only; no `db.system=postgresql` client spans.
- **No GraphQL, FaaS, GenAI, feature flags** (§5.6).

### 5.3 Observability stack breadth

- **Single exporter** (`googlecloud`) vs landscape Collector fan-out (Jaeger, Prometheus, OpenSearch).
- **No span-metrics connector** (OTel Demo uses this for Prometheus).
- **Logs signal** not demonstrated end-to-end.
- **Baggage, profiles, events** not demonstrated.

### 5.4 Deployment patterns

- **No sidecar/agent** Collector topology.
- **No Istio/Envoy** trace propagation demo in base repo (Istio is a separate kustomize component, not default).
- **No browser/mobile** client SDK (landscape §6.6).

### 5.5 Propagation and legacy interop

- **No B3/Jaeger/Zipkin** first-class path in the documented OB overlay.
- **No OpenCensus receiver** in the Collector config (historical client libraries may still emit OpenCensus-shaped data in older forks).

---

## 6. StartD8 repo touchpoints

Online Boutique is already a first-class corpus in this SDK:

| Artifact | Role |
| --- | --- |
| `scripts/gen_ob_benchmark_seeds.py` | 9 gRPC services → benchmark seeds |
| `docs/design/model-benchmark/seeds/` | Per-service `prime-context-seed.json` + `demo.proto` |
| `docs/design/controlled-corpus/` | 9 services · 15 RPCs · forward-manifest bindings |
| `src/startd8/benchmark_matrix/behavioral/` | Track 2 sandbox (e.g. PaymentService Charge suite) |
| Kaizen `KAIZEN_INVESTIGATION_RUN*_ONLINE_BOUTIQUE.md` | Generation quality on OB targets |
| `docs/design/prime-contractor-node/plan-nodejs.md` | OB Node.js reproduction plans |

The overlap catalog informs **which landscape dimensions OB seeds stress-test** (gRPC × 5 languages, Redis, HTTP edge) and **which require OTel Demo or synthetic fixtures** (Java/C# depth, messaging, SQL, GenAI).

---

## 7. Optional overlay: google-cloud-operations

Enabling `kustomize/components/google-cloud-operations` adds the primary **OB → OTel landscape** bridge:

1. Patches deployments with `ENABLE_TRACING`, `ENABLE_STATS`, `COLLECTOR_SERVICE_ADDR`.
2. Deploys `opentelemetrycollector` (Collector **contrib** image).
3. Collector pipeline: `otlp` receiver → `googlecloud` exporter (traces + metrics).
4. Requires GCP APIs: Cloud Trace, Monitoring, Profiler.

**Overlap added vs default OB:** landscape §4.1 OTLP/gRPC, §7 gateway Collector, §2 traces + partial metrics, §6 `cloud.provider=gcp` on GKE.

**Still missing vs full landscape:** logs pipeline, multi-exporter fan-out, messaging/SQL semconv in the app itself.

---

## 8. OpenTelemetry Demo fork — extended overlap (not base OB)

[OpenTelemetry Demo](https://opentelemetry.io/docs/demo/architecture/) (`open-telemetry/opentelemetry-demo`, package `oteldemo`) descends from Online Boutique. It **widens** landscape overlap without changing the core hipstershop-shaped services:

| Landscape gap in base OB | OTel Demo addition |
| --- | --- |
| Languages §3.1 (7 missing) | Adds C++, Ruby, Rust, Kotlin, PHP, Elixir, TypeScript services |
| Messaging §5.4 | Kafka queue → accounting, fraud-detection |
| SQL database §5.5 | PostgreSQL (accounting, product-reviews) |
| Feature flags §5.6 | flagd (Go), flagd-ui (Elixir) |
| GenAI | llm (Python), ProductReview AI RPC |
| HTTP edge complexity | frontend-proxy (Envoy), image-provider (nginx) |
| Collector §7 | OTLP → Jaeger, Prometheus, OpenSearch, Grafana; span-metrics connector |
| Cache naming | Valkey (Redis-compatible) for cart |

StartD8 tracks this as a second benchmark corpus: `docs/design/otel-demo-corpus/OTEL_DEMO_SEED_EXTRACTION_PLAN.md`.

**Comparability note:** Scores and instrumentation contracts should be reported **per corpus** (OB vs OTel Demo), not pooled — see OTel Demo plan §6 (OQ-OT-5).

---

## 9. Summary matrix — landscape section → OB coverage

| Catalog § | Topic | OB coverage |
| ---: | --- | --- |
| §2 | Signals | Traces + partial metrics (overlay); no logs/profiles/baggage demo |
| §3 | Languages | 5 / 12 first-class SDKs |
| §3.3 | Instrumentation modes | Library/manual only |
| §4.1 | OTLP | gRPC to Collector (overlay) |
| §4.2 | Propagation | W3C Trace Context (when on) |
| §4.3 | Legacy bridges | Minimal; googlecloud export not in catalog core list |
| §5.2 | HTTP | frontend + loadgenerator |
| §5.3 | gRPC/RPC | **Core** — entire mesh |
| §5.4 | Messaging | — |
| §5.5 | Database | Redis only |
| §5.6–§5.7 | GraphQL, FaaS, CI/CD, … | — |
| §6 | Platform resources | K8s, container, service; GCP when on GKE + overlay |
| §7 | Collector | Gateway only; otlp → googlecloud |
| §8 | Semconv index | HTTP, RPC, Redis, Resource, General |
| §9 | Protocol × language matrix | 5×3 cells filled (HTTP, gRPC, Redis) |
| §10 | Env configuration | Partial (`ENABLE_*`, collector addr) |

---

## 10. References

1. [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](./OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md) — baseline landscape
2. [Online Boutique README](https://github.com/GoogleCloudPlatform/microservices-demo/blob/main/README.md) — service table
3. [OB google-cloud-operations kustomize](https://github.com/GoogleCloudPlatform/microservices-demo/tree/main/kustomize/components/google-cloud-operations) — OTel Collector overlay
4. [OpenTelemetry Demo architecture](https://opentelemetry.io/docs/demo/architecture/) — extended fork
5. [StartD8 OB benchmark seeds](../../scripts/gen_ob_benchmark_seeds.py) — 9-service corpus
6. [OTel Demo seed extraction plan](./otel-demo-corpus/OTEL_DEMO_SEED_EXTRACTION_PLAN.md) — second corpus
7. [Controlled corpus inventory](./controlled-corpus/CORPUS_INVENTORY.md) — 9 services · 15 RPCs

---

## Document maintenance

- **Refresh when:** OB upstream adds services (e.g. shopping-assistant), changes observability overlay, or OTel Demo diverges further from hipstershop proto.
- **Pair with:** `OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md` for the full landscape; this doc for **what OB actually covers**.
