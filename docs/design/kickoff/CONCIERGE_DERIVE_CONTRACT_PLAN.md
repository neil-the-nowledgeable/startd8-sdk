# Concierge `derive-contract` — Implementation Plan

**Version:** 0.1 (Draft — post-exploration, pre-CRP)
**Date:** 2026-06-15
**Status:** Draft — for review before implementation
**Requirements:** [`CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md`](CONCIERGE_DERIVE_CONTRACT_REQUIREMENTS.md) v0.2

> The planning pass read the emitter/IR (`manifest_extraction/`), the navig8 source models
> (`startd8_work.legal`), and the hand-derived `navig8/prisma/schema.prisma`. Verdict: **most of
> the derivation is deterministic and the emit half + drift primitives are reused as-is**; the
> only net-new code is a Pydantic introspector + the IR mapping, and the only *ambiguous* rules
> (M2M joins, pipeline-artifact exclusion) are resolved by an explicit marker + flag-for-human.

---

## 1. Architecture: three layers, two reused

```
[1 NET-NEW]  PydanticModelIntrospector   models → normalized field/enum/relation facts
[2 NET-NEW]  EntityGraph mapper          facts → manifest_extraction.EntityGraph
[3 REUSE  ]  render_prisma_schema(graph) → schema.prisma            (prisma_emitter, unchanged)
[4 REUSE  ]  parity_against_live(graph, live) → drift               (--check, unchanged)
[  SAFE   ]  apply_write_plan / CLI                                 (Concierge safe-writer, OQ-7)
```

The contract direction is reversed from `generate backend`, but the **back half is identical** —
derive-contract feeds the same `EntityGraph` the markdown path feeds, into the same emitter.

## 2. Steps

### Step 1 — `PydanticModelIntrospector` (net-new, ~200 LOC)
Runtime introspection (OQ-2 resolved: AST alone is insufficient — Pydantic needs `model_fields`
for `is_required`/defaults). Per `BaseModel`:
- `model_fields` → name, annotation, required, default;
- unwrap `Optional[T]`/`List[T]`/`Dict[K,V]` via `typing.get_args`/`get_origin`;
- classify each field: scalar / enum (`issubclass(ann, Enum)`) / nested `BaseModel` / `List[BaseModel]`
  / `List[scalar]` / `Dict` / marked-join;
- detect & **drop** `@computed_field`/`@property` (not stored);
- collect `Enum` classes (values, with hyphen→underscore normalization + a note).
**Constraint (new, FR-DC-10):** importing the models executes module code and needs the project's
deps importable — derive-contract runs in an env where the target package imports cleanly; the
report records the import set. Side-effect risk is documented.

### Step 2 — EntityGraph mapper (net-new, ~300 LOC)
Map introspected facts → `EntityGraph` (entities/fields/enums/fk_parents/joins/uniques). The
deterministic rules (verified against navig8):

| Model-side signal | Contract result | Determinism |
|---|---|---|
| explicit `id: str` field present | `<entity>Key` + `@@unique([parentFk, key])` + synth cuid PK | **deterministic** |
| no `id` field | cuid PK only (root/value object: DecisionTree, Citation) | **deterministic** |
| parent has `List[ChildModel]` | child gets `<parent>Id` FK + parent reverse list (1:N) | **deterministic** |
| field is nested `BaseModel` / `Optional[BaseModel]` | `<model>Id` FK (optional mirrors Optional) | **deterministic** |
| `List[scalar]` / `Dict[...]` / nested dict | `Json?` | **deterministic** |
| `@computed_field` / `@property` | excluded (not a column) | **deterministic** |
| Python `Enum` | Prisma `enum`; hyphenated values → underscore + note | **deterministic** |
| `List[str]` of foreign ids (e.g. `screens`) ↔ reciprocal list | **M2M join model** (navig8 `ScreeningLink`) | **NOT deterministic → marker (Step 4) or flag** |
| house meta-fields absent | add `id/ownerId/source/confirmed/createdAt/updatedAt` per SDK convention | deterministic |

### Step 3 — Emit (reuse, ~0 LOC)
`render_prisma_schema(graph)` unchanged. The contract + the derivation report (every rule applied,
every exclusion, every flagged ambiguity — FR-DC-7/8) are the output.

