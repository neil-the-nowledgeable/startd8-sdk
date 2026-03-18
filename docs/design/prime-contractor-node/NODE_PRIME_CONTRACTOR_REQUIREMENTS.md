# Node.js Prime Contractor — Requirements & Design

**Date:** 2026-03-17
**Status:** Draft
**Derived From:** Go Prime Contractor Requirements (REQ-GO-*), Java Prime Contractor Requirements (REQ-JMP-*), `NodeLanguageProfile` in `languages/nodejs.py`, Online Boutique Node.js requirements (`requirements-nodejs.md`) and plan (`plan-nodejs.md`)
**Strategy:** Prime Contractor-first (same as Go — file-whole generation, not MicroPrime-first)

---

## 1. Context & Strategic Rationale

### 1.1 Background

The Prime Contractor workflow generates code for multi-file features. Prior runs targeted Python (~50 runs), Go (run-066), and Java (in progress via MicroPrime-first). No Node.js Prime Contractor runs have been attempted yet.

The Online Boutique Node.js microservices (currencyservice + paymentservice) are the validation target: 7 features, 10 output files, ~593 LOC across JavaScript, Dockerfile, and JSON.

### 1.2 Why Prime Contractor-First for Node.js

Node.js follows the **Go strategy** (Prime Contractor cloud-path first), not the Java strategy (MicroPrime-first), for the following reasons:

**1. No Python-native JS AST parser.**
Java has `javalang` (pure Python, in-process AST). Go has `gofmt -e` (subprocess, syntax only). Node.js has `node --check` (subprocess, syntax only) — no structural extraction from Python. A MicroPrime splicer would need regex-based parsing (like Go) but with significantly more syntactic ambiguity (closures, arrow functions, destructuring, template literals).

**2. No rigid file structure.**
Java enforces one-public-class-per-file. Go enforces `package` declarations. Node.js has no structural constraint — a file can export anything via `module.exports`, `exports.x`, or ESM `export`. Method-to-module ownership is ambiguous, making DFA skeleton assembly unreliable.

**3. Module system variance.**
CommonJS (`require`/`module.exports`) and ESM (`import`/`export`) coexist, often in the same project. The Online Boutique services use CommonJS exclusively, but a general Node.js pipeline must handle both. This doubles the patterns for import rendering, stub detection, and skeleton assembly.

**4. Low boilerplate ratio.**
Java's constructor/getter/setter/equals/hashCode/toString/Builder patterns are ideal for deterministic templates (8+ in `JAVA_TEMPLATES`). Node.js has minimal boilerplate — no getter/setter ceremony, no equals/hashCode, no explicit type declarations. Template ROI is low.

**5. File-whole generation quality is proven.**
Go run-066 demonstrated that file-whole LLM generation produces production-grade code for well-prompted non-Python targets. The LLM already knows Node.js idioms deeply. The Online Boutique services are ~60–200 LOC per file — well within LLM generation capacity.

**6. The validation target is small.**
10 files, ~593 LOC. File-whole generation is sufficient. MicroPrime's value (cost reduction via local models for element-level generation) is minimal for this scope.

### 1.3 Comparison: Pipeline Complexity by Language

| Pipeline Capability | Python | Go | Java | Node.js |
|---|---|---|---|---|
| Generation path | MicroPrime (element-level) | File-whole (cloud) | MicroPrime (element-level) | **File-whole (cloud)** |
| AST from Python | `ast.parse()` (in-process) | Regex (`go_parser.py`) | `javalang` (in-process) | **None** (subprocess only) |
| Syntax validation | `ast.parse()` | `gofmt -e` | `javalang.parse.parse()` | **`node --check`** |
| DFA skeletons | Full (assembler) | N/A | Full (assembler) | **N/A** |
| Splicer | AST-based | Text/brace-based | Text/brace-based | **N/A** |
| Templates | 12+ (dunder, dataclass) | None | 8+ (Java boilerplate) | **None** |
| Decomposition | Class + Function strategies | N/A | Class strategy | **N/A** |
| Import fixing | N/A (DFA renders) | `goimports` (excellent) | None (DFA must get it right) | **None** |
| Post-gen cleanup | Ruff lint | `goimports -w` | `google-java-format` (best-effort) | **None** (prettier possible) |

