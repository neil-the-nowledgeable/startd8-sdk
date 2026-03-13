# Kaizen for Seed Utilization — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-09
> **Scope:** Systematic continuous improvement of how seeds produced by Plan Ingestion are consumed and utilized by the Prime Contractor — the handoff boundary between the two systems
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md)
> **Upstream:** [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) (REQ-KPI-6xx)
> **Downstream:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) (REQ-KZ-1xx)
> **Implementation Home:** `~/Documents/dev/startd8-sdk/` (SDK) + `~/Documents/dev/cap-dev-pipe/` (pipeline)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Seed Consumption Observability (REQ-KSU-1xx)](#3-layer-1--seed-consumption-observability-req-ksu-1xx)
4. [Layer 2 — Seed-to-Outcome Attribution (REQ-KSU-2xx)](#4-layer-2--seed-to-outcome-attribution-req-ksu-2xx)
5. [Layer 3 — Seed Fitness Scoring (REQ-KSU-3xx)](#5-layer-3--seed-fitness-scoring-req-ksu-3xx)
6. [Layer 4 — Cross-Run Seed Effectiveness (REQ-KSU-4xx)](#6-layer-4--cross-run-seed-effectiveness-req-ksu-4xx)
7. [Layer 5 — Upstream Feedback Loop (REQ-KSU-5xx)](#7-layer-5--upstream-feedback-loop-req-ksu-5xx)
8. [Existing Capabilities Leveraged](#8-existing-capabilities-leveraged)
9. [Traceability Matrix](#9-traceability-matrix)
10. [Verification Strategy](#10-verification-strategy)
11. [Cross-References](#11-cross-references)

---

## 1. Overview

### 1.1 Vision

Plan Ingestion produces seeds. Prime Contractor consumes them. Today these two systems are connected by a file on disk — the context seed JSON — but there is no systematic way to answer:

- **Which seed fields actually influenced code generation quality?**
- **Which seed deficiencies caused downstream failures?**
- **Is Plan Ingestion producing what Prime Contractor actually needs?**

The Plan Ingestion Kaizen (REQ-KPI-6xx) defines a `_ingestion_quality` metadata block that travels with the seed. The Prime Contractor Kaizen (REQ-KZ-1xx) defines post-mortem analysis of generation outcomes. But neither document owns the *bridge* — the causal relationship between seed quality and generation quality.

This document closes that gap. Under Kaizen, every seed consumption becomes a learning opportunity: which fields were used, which were missing, which correlated with success or failure.

### 1.2 The Seed Handoff Boundary

```
Plan Ingestion                    Seed File                     Prime Contractor
┌─────────────┐              ┌─────────────────┐              ┌──────────────────┐
│ PARSE       │              │ context-seed.json│              │ Task Queue       │
│ ASSESS      │──── EMIT ───→│                  │──── LOAD ───→│ Spec Builder     │
│ TRANSFORM   │              │ tasks[]          │              │ Draft Builder    │
│ REFINE      │              │ _ingestion_quality│             │ Code Generation  │
│ EMIT        │              │ config{}         │              │ Post-Mortem      │
└─────────────┘              └─────────────────┘              └──────────────────┘
                                     ↑                                  │
                                     │         Feedback                 │
                                     └──────────────────────────────────┘
                                        (this document)
```

**Key insight:** The seed is the *contract* between the two systems, but today neither side measures whether the contract is well-formed for the consumer's needs. Plan Ingestion measures seed *completeness* (did we fill the fields?). Prime Contractor measures *outcome* (did the code pass?). Nobody measures *fitness* (did the seed contain what was needed to succeed?).

### 1.3 Seed Field Consumption Map (Empirical)

Source: `spec_builder.py`, `drafter.py`, `queue.py`, `classifier.py` (as of 2026-03-09)

The following seed fields are actively consumed by the Prime Contractor. This is the empirical ground truth for what Plan Ingestion *should* produce — not what its schema *allows*.

| Seed Field | Consumer | Impact | Notes |
|-----------|----------|--------|-------|
| `task_description` | `spec_builder.build_spec_prompt()` | **Critical** — primary LLM instruction | Thin descriptions (<100 chars) reliably produce poor code |
| `target_files` | `spec_builder`, `drafter` (6+ sites) | **Critical** — determines output file paths, multi-file format, skeleton matching | Multi-file tasks change draft output format entirely |
| `element_tiers` | `spec_builder` (pre-assembly preamble), `drafter` (skeleton fill mode) | **High** — drives draft mode selection and scope narrowing | Absence falls back to full-file generation (W-3 waste); presence enables `skeleton_fill` mode |
| `skeleton_sources` | `drafter._detect_skeleton_fill()`, `build_skeleton_section()` | **High** — provides pre-assembled code skeleton for fill-in | Both `skeleton_sources` AND `element_tiers` required for `skeleton_fill` activation |
| `runtime_dependencies` | `spec_builder.build_spec_available_imports()` | **Medium** — available imports section | Empty = no import guidance = LLM guesses |
| `existing_files` | `drafter._resolve_draft_mode()` | **High** — switches between create/edit/search_replace modes | Presence + line count determines edit vs search_replace (threshold: `SEARCH_REPLACE_LINE_THRESHOLD`) |
| `dependencies` | `queue.get_next_feature()` | **Critical** — task ordering in execution queue | Circular deps deadlock the queue (run-018 incident: 17/17 tasks blocked) |
| `output_format` | `spec_builder.build_spec_context_section()` | **Low** — output formatting hints | Rarely populated; fallback to auto-detection |
| `negative_scope` | Embedded in `task_description` | **Medium** — exclusions to reduce hallucination | Not a separate field read — must be woven into description text |
| `api_signatures` | Embedded in `task_description` | **Medium** — interface contracts | Same as negative_scope — consumed as prose, not structured data |

**Draft mode decision tree** (from `drafter.py`):
```
Has skeleton_sources + element_tiers + target match?
  └─ YES → skeleton_fill
  └─ NO  → Has existing_files?
              └─ YES → file > SEARCH_REPLACE_LINE_THRESHOLD lines?
              │          └─ YES → search_replace
              │          └─ NO  → edit
              └─ NO  → create
```

**Implication for Plan Ingestion:** The most impactful seed improvements are:
1. **Populate `element_tiers` + `skeleton_sources`** — unlocks skeleton_fill mode (highest quality, lowest waste)
2. **Ensure acyclic `dependencies`** — prevents queue deadlock
3. **Dense `task_description`** with code examples, requirements refs, and negative scope — directly consumed as the LLM's primary instruction

### 1.4 Gaps to Close

| Gap | Problem | Impact |
|-----|---------|--------|
| KSU-1 | No visibility into which seed fields Prime Contractor actually reads | Cannot distinguish unused fields from critical ones |
| KSU-2 | No causal link between seed characteristics and per-task outcomes | "Bad seed → bad code" is a hypothesis, not a measurement |
| KSU-3 | No fitness score for how well a seed serves the consumer | Seed quality score (REQ-KPI-302) measures completeness, not utility |
| KSU-4 | No cross-run view of seed effectiveness trends | Cannot answer "are seeds getting more useful?" |
| KSU-5 | No feedback from Prime Contractor outcomes back to Plan Ingestion | Plan Ingestion has no signal about which seed improvements would help most |

### 1.5 Success Criteria

1. Prime Contractor logs which seed fields it reads per task (KSU-1 closed)
2. Per-task outcomes are attributable to seed characteristics (KSU-2 closed)
3. A seed fitness score (distinct from seed quality) measures consumer utility (KSU-3 closed)
4. Seed fitness trends are trackable across runs (KSU-4 closed)
5. Prime Contractor outcomes generate actionable feedback for Plan Ingestion (KSU-5 closed)

### 1.6 Constraints

- **No new LLM calls** for Kaizen analysis — all checks are deterministic
- **Minimal runtime overhead** — field access tracking must not measurably slow generation
- **Backward compatible** — seed format changes are additive only (new metadata fields)
- **Builds on existing Kaizen** — consumes `_ingestion_quality` (REQ-KPI-600) and post-mortem output (REQ-KZ-100)
- **Does not own either endpoint** — this document defines the bridge contract, not the internals of either system

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status | Closes |
|--------|-------------|-----------|--------|--------|
| **Layer 1 — Seed Consumption Observability** | | | | |
| REQ-KSU-100 | Seed field access logging during Prime Contractor execution | startd8-sdk | PLANNED | KSU-1 |
| REQ-KSU-101 | Unused/missing field report per run | startd8-sdk | PLANNED | KSU-1 |
| **Layer 2 — Seed-to-Outcome Attribution** | | | | |
| REQ-KSU-200 | Per-task seed-vs-outcome record | startd8-sdk | PLANNED | KSU-2 |
| REQ-KSU-201 | Failure-to-seed-gap correlation | startd8-sdk | PLANNED | KSU-2 |
| **Layer 3 — Seed Fitness Scoring** | | | | |
| REQ-KSU-300 | Consumer-side fitness score | startd8-sdk | PLANNED | KSU-3 |
| REQ-KSU-301 | Fitness vs quality comparison | startd8-sdk | PLANNED | KSU-3 |
| **Layer 4 — Cross-Run Seed Effectiveness** | | | | |
| REQ-KSU-400 | Seed effectiveness trend aggregation | cap-dev-pipe | PLANNED | KSU-4 |
| REQ-KSU-401 | Field-level effectiveness ranking | cap-dev-pipe | PLANNED | KSU-4 |
| **Layer 5 — Upstream Feedback Loop** | | | | |
| REQ-KSU-500 | Seed improvement recommendations | startd8-sdk | PLANNED | KSU-5 |
| REQ-KSU-501 | Feedback artifact for Plan Ingestion Kaizen config | cap-dev-pipe | PLANNED | KSU-5 |

---

## 3. Layer 1 — Seed Consumption Observability (REQ-KSU-1xx)

**Closes:** Gap KSU-1 (no visibility into which seed fields Prime Contractor reads)

**Intent:** Instrument the Prime Contractor's seed consumption path to record which fields are accessed, which are missing-but-expected, and which are present-but-ignored. This produces the ground truth for all downstream layers.

**Detail level:** Requirements in this layer will specify the instrumentation points, field access log format, and the per-run unused/missing field report. *(Details deferred — high-level structure only in v0.1.0.)*

---

## 4. Layer 2 — Seed-to-Outcome Attribution (REQ-KSU-2xx)

**Closes:** Gap KSU-2 (no causal link between seed characteristics and per-task outcomes)

**Intent:** For each task the Prime Contractor processes, record the seed characteristics alongside the outcome (success/failure, code quality score, repair needed, etc.). This creates a per-task record that enables statistical correlation: "tasks with thin descriptions fail 3x more often."

**Detail level:** Requirements in this layer will specify the attribution record schema, how it joins with post-mortem data (REQ-KZ-100), and the correlation analysis method. *(Details deferred.)*

---

## 5. Layer 3 — Seed Fitness Scoring (REQ-KSU-3xx)

**Closes:** Gap KSU-3 (no fitness score for consumer utility)

**Intent:** Define a *fitness* score that is distinct from the Plan Ingestion *quality* score (REQ-KPI-302). Quality measures "did we fill the fields?" Fitness measures "did the fields contain what the consumer needed to succeed?" Fitness is computed *after* Prime Contractor execution, using outcome data to weight field importance.

**Prior art — recalibrated seed quality score** (`b601aed`): The original 4-component quality formula (description presence 0.3, target presence 0.3, schema 0.2, field coverage 0.2) gave 1.0 to seeds with single-line descriptions that reliably produced poor code. The recalibrated 6-component formula adds:

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| Description presence | 0.20 | Has any description at all |
| Target file presence | 0.20 | Has target_files |
| Schema validity | 0.15 | Passes JSON schema check |
| Field coverage | 0.15 | Optional enrichment fields populated |
| **Description depth** | **0.15** | `min(chars / 500, 1.0)` — penalizes shallow descriptions |
| **Description richness** | **0.15** | Has code examples OR requirements references |

Plus `compute_density_warnings()` generates actionable warnings: shallow descriptions (<500 chars), missing code examples, missing requirements references.

**This recalibrated score is a stepping stone toward fitness scoring.** It still measures producer-side characteristics (what the seed *contains*), not consumer-side utility (whether those characteristics *helped*). The fitness score (REQ-KSU-300) will close the loop by weighting components based on observed outcome correlation — e.g., if `has_code_examples` correlates 3x more strongly with generation success than `has_requirements_refs`, the fitness formula should reflect that.

**Also note:** `TaskDensity.has_negative_scope` was added in the same commit, recognizing that negative scope (explicit exclusions) reduces LLM hallucination. But `negative_scope` is consumed as embedded prose in `task_description`, not as a structured field the consumer reads separately (see Section 1.3 consumption map). The fitness score should measure whether negative scope *in the description* correlates with fewer repair cycles downstream.

**Detail level:** Requirements in this layer will specify the fitness scoring formula, its relationship to the recalibrated quality score, and how field weights are derived from outcome data. *(Details deferred.)*

---

## 6. Layer 4 — Cross-Run Seed Effectiveness (REQ-KSU-4xx)

**Closes:** Gap KSU-4 (no cross-run seed effectiveness trends)

**Intent:** Aggregate seed fitness scores and field-level effectiveness across runs to answer: "are seeds getting more useful over time?" and "which fields have the highest impact on outcomes?" This builds on the cross-run infrastructure from both companion Kaizen docs (REQ-KPI-400, REQ-KZ-400).

**Detail level:** Requirements in this layer will specify the aggregation script, trend output format, and field-level effectiveness ranking. *(Details deferred.)*

---

## 7. Layer 5 — Upstream Feedback Loop (REQ-KSU-5xx)

**Closes:** Gap KSU-5 (no feedback from Prime outcomes to Plan Ingestion)

**Intent:** Transform seed effectiveness analysis into actionable recommendations for Plan Ingestion. This closes the full Kaizen cycle: Plan Ingestion → Seed → Prime Contractor → Outcome Analysis → Feedback → Better Plan Ingestion. The feedback takes the form of a structured artifact that the Plan Ingestion Kaizen config (REQ-KPI-502) can consume.

**Detail level:** Requirements in this layer will specify the feedback artifact format, recommendation categories (field enrichment, prompt adjustment, threshold tuning), and the injection mechanism. *(Details deferred.)*

---

## 8. Existing Capabilities Leveraged

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| `_ingestion_quality` metadata | REQ-KPI-600 (Plan Ingestion Kaizen) | Input quality signal consumed at handoff |
| `seed_quality_score` | REQ-KPI-302 (Plan Ingestion Kaizen) | Baseline quality to compare against fitness |
| Post-mortem reports | REQ-KZ-100 (Prime Kaizen) | Outcome data for attribution |
| Per-task metrics | `PrimeContractorWorkflow` | Success/failure, cost, time per task |
| Cross-run trend scripts | REQ-KPI-400, REQ-KZ-400 | Pattern for trend aggregation |
| Kaizen config injection | REQ-KPI-502, REQ-KZ-502 | Mechanism for feedback delivery |
| `spec_builder.py` | `implementation_engine/` | Primary seed consumption point (reads task descriptions, context, targets) |
| `drafter.py` | `implementation_engine/` | Secondary seed consumption point (reads implementation hints) |
| `queue.py` | `contractors/` | Task ordering derived from seed dependency graph |
| Complexity classifier | `complexity/classifier.py` | Tier assignment uses seed signals |
| Recalibrated seed quality score | `plan_ingestion_diagnostics.py` (`b601aed`) | 6-component formula with depth + richness — stepping stone toward fitness scoring |
| `TaskDensity` dataclass | `plan_ingestion_diagnostics.py` | Per-task density metrics (chars, lines, code examples, req refs, negative scope) |
| `compute_density_warnings()` | `plan_ingestion_diagnostics.py` | Actionable warnings for shallow descriptions — feed-forward signal |

---

## 9. Traceability Matrix

| Gap | Requirements | Kaizen Principle Rule |
|-----|-------------|---------------------|
| KSU-1: No field access visibility | REQ-KSU-100, 101 | Rule 1 (preserve all outputs) |
| KSU-2: No seed-outcome attribution | REQ-KSU-200, 201 | Rule 3 (measure before and after) |
| KSU-3: No fitness score | REQ-KSU-300, 301 | Rule 3 (measure) — consumer-side complement to producer-side quality |
| KSU-4: No effectiveness trends | REQ-KSU-400, 401 | Rule 6 (automate analysis) |
| KSU-5: No upstream feedback | REQ-KSU-500, 501 | Rule 5 (feed forward) — completes the full cycle |

---

## 10. Verification Strategy

### Standalone Verification

1. **Field access log:** Run Prime Contractor on a known seed; verify field access log records all expected reads
2. **Attribution record:** Verify per-task records contain both seed characteristics and outcome data
3. **Fitness score:** Run on seeds of known quality; verify fitness diverges from quality score when outcomes differ
4. **Missing field report:** Use a seed with deliberately empty fields; verify the report identifies them

### Pipeline Verification

5. **End-to-end cycle:** Run Plan Ingestion → Prime Contractor → Feedback generation; verify feedback artifact is well-formed
6. **Feedback consumption:** Inject feedback into Plan Ingestion Kaizen config; verify next run's prompts/thresholds change
7. **Trend accuracy:** Run 3+ cycles; verify seed effectiveness trends reflect actual outcome improvements

---

## 11. Run Analysis — online-boutique run-020 (2026-03-09)

### 11.1 Run Summary

| Metric | Value | Assessment |
|--------|-------|------------|
| Seed quality score | 0.787 | Below target — depth and richness components scoring low |
| Route | prime | Borderline: composite=40, threshold=40, margin=**0** |
| Tasks | 17 | Same count as run-018 (post-cycle-fix) |
| Cost | $0.39 | 3 LLM calls: PARSE $0.20, TRANSFORM $0.18, ASSESS $0.01 |
| Time | 300s | PARSE 110s (37%), TRANSFORM 180s (60%), ASSESS 9s (3%) |
| Pre-assembly | 0/38 elements pre-filled | 38 registry misses, 0 hits, 0 template fills |

### 11.2 Findings

#### F-1: Route margin = 0 (CRITICAL)

Composite score 40 with threshold 40. Dimension spread 27 confirms conflicting signals — the LLM dimensions are pulling in opposite directions. Any minor plan edit could flip the route. This is the REQ-KPI-301 scenario: `route_margin < 10` should trigger a warning, and here the margin is literally zero.

**Consumer impact:** Prime Contractor proceeds, but the task set may be better suited to Artisan. If the route is wrong, all downstream generation effort is wasted.

#### F-2: 17/17 descriptions below 500-char depth threshold (HIGH)

Every task description is a single line, averaging 226 chars (range: 106–369). The recalibrated quality formula penalizes this, but the score (0.787) still looks acceptable. From the consumer's perspective this is worse than the score suggests — `task_description` is the **primary LLM instruction** in the spec builder. One-sentence descriptions produce vague specs that the drafter interprets liberally.

| Task | Chars | Has Code | Has Refs | Has Neg Scope |
|------|-------|----------|----------|---------------|
| PI-001 | 184 | - | - | - |
| PI-002 | 161 | - | - | - |
| PI-003 | 271 | - | REQ | - |
| PI-004 | 173 | - | - | - |
| PI-005 | 208 | - | - | - |
| PI-006 | 369 | - | - | - |
| PI-007 | 178 | - | - | - |
| PI-008 | 352 | - | - | - |
| PI-009 | 213 | - | - | - |
| PI-010 | 283 | - | - | - |
| PI-011 | 261 | - | - | - |
| PI-012 | 231 | - | - | - |
| PI-013 | 283 | - | - | - |
| PI-014 | 235 | - | REQ | - |
| PI-015 | 221 | - | REQ | - |
| PI-016 | 117 | - | REQ | - |
| PI-017 | 106 | - | REQ | - |

#### F-3: 0/17 tasks have code examples (HIGH)

No fenced code blocks in any description. Code examples are the strongest predictor of correct API usage in generated code. The TRANSFORM prompt does not request them.

#### F-4: 0/17 tasks have negative scope (MEDIUM)

No explicit exclusions. Without negative scope, the LLM has no guardrails against hallucinating extra features or implementing beyond the task boundary. Per the consumption map, negative scope is consumed as embedded prose — it must appear in the description text, not as a separate structured field.

#### F-5: 12/17 tasks missing requirements references (MEDIUM)

Only 5 tasks (PI-003, PI-014–PI-017) contain `REQ-*` patterns. No traceability for 71% of tasks. This limits the review phase's ability to verify the generated code against the original requirements.

#### F-6: 0/38 elements pre-filled — skeleton_fill unavailable (HIGH)

38 elements classified but 0 registry hits. The element registry has no templates for this project's file patterns. Consequence: every task will use `create` mode (full-file generation) rather than `skeleton_fill` mode (targeted fill-in of pre-assembled skeletons). Per the consumption map, this is the difference between the highest-quality/lowest-waste mode and the highest-waste mode.

#### F-7: 7/17 features have API signatures (LOW)

Only 41% of features include `api_signatures`. The spec builder uses these to construct the available imports section. Missing signatures mean the LLM receives no import guidance for 10 tasks.

### 11.3 Prioritized Recommendations

Ordered by expected impact on downstream code generation quality:

| Priority | Finding | Recommendation | Mechanism | Effort |
|----------|---------|---------------|-----------|--------|
| **P0** | F-2: Shallow descriptions | TRANSFORM prompt must request multi-line structured descriptions: implementation steps, function signatures, error handling, edge cases. Target: 500+ chars, 5+ lines per task. | REQ-KPI-500 (prompt suffix) | Low — prompt change only |
| **P1** | F-3: No code examples | TRANSFORM prompt must request fenced code blocks showing key API calls, constructor patterns, or expected output format for each task. | REQ-KPI-500 (prompt suffix) | Low — prompt change only |
| **P2** | F-1: Route margin = 0 | Add `complexity_threshold_override: 45` to kaizen config for this plan. Alternatively, investigate whether the dimension spread (27) indicates the plan genuinely straddles the boundary and should be split. | REQ-KPI-501 (threshold tuning) | Low — config change |
| **P3** | F-6: No pre-fill | Populate element registry with templates for online-boutique file patterns (Python services, Dockerfiles, YAML configs). This is a one-time investment that unlocks skeleton_fill for all future runs. | Element registry population (outside Kaizen scope) | Medium — registry work |
| **P4** | F-4: No negative scope | TRANSFORM prompt must request "What this task should NOT do" as a mandatory section per task. | REQ-KPI-500 (prompt suffix) | Low — prompt change only |
| **P5** | F-5: Missing req refs | TRANSFORM prompt should inject the requirements document's `REQ-*` identifiers into task descriptions where applicable. May require passing the requirements doc as TRANSFORM context. | REQ-KPI-500 (prompt suffix) + possible context expansion | Medium — may need pipeline change |
| **P6** | F-7: Missing API signatures | PARSE prompt should more aggressively extract function/method signatures from the plan text. Lower priority because signatures are partially redundant with code examples (P1). | REQ-KPI-500 (prompt suffix) | Low — prompt change only |

### 11.4 Score Impact Estimate

If P0–P1 are implemented (deeper descriptions + code examples), the recalibrated quality score would shift:

| Component | Current | Projected | Delta |
|-----------|---------|-----------|-------|
| Description depth (0.15) | ~0.45 × 0.15 = 0.068 | ~1.0 × 0.15 = 0.15 | +0.082 |
| Description richness (0.15) | ~0.29 × 0.15 = 0.044 | ~0.80 × 0.15 = 0.12 | +0.076 |
| **Projected score** | **0.787** | **~0.945** | **+0.158** |

More importantly, the *fitness* score (once implemented) should show a larger improvement because deeper descriptions directly feed the spec builder — the most critical consumption point.

---

## 12. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | Governing design principle |
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Upstream: produces seeds with quality metadata (REQ-KPI-6xx) |
| [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) | Downstream: post-mortem and metrics for outcome data (REQ-KZ-1xx) |
| [MOTTAINAI_DESIGN_PRINCIPLE.md](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Related: don't waste artifacts within a run |
| `implementation_engine/spec_builder.py` | Primary seed consumption point |
| `implementation_engine/drafter.py` | Secondary seed consumption point |
| `contractors/queue.py` | Dependency graph consumption |
| `complexity/classifier.py` | Tier classification from seed signals |
| SDK Lessons: Leg 13 #33 | Requirements layer gap — data injection ≠ prompt consumption |
| SDK Lessons: Leg 13 #40 | 12-point pipeline field threading — silent data loss at wiring gaps |
