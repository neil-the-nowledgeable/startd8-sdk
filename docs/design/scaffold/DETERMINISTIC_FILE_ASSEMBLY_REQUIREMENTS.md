# Deterministic File Assembly — Requirements

**Phase:** Post-FLCM, Pre-IMPLEMENT scaffold enhancement
**Status:** DRAFT — awaiting review
**Date:** 2026-02-27

---

## 1. Goal

Extend the existing SCAFFOLD phase to deterministically generate skeleton Python `.py` files from structured data already available after plan ingestion and FLCM extraction — **without any LLM calls**. This converts the IMPLEMENT phase from "generate entire files" to "fill in function bodies in existing stubs," reducing LLM cost and improving generation reliability.

## 2. Problem Statement

Today's pipeline:

```
Plan Ingestion → FLCM Extraction → SCAFFOLD → DESIGN → IMPLEMENT → ...
                                      ↑                    ↑
                                creates dirs only     generates entire files from scratch
```

The SCAFFOLD phase (`ScaffoldPhaseHandler`) currently:

- Creates missing directories
- Validates target paths
- Discovers importable modules (`module_inventory`)
- **Does NOT create any `.py` file stubs**

Meanwhile, by the time SCAFFOLD runs, the pipeline already has rich structural data:

| Data Source | Available Fields |
|---|---|
| `ParsedFeature` (plan ingestion) | `target_files`, `api_signatures`, `runtime_dependencies`, `protocol` |
| `ForwardManifest` (FLCM extractor) | `ForwardFileSpec` per file: elements (name, kind, signature, bases, decorators, visibility), imports, dependencies |
| `InterfaceContract` (FLCM) | Function names, class names, base classes, import paths, config keys |
| Handoff (DESIGN phase) | `design_structural_delta` (add/modify/preserve per file), `design_mode_evidence` (create vs edit) |

This structural data is sufficient to create syntactically valid Python skeleton files deterministically.

## 3. Scope

### 3.1 In Scope

- A `DeterministicFileAssembler` class that renders `ForwardFileSpec` → `.py` source text
- Integration hook in SCAFFOLD phase (after directory creation, before DESIGN)
- `__init__.py` chain generation for new packages
- Import block rendering (stdlib / third-party / local ordering)
- Class definitions with bases, decorators, and `pass` or `__init__` stubs
- Function/method stubs with full type-hinted signatures and `raise NotImplementedError` bodies
- Constant placeholders from `FORMULA`/`CONFIG_KEY` contracts
- Module-level docstrings from contract descriptions
- `__all__` export lists from public-visibility elements
- Validation that rendered output is syntactically valid via `ast.parse()`
- Compatibility with `--stop-after scaffold` (existing CLI arg)
- Compatibility with `--dry-run` (no file writes)

### 3.2 Out of Scope

- Function body logic (remains LLM work in IMPLEMENT)
- Test file generation (remains in TEST phase)
- Non-Python file types (HTML, YAML, Dockerfile, etc.)
- Design document generation (remains in DESIGN phase)
- Modifications to plan ingestion prompts (separate follow-up; see §8)

## 4. Data Flow

```
Plan Ingestion
  └→ ParsedFeature[] with target_files, api_signatures, runtime_dependencies

FLCM Extractor (Phase 3, already runs, zero LLM cost)
  └→ ForwardManifest
       ├── contracts: InterfaceContract[]
       └── file_specs: {filepath → ForwardFileSpec}
                              ├── elements: ForwardElementSpec[]
                              │     ├── kind (CLASS, FUNCTION, METHOD, ...)
                              │     ├── name
                              │     ├── signature (Param[], return_annotation)
                              │     ├── bases[]
                              │     ├── decorators[]
                              │     └── visibility
                              ├── imports: ForwardImportSpec[]
                              └── dependencies: ForwardDependencies

SCAFFOLD Phase (enhanced)
  ├── Directory creation          [existing]
  ├── Module inventory            [existing]
  ├── DeterministicFileAssembler  [NEW]
  │     └→ skeleton .py files on disk
  └── ScaffoldPhaseOutput         [extended with file_stubs_created]

DESIGN Phase
  └→ (reads existing stubs, produces design docs)

IMPLEMENT Phase
  └→ (fills in function bodies in existing stubs — NOT generating from scratch)
```

## 5. Functional Requirements

### FR-001: ForwardFileSpec → Python Source Rendering

