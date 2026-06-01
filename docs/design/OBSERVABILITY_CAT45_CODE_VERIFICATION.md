# Cat-4/5 Code Verification — archaeology check of plan claims

**Date:** 2026-05-31
**Purpose:** Verify firsthand the code-grounded claims in `OBSERVABILITY_AI_AGENT_PLAN.md` (v0.1)
and `OBSERVABILITY_PROJECT_PLAN.md` (v0.1) before the post-CRP reconciliation, so the reconciliation
and eventual implementation rest on accurate facts. Read-only; no doc/code edits.
**Worktree:** `startd8-obs-gap`, branch `feat/observability-followup-run007`.

> Feeds the post-CRP cross-doc reconciliation. Two plan claims are **stale**, four are **confirmed**,
> and one **new collision** (not in any doc) was found. The new collision is the highest-value catch.

> **RECONCILED 2026-05-31** (merge `5babc995` on `main`). All findings folded into the plan docs and
> implemented: the §A stale claims are now *corrected and shipped* (A-1 tier histogram declared in
> commit `7b78b89c`; A-2 Prometheus path retired in `bdfad35f`), §B confirmed claims addressed
> (B-3 `task.*` collision → **deferred** disambiguation follow-up; B-4 phase-span naming → still open),
> and the §C `category` polysemy is **resolved** (see §C resolution note below).

---

## A. Stale plan claims — must revise

### A-1. PRO Phase 0.2 / C-2 — "dead tier histogram (created, never recorded)" is FALSE
- `complexity/classifier.py:24` creates `_tier_histogram` (name `complexity.tier_distribution`);
  **it IS recorded** at `classifier.py:277–281`: `_tier_histogram.record(1, {"tier": tier.value})`
  inside `_classify_tier_core`'s return path. Not dead.
- **The real issue** is the opposite: the histogram is **live but UNDECLARED** — `complexity/classifier.py`
  is **not** among the 11 modules that declare `_OTEL_DESCRIPTORS` (see §C). So it is
  *emitted-but-not-declared* → a genuine parity gap.
- **Action:** flip C-2 from "remove dead histogram / wire a record()" to "**declare** the live
  `complexity.tier_distribution` histogram in `_OTEL_DESCRIPTORS` (category/orientation = project /
  system — it's a routing signal)." This *strengthens* the parity-test rationale (REQ-AAO-012 /
  REQ-PRO-002 2.3): the parity test would have caught this. Net: a deletion claim becomes a
  declaration + parity-coverage claim. No line-removal here (revise the Phase-0 "net-negative" tally).

### A-2. AAO Phase 0.3 — "dead Prometheus fallback (session_tracking.py:438–503)" is OVERSTATED
- `_init_prometheus` (438–503) is **reachable opt-in**, not dead: gated by
  `if prometheus_port and not self._otel_enabled` (`session_tracking.py:336`); `prometheus_port`
  defaults `None`. It already emits a deprecation warning (441) and has **live recording sites** at
  611, 810, 895 (`# Legacy Prometheus metrics`).
- **Action:** reframe 0.3 from "remove the dead fallback" to "**retire the deprecated opt-in
  Prometheus path** once OTel-only is confirmed — removal spans 336, 438–503, **and** the 611/810/895
  recording sites + the `_prom_*` attrs, not just 438–503." Still a valid net-removal, just larger
  and correctly scoped. Keep behind a confirmed-no-consumer grep (AAO 0.3 validation already says this).

---

## B. Confirmed claims — as written

### B-1. Cost double-record (AAO-002) — two DECLARED, disjoint paths ✓ (latent, not actual)
- `costs/otel_metrics.py:18` declares `_OTEL_DESCRIPTORS` → **`startd8.cost.total`** (dotted, meter
  `startd8.costs`, attrs incl. `correlation_id`); recorded via `self._cost_total.add(...)` (134).
- `session_tracking.py:39/90/400` declares/creates **`startd8_cost_total`** (underscore, per-session).
- Distinct semantics (global cost tracker vs per-session counter), disjoint emission paths → the
  double-count is **latent** (would only double if the same spend is fed to both). AAO-002's
  "document distinct semantics + guard on shared `correlation_id`" is the right, minimal response.

### B-2. Underscore metric names (AAO Phase 2 rename targets) ✓
- `session_tracking.py` creates **OTel** instruments with **underscore** names (non-idiomatic):
  `startd8_active_sessions` (356), `startd8_requests_total` (363), `startd8_tokens_total` (370),
  `startd8_truncations_total` (393), `startd8_cost_total` (400). Rename-to-dotted (Prom exporter
  reproduces underscore) is valid. **Caveat:** the deprecated Prom path (§A-2) *also* creates the
  same underscore names directly (452–489); they're mutually exclusive at runtime, but sequence the
  Phase-2 rename **after/with** the 0.3 retirement to avoid two producers of the same Prom name.

### B-3. `task.*` naming collision (PRO-008) ✓ — genuine polysemy
- `otel_conventions.py` `TASK_*` are **codegen-chunk** attrs: `task.complexity_tier` (71),
  `task.blast_radius` (72), `task.caller_count` (73), `task.has_dynamic_dispatch` (74),
  `task.id/title/domain/phase/status/cost/attempts` (61–68).
