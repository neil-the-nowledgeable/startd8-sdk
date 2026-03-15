# Semantic Validation Implementation Plan

**Date:** 2026-03-15
**Status:** Ready for Development
**Requirements:** [SEMANTIC_VALIDATION_REQUIREMENTS.md](SEMANTIC_VALIDATION_REQUIREMENTS.md)
**Evidence:** [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md)

---

## 1. Implementation Overview

Four phases, each independently shippable. Each phase produces a commit with tests, updates the postmortem scoring, and is verifiable against run-049 (no false positives) and run-050 (catches known bugs).

```
Phase 1: Foundation + L1 Import Resolution       [P0, ~250 LOC + ~300 test LOC]
Phase 2: L2 Cross-Scope Duplicates + L3 Dockerfile Digest  [P1, ~80 LOC + ~150 test LOC]
Phase 3: L4 Factory Return + L5 Requirements Cross-Check   [P2, ~100 LOC + ~200 test LOC]
Phase 4: L6 Expression Lint + Observability       [P3, ~120 LOC + ~150 test LOC]
```

**Total estimated:** ~550 LOC implementation + ~800 LOC tests across 4 commits.

---

## 2. Phase 1: Foundation + L1 Import Resolution (P0)

### Goal
Catch the 4 highest-severity bugs from run-050: phantom imports, wrong module paths, repair-mangled imports. Establish the structured `semantic_issues` entry format used by all subsequent phases.

### Step 1.1: Extract Shared Import Infrastructure

**File:** `src/startd8/utils/import_resolution.py` (new)

The import resolution logic needed by L1 validation overlaps with `requirements_generator.py` but has a different purpose (validation vs. generation). Extract the shared primitives into a utility module rather than importing from the generator.

```python
"""Import resolution utilities for semantic validation.

Reuses _STDLIB_MODULES and _PROTOBUF_STUB_RE from requirements_generator.py
via re-export; adds validation-specific resolution logic.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

from startd8.utils.requirements_generator import (
    _STDLIB_MODULES,
    _PROTOBUF_STUB_RE,
)
from startd8.implementation_engine.package_aliases import import_to_pypi


def extract_import_modules(tree: ast.AST) -> List[dict]:
    """Extract all imports from an AST with line numbers.

    Returns list of dicts:
        {"module": "grpc", "full_path": "grpc", "line": 3, "kind": "import"}
        {"module": "demo_pb2", "full_path": "demo_pb2_grpc", "line": 5, "kind": "from"}
    """
    ...


def discover_sibling_modules(
    file_path: str, project_root: str
) -> Set[str]:
    """Discover .py file stems and directory package names in the same directory."""
    ...


def resolve_import(
    module_name: str,
    *,
    sibling_modules: Set[str],
    requirements_packages: Set[str],
    import_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Resolve an import to its source classification.

    Returns one of:
        "stdlib"
        "pip:<package>"
        "proto:<stub>"
        "local:<module>"
        "import_map:<classification>"   (when import_map provided)
        None                            (unresolvable — semantic error)
    """
    ...
```

**Why a new file instead of adding to `forward_manifest_validator.py`:** The validator is already 600 lines. Import resolution is a cohesive concern with its own test surface. Keeping it separate enables reuse by both the validator and future consumers (e.g., context resolution dependency injection).

**Dependencies:**
- `requirements_generator._STDLIB_MODULES` — re-import (already public via module scope)
- `requirements_generator._PROTOBUF_STUB_RE` — re-import
- `package_aliases.import_to_pypi` — existing function

### Step 1.2: Implement `_validate_import_resolution()`

**File:** `src/startd8/forward_manifest_validator.py`

Add after `_count_duplicate_definitions()` (after line 584):

