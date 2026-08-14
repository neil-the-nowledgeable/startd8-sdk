#!/usr/bin/env python3
"""navigator_content_loop — the Node Content Improvement Loop (child of the Pilot loop).

Sibling to `navigator_pilot_loop.py`. Where the pilot loop improves a node's **grounding**
(status · confidence · lives · health), this loop improves a node's **authored content** — the
semantic fields a human writes: the deterministic **Name:** (and its derived handle/canonical ref),
the behavior prose, the acceptance test, the objective link, the surface, and non-goals.

Same shape as the pilot loop: `baseline → diagnose → [author the missing content] → verify → record`,
rolling the authored fields up to a single `content_score ∈ [0,1]` and naming the one **TOP CONTENT
GAP** to write next. The pilot loop *calls* this loop for its orthogonal read and hands off when a
node is grounding-complete but content-incomplete.

Reuses the pilot loop's node-loading + metrics (single node→metrics pass, two scores) so grounding
and content never re-derive each other.

Usage (mirrors the pilot loop; --source requirements | capability-index):
    python3 scripts/navigator_content_loop.py --survey                     # rank by content_score
    python3 scripts/navigator_content_loop.py FR-2                         # baseline + diagnose
    python3 scripts/navigator_content_loop.py FR-2 --verify                # delta vs baseline
    python3 scripts/navigator_content_loop.py --status
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Shared primitives from the pilot loop (node loading, one node→metrics pass, source config, ledger dir).
from navigator_pilot_loop import (  # noqa: E402
    DEFAULT_SOURCE,
    LEDGER_DIR,
    PILOTS_BY_SOURCE,
    REPO,
    _metrics_for,
    _metrics_of_node,
    _nodes_for,
    _now,
    _pilots,
)


# --------------------------------------------------------------------------- #
# content score + gap
# --------------------------------------------------------------------------- #

def content_score(m: Dict[str, Any]) -> float:
    """Authored-content completeness in [0,1] — the moving number this loop improves.

    Orthogonal to pilot_score (grounding). The Name signal (0.30) is the headline: a node identified
    by its integer key alone, with no deterministic semantic name, is the anti-pattern this loop
    exists to close (handle + canonical ref derive from the name, so they are not scored separately).
    """
    score = 0.0
    if m.get("name"):
        score += 0.30                                    # deterministic semantic Name: (→ handle+canonical)
    does, title = (m.get("does") or "").strip(), (m.get("title") or "").strip()
    if len(does) >= 20 and does != title:
        score += 0.15                                    # real behavior prose, not just the title
    if m.get("verify"):
        score += 0.15                                    # acceptance test authored
    if m.get("serves"):
        score += 0.15                                    # linked to an objective (O-N)
    if m.get("touches"):
        score += 0.15                                    # implementation surface named
    if m.get("wont"):
        score += 0.10                                    # authored non-goals (WON'T)
    return round(score, 3)


def content_top_gap(m: Dict[str, Any], source: str = DEFAULT_SOURCE) -> str:
    """The single highest-value content to author next (ordered, actionable)."""
    does, title = (m.get("does") or "").strip(), (m.get("title") or "").strip()
    if not m.get("name"):
        return ("NAME — no deterministic semantic name (Name:); identifying this by its key alone is "
                "the anti-pattern. Author actor · action · object · outcome (handle + canonical derive).")
    if len(does) < 20 or does == title:
        return "BEHAVIOR — `does` is empty or just restates the title; write the WHAT this delivers."
    if not m.get("verify"):
        return "VERIFY — no acceptance test authored; write how it's checked."
    if not m.get("serves"):
        return "SERVES — not linked to an objective (O-N); state which outcome it serves."
    if not m.get("touches"):
        return "TOUCHES — no implementation surface named."
    if not m.get("wont"):
        return "WONT — no authored non-goals/constraints (WON'T) for this node."
    return "content-complete ✓ — deterministic name + full authored fields; promote as an exemplar."


# --------------------------------------------------------------------------- #
# ledger (content-suffixed, per source)
# --------------------------------------------------------------------------- #

def _ledger_path(source: str) -> Path:
    tag = "" if source == "requirements" else f"-{source}"
    return LEDGER_DIR / f"ledger-content{tag}.json"


def _load(source: str) -> Dict[str, List[Dict[str, Any]]]:
    p = _ledger_path(source)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _save(source: str, led: Dict[str, List[Dict[str, Any]]]) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    _ledger_path(source).write_text(json.dumps(led, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _render_md(source, led)


def _render_md(source: str, led: Dict[str, List[Dict[str, Any]]]) -> None:
    keys = list(_pilots(source)) or sorted(led)
    lines = [f"# Node Content Improvement Loop — ledger ({source})", "",
             "Authored-content completeness per node (see `LOOP_CATALOG.md`). Auto-generated.", ""]
    for key in keys:
        entries = led.get(key, [])
        if not entries:
            lines += [f"## {key} — not started", ""]
            continue
        base, last = entries[0]["metrics"]["content_score"], entries[-1]["metrics"]["content_score"]
        arrow = "→" if last == base else ("↑" if last > base else "↓")
        lines += [f"## {key} — content_score {base} {arrow} {last} ({len(entries)} pass(es))", "",
                  "| # | phase | when | name | does | verify | serves | touches | wont | score |",
                  "|---|-------|------|------|------|--------|--------|---------|------|-------|"]
        for i, e in enumerate(entries):
            m = e["metrics"]
            def y(v):
                return "Y" if v else "-"
            lines.append(
                f"| {i} | {e['phase']} | {e['when'][:16]} | {y(m.get('name'))} | "
                f"{y(len((m.get('does') or '')) >= 20)} | {y(m.get('verify'))} | {y(m.get('serves'))} | "
                f"{y(m.get('touches'))} | {y(m.get('wont'))} | {m['content_score']} |")
        lines += ["", f"**Next content gap:** {content_top_gap(entries[-1]['metrics'], source)}", ""]
    tag = "" if source == "requirements" else f"-{source}"
    (LEDGER_DIR / f"ledger-content{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #

def run(key: str, source: str, path, verify: bool, reset: bool) -> int:
    led = _load(source)
    if reset:
        led.pop(key, None)
        _save(source, led)
        print(f"reset content ledger for {key} ({source})")
        return 0
    m = _metrics_for(key, source, path)
    if m is None:
        print(f"error: {key} not found in {source}", file=sys.stderr)
        return 1
    m["content_score"] = content_score(m)
    entries = led.setdefault(key, [])
    phase = "verify" if (verify and entries) else "baseline"

    print(f"\n=== {key} ({source}) — content {phase} @ {_now()[:16]} ===")
    print(f"  name={'yes' if m.get('name') else 'NO'}  handle={'yes' if m.get('handle') else '-'}  "
          f"verify={'yes' if m.get('verify') else '-'}  serves={m.get('serves') or '-'}  "
          f"touches={'yes' if m.get('touches') else '-'}  wont={'yes' if m.get('wont') else '-'}")
    if m.get("name"):
        print(f"  NAME → {m['name']}")
        print(f"  handle: {m.get('handle')}  ·  canonical: {m.get('canonical')}")
    print(f"  content_score={m['content_score']}")
    print(f"  TOP CONTENT GAP → {content_top_gap(m, source)}")

    if phase == "verify":
        base = entries[0]["metrics"]["content_score"]
        d = round(m["content_score"] - base, 3)
        print(f"\n  DELTA vs baseline: content_score {base} → {m['content_score']} ({'+' if d >= 0 else ''}{d})")

    entries.append({"phase": phase, "when": _now(), "metrics": m,
                    "top_gap": content_top_gap(m, source)})
    _save(source, led)
    print(f"\nrecorded content {phase} for {key} → {_ledger_path(source).relative_to(REPO)}")
    return 0


def survey(source: str, path, top: int) -> int:
    scored = []
    for n in _nodes_for(source, path):
        m = _metrics_of_node(n)
        m["content_score"] = content_score(m)
        scored.append(m)
    scored.sort(key=lambda m: m["content_score"])
    print(f"{source}: {len(scored)} nodes — lowest {min(top, len(scored))} content_scores (author these):\n")
    print(f"{'KEY':38}{'score':7}{'name':6}top content gap")
    print("-" * 120)
    for m in scored[:top]:
        print(f"{m['fr']:38}{m['content_score']:<7}{'Y' if m.get('name') else '-':<6}"
              f"{content_top_gap(m, source)}"[:150])
    from collections import Counter
    print(f"\nscore distribution across all {len(scored)}: "
          f"{dict(sorted(Counter(m['content_score'] for m in scored).items()))}")
    return 0


def status(source: str, path) -> int:
    led = _load(source)
    keys = list(_pilots(source)) or sorted(led)
    if not keys:
        print(f"no content pilots for {source} yet — run --survey.")
        return 0
    print(f"{'KEY':34}{'baseline':10}{'latest':8}next content gap")
    print("-" * 110)
    for key in keys:
        entries = led.get(key, [])
        if not entries:
            m = _metrics_for(key, source, path)
            cs = content_score(m) if m else "?"
            print(f"{key:34}{'—':10}{cs:<8}(not started)"[:150])
            continue
        b, l = entries[0]["metrics"]["content_score"], entries[-1]["metrics"]["content_score"]
        print(f"{key:34}{b:<10}{l:<8}{content_top_gap(entries[-1]['metrics'], source)}"[:150])
    return 0


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", nargs="?", help="node key, e.g. FR-2")
    ap.add_argument("--source", default=DEFAULT_SOURCE, choices=sorted(PILOTS_BY_SOURCE))
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--survey", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--path", type=Path, default=None)
    args = ap.parse_args(argv[1:])
    if args.survey:
        return survey(args.source, args.path, args.top)
    if args.status:
        return status(args.source, args.path)
    if not args.key:
        ap.print_help()
        return 2
    return run(args.key, args.source, args.path, verify=args.verify, reset=args.reset)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
