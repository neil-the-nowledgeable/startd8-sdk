# RUN_009 In-Flight Findings — Cross-Feature Inheritance and the `--fresh` Anchor Wipe

**Date:** 2026-06-01
**Status:** **IN FLIGHT** — prime-contractor (PID 97630) is still running attempt-2 against run-009's seed via `./run-prime-contractor.sh --provenance pipeline-output/startd8/latest/run-provenance.json --fresh`. Postmortem not yet written.
**Predecessor reports:** `RUN_003_FORWARD_MANIFEST_GAP_POSTMORTEM.md`, `RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`, `RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`.
**This doc:** captures observations available before the run finishes. Companion final postmortem (`RUN_009_POSTMORTEM.md`) will be written after the postmortem-level artifacts (verdict, classifier signatures, Kaizen suggestions) land.

---

## 1. Context

Run-009 was the first pipeline invocation after the user implemented the **Fix 1 (intra-batch inter-feature context inheritance)** and **Fix 2 (cross-file integrity classifier signatures)** remediations specced in the RUN_008 postmortem. The active plan was `typescript-plan.md` v(2026-05-31) (scope: M2 consumer regeneration + M3 AI engine; 6 features expected — see `.cap-dev-pipe/typescript/typescript-plan.md`).

Attempt-1 (started 2026-06-01 00:45) halted at PI-001 (F-101 Value Model Zod schemas) with a pre-merge TypeScript check failure: `Cannot find module 'zod'` against a temp-file copy at `/var/folders/.../tmp4r0z9dfv.ts`. The temp dir had no `node_modules`; the project's `node_modules/zod` was present and the on-disk `lib/value-model.ts` would have compiled correctly. Verdict reported as FAIL 0.00 with stage `unknown / unknown(1)` — same blind-classifier signature as RUN_003 / RUN_007. **Attempt-1 snapshot saved to `/tmp/run-009-attempt-1-20260601T1005/`** for comparison.

Attempt-2 (started ~2026-06-01 09:50, still running at writing) is a re-invocation of `run-prime-contractor.sh` against the same run-009 seed with `--fresh`, which triggers `clean-prior-run.sh` to remove all files in the seed's `forward_manifest.file_specs` before generation begins. The user implemented changes between attempts — direction unknown to this writer; the observations below are inferred from the on-disk state.

---

## 2. On-disk progress at writing time

5 of the 6 Phase-1 deliverables are on disk with progressive mtimes; **none of the Phase-2 (M3) files exist yet**:

| Mtime | File | Feature | Phase |
|-------|------|---------|-------|
| 09:50:51 | `lib/value-model.ts` | F-101 (Zod schemas) | 1 |
| 09:53:13 | `app/api/profile/route.ts` | F-102 (Profile API) | 1 |
| 09:56:19 | `app/profile/page.tsx` | F-102 (Profile UI) | 1 |
| 09:59:59 | `app/api/proof-points/route.ts` | F-103 (ProofPoint list/create API) | 1 |
| 10:02:28 | `app/api/proof-points/[id]/route.ts` | F-103 (ProofPoint item API) | 1 |
| 10:05:18 | `app/proof-points/page.tsx` | F-103 (ProofPoint UI) | 1 |
| — | `lib/ai/service.ts` | F-104 | 2 (pending) |
| — | `lib/ai/extract.ts` + 2 surfaces | F-105 | 2 (pending) |
| — | `lib/ai/artifacts.ts` + 2 surfaces | F-106 | 2 (pending) |

Phase 1 (M2 consumer regen) appears complete; Phase 2 (M3 AI engine) is the in-flight work. Cumulative feature-completion progress vastly exceeds attempt-1 (which produced 1 file).

---

## 3. RUN_009 attempt-1 issues — current status per item

