#!/usr/bin/env python3
# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Post-hoc execution-cell tracking for a finished benchmark run (T4 / Section B).

Pure reader over a run's ``run-spec.json`` + ``cells.json`` — emits the ContextCore execution-cell
hierarchy (epic=run, story=service, task=cell), rolls up cost, and optionally emits notable-cell
insights. Touches no run-loop code (FR-25 non-blocking).

Usage::

    python3 scripts/track_benchmark_run.py --run-dir <.../benchmark-runs/<hash>>
    python3 scripts/track_benchmark_run.py --run-dir <dir> --mode count --install --insights
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.benchmark_matrix.tracking import reconstruct_run_tracking  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True, help="A finished benchmark run directory")
    ap.add_argument("--mode", choices=["auto", "cell", "count"], default="auto", help="OQ-2 granularity")
    ap.add_argument("--out", type=Path, default=None, help="Output dir (default: <run-dir>/contextcore-tracking)")
    ap.add_argument("--install", action="store_true", help="Install state files to ~/.contextcore/state/")
    ap.add_argument("--insights", action="store_true", help="Also emit notable-cell insights")
    args = ap.parse_args()

    bridge = None
    if args.insights:
        from startd8.integrations.contextcore import AgentInsightBridge

        bridge = AgentInsightBridge(project_id="startd8-benchmark", agent_id="claude-opus-4-8")

    s = reconstruct_run_tracking(
        args.run_dir, mode=args.mode, output_dir=args.out, install=args.install, insight_bridge=bridge
    )
    print(f"Run:         {s['run_id']}  (project: {s['project_id']})")
    print(f"Granularity: {s['granularity']}")
    print(f"Hierarchy:   {s['counts']['services']} services / {s['counts']['cell_tasks']} cell-tasks "
          f"({s['counts']['cells']} cells)")
    print(f"Cost:        ${s['cost_total_usd']:.4f} total")
    if args.insights:
        print(f"Insights:    {s['notable_insights']} notable-cell insights")
    print(f"Output:      {s['tasks_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