```python
def _validate_import_resolution(
    tree: ast.AST,
    file_path: str,
    project_root: str,
    *,
    sibling_files: Optional[List[str]] = None,
    import_map: Optional[Dict[str, str]] = None,
) -> List[dict]:
    """Validate that all imports resolve to known sources (REQ-SV-201).

    Returns list of semantic issue dicts with category="import_resolution".
    """
    from startd8.utils.import_resolution import (
        extract_import_modules,
        discover_sibling_modules,
        resolve_import,
    )

    issues: List[dict] = []

    # Build sibling module set
    if sibling_files is not None:
        sibling_modules = {Path(f).stem for f in sibling_files}
        # Also add directory names as packages
        sibling_modules |= {
            Path(f).parent.name for f in sibling_files if Path(f).parent.name
        }
    else:
        sibling_modules = discover_sibling_modules(file_path, project_root)

    # Build requirements package set from sibling requirements.in
    requirements_packages = _discover_requirements_packages(
        file_path, project_root
    )

    # Extract and resolve each import
    for imp in extract_import_modules(tree):
        resolution = resolve_import(
            imp["module"],
            sibling_modules=sibling_modules,
            requirements_packages=requirements_packages,
            import_map=import_map,
        )
        if resolution is None:
            issues.append({
                "category": "import_resolution",
                "severity": "error",
                "message": (
                    f"Unresolvable import: '{imp['full_path']}' is not stdlib, "
                    f"not in requirements.in, not a local module, "
                    f"and not a protobuf stub"
                ),
                "line": imp["line"],
                "symbol": imp["full_path"],
            })

    return issues


def _discover_requirements_packages(
    file_path: str, project_root: str
) -> Set[str]:
    """Find requirements.in in the same service directory and extract package names."""
    ...
```

**Key behaviors:**
- When `import_map` is provided (golden seed mode), operates in closed-world: any import NOT in the map is an error
- When `import_map` is absent, operates in open-world: resolves against stdlib + PyPI + local + proto
- Repair-mangled import detection (REQ-SV-204): flag `from <service_name>.<internal_module> import ...` patterns as warnings

### Step 1.3: Wire into `validate_disk_compliance()`

**File:** `src/startd8/forward_manifest_validator.py`, line 320

Extend the function signature:

```python
def validate_disk_compliance(
    file_path: str,
    project_root: str,
    manifest: Optional[ForwardManifest] = None,
    *,
    sibling_files: Optional[List[str]] = None,
    sibling_imports: Optional[Dict[str, Set[str]]] = None,
    import_map: Optional[Dict[str, str]] = None,
    factory_patterns: Optional[List[str]] = None,
) -> DiskComplianceResult:
```

Add after the duplicate definitions check (after line 369):

```python
    # Semantic validation (only when AST is valid)
    if result.ast_valid and tree is not None:
        # L1: Import resolution (REQ-SV-201)
        import_issues = _validate_import_resolution(
            tree, file_path, project_root,
            sibling_files=sibling_files,
            import_map=import_map,
        )
        result.semantic_issues.extend(import_issues)
```

**Backward compatibility:** All new parameters are keyword-only with `None` defaults. Existing call sites pass positional args only → zero breakage.

### Step 1.4: Update Prime Postmortem Call Site

**File:** `src/startd8/contractors/prime_postmortem.py`, lines 866-868

The current call:
```python
compliance = validate_disk_compliance(
    effective_file, effective_root, forward_manifest,
)
```

Updated call:
```python
# Build sibling file list for import resolution
sibling_files_for_task = [
    f for f in all_generated_files
    if Path(f).parent == Path(effective_file).parent
]

# Get import_map from seed if available
import_map = _get_import_map_for_task(
    fpm.feature_id, seed_context
)

compliance = validate_disk_compliance(
    effective_file, effective_root, forward_manifest,
    sibling_files=sibling_files_for_task,
    import_map=import_map,
)
```

This requires threading `seed_context` into `_attach_disk_validation_metrics()`. The method already receives `features` and `project_root`; add `seed_context: Optional[dict] = None` parameter.

**Helper:**
```python
def _get_import_map_for_task(
    feature_id: str, seed_context: Optional[dict]
) -> Optional[Dict[str, str]]:
    """Extract import_map for a task from golden seed context."""
    if not seed_context:
        return None
    tasks = seed_context.get("tasks", {})
    task = tasks.get(feature_id, {})
    return task.get("import_map")
```

### Step 1.5: Tests

**File:** `tests/unit/test_semantic_validation_imports.py` (new)