| # | Attempt-1 issue | Status now | Evidence |
|---|---|---|---|
| 1 | Halt at PI-001 / `Cannot find module 'zod'` (pre-merge TS check tooling artifact) | **RESOLVED** | 5 files past PI-001 on disk; Phase 1 visibly complete |
| 2 | Postmortem stage `unknown / unknown` (Fix 2 classifier not visible) | **NOT YET TESTABLE** | Postmortem not written; still attempt-1's mtime 00:54 |
| 3 | Kaizen suggestions empty `[]` | **NOT YET TESTABLE** | Same — written only at run completion |
| 4 | Verdict FAIL 0.00 / 1 feature processed | **TRENDING BETTER** | 6× more files on disk; final verdict TBD |
| 5 | Generated `lib/value-model.ts` diverges from Prisma | **PARTIALLY UNRESOLVED** | See §4 — name-level coherence yes, field-level no, and Prisma was wiped |

---

## 4. Fix 1 (intra-batch inter-feature inheritance) — partial signal

**✅ Module-name coherence — WORKING at the producer/consumer name level.** Every consumer feature in Phase 1 that imports the Zod schemas uses the same path as the producer emitted:

```typescript
// F-102 app/api/profile/route.ts:2
import { ProfileSchema } from "@/lib/value-model";

// F-103 app/api/proof-points/route.ts:2
import { ProofPointSchema } from "@/lib/value-model";
```

This is the canonical RUN_008 Gap A failure mode (three invented module names for the same target) **closed for this run's intra-batch producer/consumer chain.** F-101 emitted `lib/value-model.ts`; F-102 and F-103 both correctly inherited that exact path. **This is real Fix 1 evidence.**

**🔶 Module-name coherence — NOT working for the pre-existing upstream `@/lib/db`.** F-102 correctly imports `from "@/lib/db"` (the M1 ship-set Prisma client singleton). F-103 invents a different name:

```typescript
// F-103 app/api/proof-points/route.ts:1
import prisma from "@/lib/prisma";   // ← invented path; file does not exist
```

The same Gap-A pattern (cross-feature naming disagreement) survives **for files that aren't produced by an earlier feature in this batch**. F-102 happened to use the correct path; F-103 reverted to inventing one. The pattern is consistent with a Fix 1 implementation that propagates names from **same-batch upstream features** but not from **pre-existing project files** — see §6 hypothesis.

**❌ Field-level coherence — NOT working.** The regenerated `ProfileSchema` is identical in shape to attempt-1 (and to the broken run-008 Zod):

```typescript
export const ProfileSchema = z.object({
  id, name, title, bio, createdAt, updatedAt
});
```

`bio` is **invented** (not in `prisma/schema.prisma`, not in `docs/REQUIREMENTS.md`, not in `docs/PLAN.md` §2). All the other Profile fields the canonical Prisma model carries (`ownerId`, `source`, `confirmed`, `company`, `industry`, `summary`, `linkedinUrl`, `email`, `phone`, `location`, `yearsExp`, `notes`) are absent. Same divergence as RUN_008 Gap B.

---

## 5. Critical: `--fresh` wiped the declared immutable upstream anchor

`prisma/schema.prisma` is **missing from the project root** at writing time:

```
sed: /Users/neilyashinsky/Documents/dev/strtd8/strtd8/prisma/schema.prisma: No such file or directory
```

The `typescript-plan.md` declared `prisma/schema.prisma` as the **immutable upstream anchor** for inheritance and **explicitly out of scope** for regeneration in this batch. But the `--fresh` flag invokes `clean-prior-run.sh`, which removes every file in the seed's `forward_manifest.file_specs` — and the seed for this batch evidently still listed `prisma/schema.prisma` as a target (carried over from prior M1-M2 plan, or re-derived by enrichment from text references).

**The plan's "out of scope" declaration was not honored by the seed enrichment or by `clean-prior-run.sh`.** The supposed-immutable upstream was wiped before the first feature generated. Fix 1 (whatever inheritance scope it implements) had no on-disk Prisma to inherit from when F-101 generated `lib/value-model.ts`.

