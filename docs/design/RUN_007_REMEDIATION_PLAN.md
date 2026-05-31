# RUN-007 Partial-Delivery Remediation — Implementation Plan

**Version:** 0.3 (Post-CRP — triage applied)
**Date:** 2026-05-31
**Status:** Draft (ready for implementation)
**Requirements:** `docs/design/RUN_007_REMEDIATION_REQUIREMENTS.md` (v0.3 — FR-0..FR-10)
**Source incident:** `docs/design/RUN_007_PARTIAL_DELIVERY_POSTMORTEM.md`

This plan implements the v0.3 requirements. Every FR maps to a step; every step traces to an FR. Ordered smallest-blast-radius-first; each step is independently testable. **23 plan-side CRP suggestions triaged (22 accepted, R2-S1 narrowed — see Appendix A/B).**

---

## Steps

| # | Step | FR | Files | Verify |
|---|------|----|----|--------|
| **0** | **Discovery/blocking:** pin the Node stem→CLASS synthesizer; **prove the dollar budget signal is observable at the micro-prime escalation site** (R1-S3 — if not, re-home FR-4 to orchestration); confirm `validate_disk_compliance` is Python-only AST (R1-S4); confirm the seed carries description/AC for escalation input, else refuse (R5-S4) | OQ-1/3/4, FR-4 | seed/spec construction, `prime_adapter.py`, `engine.py`, `forward_manifest_validator.py` | trace + a repro test for `lib/value-model.ts`; a budget-exhausted fixture observed at the escalation decision |
| **1** | **Positive fillability classifier** `is_fillable(element)` (NOT `kind != CLASS`): data/behaviour-bearing + registry `DEFAULT_EXPORT`/`CONSTANT` fillable; empty CLASS/STRUCT/INTERFACE/ENUM/TYPE_ALIAS not. Plus `MissingTemplateError` + shared `is_empty_stem_type_artifact()` | FR-0, FR-2, FR-5 | `micro_prime/` shared util, exceptions module | unit matrix over all `ElementKind`s; only data-bearing/registry cases fillable; refusal type imports |
| **2** | **One shared gate** in `_generate_skeletons` (folds old Step 3): empty-fillable spec + no registry → do NOT emit skeleton; **clear stale `skeleton_sources`/`element_tiers`** (R4-S1/R6-F1); set escalation flag. **Co-land with Step 4** (R5-S1) | FR-1, FR-7, FR-10 | `prime_adapter._generate_skeletons` (~1955–2069) | unit: empty spec → no skeleton + stale context cleared + escalation flag; registry match → skeleton still emitted |
| **3** | **All deterministic assembler empty-element branches** (not just Java/C#): Java `:253`, C# `:337`, **Go `:204` incl. `package main` silent-empty** (R5-S2), Python DFA `from __future__` stub (R1-S1) | FR-1 | `java/csharp/go_file_assembler.py`, `utils/file_assembler.py` | unit: each language, empty elements → no stem-type / no silent-empty file shipped |
| **4** | **Dedicated empty-spec escalation entrypoint** (NOT `_is_file_ollama_whole_eligible`, which needs stub markers — R3-S2); feed seed description/AC (R5-S4); escalate **once** (count existing primary/retry; persist flag across resume — R1-S6); on empty/stub → `try/except MissingTemplateError` (R2-S3) → `success=False` + distinct root_cause/stage; **per-target success** not `effective_file_count>0` (R4-S3) + terminal-outcome enum (R4-S4) | FR-2/3/4/9 | `micro_prime/engine.py`, `prime_adapter.py`, orchestration | unit: escalates once then refuses; resume → no re-escalate; refusal caught, batch continues; mixed-target feature → `success=False` |
| **5** | Emission boundary is **authoritative** for escalate (R1-S5); `classify_tier()` guard only if `TaskComplexitySignals` gains a fillability field (else advisory); **registry CLASS-only tie-break** "registry → never escalate" (R5-S3) | FR-7 | `complexity/classifier.py`, `complexity/signals.py` | unit: CLASS-only spec → emission boundary escalates; `next.config.mjs` + stray CLASS → registry path, not escalated |
| **6** | Disk-validator detector in **non-Python path**, reusing `NodeLanguageProfile.validate_syntax` (R4-S2/R6-F2); "empty body" incl. whitespace/comments/throw (R2-S2); **hard effect: `ast_valid=False`/`contract_compliance=0.0` + FAIL**, not stub counting (R3-S3); false-positive matrix **before** hard-fail incl. `.d.ts`/`.tsx`/marker/enum/config (R3-S5) | FR-5/6 | `forward_manifest_validator.py` | unit: empty stem-type → FAIL + score ≤ ceiling; barrel/index/`.d.ts`/marker/enum/config → pass |
| **7** | Regression: **real-content-OR-structured-refusal** for all shapes (R5-S2 Go main; mixed-success; stale-context; provider/budget matrix R3-S4); **detector-regression lock** — 9 shapes fed directly to `validate_disk_compliance` assert FAIL independent of generation side (R5-S5) | FR-8 | tests | all 9 `.ts` shapes + Go main + provider/budget cases → never a stub/silent-empty; direct-to-validator FAIL ×9 |

**Sequencing note (revised — R5-S1 co-landing constraint):** Step 1 first (predicate + error type). **Steps 2 and 4 MUST co-land** (or Step 4 first): suppressing skeleton emission (Step 2) before the empty-spec escalation entrypoint (Step 4) exists opens a **silent-bypass window** — `_is_file_ollama_whole_eligible` requires stub markers a suppressed empty class lacks, so file-whole is skipped and the feature bypasses both fix branches. Then Step 3 (all assemblers), Step 5 (classifier authority), Step 6 (detector), Step 7 (regression). Fix 3 (single ledger) remains deferred.

**Open questions gating code (Step 0):** OQ-3 (budget reach — likely NO per R1-S3) and OQ-4 (validator parse reuse — NO per R1-S4) plus the escalation-input-context check (R5-S4) are resolved in Step 0 before Steps 1–7.

---

## Appendix A — Accepted Suggestions

> Triaged 2026-05-31 (v0.3). Round history preserved in Appendix C (cross-model memory — do not strip).

| ID | Disposition | Merged into |
|----|-------------|-------------|
| R1-S1 | ACCEPTED | Step 3 (all assembler empty branches incl. Go + Python DFA) |
| R1-S2 | ACCEPTED | Step 2 (one shared gate; folds old Step 3) |
| R1-S3 | ACCEPTED | Step 0 (prove budget reaches escalation site) |
| R1-S4 | ACCEPTED | Step 6 (non-Python detector net-new) |
| R1-S5 | ACCEPTED | Step 5 (emission boundary authoritative) |
| R1-S6 | ACCEPTED | Step 4 (partial-fill predicate + checkpoint/resume idempotency) |
| R2-S2 | ACCEPTED | Step 6 ("empty body" incl. whitespace/comments/throw) |
| R2-S3 | ACCEPTED | Step 4 (try/except MissingTemplateError; batch continues) |
| R3-S1 | ACCEPTED | Step 1 (positive fillability classifier) |
| R3-S2 | ACCEPTED | Step 4 (dedicated empty-spec entrypoint; primary/retry accounting) |
| R3-S3 | ACCEPTED | Step 6 (hard FAIL + score cap) |
| R3-S4 | ACCEPTED | Steps 4/7 (no-provider/budget matrix) |
| R3-S5 | ACCEPTED | Step 6 (`.d.ts`/`.tsx` split; FP matrix before hard-fail) |
| R4-S1 | ACCEPTED | Step 2 (clear stale context) |
| R4-S2 | ACCEPTED | Step 6 (reuse `NodeLanguageProfile.validate_syntax`) |
| R4-S3 | ACCEPTED | Step 4 (per-target success, not `effective_file_count>0`) |
| R4-S4 | ACCEPTED | Step 4 (terminal-outcome enum) |
| R5-S1 | ACCEPTED (critical) | Sequencing note (Step 2↔4 co-landing constraint) |
| R5-S2 | ACCEPTED | Steps 3/7 (Go `package main` silent-empty shape) |
| R5-S3 | ACCEPTED | Step 5 (registry CLASS-only tie-break) |
| R5-S4 | ACCEPTED | Steps 0/4 (escalation input contract — seed desc/AC) |
| R5-S5 | ACCEPTED | Step 7 (detector-regression lock) |

## Appendix B — Rejected / Narrowed Suggestions (with rationale)

| ID | Disposition | Rationale |
|----|-------------|-----------|
| R2-S1 | **NARROWED** | Proposed removing the `AND no FRAMEWORK_CONFIG_DEFAULTS match` clause from Steps 2/5, relying purely on `implementable_elements_count == 0`. Refuted by R5-S3 (`apply_framework_defaults` collision rule leaves CLASS-only registry paths that pure fillability would mis-escalate). R3-S1/R4-S1 also narrowed it. **Resolution:** keep the registry clause as an explicit "registry → never escalate" tie-break (Step 5); the positive fillability classifier (Step 1) handles the rest. |

## Appendix C — Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-05-31

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-05-31 17:20:00 UTC
- **Scope**: Robustness, end-user value, and accidental-complexity reduction in the lead-contractor / micro-prime emission path. Suggestions grounded in reads of `prime_adapter._generate_skeletons`, the four deterministic assemblers, `complexity/classifier.py`, `micro_prime/engine.py`, and `forward_manifest_validator.py`.

**Executive summary (top risks / opportunities):**

- **FR-1 "three sites" is incomplete by construction.** `go_file_assembler.py:201-204` emits `type <Stem> struct {}` on empty elements (a 4th emitter); the Python `DeterministicFileAssembler` ships a `from __future__`-only stub (a 5th shape). Patching Java/C# leaves the same defect reachable via Go/Python — the failure will recur under a different file extension.
- **Accidental complexity:** the ship-unfilled-skeleton decision is *distributed across 5 assembler implementations*, each with its own divergent empty-elements branch (Go gates on `package != "main"` and `not type_elements and not func_elements`; Java/C# gate on `not type_elements` only). One shared gate in `_generate_skeletons` would collapse this and prevent drift.
- **OQ-3 is likely "no":** `micro_prime/engine.py` only carries a *recursion* budget (`policy.check_budget`) and a *token* budget; `prime_adapter` only *accumulates* `element_escalation_cost` after the fact. No dollar cost-cap appears to reach the escalation decision — FR-4 may be unenforceable at this site as written.
- **OQ-4 is "no" for the run-007 shapes:** `validate_disk_compliance` returns `_validate_non_python_file` for any non-`.py` suffix and only AST-parses Python. The run-007 stubs are `.ts`. FR-5's "reuse existing parse / language-agnostic" cannot reuse the Python AST path.
- **FR-7 dual-boundary authority hazard:** the SIMPLE label that produced run-007 came from the `_generate_skeletons` stamp (line ~2064), not `classify_tier()`. `classify_tier` consumes `TaskComplexitySignals`, which carries no element-kind field — FR-7(a)'s guard may have nothing to key on at that boundary.
- **Idempotency gap:** escalate-once (FR-3) is stated per-feature but the plan does not say the "already escalated" flag must survive checkpoint/resume; a resumed run could re-escalate.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Step 3 must also remove/redirect the **Go** empty-struct emit at `go_file_assembler.py:201-204` (`type <Stem> struct {}` when `package != "main"`), and explicitly audit the Python `DeterministicFileAssembler` empty case (`from __future__`-only file). Rename the step from "Java/C# assembler" to "all deterministic assembler empty-element branches." | The fix as scoped leaves Go and Python able to ship the same unfilled skeleton under a different extension; run-007 happened to be `.ts` but the defect is language-wide. | Step 3 (`# 3` row) + Files column | unit: Go file-spec with empty elements → no `type <Stem> struct {}` written; Python empty spec → no `from __future__`-only file shipped as final |
| R1-S2 | Architecture | high | Introduce **one** shared gate in `prime_adapter._generate_skeletons` (before the per-suffix dispatch) that decides *whether a deterministic skeleton may be emitted at all* — `has_implementable_elements(spec) or registry_match`. Have every assembler branch consult it instead of each re-deriving an empty-elements default. Fold Steps 2+3 into this single decision. | Removes ~5 divergent empty-branches (accidental complexity) and makes FR-1 enforced by construction at one chokepoint rather than N patch sites that will drift as languages are added. High effort-to-value: the gate is ~10 lines and deletes scattered branches. | New row between Steps 2 and 3; reference from Step 1 shared predicate | unit: every language with empty spec + no registry → no skeleton path taken; registry match → skeleton still emitted |
| R1-S3 | Risks | critical | Step 0 must add an explicit sub-task: **prove the dollar cost budget reaches the micro-prime escalation decision** (not just orchestration). Grep confirms `engine.py` only has `policy.check_budget` (recursion depth) + `input_token_budget`; `prime_adapter` only *records* `element_escalation_cost`. If the cap is orchestration-only, FR-4 must be re-homed there (refuse before dispatching micro-prime) rather than inside the escalation site. | FR-4 ("refuse if budget exhausted, never stub") is unimplementable if the escalation site cannot read remaining budget. This blocks Step 4. | Step 0 Verify column (add: "confirm a `remaining_budget`/`can_afford(est_cost)` signal exists at the escalation site or relocate FR-4") | unit/integration: a budget-exhausted fixture reaches the escalation decision and observes the cap; assert refusal, not stub |
| R1-S4 | Validation | high | Step 6 must account for `validate_disk_compliance` being **Python-only** (`suffix != ".py" → _validate_non_python_file`, AST-parse is Python-only). The empty-stub detector for the run-007 `.ts` shapes lives in the *non-Python* branch and needs a light per-language structural check; OQ-4's "reuse the existing parse" is false for TS/Go. Schedule the per-language structural check as explicit work, not reuse. | The plan implies FR-5 reuses an existing parse; for the actual stub language (TS) no such parse exists. Underestimating this risks Step 6 shipping a Python-only detector that never fires on the regression shapes. | Step 6 Files/Verify columns | unit: `.ts` stub (`export class X {}`) → flagged via `_validate_non_python_file`; Python AST path unchanged |
| R1-S5 | Interfaces | high | Resolve Step 5 vs Step 2 **authority**: make the `_generate_skeletons` emission boundary (Step 2) authoritative for the empty-spec→escalate decision, and document that `classify_tier()` (Step 5) cannot independently enforce FR-7(a) unless `TaskComplexitySignals` is extended with an element-kind/implementable signal. Verify the feature even *reaches* `classify_tier` (skeleton emission may short-circuit it). | The run-007 SIMPLE label came from the line ~2064 stamp, not the classifier. Guarding `classify_tier` without threading element-kind data is a no-op; two boundaries disagreeing is the ordering hazard the focus file flags. | Step 5 row + Sequencing note | unit: CLASS-only spec — assert which boundary emits the escalation flag; assert classifier guard only fires when signals carry the new field |
| R1-S6 | Risks | medium | Step 4 must (a) define "still empty/stub after escalation" with a **deterministic, cross-language** predicate (Python can reuse `utils.ast_checks.is_stub_only_body`; TS/Go need an explicit equivalent) including the **partial-fill** case (real content + residual stub → treat as filled or refuse — pick one and test it); and (b) require the escalate-once flag to **persist across checkpoint/resume** so a resumed run does not re-escalate. | FR-2/FR-3 termination is only airtight if "stub" is decidable for the stub languages and the once-flag survives crash recovery. Both are currently unstated. | Step 4 Verify column + Sequencing note | unit: partial-fill result → deterministic verdict; resume-after-escalation fixture → no second escalation |

## Requirements Coverage Matrix — R1

| Requirement / OQ | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled stem-class shipped, language-wide) | Steps 2, 3 | Partial | Go (`go_file_assembler.py:201`) and Python DFA empty branches uncovered; "three sites" undercounts (R1-S1, R1-S2) |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | "empty/stub after escalation" + partial-fill verdict undefined; cross-language stub predicate missing (R1-S6) |
| FR-3 (escalation terminates, no loop) | Step 4 | Partial | Idempotency across checkpoint/resume not specified (R1-S6) |
| FR-4 (cost-budget → refuse not stub) | Steps 0, 4 | Gap | Budget signal not confirmed at micro-prime escalation site; may be orchestration-only (R1-S3, OQ-3 open) |
| FR-5 (disk-validator empty-stub detector) | Step 6 | Partial | Validator is Python-only; non-`.py` detector + per-language parse is net-new, not reuse (R1-S4, OQ-4 open) |
| FR-6 (no false-flag on minimal files) | Step 6 | Partial | Plan lists barrel/index/marker; focus adds `.d.ts`, empty enum, config-object module — not yet enumerated |
| FR-7 (SIMPLE requires spec/registry, dual-boundary) | Steps 2, 5 | Partial | Authority/ordering unresolved; classifier boundary may lack the signal to enforce (R1-S5) |
| FR-8 (regression repro of 9 shapes) | Step 7 | Covered | Sound as written; extend to assert Go/Python shapes too once R1-S1 lands |
| OQ-3 (budget reach) | Step 0 | Gap | Open; gates FR-4 (R1-S3) |
| OQ-4 (validator parse reuse) | Step 0 | Gap | Open; reuse contradicted for TS/Go (R1-S4) |

#### Review Round R2 — gemini-3-1-pro — 2026-05-31

- **Reviewer**: gemini-3-1-pro
- **Date**: 2026-05-31 17:35:00 UTC
- **Scope**: Accidental complexity reduction, edge-case robustness, and control flow safety.

**Executive summary (top risks / opportunities):**

- **Redundant registry check (accidental complexity):** `forward_manifest_extractor.py` already populates `DEFAULT_EXPORT` or `CONSTANT` elements for `FRAMEWORK_CONFIG_DEFAULTS` matches. Because these are not `CLASS` elements, `implementable_elements` is naturally non-empty for registry matches. The `AND no registry match` clause in FR-2/FR-7 is logically redundant and creates a false dependency that makes FR-7(a) hard to implement.
- **LLM evasion of the empty-stub detector:** A naive structural check for "empty body" will false-negative if the LLM outputs a stub containing only comments (e.g., `export class ValueModel { // TODO }`).
- **Uncaught refusal exception:** If `MissingTemplateError` is raised during escalation, it will crash the `prime_adapter.generate` loop unless explicitly caught.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Remove the `AND no FRAMEWORK_CONFIG_DEFAULTS match` condition from the guards in Steps 2 and 5. Rely purely on `implementable_elements_count == 0`. | `apply_framework_defaults()` mutates the spec to add non-CLASS elements for registry matches. Thus, registry matches already have `implementable_elements_count > 0`. Removing the redundant check simplifies the code and severs an unnecessary dependency in `classify_tier`. | Steps 2 and 5 | unit: registry match fixture -> `implementable_elements_count > 0` -> does not trigger empty-spec guard. |
| R2-S2 | Validation | high | Step 6's non-Python structural check must explicitly define "empty body" to include bodies containing only whitespace, comments (e.g., `// TODO`), or basic throw statements. | LLMs frequently emit stubs with comments or `throw new Error()`. If the detector only looks for strictly empty braces `{}`, it will be trivially bypassed. | Step 6 | unit: `export class X { // TODO }` is flagged as a stub by the detector. |
| R2-S3 | Risks | high | Step 4 must explicitly add a `try/except MissingTemplateError` block in `prime_adapter.py` (or the orchestrator) to catch the refusal and yield a `GenerationResult(success=False, error=...)`. | Without an explicit catch, the new exception will bubble up and crash the entire `PrimeContractor` batch, turning a single-file refusal into a pipeline failure. | Step 4 | unit: `MissingTemplateError` raised -> batch continues, file marked `success=False`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Agree Go/Python need explicit coverage to prevent the defect migrating.
- R1-S2: Agree a single gate in `_generate_skeletons` is much better than N divergent assembler branches.
- R1-S3: Agree budget signal visibility at the escalation site is a blocking unknown.
- R1-S4: Agree `validate_disk_compliance` is Python-only and needs a non-Python path.
- R1-S5: Agree `classify_tier` lacks the signal to enforce FR-7(a).
- R1-S6: Agree partial-fill and checkpoint/resume idempotency must be defined.

#### Review Round R3 — gpt-5.5 — 2026-05-31

- **Reviewer**: gpt-5.5
- **Date**: 2026-05-31 17:45:00 UTC
- **Scope**: New-agent, code-grounded plan pass. Focus: implementation sequencing and hidden control-flow paths that can still turn "do not write a stub" into bypass/skip, weak scoring, or a second file-whole attempt.

**Executive summary (top risks / opportunities):**

- Step 1's `_implementable_elements(spec)` should not copy `engine.py:1336` literally. `kind != CLASS` is a negative predicate that treats empty `STRUCT`, `INTERFACE`, `ENUM`, and `TYPE_ALIAS` elements as implementable; Step 1 should create a positive, shared fillability classifier.
- Step 4 cannot rely on the existing file-whole path as-is. `_is_file_ollama_whole_eligible` requires stub markers in the skeleton, and a clean empty stem class has none; a dedicated empty-spec escalation/refusal path is needed before the normal file-whole eligibility gate.
- Step 6 must change scoring semantics, not just count stubs. `compute_disk_quality_score` only gives one stub a tiny penalty; FR-5's empty-stem detector needs a hard FAIL and score floor/ceiling.
- Preventing skeleton emission may move files into bypass/fallback paths. The plan should assert that no-fallback, fallback-disabled, and budget-boundary cases produce structured refusals, not silent skips.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Step 1 should implement `_implementable_elements(spec)` as a **positive fillability classifier**, not `kind != CLASS`: count executable/data-bearing elements and registry defaults, but treat empty structural declarations (`CLASS`, `STRUCT`, empty `INTERFACE`, empty `ENUM`, `TYPE_ALIAS`) as non-fillable unless they contain members/values. | The plan anchors Step 1 to FR-1/OQ-5, but the quoted predicate is language-biased. `ElementKind` includes structural kinds beyond `CLASS`; carrying the negative test into the shared gate preserves a hole for empty Go structs and creates false complexity around marker interfaces. | Step 1 row + Step 5 row | Unit matrix over CLASS/STRUCT/INTERFACE/ENUM/TYPE_ALIAS/DEFAULT_EXPORT; only data-bearing or registry-derived cases bypass escalation |
| R3-S2 | Risks | high | Step 4 should add a dedicated **empty-spec escalation/refusal entrypoint** before normal file-whole eligibility, and explicitly state whether existing `file_whole_primary` / `file_whole_escalation_retry` attempts count against the "exactly once" budget. Do not depend on `_is_file_ollama_whole_eligible`, because it skips file-whole when the skeleton has no stub markers. | The run-007 artifact (`export class <stem> {}`) can be syntactically valid and marker-free. Existing file-whole routing checks `_skeleton_has_stubs` first; without a separate entrypoint, the empty-spec path may never reach escalation, or may use both primary and retry paths and violate FR-3. | Step 4 Verify column + Sequencing note | Test: marker-free empty class triggers the empty-spec entrypoint exactly once; existing primary/retry attempts are counted or disabled per the documented rule |
| R3-S3 | Validation | high | Step 6 must include a score/verdict implementation task: when the empty-stem detector matches, force FAIL and cap `disk_quality_score` at a documented low ceiling (or set `contract_compliance=0`/`ast_valid=False`), rather than only incrementing `stubs_remaining`. | In `compute_disk_quality_score`, one stub reduces only the 0.2-weighted stub component; a single empty class can remain near-perfect. FR-5 says it must drive disk quality low and FAIL, so Step 6 needs explicit scoring work. | Step 6 Verify column | Unit: empty stem class produces FAIL and score <= ceiling; barrel/index/marker/config fixtures keep normal scores |
| R3-S4 | Ops | medium | Add a Step-4/Step-7 regression matrix for **no escalation provider** states: fallback unavailable, escalation disabled, Ollama unavailable, and budget would exceed cap. Each must produce structured refusal metadata (`success=False`, root_cause/stage) and write no skeleton. | The current plan tests "budget-exhausted → refuse" but not provider impossibility. In code, no-skeleton/non-Python paths can fall into bypass/fallback handling; if fallback is absent they may be skipped without the explicit `MissingTemplateError` signal the user needs. | Step 4 Verify column + Step 7 row | Four-case matrix asserts no file written and refusal appears in `prime-result.json` history |
| R3-S5 | Validation | medium | Step 6 should explicitly split TypeScript source validation from `.d.ts` ambient declarations and `.tsx` syntax. The detector can be text/structural, but the false-positive matrix must include `.d.ts` and `interface`/`enum` cases before applying a hard FAIL. | `Path.suffix` treats `foo.d.ts` as `.ts`; a JS `node --check` style path can false-fail ambient declarations. Because R3-S3 makes the detector hard-fail, the exemption/fixture matrix must land before the score floor. | Step 6 Files/Verify columns | Fixtures: `.d.ts` ambient interface, empty enum allowed/denied per requirement, config-object module, `export *` barrel, exact empty stem class |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R1-S2: The shared gate is the right simplification; R3-S1 tightens what the gate should compute.
- R1-S6: Partial-fill/idempotency must be defined; R3-S2 adds existing file-whole primary/retry accounting.
- R2-S3: Catching `MissingTemplateError` is required; R3-S4 extends it to no-provider and budget-boundary paths.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):

