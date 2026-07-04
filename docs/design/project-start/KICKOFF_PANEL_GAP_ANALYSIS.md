# Kickoff Panel — Gap Analysis & Cross-Domain Wisdom

**Version:** 1.0
**Date:** 2026-07-04
**Purpose:** Audit the facilitated multi-round panel (spec
`KICKOFF_PANEL_FACILITATION_DESIGN.md`, proven through experiment #6) against the
professional workshop canon, mine adjacent fields for transferable machinery, and
produce a prioritized list of additions. Folded into the spec as v0.2.

---

## 0. Baseline — what we have

A five-move process: **R0 framing → R1 private means-ends → R2 cross-pollination →
R3 pre-mortem → R4 synthesis**, with mixed-model de-correlation, an anti-smoothing
synthesizer, and a preserved rounds×roles transcript. In workshop terms: a
**divergence → collision → critique → integration** arc, with independence
preserved at the front and diversity engineered via models. A good *skeleton*.
This doc is about what the skeleton is missing.

---

## Part 1 — Gaps vs. known-good workshop formats

### Gap 1 — We run the solution diamond; we never run the problem diamond
*(Double Diamond, British Design Council; How-Might-We, Design Sprint; Key
Assumptions Check, IC tradecraft.)* We take the objective **and the strategy** as
given and optimize within them. No serious discovery does that — the first half
interrogates whether we're solving the right problem: HMW reframing, and above all
a **Key Assumptions Check** (what does "grow AOV via bundling" silently assume —
that customers want bundles? that 6-currency support is live and not legacy? that
seasonal peak is the binding constraint?). **The single biggest structural gap:**
we are an excellent answer-refiner for an unexamined question.

### Gap 2 — No convergence / decision mechanism
*(Design Sprint dot-voting/heat-map/supervote; Delphi anonymous ranking; Nominal
Group Technique.)* We diverge, collide, critique, and *the facilitator* integrates
— but the **panel** never converges. We have no group prioritization, so we learn
*what* the risks are but not where the panel disagrees on *priority* (often the
more decision-relevant conflict).

### Gap 3 — No shared process / journey model
*(Event Storming, Brandolini; User Story Mapping, Patton.)* Personas reason about
**static domains**. The highest-value gaps hide at the **seams between journey
steps** (browse → cart → checkout → pay → ship → confirm → return). A temporal flow
model with "hotspot" markers would force "what happens to a bundle price at each
hop?" systematically rather than by luck.

### Gap 4 — No missing-stakeholder / boundary critique
*(Critical Systems Heuristics, Ulrich: who is affected but not consulted?)* The
roster is fixed and **entirely internal** — no **customer voice**, no **adversary**
(fraudster, competitor), no **regulator-as-participant**, no absent-but-affected
party (fulfillment, accessibility, sustainability given the "Blue Planet" brand). A
facilitator's reflex — "who's not in the room?" — is never triggered.

### Gap 5 — R0 is thin; the panel is still semi-blind
*(JAD pre-work; Toyota genchi genbutsu, "go and see.")* The spec says the
facilitator ingests the real artifact; the orchestrator feeds a hand-written
objective/strategy. Personas reason from a **description**, not the **system**. The
residue of the "persona is blind to the artifact" root — half-fixed.

### Gap 6 — Single-pass; mixed modes of thinking
*(Delphi iterates to convergence; Six Thinking Hats separates modes.)* Each round
runs once; open tensions are never sent back for a focused resolution round. And R1
asks for tactics + risk + blind-spot at once — de Bono's point is that mixing
generative and critical thinking degrades both.

---

## Part 2 — Cross-domain wisdom (ranked by leverage)

### 1. Intelligence-community Structured Analytic Techniques (Heuer)
The richest transfer — a tradecraft built for "rigorous collective judgment under
uncertainty while fighting bias." Three imports:
- **Key Assumptions Check** — surface load-bearing assumptions; rate confidence ×
  impact-if-wrong (fills Gap 1).
- **Analysis of Competing Hypotheses (ACH)** — seek evidence that *disconfirms*
  each option, not confirms the favored one.
- **Team A / Team B** — split the panel to argue opposite cases (the skeptic, done
  right).

### 2. The Outside View / reference-class forecasting (Kahneman; Flyvbjerg)
Our process is entirely **inside-view** — the source of the planning fallacy. Add
one pass: *"For initiatives like this in general, base rate of success + typical
failure modes?"* The model has the reference-class data in training; cheap, and it
directly corrects inside-view optimism.

### 3. Scenario planning (Wack, Shell)
Stress-test the strategy against **2–3 divergent futures** (currency-volatility
recession / viral-growth scale-crunch / competitor price war), not one assumed
future. Reveals which tactics are **robust across futures** vs. single-future bets.
The principled answer to "strategy taken as given."

### 4. Negotiation theory (Fisher & Ury; adversarial collaboration, Kahneman)
Upgrade tension resolution. Our tensions are stated as **positions** and left open.
Separate **positions from interests**, then have the two disagreeing parties
**jointly design the experiment that would resolve their disagreement**. Converts
open tensions from "noted" into an integrative solution or a **concrete test** —
our weakest output becomes our most actionable.

### 5. Threat modeling (STRIDE / attack trees)
Add **adversary personas** (fraudster, competitor, malicious insider). Constructive
stakeholders systematically miss *abuse* cases; a compliance officer is not an
attacker. Glaring absence for a payments + multi-currency retailer.

### 6. Systems thinking — Theory of Constraints (Goldratt) + leverage points (Meadows)
Ask **"what is the single binding constraint on this objective?"** (optimizing
non-constraints is waste), and push first-order risks to **second/third-order
effects** (bundling → AOV → returns → fulfillment strain → …). Elevates a risk
*list* into a causal *model*.

---

## The unifying lens — diversity-prediction theorem

Everything good we stumbled into has one theoretical home: **collective error =
average individual error − prediction diversity** (Scott Page). Wisdom of crowds
(Surowiecki) needs **diversity + independence + aggregation**. This sharpens our
choices:
- Mixed models = raising **diversity** (push further: diverse *framings* and
  *personas*, not only weights).
- R1-private = preserving **independence**.
- **R2 cross-pollination is a trade-off we've treated as free.** Letting personas
  see each other **reduces independence** — correlating their errors even as it
  surfaces collisions. The theorem says that can *lower* collective accuracy while
  *feeling* richer. Fix: be deliberate about where independence is spent — run the
  **pre-mortem before cross-pollination** (uncontaminated), treat cross-pollination
  as generative-only, and take a **final private judgment after the collision**
  (re-independent-ize) before synthesis. We currently spend independence early and
  never rebuild it.

**The highest insight of the audit:** our rounds optimize for *collision*; the math
says we should also protect *independence*, and the **sequencing** determines which
we get.

---

## What's structurally out of reach (honesty)

- **Test with real users** (Design Sprint day 5) — can't. Nearest proxy: ground the
  panel against the **actual artifact** (Sapper oracle / `survey`) so claims are
  fact-checked against the real schema/code (closes Gap 5; the one "validation"
  move within reach).
- **Tacit / experiential** knowledge and real **accountability** — unavailable.
- **True independence** — mitigated (mixed models), not achieved (shared corpora).

---

## Prioritized additions

### Tier 1 — highest leverage per unit of machinery (prototype now)
1. **Key Assumptions Check + one Outside-View pass** — fills the biggest gap;
   nearly free (two prompts).
2. **Ground R0 against the real artifact** (Sapper/`survey`) — stop reasoning about
   a system no one looked at.
3. **Adversary persona(s)** — surface the abuse cases the internal roster can't.
4. **Re-sequence for independence** — pre-mortem *before* cross-pollination + a
   **final private judgment** (a free structural change the diversity theorem says
   directly improves aggregation).

### Tier 2 — higher machinery, high payoff (next)
5. **Tensions → experiments** (negotiation / adversarial collaboration).
6. **Scenario planning** — strategy robustness across divergent futures.
7. **Group convergence** — anonymous ranking / prioritization round (Delphi).
8. **Journey/process model** as a shared artifact (Event Storming hotspots).
9. **Second-order effects + the binding constraint** (systems thinking).

---

## References (attribution)
Double Diamond (British Design Council) · Design Sprint (Knapp/GV) · JAD
(Morris/IBM) · Event Storming (Brandolini) · Story Mapping (Patton) · Six Thinking
Hats (de Bono) · Nominal Group Technique / Delphi (RAND) · Structured Analytic
Techniques & ACH (Heuer, *Psychology of Intelligence Analysis*) · Outside View /
reference-class forecasting (Kahneman & Tversky; Flyvbjerg) · Scenario planning
(Wack, Shell) · *Getting to Yes* (Fisher & Ury) · adversarial collaboration
(Kahneman) · STRIDE threat modeling (Microsoft) · Theory of Constraints (Goldratt)
· leverage points (Meadows) · pre-mortem (Klein) · Critical Systems Heuristics
(Ulrich) · diversity-prediction theorem (Page) · *The Wisdom of Crowds*
(Surowiecki) · Toyota Production System (genchi genbutsu, nemawashi, 5 Whys).
