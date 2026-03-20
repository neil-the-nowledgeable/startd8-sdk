"""C# syntax validation repair step.

Final gate for C# files — validates via tree-sitter-c-sharp
with text-based fallback (balanced braces + type declaration check).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...languages._validation_utils import PYTHON_FINGERPRINTS, check_balanced_braces
from ..models import ElementContext, RepairContext, RepairStepResult

_CS_TYPE_DECL_RE = re.compile(
    r"\b(?:class|interface|enum|struct|record)\s+\w+",
)


class CSharpSyntaxValidateStep:
    """Final C# syntax validation gate."""

    name: str = "csharp_syntax_validate"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        valid, error = _validate_csharp_syntax(code)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid, **({"error": error} if error else {})},
        )


def _validate_csharp_syntax(code: str) -> tuple[bool, str]:
    """Validate C# source via tree-sitter; fall back to text heuristics."""
    for fp in PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try tree-sitter
    try:
        from startd8.languages.csharp_parser import validate_csharp_syntax
        return validate_csharp_syntax(code)
    except ImportError:
        pass

    # Text-based fallback
    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    if not _CS_TYPE_DECL_RE.search(code):
        return False, "no type declaration found (class/interface/enum/struct/record)"

    return True, ""
