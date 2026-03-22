"""Go Python contamination strip repair step (REQ-KZ-GO-403d Phase 2).

Removes lines containing Python fingerprints from Go source files,
then validates with ``gofmt`` to ensure the file still parses.

Context-aware: skips matches inside backtick raw strings, inline
comments, and block comments to avoid false-positive line removal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...languages._validation_utils import GO_CONTAMINATION_FINGERPRINTS
from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult
from ._go_tool_runner import run_go_tool

logger = get_logger(__name__)


class GoPythonContaminationStripStep:
    """Remove Python fingerprint lines from Go files."""

    name: str = "go_contamination_strip"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        cleaned, removed_lines, patterns = _strip_contamination(code)
        if not removed_lines:
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={"lines_removed": 0, "patterns_matched": []},
            )

        # Validate with gofmt — rollback if file no longer parses
        if not _gofmt_validates(cleaned):
            logger.warning(
                "Contamination strip rollback for %s — gofmt failed after "
                "removing %d lines (patterns: %s)",
                file_path.name, len(removed_lines), ", ".join(sorted(patterns)),
            )
            return RepairStepResult(
                step_name=self.name,
                modified=False,
                code=code,
                metrics={
                    "lines_removed": 0,
                    "patterns_matched": list(patterns),
                    "rollback": True,
                    "rollback_reason": "gofmt validation failed after strip",
                },
            )

        logger.debug(
            "Contamination strip: %s — removed %d lines (patterns: %s)",
            file_path.name, len(removed_lines), ", ".join(sorted(patterns)),
        )
        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=cleaned,
            metrics={
                "lines_removed": len(removed_lines),
                "patterns_matched": list(patterns),
            },
        )


def _strip_contamination(code: str) -> tuple[str, list[int], set[str]]:
    """Remove lines matching Python fingerprints with context awareness.

    Returns:
        (cleaned_code, removed_line_numbers, matched_patterns)
    """
    lines = code.splitlines(keepends=True)
    keep: list[str] = []
    removed: list[int] = []
    patterns_found: set[str] = set()
    in_raw_string = False
    in_block_comment = False

    for i, line in enumerate(lines, start=1):
        check_content = line.strip()

        # Track block comment state
        if in_block_comment:
            if "*/" in check_content:
                in_block_comment = False
                # Fall through to check code after */ on this line
                check_content = check_content[check_content.index("*/") + 2:]
            else:
                keep.append(line)
                continue
        if "/*" in check_content:
            if "*/" in check_content:
                # Single-line block comment — remove it, check remainder
                start = check_content.index("/*")
                end = check_content.index("*/") + 2
                check_content = check_content[:start] + check_content[end:]
            else:
                in_block_comment = True
                check_content = check_content[:check_content.index("/*")]

        # Track backtick raw string state
        backtick_count = line.count("`")
        if in_raw_string:
            if backtick_count % 2 == 1:
                in_raw_string = False
            keep.append(line)
            continue
        if backtick_count % 2 == 1:
            in_raw_string = True
            keep.append(line)
            continue

        # Strip inline comment for matching
        comment_pos = check_content.find("//")
        check_text = check_content[:comment_pos].strip() if comment_pos >= 0 else check_content.strip()

        # Check fingerprints
        matched = False
        for fp in GO_CONTAMINATION_FINGERPRINTS:
            if fp in check_text:
                patterns_found.add(fp)
                matched = True
                break  # One match is enough to remove the line

        if matched:
            removed.append(i)
        else:
            keep.append(line)

    return "".join(keep), removed, patterns_found


def _gofmt_validates(code: str) -> bool:
    """Run ``gofmt -e`` on code; return True if it parses.

    Returns True (assume valid) if gofmt is not installed — the step
    should not block repair when the Go toolchain is absent.
    """
    result = run_go_tool(code, ["gofmt", "-e"])
    if not result.tool_found:
        logger.debug("gofmt not available; assuming stripped code is valid")
        return True
    return result.returncode == 0
