# Named / Shared Enum Grammar (Prisma Emitter, FR-PE-5 extension) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-09
**Status:** IMPLEMENTED 2026-06-09 (FR-PE-8…12; 12 new tests + a `md_tables` escaped-pipe fix; full
`manifest_extraction` + codegen suites green). App-side flip (acceptance #3, live `ApplicationStatus`
parity) pending the strtd8 team writing the `## Enums` declaration into their doc.
**Scope:** Extend the authoring-contract §2.1 grammar + the Prisma emitter with a **named enum
declared once and referenced by more than one field**, so a faithful re-emit of a contract that
shares an enum across models becomes possible. Closes the enum half of FR-PE-5 (which today covers
defaults / indexes / loose-refs but explicitly defers enums).
**Requested by:** the StartDate (strtd8) app team — `SDK_NAMED_ENUM_GRAMMAR_QUERY_2026-06-09.md`.
The generator→StartDate migration added `enum ApplicationStatus` (9 values) referenced by **two**
fields (`JobDescription.status`, `JobStatusEntry.status`); the grammar's per-field `choice of:` only
produces a `<Entity><Field>` enum, so the 18-model contract cannot be re-derived. This gates two
headline features at once: content-import (FR-13/15) and the time-to-job north-star (FR-OBS-5, which
*extends* that very enum with a `start_date_obtained` terminal).
**Related:**
- [`PRISMA_EMITTER_REQUIREMENTS.md`](PRISMA_EMITTER_REQUIREMENTS.md) — FR-PE-1…7; this extends
  FR-PE-5 (grammar gaps) and FR-PE-4 (semantic-parity diff)
- [`PRISMA_EMIT_COMMAND_REQUIREMENTS.md`](PRISMA_EMIT_COMMAND_REQUIREMENTS.md) — the shipped
  `startd8 generate contract` CLI this feeds
- `src/startd8/manifest_extraction/entities.py` — `extract_entities()` / `DocField` / `EntityGraph`
  (the choice-handling that names but discards per-field enums lives here)
- `src/startd8/manifest_extraction/prisma_emitter.py` — `render_prisma_schema()` / `semantic_diff()`
- `src/startd8/manifest_extraction/extract.py` — `_build_graph()` section routing + cross-doc merge
- `src/startd8/manifest_extraction/grammar.py` — `parse_sections()` / `md_tables()` / `strip_annotations()`
- `src/startd8/languages/prisma_parser.py` — `parse_prisma_schema()` already parses `enum` blocks
  (`enums: Dict[str, Tuple[str, ...]]`, `_parse_enum_body`, `is_scalar_or_enum`)

---

## 0. Planning Insights (Self-Reflective Update)

