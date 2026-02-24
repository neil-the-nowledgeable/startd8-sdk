# Code Manifest Phase 5: Runtime Introspection Requirements

**Status:** Draft
**Date:** 2026-02-24
**Author:** Neil Yashinsky + agent:claude-code
**Parent:** [CODE_MANIFEST_REQUIREMENTS.md](CODE_MANIFEST_REQUIREMENTS.md) (Section 2.3, Section 9 Phase 5)
**Implements:** Layer 3 — `inspect`-based runtime introspection

---

## 1. Objective

Augment the existing AST + symtable manifest (Phases 1 + 3) with runtime introspection data from Python's `inspect` module and `typing.get_type_hints()`. This layer provides information that is not derivable from static analysis alone:

- **Resolved type annotations**: Forward references (`from __future__ import annotations`) evaluated to concrete types
- **Runtime signatures**: Actual callable signatures accounting for decorators, `*args`/`**kwargs`, and `__wrapped__` chains
- **Method Resolution Order (MRO)**: The full class hierarchy as resolved by Python's C3 linearization
- **Public API surface**: Module-level `__all__` and `__version__` as evaluated at import time
- **Runtime attributes**: Members visible on live objects but absent from AST (e.g., dataclass-generated fields, namedtuple attributes, metaclass-injected methods)

These signals enable downstream consumers to reason about resolved API surfaces, class hierarchies, and type contracts without manually importing and inspecting target modules.

**Constraint**: This layer requires importing the target module, which may trigger side effects. It is therefore **opt-in** via `mode="introspect"`.

---

## 2. `inspect` Module Overview

Runtime introspection uses several standard library functions to extract metadata from live Python objects after import. Key API surface:

### 2.1 Core Functions

| Function | Returns | Description | Risk |
|----------|---------|-------------|------|
| `inspect.signature(obj)` | `Signature` | Resolved parameters + return annotation. Follows `__wrapped__` chain (e.g., `@functools.wraps`). | Low |
| `inspect.getmro(cls)` | `tuple[type, ...]` | Method Resolution Order — the C3 linearization of base classes | Low |
| `typing.get_type_hints(obj)` | `dict[str, type]` | Resolved type annotations with forward references evaluated | Medium (`NameError` on unresolvable refs) |
| `inspect.getmembers(obj)` | `list[(name, value)]` | All members of an object (triggers descriptors and `__getattr__`) | Medium (side effects from property access) |
| `getattr(module, '__all__', None)` | `list[str]?` | Runtime public API surface (may be dynamically computed) | Low |
| `getattr(module, '__version__', None)` | `str?` | Module version string | Low |

### 2.2 `inspect.signature()` Details

`inspect.signature()` returns an `inspect.Signature` object containing:

| Attribute / Method | Returns | Description |
|--------------------|---------|-------------|
| `parameters` | `MappingProxy[str, Parameter]` | Ordered mapping of parameter name → `Parameter` |
| `return_annotation` | `type \| inspect.Parameter.empty` | Resolved return type annotation |
| `Parameter.name` | `str` | Parameter name |
| `Parameter.annotation` | `type \| inspect.Parameter.empty` | Resolved type annotation |
| `Parameter.default` | `any \| inspect.Parameter.empty` | Evaluated default value |
| `Parameter.kind` | `ParameterKind` | `POSITIONAL_ONLY`, `POSITIONAL_OR_KEYWORD`, `VAR_POSITIONAL`, `VAR_KEYWORD`, `KEYWORD_ONLY` |

### 2.3 Constraints

- **Requires importing the module**: May trigger module-level side effects (`print()`, file I/O, network calls, process spawning). Must be opt-in.
- **`typing.get_type_hints()` can fail**: Raises `NameError` when forward references cannot be resolved in the module's namespace (e.g., references to names not yet defined or from unimported modules).
- **`inspect.getmembers()` triggers descriptors**: Accessing properties and `__getattr__` during member enumeration can cause side effects or raise exceptions.
- **C extensions**: `inspect.signature()` raises `ValueError` for C-implemented builtins without `__text_signature__`.
- **Deterministic for a given environment**: Same source + same Python version + same installed packages → same output. Different environments may yield different results (e.g., different `__all__` if dynamically computed based on optional dependencies).

---

## 3. Schema Extensions

All new fields are **additive** per the schema versioning contract (parent requirements Section 3.5). Schema version bumps from `"1.3.0"` to `"1.4.0"` (Phase 6 bytecode call graph already occupies `"1.3.0"`).

