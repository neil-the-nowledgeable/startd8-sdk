# Generated Import Path & Import Templates — Requirements

**Version:** 0.3 (Refresh — un-deferred 2026-06-15; consolidation-aware)
**Date:** 2026-06-07 (v0.2) · 2026-06-15 (v0.3 refresh)
**Status:** ▶ **ACTIVE — scheduled for build.** FR-IMP-4/5 + the source-scope member of FR-IMP-2
already SHIPPED (source-bound extraction, on `origin/main`). The remaining generalization (FR-IMP-1
`from_json` owned-kind, FR-IMP-2 **identity-key consolidation**, FR-IMP-3 `imports.yaml` grammar,
FR-IMP-6 import surface) is un-deferred — real consumer need confirmed (2026-06-15) and the
rule-of-three cost concern collapsed (the FR-PE Prisma emitter paved the grammar→manifest→generate→
gate→promote road). Plan: `GENERATED_IMPORT_PATH_PLAN.md`. See §0b for the refresh insights.
**Format:** SDK-internal requirements (REQ/FR), grounded against shipped `backend_codegen/`
**Companion:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (the path this extends),
`../kickoff/KICKOFF_AUTHORING_CONTRACT.md` (the manifest grammar an import template joins),
`docs/design/IDEAL_TARGET_ARCHITECTURE.md` (canonical target arch)
**First consumer:** strtd8 `docs/kickoff/CONTENT_IMPORT_REQUIREMENTS_v0.2-draft.md` (FR-13/14/15)

> **Objective.** Give the SDK a **generated IMPORT path symmetric to the shipped EXPORT path**
> (`backend_codegen/derived.render_export`), so that **applications built by the framework can
> leverage the deterministic generation framework directly** to build entity-import utilities —
> not hand-author them. Import behavior is **declared, not coded**: an `imports.yaml` manifest
> authored in the **same authoring-contract grammar** that already drives `pages.yaml` /
> `views.yaml` / `ai_passes.yaml` / `human_inputs.yaml`, extracted and round-trip-validated by the
> same `manifest_extraction` machinery, and projected into a generated owned-kind for $0. The one
> in-scope LLM touch (extraction from imported text) **reuses the existing AI-pass harness**, now
> made source-bindable. This sits in **bucket 1 (application) + bucket 3 (integration)** of the
> CLAUDE.md scope separation — it builds the utility that *holds/produces* content, never the real
> content itself.

> **Scope discipline (CLAUDE.md).** Deterministic-first. The **storage + round-trip + library +
> idempotency** half is $0-LLM owned capability (FR-IMP-1/2/3/6) and lands first. The **one**
> non-deterministic item — source-bound extraction (FR-IMP-4/5) — reuses an existing pass and is
> built second. No new content-authoring scope is introduced.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the shipped generators (`backend_codegen/derived.py`,
> `backend_codegen/ai_layer.py`, `manifest_extraction/{grammar,extractors,extract}.py`) and the
> first consumer's draft (strtd8 CONTENT_IMPORT v0.2) to stress-test the naive "just add an import
> generator mirroring export" framing. Five corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Add an import generator symmetric to export" is the whole job. | Export is `render_export` → `to_json` (lossless, sorted) + `to_markdown` only (`derived.py:38–71`); there is no `from_json`. But the *easy* half is the de-serializer. The hard half is the **write policy** (identity/dedup + provenance), which lives in a **different module** — `_persist` (`ai_layer.py:384–404`), hardwired to AI output. | **Split the work.** FR-IMP-1 (round-trip de-serializer, next to export, easy) is decoupled from FR-IMP-2/4/5 (write-policy generalization in the persist/AI layer — the real work). Symmetry with export is necessary but not sufficient. |
| Provenance just needs the field marked human/server-managed in `human_inputs.yaml`. | Omission keeps the AI from *authoring* it, but **nothing STAMPS it**. `_persist` strips every server-managed field (`{"id","ownerId","source","confirmed","createdAt","updatedAt"}`, `ai_layer.py:390`) and never sets a source id. A bare omitted provenance field lands **null**, not provenance-bearing. | **FR-IMP-5 added.** Omission and deterministic *stamping* are **two** requirements, not one. The strtd8 finding ("`_persist` never stamps non-edge fields") is structural, not a config gap. |
| Source-scoped dedup is a one-line `_persist` tweak. | `_persist` dedups **by `name` only** (`ai_layer.py:392–395`) and the text-mode harness signature is `def <pass>(<request_field>: str, session: Session)` (`ai_layer.py:452`) — **no source parameter exists to scope by.** Dedup AND the harness signature must both change, together. | **FR-IMP-2 + FR-IMP-4 are coupled.** Neither alone delivers FR-14-class "idempotent by source"; the value to dedup on doesn't reach the harness today. |
| Import templates are a new bespoke config format. | The SDK already extracts **6 manifests** from controlled grammar with mandatory round-trip validation against each generator's own parser (`manifest_extraction/extract.py:105–132`, fail-loud `RoundTripError`). An import template is just a **7th manifest in the same idiom** — one extractor + one parser + the existing round-trip gate. | **FR-IMP-3 reuses `manifest_extraction` wholesale.** "Import template" = a new authoring-contract §-section (`## Imports`) + `imports.yaml`, **not** a new config subsystem. Zero new parsing machinery. |
| The generated app needs a foreign-format parser. | strtd8 OQ-2 (closed from code): **no** pdf/docx/text-extraction dependency exists or is importable. v1 source formats are **JSON round-trip** + **text (paste / `.txt` / `.md`)** only. | **Format vocabulary bounded** to `{json, text}` for v1. Binary formats (PDF/DOCX) and OCR are deferred to a named future increment **with their dependency cost called out** — never silently assumed. |

**Resolved / updated open questions:**
- **OQ-IMP-A → resolved.** The import owned-kind lives in a **new `import_codegen.py`** module
  (symmetric to `ai_layer.py`), not bolted onto `derived.py` — the write-policy half pulls in the
  persist/edge machinery and would overload the "three small pure emitters" docstring of `derived`.
- **OQ-IMP-B → resolved.** `imports.yaml` is a **standalone manifest** that *cross-references*
  `human_inputs.yaml` (the stamped field) and `ai_passes.yaml` (the bound extractor) by
  entity/field name — it does not absorb them. One concern per manifest (the §5 vocabulary rule).
- **OQ-IMP-C → still open (correctly deferred):** whether `from_json` import should *replace* an
  app's bespoke FR-10-style restore or *complement* it. No SDK code bearing; consumer choice.

## 0b. Refresh Planning Insights (v0.3 — 2026-06-15, the un-deferral pass)

> Between v0.2 (deferred north-star) and v0.3, the world moved: the FR-PE Prisma emitter shipped a
> full grammar→generate→gate→promote loop, a second dedup mechanism (`dedup_by`/F-11) landed next to
> `source_binding`, and real consumer need was confirmed. Six refresh corrections:

