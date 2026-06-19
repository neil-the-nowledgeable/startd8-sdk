# OTel Demo as a Map — Coverage Quick Wins (most coverage, least work)

> **Date:** 2026-06-18  
> **Map:** [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo) ("Astronomy Shop", `oteldemo`, Apache-2.0, v2.2.0)  
> **Coverage axes:** the landscape dimensions in [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](./OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md), scored against the gaps in [OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md](./OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md).  
> **Question answered:** Using the OTel Demo as the superset reference, which functional and architectural pieces close the most landscape gaps for the least effort?

---

## 1. How to read this doc

"Coverage" = landscape-catalog dimensions a piece unlocks (signals, languages, protocols, application patterns, collector topology, deploy model). "Work" = effort to **stand up, extract, or adopt** that piece, given OB is already our baseline corpus.

The central insight: **the OTel Demo already ships the coverage as toggles.** Where Online Boutique required custom GKE + a kustomize overlay to get even traces, the OTel Demo ships `docker compose` profiles (`compose.observability.yaml`, `compose.profiling.yaml`), a ready `otel-config.yml` Collector, and 12 languages. So most "quick wins" are **flip-a-flag**, not build-from-scratch.

Scoring legend:

- **Coverage:** ★ (1 gap) → ★★★★★ (many gaps / a whole landscape section)
- **Work:** ⚡ (minutes–hours, config only) → 🔨🔨🔨 (multi-day, new code/extraction)

---

## 2. The map — OTel Demo components → landscape coverage

| OTel Demo component | Landscape § unlocked | Closes OB gap (overlap §5) | Coverage | Work |
| --- | --- | --- | ---: | ---: |
| `docker compose up` (base) | §7.2 deploy model | GKE-only → laptop in minutes | ★★★ | ⚡ |
| `compose.observability.yaml` (Jaeger + Prometheus + Grafana + OpenSearch) | §7.1/§7.3 multi-backend fan-out | single `googlecloud` exporter | ★★★★ | ⚡ |
| `otel-config.yml` + span-metrics connector | §7.1 connectors | no connector in OB | ★★★ | ⚡ |
| `compose.profiling.yaml` (Pyroscope) | §2 **Profiles** signal | OB has no profiles | ★★★ | ⚡ |
| OTLP/HTTP + OTLP/gRPC both wired | §4.1 OTLP/HTTP | OB apps only gRPC | ★★ | ⚡ |
| W3C Trace Context across all hops | §4.2 propagation (full mesh) | OB only when overlay on | ★★ | ⚡ |
| **flagd** + flagd-ui | §5.6 **feature flags** | absent in OB | ★★ | 🔨 |
| **Kafka** queue (accounting, fraud-detection) | §5.4 **messaging** (PRODUCER/CONSUMER) | absent in OB | ★★★★ | 🔨 |
| **PostgreSQL** (accounting, product-reviews) | §5.5 **SQL database** | OB Redis-only | ★★★ | 🔨 |
| frontend-proxy (**Envoy**) | §5.2 edge proxy / L7 | OB plain Go HTTP | ★★ | 🔨 |
| image-provider (**nginx**) | §5.2 static HTTP serving | — | ★ | ⚡ |
| **llm** (Python) + ProductReview AI RPC | §5.6 **GenAI** semconv | absent in OB | ★★★ | 🔨🔨 |
| 7 added languages (C++, Ruby, Rust, Kotlin, PHP, Elixir, TS) | §3.1 SDK breadth (5→12) | OB 5 languages | ★★★★★ | 🔨🔨🔨 (per lang) |
| react-native-app (TS) | §6.6 **mobile** platform | absent in OB | ★★ | 🔨🔨 |
| `telemetry-schema/` | §8 schema/versioning | absent in OB | ★ | ⚡ |
| Locust load-generator | traffic gen (drives all signals) | OB has one too | ★ | ⚡ |

---

## 3. Quick-win tiers (ranked by coverage ÷ work)

### Tier 0 — Free / hours (config toggles, zero new code)

These are pure **architectural** wins. Standing up the demo with its shipped compose profiles instantly closes the biggest, cheapest gaps OB left open.

