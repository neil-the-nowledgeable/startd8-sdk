# Semantic Compliance Reviewer — Implementation Plan

**Version:** 0.3 (CRP-triaged — rounds R1–R4 applied)
**Date:** 2026-06-03
**Status:** Plan — pre-implementation
**Tracks:** `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` v0.3

---

## Design summary

The SCR is the **first producer** of the dormant `SemanticVerificationResult` (K-7) contract.
It compares generated output against the *original requirement* for selected features and routes
findings into Kaizen so the next run is more compliant. Post-run / Service-Assistant-orchestrated
first; same contract designed to be hoisted into the in-run `MicroPrimeConfig.semantic_verification_*`
hook later. Tiered (cheap triage → Haiku review → Sonnet escalation); advisory in v1.

```
SA detects completed run
   └─ triggers SCR (within escalation budget)
        1. load prime-context-seed*.json → feature→requirement map      (FR-1)
        2. read prime-postmortem-report.json → per-feature triage signals (FR-4)
        3. rank suspicion; pick escalations + bounded PASS sample        (FR-5/5a)
        4. assemble (requirement + design intent + generated files)      (FR-1/2/3)
        5. Haiku review → SemanticVerificationResult; Sonnet on fail/low-conf (FR-6/15)
        6. score + dedup vs semantic_issues                              (FR-8, OQ-5)
        7. write semantic-compliance-report.json/.md                     (FR-9)
        8. emit templated hints → kaizen-suggestions.json + cross-feature patterns (FR-10/11)
        9. SA folds results into triage artifact + SEMANTIC_REVIEW_COMPLETE event (FR-12)
```

## Module layout

| New artifact | Purpose | Maps to |
|--------------|---------|---------|
| `src/startd8/semantic_compliance/__init__.py` | Package + `SemanticComplianceReviewer` facade | all |
| `.../requirement_loader.py` | Load `prime-context-seed*.json`, feature→task map | FR-1 |
| `.../triage.py` | Suspicion ranking from post-mortem signals + PASS sample | FR-4/5/5a |
| `.../reviewer.py` | Agent invocation → `SemanticVerificationResult` (Haiku→Sonnet) | FR-6/15 |
| `.../prompts.py` | Versioned requirement-anchored review rubric | FR-7 |
| `.../scoring.py` | `semantic_compliance_score`, dedup vs semantic_issues | FR-8 |
| `.../report.py` | `semantic-compliance-report.json`/`.md` | FR-9 |
| `.../feedback.py` | Templated hints → kaizen `prompt_hints`; cross-feature patterns | FR-10/11 |
| `prime_postmortem.py` (edit) | add `requirement_semantic_gap` → `CAUSE_TO_SUGGESTION` | FR-10 |
| `service_assistant/` (edit) | launch SCR detached; fold `pending`; reconcile event | FR-12 |
| `events/types.py` (edit) | new `SEMANTIC_REVIEW_COMPLETE` EventType member *(R1-S3)* | FR-12 |
| `.../cache.py` | verdict cache by `(run_id, feature_id, code_checksum)` *(S-R1-2)* | FR-1 |
| `SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md` | versioned report contract *(S-R1-3)* | FR-9 |
| `micro_prime/models.py` | reuse `SemanticVerificationResult` (no change) | FR-6/13 |

## Step-by-step

1. **Requirement loader** — read `prime-context-seed*.json` (`tasks[].config.{requirements_text,
   task_description}` + `prompt_constraints`); map `feature_id`↔seed `tasks[].id`, **corroborated**
   by `target_files`∩`generated_files` overlap → else `inconclusive: requirement_join_ambiguous`
   *(S-R1-4)*. Multi-seed glob → deterministic latest-by-mtime; id collisions → `inconclusive`
   *(R1-S5)*. Missing → `inconclusive` (`requirement_text_unavailable`). Verdicts cached by
   `(run_id, feature_id, code_checksum)` so re-runs don't re-pay *(S-R1-2)*. *(FR-1)*
2. **Triage** — from `prime-postmortem-report.json`: rank by structural-emptiness signals
   (`fake_work_stub`, `assembly_delta`, `disk_quality_score`) **above** `requirement_score`,
   plus `verdict` and sibling shared `root_cause`; add a `fake_work_stub`-adjacent PASS sample drawn
   from a **reserved quota** independent of the FR-5 budget *(R2-S4)*. Missing/unparseable report →
   mark features `postmortem_unavailable`, no crash *(R3-S3)*. *(FR-4/5/5a)*
3. **Input assembly** — requirement text + forward-manifest `InterfaceContract.binding_text` +
   CKG `ProjectKnowledge.{field_sets,negatives}` + generated files (`generated_files`), **excluding
   third-party/boilerplate**, under a `max_input_tokens` budget with truncation→`inconclusive`, and
   `security.py`-redacted before assembly *(R3-S1/R3-F1/F-R1-5)*. *(FR-1/2/3)*
4. **Reviewer** — resolve agent via `model_catalog` (`SEMANTIC_VALIDATOR`=Haiku), **deterministic
   decoding** (temp 0/seed) and explicit `max_tokens` *(R2-S5/R3-S4)*. Single-shot `agenerate` →
   `validate_semantic_verification_json`; on `(False, …)` one bounded retry then `inconclusive`
   *(R1-S7)*. Escalate to `CODE_REVIEW`=Sonnet on `fail`/low-confidence — **Sonnet is terminal**
   (its low-confidence result is final, no recursion) *(R4-S2)*. Budget read from config and debited
   to the shared `CostTracker`/`CostSummary` *(R1-S6/R2-S2)*; transient provider 429/529 → bounded
   backoff, then `inconclusive` (cross-provider fallback deferred — see Risks) *(R4-S1, scoped)*.
   Multi-sample voting behind a flag. *(FR-6/15)*
