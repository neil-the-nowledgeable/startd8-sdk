# Node.js Prime Contractor — Implementation Plan

**Date:** 2026-03-17
**Status:** Draft
**Requirements:** `NODE_PRIME_CONTRACTOR_REQUIREMENTS.md` (REQ-NODE-100 through REQ-NODE-601)
**Strategy:** Prime Contractor-first (file-whole generation)

---

## Overview

Implement pipeline-side Node.js language support so that Prime Contractor can generate correct, scoreable Node.js code. The validation target is the Online Boutique Node.js microservices (currencyservice + paymentservice), defined in `requirements-nodejs.md` and `plan-nodejs.md`.

This plan covers 4 phases. Phases 1 and 2 are independent and can be parallelized. Phases 3 and 4 depend on earlier phases.

### What Already Works

Before starting, the following are already in place:

| Capability | Location | Status |
|-----------|----------|--------|
| `.js`/`.mjs`/`.cjs` bypass MicroPrime | `engine.py:_NON_PYTHON_EXTENSIONS` | Working |
| Python-stub guard for non-Python files | `integration_engine.py:_detect_python_stub_in_non_python()` | Working |
| `NodeLanguageProfile` (235 lines) | `languages/nodejs.py` | Working |
| `node --check` syntax validation | `NodeLanguageProfile.validate_syntax()` | Working |
| `package.json` generation | `NodeLanguageProfile.generate_dependency_file()` | Working |
| Node.js module section in spec builder | `spec_builder.py:_build_nodejs_module_section()` | Working |
| `language_role` + `coding_standards` injection | `drafter.py:get_drafter_system_prompt()` | Working |
| Language resolution for `.js` files | `languages/resolution.py:resolve_language()` | Working |
| Framework detection with `language_profile` | `framework_imports.py:detect_frameworks()` | Working |
| Python fingerprint detection | `forward_manifest_validator.py:_detect_language_mismatch()` | Working |
| Generic JSON validator | `forward_manifest_validator.py:_validate_json_file()` | Working |

### What Needs to Be Built

| Gap | Requirement | Phase |
|-----|-------------|-------|
| No `.js`-specific disk validator | REQ-NODE-200 | 1 |
| No `package.json`-specific disk validator | REQ-NODE-201 | 1 |
| No Node.js fingerprints in cross-language guard | REQ-NODE-202 | 1 |
| `framework_imports` missing OTel/Profiler entries | REQ-NODE-400 | 2 |
| No gRPC usage pattern preamble | REQ-NODE-401 | 2 |
| Spec builder module section defaults to ESM | REQ-NODE-102 (fix) | 2 |
| `package.json` template not wired into template path | REQ-NODE-103 | 3 |
| CommonJS/ESM detection from `package.json` | REQ-NODE-104 | 3 |
| No Node.js project detection in plan ingestion | REQ-NODE-600 | 3 |
| No Dockerfile context for Node.js services | REQ-NODE-601 | 3 |
| No `prettier` post-gen formatting | REQ-NODE-300 | 4 |
| No language mismatch postmortem pattern | REQ-NODE-501 | 4 |
| No `package.json` ↔ `require()` cross-check | REQ-NODE-502 | 4 |

---

## Phase 1: Disk Validation (REQ-NODE-200, 201, 202, 500)

**Goal:** Postmortem scores `.js` and `package.json` files accurately instead of defaulting to generic JSON/unscored.

**Depends on:** Nothing. Can start immediately.

### 1.1 Add `_validate_js_file()` to `forward_manifest_validator.py`

**File:** `src/startd8/forward_manifest_validator.py`

**Behavior:**
1. Check non-empty content
2. Check for Python fingerprints (handled by existing `_detect_language_mismatch()` first-pass)
3. Check for at least one JS keyword: `function`, `const`, `let`, `var`, `require`, `import`, `export`, `class`, `module`, `=>` (arrow function)
4. If `node` is on PATH: run `node --check` via temp file (reuse `NodeLanguageProfile.validate_syntax()` pattern)
5. If `node` not available: text-based pass with `contract_compliance = 0.8`

**Scoring table:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Empty file | `False` | `0.0` |
| No JS keywords (fallback) | `False` | `0.3` |
| `node --check` fails | `False` | `0.0` |
| `node` not available, text checks pass | `True` | `0.8` |
| `node --check` passes | `True` | `1.0` |

