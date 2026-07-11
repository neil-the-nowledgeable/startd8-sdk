#!/usr/bin/env python3
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Emit ContextCore delivery-tracking artifacts for the Summer 2026 Model Benchmark (T1.2).

Reads a milestone spec (default: the benchmark's milestones.yaml) and emits an epic→story→task
SpanState v2 hierarchy with honest backfilled statuses/timestamps + milestone dependencies, for a
ContextCore Business Observability burndown — $0, no LLM.

Usage::

    python3 scripts/emit_benchmark_tracking.py                 # → ./contextcore-tasks/ (dry, no install)
    python3 scripts/emit_benchmark_tracking.py --out /tmp/bm   # custom output dir
    python3 scripts/emit_benchmark_tracking.py --install       # also install to ~/.contextcore/state/
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from startd8.integrations.milestone_tracking import emit_milestone_tracking  # noqa: E402

_DEFAULT_SPEC = (
    Path(__file__).resolve().parent.parent
    / "docs/design/benchmark-observability-tracking/milestones.yaml"
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", type=Path, default=_DEFAULT_SPEC, help="Milestone spec YAML")
    ap.add_argument("--out", type=Path, default=Path("./contextcore-tasks-out"), help="Output dir")
    ap.add_argument("--install", action="store_true", help="Install to ~/.contextcore/state/")
    args = ap.parse_args()

    spec = yaml.safe_load(args.spec.read_text(encoding="utf-8"))
    result = emit_milestone_tracking(spec, args.out, install=args.install)

    counts = result.get("counts", {})
    print(f"Project:  {result.get('project_id')}  (sprint: {spec.get('project', {}).get('sprint')})")
    print(f"Emitted:  {counts.get('epics', 0)} epic / {counts.get('stories', 0)} stories / "
          f"{counts.get('tasks', 0)} tasks")
    print(f"Output:   {result.get('tasks_dir')}")
    if args.install and result.get("installed_to"):
        print(f"Installed: {result['installed_to']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
