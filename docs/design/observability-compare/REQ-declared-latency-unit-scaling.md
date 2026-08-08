# Declared-Series Latency Threshold Unit-Scaling — Requirements

**Project:** startd8 observability generator   **Criticality:** medium
**Version:** 0.5 (IMPLEMENTED + OQ-2 resolved + liveness context)   **Date:** 2026-08-08
**Pairs with:** the embedded Plan (§Plan) below
**Origin:** F1 of the [Istio generality survivorship-audit](./GENERALITY_SURVIVORSHIP_AUDIT_ISTIO.md).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (grounding F1 against the real code) produced **three material corrections** —
> well over the 30% threshold; the audit's one-line fix suggestion was wrong in two ways. Grounded
> against `artifact_generator_generators.py` @ origin/main.

| v0.1 assumption (from the audit) | Planning discovery | Impact |
|---|---|---|
| The declared-latency default target is the **number 500**, unit-blind by 1000×. | It is the **raw string `"500ms"`** — `_resolve_threshold("latency_p99")` returns `'500ms'` (`:54`), used verbatim as the OpenSLO `target` (`:1517/:1527`). The `500` I first measured was a regex artifact grabbing `500` out of `target: 500ms`. | The defect is a **string-vs-number + unit mismatch**, not just a magnitude error: a unit-suffixed string target against a numeric `histogram_quantile` SLI. Reframes FR-2. |
| Fix = "reuse `_metric_unit`, which already recognizes `_seconds`/`_milliseconds`." | **`_metric_unit` is itself ms-blind.** `_METRIC_UNITS = {"duration": "s", …}` (`:~232`) has **no** milliseconds entry, so `_metric_unit("istio_request_duration_milliseconds")` returns **`"s"`**. | The fix needs a **prerequisite** — teach `_METRIC_UNITS` about milliseconds — or unit inference silently mislabels Istio's ms series as seconds. New **FR-1**. |
| "Bites only when the author declares a latency series **without** an explicit `target`." | The declared-**base** binder **never reads `s.target`** — it calls `_resolve_threshold("latency_p99", business, [])` for latency (`:1517`) and `_resolve_threshold("availability", …)` for availability (`:1478`). `DeclaredEmittedSeries.target` (`models.py:59`) is honored only on the **functional** path (`fr.target`). | The unit-blind default **always** applies to declared-base latency — an author cannot override it there today. Raises **OQ-2** (honor `s.target` now, or defer). |

**Resolved open questions:**
- **OQ (audit) → RESOLVED:** the convention path's correct behavior to mirror is `scale_threshold_seconds(_parse_duration_to_seconds(latency_raw))` (`:682-685`), which emits a **numeric** target (`0.5` for a seconds SLI). The declared path omits both steps.

### 0.1 Lessons-Learned Hardening (v0.3)

> Checked the SDK lessons base (`Lessons_Learned/sdk/`) + this session's survivorship discipline. Applied:

- **[Phantom-reference audit]** — grounded every symbol the spec names against the tree before citing:
  `_metric_unit`/`_METRIC_UNITS`, `_resolve_threshold`, `_parse_duration_to_seconds`,
  `scale_threshold_seconds`, `generate_declared_base_slos`, `DeclaredEmittedSeries.target` all exist and
  behave as cited (the §0 corrections are the audit findings *of that grounding*). No phantom symbols.
- **[Verify-merged / survivorship]** — the audit's numeric "500" claim was a measurement artifact; re-read
  the raw bytes (`target: 500ms`) rather than trust the earlier regex. Folded into §0 row 1.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked `docs/design-princples/`. Applied:

- **[Mottainai]** — FR-2 **reuses** the convention path's `_parse_duration_to_seconds` +
  `scale_threshold_seconds` scaling rather than a parallel declared-only scaler; FR-1 centralizes ms
  recognition in the **one** `_metric_unit` authority, not a second ad-hoc suffix parse.
- **[Accidental-Complexity anti-principle]** — the fix is *one general rule* (declared path scales like
  every other path via the shared helper), not a special-case latency branch; explicitly rejected adding
  a declared-only unit table.
- **[Hitsuzen]** — the unit is **determinable** from the series name deterministically (a table lookup),
  never an LLM call.

