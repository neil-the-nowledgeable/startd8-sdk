#!/usr/bin/env python3
"""Re-score persisted behavioral cells for $0 — the Mottainai "generate once, re-score free" loop.

Given a batch root produced by ``run_behavioral_pilot.py`` (its ``cells.json`` + per-cell workdirs,
FR-T2-PERSIST), re-run the behavioral suite against each PERSISTED generated server with the CURRENT
harness — improved dependency closure, proto-path resolution, or suite — and write an updated
functional-coverage report. No LLM, no regeneration: the expensive generation is reused, only the
(cheap, deterministic) scoring is redone. This is how a harness fix recovers previously-degraded
cells without paying to generate again.

Usage:
    python3 scripts/rescore_behavioral.py out/behavioral-pilot/run-YYYYmmddTHHMMSS
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix.aggregate import aggregate_cells, build_matrix_markdown  # noqa: E402
from startd8.benchmark_matrix.behavioral.execute import run_behavioral_cell  # noqa: E402
from startd8.benchmark_matrix.runner import (  # noqa: E402
    STATUS_FAILED,
    STATUS_OK,
    CellResult,
    sandbox_dir_name,
    seed_filename,
)
from startd8.benchmark_matrix.sandbox import SandboxConfig  # noqa: E402

SEEDS_DIR = REPO / "docs" / "design" / "model-benchmark" / "seeds"


def _target_files(seed: dict) -> list:
    return ((seed.get("tasks") or [{}])[0].get("config", {}).get("context", {}).get("target_files")) or []


def rescore(batch: Path, seeds_dir: Path, *, no_network: bool = True,
            suite_tier_override: "str | None" = None) -> dict:
    """Re-score every cell in ``batch/cells.json`` against its persisted workdir. Returns a payload
    with per-cell functional coverage + per-model medians + how many cells the current harness
    recovered vs. the persisted run."""
    cells = json.loads((batch / "cells.json").read_text())
    cfg = SandboxConfig(no_network=no_network)
    seeds: dict = {}
    rescored, by_model = [], {}
    for c in cells:
        service, model, rep = c["service"], c["model"], c["repetition"]
        # Tier-aware (FR-20): derive the cell's generation tier from its cell_id, load the matching
        # seed, and locate the tier-suffixed workdir. ``suite_tier_override`` lets us score a cell's
        # persisted server with a DIFFERENT suite tier (FR-24 cross-tier pre-validation).
        cell_id = c.get("cell_id", "")
        tier = cell_id.split(":tier-")[-1] if ":tier-" in cell_id else "baseline"
        seed_name = seed_filename(service, tier)
        seed = seeds.setdefault((service, tier),
                                json.loads((seeds_dir / seed_name).read_text())
                                if (seeds_dir / seed_name).exists() else {})
        tfs = _target_files(seed)
        wd = batch / sandbox_dir_name(service, model, rep, tier=tier)
        server = wd / tfs[0] if tfs else wd
        prev = c.get("functional_coverage")
        if not server.exists():
            rescored.append({**c, "rescored_functional": None, "rescore_note": "no persisted server"})
            by_model.setdefault(model, []).append(None)
            continue
        nm = wd / "node_modules"
        if nm.is_dir():
            shutil.rmtree(nm)  # drop stale closure so the CURRENT vendored deps + proto paths apply
        r = run_behavioral_cell(seed, wd, service, tfs, cfg=cfg, tier=(suite_tier_override or tier))
        note = "" if r.functional is not None else (
            r.provenance.get("missing_module") or r.provenance.get("attempted_proto_path")
            or r.provenance.get("reason") or "degraded")
        rescored.append({**c, "rescored_functional": r.functional, "rescore_note": note,
                         "rescore_provenance": r.provenance, "prev_functional": prev})
        by_model.setdefault(model, []).append(r.functional)
    medians = {m: (statistics.median([v for v in vs if v is not None])
                   if any(v is not None for v in vs) else None) for m, vs in by_model.items()}
    recovered = sum(1 for x in rescored
                    if x.get("prev_functional") is None and x.get("rescored_functional") is not None)
    return {"batch": str(batch), "by_model_median": medians, "recovered_cells": recovered,
            "cells": rescored, "by_model_reps": by_model}


def _k1_matrix_view(payload: dict) -> str:
    """K1: render the leaderboard + Consistency view over the RESCORED functional scores — the real
    discriminating signal lives here, not in the pilot's inline report. Quality = behavioral coverage;
    a cell that didn't score is FAILED (excluded from quality, counted catastrophic-free as non-pass)."""
    cells = []
    for c in payload["cells"]:
        f = c.get("rescored_functional")
        cells.append(CellResult(
            cell_id=c.get("cell_id", ""), service=c["service"], model=c["model"],
            language=c.get("language", "unknown"), repetition=c["repetition"],
            status=STATUS_OK if f is not None else STATUS_FAILED, quality=f))
    return build_matrix_markdown(f"{Path(payload['batch']).name} (behavioral re-score)", "", aggregate_cells(cells))


def _report_md(payload: dict) -> str:
    lines = [f"# Behavioral re-score — `{Path(payload['batch']).name}`", "",
             f"> $0 re-score (no regeneration). Recovered {payload['recovered_cells']} cell(s) that "
             "the persisted run had left degraded.", ""]
    # K1 — leaderboard (peak) + consistency (reliability) over the real rescored scores.
    lines += [_k1_matrix_view(payload), "", "## Per-cell", ""]
    for c in payload["cells"]:
        fc = c["rescored_functional"]
        fcs = "N/A" if fc is None else f"{fc:.3f}"
        note = f"  — {c['rescore_note']}" if c.get("rescore_note") else ""
        lines.append(f"- `{c['model']}` rep{c['repetition']}: functional={fcs}{note}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("batch", help="batch root from run_behavioral_pilot.py (has cells.json)")
    ap.add_argument("--seeds", default=str(SEEDS_DIR))
    ap.add_argument("--suite-tier", default=None, choices=["baseline", "hardened"],
                    help="Score every persisted server with THIS suite tier instead of the cell's "
                         "generation tier (FR-24: cross-tier discrimination pre-validation).")
    args = ap.parse_args(argv)
    batch = Path(args.batch)
    if not (batch / "cells.json").is_file():
        print(f"ERROR: no cells.json in {batch} (run the pilot first)", file=sys.stderr)
        return 2
    payload = rescore(batch, Path(args.seeds), suite_tier_override=args.suite_tier)
    (batch / "cells.rescored.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    report = _report_md(payload)
    (batch / "report.rescored.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"artifacts: {batch}/report.rescored.md  +  cells.rescored.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
