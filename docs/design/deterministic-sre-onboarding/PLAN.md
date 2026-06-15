# Implementation Plan — Deterministic SRE + Onboarding Generation (dogfooded on the Benchmark)

**Version:** 0.1 (Draft)
**Date:** 2026-06-14
**Status:** Draft
**Implements:** `REQUIREMENTS.md` (internal v0.2)

---

## 0a. Spike validation (2026-06-14 — the mechanism is PROVEN)

A proof spike compiled a real **project-metric** DashboardSpec end-to-end:
`DashboardSpec → DashboardCreatorWorkflow → generate jsonnet → jsonnet binary (Go v0.22.0) + startd8-mixin
grafonnet → valid Grafana JSON (schemaVersion 39, 5 KB)`. Panels carried `startd8_cost_total{project=~…}`
(live today) + `task_wip{project_id="startd8-benchmark"}` (ContextCore), auto-grouped into `Cost`/`Delivery`
rows. **Verdict: the load-bearing direct-DashboardSpec path works for project dashboards.** Three concrete
gotchas the spike surfaced (now baked into P1):
- **UID must match `cc-{pack}-{kebab-name}`** (e.g. `cc-benchmark-cost`). Enforced by DC-006.
- **A `variables` entry is required** (≥ the `prometheusDatasource` datasource var) or JSON validation fails
  on a missing `templating` section.
- **The mixin's `vendor/` (grafonnet) must be present** — it's `jb install`-ed in the primary checkout but
  **not committed**, so a fresh worktree/CI needs `jb install` (or vendored grafonnet) before compile. The
  toolchain guard (FR-16) must check for `vendor/`, not just the jsonnet binary.

Rendering *data* still needs a live Prometheus/Mimir; the spike proves **generation + valid JSON**, and the
cost panels would show real numbers against a scrape of the already-emitted `startd8.cost.*`.

## 0. Design summary (the corrected shape)

Two parallel deterministic outputs from **one** declarative source (`benchmark.contextcore.yaml`):

```
benchmark.contextcore.yaml  ─┬─► [SRE]  DashboardSpec (direct) → DashboardCreatorWorkflow
 (ContextManifest)           │          → jsonnet/startd8-mixin → execution-run dashboard JSON
 + tracking artifacts        │          + generate_runbook() → harness runbook.md
 (cells/aggregate/insights)  │
                             └─► [Onboarding]  portal_spec_builder.build_all_portal_specs(
                                        business, metadata) → DashboardCreatorWorkflow → portal JSON
```

**What we reuse (no new generators):** `dashboard_creator/` (`DashboardCreatorWorkflow`, `DashboardSpec`),
`startd8-mixin` (grafonnet), `observability/portal_spec_builder.py`, `observability/artifact_generator`'s
`generate_runbook()`, the T0–T5 tracking CLIs + `cost_linkage`/`tracking` rollups, ContextCore's shipped
project-progress/sprint/agent-insights dashboards (point `project_id` at the benchmark).

**What's net-new (thin):** the benchmark's declarative inputs + a small orchestrator CLI + the FR-18
data-path glue. **Deferred:** harness-ops metrics (FR-4a, unemitted), the `role_views` renderer (FR-12/14),
manifest-sourced persona value props (FR-9).

---

## 1. Sequencing — the first dogfood slice (OQ-7), then extensions

```
P0 Declare project ──► P1 Execution-run dashboard ──► P2 Runbook ──► P3 Onboarding portal ──► P4 CLI
   (FR-1/2)              (FR-3/4b/18)                  (FR-5)         (FR-7/8)                 (FR-13)
                              │
                              └─ P5 data-path validation (FR-18/OQ-8) gates the *live* panels
Deferred: harness ops (FR-4a) · role_views renderer (FR-12/14) · value-prop manifest (FR-9) · artifact_generator-as-service
```

Each P-step **generates artifacts to disk ($0)**; rendering is the optional stack-up step (P5).

---

## 2. Workstreams

### P0 — Declare the benchmark project (FR-1/2, OQ-5 resolved)
- New `docs/design/deterministic-sre-onboarding/benchmark.contextcore.yaml` — a **ContextManifest
  v1alpha2** (mirror the repo-root `.contextcore.yaml` shape that `load_business_context()` reads):
  `spec.project.id=startd8-benchmark`, `spec.business` (criticality/owner/value), `spec.requirements`
  (budget ceiling, pass-rate floor as SLO-ish targets), `spec.risks` (FR-44/45), `spec.observability`
  (datasource, dashboardPlacement), and the persona set.
- Reconcile the two `project_id`s: delivery `startd8-benchmark`; per-run `startd8-benchmark-run-<hash>`.
  Document that the **delivery** project uses ContextCore's shipped dashboards; the **run** project gets
  the generated execution dashboard.
- **Acceptance:** `load_business_context()` parses it into a `BusinessContext` with the expected fields.

### P1 — Execution-run dashboard, direct path (FR-3, FR-4b, FR-18)
- New `src/startd8/benchmark_matrix/observability.py`: `build_run_dashboard_spec(run_dir, business) ->
  DashboardSpec` — builds panels directly (no `artifact_generator`):
  - **Cost** (live today): `sum(startd8_cost_total{project="startd8-benchmark-run-<hash>"}) by (model)`.
  - **Pass/fail** (FR-18(a)): `sum(task_count_by_status{project_id="startd8-benchmark-run-<hash>"}) by
    (task_status)`, with a panel excluding `exclusion_reason` cells; **or** FR-18(b) static-export panel.
  - **Quality/latency**: from `aggregate.json` (static-table panel) or exported metrics.
