# Kaizen for Prime Contractor — Go Language Requirements

> **Version:** 1.1.0
> **Status:** DRAFT (post-implementation-planning review)
> **Date:** 2026-03-22
> **Previous:** 1.0.0 (2026-03-18)
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md)
> **Language Profile:** `GoLanguageProfile` (`src/startd8/languages/go.py`)
> **Related:** [MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md](MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md)
> **Scope:** Go-specific quality measurement, validation, and feedback for the Kaizen system

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

Go is the second most mature language in the Prime Contractor pipeline after Python. The `GoLanguageProfile` provides the foundation for Go code generation with text-based tooling (no AST module available in the SDK for Go).

### Current Capabilities

| Capability | Status | Implementation |
|-----------|--------|---------------|
| Post-gen cleanup (goimports/gofmt) | Implemented | `GoLanguageProfile.post_generation_cleanup()` |
| Syntax validation | Implemented | `GoLanguageProfile.validate_syntax()` via `gofmt -e` |
| Structure extraction (regex) | Implemented | `go_parser.py` — functions, types, methods, constants, variables |
| Body splicing (text-based) | Implemented | `go_splicer.py` — brace-matching splice with gofmt normalization |
| Stub detection | Implemented | `stub_patterns` property — `panic("not implemented")`, `// TODO` |
| Dependency file generation | Implemented | `generate_dependency_file()` — `go.mod` with require block |
| AST-based repair | Not available | `repair_enabled = True` (gates syntax/import repair, not AST) |
| MicroPrime element-level gen | Bypassed | File-whole generation via LLM |

### Key Advantages

- **goimports resolves the entire import validation problem.** It adds missing imports, removes unused imports, and formats the import block — all in a single tool invocation. This eliminates the need for the SDK to maintain import resolution logic for Go.
- **Compile-time strictness.** Go's compiler enforces no unused imports, no unused variables, and type correctness. Many errors that require AST-based validators in Python are caught by `gofmt -e` or `go vet` for free.
- **Regular syntax.** Go's brace-delimited declarations are regular enough that regex-based parsing covers ~90% of structural extraction (per `go_parser.py` header).

### Key Challenges

- **No AST-based repair.** All repair is text-based or tool-based (gofmt/goimports). The repair pipeline (`repair/`) is Python-AST-specific and cannot operate on Go source.
- **MicroPrime bypass.** Go tasks use file-whole generation, not element-by-element. This means the splicer and parser are available but not exercised through the standard MicroPrime path.
- **External tool dependency.** Validation and cleanup require `gofmt` and `goimports` on PATH. Without them, the SDK falls back to best-effort (assume valid).

### Run-066 Findings: Python Stub Contamination

Run-066 (first Go Prime Contractor run on online-boutique) revealed that **15/38 generated Go files contained Python stubs** (`from __future__ import annotations`). Root cause chain:

```
Trivial/simple Go tasks (HTML, go.mod, low-LOC .go files)
  → Routed through Python skeleton path (no Go template exists)
  → file_assembler renders Python skeleton for ALL files
  → validate_disk_compliance() sees non-.py suffix → returns default 1.0
  → Postmortem reports PASS with 0.96 aggregate (false positive)
```

This is documented in detail in [MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md](MULTI_LANGUAGE_TEMPLATE_AND_VALIDATION_REQUIREMENTS.md). The requirements in this document address Go-specific detection and prevention of this class of failure.

---

## 2. Disk Validation

### REQ-KZ-GO-100: Go Disk Compliance

Define a `validate_go_disk_compliance()` function (or extend `validate_disk_compliance()` with a Go branch) that performs the following checks on generated `.go` files:

**Syntax validity:**
- Run `gofmt -e {file}` — returns non-zero on syntax errors.
- If `gofmt` is not available, log a warning and skip (do not assume valid — score as UNKNOWN).

**Package declaration:**
- The first non-comment, non-blank line MUST be `package <name>`.
- Package name must be a valid Go identifier (lowercase, no hyphens).
- `main.go` files MUST declare `package main`.

**Cross-language contamination (critical):**
- Reject files containing ANY of the following Python artifacts:
  - `from __future__ import`
  - `import os` (bare Python import syntax, not Go `import "os"`)
  - `def ` followed by a function name and `(`
  - `class ` followed by a class name and `:`
  - `raise NotImplementedError`
  - `if __name__ == "__main__":`
  - `#!/usr/bin/env python`
- This check is binary: ANY match scores the file as 0.0 and classifies as CROSS_LANGUAGE_CONTAMINATION.

**Import block well-formedness:**
- Go import syntax: `import "pkg"` (single) or `import ( ... )` (block).
- No bare `import pkg` without quotes (Python syntax).
- No duplicate imports within a block.

**Function body completeness:**
- Count functions with empty bodies `func X() {}` or stub bodies (`panic("not implemented")`).
- Report stub count for quality scoring (see REQ-KZ-GO-300).

**Acceptance criteria:**
- `validate_go_disk_compliance()` returns a structured result with: `valid: bool`, `score: float`, `errors: List[str]`, `warnings: List[str]`, `root_causes: List[str]`.
- All `.go` files in a run are validated (not just `.py` files).
- Files with contamination get score 0.0, not the current default 1.0.

### REQ-KZ-GO-101: Go-Specific Validation Tools

The following external tools are available for Go validation, in order of preference:

| Tool | Purpose | Availability | Usage |
|------|---------|-------------|-------|
| `gofmt -e {file}` | Syntax check | Requires Go toolchain | `GoLanguageProfile.syntax_check_command` |
| `goimports -l {file}` | Import validation + format check | `go install golang.org/x/tools/cmd/goimports@latest` | Lists files with incorrect imports |
| `go vet ./...` | Semantic analysis | Requires Go toolchain + `go.mod` at cwd | Catches suspicious constructs |
| `go build ./...` | Compilation check | Requires Go toolchain + all dependencies | Heavyweight — optional, not default |

