"""Var-to-const repair step for JavaScript/TypeScript (REQ-KZ-ND-402d Phase 2).

Replaces ``var`` declarations with ``const`` (or ``let`` in for-loops).
Over-constification is acceptable — downstream ``node --check`` via
``js_syntax_validate`` catches reassignment of ``const`` bindings,
triggering rollback to the pre-repair version.

Only fires for JS/TS files.  Skips ``var`` inside comments.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})

# for-loop var: for (var i = 0; ...) → for (let i = 0; ...)
_FOR_VAR_RE = re.compile(r'(for\s*\(\s*)var\b')

# Line-start var declaration: var x = ... → const x = ...
_VAR_DECL_RE = re.compile(r'^(\s*)var\s+')


class VarToConstStep:
    """Replace ``var`` with ``const`` (or ``let`` in for-loops)."""

    name: str = "var_to_const"

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
        result_lines: list[str] = []
        count = 0

        for line in lines:
            stripped = line.lstrip()
            # Skip comment lines
            if stripped.startswith("//") or stripped.startswith("/*"):
                result_lines.append(line)
                continue

            new_line = line

            # for-loop var → let
            if _FOR_VAR_RE.search(new_line):
                new_line = _FOR_VAR_RE.sub(r'\1let', new_line)
                if new_line != line:
                    count += 1
            # Other var → const (line-start anchor prevents string matches)
            elif _VAR_DECL_RE.match(new_line):
                new_line = _VAR_DECL_RE.sub(r'\1const ', new_line)
                if new_line != line:
                    count += 1

            result_lines.append(new_line)

        modified = count > 0
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(result_lines),
            metrics={"vars_replaced": count},
        )
