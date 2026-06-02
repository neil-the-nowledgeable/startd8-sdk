# Python Contract-Codegen Path — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-02
**Status:** Post-planning (pre-CRP)
**Companion:** `docs/design/IDEAL_TARGET_ARCHITECTURE.md` (canonical target arch),
`docs/design/deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` (the kernel),
`deterministic-frontend/` (the shipped TS sibling this generalizes).

> **Objective.** Give the SDK a **Python** contract-codegen path that mirrors the shipped TS
> Prisma→Zod path, so the real app (all-Python, FastAPI + Pydantic + HTMX, modular monolith) is
> assembled **deterministically (~60–75%, $0 LLM)** from one canonical contract. The LLM is spent
> only on the irreducible semantic core (AI passes, non-CRUD logic). This raises deterministic
> coverage from today's ~5% (TS `value-model.ts` + config only).

> **Locked decisions (this iteration).** ORM = **SQLModel** (one class = contract + table).
> Pilot bounded context = **ProofPoint + Metric**. HTMX output set = **CRUD + inline validation**
> (list / detail / create+edit form / delete + validate-on-blur, field-level errors, partial swaps).

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read the shipped machinery (`schema_renderer`, `provider`,
> `deterministic_providers`, `ts_toolchain`, `languages/python`, `skeleton`, `gates`, `drift`,
> the `generate` CLI) to stress-test v0.1. Seven corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| FR-1 "generalize `render_zod_schema` into a shared projection" implies refactoring the renderer | The field projection is **already shared** — `PrismaField → FieldSpec` via `project_knowledge` `FieldSetAuthority` (`schema_renderer.py:157–187`); only the **Zod string emission** (`SCALAR_MAP`, decorator layering, `schema_renderer.py:42–104`) is hardcoded | FR-1 **narrowed**: add a **new** Pydantic emitter module (~200 LOC); **do not touch** the shipped renderer. Reuse the field projection as-is. |
| The canonical contract is authored as Pydantic (per IDEAL_TARGET §4) | The shipped pipeline's **input is `.prisma` schema text** → `parse_prisma_schema` → AST. Reusing the parser + `FieldSpec` + drift + fidelity requires keeping **`.prisma` as the neutral contract IDL** | **NEW framing:** the **`.prisma` schema is the neutral source of truth**; Pydantic + SQLModel (+ Zod for any island) are **co-generated projections**. "Nothing hand-typed twice" holds at the `.prisma` level. Pydantic-as-authored-source stays possible later but is net-new (no parser). → **OQ-7**. |
| FR-5 build gate is a from-scratch build | The `ToolchainResult` dataclass + the **"absent tool ⇒ non-pass"** verdict logic (`ts_toolchain.py:46–71`) are reusable; only the invocations/parser are language-specific | FR-5 **refined**: new `python_toolchain.py` **reusing `ToolchainResult`** (~150 LOC), mirroring the loud-degrade contract. |
| FR-9 "reuse drift" covers all owned-file checking | `drift.py` (`owned_file_in_sync`: two-stage stale-hash + byte-compare) is **fully generic** — reuse-as-is. **But** `gates.py` fidelity/symmetry checks are **Zod-syntax-specific** | FR-9 **split**: drift = reuse-as-is; fidelity/symmetry = **new `pydantic_gates.py`** (~150 LOC). |
| OQ-6 assumed `scaffold_barrel`/`scaffold_cofile` exist to reconcile | They **do not exist**. `skeleton.py` has `render_barrel`/`render_css_module_stub` (TS-specific) + reusable `_canonical_dirs`/`detect_project_conventions` | OQ-6 **resolved**: reuse skeleton dir-planning + convention detection; write new Python emitters; Python uses `__init__.py` re-exports (simpler than TS barrels). |
| FR-13 / OQ-5 CLI wiring uncertain | The `generate` CLI is **fully polyglot** — add one `@generate_app.command("backend")` in `cli_generate.py`, **zero changes** to `cli.py` | FR-13 standalone half **confirmed trivial**; only the prime-contractor integration hook remains open (OQ-5 narrowed). |
| Global: "it generalizes cleanly" | **Partially false but de-risked:** registry / drift / CLI / field-projection = **reuse-as-is**; renderers / gates / skeleton emitters / build-gate = **net-new but isolated** (~500–700 LOC across 3–4 new modules, **zero changes to shipped TS code**) | The TS path is untouched; the Python path inherits the registry/drift/CLI architecture. Effort bounded + isolated. |

