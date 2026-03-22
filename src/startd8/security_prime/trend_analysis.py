"""Cross-run security posture trend analysis — REQ-KSP-400 through REQ-KSP-402.

Reads archived ``security-gate-metrics.json`` files and computes slopes
for gate pass rate, mean score, injection findings, and OWASP coverage.

Uses ``utils/trend_math.py:linear_slope()`` for OLS regression.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger
from startd8.utils.trend_math import linear_slope

logger = get_logger(__name__)


def compute_security_posture_trend(run_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute trend slopes across archived security gate metrics.

    Args:
        run_metrics: List of security-gate-metrics.json dicts, ordered
            oldest to newest.

    Returns:
        Dict with slopes for key metrics and an interpretation.
    """
    if len(run_metrics) < 2:
        return {"status": "insufficient_data", "runs_available": len(run_metrics)}

    pass_rates = [r.get("gate_pass_rate", 0.0) for r in run_metrics]
    mean_scores = [r.get("mean_score", 0.0) for r in run_metrics]
    injections = [
        float(r.get("findings_by_type", {}).get("injection", 0))
        for r in run_metrics
    ]

    # OWASP coverage progression (if available)
    owasp_coverages: List[float] = []
    for r in run_metrics:
        owasp = r.get("owasp_coverage", {})
        if "coverage_percentage" in owasp:
            owasp_coverages.append(owasp["coverage_percentage"])

    logger.info(
        "Security posture trend: %d runs, pass_rate_slope=%s, injection_slope=%s",
        len(run_metrics),
        linear_slope(pass_rates),
        linear_slope(injections),
    )

    return {
        "status": "ok",
        "runs_analyzed": len(run_metrics),
        "pass_rate_slope": linear_slope(pass_rates),
        "mean_score_slope": linear_slope(mean_scores),
        "injection_slope": linear_slope(injections),
        "owasp_coverage_slope": linear_slope(owasp_coverages) if len(owasp_coverages) >= 2 else None,
        "latest_pass_rate": pass_rates[-1],
        "latest_mean_score": mean_scores[-1],
        "trajectory": assess_pass_rate_trajectory(pass_rates),
    }


def assess_pass_rate_trajectory(pass_rates: List[float]) -> Dict[str, Any]:
    """Threshold alerts for gate pass rate progression.

    Args:
        pass_rates: Ordered list of gate pass rates.

    Returns:
        Dict with alert_level (INFO/WARNING/ERROR), description,
        and trend direction.
    """
    if len(pass_rates) < 2:
        return {"alert_level": "INFO", "description": "Insufficient data", "trend": "unknown"}

    slope = linear_slope(pass_rates)
    latest = pass_rates[-1]

    # Count consecutive trailing values below 0.80
    consecutive_below = 0
    for rate in reversed(pass_rates):
        if rate < 0.80:
            consecutive_below += 1
        else:
            break

    if consecutive_below >= 3:
        logger.error(
            "Sustained low gate pass rate: below 80%% for %d consecutive runs",
            consecutive_below,
        )
        return {
            "alert_level": "ERROR",
            "description": f"Gate pass rate below 80% for {consecutive_below} consecutive runs (latest: {latest:.2%})",
            "trend": "sustained_low",
            "slope": slope,
            "consecutive_below_threshold": consecutive_below,
        }

    # Declining: negative slope
    if slope is not None and slope < -0.02:
        logger.warning("Gate pass rate declining: slope=%+.4f", slope)
        return {
            "alert_level": "WARNING",
            "description": f"Gate pass rate declining (slope={slope:+.4f})",
            "trend": "declining",
            "slope": slope,
        }

    # Improving
    if slope is not None and slope > 0.02:
        return {
            "alert_level": "INFO",
            "description": f"Gate pass rate improving (slope={slope:+.4f})",
            "trend": "improving",
            "slope": slope,
        }

    return {
        "alert_level": "INFO",
        "description": "Gate pass rate stable",
        "trend": "stable",
        "slope": slope,
    }
