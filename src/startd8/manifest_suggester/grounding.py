# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Schema-anchored grounding guard (FR-MS-4 — a NECESSARY, not sufficient, pre-filter).

Grounds a candidate against the extractor's own :class:`EntityGraph`: every referenced entity must
resolve to a declared entity, and a view's ``Kind`` must be in the published vocabulary. CRP-triaged
posture (R1-F3/R1-S3, Ask 2): this guard is a **cheap pre-filter**, not the completeness check — the
**round-trip through ``extract_views`` is the authoritative gate** (FR-MS-5). A "guard passed /
round-trip failed" outcome is expected behavior, not a bug; the guard exists to reject the obvious
(ungrounded entity, bad Kind) *before* the apply seam, not to reimplement the extractor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from startd8.manifest_extraction.entities import EntityGraph
from startd8.manifest_extraction.extractors import _KINDS

from startd8.manifest_suggester.models import KIND_VIEW, ScreenCandidate

__all__ = ["GroundResult", "ground", "PUBLISHED_KINDS"]

# The full published Kind vocabulary (R1-F4: 7 values, not the 3 in OQ-1). v1 drafts `dashboard`.
PUBLISHED_KINDS = frozenset(_KINDS)

_KIND_LINE = re.compile(r"^\s*(?:-\s*)?Kind:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class GroundResult:
    ok: bool
    reasons: List[str]

    def __bool__(self) -> bool:  # truthy iff grounded
        return self.ok


def ground(candidate: ScreenCandidate, graph: EntityGraph) -> GroundResult:
    """Pre-filter *candidate* against *graph*. Returns a grounded/rejected result with reasons.

    Necessary checks only (the round-trip is authoritative, FR-MS-5):
      * every ``entities_referenced`` resolves to a declared entity (schema-anchored, FR-MS-4);
      * a view's ``Kind`` is in the published vocabulary.
    """
    reasons: List[str] = []
    for ent in candidate.entities_referenced:
        if graph.resolve_entity(ent) is None:
            reasons.append(f"entity {ent!r} does not resolve against declared entities")

    if candidate.kind == KIND_VIEW:
        m = _KIND_LINE.search(candidate.prose)
        if m is None:
            reasons.append("view prose has no `Kind:` line")
        elif m.group(1).strip() not in PUBLISHED_KINDS:
            reasons.append(
                f"Kind {m.group(1).strip()!r} outside the published vocabulary {sorted(PUBLISHED_KINDS)}"
            )

    return GroundResult(ok=not reasons, reasons=reasons)