**Resolved / updated open questions:**
- **OQ-5 → narrowed.** Standalone CLI is trivial (one new `generate backend` command). Only the
  prime-contractor `integration_engine` post-gen hook remains genuinely open.
- **OQ-6 → resolved.** Reuse `skeleton._canonical_dirs` + `detect_project_conventions`; write new
  Python emitters; `__init__.py` re-exports instead of TS barrels.
- **OQ-7 → NEW (now the load-bearing question).** Contract source-of-truth: keep **`.prisma` as the
  neutral IDL** (maximal reuse — parser/projection/drift all inherited; *recommended*) vs author
  **Pydantic natively** (purist all-Python, but net-new parser + can't be both source and
  generated). **Leaning `.prisma`-as-IDL** for v1; revisit if authoring `.prisma` proves awkward.

---

## 1. Problem Statement

The SDK's deterministic codegen is **TS-only**: `frontend_codegen/` renders `value-model.ts`
(Prisma→Zod) and config, gated by `validators/ts_toolchain.run_project_typecheck` (whole-project
`tsc`). The locked target app is **all-Python**. Nothing in the SDK emits Pydantic / SQLModel /
FastAPI / HTMX, and there is **no Python project-level build gate** — so generating the real app
today falls back to LLM authoring of exactly the layers (models, CRUD, forms) that caused the
RUN-015/016/017 invention failures.

The decoupling seam is shipped and language-agnostic: the **`DeterministicFileProvider` registry**
(`contractors/deterministic_providers.py`) and the owned-file skip-hook. What's missing is a
**Python provider + Python generators + a Python build gate** behind that seam.

| Component | Current State | Gap |
|-----------|---------------|-----|
| Provider registry + skip-hook ($0.00) | ✅ shipped, language-agnostic | **reuse as-is** |
| Drift / `--check` (`drift.owned_file_in_sync`) | ✅ shipped, generic | **reuse as-is** |
| Field projection (`PrismaField → FieldSpec`) | ✅ shipped (`project_knowledge` authority) | **reuse as-is** |
| `generate` CLI surface | ✅ shipped, polyglot | **reuse** (+1 command) |
| `ToolchainResult` + loud-degrade verdict | ✅ shipped (in `ts_toolchain`) | **reuse the dataclass** |
| schema → models **string emission** | ✅ Zod only (`SCALAR_MAP` hardcoded) | **net-new Pydantic/SQLModel emitter** |
| FastAPI CRUD routes | ❌ none | net-new |
| HTMX/Jinja templates | ❌ none | net-new |
| Python **project** build gate | ❌ none (only TS; single-file stubs on `python.py`) | net-new (`python_toolchain.py`) |
| Fidelity/symmetry gates | ✅ Zod-specific only | net-new (`pydantic_gates.py`) |
| Completeness / export emitters | ❌ none | net-new (small pure emitters) |

---

## 2. Requirements

**FR-1 — `PydanticModelProvider`.** Project the canonical **`.prisma` contract** → Pydantic v2
models via a **new emitter module** that reuses the shipped `PrismaField → FieldSpec` projection
(no change to `schema_renderer`; only a Pydantic `SCALAR_MAP` + decorator-layering added). Register
via the shipped `DeterministicFileProvider` registry (entry-point group
`startd8.contractors.deterministic_providers`). Generated files are **owned** (marker header,
skip-hook `$0.00 GENERATED`, never hand-edited).

**FR-2 — SQLModel table emission.** The same `.prisma` contract co-projects to **SQLModel** table
classes (per the locked ORM decision). The "one definition = contract + table" property is realized
at the **`.prisma` level** (single source); the SQLModel tables (persistence) and the FR-1 Pydantic
schemas (API/validation/AI) are co-generated projections. Enums emit as `str, Enum` classes; list
scalars as JSON columns; field `@id` **and compound `@@id`** → primary keys; **FK constraints**
(`@relation` → `Field(foreign_key=…)`); **`Relationship()` ORM-navigation** with cross-model
`back_populates` pairing (self-ref + implicit-M2M flagged/skipped); and **`@default`/`@updatedAt`
translation** (`cuid`/`uuid`→`default_factory`, `now()`/`@updatedAt`→utcnow+`onupdate`,
literals→`default=`). Reserved attr names (`metadata`/`registry`) fail loud. **Shipped — all
runtime-verified on the real 15-model schema** (`configure_mappers` + `create_all` + a real CREATE
with defaults filled + bidirectional navigation). **Deferred:** nothing major.

