# Code Knowledge Graph — Phase 1 Implementation Plan

> **Version:** 1.2 (2026-06-01 — CRP triage applied; adds Inc-5 verdict-gating)
> **Status:** Draft plan (post-CRP)
> **Requirements:** [CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md](./CODE_KNOWLEDGE_GRAPH_PHASE1_REQUIREMENTS.md) v2.2
> **Spike:** `scripts/spikes/ckg/SG_FINDINGS.md`
> **Principle:** ship the Verifier (Approach B) for the run-009 stack; reuse the 5 shipped
> signatures; add only the 3 genuinely-missing checks behind scip-typescript.

---

## 1. Approach

Extend the **existing** Verifier surface — `contractors/prime_postmortem.py:_evaluate_cross_file_integrity`
(~lines 1660–1759) — with three new checks backed by a thin scip-typescript layer. No new
substrate, no store. The new checks **degrade to advisory** when the Node toolchain / installed
project is unavailable, so the 5 toolchain-free signatures always run. Build the 16-failure
regression corpus alongside, since it is both the acceptance gate and the dev harness.

### Module layout (new)
```
src/startd8/code_observability/
  scip_runner.py     # REQ-CKG-200: subprocess `scip-typescript index` → index path
  scip_reader.py     # REQ-CKG-210/220: parse SCIP via vendored scip_pb2; exposes typed accessors
                     #   external_member_refs() / cross_file_edges() / routes() — no separate facts model
  scip_pb2.py        # vendored generated bindings (from scip.proto, pinned proto version)
src/startd8/validators/
  external_type_presence.py   # REQ-CKG-610: signature (f)
  route_shape.py              # REQ-CKG-620: route request/response shape
  # tsconfig alias check (REQ-CKG-630): extend cross_file_imports.py (already reads aliases)
```
Wiring point: `prime_postmortem.py:_evaluate_cross_file_integrity` gains the 3 checks behind a
`scip_facts` object (None when unavailable → new checks skipped + logged).

---

## 2. Work breakdown (increments)

Ordered by value × (1 − uncertainty). Inc-0 → Inc-1 first (highest value, lowest risk).

### Inc-0 — SCIP plumbing (REQ-CKG-200/210/220)  · ~2d  *(+0.5d: safety + cache, from CRP)*
- Vendor `scip_pb2.py` (pin the proto version; record source commit) — avoids a protoc build dep.
- `scip_runner.run_index(project_root) -> Path|None`: subprocess `scip-typescript index --output …`;
  returns None + warning if tool missing or project not indexable (REQ-CKG-230). **Safety (R2-S6/R4-S3):**
  resolved `project_root` must stay under the workspace root, `cwd=project_root`, no `shell=True`,
  wall-clock timeout, log pinned tool version on failure; **pre-validate `package.json`/`tsconfig.json`
  parse** before invoking (corruption → advisory degrade, not a subprocess crash).
- **Cache/staleness (R2-S4):** index key = hash(project_root, lockfile/package.json, batch file
  manifest); rebuild when the manifest changes; run the index **once immediately before** the
  cross-file scans (never reuse a pre-batch index).
- `scip_reader`: load index; expose typed accessors `external_member_refs()` (occurrence symbols
  with package + member descriptor, e.g. `npm zod 3.x …/ZodObject#extend().`), `cross_file_edges()`,
  `routes()`. **Read from `Document.occurrences`, NOT `Index.external_symbols`** (empty in 0.4.0 —
  verified). *(reqs v2.1: REQ-CKG-220 collapsed in here — no separate `ScipFacts` model.)*
- **Tests:** golden test against a committed small `.scip` (or generate in CI if the Node tool is present); assert external member descriptors parse.
- **Exit:** `ScipFacts` available for `strtd8/` in CI-or-local; graceful None path tested.

### Inc-1 — Signature (f): external-type-presence (REQ-CKG-610)  · ~1.5d  ★ highest value
- `external_type_presence.scan(sources, scip_facts) -> [Violation]`: for each external-package
  member reference in generated code, assert it resolves to a real symbol; unresolved → violation
  (`drafter / cross-file contract / external_type_presence`).
- Decide enumeration strategy (OQ-1): (a) validate only *referenced* members against the resolved
  occurrence set, vs (b) index the dependency's `.d.ts` directly to enumerate valid exports. Start
  with (a) — sufficient for #4/#11; spike (b) only if (a) yields false-positives.
