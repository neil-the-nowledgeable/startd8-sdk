# Declared-Series Functional SLI Binding — Requirements

**Version:** 0.3.1 (post planning + lessons + design-principle hardening; ready for CRP)
**Date:** 2026-07-23
**Status:** Draft — spec only, no code
**Owner:** observability artifact generator (`src/startd8/observability/`)
**Branch:** `fix/issue-300-declared-series-promql`
**Refs:** #300 (defect D), #286 (declared-emitted-series binder), #226 (functional SLOs)

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between v0.1 (pre-planning) and v0.2 after a planning
> pass over `artifact_generator_generators.py`. The planning pass revealed the central
> constraint that reshaped the whole feature.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| A declared gauge covering `saturation` can just bind `max(series{…})` and we pick a default target. | `generate_functional_slos` (`:1370`) **requires `fr.target`** — a functional FR with no target is recorded `unfulfilled`, never emitted. There is **no per-kind default-threshold table** anywhere. `_resolve_threshold("saturation", …)` (`:137`) returns `(None, "default")` because `business` has no `saturation` field and no importance default for it. | **The query is determinable; the target is not.** The feature splits into two: bind the grounded *query* always; source the *target* only from author intent. Fabricating a target is out. |
| The threshold could be a sensible per-kind default (e.g. saturation < 0.8). | No basis exists for a saturation/lag/queue_depth threshold — it is entirely domain-specific. The AI-agent kinds' "deferred threshold (OQ-1)" still requires the **author** to supply the value in the FR; deferral ≠ SDK invents it. | Introduce an optional `target` **on the declared series itself** (FR-3). Author-supplied → full graded SLO; absent → grounded-but-threshold-deferred SLI (FR-4). |
| Binding is a change inside `generate_declared_base_slos`. | That function is named/scoped to **base RED**; the functional path has its own generator, doc name (`{svc}-functional-slo.yaml`), naming scheme, and `quality` shape. Folding functional binding into the base function would overload it. | Emit into a **separate** artifact/accounting lane (FR-6), reusing the functional shape helpers, not the base function's body. |
| Any recognized functional kind can bind. | The kind→shape map `_FUNCTIONAL_SLI_TEMPLATES` (`:1042`) pins each kind to a shape that assumes a metric family (`gauge_max`→gauge, `rate`→counter, `age`→timestamp-gauge, `ratio`→counter, `quantile`→histogram). A declared **counter** covering saturation must NOT `gauge_max`. | Gate binding on **declared-type ↔ template-shape compatibility** (FR-5), reusing the #300-C "declared type wins" insight. |

