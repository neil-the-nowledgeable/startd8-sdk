# End-to-End Cap-Dev-Pipe Multi-Model Comparison — Requirements

**Version:** 0.3 (Post-CRP triage — R1–R4 dispositions applied)
**Date:** 2026-06-01
**Status:** Draft
**Author:** neil (with Claude)
**Extends:** `PRIME_MODEL_COMPARISON_REQUIREMENTS.md` v0.2 (prime-contractor-stage-only comparison)
**Paired plan:** `E2E_PIPELINE_MODEL_COMPARISON_PLAN.md` v1.0

---

## 0. Planning Insights (Self-Reflective Update)

> Planning against the real `.cap-dev-pipe` scripts revealed that the headline goal — "vary the
> model at *every* stage" — is partly infeasible today, because the pipeline spans **two tools** and
> only one exposes a model knob. The orchestration seam, however, already exists.

| # | v0.1 Assumption | Planning Discovery | Impact |
|---|-----------------|--------------------|--------|
| D1 | FR-2: thread one model through **every** LLM stage | **contextcore** `polish`/`analyze-plan`/`init-from-plan` expose **no `--model` flag**; only the **startd8** stages do | FR-2 **infeasible as written**. v1 varies the model across the model-controllable startd8 stages (plan-ingestion + prime); the contextcore manifest/polish preamble runs **once, shared, model-independent**. True all-stage variation is deferred to a contextcore change (cross-repo). |
| D2 | FR-7: harness invokes the 3 scripts in sequence | **`run-atomic.sh` already chains** cap-delivery → plan-ingestion → prime → postmortem | Reuse/parameterize `run-atomic.sh` (or its sub-scripts); don't re-sequence. FR-7 simplified. |
| D3 | "the pipeline" is one tool | Stages split across **contextcore** (cap-delivery) + **startd8** (ingestion, prime), both orchestrated by `run-atomic.sh` | Model threading is per-tool; the pipe is the seam (your point). Contextcore = no knob; startd8 = config/flags. |
| D4 | OQ: plan-ingestion model unknown | plan-ingestion is LLM-driven via config keys **`assessor_agent` + `transformer_agent`** (default Claude Sonnet) | plan-ingestion model is overridable via config. Confirmed in scope. |
| D5 | all pre-prime stages are LLM-driven | **`enrich-seed.py` is zero-LLM-cost** (deterministic DomainPreflightWorkflow); `init-from-plan` has a regex fallback | Enrichment is **not** a model-varying stage — excluded from the comparison. |
| D6 | a model knob exists somewhere | **No `--model` anywhere** in `run-atomic.sh`/sub-scripts, and **no global `STARTD8_*MODEL` chokepoint** | Must **add `--model`** at the orchestration layer that sets plan-ingestion config agents + prime `--lead-agent`/`--drafter-agent`. |

**Resolved open questions:**
- **OQ-1/OQ-3 → No model param today; no global chokepoint.** Add `--model` at the orchestration
  layer (`run-atomic.sh` / new `compare-models-e2e`), threading to plan-ingestion config
  (`assessor_agent`/`transformer_agent`) + prime (`--lead-agent`/`--drafter-agent`).
- **OQ-2 → Stage LLM/model map:** model-controllable = **plan-ingestion** (assessor/transformer) +
  **prime** (lead/drafter). Deterministic / no-knob = **enrich-seed** (zero LLM), **contextcore**
  polish/analyze/init (no `--model`).
- **OQ-4 → `run-atomic.sh` already chains** all stages + postmortem. Reuse it.
- **OQ-5 → Cost:** prime from `prime-result.json` `total_cost_usd` (proven); plan-ingestion from
  `plan-ingestion-diagnostic.json` or cost-DB time-window; contextcore cost may be unattributable
  (mark as such). Serial execution makes time-window attribution safe.
- **OQ-6 → Isolation:** reuse `materialize_sandbox`/`SANDBOX_IGNORE`; per-model `{workdir,output}`;
  copy the shared provenance into each model's output for plan-ingestion to consume.
- **OQ-7 → Capability score:** reuse prime `cross_file_gate` verdict/score + feature completion;
  add plan-ingestion `ingestion_metrics` and contextcore `validation-report`/export-quality.
- **OQ-8 → New command `startd8 compare-models-e2e`** reusing `startd8.model_comparison` helpers.
- **OQ-9 → Yes**, add a `--global-budget` batch cap in addition to per-model/per-stage caps.

---

## 1. Problem Statement

We can now compare models on the **prime-contractor stage** (`startd8 compare-models`, validated on
run-012/013): all models share one frozen `prime-context-seed.json`, and only code generation varies.
That isolates generation capability but **does not** compare models end-to-end — the upstream
LLM-driven stages (plan polish, plan analysis, manifest init, plan-ingestion enrichment) are held
constant, produced by whatever model built that seed.

We want to compare how different models perform across the Capability Delivery Pipeline, from the
same frozen `plan.md` + `requirements.md`. **v1 scope (R1-F2):** the model is varied across the
**model-controllable startd8 stages** (plan-ingestion + prime); the **contextcore manifest/polish
stages run once, shared and model-independent** (they expose no model knob — D1). Full multi-model
variation across *every* stage is deferred to v2 (OQ-10). So v1 is "frozen inputs + shared manifest →
per-model generative span," not "every LLM stage varied."

| Stage | Tool | LLM-driven? | v1 treatment |
|---|---|---|---|
| CREATE / POLISH / ANALYZE-PLAN / INIT-FROM-PLAN / EXPORT | contextcore | some | **shared, run once** (no `--model`; v2 → OQ-10) |
| VALIDATE / schema checks | contextcore | no | deterministic, shared |
| enrich-seed | startd8 | **no (zero-LLM, D5)** | deterministic |
| plan-ingestion (assessor/transformer → seed) | startd8 | yes | **varied per model** |
| prime-contractor (lead/drafter → code) | startd8 | yes | **varied per model** (existing harness) |

