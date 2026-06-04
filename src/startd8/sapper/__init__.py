"""Sapper — pre-execution plan validation (tunnel-alignment survey).

The near-side survey crew: it interrogates the *plan* (the ForwardManifest + rendered
skeletons) BEFORE generation, reconciling each assumption the plan makes about the existing
codebase against ground truth, and emits a ranked *friction report* so the costliest, most
avoidable misalignments surface at document cost rather than at integration/boot time.

Pairs with the Forward Deployed Engineer (FDE) — the far-side ground-truth interface
(``sapper.fde``). See ``docs/design/sapper/SAPPER_PREEXECUTION_VALIDATION_REQUIREMENTS.md``.

Public surface (Phase 0 — models):
- ``Assumption``, ``AssumptionKind``, ``ValidatorClass``
- ``AssumptionVerdict``, ``UnresolvedReason``, ``Severity``, ``AvoidableCostStage``
- ``FrictionFinding``, ``FrictionReport``
- ``avoidable_cost_stage``, ``rank_findings``, ``finding_fingerprint``
"""

from __future__ import annotations

from .models import (
    AVOIDABLE_COST_STAGE,
    Assumption,
    AssumptionKind,
    AssumptionVerdict,
    AvoidableCostStage,
    FrictionFinding,
    FrictionReport,
    Severity,
    UnresolvedReason,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
    rank_findings,
)

from .gate import SapperGateResult, run_sapper_gate
from .host import SapperPreflightOutcome, sapper_preflight_hook

__all__ = [
    # models (Phase 0)
    "AVOIDABLE_COST_STAGE",
    "Assumption",
    "AssumptionKind",
    "AssumptionVerdict",
    "AvoidableCostStage",
    "FrictionFinding",
    "FrictionReport",
    "Severity",
    "UnresolvedReason",
    "ValidatorClass",
    "avoidable_cost_stage",
    "finding_fingerprint",
    "rank_findings",
    # orchestration (Phases 5/9)
    "run_sapper_gate",
    "SapperGateResult",
    "sapper_preflight_hook",
    "SapperPreflightOutcome",
]

SAPPER_REPORT_SCHEMA_VERSION = "1.0.0"
