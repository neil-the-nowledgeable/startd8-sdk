# Implementation Plan: Prime-Parity Artisan Quality (Prioritized)

**Version:** 1.0.0  
**Created:** 2026-02-26  
**Status:** Ready for implementation  
**Implements:** `docs/design/artisan/PRIME_PARITY_ARTISAN_QUALITY_REQUIREMENTS.md`  
**Tracking prefix:** `REQ-PAQ`

**Detailed execution checklist (Priority 1):**  
`docs/design/artisan/plans/IMPL_PLAN_PAQ_P1_EXECUTION_CHECKLIST.md`

---

## Prioritization Model

- **Priority 1 (Critical):** Required to stop known quality regressions now.
- **Priority 2 (Must Have):** Required to stabilize, measure, and scale quality parity.
- **Priority 3 (Nice to Have):** Optimization, correlation analytics, and rollout polish.

---

## Priority 1: Critical

### Scope (REQ IDs)

- `REQ-PAQ-100`, `REQ-PAQ-101`
- `REQ-PAQ-200`, `REQ-PAQ-201`
- `REQ-PAQ-300`, `REQ-PAQ-301`
- `REQ-PAQ-400`, `REQ-PAQ-401`
- `REQ-PAQ-500`, `REQ-PAQ-501`

### Why critical

These items directly address the current failure modes: non-deterministic prompt quality, revise-and-return without full re-review, path inconsistency, and missing DESIGN gate enforcement.

### Workstream 1.1: Review Correctness Hardening

**Requirements:** `REQ-PAQ-200`, `REQ-PAQ-201`  
**Primary files:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`

**Tasks:**
1. Ensure all `_revise_design(...)` outcomes are followed by reviewer+arbiter re-review.
2. Ensure final `DesignDocumentResult` verdicts are tied to final returned design text.
3. Remove/guard all early return paths that can return revised design without re-review.

**Exit criteria:**
1. No return path exists without post-revision review evidence.
2. Unit tests cover disagreement/revision branches and final-iteration acceptance rules.

### Workstream 1.2: Canonical Path Enforcement

**Requirements:** `REQ-PAQ-300`, `REQ-PAQ-301`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

**Tasks:**
1. Set dual-review convergence path as production default.
2. Require explicit opt-in for modular/single-pass path.
3. Add equivalent review envelope for variant path (no implicit `agreed=True`).

**Exit criteria:**
1. Default config always routes to canonical path.
2. Variant path cannot bypass review-based acceptance.

### Workstream 1.3: DESIGN Gate Enforcement

**Requirements:** `REQ-PAQ-400`, `REQ-PAQ-401`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_contractor.py`

**Tasks:**
1. Add deterministic DESIGN metrics (`total_failed`, `agreement_rate`).
2. Extend `_check_quality_gate(...)` to include DESIGN under `skip|warn|block`.
3. In `block` mode, fail workflow on DESIGN gate failure.

**Exit criteria:**
1. DESIGN gate failures are enforced identically to TEST/REVIEW policy.
2. Phase output always emits required metrics for gate evaluation.

### Workstream 1.4: Deterministic High-Signal Context Floor

**Requirements:** `REQ-PAQ-100`, `REQ-PAQ-101`, `REQ-PAQ-500`, `REQ-PAQ-501`  
**Primary files:**  
`src/startd8/contractors/prompt_utils.py`  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

**Tasks:**
1. Introduce explicit section-budget registry for design prompt assembly.
2. Guarantee Tier-0 never dropped, with deterministic compression order.
3. Enforce required high-signal field presence (or explicit missing markers).
4. Block or downgrade generation when high-signal floor is not met.

**Exit criteria:**
1. All critical fields are always visible or explicitly marked missing.
2. Prompt-size pressure cannot remove Tier-0 constraints.

### Validation for Priority 1

1. New/updated unit tests for design convergence, routing, and gate behavior.
2. At least one end-to-end run proving DESIGN gate block mode works.
3. Evidence that revised designs are always re-reviewed before acceptance.

---

## Priority 2: Must Have

### Scope (REQ IDs)

- `REQ-PAQ-102`, `REQ-PAQ-202`
- `REQ-PAQ-302`, `REQ-PAQ-402`
- `REQ-PAQ-502`
- `REQ-PAQ-600`, `REQ-PAQ-601`
- `REQ-PAQ-700`

### Why must have

These items make critical fixes operationally reliable and measurable across phases and run types.

### Workstream 2.1: Cross-Phase Budget Consistency

**Requirements:** `REQ-PAQ-102`, `REQ-PAQ-502`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/development.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/prompt_utils.py`

**Tasks:**
1. Standardize budget enforcement and truncation logging across DESIGN/IMPLEMENT/REVIEW.
2. Eliminate duplicate section rendering in prompt builders.
3. Quarantine overflow into deterministic summarized lines.

### Workstream 2.2: Resolution and Routing Governance

**Requirements:** `REQ-PAQ-202`, `REQ-PAQ-302`  
**Primary files:**  
`src/startd8/contractors/artisan_phases/design_documentation.py`  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/forensic_log.py`

