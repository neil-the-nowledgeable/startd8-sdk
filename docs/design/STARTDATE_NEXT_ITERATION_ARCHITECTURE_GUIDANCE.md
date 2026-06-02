# StartDate (next iteration) — Target Architecture Guidance

> **⚠️ SUPERSEDED (2026-06-02) — see `IDEAL_TARGET_ARCHITECTURE.md`.** This doc assumed a
> **TS/React/Next** front end and pitched **polyglot-now**. Two clarifications retired that
> framing: (1) the SDK's strongest language is **Python** and its shape is microservices with
> **polyglot optional**; (2) "StartDate" was a prototype — the real app is greenfield, designed
> for max SDK support + **maximum deterministic assembly to minimize LLM cost**. The correct
> target is **all-Python, contract-first, server-rendered (FastAPI + Pydantic + HTMX)** — which
> raises the deterministic ceiling to ~60–75% and deletes the JS-front-end invention classes.
> Kept for the reasoning trail; **build to `IDEAL_TARGET_ARCHITECTURE.md`.**

**Date:** 2026-06-02 · **Audience:** the StartDate product/eng team (hand-off to update
`strtd8/docs/REQUIREMENTS.md` + `PLAN.md`) · **Status:** strategy guidance, pre-build
**Companion:** `deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md` (the SDK
capability this aligns to) · `deterministic-frontend/DETERMINISTIC_FRONTEND_SCOPE_ANALYSIS.md`

> **Premise.** Treat *all* prior StartDate runs (RUN-007…018) as **test runs**. There are no
> legacy users. The SDK's mature, durable strength is **polyglot microservices generation,
> contract-first** (the online-boutique target architecture) plus a new **deterministic
> contract→code kernel**. This doc describes how StartDate should be (re)architected so the
> SDK can support it **maximally deterministically** — i.e. the SDK generates the mechanical
> spine by construction, and the LLM is reserved (grounded + build-gated) for the genuinely
> semantic work. The single most important reframe: **your one canonical `ValueModel` schema
> becomes a *contract* the SDK projects into every service/language — not a hand-authored file.**

---

## 0. Why this changes the build (the lesson from the test runs)

RUN-015/016/017 failed on **invention**: invented module paths, invented exports
(`@/lib/prisma` vs `db`), invented UI components (shadcn), cross-file contracts that didn't
agree. Root cause: a Next.js monolith gives the LLM *too many degrees of freedom* and makes
the SDK hand-render artifacts the framework/ecosystem should generate. The fix is **structural**,
not "better prompts": choose an architecture where the **contracts are the source of truth and
codegen artifacts**, so the invention surface is designed out.

---

## 1. Architectural vision — contract-first polyglot microservices

