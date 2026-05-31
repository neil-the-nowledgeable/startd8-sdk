# Project Observability — Requirements (Taxonomy Category 4)

**Date:** 2026-05-31
**Status:** Draft v0.3 — combined cat-4/5 CRP R1 triaged (9 F-suggestions applied; references shared spine `OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md`)
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
declared, they are reported as **ContextCore-owned** honest-skip. **Field-level cede contract
(R1-F1, `REQ-OBS-SHARED-004`):** the skip record MUST carry `skip_reason=owned_elsewhere`,
`owner=contextcore`, **no** `source_checksum`, and MUST be **excluded from the `artifact_type_coverage`
denominator** (taxonomy REQ-OAT-052) — so a cede reads as ownership, not as `coverage<1.0`. **Stale
metadata (R1-F5):** when onboarding metadata *still lists* `contextcore_task_*` as declared (as
run-007 output does today), the generator MUST classify them as `owned_elsewhere` skips **on read**,
not mis-attribute them as startd8-emitted.

### 3.2 Close the descriptor-manifest gap

**REQ-PRO-002 (declare the project SPANS, PRO-D4 — refined).** The `phase.*` and codegen `task.*`
span attributes that are **already emitted** (by `artisan_phases/runner.py`, `artisan_contractor.py`,
`development.py`) MUST be declared in `_OTEL_DESCRIPTORS` with `category = project_observability`
and `orientation = system`, and those emitting modules added to `collector.py`'s
`_INSTRUMENTED_MODULES`, so the project spans enter the descriptor catalog that feeds generation
(same loop as AI-agent REQ-AAO-008). **Scope correction (planning):** this covers the OTel **spans**
only — `task_tracking_emitter` emits **no OTel** (it writes JSON state files on a *separate* channel
to ContextCore) and MUST **not** be added to the OTel manifest. The `category`/`orientation` schema
fields are owned by **`REQ-OBS-SHARED-001`** (R1-F7) — this requirement **references** that single
shared schema change by ID (the descriptor manifest is the shared spine for categories 4 & 5), it
does not duplicate or restate it. **Parity relation (R1-F3, `REQ-OBS-SHARED-002`):** project spans
use the **subset** relation (declared attrs ⊆ emitted), because span attribute sets are open — this
is the kind-aware counterpart to cat-5's metric **bijection**, enforced by the one shared parity
helper. **Layering (R1-F9, `REQ-OBS-SHARED-003`):** the descriptor manifest is a separate
telemetry-declaration layer from the taxonomy artifact-dispatch registry (REQ-OAT-070a); they share
the enum vocabulary but not rows, so hand-setting `category`/`orientation` here is not the
parallel-table the taxonomy forbids.

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
auto-generated. **Sync mechanism (R1-F4):** because these hand-authored sections are NOT
auto-discovered and the parity test cannot drift-check them, REQ-PRO-003a/007 MUST be validated in CI
against a checked-in **real `kaizen-metrics.json` / velocity-ledger sample** — so a shape change in
the Kaizen JSON producers fails the build rather than silently rotting the authored schema.

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
ContextCore + the tracker skills (cross-referenced, not generated here). startd8 MAY define
**delivery-health alerts** from its own Kaizen/batch signals (persistent-failure, quality-regression,
cost-outlier) since it owns those signals. **Scope (R1-F6): definitions only this pass** — because
REQ-PRO-003b (live metric emission) is deferred, these alerts have no queryable series yet; they are
authored alert *specs*, not deployable rules. Deployable delivery-health alerts depend on
REQ-PRO-003b.

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
**Committed scheme (R1-F2 — one decision, not an either/or):** the **work-item** hierarchy KEEPS
`task.*` (it is the ContextCore/SpanState-v2 canonical — `task.status`, `task.percent_complete` — an
external standard we do not rename); the **codegen chunk** attributes are renamed to **`codegen.task.*`**
(`codegen.task.complexity_tier`, `codegen.task.blast_radius`, `codegen.task.attempts`,
`codegen.task.cost`). This resolves the real collision verified in code — `task.status` is currently
defined in *both* worlds (`otel_conventions.py:66` codegen vs ContextCore work-item; see
`OBSERVABILITY_CAT45_CODE_VERIFICATION.md` §B-3). Descriptor declarations (REQ-PRO-002),
`otel_conventions.py`, and SLI examples MUST all use this single naming, and Phase 0.1 must land it
**before** Phase 2.1 declares descriptors.

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

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Cede field-level contract (`skip_reason`/`owner` + denominator-exclusion) | claude-opus-4-8-1m | Added to REQ-PRO-001; bound to `REQ-OBS-SHARED-004` / REQ-OAT-052 | 2026-05-31 |
| R1-F2 | PRO-008 commit to ONE task-disambiguation scheme | claude-opus-4-8-1m | Committed: work-item keeps `task.*` (ContextCore canonical), codegen → `codegen.task.*`; verified collision in §B-3 | 2026-05-31 |
| R1-F3 | Span parity relation = subset, kind-aware | claude-opus-4-8-1m | REQ-PRO-002 references `REQ-OBS-SHARED-002` (spans subset, metrics bijection) | 2026-05-31 |
| R1-F4 | Sync hand-authored SLI/JSON-schema vs real Kaizen sample | claude-opus-4-8-1m | REQ-PRO-003a/007: CI-validate against checked-in `kaizen-metrics.json` sample | 2026-05-31 |
| R1-F5 | Handle stale run-007 `contextcore_task_*` metadata | claude-opus-4-8-1m | REQ-PRO-001: classify as `owned_elsewhere` on read; `REQ-OBS-SHARED-004` | 2026-05-31 |
| R1-F6 | PRO-006 alerts definition-only this pass | claude-opus-4-8-1m | Marked specs-only; deployable alerts depend on REQ-PRO-003b (deferred) | 2026-05-31 |
| R1-F7 | One shared requirement (REQ-OBS-SHARED-001) | claude-opus-4-8-1m | REQ-PRO-002/005 reference `OBSERVABILITY_DESCRIPTOR_SPINE_REQUIREMENTS.md` by ID | 2026-05-31 |
| R1-F8 | Emit-vs-cede boundary for single generator | claude-opus-4-8-1m | `REQ-OBS-SHARED-004` (cat-4 cede / cat-5 emit) | 2026-05-31 |
| R1-F9 | Registry layering (projection vs separate layer) | claude-opus-4-8-1m | `REQ-OBS-SHARED-003`: separate layers, shared enum vocabulary | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:46:04 UTC
- **Scope**: Requirements quality (F-prefix) for Project Observability (cat 4), weighted toward the 5 cross-doc focus asks on the shared `_OTEL_DESCRIPTORS` spine vs the AI-agent doc (cat 5) and the settled taxonomy registry/cede model (REQ-OAT-070a / REQ-OAT-011/052).

