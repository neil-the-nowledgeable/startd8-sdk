"""TODO uncomment repair step (REQ-TCW-253).

Strips TODO-adjacent commented-out code blocks from LLM-generated output.
Runs after ``fence_strip`` (fences may wrap commented blocks) and before
``ast_validate`` (commented-out code would fail AST parsing).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult


class TodoUncommentStep:
    """Strip commented-out code blocks adjacent to TODO markers."""

    name: str = "todo_uncomment"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        from startd8.validators.todo_scanner import uncomment_block, _detect_language

        language = _detect_language(str(file_path))

        result, count = uncomment_block(code, language=language)
        return RepairStepResult(
            step_name=self.name,
            modified=count > 0,
            code=result,
            metrics={"blocks_uncommented": count},
        )