## 2. Goals & Non-Goals

**Goal:** From identical frozen inputs, run the pipeline's **model-controllable generative span**
(plan-ingestion → prime) once per model in fully isolated trees — on top of a **single shared
contextcore manifest preamble** — then compare final deliverables + per-stage cost/quality/gate
outcomes. (Not "every stage varied" — that's v2; see §1 and FR-2.)

## 3. Requirements

### Conceptual framing (the critical one)
- **FR-1** *(corrected — R1-F1)* Inputs (`plan.md` + `requirements.md`) are **identical and frozen**
  across all models. In v1 the **contextcore manifest/polish/analyze/init artifacts are also shared**
  (one contextcore run feeds every model — NOT per-model). Divergence begins at **plan-ingestion**:
  each model produces its **own** enriched seed and then its **own** generated code. So v1 runs
  N pipelines that share a frozen input *and* a shared manifest, diverging only across the
  plan-ingestion → prime span — **not** byte-identical prompts at every stage, and **not** per-model
  polished plans (that is v2, OQ-10). The report must state this framing so results aren't misread.

### Model propagation
- **FR-2** *(narrowed — D1/D4/D6)* A single `--model provider:model` override is threaded, at the
  orchestration layer, through the **model-controllable startd8 stages**: plan-ingestion (config
  `assessor_agent` + `transformer_agent`) and prime contractor (`--lead-agent` + `--drafter-agent`).
  The **contextcore** preamble (polish/analyze/init) exposes no model knob and runs **once, shared,
  model-independent** (D1). Varying contextcore stages is deferred until that tool exposes a model
  flag (cross-repo) — see OQ-10.
- **FR-3** Deterministic stages are unaffected by the model: validate, export, schema checks, and
  **`enrich-seed.py` (zero-LLM, D5)**. These are excluded from the comparison.

### Isolation
- **FR-4** Each model runs in its own isolated **project copy** AND its own **pipeline-output tree**
  (`pipeline-output/<model-slug>/`). No two models share a project root, pipeline-output dir, or
  manifest/inventory/ContextCore state.
- **FR-5** *(strengthened — R2-F3)* A model's failure at any stage does not corrupt or block other
  models; each is independently recoverable. Each model+stage records a status from a fixed enum
  (`not_started`, `skipped_shared`, `success`, `failed`, `timed_out`, `invalid_model`,
  `budget_exceeded`, `artifact_missing`, `invalid_comparison`), and the harness emits a **partial
  report** covering completed models. The one exception: if the **shared preamble** fails, the batch
  aborts (nothing downstream can run).

### Execution
- **FR-6** Execution is **serial** in v1 (one model's full pipeline completes before the next).
  Parallel is a non-goal but the design must not preclude it.
- **FR-7** *(simplified — D2)* The harness **reuses the existing `run-atomic.sh` orchestrator**
  (which already chains cap-delivery → plan-ingestion → prime → postmortem), parameterized with the
  per-model `--model`, rather than re-sequencing the sub-scripts itself. v1 may run the shared
  contextcore preamble once and only the startd8 stages per model (see plan S1–S4).

### Scoring & reporting
- **FR-8** *(split — R1-F3)* Capture outcomes at two levels: **(a) batch-level / shared** signals from
  the one contextcore preamble (validation-report, export quality) recorded **once**; **(b) per-model**
  signals for the varied stages only — plan-ingestion (`ingestion_metrics`, duration, cost) and prime
  (`cross_file_gate` verdict/score, feature completion, `total_cost_usd`, tokens, duration). Do **not**
  record polish/analyze verdicts per model (they are shared in v1).
- **FR-9** *(cost honesty + disclaimers — R1-F4, R1-F7, R2-F9)* The report (markdown + JSON, reusing
  the existing comparison shape) must:
  - carry **three cost fields** per model — `cost_attributable_usd` (plan-ingestion + prime),
    `cost_shared_preamble_usd` (allocated or `null`), `cost_total_loaded_usd` — and **rank on
    `cost_attributable_usd`**, with fully-loaded shown as a footnote;
  - express the **capability score** with a documented `score_breakdown` (component values, weights,
    missing-component penalties, source artifact paths) and a `capability_prime_only` column for
    apples-to-apples control against `compare-models`;
  - state in its header: `comparison_mode`, the **single-run/indicative** caveat (NR-3), and the
    **shared-manifest** disclaimer, with a pointer to `compare-models` as the prime-only control.
- **FR-10** Reuse the existing `startd8.model_comparison` cost/gate extraction patterns; add a
  per-stage extractor layer on top.

### Config & invocation
- **FR-11** User specifies: frozen plan + requirements paths, the list of models, and a batch output
  root. The harness creates per-model isolated trees automatically.
- **FR-12** A dry-run prints the per-model, per-stage command sequence without executing.
- **FR-13** Likely a new command (`startd8 compare-models-e2e`) or an extension of
  `compare-models`, sharing the existing module's helpers.

### Correctness & safety (added from CRP R1–R2)
- **FR-14** *(model-pin verification — R1-F5)* After each model-controllable stage, persist the
  **`resolved_agent_specs`** (assessor, transformer, lead, drafter) in the batch manifest; the run
  **fails** if any resolved spec differs from the `--model` under test. Guards the silent
  `Models.CLAUDE_SONNET_LATEST` fallback in `_resolve_assessor_agent`/`_resolve_transformer_agent`.
- **FR-15** *(batch integrity — R1-F8)* If two models produce an **identical `prime-context-seed.json`
  hash** post-ingestion, mark the run `invalid_comparison` (likely a model-pin failure or shared-state
  contamination collapsing E2E to prime-only).
- **FR-16** *(batch manifest — R2-F1; folds R3-F2 input hashes, R4-F8 versions, R2-F9 breakdown)* Emit
  `batch-run-manifest.json`: `schema_version`, `comparison_mode`, **frozen input copies + checksums**
  (`batch/_inputs/`), shared-preamble artifact hashes, per-model `resolved_agent_specs`, per-stage
  status + `cost_source`/`cost_confidence`, `score_breakdown`, tool/SDK versions + git SHA, and report
  paths. This manifest is the authoritative contract behind the report.
- **FR-17** *(preflight — R2-F2)* Before the shared preamble: validate every `provider:model` spec
  (provider credentials/availability), require ≥2 distinct valid models, and reject filesystem **slug
  collisions** after normalization. Fail fast — before any paid work.
- **FR-18** *(timeouts — R2-F4)* Support a per-stage (or batch) timeout; a timeout marks the
  stage/model `timed_out`, records elapsed time, and continues per FR-5. Reuse the existing
  `model_comparison.run_command(timeout=…)` pattern.
- **FR-19** *(log redaction — R2-F6)* Any stdout/stderr tails, command lines, config snapshots, or env
  summaries persisted into reports/manifest must redact API keys, tokens, and known secret env values.
- **FR-20** *(no-cost smoke test — R2-F8)* Ship a mock-provider/deterministic-fixture path exercising
  shared-preamble placeholder → per-model ingestion → prime extraction → report generation with **no
  external API calls**, for CI regression coverage.

### Tournament integration (added 2026-06-23 — staged-tournament frame)

- **FR-21** *(Round-1 advancement verdict — tournament gate)* Beyond ranking, the harness MUST emit a
  per-model **advancement verdict** for this round: a boolean `advanced` + `advancement_reason`,
  computed against a **Round-1 gate** defined as explicit, documented criteria over signals the run
  already produces (e.g. prime `cross_file_gate` pass, plan-ingestion success, `comparison_validity != invalid`,
  capability score ≥ a configurable `--advance-threshold`). The gate is **per-round** (Round 2/3 define
  their own — the user's "different bars" decision), so the threshold + criteria are parameters, not
  hardcoded. The verdict is persisted in `batch-run-manifest.json` (`advancement: {model: {advanced, reason, ...}}`)
  and surfaced in the report, so a downstream tournament orchestrator can read which models clear Round 1
  and advance. Default roster is the flagship set (`FLAGSHIP_MODELS`); a non-flagship model is gated the
  same way. Degrade-honest: a model whose gate inputs are missing is `advanced: false` with reason
  `inputs_missing`, never silently advanced.

## 4. Non-Requirements

- **NR-1** No parallel execution in v1.
- **NR-2** No per-stage model maps in v1 (single model across all stages); design leaves room.
- **NR-3** No repeat-sampling in v1 (single end-to-end run per model; documented as indicative).
- **NR-4** No modification of pipeline stage logic beyond what's needed to thread the model through.
- **NR-5** No new quality metrics inside stages — only aggregation of what stages already emit.
- **NR-6** Does not replace the prime-stage-only `compare-models` (complementary, narrower tool).

## 5. Open Questions

OQ-1…OQ-9 from v0.1 were **resolved during the planning pass** — see §0. Remaining/new:

- **OQ-10** (cross-repo) Will **contextcore** expose a `--model` flag on `polish`/`analyze-plan`/
  `init-from-plan`? If so, v2 can vary the *entire* pipeline; until then the contextcore preamble is
  shared/model-independent.
- **OQ-11 → RESOLVED (R1-F6): yes, without script surgery.** `run-plan-ingestion.sh` already
  post-patches `EFFECTIVE_CONFIG` (the `--providers`/`--profile`/kaizen pattern); the harness injects
  `assessor_agent`/`transformer_agent` the same way after `resolve-provenance.py`, then FR-14 asserts
  the resolved specs match. Acceptance: dry-run shows assessor/transformer == CLI `--model`.
- **OQ-12** Is contextcore per-stage cost recoverable at all (separate tool), or must its cost be
  reported as "unattributed/shared"?
- **OQ-13** Repeat-sampling design for end-to-end runs (deferred from v1, as in the prime-stage tool).

---

*v0.2 — Post-planning self-reflective update. 1 requirement narrowed from infeasible (FR-2: every
stage → model-controllable startd8 stages only), 1 simplified (FR-7: reuse `run-atomic.sh`), 1
clarified (FR-3: enrich-seed is zero-LLM), 9 open questions resolved, 4 new ones deferred.*

*v0.3 — Post-CRP triage (R1–R4, 33 F-suggestions). Accepted into v1: FR-1 contradiction fixed, §1/Goals
truth-in-labeling, FR-5 status enum, FR-8 batch-vs-per-model split, FR-9 cost-honesty + score breakdown
+ disclaimers, new FR-14 (model-pin verify), FR-15 (batch integrity), FR-16 (manifest, folding input
hashes/versions/breakdown), FR-17 (preflight), FR-18 (timeouts), FR-19 (redaction), FR-20 (smoke test);
OQ-11 resolved. Deferred to v2 backlog (Appendix B): report-only, selective retry, readiness preflight,
transient retry, CSV, decision guide, artifact index, run profiles, telemetry, exit codes, extractor
registry, worked example, preamble reuse, replay bundle, retention. Dispositions in Appendix A/B.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed
- **Truth-in-labeling / FR-1 contradiction** — resolved (FR-1, §1, Goals rewritten). Future reviewers: do not re-raise.
- **Cost honesty** — resolved (FR-9 three-column model + attributable ranking).
- **Silent model fallback** — resolved (FR-14 + OQ-11 resolution).

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | FR-1 shared-manifest contradiction | composer-2.5 | Rewrote FR-1; divergence starts at plan-ingestion | 2026-06-01 |
| R1-F2 | §1 "every stage" → v1 scope | composer-2.5 | §1 para + stage table rewritten | 2026-06-01 |
| R1-F3 | FR-8 batch vs per-model split | composer-2.5 | FR-8 split into (a) shared / (b) per-model | 2026-06-01 |
| R1-F4 | FR-9 three cost columns + rank policy | composer-2.5 | FR-9 rewritten; rank on `cost_attributable_usd` | 2026-06-01 |
| R1-F5 | Model-pin verification | composer-2.5 | New **FR-14** | 2026-06-01 |
| R1-F6 | Resolve OQ-11 | composer-2.5 | OQ-11 marked resolved (config post-patch) | 2026-06-01 |
| R1-F7 | Report disclaimers (mode/indicative/shared) | composer-2.5 | Folded into FR-9 header reqs | 2026-06-01 |
| R1-F8 | Batch integrity seed-hash | composer-2.5 | New **FR-15** | 2026-06-01 |
| R2-F1 | Batch manifest | gpt-5.5 | New **FR-16** (backbone) | 2026-06-01 |
| R2-F2 | Model/slug validation | gpt-5.5 | New **FR-17** (preflight) | 2026-06-01 |
| R2-F3 | Stage status enum | gpt-5.5 | Folded into FR-5 | 2026-06-01 |
| R2-F4 | Timeouts | gpt-5.5 | New **FR-18** | 2026-06-01 |
| R2-F6 | Report redaction | gpt-5.5 | New **FR-19** | 2026-06-01 |
| R2-F8 | No-cost smoke test | gpt-5.5 | New **FR-20** | 2026-06-01 |
| R2-F9 | Score breakdown | gpt-5.5 | Folded into FR-9 + FR-16 | 2026-06-01 |
| R3-F2 | Frozen input archive + hashes | gpt-5.5 | Folded into FR-16 (`batch/_inputs/`) | 2026-06-01 |
| R4-F8 | Tool-version metadata | gpt-5.5 | Folded into FR-16 | 2026-06-01 |

### Appendix B: Rejected / Deferred Suggestions (with Rationale)

> "Deferred-v2" = sound idea, intentionally out of v1 scope (guards the non-goals against scope
> creep). Tracked here as cross-model memory so later reviewers don't re-propose for v1.

| ID | Suggestion | Source | Disposition & Rationale | Date |
|----|------------|--------|-------------------------|------|
| R2-F5 | Replay bundle | gpt-5.5 | Deferred-v2 — recovery ergonomics; depends on FR-16 manifest | 2026-06-01 |
| R2-F7 | Retention controls (`--keep-workdirs`) | gpt-5.5 | Deferred-v2 — disk ergonomics, not correctness | 2026-06-01 |
| R3-F1 | Report-only regeneration | gpt-5.5 | Deferred-v2 — iteration convenience; needs FR-16 | 2026-06-01 |
| R3-F3 | Selective retry / attempts | gpt-5.5 | Deferred-v2 — recovery workflow | 2026-06-01 |
| R3-F4 | Readiness preflight (disk/budget) | gpt-5.5 | Deferred-v2 — partial overlap with FR-17 (provider check kept) | 2026-06-01 |
| R3-F5 | Transient retry/backoff | gpt-5.5 | Deferred-v2 — resilience tuning | 2026-06-01 |
| R3-F6 | CSV summary export | gpt-5.5 | Deferred-v2 — interop nicety | 2026-06-01 |
| R3-F7 | Dry-run spend estimate | gpt-5.5 | Deferred-v2 — UX; FR-12 unchanged for v1 | 2026-06-01 |
| R3-F8 | Operator decision guide | gpt-5.5 | Deferred-v2 — report ergonomics (NR-3 caveat suffices for v1) | 2026-06-01 |
| R4-F1 | Artifact index (`ARTIFACTS.md`) | gpt-5.5 | Deferred-v2 — navigation; FR-16 manifest covers v1 | 2026-06-01 |
| R4-F2 | Run profiles | gpt-5.5 | Deferred-v2 — UX presets | 2026-06-01 |
| R4-F3 | Progress/OTel telemetry | gpt-5.5 | Deferred-v2 — observability | 2026-06-01 |
| R4-F4 | Exit-code policy | gpt-5.5 | Deferred-v2 — CI semantics (revisit when CI-consumed) | 2026-06-01 |
| R4-F5 | Stage extractor contract | gpt-5.5 | Deferred-v2 — abstraction earns value at v2 multi-extractor | 2026-06-01 |
| R4-F6 | Worked example acceptance artifact | gpt-5.5 | Deferred-v2 — pairs with FR-20 smoke test impl | 2026-06-01 |
| R4-F7 | Safe shared-preamble reuse | gpt-5.5 | Deferred-v2 — perf optimization; needs FR-16 hashes | 2026-06-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: composer-2.5
- **Date**: 2026-06-02 12:00:00 UTC
- **Scope**: Feature requirements quality — robustness, end-user value, dual-doc consistency (Feature Requirements)

**Executive summary**

- **FR-1 contradicts v1 shared preamble** — must distinguish frozen *inputs* vs shared *manifest* vs per-model generative artifacts.
- **§1 Problem Statement and Goals still claim "every LLM-driven stage"** — undermines v0.2 D1 correction; fix for reader trust.
- **FR-8** lists polish/plan-analysis signals as if per-model; in v1 they are batch-level once — scope or move to shared preamble section.
- **FR-9** lacks testable acceptance for cost columns and ranking policy when shared cost is unattributable.
- **New requirement** for model-pin verification closes silent Sonnet fallback risk (OQ-11).
- **End-user docs**: report must carry `comparison_mode`, statistical caveat (NR-3), and glossary separating this tool from `compare-models`.
- **OQ-11** can move to resolved with acceptance test referencing config injection pattern in `run-plan-ingestion.sh`.
- Align **Goals** with narrowed FR-2 (rename goal to "model-controllable pipeline span" or similar).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Architecture | critical | Rewrite **FR-1** third sentence: in v1, intermediate **manifest/polish/analyze/init artifacts are shared** (one contextcore run); only **plan-ingestion + prime** outputs diverge per model. Remove "its own polished plan" for v1 or qualify as v2-only. | Current text: "each model consumes its **own** upstream artifacts (its own polished plan, its own enriched seed)" conflicts with FR-2 shared preamble (D1) and plan S1. | §3 FR-1 | Reviewer checklist: FR-1 compatible with FR-2 without footnotes |
| R1-F2 | Architecture | high | Update **§1** stage table and paragraph ("vary the model at **every** LLM-driven stage") to state v1 scope: contextcore stages **fixed shared**; comparison spans plan-ingestion + prime; full-stage deferred (OQ-10). | Headline still promises full E2E multi-model though v0.2 table D1 already narrowed FR-2. | §1 Problem Statement | Doc lint: no "every LLM stage" without v1 qualifier |
| R1-F3 | Data | high | Split **FR-8**: (a) **batch-level** signals from shared preamble (`validation-report`, export quality) recorded once; (b) **per-model** signals for plan-ingestion + prime only. Drop per-model polish verdict unless v2. | FR-8: "polish quality verdict, plan-analysis complexity" implies per-model capture incompatible with shared S1. | §3 FR-8 | Report schema lists `shared_preamble` vs `models[]` sections |
| R1-F4 | Validation | high | Add acceptance criteria to **FR-9**: report includes `cost_attributable_usd`, optional `cost_shared_preamble_usd`, `cost_total_loaded_usd`; default rank uses attributable; footnote when shared cost is `null`/unattributed. | FR-9: "total end-to-end cost" is untestable without policy when OQ-12 applies. | §3 FR-9 | Fixture batch JSON validates column presence + rank rule |
| R1-F5 | Security | medium | Add **FR-14 (model verification)**: after each model-controllable stage, persist `resolved_agent_specs` (assessor, transformer, lead, drafter) in batch manifest; comparison **fails** if any differs from `--model` under test. | OQ-11 risk: `_resolve_assessor_agent` defaults to `Models.CLAUDE_SONNET_LATEST` when config missing. | §3 new FR-14 | Inject wrong config in test; harness must fail |
| R1-F6 | Interfaces | medium | Resolve **OQ-11** in §5: YES — harness patches `EFFECTIVE_CONFIG` after `resolve-provenance.py` (same injection pattern as `--providers` in `run-plan-ingestion.sh` lines 177–190); add acceptance bullet. | OQ-11 still open though implementation path is visible in cap-dev-pipe script. | §5 OQ-11 | Dry-run shows assessor/transformer equal CLI `--model` |
| R1-F7 | Ops | low | Extend **NR-3** / FR-9 report requirements: header must state single-run **indicative** results, **shared manifest** disclaimer, and pointer to `compare-models` for prime-only control. | End users otherwise treat one-shot E2E as production model selection. | §4 NR-3; §3 FR-9 | Sample report template review |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Risks | medium | Add **FR-15 (batch integrity)**: if two models produce identical `prime-context-seed.json` hash post-ingestion, mark run **invalid** (likely pin failure or shared-state contamination). | Catches false comparisons that look like E2E but collapse to identical prime inputs. | §3 new FR-15 | Test with forced identical config; expect invalid flag |

#### Review Round R2

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:40:00 UTC
- **Scope**: Feature requirements quick wins — observability, replayability, failure handling, operator ergonomics

**Executive summary**

- R1 catches the headline correctness problems; R2 adds requirements that make the feature supportable after users run it.
- Require a machine-readable batch manifest with schema versioning before report fields accrete informally.
- Add model/slug validation so invalid comparisons fail before paid stages run.
- Define partial-failure semantics: users should get a useful report even when one model or stage fails.
- Require replay bundles and sanitized config snapshots so failed comparisons can be reproduced without guesswork.
- Add timeout and retention controls to protect long-running and large-repo use cases.
- Treat captured logs/configs as security-sensitive and require redaction.
- Add mock-provider smoke coverage so the feature can be regression-tested without LLM spend.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | Add **FR-16 (batch manifest)**: each run emits `batch-run-manifest.json` with `schema_version`, `comparison_mode`, shared preamble artifact hashes, per-model stage statuses, command references, cost sources, and report paths. | FR-8 says capture per-stage outcomes and FR-9 says emit JSON, but neither defines a stable operational contract for downstream tooling or support. | §3 Scoring & reporting after FR-10 | JSON schema fixture validates required top-level and per-model keys |
| R2-F2 | Interfaces | high | Add **FR-17 (model and slug validation)**: before executing `run-cap-delivery.sh`, validate every `provider:model`, reject fewer than two distinct valid models, and reject filesystem slug collisions after normalization. | FR-11 lets users provide models, but does not define fail-fast behavior for invalid specs or path collisions. | §3 Config & invocation after FR-13 | CLI test with invalid provider and colliding slugs exits before creating batch outputs |
| R2-F3 | Risks | high | Strengthen **FR-5**: failures produce a partial report with per-stage status from a fixed enum (`success`, `failed`, `timed_out`, `artifact_missing`, `invalid_model`, `budget_exceeded`, `invalid_comparison`) and continue to later models unless the shared preamble fails. | Current FR-5 says failure does not block others, but does not specify user-visible output or shared-preamble exception. | §3 Isolation FR-5 | Simulate one model failure; report includes failed model row and subsequent model result |
| R2-F4 | Ops | medium | Add **FR-18 (timeouts)**: v1 supports a batch-level or per-stage timeout; timeout marks the stage/model failed, records elapsed time, and continues according to FR-5. | FR-6 serial execution protects cost attribution but increases hang risk; users need a bounded run. | §3 Execution after FR-6 | Test command with hanging mock stage records `timed_out` and exits nonzero only if all models fail |
| R2-F5 | Ops | medium | Add **FR-19 (replay bundle)**: for each model, persist sanitized replay artifacts: effective plan-ingestion config, prime command, cwd, selected env keys, artifact checksum list, and a copy/paste replay command file. | FR-12 dry-run prints commands, but after a real failed run users need exact reproduction state without re-reading terminal output. | §3 Scoring & reporting or Config & invocation | Fixture run writes `batch/<slug>/replay/` and excludes secret values |
| R2-F6 | Security | medium | Add **FR-20 (report redaction)**: any stdout/stderr tails, command lines, config snapshots, and env summaries stored in JSON/Markdown must redact API keys, tokens, credentials, and known secret env var values. | The E2E harness will persist more cross-tool logs than `compare-models`; reports can otherwise leak provider keys. | §3 Scoring & reporting | Inject fake `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`; report contains `[REDACTED]`, not raw value |
| R2-F7 | Ops | low | Add **FR-21 (retention controls)**: user can choose whether to keep per-model workdirs (`always`, `failed`, `never`) while preserving output artifacts and replay bundles. | FR-4 requires isolated project copies, but large repos make always-retain behavior costly for end users. | §3 Config & invocation | Successful run with cleanup removes workdir; failed run with `failed` retains workdir |
| R2-F8 | Validation | medium | Add **FR-22 (no-cost smoke test)**: implementation includes a mock-provider or deterministic fixture path that exercises shared preamble placeholder, per-model ingestion, prime extraction, and report generation without external API calls. | The feature crosses shell scripts and SDK code; without a cheap smoke test, regressions will be found only during paid runs. | New §3 Validation requirements or after FR-13 | CI test creates Markdown + JSON report for two mock models |
| R2-F9 | Data | medium | Add **FR-23 (score explainability)**: any composite capability score must include `score_breakdown` with component values, weights, missing-component penalties, and source artifact paths. | FR-9 asks for a final capability score, but users need to understand why the ranking changed between runs. | §3 Scoring & reporting after FR-9 | Fixture with missing ingestion metrics shows explicit penalty/source entry |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: FR-1's "own polished plan" conflict must be resolved before implementation to avoid invalid acceptance criteria.
- R1-F3: Shared preamble metrics must be separated from per-model metrics in the report schema.
- R1-F4: Cost field definitions and ranking policy are required for a defensible report.
- R1-F5: Persisted resolved agent specs are the right guard against silent default-model fallback.
- R1-F8: Seed hash comparison is a simple and effective invalid-comparison detector.

#### Review Round R3

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:43:00 UTC
- **Scope**: Feature requirements for report regeneration, selective retry, readiness checks, and operator-facing value

**Executive summary**

- R1/R2 cover correctness and supportability; R3 adds user workflow requirements for second runs, report fixes, and partial recovery.
- Require a report-only mode so extractor/report bugs can be fixed without rerunning paid LLM stages.
- Persist frozen input copies and hashes, not only derived shared preamble artifacts.
- Add selective retry and attempt numbering for one failed model or stage.
- Add readiness preflight checks so missing credentials, disk space, or budget ambiguity fail early.
- Define transient retry behavior so temporary 429/network failures do not become model-quality judgments.
- Add CSV export and human decision guidance for users who need quick model-selection decisions.
- Make dry-run more valuable by including readiness and estimated maximum spend.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Ops | high | Add **FR-24 (report-only regeneration)**: users can run a report-only command against an existing batch root to regenerate Markdown/JSON/CSV from persisted artifacts without invoking contextcore, plan-ingestion, or prime. | FR-9 requires reports, but users need to repair extraction/report formatting without paying for another model run. | §3 Scoring & reporting after FR-23 | Delete reports from fixture batch; report-only command recreates them and performs no stage commands |
| R3-F2 | Data | high | Add **FR-25 (frozen input archive)**: before the shared preamble, copy the exact input plan and requirements files into `batch/_inputs/` and persist checksums referenced by every report. | FR-1 says inputs are identical and frozen, but the requirement is not auditable if source files change after the run. | §3 Conceptual framing after FR-1 | Modify original input after run; report still points to archived input and original hash |
| R3-F3 | Risks | high | Add **FR-26 (selective retry)**: users can retry one model or one failed stage from an existing batch; retries create a new attempt directory and never overwrite previous attempt artifacts. | FR-5 and R2-F3 define partial failure, but not an operator path to recover from a flaky model without rerunning the whole batch. | §3 Execution or Isolation after FR-5/FR-6 | Failed model retry creates `attempt-002`; successful models remain unchanged |
| R3-F4 | Ops | medium | Add **FR-27 (readiness preflight)**: dry-run and real-run startup check provider credentials/config, writable batch root, approximate disk requirement, model count, and budget settings before shared preamble execution. | FR-11 lists inputs, but does not require early detection of the most common operator setup failures. | §3 Config & invocation after FR-13 | Missing credential or unwritable batch root exits before creating shared preamble |
| R3-F5 | Risks | medium | Add **FR-28 (transient retry policy)**: provider/network/rate-limit failures may be retried with bounded backoff; deterministic artifact failures are not retried automatically; retry count is reported per stage. | Without this distinction, transient infrastructure errors can be mistaken for model quality or hidden as generic failures. | §3 Execution after FR-18 | Mock transient failure succeeds on retry and records retry metadata |
| R3-F6 | Interfaces | low | Add **FR-29 (CSV summary export)**: emit `comparison-summary.csv` with one row per model and stable columns for model, status, stage statuses, capability score, cost fields, duration, and report/artifact paths. | FR-9 JSON/Markdown outputs are useful, but CSV is a low-effort interoperability win for spreadsheets and dashboards. | §3 Scoring & reporting after FR-9 | CSV row count equals model count and values match JSON payload |
| R3-F7 | Validation | medium | Add **FR-30 (dry-run spend/readiness output)**: `--dry-run` prints the planned command sequence plus readiness status, archived input paths, estimated maximum spend from budget flags, and warnings for unknown model pricing. | FR-12 only says command sequence; richer dry-run gives users the go/no-go information they need before paid execution. | §3 Config & invocation at FR-12 | Snapshot test verifies dry-run includes readiness and estimated spend sections |
| R3-F8 | Ops | low | Add **FR-31 (operator decision guide)**: Markdown report includes a concise interpretation section explaining when the result is actionable, inconclusive, or should be followed by prime-only comparison or repeat sampling. | NR-3 says single-run is indicative, but end users need concrete guidance at the point of decision. | §3 Scoring & reporting / §4 NR-3 | Fixture with close scores or failed stages emits an "inconclusive" caveat |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: The batch manifest is foundational for report-only regeneration and retry behavior.
- R2-F3: Fixed stage status enums are necessary for useful partial reports.
- R2-F5: Replay bundles provide the detailed reproduction material behind selective retry.
- R2-F8: A no-cost smoke test should cover the new report-only and CSV export paths.
- R1-F7: The report must warn users that a single E2E run is directional, not statistical proof.

#### Review Round R4

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:44:00 UTC
- **Scope**: Feature requirements for adoption ergonomics, artifact navigation, telemetry, CI semantics, and extension seams

**Executive summary**

- R1-R3 cover major correctness and recovery concerns; R4 proposes smaller requirements that improve adoption and long-term maintainability.
- Require an artifact index so users do not need to reverse-engineer the batch directory.
- Add run profiles to reduce flag overload for common use cases.
- Define progress/telemetry output for long serial comparisons.
- Specify exit codes so CI and scripts can distinguish invalid input, partial model failure, and shared preamble failure.
- Add an extractor extension contract to keep future contextcore-v2 changes localized.
- Require a worked example/sample output tree as part of acceptance.
- Add safe shared-preamble reuse guarded by input and tool hashes.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | medium | Add **FR-32 (artifact index)**: each batch emits `artifact-index.json` and `ARTIFACTS.md` listing shared and per-model artifacts with producer tool, stage, scope, path, checksum, and human description. | FR-16 batch manifest is machine-oriented; end users also need a navigable map of batch outputs. | §3 Scoring & reporting after FR-16 | Fixture batch index includes `_shared`, each model seed, prime result, and reports |
| R4-F2 | Interfaces | medium | Add **FR-33 (run profiles)**: CLI supports `--profile quick|standard|audit`; profiles expand to documented defaults for budgets, retention, replay detail, report detail, and validation strictness, while explicit flags override profile values. | The accumulated flags from R1-R3 improve control but create adoption friction; profiles provide low-hanging UX value. | §3 Config & invocation after FR-13 | CLI snapshot shows expanded profile defaults and override behavior |
| R4-F3 | Ops | medium | Add **FR-34 (progress and telemetry)**: the harness emits per-stage progress events and optional OTel spans containing batch id, comparison mode, model, stage, attempt, status, duration, and cost source. | FR-6 serial execution can take a long time; users need live operational feedback and post-run traces. | §3 Execution or Scoring & reporting | Mock run captures expected progress events or span attributes |
| R4-F4 | Risks | medium | Add **FR-35 (exit code policy)**: define stable CLI exit codes for all-success, completed-with-model-failures, invalid input/preflight failure, shared preamble failure, and internal harness error. | FR-5 partial failure behavior is not enough for CI; scripts need stable process-level semantics. | §3 Execution after FR-5 | CLI tests assert each representative scenario returns the documented code |
| R4-F5 | Architecture | medium | Add **FR-36 (stage extractor contract)**: per-stage metrics extraction uses named extractors with `stage_id`, `artifact_patterns`, `schema_version`, `extractor_version`, `confidence`, and structured warnings. | Future contextcore or prime artifact changes should not require rewriting orchestration/report code. | §3 Scoring & reporting after FR-10 | Fake extractor fixture contributes metrics and warnings to the report payload |
| R4-F6 | Validation | low | Add **FR-37 (worked example acceptance artifact)**: docs include a tiny plan/requirements pair, two mock models, expected command, expected output tree, and sample report snippets. | A runnable example reduces onboarding time and gives reviewers a concrete end-user workflow. | New validation/doc subsection | Example command runs without provider keys and matches documented output tree |
| R4-F7 | Ops | low | Add **FR-38 (safe shared-preamble reuse)**: users may opt into reusing a prior shared preamble only when input hashes, contextcore version, comparison mode, and shared artifact checksums match; otherwise reuse fails closed. | Iterating over model sets should not require repeated shared setup, but reuse must not weaken the frozen-input guarantee. | §3 Execution after FR-7 | Reuse succeeds for matching fixture and fails after changing input hash |
| R4-F8 | Data | low | Add **FR-39 (tool-version metadata)**: every report records startd8 version, contextcore CLI version if available, command source (`run-atomic.sh` vs sub-scripts), and git SHA/dirty flag for the SDK checkout. | Model rankings can change because the harness changed; version metadata is needed to compare runs over time. | §3 Scoring & reporting | Report fixture includes version fields or explicit `unknown` values |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F1: Report-only regeneration pairs naturally with an extractor contract and artifact index.
- R3-F2: Frozen input archive is required before shared-preamble reuse can be safe.
- R3-F7: Dry-run should show expanded profile defaults and readiness output, not just raw commands.
- R2-F1: Batch manifest should remain the authoritative machine-readable source behind artifact index and reports.
- R2-F8: No-cost smoke tests should cover exit codes, profiles, and extractor registration.

#### Review Round R5

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:46:00 UTC
- **Scope**: Feature requirements for comparison validity, baseline deltas, spec-file ergonomics, budget governance, and portable sharing

**Executive summary**

- R1-R4 make the harness truthful, supportable, retryable, and observable; R5 focuses on improving decision quality and repeatable configuration.
- Add a versioned comparison spec file so complex runs can be reviewed and rerun without fragile long CLI commands.
- Add a run-level validity verdict so users know whether a ranking is trustworthy before interpreting winners.
- Add baseline/delta reporting and normalized stage diffs to explain where models actually diverged.
- Add an auditable budget ledger with skip/stop reasons.
- Record and optionally randomize serial execution order to reduce hidden order bias.
- Add a redacted archive export for sharing results with collaborators.
- Ensure dry-run prints the effective spec, order, and budget ledger preview.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Interfaces | high | Add **FR-40 (comparison spec file)**: CLI accepts `--spec comparison.yaml|json` with `spec_version`, inputs, models, profile, budgets, output root, retry policy, baseline model, report options, and comparison mode; CLI flags override spec values and write `effective-spec.json`. | FR-11 lists invocation fields, but long multi-model runs need a reviewable and repeatable config artifact. | §3 Config & invocation after FR-13 | Spec fixture plus CLI override produces expected effective spec and command plan |
| R5-F2 | Validation | high | Add **FR-41 (comparison validity verdict)**: reports include `comparison_validity` (`valid`, `warning`, `invalid`) plus reasons based on input hashes, model-pin checks, minimum successful models, required artifacts, cost confidence, and seed divergence. | FR-9 ranks models, but users also need to know whether the comparison itself met its assumptions. | §3 Scoring & reporting after FR-23 | Missing required model-pin artifact yields `invalid`; missing optional cost yields `warning` |
| R5-F3 | Data | medium | Add **FR-42 (baseline delta view)**: user can designate `--baseline-model`; reports show deltas for score, cost, duration, stage statuses, ingestion metrics, and prime quality relative to baseline. | Absolute ranking is less useful than "better/worse than current default" for model selection decisions. | §3 Scoring & reporting after FR-9 | Fixture report includes baseline row and delta columns for all other models |
| R5-F4 | Data | medium | Add **FR-43 (stage diff artifacts)**: emit normalized diffs for per-model `prime-context-seed.json`, selected ingestion metrics, and final prime quality signals; include a short Markdown divergence summary. | E2E comparison value depends on understanding how model-specific upstream artifacts changed, not just final rank. | §3 Scoring & reporting after FR-8 | Two mock seed files produce deterministic diff output under `_diffs/` |
| R5-F5 | Ops | medium | Add **FR-44 (budget ledger and stop policy)**: persist `budget-ledger.jsonl` with estimated, reserved, actual, and remaining cost per stage; when global budget would be exceeded, skip remaining eligible stages/models with explicit `budget_exceeded` status. | OQ-9/global budget is resolved in principle but lacks auditable enforcement behavior. | §3 Execution or Scoring & reporting | Budget fixture skips second model and records pre/post ledger entries |
| R5-F6 | Risks | low | Add **FR-45 (serial order bias control)**: report records execution order; optional `--model-order listed|random` with `--order-seed` provides reproducible randomization. | FR-6 serial execution can bias latency/failure outcomes by time or provider incident; recording order is a cheap mitigation. | §3 Execution after FR-6 | Randomized order with fixed seed is reproducible and recorded in report |
| R5-F7 | Ops | low | Add **FR-46 (portable archive export)**: optional archive includes reports, manifest, artifact index, diffs, effective spec, replay metadata, budget ledger, and redacted logs; workdirs are excluded unless explicitly requested. | Users need a safe way to share evidence without moving full project copies or secrets. | §3 Scoring & reporting / Config & invocation | Archive test verifies required files included, workdirs excluded, and redaction applied |
| R5-F8 | Validation | medium | Add **FR-47 (dry-run effective plan)**: dry-run prints and/or writes effective spec, expanded profile, resolved model order, planned baseline, estimated budget ledger, and archive/report outputs that would be created. | FR-12 command-sequence output should reflect the richer configuration surface from R1-R5. | §3 Config & invocation at FR-12 | Snapshot test verifies dry-run includes effective spec path, order, baseline, and budget preview |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R4-F1: Artifact index should be the navigation layer for portable archives and diffs.
- R4-F2: Run profiles should be supported by a versioned spec file and effective-spec output.
- R4-F4: Exit codes should distinguish invalid comparison from completed but poor model results.
- R3-F1: Report-only regeneration must include baseline deltas and stage diff artifacts.
- R2-F1: Batch manifest should be the source of truth for validity verdicts and budget ledger references.
