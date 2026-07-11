# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Deterministic semantic-compliance scoring (FR-8).

A fixed formula so two implementers produce identical scores on identical inputs (R1-F2):

    score = verdict_base × confidence − Σ severity_weight(issue)      (clamped to [0, 1])

``inconclusive`` verdicts return ``None`` — they are **excluded** from the run aggregate
denominator (neutral), not scored as 0, so missing-text/parse failures do not crash the
aggregate (R3-F3).
"""

from __future__ import annotations

from typing import Iterable, List, Optional

from .models import VerificationIssue, Verdict

# Severity → score penalty. Critical alone is enough to zero a high-confidence pass.
_SEVERITY_WEIGHTS = {
    "critical": 0.5,
    "high": 0.25,
    "medium": 0.1,
    "low": 0.03,
}

_VERDICT_BASE = {
    Verdict.PASS: 1.0,
    Verdict.FAIL: 0.0,
    Verdict.INCONCLUSIVE: None,
}


def severity_weight(severity: str) -> float:
    """Penalty weight for an issue severity (unknown → medium)."""
    return _SEVERITY_WEIGHTS.get(str(severity).lower(), _SEVERITY_WEIGHTS["medium"])


def compute_compliance_score(
    verdict: Verdict,
    confidence: float,
    issues: Iterable[VerificationIssue] = (),
) -> Optional[float]:
    """Per-feature ``semantic_compliance_score`` in [0, 1], or ``None`` for ``inconclusive``."""
    base = _VERDICT_BASE.get(verdict)
    if base is None:  # inconclusive → excluded from the aggregate (R3-F3)
        return None
    confidence = max(0.0, min(1.0, float(confidence)))
    penalty = sum(severity_weight(i.severity) for i in issues)
    return max(0.0, min(1.0, base * confidence - penalty))


def aggregate_score(scores: Iterable[Optional[float]]) -> Optional[float]:
    """Mean over **conclusive** features only; ``None`` when nothing was conclusively scored."""
    conclusive: List[float] = [s for s in scores if s is not None]
    if not conclusive:
        return None
    return sum(conclusive) / len(conclusive)