**Tool resolution order:**
1. `goimports` (preferred — fixes imports AND formats)
2. `gofmt` (fallback — formats only)
3. No tool available — log warning, score syntax as UNKNOWN (0.5, not 1.0)

**Note:** `go vet` and `go build` require `go.mod` at cwd, which is problematic in multi-service repos where `go.mod` lives in a subdirectory. These are optional and should only be used when the Go module root can be resolved.

### REQ-KZ-GO-102: go.mod Validation

`go.mod` files require a dedicated validator (they are not `.go` files but are critical to compilation):

**Required checks:**
- First line MUST be `module <path>` (e.g., `module github.com/user/repo`).
- `go <version>` directive MUST be present (e.g., `go 1.23`).
- No Python artifacts (same contamination check as REQ-KZ-GO-100).
- `require` block syntax valid (if present): `require ( ... )` with `\t<module> <version>` entries.
- No duplicate module entries in require block.

**Acceptance criteria:**
- `go.mod` files that contain `from __future__` score 0.0.
- Valid `go.mod` files score 1.0.
- Missing `module` or `go` directive scores 0.0.

---

## 3. Semantic Checks

### REQ-KZ-GO-200: Go Semantic Validators

Define Go-specific semantic check functions analogous to Python's `validators/semantic_checks.py`. These operate on source text (not AST) and are scored as warnings or errors:

**`check_missing_error_handling(source: str) -> List[Finding]`**
- Detect Go functions that return `error` as a return type where the caller assigns the result but discards the error with `_`.
- Pattern: `_, _ = SomeFunc(...)` or assignment without checking `if err != nil`.
- Severity: warning (Go convention strongly discourages ignoring errors, but it compiles).

**`check_unhandled_goroutine_errors(source: str) -> List[Finding]`**
- Detect `go func() { ... }()` or `go someFunc(...)` calls where the goroutine has no error channel, panic recovery, or logging.
- Severity: warning.

**`check_missing_package_declaration(source: str) -> List[Finding]`**
- File has no `package` keyword on any line.
- Severity: error (Go files cannot compile without a package declaration).

**`check_unused_imports(source: str) -> List[Finding]`**
- Imports not referenced in the code body.
- Note: `goimports` handles this automatically during cleanup, but detecting it pre-cleanup is useful for scoring.
- Severity: warning.

**`check_main_function_in_library(source: str) -> List[Finding]`**
- `func main()` declared in a file that also declares `package <non-main>`.
- Severity: error.

**`check_empty_interface_overuse(source: str) -> List[Finding]`**
- Count occurrences of `interface{}` or `any` used as parameter types, return types, or struct fields.
- Threshold: more than 3 uses in a single file triggers a warning.
- Severity: info.

### REQ-KZ-GO-201: Cross-Language Contamination Check

A dedicated, high-priority semantic check that flags Python syntax in Go files. This directly addresses the Run-066 root cause.

**Detection patterns (critical severity):**

| Pattern | Regex | What It Catches |
|---------|-------|-----------------|
| Python future import | `^from __future__ import` | Python stub contamination |
| Python bare import | `^import [a-z]\w+$` (no quotes) | `import os`, `import sys` |
| Python function def | `^def \w+\(` | Python function definitions |
| Python class def | `^class \w+[:\(]` | Python class definitions |
| Python raise | `raise \w+Error` | Python exception raising |
| Python main guard | `if __name__\s*==` | Python entry point guard |
| Python shebang | `^#!/usr/bin/env python` | Python shebang line |

**Scoring:** Binary — if ANY pattern matches, the file scores 0.0 for the contamination dimension. This overrides all other scoring because a Go file containing Python code is completely non-functional.

**Implementation note:** These patterns MUST use `re.MULTILINE` mode so `^` anchors match at line starts, not just file start.

---

## 4. Quality Scoring

### REQ-KZ-GO-300: Go Quality Score Formula

Define a Go-specific quality scoring formula for Kaizen metrics collection. The formula weights Go-relevant dimensions differently from Python because Go's toolchain catches many issues at compile time.

**Formula:**

```
go_quality_score = (
    compilation_check × 0.30
  + import_validity   × 0.20
  + stub_penalty      × 0.20
  + error_handling    × 0.15
  + contamination     × 0.15
)
```

**Dimension definitions:**

| Dimension | Score | Calculation |
|-----------|-------|-------------|
| `compilation_check` | 0.0–1.0 | 1.0 if `gofmt -e` passes, 0.0 if it fails. 0.5 if `gofmt` unavailable (UNKNOWN). |
| `import_validity` | 0.0–1.0 | 1.0 if no import issues after `goimports -l`. Proportional: `max(0, 1.0 - issues × 0.2)`. |
| `stub_penalty` | 0.0–1.0 | `max(0, 1.0 - stub_count × 0.15)` where stubs are `panic("not implemented")`, empty bodies, or `// TODO` function bodies. |
| `error_handling` | 0.0–1.0 | `max(0, 1.0 - unhandled_errors × 0.1)` where unhandled errors are `_` assignments on error-returning calls. |
| `contamination` | 0.0 or 1.0 | **Binary.** 0.0 if ANY Python artifact found (REQ-KZ-GO-201). 1.0 otherwise. Contamination is catastrophic — a Go file with Python code is 100% broken. |

**Key difference from Python scoring:** The contamination dimension is unique to non-Python languages and has a multiplicative effect: any contamination makes the file non-functional regardless of other dimensions.

**Aggregate file score:** If `contamination == 0.0`, the aggregate score MUST be capped at 0.0 regardless of other dimension scores. This prevents the weighted average from producing a misleading non-zero score for a completely broken file.

