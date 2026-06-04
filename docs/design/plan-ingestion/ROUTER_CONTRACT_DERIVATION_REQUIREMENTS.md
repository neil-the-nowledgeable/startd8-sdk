# Router Contract Derivation — Requirements

**Version:** 0.3 (external-review fixes folded in — bare-router / FR-10 split / verifier reuse)
**Date:** 2026-06-04
**Status:** Draft
**Owner:** neil-the-nowledgable
**Driver:** run-029 / run-032 boot failures; root-caused via Service Assistant + Semantic Compliance Reviewer

> **v0.3 fold-in (3 review fixes, all complexity-reducing):** **R2-F1** — the deterministic floor emits a
> **bare `APIRouter()`**, not a stem-derived `prefix=...` (synthesizing a prefix invents routing semantics
> and adds inference code; the keystone is *importability*, which the bare router gives). **R2-F2** — FR-7
> **reuses the existing `cross_file_verifier`** as the import↔export backstop instead of implying a new
> consumer-expectation model (that's OQ-6, deferred). **R2-F3** — FR-10 split into a MUST (bare router,
> deterministic, the boot-fix lock) and a SHOULD (bindings, only when prose states them) so the test stops
> asserting a guarantee FR-2 disclaims. Net: fewer moving parts, no new structures. Shares the root cause
> with `../micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md` — *requirements lose fidelity upstream of
> generation, in contract derivation; the defect is path-agnostic (run-029 LLM **and** run-032 $0 both
> failed identically).*

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass mapped each FR to real plan-ingestion seams and resolved the open questions
> against the code. It produced 4 material corrections — the biggest being that the **router object
> alone fixes app boot**, which dramatically narrows the v1 fix.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Route bindings as a structured `routes` field (OQ-1/FR-2) | `api_signatures` is **"consumed as prose, not structured"** (`implementation_engine/consumption_map.py:72`). A new `config.context.routes` field would be serialized to JSON but **read by no generator**. | **FR-2 corrected.** Represent the router as an **`api_signatures` STRING** (`"jobs_router = APIRouter(prefix='/jobs', tags=['jobs'])"`) — the existing `_extract_api_signatures` parses it as a VARIABLE element. **No new structured field.** |
| Router object *and* route bindings must both be in the contract, deterministically | The per-handler **method+path is NOT structured anywhere** — only in prose. **But the boot `ImportError` is on the router OBJECT, not the routes** — an empty `APIRouter()` still imports and `include_router()`-mounts, so the app **boots**. | **Keystone scoping.** **FR-1 (router object) is the deterministic keystone — it alone fixes boot.** FR-2 (per-route bindings) is **downgraded to best-effort/LLM** (functionality, not boot). v1 = guarantee the importable router. |
| Decomposition needs a new router-element strategy (FR-9) | `jobs_router = APIRouter()` parses as a **VARIABLE** element (`forward_manifest_extractor.py:786-805`); the decomposer has a strategy only for CLASS, so a VARIABLE is **passed through to generation unchanged** and emitted as a module-level directive. | **FR-9 simpler.** No new decomposition strategy — a router api_signature string flows through as a non-decomposed element and is emitted as-is. |
| Router name needs forward-manifest consumer reconciliation (FR-3/FR-7) | The forward manifest's `InterfaceContract` has **no consumer-expectation model** (no "a consumer expects to import X"). But the CRUD generator uses the convention `<prefix>_router` (`backend_codegen/crud_generator.py:118`), and `app/jobs.py`'s consumer imports `jobs_router`. | **FR-3 concrete.** Derive the name from prose if stated, else the **convention `<module_stem>_router`** (`jobs.py → jobs_router` — matches the consumer *and* the CRUD pattern). Full bidirectional import↔export reconciliation is deferred (no model exists) — OQ-6. |

**Resolved open questions:**
- **OQ-1 → RESOLVED.** Use `api_signatures` **strings**, not a structured `routes` field — strings are the only channel generators consume (`consumption_map.py`), and the existing VARIABLE parser handles `var = APIRouter()`.
- **OQ-2 → RESOLVED to a floor.** Method+path are prose-only; v1 **deterministically guarantees the router OBJECT** (fixes the ImportError → boot), and leaves per-route bindings to PARSE/LLM best-effort. An empty router still boots.
- **OQ-3 → RESOLVED.** Name = prose, else convention `<module_stem>_router`; declare authority via an `InterfaceContract` `IMPORT_PATH` `binding_text`.
- **OQ-4 → STANDS.** `plan-ingestion` is concurrently edited — sequence/branch the implementation.
- **OQ-5 → RESOLVED (negative).** The forward manifest cannot supply the consumer-expected name (no model); the convention is the deterministic substitute.
- **Seam (FR-4) confirmed:** `_enrich_api_signatures` at `plan_ingestion_enrichment.py:322`, invoked from `enrich_tasks_deterministic` (`:621/:684`); add the sibling `_enrich_router_signatures()` there, merging into `context["api_signatures"]` with dedup.