## Overview

The **convention** and **span** latency paths scale the default `latency_p99` threshold (`"500ms"`) into
the SLI's native unit and emit a **numeric** OpenSLO target (e.g. `0.5` for a seconds histogram; the
Tempo span path is asserted at `test_grpc_thanos_idiom_roundtrip.py`). The **declared-emitted-series**
base path (`generate_declared_base_slos`) does neither: it emits the raw string `"500ms"` as the target,
whatever the declared series' unit. So every declared-latency SLO in the all-seconds corpus carries a
malformed target (`"500ms"` string against a `histogram_quantile` SLI that returns seconds), and the
Istio pilot's `_milliseconds` series would be the first input where a raw-ms threshold is coincidentally
plausible. This spec makes the declared path scale like the convention path.

## Objectives

- **O-1:** the declared-series latency SLO target is a **number in the SLI's native unit** (seconds for
  a `_seconds` series, milliseconds for a `_milliseconds` series), matching the convention path.
- **O-2:** unit inference correctly distinguishes seconds from milliseconds by series name.
- **O-3:** no silent behavior change to author-supplied targets, availability/throughput, or the
  functional path; every changed emitted value is covered by an updated golden.

## Functional requirements

- **FR-1 — Teach `_METRIC_UNITS` milliseconds.** Add ordered patterns so `_metric_unit` returns `"ms"`
  for `*_milliseconds`/`*_millis`/`*_ms` **before** the `"duration" → "s"` fallback matches.
  *Touches:* `artifact_generator_generators.py:_METRIC_UNITS` / `_metric_unit`.
  *Verify:* `_metric_unit("istio_request_duration_milliseconds") == "ms"` and
  `_metric_unit("http_request_duration_seconds") == "s"`.
