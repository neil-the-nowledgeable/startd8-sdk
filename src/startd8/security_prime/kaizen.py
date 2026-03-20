"""Kaizen security feedback — SP-KZ-010 through SP-KZ-021.

Generates escalating security hints across runs and tracks security
metrics in kaizen-metrics.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from startd8.logging_config import get_logger

logger = get_logger(__name__)


def generate_security_hint(
    database: str,
    consecutive_runs: int,
    prior_files: Optional[List[str]] = None,
) -> str:
    """Generate an escalating security hint based on consecutive failure count.

    SP-KZ-010: Run 1 → guidance, Run 2 → requirement, Run 3+ → critical.

    Args:
        database: Database type that had violations.
        consecutive_runs: Number of consecutive runs with security violations.
        prior_files: File paths from prior violations (for specificity).

    Returns:
        Hint string appropriate for the escalation level.
    """
    if consecutive_runs <= 1:
        return (
            f"Prefer parameterized queries for {database} operations. "
            f"See query_prime/patterns/ for safe binding examples."
        )

    if consecutive_runs == 2:
        file_list = ""
        if prior_files:
            file_list = f" Previous run had injection in: {', '.join(prior_files[:3])}."
        return (
            f"You MUST use parameterized queries for {database} — "
            f"the previous run had SQL injection violations.{file_list}"
        )

    # 3+ consecutive runs
    return (
        f"CRITICAL: SQL injection has been found in {consecutive_runs} "
        f"consecutive runs for {database}. ALL database queries MUST use "
        f"parameterized bindings. Files that use string interpolation or "
        f"concatenation in SQL will be REJECTED by the Anzen gate."
    )


def load_security_metrics(output_dir: str) -> Dict[str, Any]:
    """Load security metrics from kaizen-metrics.json.

    Args:
        output_dir: Directory containing kaizen-metrics.json.

    Returns:
        Security metrics dict, or empty defaults if not found.
    """
    metrics_path = Path(output_dir) / "kaizen-metrics.json"
    if not metrics_path.is_file():
        return _default_metrics()

    try:
        data = json.loads(metrics_path.read_text())
        return data.get("security", _default_metrics())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load security metrics: %s", exc)
        return _default_metrics()


def update_security_metrics(
    output_dir: str,
    injection_blocked: int = 0,
    credential_blocked: int = 0,
    aggregate_score: float = 1.0,
    files_checked: int = 0,
    files_skipped: int = 0,
    violation_files: Optional[List[str]] = None,
) -> None:
    """Update security metrics in kaizen-metrics.json.

    Merges security metrics into the existing kaizen-metrics.json file,
    preserving all non-security keys.

    Args:
        output_dir: Directory containing kaizen-metrics.json.
        injection_blocked: Count of injection findings that caused gate FAIL.
        credential_blocked: Count of credential findings that caused gate FAIL.
        aggregate_score: Aggregate (weakest-link) security score.
        files_checked: Number of files that passed through the Anzen gate.
        files_skipped: Number of files skipped (no database surface).
        violation_files: File paths that had violations (for Kaizen escalation).
    """
    metrics_path = Path(output_dir) / "kaizen-metrics.json"

    # Load existing metrics (preserve non-security keys)
    existing: Dict[str, Any] = {}
    if metrics_path.is_file():
        try:
            existing = json.loads(metrics_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    # Load prior security metrics for consecutive run tracking
    prior = existing.get("security", _default_metrics())
    consecutive = prior.get("consecutive_injection_runs", 0)
    if injection_blocked > 0:
        consecutive += 1
    else:
        consecutive = 0  # Reset on clean run

    existing["security"] = {
        "injection_blocked": injection_blocked,
        "credential_blocked": credential_blocked,
        "aggregate_score": round(aggregate_score, 4),
        "files_checked": files_checked,
        "files_skipped": files_skipped,
        "consecutive_injection_runs": consecutive,
        "last_injection_files": violation_files or [],
    }

    try:
        metrics_path.write_text(json.dumps(existing, indent=2) + "\n")
        logger.info(
            "Security metrics updated: score=%.2f injection_blocked=%d consecutive=%d",
            aggregate_score, injection_blocked, consecutive,
        )
    except OSError as exc:
        logger.warning("Failed to write security metrics: %s", exc)


def _default_metrics() -> Dict[str, Any]:
    """Default security metrics for first run."""
    return {
        "injection_blocked": 0,
        "credential_blocked": 0,
        "aggregate_score": 1.0,
        "files_checked": 0,
        "files_skipped": 0,
        "consecutive_injection_runs": 0,
        "last_injection_files": [],
    }
