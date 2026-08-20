# Convergence findings from piloting the canonical generator into a new consumer (OTel Astronomy Shop 3.0)

**To:** startd8-sdk / SDK team
**Date:** 2026-08-19
**Re:** `CONTEXTCORE_GENERATOR_CONVERGENCE_NEEDS_2026-08-05.md` (this is the after-action follow-up)

**TL;DR:** The 2026-08-05 convergence **shape** fix landed — the legacy divergent RED shape
(`http_requests_total{status=~"5.."}`) is gone; artifacts now come from
`generate_observability_artifacts`. But piloting the *canonical* generator into a **different
consumer** (a live OTel Astronomy Shop 3.0 backend) surfaced **two deeper SDK-side gaps** the
2026-08-05 note did not anticipate, plus one non-SDK infra bug (noted for completeness). Both SDK
gaps are about **the generator not knowing the target's real metric surface** — the exact class §4
of the original note tried to close, one level deeper. Concrete asks in §4 below.

---

## 1. Three layers — only the first was closed by the convergence

| Layer | What we expected | What we found | Owner |
|---|---|---|---|
| **Shape** | Legacy `http_requests_total{status=~"5.."}` retired | ✅ Gone — canonical generator in use | SDK (done) |
| **Name binding** | Canonical names resolve against the backend | ❌ Generator emits OTel-Collector **default** span-metric names; this backend namespaces them `traces_span_metrics_*`. 266/292 queries resolved to 0 series | **SDK** |
| **SLO profile** | Per-service RED alerts are meaningful | ❌ One **global** RED profile applied to every target; async consumers get a request-latency p99 that is semantically wrong; no way to disable one RED dimension via the manifest | **SDK** |

(The third, non-SDK issue: a port-remap bug in the pilot's own compose wiring starved 6 services of
traffic. Fixed in the pilot; not an SDK concern — flagged only so the numbers below make sense.)

## 2. Gap A — canonical generation emits **backend-default** names, not the backend's real names

The convergence switched generation to the OTel-Collector spanmetrics-connector **default** family.
But a consumer's collector can namespace those metrics. The Astronomy Shop's collector emits:

| Generator emits (canonical default) | This backend actually has | Fix needed |
|---|---|---|
| `calls_total` | `traces_span_metrics_calls_total` | namespace prefix |
| `duration_milliseconds_bucket` | `traces_span_metrics_duration_milliseconds_bucket` | namespace prefix |
| `http_server_request_body_size_bucket` | `http_server_request_body_size_**bytes**_bucket` | OTel→Prom `_bytes` **unit suffix** omitted |

Two distinct failure modes: a **namespace** the generator can't know, and a **unit-suffix**
(`_bytes`) the OTel→Prometheus translation adds that the generator's name table omits. (The
unit-suffix defect is written up in full in `OBSERVABILITY_GENERATOR_FIDELITY_FINDINGS_2026-08-19.md`,
Finding A.)

**Why this matters for §4 of the original note.** §4 shipped `canonical_red_exprs` / `red_http` as a
single importable convention — necessary, but **not sufficient**: it standardises *one* canonical
spelling, whereas a real consumer's spelling is a function of *its* collector config (namespace,
unit-suffix policy). The binding has to be **backend-parameterised**, not a single global constant. A
`BackendProfile`-style metric-name map (namespace prefix + unit-suffix policy + label keys) that the
generator consults would close this at the source.

**How we worked around it (output path):** extended a consumer-side `retarget_promql.py` with
namespace-prefix rules for the canonical default names and a `_bytes` unit-suffix rule, wired into the
generate step. Result: PromQL validation PASS **26 → 201**. This is the "output path" stopgap the
original note's §2 anticipated; the durable fix is the input-path binding above.

## 3. Gap B — one global RED profile per target; no per-service / per-dimension control

`spec.requirements` (availability / latencyP99 / throughput) is applied **globally** to every
`spec.targets` entry. On a real fleet this breaks two ways:

1. **Async/consumer services.** Kafka-consumer services (e.g. accounting, fraud-detection) have a span
   "latency" p99 that is ~15 s (consume+process time), not request latency. A uniform p99 RED SLO is
   semantically wrong for them — but there is no per-service override to say "error-rate + availability,
   no request-latency" for a consumer.
2. **Can't drop one RED dimension.** We wanted error-rate + availability but **not** latency (see Gap
   C). Removing `latencyP99` from `spec.requirements` did **not** stop latency-alert generation — the
   generator fell back to an **importance-based default** threshold and emitted a `*LatencyP99High` per
   service anyway. The only way to drop it was a post-generation strip (`drop_latency_alerts.py`).

**Ask:** a per-target `requirements` override (or a `profile: async|sync|batch` per target), and a way
to disable a RED dimension without post-processing. An `async`/`consumer` profile that maps to lag+error
SLOs instead of request-latency p99 would be the principled fix for (1).

## 4. Gap C (context, not an SDK ask) — p99 fidelity on the real backend

Worth recording because it drove the Gap-B ask: on this backend the span-metrics duration histogram
uses **coarse default buckets** (`… 2000, 5000, 10000, 15000, +Inf`) and a low request rate (30–160
calls/5m for most services) makes `histogram_quantile(0.99, …)` **saturate into the top buckets** — many
unrelated services pin to exactly 15000 ms. No static threshold stabilises it. We dropped
request-latency p99 alerting for this pilot and rely on error-rate + availability (reliable) + a
fault-injection flow. Not an SDK defect — but it is *why* per-service / per-dimension SLO control (Gap B)
is load-bearing, not a nicety.

## 5. Concrete asks (prioritised)

1. **Backend-parameterised metric-name binding** (Gap A) — a `BackendProfile` the generator consults
   for: metric **namespace** prefix, OTel→Prom **unit-suffix** policy (`_bytes`, `_seconds`), and label
   keys (`service_name`, `status_code`). Closes the divergence at the source; retires the
   `retarget_promql.py` output-path stopgap. Extends §4 of the 2026-08-05 note.
2. **Per-target SLO override + per-dimension enable** (Gap B) — `requirements` per target (or a
   `profile: sync|async|batch`), and the ability to omit a RED dimension without a default kicking in.
   An `async` profile → lag+error SLOs (not request-latency p99).

## 6. Provenance

A generator pilot against a live OTel Astronomy Shop 3.0 backend. Evidence: PromQL validation PASS
26→201 after the retarget extension; the pilot's tooling (`retarget_promql.py`, `drop_latency_alerts.py`,
`METRIC_SCHEMA_MAP.md`) + a calibrated `.contextcore.yaml`; baseline verified clean via the pilot's
preflight. The canonical generator's own coverage descriptor (`observability-quality.json`) still lists
the stale semconv name `http_server_duration` as an expected metric — minor metadata staleness worth a
look while addressing Gap A.
