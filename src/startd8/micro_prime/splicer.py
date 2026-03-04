"""Body Splicing into Skeleton Files (REQ-MP-200).

Locates ``raise NotImplementedError`` stubs in skeleton files and replaces
them with repaired function bodies, then validates the result via AST.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)

# Sentinel comment marking skeleton files (from file_assembler.py)
_SKELETON_SENTINEL = "# [STARTD8-SKELETON]"

# Pattern to match raise NotImplementedError stubs
_STUB_PATTERN = re.compile(r"^(\s*)raise NotImplementedError.*$", re.MULTILINE)


def splice_body_into_skeleton(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Replace the NotImplementedError stub for an element with its body.

    Finds the element's ``raise NotImplementedError`` stub in the skeleton,
    replaces it with the provided body code, and validates the result.

    Args:
        body: The generated function body (may be a full def or body-only).
        element: The manifest element being spliced.
        skeleton: The full skeleton file content.

    Returns:
        The updated skeleton with the body spliced in, or None if splicing
        fails validation.
    """
    if element.kind in (ElementKind.CONSTANT, ElementKind.VARIABLE):
        return _splice_constant(body, element, skeleton)

    return _splice_function_body(body, element, skeleton)


def _splice_function_body(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Splice a function/method body into its skeleton stub."""
    lines = skeleton.splitlines()

    # Find the def line for this element
    def_line_idx = _find_def_line(element.name, element.kind, lines)
    if def_line_idx is None:
        logger.warning("Could not find def line for %s in skeleton", element.name)
        return None

    # Find the raise NotImplementedError stub after the def line
    stub_idx = _find_stub_after_def(lines, def_line_idx)
    if stub_idx is None:
        logger.warning(
            "Could not find NotImplementedError stub for %s", element.name,
        )
        return None

    # Determine the indentation of the stub
    stub_line = lines[stub_idx]
    stub_indent = stub_line[: len(stub_line) - len(stub_line.lstrip())]

    # Extract just the body from the generated code
    extracted_body = _extract_body(body, element)

    # Re-indent the body to match the stub's indentation while preserving
    # relative indentation (e.g. nested if/else, loops within the body).
    body_lines = extracted_body.splitlines()
    # Find minimum indentation of non-empty lines in the body.
    indents = [
        len(line) - len(line.lstrip())
        for line in body_lines
        if line.strip()
    ]
    min_indent = min(indents) if indents else 0

    reindented = []
    for line in body_lines:
        if line.strip():
            # Strip the base indentation, then prepend stub's indentation.
            reindented.append(stub_indent + line[min_indent:])
        else:
            reindented.append("")

    # Replace the stub line with the body
    new_lines = lines[:stub_idx] + reindented + lines[stub_idx + 1:]
    result = "\n".join(new_lines)

    # Validate
    if not _validate_skeleton(result):
        logger.warning("Spliced skeleton failed AST validation for %s", element.name)
        return None

    return result


def _splice_constant(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Splice a constant value into its skeleton placeholder."""
    lines = skeleton.splitlines()

    # Find the line with the constant's NotImplementedError or placeholder
    target_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Look for patterns like: MY_CONST = ... or MY_CONST: Type = ...
        if stripped.startswith(element.name) and "NotImplementedError" in stripped:
            target_idx = i
            break
        # Also try: MY_CONST: Type = <sentinel>
        if stripped.startswith(element.name) and "STARTD8_AUTO_STUB" in stripped:
            target_idx = i
            break

    if target_idx is None:
        # Try finding by just the name at the start of a line
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{element.name} =") or stripped.startswith(f"{element.name}:"):
                target_idx = i
                break

    if target_idx is None:
        logger.warning("Could not find placeholder for constant %s", element.name)
        return None

    # Get the indentation
    original_line = lines[target_idx]
    indent = original_line[: len(original_line) - len(original_line.lstrip())]

    # Build replacement lines
    body_lines = body.strip().splitlines()
    replacement = [indent + line.lstrip() for line in body_lines]

    new_lines = lines[:target_idx] + replacement + lines[target_idx + 1:]
    result = "\n".join(new_lines)

    if not _validate_skeleton(result):
        logger.warning("Spliced skeleton failed AST validation for constant %s", element.name)
        return None

    return result


def _find_def_line(
    name: str,
    kind: ElementKind,
    lines: list[str],
) -> Optional[int]:
    """Find the line index of the def/class statement for the named element."""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if kind == ElementKind.CLASS:
            if stripped.startswith(f"class {name}"):
                return i
        elif kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD):
            if stripped.startswith(f"async def {name}"):
                return i
        else:
            if stripped.startswith(f"def {name}"):
                return i
    return None


