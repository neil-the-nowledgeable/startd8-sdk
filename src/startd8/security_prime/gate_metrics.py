"""Gate verdict report builder — REQ-KSP-100 through REQ-KSP-602.

Aggregates per-file Anzen gate results into ``security-gate-metrics.json``,
with scoring calibration (L2), OWASP coverage (L6), and prompt effectiveness
correlation (L5).

Follows the same pattern as ``query_prime/kaizen_metrics.py:build_verification_report()``.
"""

from __future__ import annotations

import datetime
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# L1: Gate verdict report (REQ-KSP-100–103)
# ---------------------------------------------------------------------------


def build_gate_verdict_report(
    gate_results: List[Dict[str, Any]],
    run_id: str,
    run_timestamp: Optional[str] = None,
    *,
    allowlist_metrics: Optional[Dict[str, Any]] = None,
    owasp_data: Optional[Dict[str, Any]] = None,
    score_distribution: Optional[Dict[str, Any]] = None,
    prompt_effectiveness: Optional[Dict[str, Any]] = None,
    threshold_sensitivity: Optional[List[Dict[str, Any]]] = None,
    component_contributions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate per-file gate results into security-gate-metrics.json schema.

    Args:
        gate_results: List of per-file enriched dicts with keys:
            file_path, verdict, score, findings_count, finding_types,
            timing_ms, database, language, allowlisted.
        run_id: Unique run identifier.
        run_timestamp: ISO timestamp; defaults to now.
        allowlist_metrics: Optional allowlist effectiveness data.
        owasp_data: Optional OWASP coverage section.
        score_distribution: Optional L2 score distribution data.
        prompt_effectiveness: Optional L5 prompt correlation data.
        threshold_sensitivity: Optional L2 threshold sensitivity data.
        component_contributions: Optional L2 component contribution breakdown.

    Returns:
        Dict suitable for JSON serialization as security-gate-metrics.json.
    """
    ts = run_timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Verdict counts
    verdict_counts: Dict[str, int] = {"pass": 0, "warn": 0, "fail": 0}
    scores: List[float] = []
    total_findings = 0
    findings_by_type: Dict[str, int] = {}
    databases_seen: set = set()
    languages_seen: set = set()
    files_checked = 0
    files_skipped = 0
    total_timing_ms = 0.0

    items: List[Dict[str, Any]] = []

    for entry in gate_results:
        verdict = entry.get("verdict", "pass")
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1

        score = entry.get("score", 1.0)
        scores.append(score)
        files_checked += 1

        fc = entry.get("findings_count", 0)
        total_findings += fc

        for ft, count in entry.get("finding_types", {}).items():
            findings_by_type[ft] = findings_by_type.get(ft, 0) + count

        db = entry.get("database", "")
        if db:
            databases_seen.add(db)

        lang = entry.get("language", "")
        if lang:
            languages_seen.add(lang)

        timing = entry.get("timing_ms", 0.0)
        total_timing_ms += timing

        items.append({
            "file_path": entry.get("file_path", ""),
            "verdict": verdict,
            "score": round(score, 4),
            "findings_count": fc,
            "finding_types": entry.get("finding_types", {}),
            "findings": entry.get("findings", []),
            "database": db,
            "language": lang,
            "timing_ms": round(timing, 2),
            "allowlisted": entry.get("allowlisted", False),
        })

    # Aggregates
    from startd8.security_prime.scorer import compute_aggregate_score

    aggregate_score = compute_aggregate_score(scores)
    mean_score = sum(scores) / len(scores) if scores else 1.0
    gate_pass_rate = (
        (verdict_counts.get("pass", 0) / files_checked) if files_checked else 1.0
    )

    if total_timing_ms > 5000:
        logger.warning("Gate timing threshold exceeded: %.0fms > 5000ms", total_timing_ms)

    posture = determine_posture(verdict_counts, gate_pass_rate, total_files=files_checked)

    report: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "timestamp": ts,
        "files_checked": files_checked,
        "files_skipped": files_skipped,
        "files_total": files_checked + files_skipped,
        "aggregate_score": round(aggregate_score, 4),
        "mean_score": round(mean_score, 4),
        "gate_pass_rate": round(gate_pass_rate, 4),
        "total_findings": total_findings,
        "findings_by_type": findings_by_type,
        "verdict_counts": verdict_counts,
        "databases_seen": sorted(databases_seen),
        "languages_seen": sorted(languages_seen),
        "total_timing_ms": round(total_timing_ms, 2),
        "posture": posture,
        "items": items,
    }
    report["security_posture"] = posture["level"].upper()

    # Optional sections
    if allowlist_metrics is not None:
        report["allowlist"] = allowlist_metrics
    if owasp_data is not None:
        report["owasp_coverage"] = owasp_data
    if score_distribution is not None:
        report["score_distribution"] = score_distribution
    if prompt_effectiveness is not None:
        report["prompt_effectiveness"] = prompt_effectiveness
    if threshold_sensitivity is not None:
        report["threshold_sensitivity"] = threshold_sensitivity
    if component_contributions is not None:
        report["component_contributions"] = component_contributions

    return report


def determine_posture(
    verdict_counts: Dict[str, int],
    gate_pass_rate: float,
    total_files: int = 0,
) -> Dict[str, Any]:
    """Determine security posture level: clean/degraded/critical.

    Args:
        verdict_counts: Map of verdict → count.
        gate_pass_rate: Fraction of files that passed.
        total_files: Total number of gated files (for interpretation text).

    Returns:
        Dict with ``level``, ``reason``, ``rules``, and ``interpretation`` keys.
    """
    rules = {
        "clean": "All gated files pass (gate_pass_rate = 1.0) with no warnings",
        "degraded": "Any WARN verdict or gate_pass_rate < 1.0, but no FAIL",
        "critical": "Any FAIL verdict (injection or credential finding)",
    }

    if verdict_counts.get("fail", 0) > 0:
        fail_count = verdict_counts["fail"]
        pass_count = verdict_counts.get("pass", 0)
        return {
            "level": "critical",
            "reason": f"{fail_count} file(s) failed the Anzen gate",
            "rules": rules,
            "interpretation": (
                f"{fail_count} file(s) failed the Anzen gate. "
                f"{pass_count} of {total_files} gated files passed."
            ),
        }
    if verdict_counts.get("warn", 0) > 0 or gate_pass_rate < 1.0:
        warn_count = verdict_counts.get("warn", 0)
        pass_count = verdict_counts.get("pass", 0)
        return {
            "level": "degraded",
            "reason": "Warnings present or pass rate below 100%",
            "rules": rules,
            "interpretation": (
                f"{warn_count} file(s) have warnings. "
                f"{pass_count} of {total_files} gated files passed."
            ),
        }
    return {
        "level": "clean",
        "reason": "All files passed with no warnings",
        "rules": rules,
        "interpretation": "All gated files passed with no warnings.",
    }


def write_gate_metrics_report(report: Dict[str, Any], output_dir: str) -> None:
    """Advisory write to security-gate-metrics.json.

    Args:
        report: Gate verdict report dict from ``build_gate_verdict_report()``.
        output_dir: Directory to write the report file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "security-gate-metrics.json"
    try:
        report_path.write_text(
            json.dumps(report, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        logger.info("Security gate metrics report: %s", report_path)
    except OSError as exc:
        logger.warning("Failed to write security gate metrics: %s", exc)


# ---------------------------------------------------------------------------
# L6: OWASP coverage section (REQ-KSP-600–602)
# ---------------------------------------------------------------------------

# Impact ranking per OWASP category gap
# Impact heuristic: high = project generates code in this OWASP attack surface,
# medium = category relevant but not directly exercised, low = not relevant.
_OWASP_GAP_IMPACT: Dict[str, str] = {
    "A01:2021": "high",    # Broken Access Control
    "A02:2021": "medium",  # Cryptographic Failures
    "A03:2021": "high",    # Injection (already covered)
    "A04:2021": "medium",  # Insecure Design
    "A05:2021": "medium",  # Security Misconfiguration
    "A06:2021": "high",    # Vulnerable Components
    "A07:2021": "high",    # Auth Failures
    "A08:2021": "medium",  # Data Integrity
    "A09:2021": "low",     # Logging Failures
    "A10:2021": "low",     # SSRF
}


def build_owasp_section(
    checks_that_ran: Optional[set] = None,
    findings_by_check: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Wrap generate_owasp_coverage() into report schema with impact ranking.

    Args:
        checks_that_ran: Set of check type strings that executed.
        findings_by_check: Dict of check_type → finding count.

    Returns:
        Dict with coverage_percentage, categories_covered, categories_total,
        categories list, and gaps with impact ranking.
    """
    from startd8.security_prime.owasp_coverage import generate_owasp_coverage

    coverage_report = generate_owasp_coverage(checks_that_ran, findings_by_check)

    covered = [c for c in coverage_report if c["status"] in ("COVERED", "PARTIAL")]
    uncovered = [c for c in coverage_report if c["status"] == "UNCOVERED"]
    total = len(coverage_report)

    coverage_pct = len(covered) / total if total else 0.0

    gaps = []
    for cat in uncovered:
        gaps.append({
            "category": cat["category"],
            "name": cat["name"],
            "impact": _OWASP_GAP_IMPACT.get(cat["category"], "medium"),
        })
    # Sort by impact: high > medium > low
    impact_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: impact_order.get(g["impact"], 1))

    return {
        "coverage_percentage": round(coverage_pct, 4),
        "categories_covered": len(covered),
        "categories_total": total,
        "categories": coverage_report,
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# L2: Scoring calibration (REQ-KSP-200–202)
# ---------------------------------------------------------------------------


def compute_score_distribution(scores: List[float]) -> Dict[str, Any]:
    """Compute score distribution statistics.

    Args:
        scores: List of per-file security scores.

    Returns:
        Dict with min, max, mean, median, p25, p75, std_dev, and
        threshold_counts at 0.5/0.7/0.9 boundaries.
    """
    # Filter non-finite values that could corrupt statistics
    scores = [s for s in scores if math.isfinite(s)]
    if not scores:
        return {
            "min": None, "max": None, "mean": None, "median": None,
            "p25": None, "p75": None, "std_dev": None,
            "count": 0, "threshold_counts": {},
        }

    sorted_scores = sorted(scores)
    n = len(sorted_scores)

    def _percentile(data: List[float], pct: float) -> float:
        k = (n - 1) * pct / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    std_dev = statistics.stdev(scores) if n >= 2 else 0.0

    threshold_counts = {}
    for t in [0.50, 0.70, 0.90]:
        above = sum(1 for s in scores if s >= t)
        below = n - above
        threshold_counts[str(t)] = {"above": above, "below": below}

    mean = sum(scores) / n

    # Distribution shape classifier
    if n < 2:
        shape = "insufficient_data"
    elif std_dev > 0.30:
        shape = "bimodal"
    elif mean > 0.85 and std_dev < 0.15:
        shape = "clustered_high"
    elif mean < 0.50:
        shape = "clustered_low"
    else:
        shape = "spread"

    return {
        "min": round(sorted_scores[0], 4),
        "max": round(sorted_scores[-1], 4),
        "mean": round(mean, 4),
        "median": round(_percentile(sorted_scores, 50), 4),
        "p25": round(_percentile(sorted_scores, 25), 4),
        "p75": round(_percentile(sorted_scores, 75), 4),
        "std_dev": round(std_dev, 4),
        "count": n,
        "threshold_counts": threshold_counts,
        "shape": shape,
    }


def compute_threshold_sensitivity(
    file_entries: List[Dict[str, Any]],
    thresholds: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Compute false positive/negative counts at each threshold.

    FP = file fails gate (score < threshold) but has no injection or
    credential findings. FN = file passes gate but has injection or
    credential findings → logged as ERROR (invariant violation).

    Args:
        file_entries: Per-file dicts with score, finding_types keys.
        thresholds: Thresholds to test; defaults to [0.50..0.90].

    Returns:
        List of dicts per threshold with fp_count, fn_count, total.
    """
    if not file_entries:
        logger.debug("Threshold sensitivity: no file entries to analyze")
        return []

    if thresholds is None:
        thresholds = [0.50, 0.60, 0.70, 0.80, 0.90]

    results = []
    for t in thresholds:
        fp = 0
        fn = 0
        for entry in file_entries:
            score = entry.get("score", 1.0)
            ftypes = entry.get("finding_types", {})
            has_hard = (
                ftypes.get("injection", 0) > 0
                or ftypes.get("credential_leakage", 0) > 0
            )
            fails_gate = score < t
            if fails_gate and not has_hard:
                fp += 1
            if not fails_gate and has_hard:
                fn += 1
                logger.error(
                    "Threshold sensitivity: FN at %.2f — file passes "
                    "gate but has hard findings: %s",
                    t,
                    entry.get("file_path", "unknown"),
                )
        files_passing = sum(1 for e in file_entries if e.get("score", 1.0) >= t)
        files_failing = len(file_entries) - files_passing
        results.append({
            "threshold": t,
            "fp_count": fp,
            "fn_count": fn,
            "total": len(file_entries),
            "files_passing": files_passing,
            "files_failing": files_failing,
        })

    if results:
        optimal = min(results, key=lambda r: r["fp_count"] + r["fn_count"])
        logger.info(
            "Threshold sensitivity: optimal=%.2f (FP=%d, FN=%d)",
            optimal["threshold"], optimal["fp_count"], optimal["fn_count"],
        )

    return results


def compute_component_contributions(
    file_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Break down penalty contributions for failed files.

    For files with score < 1.0, shows which finding types contributed
    to the penalty using the scorer's penalty constants.

    Args:
        file_entries: Per-file dicts with score, finding_types,
            and finding_severities keys.

    Returns:
        List of dicts per failed file with penalty breakdown.
    """
    from startd8.security_prime.scorer import _SEVERITY_PENALTY, _DIMINISHING_RATE

    failed = [e for e in file_entries if e.get("score", 1.0) < 1.0]
    contributions = []

    for entry in failed:
        severities = entry.get("finding_severities", [])
        if not severities:
            contributions.append({
                "file_path": entry.get("file_path", ""),
                "score": entry.get("score", 0.0),
                "breakdown": [],
                "short_circuit_applied": False,
            })
            continue

        penalties = [_SEVERITY_PENALTY.get(s, 0.05) for s in severities]
        worst = max(penalties)
        additional = sum(penalties) - worst
        diminished = additional * _DIMINISHING_RATE

        worst_idx = penalties.index(worst)
        breakdown = []
        for i, (sev, pen) in enumerate(zip(severities, penalties)):
            effective = pen if pen == worst else pen * _DIMINISHING_RATE
            breakdown.append({
                "severity": sev,
                "raw_penalty": round(pen, 4),
                "effective_penalty": round(effective, 4),
                "is_worst": i == worst_idx,
            })

        ftypes = entry.get("finding_types", {})
        has_hard = (
            ftypes.get("injection", 0) > 0
            or ftypes.get("credential_leakage", 0) > 0
        )
        is_short_circuit = entry.get("score", 0.0) == 0.0 and has_hard

        contrib_entry: Dict[str, Any] = {
            "file_path": entry.get("file_path", ""),
            "score": entry.get("score", 0.0),
            "total_penalty": round(worst + diminished, 4),
            "breakdown": breakdown,
            "short_circuit_applied": is_short_circuit,
        }
        if is_short_circuit:
            contrib_entry["short_circuit_reason"] = (
                "injection/credential finding \u2192 FAIL \u2192 0.0"
            )
        contributions.append(contrib_entry)

    return contributions


# ---------------------------------------------------------------------------
# L5: Prompt effectiveness correlation (REQ-KSP-500–502)
# ---------------------------------------------------------------------------


def compute_prompt_effectiveness(
    file_entries: List[Dict[str, Any]],
    security_sensitive_tasks: int = 0,
    p0_injected: bool = False,
    p1_databases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute P0/P1 prompt injection impact correlation.

    Args:
        file_entries: Per-file gate result entries.
        security_sensitive_tasks: Count of tasks flagged as security-sensitive.
        p0_injected: Whether P0 system-level security hints were injected.
        p1_databases: Databases for which P1 Kaizen hints were injected.

    Returns:
        Dict with p0_correlation, p1_value_signal, and summary.
    """
    total = len(file_entries)
    fails = sum(1 for e in file_entries if e.get("verdict") == "fail")
    injection_found = sum(
        1 for e in file_entries
        if e.get("finding_types", {}).get("injection", 0) > 0
    )

    p0_section: Dict[str, Any] = {
        "injected": p0_injected,
        "total_files": total,
        "injection_findings": injection_found,
        "fails": fails,
    }
    if p0_injected:
        p0_section["correlation"] = (
            "positive" if injection_found == 0 else "weak"
        )
    else:
        p0_section["correlation"] = "baseline"

    # P1 value signal — need enough data to be meaningful
    p1_dbs = p1_databases or []
    if security_sensitive_tasks < 5:
        p1_signal = "insufficient_data"
    elif injection_found == 0 and p1_dbs:
        p1_signal = "positive"
    elif injection_found > 0 and p1_dbs:
        p1_signal = "negative"
    else:
        p1_signal = "neutral"

    return {
        "p0": p0_section,
        "p1": {
            "databases_targeted": p1_dbs,
            "security_sensitive_tasks": security_sensitive_tasks,
            "value_signal": p1_signal,
        },
        "summary": _prompt_effectiveness_summary(p0_section, p1_signal),
    }


def _prompt_effectiveness_summary(p0: Dict[str, Any], p1_signal: str) -> str:
    """Human-readable prompt effectiveness summary."""
    parts = []
    if p0.get("injected"):
        if p0.get("correlation") == "positive":
            parts.append("P0 system hints appear effective (no injection found).")
        else:
            parts.append("P0 system hints injected but injection still found.")
    else:
        parts.append("No P0 system hints injected (baseline run).")

    signal_msg = {
        "positive": "P1 Kaizen hints correlate with clean outcomes.",
        "negative": "P1 Kaizen hints did not prevent injection — escalate.",
        "neutral": "P1 signal is neutral (no targeted databases).",
        "insufficient_data": "Insufficient data for P1 assessment (<5 tasks).",
    }
    parts.append(signal_msg.get(p1_signal, ""))
    return " ".join(parts)


def compute_hint_escalation_effectiveness(
    kaizen_metrics_dir: str,
    current_injection_found: bool,
) -> Dict[str, Any]:
    """Assess Kaizen hint escalation effectiveness across runs.

    Reads ``consecutive_injection_runs`` from kaizen-metrics.json to
    determine if the 3-level escalation is working.

    Args:
        kaizen_metrics_dir: Directory containing kaizen-metrics.json.
        current_injection_found: Whether current run has injection findings.

    Returns:
        Dict with consecutive_runs, escalation_level, effectiveness.
    """
    from startd8.security_prime.kaizen import load_security_metrics

    prior = load_security_metrics(kaizen_metrics_dir)
    consecutive = prior.get("consecutive_injection_runs", 0)

    if current_injection_found:
        new_consecutive = consecutive + 1
    else:
        new_consecutive = 0

    # Escalation levels match generate_security_hint()
    if new_consecutive <= 1:
        level = "guidance"
    elif new_consecutive == 2:
        level = "requirement"
    else:
        level = "critical"

    # Effectiveness assessment
    if not current_injection_found and consecutive > 0:
        effectiveness = "positive"  # Resolved after escalation
    elif current_injection_found and consecutive >= 3:
        effectiveness = "negative"  # Persists despite critical escalation
    elif current_injection_found:
        effectiveness = "neutral"  # Still escalating
    else:
        effectiveness = "positive"  # Clean run

    # Interpretation
    if effectiveness == "positive" and consecutive > 0:
        interpretation = f"Injection resolved after escalation to '{level}' level"
    elif effectiveness == "positive" and consecutive == 0:
        interpretation = "No injection findings (clean run)"
    elif effectiveness == "negative":
        interpretation = f"Injection persists despite '{level}' escalation — structural fix may be needed"
    else:
        interpretation = f"Hint escalation in progress (level: {level})"

    return {
        "prior_consecutive_runs": consecutive,
        "current_consecutive_runs": new_consecutive,
        "escalation_level": level,
        "effectiveness": effectiveness,
        "interpretation": interpretation,
    }
