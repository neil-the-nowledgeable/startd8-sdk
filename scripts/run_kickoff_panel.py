#!/usr/bin/env python3
# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
"""Kickoff Panel — facilitated multi-round orchestrator (experiment #6).

Built against docs/design/project-start/KICKOFF_PANEL_FACILITATION_DESIGN.md.

Turns the stakeholder panel from a mirror into a lens by running a faithful
facilitated process: R1 individual means-ends -> R2 cross-pollination ->
R3 tension/pre-mortem -> R4 synthesis, with personas on MIXED model families
(de-correlation) and a neutral facilitator/synthesizer.

Safe by default: --dry-run (the default) makes ZERO model calls and only prints
the round plan + projected call count. Pass --run to actually spend.

Usage:
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project ~/Documents/dev/contextcore-demo-retail
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project <dir> --run --cap 6 --skeptic
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# --- de-correlation: independent model families (spec §4) ---------------------
FAMILIES = {
    "claude": "anthropic:claude-opus-4-8",
    "gpt": "openai:gpt-5.5",
    "gemini": "gemini:gemini-3.1-pro-preview",
}
FAMILY_ORDER = ["claude", "gpt", "gemini"]
FACILITATOR_SPEC = FAMILIES["claude"]  # synthesizer/facilitator (distinct-ish)
SKEPTIC_SPEC = FAMILIES["gpt"]

# --- default Blue Planet Adventures context (overridable via flags) -----------
DEFAULT_DESC = (
    "Blue Planet Adventures is an online store selling outdoor gear (15 SKUs across "
    "jackets, boots, shirts) to adventure-minded consumers in 6 currencies, on a "
    "microservice platform (catalog, cart, checkout, payment, currency, shipping, "
    "email, recommendations, ads)."
)
DEFAULT_OBJECTIVE = (
    "Grow revenue from the existing catalog by lifting average order value AND "
    "conversion rate, WITHOUT adding checkout friction and WITHOUT breaking "
    "multi-currency correctness or PCI compliance."
)
DEFAULT_STRATEGY = (
    "(1) grow basket size via complementary-gear bundling and recommendations; "
    "(2) improve product discovery and trust so browsers convert; "
    "(3) keep the funnel fast and reliable at seasonal peak."
)


def _context_block(desc: str, objective: str, strategy: str) -> str:
    return (
        f"CONTEXT: {desc}\nWe are in a planning kickoff for the next phase of the "
        f"business.\nOBJECTIVE (this cycle): {objective}\nSTRATEGY (proposed): {strategy}"
    )


def _r1_prompt(ctx: str, project_name: str) -> str:
    return (
        f"{ctx}\n\nYOUR TASK, reasoning from this objective and strategy into YOUR "
        "specific role and domain: (1) the 2-3 highest-leverage TACTICS you would "
        "personally drive to move this objective; (2) the biggest RISK or tension "
        "your domain sees that the rest of the team is probably underestimating; "
        "(3) one thing the team is likely NOT thinking about that would matter for "
        f"hitting this objective. Be concrete and specific to {project_name}, not generic."
    )


def _digest(entries: list[dict], exclude_role: str, cap_chars: int = 420) -> str:
    lines = []
    for e in entries:
        if e["role_id"] == exclude_role:
            continue
        txt = " ".join(e["text"].split())
        if len(txt) > cap_chars:
            txt = txt[:cap_chars] + "…"
        lines.append(f"- {e['display_name']}: {txt}")
    return "\n".join(lines)


def _r2_prompt(digest: str) -> str:
    return (
        "Here is what the other stakeholders said in the first round:\n\n"
        f"{digest}\n\nReacting from YOUR role: (1) where do you AGREE; (2) where do "
        "you PUSH BACK or see a conflict with your domain; (3) what does someone "
        "else's point imply for YOUR domain that you did NOT already say? Be specific "
        "and concise — surface tension, don't just agree."
    )


def _r3_prompt(project_name: str) -> str:
    return (
        "PRE-MORTEM. It is one year from now and this initiative failed badly. From "
        "YOUR role's vantage, tell the short story of what went wrong: the specific "
        "failure in or adjacent to your domain that caused it, and the early warning "
        f"sign we ignored. Be concrete and specific to {project_name}."
    )


_SYNTH_SYS = (
    "You are a neutral kickoff facilitator synthesizing a stakeholder panel. You "
    "have NO domain stake; your job is process quality. CRITICAL: preserve "
    "unresolved disagreement — never smooth real tension into a false consensus. "
    "Everything below is SYNTHETIC, unratified input for a human to judge, not fact."
)


def _synth_prompt(transcript_text: str, family_map: dict[str, str]) -> str:
    fam = "; ".join(f"{r}={f}" for r, f in family_map.items())
    return (
        f"Model-family assignment (for corroboration strength): {fam}\n\n"
        f"Full transcript of the facilitated panel:\n\n{transcript_text}\n\n"
        "Produce a structured synthesis:\n"
        "## Risk Register\nEach material risk; which roles flagged it; and its "
        "corroboration = CROSS-FAMILY if flagged by roles on different model "
        "families, else single-family/single-model.\n"
        "## Tensions\nEach real conflict between roles; mark RESOLVED (with the "
        "trade-off) or OPEN.\n"
        "## Recommendations\nPrioritized, derived tactics.\n"
        "## Open Questions for the Human\nWhere the panel lacked ground truth or "
        "proprietary knowledge and needs the human's judgment.\n"
        "Be concise and structured. Do not invent specific numbers."
    )


def assign_models(personas: list) -> tuple[dict, dict]:
    """Round-robin the independent families across the roster (spec §4)."""
    specs, fams = {}, {}
    for i, p in enumerate(personas):
        fam = FAMILY_ORDER[i % len(FAMILY_ORDER)]
        specs[p.role_id] = FAMILIES[fam]
        fams[p.role_id] = fam
    return specs, fams


def _entry_from_answer(answer, brief, model_spec, prompt) -> dict:
    return {
        "role_id": answer.role_id,
        "display_name": brief.display_name,
        "model": model_spec,
        "prompt": prompt,
        "text": answer.text,
        "grounding": getattr(answer.grounding, "value", str(answer.grounding)),
        "flags": list(answer.flags),
        "input_tokens": int(answer.input_tokens),
        "output_tokens": int(answer.output_tokens),
        "cost_usd": float(answer.cost_usd),
        "created_at": answer.created_at,
    }


def _persist(session: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(session, indent=2), encoding="utf-8")


def _print_round(rnd: dict) -> None:
    print(f"\n{'='*78}\n## {rnd['round_id']} — {rnd['title']}\n{'='*78}")
    for e in rnd["entries"]:
        print(f"\n### {e['display_name']}  [{e['model']}]  ({e['grounding']})")
        print(e["text"])


async def _run_round(round_id, title, kind, personas, prompts, specs, briefs) -> dict:
    """Run one round: ask each persona its (possibly per-role) prompt, in parallel."""
    async def _one(p):
        q = prompts[p.role_id]
        ans = await p.ask(q)
        return _entry_from_answer(ans, briefs[p.role_id], specs[p.role_id], q)

    entries = await asyncio.gather(*[_one(p) for p in personas])
    return {"round_id": round_id, "title": title, "kind": kind, "entries": list(entries)}


async def orchestrate(args) -> None:
    from startd8.secrets import hydrate
    from startd8.stakeholder_panel.roster import load_roster
    from startd8.stakeholder_panel.persona import Persona, compile_system_prompt
    from startd8.utils.agent_resolution import resolve_agent_spec

    hydrate()
    roster_path = Path(args.project).expanduser() / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
    roster = load_roster(roster_path)
    briefs_all = list(roster.personas)
    if args.cap:
        briefs_all = briefs_all[: args.cap]
    specs, fams = assign_models(briefs_all)
    briefs = {b.role_id: b for b in briefs_all}
    project_name = "an outdoor-gear retailer"

    ctx = _context_block(args.desc, args.objective, args.strategy)
    n = len(briefs_all)
    projected = n * 3 + 1 + (n if args.skeptic else 0)  # R1+R2+R3 + synth (+skeptic pre-mortem)

    print(f"Kickoff Panel orchestrator — {n} personas, rounds R1/R2/R3 + synthesis"
          f"{' + skeptic' if args.skeptic else ''}")
    print(f"Roster: {roster_path}")
    print("\nModel assignment (de-correlation):")
    for b in briefs_all:
        print(f"  {b.role_id:24s} -> {specs[b.role_id]}  [{fams[b.role_id]}]")
    print(f"\nProjected model calls: {projected}  (flagship models — real spend on --run)")

    if not args.run:
        print("\n[DRY-RUN] No model calls made. Re-run with --run to execute (spends money).")
        return

    # Build one persona per role on its ASSIGNED model (history threads across rounds).
    personas = []
    for b in briefs_all:
        agent = resolve_agent_spec(
            specs[b.role_id], name=f"persona:{b.role_id}",
            system_prompt=compile_system_prompt(b),
        )
        personas.append(Persona(b, agent))

    session = {
        "session_id": f"kp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": Path(args.project).name,
        "objective": args.objective,
        "strategy": args.strategy,
        "model_assignment": specs,
        "facilitator_model": FACILITATOR_SPEC,
        "rounds": [],
        "synthesis": None,
        "cost_total_usd": 0.0,
    }
    out_path = Path(args.project).expanduser() / ".startd8" / "kickoff-panel" / f"{session['session_id']}.json"

    # R1 — individual means-ends
    r1_prompts = {b.role_id: _r1_prompt(ctx, project_name) for b in briefs_all}
    r1 = await _run_round("R1", "Individual analysis (means-ends)", "individual",
                          personas, r1_prompts, specs, briefs)
    session["rounds"].append(r1); _persist(session, out_path); _print_round(r1)

    # R2 — cross-pollination (each persona reacts to a digest of the others' R1)
    r2_prompts = {b.role_id: _r2_prompt(_digest(r1["entries"], b.role_id)) for b in briefs_all}
    r2 = await _run_round("R2", "Cross-pollination", "cross_pollination",
                          personas, r2_prompts, specs, briefs)
    session["rounds"].append(r2); _persist(session, out_path); _print_round(r2)

    # R3 — pre-mortem / tension
    r3_prompts = {b.role_id: _r3_prompt(project_name) for b in briefs_all}
    r3 = await _run_round("R3", "Tension + pre-mortem", "tension_premortem",
                          personas, r3_prompts, specs, briefs)
    session["rounds"].append(r3); _persist(session, out_path); _print_round(r3)

    # R4 — synthesis (neutral facilitator sees all rounds; preserves open tension)
    transcript_text = "\n\n".join(
        f"[{r['round_id']} {r['title']}]\n" + "\n".join(
            f"{e['display_name']} ({fams[e['role_id']]}): {e['text']}" for e in r["entries"]
        )
        for r in session["rounds"]
    )
    synth_agent = resolve_agent_spec(FACILITATOR_SPEC, name="facilitator", system_prompt=_SYNTH_SYS)
    result = await synth_agent.agenerate(_synth_prompt(transcript_text, fams), system_prompt=_SYNTH_SYS)
    synth_text = result.text if hasattr(result, "text") else str(result)
    session["synthesis"] = {"model": FACILITATOR_SPEC, "text": synth_text}
    session["cost_total_usd"] = round(
        sum(e["cost_usd"] for r in session["rounds"] for e in r["entries"]), 6
    )
    _persist(session, out_path)
    print(f"\n{'='*78}\n## R4 — Synthesis (facilitator: {FACILITATOR_SPEC})\n{'='*78}\n{synth_text}")
    print(f"\nSaved transcript: {out_path}")
    print(f"Persona-call cost: ${session['cost_total_usd']:.4f} (synthesis + any $0-cost providers not included)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Facilitated multi-round kickoff panel (experiment #6).")
    ap.add_argument("--project", required=True, help="Project root containing docs/kickoff/inputs/stakeholders.yaml")
    ap.add_argument("--objective", default=DEFAULT_OBJECTIVE)
    ap.add_argument("--strategy", default=DEFAULT_STRATEGY)
    ap.add_argument("--desc", default=DEFAULT_DESC, help="One-paragraph project description")
    ap.add_argument("--cap", type=int, default=0, help="Limit to first N personas (0 = all)")
    ap.add_argument("--ladder", type=int, default=0, help="Laddering follow-ups per persona in R1 (reserved)")
    ap.add_argument("--skeptic", action="store_true", help="Add a red-team skeptic pass (reserved)")
    ap.add_argument("--run", action="store_true", help="Actually call models (spends money). Default: dry-run.")
    args = ap.parse_args(argv)
    try:
        asyncio.run(orchestrate(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
