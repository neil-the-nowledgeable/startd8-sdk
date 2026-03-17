# Go Prime Contractor — Requirements & Design

**Date:** 2026-03-17
**Status:** Active
**Derived From:** Run-066 (first Go Prime Contractor run, Online Boutique), `GoLanguageProfile` in `languages/go.py`, MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md (REQ-MLT-100–401)
**Project:** Online Boutique Go Microservices (4 services + shared packages)

---

## 1. Context

The Prime Contractor workflow generates code for multi-file features across a project. All prior ~50 runs targeted Python. Run-066 was the first Go run, generating gRPC microservices, HTML templates, Dockerfiles, and `go.mod` files for the Google Online Boutique demo.

### Run-066 Results

| File Type | Count | Quality | Issue |
|-----------|-------|---------|-------|
| `.go` files | 23 | A (production-grade) | None — proper OTel, gRPC, error handling |
| `Dockerfile` | 4 | A (multi-stage builds) | None |
| `.html` templates | 11 | F | Python stub (`from __future__ import annotations`) |
| `go.mod` | 4 | F | Python stub |

**Root cause:** Trivial-tier routing sent non-Python files through Python skeleton assembly. See REQ-MLT-100–102 for the fix (implemented 2026-03-17).

### Batch State

- **Batch ID:** `batch-c1566f89620e`
- **Total tasks:** 40 (from plan ingestion of 19 features)
- **Completed:** 27/40 (run-066)
- **Remaining:** 13
- **Estimated runs:** 1 more

---

## 2. Go Language Profile — Current State

**File:** `src/startd8/languages/go.py` (330 lines)

### Implemented Capabilities

| Capability | Status | Implementation |
|-----------|--------|----------------|
| Language ID & display name | Done | `"go"` / `"Go"` |
| Source extensions | Done | `[".go"]` |
| Build file patterns | Done | `["go.mod", "go.sum"]` |
| Syntax check | Done | `gofmt -e {file}` (per-file, no go.mod needed) |
| Lint | Disabled | `go vet` requires go.mod at cwd — multi-service repos break |
| Test | Disabled | `go test` same go.mod issue |
| Framework imports | Done | gRPC, HTTP/Gorilla/Mux, Logrus |
| Stdlib prefixes | Done | 42 prefixes (`bufio` through `unsafe`) |
| Post-generation cleanup | Done | `goimports -w` (preferred) or `gofmt -w` fallback |
| Syntax validation | Done | `gofmt -e` via temp file |
| `go.mod` generation | Done | `generate_dependency_file()` with module path, version, require block |
| Docker images | Done | Builder: `golang:1.23-alpine`, Runtime: `gcr.io/distroless/static` |
| Coding standards | Done | Idiomatic Go guidance in `coding_standards` property |
| Merge strategy | Done | `"simple"` (whole-file replacement) |
| Repair | Disabled | Go compiler validates; Python AST repair is not applicable |
| Stub patterns | Done | 5 patterns (`panic("not implemented")`, TODO comments, etc.) |
| Function start pattern | Done | Regex matching `func (receiver) Name(` |

### Supporting Libraries

| File | Purpose | Lines |
|------|---------|-------|
| `go_parser.py` | Regex-based Go structure extraction (funcs, types, methods, imports) | ~363 |
| `go_splicer.py` | Text-based body splicing with brace matching | ~100 |

---

## 3. Requirements

### 3.1 Generation Path (REQ-GO-100 series)

#### REQ-GO-100: File-Whole Generation for All Go Files

All Go source files (`.go`) MUST use file-whole LLM generation, not element-by-element MicroPrime decomposition.

**Rationale:** MicroPrime is Python-AST-based. Go files bypass it via `EscalationReason.NON_PYTHON_BYPASS` (REQ-MLT-101, implemented 2026-03-17).

**Status:** IMPLEMENTED

#### REQ-GO-101: Non-Source File Generation

Non-source files in Go projects (`go.mod`, `.html`, `Dockerfile`, `.yaml`, `.json`, `products.json`) MUST either:
1. Use file-whole LLM generation (for complex content), or
2. Use language-appropriate templates (for trivial content like `go.mod` skeletons)

