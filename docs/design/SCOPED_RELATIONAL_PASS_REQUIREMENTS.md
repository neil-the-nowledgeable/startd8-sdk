# Scoped relational AI-pass shape (FR-SRP) — Requirements

**Version:** 0.2 (post-investigation)
**Date:** 2026-06-11
**Status:** IMPLEMENTED 2026-06-11 — FR-SRP-1..5 in `ai_layer.py` (ScopeRelation + scope/scope_relations/
reads_confirmed/output_fk manifest keys; `_render_pass_scoped` join harness; `_persist_scoped` real-FK
child; needs_more_data floors). Runtime-proven (TestClient: linked Contact → TailoredAsset with real
jobDescriptionId FK + loose contactId; unlinked → needs_more_data) + drift round-trips. 283 passed.
**Scope:** A **third** generated AI-pass shape so a pass scoped to **one source row** can (a) resolve a
**relational join** from that row, (b) include whole-model **confirmed** context, and (c) write a
**cascade-FK child** — returning the strtd8 FR-MSG interviewer-message harness to **$0 generation**
(today it must be a hand-authored owned pass). Generalized — not interviewer/message-specific.
**Requested by:** strtd8 app team — `docs/v2/FR_MSG_INTERVIEWER_MESSAGE_REQUIREMENTS_v0.2-draft.md`
(Hybrid decision: hand-author now, file this SDK capability so the harness returns to $0).
**Component:** `backend_codegen/ai_layer.py` (`AiPass`/`parse_ai_passes`, `render_ai_pass`,
`_render_pass_text_bound`, `_PERSIST_SOURCE_HELPER`), `ai_passes.yaml` grammar.

## 0. Planning insights (from reading the two existing shapes)

| Assumption | Discovery (ai_layer.py) | Impact |
|------------|-------------------------|--------|
| A new pass signature is needed | The **source-bound** shape already is `def <pass>(text, session, source_id)` and the **FR-AIT `trigger:`** already delivers `source_id` = the host-entity row id (`:928-938`). | **Reuse it** — the scoped pass is the source-bound signature + join resolution; no new signature, and the trigger surface already drives it. |
| The join + the confirmed context are one new mechanism | The **read shape** (`_render_pass_read`) already builds whole-model **confirmed** context from `input_entities` (`select(M).where(confirmed)`); the gap is *only* the **per-row FK traversal** (`:791-795` reads are whole-model, never row-scoped). | The capability = **scoped FK traversal (new)** + reuse of the existing whole-model-confirmed read + the existing prompt build. Smaller than it looks. |
| Persist can set the FK | `_persist_source` (`:610-624`) sets **one loose-ref scalar** via `setattr`; a real **required FK** (`TailoredAsset.jobDescriptionId`) is never set → `INSERT` NULL-fails (`:620`, v0.2 §0). | A **new persist** must set a real FK **from the resolved relation's id** (+ keep the loose provenance). |
| The FK target is inferable | A `<x>Id` scalar's target is the SDK FK convention (`<lowerCamel(T)>Id` → `T`) — already used for FR-DM-6 view resolution. But a pass author should declare it (explicit > magic) since the scope row may have several FKs. | Manifest **declares** the traversals; the emitter validates them against the contract (loud-fail). |
| Graceful degradation is bespoke | The source-bound harness already short-circuits on a keyless provider (FR-40). | Add a pre-call **"needs more data"** guard: missing scope row / missing **required** relation / zero confirmed context → return without calling the AI or writing a draft. |

**Resolved open questions:** OQ-SRP-2 (signature) → reuse source-bound. OQ-SRP-3 (FK target) → declared,
validated. OQ-SRP-4 (confirmed context) → reuse the read shape's whole-model confirmed read.
**Still open:** OQ-SRP-1 — the exact manifest key shape (§4).

## 1. Problem statement

| Pass shape | Reads | Writes | Gap |
|------------|-------|--------|-----|
| whole-model `pass(session)` | `input_entities` whole-model (confirmed) | top-level rows (name/dedup) | not row-scoped |
| source-bound `pass(text, session, source_id)` | free text | **one** top-level row + **one loose-ref** scalar | no relation traversal; no real FK |
| **scoped relational (this)** | **one source row + its declared FK relations** + whole-model confirmed | a **child** with a **real FK** (from the join) + a loose provenance | **can't be generated today** |

## 2. Functional Requirements

