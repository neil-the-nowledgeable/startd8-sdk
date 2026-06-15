"""C# structure extraction via tree-sitter-c-sharp.

Provides in-process CST parsing for C# source files without requiring
the .NET SDK.  Falls back to regex-based extraction when tree-sitter
is not installed.

Install:  pip install tree-sitter tree-sitter-c-sharp
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Data classes for extracted structure
# ---------------------------------------------------------------------------

@dataclass
class CSharpElement:
    """A structural element extracted from C# source."""

    kind: str  # "class", "interface", "struct", "record", "enum", "method", "constructor", "property"
    name: str
    start_byte: int
    end_byte: int
    start_line: int  # 0-based
    end_line: int  # 0-based
    body_start_byte: Optional[int] = None
    body_end_byte: Optional[int] = None
    modifiers: List[str] = field(default_factory=list)
    return_type: Optional[str] = None
    parameters: Optional[str] = None  # raw parameter text
    parent: Optional[str] = None  # enclosing class/struct name


@dataclass
class CSharpParseResult:
    """Result of parsing a C# source file."""

    has_error: bool
    elements: List[CSharpElement]
    usings: List[str]  # e.g. ["System", "Grpc.Core"]
    namespace: Optional[str] = None
    parser_used: str = "none"  # "tree_sitter" or "regex"


# ---------------------------------------------------------------------------
# tree-sitter implementation
# ---------------------------------------------------------------------------

# Node types for type declarations
_TYPE_NODE_TYPES = frozenset({
    "class_declaration",
    "interface_declaration",
    "struct_declaration",
    "record_declaration",
    "enum_declaration",
})

# Node types for members inside a type body
_MEMBER_NODE_TYPES = frozenset({
    "method_declaration",
    "constructor_declaration",
    "property_declaration",
})

_NODE_KIND_MAP = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "struct_declaration": "struct",
    "record_declaration": "record",
    "enum_declaration": "enum",
    "method_declaration": "method",
    "constructor_declaration": "constructor",
    "property_declaration": "property",
}


_UNSET = object()  # sentinel for uninitialized cache
_ts_parser_cache: Any = _UNSET


def _get_ts_parser() -> Any:
    """Create and cache a tree-sitter parser for C#.

    Returns the cached ``Parser`` instance, or ``None`` if tree-sitter
    or tree-sitter-c-sharp is not installed.
    """
    global _ts_parser_cache
    if _ts_parser_cache is not _UNSET:
        return _ts_parser_cache

    try:
        import tree_sitter_c_sharp as ts_cs
        from tree_sitter import Language, Parser

        language = Language(ts_cs.language())
        parser = Parser(language)
        _ts_parser_cache = parser
        return parser
    except ImportError:
        _ts_parser_cache = None
        return None
    except Exception as exc:
        # Any init failure — corrupt shared library, or (commonly) a tree-sitter ABI/grammar
        # version mismatch between the installed `tree_sitter` binding and `tree_sitter_c_sharp`
        # grammar. Observed in the wild as ValueError("Incompatible Language version 15. Must be
        # between 13 and 14") and TypeError("an integer is required"). These MUST NOT crash the
        # caller: validate_csharp_syntax / the C# parser fall back to the regex/brace path when
        # this returns None. (Previously only OSError/RuntimeError were caught, so a version
        # mismatch escaped and aborted the whole prime/benchmark run.)
        import logging
        logging.getLogger(__name__).warning(
            "tree-sitter-c-sharp init failed (%s: %s) — falling back to regex parser",
            type(exc).__name__, exc,
        )
        _ts_parser_cache = None
        return None


def _extract_modifiers(node: Any) -> List[str]:
    """Extract modifier keywords (public, private, static, async, etc.).

    Args:
        node: A tree-sitter ``Node`` (declaration node with modifier children).
    """
    mods = []
    for child in node.children:
        if child.type == "modifier":
            mods.append(child.text.decode("utf-8"))
        elif child.type in (
            "abstract", "async", "const", "extern", "internal",
            "new", "override", "partial", "private", "protected",
            "public", "readonly", "sealed", "static", "unsafe",
            "virtual", "volatile",
        ):
            mods.append(child.type)
    return mods