The `DeterministicFileAssembler` SHALL accept a `ForwardFileSpec` and produce syntactically valid Python source text containing:

1. A `from __future__ import annotations` line (convention match: `forward_manifest.py`, `code_manifest.py`)
2. A module docstring derived from contract descriptions or file path
3. Import blocks ordered: stdlib → third-party → local (isort-compatible)
4. Class definitions with bases, decorators, and placeholder bodies
5. Function/method definitions with full signatures and stub bodies
6. Module-level constants from `FORMULA`/`CONFIG_KEY` contracts

### FR-002: Signature Fidelity

All `ForwardElementSpec` signatures SHALL be rendered with:

- Parameter names and type annotations (from `Param.annotation`)
- Default values (from `Param.default`)
- Parameter kinds: positional-only (`/`), keyword-only (`*`), `*args`, `**kwargs`
- Return type annotations (from `Signature.return_annotation`)

The `Signature` model (from `code_manifest.py`) already provides all these fields. The assembler SHALL use them without loss.

### FR-003: Import Ordering

Import blocks SHALL follow isort-compatible ordering:

```python
# 1. __future__
from __future__ import annotations

# 2. stdlib
import os
from pathlib import Path

# 3. third-party
from pydantic import BaseModel

# 4. local / internal
from startd8.models import BridgeError
```

Classification sources:

- **stdlib**: `ForwardDependencies.stdlib` + Python `sys.stdlib_module_names` (3.10+) or hardcoded fallback
- **third-party**: `ForwardDependencies.external`
- **local**: all other `ForwardImportSpec` entries; cross-referenced against `module_inventory` from SCAFFOLD

### FR-004: Class Hierarchy

For `ForwardElementSpec` with `kind=CLASS`:

- Render `class Name(Base1, Base2):` using `bases` list
- If `bases` is empty, render `class Name:` (no explicit `object`)
- Render decorators above class definition (from `decorators` list)
- Nest methods (kind=METHOD, ASYNC_METHOD) inside the class body
- If no methods, render `pass` as body

### FR-005: Stub Bodies

| Element Kind | Stub Body |
|---|---|
| `FUNCTION`, `ASYNC_FUNCTION` | `raise NotImplementedError` |
| `METHOD`, `ASYNC_METHOD` | `raise NotImplementedError` |
| `PROPERTY` | `raise NotImplementedError` |
| `CLASS` (no methods) | `pass` |
| `CONSTANT` | `{name}: {type} = ...  # TODO` or literal from `constant_value` |

### FR-006: `__init__.py` Chain

When a `ForwardFileSpec.file` path implies a new package (e.g., `src/hybrid_scaffold/mapper/models.py`), the assembler SHALL create `__init__.py` files for each new intermediate directory if they don't already exist. Generated `__init__.py` files SHALL be empty (zero bytes) unless contracts specify re-exports.

### FR-007: `__all__` Generation

If a file contains 2+ public-visibility elements, the assembler SHALL generate an `__all__` list at module level containing all `ForwardElementSpec` entries with `visibility=PUBLIC`.

### FR-008: Syntax Validation

Every rendered file SHALL be validated via `ast.parse(source)` before being written to disk. If `ast.parse` raises `SyntaxError`, the assembler SHALL:

1. Log the error with file path and source excerpt
2. Skip writing that file
3. Record the failure in the output (see FR-010)

### FR-009: Existing File Safety

The assembler SHALL NOT overwrite files that already exist on disk. For files that exist:

- If `design_mode_evidence` classifies the file as `create` mode → skip (file already created by prior run)
- If classified as `edit` mode → skip (assembler only creates new files)
- Log a warning for each skipped file

This aligns with the Mottainai principle: don't destroy existing work.

### FR-010: Output Schema Extension

`ScaffoldPhaseOutput` SHALL be extended with:

```python
@dataclass
class FileStubResult:
    file_path: str
    elements_count: int       # Number of elements rendered
    imports_count: int        # Number of import statements
    status: str               # "created" | "skipped_exists" | "syntax_error"
    error: Optional[str]      # SyntaxError message if applicable

# In ScaffoldPhaseOutput:
file_stubs_created: list[FileStubResult]
file_stubs_skipped: int
file_stubs_failed: int
```

### FR-011: Dry-Run Compatibility

When `dry_run=True`, the assembler SHALL:

- Perform all rendering and syntax validation
- NOT write any files to disk
- Return the full `FileStubResult` list (so the user can inspect what would be created)

