# Non-Python DFA & MicroPrime — Implementation Plan

> **Requirements:** [NON_PYTHON_DFA_GAP_ANALYSIS.md](NON_PYTHON_DFA_GAP_ANALYSIS.md) (REQ-DFA-100 through 108)
> **Review:** [NON_PYTHON_DFA_REQUIREMENTS_REVIEW.md](NON_PYTHON_DFA_REQUIREMENTS_REVIEW.md)
> **Date:** 2026-03-23 (v2 — revised after plan-informed requirements review)
> **Estimated scope:** ~350 lines across 8 files + ~150 lines of tests
> **Evidence:** Run-106 (C#, $2.38 all-LLM) → projected $1.04 with DFA (56% savings)

---

## Implementation Order (REVISED)

**Key insight from requirements review:** The original Phase 1 (element deriver, ~150 lines) is NOT the critical-path blocker. DFA assemblers already produce useful skeletons with empty elements. The real blocker is a **5-line context injection** that activates skeleton_fill mode.

```
Phase 0: Quick wins — 20 lines      (REQ-DFA-107a, 101a, 104a)  ← NEW
Phase 1: Fill the Go gap + Docker   (REQ-DFA-105, 106)
Phase 2: Element enrichment          (REQ-DFA-108, 100, 107b)
Phase 3: Template + interface polish (REQ-DFA-103, 104b)
Phase 4: Validate end-to-end
```

### Phase 0: Quick Wins (~20 lines, one commit)

Three zero-risk fixes that activate existing infrastructure:

**0A.** `prime_adapter.py` — inject `context["skeleton_sources"]` from DFA output (~5 lines)
**0B.** `prime_contractor.py` — skip LLM for features with deterministic build files (~10 lines)
**0C.** `csharp_file_assembler.py` — detect interface from `I`-prefix filename (~5 lines)

**Impact:** skeleton_fill activates for C#/Java/Node.js; build files stop going to LLM; ICartStore.cs defect class eliminated.

---

## Phase 1: Unblock the Pipeline (~150 lines)

**Goal:** Make ForwardManifest elements non-empty for non-Python → DFA assemblers produce skeletons → skeleton_fill mode activates.

### Step 1.1 — Element Deriver: Filename + Contract → ForwardElementSpec (REQ-DFA-108)

**File:** `src/startd8/seeds/element_deriver.py` (NEW)

This is the key unblocking function. It derives elements when no existing source exists to parse.

```python
def derive_elements_from_metadata(
    file_path: str,
    feature_description: str,
    contracts: List[InterfaceContract],
    framework_imports: Dict[str, Any],
    language_id: str,
) -> Tuple[List[ForwardElementSpec], List[str]]:
    """Derive elements and imports from feature metadata.

    Returns (elements, import_strings).
    """
```

**Logic:**
1. Derive primary type name from filename (`CartStore.cs` → `CartStore`)
2. Detect interface files (C# `I`-prefix, Java `Interface` suffix, `.d.ts`)
3. Match contracts to this file (by `applicable_task_ids` or name match)
4. Extract method signatures from matching contracts → method elements
5. Add constructor element with DI params from `framework_imports`
6. Collect import strings from framework detection

**Effort:** ~80 lines

### Step 1.2 — Wire Deriver into Seed Builder (REQ-DFA-108)

**File:** `src/startd8/seeds/builder.py` (modify `derive_tasks` or new method)

After `derive_tasks_from_features()`, iterate `file_specs` and call `derive_elements_from_metadata()` for each non-Python file with empty elements.

```python
def enrich_forward_manifest_elements(self) -> "SeedBuilder":
    """Populate ForwardElementSpec entries for non-Python files."""
    if not self._forward_manifest:
        return self
    for file_path, file_spec in self._forward_manifest.get("file_specs", {}).items():
        if file_spec.get("elements"):
            continue  # Already populated (Python AST extraction)
        ext = Path(file_path).suffix
        if ext not in (".cs", ".go", ".java", ".js", ".ts"):
            continue
        lang_id = _EXT_TO_LANG.get(ext, "")
        elements, imports = derive_elements_from_metadata(...)
        file_spec["elements"] = [e.model_dump() for e in elements]
        file_spec["imports"] = imports
    return self
```

**Effort:** ~30 lines

### Step 1.3 — Minimal Skeleton Without Elements (REQ-DFA-102)

**File:** Modify DFA assemblers: `csharp_file_assembler.py`, `java_file_assembler.py`, `nodejs_file_assembler.py`

Currently `render_file()` returns `None` when elements are empty (after the type-element check). Change to produce a minimal skeleton with namespace + class shell.

**C# example (csharp_file_assembler.py ~line 328):**
```python
# Current:
if not type_elements:
    class_body = self._render_members(member_elements, class_name)
    sections.append(f"public class {class_name}\n{{\n{class_body}\n}}")

# Already handles empty elements — produces default class!
```

Wait — the C# assembler already handles empty elements (line 328-331). It creates a default `public class {ClassName}`. The issue is that `render_file()` is never called because the prime_adapter checks `file_spec is None` or elements are empty before calling the assembler. Let me check...

Actually, from the agent report: the DFA IS called for C# files, but `render_file()` returns `None` because it checks `if not file_path.endswith(".cs"): return None` — that's fine. The real issue is that `file_spec` has `elements: []`, so the code at line 328 executes and produces an empty class body. This should actually work!

The problem must be that `render_file()` returns `None` at line 292-295 when it's not a `.cs` file. For actual `.cs` files, it should proceed. Let me verify by checking what happens when elements AND imports are both empty — the assembler should still produce `namespace + class shell`.

**Fix needed:** Ensure the skeleton is flagged for `skeleton_fill` mode downstream.

**Effort:** ~10 lines (add `skeleton_sources` context injection in prime_adapter)

### Step 1.4 — Skeleton → Fill Activation (REQ-DFA-107)

**File:** `src/startd8/micro_prime/prime_adapter.py` (modify skeleton generation section)

When a DFA assembler produces a skeleton, inject it into `context["skeleton_sources"]`:

```python
# After skeleton generation (line ~1863)
if cs_source:
    skeletons[file_path] = cs_source
    # REQ-DFA-107: Enable skeleton_fill drafter mode
    context.setdefault("skeleton_sources", {})[file_path] = cs_source
```

This activates the existing `skeleton_fill` detection in the drafter.

**Effort:** ~15 lines (add to all 4 language skeleton blocks)

---

## Phase 2: Go DFA Assembler (~50 lines) (REQ-DFA-105)

**File:** `src/startd8/utils/go_file_assembler.py` (NEW)

Follow the pattern of `CSharpDeterministicFileAssembler` but with Go conventions:

```python
class GoDeterministicFileAssembler:
    GO_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
    GO_STUB_BODY = 'panic("not implemented")'

    def render_file(self, file_spec) -> Optional[str]:
        # 1. Package declaration from directory name
        # 2. Import block (stdlib first, third-party after blank line)
        # 3. Type declarations (struct with embedded types)
        # 4. Function/method stubs with panic body
        # 5. Interface declarations (for interface files)
```

**Key Go conventions:**
- `package {dir_name}` (lowercase, single word)
- Import grouping: stdlib (`"fmt"`, `"context"`) → blank line → third-party
- Struct fields: `fieldName Type` (no semicolons)
- Methods: `func (s *StructName) MethodName(ctx context.Context) error`
- Stubs: `panic("not implemented")`

**Wire into prime_adapter.py:**
```python
# Line ~1885 (currently "skip — no Go assembler")
if _suffix == ".go":
    from startd8.utils.go_file_assembler import GoDeterministicFileAssembler
    go_assembler = GoDeterministicFileAssembler()
    go_source = go_assembler.render_file(file_spec)
    if go_source:
        skeletons[file_path] = go_source
```

**Effort:** ~50 lines (assembler) + ~10 lines (wiring)

---

## Phase 3: Deterministic File Routing (~60 lines) (REQ-DFA-101, 106)

### Step 3.1 — Route Build/Config Files to Generators (REQ-DFA-101)

**File:** `src/startd8/contractors/prime_contractor.py` (modify feature processing)

Before sending a feature to LLM generation, check if all target files are deterministic:

```python
def _is_deterministic_file(self, file_path: str, language_profile) -> bool:
    """Check if a file can be generated without LLM."""
    ext = Path(file_path).suffix
    name = Path(file_path).name
    # Build/config files
    if ext in (".csproj", ".sln") and hasattr(language_profile, "generate_dependency_file"):
        return True
    if name in ("go.mod", "go.sum"):
        return True
    if name in ("package.json", "tsconfig.json"):
        return True
    if name in ("build.gradle", "settings.gradle"):
        return True
    # Config files
    if name in ("appsettings.json", ".env", "config.yaml"):
        return True
    return False
```

When all target files are deterministic, skip LLM and call the generator directly.

**Effort:** ~30 lines

### Step 3.2 — Dockerfile Template Generator (REQ-DFA-106)

**File:** `src/startd8/languages/protocol.py` (add optional method to protocol)
**Files:** Add `generate_dockerfile()` to each language profile

Template per language (3-5 variables: `service_name`, `port`, `entry_point`):

```python
def generate_dockerfile(
    self,
    service_name: str,
    port: int = 8080,
    entry_point: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate multi-stage Dockerfile content."""
```

**Effort:** ~30 lines per language × 4 = ~120 lines, but the templates are mostly identical structure with language-specific build commands. Can extract a shared base template.

**Simpler approach:** One function with a language dispatch:

```python
# src/startd8/utils/dockerfile_generator.py
def generate_dockerfile(language_id: str, service_name: str, port: int, ...) -> str:
    templates = {
        "csharp": _CSHARP_DOCKERFILE_TEMPLATE,
        "go": _GO_DOCKERFILE_TEMPLATE,
        "java": _JAVA_DOCKERFILE_TEMPLATE,
        "nodejs": _NODEJS_DOCKERFILE_TEMPLATE,
    }
    return templates[language_id].format(service_name=service_name, port=port, ...)
```

**Effort:** ~60 lines (one file with 4 templates)

---

## Phase 4: Template Expansion (~40 lines) (REQ-DFA-103, 104)

### Step 4.1 — Health Check Templates

Add per-language health check templates to `TemplateRegistry`:

| Language | Template Name | Match Pattern | Output |
|----------|--------------|---------------|--------|
| C# | `csharp_health_check` | `Check()` or `Ping()` returning `bool`/`HealthCheckResult` | `return HealthCheckResult.Healthy();` |
| Go | `go_health_check` | `healthz` or `Check(ctx)` returning `error` | `return nil` |
| Java | `java_health_check` | `health()` returning `Health` | `return Health.up().build();` |
| Node.js | `nodejs_health_check` | `healthz` handler | `res.status(200).json({status:'ok'})` |

**Effort:** ~20 lines (4 templates, ~5 lines each)

### Step 4.2 — Interface-from-Contract Generation (REQ-DFA-104)

**File:** Enhance `derive_elements_from_metadata()` (from Step 1.1)

When the filename matches an interface pattern, generate elements with `kind="interface"` and method signatures from contracts (no bodies).

The DFA assemblers already handle `kind="interface"` — they render method signatures without bodies. The key is getting the element `kind` right.

**Effort:** ~20 lines (interface detection + contract-to-signature mapping)

---

## Phase 5: Validate End-to-End

### Step 5.1 — Unit Tests

**File:** `tests/unit/seeds/test_element_deriver.py` (NEW)

| Test | What It Validates |
|------|-------------------|
| `test_derive_class_from_filename` | `CartStore.cs` → `ForwardElementSpec(kind="class", name="CartStore")` |
| `test_derive_interface_from_filename` | `ICartStore.cs` → `ForwardElementSpec(kind="interface", name="ICartStore")` (C# I-prefix) |
| `test_derive_methods_from_contracts` | FM contract with `AddItemAsync` → method element |
| `test_derive_imports_from_framework` | gRPC framework detected → `using Grpc.Core;` |
| `test_go_package_from_directory` | `src/shipping/main.go` → `package main` |
| `test_java_package_from_directory` | `src/main/java/com/example/Foo.java` → `package com.example` |

**File:** `tests/unit/utils/test_go_file_assembler.py` (NEW)

| Test | What It Validates |
|------|-------------------|
| `test_render_go_struct` | Produces valid Go struct with fields |
| `test_render_go_interface` | Produces valid Go interface |
| `test_render_go_function_stub` | Produces `panic("not implemented")` body |
| `test_derive_package_name` | Directory → package name derivation |
| `test_gofmt_validation` | Output passes `gofmt -e` (if available) |

**Effort:** ~80 lines

### Step 5.2 — Integration Test

Replay run-106 feature metadata through the element deriver and verify:
1. All 9 .cs files get ≥1 element
2. `ICartStore.cs` gets `kind="interface"` (not class)
3. DFA assemblers produce skeletons for all files
4. Skeletons have correct namespaces (PascalCase)
5. Skeletons have ILogger<T> in constructors

### Step 5.3 — Dry-Run Validation

```bash
# Verify element derivation on run-106 seed
python3 -c "
from startd8.seeds.element_deriver import derive_elements_from_metadata
elements, imports = derive_elements_from_metadata(
    'src/cartservice/src/cartstore/ICartStore.cs',
    'Interface for cart store operations',
    contracts=[...],
    framework_imports={},
    language_id='csharp',
)
print(f'{len(elements)} elements, {len(imports)} imports')
for e in elements:
    print(f'  {e.kind}: {e.name}')
"
```

---

## File Change Summary

| File | Phase | Status | Changes | Effort |
|------|-------|--------|---------|--------|
| `src/startd8/seeds/element_deriver.py` | 1.1 | **NEW** | Element derivation from metadata | ~80 lines |
| `src/startd8/seeds/builder.py` | 1.2 | Modify | Call element deriver after FM creation | ~30 lines |
| `src/startd8/micro_prime/prime_adapter.py` | 1.4 | Modify | Inject `skeleton_sources` into context | ~15 lines |
| `src/startd8/utils/go_file_assembler.py` | 2 | **NEW** | Go DFA assembler | ~50 lines |
| `src/startd8/micro_prime/prime_adapter.py` | 2 | Modify | Wire Go assembler | ~10 lines |
| `src/startd8/utils/dockerfile_generator.py` | 3.2 | **NEW** | 4 Dockerfile templates | ~60 lines |
| `src/startd8/contractors/prime_contractor.py` | 3.1 | Modify | Deterministic file routing | ~30 lines |
| `src/startd8/micro_prime/templates.py` | 4.1 | Modify | 4 health check templates | ~20 lines |
| `tests/unit/seeds/test_element_deriver.py` | 5.1 | **NEW** | Element deriver tests | ~50 lines |
| `tests/unit/utils/test_go_file_assembler.py` | 5.1 | **NEW** | Go DFA tests | ~30 lines |
| **Total** | | **3 new + 5 modified** | | **~375 lines** |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Element deriver produces wrong method signatures | Medium | Medium | Validate against FM contracts; fall back to empty elements (no worse than today) |
| DFA skeletons cause LLM confusion in skeleton_fill | Low | Medium | Skeleton_fill mode already tested for Python; non-Python follows same pattern |
| Go DFA produces invalid syntax | Low | Low | Validate with `gofmt -e`; fall back to LLM file-whole |
| Deterministic Dockerfile diverges from project needs | Medium | Low | Template covers 90% of cases; LLM fallback for custom Docker patterns |
| Greenfield element derivation too sparse | Medium | Medium | Even 1 element (class name) produces useful skeleton; progressive enrichment over runs |

---

## Dependency Graph

```
REQ-DFA-108 (element deriver)
    ├── REQ-DFA-102 (minimal skeleton) — already works once elements flow
    ├── REQ-DFA-107 (skeleton_fill activation) — needs skeleton_sources in context
    ├── REQ-DFA-103 (templates) — 29 existing templates start matching
    └── REQ-DFA-104 (interface generation) — uses element deriver with kind="interface"

REQ-DFA-105 (Go assembler) — independent, can be done in parallel

REQ-DFA-101 (deterministic routing) — independent, can be done in parallel
    └── REQ-DFA-106 (Dockerfile templates) — needed for routing decision
```

**Critical path:** Phase 1 (element deriver) unblocks Phases 4-5 and activates 29 existing templates + 3 DFA assemblers. Phases 2 and 3 are parallel.
