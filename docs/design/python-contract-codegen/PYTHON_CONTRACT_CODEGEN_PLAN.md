# Python Contract-Codegen Path — Implementation Plan

**Version:** 1.0 (Post-planning, matches Requirements v0.2)
**Date:** 2026-06-02
**Requirements:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (v0.2)

> **Strategy.** Additive: a new `backend_codegen/` package mirroring the shipped `frontend_codegen/`,
> reusing the language-agnostic seams (registry, drift, field projection, CLI, `ToolchainResult`)
> and adding only the Python-specific emitters + gate. **Zero changes to shipped TS code.** Built
> bottom-up and pilot-driven: the smallest vertical (schema→Pydantic, owned, $0 skip) lights up
> first, then CRUD/HTMX/gate widen it, then the **ProofPoint + Metric** pilot proves the full loop.

---

## Module map (new unless noted)

| Module | Realizes | Reuse | Est. |
|--------|----------|-------|------|
| `backend_codegen/pydantic_renderer.py` | FR-1, FR-2, FR-8 | `PrismaField→FieldSpec` projection, `parse_prisma_schema`, `schema_sha256`, GENERATED header | ~200 LOC |
| `backend_codegen/provider.py` (`PydanticSQLModelProvider`) | FR-1, FR-9a | mirror `PrismaZodFileProvider`; `ProviderContext`, `drift.owned_file_in_sync` | ~60 LOC |
| `backend_codegen/pydantic_gates.py` | FR-9b | mirror `gates.verify_render_fidelity`/`assert_symmetric` | ~150 LOC |
| `validators/python_toolchain.py` | FR-5 | **reuse `ToolchainResult`** + verdict logic from `ts_toolchain` | ~150 LOC |
| `backend_codegen/crud_generator.py` | FR-3 | canonical-import discipline | ~150 LOC |
| `backend_codegen/htmx_templates.py` | FR-4 | field→widget map; Jinja string templates | ~250 LOC |
| `backend_codegen/completeness.py` | FR-6 | pure fn | ~60 LOC |
| `backend_codegen/export.py` | FR-7 | pure fn | ~80 LOC |
| `backend_codegen/skeleton.py` (or extend) | FR-11 | `skeleton._canonical_dirs`, `detect_project_conventions` | ~80 LOC |
| `cli_generate.py` (+1 command) | FR-13 | `@generate_app.command("backend")` | ~40 LOC |
| `pyproject.toml` (entry point) | FR-1 | `pydantic-sqlmodel` provider registration | 1 line |

---

## Sequenced steps

**Step 1 — Foundation: schema→Pydantic, owned, $0 skip (FR-1, FR-9).**
- `pydantic_renderer.render_pydantic_models(schema_text)` — reuse `parse_prisma_schema` + the
  `FieldSpec` projection; add a Pydantic `SCALAR_MAP` (`String→str`, `Int→int`, …) + Pydantic
  field/optional/list layering; emit the GENERATED header with `schema_sha256` so drift works.
- `provider.PydanticSQLModelProvider` (`owns` = header marker; `is_in_sync` = read `.prisma` from
  `ProviderContext.source_anchors` → `owned_file_in_sync`). Register via entry point.
- `pydantic_gates.verify_render_fidelity` (field count/order/optionality/type).
- **Proves:** the smallest vertical — a generated Pydantic models file recognized by the skip-hook
  as `$0.00 GENERATED`, drift-checked, fidelity-gated. *Depends on: nothing new.*

**Step 2 — SQLModel co-projection (FR-2). ✅ SHIPPED.** `sqlmodel_renderer.py` emits
`class X(SQLModel, table=True)` from the same `.prisma` AST: `@id`→primary key, enums→`str, Enum`
classes, list scalars→JSON columns, FK scalars→plain columns (FK constraints deferred). OQ-3
resolved (single table class + the FR-1 Pydantic schemas as the API/AI edge). Drift now dispatches
on a `# startd8-artifact:` header tag so one provider verifies both `models.py` and `tables.py`.
*Depended on: Step 1.*

