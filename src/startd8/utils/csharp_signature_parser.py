"""C# signature string parser for plan ingestion element extraction (REQ-EE-104).

Parses C# API signature strings extracted by LLM during the PARSE phase
into ``ForwardElementSpec`` objects for MicroPrime element-level generation.
"""

from __future__ import annotations

import re
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature

logger = get_logger(__name__)

# Modifiers that appear before the return type / keyword
_MODIFIER_RE = re.compile(
    r"\b(public|private|protected|internal|static|abstract|virtual|override|async|sealed|readonly|new)\b"
)

# Type declaration: class / interface / record / struct / enum
_TYPE_DECL_RE = re.compile(
    r"(?:^|\s)(class|interface|record|struct|enum)\s+"
    r"(\w+)"                        # name
    r"(?:<[^>]+>)?"                 # optional generic params
    r"(?:\s*\([^)]*\))?"           # optional record primary ctor
    r"(?:\s+where\s+.*)?"          # optional generic constraints
    r"(?:\s*:\s*(.+?))?"           # optional base list
    r"(?:\s*\{.*)?$",              # optional body start
    re.DOTALL,
)

# Method: return_type Name(params...)
_METHOD_RE = re.compile(
    r"(\S+)\s+"                    # return type (last token before name)
    r"(\w+)\s*"                    # method name
    r"\(([^)]*)\)",                # parameter list
)

# Dotted name: ClassName.MethodName (no modifiers, no parens)
_DOTTED_RE = re.compile(r"^(\w+)\.(\w+)$")


def _extract_modifiers(sig: str) -> set[str]:
    """Return the set of C# modifier keywords present in *sig*."""
    return set(_MODIFIER_RE.findall(sig))


def _resolve_visibility(modifiers: set[str]) -> Visibility:
    if "private" in modifiers:
        return Visibility.PRIVATE
    if "protected" in modifiers:
        return Visibility.PROTECTED
    # public and internal both map to PUBLIC for generation purposes
    return Visibility.PUBLIC


def _parse_bases(raw: Optional[str]) -> list[str]:
    """Parse a comma-separated inheritance list, stripping whitespace."""
    if not raw:
        return []
    # Stop at '{' if present
    raw = raw.split("{")[0]
    return [b.strip() for b in raw.split(",") if b.strip()]


def _empty_signature() -> Signature:
    """Return a minimal Signature with no params (placeholder for methods)."""
    return Signature(params=[], return_annotation=None)


def parse_csharp_signatures(
    api_signatures: list[str],
    target_file: str,
) -> list[ForwardElementSpec]:
    """Parse C# API signature strings into ``ForwardElementSpec`` objects.

    Args:
        api_signatures: Raw signature strings extracted by the LLM.
        target_file: Target file path for the generated elements.

    Returns:
        List of parsed ``ForwardElementSpec`` objects.  Unparseable
        signatures are silently skipped with a debug log.
    """
    results: list[ForwardElementSpec] = []

    for sig in api_signatures:
        sig = sig.strip()
        if not sig:
            continue

        spec = _parse_one(sig)
        if spec is not None:
            results.append(spec)
        else:
            logger.debug("Skipping unparseable C# signature: %s", sig)

    return results


def _parse_one(sig: str) -> Optional[ForwardElementSpec]:
    """Attempt to parse a single C# signature string."""
    modifiers = _extract_modifiers(sig)
    vis = _resolve_visibility(modifiers)
    is_static = "static" in modifiers
    is_abstract = "abstract" in modifiers

    # --- Dotted name shorthand: ClassName.MethodName ---
    m = _DOTTED_RE.match(sig.strip())
    if m:
        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name=m.group(2),
            parent_class=m.group(1),
            signature=_empty_signature(),
            visibility=vis,
            is_static=is_static,
            is_abstract=is_abstract,
            decomposition_source="parse-llm",
        )

    # --- Type declaration (class / interface / record / struct / enum) ---
    m = _TYPE_DECL_RE.search(sig)
    if m:
        keyword = m.group(1)
        name = m.group(2)
        bases = _parse_bases(m.group(3))
        if keyword == "interface":
            is_abstract = True
        return ForwardElementSpec(
            kind=ElementKind.CLASS,
            name=name,
            bases=bases,
            visibility=vis,
            is_static=is_static,
            is_abstract=is_abstract,
            decomposition_source="parse-llm",
        )

    # --- Method declaration ---
    m = _METHOD_RE.search(sig)
    if m:
        name = m.group(2)
        return_type = m.group(1)
        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name=name,
            signature=Signature(params=[], return_annotation=return_type),
            visibility=vis,
            is_static=is_static,
            is_abstract=is_abstract,
            decomposition_source="parse-llm",
        )

    # --- Skip field declarations (no parens, no type keyword) ---
    return None
