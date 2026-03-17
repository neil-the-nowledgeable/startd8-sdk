"""Regex-based Go source parser for structure extraction.

Extracts functions, types (struct/interface), methods, constants, and
variables from Go source files. Produces data compatible with
ForwardElementSpec for the ForwardManifest and ElementRegistry.

Go's declaration syntax is regular enough that regex covers ~90% of cases:
- func Name(params) returnType { ... }
- func (recv *Type) Name(params) returnType { ... }
- type Name struct { ... }
- type Name interface { ... }
- type Name = OtherType
- const Name = value / const ( ... )
- var Name Type = value / var ( ... )

Limitations:
- Does not parse function bodies (no call graph extraction)
- Does not resolve type aliases across files
- Multi-line signatures with embedded comments may not parse
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class GoElement:
    """Parsed Go code element."""

    kind: str  # "function", "method", "class", "type_alias", "constant", "variable"
    name: str
    signature: Optional[str] = None  # parameter list for functions/methods
    return_type: Optional[str] = None
    parent_type: Optional[str] = None  # receiver type for methods
    receiver_name: Optional[str] = None  # receiver variable name
    is_pointer_receiver: bool = False
    bases: list = field(default_factory=list)  # embedded types for structs
    is_exported: bool = False  # capitalized name
    is_interface: bool = False  # type X interface vs type X struct
    line_number: int = 0
    doc_comment: Optional[str] = None
    type_annotation: Optional[str] = None  # for consts/vars


# --- Regex patterns ---

# Function: func Name(params) returnType
_FUNC_RE = re.compile(
    r"^func\s+"
    r"(?P<name>[A-Za-z_]\w*)"
    r"\s*\((?P<params>[^)]*)\)"
    r"(?:\s*(?P<return>\S.*))?",
    re.MULTILINE,
)

# Method: func (recv *Type) Name(params) returnType
_METHOD_RE = re.compile(
    r"^func\s+"
    r"\(\s*(?P<recv_name>\w+)\s+(?P<pointer>\*)?\s*(?P<recv_type>[A-Za-z_]\w*)\s*\)"
    r"\s*(?P<name>[A-Za-z_]\w*)"
    r"\s*\((?P<params>[^)]*)\)"
    r"(?:\s*(?P<return>\S.*))?",
    re.MULTILINE,
)

# Type declaration: type Name struct/interface
_TYPE_RE = re.compile(
    r"^type\s+(?P<name>[A-Za-z_]\w*)\s+(?P<kind>struct|interface)\b",
    re.MULTILINE,
)

# Type alias: type Name = OtherType
_TYPE_ALIAS_RE = re.compile(
    r"^type\s+(?P<name>[A-Za-z_]\w*)\s+=\s+(?P<target>\S+)",
    re.MULTILINE,
)

# Simple type definition: type Name OtherType (not struct/interface)
_TYPE_DEF_RE = re.compile(
    r"^type\s+(?P<name>[A-Za-z_]\w*)\s+(?!struct\b|interface\b|=)(?P<target>\S+)",
    re.MULTILINE,
)

# Const/var single-line: const Name = value / var Name Type = value / var Name Type
_CONST_VAR_RE = re.compile(
    r"^(?P<kind>const|var)\s+(?P<name>[A-Za-z_]\w*)\s+"
    r"(?:(?P<type>[^\s=]+)\s*(?:=.*)?|=\s*\S)",
    re.MULTILINE,
)

# Const/var block: const ( ... ) / var ( ... )
_CONST_VAR_BLOCK_RE = re.compile(
    r"^(?P<kind>const|var)\s*\(",
    re.MULTILINE,
)

# Entry within a const/var block:
#   Name Type = value       (const with type)
#   Name = value            (const with inferred type)
#   Name Type               (var with type, no initializer)
#   Name []Type             (var with slice type)
#   Name *Type              (var with pointer type)
_BLOCK_ENTRY_RE = re.compile(
    r"^\s+(?P<name>[A-Za-z_]\w*)"
    r"(?:\s+(?P<type>[^\s=]+))?"
    r"(?:\s*=.*)?$",
    re.MULTILINE,
)

# Struct embedded type (field without name): TypeName or *TypeName
_EMBEDDED_RE = re.compile(
    r"^\s+\*?(?P<type>[A-Z]\w*)\s*$",
    re.MULTILINE,
)

# Doc comment (line immediately before a declaration)
_DOC_COMMENT_RE = re.compile(r"^//\s*(.*)$", re.MULTILINE)

# Import block extraction
_IMPORT_SINGLE_RE = re.compile(
    r'^import\s+"(?P<path>[^"]+)"',
    re.MULTILINE,
)
_IMPORT_BLOCK_RE = re.compile(
    r"^import\s*\((.*?)\)",
    re.MULTILINE | re.DOTALL,
)
_IMPORT_LINE_RE = re.compile(r'^\s*(?:\w+\s+)?"(?P<path>[^"]+)"', re.MULTILINE)


def _is_exported(name: str) -> bool:
    """Go exports names that start with an uppercase letter."""
    return bool(name) and name[0].isupper()


def _get_doc_comment(source: str, pos: int) -> Optional[str]:
    """Extract the doc comment block immediately preceding a declaration."""
    lines = source[:pos].rstrip().splitlines()
    doc_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("//"):
            doc_lines.append(stripped[2:].strip())
        else:
            break
    if doc_lines:
        doc_lines.reverse()
        return "\n".join(doc_lines)
    return None


def _find_struct_body(source: str, start_pos: int) -> str:
    """Extract struct body between { } for embedded type detection."""
    idx = source.find("{", start_pos)
    if idx == -1:
        return ""
    depth = 0
    end = idx
    for i in range(idx, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    return source[idx + 1 : end]


def _line_number(source: str, pos: int) -> int:
    """Return 1-based line number for a position in source."""
    return source[:pos].count("\n") + 1


def parse_go_source(source: str) -> List[GoElement]:
    """Parse Go source code and extract structural elements.

    Args:
        source: Go source file content.

    Returns:
        List of GoElement instances.
    """
    elements: List[GoElement] = []

    # Methods must be matched before functions (methods have a receiver prefix)
    # Track matched positions to avoid double-matching
    matched_positions: set = set()

    # --- Methods ---
    for m in _METHOD_RE.finditer(source):
        matched_positions.add(m.start())
        recv_type = m.group("recv_type")
        ret = (m.group("return") or "").strip().rstrip("{").strip()
        elements.append(GoElement(
            kind="method",
            name=m.group("name"),
            signature=m.group("params").strip(),
            return_type=ret or None,
            parent_type=recv_type,
            receiver_name=m.group("recv_name"),
            is_pointer_receiver=m.group("pointer") is not None,
            is_exported=_is_exported(m.group("name")),
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # --- Functions ---
    for m in _FUNC_RE.finditer(source):
        if m.start() in matched_positions:
            continue
        ret = (m.group("return") or "").strip().rstrip("{").strip()
        elements.append(GoElement(
            kind="function",
            name=m.group("name"),
            signature=m.group("params").strip(),
            return_type=ret or None,
            is_exported=_is_exported(m.group("name")),
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # --- Type declarations (struct/interface) ---
    for m in _TYPE_RE.finditer(source):
        type_kind = m.group("kind")
        is_iface = type_kind == "interface"

        # Extract embedded types from struct body
        bases = []
        if not is_iface:
            body = _find_struct_body(source, m.end())
            for em in _EMBEDDED_RE.finditer(body):
                bases.append(em.group("type"))

        elements.append(GoElement(
            kind="class",  # closest ForwardElementSpec equivalent
            name=m.group("name"),
            bases=bases,
            is_exported=_is_exported(m.group("name")),
            is_interface=is_iface,
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # --- Type aliases ---
    for m in _TYPE_ALIAS_RE.finditer(source):
        elements.append(GoElement(
            kind="type_alias",
            name=m.group("name"),
            type_annotation=m.group("target"),
            is_exported=_is_exported(m.group("name")),
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # --- Simple type definitions (type Name OtherType) ---
    for m in _TYPE_DEF_RE.finditer(source):
        elements.append(GoElement(
            kind="type_alias",
            name=m.group("name"),
            type_annotation=m.group("target"),
            is_exported=_is_exported(m.group("name")),
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # --- Constants and variables ---
    # Single-line
    for m in _CONST_VAR_RE.finditer(source):
        kind = "constant" if m.group("kind") == "const" else "variable"
        elements.append(GoElement(
            kind=kind,
            name=m.group("name"),
            type_annotation=m.group("type"),
            is_exported=_is_exported(m.group("name")),
            line_number=_line_number(source, m.start()),
            doc_comment=_get_doc_comment(source, m.start()),
        ))

    # Block declarations
    for m in _CONST_VAR_BLOCK_RE.finditer(source):
        kind = "constant" if m.group("kind") == "const" else "variable"
        # Find the closing paren
        block_start = m.end()
        paren_depth = 1
        block_end = block_start
        for i in range(block_start, len(source)):
            if source[i] == "(":
                paren_depth += 1
            elif source[i] == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    block_end = i
                    break
        block = source[block_start:block_end]
        for entry in _BLOCK_ENTRY_RE.finditer(block):
            elements.append(GoElement(
                kind=kind,
                name=entry.group("name"),
                type_annotation=entry.group("type"),
                is_exported=_is_exported(entry.group("name")),
                line_number=_line_number(source, block_start + entry.start()),
            ))

    # Sort by line number for stable output
    elements.sort(key=lambda e: e.line_number)
    return elements


def parse_go_imports(source: str) -> List[str]:
    """Extract import paths from Go source.

    Returns:
        List of import path strings (e.g. ['fmt', 'net/http']).
    """
    imports: List[str] = []

    # Single imports
    for m in _IMPORT_SINGLE_RE.finditer(source):
        imports.append(m.group("path"))

    # Block imports
    for m in _IMPORT_BLOCK_RE.finditer(source):
        block = m.group(1)
        for line_m in _IMPORT_LINE_RE.finditer(block):
            imports.append(line_m.group("path"))

    return imports


def parse_go_file(path: Path) -> List[GoElement]:
    """Parse a Go source file and return its elements.

    Args:
        path: Path to the .go file.

    Returns:
        List of GoElement instances. Empty list on read/parse error.
    """
    try:
        source = path.read_text(encoding="utf-8")
        return parse_go_source(source)
    except (OSError, UnicodeDecodeError):
        return []
