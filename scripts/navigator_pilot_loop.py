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
CRUFT_LINT = Path.home() / "Documents/dev/dev-os/scripts/cruft_lint.py"

# Per-consumer config so the SAME loop runs on any navigator source. The requirements consumer
# (REQ-01) has a confirmed causal trio; the capability-index consumer has 68 nodes, so its pilots
# are discovered by --survey (lowest pilot_score first). Ledgers are per-source so they don't collide.
DEFAULT_SOURCE = "requirements"
PILOTS_BY_SOURCE = {
    "requirements": ("FR-6", "FR-4", "FR-8"),
    "capability-index": (),  # discover via --survey, then pass keys explicitly
}
LEDGER_SUFFIX = {"requirements": "", "capability-index": "-capability"}


def _nodes_for(source: str, path):
    """Load Nodes from the named consumer source (requirements | capability-index)."""
    if source == "capability-index":
        from startd8.navigator.sources_capability import (
            default_capability_index_path,
            nodes_from_capability_index,
        )
        return nodes_from_capability_index(path or default_capability_index_path())
    from startd8.navigator.sources_requirements import nodes_from_requirements
    return nodes_from_requirements(path or REQ01)


def _pilots(source: str):
    return PILOTS_BY_SOURCE.get(source, ())


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
    # Health is HONEST unless it is a dishonest done-claim. det_req.fr_health only emits a verdict
    # for done-claims (done-ish Verify annotation); a spec-time FR is legitimately "n/a". So score
    # the ABSENCE of dishonesty (!= "unknown"), not the presence of a verdict — else the rubric would
    # pay you to falsely stamp a spec "done" (the mis-calibration the dogfood loop surfaced).
    if m["fr_health"] != "unknown":
        score += 0.15
    if m["approve_prompts"]:
        score += 0.15
    return round(score, 3)


