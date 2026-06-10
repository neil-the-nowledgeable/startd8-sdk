# Prisma Emitter (DRAFT mode) — Requirements

**Version:** 0.1 (Draft)
**Date:** 2026-06-08
**Status:** Draft — for SDK-team build
**Scope:** Realize the **deferred half of FR-WPI-8** — the `schema.prisma` **writer** ("DRAFT
mode", a.k.a. the "P7 Prisma emitter") — so the entity tables of an authoring-contract
requirements document can be **emitted as `schema.prisma`**, not merely diffed against a
hand-authored one. This completes the manifest-derivation story: today six YAML manifests derive
from the requirements doc; the contract (`schema.prisma`) is the **only** remaining hand-authored
build input. This capability makes it derived too.
**Requested by:** the StartDate (strtd8) app team. **Goal in their words:** *minimize hand-editing,
maximize parsing of requirements/docs/config → deterministic generation.* Making `schema.prisma`
a derived artifact removes the last hand-authored manifest from the build path.
**Related:**
- [`WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md`](WIREFRAME_INGESTION_WIRING_REQUIREMENTS.md)
  FR-WPI-8 (the DIFF/DRAFT split this realizes) · FR-WPI-4 (round-trip-before-write invariant) ·
  FR-WPI-5 (promotion ratchet) · FR-WPI-3/7 (report identity + semantic hashing)
- [`WIREFRAME_INGESTION_WIRING_PLAN.md`](WIREFRAME_INGESTION_WIRING_PLAN.md) **P7 — Deferred:
  Prisma emitter** (this is its requirements; reference pattern named there:
  `scaffold_codegen/renderers.py` text rendering)
- [`../kickoff/KICKOFF_AUTHORING_CONTRACT.md`](../kickoff/KICKOFF_AUTHORING_CONTRACT.md) §2.1 —
  the entity-table + relationship grammar this emits from (the **input** side already built)
- `src/startd8/manifest_extraction/entities.py` — `extract_entities()` already produces the
  `EntityGraph` AST this emitter renders; `diff_against_live()` is the parity oracle to upgrade
- `src/startd8/languages/prisma_parser.py` — `parse_prisma_schema()` is the round-trip validator
- strtd8 app: `docs/kickoff/REQUIREMENTS_v0.5-draft.md` (the reference requirements doc),
  `docs/kickoff/CONTENT_IMPORT_REQUIREMENTS_v0.2-draft.md` (the first NEW entities to flow through
  this), `docs/kickoff/VALIDATION_AND_MANIFEST_DERIVATION.md` (the app-side derivation ledger)

---

## 0. Planning Insights (from a code-investigation pass, 2026-06-08)

> Two parallel code sweeps (app repo + SDK repo) plus direct reads of `entities.py`,
> `prisma_parser.py`, the live `schema.prisma`, and the FR-WPI doc set established what already
> exists and where the real gaps are. Net effect: **the input side is done; the emitter is a
> bounded rendering step; the hard part is two grammar gaps and one app-side prerequisite.**

| Pre-investigation assumption | What the code revealed | Impact on this spec |
|------------------------------|------------------------|---------------------|
| Emitting `schema.prisma` from the doc is a from-scratch parser | `entities.py::extract_entities()` **already parses** the `### Entity` tables into a typed `EntityGraph` — `DocEntity`/`DocField` (with `prisma_type` already mapped via `PLAIN_TYPES`), `JoinModel` (with FK derivation), and `fk_parents` (has-many/belongs-to) | The emitter is **rendering only** — no new parsing. Input AST is built and tested. |
| The doc tables list every column | The 6 **bookkeeping fields** (`id/ownerId/source/confirmed/createdAt/updatedAt`) are **never** in the tables — they're implicit | The emitter must **inject** them by convention with exact defaults (FR-PE-2). |
| Relationships are decorative prose | The grammar already yields join models + parent FKs; the live schema renders them as FK fields + `@relation(... onDelete: Cascade)` + **reverse-relation list fields** + `@@unique` | These are **convention-derivable** from `EntityGraph` (FR-PE-3) — no grammar change needed for the relationship layer. |
| The doc can express the whole live contract | **It cannot.** The live `schema.prisma` carries attributes the §2.1 grammar has **no syntax for**: field **defaults** (`matchScore Int @default(0)`), explicit **`@@index`** (`TailoredMatch`, `TailoredAsset`), compound **`@@unique` on non-join entities** (`TailoredMatch`), and **required reference ids with no FK** (the polymorphic `subjectType`/`subjectId` "loose reference" pattern) | **Two grammar gaps** must be closed (FR-PE-5) or the emitted schema is not behavior-equivalent. This is the central new work. |
| The requirements doc is a complete entity source | **It is lossy.** `REQUIREMENTS_v0.5-draft.md` itself flags it: JobDescription omits its required `rawText` + 4 AI-extracted fields; TailoredAsset omits `variant/tone/body/metadataJson` | **App-side prerequisite** (FR-PE-7 dependency): the doc must be completed before its emission can reach parity. The emitter's diff **drives** that completion. |
| `diff_against_live()` is a sufficient parity oracle | It only checks **model/field presence** — not types, optionality, attributes, defaults, or block attributes | The diff must be **upgraded to a semantic parity check** (FR-PE-4) to be trustworthy as the flip gate. |
| "Just emit the 2 new entities" | The strtd8 "Full derivation" goal requires the emitter to reproduce **all** current entities faithfully before `schema.prisma` can be flipped to derived | Acceptance is **whole-schema parity** against the live 16-entity contract (FR-PE-6), not new-entity-only. |

**Resolved open questions (from the investigation):**
- **Input AST → confirmed present.** `EntityGraph` carries everything the emitter consumes; no
  upstream parsing work.
- **Reference pattern → confirmed.** `scaffold_codegen/renderers.py` text rendering (named in P7).
- **Parity oracle → identified.** `prisma_parser.parse_prisma_schema()` for round-trip + an
  upgraded `diff_against_live()` for semantic equivalence.

**Still open:** see §4 (OQ-PE-1…4) — grammar-syntax choices for defaults/indexes, reserved-name
policy, and the flip-cutover mechanics.

---

## 1. Problem Statement

The SDK already derives six manifests deterministically from an authoring-contract requirements
document (FR-WPI; verified live on the real strtd8 doc — `pages/app/views/completeness/ai_passes/
human_inputs` all round-trip clean). The data contract `schema.prisma` is the **lone exception**:
it is hand-authored, and the doc's entity tables are only **diffed** against it (FR-WPI-8 DIFF
mode), never emitted (DRAFT mode — deferred to P7, "no Prisma writer exists anywhere").

