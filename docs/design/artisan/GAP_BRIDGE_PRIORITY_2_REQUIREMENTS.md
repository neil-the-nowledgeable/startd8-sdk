# Gap Bridge Priority 2: Phase 5 Introspect Registry Foundation

**Version:** 1.0.0
**Created:** 2026-02-26
**Status:** Draft
**Parent:** [ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md](ARTISAN_FEATURE_COVERAGE_GAP_ANALYSIS.md)
**Extends:** [CODE_MANIFEST_PHASE5_PIPELINE_REQUIREMENTS.md](../CODE_MANIFEST_PHASE5_PIPELINE_REQUIREMENTS.md)
**Scope:** Implement the missing `ManifestRegistry` extension methods and wire them into the highest-value consumers (DESIGN MRO + resolved types, IMPLEMENT resolved types, PREFLIGHT `module_all`).

---

## 1. Goal

Phase 5 pipeline adoption (`CODE_MANIFEST_PHASE5_PIPELINE_REQUIREMENTS.md`) is blocked because
none of the required `ManifestRegistry` extension methods were implemented. The `enable_introspect`
flag and its consumers exist, but calling them raises `AttributeError` at runtime. This document
specifies the missing method implementations and their wiring into the top-priority consumers.

---

## 2. Foundation: ManifestRegistry Extension Methods

### 2.1 `file_element_summary(include_resolved_types=)` Kwarg

**Requirement (DS-1, IM-1):** Add `include_resolved_types: bool = False` keyword argument to the
existing `ManifestRegistry.file_element_summary()` method.

**Behavior:**

- When `include_resolved_types=True` and `element.inspect_info.resolved_signature` is available,
  render the resolved parameter types instead of AST-extracted types in the element summary.
- When `include_resolved_types=False` (default), behavior is identical to the current implementation.
- Fallback: if `inspect_info is None`, use the AST signature regardless.

**Format example:**

```
# AST signature (current):
def process(data: 'DataFrame') -> None:

# Resolved signature (with include_resolved_types=True):
def process(data: pandas.core.frame.DataFrame) -> None:
```

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.2 `file_resolved_type_summary(relative_path, budget_chars=2000)`

**Requirement (PR-1, DS-1):** New method returning a compact LLM-readable summary of resolved
types for a file's callable elements.

**Signature:**

```python
def file_resolved_type_summary(
    self, relative_path: str, budget_chars: int = 2000
) -> str:
```

**Behavior:**

- Iterate over elements in the file that have `inspect_info.resolved_signature`.
- Format each as: `element_name: (param: Type, ...) -> ReturnType`
- Progressive truncation: if total chars exceed `budget_chars`, drop lower-priority elements
  (non-public, then private) until within budget.
- Return empty string if no elements have resolved type data.
- Return empty string if file not found in registry (graceful degradation).

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.3 `file_mro_summary(relative_path)`

**Requirement (DS-2):** New method returning MRO chains for all class elements in a file.

**Signature:**

```python
def file_mro_summary(
    self, relative_path: str
) -> dict[str, list[str]]:
```

**Behavior:**

- Iterate over class elements in the file that have `inspect_info.mro`.
- Return `{class_fqn: mro_list}` where `mro_list` excludes `"builtins.object"` (too noisy).
- Only include classes where `len(mro_list) > 1` (i.e., has actual inheritance beyond object).
- Return empty dict if no eligible classes, or file not in registry.

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.4 `file_runtime_attributes(relative_path)`

**Requirement (DS-4, IM-2):** New method returning runtime-only attributes for dataclass /
namedtuple elements.

**Signature:**

```python
def file_runtime_attributes(
    self, relative_path: str
) -> dict[str, list[str]]:
```

**Behavior:**

- Iterate over elements with `inspect_info.runtime_attributes` that is non-empty.
- Return `{element_fqn: runtime_attributes_list}`.
- Return empty dict if no elements, or file not in registry.

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.5 `module_all_for(relative_path)`

**Requirement (DS-3, IN-3, PF-1):** New method returning the runtime `__all__` list for a file.

**Signature:**

```python
def module_all_for(
    self, relative_path: str
) -> list[str] | None:
```

**Behavior:**

- Return `FileManifest.module_all` for the given file, or `None` if:
  - File not in registry.
  - `FileManifest.module_all` is `None` (no introspect data, or module has no `__all__`).
- Never raise; return `None` on any error.

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.6 `module_version_for(relative_path)`

**Requirement (PI-1):** New method returning the runtime `__version__` for a file.

**Signature:**

```python
def module_version_for(
    self, relative_path: str
) -> str | None:
```

**Behavior:**

- Return `FileManifest.module_version` for the given file, or `None` if absent.
- Never raise.

**File:** `src/startd8/utils/manifest_registry.py`

---

### 2.7 `dead_candidates(use_runtime_callable=False)` Kwarg

**Requirement (CG-1):** Add `use_runtime_callable: bool = False` keyword argument to the existing
`ManifestRegistry.dead_candidates()` method.