### Step 4 — Ambiguity resolution: explicit markers + flag-for-human
The two NEEDS-ADAPTER cases (OQ-3 M2M, OQ-5 artifact exclusion) get an **opt-in marker** the model
author can set, with **flag-for-human** as the safe default when unmarked:
- M2M join: a `List[str]`-of-ids field is ambiguous (loose refs vs Json vs join) — unmarked ⇒
  emit `Json?` **and flag** "could be an M2M join — mark to confirm"; a marker (e.g. a
  `model_config`/`Field(json_schema_extra=...)` hint, TBD shape — OQ-DC-2) makes it a join.
- exclusion: which models are storage-bearing is the human's call (IntakePacket isn't even in the
  model set) — derive-contract emits **only the model set the user points it at** (Step 6) and
  auto-excludes computed fields; pipeline-artifact name heuristics (`*Verification`, `*Challenge`,
  `*Sceptic`, `*Arbiter`) are **flagged, not auto-dropped**.

### Step 5 — Drift mode `--check` (reuse, ~50 LOC)
Reuse `parity_against_live(graph, live_text)` + the round-trip gate (production primitives in
`prisma_emitter`). `derive-contract --check`: introspect → map → diff against the live
`schema.prisma`, non-zero exit on drift. **This is the durable value of mechanizing F-5** (catch
model↔contract drift over time), so it is a v1 requirement, not an extra.

### Step 6 — Surfaces (reuse the Concierge pattern)
- `handle_concierge_tool("derive-contract", project_root, models=..., ...)` → preview (the
  proposed contract + report), **never writes** (FR-C3/C3a). Add to the action enum in both MCP
  server files (parity).
- CLI `startd8 concierge derive-contract [ROOT] --models <pkg/paths> [--apply] [--force] [--check]`
  — sole writer (OQ-7), preview-by-default, safe-writer enforces no-clobber/confinement.

### Step 7 — Tests
- Introspector unit tests against the navig8 models (`tree_models`/`register_models`/`models`).
- **Golden test: re-derive navig8's contract** and assert it matches the hand-derived
  `schema.prisma` modulo the flagged-ambiguity items (M2M join + the SequenceConfig Json bag).
- Drift test: mutate a model, assert `--check` reports it.
- Disclosure/no-write: the MCP path writes nothing (FR-C3a conformance, as for the other actions).

## 3. Step → Requirement trace

| Step | Requirements |
|------|--------------|
| 1 Introspector | FR-DC-3, FR-DC-2 ($0), FR-DC-10 (importable-env, new) |
| 2 Mapper | FR-DC-4, FR-DC-5 |
| 3 Emit | FR-DC-4, FR-DC-7 |
| 4 Markers/flag | FR-DC-6, FR-DC-8 |
| 5 Drift | FR-DC-11 (--check, promoted from OQ-7) |
| 6 Surfaces | FR-DC-1, FR-C3/C3a/C14, OQ-7 |
| 7 Tests | all |

## 4. Open Questions (for CRP)

- **OQ-DC-1 — Golden-test fidelity.** How close can a re-derivation get to the hand-written navig8
  contract? The flagged items (M2M `ScreeningLink`, the `SequenceConfig` Json bag, house-field
  ordering) won't match byte-for-byte. Is "matches modulo flagged items" the acceptance bar?
- **OQ-DC-2 — Marker shape.** How does a model author mark an M2M join / an excludable artifact —
  a `Field(json_schema_extra={"prisma": ...})`, a `model_config` key, a sidecar YAML, or a
  decorator? (Wants to avoid polluting domain models with contract concerns.)
- **OQ-DC-3 — Import safety.** Runtime import executes the target's module code. Sandbox? subprocess
  isolation? Or document "only point it at code you trust" (consistent with it being the team's own
  models)? Security-relevant — flag for CRP.
- **OQ-DC-4 — Model-set selection ergonomics.** `--models app.models` (package), a glob, or scan
  for `BaseModel` subclasses under a root? Inheritance/imported-model handling.

---

*Plan 0.1 — post-exploration. Net-new surface is bounded (~550 LOC introspector+mapper); emit +
drift + safe-writer are reused. The only non-deterministic derivations (M2M joins, artifact
exclusion) are handled by opt-in markers + flag-for-human, never silent guesses.*
