"""Body Splicing into Skeleton Files (REQ-MP-200).

Locates ``raise NotImplementedError`` stubs in skeleton files and replaces
them with repaired function bodies, then validates the result via AST.
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, Signature

logger = get_logger(__name__)

# Sentinel comment marking skeleton files (from file_assembler.py)
_SKELETON_SENTINEL = "# [STARTD8-SKELETON]"


@dataclass(frozen=True)
class SpliceViolation:
    """Typed splice violation for structured repair routing (AC-R12)."""

    violation_type: str  # e.g. "signature_mismatch", "base_class_mismatch"
    message: str
    element_name: str = ""
    expected: str = ""
    actual: str = ""


def _dedent_lines(lines: list[str]) -> list[str]:
    """Strip common leading whitespace from *lines*, preserving relative indentation.

    Empty lines are preserved as empty strings.  Returns the original list
    unchanged if all lines are blank.
    """
    indents = [
        len(line) - len(line.lstrip())
        for line in lines
        if line.strip()
    ]
    if not indents:
        return lines
    min_indent = min(indents)
    if min_indent == 0:
        return lines
    return [
        line[min_indent:] if line.strip() else ""
        for line in lines
    ]


def _leading_whitespace(line: str) -> str:
    """Return the leading whitespace of *line*."""
    return line[: len(line) - len(line.lstrip())]


def _reindent_body(body: str, target_indent: str) -> list[str]:
    """Dedent *body* to zero indent and re-indent every line to *target_indent*.

    Returns a list of reindented lines.  Empty lines become empty strings
    (preserving visual separation without trailing whitespace).
    """
    dedented = textwrap.dedent(body).splitlines()
    return [
        target_indent + line if line.strip() else ""
        for line in dedented
    ]


def _collect_leading_imports(code: str) -> list[str]:
    """Extract leading **single-line** import statements from generated code.

    Returns a list of import lines (``import …`` / ``from … import …``) that
    appear before the first non-import, non-blank line.  These are the imports
    that ``_extract_body`` will strip — capturing them here lets the caller
    re-inject them into the skeleton's import section.

    Multi-line imports (``from x import (\\n  a,\\n  b\\n)``) are skipped to
    avoid injecting fragments.  Ollama almost exclusively emits single-line
    imports so this is safe.
    """
    imports: list[str] = []
    for line in code.strip().splitlines():
        stripped = line.lstrip()
        if not stripped:
            continue
        if stripped.startswith(("import ", "from ")):
            # Skip multi-line imports (open paren without close on same line)
            if "(" in stripped and ")" not in stripped:
                break
            imports.append(stripped)
        else:
            break
    return imports


def _inject_imports(skeleton: str, new_imports: list[str]) -> str:
    """Add import lines to *skeleton* that are not already present.

    Inserts new imports after the last existing ``import``/``from … import``
    line in the file so they stay grouped with the existing import block.
    If the skeleton has no imports, inserts after any leading comments /
    docstrings / ``__future__`` imports.
    """
    if not new_imports:
        return skeleton

    lines = skeleton.splitlines()

    # Build a set of normalised existing imports for dedup.
    existing = set()
    for line in lines:
        s = line.strip()
        if s.startswith(("import ", "from ")):
            existing.add(s)

    to_add = [
        imp for imp in new_imports
        if imp not in existing and "from __future__" not in imp
    ]
    if not to_add:
        return skeleton

    # Find the last import line index to insert after it.
    last_import_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(("import ", "from ")):
            last_import_idx = i

    insert_at = last_import_idx + 1 if last_import_idx >= 0 else 0
    new_lines = lines[:insert_at] + to_add + lines[insert_at:]
    return "\n".join(new_lines)


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

    # Class elements may include class-level attributes or __init__ bodies
    # assembled by the decomposer. Splice those into the class body.
    if element.kind == ElementKind.CLASS:
        return _splice_class_body(body, element, skeleton)

    return _splice_function_body(body, element, skeleton)


def _splice_function_body(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Splice a function/method body into its skeleton stub."""
    lines = skeleton.splitlines()

    # Prefer AST-based stub location (REQ-MP-202)
    stub_idx = None
    try:
        tree = ast.parse(skeleton)
        stub_idx = _find_stub_line_via_ast(element, tree, lines)
    except SyntaxError:
        tree = None

    # Fallback: find def line + scan for stub
    if stub_idx is None:
        def_line_idx = _find_def_line(element.name, element.kind, lines, element.parent_class)
        if def_line_idx is None:
            logger.warning("Could not find def line for %s in skeleton", element.name)
            return None

        stub_idx = _find_stub_after_def(lines, def_line_idx)
        if stub_idx is None:
            logger.warning(
                "Could not find NotImplementedError stub for %s", element.name,
            )
            return None

    # Determine the indentation of the stub
    stub_line = lines[stub_idx]
    stub_indent = _leading_whitespace(stub_line)

    # Collect imports that _extract_body will strip so we can re-inject them.
    element_imports = _collect_leading_imports(body)

    # Extract just the body from the generated code
    extracted_body = _extract_body(body, element)

    # Re-indent the body to match the stub's indentation while preserving
    # relative indentation (e.g. nested if/else, loops within the body).
    reindented = _reindent_body(extracted_body, stub_indent)

    # Replace the stub line with the body
    new_lines = lines[:stub_idx] + reindented + lines[stub_idx + 1:]
    result = "\n".join(new_lines)

    # Re-inject any imports the element needs that the skeleton doesn't have.
    if element_imports:
        result = _inject_imports(result, element_imports)

    # Validate
    if not _validate_skeleton(result):
        logger.warning("Spliced skeleton failed AST validation for %s", element.name)
        return None

    return result


