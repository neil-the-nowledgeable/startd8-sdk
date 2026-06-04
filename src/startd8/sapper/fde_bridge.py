"""Sapper → FDE compose seam (Option A reconciliation).

Expresses Sapper's project-ground-truth findings in the **SDK-mechanism FDE's** vocabulary so the
*deployed* FDE (``startd8.fde``) can compose them as the OBSERVED-project half of a cross-boundary
verdict (Tekizai-Tekisho). Sapper depends on ``startd8.fde`` here — **never the reverse** (the FDE
does not import Sapper), so there is no cycle.

A Sapper ``FrictionFinding`` is OBSERVED-project evidence about the *plan* ("the plan invents
``Match``, which is absent from ``app.tables``"). The FDE pairs each with its own MECHANISM claim
("this file routes to micro-prime, where convention injection is bypassed") — together, the full
RUN-028 story from a single deployed posting.

Degrades gracefully: if the ``startd8.fde`` package is unavailable, ``FDE_AVAILABLE`` is ``False``
and ``to_observed_claims`` raises a clear error rather than failing at import time.
"""

from __future__ import annotations

from typing import List

from .models import AssumptionVerdict, FrictionFinding, FrictionReport

try:  # the SDK-mechanism FDE may not be installed in every deployment
    from startd8.fde.models import ClaimLabel, LabeledClaim

    FDE_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only without the fde package
    ClaimLabel = None  # type: ignore[assignment]
    LabeledClaim = None  # type: ignore[assignment]
    FDE_AVAILABLE = False


def _claim_text(f: FrictionFinding) -> str:
    where = f"`{f.file}`" + (f":{f.line}" if f.line else "")
    verdict = f.verdict.value.upper() + (f"/{f.reason.value}" if f.reason else "")
    body = f"{f.expected}" + (f" (found: {f.found})" if f.found else "")
    fix = f" — {f.suggested_fix}" if f.suggested_fix else ""
    return f"[{verdict}] {where}: {body}{fix}"


def to_observed_claims(report: FrictionReport) -> List["LabeledClaim"]:
    """Convert a Sapper report's non-VALIDATED findings into FDE OBSERVED ``LabeledClaim``s.

    ``claim_id`` reuses the finding fingerprint so a narrator can reference a claim without
    inventing new ones, and so the same misalignment is stable across runs.
    """
    if not FDE_AVAILABLE:
        raise RuntimeError(
            "startd8.fde is unavailable — cannot bridge Sapper findings to FDE LabeledClaims"
        )
    claims: List[LabeledClaim] = []
    for f in report.ranked:
        if f.verdict is AssumptionVerdict.VALIDATED:
            continue
        claims.append(
            LabeledClaim(
                label=ClaimLabel.OBSERVED,
                text=_claim_text(f),
                source=f"sapper:{f.kind.value}",
                claim_id=f.fingerprint,
            )
        )
    return claims


def compose_with_fde_preflight(report: FrictionReport, fde_preflight_report) -> dict:
    """Compose the deployed-FDE pair (Item 4c): MECHANISM landmines + OBSERVED ground-truth.

    Merges the SDK-mechanism FDE's preflight (``FdePreflightReport`` — "this routes to micro-prime
    where injection is bypassed") with Sapper's ground-truth refutations ("...and here is the Flask /
    invented ``Match`` that proves it"). Returns a single composed view the deployed FDE can front —
    the full RUN-028 story from one posting. Sapper depends on ``startd8.fde``, never the reverse.
    """
    landmines = getattr(fde_preflight_report, "sorted_landmines", None)
    mech = (landmines() if callable(landmines) else getattr(fde_preflight_report, "landmines", [])) or []
    observed = to_observed_claims(report)
    return {
        "kind": "fde-sapper-composed",
        "mechanism_landmines": [m.to_dict() if hasattr(m, "to_dict") else m for m in mech],
        "observed_findings": [c.to_dict() if hasattr(c, "to_dict") else c for c in observed],
        "summary": {
            "mechanism_count": len(mech),
            "observed_count": len(observed),
            "sapper_counts": report.counts(),
        },
    }
