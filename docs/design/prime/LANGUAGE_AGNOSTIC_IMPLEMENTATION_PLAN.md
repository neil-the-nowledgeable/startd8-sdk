# Language-Agnostic Refactor — Implementation Plan & Requirements Reflection

**Date:** 2026-03-18
**Companion to:** `LANGUAGE_AGNOSTIC_REFACTOR_REQUIREMENTS.md`
**Purpose:** (1) Concrete implementation plan, (2) Critical reflection on requirements, surfacing gaps, over-engineering, and quick wins discovered during planning.
**Revision 2:** Second-pass reflection after plan was concrete enough to reveal structural issues.

---

## Part 1: Critical Reflection on Requirements

Planning the implementation exposed several issues with the original requirements — blind spots, over-engineering, and quick wins that weren't visible until the actual code was examined line by line.

### CRITICAL GAP #1: spec_builder.py Language Section Builders (Biggest Miss)

**The requirements focused on the wrong target in spec_builder.py.**

REQ-LA-301 targets `detect_java_frameworks()` (48 lines, lines 87–135). But the far larger language-specific surface is the **three P0 section builder functions** that the requirements never mention:

| Function | Lines | Size | What It Does |
|----------|-------|------|-------------|
| `_build_go_module_section()` | 384–451 | 68 lines | Go package declaration, module path, import rules, structural rules |
| `_build_nodejs_module_section()` | 454–513 | 60 lines | ESM vs CommonJS rules, import/export patterns, Node.js conventions |
| `_build_java_project_section()` | 516–582 | 67 lines | Java package declaration, class naming, import rules, structural rules |

Plus `_build_available_imports_section()` (lines 285–382) has a **4-way language dispatch** (lines 296–370) for dependency formatting AND import syntax guidance.

And `build_spec_prompt()` (lines 1132–1149) hard-codes calls to all three section builders with language-gated P0 priority insertion.

**Impact on C#:** Without addressing this, adding C# means writing a NEW `_build_csharp_project_section()` (50-70 lines) AND updating `build_spec_prompt()` to call it. That's exactly the shotgun surgery we're trying to eliminate.

**New requirement needed:** A protocol method `build_project_context_section(context: Dict) -> str` that each profile implements. The spec_builder calls `profile.build_project_context_section(context)` once — no language-specific function per language in the pipeline.

### CRITICAL GAP #2: derive_service_metadata() Needs Richer Context

REQ-LA-201 specifies `derive_service_metadata(features, onboarding)`. But examining the actual code reveals each language block accesses pre-computed data from the function's preamble:

- **Go** (line 320): Uses `api_sigs` for module path fallback (`sig.startswith("module ")`)
- **Java** (lines 388–399): Uses `all_runtime_deps + all_api_sigs` for `spring_boot` detection
- **Node.js** (line 412): Uses target files aggregated across all features

The method signature should accept a `context` dict containing these pre-computed aggregates, not force each profile to re-scan `features`:

```python
def derive_service_metadata(
    self,
    features: Sequence[Any],
    *,
    onboarding: Optional[Dict[str, Any]] = None,
    api_signatures: Optional[List[str]] = None,
    runtime_dependencies: Optional[List[str]] = None,
) -> Dict[str, Any]:
```

### OVER-ENGINEERING #1: `code_fence_language` Protocol Property (REQ-LA-104)

Used in exactly **ONE place**: `framework_imports.py:192-193`, a 4-entry dict. Adding a protocol property (which must be implemented by all 5 profiles, tested, documented) is not justified.

**Better:** Expand the existing `_FENCE_MAP` to 5 entries. Total cost: 1 line. Or use `profile.language_id` directly — most language IDs already work as fence tags, and only `"nodejs"` → `"javascript"` needs mapping.

**Recommendation:** Downgrade REQ-LA-104 to a simple `_FENCE_MAP` update. Remove from protocol.

### OVER-ENGINEERING #2: `filename_associations` Protocol Property (REQ-LA-105)

The `_FILENAME_TO_LANG` dict in `lang_detect.py` has 6 entries across 2 languages (Java build files + Node package.json). This is stable, never changes, and can be trivially derived from existing `build_file_patterns` on profiles:

```python
# Already exists on every profile:
JavaLanguageProfile.build_file_patterns  # ["build.gradle", "settings.gradle", "pom.xml", "build.gradle.kts"]
NodeLanguageProfile.build_file_patterns  # ["package.json", "package-lock.json", "yarn.lock"]
```

**Better:** If `lang_detect.py` needs filename→language mapping, compute it once from `LanguageRegistry` profiles' `build_file_patterns`. No new protocol property needed.

**Recommendation:** Remove REQ-LA-105 from protocol. Use `build_file_patterns` in `lang_detect.py`.

### OVER-ENGINEERING #3: REQ-LA-501 Runtime Language Literal

Replacing `Language = Literal[...]` with runtime-derived values from `LanguageRegistry` breaks static type checking. The Literal type is used for type safety in function signatures. Making it dynamic defeats the purpose.

