# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Cheap deterministic suspicion triage (FR-4/5/5a).

Ranks features for deep review using **already-computed** post-mortem signals, with
structural-emptiness (`fake_work_stub`, `assembly_delta`, low `disk_quality_score`) deliberately
**outranking** the shallow keyword `requirement_score` (F-R1-1) — otherwise a semantically-empty,
keyword-rich false-PASS would rank low and be skipped.

Escalation budget (FR-5) and the reserved false-PASS quota (FR-5a/R2-S4, independent of the suspect
budget) are applied here; budget-dropped suspects are emitted as `not_reviewed` (no silent caps).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .models import ReportConfig, SelectionReason


@dataclass
class TriageCandidate:
    feature_id: str
    suspicion_score: float
    reason: SelectionReason
    success: bool = False
    verdict: str = ""
    root_cause: str = ""
    generated_files: List[str] = field(default_factory=list)
    not_reviewed_reason: Optional[str] = None


def _suspicion(feat: dict) -> float:
    """Deterministic suspicion in [0, 1]; structural-emptiness weighted above keyword score."""
    score = 0.0
    if not feat.get("success", False):
        score += 0.6  # an outright failure is inherently suspect

    root_cause = str(feat.get("root_cause", "")).lower()
    if "fake_work_stub" in root_cause or "stub" in root_cause:
        score += 0.4  # structural emptiness — the false-PASS signal (outranks keyword)
    if int(feat.get("semantic_error_count", 0) or 0) > 0:
        score += 0.2

    assembly_delta = feat.get("assembly_delta")
    if assembly_delta is not None and float(assembly_delta) > 0.2:
        score += 0.2  # assembly degraded quality vs requirement

    dq = feat.get("disk_quality_score")
    if dq is not None and float(dq) < 0.5:
        score += 0.2

    # Keyword requirement_score contributes only weakly (F-R1-1): it is the signal the SCR exists
    # to backstop, so it must not dominate ranking.
    rq = feat.get("requirement_score")
    if rq is not None and float(rq) < 0.5:
        score += 0.1

    return min(1.0, score)


def _is_stub_adjacent(feat: dict) -> bool:
    return (
        "stub" in str(feat.get("root_cause", "")).lower()
        or int(feat.get("semantic_error_count", 0) or 0) > 0
    )


def triage(features: List[dict], config: ReportConfig) -> List[TriageCandidate]:
    """Rank + select features. Returns candidates for `suspect`, `pass_sample`, and budget-dropped
    `not_reviewed`. Below-threshold PASS features that aren't sampled are simply not returned (they
    are accounted in the report summary as total − reviewed)."""
    scored = [(_suspicion(f), f) for f in features]

    suspects = sorted(
        (f for s, f in scored if s >= config.suspicion_threshold),
        key=_suspicion,
        reverse=True,
    )
    pass_pool = [
        f for s, f in scored
        if s < config.suspicion_threshold and f.get("success", False)
    ]
    # Reserved false-PASS sample: stub-adjacent first, then highest residual suspicion (FR-5a).
    pass_pool.sort(key=lambda f: (_is_stub_adjacent(f), _suspicion(f)), reverse=True)

    out: List[TriageCandidate] = []

    for i, f in enumerate(suspects):
        within_budget = i < config.max_escalations
        out.append(
            TriageCandidate(
                feature_id=str(f.get("feature_id", "")),
                suspicion_score=_suspicion(f),
                reason=SelectionReason.SUSPECT if within_budget else SelectionReason.NOT_REVIEWED,
                success=bool(f.get("success", False)),
                verdict=str(f.get("verdict", "")),
                root_cause=str(f.get("root_cause", "")),
                generated_files=list(f.get("generated_files", []) or []),
                not_reviewed_reason=None if within_budget else "escalation_budget_exhausted",
            )
        )

    for f in pass_pool[: config.reserved_pass_quota]:
        out.append(
            TriageCandidate(
                feature_id=str(f.get("feature_id", "")),
                suspicion_score=_suspicion(f),
                reason=SelectionReason.PASS_SAMPLE,
                success=True,
                verdict=str(f.get("verdict", "")),
                root_cause=str(f.get("root_cause", "")),
                generated_files=list(f.get("generated_files", []) or []),
            )
        )

    return out


def reviewable(candidates: List[TriageCandidate]) -> List[TriageCandidate]:
    """Candidates that actually get an agent call (suspect + pass_sample)."""
    return [c for c in candidates if c.reason != SelectionReason.NOT_REVIEWED]
