# Kickoff Panel — Facilitated Multi-Round Process (Design Spec)

**Version:** 0.2 (Gap-analysis additions folded in)
**Date:** 2026-07-04
**Status:** Design — orchestrator built (`scripts/run_kickoff_panel.py`), Tier-1 additions prototyped.
**Tracks:** `PROJECT_START_REQUIREMENTS.md` FR-13 / FR-13b, §0.2 experiment log (runs 1–6).
**Companion:** `KICKOFF_PANEL_GAP_ANALYSIS.md` (the audit this version folds in).

> **v0.2 changes (from the gap analysis).** Audited the v0.1 process against the
> workshop canon + adjacent fields. Folded in **Tier-1** additions (§10): (1) a
> **Key Assumptions Check + Outside-View** prep pass; (2) **artifact grounding** so
> the panel reasons about the real system; (3) **adversary personas**; (4) a
> **re-sequence for independence** — pre-mortem *before* cross-pollination + a
> **final private judgment** after the collision (per the diversity-prediction
> theorem: collision costs independence, so rebuild it before aggregating). The
> canonical round order in §3 is updated accordingly; Tier-2 additions are logged
> in §10 as future work.

---

## 1. Purpose & the one-line thesis

Turn the stakeholder panel from a **mirror** (cold, single-round → personas restate
their briefs) into a **lens** (facilitated, multi-round → personas *derive* from a
shared objective into their domains, argue, and converge). The evidence for why
(five experiments, §0.2) is settled; this spec defines the **process** that
produced the lift, so it can be run repeatably.

**The product is the facilitation STRUCTURE, not the roster.** A roster without
this process reverts to a mirror.

Three empirical anchors this design is built on (§0.2):
- **Facilitation converts mirror→lens** (run 4): shared objective + strategy +
  means-ends probing produced genuine, non-obvious derivations from ~4/10 roles.
- **De-correlation makes convergence trustworthy** (run 5): personas on
  *independent model families* that converge give **model-independent evidence**,
  not a shared-model artifact.
- **The ceiling is "an excellent workshop of well-briefed generalists,"** not
  specialists with your data. Tacit/proprietary knowledge is the human's; the
  panel surfaces for **human ratification**, never decides.

---

## 2. Agents (who is in the room)

| Agent | Count | Model | Sees the real project artifact? | Job |
|-------|-------|-------|-------------------------------|-----|
| **Facilitator** | 1 | strong, fixed | **Yes** (schema/manifests/current-state) | Runs the process: frames objective→strategy, prepares personas, ladders, extracts tensions, drives synthesis. **No domain stake.** |
| **Persona** | N (roster) | **mixed families** (de-correlation) | No — brief only | Bring a role-lens; reason from the objective into their domain. |
| **Adversary persona** | 1–2 (v0.2) | distinct family | No — adversary brief | Attack/undercut the initiative (fraudster, competitor) — surfaces abuse cases the internal roster can't (Gap 4). |
| **Skeptic / Red-team** | 1 (optional) | strong, distinct family | Yes | Pre-mortem author + attacks the emerging plan. |
| **Synthesizer** | 1 (may = Facilitator) | strong | Yes (reads all rounds) | Integrate into a risk register + tensions + **open-questions-for-the-human**; preserve unresolved disagreement (anti-smoothing). |

The **Facilitator/Synthesizer seeing the artifact** is the fix for the "persona is
blind to the project" root (persona.py: *"the brief is your ENTIRE knowledge"*):
the facilitator grounds the process in reality; the personas supply lenses.

---

## 3. The rounds

Each round does a *distinct cognitive job*; collapsing them is what makes a
workshop mediocre. Rounds are sequential; personas run in parallel *within* a round.

> **v0.2 canonical sequence (re-sequenced for independence).** The diversity-
> prediction theorem says cross-pollination *spends* independence, so we do the
> uncontaminated critical work first and rebuild independence before aggregating:
>
> **R0 prep** (ground on artifact + Key Assumptions Check + Outside View) →
> **R1 individual means-ends** (private) →
> **R2 pre-mortem** (private — MOVED before the collision) →
> **R3 cross-pollination** (generative collision) →
> **R4 final private judgment** (re-independent-ize after the collision) →
> **R5 synthesis**.
>
> The prose subsections below describe each round's *job*; the order above is
> authoritative for v0.2. Adversary personas (§2) participate in R1–R4 with an
> attack-framed prompt.

### R0 — Preparation & framing (Facilitator, $-light)
- Facilitator ingests the real artifact (schema, manifests, current state) + the
  raw business objective.