- Feed the spec to `DashboardCreatorWorkflow.run({"spec": spec_dict, "output_dir": ...})` → Grafana JSON.
- **Toolchain guard (FR-16):** preflight `discover_mixin()` + `detect_toolchain()`; if jsonnet/mixin
  absent, emit the `DashboardSpec` YAML and warn (don't hard-fail the generation step).
- **Acceptance:** a `DashboardSpec` with ≥3 panels generates Grafana JSON when the toolchain is present;
  emits the spec YAML otherwise.

### P2 — Harness runbook (FR-5)
- Reuse `observability/artifact_generator_generators.generate_runbook()` with a `ServiceHints`-ish shim
  carrying the benchmark's risks/owners (it's markdown-from-context, not RED-coupled). Output
  `runbook.md`: dead-key / quota / sandbox-violation / budget-abort response, escalation from owners.
- **Acceptance:** runbook.md lists the 4 incident classes + escalation contacts from the manifest.

### P3 — Onboarding portal (FR-7, FR-8 — reuse path)
- New code in the orchestrator: build the `metadata` dict the portal expects — `objectives` (from
  manifest strategy), cost/pass-rate rollups (from `cell_costs_from_cells_json` + `aggregate.json`),
  agent-insight summary (from `insights.yaml`), service inventory (the benchmark's "services" = the
  run's services or the tracking projects).
- Call `portal_spec_builder.build_all_portal_specs(business, services, report, metadata)` for the
  first-slice personas (`manager` = PM view: progress/cost/quality; `operator` = SRE view) →
  `DashboardCreatorWorkflow` → portal JSON.
- **Acceptance:** portal specs build for ≥2 personas with the benchmark's objectives + cost panels.

### P4 — Orchestrator CLI (FR-13)
- New `scripts/generate_benchmark_observability.py`: one entry that runs P1+P2+P3 from
  `benchmark.contextcore.yaml` + a run dir → writes all artifacts under an output dir; `--provision`
  optional. Makes everything **regenerable** (closes the retail-demo "gitignored views" gap).
- **Acceptance:** one command regenerates the full artifact set deterministically.

### P5 — Data-path validation (FR-18 / OQ-8) — gates *live* panels
- Verify whether ContextCore ingests the installed cell task spans into `task.*` metrics in our env
  (`contextcore.agent` is absent today). If yes → FR-18(a) live panels work after
  `track_benchmark_run.py --install`. If no → implement the thin FR-18(b) exporter (push
  `aggregate.json` rollups as metrics) **or** document the stack-up: docker-compose (Mimir/Tempo/Grafana)
  + `reconstruct_run_tracking --install` + `contextcore demo generate`/`load` for fixtures.
- **Acceptance:** a documented, reproducible path from "run finished" → "dashboard shows pass/fail+cost."

---

## 3. Deferred (explicitly out of the first slice)
- **FR-4a harness ops self-monitoring** — parent FR-50 metrics unemitted; revisit when emitted.
- **FR-12/FR-14 `role_views` renderer + `ai_agent` persona** — net-new; the SDK has no renderer. Separate
  workstream if retail-demo fidelity is wanted.
- **FR-9 manifest-sourced persona value props** — small `portal_spec_builder` extension; optional.
- **`artifact_generator`-as-service** (treating the harness as a real RED service) — only if the harness
  gets real RED instrumentation.

## 4. Traceability (FR → step)
| FR | Step | FR | Step |
|----|------|----|------|
| FR-1/2 | P0 | FR-11 | P4 (manifest) |
| FR-3 | P1 | FR-12/14 | deferred |
| FR-4a | deferred | FR-13 | P4 |
| FR-4b | P1 | FR-15 | all (reuse) |
| FR-5 | P2 | FR-16 | P1 guard / P5 |
| FR-6 | P1 (alerts) | FR-17 | P0/P5 (CC owns metrics) |
| FR-7/8 | P3 | FR-18 | P1 + P5 |
| FR-9 | deferred | OQ-7 | §1 slice |
| FR-10 | P1/P3 | OQ-8 | P5 |

## 5. Risks
- **R1 — no live data in dev env** (OQ-8): the dashboards may generate but not render (no Mimir + no
  ContextCore ingestion). Mitigation: separate generation (provable now) from rendering (stack-up, P5);
  use `contextcore demo generate` fixtures to demo.
- **R2 — jsonnet/mixin runtime dependency** (FR-16): the direct path hard-fails without them. Mitigation:
  P1 toolchain guard emits the spec YAML + warns.
- **R3 — portal persona mismatch:** `portal_spec_builder`'s 4 personas ≠ the benchmark's
  PM/eng-leader/compliance role_views. Mitigation: map to the nearest built-in (PM→manager,
  eng-leader→executive, SRE→operator); role_views fidelity deferred (FR-12).
- **R4 — scope creep into the role_views renderer.** Mitigation: it's explicitly deferred; first slice
  uses the existing builder.

## 6. Out of scope (from requirements NR-1..6)
No new generator; no live-stack standup as a deliverable; no real end-user content; no change to T0–T5
emission; no generic multi-project portfolio; no bespoke web portal if the Grafana path suffices.

---

*Plan v0.1 — traces requirements v0.2. First slice = P0–P4 generated $0, rendering deferred to P5. Three
genuine gaps confirmed (role_views renderer, harness-ops metrics, static-vs-live data path); the rest is
reuse + thin glue.*
