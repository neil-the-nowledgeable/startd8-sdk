# Artisan Contractor Workflow Guide

**Version:** 0.4.0
**Document Version:** v1
**Last Updated:** 2026-02-11
**Audience:** Humans and AI Agents

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Phases](#phases)
4. [The Two-Half Split](#the-two-half-split)
5. [Quick Start](#quick-start)
6. [Runner Scripts](#runner-scripts)
7. [Design Handoff](#design-handoff)
8. [Configuration](#configuration)
9. [Context Seed](#context-seed)
10. [Cost Model](#cost-model)
11. [Observability](#observability)
12. [Best Practices](#best-practices)
13. [API Reference](#api-reference)
14. [Troubleshooting](#troubleshooting)

---

## Overview

The **Artisan Contractor** is a 7-phase workflow orchestrator that goes beyond the PrimeContractor by decomposing plans granularly before writing any code. Where PrimeContractor operates on a per-feature `generate -> integrate -> validate` loop, the Artisan Contractor separates **design** from **implementation** with explicit phase gates, checkpoint persistence, and cost budget enforcement.

### Key Differences from PrimeContractor

| Aspect | PrimeContractor | Artisan Contractor |
|--------|----------------|-------------------|
| **Input** | Feature queue with descriptions | Enriched context seed (from PlanIngestion + DomainPreflight) |
| **Design** | Implicit (LLM decides structure) | Explicit DESIGN phase with design documents per task |
| **Phase control** | Single loop | 7 discrete phases with handlers, checkpoints, and budget gates |
| **Execution model** | All-in-one | Supports split execution (design-only, implement-only) |
| **Cost model** | Single agent tier | 3-tier architecture: Haiku (drafter) / Sonnet (validator) / Opus (reviewer). Default runtime: 2-tier (Haiku + Opus via `HandlerConfig`) |
| **Resume** | Feature-level | Phase-level checkpoints with JSON persistence |

### When to Use

- Multi-task code generation batches with design review
- Projects where design documents must be reviewed before implementation
- Cost-sensitive workflows that benefit from cheap-draft/expensive-validate patterns
- Workflows that span multiple sessions (design today, implement tomorrow)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     Artisan Contractor Architecture                      │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                 ArtisanContractorWorkflow                         │   │
│  │              (orchestrator — artisan_contractor.py)                │   │
│  │                                                                   │   │
│  │  WorkflowConfig ─── phases ─── handlers ─── checkpoint_store     │   │
│  └───────────────────────────┬───────────────────────────────────────┘   │
│                               │                                          │
│                    ┌──────────▼──────────┐                               │
│                    │ ContextSeedHandlers │                               │
│                    │  (7 phase handlers) │                               │
│                    └──────────┬──────────┘                               │
│                               │                                          │
│  ┌────────┬────────┬──────────┼──────────┬────────┬────────┬────────┐   │
│  │ PLAN   │SCAFFOLD│ DESIGN   │IMPLEMENT │ TEST   │ REVIEW │FINALIZE│   │
│  │handler │handler │ handler  │ handler  │handler │handler │handler │   │
│  └────────┴────────┴──────────┴──────────┴────────┴────────┴────────┘   │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │                       Support Layers                              │   │
│  │  HandlerConfig   HandoffData   DesignDocumentationPhase           │   │
│  │  LeadContractorCodeGenerator   SeedTask                           │   │
│  └───────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Module | Role |
|-----------|--------|------|
| `ArtisanContractorWorkflow` | `artisan_contractor.py` | Orchestrator: phase sequencing, timeouts, cost budget, checkpoints |
| `ContextSeedHandlers` | `context_seed_handlers.py` | Factory that creates all 7 phase handler instances |
| `HandlerConfig` | `context_seed_handlers.py` | Shared config (agent specs, thresholds, timeouts) with 3-tier priority |
| `HandoffData` | `handoff.py` | Serializable context state for two-half workflow split |
| `SeedTask` | `context_seed_handlers.py` | Parsed task from the enriched context seed |
| `DesignDocumentationPhase` | `artisan_phases/design_documentation.py` | Multi-round design generation with reviewer/arbiter pattern |
| `LeadContractorCodeGenerator` | `generators/lead_contractor.py` | LLM-based code generation with draft/review loop |

---

## Phases

The workflow consists of 7 phases executed sequentially. Each phase receives a shared mutable `context` dict and returns output, cost, and metadata.

```
PLAN ──▶ SCAFFOLD ──▶ DESIGN ──▶ IMPLEMENT ──▶ TEST ──▶ REVIEW ──▶ FINALIZE
```

### Phase Details

#### 1. PLAN

Loads and validates the enriched context seed. Parses tasks, resolves execution order by dependencies, and builds the task index.

**Context keys set:** `tasks`, `task_index`, `plan_title`, `domain_summary`, `preflight_summary`, `total_estimated_loc`

#### 2. SCAFFOLD

Verifies that target directories exist for all tasks. Creates directories in non-dry-run mode. Reports existing files that will be overwritten.

**Context keys set:** `scaffold` (summary dict with `directories_needed`, `directories_created`, `existing_target_files`)

#### 3. DESIGN

Generates design documents for each task using the `DesignDocumentationPhase`. Each task goes through a multi-round draft/review cycle:

1. Drafter (Haiku) generates initial design
2. Reviewer (Opus) evaluates and suggests improvements
3. Iterate until agreement or max iterations reached

**Context keys set:** `design_results` (Dict[task_id, dict] with `design_document`, `agreed`, `iterations`, `cost`)

#### 4. IMPLEMENT

Generates code for each task using `LeadContractorCodeGenerator`. Uses design documents from the DESIGN phase (when available) to inform implementation.

**Context keys set:** `implementation`, `generation_results`

#### 5. TEST

Runs post-generation validators (syntax checks, import checks, lint, custom validators) against generated code.

**Context keys set:** `test_results`

#### 6. REVIEW

LLM-based quality review of generated implementations. Checks constraint coverage, code quality, and integration readiness.

**Context keys set:** `review_results`

#### 7. FINALIZE

Collects all artifacts (with per-artifact sha256 checksums, line counts, and domain classification), computes cost summaries, and writes a comprehensive execution report (`generation-manifest.json`) with per-task status rollup joining generation, test, and review outcomes.

> **Provenance gap:** The artisan seed carries `source_checksum` from the ContextCore export, but FINALIZE does not currently verify it against the original export or record it in the manifest. End-to-end provenance chain verification is planned but not yet implemented.

**Context keys set:** `workflow_summary`

---

## The Two-Half Split

The artisan workflow supports **split execution** where design and implementation run as separate processes. This is useful when:

- Design documents need human review before code generation starts
- Design and implementation happen in different sessions
- Different cost budgets apply to each half
- You want to re-run implementation against the same designs

### First Half: Design

Runs PLAN -> SCAFFOLD -> DESIGN and writes a **design handoff file** containing the context state needed by the second half.

```
                     First Half
┌──────────────────────────────────────┐
│  PLAN ──▶ SCAFFOLD ──▶ DESIGN       │
│                            │         │
│                    design-handoff.json│
└────────────────────────────┼─────────┘
                             │
                             ▼
                     Second Half
┌──────────────────────────────────────┐
│  IMPLEMENT ──▶ TEST ──▶ REVIEW ──▶  │
│                          FINALIZE    │
└──────────────────────────────────────┘
```

### Second Half: Implementation

Loads the handoff file, reconstructs the shared context dict, and runs IMPLEMENT -> TEST -> REVIEW -> FINALIZE. If no handoff is available, the handlers automatically reload tasks from the enriched seed file via `_ensure_context_loaded()`.

---

## Quick Start

### Prerequisites

1. An **enriched context seed** JSON file (output of PlanIngestionWorkflow + DomainPreflightWorkflow)
2. The SDK installed in dev mode: `pip3 install -e ".[all,dev]"`
3. `ANTHROPIC_API_KEY` set in your environment

### Full Workflow (All 7 Phases)

```bash
python3 scripts/run_artisan_workflow.py \
    --seed out/artisan-context-seed-enriched.json \
    --project-root /path/to/target/project \
    --output-dir out/artisan-results \
    --cost-budget 10.00
```

### Design Only (First Half)

```bash
python3 scripts/run_artisan_design_only.py \
    --seed out/artisan-context-seed-enriched.json \
    --project-root /path/to/target/project \
    --output-dir out/designs
```

This writes `out/designs/design-handoff.json` on success.

### Implementation Only (Second Half)

```bash
# Using the handoff file:
python3 scripts/run_artisan_implement_only.py \
    --handoff out/designs/design-handoff.json

# Or auto-detect handoff in a directory:
python3 scripts/run_artisan_implement_only.py \
    --output-dir out/designs

# Or fallback without handoff (tasks reload from seed):
python3 scripts/run_artisan_implement_only.py \
    --seed out/artisan-context-seed-enriched.json
```

### Dry Run (Preview Without Side Effects)

```bash
python3 scripts/run_artisan_workflow.py \
    --seed out/artisan-context-seed-enriched.json \
    --dry-run
```

No LLM calls, no file writes. Orchestration only — validates phase sequencing and task flow.

### Dress Rehearsal (Proactive Issue Detection)

```bash
python3 scripts/run_artisan_workflow.py \
    --seed out/artisan-context-seed-enriched.json \
    --output-dir out/designs \
    --task-filter PI-001 \
    --dress-rehearsal \
    --design-max-tokens 8192
```

**Distinct from dry run:** Dress rehearsal runs **real LLM calls** through the DESIGN phase to surface issues (truncation, section mismatches) before committing to a full run. Writes to `{output_dir}/.dress-rehearsal/`. Defaults to `--stop-after design` when set.

| Mode | LLM calls | File writes | Use case |
|------|-----------|-------------|----------|
| **Dry run** | No | No | Preview orchestration, zero cost |
| **Dress rehearsal** | Yes (through DESIGN) | To staging dir | Proactively find truncation, calibration issues |
| **Full run** | Yes | Yes | Production execution |

### Adopting Dress-Rehearsal Artifacts

Dress rehearsal design results are **not wasted**. A subsequent full run can adopt them:

```bash
# Auto-detect artifacts in <output-dir>/.dress-rehearsal/:
python3 scripts/run_artisan_workflow.py \
    --seed out/artisan-context-seed-enriched.json \
    --output-dir out/designs \
    --task-filter PI-001 \
    --adopt-prior

# Or point to a specific directory:
python3 scripts/run_artisan_workflow.py \
    --seed out/artisan-context-seed-enriched.json \
    --output-dir out/designs \
    --adopt-prior /path/to/.dress-rehearsal
```

**How it works:** The DESIGN phase handler checks each task's `design_results`. If a prior result has `status: "designed"` with a valid `design_document`, the task is **adopted** (status becomes `"adopted"`) and the LLM call is skipped entirely — saving time and cost. Tasks that failed or lack a design document are re-run normally.

When prior artifacts exist but `--adopt-prior` was not specified, the runner logs a hint:

```
INFO Prior dress-rehearsal artifacts detected at out/designs/.dress-rehearsal.
     Use --adopt-prior to reuse them and skip redundant LLM calls.
```

**Precursor to atomic operations:** This adopt-or-rerun pattern establishes task-level idempotency for the DESIGN phase — each task either reuses a valid prior result or generates a new one. Future phases (IMPLEMENT, TEST, REVIEW) can follow the same pattern for full pipeline idempotency.

### Convenience Shell Scripts (`dress-rehearsal.sh`, `adopt-prior.sh`)

Parameterized scripts that support env vars and project-root inference:

```bash
# Generic usage (requires ARTISAN_SEED):
export ARTISAN_SEED=/path/to/artisan-context-seed.json
./scripts/dress-rehearsal.sh PI-001
./scripts/adopt-prior.sh PI-002

# Optional: override project root (for multi-repo setups)
./scripts/adopt-prior.sh PI-001 /path/to/target/project
```

| Env var | Description |
|---------|-------------|
| `ARTISAN_SEED` | **(Required)** Path to enriched context seed JSON |
| `ARTISAN_OUTPUT_DIR` | Output directory (default: `seed_dir/artisan-design`) |
| `ARTISAN_PROJECT_ROOT` | Target project root; inferred from seed if unset (walk up for `pyproject.toml` or `.contextcore.yaml`). Defaults to `.` with a warning for multi-repo setups. |
| `ARTISAN_RESUME` | Set to `1` to resume from last checkpoint (use with same `--task-filter` as the interrupted run) |
| `ARTISAN_FORCE_IMPLEMENT` | Set to `1` to ignore cached `generation_results`; always run fresh IMPLEMENT |

**Project-root inference:** When `ARTISAN_PROJECT_ROOT` is unset, the script walks up from the seed's directory until it finds `pyproject.toml` or `.contextcore.yaml`. For multi-repo setups (e.g. SDK generating into wayfinder), set `ARTISAN_PROJECT_ROOT` explicitly.

**Wayfinder convenience wrappers:** `dress-rehearsal-PI-001.sh`, `adopt-prior-PI-002.sh`, etc. use wayfinder paths by default; override with env vars.

---

## Runner Scripts

### `scripts/run_artisan_workflow.py`

Full 7-phase workflow runner.

| Flag | Description |
|------|-------------|
| `--seed PATH` | **(Required)** Enriched context seed JSON |
| `--project-root PATH` | Target project root (default: `.`) |
| `--output-dir PATH` | Output directory (default: same as seed) |
| `--dry-run` | Simulate without side effects (no LLM calls) |
| `--dress-rehearsal` | Run real LLM calls through DESIGN; write to staging dir; default stop-after design |
| `--adopt-prior [PATH]` | Adopt design artifacts from a prior dress-rehearsal/design-only run; auto-detects from `.dress-rehearsal/` if no path given |
| `--force-implement` | Ignore cached `generation_results`; always run fresh IMPLEMENT (no resume from `.startd8/state/`) |
| `--design-max-tokens INT` | Override max_output_tokens for design phase (e.g. 8192 to avoid truncation) |
| `--no-auto-commit` | Disable auto-commit (default: commit each feature's generated code to git after implementation) |
| `--cost-budget FLOAT` | Maximum total cost in USD |
| `--timeout FLOAT` | Total workflow timeout in seconds |
| `--stop-after PHASE` | Stop after a phase (e.g., `--stop-after design`) |
| `--checkpoint-dir PATH` | Directory for checkpoint files |
| `--resume` | Resume from last checkpoint |
| `--lead-agent SPEC` | Lead agent spec override |
| `--drafter-agent SPEC` | Drafter agent spec override |
| `--verbose` | Debug logging |

When `--stop-after` includes the DESIGN phase, the script writes a `design-handoff.json` for the second half.

### `scripts/run_artisan_design_only.py`

Convenience wrapper that runs only PLAN -> SCAFFOLD -> DESIGN. Always writes `design-handoff.json` on success.

| Flag | Description |
|------|-------------|
| `--seed PATH` | **(Required)** Enriched context seed JSON |
| `--project-root PATH` | Target project root (default: `.`) |
| `--output-dir PATH` | Output directory (default: same as seed) |
| `--dry-run` | Simulate without side effects |
| `--lead-agent SPEC` | Lead agent spec override |
| `--verbose` | Debug logging |

### `scripts/run_artisan_implement_only.py`

Runs only IMPLEMENT -> TEST -> REVIEW -> FINALIZE using a design handoff.

| Flag | Description |
|------|-------------|
| `--handoff PATH` | Explicit path to `design-handoff.json` |
| `--output-dir PATH` | Directory containing `design-handoff.json` (auto-detected) |
| `--seed PATH` | Fallback: seed path only (no design_results) |
| `--project-root PATH` | Override project root from handoff |
| `--dry-run` | Simulate without side effects |
| `--cost-budget FLOAT` | Maximum total cost in USD |
| `--timeout FLOAT` | Total workflow timeout in seconds |
| `--lead-agent SPEC` | Lead agent spec override |
| `--drafter-agent SPEC` | Drafter agent spec override |
| `--verbose` | Debug logging |

**Context resolution priority:** `--handoff` > `--output-dir` (auto-detect) > `--seed` (fallback).

---

## Design Handoff

The handoff file (`design-handoff.json`) bridges the first and second halves of the workflow.

### What It Contains

```json
{
  "schema_version": 1,
  "enriched_seed_path": "/abs/path/to/seed.json",
  "project_root": "/abs/path/to/project",
  "output_dir": "out/designs",
  "workflow_id": "abc-123-...",
  "completed_phases": ["plan", "scaffold", "design"],
  "design_results": {
    "TASK-001": {"status": "agreed", "cost": 0.12, ...},
    "TASK-002": {"status": "agreed", "cost": 0.08, ...}
  },
  "scaffold": {
    "directories_created": ["src/auth/", "src/models/"],
    "existing_target_files": ["src/config.py"]
  },
  "created_at": "2026-02-11T14:30:00+00:00"
}
```

### Schema Version

The handoff uses `schema_version: 1` for forward compatibility. `load_design_handoff()` rejects files with a schema version higher than the SDK supports, with a clear error message to upgrade.

### Programmatic Usage

```python
from startd8.contractors.handoff import write_design_handoff, load_design_handoff

# Write after design completes
path = write_design_handoff(
    output_dir="out/designs",
    enriched_seed_path="/abs/path/to/seed.json",
    project_root="/abs/path/to/project",
    workflow_id="abc-123",
    completed_phases=["plan", "scaffold", "design"],
    design_results=context.get("design_results", {}),
    scaffold=context.get("scaffold", {}),
)

# Load for implementation
handoff = load_design_handoff("out/designs")  # dir or file path
print(handoff.enriched_seed_path)
print(handoff.design_results)
```

### Why a Separate Handoff (Not Checkpoints)?

The orchestrator's checkpoint system stores phase execution metadata (cost, status, timing) but **not the shared context dict**. The context dict is in-memory only and lost when the process exits. The handoff file explicitly captures the context keys that downstream handlers need.

---

## Configuration

### HandlerConfig

All phase handlers share a `HandlerConfig` that controls agent selection, iteration limits, and thresholds.

```python
@dataclass
class HandlerConfig:
    lead_agent: str          # Default: anthropic:claude-opus-4-6
    drafter_agent: str       # Default: anthropic:claude-haiku-4-5-20251008
    max_iterations: int      # Default: 3
    pass_threshold: int      # Default: 80 (0-100)
    max_tokens: int | None   # Default: None (provider default)
    fail_on_truncation: bool # Default: True
    check_truncation: bool   # Default: True
    strict_truncation: bool  # Default: False
    test_timeout_seconds: int         # Default: 120
    review_temperature: float         # Default: 0.0
    review_max_code_chars: int        # Default: 8000
    development_timeout_seconds: float | None  # Default: None
```

### 3-Tier Priority Chain

Configuration is resolved via:

1. **CLI overrides** (highest priority) -- `--lead-agent`, `--drafter-agent`, etc.
2. **Config file / environment** -- via `ConfigManager.get_artisan_setting()`
3. **Dataclass defaults** (lowest priority)

```python
config = HandlerConfig.from_config(cli_overrides={"lead_agent": "anthropic:claude-sonnet-4-5-20250929"})
```

### WorkflowConfig

The orchestrator itself is configured via `WorkflowConfig`:

```python
config = WorkflowConfig(
    dry_run=False,
    cost_budget=10.0,             # Max USD across all phases
    total_timeout_seconds=3600,   # 1 hour wall-clock limit
    phase_timeout_seconds=600,    # 10 min per phase
    max_retries_per_phase=1,
    checkpoint_dir="out/checkpoints",
    project_root="/path/to/project",
)
```

---

## Context Seed

The artisan workflow consumes an **enriched context seed** -- a JSON file produced by the PlanIngestionWorkflow and DomainPreflightWorkflow. Each task in the seed contains:

| Field | Description |
|-------|-------------|
| `task_id` | Unique identifier (e.g., `TASK-001`) |
| `title` | Human-readable task title |
| `description` | Detailed task description |
| `target_files` | List of files to generate/modify |
| `estimated_loc` | Estimated lines of code |
| `domain` | Detected domain (e.g., `python-package-module`) |
| `environment_checks` | Pre-flight check results |
| `prompt_constraints` | Constraints for code generation |
| `post_generation_validators` | Validators to run after generation |
| `depends_on` | Task dependency IDs |

Tasks with failing environment checks are automatically skipped by the DESIGN and IMPLEMENT handlers.

---

## Cost Model

The artisan workflow defines a 3-tier model architecture:

| Role | Catalog Default | Purpose | Relative Cost |
|------|----------------|---------|---------------|
| **Drafter** | `claude-haiku-4-5-20251008` | Generate initial drafts cheaply | Low |
| **Validator** | `claude-sonnet-4-5-20250929` | Validate and refine | Medium |
| **Reviewer** | `claude-opus-4-6` | Independent quality review | High |

The core principle is **cheap drafts, expensive validation**. The drafter generates many attempts cheaply while the validator and reviewer ensure quality.

> **Runtime defaults vs catalog defaults:** The `HandlerConfig` exposes two agent roles: `lead_agent` (defaults to Opus) and `drafter_agent` (defaults to Haiku). In the artisan orchestrator, `lead_agent` serves both the validator and reviewer roles — so the default runtime behavior is **2-tier** (Opus + Haiku). The Sonnet validator tier is the default for standalone `LeadContractorCodeGenerator` usage and can be activated in the artisan workflow by setting `--lead-agent anthropic:claude-sonnet-4-5-20250929`. The `WorkflowConfig` tracks all three model IDs (`drafter_model`, `validator_model`, `reviewer_model`) for metadata and OTel span attributes regardless of which agents are actually used.

### Budget Enforcement

When `cost_budget` is set, the orchestrator tracks cumulative cost across all phases and halts with `CostBudgetExceededError` when the budget is exceeded. Each phase reports its cost, and the orchestrator accumulates them.

---

## Observability

The orchestrator automatically instruments with OpenTelemetry when available:

- **Root span**: `workflow.{workflow_id}` with budget, timeout, and model attributes
- **Phase spans**: `phase.{phase_name}` with status, cost, and duration attributes
- **Graceful degradation**: No-op spans when `opentelemetry` is not installed

Phase handlers emit their own telemetry for sub-operations (design rounds, code generation, test execution).

---

## Best Practices

1. **Start with dry-run.** Preview the task plan and scaffold before spending LLM tokens.
2. **Use the two-half split** for non-trivial projects. Review design documents before committing to implementation.
3. **Set a cost budget.** The `--cost-budget` flag prevents runaway spending.
4. **Override agents for cost control.** Use `--lead-agent` and `--drafter-agent` to select cheaper models during development.
5. **Check environment first.** Tasks with failing environment checks are auto-skipped. Fix pre-flight issues before running.
6. **Keep the seed current.** If you change target files or project structure, re-run the PlanIngestion and DomainPreflight workflows to regenerate the enriched seed.
7. **Auto-commit is on by default.** Each feature's generated code is committed to git after implementation, giving atomic commits and crash recovery. Use `--no-auto-commit` to review and commit manually.

---

## API Reference

### Orchestrator

```python
from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowResult,
    WorkflowStatus,
    PhaseStatus,
    AbstractPhaseHandler,
)
```

#### ArtisanContractorWorkflow

```python
workflow = ArtisanContractorWorkflow(
    config: WorkflowConfig = None,        # Defaults to WorkflowConfig()
    handlers: dict[WorkflowPhase, AbstractPhaseHandler] = None,
    checkpoint_store: CheckpointStore = None,
    phases: list[WorkflowPhase] = None,   # Defaults to all 7 phases
)

workflow.register_handler(phase, handler)
result: WorkflowResult = workflow.execute(
    context={"enriched_seed_path": "..."},
    resume_from_checkpoint=False,
)
```

#### WorkflowPhase

```python
WorkflowPhase.PLAN      # "plan"
WorkflowPhase.SCAFFOLD   # "scaffold"
WorkflowPhase.DESIGN     # "design"
WorkflowPhase.IMPLEMENT  # "implement"
WorkflowPhase.TEST       # "test"
WorkflowPhase.REVIEW     # "review"
WorkflowPhase.FINALIZE   # "finalize"

WorkflowPhase.ordered()          # All 7 in order
WorkflowPhase.from_value("design")  # Parse from string
```

### Context Seed Handlers

```python
from startd8.contractors.context_seed_handlers import ContextSeedHandlers

handlers = ContextSeedHandlers.create_all(
    enriched_seed_path="path/to/seed.json",
    output_dir="out/results",
    lead_agent="anthropic:claude-opus-4-6",
    drafter_agent="anthropic:claude-haiku-4-5-20251008",
    max_iterations=3,
    pass_threshold=80,
)
# Returns: dict[WorkflowPhase, AbstractPhaseHandler]
```

### Design Handoff

```python
from startd8.contractors.handoff import (
    write_design_handoff,
    load_design_handoff,
    HandoffData,
    DESIGN_HANDOFF_FILENAME,  # "design-handoff.json"
    SCHEMA_VERSION,           # 1
)

# Write
path: Path = write_design_handoff(
    output_dir="out/designs",
    enriched_seed_path="/abs/path/to/seed.json",
    project_root="/abs/path/to/project",
    workflow_id="abc-123",
    completed_phases=["plan", "scaffold", "design"],
    design_results={...},
    scaffold={...},
)

# Load (accepts file path or directory)
handoff: HandoffData = load_design_handoff("out/designs")
```

### Exceptions

```python
from startd8.contractors.artisan_contractor import (
    WorkflowError,              # Base exception (carries optional checkpoint)
    WorkflowTimeoutError,       # Total or phase timeout exceeded
    CostBudgetExceededError,    # Cumulative cost > budget
    PhaseExecutionError,        # Phase failed after retries exhausted
)
```

---

## Troubleshooting

### "Context missing 'tasks' and 'enriched_seed_path'"

**Cause:** The implementation half was started without a handoff or seed path.

**Solution:** Provide `--handoff`, `--output-dir`, or `--seed` to the implement-only script.

### "Handoff schema version X is newer than supported"

**Cause:** The handoff file was written by a newer SDK version.

**Solution:** Upgrade the SDK: `pip3 install -e ".[all,dev]"`

### "Seed file not found"

**Cause:** The seed path in the handoff no longer exists (file was moved or deleted).

**Solution:** Use `--seed` to provide the current path, overriding the handoff.

### "Cost budget exceeded"

**Cause:** Cumulative cost across phases exceeded `--cost-budget`.

**Solution:** Increase the budget, use cheaper agent overrides, or reduce the number of tasks.

### Phase stuck or timed out

**Cause:** LLM call taking too long or network issue.

**Solution:** Set `--timeout` for total workflow timeout. Individual phases respect the orchestrator's `phase_timeout_seconds` config. Use `--resume` with `--checkpoint-dir` to continue from the last successful phase.

---

## Related Documentation

- [Implementation Plan](PLAN-artisan-contractor.md) -- Detailed design decisions and triage rounds
- [Model Correction](ARTISAN_MODEL_CORRECTION.md) -- Cost hierarchy correction (Haiku/Sonnet/Opus)
- [Prime Contractor Guide](PRIME_CONTRACTOR_WORKFLOW_GUIDE.md) -- The simpler per-feature workflow
- [Pipeline Workflows](PIPELINE_WORKFLOWS_v1.md) -- Higher-level pipeline orchestration
- [SDK Architecture](SDK_ARCHITECTURE_v1.md) -- Overall SDK architecture
- [Contractors README](../src/startd8/contractors/README.md) -- Protocol-based design and adapters
