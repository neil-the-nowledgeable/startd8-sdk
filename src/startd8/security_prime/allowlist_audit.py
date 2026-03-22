"""Allowlist effectiveness audit — REQ-KSP-300 through REQ-KSP-302.

Detects stale allowlist entries (unhit for N+ consecutive runs) and
produces a markdown audit report for operator review.
"""

from __future__ import annotations

from typing import Any, Dict, List

from startd8.logging_config import get_logger

logger = get_logger(__name__)

_STALE_RUN_THRESHOLD = 5


def detect_stale_entries(
    current_metrics: Dict[str, Any],
    archived_metrics_list: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Flag allowlist entries that haven't matched in N+ consecutive runs.

    Args:
        current_metrics: Allowlist metrics from the current run
            (from ``build_allowlist_metrics()``).
        archived_metrics_list: List of prior run allowlist metrics,
            ordered oldest to newest.

    Returns:
        List of stale entry dicts with pattern, check_id, and runs_unhit.
    """
    # Collect all known patterns from current metrics
    unhit_entries = current_metrics.get("unhit_entries", [])
    if not unhit_entries:
        return []

    stale = []
    for entry in unhit_entries:
        pattern = entry.get("file_pattern", "")
        check_id = entry.get("check_id", "")

        # Count consecutive runs where this entry was unhit (from newest to oldest)
        consecutive_unhit = 1  # Current run is unhit
        for prior in reversed(archived_metrics_list):
            prior_unhit = prior.get("unhit_entries", [])
            was_unhit = any(
                e.get("file_pattern") == pattern and e.get("check_id") == check_id
                for e in prior_unhit
            )
            if was_unhit:
                consecutive_unhit += 1
            else:
                break

        if consecutive_unhit >= _STALE_RUN_THRESHOLD:
            stale.append({
                "file_pattern": pattern,
                "check_id": check_id,
                "runs_unhit": consecutive_unhit,
            })
            logger.warning(
                "Allowlist entry '%s:%s' has not matched in %d runs — consider removal",
                pattern, check_id, consecutive_unhit,
            )

    return stale


def render_allowlist_audit(
    allowlist_metrics: Dict[str, Any],
    stale_entries: List[Dict[str, Any]],
) -> str:
    """Render a markdown audit report for the allowlist.

    Args:
        allowlist_metrics: Current run allowlist metrics.
        stale_entries: List of stale entries from ``detect_stale_entries()``.

    Returns:
        Markdown string.
    """
    lines = [
        "# Security Allowlist Audit",
        "",
        f"**Total entries:** {allowlist_metrics.get('total_entries', 0)}",
        f"**Hit entries:** {allowlist_metrics.get('hit_count', 0)}",
        f"**Unhit entries:** {allowlist_metrics.get('unhit_count', 0)}",
        "",
    ]

    # Hit details
    hit_entries = allowlist_metrics.get("hit_entries", [])
    if hit_entries:
        lines.extend(["## Matched Entries", ""])
        lines.append("| Pattern | Check | Files Matched |")
        lines.append("|---------|-------|--------------|")
        for entry in hit_entries:
            files = ", ".join(entry.get("matched_files", [])[:5])
            lines.append(
                f"| `{entry.get('file_pattern', '')}` "
                f"| {entry.get('check_id', '')} "
                f"| {files} |"
            )
        lines.append("")

    # Stale entries
    if stale_entries:
        lines.extend(["## Stale Entries (consider removal)", ""])
        lines.append("| Pattern | Check | Runs Unhit |")
        lines.append("|---------|-------|-----------|")
        for entry in stale_entries:
            lines.append(
                f"| `{entry['file_pattern']}` "
                f"| {entry['check_id']} "
                f"| {entry['runs_unhit']} |"
            )
        lines.append("")

    return "\n".join(lines)
