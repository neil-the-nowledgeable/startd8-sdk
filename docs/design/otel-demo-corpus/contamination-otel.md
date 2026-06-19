# Tier 1 — OTel Demo corpus contamination index (FR-5 / NR-7)

**Corpus id:** `otel-demo`  
**Seeds dir:** `docs/design/model-benchmark/seeds-otel/`  
**Generator:** `scripts/gen_otel_benchmark_seeds.py`  
**Related:** [TIER1_CORPUS_REQUIREMENTS.md](./TIER1_CORPUS_REQUIREMENTS.md) · [OTEL_DEMO_SEED_EXTRACTION_PLAN.md](./OTEL_DEMO_SEED_EXTRACTION_PLAN.md)

---

## Contamination posture

The OpenTelemetry Demo (`open-telemetry/opentelemetry-demo`) is a **famous public repository**.
Frontier models may have memorized its layout, proto, and service implementations in pretraining —
the same contamination class as Online Boutique (OB). A second corpus buys **task variety and
Java/C#/second-Python depth**, not contamination resistance.

Tier 1 registers this corpus for the FR-47 perturbation/rename probe and reuses the existing Jetson
firewall token list in `src/startd8/benchmark_matrix/firewall.py`:

| Token | Rationale |
| --- | --- |
| `opentelemetry` | Corpus name / docs |
| `otel` | Short corpus token |
| `microservices-demo` | OB lineage (OTel demo descends from hipstershop) |
| `online boutique` | OB sibling corpus — cross-corpus leakage |
| `grpc servicer` | House-style gRPC boilerplate |
| `apache` | Shared license header in proto |

**Firewall rule:** cells whose system prompt contains any `BANNED_CORPUS_TOKENS` substring are
**invalidated** (not scored on the general leaderboard). OTel runs MUST use the neutral benchmark
prompt path — same as OB.

---

## Per-corpus reporting (no pooling)

**OTel and OB scores MUST NOT be pooled into one leaderboard** (OQ-OT-5 / NR-7).

| Corpus | Seeds dir | Services | Report separately |
| --- | --- | --- | --- |
| Online Boutique | `docs/design/model-benchmark/seeds/` | 9 (+ hardened variants) | `corpus=ob` |
| OTel Demo | `docs/design/model-benchmark/seeds-otel/` | 7 covered gRPC | `corpus=otel-demo` |

When publishing matrix results:

1. Tag the run spec / scorecard with `corpus: otel-demo` (from `seeds-index.json`).
2. Do **not** merge OTel cells with OB cells in `build_combined_scorecard.py` unless explicitly
   comparing methods within one corpus.
3. Run the FR-47 perturbation probe on OTel seeds before trusting absolute scores on memorized repos.

---

## Behavioral vs structural expectations

Only **`payment`** and **`product-catalog`** are `behavioral_eligible=true` in v1 (supported
language + no runtime DB/broker/downstream gRPC). All other OTel cells are **structural-only** for
Track 2; the harness degrades honestly (FR-32), never scores 0 for missing toolchain alone.

| Service | Language | behavioral_eligible | Why |
| --- | --- | --- | --- |
| payment | nodejs | true | leaf, securely provisioned |
| product-catalog | go | true | file-backed leaf |
| recommendation | python | false | downstream gRPC |
| product-reviews | python | false | Postgres dep |
| checkout | go | false | orchestrator + Kafka |
| cart | csharp | false | C# not securely provisioned |
| ad | java | false | Java not securely provisioned |

---

## v1 deliverable (index-only)

Per OQ-3 lean: this document is the **contamination index** for v1. Perturbation/rename seed variants
are deferred until a clean-room track is needed.

**Assertion (A6):** OTel ↔ OB pooling is forbidden; each corpus gets its own leaderboard and
contamination disclosure.
