#!/usr/bin/env python3
"""Cross-run security posture trend analysis — REQ-KSP-400.

Reads security-gate-metrics.json from archived runs via kaizen-index.json,
computes slopes for key metrics, and outputs trend analysis.

Usage:
    python3 scripts/run_security_trends.py \
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

from startd8.security_prime.trend_analysis import compute_security_posture_trend


def _load_runs(output_dir: Path) -> list[dict]:
    """Load security gate metrics from archived runs."""
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
        gate_path = run_dir / "security-gate-metrics.json"
        if not gate_path.is_file():
            continue
        try:
            data = json.loads(gate_path.read_text())
            if "gate_pass_rate" in data:
                runs.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return runs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Security Prime cross-run trend analysis",
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
    trends = compute_security_posture_trend(runs)

    if args.json:
        print(json.dumps(trends, indent=2))
    else:
        print(f"Security Posture Trends ({trends.get('runs_analyzed', 0)} runs)")
        print("=" * 55)
        if trends["status"] == "insufficient_data":
            print(f"Need at least 2 runs (have {trends['runs_available']}).")
            return
        print(f"  Pass rate slope:  {trends['pass_rate_slope']:+.4f}")
        print(f"  Mean score slope: {trends['mean_score_slope']:+.4f}")
        print(f"  Injection slope:  {trends['injection_slope']:+.2f}")
        if trends.get("owasp_coverage_slope") is not None:
            print(f"  OWASP cov slope:  {trends['owasp_coverage_slope']:+.4f}")

        traj = trends.get("trajectory", {})
        print(f"\n  [{traj.get('alert_level', 'INFO')}] {traj.get('description', '')}")

    # Write trends file
    trends_path = args.output_dir / "security-posture-trends.json"
    try:
        trends_path.write_text(json.dumps(trends, indent=2) + "\n")
    except OSError:
        pass


if __name__ == "__main__":
    main()
