# Artisan Contractor Workflow — Functional Requirements

**Version:** 1.5.0
**Created:** 2026-02-14
**Canonical Source:** [`docs/capability-index/startd8.artisan.functional-requirements.yaml`](capability-index/startd8.artisan.functional-requirements.yaml)

---

## Overview

This document provides narrative context, dependency diagrams, and a traceability matrix for the formal functional requirements defined in the canonical YAML. The artisan contractor is an 8-phase workflow orchestrator for structured multi-task code generation with design review, cost budget enforcement, and checkpoint-based recovery.

### Status Dashboard

| Layer | ID Range | Total | Implemented | Partial | Planned |
|-------|----------|-------|-------------|---------|---------|
| Phase Behavior | AR-1xx | 46 | 37 | 0 | 9 |
| Orchestration | AR-2xx | 16 | 9 | 0 | 7 |
| ContextCore Data Flow | AR-3xx | 12 | 2 | 0 | 10 |
| Cost Model | AR-4xx | 8 | 6 | 1 | 1 |
| Handoff and Recovery | AR-5xx | 12 | 8 | 0 | 4 |
| Observability | AR-6xx | 8 | 6 | 0 | 2 |
| Configuration | AR-7xx | 10 | 8 | 0 | 2 |
| Safety and Resilience | AR-8xx | 26 | 6 | 0 | 20 |
| Mottainai Compliance | AR-9xx | 9 | 0 | 0 | 9 |
| Project-Centric Context | AR-10xx | 20 | 3 | 0 | 17 |
| **Total** | | **167** | **85** | **1** | **81** |

---

## Layer 1: Phase Behavior (AR-1xx)

Defines input, behavior, and output contracts for each of the 8 phases.

### Pipeline Data Flow

```mermaid
flowchart LR
    subgraph plan [PLAN]
        AR100[AR-100 Seed Loading]
        AR101[AR-101 Preflight Abort]
        AR102[AR-102 Domain Distribution]
    end

    subgraph scaffold [SCAFFOLD]
        AR110[AR-110 Directory Creation]
        AR111[AR-111 Output Conventions]
    end

    subgraph design [DESIGN]
        AR120[AR-120 Dual-Review]
        AR121[AR-121 Depth Calibration]
        AR122[AR-122 Adopt Prior]
        AR123[AR-123 Env Skip]
        AR124[AR-124 Cross-Task Context]
        AR125[AR-125 Parameter Sources]
        AR126[AR-126 Semantic Conventions]
        AR127[AR-127 Existing File Detection]
        AR128[AR-128 design_mode Propagation]
    end

    subgraph implement [IMPLEMENT]
        AR130[AR-130 Chunk Execution]
        AR131[AR-131 Design Injection]
        AR132[AR-132 Gate 2a/2c]
        AR133[AR-133 Gate 3]
        AR134[AR-134 Resume]
        AR135[AR-135 Token Caps]
        AR136[AR-136 Auto-Commit]
        AR137[AR-137 Param Sources]
    end

    subgraph integrate [INTEGRATE]
        AR170[AR-170 Staging Merge]
        AR171[AR-171 Pre-Validation]
        AR172[AR-172 Snapshot Rollback]
        AR173[AR-173 Success Rate Gate]
        AR174[AR-174 Dirty File Protection]
        AR175[AR-175 Truncation Guard]
        AR176[AR-176 Auto-Commit Scope]
    end

    subgraph test [TEST]
        AR140[AR-140 Validators]
        AR141[AR-141 Results]
        AR142[AR-142 Command Mapping]
        AR143[AR-143 Import Dependency]
        AR144[AR-144 Protocol Fidelity]
        AR145[AR-145 Proto Field Refs]
        AR146[AR-146 Placeholder Detection]
        AR147[AR-147 Dockerfile Coherence]
    end

    subgraph review [REVIEW]
        AR150[AR-150 LLM Review]
        AR151[AR-151 Results]
        AR152[AR-152 Stub Exclusion]
    end

    subgraph finalize [FINALIZE]
        AR160[AR-160 Artifact Collection]
        AR161[AR-161 Manifest]
        AR162[AR-162 Execution Report]
        AR163[AR-163 Cost Summary]
        AR164[AR-164 Provenance]
        AR165[AR-165 Gate 3 Compat]
    end

    plan --> scaffold --> design --> implement --> integrate --> test --> review --> finalize
```

### Per-Phase Context Keys

| Phase | Context Keys Set | Source |
|-------|-----------------|--------|
| PLAN | `tasks`, `task_index`, `plan_title`, `plan_goals`, `domain_summary`, `preflight_summary`, `total_estimated_loc`, `architectural_context`, `design_calibration`, `example_artifacts`, `service_metadata`, `plan_document_text`, `onboarding_*` (6 fields) | AR-100, AR-1001..AR-1003 |
| SCAFFOLD | `scaffold` (directories_needed, directories_exist, directories_created, existing_target_files, skipped_targets, project_root) | AR-110 |
| DESIGN | `design_results` (per-task: design_document, status, agreed, iterations, cost, design_mode, existing_file_inventory) | AR-120, AR-127 |
| IMPLEMENT | `implementation`, `generation_results`, `_downstream_map` | AR-130 |
| INTEGRATE | `integration_results` (per-task: success, integrated_files, errors, rollback_performed) | AR-170..AR-176 |
| TEST | `test_results` (test_plan, total_passed, total_failed, per_task) | AR-140..AR-147 |
| REVIEW | `review_results` (review_items, total_cost, total_passed, total_failed, per_task) | AR-150 |
| FINALIZE | `workflow_summary` | AR-160 |

### INTEGRATE Phase Requirements (AR-170..AR-176)

The INTEGRATE phase is a purely mechanical (no LLM) merge step that moves staged generated code from `_staging_dir` into `project_root` with validation and rollback. It bridges the gap between code generation (IMPLEMENT) and code verification (TEST), ensuring that downstream phases operate on a fully integrated codebase.

**Entry:** `generation_results` (blocking), `_staging_dir` (warning, default: `.startd8/staging/`)
**Exit:** `integration_results` (blocking, quality: `success_rate >= 0.5` warning)

#### AR-170: Staging-to-Project Merge

**Status:** implemented
**Source:** `context_seed_handlers.py` (IntegratePhaseHandler), `integration_engine.py`

For each task in `generation_results` with `success=True`, copy staged files from `_staging_dir` into `project_root` using the configured `MergeStrategy`. Update `generation_results` file paths to reflect their final project_root locations. Clean `_staging_dir` after all tasks complete (unless `dry_run=True`).

**Acceptance criteria:**
1. Only tasks with `generation_results[task_id].success == True` are processed.
2. Staged files are resolved via `sanitize_path()` relative to `project_root`.
3. `generation_results` file paths are updated in-place to project_root locations after successful merge.
4. `_staging_dir` is removed after integration (non-dry-run).

#### AR-171: Pre-Merge Validation

**Status:** implemented
**Source:** `integration_engine.py` (pre-validate step)

Before merging, validate all generated `.py` files for syntax correctness and lint compliance. Syntax failures are blocking (halt integration for that task). Lint failures are advisory (logged, do not block).

**Acceptance criteria:**
1. `py_compile` or `ast.parse` is run on each generated `.py` file before merge.
2. Syntax errors produce a blocking failure — the task's integration is skipped.
3. Lint check failures are logged as advisory warnings.

#### AR-172: Snapshot-Based Rollback

**Status:** implemented (file-based; AR-807 for git-based upgrade is planned)
**Source:** `integration_engine.py` (_snapshot_target, _restore_target, _cleanup_snapshots)

Before overwriting any existing file, create a `.pre_integration` sidecar snapshot. If post-merge checkpoint validation fails, restore all targets from snapshots (atomic per-task rollback). Clean up sidecar files on success.

**Acceptance criteria:**
1. Each target file is snapshotted before the first merge attempt (idempotent).
2. Absent targets are recorded as `None` so rollback can delete newly created files.
3. On checkpoint failure, all targets for the failing task are restored from snapshots.
4. Sidecar files are cleaned up after successful integration.

#### AR-173: Success Rate Quality Gate

**Status:** implemented
**Source:** `artisan-pipeline.contract.yaml` (integrate exit), `_QUALITY_EXTRACTORS["success_rate"]`

The INTEGRATE exit contract declares a `success_rate` quality metric with threshold 0.5 and warning severity. The metric computes the fraction of per-task results where `success == True`. Below-threshold triggers a warning (pipeline continues) but is logged for observability.

**Acceptance criteria:**
1. `success_rate` extractor is registered in `_QUALITY_EXTRACTORS`.
2. A success rate of 0.0 (all tasks failed) triggers a warning violation.
3. A success rate >= 0.5 produces no quality violation.

#### AR-174: Dirty File Protection

**Status:** implemented
**Source:** `integration_engine.py` (dirty file check)

Before merging into an existing file, check if the target has uncommitted changes in git. If `allow_dirty=False` (default), abort the merge for that file to prevent overwriting in-progress work.

**Acceptance criteria:**
1. `git status --porcelain` is consulted for each target before overwrite.
2. Dirty files cause the task's integration to fail (not the entire pipeline).

#### AR-175: Truncation Guard

**Status:** implemented
**Source:** `integration_engine.py` (truncation detection)

Apply code-mode-aware truncation detection to each generated file before merge. High-confidence truncation (above reject threshold) blocks the merge for that task. Lower-confidence truncation produces a warning.

**Acceptance criteria:**
1. `detect_truncation()` is called with `code_mode=True` on generated code.
2. High-confidence truncation rejects the file and records an error.
3. Lower-confidence truncation logs a warning but allows the merge.

#### AR-176: Scoped Auto-Commit

**Status:** implemented
**Source:** `integration_engine.py` (_commit_files), `context_seed_handlers.py` (IntegratePhaseHandler)

Auto-commit (when enabled) happens in INTEGRATE, not in IMPLEMENT. Commits are scoped to the specific files that were successfully integrated — never `git add -A`.

**Acceptance criteria:**
1. `git add` is called with explicit file paths (not `-A` or `.`).
2. `git add` return code is checked; failures are logged.
3. Only successfully integrated files are staged for commit.

---

## Layer 2: Orchestration (AR-2xx)

Controls phase sequencing, gate enforcement, timeout, budget, and execution modes.

```mermaid
flowchart TD
    AR200[AR-200 Phase Ordering] --> AR201[AR-201 Gate Enforcement]
    AR200 --> AR202[AR-202 Per-Phase Timeout]
    AR200 --> AR203[AR-203 Total Timeout]
    AR200 --> AR204[AR-204 Cost Budget]
    AR200 --> AR205[AR-205 Dry-Run]
    AR200 --> AR206[AR-206 Feature-Serial]
    AR200 --> AR207[AR-207 Stop-After]
    AR200 --> AR208[AR-208 Phase Subsets]
    AR204 --> AR209[AR-209 Cost Projection]
    AR200 --> AR210[AR-210 Phase Skipping]
    AR200 --> AR211[AR-211 Advisory Lock]
    AR200 --> AR212[AR-212 Wave-Parallel]
    AR206 -.->|mutually exclusive| AR212
```

### Execution Modes

| Mode | Config | Behavior | Requirements |
|------|--------|----------|-------------|
| **Single-feature quality flow** (default runner policy) | `feature_serial=True` and no `--allow-batch-mode` | Runner enforces one-task-at-a-time quality flow. Batch modes are blocked unless explicitly overridden. | AR-206 |
| **Phase-serial** (batch opt-in) | `feature_serial=False` with `--allow-batch-mode` | All tasks complete each phase before moving to next | AR-200 |
| **Feature-serial** (engine behavior) | `feature_serial=True` | Each task completes DESIGN->IMPLEMENT->INTEGRATE->TEST->REVIEW before next task. Within one workflow execution, PLAN/SCAFFOLD run once before inner phases and FINALIZE runs once after. Mutually exclusive with `wave_parallel` mode (`WorkflowConfig` validation raises `ValueError` if both are set). | AR-206 |
| **Wave-parallel** | `wave_parallel=True` | Tasks are grouped into dependency waves derived from `depends_on`; lanes within each wave execute concurrently, with a barrier between waves for context merge and budget enforcement. Mutually exclusive with `feature_serial` and `lane_parallel` modes. Degenerates to lane-parallel when no inter-task dependencies exist. | AR-212 |
| **Dry-run** | `dry_run=True` | All phases execute but skip LLM calls; cost=0 | AR-205 |
| **Design-only** | `--stop-after design` | PLAN->SCAFFOLD->DESIGN, writes handoff | AR-207, AR-208 |
| **Implement-only** | loads handoff | IMPLEMENT->INTEGRATE->TEST->REVIEW->FINALIZE | AR-208 |

### AR-212: Wave-Parallel Execution Mode

