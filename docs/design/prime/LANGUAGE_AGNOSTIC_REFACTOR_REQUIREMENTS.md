# Language-Agnostic Prime Contractor — Refactor Requirements

**Date:** 2026-03-18
**Status:** Draft
**Scope:** Refactor Prime Contractor pipeline from ad-hoc per-language branching to configuration-driven language support. Add C# and Node.js (formalize existing partial support).
**Languages:** Python, Go, Java, Node.js, C# (final set — no further languages planned)

---

## 1. Problem Statement

Multi-language support was added incrementally: Python first, then Go, then Java, each as one-off implementations. This produced accidental complexity:

1. **Extension-to-language mappings duplicated in 4 files** with different formats and different language name conventions (`"nodejs"` vs `"javascript"` vs `"typescript"`)
2. **Service metadata derivation via if/elif chains** in `seeds/derivation.py` — one 30-60 line block per language, violating Open/Closed Principle
3. **Framework detection inconsistency** — Python uses a global dict, Java has a dedicated detector function in `spec_builder.py`, Go/Node use only the language profile
4. **Hard-coded suffix routing** in `forward_manifest_validator.py`, `checkpoint.py`, and `micro_prime/lang_detect.py` instead of dispatching through the language profile
5. **Python-centric defaults** — checkpoint defaults to `{".py"}` extensions, AST cache only parses `.py`, test baseline hard-codes `pytest`
6. **`Language` Literal type in `lang_detect.py`** is disconnected from `LanguageRegistry`

Adding C# today would require edits in **10+ locations** across scattered if/elif chains. The goal is to reduce this to **1 new file + 1 entry point registration + tests**.

---

## 2. Accidental vs Essential Complexity

### 2.1 Accidental Complexity (to eliminate)

| Accidental Complexity | Where | Root Cause |
|----------------------|-------|------------|
| 4 duplicate extension→language mappings | `resolution.py`, `derivation.py`, `plan_ingestion_workflow.py`, `lang_detect.py` | Each module built its own mapping instead of sharing |
| Language name inconsistency | `"nodejs"` vs `"javascript"` vs `"typescript"` across files | No canonical name registry |
| `detect_java_frameworks()` in `spec_builder.py` | `spec_builder.py:87-135` | Java added after the framework detection protocol was established; duplicated instead of using it |
| Python global `FRAMEWORK_IMPORTS` dict alongside per-profile dicts | `framework_imports.py:22-81` | Python frameworks were hard-coded before the profile protocol existed |
| `_FENCE_MAP` in `framework_imports.py` | `framework_imports.py:185-193` | Language→code-fence mapping done ad-hoc instead of via profile |
| Service metadata if/elif blocks (Go, Java, Node.js) | `derivation.py:306-435` | Each language bolted onto a monolithic function |
| Hard-coded `{".py"}` fallback in checkpoint | `checkpoint.py:243-247` | Python assumed as default |
| AST cache restricted to `.py` | `checkpoint.py:183-200` | No equivalent semantic analysis for other languages |
| `Language` Literal type disconnected from registry | `lang_detect.py:12` | MicroPrime built its own language enumeration |
| `_EXT_TO_LANGUAGE` in `derivation.py` uses dot-less keys | `derivation.py:37-50` | Different convention from `resolution.py` |

### 2.2 Essential Complexity (to preserve/add)

| Essential Complexity | Why It's Necessary |
|---------------------|-------------------|
| `LanguageProfile` protocol (15 properties/methods) | Each language genuinely differs in syntax check, lint, test, imports, merge strategy, stub patterns, cleanup, dependency files |
| Per-language service metadata derivation | Go needs `module_path`/`service_name`, Java needs `java_package`/`build_system`, Node needs `module_system`, C# needs `namespace`/`target_framework` — these are irreducibly different |
| Per-language framework registries | Spring Boot, Express, ASP.NET have genuinely different detection patterns and import syntax |
| Language-specific `SeedTask` fields | Downstream prompt construction needs language-specific context (e.g., Go module path in `go.mod` generation) |
| Non-Python MicroPrime bypass | Python has AST-based element-level generation; other languages use file-whole generation — this is a real capability gap |
| Extension→language resolution | Files must be mapped to languages; the logic is simple but must exist somewhere |

---

## 3. Requirements

### 3.1 Consolidate Extension Mappings (REQ-LA-100)