def _get_implemented_methods(class_node: ast.ClassDef) -> set[str]:
    """Return names of methods in *class_node* that have non-stub bodies.

    A method is considered "implemented" if its body is anything other than
    a single ``pass`` or ``raise NotImplementedError``.  These methods were
    already spliced by SIMPLE/TRIVIAL element processing and should not be
    duplicated when the CLASS element body is inserted.
    """
    implemented: set[str] = set()
    for stmt in class_node.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if len(stmt.body) == 1:
            only = stmt.body[0]
            if isinstance(only, ast.Pass):
                continue
            if _is_not_implemented_raise(only):
                continue
        implemented.add(stmt.name)
    return implemented


def _get_all_skeleton_methods(class_node: ast.ClassDef) -> set[str]:
    """Return names of ALL methods in *class_node* (stubs included).

    Used by the deduplication gate: any method that already exists in the
    skeleton class — whether implemented or stub — should be stripped from
    the CLASS element body to avoid F811 redefinition errors.
    """
    return {
        stmt.name
        for stmt in class_node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _strip_duplicate_methods(
    body_lines: list[str],
    implemented: set[str],
) -> list[str]:
    """Remove method definitions and bare method-body fragments from *body_lines*.

    Two cases are handled:

    1. **Full ``def`` blocks** whose name is in *implemented* — the entire
       method (def line + indented body) is removed.
    2. **Bare statements** that are clearly method-body content appearing at
       the base indentation level (``return …``, ``self.…``, ``raise …``) —
       these are artifacts of Ollama generating a method body without the
       ``def`` line.  They would cause ``SyntaxError`` at class level.
    """
    # Determine base indentation (the indentation of the first non-blank line).
    # Only bare-statement stripping applies at this level; indented lines
    # within method bodies are always preserved.
    base_indent = 0
    for line in body_lines:
        if line.strip():
            base_indent = len(line) - len(line.lstrip())
            break

    result: list[str] = []
    skip_indent: Optional[int] = None  # indentation level of def being skipped

    for line in body_lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped) if stripped else 0

        # If we're inside a method block being skipped, continue until dedent.
        if skip_indent is not None:
            if not stripped:
                continue  # skip blank lines within skipped method
            if indent > skip_indent:
                continue  # still inside skipped method body
            skip_indent = None  # dedented — stop skipping

        # Check for method def lines whose names are already implemented.
        if stripped.startswith(("def ", "async def ")):
            matched = False
            for prefix in ("async def ", "def "):
                if stripped.startswith(prefix):
                    rest = stripped[len(prefix):]
                    name = rest.split("(")[0].strip()
                    if name in implemented:
                        skip_indent = indent
                        matched = True
                    break
            if matched:
                continue
            result.append(line)
            continue

        # Strip bare statements that cannot legally appear at class level.
        # Only at the base indentation — deeper lines belong to method bodies.
        if (
            stripped
            and indent == base_indent
            and not stripped.startswith(("#", "@", "class "))
            and stripped.startswith(("return ", "return\n", "self.", "raise "))
        ):
            logger.debug("Stripping bare method-body fragment: %s", stripped[:60])
            continue

        result.append(line)

    return result


