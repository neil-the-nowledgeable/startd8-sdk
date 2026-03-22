# Mottainai Signal Recovery — Implementation Plan

**Version:** 1.0.0
**Created:** 2026-03-22
**Requirements:** `MOTTAINAI_SIGNAL_RECOVERY_REQUIREMENTS.md` v1.0
**Companion:** `REVIEW_FEEDBACK_LOOP_PLAN.md` v2.0

---

## Implementation Strategy

All 12 gaps follow the same fix pattern:
1. Add serializable dict to existing `metadata` field
2. Persist alongside existing log call
3. Zero behavioral change — pure data preservation

**Risk:** Very low. Every change is additive (new metadata keys), non-breaking (existing code doesn't read the new keys), and serializable (all-primitive types).

**Execution:** These can be implemented in parallel with the Review Feedback Loop iterations. The MSR changes make the RFL accumulator and postmortem richer but are not prerequisites.

---

## Batching

| Batch | Reqs | Files | Lines | Risk | Dependencies |
|-------|------|-------|-------|------|-------------|
| **Batch A: Integration Engine** | MSR-100,120,220,300,310,330,350 | integration_engine.py | ~80 | None | None |
| **Batch B: Budget + Context** | MSR-110,200 | budget.py, context_resolution.py | ~50 | Low (return type change in budget.py) | None |
| **Batch C: Queue + Prime** | MSR-210,340 | queue.py, prime_contractor.py | ~30 | None | None |

Batch A is the largest but all changes are independent additions to `result_obj.metadata` — they can be done in a single commit.

---

## Batch A: Integration Engine (7 Gaps)

All changes in `src/startd8/contractors/integration_engine.py`.

### A1: Merge Conflict Details (REQ-MSR-100)

**Location:** After merge operation (~line 2474)

```python
# After existing logger.warning for conflicts:
if result.conflicts:
    result_obj.metadata["merge_conflicts"] = [
        {"file": str(c.file), "type": c.conflict_type, "detail": str(c.detail)[:200]}
        for c in result.conflicts
    ]
```

### A2: Checkpoint Result Details (REQ-MSR-120)

**Location:** After checkpoint validation (~line 2554)

```python
# After collecting checkpoint_results:
if checkpoint_results:
    result_obj.metadata["checkpoint_details"] = [
        {"check_name": cr.check_name,
         "passed": cr.passed,
         "message": str(cr.message or "")[:500],
         "diagnostics": [str(d)[:200] for d in (cr.diagnostics or [])[:5]]}
        for cr in checkpoint_results
    ]
```

### A3: Contract Violation Diagnostics (REQ-MSR-220)

**Location:** After `validate_against_manifest()` (~line 1805)

```python
# After existing count log:
if violations:
    result_obj.metadata["contract_violations"] = [
        {"expected": str(v.expected)[:200], "actual": str(v.actual)[:200],
         "severity": v.severity, "repaired": False}
        for v in violations[:20]  # Cap at 20
    ]
```

After repair, update repaired status:
```python
for entry in result_obj.metadata.get("contract_violations", []):
    if entry["expected"] in repaired_expectations:
        entry["repaired"] = True
```

### A4: Skipped Files Classification (REQ-MSR-300)

**Location:** After skipped file accumulation (~line 2425)

```python
# IntegrationResult.skipped_files is already populated — just ensure it's in metadata
if result_obj.skipped_files:
    result_obj.metadata["skipped_files"] = result_obj.skipped_files
```

**Note:** `skipped_files` may already be on `IntegrationResult` — verify if it's serialized to integration_history. If yes, this is already done.

### A5: Element Registry Repair Metadata (REQ-MSR-310)

**Location:** After integration completes, before return (~line 2698)

```python
# Export element repair summary
if hasattr(self, "_element_registry") and self._element_registry:
    repaired = [e for e in self._element_registry.values() if e.get("repaired")]
    if repaired:
        repair_by_type = {}
        for e in repaired:
            t = e.get("element_type", "unknown")
            repair_by_type[t] = repair_by_type.get(t, 0) + 1
        result_obj.metadata["element_repair_summary"] = {
            "total_elements": len(self._element_registry),
            "repaired": len(repaired),
            "repair_by_type": repair_by_type,
        }
```

### A6: Language-Specific Cleanup Warnings (REQ-MSR-330)

**Location:** After language cleanup (~line 2528)

```python
# After existing warning accumulation:
if language_warnings:
    result_obj.metadata["language_warnings"] = [
        {"language": w.get("language", "unknown"),
         "category": w.get("category", "unknown"),
         "message": str(w.get("message", ""))[:200]}
        for w in language_warnings[:20]  # Cap
    ]
```

### A7: Pre-Merge Repair Metadata Asymmetry (REQ-MSR-350)

**Location:** `_attempt_pre_merge_repair()` (~line 892)

```python
# After pre-merge repair completes — mirror post-merge metadata population:
if outcome and outcome.any_modified:
    result_obj.metadata["repair_pre_merge"] = {
        "total_repairs": len(outcome.repaired_files),
        "steps_applied": list(outcome.steps_applied),
        "any_modified": True,
    }
```

### A8: Tests for Batch A

**New file:** `tests/unit/contractors/test_mottainai_signal_recovery.py`

```
test_merge_conflicts_persisted
test_merge_conflicts_absent_when_clean
test_checkpoint_details_persisted
test_checkpoint_details_truncated
test_contract_violations_persisted
test_contract_violations_capped
test_contract_violations_repair_status
test_skipped_files_persisted
test_element_repair_summary
test_language_warnings_persisted
test_pre_merge_repair_metadata
```

**Estimated:** 11 tests, ~150 lines

---

## Batch B: Budget + Context (2 Gaps)

### B1: Prompt Budget Section Drops (REQ-MSR-110)

**File:** `src/startd8/implementation_engine/budget.py`

**Current:** `enforce_prompt_budget()` returns `str` (truncated prompt).
**Change:** Return `tuple[str, dict]` (prompt, budget_decision).

```python
def enforce_prompt_budget(prompt: str, budget_tokens: int, sections: list[dict]) -> tuple[str, dict]:
    """Enforce token budget on prompt sections.

    Returns:
        Tuple of (truncated_prompt, budget_decision).
        budget_decision: {"tokens_before": int, "tokens_after": int,
                          "sections_dropped": list[str], "sections_truncated": list[str]}
    """
    budget_decision = {
        "tokens_before": estimate_tokens(prompt),
        "sections_dropped": [],
        "sections_truncated": [],
    }

    # ... existing truncation logic, but now also:
    # budget_decision["sections_dropped"].append(section_name)
    # budget_decision["sections_truncated"].append(section_name)

    budget_decision["tokens_after"] = estimate_tokens(result_prompt)
    return result_prompt, budget_decision
```

**Call site updates:**

In `spec_builder.py`:
```python
# Before:
prompt = enforce_prompt_budget(prompt, TOTAL_SPEC_BUDGET_TOKENS, sections)
# After:
prompt, budget_decision = enforce_prompt_budget(prompt, TOTAL_SPEC_BUDGET_TOKENS, sections)
context["_budget_decision"] = budget_decision  # Persist for postmortem
```

In `drafter.py` (if applicable):
```python
prompt, budget_decision = enforce_prompt_budget(prompt, TOTAL_DRAFT_BUDGET_TOKENS, sections)
```

**Risk:** Low. Return type change affects 2–3 call sites. Backward-compatible if callers are updated simultaneously.

### B2: Context Resolution Field Skips (REQ-MSR-200)

**File:** `src/startd8/contractors/context_resolution.py`

After sanitization skip (~line 1220):
```python
# Existing: logger.warning("Skipping field %s: %s", field_name, reason)
# Add:
resolution_metadata.setdefault("skipped_fields", []).append(
    {"field": field_name, "reason": reason}
)
```

Return `resolution_metadata` alongside context:
```python
# If resolve_task_context returns just dict, add metadata as a nested key:
resolved["_resolution_metadata"] = resolution_metadata
```

### B3: Tests for Batch B

```
test_budget_decision_returned
test_budget_sections_dropped_tracked
test_budget_sections_truncated_tracked
test_budget_decision_persisted_in_context
test_context_field_skips_persisted
test_context_field_skips_empty_when_clean
```

**Estimated:** 6 tests, ~100 lines

---

## Batch C: Queue + Prime (2 Gaps)

### C1: Preserve Seed Task Metadata Through Queue (REQ-MSR-210)

**File:** `src/startd8/contractors/queue.py`
**Method:** `add_features_from_seed()` (~line 299)

```python
# After existing field mapping, preserve non-core seed fields:
seed_metadata = {}
for field_name in ("priority", "effort_estimate", "acceptance_criteria", "labels", "created_at"):
    val = getattr(task, field_name, None)
    if val is not None:
        seed_metadata[field_name] = val

if seed_metadata:
    feature.metadata["seed_metadata"] = seed_metadata
```

### C2: Persist Domain Validation Issues (REQ-MSR-340)

**File:** `src/startd8/contractors/prime_contractor.py`
**Location:** After domain validation (~line 4343)

```python
# After existing logger.warning for domain issues:
if domain_issues:
    feature.metadata["domain_validation"] = {
        "passed": len(domain_issues) == 0,
        "issues": [str(i)[:200] for i in domain_issues[:10]],
        "domain": feature.metadata.get("domain", "general"),
    }
```

### C3: Tests for Batch C

```
test_seed_metadata_preserved
test_seed_metadata_priority
test_seed_metadata_absent_when_empty
test_domain_validation_persisted
test_domain_validation_passed
```

**Estimated:** 5 tests, ~60 lines

---

## Execution Order

```
Batch A (integration_engine.py — 7 gaps, one file)
├── A1-A7: All independent, can be implemented in sequence in one session
└── A8: Tests

Batch B (budget.py + context_resolution.py — 2 gaps)
├── B1: Budget return type change (slightly higher risk)
├── B2: Context field skips
└── B3: Tests

Batch C (queue.py + prime_contractor.py — 2 gaps)
├── C1: Seed metadata preservation
├── C2: Domain validation persistence
└── C3: Tests
```

Batches A, B, C have no dependencies between them — can be done in any order or in parallel.

**Relationship to Review Feedback Loop:**
- Batch A should ideally land before RFL I2 (accumulator) — the accumulator gets richer data to work with.
- Batch B should ideally land before RFL I2 — budget drop patterns feed spec emphasis.
- Batch C should ideally land before RFL I3 — seed metadata preservation is a prerequisite for seed unification.

---

## Summary

| Batch | Reqs | Files Modified | Tests | Prod Lines | Risk |
|-------|------|---------------|-------|------------|------|
| A | MSR-100,120,220,300,310,330,350 | integration_engine.py | 11 | ~80 | None |
| B | MSR-110,200 | budget.py, context_resolution.py, spec_builder.py, drafter.py | 6 | ~50 | Low |
| C | MSR-210,340 | queue.py, prime_contractor.py | 5 | ~30 | None |
| **Total** | **12 reqs** | **6 files** | **22** | **~160** | |

Combined with Review Feedback Loop:
- **Total requirements:** 24 (RFL) + 12 (MSR) = 36
- **Total new production code:** ~600 (RFL) + ~160 (MSR) = ~760 lines
- **Total tests:** 38 (RFL) + 22 (MSR) = 60 tests

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial plan from Mottainai audit |
