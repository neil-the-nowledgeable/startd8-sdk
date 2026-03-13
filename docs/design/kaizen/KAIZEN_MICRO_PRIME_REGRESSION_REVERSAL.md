# Kaizen Analysis: Micro Prime Regression Reversal

**Date:** 2026-03-11
**Scope:** 15 files, +1076 / -146 lines across micro_prime, repair, splicer, code_extraction, element_registry, forward_manifest_extractor, plan_ingestion_enrichment
**Validation:** 876 tests green (731 micro_prime + 145 related)

---

## 1. Summary

A coordinated set of improvements across the Micro Prime engine, repair pipeline, splicer, and supporting modules reverses the regressions observed in runs 014–023. The changes address all four common failure patterns documented in the [Kaizen Data Analysis Guide](KAIZEN_DATA_ANALYSIS_GUIDE.md) §6 and narrow the draft-to-disk assembly gap described in §5.

---

## 2. Failure Patterns Addressed (Guide §6 Table)

| Guide Pattern | Symptom | Fix |
|---|---|---|
| **Broken skeleton** | `raise NotImplementedError` stubs remain after generation | **File-level Ollama-whole** (`engine.py`): generates complete file in one shot for small files (≤5 elements, ≤60 LOC), bypassing element-by-element fragmentation. `_validate_file_whole_result()` rejects output that still contains stubs. |
| **Nested duplicate** | Function defined inside itself | **Dedicated system prompts** (`_ELEMENT_BODY_SYSTEM_PROMPT`, `_FILE_WHOLE_SYSTEM_PROMPT`): eliminates conflicting system/user instructions that caused small models to emit def lines inside body-only output |
| **Wrong function** | Generated code implements different API | **Aligned prompt contract**: body prompt says "output ONLY indented body lines", system prompt says the same — no more "include the def line" contradiction |
| **Cache without code** | `verification_verdict: "skipped"`, `code: null` | Not directly in this changeset (previously fixed), but **escalation cleanup** in `prime_adapter.py` now removes partially-filled files from `written_file_paths` and `generated_files` before fallback |

---

## 3. Assembly Gap Fixes (Guide §5)

### 3a. Skeleton Splicing

`splicer.py`: extracted `_reindent_body()` helper (dedent → reindent in one place, deduped 3 call sites). Added empty-body guard in `_extract_body()`.

### 3b. Fence Stripping

`repair.py`: line-anchored `_FENCE_LINE_RE` replaces `"```" in s` which false-positive matched backtick sequences inside string literals. `_strip_residual_fences()` catches fences that survive the initial `fence_strip` step.

### 3c. Raw Response Passthrough

`_generate_ollama()` now returns raw text (not pre-extracted), letting the repair pipeline's `fence_strip` step handle fence removal in one place (Fix 3 — removes redundant `extract_code_from_response` at the generation boundary).

---

## 4. Success Reporting Mitigations (Guide §7)

- **Post-assembly stub check** in `prime_adapter.py`: files already scheduled for fallback are now skipped during stub-escalation scan (`if file_path in escalated_files: continue`), preventing double-counting.
- **Partial file cleanup**: when escalating, the adapter now `unlink()`s the broken output file and removes it from tracking sets — downstream won't mistake a garbled file for a success.

---

## 5. Repair Pipeline Hardening (Guide §9, Step 6)

| Repair Step | Change |
|---|---|
| `bare_statement_wrap` | Decomposed into 5 focused helpers: `_detect_definition_line()`, `_strip_residual_fences()`, `_hoist_leading_imports()`, `_normalize_body_indentation()`, `_wrap_body_in_def()` |
| `indent_normalize` | New **structural re-indent** strategy (`_structural_reindent()`) for non-uniform indentation that `textwrap.dedent()` can't handle (mixed 4/8/12/16-space from Ollama) |
| `code_extraction` | Handles **unclosed fence blocks** (opening ``` without closing ```) — common with Ollama truncation |

