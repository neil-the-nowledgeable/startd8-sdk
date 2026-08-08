# Generality Survivorship-Audit — SDK observability generator, ahead of Istio (Pilot 3)

**Method:** [`/generality-survivorship-audit`](../../../.claude/skills/generality-survivorship-audit) —
predict-then-verify which "generic" mechanisms are secretly bound to the corpus's hidden homogeneity,
before the next input flies. **Subject:** the startd8 SDK *observability generation* pipeline (consumes
onboarding-metadata → emits SLOs/alerts/dashboards). **Incoming input:** RepoProbe Pilot 3 — **Istio**
(Go/Envoy service mesh: `istio_*`/`envoy_*` metrics in **milliseconds**, sidecar-per-workload topology,
`response_code`/`response_flags` error taxonomy). **Date:** 2026-08-08.

> This audits the SDK *generator* (the artifact-emitting half), not the RepoProbe *extractor* (the
> source-reading half, ContextCore-side) — the extractor's Go/Envoy blindness is a separate audit
> (`ContextCore/docs/design/o11y-sapper/GENERALITY_SURVIVORSHIP_AUDIT.md`).

## 1. Axes of input variation (for the *generator*)

The generator reads metadata, not source — so its axes are about the **metadata/metric shape**, not the
subject's language:

| Axis | What varies |
|---|---|
| **Metric UNIT** | seconds vs **milliseconds** vs bytes/ratio |
| Metric-name idiom | `http.server.duration` (semconv) vs `grpc_server_handled_total` vs `istio_requests_total` |
| Error taxonomy | HTTP `5xx` vs gRPC `grpc_code` vs Istio `response_code` vs Envoy `response_flags` |
| Transport/kind | http/grpc/worker/batch/cron/stream/ml_inference |
| Topology shape | single service vs **sidecar-per-workload + control plane** |
| Label schema | `service` vs `job`/`grpc_service` vs `source_/destination_workload` + `reporter` |

## 2. Coverage matrix (corpus × axis) — the homogeneity tell

