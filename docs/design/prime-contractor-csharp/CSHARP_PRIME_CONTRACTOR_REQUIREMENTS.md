# C# Prime Contractor — Requirements & Design

**Date:** 2026-03-17
**Status:** Draft
**Derived From:** Go Prime Contractor Requirements (REQ-GO-*), Java Prime Contractor Requirements (REQ-JMP-*), Node.js Prime Contractor Requirements (REQ-NODE-*), Online Boutique C# requirements (`requirements-csharp.md`) and plan (`plan-csharp.md`)
**Strategy:** MicroPrime-first (like Java). `tree-sitter-c-sharp` is superior to Java's `javalang` on every dimension (byte-level positions, error recovery, C# 1–13.0 coverage, active maintenance). Combined with C#'s rigid class-per-file structure, element-level generation is the natural path. Prime Contractor file-whole generation remains the fallback via `CSHARP_MICROPRIME_ENABLED = False` (same pattern as Java).

---

## 1. Context & Strategic Rationale

### 1.1 Background

The Prime Contractor workflow generates code for multi-file features. Prior runs targeted Python (~50 runs), Go (run-066+), Java (via MicroPrime-first), and Node.js (via Prime Contractor-first). No C# Prime Contractor runs have been attempted yet.

The Online Boutique C# microservice (cartservice) is the validation target: 7 features, 14 output files, ~964 LOC across C#, XML (.csproj/.sln), JSON (appsettings.json), Protobuf, and Dockerfile. This is the most complex single-service target attempted: 3 cart store backends (Redis, Spanner, AlloyDB), ASP.NET Core DI, gRPC health checking, and xUnit integration tests.

### 1.2 Why MicroPrime-First for C#

C# follows the **Java strategy** (MicroPrime-first), not the Go/Node.js strategy (Prime Contractor-first). Three factors are decisive:

**1. tree-sitter-c-sharp is strictly better than Java's javalang — and Java already warranted MicroPrime-first.**
Java went MicroPrime-first *despite* `javalang`'s limitations (Java 8-ish coverage, no error recovery, line/column positions only, unmaintained since 2019). C# has `tree-sitter-c-sharp` which provides byte-level positions, error recovery, C# 1–13.0 coverage, and active maintenance (last commit 2026-03-14). If Java warranted MicroPrime-first with the weaker parser, C# certainly does with the stronger one. See Section 1.3 for the detailed comparison.

**2. C# has the same structural properties that made Java a natural MicroPrime fit.**
One-class-per-file, explicit access modifiers (`public`/`private`/`protected`/`internal`), namespace hierarchy, fully typed signatures. The `ForwardElementSpec.parent_class` ambiguity that plagues Python doesn't exist. Class decomposition is natural — exactly as it was for Java's `JavaClassDecomposeStrategy`.

**3. The splicer will be the most precise one yet.**
Go's splicer uses regex + brace counting. Java's uses text + brace counting. C#'s will use tree-sitter byte offsets — no line counting, no brace matching heuristics, just `body.start_byte` / `body.end_byte` for exact replacement ranges. This makes the splicer simpler and more reliable, lowering the implementation risk of MicroPrime-first.

**4. Cost reduction potential is real.**
The cartservice has 8 `.cs` files totaling ~700 LOC of C# source with boilerplate-heavy patterns (DI configuration, gRPC service stubs, 3 cart store implementations sharing the `ICartStore` interface). Element-level generation via Ollama/Haiku could reduce cloud model costs, especially for the repetitive store implementations.

**5. Error recovery enables validation of partial LLM output.**
tree-sitter sets `has_error` on the root node but continues parsing — returning useful structure even for code with minor syntax issues. `javalang` raises an exception on any parse error. This graceful degradation is valuable for validating and repairing LLM-generated code.

#### Why Not Prime Contractor-First?

The Prime Contractor-first arguments (file-whole quality is proven, faster time-to-first-run, moderate target size) are valid but not compelling enough to override the parser advantage:

- **File-whole generation quality** — True, but applies to *any* language. The question is whether we can do *better* with element-level generation. With tree-sitter, yes.
- **Faster time-to-first-run** — Phase 1 (profile + parser + bypass) unblocks the first run under *either* strategy. The file-whole fallback path (`CSHARP_MICROPRIME_ENABLED = False`) is available from Phase 1. MicroPrime-first doesn't delay the first run; it means the infrastructure for element-level generation is built in parallel.
- **.NET compilation requires full project context** — True for `dotnet build`, but irrelevant: tree-sitter provides per-file syntax validation without `dotnet` (see Section 1.3). This is the same situation as Java (`javalang` per-file vs `javac` project-level).

#### Build File Complexity

`.csproj` is XML with `<PackageReference>` entries — simpler than Gradle's Groovy DSL, comparable to `pom.xml`. Solution files (`.sln`) have a rigid format with GUIDs. Both are well-suited for template generation regardless of strategy.

### 1.3 tree-sitter-c-sharp: Parser Capabilities

A Python-native C# parser is available via the tree-sitter ecosystem:

```
pip install tree-sitter tree-sitter-c-sharp
```

Pre-built wheels for all major platforms (macOS x86_64/ARM64, Linux x86_64/ARM64, Windows). No C toolchain or compilation needed. Python >= 3.9 for `tree-sitter-c-sharp`, Python >= 3.10 for `tree-sitter` core.

#### Comparison to javalang (Java)

| Dimension | javalang (Java) | tree-sitter-c-sharp | Advantage |
|---|---|---|---|
| Install | `pip install javalang` | `pip install tree-sitter tree-sitter-c-sharp` | javalang (1 pkg) |
| Parse API | `javalang.parse.parse(source)` → AST | `parser.parse(source_bytes)` → CST | tree-sitter (preserves positions) |
| Tree type | Abstract (semantic) | Concrete (preserves all tokens) | tree-sitter (byte-level positions) |
| Error recovery | Raises exception on syntax error | Sets `has_error` flag, continues parsing | **tree-sitter** (critical for LLM output) |
| Byte positions | No (line/column only) | Yes (`start_byte`/`end_byte`) | **tree-sitter** (precise splicing) |
| Language coverage | Java 8-ish (incomplete 17+) | C# 1–13.0 (tracks Roslyn) | **tree-sitter** (comprehensive) |
| Performance | ~50ms for medium file | ~5ms for 25KB file | tree-sitter (10x) |
| Maintenance | Last PyPI update 2019 | Last commit 2026-03-14 | **tree-sitter** (actively maintained) |
| Pre-built wheels | Pure Python | Pre-built C wheels | Comparable |

#### MicroPrime Capability Coverage

