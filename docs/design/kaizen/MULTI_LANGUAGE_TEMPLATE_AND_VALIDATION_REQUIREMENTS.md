# Multi-Language Template Matching & Non-Python File Validation

**Date:** 2026-03-17
**Status:** Draft
**Author:** Human + Agent collaboration
**Derived From:** Run-066 (first Go Prime Contractor run) — 15/38 generated files contained Python stubs (`from __future__ import annotations`) instead of Go/HTML/go.mod content. Postmortem scored 0.96 (false positive — non-Python files defaulted to 1.0).
**Priority:** P0 (template path), P1 (validation)

---

## 1. Problem Statement

### What Happened (Run-066)

The Online Boutique Go microservices run generated 38 files:
- **23 Go files** — excellent quality, production-grade (via LLM generation)
- **4 Dockerfiles** — correct multi-stage builds (via LLM or template)
- **11 HTML templates** — `from __future__ import annotations` (Python stub)
- **4 go.mod files** — `from __future__ import annotations` (Python stub)

The 15 broken files share a common trait: they were routed as **trivial** ($0.00 cost, no LLM call) and received Python skeleton stubs because the template-match and skeleton-assembly paths are Python-only.

### Root Cause Chain

```
Plan ingestion assigns estimated_loc < 50 to HTML/go.mod tasks
  → Complexity classifier routes as TRIVIAL (non-supported-language LOC-only path)
  → MicroPrime _handle_trivial() attempts Python template match → no match
  → Escalation to _handle_simple() → file_assembler renders Python skeleton
  → Python skeleton emits `from __future__ import annotations` for ALL files
  → validate_disk_compliance() sees non-.py suffix → returns default 1.0 score
  → Postmortem reports PASS with 0.96 aggregate score
```

Two independent failures compound:
1. **Generation**: Non-Python trivial/simple files receive Python stubs instead of language-appropriate content
2. **Validation**: Non-Python files with no validator (HTML, go.mod) score 1.0 by default, masking the failure

### Impact

- 39% of generated files are non-functional (Python code in Go/HTML context)
- Postmortem false-positive rate: 15 files scored 1.0 that should score 0.0
- Go services cannot compile without valid `go.mod`
- Frontend cannot render without HTML templates

---

## 2. Design Philosophy

### Diagnose, Then Generate

Following the Semantic Validation v2 principle ("diagnose before you prescribe"), we split this into:

1. **Detect** — Validators that catch Python-stub-in-wrong-language (immediate, P0)
2. **Route** — Language-aware generation path that produces correct content (P0)
3. **Validate** — File-format validators for go.mod and HTML (P1)

### Minimal Viable Validators

Each non-Python validator should be lightweight and deterministic (no LLM calls). The goal is to catch catastrophic failures (wrong language, empty content, missing required structure) — not to validate semantic correctness.

### Extensibility via File-Type Dispatch

New validators follow the existing `_validate_non_python_file()` dispatch pattern in `forward_manifest_validator.py`. Each file type gets its own validator function, keeping the router thin and validators independent.

---

## 3. Requirements

### Layer 1: Language-Aware Template/Skeleton Path (P0)

> **Goal:** Non-Python files routed through trivial/simple tiers must not receive Python skeleton stubs.

#### REQ-MLT-100: Non-Python Trivial File Detection

The complexity classifier MUST identify files where the template-match system cannot produce language-appropriate output. When a file's language is not Python and no language-specific template exists, the file MUST NOT be routed through the Python skeleton assembly path.

**Acceptance criteria:**
- Files with extensions `.html`, `.go`, `.mod`, `.yaml`, `.yml`, `.json`, `.md`, `.txt`, `.in`, `.cfg`, `.toml` do not pass through `file_assembler.render_file()`
- `go.mod` files (no extension but filename match) are identified correctly

#### REQ-MLT-101: Language-Aware Skeleton Bypass

When MicroPrime encounters a non-Python file classified as TRIVIAL or SIMPLE that has no language-specific template, it MUST escalate to file-whole LLM generation rather than emitting a Python skeleton.

