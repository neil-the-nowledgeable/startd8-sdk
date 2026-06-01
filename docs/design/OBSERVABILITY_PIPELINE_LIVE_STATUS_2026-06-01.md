# AI Observability Pipeline — Live Status

**Date:** 2026-06-01
**Author:** investigation (Claude) at user request
**Question answered:** *Of the recent AI-observability capabilities connected with the cap-dev-pipe, which are actually live yet?*
**Scope:** the observability **artifact-generation** pipeline (code/onboarding metadata → Grafana
dashboards / alerts / SLOs / runbooks). **Not** in scope: the separate *Code Observability / Mieruka /
Code Knowledge Graph* initiative (modeling code-structure-as-telemetry) — see `CODE_KNOWLEDGE_GRAPH_DESIGN.md`.

> **Confidence note.** This document corrects three conclusions reached earlier in the same
> investigation. The decisive correction was discovering the live run output in the `strtd8/`
> pilot directory; the initial "never run end-to-end" verdict was an artifact of inspecting stale
> run dirs (Feb–Mar) in the wrong locations.

---

## TL;DR

The observability artifact-generation chain is **genuinely live and producing full, high-quality
artifacts** — verified as recently as **today's run-009** in the `strtd8/` pilot. The only gap
between "artifacts on disk" and "dashboards in Grafana" is a manual provisioning step, which is
intentionally operator-gated. The per-category **dashboard generator was deliberately never built**;
dashboard authoring is **ceded to `/dbrd-cr8r` + jsonnet**.

---

## Where the live runs actually land

```
/Users/neilyashinsky/Documents/dev/strtd8/strtd8/.cap-dev-pipe/pipeline-output/startd8/run-*/observability/
```

**Not** the SDK's own `.cap-dev-pipe/pipeline-output/` and **not** the cap-dev-pipe repo's
`pipeline-output/` — both of those hold stale Feb–Mar runs that predate this work. The `strtd8/`
pilot (Plan Batch Orchestration "Increment 0 by hand") is where Stage 4.5 has actually fired.

| Run | Date | Artifacts generated |
|-----|------|--------------------|
| run-003 / 004 / 005 | May 28–31 | 3 (dashboard spec + SLO + manifest) |
| run-007 / 008 / 009 | May 31 – **Jun 1** | **9 (full set)** |

The 3→9 jump between run-005 and run-007 tracks the SDK commits "Closure 3B native generators for the
5 extended artifact types" and "Gap 4 — emit deployable Grafana JSON via DashboardCreatorWorkflow"
(`b68f090f`), corroborating that the pipeline followed the code.

### run-009 evidence (2026-06-01)

`observability-manifest.yaml` summary:
- `artifacts_generated: 9`, `artifacts_skipped: 0`, `artifacts_errored: 0`
- `artifact_type_coverage: 1.0` (both `service_observability` and `project_observability`)
- per-artifact `quality_score: 1.0`
- `metrics_awaiting_category_home: 10` (the honest cat-4/5 gap counter — see REQ-OAT-041 below)

Artifacts on disk: `alerts/strtd8-alerts.yaml`, `dashboards/strtd8-dashboard-spec.yaml`,
`grafana/dashboards/strtd8-dashboard.json` (**28-panel** RED dashboard, uid `obs-strtd8`),
`slos/strtd8-slo.yaml`, `service-monitors/`, `loki-rules/`, `notifications/`, `runbooks/strtd8-runbook.md`,
`capability-index.yaml`, `observability-quality.json` (populated, 5.5 KB).

---

## The end-to-end chain (3 repos)

```
ContextCore onboarding ──► cap-dev-pipe provenance bridge ──► Stage 4.5 ──► SDK artifact generator ──► /dbrd-cr8r + jsonnet
   (instrumentation_hints)     (resolve-provenance.py)        (run-atomic.sh)   (artifact_generator.py)    (dashboards)
```

| Link | What | Repo | Status |
|------|------|------|--------|
| Produce `instrumentation_hints` / `semantic_conventions` / `derivation_rules` in `onboarding-metadata.json` | ContextCore onboarding + SDK `onboarding_bridge.py` | ContextCore + SDK | **LIVE** (populated in the strtd8 pilot: 5/4/7 items) |
| Provenance bridge (REQ-OPI-100/101/102/103) — detect manifest, extract hints, filter non-services | `resolve-provenance.py`, called from `run-plan-ingestion.sh` | cap-dev-pipe | **WIRED + live** |
| **Stage 4.5** (REQ-UOM-050) — invoke generator, log `/dbrd-cr8r` handoff (REQ-OPI-500) | `run-atomic.sh:473`; gated on `SKIP_OBSERVABILITY != true` + `onboarding-metadata.json`; non-fatal | cap-dev-pipe | **WIRED + fired** |
| Artifact generator — alerts, SLOs, service monitors, runbooks, capability index | `observability/artifact_generator.py` (122 KB, **253 unit tests green**) | SDK (`main`) | **LIVE** |
| Grafana JSON | routed to DashboardCreatorWorkflow (jsonnet → JSON) — see below | SDK → dbrd-cr8r | **LIVE** |

---

## The dashboard generator: deliberately never built → ceded to /dbrd-cr8r + jsonnet

This was the explicit architectural decision, validated against code and decision docs:

1. **`REQ-OAT-041` reserves cat-4 (`project_observability`) and cat-5 (`ai_agent_observability`)
   namespaces "with no generator required."** Its purpose is (a) give already-emitted metrics a
   declared home and (b) let a future generator slot in without re-litigating the taxonomy. It is
   **reserved-not-scheduled** — no requirement or plan step owns building the generator. Only the
   "make the gap visible" half is implemented: `artifact_generator.py:2615` emits
   `metrics_awaiting_category_home` (run-009 reported `10`).