**Status:** planned
**Depends on:** AR-900 (full design metadata serialization — P0 blocker for wave context merging), AR-902 (reuse of `_downstream_map` — required for wave-parallel's merge field registry)

Wave-parallel execution partitions the task set into dependency waves computed from the `depends_on` graph in the seed. Within each wave, tasks execute as concurrent lanes (up to a configurable concurrency limit). A barrier at the end of each wave merges lane contexts, enforces cost budget checks, and persists a checkpoint before the next wave begins.

**Acceptance criteria:**

1. `WorkflowConfig` validation raises `ValueError` when `wave_parallel=True` and either `feature_serial=True` or `lane_parallel=True`.
2. **Dependency ordering invariant:** No task executes before all tasks it `depends_on` have completed. Waves are computed from the task-level `depends_on` DAG such that every task in wave *N* depends only on tasks in waves 0..*N*−1. Tasks with no dependencies are assigned to wave 0.
3. Within a wave, lanes execute concurrently with thread-safe context isolation.
4. A wave barrier synchronizes all lanes before the next wave starts: lane contexts are merged, cost budget is checked, and a checkpoint is written.
5. When no `depends_on` edges exist, all tasks are placed in wave 0 and behavior is equivalent to lane-parallel.
6. Checkpoint schema v4 fields (`wave_assignments`, `completed_waves`, `current_wave`, `wave_resume_count`) are persisted at each wave barrier.
7. Resume from a wave checkpoint restarts from the incomplete wave, re-executing only incomplete lanes within that wave. Before resuming, a state-to-code integrity check verifies that generated files from completed lanes exist on disk; lanes whose output files are missing are marked incomplete and re-executed.
8. A configurable `max_wave_resume_attempts` limits how many times a wave can be retried on resume. If a wave fails after the maximum number of attempts, the workflow transitions to `FAILED_UNRECOVERABLE` status, preventing unbounded cost waste from poison-pill tasks in resume loops. The `wave_resume_count` checkpoint field (see AR-505) tracks attempts across resume boundaries.

### Prime-Convergent Quality Requirements

The following requirements capture the Prime Contractor design/generation patterns that are being adopted in Artisan while preserving Artisan's phase boundaries:

| Requirement | Status | Intent |
|-------------|--------|--------|
| AR-129 | planned | DESIGN runs a spec -> draft -> review loop with a configurable pass threshold before IMPLEMENT |
| AR-139 | planned | DESIGN/IMPLEMENT handoff enforces resolved-parameter completeness gating |
| AR-138 | implemented | IMPLEMENT adds preflight decomposition and staleness/provenance-aware reuse |
| AR-153 | implemented | INTEGRATE/TEST/REVIEW failures feed bounded regenerate-with-feedback retries |
| AR-166 | implemented | FINALIZE persists Prime-style forensic artifacts (`spec`, `draft-*`, `review-*`, `integration`) |
| AR-206 | implemented | Single-feature quality flow remains the default runner policy (batch requires explicit opt-in) |

---

## Layer 3: ContextCore Data Flow (AR-3xx)

Closes the data flow gaps between ContextCore export output and the artisan workflow. This is the primary new requirement layer identified by the pipeline audit.

### Provenance Chain

```mermaid
flowchart LR
    CC[".contextcore.yaml"] -->|sha256| OM["onboarding-metadata.json<br/>source_checksum"]
    OM -->|propagate| PI["Plan Ingestion<br/>ArtisanContextSeed"]
    PI -->|AR-300| PLAN["PLAN phase<br/>context source_checksum"]
    PLAN -->|AR-302| FIN["FINALIZE<br/>generation-manifest.json<br/>provenance.source_checksum"]
    FIN -->|AR-309| G3["Gate 3<br/>a2a-diagnose"]
```

### Enrichment Data Flow

| Onboarding Field | Propagation | Consumption | Requirements |
|-----------------|-------------|-------------|-------------|
| `source_checksum` | seed -> PLAN context | FINALIZE manifest | AR-300, AR-301, AR-302 |
| `parameter_sources` | seed -> PLAN context | DESIGN prompts, IMPLEMENT chunks | AR-303, AR-304, AR-305, AR-125, AR-137 |
| `semantic_conventions` | seed -> PLAN context | DESIGN prompts, IMPLEMENT chunks | AR-306, AR-126 |
| `output_conventions` | seed -> PLAN context | SCAFFOLD validation | AR-307, AR-111 |
| `design_calibration_hints` | onboarding -> context | DESIGN cross-check | AR-308 |
| `coverage_gaps` | onboarding -> seed | PLAN scoping | AR-311 |

---

## Layer 4: Cost Model (AR-4xx)

Defines the 3-tier model architecture, budget enforcement, and cost reporting.

### Model Tier Architecture

| Tier | Alias | Role | Catalog Entry | Default Agent | Purpose | Cost/1M |
|------|-------|------|--------------|---------------|---------|---------|
| T1 | Economy | Drafter | `DRAFT_MODEL_CLAUDE_HAIKU` / `T1_ECONOMY` | `anthropic:claude-haiku-4-5-20251001` | Fast draft generation, cheap retries | ~$1 |
| T2 | Standard | Validator | `VALIDATE_MODEL_CLAUDE_SONNET` / `T2_STANDARD` | `anthropic:claude-sonnet-4-5-20250929` | Refinement, validation, quality gating | ~$3 |
| T3 | Premium | Reviewer | `REVIEW_MODEL_CLAUDE_OPUS` / `T3_PREMIUM` | `anthropic:claude-opus-4-6` | Final review, arbitration, complex design | ~$15 |

> **Runtime note:** `HandlerConfig.lead_agent` defaults to Opus (T3), `drafter_agent` to Haiku (T1), and `tier2_agent` to Sonnet (T2). The default IMPLEMENT flow is now T1 draft → T2 refine. Use `--skip-refinement` to bypass T2 and use T1 output directly.

### Phase-to-Tier Mapping

| Phase | T1 (Economy) | T2 (Standard) | T3 (Premium) |
|-------|-------------|---------------|--------------|
| DESIGN | — | — | Generate + review |
| IMPLEMENT | Draft code | Refine draft (AR-408) | — |
| TEST | Generate tests | — | — |
| REVIEW | — | — | Evaluate quality |

### T2 Refinement in IMPLEMENT (AR-408)

After T1 generates draft code, T2 refines it:
1. T1 writes files to staging
2. T2 reads back the complete files (not search/replace blocks)
3. T2 receives a refinement prompt with task context + draft code
4. T2 outputs refined complete files
5. Refined code overwrites T1 output in staging

**Non-fatal**: If T2 fails, returns empty code, or throws an exception, the T1 draft is preserved as final output. T2 is purely additive.

**Opt-out**: `--skip-refinement` or `HandlerConfig(skip_refinement=True)`.

**Acceptance criteria:**
- AC-1: T2 refiner is called after T1 drafter when `tier2_agent` is set and `skip_refinement=False`
- AC-2: T2 failure preserves T1 output (non-fatal)
- AC-3: Cost metrics include both T1 and T2 (`chunk.metadata["refine_cost_usd"]`)
- AC-4: `iterations=2` in `GenerationResult` when T2 runs
- AC-5: Forensic log emits `implement.chunk.refine` event

### Walk-Through Mode (AR-409)

A zero-cost execution mode that builds and persists all LLM prompts (DESIGN + IMPLEMENT) without making LLM calls. Useful for prompt analysis and debugging.

**Output structure:**
```
.startd8/walkthrough/
├── design/<task-id>/
│   ├── generate_system_prompt.md
│   ├── generate_user_prompt.md
│   ├── review_system_prompt.md
│   ├── review_user_prompt.md
│   ├── arbiter_system_prompt.md
│   └── arbiter_user_prompt.md
├── implement/<task-id>/
│   ├── t1_system_prompt.md
│   ├── t1_user_prompt.md
│   ├── t2_refine_system_prompt.md  (if T2 enabled)
│   ├── t2_refine_user_prompt.md    (template with {draft_code})
│   └── metadata.json
```

**Activation**: `--walkthrough` or `HandlerConfig(walkthrough=True)`.

**Acceptance criteria:**
- AC-1: IMPLEMENT walkthrough persists T1 prompts and skips LLM call
- AC-2: DESIGN walkthrough persists generate + review prompts and returns synthetic results
- AC-3: T2 prompt template contains `{draft_code}` placeholder
- AC-4: No LLM API calls are made in walkthrough mode

### IMPLEMENT Prompt Quality (AR-410 — AR-412)

Improvements identified via AR-409 walkthrough evaluation of the IMPLEMENT phase T1/T2 prompts. These address prompt clarity, context hygiene, and T2 token efficiency.

#### Existing-File vs Design-Doc Section Disambiguation (AR-410)

The "Existing Files" section in the T1 user prompt currently embeds the design document's proposed SEARCH/REPLACE blocks inline with the existing file content. This creates semantic ambiguity: the drafter sees nested SEARCH/REPLACE blocks (the design doc's changes inside the "existing file" fence, plus the output format instructions telling it to produce its own SEARCH/REPLACE blocks).

**Required change:** Separate the existing file content from the design document's change instructions into distinct, clearly labeled sections:
- **"Existing Files"** — Contains only the current file content as-is (raw source, no change blocks)
- **"Design Document"** — Contains the design doc's proposed changes (SEARCH/REPLACE blocks or prose), clearly labeled as the authoritative change specification

