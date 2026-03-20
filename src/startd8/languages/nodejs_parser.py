"""Node.js/TypeScript regex-based element extractor.

Extracts structural elements (functions, classes, methods) from JS/TS source
code using regex patterns. No AST parser -- handles the common 80% of patterns.

Limitations:
- Does not parse function bodies (no call graph extraction)
- Skips exotic patterns (computed properties, Symbol keys, generators, decorators)
- Multi-line signatures with embedded comments may not parse
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class NodeElement:
    """Parsed JS/TS code element."""

    kind: str  # "function", "class", "method", "const_function", "interface", "type_alias"
    name: str
    is_async: bool = False
    is_exported: bool = False
    line: int = 0
    parent_class: Optional[str] = None
    extends: Optional[str] = None


# --- Regex patterns ---

_FUNC_RE = re.compile(
    r"(?P<exp>export\s+)?(?P<async>async\s+)?function\s+(?P<name>\w+)\s*\(",
    re.MULTILINE,
)

_CLASS_RE = re.compile(
    r"(?P<exp>export\s+)?(?:default\s+)?class\s+(?P<name>\w+)"
    r"(?:\s+extends\s+(?P<base>\w+))?",
    re.MULTILINE,
)

_ARROW_RE = re.compile(
    r"(?P<exp>export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
    r"(?P<async>async\s+)?\([^)]*\)\s*=>",
    re.MULTILINE,
)

_FUNC_EXPR_RE = re.compile(
    r"(?P<exp>export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
    r"(?P<async>async\s+)?function\s*\(",
    re.MULTILINE,
)

_INTERFACE_RE = re.compile(
    r"(?P<exp>export\s+)?interface\s+(?P<name>\w+)",
    re.MULTILINE,
)

_TYPE_ALIAS_RE = re.compile(
    r"(?P<exp>export\s+)?type\s+(?P<name>\w+)\s*=",
    re.MULTILINE,
)

_METHOD_RE = re.compile(
    r"^\s+(?P<async>async\s+)?(?P<name>\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

# Reserved words that look like method calls but aren't
_RESERVED = frozenset({
    "if", "else", "for", "while", "do", "switch", "case", "return",
    "try", "catch", "finally", "throw", "new", "delete", "typeof",
    "instanceof", "void", "yield", "await", "import", "export",
    "default", "break", "continue", "function", "class", "const",
    "let", "var", "with", "super", "this", "constructor",
})


def _line_number(source: str, pos: int) -> int:
    """Return 1-based line number for a position in source."""
    return source[:pos].count("\n") + 1


def _find_class_body_range(source: str, class_match_end: int) -> tuple[int, int]:
    """Find the start and end of a class body (between { and })."""
    idx = source.find("{", class_match_end)
    if idx == -1:
        return -1, -1
    depth = 0
    for i in range(idx, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return idx + 1, i
    return idx + 1, len(source)


def parse_nodejs_source(source: str) -> List[NodeElement]:
    """Extract structural elements from JavaScript/TypeScript source."""
    elements: List[NodeElement] = []
    matched: set[int] = set()

    # --- Top-level functions ---
    for m in _FUNC_RE.finditer(source):
        matched.add(m.start())
        elements.append(NodeElement(
            kind="function", name=m.group("name"),
            is_async=bool(m.group("async")),
            is_exported=bool(m.group("exp")),
            line=_line_number(source, m.start()),
        ))

    # --- Arrow / function expression assignments ---
    for m in _ARROW_RE.finditer(source):
        if m.start() not in matched:
            matched.add(m.start())
            elements.append(NodeElement(
                kind="const_function", name=m.group("name"),
                is_async=bool(m.group("async")),
                is_exported=bool(m.group("exp")),
                line=_line_number(source, m.start()),
            ))

    for m in _FUNC_EXPR_RE.finditer(source):
        if m.start() not in matched:
            matched.add(m.start())
            elements.append(NodeElement(
                kind="const_function", name=m.group("name"),
                is_async=bool(m.group("async")),
                is_exported=bool(m.group("exp")),
                line=_line_number(source, m.start()),
            ))

    # --- Classes (with methods) ---
    for m in _CLASS_RE.finditer(source):
        cls_name = m.group("name")
        elements.append(NodeElement(
            kind="class", name=cls_name,
            is_exported=bool(m.group("exp")),
            extends=m.group("base"),
            line=_line_number(source, m.start()),
        ))

        # Extract methods from class body
        body_start, body_end = _find_class_body_range(source, m.end())
        if body_start < 0:
            continue
        body = source[body_start:body_end]
        for mm in _METHOD_RE.finditer(body):
            name = mm.group("name")
            if name in _RESERVED:
                continue
            elements.append(NodeElement(
                kind="method", name=name,
                is_async=bool(mm.group("async")),
                parent_class=cls_name,
                line=_line_number(source, body_start + mm.start()),
            ))

    # --- TypeScript interfaces ---
    for m in _INTERFACE_RE.finditer(source):
        elements.append(NodeElement(
            kind="interface", name=m.group("name"),
            is_exported=bool(m.group("exp")),
            line=_line_number(source, m.start()),
        ))

    # --- TypeScript type aliases ---
    for m in _TYPE_ALIAS_RE.finditer(source):
        elements.append(NodeElement(
            kind="type_alias", name=m.group("name"),
            is_exported=bool(m.group("exp")),
            line=_line_number(source, m.start()),
        ))

    elements.sort(key=lambda e: e.line)
    return elements


def parse_nodejs_file(path: Path) -> List[NodeElement]:
    """Parse a JS/TS source file and return its elements.

    Returns empty list on read/parse error.
    """
    try:
        source = path.read_text(encoding="utf-8")
        return parse_nodejs_source(source)
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Failed to parse Node.js file %s: %s", path, exc)
        return []