| Build input | Source today | Target |
|-------------|--------------|--------|
| `app.yaml`, `pages.yaml`, `views.yaml`, `ai_passes.yaml`, `completeness.yaml`, `human_inputs.yaml` | **Derived** from the requirements doc (FR-WPI) | unchanged |
| `schema.prisma` | **Hand-authored**; doc entity tables only DIFF against it | **Derived** from the requirements doc's `### Entity` tables (this capability) |

**The unmet need:** a deterministic `EntityGraph → schema.prisma` emitter, gated by round-trip and
whole-schema semantic parity, so the requirements document becomes the **single source for the
entire contract** and entity changes (e.g. the strtd8 content-import entities `ImportedDocument` /
`ContentSnippet`) land by editing prose, not Prisma.

This is deterministic ($0-LLM) by construction — it renders an already-parsed AST. It is squarely
**SDK-owned assembly logic** (the app owns its requirements doc + manifests; the SDK owns all
deterministic assembly).

## 2. Functional Requirements

> One behavior per requirement. `Realizes:` ties back to FR-WPI. `Verify:` is the asserting test.

- **FR-PE-1 — Emit `schema.prisma` from the `EntityGraph`.** A deterministic writer renders the
  `EntityGraph` produced by `extract_entities()` into valid Prisma schema text: the
  `datasource`/`generator` header, one `model` block per `DocEntity`, one per `JoinModel`, in a
  stable canonical order. Realizes: FR-WPI-8 DRAFT mode (the P7 emitter). Verify: rendering a
  fixture `EntityGraph` produces text that `parse_prisma_schema()` accepts and that contains
  exactly the expected models.

- **FR-PE-2 — Inject the bookkeeping convention.** Every emitted entity model (not join models —
  see FR-PE-3) carries the six implicit fields with exact defaults, never sourced from the doc
  tables: `id String @id @default(cuid())`, `ownerId String @default("local")`,
  `source String @default("user")`, `confirmed Boolean @default(true)`,
  `createdAt DateTime @default(now())`, `updatedAt DateTime @updatedAt`. Verify: a single-field
  doc entity emits a model whose parsed field set is `{that field} ∪ {the six}` with matching
  attributes.

- **FR-PE-3 — Render relationships by convention.** From `EntityGraph.joins` and
  `EntityGraph.fk_parents`, emit: (a) for each `JoinModel`, a model with `fk_left`/`fk_right`
  `String` fields, two `@relation(fields: […], references: [id], onDelete: Cascade)` object
  fields, and `@@unique([fk_left, fk_right])`; (b) on each parent entity, the **reverse-relation
  list field** (e.g. `capabilities ProofPointCapability[]`); (c) for `fk_parents` (has-many /
  belongs-to), the child's `<parent>Id String` FK + its `@relation`. Verify: the
  ProofPoint↔Capability↔Outcome fixture emits exactly three join models with the live schema's FK
  names, cascade behavior, and reverse-relation fields, all parse-equal.

