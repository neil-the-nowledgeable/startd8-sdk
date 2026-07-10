# SPIKE: Static Observability-Fidelity

**Status:** spike / prototype — reported-not-scored, not wired into the benchmark runner
**Date:** 2026-07-10
**Prototype:** `src/startd8/observability/observability_fidelity_static.py`
**Demo:** `src/startd8/observability/_spike_fixtures/demo_static_fidelity.py`
**Tests:** `tests/unit/observability/test_observability_fidelity_static.py` (12 passing)

---

## 1. The concept

The SDK benchmark (`src/startd8/benchmark_matrix/`) scores whether a generated
**service's code** works — it compiles and passes behavioral suites. It does
**not** score whether the service's generated **observability** is correct. A
run can produce a perfectly-compiling service *and* a set of alerts/SLOs/dashboards
that query metrics the service never emits. That mismatch is invisible today until
someone stands up Prometheus and notices every panel is empty.

**Static observability-fidelity** is a two-sided binding check between two
*generated artifacts*, with **zero runtime**:

- **Emitted set** — the metric names a service's **source code** actually emits
  (its OTel/Prometheus instrument names, plus the OTel semantic-convention metrics
  implied by its transport).
- **Referenced set** — the metric names the generated **observability** (the PromQL
  in alerts / SLOs / dashboards) **references**.
- **Static fidelity** — `coverage = |referenced ∩ emitted| / |referenced|`. A
  referenced metric absent from the emitted set is a **binding failure**: the alert
  queries a metric the service never produces.

This is the live fidelity harness's two-sided-binding idea
(`validate_promql.py`: `extract_exprs`, `diagnose_axes`, `MetricDescriptor`)
applied between two generated artifacts instead of against a live Prometheus. The
live harness is still the authoritative fidelity signal; this is a **$0,
recomputable, offline** approximation of it.

---

## 2. Does the concept work? — Yes, demonstrably

Grounded against **real generated observability**: the bpi-astronomy Online
Boutique demo output (`.../bpi-astronomy/out/observability/`), 13 services, real
`alerts/ slos/ dashboards/` YAML. That output was generated assuming the
**span-metrics-connector** convention (`calls_total`, `duration_milliseconds_bucket`,
label `service_name`, `status_code="STATUS_CODE_ERROR"`).

Paired with fixture service sources that reproduce the real instrumentation shapes
(`_spike_fixtures/services/`):

| Service | Fixture source | Instrumentation | Emitted RED metric |
|---|---|---|---|
| checkoutservice | Go | OTel gRPC-server auto-instr (semconv-grpc) | `rpc_server_duration` |
| paymentservice | Python | span-metrics `calls_total` + Flask/http | `calls_total`, `duration_milliseconds` |
| adservice | Node | OTel gRPC-server auto-instr (semconv-grpc) | `rpc_server_duration` |

### Demo output (real numbers, `python3 .../demo_static_fidelity.py`)

```
SERVICE: checkoutservice   (Go, semconv-grpc)
  EMITTED    (12): app_orders_placed_total(+family), checkout_pipeline_seconds(+family),
                   rpc_server_duration(+family)
  REFERENCED  (4): calls_total, duration_milliseconds_bucket,
                   http_server_request_body_size_bucket, http_server_response_body_size_bucket
  UNBOUND     (4): calls_total, duration_milliseconds_bucket,
                   http_server_request_body_size_bucket, http_server_response_body_size_bucket
  coverage: 0.0    VERDICT: FAIL      ← profile mismatch caught, zero runtime

SERVICE: paymentservice    (Python, emits calls_total)
  REFERENCED  (4): calls_total, duration_milliseconds_bucket,
                   http_server_request_body_size_bucket, http_server_response_body_size_bucket
  UNBOUND     (2): http_server_request_body_size_bucket, http_server_response_body_size_bucket
  coverage: 0.5    VERDICT: PARTIAL   ← RED binds; body-size histograms don't

SERVICE: adservice         (Node, semconv-grpc)
  UNBOUND     (4): calls_total, duration_milliseconds_bucket, http_server_*_body_size_bucket
  coverage: 0.0    VERDICT: FAIL
```

