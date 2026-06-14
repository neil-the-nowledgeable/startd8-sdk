# Benchmark Project Tracking via ContextCore Business + AI Agent Observability — Requirements

**Version:** 0.4 (Post-CRP R2 dual-doc — FR-8 correction + 8 R2-F suggestions applied)
**Date:** 2026-06-13
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Relates to:** `SUMMER_2026_BENCHMARK_REQUIREMENTS_v0.2.md` (v0.5), `IMPLEMENTATION_PLAN_v0.1.md` (v0.4)

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> A planning pass read the actual SDK + ContextCore code; it confirmed the machinery largely
> exists but corrected **7 requirements** and surfaced **one latent bug**.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-3: `task_tracking_emitter` can seed initial status (some milestones `done`, some `in_progress`) | Emitter **hardcodes `status="todo"`** for epic/story/task at the zero point (`task_tracking_emitter.py:192,232,283`); NDJSON hardcodes `"not_started"` | FR-3 needs a small emitter change (add `initial_statuses` param) **or** post-emission JSON patch before install. ~2–4 hrs. No longer "free." |
| FR-1/2: hand-authored hierarchy may require plan-ingestion | **Confirmed feasible without ingestion** — construct `ParsedPlan` + `ComplexityScore` + task dicts directly (`scripts/emit_task_tracking.py` precedent); 3-level epic→story→task with `parent_span_id` works | FR-1/2 unchanged; risk retired. |
| FR-13/14: capture risk/blocker/progress/discovery insights via existing `AgentInsightBridge` | Bridge exposes only **3 of 9** types: `emit_decision`/`emit_lesson`/`emit_question`. ContextCore's `InsightEmitter` has all 9 via a generic `emit(InsightType.X, …)` | FR-13/14 require either extending the bridge or calling the generic `emit()`. Added FR-27. |
| (latent) FR-12/13 "use the bridge as-is" | **BUG:** `AgentInsightBridge.emit_question()` calls `self._emitter.emit_question()`, which **does not exist** in ContextCore's `InsightEmitter` → runtime `AttributeError` (`contextcore.py:~1393`) | New FR-28: harden the bridge (fix `emit_question`, route through generic `emit()`) before relying on it. |
| FR-15/16: `emit_decision()` carries `evidence[]`, `audience`, `supersedes`, `confidence` | SDK bridge `emit_decision()` exposes only `confidence`/`rationale`/`alternatives_considered`/`task_id` — **no `evidence`/`audience`/`supersedes`**. All three exist on ContextCore's generic `emit()` | FR-15/16 met by extending the bridge to forward to `emit()` (folded into FR-27). |
| FR-17: cost→task linkage needs a `CostRecord` schema change | **No schema change** — thread `task_id`/`cell_id`/`milestone_id` via existing `tags`/`metadata`/`tracking_context()`. But `CostMetrics.record()` emits only `model`/`provider`/`project` OTel labels (no `task_id` label) | FR-17 narrowed: storage is free; emitting `task_id` as an OTel label is a small opt-in change. |
| FR-18: GenAI dual-emit keyed on `CONTEXTCORE_EMIT_MODE`, automatic on cost spans | Env var is **`STARTD8_EMIT_MODE`** (`genai_compat.py`), not `CONTEXTCORE_EMIT_MODE`. Cost path emits `startd8.cost.*` only; `gen_ai.usage.*` lives on ContextCore `InsightEmitter.emit(input_tokens=…, output_tokens=…)` — **not automatic** | FR-18 corrected: token/cost reaches the agent view only by passing tokens into insight emission; wiring is explicit. |
| FR-19: a redaction layer must be built for telemetry | `redact()` already exists (`fde/redaction.py`, 7 secret/path patterns) but is applied **only to prose input**, not span attrs/insight evidence | FR-19 narrowed: reuse `redact()`; the work is wiring it into emission, not writing patterns. |
| FR-26: a benchmark-specific `project_id` exists | `.contextcore.yaml` declares `project_id="startd8-sdk"`, `name="StartD8 SDK"`, **no `sprint_id`** (defaults `"sprint-1"`) | FR-26 now a decision: dedicated `project_id` for the benchmark vs. nesting under `startd8-sdk`. Recommendation below. |

**Resolved open questions:**
- **OQ-1 → Build Section A (delivery) first, Section B (execution) second.** A is ~feasible today (one emitter change); B depends on the FR-38 state machine and raises volume/granularity questions. Sequencing confirmed by planning.
- **OQ-3 → Coarser grain: tasks = milestone work-items, not 1:1 FR→task.** Many FRs are cross-cutting (FR-44/45 span milestones); forcing 1:1 produces misleading burndown. Map FRs to tasks only where a milestone work-item is genuinely atomic.
- **OQ-5 → No `CostRecord` schema change.** Thread identity via `tags`/`metadata`; add an optional `task_id` OTel label only if cost-per-task dashboards need it.
- **OQ-8 → `project_id` source resolved** (`startd8-sdk`, no sprint). Superseded by the FR-26 decision: **recommend a dedicated `project_id` (e.g. `startd8-benchmark`) with `sprint_id` per round (e.g. `summer-2026`)**, so the benchmark's burndown/series (FR-25) is isolated from general SDK work and recurs cleanly.

*Still open after planning: OQ-2 (cell granularity), OQ-4 (backfill), OQ-6 (insight trigger), OQ-7 (live vs post-hoc) — these are policy/tuning choices, not feasibility blockers. FR-26 project-id decision pending user confirmation.*

---

## 1. Problem Statement

The Inaugural Summer 2026 StartD8-SDK Model Benchmark is an 8-milestone (M0–M7 + R3
addendum), ~51-FR effort that (a) **builds** a benchmark harness and (b) **runs** ~3 vendors ×
3 tiers × 9 Online Boutique services × N≥5 reps (~450+ cells) scoring models on quality / cost /
speed. Today the project tracks its own progress **only in markdown plan documents**, and its
observability requirements (FR-20/21/30) describe the **results** pipeline — a dedicated Loki
stream of per-cell quality/cost/latency feeding a Grafana leaderboard. There is no
project-management-grade visibility into the *delivery tasks* themselves, nor into the *agent
reasoning* that produces both the harness and the benchmark outputs.

ContextCore provides two complementary observability paradigms the SDK already integrates with:

- **Business Observability** — tasks modeled as OpenTelemetry spans (epic→story→task→subtask,
  SpanState v2), with derived metrics (burndown, velocity, WIP, lead/cycle time) and
  portfolio/project-progress/sprint dashboards. Answers *"Is the project on track? What's
  blocked? Who owns what?"*
