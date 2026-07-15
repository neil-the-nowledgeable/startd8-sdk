# Hansei — Reflect on the Actuals, Standardize the Gain

**Status:** Living guidance.
**Lineage:** Toyota *Hansei* (反省 — honest after-the-fact self-reflection) + *Yokoten*
(横展 — horizontal spread of a proven practice). The reflect-after-doing complement to
forward planning.
**Operationalized by:** the `/reflective-retrospective` skill (the inductive twin of
`/reflective-requirements`).

---

## The Principle

> After you do a thing, reflect on **what actually happened** — the code, the logs, the
> diffs, the observed behavior, *not* the docs or the plan or your belief about it — extract
> the process/standard it **proved**, and spread it. The learning invested in a pilot is
> preserved and made repeatable, and the map is re-grounded in the territory.

The shadow it names: **un-grounded reflection.** Reflecting on the *doc* instead of the
*code*, on the *plan* instead of the *run*, manufactures a false map — and false maps drift
in both directions (closed loops look open, open loops look closed).

## Why This Matters

- A pilot, spike, or shipped mess contains **proven** learning — a process that actually
  worked, an invariant that actually held. Not codifying it is Mottainai: the invested
  discovery is discarded and re-derived (or lost) next time.
- The strongest evidence you will ever have about a system is **the system running.** A spec
  reflects on an imagined implementation; Hansei reflects on the real one. It is epistemically
  stronger precisely because it is retrospective.
- Docs decay faster than code changes. Only going to the actuals reconciles the two — and the
  reconciliation itself is a standardizable gain.

## The Rules

1. **Go to the actuals (Genchi Genbutsu is the precondition).** Read the implementation, not
   its docstring; the run's output, not the plan for the run. You cannot Hansei on a proxy.
2. **Surprise is the ore.** The gap between what you *believed* you built and what you
   *actually* built is the richest finding — it is exactly what a forward spec could not have
   predicted. Zero surprises usually means you reflected on the docs, not the code.
3. **Standardize the gain.** Codify what the pilot proved, grounded — every clause cites the
   file/line/log that establishes it. A standard the pilot did not exercise is speculation.
4. **Yokoten, then feed forward.** Spread the proven standard to its sibling instances, and
   feed it into the next forward-planning pass. Hansei (Check→Act) and reflective-requirements
   (Plan→Do) compose into one continuous learning loop.
5. **Expect drift both ways.** Assume the map is wrong until the territory confirms it — and
   wrong in both directions.

## The Diagnostic Question

> **"Did I reflect on what *actually happened* — or on what I *believe/planned* happened?"**

And the extraction follow-up:

> **"What did this pilot *prove* that I have not yet written down?"**

## Relationship to Other Principles

- **Genchi Genbutsu** — its precondition. You must *go and see the actual thing* before you
  can honestly reflect on it. Hansei is Genchi Genbutsu pointed backward at your own work.
- **Mottainai** — Hansei preserves the invested learning of a pilot instead of discarding it;
  Yokoten forwards the gain instead of regenerating it.
- **Kaizen** — Hansei is the *reflection* step of continuous improvement; without it, kaizen
  has no memory.
- **Personal Conway** — the direct counterweight to the "map lags the territory in both
  directions" facet: Hansei re-grounds the map by construction.

## Instances (grounded — this corpus, 2026-07)

- **The Controlled-Corpus pilot.** Believed dormant (per the ledger + docstrings); the actuals
  (`prime_contractor.py:3990`, `prime_postmortem.py:3282`) showed it **L3-wired behind a
  default-off flag** — the docstrings were stale. Hansei corrected the docstrings and the
  ledger, and extracted the standard *"ground the ledger against the code, never the doc."*
- **The whole corpus session.** Mining the lived corpus → extracting the RE-OS, the archetype
  library, and the Personal Conway principle *was* a Hansei loop: reflect on the actuals →
  standardize the gain.
- **This skill itself.** `/reflective-retrospective` was extracted from the closure-sprint
  pilot — the loop was formalized by running it once and standardizing what it proved.

---

*The forward loop keeps you from building the wrong thing. Hansei keeps the right things you
already built from being lost, mis-mapped, or re-derived. Do first; then standardize the gain.*
