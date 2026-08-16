# Research note: the RETROSPECTIVE bookend as an IR feedback edge — closing the NLPS's learning loop

**Date:** 2026-08-16 · **Type:** research / design consideration (emeritus) · **Status:** for discussion
**Frames:** the Natural-Language Programming System (`~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`)
**Relates:** REQ-16 (derivation edge) · REQ-17 (`was`) · REQ-18/19 (realization + the planned-vs-realized regression signal) ·
`KAIZEN_DESIGN_PRINCIPLE.md` · `/reflective-retrospective` (the Hansei process) · `project_craft_grammar` (the grand unification)

## The gap

The NLPS has **two human bookends**: **DATA MODEL** (front — designing the contract) and **RETROSPECTIVE**
(back — reflecting after an increment and feeding lessons back to the data model). We have matured the
**front + middle** heavily (IR, oracle, human-gate, derivation, realization). The **back is the least-built
half**. In compiler terms it is the **feedback edge** — the profiler/QA feeding information back to the
source; in PDCA it is the **Check→Act** arc. Today that arc runs *out-of-band*: Kaizen emits
`kaizen-suggestions.json`, Hansei produces prose, the Proven Exemplar Pipeline promotes templates — all
real, but **none of it is expressed as IR structure**, so the loop is invisible, untraceable, and ungated
at the point that matters (where a lesson touches the contract).

## The thesis (and the anti-pattern it avoids)

**The RETROSPECTIVE bookend is the system's *least* automatable part — and that is the point.** Brooks II:
the essential-complexity residue is exactly the two human bookends; interpreting *why* an increment went as
it did is judgment, not mechanics (this is the `KAIZEN` value model — *human-in-the-loop analysis, not
autonomous self-correction*). So the IR's job here is **not to automate reflection** — it is to **structure,
ground, trace, and gate** it: make the human's retrospective *input* (grounded outcomes) and *output* (a
proposed, human-gated contract revision) **first-class, so the loop is legible and the human closes it.**
An IR that tried to auto-revise the contract would be re-automating the one step the whole reliability
architecture keeps human-gated. **The IR holds the loop; the human closes it.**

## The IR representation — a Lesson node + a `revises` (feedback) edge

The forward pipeline is derivation edges (REQ-16), pointing *downstream*:
`INTENT → FR → CONTRACT → IMPL → TEST → DOC`. The RETROSPECTIVE is the **reverse**: an increment's
*outcome* derives a *lesson* that proposes a *revision* to an *upstream* node. Two new IR elements:

- **A `Lesson` node** (`category: lesson`) — the grounded interpretation of an increment's outcomes.
  - `derives-from` (existing REQ-16 edge, backward): the increment's **grounded outcomes** — the
    planned-vs-realized regression (REQ-19 FR-6), a failing `verify` oracle, a `was`-delta (REQ-17), a
    postmortem/Kaizen finding. These are the lesson's `lives` (evidence) — *a lesson is a belief until
    grounded* (invariant 4); an ungrounded lesson is cruft.
  - `revises` (a **new backward feedback edge**): the upstream node (a contract/FR/data-model node) the
    lesson *proposes* to modify.
- Together, **forward `derived-from` + backward `revises` close the PDCA loop at the IR level** — the NLPS
  becomes a *learning* compiler, and every lesson→contract influence is traceable (Mieruka).

## The reliability architecture — propose, don't dispose

The `revises` edge **must be human-gated** — modifying the contract *is* the DATA MODEL bookend (front),
which is human-gated by design. So a Lesson node **proposes** a revision; the human **disposes** via the
`approve` field (REQ-17) + a status (`proposed | accepted | rejected`). The loop closes **through the
human**, never autonomously. This is the exact reliability invariant the front already enforces, applied to
the back: the ambiguous step (should this lesson change the contract?) stays human-gated. REQ-19's
determinism-regression signal thus gets a *home* — it becomes a grounded Lesson proposing a contract
enrichment, which a human accepts or rejects.

## What exists vs the gap (a bridge, not a rebuild)

