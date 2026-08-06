# Proposal — SDK explicit-state emission for Context-Correctness-by-Construction (Tier B)

**From:** startd8-sdk owner (observability scoring pipeline) · **To:** ContextCore loop + Harbor FDE
**Re:** REQ-01 FR-7 (Explicit per-component binding state) · **Status:** proposal to route — needs a cross-repo contract, NOT a solo SDK patch
**Companion (already landed, Tier A):** single-source aggregate rollup — `rollup_avg_by_type` shared by
`_write_quality_report` + `merge_quality_services`, so a producer can no longer *drop* a per-type key.

## Why (the recurring failure mode, named)

Every scoring bug driven to closure this session was the **same shape**: a bare `0` or an *absent* field,
emitted by the SDK, that a downstream consumer read as a real value.

| Silent `0`/absent (SDK emitted) | Consumer misread it as |
|---|---|
| `avg_slo_definition_score` absent (SLO generated-but-unscored) | "not scored" |
| `metric_coverage_{system,human,bridge} = 0` (feed-excluded / not-fed) | "no coverage" |
| `avg_dashboard_spec_score` absent (merge dropped the rollup) | grader `dashboard = 0.0` → structural stuck at B |
| `metric_coverage_bridge = None` (apply never computed it) | "bridge = 0" |
| registry binds `0.0` (deployed-but-unscraped) | "not deployed" (FR-7's own example) |

This is the **"Silent Poison"** the survivorship audit names and exactly what **Context-Correctness-by-
Construction** (REQ-01 FR-7) prevents: *a state must surface explicitly instead of silently arriving as a 0.*

Tier A (landed) closes the **drop** class structurally. Tier B closes the **misread** class: the SDK stops
emitting an ambiguous `0`/absent and instead emits an **explicit state** the consumer cannot misread.

## What the SDK would emit (the proposed contract)

Replace ambiguous bare values in `observability-quality.json` with a `{value, state, reason}` shape wherever a
zero/absence is currently overloaded. Three states cover every case above:

- `computed` — the value was produced (a `0.0` here is a *real* zero: "computed, and it is zero").
- `not_computed` — the producer on this path did not run the computation (e.g. the affordance-*apply*
  path that never computes per-service `metric_coverage_*`). Carries `reason`.
- `excluded` — the artifact/axis was deliberately not produced (e.g. `alert_rule` skipped because the RED
  kind is declared-covered, #286). Carries `reason`.

Per-service `metric_coverage_*` (illustrative):
```json
"metric_coverage_bridge": {"value": 0.0, "state": "computed"}
"metric_coverage_bridge": {"state": "not_computed", "reason": "affordance-apply path; no coverage recompute"}
"metric_coverage_bridge": {"state": "excluded", "reason": "alert_rule skipped: RED kind declared-covered (#286)"}
```
Per-type aggregate presence: a type absent from the rollup because it was *skipped* is emitted as
`avg_alert_rule_score: {"state": "excluded", "reason": "skipped"}` rather than silently missing.

The report card (FR-7 consumer, `gen-report-card.py`) then maps these to the tri-state it already wants —
`grounded-and-bound` / `deployed-but-unbound(reason)` / `not-deployed` — **by reading state, never by
inferring from a 0**.

## Why this must be routed, not solo-patched (staying in lane)

It is a **schema change** to `observability-quality.json`. Every consumer — the report-card grader,
`gen-report-card.py`, `compare-live`, any `catalog.load_quality_json` reader — must adopt the `{value, state}`
shape or a back-compat shim. That is a cross-repo contract the **loop/FDE own the consumer half of** (FR-7's
touch list is explicitly `gen-report-card.py` + the coverage report). Shipping it unilaterally from the SDK
would break the graders — the exact "silent break" this proposal exists to end.

## Proposed split

- **SDK (me), on your go:** emit the `{value, state, reason}` shape behind a **back-compat flag** (default off →
  byte-identical today; on → explicit states), plus a `states` sidecar block so old readers keep working while
  new readers migrate. I own producing honest states; I do not flip the default until consumers are ready.
- **Loop/FDE (FR-7):** the report-card grader + `gen-report-card.py` consume `state`; retire the
  "0/absent → not-deployed / dashboard=0.0" inferences. Agree the enum + the migration window.

## Ask

1. Do you want the explicit-state contract? (If the report card would rather keep inferring, Tier A alone —
   already landed — closes the specific L4 drop, and this is deferred.)
2. If yes: confirm the state enum (`computed` / `not_computed` / `excluded`, + optional `unbound` for the live
   binding axis) and the migration shape (flagged dual-emit vs hard cut), and I'll build the SDK half.
3. Which surfaces first? `metric_coverage_*` (closes L1a-class misreads) is the highest-value starting point;
   aggregate per-type `excluded` is second.

## Guardrail (yours, echoed)

Verify on the **real** surface, never synthetic — the whole point is that a synthetic fixture injecting a value
hides the very absence this contract makes explicit.
