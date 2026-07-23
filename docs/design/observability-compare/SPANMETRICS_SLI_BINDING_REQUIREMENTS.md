# Span-Metrics SLI Binding (declared trace surface → bind SLIs with `service.name`) — Requirements

**Version:** 0.4 (post CRP Round 1 — 10 suggestions + adversarial, all applied)
**Date:** 2026-07-23
**Status:** IMPLEMENTED (2026-07-23) — `generate_declared_span_slos` + `tempo-spanmetrics` profile +
`DeclaredSpanSignal` + compare.py consumer + §2.0 span>series precedence + 10 tests. FR-6's
`fr_coverage`-gate fix (R1-F7) landed separately as **#310** (drift-proof `any(values())`); v1 = per-span RED.
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

### 2.0 Declared-binding lane invariants (single de-dup authority) — *(R1-F10)*

There are now **three declared-binding emission lanes**: base RED (#286, `generate_declared_base_slos`),
functional (#300 D2, `generate_declared_functional_slos`), and span (#307, `generate_declared_span_slos`).
The lanes MUST **partition every `(service, kind)` into exactly one owner**. Today base and functional avoid
each other only by hand-coded `if kind in BASE_RED_KINDS: continue` skips in each generator — adding a third
lane turns 1 pairwise skip into 3 (a shotgun-surgery seam). **Requirement:** the three lanes keep their
**separate output files** (the #300 FR-6 contract), but consult **one** precedence/de-dup authority — a
`declared_binding_owner(service, kind)` (or equivalent single function) — rather than each generator deciding
independently. A 4th lane later must touch only that function. This owns the FR-4 span-vs-declared-series
precedence and the base/functional skips uniformly.

### 2.1 Requirements

**FR-1 — Recognize the `spanmetrics` surface.** Add `spanmetrics` to the `metrics_surface` enum
(startd8-owned). It is added to `NON_EMITTING_CONVENTION_SURFACES` (the OTel-convention meter metric is still
absent → base RED SLIs suppress as today) **and** to `NON_SCRAPEABLE_SURFACES` (`metric_descriptor.py:231`):
a pure span-metrics/traces subject serves no `/metrics` endpoint, so its ServiceMonitor must be suppressed
with a `suppressed_scrape_configs` gap — else #307 re-ships the exact #285 dead-ServiceMonitor class.
`spanmetrics` is also the trigger that activates span-signal binding (FR-4). *(R1-F3)*

**FR-2 — Carry & parse `declared_span_signals`.** Parse `instrumentation_hints[svc].metrics.declared_span_signals`
(carried by ContextCore REQ-CCL-109) into a new `DeclaredSpanSignal` model:
`{span_name, attributes: Dict[str,str] = {}, covers: List[str], error_selector: str = "", target: Optional[str] = None, enabling_flag: str = ""}` — the span analogue of `DeclaredEmittedSeries`. Parse discipline mirrors
`_parse_declared_series`: explicit-only, absent→omitted (byte-identical), `covers`/`error_selector` **unfiltered**,
`target` read as `.get("target")`→`None` (not `""`).

**FR-3 — Single-source the span-metrics series names via a descriptor profile, resolved independently of
`descriptors[svc]`.** The bound PromQL series names/labels come from a `MetricDescriptor` profile, not
hardcoded. Add a `tempo-spanmetrics` profile (`traces_spanmetrics_latency_seconds_bucket`,
`traces_spanmetrics_calls_total`, the errors dimension, `service_label_key="service_name"`, `latency_unit="s"`)
resolving the acceptance convention, coexisting with the existing `span-metrics-connector` (OTel-Collector,
`ms`) profile.
- **Selection (R1-F1):** the pipeline builds exactly ONE descriptor per service (`artifact_generator.py:531`,
  `descriptors[svc]` via `metric_profile`) — that is the base-RED/alert descriptor (Mastodon = `semconv-http`,
  label `service`, unit `s`). `generate_declared_span_slos` MUST resolve its **own** span descriptor (a fixed
  `SPAN_METRICS_TEMPO_PROFILE` constant, optionally per-signal-overridable), **not** `descriptors[svc]` — else
  it binds the wrong series/label.
- **Server-kind filter (R1-F8):** the profile carries `extra_selectors` for the server-span filter
  (`span_kind="SPAN_KIND_SERVER"`, per the `metric_descriptor.py:82` double-count warning); the binder ANDs
  the profile's `extra_selectors` with the signal's `attributes` and `span_name` (each rendered only when
  non-empty — the #300-A empty-value discipline).

**FR-4 — Bind per-span SLIs with the real `service.name`.** For each `(span signal, covered-kind)`, bind an
SLI on `<latency_bucket>{service_name="<real>", span_name="<declared>"[, <attributes>][, <extra_selectors>]}`
(and the calls/errors counters for throughput/availability), where `<real>` is `service.service_name` (#275).
Precedence is decided by §2.0's single authority: **declared span-signal > declared Prometheus series > suppress
convention > convention** — a service declaring BOTH a `declared_emitted_series` and a `declared_span_signal`
covering the same kind binds exactly ONE (span wins, per the trace-surface intent) and records the loser with
a de-dup reason_code; no double-emit *(R1-F4)*. Query shape reuses `_functional_sli_query`/the base RED shapes.
- **Availability orientation (R1-F5):** availability reuses the #286-v2 good/total shape, which wires the
  ERROR subset as the ratio numerator (`good = rate(calls_total{<error_selector>})`, `total =
  rate(calls_total{})`) — i.e. an **error-ratio** objective. FR-4 fixes this orientation explicitly so the
  counters aren't inverted; the Tempo error dimension (`status_code="STATUS_CODE_ERROR"`) lives in the
  **profile's** `error_selector`, not the binder. Needs the signal's `error_selector`, else deferred.

**FR-5 — Threshold discipline (reuse #300 D2) + unit scaling.** Base RED kinds resolve the threshold from the
manifest/importance default (as #286); a functional kind with no `target` is **threshold-deferred** with its
grounded query in `deferred_declared_kinds` (#300 D2/FR-4); the SDK never invents a threshold (NR-2). **The
latency target MUST be scaled through the resolved profile's `MetricDescriptor.scale_threshold_seconds`
(`metric_descriptor.py:114`)** — `histogram_quantile` returns in the descriptor's unit, so `500ms` renders
`> 0.5` on the Tempo (`s`) profile and `> 500` on the OTel-connector (`ms`) profile; omitting the scale ships
a 1000× wrong SLO. *(R1-F2)*

**FR-6 — Separate emission lane + accounting (and fix the latent `fr_coverage` gate).** Emit into
`{svc}-declared-span-slo.yaml` (a peer of the declared-base/-functional lanes). Add `bound_declared_span` to
`fr_coverage` (only when non-empty — byte-identity per #300 FR-9); deferred/mismatch/precedence-skip cases feed
`deferred_declared_kinds` with a reason_code. **In-scope pre-existing fix (R1-F7):** the `fr_coverage`-emission
gate (`artifact_generator.py:1349`) keys on a fixed list that **omits all `bound_declared_*` keys and
`deferred_declared_kinds`** — so a run whose ONLY coverage signal is a declared binding (no suppression) drops
`fr_coverage` from the manifest entirely and `compare.py` reads `{}`. #307 MUST add `bound_declared_span`
(and, in-scope, `bound_declared_series`/`bound_declared_functional`/`deferred_declared_kinds`) to that gate.

**FR-7 — `compare.py` consumer contract (four concrete edits).** *(R1-F6, mirrors #300 FR-10 granularity):*
(1) new `ComparisonReport.bound_span` field + `to_dict`; (2) `build_comparison_report` reads
`bound_declared_span`; (3) `render_report` presents a "Bound span-metrics SLIs" block; (4) span bound/deferred
entries MUST stamp a resolved `series` key (the `traces_spanmetrics_*` name) **and** `kind` so `_entry_line`
(`compare.py:91`, gated on `entry.get("series") and entry.get("kind")`) renders `kind → series` — else they
degrade to a bare reason line. Threshold-deferred entries also carry their query (as #300 D2).

**FR-8 — Byte-identical when absent (with a golden vehicle).** No `declared_span_signals` ⇒ no span lane file,
no `bound_declared_span` key (absent, not `[]` — the #300 D2 trap at `artifact_generator.py:679`), no behavior
change. **Acceptance (R1-F9):** a golden-diff test against a spanmetrics-absent fixture asserts byte-identical
artifacts vs the pre-#307 tree.

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
- **OQ-3 — RESOLVED to an acceptance criterion (R1-F5).** The error dimension is
  `status_code="STATUS_CODE_ERROR"` on `traces_spanmetrics_calls_total`, encoded in the profile's
  `error_selector`; the good/total orientation is the #286-v2 error-ratio (FR-4). Acceptance: `compare-live`
  replay against a real Tempo metrics-generator surface confirms the emitted good/total counters.

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

*v0.4 — Post CRP Round 1 (10 F-suggestions + adversarial, all ACCEPTED; dispositions in Appendix A). Added
§2.0 single-de-dup-authority; FR-1 +NON_SCRAPEABLE, FR-3 +selection/+server-kind-filter, FR-4 +lane-precedence/
+availability-orientation, FR-5 +unit-scaling, FR-6 +latent-fr_coverage-gate-fix, FR-7 +4-edit compare contract,
FR-8 +golden. 8 FRs + §2.0 / 4 NRs / 2 residual OQs (1 cross-repo PENDING). Ready to implement. No code yet.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Span binder must resolve its OWN descriptor, not `descriptors[svc]` | CRP R1 | Applied → FR-3 Selection clause (`SPAN_METRICS_TEMPO_PROFILE`) | 2026-07-23 |
| R1-F2 | Scale latency target via `scale_threshold_seconds` (ms/s = 1000×) | CRP R1 | Applied → FR-5 (verified `:114` exists) | 2026-07-23 |
| R1-F3 | Add `spanmetrics` to `NON_SCRAPEABLE_SURFACES` (else dead ServiceMonitor, #285) | CRP R1 | Applied → FR-1 | 2026-07-23 |
| R1-F4 | Define span-vs-declared-series precedence for same `(svc,kind)` | CRP R1 | Applied → §2.0 authority + FR-4 precedence order | 2026-07-23 |
| R1-F5 | Pin availability good/total orientation (#286-v2 error-ratio) + promote OQ-3 | CRP R1 | Applied → FR-4 availability + OQ-3 resolved | 2026-07-23 |
| R1-F6 | Enumerate all 4 compare.py edits + `series`-key stamp for `_entry_line` | CRP R1 | Applied → FR-7 | 2026-07-23 |
| R1-F7 | Fix latent `fr_coverage`-emission gate (`:1349` omits bound keys) — **pre-existing bug** | CRP R1 | Applied → FR-6 (verified: gate omits all bound_* + deferred keys) | 2026-07-23 |
| R1-F8 | Profile needs `span_kind=SERVER` `extra_selectors` (double-count) | CRP R1 | Applied → FR-3 server-kind-filter | 2026-07-23 |
| R1-F9 | FR-8 needs a byte-identity golden vehicle | CRP R1 | Applied → FR-8 acceptance | 2026-07-23 |
| R1-F10 | Single de-dup authority across the 3 declared lanes (not pairwise skips) | CRP R1 adversarial | Applied → new §2.0 lane invariants | 2026-07-23 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-23

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-07-23 23:10:00 UTC
- **Scope**: First external review of a brand-new requirements doc. Focus-file weighted: FR-3 descriptor-profile reconciliation + per-service SELECTION + ms/s unit leak; FR-1 dual-nature vs the #274/#285 gates; FR-4 precedence/de-dup across the now-three declared lanes; FR-4 availability-from-span-metrics; FR-6/7 the third `bound_declared_*` key + accounting unification. Grounded against the merged tree (`metric_descriptor.py`, `artifact_generator{,_generators,_context,_models}.py`, `compare.py`).

##### Focus-file numbered asks

**Ask 1 — FR-3: second profile vs parameterized, and how is the profile SELECTED per service? Does the ms/s unit leak into the SLO target?**
- **Summary answer:** A second `tempo-spanmetrics` profile is right; but the doc has a real GAP on *selection* — the current code resolves exactly ONE descriptor per service and the span binder needs a DIFFERENT one, and the ms/s handling must be named explicitly.
- **Rationale:** `artifact_generator.py:531` builds `descriptors[service.service_id] = resolve_descriptor(profile=service.metric_profile or None, kinds=…, transport=…)` — one descriptor per service, driven by `metric_profile`. That descriptor is the base-RED/alert descriptor. The span binder cannot reuse it (Mastodon's `metric_profile` is `semconv-http`, unit `s`, label `service`), so FR-3 must say where `generate_declared_span_slos` gets its `tempo-spanmetrics` descriptor from — it is NOT `descriptors[svc]`. On the unit: `MetricDescriptor.scale_threshold_seconds` (`metric_descriptor.py:114`) already exists precisely for this (`ms`→×1000, `s`→identity); the Tempo profile is `latency_unit="s"`, the existing connector profile is `"ms"`, so a p99 SLO target of `500ms` renders `> 0.5` for Tempo and `> 500` for the connector. The doc must require the latency target be run through `scale_threshold_seconds` (as `generate_alert_rules` does), or the ms-profile fork ships a 1000× wrong SLO.
- **Assumptions / conditions:** none — both `descriptors[svc]` (`:531`) and `scale_threshold_seconds` (`:114`) are present and verified.
- **Suggested improvements:** see R1-F1 (selection source), R1-F2 (unit scaling).

**Ask 2 — FR-1: is the dual role coherent with #274 suppression + #285 ServiceMonitor gates? Should `spanmetrics` be scrapeable?**
- **Summary answer:** Coherent for #274, but there is an UNADDRESSED #285 (`NON_SCRAPEABLE_SURFACES`) decision that will mis-fire.
- **Rationale:** Adding `spanmetrics` to `NON_EMITTING_CONVENTION_SURFACES` (`metric_descriptor.py:220`) makes `_service_sli_kinds` (`:256`) drop the convention RED triple — correct, the span binding re-grounds it. BUT FR-1 is silent on `NON_SCRAPEABLE_SURFACES` (`:231`). A span-metrics/traces-only subject serves **no** `/metrics` endpoint, yet because `spanmetrics ∉ NON_SCRAPEABLE_SURFACES` the generator (`artifact_generator.py:712`) will still emit a **dead ServiceMonitor** — the exact #285 class the last cycle closed. FR-1 must decide this explicitly.
- **Suggested improvements:** see R1-F3.

**Ask 3 — FR-4: does "declared span-signal > suppress > convention" interact correctly with `_declared_covered_kinds` and the #300 base/functional binders? De-dup risk across three lanes.**
- **Summary answer:** Partial — the doc states precedence vs *convention* but never resolves precedence *between the two declared lanes* (span vs `declared_emitted_series`) for the same `(service, kind)`, which is a live double-emit.
- **Rationale:** `_declared_covered_kinds(service)` (`artifact_generator_generators.py:1182`) reads only `declared_emitted_series`. If a service declares BOTH a Prometheus series covering `latency` AND a span signal covering `latency`, `generate_declared_base_slos` emits one SLO and `generate_declared_span_slos` emits another — same `(svc, latency)`, two graded SLOs, no suppression between them. FR-4 only says span > suppress > convention; it must state span-vs-declared-series precedence and whether `_declared_covered_kinds` (or a sibling) suppresses one.
- **Suggested improvements:** see R1-F4.

**Ask 4 — FR-4 availability from span-metrics: is #286 v2 transferable, what is the real error dimension?**
- **Summary answer:** Transferable, but the doc must pin the ratio ORIENTATION and the good/total query shape, and OQ-3 should carry an acceptance test, not just prose.
- **Rationale:** #286 v2's availability path (`generate_declared_base_slos:1251-1279`) builds `good = rate(series{err_sel})` / `total = rate(series{})` — i.e. it wires the ERROR subset as "good", which is the *error-rate* ratio, not success. For Tempo `traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}` the same shape works ONLY if the SLO objective is interpreted as an error budget. FR-4 must state which (success ratio vs error ratio) so the emitted `good`/`total` counters aren't inverted.
- **Suggested improvements:** see R1-F5.

**Ask 5 — FR-6/7: a THIRD `bound_declared_*` key + lane — is the surface scaling, or should accounting unify?**
- **Summary answer:** It scales, but only if three concrete consumer edits are specified; and there is a pre-existing latent bug the third key would inherit that the doc should fix in-scope.
- **Rationale:** `compare.py` needs (a) a `bound_declared_span` field on `ComparisonReport`, (b) reads in `build_comparison_report` (`compare.py:76` sibling), (c) a render block (`render_report:119` sibling), AND (d) `_entry_line` (`compare.py:91`) keys on `entry.get("series") and entry.get("kind")` — span entries carry `span_name`, so unless they ALSO stamp a `series` key (the resolved `traces_spanmetrics_*` name) they render as a bare `- who: reason`. Separately, `artifact_generator.py:1349` gates whether `fr_coverage` is written to the manifest at all on a **fixed key list** that already omits `bound_declared_series`/`bound_declared_functional` — so a run whose ONLY signal is a span binding would drop `fr_coverage` entirely and compare.py would read `{}`. FR-6/FR-7 should require adding `bound_declared_span` to that gate list (and note the latent omission of the other two).
- **Suggested improvements:** see R1-F6, R1-F7; unification stress-test in the adversarial subsection.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | FR-3 must specify HOW `generate_declared_span_slos` obtains its `tempo-spanmetrics` descriptor, given the pipeline builds exactly ONE descriptor per service (`descriptors[svc]` via `metric_profile`). State that the span binder resolves its OWN descriptor (e.g. `profile_for("tempo-spanmetrics")` or a fixed `SPAN_METRICS_TEMPO_PROFILE` constant) independent of `descriptors[svc]`, and whether an author can override it (per-signal `profile:` vs a fixed constant). | As written, an implementer would pass `descriptors[svc]` (Mastodon's `semconv-http`, label `service`, unit `s`) into the span binder and bind the WRONG series/label. The "how is the profile selected" question in the focus file is unanswered. | FR-3, after "The binder selects the profile" | Unit test: a service with `metric_profile: semconv-http` still binds span SLIs on `traces_spanmetrics_*{service_name=…}`, not `http_server_duration{service=…}`. |
| R1-F2 | Data | high | FR-4/FR-5 must require the latency SLO **target** be scaled through `MetricDescriptor.scale_threshold_seconds` for the resolved span profile, and add an acceptance line: `500ms` ⇒ `> 0.5` on the Tempo (`s`) profile vs `> 500` on the OTel-connector (`ms`) profile. | The two coexisting profiles differ in unit (`s` vs `ms`, `metric_descriptor.py:74/149`); `histogram_quantile` returns in the descriptor's unit. Without naming `scale_threshold_seconds` (which already exists at `:114`) the doc leaves the 1000× target error latent — exactly the FR-4a bug that method was written to prevent. | FR-4 (latency binding) and FR-5 (threshold discipline) | Golden test: same `latency: 500ms` manifest, two profiles, assert emitted `target`/comparator differ by 1000×. |
| R1-F3 | Ops | high | FR-1 must state explicitly whether `spanmetrics` is added to `NON_SCRAPEABLE_SURFACES` (`metric_descriptor.py:231`). A pure span-metrics/traces-only subject serves no `/metrics`, so omitting it ships a dead ServiceMonitor (#285). | FR-1 only touches `NON_EMITTING_CONVENTION_SURFACES`; the #285 ServiceMonitor gate is a SEPARATE frozenset and will still emit a scrape config for a `spanmetrics` service unless the doc decides otherwise. The focus file explicitly asks "any gate that would now mis-fire." | FR-1, new sentence after the `NON_EMITTING_CONVENTION_SURFACES` addition | Test: a `metrics_surface: spanmetrics` service produces NO `servicemonitors/*.yaml` and records a `suppressed_scrape_configs` gap (mirror the #285 test). |
| R1-F4 | Risks | high | FR-4 must define precedence between the two DECLARED lanes for the same `(service, kind)`: if a service declares both a `declared_emitted_series` and a `declared_span_signal` covering `latency`, which binds and which is suppressed/recorded? Today `_declared_covered_kinds` (`:1182`) suppresses convention RED but does nothing between declared lanes. | Without this, both `generate_declared_base_slos` and `generate_declared_span_slos` emit a graded SLO for `(svc, latency)` — a double-emit the #300-D covers-filter work was specifically hardening against. "declared span-signal > suppress > convention" omits the declared-Prometheus-series peer. | FR-4, precedence clause | Test: a service declaring both lanes for `latency` yields exactly one graded SLO for that kind + a recorded de-dup reason for the loser. |
| R1-F5 | Interfaces | medium | FR-4 availability must pin the good/total ORIENTATION and query shape for the span error dimension. State whether the SLO objective is success-ratio or error-budget, matching the #286 v2 shape (`good = rate(calls_total{status_code="STATUS_CODE_ERROR"})`, `total = rate(calls_total{})`). Promote OQ-3 to an acceptance criterion, not prose. | The reused #286 path wires the ERROR subset as `good` (error-rate ratio). If FR-4 means success-availability, the counters are inverted vs the reused code — a silent semantic bug. The real Tempo dimension (`status_code="STATUS_CODE_ERROR"` on `traces_spanmetrics_calls_total`) should be encoded in the profile's `error_selector`, not restated in the binder. | FR-4 (availability) + OQ-3 | `compare-live` replay: confirm the emitted good/total against a real Tempo metrics-generator surface (already the OQ-1/OQ-3 vehicle). |
| R1-F6 | Interfaces | high | FR-7 must enumerate ALL FOUR compare.py consumer edits, not just "surface `bound_declared_span`": (1) new `ComparisonReport.bound_span` field + `to_dict`, (2) `build_comparison_report` read, (3) `render_report` block, (4) make span bound/deferred entries stamp a `series` (resolved `traces_spanmetrics_*` name) + `kind` so `_entry_line` (`compare.py:91`) renders them — else they degrade to a bare reason line. | `_entry_line`'s pretty path is gated on `entry.get("series") and entry.get("kind")`; span signals carry `span_name`. A single "surface it" sentence hides four real edits and one shape constraint; #300 FR-10 needed exactly this granularity. | FR-7 | Test: a span-bound run's `render_report` output contains a `Bound span-metrics SLIs` section with `kind → series` lines, and `to_dict()['bound_declared_span']` is populated. |
| R1-F7 | Validation | high | FR-6 must require adding `bound_declared_span` (and, in-scope, `bound_declared_series`/`bound_declared_functional`) to the `fr_coverage`-emission gate at `artifact_generator.py:1349`. Today that gate's fixed key list omits the bound keys, so a run whose ONLY coverage signal is a declared binding drops `fr_coverage` from the manifest entirely and compare.py reads `{}`. | This is a pre-existing latent bug the third lane would inherit and make visible: a Mastodon-style traces-only service that binds ONLY span SLIs (no suppressions, no ungrounded kinds) would produce a manifest with no `fr_coverage`, silently hiding the positive binding from the Tier-A report. | FR-6 (accounting) + a note in §9 Reference Audit | Test: a manifest whose only fr_coverage content is `bound_declared_span` still writes the `fr_coverage:` block; assert `read_fr_coverage` returns it non-empty. |
| R1-F8 | Data | medium | FR-3/OQ-2 must decide whether the `tempo-spanmetrics` profile carries an `extra_selectors` server-kind filter (e.g. `span_kind="SPAN_KIND_SERVER"`), and how a declared signal's free-form `attributes` compose with it. The existing descriptor doc warns span-metrics "often needs a server-kind filter to avoid double-counting client spans" (`metric_descriptor.py:82-84`). | Sidekiq worker spans and web request spans both flow through the connector; without a kind filter, `calls_total` double-counts client+server and the throughput/availability SLIs are 2× off. FR-3's profile sketch omits `extra_selectors` entirely. | FR-3 profile definition + OQ-2 | Test: the resolved selector for a span signal ANDs the profile's `extra_selectors` with the signal's `attributes` and `span_name`, non-empty only. |
| R1-F9 | Validation | medium | FR-8 (byte-identical when absent) needs a stated acceptance vehicle: a golden-diff test asserting a fixture with NO `declared_span_signals` produces byte-identical artifacts + no `bound_declared_span` key vs the pre-#307 tree, mirroring #300 FR-9. The FR asserts the property but names no test. | Every prior lane (#286 FR, #300 FR-9) shipped a byte-identity golden; FR-8 currently states the invariant without a verification hook, so an implementer could regress it (e.g. by always writing an empty `bound_declared_span: []`, the exact #300 D2 trap called out in `artifact_generator.py:679`). | FR-8 | Golden-diff CI test against a spanmetrics-absent fixture. |

##### Adversarial pass — the "three declared lanes" stress test (focus Ask 5: unify or not?)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F10 | Architecture | medium | Add a §2.x "declared-binding lane invariants" statement asserting the three lanes (base #286, functional #300-D2, span #307) partition every `(service, kind)` into exactly one owner, with a single de-dup authority — rather than three generators independently deciding. This answers Ask 5: keep three EMISSION lanes (three YAML files) but require ONE precedence/de-dup function they all consult. | The base and functional binders already avoid each other only by a hand-coded `if kind in BASE_RED_KINDS: continue` in each generator (`:1284`, `:1396`). A third lane multiplies these pairwise skips (span-vs-base, span-vs-functional, span-vs-declared-series) from 1 to 3, each a shotgun-surgery seam. A single `declared_binding_owner(service, kind)` the doc mandates would prevent the R1-F4 double-emit AND stop the pairwise-skip sprawl without collapsing the (legitimately separate) output files. | New §2 subsection referenced by FR-4/FR-6 | Test matrix: a service declaring the same kind across all three lanes yields exactly ONE graded SLO and two recorded de-dup reasons; adding a 4th lane later touches only the owner function. |

Note (not a suggestion): I did NOT re-propose collapsing the three `{svc}-declared-*-slo.yaml` files into one — that would break the #300 FR-6 separate-lane contract and is out of scope. R1-F10 unifies only the *precedence/accounting decision*, not the emission surface.
