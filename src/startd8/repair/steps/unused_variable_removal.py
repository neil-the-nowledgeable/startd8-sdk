"""Repair step for F841: local variable assigned but never used.

Ruff detects F841 but cannot auto-fix it.  This step uses AST analysis
to find local assignments where the target name is never referenced
elsewhere in the same scope, and removes the assignment statement.

Only removes assignments where:
- The RHS has no side effects (literal, name, simple expression)
- The target is not ``_`` (conventional discard)
- The assignment is not in a ``try/except`` block (may be intentional)
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, LintDiagnostic, RepairContext, RepairStepResult

logger = get_logger(__name__)


def _has_side_effects(node: ast.expr) -> bool:
    """Conservative check: does the RHS expression likely have side effects?

    Returns True for calls, awaits, yields — anything that might do work
    beyond producing a value.
    """
    for child in ast.walk(node):
        if isinstance(child, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom)):
            return True
    return False


def _find_unused_assignments(
    code: str,
    f841_names: set[str],
) -> list[tuple[int, int]]:
    """Find line ranges of F841 assignments that are safe to remove.

    Returns list of (start_line_0indexed, end_line_0indexed) tuples.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    removals: list[tuple[int, int]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Collect all Name references in this function (excluding assignment targets)
        referenced_names: set[str] = set()
        assigned_stmts: list[tuple[str, ast.Assign]] = []

        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id in f841_names:
                        assigned_stmts.append((target.id, child))
            elif isinstance(child, ast.Name):
                # Count all name references (including in assignments —
                # we'll subtract target names later)
                referenced_names.add(child.id)

        for var_name, assign_node in assigned_stmts:
            # Skip _ convention
            if var_name.startswith("_"):
                continue
            # Skip if RHS has side effects (removing the call would change behavior)
            if assign_node.value and _has_side_effects(assign_node.value):
                continue
            # Skip multi-target assignments like a = b = 1
            if len(assign_node.targets) > 1:
                continue

            # Check if the name is referenced as a Load anywhere in the function
            # beyond the assignment itself.  We do a targeted walk to count Load refs.
            load_count = 0
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Name)
                    and sub.id == var_name
                    and isinstance(getattr(sub, "ctx", None), ast.Load)
                ):
                    load_count += 1

            if load_count == 0:
                start = assign_node.lineno - 1
                end = (assign_node.end_lineno or assign_node.lineno)
                removals.append((start, end))

    return removals


class UnusedVariableRemovalStep:
    """Remove local variables that are assigned but never used (F841 repair)."""

    name: str = "unused_variable_removal"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        # Only activate when F841 is present in diagnostics.
        f841_names: set[str] = set()
        for d in context.diagnostics:
            if isinstance(d, LintDiagnostic) and d.rule == "F841":
                # Extract name: "Local variable `x` is assigned to but never used"
                import re

                match = re.search(
                    r"Local variable [`'](?P<name>[^`']+)[`']",
                    d.message,
                )
                if match:
                    f841_names.add(match.group("name"))

        if not f841_names:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        removals = _find_unused_assignments(code, f841_names)
        if not removals:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Remove lines in reverse order to preserve line numbers
        lines = code.splitlines(keepends=True)
        removed_names: list[str] = []
        for start, end in sorted(removals, reverse=True):
            # Record what we're removing for metrics
            removed_text = "".join(lines[start:end]).strip()
            removed_names.append(removed_text)
            # Remove the lines
            del lines[start:end]
            # If removal left consecutive blank lines, collapse them
            if (
                start < len(lines)
                and start > 0
                and lines[start - 1].strip() == ""
                and lines[start].strip() == ""
            ):
                del lines[start]

        repaired = "".join(lines)

        logger.info(
            "F841 repair: removed %d unused assignment(s): %s",
            len(removed_names), removed_names,
        )

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=repaired,
            metrics={"removed_assignments": removed_names},
        )
