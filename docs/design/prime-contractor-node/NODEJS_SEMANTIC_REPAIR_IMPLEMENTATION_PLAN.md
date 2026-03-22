# Node.js Semantic Repair — Implementation Plan

> **Requirement:** REQ-KZ-ND-402 (KAIZEN_NODEJS_REQUIREMENTS.md §5)
> **Date:** 2026-03-22
> **Status:** PLAN (v1.1 — post-plan-review)

---

## Current State

- 6 semantic checks exist in `nodejs_semantic_checks.py` (all advisory-only)
- Compliance results collected in `integration_engine.py:_run_semantic_checks()` (REQ-KZ-ND-402c — IMPLEMENTED)
- `_EXT_TO_LANGUAGE` in `routing.py` already maps all 6 Node.js extensions to `"nodejs"`
- 2 syntax/import repair routes exist for Node.js (`js_syntax_error`, `js_import_error`)
- `JsSyntaxValidateStep` exists and is registered in `_STEP_FACTORIES`
- `CAUSE_TO_SUGGESTION` has 2 Node.js entries: `console_logging_detected`, `module_system_mixing_detected`
- `_SEMANTIC_CATEGORY_TO_SUGGESTION` has 3 Node.js mappings: `console_log_in_service`, `module_system_mixing`, `python_contamination`
- 3 implemented checks (`var_usage`, `duplicate_require`, `unhandled_promise`) have NO suggestion wiring — invisible to Kaizen
- **Bug:** `_check_python_contamination()` has a `self.` substring false-positive that produces CRITICAL (0.0) scores on clean files
- No semantic repair steps or semantic routing entries exist for Node.js yet

---

## Phase 0: Quick Wins (immediate, independent, high-value)

**Goal:** Fix data quality bugs and wire existing checks before building new steps. These are independent of each other and of Phase 1/2.

### Task 0.1: Fix `self.` substring false positive (CRITICAL data quality)

**File:** `src/startd8/validators/nodejs_semantic_checks.py`

The current `_check_python_contamination()` uses `if fp in source` — a whole-file substring match. The fingerprint `"self."` matches inside string literals (e.g., `"help yourself."`) and comments, producing false CRITICAL scores.

**Fix:** Change to line-by-line matching with line-start anchor for `self.`:

```python
# Before (line 147):
for fp in _PY_FINGERPRINTS:
    if fp in source:

# After:
for i, line in enumerate(source.splitlines(), start=1):
    stripped = line.strip()
    if _is_comment_line(stripped):
        continue
    for fp in _PY_FINGERPRINTS:
        if fp == "self." and not re.match(r'^\s*self\.', line):
            continue  # only match self. at statement level
        if fp in stripped:
            ...
```

**Test:** `test_contamination_self_false_positive` — `console.log("help yourself.")` must NOT trigger `python_contamination`.

### Task 0.2: Wire 3 missing `_SEMANTIC_CATEGORY_TO_SUGGESTION` mappings

**File:** `src/startd8/contractors/prime_postmortem.py`

Add to `_SEMANTIC_CATEGORY_TO_SUGGESTION` (after line 715):
```python
"var_usage": "var_usage_detected",
"duplicate_require": "duplicate_require_detected",
"unhandled_promise": "unhandled_promise_detected",
```

These map to the `CAUSE_TO_SUGGESTION` entries added in Task 1.1. Without this mapping, the checks fire but the suggestion pipeline never sees them (silent failure).

### Task 0.3: Add `ShebangStripStep` (quick win repair step)

**New file:** `src/startd8/repair/steps/shebang_strip.py`

~15 lines. Removes `#!/usr/bin/env python3` (or any Python shebang) from JS/TS files. Deterministic, no dependencies, no external tools.

**Registration:** Add to `_STEP_FACTORIES`, `_CANONICAL_ORDER` (after `fence_strip`), `__init__.py`.

---

## Phase 1: Advisory Completeness (no new semantic repair steps)

**Goal:** All 6 categories visible in postmortem/Kaizen scoring with actionable feedback hints. Requires Phase 0 tasks 0.1 and 0.2 as prerequisites.

### Task 1.1: Add 4 missing `CAUSE_TO_SUGGESTION` mappings

**File:** `src/startd8/contractors/prime_postmortem.py`

Add entries after the existing `module_system_mixing_detected` entry:

