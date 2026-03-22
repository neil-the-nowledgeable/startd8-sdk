# Prime Contractor Pipeline Audit — Findings

**Date:** 2026-03-22
**Auditor:** human:neil + agent:claude-code
**Scope:** Full Prime Contractor pipeline — cap-dev-pipe → plan ingestion → seed → queue → spec → draft → integration → postmortem
**Principles Applied:** Mottainai (don't discard artifacts), Kaizen (cross-phase learning), Warm Up (don't discard context across transitions)

---

## Executive Summary

A systematic audit of the Prime Contractor pipeline identified **15 signal-discard violations** and **3 architectural gaps** that collectively prevent the pipeline from learning within a run, across runs, and upstream. The root cause is a one-way data flow architecture: signals are computed at every stage but flow only forward (to logs and postmortem), never laterally (to the next feature's spec) or backward (to the seed for the next run).

### Key Architectural Finding

**The Prime Contractor has no review phase.** Unlike Artisan (which has `ReviewPhaseHandler` with LLM-powered review, structured issue extraction, score/verdict output), Prime goes directly from integration to "feature complete." This was discovered when attempting to design a feedback loop — the loop had no consumer. However, the Artisan `ReviewPhaseHandler` is nearly standalone and reusable via a ~100-line adapter.

---

## Finding Categories

| Category | Count | Impact |
|----------|-------|--------|
| **A. Signal Discard (Mottainai)** | 15 | Data computed then thrown away — postmortem blind, accumulator starved |
| **B. Missing Feedback Loop** | 3 | No within-run learning, no review step, no quality gate |
| **C. Upstream Signal Gap** | 3 | Quality signals don't flow per-task through seeds or plan ingestion |

---

## A. Signal Discard Violations (Mottainai)

Every violation follows the same anti-pattern: **Compute → Log → Discard**. The data exists — it's just not persisted in a machine-readable, queryable form.

### A1. Disk Compliance Results (P0)
**Location:** `integration_engine.py:_run_semantic_checks()`
**Signal:** 10-layer semantic validation per file — `DiskComplianceResult` with `ast_valid`, `stubs_remaining`, `import_completeness`, `contract_compliance`, `semantic_issues[]`
**Current:** Logged as `logger.warning()`, discarded.
**Impact:** Postmortem must re-run validation from disk (expensive, may see different state). Accumulator has no semantic pattern data. Cannot correlate semantic issue categories with generation model or task type.

### A2. Repair Outcomes (P0)
**Location:** `integration_engine.py:_attempt_pre_merge_repair()`, `_attempt_repair()`
**Signal:** `RepairOutcome` with `repaired_files`, `steps_applied`, `before_valid`→`after_valid` transitions, step effectiveness data
**Current:** Applied to files, then outcome object discarded. Only the repaired code survives.
**Impact:** Cannot answer "what was broken before repair?" Cannot track which repair steps are reliable. Pre-merge and post-merge repair have asymmetric metadata — pre-merge doesn't populate `result_obj.metadata` at all.

### A3. Merge Conflict Details (P0)
**Location:** `integration_engine.py:2474–2478`
**Signal:** `result.conflicts` list — file paths, conflict types, resolution details
**Current:** Count logged at WARNING, details discarded.
**Impact:** Cannot identify merge-hostile files. Cannot trace conflict patterns to code structure.

### A4. Prompt Budget Section Drops (P0)
**Location:** `implementation_engine/budget.py:254–263`
**Signal:** Which P0–P3 sections were removed or truncated due to token budget overflow
**Current:** Logged, discarded. `enforce_prompt_budget()` returns `str` (no metadata).
**Impact:** Cannot correlate "architectural context was dropped" with generation failure. The most insidious gap — the generator produces bad code *because* it didn't see the context, but no one knows the context was dropped.

### A5. Checkpoint Result Details (P0)
**Location:** `integration_engine.py:2554–2612`
**Signal:** Full `CheckpointResult` objects — per-check name, pass/fail, error messages, diagnostics
**Current:** Returned in `IntegrationResult.checkpoint_results` but never stored in `integration_history`.
**Impact:** Postmortem sees only aggregate pass/fail. Cannot determine *which* checks fail most often or extract diagnostic patterns.

### A6. Context Resolution Field Skips (P1)
**Location:** `context_resolution.py:1189–1220`
**Signal:** Fields skipped due to sanitization violations (path traversal, injection, length overflow)
**Current:** Logged, discarded.
**Impact:** Cannot explain why generation context was incomplete. A field silently dropped due to length overflow looks identical to "field not available" — root cause masked.

### A7. Seed Task Metadata Loss at Queue Boundary (P1)
**Location:** `queue.py:299–328`
**Signal:** `SeedTask` fields `priority`, `effort_estimate`, `related_tasks`, `acceptance_criteria`, `owner`, `labels`, `created_at`
**Current:** Never bridged to `FeatureSpec`. Lost when seed crosses the queue boundary.
**Impact:** Cannot correlate task priority or effort estimate with actual generation quality and cost. Blocks seed unification — Prime's `FeatureSpec` is a lossy projection of the rich `SeedTask`.

### A8. Contract Violation Diagnostics (P1)
**Location:** `integration_engine.py:1805–1820`
**Signal:** Full `ContractViolation` list with expected/actual/severity and post-repair status
**Current:** Only count logged. Full violations discarded after repair attempt.
**Impact:** Cannot analyze violation types to detect systematic contract drift. Cannot distinguish "5 violations, all repaired" from "5 violations, none repairable."

### A9. Skipped Files Classification (P2)
**Location:** `integration_engine.py:2163–2167, 2319–2425`
**Signal:** Skipped file list with per-file reason classification
**Current:** Accumulated in `IntegrationResult.skipped_files` but never stored in integration_history.
**Impact:** Cannot analyze skip reason distribution. Cannot detect "most skips are binary files" pattern.

### A10. Element Registry Repair Metadata (P2)
**Location:** `integration_engine.py:881–889, 1027–1034`
**Signal:** Element-level repair tracking — which element types needed repair, which steps were applied
**Current:** Stored in integration engine's internal registry, never exported.
**Impact:** Cannot correlate element types (function vs class vs module) with repair patterns.

### A11. Language-Specific Cleanup Warnings (P2)
**Location:** `integration_engine.py:2028–2046, 2519–2528`
**Signal:** Go formatting issues, Node.js CommonJS/ESM mismatches, Java build warnings
**Current:** Accumulated then discarded.
**Impact:** Cannot correlate language-specific warnings with quality scores. Go code that needs goimports cleanup is indistinguishable from Go code that's clean.

### A12. Domain Validation Issues (P2)
**Location:** `prime_contractor.py:4316–4343`
**Signal:** Domain preflight validation results — which constraints passed/failed
**Current:** Logged, not stored in feature metadata.
**Impact:** Cannot correlate domain validation failures with downstream integration issues.

### A13. Semantic Check Issues (P2)
**Note:** Overlaps with A1 (disk compliance). If A1 is implemented, A13 is auto-satisfied. Listed for audit completeness.

### A14. Pre-Merge Repair Metadata Asymmetry (P2)
**Location:** `integration_engine.py:831–898`
**Signal:** Pre-merge repair steps and outcomes
**Current:** Post-merge repair populates `result_obj.metadata`; pre-merge does not.
**Impact:** Pre-merge repair activity is invisible — only post-merge is tracked.

### A15. Repair Step Effectiveness (P1)
**Location:** `repair/orchestrator.py:_step_effectiveness`
**Signal:** Per-step attempts, modifications, reverts, contributed-to-success counts
**Current:** Tracked in module-level `_step_effectiveness` dict. No public API to query it.
**Impact:** Spec builder cannot adapt emphasis based on repair reliability. Steps that succeed 95% of the time get the same spec emphasis as steps that succeed 5%.

---

## B. Missing Feedback Loops

### B1. No Review Phase in Prime Contractor
**Finding:** The Prime Contractor flow is `queue → spec → draft → integrate → done`. Unlike Artisan (8-phase with REVIEW), Prime has no LLM-powered quality review between integration and completion.

**Consequence:** No structured issue extraction. No score-based quality assessment. No mechanism to explain *why* output is weak — only numeric heuristics (disk quality score) after the fact.

**Opportunity:** The Artisan `ReviewPhaseHandler` is nearly standalone. Its three core methods (`_build_review_prompt()`, `_parse_review_response()`, `_resolve_review_agent()`) have no hard Artisan dependencies beyond expecting a `SeedTask` input (vs Prime's `FeatureSpec`). A ~100-line adapter can bridge the gap.

### B2. No Within-Run Feedback
**Finding:** Features are processed sequentially (`while True: feature = queue.get_next_feature()`), yet feature B's spec is built identically to feature A's — no accumulated learning.

**Consequence:** If feature A triggers 3 phantom import errors and 2 circular dependency issues, feature B's spec is equally likely to produce them. The same patterns repeat across features within a single run.

**Opportunity:** A `RunQualityAccumulator` collecting signals from integration + review feeds pattern-matched hints into subsequent features' specs at P2 priority.

### B3. No Quality Gate With Structured Re-Draft
**Finding:** Prime Contractor has `_check_quality_gate()` (~line 4127) that checks a generator-provided score against `_MIN_QUALITY_SCORE` (60). This is a numeric threshold with no corrective action — it just logs.

**Consequence:** Bad output is accepted and goes to postmortem. The only feedback path is kaizen hints in the *next* run.

**Opportunity:** A quality gate that uses the review verdict (FAIL) + disk quality score (< threshold) as dual condition, then re-drafts with the review's specific issues as a P0 corrective hint. The reviewer says "circular import between logger and server" — that becomes the re-draft instruction.

---

## C. Upstream Signal Gaps

### C1. Kaizen Suggestions Not Distributed Per-Task
**Location:** `seeds/builder.py:232–235`, `prime_postmortem.py:771–834`
**Finding:** `generate_kaizen_suggestions()` produces per-pattern hints with `config_key: "prompt_hints"`. Plan ingestion's `SeedBuilder.set_artifacts()` extracts `refine_suggestions` but stores them in the onboarding appendix — never distributed to individual tasks.

**Consequence:** All features get the same generic kaizen hint. Feature A (a server module) gets "watch for phantom imports" even if the pattern only appeared in client modules.

**Opportunity:** Match kaizen suggestions to tasks by pattern affinity (target files, domain). Feature A gets server-specific hints; Feature B gets client-specific hints.

### C2. No quality_hints Field on SeedTask
**Location:** `seeds/models.py`
**Finding:** `SeedTask` has `prompt_constraints` (from plan/domain) but no field for quality guidance learned from previous runs. Quality signals and structural requirements are mixed in the same list, degrading signal quality.

**Opportunity:** `quality_hints: list[str]` on `SeedTask` — shared by both Prime and Artisan, advancing seed unification.

### C3. No Post-Ingestion Enrichment Step in Cap-Dev-Pipe
**Location:** `.cap-dev-pipe/run-prime-contractor.sh`
**Finding:** The cap-dev-pipe runs plan ingestion → prime contractor with no enrichment step between. Previous run's postmortem data is available as JSON artifacts but not injected into the seed.

**Opportunity:** A post-ingestion enrichment script that takes seed + postmortem → enriched seed with per-task quality hints. Wired into the cap-dev-pipe as `--postmortem <path>`.

---

## Signal Flow Map (Current vs Target)

### Current: One-Way Flow

```
Plan Ingestion → Seed → Queue → Spec → Draft → Integration → Postmortem
                                                     │              │
                                                     ▼              ▼
                                               (logs only)    (next run's
                                                               kaizen hints)
```

**Problems:**
- Integration signals → logs only (A1–A14)
- No review step (B1)
- No within-run learning (B2)
- No quality gate (B3)
- Kaizen hints generic, not per-task (C1)
- No seed-level quality field (C2)
- No enrichment between ingestion and execution (C3)

### Target: Closed Loops

```
                    ┌─────── C3: post-ingestion enrichment ──────┐
                    │                                             │
Plan Ingestion → Seed(C2) → Queue(A7) → Spec ◄─── B2: accumulator
                                           │              │
                                           ▼              │
                                         Draft            │
                                           │              │
                                           ▼              │
                                    Integration ──────────┤
                                    (A1–A6,A8–A14         │
                                     persisted)           │
                                           │              │
                                           ▼              │
                                      Review (B1) ────────┤
                                           │              │
                                           ▼              │
                                    Quality Gate (B3)     │
                                    ├─ PASS → next feat ──┘
                                    └─ FAIL → re-draft
                                              with issues
                                           │
                                           ▼
                                      Postmortem
                                    → kaizen-suggestions.json
                                           │
                                           └──── C1: per-task ──► next run seed
```

---

## Priority Matrix

| Gap | Priority | Risk | LLM Cost | Value |
|-----|----------|------|----------|-------|
| A1 (disk compliance) | P0 | None | 0 | Enables accumulator + review enrichment |
| A2 (repair outcomes) | P0 | None | 0 | Enables repair attribution + calibration |
| A3 (merge conflicts) | P0 | None | 0 | Enables conflict pattern analysis |
| A4 (budget drops) | P0 | Low | 0 | Explains "why was context incomplete?" |
| A5 (checkpoint details) | P0 | None | 0 | Explains "why did validation fail?" |
| A15 (repair effectiveness API) | P1 | None | 0 | Enables spec emphasis calibration |
| A6 (context field skips) | P1 | None | 0 | Explains context incompleteness |
| A7 (seed metadata loss) | P1 | None | 0 | Prerequisite for seed unification |
| A8 (contract violations) | P1 | None | 0 | Enables violation pattern analysis |
| B1 (review step) | P0 | Low | +1/feat | Core: structured issue extraction |
| B2 (accumulator) | P0 | Low | 0 | Core: within-run learning |
| B3 (quality gate) | P0 | Medium | +1/gate | Core: re-draft with specific fixes |
| C1 (per-task kaizen) | P1 | Low | 0 | Per-task vs generic hints |
| C2 (quality_hints field) | P1 | None | 0 | Seed unification |
| C3 (cap-dev-pipe enrichment) | P1 | None | 0 | Closes cross-run loop at pipeline |
| A9–A14 (P2 signals) | P2 | None | 0 | Trend analysis + debugging |

---

## Documents Produced

| Document | Content |
|----------|---------|
| **This file** | Consolidated findings |
| `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md` v2.0 | 24 requirements: review step, quality gate, accumulator, upstream amplification |
| `REVIEW_FEEDBACK_LOOP_PLAN.md` v2.0 | Implementation plan: 3 iterations (I1 plumbing+review, I2 gate+feedback, I3 upstream) |
| `MOTTAINAI_SIGNAL_RECOVERY_REQUIREMENTS.md` v1.0 | 12 requirements: signal-discard fixes |
| `MOTTAINAI_SIGNAL_RECOVERY_PLAN.md` v1.0 | Implementation plan: 3 batches (A integration, B budget+context, C queue+prime) |
| `PRIME_PIPELINE_UNIFIED_PLAN.md` | Unified execution plan (recommended order across all workstreams) |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial findings from full pipeline audit |