> Documents what changed between v0.1 (pre-planning, which inherited the strtd8 query's "add a
> named-enum construct; it composes cleanly" framing) and v0.2, after a code-investigation planning
> pass over `manifest_extraction/`. Five corrections — full mapping in
> [`NAMED_ENUM_GRAMMAR_PLAN.md`](NAMED_ENUM_GRAMMAR_PLAN.md) §Discoveries.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| `enum: ApplicationStatus` in the Type cell parses straightforwardly | `entities.py:146` **lowercases the whole type cell** before matching — the enum **name is destroyed** (`applicationstatus`) | FR-PE-9 now requires parsing the reference from the **raw** (un-lowercased) cell. Without it the name is unrecoverable. |
| Inline `choice of:` works; we add a parallel named path | `choice.group(1)` values are **discarded** and the emitter emits **no enum block at all** — every `choice of:` field today references a **dangling** type | FR-PE-10 (value capture + block emission) is the **load-bearing prerequisite** for *any* enum to round-trip, not an add-on. |
| `semantic_diff()` will catch enum drift | It iterates only `parsed.models`, never `parsed.enums` — the parity gate is **blind to enums** | FR-PE-11 promoted to load-bearing: the reconciliation's whole point is the live 9 values matching. |
| Enums land on the graph like entities | `_build_graph()` has no `enums` field, no `## Enums` routing, no cross-doc merge | FR-PE-8 specifies the new `EntityGraph.enums`, `extract_enums()`, routing, and `setdefault` merge — and **enum extraction must run before** entity-reference validation. |
| The Prisma parser may need enum support | `prisma_parser.py` **already** parses enum blocks (ordered `enums` dict) | FR-PE-10/11 are **low-risk** on the parse side — confirmed, no parser change. |

**Resolved open questions:**
- **OQ-PE-5 → pipe-separated value line.** Reuses the `choice of:` delimiter — one parse rule for both forms.
- **OQ-PE-6 → `enum: <Name>` token**, matched against the **raw** type cell (the lowercasing trap). A bare PascalCase token is rejected.
- **OQ-PE-8 → flag collisions.** Synthesized `<Entity><Field>` names and `## Enums` names share one namespace; a collision is `not_extracted(enum-name-collision)`, never a silent merge.
- **OQ-PE-7 → remains open** (default-value membership validation).

---

## 1. Problem Statement

The §2.1 entity-table grammar maps a `choice of: a|b|c` field to an enum **named after the field**
(`entities.py`: `prisma_type = f"{name}{fname[0].upper()}{fname[1:]}"`). Two fields that should
share one enum therefore get **two divergent per-field enums** — there is no construct for "these
fields use the *same* named enum."

| Live contract (hand-added by the migration) | What the grammar emits today |
|---|---|
| `enum ApplicationStatus { discovered … on_hold }` (9 values) | — (no named-enum construct) |
| `JobDescription.status ApplicationStatus @default(discovered)` | enum **`JobDescriptionStatus`** |
| `JobStatusEntry.status ApplicationStatus` | enum **`JobStatusEntryStatus`** |

Consequence: re-emitting from the doc yields two divergent enums, not the single shared
`ApplicationStatus` the contract and `app/generator/fsm.py` depend on. So `generate contract`
cannot reconcile the 18-model contract, the requirements doc stays behind the contract, and
`--promote` would drop the migration's entities.

| Construct | Source today | Target |
|-----------|--------------|--------|
| Per-field one-off enum (`choice of: a\|b\|c`) | Names `<Entity><Field>`; **values discarded, no enum block emitted** | Capture values; emit the `<Entity><Field>` enum block |
| **Named/shared enum** (one decl, N fields) | **Inexpressible** | A `## Enums` declaration; fields reference it by name; one emitted `enum` block |

## 2. Requirements

> One behavior per requirement. `Extends:` ties back to FR-PE. `Verify:` is the asserting test.

- **FR-PE-8 — Declare a named enum once.** A top-level `## Enums` section may declare named enums,
  one per `### Enum: <Name>` block, each carrying an ordered value set written as a single
  pipe-separated line (e.g. `discovered | applied | … | on_hold`). The parsed enums land on the
  `EntityGraph` (a new `enums` mapping `Name → (value, …)`), merged across docs like entities
  (later docs never override an earlier declaration). **Enum extraction MUST run before entity
  extraction** in `_build_graph()`, so a field's reference (FR-PE-9) can be validated against the
  declared set in the same pass (enums have no reverse dependency on entities). Extends: FR-PE-5
  (enum half). Verify: a doc with one `### Enum: ApplicationStatus` block of 9 values yields one
  graph enum with those 9 values in order; two docs declaring it keep the first.

- **FR-PE-9 — Reference a named enum from a field (raw-cell parse).** A field whose `Type` cell reads
  `enum: <Name>` is typed by that named enum (`prisma_type = <Name>`), with **no** per-field enum
  synthesized. The reference MUST be parsed from the **raw, un-lowercased** type cell —
  `entities.py` currently lowercases the cell before matching, which would destroy the enum name's
  case (`ApplicationStatus` → `applicationstatus`); the plain-type and `choice of:` matches keep
  using the lowercased form. The inline `choice of: a|b|c` path is unchanged and remains the one-off
  per-field form. A reference to an enum **not** declared in `## Enums` surfaces as
  `not_extracted(enum-undeclared)` — never a dangling type. Extends: FR-PE-5. Verify: two fields in
  two entities both reading `enum: ApplicationStatus` reference the one shared type with case
  preserved; an undeclared reference produces exactly one `not_extracted` row with a reason.

- **FR-PE-10 — Capture per-field `choice of:` values + emit every enum block (load-bearing).** This
  fixes the latent gap that makes the rest possible: today `choice.group(1)` values are **parsed but
  discarded** and the emitter emits **no enum block at all**, so a `choice of:` field references a
  **dangling** type. `DocField` must retain the inline values, and the emitter must render one
  `enum <Name> { … }` block for each named enum (FR-PE-8) **and** one `<Entity><Field>` block per
  inline `choice of:` field, in a stable canonical order, **before** the model blocks. A name
  collision between a synthesized `<Entity><Field>` and a declared `## Enums` name surfaces as
  `not_extracted(enum-name-collision)` — never a silent merge (OQ-PE-8). Extends: FR-PE-1. Verify: a
  doc mixing one named enum and one inline choice emits exactly two enum blocks whose value sets
  match the source; the emitted text parses back through `parse_prisma_schema()` with both enums
  present.

- **FR-PE-11 — Enum-aware semantic parity.** `semantic_diff()` compares enum **blocks** (presence +
  ordered value set) in addition to models, so a missing enum, an extra enum, or a differing value
  set each produces exactly one stable-keyed drift line. This makes the FR-PE-4 parity gate
  trustworthy for the `ApplicationStatus` reconciliation (the live 9 values must match). Extends:
  FR-PE-4. Verify: an emitted schema missing one enum value vs the live contract reports exactly
  one enum-drift line; identical enum sets report none.

- **FR-PE-12 — Compose with defaults and relationships.** A named-enum field composes with the
  existing FR-PE-5(a) `default: <value>` Notes convention (→ `@default(<value>)`, non-optional) and
  is orthogonal to the relationship/FK grammar (an entity may carry both a named-enum field and
  `belongs to` FKs). Extends: FR-PE-5(a). Verify: `JobDescription.status` with `enum:
  ApplicationStatus` + `default: discovered` emits `status ApplicationStatus @default(discovered)`;
  the same entity's FK fields are unaffected.

## 3. Non-Requirements

- **No LLM.** Deterministic AST rendering; an undeclared/inexpressible enum is flagged, never inferred.
- **No general Prisma enum surface.** Only what the strtd8 / startd8-generator contracts use:
  bare-identifier values, optional `@default(<value>)`. Out: `@map` on enum values, native DB enum
  types, enum-typed list fields (`Status[]`) — flagged `generator-gap` if encountered.
- **No `choice of:` removal.** Inline per-field enums stay for one-offs; the named form is additive.
- **No value-membership validation of defaults** (whether `@default(x)` names a declared enum value)
  — deferred; see OQ-PE-7.

## 4. Open Questions

- **OQ-PE-5 — RESOLVED (planning): pipe-separated value line** — reuses the `choice of:` delimiter,
  one parse rule for both forms.
- **OQ-PE-6 — RESOLVED (planning): `enum: <Name>` token**, matched against the **raw** type cell (the
  lowercasing trap, FR-PE-9). A bare PascalCase token is rejected.
- **OQ-PE-7 — OPEN. Default-value membership.** Should `default: x` on an enum field be validated
  against the enum's value set, or left to the downstream Prisma toolchain? (Lean: flag, don't block.)
