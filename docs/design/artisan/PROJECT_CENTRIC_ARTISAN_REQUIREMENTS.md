# Project-Centric Artisan (PCA) Requirements

> **Version:** 1.2.0
> **Status:** Draft
> **Date:** 2026-02-21
> **Scope:** Artisan 8-phase pipeline context propagation, checkpoint persistence, prompt enrichment, and edit-first behavior

---

## Table of Contents

1. [Design Principle](#1-design-principle)
2. [Gap Analysis](#2-gap-analysis)
3. [Requirements](#3-requirements)
   - [Layer 1: Context Injection (PCA-1xx)](#layer-1-context-injection-pca-1xx)
   - [Layer 2: Checkpoint Persistence (PCA-2xx)](#layer-2-checkpoint-persistence-pca-2xx)
   - [Layer 3: Prompt Enrichment (PCA-3xx)](#layer-3-prompt-enrichment-pca-3xx)
   - [Layer 4: Cross-Phase Propagation (PCA-4xx)](#layer-4-cross-phase-propagation-pca-4xx)
   - [Layer 5: Edit-First Behavior (PCA-5xx)](#layer-5-edit-first-behavior-pca-5xx)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Traceability Matrix](#5-traceability-matrix)
6. [Priority Phasing](#6-priority-phasing)
7. [Contract YAML Amendments](#7-contract-yaml-amendments)
8. [Cross-References](#8-cross-references)
9. [Status Dashboard](#9-status-dashboard)
10. [Related Documents](#10-related-documents)

---

## 1. Design Principle

**The Artisan pipeline should assume a project-centric default.**

The cap-dev-pipe embeds into the target project (`.cap-dev-pipe/` symlinks + `pipeline.env`) and invokes the SDK from within the project it is updating. The pipeline IS the project. Every phase — PLAN through FINALIZE (including the INTEGRATE phase between IMPLEMENT and TEST) — should have access to the same project-level context that the Prime Contractor injects into every feature's code generation prompt.

The Prime Contractor attaches seed-level context (`onboarding`, `architectural_context`, `design_calibration`, `service_metadata`, `plan_document_text`) directly to its workflow instance and injects all of it into every `gen_context` dict (lines 585–662 of `prime_contractor.py`). The Artisan pipeline distributes the same data across a multi-phase boundary where it **attenuates** — onboarding fields are lost on checkpoint resume, `service_metadata` never reaches IMPLEMENT or REVIEW prompts, and project-level framing is absent from code generation and review prompts.

This document specifies 20 requirements to close that gap.

---

## 2. Gap Analysis

### Gap 1: `initial_context` Missing `project_root`

**Evidence:** `scripts/run_artisan_workflow.py` line 793–805

```python
initial_context: dict[str, Any] = {
    "enriched_seed_path": str(seed_path.resolve()),
}
# project_root is NEVER set here
```

`WorkflowConfig.project_root` is set (line 701) but is NOT injected into `initial_context`. The contract YAML declares `project_root` as a **blocking** entry requirement for PLAN phase. Downstream phases fall back to `Path(".")` via `context.get("project_root", ".")`, which is fragile and incorrect when the working directory differs from the project root.

`_CHECKPOINT_CONTEXT_KEYS` includes `"project_root"` (line 141 of `artisan_contractor.py`) so it WOULD be persisted IF it were in context — but it never gets there.

**Impact:** All path resolution in IMPLEMENT, TEST, REVIEW, and FINALIZE phases is relative to `"."` instead of the actual project root.

---

### Gap 2: Onboarding Fields Not in Checkpoint Persistence

**Evidence:** `artisan_contractor.py` lines 138–150 vs `context_seed_handlers.py` lines 855–872

`_CHECKPOINT_CONTEXT_KEYS` (22 keys) does NOT include:

| Missing Key | Set by PlanPhaseHandler | Line |
|---|---|---|
| `onboarding_derivation_rules` | `_onboarding.get("derivation_rules")` | 856 |
| `onboarding_resolved_parameters` | `_onboarding.get("resolved_artifact_parameters")` | 857 |
| `onboarding_output_contracts` | `_onboarding.get("expected_output_contracts")` | 860 |
| `onboarding_calibration_hints` | `_onboarding.get("design_calibration_hints")` | 863 |
| `onboarding_open_questions` | `_onboarding.get("open_questions")` | 866 |
| `onboarding_dependency_graph` | `_onboarding.get("artifact_dependency_graph")` | 868 |
| `service_metadata` | `_onboarding.get("service_metadata")` | 872 |
| `plan_document_text` | loaded from `artifacts.plan_document_path` | 890–906 |

These 8 keys are populated in PLAN phase but **lost on checkpoint resume**. `_ensure_context_loaded()` (line 559) does NOT re-extract them — it only restores `tasks`, `task_index`, `plan_title`, `plan_goals`, and Phase 2 data flow keys (lines 643–649).

**Impact:** Any checkpoint resume after PLAN (e.g., resuming from IMPLEMENT) silently loses all onboarding-derived context. Phases that depend on these fields operate with empty/None values.

---

### Gap 3: Artisan Generic Prompts vs. Prime Project-Contextual Prompts

**Evidence:** `development.py` `_build_prompt()` lines 542–602 vs `prime_contractor.py` `gen_context` lines 585–662

Prime Contractor injects into every feature's `gen_context`:

| Field | Prime (line) | Artisan `_build_prompt` |
|---|---|---|
| `project_objectives` | 604–606 | **Absent** |
| `architectural_context` | 610–611 | In context dict but NOT in prompt |
| `plan_context` | 617–618 | **Absent** |
| `requirements_text` | 620–621 | **Absent** |
| `service_metadata` | 623–624 | In context dict but NOT in prompt |
| `critical_parameters` | 654 | **Absent** |
| `resolved_parameters` | 655 | **Absent** |
| `prior_error_feedback` | 658–661 | Has `last_error`/`test_output` (less structured) |

Artisan's `_build_prompt()` assembles from:
1. `chunk.implementation_prompt` (which is `task.description` — a bare task description, line 3097)
2. `context["domain_constraints"]` (optional)
3. `context["project_context"]` (optional, rarely set)
4. `chunk.file_targets` (list)
5. `context["last_error"]` / `context["test_output"]` (retry only)

**Impact:** The LLM generating code in IMPLEMENT phase has no awareness of project objectives, architecture, service metadata, or the original plan — producing code that is technically correct but architecturally misaligned. (Note: IMPLEMENT now writes to a staging directory; the INTEGRATE phase merges staged files into `project_root`. The prompt enrichment gap still applies to IMPLEMENT's LLM prompts.)

---

### Gap 4: No Project-Level System Prompt in Artisan Review

**Evidence:** `context_seed_handlers.py` `ReviewPhaseHandler` lines 4718–4750

```python
REVIEW_PROMPT_TEMPLATE = """You are reviewing generated code for quality and correctness.
## Task
**ID:** {task_id}
**Title:** {title}
...
```

The reviewer has no project-level framing. Compare with Prime Contractor's review prompt (via `lead_contractor.yaml`) which includes the original task specification with project context, architectural constraints, and service metadata.

The review prompt does inject design compliance (line 4846), parameter sources (line 4875), semantic conventions (line 4881), and truncation warnings (line 4894) — but no `project_objectives`, `architectural_context`, `plan_context`, or `service_metadata`.

**Impact:** The reviewer cannot check whether implementations satisfy project-level constraints (e.g., "all healthcheck endpoints must match transport protocol") because it doesn't know what those constraints are.

---

### Gap 5: Service Metadata Not Consumed After DESIGN

**Evidence:** `context_seed_handlers.py` `_tasks_to_chunks()` lines 3092–3127

Prime Contractor injects `service_metadata` into every feature's `gen_context` (line 623). Artisan's DESIGN phase can access it via `_task_to_feature_context` (it's in `additional_context`). But IMPLEMENT, TEST, and REVIEW phases do NOT receive `service_metadata`:

- `_tasks_to_chunks()` metadata dict (lines 3100–3126) does NOT include `service_metadata`
- `_build_prompt()` (lines 542–602) does NOT read `service_metadata`
- `ReviewPhaseHandler._build_review_prompt()` (lines 4789–4868) does NOT accept `service_metadata`

The IMP-7 validation (DESIGN→IMPLEMENT parameter completeness) checks for parameter presence but doesn't inject `service_metadata` into the actual code generation prompt.

**Impact:** Generated code may add capabilities the service doesn't use, or produce healthcheck mechanisms that don't match the declared transport protocol.

---

### Gap 6: Cross-Feature Context Accumulation

**Evidence:** `context_seed_handlers.py` `DesignPhaseHandler` line 1267 vs `_tasks_to_chunks()` lines 2703–3127

The DESIGN phase accumulates `prior_design_summaries` (up to 5) for cross-task awareness. The IMPLEMENT phase has **no equivalent**:

- Prime Contractor sees prior features' generated code on disk (sequential execution within `project_root`)
- Artisan's `_tasks_to_chunks()` creates all chunks from seed tasks with no inter-chunk context
- No mechanism to accumulate learned conventions or corrections across features

**Impact:** Later features in a batch may repeat mistakes or violate conventions established by earlier features. The LLM cannot learn from its own prior outputs within the same pipeline run.

---

## 3. Requirements

### Layer 1: Context Injection (PCA-1xx)

---

#### PCA-100: Inject `project_root` into `initial_context`

- **Priority:** P0
- **Closes:** Gap 1
- **Overlaps:** AR-100 (Seed Loading)

`run_artisan_workflow.py` sets `WorkflowConfig.project_root` (line 701) but does NOT inject it into `initial_context` (line 793). Downstream phases fall back to `Path(".")`.

**Acceptance Criteria:**

1. `initial_context["project_root"]` is set to `str(Path(args.project_root).resolve())` at line 793 of `run_artisan_workflow.py`.
2. `PlanPhaseHandler.execute()` does NOT overwrite `project_root` if it is already present in context (preserves the caller's value).
3. `ScaffoldPhaseHandler`, `ImplementPhaseHandler`, `FinalizePhaseHandler` all use `context["project_root"]` rather than `context.get("project_root", ".")`.
4. The `artisan-pipeline.contract.yaml` plan.entry.required `project_root` field (already declared at severity: blocking) passes validation.

**Source files:** `scripts/run_artisan_workflow.py`, `src/startd8/contractors/context_seed_handlers.py`

---

#### PCA-101: Forward `service_metadata` from Seed to Context

- **Priority:** P0 (propagation to downstream phases is PCA-400)
- **Status:** Implemented (PLAN phase, line 872)
- **Closes:** Gap 5 (partially — injection exists, consumption is PCA-400/PCA-303)
- **Overlaps:** AR-144, AR-147

`service_metadata` is correctly extracted from the onboarding section of the seed and placed into context by `PlanPhaseHandler` (line 872). However, it is not in `_CHECKPOINT_CONTEXT_KEYS` (see PCA-200) and is not consumed after the DESIGN phase (see PCA-400, PCA-303).

**Acceptance Criteria:**

1. `context["service_metadata"]` is populated by `PlanPhaseHandler.execute()` from `seed_data["onboarding"]["service_metadata"]`. (Already true.)
2. Value is `None` when the onboarding section does not contain `service_metadata` (not an empty dict — maintain existing behavior).

**Source files:** `src/startd8/contractors/context_seed_handlers.py`

---

#### PCA-102: Forward `plan_document_text` from Seed to Context

- **Priority:** P0 (propagation to downstream phases is PCA-401)
- **Status:** Implemented (PLAN phase, lines 890–906)
- **Closes:** Gap 5 (partially)
- **Overlaps:** AR-903 (Metadata Forwarding)

`plan_document_text` is loaded by `PlanPhaseHandler` (lines 890–906) from the seed's `artifacts.plan_document_path`. However, it is not in `_CHECKPOINT_CONTEXT_KEYS` (PCA-202) and not consumed by IMPLEMENT (PCA-401).

**Acceptance Criteria:**

1. `context["plan_document_text"]` is populated by `PlanPhaseHandler.execute()` when `artifacts.plan_document_path` resolves to a readable file. (Already true.)
2. On resume, `_ensure_context_loaded()` re-extracts this field (see PCA-201).

**Source files:** `src/startd8/contractors/context_seed_handlers.py`

---

#### PCA-103: Forward All Onboarding Fields from Seed to Context

- **Priority:** P1
- **Status:** Implemented (PLAN phase, lines 855–885)
- **Closes:** Gap 2 (partially — persistence is PCA-200/201)
- **Overlaps:** AR-303..AR-308

Six onboarding fields are extracted by `PlanPhaseHandler`: `onboarding_derivation_rules`, `onboarding_resolved_parameters`, `onboarding_output_contracts`, `onboarding_calibration_hints`, `onboarding_open_questions`, `onboarding_dependency_graph`. These are consumed by `DesignPhaseHandler._task_to_feature_context()` for inventory fallback but are lost on checkpoint resume.

**Acceptance Criteria:**

1. All six fields are present in context after `PlanPhaseHandler.execute()`. (Already true.)
2. All six fields survive checkpoint resume (see PCA-200, PCA-201).
3. At least `onboarding_calibration_hints` and `onboarding_dependency_graph` are consumed by IMPLEMENT (see PCA-401) for implementation-time calibration.

**Source files:** `src/startd8/contractors/context_seed_handlers.py`

---

#### PCA-104: Log Context Injection Completeness at Phase Entry

- **Priority:** P1

Each phase handler should log a structured summary of which project-level context fields are present vs. missing at entry. This enables debugging of context propagation failures without requiring checkpoint inspection.

**Acceptance Criteria:**

1. At the start of `execute()` in SCAFFOLD, DESIGN, IMPLEMENT, INTEGRATE, TEST, REVIEW, and FINALIZE handlers, log an INFO message listing: `project_root` (present/absent), `service_metadata` (present/absent), `plan_document_text` (present/absent), `architectural_context` (present/absent), `onboarding_*` field count (N/6).
2. If fewer than 3 of the 10 project-level context fields are present, log a WARNING: `"Degraded project context: only N/10 fields available — code quality may be reduced."`
3. For INTEGRATE, the logging is advisory — the phase has no LLM prompts and consumes no tokens, but completeness logging provides a consistent diagnostic signal across all 8 phases.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (all handlers)

---

#### PCA-105: `WorkflowConfig.project_root` Propagation to Context

- **Priority:** P0
- **Closes:** Gap 1 (defense-in-depth)

As a defense-in-depth complement to PCA-100, the `ArtisanContractorWorkflow.execute()` method should inject `config.project_root` into the context dict if not already present. This ensures `project_root` is available even when scripts other than `run_artisan_workflow.py` invoke the workflow.

**Acceptance Criteria:**

1. `ArtisanContractorWorkflow.execute()` calls `context.setdefault("project_root", self.config.project_root)` before invoking the first phase handler, but only when `self.config.project_root` is not `None`.
2. Existing `context["project_root"]` values are NOT overwritten (script-level takes precedence over config-level).

**Source files:** `src/startd8/contractors/artisan_contractor.py`

---

### Layer 2: Checkpoint Persistence (PCA-2xx)

---

#### PCA-200: Expand `_CHECKPOINT_CONTEXT_KEYS` with Onboarding and Service Fields

- **Priority:** P0
- **Closes:** Gap 2
- **Overlaps:** AR-505 (Checkpoint Schema), AR-903 (Metadata Forwarding)

`_CHECKPOINT_CONTEXT_KEYS` (line 138–150 of `artisan_contractor.py`) is a frozen set that controls which context keys are serialized into checkpoint JSON. Eight project-level fields are missing.

**Acceptance Criteria:**

1. `_CHECKPOINT_CONTEXT_KEYS` includes all of the following additional keys:
   - `"onboarding_derivation_rules"`
   - `"onboarding_resolved_parameters"`
   - `"onboarding_output_contracts"`
   - `"onboarding_calibration_hints"`
   - `"onboarding_open_questions"`
   - `"onboarding_dependency_graph"`
   - `"service_metadata"`
   - `"plan_document_text"`
2. Existing checkpoint files (without these keys) load without error (backward compatibility).
3. A round-trip test verifies: `context -> checkpoint -> restore -> context` preserves all eight new fields.
4. `plan_document_text` is truncated to 100K characters in the checkpoint to prevent oversized checkpoint files (plans can be large). On restore, the full text is re-loaded from the seed file via PCA-201.

**Source files:** `src/startd8/contractors/artisan_contractor.py` (line 138)

---

#### PCA-201: Extend `_ensure_context_loaded()` to Re-Extract Onboarding Fields

- **Priority:** P0
- **Closes:** Gap 2 (defense-in-depth)
- **Overlaps:** AR-903

`_ensure_context_loaded()` (line 559) re-reads the seed file on checkpoint resume to rebuild `tasks`, `task_index`, `plan_title`, etc. It currently re-extracts `source_checksum`, `parameter_sources`, `semantic_conventions`, `output_conventions`, `architectural_context`, and `design_calibration` via `context.setdefault()` (lines 643–649). It does NOT re-extract the onboarding fields or `plan_document_text`.

**Acceptance Criteria:**

1. `_ensure_context_loaded()` adds `context.setdefault()` calls for all eight fields listed in PCA-200, extracting from the same seed paths as `PlanPhaseHandler` (lines 855–906):
   ```python
   _onboarding = seed_data.get("onboarding") or {}
   context.setdefault("onboarding_derivation_rules", _onboarding.get("derivation_rules"))
   context.setdefault("onboarding_resolved_parameters", _onboarding.get("resolved_artifact_parameters"))
   context.setdefault("onboarding_output_contracts", _onboarding.get("expected_output_contracts"))
   context.setdefault("onboarding_calibration_hints", _onboarding.get("design_calibration_hints"))
   context.setdefault("onboarding_open_questions", _onboarding.get("open_questions"))
   context.setdefault("onboarding_dependency_graph", _onboarding.get("artifact_dependency_graph"))
   context.setdefault("service_metadata", _onboarding.get("service_metadata"))
   # Re-load plan_document_text from artifacts.plan_document_path if absent
   ```
2. Re-extraction is logged at INFO level: `"Restored N/8 onboarding fields from seed on resume."`
3. Fields already present in context from checkpoint are NOT overwritten (`setdefault` semantics preserved).

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (line 559)

---

#### PCA-202: Checkpoint Size Guard for `plan_document_text`

- **Priority:** P1

`plan_document_text` can be large (50K+ characters for complex plans). Storing it verbatim in every checkpoint JSON would inflate checkpoint files.

**Acceptance Criteria:**

1. When serializing context to checkpoint, `plan_document_text` is stored as a truncated summary (first 1000 chars + `"... [truncated, full text in seed]"`) rather than the full text.
2. On restore, the full `plan_document_text` is re-loaded from the seed via PCA-201, not from the truncated checkpoint value.
3. A sentinel value (e.g., `_plan_doc_truncated: true`) is included in the checkpoint so restore logic can distinguish truncated from absent.

**Source files:** `src/startd8/contractors/artisan_contractor.py`

---

#### PCA-203: Checkpoint Schema Version Compatibility

- **Priority:** P0
- **Overlaps:** AR-511 (Schema Versioning)

Adding new context keys to checkpoints constitutes a schema evolution. Existing v4 checkpoints lacking these keys must be loadable.

**Acceptance Criteria:**

1. `CHECKPOINT_SCHEMA_VERSION` remains at 4 (no version bump needed) because the new keys are optional and handled via `setdefault` semantics on load. The checkpoint contract already tolerates absent keys for optional context.
2. Migration test: a v4 checkpoint WITHOUT the new keys loads successfully, and `_ensure_context_loaded()` fills the missing fields from the seed.

**Source files:** `src/startd8/contractors/artisan_contractor.py`

---

### Layer 3: Prompt Enrichment (PCA-3xx)

---

#### PCA-300: IMPLEMENT Phase Project Architecture Injection

- **Priority:** P0
- **Closes:** Gap 4 (partially)
- **Overlaps:** AR-131 (Design Injection), AR-903 (Metadata Forwarding)

The IMPLEMENT phase passes `task.description` as the `implementation_prompt` (line 3097) with no project-level framing. The Prime Contractor injects `architectural_context`, `project_objectives`, and `plan_context` into every feature's `gen_context` (lines 604–618). The Artisan IMPLEMENT phase should do the same.

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects the following into `DevelopmentChunk.metadata`:
   - `"architectural_context"`: from `context.get("architectural_context", {})` — filtered to objectives, constraints, and shared_modules relevant to the task's target files (same filtering as `DesignPhaseHandler._task_to_feature_context`).
   - `"plan_goals"`: from `context.get("plan_goals", [])` — first 5 goals.
   - `"plan_context"`: from `context.get("plan_document_text")` — truncated to 4000 chars for prompt budget.
2. `DevelopmentPhase._build_prompt()` (line 542) assembles these into the prompt:
   - A `## Project Architecture` section is added after `## Domain Constraints` if `architectural_context` is present in chunk metadata.
   - A `## Project Goals` subsection is added if `plan_goals` are present.
3. Prompt size is bounded: combined injection does not exceed 6000 characters. Excess is truncated with a `... [truncated for prompt budget]` marker.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`, line 2703), `src/startd8/contractors/artisan_phases/development.py` (`_build_prompt`, line 542)

---

#### PCA-301: IMPLEMENT Phase Service Metadata Injection

- **Priority:** P0
- **Closes:** Gap 5
- **Overlaps:** AR-144, AR-147

The Prime Contractor injects `service_metadata` into every feature's `gen_context` (line 623). The Artisan IMPLEMENT phase does NOT inject it into `DevelopmentChunk.metadata`.

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `"service_metadata"` from `context.get("service_metadata")` into `DevelopmentChunk.metadata`.
2. `DevelopmentPhase._build_prompt()` adds a `## Service Metadata` section when `service_metadata` is present, including:
   - `transport_protocol` (if present)
   - `runtime_dependencies` (if present)
   - A directive: *"HEALTHCHECK type MUST match transport_protocol. Do NOT add capabilities the service does not use."*
3. The injection is conditional: no section is added when `service_metadata` is `None` or empty dict.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`), `src/startd8/contractors/artisan_phases/development.py` (`_build_prompt`)

---

#### PCA-302: REVIEW Phase Project-Level System Prompt

- **Priority:** P0
- **Closes:** Gap 4 (REVIEW)
- **Overlaps:** AR-150 (LLM Review)

The REVIEW phase uses a generic system prompt: `"You are reviewing generated code for quality and correctness."` (line 4718). The Prime Contractor's review prompt includes the original task specification with project context. The Artisan reviewer should have project-level awareness.

**Acceptance Criteria:**

1. `ReviewPhaseHandler._build_review_prompt()` gains a `project_context` parameter that is formatted into the review prompt as a `## Project Context` section containing:
   - `plan_title` (1 line)
   - `plan_goals` (bulleted, max 5)
   - `architectural_context.objectives` (max 3)
   - `architectural_context.constraints` (max 5)
2. The `execute()` method of `ReviewPhaseHandler` passes project context from the workflow context dict.
3. Prompt budget: the `## Project Context` section is capped at 2000 characters.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ReviewPhaseHandler`, line 4700)

---

#### PCA-303: REVIEW Phase Service Metadata Compliance Check

- **Priority:** P1
- **Closes:** Gap 5 (REVIEW)
- **Overlaps:** AR-144, AR-907 (Guidance Compliance)

When `service_metadata` is present, the REVIEW prompt should instruct the reviewer to check compliance with transport protocol and runtime dependency declarations.

**Acceptance Criteria:**

1. When `service_metadata` is not None, `_build_review_prompt()` appends a `## Service Metadata Compliance` section containing:
   - Expected `transport_protocol` (if declared)
   - Expected `runtime_dependencies` (if declared)
   - Instruction: *"Check that HEALTHCHECK mechanism matches transport_protocol. Flag any capabilities added that the service metadata declares as absent."*
2. When `service_metadata` is None, no additional section is added.
3. `context.get("service_metadata")` is read in `ReviewPhaseHandler.execute()` and forwarded to `_build_review_prompt()`.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ReviewPhaseHandler._build_review_prompt`, line 4789)

---

#### PCA-304: TEST Phase Service Metadata Forwarding

- **Priority:** P1
- **Closes:** Gap 5 (TEST)
- **Overlaps:** AR-144, AR-147

The TEST phase handlers (`TestPhaseHandler` / `FinalizePhaseHandler`) already call `validate_protocol_fidelity()` and `validate_dockerfile_coherence()` from `self_consistency.py`, passing `service_metadata` from `context.get("service_metadata")`. This dependency is already implemented. PCA-304 formalizes the requirement and ensures it survives resume via PCA-200/201.

**Acceptance Criteria:**

1. `context.get("service_metadata")` is available in TEST/FINALIZE phase handlers. (Depends on PCA-200/201 for resume.)
2. When `service_metadata` is absent (None), validators gracefully skip transport/dependency checks (already true per `self_consistency.py`).

**Source files:** `src/startd8/contractors/context_seed_handlers.py`

---

### Layer 4: Cross-Phase Propagation (PCA-4xx)

---

#### PCA-400: Service Metadata Propagation to IMPLEMENT Chunks

- **Priority:** P0
- **Closes:** Gap 5 (IMPLEMENT)
- **Overlaps:** AR-903 (Compute-But-Don't-Forward)

Formalizes the injection from PCA-301 at the chunk metadata level. PCA-301 specifies prompt enrichment; PCA-400 specifies data propagation.

**Acceptance Criteria:**

1. Each `DevelopmentChunk` created by `_tasks_to_chunks()` includes `metadata["service_metadata"]` set to `context.get("service_metadata")`.
2. The value is the full `service_metadata` dict (not a subset), consistent with Prime Contractor behavior (line 624).
3. When `service_metadata` is None, the metadata key is omitted (not set to None).

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`)

---

#### PCA-401: Plan Document and Calibration Hints Propagation to IMPLEMENT

- **Priority:** P1
- **Closes:** Gap 5 (partial), Gap 6 (partial)
- **Overlaps:** AR-903

The Prime Contractor injects `plan_document_text` as `gen_context["plan_context"]` (line 618) and per-task calibration hints (lines 612–615). The Artisan IMPLEMENT phase does not consume either.

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `metadata["plan_context"]` from `context.get("plan_document_text")`, truncated to 4000 characters.
2. `_tasks_to_chunks()` injects per-task `metadata["calibration_hints"]` from `context.get("onboarding_calibration_hints")` when the task's artifact types match calibration hint keys.
3. `DevelopmentPhase._build_prompt()` formats `plan_context` as a `## Plan Context` section when present.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`), `src/startd8/contractors/artisan_phases/development.py` (`_build_prompt`)

---

#### PCA-402: Onboarding Field Consumption Audit Trail

- **Priority:** P1
- **Overlaps:** AR-905 (Provenance Audit Trail)

Track which onboarding fields were consumed by which phase, enabling Mottainai compliance validation.

**Acceptance Criteria:**

1. Each phase handler that reads an onboarding field from context increments a counter:
   ```python
   context.setdefault("_onboarding_consumption", {})
   context["_onboarding_consumption"].setdefault(field_name, []).append(phase_name)
   ```
2. `FinalizePhaseHandler` includes the `_onboarding_consumption` map in the execution report under `provenance.onboarding_fields_consumed`.
3. The audit trail enables answering: *"Was `service_metadata` consumed by any phase other than PLAN?"* (If not, it was injected but wasted — a Mottainai violation.)

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (all handlers), `FinalizePhaseHandler`

---

#### PCA-403: Cross-Feature Context Accumulation for IMPLEMENT

- **Priority:** P1
- **Closes:** Gap 6
- **Overlaps:** AR-124 (Cross-Task Context)

The DESIGN phase accumulates `prior_design_summaries` (up to 5) for cross-task awareness. The IMPLEMENT phase has no equivalent. When features execute sequentially, later features should benefit from conventions established by earlier features.

**Acceptance Criteria:**

1. After each feature's code is generated in IMPLEMENT, a brief summary (feature name, key files, conventions used) is appended to `context["_prior_impl_summaries"]`.
2. `_tasks_to_chunks()` injects the accumulated summaries (last 3) into `metadata["prior_implementations"]`.
3. `DevelopmentPhase._build_prompt()` formats them as a `## Prior Implementations` section.
4. In phase-serial mode, summaries accumulate across the full task list. In feature-serial mode, each feature sees summaries from all prior features.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`ImplementPhaseHandler`), `src/startd8/contractors/artisan_phases/development.py`

---

#### PCA-404: Requirements Text Propagation to IMPLEMENT

- **Priority:** P1
- **Status:** Partially implemented
- **Overlaps:** AR-903, IMP-P2

The Prime Contractor forwards `requirements_text` from `feature.metadata` to `gen_context["requirements_text"]` (line 620–621). The Artisan pipeline stores `requirements_text` on `SeedTask` and passes it to `FeatureContext` for DESIGN, but the IMPLEMENT phase does not inject it into `DevelopmentChunk.metadata`.

**Acceptance Criteria:**

1. `_tasks_to_chunks()` injects `metadata["requirements_text"]` from `task.requirements_text` when non-empty.
2. `DevelopmentPhase._build_prompt()` formats it as a `## Requirements` section placed immediately after the implementation prompt.
3. Token budget: `requirements_text` is truncated to 3000 characters for prompt budget.

**Source files:** `src/startd8/contractors/context_seed_handlers.py` (`_tasks_to_chunks`), `src/startd8/contractors/artisan_phases/development.py` (`_build_prompt`)

---

## 4. Data Flow Diagrams

### 4.1 Current State: Context Propagation Gaps

```
run_artisan_workflow.py
  │
  ▼
initial_context = {
  "enriched_seed_path": ...,        ← PRESENT
  # "project_root": ...             ← MISSING (Gap 1)
}
  │
  ▼
PlanPhaseHandler.execute()
  ├─ context["tasks"] = ...
  ├─ context["architectural_context"] = ...
  ├─ context["design_calibration"] = ...
  ├─ context["onboarding_derivation_rules"] = ...   ← SET here
  ├─ context["onboarding_resolved_parameters"] = ...
  ├─ context["onboarding_output_contracts"] = ...
  ├─ context["onboarding_calibration_hints"] = ...
  ├─ context["onboarding_open_questions"] = ...
  ├─ context["onboarding_dependency_graph"] = ...
  ├─ context["service_metadata"] = ...              ← SET here
  └─ context["plan_document_text"] = ...            ← SET here
  │
  ▼
_CHECKPOINT_CONTEXT_KEYS (line 138–150):
  PERSISTED: enriched_seed_path, plan_title, plan_goals, domain_summary,
             preflight_summary, total_estimated_loc, architectural_context,
             design_calibration, project_root, source_checksum,
             parameter_sources, semantic_conventions, output_conventions,
             scaffold, example_artifacts, workflow_id, truncation_flags
  NOT PERSISTED (Gap 2):
    onboarding_derivation_rules, onboarding_resolved_parameters,
    onboarding_output_contracts, onboarding_calibration_hints,
    onboarding_open_questions, onboarding_dependency_graph,
    service_metadata, plan_document_text
  │
  ▼
_ensure_context_loaded() (line 559):
  RE-LOADED on resume:
    tasks, task_index, plan_title, plan_goals, preflight_summary,
    domain_summary, total_estimated_loc, example_artifacts,
    source_checksum, parameter_sources, semantic_conventions,
    output_conventions, architectural_context, design_calibration
  NOT RE-LOADED (Gap 2 secondary):
    onboarding_*, service_metadata, plan_document_text
  │
  ▼
IMPLEMENT phase (DevelopmentChunk):
  implementation_prompt = task.description      ← BARE (Gap 3)
  metadata.design_document = design_doc_text    ← DESIGN output only
  metadata.parameter_sources = filtered_subset  ← narrowed per task
  metadata.semantic_conventions = ...           ← present
  # service_metadata                            ← ABSENT (Gap 5)
  # plan_document_text                          ← ABSENT
  # architectural_context                       ← ABSENT in prompt
  Writes to staging_dir (.startd8/staging/)     ← no direct project_root writes
  │
  ▼
INTEGRATE phase (IntegrationEngine):
  Reads generation_results from context
  Merges staged files into project_root
  Runs post-merge checkpoints (ruff, import checks)
  No LLM prompts — purely mechanical
  Reads: project_root, _staging_dir, generation_results
  Writes: integration_results to context
  # No project-level context consumed for prompts (no LLM calls)
  │
  ▼
TEST phase:
  │
  ▼
REVIEW phase:
  system_prompt = "You are reviewing generated   ← GENERIC (Gap 4)
    code for quality and correctness."
  # No project-level framing
  # No service_metadata                         ← ABSENT (Gap 5)
```

### 4.2 Proposed State: Full Context Propagation

```
run_artisan_workflow.py
  │
  ▼
initial_context = {
  "enriched_seed_path": ...,
  "project_root": str(resolved_path),           ← PCA-100
}
  │
  ▼
ArtisanContractorWorkflow.execute()
  └─ context.setdefault("project_root", ...)     ← PCA-105
  │
  ▼
PlanPhaseHandler.execute()
  └─ (unchanged: all context keys set)
  │
  ▼
_CHECKPOINT_CONTEXT_KEYS (expanded via PCA-200):
  ADDED: onboarding_derivation_rules, onboarding_resolved_parameters,
         onboarding_output_contracts, onboarding_calibration_hints,
         onboarding_open_questions, onboarding_dependency_graph,
         service_metadata, plan_document_text
  │
  ▼
_ensure_context_loaded() (expanded via PCA-201):
  ADDED re-extraction: onboarding_*, service_metadata, plan_document_text
  │
  ▼
IMPLEMENT phase (DevelopmentChunk):
  Writes to staging_dir (.startd8/staging/)       ← no direct project_root writes
  metadata gains:
    service_metadata                              ← PCA-400
    plan_context (truncated summary)              ← PCA-401
    architectural_context (relevant subset)        ← PCA-300
    calibration_hints (per-task)                   ← PCA-401
    requirements_text                             ← PCA-404
    prior_implementations (last 3)                ← PCA-403
  _build_prompt() gains:
    "## Project Architecture" section              ← PCA-300
    "## Service Metadata" section                  ← PCA-301
    "## Requirements" section                     ← PCA-404
    "## Plan Context" section                     ← PCA-401
    "## Prior Implementations" section            ← PCA-403
  │
  ▼
INTEGRATE phase (IntegrationEngine):
  Merges staged files → project_root              ← extracted from PrimeContractor
  Per-task: snapshot → validate → merge → checkpoint → commit/rollback
  No LLM prompts — no PCA prompt enrichment needed
  Reads: project_root, _staging_dir, generation_results
  Writes: integration_results to context
  │
  ▼
TEST phase:
  │
  ▼
REVIEW phase:
  _build_review_prompt() gains:
    "## Project Context" section                   ← PCA-302
    "## Service Metadata Compliance" section       ← PCA-303
  │
  ▼
FINALIZE phase:
  execution report gains:
    provenance.project_root                       ← PCA-100
    provenance.onboarding_fields_consumed: {}     ← PCA-402
```

---

## 5. Traceability Matrix

### 5.1 Requirement → Source File

| Requirement | Primary Source File | Line(s) | Secondary Files |
|---|---|---|---|
| PCA-100 | `scripts/run_artisan_workflow.py` | 793 | |
| PCA-101 | `src/startd8/contractors/context_seed_handlers.py` | 872 | |
| PCA-102 | `src/startd8/contractors/context_seed_handlers.py` | 890–906 | |
| PCA-103 | `src/startd8/contractors/context_seed_handlers.py` | 855–885 | |
| PCA-104 | `src/startd8/contractors/context_seed_handlers.py` | all handlers | |
| PCA-105 | `src/startd8/contractors/artisan_contractor.py` | `execute()` | |
| PCA-200 | `src/startd8/contractors/artisan_contractor.py` | 138–150 | |
| PCA-201 | `src/startd8/contractors/context_seed_handlers.py` | 559–649 | |
| PCA-202 | `src/startd8/contractors/artisan_contractor.py` | checkpoint serialization | |
| PCA-203 | `src/startd8/contractors/artisan_contractor.py` | `CHECKPOINT_SCHEMA_VERSION` | |
| PCA-300 | `src/startd8/contractors/context_seed_handlers.py` | 2703 (`_tasks_to_chunks`) | `artisan_phases/development.py` (542) |
| PCA-301 | `src/startd8/contractors/context_seed_handlers.py` | 3092–3127 | `artisan_phases/development.py` (542) |
| PCA-302 | `src/startd8/contractors/context_seed_handlers.py` | 4700–4750 | |
| PCA-303 | `src/startd8/contractors/context_seed_handlers.py` | 4789 (`_build_review_prompt`) | |
| PCA-304 | `src/startd8/contractors/context_seed_handlers.py` | TEST/FINALIZE handlers | `artisan_phases/self_consistency.py` |
| PCA-400 | `src/startd8/contractors/context_seed_handlers.py` | 3092–3127 | |
| PCA-401 | `src/startd8/contractors/context_seed_handlers.py` | 2703 (`_tasks_to_chunks`) | `artisan_phases/development.py` (542) |
| PCA-402 | `src/startd8/contractors/context_seed_handlers.py` | all handlers | `FinalizePhaseHandler` |
| PCA-403 | `src/startd8/contractors/context_seed_handlers.py` | `ImplementPhaseHandler` | `artisan_phases/development.py` |
| PCA-404 | `src/startd8/contractors/context_seed_handlers.py` | 3092–3127 | `artisan_phases/development.py` (542) |

### 5.2 Requirement → Test File

| Requirement | Test File(s) |
|---|---|
| PCA-100 | `tests/unit/contractors/test_artisan_context_injection.py` (new) |
| PCA-105 | `tests/unit/contractors/test_artisan_context_injection.py` (new) |
| PCA-200 | `tests/unit/contractors/test_checkpoint_context_keys.py` (new) |
| PCA-201 | `tests/unit/contractors/test_ensure_context_loaded.py` (extend existing) |
| PCA-202 | `tests/unit/contractors/test_checkpoint_context_keys.py` (new) |
| PCA-203 | `tests/unit/contractors/test_checkpoint_context_keys.py` (new) |
| PCA-300 | `tests/unit/contractors/test_implement_prompt_enrichment.py` (new) |
| PCA-301 | `tests/unit/contractors/test_implement_prompt_enrichment.py` (new) |
| PCA-302 | `tests/unit/contractors/test_review_phase_handler.py` (extend existing) |
| PCA-303 | `tests/unit/contractors/test_review_phase_handler.py` (extend existing) |
| PCA-304 | `tests/unit/contractors/test_review_phase_handler.py` (extend existing) |
| PCA-400 | `tests/unit/contractors/test_tasks_to_chunks.py` (extend or new) |
| PCA-401 | `tests/unit/contractors/test_tasks_to_chunks.py` (extend or new) |
| PCA-402 | `tests/unit/contractors/test_onboarding_audit_trail.py` (new) |
| PCA-403 | `tests/unit/contractors/test_cross_feature_accumulation.py` (new) |
| PCA-404 | `tests/unit/contractors/test_tasks_to_chunks.py` (extend or new) |

---

## 6. Priority Phasing

### 6.1 P0 (Critical Path) — Must Implement Before Next Artisan Run

| Requirement | Gap | LOE | Rationale |
|---|---|---|---|
| **PCA-100** | Gap 1 | XS (2 lines) | Without `project_root` in context, all downstream phases use `Path(".")` |
| **PCA-105** | Gap 1 | XS (3 lines) | Defense-in-depth for PCA-100 |
| **PCA-200** | Gap 2 | S (8 keys added to frozenset) | Without this, all onboarding data is lost on resume |
| **PCA-201** | Gap 2 | M (15–20 lines mirroring PLAN extraction) | Defense-in-depth: re-extract onboarding on resume |
| **PCA-203** | — | XS (test only) | Validates backward compat of checkpoint schema |
| **PCA-300** | Gap 3, 4 | M (30–40 lines in 2 files) | IMPLEMENT prompts lack project framing |
| **PCA-301** | Gap 5 | S (10 lines in 2 files) | `service_metadata` absent from IMPLEMENT |
| **PCA-302** | Gap 4 | M (30–40 lines) | REVIEW prompts lack project framing |
| **PCA-400** | Gap 5 | S (5 lines) | Data propagation complement to PCA-301 |

### 6.2 P1 (High Value) — Implement in Next Iteration

| Requirement | Gap | LOE | Rationale |
|---|---|---|---|
| **PCA-101** | Gap 5 | — (already done) | Formalizes existing PLAN extraction |
| **PCA-102** | Gap 5 | — (already done) | Formalizes existing PLAN extraction |
| **PCA-103** | Gap 2 | — (already done) | Formalizes existing; persistence via PCA-200 |
| **PCA-104** | — | S (10–15 lines per handler) | Debuggability of context propagation |
| **PCA-202** | Gap 2 | S (10 lines) | Prevents checkpoint bloat from large plans |
| **PCA-303** | Gap 5 | S (15 lines) | Review-time service metadata compliance |
| **PCA-304** | Gap 5 | — (already done) | Formalizes existing TEST wiring |
| **PCA-401** | Gap 5, 6 | M (20 lines) | Plan context and calibration in IMPLEMENT |
| **PCA-402** | — | S (10 lines per handler + FINALIZE) | Mottainai audit trail |
| **PCA-403** | Gap 6 | M (25 lines) | Cross-feature context accumulation |
| **PCA-404** | Gap 5 | S (10 lines) | Requirements text in IMPLEMENT |

### 6.3 Implementation Sequencing

```
Phase 1 (P0 — Context Survival):
  PCA-100 + PCA-105    (project_root injection)
  PCA-200 + PCA-203    (checkpoint keys expansion + compat test)
  PCA-201              (_ensure_context_loaded expansion)
  ──────────────────────────────────────────────────────────
  At this point: all project context survives resume

Phase 2 (P0 — Prompt Enrichment):
  PCA-300 + PCA-301    (IMPLEMENT prompt: architecture + service metadata)
  PCA-400              (service_metadata data propagation)
  PCA-302              (REVIEW prompt: project context)
  ──────────────────────────────────────────────────────────
  At this point: IMPLEMENT and REVIEW prompts match Prime quality
  Note: INTEGRATE phase has no LLM prompts — no PCA prompt
  enrichment needed.  It reads project_root and
  generation_results mechanically.

Phase 3 (P1 — Completeness):
  PCA-303              (REVIEW service metadata compliance)
  PCA-401              (plan context + calibration in IMPLEMENT)
  PCA-403              (cross-feature accumulation)
  PCA-404              (requirements text in IMPLEMENT)
  PCA-104              (context completeness logging — all 8 phases)
  PCA-402              (onboarding consumption audit)
  ──────────────────────────────────────────────────────────
  At this point: full parity with Prime Contractor
```

### 6.4 Dependency Constraints

- P0 items have **no P1 dependencies** — Phase 1 and Phase 2 can be implemented independently of Phase 3.
- PCA-400 is a data-flow prerequisite for PCA-301 (propagation before prompt enrichment).
- PCA-200/201 are prerequisites for PCA-304 (service_metadata must survive resume for TEST to consume it).
- PCA-403 depends on IMPLEMENT phase execution order (only meaningful in sequential/feature-serial mode).

---

## 7. Contract YAML Amendments

The `artisan-pipeline.contract.yaml` should be updated to reflect the new context fields:

### 7.1 `plan.exit.optional`

Add the following optional exit fields to the PLAN phase:

```yaml
plan:
  exit:
    optional:
      # ... existing fields ...
      service_metadata:
        type: dict
        description: "Service metadata from onboarding (transport, deps)"
      plan_document_text:
        type: string
        description: "Full plan document text for downstream phases"
      onboarding_derivation_rules:
        type: any
        description: "Derivation rules from onboarding"
      onboarding_resolved_parameters:
        type: any
        description: "Resolved artifact parameters from onboarding"
      onboarding_output_contracts:
        type: any
        description: "Expected output contracts from onboarding"
      onboarding_calibration_hints:
        type: any
        description: "Design calibration hints from onboarding"
      onboarding_open_questions:
        type: any
        description: "Open questions from onboarding"
      onboarding_dependency_graph:
        type: any
        description: "Artifact dependency graph from onboarding"
```

### 7.2 `implement.entry.enrichment`

Add context enrichment declarations to the IMPLEMENT phase entry:

```yaml
implement:
  entry:
    enrichment:
      # ... existing fields ...
      service_metadata:
        severity: warning
        source_phase: plan
        description: "Service metadata for protocol/dep validation in prompts"
      plan_document_text:
        severity: advisory
        source_phase: plan
        description: "Plan document text for implementation context"
      architectural_context:
        severity: advisory
        source_phase: plan
        description: "Architectural context for project-aware code generation"
```

### 7.3 `review.entry.enrichment`

Add context enrichment declarations to the REVIEW phase entry:

```yaml
review:
  entry:
    enrichment:
      # ... existing fields ...
      service_metadata:
        severity: advisory
        source_phase: plan
        description: "Service metadata for compliance review"
      architectural_context:
        severity: advisory
        source_phase: plan
        description: "Architectural context for project-aware review"
```

### 7.4 `integrate` Phase (Already Implemented)

The INTEGRATE phase contract is already declared in `artisan-pipeline.contract.yaml` (added as part of the INTEGRATE phase implementation). It has no PCA-specific amendments because INTEGRATE makes no LLM calls and does not consume project-level context for prompt construction. Its entry/exit contract is:

```yaml
integrate:
  description: "Merge staged generated code into project root with validation and rollback"
  entry:
    required:
      - name: generation_results    # from IMPLEMENT
    enrichment:
      - name: _staging_dir          # from IMPLEMENT, falls back to .startd8/staging/
  exit:
    required:
      - name: integration_results   # per-task merge outcomes
```

No PCA enrichment fields (`service_metadata`, `architectural_context`, `plan_document_text`) need to be added to INTEGRATE's entry because the phase does not construct LLM prompts.

### 7.5 New Propagation Chain

Add a new end-to-end propagation chain:

```yaml
propagation_chains:
  # ... existing chains ...
  onboarding_context:
    description: "Project-level onboarding context flows from seed through all phases"
    path: "seed → PLAN context → checkpoint → DESIGN/IMPLEMENT/INTEGRATE/TEST/REVIEW/FINALIZE"
    fields:
      - service_metadata
      - plan_document_text
      - onboarding_calibration_hints
      - onboarding_dependency_graph
      - architectural_context
    persistence: "_CHECKPOINT_CONTEXT_KEYS + _ensure_context_loaded() re-extraction"
    note: "INTEGRATE is on the path but does not consume these fields — it passes them through unchanged."
```

---

## 8. Cross-References

### 8.1 PCA → Existing AR/IMP Requirements

| PCA Requirement | Existing Requirement | Relationship |
|---|---|---|
| PCA-100 | AR-100 (Seed Loading) | Extends: AR-100 loads seeds; PCA-100 ensures `project_root` enters context |
| PCA-101 | AR-144, AR-147 | Closes: AR-144/147 validate protocol fidelity; PCA-101 ensures the data is present |
| PCA-102 | AR-903 (Metadata Forwarding) | Extends: AR-903 governs metadata flow; PCA-102 formalizes plan doc propagation |
| PCA-103 | AR-303..AR-308 | Extends: AR-303–308 cover onboarding fields; PCA-103 formalizes persistence |
| PCA-200, PCA-201 | AR-505 (Checkpoint Schema), AR-903 | Extends: AR-505 defines checkpoint structure; PCA-200 adds keys to it |
| PCA-203 | AR-511 (Schema Versioning) | Validates: no version bump needed for optional keys |
| PCA-300 | AR-131 (Design Injection), AR-903 | Complement: AR-131 injects design docs; PCA-300 adds project context |
| PCA-301, PCA-400 | AR-144, AR-147, AR-903 | Closes: AR-144/147 validate protocol fidelity; PCA-301/400 ensure data reaches IMPLEMENT |
| PCA-302 | AR-150 (LLM Review) | Extends: AR-150 defines LLM review; PCA-302 enriches the prompt |
| PCA-303 | AR-907 (Guidance Compliance) | Complement: AR-907 validates compliance; PCA-303 equips the reviewer |
| PCA-403 | AR-124 (Cross-Task Context) | Extends: AR-124 is DESIGN-phase cross-task; PCA-403 adds IMPLEMENT-phase |
| PCA-402 | AR-905 (Provenance Audit Trail) | Complement: AR-905 tracks metadata provenance; PCA-402 tracks consumption |
| PCA-404 | AR-903, IMP-P2 | Complement: IMP-P2 validates requirements text passthrough in Prime; PCA-404 mirrors it for Artisan |

### 8.2 IMP Boundary Requirements

IMP-1 through IMP-7 define the DESIGN→IMPLEMENT boundary validation. PCA requirements ensure the context that IMP-7 validates is actually present in the downstream prompt:

- **IMP-7** checks parameter completeness at the DESIGN→IMPLEMENT boundary
- **PCA-300** ensures `architectural_context` (which IMP-7 references) appears in the IMPLEMENT prompt
- **PCA-400/401** ensure `service_metadata` and `plan_context` survive the boundary

Note: The INTEGRATE phase sits between IMPLEMENT and TEST. It does not alter the DESIGN→IMPLEMENT boundary (IMP-1..7) or the context keys that PCA requirements propagate. INTEGRATE reads `generation_results` (IMPLEMENT's output) and writes `integration_results`; it does not consume or transform any PCA context fields.

---

## 9. Status Dashboard

> **Status: 20/20 COMPLETE** (2026-02-21)
>
> All P0 and P1 requirements implemented and tested. 51 tests in `test_pca_p0.py`.

| Layer | ID Range | Total | Done | Commits |
|---|---|---|---|---|
| Context Injection | PCA-100..105 | 6 | 6 | `3bf5e55` (P0), `3a4d1c8` (P1), pre-existing (101–103) |
| Checkpoint Persistence | PCA-200..203 | 4 | 4 | `3bf5e55` (P0), `3a4d1c8` (P1) |
| Prompt Enrichment | PCA-300..304 | 5 | 5 | `3bf5e55` (P0), `3a4d1c8` (P1), pre-existing (304) |
| Cross-Phase Propagation | PCA-400..404 | 5 | 5 | `3bf5e55` (P0), `3a4d1c8` (P1) |
| **Total** | | **20** | **20** | |

### Per-Requirement Status

| Req | Priority | Status | Notes |
|---|---|---|---|
| PCA-100 | P0 | DONE | `project_root` in `initial_context` |
| PCA-101 | P1 | DONE | Pre-existing (PLAN phase, line 872) |
| PCA-102 | P1 | DONE | Pre-existing (PLAN phase, lines 890–906) |
| PCA-103 | P1 | DONE | Pre-existing (PLAN phase, lines 855–885) |
| PCA-104 | P1 | DONE | `_log_context_completeness()` in 6 phase handlers |
| PCA-105 | P0 | DONE | `context.setdefault("project_root", ...)` already compliant |
| PCA-200 | P0 | DONE | 8 keys added to `_CHECKPOINT_CONTEXT_KEYS` |
| PCA-201 | P0 | DONE | `_ensure_context_loaded()` re-extracts onboarding + plan_document_text |
| PCA-202 | P1 | DONE | `_PLAN_DOC_CHECKPOINT_MAX_CHARS = 1000` + truncation marker |
| PCA-203 | P0 | DONE | Backward compat test (v4 checkpoints load without new keys) |
| PCA-300 | P0 | DONE | `architectural_context`, `plan_goals`, `plan_context` in chunk metadata + prompt |
| PCA-301 | P0 | DONE | `service_metadata` in chunk metadata + `## Service Metadata` prompt section |
| PCA-302 | P0 | DONE | `## Project Context` section in review prompt (capped at 2000 chars) |
| PCA-303 | P1 | DONE | `## Service Metadata Compliance` section in review prompt |
| PCA-304 | P1 | DONE | Pre-existing (TEST/FINALIZE `validate_protocol_fidelity()`) |
| PCA-400 | P0 | DONE | `service_metadata` propagated to `DevelopmentChunk.metadata` |
| PCA-401 | P1 | DONE | `calibration_hints` + `plan_context` in chunk metadata + `## Plan Context` section |
| PCA-402 | P1 | DONE | `_track_onboarding_consumption()` in IMPLEMENT/REVIEW + FINALIZE provenance |
| PCA-403 | P1 | DONE | `prior_impl_summaries` accumulated (last 3) + `## Prior Implementations` section |
| PCA-404 | P1 | DONE | `requirements_text` in chunk metadata (3000 char cap) + `## Requirements` section |

**Note on INTEGRATE phase:** The INTEGRATE phase (added between IMPLEMENT and TEST) is a purely mechanical phase — it merges staged files into `project_root` via `IntegrationEngine` with snapshot/validate/merge/checkpoint/rollback. It makes no LLM calls and consumes no tokens. Therefore, no PCA prompt enrichment requirements (Layer 3) apply to it. PCA-104 (context completeness logging) includes INTEGRATE for diagnostic consistency, but the logging is advisory since no LLM prompt benefits from the context in this phase.

---

## 10. Related Documents

| Document | Relationship |
|---|---|
| `docs/design/artisan/ARTISAN_REQUIREMENTS.md` | Parent requirements document (AR-xxx) |
| `docs/design/artisan/ARTISAN_PROMPT_EXTERNALIZATION_REQUIREMENTS.md` | Companion: prompt externalization plan |
| `src/startd8/contractors/contracts/artisan-pipeline.contract.yaml` | Context propagation contract (amended per Section 7; includes INTEGRATE phase) |
| `src/startd8/contractors/prime_contractor.py` | Reference implementation of project-centric context injection |
| `src/startd8/contractors/integration_engine.py` | Standalone integration pipeline extracted from PrimeContractor (used by INTEGRATE phase) |
| `src/startd8/workflows/builtin/prompts/lead_contractor.yaml` | Reference spec prompt showing full context assembly |
| `docs/ARTISAN_WORKFLOW_GUIDE.md` | User-facing workflow guide (update after implementation) |
| `docs/ARTISAN_WORKFLOW_ISSUES_CATALOG.md` | Known issues catalog (add PCA gaps as resolved) |
