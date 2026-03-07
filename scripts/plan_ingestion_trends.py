#!/usr/bin/env python3
"""Kaizen cross-run trend analysis for plan ingestion diagnostics.

Aggregates ``plan-ingestion-diagnostic.json`` files across multiple runs
and prints a tabular comparison with trend indicators.

Usage::

    python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/
    python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/ --last 5
    python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Discovery ────────────────────────────────────────────────────────


def discover_diagnostics(runs_dir: Path) -> List[Dict[str, Any]]:
    """Find and load all plan-ingestion-diagnostic.json files under *runs_dir*."""
    results: List[Dict[str, Any]] = []
    for path in sorted(runs_dir.rglob("plan-ingestion-diagnostic.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_source_path"] = str(path)
            results.append(data)
        except (OSError, json.JSONDecodeError) as err:
            print(f"  [skip] {path}: {err}", file=sys.stderr)
    # Sort by run_timestamp (ISO 8601 strings sort correctly)
    results.sort(key=lambda d: d.get("run_timestamp", ""))
    return results


# ── Metric extraction ────────────────────────────────────────────────


def extract_metrics(diag: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key metrics from a single diagnostic report."""
    phases = diag.get("phases", {})
    parse_signals = phases.get("parse", {}).get("quality_signals", {})
    assess_signals = phases.get("assess", {}).get("quality_signals", {})
    totals = diag.get("totals", {})

    fallback_count = sum(
        1 for p in phases.values()
        if isinstance(p, dict) and p.get("code_extraction_fallback")
    )

    return {
        "timestamp": diag.get("run_timestamp", "?"),
        "route": diag.get("route", "?"),
        "success": diag.get("overall_success", False),
        "features": parse_signals.get("features_extracted", 0),
        "seed_quality": diag.get("seed_quality_score", 0.0),
        "total_cost": totals.get("cost_usd", 0.0),
        "total_time_ms": totals.get("time_ms", 0),
        "fallbacks": fallback_count,
        "composite": assess_signals.get("composite_score", 0),
        "route_margin": assess_signals.get("route_margin", 0),
        "warnings": len(diag.get("quality_warnings", [])),
    }


# ── Trend computation ────────────────────────────────────────────────


_HIGHER_IS_BETTER = {"seed_quality", "features"}
_LOWER_IS_BETTER = {"total_cost", "fallbacks", "warnings", "total_time_ms"}


def trend_arrow(key: str, prev: float, curr: float) -> str:
    """Return a trend indicator arrow for a metric delta."""
    if prev == curr:
        return "→"
    improving = (curr > prev) if key in _HIGHER_IS_BETTER else (curr < prev)
    if key in _LOWER_IS_BETTER:
        improving = curr < prev
    return "↑" if improving else "↓"


# ── Formatting ───────────────────────────────────────────────────────


def _fmt_cost(val: float) -> str:
    return f"${val:.4f}"


def _fmt_time(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    return f"{ms / 1000:.1f}s"


def _fmt_quality(val: float) -> str:
    return f"{val:.2f}"


def format_table(rows: List[Dict[str, Any]]) -> str:
    """Format metrics as a plain-text table."""
    if not rows:
        return "No diagnostic reports found."

    headers = [
        "Timestamp", "Route", "OK", "Feat", "Seed Q",
        "Cost", "Time", "FB", "Comp", "Margin", "Warn", "Trend",
    ]

    lines: List[List[str]] = []
    prev: Optional[Dict[str, Any]] = None
    for row in rows:
        trend_parts = []
        if prev is not None:
            for key in ("seed_quality", "total_cost", "fallbacks"):
                arrow = trend_arrow(key, prev.get(key, 0), row.get(key, 0))
                if arrow != "→":
                    trend_parts.append(f"{key[:4]}{arrow}")
        trend_str = " ".join(trend_parts) if trend_parts else "—"

        ts = row["timestamp"]
        # Shorten ISO timestamp to date+time
        if "T" in ts:
            ts = ts.split("T")[0] + " " + ts.split("T")[1][:8]

        lines.append([
            ts,
            row["route"],
            "Y" if row["success"] else "N",
            str(row["features"]),
            _fmt_quality(row["seed_quality"]),
            _fmt_cost(row["total_cost"]),
            _fmt_time(row["total_time_ms"]),
            str(row["fallbacks"]),
            str(row["composite"]),
            str(row["route_margin"]),
            str(row["warnings"]),
            trend_str,
        ])
        prev = row

    # Compute column widths
    widths = [len(h) for h in headers]
    for line in lines:
        for i, cell in enumerate(line):
            widths[i] = max(widths[i], len(cell))

    # Build output
    header_line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_line = "  ".join("-" * widths[i] for i in range(len(headers)))
    data_lines = [
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line))
        for line in lines
    ]

    return "\n".join([header_line, sep_line] + data_lines)


# ── Main ─────────────────────────────────────────────────────────────


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Kaizen plan ingestion cross-run trend analysis",
    )
    parser.add_argument(
        "--runs-dir", required=True, type=Path,
        help="Root directory containing pipeline run outputs",
    )
    parser.add_argument(
        "--last", type=int, default=0,
        help="Show only the last N runs (0 = all)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output metrics as JSON instead of a table",
    )
    args = parser.parse_args(argv)

    if not args.runs_dir.is_dir():
        print(f"Error: {args.runs_dir} is not a directory", file=sys.stderr)
        return 1

    diagnostics = discover_diagnostics(args.runs_dir)
    if not diagnostics:
        print(f"No plan-ingestion-diagnostic.json files found under {args.runs_dir}",
              file=sys.stderr)
        return 1

    metrics = [extract_metrics(d) for d in diagnostics]
    if args.last > 0:
        metrics = metrics[-args.last:]

    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
    else:
        print(f"\nKaizen Plan Ingestion Trends ({len(metrics)} run(s))\n")
        print(format_table(metrics))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
