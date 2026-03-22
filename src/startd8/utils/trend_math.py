"""Shared trend math utilities for Kaizen cross-run analysis.

Extracted from cap-dev-pipe/kaizen-trends.py for SDK-wide reuse.
"""

from __future__ import annotations

from typing import List, Optional


def linear_slope(values: List[float]) -> Optional[float]:
    """Compute the OLS slope of a series against sequential indices.

    Returns None if fewer than 2 data points are provided.
    A positive slope indicates improvement when the metric is
    "higher is better" (e.g. score, pass rate); negative slope
    indicates improvement for "lower is better" metrics (e.g. cost).

    Args:
        values: Ordered list of numeric observations.

    Returns:
        Slope as float, or None if insufficient data.
    """
    n = len(values)
    if n < 2:
        return None

    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = 0.0
    denominator = 0.0
    for i, y in enumerate(values):
        dx = i - x_mean
        numerator += dx * (y - y_mean)
        denominator += dx * dx

    if denominator == 0.0:
        return 0.0

    return numerator / denominator