**Acceptance criteria:**
- AC-1: The "Existing Files" section contains only raw source code, not SEARCH/REPLACE blocks from the design document
- AC-2: Design document content appears in a separate section (e.g., "AUTHORITATIVE Design Changes" or "AUTHORITATIVE Design Document") that is visually and semantically distinct from the existing file listing
- AC-3: The drafter prompt contains no nested SEARCH/REPLACE blocks (the only SEARCH/REPLACE format instructions are for the drafter's own output)

#### Stale Context Filtering (AR-411)

Upstream context fields (`architectural_context`, `service_metadata`, `onboarding_calibration_hints`) may contain template defaults from `.contextcore.yaml` that are not project-specific. When these placeholders propagate to the T1/T2 prompts, they waste tokens and can actively contradict the task (e.g., "Do NOT proceed to Phase 1" as a blocking constraint).

**Required change:** Filter or suppress context sections that contain recognizable template defaults before injecting them into prompts.

**Detection heuristics** (at least one must match to suppress):
- `architectural_context.objectives` contains "Example objective" or "update with real business goal"
- `architectural_context.constraints` contains "Do NOT proceed to Phase 1"
- `service_metadata` contains "HEALTHCHECK type MUST match transport_protocol" without an actual `transport_protocol` value

**Acceptance criteria:**
- AC-1: When `architectural_context` contains template-default placeholders, the "Project Architecture" section is omitted from the T1 user prompt
- AC-2: When `service_metadata` contains only generic boilerplate, the "Service Metadata" section is omitted from the T1 user prompt
- AC-3: Legitimate (non-template) values in these fields are preserved and rendered normally
- AC-4: Filtered sections are logged at DEBUG level for diagnostic visibility

#### T2 Refine Prompt Token Efficiency (AR-412)

The T2 refine user prompt currently duplicates the entire T1 user prompt (~28K chars) as "Task Context" before appending `{draft_code}`. Since T2 receives the already-applied draft code (complete files, not search/replace blocks), the existing-file listing and output format instructions from T1 are redundant. This can double the T2 input token count unnecessarily.

**Required change:** Build a condensed T2 context that includes only information the refiner needs:
1. **Task description** — The chunk description and target files
2. **Design document** — The authoritative design specification (if present)
3. **Key constraints** — Project conventions, import rules, parameter sources
4. **Draft code** — The `{draft_code}` placeholder (injected at runtime)

**Excluded from T2 context** (already applied by T1):
- Raw existing file content (T2 sees the draft which incorporates these)
- SEARCH/REPLACE output format instructions (T2 emits complete files)
- Edit-First Directive and size regression thresholds (T2 output is always complete files)
- Redundant project identity / goals (condensed to a single-line summary)

**Acceptance criteria:**
- AC-1: T2 refine user prompt is at most 40% of the T1 user prompt size (measured in chars), excluding the `{draft_code}` placeholder
- AC-2: T2 refine user prompt includes: task description, design document (if present), key constraints, and `{draft_code}` placeholder
- AC-3: T2 refine user prompt does NOT include: raw existing file content, SEARCH/REPLACE format instructions, or Edit-First Directive
- AC-4: Walkthrough metadata.json includes `estimated_t2_context_chars` (T2 prompt size excluding `{draft_code}`)

### Budget Enforcement (AR-404)

Cost budget enforcement (AR-204/AR-404) operates at two layers depending on execution mode:

| Enforcement Point | Mode | Behavior |
|-------------------|------|----------|
| **Phase boundary** | Phase-serial, feature-serial | After each phase completes, check `cumulative_cost > cost_budget`. The phase that caused the breach completes; subsequent phases are not started. |
| **Wave barrier** | Wave-parallel | In addition to the phase-boundary check, budget is checked at each wave barrier within a phase. If cumulative cost (aggregated across concurrent lanes) exceeds the budget at a wave barrier, remaining waves within the phase are not started. The current wave's lanes complete before enforcement. |

In wave-parallel mode, concurrent lanes accumulate cost independently; the authoritative budget check occurs at the wave barrier where lane costs are merged into `cumulative_cost`.

---

## Layer 5: Handoff and Recovery (AR-5xx)

Supports split execution and checkpoint-based recovery.

### Two-Half Split

```mermaid
flowchart LR
    subgraph firstHalf [Design Half]
        P1[PLAN] --> S1[SCAFFOLD] --> D1[DESIGN]
    end
    D1 -->|"design-handoff.json"| I2
    subgraph secondHalf [Implementation Half]
        I2[IMPLEMENT] --> T2[TEST] --> R2[REVIEW] --> F2[FINALIZE]
    end
```

### Checkpoint Schema

The checkpoint schema has evolved across four versions. AR-505 defines the persistence contract; all versions must be supported for forward- and backward-compatible resume.

| Field | Type | Version | Description |
|-------|------|---------|-------------|
| `workflow_id` | `str` | v1+ | Unique workflow identifier |
| `last_completed_phase` | `str` | v1+ | Phase name of last completion |
| `phase_results` | `list` | v1+ | Per-phase result history |
| `cumulative_cost` | `float` | v1+ | Total USD spent |
| `schema_version` | `int` | v2+ | Currently 4 |
| `completed_features` | `list[str]` | v2+ | Feature-serial tracking |
| `current_feature` | `str` | v2+ | Active feature ID |
| `current_feature_phase` | `str` | v2+ | Active inner phase |
| `feature_partial_results` | `dict` | v2+ | Per-feature partial state |
| `lane_assignments` | `dict[str, int]` | v3+ | Task-to-lane mapping for lane-parallel mode |
| `completed_lanes` | `list[int]` | v3+ | Lane IDs that have completed |
| `lane_results` | `dict[int, dict]` | v3+ | Per-lane partial results |
| `wave_assignments` | `dict[str, int]` | v4+ | Task-to-wave mapping derived from `depends_on` DAG |
| `completed_waves` | `list[int]` | v4+ | Wave indices that have completed (all lanes finished) |
| `current_wave` | `Optional[int]` | v4+ | Index of the currently executing wave |
| `wave_resume_count` | `dict[int, int]` | v4+ | Per-wave resume attempt counter (wave index → attempt count). Required for AR-212 AC#8 retry limit enforcement across resume boundaries. |

> **Migration:** Checkpoints are migrated forward on load. A v2 checkpoint loaded by a v4-capable runtime gains default-empty lane and wave fields. A v3 checkpoint gains default-empty wave fields (`wave_assignments: {}`, `completed_waves: []`, `current_wave: None`, `wave_resume_count: {}`). AR-511 governs schema versioning and migration policy.

---

## Layer 6: Observability (AR-6xx)

OTel span hierarchy, events, and output manifests.

### Span Hierarchy

```
workflow.{workflow_id}                    # Root span (AR-600)
  ├── workflow.{id}.plan                  # Phase span (AR-601)
  ├── workflow.{id}.scaffold
  ├── workflow.{id}.design
  ├── workflow.{id}.implement
  ├── workflow.{id}.test
  ├── workflow.{id}.review
  └── workflow.{id}.finalize
```

### Output Files

| File | Written By | Contents | Requirement |
|------|-----------|----------|-------------|
| `generation-manifest.json` | FINALIZE | Artifacts with sha256, task status, cost | AR-604 |
| `workflow-execution-report.json` | FINALIZE | Full execution report | AR-162 |
| `.events.jsonl` | Orchestrator | Append-only event log | AR-605 (planned) |

---

## Layer 7: Configuration (AR-7xx)

All base configuration is fully implemented. AR-708 is planned for wave-parallel concurrency control.

### Configuration Priority Chain

```
CLI flags (--lead-agent, --cost-budget, ...)     # Highest priority
    ↓
Environment / Config file (ConfigManager)         # Middle priority
    ↓
Dataclass defaults (HandlerConfig, WorkflowConfig) # Lowest priority
```

### Key CLI Flags

| Flag | Maps To | Requirement |
|------|---------|-------------|
| `--seed PATH` | Runner arg | AR-100 |
| `--dry-run` | `WorkflowConfig.dry_run` | AR-205 |
| `--cost-budget FLOAT` | `WorkflowConfig.cost_budget` | AR-204 |
| `--timeout FLOAT` | `WorkflowConfig.total_timeout_seconds` | AR-203 |
| `--stop-after PHASE` | Phase subset | AR-207 |
| `--lead-agent SPEC` | `HandlerConfig.lead_agent` | AR-703 |
| `--drafter-agent SPEC` | `HandlerConfig.drafter_agent` | AR-703 |
| `--design-max-tokens INT` | `HandlerConfig.design_max_tokens` | AR-705 |
| `--no-auto-commit` | Disable auto-commit | AR-707 |
| `--force-implement` | Clear cached results | AR-706 |
| `--adopt-prior [PATH]` | Load prior designs | AR-507 |
| `--resume` | Load checkpoint | AR-506 |
| `--wave-parallel` | `WorkflowConfig.wave_parallel` | AR-212 |
| `--max-concurrent-lanes INT` | `WorkflowConfig.max_concurrent_lanes` | AR-708 |

### AR-708: Maximum Concurrent Lanes

**Status:** planned

Controls the maximum number of concurrent lanes within a wave during wave-parallel execution. Defaults to `os.cpu_count() + 4` when set to `None`, providing a safe default that prevents thread exhaustion while allowing reasonable concurrency. This flag is a critical operational control for managing API rate limits and resource utilization.

**Acceptance criteria:**

1. `WorkflowConfig.max_concurrent_lanes` accepts a positive integer or `None` (defaults to `os.cpu_count() + 4`).
2. When set, no more than `max_concurrent_lanes` tasks execute concurrently within a single wave.
3. The CLI flag `--max-concurrent-lanes` maps to `WorkflowConfig.max_concurrent_lanes`.

---

## Layer 8: Safety and Resilience (AR-8xx)

Defense-in-depth measures for the generation pipeline.

### Implemented Safety Gates

| Gate | Phase | What It Catches | Requirement |
|------|-------|----------------|-------------|
| Pre-flight | Before PLAN | Missing deps, bad config, zero cost | AR-800 |
| Domain checklist | DESIGN/IMPLEMENT | Domain-specific constraint violations | AR-801 |
| Truncation detection | IMPLEMENT | Incomplete LLM output | AR-802 |
| LOC mismatch | IMPLEMENT | Design implies more code than estimated | AR-803 |
| Multi-file completeness | After IMPLEMENT | Missing files in multi-file tasks | AR-804 |
| Semantic validators | TEST | Placeholder, import, proto, protocol, Dockerfile defects | AR-143..AR-147 |
| Service metadata preflight | Before PLAN | Missing service metadata for service-related tasks | AR-810 |

### Planned Safety Features

| Feature | What It Prevents | Requirement |
|---------|-----------------|-------------|
| Interactive mode | Blind acceptance of LLM output | AR-805 |
| Escalation pause | Unresolved design disagreements proceeding to implementation | AR-806 |
| Git tag restore points | Inability to rollback after bad generation | AR-807 |
| Advisory file lock | Concurrent workflow corruption | AR-808 |
| Stalled retry detection | Wasting tokens on non-converging drafts | AR-809 |
| Task ID validation | Path traversal, shell injection, null byte, and format string attacks via malicious task IDs | AR-811 |
| Global context immutability | Concurrent lane threads mutating read-only global context fields, causing data races and non-deterministic behavior | AR-812 |

### AR-811: Task ID Input Validation

**Status:** planned

Task IDs flow into checkpoints, file paths, git commit messages, and log messages from LLM output. This cross-cutting safety concern requires formal input validation at ingestion boundaries.

**Acceptance criteria:**

1. Task IDs are validated at seed ingestion (`SeedTask.from_seed_entry()`) and wave computation (`compute_waves()`).
2. Validation rejects identifiers containing path separators (`/`, `\`), shell metacharacters (`;`, `|`, `&`, `` ` ``, `$`), null bytes (`\x00`), or format string patterns (`{`, `}`).
3. A `ValueError` is raised with a descriptive message identifying the invalid character and task ID.

### AR-812: Global Context Immutability During Concurrent Execution

**Status:** planned

During wave-parallel execution, multiple lane threads read shared global context fields (e.g., `tasks`, `plan_goals`, `scaffold`). Mutation of these fields by any lane would cause data races and non-deterministic behavior.

**Acceptance criteria:**

1. Global context fields established before wave execution begins are protected from mutation by concurrent lane threads.
2. Each lane receives an isolated mutable context scope for lane-local writes; lane-local writes do not affect other lanes or the global context until the wave barrier merge.
3. Attempted mutation of a read-only global context field from a lane thread raises an error or is silently prevented (implementation may choose between enforcement strategies).

### Pipeline Safety Gates (AR-813–825)

These 13 requirements address three systemic gaps exposed by the PI-012/PI-013 artisan run failure ($0.74, 6m22s). See [Pipeline Safety Gate Requirements](PIPELINE_SAFETY_GATE_REQUIREMENTS.md) for the full root cause analysis, principle mapping, and cap-dev-pipe phase placement.

| Sub-Layer | ID Range | Count | Principle | Cap-Dev-Pipe Phase |
|-----------|----------|-------|-----------|-------------------|
| FINALIZE Resilience | AR-813–815 | 3 | by Construction + Mottainai | FINALIZE |
| Truncation Enforcement | AR-816–820 | 5 | by Construction + Mottainai | IMPLEMENT (Gate 4) → INTEGRATE |
| Module Resolution Fidelity | AR-821–825 | 5 | by Design + by Construction + Mottainai | SCAFFOLD → IMPLEMENT → INTEGRATE |

#### AR-813: Per-Task Error Guard in FINALIZE

**Status:** planned (P0)
**Source:** `context_seed_handlers.py` (FinalizePhaseHandler._build_finalize_summary)
**Cross-ref:** AR-165, OT-507, Mottainai Gap 30

`_build_finalize_summary()` wraps per-task processing in try/except; a single task's Gate 3b error does not crash the manifest for all tasks.

#### AR-814: Static Method Audit

**Status:** planned (P0)
**Source:** `context_seed_handlers.py` (all phase handler classes)

All non-`self`-using methods in phase handlers are decorated `@staticmethod`. CI lint or mypy strict catches missing decorators.

#### AR-815: Partial Manifest on FINALIZE Failure

**Status:** planned (P3)
**Source:** `context_seed_handlers.py` (FinalizePhaseHandler)
**Cross-ref:** AR-161, AR-906, Mottainai Gap 37

If FINALIZE crashes after processing N of M tasks, write a partial `generation-manifest.json` with `incomplete: true` flag and error details.

#### AR-816: Gate 4 Truncation Escalation

**Status:** planned (P1)
**Source:** `context_seed_handlers.py` (ImplementPhaseHandler), `integration_engine.py`
**Cross-ref:** AR-175, AR-908, Mottainai Gap 32

When Gate 4 detects truncation with confidence >= 0.5, set `truncation_blocked: true` on the generation result. INTEGRATE skips the file.

#### AR-817: Contract YAML Truncation Severity Upgrade

**Status:** planned (P1)
**Source:** `artisan-pipeline.contract.yaml` (IMPLEMENT exit)
**Cross-ref:** AR-175

`artisan-pipeline.contract.yaml` IMPLEMENT exit: truncation severity escalated to `blocking` for tasks with `truncation_blocked: true`.

#### AR-818: Size Regression Hard Block

**Status:** planned (P1)
**Source:** `integration_engine.py`
**Cross-ref:** AR-175, REQ-EFE-020, REQ-CCD-501, Mottainai Gap 38

Generated file < 70% of existing file size AND truncation confidence >= 0.5 → INTEGRATE rejects the file (preserves existing).

#### AR-819: Truncation + Existing File Compound Gate

**Status:** planned (P1)
**Source:** `integration_engine.py`
**Cross-ref:** AR-175, REQ-EFE-020

When both truncation is detected (any confidence) and target file exists, INTEGRATE applies the stricter threshold (0.5 instead of 0.7).

#### AR-820: Truncation Rejection OTel Event

**Status:** planned (P3)
**Source:** `integration_engine.py`
**Cross-ref:** OT-300

INTEGRATE emits span event on truncation-based file rejection: `truncation.confidence`, `truncation.action`, `file.size_ratio`, `file.existing_size`, `file.generated_size`.

#### AR-821: SCAFFOLD Module Inventory

**Status:** planned (P2)
**Source:** `context_seed_handlers.py` (ScaffoldPhaseHandler)
**Cross-ref:** AR-903, Mottainai Gap 39

SCAFFOLD collects importable Python module names from `project_root/src/` (`__init__.py` presence). Stored as `scaffold.module_inventory: list[str]`.

#### AR-822: Module Inventory Injection in IMPLEMENT Prompts

**Status:** planned (P2)
**Source:** `context_seed_handlers.py` (ImplementPhaseHandler), `artisan_phases/development.py`
**Cross-ref:** AR-130, REQ-CCD-302, Mottainai Gap 10

When `scaffold.module_inventory` is available, inject it into the code generation prompt with instruction to import only from listed modules.

#### AR-823: Import Validation at INTEGRATE

**Status:** planned (P2)
**Source:** `integration_engine.py`
**Cross-ref:** AR-175

Before merging a `.py` file, parse imports via `ast.parse` and validate first-party imports against `scaffold.module_inventory`. Reject files with unresolvable first-party imports.

#### AR-824: Contract YAML Module Inventory Propagation

**Status:** planned (P2)
**Source:** `artisan-pipeline.contract.yaml` (IMPLEMENT entry enrichment)
**Cross-ref:** REQ-CCD-600

`scaffold.module_inventory` added to IMPLEMENT phase enrichment with `severity: warning`, `source_phase: scaffold`.

#### AR-825: Module Resolution OTel Span Attribute

**Status:** planned (P3)
**Source:** `integration_engine.py`
**Cross-ref:** OT-300

Per-task INTEGRATE span includes `task.import_validation.unresolved_count` (int) and `task.import_validation.unresolved_modules` (string).

---

## Layer 9: Mottainai Compliance (AR-9xx)

Cross-cutting requirements ensuring artifacts produced by earlier phases are forwarded, registered, and validated — not silently discarded. Consolidates 20 intra-pipeline waste gaps (Gaps 17–36) from the [Mottainai Design Principle](../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) into 9 formal requirements.

### Three Anti-Patterns

1. **Serialize-and-Forget** — A phase produces rich structured data, then serializes only a subset. Downstream phases see a degraded view. (AR-900, AR-901)
2. **Compute-But-Don't-Forward** — Data is computed and stored in one phase's context, but the downstream phase that would benefit never reads it. (AR-902, AR-903)
3. **Inject-But-Don't-Validate** — Deterministic data is injected into LLM prompts with no post-generation check that the LLM honored it. (AR-904, AR-905, AR-906, AR-907, AR-908)

### Dependency Diagram

```mermaid
flowchart TD
    AR900[AR-900 DESIGN Serialize Full Metadata] --> AR901[AR-901 Parameter Fidelity]
    AR900 --> AR904[AR-904 TEST Deterministic Validation]
    AR900 --> AR907[AR-907 Guidance Compliance]
    AR903[AR-903 Metadata Forwarding] --> AR907
    AR902[AR-902 Reuse downstream_map]
    AR905[AR-905 Provenance Audit Trail]
    AR906[AR-906 FINALIZE Diagnostics]
    AR908[AR-908 Integrity at Output Time]
    AR900 --> AR212[AR-212 Wave-Parallel]
    AR902 --> AR212
```

AR-900 is the foundation — 3 other requirements depend on it directly, plus AR-212 (wave-parallel) depends on both AR-900 and AR-902 for wave context merging and `_downstream_map` population.

### AR-900: DESIGN Serialize Full Metadata

**Status:** planned
**Priority:** P0

DESIGN phase serializes full review metadata so that downstream phases (IMPLEMENT, TEST, FINALIZE) and wave-parallel context merging operate on complete data.

**Acceptance criteria:**

1. The `design_results` context entry for each task includes a `reviewer_verdict` dict containing: `verdict` (enum: agreed/disagreed/escalated), `reviewer_model`, `review_timestamp`, and `iteration_count`.
2. All parsed `DesignSection` objects (e.g., interface contracts, data models, error handling strategy) are persisted in `design_results` under a `parsed_sections` key, retaining their structured form (not flattened to prose).
3. Plan-level constraints that were injected into the DESIGN prompt (e.g., `architectural_context`, `design_calibration`) are stored in `design_results` under a `plan_constraints_applied` key, enabling downstream validation that the design honored them.
4. Serialization round-trips without data loss: `deserialize(serialize(design_results)) == design_results` for all persisted fields.

### Gap-to-Requirement Mapping

| Requirement | Gaps Addressed | Anti-Pattern | Summary |
|-------------|---------------|--------------|---------|
| AR-900 | 17, 19, 20 | Serialize-and-forget | DESIGN serializes full review metadata (reviewer verdicts with model/timestamp/iteration, parsed DesignSection objects, plan constraints applied) |
| AR-901 | 18 | Serialize-and-forget | DESIGN extracts and validates critical parameters |
| AR-902 | 26 | Compute-but-don't-forward | IMPLEMENT reuses pre-computed downstream file map from Gate 2c context (`context['_downstream_map']`). If the map is absent, IMPLEMENT re-computes it with a logged warning. |
| AR-903 | 21, 22, 23, 24, 25 | Compute-but-don't-forward | Earlier-phase metadata forwarded to IMPLEMENT |
| AR-904 | 27, 28 | Inject-but-don't-validate | TEST deterministic pre-review validation |
| AR-905 | 29, 33 | Inject-but-don't-validate | Metadata provenance audit trail |
| AR-906 | 30, 31 | Inject-but-don't-validate | FINALIZE preserves structured diagnostics |
| AR-907 | 34, 35 | Inject-but-don't-validate | Post-generation guidance compliance validation |
| AR-908 | 32, 36 | Inject-but-don't-validate | File integrity computed at IMPLEMENT output time |

### Priority Ordering

| Priority | Requirements | Rationale |
|----------|-------------|-----------|
| P0 | AR-900, AR-902 | Foundation (AR-900 unblocks 3 others); AR-902 is minimal code change. AR-902 is also a prerequisite for wave-parallel mode's `_downstream_map` merge field (AR-212). |
| P1 | AR-901, AR-904, AR-906 | Wire existing functions/data to downstream consumers |
| P2 | AR-903, AR-905 | Cross-phase forwarding and audit trail |
| P3 | AR-907, AR-908 | Measurement and manifest completeness |

---

## Layer 10: Project-Centric Context (AR-10xx)

Ensures project-level context (architecture, service metadata, plan goals, onboarding fields) survives the multi-phase boundary and reaches LLM prompts in IMPLEMENT and REVIEW phases. Closes the gap between data injection in PLAN and prompt consumption in downstream phases — the "last mile" complement to AR-3xx (ContextCore Data Flow).

**Design Principle:** The Artisan pipeline should assume a project-centric default. The Prime Contractor injects `architectural_context`, `service_metadata`, `plan_document_text`, and `project_objectives` into every feature's `gen_context` (lines 585–662 of `prime_contractor.py`). The Artisan pipeline distributes the same data across multi-phase boundaries where it **attenuates** — onboarding fields are lost on checkpoint resume, `service_metadata` never reaches IMPLEMENT or REVIEW prompts, and project-level framing is absent from code generation and review prompts.

**Provenance:** Consolidated from `PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md` (PCA-1xx..PCA-4xx). ID mapping: PCA-1xx → AR-10{0x}, PCA-2xx → AR-101x, PCA-3xx → AR-102x, PCA-4xx → AR-103x.

### Gap Summary

| Gap | Description | Impact |
|-----|-------------|--------|
| Gap 1 | `project_root` not injected into `initial_context` | All downstream phases resolve paths against `"."` instead of actual project root |
| Gap 2 | 8 onboarding fields not in `_CHECKPOINT_CONTEXT_KEYS` | All onboarding context lost on checkpoint resume |
| Gap 3 | IMPLEMENT prompt lacks `project_objectives`, `architectural_context`, `plan_context`, `service_metadata` | Code is technically correct but architecturally misaligned |
| Gap 4 | REVIEW prompt has no project-level framing | Reviewer cannot check project-level constraints |
| Gap 5 | `service_metadata` not consumed after DESIGN phase | Generated code may violate transport protocol or add unused capabilities |
| Gap 6 | No cross-feature context accumulation in IMPLEMENT | Later features repeat mistakes or violate conventions from earlier features |

### Context Injection (AR-1000..AR-1005)

#### AR-1000: Inject `project_root` into `initial_context`

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 1
- **Overlaps:** AR-100

`run_artisan_workflow.py` sets `WorkflowConfig.project_root` (line 701) but does NOT inject it into `initial_context` (line 793). Downstream phases fall back to `Path(".")`.

**Acceptance Criteria:**

1. `initial_context["project_root"]` is set to `str(Path(args.project_root).resolve())` in `run_artisan_workflow.py`.
2. `PlanPhaseHandler.execute()` does NOT overwrite `project_root` if already present in context.
3. All downstream phases use `context["project_root"]` rather than `context.get("project_root", ".")`.
4. The `artisan-pipeline.contract.yaml` plan.entry.required `project_root` passes validation.

**Source files:** `scripts/run_artisan_workflow.py`, `src/startd8/contractors/context_seed_handlers.py`

#### AR-1001: Forward `service_metadata` from Seed to Context

- **Priority:** P0
- **Status:** implemented (PLAN phase, line 872)
- **Closes:** Gap 5 (partially — consumption is AR-1030/AR-1023)
- **Overlaps:** AR-144, AR-147

**Acceptance Criteria:**

1. `context["service_metadata"]` is populated by `PlanPhaseHandler.execute()`. (Already true.)
2. Value is `None` when the onboarding section does not contain `service_metadata`.

#### AR-1002: Forward `plan_document_text` from Seed to Context

- **Priority:** P0
- **Status:** implemented (PLAN phase, lines 890–906)
- **Closes:** Gap 5 (partially)
- **Overlaps:** AR-903

**Acceptance Criteria:**

1. `context["plan_document_text"]` is populated when `artifacts.plan_document_path` resolves to a readable file. (Already true.)
2. On resume, `_ensure_context_loaded()` re-extracts this field (see AR-1011).

#### AR-1003: Forward All Onboarding Fields from Seed to Context

- **Priority:** P1
- **Status:** implemented (PLAN phase, lines 855–885); persistence is AR-1010/1011
- **Closes:** Gap 2 (partially)
- **Overlaps:** AR-303..AR-308

**Acceptance Criteria:**

1. All six onboarding fields are present in context after `PlanPhaseHandler.execute()`. (Already true.)
2. All six fields survive checkpoint resume (see AR-1010, AR-1011).
3. At least `onboarding_calibration_hints` and `onboarding_dependency_graph` are consumed by IMPLEMENT (see AR-1031).

#### AR-1004: Log Context Injection Completeness at Phase Entry

- **Priority:** P1
- **Status:** planned

**Acceptance Criteria:**

1. At the start of `execute()` in DESIGN, IMPLEMENT, INTEGRATE, TEST, REVIEW, and FINALIZE handlers, log an INFO message listing presence of 10 project-level context fields.
2. If fewer than 3 of 10 fields are present, log a WARNING: `"Degraded project context: only N/10 fields available — code quality may be reduced."`.
3. For INTEGRATE, the logging is advisory — the phase has no LLM prompts.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (all handlers)

#### AR-1005: `WorkflowConfig.project_root` Propagation to Context

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 1 (defense-in-depth)

**Acceptance Criteria:**

1. `ArtisanContractorWorkflow.execute()` calls `context.setdefault("project_root", self.config.project_root)` before invoking the first phase handler (when not None).
2. Existing `context["project_root"]` values are NOT overwritten.

**Source files:** `src/startd8/contractors/artisan_contractor.py`

### Checkpoint Persistence (AR-1010..AR-1013)

#### AR-1010: Expand `_CHECKPOINT_CONTEXT_KEYS` with Onboarding and Service Fields

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 2
- **Overlaps:** AR-505, AR-903

**Acceptance Criteria:**

1. `_CHECKPOINT_CONTEXT_KEYS` includes 8 additional keys: `onboarding_derivation_rules`, `onboarding_resolved_parameters`, `onboarding_output_contracts`, `onboarding_calibration_hints`, `onboarding_open_questions`, `onboarding_dependency_graph`, `service_metadata`, `plan_document_text`.
2. Existing checkpoint files (without these keys) load without error (backward compatibility).
3. Round-trip test: `context -> checkpoint -> restore -> context` preserves all eight fields.
4. `plan_document_text` is truncated to 100K characters in checkpoint to prevent oversized files.

**Source files:** `src/startd8/contractors/artisan_contractor.py` (line 138)

#### AR-1011: Extend `_ensure_context_loaded()` to Re-Extract Onboarding Fields

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 2 (defense-in-depth)
- **Overlaps:** AR-903

**Acceptance Criteria:**

1. `_ensure_context_loaded()` adds `context.setdefault()` calls for all eight fields, extracting from the same seed paths as `PlanPhaseHandler`.
2. Re-extraction logged at INFO: `"Restored N/8 onboarding fields from seed on resume."`.
3. Fields already present from checkpoint are NOT overwritten.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (line 559)

#### AR-1012: Checkpoint Size Guard for `plan_document_text`

- **Priority:** P1
- **Status:** planned

**Acceptance Criteria:**

1. `plan_document_text` is stored as truncated summary (first 1000 chars + `"... [truncated, full text in seed]"`) in checkpoint.
2. On restore, full text is re-loaded from seed via AR-1011.
3. A sentinel value (`_plan_doc_truncated: true`) distinguishes truncated from absent.

**Source files:** `src/startd8/contractors/artisan_contractor.py`

#### AR-1013: Checkpoint Schema Version Compatibility

- **Priority:** P0
- **Status:** planned
- **Overlaps:** AR-511

**Acceptance Criteria:**

1. `CHECKPOINT_SCHEMA_VERSION` remains at 4 (new keys are optional, handled via `setdefault`).
2. Migration test: a v4 checkpoint WITHOUT the new keys loads successfully, and `_ensure_context_loaded()` fills the missing fields from the seed.

**Source files:** `src/startd8/contractors/artisan_contractor.py`

### Prompt Enrichment (AR-1020..AR-1024)

#### AR-1020: IMPLEMENT Phase Project Architecture Injection

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 3 (partially)
- **Overlaps:** AR-131, AR-903

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `architectural_context` (filtered to objectives, constraints, shared_modules relevant to the task's target files), `plan_goals` (first 5), and `plan_context` (truncated to 4000 chars) into `DevelopmentChunk.metadata`.
2. `_build_prompt()` adds a `## Project Architecture` section after `## Domain Constraints` when present.
3. Combined injection capped at 6000 characters.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`), `src/startd8/contractors/artisan_phases/development.py` (`_build_prompt`)

#### AR-1021: IMPLEMENT Phase Service Metadata Injection

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 5
- **Overlaps:** AR-144, AR-147

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `service_metadata` into `DevelopmentChunk.metadata`.
2. `_build_prompt()` adds a `## Service Metadata` section with `transport_protocol`, `runtime_dependencies`, and the directive: *"HEALTHCHECK type MUST match transport_protocol. Do NOT add capabilities the service does not use."*
3. No section added when `service_metadata` is None or empty.

**Source files:** `src/startd8/contractors/context_seed_handlers.py`, `src/startd8/contractors/artisan_phases/development.py`

#### AR-1022: REVIEW Phase Project-Level System Prompt

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 4
- **Overlaps:** AR-150

**Acceptance Criteria:**

1. `_build_review_prompt()` gains a `## Project Context` section with `plan_title`, `plan_goals` (max 5), `architectural_context.objectives` (max 3), and `architectural_context.constraints` (max 5).
2. `ReviewPhaseHandler.execute()` passes project context from the workflow context dict.
3. Prompt budget: `## Project Context` capped at 2000 characters.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ReviewPhaseHandler`)

#### AR-1023: REVIEW Phase Service Metadata Compliance Check

- **Priority:** P1
- **Status:** planned
- **Closes:** Gap 5 (REVIEW)
- **Overlaps:** AR-144, AR-907

**Acceptance Criteria:**

1. When `service_metadata` is present, `_build_review_prompt()` appends a `## Service Metadata Compliance` section instructing the reviewer to check transport protocol and runtime dependency compliance.
2. When `service_metadata` is None, no additional section is added.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ReviewPhaseHandler._build_review_prompt`)

#### AR-1024: TEST Phase Service Metadata Forwarding

- **Priority:** P1
- **Status:** implemented (validators already consume `service_metadata` from context)
- **Closes:** Gap 5 (TEST)
- **Overlaps:** AR-144, AR-147

**Acceptance Criteria:**

1. `context.get("service_metadata")` is available in TEST/FINALIZE phase handlers (depends on AR-1010/1011 for resume).
2. When absent, validators gracefully skip transport/dependency checks (already true).

### Cross-Phase Propagation (AR-1030..AR-1034)

#### AR-1030: Service Metadata Propagation to IMPLEMENT Chunks

- **Priority:** P0
- **Status:** planned
- **Closes:** Gap 5 (IMPLEMENT)
- **Overlaps:** AR-903

**Acceptance Criteria:**

1. Each `DevelopmentChunk` includes `metadata["service_metadata"]` from `context.get("service_metadata")`.
2. Full `service_metadata` dict (not a subset), consistent with Prime Contractor.
3. When None, the metadata key is omitted.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`)

#### AR-1031: Plan Document and Calibration Hints Propagation to IMPLEMENT

- **Priority:** P1
- **Status:** planned
- **Closes:** Gap 5, Gap 6 (partial)
- **Overlaps:** AR-903

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `metadata["plan_context"]` (truncated to 4000 chars) and per-task `metadata["calibration_hints"]` when task artifact types match calibration hint keys.
2. `_build_prompt()` formats `plan_context` as a `## Plan Context` section.

**Source files:** `src/startd8/contractors/context_seed_handlers.py`, `src/startd8/contractors/artisan_phases/development.py`

#### AR-1032: Onboarding Field Consumption Audit Trail

- **Priority:** P1
- **Status:** planned
- **Overlaps:** AR-905

**Acceptance Criteria:**

1. Each phase handler that reads an onboarding field increments `context["_onboarding_consumption"][field_name]` with the phase name.
2. `FinalizePhaseHandler` includes the map in the execution report under `provenance.onboarding_fields_consumed`.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (all handlers), `FinalizePhaseHandler`

#### AR-1033: Cross-Feature Context Accumulation for IMPLEMENT

- **Priority:** P1
- **Status:** planned
- **Closes:** Gap 6
- **Overlaps:** AR-124

**Acceptance Criteria:**

1. After each feature's code is generated, a brief summary (feature name, key files, conventions used) is appended to `context["_prior_impl_summaries"]`.
2. `_tasks_to_chunks()` injects last 3 summaries into `metadata["prior_implementations"]`.
3. `_build_prompt()` formats them as a `## Prior Implementations` section.
4. Accumulation works in both phase-serial and feature-serial modes.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ImplementPhaseHandler`), `src/startd8/contractors/artisan_phases/development.py`

#### AR-1034: Requirements Text Propagation to IMPLEMENT

- **Priority:** P1
- **Status:** planned
- **Overlaps:** AR-903

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `metadata["requirements_text"]` from `task.requirements_text` when non-empty.
2. `_build_prompt()` formats as a `## Requirements` section placed immediately after the implementation prompt.
3. Truncated to 3000 characters.

**Source files:** `src/startd8/contractors/context_seed_handlers.py`, `src/startd8/contractors/artisan_phases/development.py`

### Implementation Sequencing

```
Phase 1 (P0 — Context Survival):
  AR-1000 + AR-1005    (project_root injection)
  AR-1010 + AR-1013    (checkpoint keys expansion + compat test)
  AR-1011              (_ensure_context_loaded expansion)
  ──────────────────────────────────────────────────────────
  At this point: all project context survives resume

Phase 2 (P0 — Prompt Enrichment):
  AR-1020 + AR-1021    (IMPLEMENT prompt: architecture + service metadata)
  AR-1030              (service_metadata data propagation)
  AR-1022              (REVIEW prompt: project context)
  ──────────────────────────────────────────────────────────
  At this point: IMPLEMENT and REVIEW prompts match Prime quality

Phase 3 (P1 — Completeness):
  AR-1023              (REVIEW service metadata compliance)
  AR-1031              (plan context + calibration in IMPLEMENT)
  AR-1033              (cross-feature accumulation)
  AR-1034              (requirements text in IMPLEMENT)
  AR-1004              (context completeness logging)
  AR-1032              (onboarding consumption audit)
  ──────────────────────────────────────────────────────────
  At this point: full parity with Prime Contractor
```

---

## Traceability Matrix

### Requirement to Source File

| Requirement | Primary Source File | Secondary Files |
|-------------|-------------------|-----------------|
| AR-100..AR-102 | `src/startd8/contractors/context_seed_handlers.py` (PlanPhaseHandler) | |
| AR-110..AR-111 | `src/startd8/contractors/context_seed_handlers.py` (ScaffoldPhaseHandler) | |
| AR-120..AR-129 | `src/startd8/contractors/context_seed_handlers.py` (DesignPhaseHandler) | `artisan_phases/design_documentation.py` |
| AR-127 | `src/startd8/contractors/context_seed_handlers.py` (DesignPhaseHandler) | Reuses `scaffold.existing_target_files` from ScaffoldPhaseHandler |
| AR-128 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | `handoff.py`, `artisan_phases/development.py` |
| AR-130..AR-139 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | `artisan_phases/development.py` |
| AR-170..AR-176 | `src/startd8/contractors/context_seed_handlers.py` (IntegratePhaseHandler) | `integration_engine.py` |
| AR-140..AR-142 | `src/startd8/contractors/context_seed_handlers.py` (TestPhaseHandler) | |
| AR-143..AR-147 | `src/startd8/contractors/artisan_phases/self_consistency.py` | `context_seed_handlers.py` (Gate 3b), `rules_validators.py` |
| AR-150..AR-153 | `src/startd8/contractors/context_seed_handlers.py` (ReviewPhaseHandler) | |
| AR-160..AR-166 | `src/startd8/contractors/context_seed_handlers.py` (FinalizePhaseHandler) | |
| AR-200..AR-211 | `src/startd8/contractors/artisan_contractor.py` | `scripts/run_artisan_workflow.py` |
| AR-212 | `src/startd8/contractors/artisan_contractor.py` | `scripts/run_artisan_workflow.py`, `handoff.py` |
| AR-300..AR-311 | `src/startd8/contractors/context_seed_handlers.py` | `workflows/builtin/plan_ingestion_workflow.py` |
| AR-400..AR-407 | `src/startd8/contractors/protocols.py` | `artisan_contractor.py`, `context_seed_handlers.py` |
| AR-408 | `src/startd8/contractors/artisan_phases/development.py` | `context_seed_handlers.py`, `run_artisan_workflow.py` |
| AR-409 | `src/startd8/contractors/artisan_phases/development.py`, `design_documentation.py` | `context_seed_handlers.py`, `run_artisan_workflow.py` |
| AR-500..AR-511 | `src/startd8/contractors/handoff.py` | `artisan_contractor.py` |
| AR-600..AR-607 | `src/startd8/contractors/artisan_contractor.py` | `context_seed_handlers.py` |
| AR-700..AR-708 | `src/startd8/contractors/context_seed_handlers.py` | `scripts/run_artisan_workflow.py` |
| AR-800..AR-810 | `src/startd8/contractors/artisan_phases/preflight.py` | `context_seed_handlers.py`, `artisan_contractor.py`, `rules_common.py` |
| AR-811 | `src/startd8/contractors/context_seed_handlers.py` | `artisan_contractor.py` (wave computation) |
| AR-812 | `src/startd8/contractors/artisan_contractor.py` | `context_seed_handlers.py` |
| AR-813 | `src/startd8/contractors/context_seed_handlers.py` (FinalizePhaseHandler) | |
| AR-814 | `src/startd8/contractors/context_seed_handlers.py` (all phase handlers) | CI lint/mypy configuration |
| AR-815 | `src/startd8/contractors/context_seed_handlers.py` (FinalizePhaseHandler) | |
| AR-816 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | `integration_engine.py` |
| AR-817 | `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` | `gate_contracts.py` |
| AR-818 | `src/startd8/contractors/integration_engine.py` | |
| AR-819 | `src/startd8/contractors/integration_engine.py` | |
| AR-820 | `src/startd8/contractors/integration_engine.py` | |
| AR-821 | `src/startd8/contractors/context_seed_handlers.py` (ScaffoldPhaseHandler) | |
| AR-822 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | `artisan_phases/development.py` |
| AR-823 | `src/startd8/contractors/integration_engine.py` | |
| AR-824 | `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` | `gate_contracts.py` |
| AR-825 | `src/startd8/contractors/integration_engine.py` | |
| AR-900 | `src/startd8/contractors/context_seed_handlers.py` (DesignPhaseHandler) | |
| AR-901 | `src/startd8/contractors/artisan_phases/design_documentation.py` | `context_seed_handlers.py` |
| AR-902 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | |
| AR-903 | `src/startd8/contractors/context_seed_handlers.py` | ScaffoldPhaseHandler, ImplementPhaseHandler |
| AR-904 | `src/startd8/contractors/context_seed_handlers.py` (TestPhaseHandler) | |
| AR-905 | `src/startd8/contractors/context_seed_handlers.py` | TestPhaseHandler, DesignPhaseHandler |
| AR-906 | `src/startd8/contractors/context_seed_handlers.py` (FinalizePhaseHandler) | |
| AR-907 | `src/startd8/contractors/context_seed_handlers.py` | DesignPhaseHandler, ImplementPhaseHandler, TestPhaseHandler |
| AR-908 | `src/startd8/contractors/context_seed_handlers.py` | ImplementPhaseHandler, FinalizePhaseHandler |
| AR-1000, AR-1005 | `scripts/run_artisan_workflow.py`, `src/startd8/contractors/artisan_contractor.py` | `context_seed_handlers.py` |
| AR-1001..AR-1003 | `src/startd8/contractors/context_seed_handlers.py` (PlanPhaseHandler) | |
| AR-1004 | `src/startd8/contractors/context_seed_handlers.py` (all handlers) | |
| AR-1010, AR-1012, AR-1013 | `src/startd8/contractors/artisan_contractor.py` | |
| AR-1011 | `src/startd8/contractors/context_seed_handlers.py` (`_ensure_context_loaded`) | |
| AR-1020, AR-1021, AR-1030, AR-1031, AR-1034 | `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`) | `artisan_phases/development.py` (`_build_prompt`) |
| AR-1022, AR-1023 | `src/startd8/contractors/context_seed_handlers.py` (ReviewPhaseHandler) | |
| AR-1024 | `src/startd8/contractors/context_seed_handlers.py` (TestPhaseHandler) | `artisan_phases/self_consistency.py` |
| AR-1032 | `src/startd8/contractors/context_seed_handlers.py` (all handlers) | FinalizePhaseHandler |
| AR-1033 | `src/startd8/contractors/context_seed_handlers.py` (ImplementPhaseHandler) | `artisan_phases/development.py` |

