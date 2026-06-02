# Ideal Target-App Architecture — Maximum Deterministic Assembly, Minimum LLM Cost

**Date:** 2026-06-02 · **Status:** canonical (supersedes the TS-framed
`STARTDATE_NEXT_ITERATION_ARCHITECTURE_GUIDANCE.md`) · **Companion:**
`deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`

> **Premise.** "StartDate" was a prototype and is retired; the real app is **greenfield,
> designed to fit the SDK** (not retrofitted). The governing objective is **maximum (reasonable)
> deterministic assembly to keep LLM cost as low as possible** — the LLM is spent only on the
> irreducibly-semantic work; everything mechanical is generated for $0. Verified constraints:
> the SDK's shape is **microservices**; its strongest language is **Python** (first-built, thus
> accidentally best); **polyglot is optional, not required**.

---

## 1. The architecture (one sentence)

**An all-Python, contract-first, server-rendered application — FastAPI + Pydantic + HTMX +
Jinja — structured as microservice-ready bounded contexts** (online-boutique *shape*, Python-
homogeneous; split into deployed services only when needed).

This is chosen on a single criterion — **how much of it the SDK can assemble deterministically**
— and it wins decisively over the prior TS/React/Next direction.

---

## 2. Why this maximizes deterministic assembly (the cost argument)

The prior TS/React stack capped at ~35–45% deterministic (the React UI was hand-authored,
semantic). This stack inverts the UI from *semantic* to *mechanical*:

- **Server-rendered + HTMX ⇒ the UI is templated from the contract.** Lists, detail views, and
  **edit forms** are a deterministic function of the Pydantic model (field → input). No JS
  framework, no component library, no client-side type graph — i.e. the **run-015/016/017
  invention classes don't exist**, and the largest semantic bucket (React components) becomes
  generatable HTML.
- **Contract-first ⇒ the data/validation/DTO layer is generated** (Pydantic = the Python Zod).
- **FastAPI CRUD handlers are templatable** (validate Pydantic → ORM op → response/render).
- **Net:** the deterministic ceiling rises to an estimated **~60–75%** of the codebase, vs
  ~35–45% for TS/React. Every point is LLM spend removed. The LLM is reserved for the genuinely
  semantic ~25–40%: the **AI passes** and non-CRUD business logic.

> Determinism *is* the cost lever: deterministic assembly = $0 LLM + caught-by-construction;
> the skip-hook marks owned files `GENERATED $0.00` so regeneration is free and never re-invented.

---

## 3. The determinism boundary (this stack)

| Layer | Owned (deterministic, $0 LLM) | Seeded / semantic (LLM — grounded + gated) |
|-------|-------------------------------|---------------------------------------------|
| Data contract | **Pydantic models** from the canonical schema (the value-model renderer, generalized) | — |
| Persistence | ORM models + the DB client/session (SQLModel/SQLAlchemy or Prisma-py) | non-trivial query logic |
| API | **FastAPI CRUD routes** (validate → ORM op → respond) + auto-OpenAPI | non-CRUD endpoints' business logic |
| UI | **HTMX/Jinja templates** for list / detail / **edit forms** / partials, generated from the model | bespoke interaction flows, copy, the wizard's *orchestration* |
| Derived | **completeness** (pure fn from a declared signal set), **export** (JSON pure; MD from a declared layout) | — |
| AI | the **tool/IO schemas** the AI passes use (generated from the contract) | the **AI passes themselves** (extract / enrich / synthesize) — the product's intelligence |
| Plumbing | config (`pyproject`, Dockerfile, compose), service scaffold, inter-context clients | — |

**Rule:** if it's derivable from the contract or a small declared manifest, the SDK generates it
(owned). The LLM only authors what requires product judgment, grounded against the generated
contracts and gated by the Python build/test.

---

## 4. The contract layer (Python-native, one source of truth)

- **Canonical data model → Pydantic models** — the same projection the shipped `value-model.ts`
  renderer does (schema→Zod), now schema→Pydantic. Projected into every bounded context; nothing
  is hand-typed twice.
- **FastAPI auto-generates OpenAPI** from those models — so if any rich-client surface is ever
  needed (a JS island, mobile), the typed client is generated for free, no SDK work and no
  invention.