**Behavior:**

- When `use_runtime_callable=True`:
  - Include elements where `inspect_info.is_callable = True` regardless of `ElementKind`.
  - Exclude elements where `inspect_info.is_callable = False` even if `ElementKind` is callable.
- When `use_runtime_callable=False` (default): identical to current behavior.

**File:** `src/startd8/utils/manifest_registry.py`

---

## 3. ManifestDiff Extensions

### 3.1 `changed_resolved_signatures`

**Requirement (IN-1):** New field on `ManifestDiff` listing elements whose resolved signatures
changed between old and new manifests.

**Type:** `list[tuple[str, str, str]]` — `(fqn, old_resolved, new_resolved)`

**Population:** In `ManifestDiff.diff()`, when both the old and new element have
`inspect_info.resolved_signature`, compare them. Populate `changed_resolved_signatures` with
triples where `old_resolved != new_resolved`.

**When empty:** List remains empty when either manifest lacks introspect data (graceful degradation).

**File:** `src/startd8/utils/manifest_registry.py`

---

### 3.2 `mro_changes`

**Requirement (IN-2):** New field detecting class inheritance restructuring.

**Type:** `list[tuple[str, list[str], list[str]]]` — `(fqn, old_mro, new_mro)`

**Population:** When both old and new class elements have `inspect_info.mro`, compare lists.
If changed, append to `mro_changes`.

**Consumer:** `IntegrationEngine._manifest_pre_merge_diff()` should emit `WARNING` via
`GateEmitter` with `gate_name="manifest_mro_change"` for each entry.

**File:** `src/startd8/utils/manifest_registry.py`

---

### 3.3 `module_all_diff`

**Requirement (IN-3):** New field reporting additions and removals from `__all__`.

**Type:** `tuple[list[str], list[str]] | None` — `(added, removed)`, or `None` if either
manifest lacks `module_all`.

**Consumer:** `IntegrationEngine._manifest_pre_merge_diff()` logs added/removed exports at INFO.

**File:** `src/startd8/utils/manifest_registry.py`

---

## 4. Consumer Wiring: DESIGN Phase

### 4.1 Resolved Types in T1 Manifest Context (DS-1)

**Requirement:** When `enable_introspect=True`, pass `include_resolved_types=True` to
`file_element_summary()` for all target files in `DesignPhaseHandler._task_to_feature_context()`.

**Implementation:**

```python
summary = registry.file_element_summary(
    file_path,
    include_resolved_types=self.config.enable_introspect,
)
```

**File:** `src/startd8/contractors/context_seed_handlers.py` — `DesignPhaseHandler._task_to_feature_context()`

---

### 4.2 MRO Chain in Design Context (DS-2)

**Requirement:** When `enable_introspect=True` and `file_mro_summary()` returns non-empty data
for a target file, append a `Class Hierarchy` subsection to `manifest_context`.

**Format:**

```
### Class Hierarchy
- MyService: [MyService → BaseService → IService]
- MyModel: [MyModel → BaseModel]
```

**File:** `src/startd8/contractors/context_seed_handlers.py` (same method as DS-1)

---

### 4.3 `public_api_surface` from `module_all` in Design Metadata (DS-3)

**Requirement:** When `enable_introspect=True` and `module_all_for()` returns a non-None list,
include it in `additional_context["public_api_surface"]` as a string list.

**Tier:** Tier 3 (advisory; droppable under budget pressure).

**File:** `src/startd8/contractors/context_seed_handlers.py` and `src/startd8/contractors/prompt_utils.py`
(add `public_api_surface` to `CONTEXT_FIELD_TIERS` at T3).

---

### 4.4 Runtime Attributes in Design Context (DS-4)

**Requirement:** When `enable_introspect=True` and `file_runtime_attributes()` returns non-empty
data for a target file, append a `Generated Members` line to the element's summary.

**Format:**

```
### Generated Members (dataclass/namedtuple)
- UserModel: [id, name, email, created_at]  ← runtime-only, do NOT redefine these
```

**File:** `src/startd8/contractors/context_seed_handlers.py` (same method as DS-1)

---

## 5. Consumer Wiring: IMPLEMENT Phase

### 5.1 Resolved Types in Chunk Metadata (IM-1)

**Requirement:** When `enable_introspect=True`, replace AST-extracted signatures with resolved
signatures in `chunk.metadata["_manifest_context"]` (the Code Structure section).

**Implementation:** Pass `include_resolved_types=self.config.enable_introspect` when calling
`file_element_summary()` inside `ImplementPhaseHandler._tasks_to_chunks()`.

**File:** `src/startd8/contractors/context_seed_handlers.py` — `ImplementPhaseHandler._tasks_to_chunks()`

---

### 5.2 Runtime Attributes for Dataclass Tasks (IM-2)

**Requirement:** When `enable_introspect=True` and a chunk targets a dataclass or namedtuple
(detected via non-empty `file_runtime_attributes()`), include generated member names in the
`## Code Structure` section.

