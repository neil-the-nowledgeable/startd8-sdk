#!/usr/bin/env python3
# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0
"""Kickoff Panel — facilitated multi-round orchestrator (experiments #6+).

Built against docs/design/project-start/KICKOFF_PANEL_FACILITATION_DESIGN.md (v0.2)
and KICKOFF_PANEL_GAP_ANALYSIS.md.

Turns the stakeholder panel from a mirror into a lens via a faithful facilitated
process, now with the Tier-1 gap-analysis additions (all default on):
  R0 prep : artifact grounding (--ground) + Key Assumptions Check (--assumptions)
            + Outside View / reference-class base rate (--outside-view)
  R1      : individual means-ends (private)  [+ adversary personas, --adversary]
  R2      : pre-mortem (private, MOVED before the collision -- independence)
  R3      : cross-pollination (generative collision)
  R4      : final private judgment (re-independent-ize after the collision)
  R5      : synthesis (neutral facilitator; preserves open tension)

Mixed-model de-correlation across Claude/GPT/Gemini. Safe by default: --dry-run
(the default) makes ZERO model calls and prints the plan + projected calls. Pass
--run to actually spend.

Usage:
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project ~/Documents/dev/contextcore-demo-retail
  PYTHONPATH=src python3 scripts/run_kickoff_panel.py --project <dir> --run
  ... --no-adversary --no-ground   # disable individual Tier-1 additions
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
FACILITATOR_SPEC = FAMILIES["claude"]  # facilitator / synthesizer / grounding / assumptions
OUTSIDE_VIEW_SPEC = FAMILIES["gpt"]    # de-correlate the base-rate estimate

ADVERSARY_IDS = {"adversary-exploit", "adversary-discredit"}

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
PROJECT_NAME = "the project described above"  # overridable via --project-name (bug fix: was retail-hardcoded)
_NEUTRAL_SYS = (
    "You are a neutral kickoff analyst. No domain stake, no cheerleading. Be "
    "candid and specific. Do not invent facts, numbers, or dates."
)


# ============================ prompt builders =================================
def _context_block(desc, objective, strategy, grounded=""):
    ctx = (
        f"CONTEXT: {desc}\nWe are in a planning kickoff for the next phase of the "
        f"business.\nOBJECTIVE (this cycle): {objective}\nSTRATEGY (proposed): {strategy}"
    )
    if grounded:
        ctx += f"\n\nCURRENT STATE (grounded in the real system):\n{grounded}"
    return ctx


def _r1_prompt(ctx):
    return (
        f"{ctx}\n\nYOUR TASK, reasoning from this objective and strategy into YOUR "
        "specific role and domain: (1) the 2-3 highest-leverage TACTICS you would "
        "personally drive; (2) the biggest RISK or tension your domain sees that the "
        "rest of the team is probably underestimating; (3) one thing the team is "
        f"likely NOT thinking about. Be concrete and specific to {PROJECT_NAME}, not generic."
    )


def _r1_adversary_prompt(ctx):
    return (
        f"{ctx}\n\nYou are an ADVERSARY, not a team member. Reasoning about how you "
        "would EXPLOIT or BEAT this initiative: (1) the 2-3 concrete ways you would "
        "attack, abuse, or undercut it; (2) the single weakness the team is most "
        "likely to leave open; (3) what they will forget to defend. Be concrete and "
        f"specific to {PROJECT_NAME}."
    )


def _premortem_prompt(is_adv):
    if is_adv:
        return (
            "PRE-MORTEM (adversary). It is one year later and YOU WON — you "
            "successfully exploited or out-competed this initiative. Tell the short "
            "story of exactly how you did it and the opening they left you. Be concrete."
        )
    return (
        "PRE-MORTEM. It is one year from now and this initiative failed badly. From "
        "YOUR role's vantage, tell the short story of what went wrong: the specific "
        "failure in or adjacent to your domain, and the early warning sign we ignored. "
        f"Be concrete and specific to {PROJECT_NAME}."
    )


def _r3_prompt(digest):
    return (
        "Here is what the other participants said in their first-round analysis:\n\n"
        f"{digest}\n\nReacting from YOUR role: (1) where do you AGREE; (2) where do you "
        "PUSH BACK or see a conflict with your domain; (3) what does someone else's "
        "point imply for YOUR domain that you did NOT already say? Surface tension — "
        "do not just agree."
    )


def _r4_prompt():
    return (
        "Having heard the others and run a pre-mortem, give your FINAL, INDEPENDENT "
        "judgment from your role: (1) the single highest-priority thing the team must "
        "get right; (2) your biggest remaining worry; (3) one concrete recommendation. "
        "Say what YOU actually conclude now, even if it dissents from the group."
    )


def _digest(entries, exclude_role, cap_chars=420):
    lines = []
    for e in entries:
        if e["role_id"] == exclude_role:
            continue
        txt = " ".join(e["text"].split())
        if len(txt) > cap_chars:
            txt = txt[:cap_chars] + "…"
        lines.append(f"- {e['display_name']}: {txt}")
    return "\n".join(lines)


_SYNTH_SYS = (
    "You are a neutral kickoff facilitator synthesizing a stakeholder panel. You "
    "have NO domain stake; your job is process quality. CRITICAL: preserve "
    "unresolved disagreement — never smooth real tension into a false consensus. "
    "Everything below is SYNTHETIC, unratified input for a human to judge, not fact."
)


def _synth_prompt(transcript_text, family_map, prep):
    fam = "; ".join(f"{r}={f}" for r, f in family_map.items())
    prep_txt = ""
    if prep.get("key_assumptions"):
        prep_txt += f"\n\nKEY ASSUMPTIONS (prep):\n{prep['key_assumptions']}"
    if prep.get("outside_view"):
        prep_txt += f"\n\nOUTSIDE VIEW / base rate (prep):\n{prep['outside_view']}"
    return (
        f"Model-family assignment (for corroboration strength): {fam}{prep_txt}\n\n"
        f"Full transcript of the facilitated panel:\n\n{transcript_text}\n\n"
        "Produce a structured synthesis:\n"
        "## Risk Register\nEach material risk; which roles flagged it; corroboration = "
        "CROSS-FAMILY if flagged by roles on different model families, else "
        "single-family/single-model.\n"
        "## Adversary Findings\nAbuse/competitive attacks the adversary personas surfaced.\n"
        "## Tensions\nEach real conflict between roles; RESOLVED (with the trade-off) or OPEN.\n"
        "## Assumptions At Risk\nWhich prep assumptions the panel's analysis threatens or confirms.\n"
        "## Recommendations\nPrioritized, derived tactics.\n"
        "## Open Questions for the Human\nWhere the panel lacked ground truth or "
        "proprietary knowledge and needs the human's judgment.\n"
        "Be concise and structured. Do not invent specific numbers."
    )


# ============================ adversary briefs ================================
def _adversary_briefs():
    # Domain-NEUTRAL adversaries: the injected context (objective/strategy/grounding)
    # makes their attacks domain-appropriate, so they work for any kickoff.
    from startd8.stakeholder_panel.models import PersonaBrief
    return [
        PersonaBrief(
            role_id="adversary-exploit",
            display_name="Exploiter / Bad Actor (ADVERSARY)",
            goals=["Exploit this initiative's weakest technical or process seam for gain, disruption, or harm."],
            known_positions=[
                "seams: the exploitable weakness is where two systems or steps each assume the other is correct and nobody validates the join",
                "new-surface: every new capability, integration, or automation is a new attack/abuse surface",
            ],
            constraints=["You are an attacker, not a team member — you probe for weakness, you do not help."],
            out_of_scope=[],
            answers_for=["exploit", "abuse", "attack-surface", "integrity"],
        ),
        PersonaBrief(
            role_id="adversary-discredit",
            display_name="Rival / Discreditor (ADVERSARY)",
            goals=["Undermine, discredit, dispute, or out-compete this initiative and take its standing, users, or trust."],
            known_positions=[
                "trust: any error, inconsistency, or unfairness they ship becomes your ammunition",
                "timing: their slowness, complexity, or blind spots are your opening",
            ],
            constraints=["You are an adversary, not a team member — you reason about how to beat or delegitimize them."],
            out_of_scope=[],
            answers_for=["competition", "dispute", "legitimacy", "trust-attack"],
        ),
    ]


# ============================ helpers ========================================
def assign_models(briefs):
    specs, fams = {}, {}
    for i, b in enumerate(briefs):
        fam = FAMILY_ORDER[i % len(FAMILY_ORDER)]
        specs[b.role_id] = FAMILIES[fam]
        fams[b.role_id] = fam
    return specs, fams


def _gather_artifact(project):
    root = Path(project).expanduser()
    picks = ["prisma/schema.prisma", ".contextcore.yaml", "CLAUDE.md", "README.md"]
    parts = []
    for rel in picks:
        p = root / rel
        if p.is_file():
            txt = p.read_text(errors="ignore")[:4000]
            parts.append(f"### {rel}\n{txt}")
    return ("\n\n".join(parts))[:12000]


def _entry(answer, brief, model_spec, prompt):
    return {
        "role_id": answer.role_id, "display_name": brief.display_name, "model": model_spec,
        "prompt": prompt, "text": answer.text,
        "grounding": getattr(answer.grounding, "value", str(answer.grounding)),
        "flags": list(answer.flags), "input_tokens": int(answer.input_tokens),
        "output_tokens": int(answer.output_tokens), "cost_usd": float(answer.cost_usd),
        "created_at": answer.created_at,
    }


def _persist(session, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(session, indent=2), encoding="utf-8")


def _print_round(rnd):
    print(f"\n{'='*78}\n## {rnd['round_id']} — {rnd['title']}\n{'='*78}")
    for e in rnd["entries"]:
        print(f"\n### {e['display_name']}  [{e['model']}]  ({e['grounding']})")
        print(e["text"])


async def _run_round(round_id, title, kind, personas, prompts, specs, briefs):
    async def _one(p):
        q = prompts[p.role_id]
        ans = await p.ask(q)
        return _entry(ans, briefs[p.role_id], specs[p.role_id], q)
    entries = await asyncio.gather(*[_one(p) for p in personas])
    return {"round_id": round_id, "title": title, "kind": kind, "entries": list(entries)}


# ============================ orchestration ===================================
async def orchestrate(args):
    from startd8.secrets import hydrate
    from startd8.stakeholder_panel.roster import load_roster
    from startd8.stakeholder_panel.persona import Persona, compile_system_prompt
    from startd8.utils.agent_resolution import resolve_agent_spec

    hydrate()
    global PROJECT_NAME
    if getattr(args, "project_name", None):
        PROJECT_NAME = args.project_name  # keep prompts in the right domain (bug fix from #8)
    roster_path = Path(args.project).expanduser() / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
    roster = load_roster(roster_path)
    briefs_all = list(roster.personas)
    if args.cap:
        briefs_all = briefs_all[: args.cap]
    if args.adversary:
        briefs_all = briefs_all + _adversary_briefs()
    specs, fams = assign_models(briefs_all)
    briefs = {b.role_id: b for b in briefs_all}
    adv_ids = [b.role_id for b in briefs_all if b.role_id in ADVERSARY_IDS]

    n = len(briefs_all)
    prep_calls = int(args.ground) + int(args.assumptions) + int(args.outside_view)
    persona_rounds = 4 if args.final_judgment else 3  # R1,R2,R3(,R4)
    projected = prep_calls + n * persona_rounds + 1

    print(f"Kickoff Panel orchestrator (v0.2 / Tier-1) — {n} participants "
          f"({len(adv_ids)} adversary), {persona_rounds} persona rounds + synthesis")
    print(f"Roster: {roster_path}")
    print("Tier-1 additions:", ", ".join(
        [k for k, v in [("ground", args.ground), ("assumptions", args.assumptions),
                        ("outside-view", args.outside_view), ("adversary", args.adversary),
                        ("final-judgment", args.final_judgment)] if v]) or "(none)")
    print("\nModel assignment (de-correlation):")
    for b in briefs_all:
        tag = "  <ADVERSARY>" if b.role_id in ADVERSARY_IDS else ""
        print(f"  {b.role_id:26s} -> {specs[b.role_id]}  [{fams[b.role_id]}]{tag}")
    print(f"\nProjected model calls: {projected}  (prep {prep_calls} + {n}x{persona_rounds} + synth)")

    if not args.run:
        print("\n[DRY-RUN] No model calls made. Re-run with --run to execute (spends money).")
        return

    # ---- R0 prep (grounding + assumptions + outside view) --------------------
    prep = {"grounded_context": "", "key_assumptions": "", "outside_view": ""}
    grounded = ""
    base_ctx = _context_block(args.desc, args.objective, args.strategy)
    if args.ground:
        artifact = _gather_artifact(args.project)
        if artifact:
            g = resolve_agent_spec(FACILITATOR_SPEC, name="facilitator", system_prompt=_NEUTRAL_SYS)
            r = await g.agenerate(
                f"Here is the ACTUAL project artifact (excerpts):\n\n{artifact}\n\n"
                f"OBJECTIVE: {args.objective}\nSTRATEGY: {args.strategy}\n\n"
                "Produce a concise CURRENT-STATE summary of what this system actually is and does "
                "today (real entities/services/capabilities). Explicitly flag anything the "
                "objective/strategy ASSUMES that the artifact does NOT support or contradicts.")
            grounded = prep["grounded_context"] = r.text
            print(f"\n{'='*78}\n## R0 — Grounded current state [{FACILITATOR_SPEC}]\n{'='*78}\n{grounded}")
    ctx = _context_block(args.desc, args.objective, args.strategy, grounded)
    if args.assumptions:
        a = resolve_agent_spec(FACILITATOR_SPEC, name="assumptions", system_prompt=_NEUTRAL_SYS)
        r = await a.agenerate(
            f"{ctx}\n\nRun a KEY ASSUMPTIONS CHECK. List the 5-8 load-bearing ASSUMPTIONS this "
            "objective+strategy silently rests on. For each: state it in one line; rate CONFIDENCE "
            "(low/med/high) and IMPACT IF WRONG (low/med/high). End by naming the 2-3 high-impact / "
            "low-confidence assumptions that most need testing.")
        prep["key_assumptions"] = r.text
        print(f"\n{'='*78}\n## R0 — Key Assumptions Check [{FACILITATOR_SPEC}]\n{'='*78}\n{r.text}")
    if args.outside_view:
        o = resolve_agent_spec(OUTSIDE_VIEW_SPEC, name="outside-view", system_prompt=_NEUTRAL_SYS)
        r = await o.agenerate(
            "Take the OUTSIDE VIEW (reference-class forecasting). Ignore project specifics. For the "
            "general class = 'an established multi-currency online retailer adding complementary-"
            "product bundling + recommendations to lift AOV and conversion', what is the rough BASE "
            "RATE of such initiatives clearly succeeding, and the 3-4 most COMMON FAILURE MODES for "
            "initiatives like this? Name the reference class. Be candid about typical disappointment.")
        prep["outside_view"] = r.text
        print(f"\n{'='*78}\n## R0 — Outside View [{OUTSIDE_VIEW_SPEC}]\n{'='*78}\n{r.text}")

    # ---- build personas on assigned models -----------------------------------
    personas = []
    for b in briefs_all:
        agent = resolve_agent_spec(specs[b.role_id], name=f"persona:{b.role_id}",
                                   system_prompt=compile_system_prompt(b))
        personas.append(Persona(b, agent))

    session = {
        "session_id": f"kp-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project": Path(args.project).name, "objective": args.objective, "strategy": args.strategy,
        "prep": prep, "model_assignment": specs, "adversaries": adv_ids,
        "facilitator_model": FACILITATOR_SPEC, "rounds": [], "synthesis": None, "cost_total_usd": 0.0,
    }
    out_path = Path(args.project).expanduser() / ".startd8" / "kickoff-panel" / f"{session['session_id']}.json"

    def _adv(rid):
        return rid in ADVERSARY_IDS

    # R1 individual means-ends (adversaries get attack framing)
    r1_prompts = {b.role_id: (_r1_adversary_prompt(ctx) if _adv(b.role_id) else _r1_prompt(ctx))
                  for b in briefs_all}
    r1 = await _run_round("R1", "Individual analysis (means-ends)", "individual",
                          personas, r1_prompts, specs, briefs)
    session["rounds"].append(r1); _persist(session, out_path); _print_round(r1)

    # R2 pre-mortem (private — before the collision, for independence)
    r2_prompts = {b.role_id: _premortem_prompt(_adv(b.role_id)) for b in briefs_all}
    r2 = await _run_round("R2", "Pre-mortem (private)", "premortem",
                          personas, r2_prompts, specs, briefs)
    session["rounds"].append(r2); _persist(session, out_path); _print_round(r2)

    # R3 cross-pollination (react to R1 analyses)
    r3_prompts = {b.role_id: _r3_prompt(_digest(r1["entries"], b.role_id)) for b in briefs_all}
    r3 = await _run_round("R3", "Cross-pollination", "cross_pollination",
                          personas, r3_prompts, specs, briefs)
    session["rounds"].append(r3); _persist(session, out_path); _print_round(r3)

    # R4 final private judgment (re-independent-ize)
    if args.final_judgment:
        r4_prompts = {b.role_id: _r4_prompt() for b in briefs_all}
        r4 = await _run_round("R4", "Final private judgment", "final_judgment",
                              personas, r4_prompts, specs, briefs)
        session["rounds"].append(r4); _persist(session, out_path); _print_round(r4)

    # R5 synthesis
    transcript_text = "\n\n".join(
        f"[{r['round_id']} {r['title']}]\n" + "\n".join(
            f"{e['display_name']} ({fams[e['role_id']]}): {e['text']}" for e in r["entries"])
        for r in session["rounds"])
    synth_agent = resolve_agent_spec(FACILITATOR_SPEC, name="facilitator", system_prompt=_SYNTH_SYS)
    result = await synth_agent.agenerate(_synth_prompt(transcript_text, fams, prep), system_prompt=_SYNTH_SYS)
    synth_text = result.text if hasattr(result, "text") else str(result)
    session["synthesis"] = {"model": FACILITATOR_SPEC, "text": synth_text}
    session["cost_total_usd"] = round(sum(e["cost_usd"] for r in session["rounds"] for e in r["entries"]), 6)
    _persist(session, out_path)
    print(f"\n{'='*78}\n## R5 — Synthesis (facilitator: {FACILITATOR_SPEC})\n{'='*78}\n{synth_text}")
    print(f"\nSaved transcript: {out_path}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Facilitated multi-round kickoff panel (v0.2 / Tier-1).")
    ap.add_argument("--project", required=True, help="Project root with docs/kickoff/inputs/stakeholders.yaml")
    ap.add_argument("--objective", default=DEFAULT_OBJECTIVE)
    ap.add_argument("--strategy", default=DEFAULT_STRATEGY)
    ap.add_argument("--desc", default=DEFAULT_DESC)
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