| Test | What It Verifies | Expected |
|------|-----------------|----------|
| `test_stdlib_import_passes` | `import os, sys, json` | 0 issues |
| `test_pip_import_passes` | `import flask` with `flask` in requirements.in | 0 issues |
| `test_proto_import_passes` | `import demo_pb2` | 0 issues |
| `test_local_sibling_passes` | `import logger` with `logger.py` sibling | 0 issues |
| `test_phantom_import_flagged` | `from alloydbengine import AlloyDBEngine` | 1 error |
| `test_wrong_path_import_flagged` | `from emailservice.email_server import EmailServiceStub` | 1 error (or warning for repair-mangled) |
| `test_repair_mangled_import_flagged` | `from recommendationservice.recommendation_server import X` | 1 warning |
| `test_golden_seed_import_map_strict` | Import not in map | 1 error |
| `test_golden_seed_import_map_passes` | All imports in map | 0 issues |
| `test_no_sibling_files_degrades_gracefully` | No sibling_files param | Falls back to disk scan |
| `test_no_requirements_in_skips_pip_check` | No requirements.in sibling | Only checks stdlib/local/proto |
| `test_scoring_integration` | File with 4 phantom imports | `semantic_penalty` = max(0, 1.0 - 4 × 0.15) = 0.4 |
| `test_backward_compat_no_kwargs` | Call without new kwargs | Same behavior as before |

**File:** `tests/unit/test_import_resolution.py` (new)

Unit tests for `import_resolution.py` functions in isolation:
- `extract_import_modules()` with various import forms
- `discover_sibling_modules()` with filesystem fixtures
- `resolve_import()` with each resolution path (stdlib, pip, proto, local, import_map, None)

### Step 1.6: Validation Against Run Data

After implementation, verify:
- **Run-049** (14/16 byte-identical to reference): 0 false positive semantic issues on the 14 correct files
- **Run-050** bugs caught:
  - `from alloydbengine import AlloyDBEngine` → error (phantom import)
  - `from emailservice.email_server import EmailServiceStub` → error (wrong path)
  - `from recommendationservice.recommendation_server import ListRecommendationsRequest` → error (repair-mangled)
  - `from recommendationservice.recommendation_server import RecommendationServiceServicer` → error (repair-mangled)

**Expected score impact on run-050's `shoppingassistantservice.py`:** At least 2 phantom import errors → semantic_penalty drops from 1.0 to 0.7 → composite drops from ~1.0 to ~0.94. With additional issues from later phases, this file should drop below PASS threshold.

---

## 3. Phase 2: L2 Cross-Scope Duplicates + L3 Dockerfile Digest (P1)

### Goal
Catch the nested/module-level `talkToGemini` duplicate and truncated SHA256 digests. Both are low-effort, high-confidence checks.

### Step 2.1: Extend `_count_duplicate_definitions()` for Cross-Scope

**File:** `src/startd8/forward_manifest_validator.py`, lines 572-584

The current implementation only checks module-level children:
```python
for node in ast.iter_child_nodes(tree):  # Direct children only
```

Replace with a scope-aware walker:

```python
def _count_duplicate_definitions(tree: ast.AST) -> int:
    """Count duplicate function/class names at module level only."""
    # ... existing code unchanged — returns int for backward compat ...


def _detect_cross_scope_duplicates(tree: ast.AST) -> List[dict]:
    """Detect function/class names duplicated across scopes (REQ-SV-301).

    Returns semantic issue dicts for names appearing at both module level
    and inside a nested scope.
    """
    # Collect (name, scope_type, line, parent_name)
    module_names: Dict[str, int] = {}  # name → line
    nested_names: List[tuple] = []     # (name, line, parent_name)

    # Module-level definitions
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names[node.name] = node.lineno

    # Nested definitions (walk all children of module-level nodes)
    for top_node in ast.iter_child_nodes(tree):
        if isinstance(top_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for node in ast.walk(top_node):
                if node is top_node:
                    continue
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name in module_names:
                        nested_names.append(
                            (node.name, node.lineno, top_node.name)
                        )

    issues = []
    for name, nested_line, parent_name in nested_names:
        issues.append({
            "category": "cross_scope_duplicate",
            "severity": "warning",
            "message": (
                f"'{name}' defined at module level (line {module_names[name]}) "
                f"and inside '{parent_name}' (line {nested_line})"
            ),
            "line": nested_line,
            "symbol": name,
        })
    return issues
```

