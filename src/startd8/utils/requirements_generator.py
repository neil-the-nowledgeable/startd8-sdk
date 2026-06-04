"""Deterministic requirements.in generator from Python source imports.

Scans generated Python files, extracts third-party imports, maps them
to PyPI package names via the bidirectional alias map, and produces a
requirements.in file. Zero LLM cost, zero hallucination risk.

Usage:
    from startd8.utils.requirements_generator import generate_requirements_in

    content = generate_requirements_in(
        python_files={"src/service/app.py": "import flask\\nfrom redis import Redis\\n"},
    )
    # Returns: "flask\\nredis\\n"
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import PurePosixPath
from typing import Iterable, Optional

from startd8.implementation_engine.package_aliases import import_to_pypi

# Use sys.stdlib_module_names (3.10+) with fallback for older versions.
_STDLIB_MODULES: frozenset[str] = (
    frozenset(sys.stdlib_module_names)
    if hasattr(sys, "stdlib_module_names")
    else frozenset({
        "abc", "asyncio", "collections", "concurrent", "contextlib",
        "copy", "csv", "dataclasses", "datetime", "enum", "functools",
        "hashlib", "html", "http", "importlib", "inspect", "io",
        "itertools", "json", "logging", "math", "multiprocessing", "os",
        "pathlib", "pickle", "pprint", "queue", "random", "re",
        "shutil", "signal", "socket", "sqlite3", "string", "struct",
        "subprocess", "sys", "tempfile", "textwrap", "threading",
        "time", "traceback", "typing", "unittest", "urllib", "uuid",
        "warnings", "xml", "zipfile",
    })
)

# Imports that are local to the project (not real packages).
# These patterns indicate relative or in-project imports.
_LOCAL_IMPORT_PATTERNS = frozenset({
    ".", "..",
})

# Regex for protobuf/gRPC generated stubs (e.g., demo_pb2, demo_pb2_grpc).
# These are generated at build time by grpc_tools.protoc and are never
# installable pip packages.
_PROTOBUF_STUB_RE = re.compile(r"^[a-zA-Z_]\w*_pb2(_grpc)?$")


def _build_local_module_names(python_files: dict[str, str]) -> frozenset[str]:
    """Derive local module names from the file paths in the project.

    A file ``emailservice/logger.py`` produces the local module name
    ``logger``.  A file ``src/emailservice/email_server.py`` produces
    ``email_server``, ``src``, and ``emailservice``.

    All intermediate directory names are included because they represent
    local Python packages that aren't pip-installable (e.g.,
    ``from emailservice.email_server_pb2_grpc import ...``).
    """
    local: set[str] = set()
    for file_path in python_files:
        if not file_path.endswith(".py"):
            continue
        p = PurePosixPath(file_path)
        # The stem of the .py file is a local module (e.g., logger.py → logger)
        local.add(p.stem)
        # All parent directories are local packages
        # (e.g., src/emailservice/server.py → src, emailservice)
        for part in p.parts[:-1]:  # exclude the filename itself
            local.add(part)
    return frozenset(local)


def _is_local_or_generated(
    module_name: str, local_modules: frozenset[str]
) -> bool:
    """Return True if *module_name* is a local/generated module, not a pip package.

    Catches:
    - Protobuf stubs (``*_pb2``, ``*_pb2_grpc``)
    - Sibling Python modules (files in the same service directory)
    """
    top_level = module_name.split(".")[0]

    # Protobuf / gRPC generated stubs
    if _PROTOBUF_STUB_RE.match(top_level):
        return True

    # Local project module (sibling .py file or subdirectory)
    if top_level in local_modules:
        return True

    return False


def generate_requirements_in(
    python_files: dict[str, str],
    extra_packages: Optional[list[str]] = None,
    exclude_packages: Optional[set[str]] = None,
) -> str:
    """Generate requirements.in content from Python source imports.

    Args:
        python_files: Map of file path → Python source code.
        extra_packages: Additional packages to include (e.g., from
            task metadata or manifest dependencies).
        exclude_packages: Packages to exclude from output.

    Returns:
        Contents for a requirements.in file (one package per line,
        sorted, no version pins).
    """
    local_modules = _build_local_module_names(python_files)
    all_imports = set()

    for file_path, source in python_files.items():
        if not file_path.endswith(".py"):
            continue
        imports = extract_third_party_imports(source)
        all_imports.update(imports)

    # Filter out local/generated modules before mapping to PyPI names
    all_imports = {
        imp for imp in all_imports
        if not _is_local_or_generated(imp, local_modules)
    }

    # Map import names to PyPI package names.
    # import_to_pypi handles alias lookup with prefix matching.
    # For unmapped deep imports (e.g., sqlalchemy.ext.asyncio), fall back
    # to the top-level module name which is usually the PyPI package name.
    alias_matched: set[str] = set()  # packages found via alias map
    fallback_packages: set[str] = set()  # top-level fallbacks
    for imp in all_imports:
        pypi_name = import_to_pypi(imp)
        if pypi_name != imp:
            # Alias map matched — this is a specific package
            alias_matched.add(pypi_name)
        elif "." in pypi_name:
            # No alias match for dotted import — fall back to top-level
            fallback_packages.add(imp.split(".")[0])
        else:
            # Simple name, no dots — use as-is (e.g., flask, locust)
            alias_matched.add(pypi_name)

    # Suppress generic top-level fallbacks when a specific alias-matched
    # package already covers that namespace (e.g., don't add "google" when
    # "google-cloud-secret-manager" is already present).
    pypi_packages = set(alias_matched)
    for fb in fallback_packages:
        # Only add if no alias-matched package starts with the same prefix
        if not any(p.startswith(fb) for p in alias_matched):
            pypi_packages.add(fb)

    # Add extras
    if extra_packages:
        pypi_packages.update(extra_packages)

    # Remove exclusions
    if exclude_packages:
        pypi_packages -= exclude_packages

    if not pypi_packages:
        return ""

    return "\n".join(sorted(pypi_packages)) + "\n"


def extract_third_party_imports(source: str) -> set[str]:
    """Extract third-party import module names from Python source.

    Returns top-level module names only (e.g., ``flask`` from
    ``from flask import Flask``). Excludes stdlib and relative imports.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Keep full dotted path for alias lookup (e.g., google.cloud)
                full = alias.name
                top_level = full.split(".")[0]
                if top_level not in _STDLIB_MODULES and top_level:
                    modules.add(full)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import
            if node.module:
                top_level = node.module.split(".")[0]
                if top_level not in _STDLIB_MODULES and top_level:
                    # For `from google.cloud import secretmanager`, build
                    # full paths: both "google.cloud" and "google.cloud.secretmanager"
                    # so alias lookup can match the most specific entry.
                    modules.add(node.module)
                    if node.names:
                        for alias in node.names:
                            modules.add(f"{node.module}.{alias.name}")

    return modules