**Acceptance criteria:**
- Non-Python trivial files that fail template match escalate to file-whole generation (not Python skeleton)
- The escalation path uses the task's `target_files` to resolve language via `resolve_language()`
- Cost impact is acceptable: trivial files escalated to file-whole use the configured simple-tier model (Ollama/Haiku)

#### REQ-MLT-102: Python-Stub Cross-Language Guard

A safety check MUST prevent Python-specific content from being written to non-Python target files. This is a defense-in-depth guard independent of routing.

**Acceptance criteria:**
- Before writing a generated file to disk, check if the content starts with `from __future__` or contains only Python boilerplate when the target file extension is not `.py`
- If the guard triggers, log a WARNING and mark the file as failed (not silently accepted)
- Guard applies at the integration engine write site, not deep in MicroPrime (single choke point)

#### REQ-MLT-103: Go-Specific Trivial Templates

For Go files classified as TRIVIAL, provide minimal language-appropriate templates for common patterns:

| Pattern | Template Output | Match Condition |
|---------|----------------|-----------------|
| `go.mod` | `module {module_path}\n\ngo {go_version}\n` | Filename is `go.mod` |
| Empty `main.go` | `package main\n\nfunc main() {\n}\n` | File has single `main()` element, package `main` |
| Empty test file | `package {pkg}_test\n` | Filename ends `_test.go`, no elements |

**Acceptance criteria:**
- `go.mod` template extracts `module_path` from seed task metadata (falls back to directory-based inference: `github.com/{org}/{repo}/src/{service}`)
- `go_version` extracted from seed or defaults to `1.22` (current stable)
- Go templates validate via basic syntax check (no AST — Go has no stdlib AST in Python)
- Templates are registered in a new `GO_TEMPLATES` list alongside existing Python `TEMPLATES`

#### REQ-MLT-104: HTML Trivial Template

For HTML template files classified as TRIVIAL, provide a minimal Go `html/template`-compatible skeleton.

**Acceptance criteria:**
- HTML template files (`.html` in a `templates/` directory) receive a `{{define "name"}}...{{end}}` skeleton
- Template name derived from filename (e.g., `home.html` → `{{define "home"}}`)
- Body contains a placeholder comment: `<!-- TODO: implement {name} template -->`
- This is strictly a "better than Python stub" fallback — real content comes from LLM generation

---

### Layer 2: go.mod File Validation (P1)

> **Goal:** `validate_disk_compliance()` catches invalid `go.mod` files instead of scoring them 1.0.

#### REQ-MLT-200: go.mod Syntax Validator

Add a `_validate_go_mod()` function to the non-Python file dispatch in `forward_manifest_validator.py`.

**Acceptance criteria:**
- Dispatched when filename is `go.mod` (regardless of directory)
- Checks for the following required elements:

| Check | Severity | Rule |
|-------|----------|------|
| `module` directive present | Error | First non-comment, non-blank line must start with `module ` |
| `go` version directive present | Error | File must contain a line matching `go 1.\d+` (or `go \d+\.\d+`) |
| No Python content | Error | File must not contain `import`, `from __future__`, `def `, `class ` |
| Valid module path format | Warning | Module path should match `[\w./-]+` (no spaces, no Python package names) |

**Scoring:**
- Missing `module` directive → `ast_valid=False`, `contract_compliance=0.0`
- Missing `go` directive → `contract_compliance=0.5` (parseable but incomplete)
- Python content detected → `ast_valid=False`, `contract_compliance=0.0`, `error="python_content_in_go_mod"`
- All checks pass → `contract_compliance=1.0`

#### REQ-MLT-201: go.mod Require Block Validation

When a `require` block is present, validate its structure.

**Acceptance criteria:**
- Lines inside `require ( ... )` must match `\s+[\w./-]+ v[\d.]+` (module path + semver)
- Invalid require lines produce warnings (not errors) — LLM may use indirect deps
- Empty `require ()` block is valid (no dependencies)

---

### Layer 3: HTML File Validation (P1)

> **Goal:** `validate_disk_compliance()` catches non-HTML content in `.html` files.

#### REQ-MLT-300: HTML Content Validator

Add a `_validate_html_file()` function to the non-Python file dispatch.