- **AI Agent Observability** — agent insights modeled as spans (`insight.type` ∈
  analysis/recommendation/decision/blocker/discovery/risk/progress/lesson), with agent identity,
  confidence, evidence references, and GenAI dual-emit of token/cost. Answers *"What decisions
  did the agent make, on what evidence, and where is it stuck?"*

We want to apply **both** paradigms to track the benchmark project.

### Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| **Project delivery tasks (M0–M7 + FRs)** | Tracked in markdown plan/reqs docs only | Not modeled as ContextCore task spans; no burndown, velocity, blocker, or WIP visibility; no single source of truth for "what's done" |
| **Benchmark execution cells (~450)** | FR-38 idempotent per-cell state machine (planned); FR-20 Loki *results* stream | Cell lifecycle (`planned→leased→running→…→published`) not surfaced as business-observable tasks; no live progress gauge or completion ETA for a run |
| **Agent reasoning (build & run)** | `AgentInsightBridge` exists in SDK but unused by the benchmark | No decision/risk/lesson/blocker insights captured; the architectural-review (CRP R1–R3) decisions and per-cell failures aren't queryable as insights |
| **Per-task / per-cell cost** | `startd8.cost.*` OTel metrics, global + `by_project` breakdown | No `task_id`/`cell_id` linkage; cannot attribute spend to a milestone or a benchmark cell; no estimated-vs-actual variance |
| **GenAI token/cost on agent spans** | `SessionTracker` + `CostMetrics` emit at session/global scope | Not joined to insight spans via GenAI dual-emit conventions; agent-insights dashboard can't show cost-per-decision |

### What "tasks" means here (scope axis)

The benchmark project has **two distinct task populations**, and both could be tracked:

1. **Delivery tasks** — the M0–M7 milestones and their constituent FRs/work-items that *build*
   the harness (a finite, ~weeks-long project-management problem).
2. **Execution tasks** — the per-cell benchmark units produced each time the harness *runs*
   (a repeatable, ~hundreds-of-cells operational problem).

This document specifies tracking for both, separated into Section A (delivery) and Section B
(execution), so they can be adopted independently. See OQ-1.

---

## 2. Requirements

### Section A — Business Observability: Delivery-Task Tracking (M0–M7)

- **FR-1.** Model the benchmark project's delivery work as a ContextCore task hierarchy:
  one **epic** (the benchmark project), **stories** per milestone (M0–M7 + R3 addendum), and
  **tasks** per milestone work-item (mapped from FR-N where a 1:1 mapping is meaningful).
- **FR-2.** Emit the hierarchy as SpanState v2 task spans under
  `~/.contextcore/state/<project>/` using the existing `task_tracking_emitter`, with the
  canonical `task.status` enum (`backlog|todo|in_progress|in_review|blocked|done|cancelled`),
  `task.type` enum (`epic|story|task`), required top-level `status` field, `task.percent_complete`,
  and the zero-point `task.created` event for burndown.
- **FR-3.** Seed initial status from the current plan reality: milestones already merged to main
  (e.g. M0–M4 compile-gate work) marked `done`; in-flight marked `in_progress`; remainder
  `todo`/`backlog`. Provide a single source-of-truth mapping file (milestone → FRs → status).
  *(v0.2: `task_tracking_emitter` hardcodes `status="todo"` at the zero point. Satisfying this
  requires either adding an `initial_statuses: Dict[task_id,str]` parameter to the emitter and
  `_build_state_file()`, or a post-emission patch of the state JSON before install. Prefer the
  emitter parameter — it keeps the SpanState files internally consistent and is reusable beyond
  this project. Interacts with OQ-4 backfill.)*
  *(v0.3 / R1-F7: **honest-burndown criterion.** Backfilled terminal `done` events MUST carry the
  real merge-commit timestamp (from `git log`), NOT run-time-`now`; and each entity's zero-point
  `task.created` event MUST predate its earliest backfilled completion. Acceptance: backfilled
  M0–M4 completion timestamps equal their merge dates, and created < min(completion) per entity —
  otherwise the burndown collapses to a flat instant and is unfalsifiable.)*
- **FR-4.** Support **status transitions** as the project progresses (todo→in_progress→
  in_review→done, plus blocked/unblocked), each recorded as a span event with timestamp, so
  burndown and cycle-time metrics are derivable.
- **FR-5.** Capture **dependencies** between milestones/tasks (`task.blocked_by`) so the critical
  path (e.g. M2.5 budget guardrails gating M3 matrix) is visible.
- **FR-6.** Surface the **derived Business metrics** ContextCore computes from these spans
  (burndown, velocity, WIP, lead/cycle time, count-by-status) on a project-progress dashboard
  for this project's `project_id`.

### Section B — Business Observability: Execution-Cell Tracking (per run)

- **FR-7.** When the harness executes a benchmark **run**, model the run as a ContextCore
  hierarchy: run = epic; service (or service×model band) = story; each
  (service × model × language × rep) **cell** = task.
  *(v0.3 / R1-F3: every execution-cell task span MUST carry `run_id` and a parseable
  cell-identity attribute capturing the full `service × model × language × rep` tuple. These are
  REQUIRED emitted attributes, not optional — they are the load-bearing join key for FR-11
  (Business↔results) and FR-26 (Business↔Agent). Acceptance: a TraceQL/LogQL join on `run_id`
  returns both the task span and its matching Loki results record.)*
  *(v0.4 / R2-F5 — **provisional pending OQ-2**: the "cell = task" hierarchy below holds for the
  flagship/full-app run; for the large matrix, OQ-2 (now RESOLVED) rolls cells up to service-level
  stories carrying cell **counts**, with per-cell tasks only for flagships. Where counts-only
  applies, `run_id` + the cell-identity tuple are carried on the rollup story's per-cell count
  records, preserving the join key.)*
