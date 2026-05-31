# Multi-Language Template Matching & Non-Python File Validation

**Date:** 2026-03-17 (Layers 1–4) · **Updated:** 2026-05-31 (Layer 5)
**Status:** Draft — Layers 1–4 implemented; Layer 5 false-positive hardening REQ-MLT-501/502/503/504 ✅ DONE, REQ-MLT-505 backlog open
**Author:** Human + Agent collaboration
**Derived From:** Run-066 (first Go Prime Contractor run) — 15/38 generated files contained Python stubs (`from __future__ import annotations`) instead of Go/HTML/go.mod content. Postmortem scored 0.96 (false **negative** — non-Python files defaulted to 1.0). **Layer 5** addresses the inverse (false **positives** on valid TS/TSX/JSONC/Go) found in run-005 and run-007.
**Priority:** P0 (template path), P1 (validation), P1 (Layer 5 false-positive hardening)

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

### Layer 5: Multi-Language False-Positive Hardening (run-005 / run-007)

> **Goal:** stop the *inverse* of the run-066 failure. Run-066 was a false **negative**
> (invalid non-Python files scored 1.0). Layers 5 addresses false **positives** —
> *valid* multi-language output wrongly failed — found in two later runs:
>   - **run-005:** valid `app/layout.tsx` failed the INTEGRATE checkpoint and valid TS/TSX
>     elements escalated, because `node --check` can't parse `.tsx` (Node ≥ 23) and `npx tsc`
>     install-noise was misread as a compile error. Fixed via REQ-NODE-MP-303/304/305
>     (`prime-contractor-node/NODEJS_MICROPRIME_REQUIREMENTS.md`).
>   - **run-007:** a flawless `tsconfig.json` (requirement_score 1.0) scored `FAIL:disk_quality`
>     because it was parsed as strict JSON, not JSONC.
>
> **Governing principle (REQ-MLT-500).** A validator MUST distinguish **"my tool/dialect/
> heuristic cannot handle this"** from **"the artifact is invalid."** The former degrades to a
> best-effort pass (or an advisory `warning`); only the latter sets `ast_valid=False` /
> `contract_compliance=0.0`. Every false positive below is an instance of conflating the two.
> This is the disk/syntax-validation analogue of the parser-confidence severity calibration in
> `MULTILANG_MANIFEST_VALIDATION_REQUIREMENTS.md` FR-5 ("never trade Python's
> false-negative-free enforcement for false positives elsewhere").

#### REQ-MLT-501: JSONC config files are not strict JSON — ✅ DONE (run-007)

`tsconfig.json`, `jsconfig.json`, `*.jsonc`, the `tsconfig.*.json` / `jsconfig.*.json` variant
families (`tsconfig.build.json`, `tsconfig.app.json`, `tsconfig.base.json`), VS Code configs
(`settings.json`, `launch.json`, `tasks.json`, `extensions.json`), and `.babelrc` / `.eslintrc.json`
are **JSONC** — `//` and `/* */` comments and trailing commas are legal. `_validate_json_file`
MUST retry these tolerantly (string-aware comment/trailing-comma strip) before failing. Plain
data `.json` stays strict; genuine errors in JSONC still fail.
*Impl:* `forward_manifest_validator.py::_strip_jsonc` + `_is_jsonc_filename`.

#### REQ-MLT-502: Contamination fingerprints MUST be statement-anchored, not substring — ✅ DONE

REQ-MLT-400 already specified anchored detection ("as first code line / first code construct"),
but the per-language file validators (`_validate_csharp_file`/`_validate_java_file`/`_validate_go_file`)
shipped a naive `if fp in content` substring scan. `self.` matches `window.self` / `obj.self` /
an identifier named `self`; `def ` matches text in strings/comments — all valid non-Python code,
zeroed to `ast_valid=False`. The fingerprint check MUST be line-anchored and comment-aware.
*Impl:* `languages/_validation_utils.py::detect_python_contamination` (shared, mirrors the correct
`nodejs_semantic_checks` logic), wired into all three file validators.

#### REQ-MLT-503: Version checks MUST never hard-error on a newer-than-baked-in version — ✅ DONE

A baked-in version *range* is a time-bomb: `_GO_VERSION_RANGE=(1,18,1,24)` hard-errored
(severity `error`) on the released `go 1.25` and on valid older `go 1.17`. Version validators
MUST accept any plausible current/future release (floor only, e.g. Go modules ≥ 1.11) and at most
**warn** (never error) on implausible values (Go 2 unreleased; absurd minors — likely
hallucinations). Applies to the `go`/`toolchain` directives and `golang:X.Y` Docker base images.
*Impl:* `validators/go_semantic_checks.py::_go_version_issue`.

#### REQ-MLT-504: TS/TSX syntax uses `tsc`, not `node --check`; tool-absence ≠ invalidity — ✅ DONE

`syntax_check_command` (the static `node --check {file}` template) MUST be `None` for Node so all
syntax checking flows through the extension-aware `validate_syntax`, which routes `.ts`/`.tsx` to
`tsc` (with a `.tsx` temp + `--jsx` for JSX) and treats a non-zero `tsc` exit as a failure only
when it carries a real `error TS\d+` diagnostic. Full spec: REQ-NODE-MP-303/304/305.

#### REQ-MLT-505: Calibration backlog (open — from the run-007 validation-code audit)

The audit that produced REQ-MLT-501/502/503 also catalogued lower-priority false-positive sources.
These remain **open**; each is an instance of REQ-MLT-500 (validator-incapacity treated as
invalidity) and most are amplified by the `ast_valid=False → 0.0` collapse (see the kaizen-scoring
note KZ-FP-1):

| ID | Location | Valid input wrongly failed | Sev | Fix direction |
|----|----------|----------------------------|-----|---------------|
| F2 | `_validate_yaml_file` | multi-doc (`---`) / custom-tag YAML (`!Ref`, `!vault`) raises `YAMLError` → score 0.0 | MED | `safe_load_all`; treat unknown-tag `ConstructorError` as well-formed |
| F6 | `_validate_html_file` | `{{ }}` balance check fires on Vue/Angular/Jinja/GHA `${{ }}` in plain HTML | MED | only run Go-template balance for `.gohtml`/`.tmpl` or `{{define}}` files |
| F7 | `_validate_requirements_file` | camelCase PyPI packages (`wxPython`, `PyMySQL`) flagged "not a package" | MED | advisory-only; resolve against known-package heuristic |
| F8 | `_validate_dockerfile` | builder-stage with no `CMD`/`ENTRYPOINT` deducted | MED | exempt builder stages / multi-`FROM` |
| F9 | `_digest_looks_fabricated` | real SHA256 digests probabilistically flagged "fabricated" (error) | LOW | require both signals or downgrade to warning |
| F10 | `nodejs._looks_like_typescript` | plain JS with `Array<T>` in a JSDoc/string routed to `tsc` | MED | only treat as TS on `.ts`/`.tsx` hint; heuristic as tiebreaker |
| F11 | `_count_stubs_text` | `// TODO:` comments in complete code counted as unimplemented stubs | LOW | separate "TODO comment" from "stub body" |
| F12 | `go._check_unchecked_errors` | `x, err := f(); return x, err` (most common Go idiom) flagged | MED | accept `return … err`, `errors.Is/As`, `require.NoError`, `_ = err` |
| F13 | `go._check_package_filepath_alignment` | pkg name ≠ dir name (valid, convention only) flagged | MED | advisory-only / case-variant only |
| F14 | `java._check_missing_access_modifiers` | interface methods (implicitly public) / package-private flagged | MED | skip interface/annotation scope; package-private = info |
| F16 | `csharp._check_missing_async_await` | `async Task` returning a Task without `await` flagged | MED | info, recognize `return Task`/`ValueTask` |
| F17 | `csharp._check_console_writeline` | `Console.WriteLine` in `Program.cs`/`Main` flagged (no entry-point exemption) | LOW | exempt `Program.cs`/`Main`/top-level statements (mirror Node/Java) |
| F18 | `observability_artifact_checks` | real Grafana JSON (`targets[].expr`, `fieldConfig…unit`) fails the flat-`panels[]` schema check | MED | detect native Grafana schema locations |

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
| MLT-500 | run-005/007 false positives | Governing principle: validator-incapacity ≠ artifact-invalidity |
| MLT-501 | run-007 tsconfig FAIL:disk_quality | JSONC ≠ strict JSON |
| MLT-502 | run-007 audit (F1) | Anchored, not substring, contamination fingerprints |
| MLT-503 | run-007 audit (F4) | No hard-error on newer-than-baked-in versions |
| MLT-504 | run-005 layout.tsx | TS/TSX via tsc; tool-absence ≠ invalidity (REQ-NODE-MP-303/304/305) |
| MLT-505 | run-007 validation-code audit | Calibration backlog (F2/F6–F18) |

---

## 7. Out of Scope

- **Go AST validation** — Python has no stdlib Go parser; use syntax checks via `go build` only when Go toolchain is available
- **CSS/JS validation** — Not encountered in run-066; defer until needed
- **Proto file validation** — `.proto` files not generated in this run; defer
- **Automatic go.mod dependency population** — `require` blocks with correct transitive deps require `go mod tidy`; out of scope for template generation
- **HTML semantic correctness** — Checking that template variables (`{{.product}}`) match handler payload is a future Kaizen correlation target, not a validation layer
