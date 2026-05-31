# Node.js MicroPrime Requirements — Refinement & Enhancement

> **Version:** 1.3.0
> **Status:** DRAFT (post-Hayai cross-reference)
> **Date:** 2026-05-31
> **Changelog:**
>   - **1.3.0 (2026-05-31):** Production findings from prime-contractor run-005 (Next.js/TypeScript target). The v1.1 TypeScript validation (REQ-NODE-MP-300) shipped three gaps that false-failed valid code: JSX/TSX rejected by a `.ts` temp suffix (REQ-NODE-MP-303), `npx tsc` install-noise misread as a syntax error (REQ-NODE-MP-304), and a second un-wired consumer — `IntegrationCheckpoint.check_syntax()` running `node --check` on `.tsx` (REQ-NODE-MP-305). All three resolved.
>   - **1.2.0 (2026-03-24):** Post-Hayai cross-reference baseline.
> **Parent:** [REQ-MP-12xx Polyglot MicroPrime Enablement](../micro-prime/REQ-MP-12xx_POLYGLOT_MICROPRIME_ENABLEMENT.md)
> **Related:**
>   - [KAIZEN_NODEJS_REQUIREMENTS.md](KAIZEN_NODEJS_REQUIREMENTS.md) — Node.js quality measurement and feedback
>   - [GO_MICROPRIME_REQUIREMENTS.md](../prime-contractor-go/GO_MICROPRIME_REQUIREMENTS.md) — Go equivalent (template for this doc)
>   - [GO_MICROPRIME_HAYAI_AUDIT.md](../prime-contractor-go/GO_MICROPRIME_HAYAI_AUDIT.md) — Run-118 forensic methodology
>   - [MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md](../micro-prime/MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md) — Language-agnostic checklist
>   - [HAYAI_DESIGN_PRINCIPLE.md](../../design-princples/HAYAI_DESIGN_PRINCIPLE.md) — Early enforcement principle
>   - [AST_PARSE_AUDIT.md](../micro-prime/AST_PARSE_AUDIT.md) — ast.parse() quality-loss findings (v1.2)
>   - [REQ-MP-1211a/b/c](../micro-prime/REQ-MP-12xx_POLYGLOT_MICROPRIME_ENABLEMENT.md) — Language-aware stub/import/signature rendering (v1.2)
> **Language Profile:** `NodeLanguageProfile` (`src/startd8/languages/nodejs.py`)
> **Scope:** Node.js-specific MicroPrime element generation, decomposition, and repair refinement

---

## 1. Current State (Post REQ-MPL-100–105)

### What's Working

| Capability | Status | Evidence |
|-----------|--------|---------|
| Enrichment-time language resolution | DONE | `resolve_language()` maps `.js`/`.ts`/`.mjs`/`.cjs`/`.tsx`/`.jsx` → `"nodejs"` |
| Element routing (bypass gate) | DONE | `.js`/`.ts` → `_is_non_python_file()` = False |
| SIMPLE tier classification | DONE | Elements from Node.js files classified correctly |
| Language-aware system prompt | DONE | `_build_system_prompt()` dispatches by `language_id` |
| Language-aware user prompt | DONE (REQ-MPL-101) | `stub_marker_text`, indent, keyword from profile |
| Full-function mode for Node.js | DONE (REQ-MPL-102) | Non-Python forced to `full_function` |
| Pre-extraction fence strip | DONE (REQ-MPL-103) | Fences stripped before validation |
| Repair language guard | DONE (REQ-MPL-100) | `bare_statement_wrap` no-op for Node.js |
| Syntax validation (JS via `node --check`, TS/TSX via `tsc`) | DONE (v1.3) | `validate_syntax()` is the single dispatch point; `syntax_check_command` is `None` so both `_try_parse()` and `IntegrationCheckpoint.check_syntax()` defer to it (REQ-NODE-MP-303/304/305) |
| Splicer dispatch | DONE | `splice_body_into_skeleton()` → Node.js splicer wired |
| Node.js parser (regex) | DONE | `nodejs_parser.py` — functions, classes, methods, arrows, const-functions |
| Node.js splicer (brace-match) | DONE | `nodejs_splicer.py` — body replacement for functions, arrows, class methods |
| 6 Node.js templates | DONE | `_LANGUAGE_TEMPLATES["nodejs"]` registered (constructor, toString, getter, setter, async method, Express handler) |
| 6 semantic checks | DONE | `nodejs_semantic_checks.py` — console.log, var usage, dupe require, unhandled promises, contamination, module mixing |
| Post-gen cleanup (prettier) | DONE | `NodeLanguageProfile.post_generation_cleanup()` — best-effort, optional |
| Repair routes (6 routes) | DONE | syntax, import, credential, var_usage, duplicate_require, python_contamination |
| Kaizen suggestion mappings | DONE | All 6 categories wired in `_SEMANTIC_CATEGORY_TO_SUGGESTION` |
| ESM/CJS context injection | DONE | `build_project_context_section()` produces module-system-specific rules |
| package.json deterministic gen | DONE | `_try_generate_package_json()` in `prime_adapter.py` |
| File assembler | DONE | `nodejs_file_assembler.py` — skeleton generation for `.js`/`.ts` files |
| Signature parser | DONE | `nodejs_signature_parser.py` — LLM signature → `ForwardElementSpec` |

### What's Not Working (Effectiveness Gaps)