**Resolved open questions:**
- **OQ-a (threshold source) → author-supplied on the series, else threshold-deferred.** No fabrication; no default-threshold table (see FR-3/FR-4, §0.2 Genchi Genbutsu).
- **OQ-b (de-dup) → a functional FR wins over a declared-series binding for the same `(service, signal_kind)`.** The FR is the richer, target-carrying intent (FR-7).
- **OQ-c (generalization) → all `_FUNCTIONAL_SLI_TEMPLATES` kinds, gated by declared-type↔shape compatibility.** Project-scoped AI-agent kinds excluded (they aren't per-service declared series) (FR-5, NR-4).
- **OQ-d (emission/naming/accounting) → a distinct `{svc}-declared-functional-slo.yaml` doc + a new `bound_declared_functional` list; threshold-deferred and type-mismatch cases stay in `deferred_declared_kinds` with a reason_code** (FR-6, FR-8).

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/`. Applied:

- **Phantom-reference audit** — verified every symbol this spec binds to exists on the branch:
  `_FUNCTIONAL_SLI_TEMPLATES` (`:1042`), `_functional_sli_query` (`:1350`), `_select_functional_metric`
  (`:1075`), `_resolve_threshold` (`:137`), `_PROJECT_SCOPED_SIGNAL_KINDS` (`:1070`), `DeclaredEmittedSeries`
  (`artifact_generator_models.py:32`). Added §9 Reference Audit.
- **Single-source vocabulary ownership** — the kind→(candidates, shape, unit) mapping is owned by
  `_FUNCTIONAL_SLI_TEMPLATES`; this spec **cites** it, never restates the shapes. The type↔shape
  compatibility table (FR-5) is *new* vocabulary and must live in exactly one place in code.
- **Overloaded-term co-location** — "declared" already names the base-RED binder's artifact
  (`declared-base-slo.yaml`). The new lane is named `declared-functional` to avoid stacking a second
  meaning onto the base doc/quality keys.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked `docs/design-princples/`. Each changed the draft:

- **Genchi Genbutsu (go and see the real thing)** — the target must bind to *authored intent* or the
  *real* absence of one, never a convention/guess. → No default-threshold table; author supplies the
  target on the series, else the SLO is honestly threshold-deferred (FR-3/FR-4).
- **Hitsuzen (derive the determinable)** — the *query* is fully determined by the declared series name +
  labels + type; the *target* is not. → Derive and emit the query deterministically even when the target
  is absent; never ask an LLM or a default table to conjure the target (FR-2/FR-4).
- **Accidental-Complexity anti-principle** — the v0.1 "per-kind default threshold" would be a growing
  special-case table compensating for the missing author input. → Deleted in favor of one rule: *target
  comes from the author or the SLO is threshold-deferred* (FR-3/FR-4).
- **Mottainai (don't regenerate what exists)** — the declared series already grounds the query; deferring
  it (status quo) discards that. → Bind the query rather than re-deferring; reuse `_functional_sli_query`
  and `_FUNCTIONAL_SLI_TEMPLATES` rather than a parallel shape switch (FR-2/FR-6).

---

## 1. Problem Statement

The observability generator has **two SLI-emitting paths that never cross**:

| Path | Source | Kinds | Threshold | Artifact |
|---|---|---|---|---|
| Declared-base binder (`generate_declared_base_slos`, #286) | `declared_emitted_series` | base RED only (latency/throughput/availability) | manifest / importance default | `{svc}-declared-base-slo.yaml` |
| Functional (`generate_functional_slos`, #226) | `business.functional_requirements` | non-RED (`_FUNCTIONAL_SLI_TEMPLATES`) | the FR's own `target` (required) | `{svc}-functional-slo.yaml` |

After the #300 fix, a `declared_emitted_series` covering a **functional** kind (e.g. `sidekiq_queue_size`
gauge, `covers: [saturation]`) correctly surfaces in `deferred_declared_kinds` with
`reason_code="functional_kind_not_base_red"`. But that series *already grounds a real SLI*
(`max(sidekiq_queue_size{queue_name="default"})`) — the deferral leaves value on the floor.

**The gap:** a declared series that could ground a functional SLI is only ever *deferred*, never *bound*,
because the functional path is FR-driven and the declared-series path is RED-only.

## 2. Requirements

**FR-1 — Recognize declared-series functional coverage.** When a `declared_emitted_series` `covers` a
kind in `_FUNCTIONAL_SLI_TEMPLATES` (non-RED, non-project-scoped), treat it as a *candidate* functional
binding rather than an automatic deferral.

**FR-2 — Bind the grounded query deterministically.** For a candidate, emit the functional SLI query from
the **declared series name** + its labels selector + the template's shape — via the existing
`_functional_sli_query(shape, s.name, selector)`. The query is always determinable and must be emitted
(as an SLO or a threshold-deferred SLI per FR-3/FR-4). Do **not** substitute the template's candidate
metric name; the declared series name is the ground truth (mirrors #286 FR-6a).

**FR-3 — Target from author intent only.** Add an optional `target` field to `DeclaredEmittedSeries`. When
present, it is the SLO objective (analogous to `fr.target`). The SDK **must not** synthesize a target for
a functional kind from any default table.

**FR-4 — Threshold-deferred when no target.** When a candidate has no `target`, emit the SLI query but
record the binding as **threshold-deferred**: either (a) an SLO doc with the objective omitted/flagged, or
(b) retained in `deferred_declared_kinds` with `reason_code="functional_bound_threshold_deferred"` **and**
the grounded query included in the record so a downstream surface (compare/dashboard) can still use it.
[Decision point for CRP — see OQ-5.] The value that must not be lost is the *grounded query*.

**FR-5 — Type↔shape compatibility gate.** Bind only when the declared `type` is compatible with the
kind's template shape: `gauge_max`↔gauge, `rate`↔counter, `ratio`↔counter, `age`↔gauge, `quantile`↔
histogram. On mismatch (e.g. a counter covering saturation), do not bind — defer with
`reason_code="functional_type_shape_mismatch"` naming both the declared type and the required shape.

**FR-6 — Separate emission lane.** Emit declared-series functional SLOs into a distinct artifact
(`{svc}-declared-functional-slo.yaml`) — not folded into `generate_declared_base_slos`'s base doc. Reuse
the functional shape helpers; do not fork the shape switch.

**FR-7 — FR precedence (de-dup).** If `business.functional_requirements` contains an FR covering the same
`(service, signal_kind)`, the FR wins and the declared-series binding for that kind is **skipped** (not
double-emitted). Record the skip so it is observable (not silent).

**FR-8 — Coverage accounting.** Add a `bound_declared_functional` list to `fr_coverage` (parallel to
`bound_declared_series`), each entry `{service, kind, series, query, threshold: "authored"|"deferred"}`.
Threshold-deferred and type-mismatch candidates remain in `deferred_declared_kinds` with their
reason_code (FR-4/FR-5).

**FR-9 — Byte-identical when absent.** A metadata surface with no functional-covering declared series
produces exactly today's output (no new file, no new `fr_coverage` key values) — additive only.

## 3. Non-Requirements

**NR-1 — No default/importance-scaled thresholds for functional kinds.** The SDK never invents a
saturation/lag/queue_depth target. (Genchi Genbutsu.)

**NR-2 — No new shapes.** Reuse `_FUNCTIONAL_SLI_TEMPLATES` shapes; this feature adds no PromQL shape.

**NR-3 — Base RED unchanged.** `generate_declared_base_slos` behavior for latency/throughput/availability
is untouched (the #300 fixes stand).

**NR-4 — Project-scoped AI-agent kinds excluded.** `llm_cost_per_request`/`token_throughput`/
`context_saturation` are model/project-labeled, not per-service declared series — out of scope.

**NR-5 — No change to the functional-FR path.** `generate_functional_slos` is not modified; FR precedence
(FR-7) is enforced on the declared side by consulting the FR list read-only.

## 4. Open Questions

- **OQ-5 — Threshold-deferred artifact shape (FR-4a vs 4b).** Emit a target-less/annotated SLO doc, or keep
  it as an enriched `deferred_declared_kinds` record carrying the query? Leaning **4b** (no half-formed
  SLO on disk; the query travels in the gap record). CRP to confirm.
- **OQ-6 — Should `target` on the series also be honored for base RED kinds?** Today base RED targets come
  from the manifest/importance default. Allowing a per-series target for latency could be a nice
  unification but expands scope — default **no** (keep base RED sourcing as-is), revisit later.
- **OQ-7 — Alert emission for threshold-deferred SLIs.** An SLI with no objective can't have a burn-rate
  alert. Confirm we emit the SLI/recording query only, no alert, until a target exists.

## 9. Reference Audit

| Symbol cited | Location | Exists? |
|---|---|---|
| `_FUNCTIONAL_SLI_TEMPLATES` | `artifact_generator_generators.py:1042` | ✅ |
| `_functional_sli_query` | `:1350` | ✅ |
| `_select_functional_metric` | `:1075` | ✅ (bypassed by FR-2) |
| `_resolve_threshold` | `:137` (returns `(None, …)` for saturation) | ✅ |
| `_PROJECT_SCOPED_SIGNAL_KINDS` | `:1070` | ✅ |
| `generate_declared_base_slos` | `:1200`-ish | ✅ |
| `generate_functional_slos` | `:1370` | ✅ |
| `DeclaredEmittedSeries` (add `target`) | `artifact_generator_models.py:32` | ✅ (field to add) |
| `deferred_declared_kinds` aggregation | `artifact_generator.py:583` | ✅ |

---

*v0.3.1 — Post planning + lessons + design-principle hardening. 5 assumptions corrected (all 4 OQs
resolved), 9 FRs / 5 NRs / 3 residual OQs. Ready for CRP. No code yet.*
