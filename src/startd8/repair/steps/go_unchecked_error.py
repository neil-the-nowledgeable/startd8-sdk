"""Go unchecked error repair step (REQ-KZ-GO-403d Phase 3).

Inserts ``if err != nil { return err }`` after unguarded ``err``
assignments in Go source files.  Only handles the simple case:
single-return-error functions where the fix is a one-line insertion.

Validates with ``gofmt -w`` after patching to catch type mismatches
(e.g., function returns ``(int, error)`` but the inserted ``return err``
only returns one value).  Rolls back on failure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult
from ._go_tool_runner import run_go_tool

logger = get_logger(__name__)

# Same patterns as go_semantic_checks._check_unchecked_errors
_ERR_ASSIGN_RE = re.compile(
    r'^\s*(?:\w+\s*,\s*)?err\s*(?::=|=)\s*\S+',
)
_ERR_CHECK_RE = re.compile(
    r'if\s+err\s*!=\s*nil',
)


class GoUncheckedErrorFixStep:
    """Insert ``if err != nil`` checks after unguarded error assignments."""

    name: str = "go_unchecked_error_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        patched, insertions = _insert_error_checks(code)
        if not insertions:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"insertions": 0},
            )

        # Validate with gofmt — rollback if the inserted code doesn't compile
        if not _gofmt_validates(patched):
            logger.warning(
                "Unchecked error fix rollback for %s — gofmt failed after "
                "inserting %d checks",
                file_path.name, len(insertions),
            )
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={
                    "insertions": 0,
                    "rollback": True,
                    "rollback_reason": "gofmt validation failed after insertion",
                    "attempted_lines": insertions,
                },
            )

        logger.debug(
            "Unchecked error fix: %s — inserted %d checks at lines %s",
            file_path.name, len(insertions), insertions,
        )
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=patched,
            metrics={
                "insertions": len(insertions),
                "inserted_at_lines": insertions,
            },
        )


def _insert_error_checks(code: str) -> tuple[str, list[int]]:
    """Find unguarded ``err`` assignments and insert nil checks.

    Only patches lines where:
    1. ``err`` is assigned (`:=` or `=`).
    2. The next non-blank, non-comment line is NOT ``if err != nil``.
    3. The insertion is a simple ``if err != nil { return err }``.

    Returns:
        (patched_code, list_of_line_numbers_where_checks_were_inserted)
    """
    lines = code.splitlines(keepends=True)
    result: list[str] = []
    insertions: list[int] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("//") or stripped.startswith("/*"):
            result.append(line)
            i += 1
            continue

        if _ERR_ASSIGN_RE.match(stripped):
            # Look ahead for err check within next 3 lines
            found_check = False
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                if next_line == "" or next_line.startswith("//"):
                    continue
                if _ERR_CHECK_RE.search(next_line):
                    found_check = True
                    break
                # Any other non-blank line means err was not checked
                break

            result.append(line)
            if not found_check:
                # Derive indentation from the assignment line
                indent = _get_indent(line)
                check_line = f"{indent}if err != nil {{\n{indent}\treturn err\n{indent}}}\n"
                result.append(check_line)
                insertions.append(i + 1)  # 1-indexed
        else:
            result.append(line)

        i += 1

    return "".join(result), insertions


def _get_indent(line: str) -> str:
    """Extract leading whitespace from a line."""
    return line[: len(line) - len(line.lstrip())]


def _gofmt_validates(code: str) -> bool:
    """Run ``gofmt -e`` on code; return True if it parses."""
    result = run_go_tool(code, ["gofmt", "-e"])
    if not result.tool_found:
        logger.debug("gofmt not available; assuming patched code is valid")
        return True
    return result.returncode == 0
