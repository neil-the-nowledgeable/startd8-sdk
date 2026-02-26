# Code Manifest Phase 3: Symbol Table Augmentation Requirements

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** [CODE_MANIFEST_REQUIREMENTS.md](CODE_MANIFEST_REQUIREMENTS.md) (Section 2.2, Section 9 Phase 3)
**Implements:** Layer 2 — `symtable` scope and binding analysis

---

## 1. Objective

Augment the existing AST-based code manifest (Phase 1) with scope and binding semantics from Python's `symtable` standard library module. This layer provides information that is not derivable from the AST alone:

- **Variable scope classification**: Is a name local, global, nonlocal, free (closure), imported, or a parameter?
- **Read/write analysis**: Is a name referenced (read), assigned (written), or both?
- **Closure detection**: Which functions capture variables from enclosing scopes?
- **Unused name detection**: Which names are assigned but never referenced?

These signals enable downstream consumers to reason about side effects, variable provenance, and code health without executing the target file.

---

## 2. `symtable` Module Overview

`symtable.symtable(source, filename, "exec")` returns a `SymbolTable` representing the module scope. Key API surface:

### 2.1 SymbolTable

| Method | Returns | Description |
|--------|---------|-------------|
| `get_type()` | `str` | `"module"`, `"function"`, `"class"`, `"annotation"`, `"lambda"` |
| `get_name()` | `str` | Scope name (`"top"` for module, function/class name otherwise) |
| `get_lineno()` | `int` | Line where scope is defined (0 for module) |
| `get_children()` | `list[SymbolTable]` | Nested scopes (functions, classes, comprehensions, annotations) |
| `get_symbols()` | `list[Symbol]` | All symbols in this scope |
| `lookup(name)` | `Symbol` | Look up specific symbol (raises `KeyError` if absent) |

### 2.2 Symbol

| Method | Returns | Description |
|--------|---------|-------------|
| `get_name()` | `str` | Symbol identifier |
| `is_local()` | `bool` | Assigned in this scope |
| `is_global()` | `bool` | `global` keyword or module-level reference |
| `is_declared_global()` | `bool` | Explicit `global x` declaration |
| `is_nonlocal()` | `bool` | Explicit `nonlocal x` declaration |
| `is_free()` | `bool` | References enclosing scope (closure variable) |
| `is_imported()` | `bool` | Brought in via `import`/`from X import` |
| `is_parameter()` | `bool` | Function/lambda parameter |
| `is_referenced()` | `bool` | Used (read) somewhere in scope |
| `is_assigned()` | `bool` | Assigned (written) in scope |
| `is_annotated()` | `bool` | Has type annotation |
| `is_namespace()` | `bool` | Is a function/class definition |

### 2.3 Constraints

- **Requires valid syntax**: Raises `SyntaxError` just like `ast.parse()`. Since Phase 1 already successfully parsed the AST, symtable should succeed on the same source.
- **No code execution**: Pure static analysis — no imports, no side effects.
- **Deterministic**: Same source always produces the same symbol table.

---

## 3. Schema Extensions

All new fields are **additive** per the schema versioning contract (Section 3.5 of the parent requirements). Schema version bumps from `"1.0.0"` to `"1.2.0"`.

### 3.1 New Enum: `ScopeKind`

```
"local" | "global" | "nonlocal" | "free" | "imported" | "parameter"
```

| Value | Meaning | symtable Signal |
|-------|---------|-----------------|
| `local` | Assigned in this scope, not parameter | `is_local() and not is_parameter()` |
| `global` | Declared with `global` keyword, or module-level name | `is_global()` |
| `nonlocal` | Declared with `nonlocal` keyword | `is_nonlocal()` |
| `free` | References enclosing scope (closure capture) | `is_free()` |
| `imported` | Brought in via `import` statement | `is_imported()` |
| `parameter` | Function/lambda parameter | `is_parameter()` |

**Classification priority** (applied in order, first match wins):
1. `parameter` — `is_parameter()` is true
2. `imported` — `is_imported()` is true
3. `nonlocal` — `is_nonlocal()` is true
4. `free` — `is_free()` is true
5. `global` — `is_global()` is true
6. `local` — fallback

> **Note — nonlocal before free**: Explicit `nonlocal x` declarations have *both* `is_nonlocal()=True` and `is_free()=True` (they reference an enclosing scope). Checking `nonlocal` before `free` distinguishes explicit declarations from implicit closure captures. Annotation-only declarations (`x: int` without assignment) fall through to `local`.

### 3.2 New Model: `SymbolEntry`

Per-symbol detail for consumers that need read/write analysis.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `string` | required | Symbol identifier |
| `scope` | `ScopeKind` | required | Scope classification |
| `is_referenced` | `bool` | `false` | Symbol is read somewhere in its scope |
| `is_assigned` | `bool` | `false` | Symbol is written in its scope |
| `is_parameter` | `bool` | `false` | Symbol is a function/lambda parameter |

### 3.3 New Model: `SymbolInfo`

Scope-level summary attached to each manifest `Element`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `local_vars` | `list[string]` | `[]` | Names classified as `local` or `parameter` |
| `global_vars` | `list[string]` | `[]` | Names declared `global` in this scope |
| `nonlocal_vars` | `list[string]` | `[]` | Names declared `nonlocal` in this scope |
| `free_vars` | `list[string]` | `[]` | Closure variables captured from enclosing scope |
| `imported_names` | `list[string]` | `[]` | Names brought in via `import` |
| `symbols` | `list[SymbolEntry]` | `[]` | Full per-symbol detail |
| `is_closure` | `bool` | `false` | `true` if `free_vars` is non-empty |

All list fields are sorted alphabetically for deterministic output.

