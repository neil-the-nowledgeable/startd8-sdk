# Generated Import Path — Implementation Plan

**Version:** 1.0
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
| 0.2 | **Resolve OQ-IMP-D — name the first consumer** (strtd8 content-import FR-13/15 / navig8 / startd8-generator). Fixes the formats + acceptance entities. |
| 0.3 | Post the **FR-IMP-2 unification proposal** (Phase 1 design below) to the AI-layer owner; agree the seam before touching `ai_layer.py`. |

## Phase 1 — FR-IMP-2: unify the dedup keys into ONE identity key *(foundational; coordinated)*

> Today `AiPass` has `source_binding` (source-scope) **and** `dedup_by` (single-field), each with its
> own persist helper. Collapse to one declared **identity key**, defined once, consumed by the AI
> persist path *and* (Phase 3) the `from_json` path. **Back-compat is the hard constraint.**

| Feature | Target files | Est. LOC | Notes |
|---------|-------------|----------|-------|
| F-101 `IdentityKey` model + resolver | **new** `manifest_extraction/identity.py` (or `backend_codegen/identity.py`) | ~90 | `IdentityKey(kind: id\|field\|composite\|source\|name\|none, fields: tuple, provenance: str\|None)`; `resolve_identity(...)` from manifest + schema. One source of truth. |
| F-102 map `source_binding`/`dedup_by` → `IdentityKey` (back-compat) | `ai_layer.py` (`AiPass`, `parse_ai_passes`) | ~40 | `source_binding` → `source:<field>`; `dedup_by` → `field:<name>`; neither → `name` (today's default). Keys stay accepted; deprecation note only. |
| F-103 single parameterized persist helper | `ai_layer.py` (replace `_persist`/`_persist_source`/`_persist_dedup` shared strings) | ~80 | One emitted `_persist(session, model, edge, *, identity)` dispatching on `IdentityKey.kind`. **Verify byte-identity** of generated harnesses for existing `source_binding`/`dedup_by` passes (the regression gate). |
| F-104 (optional) `identity:` first-class manifest key | `ai_passes.yaml` parse + `imports.yaml` (Phase 2) | ~30 | Lets a pass/import declare `identity:` directly; the legacy keys map onto it. |

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
