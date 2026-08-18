"""Conformance + liveness validation for a projected det-handoff/0.1 (SCHEMA §7).

Validates a :class:`Handoff` against the ``det-handoff/0.1`` rules and emits findings as **SARIF
2.1.0** through the ONE reusable renderer — ``coverage_map/findings_sarif`` (imported, not vendored;
charter §5/§6). Liveness is checked on BOTH ``pairsWith`` (the REQ) and ``base`` (the git sha).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..coverage_map.findings_sarif import render_sarif_from_findings
from .models import (
    COMPANION_KIND,
    FORMAT_VERSION,
    PROJECTED_MATURITY,
    Handoff,
    HandoffFinding,
)

TOOL_NAME = "startd8-handoff-projector"

LIVE = "LIVE"
PHANTOM = "PHANTOM"
ABSENT = "ABSENT"


def classify_pairs_with(handoff: Handoff, *, base_dir: Optional[Path]) -> str:
    """Classify the ``pairsWith`` (REQ) link (§3). LIVE iff the paired REQ resolves on disk."""
    if not handoff.pairs_with or handoff.pairs_with == "(source req)":
        return ABSENT
    if base_dir is None:
        return PHANTOM
    return LIVE if (base_dir / handoff.pairs_with).is_file() else PHANTOM


def validate_handoff(
    handoff: Handoff,
    *,
    req_fr_ids: Optional[set] = None,
    base_dir: Optional[Path] = None,
) -> List[HandoffFinding]:
    """Validate *handoff* against det-handoff/0.1 §7; return findings (empty = clean).

    Checks: ``formatVersion``; ``companionKind == HANDOFF``; ``maturity`` not inflated; every
    ``buildOrder`` entry references an FR in the paired REQ (when ``req_fr_ids`` supplied); ``base``
    resolves (not the unresolved sentinel); a ``PHANTOM`` prerequisite is surfaced as not-build-ready;
    and ``pairsWith`` resolves LIVE (§3 liveness).
    """
    findings: List[HandoffFinding] = []
    where = handoff.pairs_with or "(handoff)"

    if handoff.format_version != FORMAT_VERSION:
        findings.append(
            HandoffFinding(
                "format-version",
                "error",
                f"formatVersion must be {FORMAT_VERSION!r}, got {handoff.format_version!r}",
                where,
            )
        )
    if handoff.companion_kind != COMPANION_KIND:
        findings.append(
            HandoffFinding(
                "companion-kind",
                "error",
                f"companionKind must be {COMPANION_KIND!r}, got {handoff.companion_kind!r}",
                where,
            )
        )
    if handoff.maturity != PROJECTED_MATURITY:
        findings.append(
            HandoffFinding(
                "maturity-inflation",
                "error",
                f"a projected handoff must be maturity {PROJECTED_MATURITY!r}, got "
                f"{handoff.maturity!r}",
                where,
            )
        )
    if "unresolved" in handoff.base:
        findings.append(
            HandoffFinding(
                "base-unresolved",
                "warning",
                "base sha is unresolved — pass the git base so `base` resolves LIVE (§3)",
                where,
            )
        )
    if req_fr_ids is not None:
        for step in handoff.build_order:
            if step.fr not in req_fr_ids:
                findings.append(
                    HandoffFinding(
                        "phantom-fr",
                        "error",
                        f"buildOrder references {step.fr} which is not an FR in the paired REQ",
                        where,
                    )
                )
    for p in handoff.prerequisites:
        if not p.resolved:
            findings.append(
                HandoffFinding(
                    "phantom-prerequisite",
                    "warning",
                    f"prerequisite `{p.ref}` is PHANTOM (absent) — NOT build-ready (§3)",
                    where,
                )
            )

    if classify_pairs_with(handoff, base_dir=base_dir) != LIVE:
        findings.append(
            HandoffFinding(
                "handoff-liveness",
                "warning",
                f"pairsWith `{handoff.pairs_with}` is not LIVE — a paired census counts LIVE only (§3)",
                where,
            )
        )
    return findings


def findings_to_sarif(
    findings: List[HandoffFinding], *, corpus: Optional[str] = None
) -> dict:
    """Render conformance/liveness findings as SARIF 2.1.0 via the ONE reusable renderer."""
    return render_sarif_from_findings(
        findings, tool_name=TOOL_NAME, tool_version=FORMAT_VERSION, corpus=corpus
    )