### 3.1 New `ParseErrorKind` Value

Add one value to the existing `ParseErrorKind` enum:

| Value | Description |
|-------|-------------|
| `IMPORT_ERROR = "import_error"` | Module could not be imported during introspect mode (timeout, `ImportError`, `ModuleNotFoundError`, or other exception) |

This extends the existing enum (`syntax_error`, `encoding_error`, `io_error`, `partial_parse`) without removing or redefining any values.

### 3.2 New Model: `ResolvedParam`

Per-parameter detail from `inspect.signature()`, providing the runtime-resolved view of a function parameter.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `string` | required | Parameter name (bare identifier, no `*`/`**` prefix) |
| `annotation` | `string?` | `null` | Resolved type annotation as a string. `null` if no annotation or `inspect.Parameter.empty`. Forward references are resolved via `typing.get_type_hints()`. |
| `default` | `string?` | `null` | `repr()` of the evaluated default value. `null` if no default or `inspect.Parameter.empty`. |
| `kind` | `ParamKind` | `positional` | Same enum as AST-derived `Param` (`positional`, `keyword`, `var_positional`, `var_keyword`, `positional_only`, `keyword_only`) |
| `has_default` | `bool` | `false` | Whether the parameter has a default value (including `None` as an explicit default) |

**Mapping from `inspect.Parameter.kind`:**

| `inspect.Parameter.kind` | `ParamKind` value |
|---------------------------|-------------------|
| `POSITIONAL_ONLY` | `positional_only` |
| `POSITIONAL_OR_KEYWORD` | `positional` |
| `VAR_POSITIONAL` | `var_positional` |
| `VAR_KEYWORD` | `var_keyword` |
| `KEYWORD_ONLY` | `keyword_only` |

### 3.3 New Model: `ResolvedSignature`

Runtime-resolved callable signature, combining `inspect.signature()` with `typing.get_type_hints()`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `params` | `list[ResolvedParam]` | `[]` | Runtime-resolved parameters in declaration order |
| `return_annotation` | `string?` | `null` | Resolved return type as a string. `null` if no return annotation. |

### 3.4 New Model: `InspectInfo`

Scope-level runtime introspection data attached to each manifest `Element`. Analogous to `SymbolInfo` from Phase 3 — a separate model because the data source, availability, and failure modes are fundamentally different.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `resolved_signature` | `ResolvedSignature?` | `null` | For callables: runtime-resolved signature from `inspect.signature()`. `null` for non-callable elements. |
| `mro` | `list[string]` | `[]` | For classes: Method Resolution Order as fully-qualified name strings (e.g., `["mymodule.Child", "mymodule.Parent", "builtins.object"]`). Empty for non-class elements. |
| `resolved_annotations` | `dict[str, str]` | `{}` | Resolved type hints from `typing.get_type_hints()`. Keys are attribute/parameter names, values are string representations of the resolved types. Empty if `get_type_hints()` fails. |
| `runtime_attributes` | `list[string]` | `[]` | Attribute names visible via `inspect.getmembers()` but not present in the AST class body (e.g., dataclass-generated `__init__`, `__repr__`, namedtuple `_fields`). |
| `is_callable` | `bool` | `false` | Whether the object is callable at runtime (has `__call__`). |
| `qualname` | `string?` | `null` | `__qualname__` from the runtime object. Useful for confirming nested function/class identity. |

All list fields are sorted alphabetically for deterministic output. Dict keys in `resolved_annotations` are sorted alphabetically.

**Design decision — separate `InspectInfo` vs extending `SymbolInfo`**: These models represent different data sources with different availability (symtable is always available for valid syntax; inspect requires successful import), different failure modes (symtable never has side effects; inspect may trigger them), and different opt-in semantics. Keeping them separate ensures consumers can check each independently.

### 3.5 Element Model Extension

Add one field to the existing `Element` schema:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `inspect_info` | `InspectInfo?` | `null` | Runtime introspection data. `null` when introspect mode is disabled, the element could not be resolved at runtime, or the module failed to import. |

**Backward compatibility**: `inspect_info` defaults to `null`, so Phase 1/Phase 3 manifests remain valid. Consumers check `element.inspect_info is not None` to determine if introspection data is available.

### 3.6 FileManifest Extensions