---

## 1. Problem Statement

HTTP "router" features consistently generate their **handler functions** but **omit the router
object and the route bindings**, producing a module that registers no routes. A consumer that
imports the router (`from app.jobs import jobs_router`) then fails at import → **the app does not
boot**. This recurs across runs and across generation paths.

### Verified root cause

The plan-ingestion **PARSE** phase derives a feature's structured contract `api_signatures` as
**only** class/function/method signatures (`plan_ingestion_workflow.py` ~L537/L563 —
`"Class X(Base)"`, `"def f(...)"`, `"def Cls.m(...)"`). It has **no provision** for:
- the module-level **router instantiation** (`jobs_router = APIRouter()`), nor
- the **function → route bindings** (`@router.get('/jobs')` / method+path → handler),

even though `protocol: http` is captured. And **no downstream step synthesizes them** — there is
no router enrichment in `plan_ingestion_enrichment.py`, `…_micro_ingest.py`, `seeds/`, or
`micro_prime/decomposer.py`. (The micro-ingest parser *can* read `var = APIRouter()` signatures
at `…_micro_ingest.py:150-169`, but it never receives any.)

Because both the LLM and the `$0` deterministic generators **build to `api_signatures`**, the
router and routes — absent from the contract — are never produced. This is **upstream of
generation**, so it is path-agnostic: the LLM path (run-029, $1.08) and the deterministic path
(run-032, $0) both omitted the router.

### Evidence (run-032, `PI-001` "Jobs dashboard router")

| Signal | Value |
|--------|-------|
| Requirement prose | "Implements the **jobs_router** APIRouter providing GET /jobs and GET /job/{id}" |
| Derived `api_signatures` | `[def jobs_dashboard(...), def job_workspace(...), def resolve_matches(...)]` — **functions only** |
| `protocol` | `http` |
| Generated `app/jobs.py` | helper/handler functions, **no `APIRouter`, no `jobs_router`, no `@router.get`** |
| Consumer | `app/user_routers.py:10` → `from app.jobs import jobs_router` |
| Outcome | ImportError → `app does not boot (app.server:app)` → post-mortem `FAIL:boot` |

The Semantic Compliance Reviewer (FR-17) independently flagged this as a **critical
`missing_route` / `missing_route_handlers`** and emitted the precise Kaizen fix — but a prompt-hint
only helps the LLM path; the durable fix is to put the router into the **contract** so *every*
path emits it (FR-14: a deterministic re-run is otherwise idempotent and reproduces the defect).

### Gap table

| Contract element | Today | Gap |
|------------------|-------|-----|
| Handler functions | extracted into `api_signatures` | ✅ present |
| Router object (`<name>_router = APIRouter()`) | not modeled | **missing** — consumer import fails |
| Route bindings (method + path → handler) | not modeled | **missing** — no routes registered |
| Router symbol name ↔ consumer import | not reconciled | **missing** — cross-file contract breaks |
| Protocol-aware synthesis | `protocol: http` captured but unused | **missing** — nothing acts on it |

---

## 2. Goals & Non-Goals (summary)

**Goal:** Make the plan-ingestion structured contract for an HTTP feature **completely describe its
public routing surface** — the router object, its name (matching consumers), and each handler's
method+path binding — so **both** the LLM and the deterministic generators emit an importable
router with registered routes, and the app boots.

**Not a goal (v1):** generating the route handler *bodies* (existing generation already does the
functions); changing the `backend_codegen` entity-CRUD routers (those work); supporting non-HTTP
protocols; non-FastAPI frameworks beyond the project stack.

---

## 3. Requirements

### Contract completeness

- **FR-1 — Router object in the contract (KEYSTONE).** For a feature with `protocol == "http"` whose
  target is a source module exposing handler functions, the derived contract SHALL include the
  module-level **router instantiation** as an `api_signatures` **string**, so the existing
  `_extract_api_signatures` VARIABLE parser emits an **importable** router symbol. *This alone closes
  the boot failure* — the consumer `ImportError` is on the router symbol, and an empty `APIRouter()`
  still imports and `include_router`-mounts. **This is the deterministic v1 floor (FR-4).**
  **v0.3 (R2-F1 — bare router, do not invent routing semantics):** the deterministic floor SHALL emit a
  **bare `"<name> = APIRouter()"`** — **not** `APIRouter(prefix=..., tags=...)`. A synthesized `prefix`
  derived from the module stem is an *invented routing decision*: it silently changes every route's path
  (risking doubled prefixes `/jobs/jobs`, or a mount the consumer's `include_router` didn't expect). The
  keystone guarantee is *importability*, which the bare router fully satisfies. `prefix`/`tags` are
  routing *semantics* → they belong to FR-2 (best-effort, only when the prose states them), never to the
  deterministic floor. This also keeps FR-4 free of any stem→prefix inference logic (less code, no
  guess).

