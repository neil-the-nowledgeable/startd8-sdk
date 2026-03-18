"""C# structure extraction via tree-sitter-c-sharp.

Provides in-process CST parsing for C# source files without requiring
the .NET SDK.  Falls back to regex-based extraction when tree-sitter
is not installed.

Install:  pip install tree-sitter tree-sitter-c-sharp
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


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


def _get_ts_parser():
    """Create and cache a tree-sitter parser for C#.

    Returns None if tree-sitter or tree-sitter-c-sharp is not installed.
    """
    global _ts_parser_cache
    try:
        return _ts_parser_cache
    except NameError:
        pass

    try:
        import tree_sitter_c_sharp as ts_cs
        from tree_sitter import Language, Parser

        language = Language(ts_cs.language())
        parser = Parser(language)
        _ts_parser_cache = parser
        return parser
    except (ImportError, Exception):
        _ts_parser_cache = None
        return None


def _extract_modifiers(node) -> List[str]:
    """Extract modifier keywords (public, private, static, async, etc.)."""
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


def _node_name(node) -> str:
    """Get the name of a declaration node."""
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return name_node.text.decode("utf-8")
    return ""


def _node_return_type(node) -> Optional[str]:
    """Get the return type of a method declaration."""
    ret = node.child_by_field_name("returns")
    if ret is None:
        ret = node.child_by_field_name("type")
    if ret is not None:
        return ret.text.decode("utf-8")
    return None


def _node_parameters(node) -> Optional[str]:
    """Get the raw parameter list text."""
    params = node.child_by_field_name("parameters")
    if params is not None:
        return params.text.decode("utf-8")
    return None


def _extract_body_range(node):
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
    r"^\s*(?:public|private|protected|internal|static|abstract|sealed|partial|readonly\s+)*"
    r"\s*(?P<kind>class|interface|struct|record|enum)\s+(?P<name>[A-Za-z_]\w*)",
    re.MULTILINE,
)
_METHOD_DECL_RE = re.compile(
    r"^\s*(?:public|private|protected|internal|static|abstract|virtual|override|async|sealed\s+)*"
    r"\s*(?P<ret>[\w<>\[\],\s?]+?)\s+(?P<name>[A-Za-z_]\w*)\s*\(",
    re.MULTILINE,
)


def _parse_with_regex(source: str) -> CSharpParseResult:
    """Fallback regex-based C# structure extraction."""
    usings = _USING_RE.findall(source)
    ns_match = _NAMESPACE_RE.search(source)
    namespace = ns_match.group(1) if ns_match else None

    elements: List[CSharpElement] = []
    lines = source.split("\n")

    for m in _TYPE_DECL_RE.finditer(source):
        line_num = source[:m.start()].count("\n")
        elements.append(CSharpElement(
            kind=m.group("kind"),
            name=m.group("name"),
            start_byte=m.start(),
            end_byte=m.end(),
            start_line=line_num,
            end_line=line_num,
        ))

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
    _PYTHON_FINGERPRINTS = (
        "def ", "import os", "from __future__", "print(", "self.",
        "#!/usr/bin/env python", "#!/usr/bin/python",
    )
    for fp in _PYTHON_FINGERPRINTS:
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


def is_tree_sitter_available() -> bool:
    """Check if tree-sitter-c-sharp is importable."""
    return _get_ts_parser() is not None
