"""Java signature string parser for plan ingestion element extraction (REQ-EE-102).

Parses Java-style API signature strings extracted by LLM during plan ingestion
into ``ForwardElementSpec`` objects consumable by MicroPrime element-level
code generation.
"""

from __future__ import annotations

import re
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Signature

logger = get_logger(__name__)

# Matches: [modifiers] (class|interface|record|enum) Name [extends X] [implements Y, Z]
_CLASS_RE = re.compile(
    r"(?:(?P<mods>(?:(?:public|private|protected|static|abstract|final)\s+)*)"
    r"(?P<kind>class|interface|record|enum)\s+)"
    r"(?P<name>\w+)"
    r"(?:\s*\([^)]*\))?"  # record components e.g. (String url, String text)
    r"(?:\s+extends\s+(?P<extends>[\w.<>,\s]+?))?"
    r"(?:\s+implements\s+(?P<implements>[\w.<>,\s]+?))?"
    r"\s*(?:\{.*)?$"
)

# Matches: [modifiers] [<generics>] returnType methodName(params...)
_METHOD_RE = re.compile(
    r"(?P<mods>(?:(?:public|private|protected|static|abstract|final|synchronized|default|native)\s+)*)"
    r"(?:<.+?>\s+)?"  # generic type params e.g. <T>, <T extends Comparable<T>>
    r"(?P<ret>[\w.<>,\[\]?]+)\s+"
    r"(?P<name>\w+)\s*\("
)

# Matches: ClassName.methodName (dotted name shorthand)
_DOTTED_RE = re.compile(r"^(?P<cls>\w+)\.(?P<method>\w+)$")

_EMPTY_SIG = Signature(params=[], return_annotation=None)

_VISIBILITY_MAP = {
    "public": Visibility.PUBLIC,
    "private": Visibility.PRIVATE,
    "protected": Visibility.PROTECTED,
}


def _parse_modifiers(mods_str: str) -> tuple[Visibility, bool, bool]:
    """Extract visibility, is_static, is_abstract from a modifier string."""
    tokens = mods_str.split()
    visibility = Visibility.PUBLIC  # Java default for API signatures
    is_static = False
    is_abstract = False
    for tok in tokens:
        if tok in _VISIBILITY_MAP:
            visibility = _VISIBILITY_MAP[tok]
        elif tok == "static":
            is_static = True
        elif tok == "abstract":
            is_abstract = True
    return visibility, is_static, is_abstract


def _split_type_list(s: str) -> list[str]:
    """Split a comma-separated type list, respecting generic brackets."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in s:
        if ch in ("<",):
            depth += 1
        elif ch in (">",):
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def parse_java_signatures(
    api_signatures: list[str],
    target_file: str,
) -> list[ForwardElementSpec]:
    """Parse Java-style API signature strings into ForwardElementSpec objects.

    Handles classes, interfaces, records, enums, methods with modifiers,
    and dotted ``ClassName.methodName`` shorthand patterns. Unparseable
    signatures are skipped with a debug log.

    Args:
        api_signatures: Raw signature strings from LLM plan extraction.
        target_file: Target file path (unused but reserved for future use).

    Returns:
        List of parsed ``ForwardElementSpec`` objects.
    """
    results: list[ForwardElementSpec] = []

    for sig in api_signatures:
        sig = sig.strip()
        if not sig:
            continue

        spec = _try_parse(sig)
        if spec is not None:
            results.append(spec)
        else:
            logger.debug("Skipping unparseable Java signature: %s", sig)

    return results


def _try_parse(sig: str) -> Optional[ForwardElementSpec]:
    """Attempt to parse a single signature string."""
    # 1. Dotted name shorthand: ClassName.methodName
    m = _DOTTED_RE.match(sig)
    if m:
        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name=m.group("method"),
            signature=_EMPTY_SIG,
            parent_class=m.group("cls"),
            visibility=Visibility.PUBLIC,
            decomposition_source="parse-llm",
        )

    # 2. Class/interface/record/enum
    m = _CLASS_RE.match(sig)
    if m:
        mods_str = m.group("mods") or ""
        visibility, _, is_abstract = _parse_modifiers(mods_str)
        kind_kw = m.group("kind")

        # interfaces are abstract by nature
        if kind_kw == "interface":
            is_abstract = True

        bases: list[str] = []
        if m.group("extends"):
            bases.extend(_split_type_list(m.group("extends")))
        if m.group("implements"):
            bases.extend(_split_type_list(m.group("implements")))

        return ForwardElementSpec(
            kind=ElementKind.CLASS,
            name=m.group("name"),
            bases=bases,
            visibility=visibility,
            is_abstract=is_abstract,
            decomposition_source="parse-llm",
        )

    # 3. Method signature
    m = _METHOD_RE.match(sig)
    if m:
        mods_str = m.group("mods") or ""
        visibility, is_static, is_abstract = _parse_modifiers(mods_str)

        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name=m.group("name"),
            signature=_EMPTY_SIG,
            visibility=visibility,
            is_static=is_static,
            is_abstract=is_abstract,
            decomposition_source="parse-llm",
        )

    return None
