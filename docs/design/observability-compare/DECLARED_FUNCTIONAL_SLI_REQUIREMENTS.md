# Declared-Series Functional SLI Binding — Requirements

**Version:** 0.4 (post CRP Round 1 — 10 suggestions + adversarial, all applied; ready to implement)
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
binding rather than an automatic deferral. **Candidacy is evaluated per `(series, covered-kind)`** — a
series with `covers: [saturation, queue_depth]` yields two independent candidates, each separately gated
by FR-5 (type↔shape) and FR-7 (precedence). *(R1 adversarial)*

**FR-2 — Bind the grounded query deterministically.** For a candidate, emit the functional SLI query from
the **declared series name** + its labels selector + the template's shape — via the existing
`_functional_sli_query(shape, s.name, selector)`. The query is always determinable and must be emitted
(as an SLO or a threshold-deferred SLI per FR-3/FR-4). Do **not** substitute the template's candidate
metric name; the declared series name is the ground truth (mirrors #286 FR-6a).

**FR-3 — Target from author intent only.** Add an optional field **`target: Optional[str] = None`** to
`DeclaredEmittedSeries`, matching the name, type, and semantics of `FunctionalRequirement.target`
(`artifact_generator_models.py:121`) — a raw PromQL/objective **string**, not a float. When present it is
the SLO objective (analogous to `fr.target`). The SDK **must not** synthesize a target for a functional
kind from any default table. *(R1-F3)*

**FR-4 — Threshold-deferred when no target (resolved: 4b).** When a candidate has no `target`, emit the
grounded SLI query but **write NO SLO YAML to disk** for it (a null-`spec.target` OpenSLO doc is malformed
and breaks `compare-live` replay). Instead retain it in `deferred_declared_kinds` as an enriched record
with the exact keys `{service, kind, series, query, threshold_deferred: true,
reason_code: "functional_bound_threshold_deferred"}`. The `query` field is mandatory and non-empty — it
is the value that must not be lost. *(R1-F1; OQ-5 resolved)*

**FR-5 — Type↔shape compatibility gate.** Evaluated per `(series, covered-kind)`. Bind only when the
declared `type` is compatible with the kind's template shape: `gauge_max`↔gauge, `rate`↔counter,
`ratio`↔counter, `age`↔gauge. On mismatch (e.g. a counter covering saturation), do not bind — defer with
`reason_code="functional_type_shape_mismatch"` naming both the declared type and the required shape.
`quantile`↔histogram is **reserved/forward-compat only**: no in-scope (non-project-scoped) functional kind
in `_FUNCTIONAL_SLI_TEMPLATES` uses the `quantile` shape today, so that path cannot fire under NR-4 — it is
listed for completeness, not as a live binding path. *(R1-F9)*

**FR-6 — Separate emission lane.** Emit declared-series functional SLOs into a distinct artifact
(`{svc}-declared-functional-slo.yaml`) — not folded into `generate_declared_base_slos`'s base doc. Reuse
the functional shape helpers; do not fork the shape switch.

**FR-7 — FR precedence (de-dup).** If `business.functional_requirements` contains an FR covering the same
`(service, signal_kind)`, the FR wins and the declared-series binding for that kind is **skipped** (not
double-emitted). The service-match predicate MUST reuse `generate_functional_slos`'s own filter —
`f.service in (None, "", service_id)` — so a **global** FR (`service=None`) covering the kind also
suppresses the declared binding, rather than a strict equality key that would miss it and double-emit.
The skip is recorded in `deferred_declared_kinds` with
`reason_code="functional_fr_precedence_skip"` and the **winning FR id**, so precedence is traceable in the
single gap channel `compare.py` already renders. *(R1-F7, R1-F8)*

**FR-8 — Coverage accounting.** Add a `bound_declared_functional` list to `fr_coverage` (parallel to
`bound_declared_series`), each entry `{service, kind, series, query, threshold: "authored"}` (only fully
bound, author-targeted SLOs land here). Threshold-deferred (FR-4), type-mismatch (FR-5), and
precedence-skip (FR-7) candidates remain in `deferred_declared_kinds` with their reason_code.

**FR-9 — Byte-identical when absent.** A metadata surface with no functional-covering declared series
produces exactly today's output — additive only. Concretely: **no `{svc}-declared-functional-slo.yaml`
file is written, and `fr_coverage` gains no `bound_declared_functional` key at all** (the key is *absent*,
not an empty list — an empty list is itself a manifest byte-diff that breaks golden fixtures). The parse
layer reads the new field as `s.get("target")` — yielding `None` when the key is absent, **not** `str(...)`
coercion to `""` — so an absent `target` is indistinguishable from a pre-feature series. *(R1-F4, R1-F10)*

**FR-10 — `compare.py` consumer contract (the key must not be dead).** The new `fr_coverage` key and the
threshold-deferred query are inert unless `compare.py` consumes them. This FR is normative:
`build_comparison_report` (`compare.py:67`) MUST read `bound_declared_functional` (parallel to
`bound_declared_series`) into the report, `render_report` MUST present it, and `_entry_line` MUST surface
the grounded `query` (and the `threshold_deferred` state) for a `functional_bound_threshold_deferred`
entry — not just `kind → series`. Without this, FR-4's protected query is dropped at render and FR-8's key
is invisible to dashboards. *(R1-F2, R1-F5)*

**FR-11 — `compare-live` baseline update is part of the change.** A newly bound functional SLI is replayed
by `compare-live` and appears as a new verdict id; against an existing committed baseline it would red-flag
as unexpected drift on first run. Any fixture that gains a bound functional SLI MUST have its
`compare_live_baseline.json` re-authored (via `--write-baseline`) in the same change, and this step is a
documented acceptance criterion — not an incidental follow-up. *(R1-F6)*

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

- **OQ-5 — RESOLVED (CRP R1-F1) → 4b.** No SLO YAML on disk for a threshold-deferred candidate; the
  grounded query travels in an enriched `deferred_declared_kinds` record (see FR-4). A null-`spec.target`
  OpenSLO doc (4a) is malformed and breaks `compare-live` replay.
- **OQ-6 — Should `target` on the series also be honored for base RED kinds?** Today base RED targets come
  from the manifest/importance default. Allowing a per-series target for latency could be a nice
  unification but expands scope — default **no** (keep base RED sourcing as-is), revisit later.
- **OQ-7 — Alert emission for threshold-deferred SLIs.** An SLI with no objective can't have a burn-rate
  alert. Confirmed: emit the grounded SLI/recording query only, **no alert**, until a target exists (a
  fully-bound FR-8 SLO emits an alert as functional SLOs do today).

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
| `FunctionalRequirement.target` (name/type to mirror) | `artifact_generator_models.py:121` | ✅ (`Optional[str]`) |
| `deferred_declared_kinds` aggregation | `artifact_generator.py:583` | ✅ |
| `compare.py:build_comparison_report` (FR-10 consumer) | `compare.py:67` | ✅ (fixed key set — must extend) |
| `compare.py:_entry_line` (FR-10 render) | `compare.py` | ✅ (reads kind/series/reason — must add query) |

---

*v0.4 — Post CRP Round 1 (10 F-suggestions + adversarial, all ACCEPTED). OQ-5 resolved to 4b; 2 FRs added
(FR-10 compare.py consumer contract, FR-11 baseline update); FR-3/4/5/7/8/9 tightened. 11 FRs / 5 NRs /
2 residual OQs. Ready to implement. No code yet.*

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
| R1-F1 | Resolve OQ-5 to 4b; pin the enriched deferred-record schema; forbid on-disk half-SLO | CRP R1 | Applied → FR-4 rewritten (no SLO YAML; exact keys incl. mandatory non-empty `query`); OQ-5 marked resolved | 2026-07-23 |
| R1-F2 | `compare.py:_entry_line` must surface the grounded query for threshold-deferred entries | CRP R1 | Applied → folded into new FR-10 (render contract) | 2026-07-23 |
| R1-F3 | Name field `target: Optional[str] = None`, mirror `FunctionalRequirement.target`, string not float | CRP R1 | Applied → FR-3 + Reference Audit row | 2026-07-23 |
| R1-F4 | Parse `target` as `s.get("target")` → `None` when absent, not `str(...)`→`""` | CRP R1 | Applied → FR-9 parse-contract sentence | 2026-07-23 |
| R1-F5 | `build_comparison_report` must read `bound_declared_functional` or the key is dead | CRP R1 | Applied → new FR-10 (consumer contract) | 2026-07-23 |
| R1-F6 | New bound SLIs mint new `compare-live` verdict ids → require baseline re-author step | CRP R1 | Applied → new FR-11 | 2026-07-23 |
| R1-F7 | FR-7 de-dup must reuse `f.service in (None,"",svc)` so global FRs suppress | CRP R1 | Applied → FR-7 predicate specified | 2026-07-23 |
| R1-F8 | FR-7 skip channel: `deferred_declared_kinds` + `reason_code=functional_fr_precedence_skip` + winning FR id | CRP R1 | Applied → FR-7 + FR-8 | 2026-07-23 |
| R1-F9 | `quantile↔histogram` is inert for in-scope kinds — mark reserved/forward-compat | CRP R1 | Applied → FR-5 note | 2026-07-23 |
| R1-F10 | FR-9 must forbid empty-list `bound_declared_functional` key (absent, not `[]`) for byte-identity | CRP R1 | Applied → FR-9 | 2026-07-23 |
| R1-adv | Multi-kind `covers` → evaluate per `(series, covered-kind)` | CRP R1 adversarial | Applied → FR-1 + FR-5 | 2026-07-23 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-23

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-23 21:05:00 UTC
- **Scope**: Single-document requirements review of the Declared-Series Functional SLI Binding spec (v0.3.1). Weighted per `.crp-focus-declared-functional.md` on the four numbered concerns (OQ-5 artifact shape, `target` on `DeclaredEmittedSeries`, the new artifact lane + `fr_coverage` key, FR-7 de-dup). Grounded against `artifact_generator_generators.py`, `artifact_generator_models.py`, `artifact_generator_context.py`, and `compare.py` on the branch.

**Focus-file numbered concerns (addressed first, per prompt):**

**Concern 1 — OQ-5 threshold-deferred artifact shape (4a on-disk SLO vs 4b enriched gap record).**
- **Summary answer:** Adopt **4b** (the spec's lean) as the *default*, but the spec must explicitly forbid a half-formed SLO on disk AND define the exact enriched-record schema, because "4b" as written is under-specified for the very consumers OQ-5 names.
- **Rationale:** `compare.py:_entry_line` renders a declared deferred entry as `kind → series` and silently drops any `query`/`threshold`/`reason_code` fields (verified: it only reads `entry['kind']`, `entry['series']`, `enabling_flag`, `reason`). So under 4b the grounded query FR-4 says "must not be lost" is *parsed-and-dropped at render time* — the value still lands on the floor, just one layer later. 4b only works if `_entry_line` is extended to surface `query`. 4a (on-disk SLO with objective omitted) would fail OpenSLO schema validation (`spec.target` is required in the `openslo/v1` SLO shape emitted by `generate_functional_slos`), breaking `compare-live` replay — a decisive point *for* 4b.
- **Assumptions / conditions:** `compare-live` replay treats the `{svc}-declared-functional-slo.yaml` lane as OpenSLO-validated; the enriched gap record is machine-readable (has stable keys).
- **Suggested improvements:** see R1-F1 (forbid on-disk half-SLO; pin the 4b record schema) and R1-F2 (extend `_entry_line`/render contract).

**Concern 2 — new optional `target` on `DeclaredEmittedSeries`.**
- **Summary answer:** Sound, but the spec must (a) name the field to mirror the existing `FunctionalRequirement.target: Optional[str]` and (b) state the parse + back-compat contract explicitly.
- **Rationale:** `FunctionalRequirement` already carries `target: Optional[str] = None` (`artifact_generator_models.py:121`); reusing that exact name/type/semantics keeps the two intent-sources congruent and avoids a second threshold vocabulary. `_parse_declared_series` (`artifact_generator_context.py:296`) currently stringifies every field defensively and has NO `target` read — FR-3 needs a parse line, and the spec should state the absent-key contract (`s.get("target")` → `None`, not `""`) so FR-9 byte-identity holds.
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F3, R1-F4.

**Concern 3 — new lane `{svc}-declared-functional-slo.yaml` + `bound_declared_functional` fr_coverage key.**
- **Summary answer:** Separate lane is correct; but the `fr_coverage`→`compare.py` wiring is a hard gap the spec omits, and it must be listed as an FR, not left implicit.
- **Rationale:** `build_comparison_report` (`compare.py:67`) reads exactly `emitted`, `bound_declared_series`, and the closed `_GAP_CLASSES` tuple. A `bound_declared_functional` key added by the generator is **invisible** to the comparison report and every dashboard keyed on it unless `compare.py` is changed to read it (parallel to the `bound` field). The spec's FR-8 adds the key generator-side but never states the consumer-side contract.
- **Assumptions / conditions:** dashboards + `compare-live` verdict ids read `fr_coverage` via `compare.py`, not the raw manifest.
- **Suggested improvements:** R1-F5, R1-F6.

**Concern 4 — FR-7 FR-precedence de-dup correctness.**
- **Summary answer:** The `(service, signal_kind)` key is right, but the spec leaves the cross-generator *ordering/authority* and the *skip record shape* undefined — a correctness gap.
- **Rationale:** FR-7 says "consulting the FR list read-only" (NR-5) but `generate_functional_slos` filters FRs by `f.service in (None, "", service.service_id)` — an FR with `service=None` (global) covers *every* service's `signal_kind`. The de-dup key must therefore treat a `service=None` FR as covering the declared series' service, or precedence silently fails to fire for global FRs. Also unspecified: is the skip recorded in `deferred_declared_kinds` (with a new `reason_code`) or a separate list? FR-7 says "observable" but names no channel.
- **Assumptions / conditions:** an FR with `service=None`/`""` is intended to apply to all services (matches the existing filter).
- **Suggested improvements:** R1-F7, R1-F8.

**Numbered suggestions (F-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Resolve OQ-5 to 4b in FR-4 and pin the enriched deferred-record schema explicitly: the exact keys `{service, kind, series, query, threshold_deferred: true, reason_code}` and a normative statement "no SLO YAML is written to disk for a threshold-deferred candidate." | FR-4 currently offers 4a *or* 4b and OQ-5 only "leans" 4b; an implementer could pick either. 4a produces an OpenSLO SLO with a null/absent `spec.target`, which fails the `openslo/v1` shape `generate_functional_slos` emits and breaks `compare-live` replay. | §2 FR-4 + §4 OQ-5 (mark resolved) | Unit test: a covering series with no `target` produces zero files on disk and one `deferred_declared_kinds` entry containing a non-empty `query`. |
| R1-F2 | Interfaces | high | Add an FR (or extend FR-8) requiring `compare.py:_entry_line` to surface the grounded `query` (and `threshold_deferred` state) for a `functional_bound_threshold_deferred` entry, not just `kind → series`. | Verified: `_entry_line` reads only `kind`, `series`, `enabling_flag`, `reason`. Under 4b the query FR-4 says "must not be lost" is dropped at render time — the render contract, not just the data, must carry it. | §2, new FR near FR-8; reference `compare.py:_entry_line` | Snapshot test on `render_report` output: the threshold-deferred entry line contains the PromQL query substring. |
| R1-F3 | Data | medium | In FR-3, name the new field `target: Optional[str] = None` explicitly (mirroring `FunctionalRequirement.target`, `artifact_generator_models.py:121`) and state it accepts a raw PromQL objective string, not a float. | The spec says "add an optional `target` field" without type or naming. The sibling intent-carrier already uses `target: Optional[str]`; divergence (e.g. `Optional[float]`, or a name like `threshold`) would fork threshold vocabulary and break the "analogous to `fr.target`" claim in FR-3. | §2 FR-3 | Type check: field signature equals `FunctionalRequirement.target`. |
| R1-F4 | Data | medium | Add an explicit parse-contract line to FR-9: `_parse_declared_series` must read `target` as `s.get("target")` (yielding `None` when absent, NOT `""`), so an absent key is indistinguishable from today's model and FR-9 byte-identity holds. | `_parse_declared_series` (`artifact_generator_context.py:296`) stringifies every other field with `str(...)`; blindly doing `str(s.get("target",""))` would make absent `target` = `""` (truthy-distinct from `None`) and could flip a series into a "has authored target" branch. | §2 FR-9 (or FR-3) | Test: parsing a series dict with no `target` key yields `target is None`; round-trips byte-identically vs pre-feature. |
| R1-F5 | Interfaces | high | Add an FR making the `compare.py` consumer contract normative: `build_comparison_report` must read `bound_declared_functional` (parallel to `bound_declared_series`) and `render_report` must present it; otherwise the new `fr_coverage` key is dead. | `build_comparison_report` (`compare.py:67`) reads a fixed set of keys; a generator-only key is invisible to the report and to dashboards that consume the report. FR-8 stops at the generator boundary. | §2, new FR after FR-8; anchor `compare.py:build_comparison_report` | Test: a manifest with a `bound_declared_functional` entry produces a report whose `to_dict()` includes it and whose `render_report` text lists it. |
| R1-F6 | Ops | medium | State whether the new lane + `bound_declared_functional` entries mint NEW `compare-live` verdict ids, and if so require a golden-baseline update step in the FR so the CI gate doesn't red-flag the new SLIs as unexpected drift. | The focus file flags "new replayable SLIs → new verdict ids." A new bound SLI that `compare-live` replays will appear as an unrecognized live series against the existing baseline and fail the gate on first run unless the baseline is regenerated. | §2 (new FR) or §3 NR with an explicit ops note | Run `compare-live` against a fixture with one bound-functional series; confirm the documented baseline-update step yields a green gate. |
| R1-F7 | Risks | high | Tighten FR-7's de-dup key: an FR with `service` in `(None, "", <svc>)` must be treated as covering `<svc>`'s `signal_kind` (matching `generate_functional_slos`'s own filter), else a global (`service=None`) FR fails to suppress the declared binding and both emit. | `generate_functional_slos` filters `f.service in (None, "", service.service_id)`; a strict `(service, signal_kind)` equality key would miss `service=None` FRs and double-emit. The de-dup must reuse the same service-matching predicate. | §2 FR-7 | Test: a global FR (`service=None`, `signal_kind=saturation`) + a saturation-covering declared series on `svc-a` → exactly one SLO for `svc-a`, and a recorded skip. |
| R1-F8 | Validation | medium | Specify FR-7's skip *channel* and *shape*: record the skipped declared binding in `deferred_declared_kinds` with `reason_code="functional_fr_precedence_skip"` (naming the winning FR id), rather than an unspecified "observable" record. | FR-7 says the skip must be "observable (not silent)" but names no list, key, or field — an implementer could log it, drop it, or invent a new list, defeating traceability. Reusing `deferred_declared_kinds` keeps it in the single gap channel `compare.py` already renders. | §2 FR-7 + §2 FR-8 accounting | Test: FR-covered + declared-covered same `(svc,kind)` → one `deferred_declared_kinds` entry with `reason_code=functional_fr_precedence_skip` and the winning FR id. |
| R1-F9 | Architecture | low | Note in FR-5 that `quantile↔histogram` is inert for in-scope kinds: no per-service functional kind in `_FUNCTIONAL_SLI_TEMPLATES` uses the `quantile` shape (only the NR-4-excluded AI-agent kinds do). List it as "reserved/forward-compat" or drop it to avoid implying a binding path that can't fire. | Verified: `queue_depth`/`lag`/`saturation`→`gauge_max`, `retry_rate`→`rate`, `run_success`→`ratio`, `freshness`→`age`. `quantile` appears only on `llm_cost_per_request` etc. (project-scoped, excluded). The FR-5 row is dead code as scoped. | §2 FR-5 compatibility list | Static check: intersection of {kinds using `quantile` shape} and {in-scope non-project-scoped kinds} is empty. |
| R1-F10 | Ops | low | Add an acceptance criterion to FR-9 that names the *exact* invariance surface: absent any functional-covering declared series, no `{svc}-declared-functional-slo.yaml` is written AND `fr_coverage` gains no `bound_declared_functional` key (absent, not empty-list), since an empty-list key is a new byte in the manifest. | FR-9 says "no new `fr_coverage` key values" but an empty `bound_declared_functional: []` is itself a diff vs today's manifest and would break byte-identity for existing golden fixtures. | §2 FR-9 | Golden test: diff manifest for a no-functional-series metadata surface against the pre-feature golden = zero bytes changed. |

**Adversarial stress-test (edge/failure modes):**

- **Multi-kind `covers` list.** A single declared series may `covers: [saturation, queue_depth]` (both `gauge_max`). The spec is silent on whether one series binds *multiple* functional SLIs, and whether FR-7 precedence + the type-compat gate are evaluated **per (series,kind)** or per series. Recommend FR-1/FR-5 state "evaluated per (series, covered-kind)". (Captured in spirit by R1-F7's key discussion but not filed separately to respect the soft cap.)
- **`target` present but `type↔shape` mismatch (FR-5 defer) simultaneously.** Which wins — does an authored target on a shape-incompatible series still defer (correct), and is the target then discarded or preserved in the mismatch record? FR-4/FR-5 interaction is unspecified; the mismatch record should note the target was present-but-unusable so the author isn't misled into thinking it was honored.
- **Base-RED overlap.** A series could `covers: [latency, saturation]` — the base binder (FR-1..) binds `latency`, this feature binds `saturation`, from the **same** series. Confirm no double-emission of the shared series into two lanes causes a metadata `name` collision (both SLOs derive names from `{svc}-{kind}-...`; distinct kinds avoid collision, but the spec should assert it).

**Endorsements / Disagreements:** none — Appendix A/B/C were empty prior to this round (R1 is the first external review).

