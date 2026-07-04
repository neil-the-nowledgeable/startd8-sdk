#!/usr/bin/env python3
# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
"""Kickoff Panel — facilitated multi-round orchestrator (thin CLI over the package module).

The orchestration itself was **promoted** (GE-M3a / FR-GE-11a) into
``startd8.stakeholder_panel.facilitation`` — importable, testable, and with transcript
persistence routed through the confined safe-write floor (FR-GE-13). This script is now a
thin CLI wrapper: it parses flags, prints the plan / live rounds, and delegates the actual
facilitated run to :class:`~startd8.stakeholder_panel.facilitation.KickoffFacilitator`.

Rounds (all default on):
  R0 prep : artifact grounding (--ground) + Key Assumptions Check (--assumptions)
            + Outside View / reference-class base rate (--outside-view)
  R1      : individual means-ends (private)  [+ adversary personas, --adversary]
  R2      : pre-mortem (private, MOVED before the collision -- independence)
  R3      : cross-pollination (generative collision)
  R4      : final private judgment (re-independent-ize after the collision)
  R5      : synthesis (neutral facilitator; preserves open tension)

Mixed-model de-correlation across Claude/GPT/Gemini. Safe by default: --dry-run (the
default) makes ZERO model calls and prints the plan + projected calls. Pass --run to spend.

Usage:
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project ~/Documents/dev/contextcore-demo-retail
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project <dir> --run
  ... --no-adversary --no-ground   # disable individual Tier-1 additions
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from startd8.stakeholder_panel import facilitation as F


def _print_round(rnd: dict) -> None:
    print(f"\n{'='*78}\n## {rnd['round_id']} — {rnd['title']}\n{'='*78}")
    for e in rnd["entries"]:
        print(f"\n### {e['display_name']}  [{e['model']}]  ({e['grounding']})")
        print(e["text"])


def _print_prep(kind: str, spec: str, text: str) -> None:
    titles = {
        "grounded_context": "Grounded current state",
        "key_assumptions": "Key Assumptions Check",
        "outside_view": "Outside View",
    }
    print(f"\n{'='*78}\n## R0 — {titles.get(kind, kind)} [{spec}]\n{'='*78}\n{text}")


def _print_synthesis(spec: str, text: str) -> None:
    print(f"\n{'='*78}\n## R5 — Synthesis (facilitator: {spec})\n{'='*78}\n{text}")


async def orchestrate(args: argparse.Namespace) -> None:
    from startd8.stakeholder_panel.roster import load_roster

    cfg = F.FacilitationConfig(
        project=Path(args.project).expanduser(),
        objective=args.objective,
        strategy=args.strategy,
        desc=args.desc,
        project_name=args.project_name,
        cap=args.cap,
        ground=args.ground,
        assumptions=args.assumptions,
        outside_view=args.outside_view,
        adversary=args.adversary,
        final_judgment=args.final_judgment,
    )
    roster_path = Path(args.project).expanduser() / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
    roster = load_roster(roster_path)

    briefs_all = F.build_briefs(cfg, roster)
    specs, fams = F.assign_models(briefs_all)
    adv_ids = [b.role_id for b in briefs_all if b.role_id in F.ADVERSARY_IDS]
    n = len(briefs_all)
    persona_rounds = 4 if cfg.final_judgment else 3
    projected = F.projected_calls(cfg, n)

    print(f"Kickoff Panel orchestrator (v0.2 / Tier-1) — {n} participants "
          f"({len(adv_ids)} adversary), {persona_rounds} persona rounds + synthesis")
    print(f"Roster: {roster_path}")
    print("Tier-1 additions:", ", ".join(
        [k for k, v in [("ground", cfg.ground), ("assumptions", cfg.assumptions),
                        ("outside-view", cfg.outside_view), ("adversary", cfg.adversary),
                        ("final-judgment", cfg.final_judgment)] if v]) or "(none)")
    print("\nModel assignment (de-correlation):")
    for b in briefs_all:
        tag = "  <ADVERSARY>" if b.role_id in F.ADVERSARY_IDS else ""
        print(f"  {b.role_id:26s} -> {specs[b.role_id]}  [{fams[b.role_id]}]{tag}")
    print(f"\nProjected model calls: {projected}  (prep + {n}x{persona_rounds} + synth)")

    if not args.run:
        print("\n[DRY-RUN] No model calls made. Re-run with --run to execute (spends money).")
        return

    fac = F.KickoffFacilitator(
        cfg,
        roster=roster,
        on_prep=_print_prep,
        on_round=_print_round,
        on_synthesis=_print_synthesis,
    )
    session = await fac.run()
    print(f"\nSaved transcript: {fac.transcript_path(session['session_id'])}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Facilitated multi-round kickoff panel (v0.2 / Tier-1).")
    ap.add_argument("--project", required=True, help="Project root with docs/kickoff/inputs/stakeholders.yaml")
    ap.add_argument("--objective", default=F.DEFAULT_OBJECTIVE)
    ap.add_argument("--strategy", default=F.DEFAULT_STRATEGY)
    ap.add_argument("--desc", default=F.DEFAULT_DESC)
    ap.add_argument("--project-name", dest="project_name", default="",
                    help="Short domain noun used in prompts (e.g. 'a benchmark portal'). "
                         "Prevents the default-domain leaking into a re-purposed run (bug fix from #8).")
    ap.add_argument("--cap", type=int, default=0, help="Limit roster to first N personas (0 = all)")
    ap.add_argument("--run", action="store_true", help="Actually call models (spends money). Default: dry-run.")
    # Tier-1 additions (default ON; use --no-<flag> to disable)
    ap.add_argument("--ground", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--assumptions", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--outside-view", dest="outside_view", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--adversary", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--final-judgment", dest="final_judgment", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args(argv)
    try:
        asyncio.run(orchestrate(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
