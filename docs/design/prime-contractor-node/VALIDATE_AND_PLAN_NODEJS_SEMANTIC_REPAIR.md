# Prompt: Validate & Plan Node.js Semantic Repair (REQ-KZ-ND-402)

> Provide this prompt alongside `KAIZEN_NODEJS_REQUIREMENTS.md` to validate the requirements and produce an implementation plan.

---

## Context

The StartD8 SDK has a multi-language code generation pipeline (Prime Contractor) with a Kaizen quality system. The C# language has a working semantic-to-repair bridge. Java and Go have convention requirements following the same pattern.

Node.js has 6 semantic checks in `nodejs_semantic_checks.py` and compliance_results collection (just implemented), but no repair steps or dispatch. REQ-KZ-ND-402 defines the convention — all categories advisory in Phase 1; Phase 2 adds three text-based steps (`var_to_const`, `dedup_require`, `contamination_strip_js`); Phase 3 integrates `eslint --fix`.

**Node.js-specific considerations:**
- Multiple file extensions: `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx`
- CJS vs ESM module systems affect repair strategy
- External tools: `prettier`, `eslint`, `node --check`, `tsc --noEmit`
- `NodeLanguageProfile.repair_enabled = True`

## Task

### Part 1: Validate Requirements

Read REQ-KZ-ND-402 (Section 5, after REQ-KZ-ND-400) and validate against the codebase:

1. **Category inventory accuracy** — Confirm all 6 categories in `nodejs_semantic_checks.py` are listed in REQ-KZ-ND-402b. Check `check=` field string values match exactly.
2. **Classification correctness** — For each "Repairable" category, verify feasibility:
   - `var_usage`: Is `s/\bvar\b/const/` safe? What about `var` in `for (var i = 0; ...)` where `let` is correct, not `const`? Check if the regex would break reassignment patterns.
   - `duplicate_require`: Is "keep first occurrence" always correct? What if the second `require()` has a different destructuring pattern (`const {a} = require('x')` then `const {b} = require('x')`)?
   - `python_contamination`: Same concern as Go — could fingerprints match in string literals?