**Goal:** Single canonical source for extension→language ID mapping.

**REQ-LA-101:** `LanguageRegistry` SHALL expose a `get_extension_map() -> Dict[str, str]` class method that computes the extension→language_id mapping from registered profiles' `source_extensions` properties.

**REQ-LA-102:** The following files SHALL be updated to use `LanguageRegistry.get_extension_map()` instead of local mappings:
- `seeds/derivation.py` — remove `_EXT_TO_LANGUAGE` dict
- `workflows/builtin/plan_ingestion_workflow.py` — remove `_EXT_TO_LANGUAGE` dict
- `micro_prime/lang_detect.py` — remove `_EXTENSION_TO_LANG` dict (retain `_FILENAME_TO_LANG` for special filenames like `Dockerfile`, `build.gradle`)

**REQ-LA-103:** `languages/resolution.py` SHALL delegate to `LanguageRegistry.get_extension_map()` instead of maintaining its own `_EXT_TO_LANGUAGE_ID` dict.

**REQ-LA-104 (downgraded):** ~~`LanguageProfile` protocol SHALL add a `code_fence_language` property~~ Add `"csharp": "csharp"` to `_FENCE_MAP` in `framework_imports.py`. A protocol property is over-engineering for a 5-entry dict used in one location. See implementation plan for rationale.

**REQ-LA-105 (removed):** ~~`LanguageProfile` protocol SHALL add a `filename_associations` property~~ Derive filename→language mapping from existing `build_file_patterns` on profiles. No protocol change needed — `lang_detect.py` can compute `_FILENAME_TO_LANG` from `LanguageRegistry` profiles' `build_file_patterns`.

### 3.2 Move Service Metadata Derivation to Language Profiles (REQ-LA-200)

**Goal:** Replace the if/elif chain in `infer_service_metadata()` with per-profile dispatch.

**REQ-LA-201 (revised):** `LanguageProfile` protocol SHALL add a method:
```python
def derive_service_metadata(
    self,
    features: Sequence[Any],
    *,
    onboarding: Optional[Dict[str, Any]] = None,
    api_signatures: Optional[List[str]] = None,
    runtime_dependencies: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Derive language-specific service metadata from plan features."""
```

The additional keyword arguments supply pre-computed aggregates from the function preamble. Go uses `api_signatures` for module path fallback; Java uses `runtime_dependencies` for `spring_boot` detection. Without these, each profile would redundantly re-scan all features.

**REQ-LA-202:** Each language profile SHALL implement `derive_service_metadata()` containing the logic currently in the corresponding if/elif block of `derivation.py:infer_service_metadata()`:
- `GoLanguageProfile` — module_path, service_name, go_version derivation
- `JavaLanguageProfile` — java_package, build_system, java_version, spring_boot derivation
- `NodeLanguageProfile` — module_system, node_version derivation
- `PythonLanguageProfile` — empty dict (no language-specific metadata currently)
- `CSharpLanguageProfile` — namespace, target_framework derivation (new)

**REQ-LA-203:** `derivation.py:infer_service_metadata()` SHALL be refactored to:
1. Resolve the language profile via `resolve_language(target_files)`
2. Call `profile.derive_service_metadata(features, onboarding)`
3. Merge the result into the metadata dict

The function body SHALL contain zero language-specific if/elif blocks.

**REQ-LA-204:** `SeedTask` SHALL add C#-specific fields:
```python
csharp_namespace: str = ""       # e.g., "MyApp.Services"
target_framework: str = ""       # e.g., "net8.0"
```

**REQ-LA-205:** `_CONTEXT_THREADABLE_FIELDS` in `plan_ingestion_workflow.py` SHALL include the new C# fields (`csharp_namespace`, `target_framework`).

### 3.3 Unify Framework Detection (REQ-LA-300)

**Goal:** All framework detection goes through the language profile. No language-specific detector functions in the pipeline.

**REQ-LA-301:** `detect_java_frameworks()` in `spec_builder.py` SHALL be removed. Java framework detection SHALL use `JavaLanguageProfile.framework_imports` exclusively, matching the pattern already used by Go and Node.js.

**REQ-LA-302:** The global `FRAMEWORK_IMPORTS` dict in `framework_imports.py` SHALL be moved into `PythonLanguageProfile.framework_imports`, making Python consistent with other languages. The `detect_frameworks()` function SHALL always use `language_profile.framework_imports` — no fallback to a global dict.