def _node_name(node: Any) -> str:
    """Get the name of a declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node.text.decode("utf-8")
    return ""


def _node_return_type(node: Any) -> Optional[str]:
    """Get the return type of a method declaration."""
    ret = node.child_by_field_name("returns")
    if ret is None:
        ret = node.child_by_field_name("type")
    if ret is not None:
        return ret.text.decode("utf-8")
    return None


def _node_parameters(node: Any) -> Optional[str]:
    """Get the raw parameter list text."""
    params = node.child_by_field_name("parameters")
    if params is not None:
        return params.text.decode("utf-8")
    return None


def _extract_body_range(node: Any) -> tuple[Optional[int], Optional[int]]:
    """Get the body byte range of a declaration, if it has one."""
    body = node.child_by_field_name("body")
    if body is not None:
        return body.start_byte, body.end_byte
    # Properties use "accessors" instead of "body"
    for child in node.children:
        if child.type == "accessor_list":
            return child.start_byte, child.end_byte
    return None, None


def _parse_with_tree_sitter(source: str) -> Optional[CSharpParseResult]:
    """Parse C# source using tree-sitter. Returns None if unavailable."""
    parser = _get_ts_parser()
    if parser is None:
        return None

    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    elements: List[CSharpElement] = []
    usings: List[str] = []
    namespace: Optional[str] = None

    def _walk(node, parent_name: Optional[str] = None):
        nonlocal namespace

        if node.type == "using_directive":
            # Extract the namespace from the using directive.
            # tree-sitter-c-sharp represents the namespace as a direct child
            # (identifier or qualified_name), not via a named field.
            for child in node.children:
                if child.type in ("identifier", "qualified_name", "name"):
                    usings.append(child.text.decode("utf-8"))
                    break
            return

        if node.type == "file_scoped_namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                namespace = name_node.text.decode("utf-8")
            for child in node.children:
                _walk(child, parent_name)
            return

        if node.type == "namespace_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                namespace = name_node.text.decode("utf-8")
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, parent_name)
            return

        if node.type in _TYPE_NODE_TYPES:
            name = _node_name(node)
            body_start, body_end = _extract_body_range(node)
            elem = CSharpElement(
                kind=_NODE_KIND_MAP[node.type],
                name=name,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                body_start_byte=body_start,
                body_end_byte=body_end,
                modifiers=_extract_modifiers(node),
                parent=parent_name,
            )
            elements.append(elem)
            # Recurse into body for members
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    _walk(child, name)
            return

        if node.type in _MEMBER_NODE_TYPES and parent_name:
            name = _node_name(node)
            body_start, body_end = _extract_body_range(node)
            elem = CSharpElement(
                kind=_NODE_KIND_MAP[node.type],
                name=name,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                body_start_byte=body_start,
                body_end_byte=body_end,
                modifiers=_extract_modifiers(node),
                return_type=_node_return_type(node),
                parameters=_node_parameters(node),
                parent=parent_name,
            )
            elements.append(elem)
            return

        # Recurse into other nodes
        for child in node.children:
            _walk(child, parent_name)

    _walk(root)

    return CSharpParseResult(
        has_error=root.has_error,
        elements=elements,
        usings=usings,
        namespace=namespace,
        parser_used="tree_sitter",
    )


# ---------------------------------------------------------------------------
# Regex fallback
# ---------------------------------------------------------------------------

_USING_RE = re.compile(r"^\s*using\s+([\w.]+)\s*;", re.MULTILINE)
_NAMESPACE_RE = re.compile(
    r"^\s*namespace\s+([\w.]+)", re.MULTILINE,
)
_TYPE_DECL_RE = re.compile(
    r"^\s*(?P<mods>(?:(?:public|private|protected|internal|static|abstract|sealed|partial|readonly)\s+)*)"
    r"(?P<kind>class|interface|struct|record|enum)\s+(?P<name>[A-Za-z_]\w*)",
    re.MULTILINE,
)
_METHOD_DECL_RE = re.compile(
    r"^\s*(?P<mods>(?:(?:public|private|protected|internal|static|async|override|virtual|abstract|sealed|new|extern)\s+)*)"
    r"(?P<ret>[\w<>\[\],?\s]+?)\s+(?P<name>[A-Za-z_]\w*)\s*\(",
    re.MULTILINE,
)
_PROPERTY_DECL_RE = re.compile(
    r"^\s*(?P<mods>(?:(?:public|private|protected|internal|static|virtual|override|abstract|sealed|new)\s+)*)"
    r"(?P<type>[\w<>\[\]?]+)\s+(?P<name>[A-Za-z_]\w*)\s*\{[^}]*(?:get|set)",
    re.MULTILINE,
)

# C# keywords that should NOT be treated as method names
_CS_NON_METHOD_KEYWORDS = frozenset({
    "if", "else", "for", "foreach", "while", "do", "switch", "case",
    "try", "catch", "finally", "lock", "using", "return", "throw",
    "new", "class", "struct", "interface", "enum", "record",
    "namespace", "void", "get", "set", "value",
})


def _extract_mods_from_text(mods_text: str) -> List[str]:
    """Extract modifier words from a regex capture group."""
    return [m for m in mods_text.split() if m]


def _find_parent_class_at(source: str, offset: int, type_elements: List[CSharpElement]) -> Optional[str]:
    """Determine which type declaration encloses the given offset using brace depth.

    Walks *source* from each type declaration's start, tracking ``{`` / ``}``
    depth.  If *offset* falls inside the braces of a type, that type is the
    enclosing parent.
    """
    best: Optional[str] = None
    best_start = -1

    for te in type_elements:
        if te.start_byte > offset:
            continue
        # Walk from the type start and find its opening brace
        depth = 0
        in_body = False
        pos = te.start_byte
        body_end = len(source)
        while pos < len(source):
            ch = source[pos]
            if ch == '{':
                depth += 1
                if not in_body:
                    in_body = True
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    body_end = pos
                    break
            pos += 1

        if in_body and te.start_byte < offset <= body_end:
            # Prefer the innermost (closest start_byte)
            if te.start_byte > best_start:
                best = te.name
                best_start = te.start_byte

    return best


