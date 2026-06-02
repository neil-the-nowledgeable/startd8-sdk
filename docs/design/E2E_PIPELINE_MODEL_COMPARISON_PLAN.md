# End-to-End Cap-Dev-Pipe Multi-Model Comparison — Implementation Plan

**Version:** 1.1 (post-CRP triage R1–R4, paired with requirements v0.3)
**Date:** 2026-06-01
**Status:** Plan

> Built by planning against the real `.cap-dev-pipe` scripts. Discoveries fed back into
> requirements §0.

## What planning found (grounding)

- **`run-atomic.sh` is the unified orchestrator** — it already chains `run-cap-delivery.sh` →
  `run-plan-ingestion.sh` → `run-prime-contractor.sh` → postmortem (lines 410/512/624). The harness
  parameterizes/wraps **this**, not the three scripts individually.
- **Two tools, one orchestrator.** `run-cap-delivery.sh` drives the **contextcore** CLI
  (`contextcore polish`, `manifest analyze-plan`, `manifest init-from-plan`, export);
  `run-plan-ingestion.sh` and `run-prime-contractor.sh` drive **startd8**. The pipe is the seam.
- **Per-stage model surface:**
  - **prime** (`run_prime_workflow.py`): `--lead-agent` / `--drafter-agent` (passthrough). ✅ model-controllable.
  - **plan-ingestion** (`startd8 workflow run plan-ingestion`): LLM-driven via config keys
    `assessor_agent` + `transformer_agent` (default Claude Sonnet). ✅ model-controllable via config.
  - **enrich-seed.py**: **zero LLM cost** (deterministic DomainPreflightWorkflow). ➖ not a model stage.
  - **contextcore** polish/analyze/init: **no `--model` flag exposed**. ❌ not model-controllable from the pipe.
  - **run-atomic.sh**: **no `--model` today** (only `--skip-polish`, cost-budget forwarding).
- **No global model chokepoint** (no `STARTD8_*MODEL` env override of `model_catalog`).

## Approach (v1)

Add a `--model` to the orchestration layer that threads to the **model-controllable startd8
stages** (plan-ingestion + prime). The **contextcore manifest/polish preamble runs once as a shared,
model-independent stage** (it has no model knob, and a shared frozen manifest strengthens the
"identical input" property). So the comparison covers the generative span: *frozen plan →
[shared manifest] → per-model plan-ingestion → per-model prime → per-model deliverable.*

A new command `startd8 compare-models-e2e` reuses `startd8.model_comparison` helpers (slug, sandbox
isolation, gate/cost extraction, ranking, report) and adds a per-stage orchestration + extractor layer.

**Orchestration contract (R1-S6).** To avoid double-running cap-delivery: the harness runs the
contextcore preamble **once** (S1), then per model invokes only the startd8 stages — either by calling
`run-plan-ingestion.sh` + `run-prime-contractor.sh` directly, or `run-atomic.sh --skip-cap-delivery`
(reusing the S1 shared manifest). The dry-run must show cap-delivery executing **exactly once per
batch**. Every export carries `comparison_mode: manifest_frozen_v1` (R1-S5) so downstream tooling and
users never misread a v1 batch as full-pipeline multi-model.

## Step-by-step

### S0 — Preflight (R1-S1, R2-S4) — before any paid work
Validate all `provider:model` specs (provider creds/availability via existing ProviderRegistry
validation), require ≥2 distinct valid models, reject filesystem **slug collisions** after
normalization. **OQ-11 closure gate:** dry-run one config injection and assert
`startd8 workflow run plan-ingestion --dry-run` logs `assessor_agent`/`transformer_agent` == the model
under test; **fail the batch on mismatch** (guards silent Sonnet fallback → FR-14).

### S1 — Shared manifest preamble (once)
Run `run-cap-delivery.sh` once from the frozen `plan.md` + `requirements.md` → manifest / provenance
/ export in a shared `batch/_shared/` dir. Model-independent (contextcore default). Record its cost
(if contextcore emits any) as a shared, non-comparative line item.

### S2 — Per-model isolated sandbox (FR-4/5) — reuse existing patterns
For each model: `batch/<slug>/{workdir,output}`; `workdir` = project copy. Reuse
`materialize_sandbox(..., batch_root=...)` so the **H1 ignore** also excludes `batch/_shared` and
sibling model outputs from the copy (R1-S2) — preventing cross-model bleed and disk blow-up — on top
of the existing `.startd8`/state/`.cap-dev-pipe` exclusions. Copy the shared provenance (read-only)
into the per-model output so plan-ingestion can consume it.

### S3 — Per-model plan-ingestion with model pinned (FR-2 narrowed)
Invoke `run-plan-ingestion.sh` (or `startd8 workflow run plan-ingestion`) with a config that sets
`assessor_agent` and `transformer_agent` to the model under test → per-model `prime-context-seed.json`.
Capture `plan-ingestion-diagnostic.json` (Kaizen diag) + `ingestion_metrics`, and **record
`resolved_agents`** (FR-14). After ingestion, **hash each model's seed**; if two models share a seed
hash, mark the run `invalid_comparison` (R1-S8 / FR-15).

### S4 — Per-model prime with model pinned (proven)
Invoke prime with `--lead-agent <model> --drafter-agent <model> --force-regenerate` on the per-model
seed + workdir. This is exactly the validated `compare-models` path.

### S5 — Per-stage + end-to-end extraction (FR-8/9/10)
- plan-ingestion: success, duration, `ingestion_metrics`, cost (diagnostic or cost-DB time-window).
- prime: reuse `extract_metrics` (cost from `prime-result.json` `total_cost_usd`, `cross_file_gate`).
- **Three cost fields (R1-S3):** `cost_attributable_usd` (ingestion + prime), `cost_shared_preamble_usd`
  (allocated or `null`), `cost_total_loaded_usd`; each tagged `cost_source`/`cost_confidence`
  (`prime_result` | `cost_db_window` | `shared` | `missing`) (R2-S3). Rank on attributable.
- **Capability score (R1-S4):** explicit `w_ingestion·norm(ingestion_metrics) +
  w_prime·norm(gate + completion)`, weights documented + summing to 1.0, with a `score_breakdown`
  (components, penalties, source paths) and a `capability_prime_only` control column.
- **Stage status enum (R2-S3)** per model+stage (per FR-5). **Redact secrets** (R2-S6) from any
  persisted stdout/stderr/command/config.

### S6 — Ranked report + batch manifest (FR-9, FR-16)
Emit `batch-run-manifest.json` (R2-S1) as the backbone: `schema_version`, `comparison_mode`,
`batch/_inputs/` frozen-input hashes, shared-preamble artifact hashes, per-model `resolved_agents`,
per-stage status + cost source/confidence, `score_breakdown`, tool/SDK versions + git SHA, report
paths. The markdown/JSON report derives from it: per-model rows (per-stage success/cost/duration +
prime gate + total cost + capability score), ranked (capability → attributable cost). Header states
the FR-1 framing, `comparison_mode`, the single-run/indicative caveat, and the shared-manifest disclaimer.

### S7 — Orchestration & flags (FR-11/12/13)
New `startd8 compare-models-e2e`: `--plan`, `--requirements` (repeatable), `--model` (≥2),
`--source-root`, `--batch-root`, `--cost-budget` (per model, fed to prime; plan-ingestion budget
separate), `--global-budget` (FR/OQ-9), `--comparison-mode` (default `manifest_frozen_v1`, R1-S5),
`--per-stage-timeout` (R2-S2, reuse `run_command(timeout=…)`), `--dry-run`. Serial loop (FR-6).

### S8 — No-cost smoke test (FR-20, R2-S8)
Mock-provider/deterministic fixture: tiny plan+requirements, two `mock:` models, shared-preamble
placeholder → per-model ingestion → prime extraction → report+manifest. Runs in CI with no API spend;
asserts two isolated trees, two artifact sets, one ranked report + manifest.

