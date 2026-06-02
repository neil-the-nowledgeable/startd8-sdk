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
at the **`.prisma` level** (single source); SQLModel and the API-facing Pydantic schema are
co-generated projections. Server-set / read-only field distinctions are emitted deterministically.
*(One-class-vs-DTO split → OQ-3.)*

**FR-3 — FastAPI CRUD generator.** Per entity, emit owned route handlers for list / detail /
create / update / delete: validate Pydantic → SQLModel op → response. Canonical imports only (the
generated models module, the DB session). No invented module paths.

**FR-4 — HTMX/Jinja template generator.** Per entity, emit the **locked HTMX output set**: list,
detail, create+edit form, delete — **plus inline validation** (validate-on-blur endpoints,
field-level error partials, partial swaps). Field→input widget mapping derived from the model
(enum→select, date→date input, bool→checkbox, relation→picker stub, str→input/textarea). Owned.

**FR-5 — Python project build gate.** New `python_toolchain.py` mirroring `ts_toolchain`, **reusing
the `ToolchainResult` dataclass + verdict logic**: run `python -m compileall` → `mypy` → `pytest`
over the generated project. **Loud-degrade when a tool is absent — never a silent pass.** Expose a
`python_typecheck_enabled()` flag mirroring the TS gate's toggle.

**FR-6 — Completeness emitter.** Generate a **pure** function from an explicitly declared signal set
→ score + priority-ordered nudges (realizes the app's FR-9). Owned, no LLM. *(Signal declaration →
OQ-4.)*

**FR-7 — Export emitter.** Generate structured-data → **JSON** (pure) + **Markdown** (from a
declared layout) with round-trip fidelity. Owned.

**FR-8 — AI tool/IO schema emission.** Project the **same `.prisma` contract** into the
structured-output schemas the AI passes import (their I/O contract), reusing the FR-1 projection
(Pydantic target). Schemas owned/deterministic; pass *logic* stays LLM.

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

**FR-11 — Canonical layout + generated imports.** Fix a project directory/convention layout
(reusing `skeleton._canonical_dirs` + `detect_project_conventions`; `__init__.py` re-exports instead
of TS barrels) so all generated imports resolve by construction; the build gate (FR-5) fails on any
invented path.

**FR-12 — Pilot.** Drive **ProofPoint + Metric** end-to-end: `.prisma` contract → generated Pydantic
+ SQLModel + FastAPI CRUD + HTMX form/list (with inline validation) → `$0.00` skip on regen →
Python build gate green. The v1 acceptance milestone.

**FR-13 — CLI surface.** Add `startd8 generate backend` as one `@generate_app.command` in
`cli_generate.py` (zero changes to `cli.py`), supporting `--schema`/`--out`/`--check`/`--strict`
like the `frontend` command. Prime-contractor integration is a follow-on. *(Integration hook →
OQ-5.)*

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
- **OQ-3 — SQLModel single-class vs separate DTO.** One SQLModel class as both API contract + table,
  or a separate read/write Pydantic DTO at the API edge? (Affects FR-2/FR-3 projection.)
- **OQ-4 — Completeness signal declaration.** Contract field annotations vs a separate manifest?
  (Couples to OQ-1.)
- **OQ-5 — Prime-contractor integration hook** *(narrowed)*. Beyond the standalone CLI, wire the
  Python gate into `integration_engine` post-generation (matching the TS tsc gate placement)?
- **OQ-7 — Contract source-of-truth** *(new, load-bearing)*. Keep `.prisma` as the neutral IDL
  (maximal reuse; *recommended*) vs author Pydantic natively (purist; net-new parser). Leaning
  `.prisma`-as-IDL for v1.

> *Resolved during planning: OQ-6 (skeleton reuse — see §0).*

---

*v0.2 — Post-planning self-reflective update. 6 requirements narrowed/refined (FR-1, FR-2, FR-5,
FR-9, FR-11, FR-13), 1 framing change (`.prisma` as neutral contract IDL), 1 OQ resolved (OQ-6),
1 OQ narrowed (OQ-5), 1 OQ added (OQ-7). Net effort: ~500–700 LOC across 3–4 new isolated modules,
zero changes to shipped TS code.*
