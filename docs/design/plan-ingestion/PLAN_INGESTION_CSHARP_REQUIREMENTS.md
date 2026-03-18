# Plan Ingestion — C# Language Support Requirements

**Date:** 2026-03-18
**Status:** Draft
**Derived From:** PLAN_INGESTION_MULTI_LANGUAGE_REQUIREMENTS.md (REQ-PLI-*), CSHARP_PRIME_CONTRACTOR_REQUIREMENTS.md (REQ-CS-*), Online Boutique C# requirements (`requirements-csharp.md`) and plan (`plan-csharp.md`)
**Scope:** Plan ingestion pipeline changes needed before the first C# Prime Contractor run
**Validation Target:** Online Boutique cartservice — 7 features, 14 files, ~964 LOC across C#, XML (.csproj/.sln), JSON (appsettings.json), Protobuf, Dockerfile
**Depends On:** Node.js plan ingestion validation (PLAN_INGESTION_NODEJS_REQUIREMENTS.md) — shared patterns for non-Python PARSE prompt structure

---

## 1. Current State Assessment

C# plan ingestion has **minimal explicit support** — the pipeline recognizes `.cs` as a language extension but has no C#-specific metadata extraction, service inference, or prompt sections.

### Already Implemented

| Capability | Evidence | Status |
|-----------|----------|--------|
| `_EXT_TO_LANGUAGE` recognizes `.cs` → `"csharp"` | `plan_ingestion_workflow.py:97`, `seeds/derivation.py:49` | DONE |
| `.csproj` detected in dependency file logic | `plan_ingestion_workflow.py:676`, `seeds/derivation.py:227` | DONE |
| `.cs` in target file extension scan | `plan_ingestion_workflow.py:681`, `seeds/derivation.py:233` | DONE |
| `_NON_PYTHON_EXTENSIONS` includes `.cs` | `engine.py:109` | DONE |
| `_is_non_python_file()` defaults unknown to True | `engine.py:147` | DONE |
| `lang_detect.py` does NOT map `.cs` → language | Missing | GAP |

### Gaps

| Gap | REQ-PLI | Severity | Description |
|-----|---------|----------|-------------|
| G-1 | PLI-100 | **P0** | `lang_detect.py` has no `.cs` → `"csharp"` mapping; also missing `.csproj`, `.sln`, `.razor` |
| G-2 | PLI-200 | **P1** | No C# PARSE prompt fields (namespace, target_framework, build_system) |
| G-3 | PLI-301 | **P1** | No C# fields in `_CONTEXT_THREADABLE_FIELDS` |
| G-4 | PLI-300 | **P1** | No C# block in `_infer_service_metadata()` |
| G-5 | PLI-700 | **P1** | No C# fields on `ParsedFeature` or `SeedTask` |
| G-6 | PLI-501 | **P1** | No `_build_csharp_module_section()` in spec builder |
| G-7 | PLI-500 | **P1** | No C# available-imports formatting (`using X;` syntax) |
| G-8 | PLI-402 | **P1** | No `.csproj` deterministic generation routing |
| G-9 | PLI-102 | **P2** | No filename detection for `.csproj`, `.sln`, `appsettings.json`, `Program.cs` |
| G-10 | PLI-502 | **P2** | No ASP.NET Core / gRPC framework detection from plan text |
| G-11 | — | **P2** | No `CSharpLanguageProfile` in `languages/` (needed for `generate_dependency_file()`, `system_prompt_role`, `coding_standards`) |

---

## 2. Requirements

### 2.1 Language Detection (REQ-PLI-CS-100)

`lang_detect.py` MUST map C# file extensions and filenames:

**Extension mappings:**
```python
_EXTENSION_TO_LANG = {
    ...
    ".cs": "csharp",
    ".csx": "csharp",      # C# script
    ".razor": "csharp",    # Razor pages (ASP.NET)
}
```

**Filename mappings:**
```python
_FILENAME_TO_LANG = {
    ...
    "appsettings.json": "csharp",           # ASP.NET config (distinct from generic JSON)
    "appsettings.Development.json": "csharp",
    "Program.cs": "csharp",                  # ASP.NET entry point (redundant with .cs but explicit)
}
```