### Requirement to Test File

| Requirement | Test File(s) |
|-------------|-------------|
| AR-100..AR-102 | `tests/unit/contractors/test_artisan_plan_deconstruction.py` |
| AR-110 | `tests/unit/contractors/test_7phase_integration.py` |
| AR-120..AR-124, AR-129 | `tests/unit/contractors/test_design_phase_handler.py`, `test_design_quality_context.py`, `test_artisan_design_documentation.py` |
| AR-130..AR-136, AR-138, AR-139 | `tests/unit/contractors/test_implement_phase_integration.py`, `test_implement_auto_commit.py` |
| AR-170..AR-176 | `tests/unit/contractors/test_integrate_phase.py`, `tests/contract_validation/test_quality_gates.py` |
| AR-140..AR-142 | `tests/unit/contractors/test_context_seed_review_finalize.py`, `test_artisan_test_construction.py` |
| AR-143..AR-147 | `tests/unit/contractors/test_self_consistency_validators.py`, `test_gate3b_content_validation.py` |
| AR-150..AR-153 | `tests/unit/contractors/test_review_phase_handler.py`, `test_context_seed_review_finalize.py` |
| AR-160..AR-163, AR-166 | `tests/unit/contractors/test_context_seed_review_finalize.py` |
| AR-200..AR-208 | `tests/unit/contractors/test_7phase_integration.py`, `tests/e2e/contractors/test_artisan_e2e.py` |
| AR-202..AR-203 | `tests/e2e/contractors/test_artisan_timeout.py` |
| AR-205 | `tests/e2e/contractors/test_artisan_dry_run.py` |
| AR-206 | `tests/unit/contractors/test_feature_serial_checkpoint.py` |
| AR-310..AR-311 | `tests/unit/test_plan_ingestion_workflow.py` |
| AR-400..AR-401 | `tests/unit/contractors/test_artisan_models.py`, `tests/unit/test_artisan_config.py` |
| AR-408 | `tests/unit/contractors/test_tier2_refinement.py` |
| AR-409 | `tests/unit/contractors/test_walkthrough_mode.py` |
| AR-402..AR-404 | `tests/e2e/contractors/test_artisan_resume.py`, `test_artisan_e2e.py` |
| AR-500..AR-504 | `tests/unit/contractors/test_handoff.py` |
| AR-505..AR-506 | `tests/e2e/contractors/test_artisan_resume.py` |
| AR-700..AR-703 | `tests/unit/test_artisan_config.py` |
| AR-800 | `tests/unit/contractors/test_artisan_preflight.py`, `tests/e2e/contractors/test_artisan_preflight_failure.py` |
| AR-806 | `tests/e2e/contractors/test_artisan_escalation.py` |
| AR-810 | `tests/unit/test_service_metadata_preflight.py` |
| AR-1000, AR-1005 | `tests/unit/contractors/test_artisan_context_injection.py` (new) |
| AR-1010, AR-1012, AR-1013 | `tests/unit/contractors/test_checkpoint_context_keys.py` (new) |
| AR-1011 | `tests/unit/contractors/test_ensure_context_loaded.py` (extend existing) |
| AR-1020, AR-1021 | `tests/unit/contractors/test_implement_prompt_enrichment.py` (new) |
| AR-1022, AR-1023 | `tests/unit/contractors/test_review_phase_handler.py` (extend existing) |
| AR-1024 | `tests/unit/contractors/test_review_phase_handler.py` (extend existing) |
| AR-1030, AR-1031, AR-1034 | `tests/unit/contractors/test_tasks_to_chunks.py` (new or extend) |
| AR-1032 | `tests/unit/contractors/test_onboarding_audit_trail.py` (new) |
| AR-1033 | `tests/unit/contractors/test_cross_feature_accumulation.py` (new) |