**Better:** Just add `"csharp"` to the Literal union. 5 languages is a fixed set — this is a one-line change.

### QUICK WIN #1: Fix Naming Inconsistency NOW (Pre-Requisite)

`derivation.py:_EXT_TO_LANGUAGE` uses `"javascript"` and `"typescript"` instead of the canonical `"nodejs"`. This forces the ugly multi-way check:

```python
is_nodejs = primary_lang == "nodejs" or primary_lang == "javascript" or (
    isinstance(primary_lang, list)
    and ("nodejs" in primary_lang or "javascript" in primary_lang)
)
```

**Fix:** Change `_EXT_TO_LANGUAGE` values from `"javascript"`/`"typescript"` to `"nodejs"`. This simplifies the check to `primary_lang == "nodejs"`. **5-minute change, zero risk, immediate clarity.**

Same fix in `plan_ingestion_workflow.py:_EXT_TO_LANGUAGE`.

This can be done independently before any refactoring. Commit it separately.

### QUICK WIN #2: `spring_boot` Not Threaded Through QP-1

`spring_boot` is extracted in the PARSE phase (`plan_ingestion_workflow.py:1435`) and stored on `ParsedFeature` (`plan_ingestion_models.py:247`), but it's **NOT in** `_CONTEXT_THREADABLE_FIELDS` and **NOT on** `SeedTask`.

It only reaches downstream via `infer_service_metadata()` which scans features for `spring_boot=True`. This works, but it's inconsistent — all other language-specific fields use QP-1 threading.

**Fix:** Add `spring_boot` to `_CONTEXT_THREADABLE_FIELDS` and to `SeedTask`. Then `derive_service_metadata()` can read it from context instead of scanning features.

### QUICK WIN #3: `infer_artifact_types_from_files()` Hardcoded Extensions

`derivation.py:231-235` hardcodes source extensions:
```python
elif any(name.endswith(ext) for ext in (".py", ".go", ".js", ".ts", ".rs", ".java", ".rb", ".cs")):
    inferred = "source_module"
```

This already includes `.cs` but is disconnected from the registry. Replace with `LanguageRegistry.get_extension_map()` keys for consistency. One-line change.

### DESIGN INSIGHT: `derive_service_metadata()` vs `build_project_context_section()` Symmetry

These two methods form a natural pair:
1. **`derive_service_metadata()`** — extracts language-specific metadata from plan features (runs during plan ingestion)
2. **`build_project_context_section()`** — produces language-specific prompt sections from task context (runs during code generation)

Both live on the language profile. Both take context dicts. Both replace if/elif chains in pipeline code. Implementing them together ensures the metadata produced by (1) is consumed correctly by (2).

### DESIGN INSIGHT: `_build_available_imports_section()` Dependency Formatting

Lines 310-370 of spec_builder.py have per-language dependency version stripping and import syntax guidance. Two protocol methods would absorb this:

```python
def strip_dependency_version(self, dep: str) -> str:
    """Strip version pin from a dependency string. E.g. 'grpcio==1.76.0' → 'grpcio'."""

def get_import_syntax_guidance(self) -> str:
    """Return language-specific import syntax guidance for LLM prompts."""
```

These are small (5-10 lines per profile) but eliminate another 4-way if/elif.

### FLEXIBILITY ISSUE: REQ-LA-302 Global FRAMEWORK_IMPORTS Removal

Moving `FRAMEWORK_IMPORTS` into `PythonLanguageProfile.framework_imports` is correct in principle but creates a **lazy import issue**. Currently:

```python
# python.py line 47-50:
@property
def framework_imports(self) -> Dict[str, dict]:
    from ..implementation_engine.framework_imports import FRAMEWORK_IMPORTS
    return FRAMEWORK_IMPORTS
```

PythonLanguageProfile already lazy-imports the global dict. If we move the dict INTO python.py, we create a circular dependency risk (framework_imports.py imports from python.py, python.py is in languages/).

**Better:** Keep `FRAMEWORK_IMPORTS` defined in `framework_imports.py` but rename it `_PYTHON_FRAMEWORK_IMPORTS` (private). `PythonLanguageProfile` continues to import it. `detect_frameworks()` no longer falls back to it — always uses `language_profile.framework_imports`. The dict stays where it is; only the access path changes.

### REVISED PRIORITY: What Actually Matters Most

The original P0 (extension mapping consolidation) is foundational but low-impact. The highest-value changes are:

