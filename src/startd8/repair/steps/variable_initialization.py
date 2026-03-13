"""Variable initialization repair step.

Handles F821 (undefined name) errors via two strategies:
1. **Well-known patterns** — deterministic variable→init mappings
   (e.g. ``fake = Faker()``).
2. **Skeleton ground truth** — when ``RepairContext.skeleton_content``
   is provided, any module-level assignment in the skeleton that is
   missing from the generated code and referenced by an F821 diagnostic
   is re-inserted verbatim.  This covers splicer-induced variable loss
   for project-specific state (config dicts, client singletons, lists).

The ``import_completion`` step adds ``from faker import Faker`` but the
F821 for ``fake`` persists because the *variable* is never assigned.
This step fills that gap.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ..models import (
    ElementContext,
    LintDiagnostic,
    RepairContext,
    RepairStepResult,
)

# Well-known variable → (required_import, initialization_statement).
# Only includes patterns where the initialization is deterministic
# (no constructor arguments that depend on runtime context).
_WELL_KNOWN_VARIABLE_INITS: dict[str, tuple[str, str]] = {
    # Faker — universally "fake = Faker()"
    "fake": ("from faker import Faker", "fake = Faker()"),
}


def _collect_defined_names(code: str) -> set[str]:
    """Return names assigned at module level via AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(
            getattr(node, "target", None), ast.Name,
        ):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _extract_module_level_assignments(code: str) -> dict[str, str]:
    """Extract module-level assignment statements from source code.

    Returns a mapping of variable name → source line(s) for the assignment.
    Only captures simple assignments (``x = ...``) and annotated assignments
    (``x: T = ...``) — not function/class defs or imports.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    lines = code.splitlines()
    assignments: dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    start = node.lineno - 1
                    end = node.end_lineno or node.lineno
                    stmt = "\n".join(lines[start:end])
                    assignments[target.id] = stmt
        elif isinstance(node, ast.AnnAssign) and isinstance(
            getattr(node, "target", None), ast.Name,
        ):
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            stmt = "\n".join(lines[start:end])
            assignments[node.target.id] = stmt
    return assignments


def _find_init_insertion_line(lines: list[str]) -> int:
    """Find the line index where a module-level initialization should go.

    Inserts after the last import block (before the first function/class
    definition or module-level code).
    """
    last_import_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and "(" not in stripped:
            last_import_line = i + 1
        elif stripped.startswith(("import ", "from ")) and "(" in stripped:
            # Multi-line import — skip until closing paren
            last_import_line = i + 1
            for j in range(i + 1, len(lines)):
                last_import_line = j + 1
                if ")" in lines[j]:
                    break
    return last_import_line


def _extract_f821_names(
    diagnostics: list,
    file_path: Path,
) -> set[str]:
    """Extract undefined names from F821 diagnostics matching the given file."""
    f821_names: set[str] = set()
    for diag in diagnostics:
        if (
            isinstance(diag, LintDiagnostic)
            and diag.rule == "F821"
            and (
                diag.file == str(file_path)
                or diag.file == file_path.name
                or Path(diag.file).name == file_path.name
            )
        ):
            match = re.search(
                r"Undefined name [`'](?P<name>[^`']+)[`']",
                diag.message,
            )
            if match:
                f821_names.add(match.group("name"))
    return f821_names


class VariableInitializationStep:
    """Insert module-level variable initializations for well-known patterns
    and skeleton-derived ground truth."""

    name: str = "variable_initialization"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        all_f821_names = _extract_f821_names(context.diagnostics, file_path)
        if not all_f821_names:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        defined = _collect_defined_names(code)
        missing = all_f821_names - defined
        if not missing:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines()
        insert_idx = _find_init_insertion_line(lines)
        inits_added: list[str] = []
        imports_added: list[str] = []
        skeleton_recovered: list[str] = []

        # Strategy 1: Well-known patterns
        well_known_handled: set[str] = set()
        for var_name in sorted(missing):
            if var_name in _WELL_KNOWN_VARIABLE_INITS:
                required_import, init_stmt = _WELL_KNOWN_VARIABLE_INITS[var_name]
                if required_import not in code:
                    imports_added.append(required_import)
                inits_added.append(init_stmt)
                well_known_handled.add(var_name)

        # Strategy 2: Skeleton ground truth recovery
        remaining = missing - well_known_handled
        if remaining and context.skeleton_content:
            skeleton_assignments = _extract_module_level_assignments(
                context.skeleton_content,
            )
            for var_name in sorted(remaining):
                if var_name in skeleton_assignments:
                    inits_added.append(skeleton_assignments[var_name])
                    skeleton_recovered.append(var_name)

        if not inits_added and not imports_added:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Build insertion block: imports first, then blank line, then inits
        insertion_lines: list[str] = []
        if imports_added:
            insertion_lines.extend(imports_added)
        if inits_added:
            if insertion_lines:
                insertion_lines.append("")
            insertion_lines.extend(inits_added)
        insertion_lines.append("")  # trailing blank line

        new_lines = lines[:insert_idx] + insertion_lines + lines[insert_idx:]
        new_code = "\n".join(new_lines)

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=new_code,
            metrics={
                "variables_initialized": inits_added,
                "imports_added": imports_added,
                "skeleton_recovered": skeleton_recovered,
            },
        )
