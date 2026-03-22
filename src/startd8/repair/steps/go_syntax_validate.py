"""Go syntax validation repair step.

Final gate for Go files — validates via gofmt -e subprocess
with text-based fallback when gofmt is not installed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...languages._validation_utils import check_balanced_braces
from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult
from ._go_tool_runner import run_go_tool

logger = get_logger(__name__)

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
    """Validate Go source via gofmt; fall back to text heuristics.

    Note: Python contamination detection is owned by
    ``go_semantic_checks._check_python_contamination()`` (REQ-KZ-GO-402a).
    This step focuses on Go syntax validity only.
    """
    result = run_go_tool(code, ["gofmt", "-e"])
    if result.tool_found:
        if result.returncode == 0:
            return True, ""
        return False, f"gofmt error: {result.stderr.strip()}"

    # gofmt not installed — text-based fallback
    logger.debug("gofmt not available; using text-based Go validation")
    return _text_based_go_validate(code)


def _text_based_go_validate(code: str) -> tuple[bool, str]:
    """Lightweight text-based Go validation (no gofmt dependency)."""
    ok, msg = check_balanced_braces(code)
    if not ok:
        return False, msg

    if not re.search(r"^\s*package\s+\w+", code, re.MULTILINE):
        return False, "missing package declaration"

    if not _GO_DECL_RE.search(code):
        return False, "no func/type/var/const declaration found"

    return True, ""
