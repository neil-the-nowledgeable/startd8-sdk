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

        # Collect all Name references in code
        used_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

        # Find manifest imports that provide used names but are missing
        missing_imports: list[str] = []
        for imp in element_context.imports:
            if hasattr(imp, "kind") and imp.kind == "from":
                for name in imp.names:
                    if name in used_names and name not in existing_imports:
                        names_str = ", ".join(imp.names)
                        missing_imports.append(f"from {imp.module} import {names_str}")
                        existing_imports.update(imp.names)
                        break
            elif hasattr(imp, "module"):
                mod_base = imp.module.split(".")[0]
                effective_name = getattr(imp, "alias", None) or mod_base
                if effective_name in used_names and effective_name not in existing_imports:
                    alias_str = f" as {imp.alias}" if getattr(imp, "alias", None) else ""
                    missing_imports.append(f"import {imp.module}{alias_str}")
                    existing_imports.add(effective_name)

        if not missing_imports:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        import_block = "\n".join(missing_imports)
        new_code = import_block + "\n\n" + code

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=new_code,
            metrics={"imports_added": len(missing_imports)},
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
            and (d.file == str(file_path) or d.file == file_path.name)
        ]

        if not import_diagnostics:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Collect existing imports to avoid duplicates (R1-S3)
        existing: set[str] = set()
        if context.existing_imports and file_path in context.existing_imports:
            existing = context.existing_imports[file_path]
        else:
            try:
                existing = _collect_existing_imports(ast.parse(code))
            except SyntaxError:
                pass

        missing_imports: list[str] = []
        for diag in import_diagnostics:
            module = diag.module
            if not module or module in existing:
                continue

            # R3-S8: Consult ManifestRegistry for correct import path
            if context.manifest_registry is not None:
                try:
                    resolved = context.manifest_registry.resolve_fqn(module)
                    if resolved:
                        module = resolved[0] if isinstance(resolved, tuple) else module
                except Exception:
                    pass  # Fall back to heuristic

            if diag.name:
                missing_imports.append(f"from {module} import {diag.name}")
                existing.add(diag.name)
            else:
                missing_imports.append(f"import {module}")
                existing.add(module.split(".")[0])

        if not missing_imports:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        import_block = "\n".join(missing_imports)
        new_code = import_block + "\n\n" + code

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=new_code,
            metrics={"imports_added": len(missing_imports)},
        )
