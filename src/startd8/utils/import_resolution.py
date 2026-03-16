"""Import resolution utilities for semantic validation.

Determines whether an import statement in generated code resolves to a
known source (stdlib, PyPI package, local sibling, protobuf stub, or
golden-seed import map).  Used by ``forward_manifest_validator.py`` to
populate ``semantic_issues`` for unresolvable imports (REQ-SV-201).

Reuses ``_STDLIB_MODULES`` and ``_PROTOBUF_STUB_RE`` from
``requirements_generator`` and ``import_to_pypi`` from
``package_aliases`` — no new data structures.
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
from startd8.implementation_engine.package_aliases import import_to_pypi, pypi_to_import


def extract_import_modules(tree: ast.AST) -> List[Dict[str, object]]:
    """Extract all imports from a parsed AST with metadata.

    Returns a list of dicts, each with:
        ``module``    – top-level module name (e.g. ``grpc``)
        ``full_path`` – full dotted import path (e.g. ``grpc.aio``)
        ``line``      – source line number
        ``kind``      – ``"import"`` or ``"from"``
    """
    results: List[Dict[str, object]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append({
                    "module": alias.name.split(".")[0],
                    "full_path": alias.name,
                    "line": node.lineno,
                    "kind": "import",
                })
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import — always local
            if node.module:
                results.append({
                    "module": node.module.split(".")[0],
                    "full_path": node.module,
                    "line": node.lineno,
                    "kind": "from",
                })
    return results


def discover_sibling_modules(
    file_path: str, project_root: str,
) -> Set[str]:
    """Discover ``.py`` file stems and directory-package names alongside *file_path*.

    Both the immediate parent directory's ``.py`` children and any
    sub-directory names (potential packages) are returned.
    """
    abs_path = Path(project_root) / file_path
    parent = abs_path.parent
    modules: Set[str] = set()
    if not parent.is_dir():
        return modules
    for child in parent.iterdir():
        if child.suffix == ".py" and child.name != abs_path.name:
            modules.add(child.stem)
        elif child.is_dir() and not child.name.startswith("."):
            modules.add(child.name)
    return modules


def resolve_import(
    module_name: str,
    *,
    sibling_modules: Set[str],
    requirements_packages: Set[str],
    import_map: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Classify *module_name* to its resolution source.

    Returns one of:
        ``"stdlib"``                     – standard library module
        ``"pip:<package>"``              – third-party PyPI package
        ``"proto"``                      – protobuf/gRPC generated stub
        ``"local:<module>"``             – sibling Python file or package
        ``"import_map:<classification>"``– matched by golden-seed import map
        ``None``                         – unresolvable (semantic error)

    When *import_map* is provided the function operates in **closed-world**
    mode: the import must appear in the map to be considered valid.
    """
    top_level = module_name.split(".")[0]

    # Golden-seed import map — authoritative closed-world check
    if import_map is not None:
        classification = import_map.get(module_name)
        if classification is None:
            classification = import_map.get(top_level)
        if classification is not None:
            return f"import_map:{classification}"
        # Closed-world: not in the map → unresolvable
        return None

    # Open-world resolution order: stdlib → proto → local → pip

    if top_level in _STDLIB_MODULES:
        return "stdlib"

    if _PROTOBUF_STUB_RE.match(top_level):
        return "proto"

    if top_level in sibling_modules:
        return f"local:{top_level}"

    # PyPI check: see if the import maps to a known package that is in
    # the task's requirements.  ``import_to_pypi`` returns the import name
    # unchanged when no mapping exists, so ``flask`` → ``flask``.
    pypi_name = import_to_pypi(module_name)
    if pypi_name != module_name:
        # Alias-mapped (e.g. grpc → grpcio) — always resolvable even
        # without a requirements.in (the mapping itself is evidence).
        return f"pip:{pypi_name}"

    # Simple top-level name matches itself as a PyPI package
    if top_level in requirements_packages:
        return f"pip:{top_level}"

    # Check if any requirements package maps to this import via alias
    for req_pkg in requirements_packages:
        expected_import = pypi_to_import(req_pkg)
        if top_level == expected_import or module_name.startswith(expected_import + "."):
            return f"pip:{req_pkg}"
        # Reverse prefix: import is a prefix of the expected import.
        # e.g. `from google.cloud import secretmanager` → full_path="google.cloud",
        # expected_import="google.cloud.secretmanager" (from google-cloud-secret-manager).
        # The import path is a parent namespace of the package's import path.
        if expected_import.startswith(module_name + "."):
            return f"pip:{req_pkg}"

    return None


def parse_requirements_packages(content: str) -> Set[str]:
    """Extract package names from requirements.in content.

    Strips version specifiers, comments, pip flags, and blank lines.
    Returns lowercase package names.
    """
    packages: Set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        # Strip inline comments then version specifiers
        spec = stripped.split("#")[0].strip()
        name = re.split(r"[~=!<>\[;]", spec)[0].strip().lower()
        if name:
            packages.add(name)
    return packages