**Acceptance criteria:**
- Run-066's 15 contaminated files would score 0.0 (not 1.0).
- The run aggregate score would be approximately `23/38 × avg_go_score` (not 0.96).
- Score function is invoked for ALL `.go` files and `go.mod` files, not just `.py` files.

### REQ-KZ-GO-301: Go Root Causes

Extend the root cause taxonomy with Go-specific entries. These are used in Kaizen metrics, suggestions, and trend analysis.

| Root Cause ID | Description | Severity | Example |
|--------------|-------------|----------|---------|
| `CROSS_LANGUAGE_CONTAMINATION` | Python code in Go file | critical | `from __future__ import annotations` in `main.go` (Run-066) |
| `GO_COMPILATION_ERROR` | `gofmt -e` fails — syntax error | high | Missing closing brace, invalid type syntax |
| `MISSING_PACKAGE_DECLARATION` | No `package` line in `.go` file | high | File starts with `import` or `func` |
| `MISSING_ERROR_HANDLING` | Error return values ignored with `_` | medium | `_, _ = http.Get(url)` |
| `INVALID_GO_MOD` | Malformed `go.mod` file | high | Missing `module` directive, invalid `go` version |
| `EMPTY_FUNCTION_BODY` | Function with no implementation | medium | `func HandleRequest(w http.ResponseWriter, r *http.Request) {}` |
| `IMPORT_CYCLE` | Circular package imports | high | Package A imports B, B imports A |
| `MISSING_MAIN` | `cmd`/`main` package without `func main()` | high | `package main` file with no entry point |
| `STUB_BODY` | Function body is a placeholder | low | `panic("not implemented")`, `panic("TODO")` |
| `UNUSED_IMPORT` | Import not referenced in code | low | Caught by `goimports` but scored pre-cleanup |

**Integration:** These root causes feed into the Kaizen suggestion system (REQ-KZ-GO-500, REQ-KZ-GO-501) and cross-run trend analysis (parent REQ-KZ-400).

---

## 5. Repair Pipeline

### REQ-KZ-GO-400: Go Repair Capabilities

`GoLanguageProfile.repair_enabled = True` — this gates the syntax/import repair routes (`go_syntax_error`, `go_import_error`) in `repair/routing.py` which already work via `GoSyntaxValidateStep`. The SDK's Python-AST-based semantic repair steps cannot operate on Go source, but text-based repair steps (fence strip, bracket balance) and external tool validation (`gofmt`, `goimports`) are available through the standard repair pipeline.

**Available repairs via external tools:**

| Repair Step | Tool | What It Fixes | Availability |
|------------|------|--------------|-------------|
| Import fix | `goimports -w {file}` | Adds missing imports, removes unused, formats import block | Requires `goimports` on PATH |
| Format fix | `gofmt -w {file}` | Normalizes whitespace, indentation, braces | Requires Go toolchain |
| Fence strip | `FenceStripStep` | Removes markdown code fences from LLM output | **Already wired** — in Go `go_syntax_error` route |
| Syntax repair | (not available) | No Go equivalent of Python AST-based repair | Would require Go toolchain API |

**Already available (discovered during implementation planning):**

- **`FenceStripStep`** (`fence_strip`): Already language-agnostic and wired into Go's `go_syntax_error` route in `routing.py` line 94. Uses `extract_code_from_response()` from `startd8.utils.code_extraction`. **REQ-KZ-GO-402 is already satisfied** — no new step needed.
- **`GoSyntaxValidateStep`** (`go_syntax_validate`): Already checks `PYTHON_FINGERPRINTS` from `languages/_validation_utils.py` as a first-pass contamination gate, falling back to text heuristics when `gofmt` is unavailable. **Overlaps with `_check_python_contamination()` in `go_semantic_checks.py`** — see consolidation note below.

**Recommended additions:**

- **`go_format`**: Run `gofmt -w` as an explicit repair step (separate from post-gen cleanup). This normalizes formatting after any text-based repairs.

**Not recommended:**
- AST-based repair for Go. The Go compiler's error messages are specific enough that re-prompting the LLM with the error is more effective than attempting programmatic repair.

### REQ-KZ-GO-401: Post-Generation Cleanup

`GoLanguageProfile.post_generation_cleanup()` is already implemented and runs `goimports` (preferred) or `gofmt` (fallback) on all generated `.go` files.

**Sequencing requirement:** Cleanup MUST run BEFORE disk validation scoring. The current pipeline order is:

```
LLM generation → post_generation_cleanup() → validate_disk_compliance()
```

This is critical because `goimports` resolves import issues that would otherwise be scored as failures. The quality score should reflect the final file state after cleanup, not the raw LLM output.

**Cleanup scope:**
- `.go` files: `goimports -w` (preferred) or `gofmt -w` (fallback)
- `go.mod` files: Not processed by cleanup (no formatting tool needed)
- `go.sum` files: Not generated by the pipeline (created by `go mod tidy`)

**Fallback behavior:**
- If neither `goimports` nor `gofmt` is available, cleanup logs a warning and continues.
- Files that fail cleanup (non-zero exit from tool) are logged with the stderr message and continue to validation (they may still score well if the error is cosmetic).

### REQ-KZ-GO-402: Fence Strip for Go Files

