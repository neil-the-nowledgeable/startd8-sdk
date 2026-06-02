"""CKG Phase 2 — structural relevance scoping (REQ-CKG-524/527, D4).

Replaces the ``_feature_mirrors_data_model`` name/description keyword gate (the
likely RUN-011 Gap-A miss: PI-001/004/007 never matched it, so the field set was
never injected) with two structural signals derived from the code itself:

- **Import-graph closure** (REQ-524): which project modules the feature's target
  files import, via ``extract_import_specifiers`` → ``resolve_specifier_to_paths``
  (the Phase-1 resolver — no new scanner).
- **Entity-reference resolution** (REQ-527): which Prisma entities the feature
  references, by token-matching the real ``models.keys()`` against the feature's
  target-file contents + description.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, Optional, Set

from ..upstream_interface import extract_import_specifiers, resolve_specifier_to_paths

__all__ = ["module_closure", "referenced_entities"]


def module_closure(
    target_sources: Dict[str, str],
    candidate_paths: Iterable[str],
    *,
    alias_prefixes: Optional[Dict[str, str]] = None,
) -> Set[str]:
    """Project module paths the feature's ``target_sources`` import (depth 1).

    ``target_sources`` maps each target file path → its (draft) content;
    ``candidate_paths`` is the set of resolvable project module paths (typically
    the producer's known interfaces). Returns the subset of ``candidate_paths``
    reached by an import specifier. Bare package imports resolve to nothing.
    """
    candidates = list(candidate_paths)
    reached: Set[str] = set()
    for importer_path, source in target_sources.items():
        for spec in extract_import_specifiers(source or ""):
            for hit in resolve_specifier_to_paths(
                spec, candidates,
                alias_prefixes=alias_prefixes,
                importer_path=importer_path,
            ):
                reached.add(hit)
    return reached


def _plural_forms(name: str) -> Set[str]:
    """Singular + common English plural surface forms of an entity name (lowercased).

    Pre-generation the only signal is the feature's name/description/target stems,
    where entities surface in plural (``enrich-capabilities`` → ``Capability``). We
    accept the singular and the regular plural variants, each matched on a word
    boundary so ``Capacitor`` never matches ``Capability``.
    """
    n = name.lower()
    forms = {n, n + "s", n + "es"}
    if n.endswith("y"):
        forms.add(n[:-1] + "ies")
    if n.endswith("s"):
        forms.add(n)  # already plural-ish; keep as-is
    return forms


def referenced_entities(texts: Iterable[str], model_names: Iterable[str]) -> Set[str]:
    """Prisma entities a feature references, by plural-tolerant whole-word match.

    Structural per REQ-527: the candidate set is the schema's real model names
    (not a fixed keyword list), so a feature calling ``db.capability`` / naming
    ``Capability`` / titled ``enrich-capabilities`` is scoped to that entity
    regardless of its filename. Matching is case-insensitive on a word boundary
    over the singular + regular plural forms, so ``Capacitor`` does not match
    ``Capability``.
    """
    names = [n for n in model_names if n]
    if not names:
        return set()
    blob = "\n".join(t for t in texts if t)
    if not blob:
        return set()
    low = blob.lower()
    hits: Set[str] = set()
    for name in names:
        for form in _plural_forms(name):
            if re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", low):
                hits.add(name)
                break
    return hits
