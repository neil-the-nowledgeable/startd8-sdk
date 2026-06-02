# Python Contract-Codegen — Next Steps (team hand-off)

**Date:** 2026-06-02 · **Status:** kernel shipped/merged; hardening + first runtime use next.
**Companions:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (v0.2, all FRs marked shipped),
`PYTHON_CONTRACT_CODEGEN_PLAN.md` (v1.0), `../IDEAL_TARGET_ARCHITECTURE.md` (the why).

---

## Where we are (done)

From **one `.prisma` contract**, `startd8 generate backend` deterministically assembles the entire
all-Python app spine — Pydantic models, SQLModel tables, FastAPI CRUD, server-rendered HTMX UI
(inline validation), JSON/Markdown export, AI tool-schemas, completeness, `requirements.txt`. **12
owned artifact kinds**, all `$0.00`-skip-recognized by the `pydantic-sqlmodel` provider, all
build-gateable.

- **Merged to `main`** (merge `900c9e8e`); package `src/startd8/backend_codegen/`.
- **OQ-5 wired** (`4d894bc5`): skip-hook via entry point + the build gate in
  `prime_postmortem._evaluate_python_toolchain` (env `STARTD8_PY_TYPECHECK`).
- **Pilot passed** (ProofPoint+Metric): 19 files, gate pass, `--check` all in_sync.
- **Verified on the real strtd8 15-model contract**: byte-identical idempotent, `--check` in_sync.
- **Runtime-verified** (#1 below): the generated app actually serves — full JSON CRUD + HTMX UI
  via `TestClient` against real fastapi/sqlmodel/jinja2.

---

## Next steps (prioritized)

### 1. Real-runtime smoke test of a generated app  ·  ✅ DONE
Generated the ProofPoint+Metric app into a throwaway venv with real
fastapi/sqlmodel/jinja2/python-multipart and drove the full cycle via FastAPI's `TestClient` —
**13/13 pass**: JSON CRUD with the DTOs, JSON-list-column round-trip (`tags`), enum coercion,
partial `XUpdate` PATCH, and the whole HTMX UI (list/form/validate/delete). Encoded as
`tests/unit/backend_codegen/test_runtime_smoke.py` (skips when app deps absent; runs in
CI-with-deps).

**Three real defects the runtime test caught (all fixed):**
- **`TemplateResponse` signature** — old `(name, context)` form crashes on modern Starlette
  (treats the context dict as the template name). Now `(request, name, context)`.
- **`web_router` never mounted** — `main.py` only included the JSON routers; the HTMX UI was
  generated but unreachable. Now `app.include_router(web_router)`.
- **`python-multipart` is a required runtime dep** (form parsing) and the SDK emitted no dependency
  manifest. Added a generated **`requirements.txt`** (fastapi/sqlmodel/jinja2/python-multipart/
  uvicorn) — a 12th owned artifact kind.

### 2. Tag + clear the retired TS `app/` in strtd8  ·  *prerequisite, cheap*
The strtd8 app tree is still Next.js. Tag it (`retired-ts-prototype`) and clear it so the Python
`app/` can be generated cleanly. Pair with #1. (Not yet ready for multi-phase cap-dev-pipe runs
until this is done.)

### 3. SQLModel `Create`/`Read`/`Update` DTO split (OQ-3)  ·  ✅ DONE
`sqlmodel_renderer` now emits `XCreate` (editable surface, hides `@default` server-set fields),
`XRead` (full view), and `XUpdate` (every non-PK field optional, partial PATCH) alongside the
unchanged table class; routers use them (`item: XCreate` → `-> XRead`; `data: XUpdate`). The runtime
test (#1) may still reveal which `@default`/server-set fields a real schema needs hidden — confirm
then.

### 4. FK constraints + `Relationship()` + `@default` translation + reserved-name guard  ·  ✅ DONE
All runtime-verified **on the real 15-model schema** (`configure_mappers` + `create_all` + a real
CREATE + bidirectional navigation):
- **FK constraints** — `@relation` → `Field(foreign_key="table.col")`.
- **`Relationship()`** — cross-model `back_populates` pairing (relation-name disambiguation;
  self-ref + implicit-M2M flagged & skipped); compound `@@id` PKs for join models.
- **`@default`/`@updatedAt` translation** (fixed the write-path blocker the team's smoke test found):
  `cuid`/`uuid`→`default_factory`, `now()`/`@updatedAt`→utcnow factory+`onupdate`, literals→`default=`.
- **Reserved attr names** (`metadata`/`registry`) fail loud instead of emitting import-crashing code.

### 5. Lower priority
- **Completeness domain-manifest (OQ-4)** — replace the v1 presence rule with the real thresholds
  (Profile present, ≥3 confirmed ProofPoints, ≥1 Outcome/Metric/Differentiator) via a declared
  signal manifest. *(The team's FR-6 note — "AI must never write `Metric.value`" — also lands here:
  it's a domain rule the generic renderer can't infer, needs an app-authored narrower draft schema
  or this manifest.)*

### Skip for now
Polyglot / `ProtoStubProvider` (no demand) and a Pydantic-native contract format — the
`.prisma`-as-IDL bet (OQ-7) is working; revisit only if `.prisma` authoring becomes a burden.

---

## Pointers
- Generators: `src/startd8/backend_codegen/` (`assembler.render_backend` = the full set).
- Gate: `src/startd8/validators/python_toolchain.py`; wired in `prime_postmortem._evaluate_python_toolchain`.
- CLI: `startd8 generate backend --schema <prisma> --out <root> [--check] [--gate]`.
- Layout: `backend_codegen.CANONICAL_LAYOUT` (one `app/` package).
- Tests: `tests/unit/backend_codegen/`, `tests/unit/validators/test_python_toolchain.py`.