##### Focus-ask answers (sponsor cross-doc concerns 1–5)

**Ask 1 — Spine consistency (PRO-002/005 vs AAO-004/008/012: same schema change + parity test, or drift?).**
- **Summary answer:** Partial — PRO-002 correctly says it *reuses* the AAO schema change ("does not duplicate it"), but the parity test is restated here as a *subset* relation while the AAO doc states a *bijection*, so the "shared" test has already drifted in spec.
- **Rationale:** REQ-PRO-002 explicitly defers the schema-field contract to REQ-AAO-004 ("reuses that single shared schema change"), which is the right move and better than the AAO side's symmetric restatement. But PRO plan Phase 2.3 says "declared attrs ⊆ emitted attrs" (subset) whereas AAO-012 reads as bijection — the one shared parity mechanism is specified with two different relations.
- **Assumptions / conditions:** Holds unless one normative owner is designated for both the schema fields (AAO-004) and the parity relation.
- **Suggested improvements:** Promote both the schema-field contract and the parity relation to a single shared requirement that PRO-002 and AAO-004/012 reference (cross-doc R1-F7); pick subset-or-bijection once (cross-doc R1-F8).

**Ask 2 — Emit-vs-cede asymmetry coherent and implementable? Does the cat-4 cede mirror the taxonomy capability_index cede (REQ-OAT-011)?**
- **Summary answer:** Yes — the cat-4 cede is coherent and REQ-PRO-001 already names the taxonomy `capability_index` honest-skip (REQ-OAT-011) as its model; it is the more precise of the two ownership shapes.
- **Rationale:** REQ-PRO-001 states startd8 produces raw signals while ContextCore owns the `contextcore_*` gauges and "where declared, they are reported as ContextCore-owned (honest-skip, mirroring REQ-OAT-011)." That is exactly the taxonomy cede vocabulary. The one missing precision: REQ-PRO-001 names REQ-OAT-011 but not the `skip_reason=owned_elsewhere`/`owner` *fields* that REQ-OAT-052 (settled, R2-F3/R4-F2) requires the skip record to carry, nor that owned_elsewhere skips are excluded from the coverage denominator.
- **Assumptions / conditions:** Holds; the gap is field-level precision, not a conceptual flaw.
- **Suggested improvements:** Have REQ-PRO-001 require the cede be recorded with `skip_reason=owned_elsewhere` + `owner=contextcore` and excluded from artifact_type_coverage (R1-F1), citing REQ-OAT-052.

