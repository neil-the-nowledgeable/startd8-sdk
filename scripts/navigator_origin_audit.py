#!/usr/bin/env python3
"""navigator_origin_audit — the Chrome Origin Audit (a sub-loop of the navigator loops).

Answers "where does this chrome come from?" for a navigator view. The apex a reader sees —

    <summary meta>   The Node model rendered as Nodes — a Kagami mirror of models.py …
    Why  …           Do  …
    Status  8 authored / 3 computed / 3 derived / 1 meta
    Shape   Nodes: 15 | Sections: 7

— is not free-floating text; each element reflects a source (a RenderProfile field, a computed
aggregate, or the node data). This audit traces every chrome element to its origin and flags any
**orphan** (chrome with no source value — text the Kagami mirror shouldn't be showing). chrome_score
= fraction of chrome elements that trace to a present source.

Usage:
    python3 scripts/navigator_origin_audit.py --source node-schema      # trace + score the chrome
    python3 scripts/navigator_origin_audit.py --source requirements
    python3 scripts/navigator_origin_audit.py --source capability-index --record   # append to ledger
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from navigator_pilot_loop import DEFAULT_SOURCE, LEDGER_DIR, PILOTS_BY_SOURCE, REPO, _nodes_for, _now


def _plan_and_profile(source: str, path):
    from startd8.navigator.project import nodes_to_wireframe_plan
    nodes = _nodes_for(source, path)
    plan = nodes_to_wireframe_plan(nodes)
    if source == "capability-index":
        from startd8.navigator.sources_capability import CAPABILITY_PROFILE as prof
    elif source == "node-schema":
        from startd8.navigator.sources_node_schema import NODE_SCHEMA_PROFILE as prof
    else:
        from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE as prof
    return nodes, plan, prof


def audit(source: str, path) -> Dict[str, Any]:
    from startd8.navigator.provenance import chrome_provenance
    nodes, plan, prof = _plan_and_profile(source, path)
    rows = chrome_provenance(nodes, plan, prof)
    present = sum(1 for r in rows if r["present"])
    return {"source": source, "rows": rows, "present": present, "total": len(rows),
            "chrome_score": round(present / len(rows), 3) if rows else 0.0,
            "orphans": [r["element"] for r in rows if not r["present"]]}


def _print(a: Dict[str, Any]) -> None:
    print(f"\n=== chrome origin audit — {a['source']} @ {_now()[:16]} ===")
    print(f"{'ELEMENT':14}{'ORIGIN':56}VALUE")
    print("-" * 120)
    for r in a["rows"]:
        mark = "" if r["present"] else "  ⚠ ORPHAN"
        val = str(r["value"])
        print(f"{r['element']:14}{r['origin']:56}{val[:44]}{mark}"[:150])
    print("-" * 120)
    print(f"chrome_score={a['chrome_score']}  ({a['present']}/{a['total']} elements trace to a source)"
          + (f"  · ORPHANS: {a['orphans']}" if a["orphans"] else "  · no orphans ✓"))


def _ledger_path(source: str) -> Path:
    tag = "" if source == "requirements" else f"-{source}"
    return LEDGER_DIR / f"ledger-origin{tag}.json"


def _record(source: str, a: Dict[str, Any]) -> None:
    p = _ledger_path(source)
    led = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []
    led.append({"when": _now(), "chrome_score": a["chrome_score"],
                "present": a["present"], "total": a["total"], "orphans": a["orphans"]})
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nrecorded → {p.relative_to(REPO)}")


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    choices=sorted(set(PILOTS_BY_SOURCE) | {"node-schema"}))
    ap.add_argument("--path", type=Path, default=None)
    ap.add_argument("--record", action="store_true", help="append chrome_score to the audit ledger")
    ap.add_argument("--json", action="store_true", help="emit the audit as JSON")
    args = ap.parse_args(argv[1:])
    a = audit(args.source, args.path)
    if args.json:
        print(json.dumps(a, indent=2))
    else:
        _print(a)
    if args.record:
        _record(args.source, a)
    return 0 if not a["orphans"] else 1  # orphan chrome fails (Kagami: mirror showing sourceless text)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
