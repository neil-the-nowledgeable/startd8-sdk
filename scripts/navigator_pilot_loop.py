#!/usr/bin/env python3
"""navigator_pilot_loop — repeatable per-requirement improvement loop for the dogfood navigator.

The requirements-visualization capability renders REQ-01's own FRs as Nodes. This drives the
§6 operating recipe (TOP_DOWN_IMPROVEMENT_PLAN) one FR at a time, measurably:

    baseline  →  diagnose  →  [you apply the smallest fix]  →  verify  →  record

Stateful via a corpus ledger (docs/design/requirements-visualization/_pilot/): the first run for
an FR snapshots a BASELINE; later runs are VERIFY passes that compute the before→after delta.

Usage:
    python3 scripts/navigator_pilot_loop.py FR-6                 # baseline + diagnose (first run)
    #   ... apply the smallest fix the diagnosis names ...
    python3 scripts/navigator_pilot_loop.py FR-6 --verify        # delta vs baseline, record it
    python3 scripts/navigator_pilot_loop.py FR-6 --reset         # drop this FR's ledger, start over
    python3 scripts/navigator_pilot_loop.py --status             # show all pilots' current scores

Metrics per FR node (the glance-approvability the architect acceptance test cares about):
    status_key · confidence · fr_health · lives(count/types) · lives_resolve · approve_prompts
A composite pilot_score in [0,1] rolls them up so improvement is a single moving number.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

REQ01 = REPO / "docs/design/requirements-visualization/REQ-01-sdk-node-home.md"
LEDGER_DIR = REPO / "docs/design/requirements-visualization/_pilot"
PILOTS = ("FR-6", "FR-4", "FR-8")  # the confirmed trio, in causal order
CRUFT_LINT = Path.home() / "Documents/dev/dev-os/scripts/cruft_lint.py"


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #

def _lives_types(node: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for ev in node.get("lives", []):
        out[ev.get("type", "?")] = out.get(ev.get("type", "?"), 0) + 1
    return out


def _resolve_ref(ref: str) -> bool:
    """A Lives ref resolves iff its path exists on disk (strip a git:<sha>: prefix if present)."""
    path = ref
    if ref.startswith("git:"):
        parts = ref.split(":", 2)
        path = parts[2] if len(parts) == 3 else ref
    return (REPO / path).exists()


def _pilot_score(m: Dict[str, Any]) -> float:
    """Glance-approvability rollup in [0,1] — the moving number a pilot improves."""
    score = 0.0
    if m["status_key"] in ("grounded", "built"):
        score += 0.30
    if (m["confidence"] or 0) >= 0.9:
        score += 0.20
    if m["lives_count"] and m["lives_resolve"] == m["lives_count"]:
        score += 0.20
    if m["fr_health"] not in ("", "n/a", None):
        score += 0.15
    if m["approve_prompts"]:
        score += 0.15
    return round(score, 3)


def _metrics_for(fr_id: str, req: Path) -> Optional[Dict[str, Any]]:
    from startd8.navigator.sources_requirements import nodes_from_requirements

    nodes = nodes_from_requirements(req)
    node = None
    for n in nodes:
        nd = {
            "key": n.key,
            "confidence": n.confidence,
            "ships_when": n.ships_when,
            "route_state": n.route_state,
            "lives": [{"type": e.type, "ref": e.ref} for e in n.lives],
            "attributes": dict(n.attributes),
        }
        if n.key == fr_id:
            node = nd
            break
    if node is None:
        return None
    a = node["attributes"]
    types = _lives_types(node)
    refs = [e["ref"] for e in node["lives"]]
    m = {
        "fr": fr_id,
        "status_key": a.get("status_key", ""),
        "confidence": node["confidence"],
        "fr_health": a.get("fr_health", ""),
        "lives_count": len(refs),
        "lives_types": types,
        "lives_resolve": sum(1 for r in refs if _resolve_ref(r)),
        "approve_prompts": bool(a.get("approve_prompts")),
        "ships_when": bool(node["ships_when"]),
    }
    m["pilot_score"] = _pilot_score(m)
    return m


def _top_gap(m: Dict[str, Any]) -> str:
    """The single highest-value fix to attempt next for this FR (actionable, ordered)."""
    t = ",".join(f"{k}:{v}" for k, v in m["lives_types"].items()) or "none"
    if m["status_key"] not in ("grounded", "built"):
        return (f"STATUS is {m['status_key']!r} — cite a code Lives ref for the implementation "
                f"(currently {t}); a built FR that cites only tests reads as spec.")
    if m["lives_count"] and m["lives_resolve"] < m["lives_count"]:
        return (f"EVIDENCE — {m['lives_count'] - m['lives_resolve']} of {m['lives_count']} Lives "
                "refs do not resolve on disk; fix the path or sha.")
    if (m["confidence"] or 0) < 0.9:
        return (f"CONFIDENCE is {m['confidence']} — cite BOTH code AND test Lives so "
                f"default_confidence yields 0.9 (currently {t}). If the extractor drops one type "
                "per FR, that is the FR-6 fidelity gap.")
    if m["fr_health"] in ("", "n/a", None):
        return "HEALTH — fr_health is n/a; the vendor_thin fr_health helper is not producing a verdict."
    if not m["approve_prompts"]:
        return "SIGN-OFF — no APPROVE? prompt on this FR; add one so it lights up the per-item sign-off."
    return "glance-approvable ✓ — no mechanical gap; promote as an exemplar."


# --------------------------------------------------------------------------- #
# diagnose helpers
# --------------------------------------------------------------------------- #

def _render_html(req: Path, out: Path) -> None:
    from startd8.navigator.sources_requirements import (
        REQUIREMENTS_PROFILE,
        nodes_from_requirements,
    )
    from startd8.navigator.project import render_nodes_html

    nodes = nodes_from_requirements(req)
    render_nodes_html(nodes, out, project_root=str(req.parent), profile=REQUIREMENTS_PROFILE)


def _cruft_lint(html: Path, req: Path) -> str:
    if not CRUFT_LINT.is_file():
        return f"(cruft_lint not found at {CRUFT_LINT} — run /cruft-audit by hand per the runbook)"
    try:
        r = subprocess.run(
            [sys.executable, str(CRUFT_LINT), str(html), f"--source={req}"],
            capture_output=True, text=True, timeout=60,
        )
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "(no output)"
    except (subprocess.SubprocessError, OSError) as e:
        return f"(cruft_lint failed: {e})"


# --------------------------------------------------------------------------- #
# ledger
# --------------------------------------------------------------------------- #

def _ledger_path() -> Path:
    return LEDGER_DIR / "ledger.json"


def _load_ledger() -> Dict[str, List[Dict[str, Any]]]:
    p = _ledger_path()
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_ledger(led: Dict[str, List[Dict[str, Any]]]) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _ledger_path().write_text(json.dumps(led, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _render_ledger_md(led)


def _render_ledger_md(led: Dict[str, List[Dict[str, Any]]]) -> None:
    lines = ["# Navigator dogfood — pilot improvement ledger", "",
             "Repeatable per-FR loop (see `PILOT_IMPROVEMENT_LOOP.md`). Auto-generated; do not hand-edit.",
             ""]
    for fr in PILOTS:
        entries = led.get(fr, [])
        if not entries:
            lines += [f"## {fr} — not started", ""]
            continue
        base = entries[0]["metrics"]["pilot_score"]
        last = entries[-1]["metrics"]["pilot_score"]
        arrow = "→" if last == base else ("↑" if last > base else "↓")
        lines += [f"## {fr} — score {base} {arrow} {last} ({len(entries)} pass(es))", "",
                  "| # | phase | when | status | conf | health | lives(resolve) | appr | score |",
                  "|---|-------|------|--------|------|--------|----------------|------|-------|"]
        for i, e in enumerate(entries):
            m = e["metrics"]
            t = ",".join(f"{k}:{v}" for k, v in m["lives_types"].items()) or "—"
            lines.append(
                f"| {i} | {e['phase']} | {e['when'][:16]} | {m['status_key']} | {m['confidence']} | "
                f"{m['fr_health'] or 'n/a'} | {t} ({m['lives_resolve']}/{m['lives_count']}) | "
                f"{'Y' if m['approve_prompts'] else '-'} | {m['pilot_score']} |")
        lines += ["", f"**Next gap:** {_top_gap(entries[-1]['metrics'])}", ""]
    (LEDGER_DIR / "ledger.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def _print_metrics(m: Dict[str, Any]) -> None:
    t = ",".join(f"{k}:{v}" for k, v in m["lives_types"].items()) or "—"
    print(f"  status={m['status_key']}  confidence={m['confidence']}  fr_health={m['fr_health'] or 'n/a'}")
    print(f"  lives={t} ({m['lives_resolve']}/{m['lives_count']} resolve)  "
          f"approve_prompts={'yes' if m['approve_prompts'] else 'no'}")
    print(f"  pilot_score={m['pilot_score']}")


def run_pilot(fr_id: str, req: Path, verify: bool, reset: bool) -> int:
    if fr_id not in PILOTS:
        print(f"warning: {fr_id} is not in the confirmed pilot trio {PILOTS}", file=sys.stderr)
    led = _load_ledger()
    if reset:
        led.pop(fr_id, None)
        _save_ledger(led)
        print(f"reset ledger for {fr_id}")
        return 0

    m = _metrics_for(fr_id, req)
    if m is None:
        print(f"error: {fr_id} not found in {req}", file=sys.stderr)
        return 1

    entries = led.setdefault(fr_id, [])
    phase = "verify" if (verify and entries) else "baseline"
    if phase == "baseline" and entries:
        print(f"note: {fr_id} already has a baseline; recording another baseline "
              "(use --verify to record a delta pass, --reset to start over)")

    # diagnose (both phases): render + cruft_lint + evidence gate + top gap
    html = LEDGER_DIR / f"{fr_id}.html"
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _render_html(req, html)
    cruft = _cruft_lint(html, req)

    print(f"\n=== {fr_id} — {phase} @ {_now()[:16]} ===")
    _print_metrics(m)
    print(f"  cruft_lint: {cruft}")
    print(f"  TOP GAP → {_top_gap(m)}")

    if phase == "verify":
        base = entries[0]["metrics"]
        d = round(m["pilot_score"] - base["pilot_score"], 3)
        sign = "+" if d >= 0 else ""
        print(f"\n  DELTA vs baseline: pilot_score {base['pilot_score']} → {m['pilot_score']} ({sign}{d})")
        for k in ("status_key", "confidence", "fr_health"):
            if base[k] != m[k]:
                print(f"    {k}: {base[k]!r} → {m[k]!r}")

    entries.append({"phase": phase, "when": _now(), "metrics": m,
                    "cruft_lint": cruft, "top_gap": _top_gap(m)})
    _save_ledger(led)
    print(f"\nrecorded {phase} for {fr_id} → {_ledger_path().relative_to(REPO)}")
    return 0


def run_status(req: Path) -> int:
    led = _load_ledger()
    print(f"{'FR':6}{'baseline':10}{'latest':8}{'passes':8}next gap")
    print("-" * 90)
    for fr in PILOTS:
        entries = led.get(fr, [])
        if not entries:
            m = _metrics_for(fr, req)
            print(f"{fr:6}{'—':10}{m['pilot_score'] if m else '?':<8}{0:<8}(not started) {_top_gap(m) if m else ''}"[:120])
            continue
        b = entries[0]["metrics"]["pilot_score"]
        l = entries[-1]["metrics"]["pilot_score"]
        print(f"{fr:6}{b:<10}{l:<8}{len(entries):<8}{_top_gap(entries[-1]['metrics'])}"[:120])
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fr", nargs="?", help="FR id, e.g. FR-6")
    ap.add_argument("--verify", action="store_true", help="record a delta pass vs the baseline")
    ap.add_argument("--reset", action="store_true", help="drop this FR's ledger and start over")
    ap.add_argument("--status", action="store_true", help="show all pilots' current scores")
    ap.add_argument("--req", type=Path, default=REQ01, help="requirements doc (default: REQ-01)")
    args = ap.parse_args(argv[1:])

    if args.status:
        return run_status(args.req)
    if not args.fr:
        ap.print_help()
        return 2
    return run_pilot(args.fr, args.req, verify=args.verify, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