**Ask 3 — Do these descriptors fit the taxonomy single type-keyed registry (REQ-OAT-070a)? Does the "task" collision (REQ-PRO-008) interact with cat-5's naming (REQ-AAO-003)?**
- **Summary answer:** Depends — declaring project *spans* in `_OTEL_DESCRIPTORS` with hand-set `category`/`orientation` has the same projection-vs-authoritative question as cat 5; the "task" collision is a real, separate naming hazard that does NOT interact with cat-5's dotted/underscore split.
- **Rationale:** REQ-PRO-002 adds `category=project_observability`/`orientation=system` per descriptor — same parallel-axis concern as REQ-OAT-070a (category/orientation are derived projections, never independently authored). Separately, REQ-PRO-008's work-item-`task` vs codegen-`task.*` disambiguation is a within-cat-4 namespace fix (`workitem.*` vs `codegen.task.*`); cat-5's REQ-AAO-003 dotted-vs-underscore is a metric-name-style fix. They are orthogonal — no shared token, no interaction — so they can land independently.
- **Assumptions / conditions:** Holds if the descriptor manifest's axes are reconciled with the REQ-OAT-070a registry (same condition as cat 5).
- **Suggested improvements:** State whether project-span descriptor axes are projections of REQ-OAT-070a or a separate layer (cross-doc R1-F9); confirm REQ-PRO-008 and REQ-AAO-003 are independent (no doc change needed beyond a note).

**Ask 4 — Shared keystone + parity test concretely sequenced, or two PRs each add it?**
- **Summary answer:** Partial — PRO plan Phase 1.1 explicitly says "= AI-agent REQ-AAO-004; ONE change" and the checklist says "landed once", which is good, but it still lists the field addition as its own step rather than a dependency on the cat-5 landing.
- **Rationale:** PRO plan Phase 1.1 and before-code checklist both assert the schema change is shared/landed-once and the parity test (2.3) is shared with AAO-012 — stronger than the cat-5 plan's wording. But Phase 1.1 is still written as a step this plan performs, not as "depends on cat-5 Phase 1 having landed it." Same branch mitigates, doesn't eliminate.
- **Assumptions / conditions:** Holds unless ordering is recorded (cat-5 lands schema+parity; cat-4 rebases and only adds project spans).
- **Suggested improvements:** Reframe PRO plan Phase 1.1 as a dependency edge on the cat-5 keystone (plan-side S suggestion in the PRO plan file).