### FR-012: `--stop-after scaffold` Compatibility

The feature SHALL work correctly with the existing `--stop-after scaffold` CLI argument. When the pipeline stops after SCAFFOLD, the generated skeleton files SHALL be on disk and inspectable.

### FR-013: Async Method Rendering

`ASYNC_FUNCTION` and `ASYNC_METHOD` element kinds SHALL be rendered with the `async def` prefix.

### FR-014: Decorator Rendering

Decorators from `ForwardElementSpec.decorators` SHALL be rendered as `@decorator_name` lines above the element definition. Decorators with arguments (containing `(`) SHALL be rendered verbatim.

### FR-015: Docstring Hints

When `ForwardElementSpec.docstring_hint` is non-None, the assembler SHALL render it as a triple-quoted docstring immediately after the `def` or `class` line.

## 6. Non-Functional Requirements

### NFR-001: Zero LLM Cost

The assembler SHALL make **zero** LLM API calls. All rendering is deterministic string manipulation.

### NFR-002: Performance

Assembly of 50 files (typical large plan) SHALL complete in < 2 seconds. This is pure CPU/IO work.

### NFR-003: No New Dependencies

The assembler SHALL use only stdlib (`ast`, `pathlib`, `textwrap`, `sys`) and existing SDK imports. No Jinja2 required — the rendering is simpler than template-based generation.

### NFR-004: Idempotency

Running SCAFFOLD twice with the same `ForwardManifest` SHALL produce identical results: existing files are skipped (FR-009), new files are created only if missing.

## 7. Files Created / Modified

| File | Action | Purpose |
|---|---|---|
| `src/startd8/contractors/file_assembler.py` | **CREATE** | `DeterministicFileAssembler` class |
| `src/startd8/contractors/context_seed_handlers.py` | MODIFY | Hook assembler into `ScaffoldPhaseHandler.execute()` |
| `src/startd8/contractors/context_schema.py` | MODIFY | Add `FileStubResult`, extend `ScaffoldPhaseOutput` |
| `tests/unit/contractors/test_file_assembler.py` | **CREATE** | Unit tests (~40 tests) |

## 8. Future Enhancement: Plan Ingestion Prompt Enrichment

The current `api_signatures` field in `ParsedFeature` is inconsistently populated. A follow-up enhancement to plan ingestion prompts would improve assembler coverage:

| Current State | Enhancement |
|---|---|
| `api_signatures` sometimes empty | Require at least class-level signatures for every task |
| No class definition syntax | Support `"class ContextBridge(object)"` in `api_signatures` |
| Only package-level `runtime_dependencies` | Add `import_requirements` field: `"from pathlib import Path"` |
| No method-to-class association | Encourage dotted signatures: `"def ContextBridge.build_context(self) -> dict"` |

These are prompt-level changes to plan ingestion, not code changes. They would increase the number of `ForwardElementSpec` entries the FLCM extractor produces, which directly increases how much the assembler can scaffold.

**Note:** This enhancement is intentionally deferred. The assembler should first prove value with currently-available data, then prompts can be tuned to feed it richer input.

## 9. Integration with Existing Pipeline Infrastructure

### 9.1 FLCM Forward Manifest

The assembler consumes `ForwardManifest.file_specs` directly. The `ForwardFileSpec` model already has exactly the right shape:

- `file: str` — target file path
- `elements: list[ForwardElementSpec]` — classes, functions, methods
- `imports: list[ForwardImportSpec]` — import statements
- `dependencies: ForwardDependencies` — package classification

### 9.2 Code Manifest Models

The assembler reuses `ElementKind`, `Signature`, `Param`, `ParamKind`, `Visibility` from `utils/code_manifest.py`. No new type models needed.

### 9.3 Handoff

The assembler reads `design_mode_evidence` from handoff (when available) to distinguish create-mode vs edit-mode files. If handoff is not yet available (assembler runs before DESIGN), all files in `ForwardManifest.file_specs` are treated as create-mode.

### 9.4 Checkpoint

Generated stubs are not checkpointed separately — they're ordinary files on disk. The existing per-phase checkpoint tracks SCAFFOLD completion, which implicitly covers stub creation.

### 9.5 Contract Validation

`gate_contracts.py` defines SCAFFOLD exit requirements. The `file_stubs_created` output should be included in the exit validation to confirm stubs were generated for all `ForwardFileSpec` entries (minus skipped/failed).

## 10. Test Strategy

