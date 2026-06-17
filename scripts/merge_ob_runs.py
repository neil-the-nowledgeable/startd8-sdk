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

Two union modes:

- **Default — model-supersede** (disjoint-model runs): a model present in a later input supersedes
  that model's cells in earlier inputs. So `merge_ob_runs.py OUT round3 round3-rerun-openai` keeps
  round3's 6 non-OpenAI models and replaces its OpenAI cells with the fresh re-run.

- **`--cell-union`** (inputs that SHARE models): key by (service, model, repetition) and keep the
  best-status cell across all inputs (ok < deps_missing < failed < timeout < infra_fail < skip). Use
  this to combine two *partial* runs of the same roster — e.g. an OpenAI run that quota-failed on 4
  services + a re-run of just those 4: the re-run's `ok` cells supersede the earlier `infra_fail`,
  producing one full roster. (This is how round3-final's combined OpenAI set was built.)

Output is a lightweight board dir (cells.json + aggregate.json + leaderboard.md only — no
sandboxes), matching round2-complete.

  # disjoint models (round2-complete pattern):
  python3 scripts/merge_ob_runs.py results/round3-final results/round3 results/round3-openai-combined
  # combine two partial same-model runs:
  python3 scripts/merge_ob_runs.py --cell-union results/round3-openai-combined \\
      results/round3-rerun-openai results/round3-rerun-openai-svc4
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix import CellResult, aggregate_cells, build_matrix_markdown  # noqa: E402
from startd8.benchmark_matrix.aggregate import DEFAULT_PASS_THRESHOLD  # noqa: E402


# Cell status preference for the cell-union mode (best first): a re-run that produced a
# real result supersedes an env failure. ok < deps_missing < failed < timeout < infra_fail < skip.
_STATUS_PRIO = {"ok": 0, "deps_missing": 1, "failed": 2, "timeout": 3, "infra_fail": 4, "budget_skip": 5}


def merge(out_dir: Path, inputs: list[Path], *, cell_union: bool = False) -> int:
    if cell_union:
        # CELL-LEVEL union: inputs may share models (two partial runs of the same roster).
        # Key by (service, model, repetition) and keep the best-status cell across all inputs —
        # so a re-run's `ok` cell supersedes an earlier `infra_fail`/`failed` for the same coord.
        best: dict[tuple, dict] = {}
        for inp in inputs:
            for c in json.loads((inp / "cells.json").read_text()):
                k = (c["service"], c["model"], c["repetition"])
                if k not in best or _STATUS_PRIO.get(c["status"], 9) < _STATUS_PRIO.get(best[k]["status"], 9):
                    best[k] = c
        merged = list(best.values())
    else:
        # MODEL-supersede union (default): each input owns disjoint models; a later input's
        # models replace the same model in earlier inputs (the round2-complete pattern).
        later_models = {
            c["model"] for inp in inputs[1:] for c in json.loads((inp / "cells.json").read_text())
        }
        merged = []
        for i, inp in enumerate(inputs):
            cells = json.loads((inp / "cells.json").read_text())
            if i == 0:
                cells = [c for c in cells if c["model"] not in later_models]
            merged.extend(cells)

    seen = {c["cell_id"] for c in merged}
    if len(seen) != len(merged):
        print(f"error: {len(merged) - len(seen)} duplicate cell_id(s) across inputs — refusing to merge "
              f"(use --cell-union when inputs share models/coordinates)", file=sys.stderr)
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
    cell_union = "--cell-union" in argv
    argv = [a for a in argv if a != "--cell-union"]
    if len(argv) < 3:
        print("usage: merge_ob_runs.py [--cell-union] OUT_DIR RUN1 RUN2 [MORE_RUNS...]", file=sys.stderr)
        print("  default: later runs' models supersede earlier (disjoint-model runs)", file=sys.stderr)
        print("  --cell-union: best-status per (service,model,rep) across inputs that SHARE models", file=sys.stderr)
        print("               (e.g. combine two partial OpenAI runs: re-run's ok beats earlier infra_fail)", file=sys.stderr)
        return 2
    out_dir, *inputs = (Path(a) for a in argv)
    for inp in inputs:
        if not (inp / "cells.json").exists():
            print(f"error: no cells.json in {inp}", file=sys.stderr)
            return 1
    return merge(out_dir, inputs, cell_union=cell_union)


if __name__ == "__main__":
    sys.exit(main())
