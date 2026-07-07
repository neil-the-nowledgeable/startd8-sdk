# Deterministic SRE Observability + Business Onboarding Generation (dogfooded on the Benchmark)

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-14
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Relates to:** `docs/design/benchmark-observability-tracking/` (T0–T5 tracking), the ContextCore
retail demo (`retail-blue-planet` in `docs/demos/DEMO_REGISTRY.yaml`), `observability/`,
`dashboard_creator/`, `startd8-mixin/`

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the real generator/portal input contracts and the benchmark's actual
> telemetry. It corrected the core design (>30% of requirements revised) — the loop working.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-3/4: drive `observability/artifact_generator` with a "project pseudo-service" for SRE dashboards | `extract_service_hints()` **requires a `transport` field** (`http`/`grpc`) and the generator synthesizes http/grpc **RED panels** (`_ensure_red_coverage`, protocol error filters) irrelevant to a project. `convention_metrics` accepts arbitrary names, so it's *possible* but produces noise. | **Reframe:** for project dashboards, drive **`DashboardCreatorWorkflow` directly** with project-metric `DashboardSpec`s (OQ-1/OQ-2). Use `artifact_generator` only if treating the **harness as a real service** (RED) — separate concern. |
| FR-3: direct dashboard path is uncertain | `DashboardCreatorWorkflow.run({"spec": dict})` accepts a `DashboardSpec` with **arbitrary PromQL panels** — zero effort, full pipeline (jsonnet→Grafana JSON). | FR-3 simplified: build `DashboardSpec` YAML directly; **no artifact_generator needed** for project dashboards. |
| FR-4: the SRE dashboard shows harness ops (queue depth, 429/5xx, `tracking.dropped`, FR-50) | Those metrics are **PLANNED, NOT emitted** — infra errors are only *classified* (`infra_fail`), not metricized. | **FR-4a deferred:** no data. SRE dashboards use what IS emitted: `startd8.cost.*`, `startd8.requests/tokens/response_time`, + ContextCore `task.*` (if ingested). |
| (implicit) the benchmark's pass/fail/quality/cost-by-model is queryable from Prometheus | **It's STATIC** — lives in `cells.json`/`aggregate.json`, not live metrics. Grafana queries Prometheus/Mimir. | **NEW FR-18 (data path):** to dashboard pass/fail, either (a) ContextCore ingests the cell **task spans** → `task.count_by_status` keyed by `project_id`, or (b) a static-data path. Must choose. |
| FR-7/8/9: author `onboarding-index.yaml` role_views and render via `portal_spec_builder` | `portal_spec_builder.py` uses a **hard-coded** persona model (`operator/engineer/manager/executive`, `_PERSONA_VALUE` literals); it does **NOT** read `onboarding-index.yaml`/`role_views`. Grep: **zero** SDK references to `role_views`/`onboarding-index`/`section_order`. | **Major reframe.** The reuse path is `portal_spec_builder` **as-is** (4 hard-coded personas, `metadata`-driven sections). The retail-demo `role_views` pattern has **no SDK renderer** — building one is net-new (FR-7/9/12/14 are gaps, not reuse). |
| FR-1/OQ-5: declare via ProjectContext CRD | SDK generators read **`.contextcore.yaml` (ContextManifest v1alpha2)**, not the K8s CRD (`load_business_context()`). A repo-root `.contextcore.yaml` exists but is scoped to `startd8-sdk`, not the benchmark. | FR-1 narrowed: author a **benchmark `.contextcore.yaml`** (the CRD is out of scope, no K8s). |
| FR-16: generate $0 offline | **Generation** is $0/offline (specs/JSON/jsonnet on disk), but the **direct dashboard path requires jsonnet+startd8-mixin at runtime** and **rendering** needs a live Mimir/Tempo/Grafana stack (or fixtures loaded into one). No standalone "fixtures→dashboard render." | FR-16 split: **generation offline ✓**; **rendering needs the stack** (or `contextcore demo generate` fixtures loaded into a local stack). |

