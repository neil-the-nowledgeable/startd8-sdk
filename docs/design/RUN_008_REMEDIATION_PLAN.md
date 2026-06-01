# RUN-008 Cross-Feature Incoherence Remediation — Implementation Plan

**Version:** 0.2 (Comprehensive TS-robustness direction — toolchain-backed)
**Date:** 2026-05-31
**Status:** Draft (ready for convergent review)
**Requirements:** `docs/design/RUN_008_REMEDIATION_REQUIREMENTS.md` (v0.2 — FR-1..FR-11)
**Source incident:** `docs/design/RUN_008_CROSS_FEATURE_INCOHERENCE_POSTMORTEM.md`

This plan implements the v0.2 requirements. Every FR maps to a step; every step traces to an FR. **Step 0 (discovery) is already complete** — its findings are the requirements' §0. The landing order is **Track B (TS-stack robustness via the real toolchain) first, then Track A (generation propagation)**: the toolchain verification surface is both the user's primary goal *and* the safety net that converts the run-008 false PASS into an honest FAIL immediately — before generation is touched. This mirrors the postmortem §5 "the classifier upgrade is load-bearing … the visibility surface that makes the inheritance fix testable in production."

---

## Implementation status (2026-06-01)

**Both tracks landed; 54 new tests green; zero regressions** (591 language + 571 implementation_engine + 140 targeted contractors).

- **Track B — toolchain compile-class (FR-4/5/9):** `validators/ts_toolchain.py` — project-level `tsc --noEmit` + `prisma generate`, structured diagnostics, FR-9 loud degradation (`unavailable` ≠ pass). Env-gated postmortem wiring (`_evaluate_ts_toolchain`, `STARTD8_TS_TYPECHECK`). **Proven end-to-end** on the real spike: 5 diagnostics (TS2307 import + 4× TS2322 Prisma `where`), verdict `fail`. *FR-8 `.d.ts` emit deferred — Track A uses a toolchain-free regex export extractor instead.*
- **Track A — generation propagation (FR-1/2/3):** `contractors/upstream_interface.py` — real export extraction, `@/`-alias/relative import resolution, `MissingUpstreamArtifact` (FR-2). Wired into `_build_generation_context` (`upstream_interfaces` key, selected from `depends_on` edges — FR-3) and rendered in the drafter P1 prompt (FR-1). Live path logs missing upstreams (FR-2 surfaced); strict raise available via `require_present=True`.
- **Prior:** FR-6 (`.prisma` first-class), FR-7 (Prisma↔Zod symmetry, wired/auto-FAIL), FR-10 (cross-file integrity in postmortem) — all done.

**Remaining:** OQ-3 host decision (where the pipeline provisions `npm install`/`prisma generate` to flip `STARTD8_TS_TYPECHECK` on); FR-8 `.d.ts` interface emit (optional refinement); FR-11 broader end-to-end regression fixtures.

## Steps