## Risks
- **Contextcore can't vary by model (D1):** v1 explicitly does NOT compare the polish/analyze/init
  stages. True all-stage comparison is deferred until contextcore exposes a model flag (cross-repo).
- **Per-stage cost gaps:** contextcore cost may not be captured; plan-ingestion cost may need the
  cost-DB time-window fallback. Report tags each cost `cost_confidence` and marks unattributed as such.
- **Cost/time multiplies** across stages per model — `--global-budget` guards runaway spend.
- **Config plumbing (OQ-11, resolved):** `run-plan-ingestion.sh` post-patches `EFFECTIVE_CONFIG`
  (`--providers`/`--profile` pattern); inject `assessor_agent`/`transformer_agent` the same way, and
  S0 asserts the resolved specs to prevent silent Sonnet fallback.

## Out of scope (v1) → v2 backlog
Varying contextcore stages by model (OQ-10); parallel execution; per-stage model maps; repeat sampling.
**Deferred from CRP R2–R4 (Appendix B):** replay bundles, retention controls, report-only regeneration,
selective retry/attempts, readiness preflight (disk/budget), transient retry/backoff, CSV export,
operator decision guide, artifact index, run profiles, OTel/progress telemetry, exit-code policy,
stage-extractor registry, worked-example artifact, safe shared-preamble reuse.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed
- **Orchestration double-run risk** — resolved (Approach "Orchestration contract" + S0/S1 once).
- **Cost honesty** — resolved (S5 three cost fields + confidence; rank on attributable).
- **Model-pin verification** — resolved (S0 OQ-11 gate + S3 `resolved_agents`).

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | S0 preflight + OQ-11 closure gate | composer-2.5 | New **S0** | 2026-06-01 |
| R1-S2 | H1 `batch_root` exclusion in sandbox | composer-2.5 | S2 uses `materialize_sandbox(batch_root=…)` | 2026-06-01 |
| R1-S3 | Three cost fields + ranking policy | composer-2.5 | S5 cost fields; rank on attributable | 2026-06-01 |
| R1-S4 | Explicit capability formula + prime-only | composer-2.5 | S5 weighted formula + `capability_prime_only` | 2026-06-01 |
| R1-S5 | `--comparison-mode` metadata | composer-2.5 | Approach + S6 header + S7 flag | 2026-06-01 |
| R1-S6 | Orchestration contract (no double cap-delivery) | composer-2.5 | Approach "Orchestration contract" | 2026-06-01 |
| R1-S8 | Seed-hash integrity guard | composer-2.5 | S3 seed hashing → `invalid_comparison` | 2026-06-01 |
| R2-S1 | Batch run manifest | gpt-5.5 | S6 `batch-run-manifest.json` | 2026-06-01 |
| R2-S2 | Per-stage timeout | gpt-5.5 | S7 `--per-stage-timeout` | 2026-06-01 |
| R2-S3 | Stage status taxonomy + cost confidence | gpt-5.5 | S5 status enum + `cost_confidence` | 2026-06-01 |
| R2-S4 | Model/slug preflight | gpt-5.5 | Folded into S0 | 2026-06-01 |
| R2-S6 | Log/secret redaction | gpt-5.5 | S5 redaction note | 2026-06-01 |
| R2-S8 | Mock-provider smoke test | gpt-5.5 | New **S8** | 2026-06-01 |

### Appendix B: Rejected / Deferred Suggestions (with Rationale)

> "Deferred-v2" = sound, intentionally out of v1 scope (see Out of scope). Kept as cross-model memory.

| ID | Suggestion | Source | Disposition & Rationale | Date |
|----|------------|--------|-------------------------|------|
| R1-S7 | Optional prime-only baseline subprocess | composer-2.5 | Deferred-v2 — `capability_prime_only` column (S5) covers the v1 need; spawning a second run is extra cost | 2026-06-01 |
| R2-S5 | Replay bundle | gpt-5.5 | Deferred-v2 — recovery ergonomics; needs manifest | 2026-06-01 |
| R2-S7 | Retention controls | gpt-5.5 | Deferred-v2 — disk ergonomics | 2026-06-01 |
| R3-S1 | Report-only re-extraction | gpt-5.5 | Deferred-v2 — iteration convenience | 2026-06-01 |
| R3-S2 | Selective retry/resume + attempts | gpt-5.5 | Deferred-v2 — recovery workflow | 2026-06-01 |
| R3-S3 | Frozen input archive | gpt-5.5 | Accepted-lite — folded into S6 manifest (`batch/_inputs/`) | 2026-06-01 |
| R3-S4 | Readiness preflight (disk/budget) | gpt-5.5 | Deferred-v2 — provider check kept in S0; disk/budget later | 2026-06-01 |
| R3-S5 | Transient retry/backoff | gpt-5.5 | Deferred-v2 — resilience tuning | 2026-06-01 |
| R3-S6 | CSV export | gpt-5.5 | Deferred-v2 — interop nicety | 2026-06-01 |
| R3-S7 | Operator decision guide | gpt-5.5 | Deferred-v2 — report ergonomics | 2026-06-01 |
| R4-S1 | Artifact index | gpt-5.5 | Deferred-v2 — S6 manifest covers v1 | 2026-06-01 |
| R4-S2 | Run profiles | gpt-5.5 | Deferred-v2 — UX presets | 2026-06-01 |
| R4-S3 | Progress/OTel telemetry | gpt-5.5 | Deferred-v2 — observability | 2026-06-01 |
| R4-S4 | Exit-code semantics | gpt-5.5 | Deferred-v2 — CI semantics | 2026-06-01 |
| R4-S5 | Stage extractor registry | gpt-5.5 | Deferred-v2 — earns value at v2 multi-extractor | 2026-06-01 |
| R4-S6 | Worked example | gpt-5.5 | Deferred-v2 — pairs with S8 impl | 2026-06-01 |
| R4-S7 | Safe shared-preamble reuse | gpt-5.5 | Deferred-v2 — perf opt; needs manifest hashes | 2026-06-01 |
| R4-S8 | Tool-version metadata | gpt-5.5 | Accepted-lite — folded into S6 manifest | 2026-06-01 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: composer-2.5
- **Date**: 2026-06-02 12:00:00 UTC
- **Scope**: Dual-document architectural review — robustness, end-user value, sponsor focus (7 asks)

**Executive summary**

- v1 boundary (shared contextcore + per-model startd8) is **defensible** only with renamed comparison mode and report disclaimers; headline "full pipeline / every stage" over-promises today.
- **FR-1 prose contradicts v1 design** (claims per-model polished plan while plan S1 shares one manifest) — misleads readers and undermines trust in results.
- **Cost ranking needs two totals** (attributable per-model vs batch fully-loaded incl. shared preamble) or cheap models win on accounting artifacts alone.
- **Capability score must be specified** (weights for prime gate vs ingestion vs shared manifest quality); default prime-heavy composite risks false "end-to-end" claims.
- **OQ-11 is likely solvable** without script surgery: `run-plan-ingestion.sh` already post-patches `EFFECTIVE_CONFIG` (kaizen/providers/profile pattern); add assessor/transformer injection + a verify step.
- **Isolation gap**: extend `model_comparison._ignore_factory` (H1) to `batch/_shared` and document ContextCore home-dir bleed if polish writes outside pipeline-output.
- **FR-7 vs S1–S4 split** needs an explicit orchestration contract (`run-atomic.sh --skip-cap-delivery` or harness-only sub-scripts) so implementers don't double-run cap-delivery.
- **End-user value**: dry-run (FR-12) should print resolved agent specs per stage; JSON report should carry `comparison_mode: manifest_frozen_v1` for downstream tooling.
- **Prime-only comparison remains the control** — E2E report should link each model row to an optional same-seed `compare-models` row to separate ingestion effects from generation.
- **Problem statement table (§1)** still lists POLISH/ANALYZE as "model not threaded" without v1/shared annotation — confuses stakeholders.

### Sponsor focus — explicit answers

