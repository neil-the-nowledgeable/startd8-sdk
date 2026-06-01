# Finding: Cost/Session OTel metrics are not emitted during Prime-Contractor runs

**Date:** 2026-06-01
**Status:** Finding (root-caused) — requirements-vs-implementation classification in §6
**Severity:** Medium — cost/usage telemetry from the *active construction path* never reaches Mimir;
agent-observability dashboards (cost, tokens, sessions, latency) have no live producer.
**Discovered while:** a live prime-contractor run (run-011, strtd8 pilot, $2.07 spent) produced
**zero** `startd8.cost.*` / `startd8_*` series in Mimir.

> Companions: `OBSERVABILITY_GENERATOR_NAMING_FIX_REQUIREMENTS.md` (dashboard query/label bug — a
> *separate* defect), `OBSERVABILITY_PIPELINE_LIVE_STATUS_2026-06-01.md`.

---

## 1. Symptom

A prime-contractor run was active and **spending real money** — run-011 postmortem:
`cost_summary.total_usd = 2.067`, with per-feature `lead_cost` / `drafter_cost` (e.g. PI-001
lead_cost=0.1344, drafter_cost=0.0181). Yet querying Mimir during the run:
- `startd8_cost_USD_total`, `startd8_requests_total`, `startd8_active_sessions`,
  `startd8_tokens_total`, `startd8_response_time_ms_*` → **0 series across all jobs.**
- The only live `job="startd8-sdk"` series were workload-internal: `complexity_tier_distribution_*`,
  `micro_prime_element_registry_*`, `pipeline_artifact_inventory_lookup_total`,
  `startd8_events_total`, `otel_sdk_span_*`.

So the OTLP→Alloy→Mimir pipeline works (other startd8 metrics flow); the cost/session metric
**families are simply never produced** by this code path.

## 2. Root cause

The `startd8.cost.*` metrics have **exactly one emitter**, and the prime path never triggers it:

```
startd8.cost.* OTel metrics
  └─ CostMetrics.record()                      costs/otel_metrics.py:138-141
       └─ CostTracker.record_cost()            costs/tracker.py:259-266  (lazily builds CostMetrics)
            └─ called from BaseAgent           agents/base.py:356
                 guarded by:  if self.cost_tracker and _COSTS_AVAILABLE:   (base.py:344)
                 reached only via:  BaseAgent.generate_and_track()  (STEP 3), not agenerate()
```

The prime-contractor satisfies **neither** condition:
1. **No `CostTracker` is injected.** `scripts/run_prime_workflow.py`, `contractors/prime_contractor.py`,
   and `implementation_engine/drafter.py` never construct or attach a `CostTracker`, so
   `self.cost_tracker` is falsy and the `record_cost()` call at base.py:356 is skipped.
2. **It bypasses the tracked path.** The contractor calls `agent.agenerate(prompt)` directly and then
   computes cost from the returned `token_usage` via `token_usage_cost()` — a **pure pricing helper
   with no OTel emission** (`utils/token_usage.py`). The result is written to postmortem JSON and to
   trace-span attributes (`llm.cost_usd`), never to a metric.

**Session metrics have the same shape.** `startd8_active_sessions / requests_total /
response_time_ms_* / tokens_total` are emitted only by `SessionTracker.record_request()`
(`session_tracking.py`), which is **not driven anywhere** in the prime/agent path.

## 3. Where prime-contractor cost telemetry actually lands

| Destination | Carries cost? | Mechanism |
|---|---|---|
| Postmortem JSON (`prime-postmortem-report.json`, `kaizen-metrics.json`, `batch-postmortem-report.json`) | ✅ | `token_usage_cost()` aggregation |
| Tempo trace spans (`llm.cost_usd`, `agent.tokens_input/output`, `agent.truncated`) | ✅ | `agents/tracked.py` span attributes |
| **Mimir metrics (`startd8.cost.*`, `startd8_*`)** | ❌ **never** | no emitter on this path |

The historical `startd8_cost_USD_total` series seen earlier came from a **different entrypoint**
that *does* wrap agents with a `CostTracker` (benchmark runner / tracked-agent usage); that history
was lost when the corrupt Mimir head was cleared (see the Mimir incident postmortem).

## 4. Evidence
- run-011 postmortem `cost_summary.total_usd = 2.067` (10 features) — cost IS tracked.
- `grep '\.record_cost(' src` → only `costs/tracker.py:100` (wrapper) and `agents/base.py:356` (gated).
- prime path (`run_prime_workflow.py` / `prime_contractor.py` / `drafter.py`) → no `CostTracker` /
  `SessionTracker` / `record_cost` / `record_request` construction.