5. **Rubric** — versioned prompt anchored on requirement satisfaction + honoring named
   contracts/field authorities + not inventing forbidden constructs (CKG negatives). **Delimits
   untrusted reviewed content** and instructs the agent to ignore embedded instructions
   (anti-prompt-injection) *(R1-S8)*. **Language-aware** — per-feature `language` selects the rubric
   variant; v1 is Python-only (non-Python → `inconclusive: language_unsupported`) *(R2-S1)*. Feature
   verdicts carry an explicit `review_granularity: "feature"|"element"` and a documented
   feature→`element_fqn` mapping (synthetic `feature:<feature_id>`) so post-run and Phase-2 element
   verdicts are comparable *(R1-S4/S-R1-5)*. *(FR-7)*
6. **Scoring + dedup** — `semantic_compliance_score` from verdict+confidence+issue severities;
   drop issues whose category already appears in `disk_compliance.semantic_issues`. *(FR-8, OQ-5)*
7. **Report** — `semantic-compliance-report.json` (+ `.md`): per-feature verdicts/issues/scores,
   triage+escalation decisions, requirement text reviewed. **Round-trip-safe serialization**: the
   loader and `from_json` must agree on the `verification` envelope (else a reloaded report silently
   auto-corrects to `inconclusive`) *(R1-S1)*. **Atomic write-rename + `status: pending|complete`**
   so the detached SCR (Step 9) never lets the SA fold read partial JSON *(R2-S3)*. Strips raw code
   snippets — bounded excerpts only, to cap artifact size and avoid secret leakage *(R4-S3)*. Pin
   the contract in a `SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md` (mirrors the SA `TRIAGE_SCHEMA.md`)
   *(S-R1-3)*. *(FR-9)*
8. **Feedback** — emit the **structured suggestion-dict** schema `generate_kaizen_suggestions`
   produces (`pattern_type`/`suggested_action`/`config_key`/`phase`/`confidence`/`auto_applicable`),
   **not bare strings** *(R1-S2)*; confidence-gate + advisory-flag the hints (FR-10). Register the
   generic `requirement_semantic_gap` `{phase,hint}`. Emit cross-feature patterns via the existing
   `CrossFeaturePattern` dataclass (no parallel store), gated on the relative threshold *(R2-S6)*.
   On a later `pass`, **prune/tombstone** the feature's stale hints *(R3-S2)*. *(FR-10/11)*
9. **SA orchestration** — SA **launches the SCR as a detached/async step** (not inline), preserving
   its "never block the pipeline, exit fast" contract; the triage artifact references the compliance
   report as `pending`, reconciled later by the `SEMANTIC_REVIEW_COMPLETE` event *(S-R1-1)*. Adding
   that event requires a new `EventType` member in `events/types.py`. *(FR-12)*
10. **OTel** — span attrs: `scr.review_count`, `scr.escalations`, `scr.cost_usd`,
    `scr.avg_confidence`, verdict distribution. *(FR-16)*

## Reuse map (don't reinvent)

| Need | Existing component |
|------|--------------------|
| Verdict contract | `SemanticVerificationResult` / `VerificationIssue` (`micro_prime/models.py`) |
| Triage signals | `FeaturePostMortem` fields in `prime-postmortem-report.json` |
| Requirement text | `prime-context-seed*.json` → `SeedTask` (`seeds/models.py`) |
| Design intent | `InterfaceContract.binding_text`; CKG `ProjectKnowledge` (`contractors/project_knowledge/`) |
| Feedback loop | `generate_kaizen_suggestions` / `kaizen-suggestions.json` / `_apply_kaizen_hints` |
| Model tiers | `Models.SEMANTIC_VALIDATOR` (Haiku), `Models.CODE_REVIEW` (Sonnet) |
| Cost accounting | `CostTracker` / `CostSummary` — debit reviews, reconcile `scr.cost_usd` *(R2-S2)* |
| Cross-feature patterns | `CrossFeaturePattern` (`prime_postmortem.py`) — no parallel store *(R2-S6)* |
| In-run home (Phase 2) | `MicroPrimeConfig.semantic_verification_{enabled,agent_spec,fn}` |
| Orchestration | `service_assistant/` (detect→launch-detached→fold) |

## Risks / watch-items

- **Requirement text absent** (OQ-1) — must degrade to `inconclusive`, never fabricate compliance.
- **Cheap-tier reliability** (OQ-4) — Haiku `fail` verdicts may be noisy; escalate to Sonnet before
  emitting a high-severity Kaizen hint; keep multi-sample voting available for gating-readiness.
- **Double-reporting** (OQ-5) — dedup SCR findings against `semantic_issues` categories.
- **Altitude** (OQ-9) — feature-level vs element-level verdict comparability with the Phase-2 hook.
- **Cost creep** — escalation budget + PASS-sample cap must be enforced and logged (no silent caps).
- **SA coupling** (S-R1-1) — SCR must run **detached**; inline N-agent review would block the SA's fast post-run hook.
- **Provider outage** (R4-S1) — cheap-tier 429/529 → bounded backoff then `inconclusive`; cross-provider fallback (Gemini-tier equiv) **deferred** to a follow-up, not v1.
- **Feedback poisoning** (F-R1-4 / R3-F2) — confidence-gate + advisory-flag hints; prune on later `pass`.
- **Wrong-requirement join** (S-R1-4) — corroborate the seed-task join by `target_files`∩`generated_files`.