| # | Win | Unlocks | Why it's free |
| --- | --- | --- | --- |
| 0.1 | **Stand up via `docker compose`** | §7.2 laptop deploy; whole mesh live | One command; no GKE, no kustomize |
| 0.2 | **Enable `compose.observability.yaml`** | §7.3 Jaeger + Prometheus + OpenSearch + Grafana fan-out; §2 traces+metrics+logs all visible | Backends + wiring pre-authored |
| 0.3 | **Enable `compose.profiling.yaml`** | §2 **Profiles** signal (Pyroscope) — a whole signal OB never had | Pre-wired profile pipeline |
| 0.4 | **Adopt `otel-config.yml` Collector** | §7.1 processors + **span-metrics connector**; OTLP gRPC **and** HTTP receivers | Reference config, copy/borrow verbatim |

**Tier 0 payoff:** moves coverage from "OB + custom overlay" to **3 signals + multi-backend + connectors + both OTLP transports + profiles** — for essentially the cost of `git clone && docker compose up`.

### Tier 1 — Half-day each (extract existing services into corpus / patterns)

These are **functional** wins. The services already exist and emit telemetry; the work is **extraction into the StartD8 benchmark corpus** (`gen_otel_benchmark_seeds.py`, already planned) or wiring the pattern into instrumentation-contract derivation.

| # | Win | Unlocks | Effort note |
| --- | --- | --- | --- |
| 1.1 | **Kafka messaging path** (accounting / fraud-detection consumers) | §5.4 PRODUCER/CONSUMER spans, `messaging.*` semconv — **the single largest missing pattern** | Highest coverage/work in this tier; consumers are TCP/Kafka, not RPC servers — declare as pattern, even if not a benchmark RPC cell |
| 1.2 | **PostgreSQL path** (product-reviews, accounting) | §5.5 SQL `db.system=postgresql` client spans | product-reviews is also a **new Python task** (not an OB restatement) — see seed plan OQ-OT-2 |
| 1.3 | **flagd feature flags** | §5.6 feature-flag evaluation events | Many services call flagd over gRPC — propagation + flag semconv for free |
| 1.4 | **Adopt OTel Demo seeds (5 covered langs)** | benchmark corpus parity; bolsters **Java + C#** depth, adds 2nd Python | Already specced: `OTEL_DEMO_SEED_EXTRACTION_PLAN.md` — copy `gen_ob_benchmark_seeds.py`, swap data |
| 1.5 | **Envoy frontend-proxy + nginx image-provider** | §5.2 L7 proxy + static serving edge patterns | Config/infra services; declare in service graph |

### Tier 2 — Multi-day (new code / language ramp)

Real engineering. Do these only when the cheaper tiers are exhausted and the specific coverage is needed.

| # | Win | Unlocks | Why it's heavier |
| --- | --- | --- | --- |
| 2.1 | **Add one new SDK language to corpus** (start: Rust *shipping* or PHP *quote*) | §3.1 SDK breadth, per language | Each needs language profile, compile gate, startup block, runtime semconv (`§6.5`) validation — `OTEL_DEMO_SEED_EXTRACTION_PLAN` excludes these in v1 |
| 2.2 | **GenAI llm service** | §5.6 GenAI semconv (external repo) | Non-deterministic, external model dep; seed plan explicitly omits `AskProductAIAssistant` |
| 2.3 | **react-native-app** | §6.6 mobile platform semconv | Mobile SDK + build toolchain |
| 2.4 | **Remaining languages** (C++, Ruby, Kotlin, Elixir, TS) | §3.1 full 12/12 | Diminishing return per language; do on demand |

---

## 4. Two lenses

### 4.1 Functional coverage (patterns & services)

Ranked by gap size closed per unit work:

1. **Kafka messaging** (Tier 1.1) — closes the entire §5.4 domain OB is silent on. Best functional ROI.
2. **PostgreSQL** (Tier 1.2) — closes §5.5 SQL; doubles as a genuinely new Python benchmark task.
3. **flagd feature flags** (Tier 1.3) — closes §5.6 feature flags; cheap because it's gRPC the mesh already speaks.
4. **GenAI** (Tier 2.2) — high interest, but non-deterministic → defer for benchmark use.

### 4.2 Architectural coverage (signals, collector, topology, deploy)

Ranked by gap size closed per unit work:

1. **Observability compose** (Tier 0.2) — multi-backend fan-out + all three signals visible, $0.
2. **Profiling compose** (Tier 0.3) — adds the Profiles signal wholesale, $0.
3. **Collector `otel-config.yml` + span-metrics connector** (Tier 0.4) — connectors + dual OTLP transport, $0.
4. **Docker-compose deploy** (Tier 0.1) — collapses OB's GKE barrier to a laptop command.

**Architectural wins dominate the cheap end:** every Tier-0 item is a config toggle that closes a landscape section OB left empty.