### 10.1 Unit Tests (~40 tests in 6 groups)

| Group | Count | Coverage |
|---|---|---|
| Import rendering | 6 | stdlib/3p/local ordering, `from` vs `import`, aliases, `__future__` |
| Class rendering | 8 | bases, decorators, nested methods, empty class, `__all__` |
| Function rendering | 8 | sync/async, params (all kinds), defaults, return annotations |
| Constant rendering | 4 | typed placeholders, literal values from contracts |
| Full file rendering | 8 | multi-element files, syntax validation, round-trip `ast.parse()` |
| Safety | 6 | existing file skip, dry-run, `__init__.py` chain, syntax error handling |

### 10.2 Verification Criteria

1. Every rendered file passes `ast.parse()` (syntax valid)
2. Round-trip: `ForwardFileSpec` → render → `ast.parse()` → extract element names → match original spec
3. Existing files are never overwritten
4. Dry-run produces results but no files on disk
5. `--stop-after scaffold` leaves stubs on disk

## 11. Example: End-to-End Rendering

Given this `ForwardFileSpec` (produced by FLCM extractor from plan ingestion):

```python
ForwardFileSpec(
    file="src/hybrid_scaffold/context_bridge.py",
    elements=[
        ForwardElementSpec(
            kind=ElementKind.CLASS, name="ContextBridge",
            bases=[], visibility=Visibility.PUBLIC,
            docstring_hint="Bridge between Eagle and ContextCore extractors.",
        ),
        ForwardElementSpec(
            kind=ElementKind.METHOD, name="build_context",
            signature=Signature(
                params=[
                    Param(name="self", kind=ParamKind.POSITIONAL),
                ],
                return_annotation="dict[str, Any]",
            ),
            visibility=Visibility.PUBLIC,
            docstring_hint="Orchestrate extraction and return merged context.",
        ),
        ForwardElementSpec(
            kind=ElementKind.METHOD, name="_transform_eagle",
            signature=Signature(
                params=[
                    Param(name="self", kind=ParamKind.POSITIONAL),
                    Param(name="metadata", annotation="ProjectMetadata",
                          kind=ParamKind.POSITIONAL),
                ],
                return_annotation="dict",
            ),
            visibility=Visibility.PROTECTED,
        ),
    ],
    imports=[
        ForwardImportSpec(kind="from", module="__future__", names=["annotations"]),
        ForwardImportSpec(kind="from", module="pathlib", names=["Path"]),
        ForwardImportSpec(kind="from", module="typing", names=["Any"]),
    ],
    dependencies=ForwardDependencies(stdlib=["pathlib", "typing"]),
)
```

The assembler produces:

```python
"""Context bridge module."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ContextBridge:
    """Bridge between Eagle and ContextCore extractors."""

    def build_context(self) -> dict[str, Any]:
        """Orchestrate extraction and return merged context."""
        raise NotImplementedError

    def _transform_eagle(self, metadata: ProjectMetadata) -> dict:
        raise NotImplementedError


__all__ = ["ContextBridge"]
```

This file is syntactically valid, import-ordered, and ready for the LLM to fill in method bodies during IMPLEMENT.

## 12. Open Questions

1. **Nesting heuristic**: How should the assembler determine which `METHOD`-kind elements belong inside which `CLASS`? Options:
   - (a) Name prefix convention: `ContextBridge.build_context` → method of `ContextBridge`
   - (b) Ordering convention: methods listed after a class in `elements[]` belong to it until the next class
   - (c) Explicit `parent_class` field on `ForwardElementSpec` (requires schema addition)

2. **Dataclass / Pydantic model rendering**: Should the assembler detect `@dataclass` or `BaseModel` in bases/decorators and render fields instead of methods?

3. **Type import inference**: When a signature references a type like `ProjectMetadata`, should the assembler attempt to infer its import path from `module_inventory`?

## 13. Review Feedback (2026-02-27)

### Summary

The draft is strong and implementation-oriented, but a few requirements are currently ambiguous or internally inconsistent. Tightening these points will improve determinism, reduce rework, and make test expectations clearer.

### Suggested Improvements

1. **Resolve method-to-class ownership before implementation (blocking ambiguity).**  
   FR-004 requires nested method rendering, but §12 still leaves the ownership heuristic open. Choose one canonical rule now (preferably explicit schema, e.g., `parent_class`) and make it normative in FR-004.

