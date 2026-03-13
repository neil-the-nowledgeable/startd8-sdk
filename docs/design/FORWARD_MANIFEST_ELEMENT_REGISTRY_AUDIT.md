# Forward Manifest & Element Registry Audit

**Date:** 2026-03-13
**Scope:** Forward manifest lifecycle, element registry integration, code assembly, and repair pipeline wiring

---

## 1. Executive Summary

The Forward Manifest (FM) and Element Registry (ER) are well-designed systems that are **partially integrated**. The core problem: contract violations are **detected too late** (REVIEW phase) and **never routed to the repair pipeline**. Five gaps were identified and fixed.

---

## 2. Systems Overview

### Forward Manifest (`forward_manifest.py`)
Design-time contract specification. Contains `ForwardManifest` → `ForwardFileSpec` → `ForwardElementSpec` with signatures, base classes, imports, and binding constraints.

### Element Registry (`element_registry.py`)
Persistent, thread-safe element cache. Tracks element generation status, phase history, cached code, and context checksums for staleness detection.

### Repair Pipeline (`repair/`)
Deterministic code repair with routing (`routing.py`), step execution (`orchestrator.py`), and specialized fix steps (`steps/`). Includes `ContractViolationFixStep` for manifest violations.

---

## 3. Pipeline Coverage (Before Fix)

| Phase | FM Constraints in Prompt? | FM Violations Checked? | Registry Updated? | Repair Wired? |
|-------|--------------------------|----------------------|-------------------|---------------|
| PLAN | — | — | — | — |
| SCAFFOLD | No | No | No | — |
| DESIGN | Yes | No | No | — |
| IMPLEMENT | Yes (P1 binding) | Splicer only (logged) | Yes | **No** |
| INTEGRATE | No | **No** | No | **No** |
| TEST | **No** (FM lost) | No | No | — |
| REVIEW | Yes | Yes (blocks) | Yes (scoring) | **No** |
| FINALIZE | **No** (FM lost) | No | No | — |

---

## 4. Gaps Identified

### Gap 1: Splicer Violations Never Reach Repair Pipeline

**Location:** `micro_prime/engine.py:1562-1577`, `micro_prime/splicer.py:287-298`

The splicer detects signature and base-class mismatches, returning them in `SpliceResult.violations` (list of strings). The engine logs them but never converts them to `ContractViolationDiagnostic` objects. Meanwhile, `repair/steps/contract_violation_fix.py` filters diagnostics by `isinstance(d, ContractViolationDiagnostic)` — so the two systems are designed to work together but never wired.

**Fix:** Convert splicer violation strings to `ContractViolationDiagnostic` and run them through the repair orchestrator's `contract_violation_fix` step. If repair succeeds, re-splice with the repaired code.

### Gap 2: No Post-Integrate Contract Validation

**Location:** `contractors/integration_engine.py:819-961`

Post-merge repair (`_attempt_repair`) only processes checkpoint failures (syntax, import, lint). It never runs `validate_forward_manifest()` to detect contract violations in the merged code. Violations are only caught at REVIEW — too late for automated repair.

**Fix:** After the existing post-merge repair, run forward manifest validation on integrated files. Convert violations to `ContractViolationDiagnostic` and route through `run_file_repair()`.

### Gap 3: File Assembler Doesn't Check Staleness Before Pre-Fill

**Location:** `utils/file_assembler.py:444-480`

`_lookup_registry_code()` uses cached code from the element registry without checking `is_stale()`. If the element's signature, bases, or decorators have changed since the code was cached, the pre-filled code may be incompatible with the current manifest spec.

**Fix:** Compute the current context checksum from the element spec and call `is_stale()` before using cached code. Fall back to `raise NotImplementedError` stub if stale.

### Gap 4: Repair Pipeline Doesn't Update Registry

**Location:** `micro_prime/engine.py:1386-1388`

After successful generation, the engine calls `registry.set_phase_status(element_id, "implement", "generated")`. But after successful repair (either micro-prime repair or file-level repair), the registry is never updated. Cross-task reuse can pull pre-repair code.

**Fix:** After successful repair in the engine, update registry with the repaired code and set phase status to `"repaired"`.

### Gap 5: Forward Manifest Lost After IMPLEMENT

**Location:** `contractors/context_seed/core.py` (TEST/FINALIZE handlers)

The `TestPhaseHandler.execute()` reads `context.get("generation_results")` and `context.get("integration_results")` but never `context.get("forward_manifest")`. Similarly for `FinalizePhaseHandler`. The manifest is available in context but not consumed for constraint-aware test generation or final validation.

**Fix:** Thread `forward_manifest` from context into TEST phase for binding-constraint-aware test expectations, and into FINALIZE for final contract validation.

---

## 5. Fixes Applied

### Fix 1: Wire Splicer Violations → Repair Pipeline (engine.py)
- Parse splicer violation strings into `ContractViolationDiagnostic` objects
- Run `contract_violation_fix` step on the spliced code
- If repair modifies the code, re-validate via `ast.parse()`
- Update the splice result with repaired code

### Fix 2: Post-Integrate Contract Validation (integration_engine.py)
- After existing `_attempt_repair()`, run `validate_forward_manifest()` on integrated files
- Convert `ContractViolation` objects to `ContractViolationDiagnostic`
- Route through `run_file_repair()` with `contract_violation` category
- Write repaired files back if successful

### Fix 3: Staleness Check in File Assembler (file_assembler.py)
- Import `compute_element_context_checksum` and `is_stale`
- Compute current checksum from element spec before lookup
- Skip cached code if stale, log warning, fall back to stub