**FR-3 — FastAPI CRUD generator. Shipped (Step 4).** `crud_generator.py` emits the owned spine —
`app/routers.py` (one `APIRouter` per entity: list / detail / create / update / delete, validate via
the SQLModel class → session op → response; entities without a single-column PK get list+create
only), `app/db.py` (SQLite engine + `get_session` + `init_db`), `app/main.py` (FastAPI app + all
routers). Canonical imports only; no invented module paths.

**FR-4 — HTMX/Jinja template generator. Shipped (Step 5).** `htmx_generator.py` emits the owned UI:
`app/web.py` (HTML routes — list / new / create / detail / edit / update / delete + a `/validate`
inline endpoint) and Jinja templates (`base.html`, `_field_error.html`, per-entity
`list/detail/form.html`). The **locked HTMX output set** — CRUD + **inline validation**
(validate-on-blur via `hx-post`+`hx-trigger`, field-level error slots, `outerHTML` partial swaps on
delete). Field→widget map derived from the model (enum→`<select>`, bool→checkbox, Int/Float→number,
DateTime→datetime-local, else→text). Template provenance is a `#` header wrapped in a Jinja `{# #}`
comment, so the **existing drift path recognizes templates** (entity-aware dispatch) with no new
machinery. Owned; `$0.00`-skippable.

**FR-5 — Python project build gate. Shipped (Step 3).** `validators/python_toolchain.py` mirrors
`ts_toolchain`'s **verdict contract** (`checked`/`unavailable`/`timeout`/`error` →
`pass`|`fail`|`unavailable`) with a **native `PyToolchainResult`** — *not* a literal reuse of
`ToolchainResult`, which is TS-coupled (`prisma_generated`, `TscDiagnostic`). *(Corrected from v0.2
§0, which assumed dataclass reuse; the real reuse is the contract + loud-degrade rule.)* Stages:
`compileall` (the **always-available syntax floor**) → `mypy` → `pytest`; absent/disabled stages are
**recorded in `stages_skipped`** (loud, never a silent pass). `python_typecheck_enabled()` toggles
on `STARTD8_PY_TYPECHECK`, mirroring the TS gate.

**FR-6 — Completeness emitter. Shipped (Step 6).** `derived.render_completeness` → `app/completeness.py`:
a pure `compute_completeness(present)` → score + priority-ordered nudges. *(OQ-4 resolved: a
schema-derived **presence** rule in v1 — each entity with ≥1 row contributes; nudge per absent
entity. Domain-weighted thresholds, e.g. ≥3 ProofPoints, are a declared-manifest refinement,
deferred.)* Owned, no LLM.

**FR-7 — Export emitter. Shipped (Step 6).** `derived.render_export` → `app/export.py`: `to_json`
(lossless, sorted) + `to_markdown` (deterministic layout — section per entity in schema order, field
lines in order). JSON is the round-trip format. Owned.

**FR-8 — AI tool/IO schema emission. Shipped (Step 6).** `derived.render_ai_schemas` →
`app/ai_schemas.py`: re-projects the FR-1 Pydantic models as the AI passes' structured-output
contract — `AI_SCHEMAS` (entity → model class) + `json_schema(entity)`. Owned/deterministic; pass
*logic* stays LLM.

**FR-9 — Owned-file discipline.** (a) **Drift** — the two-stage *logic* (stale-hash + re-render
byte-compare) carries over, but is **mirrored, not reused**: a `.py` file carries a `#` GENERATED
header (not the TS `//`) and `check_drift` hardwires the renderer, so the path ships its own
`backend_codegen/drift.py` (~120 LOC). *(Corrected during Step 1 — v0.2 §0 had assumed drift was
reuse-as-is.)* (b) **Fidelity** — `backend_codegen/gates.py:verify_pydantic_fidelity` (field
count/order/optionality/list). All artifacts participate in the skip-hook (`$0.00`) and `--check`;
regenerated on contract change; never hand-edited. **Shipped (Step 1).**

**FR-10 — Generation spec source.** Derive CRUD/route/AI-trigger selection maximally from the
contract; permit a **small declared manifest** for irreducible choices (which entities get CRUD,
which routes are AI-trigger wrappers, AI-pass names). *(Pure-contract vs manifest → OQ-1.)*

**FR-11 — Canonical layout + generated imports. Shipped (Step 4).** A `CANONICAL_LAYOUT` constant
fixes the five artifacts to one `app/` package (`models.py`/`tables.py`/`routers.py`/`db.py`/
`main.py`), so the generated relative imports (`from .db import get_session`, `from .tables import
X`, `from .routers import all_routers`) resolve by construction; the FR-5 build gate fails on any
invented path. *(A bespoke layout constant proved simpler than the planned `skeleton._canonical_dirs`
reuse, which is TS/barrel-oriented — corrected from v0.2.)*