**Ask 5 — Deferred-vs-in-scope boundary clean (in-scope small, deferred clearly elsewhere)?**
- **Summary answer:** Yes — the boundary is the cleanest of the set: REQ-PRO-003 splits declare-only (003a, S, in) from metric-ify (003b, L, deferred); REQ-PRO-004 cedes live progress to ContextCore; §4 excludes the generator and ContextCore dashboards.
- **Rationale:** REQ-PRO-003a/b is an explicit S/L split with the deferred half named; REQ-PRO-004 explicitly says "startd8 MUST NOT build a progress-delta emitter"; C-5 (three quality scorers) is flagged "separate, larger effort, not folded in." The deferred work is clearly ContextCore's or a later pass. The one soft edge: REQ-PRO-003a says delivery signals are a "hand-authored section" while the collector auto-discovers descriptors — the requirement should state how the hand-authored section is kept in sync (it cannot drift-check like descriptors do).
- **Assumptions / conditions:** None material.
- **Suggested improvements:** Add a sync/ownership note for the hand-authored SLI/JSON-schema section (R1-F4).

##### Numbered suggestions (F-prefix → requirements)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | REQ-PRO-001 MUST require the `contextcore_*` cede be recorded with the taxonomy skip fields: `skip_reason=owned_elsewhere`, `owner=contextcore` (REQ-OAT-052), and that such skips are **excluded from the artifact_type_coverage denominator** (REQ-OAT-011/052, R4-F2) — not merely "reported as ContextCore-owned". | REQ-PRO-001 names REQ-OAT-011 conceptually but omits the field-level contract (`skip_reason`/`owner`) and the denominator-exclusion that the settled taxonomy requires; without it the cede is a looks-like-failure (coverage <1.0) for operators (focus Ask 2). | REQ-PRO-001 (§3.1) | Test: a project declaring onboarding/ContextCore-owned `contextcore_task_progress` yields a skip with `skip_reason=owned_elsewhere`, `owner=contextcore`, and artifact_type_coverage=1.0. |
| R1-F2 | Data | medium | REQ-PRO-008 MUST commit to ONE disambiguation scheme rather than offering an either/or ("rename codegen `task.*` to `codegen.task.*` **or** keep `task.*` for work-items and namespace the chunk attrs"). An implementer cannot build/test against an alternative. | REQ-PRO-008 and plan Phase 0.1 both present two options; the requirement is supposed to be the decision. Leaving the choice open means the descriptor names (REQ-PRO-002) and SLIs depend on an undecided namespace (focus Ask 3). | REQ-PRO-008 (§3.5) | Doc review: exactly one target naming (`workitem.*` vs `codegen.task.*`) is normative; descriptors and SLI examples use it consistently. |
| R1-F3 | Validation | medium | REQ-PRO-002 MUST state the parity relation for project SPANS (declared ⊆ emitted, because span attribute sets are open) and note this MAY differ from the cat-5 metric parity relation — so the shared parity test is parameterized by signal kind rather than assumed identical. | The PRO plan Phase 2.3 already implies subset for spans, but the requirement doesn't say so; meanwhile AAO-012 implies bijection for metrics. Spans legitimately need subset (you don't declare every ad-hoc attr); metrics may need bijection. The requirement should make the relation explicit and kind-aware (focus Ask 1/4). | REQ-PRO-002 (§3.2) | Test: the parity helper enforces ⊆ for span descriptors and the (chosen) relation for metric descriptors; both documented in both docs. |
| R1-F4 | Ops | medium | REQ-PRO-003a / REQ-PRO-007 MUST state how the **hand-authored** SLI/JSON-schema manifest section stays in sync with the underlying JSON producers (Kaizen/velocity), since unlike descriptors it is NOT auto-discovered and cannot be drift-checked by the parity test. | The doc twice notes these are hand-authored ("the collector auto-discovers descriptors but SLO/alert/JSON-schema sections are hand-maintained") but gives no sync mechanism; a hand-authored schema silently rots when the Kaizen JSON shape changes (focus Ask 5). | REQ-PRO-003a / REQ-PRO-007 (§3.3/§3.5) | Test or CI check: the authored Kaizen/velocity JSON-schema section is validated against a real `kaizen-metrics.json` sample so shape drift fails. |
| R1-F5 | Risks | medium | REQ-PRO-001/004 SHOULD specify what the generator does when the run-007 onboarding metadata *still lists* `contextcore_task_*` as declared (as it does today): the requirement says "MUST NOT claim startd8 emits" them, but does not say the metadata source must be corrected or treated as owned_elsewhere on read. | The defining finding (§0.1) is that these gauges are declared-but-not-emitted; the requirement forbids the false claim but leaves the existing metadata declaration unaddressed — a generator reading it naively still mis-attributes (focus Ask 2). | REQ-PRO-001 (§3.1) | Test: feeding the current run-007 metadata, the generator classifies `contextcore_*` as owned_elsewhere skips, not startd8-emitted artifacts. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Architecture | low | REQ-PRO-006 SHOULD bound the "startd8 MAY generate delivery-health alerts" clause: since REQ-PRO-003b defers metric emission, alerts on Kaizen/velocity signals would have no live metric to alert on — state that these alerts are *definitions only* this pass (consistent with REQ-PRO-003a declare-only), not deployable, to avoid implying an emit path that's deferred. | REQ-PRO-006 says startd8 "MAY generate delivery-health alerts … since it owns those signals," but the signals are post-run JSON with no metric (003b deferred) — an alert needs a queryable series; the MAY clause implies more than the in-scope declare-only work delivers. | REQ-PRO-006 (§3.5) | Doc review: REQ-PRO-006 alert clause is marked definition-only this pass; deployable alerts depend on REQ-PRO-003b (deferred). |

