#!/usr/bin/env python3
"""navigator_spec_delivery_loop — the Spec Delivery Loop (LOOP_CATALOG #6).

The disciplined, semi-autonomous path from an authored det-req SPEC to a landed IMPLEMENTATION.
It is the *forward* sibling of the improvement loops: where the Pilot/Content loops improve a node
that already exists, this loop turns a build-ready spec into merged code under engineering discipline.

The loop has six stages (full detail in the runbook `SPEC_DELIVERY_LOOP.md`):

  0. GATE      (this script — deterministic)  the spec is build-ready: name block · single-line FRs
               that parse · every FR has Name/Verify/Serves. FAIL → refuse to proceed.
  1. PREP      (out-of-cast agent)            name check + port-map/readiness; surface decisions.
  2. BUILD     (agent, isolated git worktree) never the primary tree; decisions baked in.
  3. GATE-2    (deterministic)                full suite + byte-identity (UNEDITED) + no-forbidden-
               import + ruff, pinned PYTHONPATH=<wt>/src.
  4. REVIEW    (fresh eyes — the human)       read the diff before anything lands.
  5. LAND      (git cadence)                  branch → FF main → restore to main; stage OWN files only.
  6. RECORD    (Mieruka)                      refresh the session ledger; register the outcome.

Only stage 0 (and the mechanical half of stage 3) is a pure script — the rest is agent+human
orchestration the runbook governs. This driver is the enforceable gate: it reuses the SDK's own
`det_req` parser (Kagami/Mottainai — the same parser the corpus is governed by, not a second one),
so a spec that would silently drop fields on a hard-wrap cannot pass. It is REQ-06 corpus governance
in embryo, scoped to the one precondition that guards a build.

Usage:
    python3 scripts/navigator_spec_delivery_loop.py --status            # readiness of every REQ-*.md
    python3 scripts/navigator_spec_delivery_loop.py REQ-05              # gate one spec (by key or path)
    python3 scripts/navigator_spec_delivery_loop.py --checklist         # print the 6-stage runbook
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Kagami (one home): the stage-0 build-readiness gate + its name-block regexes now LIVE in
# startd8.navigator.govern (REQ-06 corpus governance — `gate_spec` is the single-doc precondition
# `govern_corpus` generalizes). Import + re-export at module scope so `sdl.gate_spec` / `sdl._HANDLE`
# / `sdl._SEMNAME` / `sdl._FR_MARKER` keep resolving for existing callers and tests.
from startd8.navigator.govern import (  # noqa: E402,F401
    _FR_MARKER,
    _HANDLE,
    _SEMNAME,
    gate_spec,
)

SPEC_DIR = REPO / "docs/design/requirements-visualization"

# top-level (unindented) public def/class — the EB-3 reachability probe's subjects
_PUBLIC_DEF = re.compile(r"^(?:def|class)\s+([A-Za-z][A-Za-z0-9_]*)\s*[\(:]", re.MULTILINE)


# --------------------------------------------------------------------------- #
# stage 3 — the reachability probe (EB-3): "wired, not just built"
# --------------------------------------------------------------------------- #

def _public_symbols(path: Path) -> List[str]:
    """Top-level public ``def``/``class`` names in a Python file (skip ``_``-prefixed)."""
    text = path.read_text(encoding="utf-8")
    return [m.group(1) for m in _PUBLIC_DEF.finditer(text) if not m.group(1).startswith("_")]


def reachability(paths: List[Path]) -> List[Dict[str, Any]]:
    """For each public symbol defined in ``paths``, find call sites elsewhere in ``src/`` + ``scripts/``.

    Grounds the HTH retro's clause 5 ("wired, not just built"): a ported/lifted symbol that is tested
    but never *called* in the real tree is dormant (D-2 ``validate_graph_model`` was exactly this). A
    reference only in an ``__init__.py`` re-export is ``export-only`` (wired to the surface, not a
    consumer). Zero references outside the defining file → ``DORMANT``.

    Scan roots are ``src/`` (product) **and** ``scripts/`` (tooling) — a symbol consumed by a driver
    script (e.g. ``gate_spec`` from the loop script) is genuinely wired, so a ``src``-only scan would
    cry wolf (found by HTH on REQ-06). ``tests/`` is deliberately EXCLUDED: a test-only consumer is the
    "tested but not wired" dormant this probe exists to catch, so it must not count as a call site.
    """
    scan_roots = [REPO / "src", REPO / "scripts"]
    src_files = [f for root in scan_roots if root.is_dir() for f in root.rglob("*.py")]
    cache = {f: f.read_text(encoding="utf-8", errors="replace") for f in src_files}
    out: List[Dict[str, Any]] = []
    for path in paths:
        rp = path.resolve()
        for sym in _public_symbols(path):
            pat = re.compile(rf"\b{re.escape(sym)}\b")
            real = export_only = 0
            for f, text in cache.items():
                if f.resolve() == rp:
                    continue
                if not pat.search(text):
                    continue
                if f.name == "__init__.py":
                    export_only += 1
                else:
                    real += 1
            status = "wired" if real else ("export-only" if export_only else "DORMANT")
            out.append({"symbol": sym, "path": path, "real": real,
                        "export_only": export_only, "status": status})
    return out


def run_reachability(paths: List[Path], strict: bool) -> int:
    files = [p for p in paths if p.suffix == ".py" and p.is_file()]
    missing = [p for p in paths if p not in files]
    for p in missing:
        print(f"skip (not a .py file): {p}", file=sys.stderr)
    rows = reachability(files)
    print(f"\n=== reachability probe — {len(rows)} public symbol(s) across {len(files)} file(s) ===")
    print(f"{'SYMBOL':38}{'STATUS':13}refs (real/export-only)")
    print("-" * 80)
    dormant = 0
    for r in sorted(rows, key=lambda r: (r["status"] != "DORMANT", r["symbol"])):
        if r["status"] == "DORMANT":
            dormant += 1
        print(f"{r['symbol']:38}{r['status']:13}{r['real']}/{r['export_only']}")
    if dormant:
        print(f"\n⚠ {dormant} DORMANT symbol(s) — built/ported but no call site in src/ "
              f"(wire it in the real path, or soft-label the claim).")
    else:
        print("\n✓ no dormant symbols — every public symbol has a call site.")
    return 1 if (dormant and strict) else 0


# --------------------------------------------------------------------------- #
# resolution + rendering
# --------------------------------------------------------------------------- #

def _resolve(key_or_path: str) -> Optional[Path]:
    p = Path(key_or_path)
    if p.is_file():
        return p
    # by REQ key, e.g. "REQ-05" or "05"
    stem = key_or_path if key_or_path.upper().startswith("REQ-") else f"REQ-{key_or_path}"
    hits = sorted(SPEC_DIR.glob(f"{stem}-*.md")) + sorted(SPEC_DIR.glob(f"{stem}.md"))
    return hits[0] if hits else None


def _print_verdict(v: Dict[str, Any]) -> None:
    rel = v["path"].relative_to(REPO)
    banner = "BUILD-READY ✓" if v["ok"] else "BLOCKED ✗"
    print(f"\n=== {rel.name} — {banner} ({v['frs']} FRs) ===")
    for name, ok, detail in v["checks"]:
        print(f"  [{'✓' if ok else '✗'}] {name:12} {detail}")
    if v["ok"]:
        print("  → proceed to stage 1 (PREP). See --checklist for the full loop.")
    else:
        print(f"  → NOT build-ready. Fix: {', '.join(v['blocked'])}. Re-run the gate before building.")


CHECKLIST = """\
Spec Delivery Loop — the 6 stages (runbook: docs/design/requirements-visualization/SPEC_DELIVERY_LOOP.md)

  0. GATE      python3 scripts/navigator_spec_delivery_loop.py REQ-NN   (must PASS to proceed)
  1. PREP      out-of-cast agent: name check + port-map/readiness; surface decisions to the human
  2. BUILD     agent in an ISOLATED git worktree (never the primary tree); locked decisions baked in
  3. GATE-2    PYTHONPATH=<wt>/src pytest <suites>  +  byte-identity UNEDITED  +  no-forbidden-import  +  ruff
               + reachability probe: navigator_spec_delivery_loop.py --reachability <touched.py...>
                 ("wired, not just built" — every new/ported public symbol needs a call site)
  4. REVIEW    the human reads the diff (fresh eyes) BEFORE anything lands
  5. LAND      branch → FF main → restore to main; stage OWN files only (file-disjoint from other agents)
  6. RECORD    refresh SESSION_LEDGER; register the outcome