- Wire into `_evaluate_cross_file_integrity` behind `scip_facts`.
- **Tests — import-form matrix (R1-S5):** beyond invented `Anthropic.ContentBlockParam` (flag) /
  real `Anthropic.TextBlockParam` (pass) / `import { defineConfig } from 'next'` (flag #4), each
  fixture states expected behavior for namespace / named / default / `import type` / re-export /
  subpath / conditional-export / helper-type forms, with the strategy-(b) fallback trigger noted.
- **Exit:** #4 + #11 detected, zero false-positive across the import-form matrix.

### Inc-2 — tsconfig path-alias existence (REQ-CKG-630)  · ~1.5d  *(was 0.5d — real parsing, R2-S1)*
- **Correction (verified):** `cross_file_imports.py` does **not** read `compilerOptions.paths` — it
  uses a hardcoded `alias_bases=("", "src")` heuristic. So this is real new work: parse
  `tsconfig.json`/`tsconfig.*.json` `paths` **honoring `extends` chains**, map each pattern to its
  filesystem target(s), flag non-existent targets. `@/` *import* resolution stays with the existing
  unresolvable-import signature; this owns *alias-definition* validity.
- **Tests:** `@/* → ./src/*` with no `src/` flagged (#5); multi-level `extends` resolves; valid alias passes (no FP).

### Inc-3 — Route request/response-shape (REQ-CKG-620)  · ~2–3d  ⚠ highest uncertainty (OQ-2)
- **Sub-spike first (0.5d):** confirm SCIP exposes Next.js handler request/response types usefully
  (Response generics, inferred return, `NextResponse.json(...)` body). **Record exactly one decision
  (R1-S4):** (i) SCIP type field-set check, (ii) literal `NextResponse.json` body field-set check,
  (iii) tsc-only diagnostic handoff, or (iv) unsupported → **#15 removed from 690b** and tracked by
  the tsc/framework gate. Update 690b + the coverage matrix to match the decision.
- `route_shape.scan(sources, scip_facts)`: bind UI consumer expected shape ↔ route actual response
  type; diff. Reuse the field-diff style from `prisma_zod_symmetry`.
- **Tests:** UI consuming a `body` field absent from the route response flagged (#15).
- **Exit:** #15 detected; documented fidelity bound.

### Inc-4 — Extract verifier + unify + regression corpus (REQ-CKG-600/690/235/236)  · ~2.5d
- **Extract `validators/cross_file_verifier.py`** (R1-S2/R2-S2): a typed `CrossFileCheck` registry;
  `prime_postmortem._evaluate_cross_file_integrity` becomes a thin caller that **returns a typed batch
  result** (verdict + per-check availability + findings, R3-S4) — not just report files. Explicitly
  **do not** import `scip_runner`/`cross_file_verifier` from `implementation_engine` or
  `PrimaryContractorWorkflow` (grep/arch test; R2-S2).
- **Finding contract (REQ-CKG-235/R1-S6/R4-F2):** every check emits `check_id/source/feature/severity/
  expected_vs_actual/evidence/availability_state/scope/message/remediation_hint`.
- **Materialization guard (REQ-CKG-236/R2-S3):** checks run only after batch files are flushed;
  generated-but-absent paths → `skipped_not_materialized`, never silently dropped.
- **LLM-reviewer defer (NFR-6/R4-S1):** edit the `contractor_prompts.yaml` review template to mark
  cross-file/external-type checks out of scope for the per-feature review.
- **Optional findings export (OQ-4/R2-F5):** write `.startd8/state/ckg-findings-{run_id}.json` on FAIL.
- **690a (land FIRST):** lock the 5-existing-signature categories byte-equivalent **before** the
  extraction/refactor; **+ Zod composition audit** (nested/union/discriminated/`.extend`/`.merge`/
  `lazy`/imported — R1-S3/F5), each detected / classified / explicitly excluded.
- **690b (end):** all 16; new checks catch #4/#11/#5 (and #15 iff 620 lands) at **feature AND run
  level**; include the single-failure dilution fixture → zero false-PASS.
- **No `[code-observability]` pip extra** (reqs v2.2 §6: protobuf already present + vendored
  `scip_pb2`; only the Node `scip-typescript` tool is a prereq). Document install in `docs/` +
  operator preflight; assert core suite green with the Node tool absent (REQ-CKG-230/NFR-1).

### Inc-5 — Verdict gating + aggregate any-error rule (REQ-CKG-240/245, NFR-5)  · ~2d  ★ CRITICAL
*The CRP found (verified in code) that the verifier is currently non-gating; without this increment,
Phase 1 produces a report nobody acts on and 690b is unachievable.*
- **Synchronous consumption (R3-S1):** make the batch cross-file verifier feed its verdict into the
  prime run result / CLI exit code — replace the detached `daemon=False` `launch_prime_postmortem_async`
  path (or join it deterministically before final status) so a FAIL gates the run.
- **Aggregate any-error rule (R3-S2):** any error-severity cross-file finding caps the batch verdict
  at FAIL/PARTIAL, independent of `mean(disk_scores)` vs `_PASS_THRESHOLD=0.8`.
- **Determinism (NFR-5/R3-S3):** index + verifier complete (awaited/joined) before final status in
  CI/acceptance; 20 repeats → identical verdict.
- **Tests:** batch with #4/#11 → non-PASS run result/exit; 12 clean + 1 cross-file FAIL → non-PASS
  (dilution fixture); 20-run determinism check.

---

## 3. Sequencing & dependencies

```
Inc-0 (SCIP plumbing) ──► Inc-1 (signature f) ──► Inc-2 (tsconfig) ──► Inc-3 (route-shape, sub-spike gated)
        └───────────────► Inc-4 (corpus + unify) runs alongside, finalizes last
```
Inc-1 depends on Inc-0. Inc-2 is independent (no SCIP) — could land first as a quick win. Inc-3 is
gated on its sub-spike. Inc-4 accumulates throughout; the regression half (5 existing signatures)
can be encoded immediately, before any new code.

## 4. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Route-shape extraction from SCIP is low-fidelity (OQ-2) | Sub-spike gates Inc-3; narrow acceptance if needed; #15 is the only failure depending on it |
| scip-typescript needs a cleanly-installed project; mid-batch code isn't built | Run per-batch against installed disk state; new checks advisory when unindexable (REQ-CKG-230) |
| Enumerating valid exports without a reference (OQ-1) | Start with referenced-member validation (a); `.d.ts` indexing (b) only if needed |
| Vendored `scip_pb2` drifts from tool's SCIP version | Pin proto version; CI note; reader tolerant of unknown fields (protobuf default) |
| Duplicating/!regressing the 5 shipped signatures | Inc-4 regression half locks current behavior before touching the surface |
| Node 26 / tool-version churn | Pin `@sourcegraph/scip-typescript` version; record in extra |

## 5. Test plan

- **Unit:** each new check in isolation (Inc-1/2/3) + `scip_reader` golden parse (Inc-0).
- **Regression:** the 5 existing signatures over the corpus (no behavior change).
- **Acceptance (REQ-CKG-690):** 16/16 detected, zero false-PASS, on the run-009 corpus.
- **Degrade:** corpus run with `scip-typescript` absent → 5 signatures still fire; 3 new advisory.

## 6. Rollout

- Behind the existing postmortem path (no separate flag needed — the Verifier already runs);
  new checks self-gate on `scip_facts is not None`.
- Land Inc-2 + Inc-1 first (close #4/#11/#5), then Inc-3 (#15). Ship the corpus test with Inc-1.

## 7. Effort summary

| Inc | REQ | Effort | Risk |
|-----|-----|--------|------|
| 0 SCIP plumbing (+safety/cache) | 200/210/220 | ~2d | Low |
| 1 signature (f) + import-form matrix | 610 | ~1.5d | Low |
| 2 tsconfig **paths** parsing | 630 | ~1.5d | Low |
| 3 route-shape | 620 | ~2–3d | **Med-High (OQ-2)** |
| 4 extract verifier + unify + corpus | 600/690/235/236 | ~2.5d | Med |
| **5 verdict gating + aggregate rule** | **240/245/NFR-5** | **~2d** | **Med ★ CRITICAL** |

**Total ≈ 11.5–12.5 days** — up from ~7–8d. The CRP grew scope by adding **Inc-5 (verdict gating,
the load-bearing fix)**, real tsconfig parsing (Inc-2), and the verifier extraction + finding
contract (Inc-4). This is the review working: the original plan would have shipped checks that never
gated the run. Inc-5 + Inc-0/Inc-1 are the critical path; Inc-3 remains the only feasibility risk.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Named SCIP lifecycle step | gpt-5.5 | → §8 OQ-3 (reqs) + Inc-0 cache/lifecycle | 2026-06-01 |
| R1-S2 | Extract checks to `CrossFileCheck` registry | gpt-5.5 | → REQ-CKG-600 + Inc-4 (`cross_file_verifier.py`) | 2026-06-01 |
| R1-S3 | Zod composition audit before locking | gpt-5.5 | → Inc-4 690a Zod audit | 2026-06-01 |
| R1-S4 | Inc-3 route-shape decision table | gpt-5.5 | → Inc-3 sub-spike (4 options) + REQ-CKG-620 | 2026-06-01 |
| R1-S5 | Inc-1 import-form matrix | gpt-5.5 | → Inc-1 tests + REQ-CKG-610 | 2026-06-01 |
| R1-S6 | Normalized verifier result contract | gpt-5.5 | → REQ-CKG-235 finding contract | 2026-06-01 |
| R2-S1 | Real tsconfig `paths`+`extends` parsing | composer-2.5 | → Inc-2 (bumped to 1.5d) + REQ-CKG-630 (verified) | 2026-06-01 |
| R2-S2 | `cross_file_verifier.py` module; batch-only wiring | composer-2.5 | → Inc-4 + REQ-CKG-600 (arch test: no import from impl-engine) | 2026-06-01 |
| R2-S3 | Disk-flush precondition | composer-2.5 | → REQ-CKG-236 + Inc-4 materialization guard | 2026-06-01 |
| R2-S4 | SCIP index cache invalidation key | composer-2.5 | → Inc-0 cache/staleness | 2026-06-01 |
| R2-S5 | Remove pip extra; align header to v2.2 | composer-2.5 | → header v1.2/reqs v2.2; Inc-4 pip-extra removed | 2026-06-01 |
| R2-S6 | `scip_runner` subprocess safety | composer-2.5 | → Inc-0 safety (cwd/no-shell/timeout/path-bound) | 2026-06-01 |
| R3-S1 | **Sync verdict consumption (CRITICAL)** | claude-opus-4-8 | **verified**; → Inc-5 + REQ-CKG-240 (gate the run) | 2026-06-01 |
| R3-S2 | **Aggregate any-error rule (CRITICAL)** | claude-opus-4-8 | **verified**; → Inc-5 + REQ-CKG-245 | 2026-06-01 |
| R3-S3 | Deterministic completion (join) | claude-opus-4-8 | → Inc-5 + NFR-5 | 2026-06-01 |
| R3-S4 | Verifier returns typed batch result | claude-opus-4-8 | → REQ-CKG-600 + Inc-4 | 2026-06-01 |
| R3-S5 | 690b assert aggregate/run-level non-PASS | claude-opus-4-8 | → REQ-CKG-690b two-level acceptance | 2026-06-01 |
| R4-S1 | LLM reviewer defers cross-file (prompt edit) | gemini-3.1-pro | → NFR-6 + Inc-4 `contractor_prompts.yaml` edit | 2026-06-01 |
| R4-S3 | scip_runner pre-flight config-parse check | gemini-3.1-pro | → Inc-0 safety (pre-validate package.json/tsconfig) | 2026-06-01 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R4-S2 | Consolidate duplicate `_review_draft`/`_areview_draft` parsing in `primary_contractor_workflow.py` into `implementation_engine.reviewer` | gemini-3.1-pro | **Out of scope for CKG Phase 1.** This is a pre-existing refactor of the contractor review *parsing* path, unrelated to the cross-file verifier; bundling it couples a hot-path refactor to the CKG work and risks regression in the per-feature review loop. Tracked separately as contractor tech-debt; not a CKG requirement. (NFR-6/R4-S1 already handles the only CKG-relevant LLM-reviewer change — deferring cross-file checks — without touching the parsing internals.) | 2026-06-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — gpt-5.5 — 2026-06-01 18:45 UTC

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-01 18:45:00 UTC
- **Scope**: Dual-document architectural review focused on CKG Phase 1 under-scope risk, route-shape feasibility, SCIP integration, and accidental complexity in the lead/primary contractor verifier path.

##### Focus Ask Responses

1. **Phase 1 under-scope**
   - **Summary answer:** Partial: the reframe is mostly sound, but Phase 1 is under-scoped unless it explicitly audits the current Zod/Prisma extractor limits before claiming the 5 existing signatures cover RUN_009-class drift.
   - **Rationale:** The plan leans on "5 shipped signatures" and `prisma_zod_symmetry`, but the current extractor is a pragmatic top-level `z.object` parser. It does not prove coverage for nested objects, discriminated unions, `z.union`, `.extend()`, `.merge()`, or route response shapes where the mismatch is outside a flat Zod object field set.
   - **Assumptions / conditions:** This is acceptable only if Inc-4 adds regression fixtures for those Zod patterns or narrows the coverage claim to flat object schemas.
   - **Suggested improvements:** Add a "Zod coverage audit" task under Inc-4 and require explicit pass/narrow/tsc-handoff outcomes.

2. **REQ-CKG-620 route-shape feasibility**
   - **Summary answer:** The spike-gate is the right call, but the fallback is currently too vague to protect end users from another false PASS.
   - **Rationale:** SCIP can resolve symbols, but Next.js route bodies often come from `NextResponse.json(...)`, inferred returns, helper functions, or `Response` values without useful generics. If the sub-spike cannot recover concrete field sets, route-shape should either use a TypeScript checker/literal-body extractor or be marked outside the 16/16 acceptance promise.
   - **Assumptions / conditions:** The route-shape check should fail closed only when the toolchain is available and the route is analyzable; otherwise the report must say "unverified," not "passed."
   - **Suggested improvements:** Add a decision table to Inc-3: SCIP field-set available, literal `NextResponse.json` field-set available, tsc-only handoff, or out-of-scope with acceptance adjusted.

3. **Signature (f) strategy (a) sufficiency**
   - **Summary answer:** Referenced-member validation is a good first slice for #4/#11, but it needs import-form fixtures before it can be treated as robust.
   - **Rationale:** The requirements name straightforward member references, while real code will include namespace imports, re-exports, `import type`, subpath exports, conditional exports, and members reached through package helper types. Strategy (a) can avoid enumerating every package export, but it must define when an unresolved occurrence is evidence of a bad reference versus a SCIP/indexing limitation.
   - **Assumptions / conditions:** Strategy (b), direct `.d.ts` indexing, should be an explicit fallback for ambiguous import forms rather than only for observed false positives after the fact.
   - **Suggested improvements:** Add an Inc-1 acceptance matrix covering these import forms and a fallback trigger list.

4. **Integration / surface risk**
   - **Summary answer:** Extending `_evaluate_cross_file_integrity` is acceptable only as a compatibility facade; the new checks should live behind a small verifier registry to avoid adding accidental complexity to an already crowded postmortem method.
   - **Rationale:** The current surface already reads files, calls Zod/Prisma checks, import checks, dependency checks, Prisma usage checks, maps findings to features, mutates verdict fields, and formats errors. Adding SCIP lifecycle, route-shape, external API checks, and availability state inline will couple IO, orchestration, and check logic in one method.
   - **Assumptions / conditions:** The existing method name and call site can remain stable for behavior preservation, but its internals should delegate to a typed check list.
   - **Suggested improvements:** Add an Inc-4 subtask for a `CrossFileCheck` contract and verifier registry, with 690a proving identical output for the 5 existing checks before adding new checks.

5. **Per-batch SCIP integration point**
   - **Summary answer:** OQ-3 is not resolved enough; "installed disk state" needs a named lifecycle point in the prime/primary contractor run.
   - **Rationale:** If SCIP runs before generated files are materialized, before dependency installation, or after a partial batch, the advisory path can leave #4/#11/#15 unverified. The plan should say whether the index runs after batch write, after `package.json`/lockfile changes are applied, after optional install, and before postmortem scoring.
   - **Assumptions / conditions:** For generated dependencies, the verifier needs either a pre-existing `node_modules` contract or a dependency-install step before SCIP.
   - **Suggested improvements:** Add an Inc-0/Inc-4 lifecycle sequence: materialize batch, verify/install dependencies as configured, run SCIP once, then run all SCIP-backed checks against the same index.

6. **Deferral correctness**
   - **Summary answer:** Deferring SQLite, OTel projection, taint, and tree-sitter draft mode is safe for Phase 1; deferring #16 is safe only if the scoring/reporting model makes it visibly unverified rather than silently green.
   - **Rationale:** Phase 1's value is immediate false-PASS reduction, so the store/projection can wait. However, #16 framework rendering mode affects whether a Next.js app actually deploys, and #10 unused params are already compiler/lint-class issues; if they are deferred, the acceptance claim must not imply the stack is fully verified without the tsc/framework gate.
   - **Assumptions / conditions:** The report should distinguish "caught by CKG," "caught by tsc/framework gate," and "deferred/unverified."
   - **Suggested improvements:** Add a verdict taxonomy that separates PASS, FAIL, and UNVERIFIED categories by check family.

##### Executive Summary

- The plan is directionally strong because it reuses shipped validators and avoids a premature store, but it needs sharper boundaries around what the existing validators actually prove.
- The most important robustness gap is lifecycle: SCIP must run at a named post-materialization, dependency-ready point or its advisory degradation will preserve false-PASS behavior for the failures it is meant to catch.
- The main accidental-complexity risk is growing `_evaluate_cross_file_integrity` into a larger god method; keep the surface, but move checks behind a typed registry and result contract.
- Route-shape should stay spike-gated, but the fallback must change the acceptance promise or route to a tsc/literal-body extractor so #15 is not counted as closed without evidence.
- End-user value improves if postmortem output explains not only violations, but also which checks ran, which were unavailable, and what remains unverified.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Ops | high | Add a named SCIP lifecycle step: materialize the batch to disk, confirm dependency state, optionally install or declare install unavailable, run `scip-typescript` once, then run SCIP-backed checks against that index before postmortem scoring. | The current "run per-batch against installed disk state" line does not specify where the target becomes installed/buildable; if the index is unavailable at the wrong time, #4/#11/#15 can remain advisory and look successful to users. | Section 3 "Sequencing & dependencies" and Section 4 risk row "scip-typescript needs a cleanly-installed project" | Add tests for three states: dependency-ready project runs SCIP and checks fire; missing tool records UNVERIFIED/advisory; generated dependency absent prevents a PASS claim for SCIP-backed categories. |
| R1-S2 | Architecture | high | Keep `_evaluate_cross_file_integrity` as the stable facade, but add an Inc-4 subtask to extract its inline checks into a small `CrossFileCheck` registry returning normalized finding and availability records. | The plan currently says the method "gains the 3 checks"; the method already aggregates Zod/Prisma, import, dependency, Prisma-usage, feature attribution, verdict mutation, and error formatting. Adding SCIP inline increases accidental complexity in the lead/primary contractor verification path. | Section 1 "Approach" after "Wiring point" and Inc-4 "Unify + regression corpus" | 690a should snapshot current outputs for the 5 existing signatures, then a registry refactor should produce byte-equivalent feature verdicts before new checks are registered. |
| R1-S3 | Validation | high | Add a Zod coverage audit before declaring the 5 shipped signatures fully locked: include nested Zod objects, `z.union`, discriminated unions, `.extend()`, `.merge()`, `z.lazy`, and schemas imported from helper modules. | The focus asks specifically pressure-test holes inside the existing validators; current coverage is proven for flat top-level `z.object` fields, not the common composition forms that can hide API-shape and schema drift. | Inc-4 regression corpus, before "690a regression-lock" | Add corpus fixtures where each composition form has one coherent and one drifting example; the accepted outcome is either detection or an explicit documented limitation tied to tsc/route-shape handoff. |
| R1-S4 | Interfaces | high | Replace Inc-3's single route-shape fallback sentence with a decision table: SCIP type field-set available, `NextResponse.json` literal-body field-set available, tsc-only diagnostic, or unsupported with #15 removed from 690b. | Without a concrete fallback, the plan can "narrow acceptance" while still saying the phase closes #15; that weakens the end-user value of the verifier. | Inc-3 "Route request/response-shape" and Section 5 "Test plan" | The Inc-3 sub-spike should produce one recorded decision and update 690b so the coverage matrix and acceptance test agree with what is technically supported. |
| R1-S5 | Validation | medium | Expand Inc-1 tests into an external-member import-form matrix covering namespace imports, named imports, default imports, `import type`, re-exports, subpath exports, conditional exports, and package helper types. | Strategy (a) is likely sufficient for the two named RUN_009 failures, but without this matrix it may create false positives or false negatives on normal SDK usage patterns. | Inc-1 "Tests" | Each fixture should state expected SCIP occurrence behavior and whether strategy (b) direct `.d.ts` indexing is required. |
| R1-S6 | Data | medium | Define the verifier result contract now: check id, source file, owning feature, severity, evidence source, availability state, user-facing message, and remediation hint. | Normalized outputs make later CKG facts, Kaizen suggestions, and reports cheaper without committing to SQLite or OTel in Phase 1. This captures data already flowing through the verifier and avoids reworking ad hoc finding shapes later. | Section 1 module layout or Inc-4 "Unify + regression corpus" | Unit-test that every existing and new check emits the normalized contract and that postmortem output shows ran, failed, skipped-advisory, and unavailable states distinctly. |

#### Review Round R2 — composer-2.5 — 2026-06-01 19:15 UTC

- **Reviewer**: composer-2.5
- **Date**: 2026-06-01 19:15:00 UTC
- **Scope**: Second-pass (adversarial) review — implementation accuracy vs shipped code, prime/primary-contractor integration boundaries, and second-order false-PASS risks R1 did not spell out.

##### Focus Ask Responses

1. **Phase 1 under-scope**
   - **Summary answer:** Partial — endorse R1-S3; add that failure #9 in the requirements table must not be read as covering UI↔route shape (#15).
   - **Rationale:** `prisma_zod_symmetry` compares Zod objects to Prisma models; RUN_009 #9 was Zod/API field drift on a route handler, while #15 is a page type consuming a field absent from the route response. Treating both as "existing" overstates symmetry coverage.
   - **Assumptions / conditions:** None if the failure table annotates #9 vs #15 separately in acceptance docs.
   - **Suggested improvements:** Add Inc-4 corpus rows that distinguish #9 (Zod destructuring) from #15 (UI consumer type).

2. **REQ-CKG-620 route-shape feasibility**
   - **Summary answer:** Unchanged from R1 — spike-gate remains correct.
   - **Rationale:** No new evidence beyond R1; second-order risk is counting #9 as already caught.
   - **Assumptions / conditions:** Inc-3 sub-spike still gates commitment.
   - **Suggested improvements:** Endorse R1-S4.

3. **Signature (f) strategy (a)**
   - **Summary answer:** Unchanged — endorse R1-S5 import-form matrix.
   - **Rationale:** Still the right default; no new false-positive data in this pass.
   - **Assumptions / conditions:** SCIP index must be fresh (see R2-S4).
   - **Suggested improvements:** Endorse R1-S5.

4. **Integration / surface risk**
   - **Summary answer:** Yes, but extract orchestration to `validators/cross_file_verifier.py` and keep primary-contractor review out of Phase 1.
   - **Rationale:** `PrimaryContractorWorkflow._review_draft` already runs forward-manifest validation; adding SCIP per feature would stack LLM review + manifest + cross-file checks and duplicate postmortem work. Prime batch already ends with `launch_prime_postmortem_async` — that is the correct batch hook.
   - **Assumptions / conditions:** Phase 1 defers in-loop redraft on cross-file findings (quality gate uses per-feature disk score, not batch symmetry).
   - **Suggested improvements:** Document in plan Section 6 that cross-file FAIL surfaces in postmortem/Kaizen, not mid-batch primary-contractor iteration.

5. **Per-batch SCIP integration point**
   - **Summary answer:** Partial — trigger is batch postmortem, not "any installed disk state."
   - **Rationale:** Code path: `PrimeContractorWorkflow` completes the queue, then `launch_prime_postmortem_async(..., project_root=...)` runs `_evaluate_cross_file_integrity`. SCIP must run inside that window after all `generated_files` are on disk, before aggregate PASS is computed.
   - **Assumptions / conditions:** Postmortem only loads paths where `Path(project_root)/fp` `is_file()` — in-memory-only drafts are invisible to the verifier.
   - **Suggested improvements:** Endorse R1-S1 and add R2-S3 disk-flush precondition.

6. **Deferral correctness**
   - **Summary answer:** Safe with explicit user messaging when cross-file runs only at batch end.
   - **Rationale:** End users may see per-feature review PASS then batch FAIL; that is honest if reports explain timing, confusing if not.
   - **Assumptions / conditions:** Postmortem summary lists cross-file as batch gate.
   - **Suggested improvements:** Add postmortem summary section "Batch cross-file verifier."

##### Executive Summary

- Inc-2 overclaims tsconfig support: `cross_file_imports` only heuristically resolves `@/` to `("", "src")`, so REQ-CKG-630 is real parsing work, not a 0.5d extension of existing logic.
- Phase 1 should stay batch-scoped at postmortem to avoid stacking validation on the already-heavy primary/lead contractor review path.
- SCIP index staleness and disk-only source loading are concrete false-PASS paths if lifecycle ordering is wrong.
- Plan header and Inc-4 dependency lines drift from requirements v2.1 (version label, `[code-observability]` extra, `ScipFacts` naming).
- Endorse most R1 items; this round adds code-accurate corrections and module boundaries.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Validation | high | Correct Inc-2: replace "already parses alias bases" with "add tsconfig `compilerOptions.paths` resolution (honor `extends`), then assert each mapped target exists on disk." | `scan_unresolvable_imports` uses hardcoded `alias_bases=("", "src")` when tsconfig is missing; it does not read `paths` today. Planning REQ-CKG-630 as 0.5d on top of existing logic is only valid if scope includes JSON parse + extends merge. | Inc-2 bullet list | Fixture: `paths: {"@/*": ["./src/*"]}` with no `src/` dir → violation; fixture with `extends` chain → correct resolution; no false positive when alias target exists. |
| R2-S2 | Architecture | high | Add `src/startd8/validators/cross_file_verifier.py` as the orchestration module; `prime_postmortem._evaluate_cross_file_integrity` becomes a thin caller. Phase 1 explicitly does **not** invoke this module from `PrimaryContractorWorkflow` / `DefaultImplementationEngine`. | Keeps R1-S2 intent but names the extraction target and prevents accidental per-feature SCIP calls in the lead/primary loop (manifest + LLM review + batch checks). | Section 1 module layout and Inc-4 | 690a compares verdicts before/after refactor; grep test or architecture test that `implementation_engine` and `primary_contractor_workflow` do not import `scip_runner`. |
| R2-S3 | Ops | high | Add a postmortem precondition in Inc-4/Section 3: cross-file checks run only after all batch `generated_files` are flushed to `project_root` and readable; document that `_evaluate_cross_file_integrity` skips paths that are not `is_file()`. | Current postmortem builds `sources` from on-disk files only (`prime_postmortem.py` ~1689–1695). Late writes or missing flush → checks silently see an incomplete batch. | Section 3 sequencing and Inc-4 | Integration test: generated content only in memory → UNVERIFIED or explicit skip reason; after flush → findings attributed. |
| R2-S4 | Risks | medium | Specify SCIP index cache invalidation in Inc-0: key = hash(project_root, lockfile/package.json, batch file manifest); rebuild when manifest changes; run index once immediately before cross-file scans in postmortem. | Running SCIP before the last feature lands, or reusing an index from pre-batch anchors, can miss #4/#11/#15 in the generated delta. | Inc-0 `scip_runner` and Section 4 risks | Test: mutate a generated file after index → either rebuild detected or checks mark index stale/unverified. |
| R2-S5 | Ops | medium | Remove Inc-4 "Add `[code-observability]` pip extra" (requirements v2.1: no new pip extra; only Node `scip-typescript` subprocess). Document install in `docs/` + operator preflight, align plan header to requirements v2.1. | Plan header still cites "requirements v2.0"; Inc-4 contradicts Planning Insights row "Dependencies simplified." | Inc-4 last bullet and document header | Doc review + CI job without pip extra installs; optional Node-present matrix job only. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-S1: SCIP lifecycle must be named relative to batch postmortem, not vague "installed disk state."
- R1-S2: Registry/facade extraction is required before adding SCIP inline.
- R1-S3: Zod composition audit is necessary before locking 690a.
- R1-S4: Route-shape needs a written decision table before 690b claims #15.

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S6 | Security | medium | Add Inc-0 requirements for `scip_runner`: resolved `project_root` must stay under the prime workspace root, subprocess uses `cwd=project_root`, no `shell=True`, wall-clock timeout, and log tool version on failure. | SCIP is a subprocess over the target repo; without bounds, a misconfigured `project_root` or hung indexer can block batch completion or escape intended cwd. | Inc-0 and Section 4 risks | Unit tests with traversal path rejected; timeout kills hung subprocess; logs include pinned `@sourcegraph/scip-typescript` version. |

#### Review Round R3 — claude-opus-4-8 — 2026-06-01 19:30 UTC

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-01 19:30:00 UTC
- **Scope**: Third-pass, gap-hunting / interaction review. Prior rounds covered lifecycle ordering, surface extraction, and check accuracy; this round targets two second-order false-PASS holes in the *consuming* path (async postmortem + aggregate mean) that make the verifier's verdict non-load-bearing at the run level, plus their interactions with R1/R2 suggestions.

##### Focus Ask Responses

1. **Phase 1 under-scope**
   - **Summary answer:** The deeper under-scope is not check coverage but *verdict consumption* — even a perfect set of checks cannot close the inversion given the current async/aggregate path.
   - **Rationale:** `launch_prime_postmortem_async` runs the verifier in a background `threading.Thread` after `result_dict` is already returned (`prime_contractor.py` ~5230). The cross-file FAIL never re-enters the run result.
   - **Assumptions / conditions:** Confirmed by reading the launch function (`daemon=False`, not joined) and the prime run return path.
   - **Suggested improvements:** See R3-S1; treat verdict feedback as Phase 1 scope or explicitly label CKG advisory-only.

2. **REQ-CKG-620 route-shape feasibility** — No new position beyond R1-S4/R2; endorse R1-S4.

3. **Signature (f) strategy (a)** — No new position; endorse R1-S5.

4. **Integration / surface risk**
   - **Summary answer:** Endorse R1-S2/R2-S2; add that the extracted verifier's verdict must be returned to the caller, not only written to report files.
   - **Rationale:** Extraction without a synchronous return path still leaves the inversion open.
   - **Assumptions / conditions:** None.
   - **Suggested improvements:** R3-S1 + R3-S3.

5. **Per-batch SCIP integration point**
   - **Summary answer:** Endorse R1-S1/R2-S3; the named lifecycle point must be *synchronous with the run verdict*, not the current detached thread.
   - **Rationale:** Lifecycle correctness (R1-S1) and consumption correctness (R3-S1) are separate; fixing one without the other still yields false-PASS.
   - **Assumptions / conditions:** None.
   - **Suggested improvements:** R3-S1, R3-S3.

6. **Deferral correctness**
   - **Summary answer:** The most dangerous deferral is implicit: deferring *aggregate verdict semantics* lets a real cross-file FAIL average away.
   - **Rationale:** `aggregate_score = sum(disk_scores)/len`; one zeroed feature in a 13-feature batch ≈ 0.92 ≥ 0.8 PASS threshold.
   - **Assumptions / conditions:** Confirmed in `prime_postmortem.py` ~1452–1476.
   - **Suggested improvements:** R3-S2.

##### Executive Summary

- Critical: the cross-file verifier runs in a fire-and-forget background thread *after* the run reports its result — so its FAIL verdict is currently non-load-bearing and cannot close the score-vs-reality inversion at the run level. This is the single highest-value gap in the plan.
- Critical: the aggregate verdict is a mean over per-feature disk scores against a 0.8 PASS threshold; one cross-file FAIL among ~13 features still aggregates to PASS, diluting exactly the failure class CKG exists to catch.
- These two interact with R1-S1/R2-S2/R2-S3: lifecycle ordering and surface extraction are necessary but not sufficient unless the verdict is consumed synchronously and aggregated with an any-error rule.
- Determinism gap: the postmortem thread is `daemon=False` and not joined, so CI/acceptance runs can race or hang on it; 690b acceptance needs a deterministic await.
- Endorse the load-bearing R1/R2 items rather than restating them.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Risks | critical | State explicitly how the cross-file verdict reaches the user: either (a) Phase 1 makes the cross-file verifier synchronous and feeds its FAIL into the prime run result / CLI exit code, or (b) the plan declares CKG Phase 1 advisory-only and concedes it cannot satisfy "zero false-PASS" at the run level. | `launch_prime_postmortem_async` (`prime_contractor.py` ~5230, `prime_postmortem.py` ~2669) runs the verifier in a background thread after `result_dict` is returned; a FAIL verdict never gates the run. Without this, every other CKG suggestion improves a report nobody acts on. | Section 1 "Approach" and Section 6 "Rollout" | Integration test: a batch containing #4/#11 yields a non-PASS run result (exit code / returned verdict), not just a FAIL line in an async report written later. |
| R3-S2 | Validation | critical | Add an aggregate-verdict rule to Inc-4: any error-severity cross-file finding caps the batch verdict at FAIL (or at most PARTIAL), independent of the mean disk score. Do not let `aggregate_score = mean(disk_scores)` decide cross-file outcomes. | `prime_postmortem.py` ~1452–1476 averages disk scores against `_PASS_THRESHOLD = 0.8`; one zeroed feature in a 13-feature batch ≈ 0.92 → PASS. The cross-file failures are build-breaking, so mean dilution reproduces the inversion at the aggregate layer. | Inc-4 "Unify + regression corpus" and Section 5 "Test plan" | Corpus test: 12 clean features + 1 cross-file FAIL → aggregate verdict is NOT PASS. Add an explicit "single-failure dilution" fixture. |
| R3-S3 | Ops | high | Specify deterministic completion: the batch-end SCIP index + cross-file verifier must complete (be awaited/joined) before the run reports final status in CLI/CI/acceptance modes; the `daemon=False`, un-joined postmortem thread is not acceptable for a gating check. | The current thread is started and never joined; short-lived CLI invocations can exit before it finishes, and CI cannot reliably assert on its verdict. A gating verifier must be synchronous or explicitly joined. | Section 3 "Sequencing & dependencies" and Section 6 | Test: CLI run returns only after verifier completes; CI asserts verdict deterministically across 20 repeats (no race). |
| R3-S4 | Architecture | medium | Make R1-S2/R2-S2 extraction return a typed batch result (verdict + per-check availability + findings) to the caller, not only write report files; the prime run consumes that return value for its verdict. | Extraction alone (R1-S2/R2-S2) reduces complexity but does not fix consumption; a returned result object is the seam that lets R3-S1/R3-S2 work without re-reading report JSON. | Section 1 module layout (`cross_file_verifier.py`) | Unit test: verifier returns a structured result; postmortem/run path asserts on the returned verdict, not on parsed files. |
| R3-S5 | Validation | medium | Clarify REQ-CKG-690b acceptance in the plan to assert the *aggregate run verdict* (not only per-feature verdicts) is non-PASS when any of #4/#11/#5/#15 is present in a multi-feature batch. | 690b currently reads as per-feature "zero false-PASS"; the dilution and async paths mean per-feature FAIL can coexist with an aggregate/run PASS. Acceptance must pin both levels. | Inc-4 690b bullet and Section 5 | Acceptance test asserts both: offending feature FAILs AND the batch/run verdict is non-PASS. |

#### Review Round R4 — gemini-3.1-pro — 2026-06-01 19:40 UTC

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-01 19:40:00 UTC
- **Scope**: Fourth-pass review focusing on reducing adjacent accidental complexity in the `lead-contractor` (`PrimaryContractorWorkflow`) codebase and defining clear boundaries between LLM-based inner-loop reviews and batch-level deterministic CKG checks.

##### Executive Summary

- The LLM reviewer in `PrimaryContractorWorkflow` runs in an inner loop *before* the batch-level SCIP index is built. The plan must explicitly update the review prompt to stop the LLM from hallucinating cross-file or external-package compliance, preventing wasted retry loops.
- Accidental complexity in `primary_contractor_workflow.py` is high due to duplicate sync/async review parsing (`_review_draft` vs `_areview_draft`) partially delegating to `implementation_engine`. The plan should consolidate this parsing to cleanly decouple the LLM response from the CKG verifier logic.
- We must protect the SCIP indexer from being broken by mid-batch generated files that corrupt the project's build state (e.g., malformed `package.json` or `tsconfig.json`).
- Endorse R3-S1 (sync verdict) and R2-S2 (verifier extraction).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Interfaces | high | Add a step to explicitly modify `contractor_prompts.yaml` (the review template) to instruct the `PrimaryContractorWorkflow` LLM reviewer NOT to validate cross-file imports or external dependencies, deferring them to the batch postmortem. | `PrimaryContractorWorkflow` loops up to 3 times based on LLM reviews. Since SCIP indexing is strictly per-batch (NFR-2), the LLM lacks cross-file context. If it guesses wrong, it triggers expensive, futile retry loops. | Section 1 "Approach" or Inc-4 | Verify `contractor_prompts.yaml` review template explicitly defers external type/import validation. Test that a feature with a valid external import isn't rejected by the LLM guessing it's invalid. |
| R4-S2 | Architecture | medium | Consolidate the duplicate parsing logic in `primary_contractor_workflow.py` (`_review_draft` and `_areview_draft` duplicate `_parse_list_section` and `ReviewResult` mapping) fully into `implementation_engine.reviewer`. | The prompt asks to reduce adjacent accidental complexity in lead-contractor code. The workflow file currently mixes async orchestration with raw LLM string parsing, muddying the boundary between workflow state and review semantics. | Inc-4 "Unify + regression corpus" | Refactor replaces inline parsing with `implementation_engine.parsers` calls. Unit tests pass with no behavior change. |
| R4-S3 | Risks | medium | Add a pre-flight check in `scip_runner.py` (Inc-0) that validates `package.json` and `tsconfig.json` are parseable before invoking `scip-typescript`. If corrupted by the batch, gracefully downgrade to advisory. | A generated feature in the batch might inadvertently overwrite or corrupt configuration files. Since SCIP depends on the installed disk state, a corrupted config will cause `scip-typescript` to crash ungracefully. | Inc-0 "SCIP plumbing" | Test: Inject a malformed `tsconfig.json` into the batch output; SCIP runner catches the JSON error and returns `None` (advisory degrade) instead of a subprocess exception. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R3-S1: Making the verifier synchronous and gating the run is absolutely critical for the value of CKG.
- R3-S2: The aggregate mean dilution completely nullifies cross-file validation.
- R2-S2: Extracting the verifier keeps `prime_postmortem.py` from growing into a monolithic bottleneck.

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-S1: SCIP lifecycle must be named relative to batch postmortem — necessary precondition for R3-S1.
- R1-S2 / R2-S2: Verifier extraction to a typed module is the seam R3-S4 builds on.
- R2-S3: Disk-flush precondition is required before the verifier can be trusted to gate.
- R1-S6: A normalized result contract is what R3-S4's returned object should carry.

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Thesis and 16 RUN_009 failure scope | Sections 1, 2, 5 | Partial | Plan tracks the 16-failure corpus, but #10/#16 and route-shape fallback need clearer PASS versus UNVERIFIED semantics. |
| REQ-CKG-200 scip-typescript runner | Inc-0 | Partial | Runner exists in plan, but lifecycle trigger, dependency readiness, cache/index path ownership, and unavailable-state reporting are underspecified. |
| REQ-CKG-210 and collapsed REQ-CKG-220 SCIP reader/accessors | Inc-0 module layout and tests | Partial | Reader accessors are named, but the verifier result contract and provenance fields are not yet specified. |
| REQ-CKG-230 fallback | Inc-0, Section 4, Section 5 degrade test | Partial | Graceful degradation is covered, but the plan does not yet prevent unavailable SCIP checks from being misread as successful verification. |
| REQ-CKG-610 external-type-presence | Inc-1 | Partial | Basic #4/#11 cases are covered; import-form matrix and fallback triggers for direct `.d.ts` indexing are missing. |
| REQ-CKG-620 route request/response shape | Inc-3 | Partial | Spike-gate is covered; fallback outcomes and acceptance impact for #15 need a decision table. |
| REQ-CKG-630 tsconfig path-alias target existence | Inc-2 | Full | Plan has a small independent implementation and direct #5 acceptance test. |
| REQ-CKG-600 unified verifier | Section 1 wiring point and Inc-4 | Partial | Behavior preservation is covered by 690a, but the plan should add a registry/contract extraction to reduce verifier-path complexity. |
| REQ-CKG-690a regression lock | Inc-4 and Section 3 | Full | Plan explicitly lands existing-signature regression fixtures before surface edits. |
| REQ-CKG-690b new-check acceptance | Inc-4 and Section 5 | Partial | 16/16 claim depends on route-shape and deferred #10/#16 semantics; coverage should be updated after Inc-3 decision. |
| NFR-1 toolchain-free baseline | Section 5 degrade and Section 6 rollout | Full | Core toolchain-free signatures remain active when SCIP is absent. |
| NFR-2 per-batch not inner-loop | Inc-0, Section 3, Section 4 | Partial | Per-batch intent is clear; exact prime/primary contractor integration point needs naming. |
| NFR-3 clean-room dependencies | Inc-0, Section 4, Inc-4 | Full | Vendored SCIP proto, pinned Node tool, and no CodeQL artifacts are represented. |
| NFR-4 anti-deferral | Sections 2, 5, 6 | Partial | Anti-deferral is strong for #4/#11/#5; #15 and framework-mode deferrals need explicit report semantics. |

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Thesis and 16 RUN_009 failure scope | Sections 1, 2, 5 | Partial | Failure #9 (api-request-shape via Zod) is conflated with #15 (UI↔route); plan should not imply symmetry check closes both. |
| REQ-CKG-200 scip-typescript runner | Inc-0 | Partial | Runner lacks specified timeout, cache invalidation key, and subprocess cwd/safety constraints. |
| REQ-CKG-210 and collapsed REQ-CKG-220 | Inc-0 | Partial | Inc-0 exit still says `ScipFacts` though reqs collapsed the model; naming drift risks reintroducing a duplicate layer. |
| REQ-CKG-230 fallback | Inc-0, Section 4, Section 5 | Partial | Stale-index risk if SCIP runs before final disk flush is not addressed. |
| REQ-CKG-610 external-type-presence | Inc-1 | Partial | Unchanged from R1; import-form matrix still required. |
| REQ-CKG-620 route request/response shape | Inc-3 | Partial | Unchanged from R1; decision table still required. |
| REQ-CKG-630 tsconfig path-alias target existence | Inc-2 | Partial | Plan overstates "already parses alias bases"; real tsconfig `paths` parsing is still new work. |
| REQ-CKG-600 unified verifier | Section 1, Inc-4 | Partial | Needs explicit `cross_file_verifier.py` extraction and batch-only wiring (not primary-contractor review loop). |
| REQ-CKG-690a regression lock | Inc-4 | Full | Unchanged. |
| REQ-CKG-690b new-check acceptance | Inc-4, Section 5 | Partial | Disk-flush precondition for postmortem source collection not in plan. |
| NFR-1 toolchain-free baseline | Section 5 | Full | Unchanged. |
| NFR-2 per-batch not inner-loop | Inc-0, Section 3 | Partial | Prime batch completion hook (`launch_prime_postmortem_async`) should be named as SCIP trigger. |
| NFR-3 clean-room dependencies | Inc-0, Inc-4 | Partial | Inc-4 `[code-observability]` pip extra contradicts reqs §6 (Node tool only). |
| NFR-4 anti-deferral | Sections 2, 5, 6 | Partial | Per-feature quality gate uses disk score, not batch cross-file — plan should state user-visible timing of cross-file FAIL. |

## Requirements Coverage Matrix — R3

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Thesis and 16 RUN_009 failure scope | Sections 1, 2, 5 | Partial | Even full check coverage cannot close the inversion unless the verdict gates the run (R3-S1) and aggregation uses an any-error rule (R3-S2). |
| REQ-CKG-200 scip-typescript runner | Inc-0 | Partial | Runner must complete synchronously/joined before run verdict (R3-S3); current postmortem thread is detached. |
| REQ-CKG-210 / collapsed REQ-CKG-220 | Inc-0 | Partial | Result contract must be a returned typed object consumed by the run, not only report files (R3-S4). |
| REQ-CKG-230 fallback | Inc-0, Section 4, Section 5 | Partial | Availability states only help if they reach the run verdict; depends on R3-S1. |
| REQ-CKG-610 external-type-presence | Inc-1 | Partial | Unchanged; accuracy is moot if verdict is non-load-bearing (R3-S1). |
| REQ-CKG-620 route request/response shape | Inc-3 | Partial | Unchanged from R1/R2. |
| REQ-CKG-630 tsconfig path-alias target existence | Inc-2 | Partial | Unchanged from R2 (real `paths` parsing still owed). |
| REQ-CKG-600 unified verifier | Section 1, Inc-4 | Partial | Extraction should return a typed batch verdict to the caller (R3-S4), not just write files. |
| REQ-CKG-690a regression lock | Inc-4 | Full | Unchanged. |
| REQ-CKG-690b new-check acceptance | Inc-4, Section 5 | Partial | Must assert non-PASS at the aggregate/run level, not only per-feature (R3-S5). |
| NFR-1 toolchain-free baseline | Section 5 | Full | Unchanged. |
| NFR-2 per-batch not inner-loop | Inc-0, Section 3 | Partial | Batch hook named, but it is async fire-and-forget; must be made gating (R3-S1, R3-S3). |
| NFR-3 clean-room dependencies | Inc-0, Inc-4 | Partial | Unchanged from R2 (pip extra vs Node-only). |
| NFR-4 anti-deferral | Sections 2, 5, 6 | Partial | Aggregate-verdict semantics are the deferred item that reproduces the inversion (R3-S2). |

## Requirements Coverage Matrix — R4

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Thesis and 16 RUN_009 failure scope | Sections 1, 2, 5 | Partial | Unchanged from R3. |
| REQ-CKG-200 scip-typescript runner | Inc-0 | Partial | Missing safety checks for corrupted `tsconfig.json`/`package.json` that break the runner (R4-S3). |
| REQ-CKG-210 / collapsed REQ-CKG-220 | Inc-0 | Partial | Unchanged from R3. |
| REQ-CKG-230 fallback | Inc-0, Section 4, Section 5 | Partial | Unchanged from R3. |
| REQ-CKG-610 external-type-presence | Inc-1 | Partial | Unchanged from R3. |
| REQ-CKG-620 route request/response shape | Inc-3 | Partial | Unchanged from R3. |
| REQ-CKG-630 tsconfig path-alias target existence | Inc-2 | Partial | Unchanged from R3. |
| REQ-CKG-600 unified verifier | Section 1, Inc-4 | Partial | Unchanged from R3. |
| REQ-CKG-690a regression lock | Inc-4 | Full | Unchanged. |
| REQ-CKG-690b new-check acceptance | Inc-4, Section 5 | Partial | Unchanged from R3. |
| NFR-1 toolchain-free baseline | Section 5 | Full | Unchanged. |
| NFR-2 per-batch not inner-loop | Inc-0, Section 3 | Partial | LLM reviewer prompt must explicitly exclude cross-file validation to avoid inner-loop hallucination (R4-S1). |
| NFR-3 clean-room dependencies | Inc-0, Inc-4 | Partial | Unchanged from R3. |
| NFR-4 anti-deferral | Sections 2, 5, 6 | Partial | Unchanged from R3. |