### 3.4 Element Model Extension

Add one field to the existing `Element` schema (Section 3.2 of parent requirements):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `symbol_info` | `SymbolInfo?` | `null` | Symbol table analysis. `null` when symtable augmentation is disabled or the element is not part of a recognized scope. |

**Backward compatibility**: `symbol_info` defaults to `null`, so Phase 1/Phase 2 manifests remain valid. Consumers check `element.symbol_info is not None` to determine if symtable data is available.

### 3.5 Schema Version

- **Current**: `"1.0.0"` (Phase 1)
- **Phase 3**: `"1.2.0"` (additive: `ScopeKind`, `SymbolEntry`, `SymbolInfo`, `Element.symbol_info`)
- **Compatibility**: Phase 1 consumers ignore the new `symbol_info` field. Phase 3 consumers handle `symbol_info: null` for Phase 1 manifests.

---

## 4. Scope Matching Algorithm

The core challenge is aligning the `symtable` scope tree with the manifest `Element` tree, which were built from different traversals of the same source.

### 4.1 Parallel Tree Walk

```
Module SymbolTable ("top")  ←→  FileManifest.elements (top-level)
  ├─ Class scope ("MyClass")  ←→  Element(kind=CLASS, name="MyClass")
  │   ├─ Method scope ("run")   ←→  Element(kind=METHOD, name="run") in children
  │   └─ Method scope ("_init")  ←→  Element(kind=METHOD, name="_init") in children
  └─ Function scope ("helper")  ←→  Element(kind=FUNCTION, name="helper")
```

### 4.2 Matching Rules

1. **Module scope** (`get_name() == "top"`) corresponds to `FileManifest.elements` (top-level elements).
2. **Scope-creating elements** (class, function, async_function, method, async_method, property) each have a corresponding child `SymbolTable` accessible via `get_children()`.
3. **Name-based matching**: For each scope-creating Element, find the child SymbolTable where `get_name() == element.name`.
4. **Source-order disambiguation**: When multiple child scopes share the same name (overloads, property triads, branch duplicates), they are returned by `get_children()` in source order. Elements are also in source order from the AST walker. Match by popping the first unused scope with the matching name.
5. **Non-scope elements** (constants, variables, type aliases) are looked up as symbols in their parent scope via `scope.lookup(element.name)`.

### 4.3 Recursive Enrichment

For each scope-creating element:
1. Find and consume its matching child SymbolTable.
2. Build `SymbolInfo` from the scope's symbols.
3. Recurse into `element.children` using the child SymbolTable's nested scopes.
4. Recurse into `element.class_variables` using symbol lookups in the class scope.
5. Rebuild the element with `model_copy(update={...})` (since Element is frozen).

### 4.4 Unmatched Scopes

Child SymbolTables that do not match any Element are silently ignored. This occurs for:
- **`__annotate__` scopes** (Python 3.10+): synthetic scopes for annotation evaluation
- **Lambda scopes**: anonymous functions not extracted as named Elements
- **Comprehension scopes**: list/dict/set comprehensions have implicit scopes

These are **not** errors. The enrichment function logs at DEBUG level for unmatched scopes.

---

## 5. Generation Mode Integration

### 5.1 Mode Behavior

| Mode | Layers | symtable | Description |
|------|--------|----------|-------------|
| `static` (default) | AST + symtable | **Yes** | Full static analysis. Default for all callers. |
| `ast_only` | AST only | No | Pure Phase 1 behavior. For backward compat or performance-sensitive paths. |
| `introspect` | AST + symtable + inspect | Yes | Future (Phase 5). Raises `NotImplementedError`. |
| `full` | All layers | Yes | Future (Phase 6). Raises `NotImplementedError`. |

### 5.2 `generate_file_manifest()` Changes

- Accept `mode="ast_only"` as a valid mode (skip symtable augmentation).
- In `mode="static"` (default): call `_augment_with_symtable()` after AST visitation and before returning.
- Skip augmentation if the manifest has parse errors (AST failed → symtable would fail too).
- Update error message for unsupported modes from `"Phase 3+"` to `"Phase 5+"`.

### 5.3 Defensive Error Handling

Although `symtable.symtable()` should not fail if `ast.parse()` succeeded on the same source, the augmentation function catches **any `Exception`** defensively and returns the unenriched manifest with a **WARNING**-level log (including `exc_info=True` for stack trace visibility). This broad catch prevents silent failures from unexpected edge cases (e.g., `ValueError` on encoding issues, internal CPython errors) and ensures the manifest generation pipeline is never interrupted by symtable failures. The WARNING level is appropriate because a symtable failure after a successful AST parse indicates an anomaly worth investigating.

---

## 6. Cache Compatibility

### 6.1 Digest-Based Cache

The digest is computed from source content, not manifest content. Upgrading from Phase 1 to Phase 3 does **not** change the digest for unchanged files. This means a Phase 1 cache entry (schema `"1.0.0"`, no `symbol_info`) would be served as a cache hit for Phase 3 code.

### 6.2 Schema Version Gate

To force regeneration on schema upgrade, the cache hit check must verify schema version:

```
cache hit = (cached.digest == current_digest) AND (cached.schema_version == SCHEMA_VERSION)
```

This ensures that upgrading the code triggers a one-time full regeneration. Subsequent runs hit the cache.

### 6.3 Forward/Backward Loading

- **Pydantic `model_validate()`** ignores unknown fields by default (forward compatibility).
- **`symbol_info` defaults to `None`** (backward compatibility: loading Phase 1 manifests in Phase 3 code works).
- Cache entries from Phase 3 loaded by Phase 1 code: unknown `symbol_info` field is ignored.

---

## 7. Edge Cases

### 7.1 `__annotate__` Scopes (Python 3.10+)