- **FR-8.** Map the FR-38 per-cell state machine
  (`planned|leased|running|succeeded|failed_retryable|failed_terminal|scored|published`) onto
  the canonical `task.status` enum, preserving the native cell state as a `task.labels` /
  attribute so no information is lost. *(v0.3 / R1-F4: the mapping is **deterministic** — one
  native state → exactly one `task.status` — per this canonical table:)*

  | FR-38 cell state | `task.status` | Notes |
  |------------------|---------------|-------|
  | `planned` | `todo` | enqueued, not yet leased |
  | `leased` | `todo` | claimed by a worker, work not started |
  | `running` | `in_progress` | model generation in flight |
  | `succeeded` | `in_progress` | generated, awaiting scoring (not yet terminal) |
  | `scored` | `in_review` | scored, pre-publication |
  | `published` | `done` | terminal success |
  | `failed_retryable` | `blocked` | awaiting re-lease/retry |
  | `failed_terminal` | `cancelled` | terminal failure (canonical pick; `blocked` reserved for retryable) |

  The native state is always preserved in a `task.labels`/attribute so the mapping round-trips.
  Acceptance: a table-driven test asserts each native state maps to exactly one
  `task.status` and round-trips back via the preserved label.
  *(v0.3.1 / plan-time correction: the table above is **forward-looking** — it assumes the parent
  FR-38 8-state machine, which is **not yet built**. `benchmark_matrix/runner.py:22-28` currently
  produces only **6 terminal statuses**. The plan implements the **as-built 6→`task.status`
  mapping** (PLAN §T4.1).)*
  *(v0.4 / R2-F1 + R1-S2 — **`integrity_fail` is NOT a model failure**: it means a deterministic
  shortcut fired (cell void), an exclusion like `infra_fail`, not a model error. As-built mapping
  corrected: `ok→done`; `failed`/`timeout→cancelled`; `integrity_fail→cancelled` **with a
  `exclusion_reason=integrity` label** (or `infra` for `infra_fail`); `budget_skip`/`infra_fail→
  blocked`. **FR-21's model pass/fail tally MUST exclude `exclusion_reason`-labelled cells.**
  Acceptance: a test asserts integrity/infra cells are excluded from the model pass-rate.)*
  *(v0.4 / R2-F7 + R1-S9 — **forward-compat frozen**: when FR-38's 8-state machine lands, the
  mapping extension MUST be purely additive (add the missing native states); it MUST NOT re-target
  any of the as-built rows' `task.status`. Acceptance on this correction: the as-built rows are
  pinned by test.)*
