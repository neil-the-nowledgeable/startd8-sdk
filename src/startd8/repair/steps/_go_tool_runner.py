"""Shared subprocess helper for Go external tool invocation.

Deduplicates the write-to-tempfile → run-tool → read-back → cleanup
pattern used by ``GoSyntaxValidateStep``, ``GoPythonContaminationStripStep``,
and ``GoDotImportCleanupStep``.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class GoToolResult:
    """Result of running a Go tool on source code."""

    returncode: int
    stdout: str
    stderr: str
    output_code: str  # file content after tool ran (may differ from input if -w flag)
    tool_found: bool  # False if FileNotFoundError


def run_go_tool(
    code: str,
    tool_args: list[str],
    *,
    read_back: bool = False,
    timeout: int = 10,
) -> GoToolResult:
    """Write *code* to a temp ``.go`` file, run *tool_args*, and clean up.

    Args:
        code: Go source to write to the temp file.
        tool_args: Command list — the temp file path is **appended** as the
            last argument (e.g., ``["gofmt", "-e"]`` becomes
            ``["gofmt", "-e", "/tmp/xxx.go"]``).
        read_back: If True, read the temp file back after the tool runs
            (for ``-w`` style tools that modify in place).
        timeout: Subprocess timeout in seconds.

    Returns:
        GoToolResult with returncode, stdout/stderr, output_code, and
        tool_found flag.  On ``FileNotFoundError`` (tool not installed),
        returns ``tool_found=False`` with returncode=-1.
    """
    try:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".go", mode="w", delete=False, encoding="utf-8",
        )
        try:
            tmp.write(code)
            tmp.flush()
            tmp.close()
            result = subprocess.run(
                [*tool_args, tmp.name],
                capture_output=True, text=True, timeout=timeout,
            )
            output_code = code
            if read_back and result.returncode == 0:
                with open(tmp.name, encoding="utf-8") as f:
                    output_code = f.read()
            return GoToolResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                output_code=output_code,
                tool_found=True,
            )
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    except FileNotFoundError:
        return GoToolResult(
            returncode=-1,
            stdout="",
            stderr="tool not found",
            output_code=code,
            tool_found=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return GoToolResult(
            returncode=-1,
            stdout="",
            stderr=str(exc),
            output_code=code,
            tool_found=True,
        )
