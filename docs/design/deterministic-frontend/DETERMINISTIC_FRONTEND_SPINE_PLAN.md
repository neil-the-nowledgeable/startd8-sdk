# Deterministic Frontend SPINE Generation — Implementation Plan

> **⚠️ SUPERSEDED (2026-06-02) — do not implement as written.** The TS-Next-specific "spine"
> (route-handler generator, etc.) is deprioritized: the SDK is re-anchoring on **polyglot
> microservices** (online-boutique style), and a TS-monolith frontend generator would be narrow
> tech debt. **What survives is the PATTERN, not these TS templates** — deterministic
> schema/contract→code generation + the owned-file skip-hook + the by-construction verification
> gate — now generalized in **`DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`**. Kept for historical
> reasoning and the reflective-requirements §0 record. Do not execute the tasks below.

**Version:** 1.0 (pairs with `DETERMINISTIC_FRONTEND_SPINE_REQUIREMENTS.md` v0.2)
**Date:** 2026-06-02
**Status:** Draft for review

> Generalize the proven `value-model.ts` renderer to the deterministic spine: a **declared
> manifest** + the Prisma schema drive string-template generators for owned artifacts (routes,
> input schemas, db, completeness, export, tool-schemas), each verified by the live whole-project
> `tsc` gate + import-resolution checks. Reuse every existing primitive; the only net-new pieces
> are the manifest model, the route/input/export/completeness templates, and the conventions
> extension. No LLM anywhere.

---

## 0. Planning discoveries (the centerpiece — fed REQUIREMENTS §0)