def _parse_with_regex(source: str) -> CSharpParseResult:
    """Fallback regex-based C# structure extraction.

    Extracts type declarations (class, interface, struct, record, enum),
    method declarations, and property declarations.  Uses brace-depth
    tracking to assign ``parent`` for members inside a type body.
    """
    usings = _USING_RE.findall(source)
    ns_match = _NAMESPACE_RE.search(source)
    namespace = ns_match.group(1) if ns_match else None

    elements: List[CSharpElement] = []

    # Pass 1: type declarations
    for m in _TYPE_DECL_RE.finditer(source):
        line_num = source[:m.start()].count("\n")
        mods = _extract_mods_from_text(m.group("mods"))
        elements.append(CSharpElement(
            kind=m.group("kind"),
            name=m.group("name"),
            start_byte=m.start(),
            end_byte=m.end(),
            start_line=line_num,
            end_line=line_num,
            modifiers=mods,
        ))

    type_elements = list(elements)  # snapshot for parent lookup

    # Pass 2: method declarations
    for m in _METHOD_DECL_RE.finditer(source):
        name = m.group("name")
        if name in _CS_NON_METHOD_KEYWORDS:
            continue
        ret = m.group("ret").strip()
        # Skip if ret is a type keyword (these are type decls, not methods)
        if ret in ("class", "interface", "struct", "record", "enum", "namespace"):
            continue
        line_num = source[:m.start()].count("\n")
        mods = _extract_mods_from_text(m.group("mods"))
        parent = _find_parent_class_at(source, m.start(), type_elements)
        elements.append(CSharpElement(
            kind="method",
            name=name,
            start_byte=m.start(),
            end_byte=m.end(),
            start_line=line_num,
            end_line=line_num,
            modifiers=mods,
            return_type=ret,
            parent=parent,
        ))

    # Pass 3: property declarations
    for m in _PROPERTY_DECL_RE.finditer(source):
        name = m.group("name")
        line_num = source[:m.start()].count("\n")
        mods = _extract_mods_from_text(m.group("mods"))
        parent = _find_parent_class_at(source, m.start(), type_elements)
        elements.append(CSharpElement(
            kind="property",
            name=name,
            start_byte=m.start(),
            end_byte=m.end(),
            start_line=line_num,
            end_line=line_num,
            modifiers=mods,
            return_type=m.group("type").strip(),
            parent=parent,
        ))

    # Sort by source position for stable ordering
    elements.sort(key=lambda e: e.start_byte)

    return CSharpParseResult(
        has_error=False,  # regex can't detect errors
        elements=elements,
        usings=usings,
        namespace=namespace,
        parser_used="regex",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_csharp(source: str) -> CSharpParseResult:
    """Parse C# source code, returning structural elements.

    Uses tree-sitter-c-sharp if available, falls back to regex.
    """
    result = _parse_with_tree_sitter(source)
    if result is not None:
        return result
    return _parse_with_regex(source)


def validate_csharp_syntax(source: str) -> tuple[bool, str]:
    """Validate C# syntax via tree-sitter (with text-based fallback).

    Returns ``(True, "")`` on success or ``(False, error_message)`` on failure.
    """
    from ._validation_utils import check_balanced_braces

    # Python fingerprint check (fast, catches cross-language contamination)
    from ._validation_utils import PYTHON_FINGERPRINTS
    for fp in PYTHON_FINGERPRINTS:
        if fp in source:
            return False, f"Python fingerprint detected: {fp!r}"

    if not source.strip():
        return False, "empty file"

    # Try tree-sitter first
    result = _parse_with_tree_sitter(source)
    if result is not None:
        if result.has_error:
            return False, "tree-sitter parse error (syntax invalid)"
        return True, ""

    # Text-based fallback
    ok, msg = check_balanced_braces(source)
    if not ok:
        return False, msg

    # Must contain at least one C# keyword
    _CS_KEYWORDS = {
        "using", "namespace", "class", "interface", "struct",
        "public", "private", "void", "async", "Task",
    }
    words = set(re.findall(r"\b\w+\b", source))
    if not words & _CS_KEYWORDS:
        return False, "no C# keywords detected"

    return True, ""


def parse_csharp_source(source: str) -> List[CSharpElement]:
    """Extract structural elements from C# source code.

    Convenience wrapper around :func:`parse_csharp` that returns just the
    element list (REQ-PLI-CS-202).  Uses tree-sitter-c-sharp when available,
    falls back to regex.
    """
    result = parse_csharp(source)
    return result.elements


def is_tree_sitter_available() -> bool:
    """Check if tree-sitter-c-sharp is importable."""
    return _get_ts_parser() is not None