**Resolved open questions:**
- **OQ-1 → Direct `DashboardSpec` path for project dashboards** (arbitrary PromQL accepted); `artifact_generator` reserved for treating the harness as a real RED service.
- **OQ-2 → Confirmed** the direct path works end-to-end ($0 generation; jsonnet+mixin required at runtime).
- **OQ-3 → `portal_spec_builder` uses its own hard-coded persona model**, not `onboarding-index.yaml`. role_views is unimplemented in the SDK.
- **OQ-5 → `.contextcore.yaml` (ContextManifest)** is the canonical source for the SDK generators (not the CRD).
- **OQ-6 → Harness ops metrics (FR-50) are NOT emitted.** Scope to emitted metrics (cost/session) + ContextCore `task.*` + static aggregate.
- **OQ-4 → Partial.** Generation is offline; rendering needs a stack. `contextcore demo generate` produces backdated fixture spans but there's no fixtures→dashboard-JSON renderer.

*Still open: OQ-7 (first-slice scope) — now sharpened by the above.*

---

## 1. Problem Statement

We have a rich set of **deterministic ($0, no-LLM) generators** for observability and onboarding
artifacts spread across the SDK and ContextCore, plus a fully-tracked dogfood project (the Summer
2026 Benchmark, T0–T5). What we do **not** have is the end-to-end wiring that takes **one
declarative project context** and produces **(a) the SRE observability artifact set** and **(b) a
per-persona business-onboarding portal** — proven on a real project. The retail demo shows the
*pattern* but documents the *gaps* (no render host, generated views uncommitted, manifest not wired).

The goal: **declare the benchmark as a ContextCore project once, and deterministically generate both
audiences' artifacts from it** — closing the documented gaps as needed, and surfacing where the
existing generators genuinely fit vs. where the benchmark's project-shape breaks their service-shaped
assumptions.

### Gap table (generators that exist vs. what's missing for this goal)

| Component | Current State | Gap for this goal |
|-----------|--------------|-------------------|
| **jsonnet dashboard engine** (`dashboard_creator/` + `startd8-mixin`) | DashboardSpec YAML → jsonnet (grafonnet) → Grafana JSON; $0; invoked by `DashboardCreatorWorkflow` | Works; need to drive it from the benchmark's project context, not just per-service RED |
| **observability artifact generator** (`observability/artifact_generator`) | 8 types (dashboard spec, alerts, SLOs, ServiceMonitor, notif policy, Loki rules, runbook, capability index) from `onboarding-metadata.json` + `.contextcore.yaml`; derives severity/thresholds from criticality/SLOs | **Service-oriented (RED)** — the benchmark is a *project*, not a microservice; its signals are burndown/velocity/cost/pass-rate, not http/grpc RED. Impedance to resolve. |
| **ContextCore operator** (ProjectContext CRD → ServiceMonitor/PrometheusRule) | Active; derives K8s SLO/alert from CRD | Need a ProjectContext for the benchmark; no K8s in the dogfood env (CRD may be paper-only) |
| **ContextCore project metrics** (burndown/velocity/WIP from spans) | Computed `metrics.py`, exported to Mimir | The benchmark's tracking spans (T0–T5) feed these — but only when ContextCore runs (`contextcore.agent` absent in dev env) |
| **persona onboarding portal** (`portal_spec_builder.py`) | Renders per-persona Grafana portal (operator/manager/exec/engineer) | Phase-1 (service inventory); value props hard-coded; not driven by `onboarding-index.yaml` role_views |
| **onboarding role_views IA** (`onboarding-index.yaml`, retail demo) | Per-persona ordered sections (default template + role overrides) as **data** | **No render host** (§1.3 gap); generated views gitignored/uncommitted; artifact manifest not wired; ai_agent has no role |
| **benchmark tracking** (T0–T5, just shipped) | Emits delivery + execution-cell task spans, agent insights, cost rollups, join contract; CLIs to emit | Not yet declared as a ContextCore project; not wired into the generators |

