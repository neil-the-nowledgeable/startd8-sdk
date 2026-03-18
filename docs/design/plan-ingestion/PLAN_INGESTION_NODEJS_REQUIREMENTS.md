# Plan Ingestion — Node.js Language Support Requirements

**Date:** 2026-03-18
**Status:** Draft
**Derived From:** PLAN_INGESTION_MULTI_LANGUAGE_REQUIREMENTS.md (REQ-PLI-*), NODE_PRIME_CONTRACTOR_REQUIREMENTS.md (REQ-NODE-*), `NodeLanguageProfile` in `languages/nodejs.py`
**Scope:** Plan ingestion pipeline changes needed before the first Node.js Prime Contractor run
**Validation Target:** Online Boutique Node.js services (currencyservice, paymentservice) — 7 features, 10 files, ~593 LOC

---

## 1. Current State Assessment

Node.js plan ingestion support is **substantially implemented** but not yet validated end-to-end. The Go run-066 failures motivated a generalization pass that included Node.js scaffolding.

### Already Implemented

| Capability | Evidence | Status |
|-----------|----------|--------|
| `lang_detect.py`: `.js`/`.ts`/`.tsx`/`.mjs`/`.cjs` → `"nodejs"` | `lang_detect.py:32-37` | DONE |
| `lang_detect.py`: `package.json` → `"nodejs"` | `lang_detect.py:47` | DONE |
| `Language` type includes `"nodejs"` | `lang_detect.py:12` | DONE |
| `_CONTEXT_THREADABLE_FIELDS`: `module_system`, `node_version` | `plan_ingestion_workflow.py:118-119` | DONE |
| PARSE prompt: Node.js metadata fields | `plan_ingestion_workflow.py:344-345, 376-377` | DONE |
| `ParsedFeature.module_system`, `ParsedFeature.node_version` | `plan_ingestion_models.py:249-250` | DONE |
| `SeedTask.module_system`, `SeedTask.node_version` | `seeds/models.py:142-143, 280-281` | DONE |
| `_infer_service_metadata()`: Node.js block | `plan_ingestion_workflow.py:860-894`, `seeds/derivation.py:401-435` | DONE |
| `_build_nodejs_module_section()` | `spec_builder.py:454-498` | DONE |
| `_build_available_imports_section()`: Node.js format | `spec_builder.py` (Node.js require/import format) | NEEDS VERIFICATION |
| `NodeLanguageProfile.generate_dependency_file()` | `nodejs.py:214-252` (package.json) | DONE |
| `_NON_PYTHON_EXTENSIONS`: `.js`/`.ts`/`.tsx`/`.jsx` | `engine.py:104` | DONE |
| `_is_non_python_file()`: unknown extension → True | `engine.py:147` (just fixed) | DONE |

### Gaps Remaining

| Gap | REQ-PLI | Severity | Description |
|-----|---------|----------|-------------|
| G-1 | PLI-500 | **P1** | Available-imports Node.js formatting — verify `require('@pkg')` vs `import from '@pkg'` rendering respects `module_system` |
| G-2 | PLI-402 | **P1** | Dependency file routing — verify `package.json` targets trigger `NodeLanguageProfile.generate_dependency_file()` in EMIT |
| G-3 | PLI-602 | **P2** | Per-service `package.json` placement — monorepo services need `src/{service}/package.json`, not root |
| G-4 | PLI-502 | **P2** | Framework detection — Express.js, React, Next.js indicators not wired to PARSE plan-text scan |
| G-5 | — | **P2** | TypeScript extension handling — `.ts`/`.tsx` map to `"nodejs"` but spec builder doesn't inject TypeScript-specific guidance (interfaces, type annotations, `tsconfig.json`) |
| G-6 | PLI-401 | **P3** | Element extraction — no Node.js parser for `ForwardFileSpec.elements` population (not blocking for file-whole strategy) |

---

## 2. Requirements

### 2.1 Available-Imports Formatting (REQ-PLI-NODE-100)

`spec_builder.py:_build_available_imports_section()` MUST format Node.js dependencies using the project's module system:

**CommonJS (default when `module_system != "esm"`):**
```
const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const pino = require('pino');
```

**ESM (when `module_system == "esm"`):**
```
import grpc from '@grpc/grpc-js';
import protoLoader from '@grpc/proto-loader';
import pino from 'pino';
```

