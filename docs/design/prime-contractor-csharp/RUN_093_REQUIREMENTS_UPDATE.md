# Run-093 Requirements Update — C# Prime Contractor

**Date**: 2026-03-21
**Run**: run-093-20260321T1726 (online-boutique cartservice, 15/15 PASS, 0.91 score, $1.88)
**Purpose**: Document specific requirements updates needed based on actual C# generation results.

---

## Status Updates (requirements that are now IMPLEMENTED)

These requirements were listed as NOT IMPLEMENTED in the original docs but are now working:

### CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md

| Requirement | Original Status | Current Status | Evidence |
|-------------|----------------|----------------|----------|
| REQ-CS-100 | NOT IMPLEMENTED | **IMPLEMENTED** | `.cs` in bypass sets, `CSHARP_MICROPRIME_ENABLED = True` |
| REQ-CS-101 | PARTIALLY IMPLEMENTED | **IMPLEMENTED** | `.csproj`, `.sln` in bypass sets |
| REQ-CS-102 | NOT IMPLEMENTED | **IMPLEMENTED** | `CSharpLanguageProfile.system_prompt_role` + `build_project_context_section()` |
| REQ-CS-103 | NOT IMPLEMENTED | **IMPLEMENTED** | `generate_dependency_file()` produces .csproj with `<Nullable>enable</Nullable>` |
| REQ-CS-104 | NOT IMPLEMENTED | **IMPLEMENTED** | `generate_solution_file()` produces .sln with GUIDs |
| REQ-CS-105 | NOT IMPLEMENTED | **IMPLEMENTED** | `_derive_namespace()` + namespace injection in prompt |
| REQ-CS-200 | NOT IMPLEMENTED | **IMPLEMENTED** | tree-sitter validation in `_validate_csharp_file()` |
| REQ-CS-201 | NOT IMPLEMENTED | **IMPLEMENTED** | `_validate_csproj_file()` checks XML, TargetFramework, SDK |
| REQ-CS-202 | NOT IMPLEMENTED | **IMPLEMENTED** | `_validate_sln_file()` checks header, project entries |
| REQ-CS-203 | NOT IMPLEMENTED | **IMPLEMENTED** | Python fingerprints in `validate_csharp_syntax()` |
| REQ-CS-300 | NOT IMPLEMENTED | **IMPLEMENTED** | `post_generation_cleanup()` calls `dotnet format` |
| REQ-CS-400 | NOT IMPLEMENTED | **IMPLEMENTED** | `framework_imports` with 10 frameworks |
| REQ-CS-401 | NOT IMPLEMENTED | **PARTIALLY** | gRPC base class and DI patterns in prompt context, but not all REQ-CS-401 sub-items |
| REQ-CS-500 | NOT IMPLEMENTED | **IMPLEMENTED** | C# disk validators in `forward_manifest_validator.py` |
| REQ-CS-502 | NOT IMPLEMENTED | **IMPLEMENTED** | `check_using_coverage()` exists (just wired into integration engine) |
| REQ-CS-600 | NOT IMPLEMENTED | **PARTIALLY** | Language hint detected; .csproj PackageReferences not yet extracted from seed |
| REQ-CS-601 | NOT IMPLEMENTED | **IMPLEMENTED** | `build_project_context_section()` includes Dockerfile patterns |
| REQ-CS-602 | NOT IMPLEMENTED | **IMPLEMENTED** | Proto file patterns in `build_project_context_section()` |

### KAIZEN_CSHARP_REQUIREMENTS.md