---

## 5. Recommended sequence (coverage curve)

```
Day 0  ── Tier 0 (0.1→0.4): clone + compose up + observability + profiling
          → 3 signals, profiles, multi-backend, connectors, dual OTLP   [biggest jump, ~$0]
          │
Day 1  ── Tier 1.4: extract OTel Demo seeds (5 langs) → corpus parity
          Tier 1.1: declare Kafka messaging pattern  → §5.4 closed
          Tier 1.2: declare PostgreSQL pattern       → §5.5 closed
          Tier 1.3: declare flagd feature-flag path  → §5.6 (flags) closed
          │
Week 1 ── Tier 2.1: add ONE new language (Rust or PHP) end-to-end
          │
Later  ── Tier 2.2–2.4 on demand (GenAI, mobile, remaining langs)
```

The curve is intentionally front-loaded: **~80% of the missing landscape coverage is reachable by end of Day 1**, almost entirely through configuration and data extraction rather than new code.

---

## 6. Coverage delta — before vs after

| Landscape § | OB baseline | After Tier 0 | After Tier 1 | Full OTel Demo (Tier 2) |
| --- | --- | --- | --- | --- |
| §2 Signals | traces + partial metrics (overlay) | **+ logs + profiles** | same | same |
| §3.1 Languages | 5 / 12 | 5 / 12 | 5 / 12 (corpus parity) | **12 / 12** |
| §4.1 OTLP | gRPC only | **+ HTTP** | same | same |
| §4.2 Propagation | overlay only | **full mesh W3C** | same | same |
| §5.2 HTTP | frontend | **+ Envoy + nginx** | same | same |
| §5.3 gRPC | core | core | core | core |
| §5.4 Messaging | — | — | **Kafka** | Kafka |
| §5.5 Database | Redis | Redis (+Valkey) | **+ PostgreSQL** | + PostgreSQL |
| §5.6 Flags / GenAI | — | — | **flagd** | **+ GenAI llm** |
| §6.6 Mobile/Browser | — | — | — | **react-native** |
| §7 Collector | gateway → googlecloud | **fan-out + connectors** | same | same |
| §7.2 Deploy | GKE/kustomize | **docker compose** | same | same |

---

## 7. Caveats

- **Contamination:** OTel Demo is a famous public repo — frontier models have memorized it, same as OB (`OTEL_DEMO_SEED_EXTRACTION_PLAN` §6). Coverage breadth ≠ contamination resistance.
- **Non-RPC shapes:** Kafka consumers (accounting, fraud-detection) aren't gRPC servers; they extend **pattern** coverage but don't fit the "one RPC service per cell" benchmark shape — count them for landscape coverage, not as benchmark cells.
- **Behavioral vs structural:** Tier-1 seed extraction is structural-first; behavioral (Track 2) needs per-service `startup` blocks derived from each Dockerfile (seed plan OQ-OT-1).
- **Per-corpus reporting:** don't pool OTel Demo and OB scores; report separately (seed plan OQ-OT-5).

---

## 8. Bottom line

| Want the most coverage for the least work? Do this first: |
| --- |
| **1. `docker compose up` + observability + profiling profiles** → 3 signals, profiles, multi-backend, connectors, dual OTLP — all $0 config (Tier 0). |
| **2. Extract OTel Demo seeds + declare the Kafka / Postgres / flagd patterns** → closes messaging, SQL, and feature-flag landscape sections in ~1 day (Tier 1). |
| **3. Add one new language only when you actually need SDK breadth** (Tier 2). |

The OTel Demo's value as a map is that it **pre-packages the coverage as toggles**: the highest-leverage moves are architectural config flips, not functional rebuilds.

---

## 9. References

1. [OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md](./OTEL_PROGRAMMING_LANDSCAPE_CATALOG.md) — coverage axes
2. [OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md](./OTEL_LANDSCAPE_ONLINE_BOUTIQUE_OVERLAP.md) — gap baseline
3. [OTEL_DEMO_SEED_EXTRACTION_PLAN.md](./otel-demo-corpus/OTEL_DEMO_SEED_EXTRACTION_PLAN.md) — corpus extraction (Tier 1.4)
4. [OpenTelemetry Demo repo](https://github.com/open-telemetry/opentelemetry-demo) — compose profiles, `otel-config.yml`, 12 languages
5. [OpenTelemetry Demo architecture](https://opentelemetry.io/docs/demo/architecture/) — service graph, telemetry data flow
