# Cost/Session Metric-Emission Coverage Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-01
**Status:** Draft
**Prefix:** REQ-CME (Cost Metric Emission)
**Component:** `src/startd8/contractors/prime_contractor.py`, `src/startd8/costs/otel_metrics.py`
**Origin:** `docs/design/OBSERVABILITY_COST_METRIC_EMISSION_GAP.md` §6 (requirements-vs-implementation classification)
**Plan:** `docs/design/COST_METRIC_EMISSION_COVERAGE_PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (read of the prime/agent/cost path) revealed 5 corrections. Net: the fix is far
> smaller and lower-risk than v0.1 assumed — a localized emission at one chokepoint, not an
> agent-injection refactor.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Wire via injected `CostTracker` + `generate_and_track()` (FR-6a preferred) | Generation uses raw `agent.agenerate()` across workflows/context_seed/engine — switching all call sites is invasive/risky | **FR-6 reframed:** emit at the per-feature result chokepoint instead |
| Cost-compute site is scattered (OQ-4) | A single chokepoint `prime_contractor.py:_record_generation_result` (~4607) already holds `result.{cost_usd,input_tokens,output_tokens,model}` and already emits an instrumentor metric | One localized addition covers every feature |
| Use `CostTracker.record_cost()` (OQ-5) | `CostTracker.__init__` **requires a SQLite `CostStore`** — heavy for metric-only emission. `CostMetrics().record(cost_record)` is **store-free**, duck-typed | **FR-6 uses `CostMetrics` directly**, no store/DB per run |
| `record_cost` re-prices tokens (metric == postmortem) | `record_cost`/pricing recompute cost → could drift from `result.cost_usd` | **NEW FR-8:** emit the already-computed `result.cost_usd` as `total_cost` (postmortem-authoritative, no drift) |
| Session metrics in scope (FR-1, OQ-3) | The contractor has **no per-LLM-call session loop**; `SessionTracker` models live sessions, a poor fit for a batch run | **FR-1 narrowed** to the cost/token family; session metrics **deferred** (Non-Req) |

**Resolved open questions:**
- **OQ-1/OQ-4 → resolved.** Single emission chokepoint at `_record_generation_result` (~4607).
- **OQ-2 → moot.** `generate_and_track()` not needed; chokepoint emission bypasses it.
- **OQ-3 → deferred.** No session lifecycle in the construction path → session-family metrics out of v1 scope.
- **OQ-5 → resolved.** Avoid `CostTracker` (needs `CostStore`/SQLite); emit via store-free `CostMetrics().record()`.
- **OQ-6 → resolved.** Single chokepoint, agents carry no `cost_tracker` → no double-count; `double_record_guard` (dual-API same `correlation_id`) not triggered.

---

## 1. Problem Statement

The Prime Contractor (the active construction path) incurs real LLM cost but emits **zero**
`startd8.cost.*` / `startd8_*` OTel metrics to Mimir, so agent-observability dashboards (cost, tokens,
sessions, latency) have no live producer. Cost is captured only in postmortem JSON and trace-span
attributes. Root cause (already established): the contractor calls `agent.agenerate()` directly and
prices results with `token_usage_cost()` (a pure helper), bypassing `CostTracker.record_cost()` — the
sole emitter of `startd8.cost.*` — which is reachable only via `BaseAgent.generate_and_track()` and
gated on an injected `cost_tracker`. Session metrics (`SessionTracker.record_request()`) are never
driven on this path either.

This is a requirements **coverage** gap (no doc owns "the construction path MUST emit cost metrics")
surfaced by an implementation divergence (contractor bypasses the tracked emit path).

| Component | Current State | Gap |
|-----------|---------------|-----|
| `startd8.cost.*` emitter | Exists (`CostTracker.record_cost` → `CostMetrics`) | Not invoked on the contractor path |
| Prime Contractor generation | `agenerate()` + `token_usage_cost()` → JSON/spans | No metric emission |
| Session metrics | `SessionTracker.record_request()` exists | Never driven by contractor |
| Validation (REQ-AAO-012) | Static descriptor⇔emitter parity | Doesn't assert runtime emission by the dominant workload |
| Requirement ownership | REQ-AAO (observe-only), REQ-CT (base.py bridge), REQ-PC-013/014 (JSON cost) | None mandate construction-path metric emission |

## 2. Requirements

**FR-1 (coverage requirement — the owned mandate).** Every cost-incurring generation in the Prime
Contractor construction path MUST result in emission of the `startd8.cost.*` cost/token metrics, in
addition to the existing postmortem JSON and span-attribute capture. Home: a new REQ-PC observability
requirement, cross-linked from REQ-AAO. *(v0.2: narrowed to the cost/token family; the session/usage
family is deferred — see Non-Requirements — because the construction path has no per-call session
lifecycle.)*

**FR-2 (no double-counting).** Emission MUST NOT double-count cost. A single LLM generation MUST
produce exactly one `startd8.cost.total` increment for its cost. The existing double-invocation guard
(`double_record_guard.py`, REQ-AAO-002) MUST be honored/extended to the contractor path.

**FR-3 (preserve postmortem path).** Adding metric emission MUST NOT change or regress the existing
per-feature `lead_cost`/`drafter_cost` postmortem JSON accounting or the trace-span `llm.cost_usd`
attributes. Metrics are additive.

**FR-4 (attribution labels).** Emitted cost/session metrics MUST carry attribution labels sufficient
for the dashboards: at minimum `model`, `provider`, and `project`; SHOULD include agent role
(lead/drafter/arbiter) and feature/run identifiers where available, subject to cardinality limits.

**FR-5 (runtime-coverage validation).** A test/validation MUST assert that a representative
construction run actually produces `startd8.cost.*` (and session) series — not merely that the emitter
modules declare⇔create instruments. Upgrade REQ-AAO-012 or add REQ-AAO-013.

**FR-6 (wiring approach — reframed v0.2).** Emission MUST happen at the per-feature result chokepoint
`prime_contractor.py:_record_generation_result` (~4607), reusing the existing OTel emitter
`CostMetrics().record(cost_record)` (store-free) — **not** by injecting a `CostTracker` (requires a
SQLite `CostStore`) nor by switching generation call sites to `generate_and_track()` (invasive, raw
`agenerate()` is used across multiple layers). The emitter and metric definitions MUST be reused, not
duplicated. Emission MUST cover both success and failure paths (failed features still incur cost).

**FR-7 (conventions).** New SDK code MUST use `get_logger` (not `logging.getLogger`) and
`model_catalog` defaults (no hardcoded model strings), per project conventions.

**FR-8 (cost source — no drift).** The emitted `startd8.cost.total` MUST use the already-computed,
postmortem-authoritative `result.cost_usd` as the recorded cost (passed through to `CostMetrics`),
NOT a re-priced value, so the metric and the postmortem JSON agree. Token counters use
`result.input_tokens`/`output_tokens`. (Pricing accuracy itself remains owned by the REQ-CT track.)

## 3. Non-Requirements

- Building the category-5 artifact **generator** (separate; REQ-OAT-041).
- Fixing the dashboard query/label naming bug (separate; `OBSERVABILITY_GENERATOR_NAMING_FIX_REQUIREMENTS.md`).
- Changing cost **accuracy**/pricing (separate; REQ-CT precision track).
- Backfilling historical cost metrics lost when the Mimir head was cleared.
- Instrumenting the Artisan path (ON HOLD).
- **Session/usage metric family** (`startd8_active_sessions/requests_total/response_time_ms_*/tokens_total`)
  for the construction path — deferred (v0.2): no per-call session lifecycle exists to drive
  `SessionTracker`. Revisit if a contractor session model is introduced.
- Persisting contractor cost to the `CostStore` SQLite DB — out of scope; the postmortem JSON already
  persists, and v1 emits metrics only.

## 4. Open Questions (all resolved during planning — see §0)

- **OQ-1/OQ-4 → resolved:** single chokepoint `_record_generation_result` (~4607).
- **OQ-2 → moot:** `generate_and_track()` not used.
- **OQ-3 → deferred:** no session lifecycle → session metrics out of v1 scope.
- **OQ-5 → resolved:** avoid `CostTracker`/`CostStore`; emit via store-free `CostMetrics().record()`.
- **OQ-6 → resolved:** single emitter on the path → no double-count.
- **Residual:** confirm `result.provider` (or derive from the model spec) is available at the chokepoint
  for the `provider` label (FR-4) — verify during implementation.

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed (FR-1), 1 reframed (FR-6),
1 added (FR-8), 6 open questions resolved/deferred, session family moved to Non-Requirements.*
