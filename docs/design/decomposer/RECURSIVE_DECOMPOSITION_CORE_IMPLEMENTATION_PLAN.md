# Recursive Decomposition Core — Implementation Plan

**Date:** 2026-03-07  
**Status:** DRAFT  
**Source:** [REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md](./REQ-MP-910_RECURSIVE_DECOMPOSITION_CORE.md)  
**Related:** [REQ-MP-9xx_MODERATE_DECOMPOSER.md](../micro-prime/REQ-MP-9xx_MODERATE_DECOMPOSER.md), [SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md](../micro-prime/SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md), [MICRO_PRIME_REQUIREMENTS.md](../micro-prime/MICRO_PRIME_REQUIREMENTS.md)

---

## Overview

This plan introduces a shared decomposition core and a policy‑gated recursion path so MODERATE → SIMPLE and SIMPLE → TRIVIAL decomposition can compose without unbounded recursion, partial writes, or behavior regressions.

---

## Phase 0: Decomposition Core Types (Foundational)

**Goal:** Centralize shared types and utilities used by all decomposition strategies.

### Changes

1. Add `src/startd8/micro_prime/decomposition/core.py` with `DecompositionContext`, `DecompositionNode`, `DecompositionPlanGraph`, and shared `_compute_confidence()` (imported from existing decomposer utilities if already present). Include `file_path` in `DecompositionContext` to support canonical fingerprints.
2. Update `micro_prime/decomposer.py` to accept a `DecompositionContext` input in strategy planning.
3. Keep compatibility with existing `DecompositionPlan` and `SubElement` interfaces from REQ‑MP‑9xx.

### Tests

- `test_decomposition_context_plumbing` verifies strategies receive the same context fields as prior direct parameters.
- `test_decomposition_plan_graph_structure` validates root node ordering and child relationships.

---

## Phase 1: Recursion Policy + Config Wiring

**Goal:** Gate recursion with explicit policy and config defaults.

### Changes

1. Add `RecursionPolicy` (models or core) with defaults and bounds.
2. Add config fields in `MicroPrimeConfig`: `recursion_enabled`, `recursion_max_depth`, `recursion_max_sub_elements_total`, `recursion_max_llm_calls`, `recursion_monotonicity`.
3. Plumb `RecursionPolicy` into `DecompositionContext`.

### Tests

- `test_recursion_config_defaults` confirms defaults preserve current behavior.
- `test_recursion_policy_depth_limit` rejects plans beyond `max_depth`.
- `test_recursion_policy_budget_limit` rejects plans exceeding sub‑element or LLM budgets.
- `test_recursion_monotonicity_strict` rejects same‑tier recursion when `strict_tier_decrease`.

---

## Phase 2: Recursive Execution + Staging

**Goal:** Execute nested plans safely, with no partial writes.

### Changes

1. Add a plan‑graph executor in `micro_prime/engine.py` that renders deterministic/template results first, attempts recursive decomposition when policy allows, and otherwise falls back to `_handle_simple` or escalation.
2. Use scratch skeletons and staged caches for sub‑element generation.
3. Add cycle detection using element fingerprints in the decomposition path. Canonical fingerprint matches engine caching: `f\"{parent_class}:{name}:{file_path}:{tier.value}\"`.
4. Reject recursion with bounded reasons when policy fails.

### Tests

- `test_recursive_decomposition_staging` ensures skeleton and caches are unchanged on failure.
- `test_cycle_detection_rejects` verifies repeated fingerprints are blocked.
- `test_recursion_disabled_blocks` verifies recursion is not attempted when disabled.
- `test_deterministic_sub_elements_do_not_count_llm_budget` enforces budget accounting.

---

## Phase 3: Observability + Reporting

**Goal:** Make recursion traceable and measurable.

### Changes

1. Add counters: `micro_prime.recursion_attempted`, `micro_prime.recursion_succeeded`, `micro_prime.recursion_rejected`.
2. Extend decomposition rejection reason enum with recursion values: `recursion_blocked`, `depth_exceeded`, `budget_exceeded`, `monotonicity_violation`, `cycle_detected`.
3. Include recursion metadata in postmortem entries when applicable (`recursion_depth`, `decomposition_path`).

### Tests

- `test_recursion_metrics_emitted_when_enabled` verifies counters fire only when enabled.
- `test_recursion_rejection_reason_bounded` validates metric labels are bounded.
- `test_postmortem_includes_recursion_metadata` validates schema extension and required fields.

---

## Implementation Order