**FR-12 — Pilot. PASSED (Step 8).** `startd8 generate backend` on the **ProofPoint + Metric**
`.prisma` writes 19 files (10 `.py` + 8 templates + `requirements.txt`), `--gate` reports **build
gate: pass**, and
`--check` reports **all 18 artifacts in_sync** — i.e. the skip-hook would mark a regen `$0.00`. The
v1 acceptance milestone, proven end-to-end via the real CLI.

**FR-13 — CLI surface. Shipped (Step 7).** `startd8 generate backend` — one `@generate_app.command`
in `cli_generate.py` (zero changes to `cli.py`): `--schema`/`--out`/`--check`/`--gate`/
`--source-label`. Writes the whole `app/` package (via `render_backend`); `--check` drift-checks
every owned artifact (exit 1 on drift); `--gate` runs the Python build gate. Prime-contractor wiring
is **done** (OQ-5): the gate runs in `prime_postmortem._evaluate_python_toolchain`, and the skip-hook
auto-recognizes the artifacts via the `pydantic-sqlmodel` entry point.

---

## 3. Non-Requirements

- **`ProtoStubProvider` / the other 4 languages** — deferred; future per-service option behind the
  same registry.
- **Auto pre-write of owned files during a run** — still deferred. The skip-hook *recognizes* a
  committed, in-sync owned file; it does not generate it mid-run. Generation stays an explicit
  `startd8 generate` step.
- **Refactoring the shipped TS renderer/`schema_renderer.py`** — the Python path is **additive**
  (new modules); the Prisma→Zod path stays untouched.
- **A Python-native (non-`.prisma`) contract authoring format** — possible later (OQ-7); net-new
  parser, out of scope for v1.
- **The AI passes' prompts/logic, page UX/copy, wizard orchestration, non-CRUD business logic** —
  semantic, stays LLM (grounded + build-gated).
- **Auth/authz, deployment infra, the actual service split, migrating the retired prototype** — out
  of scope.

---

## 4. Open Questions

- **OQ-1 — Generation spec source.** Pure contract annotations vs a small declared manifest for
  CRUD/route/AI-trigger selection? Resolve against the `.prisma` contract's expressiveness.
- **OQ-2 — Templating engine.** Pure string templates (the proven `value-model.ts` pattern) vs a
  structured/AST emitter — and how each stays convention-true to FastAPI app structure + Jinja/HTMX
  idioms.
- **OQ-3 → fully resolved (Step 2 table + DTO refinement).** The `class X(SQLModel, table=True)` is
  the persistence truth; typed DTOs are generated alongside it for the API edge — `XCreate`
  (editable surface, hides `@default` server-set fields), `XRead` (full view), `XUpdate` (every
  non-PK field optional, partial PATCH). Routers use the DTOs (`item: XCreate` → `-> XRead`;
  `data: XUpdate`); the table class is unchanged, so the fidelity gate is unaffected.
- **OQ-4 → resolved (Step 6).** Not derivable from the schema (the `.prisma` doesn't encode "≥3
  ProofPoints"). v1 ships a schema-derived **presence** rule; domain-weighted thresholds are a
  declared-manifest refinement, deferred.
- **OQ-5 → resolved.** Both halves wired: (a) the **$0.00 skip-hook** auto-recognizes backend
  artifacts via the `pydantic-sqlmodel` entry point (active on `pip install -e`); (b) the **build
  gate** is `prime_postmortem._evaluate_python_toolchain` (alongside the TS gate's
  `_evaluate_ts_toolchain`), env-gated `STARTD8_PY_TYPECHECK`, attributing real compileall/mypy
  faults to features and filtering mypy import-resolution noise (absent app deps = infra, not fault).
- **OQ-7 — Contract source-of-truth** *(new, load-bearing)*. Keep `.prisma` as the neutral IDL
  (maximal reuse; *recommended*) vs author Pydantic natively (purist; net-new parser). Leaning
  `.prisma`-as-IDL for v1.

> *Resolved during planning: OQ-6 (skeleton reuse — see §0).*

---

*v0.2 — Post-planning self-reflective update. 6 requirements narrowed/refined (FR-1, FR-2, FR-5,
FR-9, FR-11, FR-13), 1 framing change (`.prisma` as neutral contract IDL), 1 OQ resolved (OQ-6),
1 OQ narrowed (OQ-5), 1 OQ added (OQ-7). Net effort: ~500–700 LOC across 3–4 new isolated modules,
zero changes to shipped TS code.*
