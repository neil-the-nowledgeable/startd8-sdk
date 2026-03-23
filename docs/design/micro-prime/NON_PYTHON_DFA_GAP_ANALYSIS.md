# Non-Python Deterministic File Assembly & MicroPrime — Gap Analysis

> **Version:** 2.0.0
> **Date:** 2026-03-23
> **Status:** REQUIREMENTS (revised after plan-informed review)
> **Review:** [NON_PYTHON_DFA_REQUIREMENTS_REVIEW.md](NON_PYTHON_DFA_REQUIREMENTS_REVIEW.md) — insights from implementation planning
> **Scope:** Language-agnostic structural gaps in the DFA → MicroPrime → LLM pipeline for non-Python languages (C#, Go, Java, Node.js)
> **Evidence:** Run-106 (C#, online-boutique cartservice) — MicroPrime fully bypassed, 15/15 features via pure LLM file-whole generation at $2.38
> **Related:** [KAIZEN_CSHARP_REQUIREMENTS.md](../prime-contractor-csharp/KAIZEN_CSHARP_REQUIREMENTS.md), [MICRO_PRIME_REQUIREMENTS.md](MICRO_PRIME_REQUIREMENTS.md)

---

## Table of Contents

1. [Current Architecture](#1-current-architecture)
2. [The Pipeline Gap](#2-the-pipeline-gap)
3. [Language-Agnostic Gaps](#3-language-agnostic-gaps)
4. [Deterministic File Categories](#4-deterministic-file-categories)
5. [Skeleton → Fill Opportunity](#5-skeleton--fill-opportunity)
6. [Cost & Quality Impact Model](#6-cost--quality-impact-model)
7. [Requirements](#7-requirements)
8. [Per-Language Gap Summary](#8-per-language-gap-summary)

---

## 1. Current Architecture

### 1.1 What Exists

The pipeline has four tiers of code generation, from cheapest to most expensive:

```
Tier 0: Deterministic File Assembly (DFA)     $0.00   — templates, project files
Tier 1: MicroPrime Template Match (TRIVIAL)   $0.00   — known patterns (health check, __init__.py)
Tier 2: MicroPrime Local LLM (SIMPLE)         ~$0.001 — Ollama/Haiku element generation
Tier 3: Cloud LLM File-Whole (MODERATE+)      ~$0.15  — Sonnet/Opus full-file generation
```

### 1.2 What's Implemented Per Language

| Component | Python | C# | Go | Java | Node.js |
|-----------|--------|----|----|------|---------|
| **LanguageProfile** | Full | Full | Full | Full | Full |
| **DFA assembler** | `DeterministicFileAssembler` | `CSharpDeterministicFileAssembler` | None | `JavaDeterministicFileAssembler` | `NodejsDeterministicFileAssembler` |
| **Parser** | AST (`ast.parse`) | tree-sitter + regex | regex (`go_parser.py`) | regex | regex |
| **Splicer** | AST-based | tree-sitter byte-offset | text-based brace matching | None | None |
| **ForwardManifest elements** | Populated from existing source | **Empty** (parser exists, not wired) | **Empty** (parser wired to contracts only) | **Empty** (parser exists, not wired) | **Empty** (parser exists, not wired) |
| **MicroPrime element routing** | Full (TRIVIAL→SIMPLE→MODERATE→COMPLEX) | **Bypassed** (DFA + templates exist unused) | **Bypassed** (7 templates unused) | **Bypassed** (DFA + 8 templates unused) | **Bypassed** (DFA + 6 templates unused) |
| **Template registry** | ~20 templates | **8 templates** (unused) | **7 templates** (unused) | **8 templates** (unused) | **6 templates** (unused) |
| **Skeleton → Fill mode** | Supported | **Implemented, not triggered** | **Splicer ready, not triggered** | **Implemented, not triggered** | **No splicer** |
| **Semantic repair** | Full pipeline | 2 steps + routing | 2 steps + routing | Full routing | **5 steps + routing** |

### 1.3 The Python-Only Bottleneck

MicroPrime's element-level pipeline (classify → decompose → route → generate → splice) runs **only for Python** because:

1. The ForwardManifest extractor uses `ast.parse()` — Python only
2. Element classification requires parsed function/class signatures
3. Template matching requires element-level granularity
4. The splicer replaces individual function bodies in existing files

For all other languages, the pipeline collapses to:
```
Plan → file_specs (elements: []) → DFA returns None → LLM file-whole ($0.15/file)
```

---

## 2. The Pipeline Gap

### 2.1 Evidence: Run-106 (C#)

| Metric | Expected (with DFA) | Actual (without DFA) |
|--------|---------------------|---------------------|
| Files with DFA skeletons | 9 .cs + 2 .csproj + 1 .sln = 12 | **0** |
| MicroPrime element classifications | ~30-40 methods | **0** |
| Template hits (TRIVIAL) | 2-3 (health check, .csproj, .sln) | **0** |
| Skeleton → Fill drafts | 9 .cs files | **0** |
| Pure LLM file-whole generations | 3-5 (complex files only) | **15** |
| Total cost | ~$1.00 | **$2.38** |
| Namespace correctness | 100% (DFA enforces) | **89%** (1 missing) |
| ILogger<T> injection | 100% (DFA scaffolds) | **44%** (5/9 missing) |

### 2.2 The Root Cause Chain

```
ForwardManifest extractor → only parses Python AST
    ↓
file_specs have elements: [] for non-Python
    ↓
DFA.render_file() → None (no elements to render)
    ↓
MicroPrime classifier → no elements to classify
    ↓
Template registry → no elements to match
    ↓
Fallback: LLM file-whole generation for EVERY file
    ↓
Result: $0.15/file × 15 files = $2.38, with quality gaps
```

---

## 3. Language-Agnostic Gaps

These gaps apply to ALL non-Python languages equally.

### GAP-DFA-1: No Plan-to-Element Derivation

**Problem:** The ForwardManifest gets elements only from existing source files (via `ast.parse`). For greenfield projects, there are no existing files. For non-Python, there's no parser that populates elements.

**Impact:** DFA assemblers exist but have nothing to assemble.

**Requirement:** A plan-to-element pipeline that derives `ForwardElementSpec` entries from feature descriptions and task metadata — without parsing source code.

**Input available today:**
- Feature name: "SpannerCartStore"
- Feature description: "Implements ICartStore with Spanner backend for AddItem, EmptyCart, GetCart"
- Target file: `src/cartservice/src/cartstore/SpannerCartStore.cs`
- Interface contract (from ForwardManifest `contracts`): method signatures

**Output needed:**
```json
{
  "file": "src/cartservice/src/cartstore/SpannerCartStore.cs",
  "elements": [
    {"name": "SpannerCartStore", "kind": "class", "bases": ["ICartStore"]},
    {"name": "AddItemAsync", "kind": "method", "parent_class": "SpannerCartStore",
     "signature": {"params": [{"name": "userId", "annotation": "string"}, ...]}},
    {"name": "EmptyCartAsync", "kind": "method", ...},
    {"name": "GetCartAsync", "kind": "method", ...},
    {"name": "Ping", "kind": "method", ...}
  ],
  "imports": ["Google.Cloud.Spanner.Data", "Grpc.Core", ...]
}
```

### GAP-DFA-2: No Deterministic Routing for Build/Config Files

**Problem:** Files that are 100% deterministic (.csproj, .sln, go.mod, package.json, Dockerfile, .proto) are sent to the LLM at $0.15/file. The SDK already has generators for most of these (`generate_dependency_file()`, `generate_solution_file()`).

**Impact:** Wasted LLM cost + lower quality (LLM omits `<Nullable>enable</Nullable>`, generates wrong go.mod versions, etc.).

**Requirement:** A routing decision BEFORE the LLM that checks:
1. Is this file type fully deterministic? → Tier 0 (DFA, $0.00)
2. Is this file type template-matchable? → Tier 1 (template, $0.00)
3. Does a DFA skeleton exist? → skeleton_fill mode ($0.05)
4. Otherwise → LLM file-whole ($0.15)

### GAP-DFA-3: Skeleton → Fill Mode Not Triggered for Non-Python

**Problem:** The `skeleton_fill` drafter mode exists (FR-MPA-005) and is wired into the prompt pipeline. But it's never activated for non-Python because DFA skeletons are never produced (GAP-DFA-1).

**Impact:** Even when partial DFA output is available, the LLM regenerates the entire file from scratch instead of filling stubs.

**Requirement:** When a DFA assembler produces a skeleton with `// [STARTD8-SKELETON]` marker and `throw new NotImplementedException()` stubs, the drafter MUST use `skeleton_fill` mode.

### GAP-DFA-4: No Template Registry for Non-Python

**Problem:** The `TemplateRegistry` has ~20 Python templates (health checks, `__init__.py`, simple getters, etc.). Zero templates for C#, Go, Java, or Node.js.

**Impact:** TRIVIAL-tier work items that could be generated deterministically ($0.00) go to the LLM ($0.15).

**Requirement:** Per-language template registries for common patterns:
- Health check endpoints (every language has one)
- Configuration/options classes
- DI registration (C# Startup.cs, Java @Configuration, Node.js container)
- Test scaffolds (xUnit [Fact], JUnit @Test, Jest describe/it)
- Interface definitions (method signatures only, no body)

### GAP-DFA-5: No Interface-Aware Element Derivation

**Problem:** Interface files (C# `ICartStore.cs`, Go interfaces, Java interfaces, TypeScript `.d.ts`) have no bodies — they're pure signatures. The DFA could generate these 100% deterministically from the ForwardManifest contracts. But contracts aren't connected to element derivation.

**Impact:** Run-106 ICartStore.cs was generated by LLM and got the WRONG content (class instead of interface).

**Requirement:** When a target file matches an interface pattern (I-prefix for C#, `_interface` suffix, `.d.ts` for TypeScript), derive elements from the ForwardManifest `contracts` section and generate the interface deterministically.

### GAP-DFA-6: No Constructor DI Scaffold from Metadata

**Problem:** Service classes in modern frameworks universally use constructor injection. The seed metadata has `framework_imports` that imply which DI parameters are needed (e.g., `ILogger<T>`, `ICartStore`, `IConfiguration`). But this information isn't used to populate constructor elements.

**Impact:** LLM-generated code frequently uses `Console.WriteLine` instead of `ILogger<T>` because the constructor scaffold doesn't enforce DI patterns.

**Requirement:** When the LanguageProfile's `framework_imports` are detected AND the file is a service class, the DFA should scaffold a constructor with framework-appropriate DI parameters.

### GAP-DFA-7: No Namespace/Package Derivation in File Specs

**Problem:** Every language has a namespace/package/module declaration that must match the directory structure. The DFA assemblers all have `_derive_namespace()` functions. But they can't run because `file_specs` have empty elements, so `render_file()` returns `None` before reaching namespace derivation.

**Impact:** Namespace mismatches (run-106: lowercase `cartservice.cartstore` vs PascalCase convention), missing namespaces (Program.cs), wrong package declarations.

**Requirement:** Even when `elements: []`, the DFA should produce a minimal skeleton with:
1. Correct namespace/package declaration
2. Using/import directives from `file_spec.imports`
3. Empty class/struct shell with the correct name (derived from filename)

---

## 4. Deterministic File Categories

Files that should NEVER go to the LLM:

| File Type | Languages | Generator | Cost Savings |
|-----------|-----------|-----------|-------------|
| **Dependency manifest** | .csproj, go.mod, package.json, build.gradle | `generate_dependency_file()` | ~$0.10/file |
| **Solution/workspace** | .sln, go.work, pnpm-workspace.yaml | `generate_solution_file()` | ~$0.10/file |
| **Interface definition** | IFoo.cs, .d.ts, Go interface files | DFA from contracts | ~$0.15/file |
| **Proto definition** | .proto | Template with package + service name | ~$0.10/file |
| **Dockerfile** | Dockerfile | Template with 3-5 variables | ~$0.12/file |
| **Config files** | appsettings.json, .env, config.yaml | Template/literal | ~$0.08/file |
| **Test scaffold** | *Tests.cs, *_test.go, *.test.ts | DFA with test framework setup | ~$0.10/file |

**Estimated savings per run:** 4-6 deterministic files × ~$0.10 = $0.40-$0.60 (20-25% of typical run cost).

---

## 5. Skeleton → Fill Opportunity

For files that ARE partially deterministic (namespace + imports + constructor + stubs), the skeleton → fill mode saves cost by giving the LLM a structured starting point instead of generating from scratch.

**Skeleton (deterministic, $0.00):**
```
namespace {derived};
using {framework_imports};

public class {ClassName} : {interfaces}
{
    private readonly ILogger<{ClassName}> _logger;
    // ... DI fields from framework detection

    public {ClassName}({DI_params})
    {
        _logger = logger;
        throw new NotImplementedException();
    }

    public async Task<Cart> GetCartAsync(string userId)
    {
        throw new NotImplementedException();
    }
    // ... method stubs from interface contract
}
```

**LLM fill ($0.05-$0.08 — only method bodies):**
```
Replace `throw new NotImplementedException();` in GetCartAsync with:
    var cart = await _store.GetAsync(userId);
    return cart ?? new Cart { UserId = userId };
```

**Expected savings:** 40-60% token reduction (skeleton provides ~40% of the final file).

---

## 6. Cost & Quality Impact Model

### Cost Projection (15-feature C# run)

| Routing | Files | Tier | Cost/File | Total |
|---------|-------|------|-----------|-------|
| Current (all LLM) | 15 | T3 | $0.16 | **$2.38** |
| With Tier 0 routing | 5 deterministic | T0 | $0.00 | $0.00 |
| With skeleton_fill | 7 .cs files | T3 (fill) | $0.08 | $0.56 |
| Complex files (LLM) | 3 files | T3 | $0.16 | $0.48 |
| **Projected total** | 15 | Mixed | — | **$1.04** |

**Savings: ~56% ($1.34/run)**

### Quality Projection

| Defect | Current (LLM-only) | With DFA + Skeleton |
|--------|--------------------|--------------------|
| Missing namespace | 1/9 files | **0** (DFA enforces) |
| Wrong type in interface file | 1/1 interface | **0** (DFA derives from contract) |
| Missing ILogger<T> | 5/9 files | **0** (DFA scaffolds) |
| Lowercase namespaces | 8/9 files | **0** (DFA PascalCase) |
| Missing Nullable in csproj | 1/1 csproj | **0** (generator includes it) |
| Disorganized usings | ~5 files | **0** (DFA 2-tier ordering) |

---

## 7. Requirements

### REQ-DFA-100: Plan-to-Element Derivation (Language-Agnostic)

The plan ingestion pipeline SHALL derive `ForwardElementSpec` entries from feature metadata for non-Python languages when no existing source files are available for parsing.

**Input sources (priority order):**
1. ForwardManifest `contracts` → method signatures for interface implementations
2. Feature `description` → NLP extraction of class/method names
3. Feature `target_files` → filename-to-type derivation (ICartStore.cs → interface ICartStore)
4. LanguageProfile `framework_imports` → DI constructor parameters

**Acceptance criteria:**
- After plan ingestion, `file_specs[path].elements` is non-empty for .cs, .go, .java, .ts files
- Element `kind` is correctly set (class, interface, method, constructor)
- Element `imports` is populated from LanguageProfile `framework_imports`

### REQ-DFA-101: Deterministic File Routing

The Prime Contractor SHALL route files to the cheapest sufficient tier:

| Condition | Tier | Cost |
|-----------|------|------|
| File type has a `generate_*` method on LanguageProfile | Tier 0 | $0.00 |
| File matches a TemplateRegistry entry | Tier 1 | $0.00 |
| DFA assembler produces a skeleton with stubs | skeleton_fill | ~$0.05 |
| None of the above | LLM file-whole | ~$0.15 |

**Acceptance criteria:**
- .csproj, .sln, go.mod, package.json, build.gradle never go to LLM
- Dockerfiles use template with variable substitution
- Interface files derived from contracts
- Routing decision logged with tier and rationale

### REQ-DFA-102: Minimal Skeleton Even Without Elements

When `file_specs[path].elements` is empty but the file is a recognized source extension (.cs, .go, .java, .ts), the DFA SHALL produce a minimal skeleton containing:
1. Namespace/package declaration (derived from file path)
2. Import/using directives (from `file_spec.imports` or LanguageProfile defaults)
3. Type shell (class/interface/struct name derived from filename)

**Acceptance criteria:**
- A .cs file with `elements: []` still gets `namespace X; public class Y { }` skeleton
- A .go file with `elements: []` still gets `package x` skeleton
- The skeleton uses `skeleton_fill` drafter mode

### REQ-DFA-103: Non-Python Template Registry Expansion

**Status update:** The agent audit found **29 templates already exist** (C#: 8, Go: 7, Java: 8, Node.js: 6). These are IMPLEMENTED and ACTIVE in the `TemplateRegistry` but never fire because element classification never runs (blocked by REQ-DFA-100).

**Remaining gaps — templates that should be added:**

| Language | Missing Template | Pattern |
|----------|-----------------|---------|
| C# | Health check endpoint (IHealthCheck) | `Check()` → `HealthCheckResult.Healthy()` |
| C# | Options/config class | Auto-properties from config schema |
| Go | Health check handler | `http.HandleFunc("/healthz", ...)` |
| Go | gRPC server startup | `grpc.NewServer()` + listener |
| Java | @Configuration class | Spring DI wiring |
| Java | @RestController scaffold | Spring MVC handler methods |
| Node.js | Express app scaffold | `express()` + middleware + listen |

**Acceptance criteria:**
- Existing 29 templates start matching once elements flow (REQ-DFA-100)
- At least 2 additional templates per language for framework-level scaffolds
- `TemplateRegistry.is_trivial()` returns True for health check patterns in all 4 languages

### REQ-DFA-104: Interface-from-Contract Generation

When a target file matches an interface pattern AND ForwardManifest contracts contain method signatures applicable to that file, the DFA SHALL generate the interface deterministically.

**Interface patterns:**
- C#: `I{Name}.cs` (I-prefix convention)
- Go: `{name}.go` with only interface type declarations
- Java: `{Name}.java` with `interface` keyword in description
- TypeScript: `{name}.d.ts` or `I{Name}.ts`

**Acceptance criteria:**
- Interface files have correct method signatures from contracts
- No LLM call required for interface generation
- Generated interface passes language-specific syntax validation

### REQ-DFA-105: Go Deterministic File Assembler

A `GoDeterministicFileAssembler` SHALL be created following the pattern of `CSharpDeterministicFileAssembler` and `JavaDeterministicFileAssembler`.

Go is the only language without a DFA assembler. The infrastructure exists:
- `go_parser.py` extracts functions, methods, types, interfaces (regex-based)
- `go_splicer.py` has `GO_SKELETON_SENTINEL` and stub patterns defined
- `go_parser.py` is already wired into `forward_manifest_extractor.py` for contract reconciliation

**Skeleton output must include:**
1. `package {name}` declaration (derived from directory)
2. Import block with stdlib/third-party grouping
3. Type declarations (struct/interface) with embedded types
4. Function/method stubs with `panic("not implemented")` bodies
5. `// [STARTD8-SKELETON]` sentinel marker

**Acceptance criteria:**
- `GoDeterministicFileAssembler.render_file()` produces valid Go source
- Passes `gofmt -e` validation
- Integrates with `go_splicer.py` for stub body replacement
- Registered in `prime_adapter.py` alongside Java/C#/Node.js assemblers

### REQ-DFA-106: Dockerfile Template Generation

Each LanguageProfile SHALL provide a `generate_dockerfile()` method that produces a multi-stage Dockerfile from 3-5 variables (service name, port, entry point).

**Current state:** All 4 languages define `docker_base_image` and `docker_runtime_image` properties. `build_project_context_section()` injects Dockerfile guidance into LLM prompts. But no method generates actual Dockerfile content.

**Templates per language:**

| Language | Builder Image | Runtime Image | Build Command | Pattern |
|----------|--------------|---------------|---------------|---------|
| C# | `mcr.microsoft.com/dotnet/sdk:10.0` | `runtime-deps:10.0-chiseled` | `dotnet publish -c release --self-contained` | restore-first, USER 1000 |
| Go | `golang:1.25-alpine` | `gcr.io/distroless/static` | `CGO_ENABLED=0 go build` | mod-download-first, SKAFFOLD_GO_GCFLAGS |
| Java | `eclipse-temurin:21-jdk` | `eclipse-temurin:21-jre-alpine` | `gradle build` or `mvn package` | restore-first, jar execution |
| Node.js | `node:20-alpine` | `node:20-alpine` | `npm install --only=production` | copy-package-first, non-root |

**Acceptance criteria:**
- `profile.generate_dockerfile(service_name, port, entry_point)` returns valid Dockerfile content
- Output uses multi-stage build (builder → runtime)
- Output follows the language's established pattern from `build_project_context_section()`
- Routed as Tier 0 (deterministic, $0.00) by REQ-DFA-101

### REQ-DFA-107: Skeleton → Fill Activation Wiring

The `skeleton_fill` drafter mode (FR-MPA-005) is fully implemented but never activates for non-Python because DFA skeletons are never produced. Once REQ-DFA-100 populates elements and DFA assemblers produce skeletons, the drafter MUST be wired to use `skeleton_fill` mode.

**Current state:** The drafter checks for `skeleton_sources` and `element_tiers` in the pipeline context. These are never set for non-Python.

**Acceptance criteria:**
- When a DFA assembler produces a skeleton with `// [STARTD8-SKELETON]` marker, the context includes `skeleton_sources[file_path] = skeleton_content`
- The drafter selects `skeleton_fill` mode when `skeleton_sources` is non-empty
- The LLM receives the skeleton as context and fills only stub method bodies
- Token usage is reduced by ~40-60% compared to file-whole generation

### REQ-DFA-108: Parser-to-ForwardManifest Bridge (Key Unblocking Fix)

This is the **single highest-priority requirement** — all other DFA/MicroPrime capabilities are blocked by empty `file_specs[].elements`.

A language-dispatched element deriver SHALL populate `ForwardElementSpec` entries from feature metadata during plan ingestion.

**Dispatch table:**

| Extension | Parser | Element Types Derived |
|-----------|--------|----------------------|
| `.cs` | `csharp_parser.py` (tree-sitter) | class, interface, method, constructor, property |
| `.go` | `go_parser.py` (regex) — **already wired to FM** | function, method, type (struct/interface) |
| `.java` | `java_parser.py` (javalang + regex) | class, interface, method, constructor, field |
| `.js`/`.ts` | `nodejs_parser.py` (regex) | class, function, method, TypeScript interface |

**For greenfield projects (no existing source):**

When no existing source files are available, elements SHALL be derived from:
1. **Target filename** → primary type name (e.g., `CartStore.cs` → `class CartStore`)
2. **FM contracts** → method signatures for interface implementations
3. **Feature description** → keyword extraction for method names
4. **LanguageProfile.framework_imports** → using/import directives + DI constructor params

**Acceptance criteria:**
- After plan ingestion, `file_specs[path].elements` has ≥1 entry for each .cs/.go/.java/.ts file
- Element `kind` matches language conventions (class for C#/Java, struct for Go, etc.)
- Element `imports` populated from framework detection
- Go files benefit immediately (parser already wired)
- C#/Java/Node.js files get elements from filename + contract derivation

---

## 8. Per-Language Gap Summary (Agent Findings)

### 8.1 Corrected Capability Matrix

The agent audit revealed **significantly more implementation** than initially assumed. The table from Section 1.2 was wrong — here's the corrected matrix:

| Component | Python | C# | Go | Java | Node.js |
|-----------|--------|----|----|------|---------|
| **LanguageProfile** | Full | Full | Full | Full | Full |
| **DFA assembler** | `DeterministicFileAssembler` | `CSharpDFA` | **MISSING** | `JavaDFA` | `NodejsDFA` |
| **Parser** | AST | tree-sitter + regex | regex | javalang + regex | regex |
| **Splicer** | AST-based | tree-sitter byte-offset | text-based brace | text-based brace | None |
| **Template registry** | ~20 | **8** | **7** | **8** | **6** |
| **Semantic checks** | Full | 12 checks | 10 checks | 12 checks | 7 checks |
| **Semantic repair** | Full | Dispatch + 2 steps | Dispatch + 2 steps | Dispatch + steps | **5 steps** |
| **Dep file generator** | Yes | Yes (.csproj) | Yes (go.mod) | Yes (build.gradle) | Yes (package.json) |
| **Solution/workspace gen** | N/A | Yes (.sln) | No | No | Yes (tsconfig) |
| **Dockerfile generator** | N/A | **No** (context only) | **No** (context only) | **No** (images only) | **No** (context only) |
| **FM element extraction** | AST-based | **Parser exists, not wired** | **Parser wired** (!) | **Parser exists, partial** | **Parser exists** |
| **Skeleton → Fill mode** | Active | **IMPLEMENTED_UNUSED** | **IMPLEMENTED_UNUSED** | **IMPLEMENTED_UNUSED** | **IMPLEMENTED_UNUSED** |

### 8.2 Key Surprise: Templates Already Exist

All four languages have templates in the MicroPrime `TemplateRegistry`:

| Language | Templates | Examples |
|----------|-----------|---------|
| **C#** (8) | DI constructor, property, Equals, GetHashCode, ToString, Dispose, async method, plain constructor |
| **Go** (7) | Constructor (NewFoo), Stringer, Error, Close, getter, setter, main |
| **Java** (8) | Getter, setter, constructor, Equals, hashCode, toString, builder, Spring Boot main |
| **Node.js** (6) | Constructor, toString, getter, setter, async method, Express handler |

These templates are **IMPLEMENTED and ACTIVE** in the registry — they just never fire because the upstream element classification never runs for non-Python (GAP-DFA-1 blocks everything).

### 8.3 Key Surprise: Go Parser Already Wired to ForwardManifest

The `go_parser.py` is already integrated into `forward_manifest_extractor.py` (lines 1515-1573) via `_reconcile_go_file()`. This means Go has the closest path to full MicroPrime activation — the parser populates contracts, but the contracts aren't converted to `file_specs[].elements`.

### 8.4 Per-Language Specific Gaps

#### C# — CLOSEST TO ACTIVATION
- **Blocker:** ForwardManifest extractor doesn't call `csharp_parser.py` to populate elements
- **DFA assembler:** Fully functional, produces correct skeletons when elements provided
- **Splicer:** tree-sitter byte-offset — most precise non-Python splicer
- **Repair:** 2 steps (convention fix, syntax validate) + sql_parameterize registered
- **Missing:** No Dockerfile generator, no `generate_dockerfile()` method
- **Quick win:** Wire csharp_parser into FM extractor → DFA skeletons → skeleton_fill mode

#### Go — PARSER ALREADY WIRED
- **Blocker:** No `GoDeterministicFileAssembler` class (needs creation)
- **Parser:** Already wired to FM extractor for contract reconciliation
- **Splicer:** Text-based brace matching, `GO_SKELETON_SENTINEL` defined
- **Repair:** 2 steps (syntax validate, unchecked error fix)
- **Missing:** DFA assembler class, Dockerfile template
- **Quick win:** Create `GoDeterministicFileAssembler` following Java/C# pattern; Go is ~40 lines since parser/splicer infra exists

#### Java — MOST COMPLETE NON-PYTHON
- **Blocker:** ForwardManifest extractor doesn't call `java_parser.py`
- **DFA assembler:** Full implementation with package derivation, 2-tier imports
- **Splicer:** Text-based brace matching with javalang validation
- **Parser:** Hybrid javalang AST + regex fallback — most capable non-Python parser
- **Repair:** Full routing + semantic checks (12 checks)
- **Missing:** No Dockerfile generator, no Spring @Configuration template
- **Note:** Marked "lowest payoff (1 service)" in code comment — Java generation volume is low

#### Node.js — BROADEST FRAMEWORK SUPPORT
- **Blocker:** ForwardManifest extractor doesn't call `nodejs_parser.py`
- **DFA assembler:** Full ESM/CJS-aware skeleton generation
- **Parser:** Regex-based but covers TypeScript interfaces + async patterns
- **Splicer:** **MISSING** — No body-level splicing (only file-whole)
- **Repair:** 5 steps (eslint-autofix, var-to-const, dedup-require, contamination strip, syntax validate)
- **Missing:** No .d.ts generation, no Express/Fastify scaffold templates, no splicer
- **Extra:** Has `generate_tsconfig()` for TypeScript projects

### 8.5 The Single Unblocking Fix

**All four languages share the same root cause:** `ForwardManifest file_specs` have `elements: []` for non-Python files.

The fix is **one function** — a language-dispatched element deriver in plan ingestion that:
1. Parses feature description + target file path + contracts
2. Calls the language-specific parser (which exists for all 4 languages)
3. Populates `file_specs[path].elements` with `ForwardElementSpec` entries
4. Populates `file_specs[path].imports` from `LanguageProfile.framework_imports`

Once elements are populated:
- DFA assemblers produce skeletons (already implemented for C#, Java, Node.js)
- Template registry matches TRIVIAL elements (29 templates ready across 4 languages)
- Skeleton_fill drafter mode activates (already implemented)
- Splicers fill stub bodies (implemented for C#, Go, Java)

**Estimated effort:** ~100-150 lines for the element deriver + ~40 lines for Go DFA assembler.
**Estimated impact:** 40-60% cost reduction on non-Python runs; elimination of namespace/package/import structural defects.