- R2-S1: Narrow, not reject. Removing the registry-match clause is safe only after Step 1 proves framework defaults add positive fillable elements; otherwise it can accidentally escalate legitimate $0.00 config files.

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled stem-class shipped) | Steps 2, 3 | Partial | R1-S1, R1-S2 |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | R1-S6, R2-S3 (uncaught exception risk), R2-S1 (redundant registry check) |
| FR-3 (escalation terminates) | Step 4 | Partial | R1-S6 |
| FR-4 (cost-budget) | Steps 0, 4 | Gap | R1-S3 |
| FR-5 (disk-validator empty-stub detector) | Step 6 | Partial | R1-S4, R2-S2 (LLM evasion via comments) |
| FR-6 (no false-flag on minimal files) | Step 6 | Partial | R1-S4 |
| FR-7 (SIMPLE requires spec/registry) | Steps 2, 5 | Partial | R1-S5, R2-S1 (redundant registry check) |
| FR-8 (regression repro) | Step 7 | Covered | — |
| OQ-3 (budget reach) | Step 0 | Gap | R1-S3 |
| OQ-4 (validator parse reuse) | Step 0 | Gap | R1-S4 |

## Requirements Coverage Matrix — R3

| Requirement / OQ | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled skeleton shipped, language-wide) | Steps 1, 2, 3 | Partial | Shared predicate still negative (`kind != CLASS`); must handle STRUCT/INTERFACE/ENUM/TYPE_ALIAS and registry defaults (R3-S1/R3-F1) |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | Existing file-whole eligibility requires stub markers; marker-free empty class needs dedicated entrypoint and shared post-escalation detector (R3-S2/R3-F3) |
| FR-3 (termination/no loop) | Step 4 | Partial | Plan does not say whether existing primary/retry file-whole attempts count toward "exactly once" (R3-S2) |
| FR-4 (budget/provider refusal) | Steps 0, 4 | Partial | Budget reach covered by R1; exact cap boundary and provider-unavailable/refusal behavior still missing (R3-S4/R3-F4) |
| FR-5 (disk-validator empty-stub detector) | Step 6 | Partial | Detector must hard-fail/cap score, not just increment ordinary stub count (R3-S3/R3-F2) |
| FR-6 (minimal-file false positives) | Step 6 | Partial | `.d.ts`, `.tsx`, marker interface/enum/config fixtures must land before hard-fail scoring (R3-S5) |
| FR-7 (SIMPLE requires spec/registry) | Steps 2, 5 | Partial | Guard needs positive fillability signal shared by emission and classifier boundaries (R3-S1/R3-F1) |
| FR-8 (run-007 regression) | Step 7 | Partial | Needs no-provider/budget-boundary and post-escalation-empty-class cases, not only initial `.ts` stub reproduction (R3-S4) |

