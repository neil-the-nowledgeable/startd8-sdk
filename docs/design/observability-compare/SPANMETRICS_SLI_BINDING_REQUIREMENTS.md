# Span-Metrics SLI Binding (declared trace surface → bind SLIs with `service.name`) — Requirements

**Version:** 0.3.1 (post planning + lessons + design-principle hardening; ready for CRP)
**Date:** 2026-07-23
**Status:** Draft — spec only, no code
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** startd8-sdk **#307** (Part B) · pairs with ContextCore **#58** / REQ-CCL-109 (Part A, the carry)
**Refs:** #286/#300 (declared-emitted-series binding — the Prometheus-surface sibling), #275/#276 (real
`service.name`), option-b1 (`OSS/mastodon/analysis/option-b1-spanmetrics-capability-ask.md`)

---

## 0. Planning Insights (Self-Reflective Update)

> What the planning pass (reading `metric_descriptor.py`, the declared-series generators, and the
> `metrics_surface` enum owner) corrected from the naïve v0.1 "add a span-metrics binder" draft.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| The series is `traces_spanmetrics_latency_seconds_bucket{service_name, span_name}` (verbatim from the issue) and we hardcode it. | A **`span-metrics-connector` MetricDescriptor already exists** (`metric_descriptor.py:144`) — but with the **OTel Collector spanmetrics** names (`calls_total`, `duration_milliseconds_bucket`, `service_name`), NOT the **Grafana Tempo metrics-generator** names the issue cites (`traces_spanmetrics_*_seconds`). Two real conventions, different names. | **Single-source the series names via a descriptor profile (FR-3), never hardcode.** Resolve which convention Mastodon's surface emits (OQ-1) — the acceptance says *Tempo metrics-generator*, so a `tempo-spanmetrics` profile is added rather than overloading the existing OTel-connector one. |
| The service label needs new plumbing. | `MetricDescriptor.service_label_key` (`service` vs `service_name`) + `service_matcher` already exist and are live (`generators.py:2003`, the notification-policy path). The #275 real `service.name` already reaches selectors via `getattr(service, "service_name", ...)`. | **Reuse the descriptor selector machinery + `service_name` (FR-4); no new label plumbing.** This is where the #275 fix first reaches an *SLO* selector. |
| A whole new binder subsystem. | `generate_declared_functional_slos` (#300 D2) + `DeclaredEmittedSeries` are the **exact template**: per-`(series,covered-kind)` candidacy, precedence declared>suppress>convention, threshold-deferred when no target, a separate `{svc}-declared-*-slo.yaml` lane, `bound_declared_*` accounting. | **Mirror it: a `DeclaredSpanSignal` model + `generate_declared_span_slos` generator** shaped like D2, not a greenfield design. Reuse `_functional_sli_query`, `_resolve_threshold`, the `_series_slug` naming, the deferred-gap reason_code discipline. |
| `metrics_surface: spanmetrics` is just another non-emitting surface. | `spanmetrics` is **not in the enum** (`NON_EMITTING_CONVENTION_SURFACES = {traces_only,none,prometheus_exporter,node_metrics}`). It *doesn't* emit the convention meter metric (so base RED still suppresses), but it *does* emit span-derived RED — a **new dual nature**. | Add `spanmetrics` to `NON_EMITTING_CONVENTION_SURFACES` (base RED still dead) **and** treat it as the trigger surface for span-binding (FR-1). The span binding is what re-grounds RED — same precedence shape as #286. |
| ContextCore generates the connector; #307 binds. | Per REQ-CCL-109 planning, the connector generator is **startd8-owned** (collector_enrichment precedent), but the ContextCore spec explicitly does **not** implement it. The issue #307's *stated* ask is the **binding**. | **Scope #307 to the binding (FR-4-equivalent).** Connector-config generation is a separate startd8 capability → NR-1 (pointer, not built here). |

**Resolved open questions:**
- **OQ-a (series names) → a descriptor profile, resolving to the Tempo metrics-generator convention** (the acceptance's validation surface); reconcile with the existing OTel-connector profile rather than hardcoding (FR-3, OQ-1 tracks the cross-repo confirmation).
- **OQ-b (surface interaction) → `spanmetrics` suppresses base convention RED AND triggers span binding** (dual nature; FR-1).
- **OQ-c (shape reuse) → mirror the #300 D2 binder** (`DeclaredSpanSignal` + `generate_declared_span_slos`); no new subsystem.
- **OQ-d (connector generation) → out of scope for #307** (separate startd8 ask; NR-1).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK + this-session lessons before CRP:

- **Phantom-reference audit** — verified against the merged tree: `span-metrics-connector` descriptor
  (`metric_descriptor.py:144`), `service_label_key`/`service_matcher` (`:52`/`:94`), `_functional_sli_query`,
  `_resolve_threshold`, `_series_slug`, `NON_EMITTING_CONVENTION_SURFACES` (`:220`), `ServiceHints.service_name`
  (#275). Added §9 Reference Audit.
- **Single-source vocabulary ownership** — the span-metrics **series names/labels** are owned by a
  `MetricDescriptor` profile (not restated in the binder); the `metrics_surface` **enum** is startd8-owned
  (REQ-CCL-106 discipline — ContextCore carries the value verbatim, the SDK blesses it).
- **[preserve-declared-intent-consumer-decides]** (the #300-D covers-filter regression) — the parser SHALL
  carry the author's full `covers` + verbatim `error_selector` **unfiltered**; the binder decides what binds
  (mirrors the #300 D2 fix — no producer-side subsetting).
- **[verify-consumer-against-merged-diff]** — the Tempo series names + the `spanmetrics` enum value are
  marked PENDING confirmation against a real Tempo metrics-generator surface via `compare-live` (§5/OQ-1).

### 0.2 Design-Principle Hardening (v0.3.1)

- **Genchi Genbutsu** — bind to the **real** emitted span-metrics series with the **real** `service.name`
  (#275), not a convention proxy; respect the enum boundary (SDK owns the values). One canonical field name
  `declared_span_signals` (not generic `spans`/`signals`).
- **Mottainai** — reuse the existing descriptor selector machinery, `_functional_sli_query`, and the D2
  binder shape; do not rebuild a parallel span binder or a second service-label mechanism.
- **Hitsuzen (derive the determinable)** — `span_name`/`covers`/`error_selector`/`target` are author-declared;
  the *query* is deterministic from them + the descriptor; nothing is LLM-generated.
- **Accidental-Complexity anti-principle** — do NOT add a second hardcoded series-name convention; a single
  descriptor profile carries the names so the OTel-connector vs Tempo-generator split can't scatter.

---

## 1. Problem Statement

#286/#300 bound SLIs to an author-declared **Prometheus** surface. But a traces-only subject's real signals
aren't in Prometheus:

- Mastodon's Prometheus surface is opt-in, web-biased, and labels by `type=puma`/`job_name` — **not
  `service.name`** — so the #275/#276 `service.name` fix never reaches an SLO selector on that path.
- The async fan-out functional signals — **FR-002 enqueue**, per-worker **FR-003/004/005** — live in
  **traces**, not Prometheus.

Mastodon auto-instruments the whole fan-out (Sidekiq spans named by worker class;
`service.name = mastodon/web|sidekiq`). A **span-metrics connector** (OTel Collector `spanmetrics` / Tempo
metrics-generator) turns those spans into RED metrics **carrying `service.name`**. **The gap:** the SDK has
a `span-metrics-connector` *descriptor* but no way to declare a span surface or bind per-span SLIs to
`traces_spanmetrics_*{service_name, span_name}`. #307 is the SDK binding half (ContextCore #58 carries it).

## 2. Requirements

**FR-1 — Recognize the `spanmetrics` surface.** Add `spanmetrics` to the `metrics_surface` enum
(startd8-owned). It is added to `NON_EMITTING_CONVENTION_SURFACES` (the OTel-convention meter metric is still
absent → base RED SLIs suppress as today) **and** is the trigger that activates span-signal binding (FR-4).

**FR-2 — Carry & parse `declared_span_signals`.** Parse `instrumentation_hints[svc].metrics.declared_span_signals`
(carried by ContextCore REQ-CCL-109) into a new `DeclaredSpanSignal` model:
`{span_name, attributes: Dict[str,str] = {}, covers: List[str], error_selector: str = "", target: Optional[str] = None, enabling_flag: str = ""}` — the span analogue of `DeclaredEmittedSeries`. Parse discipline mirrors
`_parse_declared_series`: explicit-only, absent→omitted (byte-identical), `covers`/`error_selector` **unfiltered**,
`target` read as `.get("target")`→`None` (not `""`).

**FR-3 — Single-source the span-metrics series names via a descriptor profile.** The bound PromQL series
names/labels come from a `MetricDescriptor` profile, not hardcoded. Add a `tempo-spanmetrics` profile
(`traces_spanmetrics_latency_seconds_bucket`, `traces_spanmetrics_calls_total`, the errors dimension,
`service_label_key="service_name"`) resolving the issue's acceptance convention, coexisting with the existing
`span-metrics-connector` (OTel-Collector) profile. The binder selects the profile; the two conventions never
scatter into the binder body.

**FR-4 — Bind per-span SLIs with the real `service.name`.** For each `(span signal, covered-kind)`, bind an
SLI on `<latency_bucket>{service_name="<real>", span_name="<declared>"[, <attributes>]}` (and the
calls/errors counters for throughput/availability), where `<real>` is `service.service_name` (#275). Same
precedence as #286: **declared span-signal > suppress convention > convention**. Query shape reuses
`_functional_sli_query`/the base RED shapes; latency = p99 on the `_bucket`, throughput = rate on calls,
availability = errors/calls ratio (needs `error_selector`, else deferred — mirrors #286 v2).

**FR-5 — Threshold discipline (reuse #300 D2).** Base RED kinds resolve the threshold from the manifest/
importance default (as #286). A functional kind (saturation/…) with no `target` on the span signal is
**threshold-deferred** with its grounded query in `deferred_declared_kinds` (identical to #300 D2/FR-4). The
SDK never invents a threshold (NR — Genchi Genbutsu).

**FR-6 — Separate emission lane + accounting.** Emit into `{svc}-declared-span-slo.yaml` (a peer of the
declared-base/-functional lanes). Add `bound_declared_span` to `fr_coverage` (only when non-empty, byte-
identity per #300 FR-9); deferred/mismatch cases feed `deferred_declared_kinds` with a reason_code.

**FR-7 — `compare.py` consumer contract.** `build_comparison_report`/`render_report`/`_entry_line` surface
`bound_declared_span` and any threshold-deferred query (mirrors the #300 D2 FR-10 fix — a new key is dead
unless compare consumes it).

**FR-8 — Byte-identical when absent.** No `declared_span_signals` ⇒ no span lane file, no
`bound_declared_span` key, no behavior change (additive only).

## 3. Non-Requirements

**NR-1 — Do NOT generate the `spanmetrics` connector config.** That (option-b1 Part A / REQ-CCL-109 FR-3) is
a separate startd8 capability (an OTel Collector artifact type, collector_enrichment precedent). #307 binds
SLIs to a span-metrics surface **assumed to exist** (a Tempo metrics-generator or Collector connector). Pointer
only.

**NR-2 — No fabricated thresholds** (inherits #300 NR-1).

**NR-3 — Base RED convention path unchanged** for non-spanmetrics surfaces.

**NR-4 — FR-007 freshness is out of scope** — it is cross-trace (span link, `propagation_style: :link`) and a
span-metrics connector can't produce it. That is option-b2 / #308 (the synthetic-probe SLI type).

## 4. Open Questions

- **OQ-1 (cross-repo, PENDING) — the exact Tempo series names/labels.** Confirm against a real Tempo
  metrics-generator surface (or OTel-demo) via `compare-live` before declaring bound: is it
  `traces_spanmetrics_latency_seconds_bucket` + `traces_spanmetrics_calls_total`, and is the label
  `service_name` (vs `service`)? FR-3's profile encodes the answer; do not ship unverified.
- **OQ-2 — `attributes` in the selector.** A span signal may declare extra span attributes (e.g.
  `messaging.destination`) — bind them into the selector, or ignore for v1 (span_name + service_name only)?
  Lean: carry them, render only non-empty (mirrors the #300-A empty-label discipline).
- **OQ-3 — availability from span-metrics.** The errors dimension is `status_code`/`span.status` on
  `calls_total` — is the `error_selector` a `status_code=~"..."` fragment? Confirm the Tempo convention.

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `span-metrics-connector` descriptor (OTel names) | `metric_descriptor.py:144` | ✅ (add a `tempo-spanmetrics` peer) |
| `service_label_key` / `service_matcher` / `selector` | `metric_descriptor.py:52/94/99` | ✅ |
| `NON_EMITTING_CONVENTION_SURFACES` (add `spanmetrics`) | `metric_descriptor.py:220` | ✅ |
| `ServiceHints.service_name` (#275) | model | ✅ |
| `generate_declared_functional_slos` / `DeclaredEmittedSeries` (template) | `artifact_generator_generators.py` / `_models.py` | ✅ |
| `_functional_sli_query` / `_resolve_threshold` / `_series_slug` | `artifact_generator_generators.py` | ✅ |
| `_parse_declared_series` (parse template) | `artifact_generator_context.py:296` | ✅ |
| `compare.py` consumer (FR-7 mirror of #300 FR-10) | `compare.py:67/78/93` | ✅ |
| `declared_span_signals` / `DeclaredSpanSignal` | — | ❌ to add (FR-2) |
| ContextCore carry (REQ-CCL-109) | ContextCore #58 | ⏳ Part A (cross-repo) |

---

*v0.3.1 — Post planning + lessons + design-principle hardening. 6 assumptions corrected, OQ a–d resolved,
8 FRs / 4 NRs / 3 residual OQs (1 cross-repo PENDING). Ready for CRP. No code yet.*
