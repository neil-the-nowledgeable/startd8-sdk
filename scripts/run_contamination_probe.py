#!/usr/bin/env python3
"""CodeBLEU contamination / memorization probe (FR-47) — $0, no execution.

Scores each generated service in a completed benchmark run against the canonical *public*
Online Boutique source. High CodeBLEU ⇒ likely memorization of the public corpus (a
credibility control, NOT a quality term).

  python3 scripts/run_contamination_probe.py <run_dir> --reference <microservices-demo>/src
  python3 scripts/run_contamination_probe.py <run_dir> --reference <ref> --out probe.json

NOTE: if the run was produced with the SDK's repair capability active, the scored artifacts are
repair-polished — the clean memorization signal comes from a repair-OFF run. On Python 3.14 C#
degrades (tree-sitter ABI vs codebleu pin); 8/9 OB services score.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix.contamination import codebleu_available, score_run  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run_dir", type=Path, help="Benchmark run dir (holds sandboxes/).")
    ap.add_argument("--reference", type=Path, required=True,
                    help="Canonical Online Boutique source dir (e.g. microservices-demo/src).")
    ap.add_argument("--out", type=Path, default=None, help="Write the full JSON report here.")
    args = ap.parse_args(argv)

    if not codebleu_available():
        print("error: codebleu not installed (pip install codebleu + tree-sitter-<lang>)", file=sys.stderr)
        return 1
    if not (args.run_dir / "sandboxes").exists():
        print(f"error: no sandboxes/ in {args.run_dir}", file=sys.stderr)
        return 1
    if not args.reference.exists():
        print(f"error: reference dir not found: {args.reference}", file=sys.stderr)
        return 1

    rep = score_run(args.run_dir, args.reference)
    print(f"scored {rep['n_scored']}/{rep['n_cells']} cells against {rep['reference_root']}")
    print("\nMean CodeBLEU vs upstream public OB (higher = more similar = more likely memorized):")
    for m, v in rep["model_mean_codebleu"].items():
        print(f"  {m:<42} {v:.3f}")
    degraded = sorted({c["service"] for c in rep["cells"] if not c["available"]})
    if degraded:
        print(f"\ndegraded (no score, FR-32): {', '.join(degraded)}")
    if args.out:
        args.out.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"\n✔ wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
