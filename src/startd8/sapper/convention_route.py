"""FR-SAP-10 — declaration-surface conformance via the FR-CAR convention authority.

Run ``repair/convention.py`` ``detect_conventions`` over each skeleton at plan time
(spike-validated, requirements §0.7). Catches the *declaration-surface* conformance
violations a typecheck is structurally blind to — ``from flask import`` (framework),
``from app.models import <Table>`` (module-source), ``from sqlalchemy import`` (orm, OQ-6).

Body-internal idioms (``session.query``, ``render_template``) are absent from a skeleton and
remain post-gen FR-CAR's job — the complementary half of the 2×2 (§0.7).

Greenfield fallback (R2-F5): if the convention authority can't be built, emit a single
``UNRESOLVED(authority_absent)`` note rather than crashing.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from startd8.logging_config import get_logger

from .models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    Severity,
    UnresolvedReason,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
)

logger = get_logger(__name__)

# convention_kind (from ConventionDiagnostic) → Sapper AssumptionKind.
_KIND_MAP = {
    "framework": AssumptionKind.FRAMEWORK_IDIOM,
    "orm_idiom": AssumptionKind.ORM_IDIOM,
    "template_idiom": AssumptionKind.FRAMEWORK_IDIOM,
    "module_source": AssumptionKind.MODULE_SOURCE,
}


def run_convention_route(
    skeleton_sources: Dict[str, str],
    *,
    shared_files: Optional[Set[str]] = None,
    authority=None,
) -> List[FrictionFinding]:
    """Detect declaration-surface convention violations across all Python skeletons."""
    shared = shared_files or set()
    try:
        from startd8.repair.convention import (
            build_python_convention_authority,
            detect_conventions,
        )

        auth = authority or build_python_convention_authority()
    except Exception as exc:  # greenfield / authority unavailable → graceful UNRESOLVED
        logger.info("convention authority unavailable: %s", exc)
        return [
            FrictionFinding(
                id="convention::authority_absent",
                kind=AssumptionKind.FRAMEWORK_IDIOM,
                verdict=AssumptionVerdict.UNRESOLVED,
                severity=Severity.LOW,
                avoidable_cost_stage=avoidable_cost_stage(AssumptionKind.FRAMEWORK_IDIOM),
                fingerprint=finding_fingerprint(
                    AssumptionKind.FRAMEWORK_IDIOM, "", "authority"
                ),
                reason=UnresolvedReason.AUTHORITY_ABSENT,
                found="no convention authority for this project (greenfield)",
                validator_class=ValidatorClass.FDE_QUERY,
            )
        ]

    findings: List[FrictionFinding] = []
    for path, src in sorted(skeleton_sources.items()):
        if not path.endswith(".py"):
            continue
        for diag in detect_conventions(src, auth, file=path):
            kind = _KIND_MAP.get(diag.convention_kind, AssumptionKind.FRAMEWORK_IDIOM)
            is_shared = path in shared
            findings.append(
                FrictionFinding(
                    id=f"convention::{path}:{diag.line}:{diag.convention_kind}",
                    kind=kind,
                    verdict=AssumptionVerdict.REFUTED,
                    severity=Severity.HIGH if is_shared else Severity.MEDIUM,
                    avoidable_cost_stage=avoidable_cost_stage(kind, shared_file=is_shared),
                    fingerprint=finding_fingerprint(kind, path, diag.symbol),
                    file=path,
                    line=diag.line,
                    expected=diag.expected,
                    found=diag.symbol,
                    suggested_fix=(diag.expected if diag.safe_fixable else None),
                    context_snippet=_line(src, diag.line),
                    validator_class=ValidatorClass.FDE_QUERY,
                )
            )
    return findings


def _line(src: str, line: int) -> Optional[str]:
    lines = src.splitlines()
    if 0 < line <= len(lines):
        return lines[line - 1].strip() or None
    return None
