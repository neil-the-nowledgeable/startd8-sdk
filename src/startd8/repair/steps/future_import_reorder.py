"""Future import reorder repair step (REQ-RPL-107).

Moves ``from __future__ import ...`` lines to the correct position
at the beginning of the file (after hashbang, encoding declarations,
docstrings, and leading comments — but before any other imports or code).

This fixes both ``SyntaxError: from __future__ imports must occur at
the beginning of the file`` and ruff ``F404``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# Matches any `from __future__ import ...` line (with optional parentheses)
_FUTURE_IMPORT_RE = re.compile(r"^\s*from\s+__future__\s+import\s+")


def _reorder_future_imports(code: str) -> str:
    """Move all ``from __future__ import`` lines to the top of the file.

    Preserves hashbang, encoding declarations, leading comments, and
    module docstrings above the future imports.
    """
    lines = code.splitlines(keepends=True)

    # Extract future import lines and their indices (including multi-line)
    future_lines: list[str] = []
    future_indices: set[int] = set()
    i = 0
    while i < len(lines):
        line = lines[i]
        if _FUTURE_IMPORT_RE.match(line):
            # Check for multi-line parenthesized import
            if "(" in line and ")" not in line:
                # Collect continuation lines until closing paren
                collected = [line]
                future_indices.add(i)
                i += 1
                while i < len(lines):
                    collected.append(lines[i])
                    future_indices.add(i)
                    if ")" in lines[i]:
                        i += 1
                        break
                    i += 1
                future_lines.extend(collected)
            else:
                future_lines.append(line)
                future_indices.add(i)
                i += 1
        else:
            i += 1

    if not future_lines:
        return code

    # Find the insertion point: after hashbang, encoding, docstring, comments
    insert_at = _find_future_insertion_point(
        [line.rstrip("\n\r") for line in lines],
    )

    # Check if all future imports are already at or before the insertion point
    # and contiguous — if so, nothing to do
    if future_indices and max(future_indices) <= insert_at:
        return code

    # Build removal set: future import lines + their immediately-following blank lines
    removal_indices: set[int] = set(future_indices)
    for idx in sorted(future_indices):
        next_idx = idx + 1
        if next_idx < len(lines) and next_idx not in future_indices and lines[next_idx].strip() == "":
            removal_indices.add(next_idx)

    # Remove future imports and orphaned blank lines
    cleaned: list[str] = [line for i, line in enumerate(lines) if i not in removal_indices]

    # Recalculate insertion point on the cleaned lines
    insert_at = _find_future_insertion_point(
        [line.rstrip("\n\r") for line in cleaned],
    )

    # Build result: before + future imports + separator + after
    before = cleaned[:insert_at]
    after = cleaned[insert_at:]

    result_parts: list[str] = []
    result_parts.extend(before)

    # Ensure blank line before future imports if there's content above
    if before and before[-1].strip() != "":
        result_parts.append("\n")

    result_parts.extend(future_lines)

    # Ensure blank line after future imports if there's content below
    if after and after[0].strip() != "":
        result_parts.append("\n")

    result_parts.extend(after)

    return "".join(result_parts)


def _find_future_insertion_point(lines: list[str]) -> int:
    """Find where ``from __future__`` imports should be inserted.

    Returns the 0-based line index. Future imports go *before* this line.

    Skips past:
    - Hashbang (``#!/...``)
    - Encoding declarations (``# -*- coding: ...``)
    - Leading comments and blank lines
    - Module docstrings (triple-quoted, single or multi-line)
    """
    i = 0
    n = len(lines)

    # Skip hashbang
    if i < n and lines[i].startswith("#!"):
        i += 1

    # Skip leading comments, blank lines, encoding declarations
    while i < n:
        stripped = lines[i].strip()
        if stripped == "" or stripped.startswith("#"):
            i += 1
        else:
            break

    # Skip module docstring (triple-quoted)
    if i < n:
        stripped = lines[i].strip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                if stripped.count(quote) >= 2 and stripped.endswith(quote) and len(stripped) > len(quote):
                    # Single-line docstring
                    i += 1
                else:
                    # Multi-line docstring — find closing quote
                    i += 1
                    while i < n and quote not in lines[i]:
                        i += 1
                    if i < n:
                        i += 1  # skip the closing line
                break

    # Skip blank lines after docstring
    while i < n and lines[i].strip() == "":
        i += 1

    return i


class FutureImportReorderStep:
    """Move ``from __future__ import`` to the top of the file."""

    name: str = "future_import_reorder"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        reordered = _reorder_future_imports(code)
        modified = reordered != code
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=reordered,
            metrics={"reordered": modified},
        )