1. Phase 0 (core types)
2. Phase 1 (policy + config)
3. Phase 2 (execution + staging)
4. Phase 3 (metrics + reporting)

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Architecture**: 1/3 suggestions accepted (R1-S1) — need 2 more
- **Interfaces**: 0/3 suggestions accepted — need 3 more
- **Data**: 1/3 suggestions accepted (R1-S2) — need 2 more
- **Risks**: 0/3 suggestions accepted — need 3 more
- **Validation**: 0/3 suggestions accepted — need 3 more
- **Ops**: 1/3 suggestions accepted (R1-S3) — need 2 more
- **Security**: 0/3 suggestions accepted — need 3 more

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Update related links to the new decomposer document location. | CRP R1 | Updated Related links to `../micro-prime/...`. | 2026-03-07 |
| R1-S2 | Include `file_path` in `DecompositionContext` and align cycle detection with canonical fingerprint format. | CRP R1 | Added in Phase 0 and Phase 2 changes. | 2026-03-07 |
| R1-S3 | Specify recursion metadata fields in postmortem entries and tests. | CRP R1 | Added to Phase 3 changes and test note. | 2026-03-07 |
| R2-S1 | Define the `DecompositionContext` / strategy interface contract explicitly: what fields are required vs optional, what the strategy must return, and what invariants the executor assumes. | CRP R2 | Added interface contract subsection to Phase 0. | 2026-03-07 |
| R2-S2 | Add rollback contract: specify exactly which artifacts are staged (skeleton diff, cache entries), what "rollback" means for each, and that partial sub-element successes are not flushed on parent failure. | CRP R2 | Added rollback specification to Phase 2. | 2026-03-07 |
| R2-S3 | Add a `test_partial_plan_failure_rolls_back_all_staged_caches` test that fails one sub-element mid-plan and asserts no cache entries were written. | CRP R2 | Added to Phase 2 test list. | 2026-03-07 |
| R2-S4 | Specify what happens when `recursion_enabled=False` but a strategy returns a `DecompositionPlanGraph` — clarify whether the graph is silently flattened, an error is raised, or execution falls back. | CRP R2 | Added fallback behaviour note to Phase 1 changes. | 2026-03-07 |
| R2-S5 | Specify LLM call counting rules: which calls count toward `max_llm_calls` (decomposition prompts? repair prompts? escalation calls?), and document this in Phase 1. | CRP R2 | Added LLM budget accounting note to Phase 1 changes. | 2026-03-07 |
| R2-S6 | Add a `test_llm_budget_counts_only_decomposition_calls` test that explicitly exercises the boundary between counted and uncounted LLM calls. | CRP R2 | Added to Phase 2 test list. | 2026-03-07 |
| R2-S7 | Add a `test_recursion_metrics_not_emitted_when_disabled` negative-path test asserting zero metric emissions when `recursion_enabled=False`. | CRP R2 | Added to Phase 3 test list. | 2026-03-07 |
| R2-S8 | Describe the `confidence` field on `DecompositionPlanGraph`: how it is computed for a nested plan (aggregate of child confidences? minimum? explicit formula?). | CRP R2 | Added confidence aggregation note to Phase 0 changes. | 2026-03-07 |
| R2-S9 | Note that `RecursionPolicy` defaults must be validated against `MicroPrimeConfig` field constraints at construction time to prevent invalid states (e.g., `max_depth=0` or `max_llm_calls=0`). | CRP R2 | Added validation note to Phase 1 changes. | 2026-03-07 |
| R2-S10 | Add a `test_invalid_recursion_policy_raises` test covering out-of-range defaults (depth=0, sub-elements=0, llm-calls=0). | CRP R2 | Added to Phase 1 test list. | 2026-03-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|--------------------|---------------------|
| R1-S1 | Architecture | low | Update related links to the new decomposer document location. | Links break after moving files. | Header `Related` section. | Manual link verify. |
| R1-S2 | Data | medium | Include `file_path` in `DecompositionContext` and align cycle detection with the canonical engine fingerprint. | Cycle detection needs a stable, shared fingerprint definition. | Phase 0 change list and Phase 2 change list. | Add a fingerprint format test. |
| R1-S3 | Ops | medium | Specify recursion metadata fields in postmortem entries and ensure tests validate them. | Observability needs depth/path visibility. | Phase 3 changes and tests. | Extend postmortem metadata test to assert fields. |

#### Review Round R2