| Input | Unit | Idiom | Error | Kind | Topology | Labels |
|---|---|---|---|---|---|---|
| Online Boutique | **s** | semconv | 5xx / grpc | http/grpc | single | service |
| Mastodon | **s** | semconv/exporter | 5xx | http/worker | single | job/service |
| Harbor | **s** | exporter | 5xx | http (+DB) | single | job |
| Thanos | **s** | exporter | grpc_code | grpc/batch | single | grpc_service |
| **Istio (incoming)** | **ms** | `istio_*`/`envoy_*` | response_code/**response_flags** | http (mesh) | **sidecar+mesh** | **source/destination_workload,reporter** |

**Blind (all-one-value) axes:** **UNIT (all seconds)** and **TOPOLOGY (no sidecar/mesh)**. These are
where input-specific code passes as generic — Istio is the first input to diverge on both.

## 3. Findings (predict → verify → earn-it)

### 🔴 F1 — Declared-series latency target is **unit-blind** *(verified defect; the corpus masks it)*
The **declared-Prometheus-series** latency SLO does not scale its default threshold by the series' unit.
Verified in isolation (`generate_observability_artifacts` on a one-service fixture):

| Declared latency series | Emitted `target:` | Correct? |
|---|---|---|
| `http_request_duration_seconds` (seconds) | **`500`** | ❌ means "p99 ≤ **500 seconds**" — 1000× too loose |
| `istio_request_duration_milliseconds` (ms) | **`500`** | ✅ "p99 ≤ 500ms" |

The **convention** path *does* scale (`MetricDescriptor.latency_unit` + `scale_threshold_seconds`; the
Tempo span path renders `target: 0.5` — asserted in `test_grpc_thanos_idiom_roundtrip.py`). The
declared path does **not** — it emits the raw `latency_p99` default (500). So the all-**seconds** corpus
has been getting **1000×-too-loose** declared-latency SLOs, unnoticed because no one validated the
numeric target against real telemetry — and **Istio's milliseconds would be the first input where the
unit-blind default is coincidentally *right*.** Classic survivorship: the mechanism "worked" on every
input only because none exercised the unit axis.
- **Caveat (verify before fixing):** this bites only when the author declares a latency series *without*
  an explicit `target`. If the pilots always author `target: "500ms"`, the default never fires — confirm
  against the real plans first.
- **Armor:** on the declared-latency path, infer the unit from the series **name** (reuse `_metric_unit`,
  which already recognizes `*_seconds`/`*_milliseconds`) and `scale_threshold_seconds` before emitting —
  exactly what the convention path does. *(A behaviour change to existing seconds subjects' targets, so
  it warrants its own reflective-requirements + review, not a silent audit-time edit.)*

### 🟠 F2 — Convention metric-name idiom is HTTP/semconv-bound *(known; Istio makes it concrete)*
A convention-only service (no declared series) binds latency/throughput to `http_server_duration` /
`rpc_server_duration` (`metric_descriptor.py:147-187`). Istio workloads emit `istio_requests_total` /
`istio_request_duration_milliseconds` — **not** the semconv names — so a convention-only Istio service
yields **dead SLIs**. **Mitigated:** the `declared_emitted_series` path (#286) + `service_name` (#39) let
an author bind the real `istio_*` series (as Thanos did for `grpc_*`), and the #274 emission-surface
suppression records the gap instead of shipping a dead HTTP SLI. So the fix already exists — it just
requires the pilot's plan to **declare** the `istio_*` series (an authoring obligation, not an SDK gap).

### 🟡 F3 — Error taxonomy is **largely armored** *(earn-it: not filed)*
`affordance_map_consume.py` already recognizes Istio's **label-encoded** error selector
(`response_code=~"5.."`, `_label_encoded_error_selector` / `red_taxonomy.ERR_CODE_FILTER_RE`), and
`error_selector` is **opaque** (raw PromQL — the matcher-key de-dup even survives gRPC alternation, per
#361). Envoy **`response_flags`** mesh-level failures (`UH`/`UF`/`NR`/`UO`) have no dedicated template,
but the `custom` signal_kind + author PromQL covers them. **No gap filed** — the common Istio error idiom
is handled.

### 🟡 F4 — Sidecar/reporter topology *(partly generic)*
Istio metrics are reported by the Envoy **sidecar** with `source_workload`/`destination_workload` +
`reporter` (source vs destination) labels — a shape absent from the corpus. The **convention**
`service_matcher` emits `{service="X"}`, which won't match `{destination_workload="X",reporter="destination"}`.
**Mitigated** by author-declared labels (the declared-series selector binds where the series *actually*
lives) + `service_name`. **Risk:** double-counting if both `reporter="source"` and `reporter="destination"`
series match a selector that omits `reporter` — an authoring pitfall worth a plan note, not an SDK defect.

## 4. Verdict & armor priority

| # | Finding | Status | Action |
|---|---|---|---|
| F1 | declared-latency unit-blind | **RESOLVED** — spec'd (#422) + fixed (#424) | scaled via `_metric_unit` (now ms-aware) + shared `scale_seconds_to_unit`; live-verified on Harbor (`500ms` string → `0.5` numeric). Liveness-attribution follow-on = contextcore#406. |
| F2 | convention idiom HTTP-bound | known, mitigated | ensure the Istio plan **declares** `istio_*` series (authoring) |
| F3 | error taxonomy | armored | — (Envoy `response_flags` → `custom` path) |
| F4 | sidecar/reporter labels | mitigated | plan note: pin `reporter` in the declared selector |

> **Update (2026-08-08):** F1 is **resolved** — spec `REQ-declared-latency-unit-scaling.md` (#422) →
> fix #424 (`_metric_unit` learns ms; declared path scales via the single-sourced `scale_seconds_to_unit`;
> live-verified that real Harbor no longer ships the `500ms` string). A generation-layer finding whose
> *liveness* attribution (is an unbound SLI a code gap or a load gap?) is the contextcore#406 follow-on.

**Bottom line:** the generator is far more Istio-ready than a naive audit would guess — units are scaled
on the convention/span paths, the Istio error idiom is already recognized, and the declared-series path
is metric-name/label agnostic. The **one genuine, verified defect** was F1 (declared-latency unit
blindness), which — because the whole corpus is seconds — had been silently producing too-loose SLOs and
would only *look* correct once Istio's milliseconds arrive. That is exactly the failure class this audit
exists to catch: a mechanism that survived every input because every input shared its hidden assumption.