- **FR-PE-4 — Upgrade `diff_against_live()` to semantic parity.** The drift checker must compare
  not just model/field **presence** but, per field: base type, `is_optional`, `is_list`, and the
  normalized attribute set (`@id`, `@unique`, `@default(…)`, `@relation(…)`); and per model: the
  block attributes (`@@unique`, `@@id`, `@@index`). It reports every divergence with a stable
  identity key (FR-WPI-3 form). Verify: a field whose live type is `Int` but doc-derived `String`,
  a missing `@@index`, and a differing `@default` each produce exactly one drift line; an identical
  pair produces none.

- **FR-PE-5 — Close the two grammar gaps (or flag, never silently drop).** The §2.1 entity-table
  grammar must gain syntax — and the emitter support — for the attributes the live contract uses
  that the grammar cannot currently express:
  1. **Field defaults** (e.g. `matchScore` → `Int @default(0)`).
  2. **Explicit indexes** `@@index([…])` and **compound `@@unique([…])` on non-join entities**
     (e.g. `TailoredMatch`).
  3. **Required reference ids with no FK** — the polymorphic "loose reference" pattern
     (`subjectType`/`subjectId`, and the strtd8 `sourceDocumentId` content-import field): a
     required-or-optional scalar `text` id that is deliberately **not** a relation.
  Any live-schema construct still inexpressible after this MUST surface as
  `not_extracted(generator-gap)` in the extraction report (the FR-WPI-4 precedent for the
  completeness/`app.yaml` drift classes) — **never** emitted wrong and never silently dropped.
  Verify: a doc fixture exercising each of the three constructs round-trips to the live form; an
  intentionally-inexpressible construct appears as a single `not_extracted` report row with a
  reason.

- **FR-PE-6 — Round-trip-before-write + whole-schema parity gate.** Before any emission is
  written, it MUST round-trip through `parse_prisma_schema()` (FR-WPI-4 invariant extended to the
  contract). For the strtd8 cutover, the emitter run over the **completed** reference doc MUST
  reach **zero semantic-parity drift** (FR-PE-4) against the live 16-entity `schema.prisma`. Verify:
  the parity run on the reference doc reports an empty drift set; a deliberately-mutated doc
  (drop a field) reports exactly that drift.

