#!/usr/bin/env python3
"""navigator_inspect_loop — the Inspect Loop (find derivative value in surviving chrome).

The constructive counterpart to the Cruft Sentinel. Where the cruft loop presumes GUILT (prove your
origin or be purged), the inspect loop presumes a LEGACY VALUE: the non-node-driven chrome that
survived the cruft pass (masthead · summary band · legend) was built for a reason. Instead of asking
"is this cruft?", it asks "what **derivative information or updated context** would make this useful
in the CURRENT (node-debugging) sense?" — and emits a repurpose/enhancement worklist, not a purge.

Verdicts per element: **realized** (derivative value already serving) · **candidate** (latent value
worth wiring) · **uninspected** (chrome with no inspection yet). inspect_score = realized / total.
When candidates remain, it recommends **/enhancement-backlog** to wire the derivative value (mirrors
the cruft loop's /audit-then-metabolize trigger, opposite polarity).

Usage:
    python3 scripts/navigator_inspect_loop.py --source requirements   # inspect one view's chrome
    python3 scripts/navigator_inspect_loop.py --all                   # sweep every view
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from navigator_pilot_loop import LEDGER_DIR, PILOTS_BY_SOURCE, REPO, _nodes_for, _now

SOURCES = sorted(set(PILOTS_BY_SOURCE) | {"node-schema"})


def _profile_for(source: str):
    if source == "capability-index":
        from startd8.navigator.sources_capability import CAPABILITY_PROFILE as p
    elif source == "node-schema":
        from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE as p
    else:
        from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE as p
    return p


def inspect(source: str, path) -> Dict[str, Any]:
    from startd8.navigator.inspect import inspect_elements
    from startd8.navigator.project import nodes_to_wireframe_plan
    nodes = _nodes_for(source, path)
    rows = inspect_elements(nodes, nodes_to_wireframe_plan(nodes), _profile_for(source))
    realized = sum(1 for r in rows if r["verdict"] == "realized")
    candidates = [r for r in rows if r["verdict"] == "candidate"]
    uninspected = [r["element"] for r in rows if r["verdict"] == "uninspected"]
    return {"source": source, "rows": rows, "realized": realized, "total": len(rows),
            "inspect_score": round(realized / len(rows), 3) if rows else 0.0,
            "candidates": candidates, "uninspected": uninspected}


def _print(a: Dict[str, Any]) -> None:
    print(f"\n=== inspect loop — derivative value of non-node-driven chrome ({a['source']}) @ {_now()[:16]} ===")
    for r in a["rows"]:
        tag = {"realized": "✓ realized", "candidate": "◆ CANDIDATE", "uninspected": "? uninspected"}[r["verdict"]]
        print(f"  {r['element']:14}{tag}")
        print(f"  {'':14}   was:        {r['original']}")
        if r["derivative"]:
            print(f"  {'':14}   derivative: {r['derivative']}")
    print(f"\n  inspect_score={a['inspect_score']}  ({a['realized']}/{a['total']} realized)")
    if a["candidates"]:
        names = ", ".join(r["element"] for r in a["candidates"])
        print(f"  DERIVATIVE VALUE to wire ({len(a['candidates'])}): {names}")
        print("  → /enhancement-backlog  (realize the derivative value; wire the plumbing that exists)")
    if a["uninspected"]:
        print(f"  UNINSPECTED chrome (add an inspection): {', '.join(a['uninspected'])}")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--path", type=Path, default=None)
    ap.add_argument("--record", action="store_true", help="append inspect_score to the ledger")
    args = ap.parse_args(argv[1:])
    if not args.source and not args.all:
        ap.print_help()
        return 2
    sources = SOURCES if args.all else [args.source]
    results = [inspect(s, args.path if not args.all else None) for s in sources]
    for a in results:
        _print(a)
    if args.record:
        ledger = LEDGER_DIR / "ledger-inspect.json"
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        hist = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
        hist.append({"when": _now(), "results": [
            {"source": a["source"], "inspect_score": a["inspect_score"],
             "candidates": [r["element"] for r in a["candidates"]]} for a in results]})
        ledger.write_text(json.dumps(hist, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nrecorded → {ledger.relative_to(REPO)}")
    # Candidates are opportunities, not failures — exit 0 (this loop generates, it doesn't gate).
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
