"""FR-SAP-8/9/11 — the Sapper gate orchestrator.

Runs the validators (bore, convention route, cross-contract, per-element), optionally enriches
findings via the FDE, dedups by fingerprint, builds the ranked ``FrictionReport``, and applies
the **gated-off** blocking decision (FR-SAP-8 / NR-2 — advisory by default).

Loud degradation (FR-SAP-9, R1-F10): missing/empty EMIT inputs → a single
``UNRESOLVED(input_absent)`` report, never a silent empty ``VALIDATED``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Set

from startd8.logging_config import get_logger

from .convention_route import run_convention_route
from .cross_contract import run_cross_contract
from .extractor import shared_files as compute_shared_files
from .ground_truth import GroundTruthQuestion, GroundTruthQuery, GroundTruthTimeout, GroundTruthVerdict, NullOracle
from .models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    FrictionReport,
    Severity,
    UnresolvedReason,
    avoidable_cost_stage,
    finding_fingerprint,
)
from .pilot_bore import run_pilot_bore
from .rules_sapper import run_per_element_rules

logger = get_logger(__name__)

GATING_ENV = "STARTD8_SAPPER_GATING"
GATED_KINDS_ENV = "STARTD8_SAPPER_GATED_KINDS"


@dataclass
class SapperGateResult:
    report: FrictionReport
    blocked: bool = False
    block_reasons: List[str] = field(default_factory=list)


def gating_enabled() -> bool:
    return os.environ.get(GATING_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _gated_kinds() -> Set[str]:
    raw = os.environ.get(GATED_KINDS_ENV, "").strip()
    if raw in ("", "none"):
        return set()
    if raw == "all":
        return {k.value for k in AssumptionKind}
    return {k.strip() for k in raw.split(",") if k.strip()}


def run_sapper_gate(
    manifest,
    skeleton_sources: Optional[dict],
    project_root: Optional[str] = None,
    *,
    fde: Optional[GroundTruthQuery] = None,
) -> SapperGateResult:
    """Run the full pre-execution survey and return the report + (gated-off) block decision."""
    # --- FR-SAP-9: loud degradation on absent EMIT inputs ---
    if manifest is None or not skeleton_sources:
        report = FrictionReport(
            bore_status="unavailable",
            notes=["EMIT inputs absent/empty — loud UNRESOLVED(input_absent)"],
            findings=[
                FrictionFinding(
                    id="gate::input_absent",
                    kind=AssumptionKind.DECOMPOSITION_INTEGRITY,
                    verdict=AssumptionVerdict.UNRESOLVED,
                    severity=Severity.HIGH,
                    avoidable_cost_stage=avoidable_cost_stage(AssumptionKind.DECOMPOSITION_INTEGRITY),
                    fingerprint=finding_fingerprint(
                        AssumptionKind.DECOMPOSITION_INTEGRITY, "", "input_absent"
                    ),
                    reason=UnresolvedReason.INPUT_ABSENT,
                    found="missing or empty ForwardManifest / skeleton_sources",
                )
            ],
        )
        return SapperGateResult(report=report)

    shared = compute_shared_files(manifest)
    fde = fde or NullOracle()

    findings: List[FrictionFinding] = []

    bore = run_pilot_bore(skeleton_sources, project_root, shared_files=shared)
    findings.extend(bore.findings)
    findings.extend(run_convention_route(skeleton_sources, shared_files=shared))
    findings.extend(run_cross_contract(manifest, shared_files=shared))
    findings.extend(run_per_element_rules(manifest, shared_files=shared))

    findings = _enrich_with_fde(findings, fde)
    findings = _dedup(findings)

    report = FrictionReport(
        findings=findings,
        bore_status=bore.bore_status,
        notes=list(bore.notes),
    )

    blocked, reasons = _gating_decision(report)
    return SapperGateResult(report=report, blocked=blocked, block_reasons=reasons)


def _enrich_with_fde(findings: List[FrictionFinding], fde: GroundTruthQuery) -> List[FrictionFinding]:
    """Ask the FDE about module-source findings to attach a suggested fix (R4-F5 path)."""
    for f in findings:
        if f.kind is not AssumptionKind.MODULE_SOURCE or f.suggested_fix or not f.symbol:
            continue
        q = GroundTruthQuestion(
            assumption_id=f.id, kind=f.kind, claim=f.expected, module=f.symbol, symbol=f.symbol
        )
        try:
            ans = fde.answer(q)
        except GroundTruthTimeout:
            continue
        if ans.verdict is GroundTruthVerdict.REFUTED and ans.evidence:
            f.suggested_fix = ans.evidence
    return findings


def _dedup(findings: List[FrictionFinding]) -> List[FrictionFinding]:
    """Collapse duplicate findings (same fingerprint) — e.g. bore + convention on one miss.

    Prefers a finding that carries a suggested_fix / richer evidence.
    """
    by_fp: dict = {}
    for f in findings:
        existing = by_fp.get(f.fingerprint)
        if existing is None:
            by_fp[f.fingerprint] = f
            continue
        # keep the one with a suggested_fix, else the higher severity
        if f.suggested_fix and not existing.suggested_fix:
            by_fp[f.fingerprint] = f
        elif f.severity.order > existing.severity.order:
            by_fp[f.fingerprint] = f
    return list(by_fp.values())


def _gating_decision(report: FrictionReport):
    """FR-SAP-8: gated off by default; per-kind selectable. Advisory unless explicitly enabled."""
    if not gating_enabled():
        return False, []
    gated = _gated_kinds()
    if not gated:
        return False, []
    reasons = [
        f"{f.kind.value} REFUTED (high) in {f.file}"
        for f in report.refuted
        if f.severity is Severity.HIGH and f.kind.value in gated
    ]
    return (bool(reasons), reasons)
