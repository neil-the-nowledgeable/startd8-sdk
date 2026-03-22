#!/usr/bin/env python3
"""Cross-run trend analysis for Query Prime security metrics — REQ-KQP-400.

Reads query-security-metrics.json from archived runs via kaizen-index.json,
computes slopes for key metrics, and outputs trend analysis.

Usage:
    python3 scripts/run_query_prime_trends.py \\
        --output-dir .cap-dev-pipe/pipeline-output/my-project/run-005/plan-ingestion
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SDK_SRC = _SCRIPT_DIR.parent / "src"
if _SDK_SRC.is_dir():
    sys.path.insert(0, str(_SDK_SRC))

from startd8.utils.trend_math import linear_slope


def _load_runs(output_dir: Path) -> list[dict]:
    """Load query security metrics from kaizen-index.json run history."""
    index_path = output_dir / "kaizen-index.json"
    if not index_path.is_file():
        return []

    try:
        index = json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    runs = []
    for entry in index.get("runs", []):
        run_dir = output_dir / entry.get("relative_path", "")
        metrics_path = run_dir / "kaizen-metrics.json"
        if not metrics_path.is_file():
            # Try query-security-metrics.json as fallback
            metrics_path = run_dir / "query-security-metrics.json"
        if not metrics_path.is_file():
            continue
        try:
            data = json.loads(metrics_path.read_text())
            qs = data.get("query_security", data)  # Standalone or embedded
            if "mean_score" in qs:
                runs.append(qs)
        except (json.JSONDecodeError, OSError):
            continue

    return runs


def compute_trends(runs: list[dict]) -> dict:
    """Compute trend slopes across runs."""
    if len(runs) < 2:
        return {"status": "insufficient_data", "runs_available": len(runs)}

    scores = [r.get("mean_score", 0.0) for r in runs]
    pass_rates = [r.get("pass_rate", 0.0) for r in runs]
    costs = [r.get("total_cost_usd", 0.0) for r in runs]
    injections = [float(r.get("injection_total", 0)) for r in runs]

    return {
        "status": "ok",
        "runs_analyzed": len(runs),
        "score_slope": linear_slope(scores),
        "pass_rate_slope": linear_slope(pass_rates),
        "cost_slope": linear_slope(costs),
        "injection_slope": linear_slope(injections),
        "latest_score": scores[-1] if scores else None,
        "latest_pass_rate": pass_rates[-1] if pass_rates else None,
        "interpretation": _interpret(
            linear_slope(scores),
            linear_slope(injections),
        ),
    }


def _interpret(score_slope: float | None, injection_slope: float | None) -> str:
    """Human-readable trend interpretation."""
    if score_slope is None:
        return "Insufficient data for trend analysis."

    parts = []
    if score_slope > 0.01:
        parts.append("Security quality is IMPROVING across runs.")
    elif score_slope < -0.01:
        parts.append("Security quality is DECLINING — review recent changes.")
    else:
        parts.append("Security quality is STABLE.")

    if injection_slope is not None:
        if injection_slope > 0.1:
            parts.append("Injection findings are INCREASING — escalate review.")
        elif injection_slope < -0.1:
            parts.append("Injection findings are decreasing.")

    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query Prime cross-run trend analysis",
    )
    parser.add_argument(
        "--output-dir", required=True, type=Path,
        help="Run output directory containing kaizen-index.json",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of summary",
    )
    args = parser.parse_args()

    runs = _load_runs(args.output_dir)
    trends = compute_trends(runs)

    if args.json:
        print(json.dumps(trends, indent=2))
    else:
        print(f"Query Prime Trends ({trends.get('runs_analyzed', 0)} runs)")
        print("=" * 50)
        if trends["status"] == "insufficient_data":
            print(f"Need at least 2 runs (have {trends['runs_available']}).")
            return
        print(f"  Score slope:     {trends['score_slope']:+.4f}")
        print(f"  Pass rate slope: {trends['pass_rate_slope']:+.4f}")
        print(f"  Cost slope:      {trends['cost_slope']:+.6f}")
        print(f"  Injection slope: {trends['injection_slope']:+.2f}")
        print(f"\n  {trends['interpretation']}")

    # Write trends file
    trends_path = args.output_dir / "query-prime-trends.json"
    try:
        trends_path.write_text(json.dumps(trends, indent=2) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    main()