| v0.2 Assumption | v0.3 Discovery (current `origin/main`) | Impact |
|-----------------|----------------------------------------|--------|
| FR-IMP-2 is greenfield — replace `_persist`'s name-dedup with one declared key. | **Two** dedup keys now coexist on `AiPass` (`ai_layer.py`): `source_binding` (source-scope, mine) **and** `dedup_by` (single-field, the parallel team's F-11), plus an unrelated `trigger`. | **FR-IMP-2 is a CONSOLIDATION/refactor, not greenfield** — unify both under one declared identity key, **back-compat preserved**, and **coordinate with the AI-layer owner** (the highest-collision surface). |
| FR-IMP-3 (the grammar) is the risky, expensive part. | The Prisma emitter shipped the entire **authoring-contract §-section → `extract_*` extractor → `parse_*` round-trip gate → generate owned-kind → FR-PE-6/7 gate+promote** pattern, plus a generalized `build_entity_graph` and the fail-loud gate discipline (errors/unrenderable/round-trip oracle, `--allow-lossy`). | **FR-IMP-3 cost collapsed — it's a paved road.** `imports.yaml` is a 7th manifest cloning `extract_views`/`parse_views`; the keystone is now the *cheapest* phase, not the riskiest. |
| `from_json` is the easy de-serializer; just write it. | The emitter proved a **safety-gate discipline** is essential for a write path: a round-trip import that drops rows or violates the declared identity should **fail loud**, not silently. | **FR-IMP-1 gains a gate** (idempotency + completeness oracle) mirroring FR-PE-6; symmetric to export is necessary but a *gated* importer is the bar. |
| The identity key is an AI-pass concern (`_persist`). | `from_json` restore (FR-IMP-1) writes **user** rows; the AI pass writes **ai** rows — both need the **same** declared identity key, at **two** call sites. | **FR-IMP-2's identity key is the shared seam** between the AI `_persist*` path and the new `from_json` path — define it once, consume it in both (under-specified in v0.2). |
| Rule-of-three: hold for a 2nd consumer. | Real need confirmed 2026-06-15 (consumer to be named — strtd8 content-import FR-13/15, navig8, or startd8-generator). | **Un-deferred.** Consumer identity is now the load-bearing open question (it fixes formats/entities) → **OQ-IMP-D**. |
| Build it on a branch like any feature. | The repo runs many concurrent worktrees + a parallel team **actively in `ai_layer.py`/`generate contract`** (see memory `reference_multiworktree_env`). | **Coordination is a first-class plan step.** `git fetch` + check `origin/main` before each phase; the FR-IMP-2 phase opens with a heads-up to the AI-layer owner, not a surprise PR. |

**Refresh open-question updates:**
- **OQ-IMP-A → revised.** Module split stands (`import_codegen.py`), but the **identity-key logic** is
  shared with `ai_layer.py` — extract it to a small `identity.py` (or `ai_layer` helper) consumed by
  both, so there is one source of truth (resolves the FR-IMP-2 two-call-site seam).
- **OQ-IMP-D → NEW (load-bearing):** **name the first un-deferred consumer.** strtd8 content-import
  (FR-13/15) drives `{json, text}` + a snippet library; navig8/the generator may need different
  formats/entities. The grammar (FR-IMP-3) is consumer-agnostic, but the *acceptance* (FR-IMP-6
  surface, FR-IMP-1 round-trip target) needs a named consumer. Resolve before Phase 3.

---

## 1. Problem Statement

The deterministic framework projects one `.prisma` contract into ~12 owned kinds, **including a
generated EXPORT** (`derived.render_export` → `app/export.py`: `to_json` round-trip + `to_markdown`).
**It generates no IMPORT.** An application built by the framework that wants to *bring data back in*
— restore its own export, ingest a foreign document as a durable record, or extract structured rows
from imported text — must **hand-author every line of that glue**, outside the deterministic /
drift-tracked / $0 model. The framework can *produce* an entity's data but cannot *take it back*.

Three concrete shipped gaps block the first consumer (strtd8 content-import) and any other:

| Capability | Current State | Gap this doc addresses |
|------------|---------------|------------------------|
| Round-trip restore of the app's own export | `to_json` writes it; **no `from_json` reads it** | **FR-IMP-1** — generated inverse de-serializer |
| Idempotent re-ingest (no duplicate explosion) | `_persist` dedups **by `name` only** (`ai_layer.py:392`); entities without a `name` column never dedup → re-ingest **appends duplicates** | **FR-IMP-2** — declarable identity/idempotency key |
| Declaring *how* an entity is imported | No surface for it; import is whatever an app hand-writes | **FR-IMP-3** — `imports.yaml`, authored in the manifest grammar |
| Extract from a *stored* record with provenance | Text harness is `def <pass>(text, session)` — **no source binding** (`ai_layer.py:452`); can't scope or stamp | **FR-IMP-4** — source-bound AI pass |
| Provenance fields that survive | `_persist` strips all server-managed fields and **never stamps** a source id; edge-schema would otherwise **hand the field to the AI to hallucinate** | **FR-IMP-5** — server-stamped, never-AI-filled provenance |
| An import affordance (paste / upload) in the UI | Only generic CRUD create exists; no paste/text-file intake | **FR-IMP-6** — generated import surface (optional, declared) |

**The core unmet need (project-agnostic):** *let the application reach into its own deterministic
contract to import entities — restore, ingest, and (where declared) extract — with declared
identity and declared provenance, generated for $0 from the same contract the entity was defined by.*

---

## 2. Requirements

> FR-IMP-1…6. Behaviors only; the `imports.yaml` shape is in §5. Each has a `Verify:` line a test
> can assert, per the house format. The deterministic split (CLAUDE.md): **FR-IMP-1/2/3/6 are $0
> owned generation; FR-IMP-4/5 reuse one existing AI pass.**

- **FR-IMP-1 — Generated round-trip import (the inverse of export).** The SDK emits a deterministic
  owned-kind (`app/import.py`, kind `python-import`, drift-tracked, $0) projected from the contract:
  a `from_json(text) -> payload` / loader that ingests the app's own `to_json` export format into
  entity rows, the structural inverse of `render_export`. It honours the entity's declared identity
  key (FR-IMP-2). Touches: `import_codegen.render_import`, `app/import.py`. **It is GATED** (v0.3,
  mirroring the FR-PE-6 emitter discipline): the importer reports a structured result and **fails
  loud** rather than silently — a row that violates the declared identity, a field the contract can't
  accept, or a count that doesn't reconcile is surfaced (not dropped); a `--strict`/`--allow-lossy`
  switch governs partial imports. Verify: for any contract, `from_json(to_json(payload))` reconstructs
  every entity row with field fidelity (sorted-key stable); re-running the load is idempotent under
  the declared identity key (no duplicate rows); a row referencing an undeclared field is reported,
  not silently dropped; the emitted file carries the standard provenance header and passes `--check`
  drift.

- **FR-IMP-2 — Unify the dedup mechanisms into ONE declared identity key (CONSOLIDATION).** *(v0.3:
  no longer greenfield.)* `AiPass` carries **two** overlapping dedup keys today — `source_binding`
  (source-scope) and `dedup_by` (single field, F-11). Consolidate them into **one** declared identity
  key with the full vocabulary: `id` (upsert / restore), a single named field, a composite of named
  fields, a **source scope** (an FR-IMP-5 provenance field), or `none` (append-only). The key is the
  **shared seam** between the AI persist path *and* the FR-IMP-1 `from_json` path — defined once
  (a small `identity` helper), consumed at both call sites. **Back-compat is mandatory:** existing
  `source_binding`/`dedup_by` manifests keep working (mapped onto the unified key), and an entity
  with no declaration still dedups by `name` exactly as before. Touches: `ai_layer` (the persist
  helpers + `AiPass`), `import_codegen`, `imports.yaml`. **Coordination (the highest-collision
  surface):** this lands via a proposal to the AI-layer owner, not a surprise branch (see §0b).
  Verify: `source_binding`/`dedup_by` manifests emit byte-identical generated code post-unification;
  `identity: id` upserts on re-import; `identity: [a, b]` composites; `identity: source:<field>`
  replaces only that source's unconfirmed rows; `identity: none` appends; no-declaration still
  name-dedups.

- **FR-IMP-3 — Import templates declared in the authoring-contract grammar → `imports.yaml`.** A new
  authoring-contract section (`## Imports`, §5) and a `manifest_extraction` extractor emit
  `imports.yaml`, **round-trip-validated against its own `parse_imports` parser** like every other
  manifest (`extract.py:105–132`), with per-value extraction-report rows (`extracted(source:…)` /
  `not_extracted(reason)` / `defaulted(source)`). An import template binds: target entity, source
  format, identity key (FR-IMP-2), provenance source value, and an optional source/extractor binding
  (FR-IMP-4). **(v0.3 — paved road):** this clones the exact pattern the FR-PE Prisma emitter shipped
  — a `## Imports` extractor modeled on `extract_views` (`extractors.py`), a `parse_imports` strict
  parser, and wiring into the `extract_manifests` round-trip gate (`extract.py`) — so it is the
  **cheapest, lowest-risk phase**, not the riskiest. Touches: `KICKOFF_AUTHORING_CONTRACT §2.8`,
  `manifest_extraction/extractors.py` + `extract.py`, `import_codegen.parse_imports`. Verify: a
  conforming `## Imports` block extracts to an `imports.yaml` that round-trips through `parse_imports`;
  an unknown target entity / field reference fails **loudly** (never a silent flag); a non-conforming
  row emits exactly one `not_extracted(reason)` report row.

