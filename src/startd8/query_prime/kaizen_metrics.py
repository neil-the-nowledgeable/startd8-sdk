"""Kaizen metrics for Query Prime — REQ-KQP-100 through REQ-KQP-302.

Layer 1: Verification report aggregation (build_verification_report).
Layer 3: Per-work-item quality scoring (compute_query_security_score).
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

from .models import (
    QueryResult,
    SecurityCheckType,
    SecurityVerdict,
)

logger = get_logger(__name__)

# REQ-KQP-302: T3 first_pass_rate threshold for auto-escalation warning.
_T3_FIRST_PASS_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# L3: Scoring weights (REQ-KQP-300)
# ---------------------------------------------------------------------------


@dataclass
class QueryScoreWeights:
    """Configurable weights for query security scoring.

    Projects with no credential handling can zero out credential_safety.
    Weights must sum to 1.0 for meaningful scores.
    """

    parameterization: float = 0.35
    credential_safety: float = 0.25
    lifecycle_compliance: float = 0.15
    verification_pass: float = 0.15
    tier_efficiency: float = 0.10


# ---------------------------------------------------------------------------
# L3: Per-work-item scoring (REQ-KQP-301, 302)
# ---------------------------------------------------------------------------


def compute_query_security_score(
    result: QueryResult,
    weights: Optional[QueryScoreWeights] = None,
) -> float:
    """Compute a [0.0, 1.0] quality score for a single QueryResult.

    Short-circuits to 0.0 if any injection finding is present.

    Args:
        result: A single QueryResult from engine processing.
        weights: Optional custom scoring weights.

    Returns:
        Score in [0.0, 1.0].
    """
    w = weights or QueryScoreWeights()

    if result.verification is None:
        return 0.0

    findings = result.verification.findings

    # Short-circuit: injection = 0.0
    has_injection = any(
        f.check_type == SecurityCheckType.INJECTION and f.severity == "error"
        for f in findings
    )
    if has_injection:
        return 0.0

    # Component scores (each 0.0 or 1.0 for binary checks)
    param_score = 1.0 if not any(
        f.check_type == SecurityCheckType.INJECTION for f in findings
    ) else 0.0

    cred_score = 1.0 if not any(
        f.check_type == SecurityCheckType.CREDENTIAL_LEAKAGE for f in findings
    ) else 0.0

    lifecycle_score = 1.0 if not any(
        f.check_type == SecurityCheckType.LIFECYCLE for f in findings
    ) else 0.0

    verification_score = 1.0 if result.verification.verdict != SecurityVerdict.FAIL else 0.0

    # Tier efficiency: 1.0 if no escalations, degrades with each
    tier_score = max(0.0, 1.0 - (result.escalations * 0.33))

    score = (
        w.parameterization * param_score
        + w.credential_safety * cred_score
        + w.lifecycle_compliance * lifecycle_score
        + w.verification_pass * verification_score
        + w.tier_efficiency * tier_score
    )
    return round(min(1.0, max(0.0, score)), 4)


# ---------------------------------------------------------------------------
# L1: Verification report (REQ-KQP-100, 101, 102)
# ---------------------------------------------------------------------------


def build_verification_report(
    results: List[QueryResult],
    run_id: str,
    run_timestamp: Optional[str] = None,
    *,
    weights: Optional[QueryScoreWeights] = None,
) -> Dict[str, Any]:
    """Aggregate per-work-item QueryResults into query-security-metrics.json schema.

    Args:
        results: List of QueryResult from engine processing.
        run_id: Unique run identifier.
        run_timestamp: ISO timestamp; defaults to now.
        weights: Optional custom scoring weights.

    Returns:
        Dict suitable for JSON serialization as query-security-metrics.json.
    """
    ts = run_timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    w = weights or QueryScoreWeights()

    # Per-item details
    items: List[Dict[str, Any]] = []
    scores: List[float] = []
    by_database: Dict[str, List[float]] = defaultdict(list)
    by_tier: Dict[str, _TierStats] = defaultdict(_TierStats)
    total_cost = 0.0
    total_injection = 0
    total_credential = 0
    total_lifecycle = 0

    for r in results:
        score = compute_query_security_score(r, w)
        scores.append(score)
        total_cost += r.cost_usd

        # Classify findings
        n_injection = 0
        n_credential = 0
        n_lifecycle = 0
        db_name = "unknown"
        if r.verification:
            for f in r.verification.findings:
                if f.check_type == SecurityCheckType.INJECTION:
                    n_injection += 1
                elif f.check_type == SecurityCheckType.CREDENTIAL_LEAKAGE:
                    n_credential += 1
                elif f.check_type == SecurityCheckType.LIFECYCLE:
                    n_lifecycle += 1
                if f.database:
                    db_name = f.database

        total_injection += n_injection
        total_credential += n_credential
        total_lifecycle += n_lifecycle

        # Tier tracking
        tier_name = r.tier_used.value if r.tier_used else "unknown"
        tier_stats = by_tier[tier_name]
        tier_stats.count += 1
        tier_stats.scores.append(score)
        if r.verification and r.verification.verdict != SecurityVerdict.FAIL:
            tier_stats.first_pass += 1
        if r.escalations > 0:
            tier_stats.escalated += 1

        by_database[db_name].append(score)

        item_dict: Dict[str, Any] = {
            "work_item_id": r.work_item_id,
            "score": score,
            "tier_used": tier_name,
            "model_used": r.model_used,
            "cost_usd": round(r.cost_usd, 6),
            "escalations": r.escalations,
            "injection_findings": n_injection,
            "credential_findings": n_credential,
            "lifecycle_findings": n_lifecycle,
        }
        if r.verification:
            item_dict["verdict"] = r.verification.verdict.value
            # REQ-KQP-102: verification pipeline timing
            if r.verification.verification_timing_ms:
                item_dict["verification_timing_ms"] = r.verification.verification_timing_ms
            item_dict["false_positives_suppressed"] = r.verification.false_positives_suppressed
        items.append(item_dict)

    # Aggregates
    mean_score = sum(scores) / len(scores) if scores else 0.0
    pass_count = sum(1 for s in scores if s >= 0.8)

    db_summary = {
        db: {
            "count": len(db_scores),
            "mean_score": round(sum(db_scores) / len(db_scores), 4),
        }
        for db, db_scores in by_database.items()
    }

    tier_summary = {}
    for tier_name, stats in by_tier.items():
        tier_summary[tier_name] = {
            "count": stats.count,
            "mean_score": round(sum(stats.scores) / len(stats.scores), 4) if stats.scores else 0.0,
            "first_pass_rate": round(stats.first_pass / stats.count, 4) if stats.count else 0.0,
            "escalation_rate": round(stats.escalated / stats.count, 4) if stats.count else 0.0,
        }

    # REQ-KQP-302: threshold alert for T3 insufficiency
    t3_stats = tier_summary.get("simple") or tier_summary.get("SIMPLE")
    if t3_stats and t3_stats["first_pass_rate"] < _T3_FIRST_PASS_THRESHOLD:
        logger.warning(
            "Kaizen KQP-302: T3 first_pass_rate (%.2f) below %.2f threshold "
            "— auto-escalation to T2 is warranted for SIMPLE-tier queries",
            t3_stats["first_pass_rate"], _T3_FIRST_PASS_THRESHOLD,
        )

    return {
        "run_id": run_id,
        "timestamp": ts,
        "total_work_items": len(results),
        "mean_score": round(mean_score, 4),
        "pass_rate": round(pass_count / len(results), 4) if results else 0.0,
        "total_cost_usd": round(total_cost, 6),
        "injection_total": total_injection,
        "credential_total": total_credential,
        "lifecycle_total": total_lifecycle,
        "by_database": dict(db_summary),
        "by_tier": tier_summary,
        "items": items,
    }


@dataclass
class _TierStats:
    """Internal accumulator for per-tier statistics."""

    count: int = 0
    scores: List[float] = field(default_factory=list)
    first_pass: int = 0
    escalated: int = 0