- **FR-2 — Route bindings + prefix/tags (best-effort, not the boot-blocker).** The contract SHOULD bind
  each handler to its HTTP **method + path** (`GET /jobs → jobs_dashboard`) so the generator emits route
  registrations (`@router.get('/jobs')`), and MAY include `prefix`/`tags` **when the requirement prose
  states them**. However, method+path (and prefix/tags) are **prose-only** (not structured anywhere
  post-PARSE), so v1 does **not** guarantee them deterministically — they are extracted by PARSE (FR-5) /
  inferred by the LLM **best-effort**. They affect route *functionality*, not app *boot* (FR-1's bare
  router already restores boot). They SHALL be expressed as `api_signatures` strings or prose, **not** a
  new structured field (OQ-1: generators consume api_signatures as prose).

- **FR-3 — Router name = consumer import name.** The router symbol name SHALL be derived to **match
  what consumers import** (e.g. `app/user_routers.py` does `from app.jobs import jobs_router`).
  Derivation precedence — given the forward manifest has **no** consumer-expectation model (OQ-5):
  (a) a name stated in the requirement prose ("jobs_router"); (b) the deterministic convention
  **`<module_stem>_router`** (`app/jobs.py → jobs_router`), which matches both the consumer here and
  the `backend_codegen` CRUD pattern (`crud_generator.py:118`). The chosen name SHALL be recorded as
  an `InterfaceContract` (`IMPORT_PATH`) `binding_text` so generation is anchored to it.

### Synthesis (the durable, path-agnostic fix)

- **FR-4 — Deterministic router enrichment (primary).** Plan-ingestion SHALL add a **deterministic
  enrichment step `_enrich_router_signatures()`** in `plan_ingestion_enrichment.py` (sibling to
  `_enrich_api_signatures:322`, invoked from `enrich_tasks_deterministic:684`) that, when
  `protocol == "http"` and no router symbol is present in `api_signatures`, **synthesizes the bare router
  object** (FR-1: `"<name> = APIRouter()"`, no prefix/tags) named per FR-3 and appends it to
  `context["api_signatures"]` with **merge-dedup** (mirroring `:340`) — independent of any LLM call. This
  guarantees the `$0` deterministic path produces an importable router (the run-032 failure mode FR-14
  could not otherwise fix). Route *bindings* and prefix/tags (FR-2) are out of this deterministic step's
  guarantee — keeping the step a pure string-synthesis with **no path/prefix inference**. Returns a count
  for diagnostics.

- **FR-5 — PARSE extraction (secondary).** The PARSE prompt SHALL be extended to **extract** an
  explicitly-stated router instantiation and route bindings from the plan when present
  (`plan_ingestion_workflow.py` api_signatures guidance). When PARSE captures them, FR-4 SHALL NOT
  duplicate (FR-8).

- **FR-6 — Framework-aware.** Synthesis SHALL be **framework-aware** for the project stack — v1:
  **FastAPI `APIRouter`** (the all-Python/FastAPI pivot). The representation SHALL be extensible to
  Flask `Blueprint` / others later, but v1 scope is FastAPI.

### Integrity

- **FR-7 — Cross-file contract alignment (reuse the existing verifier).** The synthesized/extracted
  router symbol SHALL be recorded as a provider-side export the **existing** cross-file verifier
  (`validators/cross_file_verifier.py` / `cross_file_imports.py`, already gating the verdict via the CKG
  Phase-1 path) can reconcile against consumer imports (`from app.jobs import jobs_router`). This is the
  **design-time/post-gen backstop** that catches an FR-3 convention-mismatch *before* runtime boot-smoke
  (NR-5) — **without** adding a new model. **v0.3 (R2-F2):** do NOT build a new consumer-expectation
  contract for v1; the verifier already checks import↔export, and the FR-3 `<module_stem>_router`
  convention + the verifier backstop together cover the run-032 case. The full bidirectional model is
  OQ-6 (deferred).

- **FR-8 — Idempotent, non-duplicating.** If the contract already declares a router (PARSE extracted
  it, or a prior enrichment ran), enrichment SHALL NOT add a second router or duplicate route
  bindings. Re-ingesting the same plan SHALL be stable.

