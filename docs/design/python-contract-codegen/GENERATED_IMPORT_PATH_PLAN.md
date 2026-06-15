# Generated Import Path — Implementation Plan

**Version:** 1.1 (CRP R1–R4 triaged — see §Post-Review Amendments)
**Date:** 2026-06-15
**Pairs with:** `GENERATED_IMPORT_PATH_REQUIREMENTS.md` v0.3 (FR-IMP-1/2/3/6 + the §0b refresh)
**Base:** `origin/main` (FR-IMP-4/5 + source-scope FR-IMP-2 already shipped)

## Overview

Build the remaining import-path capabilities in dependency order: the **identity-key consolidation
(FR-IMP-2)** and the **`imports.yaml` grammar (FR-IMP-3)** are the two foundations and can run in
parallel; the **`from_json` owned-kind (FR-IMP-1)** consumes both; the **import surface (FR-IMP-6)**
consumes the manifest. The discipline throughout is the FR-PE emitter's: **declare → generate →
fail-loud gate → human-gated write**. The AI-layer surface (`ai_layer.py`) is actively owned by a
parallel team, so Phase 0 front-loads coordination and every phase re-checks `origin/main`.

## Phase 0 — Coordinate + name the consumer *(blocks nothing technical; gates the rest)*

| Step | Action |
|------|--------|
| 0.1 | `git fetch origin main`; branch `feat/import-path` off **current** `origin/main` in a fresh worktree (pin `PYTHONPATH=<wt>/src` for tests — `reference_multiworktree_env`). |
| 0.2 | **OQ-IMP-D RESOLVED (2026-06-15): first consumer = strtd8** (content-import FR-13/15, formats `{json, text}`). Produce `OQ-IMP-D-decision.md` pinning the strtd8 acceptance fixture (§6 map); navig8/generator are later consumers, not blockers. |
| 0.3 | **Seam DECIDED 2026-06-15 (see Phase 1):** "one declaration, mode-specific application." Proceed — land via a coordinated PR onto current `origin/main` and fix follow-on collisions, rather than block on prior sign-off. Notify the AI-layer owner with the PR, not before it. |

## Phase 1 — FR-IMP-2: unify the dedup keys into ONE identity key *(foundational; coordinated)*

> Today `AiPass` emits **four** persist shapes at **two layers**: per-row `_PERSIST_HELPER` (name) +
> `_PERSIST_DEDUP_HELPER` (`dedup_by`); harness-level `_PERSIST_SOURCE_HELPER` (`source_binding`, a
> once-per-run source-scope pre-clear); and the `is_scoped` child-FK `_render_pass_scoped`.

> **SEAM DECISION (2026-06-15): "one declaration, mode-specific application."** A single
> `_persist(..., identity)` cannot swallow all four — `source` dedups at the whole-source layer and
> `scoped` is a child-FK shape, neither per-row. So:
> - **Layer 1 (unified):** one `IdentityKey` declaration + `resolve_identity()` in a new `identity.py`,
>   pure, **no `ai_layer.py` edit**, consumed by the AI persist path *and* the `from_json` path (P3).
> - **Layer 2 (mode-specific):** consolidate ONLY the same-shape per-row helpers (name + `dedup_by`)
>   into one row-level `_persist` dispatching on `kind ∈ {name, field, composite}`.
>   `_PERSIST_SOURCE_HELPER` and `_render_pass_scoped` stay their own emission paths but **read** the
>   same `IdentityKey` — so those harnesses remain **byte-identical** (untouched code).
> - **Back-compat is the hard constraint.** Only the `dedup_by` path is re-expressed through the unified
>   row helper, and its generated output must diff byte-identical too.

| Feature | Sub-phase | Target files | Est. LOC | Notes |
|---------|-----------|-------------|----------|-------|
| F-101 `IdentityKey` model + resolver | **P1a** | **new** `backend_codegen/identity.py` | ~90 | `IdentityKey(kind: id\|field\|composite\|source\|name\|none, fields: tuple, provenance: str\|None)`; `resolve_identity(manifest_entry, schema)`. Pure, unit-tested standalone, **no ai_layer edit** → Phase 3 depends on P1a only. |
| F-102 map `source_binding`/`dedup_by` → `IdentityKey` (back-compat, **3 source states**) | **P1b** | `ai_layer.py` (`AiPass`, `parse_ai_passes`) | ~40 | `dedup_by` → `field:<name>`; **explicit** `source_binding` → `source:<field>`; **schema-derived** binding (`effective_source_binding`, no key) → `source:<derived>`; `source_binding: none` → disabled; only a truly bindingless pass → `name`. Legacy keys stay accepted; deprecation note only. |
| F-103 consolidate the **per-row** helpers only | **P1b** | `ai_layer.py` (merge `_PERSIST_HELPER` + `_PERSIST_DEDUP_HELPER`) | ~60 | One row-level `_persist` dispatching on `kind ∈ {name, field, composite}`. **Leave `_PERSIST_SOURCE_HELPER` + `_render_pass_scoped` untouched.** Byte-identity diff on every existing manifest is the regression gate. |
| F-105 behavioral-parity gate | **P1b** | `tests/test_import_identity.py` (emitted) | ~50 | Exercise confirmed-non-touch / unconfirmed-supersede / source-scope count-stability — byte-identity alone is insufficient (R3-S4). |
| F-104 (optional) `identity:` first-class manifest key | **P1b** | `ai_passes.yaml` parse + `imports.yaml` (Phase 2) | ~30 | Lets a pass/import declare `identity:` directly; legacy keys map onto it. |

**Verify:** existing `source_binding`/`dedup_by` manifests emit **byte-identical** generated code
(diff vs pre-change); new `identity: id|[a,b]|source:f|none` each behave per FR-IMP-2; the
`ai-tests-pass` generated suite stays green. **Dependency:** blocks Phase 3.

## Phase 2 — FR-IMP-3: `imports.yaml` grammar *(paved road; parallel with Phase 1)*

> Clone the FR-PE manifest pattern end-to-end. Lowest-risk phase.

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-201 `## Imports` extractor | `manifest_extraction/extractors.py` (model on `extract_views`) | ~70 | Table → `imports.yaml`; per-row `not_extracted(reason)`; unknown entity/field fails loud. |
| F-202 `parse_imports` strict parser | `import_codegen.py` (new) | ~60 | The round-trip oracle (like `parse_views`). |
| F-203 wire into the round-trip gate | `manifest_extraction/extract.py` (`extract_manifests` round_trips map) | ~15 | `imports.yaml` round-trips through `parse_imports` before return (`RoundTripError` on failure). |
| F-204 authoring-contract doc | `docs/design/kickoff/KICKOFF_AUTHORING_CONTRACT.md` §2.8 | docs | The `## Imports` grammar table (Entity\|Format\|Identity\|Provenance\|Extract via\|Surface). |

**Verify:** a conforming `## Imports` block → valid `imports.yaml` that round-trips; unknown
entity/field → loud; non-conforming row → one `not_extracted` row. **No dependency** (parallel P1).