### 1.4 Node.js Language Profile — Current State

**File:** `src/startd8/languages/nodejs.py` (235 lines)

| Capability | Status | Implementation |
|-----------|--------|----------------|
| Language ID & display name | Done | `"nodejs"` / `"Node.js"` |
| Source extensions | Done | `[".js", ".mjs", ".cjs"]` |
| Build file patterns | Done | `["package.json", "package-lock.json", "yarn.lock"]` |
| Syntax check | Done | `node --check {file}` (per-file, no project context needed) |
| Lint | Disabled | ESLint if available; no built-in |
| Test | Done | `npm test` |
| Framework imports | Done | gRPC (`@grpc/grpc-js`), Express, Pino (logging) |
| Stdlib prefixes | Done | 38 prefixes (`assert` through `zlib`, plus `node:` prefix) |
| Post-generation cleanup | Disabled | Returns `[]` — no authoritative import fixer |
| Syntax validation | Done | `node --check` via temp file with graceful fallback |
| `package.json` generation | Done | `generate_dependency_file()` with `name@version` parsing |
| Docker images | Done | Builder: `node:20-alpine`, Runtime: `node:20-alpine` |
| Coding standards | Done | Modern JS: async/await, const, destructuring, no var |
| Merge strategy | Done | `"simple"` (whole-file replacement) |
| Repair | Enabled | `repair_enabled = True` |
| Stub patterns | Done | 3 patterns (`throw new Error("not implemented")`, `throw new Error("TODO")`, `// TODO`) |
| Function start pattern | Done | Regex matching `function Name(` with optional async/export |
| System prompt role | Done | `"an expert Node.js engineer"` |
| Import patterns | Done | Both CommonJS (`require('...')`) and ESM (`from '...'`) |

### 1.5 Gap Summary

| Area | What Exists | What's Missing |
|------|------------|----------------|
| **Generation path** | `.js`/`.mjs`/`.cjs` in `_NON_PYTHON_EXTENSIONS` — bypass works | Nothing (correct behavior) |
| **Syntax validation** | `node --check` in `NodeLanguageProfile` | Not wired into disk compliance validator |
| **Disk validation** | `_validate_json_file()` exists (generic) | No `.js`-specific validator, no `package.json`-specific validator |
| **System prompts** | Properties on profile (`system_prompt_role`, `coding_standards`) | Wiring into `spec_builder.py`/`drafter.py` unconfirmed for Node.js |
| **Framework detection** | `framework_imports` dict on profile (gRPC, Express, Pino) | Missing OTel, Cloud Profiler entries |
| **Cross-language guard** | `_detect_language_mismatch()` detects Python fingerprints | No Node.js fingerprints detected in non-JS files |
| **Postmortem** | Generic — non-Python files may default to 1.0 | No Node.js-specific scoring |
| **package.json template** | `generate_dependency_file()` exists | Not wired into template-match path |

---

## 2. Target Project Characteristics

### 2.1 Node.js Microservices (Online Boutique)

```
project-root/
├── src/
│   ├── currencyservice/
│   │   ├── server.js           (gRPC server, single-file)
│   │   ├── data/
│   │   │   └── currency_conversion.json
│   │   ├── package.json
│   │   ├── Dockerfile
│   │   └── proto/              (pre-provided, not generated)
│   └── paymentservice/
│       ├── index.js            (entry point + OTel/profiler init)
│       ├── server.js           (HipsterShopServer class)
│       ├── charge.js           (credit card validation)
│       ├── logger.js           (shared pino logger)
│       ├── package.json
│       ├── Dockerfile
│       └── proto/              (pre-provided, not generated)
```

