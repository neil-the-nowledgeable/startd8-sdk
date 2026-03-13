# Element-by-Element Path Sunset Plan

**Date**: 2026-03-13
**Status**: Proposed
**Depends on**: R1 (file-whole primary) ✅, R2 (unified retry loop) ✅
**Trigger**: When file-whole coverage reaches 95%+ of processed files (currently ~80%)

---

## Context

The Micro Prime engine has two generation paths:

1. **File-whole** (primary) — generates the entire file in one LLM call using the full skeleton as context. Zero lossy information boundaries. ~280 lines of core logic.
2. **Element-by-element** (fallback) — classifies each element, generates body-only fragments, repairs artifacts, splices fragments back into the skeleton. Five lossy information boundaries. ~3,700 lines of compensatory code across 4 modules.

Three Kaizen accidental complexity runs (2026-03-07 through 2026-03-12) established that the element-by-element path's compensatory machinery accounts for **45% of the Micro Prime codebase** while serving a shrinking fraction of traffic. The R1/R2 refactoring (2026-03-13) made file-whole unambiguously primary and unified the retry loops, but the compensatory modules remain.

This document records the architectural rationale for eventual removal and defines the conditions under which each module can be safely deleted.

---

## Why These Components Are Marginal By Architecture

The element-by-element path creates 5 information boundaries:

```
file → element → body-only prompt → repair → splice → skeleton
```

Each boundary loses context:

| Boundary | Context Lost | Compensatory Code |
|----------|-------------|-------------------|
| file → element | Cross-element calls, shared state | classifier (543 lines) |
| element → body | Surrounding code, class structure | prompt_builder body-only path |
| body → repair | Original intent, correct indentation | repair steps 3-7 (~1,350 lines) |
| repair → splice | Indentation context, sibling positions | splicer (1,048 lines) |
| element → sub-element | Inter-dependency between parts | decomposer (1,011 lines) |

File-whole has **zero** lossy boundaries. The model sees the full skeleton (structure + signatures + imports) and fills all stubs in one pass.

Each compensatory module exists to recover information lost at a specific boundary. No amount of optimization to these modules can eliminate the underlying information loss — it is structural to the "split, generate independently, merge" approach.

Evidence: `moderate_ollama_whole` (generating MODERATE elements whole instead of decomposing) succeeds ~70% of the time, confirming that avoiding decomposition produces better results even for complex elements.

---

## Modules to Remove

### 1. decomposer.py (1,011 lines)

**What it does**: Breaks MODERATE elements into SIMPLE sub-elements via ClassDecomposeStrategy (classes → shell + methods) and FunctionChainStrategy (functions → dispatch + helpers).

**Why it's marginal**: Decomposition destroys the context that makes code correct. Sub-elements are generated independently, each guessing at shared state, types, and error handling conventions. Assembly hopes they're compatible. File-whole avoids this by generating everything with full context.

**Current traffic**: 1-3% of elements. Only fires when:
- File-whole is ineligible (>60 elements or >600 LOC), AND
- `moderate_ollama_whole` fails, AND
- `decomposition_enabled=True` (default: `False`)

**Removal condition**: When `decomposition_enabled` default remains `False` for 3+ production runs with no manual overrides.

**Files to remove**:
- `src/startd8/micro_prime/decomposer.py` (1,011 lines)
- `src/startd8/micro_prime/decomposition/` directory
- `tests/unit/micro_prime/test_decomposer.py`
- Related tests in `test_engine.py` (decomposition-specific cases)

**Dependencies to update**:
- `engine.py`: Remove `ModerateDecomposer` import, `_handle_moderate` decomposition branch, `_generate_sub_elements`, graph execution methods
- `models.py`: `MicroPrimeConfig` decomposition fields can be deprecated
- `metrics.py` / `engine.py`: Remove decomposition OTel counters

---

### 2. splicer.py (1,048 lines)

**What it does**: Merges generated body fragments back into the skeleton at the correct indentation level. Handles class nesting, `__init__` ordering, signature validation, constant placement, deduplication.

**Why it's marginal**: Every problem the splicer solves is an artifact of extracting bodies from the skeleton. Body-only prompts say "generate just the body"; the splicer reconstructs what was discarded. File-whole writes the complete file directly — no extraction, no re-insertion.

**Current traffic**: 5-10% of elements. Only fires on the element-by-element fallback path.

**Removal condition**: When element-by-element fallback fires on <5% of files for 3+ production runs.

**Files to remove**:
- `src/startd8/micro_prime/splicer.py` (1,048 lines)
- `tests/unit/micro_prime/test_splicer.py`

**Dependencies to update**:
- `engine.py`: Remove `splice_body_into_skeleton` import and the splice loop in `process_file()` (~40 lines)
- `engine.py`: Remove `_attempt_splice_violation_repair` (lines 86-159)

---

### 3. Repair Steps 3-7 (~1,350 lines)

**What they do**: Fix artifacts of body-only generation that file-whole never produces.

