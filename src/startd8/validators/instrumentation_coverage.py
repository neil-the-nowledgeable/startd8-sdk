"""Instrumentation coverage computation (REQ-TCW-402/403).

Grep-searches generated source files for metric/trace names declared in
the instrumentation contract and reports coverage percentage + gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


__all__ = [
    "CoverageResult",
    "compute_instrumentation_coverage",
    "extract_promql_metrics",
    "validate_dashboard_coverage",
]

DEFAULT_EXTENSIONS: Tuple[str, ...] = (".java", ".py", ".go", ".js", ".ts", ".cs")


@dataclass(frozen=True)
class CoverageResult:
    """Result of instrumentation coverage analysis."""

    contract_entries: int = 0
    satisfied_entries: int = 0
    coverage_pct: float = 0.0
    gaps: List[Dict[str, str]] = field(default_factory=list)
    satisfied: List[Dict[str, Any]] = field(default_factory=list)


def _collect_contract_names(contract: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract metric/trace names from an instrumentation contract.

    Handles both normalized (``metrics.required``) and raw ContextCore
    (``metrics.convention_based`` / ``metrics.manifest_declared``) schemas.
    """
    entries: List[Dict[str, str]] = []

    metrics = contract.get("metrics")
    if isinstance(metrics, dict):
        for key in ("required", "convention_based", "manifest_declared"):
            items = metrics.get(key, [])
            if isinstance(items, list):
                for item in items:
                    name = item.get("name") or item.get("metric_name") or ""
                    if name:
                        entries.append({"name": name, "type": "metric"})

    traces = contract.get("traces")
    if isinstance(traces, dict):
        for key in ("required", "convention_based", "manifest_declared"):
            items = traces.get(key, [])
            if isinstance(items, list):
                for item in items:
                    name = item.get("name") or item.get("span_name") or ""
                    if name:
                        entries.append({"name": name, "type": "trace"})

    # Deduplicate by name
    seen: Set[str] = set()
    unique: List[Dict[str, str]] = []
    for e in entries:
        if e["name"] not in seen:
            seen.add(e["name"])
            unique.append(e)
    return unique


def _search_files(
    project_root: Path,
    pattern: str,
    extensions: Tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    """Search source files for *pattern*. Returns first match or None."""
    for src in project_root.rglob("*"):
        if not src.is_file() or src.suffix not in extensions:
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if pattern in line:
                return {
                    "found_in": str(src.relative_to(project_root)),
                    "line": line_no,
                }
    return None


def compute_instrumentation_coverage(
    project_root: Path,
    instrumentation_contract: Optional[Dict[str, Any]],
    extensions: Tuple[str, ...] = DEFAULT_EXTENSIONS,
) -> CoverageResult:
    """Compute how many contract entries are satisfied by generated code.

    Args:
        project_root: Root directory of generated source code.
        instrumentation_contract: The instrumentation contract dict
            (ContextCore hints or normalized ``metrics.required`` schema).
        extensions: File suffixes to search.

    Returns:
        A :class:`CoverageResult` with coverage percentage and gap details.
    """
    if not instrumentation_contract or not isinstance(instrumentation_contract, dict):
        return CoverageResult()

    entries = _collect_contract_names(instrumentation_contract)
    if not entries:
        return CoverageResult()

    satisfied: List[Dict[str, Any]] = []
    gaps: List[Dict[str, str]] = []

    for entry in entries:
        match = _search_files(project_root, entry["name"], extensions)
        if match:
            satisfied.append({
                "name": entry["name"],
                "type": entry["type"],
                **match,
            })
        else:
            gaps.append({
                "name": entry["name"],
                "type": entry["type"],
                "status": "missing",
            })

    total = len(entries)
    sat = len(satisfied)
    pct = (sat / total * 100) if total > 0 else 0.0

    return CoverageResult(
        contract_entries=total,
        satisfied_entries=sat,
        coverage_pct=round(pct, 2),
        gaps=gaps,
        satisfied=satisfied,
    )


# ---------------------------------------------------------------------------
# REQ-TCW-403: Closed-loop dashboard validation (P3)
# ---------------------------------------------------------------------------

_PROMQL_METRIC_RE = re.compile(
    r"""
    (?<![a-zA-Z0-9_])      # Not preceded by identifier char (lookbehind)
    ([a-zA-Z_:][a-zA-Z0-9_:]*)  # PromQL metric name
    \s*[\{\[\(]            # Followed by label selector or function call
    """,
    re.VERBOSE,
)


def extract_promql_metrics(dashboard_json: Dict[str, Any]) -> Set[str]:
    """Extract metric names from Grafana dashboard JSON PromQL targets.

    Walks all panels and their targets, extracting metric names from
    ``expr`` fields using a regex heuristic.
    """
    metrics: Set[str] = set()
    _BUILTIN = {
        "sum", "rate", "avg", "min", "max", "count", "histogram_quantile",
        "increase", "irate", "delta", "deriv", "predict_linear",
        "label_replace", "label_join", "absent", "absent_over_time",
        "changes", "resets", "sort", "sort_desc", "topk", "bottomk",
        "group", "clamp", "clamp_min", "clamp_max", "ceil", "floor",
        "round", "time", "vector", "scalar", "by", "without", "on",
        "ignoring", "bool", "offset",
    }

    def _walk_panels(panels: list) -> None:
        for panel in panels:
            if not isinstance(panel, dict):
                continue
            # Recurse into collapsed rows
            if "panels" in panel:
                _walk_panels(panel["panels"])
            for target in panel.get("targets", []):
                expr = target.get("expr", "")
                if not isinstance(expr, str):
                    continue
                for m in _PROMQL_METRIC_RE.finditer(expr):
                    name = m.group(1)
                    if name.lower() not in _BUILTIN and not name.startswith("$"):
                        metrics.add(name)

    _walk_panels(dashboard_json.get("panels", []))
    return metrics


def validate_dashboard_coverage(
    project_root: Path,
    instrumentation_contract: Dict[str, Any],
    dashboard_dir: Path,
    extensions: Tuple[str, ...] = DEFAULT_EXTENSIONS,
) -> List[Dict[str, Any]]:
    """Cross-check dashboard metric names against generated code.

    Returns a list of gap entries for metrics referenced in dashboards
    but not found in the source code.
    """
    dashboard_metrics: Set[str] = set()
    for f in dashboard_dir.glob("*.json"):
        try:
            data = __import__("json").loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        dashboard_metrics |= extract_promql_metrics(data)

    if not dashboard_metrics:
        return []

    gaps: List[Dict[str, Any]] = []
    for metric_name in sorted(dashboard_metrics):
        match = _search_files(project_root, metric_name, extensions)
        if not match:
            gaps.append({
                "name": metric_name,
                "type": "metric",
                "source": "dashboard",
                "status": "missing_in_code",
            })
    return gaps