**Note:** `.csproj` and `.sln` are XML-based but should map to `"csharp"` for routing purposes (they're C#-ecosystem build files, not generic XML). Same pattern as `build.gradle` → `"java"`.

```python
_FILENAME_TO_LANG = {
    ...
    # C# build files (detected by suffix, not exact name)
}

# Additional suffix check in detect_language():
if filename.endswith(".csproj") or filename.endswith(".sln"):
    return "csharp"
```

**Language type update:**
```python
Language = Literal["python", "dockerfile", "go", "java", "nodejs", "csharp", "proto", "text", "unknown"]
```

**Acceptance:** `detect_language("CartService.cs")` returns `"csharp"`. `detect_language("cartservice.csproj")` returns `"csharp"`.

**Status:** NOT IMPLEMENTED

---

### 2.2 PARSE Prompt — C# Metadata Fields (REQ-PLI-CS-200)

The PARSE prompt MUST request C#-specific metadata:

```json
{
  "csharp_namespace": "optional root namespace e.g. cartservice",
  "target_framework": "optional .NET TFM e.g. net8.0 (default: net8.0)",
  "csharp_project_type": "optional: webapi, grpc, console, classlib (default: webapi)"
}
```

**Why these fields:**

| Field | Purpose | Downstream Consumer |
|-------|---------|-------------------|
| `csharp_namespace` | Root namespace for `namespace X { }` declarations | Spec builder module section, `.csproj` generation |
| `target_framework` | Target Framework Moniker for `.csproj` | `.csproj` deterministic generation |
| `csharp_project_type` | Template selection (webapi vs console vs classlib) | `.csproj` generation, `Program.cs` boilerplate |

**Threading:** All three fields MUST be added to `_CONTEXT_THREADABLE_FIELDS`.

**PARSE prompt text:**
```
csharp_namespace: (C# projects only) the root namespace, typically matching the project directory name (e.g. "cartservice"). Used for namespace declarations and project file generation. Omit for non-C# projects.
target_framework: (C# projects only) .NET Target Framework Moniker from the plan. Common values: "net8.0", "net9.0". Default "net8.0". Omit for non-C# projects.
csharp_project_type: (C# projects only) the project type: "webapi" (ASP.NET Core Web API), "grpc" (gRPC service), "console" (console app), "classlib" (class library). Default "webapi". Omit for non-C# projects.
```

**Status:** NOT IMPLEMENTED

---

### 2.3 ParsedFeature and SeedTask Model Extensions (REQ-PLI-CS-201)

**`ParsedFeature` additions:**
```python
csharp_namespace: str = ""       # Root namespace
target_framework: str = ""       # .NET TFM (e.g. "net8.0")
csharp_project_type: str = ""    # webapi, grpc, console, classlib
```

**`SeedTask` additions:**
```python
csharp_namespace: str = ""
target_framework: str = ""
csharp_project_type: str = ""
```

With `from_seed_entry()` wiring:
```python
csharp_namespace=context.get("csharp_namespace", ""),
target_framework=context.get("target_framework", ""),
csharp_project_type=context.get("csharp_project_type", ""),
```

**Status:** NOT IMPLEMENTED

---

### 2.4 Service Metadata Inference (REQ-PLI-CS-300)

`_infer_service_metadata()` MUST include a C# block (parallel to Go and Node.js blocks):

```python
# C#-specific: derive namespace, target_framework, project_type
if primary_language == "csharp":
    # csharp_namespace: prefer explicit, else infer from directory
    namespaces: list[str] = []
    for f in features:
        ns = getattr(f, "csharp_namespace", "")
        if ns:
            namespaces.append(ns)
    if namespaces:
        metadata["csharp_namespace"] = namespaces[0]
    elif service_dirs:
        # Infer from directory name (e.g. src/cartservice → cartservice)
        metadata["csharp_namespace"] = service_dirs[0].replace("-", "_")

    # target_framework
    target_framework = "net8.0"
    for f in features:
        tf = getattr(f, "target_framework", "")
        if tf:
            target_framework = tf
            break
    if onboarding:
        target_framework = str(onboarding.get("target_framework", target_framework))
    metadata["target_framework"] = target_framework

    # csharp_project_type
    project_type = "webapi"
    for f in features:
        pt = getattr(f, "csharp_project_type", "")
        if pt:
            project_type = pt
            break
    metadata["csharp_project_type"] = project_type
```

**Status:** NOT IMPLEMENTED

---

### 2.5 Spec Builder — C# Module Section (REQ-PLI-CS-400)

`_build_csharp_module_section()` MUST inject C#-specific structural guidance:

```markdown
## C# / .NET Context
- **Target framework**: net8.0
- **Root namespace**: cartservice
- **Project type**: grpc

### C# Conventions
- Use file-scoped namespaces: `namespace Cartservice;` (not `namespace Cartservice { ... }`)
- One public class per file, filename matches class name
- Use `var` for local variables when the type is obvious from the right side
- Use primary constructors for DI (C# 12+): `public class CartService(ILogger<CartService> logger)`
- Use `async Task` for async methods (not `async void` except event handlers)
- NuGet package imports use `using` directives (no version in using statement)

### ASP.NET Core / gRPC Patterns
- Services registered via `builder.Services.AddXxx()` in `Program.cs`
- gRPC services inherit from generated base class: `public class CartService : Hipstershop.CartService.CartServiceBase`
- Health checks: `builder.Services.AddGrpcHealthChecks()` + `app.MapGrpcHealthChecksService()`
- Configuration via `IConfiguration` / `IOptions<T>` pattern
```

**Conditional sections:**
- gRPC patterns: injected when `detected_frameworks` includes `"grpc"` or target files contain `.proto`
- ASP.NET patterns: injected when `csharp_project_type` is `"webapi"` or `"grpc"`

**Status:** NOT IMPLEMENTED

---

### 2.6 Available-Imports Formatting (REQ-PLI-CS-401)

`_build_available_imports_section()` MUST format C# dependencies as `using` directives:

**Input:** `Grpc.AspNetCore@2.67.0`, `Google.Protobuf@3.28.0`, `StackExchange.Redis@2.8.0`

**Output:**
```
using Grpc.Core;
using Google.Protobuf;
using StackExchange.Redis;
```

**NuGet package → namespace mapping:**
NuGet package names generally match their root namespace. Exceptions should be handled via a `_NUGET_TO_NAMESPACE` alias map (parallel to `_PYPI_TO_IMPORT` for Python):

```python
_NUGET_TO_NAMESPACE: dict[str, str] = {
    "Grpc.AspNetCore": "Grpc.Core",
    "Google.Protobuf": "Google.Protobuf",
    "StackExchange.Redis": "StackExchange.Redis",
    "Microsoft.Extensions.Logging": "Microsoft.Extensions.Logging",
    "Microsoft.AspNetCore.Diagnostics.HealthChecks": "Microsoft.Extensions.Diagnostics.HealthChecks",
}
```

**Version stripping:** `@` separator (like Node.js), not `==` (Python) or space (Go).

**Status:** NOT IMPLEMENTED

---

### 2.7 Dependency File Generation — .csproj (REQ-PLI-CS-402)

A `.csproj` deterministic generator MUST produce valid MSBuild XML:

```xml
<Project Sdk="Microsoft.NET.Sdk.Web">

  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <RootNamespace>cartservice</RootNamespace>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Grpc.AspNetCore" Version="2.67.0" />
    <PackageReference Include="Google.Cloud.Spanner.Data" Version="5.0.0" />
    <PackageReference Include="StackExchange.Redis" Version="2.8.0" />
  </ItemGroup>

</Project>
```

**Inputs:**
- `target_framework` from service metadata (default: `net8.0`)
- `csharp_namespace` from service metadata
- `dependencies` list from features (NuGet package@version format)
- `csharp_project_type` determines SDK type:
  - `"webapi"` or `"grpc"` → `Microsoft.NET.Sdk.Web`
  - `"console"` → `Microsoft.NET.Sdk`
  - `"classlib"` → `Microsoft.NET.Sdk`

**Routing in EMIT:** Files matching `*.csproj` in target_files trigger `CSharpLanguageProfile.generate_dependency_file()`.

**Status:** NOT IMPLEMENTED — requires `CSharpLanguageProfile` creation

---

### 2.8 Framework Detection from Plan Text (REQ-PLI-CS-403)

During PARSE or pre-PARSE, detect C# framework indicators:

| Framework | Detection Signals | Impact on Generation |
|-----------|-------------------|---------------------|
| ASP.NET Core | "ASP.NET", "WebAPI", "Kestrel", "Program.cs", "builder.Services" | Inject DI + middleware patterns |
| gRPC | "gRPC", "protobuf", ".proto", "Grpc.AspNetCore" | Inject gRPC service patterns |
| Entity Framework | "EF Core", "DbContext", "Entity Framework", "migrations" | Inject EF Core patterns |
| xUnit | "xUnit", "xunit", "[Fact]", "[Theory]" | Inject test patterns |
| Redis | "Redis", "StackExchange.Redis", "IDistributedCache" | Inject Redis connection patterns |

Detected frameworks stored in `service_metadata.detected_frameworks`.

**Status:** NOT IMPLEMENTED

---

### 2.9 Solution File Handling (REQ-PLI-CS-404)

For projects with a `.sln` file in target_files:

1. `.sln` files have a rigid format with GUIDs — they SHOULD be generated deterministically, not via LLM
2. The generator needs: project name, project path relative to `.sln`, project GUID (generated)
3. If the plan includes multiple C# projects (e.g., `CartService` + `CartService.Tests`), each gets its own GUID entry

**This is P2 — the cartservice validation target may not need multi-project `.sln` generation in the first run.**

**Status:** NOT IMPLEMENTED

---

## 3. CSharpLanguageProfile (REQ-PLI-CS-500)

A `CSharpLanguageProfile` class MUST be created at `src/startd8/languages/csharp.py` with at minimum:

| Property/Method | Value | Notes |
|-----------------|-------|-------|
| `language_id` | `"csharp"` | |
| `display_name` | `"C#"` | |
| `source_extensions` | `[".cs"]` | |
| `build_file_patterns` | `["*.csproj", "*.sln", "appsettings.json"]` | |
| `syntax_check_command` | `None` | `dotnet build` requires full project — use tree-sitter for per-file if available |
| `system_prompt_role` | `"an expert C# / .NET engineer"` | |
| `coding_standards` | Modern C# 12+, nullable refs, primary constructors, file-scoped namespaces | |
| `docker_base_image` | `"mcr.microsoft.com/dotnet/sdk:8.0"` | |
| `docker_runtime_image` | `"mcr.microsoft.com/dotnet/aspnet:8.0"` | |
| `generate_dependency_file()` | Produces `.csproj` XML from metadata | REQ-PLI-CS-402 |
| `framework_imports` | gRPC, EF Core, Redis, OTel patterns | |
| `stub_patterns` | `throw new NotImplementedException()`, `// TODO` | |

**Entry point registration:**
```toml
[project.entry-points."startd8.languages"]
csharp = "startd8.languages.csharp:CSharpLanguageProfile"
```

**Status:** NOT IMPLEMENTED

---

## 4. Implementation Phases

### Phase 1: Foundation (enables first C# plan ingestion run)

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| F-1 | CS-100 | Add `.cs`/`.csproj`/`.sln` to `lang_detect.py` | `lang_detect.py` | ~10 lines |
| F-2 | CS-500 | Create `CSharpLanguageProfile` (minimal) | `languages/csharp.py` | ~150 lines |
| F-3 | CS-200 | Add C# fields to PARSE prompt | `plan_ingestion_workflow.py` | ~15 lines |
| F-4 | CS-201 | Add C# fields to `ParsedFeature` + `SeedTask` | `plan_ingestion_models.py`, `seeds/models.py` | ~15 lines |
| F-5 | CS-201 | Add C# fields to `_CONTEXT_THREADABLE_FIELDS` | `plan_ingestion_workflow.py` | ~3 lines |
| F-6 | CS-300 | Add C# block to `_infer_service_metadata()` | `plan_ingestion_workflow.py`, `seeds/derivation.py` | ~30 lines |
| F-7 | CS-400 | Create `_build_csharp_module_section()` | `spec_builder.py` | ~40 lines |
| F-8 | CS-401 | Add C# import formatting | `spec_builder.py` | ~15 lines |

**~280 lines. Enables plan ingestion → seed production for C# projects.**

### Phase 2: Dependency File Generation

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| D-1 | CS-402 | `.csproj` deterministic generator | `languages/csharp.py` | ~60 lines |
| D-2 | CS-402 | EMIT routing for `.csproj` targets | `plan_ingestion_emitter.py` | ~10 lines |
| D-3 | — | `_NON_PYTHON_EXTENSIONS` add `.csproj`, `.sln`, `.razor` | `engine.py` | ~3 lines |

**~73 lines.**

### Phase 3: Quality & Framework Detection

| Step | REQ | Description | Files | Effort |
|------|-----|-------------|-------|--------|
| Q-1 | CS-403 | ASP.NET/gRPC/EF Core framework detection | `plan_ingestion_workflow.py` | ~30 lines |
| Q-2 | CS-404 | `.sln` deterministic generation | `languages/csharp.py` | ~40 lines |
| Q-3 | — | C# plan ingestion tests | `tests/unit/` | ~120 lines |

**~190 lines.**

### Total: ~543 lines across 3 phases

---

## 5. Comparison: Plan Ingestion Readiness by Language

| Capability | Python | Go | Java | Node.js | C# |
|-----------|--------|-----|------|---------|-----|
| File extension detection | DONE | DONE | DONE | DONE | **GAP** |
| Filename detection | N/A | Partial | DONE | DONE | **GAP** |
| PARSE prompt fields | N/A | DONE | DONE | DONE | **GAP** |
| Context threading (QP-1) | N/A | DONE | DONE | DONE | **GAP** |
| Service metadata inference | N/A | DONE | DONE | DONE | **GAP** |
| Module context section | N/A | DONE | DONE | DONE | **GAP** |
| Available-imports formatting | DONE | DONE | Partial | NEEDS VERIFY | **GAP** |
| Dependency file generation | DONE | DONE | DONE | DONE | **GAP** |
| Dep file placement (monorepo) | DONE | DONE | DONE | NEEDS VERIFY | **GAP** |
| Framework detection | N/A | DONE | DONE | GAP | **GAP** |
| Language profile | DONE | DONE | DONE | DONE | **GAP** |
| Element extraction | DONE | DONE | DONE | GAP | **GAP** |
| Acyclicity gate | DONE | DONE | DONE | DONE | DONE |

**Assessment:** C# plan ingestion requires a full implementation pass (Phase 1 + 2). Unlike Node.js (which is ~80% done), C# has only basic extension recognition. The good news: the patterns from Go, Java, and Node.js are well-established, making each new language a formulaic addition.

---

## 6. Unique C# Considerations

### 6.1 XML-Based Build Files

Unlike Go (`go.mod` — plain text), Java (`build.gradle` — Groovy DSL), and Node.js (`package.json` — JSON), C# uses `.csproj` (MSBuild XML). The deterministic generator needs XML templating — not JSON serialization or text concatenation.

### 6.2 Multiple Build Artifacts per Service

A typical C# service produces:
- `ServiceName.csproj` — project file
- `ServiceName.sln` — solution file (optional but conventional)
- `appsettings.json` — runtime configuration
- `appsettings.Development.json` — dev-only config overrides
- `Properties/launchSettings.json` — launch profiles

Compared to Go (just `go.mod`) or Node.js (just `package.json`), C# has a higher build-artifact-to-source-code ratio.

### 6.3 Namespace vs Directory Mismatch

C# namespaces don't always map to directories. A file at `src/cartservice/cartstore/RedisCartStore.cs` might use namespace `cartservice` (flat) or `cartservice.cartstore` (nested). The `<RootNamespace>` element in `.csproj` controls this. The PARSE prompt should extract the root namespace to avoid LLM guessing.

### 6.4 Implicit Usings (C# 10+)

Modern .NET projects with `<ImplicitUsings>enable</ImplicitUsings>` automatically import common namespaces (`System`, `System.Collections.Generic`, `System.Linq`, `System.Threading.Tasks`, etc.). The available-imports section should NOT list these when implicit usings are enabled — it wastes prompt budget on unnecessary guidance.
