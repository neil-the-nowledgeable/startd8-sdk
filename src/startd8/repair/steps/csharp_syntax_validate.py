"""C# syntax validation repair step.

Final gate for C# files — validates via tree-sitter-c-sharp
with text-based fallback (balanced braces + type declaration check).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_CS_TYPE_DECL_RE = re.compile(
    r"\b(?:class|interface|enum|struct|record)\s+\w+",
)

_PYTHON_FINGERPRINTS = (
    "def ", "import os", "from __future__", "self.", "#!/usr/bin/env python",
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
    # Check for Python fingerprints
    for fp in _PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try tree-sitter
    try:
        from startd8.languages.csharp_parser import validate_csharp_syntax
        return validate_csharp_syntax(code)
    except ImportError:
        pass

    # Text-based fallback
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, "unbalanced braces"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"

    if not _CS_TYPE_DECL_RE.search(code):
        return False, "no type declaration found (class/interface/enum/struct/record)"

    return True, ""