**The load-bearing result:** the generated Online-Boutique alerts assume
`calls_total` (span-metrics), but a gRPC service auto-instrumented with OTel
semconv emits `rpc_server_duration`. That is a real, common, silent
misconfiguration — and it is caught here with **no Prometheus and no running
service**. This is precisely the `diagnose_axes` "metric_name axis mismatch" the
live harness reports, recovered offline.

The `paymentservice` PARTIAL is also a *true* finding, not noise: the generated
dashboards reference `http_server_request_body_size_bucket` /
`_response_body_size_bucket`, which are OTel HTTP-semconv metrics the service does
not emit (they require explicit body-size instrumentation). Coverage 0.5 correctly
flags "your RED alerts bind, but two dashboard panels will be blank."

---

## 3. How accurately can emitted metrics be extracted? (the hard part — honest)

Emitted-side extraction is regex + transport-implication, **not** a compiler. Per
language:

| Language | Explicit constructors | Recall | Precision | Notes |
|---|---|---|---|---|
| **Python** | `meter.create_counter/histogram/gauge/...`; `prometheus_client` `Counter/Histogram/Gauge/Summary("name")` | **High** for literal-string names | **High** | Best-supported. Names built from f-strings/constants are missed. |
| **Go** | OTel `Int64Counter/Float64Histogram("name")`; `prometheus.*Opts{Name: "..."}` (promauto) | **Medium** | **Medium** | The `Name:` regex is broad — it matches *any* `Name:` field in a struct literal, so a non-metric `Name:` could be a false positive. Acceptable for a spike; needs the Go AST (`go/parser`) for production. |
| **Node/TS** | OTel `meter.createCounter('name')`; prom-client `new client.Counter({name:'...'})` | **Medium** | **Medium** | Same broad-`name:` caveat as Go. TS type syntax not an issue for the regex. |
| Java / C# / Rust / … | none | **0** | — | Not parsed. Online Boutique's real adservice is Java — unsupported today. |

**Transport-implied semconv metrics** are the crucial recall path. Auto-instrumented
services emit **no explicit constructor at all** — their RED metrics come from the
OTel gRPC/HTTP instrumentation. The prototype sniffs transport from import/framework
fingerprints (`grpc`, `flask`, `net/http`, `@grpc/grpc-js`, …) and adds the semconv
base (`rpc_server_duration` / `http_server_duration`) + histogram family. Without
this, every auto-instrumented service would falsely report coverage 0.0. This
mirrors `metric_descriptor.py`'s `semconv-grpc` / `semconv-http` profiles.

**Suffix / family expansion:** PromQL references histogram-derived series
(`_bucket` / `_count` / `_sum`) and counter `_total`, which the constructor name
doesn't spell out. The prototype expands every base name into the histogram family.
This over-generates the emitted set deliberately — the safe direction, since it can
only *hide* a real gap (false negative), never *invent* one (false positive).

### False-positive / false-negative risk

