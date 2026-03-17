"""Shared complexity tier classifier.

Port of ``_classify_complexity_tier()`` from Artisan's
``context_seed_handlers.py``, made subsystem-independent.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List

from startd8.logging_config import get_logger

from .models import (
    ClassificationResult,
    ComplexityRoutingConfig,
    ComplexityTier,
    TaskComplexitySignals,
)

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
) -> ClassificationResult:
    """Classify a task into a complexity tier.

    Pure function, stateless, deterministic.  Evaluation order:

    1. COMPLEX triggers — any single trigger fires.
    2. SIMPLE eligibility — all conditions must pass.
    3. Default: COMPLEX (was MODERATE before AC-R3-R7).

    Args:
        signals: Complexity signals for the task.
        config: Threshold configuration.  Uses defaults when ``None``.

    Returns:
        ``ClassificationResult`` carrying tier, reason, and the original
        signals.  Supports tuple unpacking for backward compatibility::

            tier, reason = classify_tier(signals)  # still works
    """
    cfg = config or ComplexityRoutingConfig()

    # --- Non-Python early routing ---
    # Files for supported languages (Go, Node.js, Java) use the full
    # complexity analysis below.  Non-supported languages (HTML, Dockerfile,
    # YAML, requirements.txt, etc.) route by LOC only.
    # Run-013 showed an HTML template costing $0.59 via cloud fallback — it
    # should have been TRIVIAL ($0.00).
    _is_supported_language = False
    if signals.file_extension and signals.file_extension != ".py":
        try:
            from startd8.languages import LanguageRegistry
            _profile = LanguageRegistry.get_by_extension(signals.file_extension)
            _is_supported_language = _profile is not None
        except (ImportError, AttributeError):
            pass

    if signals.file_extension and signals.file_extension != ".py" and not _is_supported_language:
        if signals.estimated_loc <= cfg.non_python_trivial_loc_max:
            return _emit(
                ComplexityTier.TRIVIAL,
                f"non-Python file ({signals.file_extension}) "
                f"below trivial LOC threshold ({signals.estimated_loc} <= {cfg.non_python_trivial_loc_max})",
                signals,
            )
        if signals.estimated_loc <= cfg.non_python_simple_loc_max:
            return _emit(
                ComplexityTier.SIMPLE,
                f"non-Python file ({signals.file_extension}) "
                f"below simple LOC threshold ({signals.estimated_loc} <= {cfg.non_python_simple_loc_max})",
                signals,
            )
        return _emit(
            ComplexityTier.COMPLEX,
            f"non-Python file ({signals.file_extension}) "
            f"above simple LOC threshold ({signals.estimated_loc} > {cfg.non_python_simple_loc_max})",
            signals,
        )

    # --- COMPLEX: any trigger fires ---
    if signals.blast_radius > cfg.blast_radius_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"blast_radius {signals.blast_radius} > {cfg.blast_radius_complex_threshold}",
            signals,
        )
    if signals.has_dynamic_dispatch:
        return _emit(ComplexityTier.COMPLEX, "has_dynamic_dispatch", signals)
    if (
        signals.edit_mode == "edit"
        and signals.caller_count > cfg.caller_count_complex_threshold
    ):
        return _emit(
            ComplexityTier.COMPLEX,
            f"edit mode with caller_count {signals.caller_count} > {cfg.caller_count_complex_threshold}",
            signals,
        )
    if signals.mro_depth > cfg.mro_depth_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"mro_depth {signals.mro_depth} > {cfg.mro_depth_complex_threshold}",
            signals,
        )
    if signals.unresolved_call_count > cfg.unresolved_calls_complex_threshold:
        return _emit(
            ComplexityTier.COMPLEX,
            f"unresolved_call_count {signals.unresolved_call_count} > {cfg.unresolved_calls_complex_threshold}",
            signals,
        )
    if signals.estimated_loc > cfg.loc_complex_min:
        return _emit(
            ComplexityTier.COMPLEX,
            f"estimated_loc {signals.estimated_loc} > {cfg.loc_complex_min}",
            signals,
        )
    if signals.target_file_count > 1 and signals.has_cross_file_edges:
        return _emit(ComplexityTier.COMPLEX, "multi-file with cross-file edges", signals)

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
        return _emit(ComplexityTier.SIMPLE, "all SIMPLE conditions met", signals)

    # --- Relaxed SIMPLE (Kaizen run-017): create-mode elements with small
    # blast radius that only fail SIMPLE on manifest_coverage or blast_radius.
    if (
        cfg.simple_relaxed_enabled
        and signals.edit_mode == "create"
        and signals.blast_radius <= cfg.simple_relaxed_blast_radius_max
        and signals.caller_count == 0
        and not signals.has_dynamic_dispatch
        and signals.estimated_loc < cfg.loc_simple_max
        and signals.target_file_count == 1
    ):
        return _emit(
            ComplexityTier.SIMPLE,
            f"relaxed SIMPLE: create-mode, blast_radius={signals.blast_radius} "
            f"<= {cfg.simple_relaxed_blast_radius_max}",
            signals,
        )

    # --- Default: COMPLEX (AC-R3-R7) ---
    # Changed from MODERATE → COMPLEX to collapse the MODERATE tier.
    # MODERATE existed to justify the decomposition pipeline (decomposer +
    # splicer + per-element repair = ~2,483 lines of compensatory code).
    # With file-whole thresholds raised to 30 elements / 300 LOC (AC-R3-R4),
    # files below those thresholds use file-whole generation.  Files above
    # them route to cloud (LeadContractor) — more expensive per-call but
    # eliminates the decomposition failure modes.
    return _emit(ComplexityTier.COMPLEX, "default (no COMPLEX triggers, SIMPLE conditions not fully met)", signals)


def _emit(
    tier: ComplexityTier,
    reason: str,
    signals: TaskComplexitySignals,
) -> ClassificationResult:
    """Log the classification and record OTel metric if available."""
    logger.info("Classified tier=%s reason=%s", tier.value, reason)
    if _tier_histogram is not None:
        try:
            _tier_histogram.record(1, attributes={"tier": tier.value})
        except Exception:
            logger.debug("Failed to record OTel tier histogram", exc_info=True)
    return ClassificationResult(tier=tier, reason=reason, signals=signals)


def log_tier_distribution(tiers: List[ComplexityTier]) -> Dict[str, int]:
    """Log a summary of tier distribution from a batch run.

    Args:
        tiers: List of tiers from a workflow run.

    Returns:
        Dict mapping tier name to count.
    """
    counts: Dict[str, int] = dict(Counter(t.value for t in tiers))
    logger.info(
        "Tier distribution: %s (total=%d)",
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        len(tiers),
    )
    return counts
