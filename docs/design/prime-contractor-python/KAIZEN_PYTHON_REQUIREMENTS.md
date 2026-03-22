# Kaizen for Prime Contractor — Python Language Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-18
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) (REQ-KZ-100–601)
> **Language Profile:** `PythonLanguageProfile` (`src/startd8/languages/python.py`)
> **Scope:** Python-specific quality measurement, validation, and feedback for the Kaizen system

---

## Table of Contents

1. [Overview](#1-overview)
2. [Disk Validation (extends Phase B)](#2-disk-validation-extends-phase-b)
3. [Semantic Checks (extends Phase D)](#3-semantic-checks-extends-phase-d)
4. [Quality Scoring (extends Phase E)](#4-quality-scoring-extends-phase-e)
5. [Repair Pipeline](#5-repair-pipeline)
6. [Feedback Loop Hints (extends Phase C / Layer 5)](#6-feedback-loop-hints-extends-phase-c--layer-5)
7. [Generation Profile](#7-generation-profile)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Verification Strategy](#9-verification-strategy)

---

## 1. Overview

Python is the most mature language in the Prime Contractor pipeline. It has full AST-based repair, Ruff linting, semantic validation, and the deepest integration with the Kaizen quality measurement system. All other language profiles (Go, Java, C#, Node.js) were modeled after the Python implementation.

This document codifies the Python-specific Kaizen behaviors that were previously implicit in the language-agnostic [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md). With Prime Contractor now supporting 5 languages, each language needs explicit requirements for:

- **Disk validation** — what tools and techniques verify generated code correctness
- **Semantic checks** — what deterministic AST-based checks catch "correct but wrong" code
- **Quality scoring** — how the composite quality score is computed
- **Repair** — what repair steps are available and in what order
- **Feedback hints** — what language-specific guidance feeds back into the next run

Python-specific Kaizen leverages the following toolchain:

| Tool | Purpose | Module |
|------|---------|--------|
| `ast.parse()` | Structural analysis, stub detection, semantic checks | stdlib `ast` |
| `py_compile.compile()` | Bytecode-level syntax validation | stdlib `py_compile` |
| Ruff (`ruff check --select E7,E9,F`) | Lint error detection and auto-fix | `PythonLanguageProfile.lint_command` |
| pytest | Test execution | `PythonLanguageProfile.test_command` |
| pip / pyproject.toml / requirements.txt | Dependency resolution | `PythonLanguageProfile.build_file_patterns` |

Shared Kaizen infrastructure (Layers 1-4 pipeline orchestration, Layer 6 prompt-quality correlation) is language-agnostic and documented in the parent requirements. This document covers **Layer 5 feedback**, **Phase B-E quality measurement**, and the **repair pipeline** as they apply to Python.

---

## 2. Disk Validation (extends Phase B)

### REQ-KZ-PY-100: Python Disk Compliance

`validate_disk_compliance()` in `forward_manifest_validator.py` is the reference implementation for Python disk validation. It only processes `.py` files (non-Python files are handled by `_validate_non_python_file()`).

The Python disk compliance check performs 10 validation layers in sequence:

| Layer | Check | Function | REQ ID |
|-------|-------|----------|--------|
| L0 | AST validity | `ast.parse()` (short-circuits on failure) | REQ-SV-100 |
| L0a | Stub counting | `_count_stubs()` — `raise NotImplementedError` and bare `pass` in function/method bodies | REQ-SV-100 |
| L0b | Duplicate definitions | `_count_duplicate_definitions()` — module-level only, not class methods | REQ-SV-100 |
| L1 | Import resolution | `_validate_import_resolution()` — ratio of resolvable imports vs total; closed-world mode when `import_map` provided | REQ-SV-201 |
| L2 | Cross-scope duplicates | `_detect_cross_scope_duplicates()` | REQ-SV-301 |
| L4 | Factory return values | `_validate_factory_returns()` — `create_*`, `make_*`, `build_*`, `*_factory` patterns | REQ-SV-501 |
| L6 | Discarded return values | `_validate_discarded_returns()` | REQ-SV-701 |
| L8 | Service identity | `_validate_service_identity()` — cross-file class/function name collision | REQ-SV2-400 |
| L9 | Method resolution | `_validate_method_resolution()` — `self.x()` where `x` is module-level, not a method | REQ-SV2-500 |
| L10 | Dead code / reachability | `_validate_reachability()` — module-level functions never called within the file | REQ-SV2-600 |

After validation layers, contract compliance is computed against the `ForwardManifest`:

- If a file spec exists in the manifest, elements and imports are checked against it
- `contract_compliance = max(0.0, 1.0 - (error_violations / total_checks))`
- `import_completeness = matched_imports / total_required_imports`

**Output:** `DiskComplianceResult` dataclass with 9 fields: `file_path`, `ast_valid`, `stubs_remaining`, `duplicate_definitions`, `import_completeness`, `contract_compliance`, `contract_violations`, `semantic_issues`, `error`.

### REQ-KZ-PY-101: Python-Specific Validation Tools

Python validation uses the following tools, configured in `PythonLanguageProfile`:

| Tool | Profile Property | Command |
|------|-----------------|---------|
| Syntax validation | `syntax_check_command` | `python3 -m py_compile {file}` |
| Lint checking | `lint_command` | `python3 -m ruff check {file} --select=E7,E9,F --output-format=concise` |
| Inline syntax check | `validate_syntax()` | `ast.parse(code)` — returns `(bool, str)` tuple |
| Test execution | `test_command` | `python3 -m pytest -v --tb=short -q` |

Import resolution resolves against three sources in priority order:
1. **Python stdlib** — `_PYTHON_STDLIB_PREFIXES` tuple (100+ entries in `python.py`) and `_STDLIB_MODULES` frozenset (in `semantic_checks.py`)
2. **Declared dependencies** — `requirements.txt` / `pyproject.toml` / `setup.py` / `setup.cfg` / `Pipfile` (from `build_file_patterns`)
3. **Local modules** — sibling files in the project, resolved via `sibling_files` parameter

The `package_alias_map` property provides PyPI-to-import name mappings (e.g., `Pillow` -> `PIL`, `beautifulsoup4` -> `bs4`) via `_PYPI_TO_IMPORT` from `implementation_engine/package_aliases.py`.

---

## 3. Semantic Checks (extends Phase D)

### REQ-KZ-PY-200: Python Semantic Validators

Four deterministic AST-based checks are implemented in `validators/semantic_checks.py`. All checks are pure AST analysis with no LLM calls.

| Check | Function | Severity | What It Catches |
|-------|----------|----------|-----------------|
| Duplicate main guards | `check_duplicate_main_guards()` | warning | Files with more than one `if __name__ == "__main__"` guard (lines reported) |
| Duplicate definitions | `check_duplicate_definitions()` | warning | Same function/class name defined twice at module level; class-level methods excluded |
| Bare except:pass | `check_bare_except_pass()` | warning | `except: pass` blocks that silently swallow all exceptions; `except Exception:` not flagged |
| Phantom dependencies | `check_phantom_dependencies()` | warning | Imports of packages not in `known_packages` set; imports inside `try/except ImportError` are skipped |

**Orchestrator:** `run_semantic_checks(source, known_packages, file_path)` runs all 4 checks and stamps `file_path` on each `SemanticIssue`. Returns empty list on `SyntaxError` (graceful degradation).

**Integration point:** `IntegrationEngine._run_semantic_checks()` calls the orchestrator after repair, before commit. Issues are logged as warnings (non-blocking).

### REQ-KZ-PY-201: Python-Specific Semantic Extensions (Planned)

The following extensions are planned for future implementation. Each would follow the same pattern: AST-based, deterministic, no LLM calls, returning `List[SemanticIssue]`.

| Extension | Description | Priority |
|-----------|-------------|----------|
| `check_circular_imports()` | Detect circular import chains across generated files within a single feature. Uses the `sibling_imports` mapping from `validate_disk_compliance()` to build an import graph and find cycles. | Medium |
| `check_type_annotation_completeness()` | Verify that all public functions (no leading `_`) have return type annotations and parameter type annotations. Uses `ast.FunctionDef.returns` and `ast.arg.annotation` nodes. | Low |
| `check_unused_imports()` | Flag imports that are never referenced in the file body. Supplements Ruff F401 for cases where Ruff is not available or not configured. | Low |
| `check_mutable_default_args()` | Flag the `def f(x=[])` anti-pattern. Checks `ast.FunctionDef.args.defaults` and `ast.FunctionDef.args.kw_defaults` for `ast.List`, `ast.Dict`, `ast.Set` nodes. | Low |

---

## 4. Quality Scoring (extends Phase E)

### REQ-KZ-PY-300: Python Quality Score Formula

The existing `compute_disk_quality_score()` in `prime_postmortem.py` IS the Python quality formula. It operates on a `DiskComplianceResult` and produces a float in `[0.0, 1.0]`.

**Formula:**

```
composite = (contract_compliance * 0.4)
          + (import_completeness * 0.2)
          + (stub_penalty * 0.2)
          + (semantic_penalty * 0.2)
```

**Component definitions:**

| Component | Weight | Computation | Range |
|-----------|--------|-------------|-------|
| `contract_compliance` | 0.4 | `max(0.0, 1.0 - (error_violations / total_checks))` | [0.0, 1.0] |
| `import_completeness` | 0.2 | `matched_imports / total_required_imports` | [0.0, 1.0] |
| `stub_penalty` | 0.2 | `max(0.0, 1.0 - stubs * 0.1)` — each unfilled stub deducts 0.1 | [0.0, 1.0] |
| `semantic_penalty` | 0.2 | `max(0.0, 1.0 - error_count * 0.3 - warning_count * 0.1)` — severity-weighted | [0.0, 1.0] |

**Short-circuit rules:**
- `compliance is None` -> 0.0
- `ast_valid == False` -> 0.0

**Derived metrics:**
- `FeaturePostMortem.disk_quality_score` — per-feature score
- `FeaturePostMortem.assembly_delta` — `requirement_score - disk_quality_score` (measures quality loss from design to assembly)
- `PrimePostMortemReport.avg_assembly_delta` — average delta across all features with non-None scores
- `assembly_quality_gap` cross-feature pattern — triggered when 2+ features show delta > 0.2; severity escalates to "high" at 3+ features

### REQ-KZ-PY-301: Python Root Causes

The `RootCause` enum in `prime_postmortem.py` defines 16 failure categories. Each has Python-specific manifestations:

| RootCause | Value | Python Manifestation | Pipeline Stage |
|-----------|-------|---------------------|----------------|
| `DUPLICATE_IMPORT` | `duplicate_import` | `from x import y` appearing multiple times; `import os` followed by `from os import path` | INTEGRATION |
| `UNFILLED_STUB` | `unfilled_stub` | `raise NotImplementedError` or bare `pass` in function/method body; detected by AST walk in `_count_stubs()` | INTEGRATION |
| `SCOPE_CORRUPTION` | `scope_corruption` | Indentation errors causing functions to nest inside other functions; class methods placed at module level; `IndentationError` from `ast.parse()` | SPLICER |
| `PHANTOM_IMPORT` | `phantom_import` | Import of module not in `requirements.txt`, stdlib, or local project; e.g., `import flask` when only `fastapi` is declared | INTEGRATION |
| `SKELETON_MISSING` | `skeleton_missing` | Target `.py` file not generated at all; skeleton assembly failed to create the file before code generation | SKELETON |
| `OLLAMA_TIMEOUT` | `ollama_timeout` | Ollama generation exceeded timeout (default 300s); typically large Python files or complex class hierarchies | OLLAMA_GENERATION |
| `OLLAMA_EMPTY_RESPONSE` | `ollama_empty_response` | Ollama returned empty string or whitespace-only response for a Python element | OLLAMA_GENERATION |
| `OLLAMA_CIRCUIT_BREAKER` | `ollama_circuit_breaker` | Circuit breaker tripped after repeated Ollama failures; batch abandoned | OLLAMA_GENERATION |
| `REPAIR_EXHAUSTED` | `repair_exhausted` | All 18 Python repair steps attempted but code still fails validation; typically cascading syntax errors | REPAIR |
| `SPLICER_MISMATCH` | `splicer_mismatch` | AST splicer could not find the target anchor (function/class name) in the existing file; generated code uses different names than the skeleton | SPLICER |
| `TIER_ESCALATION` | `tier_escalation` | Element classified as SIMPLE but required MODERATE/COMPLEX generation; decomposer could not break it down further | CLASSIFICATION |
| `AST_FAILURE` | `ast_failure` | `SyntaxError` from `ast.parse()` after all repair steps; malformed Python output from LLM | REPAIR |
| `SIZE_REGRESSION` | `size_regression` | Generated file significantly larger than original; LLM rewrote the entire file instead of surgical edit | INTEGRATION |
| `GENERATION_ERROR` | `generation_error` | Generic generation failure — LLM returned error string, exception during generation, or non-code content | OLLAMA_GENERATION |
| `DEPENDENCY_BLOCKED` | `dependency_blocked` | Feature blocked by unmet dependency in `FeatureQueue`; prerequisite feature failed or was not generated | INTEGRATION |
| `UNKNOWN` | `unknown` | Failure does not match any known error pattern; requires manual inspection | UNKNOWN |

The `RootCauseClassifier` class matches failures to root causes via two strategies:
1. **Error message pattern matching** — `_ERROR_PATTERNS` list of `(regex, RootCause, PipelineStage)` tuples
2. **Status-based fallback** — `status == "blocked"` maps to `DEPENDENCY_BLOCKED`

---

## 5. Repair Pipeline

### REQ-KZ-PY-400: Python Repair Steps

Python has the most comprehensive repair pipeline of all supported languages, with 18 repair steps implemented in `src/startd8/repair/steps/`. The `PythonLanguageProfile` enables repair via `repair_enabled = True`.

Repair steps are executed by `run_file_repair()` and `run_element_repair()` in `repair/orchestrator.py`. Each step implements the `RepairStep` protocol and operates on source code strings.

| Step | Class | What It Fixes |
|------|-------|---------------|
| Fence strip | `FenceStripStep` | Removes markdown code fences (` ```python ... ``` `) from LLM output |
| AST validate | `AstValidateStep` | Parses with `ast.parse()`, reports `SyntaxError` with line/column |
| Bracket balance | `BracketBalanceStep` | Fixes unmatched `(`, `[`, `{` brackets |
| Indent normalize | `IndentNormalizeStep` | Fixes mixed tabs/spaces and incorrect indentation levels |
| Future import reorder | `FutureImportReorderStep` | Moves `from __future__ import annotations` to file top |
| Duplicate removal | `DuplicateRemovalStep` | Removes duplicate import statements and duplicate function/class definitions |
| Class body dedup | `ClassBodyDeduplicationStep` | Removes duplicate method definitions within a class body |
| Definition order fix | `DefinitionOrderFixStep` | Reorders definitions so callees appear before callers |
| Dunder all fix | `DunderAllFixStep` | Fixes `__all__` to match actual module-level exports |
| Extended lint fix | `ExtendedLintFixStep` | Auto-fixes Ruff-detected lint errors via `ruff check --fix` |
| Import completion (error) | `ErrorDrivenImportCompletion` | Adds missing imports based on `NameError`-style messages |
| Import completion (manifest) | `ManifestImportCompletion` | Adds missing imports based on `ForwardManifest` contract |
| Variable initialization | `VariableInitializationStep` | Adds missing variable initializations (e.g., `x` referenced before assignment) |
| Unused variable removal | `UnusedVariableRemovalStep` | Removes variables assigned but never read |
| Semantic: duplicate main | `SemanticDuplicateMainFixStep` | Removes duplicate `if __name__ == "__main__"` guards |
| Semantic: discarded return | `SemanticDiscardedReturnFixStep` | Fixes discarded return values from factory/builder calls |
| Semantic: import fix | `SemanticImportFixStep` | Fixes phantom/broken imports detected by semantic analysis |
| Semantic: method resolution | `SemanticMethodResolutionFixStep` | Fixes `self.x()` calls where `x` is a module-level function, not a method |
| Semantic: method fix | `SemanticMethodFixStep` | Fixes general method-level semantic issues |
| Contract violation fix | `ContractViolationFixStep` | Auto-fixes contract violations detected by `ForwardManifest` validation |

**Integration points:**
- `IntegrationEngine._attempt_pre_merge_repair()` — runs repair before merging into project root
- `IntegrationEngine._attempt_repair()` — runs repair after merge when post-merge validation fails
- `repair/routing.py` — routes classified failures (`RepairRoute`) to the appropriate subset of repair steps
- `repair/staging.py` — provides atomic staging so failed repairs can be rolled back

---

## 6. Feedback Loop Hints (extends Phase C / Layer 5)

### REQ-KZ-PY-500: Python-Specific Kaizen Hints

When Kaizen analysis identifies recurring Python-specific issues, hints are injected into the next run's spec and draft prompts via `spec_builder.py` (P1 priority section: `"## Quality Hints (from prior run analysis)"`) and `drafter.py` (P1 supplementary section).

Python-specific hint categories:

| Category | Example Hint | Triggered By |
|----------|-------------|--------------|
| Import validation | "Validate all imports exist in requirements.txt before using them" | `phantom_import` root cause |
| Type safety | "Include type annotations on all public functions" | Type annotation completeness check (planned) |
| Testing patterns | "Use pytest fixtures, not unittest.TestCase" | `PythonLanguageProfile.test_command` uses pytest |
| Async patterns | "Use async/await consistently; don't mix sync and async" | Mixed sync/async pattern detection |
| Pydantic patterns | "Use Pydantic v2 model_validator, not v1 validator" | Framework import guidance |
| Indentation | "Match the indentation style of the surrounding file exactly" | `indentation_error` cause |
| Scope preservation | "Preserve the existing function and class structure. Do not reorganize scopes." | `scope_corruption` cause |
| Import deduplication | "Check for existing imports before adding new ones. Deduplicate at file top." | `duplicate_import` cause |

### REQ-KZ-PY-501: Python CAUSE_TO_SUGGESTION Mappings

The `CAUSE_TO_SUGGESTION` dictionary in `prime_postmortem.py` contains 25 entries. All are Python-oriented (they reference Python syntax, Python tools, and Python conventions). These serve as the Python-specific Kaizen suggestion mappings.

**Primary mappings (16 entries, one per RootCause):**

| Cause Key | Phase | Hint |
|-----------|-------|------|
| `duplicate_import` | draft | "Check for existing imports before adding new ones. Deduplicate at file top." |
| `unfilled_stub` | draft | "Replace every stub/placeholder with real implementation before returning." |
| `scope_corruption` | draft | "Preserve the existing function and class structure. Do not reorganize scopes." |
| `phantom_import` | draft | "Validate all imports exist in the target project before referencing them." |
| `indentation_error` | draft | "Match the indentation style of the surrounding file exactly." |
| `splicer_mismatch` | draft | "Ensure generated code anchors (function/class names) match the target file exactly." |
| `tier_escalation` | spec | "Decompose complex features into smaller, independently implementable units." |
| `ast_failure` | draft | "Emit syntactically valid Python at all times; run a mental parse check before returning." |
| `size_regression` | draft | "Do not generate significantly more lines than the original file; prefer surgical edits." |
| `generation_error` | draft | "If generation fails, emit a minimal valid stub rather than an error string." |
| `skeleton_missing` | spec | "Ensure skeleton files are generated before code generation begins." |
| `ollama_timeout` | spec | "Reduce element scope to fit within generation time budgets. Split large elements." |
| `ollama_empty_response` | draft | "Always return code content. If unsure, emit a minimal valid stub rather than nothing." |
| `ollama_circuit_breaker` | spec | "Reduce batch size or complexity to stay within circuit breaker thresholds." |
| `repair_exhausted` | draft | "Generate cleaner code that requires fewer repair steps. Match target file conventions exactly." |
| `dependency_blocked` | spec | "Declare dependencies explicitly in the spec so blocked features are skipped early." |
| `unknown` | draft | "Inspect the failure message and add a targeted fix rather than regenerating the whole file." |

**Escalation subtypes (9 entries, `repeated_escalation:*` prefix):**

| Cause Key | Phase | Hint |
|-----------|-------|------|
| `repeated_escalation:ast_failure` | draft | "Emit syntactically valid Python; run a mental parse check. If generating function bodies, always include the def line." |
| `repeated_escalation:tier_too_high` | spec | "Decompose into simpler sub-elements; complex features need finer granularity in the spec." |
| `repeated_escalation:not_decomposable` | spec | "Elements that resist decomposition may need manual splitting or should be routed to cloud-tier generation." |
| `repeated_escalation:structural_mismatch` | draft | "Match the exact class/function structure of the target file. Do not reorganize or rename anchors." |
| `repeated_escalation:empty_response` | draft | "Always return code content. If unsure, emit a minimal valid stub rather than nothing." |
| `repeated_escalation:timeout` | spec | "Reduce element scope to fit within generation time budgets. Split large elements." |
| `repeated_escalation:repair_exhausted` | draft | "Generate cleaner code that requires fewer repair steps. Match target file conventions exactly." |
| `repeated_escalation:circuit_breaker` | spec | "Reduce batch size or complexity to stay within circuit breaker thresholds." |
| `language_mismatch_in_generation` | spec | "Non-Python files received Python stubs. Check template-match routing for non-Python trivial tasks. Ensure _NON_PYTHON_EXTENSIONS includes all target file extensions." |

**Selection logic:** `generate_kaizen_suggestions()` filters cross-feature patterns by `frequency >= 2`, maps `pattern_type` to `CAUSE_TO_SUGGESTION`, and returns structured suggestion dicts with `pattern`, `suggested_action`, `config_key`, `phase`, `confidence` (high if frequency >= 3, else medium), and `auto_applicable` fields.

---

## 7. Generation Profile

### REQ-KZ-PY-600: Python Generation Characteristics

The `PythonLanguageProfile` defines the following generation characteristics:

| Property | Value | Notes |
|----------|-------|-------|
| `language_id` | `"python"` | Registry key |
| `source_extensions` | `[".py"]` | `.pyw` also supported via `supports_extension()` |
| `merge_strategy_preference` | `"ast"` | AST-based splicer (vs text-based for Go/Java/C#/Node.js) |
| `repair_enabled` | `True` | Full 18-step repair pipeline |
| `stub_patterns` | `[]` (empty) | Python uses AST-based stub detection, not text pattern matching |
| `function_start_pattern` | `None` | Python uses AST-based detection, not regex |
| `docker_base_image` | `"python:3.12-slim"` | For containerized execution |
| `system_prompt_role` | `"an expert Python engineer"` | LLM persona for code generation |
| `coding_standards` | Ruff: no single-letter vars l/O/I; define helpers before use; stdlib-only imports unless listed | Injected into LLM prompts |
| `import_pattern_template` | `"import {module}\|from {module}"` | For blast radius analysis |

**MicroPrime support:** Full support for element-level generation. The AST splicer (`micro_prime/splicer.py`) can insert, replace, or append Python elements (functions, classes, methods) into existing files using AST node matching.

**Template matching:** Python-specific templates for common patterns (e.g., dataclass, FastAPI endpoint, pytest fixture) registered in `micro_prime/templates.py`.

**Skeleton assembly:** Python files are initialized with `from __future__ import annotations` header when the profile is active.

**Post-generation cleanup:** Not separately needed for Python. Cleanup is handled inline by the repair pipeline (Ruff auto-fix, import sorting, fence stripping). The `post_generation_cleanup()` method returns an empty list.

**Dependency files:** `requirements.txt` or `pyproject.toml` generation is handled by the existing `requirements_generator.py` pipeline, not by the language profile directly. The profile provides `build_file_patterns` for discovery and `strip_dependency_version()` for version pin normalization.

**Import guidance:** `get_import_syntax_guidance()` returns: "Use `import module` or `from module import name`. Prefer absolute imports. No wildcard imports." This is injected into LLM prompts for Python code generation.

---

## 8. Traceability Matrix

### REQ-KZ-PY-* to REQ-KZ-* Mapping

| Python Req | Extends/Specializes | Description |
|-----------|---------------------|-------------|
| REQ-KZ-PY-100 | Phase B (REQ-KZ-300 metrics) | Python disk compliance — 10 validation layers, all AST-based |
| REQ-KZ-PY-101 | Phase B | Python validation tools — py_compile, Ruff, ast.parse, import resolution |
| REQ-KZ-PY-200 | Phase D (new capability) | Python semantic validators — 4 deterministic AST checks |
| REQ-KZ-PY-201 | Phase D (planned) | Python semantic extensions — circular imports, type annotations, unused imports, mutable defaults |
| REQ-KZ-PY-300 | Phase E (REQ-KZ-300 metrics) | Python quality score formula — 4-component weighted composite |
| REQ-KZ-PY-301 | REQ-KZ-401 (pattern detection) | Python root causes — 16 RootCause enum values with Python-specific manifestations |
| REQ-KZ-PY-400 | Phase B + D + Repair | Python repair steps — 18 steps from fence stripping to semantic method resolution |
| REQ-KZ-PY-500 | REQ-KZ-500/501 (Layer 5) | Python-specific Kaizen hints — import, type, testing, async, Pydantic patterns |
| REQ-KZ-PY-501 | REQ-KZ-501 (suggestions) | Python CAUSE_TO_SUGGESTION — 25 entries (16 primary + 9 escalation subtypes) |
| REQ-KZ-PY-600 | N/A (profile spec) | Python generation characteristics — AST merge, full repair, MicroPrime support |

### Shared Requirements (Not Python-Specific)

The following REQ-KZ requirements are language-agnostic and apply to Python without modification:

| REQ-KZ | Layer | Description |
|--------|-------|-------------|
| REQ-KZ-100–102 | Layer 1 | Post-mortem invocation, output archiving, summary display |
| REQ-KZ-200–204 | Layer 2 | Prompt-response pairing and persistence |
| REQ-KZ-300–304 | Layer 3 | Run metrics extraction and archive index |
| REQ-KZ-400–403 | Layer 4 | Cross-run aggregation, trend detection, escalation |
| REQ-KZ-500, 502–504 | Layer 5 | Kaizen config format, injection, bypass, verification |
| REQ-KZ-600–601 | Layer 6 | Prompt quality correlation and scoring |

---

## 9. Verification Strategy

### Existing Test Coverage

Python-specific Kaizen behavior is verified by the following test suites:

| Test File | Test Count | What It Covers |
|-----------|------------|----------------|
| `tests/unit/test_forward_manifest_validator_disk.py` | 30 tests | `DiskComplianceResult`, `validate_disk_compliance()`, stub counting, import completeness, duplicate definitions, AST validity, non-Python file guard, contract compliance scoring |
| `tests/unit/validators/test_semantic_checks.py` | 18 tests | All 4 semantic checks: duplicate main guards, duplicate definitions, bare except:pass, phantom dependencies; `run_semantic_checks()` orchestrator; edge cases (reversed comparison, multiple handlers, guarded imports) |
| `tests/unit/test_kaizen_quality.py` | 21 tests | `TestRegistryMetadataEnrichment` (2), `TestKaizenFeedbackLoop` (5), `TestCauseToSuggestion` (5), `TestDualQualityScoring` (9) — covers quality score formula, stub/semantic penalties, assembly delta, short-circuit rules |
| `tests/unit/contractors/test_prime_postmortem.py` | 53 tests | `RootCauseClassifier`, `PrimePostMortemEvaluator`, cross-feature pattern detection, `generate_kaizen_suggestions()`, cost outlier detection, escalation analysis |

**Additional related test files:**

| Test File | What It Covers |
|-----------|----------------|
| `tests/unit/test_semantic_validation_imports.py` | L1 import resolution layer in disk compliance |
| `tests/unit/test_semantic_validation_lint_and_otel.py` | Lint integration and OTel emission from semantic validation |
| `tests/unit/test_semantic_validation_factory_and_reqs.py` | L4 factory return validation and requirements checking |
| `tests/unit/test_semantic_validation_scope_and_dockerfile.py` | L2 cross-scope duplicate detection |
| `tests/unit/contractors/test_semantic_repair_scoring.py` | Semantic repair impact on quality scoring |

### Verification Checklist

For any change to Python-specific Kaizen behavior, verify:

1. **Quality score computation** — `pytest tests/unit/test_kaizen_quality.py -v` (21 tests)
2. **Disk validation layers** — `pytest tests/unit/test_forward_manifest_validator_disk.py -v` (30 tests)
3. **Semantic checks** — `pytest tests/unit/validators/test_semantic_checks.py -v` (18 tests)
4. **Post-mortem classification** — `pytest tests/unit/contractors/test_prime_postmortem.py -v` (53 tests)
5. **Repair step behavior** — repair steps are tested individually in `tests/unit/repair/`
6. **Full regression** — `pytest tests/unit/ -v --tb=short` (all unit tests)