- **Inter-context contracts:** start with the in-process Pydantic contract; promote to OpenAPI
  (or gRPC/proto) only when a context is split into a deployed service.

---

## 5. The SDK work this implies (Python-first, small)

This is **not** the full 5-language `ProtoStubProvider`. The concrete first build is a **Python
contract-codegen provider**, reusing everything already shipped:

1. **`PydanticModelProvider`** — schema/contract → Pydantic models (generalize `render_zod_schema`
   to a Python emitter), registered via the shipped `DeterministicFileProvider` registry.
2. **FastAPI CRUD + HTMX-template generators** — the spine, as string templates (the proven
   pattern), project-convention-true.
3. **A Python build/test gate** — generalize `ts_toolchain.run_project_typecheck` to the SDK's
   Python `LanguageProfile` (it's the strongest profile): `python -m compileall` / `mypy` /
   `pytest` as the by-construction gate; loud-degrade when absent (never a silent pass).
4. **Reuse as-is:** the owned-file skip-hook (`$0.00`), drift/`--check`, the provider registry,
   the import/missing-dep checks. The completeness/export generators are small pure emitters.

Polyglot (`ProtoStubProvider` across the other 4 languages) stays a **future option** behind the
same registry — add it per-service only when a real cross-language need appears.

---

## 6. Deployment shape: modular monolith now, services when needed

The SDK's strength is the microservices *shape*, but a single greenfield app pays orchestration
tax for true services on day one. **Recommended: a Python *modular monolith* with
microservice-ready bounded contexts** (clear module boundaries + contract discipline), one
deployable. Split a context into a deployed service only when scale/ownership demands it — at
which point its in-process Pydantic contract is promoted to OpenAPI/gRPC and the SDK generates the
client. This serves *move-fast + low-cost* without foreclosing the online-boutique microservices
end-state.

---

## 7. Anti-patterns designed out (the run-015/016/017 lessons, structurally)

- **No JS framework / component invention** — server-rendered HTMX has no component-library
  surface to invent (the shadcn class is gone).
- **No cross-file type drift** — one contract, projected; nothing hand-typed twice.
- **No invented module paths** — canonical layout + generated imports; the build gate fails on
  invention.
- **No hand-written CRUD/forms** — generated from the contract.

---

## 8. Sequencing

**App team:** (1) author the **canonical data contract** (Pydantic / a schema) — the keystone
input; (2) accept the generated spine (models, CRUD, HTMX forms/lists, config); (3) author only
the AI passes + non-CRUD logic, grounded + gated.
**SDK team:** (1) `PydanticModelProvider` + register it; (2) FastAPI/HTMX/CRUD generators; (3) the
Python build/test gate; (4) pilot one bounded context end-to-end (model → CRUD → HTMX form →
$0.00 skip on regen) to prove the loop, then widen.

---

## 9. Confirm / open
- **UI:** server-rendered FastAPI + HTMX + Jinja — **LOCKED.** (Thin-TS-SPA over generated
  OpenAPI is a per-screen escape hatch only if a screen needs rich client interactivity.)
- **ORM:** SQLModel (Pydantic-native, least impedance) vs SQLAlchemy vs Prisma-py — *lean
  SQLModel* (one model definition doubles as contract + table). Confirm.
- **Monolith-first vs services-first** (§6) — *lean modular monolith*, microservice-ready.
- **HTMX interactivity ceiling** — fine for forms/lists/wizard; flag any screen that truly needs
  a rich client.

---

## 10. One-paragraph summary

Build the real app as an **all-Python, contract-first, server-rendered (FastAPI + Pydantic +
HTMX) modular monolith with microservice-ready bounded contexts.** It maximizes the fraction the
SDK assembles deterministically (~60–75% — the UI becomes templated HTML, not hand-written
React), which directly minimizes LLM cost; it plays to the SDK's strongest language (Python) and
its microservices shape; and it structurally deletes the run-015/016/017 invention classes. The
SDK's first build is a small **Python contract-codegen provider + Python build gate** reusing the
shipped registry/skip-hook/gate pattern — *not* the full polyglot kernel, which stays a future
per-service option.