#### Review Round R4 — gpt-5.5 — 2026-05-31

- **Reviewer**: gpt-5.5
- **Date**: 2026-05-31 17:55:00 UTC
- **Scope**: New-agent pass after R1-R3. Focus: stale context, success accounting, and duplicated JS/TS validation paths that can preserve accidental complexity or still report user-visible success when a target file was skipped/refused.

**Executive summary (top risks / opportunities):**

- `_generate_skeletons` mutates `context["skeleton_sources"]` and `context["element_tiers"]`; a new "do not emit skeleton" decision must also clear stale entries for that file, or retry/resume can preserve the old `tier:SIMPLE` skeleton-fill path.
- `forward_manifest_validator._validate_js_file` duplicates JS/TS syntax validation instead of using `NodeLanguageProfile.validate_syntax`; it writes all JS/TS/TSX content to a `.js` temp file and hardcodes `_count_stubs_text(content, ".js")`, bypassing the richer TypeScript/TSX logic already present in `languages/nodejs.py`.
- `MicroPrimeCodeGenerator.generate` returns `success=st.effective_file_count > 0`; that can still mark a feature successful when only some target files were written and one empty-spec target was skipped/refused.
- The remediation should prefer a shared "per-target terminal outcome" contract over more ad hoc branches: generated, delegated, refused, skipped. That gives the end user a clear answer for every requested file without waiting for deferred Fix 3.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Risks | high | Step 2 must explicitly clear stale `context["skeleton_sources"][file_path]` and `context["element_tiers"][file_path]` when the empty-spec gate decides "do not emit; escalate/refuse." Add this before returning from `_generate_skeletons`, not only when adding new skeletons. | `_generate_skeletons` mutates context in place and only updates tiers for files in `skeletons`. On retry/resume, or when a caller passes pre-populated context, a stale skeleton source and `tier:SIMPLE` marker can survive even though the new guard skipped emission. That would preserve the exact skeleton-fill path the fix is trying to close. | Step 2 Verify column | Unit: pre-seed context with `skeleton_sources[file]` and `element_tiers[file] = {"tier":"SIMPLE"}`; empty-spec gate fires; assert both entries are removed and no skeleton is written |
| R4-S2 | Validation | high | Step 6 should replace the JS/TS syntax/stub duplicate in `forward_manifest_validator._validate_js_file` with the existing `NodeLanguageProfile.validate_syntax(code, filename_hint=file_path)` and pass the real suffix to stub counting. | The disk validator currently writes `.ts`/`.tsx` content to a `.js` temp file for `node --check` and calls `_count_stubs_text(content, ".js")`. The Node language profile already has TypeScript/TSX-aware `tsc --noEmit` validation. Reusing it removes duplicated validator logic and reduces false positives/false negatives around TypeScript syntax. | Step 6 Files/Verify columns | Unit: `.ts` type annotation and `.tsx` JSX fixture validate through the Node profile; `.js` still uses `node --check`; stub counting uses the actual file extension |
| R4-S3 | Ops | high | Step 4/7 should assert feature success is **per-target complete**, not `effective_file_count > 0`: if any target file is refused, skipped, fallback-disabled, or unresolved, the returned `GenerationResult.success` is false even if other files were generated. | The current `generate()` success expression can report success when at least one file was written. That recreates the user-visible failure mode in smaller form: a batch/feature appears successful while one target silently did not materialize or was refused. This is not full Fix 3 ledger work; it is the local success invariant needed for `MissingTemplateError` to matter. | Step 4 Verify column and Step 7 regression row | Unit: two-target feature where one file generates and one empty-spec file refuses -> `success=False`, generated file retained, refusal metadata present |
| R4-S4 | Interfaces | medium | Add a tiny per-target outcome enum or dict in `prime_adapter` for this path (`generated`, `delegated`, `refused`, `skipped`) and include it in metadata/history for the run-007 regression. | This reduces adjacent accidental complexity by replacing branch-specific logging with one explicit terminal state per file. It also gives the end user a clear explanation of what happened without pulling the larger single-ledger Fix 3 into scope. | Step 4 or new Step 4a | Unit: output metadata contains one terminal outcome for each requested target file; no target has both `generated` and `refused` |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S2: The shared gate is still the central simplification; R4-S1 adds the context cleanup needed for retries.
- R3-S4: Provider/budget impossibility must produce a structured refusal; R4-S3 makes that refusal affect feature success.
- R3-S5: TS/TSX false-positive handling matters; R4-S2 points to the existing Node profile as the lower-complexity implementation path.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):
- R2-S1: Narrow. Removing the registry clause should be paired with R3-S1/R4-S1; otherwise stale context or misclassified structural kinds can still blur registry-backed skeletons and empty-spec refusals.