- **FR-9.** Update `task.percent_complete` and emit progress/status events as cells advance, so a
  run exposes a burndown and completion ETA without scraping logs.
  *(v0.3 / R1-F1 — RESOLVES OQ-7: by **default**, execution-cell spans are reconstructed
  **post-hoc** from the FR-38 state-machine journal/artifacts after the run, keeping tracking
  fully decoupled from the cell execution path (honors FR-25's non-blocking MUST). **Live**
  per-cell update during the run is available only behind an explicit opt-in flag, and that path
  MUST itself honor the FR-25 async/timeout degradation contract. Acceptance: with live mode off,
  the run loop has zero synchronous calls into ContextCore emission — verifiable by grep/trace of
  the cell execution path for emit calls.)*
  *(v0.4 / R2-F8 + R1-S4 — **SHOULD** persist per-cell wall-clock `started_at`/`completed_at` in
  `benchmark_matrix/runner.py` → `cells.json` (additive ~2 lines, no run-loop coupling), so the
  default post-hoc burndown is wall-clock-true rather than completion-ordering-synthetic. Until
  then, the post-hoc burndown synthesizes ordering from cumulative `latency_s` — documented fidelity
  limit, not a blocker.)*
- **FR-10.** Record **per-cell failure** as a task in a terminal non-done state with a failure-code
  attribute (aligned to FR-39 failure taxonomy), so failures are never silently dropped and are
  queryable as business tasks.
- **FR-11.** Keep execution-cell tracking **decoupled from the results Loki stream** (FR-20/30):
  Business Observability tracks *task lifecycle/progress*; the Loki stream carries *scored
  metrics*. The two correlate on shared `run_id` + cell identity, not by duplicating data.

### Section C — AI Agent Observability: Insight Tracking

- **FR-12.** Capture agent **decisions** made while building the harness as insights via
  `AgentInsightBridge` — minimally the CRP R1–R3 architectural-review decisions
  (e.g. Temporal NO-GO, Cursor cut from Round 1, fail-closed budget default), each with
  `insight.type=decision`, a rationale, and `insight.evidence[]` pointing at the source doc.
- **FR-13.** Capture **risks/blockers/lessons** surfaced during build and run (e.g. the two
  CRITICAL items FR-44 sandbox / FR-45 redaction as `risk`; per-cell terminal failures as
  `blocker`; postmortem findings as `lesson`).
  *(v0.2: `AgentInsightBridge` exposes only `decision`/`lesson`/`question`. `risk`/`blocker`/
  `progress`/`discovery` require the generic `InsightEmitter.emit(InsightType.X, …)` —
  see FR-27.)*
- **FR-14.** Capture **run-time agent insights**: for each benchmark cell (or notable subset),
  optionally emit a `progress`/`discovery` insight (e.g. contamination-probe hit, catastrophic
  failure) so the agent-insights view reflects what the harness *learned*, not just task status.
  *(v0.2: notable-events-only by default per OQ-6 — do not emit a per-cell insight for all ~450
  cells.)*
- **FR-15.** Insights MUST carry `agent.id`, `agent.session_id`, `project.id`, and (where
  applicable) `insight.confidence`, `insight.audience`, and `insight.evidence[]` (pointing at the
  source doc/commit/artifact), and be queryable via TraceQL by `project.id` and `insight.type`.
  *(v0.2: the SDK bridge's `emit_decision()` does not expose `evidence`/`audience` today; covered
  by the FR-27 bridge extension.)*
- **FR-16.** Use `insight.supersedes` when a later decision overrides an earlier one (e.g. a CRP
  round reversing a prior round's suggestion), preserving the cross-model review memory rather
  than overwriting it.
  *(v0.2: `supersedes` exists on ContextCore's generic `emit()` but not the SDK bridge wrapper;
  covered by FR-27.)*

### Section D — Cost & Token Correlation (cross-cutting)

- **FR-17.** Attribute LLM **cost** to the unit of work so "cost per milestone" and "cost per
  cell" rollups are possible. *(v0.2: no `CostRecord` schema change — thread `task_id`/`cell_id`/
  `milestone_id` through the existing `tags`/`metadata` via `tracking_context()` at the call
  site. Emitting `task_id` as an OTel metric label (for Grafana grouping) is an optional small
  change to `CostMetrics.record()`; only do it if a cost-per-task panel is required.)*
  *(v0.3 / R1-F5 — **cardinality bound:** the optional `task_id` OTel **label** MAY be emitted at
  milestone/story granularity only. It MUST NOT be applied per-cell (~450 cell ids × providers ×
  tiers) without an explicit cardinality review, to prevent metric-series explosion. Per-cell cost
  identity still lives in `tags`/`metadata` (free, not a label-cardinality vector). Acceptance:
  `CostMetrics.record()` label set excludes per-cell ids unless a documented allowlist is set.)*
- **FR-18.** Make token/cost visible on the **agent view** by passing `input_tokens`/
  `output_tokens` into insight emission, which ContextCore maps to `gen_ai.usage.input_tokens`/
  `gen_ai.usage.output_tokens` (plus `gen_ai.request.model`, `gen_ai.system`) so the
  agent-insights / code-generation-health dashboards can show cost-per-decision and cost-per-cell.
  *(v0.2: this is NOT automatic — the SDK cost path emits `startd8.cost.*` only. The relevant
  dual-emit env var is `STARTD8_EMIT_MODE`, not `CONTEXTCORE_EMIT_MODE`. Wiring cost→insight
  tokens is explicit work; treat as optional enrichment, not a core requirement.)*
  *(v0.4 / R2-F4 — **resolve the FR-18↔FR-22 contradiction**: FR-18 is optional enrichment, but
  FR-22 requires a cost-per-decision panel. Resolution: token-passing into insight emission is
  **REQUIRED for the decision-insight path that feeds FR-22** (so cost-per-decision has data);
  it remains optional elsewhere. FR-22's panel is otherwise scoped to "where FR-18 enrichment is
  enabled.")*
- **FR-19.** Respect the benchmark's **secret-redaction** requirement (FR-45): no API keys,
  headers, account ids, or absolute home paths may appear in any emitted span attribute, event,
  or insight evidence ref. Tracking telemetry is subject to the same redaction gate as the
  results stream. *(v0.2: reuse the existing `redact()` utility (`fde/redaction.py`, 7 patterns);
  the work is wiring it into span-attribute / insight-evidence serialization before emission, not
  authoring new patterns.)*
  *(v0.3 / R1-F2 — **posture + bypass paths.** Redaction is **fail-open**: if `redact()` raises,
  the offending attribute/insight field is **dropped**, never the cell — a redaction failure must
  not stall or fail a benchmark cell (consistent with FR-25). FR-19 explicitly covers these known
  bypass paths, each of which MUST be redacted before emission: (a) `fail_task(reason=...)` free
  text, (b) `insight.evidence[]` refs that may contain absolute home paths, (c) raw exception
  messages, (d) span-event payloads. Acceptance: a golden test emits a span/insight whose reason,
  evidence ref, and exception message each contain a fake API key + absolute home path and asserts
  all are redacted; a fault-injection test makes `redact()` raise and asserts the attribute is
  dropped while the cell is unaffected.)*
  *(v0.4 / R1-S5 — **extend the bypass-path coverage** to: seed/milestone-derived `task.title`/
  `task.labels` (T1.2), the preserved native-`status` label + `error`-derived failure-code
  attribute (T4.1), and any `aggregate.json`/`leaderboard.md` text echoed into an insight (T3.x).
  Triage note: the general redaction posture stays **fail-open** (drop field, never the cell) for
  consistency with FR-25; the stricter "fail-closed for an un-redactable `insight.evidence[]` ref"
  variant R1-S5 also proposed is **deferred** — it trades a hard non-blocking guarantee for a
  marginal leak-defense already backstopped by the parent FR-45 human review.)*

### Section E — Dashboards & Surfacing

- **FR-20.** Provide a **project-progress / sprint dashboard** (Business view) for the delivery
  epic: burndown, status breakdown, WIP, blocked tasks, velocity. Built via the SDK's existing
  dashboard tooling / `/dbrd-cr8r`, not hand-authored JSON.
- **FR-21.** Provide an **execution-run dashboard** (Business view) for a live run: cell
  completion %, pass/fail tallies, ETA, top failure codes — distinct from the existing
  *results* leaderboard dashboard (FR-21 of the parent reqs).
- **FR-22.** Provide an **agent-insights dashboard** (Agent view): recent decisions, open
  blockers, high-confidence insights, cost-per-decision — scoped to this `project_id`.
  *(v0.4 / R2-F4 — the cost-per-decision panel depends on FR-18 token enrichment on the
  decision-insight path, which FR-18 now makes REQUIRED for that path.)*

### Section F — Integration & Reuse Constraints

- **FR-23.** Reuse existing SDK machinery wherever it exists: `task_tracking_emitter`
  (SpanState v2 emission), `ContextCoreWorkflowAdapter`/`ContextCoreTaskRunner` (lifecycle),
  `AgentInsightBridge` (insights), `CostTracker`/`CostMetrics` (cost), `otel.py` `ProjectContext`.
  Do **not** re-implement task-span persistence, insight emission, or cost metrics.
  *(v0.4 / R2-F3 — **anti-reimplementation acceptance** (this prohibition was previously
  untestable): the tracking code MUST import and call `task_tracking_emitter`,
  `AgentInsightBridge`, `CostMetrics`/`CostTracker`, and ContextCore's `InsightEmitter.emit()` —
  it MUST NOT define its own SpanState serializer, insight emitter, or cost-metric recorder.
  Acceptance: a test/grep asserts no duplicate serializer/emitter/recorder in the tracking module.)*
- **FR-24.** Honor the ContextCore ownership boundary: the SDK **emits** task/insight spans and
  zero-point events; ContextCore **owns** the derived progress/velocity/burndown metric
  computation. Do not emit progress-delta gauges from the SDK.
  *(v0.4 / R2-F2 — **testable acceptance** (this prohibition was previously unverifiable): a
  contract test asserts the SDK emits only task/insight spans + zero-point `task.created`/status
  events, and emits **no** derived rate/velocity/burndown gauge metric — those are computed by
  ContextCore. R1-S1 raised the same gap from the plan side.)*
- **FR-25.** Tracking MUST be **opt-in and non-blocking**: a benchmark run with tracking disabled
  behaves exactly as today; tracking failures (e.g. ContextCore unreachable) degrade gracefully
  and never fail or slow a benchmark cell.
  *(v0.3 / R1-F10 — **quantitative degradation contract**, covering tracking *enabled*, not just
  disabled: when the live opt-in (FR-9) is on, per-cell emission MUST be async / fire-and-forget
  or out-of-band, with a bounded timeout, so a slow or hung ContextCore endpoint adds at most a
  defined latency budget (default ≤250 ms/cell, configurable) and can never stall a cell. A write
  that exceeds the timeout is abandoned, not retried inline. Acceptance: a fault-injection test
  stubs the ContextCore endpoint to hang and asserts the cell completes within `baseline + budget`
  and the emission times out without raising into the run loop.)*
  *(v0.4 / R2-F6 — **emission-loss accounting**: every abandoned/timed-out emission MUST increment
  an observable counter (e.g. `startd8.tracking.dropped`), so "non-blocking" cannot silently become
  "tracking incomplete." Acceptance: the fault-injection test asserts the dropped-counter increments
  when an emission is abandoned.)*
- **FR-26.** A single `project_id` (and `sprint_id` where relevant) identifies this benchmark
  project across Business and Agent observability, so the two paradigms join on shared identity.
  *(v0.2: `.contextcore.yaml` currently declares `project_id="startd8-sdk"` (the whole SDK) with
  no `sprint_id`. **DECIDED (user, 2026-06-13):** dedicated `project_id="startd8-benchmark"` with
  per-round `sprint_id="summer-2026"`, so the benchmark's burndown is isolated and the
  recurring-series framing (parent FR-25) gets a clean per-round sprint axis. This `project_id`
  is set via `TaskTrackingConfig`/`ContextCoreConfig` at emission time — it does NOT change the
  repo-level `.contextcore.yaml`.)*

- **FR-27.** Extend `AgentInsightBridge` to cover the insight surface this project needs, as
  **two separable acceptance criteria** (v0.3 / R1-F6 — a partial implementation must be visible,
  not silently pass a coarse review):
  - **FR-27a — type surface:** expose `risk`/`blocker`/`progress`/`discovery` (in addition to
    `decision`/`lesson`/`question`), forwarding to ContextCore's generic
    `InsightEmitter.emit(InsightType.X, …)`. *Enables FR-13, FR-14.* Acceptance: a test emits each
    new type and asserts the correct `insight.type` lands in ContextCore.
  - **FR-27b — parameter surface:** add `evidence[]`, `audience`, and `supersedes` parameters,
    forwarded to the same generic `emit()`. *Enables FR-12, FR-15, FR-16.* Acceptance: a test
    asserts `evidence`/`audience`/`supersedes` round-trip through the bridge into ContextCore.
- **FR-28.** *(v0.3 / R1-F9 — relationship to FR-27 clarified.)* The latent
  `AgentInsightBridge.emit_question()` bug — it calls a non-existent
  `InsightEmitter.emit_question()` (runtime `AttributeError`) — is **subsumed by FR-27a's
  "forward everything through generic `emit()`" rewrite**: once questions route through
  `emit(InsightType.QUESTION, …)`, the bug evaporates as a side effect. FR-28 therefore reduces
  to a **regression test + ordering gate**, not a second code change: (a) a regression test
  asserting `emit_question()` raises no `AttributeError` and exactly one code path emits questions;
  (b) an ordering gate — FR-27a MUST land before the benchmark relies on the bridge. This avoids
  duplicate/conflicting edits to the same bridge method.

### Section G — Join Contract (v0.3 / R1-F8)

> The Business/Agent separation's correctness rests on cross-view joins that FR-11/FR-17/FR-18/
> FR-26 each assert in scattered prose. This table is the single verifiable contract: every
> asserted join names its shared attribute and direction. Acceptance (review checklist): every
> join asserted in those FRs appears here with a named attribute.

| Link | Shared attribute(s) | Direction | Asserted by |
|------|---------------------|-----------|-------------|
| Business-execution ↔ results Loki stream | `run_id` + cell-identity tuple (`service`/`model`/`language`/`rep`) | task span ⇄ Loki record | FR-11, FR-7 |
| Business-delivery ↔ cost | `milestone_id`/`task_id` (via cost `tags`/`metadata`) | cost record → task | FR-17 |
| Business-execution ↔ cost | `cell_id` (via cost `tags`/`metadata`) | cost record → cell task | FR-17 |
| Agent-insight ↔ cost / tokens | `gen_ai.usage.*` on the insight span (tokens passed into `emit()`) | cost/tokens → insight | FR-18 |
| Business ↔ Agent (both paradigms) | `project_id` (`startd8-benchmark`) + `sprint_id` (`summer-2026`) | shared identity | FR-26 |

---

## 3. Non-Requirements

- **NR-1.** Does **not** change the benchmark's scoring methodology, roster, or results schema
  (FR-11/39 of the parent reqs are untouched).
- **NR-2.** Does **not** replace or modify the results Loki stream / leaderboard (FR-20/21/30
  parent). This is additive: project/agent tracking alongside results.
- **NR-3.** Does **not** build new ContextCore infrastructure (no new metric backends, no new
  span schema). Consumes ContextCore's existing SpanState v2 + semantic conventions.
- **NR-4.** Does **not** introduce autonomous agent self-correction. Insights are recorded for
  human/agent visibility, not to auto-modify the run (consistent with the Kaizen value model).
- **NR-5.** Does **not** require ContextCore to be running for a benchmark to execute (see FR-25).
- **NR-6.** Out of scope: tracking delivery tasks of *other* SDK projects; multi-project portfolio
  rollups beyond this one benchmark epic.

---

## 4. Open Questions

- **OQ-1.** ✅ **RESOLVED (planning):** Build Section A (delivery) first, Section B (execution)
  second. A is feasible now; B depends on the FR-38 state machine.
- **OQ-2.** ✅ **RESOLVED (CRP R2-F5 / R1-S8 — decided before T4.1 to avoid mid-build rework):**
  **per-cell task spans only for the flagship/full-app run (M3.5); service-level stories carrying
  cell *counts* for the large matrix.** FR-7 annotated provisional accordingly; the `run_id` +
  cell-identity join key is preserved on the rollup count records so the Section-G joins still hold.
- **OQ-3.** ✅ **RESOLVED (planning):** Coarser grain — tasks = milestone work-items, not 1:1
  FR→task. Cross-cutting FRs (44/45) would distort burndown if forced to 1:1.
- **OQ-4.** ✅ **RESOLVED (CRP R1-F7):** Backfill — and the burndown must be *honest*: backfilled
  `done` events carry real merge-commit timestamps (not run-time-now), with `task.created`
  predating the earliest completion. Promoted to a firm acceptance criterion on FR-3.
- **OQ-5.** ✅ **RESOLVED (planning):** No `CostRecord` schema change — thread identity via
  `tags`/`metadata`/`tracking_context()`. Optional `task_id` OTel label only if a cost-per-task
  panel is needed.
- **OQ-6.** **Insight emission trigger (FR-14):** Per-cell run-time insights for ~450 cells could
  be excessive. *Resolved default: notable-events-only (failure, contamination hit, catastrophic).*
- **OQ-7.** ✅ **RESOLVED (CRP R1-F1):** Post-hoc reconstruction from the FR-38 journal is the
  **default** (decoupled from the run loop, honors FR-25); live per-cell update is an explicit
  opt-in bound by the FR-25 degradation contract. Promoted to firm requirement on FR-9. An
  undecided question could not be left gating FR-25's normative MUST.
- **OQ-8.** ✅ **RESOLVED (planning):** `project_id` source is `startd8-sdk` (no sprint). Superseded
  by the FR-26 decision (recommend dedicated `startd8-benchmark` / `summer-2026`).

---

*v0.2 — Post-planning self-reflective update. 7 requirements corrected/narrowed, 2 added
(FR-27 bridge extension, FR-28 bug fix), 4 open questions resolved. One latent bug surfaced
(`emit_question`). Pending user decision: FR-26 `project_id` choice.*

*v0.3 — Post-CRP Round 1. All 10 R1 suggestions ACCEPTED and applied: FR-3 (honest backfill),
FR-7 (run_id/cell-identity required attrs), FR-8 (deterministic 9→7 mapping table), FR-9 +
OQ-7 (post-hoc default / live opt-in), FR-17 (label-cardinality bound), FR-19 (fail-open +
bypass paths), FR-25 (quantitative degradation contract), FR-27 (split a/b), FR-28 (subsumed →
regression+ordering gate), new Section G join-contract table. OQ-4/OQ-7 promoted to firm
requirements. FR-26 decided (dedicated `startd8-benchmark`/`summer-2026`). Dispositions in
Appendix A.*

*v0.3.1 — Plan-time FR-8 correction: runner has no FR-38 state machine (6 terminal statuses);
as-built 6→`task.status` mapping in PLAN §T4.1.*

*v0.4 — Post-CRP R2 (dual-doc). All 8 R2-F suggestions ACCEPTED: FR-8 (integrity_fail exclusion +
forward-freeze), FR-23/FR-24 (testable acceptance for the negative reqs), FR-18/FR-22 (cost-per-
decision reconciliation), FR-7+OQ-2 (granularity resolved), FR-25 (emission-loss counter), FR-9
(wall-clock cell timestamps SHOULD), FR-19 (extended bypass scope; fail-closed-evidence deferred).
Companion plan suggestions R1-S1..S9 triaged in PLAN.md. NO open questions remain.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Promote OQ-7 to firm req: post-hoc default, live behind opt-in | R1 (claude-opus-4-8) | Applied to **FR-9** + OQ-7 RESOLVED. Acceptance: live-off → zero sync emit calls in cell path. | 2026-06-13 |
| R1-F2 | FR-19 fail-open posture + bypass-path enumeration | R1 (claude-opus-4-8) | Applied to **FR-19**: fail-open (drop attr, not cell) + covers `fail_task(reason)`, evidence abs-paths, exception strings, span-event payloads. Golden + fault-injection acceptance. | 2026-06-13 |
| R1-F3 | `run_id` + cell-identity as REQUIRED emitted attributes | R1 (claude-opus-4-8) | Applied to **FR-7**; also anchored in Section G join table. Join-on-`run_id` acceptance. | 2026-06-13 |
| R1-F4 | Deterministic 9→7 status mapping table | R1 (claude-opus-4-8) | Applied to **FR-8**: canonical table, `failed_terminal→cancelled`, `failed_retryable→blocked`. Table-driven round-trip test. | 2026-06-13 |
| R1-F5 | Bound FR-17 `task_id` OTel label cardinality | R1 (claude-opus-4-8) | Applied to **FR-17**: label at milestone/story grain only, never per-cell w/o cardinality review. | 2026-06-13 |
| R1-F6 | Split FR-27 into separable a/b acceptance criteria | R1 (claude-opus-4-8) | Applied to **FR-27a** (type surface) / **FR-27b** (param surface) with per-clause FR traceability. | 2026-06-13 |
| R1-F7 | FR-3/OQ-4 honest-backfill timestamp criterion | R1 (claude-opus-4-8) | Applied to **FR-3** + OQ-4 RESOLVED: merge-commit timestamps, created < min(completion). | 2026-06-13 |
| R1-F8 | Add explicit join-contract table | R1 (claude-opus-4-8) | Applied as new **Section G** (5 join rows). | 2026-06-13 |
| R1-F9 | Clarify FR-28 relationship to FR-27 (subsumed) | R1 (claude-opus-4-8) | Applied to **FR-28**: reduced to regression test + ordering gate; code change subsumed by FR-27a. | 2026-06-13 |
| R1-F10 | FR-25 quantitative degradation contract (latency/timeout/async) | R1 (claude-opus-4-8) | Applied to **FR-25**: async/fire-and-forget, ≤250 ms/cell default budget, timeout-abandon. Fault-injection acceptance. | 2026-06-13 |
| R2-F1 | `integrity_fail` not bucketed with model failures | R2 (claude-opus-4-8) | Applied to **FR-8**: `exclusion_reason=integrity\|infra` label; FR-21 model pass/fail MUST exclude. Pairs w/ R1-S2. | 2026-06-14 |
| R2-F2 | FR-24 testable acceptance (no SDK-derived gauges) | R2 (claude-opus-4-8) | Applied to **FR-24**: contract test asserts only spans+zero-point events, no rate/velocity gauge. Pairs w/ R1-S1. | 2026-06-14 |
| R2-F3 | FR-23 anti-reimplementation acceptance | R2 (claude-opus-4-8) | Applied to **FR-23**: test asserts tracking imports/calls existing emitters, defines no duplicate serializer/emitter/recorder. | 2026-06-14 |
| R2-F4 | Resolve FR-18↔FR-22 cost-per-decision contradiction | R2 (claude-opus-4-8) | Applied to **FR-18/FR-22**: token-passing REQUIRED on the decision-insight path feeding FR-22; optional elsewhere. | 2026-06-14 |
| R2-F5 | Resolve OQ-2 before FR-7/8 final | R2 (claude-opus-4-8) | Applied: **OQ-2 RESOLVED** (per-cell flagship, counts large matrix); **FR-7** annotated provisional. Pairs w/ R1-S8. | 2026-06-14 |
| R2-F6 | Emission-loss accounting counter | R2 (claude-opus-4-8) | Applied to **FR-25**: abandoned/timed-out emission increments `startd8.tracking.dropped`; fault-injection asserts it. | 2026-06-14 |
| R2-F7 | Pin FR-8 as-built mapping forward-compat-frozen | R2 (claude-opus-4-8) | Applied to **FR-8**: FR-38 extension additive-only; as-built rows pinned by test. Pairs w/ R1-S9. | 2026-06-14 |
| R2-F8 | FR-9 SHOULD persist wall-clock cell timestamps | R2 (claude-opus-4-8) | Applied to **FR-9** as SHOULD (runner.py `started_at`/`completed_at` → cells.json). Pairs w/ R1-S4. | 2026-06-14 |
| R1-S5 | Extend redaction bypass scope (req side) | R2 dual (claude-opus-4-8) | Applied to **FR-19**: +task.title/labels, native-status label, error-derived code, aggregate echoes. Fail-closed-evidence variant DEFERRED (FR-25 consistency). | 2026-06-14 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-06-13

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-13 (UTC)
- **Scope**: Requirements-only review (F-prefix). Weighted per sponsor focus file: §0 feasibility, Business/Agent separation, cost→task linkage (FR-17/18), redaction (FR-19), non-blocking (FR-25), open questions OQ-2/4/7.

**Executive summary (top risks / gaps / opportunities):**

- FR-25 (non-blocking) and OQ-7 (live vs post-hoc) are in tension: a *normative* MUST sits next to an *undecided* design choice that determines whether the MUST can hold. OQ-7 should be promoted to a requirement, not left open.
- FR-19 redaction is specified as "wire `redact()` in" but lacks a **fail-open vs fail-closed** posture and an enumeration of bypass paths (`fail_task(reason=...)` free text, evidence refs with absolute paths, exception messages). Highest-severity gap given it inherits parent FR-45 CRITICAL.
- The Business/Agent boundary (Sections A/B vs C) is "joined only on `project_id`/`run_id`" but **`run_id` is never defined as a required attribute** in Section B (FR-7/8 use "run"); the join key is asserted but not made testable.
- FR-8's 9-state→7-value enum collapse is lossy by design (acceptable) but **`failed_terminal→blocked or cancelled` is non-deterministic** ("or") — an implementer/QA cannot verify the mapping without a fixed rule.
- FR-17 "no schema change" at ~450 cells risks **OTel label cardinality explosion** if the optional `task_id` label is ever enabled per-cell; the requirement should bound where the label may be applied.
- FR-3/OQ-4 backfill with "synthetic timestamps" / "merge commit dates" has no stated acceptance criterion for what makes a backfilled burndown "honest" vs misleading.
- FR-27 bundles four new insight types **plus** three new parameters (`evidence`/`audience`/`supersedes`) into one requirement — testable acceptance criteria are not separable; risk of partial-implementation passing review.
- FR-28 (latent `emit_question` bug fix) is correctly gated ("MUST land before…") but has no link to *which* FRs it blocks; traceability is implicit.
- Opportunity: FR-11/FR-26 already establish a shared-identity join; an explicit cross-reference contract (one table: which attribute joins which view) would make the whole separation testable cheaply.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Promote OQ-7 (live vs post-hoc) to a firm requirement: state that execution-cell tracking reconstructs spans **post-hoc from the FR-38 state-machine journal** by default, with live update behind an explicit opt-in flag that itself honors FR-25. | FR-25 says tracking MUST never fail or slow a cell, but OQ-7 leaves open the one design choice that decides whether that MUST is achievable. An undecided question cannot gate a normative MUST. The OQ-7 "Lean" already favors post-hoc; commit it. | Section B (new FR or amend FR-9) + mark OQ-7 RESOLVED in §4 | QA: with live mode off, assert the run loop has zero synchronous calls into ContextCore emission (grep/trace for emit calls inside the cell execution path). |
| R1-F2 | Security | high | FR-19 must declare a **fail-open** posture explicitly (redaction failure drops the attribute/insight, never the cell) AND enumerate the known bypass paths it covers: `fail_task(reason=...)` free text, `insight.evidence[]` absolute paths, raw exception messages, and span event payloads. | "Wire `redact()` in" is necessary but not sufficient — the FR doesn't say what happens if redaction raises, nor which serialization paths are in scope. Under parent FR-45 CRITICAL, an unredacted exception string is a leak. Best-effort vs gate must be stated. | FR-19 (add posture sentence + bypass-path bullet list) | QA: golden test — emit a span/insight whose reason, evidence ref, and exception message each contain a fake API key + absolute home path; assert all redacted; inject a `redact()` exception and assert attribute dropped, cell unaffected. |
| R1-F3 | Interfaces | high | Define `run_id` (and the full cell identity tuple `service × model × language × rep`) as **required emitted attributes** in FR-7/FR-8, since FR-11 and FR-26 assert the Business↔results and Business↔Agent joins happen on `run_id` + cell identity. | The join key is the load-bearing element of the entire A/B vs C separation, yet it's only named in prose (FR-11) and never made a required attribute in the section that emits it. Without it the separation is un-joinable and untestable. | FR-7/FR-8 (add `run_id` + cell-identity attribute requirement) | QA: assert every execution-cell task span carries `run_id` and a parseable cell-identity attribute; assert a TraceQL join on `run_id` returns both the task span and the matching Loki results record. |
| R1-F4 | Data | medium | Make FR-8's terminal-state mapping deterministic: replace `failed_terminal→`blocked` or `cancelled`` with a fixed rule (e.g. `failed_terminal→cancelled`, reserve `blocked` for `failed_retryable` awaiting lease), and give the full 9→7 mapping as a table. | "or" makes the mapping non-deterministic; two implementers (or the impl vs QA) will diverge, and burndown/blocked-count metrics depend on the choice. The native state is preserved in `task.labels` anyway, so the canonical pick only needs to be *consistent*. | FR-8 (convert prose to a 9-row mapping table) | QA: table-driven test asserting each of the 9 native states maps to exactly one `task.status` and round-trips back via the preserved label. |
| R1-F5 | Data | medium | Bound FR-17's optional `task_id` OTel label: state it MAY be emitted at **milestone/story granularity only**, and MUST NOT be applied per-cell (~450 values) without an explicit cardinality review, to prevent metric label explosion. | "No schema change, thread via tags" is safe for storage, but the optional `task_id` *OTel label* is a cardinality vector — 450 cell ids × providers × tiers can blow up the metric series. The FR invites the label without bounding it. | FR-17 (add cardinality-bound sentence) | QA: assert `CostMetrics.record()` label set excludes per-cell ids unless a documented allowlist is set; cardinality test on emitted series count. |
| R1-F6 | Validation | medium | Split FR-27 into separable acceptance criteria: (a) expose `risk`/`blocker`/`progress`/`discovery`; (b) add `evidence[]`/`audience`/`supersedes` params forwarding to generic `emit()`. Enumerate which downstream FR each clause enables. | FR-27 bundles a type-surface expansion and a parameter expansion; a partial implementation (types only, no evidence) could pass a coarse review while silently breaking FR-15/FR-16. Separable criteria make partial completion visible. | FR-27 (sub-bullets a/b with per-clause FR traceability) | QA: two independent tests — one emitting each new type, one asserting `evidence`/`audience`/`supersedes` round-trip through the bridge into ContextCore. |
| R1-F7 | Validation | medium | FR-3 + OQ-4: define an acceptance criterion for a "honest" backfilled burndown — e.g. backfilled `done` events MUST carry the real merge-commit timestamp (not run-time-now), and the zero-point `task.created` MUST predate the earliest backfilled completion. | Backfill with "synthetic timestamps" is currently unfalsifiable — any burndown shape would "pass." Tying timestamps to merge commits and ordering the created event makes it testable and prevents a flat/instant burndown artifact. | FR-3 (add criterion) + OQ-4 (note the criterion when resolving) | QA: assert backfilled completion timestamps equal `git log` merge dates for M0–M4; assert created-event timestamp < min(completion timestamps). |
| R1-F8 | Architecture | low | Add an explicit **join-contract table** to the doc (one row per cross-view link: Business-delivery↔cost, Business-execution↔results-Loki, Agent-insight↔cost) naming the shared attribute and direction, since FR-11/FR-17/FR-18/FR-26 each assert a join in prose. | The separation's correctness rests on these joins being consistent; collecting them in one table turns four scattered prose assertions into a single verifiable contract and helps the next reviewer. | New subsection after §2 Section F, or amend FR-26 | QA: review checklist — every asserted join in FR-11/17/18/26 appears in the table with a named attribute. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | medium | Stress §0/FR-28: FR-28 says fix `emit_question` and "route through generic `emit()`," but FR-13/FR-27 also route the *other* types through generic `emit()`. State whether FR-28 is subsumed by FR-27's forwarding rewrite or is a distinct pre-req — and if subsumed, keep FR-28 only as the **regression test + ordering gate**, not a second code change. | If FR-27's "forward everything to `emit()`" lands first, the `emit_question` bug evaporates as a side effect, making FR-28's "code change" redundant while its *test/ordering* value remains. Leaving both as independent code changes risks duplicate/conflicting edits to the same bridge method. | FR-28 (clarify relationship to FR-27) | QA: assert exactly one code path emits questions post-change; FR-28 reduces to a regression test asserting no `AttributeError`. |
| R1-F10 | Ops | medium | Adversarial on FR-25 "non-blocking": specify the **degradation contract** quantitatively — define the max added latency budget per cell when tracking is *enabled* (not just disabled), and require emission to be async/fire-and-forget or out-of-band so a slow/hung ContextCore endpoint cannot stall a cell even with tracking on. | FR-25's "behaves exactly as today" is only asserted for tracking *disabled*. The real risk is tracking *enabled* + ContextCore slow/hung: "degrade gracefully" is unfalsifiable without a latency/timeout bound. A hung HTTP write is the classic non-blocking violation. | FR-25 (add latency budget + timeout/async requirement) | QA: fault-injection test — stub ContextCore endpoint to hang; assert cell completes within `baseline + budget` and emission times out without raising into the run loop. |

**Endorsements / Disagreements:** none — Appendix A/B/C contain no prior rounds to react to (this is R1).

#### Review Round R2 — claude-opus-4-8 — 2026-06-14 (dual-document review w/ the plan)

- **Reviewer**: claude-opus-4-8
- **Scope**: Dual-document review (requirements F-prefix; plan got S-prefix in PLAN.md). Weighted per the dual-doc focus file: traceability, FR-8 as-built correction, sequencing, non-blocking executability, bridge blast radius, redaction sufficiency, open items.
- **Triage**: all 8 ACCEPTED (see Appendix A). Recovered verbatim after a concurrent-process file loss; preserved here for the cross-model memory.

| ID | Area | Severity | Suggestion | Placement |
|----|------|----------|------------|-----------|
| R2-F1 | Data | high | `integrity_fail` must NOT bucket with genuine model failures — map→`blocked` or keep `cancelled` + `exclusion_reason=integrity\|infra` label; FR-21 model pass/fail MUST exclude these. | FR-8 |
| R2-F2 | Validation | high | FR-24 needs a testable acceptance: contract test asserts SDK emits only spans+zero-point events, no derived rate/velocity/burndown gauge. | FR-24 |
| R2-F3 | Architecture | medium | FR-23 needs an anti-reimplementation acceptance: tracking imports/calls existing emitters, defines no duplicate serializer/emitter/recorder. | FR-23 |
| R2-F4 | Interfaces | medium | Resolve FR-18↔FR-22: FR-18 "optional" vs FR-22 "cost-per-decision" — make token-passing REQUIRED on the decision-insight path feeding FR-22. | FR-18/FR-22 |
| R2-F5 | Architecture | medium | Resolve OQ-2 before FR-7/8 are final, or annotate FR-7 provisional — per-cell vs counts changes what FR-7 emits. | FR-7 / OQ-2 |
| R2-F6 | Ops | medium | FR-25 needs emission-loss accounting: abandoned/timed-out emissions increment an observable counter. | FR-25 |
| R2-F7 | Risks | medium | Pin FR-8's as-built mapping forward-compat-frozen: FR-38 extension additive-only, never re-target as-built rows. | FR-8 |
| R2-F8 | Validation | low | FR-9 SHOULD persist per-cell wall-clock `started_at`/`completed_at` so the default post-hoc burndown is wall-clock-true. | FR-9 |

> The companion plan review round (R1-S1..S9) lives in `PLAN.md` Appendix C; several pair with the
> above (R1-S1↔R2-F2/F3, R1-S2↔R2-F1, R1-S4↔R2-F8, R1-S8↔R2-F5, R1-S9↔R2-F7).
