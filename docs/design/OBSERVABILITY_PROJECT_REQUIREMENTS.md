# Project Observability — Requirements (Taxonomy Category 4)

**Date:** 2026-05-31
**Status:** Draft v0.1 — surfacing existing telemetry as formal requirements
**Lineage:** Instantiates **Category 4 — Project Observability** of
`OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (the "reserved — signals emitted, no generator"
row). Evidence base: a read-only telemetry inventory of `src/startd8/` (task_tracking_emitter,
integrations/contextcore, otel_conventions, complexity/, improvement_tracking, contractors/
prime_postmortem + batch_postmortem, observability/manifest + collector).
**Subject observed:** the **project's development lifecycle** — task progress/status, hierarchy,
phase execution, complexity/blast-radius, delivery & output quality, velocity.

---

## 0. Motivation

The SDK already produces a substantial body of *development-lifecycle* telemetry — task state,
phase/task spans, complexity signals, and rich delivery-quality data (Kaizen, improvement deltas,
batch velocity). But it accreted as internal pipeline instrumentation and, crucially, **ownership
is split** with ContextCore in a way nothing documents.

**The defining finding (vs Category 5):** the category-4 *metrics* the run-007 onboarding metadata
declared — `contextcore_task_progress`, `contextcore_task_status`,
`contextcore_install_completeness_percent` — are **NOT emitted by startd8**. They are **owned by
ContextCore** (the external `TaskTracker`). startd8's contribution is the **raw lifecycle signals**
(task **state files**, OTel **spans**, Kaizen/velocity **JSON**) that ContextCore and the
`/context-core-tracker` + `/time-series-progress-tracker` skills consume to produce those gauges and
the burndown/velocity dashboards. Category 4 is therefore a **shared, split-ownership** category —
unlike Category 5, where the SDK emits its own metrics directly.

This document surfaces what the SDK produces, draws the startd8↔ContextCore boundary explicitly, and
names the gaps (rich signals stuck in JSON, span conventions absent from the descriptor manifest, no
live progress deltas).

This is a **requirements** document. Code alignment is a separate, follow-up pass.

---

## 1. What we already collect (the evidence base)

### 1.1 Task lifecycle — state files + zero-point events (startd8 produces ✅, ContextCore consumes)

`workflows/builtin/task_tracking_emitter.py` (`emit_task_tracking_artifacts()`) writes **SpanState
v2** task state files + an NDJSON event log, installable to `~/.contextcore/state/{project_id}/`:
- hierarchy **epic → story → task** via `parent_span_id`;
- per-task attributes: `task.{id,title,type,status,priority,story_points,depends_on,labels,
  feature_id,target_files,estimated_loc}`, `project.id`, `sprint.id`;
- **zero-point** `task.created` event with `percent_complete: 0` (burndown seed).

**Owner:** startd8 produces the files; **ContextCore** consumes them and owns the metric-ified
`task.status`/progress.

### 1.2 Phase & task OTel spans (startd8 emits ✅ via OTLP → Tempo)

`otel_conventions.py` defines the conventions; `contractors/artisan_contractor.py` +
`artisan_phases/runner.py` emit them:
- `phase.{type}.attempt.{n}` — `phase.{name,status,cost,duration_seconds}`;
- task spans — `task.{id,title,domain,phase,status,cost,attempts,complexity_tier,blast_radius}`.

### 1.3 Complexity / scope (startd8 emits ✅ as span attributes)

- `task.complexity_tier` (SIMPLE/MODERATE/COMPLEX) — `complexity/classifier.py`;
- `task.blast_radius` (caller count, threshold tier-3 ≥5) — `complexity/signals.py`.

### 1.4 Delivery & output quality (startd8 produces ✅ — but JSON/YAML, **not** metrics)

- **Improvement tracking** (`improvement_tracking.py`): per-version document-quality deltas across 6
  categories (Completeness, Clarity, Consistency, Testability, Maintainability, DX) →
  `project-index-local.yaml`.
- **Kaizen / post-mortem** (`contractors/prime_postmortem.py`): `root_cause` (16-value enum),
  `pipeline_stage`, dual scoring (PASS ≥0.8 / PARTIAL / FAIL <0.4), cost-outlier + cross-feature
  pattern detection, `query_security_score` → `kaizen-metrics.json`, `prime-postmortem-report.json`,
  `kaizen-suggestions.json`.
- **Batch velocity** (`contractors/batch_postmortem.py`): `tasks_per_run_avg`, `trend`
  (stable/accelerating/decelerating), `estimated_runs_remaining`, persistent-failure tracking
  (same task failing across ≥2 runs) → JSON ledger.

### 1.5 The `contextcore_task_*` gauges — **ContextCore-owned, not SDK-emitted** ❌

`contextcore_task_progress`, `contextcore_task_status`, `contextcore_install_completeness_percent`
appear only in metadata/test declarations; **no emission site exists in startd8**. ContextCore's
`TaskTracker` produces them from the §1.1 state files.

### 1.6 Descriptor-manifest status (gap ❌)

Unlike cost/session metrics, the project-obs **`task.*`/`phase.*` conventions are declared in
`otel_conventions.py` prose but NOT in any module's `_OTEL_DESCRIPTORS`**, and
`task_tracking_emitter` is absent from `observability/collector.py`'s `_INSTRUMENTED_MODULES`. So
project signals are **not in the descriptor catalog** that drives the taxonomy generator.

---

## 2. Findings

| # | Finding | Evidence |
|---|---------|----------|
| PRO-D1 | **Split ownership undocumented.** SDK produces raw signals (state files, spans, Kaizen JSON); ContextCore owns the metric gauges + burndown dashboards. Nothing draws the line | §1.1/1.5 |
| PRO-D2 | **Declared-not-emitted gauges.** `contextcore_task_*` are declared in onboarding metadata but not emitted by startd8 — a category-4 analogue of the `capability_index` cede | §1.5 |
| PRO-D3 | **Rich delivery signals stuck in JSON.** Improvement deltas, Kaizen root-cause/scores, batch velocity are valuable project-health signals but are JSON/YAML only — not observable via metrics/dashboards | §1.4 |
| PRO-D4 | **Span conventions absent from the descriptor manifest.** `task.*`/`phase.*` are prose-declared, not in `_OTEL_DESCRIPTORS`; the generator can't see them | §1.6 |
| PRO-D5 | **No live progress deltas.** `percent_complete` is seeded at 0 but no `task.updated` events are emitted during execution — progress is point-in-time, not live (burndown can't move from SDK signals alone) | §1.1 |
| PRO-D6 | **Burndown/velocity dashboards are external.** Realized by ContextCore + the `/context-core-tracker` / `/time-series-progress-tracker` skills, not generated by startd8 | §6 inventory |

---

## 3. Requirements

### 3.1 Draw the ownership boundary

**REQ-PRO-001 (ownership boundary, PRO-D1/D2).** The boundary MUST be documented and respected:
- **startd8 produces** the raw lifecycle signals — task **state files** (SpanState v2), phase/task
  **OTel spans**, complexity span attributes, and Kaizen/improvement/velocity **JSON artifacts**.
- **ContextCore owns** the metric-ified gauges (`contextcore_task_progress`/`status`/
  `install_completeness_percent`) and the burndown/velocity dashboards.
The observability artifact generator MUST NOT claim startd8 emits the `contextcore_*` gauges; where
declared, they are reported as **ContextCore-owned** (honest-skip, mirroring the taxonomy's
`capability_index` cede, REQ-OAT-011).

### 3.2 Close the descriptor-manifest gap

**REQ-PRO-002 (declare the spans, PRO-D4).** The `task.*` and `phase.*` span conventions
(`otel_conventions.py`) MUST be declared in `_OTEL_DESCRIPTORS` with
`category = project_observability` and `orientation = system`, and the emitting modules MUST be added
to `collector.py`'s `_INSTRUMENTED_MODULES`, so project spans are in the descriptor catalog that
feeds generation (consistent with the AI-agent doc's REQ-AAO-008 loop).

### 3.3 Surface the delivery-quality signals

**REQ-PRO-003 (make delivery quality observable, PRO-D3).** The JSON-only delivery signals MUST be
made discoverable and, where they answer an operational question, observable:
- Kaizen failure distribution: `root_cause` counts, `pipeline_stage` failure rates, dual-scoring
  PASS/PARTIAL/FAIL ratio;
- delivery velocity & trend, persistent-failure count;
- document/output quality improvement deltas.
Per signal, decide: (a) emit as an OTel metric (so it's dashboard-able), or (b) keep as a JSON
artifact but **declare it in the manifest** so the catalog is complete. At minimum the manifest MUST
list them (no silent JSON-only project-health signals).

### 3.4 Live progress (optional/phased)

**REQ-PRO-004 (progress deltas, PRO-D5).** For live burndown, startd8 SHOULD emit `task.updated`
events carrying a `percent_complete` delta as tasks advance (not only the zero-point). If deferred,
the SDK MUST document that progress is **point-in-time** (seeded), with live movement owned by the
ContextCore consumer.

### 3.5 Orientation & artifacts

**REQ-PRO-005 (orientation).** Project-obs artifacts classify on the orientation axis: burndown /
velocity / quality dashboards = **human**; task/phase spans, SLI definitions, descriptor catalog =
**system**; delivery-health alerts (persistent-failure, quality-regression, cost-outlier) =
**bridge**.

**REQ-PRO-006 (artifacts startd8 generates vs cedes).** Like Category 5, startd8 provides the
**signal catalog + SLI/alert definitions**; the **burndown/velocity dashboards** are **ceded** to
ContextCore + the tracker skills (cross-referenced, not generated here). startd8 MAY generate
**delivery-health alerts** from its own Kaizen/batch signals (persistent-failure, quality-regression,
cost-outlier) since it owns those signals.

**REQ-PRO-007 (project SLIs/SLOs — system).** Definable from owned signals: delivery success rate
(`tasks_passed / tasks_attempted`), velocity trend, quality-improvement trend, blast-radius
distribution, persistent-failure count (objective: 0).

---

## 4. Non-requirements / out of scope

- Implementing the category-4 **generator** (taxonomy REQ-OAT-041 reserves the namespace).
- Re-implementing ContextCore's gauges or burndown/velocity dashboards — those are **ceded**
  (REQ-PRO-001/006).
- Category-5 (agent) and category-1 (service) signals — separately specified.

## 5. Open questions

- **OQ-1.** Which delivery signals (REQ-PRO-003) warrant metric emission vs descriptor-declare-only?
  (Kaizen root-cause distribution and velocity are the strongest dashboard candidates.)
- **OQ-2.** Should live progress deltas (REQ-PRO-004) be startd8's job at all, or strictly
  ContextCore's once it consumes the state files? (Boundary question — ties to REQ-PRO-001.)
- **OQ-3.** Is `install_completeness_percent` project-obs (delivery) or pipeline-innate (capdevpipe
  install bookkeeping)? Its emission owner (ContextCore vs cap-dev-pipe installer) decides.

---

## Appendix A — signal → (owner, orientation, surfaced?) catalog

| Signal | Kind | Owner | Orientation (of artifacts) | Surfaced today? |
|--------|------|-------|----------------------------|-----------------|
| task state files (SpanState v2) | state file | startd8 → ContextCore | system | ✅ ~/.contextcore/state/ |
| `task.created` / `percent_complete:0` | event | startd8 | human (burndown) | ✅ state files (no live delta) |
| `phase.{name,status,cost,duration}` | span | startd8 | system | ✅ OTLP/Tempo (not in descriptors — PRO-D4) |
| `task.{complexity_tier,blast_radius}` | span attr | startd8 | system / human | ✅ OTLP (not in descriptors) |
| improvement deltas (6 categories) | YAML | startd8 | human | ❌ project-index JSON only |
| Kaizen `root_cause`/`pipeline_stage`/dual-score | JSON | startd8 | bridge (alert) / human | ❌ kaizen-metrics.json only |
| batch velocity / persistent-failure | JSON | startd8 | human / bridge | ❌ ledger only |
| `contextcore_task_progress/status` | gauge | **ContextCore** | human / bridge | ❌ external (ceded) |
| `install_completeness_percent` | gauge | ContextCore / capdevpipe | — | ❌ external (OQ-3) |

## Appendix B — requirement index

`REQ-PRO-001` ownership boundary · `REQ-PRO-002` descriptor-manifest (declare spans) ·
`REQ-PRO-003` surface delivery quality · `REQ-PRO-004` live progress (phased) · `REQ-PRO-005`
orientation · `REQ-PRO-006` generate-vs-cede · `REQ-PRO-007` project SLIs.

---

*Draft v0.1 — surfaces the SDK's development-lifecycle telemetry (task state files, phase/task spans,
complexity attrs, and JSON-only Kaizen/improvement/velocity signals) as Category-4 requirements. The
defining finding: Category 4 is split-ownership — startd8 produces raw signals; ContextCore owns the
gauges + burndown dashboards (the `contextcore_task_*` metrics are declared-but-not-SDK-emitted).
Names 6 findings and 7 requirements. Candidate for a reflective-requirements + CRP pass.*