Classes and functions with type annotations generate synthetic `__annotate__` child scopes in the symtable. These must be filtered out during child scope indexing:

```python
if child.get_name() == "__annotate__":
    continue
```

### 7.2 Class Scope Rules

Python class bodies do **not** create an enclosing scope for nested methods. A method cannot access class-level variables via closure — it must use `self.x` or `ClassName.x`. The symtable correctly reflects this: class-scope symbols have `is_local()=True` but they are not `is_free()` in method scopes. No special handling needed.

### 7.3 Overloads and Property Triads

Functions decorated with `@overload` and `@property`/`@name.setter`/`@name.deleter` produce multiple child scopes with the same name. The pop-from-list matching strategy (Section 4.2, rule 4) handles this because both the Element list and the SymbolTable children are in source order.

### 7.4 Nested Functions

Inner functions defined inside other functions create nested scopes. The recursive enrichment (Section 4.3) handles this naturally. Free variables in inner functions (`is_free()=True`) appear in `SymbolInfo.free_vars`, and `is_closure` is set to `True`.

### 7.5 Global and Nonlocal Declarations

- `global x` in a function: symbol `x` has `is_global()=True`, `is_declared_global()=True`. Classified as `ScopeKind.GLOBAL`. Appears in `SymbolInfo.global_vars`.
- `nonlocal x` in a nested function: symbol `x` has `is_nonlocal()=True`. Classified as `ScopeKind.NONLOCAL`. Appears in `SymbolInfo.nonlocal_vars`.

### 7.6 Module-Level Variables

At module scope, all assigned names have `is_local()=True` (they are local to the module). The classification priority (Section 3.1) places `imported` before `global` before `local`, so imported names are correctly classified even though they are also "local" to the module.

### 7.7 Walrus Operator (`:=`)

Assignment expressions create local variables in the enclosing function scope (not the enclosing comprehension scope). The symtable handles this per PEP 572 semantics. No special handling needed.

---

## 8. Performance Budget

| Operation | Target | Notes |
|-----------|--------|-------|
| symtable overhead per file | < 10ms | `symtable.symtable()` + scope walk + model rebuild |
| Total static mode per file | < 110ms | Phase 1 AST (~100ms) + Phase 3 symtable (~10ms) |
| Batch scan regression | None | Cache schema version gate triggers one-time regen; subsequent runs same speed |

### 8.1 Performance Strategy

- `symtable.symtable()` parses the same source that `ast.parse()` already processed. The compile step is shared internally by CPython, so the incremental cost is primarily the scope analysis and our enrichment walk.
- The enrichment walk is O(elements × symbols_per_scope). For typical files, this is dominated by the number of top-level and class-level elements.
- `model_copy(update={...})` creates new Pydantic instances but avoids full re-validation when the model is frozen.

---

## 9. Acceptance Criteria

### 9.1 Functional

| # | Criterion | Verification |
|---|-----------|-------------|
| AC-1 | Closure variables correctly identified | `inner()` capturing `x` from `outer()` → `symbol_info.free_vars == ["x"]`, `is_closure == True` |
| AC-2 | `global` declarations captured | `global counter` in function → `symbol_info.global_vars == ["counter"]` |
| AC-3 | `nonlocal` declarations captured | `nonlocal count` in nested function → `symbol_info.nonlocal_vars == ["count"]` |
| AC-4 | Parameters classified correctly | Function params → `ScopeKind.PARAMETER` in `symbols` |
| AC-5 | Imported names classified | `import os` at module level → `ScopeKind.IMPORTED` |
| AC-6 | Read/write analysis accurate | Assigned-only variable: `is_assigned=True, is_referenced=False` |
| AC-7 | Recursive enrichment | Nested function children and class variables all receive `symbol_info` |
| AC-8 | Schema version bumped | `manifest.schema_version == "1.2.0"` |
| AC-9 | Backward compat: None default | `Element(…)` without `symbol_info` still works (defaults to `None`) |
| AC-10 | `ast_only` mode skips symtable | `mode="ast_only"` → all `symbol_info` are `None` |
| AC-11 | Parse error safety | File with syntax error → `symbol_info` is `None`, no crash |
| AC-12 | Determinism | Same source → same `symbol_info` output |
| AC-13 | Existing tests pass | All Phase 1/2 tests pass without modification (except mode error message) |

### 9.2 Performance

| # | Criterion | Verification |
|---|-----------|-------------|
| AP-1 | symtable overhead < 10ms per file | Benchmark `mode="static"` vs `mode="ast_only"` on `code_manifest.py` itself |
| AP-2 | No batch regression | `startd8 manifest generate --verbose` completes in < 10s |

### 9.3 Cache

| # | Criterion | Verification |
|---|-----------|-------------|
| AC-C1 | Schema upgrade invalidates cache | Phase 1 cache entries regenerated on first Phase 3 run |
| AC-C2 | Phase 1 manifests load in Phase 3 | `symbol_info` is `None`, no validation error |

---

## 10. Downstream Consumer Guidance

### 10.1 Checking for symtable Data

```python
if element.symbol_info is not None:
    if element.symbol_info.is_closure:
        print(f"{element.fqn} captures: {element.symbol_info.free_vars}")
```

### 10.2 Unused Name Detection

```python
for entry in element.symbol_info.symbols:
    if entry.is_assigned and not entry.is_referenced:
        print(f"Unused: {entry.name} in {element.fqn}")
```

### 10.3 Side Effect Analysis

```python
if element.symbol_info.global_vars:
    print(f"{element.fqn} modifies globals: {element.symbol_info.global_vars}")
```

---

## Appendix: Iterative Review Log

### Reviewer Instructions

