# Kaizen for Prime Contractor — Node.js Language Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-18
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md)
> **Language Profile:** `NodeLanguageProfile` (`src/startd8/languages/nodejs.py`)
> **Scope:** Node.js/TypeScript-specific quality measurement, validation, and feedback for the Kaizen system

---

## Table of Contents

1. [Overview](#1-overview)
2. [Disk Validation](#2-disk-validation)
3. [Semantic Checks](#3-semantic-checks)
4. [Quality Scoring](#4-quality-scoring)
5. [Repair Pipeline](#5-repair-pipeline)
6. [Feedback Loop Hints](#6-feedback-loop-hints)
7. [Generation Profile](#7-generation-profile)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Verification Strategy](#9-verification-strategy)

---

## 1. Overview

### Language Scope

Node.js covers both JavaScript and TypeScript within the Prime Contractor pipeline. The `NodeLanguageProfile` registers these source extensions: `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx`. Build files: `package.json`, `package-lock.json`, `yarn.lock`.

### Key Advantages

- **npm ecosystem**: The largest package registry in existence. Dependency resolution is well-defined via `package.json` and lockfiles.
- **Flexible module system**: Both CommonJS (CJS) and ES Modules (ESM) are supported, selectable via `package.json` `"type"` field or file extension (`.mjs`/`.cjs`).
- **Wide LLM training data**: Node.js is heavily represented in LLM training corpora. Models generally produce syntactically valid JavaScript with high reliability.
- **Async-first**: `async`/`await` is native and idiomatic; models tend to generate it correctly.

### Key Challenges

- **CJS vs ESM confusion**: LLMs frequently mix `require()` and `import` in the same file, or generate CJS syntax when the project uses ESM (and vice versa). This is the single most common defect class in Node.js generation.
- **TypeScript compilation**: TypeScript files require `tsc --noEmit` validation (not just `node --check`), and LLMs often generate loosely-typed code with excessive `any` annotations.
- **Dependency management**: npm, yarn, and pnpm have different lockfile formats. LLMs sometimes reference packages that don't exist on npm, or use outdated API surfaces.
- **Cross-language contamination**: When generating mixed-language projects (e.g., Go microservices with Node.js frontends), the Python skeleton assembly path can emit Python stubs for `.js` files routed through trivial/simple tiers (see MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md).

### MicroPrime Bypass

Node.js uses **file-whole generation** in MicroPrime. The `merge_strategy_preference` is `"simple"` — no AST-based splicing or element-level decomposition. All generation produces complete files rather than individual functions or classes.

### Relationship to Parent Requirements

This document extends [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) with Node.js-specific quality checks, scoring adjustments, and feedback hints. The parent's Layer 3 (Run Metrics), Layer 4 (Cross-Run Aggregation), and Layer 5 (Feedback Loop) mechanisms apply unchanged — this document defines only the **language-specific inputs** to those layers.

---

## 2. Disk Validation

### REQ-KZ-ND-100: Node.js Disk Compliance

The Kaizen disk compliance checker MUST validate Node.js files using language-appropriate tools and heuristics. Validation operates at two levels: per-file syntax/structure and per-project dependency integrity.

#### Per-File Checks

| Check | Tool/Method | Applies To | Severity |
|-------|-------------|-----------|----------|
| JavaScript syntax validity | `node --check {file}` | `.js`, `.mjs`, `.cjs` | CRITICAL — score 0.0 on failure |
| TypeScript compilation | `tsc --noEmit {file}` (requires `tsconfig.json`) | `.ts`, `.tsx` | CRITICAL — score 0.0 on failure |
| Module system consistency | Regex scan for `require()` + `import` in same file | `.js` (not `.mjs`/`.cjs`) | HIGH — 0.5 penalty |
| Cross-language contamination | Detect Python artifacts (`from __future__`, `def `, `import os`) | All extensions | CRITICAL — score 0.0 on detection |
| Export presence | File exports at least one symbol (function, class, constant) | All except entry points | LOW — 0.1 penalty |
| No `var` declarations | Regex scan for `var ` keyword | All JS/TS files | LOW — 0.05 penalty |

**Module system consistency rules:**

- `.mjs` files: ESM only (`import`/`export`). Any `require()` is a violation.
- `.cjs` files: CJS only (`require()`/`module.exports`). Any `import`/`export` is a violation.
- `.js` files: Must be consistent with `package.json` `"type"` field. If `"type": "module"`, ESM rules apply. If absent or `"type": "commonjs"`, CJS rules apply. Mixed usage in a `.js` file is always a violation regardless of `"type"` field.
- `.ts`/`.tsx` files: Always ESM syntax (`import`/`export`). `require()` in TypeScript is a violation (use `import` instead).

**Cross-language contamination patterns:**

```
from __future__ import annotations   # Python stub
def function_name(                    # Python function definition
import os                            # Python stdlib import (no 'from', no quotes)
class MyClass:                       # Python class (colon syntax)
```

These patterns indicate the file received a Python skeleton stub instead of Node.js content (the trivial/simple tier routing failure described in REQ-MLT-100).

**Entry point detection:**

Files matching these patterns are exempt from the export presence check:
- `index.js` / `index.ts` / `main.js` / `main.ts` / `app.js` / `app.ts` / `server.js` / `server.ts`
- Files containing `process.exit()` or `http.createServer()` or `app.listen()`
- Files with a shebang line (`#!/usr/bin/env node`)

#### Per-Project Checks

| Check | Method | Severity |
|-------|--------|----------|
| `package.json` existence | File presence check | CRITICAL — project cannot install deps |
| `package.json` validity | JSON parse + required fields (`name`, `version`) | HIGH |
| `main`/`module`/`exports` field | At least one entry point field present | MEDIUM |
| Dependencies declared | Every `require()`/`import` of a non-stdlib, non-local module has a corresponding entry in `dependencies` or `devDependencies` | HIGH |
| No phantom packages | Every entry in `dependencies` exists on npm (optional — requires network) | LOW |

**Acceptance criteria:**

- A `.js` file with `node --check` failure scores 0.0 for the syntax component
- A `.js` file containing both `require('express')` and `import { Router } from 'express'` is flagged as MODULE_SYSTEM_MISMATCH
- A `.js` file containing `from __future__ import annotations` scores 0.0 (CROSS_LANGUAGE_CONTAMINATION)
- A `package.json` missing the `name` field is flagged as MISSING_PACKAGE_JSON (structural)
- A file importing `@grpc/grpc-js` with no corresponding `package.json` entry is flagged as DEPENDENCY_NOT_IN_PACKAGE_JSON

### REQ-KZ-ND-101: Node.js Validation Tools

The following tools are used for Node.js validation. Tools are categorized as **required** (must be available) or **optional** (best-effort, degrade gracefully if absent).

| Tool | Purpose | Required? | Fallback |
|------|---------|-----------|----------|
| `node --check {file}` | JavaScript syntax validation | **Required** | If `node` not installed, skip syntax check with warning (best-effort, per `validate_syntax()` in `NodeLanguageProfile`) |
| `tsc --noEmit` | TypeScript compilation check | Optional | Skip TS validation; flag as UNVALIDATED in disk compliance result |
| `eslint {file}` | Lint analysis (unused vars, style) | Optional | Skip lint; no score penalty for absence |
| `prettier --check {file}` | Formatting consistency check | Optional | Skip formatting check; cosmetic only |
| `npm audit` | Known vulnerability detection in dependencies | Optional | Skip security check; informational only |
| `npm ls --all` | Dependency tree resolution (detects phantom deps) | Optional | Skip dep-tree check; rely on `package.json` presence only |

**Tool discovery:** Validation uses `shutil.which()` to detect tool availability at runtime (consistent with `NodeLanguageProfile.post_generation_cleanup()`).

**Timeout constraints:** All external tool invocations MUST have a timeout. Defaults: `node --check` = 15s (per `validate_syntax()`), `tsc --noEmit` = 30s, `eslint` = 30s, `prettier --check` = 15s.

---

## 3. Semantic Checks

### REQ-KZ-ND-200: Node.js Semantic Validators

Semantic validators detect issues that pass syntax checks but indicate broken or low-quality code. Each validator populates the `semantic_issues` list in `DiskComplianceResult` with structured entries (severity, category, message, line number).

#### `check_module_system_consistency(code: str, file_ext: str, package_type: str) -> list[SemanticIssue]`

Detects mixing of CommonJS and ESM syntax within a single file.

**Detection patterns:**

| CJS indicators | ESM indicators |
|---------------|----------------|
| `require(` | `import ... from` |
| `module.exports` | `export default` |
| `exports.` | `export {` |
| `__dirname` | `export const` / `export function` / `export class` |
| `__filename` | `import.meta.url` |

**Rules:**
- If both CJS and ESM indicators are present in the same file, emit `MODULE_SYSTEM_MISMATCH` (severity: HIGH)
- `.mjs` with CJS indicators: emit `MODULE_SYSTEM_MISMATCH` (severity: CRITICAL)
- `.cjs` with ESM indicators: emit `MODULE_SYSTEM_MISMATCH` (severity: CRITICAL)
- `.ts`/`.tsx` with `require()`: emit `MODULE_SYSTEM_MISMATCH` (severity: HIGH) — TypeScript should use `import`

**Exceptions:**
- `require('dotenv').config()` in a top-level config file is acceptable in ESM projects (common pattern)
- `require()` inside `try/catch` for optional dependency loading is acceptable
- Dynamic `import()` expressions are valid in both CJS and ESM

#### `check_missing_error_handling(code: str) -> list[SemanticIssue]`

Detects async operations without error handling.

**Detection patterns:**
- `async function` or `async (` without any `try` block in the function body: emit `UNHANDLED_PROMISE_REJECTION` (severity: MEDIUM)
- `.then(` without a subsequent `.catch(`: emit `UNHANDLED_PROMISE_REJECTION` (severity: MEDIUM)
- `new Promise(` constructor without reject handler: emit `UNHANDLED_PROMISE_REJECTION` (severity: LOW)

**Exceptions:**
- Top-level `process.on('unhandledRejection', ...)` in the same file satisfies the global handler requirement
- Functions that only `await` synchronous-looking operations (e.g., `await delay(100)`) are exempt

#### `check_callback_hell(code: str) -> list[SemanticIssue]`

Detects deeply nested callback patterns that should use `async`/`await`.

**Detection:** Count nested callback indentation depth. If any callback chain exceeds 3 levels of nesting (measured by indentation increase of >3 levels from the outermost callback), emit `CALLBACK_HELL` (severity: MEDIUM).

**Pattern:**
```javascript
// 3+ levels of nested callbacks = CALLBACK_HELL
fs.readFile('a', (err, data) => {
  db.query(data, (err, rows) => {
    http.get(rows[0].url, (err, res) => {
      // This is callback hell
    });
  });
});
```

#### `check_console_log_in_production(code: str, file_path: str) -> list[SemanticIssue]`

Detects `console.log()` / `console.warn()` / `console.error()` in production code that should use a structured logger.

**Rules:**
- `console.log()` in non-test, non-script files: emit severity LOW
- Exempt: files in `test/`, `tests/`, `__tests__/`, `spec/` directories
- Exempt: files named `*.test.js`, `*.spec.js`, `*.test.ts`, `*.spec.ts`
- Exempt: `console.error()` in catch blocks (acceptable fallback)

#### `check_unused_requires(code: str) -> list[SemanticIssue]`

Detects `require()` or `import` statements whose bindings are never referenced in the rest of the file.

**Detection:**
- Extract all `const X = require(...)` bindings
- Extract all `import { X, Y } from '...'` bindings
- Scan the remaining code for references to each binding name
- If a binding is never referenced: emit `UNUSED_IMPORT` (severity: LOW)

**Exceptions:**
- Side-effect imports: `require('dotenv').config()`, `import './polyfill'` (no binding)
- Imports used only in type annotations (TypeScript): `import type { X }` is exempt

#### `check_missing_exports(code: str, file_path: str) -> list[SemanticIssue]`

Detects modules that define functions or classes but export nothing.

**Detection:**
- File has `function` or `class` definitions but no `module.exports`, `exports.`, `export default`, or `export {`
- Emit `MISSING_EXPORTS` (severity: MEDIUM) — likely a dead module

**Exceptions:**
- Entry point files (see REQ-KZ-ND-100 entry point detection)
- Files that are purely configuration (e.g., `jest.config.js`, `.eslintrc.js`)
- Test files

#### `check_typescript_any_overuse(code: str) -> list[SemanticIssue]`

Detects excessive use of the `any` type annotation in TypeScript files.

**Detection:**
- Count occurrences of `: any`, `as any`, `<any>`, `: any[]`, `: any)` in `.ts`/`.tsx` files
- If count > 3 per file, or > 1 per function: emit `ANY_TYPE_OVERUSE` (severity: MEDIUM)
- If count > 10 per file: emit `ANY_TYPE_OVERUSE` (severity: HIGH)

**Exceptions:**
- `// @ts-ignore` or `// eslint-disable` comments on the same line indicate intentional escape
- Files explicitly named `*.d.ts` (declaration files) are exempt
- Generic constraint `<T = any>` as a default is acceptable (1 occurrence per generic)

#### `check_cross_language_contamination(code: str, file_ext: str) -> list[SemanticIssue]`

Detects Python or Go code artifacts in Node.js files.

**Detection patterns:**

| Pattern | Language | Confidence |
|---------|----------|------------|
| `from __future__ import` | Python | 100% — CRITICAL |
| `def ` followed by `(self` | Python | 95% — CRITICAL |
| `import os` (bare, no quotes) | Python | 90% — HIGH |
| `func ` followed by `(` | Go | 85% — HIGH |
| `package main` | Go | 95% — CRITICAL |
| `fmt.Println` | Go | 100% — CRITICAL |

Emit `CROSS_LANGUAGE_CONTAMINATION` with the detected source language.

---

## 4. Quality Scoring

### REQ-KZ-ND-300: Node.js Quality Score Formula

The Node.js quality score follows the same composite structure as the parent Kaizen system but with Node.js-specific component weights:

```
quality_score = (syntax_check × 0.25)
             + (module_consistency × 0.20)
             + (stub_penalty × 0.20)
             + (error_handling × 0.15)
             + (contamination_check × 0.10)
             + (convention_compliance × 0.10)
```

#### Component Definitions

| Component | Value Range | Calculation |
|-----------|------------|-------------|
| `syntax_check` | 0.0 or 1.0 | 1.0 if `node --check` passes (or `tsc --noEmit` for TS); 0.0 on failure |
| `module_consistency` | 0.0, 0.5, or 1.0 | 1.0 if pure CJS or pure ESM throughout file; 0.5 if mixed but functional (e.g., dynamic `import()` in CJS); 0.0 if incompatible mixing |
| `stub_penalty` | 0.0 to 1.0 | `max(0, 1.0 - (stub_count × 0.2))`. Stubs detected via `NodeLanguageProfile.stub_patterns` |
| `error_handling` | 0.0 to 1.0 | `max(0, 1.0 - (unhandled_async_count × 0.15))` |
| `contamination_check` | 0.0 or 1.0 | 1.0 if no cross-language contamination; 0.0 if any Python/Go artifacts detected |
| `convention_compliance` | 0.0 to 1.0 | Composite of: no `var` (0.3), camelCase functions (0.3), `const` preference (0.2), no `console.log` in prod (0.2) |

**Node.js stub patterns** (from `NodeLanguageProfile.stub_patterns`):

```regex
throw\s+new\s+Error\s*\(\s*['"]not implemented
throw\s+new\s+Error\s*\(\s*['"]TODO
^\s*//\s*TODO\b
```

Additional stub indicators for scoring:
- `return undefined; // placeholder`
- `/* istanbul ignore next */` wrapping an empty function body
- Function body consisting solely of `return null;` or `return {};`

### REQ-KZ-ND-301: Node.js Root Causes

The Kaizen system categorizes Node.js defects using these root cause codes. Each code maps to a specific semantic check and feeds into the parent system's `pipeline_attribution` for trend analysis.

| Root Cause Code | Description | Semantic Check | Typical Score Impact |
|----------------|-------------|----------------|---------------------|
| `CROSS_LANGUAGE_CONTAMINATION` | Python/Go artifacts in Node.js file | `check_cross_language_contamination()` | 0.0 (fatal) |
| `SYNTAX_ERROR` | `node --check` or `tsc` failure | Disk validation (REQ-KZ-ND-100) | 0.0 (fatal) |
| `MODULE_SYSTEM_MISMATCH` | CJS/ESM mixing in same file | `check_module_system_consistency()` | -0.20 to -0.25 |
| `MISSING_PACKAGE_JSON` | No `package.json` or invalid structure | Disk validation (REQ-KZ-ND-100) | -0.15 project-level |
| `UNHANDLED_PROMISE_REJECTION` | Missing error handling on async ops | `check_missing_error_handling()` | -0.15 per instance |
| `TYPESCRIPT_COMPILATION_ERROR` | `tsc --noEmit` failure for `.ts`/`.tsx` | Disk validation (REQ-KZ-ND-100) | 0.0 (fatal) |
| `MISSING_EXPORTS` | Module defines symbols but exports none | `check_missing_exports()` | -0.10 |
| `DEPENDENCY_NOT_IN_PACKAGE_JSON` | `require()`/`import` of pkg not in deps | Disk validation (REQ-KZ-ND-100) | -0.15 per instance |
| `CALLBACK_HELL` | >3 levels nested callbacks | `check_callback_hell()` | -0.10 |
| `ANY_TYPE_OVERUSE` | Excessive `any` in TypeScript | `check_typescript_any_overuse()` | -0.05 to -0.15 |
| `UNUSED_IMPORT` | `require()`/`import` with unused binding | `check_unused_requires()` | -0.05 per instance |

---

## 5. Repair Pipeline

### REQ-KZ-ND-400: Node.js Repair Capabilities

Node.js repair operates at the file-whole level (no AST-based splicing). The `NodeLanguageProfile` has `repair_enabled = True`, meaning the existing repair pipeline activates for Node.js files but with a limited set of deterministic steps.

#### Available Repair Steps

| Step | Tool | Deterministic? | What It Fixes |
|------|------|---------------|---------------|
| `fence_strip` | Regex | Yes | Removes markdown code fences (`` ```javascript ... ``` ``) from LLM output that wasn't properly extracted |
| `prettier_format` | `prettier --write {file}` | Yes | Normalizes formatting (indentation, semicolons, trailing commas per config) |
| `eslint_autofix` | `eslint --fix {file}` | Mostly | Auto-fixable lint issues (unused imports, missing semicolons, `==` to `===`) |
| `shebang_strip` | Regex | Yes | Removes accidental `#!/usr/bin/env python3` shebang from Node.js files |
| `contamination_strip` | Regex | Yes | Removes Python preamble lines (`from __future__`, `import os`) from files that are otherwise valid JS |

#### Missing Repair Capabilities (Not Implemented)

| Capability | Why Missing | Workaround |
|-----------|-------------|------------|
| CJS-to-ESM conversion | Requires semantic understanding of dynamic `require()` paths | Regenerate with explicit module system hint |
| ESM-to-CJS conversion | `import.meta.url` has no CJS equivalent without polyfill | Regenerate with explicit module system hint |
| `any` type narrowing | Requires understanding of runtime types | Flag for LLM review; no automated fix |
| Missing `package.json` dependency addition | Requires npm registry lookup | Flag in feedback hints; operator adds manually |
| AST-based repair | No Node.js AST manipulation in SDK | File-whole regeneration is the fallback |

#### Repair Ordering

Repairs execute in this order (consistent with the parent repair pipeline):

1. `fence_strip` — Extract code from markdown fences
2. `contamination_strip` — Remove cross-language artifacts
3. `shebang_strip` — Remove incorrect shebang lines
4. `prettier_format` — Normalize formatting (if `prettier` available)
5. `eslint_autofix` — Fix lint issues (if `eslint` available)
6. Re-validate with `node --check` (or `tsc --noEmit` for TS)

If re-validation fails after all repair steps, the file is marked as `repair_failed` and the original (pre-repair) version is preserved alongside the attempted repair for diagnostic comparison.

### REQ-KZ-ND-402: Node.js Semantic-to-Repair Bridge Convention

**Status:** Phase 1 (advisory-only; no Node.js semantic repair steps yet)
**Depends on:** REQ-KZ-ND-400, REQ-KZ-ND-300
**Analogous to:** REQ-KZ-CS-402a/b/c

The Node.js semantic checks module (`nodejs_semantic_checks.py`) produces 6 categorized findings. This requirement defines which are auto-repairable, which remain advisory-only, and the phased rollout plan.

**Invariant:** A category MUST NOT appear in `_REPAIRABLE_CATEGORIES` until a deterministic repair step exists.

#### REQ-KZ-ND-402a: Multi-Language Dispatch

Add `.js`, `.jsx`, `.ts`, `.tsx` to `_SEMANTIC_REPAIR_EXTENSIONS` when Phase 2 repair steps exist. Phase 1: JS/TS files are NOT dispatched to semantic repair.

#### REQ-KZ-ND-402b: Category Registration

| Category | Severity | Classification | Rationale |
|---|---|---|---|
| `var_usage` | warning | **Repairable** | Regex `s/\bvar\b/const/` or `eslint --fix` with `no-var` rule. Deterministic. |
| `duplicate_require` | warning | **Repairable** | Remove duplicate `require()`/`import` lines keeping first occurrence. |
| `python_contamination` | error | **Repairable** | Line removal of Python fingerprints. Shared pattern with other profiles. |
| `console_log_in_service` | warning | Advisory | Replacement requires project-specific logger knowledge (winston/pino/bunyan). |
| `unhandled_promise` | warning | Advisory | `try/catch` wrapping requires understanding error propagation scope. |
| `module_system_mixing` | error | Advisory | CJS↔ESM conversion involves package.json `"type"` field + consumer compat. |

#### REQ-KZ-ND-402c: Compliance Results Collection

**Status:** IMPLEMENTED (2026-03-22). Node.js semantic results stored in `compliance_results`.

#### REQ-KZ-ND-402d: Phased Repair Step Plan

**Phase 1 (current):** All 6 categories advisory-only. Visible in postmortem/Kaizen scoring.

**Phase 2:** Three deterministic text-based steps (no external tool dependency):
1. **`var_to_const`** — Regex `s/\bvar\s+/const /g`. Downstream `node --check` catches incorrect `const` for reassigned vars.
2. **`dedup_require`** — Track seen specifiers, remove duplicate `require()`/`import` lines.
3. **`contamination_strip_js`** — Remove Python fingerprint lines. Reuse pattern list from cross-language contamination strip.

Register `var_usage`, `duplicate_require`, `python_contamination` as repairable. Add JS/TS extensions to `_SEMANTIC_REPAIR_EXTENSIONS`.

**Phase 3:** `eslint --fix` integration as composite step. Falls back to Phase 2 text-based steps if `eslint` unavailable. Potentially promotes additional categories as ESLint auto-fix coverage expands.

---

## 6. Feedback Loop Hints

### REQ-KZ-ND-500: Node.js-Specific Kaizen Hints

When the Kaizen system generates improvement suggestions (per parent REQ-KZ-500/501), Node.js-specific hints use these templates. Hints are injected into the LLM prompt context for subsequent runs.

#### Module System Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| `MODULE_SYSTEM_MISMATCH` detected | `"Use ESM (import/export) for new projects. Use CJS (require/module.exports) only when required by existing project configuration. Check package.json 'type' field: if 'module', use ESM; if 'commonjs' or absent, use CJS. NEVER mix require() and import in the same file."` |
| `.mjs` file with `require()` | `"Files with .mjs extension MUST use ESM syntax exclusively. Use 'import' instead of 'require()'. Use 'import.meta.url' instead of '__dirname'."` |
| `.ts` file with `require()` | `"TypeScript files MUST use 'import' syntax, not 'require()'. Use 'import X from 'pkg'' for default imports and 'import { X } from 'pkg'' for named imports."` |

#### Error Handling Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| `UNHANDLED_PROMISE_REJECTION` | `"Wrap async operations in try/catch blocks. Every async function that calls external services (HTTP, database, file I/O) MUST have error handling. Use 'process.on('unhandledRejection', handler)' as a safety net in entry points."` |
| `CALLBACK_HELL` | `"Convert nested callbacks to async/await. Replace callback chains with: 'const result = await asyncOperation()'. Use Promise.all() for parallel operations."` |

#### TypeScript Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| `ANY_TYPE_OVERUSE` | `"Avoid the 'any' type. Use specific types or interfaces. If the type is truly unknown, use 'unknown' and narrow with type guards. Define interfaces for object shapes: 'interface Config { port: number; host: string; }'."` |
| `TYPESCRIPT_COMPILATION_ERROR` | `"Ensure TypeScript code compiles with strict mode. Common fixes: add type annotations to function parameters, use 'as const' for literal types, import types with 'import type { X }'."` |

#### Testing Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| Test files with no assertions | `"Use describe/it/expect patterns with vitest or jest. Every test file MUST have at least one expect() assertion. Structure: describe('module') → it('should behavior') → expect(result).toBe(expected)."` |
| No test files generated | `"Generate test files alongside source files. For 'src/service.js', create 'test/service.test.js'. Use the project's existing test framework (vitest, jest, or mocha)."` |

#### Dependency Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| `DEPENDENCY_NOT_IN_PACKAGE_JSON` | `"Every npm package used in require() or import statements MUST be listed in package.json dependencies. Pin major versions: '@grpc/grpc-js': '^1.10.0', not '*'. Use package-lock.json for reproducible installs."` |
| `MISSING_PACKAGE_JSON` | `"Every Node.js project requires a package.json with at minimum: name, version, and dependencies. Use 'npm init -y' as a template. Set 'type': 'module' for ESM projects."` |

#### Contamination Hints

| Trigger Condition | Hint Text |
|-------------------|-----------|
| `CROSS_LANGUAGE_CONTAMINATION` | `"This file contains Python code artifacts in a Node.js file. Generate JavaScript/TypeScript code only. Do NOT use Python syntax (def, import os, from __future__). Node.js uses function/const/class declarations, not Python def/class:."` |

---

## 7. Generation Profile

### REQ-KZ-ND-600: Node.js Generation Characteristics

This section defines the generation-time decisions that affect Kaizen quality outcomes.

#### Module System Decision Tree

The module system for generated code is determined by this priority chain (highest to lowest):

1. **Explicit `module_system` in seed task metadata** — If the plan specifies `"module_system": "esm"` or `"module_system": "commonjs"`, use it directly.
2. **`package.json` `"type"` field** — If an existing `package.json` exists in the project root, `detect_module_system()` reads the `"type"` field. `"module"` = ESM, absent/`"commonjs"` = CJS.
3. **File extension** — `.mjs` forces ESM, `.cjs` forces CJS.
4. **Inferred from plan features** — `derive_service_metadata()` examines target file extensions across all features. If any `.mjs` and no `.cjs`, default to ESM. Otherwise, default to CJS.
5. **Fallback** — `"commonjs"` (Node.js default when `package.json` has no `"type"` field, per `build_project_context_section()`).

**Kaizen enforcement:** If a run produces `MODULE_SYSTEM_MISMATCH` defects, the feedback loop (REQ-KZ-ND-500) injects explicit module system instructions. The next run's spec prompt includes the `build_project_context_section()` output, which contains detailed CJS or ESM rules (see `NodeLanguageProfile.build_project_context_section()`).

#### TypeScript Configuration

When generating TypeScript files (`.ts`/`.tsx`), the generation profile includes:

- `tsconfig.json` generation via plan-level metadata (not `generate_dependency_file()` — that handles `package.json` only)
- Strict mode enabled by default: `"strict": true`, `"noImplicitAny": true`
- Module resolution: `"moduleResolution": "node"` for CJS, `"moduleResolution": "bundler"` for ESM
- Target: `"target": "ES2022"` (matches Node.js 20 LTS capabilities)

#### Template Requirements

Skeleton files for Node.js use these patterns:

**CJS skeleton (`{service}.js`):**
```javascript
'use strict';

const { /* deps */ } = require('...');

// TODO: implement
module.exports = { /* exports */ };
```

**ESM skeleton (`{service}.js` with `"type": "module"`):**
```javascript
import { /* deps */ } from '...';

// TODO: implement
export default { /* exports */ };
```

**TypeScript skeleton (`{service}.ts`):**
```typescript
import { /* deps */ } from '...';

// TODO: implement
export default { /* exports */ };
```

#### Dependency File Generation

`NodeLanguageProfile.generate_dependency_file()` produces `package.json` with:
- `name`: from `service_name` parameter
- `version`: `"1.0.0"` (default)
- `private`: `true` (prevents accidental npm publish)
- `dependencies`: populated from plan's dependency list, with version handling for scoped packages (`@scope/pkg@version`)

**Kaizen relevance:** If `DEPENDENCY_NOT_IN_PACKAGE_JSON` is a recurring root cause, the feedback loop should verify that `generate_dependency_file()` is being called with the complete dependency list from the plan. Missing dependencies indicate a plan ingestion gap, not a generation gap.

#### Docker Generation

For tasks with Dockerfile targets, `build_project_context_section()` injects Docker-specific context:
- Builder image: `node:20-alpine` (per `docker_base_image`)
- Runtime image: `node:20-alpine` (per `docker_runtime_image`)
- Multi-stage build pattern: `COPY package*.json` → `npm install --only=production` → copy app
- Entry point: `node {entry_point}` (configurable via service metadata)

---

## 8. Traceability Matrix

### Requirements to Parent Kaizen Layer Mapping

| Node.js Requirement | Parent Layer | Parent Requirement | Relationship |
|---------------------|-------------|-------------------|-------------|
| REQ-KZ-ND-100 (Disk Compliance) | Layer 1 (Post-Mortem) | REQ-KZ-100 | Extends — adds Node.js-specific disk checks |
| REQ-KZ-ND-101 (Validation Tools) | Layer 1 (Post-Mortem) | REQ-KZ-100 | Extends — defines Node.js tool chain |
| REQ-KZ-ND-200 (Semantic Validators) | Layer 1 (Post-Mortem) | REQ-KZ-100 | Extends — populates `semantic_issues` for Node.js |
| REQ-KZ-ND-300 (Quality Score) | Layer 3 (Run Metrics) | REQ-KZ-300 | Extends — Node.js-specific scoring weights |
| REQ-KZ-ND-301 (Root Causes) | Layer 3 (Run Metrics) | REQ-KZ-300 | Extends — Node.js root cause taxonomy |
| REQ-KZ-ND-400 (Repair) | Layer 1 (Post-Mortem) | REQ-KZ-100 | Extends — Node.js repair steps |
| REQ-KZ-ND-500 (Hints) | Layer 5 (Feedback Loop) | REQ-KZ-500/501/502 | Extends — Node.js hint templates |
| REQ-KZ-ND-600 (Generation Profile) | N/A (generation-time) | N/A | New — documents generation decisions affecting quality |

### Requirements to Language Profile Mapping

| Node.js Requirement | `NodeLanguageProfile` Property/Method | Dependency Direction |
|---------------------|---------------------------------------|---------------------|
| REQ-KZ-ND-100 (syntax check) | `syntax_check_command`, `validate_syntax()` | Kaizen reads from profile |
| REQ-KZ-ND-100 (extensions) | `source_extensions`, `supports_extension()` | Kaizen reads from profile |
| REQ-KZ-ND-100 (stubs) | `stub_patterns` | Kaizen reads from profile |
| REQ-KZ-ND-100 (contamination) | N/A — Kaizen-internal check | Independent |
| REQ-KZ-ND-200 (module consistency) | `import_pattern_template`, `get_import_patterns()` | Kaizen reads from profile |
| REQ-KZ-ND-400 (prettier repair) | `post_generation_cleanup()` | Kaizen invokes profile method |
| REQ-KZ-ND-500 (module hints) | `build_project_context_section()`, `coding_standards` | Hint text derived from profile |
| REQ-KZ-ND-600 (dependency file) | `generate_dependency_file()` | Generation invokes profile method |
| REQ-KZ-ND-600 (module system) | `derive_service_metadata()` | Generation invokes profile method |
| REQ-KZ-ND-600 (Docker) | `docker_base_image`, `docker_runtime_image` | Generation reads from profile |

### Requirements to Existing SDK Module Mapping

| Node.js Requirement | SDK Module | Integration Point |
|---------------------|-----------|-------------------|
| REQ-KZ-ND-100 | `forward_manifest_validator.py` | `_validate_non_python_file()` dispatch |
| REQ-KZ-ND-200 | New: `kaizen/validators/nodejs.py` | Semantic validator functions |
| REQ-KZ-ND-300 | `kaizen/metrics.py` (TBD) | `compute_disk_quality_score()` language dispatch |
| REQ-KZ-ND-301 | `kaizen/metrics.py` (TBD) | Root cause enum extension |
| REQ-KZ-ND-400 | `repair/orchestrator.py` | Repair step registry extension |
| REQ-KZ-ND-500 | `kaizen/suggestions.py` (TBD) | Hint template registry |
| REQ-KZ-ND-600 | `languages/nodejs.py` | Already implemented (profile methods) |

---

## 9. Verification Strategy

### Unit Tests

| Test | Requirement | Description |
|------|------------|-------------|
| `test_nodejs_syntax_validation_pass` | REQ-KZ-ND-100 | Valid JS file passes `node --check` |
| `test_nodejs_syntax_validation_fail` | REQ-KZ-ND-100 | JS file with syntax error scores 0.0 |
| `test_module_consistency_pure_esm` | REQ-KZ-ND-100, REQ-KZ-ND-200 | Pure ESM file scores 1.0 for module consistency |
| `test_module_consistency_pure_cjs` | REQ-KZ-ND-100, REQ-KZ-ND-200 | Pure CJS file scores 1.0 for module consistency |
| `test_module_consistency_mixed` | REQ-KZ-ND-200 | File with both `require()` and `import` flagged as MODULE_SYSTEM_MISMATCH |
| `test_module_mismatch_mjs_with_require` | REQ-KZ-ND-200 | `.mjs` file with `require()` flagged CRITICAL |
| `test_cross_language_contamination_python` | REQ-KZ-ND-200 | JS file with `from __future__ import annotations` detected |
| `test_cross_language_contamination_go` | REQ-KZ-ND-200 | JS file with `package main` detected |
| `test_missing_error_handling` | REQ-KZ-ND-200 | Async function without try/catch flagged |
| `test_callback_hell_detection` | REQ-KZ-ND-200 | 4-level nested callbacks flagged |
| `test_console_log_exemption_test_files` | REQ-KZ-ND-200 | `console.log` in test files not flagged |
| `test_unused_require_detection` | REQ-KZ-ND-200 | `const x = require('y')` with no reference to `x` flagged |
| `test_missing_exports_detection` | REQ-KZ-ND-200 | File with functions but no exports flagged |
| `test_missing_exports_entry_point_exempt` | REQ-KZ-ND-200 | `index.js` with no exports not flagged |
| `test_typescript_any_overuse` | REQ-KZ-ND-200 | `.ts` file with 5 `any` annotations flagged |
| `test_typescript_any_dts_exempt` | REQ-KZ-ND-200 | `.d.ts` file with `any` not flagged |
| `test_quality_score_perfect` | REQ-KZ-ND-300 | Clean file scores 1.0 |
| `test_quality_score_contaminated` | REQ-KZ-ND-300 | Contaminated file scores ~0.0 |
| `test_quality_score_mixed_modules` | REQ-KZ-ND-300 | Mixed-module file loses 0.20 (module_consistency = 0.0) |
| `test_root_cause_classification` | REQ-KZ-ND-301 | Each defect type maps to correct root cause code |
| `test_fence_strip_repair` | REQ-KZ-ND-400 | Markdown fences removed from JS output |
| `test_contamination_strip_repair` | REQ-KZ-ND-400 | Python preamble lines removed |
| `test_prettier_repair_invocation` | REQ-KZ-ND-400 | `prettier --write` called when available |
| `test_repair_ordering` | REQ-KZ-ND-400 | Repairs execute in specified order |
| `test_hint_module_system` | REQ-KZ-ND-500 | MODULE_SYSTEM_MISMATCH triggers correct hint text |
| `test_hint_error_handling` | REQ-KZ-ND-500 | UNHANDLED_PROMISE_REJECTION triggers correct hint text |
| `test_hint_contamination` | REQ-KZ-ND-500 | CROSS_LANGUAGE_CONTAMINATION triggers correct hint text |
| `test_module_system_decision_tree` | REQ-KZ-ND-600 | Module system resolved via priority chain |
| `test_package_json_generation` | REQ-KZ-ND-600 | `generate_dependency_file()` produces valid JSON |

### Integration Tests

| Test | Requirements | Description |
|------|-------------|-------------|
| `test_nodejs_full_validation_pipeline` | REQ-KZ-ND-100, 200, 300 | End-to-end: generate Node.js file → validate → score → report root causes |
| `test_nodejs_repair_then_revalidate` | REQ-KZ-ND-100, 400 | File with fences → repair → passes `node --check` |
| `test_nodejs_kaizen_hint_injection` | REQ-KZ-ND-500, 600 | Run with MODULE_SYSTEM_MISMATCH → next run prompt includes module system hint |
| `test_nodejs_mixed_project_scoring` | REQ-KZ-ND-300 | Project with JS + TS + Dockerfile → each file scored with appropriate validators |

### Smoke Tests (E2E)

| Test | Requirements | Description |
|------|-------------|-------------|
| `test_prime_nodejs_online_boutique_subset` | All | Run Prime Contractor against 3 Node.js features from Online Boutique plan → verify no CROSS_LANGUAGE_CONTAMINATION, no MODULE_SYSTEM_MISMATCH, quality score > 0.7 |
