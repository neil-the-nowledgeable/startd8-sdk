# Complete Phase 1+2 gaps in the Code Manifest generator

All work is in an existing implementation — no new files needed.

## Context

The code manifest generator (`src/startd8/utils/code_manifest.py`, `src/startd8/utils/manifest_cache.py`) is ~88% complete for Phase 1+2 (P0) of the requirements at `docs/design/CODE_MANIFEST_REQUIREMENTS.md`. Tests are at `tests/unit/test_code_manifest.py` (72 tests) and `tests/unit/test_manifest_cache.py` (21 tests). All 93 tests currently pass.

## Gaps to close (6 items, ordered by severity)

### 1. `@branch[N]` FQN disambiguation (Medium) — Section 4.1.1

When the same name is defined in multiple branches of a conditional (`if/else`), each definition must get a `@branch[N]` suffix on its FQN. Currently both get the same FQN, which violates uniqueness.

**Requirements spec (Section 4.1.1):**
```
module.impl@branch[0]  — definition in the if block
module.impl@branch[1]  — definition in the else block
```
If only one definition exists for a name, no `@branch` suffix is added.

**What exists:** `_ManifestVisitor._count_name()` method exists but is never called. The visitor's `visit_FunctionDef`, `visit_ClassDef`, and `_process_assignment` need to detect when a name appears multiple times at the same scope level within different conditional branches and apply `@branch[N]` suffixes.

**Implementation hint:** A two-pass approach: first pass counts name occurrences per scope (already partially scaffolded in `_name_counts`), second pass appends `@branch[N]` only when count > 1. The tricky part is that `ast.NodeVisitor.visit()` sees top-level body statements in order — you need to detect when two `FunctionDef` nodes with the same name exist in sibling `if/else` bodies.

**Tests to add:** Test with `if sys.platform == 'win32': def impl(): ... else: def impl(): ...` — verify two elements with FQNs `module.impl@branch[0]` and `module.impl@branch[1]`, each with appropriate `scope_guard`.

### 2. Nested functions inside function bodies (Medium) — Section 4.1.1

Functions defined inside other function bodies are not visited. The visitor's `visit_FunctionDef` returns early when `self._in_class` is False (it only skips class methods, which are handled by `visit_ClassDef`). But it never recurses into the function body to find inner functions.

**Requirements spec (Section 4.1.1):**
```
module.outer_function.inner_function
```

**What to change:** After creating the `Element` for a module-level or nested function, recurse into `node.body` to discover nested `FunctionDef`/`AsyncFunctionDef`/`ClassDef` nodes and add them as `children` of the outer function element. Mirror the pattern used in `visit_ClassDef` for child extraction.

**Tests to add:** Test with a function containing an inner helper function — verify the inner function appears in `children` with the correct FQN (`module.outer.inner`), span, and signature.

### 3. `is_reexport` heuristics (a) and (c) for `__init__.py` (Low) — Section 3.3

Currently only heuristic (b) is implemented (`__all__` membership). The spec defines two additional `__init__.py`-specific heuristics:

- **(a)**: Import appears in an `__init__.py` file and imports from a submodule of the same package.
- **(c)**: Import is a `from .submodule import Name` pattern in an `__init__.py` without aliasing.

**What to change:** In `visit_ImportFrom`, check if the file being analyzed is an `__init__.py` (check `self.file_module_path` or add a flag). If so, mark `from .submodule import X` as `is_reexport=True` when the import is relative and imports from a child of the current package.

**Tests to add:** Create an `__init__.py` source with `from .models import MyModel` and verify `is_reexport=True` even without `__all__`.

### 4. YAML output format (Low) — Section 5.2

The spec requires JSON, YAML, and Python dict output. JSON and dict work via Pydantic. YAML is missing.

**What to add:** Add a `to_yaml()` method on `FileManifest` (or a standalone function). Use `yaml.dump(self.model_dump(), default_flow_style=False)`. The CLI's `manifest show --format yaml` and `manifest generate --format yaml` should work. Check if `pyyaml` is already a dependency in `pyproject.toml` (it is — listed as `pyyaml` in dependencies).

**Tests to add:** Round-trip test: generate manifest → `to_yaml()` → `yaml.safe_load()` → validate fields match.

### 5. Explicit `mode` parameter (Low) — Section 5.3

The spec defines three generation modes: `static`, `introspect`, `full`. Only `static` is implemented (P0), but the API should accept a `mode` parameter that defaults to `"static"` and raises `NotImplementedError` for the others.

**What to change:** Add `mode: str = "static"` parameter to `generate_file_manifest()`. At the top of the function, validate: `if mode != "static": raise NotImplementedError(f"Mode '{mode}' requires Phase 3+ implementation")`.

**Tests to add:** Test that `mode="static"` works, `mode="introspect"` raises `NotImplementedError`.

### 6. Batch performance benchmark (Low) — Section 5.5

Run `generate_project_manifests()` on the actual `src/startd8/` tree and verify it completes in <10s. This is a validation, not a code change.

**What to do:** Add a test marked `@pytest.mark.slow` that calls `generate_project_manifests(project_root)` with the real project root and asserts duration < 10s. If the SDK `src/startd8/` tree is too large for a unit test fixture, use `time.perf_counter()` and skip in CI with `@pytest.mark.skipif`.

## Constraints

- **Do not modify** the existing Pydantic model field definitions — they match the spec. Only add methods or parameters.
- **Do not break** the 93 existing passing tests.
- **Use `get_logger(__name__)`** for any logging (not `logging.getLogger()`).
- **Use `python3`** for all commands (not `python`).
- **Run `pytest tests/unit/test_code_manifest.py tests/unit/test_manifest_cache.py -v`** after each change to confirm no regressions.
- Follow existing code style: type hints, frozen Pydantic models, `from __future__ import annotations`.

## Definition of done

All 6 gaps closed, all new tests pass, all existing 93 tests still pass.