- contractor cost = `token_usage_cost(token_usage)` (pure helper) → JSON + span attrs.

## 5. Fix options (for a later pass)
1. **Inject a `CostTracker` into the contractor's agents** and route generation through
   `generate_and_track()` — reuses the existing emitter; cost/session metrics start flowing with no
   new metric code. (Cleanest.)
2. **Call `record_cost()` from the contractor's per-generation accounting** — it already holds
   `token_usage` where it computes `lead_cost`/`drafter_cost`; emit there.
3. **Drive a `SessionTracker`** around the run for the session-family metrics.
4. Pair with the dashboard naming fix (`OBSERVABILITY_GENERATOR_NAMING_FIX_REQUIREMENTS.md`) so the
   panels that then have data also have correct selectors.

## 6. Requirements vs. implementation classification

**Verdict: a COMBO, root-caused in a *requirements* gap (an unowned coverage requirement),
surfaced by an *implementation* divergence.** Three requirement tracks each touch cost/observability,
and each assumed *another* path emits — so no doc owns "the construction path must emit cost metrics."

### The requirements gap (primary)
1. **AI-Agent Observability (REQ-AAO)** — `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md`. Its §4 explicitly
   scopes itself **"observation-only … Changing the agent runtime behavior is out of scope."** And
   REQ-AAO-002 codifies the *assumption* that `startd8.cost.*` "is emitted by `CostTracker.record_cost()`
   **on the standard `generate()` path**." So this doc catalogued the *existing emitters* and assumed
   coverage — it neither required nor was allowed to wire the contractor. Its evidence base was a static
   telemetry **inventory**, not a runtime **coverage** check, so "who drives the emitter in the dominant
   workload?" was never asked.
2. **Cost-Tracking Precision (REQ-CT)** — `COST_TRACKING_PRECISION_REQUIREMENTS.md`. Scoped to
   `costs/` + `agents/{base,claude}.py`; its architecture assumes the universal path is
   `agents/base.py → costs/tracker.py → pricing` (the `record_cost` bridge). It targets *accuracy* of
   that path and never contemplates a generation path (the contractor) that **bypasses base.py's
   tracked bridge entirely**.
3. **Prime Contractor (REQ-PC)** — `prime/PRIME_CONTRACTOR_REQUIREMENTS.md`. Has an Observability layer
   (REQ-PC-013/014) but rated **"Low … logging and cost tracking,"** satisfied by **postmortem JSON cost
   accounting**. The requirement never distinguishes *"track cost (for the postmortem)"* from *"emit cost
   as OTel metrics (for dashboards/Mimir)"* — so the implementation met the letter of REQ-PC-013/014
   while producing zero metrics.

→ **The missing requirement:** *every cost-incurring generation path — especially the active
construction path (Prime Contractor) — MUST route through the cost/session metric emitter
(`CostTracker`/`SessionTracker`), not only persist cost to JSON/spans.* No doc states this; each
deferred to "the standard path."

**Validation requirement validates the wrong thing.** REQ-AAO-012 (descriptor↔emission parity) checks
that the emitter *modules* declare⇔create their instruments — it confirms the cost meter **can** emit,
never that the **dominant workload drives it at runtime**. So the existing validation requirement would
pass while this gap is wide open.

### The implementation divergence (secondary, contributing)
The Prime Contractor calls `agent.agenerate(prompt)` directly and prices results with
`token_usage_cost()`, instead of `BaseAgent.generate_and_track()` with an injected `CostTracker`. This
**broke the premise** REQ-AAO/REQ-CT relied on ("the standard `generate()` path"). It violates no
*explicit* requirement (none exists) — so it's not a defect-against-spec; it's an implementation choice
that invalidated the requirements' unstated coverage assumption.

### What the fix therefore requires (both layers)
- **Requirements:** add an owned coverage requirement (best home: REQ-PC observability, cross-linked
  from REQ-AAO) — "construction-path generations MUST emit cost/session OTel metrics" — and upgrade
  REQ-AAO-012 (or add REQ-AAO-013) to a **runtime coverage** assertion, not just static emitter parity.
- **Implementation:** inject a `CostTracker` into the contractor's agents + route through
  `generate_and_track()` (§5 option 1), or call `record_cost()` from the contractor's existing
  per-generation accounting (§5 option 2).

**One-line classification:** *Combo — a requirements **coverage** gap (no doc owns "the construction
path must emit cost metrics"; three tracks each assumed the standard path) that an implementation
**divergence** (contractor bypasses the tracked emit path) turned from latent into actual.*
