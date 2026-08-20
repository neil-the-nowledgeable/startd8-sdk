# Observability fidelity findings — generator gaps surfaced by the canonical fidelity gate

**Date:** 2026-08-19
**Surfaced by:** running the canonical fidelity gate against a live **OTel Astronomy Shop 3.0** target
(the standard OpenTelemetry demo app) instrumented with ContextCore-generated observability
(SLOs/alerts/dashboards) + live Prometheus, and importing the generated dashboards into a
**Perses-native** backend.
**Target:** `startd8-sdk` — `src/startd8/observability/*` (generator + the `metricsProfile` binding path).
**Method:** strictly by the book per `docs/CI_FIDELITY_GATE.md` (canonical
`startd8 observability validate-promql`, not an ad-hoc validator).

---

## BLUF
The canonical fidelity gate surfaced **one real generator defect** (Finding A) plus **dashboard-generation
gaps for Perses-native backends** (Finding D — a real defect + nice-to-haves), a `metricsProfile`
nice-to-have (Finding B), and a consumer-process note (Finding C).

Finding A: the generated `http_server_{request,response}_body_size` histogram queries **omit the `_bytes`
UCUM unit suffix** the OTel→Prometheus exporter appends. The queries reference
`http_server_request_body_size_bucket`; the live series is `http_server_request_body_size_**bytes**_bucket`.
Result: 26 queries fail to bind, `binding_coverage` **0.86** (below the 0.90 floor). A one-line name-remap
fixes it and lifts `binding_coverage` to **1.0** — proving the diagnosis and giving the exact SDK fix.

---

## Finding A — `http.server.*.body.size` omits the `_bytes` unit suffix  ★ real defect

**Symptom.** `validate-promql` (min-coverage 0.9) → gate FAIL:

| | before |
|---|---|
| binding_coverage | **0.86** (floor 0.90 → exit 2) |
| verdicts | pass 89 · bound_no_data 71 · **fail 26** |
| the 26 fails | 13 × `http_server_request_body_size` + 13 × `http_server_response_body_size` |

**The tool's own remediation string (verbatim):**
> *expr family 'http_server_request_body_size' is absent as an exact `__name__` but native-histogram
> children (`{fam}_bucket/_count/_sum`) are live — emit `histogram_quantile`/`rate` on the children.*

**Root cause (grounded against live `__name__`).** The generator emits the un-suffixed base name.
The OTel Collector's Prometheus exporter appends the UCUM unit (`By` → `_bytes`) to the metric name:

```
generated query : histogram_quantile(0.99, rate(http_server_request_body_size_bucket{…}))   → 0 series
live series     : http_server_request_body_size_bytes_bucket / _count / _sum                 → 48 series
```

So the histogram basename is correct except for the missing `_bytes` unit segment. (Note: this is why
a naive `coverage classify-uncovered` reports `substrate_absent` for `http.server.request.body.size` —
it probes the un-suffixed name; the metric **is** emitted, under the `_bytes` name.)

**Suggested SDK fix.** When lowering a UCUM-`By` metric to a Prometheus name, include the unit suffix
(`…_body_size` → `…_body_size_bytes`) for the `_bucket/_count/_sum` family — matching the collector's
Prometheus exporter naming. Applies to any `.body.size` / byte-unit convention metric, not just these two.

**Consumer-side proof (stopgap).** A single consumer-side remap rule
(`http_server_(request|response)_body_size_(bucket|count|sum)` → `…_body_size_bytes_\2`) regenerated and
re-gated to:

| | after |
|---|---|
| binding_coverage | **1.0** (exit 0, PASS) |
| verdicts | pass 114 · bound_no_data 72 · **fail 0** |

---

## Finding B — no built-in `metricsProfile` matches the target's prefixed span-metrics  (nice-to-have)

