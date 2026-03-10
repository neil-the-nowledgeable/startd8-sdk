# Task Density Enrichment — Requirements

> **Version:** 0.1.0
> **Status:** DRAFT
> **Date:** 2026-03-10
> **Scope:** Post-REFINE task-level enrichment to close the density gap between document-level review and per-task seed quality
> **Parent:** [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](./KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) (REQ-KPI-303 extension)
> **Trigger:** [KAIZEN_INVESTIGATION_RUN019](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) §9–10: seed quality score 0.50, density signals flat (0/6 code examples, 0/6 req refs, 0/6 negative scope) despite working REFINE chain

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture](#2-architecture)
3. [Option A — Deterministic Enrichment (REQ-TDE-1xx)](#3-option-a--deterministic-enrichment-req-tde-1xx)
4. [Option B — LLM-Assisted Enrichment (REQ-TDE-2xx)](#4-option-b--llm-assisted-enrichment-req-tde-2xx)
5. [Configuration (REQ-TDE-3xx)](#5-configuration-req-tde-3xx)
6. [Observability (REQ-TDE-4xx)](#6-observability-req-tde-4xx)
7. [Status Dashboard](#7-status-dashboard)
8. [Traceability Matrix](#8-traceability-matrix)
9. [Verification Strategy](#9-verification-strategy)
10. [Cross-References](#10-cross-references)

---

## 1. Problem Statement

### 1.1 The Density Gap

Plan ingestion produces task descriptions that are *present* (above 500 chars after G-1 contract enrichment) but lack *structural richness* — the signals that downstream code generation relies on for quality output:

| Signal | Run-019 | Desired | Why It Matters |
|--------|---------|---------|----------------|
| Code examples | 0/6 | 3-6/6 | Anchors LLM generation to concrete patterns; reduces hallucination |
| Requirement references | 0/6 | 4-6/6 | Enables traceability; downstream REVIEW can validate coverage |
| Negative scope | 0/6 | 3-6/6 | Prevents scope creep; reduces "bonus" code that breaks integration |
| Target files | 0/6 | 5-6/6 | Micro-prime needs output path; absence forces guessing |

### 1.2 Root Cause

REFINE operates at the **document level** — it reviews the plan and produces architectural suggestions. These suggestions flow intact to the DESIGN phase as advisory prompt guidance (Mottainai Rule 6: chain INTACT). But they never modify the seed's per-task `config.task_description`, `config.context.negative_scope`, or `config.context.target_files` fields.

The gap is architectural: no step exists between REFINE and EMIT that maps document-level insights to per-task field enrichment.

### 1.3 Approach: Two Complementary Options

| Option | When | Cost | What It Does |
|--------|------|------|-------------|
| **A: Deterministic** | Always (post-REFINE, pre-EMIT) | 0 LLM calls | Extracts and maps signals from existing pipeline artifacts into task fields |
| **B: LLM-Assisted** | On demand (via kaizen config) | 1 LLM call | Generates rich task descriptions with code examples, API signatures, negative scope |

Option A runs unconditionally as a deterministic pass. Option B is opt-in and runs after A, further enriching tasks that A couldn't fully populate. Both are independently configurable — A can be tuned (thresholds, field selection), B can be enabled/disabled and steered (prompt suffix, target signals).

### 1.4 Constraints

- **No new mandatory LLM calls** — Option A is zero-cost; Option B is opt-in
- **Backward compatible** — enrichment adds fields but never removes or overwrites non-empty existing fields
- **Idempotent** — running enrichment twice produces the same result
- **Observable** — enrichment actions are logged and reflected in the diagnostic report
- **Configurable** — both options have per-field enable/disable and threshold controls

---

## 2. Architecture

### 2.1 Pipeline Position

```
PARSE → ASSESS → TRANSFORM → REFINE → [ENRICH-A] → [ENRICH-B] → EMIT
                                         ↑              ↑
                                     deterministic    LLM (opt-in)
                                     always runs      kaizen config
```

Enrichment runs after REFINE (to consume its suggestions) and before EMIT (to populate seed fields before quality scoring). Both options operate on the task dict list in-place.

### 2.2 Data Sources for Option A

| Source | Available At | What It Provides |
|--------|-------------|-----------------|
| `ParsedFeature.negative_scope` | After PARSE | Per-feature exclusions (currently lost in TRANSFORM) |
| `ParsedFeature.target_files` | After PARSE | File paths (may be empty if plan lacks explicit paths) |
| `ParsedFeature.api_signatures` | After PARSE | Function/method signatures for code example stubs |
| Plan text (raw) | Input | `REQ-*` patterns extractable by regex |
| Feature→task mapping | After TRANSFORM | `task["config"]["context"]["feature_id"]` links task to feature |
| REFINE suggestions | After REFINE | Accepted suggestions with `area`, `rationale`, `placement` |
| `extract_target_files()` | `utils/prime_task_enrichment.py` | 5-tier regex extraction from description text |
| Service metadata | After PARSE | Aggregated `negative_scope` across all features |

### 2.3 Data Sources for Option B

| Source | What It Provides |
|--------|-----------------|
| Task description (current) | Base text for LLM to enrich |
| ParsedFeature context | API signatures, dependencies, protocol info |
| REFINE suggestions (accepted) | Architectural guidance to incorporate |
| Plan text excerpt | Feature-specific section for grounding |

---

## 3. Option A — Deterministic Enrichment (REQ-TDE-1xx)

**Always runs. Zero LLM cost. Extracts and maps signals from existing artifacts.**

### REQ-TDE-100: Negative Scope Forwarding

After TRANSFORM derives tasks from features, the enrichment pass SHALL copy `ParsedFeature.negative_scope` to `task["config"]["context"]["negative_scope"]` for each task whose `feature_id` matches.

**Rule:** Never overwrite a non-empty existing `negative_scope` field.

**Source:** `ParsedFeature.negative_scope` is populated during PARSE (prompt explicitly requests it) but currently dropped during `_derive_tasks_from_features()`.

**Expected impact:** 3-6/6 tasks gain negative scope (depends on PARSE extraction quality).

### REQ-TDE-101: Requirement Reference Injection

For each task, the enrichment pass SHALL scan the plan text for `REQ-*` patterns (using existing `_REQ_PATTERN`) that appear in proximity to the task's feature name or description keywords, and append a `## Requirements References` section to the task description.

**Format:**
```
## Requirements References
- REQ-PI-001: Shared JSON Logger
- REQ-PI-003: gRPC Server Implementation
```

**Rule:** Only inject references that are contextually relevant to the task (appear within the same section or paragraph as the feature name). Never add references already present in the description.

**Proximity heuristic:** Extract plan text within ±500 chars of the feature name mention; collect all `_REQ_PATTERN` matches from that window.

### REQ-TDE-102: Target Files Inference

When `task["config"]["context"]["target_files"]` is empty, the enrichment pass SHALL attempt inference using a 3-tier fallback chain:

1. **Tier 1: ParsedFeature.target_files** — copy from the linked feature if non-empty
2. **Tier 2: Description regex** — apply `extract_target_files()` from `utils/prime_task_enrichment.py`
3. **Tier 3: Convention-based** — derive from task title using project naming conventions (e.g., `"Email Service — gRPC Server"` → `emailservice/email_server.py`)

**Rule:** Never overwrite non-empty target_files. Tier 3 results are tagged as `_inferred: true` in the task context to signal lower confidence.

### REQ-TDE-103: API Signature Code Stubs

When `ParsedFeature.api_signatures` is non-empty for a task's linked feature, the enrichment pass SHALL append a `## API Signatures` section with code-fenced stub examples:

**Format:**
```
## API Signatures
```python
def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via the configured SMTP backend."""
    ...

class EmailService(demo_pb2_grpc.EmailServiceServicer):
    """gRPC service implementation for email operations."""
    ...
```
```

**Rule:** Only append if task description does not already contain `` ``` `` blocks. Limit to 5 signatures per task to avoid description bloat.

### REQ-TDE-104: REFINE Suggestion Mapping

For each accepted REFINE suggestion, the enrichment pass SHALL attempt to map it to one or more tasks using:

1. **Placement field match:** If the suggestion's `placement` field references a file path that matches a task's `target_files`, map to that task
2. **Area match:** If no placement match, map suggestions with `area: "interfaces"` to tasks with API-related titles; `area: "data"` to data model tasks; etc.
3. **Unmapped suggestions:** Append to all tasks as a shared `## Review Guidance` section (truncated to top 3 by severity)

**Format appended to task description:**
```
## Review Guidance (from REFINE)
- [interfaces] Ensure gRPC health check returns HealthCheckResponse, not product IDs
- [validation] Add input validation for email address format
```

**Rule:** Never duplicate suggestions already present in the description.

### REQ-TDE-105: Enrichment Ordering

The deterministic enrichment steps SHALL execute in this order:
1. Negative scope forwarding (REQ-TDE-100) — no dependencies
2. Target files inference (REQ-TDE-102) — no dependencies
3. Requirement reference injection (REQ-TDE-101) — after target files (may use file context)
4. API signature stubs (REQ-TDE-103) — after target files
5. REFINE suggestion mapping (REQ-TDE-104) — after target files (uses file match)

This order ensures each step can build on previous results.

### REQ-TDE-106: No-Clobber Rule

All enrichment operations SHALL follow the no-clobber rule:
- Never overwrite a non-empty field with enrichment data
- Never remove existing content from task descriptions
- Append-only for description text; set-only-if-empty for structured fields
- Log a DEBUG message when skipping enrichment due to existing content

---

## 4. Option B — LLM-Assisted Enrichment (REQ-TDE-2xx)

**Opt-in via kaizen config. One LLM call per task batch. Generates rich descriptions with code examples and structured context.**

### REQ-TDE-200: Enrichment Prompt Generation

When enabled, the enrichment pass SHALL construct a prompt that instructs the LLM to enrich task descriptions with:
1. Code examples (function signatures, class skeletons, usage patterns)
2. Requirement references mapped from the plan
3. Negative scope constraints (explicit "do NOT" instructions)
4. Implementation hints derived from API signatures and dependencies

**Prompt structure:**
```
You are enriching task descriptions for a code generation pipeline.
For each task below, add:
1. A ```python code example showing the expected function/class signature
2. Requirement references (REQ-*) from the plan that this task addresses
3. Negative scope: things this task must NOT do
4. Implementation notes from the API signatures provided

Task descriptions to enrich:
[batch of task descriptions with feature context]

Output format: JSON array of enriched task descriptions, one per task.
```

### REQ-TDE-201: Batch Processing

The LLM enrichment SHALL process tasks in a single batch call (not per-task) to minimize cost. The batch prompt includes:
- All task descriptions (current state, including Option A enrichments)
- Feature context (API signatures, dependencies, negative scope from ParsedFeature)
- Plan excerpt (feature-relevant sections)
- Accepted REFINE suggestions

**Token budget:** The enrichment prompt SHALL respect the same budget enforcement as other phases (`enforce_prompt_budget()` with configurable limit).

### REQ-TDE-202: Selective Enrichment

The LLM enrichment SHALL only target tasks that still lack density signals after Option A:
- Tasks already having code examples AND requirement refs AND negative scope are skipped
- The `TaskDensity` computation from Option A determines which tasks need LLM enrichment

**Skip logging:** Log at INFO level: `"ENRICH-B: skipping N/M tasks (already enriched by Option A)"`

### REQ-TDE-203: Response Parsing and Merge

The LLM response SHALL be parsed and merged into task descriptions following the no-clobber rule (REQ-TDE-106):
- Code examples: append only if task description has no `` ``` `` blocks
- Requirement refs: append only if no `REQ-*` patterns present
- Negative scope: set only if `context.negative_scope` is empty

**Fallback:** If LLM response is unparseable, log WARNING and preserve original task descriptions unchanged. Never fail the pipeline on enrichment parse errors.

### REQ-TDE-204: Agent Configuration

The LLM enrichment SHALL use a configurable agent spec:
- Default: same agent as TRANSFORM phase
- Configurable via `enrich_agent_spec` in kaizen config
- Supports all provider:model formats (e.g., `anthropic:claude-sonnet-4-6`, `ollama:startd8-coder`)

### REQ-TDE-205: Cost Guard

The LLM enrichment SHALL enforce a cost ceiling:
- Default: `$0.10` per enrichment call
- Configurable via `enrich_max_cost_usd` in kaizen config
- If estimated cost exceeds ceiling, skip enrichment and log WARNING

---

## 5. Configuration (REQ-TDE-3xx)

### REQ-TDE-300: Kaizen Config Extension

The `PlanIngestionKaizenConfig` dataclass SHALL be extended with enrichment controls:

```python
@dataclass
class PlanIngestionKaizenConfig:
    # ... existing fields ...

    # Option A: Deterministic enrichment (always runs)
    enrich_negative_scope: bool = True       # REQ-TDE-100
    enrich_requirement_refs: bool = True     # REQ-TDE-101
    enrich_target_files: bool = True         # REQ-TDE-102
    enrich_api_signatures: bool = True       # REQ-TDE-103
    enrich_refine_suggestions: bool = True   # REQ-TDE-104
    enrich_req_proximity_chars: int = 500    # REQ-TDE-101 proximity window

    # Option B: LLM-assisted enrichment (opt-in)
    enrich_llm_enabled: bool = False         # REQ-TDE-200 master switch
    enrich_agent_spec: str = ""              # REQ-TDE-204 agent override
    enrich_max_cost_usd: float = 0.10        # REQ-TDE-205 cost ceiling
    enrich_prompt_suffix: str = ""           # Custom prompt instructions
    enrich_token_budget: int = 4096          # REQ-TDE-201 token limit
```

### REQ-TDE-301: CLI Flag

The workflow SHALL accept `--enrich-llm` flag (or config key `enrich_llm_enabled: true`) to enable Option B. Option A requires no flag — it runs unconditionally unless individual steps are disabled via kaizen config.

### REQ-TDE-302: Kaizen Config JSON Format

```json
{
  "plan_ingestion_kaizen": {
    "enrich_negative_scope": true,
    "enrich_requirement_refs": true,
    "enrich_target_files": true,
    "enrich_api_signatures": true,
    "enrich_refine_suggestions": true,
    "enrich_req_proximity_chars": 500,

    "enrich_llm_enabled": false,
    "enrich_agent_spec": "",
    "enrich_max_cost_usd": 0.10,
    "enrich_prompt_suffix": "",
    "enrich_token_budget": 4096
  }
}
```

All fields are optional with sensible defaults. Unknown keys are silently ignored (existing behavior of `load_kaizen_config()`).

### REQ-TDE-303: Per-Step Disable

Each Option A enrichment step SHALL be independently disableable via its boolean config field. This allows operators to:
- Disable noisy enrichments (e.g., requirement refs producing false positives)
- Benchmark individual step impact on downstream quality
- Work around regressions without disabling all enrichment

---

## 6. Observability (REQ-TDE-4xx)

### REQ-TDE-400: Enrichment Diagnostic Block

The diagnostic report (`plan-ingestion-diagnostic.json`) SHALL include an `enrichment` section:

```json
{
  "enrichment": {
    "option_a": {
      "enabled": true,
      "negative_scope_added": 4,
      "requirement_refs_added": 3,
      "target_files_inferred": 5,
      "api_signatures_added": 2,
      "refine_suggestions_mapped": 6,
      "tasks_enriched": 5,
      "tasks_skipped": 1,
      "time_ms": 12
    },
    "option_b": {
      "enabled": false,
      "tasks_targeted": 0,
      "tasks_enriched": 0,
      "cost_usd": 0.0,
      "time_ms": 0,
      "skipped_reason": "disabled"
    }
  }
}
```

### REQ-TDE-401: Pre/Post Density Comparison

The diagnostic report SHALL include before and after density snapshots:

```json
{
  "density_comparison": {
    "before_enrichment": {
      "code_examples": 0,
      "requirement_refs": 0,
      "negative_scope": 0,
      "target_files": 0,
      "avg_description_chars": 993
    },
    "after_enrichment": {
      "code_examples": 3,
      "requirement_refs": 4,
      "negative_scope": 4,
      "target_files": 5,
      "avg_description_chars": 1247
    }
  }
}
```

### REQ-TDE-402: Seed Quality Score Impact

The `_ingestion_quality` block in the emitted seed SHALL reflect post-enrichment density. Since enrichment runs before `compute_seed_quality()` and `compute_task_density()`, the existing quality scoring infrastructure automatically captures the improvement — no changes needed to the scoring functions.

### REQ-TDE-403: Kaizen Prompt Capture

When Option B is enabled and kaizen prompt capture is active, the enrichment prompt and response SHALL be persisted to:
- `kaizen-prompts/enrich_prompt.txt`
- `kaizen-prompts/enrich_response.txt`

Follows existing `persist_prompt_response()` pattern.

---

## 7. Status Dashboard

| Req ID | Description | Status |
|--------|-------------|--------|
| **Option A — Deterministic Enrichment** | | |
| REQ-TDE-100 | Negative scope forwarding | IMPLEMENTED |
| REQ-TDE-101 | Requirement reference injection | IMPLEMENTED |
| REQ-TDE-102 | Target files inference | IMPLEMENTED (Tier 1+2; Tier 3 deferred) |
| REQ-TDE-103 | API signature code stubs | IMPLEMENTED |
| REQ-TDE-104 | REFINE suggestion mapping | IMPLEMENTED |
| REQ-TDE-105 | Enrichment ordering | IMPLEMENTED |
| REQ-TDE-106 | No-clobber rule | IMPLEMENTED |
| **Option B — LLM-Assisted Enrichment** | | |
| REQ-TDE-200 | Enrichment prompt generation | PLANNED |
| REQ-TDE-201 | Batch processing | PLANNED |
| REQ-TDE-202 | Selective enrichment | PLANNED |
| REQ-TDE-203 | Response parsing and merge | PLANNED |
| REQ-TDE-204 | Agent configuration | PLANNED |
| REQ-TDE-205 | Cost guard | PLANNED |
| **Configuration** | | |
| REQ-TDE-300 | Kaizen config extension | IMPLEMENTED |
| REQ-TDE-301 | CLI flag | PLANNED (Option B only) |
| REQ-TDE-302 | Kaizen config JSON format | IMPLEMENTED |
| REQ-TDE-303 | Per-step disable | IMPLEMENTED |
| **Observability** | | |
| REQ-TDE-400 | Enrichment diagnostic block | IMPLEMENTED |
| REQ-TDE-401 | Pre/post density comparison | IMPLEMENTED (via test_pre_post_density_snapshot) |
| REQ-TDE-402 | Seed quality score impact | IMPLEMENTED (automatic — enrichment runs before scoring) |
| REQ-TDE-403 | Kaizen prompt capture | PLANNED (Option B only) |

---

## 8. Traceability Matrix

| Run-019 Finding | Requirements | How It's Addressed |
|----------------|-------------|-------------------|
| 0/6 code examples | REQ-TDE-103, REQ-TDE-200 | A: API signature stubs from ParsedFeature; B: LLM generates full examples |
| 0/6 requirement refs | REQ-TDE-101, REQ-TDE-200 | A: Regex extraction from plan text; B: LLM maps refs to tasks |
| 0/6 negative scope | REQ-TDE-100, REQ-TDE-200 | A: Forward from ParsedFeature (already parsed); B: LLM derives from context |
| 0/6 target files | REQ-TDE-102 | A: 3-tier inference (feature→regex→convention) |
| Seed quality 0.50 | REQ-TDE-402 | Enrichment populates density signals → score increases automatically |
| REFINE suggestions unused in tasks | REQ-TDE-104 | A: Map suggestions to tasks by placement/area; append as review guidance |
| Flat density despite working REFINE | All REQ-TDE-1xx | A bridges the document→task gap deterministically |

### Kaizen Requirements Cross-Reference

| Kaizen Req | TDE Req | Relationship |
|-----------|---------|-------------|
| REQ-KPI-302 | REQ-TDE-402 | Enrichment improves seed quality score by populating depth+richness signals |
| REQ-KPI-303 | REQ-TDE-100–104 | Enrichment directly populates the density fields that KPI-303 measures |
| REQ-KPI-500 | REQ-TDE-300 | Enrichment config extends the kaizen config dataclass |
| REQ-KPI-600 | REQ-TDE-401 | Density comparison in diagnostic surfaces enrichment impact downstream |

---

## 9. Verification Strategy

### Option A Tests

| Test | What | Type |
|------|------|------|
| `test_negative_scope_forwarded` | Feature with `negative_scope: ["no auth"]` → task context has it | Unit |
| `test_negative_scope_no_clobber` | Task with existing negative_scope → not overwritten | Unit |
| `test_requirement_refs_extracted` | Plan text with `REQ-PI-003` near feature name → appended to description | Unit |
| `test_requirement_refs_proximity` | REQ-* 1000 chars away from feature → not included | Unit |
| `test_target_files_tier1` | Feature has target_files → copied to task | Unit |
| `test_target_files_tier2` | Description mentions `emailservice/server.py` → extracted | Unit |
| `test_target_files_tier3` | Title "Email Service — gRPC Server" → `emailservice/email_server.py` inferred | Unit |
| `test_api_signatures_appended` | Feature has `api_signatures` → code block in description | Unit |
| `test_api_signatures_skip_existing` | Description already has `` ``` `` → no code block added | Unit |
| `test_refine_suggestions_mapped` | Suggestion with `placement: emailservice/server.py` → mapped to matching task | Unit |
| `test_enrichment_ordering` | Steps execute in specified order | Unit |
| `test_all_steps_disabled` | All config booleans False → no enrichment | Unit |
| `test_idempotent` | Running enrichment twice → same result | Unit |

### Option B Tests

| Test | What | Type |
|------|------|------|
| `test_llm_enrichment_disabled_by_default` | No config → no LLM call | Unit |
| `test_llm_enrichment_enabled` | Config `enrich_llm_enabled: true` → LLM called | Unit |
| `test_selective_skip` | Task already enriched by A → skipped for B | Unit |
| `test_cost_guard_blocks` | Estimated cost > ceiling → skipped with WARNING | Unit |
| `test_unparseable_response` | Bad LLM response → original descriptions preserved | Unit |
| `test_prompt_capture` | Kaizen enabled → prompt/response written to kaizen-prompts/ | Unit |

### Integration Tests

| Test | What | Type |
|------|------|------|
| `test_density_score_improvement` | Seed quality score increases after enrichment | Integration |
| `test_density_warnings_reduced` | Density warnings decrease after enrichment | Integration |
| `test_online_boutique_enrichment` | Run-019 plan → enrichment adds signals to all 6 tasks | Integration |

---

## 10. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](./KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Parent: REQ-KPI-302, 303, 500, 600 |
| [KAIZEN_INVESTIGATION_RUN019](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Trigger: §9 seed analysis, §10 REFINE investigation |
| [REFINE_FORWARDING_REQUIREMENTS.md](../../REFINE_FORWARDING_REQUIREMENTS.md) | Related: REQ-RF-001–012 (REFINE→seed chain) |
| `utils/prime_task_enrichment.py` | Reuse: `extract_target_files()` for REQ-TDE-102 Tier 2 |
| `plan_ingestion_diagnostics.py` | Integration: `compute_task_density()`, `compute_density_warnings()` |
| `plan_ingestion_workflow.py` | Implementation target: enrichment pass between REFINE and EMIT |
| SDK Lessons: Leg 13 #33 | Requirements layer gap — data injection ≠ prompt consumption |
| SDK Lessons: Leg 13 #40 | 12-point pipeline field threading checklist |
