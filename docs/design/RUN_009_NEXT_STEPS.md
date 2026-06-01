# StartD8 — Suggested Next Steps (post RUN-009 remediation)

**Date:** 2026-06-01
**Context:** RUN-009 surfaced four gaps; all are now addressed in code (merged to `main` across `startd8-sdk` + `cap-dev-pipe`). This doc records what's done, what to validate, and what's left — in priority order.

---

## 1. Where things stand

| Gap | Fix | Status |
|-----|-----|--------|
| **A** — `--fresh` wiped plan-declared immutable upstream anchors | `clean-prior-run.sh` do-not-wipe guard (seed `upstream_anchors` ∪ `.cap-dev-pipe/upstream-anchors.txt` ∪ env) + FR-5 untracked warning; SDK seed-emission (`ContextSeed.upstream_anchors` from plan marker) | ✅ merged; anchors restored + git-tracked + listed |
| **B** — Mode-B inheritance (pre-existing upstream files) | `_collect_upstream_interfaces` feeds on-disk anchors (TS exports) + Prisma field-set inheritance (`render_prisma_field_sets`, FR-3) + absent-anchor warning (FR-4) | ✅ FR-1/3/4/6 merged; FR-2 narrowing = minor refinement |
| **C** — classifier blind to cross-file breakage | toolchain-free `scan_unresolvable_imports` wired into the postmortem (`cross_file_imports.py`) | ✅ merged; caught all 8 run-009 broken imports retro |
| **D** — verdict score inversely correlated with delivery | closed as a consequence of C (verdict now reflects reality) | ✅ |

---

## 2. Immediate next step — the validation rerun (in flight)

A `--fresh` prime-contractor rerun against the restored strtd8 foundation is the end-to-end proof of the whole remediation. It should demonstrate:

1. **Gap A:** the 9 M1 anchors (`package.json`, `prisma/schema.prisma`, `lib/db.ts`, …) are **NOT wiped** by `--fresh` (config-floor + the FR-5 "tracked" durability now holds).
2. **Gap B:** consumers inherit the real `@/lib/db` (not invented `@/lib/prisma`); the Zod schema mirrors the Prisma field set (`summary`/`yearsExp`, no invented `bio`).
3. **Gap C:** if anything still slips, the postmortem **FAILs honestly** with attributed `unresolvable_import` / `prisma_zod_symmetry` findings — not a false 1.00 PASS.

**Note (seed signal):** the existing run-009 seed predates the seed-emission fix, so its `upstream_anchors` is injected for this rerun to activate Gap-B Mode-B inheritance. For *future* runs, add the marker block to the plan and re-run plan-ingestion (see §3.2).

**After it finishes, check:** the postmortem verdict + `pipeline_attribution` (should be populated, not `unknown`); whether the M1 anchors survived; `npm run build` / the post-run `tsc` gate verdict; and whether Gap-B made the imports/fields coherent.

---

## 3. Structural reframe (per `CROSS_FILE_CONTRACT_RESOLUTION.md`, 2026-06-01)

That analysis is the load-bearing reframe and **supersedes the narrow "just add Mode B" framing**: the run-009 build-fix pass surfaced **~16 cross-file failures across 7 contract categories**, and **Mode A/B inheritance addresses only one** (module-path). Gaps A/B (shipped) are necessary but cover ~1.5 of 7 categories. The other categories — canonical-schema (field/type/constraint), external-library-API (SDK hallucination), dependency-availability (`pino`), api-request/response-shape, project-config (tsconfig/next.config), type-signature — are **content-level** disagreements that *more inheritance scope cannot fix*. The root is **per-file probabilistic generation (locality)**, not absent inheritance.

**Shipped-signature inventory (Approach B — the "verify-after-generate" classifier, the chronic 4-postmortem deferral):** of the 6 signatures that doc enumerates, **2 are shipped** — unresolvable-import (`cross_file_imports.py`) + Zod↔Prisma symmetry (`prisma_zod_symmetry.py`). **4 remain:** missing-dependency (vs `package.json`), Prisma-field-at-call-site (`db.model.create/update/where` fields vs the schema), compound-key validity (`findUnique`/`where` only `@unique`/`@id`), SDK-type-presence (e.g. `Anthropic.ContentBlockParam` vs the installed `.d.ts`).

## 4. Remaining work (priority order — revised per the reframe)

1. **Complete Approach B — the remaining 4 classifier signatures** *(highest leverage; Tier 1).* This is the chronic deferral and the precondition for measuring everything else (the score-vs-reality inversion). Cheapest path: they extend what's already built — `cross_file_imports.py` (add missing-dependency vs `package.json`) and `prisma_zod_symmetry.py`/`prisma_parser.py` (add call-site field + compound-key checks); SDK-type-presence needs `.d.ts` reading (pairs with Approach A). Each → honest FAIL + Kaizen, no false PASS.
2. **Approach A — pre-flight project-knowledge artifact** *(Tier 2).* Generalizes Gap A/B into one deterministic project-state read (file→exports table, `package.json`, `tsconfig`, Prisma model summary, installed-dep `.d.ts` surface) injected as a P0 spec section. Closes dependency-availability + project-config + external-API at the source. My Gap-B FR-3 Prisma field-set injection is the first slice of this.
3. **Approach D — single-pass batch synthesis** *(Tier 3, untried, high-leverage for small batches).* Generate the whole ≤~15-file batch in one prompt so the LLM literally sees the files it references — addresses *all* categories at once by construction. run-009's 13-file batch is squarely in range. Cheapest to prototype (workflow-level, not primitive-level).
4. **Plan-marker adoption** *(proper Gap-A FR-1 path).* Add `<!-- cap-dev-pipe: upstream-anchors -->` to `typescript-plan.md` so ingestion emits `upstream_anchors` (vs the hand-maintained `.cap-dev-pipe/upstream-anchors.txt`).
5. **Direct strtd8 delivery fix / the in-flight rerun** — the rerun validates Gaps A/B/C live and will empirically show which of the 7 categories remain → the data that prioritizes signature #1.
6. **Generalized compile-gate (Go/Java/C#)** — `COMPILE_GATE_*` v0.3 ready when a compiled-language batch is on the roadmap. (A provisioned `tsc`/`prisma` gate would itself cover several Approach-B categories for TS — but is toolchain-dependent; the in-process signatures fire even unprovisioned.)

---

## 4. Architectural watch-items

- **Shared `upstream_anchors` contract (3rd consumer).** Gap A (cleanup) and Gap B (inheritance) already share it. The parallel `PLAN_BATCH_ORCHESTRATION` FR-10 (inter-batch inheritance) is the same mechanism at a different seam. **If FR-10 also consumes `upstream_anchors`, run a joint CRP** over the contract before all three diverge — that's the one genuinely architectural decision worth external review.
- **Anchor durability discipline.** Untracked anchors are unrecoverable if wiped. Keep the M1 ship set git-committed (now done); the FR-5 warning is the backstop, not the guarantee.
- **The verification net is the safety margin.** With Gap C live, iterate Gaps A/B against real runs — a regression surfaces as an honest FAIL, not a silent PASS. This is why heavy upfront review of the remaining refinements isn't warranted.

---

*Authored 2026-06-01. Companions: `RUN_009_POSTMORTEM.md`, `RUN_009_GAP_A_REQUIREMENTS.md`/`_PLAN.md`, `RUN_009_GAP_B_REQUIREMENTS.md`, `COMPILE_GATE_*`.*
