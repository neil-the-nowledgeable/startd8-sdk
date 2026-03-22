"""Dedup-require repair step for JavaScript/TypeScript (REQ-KZ-ND-402d Phase 2).

Removes duplicate ``require()`` or ``import`` lines that import the same
module specifier.  Keeps the first occurrence, removes subsequent ones.

**Edge case:** When the same module is imported with different destructuring
patterns (``const {a} = require('x')`` vs ``const {b} = require('x')``),
both lines are kept — merging destructured imports requires AST-level
understanding and is deferred to Phase 3 (ESLint ``no-duplicate-imports``).

Only fires for JS/TS files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

_JS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"})

# Match require('pkg') or from 'pkg'
_REQUIRE_RE = re.compile(
    r"""(?:require\s*\(\s*['"]([^'"]+)['"]\s*\)|"""
    r"""from\s+['"]([^'"]+)['"]\s*;?)""",
)

# Match destructuring pattern: const { a, b } = require(...)
_DESTRUCTURE_RE = re.compile(
    r'(?:const|let|var)\s*\{[^}]+\}\s*=',
)


class DedupRequireStep:
    """Remove duplicate ``require()``/``import`` of the same module."""

    name: str = "dedup_require"

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
        # Track: module → (first_line_index, has_destructuring)
        seen: dict[str, tuple[int, bool]] = {}
        removed = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip comment lines
            if stripped.startswith("//") or stripped.startswith("/*"):
                result_lines.append(line)
                continue

            m = _REQUIRE_RE.search(stripped)
            if m:
                module = m.group(1) or m.group(2)
                has_destructure = bool(_DESTRUCTURE_RE.search(stripped))

                if module in seen:
                    prev_idx, prev_destructure = seen[module]
                    # If either occurrence has destructuring and they differ,
                    # keep both (merging requires AST — deferred to Phase 3)
                    if has_destructure or prev_destructure:
                        result_lines.append(line)
                        continue
                    # Identical non-destructured import — remove duplicate
                    removed += 1
                    continue
                else:
                    seen[module] = (i, has_destructure)

            result_lines.append(line)

        modified = removed > 0
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(result_lines),
            metrics={"duplicates_removed": removed},
        )