## Phase 3 — FR-IMP-1: `from_json` owned-kind *(gated importer; needs P1 + P2)*

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-301 `render_import` → `app/import.py` | `import_codegen.py` | ~150 | The inverse of `derived.render_export`: `from_json(text) -> ImportResult`, per-entity loader honouring the Phase-1 `IdentityKey`. |
| F-302 import gate (FR-PE-6 model) | `import_codegen.py` | ~60 | Structured `ImportResult(ok, errors, unrenderable, counts)`; a row violating identity / referencing an undeclared field is **reported, not dropped**; `--strict`/`--allow-lossy`. |
| F-303 drift registration | `backend_codegen/drift.py` (`_renderers`) + headers | ~20 | Register `python-import` owned-kind so `generate backend --check` covers `app/import.py`. |
| F-304 generated contract tests | `backend_codegen/test_emitter.py` | ~40 | `from_json(to_json(payload))` round-trips; idempotent re-load under the identity key. |

**Verify:** round-trip fidelity + idempotency; undeclared-field row reported; `--check` drift clean.
**Dependency:** P1 (identity key) + P2 (manifest).

## Phase 4 — FR-IMP-6: import surface *(needs P2)*

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-401 import route + template | `backend_codegen/htmx_generator.py` (model on `render_ui` form path) | ~90 | When `imports.yaml` declares `surface: true`: a paste textarea + text-file upload → creates the target row; storage independent of extraction. |
| F-402 nav + generated route test | `htmx_generator` + `test_route_smoke_emitter` | ~30 | Route smoke; byte-for-byte stored text round-trip. |

**Verify:** posting pasted text creates one target row whose stored text round-trips; nothing
extracted by the act of importing. **Dependency:** P2.

## Phase 5 — End-to-end on the named consumer

| Step | Action |
|------|--------|
| 5.1 | Author the consumer's `## Imports` block; run `generate backend` (+ the new import owned-kind); `--check` clean. |
| 5.2 | Boot-smoke: import a doc via the surface (P4), restore via `from_json` (P3), and (existing) source-bound extract (FR-IMP-4) — the full FR-13/14/15 loop. |
| 5.3 | Drift `--check` + the generated test suite green; promote per the consumer's flow. |

## Dependencies

```
P0 (coordinate + consumer) ─┬─> P1 (identity consolidation) ─┐
                            └─> P2 (imports.yaml grammar) ────┼─> P3 (from_json gated) ─┐
                                                  P2 ─────────┴─> P4 (import surface) ──┴─> P5 (e2e)
```
P1 ∥ P2 (parallel). P3 needs P1+P2. P4 needs P2.

## Risks & coordination

- **R1 — AI-layer collision (high).** `ai_layer.py` is the parallel team's hot surface; Phase 1
  rewrites its persist helpers. *Mitigation:* Phase 0 proposal + agreement; byte-identity regression
  gate (F-103); land via coordinated PR onto current `origin/main`, not a stale branch.
- **R2 — back-compat regression.** Collapsing two keys risks changing generated output for existing
  passes. *Mitigation:* F-103 byte-identity diff is a hard gate; keep both legacy keys accepted.
- **R3 — consumer drift.** Building FR-IMP-1/6 acceptance without a named consumer risks the wrong
  formats. *Mitigation:* OQ-IMP-D resolved in Phase 0; the grammar (P2) is consumer-agnostic so it can
  proceed regardless.
- **R4 — branch drift / test contamination.** *Mitigation:* fresh worktree off `origin/main`, pin
  `PYTHONPATH`, re-fetch before each phase (`reference_multiworktree_env`).

## Acceptance (whole plan)
1. Existing `source_binding`/`dedup_by` passes: **byte-identical** generated code post-Phase-1.
2. `## Imports` → `imports.yaml` round-trips; loud on unknown entity/field.
3. `from_json(to_json(x))` round-trips + idempotent under the identity key; undeclared-field rows
   reported (not dropped); `--check` drift clean.
4. Import surface stores a pasted doc, round-trips byte-for-byte, extraction-independent.
5. The named consumer's full import→extract→restore loop works end-to-end, $0 generated.

---

## Post-Review Amendments (CRP R1–R4 triaged 2026-06-15)

> All R1–R4 plan suggestions ACCEPTED (Appendix C; dispositions in Appendix A). They materially
> correct the plan — chiefly the **full manifest-wiring path** I under-specified and the **seam
> decomposition** R4 found in code. These amend the phases above and are normative.

**Phase 0 — add an exit artifact** (R1-S5): step 0.2 produces `OQ-IMP-D-decision.md` (named consumer
+ pinned acceptance-fixture path; default **strtd8** §6 if unresolved by the decision date). P5 is
blocked until it exists; P2 is not.

**Phase 1 — split into P1a / P1b and fix the seam** (R1-S2, R4-S1/S2/S3, R3-S4):
- **P1a — `resolve_identity()` (pure, no `ai_layer` edit)** in `import_codegen/identity.py`,
  unit-tested standalone. **P3 depends on P1a only** → FR-IMP-1/3 proceed even if the AI-layer owner
  delays P1b. P1b (persist unification) stays coordinated.
- **F-102 maps the THREE source-binding states** (R4-S1): explicit `source:` / **schema-derived**
  `source:` (`effective_source_binding`, no key) / `none` (disable); only a truly bindingless pass →
  `name`. The "neither ⇒ name" rule is wrong for derived passes.
- **F-103 splits resolve vs apply** (R4-S2): `id/field/composite/name` are per-row `_persist`
  dispatch; **`source` stays the harness-body pre-clear** (`_render_pass_text_bound`). A single
  `_persist(..., identity)` cannot apply a source key — do not collapse it in.
- **Five persist branches, not four** (R4-S3, R1-S1): include/fence `_PERSIST_SCOPED_HELPER`
  (`is_scoped`, `fk_values: dict`) — it has a CHILD-FK shape that does not fit the unified signature.
- **F-105 behavioral-parity gate** (R3-S4): emit `tests/test_import_identity.py` exercising
  confirmed-non-touch / unconfirmed-supersede / source-scope count stability — byte-identity alone is
  insufficient. The byte-identity matrix must add **derived-source, `source_binding: none`, and
  `is_scoped`** cells.

**Phase 2 — cross-ref + extraction guards** (R1-S4, R2-S4, R4-S5, R3-S6):
- `parse_imports` validates `extract_via`→`ai_passes.yaml` pass and `provenance`→`human_inputs.yaml`
  owned field, sourcing names from the **already-extracted candidate dicts** (like `view_prose`'s
  `known_views`); pin gate ordering so `imports.yaml` round-trips **after** those siblings (R4-S5).
- Enforce **OQ-IMP-5** at extraction (R2-S4): `source:` identity + blank Provenance ⇒ `not_extracted`.
- **Prune orphaned templates** (R3-S6): an Entity dropped from schema prunes its row at re-extract.

**NEW Phase 2.5 — Manifest wiring (the path I missed; mirror `views`/`ai_passes`):**
- **F-305 thread `imports_text`** (R2-S1) through `render_backend(..., imports_text=...)`,
  `check_drift`, `owned_file_in_sync`, and the `PydanticSQLModelProvider` reads — else `--check`
  re-renders from schema-only and perpetually false-flags `app/import.py`.