2. **Clarify exact header ordering for module docstring vs `__future__` import.**  
   FR-001 and FR-003 imply fixed ordering, while the example places module docstring before `from __future__ import annotations`. Explicitly specify the intended final order (recommended: module docstring first, then `__future__`, then other imports) to avoid conflicting implementations.

3. **Define `__all__` scope as top-level exports only.**  
   FR-007 says “public-visibility elements,” which can be read as including methods/properties. Constrain to top-level public symbols (classes, functions, constants) and exclude class members.

4. **Make file ordering deterministic across runs and platforms.**  
   Add a requirement to sort file paths and rendered elements by a defined key before output generation. This avoids nondeterministic ordering from dict iteration and improves reproducibility in tests/checkpoints.

5. **Specify behavior for unresolved/unknown type references.**  
   Signatures may include annotations not present in imports (e.g., `ProjectMetadata`). Define whether assembler should: (a) leave as-is, (b) quote unresolved types, or (c) fail with `syntax_error`-style result. This is needed for predictable syntax outcomes.

6. **Harden import classification fallback rules.**  
   FR-003 references multiple sources (`dependencies`, stdlib table, module inventory) but does not define precedence on conflicts. Add deterministic precedence (e.g., explicit dependency buckets > stdlib detection > local fallback).

7. **Extend FR-010 status enum for dry-run observability.**  
   Consider adding `would_create` and `would_skip_exists` statuses in dry-run mode instead of overloading `created/skipped_exists`. This improves CLI/report clarity and avoids confusing post-run analytics.

8. **Add explicit policy for partially generated package chains in dry-run.**  
   FR-006 + FR-011 leaves uncertainty about whether `__init__.py` chain actions are reported in dry-run. Add requirement that chain creation is included in `FileStubResult` (or dedicated counters) even when no writes occur.

9. **Define duplicate symbol handling.**  
   If two `ForwardElementSpec` entries resolve to same top-level symbol, define behavior (fail fast, de-duplicate with warning, or keep first/last). This prevents silent invalid modules and inconsistent test expectations.

## 14. Additional Feedback and Review (AI Assistant)

### Review of Existing Suggestions (Section 13)

I strongly agree with the suggestions provided in Section 13. Here is my breakdown of those suggestions:

1. **Agree**: Relying on parsing order or prefix heuristics for method-to-class ownership (Section 12, Q1) is fragile. Explicitly adding a `parent` or `parent_class` field to `ForwardElementSpec` is the most robust and deterministic approach.
2. **Agree**: The inconsistency between FR-001/FR-003 and the example needs resolution. The convention should strictly be: Module docstring -> `from __future__ import annotations` -> Standard imports.
3. **Agree**: `__all__` must be restricted to top-level module elements. Exporting class methods directly at the module level in `__all__` is invalid Python.
4. **Agree**: Deterministic file ordering is critical for reproducibility, especially when testing. Sorting `ForwardFileSpec` by file path and formatting imports deterministically ensures the same output on any platform.
5. **Agree**: For unresolved type references, the assembler should safely output them as-is. Thanks to `from __future__ import annotations`, undefined types won't crash the AST parser, allowing the IMPLEMENT phase to fix missing imports if needed.
6. **Agree**: Explicit precedence for imports (e.g., explicit deps > stdlib > module inventory) prevents `isort` flakiness and import block mangling.
7. **Agree**: Adding `would_create` and `would_skip_exists` avoids confusion in dry-run mode and keeps analytics accurate.
8. **Agree**: Package chain creation observability is important for dry-run correctness; `__init__.py` generations should be tracked.
9. **Agree**: Duplicate symbols should result in a fast failure or an explicit deduplication warning.

### Additional Suggestions for Improvement

1. **Import Aliases**: `ForwardImportSpec` should explicitly detail how aliases are handled. The test plan (Section 10.1) mentions aliases, but the functional requirement (FR-003) does not specify how to render statements like `from module import original as alias`.
2. **Indentation for Docstrings**: FR-015 (Docstring Hints) should precisely specify that docstrings must be properly indented to match the body of the class or function they belong to. Improper indentation here will surface as an `IndentationError` during the `ast.parse` step.
3. **Dataclass/Pydantic Fields vs Methods**: Regarding Section 12 Q2, it is safer for a "deterministic" assembler to leave field logic to the IMPLEMENT phase by default. If we wish to support them, we should introduce an explicit `ElementKind.FIELD` in the schema rather than trying to implicitly introspect decorators or base classes.