**Step 3 — Python build gate (FR-5). ✅ SHIPPED.** `validators/python_toolchain.run_project_check`:
`compileall` (always-available floor) → `mypy` → `pytest`, native `PyToolchainResult` mirroring the
ts_toolchain verdict contract; absent/disabled stages recorded in `stages_skipped` (loud-degrade).
`python_typecheck_enabled()` toggles on `STARTD8_PY_TYPECHECK`. *Was parallelizable with 1–2.*

**Step 4 — FastAPI CRUD + canonical layout (FR-3, FR-11). ✅ SHIPPED.** `crud_generator.py` emits
`app/routers.py` (one APIRouter/entity: list/detail/create/update/delete; keyless entities get
list+create), `app/db.py` (engine + `get_session` + `init_db`), `app/main.py` (FastAPI app + router
wiring). `CANONICAL_LAYOUT` fixes the five artifacts to one `app/` package so imports resolve by
construction. Three new artifact kinds (`fastapi-routers`/`-db`/`-main`) registered in the drift
dispatch, so the one provider $0.00-recognizes them too. *Depended on: Steps 1–2 (models) + 3 (gate).*

**Step 5 — HTMX/Jinja templates + inline validation (FR-4).** `htmx_templates` emits list / detail /
create+edit form / delete + validate-on-blur endpoints + field-level error partials + partial swaps;
field→widget map derived from the model. *Depends on: Step 4 (routes to target).*

**Step 6 — Pure emitters + AI schemas (FR-6, FR-7, FR-8).** `completeness` (declared signal set →
score+nudges), `export` (JSON pure + MD from declared layout), and AI tool/IO schema projection
(reuse Step-1 renderer). Resolve OQ-4 (signal declaration). *Depends on: Step 1 (renderer) + 2.*

**Step 7 — CLI (FR-13).** Add `startd8 generate backend --schema --out --check --strict` to
`cli_generate.py`. *Depends on: Steps 1–6 (something to invoke).*

**Step 8 — Pilot: ProofPoint + Metric end-to-end (FR-12).** Author the `.prisma` for the pilot
context → run `generate backend` → assert: Pydantic + SQLModel + CRUD + HTMX form/list generated;
re-run reports `$0.00 GENERATED`; Python build gate green. **Acceptance milestone.**
*Depends on: Steps 1–7.*

---

## Critical path & parallelism
- **Critical path:** Step 1 → 2 → 4 → 5 → 8.
- **Parallel:** Step 3 (gate) and Step 6 (pure emitters) can proceed alongside the path.
- **Fastest first signal:** Step 1 alone proves the $0 skip-hook on Python — do it first, demo it.

## Risks
- **OQ-7 (contract source).** If `.prisma`-as-IDL proves awkward to author for an all-Python team,
  a Python-native parser becomes net-new work — but that's a v2 concern; v1 commits to `.prisma`.
- **HTMX template fidelity (Step 5).** The field→widget map + partial-swap idioms are the most
  invention-prone surface; keep them pure string templates (OQ-2) and fidelity-gate them.
- **SQLModel one-class-vs-DTO (OQ-3).** Decide on the pilot's real fields before generalizing.

## Verification
Every owned artifact passes (a) its fidelity gate (`pydantic_gates`) and (b) the whole-project
Python build gate (Step 3) — by construction. The pilot (Step 8) is the end-to-end proof.

---

## Requirements coverage
FR-1→S1, FR-2→S2, FR-3→S4, FR-4→S5, FR-5→S3, FR-6→S6, FR-7→S6, FR-8→S6, FR-9→S1, FR-10→S4 (+OQ-1),
FR-11→S4, FR-12→S8, FR-13→S7. Every FR maps to a step; every step traces to ≥1 FR.

---

*v1.0 — matches Requirements v0.2. Open: OQ-1/2/3/4/5/7 (resolved inline at the steps noted).*
