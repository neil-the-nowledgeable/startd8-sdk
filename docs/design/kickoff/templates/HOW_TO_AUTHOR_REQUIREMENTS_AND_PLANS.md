# How to Author Requirements & Plans for Deterministic Generation

**Version:** 0.1
**Date:** 2026-06-05
**Audience:** Project teams (business + technical) writing a project's requirements and plan.
Plain language; no build-system knowledge assumed.
**Templates:** [`REQUIREMENTS_TEMPLATE.md`](REQUIREMENTS_TEMPLATE.md) ·
[`PLAN_TEMPLATE.md`](PLAN_TEMPLATE.md)
**Worked reference:** `strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md` + `PLAN_v3.0-draft.md`
(a real project authored this way)

---

## 1. Why the format matters (the one idea)

> **The format carries the truth; AI only carries you to the format.**

When your requirements follow this format, the build system **extracts** your application
directly from your words — your entity tables become the database, your pages table becomes the
site and its links, your view blocks become the screens — with **no AI guessing in between**.
You then walk a preview ("wireframe") of exactly what will be built, *before* anything is
built, and what you approve is what gets delivered.

When prose wanders outside the format, nothing breaks — the system simply can't extract from
it, flags the gap, and someone (usually an AI-assisted editing session with you) reshapes that
prose into the format. **The AI never fills the gap with a guess.** That's the deal: a little
formatting discipline buys you a build that does what your document says, traceably, line by
line.

## 2. The authoring process, step by step

1. **Start from the templates.** Copy both into your project's `docs/`. The `▷` guidance lines
   tell you what each section wants; delete them as you fill in.
2. **Write the Overview and Objectives first, in your own words.** This is pure prose — say
   what you're building and what success means. Make objectives measurable **when you can** —
   and when your project is too early for real numbers, a *directional* objective with its
   target marked `TBD` (dormant) is the honest, correct entry: it declares intent now and gets
   quantified when data exists. Declaring "we'll measure time-to-job, target TBD" beats
   inventing a number you don't believe — the system tracks dormant targets and reminds you
   they're awaiting a decision, it never treats them as failures.
3. **List your entities (the nouns).** Walk your product: every kind of record a user creates,
   views, or connects is an entity. One block each: a one-sentence description, a field table,
   relationship sentences. Use the plain-type words (§3). Don't over-think types — `text` vs
   `long text` is "a line vs a paragraph."