| Requirement | Original Status | Current Status | Evidence |
|-------------|----------------|----------------|----------|
| REQ-KZ-CS-100a | — | **IMPLEMENTED** | tree-sitter syntax validation |
| REQ-KZ-CS-100c | — | **IMPLEMENTED** | Python fingerprint detection |
| REQ-KZ-CS-100f | — | **IMPLEMENTED** | .csproj XML validation |
| REQ-KZ-CS-200b | — | **IMPLEMENTED** | `check_empty_catch_blocks()` in csharp_semantic_checks |
| REQ-KZ-CS-200d | — | **IMPLEMENTED** | `check_async_void()` in csharp_semantic_checks |
| REQ-KZ-CS-200h | — | **IMPLEMENTED** | Cross-language contamination detection |
| REQ-KZ-CS-400a | — | **IMPLEMENTED** | `repair_enabled = True`, fence_strip available |
| REQ-KZ-CS-400b | — | **IMPLEMENTED** | Fence strip repair step registered for csharp |
| REQ-KZ-CS-500b | — | **IMPLEMENTED** | Block-scoped namespace hint in disk validation |
| REQ-KZ-CS-700a | repair_enabled = False | **UPDATE**: `repair_enabled = True` | Changed in this session |

---

## New Requirements Needed (gaps found in run-093)

### NR-1: ILogger Enforcement in Prompt Context

**Problem**: 4 files in run-093 use `Console.WriteLine()` instead of `ILogger<T>`. The prompt says "prefer async/await for I/O-bound operations" but never mentions ILogger.

**Proposed requirement** (add to KAIZEN_CSHARP_REQUIREMENTS.md Section 6):

> **REQ-KZ-CS-500e: Logging Pattern Enforcement**
>
> When ASP.NET Core or gRPC frameworks are detected, inject this hint:
> - "Constructor-inject `ILogger<T>` — do NOT use `Console.WriteLine()`. Example: `private readonly ILogger<CartService> _logger;`"
>
> The `csharp_semantic_checks.check_console_writeline()` detector already catches violations. This hint prevents them at generation time.

**Status**: IMPLEMENTED in `build_project_context_section()` (this session).

### NR-2: PascalCase Namespace Enforcement

**Problem**: All 7 .cs files use lowercase namespaces (`cartservice.services`). The prompt said "PascalCase for types" but didn't explicitly say "PascalCase for namespaces".

**Proposed requirement** (add to CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md Section 3.1):

> **REQ-CS-106: PascalCase Namespace Convention**
>
> The C# project context section MUST explicitly state that namespaces use PascalCase matching directory structure. Example: `src/CartService/Services/` → `namespace CartService.Services;`.
>
> `_derive_namespace()` SHOULD output PascalCase namespace from path components.

**Status**: Prompt guidance IMPLEMENTED (this session). `_derive_namespace()` still returns lowercase — needs update.

### NR-3: File-Scoped Namespace Strength

**Problem**: 6/7 .cs files used block-scoped namespaces despite the prompt saying "Use file-scoped namespaces". The LLM followed the reference code's style over the instruction.

**Proposed update** (KAIZEN_CSHARP_REQUIREMENTS.md REQ-KZ-CS-500b):

> Update hint from "Use file-scoped namespaces" to **"File-scoped namespaces REQUIRED for net8.0+ targets. NEVER use block-scoped `namespace X { ... }` syntax."**
>
> Stronger phrasing ("REQUIRED", "NEVER") overrides pattern-matching from reference code.

**Status**: IMPLEMENTED in `build_project_context_section()` (this session).

### NR-4: Empty Catch Block Prevention

**Problem**: All 3 cart store `Ping()` methods have empty catch blocks. The csharp_semantic_checks detects these post-generation but the LLM wasn't told to avoid them.

**Proposed requirement** (add to KAIZEN_CSHARP_REQUIREMENTS.md Section 6):

> **REQ-KZ-CS-500f: Exception Handling Guidance**
>
> Always inject:
> - "NEVER use empty catch blocks. At minimum, log the exception with `_logger.LogError(ex, ...)`. Prefer catching specific exceptions."

**Status**: IMPLEMENTED in `build_project_context_section()` (this session).

### NR-5: Semantic Checks → Disk Quality Score Pipeline

**Problem**: csharp_semantic_checks detected issues (SQL injection, Console.WriteLine, empty catches) but they were logged as warnings only — NOT reflected in `DiskComplianceResult.semantic_issues` and therefore NOT penalized in `compute_disk_quality_score()`.

**Proposed update** (KAIZEN_CSHARP_REQUIREMENTS.md REQ-KZ-CS-300):