| Capability | tree-sitter Support | How |
|---|---|---|
| **MP-1: Syntax Validation** | Direct | `tree.root_node.has_error` — single boolean, per-file, no project context needed |
| **MP-2: Element Location** | Direct | Walk `named_children`, match `node.type == "method_declaration"` + `child_by_field_name('name').text` |
| **MP-3: Signature Rendering** | Direct | `child_by_field_name('returns')`, `child_by_field_name('parameters')`, modifier children |
| **MP-6: Stub Detection** | Direct | Check body text for `NotImplementedException`, empty `{ }` |
| **MP-7: Body Splicing** | Direct | `body.start_byte`/`body.end_byte` gives exact byte range for replacement |
| **MP-8: Structural Verification** | Direct | Walk tree collecting all `class_declaration`, `method_declaration`, `interface_declaration` by name |
| **MP-10: Class Decomposition** | Direct | Iterate `class_body.named_children`, extract each method's signature |

#### Key C# Node Types

| C# Construct | tree-sitter Node Type | Name Field | Body Field |
|---|---|---|---|
| Class | `class_declaration` | `name` | `body` (declaration_list) |
| Interface | `interface_declaration` | `name` | `body` |
| Struct | `struct_declaration` | `name` | `body` |
| Record | `record_declaration` | `name` | `body` |
| Method | `method_declaration` | `name` | `body` (block) |
| Constructor | `constructor_declaration` | `name` | `body` |
| Property | `property_declaration` | `name` | `accessors` |
| Field | `field_declaration` | (variable_declaration child) | — |
| Namespace | `namespace_declaration` | `name` | `body` |
| File-scoped NS | `file_scoped_namespace_declaration` | `name` | (children are siblings) |
| Using | `using_directive` | — | — |
| Attribute | `attribute_list` | — | — |

**Gotcha:** `type_parameter_list` (generics) is NOT accessible via `child_by_field_name('type_parameters')` on `class_declaration`. It is a positional child — find it by iterating `children` and checking `type == 'type_parameter_list'`.

#### Repository Health