4. **List your pages and views (the screens).** Pages = the standalone content pages (a
   table — never write URLs, they're derived). Views = the composite screens, each picking one
   of the five patterns (§3). If you can't pick a pattern, describe the screen in prose and
   flag it — pattern-picking is a good AI-assisted conversation.
5. **Define "complete."** In controlled sentences: *at least N Entity*. This drives the
   in-app guidance that nudges users forward — it's guidance, never a gate.
6. **Declare what the AI does — and what it never touches.** The AI-assists table (what it
   reads, what it may suggest) and the owned-fields line (values only humans enter). These two
   sections are your control surface over the AI in the *product*.
7. **Write the FRs last.** By now they're easy: one sentence per behavior, naming the entities/
   pages/views you already defined. Add `Touches:` (which pieces are involved) and `Verify:`
   (the check that would convince *you* it works). If a requirement needs three sentences,
   it's three requirements.
8. **Then the plan:** drop your features into the three iterations (data foundation → screens
   & logic → integrations), reference the FRs each feature serves, and write the dependencies
   explicitly ("F-201 after F-101"). If most of iterations 1–2 reads "0 (deterministic)" —
   good; that's the system doing the work.
9. **Validate.** Run the wireframe (or hand the docs to your build operator): you get back a
   preview of everything extractable plus a list of anything that wasn't. Fix, re-run, walk
   the preview, sign off. *Then* the build runs.

## 3. The controlled vocabularies (the only words with rules)

| Where | Allowed values | Plain meaning |
|-------|----------------|---------------|
| Field types | `text`, `long text`, `number`, `decimal`, `date`, `date+time`, `yes/no`, `choice of: a\|b\|c` | a line · a paragraph · whole number · number with decimals · calendar date · timestamp · checkbox · pick-one |
| Relationships | **has one**, **has many**, **belongs to**, **links X to Y** / **links to many** | ownership both ways · user-made connections (never inferred) |
| View kinds | **detail-compose**, **dashboard**, **board**, **workspace**, **export-package** | one connected picture · counts & summaries · status columns · everything about one record · downloadable bundle |
| Traffic profile | **test**, **internal**, **standard**, **high-traffic** | demo · team-sized · public app · scale |
| Completeness | "at least *N* *Entity* (weight *W*)" | the formula behind the progress score |
| Owned fields | "Only humans enter: *Entity.field*" | the AI never writes these values |
| Risk types | availability, cost, quality | will it be up · will it overspend · will it be wrong |

Everything else in your document is **free prose** — encouraged, read by humans, ignored by
extraction.

## 3b. Prototype & proof-of-concept posture — what defaults cover

For a prototype or PoC (**traffic profile `test` or `internal`**), most operational values
don't need a decision at all — declaring the profile pulls a coherent **non-production default
set**, and you author only what's genuinely yours (the entities, pages, views, FRs). Defaults
are always visible as defaults (provenance `config-default`/`estimate`), never mistaken for
decisions — promote any of them to a real choice whenever you're ready.

| You can leave to defaults | `test` (demo / PoC) | `internal` (team prototype) | Becomes yours when… |
|---------------------------|---------------------|------------------------------|---------------------|
| Build spend (per run / AI monthly / infra) | $5.00 / $25 / $0 (local-only) | $10.00 / $50 / $100 | spend is real money you track |
| Model routing | standard tiers, complexity routing on | same | you have cost/quality evidence to tune |
| Observability (uptime/latency/alerts/runbook) | industry dataset, non-prod posture; fictional contacts acceptable | industry dataset; **real owner contact required** | anything user-facing/non-demo |
| Criticality | low | medium | a launch date exists |
| Risks table | industry defaults (availability/cost/quality) suffice | same + your known worries | you know a project-specific failure mode |
| Completeness section | optional — absent means a simple "has at least one of each" rule | same | "complete" has a business meaning |
| Objective targets | directional + `TBD` (dormant) is fine | same | usage data or a commitment exists |
| Deployment | local, non-production — no registry, no public exposure | same, team-reachable | production planning starts |

**What never defaults:** the entities, pages, views, AI-assists/owned-fields declarations, FRs,
and non-goals — those *are* the project; nothing can supply them but you.

## 4. The rules of thumb

1. **Headings are exact.** `## Entities`, `## Pages`, `## Functional requirements` — the
   system anchors on them. The templates have them right; don't rename.
2. **Tables and lists carry values; prose explains why.** If a value matters (a field, a page,
   a number, a dependency), it lives in a table/list row. The paragraph around it is for
   humans.
3. **One sentence, one behavior, one FR.** Compound requirements extract badly and test worse.
4. **Use the same name everywhere.** If the entity is `ProofPoint`, every FR, view, and
   completeness line says `ProofPoint` — not "evidence item" in one place and "proof" in
   another. (Synonym drift is detected and flagged, not guessed at.)
5. **Never author derived values.** No URLs (derived from page names), no dependency *graphs*
   in prose (author the explicit list), no field types beyond the plain words.
6. **Mark human-only values loudly.** `ONLY HUMANS ENTER THIS` in a field note + the owned-
   fields line. This is enforced in the build, not just documented.
7. **Non-goals are load-bearing.** What you exclude protects you from the system inventing it.
8. **When the format fights you, say so in prose and flag it** — a person + AI session will
   reshape it with you. Never force a wrong table; never leave a load-bearing value in prose.

## 5. Common mistakes (each one observed in practice)

| Mistake | Why it hurts | Instead |
|---------|--------------|---------|
| Writing routes/URLs by hand | They drift from page names; they're 100% derivable | Pages table only — routes are generated |
| Burying a field list in a paragraph | Not extractable; the entity ships without those fields until someone notices | The field table |
| "The system should be fast and reliable" as an FR | Not one behavior; not verifiable | Either a measurable NFR you'll stand behind, or leave it out |
| Inventing a view pattern ("carousel-matrix") | No generator behind it — nothing gets built | Pick from the five; describe the dream in prose + flag it |
| Letting the AI table imply it writes everything | The AI's write set IS the control surface | List exactly the entities it may suggest; everything else is human |
| Dependencies described in prose ("after the backend is mostly done…") | Un-checkable; this exact class caused a 17-task build deadlock once | Explicit `F-x after F-y` lines — the build verifies no cycles |
| Renaming an entity mid-document | Extraction sees two entities | One canonical name; synonyms get flagged for you to resolve |

## 6. What happens to your document (so the discipline feels earned)

```
your REQUIREMENTS + PLAN
   → deterministic extraction  → the data model + screens + manifests (no AI guessing)
   → wireframe preview         → YOU walk "what will be built" and sign off
   → staged build              → ① data foundation ② screens & logic ③ integrations
   → every delivered piece traces back to the table row or sentence you wrote
```

Two outputs make the loop honest: the **extraction report** (every value: extracted-from-§X /
not-extracted-with-reason — never silently guessed) and the **wireframe walkthrough** (the
lo-fi prototype of the delivery, grouped by iteration, that you accept *before* the build
spends anything).

---

*Companion specs (for build operators, not required reading for authors):
`../KICKOFF_AUTHORING_CONTRACT.md` (the extraction grammars),
`REQUIREMENTS_AND_PLAN_FORMAT.md` (the format's design rationale),
`../../wireframe/WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md` (the pipeline).*
