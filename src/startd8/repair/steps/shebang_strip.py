"""Shebang strip repair step (REQ-KZ-ND-400 QW-3).

Removes accidental Python shebang lines from JavaScript/TypeScript files.
These appear when the trivial/simple tier routing emits a Python skeleton
for a Node.js target file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})


class ShebangStripStep:
    """Remove Python shebang lines from JS/TS files."""

    name: str = "shebang_strip"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        if file_path.suffix.lower() not in _JS_EXTENSIONS:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines(keepends=True)
        if not lines:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Only check the first line for a shebang
        first = lines[0]
        if first.startswith("#!") and "python" in first.lower():
            cleaned = "".join(lines[1:]).lstrip("\n")
            return RepairStepResult(
                step_name=self.name,
                modified=True,
                code=cleaned,
                metrics={"shebang_removed": first.strip()},
            )

        return RepairStepResult(
            step_name=self.name, modified=False, code=code,
        )