**Status:** ALREADY SATISFIED. `FenceStripStep` is language-agnostic and already in the Go `go_syntax_error` route (`routing.py` line 94: `["fence_strip", "todo_uncomment", "bracket_balance", "go_syntax_validate"]`). Uses `extract_code_from_response()` which handles `` ```go ``, `` ```golang ``, and bare `` ``` `` fences.

No new implementation needed. Verify existing behavior with a Go-specific test case (see Verification Strategy).

### REQ-KZ-GO-402a: Fingerprint Pattern Consolidation (Quick Win)

**Problem discovered during implementation planning:** Python fingerprint patterns are defined in THREE independent locations:

| Location | Patterns | Used By |
|----------|----------|---------|
| `languages/_validation_utils.py:PYTHON_FINGERPRINTS` | `"def ", "import os", "from __future__", "print(", "self.", "#!/usr/bin/env python", "#!/usr/bin/python"` | `GoSyntaxValidateStep`, `JavaSyntaxValidateStep`, `CSharpSyntaxValidateStep` |
| `validators/go_semantic_checks.py:_PY_FINGERPRINTS` | `"def ", "import os", "from __future__", "print(", "self.", "#!/usr/bin/env python"` | `_check_python_contamination()` |
| `KAIZEN_GO_REQUIREMENTS.md` REQ-KZ-GO-100 | 7 patterns including `class `, `raise NotImplementedError`, `if __name__` | Requirements only (not yet implemented) |

**Issues:**
1. **Pattern drift:** `_validation_utils.PYTHON_FINGERPRINTS` has 7 entries; `go_semantic_checks._PY_FINGERPRINTS` has 6 (missing `#!/usr/bin/python`). The requirements list adds 3 more (`class `, `raise NotImplementedError`, `if __name__`). Three independent lists will diverge further.
2. **Scope duplication:** `GoSyntaxValidateStep` checks `PYTHON_FINGERPRINTS` as part of syntax validation. `_check_python_contamination()` checks a near-identical list as part of semantic validation. A contaminated file triggers both, producing redundant diagnostics.
3. **The `_PY_FINGERPRINTS` tuple is defined inside the function body** (line 166 of `go_semantic_checks.py`), making it inaccessible to the contamination strip repair step without import gymnastics or duplication.

**Requirements:**
1. **Single canonical fingerprint list:** Extract to `languages/_validation_utils.py:GO_CONTAMINATION_FINGERPRINTS` (superset of current patterns, including the REQ-KZ-GO-100 additions). Import in both `go_semantic_checks.py` and the contamination strip step.
2. **Deduplicate detection paths:** `GoSyntaxValidateStep` should NOT independently check contamination. It already delegates to `gofmt` (which catches real syntax errors) and text heuristics (balanced braces, package declaration). Remove the `PYTHON_FINGERPRINTS` check from `GoSyntaxValidateStep` — let `_check_python_contamination()` own contamination detection exclusively.
3. **Multi-match detection:** `_check_python_contamination()` currently `break`s after first match (line 178). The strip step needs to know ALL matching patterns to remove them. Change to collect all distinct matches, not just the first. This also improves postmortem reporting (shows which fingerprints appeared, not just "contaminated").

### REQ-KZ-GO-402b: Detection-Level False Positive Hardening

**Problem discovered during implementation planning:** The contamination false positive issue exists at the **detection** level, not just the repair level. `_check_python_contamination()` uses `if fp in source` — a whole-file substring search that cannot distinguish:

- `def ` inside a Go raw string literal: `` const help = `Use def to define...` ``
- `print(` inside a comment: `// print() is used in Python, not Go`
- `self.` inside a struct tag: `` `json:"self.id"` ``

The requirements (our earlier update) addressed this only for the repair step, but the detection itself produces false positive `SemanticIssue` entries that flow into postmortem reports, Kaizen suggestions, and quality scores.

**Requirements:**
1. **Line-level detection with context awareness:** Replace `if fp in source` with line-by-line scan that skips:
   - Lines inside backtick-delimited raw string literals (track toggle state)
   - Substrings after `//` on the same line (inline comments)
   - Content inside `/* ... */` block comments
2. **Anchor patterns where possible:** `"def "` should be `re.compile(r"^def \w+\(")` (start-of-line), `"import os"` should be `re.compile(r"^import \w+$")` (bare import, no quotes), to reduce false positives in string content.
3. **Preserve the binary scoring behavior:** ANY surviving match after context filtering still scores 0.0. The filtering reduces false positives, not sensitivity.

### REQ-KZ-GO-403: Go Semantic-to-Repair Bridge Convention

**Status:** Phase 1 (advisory-only; no Go repair steps yet)
**Depends on:** REQ-KZ-GO-400, REQ-KZ-GO-401, REQ-KZ-GO-402
**Analogous to:** REQ-KZ-CS-402a/b/c

Go semantic checks (`go_semantic_checks.py`) produce 6 diagnostic categories. This requirement defines how they integrate with the repair pipeline. Go lacks a Python-hosted AST layer, so deterministic repairs are limited to text-based transformations.

#### REQ-KZ-GO-403a: Multi-Language Dispatch

Add `".go"` to `_SEMANTIC_REPAIR_EXTENSIONS` when Phase 2 repair steps exist. Phase 1: `.go` is NOT dispatched to semantic repair.

**Implementation insight (from planning):** `orchestrator.py` currently has `_repair_single_file()` (Python, ~90 lines) and `_repair_single_csharp_file()` (~115 lines) with ~80% structural overlap (detect → translate → route → apply → verify → rollback). Adding `_repair_single_go_file()` as a third copy creates maintenance debt. **Preferred approach:** Extract a generic `_repair_single_lang_file(fpath, config, project_root, check_fn, language_id)` that takes a detection function as a parameter. Both C# and Go dispatch through it; Python keeps its existing path (uses `validate_disk_compliance()` not a direct check function). This also makes Java/Node.js semantic repair trivial to add later.

#### REQ-KZ-GO-403b: Category Registration