**Implementation pattern:** Follow `_validate_java_file()` structure — subprocess validation with text-based fallback.

```python
def _validate_js_file(
    content: str,
    result: DiskComplianceResult,
) -> DiskComplianceResult:
    """Validate JavaScript file via node --check with text-based fallback."""
    if not content.strip():
        result.ast_valid = False
        result.contract_compliance = 0.0
        result.error = "empty_file"
        return result

    # Text-based keyword check
    _JS_KEYWORDS = {"function", "const", "let", "var", "require",
                    "import", "export", "class", "module"}
    has_keyword = any(kw in content for kw in _JS_KEYWORDS) or "=>" in content
    if not has_keyword:
        result.ast_valid = False
        result.contract_compliance = 0.3
        result.error = "no_js_keywords"
        return result

    # Try node --check
    try:
        import subprocess
        import tempfile
        import os
        tmp = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False)
        try:
            tmp.write(content)
            tmp.flush()
            tmp.close()
            proc = subprocess.run(
                ["node", "--check", tmp.name],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode == 0:
                result.ast_valid = True
                result.contract_compliance = 1.0
            else:
                result.ast_valid = False
                result.contract_compliance = 0.0
                result.error = f"syntax_error: {proc.stderr.strip()[:200]}"
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    except FileNotFoundError:
        # node not installed — text-based pass
        result.ast_valid = True
        result.contract_compliance = 0.8
    except subprocess.TimeoutExpired:
        result.ast_valid = False
        result.contract_compliance = 0.0
        result.error = "node_check_timeout"
    except OSError as exc:
        result.ast_valid = True
        result.contract_compliance = 0.8
        result.error = f"node_check_unavailable: {exc}"

    return result
```

### 1.2 Add `_validate_package_json()` to `forward_manifest_validator.py`

**File:** `src/startd8/forward_manifest_validator.py`

**Behavior:**
1. Inherits from `_validate_json_file()` (valid JSON first)
2. Check for `"name"` field
3. Check for `"dependencies"` or `"devDependencies"`
4. Validate version strings are plausible (contain a digit — catches cases where a Python dict literal was written)

```python
def _validate_package_json(
    content: str,
    result: DiskComplianceResult,
) -> DiskComplianceResult:
    """Validate package.json beyond generic JSON."""
    import json
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError) as exc:
        result.ast_valid = False
        result.contract_compliance = 0.0
        result.error = f"invalid_json: {exc}"
        return result

    if not isinstance(data, dict):
        result.ast_valid = False
        result.contract_compliance = 0.0
        result.error = "package_json_not_object"
        return result

    result.ast_valid = True

    if "name" not in data:
        result.contract_compliance = 0.3
        result.error = "missing_name_field"
        return result

    has_deps = "dependencies" in data or "devDependencies" in data
    if not has_deps:
        result.contract_compliance = 0.5
        result.error = "missing_dependencies"
        return result

    result.contract_compliance = 1.0
    return result
```

### 1.3 Wire Dispatch in `_validate_non_python_file()`

**File:** `src/startd8/forward_manifest_validator.py`
**Location:** The `if/elif` chain starting at line ~540.

**Changes:**
- Add `name == "package.json"` check **before** the generic `.json` branch
- Add `suffix in (".js", ".mjs", ".cjs")` check

```python
# Existing dispatch (add two new branches):
    if name == "go.mod":
        result = _validate_go_mod(content, result)
    elif name == "package.json":                          # NEW — before .json
        result = _validate_package_json(content, result)
    elif suffix == ".in" or name == "requirements.txt":
        result = _validate_requirements_file(content, result)
        ...
    elif suffix in (".js", ".mjs", ".cjs"):               # NEW
        result = _validate_js_file(content, result)
    elif suffix == ".json":
        result = _validate_json_file(content, result)
    ...
```

### 1.4 Extend `_detect_language_mismatch()` with Node.js Fingerprints

**File:** `src/startd8/forward_manifest_validator.py`
**Function:** `_detect_language_mismatch()`

Add detection of Node.js/JavaScript fingerprints in non-JS files (Dockerfiles, YAML, HTML):