- Produces the **objective → strategy skeleton** and, per persona, a
  **preparation packet** = shared context + that role's mandate + a homework prompt.
- *Human analog:* the BA's pre-read + stakeholder analysis. No stakeholder speaks yet.

### R1 — Individual analysis + laddering (Personas, parallel, private)
- Each persona answers the **means-ends probe**: *given this objective+strategy,
  in YOUR domain — (1) 2–3 highest-leverage tactics, (2) the biggest risk/tension
  the team underestimates, (3) one thing the team is NOT thinking about.*
- **Laddering** (optional, configurable depth 0–2): Facilitator probes each
  persona's answer 1–2× ("why does that matter? what would have to be true? what
  breaks?") to push past the shallow first answer.
- Uncontaminated: no persona sees another yet (avoids anchoring/groupthink).
- *Human analog:* 1:1 elicitation + critical-incident/5-whys.

### R2 — Cross-pollination (Personas, parallel, divergence)
- Each persona is shown a **digest of the other personas' R1 outputs** and asked:
  *where do you agree, where do you push back, and what does X's point imply for
  YOUR domain that you didn't already say?*
- Purpose: engineer the **seam-collisions** (merchandising × payments → a bundle
  problem neither sees alone). Divergent — generate, don't decide.
- *Human analog:* the group divergence workshop.

### R3 — Tension + pre-mortem (Personas + Skeptic, adversarial convergence)
- **Pre-mortem** (highest-yield technique): every persona answers *"it's a year
  later and this failed — from your domain, why?"* Surfaces risks people won't
  state as predictions but will as a post-hoc story.
- **Tension resolution:** Facilitator extracts the concrete conflicts from R1/R2
  and runs each as a short dialectic between the 2–3 relevant personas → a
  synthesis or an explicit, named trade-off.
- Optional **Skeptic** red-teams the emerging plan on a distinct model family.
- *Human analog:* pre-mortem + dialectical inquiry + devil's advocate.

### R4 — Synthesis & playback (Synthesizer)
- Integrate all rounds into a structured output:
  - **Risk register** — each risk + which roles/models flagged it +
    **corroboration strength** (single-model / single-family / **cross-family**).
  - **Tensions** — resolved (with the trade-off) and **unresolved** (kept open).
  - **Recommendations** — derived tactics, prioritized.
  - **Open questions for the human** — where the panel lacked ground truth or
    proprietary knowledge (the load-bearing output).
- **Playback framing:** presented as *"here is what the panel surfaced; here is
  what needs your judgment"* — never as decisions.
- *Human analog:* synthesis + playback + ratification.

---

## 4. De-correlation (mixed-model assignment) — first-class lever

Assign personas across **independent model families** (Claude / GPT / Gemini). This
is not for "more models" — it is so that **cross-role convergence becomes
model-independent evidence** (run-5 finding). Rules:
- Spread families roughly evenly across the roster.
- Put the **high-leverage roles** (those with real analytical purchase on the
  strategy) on **different families from each other**, so their agreement can't be
  a shared-model artifact.
- Facilitator/Synthesizer/Skeptic each on a **distinct** family where possible.
- The transcript records **which model produced each entry** (so corroboration
  strength is computable and visible in the UX).

Flagship specs (2026-07): `anthropic:claude-opus-4-8`, `openai:gpt-5.5`,
`gemini:gemini-3.1-pro-preview`. All keys hydrate via Doppler.

---

## 5. Safeguards

- **Anti-smoothing (critical).** The Synthesizer must **preserve unresolved
  tension** as an explicit open item — never resolve real disagreement into a
  plausible false consensus. A confident synthesizer is the main failure mode.
- **Grounding / ratify posture.** Every persona output stays synthetic/unratified
  (existing `grounding_guard` still downgrades unbacked $/%/date specifics). The
  panel **surfaces for human judgment**; the human is the sole ratifier.
- **Correlation honesty.** Convergence is labeled by strength (single-model <
  single-family < cross-family). Only cross-family convergence is called
  "trustworthy."
- **Cost bounds.** Every round is budget-gated (reuse `stakeholder_panel/budget`);
  a `--cap` bounds personas; laddering depth and the Skeptic are opt-in. The
  orchestrator prints a projected call/cost count before spending.
- **Determinism of record.** The transcript is the durable artifact (Mottainai):
  a run persists once and can be re-rendered/re-synthesized for $0.

---

## 6. Output artifact & observability contract