- **FR-SRP-1 — Manifest: declare a scoped relational pass.** A pass may declare `scope: <Entity>`
  (it runs per-row; `source_id` = that row's id), `scope_relations:` (a list of FK traversals
  `{via: <fkField>, entity: <Target>, optional: <bool>}`), `reads_confirmed:` (whole-model confirmed
  entities for context), and `output_fk:` (`{<outputFkField>: <Target>}` — set a real FK on the output
  from a resolved relation). Strict-parsed: unknown `scope` entity, `via` not an FK column, `entity`/
  `output_fk` target not a model → loud fail against the contract. Verify: a valid block parses; each
  bad-ref class raises.

- **FR-SRP-2 — Generated harness resolves the join.** Emit `def <pass>(text, session, source_id)` that:
  `session.get(<scope>, source_id)`; for each `scope_relations` entry, `session.get(<Target>,
  getattr(row, via))` (skipped when optional + null); and reads each `reads_confirmed` entity
  whole-model `where(confirmed)`. The resolved rows + the free `text` build the prompt context handed to
  `call_ai_service` (the prompt is app-authored; harness owned). Verify: the harness loads the scope
  row, traverses required + optional FKs, includes the confirmed reads, and compiles.

- **FR-SRP-3 — Cascade-FK child persist.** A new persist sets, on the output row: the AI-authored edge
  fields, `source="ai"`/`confirmed=false`, the **loose provenance** (`source_binding` ← `source_id`,
  existing), AND each `output_fk` field ← the **resolved relation row's id** (a real FK). Verify: the
  output persists with a non-null real FK from the join (no INSERT NULL-fail) + the loose provenance.

- **FR-SRP-4 — Graceful degradation ("needs more data").** Before calling the AI: if the scope row is
  missing, or any **required** (non-optional) `scope_relations` target doesn't resolve, or every
  `reads_confirmed` entity has zero confirmed rows → return `{"status": "needs_more_data", "created":
  {...0}}` without calling the AI or writing a draft. Verify: an untyped/unlinked scope row (missing
  required relation) and an empty confirmed context each yield `needs_more_data`, no draft, no AI call.

- **FR-SRP-5 — Compose + inert.** Composes with the existing `source_binding` (loose provenance) and the
  FR-AIT `trigger:` (delivers `source_id`); the source-scope re-run idempotency (clear prior unconfirmed
  by provenance) is preserved. A pass with **no** `scope:` emits byte-identically to today. Verify: a
  no-`scope` manifest produces unchanged output; a scoped pass is drift-registered (`ai-pass` kind) and
  round-trips `--check`.

## 3. Non-Requirements

- **No multi-hop join** (v1: one FK hop from the scope row — `scope → Target`; `Target → Target2` is a
  follow-on). The whole-model confirmed reads cover the "deep context" need without traversal.
- **No AI-authored FKs** — FKs are harness-set from the resolved join; the AI never writes a relation id
  (the FR-6/provenance discipline).
- **No new output cardinality** — one output child per run (the source-bound single-output rule). A
  multi-row scoped pass is out.
- **No prompt assembly opinions** — the harness hands resolved rows to the app-authored prompt; the SDK
  does not template the message.

## 4. Open Questions

- **OQ-SRP-1 — manifest key shape.** `scope` + `scope_relations` + `reads_confirmed` + `output_fk` (above)
  vs. a more compact `join:`/`reads:` form. Must stay strict-parseable + compose with existing pass keys
  (`source_binding`, `trigger`, `request_field`).
- **OQ-SRP-5 — should `scope_relations` be derivable** from the contract FKs (so the author only lists
  which to *include*), or fully explicit? Lean: explicit `via`+`entity`, validated (no magic).
- **OQ-SRP-6 — `needs_more_data` surfacing.** Return shape `{status, created}` vs an HTTP 422 at the
  route. Lean: the harness returns the status; the route maps it (mirrors the FR-40 503 pattern).

## 5. Acceptance

1. `parse_ai_passes` strict-parses a scoped pass; bad scope/via/entity/output_fk → loud.
2. The generated harness compiles, resolves scope + required/optional FKs + confirmed reads, and persists
   a child with a real FK (no NULL-fail) + loose provenance + `source/confirmed`.
3. Graceful degradation: missing required relation OR empty confirmed context → `needs_more_data`, no AI
   call, no draft. (Runtime-proven via a generated-app TestClient against the FR-MSG shape.)
4. No-`scope` passes are byte-identical; scoped passes round-trip `--check` (drift-registered).