> **⚠ VERIFIED CORRECTION (2026-06-01, post-review).** The specific causal claim above — "the seed for this batch evidently still listed `prisma/schema.prisma` as a target" — is **FALSIFIED by the evidence**. run-009's seed `forward_manifest.file_specs` has **13 entries (the M2/M3 targets only); `prisma/schema.prisma`, `package.json`, and `lib/db.ts` are NOT in it.** So run-009's `--fresh` did **not** wipe them via the file_specs loop. The real cause: **(a)** these M1 anchors were **never git-tracked** (`git ls-files` → none; `prisma/` is `??`), so once removed they are unrecoverable; and **(b)** *earlier* run seeds DID list them — `run-003`/`run-004` seeds carry **15** file_specs entries including `prisma/schema.prisma`+`package.json`+`lib/db.ts` — so an earlier `--fresh` wiped them and they were never restored. The **deeper, confirmed gap** is at the schema level: a `ForwardFileSpec` has **no field distinguishing a regeneration target from a pre-existing upstream anchor** (both have identical keys `file/language/elements/imports/dependencies/convention_provenance`), and tasks carry **no `target_files`** — so `clean-prior-run.sh` (which `rm`s every `file_specs` key) **cannot** tell anchors from targets. The gap the doc identified is real; the run-009 attribution was wrong. See §11.

This is its own gap, independent of Fix 1's implementation: **the pipeline does not respect plan-level "out of scope" / "pre-existing upstream" semantics; it treats every target file as wipeable.** Either:

- The plan-ingestion / seed-emitter needs to honor explicit "do-not-regenerate" markers, OR
- `clean-prior-run.sh` needs to read the same markers and skip them during cleanup, OR
- The plan author must omit any reference to the upstream file from the plan body to prevent enrichment from re-adding it to file_specs.

The third option is fragile (a referenced filename anywhere in the plan can pull it into `file_specs`); the first two are structural.

---

## 6. Hypothesis: Fix 1 propagates same-batch sibling output, not external upstream

The evidence pattern is consistent with Fix 1 implementing **only one** of the two inheritance modes the plan implicitly required:

| Mode | What it inherits from | Run-009 evidence |
|------|----------------------|------------------|
| **A — Intra-batch inter-feature** | Files produced by an earlier feature in the same batch | ✅ Working: F-102 / F-103 inherit `@/lib/value-model` from F-101's emitted file |
| **B — Pre-existing external upstream** | Files already on disk before the batch started (e.g. M1 ship-set, project conventions) | ❌ Not working: F-103 invents `@/lib/prisma` instead of inheriting the existing `@/lib/db` path; F-101 generates Zod without consulting `prisma/schema.prisma` (compounded by §5 — Prisma was wiped anyway) |

The plan I authored conflated these two modes — it declared `prisma/schema.prisma` as upstream without distinguishing "already on disk, never to be regenerated" from "produced by an earlier in-batch feature." The user's Fix 1 implementation appears to handle Mode A but not Mode B. This is a real distinction that should be documented as a Fix 1 scope limitation (or a future Fix 1b).

**Caveat:** because the Prisma schema was wiped at start of attempt-2 (§5), Mode B can't be cleanly tested in this run. The Zod-field-divergence evidence here is consistent with **both** "Mode B not implemented" and "Mode B implemented but had no upstream to read." A clean Mode-B test requires Prisma on disk at the start.

---

## 7. New issues surfaced (not in attempt-1)