def external_packages_from_imports(
    import_modules: Iterable[str],
    local_prefixes: Iterable[str] = (),
) -> set[str]:
    """Third-party PyPI package names from declared import module paths.

    Drops stdlib, relative (``.``-prefixed), and local-package imports (those whose
    top-level segment is in *local_prefixes*). Maps the rest to PyPI names via
    ``import_to_pypi``. **Ordering-independent**: it reads a SPEC's *declared* imports
    rather than generated files on disk, so a dependency is captured even when its
    importing file was generated *after* the requirements scan ran (RUN-036 fix).
    """
    local = set(local_prefixes)
    out: set[str] = set()
    for mod in import_modules:
        mod = (mod or "").strip()
        if not mod or mod.startswith("."):
            continue
        top = mod.split(".")[0]
        if not top or top in _STDLIB_MODULES or top in local:
            continue
        out.add(import_to_pypi(top))
    return out


def generate_requirements_in_from_manifest(
    manifest_imports: list[dict],
    manifest_dependencies: Optional[dict] = None,
) -> str:
    """Generate requirements.in from forward manifest import/dependency data.

    Alternative entry point when manifest data is available instead of
    raw source code.

    Args:
        manifest_imports: List of ForwardImportSpec-like dicts with
            ``module`` keys.
        manifest_dependencies: Optional ForwardDependencies-like dict
            with ``external`` list.

    Returns:
        Contents for a requirements.in file.
    """
    pypi_packages: set[str] = set()

    # From imports
    for imp in manifest_imports:
        module = imp.get("module", "")
        top_level = module.split(".")[0]
        if top_level and top_level not in _STDLIB_MODULES:
            pypi_name = import_to_pypi(top_level)
            pypi_packages.add(pypi_name)

    # From explicit dependencies
    if manifest_dependencies:
        for pkg in manifest_dependencies.get("external", []):
            pypi_packages.add(pkg)

    if not pypi_packages:
        return ""

    return "\n".join(sorted(pypi_packages)) + "\n"