**REQ-LA-303:** `get_import_preamble()` SHALL use `language_profile.code_fence_language` (REQ-LA-104) instead of the hard-coded `_FENCE_MAP`.

### 3.4 Language-Aware Checkpoint and Validation (REQ-LA-400)

**Goal:** Checkpoint and validation dispatch through the language profile, not suffix checks.

**REQ-LA-401:** `checkpoint.py:_get_source_extensions()` SHALL require a language profile (no Python fallback). Callers that don't have a profile SHALL resolve one via `resolve_language()`.

**REQ-LA-402:** `checkpoint.py:capture_test_baseline()` SHALL use `language_profile.test_command` instead of hard-coding `pytest`. If `test_command is None`, skip baseline capture (existing behavior for Go/Java).

**REQ-LA-403:** `forward_manifest_validator.py` file suffix routing SHALL be replaced with language profile dispatch. The profile MAY expose a `reconcile_file()` method, or the validator MAY resolve language per-file and dispatch to a registry of reconciliation strategies.

**Note:** REQ-LA-403 is a refactoring opportunity but NOT blocking for C#/Node.js addition. The existing pattern (add an elif for `.cs`) works. Prioritize only if the file is already being modified.

### 3.5 Unify MicroPrime Language Detection (REQ-LA-500)

**REQ-LA-501 (downgraded):** ~~`micro_prime/lang_detect.py` SHALL replace the `Language` Literal type with runtime values~~ Add `"csharp"` to the existing `Language` Literal union. Making it dynamic breaks static type checking for a fixed set of 5 languages. One-line change.

**REQ-LA-502:** `detect_language()` SHALL use `LanguageRegistry.get_extension_map()` for extension lookups (REQ-LA-102), retaining only special-case logic for Dockerfile pattern matching and filename-based detection.

### 3.6 Add C# Language Profile (REQ-LA-600)

**REQ-LA-601:** Create `src/startd8/languages/csharp.py` implementing ALL 22 `LanguageProfile` protocol properties/methods:

| Property/Method | Value |
|----------------|-------|
| `language_id` | `"csharp"` |
| `display_name` | `"C#"` |
| `source_extensions` | `[".cs"]` |
| `build_file_patterns` | `["*.csproj", "*.sln", "Directory.Build.props"]` |
| `syntax_check_command` | `["dotnet", "build", "--no-restore", "-nologo"]` (per-project, not per-file) |
| `lint_command` | `None` (Roslyn analyzers are configured in .csproj, not standalone CLI) |
| `test_command` | `["dotnet", "test", "--no-build"]` |
| `framework_imports` | ASP.NET Core, EF Core, gRPC, Serilog (see REQ-LA-602) |
| `package_alias_map` | `{}` (NuGet names match namespace names) |
| `cleanup_patterns` | `["bin/", "obj/", ".vs/"]` |
| `blast_radius_extensions` | `[".cs"]` |
| `import_pattern_template` | `"using.*{module}"` |
| `system_prompt_role` | `"an expert C# / .NET engineer"` |
| `coding_standards` | PascalCase for public members, camelCase for private, nullable reference types, async/await, using declarations |
| `merge_strategy_preference` | `"simple"` |
| `repair_enabled` | `False` (no Python AST repair equivalent) |
| `docker_base_image` | `"mcr.microsoft.com/dotnet/sdk:8.0"` |
| `docker_runtime_image` | `"mcr.microsoft.com/dotnet/aspnet:8.0"` |
| `stub_patterns` | `[r"throw new NotImplementedException\(\)", r"throw new NotSupportedException\(\)", r"\{\s*\}"]` |
| `function_start_pattern` | Regex matching C# method declarations with access modifiers, async, return types |
| `supports_extension(ext)` | `ext.lower() == ".cs"` |
| `get_import_patterns(stem)` | `[f"using {stem}", f"using static {stem}"]` |
| `get_stdlib_prefixes()` | `("System", "Microsoft")` |
| `post_generation_cleanup()` | `[]` (no authoritative CLI formatter without project context) |
| `validate_syntax()` | Text-based: Python fingerprint check, balanced braces (shared utility), C# type declaration regex |
| `generate_dependency_file()` | `.csproj` XML generation (see REQ-LA-604) |

**New protocol methods** (added by REQ-LA-1001, LA-1101, LA-201):

