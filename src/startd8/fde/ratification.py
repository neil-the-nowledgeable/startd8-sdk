# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Claim-level ratification primitives (FR-GE-14 / FR-18).

Ratification is a property of a :class:`~startd8.fde.models.LabeledClaim`, so these
primitives live in the ``fde`` leaf — the single owner both ``stakeholder_panel`` (which
mints synthetic panel answers) and ``vipp`` (which applies dispositions into a load-bearing
store) import **without an import cycle**. ``stakeholder_panel.provenance`` re-exports them
for backward compatibility; the panel-answer-specific helpers (``synthetic_claim`` /
``brief_hash``) stay there because they depend on ``PanelAnswer``/``PersonaBrief``.

A synthetic claim (a panel-authored, *unratified* input) is an ``OBSERVED`` claim carrying
``qualifier="synthetic"`` and ``source="panel:<role_id>"``. Two invariants:

* **The marker is load-bearing, not cosmetic (R1-F2).** :func:`is_synthetic` reads the
  ``qualifier`` (a typed check), not just the OBSERVED prefix; :func:`assert_ratifiable`
  refuses to let a synthetic claim cross into a ratified/load-bearing store without a
  human ratification token.
* **The marker survives serialization byte-identically (R1-F6).**
  :func:`round_trips_synthetic` guards that a persisted-then-reloaded synthetic claim
  never silently upgrades to an unqualified fact.
"""

from __future__ import annotations

from startd8.fde.models import LabeledClaim

__all__ = [
    "SYNTHETIC_QUALIFIER",
    "SOURCE_PREFIX",
    "RatificationError",
    "is_synthetic",
    "assert_ratifiable",
    "round_trips_synthetic",
]

# The qualifier that marks a claim as panel-authored/unratified. Free-text in LabeledClaim,
# but a single constant here so producer and consumers agree (and the FR-21 gate still
# passes on prefix).
SYNTHETIC_QUALIFIER = "synthetic"
# role_id rides in `source` under this prefix so a consumer can recover which persona spoke.
SOURCE_PREFIX = "panel:"


class RatificationError(RuntimeError):
    """Raised when a synthetic claim is about to enter a ratified store without a human token (FR-18)."""


def is_synthetic(claim: LabeledClaim) -> bool:
    """True iff *claim* is panel-authored — a **typed** check on the qualifier, not the label prefix.

    Consumers making a load-bearing decision must call this (R1-F2): a claim whose ``label``
    is OBSERVED but whose ``qualifier`` is ``synthetic`` is NOT a ratified fact.
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