**Scoped package handling:** Packages starting with `@` (e.g., `@grpc/grpc-js@^1.10.0`) MUST strip the version pin correctly. The rsplit-on-`@` logic in `NodeLanguageProfile.generate_dependency_file()` already handles this — the same logic should apply in import rendering.

**Acceptance:**
- Online Boutique currencyservice deps render as `const grpc = require(...)` (CommonJS)
- `@scoped/pkg@1.2.3` strips to `@scoped/pkg`, not `@scoped/pkg@1.2` or `scoped/pkg`

**Status:** NEEDS VERIFICATION — logic may already exist but untested with real Node.js plan

---

### 2.2 Dependency File Routing in EMIT (REQ-PLI-NODE-101)

When a task's `target_files` contains `package.json`, the EMIT phase MUST:
1. Detect it via `lang_detect.detect_language("package.json")` → `"nodejs"`
2. Route to `NodeLanguageProfile.generate_dependency_file()` for deterministic generation
3. NOT send it through the Python DFA or LLM generation

The deterministic generator (`nodejs.py:214-252`) produces:
```json
{
  "name": "<service_name>",
  "version": "1.0.0",
  "private": true,
  "dependencies": { ... }
}
```

**Acceptance:**
- `package.json` in target_files produces valid JSON with correct dependency versions
- No Python stubs in `package.json` output

**Status:** NEEDS VERIFICATION — `generate_dependency_file()` exists but EMIT routing may not invoke it

---

### 2.3 Per-Service Package Placement (REQ-PLI-NODE-102)

For monorepo projects with multiple Node.js services, `package.json` MUST be placed in the service directory, not the project root:

| Project Structure | Correct Location |
|------------------|-----------------|
| `src/currencyservice/server.js` | `src/currencyservice/package.json` |
| `src/paymentservice/charge.js` | `src/paymentservice/package.json` |
| `packages/api/index.ts` | `packages/api/package.json` |

This follows the Go pattern (per-service `go.mod`) already implemented in REQ-PLI-602.

**Acceptance:** Online Boutique produces `src/currencyservice/package.json` and `src/paymentservice/package.json`, not a single root `package.json`.

**Status:** NOT VERIFIED — depends on how plan LLM places `package.json` targets

---

### 2.4 TypeScript Support in Spec Builder (REQ-PLI-NODE-103)

When target files include `.ts`/`.tsx` extensions, the spec builder SHOULD inject TypeScript-specific guidance:

```
## TypeScript Context
- Use TypeScript interfaces and types for function parameters and return values
- Use `strict: true` in tsconfig.json
- Prefer `unknown` over `any` for type safety
- Use type-only imports when possible: `import type { Foo } from './foo'`
```

**Note:** This does NOT require a separate TypeScript language profile. The `NodeLanguageProfile` handles both JS and TS (same `node --check` validation, same `package.json` deps). The spec builder simply adds guidance when `.ts` files are present.

**Acceptance:** Tasks targeting `.ts` files get TypeScript guidance in the spec prompt. Tasks targeting `.js` files do not.

**Status:** NOT IMPLEMENTED

---

### 2.5 Framework Detection from Plan Text (REQ-PLI-NODE-104)

During PARSE or pre-PARSE, the workflow SHOULD detect Node.js framework indicators:

| Framework | Detection Signals | Impact on Generation |
|-----------|-------------------|---------------------|
| Express.js | "Express", "express", "middleware", "app.get(", "app.use(" | Inject Express routing patterns |
| gRPC | "gRPC", "protobuf", ".proto", "@grpc/" | Inject gRPC server/client patterns |
| React | "React", "JSX", "useState", "component", "Next.js" | Inject component lifecycle patterns |
| NestJS | "NestJS", "@nestjs/", "Controller", "Module" | Inject decorator + DI patterns |

Detected frameworks SHOULD be stored in `service_metadata.detected_frameworks` (same pattern as Java `detect_java_frameworks()`).

**Acceptance:** Plan text mentioning "Express.js REST API" populates `detected_frameworks: ["express"]` in service metadata.

**Status:** NOT IMPLEMENTED — `NodeLanguageProfile.framework_imports` has detection keywords but they're not wired to PARSE-time plan-text scanning

---

### 2.6 Node.js Module Section Verification (REQ-PLI-NODE-105)

`_build_nodejs_module_section()` in `spec_builder.py` MUST produce correct guidance for both module systems:

**CommonJS output should include:**
- `const X = require('X');` import pattern
- `module.exports = { ... }` export pattern
- Guidance to NOT mix `require()` and `import` in the same file

