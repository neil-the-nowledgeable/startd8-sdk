"""javalang-based Java source parser for structure extraction.

Extracts classes, interfaces, enums, methods, fields, constructors,
and annotations from Java source files.  Produces data compatible with
ForwardElementSpec for the ForwardManifest and ElementRegistry.

Uses ``javalang`` for AST parsing when available; falls back to regex-based
extraction (covers ~80% of common patterns) when javalang is not installed.

Limitations:
- Does not parse method bodies (no call graph extraction)
- Does not resolve type aliases across files
- Annotation processors / code-gen artifacts may not parse cleanly
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class JavaElement:
    """Parsed Java code element."""

    kind: str  # "class", "interface", "enum", "method", "constructor", "field", "constant"
    name: str
    modifiers: list[str] = field(default_factory=list)
    line_number: int = 0
    end_line: int = 0
    parent: Optional[str] = None  # enclosing class name
    signature: Optional[str] = None  # parameter list for methods/constructors
    return_type: Optional[str] = None
    annotations: list[str] = field(default_factory=list)
    extends: Optional[str] = None
    implements: list[str] = field(default_factory=list)


# ── Regex patterns (fallback) ──────────────────────────────────────────

# Package declaration
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)

# Import statement
_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:static\s+)?([\w.*]+)\s*;", re.MULTILINE,
)

# Type declaration (class, interface, enum, record, @interface)
_TYPE_DECL_RE = re.compile(
    r"^(?P<annotations>(?:\s*@\w+(?:\([^)]*\))?\s*)*)"
    r"\s*(?P<modifiers>(?:(?:public|private|protected|abstract|static|final|sealed|non-sealed|strictfp)\s+)*)"
    r"(?P<kind>class|interface|enum|record|@interface)\s+"
    r"(?P<name>\w+)"
    r"(?:<[^>]+>)?"  # generics
    r"(?:\s+extends\s+(?P<extends>[\w.<>,\s]+?))?"
    r"(?:\s+implements\s+(?P<implements>[\w.<>,\s]+?))?"
    r"\s*\{",
    re.MULTILINE,
)

# Method/constructor declaration
_METHOD_RE = re.compile(
    r"^(?P<annotations>(?:\s*@\w+(?:\([^)]*\))?\s*\n)*)"
    r"\s*(?P<modifiers>(?:(?:public|private|protected|abstract|static|final|default|synchronized|native)\s+)*)"
    r"(?:(?P<generics><[^>]+>\s+))?"
    r"(?P<return_type>[\w.<>,\[\]\s?]+?)\s+"
    r"(?P<name>\w+)\s*"
    r"\((?P<params>[^)]*)\)",
    re.MULTILINE,
)

# Constructor (no return type, name matches class)
_CONSTRUCTOR_RE = re.compile(
    r"^\s*(?P<modifiers>(?:(?:public|private|protected)\s+)?)"
    r"(?P<name>[A-Z]\w*)\s*"
    r"\((?P<params>[^)]*)\)\s*(?:throws\s+[\w.,\s]+)?\s*\{",
    re.MULTILINE,
)

# Field declaration
_FIELD_RE = re.compile(
    r"^\s*(?P<modifiers>(?:(?:public|private|protected|static|final|volatile|transient)\s+)*)"
    r"(?P<type>[\w.<>,\[\]?]+)\s+"
    r"(?P<name>\w+)\s*(?:=|;)",
    re.MULTILINE,
)


def _line_number(source: str, pos: int) -> int:
    """Return 1-based line number for a position in source."""
    return source[:pos].count("\n") + 1


def _parse_modifiers(mod_str: str) -> list[str]:
    """Parse a space-separated modifier string into a list."""
    return [m for m in mod_str.split() if m]


def _parse_annotations(ann_str: str) -> list[str]:
    """Extract annotation names from an annotation block string."""
    return re.findall(r"@(\w+)", ann_str)


def _split_type_list(type_str: str) -> list[str]:
    """Split a comma-separated type list (e.g. implements A, B<C>)."""
    if not type_str:
        return []
    # Simple split that respects generics nesting
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in type_str:
        if ch == "<":
            depth += 1
            current.append(ch)
        elif ch == ">":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def parse_java_source(source: str) -> list[JavaElement]:
    """Parse Java source code and extract structural elements.

    Tries javalang AST first; falls back to regex extraction.
    """
    try:
        return _parse_with_javalang(source)
    except ImportError:
        pass
    except (ValueError, TypeError, AttributeError, IndexError) as exc:
        # javalang raises these on malformed/unsupported Java syntax
        logger.debug("javalang parse failed, falling back to regex: %s", exc)
    return _parse_with_regex(source)


def _parse_with_javalang(source: str) -> list[JavaElement]:
    """Parse using javalang AST."""
    import javalang

    tree = javalang.parse.parse(source)
    elements: list[JavaElement] = []

    for path, node in tree.filter(javalang.tree.TypeDeclaration):
        kind = "class"
        if isinstance(node, javalang.tree.InterfaceDeclaration):
            kind = "interface"
        elif isinstance(node, javalang.tree.EnumDeclaration):
            kind = "enum"
        elif hasattr(javalang.tree, "RecordDeclaration") and isinstance(
            node, javalang.tree.RecordDeclaration
        ):
            kind = "record"

        modifiers = sorted(node.modifiers or set())
        annotations = [a.name for a in (node.annotations or [])]
        extends = None
        implements_list: list[str] = []

        if hasattr(node, "extends") and node.extends:
            if isinstance(node.extends, list):
                extends = ", ".join(e.name for e in node.extends)
            else:
                extends = node.extends.name
        if hasattr(node, "implements") and node.implements:
            implements_list = [i.name for i in node.implements]

        parent = None
        for p in path:
            if isinstance(p, javalang.tree.TypeDeclaration) and hasattr(p, "name"):
                parent = p.name

        line = getattr(node, "position", None)
        line_no = line.line if line else 0

        elements.append(JavaElement(
            kind=kind,
            name=node.name,
            modifiers=modifiers,
            line_number=line_no,
            parent=parent,
            annotations=annotations,
            extends=extends,
            implements=implements_list,
        ))

        # Extract methods
        for method in (node.methods or []):
            m_line = getattr(method, "position", None)
            m_line_no = m_line.line if m_line else 0
            m_modifiers = sorted(method.modifiers or set())
            m_annotations = [a.name for a in (method.annotations or [])]
            params_str = ", ".join(
                f"{getattr(p.type, 'name', 'Object')} {p.name}"
                for p in (method.parameters or [])
            ) if method.parameters else ""
            ret_type = getattr(method.return_type, "name", "void") if method.return_type else "void"

            elements.append(JavaElement(
                kind="method",
                name=method.name,
                modifiers=m_modifiers,
                line_number=m_line_no,
                parent=node.name,
                signature=params_str,
                return_type=ret_type,
                annotations=m_annotations,
            ))

        # Extract constructors
        for ctor in (node.constructors or []):
            c_line = getattr(ctor, "position", None)
            c_line_no = c_line.line if c_line else 0
            c_modifiers = sorted(ctor.modifiers or set())
            c_annotations = [a.name for a in (ctor.annotations or [])]
            params_str = ", ".join(
                f"{getattr(p.type, 'name', 'Object')} {p.name}"
                for p in (ctor.parameters or [])
            ) if ctor.parameters else ""

            elements.append(JavaElement(
                kind="constructor",
                name=node.name,
                modifiers=c_modifiers,
                line_number=c_line_no,
                parent=node.name,
                signature=params_str,
                annotations=c_annotations,
            ))

        # Extract fields
        for field_decl in (node.fields or []):
            for declarator in field_decl.declarators:
                f_line = getattr(field_decl, "position", None)
                f_line_no = f_line.line if f_line else 0
                f_modifiers = sorted(field_decl.modifiers or set())
                f_annotations = [a.name for a in (field_decl.annotations or [])]
                f_type = getattr(field_decl.type, "name", "Object") if field_decl.type else ""

                elem_kind = "constant" if "final" in f_modifiers and "static" in f_modifiers else "field"
                elements.append(JavaElement(
                    kind=elem_kind,
                    name=declarator.name,
                    modifiers=f_modifiers,
                    line_number=f_line_no,
                    parent=node.name,
                    return_type=f_type,
                    annotations=f_annotations,
                ))

    elements.sort(key=lambda e: e.line_number)
    return elements


def _parse_with_regex(source: str) -> list[JavaElement]:
    """Fallback regex-based extraction."""
    elements: list[JavaElement] = []

    # Type declarations
    for m in _TYPE_DECL_RE.finditer(source):
        kind_str = m.group("kind")
        kind = kind_str if kind_str != "@interface" else "interface"
        modifiers = _parse_modifiers(m.group("modifiers"))
        annotations = _parse_annotations(m.group("annotations") or "")
        extends_str = (m.group("extends") or "").strip() or None
        implements_list = _split_type_list(m.group("implements") or "")

        elements.append(JavaElement(
            kind=kind,
            name=m.group("name"),
            modifiers=modifiers,
            line_number=_line_number(source, m.start()),
            annotations=annotations,
            extends=extends_str,
            implements=implements_list,
        ))

    # Methods (regex, simplified)
    for m in _METHOD_RE.finditer(source):
        name = m.group("name")
        # Skip if name matches a type declaration keyword
        if name in ("class", "interface", "enum", "record", "if", "for", "while", "switch"):
            continue
        modifiers = _parse_modifiers(m.group("modifiers"))
        annotations = _parse_annotations(m.group("annotations") or "")
        return_type = m.group("return_type").strip()

        elements.append(JavaElement(
            kind="method",
            name=name,
            modifiers=modifiers,
            line_number=_line_number(source, m.start()),
            signature=m.group("params").strip(),
            return_type=return_type,
            annotations=annotations,
        ))

    elements.sort(key=lambda e: e.line_number)
    return elements


def parse_java_imports(source: str) -> list[str]:
    """Extract import paths from Java source.

    Returns list of import strings (e.g. ['java.util.List', 'java.io.*']).
    """
    return [m.group(1) for m in _IMPORT_RE.finditer(source)]


def parse_java_package(source: str) -> Optional[str]:
    """Extract the package declaration from Java source."""
    m = _PACKAGE_RE.search(source)
    return m.group(1) if m else None


def find_element(
    source: str, name: str, kind: Optional[str] = None,
) -> Optional[JavaElement]:
    """Find an element by name and optional kind in parsed source."""
    elements = parse_java_source(source)
    for elem in elements:
        if elem.name == name:
            if kind is None or elem.kind == kind:
                return elem
    return None


def parse_java_file(path: Path) -> list[JavaElement]:
    """Parse a Java source file and return its elements.

    Returns empty list on read/parse error.
    """
    try:
        source = path.read_text(encoding="utf-8")
        return parse_java_source(source)
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Failed to parse Java file %s: %s", path, exc)
        return []