- **Repo:** https://github.com/tree-sitter/tree-sitter-c-sharp
- **Stars:** 289, **Forks:** 90, **License:** MIT
- **Last updated:** 2026-03-14
- **Based on:** Roslyn grammar (Microsoft's official C# compiler)
- **Maintained by:** tree-sitter organization

#### Python Version Note

The SDK states "Python 3.9+" but the venv uses 3.14. `tree-sitter-c-sharp` supports Python >= 3.9 (stable ABI), but `tree-sitter` core requires Python >= 3.10. If Python 3.9 support is a hard requirement, tree-sitter would need to be an optional dependency (same pattern as `javalang` — try import, fall back to regex).

### 1.4 Comparison: Pipeline Complexity by Language

| Pipeline Capability | Python | Go | Java | Node.js | **C#** |
|---|---|---|---|---|---|
| Generation path | MicroPrime (element) | File-whole (cloud) | MicroPrime (element) | File-whole (cloud) | **MicroPrime (element)** |
| AST from Python | `ast.parse()` (in-process) | Regex (`go_parser.py`) | `javalang` (in-process) | None (subprocess only) | **tree-sitter (in-process CST)** |
| Syntax validation | `ast.parse()` | `gofmt -e` | `javalang.parse.parse()` | `node --check` | **tree-sitter `has_error` (per-file, ~5ms)** |
| DFA skeletons | Full (assembler) | N/A | Full (assembler) | N/A | **Possible (tree-sitter-based)** |
| Splicer | AST-based | Text/brace-based | Text/brace-based | N/A | **tree-sitter byte-offset splicing** |
| Templates | 12+ (dunder, dataclass) | None | 8+ (Java boilerplate) | None | **Possible (properties, DI, async/await)** |
| Decomposition | Class + Function | N/A | Class strategy | N/A | **Class strategy (tree-sitter)** |
| Import fixing | N/A (DFA renders) | `goimports` (excellent) | None (DFA must get it right) | None | **None** |
| Post-gen cleanup | Ruff lint | `goimports -w` | `google-java-format` | None (prettier possible) | **`dotnet format` (best-effort)** |
| Dependency file | `requirements.txt` | `go.mod` | `build.gradle` | `package.json` | **`.csproj` (XML)** |

### 1.5 C# Language Profile — Current State

**File:** Does not exist. Must be created as `src/startd8/languages/csharp.py`.
**Supporting libraries (to create):**
- `csharp_parser.py` — tree-sitter-based structure extraction (classes, methods, properties, using directives)
- `csharp_splicer.py` — body splicing using tree-sitter byte offsets (if MicroPrime path chosen)

| Capability | Status | Notes |
|-----------|--------|-------|
| Language ID & display name | **NOT IMPLEMENTED** | `"csharp"` / `"C#"` |
| Source extensions | **NOT IMPLEMENTED** | `[".cs"]` |
| Build file patterns | **NOT IMPLEMENTED** | `[".csproj", ".sln", "Directory.Build.props", "global.json"]` |
| Syntax check | **NOT IMPLEMENTED** | tree-sitter `has_error` (per-file, in-process) — no `dotnet` required |
| Lint | **NOT IMPLEMENTED** | `dotnet format` (style only, optional) |
| Test | **NOT IMPLEMENTED** | `dotnet test` |
| Framework imports | **NOT IMPLEMENTED** | gRPC (Grpc.AspNetCore), ASP.NET Core, EF Core, xUnit |
| Stdlib prefixes | **NOT IMPLEMENTED** | `System.*`, `Microsoft.*` (extensive) |
| Post-generation cleanup | **NOT IMPLEMENTED** | `dotnet format` (best-effort, style only) |
| Syntax validation | **NOT IMPLEMENTED** | tree-sitter in-process parse (per-file, fast, no project context needed) |
| `.csproj` generation | **NOT IMPLEMENTED** | `generate_dependency_file()` with NuGet PackageReference entries |
| Docker images | **NOT IMPLEMENTED** | Builder: `mcr.microsoft.com/dotnet/sdk:10.0`, Runtime: `mcr.microsoft.com/dotnet/runtime-deps:10.0-chiseled` |
| Coding standards | **NOT IMPLEMENTED** | C# conventions: PascalCase public, camelCase private, `async`/`await`, `IDisposable` |
| Merge strategy | **NOT IMPLEMENTED** | `"simple"` (whole-file replacement); tree-sitter-based merge when `CSHARP_MICROPRIME_ENABLED` |
| Repair | **NOT IMPLEMENTED** | tree-sitter enables AST-aware repair (unlike Go/Node.js where no parser exists) |
| Stub patterns | **NOT IMPLEMENTED** | `throw new NotImplementedException()`, `// TODO`, empty body `{ }` |
| Function start pattern | **NOT IMPLEMENTED** | tree-sitter `method_declaration` nodes (more reliable than regex) |
| System prompt role | **NOT IMPLEMENTED** | `"an expert C# / .NET engineer"` |
| Import patterns | **NOT IMPLEMENTED** | `using Namespace;`, `using static Namespace.Class;` |

### 1.6 Gap Summary

| Area | What Exists | What's Missing |
|------|------------|----------------|
| **Generation path** | `.cs` NOT in `_NON_PYTHON_EXTENSIONS` | **Critical:** Must add `.cs`, `.csproj`, `.sln` to bypass sets |
| **Language profile** | Nothing | Full `CSharpLanguageProfile` class |
| **Parser** | `tree-sitter` + `tree-sitter-c-sharp` available on PyPI | `csharp_parser.py` wrapping tree-sitter for structure extraction |
| **Splicer** | Nothing | `csharp_splicer.py` using tree-sitter byte offsets (if MicroPrime path) |
| **Entry point** | Nothing | `pyproject.toml` entry point registration |
| **Syntax validation** | Nothing | tree-sitter in-process `has_error` check (per-file, no project needed) |
| **Disk validation** | `_validate_json_file()` (for appsettings.json), `_validate_dockerfile()` | No `.cs`-specific validator, no `.csproj`-specific validator, no `.sln` validator |
| **System prompts** | Nothing for C# | Profile properties + wiring into `spec_builder.py`/`drafter.py` |
| **Framework detection** | Nothing for C# | gRPC, ASP.NET Core, EF Core, xUnit entries |
| **Cross-language guard** | `_detect_language_mismatch()` — Python fingerprints only | No C# fingerprints detected in non-CS files |
| **Postmortem** | Generic — non-Python files may default to 1.0 | No C#-specific scoring |
| **Dependency file template** | Nothing | `.csproj` template generation |

---

## 2. Target Project Characteristics

### 2.1 C# Microservice (Online Boutique — cartservice)

```
project-root/
├── src/
│   └── cartservice/
│       ├── cartservice.sln
│       ├── src/
│       │   ├── cartservice.csproj
│       │   ├── Program.cs
│       │   ├── Startup.cs
│       │   ├── appsettings.json
│       │   ├── Dockerfile
│       │   ├── protos/
│       │   │   └── Cart.proto
│       │   ├── services/
│       │   │   ├── CartService.cs
│       │   │   └── HealthCheckService.cs
│       │   └── cartstore/
│       │       ├── ICartStore.cs
│       │       ├── RedisCartStore.cs
│       │       ├── SpannerCartStore.cs
│       │       └── AlloyDBCartStore.cs
│       └── tests/
│           ├── cartservice.tests.csproj
│           └── CartServiceTests.cs
```

### 2.2 File Type Distribution

| Type | Count | Pipeline Path |
|------|-------|--------------|
| `.cs` | 8 | File-whole LLM generation |
| `.csproj` | 2 | File-whole LLM or template generation |
| `.sln` | 1 | Template generation (rigid format with GUIDs) |
| `.json` (appsettings) | 1 | File-whole LLM generation |
| `.proto` | 1 | File-whole LLM generation |
| `Dockerfile` | 1 | File-whole LLM generation |
| **Total** | **14** | |

### 2.3 C# Patterns

The cartservice uses idiomatic ASP.NET Core patterns:

```csharp
// Dependency injection
services.AddSingleton<ICartStore, RedisCartStore>();

// gRPC service registration
endpoints.MapGrpcService<CartService>();

// Async pattern (direct return vs await)
public override Task<Cart> GetCart(GetCartRequest request, ServerCallContext context)
    => _cartStore.GetCartAsync(request.UserId);  // no await — returns Task directly

// Configuration access
var redisAddress = Configuration["REDIS_ADDR"];

// Using directives
using System;
using Grpc.Core;
using cartservice.cartstore;
```

### 2.4 C# Language Characteristics Relevant to Pipeline

| Characteristic | Impact on Pipeline |
|---|---|
| **One public class per file** | Same as Java — file routing is unambiguous |
| **Namespace hierarchy** | `cartservice.cartstore` → `cartstore/` directory. Less strict than Java (namespace doesn't have to match directory) but convention is to match |
| **`using` directives** | Similar to Java `import` — always at top of file, fully qualified |
| **Access modifiers** | `public`, `private`, `protected`, `internal` — similar to Java |
| **Properties** | `public IConfiguration Configuration { get; }` — no equivalent in Go/Node.js/Python |
| **`async`/`await`** | Pervasive. `Task<T>` return types, `async override` methods |
| **Compiler catches errors** | Strong — duplicates, missing using, type errors are compile-time errors |
| **NuGet packages** | `<PackageReference Include="Name" Version="X.Y.Z" />` in `.csproj` |
| **Protobuf integration** | `<Protobuf Include="protos\Cart.proto" GrpcServices="Both" />` in `.csproj` + `Grpc.Tools` package |

---

## 3. Requirements

### 3.1 Generation Path (REQ-CS-100 series)

#### REQ-CS-100: C# MicroPrime Bypass with Feature Flag

C# source files (`.cs`) MUST be added to `_NON_PYTHON_EXTENSIONS` in both `micro_prime/engine.py` and `implementation_engine/drafter.py`. A feature flag `CSHARP_MICROPRIME_ENABLED` (default `False`) controls whether `.cs` files flow through MicroPrime or bypass to file-whole cloud generation.

**When False (default):** `.cs` is in the bypass set, all C# files use file-whole cloud generation (safe fallback for first runs).

**When True:** `_is_non_python_file()` returns `False` for `.cs` files, routing them through MicroPrime classify → generate → splice → verify pipeline (same pattern as `JAVA_MICROPRIME_ENABLED`).

**Implementation:** Add `.cs` to `_NON_PYTHON_EXTENSIONS`. Add `.csproj`, `.sln` to bypass sets. Add `CSHARP_MICROPRIME_ENABLED = False` flag with conditional check in `_is_non_python_file()`.

**Status:** NOT IMPLEMENTED — **Critical gap.** `.cs` is missing from both extension sets. Without this, C# files will be treated as Python-compatible and routed through Python AST parsing, which will fail.

#### REQ-CS-101: Non-Source File Generation

Non-source files in C# projects (`.csproj`, `.sln`, `appsettings.json`, `Dockerfile`, `.proto`) MUST either:
1. Use file-whole LLM generation (for complex content), or
2. Use language-appropriate templates (for trivial content like `.csproj` skeletons)

They MUST NOT receive Python skeleton stubs.

**Implementation:** Add `.csproj`, `.sln` to `_NON_PYTHON_EXTENSIONS` in `implementation_engine/drafter.py`. The `.json`, `.xml`, `.proto` extensions are already covered.

**Status:** PARTIALLY IMPLEMENTED — `.json`, `.proto`, `.xml` are already in the bypass set. `.csproj` and `.sln` are NOT (`.csproj` is not `.xml` suffix; `.sln` has no extension match).

#### REQ-CS-102: C# System Prompt Injection

The spec and draft prompts MUST include C#-specific context when the resolved language is C#:
- `system_prompt_role`: "an expert C# / .NET engineer"
- `coding_standards`: Idiomatic C# guidance (PascalCase, async/await, DI patterns, LINQ, IDisposable)
- Framework preamble based on detected frameworks (gRPC, ASP.NET Core, EF Core)

**Acceptance criteria:**
- `spec_builder.py` checks `language_profile.system_prompt_role` and injects it when language is C#
- `drafter.py` includes `coding_standards` in the draft system prompt
- Framework imports from `framework_imports` are listed as available when relevant

**Status:** NOT IMPLEMENTED — `CSharpLanguageProfile` does not exist yet.

#### REQ-CS-103: .csproj Template Generation

When a `.csproj` file is classified as TRIVIAL, generate it from seed metadata using `CSharpLanguageProfile.generate_dependency_file()`.

**Inputs extracted from seed:**
- `project_name`: From seed task metadata or directory name
- `target_framework`: From seed metadata or default `"net10.0"`
- `sdk_type`: `"Microsoft.NET.Sdk.Web"` for web projects, `"Microsoft.NET.Sdk"` for libraries/tests
- `dependencies`: From seed task `dependencies` field (NuGet package name + version)
- `protobuf_items`: Optional list of `.proto` file paths for gRPC projects

**Output format:**
```xml
<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Grpc.AspNetCore" Version="2.76.0" />
    <!-- ... -->
  </ItemGroup>
  <ItemGroup>
    <Protobuf Include="protos\Cart.proto" GrpcServices="Both" />
  </ItemGroup>
</Project>
```

**Status:** NOT IMPLEMENTED

#### REQ-CS-104: Solution File (.sln) Template Generation

When a `.sln` file is classified as TRIVIAL, generate it from seed metadata. Solution files have a rigid format:
- Visual Studio Solution Format Version 12.00
- Project entries with GUIDs, relative paths, and project type GUID (`{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}` for C#)
- Global sections for solution/project configuration platforms

**Rationale:** `.sln` files have extremely rigid formatting with GUID references. Template generation is more reliable than LLM generation for this format.

**Status:** NOT IMPLEMENTED

#### REQ-CS-105: Namespace-Aware Prompt Context

When generating C# code, the spec prompt SHOULD include namespace context derived from file path:
- File at `src/cartservice/src/cartstore/RedisCartStore.cs` → namespace `cartservice.cartstore`
- File at `src/cartservice/src/services/CartService.cs` → namespace `cartservice.services`

**Rationale:** C# namespace conventions follow directory structure. Including the expected namespace in the prompt reduces hallucination of incorrect namespaces.

**Status:** NOT IMPLEMENTED

---

### 3.2 Validation & Scoring (REQ-CS-200 series)

#### REQ-CS-200: C# File Validation

Generated `.cs` files MUST be validated using tree-sitter-c-sharp for per-file syntax checking, with optional `dotnet build` for full project-level validation.

**Validation strategy (tiered):**

| Tier | Condition | Method | `ast_valid` | `contract_compliance` |
|------|-----------|--------|-------------|----------------------|
| 1 | `tree-sitter-c-sharp` available (expected) | `parser.parse()` → `root_node.has_error` | True if no errors | 1.0 |
| 2 | `tree-sitter` not available | Text-based heuristics only | Best-effort | 0.8 max |
| 3 | `dotnet` available + `.csproj` present | `dotnet build` (advisory, full type checking) | True if compiles | 1.0 |

**tree-sitter validation (primary — always run when available):**
- `parser.parse(source_bytes)` — in-process, ~5ms per file, no project context needed
- `tree.root_node.has_error` — single boolean for syntax validity
- Graceful degradation: partial parses return useful structure even with errors
- No `.csproj`, NuGet restore, or `dotnet` CLI required

**Text-based heuristic checks (fallback — also run as supplementary checks):**
- Non-empty content
- Contains at least one C# keyword (`using`, `namespace`, `class`, `interface`, `public`, `private`, `void`, `async`, `Task`)
- No Python fingerprints (`from __future__`, `def `, `import os`)
- Contains a `namespace` declaration or `using` directive
- Balanced braces `{` vs `}`

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Empty file | False | 0.0 |
| Python content detected | False | 0.0 |
| No C# keywords detected | False | 0.3 |
| tree-sitter not available, text checks pass | True | 0.8 |
| tree-sitter parse has errors | False | 0.0 |
| tree-sitter parse clean | True | 1.0 |
| `dotnet build` fails (advisory) | True (syntax ok) | 0.8 (type errors) |
| `dotnet build` succeeds (advisory) | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-CS-201: .csproj Disk Validation

`validate_disk_compliance()` MUST validate `.csproj` files for:
- Valid XML (well-formed)
- Contains `<Project>` root element with `Sdk` attribute
- Contains `<TargetFramework>` element
- No Python content (cross-language guard)
- `<PackageReference>` elements have both `Include` and `Version` attributes

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Invalid XML | False | 0.0 |
| Missing `<Project>` root | False | 0.0 |
| Missing `<TargetFramework>` | True | 0.3 |
| Python content detected | False | 0.0 |
| Valid with all required elements | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-CS-202: .sln Disk Validation

`validate_disk_compliance()` MUST validate `.sln` files for:
- Contains `Microsoft Visual Studio Solution File` header
- Contains at least one `Project(` entry
- Contains `EndProject` for each `Project(`
- No Python content

**Scoring:**

| Condition | `ast_valid` | `contract_compliance` |
|-----------|-------------|----------------------|
| Missing solution header | False | 0.0 |
| No project entries | True | 0.3 |
| Unbalanced Project/EndProject | True | 0.5 |
| Python content detected | False | 0.0 |
| Valid | True | 1.0 |

**Status:** NOT IMPLEMENTED

#### REQ-CS-203: Cross-Language Content Detection for C#

Extend `_detect_language_mismatch()` to detect C# fingerprints in non-CS files.

**C# fingerprints to detect in non-CS files:**
- `using System;` or `using Microsoft.` (C# using directive)
- `namespace ` followed by `{` on same or next line (C# namespace declaration)
- `public class ` or `public interface ` (C# type declaration)
- `[assembly:` (C# assembly attribute)

**Python fingerprints already detected in CS files:**
- `from __future__` (existing)
- `def ` at line start (existing)
- `import os` / `import sys` (existing)

**Status:** NOT IMPLEMENTED — Python fingerprint detection exists. C# fingerprints in non-CS files not yet added.

#### REQ-CS-204: Python-Stub Integration Guard for C#

The integration engine MUST block Python stubs from being written to `.cs` target files.

**Status:** NOT YET IMPLEMENTED — `_detect_python_stub_in_non_python()` in `integration_engine.py` covers non-Python extensions, but `.cs` is not currently in the non-Python extension set (see REQ-CS-100). Once REQ-CS-100 is implemented, this will work automatically.

---

### 3.3 Post-Generation Cleanup (REQ-CS-300 series)

#### REQ-CS-300: dotnet format Execution (Best-Effort)

After generating `.cs` files, the pipeline MAY run `dotnet format` to normalize formatting if the `dotnet` CLI is available and a `.csproj` exists.

**Rationale:** Unlike Go's `goimports` (which fixes imports AND formatting), `dotnet format` only handles style formatting (indentation, spacing, newlines). It does NOT add missing `using` directives or remove unused ones. Its value is cosmetic only.

**Limitations:**
- Requires `.csproj` to be present (project-level tool)
- Does not fix imports
- Does not add missing namespace declarations
- Requires NuGet restore to have completed

**Priority:** P3 (low). File-whole LLM generation already produces well-formatted C# code.

**Fallback:** If `dotnet` is not on PATH or no `.csproj` exists, skip with no warning.

**Status:** NOT IMPLEMENTED

#### REQ-CS-301: No Import Fixer Available

Unlike Go (`goimports`), C# has no CLI tool that reliably adds missing `using` directives. `dotnet format` handles style but not missing usings. IDE-level tools (Visual Studio, Rider, OmniSharp) can add usings but are not CLI-callable in a pipeline context.

**Mitigation strategies:**
1. Seed enrichment includes dependency list and expected `using` directives in spec prompt
2. Framework detection injects canonical `using` patterns
3. Namespace-aware prompt context (REQ-CS-105) reduces namespace hallucination
4. Postmortem flags files missing expected `using` directives (heuristic)

**Status:** ACKNOWLEDGED (no implementation needed — this documents a known limitation)

---

### 3.4 Framework Detection (REQ-CS-400 series)

#### REQ-CS-400: C# Framework Import Entries

`CSharpLanguageProfile.framework_imports` MUST include entries for common C#/.NET frameworks:

| Framework Key | Detection Keywords | Dependencies | Using Pattern |
|---|---|---|---|
| `grpc` | "grpc", "proto", "protobuf", "gRPC" | `Grpc.AspNetCore`, `Grpc.HealthCheck` | `using Grpc.Core;`, `using Grpc.Health.V1;` |
| `aspnet` | "asp.net", "web api", "controller", "startup" | `Microsoft.NET.Sdk.Web` (SDK) | `using Microsoft.AspNetCore.Builder;`, `using Microsoft.Extensions.DependencyInjection;`, etc. |
| `efcore` | "entity framework", "ef core", "dbcontext" | `Microsoft.EntityFrameworkCore` | `using Microsoft.EntityFrameworkCore;` |
| `redis` | "redis", "cache", "distributed cache" | `Microsoft.Extensions.Caching.StackExchangeRedis` | `using Microsoft.Extensions.Caching.Distributed;` |
| `xunit` | "xunit", "unit test", "fact", "theory" | `xunit`, `xunit.runner.visualstudio` | `using Xunit;` |
| `spanner` | "spanner", "cloud spanner" | `Google.Cloud.Spanner.Data` | `using Google.Cloud.Spanner.Data;` |
| `secretmanager` | "secret manager", "secrets" | `Google.Cloud.SecretManager.V1` | `using Google.Cloud.SecretManager.V1;` |
| `npgsql` | "npgsql", "postgresql", "alloydb" | `Npgsql` | `using Npgsql;` |

**Status:** NOT IMPLEMENTED

#### REQ-CS-401: Framework Preamble for C# gRPC Services

When a C# task targets a gRPC service (detected via `Grpc.AspNetCore` dependency or description keywords), the spec prompt MUST include:

- Service base class pattern: `public class ServiceName : Proto.ServiceName.ServiceNameBase`
- DI registration: `endpoints.MapGrpcService<ServiceName>()`
- Health check pattern: `HealthBase` + `HealthCheckResponse.Types.ServingStatus`
- `ServerCallContext` parameter on all RPC methods
- `Task<T>` return types with `async override` pattern

**Status:** NOT IMPLEMENTED

#### REQ-CS-402: ASP.NET Core Host Pattern Guidance

When a C# task targets an ASP.NET Core application, the spec prompt SHOULD include:

- Host builder pattern: `Host.CreateDefaultBuilder(args).ConfigureWebHostDefaults(...)` or minimal API pattern
- Startup class pattern: `ConfigureServices(IServiceCollection)` + `Configure(IApplicationBuilder, IWebHostEnvironment)`
- DI lifetime guidance: `AddSingleton` vs `AddScoped` vs `AddTransient`
- Configuration access: `Configuration["KEY"]` pattern

**Status:** NOT IMPLEMENTED

---

### 3.5 Postmortem & Kaizen (REQ-CS-500 series)

#### REQ-CS-500: Non-Python Postmortem Accuracy for C#

The postmortem MUST NOT score C# files as 1.0 by default. Each file type must have at least a basic validator.

**File types requiring validators:**

| Type | Validator | Status |
|------|-----------|--------|
| `.cs` | `_validate_cs_file()` | **NOT IMPLEMENTED** (REQ-CS-200) |
| `.csproj` | `_validate_csproj_file()` | **NOT IMPLEMENTED** (REQ-CS-201) |
| `.sln` | `_validate_sln_file()` | **NOT IMPLEMENTED** (REQ-CS-202) |
| `.json` (appsettings) | `_validate_json_file()` | Pre-existing |
| `.proto` | Text-based (non-empty, contains `syntax`, `service`, `message`) | **NOT IMPLEMENTED** |
| `Dockerfile` | `_validate_dockerfile()` | Pre-existing |

#### REQ-CS-501: Language Mismatch Postmortem Pattern

Same as REQ-GO-501 and REQ-NODE-501. When 2+ files in a run have `language_mismatch` errors, the postmortem MUST emit a cross-feature pattern.

**Pattern:** `language_mismatch_in_generation`
**Severity:** `high` (3+ files) or `medium` (2 files)
**Suggestion:** "Non-Python files received Python stubs. Check template-match routing for non-Python trivial tasks."

**Status:** NOT IMPLEMENTED (REQ-MLT-401)

#### REQ-CS-502: .csproj Dependency Cross-Check

When both `.cs` source files and a `.csproj` exist in the same project directory, the postmortem SHOULD cross-check:
- Every `using` directive in `.cs` files that references a NuGet package has a corresponding `<PackageReference>` in `.csproj`
- Standard library namespaces (`System.*`, `Microsoft.AspNetCore.*`, `Microsoft.Extensions.*`) are not flagged (they come from the SDK or framework references)

**Priority:** P3 (future enhancement).

**Status:** NOT IMPLEMENTED

---

### 3.6 Seed Enrichment (REQ-CS-600 series)

#### REQ-CS-600: C# Project Context in Seeds

When plan ingestion detects a C# project (presence of `.csproj` in plan or sibling `*.cs` files), the seed enrichment SHOULD:

1. Set `language_hint: "csharp"` on seed tasks targeting `.cs` files
2. Include `.csproj` `<PackageReference>` entries in the task's `dependencies` field
3. Extract target framework (`<TargetFramework>`) for prompt context
4. Detect framework usage from `.csproj` dependencies for prompt preamble

**Status:** NOT IMPLEMENTED

#### REQ-CS-601: Dockerfile Context for C# Services

When a seed task targets a `Dockerfile` in a C# service directory, the spec prompt MUST include:
- The .NET SDK version (from `.csproj` `<TargetFramework>` or `global.json`)
- The project file name (for `dotnet restore` and `dotnet publish` commands)
- Whether the project is self-contained (`PublishSingleFile`, `PublishTrimmed`)
- The expected `EXPOSE` port

**Rationale:** C# Dockerfiles follow a predictable multi-stage pattern (SDK builder with `dotnet restore` + `dotnet publish`, runtime-deps with `COPY --from=builder`). The plan already specifies exact Dockerfile content with pinned image SHAs.

**Status:** NOT IMPLEMENTED

#### REQ-CS-602: Proto File Context for C# gRPC Services

When a seed task targets a `.proto` file in a C# service, the spec prompt MUST include:
- The `package` name (from `.csproj` or plan metadata)
- The gRPC service contract (RPC method names, request/response types)
- Clarification that this is a service-specific proto (not a shared `demo.proto`)

**Status:** NOT IMPLEMENTED

---

## 4. Implementation Phases

The phasing below follows the MicroPrime-first strategy (same as Java). Phases 1–5 build the foundation (profile, parser, validators, prompts, templates). Phase 6 builds the MicroPrime-specific infrastructure (splicer, decomposer, DFA skeletons). The file-whole fallback path (`CSHARP_MICROPRIME_ENABLED = False`) is available from Phase 1 for early validation runs.

### Phase 1: Extension Bypass + Language Profile + Parser (REQ-CS-100, 101, 102)

**Goal:** C# files route correctly through the pipeline. tree-sitter parser available for validation and structure extraction.

**Deliverables:**
- Add `.cs`, `.csproj`, `.sln` to `_NON_PYTHON_EXTENSIONS` in `micro_prime/engine.py` and `implementation_engine/drafter.py`
- Create `CSharpLanguageProfile` in `src/startd8/languages/csharp.py`
- Create `csharp_parser.py` wrapping tree-sitter-c-sharp for structure extraction
- Add `tree-sitter` and `tree-sitter-c-sharp` as optional dependencies in `pyproject.toml`
- Register `csharp` entry point in `pyproject.toml`
- `pip install -e .` to activate entry point

**Tests:** ~20
- `.cs` recognized as non-Python in bypass check
- `.csproj` and `.sln` recognized as non-Python
- `CSharpLanguageProfile` conforms to `LanguageProfile` protocol
- `resolve_language()` returns C# profile for `.cs` files
- Entry point discovery via `LanguageRegistry.discover()`
- tree-sitter parse of valid C# — `has_error` is False
- tree-sitter parse of invalid C# — `has_error` is True
- Structure extraction: class, method, property, interface detection
- Graceful fallback when tree-sitter not installed

**Value:** Unblocks first C# run (either strategy). Provides per-file syntax validation without requiring `dotnet` CLI. Parser available for both disk validation and future MicroPrime use.

### Phase 2: Validation & Disk Compliance (REQ-CS-200, 201, 202, 203, 500)

**Goal:** Accurate postmortem scoring for C# files using tree-sitter-based validation.

**Deliverables:**
- `_validate_cs_file()` in `forward_manifest_validator.py` — tree-sitter `has_error` with text-based fallback
- `_validate_csproj_file()` in `forward_manifest_validator.py` — XML structure checks
- `_validate_sln_file()` in `forward_manifest_validator.py` — header and project entry checks
- Dispatch wiring in `_validate_non_python_file()` for `.cs`, `.csproj`, `.sln`
- C# fingerprint detection in `_detect_language_mismatch()` (for non-CS files)

**Tests:** ~25
- `.cs` validation: valid C# (tree-sitter clean), invalid (tree-sitter error), empty, Python content
- `.csproj` validation: valid XML, missing Project root, missing TargetFramework, invalid XML, Python content
- `.sln` validation: valid, missing header, no projects, unbalanced Project/EndProject
- Cross-language detection: C# fingerprints in HTML/YAML/Dockerfile

**Value:** Postmortem accuracy — `.cs`, `.csproj`, and `.sln` files scored correctly instead of defaulting to 1.0 (unvalidated) or being unscored. tree-sitter validation is per-file and fast (~5ms), unlike `dotnet build`.

### Phase 3: Framework Detection & System Prompts (REQ-CS-102, 400, 401, 402)

**Goal:** LLM generates better C# code via language-aware prompts.

**Deliverables:**
- Verify `spec_builder.py` language_profile integration works for `language_id == "csharp"`
- `framework_imports` on `CSharpLanguageProfile` (gRPC, ASP.NET Core, Redis, xUnit, Spanner, etc.)
- Framework preamble includes usage patterns (DI registration, gRPC service base class)
- Coding standards injected into draft system prompt
- Namespace-aware prompt context (REQ-CS-105)

**Tests:** ~12
- Framework detection with `Grpc.AspNetCore`, `Microsoft.Extensions.Caching.StackExchangeRedis` dependencies
- System prompt contains "C# / .NET engineer" when language is csharp
- Import preamble uses `csharp` code fence (not `python`)
- Namespace derivation from file path

**Value:** Higher quality generated C# code. Framework-specific patterns reduce LLM hallucination for ASP.NET Core DI, gRPC service registration, and async patterns.

### Phase 4: Seed Enrichment & Template Wiring (REQ-CS-103, 104, 105, 600, 601, 602)

**Goal:** Pipeline-level intelligence for C# projects.

**Deliverables:**
- `.csproj` template generation wired into template-match path
- `.sln` template generation (rigid format)
- C# project detection in plan ingestion
- Dockerfile context enrichment for .NET services
- Proto file context for gRPC services

**Tests:** ~18
- `generate_dependency_file()` output matches expected `.csproj` structure
- `.sln` template with correct format, GUIDs, project entries
- Seed enrichment sets `language_hint: "csharp"` for `.cs` target files
- Dockerfile context includes .NET SDK version and publish flags

**Value:** Pipeline understands C# project structure. Template generation for `.csproj` and `.sln` avoids unnecessary LLM calls and ensures correct rigid formats.

### Phase 5: Post-Generation & Postmortem Enhancement (REQ-CS-300, 501, 502)

**Goal:** Quality feedback loop for C# runs.

**Deliverables:**
- `dotnet format` best-effort post-generation formatting
- Language mismatch postmortem pattern (shared with Go/Node.js — REQ-MLT-401)
- `.csproj` ↔ `using` dependency cross-check (advisory)

**Tests:** ~8
- dotnet format when available / graceful skip when not
- Postmortem pattern detection for language mismatch
- Dependency cross-check: missing PackageReference, stdlib using (no flag), all matched

**Value:** Quality scoring improvements. Language mismatch pattern prevents repeat failures.

### Phase 6: MicroPrime Integration

**Goal:** Element-level C# code generation via Ollama/Haiku using tree-sitter-based infrastructure. This is the primary generation path — file-whole cloud generation is the fallback.

**Deliverables:**
- `csharp_splicer.py` — body splicing using tree-sitter byte offsets (similar to `go_splicer.py` but more precise)
- C# keyword reserves (~80 keywords + contextual keywords)
- C# literal coercion (`true`/`false`/`null`, `List.of()` → `new List<T>()`)
- C# signature rendering (`public async Task<ReturnType> MethodName(Type param)`)
- Class decomposition strategy using tree-sitter (extract methods from class body)
- C# system prompts for element-level generation
- Structural verification using tree-sitter (check expected elements exist in output)
- DFA skeleton assembly for C# (if warranted — depends on class structure complexity)

**Tests:** ~30
- Splicer: stub replacement, indentation preservation, import injection
- Keyword collision detection
- Literal coercion: C# primitives, null, collections
- Signature rendering: async methods, generic methods, properties, constructors
- Class decomposition: extract methods, render stub class, reassemble
- Structural verification: all expected elements present after generation

**Value:** Cost reduction via local model generation for SIMPLE/MODERATE C# tasks. The tree-sitter parser provides more precise element location and splicing than Go's regex-based approach or Java's javalang, due to byte-level positions and error recovery.

---

## 5. Implementation Status Summary

### Implemented (Pre-existing)

| REQ | Description |
|-----|-------------|
| REQ-CS-204 | Python-stub integration guard (works once REQ-CS-100 adds `.cs` to bypass set) |
| REQ-CS-301 | No import fixer (acknowledged limitation) |

### Not Yet Implemented (by Phase)

| Phase | REQs | Effort | Dependencies |
|-------|------|--------|--------------|
| 1 | CS-100, 101, 102 | **S** | None — **must be done first** |
| 2 | CS-200, 201, 202, 203, 500 | S | Phase 1 |
| 3 | CS-102, 400, 401, 402 | S | Phase 1 (can parallelize with Phase 2) |
| 4 | CS-103, 104, 105, 600, 601, 602 | M | Phase 3 (framework detection) |
| 5 | CS-300, 501, 502 | S | Phase 2 (validators) |
| 6 | MicroPrime integration (splicer, decomposer, DFA, templates) | M-L | Phase 1 (parser) |

---

## 6. Test Coverage

### Current

| Test File | Tests | Covers |
|-----------|-------|--------|
| (none specific to C#) | 0 | — |
| `tests/unit/micro_prime/test_non_python_bypass.py` | ~24 | Bypass mechanism (`.cs` NOT yet in bypass set) |
| **Total** | **0** | |

### Needed (by Phase)

| Phase | Test File (Proposed) | Tests (Est.) |
|-------|----------------------|--------------|
| 1 | `test_csharp_bypass.py` | ~8 |
| 1 | `test_csharp_profile.py` | ~7 |
| 1 | `test_csharp_parser.py` | ~12 |
| 2 | `test_csharp_validators.py` | ~15 |
| 2 | `test_csharp_cross_language.py` | ~10 |
| 3 | `test_csharp_framework_detection.py` | ~6 |
| 3 | `test_csharp_system_prompts.py` | ~6 |
| 4 | `test_csharp_csproj_template.py` | ~8 |
| 4 | `test_csharp_sln_template.py` | ~5 |
| 4 | `test_csharp_seed_enrichment.py` | ~5 |
| 5 | `test_csharp_postmortem.py` | ~5 |
| 5 | `test_csharp_dep_crosscheck.py` | ~3 |
| 6 | `test_csharp_splicer.py` | ~10 |
| 6 | `test_csharp_decomposition.py` | ~8 |
| 6 | `test_csharp_microprime_gen.py` | ~12 |
| **Total** | | **~120** |

---

## 7. Known Limitations

1. **tree-sitter is a CST parser, not a semantic analyzer** — `tree-sitter-c-sharp` validates syntax and extracts structure, but cannot perform type checking, overload resolution, or namespace resolution. These require the full Roslyn compiler (`dotnet build`). tree-sitter tells you "this file parses" but not "this file compiles."

2. **No import fixer** — Unlike Go (`goimports`), C# has no CLI tool that adds missing `using` directives. `dotnet format` handles style but not missing usings. IDE tools (Rider, VS) can do this but aren't pipeline-callable.

3. **`dotnet` CLI availability for full validation** — Full type checking and compilation require the .NET SDK. If not installed, validation is limited to tree-sitter syntax checking (which is still superior to text heuristics). The target project uses .NET 10, which may not be commonly installed.

4. **Solution file rigidity** — `.sln` files have an extremely rigid format with specific GUIDs, project type GUIDs, and configuration platform entries. Template generation is preferred over LLM generation to avoid format errors.

5. **Protobuf code generation** — C# gRPC projects use `Grpc.Tools` NuGet package for compile-time proto → C# code generation. The pipeline generates the `.proto` file and the `.csproj` with `<Protobuf>` items, but the actual C# code generation from proto happens at `dotnet build` time, not in our pipeline.

6. **Namespace vs directory mismatch** — Unlike Java (where `com.example.service` MUST map to `com/example/service/`), C# namespace declarations are a convention, not enforced by the compiler. The pipeline assumes convention-following but cannot validate namespace-to-path mapping.

7. **tree-sitter `type_parameter_list` gotcha** — Generics type parameters on class/struct declarations are NOT accessible via `child_by_field_name('type_parameters')`. They are positional children that must be found by iterating `children` and checking `type == 'type_parameter_list'`.

8. **Python 3.9 compatibility** — The `tree-sitter` core package requires Python >= 3.10. If Python 3.9 support is a hard requirement, tree-sitter must be an optional dependency with regex fallback (same pattern as `javalang` for Java).

---

## 8. Comparison: C# vs Go vs Java vs Node.js Pipeline Strategy

| Aspect | Go | Java | Node.js | **C#** |
|--------|-----|------|---------|--------|
| **Strategy** | Prime-first | MicroPrime-first | Prime-first | **MicroPrime-first** |
| **Rationale** | No Python AST; strong CLI tools | Rigid structure; `javalang` AST | No Python AST; dynamic language | **tree-sitter CST (superior to javalang) + rigid structure** |
| **Python-native parser** | Regex (`go_parser.py`) | `javalang` (AST, in-process) | None | **tree-sitter-c-sharp (CST, in-process, superior to javalang)** |
| **Per-file syntax validation** | `gofmt -e` (subprocess) | `javalang.parse.parse()` (in-process) | `node --check` (subprocess) | **tree-sitter `has_error` (in-process, ~5ms, error recovery)** |
| **Import fixing** | `goimports` (excellent) | None (DFA renders) | None | **None** |
| **Templates** | None | 8+ (boilerplate-heavy) | None (low boilerplate) | **Possible: .csproj, .sln, DI patterns** |
| **Decomposition potential** | Low (no classes) | High (class-centric) | Low (irregular syntax) | **High (class-centric, tree-sitter-based)** |
| **Body splicing** | Text/brace (`go_splicer.py`) | Text/brace | N/A | **tree-sitter byte offsets (most precise)** |
| **Framework detection** | gRPC, HTTP, Logrus | Spring Boot, gRPC, JPA, SLF4J | gRPC, Express, Pino, OTel | **gRPC, ASP.NET Core, EF Core, Redis, xUnit** |
| **Compiler safety net** | Strong | Strong | None | **Strong** |
| **Dep file complexity** | Low (`go.mod`) | High (`build.gradle`) | Low (`package.json`) | **Medium (`.csproj` XML + `.sln`)** |
| **Estimated Phase 1-2 effort** | S | M (javalang + DFA) | S | **S (bypass + profile + parser + validators)** |
| **MicroPrime viability** | Possible (regex parser) | Active (Phase 1-5) | Unlikely (no parser) | **Strong (tree-sitter + rigid structure)** |

---

## 9. Relationship to Target Project Documents

This document defines **pipeline-side requirements** — what the SDK needs to support C# code generation. It is complemented by two target project documents:

| Document | Purpose |
|----------|---------|
| `requirements-csharp.md` | Acceptance criteria for the Online Boutique C# cartservice (REQ-CMS-001 through REQ-CMS-V02). Defines **what** to generate. |
| `plan-csharp.md` | Implementation plan with feature contracts, LOC estimates, and validation criteria. Defines **how** the target code is structured. |
| **This document** (`CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md`) | Pipeline requirements for C# language support (REQ-CS-100 through REQ-CS-602). Defines **what the pipeline needs** to generate C# code successfully. |

The traceability chain is: Target requirements (REQ-CMS-*) → Target plan (F-001 through F-007) → Pipeline requirements (REQ-CS-*) → Pipeline implementation.

---

## 10. Capability Map Additions

### Prime Contractor Capability Map (MULTI_LANGUAGE_CAPABILITY_MAP.md)

The following row should be added to the Section 2 mapping table:

| # | Capability | C# |
|---|-----------|-----|
| C-1 | Static Structure Extraction | **tree-sitter-c-sharp** (in-process CST, `class_declaration`/`method_declaration` nodes) |
| C-2 | Structural Merge | SimpleMergeStrategy (whole-file replace) — tree-sitter-based merge when `CSHARP_MICROPRIME_ENABLED` |
| C-3 | Import Resolution | tree-sitter `using_directive` extraction + `.csproj` `<PackageReference>` parsing |
| C-4 | Syntax Validation | **tree-sitter `has_error`** (per-file, in-process, ~5ms) — `dotnet build` for full type checking |
| C-5 | Lint / Static Analysis | `dotnet format` (style only, optional) |
| C-6 | Import Audit + Injection | No tool — compiler catches at build time |
| C-7 | Stub Detection | tree-sitter body inspection for `NotImplementedException`, empty `{ }` |
| C-8 | Duplicate Detection | Compiler-enforced (won't compile) |
| C-9 | Body Splicing | **tree-sitter byte-offset splicing** (most precise of all languages) |
| C-10 | Blast Radius Scan | String match `using Namespace;` |
| C-11 | Framework Import Preamble | C# `using Namespace;` syntax |
| C-12 | Package Manager Artifacts | `.csproj` (XML with `<PackageReference>`) + `.sln` |

### C# Summary (for Section 3)

| Capability | Approach | Effort |
|-----------|----------|--------|
| C-1 Structure Extraction | tree-sitter-c-sharp (class/method/property/interface nodes) | Low-Medium |
| C-2 Structural Merge | SimpleMergeStrategy (tree-sitter-based when MicroPrime enabled) | Medium |
| C-3 Import Resolution | tree-sitter `using_directive` + .csproj parse | Low |
| C-4 Syntax Validation | tree-sitter `has_error` (per-file, no project needed) | Low |
| C-5 Lint | Skip (no built-in per-file linter) | None |
| C-6 Import Audit | Skip (compiler catches) | None |
| C-7 Stub Detection | tree-sitter body inspection | Low |
| C-8 Duplicate Detection | Skip (compiler catches) | None |
| C-9 Body Splicing | tree-sitter byte-offset splicing | Low-Medium |
| C-10 Blast Radius | Wire profile's import patterns | Low |
| C-11 Framework Preamble | Wire profile's framework_imports + C# fences | Low |
| C-12 .csproj/.sln Generation | Template from service metadata | Medium |

### Micro Prime Capability Map (MICRO_PRIME_MULTI_LANGUAGE_CAPABILITY_MAP.md)

| # | Capability | C# |
|---|-----------|-----|
| MP-1 | Syntax Validation | **tree-sitter `has_error`** (per-file, in-process, ~5ms, error recovery) |
| MP-2 | Element Location | **tree-sitter** `child_by_field_name('name')` on `method_declaration`/`class_declaration` |
| MP-3 | Signature Rendering | tree-sitter `returns`/`parameters`/modifier extraction → `public async Task<T> Method(Type p)` |
| MP-4 | System Prompts | Language-parameterized templates |
| MP-5 | Keyword Reserves | ~80 C# keywords + contextual keywords |
| MP-6 | Stub Detection | **tree-sitter** body inspection for `NotImplementedException`, empty `{ }` |
| MP-7 | Body Splicing | **tree-sitter byte-offset splicing** (`body.start_byte`/`body.end_byte`) |
| MP-8 | Structural Verify | **tree-sitter** walk collecting all typed declarations by name |
| MP-9 | Dunder Templates | Skip (no equivalent — but properties/DI/async patterns possible) |
| MP-10 | Class Decomposition | **tree-sitter-based** (iterate `class_body.named_children`, extract methods) |
| MP-11 | Function Decomposition | Portable (keyword swap) |
| MP-12 | Repair Pipeline | tree-sitter-aware repair + compiler + `dotnet format` |
| MP-13 | Literal Coercion | `true`/`false`/`null` (same as Java) |

### C# MicroPrime Feasibility: High (superior tooling to Java)

**Key advantages:**

1. **tree-sitter-c-sharp provides the best parser of any non-Python language.** Byte-level positions enable precise splicing without line-counting heuristics. Error recovery means partial parses return useful structure. In-process parsing (~5ms) with no subprocess overhead.

2. **Rigid class-per-file structure** like Java — `ForwardElementSpec.parent_class` ambiguity doesn't exist. Class decomposition maps directly to tree-sitter `class_body.named_children`.

3. **tree-sitter is superior to javalang** (Java's parser): byte positions (vs line-only), error recovery (vs exception on error), comprehensive C# 13 support (vs incomplete Java 17), actively maintained (2026 vs 2019).

4. **Strong compiler safety net** — duplicates, type errors, missing references are caught at compile time. Same benefit as Go and Java.

**Key considerations:**

- tree-sitter parses syntax (CST) but not semantics — overload resolution, generic type inference, and namespace resolution require Roslyn (`dotnet build`). For element-level generation, syntax-level understanding is usually sufficient.
- No `goimports` equivalent for C# — import correctness depends on prompt quality and seed enrichment.

**Estimated effort:** 2-3 weeks (comparable to Java, possibly faster due to superior parser tooling).

### Language Implementation Difficulty Ranking (updated)

| Rank | Language | MicroPrime Difficulty | Key Factor |
|------|----------|-----------|------------|
| 1 | Go | Easiest | `goimports` + compiler do the heavy lifting; regex parser adequate |
| 2 | **C#** | **Low-Medium** | **tree-sitter CST parser (best tooling); rigid structure; compiler safety** |
| 3 | Java | Medium | `javalang` PyPI parser (aging, less capable than tree-sitter); Gradle complexity |
| 4 | Node.js | Hardest | No compiler, no parser, dual module system, irregular syntax |

**Notable:** C# ranks ahead of Java for MicroPrime feasibility due to tree-sitter-c-sharp being a significantly better parser than javalang. If Java were being implemented today, `tree-sitter-java` (also available on PyPI) would be the better choice.
