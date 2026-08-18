"""Shared det-req **header** parsing for the det-doc-kit projectors.

``det_req.parse_fr_lines`` parses the FR *bullets*; this parses the *header* block that every
projector also needs — the semantic name, canonical ref, ``Pairs with:`` companion line, title, and
the ``Format:``/``Governs:`` refs. Extracted from ``plan_codegen``'s first projector when the second
(``handoff_codegen``) needed the same helpers (a ``/reflective-adoption`` fold-back: the first
projector inlined shared substrate that the family must share, not duplicate).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_SEMANTIC_NAME = re.compile(
    r"^>\s*\*\*Semantic name:\*\*\s*\*?(?P<n>.+?)\*?\s*$", re.MULTILINE
)
_CANONICAL_REF = re.compile(
    r"^>\s*\*\*Canonical ref:\*\*\s*`?(?P<r>[^`\n]+?)`?\s*$", re.MULTILINE
)
_PAIRS_WITH = re.compile(r"^\*\*Pairs with:\*\*\s*(?P<p>.+?)\s*$", re.MULTILINE)
_TITLE = re.compile(r"^#\s+(?P<t>.+?)\s*$", re.MULTILINE)
_FORMAT = re.compile(r"^\*\*Format:\*\*\s*(?P<f>.+?)\s*$", re.MULTILINE)


def first(pattern: re.Pattern, text: str, group: str) -> str:
    """First match of *group* in *text* (stripped), or ``""`` when absent."""
    m = pattern.search(text)
    return m.group(group).strip() if m else ""


def semantic_name(text: str) -> str:
    """The DIDL ``> **Semantic name:** *…*`` line (empty when absent)."""
    return first(_SEMANTIC_NAME, text, "n")


def canonical_ref(text: str) -> str:
    """The ``> **Canonical ref:** `cc:intent:…``` line (empty when absent)."""
    return first(_CANONICAL_REF, text, "r")


def pairs_with_line(text: str) -> str:
    """The ``**Pairs with:**`` declaration line (empty when absent)."""
    return first(_PAIRS_WITH, text, "p")


def title(text: str) -> str:
    """The first ``# …`` heading (empty when absent)."""
    return first(_TITLE, text, "t")


def format_ref(text: str) -> str:
    """The ``**Format:**`` line (empty when absent)."""
    return first(_FORMAT, text, "f")


def req_key(text: str, req_path: Optional[Path] = None) -> str:
    """The canonical DIDL key — the req's ``…:req-NN`` tail, else its filename stem, else ``req``."""
    ref = canonical_ref(text)
    if ref:
        return ref.rsplit(":", 1)[-1].strip()
    if req_path is not None:
        return req_path.stem.lower()
    return "req"


def repo_root(req_path: Optional[Path]) -> Optional[Path]:
    """Infer the repo root from a doc path (walk up to a dir containing ``src/startd8``)."""
    if req_path is None:
        return None
    for parent in [req_path.resolve()] + list(req_path.resolve().parents):
        if (parent / "src" / "startd8").is_dir():
            return parent
    return None
