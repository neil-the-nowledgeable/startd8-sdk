# Implementation Plan — Benchmark Observability Tracking (ContextCore Business + AI Agent)

**Version:** 0.2 (Post-CRP R1 dual-doc — 9 S-suggestions applied; reconstructed after concurrent-process loss)
**Date:** 2026-06-14
**Status:** Draft
**Implements:** `REQUIREMENTS.md` (internal v0.4, 28 FRs)
**History:** v0.1 authored 2026-06-13; the original copy was lost when a parallel benchmark-extraction
process cleaned untracked docs. Reconstructed here in a **tracked** home so it cannot be clobbered again.

---

## 0. Plan-time Discoveries (feed back to requirements)

| Requirement assumption | Code reality | Plan action |
|------------------------|--------------|-------------|
| **FR-8** maps the FR-38 8-state cell machine | `benchmark_matrix/runner.py:22-28` has **no FR-38 state machine** — only 6 terminal `CellResult.status` values: `ok`/`failed`/`timeout`/`integrity_fail`/`budget_skip`/`infra_fail`. | Implement the **as-built 6-status mapping** (§T4.1). FR-8 forward-looking. (req v0.3.1) |
| **FR-9** burndown implies a wall-clock timeline | Per-cell record has `latency_s` only — **no start/end timestamps** (`runner.py:56-77`). | Default post-hoc burndown is ordering-based; **R1-S4/R2-F8**: add `started_at`/`completed_at` to `cells.json` (additive). |
| **FR-27b** forwards to a generic `emit()` | Confirmed: `InsightEmitter.emit()` takes evidence/supersedes/audience/tokens (21 params). | Pure forwarding + `Evidence` adapter. |

**As-built artifact contract:** a finished run writes `REPO/.startd8/benchmark-runs/{spec_hash[:12]}/`:
`run-spec.json` (run identity — use `spec_hash[:12]` as `run_id`), `cells.json` (per-cell
`CellResult.to_dict()` incl. `cell_id`, identity, status, cost, `latency_s`, tokens, error),
`aggregate.json`, `leaderboard.md`. **Post-hoc reconstruction is a pure reader — zero run-loop
changes** — the spine of the FR-25 non-blocking guarantee.

---

## 1. Approach & Sequencing

```
T0 Foundations ──┬─> T1 Delivery tracking (Section A)      [standalone, ship first]
 (redaction,     ├─> T2 Cost linkage (Section D)
  bridge rewrite)├─> T3 Agent insights (Section C)         [needs T0.2/T0.3]
                 └─> T4 Execution-cell tracking (Section B)[needs T0.1, T1.1]
                          └─> T5 Dashboards + join contract (Sections E/G)
```

Tracking is **opt-in** throughout (FR-25); default behavior is byte-for-byte today.

**✅ T0 + T1.1 are IMPLEMENTED and committed** (branch `feat/benchmark-tracking-t0`, 42 tests green) —
see §2 status tags. Remaining: T2, T3, T4, T5.

---

## 2. Workstreams

### T0 — Foundations  ✅ DONE (committed)

**T0.1 — Redaction middleware (FR-19, R1-F2).** ✅ `integrations/tracking_redaction.py`:
`redact_text`/`redact_attrs`/`redact_evidence`, fail-open (drop field, never the cell), home-path
scrubbing. *(R1-S5 — extend application to seed-derived `task.title`/`task.labels` (T1.2), the
native-`status` label + `error`-derived failure-code (T4.1), and `aggregate.json` echoes (T3.x) at
those emission sites; the module already covers them, the call sites are wired as those workstreams
land. Fail-closed-for-evidence variant DEFERRED — FR-25 consistency.)*

**T0.2/T0.3 — AgentInsightBridge rewrite (FR-27a/b, FR-28, R1-F6/F9).** ✅ one `_emit()` chokepoint
→ `InsightEmitter.emit()`; all 9 types; `evidence`/`audience`/`supersedes`; `emit_question` fixed.
*(R1-S6 — caller-inventory check DONE: `grep emit_question src/ tests/ scripts/` shows no external
caller depends on the old `AttributeError`; the rewrite is safe.)*