| Method | Value |
|--------|-------|
| `derive_service_metadata()` | Derive `csharp_namespace` from file paths, `target_framework` from onboarding (see REQ-LA-603) |
| `build_project_context_section()` | C# namespace declaration, `using` directive rules, .NET structural conventions |
| `strip_dependency_version()` | NuGet format: split on `/` if present |
| `get_import_syntax_guidance()` | "Use `using` directives for all namespaces. Fully qualify ambiguous types." |

**REQ-LA-602:** `CSharpLanguageProfile.framework_imports` SHALL include detection patterns for:
- **ASP.NET Core** — `[WebApplication]`, `Microsoft.AspNetCore`, `app.MapGet`
- **Entity Framework Core** — `DbContext`, `Microsoft.EntityFrameworkCore`
- **gRPC (.NET)** — `Grpc.AspNetCore`, `Google.Protobuf`
- **Serilog** — `Serilog`, `Log.Information`

**REQ-LA-603:** `CSharpLanguageProfile.derive_service_metadata()` SHALL derive:
- `csharp_namespace` — from target file paths (directory structure maps to namespace) or explicit feature metadata
- `target_framework` — default `"net8.0"`, overridable via onboarding config

**REQ-LA-604:** `CSharpLanguageProfile.generate_dependency_file()` SHALL generate a `.csproj` file from service metadata:
```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Grpc.AspNetCore" Version="2.60.0" />
  </ItemGroup>
</Project>
```

**REQ-LA-605:** Register in `pyproject.toml`:
```toml
csharp = "startd8.languages.csharp:CSharpLanguageProfile"
```

### 3.7 Formalize Node.js Language Profile (REQ-LA-700)

Node.js already has a partial profile (`nodejs.py`). These requirements close gaps.

**REQ-LA-701:** `NodeLanguageProfile` SHALL implement `derive_service_metadata()` containing the logic currently in `derivation.py:401-435` (module_system and node_version inference).

**REQ-LA-702:** `NodeLanguageProfile` SHALL implement `code_fence_language` returning `"javascript"`.

**REQ-LA-703:** `NodeLanguageProfile` SHALL implement `filename_associations` returning `["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".npmrc"]`.

### 3.8 Plan Ingestion Language Support (REQ-LA-800)

**REQ-LA-801:** The PARSE phase prompt SHALL include C#-specific extraction fields:
```
"csharp_namespace": "optional C# root namespace e.g. MyApp.Services",
"target_framework": "optional .NET target framework e.g. net8.0"
```

**REQ-LA-802:** `_CONTEXT_THREADABLE_FIELDS` SHALL include `csharp_namespace` and `target_framework`.

**REQ-LA-803:** `_EXT_TO_LANGUAGE` in plan_ingestion_workflow.py SHALL be replaced per REQ-LA-102. The mapping SHALL normalize `"javascript"` and `"typescript"` to `"nodejs"` (the canonical language_id) to eliminate the naming inconsistency.

### 3.9 Language-Specific Prompt Section Builders (REQ-LA-1000) — NEW

**Goal:** Move language-specific spec prompt sections from pipeline code into language profiles. This is the **highest-value refactor** — eliminates ~200 lines of language branching from `spec_builder.py` and makes C# addition zero-touch in the pipeline.

**Context (gap in original requirements):** `spec_builder.py` contains three P0 section builder functions (`_build_go_module_section()` 68 lines, `_build_nodejs_module_section()` 60 lines, `_build_java_project_section()` 67 lines) plus a 4-way language dispatch in `_build_available_imports_section()` (75 lines). These were not captured in the original requirements but represent MORE language-specific code than `detect_java_frameworks()` (which REQ-LA-301 targets). Adding C# without addressing these means writing another 50-70 line function and updating `build_spec_prompt()` — exactly the shotgun surgery this refactor aims to eliminate.

**REQ-LA-1001:** `LanguageProfile` protocol SHALL add:
```python
def build_project_context_section(self, context: Dict[str, Any]) -> str:
    """Build language-specific project context for spec prompts.

    Returns markdown section with package/namespace declaration rules,
    import syntax, and structural conventions. Empty string if no
    special guidance needed.
    """
```