- **FR-2 — Scale the declared-latency default target.** On the declared-base latency path, infer the
  unit from `s.name` (`_metric_unit`), parse the default threshold to seconds
  (`_parse_duration_to_seconds`), and scale to the inferred unit → a **numeric** target (mirror the
  convention path's `scale_threshold_seconds`). *Touches:* `generate_declared_base_slos` `:1515-1527`.
  *Verify:* a declared `http_request_duration_seconds` latency SLO emits `target: 0.5`; a declared
  `istio_request_duration_milliseconds` emits `target: 500` (numeric).
- **FR-3 — Unknown-unit fallback is legible, not wrong.** When `_metric_unit(s.name) == ""` (no
  recognizable unit suffix), the SLO SHALL NOT emit a mis-scaled number: it either (a) defaults to the
  OTel convention (seconds) with a recorded `threshold_tier`/note, or (b) records the kind
  threshold-deferred (no target) — resolved in OQ-1. *Verify:* a `foo_latency` series (no unit suffix)
  does not silently emit `target: 0.5` as if it were seconds without a provenance mark.

## Non-goals

- **Availability / throughput declared-base targets** — not unit-sensitive the way latency is (99% /
  rps); out of scope (they also use `_resolve_threshold`, but no unit ambiguity).
- **The functional path** (`generate_declared_functional_slos`) — already honors `fr.target`.
- **The producer side** — ContextCore stamping `unit` (contextcore#404) / `activation` (#406) on emitted series is a separate, filed ask.
- **A general "author-supplied target on a declared-base series"** feature (OQ-2 → deferred, low-priority).

## Open questions

- **OQ-1 → RESOLVED (default-to-seconds).** Confirmed against a REAL no-suffix subject: Harbor's
  `harbor_task_queue_latency` (covers latency, no unit suffix). Implemented as seconds (the OTel/
  `histogram` base unit) → numeric `0.5`. The ContextCore `unit` stamp (contextcore#404) will make this
  explicit rather than assumed.
- **OQ-2 → RESOLVED (deferred, low-priority)** — decided 2026-08-08 in discussion:
  - **(a) Do NOT make base-RED defer-when-no-target like the functional path.** The base/functional split
    is *principled*, not accidental: base-RED has meaningful universal defaults (500ms p99 / 99%
    availability); functional signals (saturation, queue_depth) have none, so they defer. The
    load-registration lens (§Liveness) reinforces it — base-RED series register under generic warm-up;
    functional/`state:` series often don't. Making base-RED defer would drop every current Harbor latency
    SLO.
  - **(b) Honoring an author `s.target` on the declared-base path** (closing the silent-ignore footgun) is
    a clean but **low-priority** follow-up: no producer populates `s.target` today, and the liveness lens
    makes it triply-latent (no setter · SLI needs load to matter · base-RED already has a working default).
    Fold into the contextcore#404 (`unit`) / #406 (`activation`) survey seam if/when built.

## Liveness context — this is a generation-layer fix (added v0.5)

F1 is a **static generation** correctness fix: the target must be a number in the SLI's native unit, true
regardless of load. It is **orthogonal to liveness** — the declared-latency SLI queries
`histogram_quantile` over a `*_bucket` series that is **lazily registered: it has no data until traffic
flows** (the compare-live warm-up exists for exactly this). Consequence for pilot scoring: a unit/target
defect counts as a real `sdk_code` finding **only once the pilot workload has been driven and the SLI is
*still* wrong** — otherwise an unbound SLI is a `workload` (load) gap, not a code gap. That attribution
rule is **contextcore#406** (thread per-metric `activation` into owner-attribution); together with
**#404** (`unit`) it is the producer-side survey seam this fix pairs with.

## Risks

| Type | Description | Mitigation | Priority |
|---|---|---|---|
| Behaviour change | Existing **seconds** declared-latency SLOs change from `target: "500ms"` → `target: 0.5`. | This is a *bug fix* (the old value was malformed); update the affected goldens in the same PR and call it out. | High |
| Test blast radius | `test_functional_emission.py` (7 `target:` refs) + `test_onboarding_metadata_golden_roundtrip.py` (1) may assert the old value. | Enumerate before editing; only declared-**latency** target assertions should change. | High |
| Over-reach | Touching `_metric_unit` affects any caller. | FR-1 is purely additive (new ms patterns, ordered before the `duration→s` fallback); verify existing callers unchanged. | Medium |

## Plan (iterations)

1. **I-1 (FR-1):** add ms patterns to `_METRIC_UNITS`, ordered before `duration`. Unit test `_metric_unit`. *(No emitted-artifact change yet.)*
2. **I-2 (FR-2):** scale the declared-latency default in `generate_declared_base_slos` (infer unit → parse → scale → numeric target). Reuse `_parse_duration_to_seconds` + the convention path's scaling.
3. **I-3 (FR-3 + goldens):** implement the unknown-unit fallback (per OQ-1) and update every golden whose declared-latency target legitimately changed (`"500ms"` → `0.5`), with a one-line note in each.
4. **I-4 (verify):** run the full observability suite; confirm only declared-latency targets changed and the Istio/Thanos gRPC + golden round-trips still pass.

## Appendix A — Accepted (with where merged)
- **FR-1/FR-2/FR-3 — IMPLEMENTED** (this branch): `_METRIC_UNITS` learns milliseconds (ordered before
  `duration`); `generate_declared_base_slos` scales the declared-latency default via the single-sourced
  `scale_seconds_to_unit` (metric_descriptor.py, also backing `MetricDescriptor.scale_threshold_seconds`).
  **Live-verified:** real Harbor `out/*/onboarding-metadata.json` no longer ship the string `target: 500ms`
  on core/jobservice/registry — they now emit numeric `0.5` (seconds). ZERO existing goldens changed
  (none locked the buggy value). New: `test_declared_latency_unit_scaling.py`.
- **OQ-1 → default-to-seconds** (grounded on Harbor's suffix-less `harbor_task_queue_latency`).

## Appendix B — Rejected (with rationale)
*(none yet)*

## Appendix C — Incoming review rounds
*(CRP rounds appended here)*

---

*v0.3.1 — Post-planning (3 corrections, §0) + lessons hardening (§0.1: phantom-ref audit, verify-merged) + principle hardening (§0.2: Mottainai/Accidental-Complexity/Hitsuzen — reuse the shared scaler, single-source `_metric_unit`). The audit's one-line fix was insufficient in two ways — grounding paid for itself. Ready for CRP.*
