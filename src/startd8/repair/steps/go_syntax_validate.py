"""Go syntax validation repair step.

Final gate for Go files — validates via gofmt -e subprocess
with text-based fallback when gofmt is not installed.
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

# Go type/function declarations
_GO_DECL_RE = re.compile(r"\b(?:func|type|var|const)\s+\w+")


class GoSyntaxValidateStep:
    """Final Go syntax validation gate."""

    name: str = "go_syntax_validate"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        valid, error = _validate_go_syntax(code)
        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"valid": valid, **({"error": error} if error else {})},
        )


def _validate_go_syntax(code: str) -> tuple[bool, str]:
    """Validate Go source via gofmt; fall back to text heuristics."""
    for fp in PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    # Try gofmt first
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".go", mode="w", delete=False)
        try:
            tmp.write(code)
            tmp.flush()
            tmp.close()
            result = subprocess.run(
                ["gofmt", "-e", tmp.name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, ""
            return False, f"gofmt error: {result.stderr.strip()}"
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    except FileNotFoundError:
        pass  # gofmt not installed — fall through to text validation
    except (OSError, subprocess.TimeoutExpired):
        pass  # filesystem/timeout error — fall through

    # Text-based fallback
    return _text_based_go_validate(code)


def _text_based_go_validate(code: str) -> tuple[bool, str]:
    """Lightweight text-based Go validation (no gofmt dependency)."""
    for fp in PYTHON_FINGERPRINTS:
        if fp in code:
            return False, f"Python fingerprint detected: {fp!r}"

    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    if not re.search(r"^\s*package\s+\w+", code, re.MULTILINE):
        return False, "missing package declaration"

    if not _GO_DECL_RE.search(code):
        return False, "no func/type/var/const declaration found"

    return True, ""
