# CKG Phase 1 — Where Reviewer Input Is Most Needed

This review is **not** a blanket pass. The requirements (v2.1) and plan (v1.1) were already
hardened by a spike (run against the real target `strtd8/`, see `SG_FINDINGS.md`) and a
self-reflective planning loop. Spend your suggestions on the six high-uncertainty decisions below;
deprioritize generic completeness/style notes on settled material.

**Read for context before reviewing:** `CODE_KNOWLEDGE_GRAPH_DESIGN.md` (the architecture + §0
research reconciliation), `CROSS_FILE_CONTRACT_RESOLUTION.md` (the 16 RUN_009 failures this exists
to kill), `scripts/spikes/ckg/SG_FINDINGS.md` (what the spike proved already-built vs the gap).

## Focus asks (answer each: Summary / Rationale / Assumptions / Suggested improvements)

1. **Is the reframe sound — is Phase 1 UNDER-scoped?** The plan asserts SG-1 (`prisma_parser`) and
   SG-3 (`prisma_zod_symmetry`) plus the "5 of 6 shipped Approach-B signatures" already cover most
   of the 16 failures, so Phase 1 builds only 3 new checks. Pressure-test the *coverage holes within
   the existing 5*: does `prisma_zod_symmetry` handle nested Zod objects, `z.union`/discriminated
   unions, `.extend()`/`.merge()`, and api-shape mismatches **beyond flat field-presence**? If those
   gaps let RUN_009-class drift through, Phase 1 is under-scoped — name the missing checks.

2. **REQ-CKG-620 route-shape feasibility (OQ-2).** Can SCIP-resolved Next.js (app-router) handler
   signatures actually yield usable request/response *shapes* (Response generics, inferred returns,
   `NextResponse.json(...)` body types)? Is the spike-gate + narrowed-fallback the right call, or is
   route-shape fundamentally a tsc-gate concern that shouldn't be in Phase 1 at all?

3. **Signature (f) strategy (a) sufficiency (REQ-CKG-610).** Does validating only *referenced*
   external members against the resolved SCIP occurrence set (not enumerating a package's exports)
   reliably catch #4/#11 **without false-positives** on real code — re-exports, namespace imports,
   type-only imports, `import type`, conditional exports, subpath exports? When must we fall back to
   indexing the `.d.ts` directly (strategy b)?

4. **Integration / surface risk (REQ-CKG-600, 690a).** Is extending the shipped, wired
   `_evaluate_cross_file_integrity` the right move, or should the 3 new checks be a *separate* pass
   to avoid coupling? Is "land the 690a regression-lock before any surface edit" an adequate
   behavior-preservation guarantee, or is more isolation needed?

5. **Per-batch SCIP integration point (OQ-3, REQ-CKG-230).** At what point in a prime-contractor run
   is the target project actually installed/buildable so `scip-typescript` can index it? If batches
   run before `npm install` / against partially-generated code, does the advisory-degrade path leave
   the very failures we care about (#4/#11/#15) *uncaught* in practice? Specify the trigger point.

6. **Deferral correctness.** Is it safe for Phase 1 to defer the SQLite CKG store, the OTel
   projection, taint, and tree-sitter draft mode — and to drop failures #10 (unused params) and #16
   (framework rendering-mode) to a tsc-gate track? Call out any deferral that will force expensive
   rework or that hides a failure category the pipeline silently mis-scores.
