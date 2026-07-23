# Synthetic-Probe SLI — P0 (declaration + static freshness SLO, $0) — Requirements

**Version:** 0.3.1 (post planning + lessons + design-principle hardening; ready for CRP)
**Date:** 2026-07-23
**Status:** Draft — spec only, no code
**Owner:** observability artifact generator (`src/startd8/observability/`)
**GitHub:** startd8-sdk **#308** (option-b2), **Phase P0** only · ContextCore probe-carry to follow
**Refs:** design doc `SYNTHETIC_PROBE_SLI_DESIGN.md` (the P0–P3 frame), #300 D2 (threshold-deferral —
the template), #307 (descriptor-profile single-sourcing), option-b2
(`OSS/mastodon/analysis/option-b2-freshness-probe-capability-ask.md`)

---

## 0. Planning Insights (Self-Reflective Update)

> What the planning pass (reading `_FUNCTIONAL_SLI_TEMPLATES`, the #300 D2 threshold-deferral, the
> existing "probe" usages, and the compare surface) corrected from the naïve "emit a freshness SLO" draft.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| A freshness SLO reuses the existing `freshness` template (`_FUNCTIONAL_SLI_TEMPLATES["freshness"]`). | That template is `("job_last_success_timestamp_seconds", "age", "s")` — shape `age` = `time() - max(metric)`, for **last-success timestamps**. A fan-out probe publishes a **measured latency** (`t(visible)−t(created)`) as `probe_fanout_freshness_seconds` — a gauge/histogram, NOT a timestamp. | **Do NOT reuse the `age` freshness shape.** The probe's published metric is queried as a gauge (`max(...)`) or histogram quantile. Freshness-via-probe ≠ freshness-via-age — a distinct binding. |
| The author supplies the freshness threshold. | option-b2 discipline: the author states the probe *shape*; the **threshold stays inferred** ("don't hand it the SLO number"). #300 D2 already solved "query determinable, target from author-or-deferred." | **Reuse #300 D2 threshold-deferral verbatim**: a probe with no `target` emits the SLI query as **threshold-deferred**; the SDK never invents the number (NR-1). |
| Emit the SLO and we're done. | The published metric **does not exist until a runner runs the probe** (P1/P2). A plain SLO querying `probe_fanout_freshness_seconds` would be false-flagged by `compare`/`compare-live` as a **dead SLI** (#274 class) — the exact opposite of the intended "positive finding." | P0 must record a **`pending_probes`** gap so the metric is understood as *pending a runner*, NOT dead. `compare` surfaces it; the #310-style latent-gate is already values-based so a pending-only run still writes `fr_coverage`. |
| Name it `probe`. | "probe" already means the blackbox-query re-probe (`validate_promql`), `fleet.boot_and_probe`, and the contamination probe. | **Name the concept distinctly:** model `DeclaredProbe`, SLI type `synthetic-probe`, published metric under a single-sourced contract. Avoid overloading `probe`. |
| The published-metric name is free-form. | The SLO's SLI query (P0) and the future runner's publish (P1) MUST agree, or the SLI never binds even after the probe runs. #307 FR-3 established single-sourcing series names via a profile. | **Single-source the published-metric contract** (name + kind) — declared on the probe (or a default profile), so P0's query and P1's runner are the same string by construction. |

