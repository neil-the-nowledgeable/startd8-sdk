"""Fence strip repair step (REQ-RPL-100).

Removes markdown code fences from LLM-generated code.
Delegates to ``extract_code_from_response()`` — truly shared,
no level-specific adaptation needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...utils.code_extraction import extract_code_from_response
from ..models import ElementContext, RepairContext, RepairStepResult


class FenceStripStep:
    """Strip markdown code fences from generated code."""

    name: str = "fence_strip"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        stripped = extract_code_from_response(code)
        modified = stripped != code
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=stripped,
            metrics={"had_fences": modified},
        )
