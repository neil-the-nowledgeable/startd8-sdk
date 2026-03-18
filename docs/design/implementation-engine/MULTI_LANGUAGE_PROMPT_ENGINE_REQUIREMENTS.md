# Multi-Language Prompt Engine Refactor — Requirements

**Date:** 2026-03-18
**Status:** Draft
**Author:** Human + Agent collaboration
**Derived From:** 18-finding audit of `implementation_engine/` against Go (runs 066-070), Java (runs 071-072), and Node.js language profiles. Run-072 Java `build.gradle` failure (LLM wrapped Gradle content in Python script) is the triggering incident.
**Scope:** `src/startd8/implementation_engine/` (spec_builder, drafter, budget, prompts), `src/startd8/utils/code_extraction.py`, `src/startd8/languages/protocol.py`

---

## 1. Problem Statement

The implementation engine was designed for Python-only code generation. It has since been extended with `{language_role}` and `{coding_standards}` placeholders, but the surrounding prompt context, output format instructions, code examples, and extraction logic remain Python-specific. This causes:

1. **Wrong-language output** — LLM wraps non-Python content in Python scripts (run-072 `build.gradle`)
2. **Missing context** — Sibling imports, import conventions, and anti-pattern examples are Python-only; non-Python tasks get zero guidance in these sections
3. **Wiring bugs** — Language-specific import syntax is resolved from profiles but silently dropped when the YAML template renders
4. **False safety** — Truncation detection and size regression are disabled for Go/Java/JS source files, not just config files
5. **Python defaults** — Drafter falls back to "expert Python engineer" + Ruff standards when context is missing

### Severity Distribution

| Severity | Count | Examples |
|----------|-------|---------|
| Critical | 4 | Python code fences on non-Python reference code, YAML template drops language import syntax, no raw-output instruction |
| High | 5 | Drafter defaults to Python, skeleton fill says `raise NotImplementedError`, Go/Java skip truncation detection |
| Medium | 4 | Anti-patterns show Python examples, `__init__.py` in multi-file template |
| Low | 5 | Sort priority, token estimate, safe no-ops |

---

## 2. Design Principles

### 2.1 Language-Neutral by Default, Language-Specific by Injection

Prompt templates MUST NOT contain language-specific content (no `Python stdlib`, no `raise NotImplementedError`, no `__init__.py`). Language-specific content enters ONLY through placeholders populated from `LanguageProfile` properties.

### 2.2 Non-Python is Not Second-Class

Every quality gate that applies to Python (truncation detection, size regression, min-lines enforcement) MUST also apply to Go, Java, and Node.js source files. Only config/data files (YAML, JSON, Markdown, Dockerfile, properties) may skip these checks.

### 2.3 Explicit Output Format

The LLM MUST always be told what format to produce. "Implement the spec" is ambiguous for config files. The prompt must say "output the raw file content" for all file types.

### 2.4 Fail Loud on Missing Language Context

When a non-Python file reaches the prompt engine without a language profile, the engine MUST log a warning (not silently fall back to Python defaults).

---

## 3. Requirements

### Layer 1: Output Format & Raw Content Instruction (Critical)

#### REQ-PE-100: Raw Output Instruction in Drafter System Prompt

All drafter system prompt templates (`draft_system_create`, `draft_system_edit`, `draft_system_search_replace`, `draft_system_skeleton_fill`) MUST include an explicit output format instruction.

**Required text (or equivalent):**
```
Output the raw file content exactly as it should appear on disk.
Do NOT wrap file content in a Python script, generator function, or any meta-program.
Each code block must contain the literal file content for its target path.
```

**Acceptance criteria:**
- All 4 `draft_system_*` templates in `contractor_prompts.yaml` include the instruction
- All 4 fallback strings in `prompts/__init__.py` include the instruction
- The instruction appears BEFORE the `{coding_standards}` placeholder (higher priority)

#### REQ-PE-101: Raw Output Instruction in Draft User Prompt

The draft user prompt template (`draft` in `contractor_prompts.yaml`) MUST reinforce the raw output instruction in the output format section.