**False negatives (report a binding gap that isn't real) — the main risk:**
- metric name built by concatenation / f-string / constant (`PREFIX + "_total"`);
- instrument created through an unrecognized project-local wrapper;
- a language we don't parse (Java/C#/Rust);
- collector-produced metrics: `calls_total`/`duration_milliseconds` from the
  **span-metrics connector** are emitted by the *collector*, not the service source,
  so they are invisible to a pure source scan (see §5, gap G2).

**False positives (bind when it shouldn't):**
- a metric named only in a comment / dead code / test file;
- the broad Go/Node `Name:`/`name:` match catching a non-metric field;
- transport-implied metric assumed present when auto-instrumentation is actually
  disabled at runtime.

Net: **false negatives dominate**, which for a *reported-not-scored* signal is the
tolerable direction — a flagged gap invites a look; it doesn't fail a build.

---

## 4. Value to the benchmark

A new **"$0-recomputable, reported-not-scored"** dimension:

- **New signal, no new cost.** Both inputs already exist in every generation run
  (the service code and the observability tree). Recomputable offline over any
  historical run dir; no Prometheus, no service boot, no LLM call.
- **Catches a class the code-only benchmark can't see.** Compile + behavioral both
  pass while the observability silently references non-existent metrics. This
  dimension is orthogonal to both.
- **Approximates the authoritative live signal offline.** It surfaces the same
  metric-name-axis mismatch `validate_promql.diagnose_axes` reports, but as a fast
  pre-filter — cheap enough to run on every candidate, reserving the live replay
  for a final gate.
- **Directional, not a gate.** Report coverage + unbound list per service; do not
  fail a run on it (false-negative surface too wide). It's a "look here" flag, the
  same posture the codebase already uses for the static coverage gate vs. the live
  fidelity signal ("no static 1.0 masquerading as fidelity").

---

## 5. Productionization path + gaps

**Reuse already in place (Mottainai):** the referenced side reuses
`validate_promql.extract_exprs`, `strip_threshold`, `substitute_grafana_macros`
verbatim. The only net-new code is `bare_metrics_from_expr` (pull bare metric
identifiers out of an expr — the live harness never needed this because it forwards
the descriptor instead of parsing referenced PromQL).

### Gaps to close before it's more than a spike

- **G1 — Cross-language extraction is the long pole.** Regex is fine for Python;
  Go and Node want real ASTs (`go/parser`, a TS/JS parser) to fix the broad
  `Name:`/`name:` precision hole and to resolve simple constant/concat names. Java
  (real adservice/currencyservice/frauddetectionservice) and C#/Rust are entirely
  unsupported and are a meaningful fraction of Online Boutique.
- **G2 — Collector-produced metrics.** The span-metrics-connector RED surface
  (`calls_total`, `duration_milliseconds`) is emitted by the *collector*, not the
  service. A pure source scan can't see it. Production must fold in the **onboarding
  metadata / manifest** the generator already consumed (`extract_service_hints` →
  the resolved `MetricDescriptor`): if the target's profile is
  `span-metrics-connector`, add its signature metrics to the emitted set. This makes
  the emitted side *manifest-aware*, closing the paymentservice-style false negative
  and unifying with the descriptor the generator used.
- **G3 — Wrapper / indirection resolution.** Recognize a small allowlist of common
  metric-helper wrappers; otherwise accept the documented false-negative.
- **G4 — Verdict policy.** Decide the report schema and where it lands (a
  `observability-fidelity-static.json` beside `observability-quality.json`, one entry
  per service). Keep it reported-not-scored.
- **G5 — Confidence tagging.** Emit per-service extraction confidence (which
  languages seen, whether transport was sniffed vs. explicit, whether any
  family-only matches carried the coverage) so a low number can be triaged as
  "real gap" vs. "extractor blind spot."

### Recommended path

1. **Ship as reported-not-scored now** (Python-only + transport implication +
   manifest-descriptor fold-in for G2). Already high-value on Python/Go services.
2. **Add the manifest/descriptor emitted-side (G2)** — biggest accuracy win for the
   least code, and reuses `metric_descriptor.resolve_descriptor` the generator
   already runs. This alone flips the span-metrics false negatives to true binds.
3. **Replace Go/Node regex with ASTs (G1)** when those languages matter for the
   target suite; add Java last (largest lift, needed for full Online Boutique).
4. **Only then** consider promoting from reported → gated, and only as a *cheap
   pre-filter* in front of the live `validate_promql` replay — never as a
   replacement for it.

---

## 6. Feasibility verdict per language

| Language | Verdict | Rationale |
|---|---|---|
| **Python** | **Feasible now** | High precision + recall on literal names; transport implication solid. Ship. |
| **Go** | **Feasible with caveats** | Works via regex; precision hole on broad `Name:`. Wants `go/parser` for production. |
| **Node/TS** | **Feasible with caveats** | Same as Go. |
| **Java / C# / Rust** | **Not yet** | Unsupported; needed for full Online Boutique coverage (real adservice is Java). |
| **Auto-instrumented (any lang)** | **Feasible via transport + manifest** | The emitted RED surface must come from transport implication + the onboarding descriptor, not source constructors. This is the correct primary path, not a fallback. |