```python
# After existing Python fingerprint detection...
# Node.js fingerprints in non-JS files
if suffix not in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"):
    _NODE_FINGERPRINTS = [
        r"^\s*const\s+\w+\s*=\s*require\(",    # const X = require('...')
        r"^\s*module\.exports\s*=",             # module.exports = ...
        r"^\s*(?:import|export)\s+.*\s+from\s+['\"]",  # ESM import/export
    ]
    for pattern in _NODE_FINGERPRINTS:
        if re.search(pattern, content, re.MULTILINE):
            return f"nodejs_content_in_{suffix}_file"
```

### 1.5 Tests

**New file:** `tests/unit/validators/test_nodejs_disk_validators.py`

| Test | What It Validates |
|------|-------------------|
| `test_valid_js_file_with_node` | Valid JS passes `node --check` → compliance 1.0 |
| `test_invalid_js_syntax` | Syntax error → compliance 0.0 |
| `test_empty_js_file` | Empty → compliance 0.0 |
| `test_no_js_keywords` | Text with no JS keywords → compliance 0.3 |
| `test_js_validation_node_not_available` | FileNotFoundError fallback → compliance 0.8 |
| `test_python_content_in_js_file` | Python fingerprints caught by language mismatch |
| `test_valid_package_json` | Valid package.json → compliance 1.0 |
| `test_package_json_missing_name` | No `name` field → compliance 0.3 |
| `test_package_json_missing_deps` | No dependencies → compliance 0.5 |
| `test_package_json_invalid_json` | Broken JSON → compliance 0.0 |
| `test_package_json_not_object` | JSON array → compliance 0.0 |
| `test_package_json_dispatched_before_generic_json` | Verifies dispatch order |
| `test_nodejs_fingerprint_in_html` | `require(` in HTML detected |
| `test_nodejs_fingerprint_in_dockerfile` | `module.exports` in Dockerfile detected |
| `test_no_false_positive_in_js_file` | JS fingerprints in `.js` file NOT flagged |

**Estimated:** 15 tests

---

## Phase 2: Framework Detection & Prompt Wiring (REQ-NODE-102, 400, 401)

**Goal:** LLM produces higher-quality Node.js code via framework-aware prompts.

**Depends on:** Nothing. Can run in parallel with Phase 1.

### 2.1 Extend `NodeLanguageProfile.framework_imports`

**File:** `src/startd8/languages/nodejs.py`
**Property:** `framework_imports`

Add entries for OTel, Cloud Profiler, and UUID — the three framework patterns missing for Online Boutique:

```python
@property
def framework_imports(self) -> Dict[str, dict]:
    return {
        "grpc": {
            "detect": ["grpc", "proto", "protobuf", "gRPC"],
            "dep_names": {"@grpc/grpc-js", "@grpc/proto-loader"},
            "imports": [
                "const grpc = require('@grpc/grpc-js');",
                "const protoLoader = require('@grpc/proto-loader');",
            ],
            "conditional": {},
        },
        "otel": {                                          # NEW
            "detect": ["opentelemetry", "OTel", "tracing", "instrumentation"],
            "dep_names": {
                "@opentelemetry/sdk-node",
                "@opentelemetry/api",
                "@opentelemetry/instrumentation-grpc",
                "@opentelemetry/exporter-trace-otlp-grpc",
            },
            "imports": [
                "const opentelemetry = require('@opentelemetry/sdk-node');",
                "const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-grpc');",
                "const { GrpcInstrumentation } = require('@opentelemetry/instrumentation-grpc');",
                "const { registerInstrumentations } = require('@opentelemetry/instrumentation');",
            ],
            "conditional": {},
        },
        "profiler": {                                      # NEW
            "detect": ["profiler", "cloud profiler"],
            "dep_names": {"@google-cloud/profiler"},
            "imports": [
                "require('@google-cloud/profiler').start({serviceContext: {service: '<SERVICE_NAME>', version: '1.0.0'}});",
            ],
            "conditional": {},
        },
        "express": {
            "detect": ["express", "web server", "REST API"],
            "dep_names": {"express"},
            "imports": [
                "const express = require('express');",
            ],
            "conditional": {},
        },
        "logging": {
            "detect": ["pino", "winston", "log"],
            "dep_names": {"pino"},
            "imports": [
                "const pino = require('pino');",
            ],
            "conditional": {},
        },
        "uuid": {                                          # NEW
            "detect": ["uuid", "transaction id"],
            "dep_names": {"uuid"},
            "imports": [
                "const { v4: uuidv4 } = require('uuid');",
            ],
            "conditional": {},
        },
    }
```

