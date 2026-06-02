# RUN-015 (P2-Batch-1, all-Gemini, fresh plan) Postmortem — Four NEW invention flavors on unseen content

**Date:** 2026-06-02
**Run:** `pipeline-output/startd8/run-015-20260602T0924/`
**Score:** 0.20 (1/5 features marked PASS — also the only feature genuinely working)
**Verdict:** FAIL
**Total cost:** $0.17
**Models:** `lead = gemini:gemini-2.5-pro`, `drafter = gemini:gemini-2.5-flash-lite`
**Predecessors:** [RUN_014_M6_ALL_GEMINI_REGRESSION_POSTMORTEM.md](./RUN_014_M6_ALL_GEMINI_REGRESSION_POSTMORTEM.md) — same model stack, **different plan** (M6 re-run vs fresh P2-Batch-1)
**Companion architectural doc:** [CROSS_FILE_CONTRACT_RESOLUTION.md](./CROSS_FILE_CONTRACT_RESOLUTION.md) §12

---

## 1. What happened

First **fresh-plan** test of the all-Gemini stack (RUN-014 was a re-run of the M6 plan — same prompt, different model; this is RUN-014's model stack on previously unseen content). P2-Batch-1's plan: 7 features for FR-20 JD ingest (JD lib + AI extract + 4 CRUD routes + 2 UI pages).

**Result: 0/7 deliverable.** Score 0.20 reflects 1 of 5 features marked PASS — but only 5 of 7 features were even attempted because plan-ingestion → prime-contractor lost PI-006 and PI-007. The lone PASS (PI-001 `lib/jd.ts`) is genuinely working.

This is the **same model stack as RUN-014 ($0.86 / 0 of 5 deliverable on M6)**. RUN-015 added: a fresh plan + 5× lower cost + **four entirely new invention flavor classes** the prior catalog (Gap A-T) didn't anticipate.

## 2. Failure attribution (reconciled)

| Feature | Verdict | tsc against project | Real status | Cost |
|---|---|---|---|---|
| PI-001 `lib/jd.ts` | PASS | clean | **DELIVERABLE** | $0.022 |
| PI-002 `lib/ai/extract-jd.ts` | FAIL `cross_file_contract` | 4 invented imports | BROKEN | $0.042 |
| PI-003 `app/api/ai/extract-jd/route.ts` | FAIL `cross_file_contract` | 2 tilde-aliases + Zod misuse | BROKEN | $0.027 |
| PI-004 `app/api/job-descriptions/route.ts` | FAIL `cross_file_contract` | nearly correct; verdict attribution noise | BROKEN-but-fixable in minor edits | $0.027 |
| PI-005 `app/api/job-descriptions/[id]/route.ts` | FAIL TS2538 | invented `jobDescriptionsStore` Map | UNUSABLE — wrong storage layer | $0.054 |
| PI-006 `app/job-descriptions/page.tsx` | **NOT EMITTED** | n/a | seed had it; prime-contractor stopped at 5 features | — |
| PI-007 `app/job-descriptions/[id]/page.tsx` | **NOT EMITTED** | n/a | same | — |

**Real verdict: 1/7 deliverable.** Plan-ingestion-to-prime-contractor lost 2/7 features before generation even started — a NEW failure mode at the pipeline-orchestration layer, not the LLM layer.

## 3. NEW failure flavors (Gap U through Gap X)

These flavors are entirely new to the run-007-015 catalog. The all-Gemini stack on fresh content produced four classes of invention that the Anthropic-stack baseline never surfaced:

### Gap U — Tilde-prefixed alias path

```
import { extractJobDescription } from "~/lib/ai/extract-jd";
import { logger } from "~/lib/logger";
```

Vercel / Nuxt / Astro convention. This project uses `@/lib/...` per `tsconfig.json` `paths`. The tilde alias never resolves.

### Gap V — Wrong Zod import idiom

```
import zod from "zod";
const schema = zod.z.object(...);
```

Canonical idiom: `import { z } from "zod"; z.object(...)`. The `zod.z.X` namespace doesn't exist on the default export. Surfaced as the classifier signature `external_type_unresolved:zod.z`.

### Gap W — Vercel AI SDK invention

```
import { generateObject } from "ai";
```

The `ai` npm package (Vercel AI SDK) is widely used in Next.js templates but is **not in this project's `package.json`**. The project uses `callAiService` from `@/lib/ai/service`. **The CKG gate correctly attributed this** as `missing_dependency:ai`. ✅ A new attributable failure mode working.

### Gap X — Symbol-as-index-type (TS2538)

PI-005's draft constructed an in-memory `Map`-like store (`jobDescriptionsStore`) with Symbol-typed access patterns. TS2538 surfaces when `obj[someSymbol]` hits a typed Record whose index signature doesn't allow Symbol keys. Heuristic detector added to the triage script as `\[Symbol\(`.

## 4. Gap V (continued): plan-ingestion drop of UI features

PI-006 and PI-007 are documented in the active plan (`typescript-plan.md` §F-506 / §F-507). The seed file (`prime-context-seed.json`) confirms 7 tasks were emitted. But the prime-contractor postmortem reports `total_features: 5` — only 5 were attempted. Hypothesis: `stop_on_failure` semantics killed the queue after PI-002 failed early in the chain.

This is a **NEW pipeline-orchestration failure mode** distinct from generation quality. Worth tracking as Gap Z or carrying as a follow-up question for the SDK team: should `--task-filter` semantics or per-feature failure isolation prevent this cascade?

## 5. What's NEW vs RUN-014 (same model stack, different plan)

| Pattern | RUN-014 (M6 re-run) | RUN-015 (P2-Batch-1 fresh plan) |
|---|---|---|
| Total cost | $0.17 | $0.17 (identical) |
| Real delivery | 0/5 | 1/7 |
| Score-vs-reality recoupling | Caught 2 of 5 verdict failures correctly | Caught 4 of 5 attempted; missed PI-001 (correctly PASS) |
| Sub-namespace invention | `@/lib/db/schema` (Drizzle), `@/lib/types` | `@/lib/ai/client`, `@/lib/data/job-descriptions`, `@/lib/utils/text-utils` (3 new invented sub-namespaces) |
| External-dep invention | `pino` (1) | `ai` (Vercel AI SDK), 1 |
| Tilde alias | NOT observed | **NEW Gap U** — `~/lib/...` (2 instances) |
| Wrong-idiom Zod | NOT observed | **NEW Gap V** — `import zod` / `zod.z.object` |
| Symbol-as-index TS2538 | NOT observed | **NEW Gap X** — invented Map-based store with Symbol keys |
| Storage-layer invention | NOT observed | **NEW** — PI-005 used in-memory Map instead of Prisma |
| Plan-ingestion drops features | NOT observed | **NEW** — PI-006/PI-007 never reached prime-contractor |

**Net:** Gemini on a fresh plan with no prior context produced 5 entirely new invention domains the prior plans (M4-M6) never had to enumerate. Each is plausible from training prior (Vercel/Nuxt, Drizzle, Map-based stub stores).

## 6. Implications

1. **Discipline blocks are domain-by-domain whack-a-mole, and the rate of NEW domains scales with plan novelty.** RUN-013 added 1 new flavor (sub-namespace). RUN-014 added 5 (external-dep, Drizzle, types-dir, TS7006, as-any). RUN-015 added 4 more (U-X). Per-plan discipline-block authoring is unsustainable.

2. **Approach A (programmatic project-knowledge artifact) becomes increasingly load-bearing** as the LLM is asked to operate further from its training prior's natural defaults. RUN-015's evidence is the strongest yet for Approach A — every flavor here would be eliminated by enumerating actual installed deps + actual tsconfig paths + actual storage layer at design-context-build time.

3. **The cost/delivery tradeoff hasn't moved.** Same $0.17 as RUN-014, identical 0% (or near-0%) delivery rate. Gemini is cheap, but cheap × broken == broken. Anthropic-stack at $0.86 also delivers 0%, just at different flavors. **Until Approach A lands, model stack choice is mostly a "which flavors do you want to debug" question, not a delivery-rate question.**

4. **Plan-ingestion silently dropping features** (Gap Z, new) is a load-bearing question for the next session. If `stop_on_failure` is the cause, it suggests Gemini's cascade-failure pattern (one broken feature → all downstream features lost) is worse than Anthropic's (Anthropic stack delivered partial sets across M4-M6 even when several features failed).

## 7. Recommended fixes

### Tier 1 — direct-fix (5 files, ~45 min)

Done in commit `3e96a52`. All 4 broken files rewritten + PI-001 preserved.

### Tier 2 — plan-level

The four NEW flavors (U-X) need explicit enumeration in any future Gemini-stack plan:

- **Block C extension:** tilde-aliases (`~/lib/...`) banned alongside sub-namespaces
- **Block A extension:** "Zod is imported as `import { z } from \"zod\"`. NEVER `import zod from \"zod\"` or `zod.z.X`."
- **Block dependency-set:** "The project's installed dependencies are listed in `package.json`. Inventing imports from packages not in that list is banned. Common training-prior dependencies that are NOT in this project: `pino`, `ai` (Vercel), `swr`, `@radix-ui/*`, `lucide-react`."
- **Block storage layer:** "Persistence goes through Prisma via `db` from `@/lib/db`. NEVER invent in-memory Map-based stores like `jobDescriptionsStore`."

### Tier 3 — SDK level

- **Fix 11 (NEW):** plan-ingestion → prime-contractor feature count parity check. If the seed has N tasks but prime-contractor reports M < N attempted, surface this as a pipeline-attribution finding instead of silently degrading.
- **Fix 12 (NEW):** post-merge `tsc --noEmit` against the assembled project (this is Fix 10 from RUN-013 §6.1, renumbered). RUN-015 evidence reinforces: Gap U/V/W are all unresolvable-import patterns that project-wide tsc catches but the verdict layer's per-feature gate misses.
- **Fix 13 (NEW):** `external_dep_not_in_package_json` classifier signature was confirmed working on `pino` (RUN-014) and `ai` (RUN-015). Should be promoted from "working" to "standard" — currently it correctly attributes one but the other 3 invented paths in PI-002 (`@/lib/ai/client`, etc.) bypassed the per-feature gate.

## 8. Recommended next steps

1. ✅ **Tier 1 direct-fixes** — done in commit `3e96a52`.
2. **Retry PI-006/PI-007 with `--task-filter`** — done in run-016 (see separate postmortem).
3. **Update [CROSS_FILE_CONTRACT_RESOLUTION.md §12](./CROSS_FILE_CONTRACT_RESOLUTION.md)** with the four new flavor classes — strengthens the §12.5 case that the signature family is incomplete without programmatic enumeration.
4. **Investigate Gap Z (plan-ingestion drops)** with the SDK team — separate from generation-quality concerns.