### Test Coverage Gaps

Requirements with no `verified_by` test file (need new tests):

| Requirement | Status | What Needs Testing |
|-------------|--------|-------------------|
| AR-127, AR-128 | planned | Existing file detection, design_mode propagation, update-mode prompt constraints, post-generation line-reduction validation |
| AR-111 | planned | SCAFFOLD output_conventions validation |
| AR-125, AR-126 | planned | DESIGN parameter_sources / semantic_conventions injection |
| AR-137 | planned | IMPLEMENT parameter_sources in chunk metadata |
| AR-129, AR-138, AR-139, AR-153, AR-166 | planned | Prime-convergent quality behaviors: DESIGN iterative threshold gate, parameter completeness gate, IMPLEMENT preflight/reuse, bounded failure feedback retries, forensic artifact persistence |
| AR-164, AR-165 | planned | FINALIZE provenance block and Gate 3 compatibility |
| AR-212 | planned | Wave-parallel execution: mutual exclusion validation, wave computation from depends_on, dependency ordering invariant, barrier semantics, degeneration to lane-parallel, wave checkpoint persistence and resume, state-to-code integrity check on resume, max_wave_resume_attempts retry limit and FAILED_UNRECOVERABLE transition |
| AR-300..AR-309 | planned | All ContextCore data flow (provenance chain, enrichment consumption) |
| AR-405 | planned | Cost projection gate |
| AR-508..AR-511 | planned | Recovery hardening (chunk resume, config drift, state integrity, migration including v3→v4) |
| AR-605, AR-606 | planned | Event JSONL externalization and dedup |
| AR-708 | planned | Max concurrent lanes configuration and enforcement, default of `os.cpu_count() + 4` |
| AR-805, AR-807..AR-809 | planned | Interactive mode, git tags, advisory lock, stalled retry |
| AR-811 | planned | Task ID input validation: path separator rejection, shell metacharacter rejection, null byte rejection, format string pattern rejection |
| AR-812 | planned | Global context immutability during concurrent lane execution: read-only enforcement, lane-local isolation, wave barrier merge correctness |
| AR-813 | planned | FINALIZE per-task error guard: single task Gate 3b crash does not kill manifest for all tasks |
| AR-814 | planned | Static method audit: all non-self-using methods in phase handlers are @staticmethod; CI lint catches missing decorators |
| AR-815 | planned | Partial manifest on FINALIZE crash: `incomplete: true` flag, error details, partial task entries |
| AR-816..AR-820 | planned | Truncation enforcement: Gate 4 escalation, contract YAML severity upgrade, size regression hard block, compound gate, OTel rejection event |
| AR-821..AR-825 | planned | Module resolution fidelity: SCAFFOLD module inventory, IMPLEMENT prompt injection, INTEGRATE import validation, contract YAML propagation, OTel attributes |
| AR-900..AR-908 | planned | Mottainai compliance — full review metadata serialization (reviewer_verdict dict, parsed DesignSection persistence, plan constraint storage, serialization round-trip fidelity), metadata forwarding, deterministic pre-review validation, provenance audit trail, structured diagnostics, integrity timing |
| AR-1000, AR-1005 | planned | `project_root` injection into `initial_context` and defense-in-depth `WorkflowConfig` propagation |
| AR-1010..AR-1013 | planned | Checkpoint persistence expansion for onboarding fields, service_metadata, plan_document_text |
| AR-1020..AR-1022 | planned | Prompt enrichment: project architecture, service metadata, and project context in IMPLEMENT and REVIEW |
| AR-1023, AR-1024 | AR-1024 implemented; AR-1023 planned | REVIEW service metadata compliance, TEST service metadata forwarding |
| AR-1030..AR-1034 | planned | Cross-phase propagation: service_metadata, plan_context, calibration_hints, requirements_text, cross-feature accumulation, audit trail |

---

## Implementation Priority

