# Front-End Work — Next-Session Handoff

**Date:** 2026-06-02 · **Picks up:** the deterministic-frontend → contract-codegen pivot.
**Read first:** `STARTDATE_NEXT_ITERATION_ARCHITECTURE_GUIDANCE.md` (the target architecture) +
`deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` (the SDK capability).

---

## TL;DR of where we landed

We started building a TS-Next deterministic "frontend spine generator," then **pivoted**: the
SDK's durable strength is **polyglot microservices + a contract-first deterministic codegen
kernel**, and the TS-monolith frontend generator was deprioritized as narrow tech debt. The
front-end direction is now: **a thin UI service over a *generated* typed client, with a locked
component library** — the framework matters less than those two levers. Prior StartDate runs
(007–018) are **test runs**.

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

## Open decisions for the next session (recommendations in the guidance doc)
1. **Contract format at the UI edge:** OpenAPI (lean) vs gRPC-web. Drives the generated-client tool.
2. **UI framework:** Next.js App Router (lean) vs RedwoodJS vs AdonisJS+Inertia — *lower-stakes* once the client is generated.
3. **Component library:** pick + **install** one (kills the shadcn-invention class).
4. **Build StartDate as microservices** (docker-compose, online-boutique-shaped) vs keep local-first single-process — weigh against NFR-1.
5. **Where front-end fits the SDK roadmap:** the contract-codegen kernel (`ProtoStubProvider` + per-LanguageProfile build gate) is the SDK-side enabler; the UI is one consumer.

## Recommended next front-end steps (in order)
1. **Decide the UI-edge contract + client generator** (OpenAPI+`openapi-typescript`/`orval`, or gRPC-web+`connect-es`/`ts-proto`). This is the keystone — it removes the type/path-invention classes.
2. **Pick + install one component library**; record it as a project convention so imports always resolve.
3. **Promote the canonical `ValueModel` to a contract** (`value_model.proto` or OpenAPI component); make `value-model.ts` a *generated* artifact from it (the renderer generalizes to "contract→DTO in N languages").
4. **SDK side:** spec/build the `ProtoStubProvider` + per-LanguageProfile build gate (charter) — the first concrete payoff of the kernel; register it via the provider registry (the pattern is already in place).
5. **Pilot one vertical slice** (Profile: `valuemodel-svc` + `bff` + `frontend-svc`) end-to-end to validate the generated-client + build-gate + skip-hook on real services.

## Gotchas to remember
- The pipeline runs in `$SDK_ROOT/.venv` — verify its protobuf is `>=6.33.5` before a run (my fix was user-site).
- The whole-project tsc gate is **informational by default**; set `STARTD8_TS_GATE_STRICT=1` to enforce.
- Don't resurrect the TS-spine route-handler generator (superseded); generalize via the kernel instead.

*Companion handoffs: `CKG_NEXT_SESSION_HANDOFF.md` (separate CKG track).*