| Piece | Exists as | Gap |
|-------|-----------|-----|
| Retrospective **analysis** | Kaizen (`kaizen-suggestions/trends/correlation`), Hansei `/reflective-retrospective`, PEP | fine — keep it |
| Retrospective **input** | `was` (REQ-17), regression signal (REQ-19), `verify` results, postmortem | grounded — reuse as `lives` |
| Retrospective **output** | `kaizen-suggestions.json` (out-of-band) | **NOT IR-expressed** — no Lesson node, no `revises` edge, no human gate at the contract |

So the work is a **bridge in the REQ-19 mould**: a stable **"lesson contract"** the Kaizen/Hansei engines
*emit* and the navigator *consumes* into Lesson nodes with grounded `derives-from` edges + a `revises` edge,
human-gated. Kaizen stays the analysis engine; the IR gains the *structure* that makes its output
first-class, traceable, and gated. (Same firewall discipline as REQ-19: the navigator depends on the lesson
contract, not on Kaizen internals.)

## The grand unification — the Lesson node is where the two pipelines fuse

This is the strategic payoff. The **Knowledge OS** (`project_craft_grammar`) is *itself* a retrospective
pipeline: experience → **lesson** → principle → skill. The **NLPS** is: functional-description → contract →
product. They were named as "two pipelines joined at the Node." The **RETROSPECTIVE bookend is the return
path that closes the join**: an increment's outcome (NLPS) authors a **Lesson** (Knowledge OS) that revises
a requirement (NLPS). The `Lesson` node is the **shared primitive** — the same shape in both systems. So
building the retrospective bookend is not just completing the NLPS; it is *welding the NLPS to the Knowledge
OS at the Lesson node* — "turning lots of good ideas into a cohesive system," made structural.

## Open research questions

- **OQ-R1 — Node, edge, or both?** A `Lesson` *node* + a `revises` *feedback edge* (my lean), vs overloading
  the existing derivation edge with a direction flag. (Both: the lesson needs its own grounded identity; the
  edge needs its own reverse semantics.)
- **OQ-R2 — Proposed-vs-accepted state.** How is the human gate modeled — `approve` + a `proposed/accepted/
  rejected` status on the `revises` edge? A rejected lesson is *retained* (a rejected-lesson is data, not
  deleted — Mottainai) with its rationale.
- **OQ-R3 — Minimal grounding for a trustable lesson.** What `lives` must a Lesson carry to not be cruft — a
  regression finding? a failing oracle? ≥N `was`-deltas? (Mirror the `realization` confidence discipline.)
- **OQ-R4 — The lesson-contract bridge.** Lift `kaizen-suggestions.json` into Lesson nodes via a typed
  contract (REQ-19 firewall pattern), or model only Kaizen's *output*? (Contract bridge — keep Kaizen
  decoupled.)
- **OQ-R5 — Loop termination.** What stops an infinite revise→increment→revise cycle? The **human gate is
  the terminator** (accept/reject), plus Hansei's loop-until-dry (K consecutive empty rounds). The IR must
  not auto-fire revisions.
- **OQ-R6 — `was` as raw material.** `was` is the measured change-delta; the Lesson is its *grounded
  interpretation* (why + what to change). Is a Lesson always `derived-from` a `was`-delta, or also from a
  single-increment outcome with no prior state?

## Where it sits in the arc (sequencing)

The retrospective bookend **consumes** REQ-18/19's output — the planned-vs-realized regression is its first,
richest *input*. So it sequences **after** the realization arc: (a)/(b) produce the grounded outcomes; the
retrospective bookend gives those outcomes a *destination* (a human-gated proposed revision to the
contract). A first increment could be narrow: **model the REQ-19 determinism-regression as a Lesson node
with a `revises` edge to the offending contract, human-gated** — the smallest end-to-end proof that the loop
closes at the IR level. Everything else (the Kaizen bridge, the general lesson contract) layers on that.

## The one-paragraph direction

Build the retrospective bookend as **IR structure, not automation**: a grounded `Lesson` node (`derives-from`
the increment's measured outcomes) + a **human-gated `revises` feedback edge** to the upstream contract —
so the NLPS's Check→Act arc becomes first-class, traceable, and gated exactly where the DATA MODEL bookend
already gates the front. Start by giving REQ-19's regression signal that home. The prize is a *learning*
NLPS that fuses with the Knowledge OS at the shared `Lesson` primitive — with the human still closing every
loop.