- **Conditional emission** (R2-S2): `assembler.render_backend` gains `if imports_text: render_import`
  (mirror `if manifest_text: render_ai_layer`); absent manifest ⇒ no `app/import.py` (opt-in).
- **F-306 deterministic provider** (R2-S3): register `python-import` on the
  `startd8.contractors.deterministic_providers` entry-point group so the Prime skip-hook recognizes an
  in-sync `app/import.py` at $0.
- **F-307 `main.py` mount** (R3-S1): tolerant `import_router` include in `render_main` (idiom of
  `ai_router`/`editor_routers`) — else every import POST 404s.
- **CLI `--imports`** (R3-S2): `cli_generate.py` backend command reads `prisma/imports.yaml` and
  threads `imports_text` into `render_backend` + `_backend_drift`.
- **Wireframe catalog** (R3-S3, R3-F4): add `imports` → `prisma/imports.yaml` to `wireframe/inputs.py`
  `CONVENTION_PATHS` + a wireframe plan section, and to `ASSEMBLY_INPUTS_TEMPLATE.md`.

**Phase 3 — import is type-faithful + durable** (R2-S5, R4-S4, R1-S3, R4-S6, R3-S5):
- **F-301 reuses `ENTITY_ORDER`/`FIELDS` from `app/export.py`** (not an independent schema walk) and
  embeds an **`imports-sha256`** header (R2-S5); builds a **schema type-coercion table** because
  `to_json` is `default=str`-lossy — coerce datetime/Decimal/int/bool/FK back to their declared types
  (R4-S4).
- **F-302 import-unique semantics**: confirmed-row non-clobber, FK load ordering, and a named
  transaction boundary — per-row/per-entity `session.begin_nested()` savepoint under `--allow-lossy`,
  whole-file rollback under `--strict` (R1-S3, R4-S6).
- **F-302/F-401 surface errors** (R3-S5): generated `from_json(text, *, strict=True)`; the surface
  renders `ImportResult.errors` in the HTMX response, not a silent 302.

**Phase 4 — discoverability** (R2-S6): `surface: true` adds an import nav link via the `build_nav_html`
idiom.

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
| R1-S1 | Five persist branches, not four (scoped helper has child-FK shape) | R1 | §Post-Review → Phase 1 (also R4-S3) | 2026-06-15 |
| R1-S2 | Split Phase 1 into P1a (pure resolver, no ai_layer edit) / P1b (persist unify) so P3 isn't blocked | R1 | §Post-Review → Phase 1 (P1a/P1b) | 2026-06-15 |
| R1-S3 | Import-unique: confirmed-row non-clobber, FK ordering, savepoint boundary | R1 | §Post-Review → Phase 3 (F-302) | 2026-06-15 |
| R1-S4 | `parse_imports` validates cross-manifest refs from already-extracted candidate dicts | R1 | §Post-Review → Phase 2 | 2026-06-15 |
| R1-S5 | Phase 0 emits `OQ-IMP-D-decision.md` exit artifact; blocks P5 not P2 | R1 | §Post-Review → Phase 0 | 2026-06-15 |
| R1-S6 | Assembler conditional-emission wiring is its own work item | R1 | §Post-Review → Phase 2.5 (R2-S2) | 2026-06-15 |
| R2-S1 | Thread `imports_text` through render_backend/check_drift/owned_file_in_sync/provider (F-305) | R2 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R2-S2 | Conditional emission `if imports_text:` mirroring `if manifest_text:` | R2 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R2-S3 | Register `python-import` deterministic provider for $0 skip-hook (F-306) | R2 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R2-S4 | Enforce OQ-IMP-5 (`source:` + blank Provenance ⇒ not_extracted) at extraction | R2 | §Post-Review → Phase 2 | 2026-06-15 |
| R2-S5 | F-301 reuses export `ENTITY_ORDER`/`FIELDS` + embeds `imports-sha256` header | R2 | §Post-Review → Phase 3 | 2026-06-15 |
| R2-S6 | `surface: true` nav link via `build_nav_html` idiom | R2 | §Post-Review → Phase 4 | 2026-06-15 |
| R3-S1 | `main.py` tolerant `import_router` mount (F-307) | R3 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R3-S2 | `cli_generate.py --imports` reads `prisma/imports.yaml`, threads into drift | R3 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R3-S3 | Wireframe catalog: add `imports` to `CONVENTION_PATHS` + plan section + template | R3 | §Post-Review → Phase 2.5 | 2026-06-15 |
| R3-S4 | F-105 behavioral-parity gate (byte-identity insufficient) | R3 | §Post-Review → Phase 1 | 2026-06-15 |
| R3-S5 | Surface renders `ImportResult.errors` (no silent 302); `from_json(strict=True)` | R3 | §Post-Review → Phase 3 | 2026-06-15 |
| R3-S6 | Prune orphaned import templates when Entity dropped at re-extract | R3 | §Post-Review → Phase 2 | 2026-06-15 |
| R4-S1 | F-102 maps THREE source-binding states (explicit/derived/none), not two | R4 | §Post-Review → Phase 1 | 2026-06-15 |
| R4-S2 | F-103 splits resolve (per-row `_persist`) vs apply (`source` stays harness pre-clear) | R4 | §Post-Review → Phase 1 | 2026-06-15 |
| R4-S3 | Fifth scoped persist helper (`is_scoped`, `fk_values`) | R4 | §Post-Review → Phase 1 (= R1-S1) | 2026-06-15 |
| R4-S4 | Schema type-coercion table — `to_json` is `default=str`-lossy | R4 | §Post-Review → Phase 3 (F-301) | 2026-06-15 |
| R4-S5 | Cross-ref validation candidate-ordered; gate `imports.yaml` after siblings | R4 | §Post-Review → Phase 2 | 2026-06-15 |
| R4-S6 | Named transaction boundary: `begin_nested` per-row under `--allow-lossy`, whole-file rollback under `--strict` | R4 | §Post-Review → Phase 3 (F-302) | 2026-06-15 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1–R4 plan suggestions ACCEPTED — well-anchored to shipped code (assembler/provider/cli_generate/wireframe idioms), no conflicts, no over-reach. They corrected the plan's under-specified manifest-wiring path (Phase 2.5) and the resolver/persist seam (R4). Folded into §Post-Review Amendments. | 2026-06-15 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 21:00:00 UTC
- **Scope**: First K2-scoped breadth pass — sponsor focus asks (FR-IMP-2 consolidation, coordination, from_json gate, imports grammar, OQ-IMP-D) + plan↔requirements gaps.

### Sponsor focus — answers (orchestrator triages later)

**Ask 1 — FR-IMP-2 identity-key consolidation (highest stakes)**