| # | Step | FR | Files | Verify |
|---|------|----|-------|--------|
| **0 ✅ DONE** | **Root-cause discovery** — confirmed G1/G2/G3. See requirements §0 for the full anchor table. | G1/G2/G3 | (read-only) | ✅ anchors captured; all three user hypotheses confirmed |
| **1 ◑ SPIKE DONE / host TBD** | **Verification host & timing decision (OQ-3).** Spike (2026-05-31) ran the real toolchain on a contained run-008 repro and proved the subsumption boundary (see requirements §0 spike table): `tsc`+`prisma generate` **catches** unresolvable imports (TS2307) + invalid `where` on non-`@unique` cols (TS2322), but **does NOT catch** Prisma↔Zod field/type divergence (spread suppresses excess-property checks) → **FR-7 proven mandatory**. Workspace had no `node_modules`/`tsc`/`prisma` → pipeline must *provision* the toolchain. **Still open:** where verification executes + install caching. | OQ-3, FR-9 | spike at `/tmp/run008-spike` (preserve as FR-11 fixture); host decision note pending | ✅ `npm i` (11 pkgs ~14s)+`prisma generate`+`tsc --noEmit` runs clean in a throwaway dir; ◑ pipeline host/caching TBD |
| **2 ✅ DONE** | **`.prisma` first-class recognition + parser** (FR-6). `languages/prisma_parser.py` (`parse_prisma_schema` → `PrismaSchema`/`PrismaModel`/`PrismaField` with `single_column_unique_keys`, `compound_unique_keys`, scalar/relation classification); `languages/prisma.py` (`PrismaLanguageProfile`, full protocol, `validate_syntax` brace-check + parser, `prisma validate` checkpoint cmd); registered via `pyproject.toml` entry point **and** `registry._register_builtins`. Stops the Python fallback. | FR-6 | `languages/prisma_parser.py`, `languages/prisma.py`, `languages/registry.py`, `pyproject.toml`, `tests/unit/languages/{test_prisma_parser.py,fixtures/run008_schema.prisma}` | ✅ 15 parser tests + 591/591 language suite green; `resolve_language(["prisma/schema.prisma"])` → `prisma` (was `python`); mixed Next batch → `nodejs` (no hijack) |
| **3** | **Project-level `tsc --noEmit` backbone + `.d.ts` emit** (FR-4, FR-8). Replace per-file `--isolatedModules` validation with a project program over the generated set using the real `tsconfig`; add `--declaration --emitDeclarationOnly` to produce `.d.ts` → structured interface. Reuse `NodeLanguageProfile` plumbing; avoid the `.js`-tempfile duplicate. | FR-4, FR-8 | `languages/nodejs.py`, `forward_manifest_validator.py` | unit: run-008 set with `@/lib/schemas` → tsc TS2307 surfaced + mapped to FAIL; coherent set → clean; `@/` resolved via tsconfig fixture; `.d.ts` for `lib/value-model.ts` lists `ProfileSchema` |
| **4** | **Prisma in the loop** (FR-5). Run `prisma validate` + `prisma generate` before the Step-3 tsc pass so generated client types exist; invalid `where`/`data` usage becomes a compile error. | FR-5 | verification host wiring, `languages/nodejs.py` | unit/integration: invented `profileId` → tsc error vs generated client; `findUnique({where:{ownerId}})` (non-unique) → error; malformed schema → `prisma validate` fail |
| **5 ✅ DONE (check) / wiring in Step 7** | **Prisma↔Zod symmetry semantic check** (FR-7) — the spike-proven mandatory bespoke check. `validators/prisma_zod_symmetry.py`: `extract_zod_objects` (pragmatic Zod `z.object` extractor, quote/comment-aware) + `check_prisma_zod_symmetry` → `SymmetryViolation`s (`field_missing_in_prisma`/`fk_invented`/`field_type_mismatch`/`field_missing_in_zod`). Entity map = suffix-normalized (`ProfileSchema`→`Profile`), overridable. **Still to wire:** invoke from `validate_disk_compliance` + emit Kaizen (Step 7/FR-10). | FR-7 | `validators/prisma_zod_symmetry.py`, `tests/unit/validators/{test_prisma_zod_symmetry.py,fixtures/*}` | ✅ 13 tests; real run-008 pair → **63 errors** (53 invented fields, 9 invented `profileId` FKs, 1 `Metric.value` type mismatch) where the pipeline reported 0.99 PASS; coherent pair / nested arrays / `z.unknown()` → no false positives |
| **6** | **Loud degradation + fallback floor** (FR-9). When `node`/`tsc`/`prisma`/deps absent → emit `verification-unavailable` (non-PASS); optional reduced-confidence floor runs the lightweight bespoke `@/`-existence + Prisma-usage-regex checks, labelled as such. | FR-9 | `forward_manifest_validator.py`, `languages/nodejs.py` | unit: tsc unavailable + broken set → NOT PASS (verification-unavailable or floor FAIL); verdict surfaces which checks ran |
| **7 ✅ DONE (FR-7 check wired)** | **Wire cross-file integrity into the postmortem** (FR-10). Added a **batch** pass `validators/prisma_zod_symmetry.evaluate_cross_file_integrity(sources)` (the per-file `validate_disk_compliance` can't see cross-file) + `prime_postmortem._evaluate_cross_file_integrity` called right after `_evaluate_disk_quality`. On any error it attributes the finding to the Zod-owning feature and forces FAIL: `disk_quality_score=0`, `success=False`, `verdict=FAIL:cross_file`, `root_cause=CROSS_FILE_CONTRACT`, `pipeline_stage=CROSS_FEATURE_CONTRACT`, semantic issues + new `CAUSE_TO_SUGGESTION` Kaizen entries. No-op without a `.prisma`+Zod pair → no false positives on Python/other batches. *(FR-4/FR-5 toolchain signatures — the `tsc`/`prisma` half — remain for the Track-B toolchain steps 2–4.)* | FR-10 | `validators/prisma_zod_symmetry.py`, `contractors/prime_postmortem.py` (enums + `CAUSE_TO_SUGGESTION` + new method), `tests/unit/contractors/test_cross_file_integrity_postmortem.py` | ✅ 5 wiring tests + 33 total green; run-008 Zod feature → flipped to FAIL with cross-file root cause/stage; coherent batch + Python-only batch → untouched |
| **8** | **Dependency-edge → generation-input plumbing** (FR-3). Producer→consumer edges (`queue.py` + `depends_on` + language-aware import inference) select what gets propagated; bound to direct producers of imported paths. | FR-3 | `contractors/queue.py` (read), `prime_contractor.py` (`_collect_dependency_imports`, `_build_generation_context`) | unit: explicit `depends_on` and inferred-import both select the producer; import-nothing feature → no extra context |
| **9** | **Cross-file propagation into spec/draft context** (FR-1) — **co-land with Step 8**. Inject the producer's real emitted interface from its `.d.ts` (Step 3) + reconcile against `InterfaceContract`; thread into spec-builder/drafter at P0/P1, replacing the name-only guess. | FR-1 | `forward_manifest.py` (cross-file accessor), `implementation_engine/spec_builder.py`, `drafter.py`, `contractors/context_resolution.py`, `prime_contractor.py` | unit: PI-011→PI-012 → PI-012 imports `@/lib/value-model` + `ProfileSchema` (matches `.d.ts`); Zod uses producer field names |
| **10** | **Block-on-missing-upstream** (FR-2). Expected producer artifact absent → `MissingUpstreamArtifact` (`success=False`, distinct `root_cause`/stage), caught — never a silent fallback. | FR-2 | `prime_contractor.py`, exceptions module | unit: PI-012 with PI-011 ungenerated → `MissingUpstreamArtifact`; batch continues; feature `success=False` |
| **11** | **Regression + detector-regression lock** (FR-11). Reproduce all run-008 shapes (import mismatch, Prisma↔Zod divergence, invalid `findUnique`, missing-upstream, toolchain-unavailable); assert coherent-OR-refusal. Feed each broken shape directly to the verifier and assert FAIL/`verification-unavailable` independent of the generation side. | FR-11 | `tests/unit/...`, run-008 fixtures | all shapes → never a silently-divergent PASS; direct-to-verifier FAIL for each broken shape |

**Sequencing rationale.** Step 1 (host decision) gates everything in Track B — it is the load-bearing unknown (requirements OQ-3). Steps 2→7 ship the **toolchain-backed verification surface first**: this alone converts the run-008 false PASS into an honest FAIL/`verification-unavailable` and delivers the "robust TS support" goal, even before generation is fixed. Steps 8→10 (Track A) then fix generation so the now-visible failures actually go away. Step 11 locks both sides.

**Co-landing constraints.**
- **Steps 8 + 9** MUST co-land — edge selection without interface injection changes nothing; injection without edge selection has no input.
- **Steps 3 + 4** are effectively atomic for Prisma projects — a `tsc` pass without `prisma generate` cannot see the generated client types, so the Prisma-usage failures (FR-5's whole point) would be missed. Land 4 immediately after 3 (or together).

**Alignment (OQ-6 RESOLVED = yes, cross-session 2026-05-31).** FR-1/FR-2/FR-3 are the `PLAN_BATCH_ORCHESTRATION` FR-10 inheritance mechanism at the **intra-batch / inter-feature** granularity. A single inheritance implementation serves both granularities: the Plan-Batch-Orchestration session's inter-batch step ("Essential ⑥") is built as the **inter-batch caller of Step 9's accessor**, not a standalone second implementation. The accessor is one interface with a pluggable source (intra-batch = producer `.d.ts` on disk; inter-batch = prior batch's persisted `InterfaceContract`). Land the consolidation in `PLAN_BATCH_ORCHESTRATION_PLAN.md` Appendix C (R3 essential-MVP).

**Inter-batch transition gate (their "Essential ④") — verification-first refinement.** That session's between-batch gate should **prefer `tsc --noEmit` (not `npm test`) for nodejs/TS projects** — Jest transpiles per-file and won't typecheck, so a set that fails `tsc` can pass tests (the run-008 false-PASS). Prefer `tsc --noEmit` over `next build` (faster, and `next build` can be neutered by `typescript.ignoreBuildErrors`). This shares FR-4's signal and may land now (small, isolated) to give the M2-M3 bridge honest signal. **Caveat:** the gate catches the *compile-class* of run-008 (unresolvable imports; typed Prisma misuse once `prisma generate` ran) but **not** the *semantic-class* (Prisma↔Zod field drift, untyped-`fetch` UI divergence) — FR-7 + FR-1 still carry that half.

---

## Step 0 — Discovery Findings

Already complete — see **`RUN_008_REMEDIATION_REQUIREMENTS.md` §0** for the full G1/G2/G3 anchor tables. Summary:

| Gap | Finding | Key anchor |
|-----|---------|-----------|
| **G1** | Cross-file contract is **not** propagated; `file_specs_for_task` returns own-target-files only; deps thread module **names** only; ordering controls merge, not generation input. | `forward_manifest.py:507`; `prime_contractor.py:4168`, `:3828-3842`, `:5001` |
| **G2** | No TS cross-file verification; `tsc --isolatedModules` per-file only; no `@/` resolution; `validate_disk_compliance` Python-only. | `nodejs.py:394`; `forward_manifest_validator.py:392` |
| **G3** | `.prisma` unrecognised → falls back to Python; no Prisma/Zod/Next awareness. | `resolution.py:241-242` |

**Net:** no blocker found except the **verification-host decision (Step 1 / OQ-3)** — running real `tsc`/`prisma` needs `node` + the project toolchain + installed deps. Favourable observation: producer output is already on disk before the consumer develops (`prime_contractor.py:5001`), so FR-1's "read the real `.d.ts`" is achievable without re-ordering the pipeline.

---

## Appendix A — Accepted Suggestions
*(empty — populated after CRP triage)*

## Appendix B — Rejected / Narrowed Suggestions (with rationale)
*(empty — populated after CRP triage)*

## Appendix C — Incoming Suggestions (Untriaged, append-only)
*(CRP review rounds append here)*
