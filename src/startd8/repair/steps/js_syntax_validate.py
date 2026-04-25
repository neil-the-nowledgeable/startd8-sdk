"""JavaScript syntax validation repair step.

Final gate for JS files — validates via node --check subprocess
with text-based fallback when node is not installed.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ...languages._validation_utils import PYTHON_FINGERPRINTS, check_balanced_braces
from ..models import ElementContext, RepairContext, RepairStepResult
from ..vue_sfc_repair import vue_script_slice

_JS_KEYWORDS = frozenset({
    "function", "const", "let", "var", "class", "import", "export",
    "require", "module", "return", "if", "else", "for", "while",
    "switch", "case", "break", "continue", "new", "this", "async",
    "await", "try", "catch", "throw",
})


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
        sl = vue_script_slice(code, file_path)
        work = sl.script if sl is not None else code
        valid, error = _validate_js_syntax(work)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid, **({"error": error} if error else {})},
        )


def _validate_js_syntax(code: str) -> tuple[bool, str]:
    """Validate JS source via node --check; fall back to text heuristics."""
    for fp in PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try node --check
    try:
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
    except (OSError, subprocess.TimeoutExpired):
        pass  # filesystem/timeout error — fall through

    # Text-based fallback
    return _text_based_js_validate(code)


def _text_based_js_validate(code: str) -> tuple[bool, str]:
    """Lightweight text-based JS validation."""
    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    has_keyword = any(
        re.search(rf'\b{kw}\b', code) for kw in _JS_KEYWORDS
    ) or "=>" in code
    if not has_keyword:
        return False, "no JavaScript keywords found"

    return True, ""
