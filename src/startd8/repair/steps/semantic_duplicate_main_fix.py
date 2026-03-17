"""Semantic duplicate main guard repair step (REQ-SR-400).

Removes duplicate ``if __name__ == "__main__"`` blocks, keeping only the
first occurrence.  Multiple guards are a common LLM generation artifact
when the model copies boilerplate from different parts of a reference file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult, SemanticDiagnostic

logger = get_logger(__name__)


def _is_main_guard(node: ast.If) -> bool:
    """Check if an If node is ``if __name__ == "__main__"``."""
    test = node.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1):
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    # Check both orderings
    return (
        (isinstance(left, ast.Name) and left.id == "__name__"
         and isinstance(right, ast.Constant) and right.value == "__main__")
        or
        (isinstance(right, ast.Name) and right.id == "__name__"
         and isinstance(left, ast.Constant) and left.value == "__main__")
    )


class SemanticDuplicateMainFixStep:
    """Remove all but the first ``if __name__ == "__main__"`` block."""

    name: str = "semantic_duplicate_main_fix"

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
            and d.semantic_category == "duplicate_main_guard"
        ]
        if not diagnostics:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        # Find all top-level if __name__ == "__main__" blocks
        guards = [
            node for node in ast.iter_child_nodes(tree)
            if isinstance(node, ast.If) and _is_main_guard(node)
        ]

        if len(guards) < 2:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        lines = code.splitlines(keepends=True)
        fixes: list[str] = []

        # Remove all guards except the first, in reverse order
        for guard in reversed(guards[1:]):
            start = guard.lineno - 1
            end = guard.end_lineno  # 1-indexed inclusive → use as exclusive
            if start < 0 or end > len(lines):
                continue
            del lines[start:end]
            fixes.append(f"removed duplicate __main__ guard at line {guard.lineno}")

        modified = len(fixes) > 0
        if modified:
            logger.info(
                "semantic_duplicate_main_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(lines),
            metrics={"fixes": fixes},
        )