- **Summary answer:** Partial — vocabulary is mostly complete but the plan undercounts persist variants and dual-key edge cases; byte-identity is necessary but not sufficient without behavioral parity tests.
- **Rationale:** Shipped `ai_layer.py` emits **four** persist helpers (`_PERSIST_HELPER`, `_PERSIST_DEDUP_HELPER`, `_PERSIST_SOURCE_HELPER`, `_PERSIST_SCOPED_HELPER` at lines 564–732), not three. Consolidation must cover scoped passes and confirmed-aware supersede semantics (FR-8 in `_PERSIST_DEDUP_HELPER`). A pass with explicit `source_binding` takes the bound path and may **never hit** `dedup_by` emission — dual-key manifests need an explicit conflict/priority rule (FR-IMP-2).
- **Assumptions / conditions:** Phase 1 lands on current `origin/main` where FR-IMP-4/5 already shipped; byte-identity gate includes bound + scoped + dedup_by matrix, not only legacy pairs.
- **Suggested improvements:** Add dual-key matrix to Phase 1 Verify; extend F-101 to document confirmed-row policy as part of `IdentityKey` dispatch.

**Ask 2 — Coordination / decouple FR-IMP-2?**

- **Summary answer:** Yes — partial decoupling is wise: land `IdentityKey` + `from_json` consumer in `import_codegen` first; Phase 1 AI-layer rewrite remains coordinated but should not block P2/P4.
- **Rationale:** Plan already parallelizes P1 ∥ P2; R1 mitigation is byte-identity + Phase 0 proposal. **Additional resilience:** F-101 can live in `import_codegen/identity.py` (plan option) so FR-IMP-1 (P3) and FR-IMP-3 (P2) proceed if AI owner delays — `_persist` consolidation becomes an adapter implementing the same resolver interface.
- **Assumptions / conditions:** `import_codegen` resolver and `ai_layer` emit must call the same `resolve_identity()` or tests will diverge.
- **Suggested improvements:** Phase 1 split into P1a (shared resolver + tests, no `ai_layer` edit) and P1b (persist unification, coordinated); P3 depends on P1a only.

**Ask 3 — FR-IMP-1 `from_json` gate discipline**

- **Summary answer:** Partial — FR-PE-6 shape is right; import-specific failures (confirmed-row collision, FK ordering, partial transactions) are not yet specified.
- **Rationale:** FR-IMP-1 (v0.3) mirrors fail-loud reporting, but `_persist` already implements **confirmed-aware** supersede (lines 611–615) while import restore may need **human/confirmed rows never overwritten** — a collision an emit gate doesn't cover. Multi-entity `to_json` payloads need **FK load order** or deferred inserts.
- **Assumptions / conditions:** `ImportResult` reports per-entity errors; `--strict` aborts whole import on any error.
- **Suggested improvements:** Add import-only Verify lines for confirmed-row protection and FK ordering; F-302 documents transaction boundary (per-entity savepoint vs whole-file).

**Ask 4 — FR-IMP-3 `imports.yaml` grammar / cross-manifest coupling**

- **Summary answer:** Mostly yes — columns are right; add **Surface** to requirements §5 table (plan F-204 already has it) and **cross-ref validation** at `parse_imports` time.
- **Rationale:** Requirements §5 authoring table omits **Surface** while emitted YAML shows `surface: true` (FR-IMP-6). Cross-refs (`extract_via`, `provenance` → `human_inputs.yaml`) can drift silently without referential checks — unlike entity names which fail loud.
- **Assumptions / conditions:** `ai_passes.yaml` pass names and `human_inputs.yaml` owned fields are stable within a project commit.
- **Suggested improvements:** F-202 validates `extract_via` pass exists and `provenance` field is owned/server-managed; extraction report row on mismatch.

**Ask 5 — OQ-IMP-D unnamed consumer**

- **Summary answer:** Partial — P2/P4 grammar is safe; P3 acceptance entities and P5 e2e are **not** safe without a named default.
- **Rationale:** Plan Phase 0 step 0.2 names OQ-IMP-D but requirements §4 Open Questions lacks it. R3 says grammar is consumer-agnostic — true for P2 — but F-304 contract tests and Phase 5 need at least a **default consumer fixture** (strtd8 per §6) with written fallback if unresolved by date X.
- **Assumptions / conditions:** strtd8 remains the provisional default named in §6.
- **Suggested improvements:** Add OQ-IMP-D to requirements §4; Phase 0 exit criterion = decision record + pinned acceptance fixture path.

**Executive summary (S/F suggestions)**

- Phase 1 must consolidate **four** persist helpers, not three; dual-key manifests need explicit rules.
- **P1a/P1b split** decouples `IdentityKey` resolver from AI-layer collision.
- `from_json` needs **confirmed-row** + **FK ordering** policies beyond FR-PE-6 emit gate.
- `parse_imports` should validate **cross-manifest** refs (`extract_via`, `provenance`).
- Register `python-import` in **`generate backend`** cascade wiring, not only drift.py.
- OQ-IMP-D needs a requirements §4 entry and Phase 0 decision record.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Extend Phase 1 (F-103) to consolidate **four** persist variants (`_persist`, `_persist_dedup`, `_persist_source`, `_persist_scoped`) and document **dual-key priority** when a pass could set both `source_binding` and `dedup_by`. | Plan Phase 1 names `_persist`/`_persist_source`/`_persist_dedup` only; shipped code also has `_PERSIST_SCOPED_HELPER` (`ai_layer.py:732`). Bound passes bypass `dedup_by` emission — consolidation without a priority matrix risks wrong dispatch. | Phase 1 table + Verify | Matrix test: each helper variant + dual-key manifest maps to one `IdentityKey`; byte-identity per cell |
| R1-S2 | Risks | high | Split Phase 1 into **P1a** (shared `IdentityKey` resolver in `import_codegen/identity.py`, unit-tested, no `ai_layer` edit) and **P1b** (persist unification, coordinated). **P3 depends on P1a only**; P1b gates AI-path parity. | Sponsor ask 2 / R1 mitigation: AI-layer owner rejection should not block `from_json` + `imports.yaml`. Plan already parallelizes P1∥P2 but ties P3 to full P1. | Dependencies diagram + Phase 1 intro | P3 prototype runs with P1a+P2 while P1b is pending; resolver tests green without `ai_layer` diff |
| R1-S3 | Validation | high | F-302: specify **import-only failure modes** in Phase 3 — (a) **confirmed-row collision** (never overwrite `confirmed:true`), (b) **FK load ordering** across entities, (c) **per-entity savepoint** so one bad row does not poison the whole `ImportResult`. | Plan F-302 copies FR-PE-6 emit gate; import writes DB rows with confirmed-aware AI semantics already shipped. Without (a–c), `--strict`/`ImportResult` miss the highest-risk import failures. | Phase 3 F-302 Notes + Verify | Tests: import row matching confirmed key ⇒ reported error, count unchanged; cyclic FK payload ⇒ ordered load or explicit error |
| R1-S4 | Validation | medium | F-202 `parse_imports`: add **cross-manifest referential checks** — `extract_via` must name an existing `ai_passes.yaml` pass; `provenance` must appear in `human_inputs.yaml` as owned/server-managed; mismatch ⇒ loud parse error (not runtime). | FR-IMP-3 cross-refs `human_inputs.yaml` + `ai_passes.yaml` by name; entity unknown is loud, but pass/field drift is silent until extract runs. | Phase 2 F-202 Notes | Fixture: `extract_via: missing-pass` ⇒ `parse_imports` raises; valid cross-refs pass |
| R1-S5 | Ops | medium | Phase 0 step 0.2: add **exit artifact** — `OQ-IMP-D-decision.md` naming consumer + pinned acceptance fixture (default strtd8 §6 if unresolved by decision date). P5 blocked until artifact exists. | Plan lists OQ-IMP-D in Phase 0 but requirements §4 omits it; R3 allows P2 without consumer but F-304/P5 need entity/format targets. | Phase 0 table + Acceptance §5 | Phase 5 cannot start without decision file; fixture path referenced in F-304 tests |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S6 | Interfaces | low | F-303: register `render_import` in the **`generate backend` assembler** (alongside `render_export` in `derived.py:297`), not only `drift.py` — otherwise `app/import.py` never emits on standard cascade. | F-303 only mentions `drift.py` `_renderers`; export is wired in assembler. Import-only drift registration would require a separate command users won't run — end-user value gap. | Phase 3 F-303 | `generate backend` on fixture with `imports.yaml` writes `app/import.py`; `--check` clean |

