"""AST validation repair step (REQ-RPL-106).

Final gate — validates that code parses via ``ast.parse()``.
Level-specific: uses class-wrapper fallback when
``element_context.parent_class`` is set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult
from ..protocol import AstParseValidator

# Stateless singleton — safe for concurrent use (no mutable state).
_validator = AstParseValidator()


class AstValidateStep:
    """Final AST validation gate."""

    name: str = "ast_validate"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        is_method = bool(
            element_context and element_context.parent_class
        )
        valid = _validator.validate(code, is_method)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid},
        )
