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

## 2. Validation rerun — DONE (bjpurue64, 2026-06-01)

The `--fresh` rerun against the restored strtd8 foundation proved the remediation:

1. **Gap A held:** "Honoring 9 upstream anchor(s) — NOT wiped." The M1 anchors survived `--fresh`.
2. **Gap C held:** **honest verdict PARTIAL / 0.78** (4 succeeded, 1 failed) — no false 1.00 PASS.
3. **Lone failure was a tooling false-positive, now fixed:** `TS2802` (Set/Map iteration "needs es2015+") from the per-file tsc check, which had no project tsconfig and defaulted to ES3. The project targets ES2017, so the file was valid. **Fixed** by pinning `--target ES2022 --lib …` in the per-file check (+ a strip backstop for the target/lib family). An equivalent rerun is effectively **5/5 buildable**.

> **Working-tree caveat (learned the hard way):** because this rerun ran on the *old 9-anchor seed* (M1 only), `--fresh` wiped the **M2/M3 working-tree files** even though they were committed — recoverable via `git checkout HEAD -- app lib`, but disruptive. **Before any future `--fresh` M-batch**, ensure the plan slice carries the `upstream-anchors` marker (or the `.cap-dev-pipe/upstream-anchors.txt` floor covers M1–M3) so the prior milestones aren't clobbered. The 24-anchor config + M4 marker now cover this going forward.

---

## 3. Structural reframe (per `CROSS_FILE_CONTRACT_RESOLUTION.md`, 2026-06-01)

That analysis is the load-bearing reframe and **supersedes the narrow "just add Mode B" framing**: the run-009 build-fix pass surfaced **~16 cross-file failures across 7 contract categories**, and **Mode A/B inheritance addresses only one** (module-path). Gaps A/B (shipped) are necessary but cover ~1.5 of 7 categories. The other categories — canonical-schema (field/type/constraint), external-library-API (SDK hallucination), dependency-availability (`pino`), api-request/response-shape, project-config (tsconfig/next.config), type-signature — are **content-level** disagreements that *more inheritance scope cannot fix*. The root is **per-file probabilistic generation (locality)**, not absent inheritance.

**Shipped-signature inventory (Approach B — the "verify-after-generate" classifier, the chronic 4-postmortem deferral): now COMPLETE.** Of the 6 signatures: **5 ship as in-process postmortem checks** — unresolvable-import + missing-dependency (`cross_file_imports.py`), Zod↔Prisma symmetry (`prisma_zod_symmetry.py`), Prisma-field-at-call-site + compound-key validity (`prisma_usage.py`). The 6th — SDK-type-presence (e.g. `Anthropic.ContentBlockParam` vs the installed `.d.ts`) — is **dispositioned to the post-run `tsc` gate** (reading `.d.ts` in-process pairs with Approach A; the provisioned compiler already covers it). All wired into `prime_postmortem.py` with `CAUSE_TO_SUGGESTION` Kaizen mappings → honest FAIL, no false PASS.

## 4. Remaining work (priority order — revised per the reframe)

1. **~~Complete Approach B — the remaining 4 classifier signatures~~ DONE (2026-06-01).** All 5 in-process signatures ship (`cross_file_imports.py` + `prisma_usage.py` + `prisma_zod_symmetry.py`); SDK-type-presence is covered by the `tsc` gate. The score-vs-reality inversion is closed (rerun verified, §2). **Approach A and Approach D below are now the highest-leverage remaining levers.**
2. **Approach A — pre-flight project-knowledge artifact** *(Tier 2; now highest-leverage).* Generalizes Gap A/B into one deterministic project-state read (file→exports table, `package.json`, `tsconfig`, Prisma model summary, installed-dep `.d.ts` surface) injected as a P0 spec section. Closes dependency-availability + project-config + external-API at the source. My Gap-B FR-3 Prisma field-set injection is the first slice of this. **Build this as the Mieruka `CodeGraph` slice — NOT a bespoke scanner** — so code-gen coherence and code-observability share one resolver (two-tier: tree-sitter for partial/non-building code, SCIP for buildable). See `CROSS_FILE_CONTRACT_RESOLUTION.md` §11. Decide before implementing.
3. **Approach D — single-pass batch synthesis** *(Tier 3, untried, high-leverage for small batches).* Generate the whole ≤~15-file batch in one prompt so the LLM literally sees the files it references — addresses *all* categories at once by construction. run-009's 13-file batch is squarely in range. Cheapest to prototype (workflow-level, not primitive-level).
4. **~~Plan-marker adoption~~ DONE (2026-06-01).** The M4 plan slice (`typescript-plan-m4.md`) carries the `<!-- cap-dev-pipe: upstream-anchors -->` marker; the parser was also fixed to accept Next.js dynamic/group route segments (`[id]`/`[...slug]`/`(group)`). Add the marker to M5/M6 plan slices as they're written.
5. **~~Direct strtd8 delivery / the rerun~~ DONE (§2).** The rerun confirmed Gaps A/B/C live. Empirical residual = the content-level categories Approach A/D target (above). strtd8's own next step is M4 — see `strtd8/docs/V1_COMPLETION_PLAN.md`.
6. **Generalized compile-gate (Go/Java/C#)** — `COMPILE_GATE_*` v0.3 ready when a compiled-language batch is on the roadmap. (A provisioned `tsc`/`prisma` gate would itself cover several Approach-B categories for TS — but is toolchain-dependent; the in-process signatures fire even unprovisioned.)

---

## 4. Architectural watch-items

- **Shared `upstream_anchors` contract (3rd consumer).** Gap A (cleanup) and Gap B (inheritance) already share it. The parallel `PLAN_BATCH_ORCHESTRATION` FR-10 (inter-batch inheritance) is the same mechanism at a different seam. **If FR-10 also consumes `upstream_anchors`, run a joint CRP** over the contract before all three diverge — that's the one genuinely architectural decision worth external review.
- **Anchor durability discipline.** Untracked anchors are unrecoverable if wiped. Keep the M1 ship set git-committed (now done); the FR-5 warning is the backstop, not the guarantee.
- **The verification net is the safety margin.** With Gap C live, iterate Gaps A/B against real runs — a regression surfaces as an honest FAIL, not a silent PASS. This is why heavy upfront review of the remaining refinements isn't warranted.

---

*Authored 2026-06-01. Companions: `RUN_009_POSTMORTEM.md`, `RUN_009_GAP_A_REQUIREMENTS.md`/`_PLAN.md`, `RUN_009_GAP_B_REQUIREMENTS.md`, `COMPILE_GATE_*`.*