Add two fields to the existing `FileManifest` schema:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `module_all` | `list[string]?` | `null` | Runtime `__all__` from the imported module. `null` if module has no `__all__` or import failed. Distinct from AST-extracted `__all__` (which only captures literal lists). |
| `module_version` | `string?` | `null` | Runtime `__version__` from the imported module. `null` if module has no `__version__` or import failed. |

### 3.7 Schema Version

- **Phase 1**: `"1.0.0"` (AST extraction)
- **Phase 2**: `"1.1.0"` (reserved for docstring/decorator enrichment per parent Section 9)
- **Phase 3**: `"1.2.0"` (symtable augmentation)
- **Phase 4**: No schema bump (pipeline integration — pure consumer, no schema changes)
- **Phase 6**: `"1.3.0"` (bytecode call graph analysis)
- **Phase 5**: `"1.4.0"` (inspect augmentation: `InspectInfo`, `ResolvedSignature`, `ResolvedParam`, `ParseErrorKind.IMPORT_ERROR`, `FileManifest.module_all`, `FileManifest.module_version`)

The bump is a **minor** version increment because all changes are additive (new optional fields, new enum value). No existing fields are removed or redefined.

---

## 4. Import Isolation Strategy

Unlike symtable (pure static analysis), inspect requires importing the target module. This section specifies the controlled import mechanism.

### 4.1 Primary: In-Process with Guards

A `_guarded_import()` context manager provides import isolation:

```
@contextmanager
def _guarded_import(module_path: str, project_root: Path, timeout_s: float = 10.0):
    """
    Import a module with sys.path/sys.modules isolation and timeout.

    Yields the imported module on success, None on failure.
    Logs at INFO level when introspect mode activates (side-effect visibility).
    """
```

**Isolation steps:**

1. **Save state**: Snapshot `sys.path[:]` and `set(sys.modules.keys())`.
2. **Inject paths**: Prepend `project_root` and `project_root / "src"` to `sys.path`.
3. **Import with timeout**: Launch import in a daemon thread with `timeout_s` ceiling.
   - Primary: `importlib.import_module(module_path)` for package-resolvable modules.
   - Fallback: `importlib.util.spec_from_file_location()` for non-package files (standalone scripts).
4. **Yield module** on success, `None` on failure (with `IMPORT_ERROR` in manifest errors).
5. **Restore state**: Restore `sys.path` via slice assignment. Remove any new `sys.modules` entries added during import (entries present before import are left untouched).
6. **Log**: INFO-level log on introspect activation: `"Introspect mode: importing {module_path}"`.

**Timeout mechanism**: Threading-based (daemon thread + `threading.Event` wait). Cross-platform — unlike `signal.alarm()` which is POSIX-only and main-thread-only. Default timeout: 10 seconds.

**Error handling**: Any exception during import (including `ImportError`, `ModuleNotFoundError`, `SyntaxError`, `TimeoutError`, and arbitrary exceptions from module-level code) is caught, logged at WARNING level with `exc_info=True`, and recorded as a `ParseErrorKind.IMPORT_ERROR` in the manifest's `errors` list. The AST + symtable data remains intact.

### 4.2 Rationale: Why Not Subprocess Isolation?

Introspect mode is **opt-in** and targets the project's own trusted code. Subprocess isolation (`subprocess.run([sys.executable, ...])`) would add ~200ms per file for process startup alone, making batch processing impractical (e.g., 100 files → 20s overhead before any actual introspection). The in-process approach with guards is sufficient for trusted code and maintains the performance budget.

If untrusted code isolation becomes a requirement in the future, subprocess isolation can be added as a separate mode without changing the schema or the `InspectInfo` model.

### 4.3 Module Path Resolution

The module path for `importlib.import_module()` is derived from the file path using the same algorithm as FQN computation (parent requirements Section 4.1):

```
file_path relative to project_root → strip "src/" prefix → replace "/" with "." → strip ".py"
```

Example: `src/startd8/utils/code_manifest.py` → `startd8.utils.code_manifest`

For files outside the `src/` layout (e.g., `scripts/run_artisan_workflow.py`), the fallback uses `importlib.util.spec_from_file_location()` with the file path directly.

---

## 5. Object Matching Algorithm

Unlike symtable (scope tree walk with parallel traversal), inspect matches by attribute lookup on the live module object. There is no tree structure to walk — each element is resolved independently.

### 5.1 Matching Rules

1. **Top-level elements**: `getattr(module, element.name, None)`. Returns the live object (function, class, variable value) or `None` if not found.