- ContextCore **work-item** tasks also live under `task.*` (`task.status`, `task.percent_complete`
  per CLAUDE.md SpanState v2). **`task.status` is defined in BOTH worlds** → real collision.
- PRO-008's rename of codegen attrs to `codegen.task.*` (or namespacing the chunk attrs) is justified.

### B-4. Phase-span naming inconsistency (PRO C-4) ✓
- Declared pattern: `artisan.workflow.{workflow_id}.phase.{phase}` (`artisan_contractor.py:111`,
  attrs `phase.name/status/duration_ms/cost`).
- Runtime span name elsewhere: `f"phase.{phase.value}"` (`artisan_contractor.py:1839`, attr
  `phase.name`). Two naming conventions for the same concept — reconcile/document (C-4 valid).

---

## C. NEW finding — `category` field already exists in `manifest.py` (in no doc)

The plans say "add `category` + `orientation` to `MetricDescriptor`/`SpanDescriptor` (additive)."
Verified nuance:

- `MetricDescriptor` (manifest.py:47–91): fields = name, instrument, unit, description, meter,
  source_file, labels, prometheus_name, dashboard_hints. **No `category`, no `orientation`** → adding
  both is genuinely additive. ✓
- `SpanDescriptor` (94–129): name_pattern, kind, source_file, attributes, events, attributes_dynamic.
  **No `category`/`orientation`** → additive. ✓
- **BUT** `EventTypeDescriptor.category` **already exists** (137) with an **8-value instrument-grouping
  vocabulary**: `agent, cost, pipeline, truncation, job, enhancement, storage, system` — which is
  **NOT** the 5-cat observability taxonomy (`service / business / pipeline_innate / project / agent`),
  even though `agent` and `pipeline` overlap lexically.

**Collision:** introducing `category` on Metric/Span meaning the **5-cat taxonomy** while
`EventTypeDescriptor.category` means the **8-value grouping** creates same-module field-name polysemy.
A reader seeing `category="agent"` (event grouping) vs `category="agent_observability"` (taxonomy) on
sibling descriptor classes will be confused. This is also a **third** `category`: REQ-OAT-070a's
single-registry `category` projection is a fourth lookup of the same word (mirrors the taxonomy doc's
own capability_index-style naming-collision theme).

**Reconciliation options (decide post-CRP, fold into AAO-004 / PRO-005 + taxonomy REQ-OAT-070a):**
1. **Distinct field name** on Metric/Span — e.g. `obs_category` / `taxonomy_category` — leaving
   `EventTypeDescriptor.category` (grouping) untouched. Lowest blast radius, but two names for
   "category-ish."
2. **Unify on the 5-cat taxonomy**: migrate `EventTypeDescriptor.category`'s 8 values into the
   taxonomy + add `orientation` everywhere; one `category` meaning module-wide. Cleaner end-state,
   larger change (touches every EventType declaration).
3. **Keep `category`, document the two axes explicitly** (grouping vs taxonomy) — cheapest, but
   preserves the polysemy the user has repeatedly flagged as accidental complexity.

→ Recommend Option 1 or 2 over 3; raise as a cross-doc reconciliation item so AAO-004, PRO-005, and
taxonomy REQ-OAT-070a all settle on ONE answer rather than three docs each adding `category`.

**RESOLUTION (shipped 2026-05-31).** A blend of Options 1 + 2, settling on ONE answer per axis:
- **Option 2 applied to `EventTypeDescriptor`:** its `category` (the 8-value instrument grouping) was
  **renamed to `event_group`** (commit `da3a1105`, AAO Phase 0.5), freeing `category` to mean the
  5-cat taxonomy uniformly on Metric/Span descriptors (`taxonomy_enums.Category`).
- **Option 1 applied to the legacy capability axis:** `_ARTIFACT_TYPE_TO_CATEGORY`
  (4-value `observe/integration/action/reference`) is **kept distinct** — it feeds the capability-index
  schema only, and the step-C taxonomy registry uses a separately-named `taxonomy_category`
  (`_ARTIFACT_TYPE_REGISTRY`, REQ-OAT-070a, commit `45f0194e`), so no taxonomy strings leak into the
  capability schema (CRP R2-F1). A test asserts the two axes stay value-disjoint.

Net: `category` now means the 5-cat taxonomy everywhere it appears as a taxonomy field; the two
other "category-ish" axes carry distinct names (`event_group`, legacy capability axis). Polysemy closed.

---

## D. Descriptor coverage (for the parity test)

11 modules declare `_OTEL_DESCRIPTORS`: `orchestration`, `session_tracking`, `costs/otel_metrics`,
`workflows/base`, `agents/tracked`, `events/otel_bridge`, `contractors/artisan_phases/runner`,
`repair/orchestrator`, `contractors/artisan_contractor`, `contractors/adapters/contextcore`
(+ `observability/collector` reads them).

**Not declaring (but emitting):** `complexity/classifier.py` (tier histogram — §A-1),
`costs/tracker.py` (records flow into `otel_metrics`). The descriptor↔emission **parity test**
(REQ-AAO-012 / REQ-PRO-002 2.3) is exactly what surfaces these — confirms the test's value with a
concrete first catch (the tier histogram).

---

*Verification note — read-only. Two stale claims (A-1, A-2), four confirmed (B-1..B-4), one new
collision (C). Hand to the post-CRP reconciliation; do not merge into the four CRP-active docs until
the reviewer's R1 round has landed.*
