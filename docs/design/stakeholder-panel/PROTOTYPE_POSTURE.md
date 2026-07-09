# Stakeholder Panel — Prototype Posture (early-stage / UX)

**Status:** implemented · **Date:** 2026-07-09 · branch `feat/panel-prototype-posture`

## Problem

The facilitated stakeholder panel (`stakeholder_panel/facilitation.py`) is, by construction, a
**strategic red-team / go-no-go** instrument:

- a **Key Assumptions gate** that HALTS the run when ≥2 load-bearing assumptions are
  high-impact/low-confidence (*"validate the premise first"*),
- two **attack adversaries** (`adversary-exploit`, `adversary-discredit`) whose briefs are to
  *exploit / discredit / out-compete* the initiative,
- **failure pre-mortems** (*"it failed badly / you won by beating them"*),
- round + synthesis prompts oriented to *risk, tension, and attack surface*.

That is the right posture for a funded go/no-go. It is the **wrong** posture for an **early
prototype** whose owner wants concrete **UX-improvement suggestions**. Worse, the assumptions gate is
*structurally guaranteed* to halt any early-stage project — an early prototype has ≥2 unproven
load-bearing assumptions **by definition** — so the panel spends $0 and returns a premise trial
instead of the UX feedback that was asked for. (Observed live on `household-o11y`, 2026-07-09: halted
at the gate, 8 risky assumptions, no synthesis.)

## Solution — a `posture` on `FacilitationConfig`

Additive, backward-compatible. Default `scrutiny` is byte-unchanged.

| Element | `scrutiny` (default) | `prototype` (new) |
|---|---|---|
| Challenger | 2 attack adversaries | **1** constructive `skeptical-new-user` |
| Assumptions check | premise **HALT** gate (≥ threshold) | **non-blocking readiness note** (never halts) |
| R1 | biggest risk / what team underestimates | highest-leverage **UX improvements**, top friction, a quick win |
| R2 pre-mortem | "it failed badly / you won" | **"first-week check"** — what makes a new user bounce |
| R3 | "surface tension, don't agree" | "**build on** others' ideas; name real trade-offs" |
| R4 / synthesis | Risk Register / Adversary Findings / Assumptions At Risk | **Prioritized UX Improvements / Quick Wins / Bigger Bets** / Tensions / Open Qs |

Tension-preservation (FR-GE-12 anti-smoothing), grounding (H1), budget ceiling (H3), and the
transcript contract are **unchanged** across postures — only framing, the challenger, and the gate's
blocking-ness differ. Posture chosen for depth: *"constructive but keep a skeptic"* — one honest
skeptical-user voice + a week-one-bounce pre-mortem retain a reality check without the red-team.

## Surface

- API: `FacilitationConfig(posture="scrutiny"|"prototype")` (validated in `__post_init__`).
- CLI: `run_kickoff_panel.py --posture scrutiny|prototype` (default `scrutiny`).
- Constants: `POSTURE_SCRUTINY`, `POSTURE_PROTOTYPE`, `POSTURES`, `SKEPTIC_IDS`, `CHALLENGER_IDS`.

## Incidental fix — outside-view reference class

The R0 outside-view (base-rate) pass had a **hardcoded Online-Boutique reference class** (*"an
established multi-currency online retailer adding … bundling + recommendations"*) — stale copy-paste
from the benchmark that silently mis-forecast every non-OB project. Now **derived from the project's
own objective/strategy** (the model names the reference class). Applies to both postures.

## Tests

`tests/unit/stakeholder_panel/test_facilitation_posture.py` (9 tests, offline/$0): default & invalid
posture; skeptic-vs-adversary selection; **prototype does not halt** on risky assumptions while
**scrutiny still does** (regression); constructive round/synthesis framing vs unchanged scrutiny
framing; derived outside-view reference class. Full `stakeholder_panel` suite green (241 passed).

## Not done / future

- No HTTP route for the facilitation (still CLI-only); the run endpoint's `/stakeholders/*` pipeline
  is unchanged. A future increment could expose posture selection to the Grafana panel.
- `prototype` keeps `outside_view` on by default (now derived); callers wanting a lighter run can
  `--no-outside-view`.