**Acceptance criteria:**
- The `draft` template's output format section includes: "Produce the COMPLETE file content. Do not wrap it in another language."
- For multi-file tasks, the multi-file output format section includes: "Each code block contains the raw content for one target file."

---

### Layer 2: Code Fence Language Parameterization (Critical)

#### REQ-PE-200: Reference Implementation Fence Uses Target Language

The reference implementation section in `spec_builder.py` MUST use the target language for code fences instead of hardcoded ` ```python `.

**Current (broken):**
```python
"```python\n" + reference_implementation + "\n```"
```

**Required:**
```python
f"```{lang_id}\n" + reference_implementation + "\n```"
```

Where `lang_id` is resolved from `context.get("language_profile").language_id`, falling back to empty string (unlabeled fence) when no profile is available.

**Acceptance criteria:**
- `spec_builder.py` line ~974-980 uses `language_profile.language_id` for fence language
- Go reference implementations are fenced as ` ```go `
- Java reference implementations are fenced as ` ```java `
- Missing profile produces unlabeled ` ``` ` (not ` ```python `)

#### REQ-PE-201: Sibling Imports Fence Uses Target Language

The sibling imports section in `spec_builder.py` (`_build_sibling_imports_section`) MUST use the target language for code fences.

**Acceptance criteria:**
- Code fence uses `language_profile.language_id` instead of hardcoded `python`
- Sibling import extraction supports non-Python files (see REQ-PE-400)

#### REQ-PE-202: Anti-Pattern Examples Use Target Language

The anti-pattern section (`_build_anti_pattern_section`) MUST produce language-appropriate code examples when the target language is not Python.

**Acceptance criteria:**
- When `language_profile.language_id` is not `python`, the function either:
  - Delegates to a language profile method for anti-pattern examples, OR
  - Skips the section entirely (safe: the section is optional)
- Python `os.getenv()` examples are never shown to a Go/Java drafter

---

### Layer 3: YAML Template Language Parameterization (Critical)

#### REQ-PE-300: Available Imports Template Accepts `{import_syntax}`

The `available_imports` YAML template MUST accept an `{import_syntax}` placeholder that replaces the hardcoded "Python stdlib" guidance.

**Current template (broken for non-Python):**
```yaml
template: |
  ## Available Packages
  {available_packages}
  Use ONLY these packages plus Python stdlib. Every non-stdlib symbol you
  reference MUST have a corresponding import statement at the top of the file.
```

**Required:**
```yaml
template: |
  ## Available Packages
  {available_packages}
  {import_syntax}
placeholders:
  - available_packages
  - import_syntax
```

**Acceptance criteria:**
- `contractor_prompts.yaml` `available_imports` template has `{import_syntax}` placeholder
- `spec_builder.py` passes `import_syntax` from `language_profile.get_import_syntax_guidance()` when formatting the template
- Fallback `import_syntax` for missing profile: "Use ONLY the packages listed above plus standard library modules."
- The fallback in `prompts/__init__.py` also uses `{import_syntax}`

#### REQ-PE-301: Skeleton Fill Template Accepts `{stub_marker}`

The `draft_system_skeleton_fill` template MUST replace the hardcoded `raise NotImplementedError` with a language-parameterized placeholder.

**Required:**
```yaml
template: |
  You are {language_role} filling method bodies in pre-assembled skeleton files.
  Implement ONLY methods marked with {stub_marker}. Do not modify pre-filled elements.
  ...
placeholders:
  - language_role
  - coding_standards
  - stub_marker
```

**Acceptance criteria:**
- `contractor_prompts.yaml` and `prompts/__init__.py` fallback both use `{stub_marker}`
- `drafter.py` resolves `stub_marker` from language profile:
  - Python: `` `raise NotImplementedError` ``
  - Go: `` `panic("not implemented")` ``
  - Java: `` `throw new UnsupportedOperationException()` ``
  - Node.js: `` `throw new Error("not implemented")` ``
- Fallback when no profile: `"stub markers (e.g., raise NotImplementedError, panic, throw)"`

#### REQ-PE-302: Multi-File Template Conditional `__init__.py` Rule

The `multi_file_output` YAML template MUST NOT reference `__init__.py` when the target language is not Python.

**Acceptance criteria:**
- The `__init__.py gets its own block` rule is either:
  - Wrapped in a conditional placeholder (e.g., `{init_file_rule}` populated only for Python), OR
  - Removed entirely and replaced with generic: "Every file gets its own code block. Do not skip any file."

---

### Layer 4: Sibling Import Extraction Generalization (High)

#### REQ-PE-400: Language-Aware Sibling Import Extraction

`_build_sibling_imports_section()` in `spec_builder.py` MUST support non-Python source files.

**Required behavior by language:**

| Language | File Filter | Import Extraction | Fence Label |
|----------|------------|-------------------|-------------|
| Python | `.py` | `ast.parse()` + `ast.Import`/`ast.ImportFrom` | `python` |
| Go | `.go` | Regex: `import "pkg"` and `import (...)` blocks | `go` |
| Java | `.java` | Regex: `import pkg.Class;` and `import static` | `java` |
| Node.js | `.js`, `.ts`, `.mjs` | Regex: `import ... from`, `require(...)` | `javascript` or `typescript` |

**Acceptance criteria:**
- Function checks `language_profile.source_extensions` for file filtering (not hardcoded `.py`)
- Python path remains unchanged (AST-based)
- Non-Python path uses regex-based import line extraction
- The LanguageProfile protocol gains an optional `extract_import_lines(source: str) -> List[str]` method
- Fence label uses `language_profile.language_id`

#### REQ-PE-401: Import Conventions Section Delegation

`_build_import_conventions_section()` MUST either delegate to the language profile or return empty string for non-Python tasks.

**Acceptance criteria:**
- When `language_profile.language_id != "python"`, the function returns `""` (the language profile's `coding_standards` and `get_import_syntax_guidance()` already cover import conventions for non-Python languages)
- No `__init__.py` or `.py`-specific logic runs for non-Python tasks

---

### Layer 5: Drafter Defaults & Safety (High)

#### REQ-PE-500: Language-Neutral Drafter Defaults

The drafter system prompt defaults MUST be language-neutral when no language profile is available.

**Current (Python-biased):**
```python
_role = language_role or "an expert Python engineer"
_standards = coding_standards or "Ruff: no single-letter vars..."
```

**Required:**
```python
_role = language_role or "a senior software engineer"
_standards = coding_standards or "Follow the language's standard style guide and idioms."
```

**Acceptance criteria:**
- `drafter.py` line ~202-206 uses language-neutral defaults
- A WARNING is logged when the fallback fires: `"Drafter using language-neutral defaults — no language_role in context"`

#### REQ-PE-501: Non-Python Source Files Get Quality Gates

Truncation detection and size regression checks MUST apply to source code files regardless of language. Only config/data files may be skipped.

**Current `_NON_PYTHON_EXTENSIONS` skip list includes:** `.go`, `.js`, `.ts`, `.java`

**Required split:**

| Category | Extensions | Truncation Check | Size Regression |
|----------|-----------|-----------------|-----------------|
| Source code | `.py`, `.go`, `.java`, `.js`, `.ts`, `.tsx`, `.jsx`, `.rs`, `.rb`, `.kt` | Yes | Yes |
| Config/data | `.yaml`, `.yml`, `.json`, `.xml`, `.toml`, `.cfg`, `.ini`, `.md`, `.txt`, `.in`, `.sql`, `.proto`, `.properties`, `.gradle` | No | No |
| Build/infra | `Dockerfile`, `Makefile`, `.sh`, `.bash` | No | No |

**Acceptance criteria:**
- `drafter.py` renames `_NON_PYTHON_EXTENSIONS` to `_CONFIG_DATA_EXTENSIONS` (or similar)
- Source code extensions are REMOVED from the skip list
- Go/Java/JS/TS source files get truncation detection and size regression checks
- Config/data/build files continue to be skipped

---

### Layer 6: Code Extraction Language Awareness (Medium)

#### REQ-PE-600: `extract_code_from_response` Prefers Matching Language Blocks

When the `language` parameter is provided, `extract_code_from_response()` MUST prefer code blocks whose fence language tag matches.

**Acceptance criteria:**
- When `language="java"` and the response has both a ` ```java ` block and a ` ```python ` block, the Java block is returned
- When no block matches the language, falls back to largest block (current behavior)
- When `language` is None, behavior is unchanged

#### REQ-PE-601: `audit_and_inject_imports` Logs Skip for Non-Python

When `audit_and_inject_imports()` receives non-Python code (detected by `ast.parse()` failure), it MUST log an INFO message explaining the skip.

**Acceptance criteria:**
- `ast.parse()` SyntaxError path logs: `"Import audit skipped: non-Python source (ast.parse failed)"`
- Code is returned unchanged (current behavior preserved)
- No functional change — this is observability only

---

## 4. Implementation Phases

### Phase 1: Output Format & Defaults (Prevents run-072 class failures)

| REQ | Effort | Files |
|-----|--------|-------|
| REQ-PE-100 | S | `contractor_prompts.yaml`, `prompts/__init__.py` |
| REQ-PE-101 | S | `contractor_prompts.yaml`, `prompts/__init__.py` |
| REQ-PE-500 | S | `drafter.py` |

**Rationale:** These 3 changes prevent the LLM from producing Python wrappers around non-Python content. No structural changes, just text updates.

### Phase 2: Fence & Template Parameterization (Fixes wiring bugs)

| REQ | Effort | Files |
|-----|--------|-------|
| REQ-PE-200 | S | `spec_builder.py` |
| REQ-PE-201 | S | `spec_builder.py` |
| REQ-PE-202 | S | `spec_builder.py` |
| REQ-PE-300 | M | `contractor_prompts.yaml`, `prompts/__init__.py`, `spec_builder.py` |
| REQ-PE-301 | S | `contractor_prompts.yaml`, `prompts/__init__.py`, `drafter.py` |
| REQ-PE-302 | S | `contractor_prompts.yaml`, `prompts/__init__.py` |

**Rationale:** Fixes all hardcoded Python content in templates. The YAML + fallback + wiring changes must be done together.

### Phase 3: Quality Gate Parity (Restores safety for non-Python source)

| REQ | Effort | Files |
|-----|--------|-------|
| REQ-PE-501 | M | `drafter.py` |
| REQ-PE-600 | S | `code_extraction.py` |
| REQ-PE-601 | S | `code_extraction.py` |

**Rationale:** Ensures Go/Java/JS source files get the same quality checks as Python.

### Phase 4: Sibling Import Generalization (Enables import context for non-Python)

| REQ | Effort | Files |
|-----|--------|-------|
| REQ-PE-400 | M | `spec_builder.py`, `languages/protocol.py` |
| REQ-PE-401 | S | `spec_builder.py` |

**Rationale:** The most complex change. Requires a new protocol method and per-language regex implementations. Deferred to Phase 4 because the existing `coding_standards` and `get_import_syntax_guidance()` provide partial coverage.

---

## 5. Test Plan

### Phase 1 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_drafter_system_prompt_contains_raw_output_instruction` | PE-100 | All 4 draft system templates contain "raw file content" |
| `test_drafter_default_role_is_language_neutral` | PE-500 | Missing `language_role` → "senior software engineer" (not "Python") |
| `test_drafter_default_standards_is_language_neutral` | PE-500 | Missing `coding_standards` → generic guidance (not Ruff) |
| `test_drafter_logs_warning_on_default_fallback` | PE-500 | Warning logged when fallback fires |

### Phase 2 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_reference_impl_fence_uses_go` | PE-200 | Go language profile → ` ```go ` fence |
| `test_reference_impl_fence_uses_java` | PE-200 | Java language profile → ` ```java ` fence |
| `test_reference_impl_fence_no_profile` | PE-200 | No profile → unlabeled ` ``` ` |
| `test_available_imports_yaml_has_import_syntax` | PE-300 | YAML template renders with `{import_syntax}` |
| `test_available_imports_go_syntax` | PE-300 | Go profile → Go import guidance (not "Python stdlib") |
| `test_skeleton_fill_go_stub_marker` | PE-301 | Go profile → `panic("not implemented")` |
| `test_skeleton_fill_java_stub_marker` | PE-301 | Java profile → `throw new UnsupportedOperationException()` |
| `test_multi_file_no_init_py_for_go` | PE-302 | Go task → no `__init__.py` rule in output format |
| `test_anti_pattern_skipped_for_go` | PE-202 | Go task → no Python `os.getenv` examples |

### Phase 3 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_go_source_gets_truncation_check` | PE-501 | `.go` file → truncation detection runs |
| `test_java_source_gets_size_regression` | PE-501 | `.java` file → size regression runs |
| `test_yaml_skips_truncation_check` | PE-501 | `.yaml` file → truncation detection skipped |
| `test_dockerfile_skips_size_regression` | PE-501 | `Dockerfile` → size regression skipped |
| `test_extract_code_prefers_matching_language` | PE-600 | `language="java"` + mixed blocks → Java block selected |
| `test_extract_code_falls_back_to_largest` | PE-600 | `language="java"` + no Java block → largest block |

### Phase 4 Tests

| Test | REQ | Description |
|------|-----|-------------|
| `test_sibling_imports_go_files` | PE-400 | Go project → Go import lines extracted and fenced as ` ```go ` |
| `test_sibling_imports_java_files` | PE-400 | Java project → Java import lines extracted |
| `test_sibling_imports_python_unchanged` | PE-400 | Python project → existing AST-based behavior unchanged |
| `test_import_conventions_skipped_for_go` | PE-401 | Go task → empty string returned |

---

## 6. Traceability

| REQ-PE | Traces To | Finding |
|--------|-----------|---------|
| PE-100, PE-101 | Run-072 `build.gradle` failure | F17 |
| PE-200 | Run-066 Python-biased reference code | F4 |
| PE-201 | F1 (sibling imports Python fence) | F1 |
| PE-202 | F3 (anti-patterns Python examples) | F3 |
| PE-300 | F15 (import syntax wiring bug), F5 (Python stdlib text) | F15, F5 |
| PE-301 | F7 (skeleton fill Python stub marker) | F7 |
| PE-302 | F9 (`__init__.py` in multi-file) | F9 |
| PE-400, PE-401 | F1 (sibling imports Python-only), F2 (import conventions Python-only) | F1, F2 |
| PE-500 | F6 (drafter defaults to Python) | F6 |
| PE-501 | F10 (Go/Java/JS skip quality gates) | F10 |
| PE-600 | F16 (language parameter unused) | F16 |
| PE-601 | F11 (import audit Python-only) | F11 |

---

## 7. Out of Scope

- **Per-language `audit_and_inject_imports()`** — Full deterministic import injection for Go/Java/Node.js requires language-specific AST or regex engines. The current Python-only implementation is safe (returns unchanged code). Generalization deferred until import errors become the top failure mode for a non-Python language.
- **Per-language token estimation** — The 4 chars/token heuristic is imprecise but safe for all languages. Language-specific calibration deferred.
- **`_looks_like_init` for Go/Java/Node.js** — Entry-point file heuristics (`main.go`, `Main.java`, `index.js`) are low priority. The multi-file extraction works correctly without them.
- **Language-specific drafter prompt templates** — Fully separate prompt templates per language (e.g., `draft_system_create_go`) are unnecessary given the parameterization approach. The same template with different placeholder values is sufficient.

---

## 8. LanguageProfile Protocol Extensions

Phase 4 requires one new optional method on the `LanguageProfile` protocol:

```python
def extract_import_lines(self, source: str) -> List[str]:
    """Extract import statements from source code.

    Returns a list of import lines (strings) found in the source.
    Used by sibling import extraction in the prompt engine.
    Default implementation returns empty list.
    """
    return []
```

Additionally, each language profile should expose a `stub_marker_text` property for REQ-PE-301:

```python
@property
def stub_marker_text(self) -> str:
    """Human-readable stub marker description for prompt templates.

    Examples:
        Python: '`raise NotImplementedError`'
        Go: '`panic("not implemented")`'
        Java: '`throw new UnsupportedOperationException()`'
    """
```

These are additive — no breaking changes to the protocol.