**Design decision:** Keep `_count_duplicate_definitions()` unchanged (returns int, used by `DiskComplianceResult.duplicate_definitions`). The new `_detect_cross_scope_duplicates()` returns semantic issue dicts that go into `semantic_issues`. This avoids changing the meaning of the existing `duplicate_definitions` field.

### Step 2.2: Wire Cross-Scope Check into `validate_disk_compliance()`

Add after the L1 import resolution block:

```python
        # L2: Cross-scope duplicates (REQ-SV-301)
        scope_dupe_issues = _detect_cross_scope_duplicates(tree)
        result.semantic_issues.extend(scope_dupe_issues)
```

### Step 2.3: Add SHA256 Digest Validation to `_validate_dockerfile()`

**File:** `src/startd8/forward_manifest_validator.py`, lines 480-508

Add after the existing FROM/CMD/ENTRYPOINT checks:

```python
    # SHA256 digest validation (REQ-SV-401)
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped.upper().startswith("FROM"):
            continue
        for match in re.findall(r"@sha256:([0-9a-fA-F]*)", stripped):
            if len(match) != 64:
                result.semantic_issues.append({
                    "category": "dockerfile_digest",
                    "severity": "error",
                    "message": (
                        f"Truncated SHA256 digest: {len(match)} chars "
                        f"(expected 64)"
                    ),
                    "line": lineno,
                    "symbol": f"sha256:{match[:16]}..." if match else "sha256:<empty>",
                })
```

**Note:** The existing `_validate_dockerfile()` iterates lines to find FROM/CMD. The digest check integrates into the same loop. The regex `[0-9a-fA-F]*` (star, not plus) also catches `@sha256:` with no hex chars at all.

### Step 2.4: Tests

**File:** `tests/unit/test_semantic_validation_scope_and_dockerfile.py` (new)

| Test | Input | Expected |
|------|-------|----------|
| `test_cross_scope_same_function_flagged` | `def foo():` at module + nested in `class Bar:` | 1 warning |
| `test_cross_scope_different_names_clean` | `def foo():` at module + `def bar():` nested | 0 issues |
| `test_class_init_not_flagged` | `__init__` at both scopes | 0 issues (common pattern, excluded) |
| `test_module_level_dupes_still_counted` | Two `def foo():` at module level | `duplicate_definitions=1` (existing behavior preserved) |
| `test_dockerfile_valid_digest_passes` | `FROM python:3.11@sha256:<64 hex chars>` | 0 issues |
| `test_dockerfile_truncated_digest_flagged` | `FROM python:3.11@sha256:abcd1234` (8 chars) | 1 error |
| `test_dockerfile_empty_digest_flagged` | `FROM python:3.11@sha256:` | 1 error |
| `test_dockerfile_no_digest_passes` | `FROM python:3.11-slim` | 0 issues |
| `test_dockerfile_multiple_from_lines` | 2 FROM with truncated digests | 2 errors |

---

## 4. Phase 3: L4 Factory Return + L5 Requirements Cross-Check (P2)

### Goal
Catch missing `return app` in factory functions and orphan dependencies in `requirements.in`.

### Step 3.1: Implement `_validate_factory_returns()`

**File:** `src/startd8/forward_manifest_validator.py`

```python
_DEFAULT_FACTORY_PATTERNS = [
    re.compile(r"^create_"),
    re.compile(r"^make_"),
    re.compile(r"^build_"),
    re.compile(r"_factory$"),
]


def _validate_factory_returns(
    tree: ast.AST,
    *,
    patterns: Optional[List[str]] = None,
) -> List[dict]:
    """Check that factory functions return a value (REQ-SV-501).

    Flags create_*, make_*, build_*, *_factory functions that have no
    `return <expr>` statement (only bare return or no return).
    """
    compiled = (
        [re.compile(p) for p in patterns]
        if patterns
        else _DEFAULT_FACTORY_PATTERNS
    )
    issues = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(p.search(node.name) for p in compiled):
            continue

        # Walk body for Return nodes with non-None value
        has_value_return = False
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and child.value is not None:
                has_value_return = True
                break

        if not has_value_return:
            issues.append({
                "category": "factory_return",
                "severity": "error",
                "message": (
                    f"Factory function '{node.name}' has no return statement "
                    f"with a value"
                ),
                "line": node.lineno,
                "symbol": node.name,
            })

    return issues
```

