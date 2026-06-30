# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP (Very Important Project Person) — the project-side negotiator/applier.

The VIPP is the **OBSERVED(project)-authority dual of the FDE** (``startd8.fde``): where the FDE is
the SDK's mechanism authority *posted into* a project, the VIPP is the project's representative
*facing* the SDK. It ingests the host onboarding stack's serialized proposals (Concierge / Welcome
Mat / Red Carpet), evaluates them against project ground-truth, and applies accepted proposals at
*project* human privilege.

Posture: file-protocol first (Keiyaku-shaped, transport-agnostic contracts; JSON canonical, markdown
derived). The dependency direction is one-way — ``vipp`` → {``fde``, ``sapper``,
``kickoff_experience``} — never the reverse (FR-8). See ``docs/design/vipp/`` for the requirements +
plan. M0 ships the contracts (:mod:`startd8.vipp.models`); later milestones add the brain, the
ground-truth adapter, the host serialization seam, and the applier.
"""

from .models import (
    HOST_PROPOSAL_FIELDS,
    PROTOCOL_VERSION,
    ClaimLabel,
    Decision,
    EnvelopedProposal,
    LabeledClaim,
    ProposalEnvelope,
    VippDisposition,
    VippReport,
    protocol_is_future,
)

__all__ = [
    "PROTOCOL_VERSION",
    "HOST_PROPOSAL_FIELDS",
    "ClaimLabel",
    "LabeledClaim",
    "Decision",
    "EnvelopedProposal",
    "ProposalEnvelope",
    "VippDisposition",
    "VippReport",
    "protocol_is_future",
]