| Gap | Description | Impact | Root Cause | Status |
|-----|-------------|--------|-----------|--------|
| ~~**Python stub in prompts**~~ (REQ-MP-1211a) | ~~`_build_element_stub()` renders Python for all~~ | | `_build_non_python_stub()` at line 450 | **DONE** (pre-existing) |
| ~~**Python import rendering**~~ (REQ-MP-1211b) | ~~`_render_imports()` renders Python for all~~ | | Language dispatch at lines 573–585 | **DONE** (pre-existing) |
| ~~**Few-shot learning blocked**~~ (AST audit #1) | ~~`_is_usable_example()` rejects valid JS~~ | | Language guard at line 730 | **DONE** (pre-existing) |
| ~~**Skeleton context lost**~~ (AST audit #2) | ~~`_extract_element_context_from_skeleton()` fails on JS~~ | | Text-based extraction at line 958 | **DONE** (pre-existing) |
| ~~**Splice repair discarded**~~ (AST audit #3) | ~~`_attempt_splice_violation_repair()` discards JS~~ | | `_try_parse()` dispatch at line 254 | **DONE** (pre-existing) |
| ~~**Signature parser not wired**~~ (REQ-MP-1211c) | ~~`_parse_api_signature()` fails on JS sigs~~ | | `_parse_signatures_by_language()` at line 374 | **DONE** (pre-existing) |
| **Template granularity mismatch** | 6 Node.js templates registered but expected 0% match in file-level runs | Templates provide zero-cost generation, but can't fire | Elements are file-level modules; templates match function-level patterns | OPEN |
| **Splicer never exercised** | Node.js splicer dispatch wired but no splices expected | Incremental generation unavailable | Depends on function-level decomposition (same root cause) | OPEN |
| **Python AST decomposer bottleneck** | `FunctionBodyDecomposer` uses `ast.parse()` — can't decompose JS/TS files | Multi-function Node.js files stay as single elements | Decomposer is Python-only | OPEN |
| ~~**`sanitize_code_examples()` is a no-op**~~ | ~~Node.js profile returns text unchanged~~ | ~~Anti-patterns propagate~~ | | **DONE** (v1.1) |
| ~~**TypeScript validation gap**~~ | ~~`node --check` validates `.js` only~~ | ~~TS syntax errors undetected~~ | | **DONE** (v1.1; hardened v1.3 — see REQ-NODE-MP-303/304/305) |
| ~~**TS/TSX false-positive validation**~~ (run-005) | ~~`.tsx` JSX rejected; npx install-noise misread as syntax error; `node --check` on `.tsx` in checkpoint~~ | ~~Valid code false-failed; 50% escalation + 1 checkpoint fail~~ | `.ts` temp suffix, non-zero-exit-as-error, static `node --check` template | **DONE** (v1.3) |
| **No formatter guarantee** | Post-gen cleanup depends on `prettier` being installed | Inconsistent formatting | Node.js ecosystem doesn't ship a standard formatter | ACCEPTED RISK |
| ~~**Module system drift**~~ | ~~CJS/ESM not enforced as P0~~ | ~~Generated code may mix~~ | | **DONE** (v1.1) |

### Node.js-Unique Challenges (vs Go)

These are challenges that don't exist in the Go pipeline and require Node.js-specific solutions:

1. **Dual module system**: CJS vs ESM is a binary choice per project, unlike Go (single module system). Mixing causes runtime errors.
2. **TypeScript overlay**: `.ts`/`.tsx` files share the same language profile but need different validation tooling (`tsc` vs `node --check`).
3. **Arrow function diversity**: `const fn = () => {}`, `const fn = function() {}`, `function fn() {}`, `class X { method() {} }` — four distinct declaration patterns that parser/splicer/templates must all handle.
4. **No compiler enforcement**: Go's compiler catches unused imports and undeclared variables. Node.js has no equivalent — quality depends entirely on semantic checks and ESLint.
5. **npm version ranges**: `^`, `~`, `>=` semantics are complex. package.json generation must produce valid ranges.
6. **Callback legacy**: Older Node.js patterns use callbacks; modern code uses async/await. Generated code must use async/await consistently.

---

## 2. Phase 0.5: Prompt Quality Fixes — AST Parse Audit + Polyglot Rendering (REQ-NODE-MP-900)

> **Added in v1.2. ALL ITEMS ALREADY IMPLEMENTED** — code inspection during implementation planning revealed that the AST Parse Audit findings and REQ-MP-1211a/b/c were fixed in the same session that produced the audit docs. The fixes are present in the current codebase. These requirements are retained for traceability and verification.
>
> **Hayai assessment:** All items below are at contamination distance 0 — resolved.

### Problem

Four `ast.parse()` calls in `prompt_builder.py` and `engine.py` silently degrade Node.js prompt quality by rejecting valid JS/TS code. Additionally, two prompt rendering functions produce Python syntax for all languages. The combined effect: **Node.js elements receive prompts with Python stubs, Python imports, no few-shot examples, and no skeleton context** — even though all the infrastructure to produce correct Node.js prompts already exists.

### REQ-NODE-MP-900: Few-Shot Example Validation (AST Audit P0 #1) — DONE

**File:** `prompt_builder.py:581` (`_is_usable_example()`)

`ast.parse(code_example)` rejects valid Node.js as "unusable" → zero few-shot learning for Node.js elements.

**Fix:** Accept `language_id` parameter. For non-Python, skip `ast.parse()` validation — the code was already validated by `node --check` or `gofmt` during generation. Optionally call `LanguageProfile.validate_syntax()` for defense-in-depth.

**Acceptance criteria:**
- A successfully-generated Node.js function body IS used as a few-shot example for subsequent elements in the same file
- Python behavior unchanged

### REQ-NODE-MP-901: Skeleton Context Extraction (AST Audit P0 #2) — DONE

**File:** `prompt_builder.py:785` (`_extract_element_context_from_skeleton()`)

`ast.parse(skeleton)` fails for Node.js → `return None, None, []` → element loses skeleton context section.

**Fix:** For non-Python skeletons, use the language's own parser:
- Node.js: `nodejs_parser.py:parse_nodejs_source()` to extract surrounding functions, class structure
- Fallback: text-based heuristic (regex for `function`/`class`/`const` declarations with line ranges)

**Acceptance criteria:**
- Node.js elements receive skeleton context showing surrounding function signatures
- Prompt includes the target function's position relative to other functions in the file
- Python skeleton context unchanged

### REQ-NODE-MP-902: Splice Repair Validation (AST Audit P1 #3) — DONE

**File:** `engine.py:251` (`_attempt_splice_violation_repair()`)

`ast.parse(result.code)` on spliced Node.js code → fails → repair silently discarded.

**Fix:** Language dispatch — use `LanguageProfile.validate_syntax()` for non-Python, `ast.parse()` for Python.

**Acceptance criteria:**
- Valid Node.js splice repairs are accepted (not silently reverted)
- Invalid splices still caught and reverted
- Python behavior unchanged

### REQ-NODE-MP-910: Language-Aware Element Stub Rendering (REQ-MP-1211a) — DONE

**File:** `prompt_builder.py:390–435` (`_build_element_stub()`)

Currently renders **Python syntax for all languages**:
```
def handler(req, res):
    raise NotImplementedError
```

When the instructions (from REQ-MPL-101) say "`function` declaration", but the stub shows `def` — the LLM resolves a contradiction. This is the Hayai precedence problem described in the [Hayai Design Principle](../../design-princples/HAYAI_DESIGN_PRINCIPLE.md): early binding eliminates precedence problems entirely.

**Fix:** Add `render_element_stub(element, language_profile)` method to each LanguageProfile, or dispatch by `language_id` in `_build_element_stub()`:

| Language | Stub Output |
|----------|------------|
| Node.js (function) | `function handler(req, res) { throw new Error("not implemented"); }` |
| Node.js (arrow) | `const handler = (req, res) => { throw new Error("not implemented"); };` |
| Node.js (class method) | `handleRequest(req, res) { throw new Error("not implemented"); }` |

**Acceptance criteria:**
- Node.js elements see `function`/`const`/`=>` syntax in the prompt stub
- Stub uses `throw new Error("not implemented")` (from `stub_marker_text`)
- Parameters rendered in JS syntax (`req, res`), not Python syntax (`req: Request, res: Response`)
- Python behavior unchanged

### REQ-NODE-MP-911: Language-Aware Import Rendering (REQ-MP-1211b) — DONE

**File:** `prompt_builder.py:456–466` (`_render_imports()`)

Currently renders all imports as Python `import X` / `from X import Y`. Node.js needs:

| Module System | Rendered Import |
|--------------|----------------|
| CJS | `const express = require('express');` |
| CJS (destructured) | `const { Router } = require('express');` |
| ESM | `import express from 'express';` |
| ESM (named) | `import { Router } from 'express';` |

**Fix:** Dispatch by `language_id` in `_render_imports()`. Use `NodeLanguageProfile.extract_import_lines()` pattern as reference for the target syntax. Module system (CJS/ESM) available from seed context.

**Acceptance criteria:**
- Node.js prompts show `require()`/`import from` syntax matching the project's module system
- Python behavior unchanged

### REQ-NODE-MP-920: Signature Parser Wiring in Plan Ingestion (REQ-MP-1211c) — DONE

**File:** `plan_ingestion_micro_ingest.py:127–251` (`_parse_api_signature()`)

`ast.parse()` on Node.js signatures → `SyntaxError` → `None` → all Node.js elements routed to Tier 3 (cloud escalation). Meanwhile `nodejs_signature_parser.py` exists and handles 80% of patterns but is **never imported or called**.

**Hayai diagnosis:** The language is known at plan ingestion time (REQ-TDE-200 persists `language_id` in seed context). The parser exists. The knowledge to route correctly is available at the earliest stage. Contamination distance = 3+ stages (plan ingestion → spec → draft → generation tier assignment).

**Fix:** Dispatch `_parse_api_signature()` by `language_id`:
```python
if language_id == "nodejs":
    return nodejs_signature_parser.parse_nodejs_signatures(signature_text)
```

**Acceptance criteria:**
- Node.js function signatures produce valid `ForwardElementSpec` with `Signature(params=[...])`
- Node.js elements classified at Tier 0–2 (local generation) based on complexity, not always Tier 3
- Python behavior unchanged

---

## 2b. Phase 1: sanitize_code_examples() Implementation (REQ-NODE-MP-100)

### Problem

The Node.js `sanitize_code_examples()` is a no-op. Plan descriptions, design docs, and reference implementations may contain anti-patterns that propagate into specs unchanged. The Go profile transforms `fmt.Println` → `slog.Info`; Node.js needs equivalent transforms.

### REQ-NODE-MP-100: Node.js Code Example Sanitization

Implement transforms for common Node.js anti-patterns in plan/design text:

| Pattern | Replacement | Rationale |
|---------|-------------|-----------|
| `console.log(...)` | `logger.info(...)` | Production code should use structured logging |
| `console.error(...)` | `logger.error(...)` | Same |
| `console.warn(...)` | `logger.warn(...)` | Same |
| `var x = ...` | `const x = ...` | `var` is deprecated in modern JS |

**Removed from v1.0 (infeasible at this layer):**
- ~~`require('...')` in ESM context → `import`~~ — `sanitize_code_examples()` receives plain text with no module system context. Module system enforcement belongs in `build_project_context_section()` (REQ-NODE-MP-200) and coding standards, which DO have context.
- ~~`callback(err, result)` → `async/await`~~ — Callback patterns are structural; regex can't reliably transform them without producing invalid syntax. Handled by coding standards + P0 constraint (REQ-NODE-MP-201) instead.

**Scope:** Same approach as Go (`go.py:128–144`): conservative regex transforms applied to all text. No code-block protection (Go doesn't have it either — the transforms are simple enough that false positives in fenced blocks are rare and harmless). Prefer false negatives over false positives.

**Hayai value:** This is defense-in-depth for the `console_log_in_service` and `var_usage` semantic checks. Semantic checks catch anti-patterns in generated code (Stage 8); sanitize catches them in PLAN TEXT before they reach the LLM (Stage 1). Together they reduce contamination distance to zero — the anti-pattern is fixed at the earliest stage where it can be resolved.

**Implementation:**
- In `NodeLanguageProfile.sanitize_code_examples()`, apply 4 regex transforms using `re.sub()` with `([^)]*)` argument capture (same pattern as Go's `fmt.Println` transform)
- Order: `console.error` → `console.warn` → `console.log` → `var` (most specific first)

**Acceptance criteria:**
- `sanitize_code_examples("Use console.log for logging")` → `"Use logger.info for logging"`
- `sanitize_code_examples("var count = 0")` → `"const count = 0"`
- `sanitize_code_examples("logger.info('already clean')")` → unchanged
- Plan text with `console.log` references produces spec with `logger.info`

### REQ-NODE-MP-101: Sanitization Test Coverage

- Unit tests for each transform (positive + negative cases)
- Integration test verifying transforms propagate through enrichment pipeline
- Clean-code-unchanged test (no false positive on `logger.info`)
- Multiline transform test (multiple patterns in same text)

---

## 3. Phase 2: Module System Enforcement (REQ-NODE-MP-200)

### Problem

CJS/ESM mixing is the #1 Node.js quality defect — a single `require()` in an ESM module causes a runtime crash. The coding standards mention it, but the information flows as general guidance, not as a P0 hard constraint.

### REQ-NODE-MP-200: P0 Module System Constraint

Elevate module system consistency from coding standards to a **P0 constraint**.

**Planning insight — no new method needed:** The existing injection paths already provide P0 priority:
1. `coding_standards` property → injected at P0 in `spec_builder.py:1259–1275` (never dropped by budget)
2. `build_project_context_section()` → injected at P0 in `spec_builder.py:1174–1179`
3. Drafter system prompt → `coding_standards` placeholder in YAML template

A new `get_p0_constraints(context)` method would require new plumbing in spec_builder and drafter. Instead, strengthen the existing text to make constraints unmissable.

**Implementation (two changes, zero new plumbing):**

1. **`coding_standards` property** — prepend CRITICAL block before general standards:
   ```
   CRITICAL NODE.JS CONSTRAINTS (violations cause runtime crashes):
   - MODULE SYSTEM: Use ONE module system consistently per file and project.
     If ESM: ONLY `import`/`export`. If CJS: ONLY `require()`/`module.exports`.
     NEVER mix — a single `require()` in an ESM module crashes at runtime.
   - ASYNC: Use async/await for ALL asynchronous operations.
     Wrap async calls in try/catch. NEVER leave a Promise unhandled —
     unhandled rejections crash Node.js in production.
   ```

2. **`build_project_context_section()`** — add CRITICAL preamble reinforcing the specific module system choice:
   ```
   **CRITICAL: This project uses {ESM/CJS}. Generate ONLY {import/require} syntax.
   Mixing module systems causes immediate runtime failure.**
   ```
   Also add ESM-specific: "File extensions REQUIRED in relative imports: `import X from './util.js'`" — this is a common LLM failure mode that causes `ERR_MODULE_NOT_FOUND` at runtime.

**Acceptance criteria:**
- Run with P0 constraint produces zero `module_system_mixing` semantic findings (vs baseline)
- Constraint survives budget enforcement (P0 = never dropped)
- ESM project generates only `import`/`export`; CJS project generates only `require`/`module.exports`
- Python/Go/Java/C# unaffected

### REQ-NODE-MP-201: Async/Await Enforcement

Add a secondary P0 constraint for async patterns:

```
CRITICAL NODE.JS CONSTRAINT: Use async/await for ALL asynchronous operations.
NEVER use raw callbacks (err, result). NEVER use .then().catch() chains unless
composing multiple promises with Promise.all(). Every async function call must
be awaited or explicitly collected in Promise.all(). Unhandled promise rejections
crash Node.js in production.
```

**Acceptance criteria:**
- Generated code uses `await` for all async calls
- No callback-style patterns in generated code
- `unhandled_promise` semantic findings decrease

---

## 4. Phase 3: TypeScript Validation (REQ-NODE-MP-300)

### Problem

`NodeLanguageProfile.validate_syntax()` writes code to a `.js` tempfile and runs `node --check`. This works for JavaScript but silently accepts invalid TypeScript (type annotations, generics, interfaces are valid TS but invalid JS). When generating `.ts` files, syntax errors in TypeScript-specific constructs go undetected.

### REQ-NODE-MP-300: TypeScript Syntax Validation

Add TypeScript-aware validation path in `validate_syntax()`:

**Detection:**
- If the source contains TypeScript indicators (`: string`, `interface`, `<T>`, `as const`, `type X =`), use TS validation
- OR if the caller provides a filename hint ending in `.ts`/`.tsx`

**Validation options (priority order):**
1. `tsc --noEmit --isolatedModules --skipLibCheck` on a temp file — `--isolatedModules` validates syntax without resolving imports (no node_modules needed); `--skipLibCheck` avoids failing on missing `.d.ts` files. This catches TS-specific SYNTAX errors (malformed type annotations, invalid generics) which is the actual gap. Full type checking (`--strict`) would require a working project context which doesn't exist during element validation. **The temp file suffix and `--jsx` flag depend on whether the code is JSX — see REQ-NODE-MP-303.**
2. `npx --no-install tsc --noEmit --isolatedModules --skipLibCheck` fallback (slower, uses npx resolution; `--no-install` prevents network downloads). **A non-zero exit is only a failure when it carries a real `error TS####` diagnostic — see REQ-NODE-MP-304.**
3. Best-effort pass: return `(True, "")` when tsc unavailable (same pattern as `node --check` when node missing)

**Implementation:**
```python
def validate_syntax(self, code: str, *, filename_hint: str = "") -> tuple[bool, str]:
    is_ts = filename_hint.endswith((".ts", ".tsx")) or _looks_like_typescript(code)
    if is_ts:
        return self._validate_typescript(code, filename_hint=filename_hint)  # thread hint (REQ-NODE-MP-303)
    return self._validate_javascript(code)
```

**Note on protocol compatibility:** The `LanguageProfile` protocol defines `validate_syntax(self, code: str) -> tuple[bool, str]`. Adding `filename_hint` as a keyword-only argument is backward compatible — existing callers that don't pass it get heuristic detection. New callers (like `_try_parse()`) can pass the hint for accurate dispatch.

**Acceptance criteria:**
- `.ts` files with syntax errors caught (e.g., malformed type annotation `const x: = 5`)
- `.js` files still validated via `node --check` (no regression)
- Graceful fallback when `tsc` is not installed (return True, same as Go when `gofmt` missing)
- `_try_parse()` in `repair.py` dispatches to TS validation for `.ts` extensions (see REQ-NODE-MP-302)

### REQ-NODE-MP-301: TypeScript Repair Route

Add a TS-specific repair route for TypeScript syntax errors:

| Category | Pattern | Steps | Language |
|----------|---------|-------|----------|
| syntax | `ts_syntax_error` | fence_strip, shebang_strip, todo_uncomment, js_syntax_validate | nodejs |

The `js_syntax_validate` step should detect `.ts` and use TypeScript validation internally.

### REQ-NODE-MP-302: `_try_parse()` Filename Threading (Cross-Cutting)

**Planning-derived insight:** TypeScript validation is useless if `_try_parse()` in `repair.py` can't tell `validate_syntax()` that the file is `.ts`. Currently `_try_parse()` calls `validate_syntax(code)` without a filename hint — all Node.js files get JS validation regardless of extension.

**Implementation:** Thread the file path through `_try_parse()` → `validate_syntax(code, filename_hint=file_path)`. The file path is available in the repair pipeline context (`element.file_path` or the `file_spec.path`).

**Scope:** This is a small change (~3 lines) but without it REQ-NODE-MP-300 has zero effect in the actual pipeline. It's the wiring that connects TS detection to TS validation.

**Acceptance criteria:**
- `_try_parse()` called with a `.ts` file path dispatches to `_validate_typescript()`
- `_try_parse()` called with a `.js` file path dispatches to `_validate_javascript()` (no regression)

---

## 4b. Phase 3 Hardening: Production Findings from run-005 (v1.3)

**Context:** prime-contractor `run-005` (Next.js 14 + TypeScript target, Node v26, TypeScript not installed in the sandbox) exposed three defects in the v1.1 TypeScript-validation implementation. All three were **false positives on valid code** — the local Ollama model's output was correct; the validator rejected it. Symptoms: one INTEGRATE checkpoint failure (`app/layout.tsx`) and a 50% MicroPrime escalation rate (`env` + `layout` elements, `ast_failure`). See [the run-005 post-mortem](../../../) (`pipeline-output/startd8/run-005-*/plan-ingestion/prime-postmortem-report.json`).

### REQ-NODE-MP-303: JSX/TSX Validation

**Problem:** REQ-NODE-MP-300 option 1 specified writing TS code to a temp **`.ts`** file. `tsc` only parses JSX in files with a `.tsx` extension, and only when `--jsx` is set. A valid `app/layout.tsx` (React/Next.js) written to a `.ts` temp therefore fails with *"Cannot use JSX unless the '--jsx' flag is provided"* — a false syntax error. (In run-005 the npx-noise gap, REQ-NODE-MP-304, masked this; it would surface in any environment where TypeScript *is* installed, e.g. CI.)

**Requirement:** When the file is `.tsx`/`.jsx` (by `filename_hint`) **or** the code contains JSX markup, `_validate_typescript()` MUST:
- write the temp file with a `.tsx` suffix, and
- pass `--jsx preserve` to `tsc`.

JSX detection uses a conservative `_looks_like_jsx()` heuristic (matched tag-pair, self-closing tag, or fragment) so JSX without a filename hint still routes correctly. It MUST NOT match TypeScript generics (`a < b`, `Array<T>`).

**Acceptance criteria:**
- Valid `.tsx`/JSX returns `(True, "")` when tsc is installed.
- `_looks_like_jsx("return (<div><span>x</span></div>)")` is `True`; `_looks_like_jsx("const x: number = a < b ? 1 : 2")` is `False`.
- The `tsc` command for a `.tsx` file contains `--jsx` and targets a `.tsx` temp.

### REQ-NODE-MP-304: Toolchain-Noise Discrimination

**Problem:** REQ-NODE-MP-300 option 3 ("best-effort pass when tsc unavailable") only covered tsc being *fully absent* (`FileNotFoundError`, i.e. no `npx`). When `npx` exists but TypeScript is **not installed**, `npx tsc` runs and exits non-zero with an install prompt (`"This is not the tsc command you are looking for"`). The v1.1 implementation treated any non-zero exit as a syntax error, so **every** `.ts`/`.tsx` element false-failed and escalated — the direct cause of run-005's 50% escalation rate on valid code.

**Requirement:** A non-zero `tsc` exit is a syntax failure **only** when its combined output contains a genuine compiler diagnostic matching `error TS\d+`. Output lacking that signature is toolchain noise and MUST degrade to a best-effort PASS `(True, "")`. The npx invocation MUST use `--no-install` so it fails fast instead of attempting a network download during validation.

**Acceptance criteria:**
- npx install-noise (no `error TS####`) → `(True, "")`, no escalation.
- A real `error TS1005` diagnostic → `(False, <diagnostic>)`.
- No network access is attempted during validation.

### REQ-NODE-MP-305: Checkpoint Syntax-Check Dispatch (second consumer)

**Problem:** REQ-NODE-MP-302 wired the *repair* path (`_try_parse()`) to thread the filename, but there is a **second** consumer of syntax validation: `IntegrationCheckpoint.check_syntax()` (INTEGRATE / post-merge). It used `LanguageProfile.syntax_check_command` — a static `node --check {file}` template — run against the file on disk with its **real** extension. On Node ≥ 23, `node --check foo.tsx` raises `ERR_UNKNOWN_FILE_EXTENSION` (the ESM loader rejects `.tsx`/`.jsx` before parsing). In run-005 this marked a valid `app/layout.tsx` as a checkpoint failure, independent of the MicroPrime path. (`.ts` passed because Node ≥ 23 natively strips `.ts` types; `.tsx` needs a *transform*, not just stripping.)

**Requirement:**
- `NodeLanguageProfile.syntax_check_command` MUST return `None`, so the static, extension-blind template is never run. All Node syntax checking flows through the extension-aware `validate_syntax()`.
- `IntegrationCheckpoint.check_syntax()` MUST, when `syntax_check_command is None`, call `validate_syntax(code, filename_hint=<file name>)`, passing the hint **signature-safely** (only `nodejs`/`vue` accept the kwarg; others retain the `(code)` protocol signature).

**Rationale (robustness — why "return None" over "special-case in checkpoint"):** Returning `None` removes the false capability claim *at the source*, so every consumer — checkpoint today, any future caller — gets correct behavior. Special-casing `.tsx`/`.jsx` inside the language-agnostic checkpoint would patch one call site, leave the misleading `node --check {file}` template as a latent landmine, and push language-specific extension knowledge into the wrong layer.

**Acceptance criteria:**
- `NodeLanguageProfile().syntax_check_command is None`.
- `IntegrationCheckpoint(...).check_syntax([Path("app/layout.tsx")])` passes for a valid layout.
- `.js`/`.mjs`/`.cjs` files still validate (via `_validate_javascript` → `node --check` on a temp file) — no regression.

---

## 5. Phase 3.5: Import Hoisting for Node.js (REQ-NODE-MP-350)

**Planning-derived insight — missing from v1.0:** `_hoist_leading_imports()` in `repair.py:271–317` only recognizes Python `import`/`from` syntax (line 288). Node.js `const X = require('...')` lines are NOT recognized as imports and would be trapped inside function bodies during `bare_statement_wrap`. This is a Python leakage vector that the Stage 7.5 audit table identified as "VERIFY" (checkpoint 7.5.6) but no requirement addressed.

**Note:** ESM `import X from '...'` is partially covered because it starts with `import ` which the existing check matches. But CJS `const X = require('...')` and destructured `const { X } = require('...')` are completely missed.

### REQ-NODE-MP-350: Node.js Import Recognition in `_hoist_leading_imports()`

**File:** `src/startd8/micro_prime/repair.py` (line 288)

Add a Node.js-aware import pattern when `_current_repair_language_id == "nodejs"`:

```python
_JS_IMPORT_RE = re.compile(r'^(?:const|let|var)\s+(?:\w+|\{[^}]*\})\s*=\s*require\s*\(')

# In _hoist_leading_imports(), after the existing check:
if lstripped.startswith(("import ", "from ")):
    hoisted.append(lstripped)
    first_body_idx = i + 1
elif _current_repair_language_id == "nodejs" and _JS_IMPORT_RE.match(lstripped):
    hoisted.append(lstripped)
    first_body_idx = i + 1
```

**Acceptance criteria:**
- `const X = require('pkg')` hoisted
- `const { X, Y } = require('pkg')` hoisted
- `import X from 'pkg'` hoisted (already works via `"import "` prefix)
- Non-import `const` lines NOT hoisted (e.g., `const x = 5`)

---

## 6. Phase 4: Node.js Function-Level Decomposition (REQ-NODE-MP-400)

> **DC-4 is now MET:** The polyglot enablement doc's constraint DC-4 ("Node.js MUST NOT be enabled until a splicer exists") is satisfied — `nodejs_splicer.py` exists and is wired at `splicer.py:191–192` (`_splice_nodejs_dispatch()`). This means **Node.js can be enabled for SIMPLE tier**, not just TRIVIAL. The decomposer is the remaining blocker for function-level generation, not the splicer.

### Problem

Same as Go (REQ-GO-MP-300): the SIMPLE decomposer uses Python `ast.parse()` and can't decompose JS/TS files. The Node.js parser (`nodejs_parser.py`) extracts functions, classes, methods, and arrow functions, but isn't wired as a decomposer. This means:
- Templates can't match individual functions (they see "server" not "createServer" + "handleRequest" + "startListening")
- Splicer can't insert individual function bodies
- No per-function validation

### REQ-NODE-MP-400: Node.js Decompose Strategy

Implement `NodeDecomposeStrategy` that uses `nodejs_parser.py` to break a JS/TS file into individual function/method elements.

**Input:** A `ForwardFileSpec` with a single file-level element + the Node.js skeleton source.

**Output:** A `DecompositionPlan` with one `SubElement` per function/method/arrow-function in the skeleton.

**Algorithm:**
1. Parse skeleton with `parse_node_source(skeleton)` → list of `NodeElement`
2. Filter to functions/methods/arrows with stub bodies (`throw new Error("not implemented")` or `// TODO`)
3. Create `ForwardElementSpec` per stub:
   - `name`: function/variable name
   - `kind`: `FUNCTION` or `METHOD`
   - `parent_class`: class name (for methods) or None
   - `signature`: from `NodeElement.signature`
4. Handle Node.js-specific patterns:
   - Arrow functions: `const handler = (req, res) => { ... }` → element name = `handler`
   - Class methods: `class Server { start() { ... } }` → element name = `start`, parent = `Server`
   - Default exports: `export default function main() { ... }` → element name = `main`
5. **Arrow function `ElementKind` mapping** (Node.js-unique challenge): Arrow functions (`const fn = () => {}`) are variable declarations with function values. The `nodejs_parser.py` extracts them as `kind="const_function"`. The decomposer must map this to `ElementKind.FUNCTION` in the `ForwardElementSpec` — not `ElementKind.VARIABLE` (which would skip template matching and splicer routing). Document this mapping explicitly.
6. Return plan with ordered sub-elements

**Dependencies:**
- `nodejs_parser.py` — already extracts functions, classes, methods, arrows, const-functions
- `nodejs_splicer.py` — already handles body replacement for all declaration patterns
- `nodejs_splicer.py:_is_stub_body()` — already detects stub bodies (via `stub_patterns`)

**Acceptance criteria:**
- A JS file with 5 functions produces 5 `ForwardElementSpec` objects
- Arrow functions decomposed correctly (the main Node.js-specific challenge)
- Class methods decomposed with correct parent class
- The decomposition plan is consumed by the element generation pipeline

### REQ-NODE-MP-401: Decomposer Language Dispatch

Add Node.js dispatch to the decomposer selection in `engine.py`:

```python
if language_id == "nodejs":
    strategy = NodeDecomposeStrategy(node_parser, node_splicer)
elif language_id == "go":
    strategy = GoDecomposeStrategy(go_parser, go_splicer)
elif language_id == "python":
    strategy = ClassDecomposeStrategy(...)  # existing
```

**Prerequisite:** REQ-MP-1221 (language dispatch in decomposer) from the polyglot enablement doc.

### REQ-NODE-MP-402: Per-Function Generation with Node.js Splicer

After decomposition, each sub-element goes through:
1. Template match attempt (existing 6 + new templates from REQ-NODE-MP-500)
2. If no match: local LLM generation (Ollama with Node.js system prompt)
3. Validate generated body with `node --check` (or `tsc` for `.ts`)
4. Splice into skeleton with Node.js splicer
5. Run `prettier --write` on the assembled file (if available)
6. Final `node --check` validation

**Acceptance criteria:**
- A file with 5 stubs generates 5 independent LLM calls
- Arrow function bodies spliced correctly (the tricky case: brace matching after `=>`)
- Class methods spliced into correct class body
- ESM/CJS imports consistent across all spliced functions
- Cost per element significantly lower than file-whole generation

---

## 7. Phase 5: Template Coverage Expansion (REQ-NODE-MP-500)

### Problem

The 6 existing Node.js templates match narrow patterns:

| Template | Pattern | Expected Match Rate |
|----------|---------|---------------------|
| `js_constructor` | `constructor` in class | Low — many classes use inline construction |
| `js_tostring` | `toString` method | Very low |
| `js_getter` | `getName` | Low — JS often uses property access, not getters |
| `js_setter` | `setName` | Low |
| `js_async_method` | `*Async` or async decorator | Medium — depends on naming convention |
| `js_express_handler` | `get`/`post`/`put`/`delete`/`handle` | Medium — only in Express/HTTP projects |

The templates are correctly designed for function-level elements. They'll start matching when decomposition (Phase 4) breaks multi-function files into individual functions. Additional Node.js-specific patterns can increase coverage.

### REQ-NODE-MP-500: Node.js File-Level Templates

Add templates for common Node.js file archetypes matchable at file-level (before decomposition):

| Template | Match Condition | Generates |
|----------|----------------|-----------|
| `js_test_file` | Element name contains `test` or `spec`, target file is `*.test.js`/`*.spec.js`/`*.test.ts` | Test skeleton with `describe`/`it` blocks (Jest/Mocha pattern) or `test()`/`expect()` (Node.js test runner) |
| `js_grpc_server` | Element name contains `server` AND design_doc mentions `gRPC` | gRPC server bootstrap with `@grpc/grpc-js`: `new grpc.Server()`, `server.addService()`, `server.bindAsync()` |
| `js_express_app` | Element name is `app` or `server` AND design_doc mentions `Express` or `REST` | Express app: `const app = express()`, middleware chain, `app.listen()` |
| `js_middleware` | Element name contains `middleware` or `Middleware` | Express middleware: `(req, res, next) => { ...; next(); }` |
| `js_worker` | Element name contains `worker` AND design_doc mentions `worker` | Worker thread: `const { parentPort, workerData } = require('worker_threads')` pattern |
| `js_index_reexport` | Target file is `index.js`/`index.ts` AND multiple sibling modules exist | Re-export barrel: `export { X } from './x.js'` for each sibling module |

**Module system context access (planning-derived insight):** Template match/render functions receive `(ForwardElementSpec, ForwardFileSpec, list[InterfaceContract])`. None of these carry module system context. Two options:
1. **Infer from file extension:** `.mjs` → ESM, `.cjs` → CJS, `.js` → default to ESM (from `ForwardFileSpec.path`)
2. **Infer from skeleton content:** If skeleton contains `import` → ESM, if `require` → CJS (from skeleton source available via file_spec)

Option 1 is simpler and handles 90% of cases. Templates should default to ESM (modern Node.js) and only emit CJS when the target file is explicitly `.cjs`.

**Acceptance criteria:**
- Templates produce valid JS/TS passing `node --check` (or `tsc` for `.ts`)
- Templates emit ESM syntax by default; CJS only for `.cjs` files
- Template bodies use `throw new Error("not implemented")` stubs for business logic
- Each template includes correct import block for its pattern
- Templates registered in `_LANGUAGE_TEMPLATES["nodejs"]`

### REQ-NODE-MP-501: Node.js Template Test Coverage

Each new template requires:
- Unit test for match function (positive + negative cases)
- Unit test for render function (output validates via `node --check`)
- Module system test: template renders correctly in both ESM and CJS modes
- Integration test showing template match during a SIMPLE element processing

---

## 8. Phase 6: package.json Assembly Enhancement (REQ-NODE-MP-600)

### Problem

`_try_generate_package_json()` in `prime_adapter.py` produces deterministic package.json files, but coverage is limited:
- Version ranges default to `*` for unversioned deps (unsafe for production)
- `scripts` section not populated (no `start`, `test`, `build` entries)
- `type` field not set (ESM vs CJS ambiguity)
- Dev dependencies not separated from runtime dependencies

### REQ-NODE-MP-600: Comprehensive package.json Assembly

Enhance `_try_generate_package_json()`:

1. **Module system declaration:**
   - If `module_system == "esm"`, set `"type": "module"`
   - If `module_system == "commonjs"`, omit `type` field (Node.js default)

2. **Version resolution priority:**
   - Explicit `name@version` from seed → use exact version
   - Framework imports from `NodeLanguageProfile.framework_imports` → use known-good versions
   - Fallback: `"*"` → `"latest"` (safer for `npm install`)

3. **Scripts section:**
   - `"start"`: derive from entry point (`node index.js` or `node src/index.js`)
   - `"test"`: `"node --test"` (Node.js 20+) or `"jest"` if jest detected
   - `"build"`: `"tsc"` if TypeScript, omit otherwise

4. **Dependency separation:**
   - Runtime deps → `dependencies`
   - TypeScript, test frameworks → `devDependencies`

5. **Engine constraint:**
   - `"engines": { "node": ">= {node_version}" }` from service metadata

**Acceptance criteria:**
- ESM projects get `"type": "module"` in package.json
- Dependencies have version ranges (no `*`)
- Scripts section includes at least `start` and `test`
- package.json passes `npm install` validation
- Cost savings: all package.json generation is zero LLM cost

---

## 9. Python Leakage Audit (Stage 7.5 — Node.js Specific)

The REQ-MPL-100–105 fixes are language-agnostic. However, Node.js has specific leakage vectors to verify:

| # | Checkpoint | Grep Pattern | What to Verify | Status (verified during planning) |
|---|-----------|-------------|----------------|-----------------|
| 7.5.1 | `_detect_definition_line()` recognizes JS/TS | `grep -n '"function "' repair.py` | `function`, `const`, `class`, `async function`, `=>` recognized as declarations | **DONE** — `repair.py:244–248` includes `"function "`, `"export "`, `"async function "`. Arrow functions (`const x = () =>`) are NOT in the startswith list but are covered by `"export "` prefix when exported. Non-exported arrows are a gap but harmless (full_function mode means `_detect_definition_line` is informational, not gating). |
| 7.5.2 | `render_def_line()` unreachable for Node.js | n/a | REQ-MPL-102 forces `full_function` for non-Python; `render_def_line()` is body-only path | **OK** (bypassed) |
| 7.5.3 | Element prompts use `throw new Error("not implemented")` | Check `prompt_builder.py` | Profile's `stub_marker_text` used instead of hardcoded `raise NotImplementedError` | **DONE** (REQ-MPL-101) — `prompt_builder.py:211–212` uses `language_profile.stub_marker_text` |
| 7.5.4 | Indentation uses 2-space (JS convention) | Check `prompt_builder.py` | Node.js should get 2-space indent instruction, not Python 4-space | **GAP** — `prompt_builder.py:260–261` falls through to Python-style `{indent_spaces} spaces` with no Node.js-specific branch. Fixed by REQ-NODE-MP-700. |
| 7.5.5 | `ast.parse()` not called on `.js`/`.ts` files | Check validation paths | `_try_parse()` dispatches to `node --check`, not `ast.parse()` | **DONE** |
| 7.5.6 | `_hoist_leading_imports()` handles Node.js syntax | Check `repair.py` | `const X = require('...')` and `import X from '...'` recognized as import lines | **GAP** — `repair.py:288` only matches `"import "` and `"from "` prefixes. ESM `import X from` works but CJS `const X = require(...)` is completely missed. Fixed by REQ-NODE-MP-350. |
| 7.5.7 | `shebang_strip` fires for JS files | Check repair routing | Python shebangs (`#!/usr/bin/env python`) removed from JS files | **DONE** (dedicated step) |

### REQ-NODE-MP-700: Indentation Profile Property

Add `indent_style` property to `NodeLanguageProfile`:

```python
@property
def indent_size(self) -> int:
    return 2  # JS/TS community standard

@property
def indent_char(self) -> str:
    return " "  # spaces, not tabs (unlike Go)
```

Wire into `prompt_builder.py` so element prompts say "Use 2-space indentation" for Node.js (instead of Python's 4-space or Go's tabs).

---

## 10. Observability & Kaizen Integration

### REQ-NODE-MP-800: Node.js MicroPrime Metrics

Extend MicroPrime OTel metrics with Node.js-specific dimensions:

| Metric | Labels | Purpose |
|--------|--------|---------|
| `microprime.element.generation.count` | `language=nodejs, tier=SIMPLE, result={success\|escalation}` | Track Node.js local generation success rate |
| `microprime.element.template.match` | `language=nodejs, template={name}` | Track which Node.js templates fire |
| `microprime.element.splice.count` | `language=nodejs, result={success\|failure}` | Track Node.js splicer usage |
| `microprime.element.module_system` | `language=nodejs, system={esm\|cjs}` | Track module system distribution |
| `microprime.element.decomposition.count` | `language=nodejs, strategy={NodeDecomposeStrategy}` | Track decomposition when Phase 4 lands |
| `microprime.element.ts_validation` | `language=nodejs, validator={tsc\|node_check\|heuristic}` | Track TS vs JS validation path |

### REQ-NODE-MP-801: Node.js Quality Feedback Loop

Track per run:
- `module_system_mixing` count (trend should reach and stay at 0)
- `console_log_in_service` count (trend should decrease with sanitization)
- `var_usage` count (trend should decrease with sanitization)
- Template match rate (should increase as templates and decomposition improve)
- Correlation between P0 module system constraint and module mixing findings

---

## 11. Playbook Compliance Status

Current Node.js status against the [MicroPrime Language Enablement Playbook](../micro-prime/MICROPRIME_LANGUAGE_ENABLEMENT_PLAYBOOK.md):

| Stage | Checkpoint | Node.js Status |
|-------|-----------|---------------|
| 0 (Foundation) | 0.1–0.5 | All DONE |
| 0 (Foundation) | 0.6 sanitize_code_examples() | **Gap** — no-op (REQ-NODE-MP-100) |
| 0 (Foundation) | 0.7–0.8 | DONE |
| 1 (Enrichment) | 1.1–1.3 | DONE (same pipeline as Go) |
| 1 (Enrichment) | 1.4–1.5 | **Weak** — sanitize is no-op, so no transforms applied |
| 1 (Enrichment) | 1.6 | DONE |
| 2 (Spec Building) | 2.1–2.2 | DONE — `build_project_context_section()` produces ESM/CJS-specific rules |
| 2 (Spec Building) | 2.3–2.4 | **Weak** — sanitize is no-op |
| 2 (Spec Building) | 2.5 | DONE |
| 3 (Element Routing) | 3.1–3.3 | All DONE |
| 3 (Element Routing) | 3.4 | DONE — `_try_generate_package_json()` exists |
| 3 (Element Routing) | 3.5 | DONE |
| 4 (Templates) | 4.1–4.2 | DONE (6 templates) |
| 4 (Templates) | 4.3 Match in practice | **Gap** — untested in real runs (granularity mismatch) |
| 4 (Templates) | 4.5 | **Gap** — need Phase 4 decomposition |
| 5 (Decomposition) | 5.1–5.3 | DONE (parser + splicer exist) |
| 5 (Decomposition) | 5.4 Decomposer produces function-level | **Gap** — need Phase 4 (REQ-NODE-MP-400) |
| 5 (Decomposition) | 5.5 Splicer exercised | **Gap** — depends on 5.4 |
| 6 (Generation) | 6.1–6.5 | DONE (post REQ-MPL) |
| 6 (Generation) | 6.6 Fence-strip rate | **Unknown** — no Node.js run data yet |
| 7 (Repair) | 7.0–7.6 | All DONE (6 routes, 6 steps) |
| 7.5 (Leakage Audit) | 7.5.1–7.5.3 | DONE (verified during planning) |
| 7.5 (Leakage Audit) | 7.5.4 Indentation | **GAP** — REQ-NODE-MP-700 |
| 7.5 (Leakage Audit) | 7.5.5, 7.5.7 | DONE |
| 7.5 (Leakage Audit) | 7.5.6 Import hoisting | **GAP** — REQ-NODE-MP-350 |
| 8 (Semantic/Postmortem) | 8.1–8.5 | All DONE (6 checks, 6 mappings) |
| 8 (Semantic/Postmortem) | 8.6 False positive hardening | **Gap** — substring match, not line-anchored |

**Summary:** 45/50 playbook checkpoints DONE (5 closed in v1.1 implementation). 5 remaining playbook gaps + 6 cross-cutting prompt quality gaps (from AST audit + polyglot enablement).

---

## 12. Implementation Priority

| Phase | Requirements | Effort | Dependency | Expected Impact |
|-------|-------------|--------|------------|-----------------|
| ~~**1**~~ | ~~REQ-NODE-MP-100 (sanitize_code_examples)~~ | ~~1 hour~~ | | **DONE** (v1.1) |
| ~~**2**~~ | ~~REQ-NODE-MP-200/201 (P0 module system + async constraints)~~ | ~~1 hour~~ | | **DONE** (v1.1) |
| ~~**3**~~ | ~~REQ-NODE-MP-700 (indentation profile)~~ | ~~30 min~~ | | **DONE** (v1.1) |
| ~~**3.5**~~ | ~~REQ-NODE-MP-350 (import hoisting)~~ | ~~30 min~~ | | **DONE** (v1.1) |
| ~~**4**~~ | ~~REQ-NODE-MP-300/301/302 (TypeScript validation)~~ | ~~2–3 hours~~ | | **DONE** (v1.1) |
| ~~**0.5a**~~ | ~~REQ-NODE-MP-900/901/902 (AST parse quality fixes)~~ | | | **DONE** (pre-existing — fixed in same session as audit) |
| ~~**0.5b**~~ | ~~REQ-NODE-MP-910/911 (stub + import rendering)~~ | | | **DONE** (pre-existing — REQ-MP-1211a/b implemented) |
| ~~**0.5c**~~ | ~~REQ-NODE-MP-920 (signature parser wiring)~~ | | | **DONE** (pre-existing — REQ-MP-1211c implemented) |
| **5** | REQ-NODE-MP-400 (decomposer) | 6–8 hours | Node.js parser + splicer (exist, DC-4 met) | Enable function-level generation; unlock templates + splicer |
| **6** | REQ-NODE-MP-500 (file-level templates) | 2–3 hours | None | Template matches for test files, Express apps, gRPC servers |
| **7** | REQ-NODE-MP-600 (package.json assembly) | 2 hours | None | Richer deterministic package.json (scripts, type field, versions) |
| **8** | REQ-NODE-MP-800 (metrics) | 1 hour | None | Visibility into Node.js MicroPrime effectiveness |

**v1.1 quick wins DONE** (3 hours): Phases 1–4 closed 5 playbook gaps — sanitize, P0 constraints, indentation, import hoisting, TypeScript validation.

**Phase 0.5 DONE (pre-existing):** Code inspection revealed all AST parse + polyglot rendering fixes were already implemented in the same session that produced the audit docs. Node.js already gets: few-shot learning, skeleton context, correct stubs (`function` + `throw new Error`), correct import syntax (CJS/ESM), and language-specific signature parsing.

**Remaining critical path:** 5 (decomposer) → 6 (templates) → 7 (package.json) → 8 (metrics)

**Current status:** All quick wins (Phases 1–4) and prompt quality fixes (Phase 0.5) are done. The remaining work is structural — function-level decomposition (6–8 hours) is the gating item for template matching and splicer usage.

---

## 13. Verification

### Hayai Audit (Pre-Run)

Before the first Node.js MicroPrime run, execute the Python leakage audit (Stage 7.5) from the playbook. The Go run-118 found 5/8 leakage points — Node.js must be checked proactively.

### Run-Level Validation

After each phase, run Node.js Prime Contractor on a representative seed and verify:

| Phase | Metric | Baseline | Target |
|-------|--------|----------|--------|
| 1 | `console.log` in specs after sanitization | unknown (no-op) | 0 (all transformed to `logger.info`) |
| 2 | `module_system_mixing` semantic findings | unknown | 0 |
| 3 | TS syntax errors caught | 0 (invisible) | All TS-specific errors detected |
| 4 | Elements per file (avg) | 1.0 (file-level) | 3–5 (function-level) |
| 4 | Splicer operations | 0 | > 0 |
| 4 | Template match rate | 0% | 10–20% of function-level elements |
| 5 | File-level template matches | 0 | 2–4 per run (test files, Express apps) |
| 6 | package.json with `type` field | 0% | 100% of ESM projects |

### Unit Tests Per Phase

| Phase | Test File | Tests |
|-------|-----------|-------|
| 1 | `tests/unit/languages/test_sanitize_code_examples.py` | Extend existing `TestNodeSanitize` — each transform + clean-code-unchanged + multiline |
| 2 | `tests/unit/micro_prime/test_nodejs_p0_constraint.py` | P0 constraint present in Node.js spec/draft prompts for ESM and CJS |
| 3 | `tests/unit/micro_prime/test_multilang_prompts.py` | Extend with Node.js 2-space indent assertion |
| 3.5 | `tests/unit/micro_prime/test_multilang_repair.py` | Extend with Node.js `require()` hoisting assertions |
| 4 | `tests/unit/languages/test_nodejs_ts_validation.py` | TS validation dispatched for `.ts` files; JS unchanged; tsc-not-installed graceful |
| 4 | (integration) | Verify `_try_parse()` threads filename_hint to `validate_syntax()` for `.ts` |
| 0.5a | `tests/unit/micro_prime/test_ast_parse_quality.py` | Few-shot accepts valid JS; skeleton context extracted from JS; splice repair accepted for JS |
| 0.5b | `tests/unit/micro_prime/test_multilang_prompts.py` | Extend: Node.js stub shows `function`/`throw new Error`; Node.js imports show `require()`/`import from` |
| 0.5c | `tests/unit/workflows/test_signature_parser_dispatch.py` | Node.js signatures parsed via `nodejs_signature_parser`; elements classified at correct tier |
| 5 | `tests/unit/micro_prime/test_nodejs_decomposer.py` | Decomposition of multi-function JS/TS files (functions, arrows, classes) |
| 5 | `tests/unit/micro_prime/test_nodejs_splice_integration.py` | End-to-end: decompose → generate → splice → validate |
| 6 | `tests/unit/micro_prime/test_nodejs_file_templates.py` | Template match + render for each new template, ESM + CJS variants |
| 7 | `tests/unit/micro_prime/test_package_json_assembly.py` | Deterministic package.json from various metadata states |

---

## Appendix: Planning-Derived Insights (v1.1)

These insights were discovered during implementation planning and fed back into the requirements:

1. **Infeasible sanitize transforms removed** (REQ-NODE-MP-100): `require()→import` needs module system context the sanitize method doesn't have; `callback→async/await` is structural, not regex-matchable. Both moved to appropriate layers.
2. **P0 constraint mechanism simplified** (REQ-NODE-MP-200): No new `get_p0_constraints()` method needed — existing `coding_standards` and `build_project_context_section()` are already injected at P0 priority. Just strengthen the text.
3. **`_hoist_leading_imports()` gap added as REQ-NODE-MP-350**: CJS `require()` lines would be trapped inside function bodies during repair. Not in v1.0.
4. **`_try_parse()` filename threading added as REQ-NODE-MP-302**: Without this wiring, TypeScript validation (REQ-300) has zero effect in the actual pipeline.
5. **`tsc` flags refined** (REQ-NODE-MP-300): `--isolatedModules --skipLibCheck` instead of `--strict` — validates syntax without needing project context.
6. **Template ESM/CJS context access resolved** (REQ-NODE-MP-500): Infer from file extension (`.mjs`/`.cjs`/`.js`), not from seed context which templates can't access.
7. **Arrow function `ElementKind` mapping documented** (REQ-NODE-MP-400): `const_function` → `FUNCTION`, not `VARIABLE`.
8. **Leakage audit 7.5.1 and 7.5.5 confirmed DONE**: `repair.py:244–248` already includes Node.js keywords. 7.5.4 and 7.5.6 confirmed as GAPS with requirements assigned.

## Appendix: Hayai Cross-Reference Insights (v1.2)

These insights were discovered by cross-referencing the Hayai Design Principle, Go Hayai Audit, AST Parse Audit, and Polyglot Enablement docs:

1. **AST Parse Audit items are higher priority than decomposer** — 4 `ast.parse()` quality-loss calls affect every Node.js element NOW. Few-shot learning blocked (P0), skeleton context lost (P0), splice repairs discarded (P1). These are pre-existing polyglot issues that the Go audit exposed but didn't fully resolve for Node.js.
2. **REQ-MP-1211a (Python-centric stubs) is a Hayai contamination distance 0 violation** — The knowledge to render `function handler() { ... }` exists in `NodeLanguageProfile` but `_build_element_stub()` at `prompt_builder.py:390` always renders `def handler(): raise NotImplementedError`. This creates the exact precedence problem the Hayai principle describes: the LLM sees contradictory instructions vs stub syntax.
3. **REQ-MP-1211b (Python import rendering) same pattern** — `_render_imports()` at `prompt_builder.py:456` renders `import express` instead of `const express = require('express')`. All non-Python languages affected.
4. **REQ-MP-1211c (signature parser not wired) is a Hayai violation at contamination distance 3+** — `nodejs_signature_parser.py` exists. `language_id` is known at plan ingestion time (REQ-TDE-200). But `_parse_api_signature()` calls `ast.parse()` → fails → all Node.js elements routed to Tier 3. The knowledge and parser are available at the earliest stage; they just aren't wired.
5. **DC-4 ("Node.js MUST NOT be enabled until splicer exists") is MET** — `nodejs_splicer.py` exists and is wired at `splicer.py:191–192`. The polyglot enablement doc should be updated to reflect this. Node.js can be enabled for SIMPLE tier.
6. **Phase 0.5 items are polyglot** — While tracked here as REQ-NODE-MP-9xx, the AST parse fixes and rendering fixes benefit Go, Java, and C# equally. Implementation should target all languages simultaneously. The polyglot requirement IDs are REQ-MP-1211a/b/c.
7. **v1.1 implementation validates the Hayai model** — The 5 quick-win fixes (sanitize, P0 constraints, indentation, import hoisting, TS validation) all follow the Hayai pattern: bind quality knowledge at the earliest available stage. sanitize_code_examples() is the textbook case — reduces contamination distance from 3+ stages (plan→spec→draft→review) to 0 (plan ingestion).
