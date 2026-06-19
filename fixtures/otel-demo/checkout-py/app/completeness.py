# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-completeness
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

ENTITIES: List[str] = ["PlaceOrderSession"]


@dataclass
class CompletenessResult:
    score: float  # 0.0 .. 1.0
    nudges: List[str]  # priority-ordered, schema order


def compute_completeness(present: Dict[str, int]) -> CompletenessResult:
    """Presence rule (OQ-4 v1): score = fraction of entities with >=1 row; one nudge per
    absent entity. Domain-weighted thresholds (e.g. >=3 ProofPoints) are a manifest
    refinement, deferred."""
    if not ENTITIES:
        return CompletenessResult(score=1.0, nudges=[])
    have = [e for e in ENTITIES if present.get(e, 0) > 0]
    score = round(len(have) / len(ENTITIES), 4)
    nudges = [f'Add at least one {e}.' for e in ENTITIES if present.get(e, 0) == 0]
    return CompletenessResult(score=score, nudges=nudges)
