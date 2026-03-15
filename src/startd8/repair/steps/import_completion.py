"""Import completion repair step (REQ-RPL-102).

Two implementations behind one interface (per R3-S2):

- ``ManifestImportCompletion`` — uses ``element_context.imports``
  (micro-prime path)
- ``ErrorDrivenImportCompletion`` — parses ``ImportDiagnostic`` from
  ``RepairContext.diagnostics`` (contractor path). When
  ``RepairContext.manifest_registry`` is available (R3-S8), consults
  registry for correct import paths before falling back to stderr
  heuristic.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from ..models import (
    ElementContext,
    ImportDiagnostic,
    RepairContext,
    RepairStepResult,
)

# Well-known package import corrections.  LLM-generated skeletons often
# produce incorrect module paths (e.g. ``from humanmessage import HumanMessage``
# instead of ``from langchain_core.messages import HumanMessage``).  When the
# ManifestImportCompletion step encounters a ``from X import Y`` whose module
# matches a key here, it rewrites the module to the correct path.
#
# Format: {wrong_module: correct_module}
_KNOWN_IMPORT_CORRECTIONS: dict[str, str] = {
    # LangChain ecosystem
    "humanmessage": "langchain_core.messages",
    "aimessage": "langchain_core.messages",
    "systemmessage": "langchain_core.messages",
    "basemessage": "langchain_core.messages",
    "chatgooglegenerativeai": "langchain_google_genai",
    "langchain.chains": "langchain_google_genai",
    # Locust
    "fasthttpuser": "locust",
    "httpuser": "locust",
    "taskset": "locust",
    "between": "locust",
    # Faker
    "fake": "faker",
    # Flask
    "flask_app": "flask",
    # gRPC
    "grpc_health": "grpc_health.v1",
    "health_pb2": "grpc_health.v1.health_pb2",
    # Google Cloud
    "googleapicallerror": "google.api_core.exceptions",
    "templateerror": "jinja2",
}


def _find_import_insertion_line(lines: list[str]) -> int:
    """Find the line index where new imports should be inserted.

    Skips past:
    - Encoding declarations (``# -*- coding: ...``)
    - Hashbang lines (``#!/...``)
    - Module docstrings (triple-quoted)
    - Comments and blank lines at the top
    - ``from __future__ import ...`` statements

    Returns the 0-based line index where new imports should go.
    """
    i = 0
    n = len(lines)

    # Skip hashbang
    if i < n and lines[i].startswith("#!"):
        i += 1

    # Skip leading comments, blank lines, encoding declarations
    while i < n:
        stripped = lines[i].strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
        else:
            break

    # Skip module docstring (triple-quoted)
    if i < n:
        stripped = lines[i].strip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                if stripped.count(quote) >= 2 and stripped.endswith(quote) and len(stripped) > len(quote):
                    # Single-line docstring
                    i += 1
                else:
                    # Multi-line docstring — find closing quote
                    i += 1
                    while i < n and quote not in lines[i]:
                        i += 1
                    if i < n:
                        i += 1  # skip the closing line
                break

    # Skip blank lines after docstring
    while i < n and lines[i].strip() == "":
        i += 1

    # Skip from __future__ imports
    while i < n and lines[i].strip().startswith("from __future__"):
        i += 1

    return i


def _insert_imports(code: str, import_block: str) -> str:
    """Insert import statements at the correct position in the file."""
    lines = code.splitlines(keepends=True)
    insert_at = _find_import_insertion_line(
        [line.rstrip("\n\r") for line in lines],
    )

    before = "".join(lines[:insert_at])
    after = "".join(lines[insert_at:])

    # Ensure blank line separation
    if before and not before.endswith("\n\n"):
        if not before.endswith("\n"):
            before += "\n"
        before += "\n"

    if after and not after.startswith("\n"):
        import_block += "\n"

    return before + import_block + "\n" + after


def _collect_existing_imports(tree: ast.Module) -> set[str]:
    """Collect all imported names from an AST tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _collect_local_definitions(tree: ast.Module) -> set[str]:
    """Collect names defined at module level (functions, classes, assignments).

    Used to prevent the import_completion step from adding ``import foo``
    when ``foo`` is actually a function/class/variable defined in the same
    file — a common hallucination from LLM-generated code that the repair
    pipeline previously amplified (e.g. ``import setCurrency`` when
    ``setCurrency`` is a function in the same locustfile).
    """
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


class ManifestImportCompletion:
    """Add missing imports using manifest ForwardImportSpec list.

    Used by the micro-prime path where ``element_context.imports``
    provides the canonical import list from the forward manifest.
    """

    name: str = "import_completion"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if element_context is None or not element_context.imports:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        existing_imports = _collect_existing_imports(tree)
        local_defs = _collect_local_definitions(tree)

        # Collect all Name references in code
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

        # Find manifest imports that provide used names but are missing
        missing_imports: list[str] = []
        import_names: list[str] = []
        for imp in element_context.imports:
            if hasattr(imp, "kind") and imp.kind == "from":
                for name in imp.names:
                    if name in used_names and name not in existing_imports:
                        # Skip if the module path is actually a locally-defined
                        # name (e.g. ``import setCurrency`` where setCurrency is
                        # a function in this file).
                        if imp.module in local_defs:
                            continue
                        # Correct well-known wrong module paths from LLM skeletons
                        module = _KNOWN_IMPORT_CORRECTIONS.get(
                            imp.module.lower(), imp.module,
                        )
                        names_str = ", ".join(imp.names)
                        missing_imports.append(f"from {module} import {names_str}")
                        for imp_name in imp.names:
                            if imp_name not in import_names:
                                import_names.append(imp_name)
                        existing_imports.update(imp.names)
                        break
            elif hasattr(imp, "module"):
                mod_base = imp.module.split(".")[0]
                effective_name = getattr(imp, "alias", None) or mod_base
                if effective_name in used_names and effective_name not in existing_imports:
                    # Skip if the module name matches a local definition —
                    # prevents ``import foo`` when ``def foo():`` exists in
                    # the same file.
                    if imp.module in local_defs or mod_base in local_defs:
                        continue
                    # Correct well-known wrong module paths from LLM skeletons
                    module = _KNOWN_IMPORT_CORRECTIONS.get(
                        imp.module.lower(), imp.module,
                    )
                    alias_str = f" as {imp.alias}" if getattr(imp, "alias", None) else ""
                    missing_imports.append(f"import {module}{alias_str}")
                    if effective_name not in import_names:
                        import_names.append(effective_name)
                    existing_imports.add(effective_name)

        if not missing_imports:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        import_block = "\n".join(missing_imports)
        new_code = _insert_imports(code, import_block)

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=new_code,
            metrics={
                "imports_added": len(missing_imports),
                "import_names": import_names,
            },
        )


class ErrorDrivenImportCompletion:
    """Add missing imports by parsing ImportDiagnostic from checkpoint errors.

    Used by the contractor path where diagnostics come from subprocess
    stderr (import check failures).

    When ``RepairContext.manifest_registry`` is available (R3-S8),
    consults the registry for correct import paths before falling back
    to the stderr-based heuristic.
    """

    name: str = "import_completion"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        import_diagnostics = [
            d for d in context.diagnostics
            if isinstance(d, ImportDiagnostic)
            and (
                d.file == str(file_path)
                or d.file == file_path.name
                or Path(d.file).name == file_path.name
            )
        ]

        if not import_diagnostics:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Collect existing imports to avoid duplicates (R1-S3)
        existing: set[str] = set()
        local_defs: set[str] = set()
        if context.existing_imports and file_path in context.existing_imports:
            existing = context.existing_imports[file_path]
        else:
            try:
                tree = ast.parse(code)
                existing = _collect_existing_imports(tree)
                local_defs = _collect_local_definitions(tree)
            except SyntaxError:
                pass

        missing_imports: list[str] = []
        import_names: list[str] = []
        for diag in import_diagnostics:
            module = diag.module
            if not module or module in existing:
                continue
            # Skip if the "missing" module is a locally-defined name
            if module in local_defs or module.split(".")[0] in local_defs:
                continue

            # R3-S8: Consult ManifestRegistry for correct import path
            if context.manifest_registry is not None:
                try:
                    resolved = context.manifest_registry.resolve_fqn(module)
                    if resolved:
                        module = resolved[0] if isinstance(resolved, tuple) else module
                except Exception:
                    pass  # Fall back to heuristic

            # Correct well-known wrong module paths from LLM output
            module = _KNOWN_IMPORT_CORRECTIONS.get(module.lower(), module)

            if diag.name:
                missing_imports.append(f"from {module} import {diag.name}")
                if diag.name not in import_names:
                    import_names.append(diag.name)
                existing.add(diag.name)
            else:
                missing_imports.append(f"import {module}")
                mod_base = module.split(".")[0]
                if mod_base not in import_names:
                    import_names.append(mod_base)
                existing.add(mod_base)

        if not missing_imports:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        import_block = "\n".join(missing_imports)
        new_code = _insert_imports(code, import_block)

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=new_code,
            metrics={
                "imports_added": len(missing_imports),
                "import_names": import_names,
            },
        )