**Endorsements:** none — first round.

**Disagreements:** none.

#### Review Round R2 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 22:30:00 UTC
- **Scope**: Second-order gaps — manifest threading through assembler/drift/provider, conditional emission, OQ-IMP-5 at extraction, export↔import field-order contract, surface upload safety, nav discoverability.

**Executive summary**

- `imports.yaml` must thread like `ai_passes.yaml` / `views.yaml` (assembler + drift + skip-hook), not only `_renderers`.
- Emit `app/import.py` **only when** `imports.yaml` is present — mirror `if manifest_text:` / `render_editors` pattern.
- Register a **`python-import` deterministic provider** so Prime Contractor recognizes `$0` import files.
- Enforce **OQ-IMP-5** at `## Imports` extraction, not only at runtime.
- `from_json` should **import `ENTITY_ORDER` / `FIELDS` from `export.py`** — single round-trip contract.
- FR-IMP-6 surface needs **UTF-8 / binary-reject / size cap** for paste+upload.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Thread **`imports_text`** through the full manifest-derived path: `render_backend(..., imports_text=...)`, `check_drift`, `owned_file_in_sync`, and `PydanticSQLModelProvider._read_*` — same pattern as `views_text` / `manifest_text` (FR-ED-16). F-303 drift re-render must receive `imports.yaml` or `app/import.py` false-flags stale. | R1-S6 covers assembler emission; without manifest threading, `--check` re-renders import from schema-only → perpetual drift or silent LLM fall-through on a clean `$0` file (`provider.py:35-48`, `drift.py:334-377`). | Phase 3 F-303 + new F-305 manifest threading | Fixture: change `imports.yaml` identity column → `--check` reports stale; provider `is_in_sync` True when imports match |
| R2-S2 | Architecture | medium | **Conditional emission:** extend `assembler.render_backend` with `if imports_text:` → `render_import(...)` (mirror `if manifest_text: render_ai_layer`, `assembler.py:113-119`). Absent `imports.yaml` ⇒ **no** `app/import.py` on disk — not an empty stub. | Export always emits (`render_derived` unconditional); import is manifest-gated like AI layer. Unconditional emission would drift-check a file most projects never authored. | Phase 3 F-301 + assembler | Project without `## Imports` ⇒ `generate backend` writes no `app/import.py`; with manifest ⇒ file appears |
| R2-S3 | Ops | medium | Add **F-306**: register `python-import` on `startd8.contractors.deterministic_providers` entry-point group (`pyproject.toml`, model `CompositeViewProvider`) so Prime Contractor skip-hook recognizes in-sync `app/import.py` at `$0.00`. | Five providers registered today (`pyproject.toml:171-176`); drift-only registration (F-303) does not wire skip-hook — generated import files would fall through to LLM on regen batches. | New Phase 3 row F-306 | Prime workflow lists `app/import.py` as GENERATED/$0 when in-sync |
| R2-S4 | Validation | medium | F-201 extractor: enforce **OQ-IMP-5** at extraction — row with `identity: source:<field>` and blank **Provenance** ⇒ `not_extracted(source-identity-requires-provenance)` (loud), not deferred to Phase 3. | Requirements §4 OQ-IMP-5 leans fail-loud at extraction; plan F-201 only lists unknown entity/field. Runtime failure is late and user-opaque. | Phase 2 F-201 Notes + Verify | Fixture: `source:` identity + empty Provenance ⇒ extraction report row, no `imports.yaml` entry |
| R2-S5 | Interfaces | medium | F-301 `render_import`: generated `app/import.py` **imports `ENTITY_ORDER` and `FIELDS` from `.export`** (or shared `_derived_constants` module) — do not re-derive entity order independently. Header embeds **`imports-sha256`** (like `passes-sha256` on AI artifacts) for drift. | `render_export` bakes `ENTITY_ORDER` + `FIELDS` (`derived.py:55-56`); independent derivation risks import/export field-order skew on schema change. Triple-hash pattern proven on AI layer (`drift.py:214-223`). | Phase 3 F-301 Notes | Contract test: reorder schema models ⇒ import still uses export's `ENTITY_ORDER`; imports.yaml change ⇒ header hash stale |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S6 | Interfaces | low | F-401: wire **nav discoverability** — when any template has `surface: true`, add import route link(s) to `base.html` nav (same idiom as `build_nav_html` for `pages.yaml`, `htmx_generator.py:182-191`). End users cannot find paste/upload without nav. | Phase 4 emits route + template but no nav entry; CRUD list is not an import affordance. strtd8 FR-13 needs discoverable paste/upload. | Phase 4 F-401 + F-402 | Route smoke: nav contains import href; GET returns 200 |

**Endorsements** (untriaged R1 — raise triage priority):

- R1-S1 (four persist helpers + dual-key matrix), R1-S2 (P1a/P1b split), R1-S3 (confirmed-row / FK / savepoint), R1-S4 (cross-manifest parse validation), R1-S5 (OQ-IMP-D decision artifact), R1-S6 (assembler wiring).

**Disagreements:** none.

#### Review Round R3 — composer-2.5 — 2026-06-15

- **Reviewer**: composer-2.5
- **Date**: 2026-06-15 23:45:00 UTC
- **Scope**: Third-order / integration pass — CLI + wireframe cascade visibility, `main.py` router mount, behavioral parity beyond byte-identity, restore row stamping, assembly-inputs catalog, import-template pruning.

**Executive summary**