### Step 3.2: Implement `_validate_requirements_coverage()`

**File:** `src/startd8/forward_manifest_validator.py`

Add to the non-Python validation path. This runs when validating a `requirements.in` file and `sibling_imports` is provided.

```python
_KNOWN_NON_IMPORT_PACKAGES = frozenset({
    "setuptools", "wheel", "pip", "gunicorn", "uvicorn", "gevent",
    "pytest", "pytest-asyncio", "pytest-cov", "black", "ruff", "mypy",
})


def _validate_requirements_coverage(
    requirements_content: str,
    sibling_imports: Dict[str, Set[str]],
    result: DiskComplianceResult,
) -> None:
    """Check that every package in requirements.in is imported somewhere (REQ-SV-601)."""
    from startd8.implementation_engine.package_aliases import pypi_to_import

    all_imports: Set[str] = set()
    for imports in sibling_imports.values():
        all_imports |= imports

    for lineno, line in enumerate(requirements_content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue

        # Extract package name (before version specifier)
        package = re.split(r"[~=!<>\[;]", stripped)[0].strip().lower()
        if not package:
            continue
        if package in _KNOWN_NON_IMPORT_PACKAGES:
            continue

        # Map package to expected import name
        expected_import = pypi_to_import(package)

        # Check if any sibling imports this package
        found = any(
            imp == expected_import or imp.startswith(expected_import + ".")
            for imp in all_imports
        )
        if not found:
            result.semantic_issues.append({
                "category": "orphan_dependency",
                "severity": "warning",
                "message": (
                    f"Package '{package}' in requirements.in is not "
                    f"imported by any sibling Python file"
                ),
                "line": lineno,
                "symbol": package,
            })
```

### Step 3.3: Wire into `validate_disk_compliance()`

For Python files, add after L2:

```python
        # L4: Factory return check (REQ-SV-501)
        factory_issues = _validate_factory_returns(
            tree, patterns=factory_patterns
        )
        result.semantic_issues.extend(factory_issues)
```

For non-Python files (`_validate_requirements_file`), add requirements coverage check when `sibling_imports` is available. This requires threading `sibling_imports` through `_validate_non_python_file()` → `_validate_requirements_file()`.

### Step 3.4: Tests

**File:** `tests/unit/test_semantic_validation_factory_and_reqs.py` (new)

| Test | Input | Expected |
|------|-------|----------|
| `test_create_app_with_return_passes` | `def create_app(): ... return app` | 0 issues |
| `test_create_app_no_return_flagged` | `def create_app(): app = Flask(__name__)` | 1 error |
| `test_create_app_bare_return_flagged` | `def create_app(): ... return` | 1 error |
| `test_non_factory_no_return_ok` | `def process_data(): ...` | 0 issues |
| `test_custom_factory_pattern` | `patterns=["^new_"]`, `def new_widget(): ...` | 1 error |
| `test_orphan_dep_flagged` | `customjsonformatter` in reqs, no import | 1 warning |
| `test_used_dep_passes` | `flask` in reqs, `import flask` in sibling | 0 issues |
| `test_known_non_import_skipped` | `gunicorn` in reqs, no import | 0 issues |
| `test_no_sibling_imports_skips_check` | No sibling_imports param | Check skipped entirely |
| `test_alias_mapped_dep_passes` | `grpcio` in reqs, `import grpc` in sibling | 0 issues (via `pypi_to_import`) |

---

## 5. Phase 4: L6 Expression Lint + Observability (P3)

### Goal
Catch discarded return values from pure functions. Add OTel span attributes and Loki logging for all semantic checks.

### Step 4.1: Implement `_validate_discarded_returns()`

**File:** `src/startd8/forward_manifest_validator.py`

