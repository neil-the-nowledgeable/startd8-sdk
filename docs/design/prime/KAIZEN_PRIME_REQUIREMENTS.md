# Kaizen for Prime Contractor — Requirements

> **Version:** 0.5.0
> **Status:** DRAFT
> **Date:** 2026-03-07
> **Scope:** Systematic continuous improvement of PrimeContractorWorkflow effectiveness through run-over-run analysis. Core kaizen logic (metrics, index, retention) lives in startd8-sdk; cap-dev-pipe invokes it but is not required
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md)
> **Depends on:** [PRIME_CONTRACTOR_PROMPT_AUDIT_FINDINGS.md](../PRIME_CONTRACTOR_PROMPT_AUDIT_FINDINGS.md), cap-dev-pipe orchestration scripts, existing post-mortem system (`prime_postmortem.py`), walkthrough mode
> **Implementation Home:** `~/Documents/dev/cap-dev-pipe/` (pipeline orchestration) + `~/Documents/dev/startd8-sdk/` (SDK analysis modules)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Prime Post-Mortem Parity (REQ-KZ-1xx)](#3-layer-1--prime-post-mortem-parity-req-kz-1xx)
4. [Layer 2 — Prompt-Response Pairing (REQ-KZ-2xx)](#4-layer-2--prompt-response-pairing-req-kz-2xx)
5. [Layer 3 — Run Metrics & Archive Index (REQ-KZ-3xx)](#5-layer-3--run-metrics--archive-index-req-kz-3xx)
6. [Layer 4 — Cross-Run Aggregation (REQ-KZ-4xx)](#6-layer-4--cross-run-aggregation-req-kz-4xx)
7. [Layer 5 — Feedback Loop (REQ-KZ-5xx)](#7-layer-5--feedback-loop-req-kz-5xx)
8. [Layer 6 — Prompt Quality Correlation (REQ-KZ-6xx)](#8-layer-6--prompt-quality-correlation-req-kz-6xx)
9. [Existing Capabilities Leveraged](#9-existing-capabilities-leveraged)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Verification Strategy](#11-verification-strategy)
12. [Cross-References](#12-cross-references)
13. [Convergent Review — Round R1 (Triaged)](#convergent-review--round-r1-triaged)

---

## 1. Overview

### 1.1 Vision

The Prime Contractor is operated through the Capability Delivery Pipeline (`cap-dev-pipe`), which already provides run isolation via `run-atomic.sh` (timestamped directories, state archiving, provenance chain). The pipeline also integrates post-mortem analysis for the artisan route (`run-artisan.sh:364-388`). This document extends the pipeline to systematically preserve, analyze, and feed back run outputs for the prime contractor route, so that each run improves upon the last.

### 1.2 Existing Infrastructure (What We Have)

| Component | Location | What It Provides |
|-----------|----------|-----------------|
| `run-atomic.sh` | cap-dev-pipe | Timestamped run dirs, state archiving, `latest` symlink, `run-metadata.json` |
| `run-prime-contractor.sh` | cap-dev-pipe | Prime execution with provenance-driven seed discovery |
| `run-artisan.sh:364-388` | cap-dev-pipe | Post-mortem verdict display (artisan only) |
| `run-compare.sh` | cap-dev-pipe | Dual-route comparison report generation |
| `resolve-provenance.py` | cap-dev-pipe | Provenance → config translation |
| `prime_postmortem.py` | startd8-sdk | Root-cause classification, pattern detection, lessons |
| `run_prime_postmortem.py` | startd8-sdk/scripts | Standalone post-mortem runner with auto-discovery |
| `_persist_walkthrough_prompts()` | startd8-sdk | Prompt file serialization (walkthrough only) |
| `run_super_walkthrough.py` | startd8-sdk/scripts | Cross-contractor prompt analysis |
| `WalkthroughPromptEvaluator` | startd8-sdk | Requirement/constraint coverage scoring |

### 1.3 Gaps to Close

| Gap | Problem | Layer |
|-----|---------|-------|
| K-1 | No prompt capture during real runs | Layer 2 |
| K-2 | No cross-run metric aggregation | Layer 4 |
| K-3 | No feedback loop from analysis to config | Layer 5 |
| K-4 | No prompt-response quality correlation | Layer 6 |
| K-5a | Prime route has no post-mortem in pipeline | Layer 1 |
| K-5b | No run metrics index for archive querying | Layer 3 |

Note: K-5 (run archive) is **already partially closed** by `run-atomic.sh`.

### 1.4 Success Criteria

1. Prime contractor runs produce post-mortem reports at parity with artisan (K-5a closed)
2. Every run's key metrics are extracted into a queryable index (K-5b closed)
3. Prompts are persisted alongside responses during real runs (K-1 closed)
4. A script can aggregate metrics across N archived runs (K-2 closed)
5. Post-mortem insights can influence the next run's configuration (K-3 closed)
6. Prompt characteristics can be correlated with output quality (K-4 closed)

### 1.5 Constraints

- **Leverage existing orchestration** — all changes flow through cap-dev-pipe scripts and existing SDK analysis modules
- **No new LLM calls** for Kaizen analysis — all analysis is deterministic or uses existing outputs
- **Minimal runtime overhead** — archiving and prompt capture must not measurably slow the pipeline
- **Backward compatible** — existing CLI flags, `run-atomic.sh` arguments, and SDK APIs unchanged
- **Prime route scoped** — this document covers the prime contractor route only. The artisan route already has its own post-mortem integration (`run-artisan.sh:364-388`). Shared infrastructure (Layers 3-4: index, trends) is route-agnostic and can serve both routes, but Layers 1-2 and 5-6 target prime-specific code paths
- **Secret safety** — prompt/response persistence must support optional redaction rules and allow opt-out to avoid leaking sensitive data

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status | Closes |
|--------|-------------|-----------|--------|--------|
| **Layer 1 — Prime Post-Mortem Parity** | | | | |
| REQ-KZ-100 | Post-mortem invocation in `run-prime-contractor.sh` | cap-dev-pipe | PLANNED | K-5a |
| REQ-KZ-101 | Post-mortem output in run archive | cap-dev-pipe | PLANNED | K-5a |
| REQ-KZ-102 | Post-mortem summary display | cap-dev-pipe | PLANNED | K-5a |
| **Layer 2 — Prompt-Response Pairing** | | | | |
| REQ-KZ-200 | Prompt persistence during real runs | startd8-sdk | PLANNED | K-1 |
| REQ-KZ-201 | Response persistence alongside prompts | startd8-sdk | IMPLEMENTED | K-1 |
| REQ-KZ-202 | Archive prompt directory into run dir | cap-dev-pipe | PLANNED | K-1 |
| REQ-KZ-203 | Reuse existing walkthrough persistence code | startd8-sdk | PLANNED | K-1 |
| REQ-KZ-204 | Prompt/response redaction & opt-out | startd8-sdk | PLANNED | K-1 |
| **Layer 3 — Run Metrics & Archive Index** | | | | |
| REQ-KZ-300 | Per-run metrics extraction | startd8-sdk | IMPLEMENTED | K-5b |
| REQ-KZ-301 | Archive index file | startd8-sdk | IMPLEMENTED | K-5b |
| REQ-KZ-302 | Retention policy | startd8-sdk | IMPLEMENTED | K-5b |
| **Layer 4 — Cross-Run Aggregation** | | | | |
| REQ-KZ-400 | Cross-run trend script | cap-dev-pipe | PLANNED | K-2 |
| REQ-KZ-401 | Failure pattern persistence | cap-dev-pipe | PLANNED | K-2 |
| REQ-KZ-402 | Cost trend tracking | cap-dev-pipe | PLANNED | K-2 |
| **Layer 5 — Feedback Loop** | | | | |
| REQ-KZ-500 | Kaizen config file format | cap-dev-pipe | PLANNED | K-3 |
| REQ-KZ-501 | Post-mortem → kaizen suggestion generation | startd8-sdk | PLANNED | K-3 |
| REQ-KZ-502 | Config injection via `run-atomic.sh` | cap-dev-pipe | PLANNED | K-3 |
| REQ-KZ-503 | `--no-kaizen` bypass flag | cap-dev-pipe | PLANNED | K-3 |
| REQ-KZ-504 | Improvement verification | cap-dev-pipe | PLANNED | K-3 |
| **Layer 6 — Prompt Quality Correlation** | | | | |
| REQ-KZ-600 | Prompt characteristic extraction | startd8-sdk | PLANNED | K-4 |
| REQ-KZ-601 | Quality-prompt correlation script | cap-dev-pipe | PLANNED | K-4 |

---

## 3. Layer 1 — Prime Post-Mortem Parity (REQ-KZ-1xx)

**Closes:** Gap K-5a (prime route has no post-mortem in pipeline)

The artisan route already invokes post-mortem analysis and displays the verdict in `run-artisan.sh:364-388`. The prime route in `run-prime-contractor.sh` finishes without any post-mortem step. This layer adds parity.

### REQ-KZ-100: Post-Mortem Invocation in `run-prime-contractor.sh`

After the prime contractor finishes (successful or failed), `run-prime-contractor.sh` SHALL invoke the standalone post-mortem script against the run's output:

```bash
python3 "$SDK_ROOT/scripts/run_prime_postmortem.py" \
    --run-dir "$OUTPUT_DIR" \
    --output-dir "$OUTPUT_DIR"
```

**Leverages:**

- `scripts/run_prime_postmortem.py` already exists with `--run-dir` auto-discovery mode
- `_discover_artifacts()` in that script already handles finding `prime-result*.json`, seed files, and queue state
- The `OUTPUT_DIR` variable is already computed in `run-prime-contractor.sh:130`

**Implementation:** Add ~15 lines after the timing/exit-code block at `run-prime-contractor.sh:335`, mirroring the pattern from `run-artisan.sh:364-388`.

**Constraint:** Preserve the original prime contractor exit code. If the post-mortem step fails, log a warning and continue without altering the run's exit status.

### REQ-KZ-101: Post-Mortem Output in Run Archive

The post-mortem SHALL write its output files to the run's `plan-ingestion/` directory (same as other prime results):

- `prime-postmortem-report.json`
- `prime-postmortem-summary.md`
- `prime-postmortem-lessons.json`

**Leverages:** `run_prime_postmortem.py` already accepts `--output-dir` and writes these exact files. No SDK changes needed.

### REQ-KZ-102: Post-Mortem Summary Display

After the post-mortem runs, `run-prime-contractor.sh` SHALL display the verdict, score, task count, and lesson count, mirroring the artisan display pattern:

```bash
echo "  Post-Mortem Evaluation:"
python3 -c "
import json
r = json.loads(open('$PM_REPORT').read())
print(f'    Verdict: {r[\"aggregate_verdict\"]} (score: {r[\"aggregate_score\"]:.2f})')
print(f'    Features: {r[\"successful_features\"]}/{r[\"total_features\"]}')
..."
```

**Leverages:** The exact Python snippet pattern from `run-artisan.sh:374-386`, adapted for prime postmortem JSON field names.

---

## 4. Layer 2 — Prompt-Response Pairing (REQ-KZ-2xx)

**Closes:** Gap K-1 (no prompt capture during real runs)

### REQ-KZ-200: Prompt Persistence During Real Runs

When a `--kaizen` flag (or kaizen config file) is active, the Prime Contractor SHALL persist all LLM prompts to disk during real (non-walkthrough) runs. Prefer a run-isolated path:
`.startd8/kaizen-prompts/{run_id}/{feature_id}/` when `run_id` is available (from `run-metadata.json` or environment); otherwise fall back to `.startd8/kaizen-prompts/{feature_id}/`.

`feature_id` MUST be sanitized to prevent path traversal (e.g., replace `/` and `..`), and the directory is created if missing.

**Leverages:** `_persist_walkthrough_prompts()` (`prime_contractor.py:1779-1918`) already constructs and writes prompt files in exactly this directory layout. The implementation factors out the shared write logic so both walkthrough and real-run modes can call it.

**Key insight from Prompt Audit Findings:** "During real runs, these prompts are constructed identically but not persisted." The prompts are already built — they just need to be written at the point where they are sent to the LLM.

### REQ-KZ-201: Response Persistence Alongside Prompts

For each LLM phase (spec, draft, review), the raw LLM response text SHALL be persisted alongside the corresponding prompt files as `{phase}_response.md`.

**Implementation (2026-03-07):** Raw responses are forwarded via `GenerationResult.metadata` using per-phase keys (`spec_raw_response`, `draft_raw_response`, `review_raw_response`). The `LeadContractorGenerator` populates these from the workflow's `lc_summary` (`spec_raw`, `drafts_raw[-1].implementation`, `reviews_raw[-1].review_text`). The `PrimeContractorWorkflow._capture_response_files()` method reads these keys and writes `{phase}_response.md` files alongside the prompts.

**Size guard:** If a response exceeds a configurable limit (default 2 MB), persist a truncated version with a clear sentinel line (e.g., `<!-- TRUNCATED -->`) and record the original byte count in a sidecar JSON (`{phase}_response.meta.json`) to avoid oversized archives.

### REQ-KZ-202: Archive Prompt Directory Into Run Dir

After the prime contractor finishes, `run-atomic.sh` Phase 5 (post-run) SHALL archive the prompt directory from `.startd8/kaizen-prompts/` into the run directory alongside the existing state archiving:

```bash
KAIZEN_PROMPTS="$PROJECT_ROOT/.startd8/kaizen-prompts"
if [ -d "$KAIZEN_PROMPTS" ]; then
    cp -r "$KAIZEN_PROMPTS" "$RUN_DIR/kaizen-prompts"
    rm -rf "$KAIZEN_PROMPTS"
    echo "  Archived and removed: kaizen-prompts/"
fi
```

**Leverages:** `run-atomic.sh:510-517` already archives `.prime_contractor_state.json` and `.startd8/state/` into the run dir using the same copy-then-remove pattern (see lines 301-313). This follows that exact pattern.

**Constraint:** Only remove the source directory if the copy succeeds; on copy failure, preserve the original and log a warning.

### REQ-KZ-203: Reuse Existing Walkthrough Persistence Code

The prompt persistence for real runs SHALL reuse `_persist_walkthrough_prompts()` or a factored-out shared function. No duplication of prompt serialization logic.

**Implementation approach:** Extract `_persist_prompts(output_dir, feature_id, prompts_dict)` from `_persist_walkthrough_prompts()`. Both walkthrough and kaizen modes call the shared function.

### REQ-KZ-204: Prompt/Response Redaction & Opt-Out

Prompt and response persistence SHALL support optional redaction rules to avoid storing secrets. If a redaction config is present, apply it before writing any prompt/response file.

**Config discovery (deterministic):**

- File: `.startd8/kaizen-redactions.json` (project-root)
- Env: `KAIZEN_REDACTIONS` (JSON string)

**Format (example):**

```json
{
  "patterns": ["API_KEY=.*", "Authorization: Bearer .*"],
  "replacement": "[REDACTED]"
}
```

**Failure mode:** If redaction config is invalid or cannot be parsed, prompt/response persistence is **disabled for the run** and a warning is logged. This avoids accidental secret leakage
---

## 5. Layer 3 — Run Metrics & Archive Index (REQ-KZ-3xx)

**Closes:** Gap K-5b (no run metrics index for archive querying)

### REQ-KZ-300: Per-Run Metrics Extraction

After post-mortem completes, `run-prime-contractor.sh` SHALL extract key metrics into a `kaizen-metrics.json` file in the output directory:

```json
{
  "schema_version": "1.0",
  "run_id": "run-003-20260305T1430",
  "timestamp": "2026-03-05T14:30:00Z",
  "run_dir": "pipeline-output/online-boutique-python/run-003-20260305T1430",
  "route": "prime",
  "kaizen_enabled": true,
  "kaizen_config_source_run": "run-002-20260301T1010",
  "success_rate": 0.85,
  "pass_count": 12,
  "fail_count": 3,
  "total_cost_usd": 0.42,
  "cost_per_success_usd": 0.025,
  "total_features": 20,
  "successful_features": 17,
  "verdict": "PARTIAL",
  "top_root_causes": [{"cause": "DUPLICATE_IMPORT", "count": 4}]
}
```

**Note on `top_root_causes`:** Extracted from `pipeline_attribution[*].root_causes` (a `Dict[str, int]` per stage), aggregated across stages and sorted by count descending. The `cross_feature_patterns` field provides pattern-level data (`.description`, `.frequency`) but not per-cause counts.

**Note on `wall_clock_seconds`:** Not present in `PrimePostMortemReport`. Available as `$RUN_ELAPSED` in the shell script (`run-prime-contractor.sh`). If needed in metrics, inject from the shell layer rather than the SDK postmortem.

**Note on `run_id`/`timestamp`:** Prefer `run-metadata.json` (written by `run-atomic.sh`) as the source of truth to avoid timezone drift and ensure consistency with the run directory name.

**Note on `kaizen_enabled`:** Derive from the presence of an injected kaizen config and the `--no-kaizen` flag; this allows trend scripts to filter baseline runs.

**Leverages:** All data (except wall clock) is already in the post-mortem report JSON. This is a deterministic extraction — a small Python snippet in the shell script (like the existing summary display) or a `--emit-metrics` flag on `run_prime_postmortem.py`.

**Implementation:** Add a `--emit-metrics` flag to `scripts/run_prime_postmortem.py` that writes `kaizen-metrics.json` alongside the existing report files. Invoke with that flag from `run-prime-contractor.sh`.

### REQ-KZ-301: Archive Index File

`run_prime_postmortem.py --update-index` SHALL append a summary entry to `pipeline-output/{project}/kaizen-index.json`:

```json
{
  "schema_version": "1.0",
  "runs": [
    {
      "run_id": "run-003-20260305T1430",
      "timestamp": "20260305T1430",
      "run_dir": "/path/to/run-003-20260305T1430",
      "metrics_path": "/path/to/run-003-20260305T1430/plan-ingestion/kaizen-metrics.json",
      "success_rate": 0.85,
      "total_features": 6,
      "kaizen_enabled": true
    }
  ]
}
```

**Implementation (2026-03-07):** Moved from inline Python in `run-atomic.sh` / `run-prime-contractor.sh` into `scripts/run_prime_postmortem.py` via `_update_kaizen_index()`. The SDK derives `run_id` from `run-metadata.json` (via `_resolve_run_id()`), falling back to `KAIZEN_RUN_ID` env var then directory name. This makes kaizen index management independent of cap-dev-pipe shell scripts. The pipeline base directory is resolved via `_resolve_pipeline_base()` which walks up from the output directory.

**Idempotency:** If an entry with the same `run_id` already exists, it is replaced in place (no duplicates). Writes use atomic tmp+rename.

**Symlink safety:** `_resolve_run_id()` never returns `"latest"` — it reads the real run directory name from `run-metadata.json` or resolves the symlink target.

### REQ-KZ-302: Retention Policy

A `--kaizen-keep N` flag on `run_prime_postmortem.py` (default: 20, range: 5–200) SHALL prune index entries and archive directories for runs older than the Nth most recent. Pruning runs after the new entry is appended.

**Implementation (2026-03-07):** Integrated into `_update_kaizen_index()` in `scripts/run_prime_postmortem.py`. Clamped to [5, 200] range. Only prunes directories whose name starts with `run-` (safety guard). Cap-dev-pipe passes `--kaizen-keep` from `${KAIZEN_KEEP:-20}` env var.

---

## 6. Layer 4 — Cross-Run Aggregation (REQ-KZ-4xx)

**Closes:** Gap K-2 (no cross-run metric aggregation)

### REQ-KZ-400: Cross-Run Trend Script

A new script `cap-dev-pipe/run-kaizen-trends.sh` SHALL aggregate metrics from `kaizen-index.json` and produce a trend report:

```bash
./run-kaizen-trends.sh --project online-boutique-python
```

Output: `pipeline-output/{project}/kaizen-trends.json` + `kaizen-trends.md` containing:

- Success rate over time (per-run data points)
- Cost per successful feature over time
- Top failure root causes across all indexed runs (frequency table)
- Escalation rate trend (if micro-prime metadata present)
- New vs. resolved failure patterns between consecutive runs
- `skipped_runs` list with reasons for any runs missing metrics/postmortem data

**Leverages:**

- `kaizen-index.json` (from REQ-KZ-301) for run discovery
- `kaizen-metrics.json` (from REQ-KZ-300) for per-run data
- `prime-postmortem-report.json` for detailed root-cause and pattern data
- `run-compare.sh` comparison report generation pattern (lines 429-590) as structural template

**Implementation:** Python script invoked by a thin shell wrapper (matching `run-compare.sh` pattern). Reads metrics from archived runs, computes deltas, outputs JSON + Markdown.

### REQ-KZ-401: Failure Pattern Persistence

Cross-feature patterns detected by post-mortem (minimum 2 occurrences per `_CROSS_FEATURE_PATTERN_MIN`) SHALL be accumulated across runs in `pipeline-output/{project}/kaizen-patterns.json`. Each pattern entry tracks:

```json
{
  "pattern_id": "DUPLICATE_IMPORT",
  "first_seen_run": "run-001-20260301T1000",
  "last_seen_run": "run-003-20260305T1430",
  "occurrence_count": 3,
  "kaizen_action_taken": false,
  "resolved": false
}
```

**Leverages:** `PostMortemReport.cross_feature_patterns` already identifies these patterns per run. The trend script (REQ-KZ-400) performs the cross-run deduplication.

### REQ-KZ-402: Cost Trend Tracking

The trend report SHALL include cost analysis:

- Total cost per run
- Cost per successful feature per run
- Cost outlier detection across runs (runs costing 2x+ the running average)
- Cost delta between consecutive runs

**Leverages:** Post-mortem `cost_summary.total_usd` and the `_COST_OUTLIER_FACTOR = 2.0` constant already defined in `prime_postmortem.py`.

---

## 7. Layer 5 — Feedback Loop (REQ-KZ-5xx)

**Closes:** Gap K-3 (no feedback loop from analysis to config)

### REQ-KZ-500: Kaizen Config File Format

A `pipeline-output/{project}/kaizen-config.json` file SHALL define run-to-run improvement parameters:

```json
{
  "schema_version": "1.0",
  "last_updated": "2026-03-05T14:30:00Z",
  "source_run": "run-003-20260305T1430",
  "prompt_hints": [
    {
      "phase": "draft",
      "hint": "Explicitly validate all imports exist in the target project before using them.",
      "source": "PHANTOM_IMPORT appeared in 5/20 features across last 3 runs",
      "added": "2026-03-05"
    }
  ],
  "complexity_overrides": {
    "min_simple_threshold": 0.7,
    "notes": "Raised from 0.5 based on 60% escalation rate at previous threshold"
  },
  "known_failure_mitigations": [
    {
      "root_cause": "DUPLICATE_IMPORT",
      "mitigation": "pre_dedup_imports",
      "active": true
    }
  ]
}
```

### REQ-KZ-501: Post-Mortem Suggestion Generation

The post-mortem evaluation SHALL optionally produce a `kaizen-suggestions.json` alongside its existing outputs. Each suggestion maps a detected pattern to a concrete config adjustment:

```json
{
  "schema_version": "1.0",
  "source_run": "run-003-20260305T1430",
  "suggestions": [
    {
      "pattern": "PHANTOM_IMPORT occurred in 4/20 features",
      "suggested_action": "Add import validation hint to draft phase prompt",
      "config_key": "prompt_hints",
      "confidence": "high",
      "auto_applicable": false
    }
  ]
}
```

**Leverages:** The post-mortem's `lessons` extraction and `cross_feature_patterns` detection already identify patterns. This adds structured suggestion formatting.

**Implementation:** Add `--emit-suggestions` flag to `run_prime_postmortem.py`, invoked from `run-prime-contractor.sh` alongside `--emit-metrics`.

### REQ-KZ-502: Config Injection via `run-atomic.sh`

When `pipeline-output/{project}/kaizen-config.json` exists, `run-atomic.sh` SHALL pass it to the prime contractor via `--contractor-arg`:

```bash
KAIZEN_CONFIG="$PIPELINE_BASE/kaizen-config.json"
if [ -f "$KAIZEN_CONFIG" ] && [ "$NO_KAIZEN" != true ]; then
    EXTRA_CONTRACTOR_ARGS+=(--kaizen-config "$KAIZEN_CONFIG")
fi
```

The SDK's `PrimeContractorWorkflow` SHALL load this file and apply `prompt_hints` by injecting them into phase prompts as additional context. The `complexity_overrides` and `known_failure_mitigations` sections are defined in the schema for future use but are **not consumed in the initial implementation** — their SDK integration points (complexity router, repair pipeline) require separate interface design.

**Validation & safety:**

- If the config is invalid JSON or fails schema checks, log a warning and proceed without kaizen (do not fail the run).
- Deduplicate prompt hints by content hash and cap hints per phase (default: 5) to avoid prompt bloat.

**Leverages:** `run-atomic.sh` already supports `--contractor-arg` for passing extra flags. `PRIME_CONTRACTOR_EXTRA_ARGS` in `pipeline.env` provides a persistent version.

### REQ-KZ-503: `--no-kaizen` Bypass Flag

`run-atomic.sh` SHALL accept `--no-kaizen` to disable config injection for clean-baseline runs. This enables A/B comparison between kaizen-influenced and baseline runs.

### REQ-KZ-504: Improvement Verification

The trend report (REQ-KZ-400) SHALL flag whether Kaizen actions produced measurable improvement by comparing metrics before and after the `source_run` of each active kaizen config entry. Actions that degrade metrics are flagged for review.

Only runs with `kaizen_enabled=true` are considered in the post-kaizen window to avoid mixing baseline runs.

**Acceptance criteria:**

- **Improvement**: success_rate delta ≥ +0.05 (5 percentage points) across at least 2 post-kaizen runs
- **Regression**: success_rate delta ≤ −0.05 OR cost_per_success delta ≥ +50%
- **Inconclusive**: fewer than 2 post-kaizen runs available, or delta within ±0.05
- Each kaizen config entry is individually evaluated against these thresholds

---

## 8. Layer 6 — Prompt Quality Correlation (REQ-KZ-6xx)

**Closes:** Gap K-4 (no prompt-response quality correlation)

### REQ-KZ-600: Prompt Characteristic Extraction

For each archived prompt (from Layer 2), extract measurable characteristics:

- Token count (approximate, whitespace tokenization proxy)
- Requirement mention count (seed requirements referenced)
- Constraint density (constraints per 1000 tokens)
- Context completeness (percentage of seed context fields present)
- Existing file context inclusion (boolean)

**Leverages:** `WalkthroughPromptEvaluator` already computes requirement coverage and constraint coverage. This extends the evaluator to work on real-run prompts (which are identical in structure to walkthrough prompts).

### REQ-KZ-601: Quality-Prompt Correlation Script

A script `cap-dev-pipe/run-kaizen-correlation.sh` SHALL compute correlations between prompt characteristics (REQ-KZ-600) and post-mortem quality scores (REQ-KZ-300):

- Which prompt characteristics correlate with PASS vs. FAIL verdicts?
- Does higher requirement coverage correlate with higher quality scores?
- Does existing file context inclusion reduce repair step frequency?
- Which phases (spec/draft/review) have the strongest prompt-quality correlation?

**Output:** `pipeline-output/{project}/kaizen-correlation.json` + `kaizen-correlation.md`

**Method:** Use Spearman rank correlation with sample-size reporting. If fewer than 10 runs are available, emit an "insufficient data" section and skip correlation coefficients.

**Leverages:** All input comes from existing post-mortem reports and walkthrough evaluator scores — no new LLM calls.

---

## 9. Existing Capabilities Leveraged

| Requirement | Existing Component | How Leveraged |
|------------|-------------------|---------------|
| REQ-KZ-100 | `run_prime_postmortem.py` | Standalone runner with `--run-dir` auto-discovery — just invoke it |
| REQ-KZ-101 | `run_prime_postmortem.py --output-dir` | Already writes to specified output dir |
| REQ-KZ-102 | `run-artisan.sh:374-386` | Exact display pattern to replicate for prime |
| REQ-KZ-200 | `_persist_walkthrough_prompts()` | Reuse prompt serialization logic |
| REQ-KZ-201 | `LeadContractorGenerator.generate()` → `gen_metadata` | Raw responses forwarded via `spec_raw_response` / `draft_raw_response` / `review_raw_response` metadata keys |
| REQ-KZ-202 | `run-atomic.sh:510-517` | State archiving pattern to extend |
| REQ-KZ-300 | `PostMortemReport` fields | Metrics already computed — just extract |
| REQ-KZ-301 | `_update_kaizen_index()` in `run_prime_postmortem.py` | Derives run_id from `run-metadata.json` via `_resolve_run_id()` |
| REQ-KZ-400 | `run-compare.sh:429-590` | Report generation structural template |
| REQ-KZ-401 | `PostMortemReport.cross_feature_patterns` | Per-run pattern detection |
| REQ-KZ-502 | `--contractor-arg` / `PRIME_CONTRACTOR_EXTRA_ARGS` | Existing flag passthrough mechanism |
| REQ-KZ-600 | `WalkthroughPromptEvaluator` | Requirement/constraint coverage scoring |

---

## 10. Traceability Matrix

| Kaizen Gap | Requirements | Design Principle Rule | Impl Home |
|-----------|-------------|---------------------|-----------|
| K-1: No prompt capture in real runs | REQ-KZ-200, 201, 202, 203, 204 | Rule 2: Prompt-Response Pairing | SDK + cap-dev-pipe |
| K-2: No cross-run aggregation | REQ-KZ-400, 401, 402 | Rule 3: Measure Before and After | cap-dev-pipe |
| K-3: No feedback loop | REQ-KZ-500, 501, 502, 503, 504 | Rule 5: Feed Forward | cap-dev-pipe + SDK |
| K-4: No prompt-quality correlation | REQ-KZ-600, 601 | Rule 3: Measure Before and After | SDK + cap-dev-pipe |
| K-5a: No prime post-mortem in pipeline | REQ-KZ-100, 101, 102 | Rule 1: Preserve All Run Outputs | cap-dev-pipe |
| K-5b: No archive index | REQ-KZ-300, 301, 302 | Rule 1: Preserve All Run Outputs | cap-dev-pipe |

---

## 11. Verification Strategy

### Unit Tests (startd8-sdk)

| Test | Validates |
|------|-----------|
| `test_prompt_persisted_real_run` | REQ-KZ-200: Prompts written during non-walkthrough runs |
| `test_response_alongside_prompt` | REQ-KZ-201: Response files present when `gen_metadata` contains `{phase}_raw_response` keys |
| `test_walkthrough_code_reused` | REQ-KZ-203: No duplication of walkthrough persistence logic |
| `test_redaction_rules_applied` | REQ-KZ-204: Redaction patterns applied before write |
| `test_redaction_invalid_disables_persistence` | REQ-KZ-204: Invalid redaction config disables persistence |
| `test_emit_metrics_flag` | REQ-KZ-300: `--emit-metrics` produces valid JSON |
| `test_metrics_schema_version` | REQ-KZ-300: `schema_version` present and correct |
| `test_emit_suggestions_flag` | REQ-KZ-501: `--emit-suggestions` produces valid JSON |
| `test_kaizen_config_loaded` | REQ-KZ-502: Config injected at startup |

### Integration Tests (cap-dev-pipe)

| Test | Validates |
|------|-----------|
| `test_prime_postmortem_in_pipeline` | REQ-KZ-100-102: Post-mortem runs and displays after prime contractor |
| `test_kaizen_index_append` | REQ-KZ-301: `--update-index` appends run entry via `_update_kaizen_index()` |
| `test_kaizen_index_idempotent` | REQ-KZ-301: Re-running a run replaces entry in place, no duplicates |
| `test_kaizen_index_resolve_run_id` | REQ-KZ-301: `_resolve_run_id()` reads `run-metadata.json`, never returns `"latest"` |
| `test_kaizen_trends_multi_run` | REQ-KZ-400: Trend computed across multiple archived runs |
| `test_no_kaizen_flag` | REQ-KZ-503: `--no-kaizen` disables config injection |
| `test_walkthrough_then_real_prompts_match` | REQ-KZ-203: Prompts captured in walkthrough match real-run captures |

### Implementation Order

1. **Layer 1** (REQ-KZ-100–102) — Prime post-mortem parity. ✅ IMPLEMENTED.
2. **Layer 3** (REQ-KZ-300–302) — Run metrics & index. ✅ IMPLEMENTED. `--emit-metrics`, `--update-index`, `--kaizen-keep` in `run_prime_postmortem.py`. Index management moved from cap-dev-pipe to SDK (2026-03-07).
3. **Layer 4** (REQ-KZ-400–402) — Cross-run trends. Cap-dev-pipe scripts (`kaizen-trends.py`, `kaizen-correlation.py`). Partially implemented.
4. **Layer 2** (REQ-KZ-200–204) — Prompt-response pairing. REQ-KZ-201 ✅ IMPLEMENTED (response forwarding via `gen_metadata`). REQ-KZ-200, 202–204 in progress.
5. **Layer 5** (REQ-KZ-500–504) — Feedback loop. Requires both SDK and cap-dev-pipe changes.
6. **Layer 6** (REQ-KZ-600–601) — Correlation analysis. Depends on Layer 2 + 3 data.

Each layer is independently valuable and can be shipped incrementally.

---

## 12. Cross-References

### Pipeline Requirements Index

This document should be registered in `cap-dev-pipe/PIPELINE_REQUIREMENTS_INDEX.md` under a new source:

| Source | Prefix | Count | Status | Location |
|--------|--------|-------|--------|----------|
| Kaizen (Prime) | REQ-KZ-100–601 | 22 | All planned | `startd8-sdk/docs/design/prime/KAIZEN_PRIME_REQUIREMENTS.md` |

### Related Documents

- [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) — Design principle
- [MOTTAINAI_DESIGN_PRINCIPLE.md](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — Parent principle
- [PRIME_CONTRACTOR_PROMPT_AUDIT_FINDINGS.md](../PRIME_CONTRACTOR_PROMPT_AUDIT_FINDINGS.md) — Gap analysis
- [PIPELINE_REQUIREMENTS_INDEX.md](~/Documents/dev/cap-dev-pipe/PIPELINE_REQUIREMENTS_INDEX.md) — Master index
- [run-atomic.sh](~/Documents/dev/cap-dev-pipe/run-atomic.sh) — Run isolation orchestrator
- [run-prime-contractor.sh](~/Documents/dev/cap-dev-pipe/run-prime-contractor.sh) — Prime execution orchestrator
- [run-artisan.sh](~/Documents/dev/cap-dev-pipe/run-artisan.sh) — Artisan execution (post-mortem reference impl)

---

## Convergent Review — Round R1 (Triaged)

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 19:30 UTC
- **Scope**: Quality/robustness sweep after initial draft

### Findings

| ID | Area | Severity | Finding | Fix |
|----|------|----------|---------|-----|
| R1-S1 | Safety | high | Prompt/response persistence could leak secrets; no redaction or opt-out mechanism defined. | Add REQ-KZ-204 with deterministic redaction config and fail-closed behavior. |
| R1-S2 | Correctness | medium | Prompt persistence path is not run-isolated and lacks path traversal sanitization for `feature_id`. | Add run-id subdir and sanitize feature IDs. |
| R1-S3 | Robustness | medium | `kaizen-index.json` append is not idempotent; duplicate `run_id` entries possible. | Replace-by-`run_id` and atomic write. |
| R1-S4 | Evolvability | medium | `kaizen-metrics.json` and `kaizen-index.json` lack `schema_version`. | Add `schema_version` and minimal metadata fields. |
| R1-S5 | Correctness | low | Post-mortem invocation could override prime contractor exit code. | Preserve original exit code; log post-mortem failures. |
| R1-S6 | Analysis Quality | low | Trend/correlation outputs lack data-quality guards. | Add `skipped_runs` reporting and minimum sample-size thresholds. |
| R1-S7 | Robustness | low | `kaizen-config.json` is not validated; hints can grow unbounded. | Validate schema, dedup hints, cap per phase. |

### Quick Wins

| ID | Area | Severity | Suggestion |
|----|------|----------|-----------|
| R1-Q1 | Archiving | low | Only delete `.startd8/kaizen-prompts` after a successful copy. |
| R1-Q2 | Metrics | low | Add `kaizen_enabled` to metrics and index to filter baseline runs. |

### Triage Disposition

| ID | Disposition | Applied To | Notes |
|----|------------|------------|-------|
| R1-S1 | **ACCEPTED** | REQ-KZ-204 | Redaction + fail-closed persistence added |
| R1-S2 | **ACCEPTED** | REQ-KZ-200 | Run-id subdir + sanitization added |
| R1-S3 | **ACCEPTED** | REQ-KZ-301 | Idempotent index update added |
| R1-S4 | **ACCEPTED** | REQ-KZ-300/301 | Schema version fields added |
| R1-S5 | **ACCEPTED** | REQ-KZ-100 | Exit-code preservation added |
| R1-S6 | **ACCEPTED** | REQ-KZ-400/601 | Skipped-runs + min-sample guard added |
| R1-S7 | **ACCEPTED** | REQ-KZ-502 | Validation + dedup/cap added |
| R1-Q1 | **ACCEPTED** | REQ-KZ-202 | Copy-success guard added |
| R1-Q2 | **ACCEPTED** | REQ-KZ-300/301/504 | `kaizen_enabled` tracked and used |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected).
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

---

### Areas Substantially Addressed

- **Risks**: 3 suggestions applied (R1-S3, R1-S5, R1-S7)

### Areas Needing Further Review

- **Interfaces**: 0/3 suggestions accepted (need 3 more)
- **Architecture**: 1/3 suggestions accepted (need 2 more)
- **Security**: 1/3 suggestions accepted (need 2 more)
- **Validation**: 1/3 suggestions accepted (need 2 more)
- **Ops**: 1/3 suggestions accepted (need 2 more)
- **Data**: 2/3 suggestions accepted (need 1 more)

---

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Add prompt/response redaction rules and fail-closed opt-out | Antigravity (R1) | REQ-KZ-204 added: `.startd8/kaizen-redactions.json` config, invalid config disables persistence | 2026-03-05 |
| R1-S2 | Isolate prompt persistence path per run-id; sanitize `feature_id` for path traversal | Antigravity (R1) | REQ-KZ-200 updated: run-id subdir + `/` and `..` sanitization added | 2026-03-05 |
| R1-S3 | Make `kaizen-index.json` append idempotent; replace-by-`run_id` with atomic write | Antigravity (R1) | REQ-KZ-301 updated: replace-in-place for duplicate `run_id` entries + tmp-rename atomicity | 2026-03-05 |
| R1-S4 | Add `schema_version` to `kaizen-metrics.json` and `kaizen-index.json` | Antigravity (R1) | REQ-KZ-300/301 updated: `schema_version: "1.0"` + metadata fields added to both schemas | 2026-03-05 |
| R1-S5 | Preserve prime contractor exit code if post-mortem step fails | Antigravity (R1) | REQ-KZ-100 updated: exit code constraint + non-fatal logging added | 2026-03-05 |
| R1-S6 | Add `skipped_runs` list and minimum sample-size thresholds to trend/correlation outputs | Antigravity (R1) | REQ-KZ-400 updated: `skipped_runs` list with reasons; REQ-KZ-601 updated: Spearman + min-10 guard | 2026-03-05 |
| R1-S7 | Validate `kaizen-config.json` schema; dedup hints by content hash; cap hints per phase | Antigravity (R1) | REQ-KZ-502 updated: invalid config disables kaizen (non-fatal); dedup + default cap of 5 added | 2026-03-05 |
| R1-Q1 | Only delete `.startd8/kaizen-prompts` after a confirmed successful copy | Antigravity (R1) | REQ-KZ-202 updated: copy-success guard; on failure preserve source and log warning | 2026-03-05 |
| R1-Q2 | Add `kaizen_enabled` field to metrics and index to filter baseline runs | Antigravity (R1) | REQ-KZ-300/301/504 updated: `kaizen_enabled` derived from config presence + `--no-kaizen` flag | 2026-03-05 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R2

- **Reviewer**: Antigravity
- **Date**: 2026-03-05 18:47:00 UTC
- **Scope**: Second-pass sweep targeting Interfaces (0/3), Architecture (1/3), Security (1/3), Validation (1/3), and Ops (1/3) — the five areas below the substantially-addressed threshold after R1 triage

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Interfaces | high | Define a versioned SDK API contract for the `--kaizen` / `--kaizen-config` flags so that cap-dev-pipe scripts don't silently break when the SDK evolves | REQ-KZ-200 and REQ-KZ-502 each introduce new CLI flags to `run_prime_workflow.py`, but no interface contract is specified: what happens when an older cap-dev-pipe passes `--kaizen-config` to a newer SDK that renames or removes the flag? Without an explicit contract (e.g., a `--version` check or argparse-level graceful unknown-arg handling), pipeline breakage is silent and hard to diagnose. | REQ-KZ-200 / REQ-KZ-502 — add a "CLI Contract" sub-section specifying: (a) flags are stable across minor SDK versions, (b) unknown flags emit a warning and are ignored (not an error), and (c) the minimum supported SDK version for kaizen features is documented in `pipeline.env`. | Verify with `run_prime_workflow.py --kaizen-config /nonexistent/path` and with a synthetic "future SDK" that removes the flag — confirm cap-dev-pipe receives a non-zero exit code with a clear error, not a silent no-op. |
| R2-S2 | Interfaces | high | Specify the `{phase}_user_prompt.md` / `{phase}_system_prompt.md` file naming convention as a formal schema in the requirements, not just an implicit convention shared between `_persist_walkthrough_prompts()` and `WalkthroughPromptEvaluator` | REQ-KZ-200 persists prompts; REQ-KZ-600 evaluates them; REQ-KZ-203 requires zero duplication of serialization logic. All three depend on the same directory layout and filename conventions, but the layout is only described informally in prose. If the layout ever changes in `_persist_walkthrough_prompts()`, REQ-KZ-600's `extract_prompt_characteristics()` and REQ-KZ-601's correlation script will silently fail because they look for files that no longer exist at those paths. A formal schema (even a small table: `phase ∈ {spec, draft, review}`, filenames, required vs optional) makes the coupling explicit and verifiable. | Section 4 (Layer 2, REQ-KZ-200) — add a "Prompt Directory Schema" table; reference it from REQ-KZ-600 and REQ-KZ-203 explicitly. | Unit test: assert that `_write_prompt_files()` produces exactly the filenames the schema specifies; assert that `extract_prompt_characteristics()` only reads filenames in the schema. |
| R2-S3 | Architecture | high | Layer 5's suggestion-to-config pathway is entirely manual (operator edits `kaizen-config.json` by hand from `kaizen-suggestions.json`), but the requirements do not define the review/approval gate, expiry, or authorship trail for individual hint entries | REQ-KZ-500 defines the config schema with a `source_run` and `added` date, but there is no field for `reviewed_by`, `expires_after_runs`, or `auto_retire` criteria. Without these, the config file will accumulate stale hints from old runs that no longer apply (e.g., a PHANTOM_IMPORT hint added for run-003 is still active in run-020 even though the pattern disappeared). This is a design-level gap: the requirements describe the format but not the lifecycle. The implementation plan (Step 5.2) explicitly defers automation to a later maturity level — which is fine — but the manual lifecycle rules still need to be documented at this level. | REQ-KZ-500 — add a "Hint Lifecycle" sub-section: (a) each hint carries `expires_after_runs: int \| null` (null = permanent), (b) the trend script (REQ-KZ-400) emits a warning for hints that have been active for N runs with no measurable improvement (cross-reference REQ-KZ-504), (c) `reviewed_by` is optional metadata for audit purposes. | Verify: create a config with `expires_after_runs: 3`, run 4 pipelines, assert the trend report flags the expired hint. |
| R2-S4 | Validation | medium | REQ-KZ-203's acceptance criterion ("no duplication of prompt serialization logic") is untestable as stated — the test `test_walkthrough_code_reused` validates behavior, not structural duplication | The requirement says "No duplication of prompt serialization logic" and the test verifies that walkthrough prompts match real-run prompts. But if a developer duplicates the logic (instead of calling the shared function) and the outputs happen to be identical, the test passes while the requirement is violated. The requirement needs a structural verifiability clause: e.g., "the shared `_write_prompt_files` function is the sole write path for prompt files, verifiable by static analysis (grep for `write_text` in prompt-related methods)." | REQ-KZ-203 — add a testability clause: "Verify via `grep` or AST inspection that `_write_prompt_files()` is the only call site that writes prompt/response files; no other method in `prime_contractor.py` invokes `Path.write_text()` with prompt content." | Add a linting test or `grep`-based CI check: `grep -n 'write_text' prime_contractor.py` must produce only `_write_prompt_files` and `_persist_walkthrough_prompts` (the latter as a thin wrapper). |
| R2-S5 | Security | medium | REQ-KZ-204's redaction uses regex patterns applied to full file text, but the requirements do not specify encoding handling or multi-line matching behavior — a secret spanning a JSON line break would bypass the patterns | The redaction config example uses `"API_KEY=.*"` (single-line regex). In practice, LLM responses and prompts are multi-line. If a secret value is split across a JSON-escaped newline (`\n`), a single-line `.*` pattern will not match it. The requirement should specify: (a) whether redaction operates on the raw byte stream, the decoded string, or the parsed JSON value, (b) whether `re.MULTILINE` or `re.DOTALL` is the required mode, and (c) whether the redaction applies before or after JSON serialization. | REQ-KZ-204 — add a "Redaction Semantics" clause: redaction is applied to the **decoded UTF-8 string of the full file content** after formatting (so after JSON serialization, before write), using `re.sub(pattern, replacement, content, flags=re.MULTILINE)`. | Unit test: create a prompt string with a secret split across two lines (`API_KEY=
my-secret`), apply redaction, assert secret is replaced. |
| R2-S6 | Ops | medium | The retention policy (REQ-KZ-302) prunes run archive directories but does not account for runs that are still referenced by an active `kaizen-config.json` as `source_run` | If `kaizen-config.json` has `"source_run": "run-001-..."` and the retention script prunes that run (because it is older than `KAIZEN_KEEP`), the improvement verification logic in REQ-KZ-504 will fail silently: `before = [r for r in runs if r["run_id"] <= source_run]` will produce an empty set, and the verdict will be INCONCLUSIVE rather than IMPROVED or REGRESSION. The retention policy should either (a) exclude the `source_run` from pruning while it is referenced, or (b) retain the metrics JSON only (not the full archive directory) for referenced runs. | REQ-KZ-302 — add a "Protected Runs" clause: before pruning, read `kaizen-config.json` (if present) and exclude its `source_run` from the prune candidates. Log a notice when a protected run is skipped. | Test: set `KAIZEN_KEEP=1`, write a `kaizen-config.json` referencing `run-001`, run 3 pipelines, assert `run-001` is NOT pruned. |
| R2-S7 | Ops | low | The `kaizen-index.json` has no maximum size bound; with `--kaizen-keep 20` (default), the index accumulates up to 20 entries, but the inline Python that appends to it in `run-atomic.sh` loads and rewrites the entire file on each run — this is fine for 20 runs but becomes a correctness risk if `KAIZEN_KEEP` is set very large or left unbounded | The retention policy defaults to 20 runs (REQ-KZ-302), which is safe. But the requirement does not specify a hard cap on `KAIZEN_KEEP`, nor does it guard against `KAIZEN_KEEP=0` (which would prune ALL entries, destroying the index) or very large values. A simple constraint (minimum 5, maximum 200, with a guard in the pruning script) prevents operator misconfiguration from causing data loss or performance degradation. | REQ-KZ-302 — add a constraint: `KAIZEN_KEEP` must be between 5 and 200 (inclusive); values outside this range produce a warning and are clamped to the nearest bound. `KAIZEN_KEEP=0` is treated as `KAIZEN_KEEP=5`. | Test: set `KAIZEN_KEEP=0`, run pipeline, assert index is not empty (clamped to 5). |
| R2-S8 | Data | medium | `kaizen-metrics.json` includes `pipeline_attribution` (stage-level failure counts) but there is no specification for what happens when `pipeline_attribution` is empty or when a stage value is not a recognized enum member — the `stage.value` access in the implementation plan (Step 3.1) will raise `AttributeError` if any attribution entry lacks a `.value` property | REQ-KZ-300 specifies the JSON schema for `kaizen-metrics.json` but gives no guidance on partial or malformed inputs from `PrimePostMortemReport`. The schema example shows `pipeline_attribution` as an array, but if the postmortem runs against a partial result (e.g., the prime contractor crashed mid-run), the attribution may be `None` or contain partially-constructed objects. The `_emit_kaizen_metrics` function in the implementation plan accesses `a.stage.value` without a null guard. | REQ-KZ-300 — add a "Partial Report Handling" clause: if `pipeline_attribution` is `None` or empty, emit `"pipeline_attribution": []`; if any attribution entry has a non-enum `stage`, serialize it as `str(stage)` rather than raising. | Unit test: pass a mock `PrimePostMortemReport` with `pipeline_attribution=None` and assert `_emit_kaizen_metrics` produces valid JSON with `"pipeline_attribution": []`. |
| R2-S9 | Architecture | medium | The `--emit-suggestions` output (`kaizen-suggestions.json`) is consumed by the operator manually to populate `kaizen-config.json` (per Step 5.2), but there is no diff/merge specification for the case where a `kaizen-config.json` already exists and the new suggestions partially overlap with existing hints | When hints from `run-003` already exist in `kaizen-config.json` and `run-004` produces a new `kaizen-suggestions.json` with overlapping patterns, the operator has no guidance on whether to replace, merge, or deduplicate. This is a documentation gap in the requirements: the config lifecycle (REQ-KZ-500/501) should explicitly state that `kaizen-suggestions.json` is a one-way read-only output (never written by the pipeline), and that merging into `kaizen-config.json` is always a manual, additive operation — with the deduplication logic in REQ-KZ-502 (content-hash dedup) serving as the safety net for accidental duplicates. | REQ-KZ-501 — add a "Config Merge Contract" note: "`kaizen-suggestions.json` is a read-only pipeline output. The operator is responsible for merging desired suggestions into `kaizen-config.json`. Duplicate hints are silently deduplicated by the SDK loader (REQ-KZ-502) using content hashing — so double-applying a suggestion is safe." | Manual verification: add the same hint twice to `kaizen-config.json`, run pipeline, assert only one hint is injected into the prompt context. |
| R2-S10 | Validation | low | The verification strategy (Section 11) specifies integration tests for cap-dev-pipe but does not specify any E2E smoke test that confirms the full Kaizen loop end-to-end (run → post-mortem → suggestions → config → next run with improved hints → trend report shows delta) | Individual layer tests validate each component in isolation. But the claim of the entire system — that Kaizen produces measurable run-over-run improvement — is not verified by any test in Section 11. Without at least one E2E test (even a lightweight synthetic one: inject a known failure pattern, generate suggestions, apply them, verify the next run's metrics JSON reflects the improvement), the feedback loop gap K-3 remains theoretically closed but empirically unverified. | Section 11 — add an E2E integration test row: `test_kaizen_full_loop_smoke` — runs a synthetic prime workflow with a known failure pattern, verifies `kaizen-suggestions.json` contains the expected suggestion, manually applies it, re-runs, and verifies the subsequent `kaizen-trends.md` shows an IMPROVED verdict. | Run once against a mock prime workflow with injected PHANTOM_IMPORT failures; assert `kaizen-trends.md` contains `"verdict": "IMPROVED"` after 3 post-kaizen runs. |