- `generate backend` CLI must read and thread `imports.yaml` (today it reads six manifests, not seven).
- Wireframe / assembly-inputs catalog should surface the import path pre-generation (operational quick win).
- `app/main.py` needs a tolerant **`import_router` mount** like `ai_router` / `editor_routers`.
- F-103 byte-identity is insufficient without a **behavioral parity** generated test suite.
- `from_json` restore must define **`source`/`confirmed` stamping** and **`identity: id` upsert** semantics.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | high | **F-307 `main.py` mount:** extend `render_main` (`crud_generator.py:252-301`) with a tolerant optional `from .import_routes import import_router` + `app.include_router(import_router)` block — same idiom as `ai_router`, `editor_routers`, `flow_routers`. Phase 4 routes are unreachable without it. | F-401 emits route + template but plan never names `main.py` wiring; AI layer required the same F-9 mount fix (`test_emitter.py:442-457`). Import surface would 404 on every POST. | Phase 4 new F-307 + Phase 3 aggregator | `test_import_routes_mounted_if_import_present`: POST import route ≠ 404 when `imports.yaml` present |
| R3-S2 | Ops | medium | **`cli_generate.py` backend command:** add `--imports` / convention read of `prisma/imports.yaml`, thread `imports_text` into `render_backend` and `_backend_drift` (today `_reads` loop covers six manifests only, `cli_generate.py:214-236`). | R2-S1 names assembler/drift threading; CLI is the user entrypoint — without it, `startd8 generate backend` never passes the manifest even after assembler support lands. | Phase 3 (CLI wiring note) + F-305 | `generate backend` on fixture with `imports.yaml` writes `app/import.py`; `--check` passes |
| R3-S3 | Ops | medium | **Wireframe + assembly-inputs:** add catalog key `imports` → `prisma/imports.yaml` to `wireframe/inputs.py` `CONVENTION_PATHS` and a wireframe plan section (import templates count, surface flags, formats) — mirror `ai_passes` / export endpoints visibility (`wireframe/plan.py:430-431`). | End users run `startd8 wireframe` before cascade; import path is invisible today (seven manifests, no imports). Low-effort discoverability before Phase 3 ships. | Phase 2 F-204 cross-ref + new Phase 0.4 wireframe row | Wireframe JSON lists `imports` section with template count when manifest present |
| R3-S4 | Validation | high | **F-103 behavioral parity gate:** alongside byte-identity diff, emit `tests/test_import_identity.py` (owned kind) exercising post-consolidation **semantics** — confirmed-row non-touch, unconfirmed supersede, source-scope count stability — not just harness text diff. R1 sponsor ask 1 flagged byte-identity alone as insufficient. | F-103 Verify is byte-identical only; a refactor could pass diff while breaking FR-8 confirmed-aware supersede (`ai_layer.py:590-615`). AI path already has `test_ai_passes.py`; import identity shares the seam. | Phase 1 Verify + new F-105 generated tests | Behavioral tests fail if confirmed row clobbered or source-scope count grows on re-run |
| R3-S5 | Interfaces | medium | **F-302 CLI + surface errors:** generated `app/import.py` exposes `from_json(text, *, strict=True)` and documents `--strict`/`--allow-lossy` in module docstring; F-401 import surface renders `ImportResult.errors` in the HTMX response (not silent 302). End-user value: paste failure shows *why*. | F-302 names switches but not generated CLI/API surface; FR-IMP-6 Verify says row created but not error display on bad paste. FR-PE promote gate is the model. | Phase 3 F-302 + Phase 4 F-401 | Bad JSON paste ⇒ 422/400 with structured error list in HTML; `--strict` aborts on first error |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S6 | Data | low | **F-203 prune orphaned templates:** when an import template's **Entity** is dropped from schema between extractions, prune its `imports.yaml` row (mirror `view_prose.yaml` pruning against surviving `views.yaml` names, `extract.py:166-172`). Prevents round-trip failure with confusing "unknown entity" at generate time. | F-201 loud-fails unknown entity at extraction time, but schema shrink between runs can leave stale YAML on disk until manual regen. Prune-at-extract is the established pattern. | Phase 2 F-203 Notes | Remove model from schema ⇒ re-extract drops import row; round-trip still passes |

**Endorsements** (untriaged R2 — raise triage priority):

- R2-S1 (imports_text threading), R2-S2 (conditional emission), R2-S3 (deterministic provider), R2-S4 (OQ-IMP-5 at extraction), R2-S5 (ENTITY_ORDER/FIELDS reuse), R2-S6 (nav discoverability).

**Disagreements:** none.

#### Review Round R4 — claude-opus-4-8 — 2026-06-15

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-15 12:31:00 UTC
- **Scope**: Code-grounded deep pass on Phase 1 (the consolidation seam) — the derived `source_binding` state, the harness-vs-persist layering of source-scope idempotency, the `to_json` type-coercion gap feeding Phase 3, and round-trip-gate ordering for Phase 2 cross-refs. Read `ai_layer.py`/`derived.py`/`extract.py` on `feat/import-path`. composer-2.5 (R1–R3) covered breadth well; R4 deepens the two highest-stakes phases.

### Sponsor focus — answers (orchestrator triages later)

**Ask 1 — FR-IMP-2 vocabulary completeness & seam**

- **Summary answer:** No — the vocabulary is incomplete (it omits the **derived** source-binding state) AND the seam is two-layered, so one `_persist(..., identity)` helper will leak. Byte-identity over declared-key manifests is necessary but insufficient.
- **Rationale:** `effective_source_binding` (`ai_layer.py:312-339`) resolves binding three ways — explicit, **schema-derived (zero authored config)**, and `none` (DISABLE sentinel). F-102's map ("neither key ⇒ `name`") silently mis-maps a derived-source pass to name-dedup. Separately, source-scope idempotency is a **harness-body** pre-clear (`_render_pass_text_bound`, `ai_layer.py:706-716`), not a `_persist*` concern — so the unified persist signature in F-103 (`_persist(session, model, edge, *, identity)`) cannot apply a `source` key. There are also **five** persist branches, not four: `_PERSIST_SCOPED_HELPER` (`ai_layer.py:732`, `is_scoped` dispatch at 646) takes `fk_values: dict` (relational CHILD), which does not fit the proposed signature.
- **Assumptions / conditions:** Phase 1 lands on `feat/import-path` (= `origin/main`); the F-103 byte-identity matrix must add derived-source, scoped, and `source_binding: none` cells, not only declared `source_binding`/`dedup_by`.
- **Suggested improvements:** Split F-103's helper into (i) a pure `resolve_identity()` and (ii) per-kind apply paths where `source` stays a harness pre-clear; extend the back-compat map to the three-valued binding; document scoped-pass scope (in or fenced).

**Ask 3 — FR-IMP-1 import-unique failure modes**

- **Summary answer:** Partial — composer-2.5 caught confirmed-row/FK ordering; the missed one is **type-lossy `to_json`**. `from_json` must re-coerce.
- **Rationale:** `render_export` uses `json.dumps(..., default=str)` (`derived.py:60`) — datetimes/Decimals/ints/FKs land as strings. A naive `from_json` echo round-trips textually but corrupts typed columns; FR-IMP-1's "field fidelity (sorted-key stable)" Verify passes on a string-only echo. Also: `--allow-lossy` transaction boundary (per-row savepoint vs whole-file) is undefined.
- **Assumptions / conditions:** import reuses `FIELDS`+schema types (cf. R2-S5) for the coercion table.
- **Suggested improvements:** F-301 builds a per-field coercion table from the schema; F-302 names the `--allow-lossy` commit boundary (reuse `session.begin_nested()`, `ai_layer.py:721`).

