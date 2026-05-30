"""Multi-language element-manifest adapter (MULTILANG_MANIFEST_VALIDATION).

Bridges the per-language parsers (``parse_csharp_source`` / ``parse_go_source`` /
``parse_java_source`` / ``parse_nodejs_source`` / Vue) to the common
:class:`~startd8.utils.code_manifest.Element` / ``FileManifest`` shape consumed by
``ManifestRegistry`` and ``forward_manifest_validator``.

**Phase 1 (this commit)** establishes the single, total, non-colliding ``kind``-string →
:class:`ElementKind` map (FR-3) and the ``map_parser_kind`` helper. The element/import
adapters and the ``build_multilang_file_manifest`` dispatcher (FR-1/FR-2) land in Phase 2.

The map is **non-colliding**: each parser ``kind`` string has exactly one ``ElementKind``
target, and no ``ElementKind`` member is introduced twice. ``type_alias`` already exists on
``ElementKind`` (do NOT re-add it — R1-F5). ``const_function``/``constructor`` map onto the
existing ``FUNCTION``/``METHOD`` kinds.
"""

from __future__ import annotations

from startd8.logging_config import get_logger
from startd8.utils.code_manifest import ElementKind

logger = get_logger(__name__)


#: The total ``kind``-string → :class:`ElementKind` map (FR-3 / R1-F5).
#: Covers every ``kind`` literal the five per-language parsers emit (verified by
#: ``tests/unit/languages/test_manifest_kind_map.py``). Keep this the SINGLE source of
#: truth for kind translation — the Phase-2 adapters route through :func:`map_parser_kind`.
PARSER_KIND_MAP: dict[str, ElementKind] = {
    # --- shared / Python (already-existing ElementKind values) ---
    "class": ElementKind.CLASS,
    "function": ElementKind.FUNCTION,
    "async_function": ElementKind.ASYNC_FUNCTION,
    "method": ElementKind.METHOD,
    "async_method": ElementKind.ASYNC_METHOD,
    "property": ElementKind.PROPERTY,
    "constant": ElementKind.CONSTANT,
    "variable": ElementKind.VARIABLE,
    "type_alias": ElementKind.TYPE_ALIAS,  # already exists — mapped, not re-added
    # --- Node/JS/TS ---
    "const_function": ElementKind.FUNCTION,  # `const f = () => …` is a function
    # --- C#/Java/Go native kinds (new ElementKind members, FR-3) ---
    "constructor": ElementKind.METHOD,  # a constructor is a method
    "interface": ElementKind.INTERFACE,
    "enum": ElementKind.ENUM,
    "struct": ElementKind.STRUCT,
    "record": ElementKind.RECORD,
    "field": ElementKind.FIELD,
    # --- JS/TS default export (FR-4, emitted by the Phase-4 nodejs_parser enhancement) ---
    "default_export": ElementKind.DEFAULT_EXPORT,
}


#: The documented set of ``kind`` strings each parser may emit. Used by the FR-3 acceptance
#: test to assert ``parser kinds ⊆ PARSER_KIND_MAP keys`` without depending on optional
#: parser backends (tree-sitter / javalang) being installed. Sourced from each parser's
#: ``kind`` docstring + the emitted literals on disk.
PARSER_KIND_SETS: dict[str, frozenset[str]] = {
    "python": frozenset({
        "class", "function", "async_function", "method", "async_method",
        "property", "constant", "variable", "type_alias",
    }),
    "csharp": frozenset({
        "class", "interface", "struct", "record", "enum",
        "method", "constructor", "property",
    }),
    "go": frozenset({
        "function", "method", "class", "type_alias", "constant", "variable",
    }),
    "java": frozenset({
        "class", "interface", "enum", "method", "constructor", "field", "constant",
    }),
    "nodejs": frozenset({
        "function", "class", "method", "const_function", "interface", "type_alias",
    }),
}


def map_parser_kind(kind: str) -> ElementKind:
    """Translate a per-language parser ``kind`` string to an :class:`ElementKind`.

    Returns the mapped kind for any string in :data:`PARSER_KIND_MAP`. For an
    **unknown** string (a parser added a kind the map hasn't been taught), logs a WARNING
    and degrades to :attr:`ElementKind.VARIABLE` so extraction never crashes — the FR-3
    acceptance test guards against this happening for the known parsers (no silent drop in
    practice; graceful in production).
    """
    mapped = PARSER_KIND_MAP.get(kind)
    if mapped is None:
        logger.warning(
            "manifest_adapter: unmapped parser kind %r — defaulting to VARIABLE; "
            "add it to PARSER_KIND_MAP",
            kind,
        )
        return ElementKind.VARIABLE
    return mapped