### T1 — Delivery-Task Tracking (Section A)

**T1.1 — emitter `initial_statuses` + honest backfill (FR-3, R1-F7).** ✅ added `initial_statuses`,
`completion_timestamps`, `creation_timestamps` (defaulted → byte-for-byte prior behavior); terminal
status sets top-level `status=OK` + `end_time` + completion event; backfilled `created` never
post-dates completion.

**T1.2 — source-of-truth map + generator (FR-1/2/3, R1-F7).** ⬜ `docs/.../tracking/milestones.yaml`
(milestone → work-items → status → merge SHA/date; grain = work-items, OQ-3) + `scripts/
emit_benchmark_tracking.py` calling the emitter with `project_id="startd8-benchmark"`,
`sprint_id="summer-2026"`. *(R1-S5 — apply redaction to seed-derived titles/labels here.)*

**T1.3 — transitions + deps (FR-4/5).** ⬜ `TaskTrackerWrapper.update_status()`/`add_event()`;
`depends_on`→`task.blocked_by` for the M2.5→M3 critical path.

### T2 — Cost Linkage (Section D)  ⬜

**T2.1 — thread identity (FR-17, R1-F5).** No `CostRecord` schema change — `tracking_context(...)`
tags. `task_id` OTel label milestone/story grain only (cardinality bound).

**T2.2 — token/cost on agent view (FR-18, R2-F4).** Pass `input_tokens`/`output_tokens` into insight
emission → `gen_ai.usage.*`. **REQUIRED on the decision-insight path that feeds FR-22**; optional
elsewhere.

### T3 — Agent-Insight Wiring (Section C)  ⬜ (needs T0.2/T0.3 ✅)

T3.1 build-time decisions (FR-12); T3.2 risks/blockers/lessons (FR-13); T3.3 notable-events-only
run-time insights (FR-14, OQ-6). Evidence refs redacted via T0.1.

### T4 — Execution-Cell Tracking (Section B)  ⬜ (needs T0.1 ✅, T1.1 ✅)

**T4.1 — post-hoc reconstructor (FR-7/8/9/10, R1-F3/F4).** `benchmark_matrix/tracking.py`:
`reconstruct_run_tracking(run_dir)` reads `run-spec.json`+`cells.json`, builds epic(run)→
story(service)→task(cell). **OQ-2 RESOLVED (R1-S8): per-cell tasks for the flagship/full-app run;
service stories + cell counts for the large matrix** — so this is built granularity-aware from the
start, not reworked mid-stream. Required attrs: `run_id` + cell-identity (R1-F3).

As-built status mapping **(corrected per R1-S2/R2-F1)** — `integrity_fail` and `infra_fail` are
*exclusions*, not model failures:

| `CellResult.status` | `task.status` | label | notes |
|---------------------|---------------|-------|-------|
| `ok` | `done` | — | ran + scored |
| `failed` | `cancelled` | — | genuine model failure |
| `timeout` | `cancelled` | — | genuine terminal failure |
| `integrity_fail` | `cancelled` | `exclusion_reason=integrity` | deterministic shortcut fired → void; **excluded from FR-21 model pass/fail** |
| `infra_fail` | `blocked` | `exclusion_reason=infra` | auth/quota; **excluded from scoring** |
| `budget_skip` | `blocked` | — | budget ceiling; never ran |

Native `status` preserved in a label (round-trips). **R1-S9: the 6 rows are forward-frozen** — when
FR-38 lands the table extends additively, never re-targeting these. **R1-S4: also persist per-cell
`started_at`/`completed_at`** (small `runner.py` addition) for a wall-clock-true burndown.
Acceptance: table-driven 6→status round-trip; pass/fail-excludes-exclusions test; pinned-rows test.