### 2.2 Fix Module System Default

**File:** `src/startd8/implementation_engine/spec_builder.py`
**Function:** `_build_nodejs_module_section()` (line 470)

The default is currently `"esm"`. The Online Boutique services use CommonJS. The correct default for `package.json` without a `"type"` field is CommonJS (Node.js default).

**Change:**
```python
# Before:
    if not module_system:
        module_system = "esm"  # default

# After:
    if not module_system:
        module_system = "commonjs"  # Node.js default when package.json has no "type" field
```

### 2.3 Verify System Prompt Wiring

**Verification only — no code changes expected.**

The `prime_contractor.py` already populates the context with:
```python
gen_context["language_profile"] = language_profile
gen_context["language_role"] = language_profile.system_prompt_role
gen_context["coding_standards"] = language_profile.coding_standards
```

And `drafter.py:get_drafter_system_prompt()` injects these into the prompt template. Verify with a test that when `language_profile` is `NodeLanguageProfile`, the system prompt contains "Node.js engineer" and the coding standards mention "async/await".

### 2.4 Tests

**New file:** `tests/unit/languages/test_nodejs_framework_detection.py`

| Test | What It Validates |
|------|-------------------|
| `test_detect_grpc_from_deps` | `@grpc/grpc-js` in deps → `"grpc"` detected |
| `test_detect_otel_from_deps` | `@opentelemetry/sdk-node` in deps → `"otel"` detected |
| `test_detect_profiler_from_deps` | `@google-cloud/profiler` in deps → `"profiler"` detected |
| `test_detect_uuid_from_deps` | `uuid` in deps → `"uuid"` detected |
| `test_detect_pino_from_description` | "pino" in description → `"logging"` detected |
| `test_import_preamble_uses_javascript_fence` | Preamble contains ` ```javascript ` not ` ```python ` |
| `test_module_section_defaults_to_commonjs` | No module_system in context → CommonJS rules emitted |
| `test_module_section_esm_when_specified` | `module_system: "esm"` → ESM rules emitted |
| `test_system_prompt_contains_nodejs_role` | `language_role` = "an expert Node.js engineer" |
| `test_coding_standards_mention_async_await` | `coding_standards` contains "async/await" |

**Estimated:** 10 tests

---

## Phase 3: Seed Enrichment & Template Wiring (REQ-NODE-103, 104, 600, 601)

**Goal:** Pipeline understands Node.js project structure. Template generation for `package.json`.

**Depends on:** Phase 2 (framework detection).

### 3.1 Wire `package.json` Template into Template-Match Path

**File:** `src/startd8/micro_prime/engine.py` (or the template-match path in prime_adapter)

When a TRIVIAL-tier task targets a file named `package.json`, attempt to generate it via `NodeLanguageProfile.generate_dependency_file()` using seed metadata (`service_name`, `dependencies`).

**Guard:** Only when seed provides `dependencies` — if the dependency list is empty or absent, fall through to file-whole generation (the LLM will produce a better `package.json` than a bare skeleton).

**Implementation location:** This is in the Prime Contractor's template-match path, not MicroPrime (since `.json` is in `_NON_PYTHON_EXTENSIONS`). Check where `go.mod` template matching would go (REQ-GO-103, currently NOT IMPLEMENTED for Go either). The pattern will be the same for both.

### 3.2 CommonJS vs ESM Detection

**File:** `src/startd8/languages/nodejs.py`

Add a utility function:

```python
def detect_module_system(project_root: Path) -> str:
    """Detect CommonJS vs ESM from package.json type field.

    Returns "commonjs" or "esm". Defaults to "commonjs" (Node.js default).
    """
    import json
    pkg_path = project_root / "package.json"
    if not pkg_path.is_file():
        return "commonjs"
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        return "esm" if data.get("type") == "module" else "commonjs"
    except (json.JSONDecodeError, OSError):
        return "commonjs"
```

Wire into `prime_contractor.py` context building so `gen_context["module_system"]` is set before `_build_nodejs_module_section()` consumes it.

### 3.3 Node.js Project Detection in Plan Ingestion

