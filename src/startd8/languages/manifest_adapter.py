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

import hashlib
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger
from startd8.utils.code_manifest import (
    Element,
    ElementKind,
    FileManifest,
    ImportEntry,
    Signature,
    Span,
    generate_file_manifest,
)

logger = get_logger(__name__)

#: FR-5 confidence tiers stamped on a produced FileManifest.
TIER_AUTHORITATIVE = "authoritative"  # AST-grade: Python ast / C# tree-sitter / Java javalang
TIER_ADVISORY = "advisory"  # regex-grade, or an AST parser that fell back to regex

#: Element kinds the `Element` model treats as callable — these MUST carry a `Signature`
#: (``code_manifest.py:_validate_kind_fields`` raises otherwise — R1-F1). Mirrors that set.
_CALLABLE_KINDS = frozenset({
    ElementKind.FUNCTION,
    ElementKind.ASYNC_FUNCTION,
    ElementKind.METHOD,
    ElementKind.ASYNC_METHOD,
    ElementKind.PROPERTY,
})

#: Extensions routed to each adapter by :func:`build_multilang_file_manifest`.
_CSHARP_EXT = {".cs"}
_JAVA_EXT = {".java"}
_PYTHON_EXT = {".py"}


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


# --------------------------------------------------------------------------- #
# Phase 2 — element adapter + multi-language builder (FR-1 / FR-2 / FR-5)
# --------------------------------------------------------------------------- #


def _adapt_element(
    kind_str: str,
    name: str,
    start_line: int,
    end_line: int,
    *,
    parent: Optional[str] = None,
) -> Element:
    """Adapt one per-language parser element into the common :class:`Element` (FR-2).

    Lossless on ``name`` (the validator's match key). Callable kinds get a **minimal**
    synthesized ``Signature`` (R1-F1: the model rejects ``signature=None`` for callables);
    ``return_annotation`` is left ``None`` so signature/return-type enforcement stays
    deferred (OQ-5). ``bases`` is never set for non-class kinds (the model forbids it).
    """
    kind = map_parser_kind(kind_str)
    signature = (
        Signature(params=[], return_annotation=None) if kind in _CALLABLE_KINDS else None
    )
    fqn = f"{parent}.{name}" if parent else name
    return Element(
        kind=kind,
        name=name,
        fqn=fqn,
        span=Span(
            start_line=max(int(start_line), 0),
            start_col=0,
            end_line=max(int(end_line), 0),
            end_col=0,
        ),
        signature=signature,
    )


def _module_name(rel_path: str) -> str:
    return Path(rel_path).with_suffix("").as_posix().replace("/", ".")


def _make_manifest(
    rel_path: str,
    source: str,
    elements: List[Element],
    imports: List[ImportEntry],
    tier: Optional[str],
) -> FileManifest:
    return FileManifest(
        file=rel_path,
        module=_module_name(rel_path),
        digest=hashlib.sha256(source.encode("utf-8", "replace")).hexdigest(),
        elements=elements,
        imports=imports,
        parser_tier=tier,
    )


def _adapt_csharp(rel_path: str, source: str) -> FileManifest:
    from startd8.languages.csharp_parser import parse_csharp

    result = parse_csharp(source)
    # Per-parse tier (R1-F4): tree-sitter is authoritative; a regex fallback is advisory.
    tier = TIER_AUTHORITATIVE if result.parser_used == "tree_sitter" else TIER_ADVISORY
    elements = [
        _adapt_element(e.kind, e.name, e.start_line, e.end_line, parent=e.parent)
        for e in result.elements
    ]
    return _make_manifest(rel_path, source, elements, [], tier)


def _adapt_java(rel_path: str, source: str) -> FileManifest:
    from startd8.languages.java_parser import parse_java_imports, parse_java_source

    elements = [
        _adapt_element(e.kind, e.name, e.line_number, e.end_line, parent=e.parent)
        for e in parse_java_source(source)
    ]
    imports = [
        ImportEntry(
            kind="import",
            module=mod,
            span=Span(start_line=0, start_col=0, end_line=0, end_col=0),
        )
        for mod in parse_java_imports(source)
    ]
    # javalang is authoritative; the regex fallback (when javalang is absent) is advisory.
    try:
        import javalang  # noqa: F401

        tier = TIER_AUTHORITATIVE
    except ImportError:
        tier = TIER_ADVISORY
    return _make_manifest(rel_path, source, elements, imports, tier)


def build_multilang_file_manifest(rel_path: str, source: str) -> FileManifest:
    """Build a :class:`FileManifest` for any supported language (FR-1).

    Dispatches by extension: Python → the existing ``generate_file_manifest`` (authoritative,
    behavior unchanged — NFR-1); C# → tree-sitter/regex via ``parse_csharp``; Java → javalang/
    regex via ``parse_java_source``. The produced manifest carries a ``parser_tier`` (FR-5).
    Unsupported extensions (Go/Node/Vue land in Phase 3) return an **empty-but-valid**
    manifest with ``parser_tier=None`` — degrade, never raise.
    """
    ext = Path(rel_path).suffix.lower()
    if ext in _PYTHON_EXT:
        # Authoritative Python path: delegate unchanged, then stamp the tier (frozen → copy).
        manifest = generate_file_manifest(
            file_path=rel_path, project_root=Path("."), source=source
        )
        return manifest.model_copy(update={"parser_tier": TIER_AUTHORITATIVE})
    if ext in _CSHARP_EXT:
        return _adapt_csharp(rel_path, source)
    if ext in _JAVA_EXT:
        return _adapt_java(rel_path, source)
    # Unsupported (Go/Node/Vue = Phase 3): empty, tier-less, never raises.
    logger.info(
        "manifest_adapter: no element extractor for %s (ext %r) — empty manifest",
        rel_path, ext,
        extra={"event": "manifest_adapter.unsupported_language", "path": rel_path},
    )
    return _make_manifest(rel_path, source, [], [], None)