Same instructions as the parent requirements document (see CODE_MANIFEST_REQUIREMENTS.md Appendix).

### Areas Substantially Addressed

- **ambiguity**: 3 suggestions applied (R1-S2, R1-S8, R2-S8)
- **completeness**: 4 suggestions applied (R1-S1, R1-S5, R2-S1, R2-S5)

### Areas Needing Further Review

- **consistency**: 1 accepted (R1-S3) — needs 2 more to reach threshold of 3
- **feasibility**: 2 accepted (R1-S4, R2-S2) — needs 1 more to reach threshold of 3
- **testability**: 2 accepted (R1-S6, R2-S9) — needs 1 more to reach threshold of 3
- **traceability**: no accepted suggestions yet — needs 3 to reach threshold

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Define how SymbolInfo is populated for non-scope elements (variables, constants, type aliases) that use symbol lookup rather than scope traversal. | claude-4 (claude-opus-4-6) | This is a genuine gap: Section 4.2 rule 5 describes looking up non-scope elements as symbols in the parent scope, but SymbolInfo is designed for scope-level summaries. Implementers need clear guidance on what shape the SymbolInfo takes for these elements (minimal single-symbol SymbolInfo, or null with the symbol appearing in the parent's SymbolInfo instead). | 2026-02-24 18:54:48 UTC |
| R1-S2 | Document that symtable flags are not mutually exclusive and clarify known multi-flag combinations against the classification priority list. | claude-4 (claude-opus-4-6) | The priority list implicitly assumes first-match-wins but doesn't acknowledge that multiple flags can be true simultaneously. Documenting known combinations (e.g., is_free + is_assigned for augmented assignment in closures) prevents implementer confusion and ensures the priority list is applied correctly. | 2026-02-24 18:54:48 UTC |
| R1-S3 | Explain the schema version gap from 1.0.0 to 1.2.0 and clarify Phase 2's version allocation. | claude-4 (claude-opus-4-6) | The jump from 1.0.0 to 1.2.0 without explanation suggests either an error or an undocumented Phase 2 at 1.1.0. A brief note clarifying the version numbering scheme across phases eliminates this ambiguity. | 2026-02-24 18:54:48 UTC |
| R1-S4 | Specify bottom-up traversal order for frozen model enrichment to avoid O(n²) copy overhead. | claude-4 (claude-opus-4-6) | For frozen Pydantic models, enriching children first and then constructing parents with already-enriched children avoids re-copying parent chains. This is a real performance concern for deeply nested class hierarchies and the spec should mandate traversal order and acknowledge the copy cost. | 2026-02-24 18:54:48 UTC |
| R1-S5 | Document that *args and **kwargs parameters appear as bare names ('args', 'kwargs') with scope 'parameter' in SymbolEntry. | claude-4 (claude-opus-4-6) | This is a practical question implementers and consumers will have. Confirming the behavior (bare names, classified as parameter) prevents confusion and aids consumers correlating symbol info with function signatures. | 2026-02-24 18:54:48 UTC |
| R1-S6 | Expand AC-6 with a concrete code example for assigned-but-unreferenced variable detection. | claude-4 (claude-opus-4-6) | All other acceptance criteria (AC-1 through AC-5) include specific code patterns. AC-6 is the key validation for unused name detection, a primary consumer value proposition, and deserves equal specificity. | 2026-02-24 18:54:48 UTC |
| R1-S8 | Elevate the log level for defensive SyntaxError catch in symtable from DEBUG to WARNING. | claude-4 (claude-opus-4-6) | If ast.parse() succeeds but symtable.symtable() fails on the same source, this indicates a serious anomaly (CPython bug, source mutation, or encoding issue). DEBUG level would make this invisible in production. WARNING is the appropriate level for an unexpected but non-fatal condition, while DEBUG remains correct for expected unmatched scopes. | 2026-02-24 18:54:48 UTC |
| R2-S1 | Define handling for assigned lambdas (e.g., x = lambda...) — whether the lambda's SymbolTable is associated with the variable Element. | gemini-2.5 (gemini-2.5-pro) | This is directly related to R1-S1 and addresses a real ambiguity. A variable assigned a lambda creates both a variable Element and a lambda SymbolTable child scope. The spec must clarify whether these are matched (making the variable's symbol_info reflect the lambda's scope) or whether the lambda scope is unmatched/ignored per Section 4.4. | 2026-02-24 18:54:48 UTC |
| R2-S2 | Use (name, lineno) as the primary matching key for scope-to-element alignment instead of name-only with source-order pop. | gemini-2.5 (gemini-2.5-pro) | Line number matching is more robust than source-order popping, especially for edge cases like same-named functions in different branches. Both SymbolTable.get_lineno() and Element.lineno are available. This reduces fragility of the matching algorithm while keeping source-order pop as a fallback. | 2026-02-24 18:54:48 UTC |
| R2-S5 | Document that exec() and eval() are analysis boundaries and symbols within them are not captured. | gemini-2.5 (gemini-2.5-pro) | This is a concise, important limitation that consumers need to know. It fits naturally in Section 2.3 (Constraints) as a single sentence and manages expectations without scope creep. | 2026-02-24 18:54:48 UTC |
| R2-S6 | Add the Python interpreter version to the cache key to prevent invalid cache hits across Python versions. | gemini-2.5 (gemini-2.5-pro) | This is a genuine correctness issue. The symtable module's behavior changes across Python versions (e.g., __annotate__ scopes in 3.10+, PEP 709 comprehension inlining in 3.12). A cache entry from one Python version could produce incorrect results when loaded by another. The fix is simple and prevents subtle, hard-to-diagnose bugs. | 2026-02-24 18:54:48 UTC |
| R2-S8 | Clarify AC-7 to specify that class variables appear as SymbolEntry in the parent class's symbol_info, not as having their own symbol_info. | gemini-2.5 (gemini-2.5-pro) | The current wording 'class variables all receive symbol_info' is ambiguous and potentially incorrect. Class variables are non-scope elements; whether they get their own symbol_info depends on the resolution of R1-S1. At minimum, AC-7 should clarify the expected behavior rather than using vague language. | 2026-02-24 18:54:48 UTC |
| R2-S9 | Expand AC-5 to cover aliased imports, from-imports, and aliased from-imports in addition to bare 'import os'. | gemini-2.5 (gemini-2.5-pro) | Import aliasing affects which symbol name appears in the symtable (the alias, not the original module name). Testing only bare imports misses the common case of aliased imports where the symbol name differs from the module name. This is a practical correctness concern. | 2026-02-24 18:54:48 UTC |
| R1-F1 | Specify error handling when scope.lookup() raises KeyError for non-scope elements in Section 4.2 rule 5. |  | The requirements mention KeyError in the API table but don't specify handling when lookup fails for AST-extracted elements that don't have corresponding symtable symbols. This is a real edge case (e.g., __all__ assignments, conditional definitions) that needs explicit handling — likely returning null symbol_info. | 2026-02-24 19:03:10 UTC |
| R1-F2 | Update Section 4.2 body text to reflect the (name, lineno) matching strategy from the applied R2-S2 suggestion. |  | This is a clear internal inconsistency: Appendix A records R2-S2 as applied but the body text still describes the original name-only matching algorithm. Implementers will be confused by the contradiction. The body must be authoritative. | 2026-02-24 19:03:10 UTC |
| R1-F3 | Document the current mode handling implementation so the Phase 3 delta is clear. |  | The requirements say 'update error message from Phase 3+ to Phase 5+' which assumes existing infrastructure that isn't described. Without knowing the current state, an implementer can't correctly apply the delta. A brief note about current mode handling is needed. | 2026-02-24 19:03:10 UTC |
| R1-F4 | Clarify that is_closure is strictly per-scope (the function itself captures free variables) and not transitive. |  | This is a genuine semantic ambiguity. The definition says 'true if free_vars is non-empty' which is per-scope, but consumers doing side-effect analysis might expect transitivity. Explicitly stating it's non-transitive with a concrete test case prevents misuse. | 2026-02-24 19:03:10 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S7 | Document symtable behavior for conditional imports (TYPE_CHECKING, try/except ImportError). | claude-4 (claude-opus-4-6) | This is a correct observation about symtable behavior, but it's a general property of static analysis that symtable analyzes all syntactic paths. Documenting every pattern where static analysis differs from runtime is unbounded scope creep. The document already states 'no code execution: pure static analysis' in Section 2.3, which covers this implicitly. | 2026-02-24 18:54:48 UTC |
| R1-S9 | Explicitly confirm walrus operator variables in comprehensions appear in the enclosing function's SymbolInfo. | claude-4 (claude-opus-4-6) | Section 7.7 already correctly states 'the symtable handles this per PEP 572 semantics. No special handling needed.' The symtable places the walrus variable in the function scope, and the enrichment naturally picks it up. Adding a test case is good practice but doesn't require a spec change — the existing text is accurate. | 2026-02-24 18:54:48 UTC |
| R1-S10 | Add traceability IDs linking each acceptance criterion to parent document requirements. | claude-4 (claude-opus-4-6) | While traceability is generally valuable, the parent document's Phase 3 section is referenced in the header and the relationship is straightforward. The overhead of maintaining cross-reference IDs between two evolving documents outweighs the benefit at this stage. This can be added if the number of phases and requirements grows significantly. | 2026-02-24 18:54:48 UTC |
| R2-S3 | Remove the is_parameter boolean field from SymbolEntry since it's redundant with scope == 'parameter'. | gemini-2.5 (gemini-2.5-pro) | While technically redundant, the is_parameter field provides a direct mirror of the symtable API (Symbol.is_parameter()) and serves as a convenience accessor for a very common query. The redundancy cost (one boolean per symbol) is trivial, and removing it would break the parallel structure between SymbolEntry and symtable's Symbol API. | 2026-02-24 18:54:48 UTC |
| R2-S4 | Remove summary list fields (local_vars, global_vars, etc.) from SymbolInfo since they're derivable from the symbols list. | gemini-2.5 (gemini-2.5-pro) | The summary lists serve as pre-computed convenience views for the most common consumer queries (side effect analysis, closure detection). They enable O(1) checks like 'if element.symbol_info.global_vars' without requiring consumers to filter the symbols list. The manifest is a read-heavy artifact, so denormalization is appropriate. The is_closure field explicitly depends on free_vars being pre-computed. | 2026-02-24 18:54:48 UTC |
| R2-S7 | Add a strict matching mode that raises exceptions on unmatched scopes for internal testing. | gemini-2.5 (gemini-2.5-pro) | This is an implementation/testing strategy detail, not a requirements specification concern. Test authors can implement strict assertions in their test code without the production enrichment function needing a strict mode parameter. Adding it to the spec couples testing strategy to the API surface. | 2026-02-24 18:54:48 UTC |
| R2-S10 | Document that decorator-introduced symbols are not visible to symtable analysis. | gemini-2.5 (gemini-2.5-pro) | This is a general property of all static analysis (no code execution = no dynamic effects). The document already states 'no code execution: pure static analysis' in Section 2.3. Enumerating every dynamic mechanism that static analysis cannot capture (decorators, metaclasses, monkey-patching, __init_subclass__, etc.) is unbounded and adds noise. | 2026-02-24 18:54:48 UTC |
| R1-F5 | Document thread safety characteristics of symtable.symtable() and the enrichment function. |  | symtable.symtable() is a CPython builtin that operates under the GIL like any other CPython C extension. The enrichment function is a pure function (takes source, returns enriched manifest) with no shared mutable state. Thread safety is a general Python runtime concern, not specific to this feature. Documenting GIL behavior for every standard library call is unbounded scope creep. | 2026-02-24 19:03:10 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

*(Awaiting first review round)*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-24 18:52:18 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | Define how `SymbolInfo` is populated for non-scope elements (variables, constants, type aliases) that are looked up as symbols in their parent scope (Section 4.2 rule 5). Currently `SymbolInfo` has fields like `local_vars`, `free_vars`, `symbols` that make sense for scopes but not for individual symbol lookups. Specify whether these elements get a full `SymbolInfo`, a minimal `SymbolEntry`-only `SymbolInfo`, or just `null`. | Section 4.2 rule 5 says non-scope elements use `scope.lookup(element.name)`, but Section 3.3 `SymbolInfo` is designed for scope-level summaries. There is no specification for what `SymbolInfo` looks like when derived from a single symbol lookup rather than a full scope. Implementers will make inconsistent choices. | Section 4.2 (new subsection 4.2.1 "Non-Scope Element Enrichment") and Section 3.3 (clarifying note) | Implement a test with a module-level constant and a class variable; assert the exact shape of their `symbol_info` fields. |
| R1-S2 | ambiguity | high | The `ScopeKind` classification priority (Section 3.1) does not handle the case where a symbol is both `is_imported()` and `is_parameter()` (e.g., parameter shadowing an import name) or both `is_free()` and `is_assigned()`. Clarify that the priority list is exhaustive and that `symtable` flags are not mutually exclusive; document which flag combinations are possible in practice. | Python's `symtable` can return multiple true flags for a single symbol (e.g., a name that is both assigned and free in augmented assignment of a closure variable). The priority list assumes mutual exclusivity without stating this assumption or documenting known combinations. | Section 3.1, add a "Flag Combinations" note after the priority table | Add parameterized tests for known multi-flag symbols: closure variable with augmented assignment (`x += 1` with `nonlocal x`), imported name reassigned in same scope. |
| R1-S3 | consistency | high | Schema version jump from `"1.0.0"` to `"1.2.0"` skips `"1.1.0"`. Section 3.5 says Phase 1 is `"1.0.0"` and Phase 3 is `"1.2.0"`, but the parent document Section 9 defines Phase 2 (docstring/decorator enrichment). If Phase 2 uses `"1.1.0"`, this should be stated; if Phase 2 doesn't exist yet, explain the version gap. | Without explanation, `"1.2.0"` looks like an error or implies a Phase 2 schema version that is never defined. This creates confusion about whether `"1.1.0"` is reserved, allocated, or skipped. | Section 3.5, add a note explaining the version numbering scheme across phases | Verify parent document Section 9 phase numbering and confirm Phase 2 schema version allocation. |
| R1-S4 | feasibility | high | The `model_copy(update={...})` strategy (Section 4.3, 8.1) for frozen Pydantic models creates a full copy of the entire element tree for each enrichment. For deeply nested class hierarchies (e.g., a class with 50 methods each with nested functions), this creates O(n²) copies because enriching an inner element requires re-copying all ancestors. Specify whether enrichment is bottom-up or top-down and analyze the copy cost. | Frozen models require full reconstruction of the parent chain when a child is updated. If enrichment proceeds top-down and then discovers child updates, the parent must be re-copied. Bottom-up enrichment avoids this but isn't specified. The performance budget (Section 8) doesn't account for copy overhead on large files. | Section 4.3 (specify traversal order) and Section 8 (add copy cost to performance model) | Benchmark enrichment on a synthetic file with 100 methods in a class, each with 2 nested functions. Measure model_copy overhead separately from symtable analysis. |
| R1-S5 | completeness | medium | No specification for how `SymbolInfo` handles `*args` and `**kwargs` parameters. Are they classified as `parameter`? Do their names include the `*`/`**` prefix or just the bare name? | `symtable` reports `args` and `kwargs` (without prefix) as `is_parameter()=True`, but the spec doesn't confirm this behavior or state that names are always bare identifiers. This matters for consumers correlating `SymbolInfo.symbols` with function signature parameters. | Section 7 (new subsection 7.8 "Star Parameters") | Test function `def f(*args, **kwargs)`: assert `symbol_info.symbols` contains entries with `name="args"` and `name="kwargs"`, both with `scope="parameter"`. |
| R1-S6 | testability | medium | Acceptance criterion AC-6 ("Assigned-only variable: `is_assigned=True, is_referenced=False`") does not specify a concrete test case. Unlike AC-1 through AC-5 which give specific code patterns, AC-6 is abstract. Provide a canonical code snippet (e.g., `x = 42` with no subsequent use of `x`). | Without a concrete example, different test authors may write tests that pass trivially or test the wrong thing. The "unused name detection" use case (Section 10.2) is a key consumer value proposition and deserves a precise test fixture. | Section 9.1, expand AC-6 with a concrete code example | Review the test implementation to confirm it uses a non-trivial example where the assigned-but-unreferenced variable is not also a parameter or import. |
| R1-S7 | completeness | medium | No mention of how `symtable` handles conditional imports (`if TYPE_CHECKING: import X`) or `try/except ImportError` patterns. These are common in typed Python code and affect whether `X` appears as `is_imported()`. | `symtable` does static analysis of the full source, so conditionally imported names are still marked `is_imported()`. This is arguably correct but may surprise consumers expecting only runtime imports. Document the behavior and whether consumers should cross-reference with AST-level `if TYPE_CHECKING` detection. | Section 7 (new subsection 7.9 "Conditional Imports") | Test a file with `if TYPE_CHECKING: from foo import Bar` and assert `Bar` has `scope="imported"`. Add a note about the limitation. |
| R1-S8 | ambiguity | medium | Section 4.4 says unmatched scopes are "silently ignored" with DEBUG logging, but Section 5.3 says `SyntaxError` is caught with a "DEBUG log". These are different failure modes (expected skips vs. unexpected errors) logged at the same level. The DEBUG level for a defensive `SyntaxError` catch seems too quiet — this indicates a potential CPython bug or source mutation between parse and symtable. | If `ast.parse()` succeeds but `symtable.symtable()` fails, something is seriously wrong. Logging this at DEBUG level means it will likely be missed in production. WARNING or ERROR level would be more appropriate for the SyntaxError case, while DEBUG is fine for unmatched scopes. | Section 5.3 (change log level to WARNING) and Section 4.4 (keep DEBUG) | Verify log levels in implementation; write a test that mocks `symtable.symtable` to raise `SyntaxError` and asserts a WARNING-level log is emitted. |
| R1-S9 | completeness | medium | The spec does not address comprehension scopes that contain walrus operators. Section 7.7 says walrus creates locals in the enclosing function scope, and Section 4.4 says comprehension scopes are ignored. But if a walrus in a comprehension creates a variable in the enclosing function, the enrichment must correctly attribute that variable to the function's `SymbolInfo`, not lose it because the comprehension scope was skipped. | This is a subtle interaction between two documented edge cases. The symtable correctly places the walrus variable in the function scope, so the enrichment should work. But the spec should explicitly confirm this and provide a test case since it's a known source of bugs. | Section 7.7 (expand with comprehension interaction note) | Test: `def f(): result = [y := x for x in range(10)]; return y` — assert `y` appears in `f`'s `symbol_info.local_vars` and `symbol_info.symbols`. |
| R1-S10 | traceability | low | The document references "Section 2.2, Section 9 Phase 3" of the parent requirements but does not specify which specific requirements from the parent are satisfied by each acceptance criterion. Adding traceability IDs (e.g., "satisfies PARENT-REQ-9.3.1") would help verify completeness of coverage. | Without explicit traceability, it's impossible to verify that all parent Phase 3 requirements are covered by acceptance criteria in this document. A requirement could be missed without anyone noticing. | Section 9 (add traceability column to AC tables) | Cross-reference parent document Section 9 Phase 3 requirements against this document's acceptance criteria; confirm 1:1 or 1:many coverage. |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-24 18:53:15 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | completeness | high | Explicitly define handling for assigned lambdas (e.g., `x = lambda...`). | The document states lambda scopes are ignored, but an `Element` will be created for the variable `x`. It's unclear if the `SymbolTable` for the lambda (which is a child of the module scope) will be associated with the `Element` for `x`, or if `x` is just treated as a variable whose value happens to be a function. This ambiguity affects consumers analyzing callables. | Section 4.4 (Unmatched Scopes) | Create a test case with `my_lambda = lambda a: a + 1` and assert whether the `Element` for `my_lambda` has `symbol_info` populated (and if so, that it correctly reflects the lambda's parameter `a`). |
| R2-S2 | feasibility | medium | Use `(name, lineno)` as the primary matching key for scopes. | The current plan relies on name and source order (4.2.4). Using the line number (`get_lineno()`) from the `SymbolTable` and the `lineno` from the AST-derived `Element` provides a much more robust and less fragile matching key, making the source-order pop a fallback for rare cases like decorators on the same line. | Section 4.2 (Matching Rules) | A test with two functions of the same name defined in different branches of an `if/else` block. Name-only matching could fail, but `(name, lineno)` matching will succeed. |
| R2-S3 | consistency | low | Remove the `is_parameter` boolean field from `SymbolEntry`. | The `SymbolEntry.scope` field, with a value of `ScopeKind.PARAMETER`, already captures this information. The boolean field is redundant, increases payload size, and offers a potential point of inconsistency if the two fields were to ever diverge due to a bug. | Section 3.2 (New Model: SymbolEntry) | Code review of the implementation to ensure `scope == "parameter"` is used instead. A simple test asserting `symbol.scope == "parameter"` for a function argument. |
| R2-S4 | consistency | medium | Remove the summary list fields (`local_vars`, `global_vars`, etc.) from `SymbolInfo`. | These lists are entirely derivable from the `symbols: list[SymbolEntry]` field by filtering on the `scope` property. Including them creates data redundancy, increases manifest size, and risks inconsistency. Consumers can easily compute these lists if needed. | Section 3.3 (New Model: SymbolInfo) | Remove the fields from the Pydantic model. Update downstream consumer guidance (Sec 10) to show how to derive these lists from `element.symbol_info.symbols`. |
| R2-S5 | completeness | medium | Explicitly state that `exec()` and `eval()` are analysis boundaries. | The document focuses on what `symtable` can do but should also manage expectations by clarifying its limitations. Code inside `exec()` or `eval()` is opaque to static analysis, and any symbols defined or used within them will not be captured. | Section 2.3 (Constraints) or Section 7 (Edge Cases) | Add a sentence stating that symbols inside dynamically executed code are not analyzed. This is a documentation change, not a code change. |
| R2-S6 | critical | high | Add the Python interpreter version to the cache key. | The `symtable` module's behavior can change between Python versions (e.g., `__annotate__` scopes in 3.10). A cache entry generated with Python 3.9 would be invalid for a run on 3.11 but would be served as a hit under the current scheme, leading to subtle bugs. | Section 6.2 (Schema Version Gate) | Modify the cache key generation to include `sys.version_info`. Create a test that fails if the cache key is identical when generated under two different mock Python versions. |
| R2-S7 | testability | medium | Add a "strict matching" mode for internal testing. | Section 4.4 states unmatched `SymbolTable` scopes are silently ignored and logged at DEBUG. For testing the matching algorithm itself, a strict mode that raises an exception on any unmatched scope (except known ignores like `__annotate__`) would make it much easier to detect matching bugs. | Section 4.3 (Recursive Enrichment) or as a new test-only utility. | An integration test that runs the enrichment in strict mode on a complex file and asserts that no exception is raised. |
| R2-S8 | ambiguity | high | Clarify Acceptance Criterion AC-7 regarding "class variables". | AC-7 states "class variables all receive `symbol_info`". Class variables are `Element`s, but they are not scopes. They should not have a `symbol_info` object themselves. Rather, they should appear as a `SymbolEntry` within the `symbol_info` of their parent *class* `Element`. The current wording is incorrect and confusing. | Section 9.1 (Functional AC table) | Reword AC-7 to: "Class variable `Element`s do not have `symbol_info`, but are correctly listed as symbols in the `symbol_info` of their parent class `Element`." |
| R2-S9 | testability | medium | Expand AC-5 to cover aliased and `from` imports. | The current criterion `import os` is too simple. The test suite should cover `import os as my_os` (symbol is `my_os`), `from os import path` (symbol is `path`), and `from os.path import join as path_join` (symbol is `path_join`). | Section 9.1 (Functional AC table) | Add specific test cases for each import style, asserting that the correct symbol name is found with `scope: "imported"`. |
| R2-S10 | completeness | low | Document that decorator-introduced symbols are not visible. | A decorator can dynamically add attributes or methods to a function/class. `symtable` operates on the source code before execution and will not see these dynamically added symbols. This is a key limitation for consumers expecting full runtime introspection. | Section 7 (Edge Cases) | Add a subsection explaining that symbols added dynamically by decorators are outside the scope of this static analysis phase. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-24 19:01:13 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | completeness | high | Section 4.2 rule 5 says non-scope elements are looked up via `scope.lookup(element.name)`, but doesn't specify what happens when `lookup()` raises `KeyError`. This can occur for elements extracted from AST that don't correspond to a symtable symbol (e.g., `__all__` assignments parsed as elements but not present as a named symbol in all contexts). | The requirements mention `KeyError` in the Symbol API table (Section 2.1) but Section 4.2 rule 5 doesn't specify error handling for failed lookups. This is distinct from unmatched scopes (Section 4.4) which covers child SymbolTables, not individual symbol lookups. | Section 4.2, add error handling clause for rule 5 | Test with an element name that doesn't exist in the parent scope's symbol table; confirm graceful handling (null symbol_info, not a crash). |
| R1-F2 | ambiguity | high | The applied suggestion R2-S2 says to use `(name, lineno)` as the primary matching key, but Section 4.2 still describes name-based matching with source-order disambiguation. The requirements body was not updated to reflect R2-S2. The applied suggestion and the section text are contradictory. | Appendix A records R2-S2 as applied, but Section 4.2 rules 3-4 still describe the original name-only matching with source-order pop strategy. An implementer reading the body would implement the original algorithm; an implementer reading Appendix A would implement (name, lineno) matching. | Section 4.2 rules 3-4 — update to reflect the (name, lineno) matching strategy from R2-S2 | Confirm that Section 4.2 body text matches the applied suggestion in Appendix A after revision. |
| R1-F3 | ambiguity | medium | Section 5.1 states `mode="static"` is the default and includes symtable, while `mode="ast_only"` skips it. But Section 5.2 says to "Update error message for unsupported modes from 'Phase 3+' to 'Phase 5+'". This implies the current codebase already has mode handling with a specific error message format. The requirements should document the current mode enum/validation logic so the delta is clear. | Without knowing the current implementation's mode handling, an implementer can't know whether they're adding mode support from scratch or modifying existing mode validation. The "update error message" instruction assumes existing infrastructure that isn't described. | Section 5.2 — add a brief description of current mode handling implementation or reference to the codebase | Review current `generate_file_manifest()` signature and mode validation; confirm requirements accurately describe the delta. |
| R1-F4 | completeness | medium | Section 3.3 specifies `SymbolInfo.is_closure` as `true` if `free_vars` is non-empty. But what about a function that contains a nested function that is a closure — should the outer function's `is_closure` also be `true`? The current definition only marks functions that themselves capture variables, not functions that contain closures. | The distinction matters for side-effect analysis (Section 10.3). A function that doesn't capture variables itself but contains a nested closure may still have complex scope interactions. Consumers need to know if `is_closure` is transitive or strictly per-scope. | Section 3.3, `is_closure` field description — clarify that this is strictly per-scope (the function itself captures free variables), not transitive | Test with `def outer(): x=1; def inner(): return x; return inner` — assert `outer.symbol_info.is_closure == False` and `inner.symbol_info.is_closure == True`. |
| R1-F5 | completeness | medium | The requirements do not specify thread safety for the augmentation function. If `generate_file_manifest()` is called concurrently on different files (e.g., during batch scanning), the `symtable.symtable()` call and the enrichment walk must be thread-safe. Since `symtable` is a CPython C module, its thread safety characteristics should be documented. | Batch scanning (mentioned in AP-2) implies concurrent execution. If `symtable.symtable()` holds the GIL during compilation (likely), concurrent calls will serialize, but the enrichment walk uses pure Python and could have issues if shared state is introduced. | Section 8 (Performance Budget) or Section 2.3 (Constraints) — add thread safety note | Review `symtable` CPython source for GIL behavior; confirm no shared mutable state in the enrichment function. |

