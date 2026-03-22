# Kaizen for Prime Contractor — C# Language Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-18
> **Parent:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md)
> **Language Profile:** `CSharpLanguageProfile` (IMPLEMENTED — `src/startd8/languages/csharp.py`)
> **Parser:** `CSharpParser` (IMPLEMENTED — `src/startd8/languages/csharp_parser.py`, tree-sitter + regex fallback)
> **Splicer:** `CSharpSplicer` (IMPLEMENTED — `src/startd8/languages/csharp_splicer.py`, tree-sitter byte-offset splicing)
> **Scope:** C#-specific quality measurement, validation, and feedback for the Kaizen system
> **Prerequisite:** .NET SDK 8.0+ for compilation-based validation; tree-sitter-c-sharp for in-process parsing

---

## Table of Contents

1. [Overview](#1-overview)
2. [Disk Validation](#2-disk-validation)
3. [Semantic Checks](#3-semantic-checks)
4. [Quality Scoring](#4-quality-scoring)
5. [Repair Pipeline](#5-repair-pipeline)
6. [Feedback Loop Hints](#6-feedback-loop-hints)
7. [Generation Profile](#7-generation-profile)
8. [LanguageProfile Implementation Spec](#8-languageprofile-implementation-spec)
9. [Traceability Matrix](#9-traceability-matrix)
10. [Verification Strategy](#10-verification-strategy)

---

## 1. Overview

### 1.1 Current State

Unlike Go, Java, and Node.js which were documented before implementation, C# has followed the reverse path: the `CSharpLanguageProfile` is already implemented and registered in `LanguageRegistry._register_builtins()`. The full implementation includes:

- **Profile** (`csharp.py`): All 15+ `LanguageProfile` protocol properties/methods implemented, including `framework_imports` (10 frameworks: ASP.NET Core, EF Core, gRPC, Serilog, Redis, xUnit, Spanner, SecretManager, Npgsql, gRPC Health), `derive_service_metadata()`, `build_project_context_section()`, `generate_dependency_file()` (.csproj generation), and `generate_solution_file()` (.sln generation).
- **Parser** (`csharp_parser.py`): tree-sitter-c-sharp CST parsing with regex fallback. Extracts classes, interfaces, structs, records, enums, methods, constructors, properties, using directives, and namespaces.
- **Splicer** (`csharp_splicer.py`): Tree-sitter byte-offset body splicing for replacing stub method bodies in skeleton files.
- **Registry**: C# is auto-discovered as a built-in language profile (language_id: `csharp`, extension: `.cs`).

This document serves as the **Kaizen quality requirements** for C# code generation: what to validate, how to score, what to repair, and what hints to feed back into the LLM prompt loop.

### 1.2 Key Characteristics

| Property | Value |
|----------|-------|
| Extensions | `.cs` |
| Build file patterns | `*.csproj`, `*.sln`, `Directory.Build.props` |
| Syntax check | `dotnet build` (project-scoped), tree-sitter (in-process, per-file) |
| Lint | `dotnet format` or Roslyn analyzers (CA rules) |
| Test | `dotnet test --no-build` |
| Dependency file | `.csproj` (PackageReference XML) |
| Docker builder | `mcr.microsoft.com/dotnet/sdk:10.0` |
| Docker runtime | `mcr.microsoft.com/dotnet/runtime-deps:10.0-chiseled` |
| merge_strategy_preference | `simple` |
| repair_enabled | `False` (currently — see REQ-KZ-CS-400 for enablement path) |
| MicroPrime | File-whole generation (no element-level splicing in MicroPrime; splicer is available for skeleton fill) |

### 1.3 Key Advantages

- **Roslyn compiler-as-a-service**: Rich analysis capabilities via the .NET SDK, including diagnostics, code fixes, and semantic model queries.
- **Strong typing**: Nullable reference types (C# 8+), pattern matching (C# 8+), records (C# 9+), file-scoped namespaces (C# 10+) provide more surface area for deterministic validation than dynamically-typed languages.
- **tree-sitter-c-sharp**: In-process CST parsing (~5ms) enables per-file syntax validation without the .NET SDK, critical for CI/CD and pipeline environments.

### 1.4 Key Challenges

- **.NET SDK dependency**: Full compilation requires `dotnet build` which needs a .NET SDK installation. Not available in all pipeline environments.
- **.csproj/solution complexity**: NuGet package management, MSBuild property inheritance via `Directory.Build.props`, solution-level configuration.
- **Namespace conventions**: C# expects namespace to match directory structure; generated code frequently violates this.
- **Framework diversity**: ASP.NET Core, Blazor, MAUI, WPF, gRPC, EF Core each have distinct project structures and conventions.

---

## 2. Disk Validation

### REQ-KZ-CS-100: C# Disk Compliance

C# files committed to disk by the Prime Contractor MUST be validated against the following checklist. Each check produces a boolean pass/fail and an optional diagnostic message. The checks are ordered by severity (compilation-blocking first, style last).

#### REQ-KZ-CS-100a: Syntax Validity

Validate C# syntax using the existing `CSharpLanguageProfile.validate_syntax()` method, which dispatches to tree-sitter-c-sharp (preferred) or text-based fallback (balanced braces + keyword presence).

**Acceptance criteria:**
- Files that fail `validate_syntax()` score 0.0 for the syntax component
- tree-sitter parse errors produce a structured diagnostic with the error region
- Text-based fallback catches: unbalanced braces, absence of any C# keyword, Python fingerprints (`def `, `import os`, `from __future__`, `print(`, `self.`)

#### REQ-KZ-CS-100b: Namespace Compliance

Validate that the `namespace` declaration matches the expected directory structure per C# conventions.

**Acceptance criteria:**
- File-scoped namespace declarations (`namespace Foo.Bar;`) are preferred over block-scoped (`namespace Foo.Bar { ... }`) for C# 10+ targets
- The namespace must match the directory path relative to the project root (e.g., `src/CartService/Services/CartStore.cs` expects `namespace CartService.Services;`)
- Namespace derivation uses `_derive_namespace()` from `csharp.py` (strips `src/`, `source/`, `lib/` prefixes)
- Missing namespace declaration in a file containing type declarations is an error

#### REQ-KZ-CS-100c: Cross-Language Contamination

Detect Python, Go, Java, or Node.js artifacts in C# files.

**Acceptance criteria:**
- Python fingerprints: `def `, `import os`, `from __future__`, `print(`, `self.`, `#!/usr/bin/env python`
- Go fingerprints: `package main`, `func main()`, `fmt.Println`, `import "fmt"`
- Java fingerprints: `public static void main(String`, `System.out.println`, `import java.`
- Node.js fingerprints: `require(`, `module.exports`, `const express`
- Any fingerprint match fails the contamination check with severity `error`

#### REQ-KZ-CS-100d: Using Statement Validity

Validate that `using` directives are well-formed.

**Acceptance criteria:**
- Every `using` statement ends with `;`
- `using static` and `global using` forms are recognized as valid
- `using` aliases (`using Alias = Namespace.Type;`) are recognized as valid
- Duplicate `using` directives produce a warning (not an error)
- Using directives referencing non-existent namespaces are caught when import map is available (deferred to semantic checks, REQ-KZ-CS-200)

#### REQ-KZ-CS-100e: Type Name / Filename Convention

Validate that the primary type declaration matches the filename.

**Acceptance criteria:**
- A file named `CartStore.cs` must contain a type declaration `class CartStore`, `struct CartStore`, `record CartStore`, or `interface ICartStore`
- Interface files conventionally use the `I` prefix (e.g., `ICartStore.cs` contains `interface ICartStore`)
- Multiple type declarations in a single file produce a warning (C# convention is one type per file)
- Partial classes are exempted from the one-type-per-file warning

#### REQ-KZ-CS-100f: .csproj Validity

Validate generated `.csproj` files for structural correctness.

**Acceptance criteria:**
- `<TargetFramework>` element is present and contains a valid TFM (`net6.0`, `net7.0`, `net8.0`, `net9.0`, `net10.0`)
- `<PackageReference>` elements have `Include` attribute
- `<Project Sdk="...">` attribute references a valid SDK (`Microsoft.NET.Sdk`, `Microsoft.NET.Sdk.Web`, `Microsoft.NET.Sdk.Worker`)
- Well-formed XML (closes all tags)
- `<Nullable>enable</Nullable>` is present (convention for modern C#)

### REQ-KZ-CS-101: C# Validation Tools

The following external tools are used for C# validation when available. All are optional; the pipeline degrades gracefully when tools are absent.

| Tool | Command | Purpose | Fallback |
|------|---------|---------|----------|
| tree-sitter-c-sharp | (in-process) | Per-file syntax validation (~5ms) | Text-based heuristics (balanced braces, keyword check) |
| `dotnet build` | `dotnet build --no-restore` | Full compilation (resolves types, references) | tree-sitter only |
| `dotnet format` | `dotnet format --verify-no-changes` | Formatting validation | Skip (no formatting score) |
| Roslyn analyzers | `dotnet build /p:TreatWarningsAsErrors=true` | Static analysis (CA rules) | Skip (no analyzer score) |
| `dotnet test` | `dotnet test --no-build` | Test execution | Skip (no test score) |

**Acceptance criteria:**
- Each tool is invoked only if `shutil.which("dotnet")` returns a path
- Tool absence does not fail the overall validation; it reduces the score components available
- Tool timeouts are set to 60s for `dotnet build`, 30s for `dotnet format`, 120s for `dotnet test`
- All tool invocations capture stderr for diagnostic reporting

---

## 3. Semantic Checks

### REQ-KZ-CS-200: C# Semantic Validators

Semantic checks go beyond syntax to detect code that compiles but has runtime defects or violates best practices. These checks populate the `semantic_issues` list in `DiskComplianceResult`, penalized at `-0.15` per issue by the existing scoring formula.

#### REQ-KZ-CS-200a: `check_missing_null_checks()`

Detect missing null guards in code that uses nullable reference types.

**Trigger:** Method parameters typed as nullable (`string?`, `T?`) are dereferenced without null check (`if (x != null)`, `x?.`, `x!`, `??` operator).

**Severity:** `warning` (C# nullable analysis would catch this at compile time with `<Nullable>enable</Nullable>`, but generated code may not enable it).

**Implementation:** Parse method bodies for parameter types containing `?` suffix, then check body for dereference without guard. Requires tree-sitter AST for accuracy; skip if regex-only fallback.

#### REQ-KZ-CS-200b: `check_empty_catch_blocks()`

Detect empty catch blocks that silently swallow exceptions.

**Trigger:** `catch (Exception) { }`, `catch (Exception ex) { }`, or bare `catch { }` with empty or whitespace-only body.

**Severity:** `warning` (may be intentional for fire-and-forget patterns, but usually a bug in generated code).

**Implementation:** Regex-based: `catch\s*\([^)]*\)\s*\{\s*\}` or tree-sitter `catch_clause` with empty `block` child.

#### REQ-KZ-CS-200c: `check_missing_dispose()`

Detect `IDisposable` implementations that are not wrapped in `using` statements.

**Trigger:** Local variable assignment from a constructor call whose type name matches known disposable types (`HttpClient`, `SqlConnection`, `StreamReader`, `StreamWriter`, `FileStream`, `DbContext`) without a `using` declaration or `using` block enclosing it.

**Severity:** `warning`

**Implementation:** Regex-based pattern matching for `new TypeName(` assignments not preceded by `using` on the same line or enclosed in a `using (...)` block.

#### REQ-KZ-CS-200d: `check_async_void()`

Detect `async void` methods, which are a well-known anti-pattern (exceptions cannot be caught, no Task to await).

**Trigger:** Method signature matches `async void MethodName(` where the method is not an event handler (event handlers conventionally take `(object sender, EventArgs e)` parameters).

**Severity:** `error` (almost always a bug in generated code)

**Implementation:** Regex: `\basync\s+void\s+\w+\s*\(` followed by parameter check to exclude event handler signatures.

#### REQ-KZ-CS-200e: `check_string_concatenation_in_loops()`

Detect string concatenation (`+=`) inside loop bodies, which should use `StringBuilder`.

**Trigger:** `someString += ` or `someString = someString +` inside a `for`, `foreach`, `while`, or `do` block.

**Severity:** `warning` (performance issue, not a correctness bug)

**Implementation:** Requires scope analysis. Regex-based heuristic: search for `+=` patterns preceded by a loop keyword within the same brace scope. Tree-sitter preferred for accuracy.

#### REQ-KZ-CS-200f: `check_missing_sealed()`

Detect classes that could benefit from being `sealed` for performance.

**Trigger:** Non-abstract class without `sealed` modifier that has no virtual/abstract methods and is not a base class referenced elsewhere in the file.

**Severity:** `info` (performance optimization, not a defect)

**Implementation:** Tree-sitter: extract class declarations, check modifier list for `sealed`/`abstract`, check body for `virtual`/`abstract` members.

#### REQ-KZ-CS-200g: `check_namespace_mismatch()`

Detect namespace declarations that don't match the expected directory structure.

**Trigger:** File path implies namespace `CartService.Services` but declaration says `namespace MyApp.Services;`.

**Severity:** `warning` (compilation may succeed but convention violation causes developer confusion)

**Implementation:** Compare `_derive_namespace(file_path)` output against the parsed namespace from `csharp_parser.parse_csharp()`.

#### REQ-KZ-CS-200h: `check_cross_language_contamination()`

Detect non-C# code patterns in `.cs` files.

**Trigger:** Python fingerprints from `_PYTHON_FINGERPRINTS` in `csharp.py`, plus Go/Java/Node.js fingerprints.

**Severity:** `error` (file is non-functional)

**Implementation:** Already partially implemented in `validate_csharp_syntax()`. This requirement extends the check to produce structured `semantic_issues` entries rather than just a boolean validation failure.

---

## 4. Quality Scoring

### REQ-KZ-CS-300: C# Quality Score Formula

The C# quality score follows the same composite structure as other languages, with C#-specific component weights.

```
composite = (compilation_check   x 0.30)
          + (using_validity      x 0.15)
          + (stub_penalty        x 0.20)
          + (nullable_safety     x 0.15)
          + (contamination_check x 0.10)
          + (convention_compliance x 0.10)
```

#### Component Definitions

| Component | Score Range | How Computed |
|-----------|-----------|--------------|
| `compilation_check` | 0.0 or 1.0 | `validate_syntax()` pass = 1.0, fail = 0.0 |
| `using_validity` | 0.0 – 1.0 | `1.0 - (invalid_usings / total_usings)`. No usings in a file with type declarations = 0.5 |
| `stub_penalty` | 0.0 – 1.0 | `1.0 - (stub_methods / total_methods)`. Stubs matched by `stub_patterns`: `throw new NotImplementedException()`, `throw new NotSupportedException()`, `// TODO` |
| `nullable_safety` | 0.0 – 1.0 | `1.0 - (nullable_violations / nullable_parameters)`. Files without nullable params score 1.0 |
| `contamination_check` | 0.0 or 1.0 | Any Python/Go/Java/Node.js fingerprint = 0.0, clean = 1.0 |
| `convention_compliance` | 0.0 – 1.0 | Average of: namespace match (0/1), type-filename match (0/1), file-scoped namespace (0/1 for C# 10+ targets) |

**Semantic penalty** (applied after composite, consistent with existing formula):
```
final = composite - (len(semantic_issues) x 0.15)
```

### REQ-KZ-CS-301: C# Root Causes

Root cause codes for C# failures in post-mortem reports. Each code maps to one or more validation checks.

| Root Cause Code | Description | Triggered By |
|----------------|-------------|--------------|
| `CROSS_LANGUAGE_CONTAMINATION` | Non-C# code in `.cs` file | REQ-KZ-CS-100c, REQ-KZ-CS-200h |
| `COMPILATION_ERROR` | Syntax invalid (tree-sitter or text-based) | REQ-KZ-CS-100a |
| `MISSING_NAMESPACE` | No namespace declaration in file with types | REQ-KZ-CS-100b |
| `NAMESPACE_MISMATCH` | Namespace doesn't match directory structure | REQ-KZ-CS-100b, REQ-KZ-CS-200g |
| `ASYNC_VOID_USAGE` | `async void` method (non-event-handler) | REQ-KZ-CS-200d |
| `EMPTY_CATCH_BLOCK` | Exception silently swallowed | REQ-KZ-CS-200b |
| `MISSING_DISPOSE_PATTERN` | IDisposable not in `using` block | REQ-KZ-CS-200c |
| `MISSING_PACKAGE_REFERENCE` | NuGet package used but not in .csproj | REQ-KZ-CS-100f (cross-ref with using directives) |
| `CSPROJ_ERROR` | Malformed .csproj XML or missing required elements | REQ-KZ-CS-100f |
| `NULLABLE_REFERENCE_WARNING` | Nullable parameter dereferenced without guard | REQ-KZ-CS-200a |
| `STRING_CONCAT_IN_LOOP` | String concatenation in loop body | REQ-KZ-CS-200e |
| `STUB_NOT_IMPLEMENTED` | `throw new NotImplementedException()` in production code | REQ-KZ-CS-300 (stub_penalty) |

---

## 5. Repair Pipeline

### REQ-KZ-CS-400: C# Repair Capabilities

The C# repair pipeline is currently disabled (`repair_enabled = False`). This section defines the repair capabilities to enable incrementally.

#### REQ-KZ-CS-400a: Phase 1 — Formatting Repair (Low Risk)

**Tool:** `dotnet format`

**Scope:** Whitespace, indentation, brace placement, using directive ordering.

**Prerequisites:**
- `dotnet` on PATH
- A `.csproj` file in the project (already checked in `post_generation_cleanup()`)

**Implementation:** Already implemented in `CSharpLanguageProfile.post_generation_cleanup()`. Enablement requires setting `repair_enabled = True` and wiring the cleanup into the repair pipeline orchestrator.

**Risk:** Minimal — formatting changes do not alter semantics.

#### REQ-KZ-CS-400b: Phase 2 — Fence Strip (Low Risk)

**Tool:** Existing `fence_strip` repair step

**Scope:** Remove markdown code fences (` ```csharp ` / ` ``` `) that LLMs sometimes include in generated code.

**Implementation:** Reuse existing `repair/steps/fence_strip.py`. No C#-specific logic needed; the step already handles arbitrary code fence languages.

**Risk:** Minimal — only removes non-code content.

#### REQ-KZ-CS-400c: Phase 3 — Using Directive Repair (Medium Risk)

**Tool:** Roslyn code fixes via `dotnet format --diagnostics CS0246`

**Scope:** Add missing `using` directives for unresolved type names. Roslyn's CS0246 diagnostic ("The type or namespace name 'X' could not be found") has associated code fixes that add the correct `using`.

**Prerequisites:**
- `dotnet` on PATH
- `.csproj` with correct PackageReferences (types must be resolvable)

**Risk:** Medium — may add incorrect usings if the type name is ambiguous across multiple namespaces.

#### REQ-KZ-CS-400d: Phase 4 — AST-Based Repair (Deferred)

Full Roslyn-based AST repair (analogous to Python's `ast.parse` + transform) is deferred. Reasons:
- Requires the Roslyn Workspaces API, which is .NET-only (no Python binding)
- Would need a .NET sidecar process or gRPC bridge
- Complexity disproportionate to current C# generation volume

**When to revisit:** When C# generation volume exceeds 100 files/run or when Roslyn LSP integration is available.

### REQ-KZ-CS-401: Repair Enablement Path

To enable C# repair:

1. Set `repair_enabled = True` in `CSharpLanguageProfile`
2. Register C# repair steps in `repair/routing.py` (fence_strip + formatting)
3. Add `csharp` to the `REPAIRABLE_LANGUAGES` set in `repair/config.py`
4. Verify `post_generation_cleanup()` is called by the repair orchestrator
5. Add integration tests with known-broken C# files

### REQ-KZ-CS-402: SQL Injection Semantic-to-Repair Bridge

**Priority:** P1
**Status:** Implemented (2026-03-22) — `SqlParameterizeStep` + routing + diagnostic bridge
**Source:** Run-095/099 AlloyDBCartStore (DQS 0.80, 16-17 semantic errors)

The `sql_injection_risk` semantic check result MUST trigger the `sql_parameterize` repair step deterministically, converting string-interpolated SQL to parameterized queries without LLM involvement.

**Root cause:** The Lead Contractor spec encodes reference implementation SQL injection patterns as "intentional" (R-SEC-2), overriding the P0 security guidance. The semantic check detects the vulnerability post-generation but cannot fix it because semantic issues are advisory-only — they reduce the DQS but don't trigger repair.

**Solution:** Bridge semantic check output to repair pipeline input:

1. After semantic checks run on a generated C# file and produce `sql_injection_risk` issues, the integration engine creates a `SemanticDiagnostic` with `category="security"` and `pattern="csharp_sql_injection"`
2. The repair router matches this diagnostic to the `("security", "csharp_sql_injection", ["sql_parameterize", "csharp_syntax_validate"], "HIGH", "csharp")` route
3. `SqlParameterizeStep` rewrites `$"SELECT ... '{var}'"` patterns to `"SELECT ... @var"` + `cmd.Parameters.AddWithValue("@var", var)` deterministically
4. `CSharpSyntaxValidateStep` verifies the rewritten code is syntactically valid

**Acceptance criteria:**
1. When `csharp_semantic_checks.run_csharp_semantic_checks()` returns issues with `check="sql_injection_risk"`, these are converted to `SemanticDiagnostic` instances and passed to the repair pipeline
2. The repair route `security/csharp_sql_injection` is selected for these diagnostics
3. `SqlParameterizeStep` transforms interpolated SQL queries in Npgsql code to parameterized form
4. The step handles multi-line concatenated SQL (`$"SELECT ..." + $"WHERE ..."`)
5. Table name variables (e.g., `{_tableName}`) are NOT parameterized (only lowercase-initial user-input variables)
6. After repair, re-running the semantic check on the same file produces zero `sql_injection_risk` issues
7. The repair is non-destructive: only `.cs` files with both `$"` and SQL keywords are processed

**Implementation files:**
- `src/startd8/repair/steps/sql_parameterize.py` — Deterministic rewrite engine (IMPLEMENTED)
- `src/startd8/repair/routing.py` — Route registration (IMPLEMENTED)
- `src/startd8/repair/steps/__init__.py` — Step export (IMPLEMENTED)
- `src/startd8/contractors/integration_engine.py` — Semantic-to-diagnostic bridge (NEEDED)
- `tests/unit/repair/test_sql_parameterize.py` — 8 tests (IMPLEMENTED)

**Diagnostic bridge (not yet wired):**

The missing piece is in `integration_engine.py` where semantic issues are collected but not fed back to the repair pipeline. The bridge should:

```python
# In _run_semantic_checks() or _attempt_repair():
sql_issues = [i for i in semantic_issues if i.check == "sql_injection_risk"]
if sql_issues:
    from startd8.repair.models import SemanticDiagnostic
    diagnostics.append(SemanticDiagnostic(
        category="security",
        pattern="csharp_sql_injection",
        severity="HIGH",
        message=f"{len(sql_issues)} SQL injection risk(s) detected",
    ))
    # Re-run repair pipeline with the new diagnostics
```

---

## 6. Feedback Loop Hints

### REQ-KZ-CS-500: C#-Specific Kaizen Hints

Kaizen hints are injected into subsequent run prompts based on post-mortem findings. Each hint maps a root cause to a concrete LLM instruction.

#### REQ-KZ-CS-500a: Language Feature Hints

| Root Cause | Hint Text |
|------------|-----------|
| `NULLABLE_REFERENCE_WARNING` | "Use nullable reference types (`string?`) and always guard with null checks or the `??` operator before dereferencing." |
| `ASYNC_VOID_USAGE` | "Never use `async void` except for event handlers. Always return `Task` or `Task<T>` from async methods." |
| `EMPTY_CATCH_BLOCK` | "Never use empty catch blocks. At minimum, log the exception. Prefer `catch (SpecificException ex) { _logger.LogError(ex, ...); }`." |
| `MISSING_DISPOSE_PATTERN` | "Wrap IDisposable objects in `using` declarations: `using var client = new HttpClient();`" |
| `STRING_CONCAT_IN_LOOP` | "Use `StringBuilder` for string building inside loops, not `+=` concatenation." |

#### REQ-KZ-CS-500b: Modern C# Idiom Hints

When the target framework is `net8.0` or later, inject these additional hints:

- "Use file-scoped namespaces (`namespace Foo.Bar;`) instead of block-scoped."
- "Use record types for DTOs and value objects: `public record OrderDto(string Id, decimal Amount);`"
- "Use primary constructors for DI: `public class CartService(ICartStore store, ILogger<CartService> logger)`"
- "Use collection expressions: `int[] numbers = [1, 2, 3];`"
- "Use pattern matching for type checks: `if (result is Success { Value: var value })`"

#### REQ-KZ-CS-500c: Dependency Injection Hints

When ASP.NET Core or gRPC frameworks are detected:

- "Register services in `Program.cs` using `builder.Services.AddScoped<IService, ServiceImpl>();`"
- "Use constructor injection, not `HttpContext.RequestServices.GetService<T>()`"
- "For gRPC services, override the generated base class methods and inject dependencies via constructor"

#### REQ-KZ-CS-500d: Testing Hints

When xUnit framework is detected:

- "Use `[Fact]` for non-parameterized tests, `[Theory]` with `[InlineData]` for parameterized tests"
- "Use `Moq` or `NSubstitute` for mocking dependencies: `var mock = new Mock<ICartStore>();`"
- "Follow Arrange-Act-Assert pattern with blank line separators"
- "Use `FluentAssertions` for readable assertions: `result.Should().BeEquivalentTo(expected);`"

---

## 7. Generation Profile

### REQ-KZ-CS-600: CSharpLanguageProfile Generation Characteristics

These requirements document the expected behavior of the existing `CSharpLanguageProfile` for Kaizen scoring and validation purposes.

#### REQ-KZ-CS-600a: .cs Skeleton Template

When generating C# skeletons for file-whole generation, the template MUST include:

```csharp
// File-scoped namespace (C# 10+)
namespace {namespace};

// Required using directives based on framework detection
using System;
{framework_usings}

/// <summary>
/// {class_description}
/// </summary>
public class {class_name}
{
    // Constructor with DI parameters
    public {class_name}({constructor_params})
    {
        {field_assignments}
    }

    // Method stubs
    {method_stubs}
}
```

**Acceptance criteria:**
- Skeleton uses file-scoped namespace syntax for `net8.0+` targets
- `using` directives are populated from `framework_imports` based on task context
- `throw new NotImplementedException()` is used for method stubs (matched by `stub_patterns`)
- XML doc comments (`/// <summary>`) are included for public types and methods

#### REQ-KZ-CS-600b: .csproj Generation

The existing `generate_dependency_file()` method handles .csproj generation. Requirements for Kaizen validation:

- Output must be valid XML parseable by `xml.etree.ElementTree`
- `<TargetFramework>` must be present
- `<Nullable>enable</Nullable>` must be present
- `<PackageReference>` elements must have `Include` attribute
- Dependencies in `Name/Version` or `Name Version` format are both accepted
- `sdk_type` metadata controls the `<Project Sdk="...">` attribute

#### REQ-KZ-CS-600c: .sln Generation

The existing `generate_solution_file()` method handles solution file generation. Requirements:

- Output follows Visual Studio Solution File Format Version 12.00
- Project type GUID is `{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}` (C# project)
- Debug and Release configurations are declared for each project
- Each project has a unique GUID

#### REQ-KZ-CS-600d: Dockerfile Generation Context

When `build_project_context_section()` detects Dockerfile targets, it injects .NET-specific Dockerfile patterns:

- Multi-stage build: `dotnet/sdk` builder, `dotnet/runtime-deps` runtime (chiseled/distroless)
- Restore-first pattern: `COPY *.csproj . && RUN dotnet restore` (layer caching)
- Self-contained publish with trimming: `dotnet publish -c release --self-contained true -p:PublishTrimmed=true`
- Non-root user: `USER 1000`
- Diagnostic suppression: `ENV DOTNET_EnableDiagnostics=0`
- gRPC health protocol instead of HEALTHCHECK instruction

#### REQ-KZ-CS-600e: Proto File Generation Context

When `build_project_context_section()` detects `.proto` targets, it injects gRPC/protobuf patterns:

- `syntax = "proto3";`
- `package` matching the C# namespace convention
- snake_case field names (C# codegen converts to PascalCase)
- Service-specific proto (not shared demo.proto)

---

## 8. LanguageProfile Implementation Spec

### REQ-KZ-CS-700: Protocol Compliance

The `CSharpLanguageProfile` implements all properties and methods defined in `LanguageProfile` protocol (`src/startd8/languages/protocol.py`). This section documents the concrete values for Kaizen auditing.

#### REQ-KZ-CS-700a: Identity Properties

| Property | Value | Notes |
|----------|-------|-------|
| `language_id` | `"csharp"` | Registry key |
| `display_name` | `"C#"` | Human-readable |
| `source_extensions` | `[".cs"]` | |
| `build_file_patterns` | `["*.csproj", "*.sln", "Directory.Build.props"]` | |
| `system_prompt_role` | `"an expert C# / .NET engineer"` | |
| `merge_strategy_preference` | `"simple"` | No AST merge for C# |
| `repair_enabled` | `False` | See REQ-KZ-CS-400 for enablement path |

#### REQ-KZ-CS-700b: Command Properties

| Property | Value | Notes |
|----------|-------|-------|
| `syntax_check_command` | `None` | `dotnet build` requires project context; per-file check via tree-sitter instead |
| `lint_command` | `None` | Roslyn analyzers configured in .csproj, not standalone |
| `test_command` | `["dotnet", "test", "--no-build"]` | |

#### REQ-KZ-CS-700c: Code Generation Properties

| Property | Value | Notes |
|----------|-------|-------|
| `docker_base_image` | `"mcr.microsoft.com/dotnet/sdk:10.0"` | Builder stage |
| `docker_runtime_image` | `"mcr.microsoft.com/dotnet/runtime-deps:10.0-chiseled"` | Runtime stage (distroless) |
| `cleanup_patterns` | `["bin/", "obj/", ".vs/"]` | .NET build artifacts |
| `blast_radius_extensions` | `[".cs"]` | |
| `import_pattern_template` | `"using.*{module}"` | |
| `coding_standards` | PascalCase public, camelCase private, nullable refs, async/await, using declarations | |

#### REQ-KZ-CS-700d: Stub Detection

| Property | Value |
|----------|-------|
| `stub_patterns` | `[r'throw\s+new\s+NotImplementedException\s*\(', r'throw\s+new\s+NotSupportedException\s*\(', r'^\s*//\s*TODO\b']` |
| `function_start_pattern` | Regex matching C# method declarations with optional modifiers, return type, and name group |

#### REQ-KZ-CS-700e: Framework Imports (10 Frameworks)

| Framework ID | Detect Keywords | NuGet Packages | Using Directives |
|-------------|----------------|----------------|-----------------|
| `aspnet_core` | asp.net, aspnetcore, webapplication, mapget, mappost | Microsoft.AspNetCore.App | Microsoft.AspNetCore.Builder, .Hosting, .Extensions.DependencyInjection |
| `ef_core` | dbcontext, entity framework, entityframeworkcore | Microsoft.EntityFrameworkCore, .SqlServer | Microsoft.EntityFrameworkCore |
| `grpc` | grpc, protobuf, proto | Grpc.AspNetCore, Google.Protobuf | Grpc.Core, Google.Protobuf |
| `serilog` | serilog, log.information, log.error | Serilog, Serilog.AspNetCore | Serilog |
| `redis` | redis, cache, distributed cache | Microsoft.Extensions.Caching.StackExchangeRedis | Microsoft.Extensions.Caching.Distributed |
| `xunit` | xunit, unit test, fact, theory | xunit, xunit.runner.visualstudio | Xunit |
| `spanner` | spanner, cloud spanner | Google.Cloud.Spanner.Data | Google.Cloud.Spanner.Data |
| `secretmanager` | secret manager, secrets | Google.Cloud.SecretManager.V1 | Google.Cloud.SecretManager.V1 |
| `npgsql` | npgsql, postgresql, alloydb | Npgsql | Npgsql |
| `grpc_health` | health check, healthcheck | Grpc.HealthCheck | Grpc.Health.V1 |

#### REQ-KZ-CS-700f: Standard Library Prefixes

`get_stdlib_prefixes()` returns: `("System", "Microsoft", "Windows")`

These prefixes are used to exclude BCL imports from dependency alignment checks (similar to Python's `sys.stdlib_module_names`).

#### REQ-KZ-CS-700g: Service Metadata Derivation

`derive_service_metadata()` extracts:

| Key | Source | Default |
|-----|--------|---------|
| `csharp_namespace` | Feature attribute or inferred from `target_files` via `_derive_namespace()` | (none) |
| `target_framework` | Feature attribute or onboarding config | `"net8.0"` |
| `sdk_type` | Inferred from target files (Startup.cs/Program.cs) and dependencies (grpc/aspnetcore) | `"Microsoft.NET.Sdk"` / `"Microsoft.NET.Sdk.Web"` |

---

## 9. Traceability Matrix

| Requirement | Validates | Root Cause Code | Kaizen Hint | Repair Step |
|-------------|-----------|----------------|-------------|-------------|
| REQ-KZ-CS-100a | Syntax validity | COMPILATION_ERROR | (none — compile error is self-explanatory) | fence_strip |
| REQ-KZ-CS-100b | Namespace compliance | MISSING_NAMESPACE, NAMESPACE_MISMATCH | File-scoped namespace hint | (none) |
| REQ-KZ-CS-100c | Contamination | CROSS_LANGUAGE_CONTAMINATION | (none — requires re-generation) | (none) |
| REQ-KZ-CS-100d | Using validity | (contributes to using_validity score) | Import syntax guidance | dotnet format |
| REQ-KZ-CS-100e | Type/filename match | (contributes to convention_compliance) | (none) | (none) |
| REQ-KZ-CS-100f | .csproj validity | CSPROJ_ERROR | (none) | (none) |
| REQ-KZ-CS-200a | Null safety | NULLABLE_REFERENCE_WARNING | REQ-KZ-CS-500a | (none) |
| REQ-KZ-CS-200b | Empty catch | EMPTY_CATCH_BLOCK | REQ-KZ-CS-500a | (none) |
| REQ-KZ-CS-200c | Dispose pattern | MISSING_DISPOSE_PATTERN | REQ-KZ-CS-500a | (none) |
| REQ-KZ-CS-200d | Async void | ASYNC_VOID_USAGE | REQ-KZ-CS-500a | (none) |
| REQ-KZ-CS-200e | String concat | STRING_CONCAT_IN_LOOP | REQ-KZ-CS-500a | (none) |
| REQ-KZ-CS-200f | Sealed classes | (info only) | (none) | (none) |
| REQ-KZ-CS-200g | Namespace mismatch | NAMESPACE_MISMATCH | REQ-KZ-CS-500b | (none) |
| REQ-KZ-CS-200h | Contamination | CROSS_LANGUAGE_CONTAMINATION | (none) | (none) |
| REQ-KZ-CS-300 | Quality score | STUB_NOT_IMPLEMENTED | (none) | (none) |
| REQ-KZ-CS-400a | Format repair | (none — repair step) | (none) | dotnet format |
| REQ-KZ-CS-400b | Fence strip | (none — repair step) | (none) | fence_strip |
| REQ-KZ-CS-400c | Using repair | MISSING_PACKAGE_REFERENCE | (none) | dotnet format --diagnostics |

---

## 10. Verification Strategy

### 10.1 Unit Tests

| Test | Target | Method |
|------|--------|--------|
| `test_csharp_syntax_validation_pass` | REQ-KZ-CS-100a | Valid C# file passes `validate_syntax()` |
| `test_csharp_syntax_validation_fail_unbalanced` | REQ-KZ-CS-100a | Unbalanced braces fail validation |
| `test_csharp_python_contamination_detected` | REQ-KZ-CS-100c | File with `from __future__` fails contamination check |
| `test_csharp_namespace_derivation` | REQ-KZ-CS-100b | `_derive_namespace()` produces correct namespace from path |
| `test_csharp_csproj_generation` | REQ-KZ-CS-100f | `generate_dependency_file()` produces valid .csproj XML |
| `test_csharp_sln_generation` | REQ-KZ-CS-600c | `generate_solution_file()` produces valid .sln format |
| `test_csharp_quality_score_perfect` | REQ-KZ-CS-300 | Clean C# file scores 1.0 |
| `test_csharp_quality_score_with_stubs` | REQ-KZ-CS-300 | File with NotImplementedException stubs has degraded score |
| `test_csharp_async_void_detection` | REQ-KZ-CS-200d | `async void` method flagged, event handler exempted |
| `test_csharp_empty_catch_detection` | REQ-KZ-CS-200b | Empty catch blocks produce semantic issue |
| `test_csharp_framework_imports` | REQ-KZ-CS-700e | Framework detection returns correct usings for ASP.NET/gRPC/EF Core |
| `test_csharp_service_metadata_derivation` | REQ-KZ-CS-700g | `derive_service_metadata()` infers namespace and target framework |

### 10.2 Integration Tests

| Test | Target | Method |
|------|--------|--------|
| `test_csharp_end_to_end_generation` | REQ-KZ-CS-600 | Generate a C# file via Prime Contractor, validate all quality components |
| `test_csharp_postmortem_scoring` | REQ-KZ-CS-300 | Run postmortem on a generated C# file, verify score breakdown |
| `test_csharp_kaizen_hint_injection` | REQ-KZ-CS-500 | Verify hints are injected based on root cause codes from previous run |
| `test_csharp_registry_discovery` | REQ-KZ-CS-700a | `LanguageRegistry.get("csharp")` returns `CSharpLanguageProfile` |
| `test_csharp_extension_mapping` | REQ-KZ-CS-700a | `LanguageRegistry.get_by_extension(".cs")` returns C# profile |

### 10.3 Golden File Tests

Maintain a corpus of known C# files with expected quality scores:

| File | Expected Score | Key Defects |
|------|---------------|-------------|
| `golden/csharp/clean_service.cs` | 1.0 | None |
| `golden/csharp/stub_heavy.cs` | 0.40–0.60 | 3/5 methods are `throw new NotImplementedException()` |
| `golden/csharp/python_contamination.cs` | 0.0 | `from __future__ import annotations` |
| `golden/csharp/async_void_and_empty_catch.cs` | 0.70 | `async void`, empty catch, missing dispose |
| `golden/csharp/valid_csproj.csproj` | 1.0 | None |
| `golden/csharp/broken_csproj.csproj` | 0.0 | Missing TargetFramework, malformed XML |

### 10.4 Smoke Test (Manual)

Run a C# microservice generation via Prime Contractor and verify:

1. All `.cs` files pass `validate_syntax()`
2. `.csproj` files contain correct PackageReferences
3. Namespace declarations match directory structure
4. No Python/Go/Java contamination
5. Post-mortem report includes C#-specific root causes
6. Kaizen hints reference C#-specific patterns