| Category | Severity | Phase 1 | Phase 2 | Rationale |
|---|---|---|---|---|
| `unchecked_error` | warning | Advisory | Advisory (Phase 3 candidate) | Simple case is text-repairable — see note below. |
| `duplicate_function` | warning | Advisory | Advisory | Requires human decision on which definition to keep. |
| `fmt_println_in_service` | warning | Advisory | Advisory | Requires import rewrite (`fmt` → `log`) + function replacement. |
| `dot_import` | warning | Advisory | **Repairable** | Text replacement: `import . "pkg"` → `import "pkg"` + `goimports -w`. |
| `python_contamination` | error | Advisory | **Repairable** | Line removal of Python artifacts + `gofmt -w` validation. |
| `package_dir_mismatch` | warning | Advisory | Advisory | Requires file/package rename with downstream effects. |

#### REQ-KZ-GO-403c: Compliance Results Collection

**Status:** IMPLEMENTED (2026-03-22). Go semantic results stored in `compliance_results`.

#### REQ-KZ-GO-403d: Phased Repair Step Plan

**Phase 1 (current):** All 6 categories advisory-only. Visible in postmortem/Kaizen. No repair dispatch for `.go` files.

**Phase 2:** Two deterministic text-based steps:
1. **`go_dot_import_cleanup`** — Regex `import . "pkg"` → `import "pkg"`, then `goimports -w` to qualify symbols. Rollback if `goimports` exits non-zero.
2. **`go_python_contamination_strip`** — Remove Python fingerprint lines, then `gofmt -w` to verify file still parses. Rollback on failure.

**Phase 3 candidate: `unchecked_error` text repair.** The requirements classify this as "requires AST transformation" but the planning deep-dive into `_check_unchecked_errors()` reveals the detection pattern is narrow: `err` assigned on line N, next non-blank line doesn't contain `if err != nil`. The simple repair is equally narrow: insert `if err != nil { return err }` after the assignment line. This covers the ~70% case (functions that return `error`). The regex detection already identifies the exact line number. Feasibility: text insertion at known line + `gofmt -w` normalization + rollback on failure. Risk is low because Go's compiler catches type mismatches if the inserted `return err` doesn't match the function signature. Classify as Phase 3 (after Phase 2 proves the Go repair infrastructure works).

Phase 2 activation: register both steps in `routing.py`, add `dot_import` and `python_contamination` to `_REPAIRABLE_CATEGORIES`, add `".go"` to `_SEMANTIC_REPAIR_EXTENSIONS`.

**Critical configuration requirement (discovered during implementation planning):** `RepairConfig.semantic_repair_categories` defaults to `frozenset()` (empty). Even after wiring the steps, **repair will not fire** unless the caller passes `semantic_repair_categories=frozenset({"dot_import", "python_contamination"})`. This must be set in:
- `PrimeContractorWorkflow` when constructing `RepairConfig` for Go runs
- Any script that calls `run_semantic_repair()` directly
- Default should include `python_contamination` unconditionally (severity: error, zero false-positive risk after REQ-KZ-GO-402b hardening)

**Phase 2 safety constraints:**

1. **`go_dot_import_cleanup` limitation:** `goimports` can only resolve symbols from stdlib and packages discoverable via the Go module system. If the dot-imported package is internal/custom and uses many bare exported symbols, `goimports` may fail to qualify them. Constraint: limit cleanup to stdlib-recognizable import paths (no dots in first path segment), OR add a pre-check that counts bare symbol usage and skips cleanup if the count exceeds a threshold (e.g., >10 unqualified symbol references).

3. **Step ordering when both issues co-occur:** If a file has both dot-imports AND Python contamination, `_CANONICAL_ORDER` determines execution sequence. `go_contamination_strip` MUST precede `go_dot_import_cleanup` in canonical order because: (a) contamination is higher severity (error vs warning), (b) removing Python lines may remove the dot-import line entirely (if the import block is itself a Python artifact like `import . "os"` mixed with `from __future__`), and (c) `goimports` (called by dot-import cleanup) will fail on a file that still contains Python syntax. The contamination strip runs first, then dot-import cleanup operates on the surviving Go-valid content.

2. **`go_python_contamination_strip` false positives:** Python fingerprint patterns (`def `, `import os`, `print(`, `self.`) can appear in Go string literals (e.g., backtick-delimited raw strings containing Python code samples) or in comments documenting Python interop. Constraint: skip matches that appear inside backtick-delimited string literals or that are preceded by `//` on the same line. The `gofmt -w` post-validation catches destructive removals, but prevention is preferred over rollback.

---

## 6. Feedback Loop Hints

### REQ-KZ-GO-500: Go-Specific Kaizen Hints

Define Go-specific hint text for the Kaizen feedback system. These hints are injected into the LLM prompt context when `kaizen-config.json` contains Go-targeted suggestions.

**Hint categories:**

| Category | Hint Text | When Triggered |
|----------|-----------|---------------|
| Error handling | "Always check and handle error returns in Go. Never use `_` for error values — handle or propagate every error with `if err != nil { return ..., err }`." | `MISSING_ERROR_HANDLING` root cause |
| Package organization | "One package per directory in Go. The package name must match across all `.go` files in the same directory. Use `package main` only for executable entry points." | `MISSING_PACKAGE_DECLARATION` root cause |
| Import management | "Use standard library imports first, then a blank line, then third-party imports. `goimports` handles this automatically — do not manually manage import ordering." | `UNUSED_IMPORT` root cause |
| Concurrency | "Use channels for goroutine communication. Protect shared state with `sync.Mutex`. Always handle errors from goroutines — use error channels or `errgroup`." | `UNHANDLED_GOROUTINE_ERRORS` root cause |
| Naming | "Exported Go symbols (functions, types, constants) start with uppercase. Unexported symbols start with lowercase. Use short, descriptive names: `srv` not `server`, `ctx` not `context`." | General Go generation |
| Testing | "Place tests in `*_test.go` files in the same package. Use `testing.T` for unit tests. Table-driven tests are idiomatic Go." | Test generation tasks |
| Interface design | "Accept interfaces, return structs. Keep interfaces small — one or two methods. Define interfaces where they are used, not where they are implemented." | Large interface generation |
| go.mod | "Always include `module <path>` and `go <version>` in `go.mod`. Do not add `go.sum` — it is generated by `go mod tidy`." | `INVALID_GO_MOD` root cause |
| Cross-language | "Generate Go code, NOT Python. Use `package`, `func`, `type`, `import \"pkg\"` — never `def`, `class`, `from X import`, `import X` (bare)." | `CROSS_LANGUAGE_CONTAMINATION` root cause |

