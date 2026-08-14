#!/usr/bin/env python3
"""navigator_cruft_loop — the Cruft Sentinel (a navigator loop that triggers /audit-then-metabolize).

Stance: **all content is cruft until proven otherwise.** A rendered navigator view is presumed
guilty — every chrome element must PROVE it earns its place by tracing to a source (a RenderProfile
field, a computed aggregate, or the node data). What can't be proven is cruft:

  - chrome ORPHANS  — an apex/structural element with no traceable origin (Kagami: sourceless text);
  - cruft_lint GAPS — mechanical bleed / non-partitioning zero-counts / unrendered markdown.

When cruft is found, this loop does not try to fix it inline — it **triggers `/audit-then-metabolize`**
(the diagnose→cure composition) on the offending corpus, printing the exact invocation and writing a
findings artifact the ATM pass consumes. Clean ⇒ exit 0; cruft ⇒ exit 1 + the trigger directive.

Usage:
    python3 scripts/navigator_cruft_loop.py --all                 # sweep every source
    python3 scripts/navigator_cruft_loop.py --source node-schema  # one view
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from navigator_pilot_loop import LEDGER_DIR, PILOTS_BY_SOURCE, REPO, _cruft_lint, _now, _render_html
from navigator_origin_audit import audit

SOURCES = sorted(set(PILOTS_BY_SOURCE) | {"node-schema"})


def _cruft_lint_gaps(source: str, path) -> List[str]:
    """Run the rung-4 cruft_lint on the rendered HTML; return its deterministic gap lines.

    Note: cruft_lint on a JS-rendered page yields a couple of known JS-template redundancy
    false-positives; those are reported but flagged, so they don't masquerade as content cruft.
    """
    safe = source.replace("/", "_")
    html = LEDGER_DIR / f"cruft-{safe}.html"
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _render_html(source, path, html)
    line = _cruft_lint(html, path)  # one-line summary ("N gap(s), M candidate(s)") or a warn note
    return [line] if line and "0 gap(s)" not in line else []


def sweep(source: str, path) -> Dict[str, Any]:
    a = audit(source, path)  # chrome provenance → orphans are unproven chrome (cruft)
    orphans = a["orphans"]
    lint = _cruft_lint_gaps(source, path)
    cruft = list(orphans)  # deterministic cruft = chrome orphans; lint is advisory (JS-template FPs)
    return {"source": source, "chrome_score": a["chrome_score"], "chrome_orphans": orphans,
            "cruft_lint": lint, "cruft_count": len(cruft), "cruft": cruft}


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=SOURCES)
    ap.add_argument("--all", action="store_true", help="sweep every source")
    ap.add_argument("--path", type=Path, default=None)
    args = ap.parse_args(argv[1:])
    if not args.source and not args.all:
        ap.print_help()
        return 2
    sources = SOURCES if args.all else [args.source]

    print(f"\n=== cruft sentinel — all content is cruft until proven @ {_now()[:16]} ===")
    results, dirty = [], []
    for s in sources:
        r = sweep(s, args.path if not args.all else None)
        results.append(r)
        mark = f"⚠ {r['cruft_count']} CRUFT: {', '.join(r['cruft'])}" if r["cruft"] else "clean ✓"
        print(f"  {s:16} provenance {r['chrome_score']}  {mark}")
        if r["cruft_lint"]:
            print(f"  {'':16}   cruft_lint(advisory): {r['cruft_lint'][0]}")
        if r["cruft"]:
            dirty.append(s)

    ledger = LEDGER_DIR / "ledger-cruft.json"
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    hist = json.loads(ledger.read_text(encoding="utf-8")) if ledger.is_file() else []
    hist.append({"when": _now(), "results": results, "dirty": dirty})
    ledger.write_text(json.dumps(hist, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if dirty:
        corpus = ", ".join(dirty)
        print("\n  CRUFT FOUND — content that did not prove its origin.")
        print(f"  TRIGGER → /audit-then-metabolize  (corpus: navigator views [{corpus}])")
        print(f"  findings → {ledger.relative_to(REPO)}")
        return 1
    print("\n  no cruft — all chrome proven its origin ✓ (no /audit-then-metabolize needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
