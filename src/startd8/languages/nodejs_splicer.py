"""Node.js/TypeScript body splicing — splice generated bodies into skeleton files.

Uses text-based brace matching (same approach as ``go_splicer.py`` and
``java_splicer.py``). JavaScript's brace-delimited syntax makes this reliable:

1. Find function/method declaration by name
2. Locate opening ``{``
3. Match closing ``}`` via depth counting
4. Replace body lines with new implementation

Handles:
- Top-level functions: ``function name(...)`` / ``async function name(...)``
- Arrow functions: ``const name = (...) =>`` (both ``=> {`` and ``=> expr``)
- Function expressions: ``const name = function(...)``
- Class methods: ``  methodName(...) {`` (indented, inside class body)
- Constructors: ``  constructor(...) {``
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

NODEJS_SKELETON_SENTINEL = "// [STARTD8-SKELETON]"

NODEJS_STUB_PATTERNS = [
    re.compile(r'throw\s+new\s+Error\s*\(\s*["\']not implemented'),
    re.compile(r'throw\s+new\s+Error\s*\(\s*["\']TODO'),
    re.compile(r'//\s*TODO'),
    re.compile(r'/\*\s*TODO'),
]

# --- Declaration patterns for splice matching ---

# function name( / async function name(
_FUNC_DECL_RE = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:async\s+)?function\s+(?P<name>\w+)\s*\(",
    re.MULTILINE,
)

# const/let/var name = (...) => { / const name = async (...) => {
_ARROW_DECL_RE = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
    r"(?:async\s+)?\([^)]*\)\s*=>\s*\{",
    re.MULTILINE,
)

# const/let/var name = function(...) {
_FUNC_EXPR_DECL_RE = re.compile(
    r"^(?P<indent>\s*)(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
    r"(?:async\s+)?function\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

# Class method: indented methodName(...) { / async methodName(...) {
_METHOD_DECL_RE = re.compile(
    r"^(?P<indent>\s+)(?:async\s+)?(?P<name>\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)


@dataclass
class NodejsSpliceResult:
    """Result of a Node.js body splice operation."""

    code: Optional[str] = None
    functions_spliced: int = 0
    functions_skipped: int = 0
    warnings: List[str] = field(default_factory=list)


def _is_stub_body(body_lines: List[str]) -> bool:
    """Return True if the body contains only stubs/TODOs."""
    meaningful = [
        ln for ln in body_lines
        if ln.strip() and not ln.strip().startswith("//") and not ln.strip().startswith("/*")
    ]
    if not meaningful:
        return True
    joined = "\n".join(meaningful)
    return any(p.search(joined) for p in NODEJS_STUB_PATTERNS)


def _find_brace_close(lines: List[str], start_line: int, open_brace_col: int = -1) -> int:
    """Find the line index of the matching closing brace.

    Scans from *start_line* (which should contain the opening ``{``),
    counting brace depth until it reaches zero.

    Returns the line index of the closing ``}``, or -1 if not found.
    """
    depth = 0
    in_string = False
    string_char = ""
    in_template = 0  # template literal nesting depth
    in_block_comment = False

    for i in range(start_line, len(lines)):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]

            # Block comment tracking
            if in_block_comment:
                if ch == "*" and j + 1 < len(line) and line[j + 1] == "/":
                    in_block_comment = False
                    j += 2
                    continue
                j += 1
                continue
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "*":
                in_block_comment = True
                j += 2
                continue
            # Line comment — skip rest of line
            if ch == "/" and j + 1 < len(line) and line[j + 1] == "/":
                break

            # String tracking
            if in_string:
                if ch == "\\" and j + 1 < len(line):
                    j += 2  # skip escape
                    continue
                if ch == string_char:
                    in_string = False
                j += 1
                continue
            if ch in ('"', "'"):
                in_string = True
                string_char = ch
                j += 1
                continue
            # Template literals
            if ch == "`":
                in_template += 1
                j += 1
                continue
            if in_template and ch == "`":
                in_template -= 1
                j += 1
                continue

            # Brace counting (outside strings/comments)
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
            j += 1

    return -1


def _find_declaration(
    lines: List[str], name: str,
) -> Optional[tuple[int, str]]:
    """Find the line index and indent of a function/method declaration by name.

    Returns ``(line_index, indent_str)`` or ``None`` if not found.
    """
    source = "\n".join(lines)
    for pattern in (_FUNC_DECL_RE, _ARROW_DECL_RE, _FUNC_EXPR_DECL_RE, _METHOD_DECL_RE):
        for m in pattern.finditer(source):
            if m.group("name") == name:
                line_idx = source[:m.start()].count("\n")
                return line_idx, m.group("indent")
    return None


def splice_nodejs_bodies(
    skeleton: str,
    generated_bodies: Dict[str, str],
) -> NodejsSpliceResult:
    """Splice generated method/function bodies into a JS/TS skeleton.

    For each function name in *generated_bodies*, locates the declaration
    in *skeleton*, verifies the existing body is a stub, and replaces it
    with the generated implementation.

    Args:
        skeleton: Source code with stub function bodies.
        generated_bodies: Mapping of ``function_name`` → ``new_body_code``.

    Returns:
        ``NodejsSpliceResult`` with the spliced code and statistics.
    """
    if not generated_bodies:
        return NodejsSpliceResult(code=skeleton)

    lines = skeleton.splitlines()
    spliced = 0
    skipped = 0
    warnings: List[str] = []

    # Process in reverse line order to preserve indices
    splice_ops: list[tuple[int, int, str, str]] = []  # (start, end, new_body, name)

    for name, new_body in generated_bodies.items():
        decl = _find_declaration(lines, name)
        if decl is None:
            warnings.append(f"Declaration not found for '{name}'")
            skipped += 1
            continue

        decl_line, indent = decl

        # Find the opening brace on the declaration line or the next line
        brace_line = decl_line
        while brace_line < len(lines) and "{" not in lines[brace_line]:
            brace_line += 1
        if brace_line >= len(lines):
            warnings.append(f"Opening brace not found for '{name}'")
            skipped += 1
            continue

        # Find the matching closing brace
        close_line = _find_brace_close(lines, brace_line)
        if close_line < 0:
            warnings.append(f"Closing brace not found for '{name}'")
            skipped += 1
            continue

        # Extract existing body (between braces, exclusive)
        body_start = brace_line + 1
        body_end = close_line
        existing_body = lines[body_start:body_end]

        # Only splice if existing body is a stub
        if not _is_stub_body(existing_body):
            warnings.append(f"'{name}' body is not a stub — skipping")
            skipped += 1
            continue

        # Indent the new body to match the skeleton
        body_indent = indent + "  "  # JS convention: 2-space indent inside body
        new_lines = new_body.strip().splitlines()
        indented = [f"{body_indent}{ln}" if ln.strip() else "" for ln in new_lines]

        splice_ops.append((body_start, body_end, "\n".join(indented), name))

    # Apply splices in reverse order to preserve line indices
    splice_ops.sort(key=lambda op: op[0], reverse=True)
    for body_start, body_end, new_body_text, name in splice_ops:
        lines[body_start:body_end] = new_body_text.splitlines()
        spliced += 1
        logger.debug("Spliced body for '%s' (lines %d-%d)", name, body_start, body_end)

    result_code = "\n".join(lines)
    if skeleton.endswith("\n") and not result_code.endswith("\n"):
        result_code += "\n"

    return NodejsSpliceResult(
        code=result_code,
        functions_spliced=spliced,
        functions_skipped=skipped,
        warnings=warnings,
    )