## Requirements Coverage Matrix — R4

| Requirement / OQ | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled skeleton shipped, language-wide) | Steps 1, 2, 3 | Partial | R1/R3 cover emitter/fillability; R4-S1 adds stale context cleanup so skipped skeletons do not remain active |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | R4-S3/R4-S4 require refusal to affect local success and per-target metadata |
| FR-3 (termination/no loop) | Step 4 | Partial | R1/R3 cover once semantics; R4-S1 covers stale retry context that could re-enable skeleton-fill |
| FR-4 (budget/provider refusal) | Steps 0, 4 | Partial | R3 covers provider/budget impossibility; R4-S3 ensures any refusal makes the feature unsuccessful |
| FR-5 (disk-validator empty-stub detector) | Step 6 | Partial | R3 covers scoring; R4-S2 reduces JS/TS validator duplication and fixes TS/TSX syntax/stub routing |
| FR-6 (minimal-file false positives) | Step 6 | Partial | R4-S2 adds TypeScript/TSX-aware validation before hard-fail detector rollout |
| FR-7 (SIMPLE requires spec/registry) | Steps 2, 5 | Partial | R3 covers fillability; R4-S1 clears stale `tier:SIMPLE` markers |
| FR-8 (run-007 regression) | Step 7 | Partial | Needs mixed-success, stale-context, and TS/TSX disk-validation fixtures (R4-S1/R4-S2/R4-S3) |

