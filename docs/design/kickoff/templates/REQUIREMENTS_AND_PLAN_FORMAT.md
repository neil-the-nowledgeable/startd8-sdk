# Project Requirements & Plan — Authoring Format (deterministic-assembly compliant)

**Version:** 0.1 (Draft)
**Date:** 2026-06-05
**Status:** Draft — the StartDate proof-of-concept format
**Parent:** [`../KICKOFF_AUTHORING_CONTRACT.md`](../KICKOFF_AUTHORING_CONTRACT.md) (the
per-manifest grammars this format embeds) ·
[`../../wireframe/WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md`](../../wireframe/WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md)
(the pipeline that consumes it)

> **Explicit PoC goal (operator-stated).** For StartDate we control how the requirements and
> plan are created — so this format is **designed backwards from the existing deterministic
> assembly, validation, and repair capabilities**: every section below exists because a
> specific machine already consumes that shape. Authoring to this format makes the
> prose→manifests→wireframe→build chain *academic* — maximum deterministic compliance first,
> as the baseline from which more capable inference is later allowed to relax the format.
> Each section is annotated **[consumed by: …]** so the backwards-design is auditable.

---

## Part A — Requirements document format (`REQUIREMENTS.md`)

````markdown
# <Project> — Requirements

**Project:** <name>   **Criticality:** <low|medium|high>   **Industry dataset:** <end_user_application>
**Format:** requirements-and-plan-format v0.1 / authoring-contract grammar v<corpus-snapshot>

## Overview
<2–5 sentences of plain prose: what the application is and for whom.>
[consumed by: POLISH section gate; runbook overview seed]

## Objectives
- O-1: <one measurable outcome>
- O-2: …
[consumed by: POLISH; manifest strategy/objectives bootstrap]

## Risks
| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| <availability\|cost\|quality> | <risk> | <guard> | <high\|medium\|low> |
[consumed by: POLISH; REQ-CDP-INT-002 structured-risk gate; runbook/dashboard generators]

## Traffic profile
Declared profile: **<test|internal|standard|high-traffic>**
[consumed by: REQ-CDP-INT-003 throughput derivation]

## Scaffold & runtime   *(optional — defaults apply when absent)*
<Setting | Value | Plain meaning table, contract §2.7 — package name, port, database, env keys…>
[consumed by: extraction → app.yaml (generate scaffold); grammar contributed by strtd8 0.5.2]

## Entities
<one block per entity, authoring-contract §2.1: `### Name` + field table (plain-type
vocabulary) + controlled relationship sentences>
[consumed by: manifest extraction → schema.prisma draft → generate backend/views; corpus terms]

## Pages
<single table, contract §2.2 — routes/nav are DERIVED, never authored>
[consumed by: extraction → pages.yaml → generate backend --pages]

## Views
<one constrained block per view, contract §2.3, archetype from the published five>
[consumed by: extraction → views.yaml → generate views]
<optional per-view COPY keys — Title/Intro (any view), Empty state (Scope: model detail-compose),
Success/Error/Controls (import-flow) — authored inline in the `### View:` block; off-archetype keys
are ignored without error>
[consumed by: extraction → view_prose.yaml → generate views --view-prose; the WORDS layer,
hash-exempt — see "Words vs Structure" below]

## Completeness
<controlled sentences, contract §2.4: "at least N Entity (weight W)" + don't-count line>
[consumed by: extraction → completeness.yaml]

## AI assists
<table, contract §2.5: Assist | Reads | Writes | Purpose>
[consumed by: extraction → ai_passes.yaml; prompt paths derived]

## Owned fields
Only humans enter: <Entity.field, …>
[consumed by: extraction → human_inputs.yaml; FR-6-class enforcement]

## Functional requirements
- **FR-1 — <Title>.** <ONE sentence of behavior, naming entities/pages/views by their
  canonical terms.> Touches: <Entity, Page, View refs>. Verify: <one observable check a test
  can assert>.
