"""Query-specific complexity tier classifier — REQ-QP-301.

Pure function, follows the ``complexity/classifier.py`` pattern.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from startd8.complexity.models import ComplexityTier
from startd8.logging_config import get_logger

from .models import OperationType, QueryClassificationResult, QuerySignals

logger = get_logger(__name__)


@dataclass
class QueryRoutingConfig:
    """Threshold configuration for query complexity classification."""

    table_count_complex_threshold: int = 4
    enabled: bool = True


def classify_query_tier(
    signals: QuerySignals,
    config: Optional[QueryRoutingConfig] = None,
    *,
    operation_type: Optional[OperationType] = None,
) -> QueryClassificationResult:
    """Classify a query work item into a complexity tier.

    Evaluation order (REQ-QP-301):
    1. prior_injection_failure -> force minimum MODERATE
    2. COMPLEX triggers: table_count > 4, has_dynamic_columns,
       has_subquery and has_aggregate
    3. TRIVIAL: operation_type == health_check
    4. SIMPLE: table_count <= 2, join_count <= 1, no subquery/transaction/dynamic_columns
    5. Default: MODERATE

    Args:
        signals: Query classification signals.
        config: Optional threshold configuration.
        operation_type: Query operation type (for TRIVIAL health_check routing).

    Returns:
        QueryClassificationResult with tier, reason, signals.
    """
    cfg = config or QueryRoutingConfig()

    forced_minimum: Optional[ComplexityTier] = None

    # --- Rule 1: Prior injection failure forces minimum MODERATE ---
    if signals.prior_injection_failure:
        forced_minimum = ComplexityTier.MODERATE

    # --- Rule 2: COMPLEX triggers ---
    if signals.table_count > cfg.table_count_complex_threshold:
        tier = ComplexityTier.COMPLEX
        reason = (
            f"table_count {signals.table_count} > "
            f"{cfg.table_count_complex_threshold}"
        )
        return _emit(tier, reason, signals, forced_minimum)

    if signals.has_dynamic_columns:
        return _emit(
            ComplexityTier.COMPLEX, "has_dynamic_columns", signals, forced_minimum
        )

    if signals.has_subquery and signals.has_aggregate:
        return _emit(
            ComplexityTier.COMPLEX,
            "has_subquery and has_aggregate",
            signals,
            forced_minimum,
        )

    # --- Rule 3: TRIVIAL for health checks ---
    if operation_type == OperationType.HEALTH_CHECK:
        tier = ComplexityTier.TRIVIAL
        if forced_minimum is not None and _tier_rank(forced_minimum) > _tier_rank(tier):
            return _emit(forced_minimum, f"health_check forced up to {forced_minimum.value}", signals, forced_minimum)
        return _emit(tier, "health_check operation", signals, forced_minimum)

    # --- Rule 4: SIMPLE eligibility ---
    if (
        signals.table_count <= 2
        and signals.join_count <= 1
        and not signals.has_subquery
        and not signals.has_transaction
        and not signals.has_dynamic_columns
    ):
        tier = ComplexityTier.SIMPLE
        if forced_minimum is not None and _tier_rank(forced_minimum) > _tier_rank(tier):
            return _emit(forced_minimum, f"SIMPLE forced up to {forced_minimum.value} (prior injection)", signals, forced_minimum)
        return _emit(tier, "all SIMPLE conditions met", signals, forced_minimum)

    # --- Rule 5: Default MODERATE ---
    tier = ComplexityTier.MODERATE
    if forced_minimum is not None and _tier_rank(forced_minimum) > _tier_rank(tier):
        tier = forced_minimum
    return _emit(tier, "default MODERATE", signals, forced_minimum)


_TIER_RANK = {
    ComplexityTier.TRIVIAL: 0,
    ComplexityTier.SIMPLE: 1,
    ComplexityTier.MODERATE: 2,
    ComplexityTier.COMPLEX: 3,
}


def _tier_rank(tier: ComplexityTier) -> int:
    """Return numeric rank for tier comparison."""
    return _TIER_RANK.get(tier, 2)


def _emit(
    tier: ComplexityTier,
    reason: str,
    signals: QuerySignals,
    forced_minimum: Optional[ComplexityTier],
) -> QueryClassificationResult:
    """Log classification and return result."""
    logger.info("Query classified tier=%s reason=%s", tier.value, reason)
    return QueryClassificationResult(
        tier=tier,
        reason=reason,
        signals=signals,
        forced_minimum=forced_minimum,
    )