- **FR-IMP-4 — Source-bound AI pass (context binding) — generalize the text-mode harness.** Extend
  `ai_passes.yaml` + the text-mode harness (`ai_layer._render_pass_text`) so a pass may be **bound
  to a source record**: emit `def <pass>(text, session, source_id=…)` when a binding is declared
  (the current `def <pass>(text, session)` remains the unbound case). The bound harness stamps the
  declared provenance field (FR-IMP-5) and scopes dedup to that source (FR-IMP-2 `source` identity).
  Touches: `ai_layer._render_pass_text`, `ai_passes.yaml` (binding field), `imports.yaml`. Verify:
  a source-bound pass writes ≥1 row whose declared provenance field equals the passed `source_id`
  and `source="ai", confirmed=false`; re-running with the same `source_id` leaves the count of that
  source's **unconfirmed** rows stable and never modifies a **confirmed** row; an unbound pass
  generates byte-identical code to today.

- **FR-IMP-5 — Server-stamped provenance fields (never AI-filled).** A field declared as a
  provenance/source-binding target is (a) **omitted** from the AI edge schema — already supported
  via `human_inputs.yaml` omission (`ai_layer.render_edge_schemas`) — **and** (b) **deterministically
  stamped** by the harness from the binding context, closing the gap that omission alone leaves the
  field null. Provenance fields are server-managed; the AI can neither author nor see them. Touches:
  `ai_layer._persist` (stamp step), `human_inputs.yaml` (omission), `imports.yaml` (binding). Verify:
  the target entity's edge schema omits the provenance field (existing `test_edge_privacy`
  assertion); after a source-bound pass the field is **non-null** and equals the source id; a
  generated test asserts the field is absent from the edge model AND present-and-stamped on the row.

- **FR-IMP-6 — Generated import surface (optional, declared).** When an import template declares a
  surface, the generator emits an import route/screen (paste textarea + file upload for text
  formats) that creates the target entity record(s), reusing the HTMX generator idiom; storage is
  **independent of any extraction step** (importing stores; extracting is a separate user action).
  Touches: `import_codegen`, `htmx_generator`, `imports.yaml` (surface flag). Verify: posting pasted
  text to the generated import route creates one target row whose stored text round-trips
  byte-for-byte and whose label/kind render back unchanged; nothing is extracted by the act of
  importing.

## 3. Non-Requirements (explicit scope fence)

- **Not a generic ETL / CSV column-mapping engine.** v1 source formats are **JSON round-trip** and
  **text (paste / `.txt` / `.md`)** only. CSV / arbitrary-schema mapping is a future format entry,
  not v1.
- **No binary parsing.** No PDF / DOCX / OCR / scanned images — no such dependency exists in the
  target runtime (strtd8 OQ-2). Deferred to a named increment **with its dependency cost stated**.
- **Does not change export.** `render_export` / `to_json` / `to_markdown` stay exactly as-is; import
  is the inverse, added alongside.
- **No content-quality grading or fuzzy/similarity dedup.** Identity keys are **exact-match** only;
  the framework stores and surfaces, the user judges.
- **No auto-confirm of AI-authored rows.** Source-bound extraction output stays `source="ai",
  confirmed=false`; the import path never silently writes to the confirmed value model.