| Key | Phase | Hint summary |
|-----|-------|-------------|
| `var_usage_detected` | `draft` | Use `const` for immutable bindings, `let` for loop counters. Never use `var`. |
| `duplicate_require_detected` | `draft` | Each module should be imported once. Consolidate destructured imports from the same module. |
| `unhandled_promise_detected` | `draft` | Wrap async operations in try/catch. Add `process.on('unhandledRejection', ...)` as safety net. |
| `python_contamination_detected` | `spec` | Non-JS artifacts in JS file — check template routing for non-Python trivial tasks. |

**Verification:** Unit test — trigger each category, verify hint text appears in postmortem.

### Task 1.2: Wire semantic check categories to root cause detection

**File:** `src/startd8/contractors/prime_postmortem.py`

Verify `_classify_root_cause()` (or equivalent) maps semantic issue categories from `compliance_results` to the `CAUSE_TO_SUGGESTION` keys. If the mapping is indirect (e.g., via `_detected` suffix convention), confirm the convention applies to all 6 Node.js categories.

**Verification:** Run postmortem on a `.js` file containing `var x = 1;` → verify `var_usage_detected` appears in `kaizen-suggestions.json`.

### Phase 1 test file

**New file:** `tests/unit/contractors/test_nodejs_kaizen_hints.py`

- 4 tests: one per new `CAUSE_TO_SUGGESTION` entry
- 2 tests: verify existing `console_logging_detected` and `module_system_mixing_detected` entries

---

## Phase 2: Text-Based Repair Steps

**Goal:** 3 deterministic repair steps, 3 semantic routing entries, bridge registration.

### Task 2.1: `VarToConstStep`

**New file:** `src/startd8/repair/steps/var_to_const.py`

```
class VarToConstStep:
    name = "var_to_const"

    __call__(code, context, file_path, element_context) -> RepairStepResult:
        - Guard: skip non-JS/TS extensions
        - Line-by-line regex:
          - for-loop var: re.sub(r'(for\s*\(\s*)var\b', r'\1let', line)
          - other var:    re.sub(r'^\s*var\s+', 'const ', line)  (preserving indent)
        - Verification: NOT done in-step (downstream js_syntax_validate handles it)
        - Return RepairStepResult(modified=any_changes, code=result)
```

**Design decisions:**
- Line-start anchor (`^\s*var\s+`) prevents matching `var` inside strings/comments
- For-loop detection uses `for\s*\(\s*var\b` → replaces with `let` (not `const`) because loop variables are reassigned
- Over-constification is acceptable: if a `var` was being reassigned, `const` will cause `node --check` failure → repair rolls back to pre-repair version
- Does NOT handle `var` inside multi-line template literals (acceptable — these are rare in LLM output)

### Task 2.2: `DedupRequireStep`

**New file:** `src/startd8/repair/steps/dedup_require.py`

```
class DedupRequireStep:
    name = "dedup_require"

    __call__(code, context, file_path, element_context) -> RepairStepResult:
        - Guard: skip non-JS/TS extensions
        - Track seen module specifiers (dict: module → first_line_number)
        - For each require/import line:
          - Extract module specifier via _REQUIRE_RE (from nodejs_semantic_checks.py)
          - If specifier already seen:
            - Check if destructuring pattern differs → SKIP (don't remove)
            - Else (identical import) → remove line
        - Return RepairStepResult(modified=any_removals, code=result)
```

**Design decisions:**
- Destructuring merge is OUT OF SCOPE for Phase 2 (requires AST). `const {a} = require('x')` + `const {b} = require('x')` → both lines kept, neither removed
- "Identical import" = same full line content (conservative) OR same specifier with no destructuring (e.g., `require('express')` twice)
- ESM `import` and CJS `require` of the same module are treated as separate (they have different semantics)

### Task 2.3: `ContaminationStripJsStep`

**New file:** `src/startd8/repair/steps/contamination_strip_js.py`

```
class ContaminationStripJsStep:
    name = "contamination_strip_js"

    __call__(code, context, file_path, element_context) -> RepairStepResult:
        - Guard: skip non-JS/TS extensions
        - Python fingerprints (from nodejs_semantic_checks._check_python_contamination):
          "def ", "import os", "from __future__", "#!/usr/bin/env python"
        - For "self.": match only at statement level (^\s*self\.) to avoid
          false positives in string literals
        - Remove matching lines entirely
        - Return RepairStepResult(modified=any_removals, code=result,
                                  metrics={"lines_removed": count})
```