| What the requirements assumed | What planning (vs strtd8's real 24 routes) revealed |
|-------------------------------|------------------------------------------------------|
| Routes derive from the schema (12 models) | **24 routes ≠ 12 models** — CRUD pairs + 8 AI-trigger + action routes + **duplicate** `ai/enrich-*` vs `enrich/*`. Needs a **declared manifest** (FR-10). |
| `NextResponse` idiom | strtd8 uses Web **`Response.json`** — convention detection must capture it (FR-9). |
| POST validates the entity schema | real POST uses an **input schema** (omit server fields; `*Ids` link arrays) — FR-3. |
| db.ts + migrations are files | migrations are a **`prisma migrate` toolchain step**, not a file — FR-6 split. |
| Completeness = pure fn from signals | pure over a **counts object**; counts need DB queries — FR-4 = `computeCompleteness(counts)` + thin query. |
| Export fully deterministic | JSON yes; **MD needs a declared layout** — FR-5. |
| String-vs-AST templating open | **string templates** suffice (the `render_zod_schema` proof) + tsc/import gates. |
| Verify via symmetry gate | symmetry is schema-specific; routes/db/export verify via **tsc gate + import checks** — FR-11. |

---

## 1. Key seams (reuse vs new)

| Seam | Location | Role |
|------|----------|------|
| Prisma parse + field model | `prisma_parser`, `project_knowledge.FieldSpec/FieldSetAuthority` | **reuse** — one field-set projection (FR-13) |
| Schema/tool-schema render | `frontend_codegen.render_zod_schema` | **reuse** for value-model + tool schemas + input-variant base |
| Convention detection | `frontend_codegen.conventions.detect_project_conventions` | **extend** — add response idiom + api-route layout (FR-9) |
| Owned/skeleton model | `frontend_codegen.skeleton` | **extend** — owned route/db/completeness/export artifacts |
| Gates | `frontend_codegen.gates` (symmetry+fidelity) + `validators.ts_toolchain.run_project_typecheck` + `cross_file_imports.{scan_unresolvable_imports,scan_missing_dependencies}` | **reuse/generalize** for owned-artifact verification (FR-11) |
| Drift / skip-hook | `frontend_codegen.drift.owned_file_in_sync` + `prime_contractor._try_deterministic_file_shortcut` | **reuse** — recognizes all owned spine files |
| **NEW** | `frontend_codegen/manifest.py` | the declared codegen spec (FR-10) |
| **NEW** | `frontend_codegen/routes.py`, `input_schema.py`, `db_client.py`, `completeness.py`, `export_render.py` | the spine generators (string templates) |

---

## 2. Increments (by dependency + leverage)

```
Inc 1  Conventions ext (response idiom) + manifest model     (FR-9, FR-10)   — foundation
Inc 2  Input-schema generator (Create/Update)                (FR-3)          — routes depend on it
Inc 3  db.ts generator                                       (FR-6)          — trivial, routes import it
Inc 4  CRUD route-handler generator (the big one)            (FR-1)          — needs 1–3
Inc 5  AI-trigger route generator (owned shell)              (FR-2)          — needs manifest bindings
Inc 6  Completeness function generator                       (FR-4)
Inc 7  Export generator (JSON pure + MD from layout)         (FR-5)
Inc 8  AI tool-use Zod schema generator                      (FR-7)          — reuse render_zod_schema
Inc 9  Verification generalization + strtd8 spine acceptance (FR-11, FR-13)  — tsc + import gates
Inc 10 Wiring: CLI + multi-owned skip-hook + auto pre-write  (FR-12)
Inc 11 [deferred] Seeded import-shells                       (FR-8)
```

### Inc 1 — Conventions + manifest (FR-9, FR-10)
- `conventions.py`: add `response_idiom` (detect `Response.json` vs `NextResponse` from existing routes), `api_route_layout`, to `ProjectConventions`.
- `manifest.py`: `CodegenManifest` — `resources[]` (entity, crud verbs), `action_routes[]` (path, pass binding {name, module}), `export_layout`, `completeness_signals`. Loader: from a `frontend-codegen.yaml` and/or derived from the plan-ingestion task manifest (OQ-1). Validate pass-binding module paths resolve (else flag, FR-10).
*Tests:* strtd8 detection → `response_idiom="web-response"`; a manifest yields exactly the declared route set; an unresolved pass binding is flagged.

### Inc 2 — Input schemas (FR-3)
- `input_schema.py`: from the shared FieldSpec projection, render `<Entity>Create` (omit `id/ownerId/source/confirmed/createdAt/updatedAt`; relations → `<rel>Ids: z.array(z.string())`) and `<Entity>Update = .partial()`.
*Tests:* `ProofPointCreate` omits the 6 server fields + has link arrays; `Update` is partial; both compile + pass fidelity.

### Inc 3 — db client (FR-6)
- `db_client.py`: render the canonical `db.ts` singleton (`export { db }`, dev-global guard). Migrations explicitly out of scope (note in code).
*Tests:* generated `db.ts` exports `db: PrismaClient`; `import { db }` resolves.

### Inc 4 — CRUD route handlers (FR-1, the headline)
- `routes.py`: per CRUD resource → collection (`route.ts`: GET list, POST create-validated) + item (`[id]/route.ts`: GET/PATCH/DELETE), string templates using the detected response idiom, canonical `db` + input-schema imports.
*Tests:* strtd8 `proof-points` pair compiles under the tsc gate; GET→`findMany`, POST→validate+`create`; `scan_unresolvable_imports`=[].

### Inc 5 — AI-trigger routes (FR-2)
- Extend `routes.py`: owned thin wrapper per action route — validate body → call `<pass>` by canonical module path (from the manifest binding) → response idiom.
*Tests:* `ai/tailor-match` imports the pass from the real on-disk path; compiles; body-validated.

### Inc 6–8 — Completeness, Export, Tool-schemas (FR-4, FR-5, FR-7)
- `completeness.py`: pure `computeCompleteness(counts)` from the declared signal set + a thin count-query helper.
- `export_render.py`: pure JSON serializer + MD renderer from the declared layout.
- tool-schemas: reuse `render_zod_schema` on the manifest-declared entities.
*Tests:* completeness over fixture counts → expected score/nudge, no DB import; JSON round-trips; MD has declared sections; tool schema passes `verify_render_fidelity`.

### Inc 9 — Verification generalization + strtd8 spine acceptance (FR-11, FR-13)
- `gates.py` / a new `verify_owned_artifacts(project_root)`: run `run_project_typecheck` + `scan_unresolvable_imports` + `scan_missing_dependencies` over the generated spine; schema/tool files also `assert_symmetric`+`verify_render_fidelity`.
- Property test (FR-13): every generator's field set ≡ the shared projection.
- **strtd8 acceptance:** generate the CRUD spine for strtd8's manifest into a temp copy; assert **0 tsc errors + 0 unresolvable imports + 0 missing deps** attributable to owned artifacts.
*Tests:* the acceptance above; a deliberately broken template is caught.

### Inc 10 — Wiring (FR-12)
- Extend `cli_generate.py` `generate frontend` to emit the spine + a manifest of owned/seeded paths.
- Extend the skip-hook recognition to all owned spine files (the per-target `owned_file_in_sync` loop already supports multiple targets).
- **Auto pre-write** (pull from deferred): render+write the owned spine in the prime-contractor pre-generation hook (beside `_build_project_knowledge`), drift-aware (write only absent/in-sync; surface tampered), sequenced around `check_git_status` (OQ-3).
*Tests:* CLI writes the spine; a feature targeting any in-sync owned file skipped at `$0.00`; pre-write is idempotent + doesn't clobber a tampered file.

### Inc 11 — [DEFERRED] Seeded import-shells (FR-8)
Deferred per OQ-4 — owned artifacts are the leverage; revisit after Inc 1–10 prove out.

---

## 3. Requirement → increment traceability

| FR | Increment |
|----|-----------|
| FR-9 conventions ext | Inc 1 |
| FR-10 manifest | Inc 1 |
| FR-3 input schemas | Inc 2 |
| FR-6 db client | Inc 3 |
| FR-1 CRUD routes | Inc 4 |
| FR-2 AI-trigger routes | Inc 5 |
| FR-4 completeness | Inc 6 |
| FR-5 export | Inc 7 |
| FR-7 tool-schemas | Inc 8 |
| FR-11 verification + FR-13 SSOT | Inc 9 |
| FR-12 wiring/pre-write | Inc 10 |
| FR-8 seeded shells | Inc 11 (deferred) |

## 4. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Manifest becomes a heavy hand-authored spec | Derive from the plan-ingestion task manifest where possible (OQ-1); only routes/bindings/layout need declaring. |
| Route templates drift from project idioms (Response vs NextResponse, app-router) | FR-9 convention detection drives the template; the tsc gate (Inc 9) catches any idiom mismatch. |
| Relation-link arrays not derivable for all entities | Inc 2 verifies against all 12 strtd8 models; un-inferable relations declared in the manifest (OQ-2). |
| Auto pre-write trips the dirty-tree gate (~30 files) | OQ-3: write only absent/in-sync; owned-file allowlist in the gate, or commit-then-skip; surfaced, never silent clobber (audit H2). |
| String templates produce subtly wrong TS | Inc 9's whole-project tsc gate is the by-construction backstop; templates are small + per-verb. |
| Duplication with `repair/retry/scaffold` (barrels/css) | NFR-2: reconcile `skeleton.py` emitters with the now-present `scaffold_*`. |
| Scope creep into semantic files | Non-Reqs fence it; seeded shells (FR-8) deferred. |

## 5. Conventions checklist
- [ ] `get_logger(__name__)`; no hardcoded model strings (no LLM).
- [ ] Reuse `parse_prisma_schema`/`FieldSpec`/`render_zod_schema`/`ts_toolchain`/`cross_file_imports` — don't re-implement.
- [ ] Byte-idempotent (source order, no set iteration); new files in the logger-policy allowlist if needed.
- [ ] `pytest tests/unit/frontend_codegen -q` green; ruff/black/mypy clean.
- [ ] strtd8 spine acceptance (Inc 9): 0 tsc errors + 0 unresolvable imports on owned artifacts.

---

*Plan v1.0 — manifest-driven, string-template generators reusing the proven renderer pattern;
verified by the live whole-project tsc gate + import-resolution checks. The only net-new pieces
are the manifest model + per-artifact templates + the conventions extension. Pairs with
requirements v0.2. CRP review offered before Inc 1.*