## Verification

- [ ] Every FR (1–16, 5a) has a step; every step traces to an FR.
- [ ] Requirement-unavailable → `inconclusive` (not a false PASS/FAIL).
- [ ] Tiered: Haiku-only on clear cases; Sonnet only on fail/low-confidence (cost asserted).
- [ ] run-018 replay: 6 shared-cause features → one cross-feature semantic pattern + templated hint.
- [ ] False-PASS: a `fake_work_stub`-adjacent PASS gets sampled and flagged.
- [ ] Advisory: no run blocked; schema carries verdict+confidence for future gate.
- [ ] Round-trip: a persisted report reloaded via `from_json` reproduces verdict/confidence *(R1-S1)*.
- [ ] Idempotency: re-run with unchanged code reuses cached verdicts, zero new agent cost *(S-R1-2)*.
- [ ] Wrong-join guard: file-overlap mismatch → `inconclusive`, not a confident verdict *(S-R1-4)*.
- [ ] Detached SCR: SA fold during in-flight review sees `pending`, never partial JSON *(R2-S3/S-R1-1)*.
- [ ] Language: a non-Python feature → `inconclusive: language_unsupported` *(R2-S1)*.
- [ ] Determinism: identical inputs → identical verdict+confidence across two runs *(R2-S5)*.

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

> Triaged by claude-opus-4-8, 2026-06-03 (orchestrator). 25 of 26 plan suggestions ACCEPTED;
> R4-S1 accepted **scoped** (bounded backoff in v1; cross-provider fallback deferred — see Appendix B).

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Round-trip-safe report serialization | R1 (table) | Step 7 + Verification | 2026-06-03 |
| R1-S2 | `feedback.py` emit structured suggestion dict | R1 (table) | Step 8 | 2026-06-03 |
| R1-S3 | `events/types.py` `SEMANTIC_REVIEW_COMPLETE` member | R1 (table) | Module layout | 2026-06-03 |
| R1-S4 | feature→`element_fqn` mapping convention | R1 (table) | Step 5 | 2026-06-03 |
| R1-S5 | Multi-seed-file selection/precedence | R1 (table) | Step 1 | 2026-06-03 |
| R1-S6 | Pin escalation-budget config + enforcement | R1 (table) | Step 4 + FR-5 | 2026-06-03 |
| R1-S7 | Validator parse-failure path | R1 (table) | Step 4 | 2026-06-03 |
| R1-S8 | Rubric prompt-injection hardening | R1 (table) | Step 5 | 2026-06-03 |
| S-R1-1 | SA→SCR detached/async | R1 (prose) | Step 9 + Risks | 2026-06-03 |
| S-R1-2 | Verdict cache idempotency | R1 (prose) | Step 1, `cache.py`, Verification | 2026-06-03 |
| S-R1-3 | Versioned report schema doc | R1 (prose) | Step 7 + Module layout | 2026-06-03 |
| S-R1-4 | Requirement→feature join corroboration | R1 (prose) | Step 1 + Verification | 2026-06-03 |
| S-R1-5 | `review_granularity` field | R1 (prose) | Step 5 | 2026-06-03 |
| R2-S1 | Language first-class / per-language rubric | R2 | Step 5 (Python-only v1) | 2026-06-03 |
| R2-S2 | Reuse `CostTracker`/`CostSummary` | R2 | Step 4 + Reuse map | 2026-06-03 |
| R2-S3 | Atomic report + `status: pending\|complete` | R2 | Step 7 + Verification | 2026-06-03 |
| R2-S4 | Reserved PASS-sample quota | R2 | Step 2 | 2026-06-03 |
| R2-S5 | Deterministic decoding | R2 | Step 4 + Verification | 2026-06-03 |
| R2-S6 | Reuse `CrossFeaturePattern` dataclass | R2 | Step 8 + Reuse map | 2026-06-03 |
| R3-S1 | `max_input_tokens` / truncation | R3 | Step 3 | 2026-06-03 |
| R3-S2 | Prune stale Kaizen hints on `pass` | R3 | Step 8 | 2026-06-03 |
| R3-S3 | Missing post-mortem fallback | R3 | Step 2 | 2026-06-03 |
| R3-S4 | Strict `max_tokens` on `agenerate` | R3 | Step 4 | 2026-06-03 |
| R4-S2 | Sonnet escalation is terminal | R4 | Step 4 | 2026-06-03 |
| R4-S3 | Report strips raw code snippets | R4 | Step 7 | 2026-06-03 |
| R4-S1 | API outage fallback | R4 | **Scoped** — backoff in v1; cross-provider deferred (App. B) | 2026-06-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R4-S1 (part) | Cross-provider fallback to a Gemini-tier model on outage | R4 | **Deferred, not rejected.** v1 handles 429/529 via bounded backoff → `inconclusive`; a concrete cross-provider failover is premature pre-implementation and adds provider-matrix scope. Revisit once the cheap-tier reviewer's real outage behavior is measured. | 2026-06-03 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 (table pass) — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:29:00 UTC
- **Scope**: First dual-document pass on the plan — robustness, interface fidelity to the real `SemanticVerificationResult` / Kaizen / Service-Assistant seams, cost discipline, and end-user value. Anchored to verified code (`micro_prime/models.py`, `prime_postmortem.py`, `events/types.py`).