**REQ-LA-1002:** Each language profile SHALL implement `build_project_context_section()` absorbing the corresponding spec_builder function:
- `GoLanguageProfile` ← `_build_go_module_section()` (spec_builder.py:384–451)
- `JavaLanguageProfile` ← `_build_java_project_section()` (spec_builder.py:516–582)
- `NodeLanguageProfile` ← `_build_nodejs_module_section()` (spec_builder.py:454–513)
- `PythonLanguageProfile` → returns `""`
- `CSharpLanguageProfile` → new: namespace declaration, `using` directives, .NET conventions

**REQ-LA-1003:** `spec_builder.py:build_spec_prompt()` SHALL replace the three hard-coded section builder calls (lines 1136–1149) with a single language-agnostic dispatch:
```python
lang_profile = context.get("language_profile")
if lang_profile is not None:
    project_section = lang_profile.build_project_context_section(context)
    if project_section:
        prioritized.append((0, "project_context", project_section))
```

**REQ-LA-1004:** The three functions `_build_go_module_section()`, `_build_nodejs_module_section()`, `_build_java_project_section()` SHALL be deleted from `spec_builder.py`.

### 3.10 Dependency Formatting and Import Guidance (REQ-LA-1100) — NEW

**Goal:** Replace the 4-way language dispatch in `_build_available_imports_section()` with protocol methods.

**REQ-LA-1101:** `LanguageProfile` protocol SHALL add:
```python
def strip_dependency_version(self, dep: str) -> str:
    """Strip version pin from dependency string for prompt display."""

def get_import_syntax_guidance(self) -> str:
    """Return language-specific import rules for LLM prompts."""
```

**REQ-LA-1102:** `_build_available_imports_section()` in `spec_builder.py` (lines 296–370) SHALL replace its `is_go`/`is_java`/`is_nodejs`/else block with calls to `profile.strip_dependency_version()` and `profile.get_import_syntax_guidance()`.

### 3.11 Quick Wins (REQ-LA-1200) — NEW

**Pre-requisite fixes that can be committed independently before the refactor.**

**REQ-LA-1201:** `_EXT_TO_LANGUAGE` in `derivation.py` and `plan_ingestion_workflow.py` SHALL normalize `"javascript"` and `"typescript"` to `"nodejs"` immediately. This simplifies the `is_nodejs` check from a 4-condition or-chain to `primary_lang == "nodejs"`.

**REQ-LA-1202:** `spring_boot` SHALL be added to `_CONTEXT_THREADABLE_FIELDS` in `plan_ingestion_workflow.py` and to `SeedTask` in `models.py`. Currently extracted in PARSE but not threaded via QP-1, creating an inconsistency with all other language-specific fields.

**REQ-LA-1203 (removed):** ~~`infer_artifact_types_from_files()` SHALL use `LanguageRegistry.get_extension_map()`~~ The hardcoded extension tuple is deliberately MORE inclusive than the registry (includes `.rs`, `.rb`, `.ts` which have no registered profiles). Using the registry would silently drop these, making artifact classification LESS capable. The function classifies file TYPES, not languages. No change needed — `.cs` is already in the list.

### 3.12 Python Stub Guard for C# (REQ-LA-900)

**REQ-LA-901:** `_detect_python_stub_in_non_python()` in `integration_engine.py` SHALL recognize `.cs` files (already handles `.go`, `.java`, `.ts` by checking for Python `from __future__ import` fingerprint — no change needed if the existing check is extension-agnostic, which it is). Verify with a test.

---

## 4. Non-Requirements (Explicitly Out of Scope)

| Out of Scope | Rationale |
|-------------|-----------|
| YAML-based language configuration | 5 languages don't justify a configuration DSL. Python classes are the right abstraction for this scale. |
| Third-party language plugin API | No external consumers planned. Entry points work for internal use. |
| C# AST parsing from Python | No pure-Python C# parser exists. Use text-based patterns (same as Go). |
| C# MicroPrime element-level generation | Non-Python languages bypass MicroPrime. File-whole generation is sufficient. |
| `forward_manifest_validator.py` full refactor | Add `.cs` elif (minimal change). Full dispatch refactor is optional (REQ-LA-403). |
| Roslyn-based lint/analysis | Roslyn analyzers require the .NET SDK and project context. Too heavyweight for pipeline validation. |
| Additional languages beyond the 5 | Python, Go, Java, Node.js, C# are the final set. |
| TypeScript as separate profile | `.ts`/`.tsx` resolve to `"nodejs"` but NodeLanguageProfile can't validate TypeScript (`node --check` fails on .ts). TypeScript would need `tsc` tooling — out of scope. Known limitation: checkpoint skips .ts files. |
| Shared balanced-brace utility | Extracting `check_balanced_braces()` from `java.py` into `languages/_validation_utils.py` for reuse by C# is a quick win but not a formal requirement. Do it during implementation. |

