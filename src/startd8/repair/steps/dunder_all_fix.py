"""Repair step for F822: undefined names in ``__all__``.

Ruff detects F822 but cannot auto-fix it. This step uses AST to find
module-level ``__all__`` assignments, checks each name against the
module's actual top-level definitions, and strips undefined names.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, LintDiagnostic, RepairContext, RepairStepResult

logger = get_logger(__name__)


class DunderAllFixStep:
    """Strip undefined names from ``__all__`` (F822 repair)."""

    name: str = "dunder_all_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        # Only activate when F822 is present in diagnostics.
        has_f822 = any(
            isinstance(d, LintDiagnostic) and d.rule == "F822"
            for d in context.diagnostics
        )
        if not has_f822:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
                metrics={"error": "syntax_error"},
            )

        # Collect module-level defined names.
        defined_names: set[str] = set()
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined_names.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined_names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_names.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined_names.add(node.target.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)

        # Find __all__ assignment and filter undefined names.
        # Work on the source text to preserve formatting.
        lines = code.splitlines(keepends=True)
        modified = False

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                continue

            # Extract current __all__ values.
            if not isinstance(node.value, ast.List):
                continue

            current_names = []
            for elt in node.value.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    current_names.append(elt.value)

            undefined = [n for n in current_names if n not in defined_names]
            if not undefined:
                continue

            valid_names = [n for n in current_names if n in defined_names]

            if not valid_names:
                # All names undefined — remove __all__ entirely.
                start = node.lineno - 1
                end = node.end_lineno if node.end_lineno else node.lineno
                for i in range(start, end):
                    lines[i] = ""
            else:
                # Replace __all__ with only valid names.
                names_str = ", ".join(f'"{n}"' for n in valid_names)
                new_all = f"__all__ = [{names_str}]\n"
                start = node.lineno - 1
                end = node.end_lineno if node.end_lineno else node.lineno
                lines[start] = new_all
                for i in range(start + 1, end):
                    lines[i] = ""

            logger.info(
                "F822 repair: removed %d undefined name(s) from __all__: %s",
                len(undefined), undefined,
            )
            modified = True
            break  # Only one __all__ expected

        if not modified:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        repaired = "".join(lines)
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=repaired,
            metrics={"undefined_removed": undefined},
        )