---

## 2. Requirements

### Section A — Declare the benchmark as a ContextCore project

- **FR-1.** Author a **ProjectContext / `.contextcore.yaml`** for the benchmark declaring: project
  identity (`startd8-benchmark`, sprint `summer-2026`), business context (criticality, owner, value),
  SLO/requirements (where meaningful), risks, design links, and the persona/role set this project
  serves. This is the **single declarative source** the generators read.
- **FR-2.** Reconcile the **two project identities** the tracking layer emits — `startd8-benchmark`
  (delivery) and `startd8-benchmark-run-<hash>` (per execution run) — into the project declaration so
  generated artifacts target the right `project_id`(s).

### Section B — SRE observability artifacts (operator persona)

- **FR-3.** Deterministically generate the benchmark's **project dashboard(s)** by building
  `DashboardSpec` YAML directly and running `DashboardCreatorWorkflow` (→ jsonnet/startd8-mixin →
  Grafana JSON), $0. *(v0.2: this REPLACES driving the service-oriented `artifact_generator` — the
  direct path accepts arbitrary PromQL panels over project metrics, with no http/grpc RED noise.)*
  Target panels: cost burn (`startd8.cost.total` by model/project), delivery burndown + WIP
  (ContextCore `task.count_by_status`/`task.wip` by `project.id`), execution pass/fail (see FR-18).
- **FR-4.** *(v0.2 reframed)* Cover the two SRE views with the **emitted** signals:
  - **FR-4a — harness ops self-monitoring (DEFERRED):** parent FR-50 metrics (queue depth, 429/5xx,
    `tracking.dropped`, sandbox overhead) are **not emitted today** — no data. Note as future; if/when
    emitted, the same direct-DashboardSpec path adds the panels.
  - **FR-4b — run operational health:** cell completion %, pass/fail **excluding `exclusion_reason`**,
    cost-vs-budget — sourced per FR-18.
- **FR-5.** Generate a **runbook** for the benchmark harness (incident response: dead key / quota /
  sandbox violation / budget abort) — `generate_runbook()` from `artifact_generator` IS reusable here
  (markdown from declared risks + owners; not service-RED-coupled). Reuse it.
