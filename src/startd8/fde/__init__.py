# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Forward Deployed Engineer (FDE) — the SDK's mechanism-authority brain, posted to a project.

Per the Tekizai-Tekisho design principle, the FDE supplies the **MECHANISM (sdk)** half of a
cross-boundary composition: it reads the SDK's own source-of-truth artifacts/code and composes
that with the Service Assistant's **OBSERVED (project)** evidence into a source-labeled report
(explain mode), and flags SDK-mechanism landmines in plans/requirements before implementation
(preflight mode). Deterministic-first; the JSON contract is canonical and the ``.md`` is a
derived view. See ``docs/design/fde/``.
"""

from __future__ import annotations

from .assistant import (
    ExplainOutcome,
    PreflightOutcome,
    run_fde_explain,
    run_fde_preflight,
)
from .models import (
    PROTOCOL_VERSION,
    ClaimLabel,
    FdeExplanation,
    FdeMode,
    FdePreflightReport,
    FdeRequest,
    LabeledClaim,
    Landmine,
)

__all__ = [
    "PROTOCOL_VERSION",
    "ClaimLabel",
    "LabeledClaim",
    "FdeMode",
    "FdeRequest",
    "FdeExplanation",
    "FdePreflightReport",
    "Landmine",
    "run_fde_explain",
    "run_fde_preflight",
    "ExplainOutcome",
    "PreflightOutcome",
]