They MUST NOT receive Python skeleton stubs.

**Status:** IMPLEMENTED (REQ-MLT-100/101/102)

#### REQ-GO-102: Go System Prompt Injection

The spec and draft prompts MUST include Go-specific context when the resolved language is Go:
- `system_prompt_role`: "an expert Go engineer"
- `coding_standards`: Idiomatic Go guidance (exported names, `if err != nil`, composition)
- Framework preamble based on detected frameworks (gRPC, HTTP, Logrus)

**Acceptance criteria:**
- `spec_builder.py` checks `language_profile.system_prompt_role` and injects it
- `drafter.py` includes `coding_standards` in the draft system prompt
- Framework imports from `framework_imports` are listed as available when relevant

**Status:** PARTIAL — Properties exist on `GoLanguageProfile` but wiring into `spec_builder.py`/`drafter.py` is not confirmed for Go runs.

#### REQ-GO-103: go.mod Template Generation

When a `go.mod` file is classified as TRIVIAL, generate it from seed metadata using `GoLanguageProfile.generate_dependency_file()`.

**Inputs extracted from seed:**
- `module_path`: From seed task `api_signatures` or directory structure inference
- `go_version`: From seed metadata or default `"1.23"`
- `dependencies`: From seed task `dependencies` field

**Status:** NOT IMPLEMENTED — `generate_dependency_file()` exists but is not wired into the template-match path. Currently, `go.mod` files escalate to file-whole generation (acceptable fallback).

#### REQ-GO-104: HTML Template Generation for Go Projects

HTML template files in Go frontend services MUST be generated with Go `html/template` syntax (`{{define "name"}}...{{end}}`).

**Acceptance criteria:**
- Seed enrichment detects Go project context (sibling `.go` files or `go.mod`)
- HTML spec prompt includes Go template syntax guidance
- Generated HTML uses `{{.FieldName}}` variable syntax (not Jinja `{{ field_name }}`)

**Status:** NOT IMPLEMENTED — HTML templates currently use file-whole generation. LLM produces correct Go template syntax when properly prompted (proven in run-066 for Go source files).

---

### 3.2 Validation & Scoring (REQ-GO-200 series)

#### REQ-GO-200: Go File Validation via gofmt

Generated `.go` files SHOULD be validated via `gofmt -e` when the Go toolchain is available.

**Acceptance criteria:**
- `validate_syntax()` on `GoLanguageProfile` is called during post-generation checkpoint
- Syntax errors logged as warnings (non-blocking — file may still be usable)
- If `gofmt` is not on PATH, validation is skipped with a warning (best-effort)

**Status:** IMPLEMENTED in `GoLanguageProfile.validate_syntax()`. Wiring into checkpoint depends on `_language_profile` being set on `IntegrationEngine`.

#### REQ-GO-201: go.mod Disk Validation

`validate_disk_compliance()` MUST validate `go.mod` files for:
- `module` directive present (required)
- `go` version directive present (required)
- No Python content (cross-language guard)
- Valid module path format
- Well-formed `require` block entries

**Scoring:**
| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Missing `module` directive | False | 0.0 |
| Missing `go` version | True | 0.5 |
| Python content detected | False | 0.0 |
| Valid | True | 1.0 |

**Status:** IMPLEMENTED (`_validate_go_mod()` in `forward_manifest_validator.py`, 2026-03-17)

#### REQ-GO-202: HTML Disk Validation

`validate_disk_compliance()` MUST validate `.html` files for:
- Non-empty content
- Contains HTML-like markers (`<`, `{{`, `{%`, `<!DOCTYPE`)
- No Python content (cross-language guard)
- Balanced Go template delimiters (`{{` vs `}}`)

**Scoring:**
| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Empty file | False | 0.0 |
| No HTML content | False | 0.0 |
| Python content | False | 0.0 |
| Unbalanced delimiters | True | 0.8 |
| Valid | True | 1.0 |

**Status:** IMPLEMENTED (`_validate_html_file()` in `forward_manifest_validator.py`, 2026-03-17)

#### REQ-GO-203: Cross-Language Content Detection

A universal language-mismatch detector MUST run before file-specific validators for all non-Python files.