### REQ-KZ-GO-501: Go CAUSE_TO_SUGGESTION Mappings

Map each Go root cause (REQ-KZ-GO-301) to a concrete suggestion with target phase, confidence level, and hint text.

| Root Cause | Target Phase | Suggestion | Confidence | Hint Key |
|-----------|-------------|------------|------------|----------|
| `CROSS_LANGUAGE_CONTAMINATION` | `spec` + `draft` | Add explicit "Generate Go code, not Python" instruction to spec and draft prompts | 0.95 | `cross_language` |
| `GO_COMPILATION_ERROR` | `draft` | Include Go syntax rules in draft prompt; re-prompt with `gofmt -e` stderr on failure | 0.80 | `compilation` |
| `MISSING_PACKAGE_DECLARATION` | `draft` | Include package name in spec context (derived from target file path) | 0.90 | `package_organization` |
| `MISSING_ERROR_HANDLING` | `draft` | Add error handling hint to draft system prompt | 0.70 | `error_handling` |
| `INVALID_GO_MOD` | `spec` | Include module path and Go version in spec context | 0.90 | `go_mod` |
| `EMPTY_FUNCTION_BODY` | `draft` | Request complete implementations, not stubs | 0.75 | `implementation_completeness` |
| `IMPORT_CYCLE` | `spec` | Restructure package dependencies in spec to avoid cycles | 0.60 | `package_organization` |
| `MISSING_MAIN` | `spec` | Verify that `cmd`/`main` packages include `func main()` in spec | 0.85 | `package_organization` |
| `STUB_BODY` | `draft` | "Provide complete function implementations — do not use panic(\"not implemented\")" | 0.80 | `implementation_completeness` |
| `UNUSED_IMPORT` | (none) | No action — `goimports` resolves this automatically | 0.99 | (auto-resolved) |
| `DUPLICATE_FUNCTION` | `draft` | "Do not declare the same function name twice in a single file. Check for existing definitions before generating a new one." | 0.85 | `duplicate_definition` |
| `DOT_IMPORT` | `draft` | "Do not use dot-imports (`import . \"pkg\"`). Always use explicit package-qualified access (e.g., `fmt.Println`, not `Println`)." | 0.80 | `dot_import_avoidance` |

**Implementation note:** All 6 Go semantic check categories (`unchecked_error`, `duplicate_function`, `fmt_println_in_service`, `dot_import`, `python_contamination`, `package_dir_mismatch`) MUST have entries in both `_SEMANTIC_CATEGORY_TO_SUGGESTION` and `CAUSE_TO_SUGGESTION` in `prime_postmortem.py`. Currently missing: `duplicate_function` → `duplicate_definition_detected` and `dot_import` → `dot_import_detected`.

**Confidence interpretation:**
- 0.90+ : Almost always the correct fix — inject hint unconditionally when root cause is detected.
- 0.70–0.89 : Usually correct — inject hint but track whether it actually reduces the root cause across runs.
- < 0.70 : Uncertain — inject hint only if trend analysis confirms benefit (requires 3+ runs).

---

## 7. Generation Profile

### REQ-KZ-GO-600: Go Generation Characteristics

Summary of Go's generation path through the Prime Contractor pipeline:

| Characteristic | Value | Notes |
|---------------|-------|-------|
| MicroPrime routing | **BYPASS** | File-whole generation via LLM, not element-by-element |
| Merge strategy | `"simple"` | Text-based, not AST merge (`GoLanguageProfile.merge_strategy_preference`) |
| Template matching | **Not implemented** | No Go templates in the template registry |
| Skeleton assembly | **Must produce Go** | Package declaration + import block + function signatures with `panic("not implemented")` |
| Post-gen cleanup | `goimports` + `gofmt` | `GoLanguageProfile.post_generation_cleanup()` |
| Dependency file | `go.mod` | `GoLanguageProfile.generate_dependency_file()` |
| Splicer | `go_splicer.py` | Text-based body splicing with brace matching |
| Parser | `go_parser.py` | Regex-based structure extraction (functions, types, methods, constants) |
| Repair | Syntax/import only | `repair_enabled = True` (no AST-based semantic repair) |
| Docker images | `golang:1.23-alpine` (build), `gcr.io/distroless/static` (runtime) | Multi-stage build pattern |
| System prompt | `"an expert Go engineer"` | `GoLanguageProfile.system_prompt_role` |
| Coding standards | Idiomatic Go (see profile) | `GoLanguageProfile.coding_standards` |

### REQ-KZ-GO-601: Go Template Requirements

Trivial Go tasks (tasks classified as TRIVIAL by the complexity classifier) MUST produce language-appropriate skeletons, NOT Python stubs. This is the primary prevention measure for Run-066.

**`.go` file skeleton:**
```go
package <name>

import (
	// imports will be added by goimports
)

// <FunctionName> — TODO: implement.
func <FunctionName>(<params>) <returns> {
	panic("not implemented")
}
```

**`go.mod` skeleton:**
```
module <module_path>

go 1.23
```