**T4.2 — non-blocking emission contract (FR-25, R1-F10, R1-S3, R2-F6).** Async / fire-and-forget
with bounded timeout (≤250 ms/cell). **R1-S3 — named substrate + drain semantics**: a bounded
`queue.Queue` + a single daemon drainer thread runs writes off the cell critical path; at
`run_matrix()` exit the queue is best-effort-drained with a deadline, then abandoned. **R2-F6 —
emission-loss accounting**: every abandoned/timed-out write increments `startd8.tracking.dropped`.
Acceptance: hung-endpoint fault-injection → cell within `baseline+budget`, dropped-counter increments.

**T4.3 — live opt-in (FR-9 live, OQ-7).** Default post-hoc; `--track-live` flag routes per-cell
through the T4.2 async emitter. Live-off → zero sync ContextCore calls in the run loop.

### T5 — Dashboards + Join Contract (Sections E/G)  ⬜

T5.1–T5.3 three `/dbrd-cr8r` dashboards (project-progress; execution-run; agent-insights, scoped to
`project_id="startd8-benchmark"`). **T5.4 — machine-checkable join fixture (R1-S7)**: encode the
Section-G join rows as a YAML/JSON fixture; the test asserts each named attribute is actually present
on the emitted span/record/cost row, so the contract can't silently drift. **Plus the FR-23/FR-24
contract tests (R1-S1/R2-F2/F3)**: assert reuse-not-reimplement and no SDK-derived gauges.

---

## 3. Testing Strategy

Unit: emitter statuses ✅, 6→status round-trip + exclusion, bridge routing ✅, redaction golden+fail-open ✅.
Integration: generator→SpanState honest backfill; post-hoc reconstruction over a fixture `cells.json`.
Fault-injection: hung-endpoint non-blocking + dropped-counter; `redact()` raising ✅.
Contract: join fixture (R1-S7); FR-23/FR-24 negative-req tests; required-attr presence.
All run without a live ContextCore via the `_enabled` graceful-degradation path.

## 4. Traceability (FR → step)

| FR | Step | FR | Step |
|----|------|----|------|
| FR-1/2 | T1.2 | FR-17 | T2.1 |
| FR-3 | T1.1 ✅ | FR-18 | T2.2 |
| FR-4/5 | T1.3 | FR-19 | T0.1 ✅ |
| FR-6 | T5.1 | FR-20/21/22 | T5.1/2/3 |
| FR-7/8 | T4.1 | FR-23/24 | T5.4 contract tests |
| FR-9 | T4.1/T4.3 | FR-25 | T4.2 |
| FR-10 | T4.1 | FR-26 | T1.2 |
| FR-11 | T4.1/T5.4 | FR-27a/b | T0.2/T0.3 ✅ |
| FR-12/13/14 | T3.1/2/3 | FR-28 | T0.2 ✅ |
| FR-15/16 | T0.3 ✅/T3.1 | Section G | T5.4 |

## 5. Risks & Rollout
R1 emitter change — additive/defaulted ✅. R2 bridge — backward-compatible, caller-inventory clean ✅.
R3 redaction false-negatives — fail-open + parent FR-45 human backstop. R4 FR-8 divergence — req v0.3.1.
Rollout: T0 ✅ → T1 (ship delivery burndown) → T2/T3 → T4 → T5. Each independently mergeable behind opt-in.

## 6. Out of Scope
No scoring/roster/results-schema changes; no new ContextCore infra; no autonomous self-correction;
ContextCore not required for a run; no multi-project portfolio. Building the FR-38 state machine is
out of scope — T4.1 reads terminal `CellResult`s; the mapping extends additively if FR-38 lands.

---