---

## 6. Supporting Improvements

| File | Change |
|---|---|
| `decomposer.py` | Case-sensitivity fix: `"external API"` → `"external api"` (compared against `reason_lower`) |
| `element_registry.py` | Legacy ID alias mapping (`fn/` ↔ `function/`, `cls/` ↔ `class/`) so registry entries survive prefix migrations |
| `forward_manifest_extractor.py` | Skips API signature extraction for non-Python files (Dockerfile, .yaml, etc.) |
| `plan_ingestion_enrichment.py` | 3rd tier parent-heading fallback for sub-feature requirement refs (F-001a → F-001) |
| `metrics.py` | Magic numbers → named constants (`_BASELINE_INPUT_TOKENS_PER_ELEMENT`, `_BASELINE_OUTPUT_TOKENS_PER_ELEMENT`) |
| `engine.py` | Centralized `_record_local_failure()` for circuit breaker mutation (was duplicated in 2 places); classification summary logging |

---

## 7. New Capabilities

### File-Level Ollama-Whole Generation

A new generation strategy that sends the complete skeleton file to Ollama and asks it to fill ALL stubs in a single pass. This matches how small models naturally generate code (complete files) and avoids the body-only fragmentation that confuses them.

**Eligibility criteria** (conservative defaults):
- `file_ollama_whole_enabled: true` (config flag)
- Element count ≤ 5
- Skeleton LOC ≤ 60
- At least one `raise NotImplementedError` stub present

**Validation** (`_validate_file_whole_result`):
1. AST parses successfully
2. No remaining `raise NotImplementedError` stubs
3. All expected elements present in AST
4. No skeleton markers remain

**Fallback**: on any validation failure, falls through to element-by-element processing — zero regression risk.

### Structural Re-indent

A new indent normalization strategy that walks Python block structure (if/for/while/with/try/def/class) to rebuild indentation from scratch. Handles the non-uniform 4/8/12/16-space patterns that `textwrap.dedent()` cannot fix (no common prefix).

Positioned as Strategy 6 (last resort) — only tried after all standard dedent strategies fail.

---

## 8. Validation Checklist (Guide §7)

| Check | Result |
|---|---|
| Tests pass | 731 micro_prime + 145 related = **876 green** |
| No new stubs possible | File-whole validator explicitly rejects `raise NotImplementedError` |
| Draft↔disk gap narrowed | File-whole produces final file directly (no element→splice→merge chain) |
| Circuit breaker deduped | Single `_record_local_failure()` method, no inconsistent counter updates |
| Escalation cleanup | Broken files removed from tracking sets before fallback |

---

## 9. Risk Assessment

| Risk | Mitigation |
|---|---|
| File-whole produces incorrect code | Gated behind config (`max_elements=5`, `max_loc=60`); full AST + element presence validation; graceful fallback to element-by-element |
| Structural re-indent corrupts valid code | Last-resort strategy (Strategy 6); only used when all prior strategies fail AST validation |
| Raw response passthrough breaks callers | Repair pipeline's `fence_strip` step handles all fence removal; unclosed fence handling added to `extract_code_from_response` |
| Legacy ID aliases create phantom hits | Logged at INFO level; exact alias tried first, then name-prefix scan; no writes to index |

---

## 10. Cross-Reference

- Runs that exhibited these regressions: 014, 016, 017, 019, 022, 023
- Prior investigations: [KAIZEN_INVESTIGATION_RUN019](KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md), [KAIZEN_INVESTIGATION_RUN023](KAIZEN_INVESTIGATION_RUN023_ONLINE_BOUTIQUE.md), [MICRO_PRIME_CODE_REVIEW_RUN019](MICRO_PRIME_CODE_REVIEW_RUN019.md)
- Design principle: [Mottainai](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — don't discard partially-filled skeletons; repair or escalate
