"""Semantic discarded return repair step (REQ-SR-300).

Fixes ``discarded_return`` warnings where a pure function's return value
is computed and thrown away as a bare expression statement::

    os.environ.get('GCP_PROJECT_ID')    # bare Expr — discarded
    →
    gcp_project_id = os.environ.get('GCP_PROJECT_ID')

Variable name inference: if the first argument is a string constant,
lowercase + replace non-alnum with ``_``.  Fallback: ``_result``.
"""

from __future__ import annotations

import ast
import keyword
import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult, SemanticDiagnostic

logger = get_logger(__name__)


def _infer_variable_name(
    first_arg_value: Optional[str],
    existing_names: set[str],
) -> str:
    """Infer a variable name from a string constant argument.

    Args:
        first_arg_value: The string value of the first call argument, or None.
        existing_names: Names already in scope (for collision avoidance).

    Returns:
        A valid Python identifier.
    """
    if first_arg_value is not None:
        raw = first_arg_value.lower()
        name = re.sub(r"[^a-z0-9]", "_", raw).strip("_")
        name = re.sub(r"_+", "_", name)

        if not name or keyword.iskeyword(name) or name in ("true", "false", "none"):
            return "_result"
        if name in existing_names:
            return f"{name}_value"
        return name

    return "_result"


class SemanticDiscardedReturnFixStep:
    """Assign discarded return values to inferred variable names."""

    name: str = "semantic_discarded_return_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        diagnostics = [
            d for d in context.diagnostics
            if isinstance(d, SemanticDiagnostic)
            and d.semantic_category == "discarded_return"
        ]
        if not diagnostics:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        lines = code.splitlines(keepends=True)
        fixes: list[str] = []

        # Collect existing variable names for collision avoidance
        existing_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                existing_names.add(node.id)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                existing_names.add(node.name)

        # Build repair targets: (line_idx, var_name)
        targets: list[tuple[int, str]] = []
        for diag in diagnostics:
            # Find the matching AST Expr node
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and node.lineno == diag.line
                ):
                    # Single-line only (v1 scope — Q9 decision)
                    if hasattr(node, "end_lineno") and node.end_lineno != node.lineno:
                        logger.debug(
                            "Discarded return at line %d is multi-line — skipping (v1 scope)",
                            diag.line,
                        )
                        break

                    # Infer variable name from first string argument
                    first_arg_value = None
                    if (
                        node.value.args
                        and isinstance(node.value.args[0], ast.Constant)
                        and isinstance(node.value.args[0].value, str)
                    ):
                        first_arg_value = node.value.args[0].value

                    var_name = _infer_variable_name(first_arg_value, existing_names)
                    existing_names.add(var_name)  # prevent duplicates
                    targets.append((node.lineno - 1, var_name))
                    break

        # Apply in reverse line order for stable indices
        for line_idx, var_name in sorted(targets, reverse=True):
            if line_idx < 0 or line_idx >= len(lines):
                continue
            line = lines[line_idx]
            indent = len(line) - len(line.lstrip())
            stripped = line.lstrip()
            lines[line_idx] = " " * indent + var_name + " = " + stripped
            fixes.append(f"assigned discarded return to '{var_name}'")

        modified = len(fixes) > 0
        if modified:
            logger.info(
                "semantic_discarded_return_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(lines),
            metrics={"fixes": fixes},
        )