- **FR-6.** Derive **alert thresholds from declared business context** (criticality → severity; budget
  ceiling → cost-abort alert; pass-rate floor → quality-regression alert), reusing the existing
  criticality→severity + threshold-derivation machinery (`_CRITICALITY_TO_SEVERITY`, `_resolve_threshold`).
  *(v0.2: alerts that need a live metric — pass-rate, cost burn — depend on FR-18's data path.)*

### Section C — Business onboarding portal (PM / eng-leader / compliance personas)

- **FR-7.** *(v0.2 reframed — the SDK has no `role_views` renderer.)* For the dogfood, generate the
  per-persona portal via the **existing `portal_spec_builder.py`** and its built-in personas
  (`operator`/`engineer`/`manager`/`executive`) — the reuse path. The retail-demo `onboarding-index.yaml`
  **`role_views`** pattern (sre/compliance-officer/engineering-director ordered sections) is a
  **documented gap with no SDK renderer**; authoring it + a renderer is **net-new** and split to FR-12.
- **FR-8.** Deterministically generate the **per-persona onboarding portal** for the benchmark via
  `portal_spec_builder.build_all_portal_specs()` → `DashboardCreatorWorkflow`, feeding it the
  benchmark's `BusinessContext` (FR-1) + a `metadata` dict carrying objectives, the cost/pass-rate
  rollups, and agent-insight summaries (from the tracking artifacts: milestones.yaml, insights.yaml,
  aggregate.json). Sections are `metadata`-driven (the builder's actual contract).
- **FR-9.** *(v0.2: not supported as-is — `_PERSONA_VALUE` is hard-coded.)* Sourcing persona value
  props from a manifest requires a **small extension** to `portal_spec_builder` (read
  `metadata["persona_value"]` overrides, fall back to defaults). Treat as an optional enhancement, not
  a core dogfood requirement; the built-in value props suffice for the first slice.

### Section D — Wire the benchmark's tracking spans as the data source

- **FR-10.** The portal/dashboards MUST read the tracking data the T0–T5 layer produces. *(v0.2: the
  layer emits **spans + static JSON**, not live Prometheus metrics for pass/fail — see FR-18 for the
  data path.)* Delivery burndown ← ContextCore `task.*` from milestone spans; execution pass/fail+cost
  ← cell spans / `aggregate.json`; agent insights ← `insights.yaml` summaries into portal `metadata`.
- **FR-11.** Produce an **artifact manifest** for the benchmark (the "Your Toolkit" source) listing the
  generated + tracking artifacts, closing the retail-demo gap where the manifest isn't wired.
- **FR-18.** *(v0.2 NEW — the data-path decision the planning pass surfaced.)* Decide and specify how
  the benchmark's **execution pass/fail/quality/cost-by-model** (today STATIC in `cells.json`/
  `aggregate.json`) reaches a Grafana panel. Options: **(a)** ContextCore ingests the cell **task
  spans** (`reconstruct_run_tracking --install`) → `task.count_by_status` / `task.wip` by
  `project_id=startd8-benchmark-run-<hash>` → live PromQL panels (preferred — reuses T4 + ContextCore
  metrics); **(b)** a thin exporter that pushes `aggregate.json` rollups as metrics; or **(c)** a
  static-table panel. The requirement: the dashboard data path is **explicit and reproducible**, not
  assumed-live. Default lean: **(a)**, with cost panels from the already-live `startd8.cost.*`.

### Section E — Close the documented gaps (only as needed for the dogfood)

- **FR-12.** *(v0.2 — clarified as a NET-NEW gap, deferred past the first slice.)* A
  **`role_views` renderer** (read `onboarding-index.yaml` ordered sections per persona → portal) does
  **not exist in the SDK**; `portal_spec_builder`'s hard-coded personas are used instead (FR-7). If the
  retail-demo role_views fidelity (sre/compliance-officer/engineering-director custom sections) is
  wanted, building the renderer is a **separate workstream** — out of the dogfood's first slice.
- **FR-13.** **Commit the generated views**: unlike the retail demo (generated onboarding views
  gitignored), the benchmark's artifacts MUST be **regenerable from a script/CLI** (the reuse path is a
  thin `scripts/generate_benchmark_observability.py` orchestrating the direct DashboardSpec build +
  `portal_spec_builder` + `generate_runbook`), so they're reproducible, not hand-maintained.
- **FR-14.** *(v0.2: tied to FR-12.)* The **`ai_agent` persona gap** only matters if the role_views
  renderer is built; with `portal_spec_builder`'s 4 personas there's no agent persona. Defer with FR-12;
  agent reasoning is already captured as **insights** (T3) regardless of a portal persona.

### Section F — Reuse & integration constraints

- **FR-15.** **Reuse, don't reimplement.** Use `observability/artifact_generator`, `dashboard_creator/`
  + `startd8-mixin`, `portal_spec_builder.py`, the ContextCore operator/metrics, and the T0–T5 tracking
  CLIs. Net-new code is limited to the benchmark's declarative inputs + the wiring/adapter that resolves
  the project-vs-service impedance.
- **FR-16.** **Graceful degradation (v0.2 split):** *artifact generation* MUST work $0 even without a
  live ContextCore/Grafana/Mimir — **caveat:** the direct `DashboardCreatorWorkflow` path requires the
  **jsonnet binary + startd8-mixin at runtime** (verify present; both are in-repo). *Rendering* the
  dashboards (showing data) needs a live stack OR `contextcore demo generate` fixtures loaded into a
  local stack — that is the separate, optional provisioning step.
