# OpenTelemetry Programming Landscape Catalog

> **Date:** 2026-06-18  
> **Scope:** Languages, wire protocols, application communication patterns, deployment architectures, and semantic-convention domains **as defined by OpenTelemetry** (spec, semantic conventions, collector, and language SDKs).  
> **Purpose:** A single reference for what OTel officially recognizes as the observable programming landscape — useful for code-observability design, instrumentation contract derivation, and cross-language tooling decisions.  
> **Source of truth:** [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/) (v1.57.0 at time of writing), [Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/) (v1.42.0), [OTLP](https://opentelemetry.io/docs/specs/otlp/) (v1.10.0), [Status page](https://opentelemetry.io/status/), and linked sub-specs. Vendor backends are out of scope except where OTel defines compatibility or bridge protocols.

---

## 1. How OTel Defines the Landscape

OpenTelemetry does not catalog "all software." It defines a **vendor-neutral observability substrate** with four layers that together describe the programming landscape OTel cares about:

| Layer | What OTel defines | Role |
| --- | --- | --- |
| **Signals** | Traces, metrics, logs, baggage; profiles and events in development | What gets emitted |
| **API / SDK** | Per-language client libraries | How applications produce signals |
| **Semantic conventions** | Standard attribute names, span kinds, metric instruments, resource types | How signals are interpreted consistently across languages and backends |
| **Collector + OTLP** | Ingestion, processing, export pipelines; wire protocol | How signals move between processes and systems |

Everything below is organized along those layers.

---

## 2. Telemetry Signals

| Signal | Spec status | Description | OTel reference |
| --- | --- | --- | --- |
| **Traces** | Stable | Distributed request paths as spans linked by context | [Trace spec](https://opentelemetry.io/docs/specs/otel/trace/) |
| **Metrics** | Stable | Time-series measurements (counters, gauges, histograms) | [Metrics spec](https://opentelemetry.io/docs/specs/otel/metrics/) |
| **Logs** | Stable (bridging from traces/metrics still evolving) | Event records; can correlate with trace context | [Logs spec](https://opentelemetry.io/docs/specs/otel/logs/) |
| **Baggage** | Stable | Cross-cutting key/value context propagated with requests (not a standalone backend signal) | [Baggage API](https://opentelemetry.io/docs/specs/otel/baggage/) |
| **Profiles** | Development | Code-level resource usage (CPU, heap, etc.) | [Profiles spec](https://opentelemetry.io/docs/specs/otel/profiles/) |
| **Events** | Development (typed log-like records) | Structured occurrences attached to spans or emitted as log records | [Events semconv](https://opentelemetry.io/docs/specs/semconv/general/events/) |

**Span kinds** (trace topology primitives): `CLIENT`, `SERVER`, `PRODUCER`, `CONSUMER`, `INTERNAL`.

**Metric instrument kinds**: Counter, UpDownCounter, Histogram, Gauge (plus asynchronous variants).

---

## 3. Language SDKs

Official language implementations tracked on the [Status page](https://opentelemetry.io/status/). Maturity is **per signal**, not per language globally.

### 3.1 First-class language SDKs

| Language | Traces | Metrics | Logs | Profiles | SDK language key (`telemetry.sdk.language`) |
| --- | --- | --- | --- | --- | --- |
| **C++** | Stable | Stable | Stable | — | `cpp` |
| **C# / .NET** | Stable | Stable | Stable | — | `dotnet` |
| **Erlang / Elixir** | Stable | Development | Development | — | `erlang` |
| **Go** | Stable | Stable | Beta | — | `go` |
| **Java** | Stable | Stable | Stable | Development | `java` |
| **JavaScript** (Node.js + browser) | Stable | Stable | Development | — | `nodejs` / `webjs` |
| **Kotlin** | Development | Development | Development | — | (JVM ecosystem; separate SIG) |
| **PHP** | Stable | Stable | Stable | — | `php` |
| **Python** | Stable | Stable | Development | — | `python` |
| **Ruby** | Stable | Development | Development | — | `ruby` |
| **Rust** | Beta | Beta | Beta | — | `rust` |
| **Swift** | Stable | Development | Development | — | `swift` |

Additional well-known SDK language values in resource semconv: `webjs` (browser JS).

### 3.2 Other / community languages

[Other languages](https://opentelemetry.io/docs/languages/other/) and additional implementations are listed in the [OpenTelemetry Registry](https://opentelemetry.io/ecosystem/registry/) (instrumentation libraries, exporters, propagators, samplers, etc.).

### 3.3 Instrumentation modes (by language)

| Mode | Languages with official zero-code path | Mechanism |
| --- | --- | --- |
| **Manual instrumentation** | All SDK languages | Application code calls Tracer/Meter/Logger API |
| **Library instrumentation** | All (via contrib packages) | Framework-specific packages (e.g. `opentelemetry-instrumentation-fastapi`, `otelhttp`, `otelgrpc`) |
| **Zero-code / auto-instrumentation** | .NET, Go, Java, JavaScript, PHP, Python | Agents, eBPF, or operator injection — [Zero-code docs](https://opentelemetry.io/docs/zero-code/) |
| **Operator injection (Kubernetes)** | .NET, Java, Node.js, Python, Go | [OpenTelemetry Operator](https://opentelemetry.io/docs/platforms/kubernetes/operator/) sidecar/init-container injection |
| **eBPF zero-code** | Linux kernel-level (language-agnostic at probe layer) | [OBI (OpenTelemetry eBPF Instrumentation)](https://opentelemetry.io/docs/zero-code/obi/) |

---

## 4. Wire Protocols and Context Propagation

### 4.1 OTLP — primary telemetry wire protocol

[OTLP](https://opentelemetry.io/docs/specs/otlp/) is the canonical protocol for moving traces, metrics, logs, and (in development) profiles between SDKs, agents, collectors, and backends.

| Transport | Default ports (convention) | Encoding | Signal coverage |
| --- | --- | --- | --- |
| **OTLP/gRPC** | 4317 | Protocol Buffers | Traces, metrics, logs, profiles (dev) |
| **OTLP/HTTP** | 4318 | Protobuf (binary) or JSON | Traces, metrics, logs, profiles (dev) |

**Compression:** `none`, `gzip` (required server support).

**Delivery model:** Request/response `Export*` RPCs; client-side retry and optional shutdown flush. End-to-end multi-hop guarantees are explicitly **out of OTLP scope** (single client/server pair only).

**Additional exporters (SDK-side, non-OTLP):** Jaeger, Zipkin, Prometheus, OpenCensus — see [SDK Exporter spec](https://opentelemetry.io/docs/specs/otel/protocol/exporter/).

### 4.2 Context propagation formats (in-band, cross-service)

Propagators move trace and baggage context across process boundaries (typically HTTP/gRPC headers or message metadata).

| Propagator | OTel core distribution | Status | Typical carrier |
| --- | --- | --- | --- |
| **W3C Trace Context** (`traceparent`, `tracestate`) | Yes (default composite) | Required core | HTTP headers, gRPC metadata |
| **W3C Baggage** | Yes (default composite) | Required core | HTTP headers |
| **B3** (single + multi header) | Yes | Core (Zipkin interop) | HTTP headers |
| **Jaeger** | Yes | Deprecated → use W3C | HTTP headers |
| **OT Trace** (OpenTracing legacy) | Yes | Deprecated → use W3C | HTTP headers |
| **OpenCensus BinaryFormat** | Yes | Legacy interop | gRPC `grpc-trace-bin` |
| **AWS X-Ray** | Contrib (not core) | Vendor-specific | HTTP header |

Default global propagator (when platform pre-configures): **W3C Trace Context + Baggage** composite.

### 4.3 Legacy / bridge protocols (Collector receivers & compatibility)

OTel defines explicit compatibility paths for prior observability ecosystems:

| Ecosystem | Bridge mechanism | OTel reference |
| --- | --- | --- |
| **OpenCensus** | Collector `opencensus` receiver/exporter; API shim | [OpenCensus compatibility](https://opentelemetry.io/docs/specs/otel/compatibility/opencensus/) |
| **OpenTracing** | API bridge/shim to OTel API | [OpenTracing compatibility](https://opentelemetry.io/docs/specs/otel/compatibility/opentracing/) |
| **Prometheus / OpenMetrics** | Pull scrape (`prometheus` receiver); remote-write export; metric naming mapping | [Prometheus compatibility](https://opentelemetry.io/docs/specs/otel/compatibility/prometheus/) |
| **Jaeger** | Collector `jaeger` receiver (gRPC, Thrift variants) | Collector config |
| **Zipkin** | Collector `zipkin` receiver/exporter | Collector config |
| **Fluent Forward / syslog / file logs** | Log receivers (Collector contrib) | Collector config |

---

## 5. Application Communication Patterns

These are the **cross-service interaction models** OTel semantic conventions standardize. Each defines span names, kinds, attributes, and (where applicable) metric instruments.

### 5.1 Pattern overview

| Pattern | Semconv domain | Stable opt-in env | Span roles | Key attribute namespaces |
| --- | --- | --- | --- | --- |
| **HTTP** | [HTTP](https://opentelemetry.io/docs/specs/semconv/http/) | `OTEL_SEMCONV_STABILITY_OPT_IN=http` | client, server | `http.*`, `url.*`, `network.*` |
| **RPC / RMI** | [RPC](https://opentelemetry.io/docs/specs/semconv/rpc/) | `…=rpc` | client, server | `rpc.*` |
| **Messaging** | [Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/) | `…=messaging` | producer, consumer | `messaging.*` |
| **Database** | [Database](https://opentelemetry.io/docs/specs/semconv/db/) | `…=database` | client (always) | `db.*`, `server.*` |
| **GraphQL** | [GraphQL](https://opentelemetry.io/docs/specs/semconv/graphql/) | — | server | GraphQL operation attributes |
| **CloudEvents** | [CloudEvents](https://opentelemetry.io/docs/specs/semconv/cloudevents/) | — | span modeling of CloudEvents | CloudEvents spec mapping |
| **Object stores** | [Object stores](https://opentelemetry.io/docs/specs/semconv/object-stores/) | — | client | S3 and similar |
| **Cloud provider SDKs** | [Cloud providers](https://opentelemetry.io/docs/specs/semconv/cloud-providers/) | — | client | AWS SDK spans (extensible) |
| **DNS** | [DNS](https://opentelemetry.io/docs/specs/semconv/dns/) | — | client | DNS lookup attributes |
| **NFS** | [NFS](https://opentelemetry.io/docs/specs/semconv/nfs/) | — | client/server | Network file system |

Stability opt-in also supports `*/dup` variants (e.g. `http/dup`) to emit both experimental and stable conventions during migration.

### 5.2 HTTP

- **Schemes:** `http`, `https`
- **Versions:** HTTP/1.1, HTTP/2, SPDY (per spec)
- **Signals:** spans, metrics, exceptions
- **Typical metrics:** `http.server.duration`, `http.server.request.body.size`, `http.server.response.body.size`; client-side analogs

### 5.3 RPC (including gRPC)

Generic [RPC conventions](https://opentelemetry.io/docs/specs/semconv/rpc/) plus technology-specific supplements:

| RPC system | Semconv doc | Notes |
| --- | --- | --- |
| **gRPC** | [gRPC](https://opentelemetry.io/docs/specs/semconv/rpc/grpc/) | `rpc.system=grpc`; service + method attributes |
| **Connect RPC** | [Connect](https://opentelemetry.io/docs/specs/semconv/rpc/connect-rpc/) | Connect protocol over HTTP |
| **Apache Dubbo** | [Dubbo](https://opentelemetry.io/docs/specs/semconv/rpc/dubbo/) | Java-centric RPC |
| **JSON-RPC** | [JSON-RPC](https://opentelemetry.io/docs/specs/semconv/rpc/json-rpc/) | JSON-RPC over various transports |

**Typical metrics:** `rpc.server.duration`, `rpc.server.request.size`, `rpc.server.response.size`, `rpc.server.requests_per_rpc`.

### 5.4 Messaging (async / event-driven)

Generic [messaging conventions](https://opentelemetry.io/docs/specs/semconv/messaging/) plus per-broker supplements:

| System | Semconv |
| --- | --- |
| Apache **Kafka** | [Kafka](https://opentelemetry.io/docs/specs/semconv/messaging/kafka/) |
| **RabbitMQ** | [RabbitMQ](https://opentelemetry.io/docs/specs/semconv/messaging/rabbitmq/) |
| Apache **RocketMQ** | [RocketMQ](https://opentelemetry.io/docs/specs/semconv/messaging/rocketmq/) |
| AWS **SNS** | [SNS](https://opentelemetry.io/docs/specs/semconv/messaging/aws-sns/) |
| AWS **SQS** | [SQS](https://opentelemetry.io/docs/specs/semconv/messaging/aws-sqs/) |
| Google **Cloud Pub/Sub** | [Pub/Sub](https://opentelemetry.io/docs/specs/semconv/messaging/gcp-pubsub/) |
| Azure **Service Bus** | [Service Bus](https://opentelemetry.io/docs/specs/semconv/messaging/azure-servicebus/) |
| Azure **Event Hubs** | [Event Hubs](https://opentelemetry.io/docs/specs/semconv/messaging/azure-event-hubs/) |

**Span kinds:** `PRODUCER` (publish/send), `CONSUMER` (receive/process).

### 5.5 Database (sync data access)

Generic [database conventions](https://opentelemetry.io/docs/specs/semconv/db/) plus per-engine supplements:

| Database / store | Semconv | `db.system` examples |
| --- | --- | --- |
| **SQL** (generic) | [SQL](https://opentelemetry.io/docs/specs/semconv/db/sql/) | `postgresql`, `mysql`, `mariadb`, `sqlite`, … |
| **Microsoft SQL Server** | [SQL Server](https://opentelemetry.io/docs/specs/semconv/db/sql-server/) | `mssql` |
| **Oracle** | [Oracle](https://opentelemetry.io/docs/specs/semconv/db/oracledb/) | `oracle` |
| **Redis** | [Redis](https://opentelemetry.io/docs/specs/semconv/db/redis/) | `redis` |
| **MongoDB** | [MongoDB](https://opentelemetry.io/docs/specs/semconv/db/mongodb/) | `mongodb` |
| **Elasticsearch** | [Elasticsearch](https://opentelemetry.io/docs/specs/semconv/db/elasticsearch/) | `elasticsearch` |
| **DynamoDB** | [DynamoDB](https://opentelemetry.io/docs/specs/semconv/db/dynamodb/) | `dynamodb` |
| **HBase** | [HBase](https://opentelemetry.io/docs/specs/semconv/db/hbase/) | `hbase` |

All database client spans use **`CLIENT`** kind.

### 5.6 GraphQL, FaaS, feature flags, GenAI

| Application style | Semconv status | OTel reference |
| --- | --- | --- |
| **GraphQL** servers | Development | [GraphQL spans](https://opentelemetry.io/docs/specs/semconv/graphql/) |
| **Function-as-a-Service** | Development | [FaaS](https://opentelemetry.io/docs/specs/semconv/faas/) — includes [AWS Lambda](https://opentelemetry.io/docs/specs/semconv/faas/aws-lambda/) |
| **Feature flag evaluation** | Development | [Feature flags in events](https://opentelemetry.io/docs/specs/semconv/feature-flags/) |
| **Generative AI** | Moved to dedicated repo | [OpenTelemetry semantic-conventions GenAI](https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai) |

### 5.7 CI/CD and CLI

| Pattern | Semconv | Signals |
| --- | --- | --- |
| **CI/CD pipelines** | [CI/CD](https://opentelemetry.io/docs/specs/semconv/cicd/) | spans, metrics, logs |
| **CLI programs** | [CLI](https://opentelemetry.io/docs/specs/semconv/cli/) | CLI invocation attributes |
| **Session** | [Session](https://opentelemetry.io/docs/specs/semconv/general/session/) | session.id and related |

---

## 6. Runtime and Platform Architectures

Resource and system semantic conventions describe **where code runs** and **what surrounds it** — the deployment architecture OTel recognizes.

### 6.1 Resource hierarchy (deployment topology)

From [Resource semantic conventions](https://opentelemetry.io/docs/specs/semconv/resource/):

```
Service (service.name, service.version, service.namespace)
  └── Telemetry SDK (telemetry.sdk.*)
  └── Compute unit
        ├── Process
        ├── Container
        ├── Function (FaaS)
        └── Web engine
  └── Compute instance
        └── Host
  └── Environment
        ├── Operating system
        ├── Device
        ├── Cloud (provider + region + account)
        ├── Kubernetes
        ├── OpenShift
        ├── CloudFoundry
        ├── Browser
        └── Deployment (deployment.environment)
```

**`service.name`** is the primary logical grouping key for applications.

### 6.2 Cloud providers (resource + SDK spans)

Valid `cloud.provider` values and provider-specific resource attributes:

| Provider | `cloud.provider` value |
| --- | --- |
| Alibaba Cloud | `alibaba_cloud` |
| Amazon Web Services | `aws` |
| Google Cloud Platform | `gcp` |
| Microsoft Azure | `azure` |
| Tencent Cloud | `tencent_cloud` |
| Heroku | (dyno-specific conventions) |

Cloud SDK client spans: [Cloud providers semconv](https://opentelemetry.io/docs/specs/semconv/cloud-providers/) (AWS SDK first).

### 6.3 Kubernetes and container orchestration

| Domain | Semconv | Metrics |
| --- | --- | --- |
| **Kubernetes** resources | [K8s resource attributes](https://opentelemetry.io/docs/specs/semconv/resource/k8s/) (`k8s.*`) | [K8s metrics](https://opentelemetry.io/docs/specs/semconv/system/k8s-metrics/) |
| **Containers** | [Container resources](https://opentelemetry.io/docs/specs/semconv/resource/container/) | [Container metrics](https://opentelemetry.io/docs/specs/semconv/system/container-metrics/) |
| **OpenShift** | [OpenShift](https://opentelemetry.io/docs/specs/semconv/system/openshift-metrics/) | Platform metrics |

### 6.4 System, process, and hardware metrics

[System semconv](https://opentelemetry.io/docs/specs/semconv/system/) covers:

- **System** (CPU, memory, disk, network, load)
- **Process** / **OS process**
- **Hardware**
- **Runtime environment** (language-specific — see §6.5)

Collector `hostmetrics` receiver scrapes many of these from the host OS.

### 6.5 Language runtime environments

[Runtime semconv](https://opentelemetry.io/docs/specs/semconv/runtime/) — metrics prefixed by runtime namespace (not cross-language comparable):

| Runtime prefix | Language / VM |
| --- | --- |
| `jvm.*` | Java / Kotlin on JVM |
| `cpython.*` / `pypy.*` | Python implementations |
| `go.*` | Go runtime |
| `nodejs.*` | Node.js |
| `v8js.*` | V8 JS engine |
| `dotnet.*` / CLR | .NET Common Language Runtime |

Use `process.runtime.*` resource attributes alongside runtime metrics.

### 6.6 Mobile, browser, and client platforms

| Platform | Semconv area |
| --- | --- |
| **Browser** | [Browser resources](https://opentelemetry.io/docs/specs/semconv/resource/browser/), [Browser semconv](https://opentelemetry.io/docs/specs/semconv/browser/) |
| **Mobile** | [Mobile platform](https://opentelemetry.io/docs/specs/semconv/mobile/) |
| **Android** | [Android](https://opentelemetry.io/docs/specs/semconv/resource/android/) |
| **.NET mobile/desktop** | [.NET semconv](https://opentelemetry.io/docs/specs/semconv/dotnet/) |

---

## 7. Collector Architecture Patterns

The [Collector](https://opentelemetry.io/docs/collector/) is the language-agnostic hub. Its architecture defines how telemetry flows in production systems.

### 7.1 Pipeline model

Each pipeline handles one signal type (`traces`, `metrics`, `logs`) through:

```
Receivers → Processors (optional, ordered) → Exporters
```

**Connectors** join pipelines (act as exporter in one, receiver in another — e.g. span-to-metric aggregation).

### 7.2 Deployment topologies (OTel-defined)

| Pattern | Description | Typical use |
| --- | --- | --- |
| **In-process (SDK only)** | App SDK exports directly to backend | Dev, small services |
| **Agent (DaemonSet / VM daemon)** | Collector runs beside apps; apps push OTLP locally | Node-level aggregation, config push to SDKs |
| **Sidecar** | Collector container per pod | K8s pod-level isolation |
| **Gateway** | Central collector tier receives from agents/libraries | Multi-cluster fan-in, routing, tail sampling |
| **Agent + Gateway** | Agents → gateway → backends | Large-scale standard layout |

See [Collector architecture — agent and gateway](https://opentelemetry.io/docs/collector/architecture/).

### 7.3 Core Collector protocol components (representative)

**Receivers** (ingest):

| Receiver | Signals | Role |
| --- | --- | --- |
| `otlp` | traces, metrics, logs | Primary OTel ingress (gRPC + HTTP) |
| `prometheus` | metrics | Pull/scrape Prometheus exposition |
| `jaeger` | traces | Jaeger formats (gRPC, Thrift) |
| `zipkin` | traces | Zipkin HTTP |
| `kafka` | traces, metrics, logs | Message-bus ingress |
| `opencensus` | traces, metrics | Legacy OpenCensus |
| `hostmetrics` | metrics | OS/host scraping |
| `fluentforward` | logs | Fluent Bit/Forward protocol |

Full lists: [opentelemetry-collector](https://github.com/open-telemetry/opentelemetry-collector) + [opentelemetry-collector-contrib](https://github.com/open-telemetry/opentelemetry-collector-contrib) registries.

**Exporters** (egress):

| Exporter | Signals | Role |
| --- | --- | --- |
| `otlp` / `otlp_grpc` / `otlp_http` | traces, metrics, logs | Primary OTel egress |
| `prometheus` | metrics | Expose Prometheus scrape endpoint |
| `prometheusremotewrite` | metrics | Remote-write to Prometheus-compatible |
| `zipkin` | traces | Zipkin backend |
| `kafka` | traces, metrics, logs | Message-bus egress |
| `file` / `debug` | all | Debug, testing |

**Processors** (transform): `batch`, `memory_limiter`, `attributes`, `resource`, `filter`, `probabilistic_sampler`, `transform`, `span`, and many contrib processors.

---

## 8. Semantic Convention Index (by concern)

Quick map of OTel semconv **domains** to the programming concerns they cover:

| Domain | Covers | Stability (typical) |
| --- | --- | --- |
| [General](https://opentelemetry.io/docs/specs/semconv/general/) | Cross-cutting span/metric/log/event attributes, errors, naming | Mixed |
| [Resource](https://opentelemetry.io/docs/specs/semconv/resource/) | Service identity, cloud, K8s, host, process, deployment | Mixed |
| [Trace](https://opentelemetry.io/docs/specs/semconv/general/trace/) | Span conventions not tied to a specific protocol | Stable areas |
| [HTTP](https://opentelemetry.io/docs/specs/semconv/http/) | REST, web APIs, HTTP/2 | Stabilizing (`OTEL_SEMCONV_STABILITY_OPT_IN`) |
| [RPC](https://opentelemetry.io/docs/specs/semconv/rpc/) | gRPC, Connect, Dubbo, JSON-RPC | Stabilizing |
| [Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/) | Queues, pub/sub, event buses | Stabilizing |
| [Database](https://opentelemetry.io/docs/specs/semconv/db/) | SQL, NoSQL, cache clients | Stabilizing |
| [System](https://opentelemetry.io/docs/specs/semconv/system/) | Host, container, K8s, process metrics | Development |
| [Runtime](https://opentelemetry.io/docs/specs/semconv/runtime/) | JVM, Go, Node, .NET, Python runtimes | Development |
| [FaaS](https://opentelemetry.io/docs/specs/semconv/faas/) | Serverless functions | Development |
| [GraphQL](https://opentelemetry.io/docs/specs/semconv/graphql/) | GraphQL servers | Development |
| [CloudEvents](https://opentelemetry.io/docs/specs/semconv/cloudevents/) | CloudEvents-as-spans | Development |
| [Object stores](https://opentelemetry.io/docs/specs/semconv/object-stores/) | S3 and similar | Development |
| [Cloud providers](https://opentelemetry.io/docs/specs/semconv/cloud-providers/) | Cloud SDK client calls | Development |
| [CI/CD](https://opentelemetry.io/docs/specs/semconv/cicd/) | Build/deploy pipelines | Development |
| [Feature flags](https://opentelemetry.io/docs/specs/semconv/feature-flags/) | Flag evaluation events | Development |
| [Exceptions](https://opentelemetry.io/docs/specs/semconv/exceptions/) | Exception recording on spans/logs | Stable areas |
| [OpenTelemetry SDK](https://opentelemetry.io/docs/specs/semconv/otel-sdk/) | SDK self-telemetry | Development |

**Registry:** machine-readable attribute registry at [opentelemetry.io/docs/specs/semconv/registry/](https://opentelemetry.io/docs/specs/semconv/registry/).

---

## 9. Cross-Language Instrumentation Matrix (protocol × language)

OTel does not publish one official matrix file, but the **semantic conventions + contrib instrumentation libraries** imply this landscape. Representative SDK entry points:

| Protocol / concern | Python | Go | Java | JavaScript | .NET |
| --- | --- | --- | --- | --- | --- |
| **HTTP server/client** | `opentelemetry-instrumentation-*` (Flask, Django, FastAPI, `requests`, `urllib3`) | `otelhttp` | OkHttp, Spring, etc. | `@opentelemetry/instrumentation-http` | `OpenTelemetry.Instrumentation.AspNetCore` |
| **gRPC** | `opentelemetry-instrumentation-grpc` | `otelgrpc` | gRPC Java instrumentation | `@opentelemetry/instrumentation-grpc` | gRPC .NET instrumentation |
| **Database** | DB-specific (psycopg2, SQLAlchemy, Redis, …) | `otelsql`, Redis, Mongo drivers | JDBC, Mongo, etc. | pg, mysql, mongodb instrumentations | SqlClient, EF Core, etc. |
| **Messaging** | Kafka, Celery, etc. | Sarama, etc. | Kafka clients | amqplib, etc. | Azure Service Bus, etc. |
| **AWS SDK** | boto3 instrumentation | aws-sdk-go | AWS SDK Java | AWS SDK JS | AWS SDK .NET |

Full inventory: [OpenTelemetry Registry — instrumentation](https://opentelemetry.io/ecosystem/registry/?s=instrumentation).

---

## 10. Configuration and Environment Surface

OTel standardizes cross-language configuration via environment variables ([SDK configuration spec](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)):

| Variable (representative) | Purpose |
| --- | --- |
| `OTEL_SERVICE_NAME` | Resource `service.name` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint (gRPC default) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `grpc` or `http/protobuf` |
| `OTEL_TRACES_EXPORTER` / `OTEL_METRICS_EXPORTER` / `OTEL_LOGS_EXPORTER` | Exporter selection |
| `OTEL_PROPAGATORS` | Comma-separated propagator list |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional resource attributes |
| `OTEL_SEMCONV_STABILITY_OPT_IN` | Stable semconv migration (`http`, `rpc`, `database`, `messaging`, `*/dup`) |

---

## 11. Relationship to StartD8 Code Observability

This catalog describes **OTel's** landscape — the substrate for runtime/service observability. StartD8's code-observability work (see `CODE_OBSERVABILITY_*` docs) extends this with **static code structure** (imports, dataflow, taint) that OTel does not define. Intersection points:

| OTel concept | StartD8 usage |
| --- | --- |
| Traces + span attributes | Pipeline phase spans, ContextCore resource attributes (`io.contextcore.*`) |
| OTLP/gRPC export | Local Wayfinder stack (Tempo/Mimir/Loki via Alloy) |
| HTTP/gRPC semconv | Instrumentation contract derivation (`_PROTOCOL_METRICS`, `_OTEL_SDK_MAP`) |
| Span links API | Optional enrichment for DATAFLOW (canonical graph remains out-of-band) |
| Resource `service.name` | Per-script/workflow identity in `configure_otel()` |

---

## 12. Primary References

1. [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/)
2. [Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
3. [OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
4. [Language SDK Status](https://opentelemetry.io/status/)
5. [Language SDKs Overview](https://opentelemetry.io/docs/languages/)
6. [Signals Overview](https://opentelemetry.io/docs/concepts/signals/)
7. [Collector Architecture](https://opentelemetry.io/docs/collector/architecture/)
8. [Collector Configuration](https://opentelemetry.io/docs/collector/configuration/)
9. [Propagators API](https://opentelemetry.io/docs/specs/otel/context/api-propagators/)
10. [Compatibility (OpenCensus, OpenTracing, Prometheus)](https://opentelemetry.io/docs/specs/otel/compatibility/)
11. [Zero-code Instrumentation](https://opentelemetry.io/docs/zero-code/)
12. [OpenTelemetry Registry](https://opentelemetry.io/ecosystem/registry/)
13. [Resource Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/resource/)
14. [Runtime Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/runtime/)

---

## Document maintenance

- **Refresh trigger:** OTel minor spec releases (check [Status](https://opentelemetry.io/status/) and [Semconv changelog](https://github.com/open-telemetry/semantic-conventions/releases)).
- **Known drift risk:** Semconv stability opt-in categories, GenAI conventions (external repo), Collector contrib component inventory, language SDK logs/profiles maturity.
