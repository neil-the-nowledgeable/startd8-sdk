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
from .apply import ApplyResult, PreviewResult, apply_dispositions, preview_dispositions
from .assistant import NegotiateOutcome, run_vipp_negotiate
from .evaluate import evaluate_envelope
from .ground_truth import (
    SAPPER_AVAILABLE,
    answer_to_observed_claim,
    build_oracle,
    load_observed_claims,
    observed_from_oracle,
    observed_from_report,
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
    # M1 — ground-truth consumption
    "SAPPER_AVAILABLE",
    "load_observed_claims",
    "observed_from_oracle",
    "observed_from_report",
    "answer_to_observed_claim",
    "build_oracle",
    # M2 — negotiation brain
    "run_vipp_negotiate",
    "NegotiateOutcome",
    "evaluate_envelope",
    # M4 — applier
    "apply_dispositions",
    "ApplyResult",
    "preview_dispositions",
    "PreviewResult",
]