- **Reviewer**: Gemini 2.5 Pro (antigravity-crp-r2)
- **Date**: 2026-03-07 23:25:00 UTC
- **Scope**: Two-tier priority review — Tier 1: Interfaces, Risks, Validation, Security (0/3); Tier 2: Architecture, Data, Ops (1/3 each)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|--------------------|---------------------|
| R2-S1 | Interfaces | high | Define the `DecompositionContext` / strategy interface contract explicitly: what fields are required vs optional, what the strategy must return, and what invariants the executor assumes. | Without a declared contract, strategies can silently ignore required fields or return incompatible types, causing runtime failures that are hard to trace. | Phase 0 Changes — add an "Interface Contract" subsection. | Add a test asserting a strategy that omits a required field raises a typed error at planning time. |
| R2-S2 | Risks | high | Add a rollback contract: specify exactly which artifacts are staged (skeleton diff, cache entries), define what "rollback" means for each artifact type, and assert that partial sub-element successes are not persisted on parent failure. | The plan says "rollback staged cache and skeleton changes" but leaves the mechanism implicit; a partial write during a crash between sub-elements would produce inconsistent state. | Phase 2 Changes — add a "Staging and Rollback Contract" subsection. | `test_partial_plan_failure_rolls_back_all_staged_caches` — fail one sub-element mid-plan, assert cache and skeleton unchanged. |
| R2-S3 | Validation | high | Add a `test_partial_plan_failure_rolls_back_all_staged_caches` test that fails one sub-element mid-plan and asserts no cache entries were written and skeleton is unchanged. | The existing test only checks staging success; the failure path (partial rollback) is untested. | Phase 2 Tests. | Run test and verify zero cache writes and skeleton identity on partial failure. |
| R2-S4 | Interfaces | medium | Specify the fallback behavior when `recursion_enabled=False` but a strategy produces a `DecompositionPlanGraph` instead of a flat `DecompositionPlan` — is the graph flattened, an error is raised, or execution falls back to `_handle_simple`? | An unspecified contract here creates a silent correctness risk: if recursion is disabled the executor must have a defined response to receiving a nested plan. | Phase 1 Changes — add a "Disabled-recursion graph handling" note. | Add a test asserting the expected behavior (e.g., flat fallback) when recursion is off but a graph is returned. |
| R2-S5 | Risks | medium | Specify LLM call counting rules: which call types count toward `max_llm_calls` (decomposition prompts only, or also repair/escalation calls?), and document this as a numbered list in Phase 1. | Without explicit counting rules, different implementations will produce inconsistent budget enforcement, and the budget limit becomes unreliable. | Phase 1 Changes — add "LLM Budget Accounting" note. | `test_llm_budget_counts_only_decomposition_calls` asserts escalation calls are excluded. |
| R2-S6 | Validation | medium | Add `test_llm_budget_counts_only_decomposition_calls` to explicitly assert that escalation and repair LLM calls do not decrement the decomposition LLM budget. | Budget correctness is critical to preventing runaway recursion; this boundary is untested. | Phase 2 Tests. | Verify counter value after a repair call does not change. |
| R2-S7 | Ops | medium | Add a `test_recursion_metrics_not_emitted_when_disabled` negative-path test asserting zero OTel counter increments when `recursion_enabled=False`. | REQ-MP-914 requires metrics are emitted only when enabled; the positive path is tested but the negative path is not. | Phase 3 Tests. | Assert metric counter value == 0 after a full plan run with recursion disabled. |
| R2-S8 | Data | medium | Document how `confidence` is computed for a `DecompositionPlanGraph`: is it the minimum child confidence, a weighted aggregate, or passed through from the root strategy? | The field exists on the dataclass but the aggregation semantics are unspecified; implementers will make different choices, breaking comparability across plans. | Phase 0 Changes — add a "Confidence Aggregation" note to the plan-graph executor description. | Add a test with a known child confidence distribution and assert the top-level graph confidence matches the documented formula. |
| R2-S9 | Risks | medium | Validate `RecursionPolicy` field constraints at construction time: reject `max_depth=0`, `max_sub_elements_total=0`, and `max_llm_calls=0` with a descriptive error, since these silently block all recursion regardless of the `enabled` flag. | A policy with any limit at zero is effectively broken and would be hard to diagnose because it produces the same output as `enabled=False`. | Phase 1 Changes — add a "Policy Invariant Validation" note. | `test_invalid_recursion_policy_raises` — construct policies with zero limits and assert typed validation errors. |
| R2-S10 | Security | low | Note that `decomposition_path` (list of element fingerprints) must not be logged at verbosity levels accessible to unprivileged users since fingerprints encode file paths and class names that may leak internal source layout. | Fingerprints include `file_path` and class names; leaking these in production logs could expose internal source structure. | Phase 2 Changes and Phase 3 Changes — add a "Fingerprint Log Level" note. | Assert fingerprint logging is at DEBUG level only and does not appear in INFO-level log output. |