**`Dockerfile` skeleton (Go service):**
```dockerfile
# Build stage
FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /bin/service ./cmd/<service>

# Runtime stage
FROM gcr.io/distroless/static
COPY --from=builder /bin/service /bin/service
ENTRYPOINT ["/bin/service"]
```

**Routing requirement:** When the complexity classifier routes a task as TRIVIAL and the target file extension is `.go` or the filename is `go.mod`, the skeleton assembly path MUST:
1. Detect the target language from the file extension (`.go`) or filename (`go.mod`, `Dockerfile`).
2. Use the Go skeleton template (above) instead of the Python skeleton.
3. Populate the package name from the target file's directory context.
4. Populate the module path from `service_metadata` (if available).

### REQ-KZ-GO-602: Go Parser Integration with Kaizen

The regex-based Go parser (`go_parser.py`) extracts structural elements that Kaizen can use for quality assessment:

**Available element types from `parse_go_source()`:**

| Element Kind | GoElement Fields | Kaizen Use |
|-------------|-----------------|------------|
| `function` | name, signature, return_type, is_exported | Count exported API surface; detect missing error returns |
| `method` | name, signature, return_type, parent_type, receiver_name, is_pointer_receiver | Method coverage per type |
| `class` (struct/interface) | name, bases (embedded types), is_interface | Type hierarchy, interface compliance |
| `type_alias` | name, type_annotation | Type complexity |
| `constant` | name, type_annotation | API constant coverage |
| `variable` | name, type_annotation | Package-level var detection (potential smell) |

**Import extraction from `parse_go_imports()`:**
- Returns list of import path strings.
- Usable for dependency validation against `go.mod` require entries.

**Kaizen integration points:**
- Forward manifest population: `GoElement` maps to `ForwardElementSpec` for contract validation.
- Stub detection: Functions with `panic("not implemented")` bodies are identifiable via `go_parser.py` + `go_splicer._is_stub_body()`.
- Coverage metrics: Ratio of exported functions with doc comments (Go convention: all exported symbols should have comments).

### REQ-KZ-GO-603: Go Splicer Integration with Kaizen

The body splicer (`go_splicer.py`) provides splice statistics that feed quality metrics:

| Metric | Source | Kaizen Use |
|--------|--------|------------|
| `functions_spliced` | `GoSpliceResult.functions_spliced` | Count of successfully filled stubs |
| `functions_skipped` | `GoSpliceResult.functions_skipped` | Count of failed splices (body extraction failure, non-stub body) |
| `warnings` | `GoSpliceResult.warnings` | Diagnostic text for root cause analysis |

**Quality signal:** `splice_ratio = functions_spliced / (functions_spliced + functions_skipped)` — a splice ratio below 0.5 indicates the generated code is structurally incompatible with the skeleton.

---

## 8. Traceability Matrix

| Go Challenge | Requirements | Parent Kaizen Gap | Implementation Home |
|-------------|-------------|-------------------|---------------------|
| Python stub contamination (Run-066) | REQ-KZ-GO-100, 201, 300, 601 | K-1 (no prompt capture), K-3 (no feedback loop) | SDK: validators + templates |
| No Go disk validation | REQ-KZ-GO-100, 101, 102 | K-5a (no post-mortem parity for Go) | SDK: `validate_go_disk_compliance()` |
| No Go quality scoring | REQ-KZ-GO-300, 301 | K-2 (no cross-run aggregation) | SDK: Go scoring formula |
| No Go semantic checks | REQ-KZ-GO-200, 201 | K-4 (no quality correlation) | SDK: Go semantic validators |
| No Go **semantic** repair steps | REQ-KZ-GO-400, 402a, 402b, 403 | (new — Go-specific) | SDK: contamination strip + dot-import cleanup (syntax/import repair already exists) |
| No Go feedback hints | REQ-KZ-GO-500, 501 | K-3 (no feedback loop) | SDK + cap-dev-pipe: kaizen config |
| MicroPrime bypass for Go | REQ-KZ-GO-600, 601 | (new — Go-specific) | SDK: template registry + routing |
| Parser/splicer not scored | REQ-KZ-GO-602, 603 | K-5b (no archive index for Go) | SDK: Kaizen metrics integration |

---

## 9. Verification Strategy

### Unit Tests (startd8-sdk)

| Test | Validates | Test File |
|------|-----------|-----------|
| `test_go_disk_compliance_valid` | REQ-KZ-GO-100: Valid Go file scores 1.0 | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_disk_compliance_contaminated` | REQ-KZ-GO-100, 201: Python-contaminated Go file scores 0.0 | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_disk_compliance_no_package` | REQ-KZ-GO-100: Missing package declaration detected | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_mod_validation_valid` | REQ-KZ-GO-102: Valid go.mod scores 1.0 | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_mod_validation_contaminated` | REQ-KZ-GO-102: Python-contaminated go.mod scores 0.0 | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_quality_score_formula` | REQ-KZ-GO-300: Weighted score computed correctly | New: `tests/unit/languages/test_go_quality_scoring.py` |
| `test_go_quality_score_contamination_cap` | REQ-KZ-GO-300: Contamination caps score at 0.0 | New: `tests/unit/languages/test_go_quality_scoring.py` |
| `test_go_contamination_patterns` | REQ-KZ-GO-201: All Python patterns detected | New: `tests/unit/languages/test_go_disk_compliance.py` |
| `test_go_error_handling_check` | REQ-KZ-GO-200: Missing error handling detected | New: `tests/unit/languages/test_go_semantic_checks.py` |
| `test_go_root_cause_mapping` | REQ-KZ-GO-301: All root causes have suggestions | New: `tests/unit/languages/test_go_quality_scoring.py` |
| `test_go_template_skeleton` | REQ-KZ-GO-601: Go skeleton produced for .go trivial tasks | New: `tests/unit/languages/test_go_templates.py` |
| `test_go_mod_template_skeleton` | REQ-KZ-GO-601: go.mod skeleton produced (not Python) | New: `tests/unit/languages/test_go_templates.py` |
| `test_go_fence_strip_existing` | REQ-KZ-GO-402: Verify existing `FenceStripStep` handles `` ```go `` fences | Extend: `tests/unit/repair/test_go_repair_steps.py` |
| `test_fingerprint_consolidation` | REQ-KZ-GO-402a: Single canonical pattern list, no drift | New: `tests/unit/validators/test_fingerprint_consolidation.py` |
| `test_contamination_multi_match` | REQ-KZ-GO-402a: All fingerprints reported, not just first | Extend: `tests/unit/validators/test_go_semantic_checks.py` |
| `test_contamination_skip_raw_string` | REQ-KZ-GO-402b: `def ` inside backtick string not flagged | New: `tests/unit/validators/test_go_semantic_checks.py` |
| `test_contamination_skip_comment` | REQ-KZ-GO-402b: `import os` after `//` not flagged | New: `tests/unit/validators/test_go_semantic_checks.py` |
| `test_go_kaizen_all_6_categories` | REQ-KZ-GO-501: All 6 semantic categories have suggestion mappings | New: `tests/unit/contractors/test_go_kaizen_suggestions.py` |
| `test_semantic_repair_config_activation` | REQ-KZ-GO-403d: Repair fires when config includes Go categories | New: `tests/unit/repair/test_go_semantic_repair.py` |

