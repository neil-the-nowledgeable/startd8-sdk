# CRP Focus — Descriptive Layer (R1)

**Target:** the two least-reviewed docs `DESCRIPTIVE_LAYER_REQUIREMENTS.md` (v0.3.1) +
`DESCRIPTIVE_LAYER_PLAN.md` (v0.2). No prior CRP rounds — Appendix A/B/C are empty scaffolds
(initialize them). This is the first external pass.

**What it is:** a deterministic descriptive/UX "meta layer" that wraps raw `startd8` command
output (piloting on `startd8 wireframe`, generalizing to the Requirements Navigator / NODE-SCHEMA
nodes). Each output-unit declares WHAT/HOW/WHY/DO/NEXT + workflow grounding. Modeled on the
`3xl-kcui` declarative-manifest pattern (`~/Documents/dev/cui/3xl-kcui`).

## Settled — DO NOT relitigate (decided via the reflective loop)
1. **Deterministic, no-LLM** (FR-DL-8, Hitsuzen). Do not propose LLM narration.
2. **Extends the existing FR-W5 `consequence` seed** and reuses the wireframe's renderer + 5-status
   model + `worst()` roll-up (§0). Do not propose rebuilding these (Mottainai).
3. **NODE-SCHEMA fields reused by reference, not re-spec'd** (FR-DL-10).
4. **Read-only scope** — no mutation/confirm/blast-radius ceremony (NR-3, NR-5).
5. **Concept-key naming** (`FR-DL` prefix) is fixed.

## Weight the review on these UNKNOWNS (where the internal loop is blind)
1. **OQ-2 — manifest format/home:** YAML data file vs Python module beside the renderer. Trade-offs
   for single-sourcing, testing, and the composer.
2. **OQ-3 — interactivity:** printed action hints (one-shot CLI) now vs selectable affordances
   (needs a REPL). Is deferring interactivity right, or does it bake in a wrong boundary?
3. **OQ-5 — navigator reuse (the big lever):** should the manifest ALSO generate the three
   navigator READMEs, making it the single source behind both the static navigators and the live
   CLI? Scope vs Mottainai payoff.
4. **Record schema completeness:** are `what/how/why/do/next/degrade` the right fields — or is one
   missing? (3xl-kcui carries an `audience` dimension and provenance; NODE-SCHEMA has `confidence`.
   Should a descriptive record carry `audience` and/or `confidence`?)
5. **FR-DL-4 workflow-position inference heuristic robustness:** inferring position from the status
   mix (mostly `not_defined` ⇒ early DATA MODEL). Failure modes? Should position be authored, not
   inferred?
6. **FR-DL-5 composer template-fill (CCbC):** interface/data risks — unfillable placeholders,
   partial plan data, byte-stability of the deterministic output.