| Phase | Requirements | Priority | Impact |
|-------|-------------|----------|--------|
| 0a. FINALIZE Crash Prevention | AR-813, AR-814 | **Critical** | Per-task error guard + static method audit — without this, every future run risks losing its manifest |
| 0. Update-First Design Mode | AR-127, AR-128 | **Critical** | Prevents A-15 production file destruction |
| 0b. Truncation Enforcement | AR-816, AR-817, AR-818, AR-819 | **High** | Prevents destructive overwrites of existing code with truncated generation |
| ~~1b. Semantic Validators~~ | ~~AR-143..AR-147, AR-810~~ | ~~**High**~~ | ~~DONE — Commits `bed77d5`, `dc3c241`~~ |
| 1. ContextCore Data Flow Fixes | AR-300..AR-302, AR-164, AR-165 | **High** | Closes provenance chain, enables Gate 3 |
| 2. Onboarding Metadata Consumption | AR-303..AR-308, AR-111, AR-125..AR-126, AR-137 | **Medium** | Enriches code generation with export data |
| 3. Recovery Hardening | AR-508..AR-511 | **Medium** | Robust resume across config changes |
| 4. Orchestration Enhancements | AR-209..AR-212, AR-405, AR-708, AR-809, AR-811, AR-812 | **Medium** | Wave-parallel execution, concurrency control, cost projection, operational safety, task ID validation, context immutability |
| 4d. Prime-Convergent Quality Loop | AR-129, AR-138, AR-139, AR-153, AR-166 (with AR-206 policy baseline) | **High** | Brings Prime’s strongest quality controls into Artisan: spec/review thresholding, deterministic retries with feedback, decomposition/reuse safeguards, and forensic artifact retention |
| 4b. Module Resolution Fidelity | AR-821, AR-822, AR-823, AR-824 | **Medium** | Prevents LLM from importing non-existent modules |
| 4c. Safety Observability | AR-815, AR-820, AR-825 | **Medium** | Partial manifest, OTel events for truncation and import validation |
| 5. Interactive and Git Safety | AR-605..AR-606, AR-805..AR-808 | **Low** | Interactive operation, event durability |
| 6. Mottainai Compliance | AR-900..AR-908 | **Medium** | Eliminates 20 intra-pipeline waste gaps (Gaps 17–36). Note: AR-900 (P0) and AR-902 (P0) must be implemented before or alongside AR-212 wave-parallel mode, as wave context merging depends on full design metadata serialization (AR-900) and `_downstream_map` population (AR-902). |
| 7a. Project-Centric Context Survival | AR-1000, AR-1005, AR-1010, AR-1011, AR-1013 | **High** | P0 context injection + checkpoint persistence — prerequisite for prompt enrichment. ~25 lines of production code. |
| 7b. Project-Centric Prompt Enrichment | AR-1020..AR-1022, AR-1030 | **High** | P0 prompt enrichment — IMPLEMENT and REVIEW prompts gain project architecture, service metadata, and project context. ~70 lines across 2 files. |
| 7c. Project-Centric Completeness | AR-1004, AR-1012, AR-1023, AR-1031..AR-1034 | **Medium** | P1 completeness — audit trail, cross-feature accumulation, requirements text. ~80 lines across 3 files. |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [`startd8.artisan.functional-requirements.yaml`](capability-index/startd8.artisan.functional-requirements.yaml) | Canonical YAML (this doc is the companion) |
| [`PLAN-artisan-contractor.md`](PLAN-artisan-contractor.md) | Implementation plan (source for planned requirements) |
| [`ARTISAN_WORKFLOW_GUIDE.md`](ARTISAN_WORKFLOW_GUIDE.md) | User/developer guide |
| [`plans/ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md`](plans/ARTISAN_CONTEXTCORE_DATA_FLOW_FIXES.md) | Code fix plan for AR-3xx |
| [`PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md`](PROJECT_CENTRIC_ARTISAN_REQUIREMENTS.md) | Original PCA requirements (PCA-1xx..PCA-4xx → AR-10xx) — gap analysis, data flow diagrams, contract YAML amendments |
| [`PIPELINE_SAFETY_GATE_REQUIREMENTS.md`](PIPELINE_SAFETY_GATE_REQUIREMENTS.md) | PI-012/PI-013 failure analysis — AR-813..AR-825 (FINALIZE resilience, truncation enforcement, module resolution) |
| [`startd8.workflow.functional-requirements.yaml`](capability-index/startd8.workflow.functional-requirements.yaml) | Workflow framework requirements (FR-1xx..FR-5xx) |
| [`PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md`](PLAN_INGESTION_CONTEXTCORE_RECOMMENDATIONS.md) | Upstream ingestion design recommendations |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-21 16:39:43 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R3-F1 | orchestration | high | AR-206 (feature-serial) acceptance criteria should be updated to mention that wave-parallel is a third execution mode that is mutually exclusive with feature-serial. Currently AR-206 only describes the feature-serial behavior without acknowledging the wave-parallel alternative. | Straightforward documentation fix ensuring the requirements framework reflects the implemented constraint. Already applied in Appendix A for the narrative doc; this ensures the YAML is also updated. |
| R3-F2 | orchestration | high | No AR-xxx requirement exists for wave-parallel execution mode. The plan introduces a new execution mode (`wave_parallel`) comparable to AR-206 (feature-serial) but there is no formal requirement defining its behavior, acceptance criteria, or verification approach. | A new execution mode comparable in scope to AR-206 must have a corresponding formal requirement for traceability, testability, and compliance verification. Already applied in Appendix A. |
| R3-F3 | recovery | high | AR-505 (checkpoint persistence) acceptance criteria list schema version 2 fields but do not mention v3 (lane fields) or v4 (wave fields). The checkpoint schema has evolved beyond what the requirement documents. | The checkpoint schema has evolved to v4 but the requirement still documents only v2, creating a compliance verification gap. The canonical YAML must reflect the actual contract. |
| R3-F4 | cost_model | medium | AR-404 (CostBudgetExceededError) acceptance criteria say "After each phase, check cumulative_cost > cost_budget" but wave-parallel introduces intra-phase budget checks (per-wave barrier). The requirement should be updated to cover both phase-boundary and wave-barrier budget enforcement. | Two endorsements. The two-layer cost enforcement is a key correctness property. AR-404's phase-boundary-only criteria would cause compliance tests to miss the wave-barrier enforcement path. |