### 2.2 File Type Distribution

| Type | Count | Pipeline Path |
|------|-------|--------------|
| `.js` | 6 | File-whole LLM generation |
| `.json` (data) | 1 | File-whole LLM generation |
| `package.json` | 2 | File-whole LLM or template generation |
| `Dockerfile` | 2 | File-whole LLM generation |
| **Total** | **11** | |

### 2.3 Node.js Module Patterns (CommonJS Only)

The Online Boutique services use CommonJS exclusively:

```javascript
// Import
const grpc = require('@grpc/grpc-js');
const HipsterShopServer = require('./server');
const { v4: uuidv4 } = require('uuid');

// Export
module.exports = HipsterShopServer;        // single export
module.exports = function charge(request) { ... };  // function export
```

No ESM (`import`/`export`) is used. The pipeline must handle CommonJS for this target but should not assume CommonJS-only for future Node.js projects.

---

## 3. Requirements

### 3.1 Generation Path (REQ-NODE-100 series)

#### REQ-NODE-100: File-Whole Generation for All Node.js Files

All Node.js source files (`.js`, `.mjs`, `.cjs`) MUST use file-whole LLM generation, not element-by-element MicroPrime decomposition.

**Rationale:** No Python-native JS AST parser exists. `node --check` validates syntax but cannot extract structural elements. File-whole generation is the correct path until a parser/splicer is built.

**Implementation:** `.js`, `.ts`, `.tsx`, `.jsx` are already in `_NON_PYTHON_EXTENSIONS`. No change needed.

**Status:** IMPLEMENTED

#### REQ-NODE-101: Non-Source File Generation

Non-source files in Node.js projects (`package.json`, `Dockerfile`, `.json` data files) MUST either:
1. Use file-whole LLM generation (for complex content), or
2. Use language-appropriate templates (for trivial content like `package.json` skeletons)

They MUST NOT receive Python skeleton stubs.

**Status:** IMPLEMENTED (REQ-MLT-100/101/102)

#### REQ-NODE-102: Node.js System Prompt Injection

The spec and draft prompts MUST include Node.js-specific context when the resolved language is Node.js:
- `system_prompt_role`: "an expert Node.js engineer"
- `coding_standards`: Modern JavaScript guidance (async/await, const, destructuring)
- Framework preamble based on detected frameworks (gRPC, Express, Pino, OTel)

**Acceptance criteria:**
- `spec_builder.py` checks `language_profile.system_prompt_role` and injects it when language is Node.js
- `drafter.py` includes `coding_standards` in the draft system prompt
- Framework imports from `framework_imports` are listed as available when relevant

**Status:** PARTIAL — Properties exist on `NodeLanguageProfile` but wiring into `spec_builder.py`/`drafter.py` is not confirmed for Node.js runs. The `spec_builder.py` already has a generic `language_profile` integration path (used for Go) — verify it works for Node.js language ID.

#### REQ-NODE-103: package.json Template Generation

When a `package.json` file is classified as TRIVIAL, generate it from seed metadata using `NodeLanguageProfile.generate_dependency_file()`.

**Inputs extracted from seed:**
- `service_name`: From seed task metadata or directory name
- `dependencies`: From seed task `dependencies` field (supports `name@version` format)

**Current state:** `generate_dependency_file()` exists and handles `@`-scoped packages correctly. Not wired into the template-match path.

**Status:** NOT IMPLEMENTED — `generate_dependency_file()` exists but is not wired into the template-match path. Currently, `package.json` files escalate to file-whole generation (acceptable fallback).

#### REQ-NODE-104: CommonJS vs ESM Detection

When generating Node.js code, the pipeline SHOULD detect the module system from project context:

| Signal | Module System |
|--------|--------------|
| `"type": "module"` in `package.json` | ESM |
| `"type": "commonjs"` or absent in `package.json` | CommonJS |
| `.mjs` extension | ESM |
| `.cjs` extension | CommonJS |
| `.js` extension | Follows `package.json` `type` field |

This detection SHOULD be injected into the spec prompt so the LLM generates correct `require`/`module.exports` or `import`/`export` syntax.

**Status:** NOT IMPLEMENTED — Low priority for Online Boutique (CommonJS only). Becomes relevant for future Node.js projects using ESM.

---

### 3.2 Validation & Scoring (REQ-NODE-200 series)

#### REQ-NODE-200: Node.js File Validation via node --check

Generated `.js` files SHOULD be validated via `node --check` when the Node.js runtime is available.

**Acceptance criteria:**
- `_validate_js_file()` added to `forward_manifest_validator.py`
- Uses `node --check` via temp file (same pattern as `NodeLanguageProfile.validate_syntax()`)
- Syntax errors recorded in `DiskComplianceResult.error`
- If `node` is not on PATH, validation falls back to text-based checks (non-empty, no Python fingerprints)
- Text-based fallback checks: non-empty content, contains at least one JS keyword (`function`, `const`, `let`, `var`, `require`, `import`, `export`, `class`, `module`), no Python fingerprints

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| `node --check` fails | False | 0.0 |
| Empty file | False | 0.0 |
| Python content detected | False | 0.0 |
| No JS keywords detected (fallback) | False | 0.3 |
| `node` not available, text checks pass | True | 0.8 |
| `node --check` passes | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-NODE-201: package.json Disk Validation

`validate_disk_compliance()` MUST validate `package.json` files beyond the generic JSON validator.

**Checks:**
- Valid JSON (inherits from `_validate_json_file()`)
- Contains `"name"` field (required by npm)
- Contains `"dependencies"` or `"devDependencies"` (expected for service packages)
- No Python content (cross-language guard — catches cases where pipeline writes a Python `setup.py` dict literal)
- Version strings are valid semver or semver ranges

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Invalid JSON | False | 0.0 |
| Missing `name` field | True | 0.3 |
| Missing both `dependencies` and `devDependencies` | True | 0.5 |
| Valid with `name` + dependencies | True | 1.0 |

**Implementation note:** Dispatch in `_validate_non_python_file()` by checking `name == "package.json"` (before the generic `.json` branch).

**Status:** NOT IMPLEMENTED

#### REQ-NODE-202: Cross-Language Content Detection for Node.js

Extend `_detect_language_mismatch()` to detect Node.js fingerprints in non-JS files.

**Node.js fingerprints to detect in non-JS files:**
- `require('` or `require("` (CommonJS import)
- `module.exports` (CommonJS export)
- `const ` followed by `= require(` on same line

**Python fingerprints already detected in JS files:**
- `from __future__` (existing)
- `def ` at line start (existing)
- `import os` / `import sys` (existing)
- `class .*:$` with colon (Python class syntax)

**Status:** PARTIAL — Python fingerprint detection exists. Node.js fingerprints in non-JS files not yet added.

#### REQ-NODE-203: Python-Stub Integration Guard for Node.js

The integration engine MUST block Python stubs from being written to `.js`/`.mjs`/`.cjs` target files.

**Status:** IMPLEMENTED — `_detect_python_stub_in_non_python()` in `integration_engine.py` already covers all non-Python extensions (2026-03-17).

---

### 3.3 Post-Generation Cleanup (REQ-NODE-300 series)

#### REQ-NODE-300: Prettier Execution (Best-Effort)

After generating `.js` files, the pipeline MAY run `prettier --write` to format the output if `prettier` is available on PATH.

**Rationale:** Unlike Go's `goimports` (which fixes imports and formatting) or Java's `google-java-format`, `prettier` only formats — it does not fix imports, add missing requires, or remove unused requires. Its value is cosmetic only.