> C# semantic checks from `run_csharp_semantic_checks()` MUST be incorporated into the `DiskComplianceResult.semantic_issues` list during disk compliance validation. Each issue contributes to the existing severity-weighted penalty formula: `-0.3` per error, `-0.1` per warning.
>
> This ensures the quality score reflects actual code quality, not just syntax validity.

**Status**: IMPLEMENTED in `_validate_csharp_file()` (this session).

### NR-6: check_using_coverage() Integration

**Problem**: `csharp_splicer.check_using_coverage()` was fully implemented but never called. Missing using-to-PackageReference cross-checks were invisible.

**Proposed update** (CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md REQ-CS-502):

> **Status update**: IMPLEMENTED and WIRED. `check_using_coverage()` is now called from `integration_engine._run_semantic_checks()` after C# semantic checks. Issues logged as advisory warnings.

**Status**: IMPLEMENTED in `integration_engine.py` (this session).

### NR-7: Namespace-to-Filepath Validation

**Problem**: No validator checks whether the namespace declaration matches the directory structure. Run-093's lowercase namespaces went undetected.

**Proposed requirement** (add to KAIZEN_CSHARP_REQUIREMENTS.md Section 3):

> **REQ-KZ-CS-200i: check_namespace_filepath_alignment()**
>
> Compare the parsed namespace declaration (from csharp_parser) against the expected namespace from `_derive_namespace(file_path)`. Flag mismatches as `warning` severity.
>
> This catches both case mismatches (`cartservice.services` vs expected `CartService.Services`) and structural mismatches (wrong directory nesting).

**Status**: NOT IMPLEMENTED — `_derive_namespace()` exists but no validator compares its output to the parsed namespace.

### NR-8: _derive_namespace() PascalCase Output

**Problem**: `_derive_namespace()` returns lowercase namespace from directory names. C# convention requires PascalCase.

**Proposed update** (to `csharp.py`):

> `_derive_namespace()` SHOULD apply PascalCase conversion to each path component when deriving the namespace. Example: `src/cartservice/cartstore/` → `Cartservice.Cartstore` (at minimum capitalize first letter of each segment).

**Status**: NOT IMPLEMENTED.

### NR-9: Kaizen Hint Bootstrap

**Problem**: `kaizen-suggestions.json` was empty in run-093. No learned patterns from prior runs were injected.

**Proposed process** (not a code requirement):

> After each C# run, review postmortem semantic_issue_breakdown. If patterns repeat across 2+ runs, manually seed `kaizen-config.json` with hints matching the root cause → hint mapping in REQ-KZ-CS-500a.

### NR-10: Verdict Should Incorporate Disk Quality

**Problem**: PI-003 (.sln) scored `disk_quality_score: 0.0` but verdict was PASS because `requirement_score: 1.0` overrode it.

**Proposed requirement** (cross-cutting, not C#-specific):

> When `disk_quality_score < 0.3` for any file in a feature, the feature verdict SHOULD be FAIL regardless of `requirement_score`. A file that cannot parse or compile is not a successful generation even if the LLM claims requirements are met.

**Status**: NOT IMPLEMENTED — requires change to postmortem verdict logic.

---

## Summary: What to Update in Each Document

### CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md
1. Bulk status update: 15+ requirements now IMPLEMENTED (Section 1.5 gap table is stale)
2. Add REQ-CS-106 (PascalCase namespace convention)
3. Update REQ-CS-502 status to IMPLEMENTED
4. Update Section 1.5 "Current State" — profile, parser, splicer ALL exist now
5. Update Phase statuses (Phases 1-5 complete, Phase 6 MicroPrime enabled)

### KAIZEN_CSHARP_REQUIREMENTS.md
1. Update REQ-KZ-CS-700a: `repair_enabled = True`
2. Update REQ-KZ-CS-300: semantic checks now feed into disk quality score
3. Add REQ-KZ-CS-200i (namespace-filepath alignment)
4. Add REQ-KZ-CS-500e (ILogger enforcement)
5. Add REQ-KZ-CS-500f (exception handling guidance)
6. Update REQ-KZ-CS-400 repair status: Phase 1-2 ENABLED
7. Add run-093 findings as Section 11 (Validation Results)
