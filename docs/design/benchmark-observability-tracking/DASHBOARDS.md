# Dashboards & Join Contract (T5 / Sections E & G)

**Status:** T5.4 (join contract + FR-23/FR-24 contract tests) shipped in code. Dashboards (FR-20/21/22)
are **ContextCore-owned** per the FR-24 boundary — see below.

---

## Why the SDK does not ship dashboard JSON (FR-24 ownership boundary)

The SDK **emits** task/insight spans and zero-point events; **ContextCore owns** the derived
progress/velocity/burndown metric computation and the dashboards that visualize them
(`integrations/contextcore.py` docstring; FR-24; req v0.4 R2-F2). So FR-20/21/22 are satisfied by
**pointing ContextCore's existing, shipped dashboards at the benchmark's `project_id`s** — not by
hand-authoring Grafana JSON in the SDK (which would also violate the global `/dbrd-cr8r` HARD RULE).

A contract test enforces this: `tests/unit/test_join_contract.py::test_fr24_no_sdk_derived_gauge_metrics`
asserts the tracking modules create **no** OTel gauge/counter/histogram — gauges stay ContextCore-side.

## FR-20/21/22 → ContextCore dashboards, filtered by project_id

| Req | View | ContextCore dashboard | Filter |
|-----|------|-----------------------|--------|
| **FR-20** | Delivery project-progress / sprint burndown (M0–M7) | `core/project-progress.json`, `core/sprint-metrics.json` | `project.id = "startd8-benchmark"`, `sprint.id = "summer-2026"` |
| **FR-21** | Execution-run (per run): cell completion %, pass/fail, exclusions, top failure codes | `core/project-progress.json` (per-run project) | `project.id = "startd8-benchmark-run-<spec_hash[:12]>"` |
| **FR-22** | Agent-insights: recent decisions, open blockers, high-confidence insights, **cost-per-decision** | `core/agent-insights.json`, `core/code-generation-health.json` | `project.id = "startd8-benchmark"` |

**Cost-per-decision (FR-22)** is fed by the T2.2 change: `emit_decision(... input_tokens=, output_tokens=)`
→ `gen_ai.usage.*` on the insight span (REQUIRED on the decision path per req v0.4 R2-F4). The
`code-generation-health` dashboard reads those.

**Execution-run pass/fail (FR-21)** correctly **excludes** infra/integrity cells: the T4 reconstructor
labels them `exclusion_reason:infra|integrity`, so the dashboard filters `NOT exclusion_reason=*` for
the model pass/fail tally (req v0.4 R2-F1).

## How to light them up

1. Emit the spans (T1–T4):
   ```bash
   python3 scripts/emit_benchmark_tracking.py --install            # delivery (M0–M7)
   python3 scripts/emit_benchmark_insights.py                      # agent insights
   python3 scripts/track_benchmark_run.py --run-dir <run> --install --insights   # a run's cells
   ```
2. With ContextCore running (OTLP → Tempo/Mimir/Loki → Grafana), open its shipped dashboards and set
   the `project.id` variable to the value in the table above. No new JSON.

> If a bespoke benchmark dashboard is ever wanted beyond ContextCore's templates, author it through the
> **`/dbrd-cr8r`** pipeline (requirements doc → DashboardSpec YAML → generated JSON → provision) — never
> hand-assemble JSON. That is out of scope here (no live metric store in this environment).

---

## Section G — the machine-checkable join contract (T5.4 / R1-S7)

`src/startd8/integrations/join_contract.py` encodes the five Section-G joins as predicates over the
real emitted artifacts and `verify_join_contract()` checks them. The fixture cannot silently drift from
the emitters — `test_join_contract.py::test_join_contract_holds_on_real_artifacts` runs it against
artifacts produced by the actual T2/T3/T4 code.

| Link | Shared attribute | Carried on |
|------|------------------|-----------|
| Business-execution ↔ results Loki | `run_id` + cell-identity (`service`/`model`/`lang`/`rep`) | cell task-span `task.labels` |
| Business-execution ↔ cost | `cell_id` | cost rollup `per_cell` |
| Business-delivery ↔ cost | `milestone:`/`cell:` tag | cost record tags |
| Agent-insight ↔ cost/tokens | `gen_ai.usage.*` | insight span |
| Business ↔ Agent | `project.id` (+ `sprint.id`) | every task/insight span |
