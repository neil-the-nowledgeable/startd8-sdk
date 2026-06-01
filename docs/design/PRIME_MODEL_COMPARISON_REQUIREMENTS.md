# Prime Contractor Multi-Model Comparison Harness — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-01
**Status:** Draft
**Author:** neil (with Claude)
**Paired plan:** `PRIME_MODEL_COMPARISON_PLAN.md` v1.0

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). The planning pass against the
> real codebase revealed 6 corrections — notably one that flips a requirement from "nice-to-have
> hygiene" to "mandatory for correctness," and one that exposes a metric source the precedent script
> doesn't read.

| # | v0.1 Assumption | Planning Discovery | Impact |
|---|-----------------|--------------------|--------|
| D1 | FR-7: must **disable** complexity-routing and Micro Prime to pin the model | Both are opt-in (`store_true`, `default=False` in `run_prime_workflow.py:207,236`) | FR-7 simplified: just set `--lead-agent` + `--drafter-agent` and *don't enable* routing/micro-prime. No disable flags needed. |
| D2 | FR-9/FR-10: capability metrics come from `prime-result*.json` | `prime-result.json` is thin (`processed/succeeded/failed/success`). Real capability metrics (`disk_quality_score`, `assembly_delta`, `semantic_error_count`) live in **`prime-postmortem-report.json`**, which the parity-benchmark precedent does **not** read | A **new extractor** for the postmortem report is required (still reads existing artifacts → no in-workflow code, NR-2 holds). FR-10 metric list corrected. |
| D3 | FR-10: includes `truncation_incidence` + `design_agreement_rate` | Those are **Artisan-only** (`workflow-execution-report.json`); prime artifacts lack them (parity benchmark returns `None` for prime) | Dropped from the prime metric set. |
| D4 | FR-1: separate project-root is isolation **hygiene** | `integration_engine` merges generated code **into** `project_root` (`integration_engine.py:437`) and writes state there | FR-1 **strengthened to mandatory**: a per-model project-root copy is required for *correctness* (runs mutate the source tree), not just cleanliness. |
| D5 | OQ-3: may need to **inject a per-run cost-DB path** (plumbing through the workflow) | Cost store has `query()`/`get_summary()` with a `timestamp` index (`store.py:114`); serial runs → non-overlapping windows | Cost attribution via **time-window filtering**, zero plumbing. Tagging is a future nicety, not required. |
| D6 | OQ-5: unsure where the harness lives | Precedent `run_prime_parity_benchmark.py` is a standalone subprocess-driving script | Resolve to a **standalone `scripts/` harness** for v1. |

**Resolved open questions:**
- **OQ-1 → Per-model working-tree copy (mandatory).** `copy` mode default (`shutil.copytree`),
  `worktree` mode optional for large repos. Required because runs mutate `project_root` (D4).
- **OQ-2 → Headline metrics + ranking defined.** Rank by mean `disk_quality_score`, tie-break by
  `cost_per_succeeded_feature`; show completion_rate, failed count, `avg_assembly_delta`,
  `semantic_error_count`, total cost. Per-metric table + named winner.
- **OQ-3 → Time-window cost filtering** (serial guarantees non-overlap); no DB-path injection (D5).
- **OQ-4 → Confirmed.** Routing/micro-prime off by default; pinning lead+drafter routes 100% of
  generation through one model. `--tier3-agent` is irrelevant when routing is off.
- **OQ-5 → Standalone script** `scripts/run_prime_model_comparison.py` (D6).
- **OQ-6 → Flags resolved.** Pin: `--lead-agent`/`--drafter-agent`; isolate: `--project-root`/
  `--output-dir`; freshness: `--force-regenerate`. Do **not** pass `--complexity-routing`/`--micro-prime`.
- **OQ-7 → Schemas resolved.** `prime-result.json`: `processed/succeeded/failed/success`.
  `prime-postmortem-report.json`: `avg_assembly_delta` + `features[].{disk_quality_score,`
  `assembly_delta, semantic_error_count}`.
- **OQ-8 → Single-run v1 with explicit nondeterminism caveat** in the report header; schema reserves
  room for `--repeats` (NR-4).

---

## 1. Problem Statement

The SDK can benchmark models on **single test prompts** (`startd8 run-benchmark` →
latency/tokens/cost rankings). That measures raw generation economics, not whether a model
can actually *build the thing*. We want to evaluate models against **real capability**: give
2+ models the same requirements + plan, have each drive a full PrimeContractorWorkflow code-gen
run in complete isolation, then score the **generated code** (disk quality, contract compliance,
review pass rate, cost-per-feature) and rank the models.

A direct precedent exists: `scripts/run_prime_parity_benchmark.py` runs two *engines*
(Artisan vs Prime) sequentially in separate output dirs and emits a delta report. This feature
generalizes that to vary the **model** instead of the engine.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Prompt-level benchmark | `run-benchmark` ranks models on a toy prompt | No capability/code-gen signal |
| Prime Contractor run | Runs one model on one seed, output-dir configurable | No notion of "same seed, N models, isolated" |
| Parity benchmark | Compares Artisan vs Prime engines, serial, delta report | Hardwired to 2 engines, not parameterized by model |
| Cross-run scoring | `prime-postmortem-report.json` / `kaizen-metrics.json` per run | Not aggregated/ranked across models |