Human checkpoints (what keeps it *semi*-autonomous, not autonomous): decisions in stage 1, diff review in stage 4.
"""


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?", help="REQ key (REQ-05 / 05) or path to a spec .md")
    ap.add_argument("--status", action="store_true", help="gate every REQ-*.md in the spec dir")
    ap.add_argument("--checklist", action="store_true", help="print the 6-stage delivery runbook")
    ap.add_argument("--reachability", nargs="+", metavar="FILE.py", type=Path,
                    help="GATE-2 reachability probe: flag public symbols in these files with no call site")
    ap.add_argument("--strict", action="store_true",
                    help="with --reachability: exit 1 if any symbol is dormant (default: advisory)")
    args = ap.parse_args(argv[1:])

    if args.checklist:
        print(CHECKLIST)
        return 0

    if args.reachability:
        return run_reachability(args.reachability, strict=args.strict)

    if args.status:
        specs = sorted(SPEC_DIR.glob("REQ-*.md"))
        print(f"{'SPEC':52}{'READY':8}blockers")
        print("-" * 100)
        n_blocked = 0
        for s in specs:
            try:
                v = gate_spec(s)
            except (OSError, UnicodeDecodeError) as exc:
                # One unreadable/non-UTF-8 spec must not abort the whole survey.
                n_blocked += 1
                print(f"{s.name:52}{'✗':8}unreadable: {exc}"[:150])
                continue
            if not v["ok"]:
                n_blocked += 1
            print(f"{s.name:52}{'✓' if v['ok'] else '✗':8}"
                  f"{'' if v['ok'] else ', '.join(v['blocked'])}"[:150])
        print(f"\n{len(specs)} specs — {len(specs) - n_blocked} build-ready, {n_blocked} blocked.")
        return 0

    if not args.spec:
        ap.print_help()
        return 2

    path = _resolve(args.spec)
    if path is None:
        print(f"error: no spec found for {args.spec!r} in {SPEC_DIR.relative_to(REPO)}", file=sys.stderr)
        return 1
    v = gate_spec(path)
    _print_verdict(v)
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