**Acceptance criteria:**
- Dispatched when file extension is `.html` or `.htm`
- Checks for the following:

| Check | Severity | Rule |
|-------|----------|------|
| No Python content | Error | File must not contain `from __future__`, `import `, `def `, `class ` as first non-blank lines |
| Contains HTML-like content | Error | File must contain at least one of: `<`, `{{`, `{%`, or `<!DOCTYPE` |
| Non-empty | Error | File must have > 0 non-blank lines |
| Go template syntax valid | Warning | Matched `{{` must have corresponding `}}` (balanced pairs) |

**Scoring:**
- Python content detected → `ast_valid=False`, `contract_compliance=0.0`, `error="python_content_in_html"`
- No HTML-like content → `ast_valid=False`, `contract_compliance=0.0`, `error="no_html_content"`
- Empty file → `ast_valid=False`, `contract_compliance=0.0`
- Unbalanced template delimiters → `contract_compliance=0.8` (warning, content may still render)
- All checks pass → `contract_compliance=1.0`

#### REQ-MLT-301: Go Template Define Block Detection

For HTML files in a Go project context (sibling `go.mod` or `.go` files exist), validate Go `html/template` conventions.

**Acceptance criteria:**
- If Go project context detected, check for `{{define "name"}}` wrapper
- Missing `{{define}}` is a warning (not error) — some templates use `{{template}}` includes instead
- `{{define}}` without matching `{{end}}` → `contract_compliance=0.8`

---

### Layer 4: Cross-Language Content Detection (P1)

> **Goal:** Generic "wrong language" detector that catches Python-in-Go, Go-in-Python, etc.

#### REQ-MLT-400: Language Fingerprint Mismatch Detection

Add a generic content-vs-extension mismatch detector that runs for ALL non-Python files before delegating to file-specific validators.

**Acceptance criteria:**
- Detects Python fingerprints in non-Python files:
  - `from __future__ import` (strongest signal)
  - `import {name}` as first code line + `.py`-style patterns
  - `def ` or `class ` as first code constructs in non-Python files
- Detects Go fingerprints in non-Go files:
  - `package main` in `.html`, `.yaml`, `.json` files
  - `func ` declarations in non-Go files
- On mismatch: `ast_valid=False`, `contract_compliance=0.0`, `error="language_mismatch:{detected}_in_{expected}"`
- This check runs FIRST in `_validate_non_python_file()`, before file-type-specific validators

#### REQ-MLT-401: Postmortem Language Mismatch Pattern

When `_evaluate_disk_quality()` encounters 2+ files with `language_mismatch` errors, emit a cross-feature pattern:

**Pattern:** `language_mismatch_in_generation`
**Severity:** `high` (3+ files) or `medium` (2 files)
**Suggestion:** "Non-Python files received Python stubs. Check template-match routing for non-Python trivial tasks."

---

## 4. Implementation Scope

### Phase 1 (P0 — Unblocks Go runs)

| REQ | Effort | Files Modified |
|-----|--------|----------------|
| REQ-MLT-100 | S | `micro_prime/engine.py` |
| REQ-MLT-101 | M | `micro_prime/engine.py`, `complexity/router.py` |
| REQ-MLT-102 | S | `contractors/integration_engine.py` |
| REQ-MLT-400 | S | `forward_manifest_validator.py` |

**Rationale:** Phase 1 ensures non-Python files never get Python stubs (generation-side guard) and that any that slip through are caught (validation-side guard). This is sufficient to unblock the remaining 13 tasks in the Go batch.

### Phase 2 (P1 — Correct validation and templates)

| REQ | Effort | Files Modified |
|-----|--------|----------------|
| REQ-MLT-103 | M | `micro_prime/templates.py` (new `GO_TEMPLATES`), `micro_prime/engine.py` |
| REQ-MLT-104 | S | `micro_prime/templates.py` (new `HTML_TEMPLATES`) |
| REQ-MLT-200 | S | `forward_manifest_validator.py` |
| REQ-MLT-201 | S | `forward_manifest_validator.py` |
| REQ-MLT-300 | S | `forward_manifest_validator.py` |
| REQ-MLT-301 | S | `forward_manifest_validator.py` |
| REQ-MLT-401 | S | `contractors/prime_postmortem.py` |

