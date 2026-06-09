# Prisma-Emit Command — Scope & Requirements (FR-PE-7 cutover mechanics → CLI)

**Status:** ✅ IMPLEMENTED (v1, 2026-06-09) — commit `9952aca6` on `origin/main`. Scope v0.1 below;
the one refinement made during the build is folded into §5 FR-EMIT-3 (the promote gate is
round-trip + non-empty, **not** parity-zero — parity drift is the intended change being applied).
**Owner:** startd8-sdk
**Answers:** StartDate `SDK_EMIT_COMMAND_QUERY_2026-06-08.md` (the missing runnable re-emit command)
**Builds on:** `PRISMA_EMITTER_REQUIREMENTS.md` (FR-PE-1…7), `manifest_extraction/prisma_emitter.py`,
`manifest_extraction/extract.py`
**Standing rule:** requirements before implementation — this is the scope, not the build.

---

## 1. BLUF — the gap is CLI-only; the engine already exists

The Prisma emitter shipped end-to-end as an **API** but has **no CLI entry point**, so the first
step of the "edit prose → regenerate" loop is not runnable by the app team. Everything the command
needs already exists and is gated:

| Capability | Function (on `origin/main`) | Status |
|---|---|---|
| Parse requirements doc → `EntityGraph` | `manifest_extraction.entities.extract_entities()` (via `extract.extract_manifests()`) | ✅ exists |
| Render graph → `schema.prisma` text | `prisma_emitter.render_prisma_schema()` (FR-PE-1/2/3) | ✅ exists |
| Round-trip + parity gate | `prisma_emitter.emit_schema_draft()` (FR-PE-6) | ✅ exists |
| Human-triggered flip to project tree | `prisma_emitter.promote_schema()` (FR-PE-7) | ✅ exists |
| Re-derive YAML manifests | `extract.extract_manifests()` | ✅ exists |

**The only missing piece is a `startd8` subcommand that threads these together.** The flip `fe89387`
was done via a direct API/script call — not reproducible from the docs, exactly as StartDate reports.

Estimated effort: **~1 command module (~120 LOC) + 1 header variant + tests.** No engine changes.

## 2. Proposed command — `startd8 generate contract`

Place it in the **`generate`** family (one verb for "$0 deterministic projection"), documenting the
asymmetry: every other `generate` subcommand *reads* `schema.prisma`; this one *produces* it from the
requirements doc. (Rejected alternatives: a new `emit` group — fragments the surface; `wireframe
--promote` — `wireframe` is read-only/advisory by contract.)

```
startd8 generate contract \
    --requirements docs/kickoff/REQUIREMENTS_v0.5-draft.md \   # source of truth (required)
    [--out .startd8/emit/<run>]            \   # run-dir for the gated DRAFT (default: tmp run dir)
    [--live prisma/schema.prisma]          \   # current contract for the parity gate (default: auto-detect)
    [--promote]                            \   # FR-PE-7 explicit flip to prisma/schema.prisma (human-gated)
    [--check]                              \   # gate-only, write nothing (CI); exit 0=ok / 1=drift / 2=error
    [--json]                                   # machine-readable gate result
```

**Default behavior (no `--promote`):** parse → render → `emit_schema_draft(graph, out, live_text=live)`
→ print the `EmitGateResult` (models rendered, round-trips Y/N, parity drift lines, unrenderable
fields) → write the **draft to the run-dir only** (never the project tree). Exit non-zero if the gate
fails (round-trip failure or parity drift), so it is CI-safe.