Detects:
- Python fingerprints (`from __future__`, `import`, `def`, `class`) in non-Python files
- Go fingerprints (`package main`) in non-Go files (HTML, YAML, JSON)

**Status:** IMPLEMENTED (`_detect_language_mismatch()` in `forward_manifest_validator.py`, 2026-03-17)

#### REQ-GO-204: Python-Stub Integration Guard

The integration engine MUST block Python stubs from being written to non-Python target files.

**Status:** IMPLEMENTED (`_detect_python_stub_in_non_python()` in `integration_engine.py`, 2026-03-17)

---

### 3.3 Post-Generation Cleanup (REQ-GO-300 series)

#### REQ-GO-300: goimports Execution

After generating `.go` files, the pipeline MUST run `goimports -w` to:
- Add missing imports (resolves import audit issues without LLM retry)
- Remove unused imports (Go compiler requirement)
- Format import blocks (stdlib vs third-party grouping)

**Fallback:** `gofmt -w` if `goimports` is not installed.

**Status:** IMPLEMENTED in `GoLanguageProfile.post_generation_cleanup()`. Wiring into integration engine's post-generation hook is PARTIAL (depends on `_language_profile` being set).

#### REQ-GO-301: goimports Availability Warning

If neither `goimports` nor `gofmt` is found on PATH, the pipeline MUST:
1. Log a WARNING with install instructions (`go install golang.org/x/tools/cmd/goimports@latest`)
2. Continue without cleanup (do not fail the run)

**Status:** IMPLEMENTED

---

### 3.4 Multi-Service Project Handling (REQ-GO-400 series)

#### REQ-GO-400: Per-Service go.mod Recognition

The pipeline MUST recognize that Go microservice repos have per-service `go.mod` files (not a single root `go.mod`).

**Online Boutique structure:**
```
src/
├── shippingservice/
│   ├── go.mod          (module github.com/.../src/shippingservice)
│   ├── main.go
│   └── ...
├── productcatalogservice/
│   ├── go.mod          (module github.com/.../src/productcatalogservice)
│   ├── server.go
│   └── ...
├── frontend/
│   ├── go.mod          (module github.com/.../src/frontend)
│   ├── main.go
│   ├── handlers.go
│   ├── templates/      (HTML Go templates)
│   └── ...
└── checkoutservice/
    ├── go.mod
    ├── main.go
    └── money/          (shared package within service)
```

**Acceptance criteria:**
- Each service's `go.mod` specifies its own module path
- Cross-service imports use full module paths (not relative imports)
- `go build` and `go test` execute from the service directory, not project root

**Status:** PARTIAL — Plan ingestion correctly generates per-service `go.mod` tasks. But `go vet`/`go test` in checkpoint cannot run because they assume `go.mod` at project root.

#### REQ-GO-401: Protobuf/gRPC Stub Awareness