```python
_PURE_FUNCTIONS = frozenset({
    "os.getenv",
    "os.environ.get",
    "os.path.join",
    "os.path.exists",
    "dict.get",
    "str.format",
    "str.replace",
    "str.strip",
    "str.lower",
    "str.upper",
})


def _validate_discarded_returns(tree: ast.AST) -> List[dict]:
    """Flag expression statements that discard return values (REQ-SV-701).

    Only flags calls to functions in the _PURE_FUNCTIONS set.
    """
    issues = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Expr):
            continue
        if not isinstance(node.value, ast.Call):
            continue

        callee = _extract_callee_name(node.value)
        if callee and callee in _PURE_FUNCTIONS:
            issues.append({
                "category": "discarded_return",
                "severity": "warning",
                "message": f"Return value of '{callee}' is discarded",
                "line": node.lineno,
                "symbol": callee,
            })
    return issues


def _extract_callee_name(call_node: ast.Call) -> Optional[str]:
    """Extract dotted name from a Call node (e.g., 'os.getenv')."""
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = []
        node = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
    return None
```

### Step 4.2: Add OTel Span Attributes (REQ-SV-901)

**File:** `src/startd8/forward_manifest_validator.py`

At the end of `validate_disk_compliance()`, before returning `result`:

```python
    # OTel span attributes (REQ-SV-901)
    try:
        from opentelemetry import trace
        span = trace.get_current_span()
        if span.is_recording():
            error_count = sum(
                1 for i in result.semantic_issues
                if isinstance(i, dict) and i.get("severity") == "error"
            )
            warning_count = sum(
                1 for i in result.semantic_issues
                if isinstance(i, dict) and i.get("severity") == "warning"
            )
            categories = sorted({
                i["category"] for i in result.semantic_issues
                if isinstance(i, dict) and "category" in i
            })
            span.set_attribute("semantic_validation.issues_count", len(result.semantic_issues))
            span.set_attribute("semantic_validation.error_count", error_count)
            span.set_attribute("semantic_validation.warning_count", warning_count)
            span.set_attribute("semantic_validation.categories", categories)
            span.set_attribute("semantic_validation.import_map_mode", import_map is not None)
    except Exception:
        pass  # OTel is optional
```

### Step 4.3: Add Loki Logging (REQ-SV-902)

**File:** `src/startd8/forward_manifest_validator.py`

Replace `logger = logging.getLogger(__name__)` (line 13) with:

```python
from startd8.logging_config import get_logger
logger = get_logger(__name__)
```

Add after each semantic check block:

```python
    for issue in result.semantic_issues:
        if isinstance(issue, dict):
            logger.warning(
                "Semantic issue: %s",
                issue.get("message", str(issue)),
                extra={
                    "category": issue.get("category", "unknown"),
                    "severity": issue.get("severity", "unknown"),
                    "file_path": file_path,
                    "line": issue.get("line"),
                },
            )
```

### Step 4.4: Kaizen Export (REQ-SV-903)

**File:** `src/startd8/contractors/prime_postmortem.py`

In the Kaizen-exportable section of `FeaturePostMortem`, add computed properties:

```python
    @property
    def semantic_issue_summary(self) -> Dict[str, int]:
        """Category → count mapping for Kaizen trend analysis."""
        if not self.disk_compliance:
            return {}
        summary: Dict[str, int] = {}
        for issue in getattr(self.disk_compliance, "semantic_issues", []):
            if isinstance(issue, dict):
                cat = issue.get("category", "unknown")
                summary[cat] = summary.get(cat, 0) + 1
        return summary
```

Include in the Kaizen report output alongside existing fields.

### Step 4.5: Tests

| Test | Input | Expected |
|------|-------|----------|
| `test_discarded_getenv_flagged` | `os.getenv("FOO")` as expression statement | 1 warning |
| `test_assigned_getenv_passes` | `val = os.getenv("FOO")` | 0 issues |
| `test_print_not_flagged` | `print("hello")` as expression | 0 issues (not in pure set) |
| `test_list_append_not_flagged` | `my_list.append(x)` | 0 issues (side-effect call) |
| `test_otel_attributes_set` | Mock OTel span, run validation | Attributes set correctly |
| `test_logger_uses_get_logger` | Import check | Uses `get_logger`, not `logging.getLogger` |

---

## 6. File Change Summary

