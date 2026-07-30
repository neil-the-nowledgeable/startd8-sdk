"""``gen.complete_triplet`` completeness gate (Thanos remediation gap #4, FR-3).

Advisory-first (R1-S6): this module only *reports* a verdict plus the named
evidence it checked. Callers decide whether a failing verdict blocks
anything; nothing here mutates a tree or fails a build by itself.

The gate is one general **bidirectional** rule over data the manifest
already records, keyed by ``path`` (FR-7 / P-B): for each required leg of a
service, a declared manifest row whose ``status`` is not ``"generated"``, or
whose declared ``path`` is absent from disk, blocks a complete verdict for
that leg — and a disk file with no declared manifest row is named as an
undeclared-artifact problem, not silently ignored. A leg must also be
**scoring-visible** (present under ``quality["services"][svc][leg]`` with a
numeric ``score`` key) unless it is exempt via
:data:`TRIPLET_UNSCORED_BY_CONTRACT` (the declared-base SLO variant — #226
FR-5 / P-A: "emitted" does not imply "scoring-visible"). A dated Class-A
suppression can mark a named row complete despite a problem; suppressions
are never silently assumed.

Does **not** import contextcore (NR-G1 / AC-G7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from startd8.observability.affordance_map_consume import TRIPLET_LEGS

# The declared-base SLO row is deliberately produced without a ``score`` key
# (artifact_generator.py::generate_declared_base_slos — "not a scored
# artifact"). It must never be required to be scoring-visible, and it must
# never be treated as satisfying the *primary* slo_definition leg (that
# would be the declared-base substitution the requirements' Non-goals
# forbid).
DECLARED_BASE_SLO_SUFFIX = "-declared-base-slo.yaml"

# Leg -> the manifest path suffix that identifies the *primary*, scored row
# for that leg (as opposed to a sibling declared-base row). Only slo_definition
# currently has a sibling; other legs have exactly one declared row.
_PRIMARY_PATH_EXCLUDES: Dict[str, Tuple[str, ...]] = {
    "slo_definition": (DECLARED_BASE_SLO_SUFFIX,),
}


@dataclass
class SuppressionRecord:
    """A dated Class-A suppression for one (service, leg) row (FR-3)."""

    reason: str
    date: str
    evidence: str

    @property
    def is_valid(self) -> bool:
        return bool(self.reason and self.date and self.evidence)


@dataclass
class TripletLegEvidence:
    """Per-leg gate evidence for one service (FR-3 / R1-F6)."""

    leg: str
    declared_status: Optional[str] = None
    declared_path: Optional[str] = None
    on_disk: Optional[bool] = None
    scored: Optional[bool] = None
    problem: Optional[str] = None
    suppressed: bool = False

    @property
    def complete(self) -> bool:
        return self.problem is None or self.suppressed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leg": self.leg,
            "declared_status": self.declared_status,
            "declared_path": self.declared_path,
            "on_disk": self.on_disk,
            "scored": self.scored,
            "problem": self.problem,
            "suppressed": self.suppressed,
            "complete": self.complete,
        }


@dataclass
class TripletGateResult:
    """Gate verdict for one service (FR-3)."""

    service_id: str
    legs: List[TripletLegEvidence] = field(default_factory=list)
    undeclared_on_disk: List[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.legs) and all(leg.complete for leg in self.legs) and not (
            self.undeclared_on_disk
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "complete": self.complete,
            "legs": [leg.to_dict() for leg in self.legs],
            "undeclared_on_disk": list(self.undeclared_on_disk),
        }


def _find_primary_row(
    rows: Sequence[Mapping[str, Any]], leg: str
) -> Optional[Mapping[str, Any]]:
    """Pick the primary (scored) declared row for ``leg`` among candidates.

    For ``slo_definition`` this deliberately excludes the declared-base
    variant (P-A/P-B) rather than accepting the first row found — a
    first-entry-wins pick is exactly how the declared-base variant could be
    silently substituted for the primary leg.
    """
    excludes = _PRIMARY_PATH_EXCLUDES.get(leg, ())
    for row in rows:
        path = str(row.get("path") or "")
        if excludes and any(path.endswith(sfx) for sfx in excludes):
            continue
        return row
    return None


def _leg_scored(quality: Mapping[str, Any], service_id: str, leg: str) -> Optional[bool]:
    svc_q = (quality.get("services") or {}).get(service_id)
    if not isinstance(svc_q, Mapping):
        return None
    block = svc_q.get(leg)
    if not isinstance(block, Mapping) or "score" not in block:
        return False
    try:
        return float(block.get("score") or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def evaluate_triplet_gate(
    *,
    service_id: str,
    output_dir: Path,
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    legs: Sequence[str] = TRIPLET_LEGS,
    suppressions: Optional[Mapping[Tuple[str, str], SuppressionRecord]] = None,
) -> TripletGateResult:
    """Evaluate the FR-3 completeness gate for one service.

    ``manifest`` is the parsed ``observability-manifest.yaml`` dict (with an
    ``artifacts`` list of ``{type, service, path, status}`` rows). ``quality``
    is the parsed ``observability-quality.json`` dict. Disk state is read
    from ``output_dir`` — pass the locked or a ``/tmp`` dogfood root, never a
    path outside those two contracts.
    """
    suppressions = suppressions or {}
    rows_by_type: Dict[str, List[Mapping[str, Any]]] = {}
    for row in manifest.get("artifacts") or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("service") != service_id:
            continue
        rows_by_type.setdefault(str(row.get("type")), []).append(row)

    result = TripletGateResult(service_id=service_id)
    for leg in legs:
        row = _find_primary_row(rows_by_type.get(leg, []), leg)
        ev = TripletLegEvidence(leg=leg)
        if row is None:
            ev.problem = "declared_row_missing"
        else:
            ev.declared_status = str(row.get("status") or "")
            ev.declared_path = str(row.get("path") or "") or None
            if ev.declared_status != "generated":
                ev.problem = f"declared_status_{ev.declared_status or 'unknown'}"
            elif ev.declared_path:
                dest = output_dir / ev.declared_path
                ev.on_disk = dest.is_file()
                if not ev.on_disk:
                    ev.problem = "path_absent_from_disk"
            if ev.problem is None:
                scored = _leg_scored(quality, service_id, leg)
                ev.scored = scored
                if not scored:
                    ev.problem = "not_scoring_visible"
        if ev.problem is not None:
            supp = suppressions.get((service_id, leg))
            if supp is not None and supp.is_valid:
                ev.suppressed = True
        result.legs.append(ev)

    # Bidirectional: a disk file under the leg-relevant directories with no
    # declared manifest row at all is named, not silently ignored (FR-3).
    # Checked against an explicit candidate set (never an open `{service_id}-*`
    # glob): Thanos service ids overlap by prefix (``query`` / ``query-frontend``),
    # so a glob would misreport query-frontend's own files as undeclared for
    # ``query``.
    declared_paths = {
        str(row.get("path"))
        for rows in rows_by_type.values()
        for row in rows
        if row.get("path")
    }
    candidate_rels = [
        f"alerts/{service_id}-alerts.yaml",
        f"slos/{service_id}-slo.yaml",
        f"slos/{service_id}{DECLARED_BASE_SLO_SUFFIX}",
        f"dashboards/{service_id}-dashboard-spec.yaml",
    ]
    for rel in candidate_rels:
        if (output_dir / rel).is_file() and rel not in declared_paths:
            result.undeclared_on_disk.append(rel)

    return result


def evaluate_triplet_gate_for_services(
    *,
    service_ids: Sequence[str],
    output_dir: Path,
    manifest: Mapping[str, Any],
    quality: Mapping[str, Any],
    legs: Sequence[str] = TRIPLET_LEGS,
    suppressions: Optional[Mapping[Tuple[str, str], SuppressionRecord]] = None,
) -> Dict[str, TripletGateResult]:
    """Evaluate the gate across every eligible service (report-only, FR-3)."""
    return {
        sid: evaluate_triplet_gate(
            service_id=sid,
            output_dir=output_dir,
            manifest=manifest,
            quality=quality,
            legs=legs,
            suppressions=suppressions,
        )
        for sid in service_ids
    }


def eligible_triplet_denominator(
    *,
    all_element_ids: Sequence[str],
    excluded: Mapping[str, str],
) -> Tuple[List[str], List[Dict[str, str]]]:
    """Split elements into the eligible denominator and named exclusions.

    ``excluded`` maps ``element_id -> locus_reason`` for elements that are
    not triplet-eligible (``no_source_locus`` per the existing planning-time
    locus rule — gap #4 FR-2, Step 4). Eligibility is never a per-project
    name allowlist: the caller supplies the locus-derived exclusion set, and
    excluded elements are kept out of both the numerator and the
    denominator, never folded into either.
    """
    eligible = [e for e in all_element_ids if e not in excluded]
    excluded_list = [
        {"element_id": eid, "locus_reason": reason}
        for eid, reason in excluded.items()
        if eid in all_element_ids
    ]
    return eligible, excluded_list


__all__ = [
    "DECLARED_BASE_SLO_SUFFIX",
    "SuppressionRecord",
    "TripletLegEvidence",
    "TripletGateResult",
    "evaluate_triplet_gate",
    "evaluate_triplet_gate_for_services",
    "eligible_triplet_denominator",
]
