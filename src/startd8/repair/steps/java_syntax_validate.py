"""Java syntax validation repair step.

Final gate for Java files — validates via javalang parser
with text-based fallback (same logic as ``java.py:validate_syntax()``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...languages._validation_utils import check_balanced_braces
from ..models import ElementContext, RepairContext, RepairStepResult


class JavaSyntaxValidateStep:
    """Final Java syntax validation gate."""

    name: str = "java_syntax_validate"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        valid, error = _validate_java_syntax(code)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid, **({"error": error} if error else {})},
        )


def _validate_java_syntax(code: str) -> tuple[bool, str]:
    """Validate Java source via javalang parser; fall back to text heuristics."""
    # Try javalang first
    try:
        import javalang
        try:
            tree = javalang.parse.parse(code)
            has_type = any(
                isinstance(node, (
                    javalang.tree.ClassDeclaration,
                    javalang.tree.InterfaceDeclaration,
                    javalang.tree.EnumDeclaration,
                ))
                for _, node in tree
                if hasattr(node, '__class__')
            )
            if not has_type:
                return False, "no type declaration found (class/interface/enum)"
            return True, ""
        except javalang.parser.JavaSyntaxError as exc:
            return False, f"javalang syntax error: {exc}"
        except javalang.tokenizer.LexerError as exc:
            return False, f"javalang lexer error: {exc}"
    except ImportError:
        pass  # Fall through to text-based validation

    # Text-based fallback: balanced braces + type declaration
    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    if not re.search(r"\b(?:class|interface|enum|record|@interface)\s+\w+", code):
        return False, "no type declaration found (class/interface/enum/record)"

    return True, ""