#### Review Round R5 — claude-opus-4-8-1m — 2026-05-31

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-05-31 18:15:00 UTC
- **Scope**: Fifth plan pass (renumbered from a concurrent R4 to preserve round monotonicity — a parallel gpt-5.5 R4 landed simultaneously). R1–R4 already covered: shared gate (R1-S2), Go/Python emitter breadth (R1-S1), budget reach (R1-S3), Python-only validator + JS/TS dedup (R1-S4/R4-S2), classifier authority (R1-S5), partial-fill/idempotency (R1-S6), positive fillability (R3-S1), empty-spec escalation entrypoint + `_is_file_ollama_whole_eligible` marker gate (R3-S2), hard-fail scoring (R3-S3), provider-impossibility matrix (R3-S4), `.d.ts`/`.tsx` split (R3-S5), stale-context cleanup (R4-S1), per-target success accounting (R4-S3), terminal-outcome enum (R4-S4). I endorse those and add only uncovered sequencing/edge findings.

**Executive summary (new only):**

- **Step 2 ↔ Step 4 ordering hazard (compounds R3-S2):** Step 2 suppresses skeleton emission for empty specs; `_is_file_ollama_whole_eligible` gates file-whole on the skeleton *having stub markers*. With no skeleton written (Step 2) and a marker-free empty class, the eligibility gate sees nothing to fill → file-whole is skipped → the feature silently bypasses both fix branches. The "land 1–5 then 6 then 7" note doesn't capture that Step 2 and Step 4 must land together (or Step 4 first), else the intermediate state opens a silent bypass.
- **Go `package == "main"` second failure mode (uncovered):** Step 3 removes the non-main Go struct emit, but `package main` empty specs already emit nothing — they ship effectively empty (validator `empty_file`). Step 7's repro must include this shape, else the Go fix passes while a silent-empty Go main file still ships.
- **Registry CLASS-only collision (uncovered):** Step 1/Step 5's fillability predicate must carve out registry-matched paths that the `apply_framework_defaults` collision rule left CLASS-only, or it will wrongly escalate a legitimate $0.00 config file.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Risks | critical | Add an explicit **Step 2↔Step 4 co-landing constraint** to the Sequencing note: suppressing skeleton emission (Step 2) before the empty-spec escalation entrypoint (Step 4 / R3-S2) exists opens a silent-bypass window — `_is_file_ollama_whole_eligible` requires stub markers in the skeleton, and a suppressed/marker-free empty class produces none, so file-whole is skipped. Land Step 2 and Step 4 atomically (or Step 4 first). | The plan's "land 1–5, then 6, then 7" ordering implicitly allows Step 2 before Step 4; that intermediate state ships features that are neither skeleton-emitted nor escalated. | Sequencing note + Step 2/Step 4 rows | Integration: with only Steps 1–3 landed, an empty-spec feature must NOT silently bypass (assert refusal or escalation, never a no-op skip) |
| R5-S2 | Validation | high | Step 3 + Step 7 must cover the **Go `package == "main"` shape**: `go_file_assembler.py:202-204` emits no struct for `package main`, so an empty-spec main file ships effectively empty (validator `empty_file`, `:782`), a different defect than the stem-struct. Removing only the non-main emit leaves this path. | The Go fix as scoped (remove `type <Stem> struct {}`) does nothing for `package main`, which already emits nothing yet still ships as a success. | Step 3 Files + Step 7 row | unit: Go `package main`, empty elements → structured refusal, not a silently-empty file marked success |
| R5-S3 | Architecture | high | Step 1/Step 5 fillability predicate must include a **registry CLASS-only tie-break**: `apply_framework_defaults` only fills paths whose element list is EMPTY ("non-empty plan-declared list wins"), so a registry path that also has a plan-declared CLASS element stays CLASS-only and would be wrongly escalated by the pure positive-fillability classifier (R3-S1). Add "registry-matched path → never escalate" as an override. | R3-S1/R2-S1 assume registry files always carry a non-CLASS default; the collision rule is the exception that re-breaks the $0.00 path. | Step 1 row + Step 5 row | unit: `next.config.mjs` with a stray plan-declared CLASS element → registry path, not escalated |
| R5-S4 | Interfaces | medium | Step 4 must specify the **escalation input contract**: file-whole receives the seed feature description / acceptance criteria, not the empty zero-implementable-element spec. Add a Step-0 sub-task to confirm the seed carries enough context to make escalation non-vacuous; if it doesn't, the correct outcome is immediate refusal (under-specified seed), recorded as such. | If file-whole is fed the same empty spec, it regenerates an empty result and refuses — escalation becomes theater that adds cost/latency and hides an under-specified seed. | Step 4 row + Step 0 Verify | unit: escalation prompt for an empty-spec feature contains the feature description/AC (non-empty); empty-context escalation rejected at construction |
| R5-S5 | Validation | medium | Step 7 must add a **detector-regression lock**: feed each of the 9 run-007 shapes directly to `validate_disk_compliance` and assert FAIL/score-below-ceiling, independent of the generation-side escalate/refuse assertions. | Step 7 currently locks only the by-construction fix; a later refactor could silence the FR-5 detector with no test catching it, re-blinding the verdict if the by-construction fix ever regresses. | Step 7 row | unit: 9 shapes → validator FAIL for all 9 (detection side asserted separately from generation side) |