**Priority:** P3 (low). File-whole LLM generation already produces reasonably formatted code.

**Fallback:** If `prettier` is not on PATH, skip with no warning. Unlike `goimports` (which is strongly recommended for Go), `prettier` is not essential for correctness.

**Status:** NOT IMPLEMENTED — `NodeLanguageProfile.post_generation_cleanup()` currently returns `[]`.

#### REQ-NODE-301: No Import Fixer Available

Unlike Go (`goimports`) and Python (ruff), Node.js has no CLI tool that reliably adds/removes `require` or `import` statements. Import correctness depends entirely on the LLM prompt and seed enrichment.

**Mitigation strategies:**
1. Seed enrichment includes dependency list in spec prompt
2. Framework detection injects canonical import patterns
3. Postmortem flags files with `require()` calls to non-existent modules (if `package.json` is available for cross-reference)

**Status:** ACKNOWLEDGED (no implementation needed — this documents a known limitation)

---

### 3.4 Framework Detection (REQ-NODE-400 series)

#### REQ-NODE-400: Extended Framework Imports

Extend `NodeLanguageProfile.framework_imports` with additional framework entries for the Online Boutique services and common Node.js patterns.

**New entries:**

| Framework Key | Detection Keywords | Dependencies | Import Pattern |
|---|---|---|---|
| `otel` | "opentelemetry", "OTel", "tracing" | `@opentelemetry/sdk-node`, `@opentelemetry/api` | `const opentelemetry = require('@opentelemetry/sdk-node')` + related |
| `profiler` | "profiler", "cloud profiler" | `@google-cloud/profiler` | `require('@google-cloud/profiler').start(...)` |
| `uuid` | "uuid", "transaction id" | `uuid` | `const { v4: uuidv4 } = require('uuid')` |
| `proto-loader` | "proto", "protobuf" | `@grpc/proto-loader` | (already in `grpc` entry) |

**Note:** The existing `grpc` entry already covers `@grpc/grpc-js` and `@grpc/proto-loader`. The `otel` and `profiler` entries are the primary gaps for Online Boutique generation.

**Status:** NOT IMPLEMENTED

#### REQ-NODE-401: Framework Preamble for Node.js gRPC Services

When a Node.js task targets a gRPC service (detected via dependency on `@grpc/grpc-js` or description keywords), the spec prompt MUST include:

- Proto loading pattern: `protoLoader.loadSync` with canonical options
- Health check registration pattern: `grpc.health.v1.Health.service`
- `ServerCredentials.createInsecure()` for dev environments
- `server.bindAsync` with callback pattern (not `server.bind` which is deprecated)

**Source:** `NodeLanguageProfile.framework_imports["grpc"]["imports"]` already contains the require statements. The preamble SHOULD also include usage patterns, not just imports.

**Status:** NOT IMPLEMENTED — Imports exist; usage pattern guidance does not.

---

### 3.5 Postmortem & Kaizen (REQ-NODE-500 series)

#### REQ-NODE-500: Non-Python Postmortem Accuracy for Node.js

The postmortem MUST NOT score Node.js files as 1.0 by default. Each file type must have at least a basic validator.

**File types requiring validators:**

| Type | Validator | Status |
|------|-----------|--------|
| `.js` | `_validate_js_file()` | **NOT IMPLEMENTED** (REQ-NODE-200) |
| `package.json` | `_validate_package_json()` | **NOT IMPLEMENTED** (REQ-NODE-201) |
| `.json` (data) | `_validate_json_file()` | Pre-existing |
| `Dockerfile` | `_validate_dockerfile()` | Pre-existing |

#### REQ-NODE-501: Language Mismatch Postmortem Pattern

Same as REQ-GO-501. When 2+ files in a run have `language_mismatch` errors, the postmortem MUST emit a cross-feature pattern.