1. **spec_builder.py section builders → protocol method** (eliminates 200+ lines of language branching from the pipeline AND makes C# addition trivial)
2. **derive_service_metadata() → protocol method** (eliminates 130+ lines of if/elif)
3. **C# profile creation** (the actual goal)
4. **Extension mapping consolidation** (cleanup, not blocking)

---

## Part 2: Revised Requirements (Amendments)

### NEW: REQ-LA-1000 — Language-Specific Prompt Section Builders

**REQ-LA-1001:** `LanguageProfile` protocol SHALL add a method:
```python
def build_project_context_section(self, context: Dict[str, Any]) -> str:
    """Build language-specific project context for the spec prompt.

    Returns a markdown section with language rules (package/namespace
    declaration, import syntax, structural conventions) or empty string
    if no special guidance is needed.
    """
```

**REQ-LA-1002:** Each language profile SHALL implement `build_project_context_section()` containing the logic currently in the corresponding spec_builder function:
- `GoLanguageProfile` — absorbs `_build_go_module_section()` (lines 384–451)
- `JavaLanguageProfile` — absorbs `_build_java_project_section()` (lines 516–582)
- `NodeLanguageProfile` — absorbs `_build_nodejs_module_section()` (lines 454–513)
- `PythonLanguageProfile` — returns `""` (Python has no special project context section)
- `CSharpLanguageProfile` — new C# project context section (namespace, using statements, .NET conventions)

**REQ-LA-1003:** `spec_builder.py:build_spec_prompt()` (lines 1136–1149) SHALL replace the three hard-coded section builder calls with a single dispatch:
```python
lang_profile = context.get("language_profile")
if lang_profile is not None:
    project_section = lang_profile.build_project_context_section(context)
    if project_section:
        prioritized.append((0, "project_context", project_section))
```

**REQ-LA-1004:** The three functions `_build_go_module_section()`, `_build_nodejs_module_section()`, `_build_java_project_section()` SHALL be removed from `spec_builder.py` after migration.

### NEW: REQ-LA-1100 — Dependency Formatting and Import Guidance

**REQ-LA-1101:** `LanguageProfile` protocol SHALL add:
```python
def strip_dependency_version(self, dep: str) -> str:
    """Strip version pin from dependency string for prompt display."""

def get_import_syntax_guidance(self) -> str:
    """Return language-specific import rules for LLM prompts."""
```

**REQ-LA-1102:** `_build_available_imports_section()` in `spec_builder.py` SHALL replace its 4-way is_go/is_java/is_nodejs/else block (lines 296–370) with calls to `profile.strip_dependency_version()` and `profile.get_import_syntax_guidance()`.

### REVISED: REQ-LA-201 — Richer Method Signature

Replace the original REQ-LA-201 with:

**REQ-LA-201 (revised):** `LanguageProfile` protocol SHALL add:
```python
def derive_service_metadata(
    self,
    features: Sequence[Any],
    *,
    onboarding: Optional[Dict[str, Any]] = None,
    api_signatures: Optional[List[str]] = None,
    runtime_dependencies: Optional[List[str]] = None,
) -> Dict[str, Any]:
```

The additional keyword arguments supply pre-computed aggregates that individual language blocks currently derive from the function preamble.

### DOWNGRADED: REQ-LA-104, REQ-LA-105

**REQ-LA-104 (downgraded):** Instead of a protocol property, add `"csharp": "csharp"` to `_FENCE_MAP` in `framework_imports.py`. Total change: 1 line.

**REQ-LA-105 (removed):** Derive filename→language mapping from `build_file_patterns` in `lang_detect.py`. No protocol change needed.

### DOWNGRADED: REQ-LA-501

**REQ-LA-501 (downgraded):** Add `"csharp"` to the `Language` Literal union. Do NOT make it dynamic — that breaks type checking for 5 fixed languages.

---

## Part 3: Implementation Plan

### Phase 0: Quick Wins (Independent, No Dependencies)

**Estimated scope:** 4 small commits, each independently testable.

#### 0a. Fix naming inconsistency in extension maps

**Files:**
- `src/startd8/seeds/derivation.py:37-50` — change `"javascript"` → `"nodejs"`, `"typescript"` → `"nodejs"`
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py:92-98` — same

**Test:** Existing tests for `infer_service_metadata()` with Node.js features still pass. The `is_nodejs` check in `derivation.py:401` can be simplified to `primary_lang == "nodejs"` (remove `or primary_lang == "javascript"` branch).

**Risk:** Low. Purely internal naming. No downstream consumers use `"javascript"` as a language_id.

#### 0b. Thread `spring_boot` through QP-1

**Files:**
- `src/startd8/seeds/models.py` — add `spring_boot: bool = False` to SeedTask
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` — add `"spring_boot"` to `_CONTEXT_THREADABLE_FIELDS`

**Test:** Plan ingestion of a Java/Spring Boot plan → seed task has `spring_boot=True` in context.

#### 0c. Add `"csharp"` to lang_detect.py Literal

**Files:**
- `src/startd8/micro_prime/lang_detect.py:12` — add `"csharp"` to `Language` Literal
- `src/startd8/micro_prime/lang_detect.py:15-39` — add `".cs": "csharp"` to `_EXTENSION_TO_LANG`

**Test:** `detect_language("src/Services/OrderService.cs") == "csharp"`

#### 0d. Add `.cs` to forward_manifest_validator.py

**Files:**
- `src/startd8/forward_manifest_validator.py` — add `elif suffix == ".cs": result = _validate_csharp_file(content, result)` in the dispatch chain (after `.java`), with a minimal `_validate_csharp_file()` that checks for balanced braces and a `namespace` or `using` declaration.

**Test:** `validate_disk_compliance()` on a `.cs` file doesn't crash, recognizes basic structure.

---

### Phase 1: Protocol Extensions + Extension Map Consolidation

**Estimated scope:** 1 focused commit.

#### 1a. Add `get_extension_map()` to LanguageRegistry

**File:** `src/startd8/languages/registry.py`

```python
@classmethod
def get_extension_map(cls) -> Dict[str, str]:
    """Canonical extension→language_id mapping from all registered profiles."""
    cls.discover()
    mapping: Dict[str, str] = {}
    with cls._lock:
        for profile in cls._profiles.values():
            for ext in profile.source_extensions:
                mapping[ext] = profile.language_id
    return mapping
```

Note: `discover()` is called first, solving the bootstrapping problem. `get_by_extension()` already does this (line 199).

#### 1b. Migrate extension mapping consumers

**File changes:**
- `src/startd8/languages/resolution.py` — delete `_EXT_TO_LANGUAGE_ID`, use `LanguageRegistry.get_extension_map()` in `resolve_language()`. Cache the result since it doesn't change after discovery.
- `src/startd8/seeds/derivation.py` — delete `_EXT_TO_LANGUAGE`, replace usage in `infer_service_metadata()` with `LanguageRegistry.get_extension_map()`. Normalize to use dotted extensions (`.py` not `py`) for consistency.
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` — delete `_EXT_TO_LANGUAGE`, use registry.
- `src/startd8/micro_prime/lang_detect.py` — replace `_EXTENSION_TO_LANG` with a lazy-computed version from `LanguageRegistry.get_extension_map()` merged with the non-language entries (`.proto`, `.toml`, `.yaml`, etc. → `"text"`). Retain `_FILENAME_TO_LANG` built from profiles' `build_file_patterns`.

**Key detail for lang_detect.py:** This module maps many non-language extensions to `"text"` (`.yaml`, `.json`, `.md`, `.sh`, etc.). These aren't language profiles. Solution: `get_extension_map()` for language extensions, keep a static `_TEXT_EXTENSIONS` set for the rest.

**Verification:** `grep -rn '_EXT_TO_LANG\|_EXTENSION_TO_LANG\|_EXT_TO_LANGUAGE' src/` → zero standalone dict definitions.

---

### Phase 2: Service Metadata → Protocol Method

**Estimated scope:** 1 commit. This is the biggest refactor — 130+ lines moved.

#### 2a. Add protocol method

**File:** `src/startd8/languages/protocol.py`

```python
def derive_service_metadata(
    self,
    features: Sequence[Any],
    *,
    onboarding: Optional[Dict[str, Any]] = None,
    api_signatures: Optional[List[str]] = None,
    runtime_dependencies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Derive language-specific service metadata from plan features.

    Returns dict of metadata keys (e.g., module_path, java_package).
    Called by seeds/derivation.py:infer_service_metadata() after
    language-agnostic metadata is computed.
    """
    ...
```

#### 2b. Implement on each profile

**Move the exact existing logic:**
- `GoLanguageProfile.derive_service_metadata()` ← `derivation.py:306-336`
- `JavaLanguageProfile.derive_service_metadata()` ← `derivation.py:338-400`
- `NodeLanguageProfile.derive_service_metadata()` ← `derivation.py:401-435`
- `PythonLanguageProfile.derive_service_metadata()` → returns `{}`

**Important:** The Java block imports `_derive_package` from `startd8.utils.java_file_assembler`. This lazy import moves into `JavaLanguageProfile.derive_service_metadata()` — same pattern, different location.

#### 2c. Refactor `infer_service_metadata()`

**File:** `src/startd8/seeds/derivation.py`

The function preamble (lines 242-305) stays — it aggregates features into `protocols`, `all_runtime_deps`, `all_api_sigs`, `languages`, etc. Then:

```python
# Replace 130 lines of if/elif with:
primary_lang = metadata.get("primary_language", "")
lang_id = primary_lang if isinstance(primary_lang, str) else (primary_lang[0] if primary_lang else "")
profile = LanguageRegistry.get(lang_id)
if profile is not None:
    lang_metadata = profile.derive_service_metadata(
        features,
        onboarding=onboarding,
        api_signatures=api_sigs,
        runtime_dependencies=runtime_deps,
    )
    metadata.update(lang_metadata)
```

**Verification:** `grep -n 'is_go\|is_java\|is_nodejs' src/startd8/seeds/derivation.py` → zero matches.

---

### Phase 3: Prompt Section Builders → Protocol Method

**Estimated scope:** 1 commit. Moves ~200 lines from spec_builder into profiles.

#### 3a. Add protocol methods

**File:** `src/startd8/languages/protocol.py`

```python
def build_project_context_section(self, context: Dict[str, Any]) -> str:
    """Build language-specific project context for spec prompts."""
    ...

def strip_dependency_version(self, dep: str) -> str:
    """Strip version pin from dependency string for prompt display."""
    ...

def get_import_syntax_guidance(self) -> str:
    """Return language-specific import rules for LLM prompts."""
    ...
```

#### 3b. Implement on each profile

Move the exact existing logic from spec_builder.py:
- `GoLanguageProfile.build_project_context_section()` ← `_build_go_module_section()` (lines 384-451)
- `JavaLanguageProfile.build_project_context_section()` ← `_build_java_project_section()` (lines 516-582)
- `NodeLanguageProfile.build_project_context_section()` ← `_build_nodejs_module_section()` (lines 454-513)
- `PythonLanguageProfile.build_project_context_section()` → returns `""`

For `strip_dependency_version()`:
- Python: split on `==`, `>=`, etc. (lines 329-334)
- Go: `dep.split()[0]` (line 328)
- Java: `:`.join(parts[:2])` (lines 311-314)
- Node.js: scoped package handling (lines 316-325)

For `get_import_syntax_guidance()`:
- Each returns its 3-4 line guidance string (lines 341-370)

#### 3c. Simplify spec_builder.py

**Replace** in `build_spec_prompt()` (lines 1136-1149):
```python
# Before: 3 hard-coded section builder calls
go_module_section = _build_go_module_section(context)
if go_module_section:
    prioritized.append((0, "go_module", go_module_section))
java_section = _build_java_project_section(context)
if java_section:
    prioritized.append((0, "java_project", java_section))
nodejs_section = _build_nodejs_module_section(context)
if nodejs_section:
    prioritized.append((0, "nodejs_module", nodejs_section))

# After: 1 generic call
lang_profile = context.get("language_profile")
if lang_profile is not None:
    project_section = lang_profile.build_project_context_section(context)
    if project_section:
        prioritized.append((0, "project_context", project_section))
```

**Replace** in `_build_available_imports_section()` (lines 296-370):
```python
# Before: 4-way is_go/is_java/is_nodejs/else
# After:
lang_profile = context.get("language_profile")
for dep in sorted(deps):
    if lang_profile:
        pkg = lang_profile.strip_dependency_version(dep)
    else:
        # fallback: Python-style stripping
        pkg = dep
        for sep in ("==", ">=", "<=", "~=", "!=", "<", ">"):
            pkg = pkg.split(sep)[0]
        pkg = pkg.strip()
# ...
if lang_profile:
    import_syntax = lang_profile.get_import_syntax_guidance()
else:
    import_syntax = "Use ONLY these packages plus Python stdlib..."
```

**Delete** the three standalone functions.

#### 3d. Unify framework detection (original REQ-LA-301, LA-302)

- Delete `detect_java_frameworks()` from spec_builder.py
- Remove its call site in `build_spec_context_section()` (line 167)
- Rename `FRAMEWORK_IMPORTS` → `_PYTHON_FRAMEWORK_IMPORTS` in `framework_imports.py` (private)
- `detect_frameworks()` always requires `language_profile` param — no global fallback
- Update `_FENCE_MAP` to include `"csharp": "csharp"` (1 line)

**Verification:** `grep -rn 'detect_java_frameworks\|_build_go_module\|_build_nodejs_module\|_build_java_project' src/startd8/implementation_engine/` → zero matches.

---

### Phase 4: C# Language Profile

**Estimated scope:** 1 commit. Self-contained — all infrastructure from Phases 0-3 is in place.

#### 4a. Create `src/startd8/languages/csharp.py`

Implement all protocol properties/methods per REQ-LA-601 table, plus the new methods:
- `derive_service_metadata()` — derive `csharp_namespace` from target file paths, `target_framework` from onboarding
- `build_project_context_section()` — C# namespace declaration, `using` statement rules, .NET conventions
- `strip_dependency_version()` — NuGet format: `PackageName/1.0.0` → `PackageName`
- `get_import_syntax_guidance()` — "Use `using` directives for all namespaces..."
- `generate_dependency_file()` — `.csproj` XML generation
- `framework_imports` — ASP.NET Core, EF Core, gRPC, Serilog patterns
- `get_stdlib_prefixes()` — `("System", "Microsoft")`
- `validate_syntax()` — text-based: check for `namespace` or top-level statements, balanced braces, C# type declarations

#### 4b. Wire into pipeline

- `src/startd8/seeds/models.py` — add `csharp_namespace: str = ""`, `target_framework: str = ""`
- `src/startd8/workflows/builtin/plan_ingestion_models.py` — add same fields to `ParsedFeature`
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py`:
  - Add `csharp_namespace`, `target_framework` to `_CONTEXT_THREADABLE_FIELDS`
  - Add C# extraction fields to PARSE prompt (lines 339-345 area)
  - Add C# extraction guidance to PARSE prompt (lines 371-377 area)
  - Add `csharp_namespace` and `target_framework` to feature construction (lines 1430-1437 area)
- `pyproject.toml` — add `csharp = "startd8.languages.csharp:CSharpLanguageProfile"` entry point

#### 4c. Verification tests

- `tests/unit/languages/test_csharp_profile.py` — profile properties, validate_syntax(), generate_dependency_file(), derive_service_metadata(), build_project_context_section()
- `tests/unit/validators/test_csharp_disk_validators.py` — forward manifest validation for .cs files
- `tests/unit/workflows/test_plan_ingestion_csharp.py` — PARSE extraction of C# fields, context threading

---

### Phase 5: Node.js Formalization

**Estimated scope:** 1 small commit. Node.js profile already exists — just add the new methods.

- Implement `derive_service_metadata()` (move from derivation.py — already done in Phase 2)
- Implement `build_project_context_section()` (move from spec_builder.py — already done in Phase 3)
- Implement `strip_dependency_version()` and `get_import_syntax_guidance()`

If Phases 2-3 are done correctly, this is already complete. Phase 5 is just verification that Node.js works end-to-end.

---

### Phase 6: Checkpoint Cleanup (Optional)

- `checkpoint.py:_get_source_extensions()` — log warning instead of silent Python fallback
- `checkpoint.py:capture_test_baseline()` — use `profile.test_command` (already partially done, lines 151-155)
- Remove hard-coded `.py` check in `_run_pre_merge_validation()` (line 552) — use `profile.language_id == "python"` (already partially done)

---

## Part 4: Revised Priority Order

The original plan had extension mapping consolidation as P0. After reflection, the highest-value work is the protocol methods that eliminate language branching from the pipeline.

| Phase | What | Lines Eliminated | Files Changed | Value |
|-------|------|-----------------|---------------|-------|
| **0** | Quick wins (naming fix, spring_boot, .cs in lang_detect, .cs in validator) | ~15 | 5 | Immediate clarity, unblocks later phases |
| **1** | Extension map consolidation | ~60 (4 dicts) | 5 | Dedup, single source of truth |
| **2** | `derive_service_metadata()` → protocol | ~130 (if/elif chains) | 6 | Biggest derivation.py cleanup |
| **3** | Prompt section builders → protocol + framework unification | ~250 (3 functions + detect_java) | 7 | Biggest spec_builder cleanup, **enables C# without shotgun surgery** |
| **4** | C# language profile | +350 (new) | 6 | **The goal** — trivial after Phases 0-3 |
| **5** | Node.js verification | ~0 (already moved in Phase 2-3) | 1 | Confidence |
| **6** | Checkpoint cleanup | ~10 | 1 | Polish |

**Total lines eliminated from pipeline code:** ~455
**Total lines added to profiles:** ~350 (moved, not new logic)
**Net complexity reduction:** Pipeline becomes language-agnostic; all language knowledge lives in profiles.

---

## Part 5: Dependency Graph

```
Phase 0 (quick wins) ─────── independent, do first
    │
Phase 1 (extension maps) ─── depends on Phase 0a (naming fix)
    │
Phase 2 (metadata) ────────── depends on Phase 1 (registry.get_extension_map used in derivation.py)
    │
Phase 3 (prompt sections) ── depends on Phase 2 (profiles have derive_service_metadata)
    │
Phase 4 (C# profile) ──────── depends on Phases 1-3 (protocol methods exist)
    │
Phase 5 (Node.js verify) ─── depends on Phases 2-3
    │
Phase 6 (checkpoint) ──────── independent, can be done anytime after Phase 1
```

**Critical path:** 0 → 1 → 2 → 3 → 4

---

## Part 6: Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Moving 200+ lines of prompt logic into profiles breaks existing spec prompts | Diff the prompt output before/after for a Go, Java, and Node.js task — must be byte-identical |
| `get_extension_map()` returns empty during early init | `discover()` called first (same as `get_by_extension()`). Tests use `LanguageRegistry.register()` directly. |
| `derive_service_metadata()` on profile doesn't have access to all the same data | Revised signature includes `api_signatures` and `runtime_dependencies` kwargs |
| `detect_frameworks()` without global fallback breaks callers that don't pass language_profile | Audit all call sites. `framework_imports.py:detect_frameworks()` is called from `spec_builder.py:_build_framework_imports_section()` which already passes `lang_profile`. |
| Python `FRAMEWORK_IMPORTS` circular import if moved into python.py | Keep dict in `framework_imports.py` as `_PYTHON_FRAMEWORK_IMPORTS`, imported by PythonLanguageProfile |
| Existing tests mock internal functions being moved | Run full test suite after each phase. `mock.patch` targets must be updated to new locations. |

---

## Part 7: Test Strategy

Each phase has a verification gate:

| Phase | Verification |
|-------|-------------|
| 0 | Existing tests pass. `is_nodejs` simplification doesn't change behavior. |
| 1 | `grep` for standalone dicts → zero. `resolve_language()` still works for all 4 languages. |
| 2 | `grep is_go\|is_java\|is_nodejs derivation.py` → zero. Existing seed derivation tests pass. |
| 3 | Spec prompt output for Go/Java/Node.js tasks is byte-identical before/after. `grep detect_java_frameworks spec_builder.py` → zero. |
| 4 | New C# test suite passes. `resolve_language(["Foo.cs"])` → CSharpLanguageProfile. Plan ingestion extracts C# fields. |
| 5 | Node.js end-to-end test passes. |
| 6 | Checkpoint tests pass without Python fallback. |

---

## Part 8: Second-Pass Reflection (Post-Plan Review)

After the plan was concrete enough to trace every code movement, a second critical review surfaced structural issues, additional quick wins, and one requirement that should be removed.

### STRUCTURAL ISSUE #1: Too Many Phases — Collapse 2 and 3

Phases 2 (metadata → protocol) and 3 (prompt sections → protocol) implement the **same pattern**: move language-specific logic from a pipeline module into protocol methods on profiles. They touch different files and have no dependency between them. Separating them into two phases doubles the context-switch overhead (two commit cycles, two test runs, two review rounds) without reducing risk.

**Recommendation:** Merge into a single "Protocol Methods + Pipeline Simplification" phase. Add ALL new protocol methods to `protocol.py` at once (`derive_service_metadata`, `build_project_context_section`, `strip_dependency_version`, `get_import_syntax_guidance`), implement them on all 4 existing profiles, then simplify both `derivation.py` and `spec_builder.py` in the same commit.

This reduces the plan from 7 phases to **5 phases**:

| Phase | What | Was |
|-------|------|-----|
| 0 | Quick wins | Same |
| 1 | Extension map consolidation | Same |
| **2** | **ALL protocol methods + pipeline simplification** | **Old Phases 2+3 merged** |
| 3 | C# profile + wiring | Old Phase 4 |
| 4 | Cleanup + verification | Old Phases 5+6 |

### STRUCTURAL ISSUE #2: Build C# Alongside, Not After

The current plan creates the C# profile AFTER all refactoring is done (Phase 4). But during Phase 2 (merged), we're already implementing `derive_service_metadata()` and `build_project_context_section()` on all 4 profiles. Adding the 5th profile (C#) in the SAME phase is marginal cost — one more implementation of each method.

**Why this matters:** If C# is in Phase 2 (merged), then by the end of that single phase, EVERYTHING works — all 5 languages, all protocol methods, pipeline simplified. No "refactoring is done but C# still needs wiring" intermediate state. Phase 3 becomes just plan ingestion PARSE prompt additions and test creation.

**Revised 4-phase plan:**

| Phase | What |
|-------|------|
| 0 | Quick wins (naming fix, spring_boot, .cs in lang_detect + validator) |
| 1 | Extension map consolidation |
| **2** | **Protocol methods on all 5 profiles (including NEW csharp.py) + pipeline simplification** |
| 3 | Plan ingestion C# wiring (PARSE prompt, threadable fields, SeedTask fields) + tests + cleanup |

Phase 2 is large but atomic — it's the "make the architecture right" commit. Phase 3 is the "wire C# into the data pipeline" commit.

### REQUIREMENT TO REMOVE: REQ-LA-1203

REQ-LA-1203 says `infer_artifact_types_from_files()` should use `LanguageRegistry.get_extension_map()` for source module detection instead of the hardcoded extension tuple.

**This is wrong.** The hardcoded list is:
```python
(".py", ".go", ".js", ".ts", ".rs", ".java", ".rb", ".cs")
```

It's deliberately MORE inclusive than the registry — it includes `.rs` (Rust), `.rb` (Ruby), and `.ts` (TypeScript), none of which are registered language profiles. Using `get_extension_map()` would **silently drop** those extensions, making the function LESS capable. The function's job is artifact TYPE classification ("is this a source file?"), not language identification. A Rust file is a source module even though we don't have a RustLanguageProfile.

**Recommendation:** Remove REQ-LA-1203. The hardcoded list is correct and already includes `.cs`.

### QUICK WIN #4: 1,168 Lines of Untracked Tests Already Exist

Git status shows 4 untracked test files with 1,168 lines total:
```
?? tests/unit/implementation_engine/test_java_spec_sections.py     (237 lines)
?? tests/unit/languages/test_nodejs_framework_detection.py          (206 lines)
?? tests/unit/validators/test_nodejs_disk_validators.py             (249 lines)
?? tests/unit/workflows/test_plan_ingestion_multi_language.py       (476 lines)
```

These pass (109/110, with 1 minor assertion mismatch: `test_default_esm` expects ESM but code defaults to CommonJS at `spec_builder.py:471`). They should be committed in Phase 0 — they provide regression coverage for the refactoring phases.

### QUICK WIN #5: Fix the Node.js Module System Default Bug

`spec_builder.py:471` defaults to `"commonjs"` when no module_system is specified:
```python
if not module_system:
    module_system = "commonjs"  # Node.js default when package.json has no "type" field
```

The test `test_default_esm` expects `"esm"`. The code comment says CommonJS is correct (it IS the Node.js default). The test is wrong. Fix the test, not the code. But this discrepancy reveals that the default may need to be configurable or at least documented. When this logic moves into `NodeLanguageProfile.build_project_context_section()`, the default should be a named constant on the profile.

### QUICK WIN #6: REQ-LA-601 Table is Incomplete

The requirements table for `CSharpLanguageProfile` lists 12 properties but the protocol has **22 properties/methods**. Missing from the table:

| Property/Method | Value for C# |
|----------------|-------------|
| `package_alias_map` | `{}` (NuGet names match namespace names) |
| `cleanup_patterns` | `["bin/", "obj/", ".vs/"]` |
| `blast_radius_extensions` | `[".cs"]` |
| `import_pattern_template` | `"using.*{module}"` |
| `system_prompt_role` | `"an expert C# / .NET engineer"` |
| `coding_standards` | PascalCase public, camelCase private, nullable refs, async/await |
| `function_start_pattern` | `r'^\s*(?:public\|private\|protected\|internal)?\s*(?:static\s+)?(?:async\s+)?[\w<>\[\]]+\s+(?P<name>\w+)\s*\('` |
| `supports_extension(ext)` | `ext.lower() == ".cs"` |
| `get_import_patterns(stem)` | `[f"using {stem}", f"using static {stem}"]` |
| `get_stdlib_prefixes()` | `("System", "Microsoft")` |
| `post_generation_cleanup()` | `[]` (no authoritative CLI formatter; `dotnet format` requires project context) |

These are essential for correctness — blast radius scanning, import pattern matching, and prompt engineering all use these values. **Update REQ-LA-601 to include all 22 protocol members.**

### QUICK WIN #7: Extract Balanced-Brace Validation as Shared Utility

Java's `_text_based_java_validate()` (`java.py:337-366`) contains a brace-depth validation loop that C# will need identically. Currently it's a private function in `java.py`. Extract it as:

```python
# languages/_validation_utils.py
def check_balanced_braces(code: str) -> tuple[bool, str]:
    """Check that braces are balanced in source code."""
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, "unbalanced braces (extra closing brace)"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"
    return True, ""
```

Java's `_text_based_java_validate()` and C#'s `validate_syntax()` both call it. Saves ~10 lines of duplication and ensures consistent behavior. Tiny change, done in Phase 2 alongside profile implementations.

### KNOWN LIMITATION: TypeScript Gap in NodeLanguageProfile

`resolution.py` maps `.ts`/`.tsx` to `"nodejs"`, but `NodeLanguageProfile.source_extensions` only includes `[".js", ".mjs", ".cjs"]`. This means:
- `resolve_language(["app.ts"])` → NodeLanguageProfile (works)
- `profile.source_extensions` → `[".js", ".mjs", ".cjs"]` (no .ts)
- `checkpoint._get_source_extensions()` → misses .ts files

This is intentional — the profile's `syntax_check_command` (`node --check`) and `validate_syntax()` don't work on TypeScript files. TypeScript requires `tsc` compilation, which is a different capability.

**Don't fix this now.** Adding `.ts` to `source_extensions` would make checkpoint try to run `node --check` on TypeScript files, which would fail. If TypeScript support is needed later, it would be a separate `TypeScriptLanguageProfile` with `tsc` tooling, or a TypeScript-aware flag on NodeLanguageProfile.

**Document as known limitation in the requirements.**

### RISK REFINEMENT: Spec Prompt Parity is the Highest-Risk Verification

Phase 2 (merged) moves prompt-generating code from `spec_builder.py` into profiles. If the moved code produces even slightly different output, the LLM will generate different code. This is subtle and hard to test with unit tests.

**Mandatory verification protocol:**
1. BEFORE Phase 2, capture golden spec prompt output for 3 tasks (Go, Java, Node.js) by calling `build_spec_prompt()` with representative contexts
2. AFTER Phase 2, generate the same prompts and diff
3. Diffs MUST be zero (not "approximately similar" — byte-identical)

This is not just a test — it's a GATE. If the diff is non-zero, Phase 2 has a bug. Do not proceed to Phase 3.

### REVISED 4-PHASE PLAN SUMMARY

```
Phase 0: Quick wins + commit existing tests (0a-0e, 5 small commits)
    │
Phase 1: Extension map consolidation (1 commit)
    │
Phase 2: Protocol methods on ALL 5 profiles + pipeline simplification (1-2 commits)
    │         - csharp.py created HERE (not after)
    │         - derive_service_metadata() on all profiles
    │         - build_project_context_section() on all profiles
    │         - strip_dependency_version() + get_import_syntax_guidance() on all profiles
    │         - derivation.py if/elif eliminated
    │         - spec_builder.py section builders eliminated
    │         - framework detection unified
    │         - balanced-brace utility extracted
    │
Phase 3: C# plan ingestion wiring + tests + cleanup (1 commit)
    │         - PARSE prompt C# fields
    │         - SeedTask C# fields
    │         - _CONTEXT_THREADABLE_FIELDS update
    │         - ParsedFeature C# fields
    │         - Checkpoint cleanup
    │         - Full test suite for all 5 languages
```

**Critical path: 0 → 1 → 2 → 3**
**Total phases: 4 (reduced from 7)**
**Total commits: ~8-9 (reduced from ~10-12)**