- **FR-9 — Decomposition passes the router element through.** No new decomposition strategy is
  required: a `var = APIRouter()` api_signature is extracted as a **VARIABLE** `ForwardElementSpec`
  (`forward_manifest_extractor.py:786-805`), and since `micro_prime/decomposer.py` has a strategy only
  for CLASS, the VARIABLE is **passed through to generation unchanged** and emitted as a module-level
  directive. The requirement is therefore that the router VARIABLE element SHALL survive ingestion
  intact through to emission (it does today once FR-1/FR-4 put it in `api_signatures`).

### Observability / validation

- **FR-10 — Verifiable (split per the FR-1/FR-2 guarantee boundary).** **v0.3 (R2-F3):** the original
  single assertion conflated the deterministic guarantee with the best-effort layer. Split:
  - **(a) MUST — deterministic floor.** A test SHALL assert that the run-032 `PI-001` shape (3 handlers,
    `protocol: http`, no router) is enriched by `_enrich_router_signatures()` to include the **bare
    `jobs_router = APIRouter()`** symbol — the guarantee FR-1/FR-4 actually make, on the $0 path with no
    LLM. This is the boot-fix regression lock.
  - **(b) SHOULD — best-effort bindings.** A test SHALL assert that **when the prose states method+path**
    (PI-001's prose does: "GET /jobs and GET /job/{id}"), PARSE (FR-5) captures the `GET /jobs` /
    `GET /job/{id}` bindings — but this is NOT asserted on the binding-free deterministic path, because
    FR-2 does not guarantee it there.

---

## 4. Non-Requirements

- **NR-1.** Does not generate route handler **bodies** — existing generation produces the functions;
  this fills only the router object + route wiring gap.
- **NR-2.** Does not alter `backend_codegen` entity-CRUD routers (those already emit routers).
- **NR-3.** Non-HTTP protocols (grpc/cli/library) are out of scope — gRPC servicer modeling already
  exists in PARSE.
- **NR-4.** Non-FastAPI frameworks beyond the project stack are deferred (FR-6 leaves the seam).
- **NR-5.** Not a runtime fix — this is design-time contract completeness; the boot-smoke remains the
  backstop.

---

## 5. Open Questions

> OQ-1, OQ-2, OQ-3, OQ-5 were resolved by the planning pass — see §0. Retained condensed; OQ-4
> stands and OQ-6 is new.

- **OQ-1 → RESOLVED.** `api_signatures` strings, not a structured `routes` field (generators consume api_signatures as prose).
- **OQ-2 → RESOLVED (floor).** Router OBJECT guaranteed deterministically (fixes boot); per-route bindings are PARSE/LLM best-effort.
- **OQ-3 → RESOLVED.** Name = prose, else `<module_stem>_router` convention; recorded as an `InterfaceContract` `IMPORT_PATH` binding_text.
- **OQ-4 — STANDS (coordination).** `plan-ingestion` is under active concurrent development
  (`plan_ingestion_workflow.py` / `_models.py` / `_diagnostics.py`). The `_enrich_router_signatures`
  addition (`plan_ingestion_enrichment.py`) must be sequenced/branched to avoid colliding with
  in-flight edits.
- **OQ-5 → RESOLVED (negative).** The forward manifest has no consumer-expectation model, so the
  existing consumer's expected name can't be read structurally; the `<module_stem>_router` convention
  is the deterministic substitute (it happens to match the real consumer here).

### New open question surfaced during planning

- **OQ-6 — Bidirectional import↔export reconciliation (deferred).** The deeper fix — design-time
  validation that every consumer's expected import (e.g. `from app.jobs import jobs_router`) matches a
  declared export — has **no model** in `forward_manifest` today (only provider-side
  `ForwardElementSpec.name`, no consumer-expectation contract). v1 sidesteps it via the naming
  convention. Should a consumer-expectation contract be added so router-name mismatches are caught at
  ingest rather than at runtime boot? (Larger lift; would also catch non-router cross-file drift.)

---

*v0.2 — Post-planning self-reflective update. 5 requirements revised (FR-1/2/3/4/9), 4 open questions
resolved, 1 new (OQ-6). Key insight: the **router object alone fixes boot**, so the v1 deterministic
fix narrows to synthesizing one importable `APIRouter()` api_signature string (named by convention)
in a new `_enrich_router_signatures()` step — route *bindings* are a separate best-effort concern.*

*v0.3 — External-review fixes folded in (R2-F1/F2/F3), all **complexity-reducing**: bare-router floor (no
invented prefix → no stem-inference code), verifier-reuse for FR-7 (no new model), FR-10 split to match
the actual guarantee boundary. No new requirements; the v1 surface is now **one deterministic
string-synthesis step + a regression test + reuse of the existing verifier**. CRP **not warranted** (no
architectural contention; the one architectural item, OQ-6, is deferred). Ready for implementation —
coordinate per OQ-4 (concurrent plan-ingestion edits).*