## 2. Goals & Non-Goals

**Goal:** A serial harness that runs the same seed through PrimeContractor once per model, each in
a fully isolated sandbox, then produces a ranked capability+cost comparison report.

## 3. Requirements

### Isolation
- **FR-1** *(mandatory — D4)* Each model run executes in its own isolated working-tree **copy** of
  the target source (separate `--project-root`) AND its own `--output-dir`. This is required for
  correctness, not just hygiene: `integration_engine` merges generated code into `project_root` and
  writes resume/cache state there, so runs that shared a project-root would corrupt each other.
  Isolation mechanism is `copy` (default) or `worktree` (opt-in for large repos).
- **FR-2** Runs touch no shared mutable state except the global cost DB (`~/.startd8/costs.db`),
  which is append-only and safe under serial execution.
- **FR-3** A run's failure (crash, non-zero exit, budget exceeded) must not corrupt or block other
  models' runs; each is independently recoverable.

### Execution
- **FR-4** Execution is **serial** in v1 (one model fully completes before the next starts).
  Parallel execution is a non-goal for v1 but the design must not preclude it later.
- **FR-5** All models receive the **identical seed** (requirements + plan + seed tasks). The harness
  must not mutate the seed between runs.
- **FR-6** The harness invokes the existing `run_prime_workflow.py` entry point per model (subprocess),
  not a reimplementation of the workflow.

### Model pinning (fair comparison)
- **FR-7** *(simplified — D1)* All generation paths for a run are pinned to the single model under
  test by setting `--lead-agent` AND `--drafter-agent` to the same spec. Complexity routing and
  Micro Prime are **opt-in** (off by default), so the harness simply must **not enable** them; no
  disable flags are needed. With routing off, `--tier3-agent` is never exercised.
- **FR-8** Mottainai generation-cache reuse is disabled per run (`--force-regenerate`) so each run
  reflects the model's own output, not reused artifacts.

### Scoring & reporting
- **FR-9** *(clarified — D2)* The harness scores each run from artifacts the workflow already
  produces, with **no new in-workflow scoring code**. It reads **both** `prime-result*.json` (thin:
  `processed/succeeded/failed/success`) **and** `prime-postmortem-report.json` (rich capability
  signal) — the latter is a new extractor the precedent script lacks but still consumes an existing
  artifact.
- **FR-10** *(corrected — D2, D3)* Captured metrics per model: `processed`/`succeeded`/`failed`
  counts and completion_rate; **mean `disk_quality_score`**; `avg_assembly_delta`; total
  `semantic_error_count`; total cost; and cost-per-succeeded-feature. `truncation_incidence` and
  `design_agreement_rate` are **excluded** (Artisan-only artifacts; absent from prime runs). Missing
  fields render as `N/A`, never crash.
- **FR-11** The harness emits a single ranked comparison report (markdown + JSON) showing per-metric
  values per model with deltas vs. the best, and a recommended winner, reusing the parity-benchmark
  report shape. Default ranking: highest mean `disk_quality_score`, tie-broken by lowest
  cost-per-succeeded-feature. The report header states results are single-run/indicative (OQ-8).
- **FR-12** *(resolved — D5)* Cost per model is attributed via **time-window filtering** of the
  shared cost DB (`CostStore.query()` over the run's start/end timestamps). Serial execution (FR-4)
  guarantees non-overlapping windows, so no per-run DB-path injection or workflow plumbing is needed.

### Config & invocation
- **FR-13** The user specifies: the seed, the list of model specs, and a batch output root. The
  harness creates `runs/<batch>/<model-slug>/{workdir,output}/` automatically.
- **FR-14** A dry-run mode prints the planned per-model commands and sandbox layout without executing.

## 4. Non-Requirements

- **NR-1** No parallel execution in v1.
- **NR-2** No new in-workflow scoring/metrics; only aggregation of existing artifacts.
- **NR-3** No per-tier model maps / routing-profile comparison in v1 (single-model-everywhere only).
- **NR-4** No statistical repeat-sampling in v1 (single run per model), though the schema should allow it.
- **NR-5** No UI/dashboard in v1 (markdown + JSON report only).
- **NR-6** Not a replacement for `run-benchmark`; complementary.

## 5. Open Questions

All v0.1 open questions (OQ-1…OQ-8) were **resolved during the planning pass** — see §0 Planning
Insights for resolutions. Remaining questions deferred beyond v1:

- **OQ-9** Repeat-sampling design (K runs/model, mean±variance) — schema reserves `--repeats`; method TBD.
- **OQ-10** Per-run cost-context tagging (vs. time-window) if/when bounded-parallel mode is added.
- **OQ-11** Whether to graduate the script into a registered workflow once the metric set stabilizes.

---

*v0.2 — Post-planning self-reflective update. 1 requirement strengthened (FR-1: hygiene → mandatory),
3 corrected (FR-7 simplified, FR-9/FR-10 metric source + set fixed), 1 resolved without feared
plumbing (FR-12), 8 open questions resolved, 3 new ones deferred to post-v1. ~36% of requirements
revised — above the 30% heuristic, confirming the draft was premature in the metric-source and
isolation areas, exactly where planning caught it at document cost.*
