"""Shared complexity tier classifier.

Port of ``_classify_complexity_tier()`` from Artisan's
``context_seed_handlers.py``, made subsystem-independent.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

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
    *,
    exemplar_registry: Any = None,
    fingerprint: Any = None,
) -> ClassificationResult:
    """Classify a task into a complexity tier.

    Evaluation order:

    1. COMPLEX triggers — any single trigger fires.
    2. SIMPLE eligibility — all conditions must pass.
    3. Default: COMPLEX (was MODERATE before AC-R3-R7).
    4. Exemplar-informed downgrade — if a high-maturity exemplar matches,
       the tier is downgraded by one step (Layer 1).

    Args:
        signals: Complexity signals for the task.
        config: Threshold configuration.  Uses defaults when ``None``.
        exemplar_registry: Optional ``ExemplarRegistry`` instance.  Passed
            as ``Any`` to avoid import coupling.
        fingerprint: Optional ``ConfigFingerprint`` for the current task.

    Returns:
        ``ClassificationResult`` carrying tier, reason, and the original
        signals.  Supports tuple unpacking for backward compatibility::

            tier, reason = classify_tier(signals)  # still works
    """
    result = _classify_tier_core(signals, config)

    # --- Layer 1: Exemplar-informed tier downgrade ---
    if exemplar_registry is not None and fingerprint is not None:
        result = _apply_exemplar_downgrade(result, exemplar_registry, fingerprint)

    return result


# Ordered from highest to lowest; used for one-step downgrade.
_TIER_ORDER: list[ComplexityTier] = [
    ComplexityTier.COMPLEX,
    ComplexityTier.MODERATE,
    ComplexityTier.SIMPLE,
    ComplexityTier.TRIVIAL,
]


def _apply_exemplar_downgrade(
    result: ClassificationResult,
    exemplar_registry: Any,
    fingerprint: Any,
) -> ClassificationResult:
    """Downgrade tier by one step if a high-maturity exemplar matches.

    Qualifying criteria (REQ-PEP-100 Layer 1):
    - ``maturity >= 3`` (invariant or template)
    - ``disk_quality_score >= 1.0`` (perfect disk compliance)

    Cap: one step only.  TRIVIAL stays TRIVIAL.
    """
    try:
        match = exemplar_registry.find_best_match(fingerprint)
        if match is None:
            return result
        if match.maturity < 3 or match.scores.disk_quality_score < 1.0:
            return result
    except Exception:
        logger.debug("Exemplar lookup failed (non-fatal)", exc_info=True)
        return result

    original_tier = result.tier
    # Find current position and move one step down (toward TRIVIAL)
    try:
        idx = _TIER_ORDER.index(original_tier)
    except ValueError:
        return result

    if idx >= len(_TIER_ORDER) - 1:
        # Already at the lowest tier (TRIVIAL) — no downgrade
        return result

    new_tier = _TIER_ORDER[idx + 1]
    new_reason = (
        f"exemplar downgrade from {original_tier.value} "
        f"(exemplar {match.id}, maturity={match.maturity}, "
        f"score={match.scores.disk_quality_score:.2f})"
    )
    logger.info(
        "Exemplar downgrade: %s -> %s (%s)",
        original_tier.value, new_tier.value, match.id,
    )
    return ClassificationResult(
        tier=new_tier,
        reason=new_reason,
        signals=result.signals,
        exemplar_override=match.id,
    )


def _classify_tier_core(
    signals: TaskComplexitySignals,
    config: ComplexityRoutingConfig | None = None,
) -> ClassificationResult:
    """Core classification logic (extracted for exemplar wrapping)."""
    cfg = config or ComplexityRoutingConfig()

    # --- Non-Python early routing ---
    # Files for supported languages (Go, Node.js, Java, Vue, …) use the full
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

    # --- Security-sensitive floor (Anzen SP-PL-002): never below MODERATE ---
    if signals.security_sensitive:
        return _emit(
            ComplexityTier.MODERATE,
            "security_sensitive — minimum MODERATE tier (Anzen)",
            signals,
        )

    # --- RUN-007 FR-7: under-specified (empty-fillable, non-registry) spec must
    # not route to the no-LLM SIMPLE tier — that path ships an unfilled stem-name
    # stub. Route to the real-LLM path instead. Fires only when fillability is
    # known False; the Step-2 emission gate is the authoritative suppressor and
    # this aligns the classifier with it. ---
    if signals.has_fillable_elements is False:
        return _emit(
            ComplexityTier.COMPLEX,
            "empty-fillable spec — under-specified, not SIMPLE (FR-7)",
            signals,
        )

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
    # them route to cloud (Primary contractor) — more expensive per-call but
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