**Endorsements** (R5 reviewer agrees with these untriaged prior items):
- R1-S2 / R3-S1: shared gate + positive fillability classifier — the right architecture (with the R5-S3 collision caveat).
- R3-S2: the empty class is marker-free so `_is_file_ollama_whole_eligible` skips it — verified concern; my R5-S1 elevates the resulting Step 2↔4 ordering hazard to a co-landing constraint.
- R3-S3 / R1-S4 / R4-S2: hard-fail scoring + non-Python validator path via the Node profile — confirmed in source (empty `{}` body has zero stub markers, so `stub_penalty` stays 1.0 and the file scores ~0.94, the exact run-007 number).
- R1-S3 / R3-S4 / R4-S3: budget reach + provider-impossibility refusal + per-target success accounting.
- R1-S5 / R1-S6 / R4-S1: classifier authority + partial-fill/checkpoint idempotency + stale-context cleanup.

**Disagreements** (untriaged):
- R2-S1: narrow, do not fully remove the registry clause — see R5-S3 (the `apply_framework_defaults` collision rule leaves a CLASS-only-registry case that pure fillability would mis-escalate).

## Requirements Coverage Matrix — R5

| Requirement / OQ | Plan Step(s) | Coverage | Gaps (R5 view) |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled skeleton, language-wide) | Steps 1, 2, 3 | Partial | Go `package main` silent-empty mode uncovered (R5-S2); predicate breadth tracked by R3-S1 |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | Step 2↔4 co-landing bypass window (R5-S1); escalation-input vacuity (R5-S4); registry collision (R5-S3) |
| FR-3 (termination/no loop) | Step 4 | Partial | Primary/retry file-whole attempt accounting (R3-S2); checkpoint/resume idempotency (R1-S6) |
| FR-4 (budget/provider refusal) | Steps 0, 4 | Partial | Budget reach (R1-S3); exact-cap boundary + provider-impossible (R3-S4) |
| FR-5 (disk-validator detector) | Step 6 | Partial | Hard-fail/score-cap (R3-S3) — confirmed: empty `{}` has no stub markers, so `stub_penalty` stays 1.0 |
| FR-6 (minimal-file false positives) | Step 6 | Partial | `.d.ts`/`.tsx` split + Node-profile reuse (R3-S5/R4-S2) |
| FR-7 (SIMPLE requires spec/registry) | Steps 2, 5 | Partial | Authority (R1-S5); positive fillability (R3-S1); registry CLASS-only collision (R5-S3) |
| FR-8 (run-007 regression) | Step 7 | Partial | Go main shape (R5-S2); detector-regression lock (R5-S5); provider/budget cases (R3-S4) |
| OQ-3 (budget reach) | Step 0 | Gap | R1-S3 |
| OQ-4 (validator parse reuse) | Step 0 | Gap | R1-S4 — no Python AST reuse for `.ts`/`.go` |