**Executive summary**

- **Round-trip contract hazard (high):** `SemanticVerificationResult.to_dict()` nests under a `"verification"` key, but `from_json()` reads `verdict`/`confidence` at the **top level** — a reader of the persisted report (Step 7) silently auto-corrects to `inconclusive`. The SCR is the *first producer*, so it owns this seam.
- **Kaizen interface mismatch (high):** Step 8 emits "hint strings" into `prompt_hints`, but `generate_kaizen_suggestions` produces **structured suggestion dicts** (`pattern_type`, `suggested_action`, `config_key`, `phase`, `confidence`, `auto_applicable`). Raw strings will not flow through the existing loop.
- **Missing wiring callout (medium):** `SEMANTIC_REVIEW_COMPLETE` (FR-12) needs a new `EventType` enum member in `events/types.py`; the module-layout table only lists `service_assistant/ (edit)`.
- **Cost discipline under-specified (medium):** escalation budget has no config source, defaults, or single enforcement point in the plan despite being a headline risk.
- **Altitude bridge undefined (medium):** "feature name → `element_fqn`" is asserted but `element_fqn` is element-scoped; without a mapping convention, post-run and Phase-2 in-run verdicts are not comparable.
- **Opportunities:** the triage layer (Step 2) already computes everything needed for a per-feature suspicion score — persisting it in the report is ~free analytics value; the rubric is a natural place to harden against prompt-injection from reviewed code.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | Specify a round-trip-safe serialization for the persisted report: either unwrap before `from_json` or have the loader read the `verification` envelope, since `to_dict()` nests under `"verification"` while `from_json()` reads top-level `verdict`. | A consumer reloading `semantic-compliance-report.json` via `from_json` gets `data.get("verdict")==None` → silent `inconclusive` (auto-correct in `from_json`). The SCR is the first producer and will define this norm. | Step 7 "Report"; Reuse map "Verdict contract" | Round-trip unit test: `from_json(json.loads(persisted))` reproduces the original verdict/confidence/issues. |
| R1-S2 | Interfaces | high | Make `feedback.py` emit the **suggestion-dict schema** that `generate_kaizen_suggestions` produces (`pattern`, `pattern_type`, `suggested_action`, `config_key="prompt_hints"`, `phase`, `confidence`, `auto_applicable`) or call a shared emitter — not bare hint strings. | `_apply_kaizen_hints` consumes the structured suggestion list; raw strings injected ad hoc may be dropped or bypass the existing pipeline. | Step 8 "Feedback"; module `feedback.py` | Assert SCR output dict matches `generate_kaizen_suggestions` shape and is picked up by `_apply_kaizen_hints` into `gen_context["kaizen_hints"]`. |
| R1-S3 | Interfaces | medium | Add an `events/types.py (edit)` row to the Module-layout table for the new `SEMANTIC_REVIEW_COMPLETE` member; today only `service_assistant/ (edit)` is listed. | `EventType` is an `auto()` enum (`events/types.py`); emitting a new event requires a new member, which is a real edit site the plan omits. | "## Module layout" table | Enum member exists; an emit→subscribe test sees `SEMANTIC_REVIEW_COMPLETE`. |
| R1-S4 | Architecture | medium | Define the feature→`element_fqn` mapping convention (e.g. synthetic `feature:<feature_id>` fqn) so post-run feature-level verdicts and Phase-2 element-level verdicts are comparable (OQ-9). | `element_fqn` is element-scoped (`module.Class.method`); "feature name → element_fqn" without a rule makes FR-13 "same code at different triggers" produce non-comparable verdicts. | "## Risks / watch-items" → Altitude (OQ-9) | Documented mapping + test asserting a feature verdict and an element verdict share a resolvable key. |
| R1-S5 | Data | medium | Specify selection/precedence when the `prime-context-seed*.json` glob matches multiple files (latest by mtime? merge? error?) and how feature-id collisions across seeds resolve. | Step 1 globs `prime-context-seed*.json`; multi-batch runs can write several. Ambiguous selection yields wrong requirement text → wrong verdicts. | Step 1 "Requirement loader" | Fixture with 2 seed files → deterministic, documented resolution; collision test. |
| R1-S6 | Ops | medium | Pin the escalation-budget config: where it is read from (`MicroPrimeConfig`? env `STARTD8_SCR_*`? CLI?), default values for max-features and max-token-cost, and the single enforcement point that records `not_reviewed` reasons. | "Cost creep" is a headline risk but Step 4/Risks give no concrete knobs or defaults; without them the cap is unenforceable and untestable. | "## Risks" → Cost creep; Step 4 | Test: budget=N stops at N reviews and logs a `not_reviewed` reason for the rest (no silent caps). |
| R1-S7 | Risks | medium | Define the on-parse-failure path for the reviewer: `validate_semantic_verification_json` returns `(False, err)` on bad JSON — does the SCR retry once, mark `inconclusive`, or escalate? | Step 4 invokes the validator but never says what happens on `(False, ...)`; Haiku JSON noise is explicitly flagged as a risk. | Step 4 "Reviewer" | Malformed agent output → `inconclusive` with reason (or one bounded retry), never an unhandled exception. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Security | low | Have the rubric delimit/quote untrusted reviewed content (generated files, requirement text) and instruct the agent to ignore embedded instructions, to resist prompt-injection that flips the verdict. | Step 3/5 embed generated code + requirement text into the prompt; a hostile or accidental "ignore previous instructions / mark pass" comment in generated code could steer a cheap Haiku reviewer. | Step 5 "Rubric"; Step 3 "Input assembly" | Injection fixture (file with an embedded "return pass" instruction) does not flip a genuine `fail` to `pass`. |

