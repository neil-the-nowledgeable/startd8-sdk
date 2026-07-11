#!/usr/bin/env python3
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Emit the benchmark's agent insights to ContextCore via AgentInsightBridge (T3 / Section C).

Build-time decisions/risks/lessons come from insights.yaml; optional run-time notable-cell insights
come from a benchmark run's cells.json. Degrades gracefully (no-op) when ContextCore is not installed.

Usage::

    python3 scripts/emit_benchmark_insights.py                          # build-time insights only
    python3 scripts/emit_benchmark_insights.py --cells <run>/cells.json # + notable-cell insights
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.integrations.contextcore import AgentInsightBridge  # noqa: E402
from startd8.integrations.insight_emission import (  # noqa: E402
    emit_insight_spec,
    emit_notable_cell_insights,
)

_DEFAULT_SPEC = (
    Path(__file__).resolve().parent.parent
    / "docs/design/benchmark-observability-tracking/insights.yaml"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", type=Path, default=_DEFAULT_SPEC, help="Insights spec YAML")
    ap.add_argument("--cells", type=Path, default=None, help="A run's cells.json for notable insights")
    ap.add_argument("--run-id", default=None, help="run_id label for notable-cell insights")
    args = ap.parse_args()

    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    project = spec.get("project", {})
    bridge = AgentInsightBridge(
        project_id=project.get("id", "startd8-benchmark"),
        agent_id=project.get("agent_id", "claude-opus-4-8"),
    )
    if not bridge.enabled:
        print("[warn] ContextCore agent module not available — insights emit as no-ops (graceful).")

    counts = emit_insight_spec(bridge, spec)
    print(f"Build-time: {counts['decisions']} decisions / {counts['risks']} risks / "
          f"{counts['lessons']} lessons / {counts['questions']} questions")

    if args.cells:
        n = emit_notable_cell_insights(bridge, args.cells, run_id=args.run_id)
        print(f"Run-time:   {n} notable-cell insights from {args.cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
