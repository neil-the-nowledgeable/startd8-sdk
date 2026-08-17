"""Conformance + plan-liveness validation for a projected det-plan/0.1 (REQ-29 FR-5, SCHEMA §10).

Validates a :class:`DetPlan` against the ``det-plan/0.1`` conformance rules and emits its findings
as **SARIF 2.1.0** through the ONE reusable renderer — ``coverage_map/findings_sarif`` (charter
invariant 6, **imported not vendored**). Counts LIVE ``pairsWith`` only (§6): a "paired" census that
counts a PHANTOM/ABSENT companion is a survivorship lie.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..coverage_map.findings_sarif import render_sarif_from_findings
from .models import (
    COMPANION_KIND,
    FORMAT_VERSION,
    PROJECTED_MATURITY,
    DetPlan,
    PlanFinding,
)

TOOL_NAME = "startd8-plan-projector"

# pairsWith liveness classes (SCHEMA §6).
LIVE = "LIVE"
PHANTOM = "PHANTOM"
ABSENT = "ABSENT"


def classify_pairs_with(plan: DetPlan, *, base_dir: Optional[Path]) -> str:
    """Classify the plan's ``pairsWith`` link (§6). LIVE iff the paired req file resolves on disk.

    ABSENT when no ``pairsWith`` is declared; PHANTOM when declared but the file is absent (or no
    ``base_dir`` is given to resolve it against — we never claim a presence we cannot check).
    """
    if not plan.pairs_with or plan.pairs_with == "(source req)":
        return ABSENT
    if base_dir is None:
        return PHANTOM
    return LIVE if (base_dir / plan.pairs_with).is_file() else PHANTOM


def validate_plan(
    plan: DetPlan, *, req_fr_ids: Optional[set] = None, base_dir: Optional[Path] = None
) -> List[PlanFinding]:
    """Validate *plan* against det-plan/0.1 §10; return a list of :class:`PlanFinding` (empty = clean).

    Checks: ``formatVersion``; ``companionKind == PLAN``; ``maturity`` not inflated; every iteration
    carries a gate; every ``iteration.frs`` references an FR that exists in the paired req (when
    ``req_fr_ids`` is supplied); ``dependsOn`` targets a real iteration (acyclicity is enforced at
    projection time); and ``pairsWith`` resolves LIVE (plan-liveness).
    """
    findings: List[PlanFinding] = []
    where = plan.pairs_with or "(plan)"

    if plan.format_version != FORMAT_VERSION:
        findings.append(
            PlanFinding(
                "format-version",
                "error",
                f"formatVersion must be {FORMAT_VERSION!r}, got {plan.format_version!r}",
                where,
            )
        )
    if plan.companion_kind != COMPANION_KIND:
        findings.append(
            PlanFinding(
                "companion-kind",
                "error",
                f"companionKind must be {COMPANION_KIND!r}, got {plan.companion_kind!r}",
                where,
            )
        )
    if plan.maturity != PROJECTED_MATURITY:
        findings.append(
            PlanFinding(
                "maturity-inflation",
                "error",
                f"a projected plan must be maturity {PROJECTED_MATURITY!r} (anti-inflation), "
                f"got {plan.maturity!r}",
                where,
            )
        )

    iter_ids = {it.id for it in plan.iterations}
    for it in plan.iterations:
        if not it.gate:
            findings.append(
                PlanFinding(
                    "fr-less-iteration",
                    "error",
                    f"iteration {it.id} carries no gate (no FR `Verify:` clause) — no "
                    "iteration ships without its gate (§5)",
                    where,
                )
            )
        if req_fr_ids is not None:
            for fr in it.frs:
                if fr not in req_fr_ids:
                    findings.append(
                        PlanFinding(
                            "phantom-fr",
                            "error",
                            f"iteration {it.id} references {fr} which is not an FR in the "
                            "paired req",
                            where,
                        )
                    )
        for dep in it.depends_on:
            if dep not in iter_ids:
                findings.append(
                    PlanFinding(
                        "invented-dependency",
                        "error",
                        f"iteration {it.id} dependsOn {dep} which is not a real iteration "
                        "(invented edge)",
                        where,
                    )
                )

    liveness = classify_pairs_with(plan, base_dir=base_dir)
    if liveness != LIVE:
        findings.append(
            PlanFinding(
                "plan-liveness",
                "warning",
                f"pairsWith `{plan.pairs_with}` is {liveness}, not LIVE — a paired census "
                "counts LIVE only (§6)",
                where,
            )
        )
    return findings


def findings_to_sarif(
    findings: List[PlanFinding], *, corpus: Optional[str] = None
) -> dict:
    """Render conformance/liveness findings as SARIF 2.1.0 via the ONE reusable renderer (FR-5)."""
    return render_sarif_from_findings(
        findings, tool_name=TOOL_NAME, tool_version=FORMAT_VERSION, corpus=corpus
    )