def _metrics_of_node(n) -> Dict[str, Any]:
    """Score a single Node (source-agnostic — works for FRs and capabilities alike)."""
    node = {
        "key": n.key,
        "confidence": n.confidence,
        "ships_when": n.ships_when,
        "route_state": n.route_state,
        "lives": [{"type": e.type, "ref": e.ref} for e in n.lives],
        "attributes": dict(n.attributes),
    }
    a = node["attributes"]
    types = _lives_types(node)
    refs = [e["ref"] for e in node["lives"]]
    m = {
        "fr": n.key,
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


def _metrics_for(key: str, source: str, path) -> Optional[Dict[str, Any]]:
    for n in _nodes_for(source, path):
        if n.key == key:
            return _metrics_of_node(n)
    return None


def _top_gap(m: Dict[str, Any], source: str = DEFAULT_SOURCE) -> str:
    """The single highest-value fix to attempt next for this node (actionable, ordered)."""
    t = ",".join(f"{k}:{v}" for k, v in m["lives_types"].items()) or "none"
    if m["status_key"] not in ("grounded", "built"):
        return (f"STATUS is {m['status_key']!r} — cite a code Lives ref for the implementation "
                f"(currently {t}); a built FR that cites only tests reads as spec.")
    if m["lives_count"] and m["lives_resolve"] < m["lives_count"]:
        return (f"EVIDENCE — {m['lives_count'] - m['lives_resolve']} of {m['lives_count']} Lives "
                "refs do not resolve on disk; fix the path or sha.")
    if (m["confidence"] or 0) < 0.9:
        if source == "capability-index":
            return (f"CONFIDENCE is {m['confidence']} (authored in the manifest, currently {t}) — "
                    "add test evidence or confirm the authored value; capability confidence is not "
                    "derived from lives the way an FR's is.")
        return (f"CONFIDENCE is {m['confidence']} — cite BOTH code AND test Lives so "
                f"default_confidence yields 0.9 (currently {t}). If the extractor drops one type "
                "per FR, that is the FR-6 fidelity gap.")
    if m["fr_health"] == "unknown":
        return ("HEALTH — reads as a done-claim but cites no resolvable evidence "
                "(fr_health=unknown); add a resolvable Lives ref or drop the done-ish Verify "
                "annotation. (A spec-time FR is honestly n/a — not a gap.)")
    if not m["approve_prompts"]:
        if source == "capability-index":
            return ("SIGN-OFF — no APPROVE? prompt (systemic: the capability manifest carries none) "
                    "— add per-capability approve questions so the sign-off surface lights up.")
        return "SIGN-OFF — no APPROVE? prompt on this FR; add one so it lights up the per-item sign-off."
    return "glance-approvable ✓ — no mechanical gap; promote as an exemplar."


# --------------------------------------------------------------------------- #
# diagnose helpers
# --------------------------------------------------------------------------- #

def _render_html(source: str, path, out: Path) -> None:
    from startd8.navigator.project import render_nodes_html

    nodes = _nodes_for(source, path)
    if source == "capability-index":
        from startd8.navigator.sources_capability import (
            CAPABILITY_PROFILE,
            default_capability_index_path,
        )
        root = str((path or default_capability_index_path()).parent)
        render_nodes_html(nodes, out, project_root=root, profile=CAPABILITY_PROFILE)
    else:
        from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE
        render_nodes_html(nodes, out, project_root=str((path or REQ01).parent),
                          profile=REQUIREMENTS_PROFILE)


def _cruft_lint(html: Path, source_path) -> str:
    if not CRUFT_LINT.is_file():
        return f"(cruft_lint not found at {CRUFT_LINT} — run /cruft-audit by hand per the runbook)"
    try:
        cmd = [sys.executable, str(CRUFT_LINT), str(html)]
        if source_path:
            cmd.append(f"--source={source_path}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "(no output)"
    except (subprocess.SubprocessError, OSError) as e:
        return f"(cruft_lint failed: {e})"


# --------------------------------------------------------------------------- #
# ledger (per-source)
# --------------------------------------------------------------------------- #

def _ledger_path(source: str) -> Path:
    return LEDGER_DIR / f"ledger{LEDGER_SUFFIX.get(source, '-' + source)}.json"


def _load_ledger(source: str) -> Dict[str, List[Dict[str, Any]]]:
    p = _ledger_path(source)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_ledger(source: str, led: Dict[str, List[Dict[str, Any]]]) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _ledger_path(source).write_text(
        json.dumps(led, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _render_ledger_md(source, led)


def _render_ledger_md(source: str, led: Dict[str, List[Dict[str, Any]]]) -> None:
    keys = list(_pilots(source)) or sorted(led)  # discovered pilots (capability) → ledger keys
    lines = [f"# Navigator dogfood — pilot ledger ({source})", "",
             "Repeatable per-node loop (see `PILOT_IMPROVEMENT_LOOP.md`). Auto-generated; do not hand-edit.",
             ""]
    for fr in keys:
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
        lines += ["", f"**Next gap:** {_top_gap(entries[-1]['metrics'], source)}", ""]
    (LEDGER_DIR / f"ledger{LEDGER_SUFFIX.get(source, '-' + source)}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


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


def run_pilot(key: str, source: str, path, verify: bool, reset: bool) -> int:
    pilots = _pilots(source)
    if pilots and key not in pilots:
        print(f"warning: {key} is not in the confirmed pilot set {pilots}", file=sys.stderr)
    led = _load_ledger(source)
    if reset:
        led.pop(key, None)
        _save_ledger(source, led)
        print(f"reset ledger for {key} ({source})")
        return 0

    m = _metrics_for(key, source, path)
    if m is None:
        print(f"error: {key} not found in {source}", file=sys.stderr)
        return 1

    entries = led.setdefault(key, [])
    phase = "verify" if (verify and entries) else "baseline"
    if phase == "baseline" and entries:
        print(f"note: {key} already has a baseline; recording another baseline "
              "(use --verify to record a delta pass, --reset to start over)")

    # diagnose (both phases): render + cruft_lint + evidence gate + top gap
    safe = key.replace("/", "_").replace(".", "_")
    html = LEDGER_DIR / f"{source}-{safe}.html"
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _render_html(source, path, html)
    cruft = _cruft_lint(html, path)

    print(f"\n=== {key} ({source}) — {phase} @ {_now()[:16]} ===")
    _print_metrics(m)
    print(f"  cruft_lint: {cruft}")
    print(f"  TOP GAP → {_top_gap(m, source)}")

    if phase == "verify":
        base = entries[0]["metrics"]
        d = round(m["pilot_score"] - base["pilot_score"], 3)
        sign = "+" if d >= 0 else ""
        print(f"\n  DELTA vs baseline: pilot_score {base['pilot_score']} → {m['pilot_score']} ({sign}{d})")
        for k in ("status_key", "confidence", "fr_health"):
            if base[k] != m[k]:
                print(f"    {k}: {base[k]!r} → {m[k]!r}")

    entries.append({"phase": phase, "when": _now(), "metrics": m,
                    "cruft_lint": cruft, "top_gap": _top_gap(m, source)})
    _save_ledger(source, led)
    print(f"\nrecorded {phase} for {key} → {_ledger_path(source).relative_to(REPO)}")
    return 0


def run_status(source: str, path) -> int:
    led = _load_ledger(source)
    keys = list(_pilots(source)) or sorted(led)
    if not keys:
        print(f"no pilots for {source} yet — run --survey to pick some.")
        return 0
    print(f"{'KEY':34}{'baseline':10}{'latest':8}{'passes':8}next gap")
    print("-" * 110)
    for key in keys:
        entries = led.get(key, [])
        if not entries:
            m = _metrics_for(key, source, path)
            sc = m["pilot_score"] if m else "?"
            print(f"{key:34}{'—':10}{sc:<8}{0:<8}(not started)"[:150])
            continue
        b = entries[0]["metrics"]["pilot_score"]
        l = entries[-1]["metrics"]["pilot_score"]
        print(f"{key:34}{b:<10}{l:<8}{len(entries):<8}{_top_gap(entries[-1]['metrics'], source)}"[:150])
    return 0


def run_survey(source: str, path, top: int) -> int:
    """Score EVERY node in the source, ranked lowest pilot_score first (pick pilots from the head)."""
    nodes = _nodes_for(source, path)
    scored = sorted((_metrics_of_node(n) for n in nodes), key=lambda m: m["pilot_score"])
    print(f"{source}: {len(nodes)} nodes — lowest {min(top, len(scored))} pilot_scores (most improvable):\n")
    print(f"{'KEY':38}{'score':7}{'conf':6}{'appr':6}top gap")
    print("-" * 120)
    for m in scored[:top]:
        print(f"{m['fr']:38}{m['pilot_score']:<7}{m['confidence']:<6}"
              f"{'Y' if m['approve_prompts'] else '-':<6}{_top_gap(m, source)}"[:150])
    scores = [m["pilot_score"] for m in scored]
    from collections import Counter
    dist = dict(sorted(Counter(scores).items()))
    print(f"\nscore distribution across all {len(scored)}: {dist}")
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", nargs="?", help="node key, e.g. FR-6 or startd8.agent.system_prompt")
    ap.add_argument("--source", default=DEFAULT_SOURCE, choices=sorted(PILOTS_BY_SOURCE),
                    help="navigator consumer (default: requirements)")
    ap.add_argument("--verify", action="store_true", help="record a delta pass vs the baseline")
    ap.add_argument("--reset", action="store_true", help="drop this node's ledger and start over")
    ap.add_argument("--status", action="store_true", help="show this source's pilots' scores")
    ap.add_argument("--survey", action="store_true", help="score all nodes, lowest-first (pick pilots)")
    ap.add_argument("--top", type=int, default=12, help="--survey: how many to list")
    ap.add_argument("--path", type=Path, default=None, help="source doc/manifest override")
    args = ap.parse_args(argv[1:])

    if args.survey:
        return run_survey(args.source, args.path, args.top)
    if args.status:
        return run_status(args.source, args.path)
    if not args.key:
        ap.print_help()
        return 2
    return run_pilot(args.key, args.source, args.path, verify=args.verify, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
