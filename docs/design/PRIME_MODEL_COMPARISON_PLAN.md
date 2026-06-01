# Prime Contractor Multi-Model Comparison Harness — Implementation Plan

**Version:** 1.0 (post-planning, paired with requirements v0.2)
**Date:** 2026-06-01
**Status:** Plan

> Traces to `PRIME_MODEL_COMPARISON_REQUIREMENTS.md`. Built by planning against the real
> codebase; discoveries fed back into requirements §0.

## Approach

A single standalone script, `scripts/run_prime_model_comparison.py`, modeled on
`scripts/run_prime_parity_benchmark.py`. It loops serially over a list of model specs; for each,
it (1) materializes an isolated sandbox, (2) shells out to `run_prime_workflow.py` with the model
pinned, (3) extracts metrics from the run's artifacts, then aggregates and ranks. No SDK/workflow
code changes are required for v1.

## Step-by-step

### S1 — CLI & config (FR-13, FR-14)
`argparse`: `--seed` (path, required), `--model` (repeatable, ≥2 required), `--batch-root`
(output root), `--cost-budget` (per-run, optional), `--isolation {copy,worktree}` (default `copy`),
`--dry-run`. Validate ≥2 distinct models. Derive a filesystem-safe slug per model spec
(`anthropic:claude-opus-4-8` → `anthropic-claude-opus-4-8`).

### S2 — Sandbox materialization (FR-1, FR-3) — *mandatory per discovery D4*
For each model, create `runs/<batch>/<slug>/` containing `workdir/` and `output/`.
`workdir/` = an independent copy of the target source tree, because `integration_engine` merges
generated code **into** `project_root` (`integration_engine.py:437`, `project_root / rel_path`) and
writes `.prime_contractor_state.json` + `.startd8/state/` there.
- `copy` mode: `shutil.copytree(source, workdir, ignore=...)` excluding `.git`, `.venv`,
  `.startd8`, `node_modules`, build dirs.
- `worktree` mode (optional): `git worktree add` for large/clean repos.
Source tree path = the seed's project (or an explicit `--source` arg). Each sandbox is independent,
so a crash in one cannot touch another (FR-3).

### S3 — Per-model invocation (FR-4, FR-5, FR-6, FR-7, FR-8)
Build the command (subprocess, `check=False`, capture stdout/stderr tails — exactly the parity
benchmark's `_run_command`):
```
python3 scripts/run_prime_workflow.py \
  --seed <shared seed>            # FR-5: same seed, never mutated
  --project-root runs/<b>/<slug>/workdir \
  --output-dir   runs/<b>/<slug>/output \
  --lead-agent   <model> --drafter-agent <model>   # FR-7: pin both paths
  --force-regenerate                                # FR-8: no Mottainai reuse
  [--cost-budget N]
```
Do **not** pass `--complexity-routing` or `--micro-prime` (both default off → all generation flows
through the pinned lead/drafter model — discovery D1). Record wall-clock start/end timestamps per
run (feeds S5 cost attribution). Loop is strictly serial (FR-4).

### S4 — Capability metric extraction (FR-9, FR-10) — *requires new extractor, discovery D2*
Two extractors over **existing** artifacts (no in-workflow code → satisfies NR-2):
- `prime-result*.json` (thin): `processed`, `succeeded`, `failed`, `success` → completion_rate =
  succeeded/processed, failed_rate.
- `prime-postmortem-report.json` (rich): `avg_assembly_delta`, and per-feature `features[].`
  `disk_quality_score` / `assembly_delta` / `semantic_error_count` → mean disk_quality_score,
  total semantic_error_count. (Reuse `_load_json` + `_latest_match` helpers.)
Drop `truncation_incidence`/`design_agreement_rate` from the prime metric set (Artisan-only — D3).

### S5 — Cost attribution (FR-12) — *time-window, no plumbing, discovery D5*
After each run, query the cost store for the run's window:
`CostStore(~/.startd8/costs.db).query(...)` filtered by `timestamp BETWEEN start AND end`
(the `idx_cost_timestamp` index exists). Serial execution guarantees windows don't overlap.
Derive `total_cost` and `cost_per_succeeded_feature`. (Optional later: set a per-run cost-context
tag via `set_cost_context(tags=[run_id])` if the entry point is extended.)

### S6 — Ranking & report (FR-11)
Build a per-metric comparison table (one column per model) + deltas vs. the best, reusing the
parity benchmark's markdown builder shape. Default ranking: **highest mean disk_quality_score**,
tie-broken by **lowest cost_per_succeeded_feature**; show completion_rate and semantic_error_count
alongside. Emit `comparison-report.md` and `comparison-report.json` to `runs/<batch>/`. Name a
recommended winner with a one-line rationale.

### S7 — Dry-run (FR-14)
With `--dry-run`, print the sandbox layout and the exact per-model command lines; do not copy trees
or execute. (Pass through to the workflow's own `--dry-run` is *not* used — we stop before invoking.)

## Risks
- **LLM nondeterminism (OQ-8):** single run per model is noisy. v1 documents this; report header
  states "single-run, indicative not statistical." Schema leaves room for `--repeats` later.
- **Sandbox copy cost:** large repos make `copytree` slow; `--isolation worktree` mitigates.
- **Cost-window precision:** other concurrent SDK activity on the same machine could land in a
  run's window. Mitigation: run comparisons on an otherwise-idle machine; document it. Tagging is
  the robust future fix.
- **Partial failure:** a model that errors out yields partial artifacts; extractors must treat
  missing fields as `None` and the report must render "incomplete" rather than crash (FR-3).

## Test strategy
- Unit: slug derivation, command construction (assert pinned agents + no routing flags), metric
  extraction against fixture `prime-result.json` / `prime-postmortem-report.json`, ranking logic.
- Integration (mock model): two `mock:` model runs end-to-end into a temp batch root; assert two
  isolated sandboxes, two artifact sets, one ranked report.
- No live-model test in CI (cost/nondeterminism); provide a documented manual smoke command.

## Out of scope (v1)
Parallel execution; per-tier model maps; repeat sampling; dashboard; registered-workflow packaging.