**Design decisions:**
- `self.` is only matched when it appears at statement level (line-start + optional whitespace), not inside strings like `"help yourself."`
- `def ` is safe to match at line-start because JS doesn't have `def` keyword
- `import os` without quotes/braces is Python-specific (JS would be `import os from 'os'` or `require('os')`)
- Lines are removed entirely (not modified) — contaminated files typically have whole Python preambles

### Task 2.4: Register steps

**Files to modify:**

1. **`src/startd8/repair/steps/__init__.py`** — Add imports and `__all__` entries:
   ```python
   from .var_to_const import VarToConstStep
   from .dedup_require import DedupRequireStep
   from .contamination_strip_js import ContaminationStripJsStep
   ```

2. **`src/startd8/repair/routing.py`** — Add to `_CANONICAL_ORDER` (before `js_syntax_validate`):
   ```python
   "var_to_const",
   "dedup_require",
   "contamination_strip_js",
   ```

   Add to `_STEP_FACTORIES`:
   ```python
   "var_to_const": VarToConstStep,
   "dedup_require": DedupRequireStep,
   "contamination_strip_js": ContaminationStripJsStep,
   ```

   Add to `_ROUTING_TABLE`:
   ```python
   ("semantic", "var_usage", ["var_to_const", "js_syntax_validate"], "MEDIUM", "nodejs"),
   ("semantic", "duplicate_require", ["dedup_require", "js_syntax_validate"], "MEDIUM", "nodejs"),
   ("semantic", "python_contamination", ["contamination_strip_js", "js_syntax_validate"], "HIGH", "nodejs"),
   ```

3. **`src/startd8/repair/semantic_bridge.py`** — Add to `_REPAIRABLE_CATEGORIES`:
   ```python
   "var_usage",
   "duplicate_require",
   "python_contamination",
   ```

### Task 2.5: Tests

**New file:** `tests/unit/repair/test_nodejs_semantic_repair.py`

| Test | Input | Expected |
|------|-------|----------|
| `test_var_to_const_basic` | `var x = 1;` | `const x = 1;` |
| `test_var_to_let_for_loop` | `for (var i = 0; ...)` | `for (let i = 0; ...)` |
| `test_var_in_string_untouched` | `console.log("var x")` | unchanged |
| `test_var_in_comment_untouched` | `// var x = 1;` | unchanged |
| `test_dedup_require_identical` | two `require('express')` | first kept, second removed |
| `test_dedup_require_different_destructuring` | `{a} = require('x')` + `{b} = require('x')` | both kept (skip) |
| `test_dedup_import_esm` | two `import x from 'y'` | first kept, second removed |
| `test_contamination_strip_def` | `def main():` in `.js` | line removed |
| `test_contamination_strip_future` | `from __future__ import annotations` | line removed |
| `test_contamination_self_in_string` | `console.log("yourself.")` | unchanged |
| `test_contamination_self_at_statement` | `self.name = "test"` | line removed |
| `test_clean_file_no_modifications` | valid JS with no issues | `modified=False` |
| `test_non_js_file_skipped` | `.py` file with `var x = 1` | `modified=False` |
| `test_routing_var_usage` | `SemanticDiagnostic(semantic_category="var_usage")` | routes to `["var_to_const", "js_syntax_validate"]` |
| `test_routing_python_contamination` | `SemanticDiagnostic(semantic_category="python_contamination")` | routes to `["contamination_strip_js", "js_syntax_validate"]` |
| `test_bridge_translates_nodejs_categories` | `semantic_issues=[{"category": "var_usage", ...}]` | produces `SemanticDiagnostic` |
| `test_bridge_skips_advisory_categories` | `semantic_issues=[{"category": "unhandled_promise", ...}]` | empty list (not repairable) |

---

## Phase 3: ESLint Integration (future)

**Goal:** `eslint --fix` as composite step with Phase 2 fallback.

### Task 3.1: `EslintAutoFixStep`

**New file:** `src/startd8/repair/steps/eslint_autofix.py`

```
class EslintAutoFixStep:
    name = "eslint_autofix"

    __call__(code, context, file_path, element_context) -> RepairStepResult:
        - Check shutil.which("eslint")
        - If available:
          - Write code to temp file
          - Run: eslint --fix --rule '{"no-var":"error","no-duplicate-imports":"error"}' {temp}
          - Read back result
          - Verify with node --check / tsc --noEmit
        - If NOT available:
          - Fall back: run VarToConstStep + DedupRequireStep + ContaminationStripJsStep
            sequentially on the code (internal composition)
        - Return RepairStepResult
```