##### Cross-doc consistency (cats 4 & 5)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Architecture | high | Create ONE shared requirement (proposed `REQ-OBS-SHARED-001`) owning the descriptor schema change (`category`/`orientation` fields + enums + defaults) AND the descriptor↔emission parity mechanism; have REQ-PRO-002/005 and AAO-004/008/012 reference it by ID. REQ-PRO-002 already defers correctly ("reuses … does not duplicate") — formalize that into a real shared ID. | The shared spine is described narratively in both docs but owned normatively in neither; one ID removes the drift risk and makes the "land once" intent enforceable (Ask 1/4). The parity relation already diverges (subset here vs bijection in AAO-012) — proof the duplication is drifting. | New shared requirement referenced from §3.2 here and §3.2/§3.4/§3.6 in AAO | Both docs cite the same ID; one schema/parity module referenced by both plans; no field/enum/relation defined twice. |
| R1-F8 | Interfaces | medium | Resolve the emit-vs-cede asymmetry at the cross-doc level so ONE generator handles both manifests: state that cat-4 `contextcore_*` gauges are emitted by neither manifest and surface as `skip_reason=owned_elsewhere`/`owner=contextcore` (REQ-OAT-011/052), while cat-5 metrics are produced in-process (no skip). This is the precise boundary the cat-5 doc (AAO R1-F8) should also state. | Ask 2 asks whether the asymmetry is precise enough to implement. The cat-4 cede is well-modeled here; making the *contrast* explicit in both docs lets a single generator route cat-5 as produced and cat-4 gauges as owned_elsewhere from the manifests alone. | REQ-PRO-001 / §0.1 (vs Category 5) note | Test: a generator fed both manifests routes cat-5 metrics as produced, cat-4 gauges as owned_elsewhere skips. |
| R1-F9 | Data | high | Declare in BOTH docs whether the `_OTEL_DESCRIPTORS` metric/span-side `category`/`orientation` are projections of the taxonomy REQ-OAT-070a `declared_type`-keyed registry (which forbids independently-maintained axes) or a deliberately separate telemetry-declaration layer; if separate, add a reconciliation assertion that the two never disagree for an overlapping signal. | REQ-OAT-070a (settled) makes category/orientation derived projections; both cat-4/5 docs hand-populate them on descriptors (REQ-PRO-002 / REQ-AAO-004). Either they project from the registry (say from-where) or a second registry exists (bound it) — leaving it implicit reintroduces the parallel-table accidental complexity taxonomy R2-F4 removed (Ask 3). | New shared clause referenced from REQ-PRO-002 and REQ-AAO-008 | Cross-doc test: for any signal in both the descriptor manifest and the taxonomy registry, `(category,orientation)` agree; doc states which side is authoritative. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Round R1 (first encounter); no prior untriaged suggestions exist.