def _splice_class_body(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Splice class-level body lines into a class definition."""
    lines = skeleton.splitlines()

    try:
        tree = ast.parse(skeleton)
    except SyntaxError:
        logger.warning("Could not parse skeleton while splicing class %s", element.name)
        return None

    class_node = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == element.name:
            class_node = node
            break
    if class_node is None:
        logger.warning("Could not find class %s in skeleton", element.name)
        return None

    # Determine insertion point (after docstring if present)
    insert_line = class_node.lineno  # 1-based line number to insert after
    doc_node = None
    if class_node.body:
        first = class_node.body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant):
            if isinstance(first.value.value, str):
                doc_node = first
    if doc_node is not None and getattr(doc_node, "end_lineno", None):
        insert_line = doc_node.end_lineno

    # Detect class body indentation
    class_line = lines[class_node.lineno - 1]
    class_indent = _leading_whitespace(class_line)
    body_indent = class_indent + "    "

    # Remove class-level NotImplementedError stubs
    remove_ranges: list[tuple[int, int]] = []
    has_non_stub_stmt = False
    for stmt in class_node.body:
        if doc_node is not None and stmt is doc_node:
            continue
        if isinstance(stmt, ast.Pass):
            start = getattr(stmt, "lineno", None)
            end = getattr(stmt, "end_lineno", None) or start
            if start is not None:
                remove_ranges.append((start - 1, end - 1))
            continue
        if _is_not_implemented_raise(stmt):
            start = getattr(stmt, "lineno", None)
            end = getattr(stmt, "end_lineno", None) or start
            if start is not None:
                remove_ranges.append((start - 1, end - 1))
            continue
        has_non_stub_stmt = True

    # Apply removals from bottom to top so indices remain valid
    insert_idx = insert_line
    for start, end in sorted(remove_ranges, reverse=True):
        del lines[start : end + 1]
        if start < insert_idx:
            insert_idx -= (end - start + 1)

    # Guard: if Ollama generated the entire class definition (including the
    # ``class ClassName(Base):`` header), strip the header and extract only
    # the class body.  Without this, _splice_class_body would indent the
    # entire class definition and insert it under the skeleton's class
    # header, producing a nested duplicate (e.g. ``class X: class X: ...``).
    body_lines = body.splitlines()
    _first_code = ""
    for _bl in body_lines:
        _stripped_bl = _bl.strip()
        if _stripped_bl and not _stripped_bl.startswith(("#", "import ", "from ")):
            _first_code = _stripped_bl
            break
    if _first_code.startswith("class ") and element.name in _first_code:
        try:
            _body_tree = ast.parse(body)
            for _node in _body_tree.body:
                if isinstance(_node, ast.ClassDef) and _node.name == element.name:
                    # Extract only the class body (everything after the class header)
                    _all = body.splitlines()
                    _body_start = _node.body[0].lineno - 1
                    _body_content = "\n".join(_all[_body_start:])
                    body = textwrap.dedent(_body_content)
                    body_lines = body.splitlines()
                    logger.debug(
                        "Stripped class header from generated body for %s",
                        element.name,
                    )
                    break
        except SyntaxError:
            pass  # fall through to normal splice path

    # ── Deduplication gate (run-038 fix) ──
    # When both CLASS and METHOD elements are in the element list, methods
    # are spliced first (SIMPLE/TRIVIAL tier).  The CLASS body from Ollama
    # may include those same method implementations, causing duplicates
    # and bare-statement bugs.  Strip ANY method that already exists in the
    # skeleton class — including stubs — to prevent F811 redefinition errors.
    existing = _get_all_skeleton_methods(class_node)
    if existing:
        body_lines = _strip_duplicate_methods(body_lines, existing)
        logger.debug(
            "Stripped %d existing skeleton methods from class body for %s: %s",
            len(existing), element.name, existing,
        )

    # Split out __init__ block if present in assembled body
    init_block: Optional[list[str]] = None
    init_start = None
    init_indent = 0
    for i, line in enumerate(body_lines):
        stripped = line.lstrip()
        if stripped.startswith(("def __init__(", "async def __init__(")):
            init_start = i
            init_indent = len(line) - len(stripped)
            break
    if init_start is not None:
        block: list[str] = [body_lines[init_start]]
        j = init_start + 1
        while j < len(body_lines):
            ln = body_lines[j]
            if not ln.strip():
                block.append(ln)
                j += 1
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent > init_indent:
                block.append(ln)
                j += 1
                continue
            break
        init_block = block
        body_lines = body_lines[:init_start] + body_lines[j:]

    # Build insertion lines for class-level attrs / other statements
    body_str = "\n".join(body_lines).strip()
    if not body_str or body_str == "pass":
        if has_non_stub_stmt:
            result = "\n".join(lines)
            if not _validate_skeleton(result):
                logger.warning("Spliced class failed AST validation for %s", element.name)
                return None
            # Still allow __init__ replacement below if present.
            insert_lines: list[str] = []
        else:
            insert_lines = [f"{body_indent}pass"]
    else:
        insert_lines = [
            f"{body_indent}{line}" if line.strip() else ""
            for line in body_lines
        ]

    # Insert body after the docstring / class def line
    lines = lines[:insert_idx] + insert_lines + lines[insert_idx:]
    result = "\n".join(lines)
    init_insert_idx = insert_idx + len(insert_lines)

    # If __init__ block exists and class already defines __init__, replace its stub body.
    if init_block:
        has_init = any(
            isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "__init__"
            for stmt in class_node.body
        )
        if has_init:
            init_spec = ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="__init__",
                signature=Signature(
                    params=[Param(name="self")],
                    return_annotation="None",
                ),
                parent_class=element.name,
            )
            init_body = _extract_body("\n".join(init_block), init_spec)
            def_idx = _find_def_line(
                "__init__", ElementKind.METHOD, result.splitlines(),
                parent_class=element.name,
            )
            if def_idx is not None:
                stub_idx = _find_stub_after_def(result.splitlines(), def_idx)
                if stub_idx is not None:
                    res_lines = result.splitlines()
                    stub_line = res_lines[stub_idx]
                    stub_indent = _leading_whitespace(stub_line)
                    reindented = _reindent_body(init_body, stub_indent)
                    res_lines = res_lines[:stub_idx] + reindented + res_lines[stub_idx + 1:]
                    result = "\n".join(res_lines)
        else:
            # No __init__ in skeleton — insert the assembled __init__ block.
            init_lines = [
                f"{body_indent}{line}" if line.strip() else ""
                for line in init_block
            ]
            res_lines = result.splitlines()
            res_lines = res_lines[:init_insert_idx] + init_lines + res_lines[init_insert_idx:]
            result = "\n".join(res_lines)

    if not _validate_skeleton(result):
        logger.warning("Spliced class failed AST validation for %s", element.name)
        return None

    return result


def _is_not_implemented_raise(stmt: ast.stmt) -> bool:
    """Return True if the statement raises NotImplementedError."""
    if not isinstance(stmt, ast.Raise):
        return False
    exc = stmt.exc
    if isinstance(exc, ast.Name):
        return exc.id == "NotImplementedError"
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
        return exc.func.id == "NotImplementedError"
    return False


def _find_target_node(
    tree: ast.AST,
    element: ForwardElementSpec,
) -> Optional[ast.AST]:
    """Find the AST node for the target element.

    Delegates to the shared ``find_element_node`` helper (X-1).
    """
    from startd8.micro_prime._ast_utils import find_element_node

    return find_element_node(tree, element)  # type: ignore[arg-type]


def _find_stub_line_via_ast(
    element: ForwardElementSpec,
    tree: ast.AST,
    lines: list[str],
) -> Optional[int]:
    """Locate the NotImplementedError stub line via AST (REQ-MP-202)."""
    target = _find_target_node(tree, element)
    if target is None:
        return None

    body = getattr(target, "body", None) or []
    for stmt in body:
        if _is_not_implemented_raise(stmt):
            lineno = getattr(stmt, "lineno", None)
            if lineno is not None and 0 < lineno <= len(lines):
                return lineno - 1
    return None


def _is_name_boundary(text: str, name: str) -> bool:
    """Return True if *name* at the start of *text* ends at a word boundary.

    Prevents false-matching ``MY_CONST`` against ``MY_CONST_EXTENDED``.
    """
    if len(text) <= len(name):
        return True  # name is the entire text
    next_char = text[len(name)]
    return not (next_char.isalnum() or next_char == "_")


def _splice_constant(
    body: str,
    element: ForwardElementSpec,
    skeleton: str,
) -> Optional[str]:
    """Splice a constant value into its skeleton placeholder."""
    lines = skeleton.splitlines()

    search_start = 0
    search_end = len(lines)
    if element.parent_class:
        class_range = _find_class_range(element.parent_class, lines)
        if class_range is not None:
            search_start, search_end = class_range

    # Find the line with the constant's NotImplementedError or placeholder
    target_idx = None
    for i in range(search_start, search_end):
        line = lines[i]
        stripped = line.strip()
        # Look for patterns like: MY_CONST = ... or MY_CONST: Type = ...
        # Use word-boundary check to avoid false-matching longer names
        # (e.g. matching ``MY_CONST`` against ``MY_CONST_EXTENDED``).
        if (
            stripped.startswith(element.name)
            and _is_name_boundary(stripped, element.name)
            and "NotImplementedError" in stripped
        ):
            target_idx = i
            break
        # Also try: MY_CONST: Type = <sentinel>
        if (
            stripped.startswith(element.name)
            and _is_name_boundary(stripped, element.name)
            and "STARTD8_AUTO_STUB" in stripped
        ):
            target_idx = i
            break

    if target_idx is None:
        # Try finding by just the name at the start of a line
        for i in range(search_start, search_end):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith(f"{element.name} =") or stripped.startswith(f"{element.name}:"):
                target_idx = i
                break

    if target_idx is None:
        logger.warning("Could not find placeholder for constant %s", element.name)
        return None

    # Get the indentation
    original_line = lines[target_idx]
    indent = _leading_whitespace(original_line)

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
    parent_class: Optional[str] = None,
) -> Optional[int]:
    """Find the line index of the def/class statement for the named element.

    Uses ``(`` and ``:``) terminators after the name to avoid false-matching
    longer names that share a prefix (e.g. ``def name_extended``).

    When *parent_class* is provided the search is scoped to the body of that
    class, preventing false matches against methods with the same name in a
    different class.
    """
    # Terminators: ``def foo(`` or ``def foo:`` (single-line ``def foo: ...``)
    # and ``class Foo(`` or ``class Foo:``.
    if kind == ElementKind.CLASS:
        prefixes = (f"class {name}(", f"class {name}:")
    elif kind in (ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD):
        prefixes = (f"async def {name}(",)
    else:
        prefixes = (f"def {name}(",)

    # Determine search range — scope to parent class if given.
    search_start = 0
    search_end = len(lines)
    if parent_class:
        class_idx = _find_class_range(parent_class, lines)
        if class_idx is not None:
            search_start, search_end = class_idx

    for i in range(search_start, search_end):
        stripped = lines[i].lstrip()
        if any(stripped.startswith(p) for p in prefixes):
            return i
    return None


def _find_class_range(
    class_name: str,
    lines: list[str],
) -> Optional[tuple[int, int]]:
    """Return ``(start, end)`` line range for *class_name* in *lines*.

    *start* is the line after the ``class`` header; *end* is exclusive.
    Returns ``None`` if the class is not found.
    """
    class_prefixes = (f"class {class_name}(", f"class {class_name}:")
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if any(stripped.startswith(p) for p in class_prefixes):
            # Use AST to find end of class body
            body_end = _ast_body_end(lines, i)
            end = body_end if body_end is not None else len(lines)
            return (i + 1, end)
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
    if def_idx >= len(lines):
        return None

    # Determine the indentation level of the def line so we can dedent the
    # slice to column 0 (necessary when the def is inside a class).
    def_line = lines[def_idx]
    def_indent = len(def_line) - len(def_line.lstrip())

    snippet_lines = lines[def_idx:]
    if def_indent > 0:
        # Dedent so the function starts at column 0 for ast.parse.
        # min() guards against lines shorter than def_indent (e.g. partial indentation).
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
    lines = stripped.splitlines()
    first_code_idx = 0
    for i, line in enumerate(lines):
        lstripped = line.lstrip()
        if lstripped and not lstripped.startswith(("import ", "from ")):
            first_code_idx = i
            break

    first_line = lines[first_code_idx].lstrip() if first_code_idx < len(lines) else ""
    has_def = first_line.startswith(("def ", "async def "))

    # Strip leading imports — they belong at file level, not inside the body.
    if first_code_idx > 0:
        stripped = "\n".join(lines[first_code_idx:]).strip()

    if not has_def:
        # Body-only — return with imports stripped
        return stripped

    # Has a def line — extract body after the colon
    try:
        tree = ast.parse(stripped)
        if tree.body and isinstance(tree.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = tree.body[0]
            if not func.body:
                # Empty function body (shouldn't happen, but guard it)
                return "pass"
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
            return "\n".join(_dedent_lines(body_lines))
    except SyntaxError:
        logger.debug(
            "AST extraction failed for %s, falling back to line-based",
            element.name,
        )

    # Fallback: skip first line (the def line)
    rest_lines = stripped.splitlines()[1:]
    return "\n".join(_dedent_lines(rest_lines))


def _validate_skeleton(skeleton: str) -> bool:
    """Validate that the full skeleton passes ``ast.parse()``.

    Intentionally validates the entire file (not just the spliced region)
    so that interaction effects between elements are caught early.
    """
    try:
        ast.parse(skeleton)
        return True
    except SyntaxError:
        return False
