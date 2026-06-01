# Observability Artifact Generator — Naming-Strategy Fix Requirements

**Date:** 2026-06-01
**Status:** Bug / fix-requirements draft (for a later fix pass — not yet implemented)
**Component:** `src/startd8/observability/artifact_generator*.py` (+ upstream `instrumentation_hints` producer)
**Trigger:** the generated `strtd8` dashboard (`uid obs-strtd8`) returns **No Data** even with a healthy
Mimir, because every panel's PromQL name/selector mismatches the metrics the SDK actually emits.

> Companion docs: `OBSERVABILITY_PIPELINE_LIVE_STATUS_2026-06-01.md` (pipeline status),
> `~/Documents/tools/localhost_tools/local_grafana/INCIDENT_2026-06-01_mimir-crashloop-peas-ruler.md`
> (the Mimir outage that masked this — a *separate* root cause, now fixed).

---

## 1. Evidence — what the generator emitted vs. what Mimir actually has

Generated queries (run-009) all take the form `…{service="strtd8"}` over assumed metric names.
Ground truth probed from Mimir (tenant `anonymous`):

| # | Generator emitted | Reality in Mimir | Result |
|---|---|---|---|
| A | selector `service="strtd8"` | series carry `service="startd8-sdk"` (also `job="startd8-sdk"`); `service_name` label does **not** exist | matches 0 series |
| B | `http_server_duration_bucket`, `http_server_request_body_size_bucket`, … (RED triplet) | startd8-sdk is **not an HTTP server** — no `http_server_*` series exist for it | panels inapplicable |
| C | `startd8_cost_total`, `startd8_response_time_ms`, `startd8_truncations_total` | actual: `startd8_cost_USD_total`, `startd8_response_time_ms_milliseconds_{bucket,count,sum}`, `startd8_truncations_events_total` | matches 0 series |

Real emitted `startd8_*` names + identifying labels (for reference):
```
startd8_active_sessions, startd8_context_usage_ratio,
startd8_cost_USD_total, startd8_cost_input_tokens_total, startd8_cost_output_tokens_total,
startd8_cost_per_request_USD_{bucket,count,sum},
startd8_events_total, startd8_requests_total,
startd8_response_time_ms_milliseconds_{bucket,count,sum},
startd8_tokens_total, startd8_truncations_events_total
labels: agent_name, model, provider, project, session_id, status, direction, le ; job/service="startd8-sdk"
```

## 2. Root cause (one sentence)

The generator **guesses** PromQL by string-templating metric names and by using the
`instrumentation_hints` **key** (= project/run id `strtd8`) as the `service` label value, instead of
**deriving** names and selectors from the SDK's real OTel descriptors and the actual emitted
`service.name` — and the quality scorer never checks that the queries resolve.

## 3. Defects + fix requirements

### FIX-1 — service selector VALUE must be the runtime `service.name`, not the project/hint key
- **Where:** `artifact_generator_context.py:_extract` keys `ServiceHints.service_id` off the
  `instrumentation_hints` dict key (`svc_id` = `strtd8`); every PromQL template then embeds
  `service="{service_id}"` (`artifact_generator_generators.py` lines 56/58/192/228/264/412 and
  `_domain_query` line ~571).
- **Required:** the selector value MUST be the OTel `service.name` resource attribute as actually
  exported (`startd8-sdk`), not the project/run id. Options (pick one, in preference order):
  1. carry `service.name` explicitly in each `instrumentation_hints[svc]` (distinct from the map key),
  2. derive it from the SDK's OTel resource config (single source of truth),
  3. probe the datasource label values and reconcile (last-resort, see FIX-5).

### FIX-2 — do not hard-code the identifying label KEY `service`
- **Where:** `_INSTRUMENT_TO_QUERY` and `_domain_query` hard-code `{service="…"}`.
- **Required:** the identifying-label key MUST be resolved from the OTLP→Prometheus pipeline
  convention (Alloy/OTel Collector), not assumed. Real pipelines variously expose `service`, `job`,
  `service_name`, or `exported_job`. Make the label key a parameter derived from the manifest/collector
  config (here `service`/`job` both work; in general it varies). Brittle hard-coding happened to be
  half-right this time only by luck.

### FIX-3 — apply the OTel→Prometheus name transform (unit + type suffixing); stop assuming declared names are final
- **Where:** `_INSTRUMENT_TO_QUERY` appends only `_bucket`/`_total`; `_domain_query` docstring
  *asserts* "Declared metric names are already Prometheus-style" and appends only `_total` — **false**.