- **FR-PE-7 — Run-dir emission + promotion ratchet (no project-tree writes mid-run).** The emitted
  `schema.prisma` draft lands in the run directory, Architect-validated, and reaches the project
  tree only by the explicit human-triggered **promotion** step (FR-WPI-5 / FR-WPI-8: "human
  leverage moves from writes-Prisma to validates-Prisma-against-their-own-prose"). No pipeline
  stage writes the promoted contract path; the VALIDATE hash check stands. Verify: a run writes
  only under the run dir; promotion is a separate, logged copy; re-running without promotion never
  mutates the project `schema.prisma`.

- **FR-PE-13 — Custom reverse-relation names (`as <name>`).** A relationship sentence may name the
  parent's reverse-list field with a trailing `as <name>` clause — e.g.
  `JobDescription has many JobStatusEntry as statusHistory` (or the child's-perspective
  `JobStatusEntry belongs to JobDescription as statusHistory`). The emitter uses that name for the
  reverse list; absent the clause it falls back to the plural-of-child convention (`_plural`). This
  lets a contract whose hand-authored reverse name diverges from the convention (e.g. `statusHistory`
  vs the convention's `jobStatusEntries`, referenced by owned `fsm.py`) stay **fully derived without
  renaming the live field** — the gap #4 resolution from `SDK_EMITTER_GRAMMAR_GAPS_2026-06-09`.
  Extends: FR-PE-3. Verify: `has many X as Y` emits the parent's reverse list named `Y` typed `X[]`;
  the same sentence without `as` emits the plural convention name.

> **Implementation note (gaps #1–#3, `SDK_EMITTER_GRAMMAR_GAPS_2026-06-09`):** the FR-PE-5(b/c)
> constructs (`@@index`, compound `@@unique`, loose-ref scalars) were *emitted* correctly but never
> reached the emitter through the CLI path: `extract.py::_build_graph` merged only
> `entities`/`joins`/`fk_parents` from each doc's sub-graph and silently dropped `indexes`/`uniques`/
> `loose_refs` (only the unit tests, calling `extract_entities` directly, exercised them). The old
> `diff_against_live` compared presence only, so the drop was invisible until `generate contract
> --check` (semantic parity) existed. Fixed by merging all per-entity graph fields in `_build_graph`;
> regression-tested through `build_entity_graph` (the real CLI path).

## 3. Non-Requirements

- **No LLM in the emitter.** It renders a parsed AST deterministically; any value not present in
  the doc/grammar is flagged, never inferred.
- **Not a general Prisma feature surface.** Only the constructs the strtd8 contract actually uses
  are in scope (the entity/bookkeeping/relationship conventions + the three FR-PE-5 constructs).
  Exotic Prisma features (native DB types, multi-field `@id`, `@@map`, views) are out until a
  consumer needs them — flagged as `generator-gap` if encountered.
- **No automatic flip.** Making strtd8's `schema.prisma` derived is a human-gated cutover
  (FR-PE-7), not a side effect of this capability shipping.
- **The app team owns doc completeness.** This capability does not author the missing entity
  fields (FR-PE-7 dependency, §5) — it surfaces them via the diff; the app team edits the prose.
- **No change to downstream generators.** `generate backend/views` continue to consume
  `schema.prisma` unchanged; this capability only changes how that file comes to exist.

## 4. Open Questions

- **OQ-PE-1 — Default-value syntax in the entity table.** How should a field default be written in
  the `Type` column (or `Notes`)? Candidates: a `Notes` convention (`default: 0`), a type-column
  suffix, or a dedicated column. Must stay parser-clean and human-legible (the authoring-contract
  audience is non-technical).
- **OQ-PE-2 — Index/compound-unique syntax.** Where do `@@index` / compound `@@unique` live in the
  grammar? Likely a per-entity "Indexes:" line analogous to the "Relationships:" paragraph. Needs a
  closed, parseable form.
- **OQ-PE-3 — Loose-reference declaration.** How does the table mark a `text` field as a
  deliberate non-FK reference id (vs. a relation)? Proposal: it's just a `text` field by type, and
  the *relationship grammar's absence* is the signal — but `subjectType`/`subjectId` pairs and
  `sourceDocumentId` may warrant an explicit note so the diff doesn't treat them as missing
  relations.
- **OQ-PE-4 — Flip cutover mechanics for an existing contract.** Once parity holds, what exactly
  marks `schema.prisma` as "now derived"? A provenance header comment? An entry in the app's
  `VALIDATION_AND_MANIFEST_DERIVATION.md` ledger? A `_superseded-handauthored-*/` archive of the
  old file (the precedent the app already uses for the six YAML manifests)?

## 5. Dependencies & sequencing

- **App-side prerequisite (blocks FR-PE-6 parity, not the build):** the strtd8 reference
  requirements doc must be **completed** to be a faithful source — restore the fields it currently
  omits (JobDescription `rawText` + the 4 AI-extracted fields; TailoredAsset
  `variant/tone/body/metadataJson`) and express the FR-PE-5 constructs once their grammar lands.
  The emitter's own diff output is the worklist for this; it is app-team work, tracked in
  `VALIDATION_AND_MANIFEST_DERIVATION.md`.
- **First real consumer:** the content-import entities `ImportedDocument` / `ContentSnippet` +
  `ProofPoint.sourceDocumentId` (strtd8 `CONTENT_IMPORT_REQUIREMENTS_v0.2-draft.md` §5). Once this
  capability ships, those land by editing the requirements doc and re-running extraction — the
  motivating end-to-end test of "edit prose → derive contract → generate → migrate."
- **Sequence:** FR-PE-1/2/3 (emitter core) → FR-PE-4 (diff upgrade, the oracle) → FR-PE-5 (grammar
  gaps, the new work) → FR-PE-6 (parity gate) → app completes the doc → FR-PE-7 promotion + the
  strtd8 flip.

## 6. Acceptance

1. Golden-fixture unit tests per emission concern (bookkeeping injection, scalars, joins,
   fk_parents, each FR-PE-5 construct), byte-stable; malformed/inexpressible input →
   `not_extracted` + reason, never a guess (the FR-WPI test-plan discipline).
2. Round-trip: every emitted `schema.prisma` parses through `parse_prisma_schema()` (FR-PE-6).
3. **Parity milestone:** the emitter over the *completed* strtd8 reference doc produces a
   `schema.prisma` with **zero** semantic-parity drift (FR-PE-4) against the live 16-entity
   contract — the precondition for the flip.
4. End-to-end: adding `ImportedDocument`/`ContentSnippet` to the requirements doc and re-running
   extraction emits a parity-clean schema that `generate backend` consumes to produce the new
   entities' full CRUD/UI/export stack — zero `schema.prisma` hand-editing.

---

*Draft 0.1 — requirements only, no implementation. Realizes the deferred DRAFT half of FR-WPI-8
(the P7 Prisma emitter) and extends it from "greenfield drafting" to "make an existing contract
derived," per the strtd8 app team's minimize-hand-editing goal. §0 folds in a code-investigation
planning pass; OQ-PE-1…4 (grammar syntax + flip mechanics) remain for the SDK team to settle before
build.*