**Pattern:** `language_mismatch_in_generation`
**Severity:** `high` (3+ files) or `medium` (2 files)
**Suggestion:** "Non-Python files received Python stubs. Check template-match routing for non-Python trivial tasks."

**Status:** NOT IMPLEMENTED (REQ-MLT-401)

#### REQ-NODE-502: package.json Dependency Cross-Check

When both `.js` source files and a `package.json` exist in the same service directory, the postmortem SHOULD cross-check:
- Every `require('pkg')` in `.js` files has a corresponding entry in `package.json` dependencies
- No unused dependencies in `package.json` (advisory only — some deps are runtime-only)

**Priority:** P3 (future enhancement — valuable for quality scoring but not blocking).

**Status:** NOT IMPLEMENTED

---

### 3.6 Seed Enrichment (REQ-NODE-600 series)

#### REQ-NODE-600: Node.js Project Context in Seeds

When plan ingestion detects a Node.js project (presence of `package.json` in plan or sibling `*.js` files), the seed enrichment SHOULD:

1. Set `language_hint: "nodejs"` on seed tasks targeting `.js` files
2. Include `package.json` dependencies in the task's `dependencies` field
3. Extract module system (`"type"` field from `package.json`) for prompt context
4. Detect framework usage from `package.json` dependencies for prompt preamble

**Status:** NOT IMPLEMENTED — Plan ingestion currently does not inspect `package.json` for Node.js project detection. The `language_hint` mechanism exists but may not be set automatically.

#### REQ-NODE-601: Dockerfile Context for Node.js Services

When a seed task targets a `Dockerfile` in a Node.js service directory, the spec prompt MUST include:
- The service's `package.json` dependency count (informs `npm install` stage)
- The entry point file (`main` field from `package.json`, or `server.js`/`index.js`)
- The expected `EXPOSE` port (from seed metadata or environment variable documentation)

**Rationale:** Run-066 showed that Dockerfiles are high-quality when the LLM has sufficient context. Node.js Dockerfiles follow a predictable multi-stage pattern (builder with `npm install`, runtime with `COPY --from=builder`).

**Status:** NOT IMPLEMENTED

---

## 4. Implementation Phases

### Phase 1: Validation & Disk Compliance (REQ-NODE-200, 201, 202, 500)

**Goal:** Accurate postmortem scoring for Node.js files. No generation changes.

**Deliverables:**
- `_validate_js_file()` in `forward_manifest_validator.py` — `node --check` with text fallback
- `_validate_package_json()` in `forward_manifest_validator.py` — name/deps/semver checks
- Dispatch wiring in `_validate_non_python_file()` for `.js` and `package.json`
- Node.js fingerprint detection in `_detect_language_mismatch()` (for non-JS files)

**Tests:** ~20
- `.js` validation: valid JS, invalid JS, empty, Python content, node not available
- `package.json` validation: valid, missing name, missing deps, invalid JSON, Python content
- Cross-language detection: Node.js fingerprints in HTML/YAML/Dockerfile

**Value:** Postmortem accuracy — `.js` and `package.json` files scored correctly instead of defaulting to 1.0 (generic JSON) or being unscored. Works immediately with existing cloud-path generation.

### Phase 2: System Prompts & Framework Detection (REQ-NODE-102, 400, 401)

**Goal:** LLM generates better Node.js code via language-aware prompts.

**Deliverables:**
- Verify `spec_builder.py` language_profile integration works for `language_id == "nodejs"`
- Extended `framework_imports` on `NodeLanguageProfile` (OTel, Cloud Profiler, UUID entries)
- Framework preamble includes usage patterns (gRPC proto loading, server setup)
- Coding standards injected into draft system prompt

**Tests:** ~10
- Framework detection with `@grpc/grpc-js`, `@opentelemetry/sdk-node` dependencies
- System prompt contains "Node.js engineer" when language is nodejs
- Import preamble uses `javascript` code fence (not `python`)

