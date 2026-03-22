"""Go dot-import cleanup repair step (REQ-KZ-GO-403d Phase 2).

Rewrites ``import . "pkg"`` to ``import "pkg"`` (both single-line and
multi-line import blocks), then runs ``goimports -w`` to qualify
now-unqualified symbols.

Safety constraint: only cleans up stdlib-recognizable import paths
(no dot in the first path segment).  Custom/internal packages with
many bare exported symbols may break when dot-import is removed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult
from ._go_tool_runner import run_go_tool

logger = get_logger(__name__)

# Match dot-import in a multi-line import block: `. "pkg"` or `. "pkg/sub"`
_DOT_IMPORT_BLOCK_RE = re.compile(
    r'^(\s*)\.\s+"([^"]+)"',
)

# Match single-line dot-import: `import . "pkg"`
_DOT_IMPORT_SINGLE_RE = re.compile(
    r'^(\s*)import\s+\.\s+"([^"]+)"',
)


def _is_stdlib_path(import_path: str) -> bool:
    """Return True if the import path looks like a Go stdlib package.

    Stdlib paths have no dots in the first segment (e.g., ``"fmt"``,
    ``"net/http"``).  Third-party paths start with a domain
    (e.g., ``"github.com/..."``).

    Note: ``golang.org/x/*`` packages contain a dot and are treated as
    third-party by this heuristic.  This is conservative — those packages
    are quasi-stdlib but ``goimports`` may not resolve their bare symbols
    reliably, so skipping them is the safe default.
    """
    first_segment = import_path.split("/")[0]
    return "." not in first_segment


class GoDotImportCleanupStep:
    """Rewrite dot-imports to explicit imports in Go files."""

    name: str = "go_dot_import_cleanup"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        cleaned, count = _remove_dot_imports(code)
        if count == 0:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"dot_imports_cleaned": 0},
            )

        # Run goimports to qualify the now-unqualified symbols
        result = run_go_tool(cleaned, ["goimports", "-w"], read_back=True)
        if not result.tool_found or result.returncode != 0:
            logger.warning(
                "Dot-import cleanup rollback for %s — goimports %s",
                file_path.name,
                "not found" if not result.tool_found else f"failed: {result.stderr.strip()}",
            )
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={
                    "dot_imports_cleaned": 0,
                    "rollback": True,
                    "rollback_reason": "goimports failed after dot-import removal",
                },
            )

        logger.debug(
            "Dot-import cleanup: %s — %d dot-imports converted to explicit",
            file_path.name, count,
        )
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=result.output_code,
            metrics={"dot_imports_cleaned": count},
        )


def _remove_dot_imports(code: str) -> tuple[str, int]:
    """Remove dot-import prefix from import lines.

    Handles both single-line (``import . "pkg"``) and multi-line
    (``import ( ... . "pkg" ... )``) formats.  Only stdlib paths
    are cleaned; third-party dot-imports are left as-is.

    Returns:
        (modified_code, count_of_cleaned_imports)
    """
    lines = code.splitlines(keepends=True)
    result: list[str] = []
    count = 0
    in_import_block = False

    for line in lines:
        stripped = line.strip()

        # Track import block state
        if stripped == "import (":
            in_import_block = True
            result.append(line)
            continue
        if in_import_block and stripped == ")":
            in_import_block = False
            result.append(line)
            continue

        if in_import_block:
            m = _DOT_IMPORT_BLOCK_RE.match(line)
            if m and _is_stdlib_path(m.group(2)):
                # Replace `. "pkg"` with `"pkg"` preserving indent
                indent = m.group(1)
                pkg = m.group(2)
                result.append(f'{indent}"{pkg}"\n')
                count += 1
                continue
        else:
            m = _DOT_IMPORT_SINGLE_RE.match(line)
            if m and _is_stdlib_path(m.group(2)):
                indent = m.group(1)
                pkg = m.group(2)
                result.append(f'{indent}import "{pkg}"\n')
                count += 1
                continue

        result.append(line)

    return "".join(result), count