## Appendix: Iterative Review Log

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation | Date |
|----|------------|--------|-----------------------------|------|
| R1-S1 | FR-23/FR-24 need testable acceptance (negative reqs) | R1 dual (claude-opus-4-8) | Applied: contract tests in **T5.4**; mirrored in req FR-23/FR-24 (R2-F2/F3). | 2026-06-14 |
| R1-S2 | `integrity_fail` not bucketed with model failures | R1 dual | Applied to **T4.1** mapping: `exclusion_reason` label; FR-21 excludes. Pairs w/ R2-F1. | 2026-06-14 |
| R1-S3 | Name async substrate + drain semantics | R1 dual | Applied to **T4.2**: bounded queue + daemon drainer; best-effort drain w/ deadline at run exit. | 2026-06-14 |
| R1-S4 | Persist wall-clock cell timestamps in runner | R1 dual | Applied to **T4.1** (+ req FR-9 SHOULD, R2-F8): `started_at`/`completed_at`→cells.json. | 2026-06-14 |
| R1-S5 | Extend redaction bypass scope; fail-closed evidence | R1 dual | Applied to **T0.1** application sites (req FR-19); fail-closed-evidence variant DEFERRED. | 2026-06-14 |
| R1-S6 | Caller-inventory before bridge rewrite | R1 dual | DONE: no external `emit_question` caller depends on the raise; rewrite safe. | 2026-06-14 |
| R1-S7 | Machine-checkable join fixture | R1 dual | Applied to **T5.4**: Section-G rows as a fixture asserted against emitters. | 2026-06-14 |
| R1-S8 | Resolve OQ-2 before T4.1 | R1 dual | Applied: **OQ-2 RESOLVED** (per-cell flagship, counts large matrix); T4.1 built granularity-aware. Pairs w/ R2-F5. | 2026-06-14 |
| R1-S9 | Pin 6-row mapping forward-frozen | R1 dual | Applied to **T4.1**: additive-only extension; pinned-rows test. Pairs w/ R2-F7. | 2026-06-14 |

### Appendix B: Rejected Suggestions
| ID | Suggestion | Source | Rationale | Date |
|----|------------|--------|-----------|------|
| (none) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-06-14 (dual-document, plan side; recovered verbatim)

| ID | Area | Sev | Suggestion |
|----|------|-----|------------|
| R1-S1 | Validation | high | Add explicit steps + acceptance for FR-23 (reuse) and FR-24 (no SDK-derived velocity/burndown gauge) — §4 mapped both to a non-step. |
| R1-S2 | Data | high | Reconsider `integrity_fail→cancelled` — map→`blocked` or add `exclusion_reason=integrity`; FR-21 dashboard must exclude from model pass/fail. |
| R1-S3 | Architecture | high | Name T4.2's async substrate + end-of-run drain semantics (queue+drainer vs thread pool; drain-vs-drop at exit). |
| R1-S4 | Ops | medium | Capture `cell_started_at`/`cell_completed_at` in runner.py → cells.json so default post-hoc burndown is wall-clock-true (additive, no coupling). |
| R1-S5 | Security | medium | Extend T0.1 bypass list (seed titles/labels, native-status label, error-derived code, aggregate echoes); make evidence-ref fail-closed. |
| R1-S6 | Risks | medium | Grep `emit_question` callers before the rewrite — assert none depend on the AttributeError. |
| R1-S7 | Interfaces | medium | Make the Section-G join contract a machine-checkable fixture, not a manual checklist. |
| R1-S8 | Risks | medium | Resolve OQ-2 (granularity) **before** T4.1 — counts-vs-per-cell changes FR-7's emitted shape. |
| R1-S9 | Validation | low | Pin the 6 as-built rows so the future FR-38 extension is purely additive. |

> Companion requirements round R2-F1..F8 lives in `REQUIREMENTS.md` Appendix C.

## Requirements Coverage Matrix — R1

Every FR maps to a step in §4 (verified). Negative reqs FR-23/FR-24 now have explicit contract-test
steps (T5.4) — closing the R1-S1 gap where they mapped to no testable step. No FR is unmapped; no
step lacks an FR.

---

*Plan v0.2 — reconstructed + post-CRP-R1 dual-doc. T0+T1.1 implemented & committed; T2–T5 specified.
9 S-suggestions applied. Traces all 28 FRs of requirements v0.4.*
