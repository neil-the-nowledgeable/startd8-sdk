# Deterministic Frontend SPINE Generation — Requirements

> **⚠️ SUPERSEDED (2026-06-02) — do not implement as written.** The TS-Next-specific "spine"
> (route-handler generator, input-schema/db/completeness/export templates, the codegen manifest)
> is deprioritized: the SDK is re-anchoring on **polyglot microservices** (online-boutique style),
> and a TS-monolith frontend generator would be narrow tech debt. **What survives is the PATTERN,
> not these TS templates** — deterministic schema/contract→code generation + the owned-file
> skip-hook + the by-construction verification gate — now generalized in
> **`DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`**. This doc is kept for historical reasoning and
> for the reflective-requirements §0 record (the planning pass that falsified the v0.1 assumptions
> is itself reusable evidence). Do not start the FRs below.

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-02
**Status:** Draft for review — pairs with `DETERMINISTIC_FRONTEND_SPINE_PLAN.md`
**Grounding:** `DETERMINISTIC_FRONTEND_SCOPE_ANALYSIS.md` (the strtd8 determinism boundary:
~35–45% realistically deterministic vs ~5% today). Generalizes the proven `value-model.ts`
renderer (Inc 1–8b) from **one** artifact to the deterministic **spine**.
**Reuses (don't rebuild):** `languages/prisma_parser`, `project_knowledge.FieldSpec/
FieldSetAuthority`, `frontend_codegen.{schema_renderer,conventions,gates,drift,skeleton}`,
the prime-contractor owned-file skip-hook, `validators.ts_toolchain.run_project_typecheck`,
`validators.cross_file_imports.{scan_unresolvable_imports,scan_missing_dependencies}`.

> **What this is.** Extend `frontend_codegen` to deterministically generate the *mechanical
> spine* of a Next.js/Prisma/Zod app — **owned** route handlers, input schemas, the completeness
> function, export, the db client, and the AI tool-schemas — plus **seeded** import-shells for
> the semantic files. Goal: prevent the RUN-011…017 invention/compile-error class **by
> construction** across the spine, and free the LLM's budget for the irreducible semantic core
> (AI passes + UX). Not "build the app for free" — carve the mechanical 45% out of the LLM's hands.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (stress-testing against strtd8's **real** 24 routes + App-Router idiom)
> falsified several v0.1 assumptions. The big one: **route generation is not derivable from the
> Prisma schema alone — it needs a declared manifest.** Eight corrections:

| v0.1 Assumption | Planning Discovery (verified vs strtd8) | Impact |
|-----------------|------------------------------------------|--------|
| Routes derive 1:1 from the 12 models | strtd8 has **24 routes ≠ 12 models**: CRUD resource pairs (collection `route.ts` + item `[id]/route.ts`), **8 AI-trigger** routes (`ai/extract`, `ai/enrich-*`, `ai/tailor-match`…), and action routes (`completeness`, `export`, nested `[id]/matches`). It even has **duplicate/overlapping** routes (`ai/enrich-*` *and* `enrich/*`) — LLM-invented structure. | **FR-10 added: a declared codegen manifest** (resources→CRUD, action/AI routes→pass bindings) is the required input beyond the schema. The duplication is itself the case for manifest-driven generation. |
| Route handlers use `NextResponse` | strtd8 uses the **Web `Response` / `Response.json(...)`** idiom, `(request: Request): Promise<Response>` | **FR-9: convention detection must capture the response idiom** (`Response` vs `NextResponse`); generated code is project-true, not idiom-assumed. |
| POST/PATCH validate the entity Zod schema | the real POST defines an **input schema** (omits server fields; adds `capabilityIds`/`outcomeIds` link arrays) | **FR-3 added: input-variant schema generation** — Create (omit `id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt`; relations→`<rel>Ids` arrays) + Update (partial). The full schema is wrong for write bodies. |
| "db.ts + migrations" are both generatable files | `db.ts` is a file; **migrations are a `prisma migrate` toolchain action**, not a rendered file | **FR-6 split:** generate `db.ts` (file); migrations = a toolchain step the pipeline/prisma owns (out of file-gen scope, like `ts-verify-gate` running `prisma generate`). |
| Completeness is a pure function from the signal set | the score is pure over a **counts object**, but the counts need DB queries (`confirmed:true`) | **FR-4 refined:** owned artifact = `computeCompleteness(counts)` (pure) + a thin generatable count-query helper. |
| Export (MD+JSON) is fully deterministic | **JSON** is; **Markdown** needs a declared per-entity layout (headings/field order) | **FR-5 refined:** JSON serializer = pure; MD renderer = template driven by a declared layout in the manifest. |
| Templating engine is an open question (string vs AST) | the `value-model.ts` renderer proves **string templates** are sufficient and gate-verifiable; TS has no clean Python AST emitter | **OQ resolved → string templates** (the `render_zod_schema` pattern), verified by the tsc gate + import checks. |
| Verify owned artifacts via the Prisma↔Zod symmetry gate | symmetry/fidelity is **schema-file-specific**; route/db/export can't be symmetry-checked | **FR-11 generalized:** owned artifacts verify via the **whole-project `tsc` gate** (`ts_toolchain`, now live) + **import-resolution/missing-dep** checks (`cross_file_imports`); the schema file keeps symmetry+fidelity. |

**Resolved open questions:**
- **OQ-A → A declared manifest is required** (FR-10), not pure-schema derivation.
- **OQ-B → String templates**, not an AST emitter.
- **OQ-C → Auto pre-write is now critical** (the spine is ~30 owned files; manual generation
  doesn't scale) — pull the deferred pre-write into scope (FR-12), still drift-/dirty-tree-safe.

Remaining open questions: OQ-1…OQ-4 in §6.

---

## 1. Problem Statement & Gap

`frontend_codegen` deterministically generates exactly **one** artifact today — the Prisma→Zod
`value-model.ts` (~5% of the strtd8 codebase). The scope analysis shows ~35–45% is realistically
deterministic. The untapped spine is where RUN-017's 28 compile errors lived (route/page/`lib/ai`
invention).

| Spine artifact | strtd8 files | Deterministic | Generated today |
|----------------|-------------:|---------------|-----------------|
| Schema types (`value-model.ts`) | 1 | ✅ | ✅ |
| **Route handlers (CRUD + AI-trigger)** | **24** | ◑ high | ❌ |
| Input schemas (Create/Update) | (in routes) | ✅ | ❌ |
| Completeness function | ~1 | ✅ | ❌ |
| Export (MD/JSON) | ~1–2 | ✅/◑ | ❌ |
| `db.ts` client | 1 | ✅ | ❌ |
| AI tool-use Zod schemas | (in `lib/ai`) | ✅ | ❌ |
| Route/page import-shells | 24+14 | ◑ shell | ❌ |

---

## 2. Goal

A deterministic (no-LLM) generator that emits the app's **owned** mechanical spine from the
Prisma schema **+ a small declared manifest**, project-convention-true, passing the
whole-project `tsc` gate and import-resolution checks **by construction**; plus **seeded**
import-shells for semantic files. Reuse every existing `frontend_codegen` primitive; the
generators are new *targets* of the proven renderer pattern, not a new capability class.

---

## 3. Functional Requirements

### FR-1 — CRUD route-handler generator (owned, highest leverage)
For each resource declared CRUD in the manifest (FR-10), emit the App-Router pair: a collection
`app/api/<resource>/route.ts` (`GET` list, `POST` create) and an item
`app/api/<resource>/[id]/route.ts` (`GET` one, `PATCH` update, `DELETE`). Each handler:
Zod-validates the body against the generated input schema (FR-3), performs the Prisma op via the
canonical `db` import, and returns via the **detected response idiom** (FR-9). Imports are
canonical (no invented paths).
*Acceptance:* for strtd8's `proof-points` resource the generated pair compiles under the
whole-project `tsc` gate (0 errors), `GET` returns `db.proofPoint.findMany`, `POST` validates +
`db.proofPoint.create`, and no import is unresolvable (`scan_unresolvable_imports` = []).

### FR-2 — AI-trigger route generator (owned shell → seeded pass)
For each declared AI/action route, emit a thin **owned** wrapper: validate the request body
(Zod), call the named pass function by its **canonical** import path, return its result via the
response idiom. The pass module itself is **seeded** (LLM-authored logic), but the wrapper +
import path are owned/deterministic — killing the `@/lib/ai/tailoring`-style path invention.
*Acceptance:* the `ai/tailor-match` route imports `tailorJobDescription` from the canonical
module path (matches the file on disk), validates `{ jobDescriptionId }`, and compiles.

### FR-3 — Input-schema generation (Create / Update variants)
Derive write-body Zod schemas from the entity field model (reuse the FieldSpec projection):
**Create** = omit server-managed fields (`id`, `ownerId`, `source`, `confirmed`, `createdAt`,
`updatedAt`) and represent relations as `<relation>Ids: z.array(z.string())`; **Update** =
`.partial()` of Create. These are what FR-1 POST/PATCH validate against.
*Acceptance:* a generated `ProofPointCreate` omits the 6 server fields, includes
`capabilityIds`/`outcomeIds` arrays, and `ProofPointUpdate` accepts a subset; both `z.parse`
the route's test fixtures.

### FR-4 — Completeness function generator (FR-9)
Emit a **pure** `computeCompleteness(counts) -> { score, nudges[] }` from a **declared signal
set** (default: Profile present, ≥3 confirmed ProofPoints, ≥1 confirmed Outcome, ≥1 Metric,
≥1 Differentiator; nudges in that priority order), plus a thin count-query helper that supplies
`counts`. The scoring is deterministic; nudges never block.
*Acceptance:* `computeCompleteness` over a fixture counts object returns the expected score +
next nudge; the function has zero side effects / no DB import.

### FR-5 — Export generator (FR-10 of strtd8)
Emit a **JSON** serializer (pure structured-data dump, round-trip faithful) and a **Markdown**
renderer driven by a **declared per-entity layout** (headings + field order) in the manifest.
*Acceptance:* the value model exports to JSON and MD; the JSON round-trips its structured fields;
the MD contains each declared section.

### FR-6 — Prisma client (`db.ts`) generator
Emit the canonical Prisma client singleton (`export { db }`, dev-global guard). **Migrations are
out of file-gen scope** — `prisma migrate`/`generate` is a toolchain step the pipeline owns
(as `ts-verify-gate` already runs `prisma generate`).
*Acceptance:* generated `db.ts` exports `db: PrismaClient`; importing `{ db }` resolves (no more
`{ prisma }`/`@/lib/prisma` invention).

### FR-7 — AI tool-use Zod schema generator
Emit the structured-output target schemas the seeded AI passes import (reuse `render_zod_schema`
on the relevant entities). The passes' **I/O contract is owned/deterministic** even though the
pass logic is seeded.
*Acceptance:* the generated tool schema passes `verify_render_fidelity`; the seeded pass imports
it by canonical path.

### FR-8 — Route/page import-shell generator (seeded)
For semantic files (pages, components, AI passes), optionally emit a **seeded** shell: canonical
imports (the detected alias, the real `db`/schema/tool-schema paths) + the handler/component
signature, with a guarded body region for the LLM to fill.
*Acceptance:* a seeded page shell imports only resolvable modules and carries
`export default function Page(): JSX.Element` with a marked body stub.

### FR-9 — Convention detection extension
Extend `detect_project_conventions` to capture the **response idiom** (`Response.json` vs
`NextResponse`), the API-route layout, and the alias — so FR-1/FR-2 emit project-true code.
*Acceptance:* against strtd8, detection reports `response_idiom="web-response"` (`Response.json`),
`alias=@/→./`; generated handlers use `Response.json`, not `NextResponse`.

### FR-10 — Declared codegen manifest (the required input beyond the schema)
A small declared spec (file or derived from the plan's task manifest) listing: which entities get
CRUD routes; the action/AI routes and their **pass-function bindings** (name + canonical module
path); the export layout; and the completeness signal set. This is what makes route generation
deterministic (the schema can't say *which* routes exist).
*Acceptance:* a manifest produces exactly the declared route set; an entity absent from the
manifest gets no route; a route whose pass binding doesn't resolve is flagged, not emitted-broken.

### FR-11 — Verification by construction (generalized gates)
Every **owned** artifact must pass, by construction: (a) the **whole-project `tsc` gate**
(`ts_toolchain.run_project_typecheck`) with no error attributable to it, and (b)
**import-resolution** (`scan_unresolvable_imports` = []) + **declared-dependency**
(`scan_missing_dependencies` = []) checks. The schema/tool files additionally keep
`assert_symmetric` + `verify_render_fidelity`. A generator whose output fails these is a build
break, caught in CI.
*Acceptance:* the full generated spine for a fixture project yields 0 tsc errors + 0 unresolvable
imports + 0 missing deps; a deliberately broken template is caught.

### FR-12 — Wiring: CLI + skip-hook + auto pre-write
Extend `startd8 generate frontend` to emit the whole spine to `--out`/`--project`. The
prime-contractor **owned-file skip-hook** recognizes **all** owned spine artifacts (not just
`value-model.ts`). **Pull the deferred auto pre-write into scope** (FR-8B): render + write the
owned spine in the pre-generation hook, drift-aware (only write absent/in-sync; surface
tampered) and sequenced around the dirty-tree gate — because a ~30-file spine can't be
hand-generated per run.
*Acceptance (CLI):* one command writes the spine + a manifest of owned/seeded artifacts.
*Acceptance (hook):* a feature targeting any in-sync owned spine file is skipped at `$0.00`.

### FR-13 — Single source of truth (no parallel field model)
All generators consume the shared `project_knowledge` `FieldSpec`/`FieldSetAuthority` projection
and `render_zod_schema`; none defines its own field model (per the prior FR-13). The input-schema
and tool-schema variants are derived transforms of that one projection.
*Acceptance:* a property test asserts every generator's field set ≡ the shared projection for a
given schema.

---

## 4. Non-Functional Requirements
- **NFR-1 No-LLM, deterministic, byte-idempotent** (source order, no set iteration; per the prior FR-4 determinism rules).
- **NFR-2 Reuse-not-rebuild** — generators are new targets of the existing renderer/gate/convention primitives; reconcile `skeleton.py`'s local barrel/css emitters with the now-present `repair/retry/scaffold`.
- **NFR-3 Project-truthful** — every artifact follows detected conventions (alias, response idiom, app-router layout), never framework-default priors.
- **NFR-4 Owned files inert to the LLM** — marked + skip-hook-recognized + (FR-12) excluded from the LLM feature set.
- **NFR-5 Telemetry** — extend the `startd8.frontend_codegen` meter with per-artifact-class counts.

## 5. Non-Requirements (semantic — stays LLM)
- **NOT** the AI passes' prompts / extraction-synthesis logic (only their owned I/O schemas + route wrappers).
- **NOT** page/component **UX**, layout, interaction, or copy (only seeded import-shells).
- **NOT** the wizard / progressive-depth flow (FR-2/FR-11 of strtd8).
- **NOT** business rules beyond CRUD; **NOT** running migrations (toolchain owns that).
- **NOT** generating the Prisma schema itself (it remains the hand-authored source of truth; deferred).

## 6. Open Questions
- **OQ-1 — Manifest source.** A hand-authored `frontend-codegen.yaml`, or derived from the
  plan-ingestion task/file manifest the pipeline already has? *(Lean: derive from the plan
  manifest where possible; allow an override file.)*
- **OQ-2 — Relation-link inference.** Can Create-schema relation arrays (`capabilityIds`) be
  derived purely from the Prisma relations, or do some need declaring? *(Plan to verify against
  all 12 models.)*
- **OQ-3 — Auto pre-write vs dirty-tree gate.** Exact sequencing so writing ~30 owned files
  doesn't trip `check_git_status` (commit-then-skip vs an owned-file allowlist in the gate).
- **OQ-4 — Seeded shells: worth it now?** Or defer FR-8 until owned routes/db/completeness/export
  prove out? *(Lean: defer FR-8; owned artifacts are the leverage.)*

## 7. Relationship to the roadmap
- **Generalizes** the `value-model.ts` renderer (Inc 1–8b) to the spine — same pattern, more targets.
- **Closes the RUN-017 surface deterministically**: route/db/import-path invention becomes impossible for owned artifacts; the tsc gate (now live) backstops the rest.
- **Sequenced by leverage:** FR-1 routes (biggest) → FR-3 input schemas (routes need them) → FR-6 db + FR-9 conventions (routes need them) → FR-4 completeness, FR-5 export, FR-7 tool-schemas → FR-12 wiring/pre-write → FR-8 seeded shells (deferred).

---

*v0.2 — Post-planning self-reflective update: route generation reframed around a **declared
manifest** (FR-10, the headline correction — 24 routes ≠ 12 models); response-idiom convention
detection added (FR-9, strtd8 uses `Response.json` not `NextResponse`); **input-schema variants**
added (FR-3); db/migrations split (FR-6); completeness + export refined to pure-fn-plus-thin-query
and declared-layout; templating resolved to string templates; verification generalized to the
tsc + import-resolution gates (FR-11); auto pre-write pulled in (FR-12). Pairs with
`DETERMINISTIC_FRONTEND_SPINE_PLAN.md`. CRP review offered before implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

### Appendix A: Applied Suggestions
_None yet._

### Appendix B: Rejected Suggestions (with Rationale)
_None yet._

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_Awaiting first review round._
