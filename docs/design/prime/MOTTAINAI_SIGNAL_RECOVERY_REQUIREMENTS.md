# Mottainai Signal Recovery — Requirements

**Version:** 1.0.0
**Created:** 2026-03-22
**Pattern:** Mottainai (don't discard artifacts within a run)
**Domain:** Prime Contractor full pipeline — integration engine, spec builder, context resolution, queue
**Companion:** `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md` v2.0 (addresses the 3 original gaps + review step)

---

## Overview

A comprehensive Mottainai audit of the Prime Contractor pipeline found **12 signal-discard violations** beyond the 3 original gaps (disk compliance, repair outcomes, review absence). All follow the same anti-pattern: **Compute → Log → Discard**. Valuable signals are generated, written to logs at WARNING/INFO level, then thrown away — unavailable for postmortem analysis, within-run feedback, or cross-run learning.

This document addresses the 12 newly-identified gaps. The 3 original gaps are covered by `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md`.

### Fix Pattern

Every gap has the same fix:
1. Add a serializable field to the relevant result/metadata structure
2. Persist the signal alongside the existing log call (don't replace the log)
3. Thread through the pipeline to feature metadata and integration history
4. Make queryable by postmortem and accumulator

### Prioritization

| Priority | Criteria | Gaps |
|----------|----------|------|
| **P0** | Blocks postmortem root cause analysis or directly causes misdiagnosis | 3 gaps |
| **P1** | Loses signal that would improve generation quality or context completeness | 3 gaps |
| **P2** | Loses signal useful for trend analysis or pipeline debugging | 6 gaps |

---

## Status Dashboard

| Req ID | Title | Priority | Status | File |
|--------|-------|----------|--------|------|
| REQ-MSR-100 | Persist merge conflict details | P0 | planned | integration_engine.py |
| REQ-MSR-110 | Persist prompt budget section drops | P0 | planned | budget.py |
| REQ-MSR-120 | Persist checkpoint result details | P0 | planned | integration_engine.py |
| REQ-MSR-200 | Persist context resolution field skips | P1 | planned | context_resolution.py |
| REQ-MSR-210 | Preserve seed task metadata through queue | P1 | planned | queue.py |
| REQ-MSR-220 | Persist contract violation diagnostics | P1 | planned | integration_engine.py |
| REQ-MSR-300 | Persist skipped files classification | P2 | planned | integration_engine.py |
| REQ-MSR-310 | Export element registry repair metadata | P2 | planned | integration_engine.py |
| REQ-MSR-320 | Persist semantic check issues (struct) | P2 | planned | integration_engine.py |
| REQ-MSR-330 | Persist language-specific cleanup warnings | P2 | planned | integration_engine.py |
| REQ-MSR-340 | Persist domain validation issues | P2 | planned | prime_contractor.py |
| REQ-MSR-350 | Fix pre-merge repair metadata asymmetry | P2 | planned | integration_engine.py |

---

## P0: Critical Signal Loss

### REQ-MSR-100: Persist Merge Conflict Details
**Status:** planned | **Priority:** P0
**Location:** `integration_engine.py:2474–2478`

**Problem:** `result.conflicts` list is logged at WARNING but never stored. Postmortem cannot analyze conflict patterns, trace to specific code areas, or recommend merge strategy changes.

**Requirements:**
1. After merge, `result.conflicts` MUST be stored in `IntegrationResult.metadata["merge_conflicts"]`.
2. Format: list of `{"file": str, "type": str, "detail": str}` (serializable).
3. If no conflicts, key MUST be absent (not empty list — Mottainai applies to the key itself).
4. Postmortem MUST be able to query conflict frequency per file to detect merge-hostile files.

---

### REQ-MSR-110: Persist Prompt Budget Section Drops
**Status:** planned | **Priority:** P0
**Location:** `implementation_engine/budget.py:254–263`

**Problem:** `enforce_prompt_budget()` logs which P0–P3 sections were removed due to budget overflow, but never persists this decision. Cannot correlate generation failure with "architectural context was dropped."

**Requirements:**
1. `enforce_prompt_budget()` MUST return a `BudgetDecision` dict alongside the truncated prompt.
2. `BudgetDecision`: `{"total_tokens_before": int, "total_tokens_after": int, "sections_dropped": list[str], "sections_truncated": list[str]}`.
3. The caller (spec_builder or drafter) MUST store this in the generation context metadata.
4. Postmortem MUST be able to correlate "section X dropped" with review scores to detect prompt-quality causation.

**Design Note:** This is a return-type change. `enforce_prompt_budget()` currently returns `str`. It should return `tuple[str, dict]` or a dataclass. All call sites (2–3) must be updated.

---

### REQ-MSR-120: Persist Checkpoint Result Details
**Status:** planned | **Priority:** P0
**Location:** `integration_engine.py:2554–2612`

**Problem:** Full `CheckpointResult` objects are returned in `IntegrationResult.checkpoint_results` but never stored in `integration_history`. Postmortem sees only aggregate pass/fail, losing per-check error messages and diagnostic details.

**Requirements:**
1. `IntegrationResult.checkpoint_results` MUST be serialized and stored in `integration_history` per feature.
2. Serialization: `{"check_name": str, "passed": bool, "message": str, "diagnostics": list[str]}` per check.
3. Large diagnostic payloads MUST be truncated to 500 chars per check (prevent metadata bloat).
4. Postmortem MUST be able to query "which checks fail most often" across features.

---

## P1: Quality-Impacting Signal Loss

### REQ-MSR-200: Persist Context Resolution Field Skips
**Status:** planned | **Priority:** P1
**Location:** `context_resolution.py:1189–1220`

**Problem:** Fields skipped due to sanitization violations (path traversal, injection attempts, length overflow) are logged but not stored. Cannot explain why generation context was incomplete.

**Requirements:**
1. Context resolution MUST return a `resolution_metadata` dict alongside the resolved context.
2. `resolution_metadata["skipped_fields"]`: list of `{"field": str, "reason": str}` (e.g., `{"field": "arch_context", "reason": "length_overflow:8500>5000"}`).
3. Thread to generation context metadata for postmortem and accumulator consumption.
4. The accumulator (from Review Feedback Loop) SHOULD track field skip frequency to detect systematic context incompleteness.

---

### REQ-MSR-210: Preserve Seed Task Metadata Through Queue
**Status:** planned | **Priority:** P1
**Location:** `queue.py:299–328`

**Problem:** `SeedTask` fields (`priority`, `effort_estimate`, `related_tasks`, `acceptance_criteria`, `owner`, `labels`, `created_at`) are never bridged to `FeatureSpec`. Rich upstream context from plan ingestion is lost at the queue boundary.

**Requirements:**
1. `add_features_from_seed()` MUST forward ALL non-core SeedTask fields into `FeatureSpec.metadata["seed_metadata"]`.
2. Core fields (id, name, description, target_files, domain, dependencies) are already mapped — no change needed.
3. The preserved metadata MUST include at minimum: `priority`, `effort_estimate`, `acceptance_criteria`, `labels`.
4. Postmortem MUST be able to correlate `priority` and `effort_estimate` with actual generation quality and cost.
5. This advances seed unification (REQ-RFL-340) by preserving the full seed through the Prime pipeline.

---

### REQ-MSR-220: Persist Contract Violation Diagnostics
**Status:** planned | **Priority:** P1
**Location:** `integration_engine.py:1805–1820`

**Problem:** Full violation list from `validate_against_manifest()` is computed but only the count is logged. Violations are not persisted; only success/failure of repair is tracked.

**Requirements:**
1. Contract violations MUST be stored in `IntegrationResult.metadata["contract_violations"]`.
2. Format: list of `{"expected": str, "actual": str, "severity": str, "repaired": bool}`.
3. Cap at 20 violations per integration (prevent metadata bloat on catastrophic failures).
4. Postmortem MUST be able to query violation types to detect systematic contract drift.

---

## P2: Trend & Debugging Signal Loss

### REQ-MSR-300: Persist Skipped Files Classification
**Status:** planned | **Priority:** P2
**Location:** `integration_engine.py:2163–2167, 2319–2425`

**Problem:** Skipped files are accumulated in `IntegrationResult.skipped_files` (with reason classification) but never stored in `integration_history`.

**Requirements:**
1. `integration_history[feature_id]["skipped_files"]` MUST contain the skipped files list.
2. Format: list of `{"file": str, "reason": str}` (already this format in `IntegrationResult`).
3. Postmortem SHOULD analyze skip reason distribution (e.g., "60% of skips are binary files" → improve file filter).

---

### REQ-MSR-310: Export Element Registry Repair Metadata
**Status:** planned | **Priority:** P2
**Location:** `integration_engine.py:881–889, 1027–1034, 1868–1875`

**Problem:** Element-level repair tracking is stored in the integration engine's internal registry but never exported to feature metadata. Cannot correlate element types to repair patterns.

**Requirements:**
1. After integration completes, export element registry snapshot to `IntegrationResult.metadata["element_repair_summary"]`.
2. Format: `{"total_elements": int, "repaired": int, "repair_by_type": dict[str, int]}`.
3. Keep summary-level only (not full element details — too large).

---

### REQ-MSR-320: Persist Semantic Check Issues (Structured)
**Status:** planned | **Priority:** P2

**Note:** This overlaps with REQ-RFL-100 from the Review Feedback Loop requirements. REQ-RFL-100 persists `DiskComplianceResult` (which includes semantic issues). If REQ-RFL-100 is implemented first, this requirement is **auto-satisfied**. Kept here for completeness and to ensure the Mottainai audit is comprehensive.

---

### REQ-MSR-330: Persist Language-Specific Cleanup Warnings
**Status:** planned | **Priority:** P2
**Location:** `integration_engine.py:2028–2046, 2519–2528`

**Problem:** Language-specific warnings (Go formatting issues, Node.js CommonJS/ESM mismatches, etc.) are accumulated then discarded.

**Requirements:**
1. Language-specific warnings MUST be stored in `IntegrationResult.metadata["language_warnings"]`.
2. Format: list of `{"language": str, "category": str, "message": str}`.
3. Postmortem SHOULD correlate language-specific warnings with generation quality.

---

### REQ-MSR-340: Persist Domain Validation Issues
**Status:** planned | **Priority:** P2
**Location:** `prime_contractor.py:4316–4343`

**Problem:** Domain validation issues (from preflight/domain checklist) are logged but not stored in feature history.

**Requirements:**
1. Domain validation results MUST be stored in `feature.metadata["domain_validation"]`.
2. Format: `{"passed": bool, "issues": list[str], "domain": str}`.
3. Postmortem SHOULD correlate domain validation failures with downstream integration issues.

---

### REQ-MSR-350: Fix Pre-Merge Repair Metadata Asymmetry
**Status:** planned | **Priority:** P2
**Location:** `integration_engine.py:831–898`

**Problem:** Post-merge repair populates `result_obj.metadata` with repair details, but pre-merge repair does not — creating an asymmetry where pre-merge repair steps are invisible.

**Requirements:**
1. Pre-merge repair MUST populate `result_obj.metadata` with the same structure as post-merge repair.
2. Use sub-keys `"repair_pre_merge"` and `"repair_post_merge"` to distinguish phases.
3. This aligns with REQ-RFL-105 which condenses repair summaries — ensure both phases are captured.

---

## Relationship to Review Feedback Loop

These requirements are complementary to `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md`:

| This Doc (MSR) | Review Feedback Loop (RFL) | Relationship |
|---|---|---|
| REQ-MSR-100 (merge conflicts) | REQ-RFL-200 (accumulator) | Accumulator SHOULD track conflict frequency |
| REQ-MSR-110 (budget drops) | REQ-RFL-240 (spec hints) | Budget drop patterns SHOULD inform spec emphasis |
| REQ-MSR-120 (checkpoint details) | REQ-RFL-200 (accumulator) | Checkpoint failure types feed pattern detection |
| REQ-MSR-200 (field skips) | REQ-RFL-250 (spec injection) | "Context field X was unavailable" is a useful spec hint |
| REQ-MSR-210 (seed metadata) | REQ-RFL-340 (seed unification) | Preserving seed metadata is a prerequisite for unification |
| REQ-MSR-220 (contract violations) | REQ-RFL-225 (corrective hint) | Violation types improve re-draft corrective hints |
| REQ-MSR-320 (semantic issues) | REQ-RFL-100 (disk compliance) | Overlapping — RFL-100 satisfies MSR-320 |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial requirements from Mottainai audit |
