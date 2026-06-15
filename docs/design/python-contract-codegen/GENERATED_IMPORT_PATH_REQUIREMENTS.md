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

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