Go gRPC services reference generated protobuf stubs (e.g., `pb "github.com/.../genproto"`). The pipeline MUST:
1. Not flag `genproto` imports as phantom dependencies (they're build-time generated)
2. Include proto package paths in the seed's `dependencies` field
3. Generate correct `import pb "..."` statements in spec prompts

**Status:** PARTIAL — Run-066 generated correct proto imports in Go files. The seed enrichment includes proto package info. However, `genproto/` directories are not generated by the pipeline (assumed pre-existing or build-generated).

#### REQ-GO-402: Shared Package Dependencies

When multiple features within a service depend on a shared package (e.g., `frontend/money/`, `frontend/validator/`), the pipeline MUST:
1. Order generation so shared packages are generated before their consumers
2. Include the shared package's exports in consumer feature specs

**Status:** IMPLEMENTED via `FeatureQueue` dependency ordering in Prime Contractor.

---

### 3.5 Postmortem & Kaizen (REQ-GO-500 series)

#### REQ-GO-500: Non-Python Postmortem Accuracy

The postmortem MUST NOT score non-Python files as 1.0 by default. Each file type must have at least a basic validator.

**File types requiring validators:**

| Type | Validator | Status |
|------|-----------|--------|
| `.go` | `gofmt -e` syntax check | Implemented (best-effort) |
| `go.mod` | `_validate_go_mod()` | Implemented |
| `.html` | `_validate_html_file()` | Implemented |
| `Dockerfile` | `_validate_dockerfile()` | Pre-existing |
| `.yaml`/`.yml` | `_validate_yaml_file()` | Pre-existing |
| `.json` | `_validate_json_file()` | Pre-existing |
| `.in`/`requirements.txt` | `_validate_requirements_file()` | Pre-existing |

#### REQ-GO-501: Language Mismatch Postmortem Pattern

When 2+ files in a run have `language_mismatch` errors, the postmortem MUST emit a cross-feature pattern.

**Pattern:** `language_mismatch_in_generation`
**Severity:** `high` (3+ files) or `medium` (2 files)
**Suggestion:** "Non-Python files received Python stubs. Check template-match routing for non-Python trivial tasks."

**Status:** NOT IMPLEMENTED (REQ-MLT-401)

---

## 4. Implementation Status Summary

### Implemented (2026-03-17)

| REQ | Description | Commit |
|-----|-------------|--------|
| REQ-GO-100 | Non-Python bypass in MicroPrime | `_is_non_python_file()`, `NON_PYTHON_BYPASS` |
| REQ-GO-101 | Non-source file protection | REQ-MLT-100/101/102 |
| REQ-GO-200 | Go syntax validation | `GoLanguageProfile.validate_syntax()` |
| REQ-GO-201 | go.mod disk validation | `_validate_go_mod()` |
| REQ-GO-202 | HTML disk validation | `_validate_html_file()` |
| REQ-GO-203 | Cross-language detection | `_detect_language_mismatch()` |
| REQ-GO-204 | Python-stub integration guard | `_detect_python_stub_in_non_python()` |
| REQ-GO-300/301 | goimports post-generation | `GoLanguageProfile.post_generation_cleanup()` |
| REQ-GO-402 | Shared package ordering | `FeatureQueue` dependency resolution |

### Partially Implemented

| REQ | Description | Gap |
|-----|-------------|-----|
| REQ-GO-102 | Go system prompt injection | Properties exist; wiring into spec/draft builders unconfirmed |
| REQ-GO-400 | Per-service go.mod | Plan ingestion works; checkpoint `go vet`/`go test` blocked |
| REQ-GO-401 | Proto stub awareness | Imports correct; `genproto/` not generated |

### Not Implemented

| REQ | Description | Priority | Effort |
|-----|-------------|----------|--------|
| REQ-GO-103 | go.mod template generation | P2 | S |
| REQ-GO-104 | HTML template generation | P2 | S |
| REQ-GO-501 | Language mismatch postmortem pattern | P2 | S |

---

## 5. Test Coverage

| Test File | Tests | Covers |
|-----------|-------|--------|
| `tests/unit/micro_prime/test_non_python_bypass.py` | 24 | REQ-GO-100, REQ-GO-101 |
| `tests/unit/contractors/test_integration_engine_cross_language.py` | 8 | REQ-GO-204 |
| `tests/unit/validators/test_non_python_validators.py` | 26 | REQ-GO-201, REQ-GO-202, REQ-GO-203 |
| `tests/unit/languages/test_go_*.py` | ~20 | GoLanguageProfile, parser, splicer |
| **Total** | **~78** | |

---

## 6. Known Limitations

1. **No Go AST in Python** — Cannot parse Go source into an AST from Python. All Go validation is text/regex-based or delegates to `gofmt`/`goimports`.

2. **Multi-module checkpoint gap** — `go vet ./...` and `go test ./...` require `go.mod` at cwd. In multi-service repos, each service has its own `go.mod` in a subdirectory. Checkpoint currently runs from project root, so Go lint/test commands are disabled.

3. **MicroPrime bypass** — Go files skip element-by-element generation entirely. This means no template matching, no decomposition, no element-level repair. File-whole generation quality depends entirely on the LLM prompt.

4. **goimports availability** — Post-generation cleanup is best-effort. If `goimports` is not installed, imports are not fixed. The pipeline warns but does not fail.

5. **Protobuf generation** — The pipeline generates Go source that imports `genproto` packages but does not generate the proto stubs themselves. These must pre-exist or be generated by a separate `protoc` step.
