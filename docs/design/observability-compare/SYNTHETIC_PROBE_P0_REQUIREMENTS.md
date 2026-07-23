# Synthetic-Probe SLI — P0 (declaration + static freshness SLO, $0) — Requirements

**Version:** 0.4 (post CRP Round 1 — 10 suggestions + adversarial, all applied; ready to implement)
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
execute them). `target` read as `.get("target")`→`None`. **`metric_kind` is a closed enum
`gauge|histogram`** — any other value defers with a reason_code (FR-5), never a fabricated query
(`_functional_sli_query`'s final branch returns a raw un-shaped fallback for unknown shapes). **`signal_kind`
is `freshness` for v1** — a probe declaring any other kind defers with a reason_code (no query shape is
defined for a synthetic *availability*/etc. probe in P0) *(R1-F5, R1-F7; OQ-1 resolved)*.

**FR-2 — No SLO YAML on disk in P0 (critical) — the derived SLO lives in the `pending_probes` record.**
P0 does **not** write a `{svc}-declared-probe-slo.yaml` (or any `slos/*.yaml`) for a declared probe — for
EITHER the graded (`target`) or the deferred case. `validate_promql.extract_exprs` walks `slos/*.yaml`
file-by-file and is not `fr_coverage`-aware, so any probe SLO on disk querying a not-yet-published metric
would be replayed and **red-flagged as a #274 dead SLI** — the exact opposite of the intended positive
finding. The `generate_declared_probe_slos` generator therefore emits **no file** (`status="skipped"`,
empty content) and records the full SLO shape (query, target-or-deferred, published_metric) in the
`pending_probes` accounting (FR-5). The on-disk SLO file is written by **P1/P2**, once a runner can populate
the metric *(R1-F1)*.

**FR-3 — Single-sourced, service-scoped published-metric contract.** The SLI query targets the probe's
published metric, resolved from the `DeclaredProbe`: `published_metric` if declared, else the default
`probe_<name>_seconds`. The query MUST carry a `{service="<svc>"}` (or `{probe="<name>"}`) selector so two
services' probes sharing a `name` do not silently bind one unselected series; if two probes on the same
service share a `name`, `published_metric` is required (else defer). The query shape is chosen by
`metric_kind`: `gauge` → `max(<metric>{selector})`; `histogram` → the `quantile` shape, which appends
`_bucket` — so **P1's runner MUST publish a `<published_metric>_bucket` histogram family** for a histogram
probe (stated here so the single-sourcing holds by construction, not silently for a bare gauge name)
*(R1-F3, R1-F4)*.

**FR-4 — Threshold from author, else deferred (reuse #300 D2) — both live in `pending_probes`.** A probe
with a `target` carries it in its `pending_probes` record (`target` field); a probe without one is recorded
threshold-deferred (`threshold_deferred: true`), exactly as `generate_declared_functional_slos`. Neither
writes an SLO file in P0 (FR-2). The SDK never infers a freshness threshold (NR-1).

**FR-5 — `pending_probes` accounting class (a positive finding, NOT a dead SLI).** P0 records each declared
probe in a new `fr_coverage["pending_probes"]` class:
`{service, name, signal_kind, query, published_metric, metric_kind, target?, threshold_deferred?,
reason_code}` — `reason_code="probe_pending_no_runner"` for a bindable probe; a distinct reason_code for an
unsupported `metric_kind`/`signal_kind` (FR-1) that emits no query. This is a **positive finding** ("a
freshness SLO the subject has no metric for, pending a probe runner"), explicitly distinct from a #274 dead
SLI, and does **not** count toward `total_gaps` (it is not a `_GAP_CLASSES` divergence).

**FR-6 — Accounting, `compare.py` surface, and byte-identity.** Add `pending_probes` to the `fr_coverage`
dict (surfaced by the values-based emission gate, #310). `compare.py`: a `pending` field on
`ComparisonReport` + its `_count` in `to_dict` + a `build_comparison_report` read + a **dedicated
`render_report` "Pending probes" section placed with the positive (bound) sections, NOT inside the
"Divergence" block** (which reads "where the derived artifacts can't be grounded") and not incrementing
`total_gaps` *(R1-F10)*. **Byte-identity (testable):** no `declared_probes` ⇒ no `pending_probes` key at all
(absent, not `[]` — guarded like the other lanes' `if _bound_declared_*:`), no probe file, manifest
byte-identical to a pre-feature golden *(R1-F6)*. **Forward-note (debt, not P0 work):** this is the FOURTH
positive-finding field on `ComparisonReport` (`bound`/`bound_functional`/`bound_span`/`pending`); a unified
positive-findings shape is deferred (echoing #307 R1-F10) — revisit at the 5th lane, do NOT unify in P0
*(R1-F8)*.

**FR-7 — End-to-end $0 acceptance (the positive-finding claim, made testable).** A run declaring one probe
with NO target and NO runner produces a `pending_probes` entry with a determinable `query` +
`published_metric`, a non-empty "Pending probes" section in `render_report`, **zero LLM/$ cost, and no
`slos/` file** — proving P0 stands alone and delivers the "derived SLO Mastodon has no metric for" finding
statically *(R1-F9)*.

## 3. Non-Requirements (P0)

**NR-1 — No inferred/fabricated freshness threshold.** (Genchi Genbutsu.)
**NR-2 — No runner spec, no runtime, no credentials/secrets.** P0 is static, $0 (P1/P2).
**NR-3 — No `compare-live` (Tier-B) pending-probe verdict.** The live gate's pending-probe verdict class is
P2. P0 touches only the Tier-A `compare` report + `fr_coverage`. **Cross-ref (R1-F2):** because P0 writes no
SLO file (FR-2), no probe query reaches `validate_promql`/`compare-live`; when **P1** first writes a probe
SLO to disk it MUST add a probe-lane exclusion (filename/`fr_coverage`-aware) to the dead-SLI denominator —
a stated **P1 dependency**, not a latent regression to discover.
**NR-4 — No probe execution.** `action`/`poll`/`assert` are carried opaque; P0 never runs them.
**NR-5 — Reuse `age`/existing freshness template unchanged** — the probe path is a new binding, not a
change to the convention-freshness path.

## 4. Open Questions

- **OQ-1 — RESOLVED (R1-F7) → `freshness` only in v1.** A probe declaring another `signal_kind` defers with a
  reason_code (no query shape defined for non-freshness synthetic probes in P0); revisit when a second kind
  has a defined shape.
- **OQ-2 — RESOLVED (R1-F1) → no SLO file in P0 for EITHER case.** Both graded and deferred probes live in
  `pending_probes`; the file is a P1 artifact (supersedes the earlier "a target writes an SLO file" lean,
  which created the validate_promql leak).
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

*v0.4 — Post CRP Round 1 (10 F-suggestions + adversarial, all ACCEPTED; dispositions in Appendix A). The
load-bearing change: P0 writes NO SLO file (R1-F1) — the derived SLO lives entirely in `pending_probes`,
closing the validate_promql dead-SLI leak. Plus service-scoped metric + `_bucket` histogram obligation
(FR-3), `metric_kind`/`signal_kind` enums (FR-1/5), render placement + byte-identity + $0 acceptance
(FR-6/7). 7 FRs / 5 NRs / 1 residual OQ (cross-repo carry). Ready to implement. P1–P3 remain in the design doc.*

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
| R1-F1 | **Critical:** P0 must NOT write a probe SLO YAML (graded or deferred) — validate_promql is file-based → dead-SLI leak | CRP R1 | Applied → FR-2 rewritten (no file, all in `pending_probes`); OQ-2 resolved | 2026-07-23 |
| R1-F2 | Belt-and-suspenders: validate_promql/compare-live probe-lane exclusion when a file IS written | CRP R1 | Applied → NR-3 cross-ref as a stated **P1 dependency** (P0 writes no file, so no leak) | 2026-07-23 |
| R1-F3 | Default `probe_<name>_seconds` needs a service selector + collision handling | CRP R1 | Applied → FR-3 (service-scoped selector; `published_metric` required on same-service name clash) | 2026-07-23 |
| R1-F4 | `metric_kind:histogram` → `quantile` shape appends `_bucket` → runner must publish `_bucket` family | CRP R1 | Applied → FR-3 (stated the `_bucket` obligation) | 2026-07-23 |
| R1-F5 | Constrain `metric_kind` to `gauge\|histogram`; unknown defers with reason_code | CRP R1 | Applied → FR-1 (enum) + FR-5 (defer, no fabricated query) | 2026-07-23 |
| R1-F6 | Byte-identity needs a testable criterion (no `pending_probes: []` key) | CRP R1 | Applied → FR-6 | 2026-07-23 |
| R1-F7 | Resolve OQ-1: non-`freshness` `signal_kind` has no shape → v1 = freshness only, else defer | CRP R1 | Applied → FR-1 + OQ-1 resolved | 2026-07-23 |
| R1-F8 | Note the 4th positive-finding lane as tracked debt (don't unify in P0) | CRP R1 | Applied → FR-6 forward-note | 2026-07-23 |
| R1-F9 | Add an end-to-end $0 acceptance for the positive-finding claim | CRP R1 | Applied → new FR-7 | 2026-07-23 |
| R1-F10 | `render_report` places "Pending probes" as its own positive section, not under Divergence; no `total_gaps` | CRP R1 | Applied → FR-5 + FR-6 | 2026-07-23 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-23

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-07-23 23:54:54 UTC
- **Scope**: Requirements-only review of Synthetic-Probe SLI P0, code-grounded against the shipped
  #286/#300/#307/#310 binders in `src/startd8/observability/` (generators, `compare.py`,
  `validate_promql.py`, models, context parser). Weighted per `.crp-focus-probe-p0.md`.

##### Sponsor asks (answered first, per focus file)

**Ask 1 — FR-5 `pending_probes` vs dead-SLI distinction; graded-case leak.**
- **Summary answer:** Partial / NO — the distinction is enforced for the Tier-A `compare` report, but
  the graded case (FR-4 with a `target`) DOES leak into the Tier-B dead-SLI classifier.
- **Rationale:** `validate_promql.extract_exprs` (`validate_promql.py:228`) walks `slos/*.yaml`
  **file-by-file** and pulls every `query`/`expr` (`_iter_exprs_in_obj:119`); it is NOT
  `fr_coverage`-aware and has no probe-file exclusion (`_EXCLUDED_ARTIFACT_DIRS:274` excludes by
  *subdir*, not filename, and does not include `slos/`). So when FR-4's graded branch writes
  `{svc}-declared-probe-slo.yaml` with a query on `probe_<name>_seconds` (which does not exist until
  P1's runner runs, FR-5), a `compare-live`/`validate-promql` run replays it and it returns empty →
  `detect_target_drift` (`:300`) red-flags it as a #274-class dead SLI. NR-3 defers the pending-probe
  *verdict class*, but not the file-walk exposure of a written SLO doc. The `pending_probes`
  `fr_coverage` record protects the static `compare` report only — not a YAML on disk.
- **Assumptions / conditions:** holds whenever a probe carries a `target` and a Tier-B replay runs
  before P1 populates the metric.
- **Suggested improvements:** see R1-F1 (do not write the graded SLO to disk in P0; keep the query in
  the `pending_probes` record even when a target exists) and R1-F2 (belt-and-suspenders exclusion in
  validate_promql). This is the single highest-risk gap in the spec.

**Ask 2 — FR-3 published-metric single-sourcing / default robustness.**
- **Summary answer:** Depends — the single-source-on-the-model shape is right, but the default
  `probe_<name>_seconds` is under-specified on collision, labels, and unit.
- **Rationale:** #307 FR-3 put the series identity on a descriptor **profile**; here it defaults to a
  bare string derived from `name`. Two probes with the same `name` across services collide silently,
  and the query carries no `{service=...}` selector (unlike declared-functional, which threads a
  `_declared_series_selector`). `metric_kind: histogram` must map to the `quantile` shape, which in
  `_functional_sli_query` (`:1713`) appends `_bucket` to the metric — the spec's FR-3 text
  (`p99 via the existing quantile shape`) does not state that the runner must therefore publish a
  `_bucket` histogram family, not `probe_<name>_seconds` directly. See R1-F3, R1-F4, R1-F5.
- **Assumptions / conditions:** none.

**Ask 3 — FR-1 `DeclaredProbe` shape / `assert_` / P0→P1 breaking-change risk.**
- **Summary answer:** Mostly right; `assert_`/`action`/`poll` as opaque strings are fine for P0, but
  two forward-compat hazards are unstated. See R1-F6, R1-F7.

**Ask 4 — FR-6 fourth positive-finding lane / unification.**
- **Summary answer:** Partial — the accumulation is real (`bound`/`bound_functional`/`bound_span`/now
  `pending`) but P0 need not unify; flag it as debt. See R1-F8.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | critical | Make FR-4's graded case NOT write an SLO YAML to `slos/` in P0. State that a probe with a `target` records its query + target in the `pending_probes` record (with a `target` field) exactly like the deferred case — no `{svc}-declared-probe-slo.yaml` is written until P1 can populate the metric. FR-2 ("Emit the freshness SLO into a distinct `{svc}-declared-probe-slo.yaml`") and FR-4 ("With a `target`, the SLO is graded [and emitted]") currently mandate writing a file whose query is dead until P1. | `validate_promql.extract_exprs` is file-based (`:228`), not `fr_coverage`-aware; ANY SLO YAML under `slos/` is replayed and a `probe_<name>_seconds` query returns empty → flagged dead (#274 class), the exact opposite of the "positive finding" intent. OQ-2 raises the "probe with a target writes an SLO file" branch but never resolves the leak it creates. | §2 FR-2/FR-4; §4 OQ-2 | Add an acceptance test: generate with a probe carrying `target`, assert `slos/` contains NO `*-declared-probe-slo.yaml` and the query lives in `fr_coverage["pending_probes"][…]["query"]`. |
| R1-F2 | Ops | high | Add a belt-and-suspenders defense to the spec: even if a probe SLO file is ever written, `validate_promql`/`compare-live` must exclude probe-lane files from the dead-SLI denominator (e.g. filename `*-declared-probe-slo.yaml` recognized as pending, or the runner's metric marked "expected-absent"). Note this as a P0 requirement OR an explicit P1/P2 dependency risk if deferred. | Relying solely on "don't write the file" (R1-F1) is a single point of failure; the classifier has no probe awareness today (`_EXCLUDED_ARTIFACT_DIRS:274` is subdir-scoped). Even if NR-3 defers the Tier-B *verdict*, the file-walk exposure is a latent regression the moment any probe SLO reaches disk. | §3 NR-3 (add a cross-ref); new §2 note or §4 OQ | Unit test: drop a probe SLO YAML into `slos/`, run `extract_exprs`, assert its query is excluded/marked pending, not counted as a binding miss. |
| R1-F3 | Interfaces | high | Specify how the FR-3 default `probe_<name>_seconds` is dimensioned/selected. State whether the P0 SLI query carries a `{service=...}` (or `{probe=...}`) selector, and how name collisions across probes/services are prevented (e.g. require `published_metric` when >1 probe shares a `name`, or fold `service` into the default). | Declared-functional threads `_declared_series_selector(s.labels)` into every query (`:1462`); the probe lane as specced emits a bare `max(probe_<name>_seconds)` with no selector, so two services' probes with the same `name` bind to one unselected series. This is a silent mis-binding, not a compile error. | §2 FR-3 | Test two services each declaring a probe named `fanout`; assert the two emitted queries are distinguishable (distinct metric or distinct selector). |
| R1-F4 | Interfaces | high | State the `metric_kind: histogram` → query-shape contract explicitly: the `quantile` shape in `_functional_sli_query` appends `_bucket` to the metric (`:1713`), so P1's runner must publish `probe_<name>_seconds_bucket` (a histogram family), NOT a bare `probe_<name>_seconds` gauge. FR-3 says "p99 via the existing `quantile` shape" without surfacing the `_bucket` naming obligation the single-sourcing depends on. | If the runner publishes `probe_<name>_seconds` but the SLI queries `probe_<name>_seconds_bucket`, the "single-sourced so it binds by construction" guarantee (FR-3) fails silently for every histogram probe. | §2 FR-3 | Assert the emitted histogram query targets `<published_metric>_bucket` and document the runner's publish name accordingly. |
| R1-F5 | Data | medium | Constrain `metric_kind` to a closed enum (`gauge`\|`histogram`) and specify P0 behavior on an unrecognized value — deferred with a reason_code (mirroring `unknown_kind` in `generate_declared_functional_slos:1423`), never a fabricated/empty query. FR-1 types it as a bare `str` defaulting `"gauge"`. | `_functional_sli_query`'s final branch returns `f"{metric}{selector}"` (a raw, un-shaped fallback) for any unknown shape (`:1720`); an unvalidated `metric_kind` would ship a malformed SLI rather than defer. | §2 FR-1, FR-3 | Test `metric_kind: "counter"` (unsupported) → recorded in a gap class with a reason_code, no SLO/SLI emitted. |
| R1-F6 | Interfaces | medium | Add an acceptance criterion for the FR-1 byte-identity claim ("absent→omitted byte-identical") matching the shipped discipline: no `declared_probes` ⇒ no `pending_probes` key at all (absent, not `[]`), no probe lane file, and the manifest is byte-identical to a pre-feature golden. FR-6 states this in prose but no FR gives it a testable criterion. | The shipped lanes each guard this explicitly (`if _bound_declared_functional:` at `artifact_generator.py:691`; FR-9 in #300/#307). Without a stated criterion the emission gate could regress to emitting `pending_probes: []`, a new manifest byte. | §2 FR-6 | Golden test: a manifest with zero probes is byte-identical pre/post feature; grep the manifest for `pending_probes` → absent. |
| R1-F7 | Risks | medium | Resolve OQ-1 in the spec body (not just "lean"): if `signal_kind` may be any recognized kind (not fixed to `freshness`), state which kinds P0 will actually emit a query shape for, and that an unsupported `signal_kind` defers rather than emitting a freshness query by default. As written, `signal_kind` defaults to `freshness` but FR-3 only describes a freshness/gauge/histogram query — an `availability` probe (OQ-1's own example) has no specified shape. | Leaving OQ-1 open while defaulting to `freshness` invites a P1 breaking change the moment a second `signal_kind` is added; the query-shape mapping for non-freshness kinds is undefined. | §4 OQ-1; §2 FR-3 | Test a probe with `signal_kind: availability` and assert defined behavior (deferred-with-reason or a specified query), not an accidental freshness query. |
| R1-F8 | Architecture | low | Note the fourth-lane accumulation as explicit, tracked debt rather than unifying now. `ComparisonReport` will carry `bound`/`bound_functional`/`bound_span`/`pending` (4 positive-finding fields + their `_count` mirrors in `to_dict`, `compare.py:54`). Add a one-line forward-note that a unified positive-findings shape is deferred (echoing the #307 R1-F10 single-authority concern) so the next lane doesn't compound it silently. | Each new lane duplicates the field+build+render+to_dict pattern (`compare.py:45-134`); this is manageable at 4 but the spec should acknowledge the seam so unification is a deliberate future decision, not drift. Do NOT unify in P0 (accidental-complexity anti-principle, §0.2). | §2 FR-6 (add a forward-note); §4 as a new OQ | N/A (documentation note); revisit at the 5th lane. |
| R1-F9 | Validation | medium | Add an explicit acceptance criterion that P0 stands alone with NO runtime and still delivers a "positive finding" — i.e. a run with a declared probe and NO runner produces a `pending_probes` entry with a determinable `query` and `published_metric`, and `compare render_report` shows a "Pending probes" section, all at $0. This makes the §1 / focus-Ask-5 "honest positive finding for a static artifact" claim testable. | The whole P0 value claim ("a derived SLO Mastodon has no metric for is a positive finding") is currently asserted in prose (§1) with no end-to-end acceptance test tying declaration → pending_probes → compare surface. | §1; §2 FR-5/FR-6 | End-to-end test: declare one probe, no target, no runner; assert the `pending_probes` record + a non-empty "Pending probes" render section; assert zero LLM/$ cost. |
| R1-F10 | Interfaces | low | Specify `render_report` placement and label for the new "Pending probes" section relative to the existing positive (bound) sections and the divergence block — it is neither a `bound_*` grounding nor a `_GAP_CLASSES` divergence. State it renders as its own positive-but-pending section (not inside "Divergence", which reads "where the derived artifacts can't be grounded", `compare.py:141`). | If mis-placed under the gap/divergence block a reader sees a "positive finding" framed as a failure — inverting FR-5's intent. The render ordering in `render_report` (`:115`) is explicit for the other three lanes; the pending lane needs the same specification. | §2 FR-6 | Assert the rendered report places "Pending probes" outside the "Divergence:" section and does not increment `total_gaps`. |