Mirror the online-boutique shape (the SDK's strongest, best-tested target):

- **Contracts are the source of truth.** Define the domain + every service boundary as a
  **contract** (Protobuf/gRPC for service-to-service; OpenAPI or gRPC-web at the frontend
  edge). The SDK **deterministically generates** the typed stubs, DTOs, and clients for *every*
  language from those contracts. Nothing cross-service is hand-typed.
- **Services, each in its best language** (the SDK's 5 LanguageProfiles):

| Service | Responsibility (StartDate FRs) | Lang (suggested) | Mostly deterministic? |
|---------|--------------------------------|------------------|------------------------|
| `valuemodel-svc` | persist + CRUD the Value Model graph (Profile, ProofPoint, Capability, Outcome, Metric, Differentiator, ValueProp, Artifact) — FR-1/4/5/7/8(persist)/12 | Go or Node | ✅ contract + CRUD generated; persistence rules small |
| `enrichment-svc` (AI) | the AI passes: extract, suggest cap/outcome, quantify metric, synthesize differentiators/value-props, generate artifacts — FR-3/5/6/7/8/40 | **TS or Python** (`@anthropic-ai/sdk`) | ❌ semantic core (grounded+gated); its **tool-schemas are generated** from the contract |
| `completeness-svc` | derived completeness score + nudges — FR-9 | any | ✅ pure function from a declared signal set |
| `export-svc` | Markdown + JSON export — FR-10 | any | ✅ JSON pure; MD from a declared layout |
| `tailoring-svc` (P2) | JD ingest, per-job match, asset generation — FR-20…23 | TS/Python | ❌ semantic; contract + match-record CRUD generated |
| `pipeline-svc` (P3) | opportunities/stages/contacts — FR-30…34 | any | ✅ mostly CRUD over a contract |
| `bff`/`gateway` | aggregates services for the UI; owns the OpenAPI the frontend consumes | TS | ✅ contract + client generated |
| `frontend-svc` | the UI (wizard, value map, editing) — FR-2/8(render)/11 | TS | ◑ UX semantic; **all data types/clients generated** |

- **The AI layer stays TS/Python** so `@anthropic-ai/sdk` structured-output/tool-use stays
  first-class — and its **tool-use schemas are generated from the same contract** (so the
  AI's I/O contract can't drift).

---

## 2. The determinism contract (what the SDK owns vs what the LLM authors)

| The SDK generates **deterministically (owned, by-construction)** | The LLM authors (**semantic — grounded + build-gated**) |
|---|---|
| Per-language DTOs/structs + gRPC stubs from `.proto`; typed API client + OpenAPI types for the UI | Service **business logic** (the actual handlers' behavior) |
| The canonical `ValueModel` projected into every service (the value-model.ts renderer, generalized) | The **AI passes** (prompts, extraction/synthesis) — the product's intelligence |
| Build/config per service (`package.json`/`go.mod`/`csproj`/…), Dockerfiles, the inter-service wiring | **UI UX**: components, layout, the wizard/progressive-depth flow, copy |
| CRUD handlers over a contract entity; input/validation schemas; the completeness function; export serializers | Anything requiring product judgment |
| Owned-file markers + skip-hook recognition; drift/staleness `--check` | — |

**Verification by construction:** every owned artifact must pass its language's **build gate**
(the SDK's per-LanguageProfile build/`tsc`/compile check — the generalization of the now-live
whole-project tsc gate) + import/contract-resolution checks. A generated file that doesn't
compile is a build break, caught before the LLM ever runs on top of it.

---

## 3. UI / UX framework choice (+ rationale)

Under a contract-first microservices design, **the front end is one thin service over a
*generated* typed client** — so the framework choice is *lower-stakes* and the invention
surface is small. Recommendation, in priority of impact:

1. **Data layer = generated client, never hand-written.** Drive an **official contract→client
   generator** — `connect-es`/`ts-proto` (gRPC-web) or `openapi-typescript` + `openapi-fetch`/
   `orval` (OpenAPI). This is the "official generators" objective, realized at the contract
   layer. It eliminates the `@/lib/*` / wrong-export / type-invention classes outright (the
   types and client are generated, not invented).
2. **Lock the component system to ONE installed library.** Pick a single design system
   (e.g. shadcn/ui *installed*, or MUI/Mantine) and **install it** so `@/components/ui/*`
   imports always resolve. This kills the RUN-016/017 shadcn-invention class.
3. **Framework: Next.js (App Router) as the `frontend-svc`** — familiar, opinionated routing,
   server-components-leaning (smaller client module graph = less to invent). *Alternatives* if
   you want heavier scaffolding: **RedwoodJS** (generator-rich, Prisma-native — verify current
   ecosystem stability) or **AdonisJS + Inertia** (Rails-grade generators; Inertia removes the
   client API layer entirely). Any of these works *because the data layer is generated*; the
   framework is now a thin shell.
4. **Server-rendered-leaning UX** to minimize invented client modules; reserve client
   interactivity for where the wizard truly needs it (FR-2/11).

> Net: the decisive choices are **(1) generated clients** and **(2) a locked component set** —
> not the framework. Those two design-out ~all of the run-15/16/17 front-end invention.

---

## 4. Requirements updates (re-map the 52 FRs onto the new architecture)

Concrete edits for `strtd8/docs/REQUIREMENTS.md` + `PLAN.md`:

- **Promote "one canonical `ValueModel` schema" (today FR-3/architecture) to a first-class
  CONTRACT** (`value_model.proto` or an OpenAPI component). This is the keystone: your existing
  "single typed source" decision is *already* the right instinct — just move the source of
  truth from a hand-authored Zod file to a contract the SDK projects into every
  service/language (Zod/TS for the UI, structs for Go, etc.). **value-model.ts becomes a
  generated artifact, not a source file.**
- **Reframe FR-3/5/6/7/8/40 as `enrichment-svc`** with **generated tool-schemas**. Keep the
  "passes of one enrichment service" framing (you already have it) — but its structured-output
  targets are generated from the contract. Provenance fields (`source`/`confirmed`) live on the
  contract entities.
- **FR-1/4/5(persist)/12 → `valuemodel-svc`**: CRUD + persistence generated from the contract;
  only domain rules are hand-written.
- **FR-9 completeness → `completeness-svc`** with an **explicitly declared signal set** (you
  already define it) → a generated pure scoring function + a thin count query.
- **FR-10 export → `export-svc`**: JSON serializer generated; Markdown from a **declared
  per-entity layout** (add this layout to requirements).
- **FR-2/11 wizard/depth + FR-8(render) → `frontend-svc`**: explicitly mark the wizard/UX as
  **semantic/LLM**, and mandate **generated client + locked component library** as NFRs.
- **P2 (FR-20…23) → `tailoring-svc`; P3 (FR-30…34) → `pipeline-svc`** — same owned/semantic split.
- **New cross-cutting NFRs to add:**
  - **NFR-Contract-First:** all cross-service types come from a contract; nothing cross-service
    is hand-typed.
  - **NFR-Generated-Client-Only:** the frontend accesses services *only* through generated
    clients.
  - **NFR-Owned-File-Discipline:** generated files carry an ownership marker, are never
    hand-edited, and are regenerated on contract change (drift-checked).
  - **NFR-Build-Gated:** every service must pass its language build gate in CI before merge.
  - Keep existing NFR-1 (local-first), NFR-2 (privacy/per-pass payloads), NFR-6 (typed
    end-to-end) — all *strengthened* by contract-first.

---

## 5. Quality & verification model (what the SDK enforces for you)

- **Per-service build gate** (generalizes the live whole-project `tsc` gate to each
  LanguageProfile) — owned artifacts compile by construction; loud-degrades to "non-pass" if a
  toolchain is missing (never a silent pass).
- **Contract conformance + import-resolution** checks (the `cross_file_imports` family,
  generalized): no invented modules, no missing deps.
- **Owned-file skip-hook** (the new `DeterministicFileProvider` registry): the contractor skips
  the LLM ($0.00) for in-sync generated files — so regeneration is cheap and the LLM never
  re-invents the spine.
- **Drift `--check`**: detect a stale/hand-edited generated file before a run.

---

## 6. Anti-patterns to design out (the run-15/16/17 lessons, as rules)

1. **Never hand-write cross-service or API types** — generate from the contract.
2. **Never invent module paths** — canonical layout + generated imports; the build gate fails
   on `@/lib/ai/tailoring`-style invention.
3. **Never invent UI components** — one installed component library; "the project doesn't use
   shadcn" must be either false (install it) or enforced.
4. **One data layer per service** — no `prisma` vs `db` ambiguity; the generated client is the
   only access path.
5. **No partial/duplicate features** (the `ai/enrich-*` vs `enrich/*` mess) — the contract +
   service decomposition is the single structure.

---

## 7. Conventions to adopt for maximal deterministic support

- **A canonical repo layout** per service (the SDK encodes it as a framework profile).
- **A small codegen manifest** per service: which contract entities get CRUD, which endpoints
  are AI/action, the export layout, the completeness signal set. (This is what makes generation
  deterministic — the contract says *what types*, the manifest says *what surface*.)
- **Generated-file headers** (`// GENERATED from <contract> — do not edit`) + a content hash,
  so drift is detectable and the skip-hook recognizes ownership.
- **Monorepo** (recommended) with the contracts in one place, services consuming generated code.

---

## 8. Migration & sequencing (move fast)

1. **Author the contracts first** (`value_model.proto` + per-service service defs / the BFF
   OpenAPI). This is the highest-leverage artifact and the SDK's input.
2. **Generate the spine** across services (DTOs/stubs/clients/config) — owned, build-gated.
3. **Pilot one vertical slice end-to-end** (e.g. `valuemodel-svc` + `bff` + `frontend-svc`
   Profile flow) to validate the SDK's per-language gates + skip-hook on real services.
4. **Fill the semantic core** (AI passes, UX) grounded against the generated contracts, gated by
   the per-service build.
5. **Layer P2/P3** as additional services once MVP-1's slice is green.

---

## 9. Open decisions for the StartDate team (recommendations noted)

- **gRPC vs OpenAPI at the UI edge.** *Lean:* OpenAPI at the BFF→frontend boundary (simplest
  generated client for a web UI), gRPC/proto between services. Revisit if the UI needs streaming.
- **UI framework** (§3): *Lean:* Next.js App Router + generated client + one installed component
  library; Redwood/Adonis+Inertia as heavier-scaffold alternatives.
- **Language per service** (§1 table are suggestions): pick per the SDK's strongest profiles +
  your team's familiarity; the AI service should stay TS/Python.
- **Monorepo vs polyrepo** (*lean:* monorepo for shared contracts).
- **Local-first vs multi-service locally.** MVP-1 was local-first single-process; microservices
  add orchestration (docker-compose) — weigh against NFR-1. *Lean:* docker-compose locally,
  online-boutique-style, which the SDK already targets.

---

## 10. The one-paragraph summary for the StartDate team

Re-architect StartDate as **contract-first polyglot microservices** (online-boutique-shaped).
Make your already-canonical **ValueModel a contract** the SDK projects into every
service/language; let the SDK deterministically generate the mechanical spine (DTOs, stubs,
clients, CRUD, config, completeness, export) **build-gated by construction**; and reserve the
LLM — grounded against the generated contracts — for the **enrichment AI passes and the UI/UX**,
which is where StartDate's actual value lives. For the front end specifically: **generated
client + one installed component library** matter far more than the framework, and together
they design-out the invention failures from the test runs. This shape is exactly what the SDK
is most mature at and what the contract-codegen kernel is being built to support.

*Hand-off: fold §4 into `strtd8/docs/REQUIREMENTS.md` (new NFRs + the contract/service re-map)
and §1/§8 into `strtd8/docs/PLAN.md` (service decomposition + contract-first build order).*