**Resolved open questions (from the design doc):**
- **OQ-3 (published-metric contract) → single-sourced on the `DeclaredProbe`** (`published_metric` + `metric_kind`), defaulting to `probe_<name>_seconds`/gauge; P0's query derives from it (FR-3).
- **OQ-4 (threshold) → threshold-deferred (reuse #300 D2)**, never inferred by the SDK (FR-4, NR-1).
- **OQ-5 (compare semantics) → a `pending_probes` Tier-A class** distinct from a dead SLI (FR-5); the live/Tier-B pending-probe verdict is **P2, out of P0 scope** (NR-3).
- **OQ-1/OQ-2 (runner artifact, credentials/side-effects) → out of P0 scope** — P0 is static, $0, no runtime, no runner spec, no secrets (NR-2).

### 0.1 Lessons-Learned Hardening (v0.3)

- **Phantom-reference audit** — verified: `_FUNCTIONAL_SLI_TEMPLATES` / `_functional_sli_query`
  (`artifact_generator_generators.py`), the #300 D2 threshold-deferral (`functional_bound_threshold_deferred`),
  the values-based `fr_coverage` gate (#310), the compare consumer (`compare.py`), `_series_slug`,
  `_resolve_threshold`. Added §9 Reference Audit.
- **[preserve-declared-intent-consumer-decides]** — the parser carries the probe's full declaration
  verbatim (`action`/`poll`/`assert`/`measure`); no producer-side subsetting.
- **Single-source vocabulary ownership** — the published-metric name/kind is owned by the `DeclaredProbe`
  (or one default profile), cited by the query builder — never restated at the query site.
- **[verify-consumer-against-merged-diff]** — the `pending_probes` compare surface is verified against the
  merged `compare.py`, and the SLO shape against a real OpenSLO validator (§5).

### 0.2 Design-Principle Hardening (v0.3.1)

- **Genchi Genbutsu / not-fabrication** — the SLO is *derived from the declared probe*, and the value it
  will measure is **real behavior** (t(visible)−t(created)); the SDK asserts no metric that isn't there —
  it marks it *pending a runner*. The threshold comes from author intent or is deferred (never invented).
- **Hitsuzen (derive the determinable)** — the SLI *query* is fully determined by the probe's published-
  metric contract; only the *measurement* (P1/P2) and the *threshold* (author) are not. Derive the query,
  defer the rest.
- **Accidental-Complexity anti-principle** — P0 adds NO runtime, NO runner, NO secret plumbing. It is the
  smallest artifact that delivers the "derived SLO Mastodon has no metric for" finding; P1–P3 are separate.
- **Mottainai** — reuse #300 D2 threshold-deferral and the `compare` consumer shape; do not build a
  parallel deferral or a second gap channel.

---

## 1. Problem Statement

FR-007 **fan-out freshness** (status-creation → feed-visible latency) is the pilot's flagship *derive-value*
case: *"a derived SLO Mastodon has no metric for is a positive finding."* Mastodon emits **no** freshness
metric, and (settled from source) `propagation_style: :link` means the fan-out is **cross-trace** — so
neither a scrape (#286) nor a span-metrics connector (#307) can produce it. It requires a **synthetic
probe** (do X, poll until Y, measure the delta). That probe is a **runtime, live-subject** capability — but
its *declaration and the derived SLO* are static and $0. **P0 delivers exactly that static half**: declare
the probe, emit the freshness SLO (threshold-deferred), and record it as *pending a runner* — without any
runtime, runner spec, or credentials (all P1+).

## 2. Requirements (P0)

**FR-1 — `DeclaredProbe` model + parse.** Add a `DeclaredProbe` model carried on
`instrumentation_hints[svc].metrics.declared_probes` (ContextCore carry to follow), parsed like the other
declared-* families (explicit-only, absent→omitted byte-identical):
`{name, action, poll, assert_: str, measure: str = "", interval: str = "60s", timeout: str = "30s",
signal_kind: str = "freshness", published_metric: str = "", metric_kind: str = "gauge",
target: Optional[str] = None}`. `action`/`poll`/`assert_` are opaque strings carried verbatim (P0 does not
execute them). `target` read as `.get("target")`→`None`.

**FR-2 — A `synthetic-probe` SLI emission lane.** Emit the freshness SLO into a distinct
`{svc}-declared-probe-slo.yaml` (a peer of the declared-base/-functional/-span lanes), via a new
`generate_declared_probe_slos` generator. One SLO per declared probe.

**FR-3 — Single-sourced published-metric contract.** The SLI query targets the probe's published metric,
resolved from the `DeclaredProbe`: `published_metric` if declared, else the default `probe_<name>_seconds`.
The query shape is chosen by `metric_kind`: `gauge` → `max(<metric>)`, `histogram` → p99 via the existing
`quantile` shape. This same contract string is what P1's runner will publish (single-sourced, so the SLI
binds by construction once the probe runs).

**FR-4 — Threshold from author, else deferred (reuse #300 D2).** With a `target`, the SLO is graded. With
none, the SLI query is emitted **threshold-deferred** — recorded (not a graded SLO on disk) exactly as
`generate_declared_functional_slos` does (`functional_bound_threshold_deferred`). The SDK never infers a
freshness threshold (NR-1).

**FR-5 — `pending_probes` gap class (NOT a dead SLI).** Because the published metric does not exist until a
runner runs the probe (P1/P2), P0 records each probe in a new `fr_coverage["pending_probes"]` class:
`{service, name, signal_kind, query, published_metric, reason_code: "probe_pending_no_runner"}`. This is a
**positive finding** ("a freshness SLO the subject has no metric for, pending a probe runner"), explicitly
distinct from a #274 dead SLI. `compare.py` surfaces it as its own section (not a divergence/gap-to-fix).

**FR-6 — Accounting + byte-identity.** Add `pending_probes` to the `fr_coverage` dict; surfaced by the
values-based emission gate (#310, already merged). No `declared_probes` ⇒ no probe lane file, no
`pending_probes` key (absent, not `[]`), byte-identical. `compare.py`: a `pending` field on
`ComparisonReport` + `to_dict` + `build_comparison_report` read + a `render_report` "Pending probes"
section (the recurring FR-10 "a new key is dead unless compare consumes it" lesson).

## 3. Non-Requirements (P0)

**NR-1 — No inferred/fabricated freshness threshold.** (Genchi Genbutsu.)
**NR-2 — No runner spec, no runtime, no credentials/secrets.** P0 is static, $0 (P1/P2).
**NR-3 — No `compare-live` (Tier-B) pending-probe verdict.** The live gate's pending-probe verdict class is
P2. P0 touches only the Tier-A `compare` report + `fr_coverage`.
**NR-4 — No probe execution.** `action`/`poll`/`assert` are carried opaque; P0 never runs them.
**NR-5 — Reuse `age`/existing freshness template unchanged** — the probe path is a new binding, not a
change to the convention-freshness path.

## 4. Open Questions

- **OQ-1 — probe `signal_kind`.** Fixed to `freshness` for v1, or allow any recognized kind (a probe could
  measure a synthetic *availability* too)? Lean: allow any, default `freshness` (the pilot case).
- **OQ-2 — SLO vs SLI-only when threshold-deferred.** Same OQ #300 D2 answered (4b): no half-SLO on disk;
  the query travels in the `pending_probes` record. Confirm consistency (a probe with a `target` writes an
  SLO file; without, only the `pending_probes` record). 
- **OQ-3 — ContextCore carry.** `declared_probes` needs a REQ-CCL-style carry (analogous to 107/109). Paired
  ask, to follow; P0 parses the field if present (explicit-only) so it works ahead of the carry.

## 9. Reference Audit

| Symbol / fact | Location | Exists? |
|---|---|---|
| `_functional_sli_query` (gauge_max/quantile shapes) | `artifact_generator_generators.py:1703` | ✅ |
| `_FUNCTIONAL_SLI_TEMPLATES["freshness"]` = age (NOT reused) | `:1054` | ✅ |
| #300 D2 threshold-deferral (`functional_bound_threshold_deferred`) | `:1468` | ✅ (template) |
| values-based `fr_coverage` gate (#310) | `artifact_generator.py` | ✅ (pending key auto-surfaces) |
| `compare.py` consumer (field+build+render) | `compare.py` | ✅ (add `pending`) |
| `_series_slug` / `_resolve_threshold` | `artifact_generator_generators.py` | ✅ |
| `DeclaredProbe` / `declared_probes` / `generate_declared_probe_slos` | — | ❌ to add (FR-1/2) |
| ContextCore `declared_probes` carry | ContextCore (to file) | ⏳ cross-repo |

---

*v0.3.1 — Post planning + lessons + design-principle hardening. 5 assumptions corrected, design-doc OQs
resolved for P0, 6 FRs / 5 NRs / 3 residual OQs. Ready for CRP. No code yet. P1–P3 remain in the design doc.*
