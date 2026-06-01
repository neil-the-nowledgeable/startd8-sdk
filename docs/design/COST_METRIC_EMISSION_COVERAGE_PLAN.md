# Cost/Session Metric-Emission Coverage — Implementation Plan

**Paired with:** `COST_METRIC_EMISSION_COVERAGE_REQUIREMENTS.md`
**Date:** 2026-06-01
**Status:** IMPLEMENTED 2026-06-01 (branch `fix/observability-generator-naming`)

> **Implementation correction (Phase 6):** the cost-accumulation chokepoint is **`develop_feature()`**,
> which increments `total_cost_usd` at **three** mutually-exclusive sites (content-cache hit, element-cache
> assembly, and the LLM-generation path "regardless of success"). The success-only `_accept_generation_result`
> would have **missed failed features**. Implemented by centralizing all three into a new
> `_accumulate_cost(result)` helper that does the `total_*` trio **and** emits via `_emit_cost_metric()`,
> so the metric and postmortem totals advance in lockstep by construction. Emitter: store-free
> `CostMetrics` (`prime_contractor.py`), record `result.cost_usd` directly (FR-8). Tests:
> `tests/unit/contractors/test_cost_metric_emission.py` (4 pass); 354 contractor tests green.

---

## Planning discoveries (feed the reflection)

| Requirements v0.1 assumed | Planning revealed | Impact |
|---|---|---|
| FR-6(a) preferred: inject `CostTracker` into agents + route via `generate_and_track()` | Generation across the prime path uses `agent.agenerate()` (raw), not `generate_and_track()`, in multiple layers (workflows/builtin + context_seed + engine). Switching all call sites is invasive and high-risk. | **Reframe FR-6:** prefer emission at the per-feature **result chokepoint**, not agent injection. |
| Cost data is scattered; need to find the compute site (OQ-4) | A single chokepoint — `prime_contractor.py:_record_generation_result` (~4600-4608) — already holds `result.cost_usd`, `result.input_tokens`, `result.output_tokens`, `result.model`, and **already emits** `instrumentor.emit_metric('prime_contractor.feature_cost', …)`. | One-line-ish addition of `record_cost(...)` here covers every feature. OQ-4 resolved. |
| `record_cost()` needs token counts | The chokepoint already logs `result.input_tokens/output_tokens` → available. | Token + cost metrics both emittable. |
| Session metrics in scope (FR-1) (OQ-3) | The contractor has **no per-LLM-call session loop**; `SessionTracker` models live agent sessions, which don't map cleanly to a batch construction run. | **Narrow FR-1** to the cost/token family for v1; defer/мark session metrics optional (or one coarse session-per-run). |
| `BaseAgent` may not accept a tracker | `BaseAgent.__init__` already accepts `cost_tracker` (base.py:123) and `resolve_agent_spec(**agent_config)` forwards to `create_agent`. | Injection is *possible* (kept as alt), but unnecessary given the chokepoint. |
| `record_cost` emits the same cost as the postmortem | `record_cost` **recomputes** cost from tokens×pricing (REQ-CT path); may differ slightly from `result.cost_usd` (workflow `token_usage_cost`). | Note reconciliation; emitted `startd8.cost.total` is tokens-derived. Consider optional explicit-cost passthrough (REQ-CT territory). |

## Approach (chosen): emit at the per-feature result chokepoint via store-free `CostMetrics`

> Updated after OQ-5: `CostTracker.__init__` requires a SQLite `CostStore` — too heavy for metric-only
> emission. Use `CostMetrics().record(cost_record)` directly (store-free, duck-typed on `model/provider/
> project/total_cost/input_tokens/output_tokens`), passing the postmortem-authoritative `result.cost_usd`
> as `total_cost` (FR-8 — no re-pricing drift).

**Step 1 — hold one `CostMetrics` per workflow run.** In `PrimeContractorWorkflow.__init__`, lazily
build `self._cost_metrics = CostMetrics()` behind `_COSTS_AVAILABLE` (its meter/instruments init lazily
on first `record`). No store, no DB.

**Step 2 — emit in `_record_generation_result` (~prime_contractor.py:4607).** Right after the existing
`instrumentor.emit_metric('prime_contractor.feature_cost', …)`, build a lightweight cost-record and
emit:
```python
if self._cost_metrics:
    self._cost_metrics.record(_FeatureCostRecord(
        model=result.model,
        provider=_provider_of(result.model),          # derive from spec; verify availability
        project=self.contextcore_project_id or self.project_name,
        total_cost=result.cost_usd,                    # FR-8: postmortem-authoritative, no re-pricing
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    ))
```
`_FeatureCostRecord` is a tiny local dataclass/namedtuple matching the attributes `CostMetrics.record`
reads. Emits `startd8.cost.*` once per feature, from data already in hand. Also call on the **failure**
path (failed features still incur cost) so metric coverage matches the postmortem.

**Step 3 — per-role attribution (enhancement, optional for v1).** If lead/drafter split is wanted on
the dashboard, emit two records using `metadata.lead_cost`/`drafter_cost` + `lead_agent_spec`/
`drafter_agent_spec`. Defer unless required (cardinality + needs per-role token counts, which the
aggregate result may not carry).

**Step 4 — runtime-coverage test (FR-5).** Add a test that runs a minimal contractor generation against
a mock agent with known token usage and asserts the in-memory OTel metric reader recorded a
`startd8.cost.total` point (and token counters). This validates the *workload drives the emitter*, not
just that the emitter exists. Place near existing cost/otel tests.

**Step 5 — conventions + no-regression.** Use `get_logger`; no hardcoded models (FR-7). Verify
postmortem JSON cost path and span `llm.cost_usd` are untouched (FR-3). Run the cost + observability +
contractor unit suites.

## Alternative (documented, not chosen)
Inject `CostTracker` via `resolve_agent_spec(cost_tracker=…)` **and** switch generation call sites from
`agenerate()` to `generate_and_track()`. Rejected for v1: touches many call sites across workflows/
context_seed/engine, changes control flow, higher regression risk. The chokepoint approach reuses the
same emitter with a fraction of the surface area.

## Double-count / guard (FR-2)
The chokepoint fires once per feature result; agents on the prime path carry **no** `cost_tracker`, so
`base.py:356` never also fires for the same generation — no double-count. `SessionTracker` is not used
per-call, so the `double_record_guard` (same `correlation_id` via both APIs) is not triggered. If Step 3
or session metrics are added later, set/verify `correlation_id` and honor the guard.

## Open questions remaining for the requirements update
- OQ-5: confirm `CostTracker()` constructs with no mandatory store and is safe to hold per-run.
- Reconciliation: should the emitted metric use `result.cost_usd` (postmortem-authoritative) instead of
  re-priced tokens, to avoid dashboard-vs-postmortem drift? (Possible `record_cost(explicit_cost=…)`.)