**Rationale:** Phase 2 provides language-appropriate trivial templates (better defaults than LLM calls for simple files) and per-format validators that catch structural issues.

---

## 5. Test Plan

### Phase 1 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_non_python_trivial_escalates_to_file_whole` | MLT-100, MLT-101 | `.html` file classified TRIVIAL does not receive Python skeleton |
| `test_go_mod_trivial_escalates_to_file_whole` | MLT-100, MLT-101 | `go.mod` file classified TRIVIAL does not receive Python skeleton |
| `test_python_stub_guard_blocks_cross_language` | MLT-102 | `from __future__ import annotations` in `.go` target triggers warning and failure |
| `test_python_stub_guard_allows_python_files` | MLT-102 | `from __future__` in `.py` target is allowed (no false positive) |
| `test_language_mismatch_python_in_html` | MLT-400 | `from __future__` in `.html` → `contract_compliance=0.0` |
| `test_language_mismatch_python_in_go_mod` | MLT-400 | `import os` in `go.mod` → `contract_compliance=0.0` |
| `test_valid_html_passes_mismatch_check` | MLT-400 | `<html>...</html>` passes mismatch detector |
| `test_valid_go_mod_passes_mismatch_check` | MLT-400 | `module example.com/foo\n\ngo 1.22\n` passes |

### Phase 2 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_go_mod_template_match` | MLT-103 | `go.mod` TRIVIAL file receives `module`+`go` skeleton |
| `test_go_mod_template_extracts_module_path` | MLT-103 | Module path derived from seed metadata |
| `test_html_template_match` | MLT-104 | `.html` TRIVIAL file receives `{{define}}` skeleton |
| `test_go_mod_missing_module_directive` | MLT-200 | No `module` line → `ast_valid=False` |
| `test_go_mod_missing_go_directive` | MLT-200 | No `go 1.x` line → `contract_compliance=0.5` |
| `test_go_mod_with_python_content` | MLT-200 | Python stub → `contract_compliance=0.0` |
| `test_go_mod_valid_require_block` | MLT-201 | `require ( ... )` with valid entries → pass |
| `test_html_empty_file` | MLT-300 | Empty `.html` → `contract_compliance=0.0` |
| `test_html_no_html_content` | MLT-300 | Plain text in `.html` → `contract_compliance=0.0` |
| `test_html_with_go_template_syntax` | MLT-300 | `{{define "home"}}...{{end}}` → pass |
| `test_html_unbalanced_template_delimiters` | MLT-300 | `{{define "x"}}` without `{{end}}` → `contract_compliance=0.8` |
| `test_go_template_define_detection` | MLT-301 | Go project context + missing `{{define}}` → warning |
| `test_language_mismatch_pattern_emission` | MLT-401 | 3 files with mismatch → `language_mismatch_in_generation` pattern (high) |

---

## 6. Traceability

| REQ-MLT | Traces To | Rationale |
|---------|-----------|-----------|
| MLT-100–102 | KZ-Q4 (Kaizen validation doc) | Non-Python file format validation |
| MLT-103–104 | Run-066 template-match gap | Go/HTML trivial files need language-appropriate stubs |
| MLT-200–201 | Run-066 go.mod Python stubs | 4 go.mod files scored 1.0 with Python content |
| MLT-300–301 | Run-066 HTML Python stubs | 11 HTML templates scored 1.0 with Python content |
| MLT-400–401 | Postmortem false-positive rate | 15/38 files scored 1.0 incorrectly |

---

## 7. Out of Scope

- **Go AST validation** — Python has no stdlib Go parser; use syntax checks via `go build` only when Go toolchain is available
- **CSS/JS validation** — Not encountered in run-066; defer until needed
- **Proto file validation** — `.proto` files not generated in this run; defer
- **Automatic go.mod dependency population** — `require` blocks with correct transitive deps require `go mod tidy`; out of scope for template generation
- **HTML semantic correctness** — Checking that template variables (`{{.product}}`) match handler payload is a future Kaizen correlation target, not a validation layer