- **Reality (the transform that actually happens):** dots→underscores, **instrument unit inserted**
  before the type suffix, then the type suffix:
  - counter `startd8.cost.total` unit `USD` → `startd8_cost_USD_total`
  - histogram `startd8.response_time_ms` unit `milliseconds` → `startd8_response_time_ms_milliseconds_{bucket,count,sum}`
  - counter `startd8.truncations` unit `events` → `startd8_truncations_events_total`
  - gauge `startd8.context_usage_ratio` (no unit) → `startd8_context_usage_ratio`
- **Required:** implement the deterministic OTel→Prometheus naming function (units + `_total` for
  monotonic counters + `_bucket/_count/_sum` for histograms + no suffix for gauges) and apply it to the
  **declared descriptors**. Strongly prefer **reusing the exact same function the SDK's OTel
  exporter/Alloy uses**, so generated names match emitted names *by construction* rather than by a
  parallel re-implementation that can drift.

### FIX-4 — convention/RED panels must be evidence-based, not transport-assumed
- **Where:** `artifact_generator_context.py:300` reads `hint.transport`; `transport="http"` →
  `convention_based` RED metrics (`http_server_*`). For `strtd8` the hint said `http`, but the SDK
  emits no HTTP-server metrics.
- **Required:** only emit RED/HTTP panels when the service actually emits those series (verify against
  declared descriptors and/or a live probe). For SDK/library/agent services, emit the **domain panels**
  from `manifest_declared` (cost, sessions, tokens, latency, truncations) instead of a generic HTTP
  template. Transport/shape MUST be detected from evidence, not defaulted.

### FIX-5 — quality scoring must verify selectors RESOLVE, not just that JSON is structurally valid
- **Where:** the run-009 manifest reported `artifact_type_coverage: 1.0` and per-artifact
  `quality_score: 1.0` for a dashboard whose every query matches **zero** series.
- **Required:** add a resolvability gate to scoring: each generated selector MUST be checkable against
  (a) the declared descriptor names/label keys (offline), and (b) optionally live datasource
  label/metric values (online, when a datasource is reachable). A dashboard whose queries cannot match
  anything MUST be scored down / flagged, never 1.0. ("Declare-don't-guess" applies to *validation* too.)

## 4. Recommended naming strategy (the durable fix)

**Derive, don't guess — from a single shared naming source.**
1. Treat the SDK's OTel **descriptors** (`_OTEL_DESCRIPTORS` → `generate_manifest()` → `manifest_declared`)
   as the source of truth for metric identity: `name`, `instrument_type`, `unit`, label keys.
2. Have **one** OTel→Prometheus naming function (the exporter's) that both the runtime exporter and the
   generator call. Generated names then equal emitted names by construction.
3. Resolve the identifying label key + service value from the actual OTel resource/collector config, not
   from the project id.
4. Gate panel *shape* (RED vs domain) on emitted descriptors, not assumed transport.
5. Validate selectors resolve before reporting coverage/quality.

## 5. Upstream data fixes (the `instrumentation_hints` producer — ContextCore onboarding)

The same defects partly originate upstream and should be fixed where the hints are produced:
- The hint **key** is the project id (`strtd8`), not the emitted `service.name` (`startd8-sdk`) → FIX-1.
- `transport: http` was set for a non-HTTP SDK → FIX-4.
- `manifest_declared` carried **non-final** names (no unit infix) → FIX-3. The producer should carry
  either the final Prometheus names or full descriptors (name + instrument type + unit) so the
  generator can derive them deterministically.

## 6. Acceptance criteria (for the eventual fix)
1. For the startd8-sdk service, generated selectors use `service="startd8-sdk"` (or the resolved
   identifying label) and the real exported metric names — and the provisioned dashboard shows data.
2. No `http_server_*` RED panels are generated for services that don't emit them.
3. Generated metric names are produced by the shared OTel→Prometheus transform; a unit-test asserts a
   round-trip (descriptor → exporter name == descriptor → generator name) for cost/latency/truncation/gauge.
4. A dashboard whose queries resolve to zero series is flagged by the quality scorer (no false 1.0).
5. Regression test fixture: the run-009 `strtd8` onboarding metadata → dashboard whose selectors match
   the emitted-series fixture.