- **Not a foreign-key resolver beyond the declared identity key.** Loose `text` references with no FK
  (the consumer's `subjectId` pattern) are honoured; cross-entity reference *resolution* is out.
- **No new content-authoring scope (bucket 4).** This builds the import *utility*; the imported
  content is the user's / company's, never SDK-generated.

## 4. Open Questions

- **OQ-IMP-1 — Composite identity-key normalization.** For `identity: [a, b]`, are values
  case-normalized / trimmed before comparison, or compared verbatim? (Lean: verbatim in v1; document
  it; a normalization policy is a later refinement.)
- **OQ-IMP-2 — Binding cardinality.** Is FR-IMP-4 source-binding a single `source_id` → single
  declared provenance field, or a general `{context-key → stamped-field}` map? (Lean: single in v1;
  covers the consumer; generalize only on a second consumer's need.)
- **OQ-IMP-3 — `from_json` vs app-level restore (= OQ-IMP-C).** Should the generated `from_json`
  *replace* a project's bespoke FR-10-style round-trip restore, or *complement* it? No SDK code
  bearing; consumer choice. **Open.**
- **OQ-IMP-4 — Surface kind vocabulary.** Does FR-IMP-6's surface reuse a `views.yaml` archetype
  (closed vocabulary) or get its own minimal `import-form` kind? (Lean: minimal own kind — the
  archetype set is deliberately closed; an import form is a distinct shape.)
- **OQ-IMP-5 — Identity `source` scope without a provenance field.** Can an entity declare
  `identity: source` without also declaring an FR-IMP-5 provenance field? (Lean: **no** — fail
  loudly at extraction; `source` identity *requires* the field it scopes by.)

## 5. The `imports.yaml` manifest *(planning-confirmed shape)*

> A 7th manifest, authored as a new authoring-contract section and extracted like the other six.
> It **cross-references** `human_inputs.yaml` (the stamped field) and `ai_passes.yaml` (the bound
> extractor) by name — it does not absorb them (§ vocabulary-ownership rule). Round-trip-validated
> against `parse_imports`; any non-round-tripping emission is a bug, never a flag.

### Authoring grammar — `## Imports` *(new authoring-contract §2.8)*

A table, one row per import template, in the controlled idiom of the sibling sections:

```markdown
## Imports
| Entity | Format | Identity | Provenance | Extract via |
|--------|--------|----------|------------|-------------|
| ImportedDocument | text   | id            |               |              |
| ContentSnippet   | text   | id            | sourceDocumentId |           |
| ProofPoint       | text   | source: sourceDocumentId | sourceDocumentId | extract |
```

- **Entity** — must match a declared contract model (else `not_extracted(unknown-entity)` → loud).
- **Format** — `json` (round-trip) | `text` (paste / `.txt` / `.md`). Closed vocabulary; binary
  flagged `not_extracted(generator-gap: format-deferred)`.
- **Identity** — `id` | `<field>` | `[<f1>, <f2>]` | `source: <field>` | `none`. Drives FR-IMP-2.
- **Provenance** — a field name to **server-stamp** with the source id (FR-IMP-5); must also appear
  in `## Owned fields` (cross-ref to `human_inputs.yaml` for AI-omission). Blank = none.
- **Extract via** — the `ai_passes.yaml` pass name to source-bind (FR-IMP-4). Blank = store only
  (FR-IMP-6), no extraction.

### Emitted `imports.yaml`

```yaml
imports:
  - entity: ImportedDocument
    format: text
    identity: id
    surface: true            # FR-IMP-6, when a surface is declared
  - entity: ProofPoint
    format: text
    identity: { source: sourceDocumentId }
    provenance: sourceDocumentId   # FR-IMP-5 server-stamp; AI-omitted via human_inputs
    extract_via: extract           # FR-IMP-4 source-bind the existing 'extract' pass
```

**Three accompanying manifest cross-edits (planning-confirmed, mirroring the consumer's §5):**
1. `human_inputs.yaml` — every `provenance:` field marked human/server-managed (AI edge omission).
2. `ai_passes.yaml` — the `extract_via` pass gains a source-binding marker (FR-IMP-4).
3. `completeness.yaml` — import-only / library entities the project excludes stay the project's call
   (the SDK does not auto-exclude; it surfaces the field for the author).

## 6. First consumer — StartDate (the requirements-to-SDK map)

> How strtd8 `CONTENT_IMPORT_REQUIREMENTS v0.2` FR-13/14/15 land on these project-agnostic
> capabilities. This is the "see how a project would like these to work" mapping.

| strtd8 need | SDK capability | Notes |
|-------------|----------------|-------|
| FR-13 — import a prior document as a durable record; paste + `.txt`/`.md` | **FR-IMP-6** (surface) + existing CRUD create | $0 cascade today *except* the paste/upload affordance, which FR-IMP-6 generates |
| FR-13 — round-trip stored raw text byte-for-byte | **FR-IMP-1** | round-trip fidelity is the same property as restore |
| FR-14 — extract ProofPoints from a stored doc, stamped with `sourceDocumentId` | **FR-IMP-4 + FR-IMP-5** | the exact "`extract(text, session, source_id=…)` + server-stamp" the consumer asked for |
| FR-14 — re-running is idempotent by source; never touches confirmed rows | **FR-IMP-2** (`identity: source: sourceDocumentId`) | replaces the false "dedup-by-name" path the consumer found broken |
| FR-14 — AI never authors `sourceDocumentId` | **FR-IMP-5** (omit + stamp) | closes the "AI-hallucinated id" gap |
| FR-15 — reusable snippet library (tagged, listed, copyable) | existing $0 CRUD/UI + **FR-IMP-1/6** | library is plain generated CRUD; import path lets snippets be saved *from* a document |

**The deterministic split this produces (CLAUDE.md-aligned):** FR-IMP-1/2/3/6 = **$0 owned
generation**, build first (delivers strtd8 FR-13 + FR-15 + the idempotency the consumer needs);
FR-IMP-4/5 = **one source-bound reuse of an existing AI pass**, build second (delivers strtd8 FR-14).
Exactly the consumer's own Stage-1/Stage-2 sequencing, generalized into SDK capability.

## 7. Implementation sequence *(v0.3 — see `GENERATED_IMPORT_PATH_PLAN.md` for the detailed plan)*

**Already shipped (`origin/main`):** FR-IMP-4 (source-bound pass) + FR-IMP-5 (server-stamp) + the
source-scope member of FR-IMP-2 — the source-bound-extraction work.

**Remaining, phased (foundational first):**
- **Phase 0 — Coordinate** (the AI-layer surface is hot): `git fetch`, confirm `origin/main`, post
  the FR-IMP-2 unification proposal to the AI-layer owner. Name the consumer (OQ-IMP-D).
- **Phase 1 — FR-IMP-2 identity-key consolidation** (foundational): unify `source_binding` + `dedup_by`
  into one declared key in a shared `identity` helper; back-compat byte-identical. Blocks FR-IMP-1.
- **Phase 2 — FR-IMP-3 `imports.yaml` grammar** (paved road, parallelizable with Phase 1): `## Imports`
  extractor + `parse_imports` + round-trip gate, cloning `extract_views`.
- **Phase 3 — FR-IMP-1 `from_json` owned-kind** (gated importer): consumes the Phase-1 key + Phase-2
  manifest; the FR-PE-6-style import gate.
- **Phase 4 — FR-IMP-6 import surface**: `htmx_generator` paste/upload screen when `imports.yaml`
  declares one.
- **Phase 5 — End-to-end** on the named consumer + drift `--check` + boot-smoke.

---

*v0.3 — Refresh / un-deferral (2026-06-15). Un-deferred on confirmed consumer need; the rule-of-three
cost concern collapsed because the FR-PE Prisma emitter paved the grammar→generate→gate→promote road
(FR-IMP-3 is now the cheapest phase). FR-IMP-2 reframed from greenfield to a **consolidation** of two
shipped dedup keys (`source_binding` + `dedup_by`) into one identity key shared by the AI-persist and
`from_json` paths — back-compat mandatory, coordinated with the AI-layer owner. FR-IMP-1 gained a
fail-loud import gate (FR-PE-6 model). New OQ-IMP-D (name the consumer). See §0b + the plan doc.*

---

## 8. Post-Review Amendments (CRP R1–R4 triaged 2026-06-15)

> Accepted suggestions from the convergent review (Appendix C R1–R4), folded into the requirements.
> Dispositions in Appendix A/B. These are **normative** amendments to §2's FRs.

**FR-IMP-1 (`from_json`) — import is not a string echo:**
- **Reuse the export contract, not an independent schema walk** (R2-F1): load entities in
  `ENTITY_ORDER` and validate fields against `FIELDS` from the generated `app/export.py`.
- **Type re-coercion** (R4-F2 — code-grounded): `to_json` serializes `default=str` (`derived.py:60`),
  so datetimes/Decimals/ints/FKs land as strings. `from_json` MUST coerce each field back to its
  declared schema type — fidelity is **type-faithful, not string-faithful** (a bare echo corrupts
  typed columns while passing a textual round-trip).
- **Confirmed-row non-clobber** (R1-F2): never overwrite/delete a `confirmed:true` row under the
  identity key — collision ⇒ `ImportResult` error (mirrors the AI path's confirmed-aware supersede).
- **Restore provenance stamping** (R3-F1): round-trip restore **preserves** `source`/`confirmed` from
  the payload; text/surface import defaults to `source="human", confirmed=false` — **never** the AI
  `source="ai"` default.
- **`identity: id` upsert** (R3-F2): explicit `id` + `identity: id` ⇒ upsert that PK; absent ⇒ insert.
- **FK load ordering** (R1-F3): multi-entity payloads load parent-before-child per schema FKs, or fail
  loud — not left to SQLAlchemy insert order.
- **Partial-import atomicity** (R4-F6): `--allow-lossy` uses a per-row/per-entity savepoint (reuse
  `session.begin_nested()`); `--strict` rolls the whole file back. The commit boundary is defined.
- **Text-path acceptance** (R2-F5): importing a pasted/stored *text* doc (not only a `to_json`
  payload) creates/updates the target row per identity (strtd8 FR-13 byte-for-byte).

**FR-IMP-2 (identity consolidation) — the seam is subtler than v0.3 stated:**
- **The back-compat map is THREE-valued, not two** (R4-F1 — code-grounded): `effective_source_binding`
  (`ai_layer.py:312-339`) resolves a binding *explicit* / *schema-derived (zero authored config)* /
  `none` (disable). A pass with **no** `source_binding` key can still be source-bound; mapping
  "neither key ⇒ `name`" silently breaks it. The derived case maps to `source:<derived-field>`, and
  the byte-identity gate MUST exercise it (declared-key manifests alone won't).
- **Source-scope idempotency is HARNESS-level, not persist-level** (R4-F3): it is a pre-insert
  *clear-prior-unconfirmed* step in the harness body (`_render_pass_text_bound`), separate from per-row
  `_persist`. The seam is two-layered — `resolve_identity()` (pure) + per-kind **apply** where
  `source` stays a harness pre-clear. One `_persist(..., identity)` signature **cannot** express it.
- **Five persist branches, not four** (R4-F4): `_PERSIST_SCOPED_HELPER` (FR-SRP, `is_scoped`,
  `fk_values: dict`) is a fifth; FR-IMP-2 must include it in scope or **explicitly fence** it.
- **Dual-key precedence** (R1-F1): a manifest setting both keys ⇒ defined outcome (lean: `source`
  wins, `dedup_by` ignored with an extraction warning; or fail-loud at parse) — never implementation-defined.
- **Composite comparison** (R2-F6 + R4-F7): verbatim (no trim/case-fold, v1) **and** on the **coerced
  typed value**, not the JSON string repr — shared by the import and AI paths.
- **Behavioral parity, not just byte-identity** (R3-S4): the regression gate also emits a behavioral
  test (confirmed-non-touch, unconfirmed supersede, source-scope count stability).

**FR-IMP-3 (`imports.yaml` grammar):**
- **Cross-ref validation, candidate-ordered** (R1-F4 + R4-F5): `parse_imports` validates `extract_via`
  → an `ai_passes.yaml` pass and `provenance` → a `human_inputs.yaml` owned field, sourcing the
  sibling names from the **already-extracted candidate manifests** (like `view_prose`'s `known_views`)
  — so `imports.yaml` round-trips **after** `ai_passes`/`human_inputs` in the gate. Unknown ⇒ loud.
- **OQ-IMP-5 normative** (R2-F2): `identity: source:<field>` **requires** a non-blank `Provenance` ⇒
  loud at extraction, not runtime.
- **Duplicate-entity policy** (R2-F4): multiple `## Imports` rows for one Entity ⇒ defined (fail-loud
  or ordered precedence) — never silent last-wins.
- **Surface column** (R1-F6): add `Surface` to the §5 authoring table (so `surface: true` is authorable).
- **Prune orphaned templates** (R3-S6): an Entity dropped from the schema prunes its `imports.yaml`
  row at re-extract (like `view_prose`).

**FR-IMP-6 (import surface):**
- **Upload safety** (R2-F3): UTF-8 only (reject binary), a documented max size (lean 1 MiB,
  configurable), `.txt`/`.md` extensions for file upload (paste unchanged).
- **CSRF** (R3-F3): inherits the generated form layer's CSRF/session posture — same as entity forms
  (no import-specific scheme beyond what those forms have).
- **Import ≠ extract** (R3-F5): a successful import POST **never** invokes `extract_via`; extraction is
  a separate user action (FR-IMP-4).
- **Discoverability + error display** (R2-S6 + R3-S5): `surface: true` adds an import link to the nav;
  a bad paste renders `ImportResult.errors` in the HTMX response, not a silent 302.

**§3 Non-Requirements (new fences):** import is **opt-in** — no `imports.yaml` ⇒ no `app/import.py`
emitted, no drift expected (R2-F7); generated `from_json` **complements** any bespoke restore (e.g.
strtd8 FR-10), never auto-replaces it (R3-F6, OQ-IMP-C).

**§4 Open Questions:** **OQ-IMP-D (NEW, load-bearing)** — name the first consumer before Phase 5;
provisional default **strtd8** (§6) with `{json, text}` + a pinned acceptance fixture. Unresolved by
the decision date blocks e2e acceptance only, not the P2 grammar (R1-F5).

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

> Triaged 2026-06-15 (claude-opus-4-8). All R1–R4 requirements suggestions ACCEPTED — well-anchored,
> code-grounded, no conflicts. Folded into **§8 Post-Review Amendments**; merge target noted.

| ID | Merged into (§8) | Date |
|----|------------------|------|
| R1-F1 | FR-IMP-2 · dual-key precedence | 2026-06-15 |
| R1-F2 | FR-IMP-1 · confirmed-row non-clobber | 2026-06-15 |
| R1-F3 | FR-IMP-1 · FK load ordering | 2026-06-15 |
| R1-F4 | FR-IMP-3 · cross-ref validation | 2026-06-15 |
| R1-F5 | §4 · OQ-IMP-D (new) | 2026-06-15 |
| R1-F6 | FR-IMP-3 · Surface column | 2026-06-15 |
| R2-F1 | FR-IMP-1 · export-contract reuse (ENTITY_ORDER/FIELDS) | 2026-06-15 |
| R2-F2 | FR-IMP-3 · OQ-IMP-5 normative | 2026-06-15 |
| R2-F3 | FR-IMP-6 · upload safety (UTF-8/size/ext) | 2026-06-15 |
| R2-F4 | FR-IMP-3 · duplicate-entity policy | 2026-06-15 |
| R2-F5 | FR-IMP-1 · text-path acceptance | 2026-06-15 |
| R2-F6 | FR-IMP-2 · composite verbatim | 2026-06-15 |
| R2-F7 | §3 · conditional ownership (opt-in) | 2026-06-15 |
| R3-F1 | FR-IMP-1 · restore source/confirmed stamping | 2026-06-15 |
| R3-F2 | FR-IMP-1 · identity:id upsert | 2026-06-15 |
| R3-F3 | FR-IMP-6 · CSRF (inherit form-layer posture) | 2026-06-15 |
| R3-F4 | FR-IMP-3 · assembly-inputs catalog (+ plan R3-S3) | 2026-06-15 |
| R3-F5 | FR-IMP-6 · import ≠ extract | 2026-06-15 |
| R3-F6 | §3 · OQ-IMP-C coexistence | 2026-06-15 |
| R4-F1 | FR-IMP-2 · three-valued (derived-source) map | 2026-06-15 |
| R4-F2 | FR-IMP-1 · type re-coercion (to_json default=str) | 2026-06-15 |
| R4-F3 | FR-IMP-2 · two-layer seam (harness vs persist) | 2026-06-15 |
| R4-F4 | FR-IMP-2 · five persist branches (scoped) | 2026-06-15 |
| R4-F5 | FR-IMP-3 · candidate-ordered cross-ref | 2026-06-15 |
| R4-F6 | FR-IMP-1 · partial-import atomicity | 2026-06-15 |
| R4-F7 | FR-IMP-2 · composite coerced-value compare | 2026-06-15 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Source | Rationale | Date |
|----|--------|-----------|------|
| R2 (2nd block) | composer-2.5 | **Duplicate** — the requirements doc carries two identical R2 blocks (a transcription artifact); triaged once via the IDs above, the second block is not re-dispositioned. | 2026-06-15 |

*(No substantive rejects — R3-F3 CSRF accepted in the softened "inherit form-layer posture" form; all
others applied verbatim-in-intent.)*

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 21:00:00 UTC
- **Scope**: Requirements-side gaps for consolidation, from_json gate, grammar cross-refs, OQ-IMP-D, confirmed-row policy.

### Sponsor focus — answers (requirements lens)

See plan Appendix C R1 for full ask-by-ask answers; requirements-specific deltas below.

**Ask 1 (FR-IMP-2):** Add explicit **dual-key conflict rule** and **four-helper consolidation scope** to FR-IMP-2 Verify block.

**Ask 3 (FR-IMP-1):** Extend Verify with **confirmed-row non-clobber** and **FK ordering** — import failures unique vs emit.

**Ask 4 (FR-IMP-3):** Align §5 authoring table with **Surface** column; require **cross-ref validation** at parse time.

**Ask 5 (OQ-IMP-D):** Add to §4 Open Questions with strtd8 default + decision deadline.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | high | **FR-IMP-2 dual-key rule:** When a pass or import row could specify both `source_binding`/`source:` identity **and** `dedup_by`/field identity, FR-IMP-2 MUST state **precedence** (lean: `source` scope wins; `dedup_by` ignored with extraction warning) or **fail loud** at parse — not implementation-defined. | FR-IMP-2 lists vocabulary but not interaction of the two **shipped** keys (`ai_layer.py:95-99`). Consolidation without a rule lets one abstraction leak. | FR-IMP-2, new bullet after vocabulary list | Parse test: manifest with both keys ⇒ defined outcome (error or mapped `IdentityKey` + warning row) |
| R1-F2 | Validation | high | **FR-IMP-1 confirmed-row policy:** Extend FR-IMP-1 Verify: `from_json` MUST NOT overwrite or delete rows with `confirmed:true` for the declared identity key; collision ⇒ `ImportResult` error (same semantics as FR-8 re-synthesis in `_PERSIST_DEDUP_HELPER`). | FR-IMP-1 covers idempotency and field fidelity but not **confirmed** rows — AI path already never clobbers confirmed (`ai_layer.py:611-612`). Import restore without this rule can destroy user-confirmed data. | FR-IMP-1 Verify paragraph | Test: confirmed row exists ⇒ re-import reports collision, row unchanged |
| R1-F3 | Validation | high | **FR-IMP-1 FK ordering:** FR-IMP-1 MUST define load order for multi-entity `to_json` payloads (parent before child per schema FKs) or fail loud when order cannot be satisfied — not leave to SQLAlchemy insert order. | FR-IMP-1: "`from_json` ingests the app's own `to_json` export format" — exports can include dependent entities. Emit gate (FR-PE-6) has no DB FK concept; this is import-unique. | FR-IMP-1, new sentence in body | Fixture with parent/child entities: child-first payload ⇒ error or reorder; parent-first succeeds |
| R1-F4 | Interfaces | medium | **FR-IMP-3 cross-ref validation:** `parse_imports` MUST validate `extract_via` against `ai_passes.yaml` pass names and `provenance` against `human_inputs.yaml` owned fields — unknown entity is already loud; **unknown pass/field cross-ref must be equally loud**. | §5: "`extract_via` — the `ai_passes.yaml` pass name" and provenance cross-ref to `human_inputs.yaml` — no Verify line for referential integrity at parse time. | FR-IMP-3 Verify + §5 bullet list | `extract_via: no-such-pass` ⇒ parse error; provenance not in owned fields ⇒ parse error |
| R1-F5 | Ops | medium | **OQ-IMP-D — name the consumer:** Add §4 open question: first consumer must be named before Phase 5; **provisional default strtd8** (§6) with formats `{json, text}` and acceptance entities pinned in a fixture path. Unresolved by decision date blocks e2e acceptance only, not P2 grammar. | Plan Phase 0.2 names OQ-IMP-D; requirements §4 lacks it while §6 already maps strtd8. Unnamed consumer poisons F-304/P5 acceptance per sponsor ask 5. | §4 Open Questions (new OQ-IMP-D) | Decision record exists; F-304 tests reference pinned fixture |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Interfaces | low | **§5 grammar table — Surface column:** Add **Surface** to the `## Imports` authoring table (plan F-204 already includes it) so FR-IMP-6 `surface: true` is authorable from the contract table, not only emitted YAML. | §5 markdown table columns: `Entity \| Format \| Identity \| Provenance \| Extract via` — emitted example shows `surface: true` with no authoring-column home. | §5 Authoring grammar table + bullet list | Round-trip: `## Imports` row with Surface=yes ⇒ `imports.yaml` `surface: true` |

**Endorsements:** none — first round.

**Disagreements:** none.

#### Review Round R2 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 22:30:00 UTC
- **Scope**: Requirements precision — export contract reuse, OQ-IMP-5 extraction rule, surface upload safety, duplicate-template policy, conditional ownership, text-format acceptance.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | **FR-IMP-1 export contract reuse:** FR-IMP-1 MUST state that `from_json` loads entities in **`ENTITY_ORDER`** and validates fields against **`FIELDS`** from the generated `app/export.py` — not an independent schema walk. The round-trip oracle is export→import, not schema→import. | FR-IMP-1: "`from_json` ingests the app's own `to_json` export format" — `render_export` defines order + allowed fields (`derived.py:55-56`). Independent derivation is an untested second contract. | FR-IMP-1 body, after "`to_json` export format" | Test: export payload with entities in `ENTITY_ORDER` succeeds; field not in `FIELDS[entity]` ⇒ `ImportResult` error |
| R2-F2 | Validation | medium | **OQ-IMP-5 → normative:** Promote OQ-IMP-5 from open question to FR-IMP-3 Verify rule: `identity: source:<field>` **requires** a non-blank **Provenance** naming the same field (or a documented superset); violation ⇒ loud at **`## Imports` extraction**, not runtime. | §4 OQ-IMP-5 leans fail-loud at extraction; FR-IMP-3 Verify lists unknown entity/field only. Authoring table row 3 (`ProofPoint`) pairs both — rule must be explicit for partial rows. | FR-IMP-3 Verify + §5 Provenance bullet | Row with `source:` identity + blank Provenance ⇒ `not_extracted`, no YAML entry |
| R2-F3 | Security | medium | **FR-IMP-6 upload safety:** Extend FR-IMP-6 Verify: text upload MUST accept **UTF-8** (reject binary/non-UTF-8 with user-visible error), enforce a **documented max size** (lean: 1 MiB, configurable constant in generated code), and accept only `.txt`/`.md` extensions for file upload (paste path unchanged). | §3 Non-Requirements bounds formats to text but not upload attack surface. Unbounded binary upload to a paste route is an end-user footgun and DoS vector. | FR-IMP-6 Verify paragraph | Test: upload `application/pdf` ⇒ 400; 2 MiB paste ⇒ 413/validation error; valid `.md` succeeds |
| R2-F4 | Data | medium | **Duplicate entity rows:** FR-IMP-3 MUST state whether multiple `## Imports` rows for the **same Entity** are allowed (e.g. `json` + `text` templates) or **fail loud** at extraction. If allowed, `parse_imports` must define merge precedence; if forbidden, one row per entity. | §5 table has one row per entity in examples; no rule for two rows same Entity different Format. Silent last-wins in YAML list is implementation-defined. | FR-IMP-3 body or §5 bullet list | Two rows `ImportedDocument` ⇒ defined outcome (error or ordered list with stable precedence) |
| R2-F5 | Validation | medium | **Text-format acceptance:** Extend FR-IMP-1 Verify with a **text-path** case: importing a pasted/stored text document (not only `to_json` payload) creates/updates the target row per declared identity — mirrors strtd8 FR-13 byte-for-byte storage. F-304 plan cites JSON round-trip only. | FR-IMP-1 Verify focuses on `from_json(to_json(x))`; strtd8 §6 maps FR-13 round-trip to FR-IMP-1 but format is `text`, not JSON. | FR-IMP-1 Verify paragraph | Fixture: paste text via surface or `from_text` helper ⇒ row stored byte-identically |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F6 | Data | low | **OQ-IMP-1 closure for Phase 3:** FR-IMP-2 Verify should cross-reference OQ-IMP-1: composite identity `[a,b]` comparisons are **verbatim** (no trim/case-fold) in v1; document in FR-IMP-2 Verify so import and AI paths share one comparand rule. | §4 OQ-IMP-1 leans verbatim; FR-IMP-2 Verify lists composite behavior but not normalization policy — import `from_json` and `_persist` could diverge on whitespace. | FR-IMP-2 Verify, composite bullet | `" foo "` vs `"foo"` under `identity: [a]` ⇒ no match (distinct rows or reported collision per policy) |
| R2-F7 | Ops | low | **Conditional ownership fence:** Add to §3 Non-Requirements (or FR-IMP-1): when no `imports.yaml` exists, the SDK **does not emit** `app/import.py` and drift does not expect it — import is opt-in via manifest, unlike always-on `app/export.py`. | Export is universal (`render_derived` unconditional); import is manifest-declared. Requirements never state opt-in emission; risks spurious drift on every generated app. | §3 Non-Requirements, new bullet | App without `## Imports` ⇒ no `app/import.py` in layout; `--check` passes |

**Endorsements** (untriaged R1):

- R1-F1 (dual-key precedence), R1-F2 (confirmed-row), R1-F3 (FK ordering), R1-F4 (cross-ref validation), R1-F5 (OQ-IMP-D in §4), R1-F6 (Surface column).

**Disagreements:** none.

#### Review Round R2 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 22:30:00 UTC
- **Scope**: Requirements precision — export contract reuse, OQ-IMP-5 extraction rule, surface upload safety, duplicate-template policy, conditional ownership, text-format acceptance.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Interfaces | high | **FR-IMP-1 export contract reuse:** FR-IMP-1 MUST state that `from_json` loads entities in **`ENTITY_ORDER`** and validates fields against **`FIELDS`** from the generated `app/export.py` — not an independent schema walk. The round-trip oracle is export→import, not schema→import. | FR-IMP-1: "`from_json` ingests the app's own `to_json` export format" — `render_export` defines order + allowed fields (`derived.py:55-56`). Independent derivation is an untested second contract. | FR-IMP-1 body, after "`to_json` export format" | Test: export payload with entities in `ENTITY_ORDER` succeeds; field not in `FIELDS[entity]` ⇒ `ImportResult` error |
| R2-F2 | Validation | medium | **OQ-IMP-5 → normative:** Promote OQ-IMP-5 from open question to FR-IMP-3 Verify rule: `identity: source:<field>` **requires** a non-blank **Provenance** naming the same field (or a documented superset); violation ⇒ loud at **`## Imports` extraction**, not runtime. | §4 OQ-IMP-5 leans fail-loud at extraction; FR-IMP-3 Verify lists unknown entity/field only. Authoring table row 3 (`ProofPoint`) pairs both — rule must be explicit for partial rows. | FR-IMP-3 Verify + §5 Provenance bullet | Row with `source:` identity + blank Provenance ⇒ `not_extracted`, no YAML entry |
| R2-F3 | Security | medium | **FR-IMP-6 upload safety:** Extend FR-IMP-6 Verify: text upload MUST accept **UTF-8** (reject binary/non-UTF-8 with user-visible error), enforce a **documented max size** (lean: 1 MiB, configurable constant in generated code), and accept only `.txt`/`.md` extensions for file upload (paste path unchanged). | §3 Non-Requirements bounds formats to text but not upload attack surface. Unbounded binary upload to a paste route is an end-user footgun and DoS vector. | FR-IMP-6 Verify paragraph | Test: upload `application/pdf` ⇒ 400; 2 MiB paste ⇒ 413/validation error; valid `.md` succeeds |
| R2-F4 | Data | medium | **Duplicate entity rows:** FR-IMP-3 MUST state whether multiple `## Imports` rows for the **same Entity** are allowed (e.g. `json` + `text` templates) or **fail loud** at extraction. If allowed, `parse_imports` must define merge precedence; if forbidden, one row per entity. | §5 table has one row per entity in examples; no rule for two rows same Entity different Format. Silent last-wins in YAML list is implementation-defined. | FR-IMP-3 body or §5 bullet list | Two rows `ImportedDocument` ⇒ defined outcome (error or ordered list with stable precedence) |
| R2-F5 | Validation | medium | **Text-format acceptance:** Extend FR-IMP-1 Verify with a **text-path** case: importing a pasted/stored text document (not only `to_json` payload) creates/updates the target row per declared identity — mirrors strtd8 FR-13 byte-for-byte storage. F-304 plan cites JSON round-trip only. | FR-IMP-1 Verify focuses on `from_json(to_json(x))`; strtd8 §6 maps FR-13 round-trip to FR-IMP-1 but format is `text`, not JSON. | FR-IMP-1 Verify paragraph | Fixture: paste text via surface or `from_text` helper ⇒ row stored byte-identically |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F6 | Data | low | **OQ-IMP-1 closure for Phase 3:** FR-IMP-2 Verify should cross-reference OQ-IMP-1: composite identity `[a,b]` comparisons are **verbatim** (no trim/case-fold) in v1; document in FR-IMP-2 Verify so import and AI paths share one comparand rule. | §4 OQ-IMP-1 leans verbatim; FR-IMP-2 Verify lists composite behavior but not normalization policy — import `from_json` and `_persist` could diverge on whitespace. | FR-IMP-2 Verify, composite bullet | `" foo "` vs `"foo"` under `identity: [a]` ⇒ no match (distinct rows or reported collision per policy) |
| R2-F7 | Ops | low | **Conditional ownership fence:** Add to §3 Non-Requirements (or FR-IMP-1): when no `imports.yaml` exists, the SDK **does not emit** `app/import.py` and drift does not expect it — import is opt-in via manifest, unlike always-on `app/export.py`. | Export is universal (`render_derived` unconditional); import is manifest-declared. Requirements never state opt-in emission; risks spurious drift on every generated app. | §3 Non-Requirements, new bullet | App without `## Imports` ⇒ no `app/import.py` in layout; `--check` passes |

**Endorsements** (untriaged R1):

- R1-F1 (dual-key precedence), R1-F2 (confirmed-row), R1-F3 (FK ordering), R1-F4 (cross-ref validation), R1-F5 (OQ-IMP-D in §4), R1-F6 (Surface column).

**Disagreements:** none.

#### Review Round R3 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 23:45:00 UTC
- **Scope**: Restore semantics, upsert policy, CSRF on import POST, assembly-inputs catalog, Phase 5 loop ordering, OQ-IMP-C coexistence.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Data | high | **FR-IMP-1 restore stamping:** FR-IMP-1 MUST define row provenance on import: rows restored via `from_json(to_json(x))` **preserve** `source` and `confirmed` from the export payload field-for-field; rows created via text/surface import default to `source="human"` (or project convention) and `confirmed=false` unless the template declares restore semantics. Not AI `source="ai"` defaults. | FR-IMP-1 covers field fidelity but not **provenance columns** — `_persist` always sets `source="ai", confirmed=false` (`ai_layer.py:577-580`). Import restore copying export could silently flip confirmed state or apply AI defaults. | FR-IMP-1 body + Verify | Round-trip export with `confirmed:true` row ⇒ re-import preserves `confirmed:true`; surface paste ⇒ `confirmed:false` |
| R3-F2 | Data | high | **FR-IMP-1 `identity: id` upsert:** When export payload includes explicit `id` and template declares `identity: id`, `from_json` MUST **upsert** that primary key (update in place if unconfirmed policy allows, or report collision if confirmed — per R1-F2); without `id`, allocate a new row. Restore fidelity depends on this. | FR-IMP-2 Verify mentions `identity: id` upserts but FR-IMP-1 never ties upsert to export payload shape; `to_json` includes `id` when present in rows. | FR-IMP-1 Verify, idempotency bullets | Export row with known `id` ⇒ re-import updates same row; new id absent ⇒ insert |
| R3-F3 | Security | medium | **FR-IMP-6 CSRF:** Import surface POST MUST use the same CSRF/session token pattern as generated HTMX entity forms (hidden field or header check). Paste/upload is a state-changing POST — out of scope for generic CRUD create only when form CSRF exists. | FR-IMP-6 Verify covers byte-round-trip only; unauthenticated POST import is a classic CSRF vector on multi-user deployments. | FR-IMP-6 Verify paragraph | POST without valid CSRF token ⇒ 403; with token ⇒ 200/redirect |
| R3-F4 | Ops | medium | **Assembly-inputs catalog:** Add `imports` key to kickoff `ASSEMBLY_INPUTS_TEMPLATE.md` manifest inventory (`prisma/imports.yaml`) — eighth manifest alongside `views`, `ai_passes`, etc. Pairs with wireframe `CONVENTION_PATHS` (R3-S3). | §5 positions `imports.yaml` as 7th manifest; assembly-inputs template and wireframe still enumerate seven paths (`wireframe/inputs.py:30-38`). Authors won't discover the path. | §5 "Three accompanying manifest cross-edits" → four; kickoff template cross-ref | `ASSEMBLY_INPUTS_TEMPLATE` lists `imports`; wireframe resolves path |
| R3-F5 | Validation | medium | **Import ≠ extract (normative):** FR-IMP-6 MUST explicitly restate: successful import POST **never** invokes `extract_via` — extraction is a separate user action (FR-IMP-4). Plan Phase 5.2 boot-smoke should list three **sequential** user steps, not one combined POST. | FR-IMP-6 says "nothing extracted by the act of importing" but Phase 5.2 prose bundles "import via surface … extract" without ordering guard — implementers might wire auto-extract on upload. | FR-IMP-6 body + Phase 5.2 plan cross-ref | POST import ⇒ row stored, zero AI-pass invocations; extract only on explicit `/run-extract` |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F6 | Ops | low | **OQ-IMP-C coexistence note:** Add §3 Non-Requirements bullet: when a consumer already has bespoke restore (strtd8 FR-10), generated `from_json` **complements** it — the SDK does not remove or auto-replace app-authored restore; authors choose one entrypoint. Prevents double-write if both coexist. | §4 OQ-IMP-3 open; §6 maps strtd8 FR-13 to FR-IMP-1 but FR-10 bespoke restore may still exist. No fence against two restore paths writing the same entity. | §3 Non-Requirements | Doc + test fixture: both paths documented; no generated code deletes bespoke restore module |

**Endorsements** (untriaged R2):

- R2-F1 (export contract reuse), R2-F2 (OQ-IMP-5 normative), R2-F3 (upload safety), R2-F4 (duplicate entity rows), R2-F5 (text-format acceptance), R2-F7 (conditional ownership).

**Disagreements:** none.

#### Review Round R4 — claude-opus-4-8 — 2026-06-15

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-15 12:31:00 UTC
- **Scope**: Deeper code-grounded pass over the consolidation seam, the `to_json` type-coercion round-trip gap, and the derived-vs-declared `source_binding` back-compat blind spot. Read `ai_layer.py` (`effective_source_binding`, the 4+1 persist branches), `derived.render_export` (`default=str`), `manifest_extraction/extract.py` (round-trip gate) on `feat/import-path` (= `origin/main` target). Prior reviewer (composer-2.5, R1–R3) covered breadth thoroughly; this round goes deeper on three things the prose-level review could not see in the code.

### Sponsor focus — answers (requirements lens; full ask-by-ask in plan R4)

**Ask 1 (FR-IMP-2 vocabulary completeness):** Vocabulary is **incomplete** — it omits the **derived** `source_binding` state. `effective_source_binding` (`ai_layer.py:312-339`) resolves a source binding three ways: explicit, **schema-derived (zero authored config)**, and `none` (explicit DISABLE sentinel). A manifest with NO `source_binding` key can still emit a source-bound harness. The `IdentityKey` vocabulary (`id|field|composite|source|name|none`) and the back-compat map (F-102: "`source_binding` → `source:<field>`; neither → `name`") both assume binding is declared-or-absent; the derived case is a third path that maps to `source` with **no manifest key present**. Byte-identity over *declared-key* manifests will not exercise it. See R4-F1.

**Ask 3 (FR-IMP-1 round-trip fidelity):** `to_json` serializes with `default=str` (`derived.py:60`) — datetimes, Decimals, booleans-as-? and FK ints all land as **strings** in the JSON. `from_json` round-trip fidelity is therefore **lossy unless it re-coerces** each field to its schema type. "field fidelity (sorted-key stable)" in FR-IMP-1 Verify is satisfiable by a string-only echo that silently corrupts typed columns. See R4-F2.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | high | **FR-IMP-2 must cover the DERIVED source-binding state, not just declared/absent.** Add to FR-IMP-2: the unified identity key has a **derived-`source`** case — a pass with no `source_binding` key but exactly one schema-derived loose-ref provenance field (`effective_source_binding` derivation) maps to `identity: source:<derived-field>`, NOT to `name`. The back-compat map is three-valued (explicit `source:` / derived `source:` / `none`→ no-bind), not two. | FR-IMP-2 says "an entity with no declaration still dedups by `name`" — but `effective_source_binding` (`ai_layer.py:328-336`) derives a `source` binding from schema+human_inputs with zero authored config; such a pass does NOT name-dedup today. Mapping it to `name` is a silent behavior change the byte-identity gate (declared-key manifests only) won't catch. | FR-IMP-2 vocabulary + back-compat paragraph | Fixture: pass with a single server-managed optional-String loose-ref field, **no** `source_binding` key ⇒ post-consolidation `IdentityKey.kind == source` (byte-identical harness), not `name` |
| R4-F2 | Data | high | **FR-IMP-1 must specify type re-coercion on import.** Add to FR-IMP-1 Verify: `from_json` MUST coerce each field back to its **declared schema type** (datetime/Decimal/int/bool/FK), because `to_json` emits `default=str` (every non-JSON-native value becomes a string). A bare `from_json` that writes the string back round-trips *textually* but corrupts typed columns. Round-trip fidelity is type-faithful, not string-faithful. | `render_export` (`derived.py:60`): `json.dumps(..., default=str)`. The export is lossy-to-string for typed fields; import must invert it using `FIELDS`+schema types or the "field fidelity" claim is false for any datetime/Decimal/int column. | FR-IMP-1 Verify paragraph | Fixture: entity with a `DateTime`/`Int` column ⇒ `from_json(to_json(rows))` yields rows whose typed columns equal the originals by **value and type**, not string repr |
| R4-F3 | Architecture | high | **FR-IMP-2 seam: source-scope idempotency is HARNESS-level, not persist-level — say so.** Clarify FR-IMP-2: the "shared `identity` helper consumed at both call sites" resolves the key, but **applying** a `source` key is a pre-insert *clear-prior-unconfirmed* step in the harness body (`_render_pass_text_bound`, `ai_layer.py:706-716`: `select(...).where(prov==source_id, confirmed.is_(False))` + delete), separate from the per-row `_persist*`. A unified `_persist(session, model, edge, *, identity)` that dispatches only inside the persist call **cannot** express source-scope idempotency. The seam is two-layered (resolve key + apply policy), not one helper. | The focus ask 1 "one abstraction will leak" is real: `id`/`field`/`composite`/`name` are per-row persist concerns; `source` is a per-run harness concern. Collapsing all five into one `_persist` signature loses where source-scope lives. | FR-IMP-2 "shared seam" sentence | Code review gate: the consolidation keeps the per-run source-clear in the harness; a generated source-bound harness still emits the pre-clear loop (byte-identical) |
| R4-F4 | Risks | medium | **FR-IMP-2 must include the SCOPED (FR-SRP relational child) pass in consolidation scope, or explicitly exclude it.** `_PERSIST_SCOPED_HELPER` (`ai_layer.py:732`) is a **fifth** persist branch (`is_scoped` dispatch, `ai_layer.py:646-648`) taking `fk_values: dict` to set real FK relations — not just a provenance string. FR-IMP-2 names `ai_layer` persist helpers generically; state whether `is_scoped` passes are in the identity-key unification or fenced out (they have a distinct CHILD-FK shape). | Plan F-103 proposes one `_persist(..., identity)` dispatching on `IdentityKey.kind`; the scoped helper's extra `prov_field` + `fk_values` params don't fit that signature. Silent exclusion or a leaky merge are both regressions. | FR-IMP-2 Touches/scope sentence | Matrix test includes an `is_scoped` pass: post-consolidation it either keeps its own emit path (byte-identical) or maps cleanly to a documented `IdentityKey` variant |
| R4-F5 | Interfaces | medium | **FR-IMP-3 cross-ref validation must be ordering-explicit in the round-trip gate.** Strengthen FR-IMP-3 Verify (beyond R1-F4): `parse_imports`'s cross-manifest checks (`extract_via`→`ai_passes.yaml`, `provenance`→`human_inputs.yaml`) must source the sibling names from the **already-extracted candidate manifests**, exactly as `view_prose.yaml` sources `known_views` from the `views.yaml` candidate (`extract.py:191-196`). Specify that `imports.yaml` round-trips **after** `ai_passes.yaml`/`human_inputs.yaml` in the gate so the sibling candidates exist. | The round-trip gate iterates `candidates.items()` with no dependency ordering (`extract.py:200-214`); cross-ref validation that reads a sibling candidate before it is populated would false-pass or KeyError. The established pattern (view_prose) reads from the candidate dict, not from disk. | FR-IMP-3 Verify + §5 cross-ref bullet | Fixture: `imports.yaml` extracted before `ai_passes.yaml` is built ⇒ gate still validates `extract_via` (candidate ordering enforced); unknown pass ⇒ loud |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F6 | Validation | medium | **FR-IMP-1 `--allow-lossy` partial-import atomicity.** Specify the transaction boundary `--allow-lossy` implies: does a reported-but-skipped row commit the rows around it (per-row/per-entity savepoint) or roll back the file? FR-IMP-1 says rows are "reported, not dropped" but never says whether a partial import leaves the DB half-loaded. The shipped bound harness already uses `session.begin_nested()` per row (`ai_layer.py:721`) — reuse that pattern and name it. | FR-IMP-1 Verify covers idempotency + reporting but not durability of a partial run; `--strict` (abort) vs `--allow-lossy` (continue) differ precisely on commit boundary, which is undefined. | FR-IMP-1 Verify paragraph | Fixture: 3-row payload, row 2 invalid ⇒ `--allow-lossy` commits rows 1,3 + reports 2; `--strict` commits nothing |
| R4-F7 | Data | low | **OQ-IMP-1 + R4-F2 interaction: composite key compares post-coercion, not on string repr.** When OQ-IMP-1 is resolved verbatim (R2-F6), state the comparand is the **coerced typed value**, not the JSON string, so a composite `[createdAt, name]` doesn't false-dedup on string-formatted timestamps differing only in representation. | R2-F6 fixes verbatim-vs-normalized; R4-F2 adds type coercion. Their interaction is unspecified: comparing string reprs of typed fields under a composite key is a distinct correctness trap. | FR-IMP-2 Verify, composite bullet (cross-ref OQ-IMP-1, R4-F2) | Two rows whose `DateTime` serializes identically but differs in tz ⇒ defined (coerced) comparison outcome |

**Endorsements** (untriaged R1–R3):

- R1-F1 (dual-key precedence — but note R4-F1: precedence must also cover the *derived* binding, not only the two declared keys).
- R1-F2 (confirmed-row non-clobber), R1-F3 (FK ordering), R2-F1 (export contract reuse — R4-F2 extends it to type coercion, not only `ENTITY_ORDER`/`FIELDS`), R2-F2 (OQ-IMP-5 normative), R2-F3 (upload safety), R3-F1 (restore `source`/`confirmed` stamping), R3-F2 (`identity: id` upsert).

**Disagreements:** none — composer-2.5's R1–R3 are sound; R4 deepens R1-F1/R2-F1 rather than disputing them.