**Tasks:**
1. Persist auditable resolution metadata (action, guidance, actor, delta summary).
2. Implement policy-driven route selection by complexity/risk signals.
3. Log route decisions and allow hard force-to-canonical kill switch.

### Workstream 2.3: Contract + Telemetry Baseline

**Requirements:** `REQ-PAQ-402`, `REQ-PAQ-600`, `REQ-PAQ-601`  
**Primary files:**  
`src/startd8/contractors/artisan-pipeline.contract.yaml`  
`src/startd8/contractors/context_schema.py`  
`src/startd8/contractors/forensic_log.py`  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_phases/design_documentation.py`

**Tasks:**
1. Add DESIGN exit quality extractors to contract rules.
2. Emit prompt-composition telemetry (size, sections, truncation, dropped fields).
3. Emit disagreement telemetry (count, categories, confidence gaps, re-review rate).

### Workstream 2.4: Prime-Parity Benchmark Harness

**Requirements:** `REQ-PAQ-700`  
**Primary files:**  
`scripts/` benchmark tooling  
`docs/` benchmark report templates

**Tasks:**
1. Define fixed seed suite (simple/medium/high complexity).
2. Produce repeatable Artisan vs Prime comparison report.
3. Track key deltas: review pass rate, failed-task rate, agreement rate, truncation incidence.

### Validation for Priority 2

1. Contract validator reports DESIGN quality violations consistently.
2. Walkthrough and forensic artifacts include prompt/review telemetry.
3. Benchmark results are reproducible on fixed seed set.

---

## Priority 3: Nice to Have

### Scope (REQ IDs)

- `REQ-PAQ-602`, `REQ-PAQ-603`, `REQ-PAQ-701`

### Why nice to have

These items improve long-term optimization and rollout confidence but are not required to stop immediate quality regressions.

### Workstream 3.1: Path-Quality Correlation Analytics

**Requirements:** `REQ-PAQ-602`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/forensic_log.py`

**Tasks:**
1. Add per-task path tags to all relevant outputs.
2. Add run summary grouped metrics by path type.
3. Enable direct canonical vs variant performance comparison.

### Workstream 3.2: End-to-End Gate Traceability

**Requirements:** `REQ-PAQ-603`  
**Primary files:**  
`src/startd8/contractors/artisan_contractor.py`  
`src/startd8/contractors/forensic_log.py`

**Tasks:**
1. Unify gate IDs and naming across runtime and contract signals.
2. Expose gate decision objects in final workflow summary.

### Workstream 3.3: Rollout Guardrails

**Requirements:** `REQ-PAQ-701`  
**Primary files:**  
`src/startd8/contractors/context_seed_handlers.py`  
`src/startd8/contractors/artisan_contractor.py`

**Tasks:**
1. Finalize feature flags for behavior toggles (re-review, canonical routing, design blocking).
2. Define canary rollout and rollback triggers.
3. Document operational playbook.

### Validation for Priority 3

1. Run reports show path-grouped outcomes and gate traceability.
2. Rollout toggles can be changed without code edits.

---

## Execution Order and Dependencies

1. **Priority 1 first** (hard quality controls): `1.1 -> 1.2 -> 1.3 -> 1.4`
2. **Priority 2 second** (stability + measurement): `2.1 -> 2.2 -> 2.3 -> 2.4`
3. **Priority 3 last** (analytics + rollout polish): `3.1 -> 3.2 -> 3.3`

Dependency notes:

1. `REQ-PAQ-200/201` must complete before benchmarking (`REQ-PAQ-700`), or results are not trustworthy.
2. `REQ-PAQ-400/401` should precede contract-level design gate (`REQ-PAQ-402`) to avoid contract/runtime mismatch.
3. `REQ-PAQ-600/601` should land before `REQ-PAQ-602` so correlation metrics have baseline telemetry.

---

## Delivery Milestones

### Milestone M1 (Critical Quality Lock)

- Complete all Priority 1 requirements.
- Outcome: no unreviewed revised design acceptance, canonical path enforced, DESIGN gate active.

### Milestone M2 (Operational Quality Parity)

- Complete all Priority 2 requirements.
- Outcome: cross-phase consistency, contract-backed DESIGN quality validation, parity benchmark in place.

### Milestone M3 (Optimization and Rollout Confidence)

- Complete all Priority 3 requirements.
- Outcome: path-performance analytics and rollout guardrails fully operational.

---

## Suggested PR Breakdown

1. **PR-A:** `REQ-PAQ-200/201` (re-review correctness).
2. **PR-B:** `REQ-PAQ-300/301` (canonical path + variant envelope).
3. **PR-C:** `REQ-PAQ-400/401` (DESIGN gate metrics and enforcement).
4. **PR-D:** `REQ-PAQ-100/101/500/501` (deterministic context floor).
5. **PR-E:** Priority 2 workstreams.
6. **PR-F:** Priority 3 workstreams.
