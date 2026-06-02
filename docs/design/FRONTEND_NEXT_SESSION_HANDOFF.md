# Front-End Work — Next-Session Handoff

**Date:** 2026-06-02 · **Picks up:** the deterministic-frontend → contract-codegen pivot.
**Read first:** `STARTDATE_NEXT_ITERATION_ARCHITECTURE_GUIDANCE.md` (the target architecture) +
`deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` (the SDK capability).

---

## TL;DR of where we landed

We started building a TS-Next deterministic "frontend spine generator," then **pivoted twice**:
(1) the SDK's durable strength is **microservices + a contract-first deterministic codegen
kernel** (TS-monolith spine generator = narrow debt, retired); then (2) — the **current,
canonical direction** — the real app is **greenfield, all-Python, contract-first, server-rendered
(FastAPI + Pydantic + HTMX), modular-monolith-microservice-ready**, chosen to **maximize
deterministic assembly and minimize LLM cost** (~60–75% deterministic ceiling; **no React/Next** —
the JS-front-end invention classes vanish; the "front-end framework" question dissolved). Python
is the SDK's strongest language; polyglot is optional. "StartDate" was a prototype, retired.

> **READ FIRST next session:** `docs/design/IDEAL_TARGET_ARCHITECTURE.md` (canonical) +
> `deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` (Direction update §). The
> TS-framed `STARTDATE_NEXT_ITERATION_ARCHITECTURE_GUIDANCE.md` + the SPINE docs are SUPERSEDED.

---

## What's committed on `main` (durable, working)

| Area | State |
|------|-------|
| `frontend_codegen` package (Prisma→Zod `value-model.ts` renderer, conventions, gates, drift, skeleton, telemetry, CLI `startd8 generate frontend`) | ✅ shipped (Inc 1–8b), 100+ tests |
| Whole-project **tsc gate** (`validators/ts_toolchain` + `cap-dev-pipe/ts-verify-gate.py`) | ✅ live; opt-in enforce via `STARTD8_TS_GATE_STRICT=1` |
| Advisory **missing-dependency** check wired into `integration_engine` | ✅ |
| **`DeterministicFileProvider` registry** (`contractors/deterministic_providers.py`) + `PrismaZodFileProvider` (`frontend_codegen/provider.py`); skip-hook decoupled from the core (no `frontend_codegen` import in `prime_contractor`) | ✅ the debt-shed refactor; entry point `startd8.contractors.deterministic_providers` |
| protobuf pin `>=6.33.5` (unblocks the contractors test suite) | ✅ |
| Design docs: CHARTER, SCOPE_ANALYSIS, GENERATION_* (renderer), CRP artifacts, StartDate guidance | ✅ committed |
| TS-spine docs (`SPINE_REQUIREMENTS/PLAN`) | ✅ committed but **SUPERSEDED** (do not implement) |

## Untracked / not done (intentionally)
- **Auto pre-write** of owned files during a run — still deferred (skip-hook only *recognizes*
  a pre-generated, committed, in-sync file; it doesn't generate it). See charter/§FR-12.
- The `prisma-zod` entry point activates on the next `pip install -e .` (until then the skip-hook
  no-ops safely; tests register the provider manually).
- strtd8 repo: `value-model.ts` was regenerated + committed there (`6f39962`); the Tailored*/
  AI feature is **unfinished untracked WIP** (missing `@/lib/ai/client`, `@/lib/types`) — it will
  fail a strict tsc gate until finished or removed.
- Pre-existing repo WIP (CLAUDE.md, CKG handoff, exemplar-registry, many other untracked files) —
  **not ours**, left untouched.

## Open decisions for the next session (small; see `IDEAL_TARGET_ARCHITECTURE.md` §9)
1. **ORM:** SQLModel (Pydantic-native — one def = contract + table; *lean*) vs SQLAlchemy vs Prisma-py.
2. **Deploy shape:** modular monolith now (microservice-ready; *lean*) vs services-from-day-one.
3. **HTMX ceiling:** flag any screen that genuinely needs rich client interactivity (the only place a thin-TS island over the auto-OpenAPI client is warranted).
> RESOLVED this session: UI = **server-rendered FastAPI + HTMX (no React/Next)**; **no component
> library / no JS framework** (the shadcn "ban" was a prototype artifact, moot here); polyglot
> deferred; objective = max deterministic assembly / min LLM cost.

## Recommended next steps (in order) — Python-first
1. **Author the canonical data contract** (Pydantic models / a schema) — the keystone input the SDK projects from.
2. **SDK build (charter §sequencing ii):** `PydanticModelProvider` (schema→Pydantic, generalize `render_zod_schema`) + **FastAPI CRUD + HTMX-template generators** + completeness/export emitters + a **Python project build/test gate** (generalize `run_project_typecheck` onto the Python LanguageProfile; preserve "absent ⇒ non-pass"). Register the provider via the shipped registry.
3. **Pilot one bounded context end-to-end:** model → generated CRUD → generated HTMX form/list → `$0.00` skip on regen + Python build gate green. Prove the loop, then widen.
4. **Author only the semantic core** (AI passes + non-CRUD logic) grounded on the generated contract, gated by the build.
5. **Defer:** polyglot (`ProtoStubProvider`/other languages), true service split — both future, per-need.

## Gotchas to remember
- The whole-project **tsc** gate is TS-specific + informational by default (`STARTD8_TS_GATE_STRICT=1` to enforce); the **Python** build gate is the one to build next (it doesn't exist yet).
- Don't resurrect the TS-spine route-handler generator OR a React/Next front end (both superseded); the UI is server-rendered HTMX.
- protobuf pin `>=6.33.5` is in pyproject; the pipeline `.venv` may need a reinstall to pick it up.
- The shipped `frontend_codegen` (Prisma→Zod) stays as a reference impl / provider; the next renderer is its Python sibling (Pydantic), same pattern.

*Companion handoffs: `CKG_NEXT_SESSION_HANDOFF.md` (separate CKG track).*
