

# Kaizen for Plan Ingestion — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-07
> **Scope:** Systematic continuous improvement of the PlanIngestionWorkflow through run-over-run analysis — first as an isolated step, then as part of the larger Capability Delivery Pipeline
> **Design Principle:** [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md)
> **Companion:** [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md)
> **Implementation Home:** `~/Documents/dev/startd8-sdk/` (SDK workflow) + `~/Documents/dev/cap-dev-pipe/` (pipeline orchestration)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Status Dashboard](#2-status-dashboard)
3. [Layer 1 — Run Diagnostics & Persistence (REQ-KPI-1xx)](#3-layer-1--run-diagnostics--persistence-req-kpi-1xx)
4. [Layer 2 — Prompt-Response Pairing (REQ-KPI-2xx)](#4-layer-2--prompt-response-pairing-req-kpi-2xx)
5. [Layer 3 — Output Quality Metrics (REQ-KPI-3xx)](#5-layer-3--output-quality-metrics-req-kpi-3xx)
6. [Layer 4 — Cross-Run Aggregation (REQ-KPI-4xx)](#6-layer-4--cross-run-aggregation-req-kpi-4xx)
7. [Layer 5 — Feedback Loop (REQ-KPI-5xx)](#7-layer-5--feedback-loop-req-kpi-5xx)
8. [Layer 6 — Pipeline Integration (REQ-KPI-6xx)](#8-layer-6--pipeline-integration-req-kpi-6xx)
9. [Existing Capabilities Leveraged](#9-existing-capabilities-leveraged)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Verification Strategy](#11-verification-strategy)
12. [Cross-References](#12-cross-references)

---

## 1. Overview

### 1.1 Vision

Plan Ingestion is the bridge between a human-authored plan and machine-executable task seeds. Its quality directly determines the ceiling of everything downstream — the Prime Contractor or Artisan pipeline can only be as good as the seeds it receives. Yet today, plan ingestion runs are fire-and-forget: the workflow produces outputs, but there is no systematic mechanism to evaluate output quality, compare across runs, or feed insights back.

Under Kaizen, every plan ingestion run becomes a learning opportunity. Each phase (PARSE → ASSESS → TRANSFORM → REFINE → EMIT) produces observable outcomes that, when measured and compared, reveal concrete improvements for the next run.

### 1.2 The Plan Ingestion Pipeline

```
┌──────────┐    ┌──────────┐    ┌────────────┐    ┌──────────┐    ┌──────────┐
│  PARSE   │───→│  ASSESS  │───→│ TRANSFORM  │───→│  REFINE  │───→│   EMIT   │
│          │    │          │    │            │    │          │    │          │
│ Plan text│    │ Complexity│   │ Task YAML  │    │ Arc-review│   │ Context  │
│ → JSON   │    │ scoring + │   │ or Plan MD │    │ rounds   │    │ seed +   │
│ features │    │ routing   │    │            │    │          │    │ config   │
└──────────┘    └──────────┘    └────────────┘    └──────────┘    └──────────┘
   LLM call       LLM call        LLM call        N LLM calls    Deterministic
```

**Key characteristics:**
- 3 mandatory LLM calls (PARSE, ASSESS, TRANSFORM) + N optional (REFINE review rounds)
- PARSE produces the foundational structured representation — errors here cascade to all downstream phases
- ASSESS determines routing (Prime vs Artisan) which shapes the entire downstream pipeline
- TRANSFORM produces the contractor-consumable format — this is the primary quality-bearing output
- REFINE applies architectural review to improve the transformed output
- EMIT is deterministic assembly — no LLM, but schema validation and field coverage checks

### 1.3 What We Have Today

| Component | Location | What It Provides |
|-----------|----------|-----------------|
| `PlanIngestionWorkflow` | `workflows/builtin/plan_ingestion_workflow.py` | 5-phase workflow with OTel spans |
| `run-plan-ingestion.sh` | cap-dev-pipe | Provenance-driven orchestration with banner/timing |
| `StepResult` per phase | SDK workflow framework | Per-step agent name, timing, token counts, cost |
| `WorkflowResult` | SDK workflow framework | Aggregate success/failure, step list, total metrics |
| `_validate_context_seed()` | plan_ingestion_workflow.py | JSON schema validation on emitted seed |
| `_validate_seed_field_coverage()` | plan_ingestion_workflow.py | Advisory field-coverage warnings |
| `extract_code_from_response()` | utils/code_extraction.py | Code block extraction with raw fallback |
| OTel spans | Per-phase LLM spans | `llm.plan_ingestion.{parse,assess,transform}` with token/cost attributes |
| `run-atomic.sh` | cap-dev-pipe | Timestamped run dirs, state archiving, provenance chain |

### 1.4 Gaps to Close

| Gap | Problem | Impact | Layer |
|-----|---------|--------|-------|
| KPI-1 | No structured diagnostic report after plan ingestion | Cannot systematically evaluate run quality without reading logs | Layer 1 |
| KPI-2 | No prompt-response capture during runs | Cannot correlate prompt patterns with output quality | Layer 2 |
| KPI-3 | No quality metrics on TRANSFORM output | "Did it produce good seeds?" is unanswerable without manual inspection | Layer 3 |
| KPI-4 | No cross-run comparison | Cannot answer "is plan ingestion getting better?" | Layer 4 |
| KPI-5 | No feedback from analysis to next run | Each run starts from scratch regardless of prior learnings | Layer 5 |
| KPI-6 | Plan ingestion quality is invisible to downstream pipeline stages | Prime/Artisan contractor has no signal about seed quality before starting | Layer 6 |

### 1.5 Success Criteria

1. Every plan ingestion run produces a structured diagnostic report with per-phase metrics (KPI-1 closed)
2. Prompts and LLM responses are persisted for all 3 LLM-calling phases (KPI-2 closed)
3. TRANSFORM output quality is measurable via deterministic checks (KPI-3 closed)
4. A script can compare plan ingestion metrics across N archived runs (KPI-4 closed)
5. Prior-run analysis can influence prompt templates or thresholds for the next run (KPI-5 closed)
6. Downstream pipeline stages receive a quality signal from plan ingestion (KPI-6 closed)

### 1.6 Constraints

- **No new LLM calls** for Kaizen analysis — all quality checks are deterministic or use existing outputs
- **Minimal runtime overhead** — diagnostics capture must not measurably slow the workflow
- **Backward compatible** — existing CLI flags, `run-plan-ingestion.sh` arguments, and SDK APIs unchanged
- **Standalone first** — all Layer 1–5 capabilities work when plan ingestion runs in isolation (not via cap-dev-pipe)
- **Pipeline-ready** — Layer 6 defines the interface for downstream consumption but does not require cap-dev-pipe changes to be useful standalone
- **Secret safety** — prompt/response persistence must support opt-out to avoid leaking sensitive plan content

---

## 2. Status Dashboard

| Req ID | Description | Impl Home | Status | Closes |
|--------|-------------|-----------|--------|--------|
| **Layer 1 — Run Diagnostics & Persistence** | | | | |
| REQ-KPI-100 | Per-run diagnostic report | startd8-sdk | ✅ DONE | KPI-1 |
| REQ-KPI-101 | Per-phase timing and token breakdown | startd8-sdk | ✅ DONE | KPI-1 |
| REQ-KPI-102 | Diagnostic archive in run directory | cap-dev-pipe | PLANNED | KPI-1 |
| **Layer 2 — Prompt-Response Pairing** | | | | |
| REQ-KPI-200 | Prompt persistence for PARSE/ASSESS/TRANSFORM | startd8-sdk | ✅ DONE | KPI-2 |
| REQ-KPI-201 | Response persistence alongside prompts | startd8-sdk | ✅ DONE | KPI-2 |
| REQ-KPI-202 | Code extraction fallback tracking | startd8-sdk | ✅ DONE | KPI-2 |
| **Layer 3 — Output Quality Metrics** | | | | |
| REQ-KPI-300 | PARSE quality: feature extraction completeness | startd8-sdk | ✅ DONE | KPI-3 |
| REQ-KPI-301 | ASSESS quality: routing confidence | startd8-sdk | ✅ DONE | KPI-3 |
| REQ-KPI-302 | TRANSFORM quality: seed completeness score | startd8-sdk | ✅ DONE | KPI-3 |
| REQ-KPI-303 | TRANSFORM quality: task description density | startd8-sdk | ✅ DONE | KPI-3 |
| REQ-KPI-304 | REFINE quality: review acceptance rate | startd8-sdk | ✅ DONE | KPI-3 |
| **Layer 4 — Cross-Run Aggregation** | | | | |
| REQ-KPI-400 | Cross-run trend script | startd8-sdk | ✅ DONE | KPI-4 |
| REQ-KPI-401 | Phase-level metric comparison | startd8-sdk | ✅ DONE | KPI-4 |
| REQ-KPI-402 | Cost trajectory tracking | startd8-sdk | ✅ DONE | KPI-4 |
| **Layer 5 — Feedback Loop** | | | | |
| REQ-KPI-500 | Prompt template adjustment from prior analysis | startd8-sdk | ✅ DONE | KPI-5 |
| REQ-KPI-501 | Complexity threshold tuning | startd8-sdk | ✅ DONE | KPI-5 |
| REQ-KPI-502 | Kaizen config injection | cap-dev-pipe | PLANNED | KPI-5 |
| **Layer 6 — Pipeline Integration** | | | | |
| REQ-KPI-600 | Seed quality signal for downstream consumption | startd8-sdk | ✅ DONE | KPI-6 |
| REQ-KPI-601 | Quality gate: block contractor on low-quality seeds | cap-dev-pipe | ✅ DONE | KPI-6 |

### Implementation Notes

**REQ-KPI-302 Recalibration (2026-03-09):** The original 4-component quality formula (30% desc + 30% targets + 20% schema + 20% coverage) only measured *presence* of descriptions and target files, giving a perfect 1.0 to seeds with single-line descriptions. Commit `b601aed` recalibrates to a 6-component formula when `task_density` is provided:

| Component | Weight | What It Measures |
|-----------|--------|-----------------|
| Description presence | 0.20 | Tasks with non-empty `task_description` |
| Target file presence | 0.20 | Tasks with non-empty `target_files` |
| Schema validity | 0.15 | JSON schema validation passes |
| Field coverage | 0.15 | Optional enrichment fields populated |
| Description depth | 0.15 | Average of `min(chars/500, 1.0)` per task |
| Description richness | 0.15 | Fraction of tasks with code examples OR requirements refs |

The original 4-component formula is preserved when `task_density=None` (backward compatible).

**Density warnings** (REQ-KPI-303 extension): `compute_density_warnings()` generates actionable warnings when task descriptions are shallow (< 500 chars), lack code examples, or miss requirements references. These are surfaced in both the `_ingestion_quality` seed block and the `check_seed_quality.py` gate script.

---

## 3. Layer 1 — Run Diagnostics & Persistence (REQ-KPI-1xx)

**Closes:** Gap KPI-1 (no structured diagnostic report)

Today, plan ingestion produces a `WorkflowResult` with `StepResult` entries, but this is an in-memory object returned to the caller. There is no persistent, human-readable diagnostic artifact.

### REQ-KPI-100: Per-Run Diagnostic Report

After the EMIT phase completes (or on any phase failure), the workflow SHALL write a `plan-ingestion-diagnostic.json` to the output directory containing:

```json
{
  "schema_version": "1.0.0",
  "run_timestamp": "2026-03-07T15:57:38Z",
  "plan_source": "path/to/plan.md",
  "plan_checksum": "sha256:abc123...",
  "route": "prime",
  "overall_success": true,
  "phases": {
    "parse": {
      "success": true,
      "time_ms": 2340,
      "input_tokens": 1200,
      "output_tokens": 3400,
      "cost_usd": 0.012,
      "features_extracted": 6,
      "files_mentioned": 12,
      "code_extraction_fallback": true
    },
    "assess": {
      "success": true,
      "time_ms": 1100,
      "input_tokens": 800,
      "output_tokens": 400,
      "cost_usd": 0.004,
      "composite_score": 35,
      "route_decision": "prime",
      "route_forced": false,
      "code_extraction_fallback": true
    },
    "transform": {
      "success": true,
      "time_ms": 8500,
      "input_tokens": 2000,
      "output_tokens": 15000,
      "cost_usd": 0.045,
      "output_file": "plan-ingestion-tasks.yaml",
      "output_bytes": 27520,
      "code_extraction_fallback": false
    },
    "refine": {
      "success": true,
      "time_ms": 45000,
      "rounds_completed": 2,
      "suggestions_accepted": 4,
      "suggestions_rejected": 2,
      "cost_usd": 0.120
    },
    "emit": {
      "success": true,
      "time_ms": 150,
      "seed_file": "artisan-context-seed.json",
      "tasks_emitted": 6,
      "schema_valid": true,
      "field_coverage_warnings": ["no service_metadata"]
    }
  },
  "totals": {
    "time_ms": 57090,
    "cost_usd": 0.181,
    "input_tokens": 4000,
    "output_tokens": 18800,
    "llm_calls": 5
  }
}
```

**Leverages:** `StepResult` objects already carry `time_ms`, `input_tokens`, `output_tokens`, `cost`. The diagnostic report assembles these with phase-specific quality signals.

**Advisory persistence:** Wraps I/O in `try/except OSError` with `logger.warning` — never fails a successful ingestion run due to a report write error.

### REQ-KPI-101: Per-Phase Timing and Token Breakdown

Each `StepResult` already captures `time_ms`, `input_tokens`, `output_tokens`, and `cost`. However:

- The REFINE phase runs the `ArchitecturalReviewLogWorkflow` internally, which returns its own `WorkflowResult`. The diagnostic report SHALL extract per-round metrics from the review sub-workflow.
- The EMIT phase has no timing instrumentation today. Add `time.monotonic()` bookends around the emit logic and include in the diagnostic.

**Status: PARTIAL** — StepResult plumbing exists; phase-specific quality signals and EMIT timing are missing.

### REQ-KPI-102: Diagnostic Archive in Run Directory

When plan ingestion runs via `run-plan-ingestion.sh` within `run-atomic.sh`, the diagnostic report SHALL be archived alongside other run artifacts in the timestamped run directory.

**Leverages:** `run-atomic.sh` Phase 5 already archives `.startd8/state/`. Add `plan-ingestion-diagnostic.json` to the archive set.

---

## 4. Layer 2 — Prompt-Response Pairing (REQ-KPI-2xx)

**Closes:** Gap KPI-2 (no prompt-response capture)

The warning that triggered this investigation — `No code blocks found in response (27520 chars). Using raw response` — demonstrates why prompt-response pairing matters: we need to see what was asked and what came back to diagnose extraction issues.

### REQ-KPI-200: Prompt Persistence for PARSE/ASSESS/TRANSFORM

When a `--kaizen` flag or kaizen config is active, the workflow SHALL persist the full prompt text for each LLM-calling phase to disk:

```
{output_dir}/kaizen-prompts/
├── parse_prompt.txt
├── assess_prompt.txt
└── transform_prompt.txt
```

**Implementation:** The prompts are already constructed as local variables in `_phase_parse`, `_phase_assess`, `_phase_transform`. Add a conditional write after prompt construction, before the `agent.generate()` call.

**Size guard:** If a prompt exceeds 2 MB (e.g., very large plan text), truncate with a `<!-- TRUNCATED at 2MB -->` sentinel and record original byte count.

### REQ-KPI-201: Response Persistence Alongside Prompts

For each phase, persist the raw LLM response text alongside the prompt:

```
{output_dir}/kaizen-prompts/
├── parse_prompt.txt
├── parse_response.txt        ← NEW
├── assess_prompt.txt
├── assess_response.txt       ← NEW
├── transform_prompt.txt
└── transform_response.txt    ← NEW
```

This enables direct comparison of what was asked vs. what was returned. The `code_extraction_fallback` flag in the diagnostic report (REQ-KPI-100) indicates whether the response needed raw-text fallback.

### REQ-KPI-202: Code Extraction Fallback Tracking

When `extract_code_from_response()` falls back to raw response (no code fences found), the diagnostic report SHALL record this per phase. This is a quality signal: consistently fence-less responses indicate the prompt should explicitly request fenced output, or the model choice is suboptimal.

**Current state:** The warning `No code blocks found in response` already fires via `logger.warning`. The diagnostic report captures this as a boolean `code_extraction_fallback` field per phase.

---

## 5. Layer 3 — Output Quality Metrics (REQ-KPI-3xx)

**Closes:** Gap KPI-3 (no quality metrics on TRANSFORM output)

These are deterministic quality checks — no LLM calls required. They answer: "did plan ingestion produce good seeds?"

### REQ-KPI-300: PARSE Quality — Feature Extraction Completeness

After PARSE, compute:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `features_extracted` | `len(parsed_plan.features)` | Feature count vs. plan complexity |
| `features_with_targets` | Count of features where `len(target_files) > 0` | Percentage of features with actionable file targets |
| `features_with_deps` | Count of features where `len(dependencies) > 0` | Dependency graph completeness |
| `multi_file_features` | Features with `len(target_files) > 1` | Multi-file violation count (should be 0 per prompt guidance) |
| `features_with_signatures` | Features with non-empty `api_signatures` | API contract extraction rate |
| `dep_graph_coverage` | Features in `dependency_graph` / total features | Are all features represented in the graph? |

**Threshold alert:** If `multi_file_features > 0`, log a warning — multi-file tasks reliably fail downstream (per prompt guidance).

### REQ-KPI-301: ASSESS Quality — Routing Confidence

After ASSESS, compute:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `composite_score` | Direct from `ComplexityScore.composite` | Raw complexity estimate |
| `route_decision` | `ComplexityScore.route.value` | Prime vs Artisan |
| `route_margin` | `abs(composite - threshold)` | How close to the threshold — low margin = uncertain routing |
| `llm_route_agreement` | LLM's suggested route == deterministic route | Model agrees with threshold logic |
| `dimension_spread` | `max(dims) - min(dims)` | Wide spread may indicate conflicting signals |

**Threshold alert:** If `route_margin < 10`, log a warning — the routing decision is borderline and may flip on minor plan changes.

### REQ-KPI-302: TRANSFORM Quality — Seed Completeness Score

After TRANSFORM and EMIT, compute a composite seed quality score:

| Metric | How | Weight | What It Reveals |
|--------|-----|--------|-----------------|
| `tasks_with_description` | Tasks where `config.task_description` is non-empty | 0.3 | Every task must have implementation instructions |
| `tasks_with_targets` | Tasks where `config.context.target_files` is non-empty | 0.3 | Every task must know its output file |
| `schema_valid` | `_validate_context_seed()` passes | 0.2 | Seed is structurally correct |
| `field_coverage` | 1.0 - (warning_count / total_field_checks) from `_validate_seed_field_coverage()` | 0.2 | Optional enrichment fields populated |

Weighted sum produces `seed_quality_score` (0.0–1.0). Recorded in the diagnostic report.

### REQ-KPI-303: TRANSFORM Quality — Task Description Density

For each emitted task, measure description density:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `description_chars` | `len(task_description)` | Raw length |
| `description_lines` | Line count | Structural complexity |
| `has_code_examples` | Contains `` ``` `` blocks | Implementation guidance present |
| `has_requirements_refs` | Matches `REQ-*` pattern | Traceability to requirements |
| `has_negative_scope` | `negative_scope` field non-empty | Explicit exclusions reduce hallucination |

**Threshold alert:** If any task description is < 100 chars, log a warning — thin descriptions produce poor code generation results.

### REQ-KPI-304: REFINE Quality — Review Acceptance Rate

After REFINE, extract from the architectural review sub-workflow:

| Metric | How | What It Reveals |
|--------|-----|-----------------|
| `suggestions_total` | Total suggestions across all rounds | Review thoroughness |
| `suggestions_accepted` | Suggestions classified as ACCEPT | Improvement uptake |
| `acceptance_rate` | accepted / total | High = reviews are actionable; low = reviews miss the mark or doc is already good |
| `rounds_completed` | Number of review iterations | Actual vs configured rounds |
| `areas_covered` | Distinct review areas addressed | Coverage breadth |

---

## 6. Layer 4 — Cross-Run Aggregation (REQ-KPI-4xx)

**Closes:** Gap KPI-4 (no cross-run comparison)

### REQ-KPI-400: Cross-Run Trend Script

A script (`run-kaizen-plan-ingestion-trends.sh` or Python CLI) SHALL read diagnostic reports from multiple archived runs and produce a trend summary:

```
Plan Ingestion Trends (last 5 runs)
─────────────────────────────────────
                      run-003  run-004  run-005  run-006  run-007
Route                 prime    prime    artisan  prime    prime
Features extracted    6        6        12       6        8
Seed quality score    0.72     0.78     0.65     0.82     0.85  ↑
Total cost (USD)      $0.18    $0.16    $0.42    $0.15    $0.14  ↓
PARSE time (ms)       2340     2100     4800     1900     1850  ↓
Code fence fallbacks  2/3      1/3      2/3      0/3      0/3   ↓
Multi-file violations 1        0        3        0        0     ↓
```

**Leverages:** `run-atomic.sh` already archives run outputs in timestamped directories. Diagnostic reports (REQ-KPI-100) provide the queryable data.

### REQ-KPI-401: Phase-Level Metric Comparison

The trend script SHALL support per-phase drill-down, comparing the same phase across runs. This reveals which phases are improving vs. degrading independently.

### REQ-KPI-402: Cost Trajectory Tracking

Track cost per phase across runs. Plan ingestion is a fixed-structure pipeline (always 3+N LLM calls), so cost variance indicates either plan complexity differences or model/prompt changes.

---

## 7. Layer 5 — Feedback Loop (REQ-KPI-5xx)

**Closes:** Gap KPI-5 (no feedback from analysis to next run)

### REQ-KPI-500: Prompt Template Adjustment from Prior Analysis

When diagnostic analysis reveals a recurring issue (e.g., `code_extraction_fallback: true` on >50% of runs for PARSE), the Kaizen config SHALL support prompt template overrides:

```json
{
  "plan_ingestion_kaizen": {
    "parse_prompt_suffix": "\n\nIMPORTANT: Wrap your JSON output in ```json code fences.",
    "assess_prompt_suffix": "",
    "transform_prompt_suffix": ""
  }
}
```

The workflow appends the suffix to the base prompt template before the LLM call. This is the minimal viable feedback loop — a human writes the suffix based on diagnostic analysis, and it persists across runs.

### REQ-KPI-501: Complexity Threshold Tuning

When cross-run analysis shows routing instability (frequent `route_margin < 10` or downstream success rate varies by route), the Kaizen config SHALL support threshold override:

```json
{
  "plan_ingestion_kaizen": {
    "complexity_threshold_override": 45
  }
}
```

This overrides the default `complexity_threshold=40` without changing the SDK code.

### REQ-KPI-502: Kaizen Config Injection

`run-plan-ingestion.sh` SHALL accept an optional `--kaizen-config` flag pointing to a JSON file. The workflow reads this file and applies overrides (prompt suffixes, threshold adjustments) before execution.

**Standalone support:** The `PlanIngestionWorkflow` itself accepts a `kaizen_config` parameter in its config dict, independent of the shell script.

---

## 8. Layer 6 — Pipeline Integration (REQ-KPI-6xx)

**Closes:** Gap KPI-6 (plan ingestion quality invisible to downstream)

This layer defines how plan ingestion communicates quality to the next pipeline stage (Prime Contractor or Artisan).

### REQ-KPI-600: Seed Quality Signal for Downstream Consumption

The emitted context seed SHALL include a `_ingestion_quality` metadata block:

```json
{
  "version": "1.0.0",
  "tasks": [...],
  "_ingestion_quality": {
    "seed_quality_score": 0.85,
    "features_extracted": 8,
    "multi_file_violations": 0,
    "code_extraction_fallbacks": 0,
    "route_margin": 25,
    "field_coverage_warnings": ["no service_metadata"],
    "diagnostic_report_path": "plan-ingestion-diagnostic.json"
  }
}
```

The `_` prefix signals advisory metadata (not consumed by task execution logic). Downstream tooling can read this to decide whether to proceed or flag for human review.

### REQ-KPI-601: Quality Gate — Block Contractor on Low-Quality Seeds

When `seed_quality_score < configurable_threshold` (default: 0.5), `run-cap-delivery.sh` SHALL pause and prompt the operator:

```
⚠ Plan ingestion seed quality score: 0.38 (threshold: 0.50)
  Warnings: 3 tasks missing target_files, no service_metadata

  Continue to contractor? [y/N]
```

This prevents low-quality seeds from wasting downstream LLM budget.

---

## 9. Existing Capabilities Leveraged

| Capability | Source | Kaizen Use |
|-----------|--------|------------|
| `StepResult` per phase | `workflows/models.py` | Foundation for REQ-KPI-100 (timing, tokens, cost) |
| `_validate_context_seed()` | `plan_ingestion_workflow.py` | Schema validation signal for REQ-KPI-302 |
| `_validate_seed_field_coverage()` | `plan_ingestion_workflow.py` | Field coverage warnings for REQ-KPI-302 |
| `extract_code_from_response()` | `utils/code_extraction.py` | Fallback detection for REQ-KPI-202 |
| OTel spans per phase | `plan_ingestion_workflow.py` | Timing and token attribution for REQ-KPI-101 |
| `run-atomic.sh` | cap-dev-pipe | Run directory isolation for REQ-KPI-102 |
| `run-plan-ingestion.sh` | cap-dev-pipe | Entry point for REQ-KPI-502 (kaizen config injection) |
| `ArchitecturalReviewLogWorkflow` | SDK workflows | REFINE metrics source for REQ-KPI-304 |
| `run-kaizen-trends.sh` | cap-dev-pipe | Pattern for REQ-KPI-400 (cross-run trends) |
| Kaizen config pattern | `KAIZEN_PRIME_REQUIREMENTS.md` (REQ-KZ-500) | Config injection pattern reusable for REQ-KPI-502 |

---

## 10. Traceability Matrix

| Gap | Requirements | Kaizen Principle Rule |
|-----|-------------|---------------------|
| KPI-1: No diagnostic report | REQ-KPI-100, 101, 102 | Rule 1 (preserve all outputs) |
| KPI-2: No prompt-response capture | REQ-KPI-200, 201, 202 | Rule 2 (prompt-response pairing) |
| KPI-3: No output quality metrics | REQ-KPI-300, 301, 302, 303, 304 | Rule 3 (measure before and after) |
| KPI-4: No cross-run comparison | REQ-KPI-400, 401, 402 | Rule 3 (measure) + Rule 6 (automate) |
| KPI-5: No feedback loop | REQ-KPI-500, 501, 502 | Rule 5 (feed forward) |
| KPI-6: Quality invisible downstream | REQ-KPI-600, 601 | Rule 5 (feed forward) + Rule 4 (attributable changes) |

---

## 11. Verification Strategy

### Standalone Verification (Plan Ingestion in Isolation)

1. **Diagnostic report smoke test:** Run plan ingestion on a known plan, verify `plan-ingestion-diagnostic.json` is written with all required fields
2. **Quality metrics accuracy:** Run on a plan with known characteristics (e.g., 6 single-file features) and verify PARSE quality metrics match expectations
3. **Prompt-response persistence:** Run with `--kaizen` flag, verify prompt/response files exist for all 3 LLM phases
4. **Code extraction fallback detection:** Use a model known to omit code fences; verify `code_extraction_fallback: true` in diagnostic
5. **Seed quality score:** Construct a seed with known gaps (missing descriptions, missing targets); verify quality score reflects the gaps

### Pipeline Verification (Within cap-dev-pipe)

6. **Archive inclusion:** Run via `run-atomic.sh`; verify diagnostic report appears in timestamped run directory
7. **Cross-run trend:** Run plan ingestion 3 times on the same plan with incremental prompt improvements; verify trend script shows improvement
8. **Quality gate:** Set `seed_quality_threshold: 0.99`; verify cap-delivery pipeline pauses with quality warning
9. **Kaizen config injection:** Provide `--kaizen-config` with prompt suffix; verify the suffix appears in persisted prompts

---

## 12. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_DESIGN_PRINCIPLE.md](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | Governing design principle |
| [KAIZEN_PRIME_REQUIREMENTS.md](../prime/KAIZEN_PRIME_REQUIREMENTS.md) | Companion: Kaizen for the Prime Contractor (downstream consumer of plan ingestion output) |
| [MOTTAINAI_DESIGN_PRINCIPLE.md](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Related: don't waste within a run (vs. Kaizen: don't waste across runs) |
| `plan_ingestion_workflow.py` | Implementation target for Layers 1–3, 5 |
| `run-plan-ingestion.sh` | Implementation target for Layers 2, 5–6 |
| `run-cap-delivery.sh` | Integration point for Layer 6 quality gate |
| SDK Lessons: Leg 10 #13–14 | Phase error-return pattern, shared token_usage utility |
| SDK Lessons: Leg 13 #42–43 | Plan ingestion auto-filter and dual-seed consistency |
