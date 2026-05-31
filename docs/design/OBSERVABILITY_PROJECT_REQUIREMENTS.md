# Project Observability — Requirements (Taxonomy Category 4)

**Date:** 2026-05-31
**Status:** Draft v0.2 — post-planning self-reflective update (requirements only; no code this pass)
**Lineage:** Instantiates **Category 4 — Project Observability** of
`OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (the "reserved — signals emitted, no generator"
row). Evidence base: a read-only telemetry inventory of `src/startd8/` (task_tracking_emitter,
integrations/contextcore, otel_conventions, complexity/, improvement_tracking, contractors/
prime_postmortem + batch_postmortem, observability/manifest + collector).
**Subject observed:** the **project's development lifecycle** — task progress/status, hierarchy,
phase execution, complexity/blast-radius, delivery & output quality, velocity.

---

## 0. Planning Insights (self-reflective update, v0.1 → v0.2)

> A planning pass traced the startd8↔ContextCore seam, the descriptor manifest, and the JSON
> delivery-signal emission paths. Headline: **the ownership seam is already clean in code** —
> ContextCore is an *optional* import (graceful `_enabled=False` if absent); startd8 writes state
> files, ContextCore reads them. So the category-4 work is mostly **documentation + descriptor
> declaration**, not decoupling. Two requirements were over-optimistic and are corrected.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| REQ-PRO-001: boundary needs drawing (maybe code) | Code seam is **already clean** — ContextCore optional-import + file-consumer pattern, no hard dep, no bidirectional coupling | 001 = **pure documentation** (S): mirror the boundary in code comments; the doc was ~95% right |
| REQ-PRO-002: add `task_tracking_emitter` to the OTel descriptor manifest | `task_tracking_emitter` emits **no OTel** — only JSON state files (a *separate channel* to ContextCore). The real descriptor gap is the **`phase.*`/`task.*` OTel SPANS** (artisan runners + `development.py`) that ARE emitted but not declared | 002 **refined**: declare the *spans*; the state-file emitter stays out of the OTel manifest (it has no OTel) |
| REQ-PRO-003: surface delivery signals (implied metric-ify) | Kaizen/improvement/velocity are **post-run async JSON** (postmortem runs in a thread after the run); no inline emit point — metric-ifying needs re-architecture | 003 **split**: *declare-only* (manifest schema + sample SLI queries) is S and in scope; *metric emission* is L and deferred (resolves OQ-1 → declare-only) |
| REQ-PRO-004: startd8 emits live progress deltas | `task_tracking_emitter` is a **one-time** emitter; `percent_complete` is structurally **always 0** from startd8 (zero-point seed only). Live progress is computed by ContextCore from the state files | 004 **reframed**: progress is **ContextCore-owned**; startd8 emits only the seed. Do **not** build a delta emitter (wrong-owner accidental complexity). Resolves OQ-2 → ContextCore |
| (not in v0.1) | "**task**" names two different things: the **work-item** hierarchy (epic/story/task in `task_tracking_emitter`, state files) vs **codegen `task.*` span attributes** (`development.py` chunk attrs: complexity_tier/blast_radius) — a naming collision | **NEW REQ-PRO-008**: disambiguate the two "task" concepts in `otel_conventions.py` + descriptors |
| (not in v0.1) | The descriptor-schema change (add `category`/`orientation`) is the **same** change the AI-agent doc needs — one keystone serving cats 4 **and** 5 (and the taxonomy's declare-don't-guess) | **Convergence**: the `_OTEL_DESCRIPTORS` manifest is the **shared spine**; REQ-PRO-002/005 reference the AAO schema change, not duplicate it |
| (not in v0.1) | **Three overlapping quality scorers**: ImprovementTracker (6-cat doc quality), Kaizen RootCause (16×9), `query_security_score` — no unified quality taxonomy; and `complexity/classifier.py` creates an OTel histogram it **never records to** (dead) | Catalogued in Appendix C; the dead histogram is a quick win |

**Resolved open questions:**
- **OQ-1 → declare-only.** Delivery signals are post-run JSON; declare their schema + SLI queries in
  the manifest now; defer metric emission (REQ-PRO-003).
- **OQ-2 → ContextCore owns progress.** startd8 seeds the zero-point; ContextCore computes deltas
  (REQ-PRO-004).
- **OQ-3 → externally owned.** `install_completeness_percent` is produced by ContextCore / the
  cap-dev-pipe installer, not startd8 — ceded regardless of which category it lands in.

*Essential complexity: declare the existing project spans (with category/orientation) in the one
shared descriptor manifest + draw the (already-clean) ownership boundary in docs. The rest
(metric-ifying post-run JSON, live progress deltas) is either deferred or the wrong owner.*

---

## 0.1 Motivation

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

**REQ-PRO-001 (ownership boundary — documentation; seam already clean).** Planning confirmed the
code seam is already clean (ContextCore is an optional import with graceful degradation; startd8
writes state files that ContextCore reads — no hard dependency, no bidirectional coupling). So this
is a **documentation** requirement, not a decoupling one: the boundary MUST be stated in the docs
and mirrored in code comments (on `task_tracking_emitter.emit_task_tracking_artifacts()` and
`contextcore.py`'s `TaskTrackerWrapper`):
- **startd8 produces** the raw lifecycle signals — task **state files** (SpanState v2), phase/task
  **OTel spans**, complexity span attributes, and Kaizen/improvement/velocity **JSON artifacts**.
- **ContextCore owns** the metric-ified gauges (`contextcore_task_progress`/`status`/
  `install_completeness_percent`), the **live progress computation** (the deltas off the seeded
  zero-point — REQ-PRO-004), and the burndown/velocity dashboards.
The observability artifact generator MUST NOT claim startd8 emits the `contextcore_*` gauges; where
declared, they are reported as **ContextCore-owned** (honest-skip, mirroring the taxonomy's
`capability_index` cede, REQ-OAT-011).

### 3.2 Close the descriptor-manifest gap

**REQ-PRO-002 (declare the project SPANS, PRO-D4 — refined).** The `phase.*` and codegen `task.*`
span attributes that are **already emitted** (by `artisan_phases/runner.py`, `artisan_contractor.py`,
`development.py`) MUST be declared in `_OTEL_DESCRIPTORS` with `category = project_observability`
and `orientation = system`, and those emitting modules added to `collector.py`'s
`_INSTRUMENTED_MODULES`, so the project spans enter the descriptor catalog that feeds generation
(same loop as AI-agent REQ-AAO-008). **Scope correction (planning):** this covers the OTel **spans**
only — `task_tracking_emitter` emits **no OTel** (it writes JSON state files on a *separate* channel
to ContextCore) and MUST **not** be added to the OTel manifest. The `category`/`orientation` schema
fields are the **same** addition the AI-agent doc specifies (REQ-AAO-004) — this requirement
**reuses** that single shared schema change (the descriptor manifest is the shared spine for
categories 4 & 5), it does not duplicate it.

### 3.3 Surface the delivery-quality signals

**REQ-PRO-003 (make delivery quality discoverable — declare-only now; metric-ify deferred).**
Planning found these signals (Kaizen `root_cause`/`pipeline_stage`/dual-score, velocity/trend,
persistent-failure, quality-improvement deltas) are **post-run async JSON** (postmortem runs in a
thread after the run) with no inline emit point. So the requirement splits:
- **REQ-PRO-003a (declare-only — in scope, S):** these signals MUST be **declared in the manifest**
  (their JSON schema + sample SLI/PromQL query forms) as a hand-authored section, so the catalog has
  no silent JSON-only project-health signals and the generator can reference them.
- **REQ-PRO-003b (metric emission — deferred, L):** emitting them as live OTel metrics is deferred —
  it requires re-architecting Kaizen from post-run analysis into in-process instrumentation, which is
  out of scope for this pass.

(Resolves OQ-1: declare-only.) Note: the collector auto-discovers descriptors but **SLO/alert/JSON-schema
sections are hand-maintained** — so REQ-PRO-003a and REQ-PRO-007 are authored sections, not
auto-generated.

### 3.4 Live progress (optional/phased)

**REQ-PRO-004 (progress ownership — reframed: ContextCore, not startd8).** Planning showed
`task_tracking_emitter` is a **one-time** emitter and `percent_complete` is structurally **always 0**
from startd8 (a zero-point seed). Building a `task.updated` delta emitter in startd8 would put
progress computation in the **wrong owner** and add accidental complexity. The requirement is
therefore to **document that live progress is ContextCore-owned** — startd8 provides the seeded
zero-point; ContextCore computes the deltas from the state files + run telemetry. startd8 MUST NOT
build a progress-delta emitter. (Resolves OQ-2.)

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
distribution, persistent-failure count (objective: 0). These are **hand-authored** manifest sections
(the collector auto-discovers descriptors, not SLI/SLO templates — see REQ-PRO-003).

**REQ-PRO-008 (disambiguate the two "task" concepts — from planning).** The token "task" denotes two
distinct things and the requirements/code MUST disambiguate them, or routing and dashboards conflate
them:
- **work-item task** — the epic/story/**task** hierarchy in `task_tracking_emitter` (state files,
  ContextCore-bound; the burndown unit);
- **codegen task** — the `task.*` span attributes in `development.py`/`otel_conventions.py`
  (per-chunk codegen: `complexity_tier`, `blast_radius`, `attempts`, `cost`).
The descriptor declarations (REQ-PRO-002) and `otel_conventions.py` MUST name these distinctly (e.g.
`workitem.*` vs `codegen.task.*`) so the manifest, SLIs, and any generated artifacts don't merge a
plan's work-items with code-generation chunk telemetry.

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

*(v0.1 footer superseded by the v0.2 summary below.)*

## Appendix C — pre-existing accidental complexity to eliminate (opportunistic)

Catalogued by the planning pass; the code-alignment follow-up SHOULD remove these. Effort S/M/L.

| # | Smell | Location | Why accidental | Distillation | Effort |
|---|-------|----------|----------------|--------------|--------|
| C-1 | **"task" naming collision** | `otel_conventions.py`, `task_tracking_emitter.py`, `development.py` | work-item task vs codegen-chunk `task.*` attrs share the name | disambiguate (`workitem.*` vs `codegen.task.*`) (REQ-PRO-008) | S |
| C-2 | **Dead OTel histogram** | `complexity/classifier.py:23–35` | creates a tier histogram but **never records** to it | remove, or actually `record()` tier classifications | S |
| C-3 | **Constants declared but call-sites use raw strings** | `otel_conventions.py` (AttributeKeys) vs `development.py:5327`, `runner.py:525` | span-attr names defined as constants but set via literal strings → drift | use the constants everywhere; a parity check ties declared↔emitted | M |
| C-4 | **Span-name pattern mismatch** | `artisan_contractor.py` (`artisan.workflow.{id}.phase.{phase}`) vs `runner.py` (`phase.{type}.attempt.{n}`) | two patterns for phase spans; unclear if same hierarchy | reconcile/​document the phase-span hierarchy | S |
| C-5 | **Three overlapping quality scorers** | `improvement_tracking.py` (6-cat doc quality) · Kaizen `prime_postmortem.py` (16 root-cause × 9 stage) · `query_prime/kaizen_metrics.py` (`query_security_score`) | three independent quality taxonomies, no unifying model | document the three lenses; a unified quality signal hierarchy is a *separate, larger* effort (flag, don't fold in) | L (deferred) |
| C-6 | **SpanState v2 schema duplicated** across producer + external consumer | `task_tracking_emitter._build_state_file()` hardcodes the schema ContextCore also depends on | the contract lives in two repos with no shared definition | document the schema-version contract explicitly (a shared dataclass is hard across the repo boundary) | M |
| C-7 | **Descriptor schema lacks category/orientation** | `observability/manifest.py` | the routing fields cats 4 & 5 need aren't in the schema | add two fields — **shared** with AI-agent REQ-AAO-004 (one change, two categories) | S |

**Net:** C-1/C-2/C-7 are S quick wins (C-7 is shared with the AI-agent doc — one change). C-3/C-4/C-6
are M documentation/parity tidy-ups. C-5 (three quality scorers) is real but **larger scope** — flagged
for a separate consolidation, not folded into this pass to avoid scope creep.

---

*v0.2 — Post-planning self-reflective update. Confirmed the ownership seam is already clean (001 →
documentation), refined 002 (spans not state-files; reuses the shared descriptor-schema change),
split 003 (declare-only in scope / metric-ify deferred — Kaizen is post-run async), reframed 004
(progress is ContextCore-owned; don't build a delta emitter), added 008 (disambiguate the two "task"
concepts), resolved 3 open questions, and catalogued 7 accidental-complexity items (Appendix C). Net
finding: category-4 is mostly documentation + declaring existing spans in the one shared descriptor
manifest — the boundary is clean and the heavy lifting (metrics, progress) is deferred or
ContextCore's.*