**`--promote`:** runs the same gate, and **only if `ok`** calls `promote_schema(out, project_path)` —
the explicit, logged flip that archives the prior contract under `_superseded-handauthored/`.
Promotion still requires the operator to type `--promote`, preserving **FR-PE-7** ("no pipeline stage
writes the promoted path"). A failed gate refuses to promote.

This **directly answers their Q1 + Q2:** the gate is built into the emit; `--check` is the separate
CI form; the safe sequence is "emit (gate) → inspect → `--promote`".

## 3. The OQ-PE-4 provenance-header fix (must ship with the command)

`render_prisma_schema` writes the generic `header_standard(...)` which hardcodes:

```
# GENERATED from prisma/schema.prisma — … regenerate via `startd8 generate backend`.
# Source of truth: the Prisma schema.
```

For the *emitted* schema this is **self-referential and wrong** — the source is the requirements doc;
the producer is the emitter, not `generate backend`. **Add a `header_emitted_contract(...)` variant**
(or parameterize `header_standard`) that writes:

```
# GENERATED from <requirements-doc-path> — do not edit by hand; regenerate via
#   `startd8 generate contract --requirements <doc> --promote`.
# startd8-artifact: prisma-schema
# Source of truth: the requirements doc (this schema is derived).
# schema-sha256: <sha>
```

`render_prisma_schema`/`emit_schema_draft` already take `source_file`; the command passes the
requirements-doc path, and the header text must name the **emit command** as the regenerator. This
closes OQ-PE-4 / their Q4 and makes "derived-from-prose vs hand-authored" decidable from the file.

## 4. The full ordered sequence — "added an entity → working app" (their Q3)

The YAML manifests are a **separate extraction** (`extract_manifests`), not part of the schema emit.
The documented loop for an entity change:

```bash
# 1. Edit the requirements doc (add the entity + its nav/completeness/owned-field declarations)
# 2. Re-emit the contract (gated draft → inspect → flip)
startd8 generate contract --requirements docs/kickoff/REQUIREMENTS_v0.5-draft.md          # gate
startd8 generate contract --requirements docs/kickoff/REQUIREMENTS_v0.5-draft.md --promote # flip
# 3. Re-derive the YAML manifests (pages.yaml / completeness.yaml / human_inputs.yaml)
startd8 manifest generate ...        # (existing extract_manifests path — confirm exact invocation)
# 4. Deterministic $0 cascade off the new contract
startd8 generate backend
startd8 generate views
# 5. Migrate + verify
alembic revision --autogenerate && alembic upgrade head
pytest
```

**Open decision (OQ-EMIT-1):** should `generate contract` optionally re-derive the manifests in the
same call (`--with-manifests`) so steps 2–3 are one command? Recommendation: **keep contract-only by
default** (single responsibility, the gate is about the schema), offer `--with-manifests` as a
convenience that runs `extract_manifests` into the same run-dir behind its own gate. With F-13's
opt-in completeness fix already shipped, adding an entity no longer silently shifts the score even if
the manifests lag — so the two steps are decoupled and safe to run separately.

## 5. Functional requirements

- **FR-EMIT-1** Read a requirements doc path, parse to `EntityGraph` via the existing extractor; fail
  loud with the per-entity `ExtractionRecord` reasons if entity blocks are malformed (no silent empty
  graph).
- **FR-EMIT-2** Render + gate via `emit_schema_draft` (round-trip + parity vs `--live`); write the
  draft to the run-dir **only**.
- **FR-EMIT-3** `--promote` flips to the project contract path via `promote_schema`. **Blocking gate
  = round-trip + non-empty** (`models > 0`); a failed round-trip or an empty/malformed doc refuses
  the flip (project contract untouched). **Parity drift is NOT a blocker** — you promote *because*
  the prose changed, so drift is the changeset being **applied** (surfaced as "applying N change(s)
  vs the live contract"). Strict parity-zero is the `--check` gate, not the promote gate. Archive the
  prior contract under `_superseded-handauthored/`.
- **FR-EMIT-4** `--check` computes the gate and writes nothing; exit `0` ok / `1` drift or round-trip
  failure / `2` usage/error. `--json` emits the `EmitGateResult` as JSON for CI.
- **FR-EMIT-5** Emitted schema carries the **requirements-doc provenance header** (§3), not the
  self-referential `generate backend` one.
- **FR-EMIT-6** Auto-detect `--live` from `prisma/schema.prisma` when present; if absent (first
  emit), skip parity and gate on round-trip only.
- **FR-EMIT-7** Print unrenderable fields (types outside the plain vocabulary) as **warnings**, not
  silent drops — the operator must see what the prose declared that the emitter can't render.

## 6. Test plan

- Unit: doc → graph → emit → gate result (round-trips, parity-clean, unrenderable surfaced).
- Gate-refuses-promote: a drifting/round-trip-failing graph with `--promote` does **not** write the
  project path (assert the file is untouched).
- Promote archives: an existing hand-authored contract is moved to `_superseded-handauthored/`.
- Provenance: emitted header names the requirements doc + `generate contract`, carries
  `startd8-artifact: prisma-schema`; **not** "Source of truth: the Prisma schema".
- `--check` exit codes (0/1/2) + `--json` shape.
- End-to-end on the strtd8 fixture: add `ImportedDocument` + `ContentSnippet` to a doc, emit, confirm
  the two models appear and round-trip (their actual blocked change, FR-13/15).

## 7. Open questions

- **OQ-EMIT-1** Manifest re-derivation in the same command? (§4 — recommend `--with-manifests` opt-in)
- **OQ-EMIT-2** Default run-dir location/retention (`.startd8/emit/<ts>`?) and whether `--promote`
  without a prior explicit emit should emit-then-promote in one shot (recommend: yes, it runs the
  gate internally, so a single `--promote` is safe and ergonomic).
- **OQ-EMIT-3** Command name ratification: `generate contract` (recommended) vs `emit contract`.

---

*Answers StartDate's four questions directly: Q1 → `startd8 generate contract --requirements <doc>
[--promote]`; Q2 → the gate is built into the emit, `--check` is the CI form; Q3 → §4 ordered
sequence, manifests are a separate `manifest generate` step (OQ-EMIT-1 may fold them in); Q4 → §3
provenance header fix ships with the command. A first-class subcommand is **recommended and scoped
here** — the loop becomes operable without insider knowledge of how `fe89387` was done.*
