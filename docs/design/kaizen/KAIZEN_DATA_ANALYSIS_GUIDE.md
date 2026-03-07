# Kaizen Data Analysis Guide

Kaizen is a closed-loop continuous improvement system for the Capability Delivery Pipeline. Each pipeline stage that makes LLM calls can produce Kaizen telemetry: diagnostic reports, captured prompts/responses, quality metrics, and trend data. This guide explains the common framework and then covers each instrumented stage.

Currently instrumented stages:

| Stage | Pipeline position | Diagnostic file | Trend script |
|-------|-------------------|-----------------|--------------|
| [Plan Ingestion](#plan-ingestion) | Stage 5 | `plan-ingestion-diagnostic.json` | `scripts/plan_ingestion_trends.py` |
| [Prime Contractor](#prime-contractor) | Stage 6 | `kaizen-metrics.json` | `kaizen-trends.py` (cap-dev-pipe) |

---

## Common Concepts

### Enabling Kaizen

Every instrumented stage follows the same two-level pattern:

1. **Diagnostics (always on)** — Structured metrics written after every run. No flags required.
2. **Prompt capture (opt-in)** — Full prompt and response text persisted for offline analysis. Enabled with `--kaizen`.

Both levels are **advisory** — I/O failures never block a successful pipeline run.

```bash
# Enable prompt capture for the full pipeline
./run-atomic.sh --plan plan.md --requirements reqs.md --kaizen

# Disable kaizen config injection even when kaizen-config.json exists
./run-atomic.sh ... --no-kaizen
```

### Kaizen Config

Each stage can accept a `kaizen-config.json` file containing stage-specific tuning parameters (prompt suffixes, threshold overrides, feature hints). The config is a single JSON file with stage-keyed sections:

```json
{
  "plan_ingestion_kaizen": {
    "parse_prompt_suffix": "...",
    "complexity_threshold_override": 45
  },
  "prime_contractor_kaizen": {
    "feature_hints": { "PI-005": "Use dependency injection pattern" }
  }
}
```

Each stage reads only its own section. Unknown keys are silently ignored. All fields are optional.

### Prompt Capture Limits

Prompt and response files are capped at **2 MiB** each. Files exceeding this are truncated with a `<!-- TRUNCATED at N bytes (original: M) -->` marker.

### Directory Layout

All Kaizen data lives under the run directory:

```
pipeline-output/{project}/{run-id}/
  plan-ingestion/                          # Stage 5 output
    plan-ingestion-diagnostic.json         #   diagnostic (always)
    {route}-context-seed.json              #   seed with _ingestion_quality
    kaizen-prompts/                        #   prompt capture (--kaizen only)
      {phase}_prompt.txt
      {phase}_response.txt
  kaizen-metrics.json                      # Stage 6 diagnostic (always)
  kaizen-prompts/                          # Stage 6 prompt capture (--kaizen only)
    standalone/{FEATURE_ID}/
      metadata.json
      {phase}_user_prompt.md
      {phase}_system_prompt.md
      {phase}_response.md
  plan-ingestion-diagnostic.json           # Archived copy at run root
  kaizen-analysis.log                      # Post-run analysis log
  kaizen-suggestions.json                  # Auto-generated tuning suggestions
  kaizen-correlation.md                    # Prompt characteristic vs outcome
  kaizen-trends.md                         # Cross-run trend report
```

### The Feedback Loop

The core Kaizen workflow is the same regardless of stage:

1. **Run** with `--kaizen` to capture telemetry.
2. **Diagnose** — read the diagnostic file, identify weak metrics.
3. **Inspect** — read captured prompts to understand what the LLM received and produced.
4. **Tune** — create or update `kaizen-config.json` with targeted adjustments.
5. **Re-run** — execute again with `--kaizen-config` and compare metrics.
6. **Trend** — use the trend script to track improvement across runs.

### Code Extraction Fallback

A common signal across stages is `code_extraction_fallback: true`, which means the LLM response contained no code fences (`` ``` ``) and the raw text was used as-is. This indicates the LLM ignored format instructions. Consistent fallbacks warrant:

- Adding format instructions via the stage's kaizen config prompt suffix
- Inspecting the captured prompt to verify format instructions are present
- Switching to a model with better instruction following

---

## Plan Ingestion

**Pipeline position:** Stage 5 (between ContextCore export and contractor execution)

**What it does:** Parses a plan document, assesses complexity, routes to prime or artisan, transforms features into a structured context seed.

**Phases:** `parse` → `assess` → `transform` → `refine` → `emit`

### Enabling

```bash
# Via cap-dev-pipe
./run-plan-ingestion.sh --provenance .../run-provenance.json --kaizen
./run-plan-ingestion.sh --provenance ... --kaizen --kaizen-config kaizen-config.json

# Direct SDK CLI
startd8 workflow run plan-ingestion --config config.json  # set "kaizen": true in config
```

### Kaizen Config

Section key: `plan_ingestion_kaizen`

| Field | Type | Effect |
|-------|------|--------|
| `parse_prompt_suffix` | string | Appended to the PARSE phase prompt |
| `assess_prompt_suffix` | string | Appended to the ASSESS phase prompt |
| `transform_prompt_suffix` | string | Appended to the TRANSFORM phase prompt |
| `complexity_threshold_override` | int | Overrides the prime/artisan routing threshold |

### Diagnostic Report

File: `plan-ingestion-diagnostic.json` (always written)

```json
{
  "schema_version": "1.0.0",
  "run_timestamp": "2026-03-07T14:30:00Z",
  "plan_source": "/path/to/plan.md",
  "plan_checksum": "sha256:abc123...",
  "route": "prime",
  "overall_success": true,
  "phases": { ... },
  "totals": { ... },
  "seed_quality_score": 0.85,
  "quality_warnings": [ ... ],
  "task_density": [ ... ]
}
```

#### Per-phase fields

| Field | Type | Meaning |
|-------|------|---------|
| `phase` | string | Phase name |
| `success` | bool | Completed without error |
| `time_ms` | int | Wall-clock milliseconds |
| `input_tokens` / `output_tokens` | int | Token counts |
| `cost_usd` | float | Estimated LLM cost |
| `code_extraction_fallback` | bool | Raw text used (no code fences) |
| `quality_signals` | dict | Phase-specific metrics (see below) |

#### PARSE quality signals

| Signal | Meaning |
|--------|---------|
| `features_extracted` | Total features parsed from the plan |
| `files_mentioned` | Source files referenced in the plan |
| `features_with_targets` | Features with explicit `target_files` |
| `features_with_deps` | Features with dependency annotations |
| `multi_file_features` | Features spanning multiple files |
| `features_with_signatures` | Features with API signature extraction |
| `dep_graph_coverage` | Fraction of features with dependency graph entries |

#### ASSESS quality signals

| Signal | Meaning |
|--------|---------|
| `composite_score` | Overall complexity (higher = more complex) |
| `route_decision` | `"prime"` or `"artisan"` |
| `route_margin` | Distance from routing threshold (low = borderline) |
| `dimension_spread` | Max minus min across complexity dimensions |

#### Totals

| Field | Meaning |
|-------|---------|
| `time_ms` | Total pipeline wall-clock time |
| `cost_usd` | Total LLM spend |
| `input_tokens` / `output_tokens` | Aggregate token usage |
| `llm_calls` | Phases that made LLM calls (parse, assess, transform) |

### Seed Quality Score

A composite 0.0-1.0 score embedded in both the diagnostic and the seed file's `_ingestion_quality` block:

| Weight | Component | Measures |
|--------|-----------|----------|
| 0.3 | Description coverage | Fraction of tasks with non-empty `task_description` |
| 0.3 | Target file coverage | Fraction of tasks with populated `target_files` |
| 0.2 | Schema validity | Seed passes JSON schema validation |
| 0.2 | Field coverage | Presence of optional enrichment fields |

The optional enrichment fields are: `architectural_context`, `design_calibration`, `service_metadata`, `onboarding`, `context_files`, `project_metadata`.

### Quality Gate

The seed quality score feeds an automated gate between Stage 5 and Stage 6 in `run-atomic.sh`. When the score falls below `SEED_QUALITY_THRESHOLD` (default: 0.5), the operator is prompted:

```
  *** SEED QUALITY WARNING ***
  Score: 0.35 (threshold: 0.5)
  Continue to Stage 6 despite low quality? [y/N]
```

Override the threshold: `SEED_QUALITY_THRESHOLD=0.3 ./run-atomic.sh ...`

Run the gate standalone: `python3 scripts/check_seed_quality.py path/to/seed.json --threshold 0.7 --json`

### Quality Warnings

| Warning | Meaning | Action |
|---------|---------|--------|
| `seed has no tasks` | Zero features parsed or zero tasks transformed | Check plan format |
| `N/M task(s) missing description` | Tasks lack detail | Enrich the plan |
| `N/M task(s) missing target_files` | Contractor won't know where to write | Add file path hints |
| `no architectural_context` | Upstream export lacked architecture docs | Add docs to ContextCore export |
| `no service_metadata` | No language/framework detected | Verify source files exist |

### Task Density

Per-task description richness in `task_density`:

| Field | Meaning |
|-------|---------|
| `task_id` | Task identifier |
| `description_chars` | Description character count |
| `description_lines` | Description line count |
| `has_code_examples` | Contains code fences |
| `has_requirements_refs` | References requirement IDs (`REQ-XXX`) |

Low values indicate thin tasks that may produce generic contractor output.

### Prompt Capture Files

With `--kaizen`, the `kaizen-prompts/` directory contains:

| File | Content |
|------|---------|
| `parse_prompt.txt` / `parse_response.txt` | Full PARSE LLM exchange |
| `assess_prompt.txt` / `assess_response.txt` | Full ASSESS LLM exchange |
| `transform_prompt.txt` / `transform_response.txt` | Full TRANSFORM LLM exchange |

### Trend Analysis

```bash
python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/
python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/ --last 5 --json
```

Columns: Route, OK (success), Feat (features), Seed Q, Cost, Time, FB (fallbacks), Comp (composite), Margin, Warn, Trend arrows.

| Pattern | Meaning | Action |
|---------|---------|--------|
| Seed Q declining | Config changes degraded output | Compare prompts between runs |
| FB increasing | LLM losing structured format | Check model; add format instructions |
| Margin near zero | Borderline routing decision | Use `--force-prime` or `--force-artisan` |
| Feature count shifting | Inconsistent parse | Check plan section boundaries |
| Cost spiking | Refine doing many rounds | Reduce `--review-rounds` |

### Fallback Interpretation

| Phase | Fallback means | Risk |
|-------|----------------|------|
| PARSE | Features returned as prose instead of structured format | Lost feature structure |
| ASSESS | Scores extracted from unstructured text | Unreliable complexity values |
| TRANSFORM | Task definitions without delimiters | Wrong field boundaries |

### Debugging Workflow

1. Check `seed_quality_score` and `quality_warnings` in the diagnostic.
2. Check `phases` for `"success": false` or high `time_ms` outliers.
3. If `code_extraction_fallback: true`, inspect the prompt/response pair.
4. Check `task_density` for thin tasks.
5. Compare against prior runs with `plan_ingestion_trends.py`.
6. Locate the issue: parsing → plan structure; assessment → `route_margin` / threshold override; transformation → task descriptions and targets.
7. Create targeted `kaizen-config.json` with prompt suffixes, re-run, compare.

---

## Prime Contractor

**Pipeline position:** Stage 6 (consumes the context seed from plan ingestion)

**What it does:** Generates code for each feature in the seed via the Lead Contractor workflow (spec → draft → review per feature), with optional micro-prime (Ollama) routing.

### Enabling

```bash
# Via cap-dev-pipe
./run-atomic.sh --plan plan.md --requirements reqs.md --route prime --kaizen

# Direct script
python3 scripts/run_prime_workflow.py --kaizen ...
```

### Kaizen Config

Section key: `prime_contractor_kaizen`

Feature-level hints are injected per-feature to steer LLM behavior. See `kaizen-suggestions.json` for auto-generated hints from prior runs.

### Diagnostic Report

File: `kaizen-metrics.json` (always written)

Key fields:

| Field | Meaning |
|-------|---------|
| `success_rate` | Ratio of PASS features to total features |
| `top_root_causes` | Failure layer attribution (`generation_error`, `repair_exhausted`, `validation_failure`) |
| `pipeline_attribution` | Where in the pipeline the fault occurred (`ollama_generation`, etc.) |

### Aggregated Analysis Files

| File | Content |
|------|---------|
| `kaizen-correlation.md` | Maps scalar characteristics (feature sizes, prompt word counts, dependency counts) to PASS/FAIL groups |
| `kaizen-suggestions.json` | Auto-generated prompt improvement suggestions for injection via `--kaizen-config` |
| `kaizen-trends.md` | Cross-run trend report |
| `kaizen-analysis.log` | Post-mortem analysis script execution log |

#### Reading `kaizen-correlation.md`

Compare `PASS mean` vs `FAIL mean` columns. If the `FAIL mean` for `target_file_count` is consistently higher than `PASS mean`, the decomposer is failing to split large work effectively.

### Per-Feature Prompt Data

With `--kaizen`, `kaizen-prompts/standalone/<FEATURE_ID>/` contains:

| File | Content |
|------|---------|
| `metadata.json` | Agent models, target files, boolean flags, active context keys |
| `spec_user_prompt.md` / `spec_system_prompt.md` | Spec phase prompts |
| `draft_user_prompt.md` / `draft_system_prompt.md` | Draft phase prompts |
| `review_user_prompt.md` / `review_system_prompt.md` | Review phase prompts |
| `{phase}_response.md` | Raw LLM output (PII-redacted) |
| `{phase}_response.meta.json` | Truncation metadata |

> [!WARNING]
> **Missing response files** may indicate: (a) a hard LLM fault (timeout, empty response), or (b) the code generator did not forward raw responses via `GenerationResult.metadata` keys (`spec_raw_response`, `draft_raw_response`, `review_raw_response`).

### Draft vs Disk: The Assembly Gap

> [!IMPORTANT]
> The LLM draft and the file on disk can diverge. Always compare both when investigating failures.

The captured draft (`draft_response.md`) passes through transformation steps before reaching disk:

1. **Skeleton splicing** (micro-prime): Element-level code spliced into a skeleton. Failed splices leave `raise NotImplementedError` stubs.
2. **AST merge** (when `has_existing_files: true`): Additive merge can keep stale definitions and duplicate nodes.
3. **File path resolution**: Fallback path derivation can misplace files.

```bash
# Compare draft to disk
diff <(cat kaizen-prompts/standalone/PI-XXX/draft_response.md) <(cat src/path/to/file.py)

# Verify syntax
python3 -c "import ast; ast.parse(open('src/path/to/file.py').read())"

# Check for stubs
grep -n "raise NotImplementedError" src/path/to/file.py
```

| File type | `has_existing_files: true` | `has_existing_files: false` |
|-----------|---------------------------|----------------------------|
| Python | AST merge (additive, auto-replace if >50% overlap) | Direct copy |
| HTML, other | Direct copy | Direct copy |

### Micro-Prime Artifacts

When a feature routes through micro-prime (local Ollama), telemetry is at the **element level** (individual functions/methods):

| Field | Meaning |
|-------|---------|
| `success` | Element generation succeeded |
| `tier` | Complexity tier |
| `code` | Generated code (`null` = cache hit with no code) |
| `verification_verdict` | `"skipped"` = served from cache |
| `filled_skeleton` | Post-splice state (stubs indicate splice failure) |
| `escalation.reason` | Why element escalated (`STRUCTURAL_MISMATCH`, `REPAIR_EXHAUSTED`) |

Common failure patterns:

| Pattern | Symptom | Where to look |
|---------|---------|---------------|
| Broken skeleton | `raise NotImplementedError` stubs remain | `filled_skeleton`; element `code` |
| Nested duplicate | Function defined inside itself | `draft_response.md`; `over_generation_trim` |
| Wrong function | Implements different API | `draft_user_prompt.md` |
| Cache without code | `verdict: "skipped"`, `code: null` | `_success_cache` |

### Success Reporting Caveats

> [!WARNING]
> `success: true` does not guarantee the file on disk is correct.

Success is determined by element-level verdict, review score (evaluates the draft, not disk), and post-assembly gate (checks for remaining stubs). Known gaps:

- Review scores reflect draft quality, not assembly quality
- Partially-filled files can still report element-level successes
- AST merge conflicts are logged as warnings but don't flip `success` to `false`

**Validation checklist for "successful" features:**

1. Does the file parse? (`ast.parse()`)
2. Any remaining `raise NotImplementedError` stubs?
3. Does `diff` between draft and disk show unexpected changes?
4. For `has_existing_files`: duplicate `__main__` guards, constants, or class definitions?

### Cross-Feature Comparison

When multiple features target similar code, compare outcomes to isolate systemic vs feature-specific issues:

| Dimension | What it reveals |
|-----------|-----------------|
| Route (micro-prime vs cloud) | Cloud fallback produces better output; micro-prime failures are often structural |
| Cost ($0.00 vs $0.08+) | $0.00 = micro-prime only; non-zero = cloud fallback |
| Review score | Identical specs with divergent scores → assembly issue, not LLM quality |
| File on disk | Side-by-side diff reveals assembly divergence |

### Debugging Workflow

1. Open `kaizen-metrics.json` — check `success_rate` and `top_root_causes`.
2. For generation faults, navigate to `kaizen-prompts/standalone/<FEATURE_ID>/`.
3. Inspect `draft_response.md` for what the LLM produced.
4. **Compare draft to disk** — catch assembly/merge corruption.
5. For stubs or garbled content: check element results and `filled_skeleton` (micro-prime) or merge log (`has_existing_files`).
6. For hallucinations: open `draft_user_prompt.md` to check context.
7. For cross-feature issues: compare sibling features with shared specs.
8. Create a hint in `kaizen-config.json`, re-run with `--kaizen-config`, measure.

---

## Cross-Stage Analysis

Plan Ingestion and Prime Contractor Kaizen are complementary. A low seed quality score often cascades into contractor failures. When debugging contractor issues, **check the ingestion diagnostic first** — fixing the seed may resolve downstream problems without touching contractor config.

| Dimension | Plan Ingestion | Prime Contractor |
|-----------|---------------|------------------|
| **Scope** | Plan parsing, complexity assessment, seed generation | Per-feature code generation, review, assembly |
| **Granularity** | Per-phase (5 phases) | Per-feature (3 LLM calls each) |
| **Key metric** | `seed_quality_score` (0.0-1.0) | `success_rate` (pass/fail per feature) |
| **Prompt capture** | 3 phase-level pairs | 3 pairs per feature (N features) |
| **Config tuning** | Phase-level prompt suffixes + threshold override | Feature-level hints |
| **Diagnostic** | `plan-ingestion-diagnostic.json` | `kaizen-metrics.json` |
| **Trend script** | `scripts/plan_ingestion_trends.py` | `kaizen-trends.py` (cap-dev-pipe) |

### End-to-end debugging sequence

1. Check `plan-ingestion-diagnostic.json` — is the seed quality adequate?
2. If seed quality is low, fix via ingestion kaizen config. Re-run Stage 5 only (`--stop-after ingestion`).
3. If seed quality is adequate, check `kaizen-metrics.json` — which features failed?
4. For failed features, trace from draft prompt → draft response → file on disk.
5. Use trend scripts from both stages to confirm the fix holds across runs.