def _find_stub_after_def(lines: list[str], def_idx: int) -> Optional[int]:
    """Find the raise NotImplementedError line after a def.

    Uses AST to locate the function body boundary, then searches within
    that range.  Falls back to scanning until the next top-level statement
    if AST parsing fails.  This replaces the old 20-line window which
    missed stubs pushed beyond long docstrings.
    """
    # Strategy 1: Use AST to find the function's body range.
    body_end = _ast_body_end(lines, def_idx)

    search_end = body_end if body_end is not None else len(lines)
    for i in range(def_idx + 1, search_end):
        if "raise NotImplementedError" in lines[i]:
            return i

    return None


def _ast_body_end(lines: list[str], def_idx: int) -> Optional[int]:
    """Return the line index just past the function body starting at *def_idx*.

    Parses the skeleton starting from *def_idx* through the end of the file.
    Returns the ``end_lineno`` of the function (exclusive) so callers can
    search [def_idx+1, end) for stubs.  Returns ``None`` on parse failure.
    """
    # Determine the indentation level of the def line so we can dedent the
    # slice to column 0 (necessary when the def is inside a class).
    def_line = lines[def_idx]
    def_indent = len(def_line) - len(def_line.lstrip())

    snippet_lines = lines[def_idx:]
    if def_indent > 0:
        # Dedent so the function starts at column 0 for ast.parse.
        snippet_lines = []
        for line in lines[def_idx:]:
            if line.strip():
                snippet_lines.append(line[min(def_indent, len(line)):])
            else:
                snippet_lines.append("")

    snippet = "\n".join(snippet_lines)
    try:
        tree = ast.parse(snippet)
    except SyntaxError:
        return None

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # end_lineno is 1-based and inclusive; convert to absolute line index (exclusive).
            if node.end_lineno is not None:
                return def_idx + node.end_lineno
            break

    return None


def _extract_body(code: str, element: ForwardElementSpec) -> str:
    """Extract just the function body from generated code.

    If the code includes a def line, extract only the body.
    If it's body-only, return as-is.

    Handles the case where imports precede the def line (e.g., from
    over_generation_trim preserving imports alongside the target element).
    """
    stripped = code.strip()

    # Skip leading import lines to find the actual first code line.
    # The over_generation_trim step may preserve imports before the def.
    lines = stripped.split("\n")
    first_code_idx = 0
    for i, line in enumerate(lines):
        lstripped = line.lstrip()
        if lstripped and not lstripped.startswith(("import ", "from ")):
            first_code_idx = i
            break

    first_line = lines[first_code_idx].lstrip() if first_code_idx < len(lines) else ""
    has_def = first_line.startswith(("def ", "async def "))

    # If there were leading imports, strip them — they belong at file level
    if has_def and first_code_idx > 0:
        stripped = "\n".join(lines[first_code_idx:]).strip()

    if not has_def:
        # Body-only — return as-is
        return stripped

    # Has a def line — extract body after the colon
    try:
        tree = ast.parse(stripped)
        if tree.body and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = tree.body[0]
            # Get the body lines (everything after the def line and docstring)
            all_lines = stripped.splitlines()
            # Find where the body starts (skip def line and docstring)
            body_start = func.body[0].lineno - 1
            # If the first body statement is a docstring (Expr(Constant(str)))
            if (
                isinstance(func.body[0], ast.Expr)
                and isinstance(func.body[0].value, ast.Constant)
                and isinstance(func.body[0].value.value, str)
                and len(func.body) > 1
            ):
                body_start = func.body[1].lineno - 1

            body_lines = all_lines[body_start:]
            # Dedent body
            if body_lines:
                # Find minimum indentation
                indents = [
                    len(line) - len(line.lstrip())
                    for line in body_lines
                    if line.strip()
                ]
                if indents:
                    min_indent = min(indents)
                    body_lines = [
                        line[min_indent:] if line.strip() else ""
                        for line in body_lines
                    ]
            return "\n".join(body_lines)
    except SyntaxError:
        pass

    # Fallback: skip first line (the def line)
    rest_lines = stripped.splitlines()[1:]
    if rest_lines:
        indents = [
            len(line) - len(line.lstrip())
            for line in rest_lines
            if line.strip()
        ]
        if indents:
            min_indent = min(indents)
            rest_lines = [
                line[min_indent:] if line.strip() else ""
                for line in rest_lines
            ]
    return "\n".join(rest_lines)


def _validate_skeleton(skeleton: str) -> bool:
    """Validate that the full skeleton passes ast.parse()."""
    try:
        ast.parse(skeleton)
        return True
    except SyntaxError:
        return False