**Value:** Higher quality generated Node.js code. Framework-specific patterns reduce LLM hallucination. Directly improves Online Boutique run quality.

### Phase 3: Seed Enrichment & Template Wiring (REQ-NODE-103, 104, 600, 601)

**Goal:** Pipeline-level intelligence for Node.js projects.

**Deliverables:**
- `package.json` template generation wired into template-match path
- CommonJS vs ESM detection from `package.json` `type` field
- Node.js project detection in plan ingestion
- Dockerfile context enrichment for Node.js services

**Tests:** ~15
- `generate_dependency_file()` output matches expected `package.json` structure
- Module system detection from `package.json` `type` field
- Seed enrichment sets `language_hint: "nodejs"` for `.js` target files

**Value:** Pipeline understands Node.js project structure. Template generation for `package.json` avoids unnecessary LLM calls. Module system detection prevents CommonJS/ESM confusion.

### Phase 4: Post-Generation & Postmortem Enhancement (REQ-NODE-300, 501, 502)

**Goal:** Quality feedback loop for Node.js runs.

**Deliverables:**
- `prettier` best-effort post-generation formatting
- Language mismatch postmortem pattern (shared with Go — REQ-MLT-401)
- `package.json` ↔ `require()` dependency cross-check (advisory)

**Tests:** ~10
- Prettier formatting when available / graceful skip when not
- Postmortem pattern detection for language mismatch
- Dependency cross-check: missing dep, unused dep, all matched

**Value:** Quality scoring improvements. Language mismatch pattern prevents repeat failures across runs.

---

## 5. Implementation Status Summary

### Implemented (Pre-existing)

| REQ | Description |
|-----|-------------|
| REQ-NODE-100 | File-whole generation bypass (`.js` in `_NON_PYTHON_EXTENSIONS`) |
| REQ-NODE-101 | Non-source file protection (REQ-MLT-100/101/102) |
| REQ-NODE-203 | Python-stub integration guard |
| REQ-NODE-301 | No import fixer (acknowledged limitation) |

### Partially Implemented

| REQ | Description | Gap |
|-----|-------------|-----|
| REQ-NODE-102 | Node.js system prompt injection | Properties exist; wiring into spec/draft unconfirmed |
| REQ-NODE-202 | Cross-language detection | Python fingerprints detected; Node.js fingerprints in non-JS not added |

### Not Yet Implemented (by Phase)

| Phase | REQs | Effort | Dependencies |
|-------|------|--------|--------------|
| 1 | NODE-200, 201, 202, 500 | S | None |
| 2 | NODE-102, 400, 401 | S | None (can parallelize with Phase 1) |
| 3 | NODE-103, 104, 600, 601 | M | Phase 2 (framework detection) |
| 4 | NODE-300, 501, 502 | S | Phase 1 (validators) |

---

## 6. Test Coverage

