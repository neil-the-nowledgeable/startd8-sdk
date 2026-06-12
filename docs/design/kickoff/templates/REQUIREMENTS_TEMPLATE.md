# <Project> — Requirements

> **TEMPLATE** — copy into `<project>/docs/`, replace every `<…>`, delete guidance lines
> (the `▷` lines) and this banner. How-to:
> [`HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`](HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md).
> Section headings are EXACT — the build system anchors on them. Worked reference instance:
> `strtd8/docs/kickoff/REQUIREMENTS_v0.5-draft.md`.

**Project:** <name>   **Criticality:** <low|medium|high>   **Industry dataset:** <end_user_application | …>
**Version:** <0.1.0>   **Date:** <YYYY-MM-DD>
**Format:** requirements-and-plan-format v0.1 / authoring-contract grammar v0.1
**Pairs with:** `<PLAN file>`

## Overview

<2–5 sentences, plain prose: what the application is, for whom, and what's deliberately later.>

## Objectives

▷ One outcome per line a stakeholder would recognize as success — measurable when you can.
▷ Too early for numbers? A directional objective with target TBD (dormant) is correct:
▷ "O-n: <direction> — target: TBD (dormant)". Declare intent now; quantify when data exists.
- O-1: <outcome>
- O-2: <outcome>

## Risks

▷ One row per real worry. Type is one of: availability, cost, quality.
▷ Prototype/PoC: the industry default risks suffice — delete this section if you have nothing
▷ to add yet (defaults are applied and visibly marked as defaults).
| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| <type> | <what could go wrong, plainly> | <the guard> | <high|medium|low> |

## Traffic profile

Declared profile: **<test|internal|standard|high-traffic>**
▷ One word: test = demos/PoC, internal = small/team use, standard = public app, high-traffic =
▷ scale. For prototypes pick test or internal — that one word pulls the whole non-production
▷ default set (build spend, monitoring, deployment posture; see how-to §3b), so you decide less.

## Scaffold & runtime

▷ OPTIONAL — delete for prototypes (non-production defaults apply). When present, the scaffold
▷ manifest derives from this table. Settings vocabulary: package name, display name,
▷ python version, port, database, sqlite mode, migrations, logging, container, env keys.
▷ Env-key defaults must agree with inputs/build-preferences.yaml.
| Setting | Value | Plain meaning |
|---------|-------|---------------|
| package name | <name> | the package/module name |
| port | <NNNN> | |
| env keys | <KEY (optional/default)> | `.env.example` is emitted automatically |

## Entities

▷ One `###` block per kind of record. Plain types only: text, long text, number, decimal,
▷ date, date+time, yes/no, choice of: a|b|c. Relationship verbs only: has one, has many,
▷ belongs to, links X to Y / links to many. Mark human-only fields with ONLY HUMANS ENTER THIS.
▷ Don't list bookkeeping fields (ids, timestamps, ownership) — every record gets them free.

### <EntityName>
<One sentence: what this record is, in the business's own words.>

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| <field> | <plain type> | <yes|no> | <plain note, or blank> |

Relationships: a <EntityName> **<verb>** <OtherEntity>.

## Pages

▷ Routes and navigation are DERIVED from this table — never write URLs.
| Page | Purpose | Content file |
|------|---------|--------------|
| <Name> | <one phrase> | <name.md> |

▷ Optional — only when nav differs from the pages list:
Navigation:
| Label | Target |
|-------|--------|
| <Label> | <page name or screen> |

## Views

▷ One block per composite screen. Kind is one of five patterns:
▷ detail-compose (one connected picture from several record types) · dashboard (counts/summaries)
▷ · board (status columns) · workspace (everything about one record) · export-package
▷ (downloadable bundle of a workspace).

### View: <Name>
- Kind: <dashboard | board | workspace | detail-compose | export-package | import-flow | computed-panel>
- Root: <EntityName>   *(omit for import-flow / computed-panel — they carry no entity)*
- Shows: <Entity→Entity connections / fields to surface>
▷ computed-panel binds a registered compute function (e.g. the completeness score):
- Compute: <binding>   *(computed-panel only; e.g. completeness)*
▷ Scope: model makes a detail-compose a whole-model "Value Map" (every root + relations on ONE
▷ page) — and is what gives it an Empty state. Omit for the default per-row scope.
- Scope: model   *(optional; detail-compose only)*
▷ View COPY [consumed by: extraction → view_prose.yaml]. Title/Intro show on any view; the rest are
▷ per-archetype (ignored, no error, elsewhere): Empty state → Scope: model detail-compose;
▷ Success/Error/Controls → import-flow.
- Title: "<the human page heading>"   *(optional)*
- Intro: "<a short sentence under the title, in user language>"   *(optional)*
- Empty state: "<what the page shows when there are no rows>"   *(optional; Scope: model only)*
- Success: "<import-flow restore-OK copy; may use {imported} {total}>"   *(optional; import-flow)*
- Error: "<import-flow restore-fail copy; may use {errors}>"   *(optional; import-flow)*
- Controls: validate = "<label>", restore = "<label>", confirm = "<label>"   *(optional; import-flow)*
▷ Route is DERIVED by kind (simple kinds: from the view name; workspace: /<root>/{id};
▷ export-package: from its workspace). Add an explicit line only to override:
- Route: </custom-route>   *(optional)*

## Completeness

▷ Controlled sentences only: "at least <N> <Entity>" with optional "(weight W)" and a nudge.
▷ Optional for prototypes — if "complete" has no business meaning yet, delete this section; a
▷ simple "has at least one of each main record" rule applies by default.
<A record> is complete when it has:
- at least <N> <Entity> — nudge: "<the message shown until met>"
(Don't count: <entities to exclude — connection records, system logs>.)
Completeness is **guidance, never a gate**.

## AI assists

▷ What the AI does in the app. Suggestions are always unconfirmed until a human accepts them.
| Assist | Reads | Writes | Purpose |
|--------|-------|--------|---------|
| <name> | <entities or "pasted free text"> | <entities it may suggest> | <one phrase> |

## Owned fields

Only humans enter: <Entity.field, Entity.field>
▷ The AI may suggest everything AROUND these fields, never their values.

## Functional requirements

▷ One sentence, one behavior, canonical entity/page/view names. Touches drives the build's
▷ wiring; Verify is the test's seed — write it so YOU could judge whether passing satisfies you.
- **FR-1 — <Title>.** <One sentence of behavior.> Touches: <Entity, Page, View>. Verify:
  <one observable check>.
- **FR-2 — …**

## Non-goals

▷ What is explicitly NOT being built — this guards against invention as strongly as the
▷ requirements guard for delivery.
- <out of scope item>