**Focus 1 — Cross-tool / cross-repo boundary**

- **Summary answer:** Partial — sound as **v1 "frozen-manifest + startd8 generative span"** comparison, not as literal "every LLM stage end-to-end."
- **Rationale:** Plan Approach and S1–S4 correctly narrow to startd8 stages (FR-2, D1). Requirements §1 and FR-1 still describe per-model upstream artifacts and "every LLM-driven stage," which overstates v1. Renaming the deliverable (report `comparison_mode`, command help text) preserves honesty without blocking v1 delivery.
- **Assumptions / conditions:** Stakeholders accept that contextcore default model fixed the manifest for all candidates until OQ-10 lands.
- **Suggested improvements:** Add plan step S0 "comparison mode metadata"; requirements FR-1 add v1 bullet that shared manifest means **identical** polish/analyze/init inputs to plan-ingestion, not per-model.

**Focus 2 — Shared contextcore preamble vs per-model**

- **Summary answer:** Yes for v1 cost/control; introduces **manifest-quality coupling** that must be disclosed.
- **Rationale:** Shared preamble strengthens "identical input" for ingestion (plan S1) but means plan-ingestion and prime are compared **conditional on one contextcore run's manifest**, not each model's planning stack. Per-model contextcore (even on default model) would isolate sandbox/path effects; defer to v2 when `--model` exists.
- **Assumptions / conditions:** `batch/_shared/` provenance is immutable after S1 and copied read-only into each model tree (S2).
- **Suggested improvements:** Requirements: add FR stating report lists `shared_manifest_provenance_path` + contextcore validation-report snapshot hash per batch.

**Focus 3 — Per-stage cost attribution**

- **Summary answer:** Partial — summing is defensible only with **separate attributable vs shared cost columns** and ranking policy documented.
- **Rationale:** Plan S5 aggregates Σ stage costs; OQ-12 admits contextcore may be unattributable. Allocating shared preamble cost equally across N models skews `$ / capability` for the cheapest model count. Prime `total_cost_usd` is proven; plan-ingestion time-window is serial-safe (OQ-5) but should be labeled confidence tier.
- **Assumptions / conditions:** Serial execution (FR-6) holds for time-window attribution.
- **Suggested improvements:** Plan S5/S6: `cost_attributable_usd`, `cost_shared_preamble_usd`, `cost_total_loaded_usd`; rank on attributable first, footnote fully-loaded.

**Focus 4 — Model threading mechanics (OQ-11)**

- **Summary answer:** Yes, viable via **post-resolve config injection** (same pattern as `--providers` / `--profile` in `run-plan-ingestion.sh`); silent Sonnet fallback is the real risk.
- **Rationale:** `PlanIngestionWorkflow._resolve_assessor_agent` / `_resolve_transformer_agent` read config keys with `Models.CLAUDE_SONNET_LATEST` default (`plan_ingestion_workflow.py`). Harness must patch `EFFECTIVE_CONFIG` after `resolve-provenance.py` and assert resolved specs in artifacts (diagnostic JSON or run manifest).
- **Assumptions / conditions:** Orchestrator writes temp config per model before invoking ingestion; prime passthrough flags unchanged.
- **Suggested improvements:** Plan S3 add "record `resolved_agents` block"; requirements new FR for post-stage model verification.

**Focus 5 — Isolation correctness**

- **Summary answer:** Partial — sandbox copy pattern is proven for prime; **extend exclusions** for batch output and verify no shared ContextCore state paths.
- **Rationale:** `materialize_sandbox` + `SANDBOX_IGNORE` exclude `.startd8` and `.cap-dev-pipe` (plan S2, `model_comparison.py`). Copying shared provenance into per-model output is correct for ingestion input. Risk: nested `batch/_shared` copied into each workdir (H1 in prime harness); global `~/.contextcore/state` if contextcore stages write outside pipeline-output.
- **Assumptions / conditions:** `batch_root` passed into `materialize_sandbox` like `compare-models`.
- **Suggested improvements:** Plan S2 cite H1 ignore; requirements FR-4 list excluded path globs including `batch/_shared` source tree.

**Focus 6 — Deferred cross-repo dependency (OQ-10)**

- **Summary answer:** Yes, deferral is acceptable if v1 naming and report schema encode the split.
- **Rationale:** D1 and plan Risks already draw the line at contextcore lacking `--model`. v2 trigger should be "contextcore exposes model on polish/analyze/init" plus optional `comparison_mode: full_e2e_v2`.
- **Assumptions / conditions:** Cross-repo issue tracked outside this repo.
- **Suggested improvements:** Requirements OQ-10 add acceptance criteria for v2 promotion (flag exists + harness threads it).

**Focus 7 — Capability score validity**