**ESM output should include:**
- `import X from 'X';` import pattern
- `export { ... }` or `export default` export pattern
- Guidance on `.mjs` extension convention

**Acceptance:** Existing `_build_nodejs_module_section()` already handles this — verify output matches expectations via test.

**Status:** IMPLEMENTED — needs test validation

---

## 3. Implementation Phases

### Phase 1: Validation Run (enables first Node.js plan ingestion)

| Step | Description | Files | Effort |
|------|-------------|-------|--------|
| V-1 | Run Online Boutique Node.js plan through plan ingestion | `.cap-dev-pipe/` | Run only |
| V-2 | Verify `package.json` routing in EMIT | `plan_ingestion_emitter.py` | Inspect |
| V-3 | Verify available-imports formatting | `spec_builder.py` | Inspect |
| V-4 | Fix any failures found in V-1 through V-3 | Various | ~30 lines |

### Phase 2: Quality Improvements

| Step | Description | Files | Effort |
|------|-------------|-------|--------|
| Q-1 | REQ-PLI-NODE-103: TypeScript guidance in spec builder | `spec_builder.py` | ~20 lines |
| Q-2 | REQ-PLI-NODE-104: Framework detection from plan text | `plan_ingestion_workflow.py` | ~30 lines |
| Q-3 | REQ-PLI-NODE-102: Per-service package.json placement validation | `plan_ingestion_emitter.py` | ~10 lines |
| Q-4 | Add Node.js-specific tests for plan ingestion | `tests/unit/workflows/` | ~100 lines |

### Phase 3: Parity with Go (future)

| Step | Description | Priority |
|------|-------------|----------|
| P-1 | REQ-PLI-NODE-106: Node.js element extraction (regex-based) | P3 |
| P-2 | ESLint/Prettier post-generation cleanup | P3 |
| P-3 | `tsconfig.json` deterministic generation | P3 |

---

## 4. Comparison: Node.js Plan Ingestion Readiness

| Capability | Go | Java | Node.js | Notes |
|-----------|-----|------|---------|-------|
| File extension detection | DONE | DONE | **DONE** | `.js`/`.ts`/`.tsx`/`.mjs`/`.cjs` → `"nodejs"` |
| Filename detection | Partial | DONE | **DONE** | `package.json` → `"nodejs"` |
| PARSE prompt fields | DONE | DONE | **DONE** | `module_system`, `node_version` |
| Context threading (QP-1) | DONE | DONE | **DONE** | Both fields in `_CONTEXT_THREADABLE_FIELDS` |
| Service metadata inference | DONE | DONE | **DONE** | module_system, node_version derived |
| Module context section | DONE | DONE | **DONE** | `_build_nodejs_module_section()` |
| Available-imports formatting | DONE | Partial | **NEEDS VERIFY** | CJS/ESM format switching |
| Dependency file generation | DONE | DONE | **DONE** | `generate_dependency_file()` |
| Dep file placement (monorepo) | DONE | DONE | **NEEDS VERIFY** | Per-service `package.json` |
| Framework detection | DONE | DONE | **NOT DONE** | Express, gRPC, React keywords |
| TypeScript guidance | N/A | N/A | **NOT DONE** | `.ts`/`.tsx` specific prompting |
| Element extraction | DONE | DONE | **NOT DONE** | No parser (file-whole strategy) |

**Assessment:** Node.js plan ingestion is **~80% complete**. The primary gap is end-to-end validation — most of the code is written but hasn't been tested with a real Node.js plan. Phase 1 is a validation run, not an implementation sprint.

---

## 5. Risk: Module System Ambiguity

The biggest Node.js-specific risk is **module system ambiguity**. Unlike Go (always modules), Java (always classpath), or Python (always pip), Node.js has two incompatible module systems that affect import syntax, export patterns, and file extensions:

| Signal | Suggests CommonJS | Suggests ESM |
|--------|------------------|-------------|
| `require()` in code | Yes | |
| `import from` in code | | Yes |
| `.cjs` extension | Yes | |
| `.mjs` extension | | Yes |
| `"type": "module"` in package.json | | Yes |
| No `"type"` field | Yes (default) | |
| `.js` extension | Ambiguous | Ambiguous |

The current implementation defaults to `"commonjs"` when undetectable (`spec_builder.py:471`), which is correct for the Online Boutique target (CommonJS throughout). For broader adoption, the pre-PARSE language detection (REQ-PLI-202) should scan for module system signals.
