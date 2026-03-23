# Multi-Language Parity Requirements — Prime Contractor First-Class Citizenship

**Date:** 2026-03-19
**Status:** Active
**Scope:** Ensure all 5 supported languages (Python, Go, Java, Node.js, C#) are first-class citizens of the Prime Contractor workflow
**Priority:** PAUSED all other work — this is the sole focus

---

## 1. Python Baseline (Reference Implementation)

Python has the deepest pipeline integration. This section documents every capability that other languages must match or explicitly justify skipping.

> **BASELINE VERIFICATION WARNING (2026-03-23):** The cross-language wiring gap audit found that Python — the reference implementation — is **40% wired** at the pipeline level. The 4 semantic checks in `semantic_checks.py` are orphaned (never called). The integration engine has no Python dispatch branch. 0/4 semantic categories have Kaizen suggestion mappings. **Before grading other languages against this baseline, verify that every Python capability listed below is actively exercised in the production pipeline.** A capability that exists as dead code is NOT a baseline — it is a gap. See [CROSS_LANGUAGE_WIRING_GAP_AUDIT.md](CROSS_LANGUAGE_WIRING_GAP_AUDIT.md) for details.

### 1.1 Syntax Validation & Repair

| Step | Implementation | Python-Specific? |
|------|---------------|-----------------|
| `ast.parse()` validation | `python.py:validate_syntax()` | Yes — other langs use their own parsers |
| `fence_strip` | `repair/steps/fence_strip.py` | **No — language-agnostic** |
| `future_import_reorder` | `repair/steps/future_import_reorder.py` | Yes — `from __future__` is Python-only |
| `indent_normalize` | `repair/steps/indent_normalize.py` | Yes — significant whitespace is Python-only |
| `bracket_balance` | `repair/steps/bracket_balance.py` | **Partially shared** — brace languages need this too |
| `class_body_dedup` | `repair/steps/class_body_dedup.py` | Yes — Python class body quirks |
| `definition_order_fix` | `repair/steps/definition_order_fix.py` | Yes — Python forward refs (other langs have compilers) |
| `import_completion` | `repair/steps/import_completion.py` | **Conceptually shared** — every language has imports |
| `variable_initialization` | `repair/steps/variable_initialization.py` | Yes — Python-specific undefined name fixes |
| `duplicate_removal` | `repair/steps/duplicate_removal.py` | **Conceptually shared** — duplicate imports exist in all languages |
| `extended_lint_fix` | `repair/steps/extended_lint_fix.py` (Ruff) | Yes — Ruff is Python-only; other langs need their own linters |
| `dunder_all_fix` | `repair/steps/dunder_all_fix.py` | Yes — `__all__` is Python-only |
| `unused_variable_removal` | `repair/steps/unused_variable_removal.py` | **Conceptually shared** — but requires language-specific AST |
| `ast_validate` (final gate) | `repair/steps/ast_validate.py` | Yes — `ast.parse()` final gate; other langs need own validator |

**4 Semantic Repair Steps:**

| Step | Implementation | Python-Specific? |
|------|---------------|-----------------|
| `semantic_method_fix` | `repair/steps/semantic_method_fix.py` | Yes — `self` parameter is Python-only |
| `semantic_import_fix` | `repair/steps/semantic_import_fix.py` | **Conceptually shared** — flat vs package layout |
| `semantic_method_resolution_fix` | `repair/steps/semantic_method_resolution_fix.py` | Yes — `self.x()` resolution is Python-specific |
| `semantic_discarded_return_fix` | `repair/steps/semantic_discarded_return_fix.py` | **Conceptually shared** — but detection requires AST |
| `semantic_duplicate_main_fix` | `repair/steps/semantic_duplicate_main_fix.py` | Yes — `if __name__ == "__main__"` is Python-only |

### 1.2 Semantic Validation (4 Core Checks)

| Check | Function | What It Detects |
|-------|----------|----------------|
| `check_duplicate_main_guards` | `semantic_checks.py:32` | Multiple `if __name__ == "__main__"` |
| `check_duplicate_definitions` | `semantic_checks.py:52` | Same-name functions/classes at module level |
| `check_bare_except_pass` | `semantic_checks.py:77` | `except: pass` (swallows all exceptions) |
| `check_phantom_dependencies` | `semantic_checks.py:103` | Imports not in known dependency set |

### 1.3 Disk Compliance (10 Validation Layers)

| Layer | Code | What It Validates |
|-------|------|-------------------|
| L1 | `_validate_import_resolution()` | Imports resolve to existing modules |
| L2 | `_detect_cross_scope_duplicates()` | No duplicate definitions across scopes |
| L4 | `_validate_factory_returns()` | Factory functions (`create_*`, `make_*`) return non-None |
| L6 | `_validate_discarded_returns()` | Function return values are captured |
| L8 | `_validate_service_identity()` | No self-importing modules |
| L9 | `_validate_method_resolution()` | `self.x()` calls match actual methods |
| L10 | `_validate_reachability()` | Dead code detection |
| Stubs | `_count_stubs()` | `raise NotImplementedError` count |
| Duplicates | `_count_duplicate_definitions()` | Duplicate module-level defs |
| Contract | `_validate_disk_file_against_spec()` | Forward manifest compliance |

---

## 2. Language Parity Matrix — Current State

### 2.1 Syntax Validation

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| In-process parser | `ast.parse()` | N/A | `javalang` | N/A | `tree-sitter` |
| Subprocess validator | `py_compile` | `gofmt -e` | N/A | `node --check` | N/A |
| Text-based fallback | N/A | N/A | Balanced braces + type decl | Keyword check | Balanced braces + patterns |
| Graceful degradation | N/A (always available) | Returns True if gofmt missing | Falls back to text | Falls back to text | Falls back to text |
| **Parity grade** | **Baseline** | **B** (no in-process) | **A-** (javalang optional) | **B-** (subprocess only) | **A** (tree-sitter + fallback) |

### 2.2 Repair Pipeline

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| `repair_enabled` | **True** | False | False | True | False |
| Fence strip | Yes | **NO** | **NO** | **NO** | **NO** |
| Bracket/brace balance | Yes | **NO** | **NO** | **NO** | **NO** |
| Import completion | Yes | **NO** (goimports instead) | **NO** | **NO** | **NO** |
| Duplicate import removal | Yes | **NO** (goimports instead) | **NO** | **NO** | **NO** |
| Lint auto-fix | Yes (Ruff) | **NO** (gofmt only formats) | **NO** | **NO** | **NO** |
| Final syntax gate | Yes (ast.parse) | **NO** | **NO** | **NO** | **NO** |
| **Parity grade** | **Baseline (17 steps)** | **F** (0 steps) | **F** (0 steps) | **F** (0 steps) | **F** (0 steps) |

### 2.3 Semantic Validation

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| Duplicate entry points | `check_duplicate_main_guards` | **NO** | **NO** | **NO** | **NO** |
| Duplicate definitions | `check_duplicate_definitions` | **NO** | **NO** | **NO** | **NO** |
| Exception swallowing | `check_bare_except_pass` | **NO** | **NO** | **NO** | **NO** |
| Phantom dependencies | `check_phantom_dependencies` | **NO** | **NO** | **NO** | **NO** |
| **Parity grade** | **Baseline (4 checks)** | **F** (0 checks) | **F** (0 checks) | **F** (0 checks) | **F** (0 checks) |

### 2.4 Disk Compliance

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| Syntax validation | L0 (ast.parse) | L0 (gofmt) | L0 (javalang/text) | L0 (node --check/text) | L0 (tree-sitter/text) |
| Import resolution (L1) | Yes | **NO** | **NO** | **NO** | **NO** |
| Cross-scope duplicates (L2) | Yes | **NO** | **NO** | **NO** | **NO** |
| Factory returns (L4) | Yes | N/A | N/A | N/A | N/A |
| Discarded returns (L6) | Yes | N/A | N/A | N/A | N/A |
| Service identity (L8) | Yes | **NO** | **NO** | **NO** | **NO** |
| Method resolution (L9) | Yes | N/A | **NO** | N/A | **NO** |
| Reachability (L10) | Yes | **NO** | **NO** | **NO** | **NO** |
| Stub counting | Yes | Yes (text) | Yes (text) | Yes (text) | Yes (text) |
| Contract compliance | Yes | Partial | Partial | Partial | Partial |
| **Parity grade** | **Baseline (10 layers)** | **D** (2 layers) | **D** (2 layers) | **D** (2 layers) | **D** (2 layers) |

### 2.5 Post-Generation & Templates

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| Post-gen cleanup | Ruff (inline) | goimports | None | Prettier (best-effort) | dotnet format |
| Templates (TRIVIAL) | 12+ | 0 | 8 | 0 | 0 |
| DFA skeletons | Yes | No | Yes | No | No |
| Decomposition strategy | Class + Function | No | Class | No | No |
| **Parity grade** | **Baseline** | **C** | **B+** | **D** | **D** |

### 2.6 Pipeline Connectivity Matrix (Added 2026-03-23)

> The component-based grades in Sections 2.1-2.5 measure whether components **exist**, not whether they're **connected**. This matrix traces each semantic check from detection through to action, revealing the actual pipeline wiring state.

**Classification key:**
- **COMPLETE** — Check fires → collected → scored → suggestion mapping → repair route
- **ADVISORY** — Check fires → collected → scored → suggestion mapping → intentionally no repair (documented reason)
- **BROKEN** — Check fires but pipeline is disconnected at some stage (detection generates data that is silently discarded)

| Language | Total Checks | Complete | Advisory | Broken | Pipeline Connectivity |
|----------|:------:|:--------:|:--------:|:------:|:-------------------:|
| **Python** | 4 | 0 | 0 | 4 | **0%** |
| **Go** | 6 | 5 | 0 | 1 | **83%** |
| **Node.js** | 9 | 3 | 3 | 3 | **67%** |
| **Java** | 12 | 4 | 2 | 6 | **50%** |
| **C#** | 9 | 4 | 2 | 3 | **67%** |

**Broken checks by language:**

| Language | Check | Break Point | Gap ID |
|----------|-------|-------------|--------|
| Python | `duplicate_main_guard` | Never called (orphaned code) | C-3 |
| Python | `duplicate_definition` | Never called (orphaned code) | C-3 |
| Python | `bare_except_pass` | Never called (orphaned code) | C-3 |
| Python | `phantom_dependency` | Never called (orphaned code) | C-3 |
| Go | MicroPrime profile | `code_generator._language_profile` is `None` | H-4 |
| Node.js | TS/JSX dispatch | `.ts/.tsx/.jsx` skipped in validator dispatch | C-2 |
| Node.js | package.json semantics | Semantic checks not collected | C-4 |
| Node.js | `unhandled_promise` | No repair route (deferred, not advisory) | H-3 |
| Java | `raw_type_usage` | No repair route (deferred) | H-3 |
| Java | `missing_override` | No repair route (deferred) | H-3 |
| Java | `duplicate_method` | No repair route (deferred) | H-3 |
| Java | `interface_file_contains_class` | No repair route (advisory — undocumented) | H-3 |
| Java | `package_filepath_mismatch` | No repair route (deferred) | H-3 |
| Java | `invalid_java_version` | No repair route (advisory — undocumented) | H-3 |
| C# | `console_writeline_in_service` | No repair route (advisory — undocumented) | H-3 |
| C# | `missing_async_await` | No repair route (advisory — undocumented) | H-3 |
| C# | `missing_access_modifier` | No repair route (deferred) | H-3 |

> **REQ-MLP-PIPELINE:** The Pipeline Connectivity metric SHALL be tracked alongside component grades. A language is not first-class until its connectivity rate is ≥ 80% (all checks are either COMPLETE or ADVISORY with documented rationale). BROKEN checks indicate accidental complexity — wiring that was started but not finished.

### 2.7 Semantic Check Implementation Checklist Template (Added 2026-03-23)

> Per REQ-KZ-007 (advisory/repairable classification), every new semantic check SHALL use this 5-column template to ensure full pipeline wiring at implementation time:

| Check | Function | Collection Point | Suggestion Mapping | Classification |
|-------|----------|:---:|:---:|:---:|
| *check name* | `validators/{lang}_semantic_checks.py` | `_validate_{lang}_file()` → `result.semantic_issues` | `category` → `_SEMANTIC_CATEGORY_TO_SUGGESTION[category]` → `CAUSE_TO_SUGGESTION[key]` | REPAIRABLE / ADVISORY (reason) / DEFERRED (effort) |

**Example (complete):**

| Check | Function | Collection | Suggestion | Classification |
|-------|----------|:---:|:---:|:---:|
| `check_var_usage` | `nodejs_semantic_checks.py` | `_validate_js_file()` | `var_usage` → `var_usage_detected` → hint text | REPAIRABLE → `var_to_const` step |

**Example (advisory):**

| Check | Function | Collection | Suggestion | Classification |
|-------|----------|:---:|:---:|:---:|
| `check_module_system_mixing` | `nodejs_semantic_checks.py` | `_validate_js_file()` | `module_system_mixing` → `module_system_mixing_detected` | ADVISORY — CJS↔ESM is an architectural decision requiring package.json `type` field coordination |

---

## 3. Implementation Plan — Language by Language

### Execution Order

Java first (most infrastructure exists), then Go (strong compiler, focused gaps), then C# (tree-sitter advantage), then Node.js (most gaps).

### 3.1 JAVA — Phase J1: Repair & Semantic Validation

**Current state:** Validation A-, Repair F, Semantic F
**Target state:** Validation A, Repair B, Semantic B

#### J1.1 Enable `repair_enabled = True`

Set `JavaLanguageProfile.repair_enabled = True`. Wire the following **language-agnostic** repair steps that already work for Java:

| Step | Applicable? | Notes |
|------|------------|-------|
| `fence_strip` | **YES** | Strips markdown fences — works on any language |
| `bracket_balance` | **YES** | Java uses braces — brace balancing is directly applicable |
| `ast_validate` (final gate) | **YES** — but needs Java gate | Replace `ast.parse()` with `javalang.parse.parse()` or text fallback |

#### J1.2 Java-Specific Repair Steps (New)

| Step | Analog of | What It Does |
|------|-----------|-------------|
| `java_import_dedup` | `duplicate_removal` | Remove duplicate `import` statements |
| `java_wildcard_import_fix` | N/A (Java-specific) | Replace `import pkg.*;` with explicit imports from manifest |
| `java_syntax_validate` | `ast_validate` | Final gate via `javalang.parse.parse()` with text fallback |

#### J1.3 Java Semantic Checks (New)

Implement in `validators/java_semantic_checks.py`:

| Check | Python Analog | What It Detects |
|-------|--------------|----------------|
| `check_empty_catch_blocks` | `check_bare_except_pass` | `catch (Exception e) { }` — swallowed exceptions |
| `check_duplicate_type_declarations` | `check_duplicate_definitions` | Same class/interface name in same file |
| `check_phantom_imports` | `check_phantom_dependencies` | Imports not in `build.gradle` dependencies |
| `check_missing_override` | N/A | `toString()`, `equals()`, `hashCode()` without `@Override` |
| `check_raw_type_usage` | N/A | `List` instead of `List<String>` |

#### J1.4 Java Disk Compliance Enhancements

| Layer | Python Analog | What It Validates |
|-------|--------------|-------------------|
| Package-directory match | L1 (import resolution) | `package com.example;` matches `com/example/` path |
| Class-filename match | N/A | Public class name matches `.java` filename |
| Import well-formedness | L1 | No Python-syntax imports, semicolons present |
| Cross-language contamination | L0 extension | Python/Go/JS syntax in `.java` files |

#### J1.5 Tests: ~40

**Deliverables:** `repair_enabled=True`, 3 repair steps, 5 semantic checks, 4 disk enhancements
**Estimated effort:** M

---

### 3.2 GO — Phase G1: Semantic Validation & Repair Wiring

**Current state:** Validation B, Repair F, Semantic F
**Target state:** Validation A-, Repair C, Semantic B

#### G1.1 Go Repair Steps

| Step | Applicable? | Notes |
|------|------------|-------|
| `fence_strip` | **YES** | Language-agnostic |
| `bracket_balance` | **YES** | Go uses braces |
| `goimports_fix` | **NEW** | Run `goimports -w` as repair step (already in post_generation_cleanup) |
| `go_syntax_validate` | **NEW** | Final gate via `gofmt -e` |

#### G1.2 Go Semantic Checks

Implement in `validators/go_semantic_checks.py`:

| Check | Python Analog | What It Detects |
|-------|--------------|----------------|
| `check_unchecked_errors` | `check_bare_except_pass` | `err` returned but not checked (`if err != nil`) |
| `check_duplicate_function_names` | `check_duplicate_definitions` | Same function name in same package |
| `check_phantom_imports` | `check_phantom_dependencies` | Imports not in `go.mod` |
| `check_unused_imports` | N/A | Go compiler error — but we can detect pre-goimports |

#### G1.3 Tests: ~25

**Deliverables:** `repair_enabled=True`, 4 repair steps, 4 semantic checks
**Estimated effort:** S-M

---

### 3.3 C# — Phase CS1: Semantic Validation & Repair Wiring

**Current state:** Validation A, Repair F, Semantic F
**Target state:** Validation A, Repair B, Semantic B

#### CS1.1 C# Repair Steps

| Step | Applicable? | Notes |
|------|------------|-------|
| `fence_strip` | **YES** | Language-agnostic |
| `bracket_balance` | **YES** | C# uses braces |
| `csharp_syntax_validate` | **NEW** | Final gate via tree-sitter `has_error` |
| `csharp_using_dedup` | **NEW** | Remove duplicate `using` statements |

#### CS1.2 C# Semantic Checks

Implement in `validators/csharp_semantic_checks.py`:

| Check | Python Analog | What It Detects |
|-------|--------------|----------------|
| `check_empty_catch_blocks` | `check_bare_except_pass` | `catch (Exception) { }` |
| `check_duplicate_type_declarations` | `check_duplicate_definitions` | Same class name in file |
| `check_phantom_usings` | `check_phantom_dependencies` | `using` not backed by `.csproj` PackageReference |
| `check_missing_async_await` | N/A | `async` method without `await` (compiler warning CS1998) |
| `check_missing_dispose` | N/A | `IDisposable` without `using` block or `Dispose()` call |

#### CS1.3 Tests: ~30

**Deliverables:** `repair_enabled=True`, 4 repair steps, 5 semantic checks
**Estimated effort:** M

---

### 3.4 NODE.JS — Phase N1: Semantic Validation & Repair

**Current state:** Validation B-, Repair F (enabled but empty), Semantic F
**Target state:** Validation B+, Repair C, Semantic B

#### N1.1 Node.js Repair Steps

| Step | Applicable? | Notes |
|------|------------|-------|
| `fence_strip` | **YES** | Language-agnostic |
| `bracket_balance` | **YES** | JS uses braces |
| `js_syntax_validate` | **NEW** | Final gate via `node --check` |
| `js_require_dedup` | **NEW** | Remove duplicate `require()` / `import` statements |

#### N1.2 Node.js Semantic Checks

Implement in `validators/nodejs_semantic_checks.py`:

| Check | Python Analog | What It Detects |
|-------|--------------|----------------|
| `check_unhandled_promises` | `check_bare_except_pass` | `async` function called without `await` or `.catch()` |
| `check_duplicate_exports` | `check_duplicate_definitions` | Same name exported twice |
| `check_phantom_requires` | `check_phantom_dependencies` | `require('pkg')` not in `package.json` dependencies |
| `check_var_usage` | N/A | `var` declarations (should use `const`/`let`) |

#### N1.3 Tests: ~25

**Deliverables:** 4 repair steps, 4 semantic checks
**Estimated effort:** S-M

---

## 4. Shared Infrastructure to Build

Before language-specific work, these shared components benefit all languages:

### 4.1 Language-Agnostic Repair Step Base

Refactor `repair/steps/fence_strip.py` and `repair/steps/bracket_balance.py` to work with any language (they already do, but the routing in `repair/routing.py` is Python-specific).

**Change:** Add a `language_id` parameter to `route_failures()` so it selects language-appropriate repair steps.

### 4.2 Semantic Check Protocol

Create `validators/semantic_check_protocol.py`:

```python
class SemanticCheck(Protocol):
    def check(self, source: str, file_path: str, **context) -> list[SemanticIssue]: ...

class SemanticIssue:
    category: str      # e.g. "empty_catch_block"
    severity: str      # "error" | "warning"
    message: str
    line: int | None
    language: str      # "java", "go", etc.
```

### 4.3 Language-Aware Repair Router

Extend `repair/routing.py` with per-language step sequences:

```python
LANGUAGE_REPAIR_ROUTES = {
    "python": PYTHON_ROUTES,  # existing 17-step pipeline
    "java": {
        "syntax": [fence_strip, bracket_balance, java_syntax_validate],
        "import": [java_import_dedup, java_wildcard_import_fix, java_syntax_validate],
    },
    "go": {
        "syntax": [fence_strip, bracket_balance, go_syntax_validate],
        "import": [goimports_fix, go_syntax_validate],
    },
    ...
}
```

---

## 5. Execution Order

| Phase | Language | Focus | Effort | Tests |
|-------|----------|-------|--------|-------|
| **J1** | Java | Repair + Semantic + Disk | M | ~40 |
| **G1** | Go | Repair + Semantic | S-M | ~25 |
| **CS1** | C# | Repair + Semantic | M | ~30 |
| **N1** | Node.js | Repair + Semantic | S-M | ~25 |
| **Shared** | All | Repair router + semantic protocol | S | ~15 |

**Total estimated: ~135 tests across 5 phases**

Start with **Java (J1)** — it has the most existing infrastructure (parser, splicer, templates, DFA) and the Kaizen Java requirements doc already specifies the semantic checks.

---

## 6. Success Criteria

A language is a **first-class citizen** when:

1. `repair_enabled = True` with at least 3 repair steps (fence_strip + bracket_balance + syntax_validate)
2. At least 3 language-specific semantic checks wired into disk compliance
3. Cross-language contamination detection (Python fingerprints in non-Python files AND non-Python fingerprints in other files)
4. Postmortem scores use language-specific validators (not defaulting to 1.0)
5. Framework detection covers the language's major frameworks
6. `build_project_context_section()` provides language-specific LLM guidance
7. Dependency file generation works (`generate_dependency_file()`)
8. Language-specific stub patterns are defined and detected
9. **(Added 2026-03-23)** Pipeline connectivity ≥ 80% — all semantic checks are either COMPLETE or ADVISORY with documented rationale (REQ-MLP-PIPELINE)
10. **(Added 2026-03-23)** `coding_standards` injected into spec prompts via REQ-KZ-005

### Current Citizenship Status

> **Updated 2026-03-23** to reflect wiring gap audit findings. Python was previously listed as 8/8 first-class, but the audit revealed its semantic checks are orphaned code (never run) and its pipeline connectivity is 0%. Status downgraded to second-class pending wiring fixes.

| Language | Criteria Met | Pipeline Connectivity | Status |
|----------|-------------|:---:|--------|
| **Python** | 6/10 (missing: pipeline connectivity, coding_standards injection, semantic checks run, integration dispatch) | 0% | **Second-class** (wiring gaps) |
| **Go** | 8/10 (missing: coding_standards injection, MicroPrime profile timing) | 83% | **Near first-class** |
| **Java** | 7/10 (missing: pipeline connectivity, coding_standards injection, 6 deferred repair routes) | 50% | **Second-class** |
| **C#** | 7/10 (missing: pipeline connectivity, coding_standards injection, block_scoped check) | 67% | **Second-class** |
| **Node.js** | 7/10 (missing: pipeline connectivity, coding_standards injection, TS/JSX dispatch) | 67% | **Second-class** |