#### Review Round R1 (prose pass) — claude-opus-4-8 — 2026-06-03

Plan-side architectural review (S-prefix). Anchored to plan steps/modules; orchestrator triages later.

- **S-R1-1 — SA→SCR coupling breaks the Service Assistant's "never block the pipeline" contract
  (step 9 / FR-12).** The SA is a one-shot, fast, post-run hook that explicitly never blocks the
  pipeline and exits 0. Step 9 has the SA *trigger* the SCR, which makes **N LLM calls** (slow,
  $). Running that inline turns the post-run hook into a multi-minute, paid step in the pipeline's
  tail. **Fix:** specify the SCR as a **detached/async** step the SA *launches* (or a separate
  invocation), with the SA triage artifact referencing the compliance report as `pending` and a
  later `SEMANTIC_REVIEW_COMPLETE` event reconciling it. Add the trigger-mode decision to the plan.

- **S-R1-2 — SCR has no idempotency/verdict-cache story; re-scan = full re-pay (steps 1, 9).** The
  SA is idempotent via `service-assistant-cursor.json`; a second SA scan of the same run is a
  no-op. But the SCR makes paid agent calls — if the SA re-triggers it (or it's re-invoked), step
  1/9 don't say verdicts are cached. **Fix:** cache `SemanticVerificationResult` keyed by
  `(run_id, feature_id, code_checksum)` so re-runs are free unless the code changed; mirror the SA
  cursor pattern. Add to the reuse map and Verification.

- **S-R1-3 — `semantic-compliance-report.json` (step 7 / FR-9) needs a versioned JSON Schema like
  the SA triage artifact got.** It is consumed by the SA (FR-12) and a future gate (FR-14), so the
  contract must be pinned (schema_version, per-feature verdict/confidence/issues, triage+escalation
  decisions, `requirement_text_reviewed`, `not_reviewed` reasons). **Fix:** add a schema doc
  (`SEMANTIC_COMPLIANCE_REPORT_SCHEMA.md`) as a step-7 deliverable, mirroring the SA's
  `TRIAGE_SCHEMA.md` v1.0.

- **S-R1-4 — No plan step verifies the requirement→feature join (the F-R1-3 hazard).** The reuse
  map lists "Requirement text → `prime-context-seed*.json`" but no step validates the join is
  correct, and the report has no field to surface join confidence. **Fix:** add a step-1 sub-step
  that corroborates the join (target/generated file overlap) and a `requirement_join_confidence`
  (or `inconclusive` reason) field in the report; add a Verification checkbox.

- **S-R1-5 — Feature→`element_fqn` collapse (step 5) bakes in OQ-9 and makes verdicts non-self-
  describing.** Step 5 stuffs a feature name into the element-scoped `element_fqn`, so a large
  multi-element feature gets one verdict for many elements, and the Phase-2 in-run (true element)
  path can't be reconciled with post-run output. **Fix:** add an explicit
  `review_granularity: "feature"|"element"` field to the report so verdicts are self-describing and
  comparable across the two phases; note the collapse rule for multi-element features.

#### Review Round R2 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:33:00 UTC
- **Scope**: Second pass (fresh reviewer). Deduped against both R1 rounds (`R1-S*` and `S-R1-*`). Goes deeper into ground neither R1 covered — multi-language scope, reuse of existing cost infrastructure, decoding determinism — plus second-order effects of already-proposed R1 items (async detach, verdict cache, false-PASS budget). Anchored to verified code (`prime_postmortem.py` `FeaturePostMortem`/`CostSummary`, `model_catalog.py`).

**Executive summary**

- **Multi-language blind spot (high, novel):** Both R1 rounds implicitly assume Python. `FeaturePostMortem` carries no `language`, and the rubric (`prompts.py`) + `element_fqn` convention are Python-shaped — yet the SDK supports 6 languages. A Go/Vue/Java feature would be reviewed with a Python-anchored rubric.
- **Cost-infra reuse (medium, Mottainai):** the escalation budget can reuse the existing `CostTracker`/`BudgetManager` and per-feature `cost_usd`/`CostSummary` rather than a bespoke token counter — extends R1-S6 (config) with the actual mechanism.
- **Second-order effect of S-R1-1 (medium):** if the SCR is detached/async (as S-R1-1 proposes), the report write and the SA fold now race — needs atomic write + a `pending→complete` status, else SA reads a partial/missing report.
- **Second-order effect of F-R1-1/FR-5a (medium):** even after fixing suspicion ranking, the bounded PASS sample can be starved if it draws from the same escalation budget as suspects — reserve a dedicated quota.
- **Determinism gap (medium):** the reviewer decoding temperature/seed is unspecified; without low-temp determinism the S-R1-2 verdict cache is unsound and the future θ gate (F-R1-4) is uncalibratable.
- Strong convergence between the two R1 rounds (altitude: R1-S4≈S-R1-5; Kaizen/advisory: R1-F3≈F-R1-4) — flagged in Endorsements for triage priority.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Make language a first-class input: propagate per-feature `language` into the rubric selection (`prompts.py`), the `element_fqn` convention, and scoring; provide per-language rubric variants or explicitly scope v1 to Python. | `FeaturePostMortem` has no `language` field and the SDK supports 6 languages (Python/Go/Node/Vue/Java/C#). A Python-anchored rubric reviewing a Go/Vue feature yields invalid verdicts; neither R1 round caught this. | Module layout `prompts.py`; Step 5 "Rubric" | Review a non-Python feature fixture; assert a language-appropriate rubric is selected and the verdict is not Python-biased. |
| R2-S2 | Ops | medium | Enforce the escalation budget by reusing `CostTracker`/`BudgetManager` and the existing per-feature `cost_usd` / `CostSummary` accounting rather than a new token counter. | Mottainai: per-feature `cost_usd` and `CostSummary` already exist in the post-mortem; the budget can debit the same tracker so `scr.cost_usd` reconciles with the run cost. Extends R1-S6 (which only asked for config knobs). | "## Reuse map" (add row); "## Risks" Cost creep | Test: SCR reviews debit a shared `CostTracker`; budget stop matches `CostSummary` totals. |
| R2-S3 | Risks | medium | Specify atomic report persistence + a `status: pending|complete` field so a detached SCR (per S-R1-1) never lets the SA fold read a partial or missing `semantic-compliance-report.json`. | Second-order effect of S-R1-1's async-detach fix: Step 9 SA fold and the detached writer race. Atomic write-rename + status closes it. | Step 9 "SA orchestration"; Step 7 | Concurrency test: SA fold during an in-flight SCR sees `pending`, not malformed JSON. |
| R2-S4 | Risks | medium | Reserve a dedicated PASS-sample quota (FR-5a) separate from the suspect escalation budget (FR-5) so false-PASS sampling is never starved when suspects fill the budget. | Complements F-R1-1 (ranking) with the budgeting interaction: a noisy run could consume the whole budget on suspects, zeroing the run-018-class safety net. | Steps 2–3 "pick escalations + bounded PASS sample" | Test: a budget-saturating suspect set still reviews the reserved PASS sample count. |
| R2-S5 | Validation | medium | Pin the reviewer's decoding to deterministic settings (temperature 0 / fixed seed where supported) and record them in `prompts.py` / the report. | Determinism makes the S-R1-2 verdict cache sound (same inputs → same verdict) and the future θ gate (F-R1-4 / OQ-8) calibratable; today temp/seed are unspecified. | Step 4 "Reviewer"; Step 5 | Test: identical inputs produce identical verdict+confidence across two invocations. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S6 | Architecture | low | If FR-11 cross-feature grouping stays in the SCR (vs F-R1-ADV-1's challenge), reuse the existing `CrossFeaturePattern` dataclass and emit into the report's pattern list rather than a parallel structure the Kaizen loop must reconcile. | `generate_kaizen_suggestions` already consumes `cross_feature_patterns` gated at frequency≥2; a second parallel pattern store doubles the surface and risks divergence. | Step 8 "Feedback"; Reuse map | Test: SCR-emitted patterns are consumed by `generate_kaizen_suggestions` without a new code path. |

**Endorsements & Disagreements**

**Endorsements** (untriaged prior items this round agrees with and builds on):
- S-R1-1 (async detach) — sound; R2-S3 depends on it being adopted.
- S-R1-2 (verdict cache by `(run_id, feature_id, code_checksum)`) — strong; R2-S5 (determinism) is its precondition.
- S-R1-3 (versioned report schema) — agree; pair with R2-S3's `status` field.
- S-R1-4 (requirement→feature join corroboration) — agree; highest-value robustness item across both rounds.
- Convergence signal: R1-S4 (altitude) and S-R1-5 (`review_granularity` field) are the same concern from two reviewers — prioritize in triage.

**Disagreements**: none. (R2 found no prior item worth rejecting; all are complementary.)

#### Review Round R3 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:41:00 UTC
- **Scope**: Third pass (fresh reviewer). Focuses on missing context window protections, robust failure handling during post-mortem triage, and lifecycle management for Kaizen feedback.

**Executive summary**

- **Context window vulnerability (high):** The input assembly (Step 3) lacks a truncation strategy or a `max_input_tokens` limit. A large feature will easily breach context windows or cause massive cost spikes upon escalation.
- **Kaizen hint staleness (high):** Step 8 does not describe how to handle previously emitted Kaizen hints when a feature successfully passes semantic review in a subsequent run. Stale hints will permanently pollute the context loop.
- **Unbounded response risk (medium):** Step 4 lacks a strict `max_tokens` limit for the LLM response. Hallucinations or malformed loops could severely inflate costs.
- **Missing triage fallback (medium):** Step 2 assumes `prime-postmortem-report.json` is always present. A failed AST parse or crashed post-mortem step leaves SCR with no signals.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Architecture | high | Define a truncation strategy or strict `max_input_tokens` budget for `generated_files` + requirement text during input assembly, with a degradation path to `inconclusive`. | Unbounded file inclusion exposes the LLM call to context-window overflow and unexpected cost surges. `engine.py` truncates element-level prompts, but this feature-level wrapper has no specified protection. | Step 3 "Input assembly" | Test: Pass a massively oversized file payload and assert the SCR gracefully truncates it or returns `inconclusive` without crashing. |
| R3-S2 | Ops | high | Add a sub-step to prune or invalidate prior Kaizen hints for a feature ID when it receives a `pass` verdict. | If a feature fails in Run A and receives a Kaizen hint, then passes in Run B, retaining the old hint pollutes the context loop for future iterations unnecessarily. | Step 8 "Feedback" | Unit test: A `pass` verdict actively emits a tombstone or clears the feature's prior entries in `kaizen-suggestions.json`. |
| R3-S3 | Interfaces | medium | Specify the fallback behavior when `prime-postmortem-report.json` fails to generate or is missing. | If the post-mortem crashed, the triage signals are absent. SCR should have a defined response (e.g., abort review entirely, or gracefully mark features `postmortem_unavailable`). | Step 2 "Triage" | Test: Execute SCR against a run missing the post-mortem report and verify it exits gracefully without an unhandled exception. |
| R3-S4 | Risks | medium | Add a strict `max_tokens` configuration to the `agenerate` reviewer call. | Because the expected schema is concise JSON, an unbounded output limit risks severe cost inflation from model hallucination loops. | Step 4 "Reviewer" | Configuration test verifies the presence of an explicit `max_tokens` (e.g. 1024) on the generation call. |

**Endorsements & Disagreements**

**Endorsements**:
- R2-S1 (Multi-language input) — fully agree. Expanding the architecture to 6 languages is critical.
- R2-S3 (Atomic write) — essential for asynchronous SA integration.
- R1-S1 (Serialization consistency) — strong fix for the `verification` envelope asymmetry.

**Disagreements**: none.

#### Review Round R4 — claude-opus-4-8 — 2026-06-03

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-03 17:43:00 UTC
- **Scope**: Fourth pass (fresh reviewer). Focuses on API resilience, escalation termination, reporting safety, and bounding noise at scale.

**Executive summary**

- **Provider outage fragility (high):** Step 4 hardcodes `SEMANTIC_VALIDATOR=Haiku`. If Anthropic has an outage or rate limits (429/529), the post-run compliance loop breaks. A cross-provider fallback strategy for the cheap tier is missing.
- **Unbounded escalation state (medium):** Step 4 states "escalate to Sonnet on fail/low-conf" but doesn't define the terminal condition. If Sonnet also returns low-confidence, the state machine must explicitly terminate.
- **Report bloat and leakage (medium):** Step 7 persists the review output. Retaining full code snippets or un-redacted payload reflections in the JSON report risks leaking secrets to disk/OTel and inflating artifact size.

##### First pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Ops | high | Define an API rate-limit / outage fallback strategy for Step 4. If the primary `SEMANTIC_VALIDATOR` returns 429/529, fall back to an equivalent-tier model (e.g., `GEMINI_FLASH_LITE`) or implement a bounded backoff. | Without a fallback, a transient provider issue crashes the SCR and deprives the next run of Kaizen hints. | Step 4 "Reviewer" | Mock a 529 response from Anthropic and assert the SCR successfully completes the review using a fallback provider. |
| R4-S2 | Architecture | medium | Explicitly define the Sonnet escalation (CODE_REVIEW) as the terminal state. If the escalated model returns `inconclusive` or low-confidence, it is final. | Leaving the post-escalation state undefined risks implementers building recursive loops or throwing unhandled exceptions when the "smart" model also fails to achieve confidence. | Step 4 "Reviewer" | Unit test: Sonnet returns low-confidence; SCR accepts it as the final verdict without further escalation. |
| R4-S3 | Security | medium | Mandate that `semantic-compliance-report.json` strips raw code snippets and limits context reflections to bounded excerpts. | Storing the full reviewed code in the JSON report inflates artifact size (breaking telemetry pipelines) and risks persisting sensitive data. | Step 7 "Report" | Test: The generated report JSON size is bounded and does not contain the full contents of `generated_files`. |

**Endorsements & Disagreements**

**Endorsements**:
- R3-S1 (Token budgeting/truncation) — critical for cost control.
- R3-S2 (Pruning stale hints) — essential to prevent permanent prompt pollution.
- R2-S3 (Atomic write) — necessary for the SA integration.

**Disagreements**: none.

## Requirements Coverage Matrix — R1 (table pass)

> Analysis only (claude-opus-4-8, 2026-06-03). Maps each FR to plan coverage. `Partial`/`Gap` rows reference the S-suggestion that would close them.

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Requirement retrieval | Step 1; Step 3 | Partial | Multi-seed-file selection/precedence undefined (R1-S5). |
| FR-2 Design-intent enrichment | Step 3 | Full | — |
| FR-3 Generated-output retrieval | Step 3 | Full | — |
| FR-4 Cheap triage pass | Step 2 | Full | — |
| FR-5 Escalation budget | Step 2; Step 4 | Partial | No config source/defaults/enforcement point (R1-S6). |
| FR-5a False-PASS sampling | Step 2 | Partial | Sample size/selection not quantified (see F-suggestions). |
| FR-6 Semantic verdict production | Step 4 | Partial | Parse-failure path (R1-S7); round-trip envelope (R1-S1); fail-open/closed semantics undefined. |
| FR-7 Requirement-anchored rubric | Step 5 | Full | — (hardening only, R1-S8). |
| FR-8 Compliance score | Step 6 | Partial | Score formula unspecified (see F-suggestions); dedup is covered. |
| FR-9 Persisted artifact | Step 7 | Partial | Serialization round-trip hazard (R1-S1). |
| FR-10 Kaizen integration | Step 8 | Partial | Emits strings, not the structured suggestion-dict the loop consumes (R1-S2). |
| FR-11 Cross-feature semantic patterns | Step 8 | Partial | Grouping key for "same requirement/contract" undefined (see F-suggestions). |
| FR-12 SA orchestration (post-run) | Step 9 | Partial | New `EventType` enum member not called out (R1-S3). |
| FR-13 In-run hoist contract | Reuse map; Step 4 | Partial | Altitude bridge feature↔element undefined (R1-S4). |
| FR-14 Advisory by default | Design summary; Verification | Full | — |
| FR-15 Model-tier control | Step 4 | Full | — |
| FR-16 Observability | Step 10 | Partial | Metric/span names + units not specified (see F-suggestions). |

## Requirements Coverage Matrix — R1 (prose pass)

Reviewer (claude-opus-4-8) mapping of plan steps → requirements. **Gaps** = requirements with weak/no
plan coverage; **Risks** = plan steps that under-specify a requirement.

| Requirement | Plan coverage | Assessment |
|-------------|---------------|------------|
| FR-1 retrieval | step 1 | **Risk** — join key unspecified, no corroboration (S-R1-4) |
| FR-2 design intent | step 3 | OK |
| FR-3 output retrieval | step 3 | **Gap** — no secret redaction (F-R1-5) |
| FR-4 cheap triage | step 2 | **Risk** — circular signal (F-R1-1) |
| FR-5 / FR-5a budget + PASS sample | steps 2–3 | OK; sample size unquantified |
| FR-6 verdict | step 4 | OK |
| FR-7 rubric | step 5 | OK |
| FR-8 score | step 6 | **Gap** — no capability KPI (F-R1-2) |
| FR-9 report | step 7 | **Risk** — no versioned schema (S-R1-3) |
| FR-10 Kaizen | step 8 | **Risk** — auto-injection vs "advisory" (F-R1-4) |
| FR-11 cross-feature | step 8 | OK — but see F-R1-ADV-1 (may belong in post-mortem) |
| FR-12 SA orchestration | step 9 | **Risk** — blocking/coupling (S-R1-1) |
| FR-13 in-run hoist | reuse map | OK; granularity caveat (S-R1-5) |
| FR-14 advisory/gate | step 4/Verification | OK |
| FR-15 model tiers | step 4 | OK |
| FR-16 observability | step 10 | OK |
| *(cross-cutting)* idempotency | — | **Gap** — no verdict cache (S-R1-2) |

## Requirements Coverage Matrix — R2

> R2 (claude-opus-4-8) — incremental view focused on what R2 newly surfaced; prior R1 matrices remain authoritative for items they covered. Lists only requirements whose assessment changes in light of R2.

| Requirement | Plan coverage | R2 assessment |
|-------------|---------------|---------------|
| FR-5 / FR-5a budget + PASS sample | steps 2–3 | **Risk** — PASS sample can be starved by the shared escalation budget (R2-S4); reserve a dedicated quota |
| FR-6 verdict | step 4 | **Risk** — decoding determinism (temp/seed) unspecified, undermining the S-R1-2 cache and the θ gate (R2-S5) |
| FR-7 rubric | step 5 | **Gap** — rubric/`element_fqn` assume Python; no `language` propagation for the 6-language SDK (R2-S1) |
| FR-11 cross-feature | step 8 | **Risk** — if kept in SCR, reuse `CrossFeaturePattern` rather than a parallel store (R2-S6) |
| FR-16 observability | step 10 | **Partial** — `scr.cost_usd` should reuse `CostTracker`/`CostSummary` for reconciliation (R2-S2) |
| *(cross-cutting)* async write | step 9 | **Gap** — detached SCR (S-R1-1) needs atomic write + `pending|complete` status (R2-S3) |
| *(cross-cutting)* multi-language | — | **Gap** — no language dimension anywhere in plan or requirements (R2-S1 / R2-F1) |

## Requirements Coverage Matrix — R3

> R3 (claude-opus-4-8) — incremental view. Prior matrices remain authoritative for items they covered.

| Requirement | Plan coverage | R3 assessment |
|-------------|---------------|---------------|
| FR-3 Generated-output retrieval | step 3 | **Risk** — input payload lacks token budget or truncation boundaries; no filtering of third-party boilerplate (R3-S1 / R3-F1) |
| FR-4 Cheap triage pass | step 2 | **Gap** — behavior on missing/failed post-mortem report is undefined (R3-S3) |
| FR-6 Semantic verdict production | step 4 | **Risk** — agent response generation lacks strict `max_tokens` limit, inviting runaway cost (R3-S4) |
| FR-8 Compliance score | step 6 | **Gap** — scoring impact of `inconclusive` verdict is unspecified (R3-F3) |
| FR-10 Kaizen integration | step 8 | **Gap** — no lifecycle management for stale hints; no safety net for hallucinated `suggested_fix` syntax breaking builds (R3-S2 / R3-F2) |

## Requirements Coverage Matrix — R4

> R4 (claude-opus-4-8) — incremental view. Prior matrices remain authoritative for items they covered.

| Requirement | Plan coverage | R4 assessment |
|-------------|---------------|---------------|
| FR-6 Semantic verdict production | step 4 | **Gap** — missing cross-provider fallback on API outage (R4-S1); terminal state of escalation undefined (R4-S2) |
| FR-9 Persisted artifact | step 7 | **Risk** — report persists raw code, risking bloat and secret leakage (R4-S3) |
| FR-11 Cross-feature semantic patterns | step 8 | **Risk** — absolute threshold (≥2) spams large runs; needs relative bound (R4-F2) |
| FR-14 Advisory by default, gating opt-in | step 4 | **Risk** — runaway `inconclusive` verdicts silently degrade the gate; needs a bounds limit (R4-F1) |
