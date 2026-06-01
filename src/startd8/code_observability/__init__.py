"""Code Knowledge Graph (CKG) — code-observability primitives.

Phase 1: a thin scip-typescript layer (runner + reader) feeding the cross-file Verifier.
See docs/design/CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md (v2.2).
"""

from __future__ import annotations

from .scip_reader import CrossFileEdge, ExternalRef, ParsedSymbol, ScipReader, parse_symbol
from .scip_runner import run_index

__all__ = [
    "CrossFileEdge",
    "ExternalRef",
    "ParsedSymbol",
    "ScipReader",
    "parse_symbol",
    "run_index",
]