### Task 3.2: Routing update

Replace Phase 2 step names in routing entries with `eslint_autofix` as the primary step. Phase 2 steps become internal fallbacks (invoked by `EslintAutoFixStep` when ESLint is unavailable), not separate routing entries.

### Task 3.3: Validation corpus

Create a test corpus of 10+ `.js`/`.ts` files with known defects. Run both ESLint-based and text-based repair. Verify ESLint produces equal or better outcomes.

---

## Dependency Graph

```
Phase 0.1 (self. bug fix) ────────────────────┐
Phase 0.2 (suggestion mapping) ───┐            │
Phase 0.3 (shebang_strip) ───────┤            │
                                  │            │
                                  ▼            │
Phase 1.1 (CAUSE_TO_SUGGESTION) ──┤            │
Phase 1.2 (root cause wiring)  ───┤            │
                                   │            │
                                   ├──→ Phase 2.1-2.3 (repair steps)
                                   │         │
                                   │         ▼
                                   │    Phase 2.4 (registration)
                                   │         │
                                   │         ▼
                                   │    Phase 2.5 (tests)
                                   │         │
                                   │         ▼
                                   └──→ Phase 3 (ESLint — future)
```

**Phase 0** tasks are all independent of each other and can be done in parallel. Task 0.1 (`self.` fix) is a prerequisite for reliable test results in all subsequent phases — do it first.
**Phase 1** task 1.1 requires Phase 0.2 (the `_SEMANTIC_CATEGORY_TO_SUGGESTION` entries need matching `CAUSE_TO_SUGGESTION` entries).
**Phase 2** tasks 2.1-2.3 are independent (parallel). Task 2.4 depends on 2.1-2.3. Task 2.5 depends on 2.4.

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| `var_to_const` over-constifies reassigned vars | Repair rolls back (pre-repair preserved) | `js_syntax_validate` catches `const` reassignment via `node --check` |
| `dedup_require` removes import with different destructuring | Wrong code | Phase 2 skips lines with different destructuring patterns |
| `contamination_strip_js` matches `self.` in JS string | Removes valid code line | Line-start anchor (`^\s*self\.`) prevents string-interior matches |
| `dedup_require` removes ESM `import type` needed by TypeScript | Type errors | `tsc --noEmit` verification catches missing type imports |
| ESLint not installed in CI/generation environment | Phase 3 degrades | Built-in fallback to Phase 2 text-based steps |

---

## Files Changed (Phase 0 + Phase 1 + Phase 2)

| File | Change Type | Phase |
|------|------------|-------|
| `src/startd8/validators/nodejs_semantic_checks.py` | EDIT — fix `self.` substring bug in `_check_python_contamination()` | 0.1 |
| `src/startd8/contractors/prime_postmortem.py` | EDIT — add 3 `_SEMANTIC_CATEGORY_TO_SUGGESTION` entries | 0.2 |
| `src/startd8/contractors/prime_postmortem.py` | EDIT — add 4 `CAUSE_TO_SUGGESTION` entries | 1.1 |
| `src/startd8/repair/steps/shebang_strip.py` | NEW — `ShebangStripStep` (~15 lines) | 0.3 |
| `src/startd8/repair/steps/var_to_const.py` | NEW — `VarToConstStep` | 2.1 |
| `src/startd8/repair/steps/dedup_require.py` | NEW — `DedupRequireStep` | 2.2 |
| `src/startd8/repair/steps/contamination_strip_js.py` | NEW — `ContaminationStripJsStep` | 2.3 |
| `src/startd8/repair/steps/__init__.py` | EDIT — add 4 imports + `__all__` entries | 0.3 + 2.4 |
| `src/startd8/repair/routing.py` | EDIT — add to `_CANONICAL_ORDER`, `_STEP_FACTORIES`, `_ROUTING_TABLE` | 0.3 + 2.4 |
| `src/startd8/repair/semantic_bridge.py` | EDIT — add 3 categories to `_REPAIRABLE_CATEGORIES` | 2.4 |
| `tests/unit/validators/test_nodejs_semantic_checks.py` | EDIT — add `self.` false positive regression test | 0.1 |
| `tests/unit/contractors/test_nodejs_kaizen_hints.py` | NEW — 6 hint tests + 3 mapping tests | 0.2 + 1.1 |
| `tests/unit/repair/test_nodejs_semantic_repair.py` | NEW — 17 repair/routing/bridge tests | 2.5 |
