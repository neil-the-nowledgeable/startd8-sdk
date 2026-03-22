# Node.js Kaizen Phase 4 — Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-22
> **Parent:** [KAIZEN_NODEJS_REQUIREMENTS.md](KAIZEN_NODEJS_REQUIREMENTS.md) (REQ-KZ-ND-200, REQ-KZ-ND-300)
> **Depends on:** Phases 0–3 (complete)
> **Scope:** Remaining semantic checks, language-aware quality scoring, prettier repair step

---

## Table of Contents

1. [Overview](#1-overview)
2. [Semantic Check Completion](#2-semantic-check-completion-req-kz-nd-700)
3. [Language-Aware Quality Scoring](#3-language-aware-quality-scoring-req-kz-nd-800)
4. [Prettier Repair Step](#4-prettier-repair-step-req-kz-nd-900)
5. [Dependency Graph](#5-dependency-graph)
6. [Verification Strategy](#6-verification-strategy)

---

## 1. Overview

Phase 4 covers three areas that were deferred from Phases 0–3:

| Area | Why Deferred | Value |
|------|-------------|-------|
| 5 PLANNED semantic checks | Detection-only — no repair pipeline dependency | Richer Kaizen signal quality; feeds into scoring + suggestions |
| Language-aware quality scoring | Cross-cutting — affects all 4 languages (C#, Java, Go, Node.js) | More accurate per-language scores; currently all languages share a Python-centric formula |
| Prettier repair step | Prettier already runs in `post_generation_cleanup()` | Formalizes prettier as a repair step with rollback safety; currently best-effort with no verification |

**Key insight from planning:** The language-aware scoring mechanism is the highest-leverage item. It benefits all 4 non-Python languages simultaneously, each of which has an aspirational scoring formula documented but not implemented. The 5 semantic checks are independent quick wins. The prettier step is lowest priority since prettier already runs (just without repair pipeline integration).

---

## 2. Semantic Check Completion (REQ-KZ-ND-700)

### REQ-KZ-ND-700: Implement Remaining PLANNED Semantic Checks

5 checks specified in REQ-KZ-ND-200 are marked **[PLANNED]**. Each is detection-only (no repair step needed), populates `semantic_issues` in `DiskComplianceResult`, and feeds into Kaizen scoring + suggestion wiring.

**Priority order** (by defect frequency in LLM-generated Node.js code):

| Priority | Check | Category | Rationale |
|----------|-------|----------|-----------|
| P1 | `check_unused_requires()` | `unused_import` | Most common JS defect — LLMs import packages then never use them. High noise in postmortem reports. |
| P2 | `check_missing_exports()` | `missing_exports` | Second most common — LLMs generate modules with functions but forget `module.exports` or `export`. Dead module detection. |
| P3 | `check_typescript_any_overuse()` | `any_type_overuse` | TypeScript-specific — common in LLM output. Degrades type safety. Only applies to `.ts`/`.tsx` files. |
| P4 | `check_missing_error_handling()` | `missing_error_handling` | Extends existing `_check_unhandled_promises()` with deeper patterns (`.then()` without `.catch()`, `new Promise` without reject). |
| P5 | `check_callback_hell()` | `callback_hell` | Least common in modern LLM output — models generally produce async/await. Low priority. |

**Go contamination detection** (extends `_check_python_contamination()`):

| Priority | Pattern | Confidence |
|----------|---------|------------|
| P2 | `func ` followed by `(` | 85% — HIGH |
| P2 | `package main` | 95% — CRITICAL |
| P2 | `fmt.Println` | 100% — CRITICAL |

Go contamination can be added to `_check_python_contamination()` with minimal effort — it's the same line-by-line fingerprint matching pattern.

#### REQ-KZ-ND-701: Implementation Constraints

Each check MUST:

1. **Live in `validators/nodejs_semantic_checks.py`** — same module as existing checks, called from `run_nodejs_semantic_checks()`
2. **Return `List[SemanticIssue]`** with correct `check=` category name matching the table above
3. **Skip comment lines** via `_is_comment_line()` (existing helper)
4. **Have a `_SEMANTIC_CATEGORY_TO_SUGGESTION` entry** in `prime_postmortem.py` mapping to a `CAUSE_TO_SUGGESTION` hint
5. **Have unit tests** in `tests/unit/validators/test_nodejs_semantic_checks.py` with positive and negative cases

Each check MUST NOT:

1. Require external tools (regex/text-based only — consistent with existing checks)
2. Modify the `_REPAIRABLE_CATEGORIES` set (these are detection-only, not repairable)
3. Break existing tests

#### REQ-KZ-ND-702: Unused Requires Check (P1)

**Function:** `_check_unused_requires(source: str) -> List[SemanticIssue]`

**Algorithm:**
1. Extract all import bindings: `const X = require(...)` → binding `X`; `import { X, Y } from '...'` → bindings `X`, `Y`; `import X from '...'` → binding `X`
2. For each binding, count references in the remaining source (excluding the import line itself)
3. If reference count == 0: emit `SemanticIssue(check="unused_import", severity="warning")`

**Exceptions (do not flag):**
- Side-effect imports with no binding: `require('dotenv').config()`, `import './polyfill'`, `import 'reflect-metadata'`
- TypeScript type-only imports: `import type { X } from '...'`
- Re-exports: `const X = require('x'); module.exports = { X }` — `X` appears in exports

**Edge case:** Destructured imports `const { X: aliasX } = require('...')` — track `aliasX`, not `X`.

**Kaizen wiring:**
- `_SEMANTIC_CATEGORY_TO_SUGGESTION`: `"unused_import"` → `"unused_import_detected"`
- `CAUSE_TO_SUGGESTION`: `"unused_import_detected"` → phase `"draft"`, hint: "Prior run imported modules that were never used. Only import what you reference. Remove unused require()/import statements."

#### REQ-KZ-ND-703: Missing Exports Check (P2)

**Function:** `_check_missing_exports(source: str, file_path: Optional[str]) -> List[SemanticIssue]`

**Algorithm:**
1. Check if file has any `function` or `class` keyword declarations
2. Check if file has any export mechanism: `module.exports`, `exports.`, `export default`, `export {`, `export const`, `export function`, `export class`
3. If (1) is true and (2) is false: emit `SemanticIssue(check="missing_exports", severity="warning")`

**Exceptions (do not flag):**
- Entry point files (from REQ-KZ-ND-100): `index.js`, `main.js`, `app.js`, `server.js`, `cli.js` (and `.ts` variants)
- Files containing `process.exit()`, `http.createServer()`, `app.listen()`, or a shebang
- Test files: path contains `/test/`, `/tests/`, `/__tests__/`, `/spec/`, or filename matches `*.test.*`, `*.spec.*`
- Config files: `jest.config.*`, `.eslintrc.*`, `*.config.js`, `*.config.ts`

**Kaizen wiring:**
- `"missing_exports"` → `"missing_exports_detected"` → phase `"draft"`, hint: "Prior run generated modules that define functions/classes but export nothing. Every non-entry-point module MUST export its public API via module.exports (CJS) or export (ESM)."

#### REQ-KZ-ND-704: TypeScript Any Overuse Check (P3)

**Function:** `_check_typescript_any_overuse(source: str, file_path: Optional[str]) -> List[SemanticIssue]`

**Guard:** Only runs on `.ts` and `.tsx` files. Returns empty list for `.js`/`.mjs`/`.cjs`/`.jsx`.

**Algorithm:**
1. Count occurrences of `: any`, `as any`, `<any>`, `: any[]`, `: any)`, `: any,` via regex
2. Exclude matches on lines with `// @ts-ignore`, `// @ts-expect-error`, or `// eslint-disable`
3. Exclude `.d.ts` files entirely
4. If count > 3: emit `SemanticIssue(check="any_type_overuse", severity="warning")`
5. If count > 10: emit with `severity="error"` instead

**Kaizen wiring:**
- `"any_type_overuse"` → `"any_type_overuse_detected"` → phase `"draft"`, hint: "Prior run used excessive `any` type annotations. Use specific types or `unknown` with type guards. Define interfaces for object shapes."

#### REQ-KZ-ND-705: Enhanced Error Handling Check (P4)

**Function:** `_check_missing_error_handling(source: str) -> List[SemanticIssue]`

**Relationship to existing:** This REPLACES the simpler `_check_unhandled_promises()`. The existing check catches standalone async method calls; this version adds `.then()` chains without `.catch()` and `new Promise` without reject.

**Algorithm (additive patterns beyond existing):**
1. Detect `.then(` not followed by `.catch(` on the same or next line: emit `SemanticIssue(check="unhandled_promise", severity="warning")`
2. Detect `new Promise(` where the callback parameter list doesn't include a second param (reject): emit with severity `"warning"`

**Keep existing `_check_unhandled_promises()` patterns** — the existing `_ASYNC_CALL_RE` patterns remain valid. This check subsumes and extends them.

**Kaizen wiring:** Already wired — `"unhandled_promise"` → `"unhandled_promise_detected"` (from Phase 0).

#### REQ-KZ-ND-706: Callback Hell Check (P5)

**Function:** `_check_callback_hell(source: str) -> List[SemanticIssue]`

**Algorithm:**
1. Track indentation depth changes line-by-line
2. Detect callback patterns: line ending with `=> {` or `function(` followed by indentation increase
3. If 3+ consecutive indentation increases each associated with a callback pattern: emit `SemanticIssue(check="callback_hell", severity="warning")` at the innermost callback line

**Simplification:** This is the lowest-priority check. A minimal implementation that counts `=> {` nesting depth via brace counting is acceptable for v1. A more sophisticated version (tracking actual callback chains) can follow.

**Kaizen wiring:**
- `"callback_hell"` → `"callback_hell_detected"` → phase `"draft"`, hint: "Prior run used deeply nested callbacks. Convert to async/await: `const result = await asyncOperation()`. Use Promise.all() for parallel operations."

#### REQ-KZ-ND-707: Go Contamination Fingerprints

**Change:** Add Go-specific fingerprints to `_check_python_contamination()` (rename internally to `_check_cross_language_contamination()` to reflect broader scope).

**New fingerprints (line-start matching, consistent with existing Python patterns):**

| Fingerprint | Match strategy |
|-------------|---------------|
| `package main` | `stripped.startswith("package main")` |
| `fmt.Println` | `"fmt.Println" in stripped` (unique to Go) |
| `func ` | `stripped.startswith("func ")` (Go function keyword — JS doesn't have `func`) |

**Category:** Same `python_contamination` check value (or rename to `cross_language_contamination` — decision: keep `python_contamination` for backward compatibility since the suggestion wiring and repair step already use it).

---

## 3. Language-Aware Quality Scoring (REQ-KZ-ND-800)

### REQ-KZ-ND-800: Language Dispatch for `compute_disk_quality_score()`

**Scope:** This is a CROSS-CUTTING requirement affecting all 4 non-Python languages. The mechanism is defined here because Node.js is the trigger, but it must support C#, Java, and Go formulas from their respective Kaizen requirements docs.

**Current state:** `compute_disk_quality_score()` in `forward_manifest_validator.py` uses a single language-agnostic formula:
```
composite = (contract_compliance × 0.4) + (import_completeness × 0.2)
          + (stub_penalty × 0.2) + (semantic_penalty × 0.2)
```

**Problem:** All 4 non-Python languages have different quality dimensions and weights (module_consistency for Node.js, nullable_safety for C#, error_handling for Go, type_safety for Java). The generic `semantic_penalty` lumps all semantic issues together with uniform severity weighting — it can't distinguish "3 unused imports (cosmetic)" from "1 module_system_mixing (structural)".

#### REQ-KZ-ND-801: Scoring Dispatch Interface

Add an optional `language_id: Optional[str] = None` parameter to `compute_disk_quality_score()`. When provided, delegate to a language-specific scoring function. When `None`, fall back to the existing generic formula (backward compatible).

```python
def compute_disk_quality_score(
    compliance: Any,
    language_id: Optional[str] = None,
) -> float:
    if language_id is not None:
        scorer = _LANGUAGE_SCORERS.get(language_id)
        if scorer is not None:
            return scorer(compliance)
    # Fall back to generic formula
    ...
```

**Registry:**
```python
_LANGUAGE_SCORERS: dict[str, Callable[[Any], float]] = {
    "nodejs": _compute_nodejs_quality_score,
    # "csharp": _compute_csharp_quality_score,  # future
    # "go": _compute_go_quality_score,          # future
    # "java": _compute_java_quality_score,      # future
}
```

Start with Node.js only. Other languages can be added as their check suites mature.

#### REQ-KZ-ND-802: Node.js Scoring Function

**Function:** `_compute_nodejs_quality_score(compliance: Any) -> float`

Implements the formula from REQ-KZ-ND-300:
```
quality_score = (syntax_check × 0.25)
             + (module_consistency × 0.20)
             + (stub_penalty × 0.20)
             + (error_handling × 0.15)
             + (contamination_check × 0.10)
             + (convention_compliance × 0.10)
```

**Component derivation from `DiskComplianceResult`:**

| Component | Source | Derivation |
|-----------|--------|------------|
| `syntax_check` | `compliance.ast_valid` | `1.0` if True, `0.0` if False |
| `module_consistency` | `compliance.semantic_issues` | `0.0` if any issue has `category == "module_system_mixing"`, else `1.0` |
| `stub_penalty` | `compliance.stubs_remaining` | `max(0, 1.0 - stubs × 0.2)` |
| `error_handling` | `compliance.semantic_issues` | Count issues with `category == "unhandled_promise"`: `max(0, 1.0 - count × 0.15)` |
| `contamination_check` | `compliance.semantic_issues` | `0.0` if any issue has `category == "python_contamination"`, else `1.0` |
| `convention_compliance` | `compliance.semantic_issues` | Composite: `var_usage` count × 0.1, `console_log_in_service` count × 0.05, capped at 0.0 floor |

**Invariant:** If `syntax_check == 0.0` or `contamination_check == 0.0`, the total score MUST be 0.0 regardless of other components (fatal defects).

#### REQ-KZ-ND-803: Call Site Wiring

The `language_id` must be passed to `compute_disk_quality_score()` at these call sites:

| Call Site | File | How to Get `language_id` |
|-----------|------|------------------------|
| `PrimePostMortemEvaluator._evaluate_feature()` | `prime_postmortem.py:1385` | From `feature.language_id` or inferred from `feature.target_files` via `resolve_language()` |
| `IntegrationEngine._run_semantic_checks()` | `integration_engine.py:2772` | From `_EXT_TO_LANGUAGE` via the file extension being scored |
| `_repair_single_file()` | `repair/orchestrator.py:869` | Already has language_id from `infer_language_from_diagnostics()` |

**Backward compatibility:** All existing callers that don't pass `language_id` get the generic formula (no behavior change for Python or unknown languages).

---

## 4. Prettier Repair Step (REQ-KZ-ND-900)

### REQ-KZ-ND-900: Prettier Format Step

**Current state:** Prettier runs via `NodeLanguageProfile.post_generation_cleanup()` as a best-effort cosmetic pass. It has no repair pipeline integration (no rollback, no verification, no metrics).

**Value of formalizing:** Integrating prettier as a repair step provides:
- Rollback safety (if prettier breaks syntax, pre-repair version preserved)
- Verification (`node --check` after prettier)
- Metrics (prettier ran, files modified, time spent)
- Consistent pipeline visibility (shows up in repair route logs)

**Priority:** LOW. The existing `post_generation_cleanup()` path works. This is a quality-of-life improvement.

#### REQ-KZ-ND-901: PrettierFormatStep

**New file:** `repair/steps/prettier_format.py`

**Behavior:**
1. Guard: skip if `shutil.which("prettier") is None` and `shutil.which("npx") is None`
2. Guard: skip non-JS/TS extensions
3. Write code to temp file
4. Run `prettier --write {tmpfile}` (or `npx prettier --write {tmpfile}`)
5. Read back result
6. Return `RepairStepResult(modified=code_changed, code=result)`

**Timeout:** 15 seconds (consistent with `post_generation_cleanup()`)

**Not auto-fixable errors:** If prettier fails (exit code != 0), return `modified=False` with the original code (no rollback needed since we're working on a copy).

#### REQ-KZ-ND-902: Routing

Add `prettier_format` to `_CANONICAL_ORDER` AFTER `eslint_autofix` and BEFORE `js_syntax_validate`:

```
"eslint_autofix",
"prettier_format",   # ← new
"var_to_const",
```

Add to JS syntax repair route:
```python
("syntax", "js_syntax_error", [..."prettier_format", "js_syntax_validate"], "HIGH", "nodejs"),
```

**Do NOT add to semantic repair routes.** Prettier is cosmetic — it doesn't fix semantic issues.

#### REQ-KZ-ND-903: Relationship to `post_generation_cleanup()`

`post_generation_cleanup()` and `PrettierFormatStep` serve different lifecycle stages:

| | `post_generation_cleanup()` | `PrettierFormatStep` |
|-|----------------------------|---------------------|
| **When** | After initial generation, before repair pipeline | During repair pipeline |
| **Rollback** | No | Yes (via repair staging) |
| **Verification** | No | Yes (js_syntax_validate runs after) |
| **Metrics** | Warning strings only | `RepairStepResult` with modification tracking |

Both can run safely — prettier is idempotent. If `post_generation_cleanup()` already formatted the file, `PrettierFormatStep` will detect no changes and return `modified=False`.

---

## 5. Dependency Graph

```
REQ-KZ-ND-700 (semantic checks)     REQ-KZ-ND-900 (prettier)
  ├── 702 unused_requires (P1)          └── 901 PrettierFormatStep
  ├── 703 missing_exports (P2)          └── 902 Routing
  ├── 707 Go contamination (P2)
  ├── 704 any_type_overuse (P3)      All independent of each other.
  ├── 705 error_handling (P4)        Can be implemented in any order.
  └── 706 callback_hell (P5)
            │
            ▼
REQ-KZ-ND-800 (language-aware scoring)
  ├── 801 Dispatch interface
  ├── 802 Node.js scorer ←── depends on 700 checks existing
  └── 803 Call site wiring
```

**Critical path:** REQ-KZ-ND-802 (Node.js scorer) benefits from having the P1–P3 checks implemented first, because the scoring formula references `module_system_mixing`, `unhandled_promise`, `var_usage`, and `console_log_in_service` — all of which already exist. The PLANNED checks (P1–P5) add more categories to score against but aren't strictly required for the scorer to function.

**Independent tracks:**
- Semantic checks (700) can be implemented incrementally, one at a time
- Prettier step (900) is fully independent
- Scoring dispatch (800) can start immediately using existing 6 checks, then improve as more checks land

---

## 6. Verification Strategy

### Semantic Check Tests (REQ-KZ-ND-700)

| Test | Check | Description |
|------|-------|-------------|
| `test_unused_require_detected` | 702 | `const x = require('y')` with no reference to `x` → flagged |
| `test_unused_require_side_effect_exempt` | 702 | `require('dotenv').config()` → not flagged |
| `test_unused_require_reexport_exempt` | 702 | `const X = require('x'); module.exports = { X }` → not flagged |
| `test_unused_import_type_exempt` | 702 | `import type { X } from 'y'` → not flagged |
| `test_missing_exports_detected` | 703 | File with `function foo()` but no exports → flagged |
| `test_missing_exports_entry_exempt` | 703 | `index.js` with no exports → not flagged |
| `test_missing_exports_test_exempt` | 703 | File in `tests/` dir → not flagged |
| `test_missing_exports_config_exempt` | 703 | `jest.config.js` → not flagged |
| `test_any_overuse_warning` | 704 | `.ts` file with 4 `: any` → flagged warning |
| `test_any_overuse_error` | 704 | `.ts` file with 11 `: any` → flagged error |
| `test_any_overuse_dts_exempt` | 704 | `.d.ts` file → not flagged |
| `test_any_overuse_js_exempt` | 704 | `.js` file with `: any` → not flagged (not TypeScript) |
| `test_any_overuse_ts_ignore_exempt` | 704 | `// @ts-ignore` on same line → not counted |
| `test_error_handling_then_no_catch` | 705 | `.then(fn)` without `.catch()` → flagged |
| `test_error_handling_promise_no_reject` | 705 | `new Promise((resolve) => ...)` → flagged |
| `test_callback_hell_4_levels` | 706 | 4 nested callbacks → flagged |
| `test_callback_hell_2_levels_ok` | 706 | 2 nested callbacks → not flagged |
| `test_go_contamination_package_main` | 707 | `package main` in `.js` file → flagged |
| `test_go_contamination_fmt_println` | 707 | `fmt.Println("hello")` in `.js` file → flagged |

### Language-Aware Scoring Tests (REQ-KZ-ND-800)

| Test | Requirement | Description |
|------|------------|-------------|
| `test_generic_score_unchanged` | 801 | `compute_disk_quality_score(compliance)` without `language_id` → same result as before |
| `test_nodejs_score_clean_file` | 802 | Clean JS file → score 1.0 |
| `test_nodejs_score_contaminated` | 802 | File with `python_contamination` → score 0.0 (fatal invariant) |
| `test_nodejs_score_syntax_fail` | 802 | `ast_valid=False` → score 0.0 (fatal invariant) |
| `test_nodejs_score_mixed_modules` | 802 | `module_system_mixing` → `module_consistency=0.0`, score ≤ 0.80 |
| `test_nodejs_score_var_usage` | 802 | 2 `var_usage` warnings → convention_compliance reduced |
| `test_nodejs_score_unknown_language` | 801 | `language_id="unknown"` → falls back to generic formula |

### Prettier Step Tests (REQ-KZ-ND-900)

| Test | Requirement | Description |
|------|------------|-------------|
| `test_prettier_formats_js` | 901 | Unformatted JS → prettier fixes indentation |
| `test_prettier_idempotent` | 901 | Already-formatted JS → `modified=False` |
| `test_prettier_skips_non_js` | 901 | `.py` file → `modified=False` |
| `test_prettier_unavailable_noop` | 901 | `shutil.which("prettier") is None` → `modified=False` |
| `test_prettier_in_syntax_route` | 902 | `js_syntax_error` route includes `prettier_format` |
