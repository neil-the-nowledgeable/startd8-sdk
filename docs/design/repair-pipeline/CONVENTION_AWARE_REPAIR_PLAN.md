# Convention-Aware Repair — Implementation Plan

**Version:** 0.3 (CRP R1 applied) · **Pairs with:** `CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` (v0.3)
**Date:** 2026-06-03

> Sequenced around the planning-pass discoveries: most FRs **extend established patterns** (the
> `convention` category already exists for C#; `content_contract` already detects wrong imports), but
> everything is **gated on FR-CAR-0** — the Python convention source-of-truth, which does not exist yet.

## Seam map (from the Phase-2 exploration)

| Concern | Existing seam (file:line) | Change |
|---|---|---|
| Convention rule source | `contractors/project_knowledge/{models,producer,negatives}.py` (TS/Prisma-only) | extend to Python + add framework/ORM authority (FR-CAR-0) |
| Diagnostic taxonomy | `repair/models.py` (`semantic`/`content_contract` subclasses) | add `ConventionDiagnostic` (FR-CAR-1) |
| Routing | `repair/routing.py:150` (`convention` route for C#) | add Python `convention` routes (FR-CAR-1) |
| Existing partial detection | `WrongImportPathDiagnostic`/`MisnamedFieldDiagnostic` (`models.py:128,146`) | reuse for `module_source` (FR-CAR-3) |
| Repair context | `RepairContext` carries `project_root`/`manifest_registry` (`models.py:234`) | add `convention_authority` handle (FR-CAR-2) |
| Residual escalation | `RepairOutcome` (`models.py:278`) has no residual; `_run_post_generation_repair` returns int | add `unrepaired_diagnostics`; rewire to escalate (FR-CAR-6) |
| In-run handoff | `EscalationHandoff` (`micro_prime/models.py:139`) prose-only | add residual payload (FR-CAR-6) |
| Verdict | `compute_disk_quality_score` (`forward_manifest_validator.py:553`) | add convention term / hard-gate (FR-CAR-7) |
| micro-prime injection | `MicroPrimeContext` (`context.py:11`) → `process_file_with_context` (`engine.py:2557`) | add field + thread (FR-CAR-5) |

## Phases

### Phase A — Authority + detection (advisory; no behavior change) — FR-CAR-0/1/2/3
1. **`PythonConventionAuthority`** (FR-CAR-0): **module-source** rules derived from the declarative
   `CANONICAL_LAYOUT` (tables=`app.tables`, schemas=`app.models`); **framework/orm/template idiom** rules from
   a **small generator-adjacent declarative manifest** (FastAPI / SQLModel / `Jinja2Templates` + the
   `Negative` set Flask→FastAPI, `session.query`→`select`, `app.models`-table→`app.tables`) **asserted-equal
   to renderer output by the FR-CAR-2 parity test** — NOT parsed out of the f-string renderers (v0.3 R1-S1).
   Live next to / inside `project_knowledge`; extend the producer to read `.py`.
2. **`ConventionDiagnostic`** subclass + register the Python `convention` routes (mirror the C# route).
3. **Detectors**: reuse `content_contract` for `module_source`; new AST/regex detectors for `framework`,
   `orm_idiom`, `template_idiom`, sourced from the authority (not hardcoded).
4. **Parity test** (FR-CAR-2/8): generate an app (the pilot schema), corrupt each convention, assert the
   detector fires. Seed fixtures from RUN-028's `…/generated/app/jobs.py`.
   *Exit A:* detection emits `ConventionDiagnostic`s; nothing fails yet (advisory).

### Phase B — Escalate-don't-silence + verdict (the RUN-028 fix) — FR-CAR-4/6/7
5. **Safe fixers** (FR-CAR-4): deterministic, revert-on-break — `session.query(X).get(id)`→`session.get(X,id)`;
   wrong-module import→canonical (reuse `content_contract` fixers). Wholesale framework wrong → no fix.
   **v0.3 (R1-S6/R1-S10):** add the **authority-governed-scope guard** — only generator-owned artifact kinds
   are auto-fixed; hand-written files (`app/ai/extract.py`) are detect-and-advise (acceptance: zero rewrites);
   `RepairContext` gains `convention_authority` (default `None`, all call-sites migrated).
6. **Residual plumbing** (FR-CAR-6): add `RepairOutcome.unrepaired_diagnostics` (**= the iterative loop's
   "complete true residual"**, same `List[Diagnostic]`; the `--iterate` driver consumes it, no second scan —
   R1-S2); **add a convention-detection checkpoint INTO `_run_post_generation_repair`** (today it runs only
   `check_syntax`+`check_lint` → emits no convention diagnostics; without this the micro-prime residual stays
   empty — R1-S3); rewire it to escalate the residual instead of returning a bare count. Add a residual payload
   to `EscalationHandoff` (frozen dataclass → defaulted field + call-site migration — R1-S5).
7. **Verdict gate** (FR-CAR-7): use a **hard-gate** (error-severity convention violation → 0.0, like
   `ast_valid`) — **not** a weighted 5th factor, which would re-normalize the 1.0-sum formula and destabilize
   every threshold + the corpus calibration (R1-S4). De-dup: a `convention`-counted diagnostic is excluded
   from `semantic_issues` scoring. **Symptom-fix guard test:** a file with both an F811 and a Flask import must
   FAIL even after the F811 is auto-fixed.
   *Exit B:* RUN-028 replay → the wrong-framework file FAILS loudly (not lint-clean PASS), with the residual
   escalated.

### Phase C — Reach the cheapest tier — FR-CAR-5
8. Thread the authority into micro-prime: add a `MicroPrimeContext` field, populate from `gen_context` in
   `from_prime` (prime_contractor holds `self._project_knowledge`), pass through
   `process_file_with_context` → `process_file` → prompt builders. Measure adherence lift on the micro-prime
   tier against the RUN-028 corpus (structural scoring, per the CKG methodology gate).

### Phase D — Lock-step + learning — FR-CAR-8/9/10
9. **Parity-in-lock-step** (FR-CAR-8): a meta-test asserting every owned-artifact kind in `CANONICAL_LAYOUT`
   (+ pages kinds) has a convention rule + parity fixture; a new generator without coverage fails CI.
   **v0.3 (R1-S8): deferred until after the Python proof (Phases A–C), and additive only.** The meta-test
   covers **generator-backed** languages (Python); the existing hand-coded C#/Go/Java steps (no generator to
   derive from) get a **declarative manifest + golden-corpus regression test** (assert no behavior change) —
   NOT a rewrite, so the meta-test never mis-fires on them.
10. **Telemetry → Kaizen** (FR-CAR-9): OTel counters (category/rule/tier/outcome) + a
    `requirement_convention_gap` CAUSE_TO_SUGGESTION; feed recurring per-tier violations to the classifier
    signal (postmortem A1 / D3). Keep everything deterministic/no-LLM (FR-CAR-10).

## Verification
- Unit: detector parity (generate→corrupt→detect) per convention; safe-fixer round-trips; residual surfaced;
  verdict FAILs a lint-clean wrong file; symptom-fix guard.
- Integration: RUN-028 `jobs.py` replay → detected + escalated + FAILED (today: silent PASS at micro-prime).
- **Corpus fixtures:** seed detectors + parity tests from the Controlled Corpus `false_pass_risk` set
  (`docs/design/controlled-corpus/`), esp. the Flask-RAG `shoppingassistantservice.py` (stability 1.0 /
  req 0.5) — the convention detector must flag it and the verdict term must score it failing, demonstrating
  the two-axis (structural × semantic) gate.
- Cross-tier: micro-prime adherence lift on the corpus after Phase C.
- **Regression guard against the symptom-fix trap:** assert that applying the F811 dedup (`886dccbd`) to a
  Flask file does NOT raise its disk-quality score (the convention term holds it failing).
- **v0.3 (R1-S9) escalation sibling test:** the symptom-fix guard above only checks the *verdict*; add a sibling
  asserting the **escalation path** also surfaces the residual (score=FAIL **AND** residual present in the
  `EscalationHandoff` payload) — verdict and escalation can regress independently.
- **v0.3 (R1-S7) advisory→gating precondition:** define the numeric FP gate (FP < X% over N corpus files) as
  the Exit-A→Phase-B precondition; no error-severity gate/escalation flips on until it's met (FR-CAR-11).

## Risks / open
- FR-CAR-0 is the critical path; if the authority can't be cleanly derived from the generators, fall back to
  a small generator-adjacent convention manifest (still parity-tested) — but avoid a hand-maintained list.
- False positives on `module_source`/`orm_idiom` in legitimately dual-pattern code (e.g. `app/ai/extract.py`
  supports both `session.query` and `select`) — detectors must be authority-scoped, not blanket grep.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Manifest for framework/ORM/template; `CANONICAL_LAYOUT` for module-source only | CRP R1 | **Applied** to Phase A step 1. | 2026-06-03 |
| R1-S2 | Unify `unrepaired_diagnostics` with the iterative "true residual" | CRP R1 | **Applied** to Phase B step 6. | 2026-06-03 |
| R1-S3 | Add convention-detection checkpoint into `_run_post_generation_repair` | CRP R1 | **Applied** to Phase B step 6 (else micro-prime residual is convention-empty). | 2026-06-03 |
| R1-S4 | Hard-gate over weighted term + de-dup vs `semantic_issues` | CRP R1 | **Applied** to Phase B step 7. | 2026-06-03 |
| R1-S5 | Flag frozen-dataclass breaking change + migration | CRP R1 | **Applied** to Phase B step 6 (EscalationHandoff) + step 5/6 (RepairContext). | 2026-06-03 |
| R1-S6 | Authority-governed-scope guard for safe-fixers | CRP R1 | **Applied** to Phase B step 5. | 2026-06-03 |
| R1-S7 | Numeric advisory→gating FP precondition | CRP R1 | **Applied** to Verification + FR-CAR-11. | 2026-06-03 |
| R1-S8 | Defer FR-CAR-8 retrofit; additive/golden-corpus, not rewrite | CRP R1 | **Applied** to Phase D step 9. | 2026-06-03 |
| R1-S9 | Escalation-path sibling test (not just verdict) | CRP R1 | **Applied** to Verification. | 2026-06-03 |
| R1-S10 | `RepairContext.convention_authority` defaulted; migrate call-sites | CRP R1 | **Applied** to Phase B step 5. | 2026-06-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all 10 R1-S suggestions accepted) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-04

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-06-04 04:05:00 UTC
- **Scope**: Pre-implementation review of the phased plan; weighted to the focus-file asks. Findings grounded in code (`repair/models.py`, `routing.py:150`, `micro_prime/{models,context,prime_adapter}.py`, `forward_manifest_validator.py:553`, `project_knowledge/producer.py`, `repair/steps/csharp_convention_fix.py`).

##### Executive summary (top risks / opportunities)

- FR-CAR-0 "derive from the renderers" is mechanically unclean: the `backend_codegen` renderers are Python f-string templates, not declarative; only `CANONICAL_LAYOUT` is cleanly consumable. The plan's fallback manifest (Risks 1) should be the *primary* path for framework/ORM idiom rules.
- Two residual concepts (this plan's `unrepaired_diagnostics` vs `REPAIR_RETRY_ITERATIVE`'s "complete true residual") are not unified in the plan; Phase B step 6 should declare them one type.
- Verdict change (step 7) has an unaddressed double-count vs `semantic_issues` and a re-weighting hazard: the formula sums to 1.0, so a 5th weighted factor rescales every historical score — favor the hard-gate.
- Step 6's escalation target (`_run_post_generation_repair`) today runs only syntax+lint checkpoints; the plan must add a convention-detection checkpoint *into that path* or the micro-prime residual stays empty.
- FR-CAR-8 (Phase D step 9) retrofit of working C#/Go/Java steps is a rewrite of code with no generator to parity-test against; sequence it strictly after the Python proof, as additive regression coverage.
- Frozen-dataclass contract changes (`EscalationHandoff`, `MicroPrimeContext`) are breaking; the seam map omits the call-site migration cost.

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Phase A step 1: make the framework/ORM/template rules come from a declarative generator-adjacent manifest asserted-equal-to-renderer-output, reserving "derived from generators" for `CANONICAL_LAYOUT` module-source only. | The renderers are f-string templates; "renderer idioms → framework=FastAPI" implies parsing Python templates. The plan's own Risks-1 fallback is the cleaner primary mechanism. | Phase A step 1 ("renderer idioms → framework=FastAPI…") | Parity test fires per rule-kind regardless of provenance path. |
| R1-S2 | Interfaces | high | Phase B step 6: declare `RepairOutcome.unrepaired_diagnostics` to be the same `List[Diagnostic]` as the iterative loop's "complete true residual," and have the iterative driver consume it rather than re-scan. Specify `EscalationHandoff` residual as `Diagnostic` objects or a documented projection. | Step 6 introduces a residual that overlaps `REPAIR_RETRY_ITERATIVE` FR-7/FR-8 (regen worklist). One axiom, two types = drift. | Phase B step 6 ("Residual plumbing") | Integration: iterative `--iterate` reads `unrepaired_diagnostics`; no second scan path. |
| R1-S3 | Risks | high | Phase B step 6: note that `_run_post_generation_repair` (`prime_adapter.py:1468`) only runs `check_syntax`+`check_lint` — it produces NO convention diagnostics today. Add a convention-detection checkpoint into this path, else the residual is always convention-empty in the micro-prime path RUN-028 exercises. | The whole motivating bug is micro-prime; rewiring "escalate the residual" without adding detection here changes nothing for RUN-028. | Phase B step 6 + Seam map "Residual escalation" row | RUN-028 replay through `_run_post_generation_repair` yields a `ConventionDiagnostic` in the residual. |
| R1-S4 | Data | high | Phase B step 7: choose the hard-gate over a weighted 5th factor, and add a de-dup so a `convention`-counted diagnostic is excluded from `semantic_issues` scoring. | `compute_disk_quality_score` sums contract 0.4 + import 0.2 + stub 0.2 + semantic 0.2 = 1.0; a weighted convention term re-normalizes every historical score and threshold. `semantic_issues` already penalizes — double-count risk. | Phase B step 7 ("convention term / hard-gate") | Regression: convention-clean corpus scores unchanged; single convention error not penalized twice. |
| R1-S5 | Interfaces | medium | Seam map + Phase C step 8: flag that `EscalationHandoff` (`models.py:139`) and `MicroPrimeContext` (`context.py:11`) are `frozen=True` with multiple `from_*` constructors and `to_dict`/`to_prompt_section` consumers; field additions are breaking and need defaults + a call-site migration sub-task. | The seam map lists "add field + thread" as if additive; on frozen dataclasses it touches every constructor and serializer. | Seam map rows "In-run handoff" / "micro-prime injection" | All `EscalationHandoff(`/`MicroPrimeContext(` call-sites compile with defaulted new fields. |
| R1-S6 | Risks | high | Phase B step 5: add the authority-governed-scope guard to the safe-fixers so dual-pattern hand-written files (`app/ai/extract.py`) are never auto-rewritten — Risks bullet 2 names the file but no plan step enforces scope. | "authority-scoped, not blanket grep" is asserted in Risks but no step implements the scope check; revert-on-break catches breakage, not a false rewrite of a correct `session.query`. | Phase B step 5 ("Safe fixers") | `extract.py` → zero rewrites; generator-owned file → fixed. |
| R1-S7 | Validation | medium | Verification §: the advisory→gating flip lacks a numeric gate. Add the false-positive threshold (FP rate over the `false_pass_risk` corpus) that must be met before any error-severity convention gate is enabled. | Phases A (advisory) → B (gating) flip behavior, but no measured precondition is stated; the ramp is currently a judgment call. | Verification section + Phase A/B boundary | Define FP<X% on N corpus files as the Exit-A→Phase-B precondition. |
| R1-S8 | Ops | medium | Phase D step 9: sequence the FR-CAR-8 polyglot retrofit explicitly *after* Phase C (Python proof), and scope it to additive regression coverage (golden-corpus) for C#/Go/Java where no generator exists to derive from. | `csharp_convention_fix.py` reads no authority and has rules (PascalCase) with no generator; the meta-test "fails CI if a generator lacks coverage" would mis-fire on hand-coded steps. | Phase D step 9 ("Parity-in-lock-step") | Meta-test green for Python; C#/Go/Java covered by golden-corpus regression, no behavior change. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Validation | medium | Verification §: the symptom-fix guard test ("F811 + Flask import must FAIL even after F811 auto-fixed") only exercises the *verdict*; add a sibling test that the **escalation** path also surfaces the residual (verdict and escalation can regress independently). | FR-CAR-6 (escalate) and FR-CAR-7 (verdict) are separate mechanisms; a green verdict test doesn't prove the residual reached `EscalationHandoff`. | Verification, after "Symptom-fix guard test" | Assert both: score=FAIL AND residual present in the handoff payload. |
| R1-S10 | Data | low | Seam map "Repair context" row: confirm `RepairContext` (`models.py:234`) needs a NEW `convention_authority` field — it currently carries `manifest_registry` but nothing convention-shaped — and that all `RepairContext(` constructors default it to `None` for backward compat. | The plan says "add `convention_authority` handle" but `RepairContext` is consumed widely; a non-defaulted field breaks every existing step's context construction. | Seam map "Repair context" row | grep `RepairContext(` call-sites compile with defaulted field. |

---

## Requirements Coverage Matrix — R1

Analysis only (reviewer `claude-opus-4-8-1m`, 2026-06-04). Maps each requirement to the plan step(s) that address it. `Covered` = clear implementation step; `Partial` = mentioned but missing detail/edge-cases; `Gap` = not addressed by a plan step.

| Requirement | Plan Step(s) | Coverage | Notes / what's missing |
| ---- | ---- | ---- | ---- |
| FR-CAR-0 (Python convention source-of-truth) | Phase A step 1; Risks bullet 1 (fallback) | Partial | "Derive from renderers" is mechanically unclean (f-string templates); only `CANONICAL_LAYOUT` is declarative. Promote the manifest fallback for framework/ORM idioms (R1-S1/R1-F1). |
| FR-CAR-1 (`convention` diagnostic category) | Phase A step 2; Seam map (routing.py:150) | Covered | C# route is the working precedent; `ConventionDiagnostic` subclass + Python routes are additive. |
| FR-CAR-2 (single source, parity-enforced) | Phase A step 4 (parity test) | Partial | Parity test defined for the generated→corrupt→detect path, but parity provenance per rule-kind (declarative vs renderer) is not split (R1-S1). |
| FR-CAR-3 (detect the RUN-028 class) | Phase A step 3; Verification (replay) | Partial | Detectors specified, but the post-gen path (`_run_post_generation_repair`) runs only syntax+lint — no convention checkpoint is wired in where RUN-028 actually flows (R1-S3/R1-F9). |
| FR-CAR-4 (safe-fix vs escalate) | Phase B step 5 | Partial | Lists fixers + "no wholesale rewrite," but no authority-governed-scope guard for dual-pattern files; revert-on-break ≠ false-rewrite guard (R1-S6/R1-F6/R1-F10). |
| FR-CAR-5 (adherence reaches micro-prime) | Phase C step 8 | Partial | Threading specified, but `MicroPrimeContext`/`from_prime` are `frozen=True` and `gen_context` carries no `project_knowledge` today; breaking-change migration not scoped (R1-S5/R1-F3). |
| FR-CAR-6 (escalate, don't silence) | Phase B step 6 | Partial | Two model changes named, but residual is not unified with `REPAIR_RETRY_ITERATIVE`'s "true residual," and the drop-site only sees syntax/lint diagnostics (R1-S2/R1-S3/R1-F2). |
| FR-CAR-7 (convention = hard verdict signal) | Phase B step 7 | Partial | Hard-gate-vs-weighted-term left open; double-count vs `semantic_issues` and re-weighting of the 1.0-sum formula unaddressed (R1-S4/R1-F4/R1-F8). |
| FR-CAR-8 (coverage parity / polyglot lock-step) | Phase D step 9 | Partial | Meta-test would mis-fire on hand-coded C#/Go/Java steps that have no generator; retrofit not sequenced after Python proof (R1-S8/R1-F5). |
| FR-CAR-9 (telemetry + Kaizen) | Phase D step 10 | Covered | OTel counters + CAUSE_TO_SUGGESTION mapping; consistent with existing micro-prime repair metrics. |
| FR-CAR-10 (deterministic, reuse-not-rebuild) | All phases; Verification | Covered | Reuses `Diagnostic`/`RepairContext`/routing/`EscalationHandoff`; one new `RepairContext.convention_authority` field flagged (R1-S10). |