2. **Class children (methods, properties)**: First resolve the class via `getattr(module, class_element.name, None)`, then resolve children via `getattr(class_obj, child_element.name, None)`.

3. **Property triads**: For elements with `@getter`/`@setter`/`@deleter` FQN suffixes:
   - Resolve the property descriptor via `getattr(class_obj, base_name, None)`.
   - If it is a `property` instance, extract `prop.fget`, `prop.fset`, or `prop.fdel` based on the FQN suffix.
   - Introspect the extracted accessor function.

4. **Overloaded methods**: Only the implementation definition (the non-`@overload` variant, with `overload_index is None`) gets introspected. `@typing.overload` variants are type-checker-only constructs and do not exist as separate objects at runtime. Overload variants retain `inspect_info: null`.

5. **Nested functions**: Functions defined inside other functions are **not resolvable** via `getattr()` at runtime — they are local variables of the enclosing function, not attributes of the module or class. `inspect_info` remains `null` for nested functions. This is a documented limitation.

6. **Class variables**: Resolved via `getattr(class_obj, var_name, None)`. For simple values, `is_callable` is set; for descriptors, the descriptor protocol is followed.

### 5.2 Per-Element Introspection

For each successfully resolved object:

1. **Callables** (functions, methods, async variants):
   - `inspect.signature(obj)` → `resolved_signature`
   - `typing.get_type_hints(obj)` → `resolved_annotations`
   - `obj.__qualname__` → `qualname`
   - `callable(obj)` → `is_callable`

2. **Classes**:
   - `inspect.getmro(cls)` → `mro` (as list of `type.__module__ + "." + type.__qualname__` strings)
   - `typing.get_type_hints(cls)` → `resolved_annotations` (class-level annotations)
   - `inspect.getmembers(cls)` filtered against AST-visible names → `runtime_attributes`
   - `inspect.signature(cls)` → `resolved_signature` (the `__init__` signature)
   - `obj.__qualname__` → `qualname`
   - `is_callable = True` (classes are callable)

3. **Variables/Constants**: Minimal introspection.
   - `callable(value)` → `is_callable`
   - `value.__qualname__` → `qualname` (if available)

### 5.3 Defensive Per-Element Error Handling

Each element's introspection is wrapped in `try/except Exception`:
- A failure on one element does **not** block sibling elements.
- Failures are logged at WARNING level with `exc_info=True`.
- The failed element retains `inspect_info: null` while successfully introspected siblings receive populated `InspectInfo`.
- The overall manifest is returned with whatever data was successfully gathered.

This follows the same per-task error guard pattern used in Phase 3's symtable enrichment.

---

## 6. Generation Mode Integration

### 6.1 Mode Table

| Mode | AST | symtable | inspect | Description |
|------|-----|----------|---------|-------------|
| `ast_only` | Yes | No | No | Phase 1 only. Pure AST extraction. |
| `static` (default) | Yes | Yes | No | Phases 1 + 3. Full static analysis. |
| `introspect` | Yes | Yes | Yes | Phases 1 + 3 + 5. Static + runtime introspection. |
| `full` | Yes | Yes | Yes | Future Phase 6 — raises `NotImplementedError("Phase 6")`. |

### 6.2 `generate_file_manifest()` Changes

- `mode="introspect"` is now **accepted** (no longer raises `NotImplementedError`).
- `mode="full"` raises `NotImplementedError("Mode 'full' requires Phase 6 implementation")`.
- Unknown mode values raise `ValueError(f"Unknown mode: '{mode}'")`.
- In `introspect` mode:
  1. AST extraction runs first (Phase 1).
  2. Symtable augmentation runs second (Phase 3) — introspect mode includes symtable.
  3. Inspect augmentation runs third (Phase 5) — only in `introspect` mode.
- The inspect block runs **after** symtable, so elements already have `symbol_info` populated when inspect enrichment begins.
- If the module fails to import, AST + symtable data is intact; only `inspect_info` fields are `null`.

### 6.3 Defensive Error Handling

