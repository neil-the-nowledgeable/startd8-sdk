# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""``estimate`` provenance for drafted kickoff-input recommendations (FR-KIR-5, D-KIR-2).

**Deliberately separate from** :mod:`startd8.stakeholder_panel.provenance` — which owns the reactive
*synthetic-``OBSERVED``* claim. A Teian recommendation for a still-blank field is not an observation
of project ground truth; it is a **starter estimate** on the kickoff input package's ``estimate`` tier
(owned by ``KICKOFF_INPUT_PACKAGE_GUIDE.md`` §3). Co-locating the two provenance meanings in one module
would re-create the exact overloaded-term collision D-KIR-2 forbids, so this module is the *only* home
for the estimate marker.

Two invariants (FR-KIR-5):

* A recommendation is minted ``estimate`` with a ``panel:<role_id>`` origin and **must never be
  counted as ``authored``** in any provisioning score. The flip to ``authored`` is a human, in-file,
  domain-level act (FR-KIR-7) — the SDK never does it autonomously, so nothing here promotes it.
* The marker survives serialization: :class:`~startd8.stakeholder_panel.models.Recommendation`
  ``from_dict`` defaults a missing ``provenance`` back to ``estimate`` (never to a filled/authored
  value), so a persisted-then-reloaded draft can never silently upgrade.
"""

from __future__ import annotations

from startd8.stakeholder_panel.models import Recommendation

__all__ = [
    "ESTIMATE_PROVENANCE",
    "ORIGIN_PREFIX",
    "panel_origin",
    "is_estimate",
    "assert_not_authored",
]

# The kickoff-package provenance tier a drafted starter sits on (guide §3). NOT `OBSERVED`.
ESTIMATE_PROVENANCE = "estimate"
# The recommendation's origin marker: which persona drafted it.
ORIGIN_PREFIX = "panel:"


def panel_origin(role_id: str) -> str:
    """The origin marker for a recommendation drafted by *role_id* (e.g. ``panel:product-owner``)."""
    return f"{ORIGIN_PREFIX}{role_id}"


def is_estimate(rec: Recommendation) -> bool:
    """True iff *rec* carries the estimate marker + a panel origin — a **typed** check (FR-KIR-5).

    Any consumer must treat an estimate as *unratified draft*, never an authored fact — parity with
    the synthetic-claim ``is_synthetic`` obligation, on the estimate tier.
    """
    return rec.provenance == ESTIMATE_PROVENANCE and rec.origin.startswith(
        ORIGIN_PREFIX
    )


def assert_not_authored(rec: Recommendation) -> None:
    """Guard: a Teian recommendation must never carry ``authored`` provenance (FR-KIR-5).

    The estimate→authored flip is a human, in-file, domain-level decision (FR-KIR-7); a recommendation
    object claiming ``authored`` would be a laundering vector. Raises :class:`ValueError`.
    """
    if rec.provenance == "authored":
        raise ValueError(
            f"recommendation for {rec.value_path!r} claims 'authored' provenance — a drafted "
            "estimate is never authored (FR-KIR-5); the flip is a human in-file act (FR-KIR-7)"
        )