**Ask 4 — FR-IMP-3 cross-ref coupling / ordering**

- **Summary answer:** Mostly yes, with an ordering caveat the prose review missed.
- **Rationale:** The round-trip gate iterates `candidates.items()` with **no dependency ordering** (`extract.py:200-214`); cross-ref validation must read sibling names from the **candidate dict**, as `view_prose.yaml` reads `known_views` from the views candidate (`extract.py:191-196`). `imports.yaml` must round-trip *after* `ai_passes.yaml`/`human_inputs.yaml`.
- **Suggested improvements:** F-202/F-203 source `extract_via`/`provenance` validity from the candidate manifests and pin gate ordering.

**Executive summary**

- F-102/F-103 miss the **derived** `source_binding` state — a no-key pass that today binds to source would be silently re-mapped to `name` (R4-S1).
- The consolidation seam is **two-layered**: source-scope idempotency lives in the harness body, not `_persist` — a single `_persist(..., identity)` cannot express it (R4-S2).
- There are **five** persist branches, not four: `_PERSIST_SCOPED_HELPER` (`fk_values` child) is unaddressed by F-103 (R4-S3).
- Phase 3 needs a **schema type-coercion** step because `to_json` is `default=str`-lossy (R4-S4).
- Phase 2 cross-ref validation must respect **candidate ordering** in the round-trip gate (R4-S5).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Architecture | high | **F-102: map the THREE source-binding states, not two.** Extend F-102: `source_binding` → `source:<field>` (explicit); **a schema-derived binding** (no key, single loose-ref provenance field via `effective_source_binding`) → `source:<derived-field>`; `source_binding: none` → no-bind; only a truly bindingless pass → `name`. The "neither ⇒ `name`" rule is wrong for derived passes. | `effective_source_binding` (`ai_layer.py:328-336`) derives a `source` binding with zero authored config; F-102 ("neither ⇒ `name`") would silently flip such a pass to name-dedup. Byte-identity over declared-key manifests never exercises the derived path. | Phase 1 F-102 Notes + Verify | Matrix cell: pass with one server-managed optional-String loose-ref field, no `source_binding` key ⇒ `IdentityKey.kind==source`, byte-identical harness; `source_binding: none` ⇒ no-bind |
| R4-S2 | Architecture | high | **F-103: do NOT collapse source-scope into `_persist`.** Split F-103 into `resolve_identity()` (pure, shared) + a per-kind **apply** layer where `id/field/composite/name` are per-row `_persist` dispatch but `source` stays the harness-body pre-clear (`select(prov==source_id, confirmed.is_(False))`+delete). A single `_persist(session, model, edge, *, identity)` cannot express a per-run source clear. | Source-scope idempotency is harness-level (`_render_pass_text_bound`, `ai_layer.py:706-716`), not in any `_persist*`. The focus ask-1 "one abstraction will leak" is confirmed in code: source is a per-run concern, the others per-row. | Phase 1 F-103 Notes (split into F-103a resolver / F-103b apply) | Generated source-bound harness still emits the pre-clear loop byte-identically; resolver unit-tested independent of `ai_layer` |
| R4-S3 | Risks | medium | **F-103: account for the FIFTH persist branch (`_PERSIST_SCOPED_HELPER`).** State whether `is_scoped` (FR-SRP) relational-child passes are in the identity-key unification or fenced out. The scoped helper takes `fk_values: dict` + `prov_field` (`ai_layer.py:732`) — it does not fit `_persist(..., identity)`. | Plan/R1-S1 enumerate four helpers; `_PERSIST_SCOPED_HELPER` (`is_scoped` dispatch, `ai_layer.py:646-648`) is a fifth with a CHILD-FK shape. Silent exclusion or a leaky merge both regress FR-SRP. | Phase 1 F-103 table | Byte-identity matrix includes an `is_scoped` pass; it keeps its own emit path or maps to a documented variant |
| R4-S4 | Data | high | **F-301: emit a schema-driven type-coercion table; `to_json` is `default=str`-lossy.** `render_import` must coerce each field back to its declared schema type (datetime/Decimal/int/bool/FK) on load, built from the same `FIELDS`+schema the export uses — not write strings back verbatim. | `derived.py:60` serializes with `default=str`; a naive `from_json` echo corrupts typed columns while passing a string-fidelity round-trip. This is the import-unique fidelity failure the emit gate has no analog for. | Phase 3 F-301 Notes + F-304 | Contract test: entity with `DateTime`/`Int`/`Decimal` ⇒ `from_json(to_json(rows))` equal by value AND type |
| R4-S5 | Interfaces | medium | **F-202/F-203: cross-ref validation reads sibling CANDIDATES with pinned gate ordering.** `parse_imports` must validate `extract_via`/`provenance` against the extracted `ai_passes.yaml`/`human_inputs.yaml` **candidate dicts** (as `view_prose.yaml` reads `known_views` from the views candidate, `extract.py:191-196`), and `imports.yaml` must round-trip AFTER those siblings in the gate (no current ordering guarantee). | The round-trip gate iterates `candidates.items()` unordered (`extract.py:200-214`); a cross-ref read before the sibling candidate is built false-passes or KeyErrors. R1-S4 named the validation but not the ordering/source-of-truth. | Phase 2 F-202/F-203 Notes | Fixture: gate validates `extract_via` regardless of extraction order; unknown pass ⇒ loud `RoundTripError`/report row |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S6 | Validation | medium | **F-302: name the `--allow-lossy` transaction boundary; reuse `begin_nested()`.** Specify per-entity/per-row savepoint so a skipped bad row commits its neighbours under `--allow-lossy` and `--strict` rolls the whole file — reuse the shipped `session.begin_nested()` row-isolation idiom (`ai_layer.py:721`) rather than inventing one. | F-302 names the switches but not durability of a partial import; the bound harness already isolates per-row writes — the importer should mirror it for consistent semantics. | Phase 3 F-302 Notes + Verify | 3-row payload, row 2 invalid: `--allow-lossy` commits 1,3 + reports 2; `--strict` commits nothing |

**Endorsements** (untriaged R1–R3 — raise triage priority):