- **OQ-PE-8 — RESOLVED (planning): flag collisions.** A synthesized `<Entity><Field>` colliding with a
  declared `## Enums` name is `not_extracted(enum-name-collision)`, never a silent merge (FR-PE-10).

## 5. Dependencies & sequencing

- **Sequence:** FR-PE-8 (declare) → FR-PE-9 (reference) → FR-PE-10 (emit blocks + capture values) →
  FR-PE-11 (parity) → FR-PE-12 (compose). FR-PE-10's value-capture fix is a prerequisite for *any*
  enum to round-trip, named or inline.
- **First consumers:** strtd8 `ApplicationStatus` (write the declaration into
  `REQUIREMENTS_v0.5-draft.md`, run `generate contract --check` to parity, re-open the derived
  loop); startd8-generator's sibling migration introduced the same enum (shared-floor — confirm one
  construct serves both, the query's Q4).
- **Unblocks:** content-import (FR-13/15) via `--promote`; the time-to-job north-star (FR-OBS-5),
  which adds `start_date_obtained` to `ApplicationStatus` as a prose edit.

## 6. Acceptance

1. Golden-fixture unit tests: named-enum declaration, multi-field reference, inline-choice value
   capture, mixed named+inline emission, undeclared-reference `not_extracted`, default composition.
2. Round-trip: every emitted schema (named + inline enums) parses through `parse_prisma_schema()`.
3. Parity: an emitter run over a doc declaring `ApplicationStatus` + the two referencing fields
   reaches **zero** enum-aware semantic-parity drift against the live contract's enum + fields.
4. End-to-end: adding `enum: ApplicationStatus` references (and later a 10th value) to the strtd8
   doc and re-running `generate contract --check` reports parity with no Prisma hand-editing.

---

*v0.2 — Post-planning self-reflective update. 5 requirements clarified (FR-PE-9 raw-cell parse,
FR-PE-10 reframed as the load-bearing value-capture fix, FR-PE-8 pass-ordering, FR-PE-11 promoted to
load-bearing, FR-PE-12 verify-not-build), 3 open questions resolved (OQ-PE-5/6/8), 1 still open
(OQ-PE-7). Plan: [`NAMED_ENUM_GRAMMAR_PLAN.md`](NAMED_ENUM_GRAMMAR_PLAN.md).*
