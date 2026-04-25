"""Shebang strip repair step (REQ-KZ-ND-400 QW-3).

Removes accidental Python shebang lines from JavaScript/TypeScript files.
These appear when the trivial/simple tier routing emits a Python skeleton
for a Node.js target file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult
from ..vue_sfc_repair import merge_script_back, vue_script_slice

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
        sl = vue_script_slice(code, file_path)
        body = sl.script if sl is not None else code
        if file_path.suffix.lower() not in _JS_EXTENSIONS and sl is None:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = body.splitlines(keepends=True)
        if not lines:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Only check the first line for a shebang
        first = lines[0]
        if first.startswith("#!") and "python" in first.lower():
            cleaned = "".join(lines[1:]).lstrip("\n")
            out = merge_script_back(sl, code, cleaned, True)
            return RepairStepResult(
                step_name=self.name,
                modified=out != code,
                code=out,
                metrics={"shebang_removed": first.strip()},
            )

        out = merge_script_back(sl, code, body, False)
        return RepairStepResult(
            step_name=self.name, modified=False, code=out,
        )