- R1-S1 (four persist helpers — R4-S3 adds the fifth, scoped), R1-S2 (P1a/P1b split — complements R4-S2's resolver/apply split), R1-S3 (confirmed-row/FK/savepoint — R4-S6 names the boundary), R1-S4 (cross-manifest validation — R4-S5 adds ordering), R1-S6/R2-S1 (assembler + manifest threading), R2-S2 (conditional emission), R2-S3 (deterministic provider), R2-S5 (ENTITY_ORDER/FIELDS reuse — R4-S4 extends to type coercion), R3-S1 (main.py mount), R3-S4 (behavioral parity beyond byte-identity).

**Disagreements:** none — R4 deepens R1-S1/R1-S3/R2-S5 in code rather than disputing any prior item.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-IMP-1 (`from_json` gated importer, `ImportResult`, idempotency) | Phase 3 (F-301–F-304) | Partial | Confirmed-row non-clobber and FK load ordering not in F-302 (R1-S3, R1-F2, R1-F3); per-entity savepoint boundary unspecified. |
| FR-IMP-2 (identity-key consolidation, back-compat) | Phase 1 (F-101–F-104) | Partial | Plan names three persist helpers; shipped code has four (`_persist_scoped`) (R1-S1); dual-key priority when both `source_binding` and `dedup_by` set undefined (R1-F1); P1a/P1b decoupling not in dependency diagram (R1-S2). |
| FR-IMP-3 (`imports.yaml` grammar, round-trip) | Phase 2 (F-201–F-204) | Partial | Cross-manifest ref validation (`extract_via`, `provenance`) not in F-202 (R1-S4, R1-F4); Surface column in plan F-204 but missing from requirements §5 table (R1-F6). |
| FR-IMP-4 (source-bound extract) | (shipped) | Full | Already on `origin/main`; out of scope for remaining phases. |
| FR-IMP-5 (provenance stamping) | (shipped) | Full | Already on `origin/main`; out of scope for remaining phases. |
| FR-IMP-6 (import surface, extraction-independent) | Phase 4 (F-401–F-402) | Full | — |
| §0b refresh (emitter discipline) | Phases 2–3 | Full | FR-PE-6 model referenced in F-302; import-unique failures need extension (R1-S3). |
| OQ-IMP-D (first consumer) | Phase 0 step 0.2 | Partial | Plan names step; requirements §4 lacks entry; no exit artifact / fixture pin (R1-S5, R1-F5). |
| Cascade wiring (`generate backend`) | F-303 only | Partial | Drift registration only; assembler wiring for `render_import` missing (R1-S6). |

---

## Requirements Coverage Matrix — R2

Analysis only (not triaged). Second pass — manifest threading, conditional emission, extraction guards, export contract.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-IMP-1 (`from_json` gated importer) | Phase 3 (F-301–F-304) | Partial | R1 gaps remain; plus no `ENTITY_ORDER`/`FIELDS` reuse from export (R2-S5); no `imports-sha256` header (R2-S5); text-format acceptance not in F-304 (R2-F5). |
| FR-IMP-2 (identity-key consolidation) | Phase 1 (F-101–F-104) | Partial | R1 gaps remain; OQ-IMP-1 verbatim composite compare not in Phase 1 Verify (R2-F6). |
| FR-IMP-3 (`imports.yaml` grammar) | Phase 2 (F-201–F-204) | Partial | R1 gaps remain; OQ-IMP-5 not enforced at F-201 extraction (R2-S4, R2-F2); duplicate-entity-row policy undefined (R2-F4). |
| FR-IMP-4/5 (shipped) | (shipped) | Full | — |
| FR-IMP-6 (import surface) | Phase 4 (F-401–F-402) | Partial | No nav discoverability (R2-S6); no upload safety constraints in plan (R2-F3). |
| Manifest threading / skip-hook | F-303 only | Gap | `imports_text` not threaded through assembler/drift/provider (R2-S1); no deterministic provider entry (R2-S3). |
| Conditional ownership | (none) | Gap | Unconditional `app/import.py` emission not ruled out (R2-S2, R2-F7). |
| OQ-IMP-D | Phase 0 step 0.2 | Partial | R1 gaps remain. |
| OQ-IMP-5 | Requirements §4 only | Partial | Not wired into plan Phase 2 Verify (R2-S4). |

---

## Requirements Coverage Matrix — R3

Analysis only (not triaged). Third pass — CLI/wireframe integration, routing, behavioral tests, restore semantics.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-IMP-1 (`from_json` gated importer) | Phase 3 (F-301–F-304) | Partial | R1–R2 gaps remain; restore `source`/`confirmed` stamping undefined (R3-F1); `identity: id` upsert unspecified (R3-F2); CLI not wired (R3-S2); error display on surface missing (R3-S5). |
| FR-IMP-2 (identity-key consolidation) | Phase 1 (F-101–F-104) | Partial | R1–R2 gaps remain; behavioral parity beyond byte-identity not in Verify (R3-S4). |
| FR-IMP-3 (`imports.yaml` grammar) | Phase 2 (F-201–F-204) | Partial | R1–R2 gaps remain; stale-template prune on schema shrink not specified (R3-S6); assembly-inputs catalog missing (R3-F4). |
| FR-IMP-4/5 (shipped) | (shipped) | Full | — |
| FR-IMP-6 (import surface) | Phase 4 (F-401–F-402) | Partial | R2 gaps remain; `main.py` mount missing (R3-S1); CSRF not specified (R3-F3); import errors not surfaced to user (R3-S5). |
| CLI / wireframe ops | (none) | Gap | `cli_generate.py` does not read `imports.yaml` (R3-S2); wireframe invisible (R3-S3). |
| Phase 5 e2e loop | Phase 5 step 5.2 | Partial | Auto-extract on import not ruled out in plan prose (R3-F5). |
| OQ-IMP-C (coexistence) | (none) | Missing | No plan/requirements guidance when app has bespoke restore + generated `from_json` (R3-F6). |

---

## Requirements Coverage Matrix — R4

Analysis only (not triaged). Fourth pass — code-grounded depth on the Phase-1 consolidation seam and Phase-3 round-trip fidelity. Verified against `ai_layer.py`/`derived.py`/`extract.py` on `feat/import-path`.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-IMP-1 (`from_json` gated importer) | Phase 3 (F-301–F-304) | Partial | R1–R3 gaps remain; **type-coercion** missing — `to_json` is `default=str`-lossy so string-fidelity round-trip corrupts typed columns (R4-S4, R4-F2); `--allow-lossy` transaction boundary undefined (R4-S6, R4-F6). |
| FR-IMP-2 (identity-key consolidation) | Phase 1 (F-101–F-104) | Partial | R1–R3 gaps remain; **derived** `source_binding` state unmapped — F-102 "neither ⇒ name" mis-maps schema-derived source passes (R4-S1, R4-F1); seam is two-layered, source-scope is harness-level not `_persist` (R4-S2, R4-F3); fifth persist branch `_PERSIST_SCOPED_HELPER` unaddressed (R4-S3, R4-F4). |
| FR-IMP-3 (`imports.yaml` grammar) | Phase 2 (F-201–F-204) | Partial | R1–R3 gaps remain; cross-ref validation must read sibling **candidate dicts** with pinned gate ordering — round-trip gate iterates `candidates.items()` unordered (R4-S5, R4-F5). |
| FR-IMP-4/5 (shipped) | (shipped) | Full | — |
| FR-IMP-6 (import surface) | Phase 4 (F-401–F-402) | Partial | R2–R3 gaps remain; no new R4 plan gap. |
| OQ-IMP-1 (composite normalization) | §4 / Phase 1 Verify | Partial | Comparand must be the coerced typed value, not the JSON string repr (R4-F7, interacts with R4-S4). |
| Phase 1 byte-identity gate | Phase 1 Verify | Partial | Matrix must add derived-source, `source_binding: none`, and `is_scoped` cells — declared `source_binding`/`dedup_by` pairs alone do not cover the dispatch space (R4-S1, R4-S3). |
