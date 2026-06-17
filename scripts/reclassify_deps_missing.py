#!/usr/bin/env python3
"""Reclassify failed cells as deps_missing — $0, the fairness pass rescore_ob skips.

``rescore_ob_benchmark.py`` only re-scores ``ok`` cells, so a cell that FAILED purely because a
required external dependency (gRPC/protobuf stubs, e.g. ``No module named 'demo_pb2'``) was absent
in the offline sandbox stays a catastrophic ``failed`` — unfairly zeroing the model. This pass
applies the same ``is_missing_deps_failure`` classifier the live runner uses (runner.py:312) to
already-run ``failed`` cells, upgrading them to ``deps_missing`` (excluded from scoring, not the
model's fault), then rebuilds aggregate.json + leaderboard.md.

This is the pass that produced ``round3-rescored`` (48 Python cells failed→deps_missing,
pass-rate 0.102→0.545). Run it AFTER ``rescore_ob_benchmark.py <dir> --write`` so the board
reflects both the composite/compile recalibration (ok cells) and the deps fairness (failed cells).

  # preview (no writes)
  python3 scripts/reclassify_deps_missing.py results/round3
  # persist (.bak kept once)
  python3 scripts/reclassify_deps_missing.py results/round3 --write
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import CellResult, aggregate_cells, build_matrix_markdown  # noqa: E402
from startd8.benchmark_matrix.aggregate import DEFAULT_PASS_THRESHOLD  # noqa: E402
from startd8.benchmark_matrix.runner import STATUS_DEPS_MISSING, STATUS_FAILED  # noqa: E402
from startd8.benchmark_matrix.scoring import is_missing_deps_failure  # noqa: E402


def reclassify(run_dir: Path, *, write: bool, backup: bool) -> int:
    cells = json.loads((run_dir / "cells.json").read_text())
    moved = []
    for c in cells:
        if c.get("status") == STATUS_FAILED:
            kind = is_missing_deps_failure(c.get("error") or "")
            if kind:
                c["status"] = STATUS_DEPS_MISSING
                moved.append((c["service"], c["model"], c.get("language"), kind))

    print(f"{len(moved)} cell(s) failed→deps_missing:")
    for svc, model, lang, kind in moved:
        print(f"  {svc:<22} {model:<34} {lang}  ({kind})")
    if not moved:
        print("  (none — no failed cell matched the missing-deps markers)")

    cell_objs = [CellResult.from_dict(c) for c in cells]
    agg = aggregate_cells(cell_objs, DEFAULT_PASS_THRESHOLD)
    spec = {}
    spec_path = run_dir / "run-spec.json"
    if spec_path.exists():
        spec = json.loads(spec_path.read_text())
    spec_name = spec.get("name") or "benchmark"
    spec_hash = spec.get("spec_hash") or (cells[0]["cell_id"].split(":", 1)[0] if cells else "")
    leaderboard = build_matrix_markdown(spec_name, spec_hash, agg)

    if write:
        for name, payload in (("cells.json", json.dumps(cells, indent=2)),
                              ("aggregate.json", json.dumps(agg, indent=2)),
                              ("leaderboard.md", leaderboard)):
            target = run_dir / name
            if backup and target.exists() and not (run_dir / f"{name}.bak").exists():
                shutil.copy2(target, run_dir / f"{name}.bak")
            target.write_text(payload)
        print(f"\n✔ wrote cells.json / aggregate.json / leaderboard.md to {run_dir}")
    else:
        print("\n(preview only — re-run with --write to persist)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path, help="A benchmark run directory (holds cells.json).")
    ap.add_argument("--write", action="store_true", help="Persist updated cells/aggregate/leaderboard.")
    ap.add_argument("--no-backup", action="store_true", help="With --write, do not keep .bak copies.")
    args = ap.parse_args(argv)
    if not (args.run_dir / "cells.json").exists():
        print(f"error: no cells.json in {args.run_dir}", file=sys.stderr)
        return 1
    return reclassify(args.run_dir, write=args.write, backup=not args.no_backup)


if __name__ == "__main__":
    sys.exit(main())