#### Review Round R4

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 16:42:55 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R4-F1 | requirements | high | AR-212 was added (per Appendix A, R4-F2) but the `orchestration_requirements` list in the YAML only goes to AR-211. AR-212 must be added to the YAML file with its acceptance criteria, `depends_on`, `implementation_hints`, and `verified_by` fields. The YAML `summary.total_requirements` count and `orchestration.count` in `traceability` must be updated. | One endorsement. The YAML is the canonical machine-readable source. Without the YAML entry, automated tooling and compliance verification cannot find AR-212. Already accepted in Appendix A. |
| R4-F2 | requirements | medium | AR-505 acceptance criteria list "Schema version 2" fields but do not list v3 (lane fields: `lane_assignments`, `completed_lanes`, `lane_results`) or v4 (wave fields: `wave_assignments`, `completed_waves`, `current_wave`). Per Appendix A (R4-F3), this was applied to the narrative doc but the YAML `AR-505` entry still only documents v2. | One endorsement. Duplicate of R3-F3 applied to the YAML specifically. The YAML must be the authoritative checkpoint contract specification. |
| R4-F3 | requirements | low | AR-404 acceptance criteria say "Phase that caused the breach completes; subsequent phases not started" but do not mention intra-phase wave-barrier budget checks. Per Appendix A (R4-F4), this was accepted for the narrative doc. The YAML `AR-404` entry needs an additional acceptance criterion: "In wave-parallel mode, budget is also checked at wave barriers within a phase; the completed wave's lanes finish, but subsequent waves are not started." | One endorsement. Duplicate of R3-F4 applied to the YAML. Without the YAML update, automated acceptance testing misses wave-barrier enforcement. |
| R4-F4 | requirements | low | AR-206 (feature-serial) acceptance criteria do not mention mutual exclusivity with `wave_parallel`. The narrative ARTISAN_REQUIREMENTS.md Execution Modes table documents it, but the YAML `AR-206` entry has no criterion like "Mutually exclusive with wave_parallel mode (WorkflowConfig raises ValueError)." | One endorsement. Duplicate of R3-F1 applied to the YAML. The canonical testable specification must document the mutual exclusion constraint. |

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R3-F1 | Update AR-206 (feature-serial) acceptance criteria to document mutual exclusivity with wave_parallel mode. |  | The plan introduces wave_parallel as mutually exclusive with feature_serial (Phase 3b ValueError). AR-206 should reflect this constraint so that requirement-based testing covers the mutual exclusion. This is a minor documentation fix that maintains requirements-to-implementation traceability. | 2026-02-21 16:44:53 UTC |
| R3-F2 | Create a new formal requirement (AR-212) for wave-parallel execution mode with acceptance criteria matching the plan's Phase 3c specification. |  | The plan introduces a complete new execution mode comparable in scope to AR-206 (feature-serial) but has no corresponding formal requirement. This is a gap in the requirements framework — the plan is implementing functionality that cannot be traced to a testable requirement. AR-212 should define wave-parallel behavior, acceptance criteria, and verification approach to maintain the project's established traceability discipline. | 2026-02-21 16:44:53 UTC |
| R3-F3 | Update AR-505 (checkpoint persistence) acceptance criteria to include v3 (lane fields) and v4 (wave fields) checkpoint schema. |  | AR-505 acceptance criteria stop at v2 schema. The plan introduces v4 with wave fields, and v3 (lane fields from commit fbfae7a) is also undocumented in the requirement. This creates a compliance verification gap where the requirement doesn't describe the actual checkpoint schema. Updating AR-505 is necessary for the requirement to serve its purpose as a testable specification. | 2026-02-21 16:44:53 UTC |
| R3-F4 | Update AR-404 (CostBudgetExceededError) acceptance criteria to cover intra-phase budget checks at wave barriers in wave-parallel mode. |  | The plan's two-layer cost enforcement (R1-S6) adds authoritative budget checks at wave barriers within the IMPLEMENT phase. AR-404's 'after each phase' criteria doesn't cover this intra-phase enforcement path. Without updating AR-404, compliance testing would miss the wave-barrier budget check — a key correctness property of the wave execution model. | 2026-02-21 16:44:53 UTC |
| R3-F1 | Update AR-206 acceptance criteria to document mutual exclusivity with wave_parallel mode. |  | This is a straightforward documentation fix that maintains requirements-to-implementation traceability. The plan already implements this constraint (Phase 3b ValueError), so the requirement should reflect it. Already noted as applied in Appendix A but the YAML needs the actual criterion added. | 2026-02-21 16:58:12 UTC |
| R3-F2 | Create a new AR-212 requirement for wave-parallel execution mode with formal acceptance criteria. |  | A new execution mode comparable in scope to AR-206 must have a corresponding formal requirement. Already noted as applied in Appendix A and the narrative doc was updated, but this confirms the YAML entry is needed. The plan's Phase 3c specification provides the acceptance criteria to formalize. | 2026-02-21 16:58:12 UTC |
| R3-F3 | Update AR-505 checkpoint persistence acceptance criteria to include v3 (lane) and v4 (wave) schema fields. |  | The YAML is the canonical requirements source and must document the actual checkpoint schema. AR-505 stopping at v2 creates a compliance verification gap. Already noted as applied in Appendix A for the narrative doc; the YAML needs the same update. | 2026-02-21 16:58:12 UTC |
| R3-F4 | Update AR-404 acceptance criteria to cover intra-phase wave-barrier budget checks in wave-parallel mode. |  | The two-layer cost enforcement is a key correctness property of wave mode. AR-404's phase-boundary-only criteria would cause compliance tests to miss the wave-barrier enforcement path. Has 2 endorsements. Already noted as applied in Appendix A for the narrative doc; the YAML needs the criterion. | 2026-02-21 16:58:12 UTC |
| R4-F1 | Add AR-212 to the requirements YAML with full structured fields (acceptance criteria, depends_on, implementation_hints, verified_by). |  | The YAML is the canonical requirements source. AR-212 exists in the narrative companion (Appendix A confirms it was accepted) but the YAML file still lacks the entry. Automated tooling and compliance verification depend on the YAML. The narrative doc already provides the acceptance criteria to formalize. | 2026-02-21 16:58:12 UTC |
| R4-F2 | Update AR-505 in the requirements YAML to include v3 and v4 checkpoint schema fields. |  | Duplicate of R3-F3 applied to the YAML specifically. The narrative doc was updated per Appendix A but the YAML entry still documents only v2. The YAML must be the authoritative specification of the checkpoint contract. | 2026-02-21 16:58:12 UTC |
| R4-F3 | Add wave-barrier budget check criterion to AR-404 in the requirements YAML. |  | Duplicate of R3-F4 applied to the YAML specifically. The narrative was updated per Appendix A but the YAML AR-404 entry still only mentions phase-boundary checks. Without the YAML update, automated acceptance testing misses wave-barrier enforcement. | 2026-02-21 16:58:12 UTC |
| R4-F4 | Add mutual exclusivity with wave_parallel to AR-206 acceptance criteria in the requirements YAML. |  | Duplicate of R3-F1 applied to the YAML specifically. The narrative was updated but the YAML AR-206 entry lacks the criterion. Consistent with the pattern of ensuring the canonical YAML reflects all accepted changes. | 2026-02-21 16:58:12 UTC |
| R5-F2 | Add --max-concurrent-lanes to the key CLI flags table under AR-7xx in the requirements doc. |  | The plan introduces max_concurrent_lanes as a critical operational control (R3-S3) that directly affects resource utilization and API rate limiting. It's already defined in WorkflowConfig (Phase 3b) and the CLI (Phase 4a). Omitting it from the requirements doc's CLI flags table creates a documentation gap. A new AR-708 or addition to the CLI flags table ensures traceability. | 2026-02-21 16:58:12 UTC |
| R5-F3 | Amend AR-212 resume criteria to explicitly require file integrity check from the 4-step resume protocol. |  | AR-212 AC#7 says 'Resume from a wave checkpoint restarts from the incomplete wave, re-executing only incomplete lanes within that wave' but omits Step 2 of the 4-step resume protocol (verify generated files exist on disk). This is a key correctness property — without the integrity check, a resume could skip a lane that completed but whose files were lost (e.g., git reset). Making it an explicit acceptance criterion in AR-212 ensures it's tested. | 2026-02-21 16:58:12 UTC |
| R5-F4 | Add formal depends_on links from AR-212 to AR-900 and AR-902 in the requirements YAML. |  | The plan explicitly identifies AR-900 as a P0 blocker for Phase 3 and AR-902 as a dependency for wave-parallel's _downstream_map merge field. Making these dependencies machine-readable in the YAML prevents accidental scheduling of wave-parallel implementation before its prerequisites are complete. This is especially important since AR-900 and AR-902 are in a different implementation phase (phase_6 mottainai) than wave-parallel (phase_4 orchestration). | 2026-02-21 16:58:12 UTC |
| R3-F1 | Update AR-206 acceptance criteria to document mutual exclusivity with wave_parallel mode. |  | The plan already implements this constraint (Phase 3b ValueError). The requirement must reflect it for traceability and to ensure compliance testing covers the mutual exclusion. Minor documentation fix with high traceability value. | 2026-02-21 17:14:28 UTC |
| R3-F2 | Create a new AR-212 requirement for wave-parallel execution mode with formal acceptance criteria. |  | Wave-parallel is a new execution mode comparable in scope to AR-206. Without a formal requirement, there are no testable acceptance criteria, no verified_by linkage, and no traceability. This is a gap in the requirements framework that must be closed. | 2026-02-21 17:14:28 UTC |
| R3-F3 | Update AR-505 checkpoint persistence acceptance criteria to include v3 and v4 schema fields. |  | AR-505 stops at v2 schema. The actual implementation includes v3 (lane fields) and v4 (wave fields). The requirement must describe the actual checkpoint contract for compliance verification to be meaningful. | 2026-02-21 17:14:28 UTC |
| R3-F4 | Update AR-404 to cover intra-phase wave-barrier budget checks in wave-parallel mode. |  | Two endorsements. The plan's two-layer cost enforcement adds authoritative budget checks at wave barriers within IMPLEMENT. AR-404's phase-boundary-only criteria would cause compliance tests to miss this enforcement path, which is a key correctness property of wave mode. | 2026-02-21 17:14:28 UTC |
| R4-F1 | Add AR-212 to the requirements YAML with full structured fields. |  | One endorsement. The YAML is the canonical machine-readable source. AR-212 exists in the narrative but not the YAML, meaning automated tooling and compliance verification cannot find it. The summary counts are also wrong without it. | 2026-02-21 17:14:28 UTC |
| R4-F2 | Update AR-505 in the YAML to include v3 and v4 checkpoint schema fields. |  | One endorsement. Duplicate of R3-F3 applied specifically to the YAML. The YAML must be the authoritative specification of the checkpoint contract. Without the update, automated compliance checks validate only v2 fields. | 2026-02-21 17:14:28 UTC |
| R4-F3 | Add wave-barrier budget check criterion to AR-404 in the YAML. |  | One endorsement. Duplicate of R3-F4 applied to the YAML specifically. Without the YAML update, automated acceptance testing misses wave-barrier enforcement. Consistent with the pattern of ensuring the canonical YAML reflects all accepted changes. | 2026-02-21 17:14:28 UTC |
| R4-F4 | Add mutual exclusivity with wave_parallel to AR-206 acceptance criteria in the YAML. |  | One endorsement. Duplicate of R3-F1 applied to the YAML. The YAML is the canonical testable specification and must document the mutual exclusion constraint already implemented in the plan. | 2026-02-21 17:14:28 UTC |
| R5-F2 | Add --max-concurrent-lanes to the key CLI flags table under AR-7xx. |  | One endorsement. The plan introduces max_concurrent_lanes as a critical operational control that directly affects resource utilization and API rate limiting. It's already defined in WorkflowConfig and CLI. Omitting it from the requirements CLI flags table creates a documentation gap. A new AR-708 formalizes traceability. | 2026-02-21 17:14:28 UTC |
| R5-F3 | Amend AR-212 resume criteria to explicitly require file integrity check from the 4-step resume protocol. |  | One endorsement. AR-212 AC#7 omits Step 2 of the 4-step resume protocol (verify generated files exist on disk). This is a key correctness property — without the integrity check, resume could skip a lane whose output files were lost. Making it an explicit acceptance criterion ensures it's tested. | 2026-02-21 17:14:28 UTC |
| R5-F4 | Add formal depends_on links from AR-212 to AR-900 and AR-902 in the YAML. |  | One endorsement. The plan explicitly identifies AR-900 as a P0 blocker and AR-902 as a dependency. Machine-readable depends_on in the YAML prevents accidental scheduling of wave-parallel before its prerequisites. Critical for cross-phase dependency tracking. | 2026-02-21 17:14:28 UTC |
| R6-F2 | Add field-level type contracts for v4 wave fields in AR-505 acceptance criteria. |  | The plan specifies detailed type validation for wave checkpoint fields (Phase 3a) but AR-505 doesn't define the expected types. Adding explicit types (dict[str, int], list[int], Optional[int]) makes the checkpoint contract machine-verifiable and gives the type validation code a requirement to trace to. | 2026-02-21 17:14:28 UTC |
| R6-F3 | Align AR-708 default from 'unbounded' to 'os.cpu_count() + 4' to match the plan's actual implementation. |  | The requirement says unbounded, the plan says CPU-count-bounded. The plan's behavior is correct (prevents thread exhaustion), so the requirement must be updated to match. A misleading requirement is worse than no requirement. | 2026-02-21 17:14:28 UTC |
| R6-F4 | Add acceptance criterion to AR-212 for the per-wave resume retry limit. |  | The max_wave_resume_attempts feature is a user-visible behavior change (workflow permanently fails after N retries) that prevents unbounded cost waste. Without a formal acceptance criterion, an implementer could omit the retry limit and still pass AR-212 tests. This safety feature deserves formal coverage. | 2026-02-21 17:14:28 UTC |
| R7-F1 | Update AR-708 default from 'unbounded' to 'os.cpu_count() + 4'. |  | Duplicate of R6-F3. The requirement must match the plan's actual safe default. An unbounded default documented in the requirement contradicts the plan's deliberate resource protection. | 2026-02-21 17:14:28 UTC |
| R7-F2 | Add a new requirement for the per-wave resume retry limit (max_wave_resume_attempts). |  | The retry limit prevents unbounded cost waste from poison-pill tasks in resume loops. This is a user-visible safety feature that deserves formal requirement coverage. While R6-F4 adds it as an AC on AR-212, a dedicated requirement (or explicit AR-212 AC) ensures testability. Accepting this as confirmation that the retry limit needs formal coverage — can be satisfied by R6-F4's accepted AR-212 AC#8 rather than a separate requirement. | 2026-02-21 17:14:28 UTC |
| R3-F1 | Update AR-206 acceptance criteria to document mutual exclusivity with wave_parallel mode. |  | Straightforward documentation fix ensuring the requirements framework reflects the implemented constraint. Already applied in Appendix A for the narrative doc; this ensures the YAML is also updated. | 2026-02-21 17:41:52 UTC |
| R3-F2 | Create new AR-212 requirement for wave-parallel execution mode with formal acceptance criteria. |  | A new execution mode comparable in scope to AR-206 must have a corresponding formal requirement for traceability, testability, and compliance verification. Already applied in Appendix A. | 2026-02-21 17:41:52 UTC |
| R3-F3 | Update AR-505 checkpoint persistence acceptance criteria to include v3 and v4 schema fields. |  | The checkpoint schema has evolved to v4 but the requirement still documents only v2, creating a compliance verification gap. The canonical YAML must reflect the actual contract. | 2026-02-21 17:41:52 UTC |
| R3-F4 | Update AR-404 to cover intra-phase wave-barrier budget checks in wave-parallel mode. |  | Two endorsements. The two-layer cost enforcement is a key correctness property. AR-404's phase-boundary-only criteria would cause compliance tests to miss the wave-barrier enforcement path. | 2026-02-21 17:41:52 UTC |
| R4-F1 | Add AR-212 to the requirements YAML with full structured fields. |  | One endorsement. The YAML is the canonical machine-readable source. Without the YAML entry, automated tooling and compliance verification cannot find AR-212. Already accepted in Appendix A. | 2026-02-21 17:41:52 UTC |
| R4-F2 | Update AR-505 in the YAML to include v3 and v4 checkpoint schema fields. |  | One endorsement. Duplicate of R3-F3 applied to the YAML specifically. The YAML must be the authoritative checkpoint contract specification. | 2026-02-21 17:41:52 UTC |
| R4-F3 | Add wave-barrier budget check criterion to AR-404 in the YAML. |  | One endorsement. Duplicate of R3-F4 applied to the YAML. Without the YAML update, automated acceptance testing misses wave-barrier enforcement. | 2026-02-21 17:41:52 UTC |
| R4-F4 | Add mutual exclusivity with wave_parallel to AR-206 acceptance criteria in the YAML. |  | One endorsement. Duplicate of R3-F1 applied to the YAML. The canonical testable specification must document the mutual exclusion constraint. | 2026-02-21 17:41:52 UTC |
| R5-F2 | Add --max-concurrent-lanes to the key CLI flags table under AR-7xx. |  | One endorsement. Already applied in Appendix A. The plan introduces max_concurrent_lanes as a critical operational control. A new AR-708 formalizes traceability. | 2026-02-21 17:41:52 UTC |
| R5-F3 | Amend AR-212 resume criteria to explicitly require file integrity check from the 4-step resume protocol. |  | One endorsement. Already applied in Appendix A. The integrity check (Step 2) is a key correctness property for robust recovery and must be an explicit acceptance criterion. | 2026-02-21 17:41:52 UTC |
| R5-F4 | Add formal depends_on links from AR-212 to AR-900 and AR-902 in the YAML. |  | One endorsement. Already applied in Appendix A. Machine-readable dependencies prevent accidental scheduling of wave-parallel before its prerequisites are complete. | 2026-02-21 17:41:52 UTC |
| R6-F1 | Add AR-811 requirement for task_id input validation against unsafe characters. |  | Two endorsements. Task IDs flow into checkpoints, file paths, git commits, and log messages from LLM output. This cross-cutting safety concern needs a formal requirement for traceability. | 2026-02-21 17:41:52 UTC |
| R6-F2 | Add field-level type contracts for v4 wave fields in AR-505 acceptance criteria. |  | Already applied in Appendix A. The plan specifies detailed type validation (R3-S7) but the requirement doesn't define expected types. Adding explicit types makes the checkpoint contract machine-verifiable. | 2026-02-21 17:41:52 UTC |
| R6-F3 | Align AR-708 default from 'unbounded' to 'os.cpu_count() + 4' to match the plan's actual implementation. |  | Already applied in Appendix A. The requirement says unbounded, the plan says CPU-count-bounded. The plan's behavior is correct; the requirement must match. | 2026-02-21 17:41:52 UTC |
| R6-F4 | Add acceptance criterion to AR-212 for the per-wave resume retry limit (max_wave_resume_attempts). |  | Two endorsements. Already applied in Appendix A. The retry limit is a user-visible safety feature preventing unbounded cost waste that deserves formal coverage as AC#8. | 2026-02-21 17:41:52 UTC |
| R7-F1 | Update AR-708 default from 'unbounded' to 'os.cpu_count() + 4'. |  | Already applied in Appendix A. Duplicate of R6-F3. The requirement must match the plan's safe default. | 2026-02-21 17:41:52 UTC |
| R7-F2 | Add formal requirement coverage for the per-wave resume retry limit. |  | Already applied in Appendix A. Satisfied by R6-F4's accepted AR-212 AC#8 rather than a separate requirement. | 2026-02-21 17:41:52 UTC |
| R7-F4 | Add AR-812 requirement for protection of read-only global context fields from concurrent mutation. |  | Two endorsements. Already applied in Appendix A. Global context immutability during wave execution is a core safety guarantee of the concurrent execution model that needs formal requirement coverage. | 2026-02-21 17:41:52 UTC |
| R8-F1 | Add the core dependency-ordering invariant as an explicit AR-212 acceptance criterion. |  | The fundamental correctness property of wave-parallel mode — 'no task executes before all tasks it depends on have completed' — is not stated in any acceptance criterion. This is the entire reason waves exist. An implementation could satisfy all listed criteria while violating this invariant. It must be AC#1 or equivalent. | 2026-02-21 17:41:52 UTC |
| R8-F2 | Add wave_resume_count to AR-505 checkpoint schema table and acceptance criteria. |  | wave_resume_count is essential for the retry limit (AR-212 AC#8) to function across resume boundaries. Without it in the checkpoint specification, an implementer could omit it and the retry count would reset on every resume, defeating the safety feature. | 2026-02-21 17:41:52 UTC |
| R8-F4 | Update AR-708 to reference max_parallel_lanes (existing field) instead of max_concurrent_lanes per correction C2. |  | Correction C2 resolved the naming conflict by reusing max_parallel_lanes, but AR-708 still says max_concurrent_lanes. An implementer following the requirement would create a conflicting field. The requirement must match the corrected plan. | 2026-02-21 17:41:52 UTC |
| R9-F1 | Add AR-811 requirement for task ID input validation. |  | Duplicate of R6-F1 which was already accepted. Task ID validation is a cross-cutting safety concern that needs formal requirement coverage. | 2026-02-21 17:41:52 UTC |
| R9-F2 | Add AR-812 requirement for protecting read-only global context fields from concurrent mutation. |  | Duplicate of R7-F4 which was already accepted. Global context immutability is a core safety guarantee of the concurrent execution model. | 2026-02-21 17:41:52 UTC |
| R9-F3 | Make AR-900 acceptance criteria more specific and testable with field-level detail. |  | AR-900 is a P0 blocker for wave mode. Vague acceptance criteria ('serializes full review metadata') leave room for incomplete implementations. Breaking it into specific sub-criteria (reviewer_verdict dict fields, parsed DesignSection persistence, plan constraint storage) makes the requirement unambiguous and directly testable. | 2026-02-21 17:41:52 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R5-F1 | Update AR-601 to define span hierarchy for wave-parallel mode. |  | The plan explicitly defers wave-level OTel spans to Phase 5 (Future), listing it in the table with the exact hierarchy 'workflow.{id}.wave.{N}.lane.{M}'. AR-601 covers the current phase-level spans. Adding wave-level span requirements before the wave execution mode itself is validated in production is premature. When wave-level spans are implemented, AR-601 can be updated or a new AR-608 created. | 2026-02-21 16:58:12 UTC |
| R5-F1 | Update AR-601 to define OTel span hierarchy for wave-parallel mode. |  | The plan explicitly defers wave-level OTel spans to Phase 5 (Future). Adding span hierarchy requirements before the wave execution mode is validated in production is premature. This can be addressed when wave-level spans are implemented. | 2026-02-21 17:14:28 UTC |
| R7-F3 | Add a new requirement for operational circuit breakers that warn on degenerate plan structures. |  | The circuit breakers (low parallelism warning, deep dependency chain warning) are already specified in the plan as part of Phase 2c (R5-S5, accepted). These are advisory log messages, not formal behavioral contracts. Creating a dedicated AR-608 for WARNING-level log messages over-formalizes what is essentially observability sugar. The warnings are adequately covered by the plan specification and the test cases in TestOperationalCircuitBreakers. | 2026-02-21 17:14:28 UTC |
| R5-F1 | Update AR-601 to define OTel span hierarchy for wave-parallel mode. |  | Already rejected in Appendix B. The plan explicitly defers wave-level OTel spans to Phase 5 (Future). Adding span hierarchy requirements before wave mode is validated in production is premature. | 2026-02-21 17:41:52 UTC |
| R7-F3 | Add a new requirement for operational circuit breakers warning on degenerate plan structures. |  | Already rejected in Appendix B. Circuit breakers are advisory log messages, not formal behavioral contracts. They are adequately covered by the plan specification and TestOperationalCircuitBreakers. | 2026-02-21 17:41:52 UTC |
| R8-F3 | Create a formal requirement for lane_parallel mode to formalize wave_parallel mutual exclusion. |  | While the gap is real (lane_parallel has no AR-xxx requirement), creating one is out of scope for this plan. The mutual exclusion is already implemented in WorkflowConfig.__post_init__ and tested. The pre-existing gap existed before wave mode and should be addressed separately as technical debt, not as a blocker for wave mode. | 2026-02-21 17:41:52 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R4

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-21 16:55:00 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R4-F1 | orchestration | high | AR-212 was added (per Appendix A, R3-F2) but the `orchestration_requirements` list in the YAML only goes to AR-211. AR-212 must be added to the YAML file with its acceptance criteria, `depends_on`, `implementation_hints`, and `verified_by` fields. The YAML `summary.total_requirements` count and `orchestration.count` in `traceability` must be updated. | The requirements YAML is the canonical source. AR-212 exists in the narrative companion (ARTISAN_REQUIREMENTS.md) but not in the YAML. This means automated requirement-tracking tooling won't find it, and `summary.by_layer.orchestration` reports 12 instead of 13. The narrative doc shows AR-212 acceptance criteria — these need to be formalized in the YAML's structured format. |
| R4-F2 | recovery | high | AR-505 acceptance criteria list "Schema version 2" fields but do not list v3 (lane fields: `lane_assignments`, `completed_lanes`, `lane_results`) or v4 (wave fields: `wave_assignments`, `completed_waves`, `current_wave`). Per Appendix A (R3-F3), this was applied to the narrative doc but the YAML `AR-505` entry still only documents v2. | The YAML is the canonical requirements source. The narrative companion was updated, but the YAML entry for AR-505 has not been amended. Any automated compliance check against the YAML would validate only v2 fields, missing v3/v4 checkpoint contract coverage. |
| R4-F3 | cost_model | medium | AR-404 acceptance criteria say "Phase that caused the breach completes; subsequent phases not started" but do not mention intra-phase wave-barrier budget checks. Per Appendix A (R3-F4), this was accepted for the narrative doc. The YAML `AR-404` entry needs an additional acceptance criterion: "In wave-parallel mode, budget is also checked at wave barriers within a phase; the completed wave's lanes finish, but subsequent waves are not started." | Without this criterion in the YAML, automated acceptance testing of AR-404 would only verify phase-boundary budget checks and miss the wave-barrier enforcement path. |
| R4-F4 | orchestration | medium | AR-206 (feature-serial) acceptance criteria do not mention mutual exclusivity with `wave_parallel`. The narrative ARTISAN_REQUIREMENTS.md Execution Modes table documents it, but the YAML `AR-206` entry has no criterion like "Mutually exclusive with wave_parallel mode (WorkflowConfig raises ValueError)." | Per Appendix A (R3-F1), this was accepted. But the YAML — which is the canonical testable specification — still has no acceptance criterion for the mutual exclusion. An implementer verifying AR-206 compliance against the YAML would not test the wave_parallel conflict. |

#### Review Round R5

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 16:56:24 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R5-F1 | observability | high | Update AR-601 (OTel spans) to define the span hierarchy for wave-parallel mode. | AR-601 defines a flat `workflow.{id}.{phase}` hierarchy. This is insufficient for wave-parallel mode, which has two additional dimensions of execution. The requirement should specify the full hierarchy, such as `workflow.{id}.{phase}.wave.{N}.lane.{M}`, to make wave and lane performance properly observable. The plan defers this to "Future", but it's a core observability contract for the feature. |
| R5-F2 | configuration | medium | Add the `--max-concurrent-lanes` CLI flag to the list of key CLI flags under AR-7xx. | The plan introduces `--max-concurrent-lanes` as a critical operational control for managing resource utilization in wave-parallel mode. The requirements document's table of key CLI flags (under Layer 7) omits it, creating a documentation and traceability gap. It should be formally listed as a requirement. |
| R5-F3 | recovery | medium | Amend AR-212's resume criteria to explicitly require a state-to-code integrity check. | AR-212 AC#7 describes resuming incomplete lanes but omits the file integrity check from the plan's 4-step resume protocol (Step 2). This check (verifying generated files still exist on disk) is crucial for robust recovery (related to AR-510) and should be an explicit acceptance criterion for wave-mode resume. |
| R5-F4 | orchestration | high | Add formal `depends_on` links from AR-212 to its prerequisite Mottainai requirements (AR-900 and AR-902). | The plan correctly identifies AR-900 as a P0 blocker and AR-902 as a dependency for wave-parallel mode to function correctly. The requirements YAML should reflect this with explicit `depends_on: [AR-900, AR-902]` entries on the AR-212 requirement. This makes the dependency machine-readable and prevents accidental scheduling of work in the wrong order. |

#### Review Round R6

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-21 17:11:15 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R6-F1 | safety_resilience | high | AR-8xx is missing a requirement for task_id input validation. The plan introduces `_SAFE_TASK_ID_PATTERN` validation in `compute_waves()` and `SeedTask.from_seed_entry()` but there is no corresponding AR-8xx requirement covering task_id sanitization. Suggest adding AR-811: "Task ID validation rejects identifiers containing path separators, shell metacharacters, null bytes, or format string patterns." | Task IDs are the primary key across all data structures (checkpoints, generation_results, merge operations, git commits, log messages). They originate from LLM output (plan ingestion PARSE) and are never validated for content safety. This is a cross-cutting safety concern that affects all layers. Without a formal requirement, the validation introduced by the plan (R6-S1) has no acceptance criteria and no `verified_by` linkage. |
| R6-F2 | recovery | medium | AR-505 checkpoint schema (as updated per Appendix A) should include a field-level type contract for v4 wave fields. The current acceptance criteria say "captures wave_assignments, completed_waves, current_wave" but don't specify the types (`dict[str, int]`, `list[int]`, `Optional[int]`). AR-505 v2 criteria similarly lack type specifications for `completed_features: list`, `current_feature: str`, etc. | The plan's Phase 3a specifies detailed type validation for wave checkpoint fields (R3-S7) but the requirement it implements (AR-505) doesn't define the expected types. This means the type validation code has no requirement to trace to — it's defensive coding without a testable specification. Adding explicit types to AR-505's acceptance criteria makes the checkpoint contract machine-verifiable. |
| R6-F3 | configuration | medium | AR-708 acceptance criteria say "defaults to unbounded (all tasks in a wave run concurrently)" but the plan specifies a default of `os.cpu_count() + 4` when `max_concurrent_lanes` is `None`. These are contradictory — the requirement says unbounded, the plan says CPU-count-bounded. Align AR-708 AC#1 to match the plan's actual default. | An operator reading AR-708 would expect `--max-concurrent-lanes` not set → truly unbounded concurrency. The plan's ThreadPoolExecutor uses `min(lane_count, config.max_concurrent_lanes or os.cpu_count() + 4)`, meaning `None` still caps at `cpu_count + 4`. This is the correct behavior (per R3-S3's rationale about thread exhaustion) but the requirement is misleading. |
| R6-F4 | orchestration | low | AR-212 acceptance criteria should include a criterion for the resume retry limit (R5-S3). The plan adds `max_wave_resume_attempts` with `FAILED_UNRECOVERABLE` status, but AR-212's 7 acceptance criteria don't mention retry limits. This is a user-visible behavior change (workflow permanently fails after N retries) that needs formal specification. | Without this criterion, an implementer could omit the retry limit and still pass all AR-212 acceptance tests. The retry limit is a safety feature that prevents unbounded cost waste — it deserves formal requirement coverage. Suggest adding AC#8: "A wave that fails more than `max_wave_resume_attempts` consecutive resume attempts is marked FAILED_UNRECOVERABLE and the workflow halts." |

#### Review Round R7

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 17:12:27 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R7-F1 | configuration | medium | Update AR-708 to specify the default for `max_concurrent_lanes` is `os.cpu_count() + 4`, not "unbounded". | The plan (R3-S3) correctly implements a safe, resource-aware default to prevent thread exhaustion. The requirement's "unbounded" default is dangerous and should be aligned with the safer implementation plan. An unbounded default is a DoS vulnerability. |
| R7-F2 | resilience | high | Add a new requirement (e.g., AR-811) for the per-wave resume retry limit introduced in the plan (R5-S3). | The `max_wave_resume_attempts` feature is a critical defense against "poison pill" tasks that cause unbounded cost waste in resume loops. This is a new, formal safety and cost-control feature that is not tracked by any existing requirement (AR-809 is related but covers a different failure mode). |
| R7-F3 | observability | medium | Add a new requirement (e.g., AR-608) for the operational circuit breakers that warn on degenerate plan structures (R5-S5). | The plan's warnings for low parallelism or deep dependency chains provide critical, early feedback to operators about inefficient plans. This is a new, valuable observability feature that should be formalized in the requirements to ensure it is tested and maintained as part of the workflow's contract. |
| R7-F4 | safety | high | Add a new requirement (e.g., AR-812) for the protection of read-only global context fields from mutation by concurrent lane threads (R5-S1). | The plan's mechanism to deepcopy global fields on isolation and assert their immutability post-merge is a critical defense against subtle data corruption in concurrent mode. This safety guarantee is a core part of the concurrent execution model and must be captured as a formal requirement. |

#### Review Round R8

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-21 17:39:01 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R8-F1 | orchestration | high | AR-212 acceptance criteria do not specify the ordering guarantee that waves provide. The criteria say "tasks with no dependencies are assigned to wave 0" and "a wave barrier synchronizes all lanes" but never state the core invariant: "No task executes before all tasks it depends on have completed." This is the fundamental correctness property of wave-parallel mode and it is not a stated acceptance criterion. | Without this invariant as a testable criterion, an implementation could satisfy all 8 listed criteria while still violating dependency ordering (e.g., by assigning tasks to incorrect waves). The dependency-ordering invariant is the entire reason waves exist. |
| R8-F2 | recovery | medium | AR-505 checkpoint schema table (Layer 5) lists `wave_resume_count` in the plan (Phase 3a) but it does not appear in the requirements doc's checkpoint field table or in any AR-505 acceptance criterion. This field is essential for the retry limit (AR-212 AC#8) to function across resume boundaries. | Without `wave_resume_count` in the checkpoint schema specification, an implementer could omit it from the checkpoint and still claim AR-505 compliance. The retry limit would then reset on every resume (count lost), defeating R5-S3. |
| R8-F3 | orchestration | medium | AR-212 and AR-206 are documented as mutually exclusive, but there is no requirement for `wave_parallel` and `lane_parallel` mutual exclusion. The plan implements this (Phase 3b `ValueError`), but AR-212 AC#1 only mentions `feature_serial` and `lane_parallel`. The requirements doc's Execution Modes table mentions the constraint, but `lane_parallel` has no formal AR-xxx requirement of its own — it exists only as the implicit complement of `feature_serial`. | `lane_parallel` mode is an undocumented execution mode. It has no AR-xxx requirement, no formal acceptance criteria, and no `verified_by` test linkage. Wave-parallel's mutual exclusion with it cannot be formally tested against a requirement that doesn't exist. This is a pre-existing gap amplified by wave mode's introduction. |
| R8-F4 | configuration | low | AR-708 specifies `max_concurrent_lanes` but correction C2 resolved the naming conflict by reusing the existing `max_parallel_lanes` field. The requirements doc (AR-708) still references `max_concurrent_lanes` in both the CLI flag name and the `WorkflowConfig` field name. The correction was applied to the plan but not propagated to the requirements. | After C2, the plan uses `max_parallel_lanes` (existing field) while AR-708 still says `max_concurrent_lanes`. An implementer following the requirements would create a new field that conflicts with the existing one, contradicting the correction. |

#### Review Round R9

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-21 17:40:05 UTC
- **Scope**: Review wave+lane parallel execution plan for correctness, safety (thread-safety, checkpoint integrity, resume correctness), data flow completeness (Mottainai compliance), and missing edge cases. Cross-reference against the ARTISAN_REQUIREMENTS.md to ensure plan aligns with existing AR-xxx requirements. (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale |
| ---- | ---- | ---- | ---- | ---- |
| R9-F1 | safety_resilience | high | Add a new requirement (e.g., AR-811) for task ID input validation. | The plan introduces `_SAFE_TASK_ID_PATTERN` as a defense-in-depth security measure against injection attacks (R6-S1, R7-S1). Task IDs flow from LLM output into file paths, checkpoint keys, and log messages. This validation is a critical safety gate that is not covered by any existing AR-8xx requirement, creating a traceability gap. |
| R9-F2 | safety_resilience | high | Add a new requirement (e.g., AR-812) for protecting read-only global context fields from mutation by concurrent threads. | The plan's mechanism for ensuring global context fields are immutable during wave execution (R5-S1) is a core defense against subtle data corruption in concurrent mode. This safety guarantee is a fundamental part of the concurrent execution model and must be captured as a formal, testable requirement to prevent future regressions. |
| R9-F3 | data_flow | medium | Make the acceptance criteria for AR-900 (DESIGN Serialize Full Metadata) more specific and testable. | AR-900 is a P0 blocker for wave mode. Its current acceptance criterion is "DESIGN serializes full review metadata (verdicts, parsed sections, plan constraints)". This is too vague. It should be broken down into specific, verifiable sub-criteria, such as: "The `reviewer_verdict` dict, including `approved`, `confidence`, `concerns`, and `suggestions` fields, must be present...", and "The parsed `DesignSection` dict must be persisted, not just the raw text blob." This makes the requirement unambiguous and easier to implement and test correctly. |