- **Summary answer:** Partial — prime-heavy today; needs **explicit composite** including ingestion signals and a "prime-only delta" column.
- **Rationale:** Plan S5 ties capability to `cross_file_gate` + feature completion; OQ-7 mentions ingestion_metrics but no weighting. Upstream ingestion can invalidate seeds before prime runs — ignoring ingestion overstates generation quality.
- **Assumptions / conditions:** Stage artifacts exist even on partial failure (FR-5).
- **Suggested improvements:** Plan S5/S6 define weighted formula + `capability_prime_only` for apples-to-apples with existing `compare-models`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | Add **S0 — Preflight & OQ-11 closure**: before batch loop, run one dry-run model injection (patch `assessor_agent`/`transformer_agent` into resolved config) and assert `startd8 workflow run plan-ingestion --dry-run` logs both specs; document pass/fail gate. | Without proving config injection, entire comparison may silently use Sonnet defaults (`_resolve_*_agent` fallback). | New subsection before S1 | CI or manual preflight checklist; fail batch if mismatch |
| R1-S2 | Architecture | high | In **S2**, require `materialize_sandbox(..., batch_root=...)` so `batch/_shared` and sibling model outputs are excluded from workdir copies (reuse H1 in `model_comparison._ignore_factory`). | Prevents cross-model artifact bleed and disk blow-up when batch lives inside repo. | § S2 — Per-model isolated sandbox | Inspect workdir tree: no `batch/` sibling outputs present |
| R1-S3 | Data | high | In **S5/S6**, emit **three cost fields** per model: `cost_attributable_usd` (plan-ingestion + prime only), `cost_shared_preamble_usd` (allocated or null), `cost_total_loaded_usd`; document default **ranking uses attributable** with footnote for fully-loaded. | "Aggregate **total end-to-end cost** = Σ stage costs" without shared-cost policy skews rankings when contextcore cost is unattributable (Risks). | § S5–S6 | JSON schema test; report shows both columns for 2-model fixture |
| R1-S4 | Validation | medium | In **S5/S6**, define `capability_score` formula explicitly, e.g. `w_ingestion * norm(ingestion_metrics) + w_prime * norm(cross_file_gate + completion)` with defaults documented; add `capability_prime_only` column reusing existing extractor for control comparison. | Prevents over-weighting prime while claiming end-to-end signal (Focus 7, OQ-7). | § S5 — extraction | Unit test on synthetic artifacts; weights sum to 1.0 |
| R1-S5 | Interfaces | medium | In **S7**, add `--comparison-mode` (default `manifest_frozen_v1`) propagated to JSON/Markdown report header and CLI help; align with renamed user-facing description (not "every stage"). | End users otherwise misread results as full-pipeline multi-model when contextcore was single-run (Approach). | § S7 — Orchestration & flags | `--dry-run` output includes mode string |
| R1-S6 | Architecture | medium | Resolve **FR-7 vs split orchestration**: document whether harness calls `run-atomic.sh` once per model with `--skip-cap-delivery` after S1, or invokes sub-scripts only; add sequence diagram note preventing double cap-delivery. | Plan says reuse `run-atomic.sh` (requirements FR-7) but S1 runs cap-delivery once globally — implementers may run preamble twice. | § Approach or new "Orchestration contract" | Dry-run shows cap-delivery exactly once per batch |
| R1-S7 | Ops | low | Extend **S6** report with per-model link/path to optional **prime-only baseline** (`compare-models` on that model's seed) when `--with-prime-baseline` set. | Separates ingestion variance from generation for operators comparing to run-012/013 harness. | § S6 — Ranked report | Flag runs prime-only subprocess; report row populated |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Risks | medium | Require **post-stage artifact checksum** of `prime-context-seed.json` per model after ingestion; fail comparison if two models produce identical seeds (would indicate model pin failure or shared-state bug). | Adversarial: identical seeds make E2E collapse to prime-only comparison without surfacing why. | § S3 after ingestion | Assert seed hashes differ across ≥2 models in smoke test |

## Requirements Coverage Matrix — R1

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Conceptual framing | S6 report header; Approach | Partial | FR-1 body still says per-model polished plan; plan uses **shared** manifest (S1) — prose misalignment |
| FR-2 Model propagation | S3, S4, S7 | Full | Missing explicit verify-no-fallback step (see R1-S1) |
| FR-3 Deterministic stages | Approach (enrich-seed); S1 contextcore once | Full | — |
| FR-4 Isolation | S2 | Partial | H1 batch_root exclusion not stated; ContextCore global state not mentioned |
| FR-5 Independent failure | S2–S4 serial loop | Partial | No explicit per-model error row / continue policy in plan |
| FR-6 Serial execution | S7; Approach | Full | — |
| FR-7 Reuse run-atomic.sh | Approach; S1–S4 split | Partial | Orchestration split vs atomic script not specified (R1-S6) |
| FR-8 Per-stage outcomes | S5 | Partial | Lists polish/analysis signals but S1 shared — which apply per model vs batch unclear |
| FR-9 Aggregate cost + capability | S5, S6 | Partial | Cost honesty policy and composite score formula underspecified (R1-S3, R1-S4) |
| FR-10 Reuse model_comparison | S2, S4, S5; module reuse | Full | E2E extractor layer mentioned but schema not sketched |
| FR-11 Config & invocation | S7 | Full | — |
| FR-12 Dry-run | S7 | Partial | Should require resolved agent specs in dry-run output (end-user value) |
| FR-13 New command | S7; Approach | Full | — |
| NR-1–NR-6 | Out of scope; Risks | Full | NR-3 indicative-run caveat not mirrored in plan report section |
| OQ-10–OQ-13 | Risks; S1; S5 | Partial | OQ-11 not closed in plan (R1-S1); OQ-12 representation partial (R1-S3) |

#### Review Round R2

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:40:00 UTC
- **Scope**: Operational robustness, end-user value, functional quick wins after R1

**Executive summary**

- R1 covered the main truth-in-labeling, cost, model-pin, and isolation issues; R2 focuses on low-lift operational features that make the tool easier to trust and debug.
- The plan should add a **batch run manifest** as the backbone for report generation, replay, provenance, and support tickets.
- End users need a **reproducibility bundle** per model: commands, cwd, config snapshot, selected environment, and artifact checksums.
- Failure handling should be more granular than success/failure; a per-stage status enum enables partial reports and failed-model retry.
- Add timeout and resume semantics now while execution is serial; the existing `model_comparison.run_command()` pattern already has most of this shape.
- Validate model specs and slug collisions before expensive work starts.
- Treat stdout/stderr tails as potentially sensitive; redact known secret patterns before persisting logs into JSON reports.
- Add disk retention controls because per-model full project copies can grow quickly on large repos.

### Sponsor focus — R2 delta answers

**Focus 1 — Cross-tool / cross-repo boundary**

- **Summary answer:** R1's boundary is acceptable if the plan also gives users a supportable audit trail.
- **Rationale:** A shared contextcore preamble becomes easier to defend when `S1` emits immutable paths and checksums that every model row references. Without that ledger, a user cannot prove each model consumed the same shared manifest.
- **Assumptions / conditions:** The shared preamble artifacts are written once and not mutated after per-model runs begin.
- **Suggested improvements:** Add `batch-run-manifest.json` in `S1/S6` with shared artifact hashes and per-model consumed provenance paths.

**Focus 2 — Shared contextcore preamble vs per-model**

- **Summary answer:** Shared preamble is strongest when made **read-only and auditable**.
- **Rationale:** Plan `S2` copies shared provenance into each model output, but does not state whether the original shared directory is immutable during the model loop. A manifest-plus-checksum check is a small addition that detects accidental mutation.
- **Assumptions / conditions:** The harness can hash JSON/Markdown artifacts after `S1`.
- **Suggested improvements:** Add a pre-model loop assertion that shared artifact hashes still match the `S1` manifest.

**Focus 3 — Per-stage cost attribution**

- **Summary answer:** R1's three cost columns should be paired with a **cost confidence** field.
- **Rationale:** Plan `S5` allows diagnostic or cost-DB time-window fallback; operators need to know whether a number is artifact-derived, DB-window-derived, shared, or missing. This is a low-effort enum beside each cost value.
- **Assumptions / conditions:** Existing extractors can report source strings like `prime_result` and `cost_db_window`.
- **Suggested improvements:** Add `cost_source` / `cost_confidence` per stage in JSON.

**Focus 4 — Model threading mechanics**

- **Summary answer:** Verification should include fail-fast model validation before the first stage.
- **Rationale:** R1 catches silent fallback after config resolution; a preflight can also reject unknown providers/models before creating sandboxes. The existing provider pattern already expects provider discovery and validation.
- **Assumptions / conditions:** The command can call StartD8 provider validation without making generation calls.
- **Suggested improvements:** Add a preflight task in `S0` to validate all `provider:model` specs and detect duplicate filesystem slugs.

**Focus 5 — Isolation correctness**

- **Summary answer:** Add mutation detection, not just copy isolation.
- **Rationale:** `S2` says each model has a project copy, but the plan does not specify how to detect if a stage writes outside the expected per-model tree. A cheap post-stage file inventory diff can flag unexpected writes.
- **Assumptions / conditions:** The harness knows `batch/<slug>/workdir`, `batch/<slug>/output`, and `batch/_shared`.
- **Suggested improvements:** Add an allowed-write-roots check after each stage.

**Focus 6 — Deferred cross-repo dependency**

- **Summary answer:** Deferral is safer if v1 stores enough data to re-run under v2 later.
- **Rationale:** If contextcore later exposes `--model`, prior v1 batches should still be interpretable and maybe replayable. Persisting config snapshots and command lines makes that migration cheaper.
- **Assumptions / conditions:** Snapshots omit secrets.
- **Suggested improvements:** Add `replay/` scripts or commands per model in the output tree.

**Focus 7 — Capability score validity**

- **Summary answer:** Add score explainability alongside any composite score.
- **Rationale:** Users need to know why a model won, not just that it ranked first. A compact `score_breakdown` with normalized components, missing-component penalties, and source artifact paths turns the score into an actionable diagnostic.
- **Assumptions / conditions:** R1's explicit scoring formula is accepted.
- **Suggested improvements:** Add `score_breakdown` to JSON and a short "Why this ranking?" section to Markdown.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | high | Add a **batch-run manifest** emitted after `S1` and updated after each model: `schema_version`, `comparison_mode`, shared artifact paths/checksums, per-model commands, stage statuses, cost sources, and report paths. | `S5/S6` currently imply extraction directly from scattered artifacts; a manifest gives downstream docs, replay, support, and tests one stable contract. | New `S0/S6 — Batch manifest contract` | Golden JSON fixture validates required keys and checksum fields |
| R2-S2 | Ops | high | Add per-stage **timeout and continuation policy** (`--per-stage-timeout` or `{contextcore,ingestion,prime}` defaults) using the existing `run_command(... timeout=...)` pattern from `model_comparison.py`. | Serial execution can wedge the entire batch if contextcore or ingestion hangs; model-level isolation does not help without timeouts. | `S7 — Orchestration & flags` plus `Risks` | Simulated hanging stage returns timed-out status and later models still run |
| R2-S3 | Risks | medium | Add a **stage status taxonomy**: `not_started`, `skipped_shared`, `success`, `failed`, `timed_out`, `invalid_model`, `budget_exceeded`, `artifact_missing`, `invalid_comparison`. | `S5` says capture success/failure, but users need actionable failure classes in partial reports and retry flows. | `S5 — extraction` | Unit test maps representative return codes/missing artifacts to enum values |
| R2-S4 | Interfaces | medium | Add **model spec and slug preflight**: validate all `provider:model` specs before `S1`, de-duplicate exact specs, and reject slug collisions after filesystem sanitization. | Existing `slug()` can collapse distinct strings into the same path; invalid models should fail before expensive shared preamble work. | `S7 — Orchestration & flags` | Two colliding model specs produce a preflight error |
| R2-S5 | Ops | medium | Emit a **per-model replay bundle** under `batch/<slug>/replay/`: command lines, cwd, sanitized env summary, effective plan-ingestion config, prime command, and artifact checksum list. | End users debugging a losing or failed model need a reproducible path without reconstructing invocation state from logs. | `S3–S6` | Dry-run and real run both write replay files with secrets redacted |
| R2-S6 | Security | medium | Redact secrets before storing `stdout_tail`, `stderr_tail`, command lines, or config snapshots in reports; document patterns for API keys and known env var names. | Existing comparison code persists command output tails; E2E will span more tools and may expose credentials or local paths in logs. | `S5/S6` and `Risks` | Redaction test injects fake API keys and verifies report contains `[REDACTED]` |
| R2-S7 | Ops | low | Add retention controls: `--keep-workdirs` (`always`, `failed`, `never`) and `--cleanup-after-report` for successful workdirs while preserving outputs/replay bundles. | Per-model full project copies are useful for debugging but costly on large repos; a flag gives operators predictable disk use. | `S7 — Orchestration & flags` | Successful smoke run removes workdir when configured, keeps output/report |
| R2-S8 | Validation | medium | Add a cheap **mock-provider smoke test** for `compare-models-e2e` using a tiny plan/requirements pair and deterministic mock outputs. | The feature crosses shell scripts, config generation, report extraction, and sandboxing; a no-cost smoke test catches regressions without real LLM spend. | New validation subsection after `S7` | CI test produces JSON + Markdown report with two mock models |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S1: Model-pin preflight is the highest correctness gate and should be implemented before running paid comparisons.
- R1-S3: Separate cost columns are necessary for honest reporting when shared preamble cost is not per-model.
- R1-S5: `comparison_mode` is essential user-facing metadata and should appear in CLI help and JSON.
- R1-S6: The `run-atomic.sh` versus sub-script orchestration split must be resolved before implementation.
- R1-S8: Seed checksum validation is a valuable low-cost guard against false comparisons.

## Requirements Coverage Matrix — R2

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Conceptual framing | Approach; S6 | Partial | Needs audit artifacts that prove the shared preamble and per-model span were actually used as described |
| FR-2 Model propagation | S3/S4/S7 | Partial | R1 covers verification; R2 adds fail-fast model-spec and slug validation |
| FR-3 Deterministic stages | S1; S3 enrich-seed note | Full | — |
| FR-4 Isolation | S2 | Partial | Needs allowed-write-root checks and retention policy for copied workdirs |
| FR-5 Independent failure | S2–S4 | Partial | Needs explicit status taxonomy, timeout policy, and retry/replay bundle |
| FR-6 Serial execution | S7 | Full | Timeout policy should be specified while serial is still simple |
| FR-7 Reuse run-atomic.sh | Approach; S1–S4 | Partial | R1 orchestration-contract gap remains; R2 replay bundle would make the chosen contract inspectable |
| FR-8 Per-stage outcomes | S5 | Partial | Needs stage status enum, cost source/confidence, log redaction, and artifact checksums |
| FR-9 Aggregate report | S5/S6 | Partial | Needs schema version, score breakdown, and reproducibility metadata |
| FR-10 Reuse helpers | S2/S4/S5 | Full | E2E should reuse `run_command`, timeout, extraction, and report helper patterns where possible |
| FR-11 Invocation | S7 | Partial | Add slug/model validation and retention flags |
| FR-12 Dry-run | S7 | Partial | Dry-run should also show replay bundle paths and resolved validation status |
| FR-13 Command shape | S7 | Full | — |

#### Review Round R3

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:43:00 UTC
- **Scope**: Fresh-agent pass for end-user workflow, report ergonomics, selective retry, and low-lift operational enhancements

**Executive summary**

- R1/R2 cover the central correctness scaffolding; R3 targets usability and operator loops after the first run.
- Add a **report-only re-extraction mode** so users can regenerate reports after extractor fixes without paying to rerun models.
- Add **selective retry/resume** for one failed model or stage, using the batch manifest/replay bundle proposed in R2.
- Freeze and hash the original input plan/requirements in the batch output so later readers can audit exactly what was compared.
- Add a readiness check for credentials, provider availability, and estimated spend before any shared preamble or model run starts.
- Define bounded retry/backoff for transient provider or network failures separately from deterministic stage failures.
- Provide CSV/flat summary export for quick spreadsheet comparison and non-SDK users.
- Add a short user decision guide explaining when to use prime-only `compare-models` versus E2E comparison.

### Sponsor focus — R3 delta answers

**Focus 1 — Cross-tool / cross-repo boundary**

- **Summary answer:** The v1 boundary becomes more useful if users can inspect and regenerate reports from artifacts after the fact.
- **Rationale:** R1/R2 make the boundary honest and auditable; `S6` can go further by making report generation replayable from `batch-root` without rerunning contextcore or startd8. This gives users confidence that ranking changes after extractor fixes are not caused by new model output.
- **Assumptions / conditions:** R2's batch manifest or equivalent artifact index exists.
- **Suggested improvements:** Add `--report-only --batch-root <path>` to rebuild Markdown/JSON/CSV from existing artifacts.

**Focus 2 — Shared contextcore preamble vs per-model**

- **Summary answer:** Freeze the original inputs as first-class artifacts, not just the shared manifest output.
- **Rationale:** `S1` begins from frozen `plan.md` and `requirements.md`, but the plan does not say the harness copies and hashes those inputs into the batch directory. Hashing inputs lets later reviewers prove all models and the shared preamble used the intended source documents.
- **Assumptions / conditions:** Input files are local files at invocation time.
- **Suggested improvements:** Add `batch/_inputs/{plan.md,requirements*.md,checksums.json}` before `S1`.

**Focus 3 — Per-stage cost attribution**

- **Summary answer:** Add preflight cost visibility before execution, not only post-run accounting.
- **Rationale:** R1/R2 improve cost columns and sources, but users still need a go/no-go estimate before a multi-model batch spends money. A rough estimate can use model list, stage count, budget flags, and existing cost catalog defaults.
- **Assumptions / conditions:** Estimate is labeled approximate and does not block when pricing is unknown.
- **Suggested improvements:** `--dry-run` prints estimated maximum spend from per-model and global budgets plus unknown-cost warnings.

**Focus 4 — Model threading mechanics**

- **Summary answer:** Add provider readiness checks next to model validation.
- **Rationale:** R2 validates model specs and slugs; a model can still fail immediately because its provider credentials are missing or invalid. Calling provider validation before `S1` prevents users from paying for a shared preamble only to discover no candidate model can run.
- **Assumptions / conditions:** Provider validation can run without a generation call.
- **Suggested improvements:** Add readiness summary grouped by provider: configured, missing credentials, unknown pricing, or skipped.

**Focus 5 — Isolation correctness**

- **Summary answer:** Selective retry should preserve isolation boundaries.
- **Rationale:** Retrying a failed model should not reuse a dirty workdir unless the operator explicitly asks for forensic continuation. The plan should define whether retry creates a new attempt directory or resumes the existing one.
- **Assumptions / conditions:** Per-model output path can include attempt number.
- **Suggested improvements:** Add `attempt-001`, `attempt-002` under each model output for retries.

**Focus 6 — Deferred cross-repo dependency**

- **Summary answer:** Report-only mode and frozen input copies reduce migration pain when contextcore later becomes model-controllable.
- **Rationale:** If v2 adds full-pipeline variation, old v1 runs remain comparable by mode and input hash rather than ambiguous historical reports.
- **Assumptions / conditions:** `comparison_mode` from R1 is accepted.
- **Suggested improvements:** Include `input_hashes` and `comparison_mode` in every export format.

**Focus 7 — Capability score validity**

- **Summary answer:** Add a simple "decision guidance" section so rankings do not become black-box recommendations.
- **Rationale:** Even with score breakdowns, users need guidance such as "winner is cheaper but failed ingestion quality" or "prime-only baseline disagrees with E2E winner." This turns metrics into actionable end-user value.
- **Assumptions / conditions:** R1/R2 report columns are implemented.
- **Suggested improvements:** Add report heuristics that emit short caveats when rankings are close, costs are missing, or stages failed.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Ops | high | Add **report-only re-extraction**: `startd8 compare-models-e2e --report-only --batch-root <existing>` regenerates Markdown/JSON/CSV from existing artifacts without running contextcore, ingestion, or prime. | Users will tune extractors and report formatting; rerunning paid model stages just to fix a report is wasteful and slows iteration. | `S6 — Ranked report` and `S7 — flags` | Fixture batch regenerates identical report after deleting only report files |
| R3-S2 | Risks | high | Add **selective retry/resume**: `--resume-batch`, `--retry-model <slug>`, and optional `--from-stage ingestion|prime`; retries write `attempt-002` rather than overwriting prior attempt artifacts. | R2 defines failure taxonomy and replay bundles, but operators need an ergonomic recovery path when one model flakes. | New subsection after `S7` | Simulated model failure can be retried without modifying successful model directories |
| R3-S3 | Data | medium | Before `S1`, copy frozen inputs into `batch/_inputs/` and write `checksums.json` for each plan/requirements file. | The plan says inputs are frozen, but persistent copies and hashes make that claim auditable after local source files change. | `S1 — Shared manifest preamble` pre-step | Report references input hashes; modifying source after run does not change batch evidence |
| R3-S4 | Ops | medium | Add a **readiness preflight** before any stage execution: provider credentials/config validation, available disk estimate, writable batch root, and budget flag summary. | Invalid credentials or unwritable outputs should fail before shared preamble work and before any paid model calls. | New `S0 — Readiness preflight` | Dry-run with missing provider key reports provider-specific readiness failure |
| R3-S5 | Risks | medium | Define bounded **transient retry/backoff** for provider/network failures separately from deterministic artifact failures; include retry count in stage metadata. | A one-off 429 or network hiccup should not mark a model inferior, but repeated artifact failures should not be hidden by retries. | `S3/S4` execution notes and `S5` extraction | Mock command returning transient codes succeeds on second attempt and records retry count |
| R3-S6 | Interfaces | low | Emit a flat `comparison-summary.csv` alongside JSON/Markdown with one row per model and stable columns for status, score, cost, duration, and key artifact paths. | Many end users will inspect model rankings in spreadsheets or dashboards before consuming nested JSON. | `S6 — Ranked report` | CSV fixture has one row per model and matches JSON values |
| R3-S7 | Architecture | low | Add a brief **operator decision guide** to the Markdown report: when to trust E2E winner, when to run prime-only `compare-models`, and when missing cost/stage failures make the run inconclusive. | R1/R2 improve data quality, but users still need interpretation guardrails to avoid over-selecting from a noisy single run. | `S6 — Ranked report` | Snapshot test verifies report includes decision caveats for close scores and failed stages |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S1: The batch manifest is the enabling dependency for report-only mode and selective retry.
- R2-S2: Timeouts are required before selective retry is meaningful.
- R2-S5: Replay bundles give users the forensic detail needed for failed-model support.
- R2-S6: Redaction should apply to the report-only and replay paths as well as first-run reports.
- R1-S7: Prime-only baseline remains the clearest way to explain whether the E2E winner is driven by ingestion or generation.

## Requirements Coverage Matrix — R3

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Conceptual framing | Approach; S6 | Partial | Add copied input hashes so the "frozen inputs" claim is auditable |
| FR-2 Model propagation | S3/S4/S7 | Partial | R2 covers validation; R3 adds provider readiness before paid work |
| FR-3 Deterministic stages | S1/S3 | Full | — |
| FR-4 Isolation | S2 | Partial | Retry attempts need explicit attempt directories to avoid overwriting |
| FR-5 Independent failure | S2–S4 | Partial | Add selective retry/resume semantics after a partial failure |
| FR-6 Serial execution | S7 | Full | Transient retry policy should preserve serial cost attribution windows |
| FR-7 Reuse run-atomic.sh | Approach; S1–S4 | Partial | Report-only mode depends on a stable artifact layout from whichever orchestration path is chosen |
| FR-8 Per-stage outcomes | S5 | Partial | Add retry count, attempt number, and transient-vs-deterministic failure metadata |
| FR-9 Aggregate report | S5/S6 | Partial | Add CSV export, decision guide, and report-only regeneration |
| FR-10 Reuse helpers | S2/S4/S5 | Full | Existing report/extractor helpers can back report-only mode |
| FR-11 Config & invocation | S7 | Partial | Add `--report-only`, `--resume-batch`, `--retry-model`, and readiness preflight behavior |
| FR-12 Dry-run | S7 | Partial | Dry-run should include readiness and estimated maximum spend |
| FR-13 Command shape | S7 | Full | — |

#### Review Round R4

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:44:00 UTC
- **Scope**: Fresh-agent pass for adoption friction, artifact navigation, CI behavior, telemetry, and extension seams

**Executive summary**

- R1-R3 cover correctness, supportability, replay, and retry; R4 focuses on making the feature pleasant to operate and easy to extend.
- Add an **artifact index / README** so users can navigate a large batch without understanding internal directory conventions.
- Add named **run profiles** (`quick`, `standard`, `audit`) to package sensible defaults for budgets, retention, replay, and report detail.
- Emit progress/telemetry events for each stage so long serial batches are observable while running, not only after report generation.
- Define exit-code semantics for CLI/CI users.
- Introduce an extractor registry boundary so future contextcore-v2 or new stage artifacts do not force ad hoc report parsing.
- Add a user-facing example and sample report as acceptance artifacts, not afterthought documentation.
- Add safe shared-preamble reuse by input hash to avoid repeating deterministic setup when comparing model sets iteratively.

### Sponsor focus — R4 delta answers

**Focus 1 — Cross-tool / cross-repo boundary**

- **Summary answer:** The boundary should be surfaced as an artifact map, not buried in prose.
- **Rationale:** Prior rounds clarified the v1 comparison mode; an operator still needs to see which artifacts came from contextcore versus startd8. An artifact index can make the two-tool boundary visible at the top of every batch output.
- **Assumptions / conditions:** The batch layout has stable shared and per-model roots.
- **Suggested improvements:** Add `ARTIFACTS.md` or `artifact-index.json` with producer tool, stage, model scope, and path per artifact.

**Focus 2 — Shared contextcore preamble vs per-model**

- **Summary answer:** A hash-keyed shared preamble cache is a useful quick win if reuse is explicit.
- **Rationale:** R3 archives input hashes; those hashes can safely guard reuse of an existing shared preamble for another model set. This improves iteration speed without silently changing the comparison input.
- **Assumptions / conditions:** Reuse is opt-in and fails closed when input hashes or tool versions differ.
- **Suggested improvements:** Add `--reuse-shared-preamble <batch-root>` guarded by input and contextcore version checks.

**Focus 3 — Per-stage cost attribution**

- **Summary answer:** Run profiles can reduce user mistakes around budgets and report detail.
- **Rationale:** Users choosing between cheap exploration and audit-grade comparison should not memorize many flags. Profiles package cost caps, retention, report detail, and replay behavior into understandable presets.
- **Assumptions / conditions:** Profiles are only defaults; explicit flags override them.
- **Suggested improvements:** Add `--profile quick|standard|audit`.

**Focus 4 — Model threading mechanics**

- **Summary answer:** Tool-version capture belongs next to model capture.
- **Rationale:** A comparison can change because startd8/contextcore changed, not because the model changed. The plan should capture SDK version, contextcore CLI version, and git SHA in report metadata.
- **Assumptions / conditions:** Version commands are available or can be marked unknown.
- **Suggested improvements:** Add versions to the artifact index and report header.

**Focus 5 — Isolation correctness**

- **Summary answer:** Exit-code policy and artifact index help CI distinguish bad infrastructure from a losing model.
- **Rationale:** CI needs to know whether the command failed to run, ran with model failures, or ran successfully but found a low-scoring model. Without defined exit codes, automation will treat all non-perfect comparisons as generic failures.
- **Assumptions / conditions:** Partial reports are emitted before exit when possible.
- **Suggested improvements:** Add exit-code table under `S7`.

**Focus 6 — Deferred cross-repo dependency**

- **Summary answer:** Extractor boundaries reduce v2 rewrite risk.
- **Rationale:** If contextcore later emits model-controlled stage artifacts, the E2E report should add an extractor implementation rather than rewrite orchestration. A small extractor registry is a low-cost architecture seam.
- **Assumptions / conditions:** v1 stages already map to named extractor functions.
- **Suggested improvements:** Add `StageExtractor` contract with `supports(path)`, `extract(path)`, and `confidence`.

**Focus 7 — Capability score validity**

- **Summary answer:** Score trust improves when progress and stage metadata are visible during the run.
- **Rationale:** Long-running comparisons should expose current stage, model, retry count, and partial score availability. That operational feedback reduces user anxiety and makes failures easier to interpret.
- **Assumptions / conditions:** Minimal stdout progress and optional OTel spans are acceptable for v1.
- **Suggested improvements:** Add per-stage progress events and OTel span attributes.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | Ops | medium | Add an **artifact index** emitted as `artifact-index.json` plus human `ARTIFACTS.md`, listing each artifact's producer (`contextcore`/`startd8`), stage, model scope, path, checksum, and whether it is shared or per-model. | Batch outputs will contain many files; an index is low effort and high value for debugging, support, and onboarding. | `S6 — Ranked report` | Fixture run emits index entries for shared preamble, ingestion seed, prime result, and reports |
| R4-S2 | Interfaces | medium | Add named **run profiles**: `quick`, `standard`, and `audit`, each mapping to defaults for budgets, retention, replay bundle, report detail, and smoke/report-only behavior; explicit flags override profile defaults. | Profiles reduce CLI complexity and let end users choose intent without learning every operational flag. | `S7 — Orchestration & flags` | CLI test verifies profile defaults and explicit flag override precedence |
| R4-S3 | Ops | medium | Emit per-stage progress events and optional OTel spans with attributes for `batch_id`, `comparison_mode`, `model`, `stage`, `attempt`, `status`, `duration_ms`, and `cost_source`. | Long serial runs need live observability; this also aligns with the repository's ContextCore/OTel patterns. | New `S8 — Observability` | Test captures progress callbacks or span attributes for a mock run |
| R4-S4 | Risks | medium | Define CLI **exit-code semantics**: e.g. `0` all required stages succeeded, `1` completed with model/stage failures and report emitted, `2` invalid inputs/preflight failure, `3` shared preamble failed, `4` internal harness error. | CI and scripts need stable behavior distinct from ranked model outcomes. | `S7 — Orchestration & flags` | CLI tests assert exit codes for invalid input, partial model failure, and shared preamble failure |
| R4-S5 | Architecture | medium | Add a small **stage extractor registry** so contextcore, plan-ingestion, and prime metrics are parsed by named extractors with version and confidence metadata. | Future contextcore model flags or artifact changes can be handled by adding/updating extractors instead of entangling report code with stage orchestration. | `S5 — extraction` | Unit test registers a fake extractor and verifies report payload includes extractor version/confidence |
| R4-S6 | Validation | low | Add a **worked example** to the plan's validation strategy: tiny plan/requirements inputs, two mock models, expected output tree, and expected report snippets. | A concrete example is the fastest way to align implementers and reviewers on the user-facing workflow. | New validation subsection after `S7` | Example can be run locally without provider keys and matches documented tree |
| R4-S7 | Ops | low | Add opt-in **shared preamble reuse** guarded by frozen input hashes, contextcore version, and shared artifact checksums (`--reuse-shared-preamble <batch-root>`). | Users often iterate over model lists; safe reuse saves time while preserving the identical-input guarantee. | `S1 — Shared manifest preamble` and `S7` | Reuse succeeds only when input/tool hashes match; mismatch forces fresh preamble |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-S1: Report-only mode becomes more valuable with an artifact index and extractor registry.
- R3-S3: Frozen input hashes are the prerequisite for safe shared-preamble reuse.
- R3-S4: Readiness preflight should include tool-version capture and profile-expanded settings.
- R2-S1: Batch manifest should be the source for artifact index and exit-code report metadata.
- R2-S8: Mock smoke testing should include artifact-index, profile, and exit-code assertions.

## Requirements Coverage Matrix — R4

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Conceptual framing | Approach; S6 | Partial | Artifact index should make shared vs per-model artifact scope visible |
| FR-2 Model propagation | S3/S4/S7 | Partial | Tool-version capture should accompany model capture to explain comparison drift |
| FR-3 Deterministic stages | S1/S3 | Full | Shared preamble reuse must verify deterministic input/tool hashes |
| FR-4 Isolation | S2 | Partial | Artifact index should identify allowed shared artifacts and per-model artifacts |
| FR-5 Independent failure | S2-S4 | Partial | Exit-code semantics needed for partial completion in CI |
| FR-6 Serial execution | S7 | Partial | Progress events needed during long serial runs |
| FR-7 Reuse run-atomic.sh | Approach; S1-S4 | Partial | Artifact index should expose which orchestration path produced each artifact |
| FR-8 Per-stage outcomes | S5 | Partial | Extractor registry should record extractor version and confidence |
| FR-9 Aggregate report | S5/S6 | Partial | Add artifact index, profiles, and OTel/progress metadata to user-facing outputs |
| FR-10 Reuse helpers | S2/S4/S5 | Full | Extractor registry can wrap existing helpers |
| FR-11 Invocation | S7 | Partial | Add profiles, exit-code policy, and shared-preamble reuse flag |
| FR-12 Dry-run | S7 | Partial | Dry-run should show expanded profile defaults |
| FR-13 Command shape | S7 | Full | — |

#### Review Round R5

- **Reviewer**: gpt-5.5
- **Date**: 2026-06-02 03:46:00 UTC
- **Scope**: Fresh-agent pass for comparison validity, baseline deltas, config ergonomics, budget enforcement, and portability

**Executive summary**

- R1-R4 make the run honest, debuggable, replayable, and observable; R5 targets how users configure and interpret comparisons at decision time.
- Add a **comparison spec file** so complex batches are reviewable, repeatable, and less error-prone than long CLI invocations.
- Add a **baseline model and pairwise delta view** so users can see what each candidate improves or worsens relative to a known control.
- Add **stage artifact diffs** between per-model seeds/reports so E2E differences are explainable rather than only ranked.
- Add a **run validity verdict** separate from model ranking to say whether the comparison itself is trustworthy.
- Add a **budget ledger and stop policy** so global budget enforcement is auditable, not just a final number.
- Record and optionally randomize serial execution order to reduce time/order bias.
- Add a portable archive option for sharing a redacted, self-contained comparison package.

### Sponsor focus — R5 delta answers

**Focus 1 — Cross-tool / cross-repo boundary**

- **Summary answer:** A run-level validity verdict should explicitly assess whether the v1 boundary was respected.
- **Rationale:** Prior rounds make artifacts and modes visible; a validity gate can summarize whether shared preamble hashes, per-model model pins, required artifacts, and score inputs passed. This avoids burying an invalid comparison under a ranked table.
- **Assumptions / conditions:** R1-R4 manifest, checksums, and status fields exist.
- **Suggested improvements:** Add `comparison_validity: valid|warning|invalid` with reasons before model rankings.

**Focus 2 — Shared contextcore preamble vs per-model**

- **Summary answer:** Stage diffs help users see what changed after the shared handoff.
- **Rationale:** With a shared preamble, the interesting divergence starts at plan-ingestion. A diff pack comparing `prime-context-seed.json` and selected downstream metrics across models makes the abstraction tangible to end users.
- **Assumptions / conditions:** Seeds are JSON and can be normalized before diffing.
- **Suggested improvements:** Add normalized seed/metric diff artifacts under `batch/_diffs/`.

**Focus 3 — Per-stage cost attribution**

- **Summary answer:** Budget enforcement needs a ledger, not only report columns.
- **Rationale:** Cost reporting after the fact does not explain why a later model was skipped or why a stage was stopped. A ledger that records reserved, spent, estimated, and remaining budget before each stage makes budget behavior auditable.
- **Assumptions / conditions:** Exact cost can be unknown during a stage, so estimates and post-stage reconciliation are both recorded.
- **Suggested improvements:** Add `budget-ledger.jsonl` with pre/post entries per stage.

**Focus 4 — Model threading mechanics**

- **Summary answer:** A comparison spec file reduces threading mistakes.
- **Rationale:** Long CLI invocations with many models, profiles, budgets, and retry settings are easy to mis-run. A YAML/JSON spec checked into docs or CI makes the model list and mode reviewable before execution.
- **Assumptions / conditions:** CLI flags can override spec values with documented precedence.
- **Suggested improvements:** Add `--spec comparison.yaml` and a generated `effective-spec.json`.

**Focus 5 — Isolation correctness**

- **Summary answer:** Portable archives should be redacted and scoped to outputs, not workdirs by default.
- **Rationale:** Users will want to share results with collaborators. An archive command can package reports, manifests, diffs, and replay metadata while excluding bulky or sensitive project copies unless explicitly requested.
- **Assumptions / conditions:** R2 redaction and R4 artifact index exist.
- **Suggested improvements:** Add `--export-archive` after report generation.

**Focus 6 — Deferred cross-repo dependency**

- **Summary answer:** Spec files and effective specs make v1/v2 migration cleaner.
- **Rationale:** When contextcore model flags arrive, the spec can grow a `contextcore_model` or `mode: full_e2e_v2` field without changing every caller's shell invocation.
- **Assumptions / conditions:** Spec schema is versioned.
- **Suggested improvements:** Add `spec_version` and reject unknown future versions safely.

**Focus 7 — Capability score validity**

- **Summary answer:** Pairwise deltas and validity warnings make ranking more actionable than a single winner.
- **Rationale:** Users need to know whether a model won because it improved a meaningful metric, avoided failure, or merely had lower cost under noisy conditions. Baseline deltas plus validity reasons turn ranking into a decision aid.
- **Assumptions / conditions:** A baseline may be explicit or default to the first listed model.
- **Suggested improvements:** Add `--baseline-model` and a delta table in Markdown/JSON.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Interfaces | high | Add a versioned **comparison spec file** (`--spec comparison.yaml|json`) covering inputs, models, profile, budgets, output root, retry policy, baseline model, and report options; emit `effective-spec.json` after CLI overrides. | Complex comparisons will outgrow flags; a spec file is easier to review, commit, rerun, and migrate to v2. | `S7 — Orchestration & flags` | Fixture spec + CLI override yields expected `effective-spec.json` |
| R5-S2 | Validation | high | Add a run-level **comparison validity verdict** (`valid`, `warning`, `invalid`) with reasons before model ranking. Check minimum successful models, required artifacts, model-pin verification, input hashes, cost confidence, and seed divergence. | A ranked table should not imply the comparison is trustworthy when core validity checks failed. | `S5/S6` | Missing model-pin artifact marks run `invalid`; missing optional cost marks `warning` |
| R5-S3 | Data | medium | Add a **baseline/delta report** with `--baseline-model`; show per-model deltas for score, cost, duration, stage status, ingestion metrics, and prime quality relative to the baseline. | End users often compare candidates against a known current/default model, not only absolute rank. | `S6 — Ranked report` | Markdown and JSON include delta table for selected baseline |
| R5-S4 | Data | medium | Emit normalized **stage diff artifacts** under `batch/_diffs/`: seed JSON diffs, metric deltas, and a short Markdown "where models diverged" summary. | E2E value comes from seeing how upstream artifacts differ; diffs explain why one model won or failed. | `S3/S5/S6` | Two mock model seeds produce deterministic diff files |
| R5-S5 | Ops | medium | Add a **budget ledger and stop policy**: write `budget-ledger.jsonl` entries before/after each stage, reconcile estimated vs actual cost, and skip remaining optional/per-model stages when global budget would be exceeded. | `--global-budget` exists in the plan, but users need auditable enforcement and clear skip reasons. | `S7` and `Risks` | Simulated budget exhaustion skips later model and report shows `budget_exceeded` |
| R5-S6 | Risks | low | Record serial **execution order** and add optional `--model-order listed|random --order-seed <int>` to expose or reduce order bias from time-of-day, provider incidents, or local load. | Serial runs are cost-attribution friendly but order can bias duration/failure outcomes; recording and optional randomization is cheap. | `S7 — Orchestration & flags` | Report includes order and seed; randomized order is reproducible |
| R5-S7 | Ops | low | Add `--export-archive` to produce a redacted portable archive containing reports, manifest, artifact index, diffs, effective spec, replay metadata, and logs, excluding workdirs by default. | Users need to share comparison evidence without copying huge or sensitive project trees. | `S6/S7` | Archive fixture excludes workdir and contains redacted manifest/report files |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R4-S1: Artifact index is prerequisite for safe portable archives and diff navigation.
- R4-S2: Run profiles pair well with a versioned spec file.
- R4-S4: Exit-code semantics should incorporate the run-level validity verdict.
- R3-S1: Report-only regeneration should also rebuild baseline/delta and diff outputs.
- R2-S1: Batch manifest remains the backing data source for validity checks and budget ledger references.

## Requirements Coverage Matrix — R5

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Conceptual framing | Approach; S6 | Partial | Add run-level validity verdict and seed diff summary to explain whether v1 comparison assumptions held |
| FR-2 Model propagation | S3/S4/S7 | Partial | Effective spec should preserve exact requested and resolved model specs |
| FR-3 Deterministic stages | S1/S3 | Full | — |
| FR-4 Isolation | S2 | Partial | Portable archive should exclude workdirs by default to avoid leaking isolated project copies |
| FR-5 Independent failure | S2-S4 | Partial | Budget skip and validity verdict should distinguish skipped, failed, and invalid model rows |
| FR-6 Serial execution | S7 | Partial | Execution order should be recorded and optionally randomized/reproducible |
| FR-7 Reuse run-atomic.sh | Approach; S1-S4 | Partial | Effective spec should record the selected orchestration path |
| FR-8 Per-stage outcomes | S5 | Partial | Add baseline deltas and normalized stage diffs |
| FR-9 Aggregate report | S5/S6 | Partial | Add validity verdict, baseline delta table, diff summary, and archive export |
| FR-10 Reuse helpers | S2/S4/S5 | Full | Existing extractors can feed validity and delta calculations |
| FR-11 Invocation | S7 | Partial | Add spec file, baseline model, model order, and archive flags |
| FR-12 Dry-run | S7 | Partial | Dry-run should print effective spec, execution order, and budget ledger preview |
| FR-13 Command shape | S7 | Full | — |
