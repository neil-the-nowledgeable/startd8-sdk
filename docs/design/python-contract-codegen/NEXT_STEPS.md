# Python Contract-Codegen — Next Steps (team hand-off)

**Date:** 2026-06-02 · **Status:** kernel shipped/merged; hardening + first runtime use next.
**Companions:** `PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (v0.2, all FRs marked shipped),
`PYTHON_CONTRACT_CODEGEN_PLAN.md` (v1.0), `../IDEAL_TARGET_ARCHITECTURE.md` (the why).

---

## Where we are (done)

From **one `.prisma` contract**, `startd8 generate backend` deterministically assembles the entire
all-Python app spine — Pydantic models, SQLModel tables, FastAPI CRUD, server-rendered HTMX UI
(inline validation), JSON/Markdown export, AI tool-schemas, completeness. **11 owned artifact
kinds**, all `$0.00`-skip-recognized by the `pydantic-sqlmodel` provider, all build-gateable.

- **Merged to `main`** (merge `900c9e8e`); package `src/startd8/backend_codegen/`.
- **OQ-5 wired** (`4d894bc5`): skip-hook via entry point + the build gate in
  `prime_postmortem._evaluate_python_toolchain` (env `STARTD8_PY_TYPECHECK`).
- **Pilot passed** (ProofPoint+Metric): 18 files, gate pass, `--check` all in_sync.
- **Verified on the real strtd8 15-model contract**: 57 files, byte-identical idempotent,
  `--check` in_sync.
- Static validation only so far: `compile()` for `.py`, Jinja-parse for templates. **Nothing has
  imported fastapi/sqlmodel/jinja2 or served a request yet.**

---

## Next steps (prioritized)

### 1. Real-runtime smoke test of a generated app  ·  *highest value — do first*
This is the one remaining unknown that static checks can't cover, and it **doubles as the app's
M0→M2 Profile pilot slice** (`$0`-LLM `generate backend`, not a pipeline run).

**Do:** `generate backend` → fresh venv → `pip install fastapi sqlmodel jinja2 uvicorn` →
`uvicorn app.main:app`.
**Acceptance:**
- `GET /ui/<entity>` renders the list; `GET /ui/<entity>/new` renders the form.
- `POST` the form persists a row to SQLite (`init_db` ran on startup).
- `POST /ui/<entity>/validate` returns the inline field-error partial.
- delete swaps the row out (`hx-swap=outerHTML`); detail/edit round-trip.

**Why:** converts "generates correct-looking code" → "generates a running app"; will surface any
runtime import mismatch, Jinja context-key, or SQLModel coercion edge (esp. `tags` list ↔ JSON
column, enum coercion, optional/`metricId`). Capture findings back into the generators.

### 2. Tag + clear the retired TS `app/` in strtd8  ·  *prerequisite, cheap*
The strtd8 app tree is still Next.js. Tag it (`retired-ts-prototype`) and clear it so the Python
`app/` can be generated cleanly. Pair with #1. (Not yet ready for multi-phase cap-dev-pipe runs
until this is done.)

### 3. SQLModel `Create`/`Read` DTO split (OQ-3 refinement)  ·  *after #1*
Today the SQLModel table class is used directly as request body + response, so clients can supply
server-set fields (e.g. `id`) on create. Generate `XCreate`/`XRead` DTOs to hide them. Do it **after**
#1 — the runtime test tells you exactly which fields need hiding.

### 4. Lower priority
- **FK constraints + `Relationship()`** — real referential integrity (FK scalars are plain columns
  in v1).
- **Completeness domain-manifest (OQ-4)** — replace the v1 presence rule with the real thresholds
  (Profile present, ≥3 confirmed ProofPoints, ≥1 Outcome/Metric/Differentiator) via a declared
  signal manifest.

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
