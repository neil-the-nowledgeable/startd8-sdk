#!/usr/bin/env python3
"""Merge OB benchmark runs into one board — $0, no LLM (the round2-complete union, packaged).

Concatenates the ``cells.json`` of several already-scored runs and rebuilds
``aggregate.json`` + ``leaderboard.md`` for the union. This is the proven pattern behind
``round2-complete`` (= ``round2-expose-shadow`` ∪ ``round2-openai``): each run owns a disjoint
set of models, so the merge is a plain concatenation — then re-aggregate.

Use it to splice a fresh OpenAI-only re-run onto rescored non-OpenAI cells without paying to
regenerate everything (see docs/HOWTO_RERUN_ROUND3.md). Both inputs must already be scored by
the *current* scoring layer — rescore each in place first (scripts/rescore_ob_benchmark.py
<dir> --write) so the merged board is methodologically uniform.

**Later inputs win by model:** a model present in a later input supersedes that model's cells in
earlier inputs. So `merge_ob_runs.py OUT round3 round3-rerun-openai` keeps round3's 6 non-OpenAI
models and replaces its stale OpenAI cells with the fresh re-run.

Output is a lightweight board dir (cells.json + aggregate.json + leaderboard.md only — no
sandboxes), matching round2-complete.

  python3 scripts/merge_ob_runs.py results/round3-final results/round3 results/round3-rerun-openai
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import CellResult, aggregate_cells, build_matrix_markdown  # noqa: E402
from startd8.benchmark_matrix.aggregate import DEFAULT_PASS_THRESHOLD  # noqa: E402


def merge(out_dir: Path, inputs: list[Path]) -> int:
    # Models owned by a later input supersede the same model in earlier inputs.
    later_models = {
        c["model"] for inp in inputs[1:] for c in json.loads((inp / "cells.json").read_text())
    }
    merged: list[dict] = []
    for i, inp in enumerate(inputs):
        cells = json.loads((inp / "cells.json").read_text())
        if i == 0:
            cells = [c for c in cells if c["model"] not in later_models]
        merged.extend(cells)

    seen = {c["cell_id"] for c in merged}
    if len(seen) != len(merged):
        print(f"error: {len(merged) - len(seen)} duplicate cell_id(s) across inputs — refusing to merge",
              file=sys.stderr)
        return 1

    cell_objs = [CellResult.from_dict(c) for c in merged]
    agg = aggregate_cells(cell_objs, DEFAULT_PASS_THRESHOLD)
    # spec meta for the leaderboard header: reuse the base run's run-spec.json if present.
    spec = {}
    base_spec = inputs[0] / "run-spec.json"
    if base_spec.exists():
        spec = json.loads(base_spec.read_text())
    spec_name = spec.get("name") or "benchmark-merged"
    spec_hash = spec.get("spec_hash") or (merged[0]["cell_id"].split(":", 1)[0] if merged else "")
    leaderboard = build_matrix_markdown(spec_name, spec_hash, agg)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cells.json").write_text(json.dumps(merged, indent=2))
    (out_dir / "aggregate.json").write_text(json.dumps(agg, indent=2))
    (out_dir / "leaderboard.md").write_text(leaderboard)
    provs = sorted({c["model"].split(":", 1)[0] for c in merged})
    print(f"✔ merged {len(merged)} cells from {len(inputs)} runs ({', '.join(provs)}) -> {out_dir}")
    print(f"  cells.json / aggregate.json / leaderboard.md written")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        print("usage: merge_ob_runs.py OUT_DIR BASE_RUN OPENAI_RUN [MORE_RUNS...]", file=sys.stderr)
        print("  (BASE_RUN first; later runs' models supersede the base by model)", file=sys.stderr)
        return 2
    out_dir, *inputs = (Path(a) for a in argv)
    for inp in inputs:
        if not (inp / "cells.json").exists():
            print(f"error: no cells.json in {inp}", file=sys.stderr)
            return 1
    return merge(out_dir, inputs)


if __name__ == "__main__":
    sys.exit(main())