---

## 5. Implementation Priority

Revised after two rounds of implementation planning. Collapsed from 7 phases to 4. See `LANGUAGE_AGNOSTIC_IMPLEMENTATION_PLAN.md` Part 8 for rationale.

| Phase | Requirements | What Changes | Lines Eliminated | Why This Order |
|-------|-------------|-------------|-----------------|----------------|
| **Phase 0** | REQ-LA-1201, LA-1202, LA-501 (downgraded) | Quick wins: naming fix, spring_boot threading, .cs in lang_detect + validator. Commit existing untracked tests (1,168 lines). | ~15 | Independent, zero risk, provides regression coverage for later phases |
| **Phase 1** | REQ-LA-101, LA-102, LA-103, LA-502, LA-803 | Extension map consolidation: `get_extension_map()`, consumer migration | ~60 (4 dict defs) | Foundation — single source of truth for extension mapping |
| **Phase 2** | REQ-LA-201 (revised), LA-202, LA-203, LA-1001–1004, LA-1101–1102, LA-301, LA-302, LA-601–605, LA-701–703 | **ALL protocol methods on ALL 5 profiles (including NEW csharp.py) + pipeline simplification** — derive_service_metadata, build_project_context_section, strip_dependency_version, get_import_syntax_guidance. Eliminate if/elif from derivation.py. Delete section builders + detect_java_frameworks from spec_builder.py. Unify framework detection. Extract balanced-brace utility. | ~380 eliminated, +400 in profiles | **The core commit** — architecture is right, all 5 languages work, pipeline is language-agnostic |
| **Phase 3** | REQ-LA-204, LA-205, LA-801, LA-802, LA-401, LA-402, LA-901 | C# plan ingestion wiring (PARSE prompt, SeedTask fields, ParsedFeature fields, threadable fields). Checkpoint cleanup. Full test suite. | +200 (wiring + tests) | **Completion** — C# works end-to-end through plan ingestion |

**All 4 phases are required. Critical path: 0 → 1 → 2 → 3**

Key insight: C# profile is created in Phase 2 ALONGSIDE the refactoring, not after it. This avoids an intermediate state where "refactoring is done but C# isn't wired in."

---

## 6. Verification

### 6.1 Extension Mapping Dedup

After P0–P1, `grep -rn '_EXT_TO_LANG\|_EXTENSION_TO_LANG\|_EXT_TO_LANGUAGE' src/` SHALL return only `LanguageRegistry.get_extension_map()` call sites, not standalone dict definitions.

### 6.2 No Language if/elif in derivation.py

After P2, `grep -n 'is_go\|is_java\|is_nodejs\|is_csharp' src/startd8/seeds/derivation.py` SHALL return zero matches.

### 6.3 No detect_java_frameworks

After P3, `grep -rn 'detect_java_frameworks' src/` SHALL return zero matches.

### 6.4 No Language Section Builders in spec_builder.py

After Phase 3, `grep -rn '_build_go_module\|_build_nodejs_module\|_build_java_project\|detect_java_frameworks' src/startd8/implementation_engine/` SHALL return zero matches.

### 6.5 Spec Prompt Output Parity

After Phase 3, generate spec prompts for one Go, one Java, and one Node.js task. The language-specific sections SHALL be byte-identical to the pre-refactor output (logic moved, not changed).

### 6.6 C# End-to-End

After Phase 4, the following SHALL work:
1. Plan ingestion of a C#/ASP.NET Core plan → seed with `csharp_namespace`, `target_framework` populated
2. `resolve_language(["src/Services/OrderService.cs"])` → `CSharpLanguageProfile`
3. `detect_language("src/Services/OrderService.cs")` → `"csharp"`
4. `CSharpLanguageProfile.generate_dependency_file()` → valid `.csproj` XML
5. `CSharpLanguageProfile.build_project_context_section(context)` → C# namespace/using/convention guidance
6. Framework detection from context containing "ASP.NET" → ASP.NET Core guidance in spec prompt