> This is the load-bearing interface for the end-user experience the user will
> spec separately. The orchestrator MUST emit a structured, navigable record —
> not a flat text dump — so a viewer can **expand/collapse by round AND by role**,
> and show **per-entry model attribution**. Mirrors the `consult` precedent
> (`consultation/{store,serve,_webview_template}` — show N models + their outputs).

**Session transcript schema** (`.startd8/kickoff-panel/<session_id>.json`):
```json
{
  "session_id": "kp-<ts>-<rand>",
  "created_at": "<iso8601>",
  "project": "<slug>",
  "objective": "<text>",
  "strategy": "<text>",
  "prep": {                                    // v0.2 R0 passes (each a top-level card in the UX)
    "grounded_context": "<facilitator current-state summary from the real artifact>",
    "key_assumptions": "<load-bearing assumptions + confidence×impact>",
    "outside_view": "<base rate + typical failure modes for the reference class>"
  },
  "model_assignment": { "<role_id>": "<provider:model>", "...": "..." },
  "adversaries": [ "<role_id>", "..." ],       // v0.2 — which roles are attack personas
  "facilitator_model": "<provider:model>",
  "rounds": [
    {
      "round_id": "R1",
      "title": "Individual analysis",
      "kind": "individual|cross_pollination|tension_premortem",
      "description": "<one line>",
      "entries": [
        {
          "role_id": "<slug>",
          "display_name": "<name>",
          "model": "<provider:model>",
          "prompt": "<the exact prompt sent>",
          "text": "<visible answer>",
          "grounding": "grounded|uncertain|deferred|unavailable",
          "flags": ["..."],
          "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
          "created_at": "<iso8601>"
        }
      ]
    }
  ],
  "synthesis": {
    "model": "<provider:model>",
    "risk_register": [
      { "risk": "<text>", "flagged_by": ["role_id@family", "..."],
        "corroboration": "single-model|single-family|cross-family" }
    ],
    "tensions": [ { "between": ["role","role"], "issue": "<text>",
                    "status": "resolved|open", "resolution": "<text|null>" } ],
    "recommendations": [ "<text>" ],
    "open_questions": [ "<text>" ],
    "text": "<full synthesis prose>"
  },
  "cost_total_usd": 0.0
}
```

**Why this shape:** the two UX axes the user named map directly to the structure —
*expand/collapse by round* = `rounds[]`; *expand/collapse by role* =
`rounds[].entries[].role_id` (and a role-major re-pivot is a pure view transform
over the same records). Model attribution is on every entry. The orchestrator also
emits a **rendered Markdown** view (round → role) for CLI/immediate reading; the
JSON is the source of truth a future web/TUI viewer consumes.

**Live-follow (future UX, user-authored reqs):** the user wants the ability to
**follow the process as it happens** (validation-by-observation + inspiration),
with no formal validation/inspiration capability required now. Design implication
for the orchestrator: emit each entry **incrementally** (append to the transcript
and/or stream an event per completed entry) so a viewer can render rounds/roles as
they complete, not only at the end. The orchestrator therefore writes
round-by-round (append), never a single terminal dump.

---

## 7. The honest ceiling (carried from §0.2, keep visible)

1. **Correlated blind spots** are *mitigated* (mixed-model), not eliminated — the
   families still share large training overlap.
2. **No tacit/proprietary knowledge** — output is competent-generalist grade
   (obvious-to-expert, invisible-to-novice: the useful zone), not a specialist
   with your customers/market/history.
3. **Diminishing returns / cost** — more rounds multiply calls; find the knee.
   Pre-mortem and cross-family are the high-yield levers; laddering depth > 2 and
   large rosters are where returns fade.
4. **The ratification anchor holds** — a better process makes the panel more
   *worth consulting*, never *authoritative*.

---

## 8. Non-goals (now)

- No formal **validation** or **inspiration** capability (scoring, acceptance
  gates, idea-promotion) — the end-user value at this stage is *observation* only.
- No new persona-brief authoring UX (rosters come from the existing strict format
  + migration path).
- Not merging into the kernel yet — this is the FR-13b facilitation capability,
  proven via orchestrator before any productization.

---

## 9. Orchestrator implementation notes

