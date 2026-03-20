"""JavaScript syntax validation repair step.

Final gate for JS files — validates via node --check subprocess
with text-based fallback when node is not installed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_JS_KEYWORDS = frozenset({
    "function", "const", "let", "var", "class", "import", "export",
    "require", "module", "return", "if", "else", "for", "while",
    "switch", "case", "break", "continue", "new", "this", "async",
    "await", "try", "catch", "throw",
})

_PYTHON_FINGERPRINTS = (
    "def ", "from __future__", "self.", "#!/usr/bin/env python",
)


class JsSyntaxValidateStep:
    """Final JavaScript syntax validation gate."""

    name: str = "js_syntax_validate"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        valid, error = _validate_js_syntax(code)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid, **({"error": error} if error else {})},
        )


def _validate_js_syntax(code: str) -> tuple[bool, str]:
    """Validate JS source via node --check; fall back to text heuristics."""
    # Check for Python fingerprints
    for fp in _PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try node --check
    try:
        import subprocess
        import tempfile
        import os

        tmp = tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False)
        try:
            tmp.write(code)
            tmp.flush()
            tmp.close()
            result = subprocess.run(
                ["node", "--check", tmp.name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, ""
            return False, f"node syntax error: {result.stderr.strip()[:200]}"
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    except FileNotFoundError:
        pass  # node not installed — fall through
    except Exception:
        pass

    # Text-based fallback
    return _text_based_js_validate(code)


def _text_based_js_validate(code: str) -> tuple[bool, str]:
    """Lightweight text-based JS validation."""
    # Balanced braces
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

    # Must contain at least one JS keyword or arrow function
    has_keyword = any(
        re.search(rf'\b{kw}\b', code) for kw in _JS_KEYWORDS
    ) or "=>" in code
    if not has_keyword:
        return False, "no JavaScript keywords found"

    return True, ""
