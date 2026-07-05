# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Synthetic-claim provenance for panel answers (FR-10, FR-18).

A panel answer is *synthetic, unratified* input. It is minted as a
:class:`~startd8.fde.models.LabeledClaim` with ``label=OBSERVED``, ``qualifier="synthetic"``,
and ``source="panel:<role_id>"`` — rendering ``OBSERVED (project, synthetic)`` (FR-10).

The **claim-level** ratification primitives (``is_synthetic`` / ``assert_ratifiable`` /
``RatificationError`` / ``round_trips_synthetic`` / ``SYNTHETIC_QUALIFIER`` / ``SOURCE_PREFIX``)
now live in the leaf :mod:`startd8.fde.ratification` — the single owner both this package and
``vipp`` can import without an import cycle (FR-RW-5). They are re-exported here unchanged for
backward compatibility. This module keeps only the **panel-answer-specific** helpers
(:func:`synthetic_claim`, :func:`brief_hash`), which depend on ``PanelAnswer``/``PersonaBrief``.
"""

from __future__ import annotations

import hashlib
import json

from startd8.fde.models import ClaimLabel, LabeledClaim

# Re-export the claim-level ratification primitives (single source: fde.ratification).
from startd8.fde.ratification import (
    SOURCE_PREFIX,
    SYNTHETIC_QUALIFIER,
    RatificationError,
    assert_ratifiable,
    is_synthetic,
    round_trips_synthetic,
)
from startd8.stakeholder_panel.models import PanelAnswer, PersonaBrief

__all__ = [
    "SYNTHETIC_QUALIFIER",
    "SOURCE_PREFIX",
    "RatificationError",
    "brief_hash",
    "synthetic_claim",
    "is_synthetic",
    "assert_ratifiable",
    "round_trips_synthetic",
]


def brief_hash(brief: PersonaBrief) -> str:
    """Stable content hash of a persona brief (R2-F3).

    Pins the exact brief revision that produced an answer, so a persisted answer stays traceable
    after ``stakeholders.yaml`` is edited. Canonical JSON (sorted keys) ⇒ order-independent.
    """
    payload = json.dumps(brief.to_dict(), sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def synthetic_claim(answer: PanelAnswer) -> LabeledClaim:
    """Mint the ``OBSERVED (project, synthetic)`` claim for *answer* (FR-10).

    ``claim_id`` embeds the brief hash so the claim itself carries the provenance carry-through
    FR-18 requires after ratification.
    """
    return LabeledClaim(
        label=ClaimLabel.OBSERVED,
        text=answer.text,
        source=f"{SOURCE_PREFIX}{answer.role_id}",
        claim_id=f"panel:{answer.role_id}:{answer.brief_hash}",
        qualifier=SYNTHETIC_QUALIFIER,
    )