Built on existing panel APIs (no new persona machinery):
- Roster: `stakeholder_panel.roster.parse_roster`.
- Per-persona agent on its **assigned** model: `resolve_agent_spec(model,
  system_prompt=compile_system_prompt(brief))` → wrap in `stakeholder_panel.persona.Persona`
  (its bounded within-role history threads R1→R2→R3 continuity; cross-role context
  is injected into the round's question text).
- Facilitator/Synthesizer/Skeptic: `resolve_agent_spec(model, system_prompt=…)`
  plain agents via `.agenerate(prompt)`.
- Each `Persona.ask()` returns a `PanelAnswer` (role, model, grounding, flags,
  tokens, cost) → one transcript `entry`.
- CLI: a `scripts/run_kickoff_panel.py` runner (consistent with the ~52 script
  runners). `--dry-run` prints the round plan + projected call/cost with **zero**
  model calls; `--cap`, `--ladder N`, `--skeptic` gate scope/cost.
- Persist to `.startd8/kickoff-panel/<session_id>.json` incrementally (round-by-round).

---

---

## 10. Known gaps & cross-domain additions

Full audit: `KICKOFF_PANEL_GAP_ANALYSIS.md`. Summary of what v0.2 folds in and
what remains.

### Tier 1 — prototyped in v0.2 (orchestrator flags, default on)
1. **Key Assumptions Check + Outside View** (`--assumptions`, `--outside-view`) —
   R0 prep passes. Surfaces the plan's load-bearing assumptions (confidence ×
   impact) and the reference-class base rate / typical failure modes. Fills the
   biggest gap (we optimized a solution without examining the problem). *IC
   tradecraft (Heuer) + reference-class forecasting (Kahneman/Flyvbjerg).*
2. **Artifact grounding** (`--ground`) — the facilitator reads the real project
   artifact and emits a current-state summary injected into the shared context, so
   personas reason about the system, not a description. *Toyota genchi genbutsu.*
3. **Adversary personas** (`--adversary`) — 1–2 attack personas (fraud, competitor)
   with an attack-framed prompt. Surfaces abuse cases the internal roster can't.
   *STRIDE threat modeling.*
4. **Re-sequence for independence** (default) — pre-mortem *before* cross-
   pollination + a **final private judgment** after. *Diversity-prediction theorem
   (Page): collision spends independence; rebuild it before aggregating.*

> **Experiment-#7 refinement — the assumptions check must GATE, not just inform.**
> In the first Tier-1 run the grounding + assumptions passes discovered the *entire
> premise was false* (the objective targeted a system that doesn't exist) — yet the
> orchestrator still spent 48 persona calls analyzing the phantom. **v0.2.1: after
> R0, if the Key Assumptions Check returns ≥2 high-impact / low-confidence
> assumptions, HALT and surface "validate the premise before running the panel"**
> rather than proceeding. Catching a false premise is the single highest-value
> output a discovery can produce; it should short-circuit, not footnote.

### Tier 1 — hardening (REQUIRED before productization; experiments #7/#8, FR-13c)
- **H1. Artifact-grounding fidelity (biggest lever).** R0 grounding reads only
  `schema.prisma` + truncated files → under-reads a running system (#8) and rates
  real capabilities LOW-confidence for want of evidence. Read the actual `app/` +
  wire `survey`/Sapper so grounding reflects reality, not the schema alone.
- **H2. Assumptions check as a GATE** (v0.2.1): ≥2 high-impact/low-confidence
  assumptions ⇒ halt, surface "validate the premise first", don't spend the rounds.
- **H3. Cost tracking** — per-call `cost_usd` reads `0.0`; wire real attribution.
- *(Fixed post-#8: `--project-name` flag — default domain no longer leaks.)*

### Tier 2 — future (higher machinery, high payoff)
5. **Tensions → experiments** — decompose each open tension to interests; the two
   parties jointly propose the test that resolves it. *Fisher & Ury; adversarial
   collaboration (Kahneman).*
6. **Scenario planning** — react to 2–3 divergent futures; find robust tactics. *Wack/Shell.*
7. **Group convergence** — anonymous ranking / prioritization round. *Delphi/NGT.*
8. **Journey/process model** — shared temporal map; find seam-gaps + hotspots. *Event Storming.*
9. **Second-order effects + the binding constraint.** *Theory of Constraints; Meadows.*

### Structurally out of reach (do not pretend)
Test-with-real-users, tacit/proprietary knowledge, real accountability, true
independence. Nearest proxy for "validate against reality" = artifact grounding
(#2) + a future fact-check pass against the Sapper oracle.

---

*Draft 0.2 — Tier-1 additions prototyped in `scripts/run_kickoff_panel.py`. The
user authors the end-user observability UX reqs (expand/collapse by round & role,
live-follow, the §6 `prep` cards) over the §6 transcript contract.*