The entire inspect augmentation block is wrapped in a broad `except Exception` catch (same pattern as Phase 3's symtable augmentation):
- On failure, the manifest is returned with AST + symtable data intact and all `inspect_info` fields as `null`.
- Logged at WARNING level with `exc_info=True` (an import failure after successful AST parse + symtable is anomalous and worth investigating).
- The import failure is recorded in the manifest's `errors` list as `ParseErrorKind.IMPORT_ERROR`.

---

## 7. Cache Compatibility

### 7.1 Schema Version Gate

`SCHEMA_VERSION` bumped to `"1.4.0"` → auto-invalidates all cached manifests generated by Phase 6 code (`"1.3.0"`). Cache hit check:

```
cache hit = (cached.digest == current_digest)
            AND (cached.schema_version == SCHEMA_VERSION)
            AND (cached._meta.get("python_version") == current_python_version)
```

The Python version check (added in Phase 3 per R2-S6) remains in effect.

### 7.2 Mode-Aware Cache

The cache index stores `"mode"` in the `_meta` section. A mode mismatch invalidates the cache entry:

- `static` cache is discarded when regenerating with `introspect`.
- `introspect` cache is discarded when regenerating with `static` (the cached manifest may have `inspect_info` data that should not be served for `static` mode).
- `ast_only` cache is discarded for both `static` and `introspect`.

### 7.3 Forward/Backward Loading

- **`inspect_info` defaults to `null`** → Phase 3 manifests load in Phase 5 code without validation errors.
- **Pydantic `model_validate()` ignores unknown fields** → Phase 5 manifests load in Phase 3 code (unknown `inspect_info` field is silently ignored).
- **`module_all` and `module_version` default to `null`** → backward compatible on `FileManifest`.

---

## 8. Edge Cases

### 8.1 Nested Functions

Not inspectable at runtime. Local functions are variables in the enclosing function's scope, not attributes of the module or class. `inspect_info` remains `null`. Consumers should rely on AST + symtable data for nested functions.

### 8.2 Forward References (`from __future__ import annotations`)

When PEP 563 deferred evaluation is active, all annotations are strings at the AST level. `typing.get_type_hints(obj)` resolves them by evaluating in the module's namespace. If resolution fails (e.g., a referenced type is not importable), `get_type_hints()` raises `NameError`. The handler catches this and returns empty `resolved_annotations` — the AST-level string annotations remain in the existing `signature` field.

### 8.3 `__all__` Discrepancy

AST-extracted `__all__` (from `is_reexport` detection) only captures literal list/tuple assignments. Runtime `__all__` (via `getattr(module, '__all__', None)`) captures dynamically computed values (e.g., `__all__ = [name for name in dir() if not name.startswith('_')]`). Both are preserved independently:
- AST-level: used by `is_reexport` heuristic in Phase 1.
- Runtime-level: stored in `FileManifest.module_all` in Phase 5.

### 8.4 C Extensions

`inspect.signature()` raises `ValueError` for C-implemented builtins and extension types that lack `__text_signature__`. The per-element error handler catches this → `resolved_signature` is `null`. Other fields (`mro`, `resolved_annotations`) may still be populated.

### 8.5 Import Timeout

If the module import exceeds the 10-second timeout (e.g., long-running module-level computation, blocking I/O), the daemon thread is abandoned and `_guarded_import()` yields `None`. An `IMPORT_ERROR` is recorded in the manifest's errors list with a message indicating the timeout. AST + symtable data remains intact.

### 8.6 Property Descriptors

Properties are resolved to their accessor functions (`fget`, `fset`, `fdel`) based on the Element's FQN suffix. `inspect.signature(prop.fget)` provides the getter's signature. If the property object is not a `property` instance (e.g., a custom descriptor), `resolved_signature` is `null`.

### 8.7 `@functools.wraps` Decorated Functions

`inspect.signature()` follows the `__wrapped__` attribute chain by default, returning the signature of the original (inner) function. This means the `resolved_signature` reflects the true callable interface, not the wrapper's `(*args, **kwargs)`. This is the desired behavior for API surface documentation.

### 8.8 Dataclass Fields

Dataclass-generated methods (`__init__`, `__repr__`, `__eq__`, etc.) are not present in the AST class body. They appear in `runtime_attributes` (visible via `inspect.getmembers()` but absent from AST children). The class's `resolved_signature` (from `inspect.signature(cls)`) reflects the generated `__init__` parameters including field types and defaults.

### 8.9 Circular Imports

A module that imports the manifest generator itself (or creates an import cycle) is handled by Python's standard import machinery: `sys.modules` contains the partially-initialized module, and `importlib.import_module()` returns it without re-executing the module body. This may result in incomplete introspection data (missing attributes not yet defined at the point of the circular import). The per-element error handler catches any resulting `AttributeError`.

### 8.10 `exec()`/`eval()` Generated Code

Dynamically generated code is not visible to AST or symtable. Inspect may partially recover it: members injected into a class or module via `exec()`/`eval()` are visible through `inspect.getmembers()` and appear in `runtime_attributes`. However, no guarantees are made about completeness or naming for dynamically generated code. This is explicitly out of scope for comprehensive coverage.

### 8.11 `sys.path` and `sys.modules` Restoration

After introspection completes (success or failure), `_guarded_import()` must restore both `sys.path` and `sys.modules` to their pre-import state:
- `sys.path` is restored via slice assignment (`sys.path[:] = saved_path`).
- New `sys.modules` entries (keys not in the saved snapshot) are removed via `del sys.modules[key]`.
- Entries that existed before import are never removed (even if the import modified them).

This ensures the manifest generator does not permanently alter the Python environment.

---

## 9. Performance Budget

| Operation | Target | Notes |
|-----------|--------|-------|
| Inspect overhead per file | < 500ms | Dominated by `importlib.import_module()` time. `inspect.signature()` and `inspect.getmembers()` are fast on already-loaded objects. |
| Total introspect mode per file | < 600ms | AST (~100ms) + symtable (~10ms) + inspect (~500ms) |
| Total static mode per file | < 110ms | No regression from Phase 5 code in static mode |
| Batch processing (static mode) | < 10s | No regression — inspect block is skipped entirely |
| Import timeout | 10s | Per-file ceiling prevents runaway imports from blocking batch |

### 9.1 Performance Strategy

- **Import dominates cost**: The `importlib.import_module()` call accounts for the majority of per-file overhead. Once the module is loaded, `inspect.signature()`, `inspect.getmro()`, and `typing.get_type_hints()` are near-instantaneous (microseconds).
- **Shared dependencies in `sys.modules`**: When processing multiple files from the same project, shared dependencies (e.g., `pydantic`, `typing`) are already in `sys.modules` after the first import. Subsequent imports are faster because only the target module's code executes.
- **No batch module cache (deferred)**: Each file re-imports independently via `_guarded_import()` which cleans `sys.modules` after each file. A future optimization could maintain a module cache across a batch run, but this risks stale state and is deferred.
- **Static mode unaffected**: The inspect code path is gated behind `mode == "introspect"`. Static mode performance is identical to Phase 3.

---

## 10. Acceptance Criteria

### 10.1 Functional

| # | Criterion | Verification |
|---|-----------|-------------|
| AC-I1 | `InspectInfo` model is frozen and has correct defaults | `InspectInfo()` creates valid instance: `resolved_signature=None`, `mro=[]`, `resolved_annotations={}`, `runtime_attributes=[]`, `is_callable=False`, `qualname=None` |
| AC-I2 | `mode="introspect"` accepted (no longer raises) | `generate_file_manifest(..., mode="introspect")` returns a `FileManifest` without raising `NotImplementedError` |
| AC-I3 | `mode="full"` raises `NotImplementedError` with "Phase 6" | `generate_file_manifest(..., mode="full")` raises `NotImplementedError` with message containing `"Phase 6"` (updated from `"Phase 5+"`) |
| AC-I4 | Resolved signatures for functions | For `def greet(name: str, greeting: str = "Hello") -> str`, `inspect_info.resolved_signature.params` has 2 entries with correct names, annotations, defaults, and kinds |
| AC-I5 | Forward ref annotations resolved | File with `from __future__ import annotations` and `def f(x: MyClass) -> MyClass` → `resolved_annotations` has `"x": "module.MyClass"`, `"return": "module.MyClass"` |
| AC-I6 | Class MRO chain | For `class Child(Parent)`, `inspect_info.mro == ["module.Child", "module.Parent", "builtins.object"]` |
| AC-I7 | Module `__all__` extracted | File with `__all__ = ["foo", "bar"]` → `manifest.module_all == ["foo", "bar"]` |
| AC-I8 | Module `__version__` extracted | File with `__version__ = "1.2.3"` → `manifest.module_version == "1.2.3"` |
| AC-I9 | Runtime attributes detected | Dataclass with `field: int` → `__init__` in `runtime_attributes` (generated, not in AST) |
| AC-I10 | Import failure → `IMPORT_ERROR` in errors | File that raises `ImportError` at module level → `errors` contains `ParseErrorKind.IMPORT_ERROR`; AST + symtable data intact; all `inspect_info` are `null` |
| AC-I11 | Per-element failure doesn't block siblings | Class where `inspect.signature()` fails on one method → other methods still have populated `inspect_info` |
| AC-I12 | Schema version is `"1.4.0"` | `manifest.schema_version == "1.4.0"` |
| AC-I13 | Backward compat: `None` default | `Element(...)` without `inspect_info` field still creates valid instance (defaults to `None`) |
| AC-I14 | `static` mode has no `inspect_info` | `generate_file_manifest(..., mode="static")` → all elements have `inspect_info is None` |
| AC-I15 | `ast_only` mode has no `inspect_info` | `generate_file_manifest(..., mode="ast_only")` → all elements have `inspect_info is None` |
| AC-I16 | Introspect mode also runs symtable | `generate_file_manifest(..., mode="introspect")` → elements have both `symbol_info` and `inspect_info` populated |
| AC-I17 | Determinism | Same file + same Python environment → `inspect_info` output is byte-identical across runs |
| AC-I18 | `sys.path` restored after introspect | `sys.path` is identical before and after `generate_file_manifest(..., mode="introspect")` |
| AC-I19 | `sys.modules` cleaned after introspect | No new permanent entries in `sys.modules` after `generate_file_manifest(..., mode="introspect")` |

### 10.2 Performance

| # | Criterion | Verification |
|---|-----------|-------------|
| AP-I1 | Inspect overhead < 500ms per file | Benchmark `mode="introspect"` vs `mode="static"` on `code_manifest.py` itself |
| AP-I2 | No batch regression in static mode | `startd8 manifest generate --verbose` still completes in < 10s |

### 10.3 Cache

| # | Criterion | Verification |
|---|-----------|-------------|
| AC-C1 | Schema upgrade invalidates cache | Phase 6 cache entries (`"1.3.0"`) regenerated on first Phase 5 run |
| AC-C2 | Phase 3 manifests load in Phase 5 | `inspect_info` is `null`, no validation error |
| AC-C3 | Mode change invalidates cache | `static` cache discarded when switching to `introspect`; `introspect` cache discarded when switching to `static` |

---

## 11. Downstream Consumer Guidance

### 11.1 Checking for Inspect Data

```python
# Check for inspect data on an element
if element.inspect_info is not None:
    if element.inspect_info.resolved_signature:
        sig = element.inspect_info.resolved_signature
        print(f"Resolved params: {[p.name for p in sig.params]}")
        print(f"Return type: {sig.return_annotation}")
    if element.inspect_info.mro:
        print(f"MRO: {' -> '.join(element.inspect_info.mro)}")
    if element.inspect_info.resolved_annotations:
        print(f"Resolved types: {element.inspect_info.resolved_annotations}")
```

### 11.2 Module-Level API Surface

```python
# Runtime public API
if manifest.module_all is not None:
    print(f"Public API ({len(manifest.module_all)} names): {manifest.module_all}")

# Module version
if manifest.module_version is not None:
    print(f"Version: {manifest.module_version}")
```

### 11.3 Comparing AST vs Runtime Signatures

```python
# Detect signature discrepancies (e.g., decorator modifications)
if element.signature and element.inspect_info and element.inspect_info.resolved_signature:
    ast_params = {p.name for p in element.signature.params}
    runtime_params = {p.name for p in element.inspect_info.resolved_signature.params}
    if ast_params != runtime_params:
        print(f"Signature mismatch in {element.fqn}: AST={ast_params}, runtime={runtime_params}")
```

### 11.4 Forward Reference Resolution

```python
# Use resolved annotations when available, fall back to AST annotations
def get_annotation(element, param_name: str) -> str | None:
    # Prefer runtime-resolved annotation (handles forward refs)
    if element.inspect_info and element.inspect_info.resolved_annotations:
        resolved = element.inspect_info.resolved_annotations.get(param_name)
        if resolved:
            return resolved
    # Fall back to AST-level annotation
    if element.signature:
        for p in element.signature.params:
            if p.name == param_name:
                return p.annotation
    return None
```

---

## Appendix: Iterative Review Log

### Reviewer Instructions

Same instructions as the parent requirements document (see CODE_MANIFEST_REQUIREMENTS.md Appendix) and Phase 3 requirements document.

### Areas Substantially Addressed

*(Awaiting first review round)*

### Areas Needing Further Review

*(Awaiting first review round)*

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

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

*(Awaiting first review round)*