- **`app/api/proof-points/route.ts:1`** — invented path `@/lib/prisma` (file doesn't exist). Same Gap-A pattern as run-008, at a different file.
- **`app/api/profile/route.ts:3`** — `import pino from "pino"`; pino isn't a dependency in the M1 ship-set `package.json`. If `npm install` was re-run after attempt-1 wiped `package.json` (was the M1 package.json also wiped by --fresh? — would need to check), pino would be unresolvable. If not, the runtime would fail to require pino. **Either way: a dependency declared by a generated file that the project doesn't actually have.**
- **`prisma/schema.prisma` is missing** — already covered in §5.

These mirror the run-008 pattern (cross-feature invention of names and dependencies). They demonstrate Fix 1's scope gap (Mode B not covered) is real and visible without waiting for the postmortem.

---

## 8. What we can't tell yet (postmortem-level signals)

These items require the run to complete:

| Signal | Source | What it tells us |
|--------|--------|-----------------|
| Final verdict (PASS / FAIL / PARTIAL) | `prime-postmortem-summary.md` | Whether attempt-2's reported result matches reality |
| Stage / root cause attribution | `prime-postmortem-report.json` `pipeline_attribution` | Whether Fix 2 classifier signatures fired (real attribution) or are still `unknown / unknown` |
| Kaizen suggestions populated | `kaizen-suggestions.json` | Whether the learning loop fires on this run's failure modes |
| Per-feature success / fail count | `prime-result.json` `succeeded` / `failed` | Whether the success count agrees with on-disk reality (RUN_007 / RUN_008 lesson: it usually doesn't) |
| Phase-2 M3 file completion | filesystem | Whether `lib/ai/service.ts`, `lib/ai/extract.ts`, `lib/ai/artifacts.ts` and their UI/API surfaces land at all |
| `npm install && npm run build` | manual post-run | Whether what was generated actually compiles/installs |

The most important diagnostic when the postmortem lands: **compare `pipeline_attribution.stage` against `unknown`**. A populated attribution (e.g. `drafter / unresolvable_import` or `cross-file / prisma-zod-symmetry`) means Fix 2 wired correctly. An `unknown / unknown` means Fix 2 is either not wired or its signatures don't catch this run's failure shape.

---

## 9. Sequencing implications for next runs

1. **Fix the `--fresh` semantics before run-010.** The seed for the next full pipeline run (`./startd8-cap-dlv-pipe.sh`) must NOT include any file in its `forward_manifest.file_specs` that the plan declares immutable. Either harden `clean-prior-run.sh` to honor an explicit `do-not-wipe` list, or audit the seed-emitter to omit non-target files from `file_specs`, or restructure the plan body so no upstream-file path is mentioned outside an explicit "out-of-scope" block.
2. **Restore `prisma/schema.prisma` from git before any verification of attempt-2's outputs.** `git checkout prisma/schema.prisma` (assuming it was committed) or restore from `run-008` generated/ as a fallback. Without it on disk, the Zod-against-Prisma symmetry check can't run, and any Prisma-client call in the regenerated routes would fail at runtime once Prisma client is re-generated.
3. **Extend Fix 1 (or add Fix 1b) to cover Mode B — pre-existing external upstream files.** The same inheritance mechanism that propagates F-101's `lib/value-model.ts` path to F-102/F-103 should propagate `lib/db.ts`'s existing path and `prisma/schema.prisma`'s existing field set to F-101. Without this, every batch that builds on a prior ship set will re-invent names and types that already exist.
4. **Add a Fix 2 classifier signature specifically for `package.json` dependency divergence** — generated code imports `pino`, but `package.json` doesn't list it. This is a class of failure the existing Fix 2 signatures (unresolvable-import, Prisma↔Zod symmetry, Prisma usage constraint) don't appear to cover.

---

## 10. What to do when the run finishes

When PID 97630 exits and the postmortem-summary.md mtime advances past 00:54:

1. `diff /tmp/run-009-attempt-1-20260601T1005/prime-postmortem-summary.md run-009-20260601T0045/plan-ingestion/prime-postmortem-summary.md` — does the verdict change shape? Does the attribution stage become non-`unknown`?
2. Audit `lib/value-model.ts` against `prisma/schema.prisma` (restored from git) — does the regenerated Zod match the field set? If yes, Mode B is somehow working (and §5/§6 were wrong). If no, Mode B is the next gap to close.
3. Check whether `lib/ai/service.ts`, `lib/ai/extract.ts`, `lib/ai/artifacts.ts` and their API/UI surfaces land at all — Phase 2 (M3) completion is the major delivery question.
4. `cd /Users/neilyashinsky/Documents/dev/strtd8/strtd8 && npm install && npm run build` — would the regenerated app actually compile end-to-end? The pino dependency divergence in §7 is one of several potential blockers.
5. Fold this in-flight document into a full `RUN_009_POSTMORTEM.md` (same shape as RUN_007 / RUN_008) capturing gaps, fixes, and recommendations.

---

*Authored 2026-06-01 from in-flight observations of prime-contractor attempt-2 against run-009's seed. Snapshot of attempt-1's postmortem artifacts at `/tmp/run-009-attempt-1-20260601T1005/`. Files cited: project-root generated outputs in `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/{lib/,app/,prisma/}`; pipeline artifacts in `.cap-dev-pipe/pipeline-output/startd8/run-009-20260601T0045/`. Companions: RUN_003 / RUN_007 / RUN_008 postmortems.*
