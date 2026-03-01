"""Shared complexity tier classifier.

Port of ``_classify_complexity_tier()`` from Artisan's
``context_seed_handlers.py``, made subsystem-independent.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from startd8.logging_config import get_logger

from .models import ComplexityRoutingConfig, ComplexityTier, TaskComplexitySignals

logger = get_logger(__name__)

# Optional OTel histogram for tier distribution tracking.
_tier_histogram = None
try:
    from opentelemetry import metrics as _otel_metrics

    _meter = _otel_metrics.get_meter("startd8.complexity")
    _tier_histogram = _meter.create_histogram(
        name="complexity.tier_distribution",
        description="Distribution of complexity tier classifications",
        unit="1",
    )
except Exception:  # pragma: no cover – OTel may not be installed
    pass


def classify_tier(
    signals: TaskComplexitySignals,
    config: ComplexityRoutingConfig | None = None,
) -> Tuple[ComplexityTier, str]:
    """Classify a task into a complexity tier.

    Pure function, stateless, deterministic.  Evaluation order:

    1. COMPLEX triggers — any single trigger fires.
    2. SIMPLE eligibility — all conditions must pass.
    3. Default: MODERATE.

    Args:
        signals: Complexity signals for the task.
        config: Threshold configuration.  Uses defaults when ``None``.

    Returns:
        ``(tier, reason)`` where *reason* is a human-readable string
        listing which triggers or conditions determined the tier.
    """
    cfg = config or ComplexityRoutingConfig()

    # --- COMPLEX: any trigger fires ---
    if signals.blast_radius > cfg.blast_radius_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"blast_radius {signals.blast_radius} > {cfg.blast_radius_complex_threshold}",
        )
    if signals.has_dynamic_dispatch:
        return _emit(ComplexityTier.COMPLEX, "has_dynamic_dispatch")
    if (
        signals.edit_mode == "edit"
        and signals.caller_count > cfg.caller_count_complex_threshold
    ):
        return _emit(
            ComplexityTier.COMPLEX,
            f"edit mode with caller_count {signals.caller_count} > {cfg.caller_count_complex_threshold}",
        )
    if signals.mro_depth > cfg.mro_depth_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"mro_depth {signals.mro_depth} > {cfg.mro_depth_complex_threshold}",
        )
    if signals.unresolved_call_count > cfg.unresolved_calls_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"unresolved_call_count {signals.unresolved_call_count} > {cfg.unresolved_calls_complex_threshold}",
        )
    if signals.estimated_loc > cfg.loc_complex_min:
        return _emit(
            ComplexityTier.COMPLEX,
            f"estimated_loc {signals.estimated_loc} > {cfg.loc_complex_min}",
        )
    if signals.target_file_count > 1 and signals.has_cross_file_edges:
        return _emit(ComplexityTier.COMPLEX, "multi-file with cross-file edges")

    # --- SIMPLE: all must pass ---
    if (
        signals.manifest_coverage == "full"
        and signals.blast_radius == 0
        and signals.edit_mode == "create"
        and signals.caller_count == 0
        and not signals.has_dynamic_dispatch
        and signals.estimated_loc < cfg.loc_simple_max
        and signals.target_file_count == 1
    ):
        return _emit(ComplexityTier.SIMPLE, "all SIMPLE conditions met")

    # --- Default: MODERATE ---
    return _emit(ComplexityTier.MODERATE, "default (no COMPLEX triggers, SIMPLE conditions not fully met)")


def _emit(tier: ComplexityTier, reason: str) -> Tuple[ComplexityTier, str]:
    """Log the classification and record OTel metric if available."""
    logger.info("Classified tier=%s reason=%s", tier.value, reason)
    if _tier_histogram is not None:
        try:
            _tier_histogram.record(1, attributes={"tier": tier.value})
        except Exception:
            pass
    return tier, reason


def log_tier_distribution(tiers: List[ComplexityTier]) -> Dict[str, int]:
    """Log a summary of tier distribution from a batch run.

    Args:
        tiers: List of tiers from a workflow run.

    Returns:
        Dict mapping tier name to count.
    """
    counts: Dict[str, int] = {}
    for t in tiers:
        counts[t.value] = counts.get(t.value, 0) + 1
    logger.info(
        "Tier distribution: %s (total=%d)",
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        len(tiers),
    )
    return counts