**Format:**

```
## Code Structure
...
UserModel (dataclass) — Generated members (do NOT redefine): id, name, email, created_at
```

**File:** `src/startd8/contractors/artisan_phases/development.py` — `_build_manifest_context()`

---

## 6. Consumer Wiring: PREFLIGHT Phase

### 6.1 `module_all` Validation (PF-1)

**Requirement:** When `enable_introspect=True` and `module_all_for()` returns a non-None list,
validate that every name in `module_all` exists as an element in the manifest for that file.
Flag missing names as WARNING.

**Implementation:** Add this check to `CallGraphValidator` (already registered in `_registry.py`)
as a new `validate_module_all()` method called from `run()`.

**Error message format:**

```
Module exports 'X' in __all__ but no element 'X' found in {file_path}.
```

**File:** `src/startd8/workflows/builtin/preflight_rules/call_graph_validator.py`

---

## 7. Prompt Rendering: Tiered Context Extension

### 7.1 Register `manifest_resolved_types` as T1 (PR-1)

**Requirement:** Add `manifest_resolved_types` as a Tier 1 field in `CONTEXT_FIELD_TIERS`.

**Constraint:** Under budget pressure, `manifest_resolved_types` must be dropped **before**
`manifest_context` (structural data is more fundamental than resolved type annotations).

**File:** `src/startd8/contractors/prompt_utils.py` — `CONTEXT_FIELD_TIERS`

### 7.2 Register `public_api_surface` as T3 (PR-3)

**Requirement:** Add `public_api_surface` as a Tier 3 field in `CONTEXT_FIELD_TIERS`.

**File:** `src/startd8/contractors/prompt_utils.py` — `CONTEXT_FIELD_TIERS`

---

## 8. Proposed Changes Summary

| File | Change | Section |
|------|--------|---------|
| `src/startd8/utils/manifest_registry.py` | Add `include_resolved_types` kwarg to `file_element_summary()` | §2.1 |
| `src/startd8/utils/manifest_registry.py` | New method: `file_resolved_type_summary()` | §2.2 |
| `src/startd8/utils/manifest_registry.py` | New method: `file_mro_summary()` | §2.3 |
| `src/startd8/utils/manifest_registry.py` | New method: `file_runtime_attributes()` | §2.4 |
| `src/startd8/utils/manifest_registry.py` | New method: `module_all_for()` | §2.5 |
| `src/startd8/utils/manifest_registry.py` | New method: `module_version_for()` | §2.6 |
| `src/startd8/utils/manifest_registry.py` | Add `use_runtime_callable` kwarg to `dead_candidates()` | §2.7 |
| `src/startd8/utils/manifest_registry.py` | `ManifestDiff`: add `changed_resolved_signatures`, `mro_changes`, `module_all_diff` | §3.1–3.3 |
| `src/startd8/contractors/context_seed_handlers.py` | DS-1, DS-2, DS-3, DS-4 in `DesignPhaseHandler` | §4 |
| `src/startd8/contractors/context_seed_handlers.py` | IM-1, IM-2 in `ImplementPhaseHandler._tasks_to_chunks()` | §5 |
| `src/startd8/contractors/artisan_phases/development.py` | IM-2 rendering in `_build_manifest_context()` | §5.2 |
| `src/startd8/workflows/builtin/preflight_rules/call_graph_validator.py` | PF-1: `validate_module_all()` | §6.1 |
| `src/startd8/contractors/prompt_utils.py` | T1 `manifest_resolved_types`, T3 `public_api_surface` | §7 |

---

## 9. Verification Plan

1. **Unit: `file_resolved_type_summary()`** — File with elements having `inspect_info.resolved_signature`. Assert output contains resolved type strings, not forward-ref strings.
2. **Unit: `file_mro_summary()`** — Class with MRO `[Child, Parent, object]`. Assert output excludes `object`, includes `[Child → Parent]`.
3. **Unit: `file_runtime_attributes()`** — Dataclass element with `runtime_attributes=["id", "name"]`. Assert both names in output.
4. **Unit: `module_all_for()`** — File with `module_all=["foo", "bar"]`. Assert method returns `["foo", "bar"]`.
5. **Unit: `dead_candidates(use_runtime_callable=True)`** — Callable class (`is_callable=True`, `ElementKind.CLASS`, 0 callers). Assert in dead candidates.
6. **Unit: DS-1 DESIGN context** — `enable_introspect=True`, file with resolved types. Assert manifest context uses resolved types, not forward-ref strings.
7. **Unit: DS-2 DESIGN MRO** — Class element with `mro`. Assert `Class Hierarchy` subsection in design context.
8. **Unit: PF-1 `module_all` validation** — `module_all` containing a name with no matching element. Assert WARNING.
9. **Unit: `ManifestDiff.changed_resolved_signatures`** — Two manifests with matching AST but differing resolved signatures. Assert diff is non-empty.
10. **Regression: `enable_introspect=False`** — All consumers produce identical output to pre-change behavior.
