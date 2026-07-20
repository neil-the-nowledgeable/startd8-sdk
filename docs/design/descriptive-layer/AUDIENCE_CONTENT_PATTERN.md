# The Audience-Keyed Content Pattern (AR-2 — the reusable capability)

**Date:** 2026-07-19
**Status:** Named pattern (Yokoten of a design applied three times)
**One-liner:** *Author one canonical, audience-keyed content manifest; resolve it by (role × depth) with
graceful degradation; render it **benefit-first** (what to do + why), never in the system's own voice —
and track the authoring matrix so a gap can't hide.*

This names a design we have now built **three times**. The point of naming it: the *next* surface that
needs to speak to a non-expert should be **a config away, not a rebuild**.

---

## Where it's already applied (grounded)

| Instance | Canonical config | Resolver | Rendered surface |
|---|---|---|---|
| **Wireframe preview (FR-AUD)** | `wireframe/descriptive.yaml` (role × fluency variants per section) | `describe.py` `_variant()` → `describe()` | `wireframe_view/_template.py` (HTML), `--view-json` |
| **Benchmark reviewer `/start`** | `config/reviewer_roles.yaml` (per-role lens + rubric) | `app/reviewer_intro.py` `role_intros()` | `portal_templates/start.html` (personalized to the signed-in reviewer's role) |
| **Kickoff fluency** | `build-preferences.yaml` / global config | `concierge/audience.py` (flag→project→global→default ladder, disclosure tiers) | the guided walk (`expanded`/`light`/`compact`) |

## The four parts

1. **A canonical, single-source config.** The words live in ONE authored file, keyed by the audience
   axis; the renderer holds none (FR-DL-5). Editing the config changes every surface that reads it — and
   it can't drift from the *thing* it describes (the `/start` role block is the same YAML that seeds the
   rubric a reviewer is actually graded on).

2. **A resolver — audience → content, sparse + degrading.** Resolution is `(role, depth)` → `(role, ·)`
   → **base**, per field. An **absent** cell is never an error; it degrades to a defined fallback (never
   blank/None). An **authored** variant is self-contained — a field it omits does NOT leak the base
   (technical) voice (FR-AUD-1 / R1-F3). Default `(base-role, base-depth)` returns the base verbatim ⇒
   byte-identical, so adding the layer never regresses the existing surface.
   *Reusable seam:* `wireframe/describe.py::_variant`.

3. **Benefit-first, actionable framing — the content rules.** Every string serves the reader's goal
   (approve / curate / supply), never a narration of the system's steps:
   - **Plain language, zero jargon** (FR-AUD-C1) — enforced, not aspirational.
     *Reusable seam:* `wireframe_view/compose.py::has_jargon` (word-boundary banned-token matcher).
   - **No process-meta** (FR-AUD-C1b) — no filesystem paths, no build-pipeline framing ("we're about to
     build…"); show the *thing's* own name, not its path.
   - **What to do + why**, not a report — a headline + lead + a short "what to do" list (FR-AUD-C4);
     the **DOES / WON'T / NEED** framing per unit (FR-AUD-C2).
   - **Keep the reader's real data names** (entities/fields/roles), plain-label only tool *structural*
     labels (FR-AUD-C5).

4. **A coverage guard (optional but cheap).** The authoring matrix (`unit × role × depth × field`) is a
   `CoverageStat`; a CI test asserts the *expected* cells are authored, so adding a unit or a role
   without its content **fails CI** (Mieruka → Kaizen: you can't improve what you can't see).
   *Reusable seam:* `wireframe/descriptive_schema.py` (`field_order`, `matrix_coverage`).

## How to apply it to a new surface (the recipe)

1. **Pick the axis.** Role? Depth/fluency? Both? (Three distinct "audience" axes already exist — don't
   overload them; see [[audience-abstractions-landscape]]. Fluency is kickoff-walk depth; role is
   reviewer/consumer; keep them separate.)
2. **Author the canonical config** — one file, keyed by the axis, holding the benefit-first content.
3. **Resolve** — reuse the `_variant` degrade-ladder shape (or `role_intros()` for a flat role map);
   default resolves to the existing base ⇒ no regression.
4. **Render benefit-first** — apply the part-3 rules; run the jargon + process-meta checks over the
   *rendered* strings; personalize to the signed-in principal where there is one.
5. **Guard the matrix** — a coverage test over the expected cells, so gaps fail CI, not the user.

## The promise, realized (EC-4 — delivery-role kits)

The pattern's claim — *the next audience is a config away, not a rebuild* — is now demonstrated in the
wireframe preview itself. `wireframe/delivery_roles.py` registers the 11 FR-J delivery roles (source:
`HITM_ROLE_MODEL_REQUIREMENTS.md` §3, cited not restated) as **kits**: each declares a **base voice** it
overlays (plain `end_user` / technical `architect`) + a one-line **lens**. The resolver (`_variant`) makes
an unauthored kit inherit its base voice's authored content — so `--audience pm` renders the plain voice
and `--audience backend-dev` the technical voice with **zero per-section authoring**, each with its focus
lens. Ten new audiences arrived as a ~40-line registry + a resolver fallback + a toggle group — no content
matrix, no rebuild. That is the sparse-degrading overlay doing exactly what it promised.

## When NOT to use it (anti-patterns)

- **Over-application.** A one-off string for one audience needs no matrix. The layer is justified only
  because it is *sparse + degrading* (an absent cell is free) — if authoring a variant ever requires
  touching the resolver, the abstraction has failed. Keep it a standard, not machinery
  (Accidental-Complexity guard).
- **A new "audience" concept.** Reuse one of the three existing axes; a fourth is almost always an
  overloaded-term smell.
- **LLM-generated content.** The whole value is *deterministic, authored, byte-stable* (Hitsuzen). A
  model-written preview breaks trust and reproducibility.
- **Telemetry for a tiny matrix.** Mieruka here is a report + a CI test, not an OTel pipeline.

---

*Canonical instances + reusable seams cited above; this doc is the Yokoten (horizontal spread) of the
FR-AUD design. Related: `AUDIENCE_CONTENT_REQUIREMENTS.md` (the spec), `SELF_HOSTED_CONTENT_REQUIREMENTS.md`
(the coverage guard), `WIREFRAME_VISUAL_ENHANCEMENTS.md` (AR-2).*