### Current

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/unit/languages/test_protocol.py` | ~5 | Protocol conformance (includes Node.js) |
| `tests/unit/languages/test_registry.py` | ~3 | Entry point discovery |
| `tests/unit/languages/test_resolution.py` | ~2 | Language resolution |
| `tests/unit/micro_prime/test_non_python_bypass.py` | ~24 | Bypass mechanism (`.js` in bypass set) |
| **Total** | **~34** | |

### Needed (by Phase)

| Phase | Test File (Proposed) | Tests (Est.) |
|-------|----------------------|--------------|
| 1 | `test_nodejs_validation.py` | ~12 |
| 1 | `test_nodejs_disk_validators.py` | ~8 |
| 2 | `test_nodejs_framework_detection.py` | ~6 |
| 2 | `test_nodejs_system_prompts.py` | ~4 |
| 3 | `test_nodejs_seed_enrichment.py` | ~10 |
| 3 | `test_nodejs_package_json_template.py` | ~5 |
| 4 | `test_nodejs_postmortem.py` | ~5 |
| 4 | `test_nodejs_dep_crosscheck.py` | ~5 |
| **Total needed** | | **~55** |

---

## 7. Known Limitations

1. **No Python-native JS parser** — Cannot parse JavaScript source into an AST from Python. All JS validation is subprocess-based (`node --check`) or text/regex heuristic. This is the primary reason MicroPrime is not the initial strategy.

2. **No import fixer** — Unlike Go (`goimports`), Node.js has no CLI tool that reliably adds missing `require()` or removes unused imports. Import correctness depends entirely on LLM prompt quality and seed enrichment.

3. **Module system ambiguity** — CommonJS and ESM coexist. The pipeline must detect and respect the module system from project context. Generating ESM in a CommonJS project (or vice versa) will cause runtime errors.

4. **`node --check` requires Node.js** — Syntax validation falls back to text heuristics when `node` is not installed. Unlike `javalang` (pure Python, always available), `node --check` is best-effort.

5. **No struct/type extraction** — Go has `go_parser.py` (regex-based struct/function extraction). Java has `java_parser.py` (javalang-based class/method extraction). Node.js has no equivalent — structural analysis would require building a regex parser for JS syntax, which is significantly more complex due to closures, arrow functions, destructuring, and template literals.

6. **Scoped package naming** — npm packages like `@grpc/grpc-js` and `@opentelemetry/sdk-node` use `@scope/name` format. The `generate_dependency_file()` method handles this correctly (counting `@` occurrences), but other pipeline components that parse dependency names must also handle scoped packages.

---

## 8. Comparison: Node.js vs Go vs Java Pipeline Strategy

| Aspect | Go | Java | Node.js |
|--------|-----|------|---------|
| **Strategy** | Prime-first | MicroPrime-first | **Prime-first** |
| **Rationale** | No Python AST; strong CLI tools | Rigid structure; `javalang` AST | No Python AST; dynamic language |
| **Generation** | File-whole (cloud) | Element-level (local) | **File-whole (cloud)** |
| **Validation** | `gofmt -e` (subprocess) | `javalang.parse.parse()` (in-process) | **`node --check` (subprocess)** |
| **Import fixing** | `goimports` (excellent) | None (DFA renders) | **None** |
| **Templates** | None | 8+ (boilerplate-heavy) | **None** (low boilerplate) |
| **Decomposition** | N/A | Class-based | **N/A** |
| **DFA skeletons** | N/A | Full assembler | **N/A** |
| **Framework detection** | gRPC, HTTP, Logrus | Spring Boot, gRPC, JPA, SLF4J | **gRPC, Express, Pino, OTel** |
| **Estimated Phase 1-2 effort** | S (validation only) | M (javalang + DFA) | **S (validation + prompts)** |
| **Cost reduction potential** | Low (file-whole adequate) | High (templates + local gen) | **Low (file-whole adequate)** |
| **MicroPrime future** | Possible (parser exists) | Active (Phase 1-5) | **Unlikely (no parser path)** |

---

## 9. Relationship to Target Project Documents

This document defines **pipeline-side requirements** — what the SDK needs to support Node.js code generation. It is complemented by two target project documents:

| Document | Purpose |
|----------|---------|
| `requirements-nodejs.md` | Acceptance criteria for the Online Boutique Node.js services (REQ-NMS-001 through REQ-NMS-T02). Defines **what** to generate. |
| `plan-nodejs.md` | Implementation plan with feature contracts, LOC estimates, and validation criteria. Defines **how** the target code is structured. |
| **This document** (`NODE_PRIME_CONTRACTOR_REQUIREMENTS.md`) | Pipeline requirements for Node.js language support (REQ-NODE-100 through REQ-NODE-601). Defines **what the pipeline needs** to generate Node.js code successfully. |

The traceability chain is: Target requirements (REQ-NMS-*) → Target plan (F-001 through F-007) → Pipeline requirements (REQ-NODE-*) → Pipeline implementation.
