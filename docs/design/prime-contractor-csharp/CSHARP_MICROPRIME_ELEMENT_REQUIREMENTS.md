# C# MicroPrime Element-Level Generation Requirements

> **Version:** 1.0.0
> **Status:** DRAFT
> **Date:** 2026-03-22
> **Parent:** [KAIZEN_CSHARP_REQUIREMENTS.md](KAIZEN_CSHARP_REQUIREMENTS.md)
> **Language Profile:** `CSharpLanguageProfile` (`src/startd8/languages/csharp.py`)
> **Parser:** `csharp_parser.py` (tree-sitter + regex fallback) — IMPLEMENTED
> **Splicer:** `csharp_splicer.py` (tree-sitter byte-offset splicing) — IMPLEMENTED
> **Scope:** Wire existing C# parser/splicer into MicroPrime for element-level code generation
> **Prerequisite:** `pip install -e ".[csharp]"` for tree-sitter-c-sharp

---

## Table of Contents

1. [Overview](#1-overview)
2. [Current State Assessment](#2-current-state-assessment)
3. [MicroPrime Engine Integration](#3-microprime-engine-integration)
4. [Skeleton Assembly](#4-skeleton-assembly)
5. [Element Body Extraction](#5-element-body-extraction)
6. [Kaizen Feedback Wiring](#6-kaizen-feedback-wiring)
7. [Compliance Results Storage](#7-compliance-results-storage)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Implementation Order](#9-implementation-order)
10. [Verification Strategy](#10-verification-strategy)

---

## 1. Overview

### 1.1 Problem Statement

C# has the most complete language infrastructure in the SDK after Python:

- **Parser** (`csharp_parser.py`): tree-sitter CST with regex fallback — extracts classes, interfaces, structs, records, enums, methods, constructors, properties, usings, namespaces.  Returns `CSharpElement` with byte offsets, line numbers, modifiers, return types, parameters, and parent tracking.
- **Splicer** (`csharp_splicer.py`): tree-sitter byte-offset body replacement — detects stubs (`NotImplementedException`, `NotSupportedException`, `// TODO`), replaces bodies, validates post-splice syntax.
- **Signature Parser** (`csharp_signature_parser.py`): converts LLM-extracted C# signatures into `ForwardElementSpec` objects.
- **Semantic Checks** (`csharp_semantic_checks.py`): 9 checks implemented.
- **Repair Pipeline**: 4 repair routes, 3 dedicated steps (convention fix, syntax validate, SQL parameterize).
- **Deterministic Generators**: `.csproj`, `.sln`, `appsettings.json`.

**Despite all this infrastructure, C# tasks bypass MicroPrime element-level generation entirely.** The `_is_non_python_file()` check in `micro_prime/engine.py` returns `False` for `.cs` files (because `CSharpLanguageProfile` registers `.cs` in `source_extensions`), meaning MicroPrime *attempts* element-level generation — but falls through to Python `ast.parse()` in `_extract_element_body()`, which fails on C# syntax. The element then escalates to the fallback LLM generator, wasting a cycle.

The parser, splicer, and signature parser exist but are disconnected from the MicroPrime pipeline.

### 1.2 Goal

Wire the existing C# tree-sitter infrastructure into MicroPrime so that C# `.cs` files can use element-level generation (decomposition, body extraction, stub-fill splicing) instead of always falling through to file-whole LLM generation.

### 1.3 Non-Goals

- Building a new parser (the parser already exists)
- Reimplementing the splicer (the splicer already exists)
- Adding Ollama/local model support for C# (Phase 2 — requires C# compile-check verification)
- Compilation-based validation via `dotnet build` (requires full project context, too heavyweight for element-level)

### 1.4 Key Advantage: tree-sitter Gives Us More Than Go

Go uses regex-based parsing (~90% coverage) because Go syntax is regular. C# has generics (`Dictionary<string, List<int>>`), attributes (`[HttpGet]`), expression-bodied members (`=> expr;`), LINQ, and complex inheritance — regex covers ~60% at best.

tree-sitter gives us **100% grammar coverage** with precise byte offsets, enabling:
- Exact method body extraction (not regex approximation)
- Accurate stub detection across all body forms (block `{ }`, expression `=>`, empty)
- Modifier parsing (public/private/static/async/virtual/override/abstract)
- Parent class tracking (methods nested inside classes)
- Error-tolerant parsing (partial files still produce useful trees)

The existing `csharp_parser.py` and `csharp_splicer.py` already leverage all of these capabilities. This requirements document is about **connecting them to MicroPrime**, not building them.

---

## 2. Current State Assessment

### 2.1 What Works

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| Language profile | `languages/csharp.py` | IMPLEMENTED | All 15+ protocol properties/methods |
| tree-sitter parser | `languages/csharp_parser.py` | IMPLEMENTED | 508 lines; extracts 8 element kinds |
| Byte-offset splicer | `languages/csharp_splicer.py` | IMPLEMENTED | 231 lines; stub detection + body replacement |
| Signature parser | `utils/csharp_signature_parser.py` | IMPLEMENTED | 161 lines; LLM signatures → `ForwardElementSpec` |
| Semantic checks | `validators/csharp_semantic_checks.py` | IMPLEMENTED | 9 checks |
| Repair pipeline | `repair/routing.py` | IMPLEMENTED | 4 routes, 3 steps |
| Deterministic generators | `prime_adapter.py` | IMPLEMENTED | `.csproj`, `.sln`, `appsettings.json` |
| Disk validation | `forward_manifest_validator.py` | IMPLEMENTED | `_validate_csharp_file()` |
| Integration engine wiring | `integration_engine.py` | IMPLEMENTED | Post-merge semantic check + repair |

### 2.2 What's Missing (Gaps)

| Gap | Component | Impact | Effort |
|-----|-----------|--------|--------|
| **G-1**: No `_extract_element_body` branch for C# | `micro_prime/engine.py` | `.cs` elements fall through to Python `ast.parse()` → failure → escalation | Small |
| **G-2**: No `CSharpDeterministicFileAssembler` | `micro_prime/prime_adapter.py` | `.cs` skeletons use generic non-Python passthrough (existing content or skip) | Medium |
| **G-3**: No `CSharpElement` → `ForwardElementSpec` source converter | `languages/csharp_parser.py` | Can parse existing `.cs` source but can't populate the forward manifest from it | Small |
| **G-4**: No Kaizen postmortem feedback for C# | `prime_postmortem.py` | C# semantic check results not fed into cross-run Kaizen suggestions | Small |
| **G-5**: No `compliance_results` storage for C# | `prime_contractor.py` | C# semantic results collected during integration but not persisted for Kaizen | Small |
| **G-6**: Missing tree-sitter node types in parser | `csharp_parser.py` | No `field_declaration`, `delegate_declaration`, `event_declaration`, `arrow_expression_clause` extraction | Medium |
| **G-7**: `CSharpElement` field gaps vs `GoElement` | `csharp_parser.py` | No `doc_comment`, `is_exported`, `bases`, `type_annotation` fields | Small |

---

## 3. MicroPrime Engine Integration

### REQ-CS-MP-100: `_extract_element_body` C# Branch

Add a C# branch to `_extract_element_body()` in `micro_prime/engine.py` that uses the existing tree-sitter parser to extract method/property/constructor bodies.

**Implementation:**

```python
if lang_id == "csharp":
    from startd8.languages.csharp_parser import parse_csharp
    result = parse_csharp(code)
    for elem in result.elements:
        if elem.name == element.name and elem.body_start_byte is not None:
            body_bytes = code.encode("utf-8")[elem.body_start_byte:elem.body_end_byte]
            return body_bytes.decode("utf-8")
    return None
```

**Key differences from Go path:**
- Go uses line-based extraction (regex declaration finder + brace counting)
- C# uses byte-offset extraction (tree-sitter `body_start_byte`/`body_end_byte`)
- C# can distinguish methods on different classes via `elem.parent` field
- C# handles expression-bodied members (`=>`) if REQ-CS-MP-600 is implemented

**Acceptance criteria:**
- `_extract_element_body()` returns the body text for a C# method given its name
- Methods with the same name on different classes are disambiguated via `parent_class` from the `ForwardElementSpec`
- Expression-bodied members (`public int Count => _items.Count;`) are extracted correctly
- Returns `None` when element is not found (graceful fallback to escalation)
- Falls back to regex-based extraction when tree-sitter is unavailable

**Dependencies:** None — `csharp_parser.py` already exists and returns byte offsets.

### REQ-CS-MP-101: `_build_element_system_prompt` C# Handling

The existing generic non-Python path in `_build_element_system_prompt()` already uses `profile.system_prompt_role` and `profile.coding_standards`. For C#, this produces:

```
You are an expert C# / .NET engineer. Implement the spec exactly.
{coding_standards}
```

**Additional C#-specific prompt guidance needed:**
- Stub marker: `throw new NotImplementedException()` (not `panic("not implemented")`)
- Indentation: 4 spaces (not tabs like Go)
- Namespace: File-scoped (`namespace Foo.Bar;`) — never block-scoped
- Async: Methods returning `Task<T>` should use `async`/`await`

**Implementation:** Add `is_csharp` branch similar to `is_go` in `_build_element_system_prompt()` to inject C#-specific stub marker and formatting guidance.

### REQ-CS-MP-102: Non-Python Bypass Exemption for `.cs`

Currently, `.cs` files are NOT bypassed by `_is_non_python_file()` because `.cs` is in the extension map. This is correct *when element-level generation is wired*. However, without REQ-CS-MP-100, `.cs` files enter MicroPrime → fail at body extraction → escalate. This wastes a cycle.

**Phase 1 (now):** No change needed — the escalation path works, just wastes a cycle.

**Phase 2 (after REQ-CS-MP-100):** `.cs` files should flow through MicroPrime with:
1. Skeleton from `CSharpDeterministicFileAssembler` (REQ-CS-MP-200)
2. Element extraction via tree-sitter parser (REQ-CS-MP-100)
3. Body splicing via `csharp_splicer.splice_csharp_bodies()` (already exists)
4. Post-splice validation via tree-sitter syntax check (already exists)

---

## 4. Skeleton Assembly

### REQ-CS-MP-200: `CSharpDeterministicFileAssembler`

Create a deterministic file assembler for `.cs` files that produces compilable skeletons with `throw new NotImplementedException()` stubs. This parallels `JavaDeterministicFileAssembler`.

**Input:** `ForwardFileSpec` with `elements: List[ForwardElementSpec]`, target file path, service metadata (namespace, target framework).

**Output:** Compilable C# source file with:
1. File-scoped namespace declaration (derived from directory path)
2. Required `using` directives (from `ForwardFileSpec.prescribed_imports` + framework defaults)
3. Class/interface/struct/record declarations (from `ForwardElementSpec` with `kind=CLASS`)
4. Method stubs with correct signatures and `throw new NotImplementedException()` bodies
5. Property stubs with appropriate accessors
6. Constructor stubs

**Example skeleton output:**

```csharp
namespace CartService.Services;

using Grpc.Core;
using Microsoft.Extensions.Logging;

public class CartServiceImpl : Cart.CartBase
{
    private readonly ILogger<CartServiceImpl> _logger;

    public CartServiceImpl(ILogger<CartServiceImpl> logger)
    {
        _logger = logger;
    }

    public override Task<Cart> GetCart(GetCartRequest request, ServerCallContext context)
    {
        throw new NotImplementedException();
    }

    public override Task<Empty> AddItem(AddItemRequest request, ServerCallContext context)
    {
        throw new NotImplementedException();
    }

    public override Task<Empty> EmptyCart(EmptyCartRequest request, ServerCallContext context)
    {
        throw new NotImplementedException();
    }
}
```

**Key decisions:**
- File-scoped namespace (never block-scoped) — aligns with `CSharpLanguageProfile.coding_standards`
- `ILogger<T>` constructor injection for service classes — aligns with REQ-PI-CS-101
- Method signatures derived from `ForwardElementSpec.signature` (parameters, return type)
- Base class and interface implementation derived from `ForwardElementSpec.bases`
- `override` modifier when base class methods are being implemented

**Namespace derivation:** Use `CSharpLanguageProfile._derive_namespace()` which already converts directory paths to PascalCase namespaces.

**Integration point:** Wire into `prime_adapter.py` skeleton generation loop, after the `.java` handler and before the generic non-Python bypass:

```python
if _suffix == ".cs":
    # C# source files: use CSharpDeterministicFileAssembler
    ...
    continue
```

### REQ-CS-MP-201: Skeleton `using` Resolution

The skeleton must include correct `using` directives. Sources (in priority order):
1. `ForwardFileSpec.prescribed_imports` — explicit imports from the forward manifest
2. `CSharpLanguageProfile.framework_imports` — framework-specific defaults (gRPC, ASP.NET Core, etc.)
3. `service_metadata.detected_frameworks` — auto-detected from `.csproj` PackageReferences
4. Base class/interface imports — e.g., `Cart.CartBase` requires `using` for the proto namespace

**Acceptance criteria:**
- Skeleton compiles successfully when all stubs are implemented
- No unused `using` warnings (checked by `dotnet format`)
- Missing `using` directives are caught by `check_using_coverage()` in `csharp_splicer.py`

---

## 5. Element Body Extraction

### REQ-CS-MP-300: tree-sitter Body Extraction

Implement C# element body extraction using the existing `csharp_parser.py` byte offsets. This replaces the Python `ast.parse()` fallback for C# files.

**Extraction modes:**

| Element Kind | Body Location | Extraction |
|---|---|---|
| Method (block body) | `{ ... }` block | `body_start_byte` to `body_end_byte` from `CSharpElement` |
| Method (expression body) | `=> expr;` | `arrow_expression_clause` child node (REQ-CS-MP-600) |
| Property (auto) | `{ get; set; }` | Entire accessor list |
| Property (computed) | `{ get { ... } }` or `=> expr;` | Accessor body or arrow clause |
| Constructor | `{ ... }` block | Same as method |
| Class/struct/record | `{ ... members ... }` | Full type body |

**Disambiguation:** When multiple methods share the same name (overloads), match by:
1. `element.name` (function name)
2. `element.parent_class` from `ForwardElementSpec` → `elem.parent` from `CSharpElement`
3. Parameter count as tiebreaker (from `elem.parameters` vs `element.signature.params`)

**Fallback:** When tree-sitter is unavailable, use brace-depth counting (similar to Go splicer pattern) anchored on `public/private/protected ... <name>(` regex.

### REQ-CS-MP-301: Stub Detection for C#

The splicer already detects stubs via `CSHARP_STUB_PATTERNS`:
- `throw new NotImplementedException()`
- `throw new NotSupportedException()`
- `// TODO`

**Additional stubs to detect (expand `stub_patterns`):**
- `throw new System.NotImplementedException()` (fully qualified)
- `=> throw new NotImplementedException()` (expression-bodied stub)
- Empty bodies: `{ }` or `{ return default; }`

---

## 6. Kaizen Feedback Wiring

### REQ-CS-MP-400: C# `CAUSE_TO_SUGGESTION` Mappings

Add C#-specific entries to `CAUSE_TO_SUGGESTION` in `prime_postmortem.py`. Map each of the 9 C# semantic check categories to a concrete suggestion:

| Category | Target Phase | Suggestion | Confidence |
|---|---|---|---|
| `console_writeline_in_service` | `draft` | "Use `ILogger<T>` — never `Console.WriteLine` in service classes" | 0.90 |
| `sql_injection_risk` | `draft` | "Use parameterized queries (`@param`) — never string interpolation in SQL" | 0.95 |
| `interface_file_contains_class` | `draft` | "Interfaces go in `IFoo.cs`, implementations in `Foo.cs`" | 0.80 |
| `missing_nullable_in_csproj` | `spec` | "Add `<Nullable>enable</Nullable>` to .csproj" | 0.95 |
| `empty_catch_block` | `draft` | "Always log exceptions: `catch (Exception ex) { _logger.LogError(ex, ...); throw; }`" | 0.90 |
| `missing_async_await` | `draft` | "Async methods must `await` at least one operation" | 0.85 |
| `missing_access_modifier` | `draft` | "All types need explicit access modifiers (`public class`, not `class`)" | 0.85 |
| `global_using_static` | `draft` | "Avoid `using static` — use explicit class-qualified access" | 0.70 |
| `namespace_filepath_mismatch` | `draft` | "Namespace must match directory: `src/CartService/Services/` → `namespace CartService.Services;`" | 0.95 |

### REQ-CS-MP-401: C# `_SEMANTIC_CATEGORY_TO_SUGGESTION` Mappings

Add all 9 C# categories to `_SEMANTIC_CATEGORY_TO_SUGGESTION` in `prime_postmortem.py` so that semantic check results trigger Kaizen suggestion generation.

---

## 7. Compliance Results Storage

### REQ-CS-MP-500: Store C# Semantic Results in `compliance_results`

Go, Java, and Node.js store their semantic check results in `compliance_results` for Kaizen consumption (commit `1ec8849`). C# does not. Add the same wiring:

```python
# In integration_engine.py or prime_contractor.py, after C# semantic checks:
if csharp_issues:
    compliance_results[file_path] = {
        "semantic_issues": [issue.to_dict() for issue in csharp_issues],
        "language": "csharp",
    }
```

This enables the postmortem evaluator to aggregate C# issues into `kaizen-metrics.json` and generate cross-run trend analysis.

---

## 8. Traceability Matrix

| Gap | Requirements | Implementation Home | Effort |
|-----|-------------|---------------------|--------|
| G-1: No body extraction | REQ-CS-MP-100, 300 | `micro_prime/engine.py` | Small |
| G-2: No skeleton assembler | REQ-CS-MP-200, 201 | New: `utils/csharp_file_assembler.py` + `prime_adapter.py` | Medium |
| G-3: No source → ForwardElementSpec | REQ-CS-MP-300 (byproduct) | `csharp_parser.py` | Small |
| G-4: No Kaizen feedback | REQ-CS-MP-400, 401 | `prime_postmortem.py` | Small |
| G-5: No compliance_results | REQ-CS-MP-500 | `integration_engine.py` or `prime_contractor.py` | Small |
| G-6: Missing parser node types | REQ-CS-MP-600 | `csharp_parser.py` | Medium |
| G-7: CSharpElement field gaps | REQ-CS-MP-601 | `csharp_parser.py` | Small |

---

## 9. Implementation Order

### Phase 0: Quick Wins (pre-requisites, ~1 hour)

**0a. `_extract_element_body` C# branch** (REQ-CS-MP-100)
Add `if lang_id == "csharp":` branch that calls `parse_csharp()` and extracts body bytes. ~20 lines. Immediately stops the wasteful Python AST fallback cycle.

**0b. Kaizen postmortem mappings** (REQ-CS-MP-400, 401)
Add 9 entries to `CAUSE_TO_SUGGESTION` and `_SEMANTIC_CATEGORY_TO_SUGGESTION`. ~30 lines, 18 dict entries. Enables C# feedback loop.

**0c. Compliance results storage** (REQ-CS-MP-500)
Wire C# semantic results into `compliance_results`. ~10 lines. Required for 0b to have data.

### Phase 1: Skeleton Assembly (~4 hours)

**1a. `CSharpDeterministicFileAssembler`** (REQ-CS-MP-200)
New file: `utils/csharp_file_assembler.py`. Produces compilable C# skeletons from `ForwardFileSpec`. ~200-300 lines. Template: `JavaDeterministicFileAssembler`.

**1b. Wire into prime_adapter.py** (REQ-CS-MP-200)
Add `.cs` handler in skeleton generation loop. ~30 lines.

**1c. `using` resolution** (REQ-CS-MP-201)
Wire `ForwardFileSpec.prescribed_imports` + `framework_imports` into skeleton. ~50 lines.

### Phase 2: Full Element-Level Pipeline (~2 hours)

**2a. Expression-bodied member extraction** (REQ-CS-MP-600)
Add `arrow_expression_clause` handling to `csharp_parser.py`. ~40 lines.

**2b. `CSharpElement` field parity** (REQ-CS-MP-601)
Add `doc_comment`, `is_exported`, `bases`, `type_annotation` to `CSharpElement`. ~60 lines.

**2c. Source → ForwardElementSpec converter**
Convert `CSharpElement` → `ForwardElementSpec` for forward manifest population from source code (not just LLM signatures). ~80 lines.

### Phase 3: Additional Repair Steps (future)

**3a. `csharp_contamination_strip`** — Remove Python/Go/Node fingerprints from C# files.
**3b. `csharp_using_fix`** — Add missing `using` directives based on `check_using_coverage()` results.
**3c. Expanded semantic repair routes** — Wire the 8 unrepaired semantic categories.

---

## 10. Verification Strategy

### Unit Tests

| Test | Validates | File |
|------|-----------|------|
| `test_extract_element_body_csharp` | REQ-CS-MP-100: body extraction via tree-sitter | `tests/unit/micro_prime/test_csharp_element_extraction.py` |
| `test_extract_body_fallback_regex` | REQ-CS-MP-100: regex fallback when tree-sitter unavailable | Same |
| `test_extract_body_overload_disambiguation` | REQ-CS-MP-300: same-name methods on different classes | Same |
| `test_extract_expression_bodied` | REQ-CS-MP-600: `=> expr;` extraction | Same |
| `test_skeleton_produces_compilable_cs` | REQ-CS-MP-200: skeleton has namespace, usings, stubs | `tests/unit/micro_prime/test_csharp_skeleton.py` |
| `test_skeleton_ilogger_injection` | REQ-CS-MP-200: service classes get ILogger constructor | Same |
| `test_skeleton_file_scoped_namespace` | REQ-CS-MP-200: never block-scoped | Same |
| `test_kaizen_csharp_category_mappings` | REQ-CS-MP-400: all 9 categories have suggestions | `tests/unit/contractors/test_csharp_kaizen_suggestions.py` |
| `test_compliance_results_stored` | REQ-CS-MP-500: C# semantic results in compliance_results | `tests/unit/contractors/test_csharp_compliance_results.py` |

### Integration Tests

| Test | Validates |
|------|-----------|
| `test_csharp_microprime_element_level` | Full pipeline: skeleton → decompose → generate → splice → validate |
| `test_csharp_microprime_fallback_escalation` | Graceful escalation when element generation fails |
| `test_csharp_kaizen_suggestions_generated` | Post-mortem produces C#-specific suggestions |
