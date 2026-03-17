"""Go body splicing — splice generated function bodies into skeleton files.

Uses text-based brace matching (no AST required). Go's brace-delimited
syntax makes this reliable:
1. Find function/method declaration by name
2. Locate opening ``{``
3. Match closing ``}`` via depth counting
4. Replace body lines with new implementation
5. Optionally run ``gofmt`` to normalize formatting

Handles:
- Package-level functions: ``func Name(...)``
- Methods with receivers: ``func (r *Type) Name(...)``
- Multi-line signatures
- Nested braces in function bodies
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)

_GOFMT_TIMEOUT = 15

# Stub markers for Go skeleton files
GO_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"
GO_STUB_PATTERNS = [
    re.compile(r'panic\s*\(\s*"not implemented"'),
    re.compile(r'panic\s*\(\s*"TODO'),
    re.compile(r'panic\s*\(\s*"unimplemented'),
]


@dataclass
class GoSpliceResult:
    """Result of a Go body splice operation."""

    code: Optional[str] = None
    functions_spliced: int = 0
    functions_skipped: int = 0
    warnings: List[str] = field(default_factory=list)


def _find_func_declaration(
    lines: List[str],
    func_name: str,
    receiver_type: Optional[str] = None,
) -> Optional[int]:
    """Find the line index of a function/method declaration by name.

    Args:
        lines: Source file lines.
        func_name: Function name to find.
        receiver_type: If provided, matches method with this receiver type.

    Returns:
        Line index (0-based) or None if not found.
    """
    if receiver_type:
        # Method: func (r *Type) Name( or func (r Type) Name(
        pattern = re.compile(
            rf"^func\s+\(\s*\w+\s+\*?{re.escape(receiver_type)}\s*\)\s+"
            rf"{re.escape(func_name)}\s*\(",
        )
    else:
        # Function: func Name(
        pattern = re.compile(
            rf"^func\s+{re.escape(func_name)}\s*\(",
        )

    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def _find_body_range(
    lines: List[str],
    decl_line: int,
) -> Optional[Tuple[int, int]]:
    """Find the body range (open brace line, close brace line) of a function.

    Handles multi-line signatures by scanning forward from decl_line
    until the opening ``{`` is found.

    Args:
        lines: Source file lines.
        decl_line: Line index where the function declaration starts.

    Returns:
        Tuple of (open_brace_line, close_brace_line) indices, or None.
    """
    # Find the opening brace
    open_line = None
    for i in range(decl_line, min(decl_line + 10, len(lines))):
        if "{" in lines[i]:
            open_line = i
            break

    if open_line is None:
        return None

    # Count braces to find matching close
    depth = 0
    for i in range(open_line, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0:
            return (open_line, i)

    return None


def _is_stub_body(body_lines: List[str]) -> bool:
    """Check if function body lines are a stub."""
    body_text = "\n".join(body_lines)

    # Empty body
    if not body_text.strip():
        return True

    for pattern in GO_STUB_PATTERNS:
        if pattern.search(body_text):
            return True

    return False


def _extract_body_from_generated(
    generated_code: str,
    func_name: str,
    receiver_type: Optional[str] = None,
) -> Optional[str]:
    """Extract a function body from generated code.

    Finds the function by name, extracts the body between braces.

    Returns:
        Body text (lines between ``{`` and ``}``) or None.
    """
    lines = generated_code.splitlines()
    decl = _find_func_declaration(lines, func_name, receiver_type)
    if decl is None:
        return None

    body_range = _find_body_range(lines, decl)
    if body_range is None:
        return None

    open_line, close_line = body_range

    # Extract body lines (between { and })
    # If { is on the declaration line, body starts on next line
    body_lines = []
    first_line = lines[open_line]
    brace_pos = first_line.index("{")
    after_brace = first_line[brace_pos + 1 :].strip()
    if after_brace and after_brace != "}":
        body_lines.append(after_brace)

    for i in range(open_line + 1, close_line):
        body_lines.append(lines[i])

    return "\n".join(body_lines)


def _reindent_body(body: str, indent: str) -> str:
    """Dedent body to zero and re-indent to target level."""
    dedented = textwrap.dedent(body)
    result_lines = []
    for line in dedented.splitlines():
        if line.strip():
            result_lines.append(indent + line.lstrip())
        else:
            result_lines.append("")
    return "\n".join(result_lines)


def splice_go_bodies(
    skeleton: str,
    generated_bodies: Dict[str, str],
    receiver_types: Optional[Dict[str, str]] = None,
) -> GoSpliceResult:
    """Splice generated function bodies into a Go skeleton file.

    Args:
        skeleton: Skeleton file content with stub functions.
        generated_bodies: Dict mapping function names to generated code
            containing the full function (including signature and body).
        receiver_types: Optional dict mapping method names to their
            receiver type names (for method matching).

    Returns:
        GoSpliceResult with spliced code and statistics.
    """
    result = GoSpliceResult()
    lines = skeleton.splitlines()
    receiver_types = receiver_types or {}
    spliced = 0
    skipped = 0

    # Process each function in the skeleton
    for func_name, gen_code in generated_bodies.items():
        recv_type = receiver_types.get(func_name)
        decl = _find_func_declaration(lines, func_name, recv_type)
        if decl is None:
            result.warnings.append(
                f"Function '{func_name}' not found in skeleton"
            )
            skipped += 1
            continue

        body_range = _find_body_range(lines, decl)
        if body_range is None:
            result.warnings.append(
                f"Could not find body braces for '{func_name}'"
            )
            skipped += 1
            continue

        open_line, close_line = body_range

        # Check if the existing body is a stub
        body_lines = lines[open_line + 1 : close_line]
        if not _is_stub_body(body_lines):
            result.warnings.append(
                f"'{func_name}' body is not a stub — skipping"
            )
            skipped += 1
            continue

        # Extract new body from generated code
        new_body = _extract_body_from_generated(gen_code, func_name, recv_type)
        if new_body is None:
            result.warnings.append(
                f"Could not extract body for '{func_name}' from generated code"
            )
            skipped += 1
            continue

        # Determine indentation from the skeleton
        indent = "\t"  # Go convention
        for bl in body_lines:
            if bl.strip():
                indent = bl[: len(bl) - len(bl.lstrip())]
                break

        # Reindent the new body
        reindented = _reindent_body(new_body, indent)

        # Replace the body lines
        # Keep the opening { on decl line, replace body, keep closing }
        new_lines = (
            lines[: open_line + 1]
            + reindented.splitlines()
            + lines[close_line:]
        )
        lines = new_lines
        spliced += 1

    result.code = "\n".join(lines) + "\n"
    result.functions_spliced = spliced
    result.functions_skipped = skipped
    return result


def splice_and_format(
    skeleton: str,
    generated_bodies: Dict[str, str],
    project_root: Optional[Path] = None,
    receiver_types: Optional[Dict[str, str]] = None,
) -> GoSpliceResult:
    """Splice bodies and run gofmt on the result.

    Convenience wrapper that calls splice_go_bodies then formats
    the output with gofmt if available.
    """
    result = splice_go_bodies(skeleton, generated_bodies, receiver_types)
    if result.code is None:
        return result

    gofmt = shutil.which("gofmt")
    if gofmt:
        try:
            proc = subprocess.run(
                [gofmt],
                input=result.code,
                capture_output=True,
                text=True,
                timeout=_GOFMT_TIMEOUT,
                cwd=project_root,
            )
            if proc.returncode == 0 and proc.stdout:
                result.code = proc.stdout
            elif proc.stderr:
                result.warnings.append(f"gofmt: {proc.stderr.strip()}")
        except (subprocess.TimeoutExpired, OSError) as exc:
            result.warnings.append(f"gofmt failed: {exc}")

    return result
