"""Go signature string parser for plan ingestion element extraction (REQ-EE-101).

Parses Go function, method, and type declaration strings extracted by the LLM
during plan ingestion into ``ForwardElementSpec`` objects that MicroPrime can
consume for element-level code generation.
"""

from __future__ import annotations

import re
from typing import Optional

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind, Param, Signature

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# func (recv *Type) Name(...) ... — method with receiver
_METHOD_RE = re.compile(
    r"^func\s+\(\s*\w+\s+\*?(\w+)\s*\)\s+(\w+)"
)

# func Name[T ...](...) ... or func Name(...) ... — standalone function
_FUNC_RE = re.compile(
    r"^func\s+(\w+)"
)

# type Name struct / type Name interface
_TYPE_RE = re.compile(
    r"^type\s+(\w+)\s+(struct|interface)"
)

# Minimal empty signature for callable specs (no typed params needed).
_EMPTY_SIGNATURE = Signature(params=[], return_annotation=None)


def _go_visibility(name: str) -> Visibility:
    """Return PUBLIC for uppercase-initial names, PRIVATE otherwise (Go convention)."""
    if name and name[0].isupper():
        return Visibility.PUBLIC
    return Visibility.PRIVATE


def parse_go_signatures(
    api_signatures: list[str],
    target_file: str,
) -> list[ForwardElementSpec]:
    """Parse Go signature strings into ``ForwardElementSpec`` objects.

    Handles ``func``, method-with-receiver, ``type ... struct``, and
    ``type ... interface`` declarations.  Unparseable signatures are
    silently skipped with a debug log.

    Args:
        api_signatures: Raw Go signature strings (e.g. from LLM extraction).
        target_file: Target file path for context (unused by parser itself,
            reserved for future per-file scoping).

    Returns:
        List of parsed ``ForwardElementSpec`` objects.
    """
    results: list[ForwardElementSpec] = []

    for sig in api_signatures:
        sig_stripped = sig.strip()
        if not sig_stripped:
            continue

        spec = _parse_one(sig_stripped)
        if spec is None:
            logger.debug("Skipping unparseable Go signature: %s", sig_stripped)
            continue
        results.append(spec)

    return results


def _parse_one(sig: str) -> Optional[ForwardElementSpec]:
    """Attempt to parse a single Go signature string."""

    # 1. type declarations: type Name struct / type Name interface
    m = _TYPE_RE.match(sig)
    if m:
        name = m.group(1)
        type_keyword = m.group(2)
        return ForwardElementSpec(
            kind=ElementKind.CLASS,
            name=name,
            visibility=_go_visibility(name),
            is_abstract=(type_keyword == "interface"),
            decomposition_source="parse-llm",
        )

    # 2. method with receiver: func (s *ShippingService) Name(...)
    m = _METHOD_RE.match(sig)
    if m:
        receiver_type = m.group(1)
        name = m.group(2)
        return ForwardElementSpec(
            kind=ElementKind.METHOD,
            name=name,
            parent_class=receiver_type,
            signature=_EMPTY_SIGNATURE,
            visibility=_go_visibility(name),
            decomposition_source="parse-llm",
        )

    # 3. standalone function: func Name(...)
    m = _FUNC_RE.match(sig)
    if m:
        name = m.group(1)
        return ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name=name,
            signature=_EMPTY_SIGNATURE,
            visibility=_go_visibility(name),
            decomposition_source="parse-llm",
        )

    return None


__all__ = ["parse_go_signatures"]
