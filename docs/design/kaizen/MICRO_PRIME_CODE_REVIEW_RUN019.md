# Micro Prime Code Review: Quality Short-Circuit Patterns

**Date:** 2026-03-10
**Trigger:** Kaizen investigation of run-019 stop-sequence self-sabotage (PI-002/PI-004)
**Scope:** `src/startd8/micro_prime/` — engine, repair, splicer, prompt_builder, templates, decomposer

---

## Context

Run-019 revealed that `\n\ndef ` stop sequences were truncating Ollama output to imports-only when the model prefixed imports before the target function. Fixes F1 (unclosed fence) and F3 (import-only retry) were applied. This review searched for **other patterns in the same class** — where the pipeline silently degrades, truncates, or rejects correct code.

---

## Critical Issues

### C-1: Template matches skip ALL verification

**File:** `engine.py:2026-2056` (also `engine.py:1962-2003` for TRIVIAL)

Template-matched elements return `verification_verdict="skipped"` with `success=True`. No structural verification, no semantic verification, no repair. If a template produces stale or broken code, it goes straight to the splicer unchecked.

**Impact:** Bad template → bad code delivered to output. No quality gate fires.
**Fix:** Run `_structural_verify()` on template output before accepting.

### C-2: Signature reconcile can break function body

**File:** `repair.py:389-488`

`_step_signature_reconcile` replaces the entire `def` line from the ForwardElementSpec without validating that the new signature is compatible with the body. If the spec says `def foo()` but the body references parameters `x` and `y`, the code passes AST but crashes at runtime with `NameError`.

**Impact:** Code parses but fails at runtime.
**Fix:** After signature replacement, verify parameter names referenced in the body exist in the new signature.

### C-3: Decomposition rolls back ALL sub-elements on partial failure

**File:** `engine.py:1540-1563`

When assembly fails, ALL staged sub-element results are discarded and `self._completed` is rolled back. If 3 of 4 sub-elements succeeded, their code is thrown away. Few-shot examples from successful sub-elements are lost.

**Impact:** Working code discarded; escalates to cloud unnecessarily.
**Fix:** Preserve successful sub-element code in `_completed` even when assembly fails. Pass partial results into escalation context.

---

## High Priority Issues

### H-1: Semantic verify rejects valid code on malformed JSON

**File:** `engine.py:2531-2542`

Uses `find("{")/rfind("}")` to extract JSON. If verifier reason contains `}`, `rfind` truncates and parsing fails. Default on parse failure: `return False` — valid code rejected.

**Impact:** Correct code escalated due to verifier output format.
**Fix:** Use proper JSON extraction or default to accept on parse failure.

### H-2: Chars-per-token estimate systematically underestimates

**File:** `prompt_builder.py:803`

`_CHARS_PER_TOKEN = 4` is optimistic for Python code (actual ~3-3.5). Budget allows ~15-25% more content than intended, risking Ollama context window silently truncating the end of the prompt — the target stub.

**Impact:** Target stub silently lost; LLM generates without knowing what to implement.
**Fix:** Use 3.5 chars/token or add safety margin.

### H-3: `_extract_body()` IndexError on docstring-only functions

**File:** `splicer.py:625-686`

When AST-parsed function has only a docstring, `func.body[1]` raises `IndexError`. Fallback returns the docstring as the "body".

**Impact:** Corrupted splice output.
**Fix:** Guard `func.body[1]` with length check.

### H-4: Few-shot poisoning via hardcoded `syntax_valid=True`

**File:** `engine.py:2347-2358`

`"syntax_valid": True` hardcoded regardless of actual state. Repair-recovered code gets same quality marker as clean code.

**Impact:** Few-shot corpus gradually teaches worse patterns.
**Fix:** Set from `ast_valid_after`; add `repair_recovered` flag.

### H-5: Template AST validation breaks `self.*` code

**File:** `templates.py:771`

Template AST validation wraps body in `def _check():` — but method bodies reference `self.*`. Wrapper has no `self` parameter, so valid method code is rejected.

**Impact:** Valid templates rejected; element escalates.
**Fix:** Use `def _check(self):` when `element.parent_class` is set.

---

## Medium Priority Issues

### M-1: Recursion policy rejection has no fallback to SIMPLE

**File:** `engine.py:1813-1852`

Recursion rejection returns `code=""` with no fallback. Could try `_handle_simple()` before escalating.

### M-2: Import injection uses naive string dedup

**File:** `splicer.py:72-108`

`from foo import bar` and `from foo import (bar, baz)` treated as different. Can produce duplicate imports.

### M-3: Ollama-whole eligibility returns True when signals are None

**File:** `engine.py:1231`

Missing signals → optimistic Ollama-whole generation without dependency validation.

### M-4: Repair silent revert logged at DEBUG only

**File:** `repair.py:593-606`

Repair revert invisible without debug logging. Operators can't distinguish "not attempted" from "attempted but reverted".

### M-5: Decomposition confidence uses static weights

**File:** `decomposer.py:1008-1014`

Confidence weights are domain assumptions, not Kaizen-derived. Multiple signals compound and reject valid plans.

### M-6: Import-only retry fires only once

**File:** `engine.py:2446-2466`

If relaxed-stop retry also produces import-only, it's silently accepted. Should return empty string for outer retry loop.

---

## Fix Batches

### Batch 1 — Critical (C-1, C-2, C-3)
- C-1: Add `_structural_verify()` call on template output
- C-2: Add parameter reference validation after signature reconcile
- C-3: Preserve successful sub-element code on partial decomposition failure

### Batch 2 — High (H-1, H-2, H-3, H-4, H-5)
- H-1: Robust JSON extraction in semantic verify
- H-2: Adjust `_CHARS_PER_TOKEN` to 3.5
- H-3: Guard `func.body[1]` access in `_extract_body()`
- H-4: Set `syntax_valid` from actual AST state + add `repair_recovered`
- H-5: Add `self` parameter to template AST validation wrapper for methods

### Batch 3 — Medium (M-1 through M-6)
- M-1: Fallback to `_handle_simple()` on recursion rejection
- M-4: Upgrade repair revert logging from DEBUG to INFO
- M-6: Return empty on double import-only detection