- **FR-2 — …**
[consumed by: plan-ingestion PARSE (features); `Touches:` → deterministic target/linkage
enrichment; `Verify:` → the requirement→test traceability matrix (semantically verifiable
tests — the Testing Engineer's gate artifact)]

## Non-goals
- <explicitly out of scope, one per line>
[consumed by: negative_scope enrichment — the "don't invent this" guard]
````

**Format rules (the compliance contract):**
1. Section headings are **exact** (the POLISH/extraction anchors).
2. Lists and tables over prose wherever a value is load-bearing — prose explains *why*, never
   carries a value a table could.
3. One sentence per FR; one behavior per FR; canonical terms only (corpus synonyms get
   canonicalized at extraction, flagged if low-confidence).
4. Every FR has a `Verify:` clause — no FR enters the plan without a checkable outcome.
5. Anything outside these sections is free prose — welcome, and ignored by extraction.

## Part B — Plan document format (`PLAN.md`)

````markdown
# <Project> — Plan

## Overview
<how the build proceeds, 2–4 sentences>

## Iterations
### Iteration 1 — framework + persistence
| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-101 scaffold + contract projection | FR-1, FR-2 | app/tables.py, app/main.py | 0 (deterministic) |

### Iteration 2 — display + business logic
| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-201 value-map view | FR-7 | app/value_map.py | 120 |

### Iteration 3 — integration + content population
| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-301 extract pass wiring | FR-11 | app/ai/extract.py, prompts/extract.md | 150 |

## Dependencies
- F-201 after F-101
- F-301 after F-201
[AUTHORED explicitly and acyclically — never LLM-derived; validated by the queue cycle check]

## Budget & routing
Per `docs/kickoff/inputs/build-preferences.yaml` (referenced, not restated).
````

**Why these exact shapes:** the iteration tables are the *pre-formatted version* of what PARSE
extracts and the deterministic transform re-emits (feature name/description, `target_files`,
`estimated_loc` — the golden-seed enrichment fields, authored instead of derived); explicit
acyclic dependencies close the known LLM-dependency-graph failure (the run-018 deadlock class)
at authoring time; the three iterations are the staged prime-contractor passes and the
wireframe's FR-WPI-9 delivery-inventory grouping — one vocabulary end to end.

## Part C — Worked micro-sample (StartDate flavor)

```markdown
### ProofPoint
A concrete piece of evidence the user provides about their work.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| title | text | yes | |
| story | long text | no | the STAR narrative |
| value | number | no | ONLY HUMANS ENTER THIS |

Relationships: a ProofPoint **belongs to** a Profile; a ProofPoint **links** Capability **to** Outcome.

## Pages
| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing + orientation | home.md |
| How it works | The method, explained | how_it_works.md |

## Functional requirements
- **FR-7 — Value map.** A user sees their Capabilities connected to Outcomes and ProofPoints,
  using only links they created. Touches: Capability, Outcome, ProofPoint, Value Map (view).
  Verify: a profile with one user-created Capability→Outcome link renders exactly one edge;
  an unlinked Capability shows the "not yet linked" nudge.

## Non-goals
- No pipeline/funnel tracking in MVP-1.
```

From this sample alone, deterministic extraction yields: the `ProofPoint` model (+ join model
from the **links** sentence), the owned-field policy line, two pages with derived routes
`/` and `/how-it-works`, an FR-7 feature with its entity linkage and a verifiable test seed —
zero LLM calls.

## Part D — Document lifecycle conventions (human-only; ignored by extraction)

These conventions structure how a requirements/plan doc **evolves** across the reflective-requirements
loop. They are **pure human convention** — extraction ignores any non-anchored section, so adding them
carries **zero parser risk**. Use them so a reader (human or a later agent) can see *what changed and
why*, not just the final state. The template ships the empty scaffolds; fill them as the doc matures.

1. **Version/date lineage header.** The doc header carries a `**Version:**` + `**Date:**` + `**Status:**`
   line that advances with each pass (`0.1 Draft → 0.2 Post-planning → 0.3 Post-CRP → …`). The version is
   a *lineage*, not a label: every bump corresponds to a recorded reason below.

2. **§0 Planning Insights table.** The first section (before the problem statement) records what the
   planning pass falsified, keyed v(n-1)→v(n):

   ```markdown
   ## 0. Planning Insights (Self-Reflective Update)
   | v(n-1) Assumption | Planning Discovery | Impact |
   |-------------------|--------------------|--------|
   | <what was assumed> | <what planning revealed> | <how the requirement changed> |
   ```

3. **"What changed in vX" callout.** A one-paragraph blockquote at the top of a revised section noting
   the delta, so a reader scanning the doc sees the change without diffing.

4. **Implementation Reflections.** Phase-6 findings (discovered *during* implementation) are fed back
   into the doc — not just fixed in code — as a dated note on the affected FR. (This doc's own
   v0.7→v0.9 history is the worked example.)

5. **Appendix A/B/C — the CRP review-log scaffold.** Convergent-review dispositions are cross-model
   memory; keep them, never strip them:

   ```markdown
   ## Appendix A — Accepted (with where merged)
   ## Appendix B — Rejected (with rationale)
   ## Appendix C — Incoming review rounds (#### Review Round R{n} — <model-id> — <UTC date>)
   ```

   Appendix A/B are populated by triage; Appendix C accrues raw rounds. A later reviewer reads all
   three before proposing, so settled/rejected items don't resurface.

## Words vs Structure — classifying a new file-shaped input

When a feature adds a **new file-shaped input**, classify it before wiring, and route accordingly:

- **Hashed structure** — a `views.yaml` section *or* a standalone **hashed** manifest. It participates
  in the drift hash; a change is a deliberate structural edit a regen reflects. *Shipped example:*
  `display.yaml` (presentation structure — list columns, sections, label fields).
- **Hash-exempt prose (words)** — a standalone file **rendered to an untracked fragment**, referenced
  by the owned template **only when present**, so absent ⇒ byte-identical output. *Shipped example:*
  `view_prose.yaml` (the view words — title/intro/empty/success/error/controls), beside `app/pages/*.md`.

The split is the [SOTTO design principle](../../../design-princples/SOTTO_DESIGN_PRINCIPLE.md) — *"don't
disturb what exists."* Inlining words into a hashed file (or hashing a words file) is the classic
violation: editing copy then trips `--check` and propagates downstream drift.

## Acceptance criteria for a new $0-codegen manifest feature

The recurring ACs proven by the deterministic cascade — a reusable checklist for any new
deterministic-manifest feature (the words-layer entries are referenced from the **Views** copy keys above):

- [ ] **Byte-identical-when-absent** — shipping the capability changes nothing for a no-content build.
- [ ] **Fail-closed on a malformed manifest** — a broken manifest is a loud error, never a silent skip.
- [ ] **Drift-stability** — editing hash-exempt content never trips `generate … --check`.
- [ ] **Strict, loud-fail parse** — unknown keys / dangling targets are compile-time errors keyed to a
      known structural element.
- [ ] **Prose-gated opt-in** — the owned-template reference is emitted only when content is present, so
      there is no downstream drift.

## Open questions

1. Should the FR `Verify:` grammar get controlled patterns of its own (given/when/then vs free
   sentence) for deterministic test-skeleton emission, or stay free-form for the test engineer?
2. Linting surface: extend POLISH, or a `--lint` extraction dry-run (contract OQ-2)?
3. Versioned co-evolution: this format vs the authoring contract vs the corpus snapshot — one
   version triple stamped in the doc header (current lean, as drafted above).