3. **Compliance results wiring** — Confirm REQ-KZ-ND-402c (IMPLEMENTED) by reading the Node.js block in `integration_engine.py:_run_semantic_checks()`. Verify all 6 extensions (`.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx`) are covered.
4. **Extension registration scope** — Adding 6 extensions to `_SEMANTIC_REPAIR_EXTENSIONS` is broader than other languages (C# adds 1, Go adds 1, Java adds 1). Verify the orchestrator handles all 6 correctly and doesn't have extension-specific logic that would break.
5. **ESLint fallback chain (Phase 3)** — The requirement says "falls back to Phase 2 text-based steps if eslint unavailable." Verify this fallback pattern is supported by the repair step architecture. Can a single route invoke `eslint_fix` with fallback to `var_to_const`? Or does this need two separate routes?
6. **TypeScript considerations** — `var_to_const` on `.ts` files: does `tsc --noEmit` catch `const` reassignment errors that `node --check` would miss? Is the verification step language-aware?

### Part 2: Create Implementation Plan

Produce a phased implementation plan for REQ-KZ-ND-402.

**Phase 1 deliverables (advisory-only — current state):**
- Confirm all 6 categories appear in postmortem reports
- Verify Kaizen suggestions for `console_log_in_service` in `CAUSE_TO_SUGGESTION` (the audit found this mapping exists)
- Add missing mappings for: `var_usage`, `duplicate_require`, `unhandled_promise`, `module_system_mixing`, `python_contamination`
- Test: postmortem on a `.js` file with `var x = 1;` → verify `var_usage` appears in metrics

**Phase 2 deliverables:**

1. **`VarToConstStep`** in `repair/steps/var_to_const.py`:
   - Strategy: Parse `var` declarations, replace with `const`. For `for` loop vars, use `let` instead.
   - Implementation: line-by-line regex with for-loop detection (`for\s*\(\s*var\b` → `for (let`)
   - Verification: `node --check` (JS) or `tsc --noEmit` (TS) post-repair
   - Register in `_STEP_FACTORIES` as `"var_to_const"`

2. **`DedupRequireStep`** in `repair/steps/dedup_require.py`:
   - Strategy: Track seen module specifiers. For CJS: `require('pkg')`. For ESM: `from 'pkg'` / `import 'pkg'`.
   - **Edge case:** Different destructuring from same module (`const {a} = require('x')` + `const {b} = require('x')`) should be MERGED, not deduplicated. Flag: is this feasible with regex, or should this case be skipped?
   - Verification: `node --check` post-repair
   - Register as `"dedup_require"`

3. **`ContaminationStripJsStep`** in `repair/steps/contamination_strip_js.py`:
   - Reuse Python fingerprint patterns from `nodejs_semantic_checks.py:_check_python_contamination()`
   - Remove matching lines, verify with `node --check`
   - Register as `"contamination_strip_js"`

4. **Routing entries:**
   - `("semantic", "var_usage", ["var_to_const", "js_syntax_validate"], "MEDIUM", "nodejs")`
   - `("semantic", "duplicate_require", ["dedup_require", "js_syntax_validate"], "MEDIUM", "nodejs")`
   - `("semantic", "python_contamination", ["contamination_strip_js", "js_syntax_validate"], "HIGH", "nodejs")`

5. **Bridge updates:**
   - Add `"var_usage"`, `"duplicate_require"`, `"python_contamination"` to `_REPAIRABLE_CATEGORIES`
   - Add `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx` to `_SEMANTIC_REPAIR_EXTENSIONS`
   - Add `_repair_single_nodejs_file()` to orchestrator (or generalize dispatch)

6. **Tests:**
   - Unit: `var x = 1;` → `const x = 1;`, `for (var i...)` → `for (let i...)`
   - Unit: duplicate `require('express')` → first kept, second removed
   - Unit: `def main():` in `.js` file → line removed
   - Integration: repair + `node --check` verification round-trip
   - Negative: clean `.js` file → no modifications (idempotent)

**Phase 3 deliverables:**

1. **`EslintAutoFixStep`** in `repair/steps/eslint_autofix.py`:
   - Run `eslint --fix --rule '{"no-var":"error","no-duplicate-imports":"error"}'`
   - Fall back to Phase 2 text-based steps if `shutil.which("eslint") is None`
   - Verify with `node --check` / `tsc --noEmit`

2. **Routing update:** Replace Phase 2 step names with `eslint_autofix` as primary, keep text-based as fallback in step implementation (not routing)

3. **Tests:** ESLint-based repair produces equal or better outcomes than text-based on validation corpus

## Key Files to Read

| File | Purpose |
|------|---------|
| `src/startd8/validators/nodejs_semantic_checks.py` | 6 semantic checks — verify category names and patterns |
| `src/startd8/languages/nodejs.py` | `repair_enabled`, `post_generation_cleanup()`, `stub_patterns` |
| `src/startd8/repair/semantic_bridge.py` | `_REPAIRABLE_CATEGORIES`, `translate_to_diagnostics()` |
| `src/startd8/repair/routing.py` | `_ROUTING_TABLE`, `_STEP_FACTORIES`, extension → language mapping |
| `src/startd8/repair/orchestrator.py` | `_SEMANTIC_REPAIR_EXTENSIONS`, `_repair_single_csharp_file()` (reference) |
| `src/startd8/repair/staging.py` | Atomic staging for rollback support |
| `src/startd8/repair/steps/sql_parameterize.py` | Reference repair step pattern |
| `src/startd8/contractors/integration_engine.py` | Node.js block in `_run_semantic_checks()` |
| `src/startd8/contractors/prime_postmortem.py` | `CAUSE_TO_SUGGESTION` — verify Node.js mappings |
| `tests/unit/validators/test_nodejs_semantic_checks.py` | Existing Node.js semantic check tests |
| `tests/unit/repair/test_js_repair_steps.py` | Existing JS repair step tests |
| `docs/design/prime-contractor-node/KAIZEN_NODEJS_REQUIREMENTS.md` | REQ-KZ-ND-402 requirements |