### 6.7 Existing Tests Pass

All existing tests in `tests/unit/languages/`, `tests/unit/validators/`, `tests/unit/seeds/`, `tests/unit/workflows/` SHALL continue to pass after each phase.

---

## 7. Files Modified Per Phase (Revised — 4 Phases)

### Phase 0 — Quick Wins (5 small independent commits)
- `src/startd8/seeds/derivation.py` — normalize `"javascript"`/`"typescript"` → `"nodejs"` in `_EXT_TO_LANGUAGE`, simplify `is_nodejs` check
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` — same normalization + add `"spring_boot"` to `_CONTEXT_THREADABLE_FIELDS`
- `src/startd8/seeds/models.py` — add `spring_boot: bool = False` to SeedTask
- `src/startd8/micro_prime/lang_detect.py` — add `"csharp"` to Language Literal + `".cs"` to extension map
- `src/startd8/forward_manifest_validator.py` — add `.cs` elif + minimal `_validate_csharp_file()`
- `tests/unit/` — commit 4 existing untracked test files (1,168 lines, 109/110 passing)

### Phase 1 — Extension Map Consolidation (1 commit)
- `src/startd8/languages/registry.py` — add `get_extension_map()` class method
- `src/startd8/languages/resolution.py` — delegate to `get_extension_map()`
- `src/startd8/seeds/derivation.py` — delete `_EXT_TO_LANGUAGE`, use registry
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` — delete `_EXT_TO_LANGUAGE`, use registry
- `src/startd8/micro_prime/lang_detect.py` — replace `_EXTENSION_TO_LANG` with registry + static text extensions

### Phase 2 — ALL Protocol Methods on ALL 5 Profiles + Pipeline Simplification (1-2 commits)
**Protocol additions:**
- `src/startd8/languages/protocol.py` — add `derive_service_metadata()`, `build_project_context_section()`, `strip_dependency_version()`, `get_import_syntax_guidance()`

**New C# profile:**
- `src/startd8/languages/csharp.py` — **new file** (all 22+4 protocol properties/methods)
- `src/startd8/languages/_validation_utils.py` — **new file** (extracted `check_balanced_braces()` shared utility)
- `pyproject.toml` — register `csharp` entry point

**Existing profile implementations:**
- `src/startd8/languages/python.py` — implement 4 new methods (metadata returns `{}`, prompt section returns `""`, dep stripping uses Python format, import guidance for Python)
- `src/startd8/languages/go.py` — implement 4 new methods (move from derivation.py:306-336 and spec_builder.py:384-451)
- `src/startd8/languages/java.py` — implement 4 new methods (move from derivation.py:338-400 and spec_builder.py:516-582), use shared brace validation
- `src/startd8/languages/nodejs.py` — implement 4 new methods (move from derivation.py:401-435 and spec_builder.py:454-513)

**Pipeline simplification:**
- `src/startd8/seeds/derivation.py` — replace 130-line if/elif with `profile.derive_service_metadata()`
- `src/startd8/implementation_engine/spec_builder.py` — delete 3 section builders + `detect_java_frameworks()`, simplify `_build_available_imports_section()`, replace 3 calls in `build_spec_prompt()` with 1
- `src/startd8/implementation_engine/framework_imports.py` — rename `FRAMEWORK_IMPORTS` → `_PYTHON_FRAMEWORK_IMPORTS`, add `"csharp"` to `_FENCE_MAP`, require `language_profile` in `detect_frameworks()`

### Phase 3 — C# Plan Ingestion Wiring + Tests + Cleanup (1 commit)
- `src/startd8/seeds/models.py` — add `csharp_namespace`, `target_framework` fields
- `src/startd8/workflows/builtin/plan_ingestion_models.py` — add same fields to `ParsedFeature`
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` — add C# fields to threadable set + PARSE prompt + extraction guidance
- `src/startd8/contractors/checkpoint.py` — remove Python defaults, log warning when no profile
- `tests/unit/languages/test_csharp_profile.py` — **new**: profile properties, validate_syntax(), generate_dependency_file(), derive_service_metadata(), build_project_context_section()
- `tests/unit/validators/test_csharp_disk_validators.py` — **new**: forward manifest validation for .cs files
- `tests/unit/workflows/test_plan_ingestion_csharp.py` — **new**: PARSE extraction of C# fields, context threading
