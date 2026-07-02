# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Synthetic-claim provenance for panel answers (FR-10, FR-18).

A panel answer is *synthetic, unratified* input. It is minted as a
:class:`~startd8.fde.models.LabeledClaim` with ``label=OBSERVED``, ``qualifier="synthetic"``, and
``source="panel:<role_id>"`` — rendering ``OBSERVED (project, synthetic)`` (FR-10). Two invariants
this module enforces:

* **The synthetic marker is load-bearing, not cosmetic (R1-F2).** :func:`is_synthetic` reads the
  ``qualifier`` (a typed check), not just the OBSERVED prefix; and :func:`assert_ratifiable` refuses
  to let a synthetic claim cross into a ratified/load-bearing store without a human ratification
  token. (The live ratified store is wired by VIPP in M2; M1 ships the gate primitive + tests.)
* **The marker survives serialization byte-identically (R1-F6).** ``LabeledClaim.from_dict`` reads
  ``qualifier`` back, so a persisted-then-reloaded synthetic claim never silently upgrades to an
  unqualified fact. :func:`round_trips_synthetic` is the guard other code (and tests) assert on.
"""

from __future__ import annotations

import hashlib
import json

from startd8.fde.models import ClaimLabel, LabeledClaim
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

# The qualifier that marks a claim as panel-authored/unratified. Free-text in LabeledClaim, but a
# single constant here so producer and consumers agree (and the FR-21 gate still passes on prefix).
SYNTHETIC_QUALIFIER = "synthetic"
# role_id rides in `source` under this prefix so a consumer can recover which persona spoke.
SOURCE_PREFIX = "panel:"


class RatificationError(RuntimeError):
    """Raised when a synthetic claim is about to enter a ratified store without a human token (FR-18)."""


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


def is_synthetic(claim: LabeledClaim) -> bool:
    """True iff *claim* is panel-authored — a **typed** check on the qualifier, not the label prefix.

    Consumers making a load-bearing decision must call this (R1-F2): a claim whose ``label`` is
    OBSERVED but whose ``qualifier`` is ``synthetic`` is NOT a ratified fact.
    """
    return claim.qualifier == SYNTHETIC_QUALIFIER and claim.source.startswith(
        SOURCE_PREFIX
    )


def assert_ratifiable(claim: LabeledClaim, *, ratification_token: str | None) -> None:
    """Gate a write of *claim* into a ratified/load-bearing store (FR-18).

    A synthetic claim may cross the boundary only with a non-empty human ``ratification_token``.
    Non-synthetic claims pass through untouched. Raises :class:`RatificationError` otherwise.
    """
    if is_synthetic(claim) and not (ratification_token and ratification_token.strip()):
        raise RatificationError(
            f"refusing to ratify synthetic claim {claim.claim_id!r} without a human ratification "
            f"token (FR-18) — surface it for confirmation first"
        )


def round_trips_synthetic(claim: LabeledClaim) -> bool:
    """Guard (R1-F6): a synthetic claim survives ``to_dict``→``from_dict`` with its marker intact."""
    reloaded = LabeledClaim.from_dict(claim.to_dict())
    return is_synthetic(reloaded) and reloaded.qualifier == claim.qualifier