**File:** `src/startd8/seeds/derivation.py` (or wherever `language_hint` is set during plan ingestion)

When the plan references `.js` files or `package.json`, set `language_hint: "nodejs"` on affected seed tasks. This ensures `resolve_language()` returns `NodeLanguageProfile` even when the dominant file count is ambiguous.

**Detection signals:**
- `package.json` in plan output files
- `.js`/`.mjs`/`.cjs` in plan output files
- Sibling `node_modules/` directory (if scanning existing project)
- Dependencies containing `@`-scoped npm packages

### 3.4 Dockerfile Context Enrichment

**File:** `src/startd8/implementation_engine/spec_builder.py` (or seed enrichment)

When a seed task targets a `Dockerfile` and the resolved language is Node.js, inject into the spec prompt:
- Entry point filename (from `package.json` `"main"` field or seed metadata)
- `EXPOSE` port (from seed environment variable docs)
- Multi-stage build hint with `npm install --only=production` pattern

This is prompt content, not code — add it to the Node.js module section or as a separate P1 section when the target file is a Dockerfile.

### 3.5 Tests

**New file:** `tests/unit/languages/test_nodejs_seed_enrichment.py`

| Test | What It Validates |
|------|-------------------|
| `test_detect_module_system_commonjs_default` | No `type` field → "commonjs" |
| `test_detect_module_system_esm` | `"type": "module"` → "esm" |
| `test_detect_module_system_no_package_json` | Missing file → "commonjs" |
| `test_detect_module_system_invalid_json` | Broken JSON → "commonjs" |
| `test_generate_dependency_file_scoped_packages` | `@grpc/grpc-js@1.14.3` → correct JSON |
| `test_generate_dependency_file_empty_deps` | Empty list → minimal package.json |
| `test_language_hint_set_for_js_files` | `.js` in target files → `language_hint: "nodejs"` |
| `test_language_hint_set_for_package_json` | `package.json` in plan → Node.js detected |
| `test_dockerfile_context_includes_entrypoint` | Dockerfile task gets entry point in prompt |

**Estimated:** 9 tests

---

## Phase 4: Post-Generation & Postmortem (REQ-NODE-300, 501, 502)

**Goal:** Quality feedback loop for Node.js runs.

**Depends on:** Phase 1 (validators must exist for postmortem scoring).

### 4.1 Prettier Post-Generation Formatting (Best-Effort)

**File:** `src/startd8/languages/nodejs.py`
**Method:** `post_generation_cleanup()`

```python
def post_generation_cleanup(self, files: List[Path], project_root: Path) -> List[str]:
    """Run prettier on generated JS files if available."""
    import shutil
    import subprocess

    prettier = shutil.which("prettier")
    if not prettier:
        return []

    formatted = []
    js_files = [f for f in files if f.suffix.lower() in (".js", ".mjs", ".cjs")]
    for f in js_files:
        try:
            subprocess.run(
                [prettier, "--write", str(f)],
                capture_output=True, timeout=30,
            )
            formatted.append(str(f))
        except (subprocess.TimeoutExpired, OSError):
            pass  # best-effort — skip on failure
    return formatted
```

**Priority:** P3. This is cosmetic-only and non-blocking.

### 4.2 Language Mismatch Postmortem Pattern (Shared)

**File:** `src/startd8/contractors/prime_postmortem.py`

This is REQ-MLT-401 — shared across Go, Java, and Node.js. When 2+ files in a run have `language_mismatch` in their error field, emit a cross-feature pattern:

```python
pattern = "language_mismatch_in_generation"
severity = "high" if mismatch_count >= 3 else "medium"
suggestion = (
    "Non-Python files received Python stubs. "
    "Check template-match routing for non-Python trivial tasks."
)
```

### 4.3 package.json ↔ require() Cross-Check (Advisory)

**File:** `src/startd8/forward_manifest_validator.py` (new function, called from postmortem)

When both `.js` source files and a `package.json` exist in the same service directory:
1. Extract all `require('pkg')` calls from `.js` files via regex
2. Extract `dependencies` keys from `package.json`
3. Flag `require` calls with no matching dependency (advisory warning, not a compliance failure)

**Priority:** P3. Useful for quality scoring but does not block runs.

### 4.4 Tests

**New file:** `tests/unit/validators/test_nodejs_postmortem.py`