### Fix 4: Registry Update After Repair (engine.py)
- After successful splice violation repair, update `entry.extra["code"]`
- Set phase status to `"repaired"` with repair step metadata

### Fix 5: Thread FM to TEST/FINALIZE (core.py)
- Extract `forward_manifest` from context in TEST phase
- Pass binding constraints as test expectations metadata
- Extract in FINALIZE phase for final contract summary

---

## 6. Pipeline Coverage (After First Pass)

| Phase | FM Constraints in Prompt? | FM Violations Checked? | Registry Updated? | Repair Wired? |
|-------|--------------------------|----------------------|-------------------|---------------|
| PLAN | — | — | — | — |
| SCAFFOLD | No | Staleness check (Fix 3) | No | — |
| DESIGN | Yes | No | No | — |
| IMPLEMENT | Yes (P1 binding) | **Yes — splicer → repair (Fix 1)** | **Yes — post-repair (Fix 4)** | **Yes (Fix 1)** |
| INTEGRATE | No | **Yes — post-merge (Fix 2)** | No | **Yes (Fix 2)** |
| TEST | **Yes — constraints (Fix 5)** | No | No | — |
| REVIEW | Yes | Yes (blocks) | Yes (scoring) | — |
| FINALIZE | **Yes — summary (Fix 5)** | **Yes — final check (Fix 5)** | No | — |

---

## 7. Second-Pass Audit — Remaining Gaps

A second audit after the first five fixes identified four additional gaps (A–D) where the element registry was not updated after repair, splice violations were unstructured strings, and staleness detection used a manifest-wide checksum instead of per-element checksums.

### Gap A (MEDIUM): Integration Repair Doesn't Update Registry

**Location:** `integration_engine.py` — `_attempt_pre_merge_repair()` (line ~796) and `_attempt_repair()` (line ~922)

Both repair paths write repaired files back to disk but never update the element registry. Downstream phases (TEST, REVIEW) that query the registry see stale `"generated"` status instead of `"repaired"`, preventing accurate quality tracking.

**Fix:** After writing repaired files, iterate `self._element_registry.elements_for_file(rel_path)` and call `set_phase_status(eid, "integrate", "repaired", metadata={"repair_stage": "pre_merge"|"post_merge"})`.

### Gap B (MEDIUM): Splice Violations Are Unstructured Strings

**Location:** `splicer.py` — `_validate_signature_match()`, `_validate_class_contract()`, `SpliceResult.violations`

Fix 1 parsed violation strings with regex to extract fields for `ContractViolationDiagnostic`. This is fragile — any log message format change breaks the repair pipeline.

**Fix:** Introduced `SpliceViolation` frozen dataclass with typed fields (`violation_type`, `element_name`, `expected`, `actual`, `message`). Updated both validation functions to return structured objects. Added `_SPLICE_VIOLATION_TYPE_MAP` in `engine.py` to map violation types to repair types without string parsing.

### Gap C (LOW): Contract Violation Repair Doesn't Update Registry

**Location:** `integration_engine.py` — `_attempt_contract_violation_repair()` (line ~1171)

Same pattern as Gap A but for the contract-violation-specific repair path. Repaired files written to disk without registry notification.

**Fix:** After writing repaired files, iterate `elements_for_file()` and call `set_phase_status(eid, "integrate", "repaired", metadata={"repair_stage": "contract_violation"})`.

### Gap D (MEDIUM): Prime Backfill Uses Manifest-Wide Checksum

**Location:** `prime_contractor.py` — element cache check (lines 1657–1668)

The backfill loop compared `entry.context_checksum` against `fm.source_checksum` (a single hash for the entire manifest). This means if *any* element's spec changes, *all* elements are marked stale — even those whose individual specs haven't changed.

**Fix:** Replaced with per-element `compute_element_context_checksum()` using `elem_spec.name`, `kind`, `signature`, `parent_class`, `bases`, `decorators`. Calls `is_stale(entry, current_checksum)` for precise per-element staleness detection.

---

## 8. Pipeline Coverage (Final — After Second Pass)

| Phase | FM Constraints in Prompt? | FM Violations Checked? | Registry Updated? | Repair Wired? |
|-------|--------------------------|----------------------|-------------------|---------------|
| PLAN | — | — | — | — |
| SCAFFOLD | No | Staleness check (Fix 3) | No | — |
| DESIGN | Yes | No | No | — |
| IMPLEMENT | Yes (P1 binding) | **Yes — structured splicer → repair (Fix 1, Gap B)** | **Yes — post-repair (Fix 4)** | **Yes (Fix 1)** |
| INTEGRATE | No | **Yes — post-merge (Fix 2)** | **Yes — pre/post-merge + contract (Gap A, C)** | **Yes (Fix 2)** |
| TEST | **Yes — constraints (Fix 5)** | No | No | — |
| REVIEW | Yes | Yes (blocks) | Yes (scoring) | — |
| FINALIZE | **Yes — summary (Fix 5)** | **Yes — final check (Fix 5)** | No | — |

### Key Improvements (Second Pass)
- **Registry coverage**: INTEGRATE phase now updates the registry on all three repair paths (pre-merge, post-merge, contract violation)
- **Type safety**: Splice violations are structured `SpliceViolation` objects — no more regex string parsing
- **Staleness precision**: Prime backfill uses per-element checksums instead of manifest-wide, reducing false-positive cache invalidation

### Remaining Intentional Gaps
- **SCAFFOLD registry writes**: Not needed — SCAFFOLD only pre-fills stubs, no generated code to track
- **TEST/FINALIZE registry writes**: Not needed — these phases consume but don't generate element code
- **DESIGN registry writes**: Not needed — DESIGN produces specs, not code