2. **The SDK owns no native Grafana-JSON authoring.** `_convert_dashboards_to_grafana_json`
   (`artifact_generator.py:2445`) routes every `dashboard_spec` through **`DashboardCreatorWorkflow`**
   (the `/dbrd-cr8r` engine), which compiles **jsonnet → Grafana JSON** via
   `dashboard_creator/compiler.py:39 compile_jsonnet()` (gojsonnet or jsonnet binary). Landed as
   commit `b68f090f` (Gap 4 / Closure 4A). This is what produced run-009's `strtd8-dashboard.json`.

3. **Agent-observability dashboards live as hand-authored jsonnet in `startd8-mixin/dashboards/`**
   (`cost_tracking`, `primary_contractor`, `artisan_contractor`, `overview`, `metrics`). The AI-Agent
   plan Phase 5.3 directs "**extend** the cost dashboard into a full agent dashboard, don't fork |
   dashboards/ + mixin" — i.e. extend jsonnet, not write a generator.

### Emit-vs-cede, by orientation

| Orientation | Realization |
|-------------|-------------|
| **Dashboards (human)** | jsonnet / `startd8-mixin` compiled via `/dbrd-cr8r` |
| **Project / cat-4 dashboards** | further **ceded to ContextCore + `/context-core-tracker`** (`OBSERVABILITY_PROJECT_PLAN.md:9`) |
| **Alerts / SLOs / service monitors / runbooks (system/bridge)** | **natively generated** by `artifact_generator.py` |

---

## "AI Agent Observability" is instrumentation, not a new agent

`OBSERVABILITY_AI_AGENT_{PLAN,REQUIREMENTS}.md` (v0.3) implement taxonomy **Category 5** —
instrumenting the SDK's *own* agents/LLM workflows (cost, tokens, sessions, context usage, latency,
truncation, traces, output quality). There is no autonomous "agent that performs observability" to build.

- **Phases 0–3 SHIPPED to `main`** (merge `5babc995`): descriptor schema `category`/`orientation`
  axes, descriptor↔emission parity test, dotted metric-name standardization, descriptor→`manifest_declared`
  loop, plus declaring all 23 live emitters.
- **C2 orientation-aware quality scoring** shipped (`e44197e1`).
- **Remaining:** reserved signal additions — REQ-AAO-010 (eval-score hook) and REQ-AAO-011
  (tool-use telemetry), both marked "may be reserved," uncommitted; and the cat-5 *generator* (parked
  under REQ-OAT-041 as above).

---

## What is live vs not (summary)

| Capability | Status |
|-----------|--------|
| ContextCore → `instrumentation_hints` in onboarding metadata | **LIVE** (in the strtd8 pilot project) |
| Provenance bridge (REQ-OPI-100–103) | **LIVE / wired** |
| Stage 4.5 → SDK artifact generator → 9 artifacts | **LIVE** (run-009, quality 1.0) |
| Native generation: alerts / SLOs / service monitors / runbooks / capability index | **LIVE** |
| Grafana JSON via `/dbrd-cr8r` + jsonnet | **LIVE** (deployable on disk) |
| AI-Agent observability instrumentation (Phases 0–3, C2) | **LIVE on `main`** |
| Grafana **provisioning** (push to a running Grafana) | **NOT done** — operator-manual by design (REQ-OPI-502) |
| Task threshold/SLO enrichment (REQ-OPI-200) | **Partial** |
| Contractor prompt-context injection (REQ-OPI-300) | **Design-only** |
| Seed `observability_contract` (REQ-OPI-600) | **Design-only** |
| Cat-4/5 artifact **generator** (REQ-OAT-041) | **Reserved, not scheduled** — ceded to dbrd-cr8r/jsonnet + ContextCore |
| AI-Agent eval hook / tool-use telemetry (REQ-AAO-010/011) | **Reserved, uncommitted** |
| Observability AI **Agent** (as a thing to build) | **N/A** — misnomer; it's instrumentation, already shipped |
| Code Observability / Mieruka / CKG | **Design + spike**, blocked on tree-sitter/codebleu pin (separate track) |

---

## Highest-value next steps

1. **Provision a dashboard.** Take a pilot run's `dashboards/*-dashboard-spec.yaml` (or the compiled
   `grafana/dashboards/*.json`) through `/dbrd-cr8r --provision` to get the first dashboard *in* a
   running Grafana — that closes the only gap between "live generation" and "live observability."
2. **Decide REQ-OAT-041's fate explicitly.** Either keep the reserved-not-scheduled cede (dbrd-cr8r +
   jsonnet/mixin for dashboards) as the permanent answer and document it as such, or schedule the
   cat-5 generator. Right now it is implicit.
3. **Close REQ-OPI-200/300/600** if richer, observability-aware code generation is wanted
   (thresholds/SLOs threaded into tasks; observability section in contractor prompts; structured seed contract).

## Key references

- cap-dev-pipe: `design/REQ_OBSERVABILITY_PIPELINE_INTEGRATION.md`, `resolve-provenance.py`, `run-atomic.sh` (Stage 4.5)
- SDK: `src/startd8/observability/artifact_generator.py`, `src/startd8/dashboard_creator/compiler.py`, `startd8-mixin/`
- SDK docs: `OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (REQ-OAT-041), `OBSERVABILITY_AI_AGENT_{PLAN,REQUIREMENTS}.md`, `OBSERVABILITY_PROJECT_PLAN.md`
- Live run output: `…/strtd8/strtd8/.cap-dev-pipe/pipeline-output/startd8/run-009-20260601T0045/observability/`
