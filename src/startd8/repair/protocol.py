"""Repair pipeline protocol definitions.

Defines the ``RepairStep`` protocol for pluggable repair steps and
two validation protocols (R2-S1):

- ``StepValidator`` — per-step non-destructive guard (in-memory, per-file)
- ``PipelineValidator`` — post-pipeline re-checkpoint (filesystem, multi-file)

Zero imports from ``contractors/`` — uses only stdlib types.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from typing import Any, List, Optional, Protocol, runtime_checkable

from .models import ElementContext, RepairContext, RepairStepResult


@runtime_checkable
class RepairStep(Protocol):
    """Protocol for a single repair pipeline step."""

    name: str

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult: ...


class StepValidator(Protocol):
    """Per-step non-destructive guard — in-memory, per-file.

    Used between steps to verify the repair didn't break valid code.
    """

    def validate(self, code: str, is_method: bool = False) -> bool: ...


class PipelineValidator(Protocol):
    """Post-pipeline re-checkpoint — filesystem, multi-file, subprocesses.

    Uses only stdlib types. Actual ``CheckpointValidator`` implementation
    lives in ``contractors/`` (R2-S7).
    """

    def validate(self, files: List[Path], feature_name: str) -> List[Any]: ...


# ═══════════════════════════════════════════════════════════════════════════
# Built-in StepValidator implementations
# ═══════════════════════════════════════════════════════════════════════════


class AstParseValidator:
    """StepValidator that wraps ``ast.parse()`` with method fallback."""

    def validate(self, code: str, is_method: bool = False) -> bool:
        """Return True if code parses successfully."""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            pass
        if is_method:
            try:
                wrapped = "class _Wrapper:\n" + textwrap.indent(code, "    ")
                ast.parse(wrapped)
                return True
            except SyntaxError:
                pass
        return False