| Step | Lines | Fixes artifact of... | File-whole needs it? |
|------|------:|---------------------|---------------------|
| Over-generation trim | ~60 | Model outputting more than the body | No — file-whole wants the whole file |
| Bare statement wrap | ~65 | Model omitting the `def` line | No — file-whole includes `def` lines |
| Indent normalize | ~160 | Body at wrong nesting depth | No — file-whole has correct nesting |
| Signature reconcile | ~50 | Body has wrong params/return type | No — file-whole sees skeleton signatures |
| Import completion | ~331 | Body references imports stripped from context | No — file-whole sees all imports |
| Duplicate removal | ~180 | Splice introducing duplicates | No — no splice step |

**What file-whole actually needs** (~190 lines):
- Fence strip (remove markdown artifacts from LLM output)
- Octal literal fix (defensive)
- AST validate (syntax gate)
- Bracket balance (defensive)

These already exist as `run_file_repair_pipeline()` (AC-R18).

**Removal condition**: When element-by-element fallback is removed (depends on decomposer + splicer removal above).

**Files to remove**: Individual step files in `src/startd8/repair/steps/` for the 6 body-only steps. Preserve `fence_strip`, `ast_validate`, `octal_fix`, `bracket_balance`.

**Dependencies to update**:
- `repair/orchestrator.py`: Remove body-only step registrations
- `repair/routing.py`: Simplify routing (fewer failure categories)
- `engine.py`: `run_repair_pipeline` calls become `run_file_repair_pipeline`

---

### 4. _structural_verify (203 lines in engine.py)

**What it does**: Validates generated body against manifest — correct function name, parameter count, return type. 16+ decisions, highest cyclomatic complexity in engine.py.

**Why it's marginal**: For file-whole output, `_validate_file_whole_result` already checks all elements are present and non-stub. Per-element structural verification adds marginal value because the model copies signatures directly from the skeleton. Measured incidence of signature drift in file-whole output is near zero.

**Removal condition**: Same as splicer (only fires on element-by-element path).

---

## What Stays

| Component | Lines | Why |
|-----------|------:|-----|
| `engine.py` core (file-whole, process_file routing, _generate_ollama) | ~800 | Essential orchestration |
| `prompt_builder.py` | 869 | Serves both paths; lean and well-justified |
| `prime_adapter.py` core | ~900 | PrimeContractor ↔ MicroPrime bridge, quality gates |
| `classifier.py` | 543 | Tier classification feeds file-whole routing decisions |
| `repair.py` file-whole steps (fence, AST, octal, bracket) | ~190 | Minimal, necessary for any LLM output |
| `templates.py` | 773 | TRIVIAL tier template matching — zero LLM calls |
| `metrics.py` | 391 | Cost reporting, experiment results |
| `models.py` | 577 | Data models used by all paths |

---

## Migration Path

### Phase 0: Current State (done)
- File-whole is primary (R1 ✅)
- Unified retry loop (R2 ✅)
- `decomposition_enabled` defaults to `False`
- File-whole thresholds at 60 elements / 600 LOC

### Phase 1: Lazy-Load (low risk)
- Move `decomposer.py` and `splicer.py` imports behind `if` guards
- Only import when the fallback path actually fires
- Add OTel counters to track how often each module is loaded
- **Validates removal safety**: if counters stay near zero, removal is safe

### Phase 2: Feature-Flag Removal (medium risk)
- Add `legacy_element_by_element_enabled: bool = True` config flag
- When `False`, `process_file()` returns `None` from file-whole failure instead of falling through to element-by-element
- Failed files escalate entirely to cloud
- Run against existing test corpus to measure quality delta

### Phase 3: Code Removal (requires Phase 2 validation)
- Delete decomposer, splicer, body-only repair steps, _structural_verify
- Simplify `process_file()` to: classify → file-whole → escalate
- Remove ~3,700 lines of compensatory code
- Update tests (remove ~200 decomposition/splice/repair tests, add file-whole coverage)

### Phase 4: Raise or Remove Thresholds
- With element-by-element gone, file-whole thresholds become escalation thresholds
- Files above threshold escalate directly to cloud
- Simplifies the mental model: "local generates whole files, cloud handles the rest"

---

## Risks

1. **Large files**: Files with >60 elements / >600 LOC currently fall through to element-by-element. After removal, they escalate to cloud entirely. This increases cloud costs for large files but likely improves output quality (cloud models handle large files better than local element-by-element).

2. **Test coverage gap**: 135 tests cover decomposition vs. 55 for file-whole. Removal deletes more tests than remain. Need to expand file-whole test coverage before Phase 3.

3. **Downstream expectations**: `prime_adapter.py` may have callers that expect element-level granularity in results. File-whole returns one code blob per file with synthetic per-element results. Verify downstream consumers handle this correctly.

---

## Metrics to Track

Before proceeding past Phase 1, measure:

- `micro_prime.generation_path_total{path="element_by_element_fallback"}` — should trend toward zero
- `micro_prime.generation_path_total{path="file_whole_primary"}` — should be >95% of total
- `micro_prime.generation_path_outcome_total{path="file_whole_primary",outcome="success"}` — success rate
- File-whole failure reasons (via existing logging) — identify if failures are systemic or per-file