#### Review Round R6 — composer-2.5 — 2026-05-31

- **Reviewer**: composer-2.5
- **Date**: 2026-05-31 18:30:00 UTC
- **Scope**: Sixth plan pass after R1–R5. Focus: upstream root cause (element deriver), success accounting bugs not yet specified, and TS stub-pattern gaps in the validator.

**Executive summary (new only):**

- **OQ-1 resolves to `seeds/element_deriver.py`**, not an unknown "seed/spec construction" site: `enrich_forward_manifest` → `derive_elements_for_file` T0 always injects a stem-named `CLASS` element for empty non-Python file_specs — the upstream source of CLASS-only specs for `.ts`/`.java`/`.go`/`.cs`.
- **Fix upstream, not only downstream:** guarding assemblers + skeleton emission without constraining element_deriver leaves the synthetic CLASS in the spec; every downstream consumer must re-derive "empty spec" logic. A T0 guard in the deriver collapses accidental complexity.
- **`_validate_and_finalize_files` treats zero-element files as 100% filled:** `total == 0 → rate = 1.0` and `fr is None → effective_file_count += 1` can mark skeleton-only / empty-spec outputs as effective even when no element was generated — distinct from R4-S3's multi-target `success` boolean.
- **`.ts`/`.tsx`/`.jsx` are absent from `_STUB_EXT_TO_LANG`**, so `_count_stubs_text` returns 0 for run-007's `.ts` shapes even after syntax validation is fixed — Step 6 must extend the map or resolve stub patterns via `LanguageRegistry` by extension.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | Architecture | high | Step 0 must **close OQ-1** by pinning the stem→CLASS synthesizer to `seeds/element_deriver.py:derive_elements_for_file` (T0, lines ~83–108) invoked from `enrich_forward_manifest` / `SeedBuilder.enrich_elements()`. Update the Step 0 Files column accordingly. | Requirements cite an unpinned "Node upstream synthesizer"; code search shows the cross-language source is element_deriver T0, not the Node assembler. Unpinned Step 0 risks fixing downstream emitters while the spec keeps acquiring synthetic CLASS shells on every empty file_spec. | Step 0 row (Files + Verify) | grep/test: empty `.ts` file_spec before skeleton emission contains one `element_deriver_t0` CLASS named after stem; OQ-1 marked resolved with file:line |
| R6-S2 | Architecture | high | Add a **Step 0/1 upstream guard in element_deriver**: do not inject T0/T1 stem CLASS when the file_spec has no T2 method elements and no registry/framework default applies; or mark such shells explicitly non-fillable in the shared predicate. | Patching Java/C#/Go assemblers + `_generate_skeletons` without fixing deriver preserves CLASS-only specs and forces N downstream sites to rediscover the same rule. Upstream guard is the lowest-complexity chokepoint aligned with R1-S2's shared-gate intent. | New sub-step under Step 0 or Step 1 | unit: empty `.ts` spec after enrichment has zero elements (or zero fillable elements); registry path still receives `DEFAULT_EXPORT`/`CONSTANT` |
| R6-S3 | Validation | high | Step 4 must fix **`_validate_and_finalize_files` effective counting**: when `len(fr.element_results) == 0` or `fr is None` for a target that had zero fillable elements, do **not** treat fill rate as 1.0 and do **not** increment `effective_file_count`. Pair with R4-S3's feature-level `success=False`. | Source: `rate = filled / total if total > 0 else 1.0` and `if fr is None: st.effective_file_count += 1`. Skeleton-only / CLASS-only files with no element generation can still count as "effective," reproducing run-007's false-positive success at the accounting layer. | Step 4 Verify column | unit: empty-spec file written as skeleton-only → `effective_file_count` unchanged for that target; mixed feature refuses or marks incomplete |
| R6-S4 | Validation | medium | Step 6 must extend **`_STUB_EXT_TO_LANG`** to include `.ts`, `.tsx`, and `.jsx` (map to `nodejs`), or replace the map with `LanguageRegistry` resolution from the file path so stub-pattern counting works for TypeScript. | `_STUB_EXT_TO_LANG` currently lists `.js`/`.mjs`/`.cjs` only; `_validate_js_file` hardcodes `_count_stubs_text(content, ".js")`. Run-007 stubs are `.ts`; even with R4-S2's Node-profile syntax reuse, ordinary stub counting stays at zero for TS unless this map is fixed. | Step 6 Files column | unit: `.ts` file with `throw new Error("TODO")` in body → `stubs_remaining > 0`; empty stem class still caught by dedicated FR-5 detector |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R5-S1: Step 2↔4 co-landing is critical given `_is_file_ollama_whole_eligible` requires stub markers.
- R5-S3 / R5-F2: Registry CLASS-only collision tie-break is required alongside positive fillability.
- R4-S1 / R6 upstream: stale `skeleton_sources`/`element_tiers` must be cleared on refusal.
- R3-S3: Hard-fail score cap for empty-stem detector — empty `{}` has no stub markers.

**Disagreements** (prior untriaged items this reviewer would reject or narrow):
- R2-S1: Reject full removal of registry clause without R5-S3 tie-break AND R6-S2 upstream guard; collision + deriver T0 CLASS can leave registry paths CLASS-only.

## Requirements Coverage Matrix — R6

| Requirement / OQ | Plan Step(s) | Coverage | Gaps (R6 view) |
| ---- | ---- | ---- | ---- |
| FR-1 (no unfilled skeleton shipped) | Steps 0, 1, 2, 3 | Partial | Upstream deriver unpinned (R6-S1/S2); downstream patches alone insufficient |
| FR-2 (escalate-or-refuse) | Steps 1, 4 | Partial | Zero-element effective counting (R6-S3); co-landing (R5-S1) |
| FR-5 (disk-validator detector) | Step 6 | Partial | `.ts`/`.tsx` stub-pattern map gap (R6-S4) in addition to R4-S2 syntax dedup |
| FR-8 (regression) | Step 7 | Partial | Must assert deriver enrichment + effective-count invariants, not only "not a stem stub" |
| OQ-1 (emitter site) | Step 0 | Partial | Should resolve to `element_deriver.py` T0 (R6-S1) |

*(CRP review rounds append here)*
