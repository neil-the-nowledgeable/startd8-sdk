# Deterministic Frontend Generation — Scope Analysis (strtd8)

> **Note (2026-06-02):** The TS-Next "spine" *implementation* this analysis sized is deprioritized
> (see the superseded `DETERMINISTIC_FRONTEND_SPINE_*` docs), but the **determinism-boundary
> analysis** here — what is mechanically generatable vs irreducibly semantic — and the underlying
> **pattern** remain valid and feed `DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`.

**Date:** 2026-06-02
**Purpose:** Determine, against a **real** target app's full requirements, how much of a
Next.js / Prisma / Zod frontend is *realistically* deterministically generatable (pure Python,
no LLM) — and compare that to how much `frontend_codegen` generates **today** — so the next
deterministic-generation requirements target the highest-leverage gaps.
**Evidence base:** strtd8's `docs/REQUIREMENTS.md` (52 FRs), `docs/PLAN.md` (13-task
decomposition + architecture), and a census of the live strtd8 source tree (74 `.ts/.tsx`
files + schema + config). Companion to `DETERMINISTIC_FRONTEND_GENERATION_INVENTORY.md`
(which established the Prisma→Zod renderer as the first primitive).

---

## 1. The target app at a glance

strtd8 is a local-first **"value model" / job-search** app (Next.js App Router, Prisma+SQLite,
Zod shared types, Anthropic AI service). Scope:

- **Domain model:** 12 Prisma models (Profile, ProofPoint, Capability, Outcome, Metric,
  Differentiator, ValueProp, Artifact, AiCall + 3 join tables), plus P2's JobDescription /
  TailoredMatch / TailoredAsset.
- **52 FRs:** MVP-1 (FR-1…12, value articulation), P2 (FR-20…23, campaign/assets), P3
  (FR-30…34, pipeline), cross-cutting FR-40 (AI service).
- **13 build tasks** (PLAN §7): scaffold, schema, profile, proofpoints, ai-service, extract,
  artifacts, enrich-cap/metric/diff, valueprop, depth, completeness, export.

**Live file census (excl. `node_modules`/`.next`/pipeline-output):**

| Bucket | Count |
|--------|------:|
| Prisma schema | 1 |
| API route handlers (`app/**/route.ts`) | 24 |
| Pages (`page.tsx`) | 14 |
| Layouts | 1 |
| Components (`.tsx`) | 10 |
| AI passes (`lib/ai/*.ts`) | 9 |
| Other `lib/*.ts` (incl. `value-model.ts`, `db.ts`) | 8 |
| Config (`package.json`, `tsconfig.json`, `next.config`) | 3 |
| **Total source artifacts** | **~74** |

---

## 2. The determinism boundary (per artifact class)

| Artifact class | Files | Deterministic? | Basis | Generated today? |
|----------------|------:|----------------|-------|------------------|
| Prisma→Zod schema + `z.infer` types (`value-model.ts`) | 1 | ✅ **Full** | pure projection of the schema | ✅ **yes** (Inc 1–5, committed) |
| Config (`package.json`/`tsconfig`/`next.config`) | 3 | ✅ **Full** | `languages/nodejs.generate_*`; pipeline already treats as deterministic build files | ✅ yes (pipeline) |
| `db.ts` (Prisma client singleton) + migrations | ~2 | ✅ **Full** | boilerplate singleton; `prisma migrate` deterministic from schema | ❌ no |
| **API route handlers** | **24** | ◑ **High (~70%)** | CRUD = Zod-validate body → Prisma op → `NextResponse`, templatable from schema; AI-trigger routes are thin validate-and-dispatch wrappers | ❌ no |
| Completeness score (FR-9) | ~1 | ✅ **Full** | FR-9 defines an explicit signal set → a pure function | ❌ no |
| Export (Markdown + JSON, FR-10) | ~1–2 | ✅ **High** | FR-10: structured data → MD/JSON renderer | ❌ no |
| AI **tool-use Zod schemas** (FR-3/40 structured-output targets) | within `lib/ai` | ✅ **Full** | same domain-model projection as `value-model.ts` | ❌ no |
| Pages (`page.tsx`) | 14 | ◑ **Shell (~30%)** | import-shell + component skeleton mechanical; layout/UX/copy semantic | ❌ no |
| Components (`.tsx`) | 10 | ◑ **Shell (~30%)** | form field-sets derive from schema; interaction semantic | ❌ no |
| AI passes (`lib/ai/*`: extract, enrich×3, valueprop, artifacts) | 9 | ❌ **Semantic** | prompts + extraction/synthesis = the product's intelligence | ❌ no |
| Wizard / progressive-depth UX (FR-2, FR-11, §6) | pages | ❌ **Semantic** | "the single hardest UX requirement" | ❌ no |

