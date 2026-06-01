#!/usr/bin/env python3
"""Seed the Proven Exemplar Pipeline registry from curated Grafana dashboard JSON
(REQ-PEP-320). Idempotent — re-running does not duplicate entries.

Usage:
    python3 scripts/seed_dashboard_exemplars.py \
        --dir docs/design/dashboard_creator/grafana_play_reference/exemplars \
        --registry exemplar-registry.json
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from startd8.dashboard_creator.exemplar_bridge import seed_reference_exemplars
from startd8.exemplars.registry import ExemplarRegistry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="Directory of dashboard *.json files")
    ap.add_argument("--registry", default="exemplar-registry.json",
                    help="Registry file to load/merge into and save")
    args = ap.parse_args()

    src = Path(args.dir)
    if not src.is_dir():
        print(f"error: not a directory: {src}", file=sys.stderr)
        return 2

    reg_path = Path(args.registry)
    registry = ExemplarRegistry.load(reg_path) if reg_path.exists() else ExemplarRegistry()
    added = seed_reference_exemplars(src, registry)
    registry.save(reg_path)

    dist = Counter(
        e.fingerprint.archetype for e in registry._exemplars
        if e.fingerprint.language == "grafana"
    )
    print(f"Seeded {added} dashboard exemplars into {reg_path}")
    for archetype, count in dist.most_common():
        print(f"  {count:4d}  {archetype}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
