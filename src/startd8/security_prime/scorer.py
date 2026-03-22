"""Security scoring — SP-SCR-001 through SP-SCR-012.

Maps ``query_prime.models.SecurityVerificationResult`` to a [0.0, 1.0] score
using max-severity-weighted formula with diminishing returns.

No new models — uses ``SecurityVerificationResult`` and ``SecurityVerdict``
from ``query_prime.models`` directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Severity penalties (SP-SCR-003)
_SEVERITY_PENALTY = {
    "error": 0.15,
    "warning": 0.05,
    "info": 0.02,
}

# Diminishing returns multiplier for additional findings beyond the worst
_DIMINISHING_RATE = 0.3

# Simple verdict → score mapping (SP-SCR-001)
_VERDICT_SCORE = {"pass": 1.0, "warn": 0.7, "fail": 0.0}


@dataclass
class SecurityScoreResult:
    """Per-file security score with breakdown."""

    file_path: str
    score: float
    verdict: str  # "pass", "warn", "fail"
    finding_count: int
    database: Optional[str] = None
    language: Optional[str] = None


def compute_security_score(
    verdict_value: str,
    finding_severities: Optional[List[str]] = None,
) -> float:
    """Compute security score from verdict and finding severities.

    Simple path (SP-SCR-001): PASS=1.0, WARN=0.7, FAIL=0.0.

    Detailed path (SP-SCR-003): max-severity-weighted with diminishing returns
    when finding_severities is provided.

    Args:
        verdict_value: "pass", "warn", or "fail".
        finding_severities: Optional list of severity strings for granular scoring.

    Returns:
        Score in [0.0, 1.0].
    """
    if verdict_value == "pass":
        return 1.0

    # If no detailed severities, use simple mapping
    if not finding_severities:
        return _VERDICT_SCORE.get(verdict_value, 0.5)

    # Max-severity-weighted with diminishing returns
    penalties = [_SEVERITY_PENALTY.get(s, 0.05) for s in finding_severities]
    if not penalties:
        return 1.0

    worst = max(penalties)
    additional = sum(penalties) - worst
    diminished = additional * _DIMINISHING_RATE

    return max(0.0, 1.0 - worst - diminished)


def compute_aggregate_score(per_file_scores: List[float]) -> float:
    """Aggregate security score = weakest link (SP-SCR-012).

    Args:
        per_file_scores: List of per-file security scores.

    Returns:
        Minimum score, or 1.0 if no files checked.
    """
    if not per_file_scores:
        return 1.0
    return min(per_file_scores)
