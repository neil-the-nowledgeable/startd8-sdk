"""Surface-form canonicalization (FR-4, OQ-6).

Maps drifting natural-language labels ("Shared JSON Logger — emailservice" vs
"Email Service JSON Logger") to one stable canonical_key. v1 default: anchor on the
target_file (the proven invariant — see CORPUS_V0_FINDINGS title-drift-vs-stability),
falling back to a normalized surface form for terms without a file binding (proto-level
services/RPCs/entities).

OQ-6 is tracked open; this is the v1 decision, isolated here so it can change in one place.
"""
from __future__ import annotations

import re

__all__ = ["canonical_key", "normalize_surface"]

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_surface(s: str) -> str:
    """Lowercase, strip non-alphanumerics to single hyphens — for label dedup."""
    return _NON_ALNUM.sub("-", s.strip().lower()).strip("-")


def canonical_key(kind: str, surface_form: str = "", target_file: str = "") -> str:
    """Stable key for a term.

    target_file-anchored when present (the deterministic invariant); else the
    normalized surface form. For proto terms (service/rpc/entity) the surface_form
    is already canonical (it comes from the proto), so normalization is safe.
    """
    if target_file:
        return target_file.strip()
    return normalize_surface(surface_form)