### Existing Test Coverage

The following existing test files validate Go language support and should be extended (not replaced) for Kaizen integration:

| Test File | Current Coverage |
|-----------|-----------------|
| `tests/unit/languages/test_go_parser.py` | `parse_go_source()`: functions, methods, types, constants, variables, doc comments, imports |
| `tests/unit/languages/test_go_splicer.py` | `splice_go_bodies()`: brace matching, stub detection, body replacement, gofmt integration |
| `tests/unit/languages/test_go_stub_detection.py` | `stub_patterns`: panic stubs, TODO stubs, empty bodies |
| `tests/unit/languages/test_go_capabilities.py` | `GoLanguageProfile` property validation (extensions, commands, patterns) |
| `tests/unit/languages/test_go_wiring.py` | Language registry wiring, profile discovery |
| `tests/unit/micro_prime/test_go_language_support.py` | MicroPrime Go bypass behavior |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_go_run_quality_scoring` | REQ-KZ-GO-300: Full Go run produces correct aggregate score |
| `test_go_kaizen_suggestions` | REQ-KZ-GO-501: Root causes produce appropriate suggestions |
| `test_go_cleanup_before_validation` | REQ-KZ-GO-401: goimports runs before scoring |
| `test_go_trivial_routing` | REQ-KZ-GO-601: Trivial Go tasks produce Go skeletons, not Python |

### Implementation Order

**Quick wins (low effort, high value — discovered during implementation planning):**

0a. **Fingerprint consolidation** (REQ-KZ-GO-402a) — Extract single canonical `GO_CONTAMINATION_FINGERPRINTS` to `_validation_utils.py`, fix triple-definition pattern drift. ~30 min, eliminates a maintenance landmine.
0b. **Missing Kaizen suggestion mappings** (REQ-KZ-GO-501 gap) — Add `duplicate_function` → `duplicate_definition_detected` and `dot_import` → `dot_import_detected` to `CAUSE_TO_SUGGESTION` + `_SEMANTIC_CATEGORY_TO_SUGGESTION`. ~15 min, 4 dict entries, unlocks feedback for 2/6 Go categories.
0c. ~~**Fence strip repair**~~ (REQ-KZ-GO-402) — **Already satisfied.** `FenceStripStep` is language-agnostic and already in Go's `go_syntax_error` route. Zero work. Remove from backlog.
0d. **Multi-match contamination detection** (REQ-KZ-GO-402a item 3) — Remove `break` from `_check_python_contamination()`, collect all matching fingerprints. ~10 min, 2-line change, improves postmortem reporting and enables the strip step to see all patterns.

**P0 batch (Run-066 root cause):**

1. **Contamination detection hardening** (REQ-KZ-GO-100, 201, 402b) — Line-level detection with context awareness (skip raw strings, comments). Prevents false positives in quality scores.
2. **Quality scoring** (REQ-KZ-GO-300, 301) — Required for Kaizen metrics. Depends on contamination detection.
3. **Go template skeletons** (REQ-KZ-GO-601) — Prevents contamination at source.

**P1 (semantic repair pipeline):**

4. **Go semantic repair steps** (REQ-KZ-GO-403) — `go_contamination_strip` + `go_dot_import_cleanup`, bridge wiring, orchestrator generalization. Depends on quick wins 0a (shared patterns) and 0d (multi-match detection).
5. **RepairConfig activation** — Wire `semantic_repair_categories` for Go in `PrimeContractorWorkflow`. Without this, Phase 2 steps never fire.

**P2 (enrichment):**

6. **go.mod validation** (REQ-KZ-GO-102) — Complete Go project validation.
7. **Semantic checks** (REQ-KZ-GO-200) — Quality signal depth.
8. **Feedback hints** (REQ-KZ-GO-500, 501) — Requires production run data.
9. **Parser/splicer Kaizen integration** (REQ-KZ-GO-602, 603) — Metrics richness.
10. **Phase 3: `unchecked_error` text repair** (REQ-KZ-GO-403b) — Text-based `if err != nil` insertion for the simple case. Depends on Phase 2 proving the Go repair infrastructure.

Each step is independently valuable and can be shipped incrementally. Quick wins 0a-0d are pre-requisites that de-risk everything downstream. Steps 1-3 address the Run-066 root cause and should be treated as a single P0 batch.