`startd8 observability detect-profile` against the live backend → **`no-match`** (463 metric names).
The built-in `span-metrics-connector` profile signature expects **bare** `calls_total` /
`duration_milliseconds_bucket`, but this stack's span-metrics connector emits them **namespaced**:
`traces_span_metrics_calls_total` / `traces_span_metrics_duration_milliseconds_bucket` (both live).

The generator emits the connector *default* (bare) names; the target namespaces them via a `retarget`
rule. **Nice-to-have:** either ship a `span-metrics-connector-prometheus` profile variant that encodes
the `traces_span_metrics_` namespace, or have `detect-profile` suggest a per-axis
`spec.targets[].metrics` override when it detects the prefixed family. Not blocking (the consumer
override works), but it would remove a manual step for any target with a namespaced span-metrics connector.

---

## Finding C — process note for consumers (not an SDK bug)

A consumer shipped its own ad-hoc `validate_promql.py`, which counts any 0-series query as a failure. Run
against the rendered artifacts it reported **266 "EMPTY"** — conflating genuine binding failures with
`bound_no_data` (correct-but-idle queries) and Grafana `$__rate_interval` macros. The canonical
`validate-promql` (which separates `binding_coverage` from `data_coverage` and re-probes idle queries at
`--bind-window`) showed the true failure was **26**, all one root cause. Lesson worth surfacing in
consumer docs: **gate on `binding_coverage` via the canonical tool; ad-hoc 0-series counting over-reports
and misattributes.**

---

## Finding D — dashboard generation: Grafana-only output blocks Perses-native backends

Importing the generated Grafana-JSON dashboards into a **Perses-native** backend surfaced three generator
gaps. (Such backends auto-convert Grafana→Perses on upload, but the conversion is lossy and the generated
JSON needs consumer-side rewriting to be usable.) This directly motivates the Perses vendor-neutrality work
— see `docs/design/dashboard-vendor-neutrality/ADR_adopt-perses-neutral-dashboard-ir.md`.

**D1 — `histogram` panel type doesn't convert (real defect).** The generator emits Grafana
`"type": "histogram"` for the `histogram_quantile(…)` panels (latency p99, request/response body size).
Perses has no `histogram` viz → **every one fails**: *"Failed to convert this Grafana panel"* — **39 panels
across 14 dashboards.** But those queries return a single percentile **line over time**, so the correct viz
is `timeseries` (which converts + renders). **Suggested fix:** emit `timeseries` (not `histogram`) for
`histogram_quantile` panels. *Consumer stopgap:* `"type":"histogram"`→`"type":"timeseries"` rewrite →
39→0 failed conversions.

**D2 — Grafana render-macros leak into portable output.** Panels use `$__rate_interval`, which only Grafana
resolves; in a Perses import it stays literal → `rate()`/`histogram_quantile()` bind to a bad window →
**"No data."** *Consumer stopgap:* `$__rate_interval`→`5m`. **Suggested fix:** parameterize the rate window
(a dashboard variable / concrete default) rather than emitting a Grafana-only macro.

**D3 — no Perses backend profile (nice-to-have).** The generator only emits Grafana JSON; there is no Perses
output. Every Perses-native backend therefore inherits D1/D2 plus the `${datasource}` variable.
**Suggested fix:** a `perses` output profile (parallel to the existing backend profiles) would make
Perses-native backends first-class and remove the whole retarget layer — the concrete realization of the
Perses-IR ADR above.

> Consumer-side, all three are handled by a retarget step (4 rules total). Result: 14/14 dashboards,
> 0 failed-convert panels, SLIs populated.

---

## Repro (by the book)
```bash
# live OTel Astronomy Shop 3.0 + Prometheus up; artifacts generated to out/observability
startd8 observability validate-promql \
  --artifacts-dir out/observability \
  --onboarding-metadata out/onboarding-metadata.json \
  --prometheus http://localhost:9090 --min-coverage 0.9
# before Finding-A fix: binding_coverage 0.86 (exit 2); after: 1.0 (exit 0)
startd8 observability detect-profile --prometheus http://localhost:9090   # → no-match (Finding B)
```
