#!/usr/bin/env python3
"""Reproducible LOC survey of the SDK's orchestration/durability machinery.

Canonical counting method behind the inventory table in
docs/design/CROSSPLANE_TEMPORAL_SUITABILITY_EVALUATION_2026-06-07.md (§2, R3-S5).
Re-run at the R1-S2 decision gate and diff against the committed figures.

Usage:
    python3 scripts/survey_orchestration_loc.py [--json]

Counts total physical lines (wc -l semantics) of *.py files per subsystem group.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "startd8"

# Subsystem groups, matching the §2 inventory table.
GROUPS: dict[str, list[str]] = {
    "contractors (checkpoint, queue, prime_contractor, integration_engine, batch_postmortem, ...)": [
        "contractors",
    ],
    "repair (orchestrator, staging, retry pipeline)": [
        "repair",
    ],
    "workflows (base, registry, builtin)": [
        "workflows",
    ],
    "resilience + ratelimit": [
        "resilience",
        "ratelimit",
    ],
    "events (bus, types)": [
        "events",
    ],
    "backend_codegen (deterministic output -- generation, not orchestration)": [
        "backend_codegen",
    ],
}


def count_group(subdirs: list[str]) -> tuple[int, int]:
    """Return (file_count, total_lines) for all .py files under the given subdirs."""
    files = 0
    lines = 0
    for sub in subdirs:
        base = SRC / sub
        if not base.is_dir():
            print(f"warning: missing subsystem dir {base}", file=sys.stderr)
            continue
        for path in sorted(base.rglob("*.py")):
            files += 1
            with open(path, "rb") as fh:
                lines += sum(1 for _ in fh)
    return files, lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    results = {}
    total_files = 0
    total_lines = 0
    for group, subdirs in GROUPS.items():
        files, lines = count_group(subdirs)
        results[group] = {"files": files, "lines": lines}
        total_files += files
        total_lines += lines
    results["TOTAL"] = {"files": total_files, "lines": total_lines}

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        width = max(len(g) for g in results)
        for group, r in results.items():
            print(f"{group:<{width}}  {r['files']:>4} files  {r['lines']:>7} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