| Test | What It Validates |
|------|-------------------|
| `test_prettier_formats_when_available` | prettier called on `.js` files |
| `test_prettier_skipped_when_unavailable` | No prettier → empty list returned |
| `test_prettier_timeout_handled` | Timeout → skip gracefully |
| `test_language_mismatch_pattern_emitted` | 3+ mismatches → high severity pattern |
| `test_require_crosscheck_missing_dep` | `require('uuid')` with no `uuid` in deps → warning |
| `test_require_crosscheck_all_matched` | All requires satisfied → no warnings |

**Estimated:** 6 tests

---

## Execution Order & Dependencies

```
Phase 1 (Validation)          Phase 2 (Prompts)
    │                              │
    │   (independent, parallel)    │
    │                              │
    ▼                              ▼
Phase 4 (Postmortem) ◄── Phase 3 (Seed Enrichment)
    depends on P1          depends on P2
```

**Recommended execution order:** Phase 1 → Phase 2 → Phase 3 → Phase 4

Or if parallelizing: (Phase 1 ∥ Phase 2) → Phase 3 → Phase 4

---

## Files Modified (Summary)

| File | Phase | Change |
|------|-------|--------|
| `src/startd8/forward_manifest_validator.py` | 1 | Add `_validate_js_file()`, `_validate_package_json()`, dispatch wiring, Node.js fingerprints in `_detect_language_mismatch()` |
| `src/startd8/languages/nodejs.py` | 2, 3, 4 | Extended `framework_imports`, `detect_module_system()`, `post_generation_cleanup()` |
| `src/startd8/implementation_engine/spec_builder.py` | 2 | Fix default module system from `"esm"` to `"commonjs"` |
| `src/startd8/contractors/prime_postmortem.py` | 4 | Language mismatch pattern emission |

## Files Created (Summary)

| File | Phase | Purpose |
|------|-------|---------|
| `tests/unit/validators/test_nodejs_disk_validators.py` | 1 | JS + package.json validators, cross-language fingerprints |
| `tests/unit/languages/test_nodejs_framework_detection.py` | 2 | Framework detection, prompt wiring, module system |
| `tests/unit/languages/test_nodejs_seed_enrichment.py` | 3 | Module system detection, template gen, seed enrichment |
| `tests/unit/validators/test_nodejs_postmortem.py` | 4 | Prettier, mismatch pattern, dep cross-check |

---

## Estimated Totals

| Metric | Value |
|--------|-------|
| Phases | 4 |
| Requirements covered | 16 (REQ-NODE-100 through 601) |
| Files modified | 4 |
| Files created | 4 (test files) |
| Tests | ~40 |
| Effort | S-M (Phase 1-2: S each; Phase 3: M; Phase 4: S) |

---

## Acceptance Criteria

### Phase 1 Complete When:
- `pytest tests/unit/validators/test_nodejs_disk_validators.py` passes
- A `.js` file with `def foo():` gets `ast_valid=False` with `language_mismatch` error
- A valid `package.json` scores `contract_compliance=1.0`
- A `package.json` missing `"name"` scores `contract_compliance=0.3`

### Phase 2 Complete When:
- `pytest tests/unit/languages/test_nodejs_framework_detection.py` passes
- `detect_frameworks(dependencies=["@opentelemetry/sdk-node"])` returns `["otel"]` when `language_profile` is `NodeLanguageProfile`
- `_build_nodejs_module_section()` emits CommonJS rules by default
- Import preamble uses ` ```javascript ` fence tag

### Phase 3 Complete When:
- `pytest tests/unit/languages/test_nodejs_seed_enrichment.py` passes
- `detect_module_system()` returns `"commonjs"` for `package.json` without `"type"` field
- Seed tasks targeting `.js` files get `language_hint: "nodejs"`

### Phase 4 Complete When:
- `pytest tests/unit/validators/test_nodejs_postmortem.py` passes
- `post_generation_cleanup()` calls prettier when available, returns `[]` when not
- Postmortem emits `language_mismatch_in_generation` pattern for 2+ mismatch files

### Full Pipeline Validation:
- Run Online Boutique Node.js services through Prime Contractor
- All 10 output files score `contract_compliance >= 0.8`
- No `language_mismatch` errors in postmortem
- Spec prompts contain Node.js module context section and framework preamble