**Deterministic spine** = schema/types, config, `db`/migrations, the 24 route handlers,
completeness, export, AI tool-schemas, and the directory/import skeleton.
**Irreducible semantic core** = the 9 AI passes, page/component UX, the wizard.

---

## 3. Realistic vs current coverage

**Realistic (file-count-weighted, rough but defensible): ~35–45%** of the codebase is
deterministically generatable or scaffoldable.
- Fully deterministic (~9 files): `value-model.ts`, config (3), `db.ts`+migrations,
  completeness, export, tool-schemas.
- High (~70%): the **24 route handlers** — the single largest mechanical bucket.
- Shell-only (~30%): 14 pages + 10 components + layout.
- Semantic (~15%, only the tool schemas): the 9 AI passes.

**Current: ~5%** — effectively just `value-model.ts` (1 file) + the config build-files the
pipeline already emits. Of the `frontend_codegen` capability specifically: **one file**.

**The gap ≈ realistic − current = ~30–40 points**, concentrated in a handful of generators.

> **Honest framing.** The 45% is *files/plumbing*, not *value*. The deterministic spine is
> correctness-critical but mechanical; the semantic ~55% (AI passes + UX) is *why the app
> exists*. The goal is to (a) eliminate the invention/compile errors in the mechanical 45%
> **by construction**, and (b) free the LLM's budget for the hard 55% — not "build the app
> for free."

---

## 4. The capability gap, prioritized by leverage

1. **Route-handler generator (24 files — the single biggest win).** Schema-driven
   CRUD (`GET/POST/PATCH/DELETE`) + thin AI-trigger wrappers, Zod-validated, canonical imports.
   This is *exactly* where RUN-017's invention errors lived (`route.ts` importing
   `@/lib/ai/tailoring`, `@/lib/prisma`) — a generator kills that class by construction.
2. **Completeness function (FR-9).** The signal set is literally a spec for a pure function;
   trivially deterministic, currently LLM-guessed.
3. **Export renderer (FR-10).** Structured-data → Markdown/JSON; a template renderer.
4. **`db.ts` + migrations.** Boilerplate singleton + `prisma migrate`; removes the
   `prisma`-vs-`db` invented-export class.
5. **AI tool-use Zod schemas.** Same projection as `value-model.ts` — near-free to fold in.
6. **Route/page import-*shells* (seeded, not owned).** Canonical imports + handler/component
   signatures for the LLM to fill — kills the path-invention class without generating bodies.
7. **Config + directory/import skeleton.** Largely covered; formalize under one capability.
8. **Prisma schema (spec-derived).** Generatable from a domain-model spec; lower priority
   (today the schema is the hand-authored source of truth for everything else).

**RUN-017 connection:** all 28 of run-17's tsc errors were in the **route / page / `lib/ai`**
surface — precisely classes 1, 6, and the semantic core. Generators for 1 and 6 would have
prevented the bulk of run-17's invention errors at generation time (the tsc gate currently
catches them after the fact).

---

## 5. What this feeds

This analysis grounds a requirements doc covering **all realistically-deterministic frontend
capabilities** (the spine in §2/§4), an implementation plan, and a reflective-requirements
pass. Sequencing principle for the requirements: **highest-leverage, schema-derived, owned
artifacts first** (route handlers, completeness, export), reusing the existing
`frontend_codegen` primitives (`parse_prisma_schema`, the `FieldSpec`/`FieldSetAuthority`
projection, `render_zod_schema`, convention detection, the gates, the drift/skip-hook) — the
renderer pattern generalized from one artifact (the schema file) to the deterministic spine.

*Companion to `DETERMINISTIC_FRONTEND_GENERATION_{INVENTORY,REQUIREMENTS,PLAN}.md`.*