| File | Phase | Change Type | Lines Changed (est.) |
|------|-------|-------------|---------------------|
| `src/startd8/utils/import_resolution.py` | 1 | **New** | ~120 |
| `src/startd8/forward_manifest_validator.py` | 1-4 | Edit | ~250 (signature extension + 5 new functions) |
| `src/startd8/contractors/prime_postmortem.py` | 1, 4 | Edit | ~40 (threading sibling_files, import_map, Kaizen property) |
| `src/startd8/implementation_engine/package_aliases.py` | — | No change | 0 (reused as-is) |
| `src/startd8/utils/requirements_generator.py` | — | No change | 0 (reused via import) |
| `tests/unit/test_semantic_validation_imports.py` | 1 | **New** | ~200 |
| `tests/unit/test_import_resolution.py` | 1 | **New** | ~100 |
| `tests/unit/test_semantic_validation_scope_and_dockerfile.py` | 2 | **New** | ~150 |
| `tests/unit/test_semantic_validation_factory_and_reqs.py` | 3 | **New** | ~200 |
| `tests/unit/test_semantic_validation_lint_and_otel.py` | 4 | **New** | ~150 |

**Existing test files untouched:** `test_forward_manifest_validator_disk.py` and `test_forward_manifest_validator.py` continue to pass without modification (backward compat via keyword-only params).

---

## 7. Risk Mitigations

| Risk | Phase | Mitigation |
|------|-------|-----------|
| False positives from incomplete `import_to_pypi` map | 1 | Log unresolvable imports at DEBUG before flagging; run against run-049 first to calibrate |
| Breaking existing `validate_disk_compliance()` callers | 1 | All new params are keyword-only; add a backward-compat integration test that calls with positional args only |
| `_STDLIB_MODULES` incomplete on Python < 3.10 | 1 | Already handled by fallback frozenset in `requirements_generator.py` |
| Cross-scope duplicate false positives (common patterns like helper functions) | 2 | Start with `severity: "warning"` (not error); does not block PASS, only degrades score |
| Factory pattern too broad (catches non-factory `create_` functions) | 3 | Default patterns are conservative; configurable via `factory_patterns` param |
| OTel import failure in non-instrumented environments | 4 | Wrapped in try/except; OTel is always optional |
| Logger swap from `logging.getLogger` to `get_logger` | 4 | Must update `test_logger_acquisition_policy.py` allowlist (Leg 9 #33) |

---

## 8. Verification Plan

### Per-Phase Verification

Each phase runs these checks before merge:

1. **Existing tests pass:** `pytest tests/unit/test_forward_manifest_validator*.py -v`
2. **New tests pass:** `pytest tests/unit/test_semantic_validation_*.py -v`
3. **No false positives on run-049:** Apply validator to 14 byte-identical files → 0 semantic errors
4. **Known bugs caught on run-050:** Apply validator to 5 buggy files → expected issues flagged

### End-to-End Verification (After Phase 2)

Run Prime Contractor against golden seed (when available), compare:

| Metric | Before | After |
|--------|--------|-------|
| Run-050 `shoppingassistantservice.py` score | 1.0 | < 0.80 (FAIL) |
| Run-050 `email_client.py` score | 1.0 | < 0.90 (degraded) |
| Run-050 Dockerfiles (3) score | 1.0 | < 0.90 (degraded) |
| Run-049 14 correct files score | 1.0 | 1.0 (no regression) |
| Total bugs caught (of 11) | 0 | >= 8 |

---

## 9. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_REQUIREMENTS.md](SEMANTIC_VALIDATION_REQUIREMENTS.md) | Requirements this plan implements (REQ-SV-101 through REQ-SV-903) |
| [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](SEMANTIC_VALIDATION_GAP_ANALYSIS.md) | Evidence base — 11 bugs across runs 049/050 |
| [GOLDEN_SEED_REQUIREMENTS.md](../plan-ingestion/GOLDEN_SEED_REQUIREMENTS.md) | REQ-GS-302 `import_map` enables L1 closed-world mode |
| `forward_manifest_validator.py` | Primary implementation target |
| `prime_postmortem.py` | Scoring integration target |
| `requirements_generator.py` | Reusable `_STDLIB_MODULES`, `_PROTOBUF_STUB_RE` |
| `package_aliases.py` | Reusable `import_to_pypi()` |