- **FR-17.** **Honor the ownership boundary:** the SDK generates the artifacts; ContextCore owns the
  derived project metrics (burndown/velocity) and provisioning. Don't duplicate the metric computation.

---

## 3. Non-Requirements

- **NR-1.** Not building a new dashboard/observability generator — reusing the existing jsonnet + artifact
  generators.
- **NR-2.** Not standing up a live ContextCore/Grafana/Mimir stack in this work (provisioning is optional,
  out-of-band).
- **NR-3.** Not generating real end-user/business *content* (bucket 4) — only the structural observability
  + onboarding *artifacts* (buckets 1–3).
- **NR-4.** Not changing the T0–T5 tracking layer's emission (it's the data source; this consumes it).
- **NR-5.** Not solving generic multi-project portfolio onboarding — the benchmark is the single dogfood.
- **NR-6.** Not authoring a bespoke web portal app if the Grafana-dashboard portal path suffices.

## 4. Open Questions

- **OQ-1.** ✅ **RESOLVED:** Bypass the service-oriented `artifact_generator` for project dashboards;
  drive `DashboardCreatorWorkflow` directly with project-metric `DashboardSpec`s. `artifact_generator`
  reserved for treating the harness as a real RED service (separate, deferred).
- **OQ-2.** ✅ **RESOLVED (split confirmed):** ContextCore ships project-progress/sprint/agent-insights
  (delivery + agent views) — **reuse those** (point `project_id` at the benchmark). Generate only what
  ContextCore lacks: the **execution-run** dashboard (pass/fail+cost per run) and (future) harness ops.
- **OQ-3.** ✅ **RESOLVED:** `portal_spec_builder` uses its own hard-coded personas, NOT
  `onboarding-index.yaml`. role_views has no SDK renderer (FR-12, deferred).
- **OQ-4.** ✅ **RESOLVED:** Generation offline ✓; rendering needs a live stack or fixtures loaded into
  one (`contextcore demo generate` → load into local Tempo/Mimir). No fixtures→dashboard-JSON renderer.
- **OQ-5.** ✅ **RESOLVED:** `.contextcore.yaml` (ContextManifest) is the SDK generators' source; CRD
  out of scope.
- **OQ-6.** ✅ **RESOLVED:** FR-50 ops metrics NOT emitted → FR-4a deferred; use `startd8.cost.*` +
  session + ContextCore `task.*`.
- **OQ-7.** **Scope of the first dogfood slice** (still open — the decision for Phase 6): given the
  above, the realistic minimal slice is **(1)** a benchmark `.contextcore.yaml`; **(2)** one **direct
  execution-run `DashboardSpec`** (cost from `startd8.cost.*` + pass/fail from FR-18(a) cell task
  spans); **(3)** a `portal_spec_builder` portal for 1–2 personas; **(4)** the harness **runbook** —
  all **generated** ($0), with **rendering deferred** to a stack-up step. Confirm this is the slice vs.
  a broader first cut.
- **OQ-8.** *(new)* **Does ContextCore actually ingest the installed cell task spans into `task.*`
  metrics in our env?** `contextcore.agent` is absent here; FR-18(a) assumes a running ContextCore
  metrics pipeline. Validate, or fall back to FR-18(b) exporter for the demo.

---

*v0.2 — Post-planning self-reflective update. Core design corrected: direct-DashboardSpec path replaces
the service-oriented generator for project dashboards; the role_views portal is a documented gap (no SDK
renderer) so the reuse path is `portal_spec_builder`'s built-in personas; harness-ops metrics deferred
(unemitted); a new data-path requirement (FR-18) for static-vs-live pass/fail; rendering needs a stack.
6 open questions resolved, 1 added. First-slice scope (OQ-7) pending.*
