# Prime Contractor Execution Modes — Requirements

**Version:** 1.0.0
**Created:** 2026-02-20
**Status:** Partially Implemented — REQ-PEM-000 through REQ-PEM-005 complete (Layers 0–1 and Layer 2 protocol/SeedContext)
**Depends on:** `PRIME_CONTRACTOR_REQUIREMENTS.md` (REQ-PC-001–014), `PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md` (REQ-PPE-001–006)

---

## Problem Statement

The Prime Contractor was designed as a standalone code generation workflow: load a seed JSON, queue features, generate code, merge files. It has no formal concept of where its context comes from or where its output goes next.

The Capability Delivery Pipeline (stages 0–7) now provides rich context that the artisan route exploits — onboarding metadata, architectural context, design calibration, service metadata, domain enrichment, and post-generation validators. When the Prime Contractor runs as stage 6 inside this pipeline, it receives this context but uses almost none of it. The `gen_context` dict is assembled by ad-hoc attribute stashing on the workflow instance, with no contract governing what's present.

This creates two problems:

1. **Pipeline mode underperforms.** Context that costs real money to produce (plan ingestion, domain preflight, export enrichment) is ignored by the prime route, leading to lower-quality code generation compared to the artisan route.

2. **Standalone mode is fragile.** Because the same code path handles both modes, standalone usage requires the same seed structure as pipeline usage. There's no graceful degradation — missing fields silently produce empty context.

### Design Principle

**The Prime Contractor should be a first-class citizen in both worlds.** In standalone mode, it should work with minimal configuration and degrade gracefully. In pipeline mode, it should consume and exploit the full context that the pipeline provides. The same workflow code handles both — the difference is in how context is resolved.

---

## Execution Mode Model

```
                    ┌─────────────────────────────────────┐
                    │      PrimeContractorWorkflow         │
                    │                                     │
   STANDALONE       │  ┌─────────────────────────────┐   │      PIPELINE
   ─────────────────┤  │    ContextResolutionStrategy │   ├──────────────────
                    │  │                             │   │
   CLI args         │  │  resolve_task_context()     │   │  Enriched seed
   Simple seed JSON │  │  resolve_seed_context()     │   │  Onboarding metadata
   Inline prompts   │  │  resolve_validation_config()│   │  Architectural context
   No validators    │  │  resolve_output_contract()  │   │  Service metadata
   File output only │  │                             │   │  Post-gen validators
                    │  └─────────────────────────────┘   │  OTel + provenance
                    │                                     │
                    └─────────────────────────────────────┘
```

---

## Requirements

### Layer 0: Pipeline Validation Gates (REQ-PEM-000, REQ-PEM-000a)

#### REQ-PEM-000: Edit-First Smoke Test

**Priority:** P0 (prerequisite to all other phases)
**Implementation Status:** ✅ Complete — validated via REQ-EFE-020 Edit-First Enforcement gate (commit dddb9c5)
**Source files:** `src/startd8/contractors/prime_contractor.py`
**Depends on:** PCA-503 (Edit-First Directive in IMPLEMENT prompt), PCA-600 (Edit-Mode Classification)

Before any functional changes are made to `prime_contractor.py`, the Artisan pipeline MUST demonstrate that it can **edit the existing file** rather than regenerating it from scratch. This is a blocking validation gate for all subsequent phases.

**Problem statement:** The Artisan 8-phase pipeline's IMPLEMENT phase has consistently failed to honor edit-first behavior (PCA-5xx) when targeting SDK-internal files. Instead of reading the existing `prime_contractor.py` (~1800 lines of production code) and applying surgical edits, the pipeline generates a complete replacement file, destroying all existing functionality. This has been the primary blocker for implementing the Execution Modes plan — every attempt to implement Phase 1 (FR-001–FR-004) via the Artisan pipeline results in a from-scratch rewrite that breaks the entire Prime Contractor.

**Validation task:** The Artisan pipeline MUST successfully execute a single trivial edit to `prime_contractor.py`:

1. Add a module-level constant to `prime_contractor.py`:
   ```python
   # Edit-first validation marker (REQ-PEM-000) — remove after Phase 1 completion
   _EDIT_FIRST_VALIDATED = True
   ```
2. The edit MUST be applied to the **existing** file content — the file's existing code (classes, methods, imports, docstrings) MUST remain unchanged after the edit.
3. The edit MUST NOT regenerate, rewrite, or replace the file. The diff MUST show only the addition of the constant (±5 lines for surrounding whitespace).

**Success criteria:**
- `git diff` after the Artisan run shows ONLY the addition of the `_EDIT_FIRST_VALIDATED` constant (and any necessary blank lines)
- All existing tests pass without modification
- The file line count changes by no more than 3 lines
- No existing imports, classes, methods, or docstrings are modified

**Failure criteria (any one triggers failure):**
- The generated file differs from the original by more than 10 lines
- Any existing class or method signature is altered
- Any existing import is removed or reordered
- The file is shorter than the original (indicates from-scratch generation)

**Rationale:** This requirement exists because the Artisan pipeline has never successfully edited `prime_contractor.py` — it has only ever produced from-scratch rewrites. Until the pipeline can demonstrate a trivial edit, attempting complex multi-class refactoring (Phase 1–5) will continue to fail destructively. This is the smallest possible validation of PCA-5xx edit-first behavior against a real SDK-internal target file.

**Acceptance criteria:**
- The `_EDIT_FIRST_VALIDATED = True` constant exists in `prime_contractor.py` after a successful Artisan run
- The Artisan run log shows edit-mode classification as `edit` (not `create` or `greenfield`)
- The diff between pre-run and post-run `prime_contractor.py` is ≤10 lines changed
- All existing unit tests pass
- After validation, the constant MAY be removed or retained as a sentinel — it has no functional impact

---

#### REQ-PEM-000a: Full-Depth OTel Tracing Verification via Phase 0 Trace

**Priority:** P0 (prerequisite to all other phases)
**Implementation Status:** ✅ Complete — OT-100 through OT-507, OT-600 verified (commits 92cb79a, b98b4c7)
**Source files:** Grafana Tempo trace produced by Phase 0 Artisan run
**Depends on:** REQ-PEM-000 (edit-first smoke test must pass first), OT-1xx through OT-6xx (implemented OTel instrumentation), `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` (design principle validation)
**Validates:** `ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md` (OT-100–OT-507, OT-600), `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` (prescriptive verification of context correctness)

The Phase 0 Artisan run (REQ-PEM-000) produces the simplest possible end-to-end pipeline execution: a single task, one target file, trivial edit. This makes it an ideal test subject for verifying that the full-depth OTel tracing instrumentation (OT-1xx through OT-6xx) produces a correct, complete, and queryable trace — and that context correctness by construction can be programmatically validated via trace inspection.

**Problem statement:** The full-depth OTel tracing requirements (43 requirements across 7 layers) have 25 implemented and 18 planned. The implemented requirements (OT-100–OT-507, OT-600) have unit tests (`test_thread_context_propagation.py`, `test_artisan_otel_spans.py`) but no end-to-end verification against a real pipeline run. The `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` design principle — that "silent degradation is structurally impossible when contracts generate signals at every boundary" — has never been validated programmatically. Phase 0's trivial edit provides a controlled, reproducible execution that can serve as the baseline trace for both verifications.

**Verification approach:** After Phase 0 completes successfully (REQ-PEM-000 passes), the resulting trace in Grafana Tempo MUST be queried programmatically to verify the span hierarchy, context propagation, gate boundary events, and per-task attributes. This transforms the theoretical "context correctness by construction" principle into an empirical, repeatable validation.

**Span hierarchy verification (§4 of ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md):**

The Phase 0 trace MUST contain the following span hierarchy:

```
workflow.{workflow_id}                            # AR-600
  └── phase.plan                                   # AR-601
  │    ├── gate.entry                              # OT-200
  │    │    └── [context.boundary.entry event]
  │    ├── task.{task_id}                           # OT-301 (single task)
  │    └── gate.exit                               # OT-201
  │         └── [context.boundary.exit event]
  └── phase.scaffold                               # AR-601
  │    ├── gate.entry                              # OT-200
  │    └── gate.exit                               # OT-201
  └── phase.design                                 # AR-601
  │    ├── gate.entry                              # OT-200
  │    ├── task.{task_id}                           # OT-301
  │    │    └── design.iteration.1                 # OT-404
  │    │         ├── design.generate               # OT-401
  │    │         │    ├── [llm.call.start event]   # OT-400
  │    │         │    └── [llm.call.complete event] # OT-400
  │    │         └── design.review.reviewer         # OT-402
  │    └── gate.exit                               # OT-201
  └── phase.implement                              # AR-601
  │    ├── gate.entry                              # OT-200
  │    ├── task.{task_id}                           # OT-301 (single task)
  │    │    └── implement.chunk.{chunk_id}         # OT-305
  │    └── gate.exit                               # OT-201
  └── phase.integrate                              # AR-601
  │    ├── gate.entry                              # OT-200
  │    ├── task.{task_id}                           # OT-302
  │    └── gate.exit                               # OT-201
  └── phase.test                                   # AR-601
  │    ├── gate.entry                              # OT-200
  │    ├── task.{task_id}                           # OT-303
  │    │    └── test.generate                      # OT-405
  │    └── gate.exit                               # OT-201
  └── phase.review                                 # AR-601
  │    ├── gate.entry                              # OT-200
  │    ├── task.{task_id}                           # OT-304
  │    └── gate.exit                               # OT-201
  └── phase.finalize                               # AR-601
       ├── gate.entry                              # OT-200
       └── gate.exit                               # OT-201
```

**TraceQL verification queries:**

Each query MUST return results from the Phase 0 trace. A query returning zero results indicates a tracing gap.

| # | Query | Validates | Expected |
|---|-------|-----------|----------|
| V-1 | `{ resource.service.name = "startd8-sdk" && name = "workflow.*" }` | AR-600: Root span exists | 1 span |
| V-2 | `{ name =~ "phase\\..*" } \| select(span.gate.phase)` | AR-601: All 8 phase spans present | 8 spans (plan, scaffold, design, implement, integrate, test, review, finalize) |
| V-3 | `{ name = "gate.entry" } \| select(span.gate.passed, span.gate.propagation_status)` | OT-200: Gate entry spans with attributes | ≥8 spans (one per phase) |
| V-4 | `{ name = "gate.exit" } \| select(span.gate.passed)` | OT-201: Gate exit spans | ≥8 spans |
| V-5 | `{ name =~ "task\\..*" } \| select(span.task.id, span.task.status)` | OT-301–304: Per-task spans across phases | ≥4 spans (plan, design, implement, integrate, test, review) |
| V-6 | `{ name =~ "design\\.iteration\\..*" }` | OT-404: Design iteration spans | ≥1 span |
| V-7 | `{ name = "design.generate" }` | OT-401: Design generate span | ≥1 span |
| V-8 | `{ name =~ "implement\\.chunk\\..*" } \| select(span.chunk.status)` | OT-305: Implement chunk span | 1 span |
| V-9 | `{ name = "test.generate" }` | OT-405: Test generate span | 1 span |
| V-10 | `{ name =~ "design\\.review\\..*" }` | OT-402: Design review span | ≥1 span |
| V-11 | `{ status = error }` | OT-507: No error spans (successful run) | 0 spans |
| V-12 | `{ name = "design.generate" } >> { name =~ "task\\..*" }` | OT-103: Design spans are children of task spans (thread propagation) | Ancestor match |
| V-13 | `{ name =~ "implement\\.chunk\\..*" } >> { name =~ "task\\..*" }` | OT-104: Implement spans are children of task spans (thread propagation) | Ancestor match |

**Context correctness by construction validation (`CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md`):**

The trace produced by Phase 0 provides empirical evidence for the document's core claims:

1. **"Silent degradation is structurally impossible when contracts generate signals at every boundary"** — V-3 and V-4 verify that gate spans with `gate.passed` and `gate.propagation_status` attributes exist at every phase boundary. If any gate span is missing, context propagation at that boundary is invisible — violating the principle.

2. **"Prescriptive over descriptive"** — The gate span attributes (`gate.passed`, `gate.propagation_status`) declare what *should* happen (context must propagate intact) and record what *did* happen. A `gate.propagation_status = "DEGRADED"` or `"BROKEN"` is a prescriptive signal, not a post-hoc description.

3. **"Observable contracts over invisible guarantees"** — The trace makes the contract system itself observable. V-3 verifies that contract validation events (`context.boundary.entry`) land inside gate spans, making them navigable in Tempo's waterfall view. Without this nesting, contract events are orphaned and undiscoverable.

4. **"Layer 1: Context Propagation" is the keystone** — The Phase 0 trace validates that the Artisan pipeline's Layer 1 implementation (PropagationChainSpec → BoundaryValidator → PropagationTracker → emit_boundary_result) produces queryable spans at every phase transition. This is the structural property that all higher layers (schema compat, semantic conventions, causal ordering) depend on.

**Programmatic verification script:**

A verification script MUST be created that:
1. Retrieves the Phase 0 trace from Tempo via the Tempo API (`/api/traces/{traceId}`)
2. Executes each TraceQL query (V-1 through V-13) against the trace
3. Asserts expected results (span counts, attribute presence, parent-child relationships)
4. Reports pass/fail per query with diagnostic output on failure
5. Produces a summary: `"Context Correctness Verification: {passed}/{total} checks passed"`

**Acceptance criteria:**
- All 13 TraceQL verification queries (V-1 through V-13) return expected results from the Phase 0 trace
- The verification script runs successfully and produces a pass/fail report
- Gate spans at every phase boundary contain `gate.passed` and `gate.propagation_status` attributes (context correctness is observable, not invisible)
- Design and implement phase spans are correctly parented via thread context propagation (OT-103, OT-104) — no orphaned spans
- The `context.boundary.entry` and `context.boundary.exit` events are nested inside their respective gate spans (contract events are navigable in Tempo waterfall)
- `{ status = error }` returns 0 spans (the Phase 0 run succeeded)
- The verification script is reusable for future Artisan runs — it accepts a trace ID as input and validates any pipeline execution

**Relationship to planned requirements (OT-7xx):**

This requirement validates the *implemented* OTel instrumentation (OT-1xx through OT-6xx). The *planned* forensic logging layer (OT-7xx: OT-700–OT-714) is out of scope for this verification. Once OT-7xx is implemented, the Phase 0 trace can be extended to validate forensic log emission and trace-to-log correlation (OT-708) — but that is a future addition to this requirement, not a prerequisite.

---

### Layer 1: Execution Mode Declaration (REQ-PEM-001–003)

#### REQ-PEM-001: ExecutionMode Enum

**Priority:** P1
**Implementation Status:** ✅ Complete — `ExecutionMode` enum defined, mode persistence in state file
**Source files:** `src/startd8/contractors/prime_contractor.py`

The Prime Contractor MUST define an `ExecutionMode` enum with two values:

| Value | Meaning |
|-------|---------|
| `STANDALONE` | Minimal context. Graceful degradation for missing fields. No upstream pipeline dependency. |
| `PIPELINE` | Rich context from Capability Delivery Pipeline. Expects enriched seed with onboarding, architectural context, service metadata. Emits provenance and OTel spans. |

**Acceptance criteria:**
- `ExecutionMode` is importable from `startd8.contractors.prime_contractor`
- Default mode is `STANDALONE` (backward compatible)
- Mode is set at workflow construction time and immutable for the run
- Mode MUST be persisted in `.prime_contractor_state.json` for resume consistency — a resumed workflow MUST use the same mode as the original run
- On resume, the system MUST validate that the current seed's checksum matches the checksum stored in `.prime_contractor_state.json`. If mismatched, the system MUST raise an error: `"Seed checksum mismatch on resume: expected {stored}, got {current}. Use --force-regenerate to override."` This prevents inconsistent state from resuming with a modified seed.

---

#### REQ-PEM-002: Mode Auto-Detection

**Priority:** P2
**Implementation Status:** ✅ Complete — auto-detection from seed signals (commit cf40b9b, PI-006)
**Source files:** `src/startd8/contractors/prime_contractor.py`, `scripts/run_prime_workflow.py`

When no explicit mode is provided, the system MUST auto-detect the mode from the context seed:

| Signal | Detection Rule | Resulting Mode |
|--------|---------------|----------------|
| Seed contains `onboarding` with non-empty `project_objectives` | Present | `PIPELINE` |
| Seed contains `architectural_context` with non-empty value | Present | `PIPELINE` |
| Seed contains `service_metadata` with non-empty value | Present | `PIPELINE` |
| None of the above | Absent | `STANDALONE` |

**Mode determination precedence** (highest to lowest):
1. Explicit CLI flag (`--mode standalone` or `--mode pipeline`)
2. Auto-detection from seed signals (OR logic: any one signal triggers `PIPELINE`)
3. Default: `STANDALONE`

**Forced pipeline mode with inadequate seed:** When `--mode pipeline` is explicitly set but the seed lacks all pipeline signals, the system MUST proceed with degraded quality (not fail fast). Missing context fields produce warnings per REQ-PEM-007, but the workflow continues. This enables iterative pipeline development where upstream stages are still being built.

**Acceptance criteria:**
- Auto-detection uses OR logic: any one signal triggers `PIPELINE`
- Explicit `--mode standalone` or `--mode pipeline` CLI flag overrides auto-detection
- Invalid `--mode` values (e.g., `--mode foobar`) MUST produce a user-friendly error listing valid modes and exit with non-zero status
- Detection result is logged: `"Execution mode: {mode} (auto-detected from seed signals: {signals})"` or `"Execution mode: {mode} (explicit)"` — where `{signals}` lists the actual seed keys that triggered detection (e.g., `"onboarding", "service_metadata"`)

---

#### REQ-PEM-003: Mode-Specific Configuration

**Priority:** P1
**Implementation Status:** ✅ Complete — `ModeConfig` frozen dataclass with `for_mode()` factory
**Source files:** `src/startd8/contractors/prime_contractor.py`

Each execution mode MUST have a configuration profile that governs behavior differences:

| Behavior | STANDALONE | PIPELINE | CLI Override |
|----------|-----------|----------|-------------|
| Missing onboarding fields | Silent (empty dict) | Warning logged per REQ-PC-014 | — |
| Missing service_metadata | Silent | Warning logged | — |
| Post-generation validation | Skip (no validators) | Run Gate 3b validators (REQ-PC-009) | `--validate` / `--no-validate` |
| Provenance emission | Skip | Emit `generation-manifest.json` | — |
| Context injection logging | Minimal | Full per REQ-PC-014 | — |
| Staleness detection | Skip | Enforce per REQ-PC-011 | `--force-regenerate` |
| Cost reporting | Summary only | Per-feature + total per REQ-PC-013 | — |
| OTel span emission | Only if instrumentor configured | Yes (via ContextCoreInstrumentor) | — |

**`ModeConfig` dataclass definition:**

```python
@dataclass(frozen=True)
class ModeConfig:
    execution_mode: ExecutionMode
    warn_missing_fields: bool          # Log warnings for missing onboarding/service_metadata fields
    run_validators: bool               # Run post-generation Gate 3b validators
    emit_provenance: bool              # Write generation-manifest.json
    log_context_injection: bool        # Full context injection logging per REQ-PC-014
    detect_staleness: bool             # Enforce staleness detection via source_checksum
    detailed_cost_reporting: bool      # Per-feature + total cost (vs. summary only)
    require_otel: bool                 # Require OTel span emission (vs. optional)

    @classmethod
    def for_mode(cls, mode: ExecutionMode) -> "ModeConfig":
        if mode == ExecutionMode.STANDALONE:
            return cls(
                execution_mode=mode,
                warn_missing_fields=False,
                run_validators=False,
                emit_provenance=False,
                log_context_injection=False,
                detect_staleness=False,
                detailed_cost_reporting=False,
                require_otel=False,
            )
        elif mode == ExecutionMode.PIPELINE:
            return cls(
                execution_mode=mode,
                warn_missing_fields=True,
                run_validators=True,
                emit_provenance=True,
                log_context_injection=True,
                detect_staleness=True,
                detailed_cost_reporting=True,
                require_otel=True,
            )
        raise ValueError(f"Unknown execution mode: {mode}")
```

**ModeConfig / ContextResolutionStrategy relationship:** `ModeConfig` holds declarative boolean flags derived from `ExecutionMode`. The `ContextResolutionStrategy` implements behavioral differences in context resolution. `ModeConfig` determines *which* strategy is selected (standalone or pipeline) and governs non-context behaviors (logging, provenance, validation). The strategy does not read `ModeConfig` — it encapsulates its own context-building logic.

**CLI flag precedence:** CLI flags ALWAYS take precedence over `ModeConfig` defaults. Conflicting flags (e.g., `--validate` and `--no-validate` together) MUST raise a CLI parsing error. The precedence chain is: CLI flag > ModeConfig profile > ExecutionMode default.

**Acceptance criteria:**
- Configuration is a `ModeConfig` frozen dataclass derived from the `ExecutionMode` via `ModeConfig.for_mode()`
- `ModeConfig` fields correspond one-to-one with the behavior rows in the table above
- CLI overrides produce a new `ModeConfig` via `dataclasses.replace()` (not mutation of frozen instance)
- Individual behaviors can be overridden via CLI flags (e.g., `--validate` forces validation in standalone mode)
- The mode config is accessible from the workflow instance: `workflow.mode_config`

---

### Layer 2: Context Resolution Strategy (REQ-PEM-004–008)

#### REQ-PEM-004: ContextResolutionStrategy Protocol

**Priority:** P1
**Implementation Status:** ✅ Complete — protocol defined in `protocols.py` with `ValidationConfig` and `ValidationResult`
**Source files:** `src/startd8/contractors/prime_contractor.py` (new protocol)

A `ContextResolutionStrategy` protocol MUST define the interface for building generation context:

```python
@runtime_checkable
class ContextResolutionStrategy(Protocol):
    def resolve_seed_context(self, seed_data: dict) -> SeedContext: ...
    def resolve_task_context(self, feature: FeatureSpec, seed_ctx: SeedContext) -> dict: ...
    def resolve_validation_config(self, feature: FeatureSpec) -> ValidationConfig: ...
```

Where:
- `SeedContext` is a structured container for seed-level data (onboarding, architectural_context, design_calibration, service_metadata, plan_document_text)
- `resolve_task_context()` returns the `gen_context` dict that `CodeGenerator.generate()` receives
- `resolve_validation_config()` returns a `ValidationConfig` specifying validators to run after generation

**Error semantics for protocol methods:** Strategy method implementations MUST distinguish between "resolved successfully with empty data" and "resolution failed due to I/O or parsing error." On successful resolution with empty or missing source data, methods MUST return their normal return type with empty/default values (e.g., `SeedContext` with empty dicts, `ValidationConfig` with empty validator list, `gen_context` dict with only always-present sections). On resolution failure due to I/O errors, permission errors, or parsing errors (e.g., corrupt JSON in context files, unreadable plan document), methods MUST raise `ContextResolutionError` (a new exception subclass of `RuntimeError`) with a descriptive message indicating the failed resource and root cause. The workflow MUST catch `ContextResolutionError` at the call site and handle it according to mode: in standalone mode, log a warning and continue with empty defaults; in pipeline mode, log an error and — depending on which method failed — either continue with degraded context (`resolve_validation_config`) or handle as specified below for `resolve_seed_context` and `resolve_task_context`.

**Pipeline mode error handling by method:**
- `resolve_seed_context` failure: abort the workflow, since no seed context means no meaningful generation.
- `resolve_task_context` failure: the workflow MUST mark the feature as `failed` (not attempt generation with degraded context), log the error with full exception details, and continue to the next feature. Generation with incomplete context risks producing subtly wrong code that passes compilation but violates domain constraints. The feature's status in the generation manifest MUST be recorded as `"failed"` with the `ContextResolutionError` message captured in the feature's manifest entry.
- `resolve_validation_config` failure: continue with degraded context (empty validator list), since validation is a quality gate, not a generation prerequisite.

This distinction enables callers to implement appropriate recovery strategies per mode.

**Strategy initialization:** Strategy implementations MAY accept configuration via `__init__`. The workflow MUST pass `project_root: Path` and `output_dir: Path` to the strategy constructor. `project_root` is required for path traversal validation (REQ-PEM-018), and `output_dir` is required for manifest reading during staleness detection (REQ-PEM-013). The protocol defines only the three resolution methods; constructor signatures are implementation-specific and not constrained by the protocol.

**`ValidationConfig` dataclass:**
```python
@dataclass
class ValidationConfig:
    validators: List[Callable[[List[Path]], ValidationResult]]  # Validator callables
    fail_on_warning: bool = False                                # Treat warnings as failures
    skip_validators: List[str] = field(default_factory=list)     # Validator names to skip

@dataclass
class ValidationResult:
    validator_name: str         # Canonical name (e.g., "import_dependency")
    severity: str               # "pass" | "warn" | "fail"
    findings: List[str]         # Human-readable findings
```

Validators MUST come from a pre-approved, code-defined registry — never from seed data or external input (prevents RCE via dynamic class loading). Canonical validator names: `import_dependency`, `protocol_fidelity`, `placeholder_detection`, `dockerfile_coherence`.

**Acceptance criteria:**
- Protocol is defined in `protocols.py` alongside existing protocols
- Two implementations: `StandaloneContextStrategy` and `PipelineContextStrategy`
- `PrimeContractorWorkflow` accepts an optional `context_strategy` parameter; defaults based on `ExecutionMode`
- Both strategy implementations accept `project_root: Path` and `output_dir: Path` as constructor parameters
- `ContextResolutionError` is defined and raised on I/O or parsing failures within strategy methods
- Callers handle `ContextResolutionError` with mode-appropriate recovery (standalone: warn + defaults; pipeline: error + degrade or abort as specified per method)
- In pipeline mode, `resolve_task_context` failure marks the feature as `failed` and continues to the next feature (does not attempt generation with incomplete context)

---

#### REQ-PEM-005: SeedContext Dataclass

**Priority:** P1
**Implementation Status:** ✅ Complete — `SeedContext` dataclass with property accessors, lifecycle enforcement
**Source files:** `src/startd8/contractors/prime_contractor.py` or new `context_resolution.py`

Seed-level context MUST be stored in a typed `SeedContext` dataclass, replacing the current pattern of ad-hoc instance attributes:

```python
@dataclass
class SeedContext:
    onboarding: Dict[str, Any] = field(default_factory=dict)
    architectural_context: Dict[str, Any] = field(default_factory=dict)
    design_calibration: Dict[str, Any] = field(default_factory=dict)
    service_metadata: Dict[str, Any] = field(default_factory=dict)
    plan_document_text: Optional[str] = None
    context_files: List[ContextFileEntry] = field(default_factory=list)
    source_checksum: Optional[str] = None
    execution_mode: ExecutionMode = ExecutionMode.STANDALONE
```

**`ContextFileEntry` schema:**
```python
class ContextFileEntry(TypedDict):
    path: str                  # File path (relative to project root)
    name: str                  # Human-readable name
    type: str                  # "plan_document" | "design_reference" | "context"
    content: NotRequired[str]  # Loaded content (populated during resolution)
```

**`source_checksum` in pipeline mode:** In pipeline mode, `source_checksum` SHOULD be present for staleness detection. If absent, the pipeline strategy logs a warning (`"Pipeline mode: missing source_checksum — staleness detection disabled for this run"`) and skips staleness checks (does not fail fast). The checksum is computed upstream as SHA-256 over the canonical JSON form of the seed (sorted keys, no whitespace).

**SeedContext lifecycle:**
- `SeedContext` is populated during workflow initialization (via `load_seed_context()` or property setters for backward compatibility)
- After the execution phase begins (first call to `_generate_code()`), `SeedContext` is treated as immutable — no further modifications
- `SeedContext.execution_mode` is for serialization/round-trip only; `workflow.mode` is the runtime authority. These MUST always be synchronized. During deserialization (e.g., resume from state), if `SeedContext.execution_mode` differs from the persisted `workflow.mode` in `.prime_contractor_state.json`, the system MUST use the workflow-level mode as authoritative and overwrite `SeedContext.execution_mode` to match, logging a warning: `"SeedContext.execution_mode ({seed_mode}) differs from workflow mode ({workflow_mode}) — using workflow mode as authoritative"`. This prevents dual-authority conflicts where the two values diverge due to manual state editing or serialization bugs.

**Pipeline mode missing-field behavior:** Pipeline mode checks for key *presence* in the raw seed data before applying defaults. A field that is absent from the seed triggers a warning. A field that is present but empty (`{}` or `[]`) is treated as present but produces no context section (omitted from `gen_context`).

**Acceptance criteria:**
- Replaces `workflow.seed_onboarding`, `workflow.seed_architectural_context`, `workflow.seed_design_calibration`, `workflow.seed_service_metadata`, `workflow.plan_document_text` instance attributes
- `SeedContext` is populated during workflow initialization and treated as immutable after the execution phase begins
- Existing code that reads `workflow.seed_*` attributes MUST continue to work (property accessors delegate to `SeedContext`)
- When no seed file is provided (seedless `add_feature()` path per REQ-PEM-010), `SeedContext` is initialized with all defaults (empty dicts, None) and `execution_mode=STANDALONE`
- On deserialization, `SeedContext.execution_mode` is reconciled to match `workflow.mode`

---

#### REQ-PEM-006: StandaloneContextStrategy

**Priority:** P1
**Source files:** new `src/startd8/contractors/context_resolution.py`

The standalone strategy MUST reproduce current behavior:

**`resolve_seed_context(seed_data)`:**
- Extract `onboarding`, `architectural_context`, `design_calibration`, `service_metadata` with `dict.get(key, {})` defaults
- Extract `plan_document_text` if `artifacts.plan_document_path` exists and the file is readable
- All missing fields default to empty dict/None — no warnings, no errors

**`resolve_task_context(feature, seed_ctx)`:**
- Build `gen_context` dict exactly as current `_generate_code()` does (lines 484–560 of `prime_contractor.py`)
- No additional context injection beyond what exists today

**`resolve_validation_config(feature)`:**
- Return empty validator list (no post-generation validation)

**Error handling:** If `resolve_seed_context()` encounters a file read error for `context_files` entries (missing or unreadable files), it MUST log a warning and omit the file — not raise an exception. All file paths from seed MUST be validated against the project root to prevent path traversal (see REQ-PEM-018).

**Acceptance criteria:**
- Existing tests pass without modification
- Output is structurally equivalent to current behavior for the same inputs — `resolve_task_context()` produces a dict with identical keys and values (order-independent comparison via `dict.__eq__`), not byte-level identity
- No new dependencies

---

#### REQ-PEM-007: PipelineContextStrategy

**Priority:** P1
**Source files:** new `src/startd8/contractors/context_resolution.py`

The pipeline strategy MUST exploit full pipeline context:

**`resolve_seed_context(seed_data)`:**
- Extract all fields from seed with type validation
- Log missing fields with warnings per REQ-PC-014: `"Pipeline mode: missing {field} — generation quality may be reduced"`
- Validate `source_checksum` is present (for staleness detection per REQ-PC-011)
- Extract `context_files` for plan document and design references

**`resolve_task_context(feature, seed_ctx)`:**
- Build `gen_context` with structured sections (per IMP-P1):
  - `general_context`: feature name, description, target files — **always present**
  - `architectural_context`: from `seed_ctx.architectural_context` — **include if non-empty, otherwise omit**
  - `requirements_context`: from `feature.metadata["requirements_text"]` (per IMP-P2) — **include if non-empty, otherwise omit**
  - `domain_constraints`: categorized by priority (per IMP-P5) — **include if constraints exist, otherwise omit**
  - `critical_parameters`: elevated from enrichment (per IMP-P3) — **include if non-empty, otherwise omit**
  - `protocol_guidance`: derived from `seed_ctx.service_metadata` (per IMP-P4) — **include if service_metadata non-empty, otherwise omit**
  - `plan_context`: feature-specific excerpt from plan document (per REQ-PC-004) — **include if plan_document_text non-empty, otherwise omit**
  - `semantic_conventions`: from `seed_ctx.onboarding` (per REQ-PC-001) — **include if onboarding non-empty, otherwise omit**
  - `scope_boundary`: "Generate only what is specified" instruction (per REQ-PC-008) — **always present**
- **Empty field rule:** Context sections for which the source data is present but empty (e.g., `{}` or `[]`) MUST be omitted from `gen_context` — not included as empty headers. This prevents noise in LLM prompts.
- Log injected vs. missing context fields per REQ-PC-014
- All user-controlled data from seed MUST be wrapped in safe delimiters (e.g., XML tags like `<context>...</context>`) before injection into prompts, to mitigate prompt injection risks (see REQ-PEM-018). User-controlled content MUST have any occurrences of the closing delimiter tag escaped (e.g., replace `</context>` with `&lt;/context&gt;`) before wrapping, to prevent delimiter injection from breaking the isolation boundary.

**Architectural context transformation:** Raw JSON from `seed_ctx.architectural_context` is transformed to Markdown:
- Top-level JSON keys → `### {key}` Markdown headers
- Arrays → bullet lists
- Nested objects → indented sub-sections
- Scalar values → inline text
- Example: `{"patterns": ["MVVM", "Repository"], "stack": "Python 3.14"}` → `### Patterns\n- MVVM\n- Repository\n### Stack\nPython 3.14`

**Plan context extraction algorithm:** Feature-specific plan excerpt MUST be extracted by searching for the feature name (case-insensitive) in plan document section headings (lines starting with `#`). If a matching section is found, the excerpt includes that section and all content until the next section heading of equal or higher level. If no matching section is found, include the first 2000 characters of the plan document as fallback. This ensures relevant plan context is included without consuming excessive LLM tokens on large plan documents.

**`requirements_text` canonical path:** The authoritative location is `feature.metadata["requirements_text"]`. This field is populated from the enriched seed during `add_features_from_seed()` (see REQ-PEM-009). It is NOT a top-level `FeatureSpec` field.

**`resolve_validation_config(feature)`:**
- Return validator list based on `feature.metadata` enrichment:
  - Import/dependency cross-validation (AR-143 equivalent)
  - Protocol fidelity (AR-144 equivalent, requires `service_metadata`)
  - Placeholder detection (AR-146 equivalent)
  - Dockerfile/service coherence (AR-147 equivalent, requires `service_metadata`)
- Validators that lack required data (e.g., protocol fidelity without service_metadata) MUST be skipped with a warning

**Acceptance criteria:**
- All IMP-P1 through IMP-P6 prompt improvements are active in pipeline mode
- All REQ-PC-001 through REQ-PC-004 context injection requirements are satisfied
- REQ-PC-007 (service metadata awareness) is satisfied
- REQ-PC-008 (scope boundary enforcement) is satisfied
- REQ-PC-009 (post-generation validation) is satisfied
- Context injection is logged per REQ-PC-014
- Plan context extraction uses feature-name heading search with 2000-character fallback

---

#### REQ-PEM-008: Spec-to-Draft Validation (Pipeline Only)

**Priority:** P2
**Source files:** `src/startd8/workflows/builtin/lead_contractor_workflow.py`

In pipeline mode, after `_create_spec()` and before `_create_draft()`, the system MUST run the spec completeness check from IMP-P6:

- Scan spec text for resolved parameters from enrichment
- Missing parameters generate a `## Spec Completeness Warning` section injected into drafter feedback
- Uses shared `find_missing_parameters()` from `prompt_utils.py`

**`find_missing_parameters()` definition** (located in `src/startd8/contractors/prompt_utils.py`):
```python
def find_missing_parameters(
    text: str,
    resolved_parameters: Dict[str, str],
) -> List[str]:
    """Scan text for resolved parameter key values; return names of missing ones.
    
    Args:
        text: The spec/design text to scan
        resolved_parameters: Dict mapping parameter names to their resolved values
        
    Returns:
        List of parameter names whose values are not found in the text
        (case-insensitive substring search)
    """
```
- Input: the spec/design text and the `resolved_parameters` dict from enrichment
- Output: list of parameter names whose values are not found in the text (case-insensitive substring search)
- This is a text-only check (no LLM call)

**`resolved_parameters` data source:** The `resolved_parameters` dict is constructed from `feature.metadata['_enrichment']` by extracting all key-value pairs where the value is a non-empty string. If `_enrichment` is absent or empty, the spec completeness check is skipped entirely (no warning injected, no error raised). This ensures the check degrades gracefully when enrichment data is unavailable, which is expected in standalone mode and possible in early pipeline development.

In standalone mode, this check MUST be skipped (no enrichment data to validate against).

**Acceptance criteria:**
- Pipeline mode: missing parameters produce warning in drafter context
- Standalone mode: no warning injected
- Check is text-only (no LLM call)
- Check is skipped when `feature.metadata['_enrichment']` is absent or empty

---

### Layer 3: Feature Loading (REQ-PEM-009–010)

#### REQ-PEM-009: Unified Feature Loading

**Priority:** P1
**Source files:** `src/startd8/contractors/queue.py`

`FeatureQueue.add_features_from_seed()` MUST preserve all enrichment data regardless of execution mode:

- `FeatureSpec.metadata` MUST capture: `_enrichment`, `artifact_types_addressed`, `design_doc_sections`, `estimated_loc`, `requirements_text`, `api_signatures`, `protocol`, `runtime_dependencies`, `negative_scope`
- `FeatureSpec.metadata` MUST preserve all keys present in the enriched seed, not only the nine listed fields. Unknown keys MUST be round-tripped through `to_dict()`/`from_dict()` without modification. This ensures forward compatibility as upstream pipeline stages evolve and add new enrichment fields.
- In standalone mode, most of these will be empty — that's expected
- In pipeline mode, these are populated from the enriched seed

**Metadata key conflict resolution:** When enrichment data from the seed contains keys that shadow `FeatureSpec` primary fields (e.g., `id`, `name`, `description`, `target_files`), the `FeatureSpec` primary field value MUST take precedence. The conflicting metadata key MUST be dropped from `FeatureSpec.metadata`, and a warning MUST be logged: `"Enrichment key '{key}' shadows FeatureSpec primary field — primary field value retained, metadata key dropped"`. This prevents ambiguity in serialization round-trips where both `FeatureSpec.name` and `FeatureSpec.metadata["name"]` could exist with different values. The list of protected primary field names is: `id`, `name`, `description`, `target_files`, `status`, `priority`, `dependencies`.

**Acceptance criteria:**
- `FeatureSpec.metadata` round-trips through `to_dict()` / `from_dict()` (REQ-PC-006)
- No data loss at the queue boundary (REQ-PC-005)
- Unknown/additional metadata keys from the enriched seed are preserved through round-trip serialization
- Enrichment keys that shadow FeatureSpec primary fields are dropped with a warning (primary field wins)

---

#### REQ-PEM-010: Standalone Feature Construction

**Priority:** P2
**Source files:** `src/startd8/contractors/queue.py`

For standalone usage without a full seed file, `FeatureQueue` MUST support adding features from minimal specifications:

```python
queue.add_feature(
    id="my-feature",
    name="Add login endpoint",
    description="Create a /login POST endpoint...",
    target_files=["src/auth.py"],
)
```

**Seedless initialization:** When using `add_feature()` without a seed file, workflow-level configuration (output directory, model selection, global settings) MUST be provided via `PrimeContractorWorkflow` constructor parameters. `SeedContext` is initialized with all defaults (empty dicts, None, `STANDALONE` mode). The workflow MUST be fully functional in this configuration.

**Acceptance criteria:**
- `add_feature()` creates a `FeatureSpec` with empty metadata (all enrichment fields absent)
- Works without a seed file — constructor parameters supply workflow-level config
- Existing `add_features_from_seed()` continues to work unchanged

---

### Layer 4: Output Contract (REQ-PEM-011–014)

#### REQ-PEM-011: Mode-Specific Output

**Priority:** P1
**Source files:** `src/startd8/contractors/prime_contractor.py`

The Prime Contractor's output MUST vary by mode:

| Output | STANDALONE | PIPELINE |
|--------|-----------|----------|
| Generated files | Yes | Yes |
| `prime-result.json` | Yes | Yes |
| `.prime_contractor_state.json` | Yes | Yes |
| `generation-manifest.json` | No | Yes (per REQ-PC-011) |
| Per-feature cost report | Summary line | Structured JSON (per REQ-PC-013) |
| OTel spans | Only if instrumentor configured | Yes (via ContextCoreInstrumentor) |

**Acceptance criteria:**
- Standalone mode produces exactly the same output as current behavior
- Pipeline mode adds provenance manifest and structured cost report
- Output behavior is determined by `ModeConfig`, not hardcoded checks

---

#### REQ-PEM-012: Generation Manifest (Pipeline Only)

**Priority:** P2
**Source files:** `src/startd8/contractors/prime_contractor.py`

In pipeline mode, after all features are processed, the workflow MUST write `generation-manifest.json`:

```json
{
  "schema_version": "1.0.0",
  "workflow": "PrimeContractorWorkflow",
  "execution_mode": "pipeline",
  "source_checksum": "<from seed>",
  "workflow_id": "<unique run ID>",
  "generated_at": "<ISO-8601>",
  "force_regenerate": false,
  "effective_config": {
    "execution_mode": "pipeline",
    "run_validators": false,
    "emit_provenance": true,
    "detect_staleness": true,
    "log_context_injection": true
  },
  "features": {
    "<task_id>": {
      "status": "success|failed|skipped",
      "generated_files": ["..."],
      "cost_usd": 0.52,
      "model": "anthropic:claude-sonnet-4-20250514",
      "validators_run": ["import_dependency", "placeholder_detection"],
      "validator_results": {
        "import_dependency": {"outcome": "pass", "findings": []},
        "placeholder_detection": {"outcome": "warn", "findings": ["Missing import: os.path in generated auth.py"]}
      }
    }
  },
  "total_cost_usd": 5.23,
  "total_features": 10,
  "succeeded": 9,
  "failed": 1
}
```

**Model field data flow:** The `model` field per feature is populated from the `CodeGenerator.generate()` return value. The generator MUST return or expose the model spec used (e.g., `anthropic:claude-sonnet-4-20250514`). If unavailable, use `"unknown"`.

**Force regenerate recording:** The manifest MUST include a `force_regenerate` field (boolean) indicating whether `--force-regenerate` was used for this run. This provides provenance information explaining why the cache may have been bypassed.

**Effective configuration:** The manifest MUST include an `effective_config` object capturing the final `ModeConfig` state after CLI overrides, enabling run reproducibility.

**Schema version compatibility:** The manifest MUST include a `schema_version` field. Consumers MUST handle manifests with unknown `schema_version` by logging a warning and skipping staleness checks (best-effort read, not hard failure). This enables forward compatibility when schema evolves.

**Validator results schema:** The `validator_results` object MUST capture both the outcome and diagnostic findings for each validator. Each validator entry MUST be an object with `outcome` (string: `"pass"`, `"warn"`, or `"fail"`) and `findings` (array of strings: human-readable diagnostic messages from the `ValidationResult.findings` field). This ensures the manifest — as the only persistent record of validation results consumed by Stage 7 validators and developers — contains sufficient diagnostic detail without requiring downstream consumers to re-run validation. Example:
```json
"validator_results": {
  "import_dependency": {"outcome": "pass", "findings": []},
  "placeholder_detection": {"outcome": "warn", "findings": ["Placeholder 'TODO' found in generated auth.py line 42"]}
}
```

**I/O error handling:** A failure to write `generation-manifest.json` due to an I/O error MUST be logged as an error but MUST NOT cause the entire workflow to fail. Generation results are preserved regardless of manifest write success.

**File permissions:** The manifest MUST be written with restrictive permissions (0o600) since it contains cost data that may be sensitive in pipeline deployments.

**Known downstream consumers:** Stage 7 validators, OTel dashboards, pipeline orchestrator staleness checks. Changes to the manifest schema MUST be coordinated with these consumers.

**Acceptance criteria:**
- Manifest written to `{output_dir}/generation-manifest.json` with 0o600 permissions
- `source_checksum` matches the seed's checksum (for staleness detection)
- Manifest is machine-readable (JSON) for downstream pipeline stages
- `effective_config` reflects final ModeConfig including CLI overrides
- `force_regenerate` field accurately reflects whether the flag was used
- `validator_results` per feature includes both `outcome` and `findings` (not just outcome string)
- System MUST handle manifests with unknown schema versions by logging warning and skipping staleness check

---

#### REQ-PEM-013: Staleness Detection (Pipeline Only)

**Priority:** P2
**Source files:** `src/startd8/contractors/prime_contractor.py`

Before reusing cached generation results, the pipeline strategy MUST compare provenance using `source_checksum` only (content-addressable — identical inputs should produce reusable outputs regardless of run ID):

- Read existing `generation-manifest.json` if present
- If manifest is unparsable (corrupt JSON), log a warning and treat as absent
- Compare `source_checksum` from manifest against current seed's checksum
- **Match:** reuse cached results (log `"Staleness check: current (checksum match)"`)
- **Mismatch:** regenerate (log `"Staleness check: stale (checksum mismatch: {old} → {new})"`)
- **No manifest or no checksum:** regenerate (log `"Staleness check: no provenance, treating as stale"`)

The `workflow_id` in the manifest is for provenance tracking only — it is NOT used in the staleness comparison. Different runs with identical seeds should reuse cached results.

**Force regenerate interaction with staleness logging:** When `--force-regenerate` is active, the staleness comparison MUST still be performed and logged, followed by: `"Force regenerate active — bypassing cache despite {result}"` where `{result}` is `"checksum match"`, `"checksum mismatch"`, or `"no provenance"`. This ensures operators investigating cache behavior can determine whether the cache would have been valid, aiding debugging and cost analysis.

In standalone mode, staleness detection MUST be skipped (no provenance chain).

**Checksum computation for testing:** The checksum is SHA-256 computed over the canonical JSON form of the seed (sorted keys, no whitespace). Test fixtures MUST be generated using the same canonicalization algorithm: `hashlib.sha256(json.dumps(seed_data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()`. This ensures deterministic checksums for test assertions.

**Acceptance criteria:**
- Implements REQ-PC-011 (staleness detection) for pipeline mode
- Staleness is determined by `source_checksum` comparison only
- Corrupt/unparsable manifest is handled gracefully (warning + regenerate)
- Standalone mode: existing files are reused based only on `FeatureQueue` status (current behavior)
- `--force-regenerate` flag bypasses staleness check in both modes (REQ-PC-012)
- When `--force-regenerate` is active, staleness comparison is still performed and logged before bypass

---

#### REQ-PEM-014: Validation Results in Output

**Priority:** P2
**Source files:** `src/startd8/contractors/prime_contractor.py`

In pipeline mode, post-generation validation results MUST appear in both the generation manifest and the `prime-result.json`:

- Per-feature: validator names, pass/warn/fail counts, specific findings
- Summary: total validations run, total pass, total warn, total fail

In standalone mode, validation fields MUST be absent from output (not empty — absent).

**Exit code semantics:**
- Successful completion MUST exit with code 0.
- Generation failures (e.g., LLM errors, I/O errors) MUST exit with code 1.
- Validation failures with `--strict-validation` MUST exit with code 2. This enables pipeline orchestrators to distinguish retry-worthy failures (code 1) from failures requiring human attention (code 2).

**`--strict-validation` semantics:** When passed, the workflow MUST process all features to completion before evaluating the strict-validation exit code. The workflow MUST NOT exit early on the first validation failure. This ensures the generation manifest contains comprehensive results for all features, enabling pipeline orchestrators and developers to assess the full scope of validation findings in a single run. After all features are processed, if any validation finding has severity `"fail"`, the workflow exits with exit code 2. Without this flag, validation results are informational only. `--strict-validation` and `--no-validate` are mutually exclusive — passing both MUST raise a CLI parsing error.

**Acceptance criteria:**
- Pipeline output includes `validators_run` and `validator_results` per feature
- Standalone output is identical to current format (no new fields)
- Validation severity does not affect exit code unless `--strict-validation` is passed
- With `--strict-validation`, all features are processed before exit code is determined (no early termination)
- `--strict-validation` combined with `--no-validate` produces CLI error
- Exit code 0 for success, 1 for generation failure, 2 for `--strict-validation` failure

---

### Layer 5: Backward Compatibility (REQ-PEM-015–017)

#### REQ-PEM-015: Zero-Change Standalone

**Priority:** P1

All existing standalone usage patterns MUST continue to work without any changes:

- `scripts/run_prime_workflow.py` with a simple seed file
- `PrimeContractorWorkflow` constructed without mode/strategy arguments
- Existing test suites

**Acceptance criteria:**
- All existing tests pass without modification
- Default behavior (no explicit mode) matches current behavior exactly
- No new required constructor parameters

---

#### REQ-PEM-016: Script Compatibility

**Priority:** P1
**Source files:** `scripts/run_prime_workflow.py`

The runner script MUST support both modes:

```bash
# Current usage (unchanged, defaults to auto-detect)
python3 scripts/run_prime_workflow.py --seed path/to/seed.json

# Explicit standalone (forces minimal context, no validators)
python3 scripts/run_prime_workflow.py --seed path/to/seed.json --mode standalone

# Explicit pipeline (forces full context, validates, emits provenance)
python3 scripts/run_prime_workflow.py --seed path/to/seed.json --mode pipeline

# Override individual behaviors
python3 scripts/run_prime_workflow.py --seed path/to/seed.json --validate --force-regenerate

# Strict validation (non-zero exit on validation failures)
python3 scripts/run_prime_workflow.py --seed path/to/seed.json --mode pipeline --strict-validation
```

**Acceptance criteria:**
- `--mode` argument is optional; default is auto-detect
- Invalid `--mode` values produce user-friendly error and non-zero exit
- `--validate` flag forces post-generation validation regardless of mode
- `--no-validate` flag disables validation even in pipeline mode
- `--strict-validation` flag causes non-zero exit on validation failures
- `--force-regenerate` flag forces regeneration regardless of mode or cache
- Conflicting flags (`--validate` + `--no-validate`, or `--strict-validation` + `--no-validate`) MUST raise CLI parsing error

---

#### REQ-PEM-017: Property Accessor Compatibility

**Priority:** P1
**Source files:** `src/startd8/contractors/prime_contractor.py`

The following instance attributes MUST remain accessible as properties on `PrimeContractorWorkflow`, delegating to `SeedContext`:

- `workflow.seed_onboarding` → `workflow.seed_context.onboarding`
- `workflow.seed_architectural_context` → `workflow.seed_context.architectural_context`
- `workflow.seed_design_calibration` → `workflow.seed_context.design_calibration`
- `workflow.seed_service_metadata` → `workflow.seed_context.service_metadata`
- `workflow.plan_document_text` → `workflow.seed_context.plan_document_text`

**Pre-initialization behavior:** Property accessors MUST return empty defaults (empty dict for dict fields, `None` for optional fields) if `SeedContext` has not yet been initialized. This supports code that checks seed properties during construction, before `load_seed_context()` or seed loading has completed. Internally, this MAY be implemented by eagerly initializing `SeedContext` with all defaults at workflow construction time, or by having property getters check for an uninitialized state and return appropriate defaults. The key invariant is that property access MUST never raise `AttributeError` regardless of when it occurs in the workflow lifecycle.

**Lifecycle constraint:** Property setters are valid during the initialization phase (before `_generate_code()` is first called). For the purpose of this requirement, "execution begins" is defined as the first invocation of the internal `_generate_code()` method. Setters update the underlying `SeedContext` fields. After the execution phase begins, `SeedContext` is treated as immutable per REQ-PEM-005. Property setters invoked after execution begins MUST raise `RuntimeError("SeedContext is immutable after execution begins")` to enforce the immutability contract programmatically and prevent subtle state corruption.

**Acceptance criteria:**
- Existing code that reads `workflow.seed_onboarding` continues to work
- Existing code that writes `workflow.seed_onboarding = {...}` continues to work during initialization (setter populates `SeedContext`)
- Property accessors return empty defaults (empty dict or None) before SeedContext is initialized — never raise `AttributeError`
- Property setters raise `RuntimeError` if called after execution begins
- Deprecation warnings are NOT emitted (these accessors are the stable API)

---

### Layer 6: Security (REQ-PEM-018)

#### REQ-PEM-018: Secure Input Handling

**Priority:** P1
**Source files:** `src/startd8/contractors/context_resolution.py`, `src/startd8/contractors/prime_contractor.py`

All external inputs from the seed file MUST be validated and sanitized before use:

**Path traversal protection:**
- All file paths from seed (`context_files`, `plan_document_path`, `artifacts.*`) MUST be validated as within the project root directory
- Path sanitization MUST resolve symlinks and verify the canonical path is within project root
- Paths containing `..` or absolute paths outside the project root MUST be rejected with a logged error
- Symlinks that resolve to paths escaping the project root MUST be rejected
- Uses the existing `sanitize_path()` utility from the artisan route (or implements equivalent logic if not available)

**Prompt injection mitigation:**
- User-controlled data injected into LLM prompts (e.g., `project_objectives`, `architectural_context`, `requirements_text`) MUST be wrapped in safe delimiters (e.g., `<context type="architectural">...</context>`) to isolate from prompt instructions
- User-controlled content MUST have any occurrences of the closing delimiter tag escaped (e.g., replace `</context>` with `&lt;/context&gt;`) before wrapping. This prevents delimiter injection attacks where user content containing the closing tag would break the isolation boundary. Alternatively, implementations MAY use content-hash-based unique delimiters (e.g., `<context-a7f3b2>...</context-a7f3b2>`) that are computationally infeasible to predict from user input.
- The system prompt MUST explicitly instruct the LLM to treat content within safe delimiters as non-instructional context that should inform the response but never be interpreted as commands or instructions to the model
- This is defense-in-depth — not a guarantee against all injection attacks, but standard practice

**Validator registry security:**
- Post-generation validators MUST come from a pre-approved, code-defined registry only
- The seed file MUST NOT be able to specify arbitrary validator class names or paths (prevents RCE)
- Validator names in `ValidationConfig` are looked up against the registry; unknown names are logged and skipped

**State file security:**
- `.prime_contractor_state.json` MUST use file-level locking (e.g., `fcntl.flock`) for resumability to prevent corruption from concurrent access
- `.prime_contractor_state.json` MUST be written with restrictive permissions (0o600) to prevent tampering with execution state in pipeline deployments. The state file contains the execution mode, seed checksum, and feature queue status — tampering could skip features, change the execution mode, or corrupt the resume state.

**Acceptance criteria:**
- Path traversal attack on `context_files` raises error and is logged
- Prompt content from seed is wrapped in safe delimiters in generated prompts
- Closing delimiter tags within user content are escaped before wrapping
- System prompt includes instruction to treat delimited content as non-instructional
- Arbitrary validator names from seed are rejected (not dynamically loaded)
- Concurrent state file access does not corrupt state
- `.prime_contractor_state.json` is written with 0o600 permissions

---

## Traceability Matrix

### REQ-PEM → REQ-PC (Functional Requirements)

| REQ-PEM | Implements | Description |
|---------|-----------|-------------|
| REQ-PEM-003 | REQ-PC-014 | Context injection logging (pipeline mode) |
| REQ-PEM-007 | REQ-PC-001, 002, 003, 004 | Full context injection in pipeline mode |
| REQ-PEM-007 | REQ-PC-007, 008 | Service metadata awareness + scope boundary |
| REQ-PEM-007 | REQ-PC-009 | Post-generation validation (pipeline mode) |
| REQ-PEM-008 | IMP-P6 | Spec-to-draft validation (pipeline mode) |
| REQ-PEM-009 | REQ-PC-005, 006 | Queue boundary metadata preservation |
| REQ-PEM-012 | REQ-PC-011 | Staleness detection via provenance |
| REQ-PEM-013 | REQ-PC-011 | Staleness detection enforcement |
| REQ-PEM-014 | REQ-PC-009 | Validation results in output |

### REQ-PEM → IMP-P (Prompt Quality)

| REQ-PEM | Implements | Description |
|---------|-----------|-------------|
| REQ-PEM-007 | IMP-P1 | Structured context sections |
| REQ-PEM-007 | IMP-P2 | Requirements text passthrough |
| REQ-PEM-007 | IMP-P3 | Critical parameter elevation |
| REQ-PEM-007 | IMP-P4 | Protocol-aware spec guidance |
| REQ-PEM-007 | IMP-P5 | Constraint categorization |
| REQ-PEM-008 | IMP-P6 | Spec-to-draft validation |

### REQ-PEM → Upstream Dependencies

| REQ-PEM | Depends On | Why |
|---------|-----------|-----|
| REQ-PEM-007 | REQ-PI-001, 002 | Onboarding data must be in seed |
| REQ-PEM-007 | REQ-PI-003, 004 | Architectural context + design calibration must be in seed |
| REQ-PEM-007 | REQ-PI-006, 007, 008 | Service metadata must be in seed |
| REQ-PEM-013 | REQ-PI-011 | Route-agnostic seed quality |

---

## Verification

### Test Strategy

| # | Test | Validates | Mode |
|---|------|-----------|------|
| 1 | Default mode = `STANDALONE` when no signals | REQ-PEM-001, 002 | Both |
| 2 | Auto-detect `PIPELINE` from onboarding in seed | REQ-PEM-002 | Pipeline |
| 3 | Explicit `--mode standalone` overrides auto-detect | REQ-PEM-002 | Standalone |
| 4 | `SeedContext` replaces instance attributes | REQ-PEM-005 | Both |
| 5 | Property accessors backward-compatible | REQ-PEM-017 | Both |
| 6 | Standalone strategy produces structurally equivalent gen_context | REQ-PEM-006 | Standalone |
| 7 | Pipeline strategy includes structured sections when data present | REQ-PEM-007 | Pipeline |
| 8 | Pipeline strategy logs missing fields | REQ-PEM-007 | Pipeline |
| 9 | Pipeline strategy omits sections for empty data | REQ-PEM-007 | Pipeline |
| 10 | Spec-to-draft validation in pipeline mode | REQ-PEM-008 | Pipeline |
| 11 | Spec-to-draft validation skipped in standalone | REQ-PEM-008 | Standalone |
| 12 | FeatureSpec metadata round-trips (including unknown keys) | REQ-PEM-009 | Both |
| 13 | add_feature() works without seed | REQ-PEM-010 | Standalone |
| 14 | Generation manifest written in pipeline mode | REQ-PEM-012 | Pipeline |
| 15 | Generation manifest NOT written in standalone | REQ-PEM-011 | Standalone |
| 16 | Staleness detection: matching checksum reuses (verified by: zero LLM API calls, no file modifications in output directory, log message "Staleness check: current (checksum match)") | REQ-PEM-013 | Pipeline |
| 17 | Staleness detection: mismatch regenerates | REQ-PEM-013 | Pipeline |
| 18 | Staleness detection: corrupt manifest handled gracefully | REQ-PEM-013 | Pipeline |
| 19 | `--force-regenerate` bypasses staleness (staleness comparison still logged before bypass) | REQ-PEM-013 | Both |
| 20 | Validation results in pipeline output | REQ-PEM-014 | Pipeline |
| 21 | `--strict-validation` causes exit code 2 on failures (after all features complete) | REQ-PEM-014 | Pipeline |
| 22 | Existing tests pass unchanged | REQ-PEM-015 | Both |
| 23 | Script accepts `--mode` flag | REQ-PEM-016 | Both |
| 24 | Invalid `--mode` value produces user-friendly error | REQ-PEM-016 | Both |
| 25 | Conflicting flags raise CLI error | REQ-PEM-016 | Both |
| 26 | Parameterized test: CLI flag × ModeConfig combinations | REQ-PEM-003, 016 | Both |
| 27 | Path traversal in context_files rejected | REQ-PEM-018 | Both |
| 28 | Prompt content wrapped in safe delimiters with closing tags escaped | REQ-PEM-018 | Pipeline |
| 29 | Arbitrary validator names from seed rejected | REQ-PEM-018 | Pipeline |
| 30 | ModeConfig correctly derived from ExecutionMode | REQ-PEM-003 | Both |
| 31 | Mode persists across workflow resume | REQ-PEM-001 | Both |
| 32 | Forced `--mode pipeline` with minimal seed proceeds with warnings | REQ-PEM-002 | Pipeline |
| 33 | Resume with modified seed checksum raises error | REQ-PEM-001 | Both |
| 34 | Property setter after execution raises RuntimeError | REQ-PEM-017 | Both |
| 35 | System prompt includes delimiter instruction | REQ-PEM-018 | Pipeline |
| 36 | Generation manifest includes force_regenerate field | REQ-PEM-012 | Pipeline |
| 37 | Strategy constructors receive project_root and output_dir | REQ-PEM-004 | Both |
| 38 | Generation failure exits with code 1, validation failure with code 2 | REQ-PEM-014 | Both |
| 39 | Unknown metadata keys preserved through FeatureSpec round-trip | REQ-PEM-009 | Both |
| 40 | Delimiter escape prevents user content from breaking isolation | REQ-PEM-018 | Pipeline |
| 41 | SeedContext.execution_mode reconciled to workflow.mode on deserialization | REQ-PEM-005 | Both |
| 42 | `--strict-validation` processes all features before determining exit code | REQ-PEM-014 | Pipeline |
| 43 | ContextResolutionError raised on I/O/parsing failure in strategy methods | REQ-PEM-004 | Both |
| 44 | Standalone mode catches ContextResolutionError and continues with defaults | REQ-PEM-004 | Standalone |
| 45 | Pipeline mode handles ContextResolutionError per method criticality | REQ-PEM-004 | Pipeline |
| 46 | Enrichment key shadowing FeatureSpec primary field is dropped with warning | REQ-PEM-009 | Both |
| 47 | `--force-regenerate` with matching checksum logs match before bypass | REQ-PEM-013 | Pipeline |
| 48 | Property accessors return empty defaults before SeedContext initialization | REQ-PEM-017 | Both |
| 49 | ModeConfig fields match behavior table rows one-to-one | REQ-PEM-003 | Both |
| 50 | Plan context extraction finds feature-name heading match | REQ-PEM-007 | Pipeline |
| 51 | Plan context extraction falls back to first 2000 chars when no heading match | REQ-PEM-007 | Pipeline |
| 52 | Spec completeness check skipped when _enrichment absent | REQ-PEM-008 | Both |
| 53 | Pipeline mode resolve_task_context failure marks feature as failed and continues | REQ-PEM-004 | Pipeline |
| 54 | Generation manifest validator_results includes outcome and findings per validator | REQ-PEM-012 | Pipeline |
| 55 | `.prime_contractor_state.json` written with 0o600 permissions | REQ-PEM-018 | Both |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [`PRIME_CONTRACTOR_REQUIREMENTS.md`](PRIME_CONTRACTOR_REQUIREMENTS.md) | Functional requirements this enables |
| [`PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md`](PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md) | Prompt improvements activated by pipeline mode |
| [`ARTISAN_REQUIREMENTS.md`](../artisan/ARTISAN_REQUIREMENTS.md) | Artisan route (parity target for context quality) |
| [`PIPELINE_REQUIREMENTS_INDEX.md`](../../../Processes/cap-dev-pipe-prod/PIPELINE_REQUIREMENTS_INDEX.md) | Master index for all pipeline requirements |
| [`PLAN_INGESTION_REQUIREMENTS.md`](../PLAN_INGESTION_REQUIREMENTS.md) | Upstream seed construction |

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **ambiguity**: 4 suggestions applied (R8-S4, R1-S3, R1-S10, R2-S3)
- **completeness**: 8 suggestions applied (R8-S5, R1-S1, R1-S4, R2-S2, R2-S4, R2-S7, R4-S10, R5-S9)
- **consistency**: 10 suggestions applied (R8-S1, R8-S6, R1-S5, R2-S1, R3-S7, R3-S8, R3-S9, R4-S7, R4-S8, R5-S8)
- **feasibility**: 7 suggestions applied (R1-S6, R3-S4, R3-S5, R3-S6, R4-S4, R4-S5, R4-S6)
- **testability**: 4 suggestions applied (R7-S4, R1-S2, R1-S9, R2-S8)
- **traceability**: 9 suggestions applied (R8-S9, R4-S1, R4-S2, R5-S4, R6-S2, R6-S3, R6-S4, R6-S5, R6-S6)
- **unknown**: 13 suggestions applied (R2-S5, R3-F1, R3-F2, R2-F1, R3-F4, R3-F3, R4-F3, R4-F4, R5-S7, R5-F2, R5-F3, R6-F2, R6-F3)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Define error handling when explicit --mode pipeline is set but required pipeline signals are absent | claude-4 (claude-opus-4-5) | Critical gap - users forcing pipeline mode on inadequate seeds need defined behavior (fail fast, warn, or degrade) to prevent silent failures or confusion | 2026-02-20 19:57:21 UTC |
| R1-S2 | Specify concrete thresholds for byte-identical output claim in REQ-PEM-006 | claude-4 (claude-opus-4-5) | LLM outputs are non-deterministic, making byte-identical claims unverifiable without clarifying scope (structural vs content) | 2026-02-20 19:57:21 UTC |
| R1-S3 | Clarify relationship between ModeConfig and ContextResolutionStrategy | claude-4 (claude-opus-4-5) | Both govern mode-specific behavior but their interaction is undefined, creating implementation ambiguity | 2026-02-20 19:57:21 UTC |
| R1-S4 | Add requirement for mode persistence across workflow resume/retry scenarios | claude-4 (claude-opus-4-5) | Mode consistency during resume is essential for deterministic behavior; current spec doesn't address state serialization | 2026-02-20 19:57:21 UTC |
| R1-S5 | Reconcile source_checksum being Optional in REQ-PEM-005 but required validation in REQ-PEM-007 | claude-4 (claude-opus-4-5) | Direct inconsistency between schema definition and validation requirements needs resolution | 2026-02-20 19:57:21 UTC |
| R1-S6 | Specify behavior when context_files referenced in SeedContext are missing or unreadable | claude-4 (claude-opus-4-5) | File access errors are common; undefined handling leads to unpredictable failures | 2026-02-20 19:57:21 UTC |
| R1-S9 | Add negative test cases to verification matrix for invalid mode transitions | claude-4 (claude-opus-4-5) | Negative testing for invalid inputs and edge cases is essential for robust validation | 2026-02-20 19:57:21 UTC |
| R1-S10 | Clarify semantics of --no-validate flag interaction with --strict-validation | claude-4 (claude-opus-4-5) | Conflicting flags without defined precedence will cause implementation inconsistency and user confusion | 2026-02-20 19:57:21 UTC |
| R2-S1 | Reconcile conflicting requirements of SeedContext immutability and backward-compatible property setters | gemini-2.5 (gemini-2.5-pro) | Critical logical contradiction - an object cannot be both immutable (REQ-PEM-005) and support setters (REQ-PEM-017); must pick one approach | 2026-02-20 19:57:21 UTC |
| R2-S2 | Clarify how workflow and SeedContext are initialized when no seed file is provided via add_feature() | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-010 implies seedless execution but initialization path is undefined, creating a significant implementation gap | 2026-02-20 19:57:21 UTC |
| R2-S3 | Define expected structure/format for architectural_context described as formatted not raw JSON | gemini-2.5 (gemini-2.5-pro) | Formatted is ambiguous; implementation and testing require a clear transformation contract | 2026-02-20 19:57:21 UTC |
| R2-S4 | Distinguish between critical context fields that cause failure and optional fields that trigger warnings in PIPELINE mode | gemini-2.5 (gemini-2.5-pro) | Not all missing context has equal impact; failing fast on critical data prevents wasted execution | 2026-02-20 19:57:21 UTC |
| R2-S5 | Clarify staleness detection logic regarding workflow_id comparison in REQ-PEM-013 | gemini-2.5 (gemini-2.5-pro) | workflow_id is run-specific not seed-based; the comparison algorithm is confusing and likely incorrect as written | 2026-02-20 19:57:21 UTC |
| R2-S7 | Specify error behavior for runner script when invalid value passed to --mode flag | gemini-2.5 (gemini-2.5-pro) | Input validation and user-friendly error messages are essential for robust CLI design | 2026-02-20 19:57:21 UTC |
| R2-S8 | Explicitly state configuration precedence: CLI flags override ModeConfig settings | gemini-2.5 (gemini-2.5-pro) | Override hierarchy is mentioned but not formalized; explicit precedence rules are needed for predictable behavior and testing | 2026-02-20 19:57:21 UTC |
| R3-F1 | Define find_missing_parameters() function referenced in REQ-PEM-007 |  | The spec-to-draft validation depends on this undefined function; implementation cannot proceed without its specification. | 2026-02-20 20:00:05 UTC |
| R3-F2 | Specify which ModeConfig fields are CLI-overridable and the override syntax |  | Requirements state individual behaviors can be overridden but don't define which fields or how, blocking implementation. | 2026-02-20 20:00:05 UTC |
| R2-F1 | Define structure of Dict[str, Any] for context_files items in REQ-PEM-005 |  | Leaving structure as Any creates implementation ambiguity; developers need expected keys and types for context file loading. | 2026-02-20 20:00:05 UTC |
| R3-S4 | Specify mechanism for property setter compatibility when SeedContext is immutable | claude-4 (claude-opus-4-5) | REQ-PEM-005 declares immutability while REQ-PEM-017 requires setters to work - this is a direct contradiction that will cause implementation failure | 2026-02-20 20:03:28 UTC |
| R3-S5 | Define format and source of source_checksum computation for staleness detection | claude-4 (claude-opus-4-5) | Without specifying hash algorithm, inputs, and responsibility, implementations could produce incompatible checksums breaking staleness detection | 2026-02-20 20:03:28 UTC |
| R3-S6 | Specify behavior when --mode pipeline is explicitly requested but required signals are absent | claude-4 (claude-opus-4-5) | The interaction between explicit mode override and missing context signals is undefined, creating ambiguity that will lead to inconsistent implementations | 2026-02-20 20:03:28 UTC |
| R3-S7 | Reconcile validator naming between REQ-PEM-007 and REQ-PEM-012 | claude-4 (claude-opus-4-5) | Different names for equivalent validators creates confusion about whether they are the same, requiring standardization | 2026-02-20 20:03:28 UTC |
| R3-S8 | Add explicit test coverage for REQ-PEM-003 ModeConfig derivation logic | claude-4 (claude-opus-4-5) | REQ-PEM-003 has acceptance criteria about ModeConfig derivation but no dedicated test in the test strategy, creating a coverage gap | 2026-02-20 20:03:28 UTC |
| R3-S9 | Standardize context_files field schema between REQ-PEM-005 definition and REQ-PEM-007 usage | claude-4 (claude-opus-4-5) | List[Dict[str, Any]] without schema definition leaves usage semantics ambiguous and creates implementation inconsistency | 2026-02-20 20:03:28 UTC |
| R4-S1 | Version-lock document dependencies (REQ-PC and REQ-PPE) | gemini-2.5 (gemini-2.5-pro) | Without version pinning, the traceability matrix becomes ambiguous as source documents evolve, undermining the specification's reliability | 2026-02-20 20:03:28 UTC |
| R4-S2 | Persist effective configuration (including CLI overrides) in generation-manifest.json | gemini-2.5 (gemini-2.5-pro) | Recording only execution_mode without CLI overrides makes runs non-reproducible, defeating the manifest's provenance purpose | 2026-02-20 20:03:28 UTC |
| R4-S4 | Resolve contradictory requirements for SeedContext immutability vs property setters | gemini-2.5 (gemini-2.5-pro) | Duplicate of R3-S4 - this is a critical feasibility issue that must be resolved for implementation | 2026-02-20 20:03:28 UTC |
| R4-S5 | Relax byte-identical constraint in REQ-PEM-006 to semantically equivalent | gemini-2.5 (gemini-2.5-pro) | Byte-identical is overly strict and brittle; minor formatting changes from refactoring would fail validation despite functional equivalence | 2026-02-20 20:03:28 UTC |
| R4-S6 | Specify mechanism for workflow-level configuration in seedless add_feature mode | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-010 allows adding features without seed but doesn't explain how essential workflow parameters are configured, making implementation ambiguous | 2026-02-20 20:03:28 UTC |
| R4-S7 | Define explicit precedence of configuration sources (ModeConfig defaults vs CLI flags) | gemini-2.5 (gemini-2.5-pro) | Without defined precedence, conflicting inputs like --mode pipeline with --no-validate produce unpredictable behavior | 2026-02-20 20:03:28 UTC |
| R4-S8 | Re-evaluate staleness detection logic to focus on source_checksum rather than workflow_id | gemini-2.5 (gemini-2.5-pro) | Comparing workflow_id defeats content-addressable caching; identical inputs should produce reusable outputs regardless of run ID | 2026-02-20 20:03:28 UTC |
| R4-S10 | Specify behavior for corrupt/unparsable generation-manifest.json file | gemini-2.5 (gemini-2.5-pro) | Missing edge case handling will lead to unhandled exceptions in production; graceful degradation should be specified | 2026-02-20 20:03:28 UTC |
| R3-F1 | Define missing find_missing_parameters() function from prompt_utils.py |  | REQ-PEM-007 and REQ-PEM-008 reference this utility function but it's undefined. Implementation cannot proceed without knowing the signature and behavior. High severity with 1 endorsement. | 2026-02-20 20:06:22 UTC |
| R3-F2 | Specify which ModeConfig fields are overridable via CLI flags |  | Requirements state CLI flags can override behaviors but don't map flags to fields. This is needed for Phase 5 implementation where --validate overrides run_validators. | 2026-02-20 20:06:22 UTC |
| R3-F4 | Reconcile requirements_text field path between REQ-PEM-007 and REQ-PEM-009 |  | One requirement specifies feature.metadata['requirements_text'], another lists it as top-level enrichment. Implementation needs canonical path defined. | 2026-02-20 20:06:22 UTC |
| R2-F1 | Define structure of context_files Dict[str, Any] entries |  | SeedContext.context_files uses Dict[str, Any] but doesn't specify expected keys (path, name, type). Implementation needs defined schema for context file loading. | 2026-02-20 20:06:22 UTC |
| R3-F1 | Add schema_version migration strategy for generation manifest |  | High severity completeness issue. Manifest includes schema_version 1.0.0 but no handling for version mismatches or migration path. This will cause integration failures when schema evolves. | 2026-02-20 20:06:22 UTC |
| R3-F2 | Add maximum length specifications for pipeline context sections |  | Medium clarity issue. Unbounded context sections could exceed LLM context windows. Truncation strategy is needed to prevent generation failures. | 2026-02-20 20:06:22 UTC |
| R3-F3 | Add fixture generation strategy for deterministic checksum testing |  | Tests #15-16 require known checksums but don't specify how to create reproducible test fixtures. This is needed for reliable staleness detection testing. | 2026-02-20 20:06:22 UTC |
| R4-F3 | Implementation plan omits REQ-PEM-008 modifications to lead_contractor_workflow.py |  | Critical gap - duplicate of R2-S10. Plan explicitly excludes lead_contractor_workflow.py but REQ-PEM-008 requires spec-to-draft validation logic there. Must add implementation step. | 2026-02-20 20:06:22 UTC |
| R4-F4 | Add explicit requirement for secure handling of external inputs |  | Critical security gap. Requirements lack any security provisions. Path traversal and prompt injection vulnerabilities need to be explicitly addressed in requirements. | 2026-02-20 20:06:22 UTC |
| R5-S4 | Add traceability from output artifacts to downstream consumers | claude-4 (claude-opus-4-5) | Valid concern - the generation-manifest.json and other outputs serve downstream stages but consumers are not identified. This creates risk of breaking unknown dependencies. Documenting known consumers enables impact analysis for format changes. | 2026-02-20 20:22:22 UTC |
| R5-S7 | Add version traceability for dependent documents referenced in the Traceability Matrix | claude-4 (claude-opus-4-5) | Valid concern - the document references PRIME_CONTRACTOR_REQUIREMENTS.md and other documents without version pinning. If those change, the traceability claims become unreliable. Version locking is a reasonable documentation practice. | 2026-02-20 20:22:22 UTC |
| R5-S8 | Clarify relationship between REQ-PEM-013 cache reuse logic and REQ-PEM-003 staleness detection summary | claude-4 (claude-opus-4-5) | Valid consistency issue - REQ-PEM-003 mentions 'Staleness detection: Enforce per REQ-PC-011' but REQ-PEM-013 adds cache reuse semantics (matching checksum = reuse) not mentioned in the summary. The summary should accurately reflect the detailed requirement. | 2026-02-20 20:22:22 UTC |
| R5-S9 | Specify behavior when --mode pipeline is explicitly set but seed lacks pipeline signals | claude-4 (claude-opus-4-5) | This is a valid completeness gap. The requirements describe auto-detection and mode behaviors but don't specify the forced-mode-with-insufficient-context edge case. Explicit specification prevents ambiguous implementation. | 2026-02-20 20:22:22 UTC |
| R6-S2 | Add versioning to the Depends on documents | gemini-2.5 (gemini-2.5-pro) | This is a duplicate of R5-S7 which was accepted. Valid concern about dependency versioning for requirements stability. | 2026-02-20 20:22:22 UTC |
| R6-S3 | Formalize generation-manifest.json as a versioned data contract with traced consumers | gemini-2.5 (gemini-2.5-pro) | Related to R5-S4. The manifest already has schema_version field, but documenting consumers and establishing contract testing is valuable for preventing breaking changes in a pipeline integration point. | 2026-02-20 20:22:22 UTC |
| R6-S4 | Trace validator logic to formal definitions instead of opaque identifiers like AR-143 | gemini-2.5 (gemini-2.5-pro) | Valid concern - referencing 'AR-143 equivalent' provides no traceability to actual validation logic. Either hyperlink to definitions or replace with descriptive specifications to enable implementation verification. | 2026-02-20 20:22:22 UTC |
| R6-S5 | Mandate golden file regression test for standalone mode behavioral parity | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-006 and REQ-PEM-015 make strong claims about identical behavior. A golden file test is the appropriate verification mechanism for byte-identical output claims. Without it, parity is unverifiable. | 2026-02-20 20:22:22 UTC |
| R6-S6 | Create a configuration precedence table for defaults, auto-detection, ModeConfig, and CLI overrides | gemini-2.5 (gemini-2.5-pro) | Valid completeness issue - multiple configuration sources exist but their interaction/override order is not formally specified. This is essential for correct implementation and debugging. | 2026-02-20 20:22:22 UTC |
| R3-F1 | Define the find_missing_parameters() function referenced in REQ-PEM-007 |  | This function is referenced but never defined, making implementation impossible. With 2 endorsements, this is a validated gap that blocks implementation. | 2026-02-20 20:25:40 UTC |
| R3-F4 | Reconcile requirements_text field path inconsistency between REQ-PEM-007 and REQ-PEM-009 |  | Inconsistent field paths (metadata['requirements_text'] vs top-level) will cause implementation confusion and bugs. This needs a canonical definition. | 2026-02-20 20:25:40 UTC |
| R2-F1 | Define the structure of context_files Dict[str, Any] entries |  | The undefined structure of context_files entries creates implementation ambiguity. Developers need to know expected keys and value types for proper implementation. | 2026-02-20 20:25:40 UTC |
| R3-F1 | Add schema_version migration strategy for REQ-PEM-012 manifest |  | This is a different issue from the earlier R3-F1 (find_missing_parameters). Schema versioning without migration strategy will cause integration failures when schema evolves. Critical for long-term maintainability. | 2026-02-20 20:25:40 UTC |
| R3-F3 | Add checksum computation details for staleness detection test fixtures |  | Tests #15-16 are unimplementable without knowing how to create fixtures with known checksums. This is critical for reproducible testing. | 2026-02-20 20:25:40 UTC |
| R5-F2 | Specify field optionality for resolve_task_context structured sections |  | Without clear presence/absence rules for each section, implementations will handle empty data inconsistently. | 2026-02-20 20:25:40 UTC |
| R5-F3 | Replace unverifiable 'byte-identical' criterion with structural equivalence |  | The byte-identical criterion cannot be tested due to dict ordering variations. Structural equivalence is the correct verification approach. | 2026-02-20 20:25:40 UTC |
| R6-F2 | Specify behavior for empty but present context fields in REQ-PEM-007 |  | Ambiguity about empty fields (include empty section vs omit) affects prompt quality. Clear requirement prevents inconsistent implementations. | 2026-02-20 20:25:40 UTC |
| R6-F3 | Add requirements for handling I/O errors during manifest writing |  | The manifest is critical for pipeline integration. Without defined error handling, implementations may fail silently or catastrophically. Behavior must be specified. | 2026-02-20 20:25:40 UTC |
| R7-S4 | Specify observable verification criteria for staleness reuse test #16 | claude-4 (claude-opus-4-5) | The test strategy lacks actionable verification criteria. Specifying zero LLM calls, no file modifications, and specific log message makes the test implementable and deterministic. | 2026-02-20 21:17:25 UTC |
| R8-S1 | Validate seed checksum against state file on resume to detect seed modifications | gemini-2.5 (gemini-2.5-pro) | This addresses a real integrity issue where resuming with a modified seed could produce inconsistent state. The suggestion complements existing staleness detection by binding state to a specific seed version. | 2026-02-20 21:17:25 UTC |
| R8-S4 | Enforce SeedContext immutability with runtime error after execution begins instead of undefined behavior | gemini-2.5 (gemini-2.5-pro) | Undefined behavior is a bug waiting to happen. A clear RuntimeError provides a fail-fast contract that prevents subtle state corruption. This strengthens the lifecycle constraint already specified. | 2026-02-20 21:17:25 UTC |
| R8-S5 | Add system prompt instruction telling LLM to treat delimited content as non-instructional data | gemini-2.5 (gemini-2.5-pro) | The mitigation is incomplete without the model instruction. Simply wrapping in tags is insufficient - the model must be told to interpret the tags correctly. This is critical for effective prompt injection defense. | 2026-02-20 21:17:25 UTC |
| R8-S6 | Remove ingestion_metrics.generator as pipeline mode detection signal due to brittle coupling | gemini-2.5 (gemini-2.5-pro) | Coupling to a specific upstream workflow name is fragile. The structural signals (onboarding, service_metadata, architectural_context) are already sufficient and more robust indicators of pipeline mode. | 2026-02-20 21:17:25 UTC |
| R8-S9 | Record force-regenerate flag usage in generation-manifest.json for audit trail | gemini-2.5 (gemini-2.5-pro) | This is important provenance information explaining why cache was bypassed. The manifest should reflect this decision for debugging and auditing purposes. | 2026-02-20 21:17:25 UTC |
| R3-F1 | Define find_missing_parameters() function referenced in REQ-PEM-007 |  | This function is referenced but never defined, making implementation impossible. With 2 endorsements, this is a validated gap that blocks implementation. | 2026-02-20 21:24:18 UTC |
| R2-F1 | Define the structure of context_files Dict[str, Any] entries |  | The undefined structure of context_files entries creates implementation ambiguity. Developers need to know expected keys and value types for proper implementation. | 2026-02-20 21:24:18 UTC |
| R3-F1 | Add schema_version migration strategy for REQ-PEM-012 manifest |  | This is a different issue from the earlier R3-F1 (find_missing_parameters). Schema versioning without migration strategy will cause integration failures when schema evolves. Critical for long-term maintainability. | 2026-02-20 21:24:18 UTC |
| R3-F3 | Add checksum computation details for staleness detection test fixtures |  | Tests #15-16 are unimplementable without knowing how to create fixtures with known checksums. This is critical for reproducible testing. | 2026-02-20 21:24:18 UTC |
| R4-F3 | Implementation plan omits REQ-PEM-008 modifications to lead_contractor_workflow.py |  | Critical gap - duplicate of R2-S10. Plan explicitly excludes lead_contractor_workflow.py but REQ-PEM-008 requires spec-to-draft validation logic there. Must add implementation step. | 2026-02-20 21:24:18 UTC |
| R4-F4 | Add explicit requirement for secure handling of external inputs |  | Critical security gap. Requirements lack any security provisions. Path traversal and prompt injection vulnerabilities need to be explicitly addressed in requirements. | 2026-02-20 21:24:18 UTC |
| R5-F1 | Define ValidationConfig type in REQ-PEM-004 |  | The protocol references this type but it's never defined. Implementation cannot satisfy the protocol without knowing the structure. | 2026-02-20 21:24:18 UTC |
| R5-F2 | Specify field optionality for resolve_task_context structured sections |  | Without clear presence/absence rules for each section, implementations will handle empty data inconsistently. | 2026-02-20 21:24:18 UTC |
| R5-F3 | Replace unverifiable 'byte-identical' criterion with structural equivalence |  | The byte-identical criterion cannot be tested due to dict ordering variations. Structural equivalence is the correct verification approach. | 2026-02-20 21:24:18 UTC |
| R5-F4 | Add manifest schema version migration requirements |  | Duplicate of second R3-F1 (schema migration). Valid concern for long-term maintainability when schema evolves. | 2026-02-20 21:24:18 UTC |
| R6-F2 | Specify behavior for empty but present context fields in REQ-PEM-007 |  | Ambiguity about empty fields (include empty section vs omit) affects prompt quality. Clear requirement prevents inconsistent implementations. | 2026-02-20 21:24:18 UTC |
| R6-F3 | Add requirements for handling I/O errors during manifest writing |  | The manifest is critical for pipeline integration. Without defined error handling, implementations may fail silently or catastrophically. Behavior must be specified. | 2026-02-20 21:24:18 UTC |
| R7-F1 | Specify per-feature model field data flow in manifest schema |  | Requirements show the field but don't specify data flow from generator. Creates implementation ambiguity. | 2026-02-20 21:24:18 UTC |
| R7-F2 | Add architectural context transformation specification to requirements |  | Requirements state 'formatted not raw JSON' but lack transformation details. Requirements should be self-contained. | 2026-02-20 21:24:18 UTC |
| R7-F3 | Change 'byte-identical' to 'structurally equivalent' in REQ-PEM-006 |  | Dict ordering varies in Python. The requirement text must match the testable criterion. | 2026-02-20 21:24:18 UTC |
| R7-F4 | Specify path sanitization mechanism in REQ-PEM-018 |  | References 'existing utility' that may not exist. Sanitization rules must be explicit for security. | 2026-02-20 21:24:18 UTC |
| R8-F1 | Clarify validator_results schema in generation-manifest.json |  | The manifest example conflicts with ValidationResult type. Downstream consumers need to know the actual schema. | 2026-02-20 21:24:18 UTC |
| R8-F3 | Define when 'execution begins' precisely for property setter RuntimeError |  | The requirement must be testable. Specifying the exact event (_generate_code() invocation) enables deterministic test cases. | 2026-02-20 21:24:18 UTC |
| R1-F2 | Specify that ContextResolutionStrategy implementations may accept configuration via __init__ and the workflow must pass project_root and output_dir. |  | This is a genuine gap. The PipelineContextStrategy needs project_root for path traversal validation (REQ-PEM-018) and the staleness detection logic needs access to the output directory for manifest reading (REQ-PEM-013). The protocol as defined is purely method-based with no initialization contract. Since Python protocols allow __init__, this is a clarification that enables testable, dependency-injected strategy implementations without global state. | 2026-02-21 00:57:13 UTC |
| R1-F3 | Define distinct exit codes for validation failures (exit 2) vs generation failures (exit 1) vs success (exit 0). |  | Pipeline orchestrators rely on exit codes for automated remediation decisions. The current requirements specify non-zero exit for --strict-validation failures but don't distinguish from other failure modes. This is a concrete, low-cost addition that significantly improves pipeline integration. The three-code scheme (0/1/2) is standard Unix convention and enables orchestrators to distinguish 'retry-worthy' from 'needs-human-attention' failures. | 2026-02-21 00:57:13 UTC |
| R1-F4 | Require FeatureSpec.metadata to preserve all keys from the enriched seed, not only the nine explicitly listed fields. |  | REQ-PEM-009 lists nine specific enrichment fields but the queue boundary behavior for unknown keys is genuinely ambiguous. Since the pipeline is designed for iterative development (REQ-PEM-002 explicitly supports stages still being built), stripping unknown keys would break forward compatibility. Preserving all keys through to_dict()/from_dict() is the safe default and aligns with the 'no data loss at queue boundary' acceptance criterion already stated. | 2026-02-21 00:57:13 UTC |
| R1-F5 | Require escaping of closing delimiter tags in user-controlled content before wrapping with safe delimiters for prompt injection mitigation. |  | This is a genuine security gap in the existing prompt injection mitigation. REQ-PEM-018 mandates XML-style delimiters but doesn't address the case where user content contains the closing tag, which would break delimiter isolation. This is a well-known XML/HTML injection pattern. The fix is straightforward (escape closing tags) and is necessary for the defense-in-depth claim to be credible. | 2026-02-21 00:57:13 UTC |
| R1-F3 | Specify whether --strict-validation exits after all features complete or on first failure, as this affects pipeline orchestrator design. |  | This is the requirements-side formulation of R1-S6 (which was accepted). The ambiguity is real and affects downstream pipeline integration. Specifying complete-then-fail semantics is the correct resolution — it provides comprehensive diagnostics and aligns with the manifest's role as a comprehensive results record. This should be folded into the same resolution as R1-S6. | 2026-02-22 00:11:52 UTC |
| R1-F4 | Specify which source (workflow.mode vs SeedContext.execution_mode) is authoritative at runtime and define deserialization reconciliation behavior. |  | This is the requirements-side formulation of R1-S7 (which was accepted). The dual-authority risk is real and should be addressed by designating workflow.mode as runtime authority and SeedContext.execution_mode as serialization-only. These two suggestions should be resolved together. | 2026-02-22 00:11:52 UTC |
| R1-F1 | Add error semantics to ContextResolutionStrategy protocol distinguishing resolution failures from empty-data degradation |  | This is substantively the same concern as R1-S1 and should be accepted for the same reasons. The prior rejection (R1-F2, 2026-02-22) dismissed this as a 'duplicate of R1-S2' but R1-S2 was about state file recovery, not strategy error contracts. The concern remains valid and unaddressed. Merging with R1-S1 for implementation. | 2026-02-22 15:35:03 UTC |
| R1-F2 | Add conflict resolution rule when enrichment metadata keys shadow FeatureSpec built-in fields like name/description |  | REQ-PEM-009 mandates preserving all keys but doesn't address the realistic scenario where enrichment includes keys matching FeatureSpec primary fields. This was raised in R1-F4 (2026-02-22) and accepted conceptually, but the resolution rule was never formally specified in the requirements text. With 1 endorsement, this is a validated gap that needs explicit conflict resolution semantics. Primary field wins, conflicting metadata key dropped with warning is the correct resolution. | 2026-02-22 15:35:03 UTC |
| R1-F5 | Log staleness comparison result even when --force-regenerate is active, before bypassing the cache |  | This is a low-cost observability improvement that aids debugging. Operators investigating cache behavior need to know whether the cache would have been valid. The requirement already mandates staleness comparison logging — simply ensuring this logging still occurs when force-regenerate is active (before the bypass) is consistent and useful. The log message 'Force regenerate active — bypassing cache despite {match/mismatch}' provides actionable information. | 2026-02-22 15:35:03 UTC |
| R1-F2 | Add explicit ModeConfig dataclass field definition to REQ-PEM-003 to match the treatment given to SeedContext, ValidationConfig, and ContextFileEntry |  | This is a genuine asymmetry in the requirements. SeedContext (REQ-PEM-005), ValidationConfig (REQ-PEM-004), and ContextFileEntry (REQ-PEM-005) all have concrete dataclass definitions with typed fields. ModeConfig is described only via a behavior table, forcing implementers to infer the field set. Since ModeConfig is a frozen dataclass created via for_mode() and modified via dataclasses.replace() (per REQ-PEM-003 acceptance criteria), its fields must be well-defined for both methods to work correctly. Adding the definition eliminates implementation ambiguity. | 2026-02-23 03:11:56 UTC |
| R1-F3 | Specify the plan document excerpt extraction algorithm for the plan_context section in REQ-PEM-007 |  | The requirement says 'feature-specific excerpt from plan document' without defining extraction semantics. Plan documents can be thousands of lines, and implementations will diverge significantly — some including the entire document (wasting LLM tokens), others using brittle heuristics. Specifying a concrete algorithm (feature name match in headings with fallback to first N characters) makes the requirement implementable and testable. This directly affects generation quality, which is the core purpose of pipeline mode. | 2026-02-23 03:11:56 UTC |
| R1-F4 | Specify the data flow for resolved_parameters in find_missing_parameters() — where the dict comes from and skip conditions when enrichment is absent |  | REQ-PEM-008 defines find_missing_parameters() with a resolved_parameters parameter but no requirement specifies how this dict is populated. The function is a text-only utility, but its callers need to know the data source. Specifying that resolved_parameters is derived from feature.metadata['_enrichment'] (the canonical enrichment location per REQ-PEM-009) and that the check is skipped when enrichment is absent completes the data flow chain and makes the feature implementable. | 2026-02-23 03:11:56 UTC |
| R1-F6 | Specify property accessor behavior when SeedContext has not yet been initialized (before seed loading) |  | REQ-PEM-017 specifies property accessors that delegate to SeedContext but doesn't address the temporal gap between workflow construction and seed loading. Code that checks seed properties during construction (a reasonable pattern for conditional setup logic) would encounter an AttributeError. Specifying that accessors return empty defaults before initialization is consistent with the standalone mode's graceful degradation principle and prevents a class of initialization-order bugs. | 2026-02-23 03:11:56 UTC |
| R1-F1 | Specify that `resolve_task_context` failure in pipeline mode marks the feature as `failed` without attempting generation, rather than generating with undefined 'degraded context'. |  | This is the requirements-side formulation of R1-S1 and addresses the same genuine gap. The current text says 'continue with degraded context' but generating code from incomplete context risks producing subtly wrong output that passes compilation but violates domain constraints. Marking the feature as failed and moving on is the safer and more predictable behavior. This should be merged with R1-S1 during application. | 2026-02-23 17:20:43 UTC |
| R1-F3 | Require restrictive file permissions (0o600) for `.prime_contractor_state.json` to match the manifest's permission requirements. |  | This is a genuine security gap. The state file contains the execution mode, seed checksum, and feature queue status. In a pipeline deployment, tampering with the state file could skip features, change the execution mode, or corrupt the resume state. If REQ-PEM-012 mandates 0o600 for the manifest due to cost data sensitivity, the state file warrants the same protection for execution integrity. This is a low-cost, high-value addition to REQ-PEM-018. | 2026-02-23 17:20:43 UTC |
| R1-F4 | Expand the manifest's `validator_results` schema to include the `findings` list from `ValidationResult`, not just the summary outcome string. |  | This is a real observability gap. REQ-PEM-004 defines `ValidationResult` with `findings: List[str]` but REQ-PEM-012's manifest example only shows `"import_dependency": "pass"`. The manifest is the only persistent record of validation results and is consumed by Stage 7 validators and developers. Omitting findings forces downstream consumers to re-run validation to get diagnostic details, defeating the purpose of recording results. The expanded schema is a natural consequence of the existing ValidationResult type. | 2026-02-23 17:20:43 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S7 | Add traceability for REQ-PEM-010 to REQ-PEM-015 in the Traceability Matrix | claude-4 (claude-opus-4-5) | Low impact documentation improvement; these requirements serve different purposes (feature construction vs backward compat) and don't require explicit traceability linkage | 2026-02-20 19:57:21 UTC |
| R1-S8 | Define thread-safety and concurrency model for SeedContext and ContextResolutionStrategy | claude-4 (claude-opus-4-5) | Document states SeedContext is immutable after initialization, and no parallel feature processing is described in requirements; adding concurrency requirements would expand scope unnecessarily | 2026-02-20 19:57:21 UTC |
| R2-S6 | Add prompt_tokens and completion_tokens to generation-manifest.json schema | gemini-2.5 (gemini-2.5-pro) | Nice-to-have observability enhancement but not critical for core requirements; can be added in future iteration without impacting current design | 2026-02-20 19:57:21 UTC |
| R2-S9 | Specify that auto-detection log message should list actual keys found that triggered PIPELINE mode | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-002 already specifies logging signals in the message; this is an implementation detail refinement rather than a requirements gap | 2026-02-20 19:57:21 UTC |
| R3-F5 | Specify mock/fixture strategy for deterministic testing of gen_context |  | This duplicates R3-S6 which already addresses the same testing concern with structural equivalence criteria. | 2026-02-20 20:00:05 UTC |
| R2-F2 | Clarify sequence between default mode and auto-detection |  | Low severity clarity issue and existing test cases already cover the procedural logic; text sharpening is a documentation improvement, not a blocking issue. | 2026-02-20 20:00:05 UTC |
| R3-S1 | Add bidirectional trace from REQ-PEM back to Problem Statement | claude-4 (claude-opus-4-5) | The problem statement is introductory context, not a normative source requiring formal traceability; requirements trace to REQ-PC and IMP-P which are the authoritative sources | 2026-02-20 20:03:28 UTC |
| R3-S2 | Annotate execution mode model diagram with requirement IDs | claude-4 (claude-opus-4-5) | The diagram is illustrative, not normative; requirements are clearly stated in text form and adding annotations would clutter the visual aid | 2026-02-20 20:03:28 UTC |
| R3-S3 | Add individual identifiers (BEH-001 through BEH-007) to ModeConfig behavior table rows | claude-4 (claude-opus-4-5) | The behaviors are already tied to the ModeConfig of REQ-PEM-003; additional sub-identifiers add complexity without proportional benefit since tests can reference the behavior names directly | 2026-02-20 20:03:28 UTC |
| R3-S10 | Add version/dependency trace for change impact analysis | claude-4 (claude-opus-4-5) | This is a document management process concern rather than a requirements specification issue; similar suggestion R4-S1 addresses version-locking more directly | 2026-02-20 20:03:28 UTC |
| R4-S3 | Add data lineage checksums for injected context blocks to manifest | gemini-2.5 (gemini-2.5-pro) | This adds significant implementation complexity; the source_checksum already covers seed-level provenance, and per-context-block checksums are a nice-to-have rather than essential | 2026-02-20 20:03:28 UTC |
| R4-S9 | Relocate ExecutionMode enum to shared types module | gemini-2.5 (gemini-2.5-pro) | This is implementation guidance rather than requirements specification; the architect/developer can determine appropriate module organization during design | 2026-02-20 20:03:28 UTC |
| R3-F5 | Specify mock/fixture strategy for deterministic testing of gen_context |  | Test #6 verifies context building logic, not LLM outputs. The gen_context dict is deterministically built from inputs; mocking LLM responses is not needed for this specific test. | 2026-02-20 20:06:22 UTC |
| R2-F2 | Clarify sequence between default mode and auto-detection |  | Low severity clarity issue. The current requirements and plan already explain this: explicit CLI flag > auto-detection > STANDALONE default. The existing test cases adequately cover this behavior. | 2026-02-20 20:06:22 UTC |
| R4-F2 | Enhance staleness detection to be code-version aware |  | Scope creep. REQ-PEM-013 defines staleness based on source_checksum. Adding generator_version tracking is a valid enhancement but beyond current requirements and adds complexity. | 2026-02-20 20:06:22 UTC |
| R5-S1 | Add forward traceability from requirements to specific test file paths | claude-4 (claude-opus-4-5) | The Test Strategy table already maps tests to requirements. Specifying concrete test file paths at the requirements stage is premature - test organization is an implementation detail that may change. This creates maintenance burden without proportionate benefit. | 2026-02-20 20:22:22 UTC |
| R5-S2 | Add Mode-Behavior Traceability table linking enum values to governed behaviors | claude-4 (claude-opus-4-5) | REQ-PEM-003 already provides a clear table mapping behaviors to STANDALONE vs PIPELINE modes. The Execution Mode Model diagram reinforces this. Adding another table would be redundant - the relationship is already explicit in the existing requirements structure. | 2026-02-20 20:22:22 UTC |
| R5-S3 | Add Protocol Method Traceability table mapping strategy methods to requirements | claude-4 (claude-opus-4-5) | REQ-PEM-006 and REQ-PEM-007 are explicitly titled as implementations of the strategy and describe what each method does. The structure (one requirement per strategy) already provides this traceability implicitly. | 2026-02-20 20:22:22 UTC |
| R5-S5 | Add source requirement IDs for auto-detection signals in REQ-PEM-002 | claude-4 (claude-opus-4-5) | The Upstream Dependencies section already traces REQ-PEM-007 to REQ-PI requirements for onboarding, architectural context, and service metadata. Adding this at the signal level within REQ-PEM-002 would be duplicative. | 2026-02-20 20:22:22 UTC |
| R5-S6 | Add SeedContext field traceability showing source and consumer requirements | claude-4 (claude-opus-4-5) | This level of field-by-field traceability is more appropriate for detailed design documentation. The requirements already trace at the requirement level through the Traceability Matrix. Adding per-field tracing would make the document unwieldy. | 2026-02-20 20:22:22 UTC |
| R5-S10 | Add CLI Flag Traceability table mapping flags to requirements they override | claude-4 (claude-opus-4-5) | REQ-PEM-016 already describes what each flag does (e.g., '--validate flag forces post-generation validation regardless of mode'). The behavior descriptions implicitly trace to relevant requirements. A separate table adds marginal value. | 2026-02-20 20:22:22 UTC |
| R6-S1 | Add a Requirement-to-Test traceability matrix | gemini-2.5 (gemini-2.5-pro) | The existing Test Strategy table already maps tests to requirements via the 'Validates' column. A reverse matrix would be redundant - the same information can be derived by reading the existing table. | 2026-02-20 20:22:22 UTC |
| R6-S7 | Mandate code annotations to trace implementation back to requirements | gemini-2.5 (gemini-2.5-pro) | Code annotation style is an implementation/coding standards concern, not a requirements document concern. This belongs in development guidelines or contributing documentation, not functional requirements. | 2026-02-20 20:22:22 UTC |
| R6-S8 | Explicitly trace internal dependencies between requirements | gemini-2.5 (gemini-2.5-pro) | The requirements are structured in layers (1-5) which implies dependency order. Adding explicit internal dependency notes would create maintenance burden and risk becoming stale. The layered structure provides sufficient guidance. | 2026-02-20 20:22:22 UTC |
| R6-S9 | Refine auto-detection logic to require multiple signals for pipeline mode | gemini-2.5 (gemini-2.5-pro) | The current OR logic is an intentional design choice for pipeline detection. Changing detection semantics is a design change, not a requirements clarification. If this is a concern, it should be raised as a design decision review, not a requirements fix. | 2026-02-20 20:22:22 UTC |
| R6-S10 | Add section tracing Alternatives Considered with link to Appendix B | gemini-2.5 (gemini-2.5-pro) | Rejected suggestions are a review artifact, not part of the requirements document itself. The requirements document should be authoritative for what IS required, not what was considered and rejected. | 2026-02-20 20:22:22 UTC |
| R3-F2 | Add CLI flag to ModeConfig field mapping for behavior overrides |  | R4-S7 was already accepted which addresses mode override mechanisms. Additionally, the plan already specifies --validate/--no-validate flags in Phase 5 with clear semantics. | 2026-02-20 20:25:40 UTC |
| R3-F5 | Specify mock/fixture strategy for Test #6 determinism |  | Test #6 is about context building (pre-LLM), which is deterministic. The 'byte-identical' claim has been addressed by R5-S10 and R5-F3 which were already accepted, replacing byte-identical with structural equivalence. | 2026-02-20 20:25:40 UTC |
| R2-F2 | Clarify the sequence of mode determination operations |  | The plan already clearly specifies auto-detection in Phase 1 Step 6 and CLI override in Phase 5. The order (explicit flag > auto-detection > default STANDALONE) is implicit but clear from the implementation steps. | 2026-02-20 20:25:40 UTC |
| R3-F2 | Add maximum length specifications for pipeline context sections |  | This is an implementation detail that can be addressed during development. LLM context window management is a runtime concern and the requirement should remain focused on functionality, not optimization parameters. | 2026-02-20 20:25:40 UTC |
| R4-F2 | Add generator_version to staleness detection |  | While useful for comprehensive staleness detection, this significantly expands scope beyond the current requirements. The source_checksum approach handles input staleness; code version tracking is a separate concern that should be addressed in a future iteration. | 2026-02-20 20:25:40 UTC |
| R4-F3 | Add implementation plan step for REQ-PEM-008 |  | R4-S1 was already accepted which addresses adding REQ-PEM-008 to the implementation plan. This is a duplicate. | 2026-02-20 20:25:40 UTC |
| R4-F4 | Add explicit security requirements for input handling |  | R4-S9 was already accepted which addresses security considerations. Adding a separate top-level requirement is redundant. | 2026-02-20 20:25:40 UTC |
| R5-F1 | Define ValidationConfig type in requirements |  | R5-S1 was already accepted which addresses the same issue in the implementation plan. The plan is the appropriate place for type definitions. | 2026-02-20 20:25:40 UTC |
| R5-F4 | Add manifest schema version migration requirements |  | This is a duplicate of the second R3-F1 (schema_version migration) which was already accepted. | 2026-02-20 20:25:40 UTC |
| R5-F5 | Add emit_otel_spans to ModeConfig |  | This is a duplicate of R3-F3 (3 endorsements) which was already accepted. | 2026-02-20 20:25:40 UTC |
| R6-F4 | Define ValidationConfig type in requirements |  | R5-S1 was already accepted which addresses ValidationConfig definition in the implementation plan. The type definition belongs in the plan, not requirements. | 2026-02-20 20:25:40 UTC |
| R7-S1 | Add thread-safety requirements for ContextResolutionStrategy implementations | claude-4 (claude-opus-4-5) | REQ-PC-010 parallel generation support is out of scope for this document which focuses on execution modes. The strategy protocol is designed to be stateless by returning new dicts/objects. Thread-safety concerns should be addressed in implementation, not requirements. | 2026-02-20 21:17:25 UTC |
| R7-S2 | Define behavior for duplicate file paths in context_files | claude-4 (claude-opus-4-5) | This is an implementation edge case that can be handled at the code level. The document already has sufficient complexity. Standard deduplication behavior is reasonable to expect without explicit specification. | 2026-02-20 21:17:25 UTC |
| R7-S3 | Address fcntl.flock Windows compatibility for state file locking | claude-4 (claude-opus-4-5) | The codebase targets Unix-like systems for the pipeline deployment context. Windows local development can use alternative mechanisms. This is an implementation detail that doesn't belong in requirements. | 2026-02-20 21:17:25 UTC |
| R7-S5 | Specify ModeConfig to JSON serialization format for effective_config | claude-4 (claude-opus-4-5) | Using dataclasses.asdict() is standard Python practice and doesn't need explicit specification. The example JSON structure in REQ-PEM-012 already shows the expected format. | 2026-02-20 21:17:25 UTC |
| R7-S6 | Add traceability mapping for REQ-PC-010 parallel generation support | claude-4 (claude-opus-4-5) | This document explicitly does not implement REQ-PC-010 - execution modes are orthogonal to parallelism. Adding a trace would imply this document addresses parallel generation, which it does not. | 2026-02-20 21:17:25 UTC |
| R7-S7 | Rename ValidationResult.severity to outcome or status | claude-4 (claude-opus-4-5) | While the naming could be clearer, this is a minor cosmetic concern. The values 'pass/warn/fail' are self-explanatory. Changing now would require updating multiple accepted suggestions that reference this field. | 2026-02-20 21:17:25 UTC |
| R7-S8 | Add guidance for requirements_text that exceeds context window limits | claude-4 (claude-opus-4-5) | Token limit handling is a general concern for all LLM interactions, not specific to execution modes. This belongs in the prompt externalization requirements (REQ-PPE) or the code generator, not here. | 2026-02-20 21:17:25 UTC |
| R8-S2 | Add feature-level cache invalidation instead of all-or-nothing based on seed checksum | gemini-2.5 (gemini-2.5-pro) | This significantly increases complexity for marginal benefit. The content-addressable checksum approach is already defined. Feature-level caching would require per-feature checksums, dependency tracking, and complex invalidation logic. | 2026-02-20 21:17:25 UTC |
| R8-S3 | Define and enforce dependencies between validators | gemini-2.5 (gemini-2.5-pro) | This adds significant complexity to the validation system. The current design treats validators as independent which is simpler and sufficient. Validator dependency ordering is an implementation optimization, not a requirements concern. | 2026-02-20 21:17:25 UTC |
| R8-S7 | Apply consistent graceful degradation for all optional file paths in standalone mode | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-006 already specifies graceful degradation for context_files. The plan_document_path handling follows the same pattern implicitly. Adding explicit text for every file path type adds verbosity without value. | 2026-02-20 21:17:25 UTC |
| R8-S8 | Add toolchain versions to generation-manifest.json for reproducibility | gemini-2.5 (gemini-2.5-pro) | While useful for debugging, this adds scope beyond execution modes. The manifest already captures essential provenance (checksum, mode, validators). Toolchain versioning is a general infrastructure concern. | 2026-02-20 21:17:25 UTC |
| R8-S10 | Add global_settings field to SeedContext for workflow-level configuration | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-010 already addresses workflow-level configuration via constructor parameters for seedless mode. Adding a global_settings field to SeedContext creates parallel configuration paths and increases complexity. | 2026-02-20 21:17:25 UTC |
| R3-F2 | Add CLI flag to ModeConfig field mapping for behavior overrides |  | R4-S7 was already accepted which addresses mode override mechanisms. Additionally, the plan already specifies --validate/--no-validate flags in Phase 5 with clear semantics. | 2026-02-20 21:24:18 UTC |
| R3-F5 | Specify mock/fixture strategy for Test #6 determinism |  | Test #6 is about context building (pre-LLM), which is deterministic. The 'byte-identical' claim has been addressed by R5-S10 and R5-F3 which were already accepted, replacing byte-identical with structural equivalence. | 2026-02-20 21:24:18 UTC |
| R2-F2 | Clarify the sequence of mode determination operations |  | The plan already clearly specifies auto-detection in Phase 1 Step 6 and CLI override in Phase 5. The order (explicit flag > auto-detection > default STANDALONE) is implicit but clear from the implementation steps. | 2026-02-20 21:24:18 UTC |
| R3-F2 | Add maximum length specifications for pipeline context sections |  | This is an implementation detail that can be addressed during development. LLM context window management is a runtime concern and the requirement should remain focused on functionality, not optimization parameters. | 2026-02-20 21:24:18 UTC |
| R4-F2 | Add generator_version to staleness detection |  | While useful for comprehensive staleness detection, this significantly expands scope beyond the current requirements. The source_checksum approach handles input staleness; code version tracking is a separate concern that should be addressed in a future iteration. | 2026-02-20 21:24:18 UTC |
| R5-F5 | Add emit_otel_spans to ModeConfig |  | This is a duplicate of R3-F3 (3 endorsements) which was already accepted. | 2026-02-20 21:24:18 UTC |
| R6-F4 | Define ValidationConfig type in requirements |  | R5-F1 was already accepted which addresses ValidationConfig definition in the implementation plan. The type definition belongs in the plan, not requirements. | 2026-02-20 21:24:18 UTC |
| R8-F2 | Support multiple models per feature in manifest |  | This is a forward-looking enhancement. The current single-model design matches the typical single-stage generation. Multi-model support can be added when needed. | 2026-02-20 21:24:18 UTC |
| R1-F1 | Clarify that SeedContext immutability applies after first _generate_code() call and that inter-feature context updates must go through resolve_task_context(). |  | This is already addressed in the requirements. REQ-PEM-017 explicitly states: 'For the purpose of this requirement, "execution begins" is defined as the first invocation of the internal _generate_code() method.' REQ-PEM-007's resolve_task_context() already receives the feature as a parameter, providing the per-feature customization mechanism. The concern about inter-feature context is addressed by design — resolve_task_context() is called per feature with the immutable SeedContext. | 2026-02-21 00:57:13 UTC |
| R1-F1 | Add gen_context consumption contract specifying how CodeGenerator renders structured sections into LLM prompts. |  | This is a duplicate of R1-S5 (same reviewer, same concern, different ID format). The CodeGenerator's prompt rendering behavior is outside the scope of this execution modes document. The gen_context dict interface is already defined; generator-side requirements belong in the generator's own specification. | 2026-02-22 00:11:52 UTC |
| R1-F2 | Address the fragile recovery path where manifest is written only after all features but staleness detection reads it, leaving crashes unrecoverable via manifest. |  | This is a duplicate of R1-S2 (same reviewer, same concern). As stated in that rejection: `.prime_contractor_state.json` handles feature-level resume, the manifest handles provenance. These are intentionally separate concerns. A crash mid-run resumes via state file; the manifest is a post-completion artifact for downstream consumers. The requirements are coherent as written. | 2026-02-22 00:11:52 UTC |
| R1-F5 | Strengthen prompt injection mitigation to escape ALL context delimiter patterns or mandate content-hash-based unique delimiters. |  | R1-F5 from the prior round (escaping closing delimiter tags) was already accepted and incorporated into REQ-PEM-018. The requirements already mention content-hash-based unique delimiters as an alternative. The current defense-in-depth approach (escaping + system prompt instruction + delimiter wrapping) is acknowledged as not a guarantee but standard practice. Mandating escape of ALL possible delimiter patterns is impractical — the set of patterns is open-ended. The existing mitigations are proportionate to the threat model (developer-authored seeds, not adversarial input). | 2026-02-22 00:11:52 UTC |
| R1-F3 | Exclude short parameter values and common English stop words from find_missing_parameters() completeness check to reduce false positives |  | The function is already specified as a simple text-only substring search in REQ-PEM-008. Adding stop word filtering and minimum length thresholds significantly increases implementation complexity for a P2 requirement. The false positive concern is valid but the spec completeness check produces warnings (injected into drafter feedback), not failures. False positives in warnings are acceptable and preferable to the complexity of maintaining a stop word list. This is an optimization that can be addressed during implementation if the false positive rate proves problematic. | 2026-02-22 15:35:03 UTC |
| R1-F4 | Acknowledge fcntl.flock advisory-only limitations and add NFS filesystem detection with warnings |  | R7-S3 (Windows compatibility for fcntl.flock) was already rejected with the rationale that the codebase targets Unix-like systems. The NFS concern is a valid operational consideration but adding filesystem type detection and NFS-specific warnings is implementation-level defensive coding, not a requirements specification concern. The existing requirement for file-level locking is sufficient; the implementation can choose an appropriate locking library. | 2026-02-22 15:35:03 UTC |
| R1-F1 | Change resolve_task_context() return type from dict to OrderedDict or typed dataclass to enforce section ordering |  | As noted in the companion R1-S8 rejection, Python dicts preserve insertion order since 3.7. The requirements already list sections in a specific order. Changing to OrderedDict adds a type import for no behavioral change, and a TaskContext dataclass would over-constrain the interface — the number and names of sections may evolve as pipeline context grows. The current dict return type with documented section ordering is sufficient and more flexible. | 2026-02-23 03:11:56 UTC |
| R1-F5 | Change manifest write from end-of-workflow to incremental per-feature updates for long-running workflow observability |  | The current design intentionally writes the manifest after all features are processed, producing a consistent, complete provenance record. Incremental manifest updates introduce complexity: partial manifests on disk during execution could be read by concurrent pipeline stages or monitoring tools, requiring consumers to handle incomplete data. The existing .prime_contractor_state.json already provides per-feature progress tracking and resume capability. Adding incremental manifest writes duplicates this responsibility and complicates the atomic write requirement (R1-S6). Operators needing real-time progress should use the state file or OTel spans. | 2026-02-23 03:11:56 UTC |
| R1-F2 | Clarify whether the Prime Contractor or the lead contractor workflow owns the spec-to-draft validation integration point. |  | REQ-PEM-008 already specifies the source file as `lead_contractor_workflow.py` and states it runs 'after _create_spec() and before _create_draft()'. The lead contractor workflow is the component that orchestrates spec/draft phases — this is the correct integration point. The Prime Contractor delegates to the lead contractor workflow, which handles the validation internally. The requirement header and content are consistent. This was also addressed by the accepted R4-F3 which ensured the implementation plan includes this file. | 2026-02-23 17:20:43 UTC |
| R1-F5 | Specify the lifecycle timing of staleness detection relative to feature queue initialization, and define that matching checksums skip all feature generation entirely. |  | The existing requirements already cover this implicitly. REQ-PEM-013 says 'before reusing cached generation results' which naturally places it before feature generation. The staleness check operates on the seed-level checksum, not per-feature — it's inherently an all-or-nothing check. The workflow lifecycle (seed loading → staleness check → feature generation) is the obvious implementation order. Additionally, test #16 already specifies 'zero LLM API calls, no file modifications' for matching checksums, which validates the skip behavior. Adding explicit lifecycle anchoring is redundant with the existing acceptance criteria. | 2026-02-23 17:20:43 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:55:29 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | completeness | critical | Define error handling behavior when explicit `--mode pipeline` is set but required pipeline signals are absent from the seed | REQ-PEM-002 defines auto-detection signals but doesn't specify what happens if a user forces pipeline mode on a seed lacking required data. Should this fail fast, warn and continue, or silently degrade? | New section under REQ-PEM-002 or REQ-PEM-003 | Test: force `--mode pipeline` on minimal seed, verify defined behavior |
| R1-S2 | testability | high | Specify concrete thresholds for "byte-identical" output claim in REQ-PEM-006 acceptance criteria | "Output is byte-identical to current behavior" is difficult to verify given non-deterministic LLM outputs. Clarify whether this applies to structural output (file paths, JSON schema) or actual generated code content | REQ-PEM-006 acceptance criteria | Define comparison scope; create deterministic test fixtures |
| R1-S3 | ambiguity | high | Clarify the relationship between `ModeConfig` (REQ-PEM-003) and `ContextResolutionStrategy` (REQ-PEM-004) | Both mechanisms govern mode-specific behavior. Document whether strategies receive ModeConfig, whether ModeConfig determines which strategy to use, or if they're independent concepts | Add subsection after REQ-PEM-004 explaining interaction | Review for single source of truth for mode behavior |
| R1-S4 | completeness | medium | Add requirement for mode persistence across workflow resume/retry scenarios | If a workflow fails mid-execution and is resumed, the execution mode must be consistent. Current spec doesn't address serialization of ExecutionMode in state files | New REQ-PEM-018 or add to REQ-PEM-001 | Test: interrupt workflow, resume, verify mode consistency |
| R1-S5 | consistency | medium | Reconcile `source_checksum` requirement between REQ-PEM-005 and REQ-PEM-007 | REQ-PEM-005 lists `source_checksum` as `Optional[str]` in SeedContext, but REQ-PEM-007 states pipeline strategy must "Validate source_checksum is present". Clarify: is it required for pipeline mode? | Update REQ-PEM-005 to annotate pipeline-mode requirements or add validation logic specification | Schema validation test for pipeline mode seeds |
| R1-S6 | feasibility | medium | Specify behavior when `context_files` referenced in SeedContext are missing or unreadable | REQ-PEM-005 includes `context_files: List[Dict[str, Any]]` but doesn't define handling for file access errors during context resolution | Add error handling clause to REQ-PEM-006 and REQ-PEM-007 | Test: provide seed with non-existent context file paths |
| R1-S7 | traceability | medium | Add traceability for REQ-PEM-010 to REQ-PEM-015 in the Traceability Matrix | REQ-PEM-010 (standalone feature construction) and REQ-PEM-015 (zero-change standalone) support each other but aren't linked in the matrix | Add row to "REQ-PEM → REQ-PC" or create new "Internal Dependencies" section | Matrix completeness review |
| R1-S8 | completeness | medium | Define thread-safety and concurrency model for SeedContext and ContextResolutionStrategy | REQ-PEM-005 states SeedContext is "immutable thereafter" but doesn't specify concurrent access patterns if multiple features are processed in parallel | Add concurrency note to REQ-PEM-005 or create new non-functional requirement | Concurrent feature generation test |
| R1-S9 | testability | low | Add negative test cases to verification matrix for invalid mode transitions | Test Strategy covers positive paths but lacks tests for: invalid mode string in CLI, mode change attempt mid-workflow, conflicting flags (e.g., `--mode standalone --validate` edge cases) | Extend Verification table with tests 21-23 | Execute negative test suite |
| R1-S10 | ambiguity | low | Clarify semantics of `--no-validate` flag interaction with `--strict-validation` | REQ-PEM-016 mentions `--no-validate` and REQ-PEM-014 mentions `--strict-validation` but their precedence when both are specified is undefined | Add flag precedence rules to REQ-PEM-016 | Test: specify conflicting flags, verify error or defined precedence |

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:55:56 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | consistency | critical | Reconcile the conflicting requirements of `SeedContext` immutability (REQ-PEM-005) and backward-compatible property setters (REQ-PEM-017). The current requirements are contradictory, as a class with public setters cannot be immutable. | An object cannot be both immutable and have its state changed via setters after initialization. This contradiction must be resolved for the requirement to be implementable. The design should either commit to immutability (and disallow setters) or acknowledge mutability. | REQ-PEM-005, REQ-PEM-017 | Add a test that attempts to use a property setter after workflow initialization and asserts that the chosen behavior (e.g., raising an exception, or successfully updating the state) occurs as specified in the updated requirement. |
| R2-S2 | completeness | high | Clarify how `PrimeContractorWorkflow` and `SeedContext` are initialized when no seed file is provided, as implied by the `add_feature()` method in REQ-PEM-010. | The `add_feature` method suggests a new "seedless" execution path, but the rest of the document assumes a seed is always present for context. This creates a significant gap in the workflow's initialization logic that must be defined. | REQ-PEM-010 | Add a test case that initializes `PrimeContractorWorkflow` without a seed, uses `add_feature()`, and successfully runs to completion in `STANDALONE` mode, verifying that `SeedContext` is populated with sane defaults. |
| R2-S3 | ambiguity | high | In REQ-PEM-007, define the expected structure or format for `architectural_context` which is described as "formatted, not raw JSON". | "Formatted" is ambiguous. The implementation needs a clear contract for this transformation (e.g., converted to Markdown, a specific textual summary, etc.) to ensure the LLM receives context effectively and to enable proper unit testing. | REQ-PEM-007, `resolve_task_context` details | Unit test the `PipelineContextStrategy` to verify it transforms a sample raw JSON `architectural_context` into the specified target format. |
| R2-S4 | completeness | medium | For `PIPELINE` mode, introduce a distinction between "critical" context fields that cause failure if missing, and "optional" fields that only trigger a warning. | Not all missing context has the same impact. Failing fast when critical data is absent (e.g., `onboarding.project_objectives`) makes the pipeline more robust and prevents wasted execution on runs that are guaranteed to produce poor results. | REQ-PEM-007, `resolve_seed_context` details | Create two test cases for `PIPELINE` mode: one with a missing "optional" field that logs a warning and succeeds, and one with a missing "critical" field that raises an exception and fails. |
| R2-S5 | ambiguity | medium | Clarify the staleness detection logic in REQ-PEM-013. The check "Compare `source_checksum` and `workflow_id` against current seed" is confusing, as `workflow_id` is a run-specific ID, not part of the seed. | The current phrasing is unclear and seems to describe an incorrect algorithm. A precise, correct algorithm for staleness is crucial for the feature's reliability and to prevent incorrect cache reuse or unnecessary regeneration. | REQ-PEM-013 | Refine the test cases for staleness detection: 1) manifest checksum matches current seed checksum -> reuse. 2) manifest checksum differs -> regenerate. 3) The role of `workflow_id`, if any, should be explicitly tested. |
| R2-S6 | completeness | medium | Add `prompt_tokens` and `completion_tokens` to the per-feature entry in the `generation-manifest.json` schema defined in REQ-PEM-012. | While `cost_usd` is useful, token counts are fundamental metrics for LLM operations. Including them provides deeper observability for debugging prompt performance and fine-tuning cost models, which are common downstream needs. | REQ-PEM-012, JSON schema example | Inspect the `generation-manifest.json` artifact in a pipeline test run to confirm the presence and correctness of the token count fields for each feature. |
| R2-S7 | completeness | medium | Specify the error behavior for the runner script when an invalid value is passed to the `--mode` flag (e.g., `--mode foobar`). | Robust command-line interfaces must validate user input and provide helpful feedback. Defining this behavior prevents unhandled exceptions and improves the user experience. | REQ-PEM-016, Acceptance criteria | Add a test that executes the script with an invalid `--mode` argument and asserts that it exits with a non-zero status code and prints a user-friendly error message listing the valid modes. |
| R2-S8 | testability | low | Explicitly state the configuration precedence: CLI flags override `ModeConfig` settings, which are derived from the `ExecutionMode`. | Making the override hierarchy explicit (e.g., `--mode pipeline --no-validate` results in pipeline context but no validation) removes ambiguity for both developers and users, and makes the system's behavior easier to test and predict. | REQ-PEM-003 or REQ-PEM-016 | Add test cases for flag combinations, such as running in `PIPELINE` mode with `--no-validate` and asserting that validators are skipped, and running in `STANDALONE` mode with `--validate` and asserting they are run. |
| R2-S9 | completeness | low | Specify in REQ-PEM-002 that the `{signals}` in the auto-detection log message should be a list of the actual keys found in the seed that triggered `PIPELINE` mode. | A more specific log message (`...signals: "onboarding", "service_metadata"`) provides immediate insight into *why* a mode was chosen, accelerating debugging without requiring manual inspection of the source seed file. | REQ-PEM-002, Acceptance criteria | Capture logs during a test run and assert that the auto-detection message contains the specific key names that triggered `PIPELINE` mode for that test's seed file. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:58:16 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | ambiguity | high | REQ-PEM-007 references `find_missing_parameters()` from `prompt_utils.py` but this function is not defined in the requirements or the plan | The spec-to-draft validation in REQ-PEM-008 depends on a shared utility that isn't specified anywhere. Implementation cannot proceed without this definition. | REQ-PEM-008 or new appendix defining shared utilities | Define function signature, input/output, and location |
| R3-F2 | completeness | medium | REQ-PEM-003 `ModeConfig` lacks specification for individual behavior override mechanism | Requirements state "Individual behaviors can be overridden via CLI flags" but don't define which ModeConfig fields are overridable or the override syntax | REQ-PEM-003 acceptance criteria | Add table mapping CLI flags to ModeConfig fields |
| R3-F3 | consistency | medium | REQ-PEM-011 lists "OTel spans" as STANDALONE="Only if instrumentor configured" but REQ-PEM-001 doesn't include OTel configuration in mode declaration | OTel behavior varies by mode but isn't part of ExecutionMode enum or ModeConfig specification in REQ-PEM-003 | REQ-PEM-003 ModeConfig table | Add `emit_otel_spans: bool` to ModeConfig specification |
| R3-F4 | ambiguity | medium | REQ-PEM-007 specifies `feature.metadata["requirements_text"]` but REQ-PEM-009 lists `requirements_text` as a top-level enrichment field, not nested under `metadata` | Inconsistent field path specification will cause implementation confusion | Reconcile REQ-PEM-007 and REQ-PEM-009 | Define canonical path for requirements_text |
| R3-F5 | testability | low | Verification Test #6 claims "Standalone strategy produces identical gen_context" but this is unverifiable without fixed LLM responses | Test strategy doesn't account for non-deterministic components in context building | Test Strategy table, Test #6 | Specify mock/fixture strategy for deterministic testing |

#### Review Round R2

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:59:29 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | ambiguity | medium | The structure of the `Dict[str, Any]` for each item in `context_files` (REQ-PEM-005) is undefined. | To implement context file loading, developers need to know the expected keys and value types in this dictionary (e.g., `{'path': str, 'name': str, 'type': str}`). Leaving it as `Any` creates implementation ambiguity and risks integration failures. | REQ-PEM-005, `SeedContext` dataclass definition | A schema validation test should be added for the seed file, asserting that `context_files` entries conform to the newly defined structure. |
| R2-F2 | clarity | low | Clarify the sequence of operations between "default mode" (REQ-PEM-001) and "auto-detection" (REQ-PEM-002). | The requirements are slightly confusing. It should be explicitly stated that the effective mode is determined in a specific order: 1) explicit CLI flag, 2) if no flag, auto-detection from seed, 3) `STANDALONE` is the result of auto-detection if no signals are found. | REQ-PEM-001 or REQ-PEM-002 | The existing test cases for auto-detection and explicit override cover this, but the requirement's text should be sharpened to reflect this procedural logic. |

#### Review Round R3

**Reviewer**: claude-4 (claude-opus-4-5)
**Date**: 2026-02-20 20:01:04 UTC
**Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | traceability | high | Add bidirectional trace from each REQ-PEM requirement back to the originating problem statement section or design principle it addresses | The Traceability Matrix maps REQ-PEM to downstream REQ-PC and IMP-P, but no traceability exists back to the Problem Statement or Design Principle. This makes it impossible to verify that all stated problems have corresponding solutions, or to assess impact if the problem statement changes. | New subsection "### REQ-PEM → Problem Statement Traceability" after the existing Traceability Matrix | Review confirms each problem (underperformance, fragility) maps to at least one REQ-PEM; audit trail enables change impact analysis |
| R3-S2 | traceability | high | Add requirement IDs to the Execution Mode Model diagram elements to enable visual-to-requirement tracing | The ASCII diagram (lines 37-51) shows architectural components (ContextResolutionStrategy, resolve_* methods) but lacks any reference to which REQ-PEM requirements define each element. Reviewers cannot trace diagram elements to formal requirements. | Annotate diagram with REQ-PEM-004 for the strategy box, REQ-PEM-001 for mode distinction, and add a legend below the diagram | Diagram audit confirms all boxes/flows have traceable requirement references |
| R3-S3 | traceability | medium | Define explicit trace identifiers for the ModeConfig behaviors in REQ-PEM-003 table rows to enable fine-grained validation | The behavior table in REQ-PEM-003 lists 7 distinct behaviors but they lack individual identifiers. Test #1-20 cannot trace to specific behavior rows, making gap analysis between requirements and tests incomplete. | Add identifiers (e.g., BEH-001 through BEH-007) to each row in REQ-PEM-003's behavior table; update Test Strategy to reference these | Test coverage matrix maps each BEH-* to at least one test case |
| R3-S4 | feasibility | high | Specify the mechanism for property setter compatibility in REQ-PEM-017 when SeedContext is immutable per REQ-PEM-005 | REQ-PEM-005 states SeedContext is "immutable thereafter," but REQ-PEM-017 requires "code that writes `workflow.seed_onboarding = {...}` continues to work." These are contradictory — setters cannot modify an immutable dataclass. Implementation will fail or require unstated workarounds. | Add clarifying note to REQ-PEM-017 specifying that setters either (a) raise error if called after initialization, (b) replace entire SeedContext, or (c) are only valid during construction phase | Unit test attempts post-init setter assignment and verifies documented behavior |
| R3-S5 | feasibility | high | Define the format and source of `source_checksum` computation for staleness detection in REQ-PEM-012/013 | REQ-PEM-012 references `source_checksum` "from seed" and REQ-PEM-013 compares it, but no requirement specifies: (a) what inputs are hashed, (b) the hash algorithm, (c) whether it's computed by the Prime Contractor or inherited from upstream. Without this, two implementations could produce incompatible checksums. | Add new sub-requirement under REQ-PEM-012 defining checksum algorithm (e.g., SHA-256), inputs (seed JSON canonical form), and responsibility (upstream stage or Prime Contractor computes) | Integration test verifies checksum stability across serialization round-trips |
| R3-S6 | feasibility | medium | Specify behavior when `--mode pipeline` is explicitly requested but required pipeline signals are absent from seed | REQ-PEM-002 allows explicit mode override, but REQ-PEM-007 logs warnings for missing fields. If user forces pipeline mode with a minimal standalone seed, should it (a) proceed with warnings, (b) fail fast, or (c) fall back to standalone behavior? Undefined behavior creates implementation ambiguity. | Add acceptance criterion to REQ-PEM-002: "Explicit `--mode pipeline` with a seed lacking all pipeline signals MUST [proceed with degraded quality / fail with descriptive error]" | Test verifies explicit pipeline mode with minimal seed produces specified behavior |
| R3-S7 | consistency | high | Reconcile validator naming between REQ-PEM-007 and REQ-PEM-012 — different names used for equivalent validators | REQ-PEM-007 lists validators as "Import/dependency cross-validation (AR-143 equivalent)" while REQ-PEM-012's manifest example uses `"import_dependency"`. The names don't match, creating ambiguity about whether these are the same validators. | Standardize validator identifiers across both requirements; define canonical names in a shared table (e.g., `import_dependency`, `protocol_fidelity`, `placeholder_detection`, `dockerfile_coherence`) | Grep for validator names confirms single canonical identifier per validator type |
| R3-S8 | consistency | medium | Align the test numbering gap between REQ-PEM-006 test (#6) and REQ-PEM-007 test (#7) with missing coverage for ModeConfig derivation (REQ-PEM-003) | The Test Strategy jumps from test #5 (REQ-PEM-017) to #6 (REQ-PEM-006), skipping explicit tests for REQ-PEM-003's ModeConfig derivation logic. REQ-PEM-003 acceptance criteria state "Configuration is a ModeConfig dataclass derived from ExecutionMode" but no test validates this derivation. | Add test case: "ModeConfig correctly derived from ExecutionMode enum value" targeting REQ-PEM-003 | Test coverage analysis confirms REQ-PEM-003 has dedicated test |
| R3-S9 | consistency | medium | Standardize "context_files" field across SeedContext definition (REQ-PEM-005) and context resolution usage (REQ-PEM-007) | REQ-PEM-005 defines `context_files: List[Dict[str, Any]]` in SeedContext, but REQ-PEM-007's resolve_seed_context mentions extracting `context_files` for "plan document and design references" without specifying the dict schema. This creates inconsistency between data structure and usage semantics. | Add schema definition for context_files dict structure in REQ-PEM-005 (e.g., `{"type": str, "path": str, "content": Optional[str]}`) | Schema validation test confirms context_files entries match defined structure |
| R3-S10 | traceability | medium | Add version/dependency trace showing which REQ-PEM requirements require updates if dependent document versions change | The Related Documents table lists dependencies but doesn't specify version constraints or change impact. If PRIME_CONTRACTOR_REQUIREMENTS.md changes REQ-PC-009, which REQ-PEM requirements need re-review? Currently untraceable. | Add "Version Dependency" column to Related Documents table and/or add a "Change Impact" subsection listing which REQ-PEM are affected by changes to each dependency | Document review process can identify affected requirements when dependencies update |

#### Review Round R4
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:01:48 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | traceability | critical | Version-lock document dependencies. | The document depends on `REQ-PC` and `REQ-PPE` but doesn't specify their versions. Without versioning, the traceability matrix becomes ambiguous over time as the source documents evolve, making it impossible to verify which version of a requirement is being met. | Update the "Depends on" section to include a specific version number or git commit SHA for each referenced requirements document. | Review the updated section to confirm that all external document dependencies are pinned to a non-floating version. |
| R4-S2 | traceability | critical | Persist the effective configuration in `generation-manifest.json`. | The manifest in REQ-PEM-012 records the `execution_mode`, but not the final, effective configuration after CLI overrides (e.g., running in `PIPELINE` mode with `--no-validate`). This makes a run non-reproducible from its artifacts, defeating a key purpose of the manifest. | Add an `effective_config` object to the `generation-manifest.json` schema in REQ-PEM-012, capturing the final state of all `ModeConfig` behaviors after overrides are applied. | Inspect the `generation-manifest.json` from a test run that uses CLI overrides (e.g., `--mode pipeline --no-validate`) and confirm the manifest accurately reflects that validation was disabled. |
| R4-S3 | traceability | high | Add data lineage checksums for injected context to `generation-manifest.json`. | When debugging a poor generation, it's vital to know exactly what context was provided. REQ-PEM-007 injects many context blocks, but the output manifest has no link back to the source data. This makes it hard to trace failures back to specific inputs. | In REQ-PEM-012, extend the per-feature entry in the manifest to include a `context_checksums` dictionary, containing hashes of the specific context blocks injected (e.g., `architectural_context`, `plan_context`). | Create two seed files with a minor change in the `architectural_context`. Run the pipeline for both. Verify that the `context_checksums` in the two resulting manifests are different, reflecting the input change. |
| R4-S4 | feasibility | critical | Resolve contradictory requirements for `SeedContext` immutability vs. property setters. | REQ-PEM-005 states `SeedContext` is "immutable", while REQ-PEM-017 requires property setters like `workflow.seed_onboarding = {...}` to continue working. An object cannot be both immutable and have its contents changed via setters. This contradiction makes the requirement technically infeasible to implement cleanly. | Update REQ-PEM-017 to clarify the interaction. Either relax the immutability constraint in REQ-PEM-005 or deprecate the property setters in favor of initialization-only configuration. | The implementation code for `PrimeContractorWorkflow` and `SeedContext` should be reviewed to ensure a consistent and coherent approach to state management, free of contradictory patterns. |
| R4-S5 | feasibility | high | Relax the "byte-identical" constraint in REQ-PEM-006 to "semantically equivalent". | Requiring the refactored `StandaloneContextStrategy` to produce "byte-identical" output is overly strict and brittle. Minor, inconsequential changes from the refactoring (e.g., dict key ordering in JSON) could fail this test, causing significant engineering effort for no user benefit. | In REQ-PEM-006, change "Output is byte-identical to current behavior" to "Output is semantically equivalent to current behavior, with no functional regressions." | The validation approach should be a functional comparison, not a byte-level diff. For example, parse generated JSON and compare the data structures, or compile generated code and run its tests. |
| R4-S6 | feasibility | high | Specify the mechanism for providing non-feature configuration in the "seedless" `add_feature` mode. | REQ-PEM-010 introduces `queue.add_feature()` that works "without a seed file". This is underspecified. It's unclear how essential workflow parameters normally found in the seed (e.g., output directory, model selection, global settings) would be configured in this mode. | Add acceptance criteria to REQ-PEM-010 requiring a clear mechanism for providing workflow-level configuration when a seed file is not used, likely via parameters to the `PrimeContractorWorkflow` constructor. | Write a unit test that instantiates and runs the workflow using `queue.add_feature()` without a seed file, successfully configuring the output path via a constructor argument. |
| R4-S7 | consistency | critical | Explicitly define the precedence of configuration sources. | REQ-PEM-003 and REQ-PEM-016 introduce `ModeConfig` and CLI override flags, but do not specify their interaction. For example, it's unclear what should happen if a user specifies `--mode pipeline` (which enables validation) and `--no-validate`. Ambiguous precedence leads to unpredictable behavior. | Add a new requirement under "Layer 1" that defines the configuration hierarchy, e.g., "CLI flags MUST always take precedence over the defaults defined in a `ModeConfig` profile. Conflicting flags (e.g. `--validate` and `--no-validate`) MUST raise a CLI parsing error." | Create a test case where the `PIPELINE` mode is selected but `--no-validate` is passed, and assert that no validators are run. Create another test that passes conflicting flags and assert that the script exits with an error. |
| R4-S8 | consistency | high | Re-evaluate staleness detection logic in REQ-PEM-013. | The logic compares both `source_checksum` and `workflow_id`. Comparing `workflow_id` is inconsistent with the goal of content-addressable caching. If the input seed is identical (`source_checksum` matches), the output should be reusable regardless of which `workflow_id` produced it. | Modify REQ-PEM-013 to base staleness primarily on `source_checksum`. If the intent is to track the generator version, a `workflow_version` or `code_version` should be added to the manifest and checked explicitly. | Create a cached result with a manifest. Re-run the workflow with an identical seed but a different `workflow_id`. Assert that the cached result is reused, not regenerated. |
| R4-S9 | consistency | medium | Relocate the `ExecutionMode` enum to a shared types module. | REQ-PEM-001 places `ExecutionMode` in `prime_contractor.py`. However, this enum is a core concept used by the CLI script, the context strategies, and the workflow. Placing it in the main workflow file creates poor cohesion and risks future circular import errors. | Modify REQ-PEM-001 and REQ-PEM-005 to specify that `ExecutionMode` and `SeedContext` should be defined together in a new, shared module like `src/startd8/contractors/types.py`. | Verify through code review that the `ExecutionMode` enum is defined in a location that does not create circular dependencies and is imported by `prime_contractor.py`, `context_resolution.py`, and `run_prime_workflow.py`. |
| R4-S10 | completeness | medium | Specify behavior for a corrupt `generation-manifest.json` file. | REQ-PEM-013 defines staleness detection by reading an existing manifest, but it doesn't describe what to do if the file is present but unparsable (e.g., corrupt JSON). This is a missing edge case that will lead to an unhandled exception. | Add an acceptance criterion to REQ-PEM-013: "If `generation-manifest.json` exists but is unparsable, the system MUST log a warning and proceed as if the file were absent (i.e., regenerate)." | Create a test where a malformed `generation-manifest.json` is placed in the output directory. Run the workflow and assert that it logs a warning and regenerates the output, rather than crashing. |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:04:22 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | completeness | high | REQ-PEM-012 manifest schema lacks `schema_version` migration strategy | The manifest includes `schema_version: "1.0.0"` but no requirement specifies how consumers should handle version mismatches or how to migrate manifests when schema evolves. This will cause integration failures when schema changes. | REQ-PEM-012 acceptance criteria: add version compatibility rules | Test: attempt to read 1.0.0 manifest with 1.1.0 reader; verify graceful handling |
| R3-F2 | clarity | medium | REQ-PEM-007 structured sections lack maximum length specifications | Pipeline context sections (`architectural_context`, `plan_context`, etc.) have no size limits. Uncontrolled growth could exceed LLM context windows and cause generation failures. | REQ-PEM-007 resolve_task_context: add maximum token/character limits per section with truncation strategy | Test with oversized context; verify truncation occurs and generation succeeds |
| R3-F3 | testability | medium | Verification Test #15-16 for staleness detection lack checksum computation details | Tests specify "matching checksum reuses" but don't define how to create test fixtures with known checksums, making tests non-reproducible. | Verification section: add fixture generation strategy for deterministic checksum testing | Provide example test seed with pre-computed checksum |

#### Review Round R4

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:05:37 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | consistency | high | Resolve contradiction between `SeedContext` defaults and pipeline mode warnings. | REQ-PEM-005 specifies `default_factory=dict` for context fields, which means they are never "missing". However, REQ-PEM-007 requires logging warnings for missing fields. The requirements should state that pipeline mode checks for key *presence* in the raw seed before applying defaults. | REQ-PEM-005 and REQ-PEM-007. | A test for pipeline mode should use a seed where `onboarding` key is absent, and verify a warning is logged. |
| R4-F2 | completeness | high | Enhance staleness detection to be code-version aware. | REQ-PEM-013's staleness check is based only on the input `source_checksum`. It is blind to changes in the generator code itself (e.g., updated prompt templates, bug fixes). A stale artifact could be reused incorrectly, propagating old bugs. | REQ-PEM-012, REQ-PEM-013. | Add a `generator_version` (e.g., a git commit hash) to the `generation-manifest.json` and include it in the staleness comparison. |
| R4-F3 | completeness | critical | The implementation plan completely omits REQ-PEM-008. | The plan's "Untouched Files" section explicitly excludes `lead_contractor_workflow.py`, but REQ-PEM-008 (Spec-to-Draft Validation) requires modifications to this file. This is a major gap where a P2 requirement is entirely unaddressed. | Add a new step to the implementation plan, likely in Phase 4, to implement the spec completeness check. | Add test cases #9 and #10 from the requirements doc to the implementation plan's test suite. |
| R4-F4 | security | critical | Add an explicit requirement for secure handling of external inputs. | The requirements document lacks any mention of security. Critical vulnerabilities like path traversal and prompt injection are not forbidden by the current requirements, making it possible to have a compliant but insecure implementation. | Add a new top-level requirement (e.g., REQ-PEM-018: Secure Input Handling). | Security-focused code reviews and penetration tests should be added to the verification strategy. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:20:00 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | traceability | high | Add traceability from REQ-PEM requirements to specific test cases in the Verification section (Test Strategy table should reference back to which REQ-PEM IDs each test validates, but should also map to concrete test file paths or test class names) | The current Test Strategy table lists which REQ-PEM each test validates, but there is no forward link from requirements to test implementation artifacts. This creates a gap when verifying test coverage during implementation — developers cannot confirm which test file implements Test #7 for REQ-PEM-007. Bidirectional traceability is essential for audit and maintenance. | Add a new "Traceability to Tests" subsection after the Test Strategy table mapping REQ-PEM-XXX to expected test file paths (e.g., `test_context_resolution.py::TestPipelineStrategy`) | Review during implementation: verify each REQ-PEM has at least one mapped test file; CI check that mapped test files exist |
| R5-S2 | traceability | high | Add traceability links from ExecutionMode enum values to the configuration behaviors they govern (REQ-PEM-001 defines the enum but REQ-PEM-003 defines behaviors separately; no explicit link shows which behaviors belong to which mode) | The Execution Mode Model diagram shows a visual relationship, but the requirements themselves lack explicit linking. A developer implementing STANDALONE mode must cross-reference REQ-PEM-001 and REQ-PEM-003 manually, risking omission. An explicit mapping table from enum value → governed behavior IDs would ensure complete implementation. | Add a "Mode-Behavior Traceability" table within REQ-PEM-001 or as a new subsection after REQ-PEM-003 | Inspection: verify every behavior in REQ-PEM-003 table is traceable to exactly one enum value; implementation review confirms mapping accuracy |
| R5-S3 | traceability | medium | Add traceability from ContextResolutionStrategy methods to the specific REQ-PEM requirements they implement (the protocol in REQ-PEM-004 defines three methods but doesn't trace which downstream REQ-PEM each method satisfies) | REQ-PEM-004 defines `resolve_seed_context()`, `resolve_task_context()`, and `resolve_validation_config()`. REQ-PEM-006 and REQ-PEM-007 describe implementations but don't formally state which protocol method each behavior implements. This implicit mapping risks incomplete implementation of the strategy pattern. | Add a "Protocol Method Traceability" table within REQ-PEM-004 mapping each method signature to the REQ-PEM requirements it must satisfy | Code review checklist: verify each strategy implementation method is traceable to its governing requirement |
| R5-S4 | traceability | medium | Add traceability from output artifacts to consuming pipeline stages (REQ-PEM-011 and REQ-PEM-012 describe outputs but don't trace which downstream stage 7 validators or tools consume each artifact) | The document describes outputs like `generation-manifest.json` and structured cost reports but doesn't identify downstream consumers. Without this, changes to output format could break unknown dependencies. Pipeline mode outputs explicitly serve downstream stages — these dependencies should be traced. | Add a "Downstream Consumer Traceability" subsection in Layer 4 mapping each output artifact to its known consumers (e.g., `generation-manifest.json` → Stage 7 validators, OTel dashboard) | Cross-reference with pipeline stage 7 requirements during integration testing |
| R5-S5 | traceability | medium | Add requirement IDs for the auto-detection signals in REQ-PEM-002 (the table lists four signals but these signals are not traceable to where they originate in the pipeline) | REQ-PEM-002's detection rules reference `onboarding.project_objectives`, `architectural_context`, `service_metadata`, and `ingestion_metrics.generator`. These fields are produced by upstream stages but the source requirements (presumably in PLAN_INGESTION_REQUIREMENTS.md) are not explicitly linked. A broken upstream could silently change auto-detection behavior. | Add a column "Source REQ" to the Detection Rule table in REQ-PEM-002 linking each signal to its originating requirement | Validate during integration: confirm each signal field is present in seeds from the traced upstream stage |
| R5-S6 | traceability | medium | Add traceability from SeedContext fields (REQ-PEM-005) to their upstream population sources and downstream consumers | REQ-PEM-005 defines SeedContext with 8 fields but doesn't trace where each field is populated (which upstream requirement ensures it) or where it's consumed (which downstream REQ-PEM uses it). This creates a hidden dependency graph that makes impact analysis difficult. | Add a "SeedContext Field Traceability" table showing each field's source requirement and consumer requirements | Static analysis: verify each field has at least one consumer traced; test coverage ensures population path is exercised |
| R5-S7 | traceability | low | Add version/change traceability for the Traceability Matrix itself (if REQ-PC-XXX requirements change, how is this matrix kept synchronized?) | The Traceability Matrix maps REQ-PEM to REQ-PC and IMP-P requirements. If those upstream requirements are modified, the matrix becomes stale. Without a synchronization mechanism or version lock, the traceability guarantees degrade over time. | Add a note in the Traceability Matrix section specifying the versions of dependent documents (e.g., "Traces to PRIME_CONTRACTOR_REQUIREMENTS.md v1.2.0") and a review trigger when dependencies change | Periodic review: compare traced requirement IDs against current versions of dependent documents |
| R5-S8 | consistency | medium | Clarify the relationship between REQ-PEM-013 staleness detection and REQ-PEM-003's "Staleness detection: Skip/Enforce" behavior row — they describe the same behavior but REQ-PEM-013 adds cache reuse logic not mentioned in REQ-PEM-003 | REQ-PEM-003 says "Staleness detection: Skip (STANDALONE) / Enforce per REQ-PC-011 (PIPELINE)". REQ-PEM-013 adds detailed logic about reading existing manifests and comparing checksums. The cache reuse semantics in REQ-PEM-013 (matching checksum = reuse) are not mentioned in the REQ-PEM-003 summary, creating a gap between the summary and detailed requirement. | Update REQ-PEM-003's "Staleness detection" row to reference the full behavior in REQ-PEM-013, or add cache-reuse summary to the table | Review: confirm REQ-PEM-003 table and REQ-PEM-013 are semantically consistent |
| R5-S9 | completeness | medium | Specify behavior when `--mode pipeline` is explicitly set but seed lacks pipeline signals (forced pipeline mode with insufficient context) | REQ-PEM-002 and REQ-PEM-003 describe auto-detection and mode-specific behaviors, but don't specify what happens when a user forces `--mode pipeline` on a seed that lacks onboarding, architectural_context, or service_metadata. Should this warn, error, or silently degrade? The logging requirements in REQ-PEM-003 suggest warnings, but this edge case should be explicit. | Add a note in REQ-PEM-002 or REQ-PEM-003 specifying explicit-mode-with-missing-signals behavior (recommend: proceed with warnings per pipeline logging behavior, not error) | Test case: explicit `--mode pipeline` with minimal seed, verify expected warnings logged |
| R5-S10 | traceability | low | Add traceability from CLI flags (REQ-PEM-016) to the specific requirements they override | REQ-PEM-016 lists `--mode`, `--validate`, `--force-regenerate`, `--no-validate` but doesn't trace which REQ-PEM each flag overrides. For example, `--validate` should trace to REQ-PEM-003 (validation behavior) and REQ-PEM-014 (validation results), while `--force-regenerate` traces to REQ-PEM-013 (staleness detection). | Add a "CLI Flag Traceability" table in REQ-PEM-016 mapping each flag to the requirement(s) it modifies | Implementation review: verify each flag implementation modifies only its traced requirements |

#### Review Round R6
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:20:49 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | traceability | high | Add a Requirement-to-Test traceability matrix. | The current test plan lists which requirement a test validates, but there is no corresponding matrix to easily verify that *every* requirement has test coverage. This makes it difficult to assess test completeness and identify gaps for critical P1 requirements. | Add a new "Requirements to Test Case Traceability" subsection to the "Verification" section. | The new matrix is populated and a review confirms that every REQ-PEM-XXX ID has at least one corresponding test case ID. |
| R6-S2 | traceability | high | Add versioning to the `Depends on` documents. | The `Depends on` section references external requirement documents without versioning. This creates a high risk that an unannounced update to a dependency (e.g., `PRIME_CONTRACTOR_REQUIREMENTS.md`) could render this design obsolete or incorrect. | Update the `Depends on` section at the top of the document to include specific version numbers or commit hashes for each document. | The CI process should include a check that the specified versions of dependency documents exist and are accessible. |
| R6-S3 | traceability | high | Formalize the `generation-manifest.json` as a versioned data contract with traced consumers. | REQ-PEM-012 defines a manifest but doesn't specify its consumers or how schema changes are managed. An untracked breaking change in this manifest could silently break downstream pipeline stages, representing a significant second-order risk. | Add a new requirement to "Layer 4: Output Contract" that mandates the manifest schema be versioned and that known downstream consumers are documented and traced. | Identify at least one downstream consumer and add a contract test to the CI pipeline that validates the generated manifest against the consumer's expected schema. |
| R6-S4 | traceability | high | Trace validator logic to its formal definition. | REQ-PEM-007 refers to validators by opaque identifiers like "AR-143 equivalent". This provides no traceability to the actual validation logic, making it impossible to verify if the correct behavior is being implemented. | Update the bullet points in REQ-PEM-007 under `resolve_validation_config` to replace opaque identifiers with hyperlinks to the documents or code modules where the validation rules are formally defined. | A technical review confirms that each validator reference links to a specific, reviewable definition of the validation logic. |
| R6-S5 | traceability | high | Mandate a "golden file" regression test for standalone mode behavioral parity. | REQ-PEM-006 and REQ-PEM-015 mandate exact behavioral parity with the previous version. This strong claim requires a formal, automated verification method to prevent regressions that would break existing standalone users. | Add a new, specific test case to the "Test Strategy" table for "Golden file regression for standalone mode output". | A new test is created that runs the standalone workflow on a canonical input seed and compares the output byte-for-byte against a pre-approved "golden" output file stored in the repository. |
| R6-S6 | traceability | medium | Create a configuration precedence table. | The interaction between defaults, auto-detection, `ModeConfig` (REQ-PEM-003), and CLI overrides (REQ-PEM-016) creates ambiguity. A formal precedence table is needed to trace the final behavior to its source configuration and prevent bugs from incorrect override logic. | Add a new table within or immediately after REQ-PEM-016 that explicitly defines the configuration override logic (e.g., CLI flag > ModeConfig > Auto-detect > Default). | Create test cases for each override scenario (e.g., `--validate` in `STANDALONE` mode, `--no-validate` in `PIPELINE` mode) and verify the behavior matches the precedence table. |
| R6-S7 | traceability | medium | Mandate code annotations to trace implementation back to requirements. | While the requirements list source files, the link is unidirectional and fragile. Mandating code comments (e.g., `// Implements: REQ-PEM-007`) provides bidirectional traceability, simplifying maintenance, auditing, and impact analysis. | Add a new "Implementation Guidance" section stating that key logic implementing a requirement MUST be annotated with the requirement ID. | A static analysis check or a linter rule is added to the CI pipeline to verify that code in the specified source files contains annotations linking back to the requirements they implement. |
| R6-S8 | traceability | medium | Explicitly trace internal dependencies between requirements. | The requirements have implicit internal dependencies (e.g., REQ-PEM-013 Staleness Detection depends on the manifest from REQ-PEM-012). Not tracing these makes it easier to misunderstand implementation order, leading to integration bugs. | Add a note to each requirement listing its direct dependencies on other REQ-PEMs within this document. | A design review is held to walk through the requirements and confirm all internal dependencies (e.g., "REQ-PEM-013 depends on REQ-PEM-012") have been identified and documented. |
| R6-S9 | completeness | medium | Refine auto-detection logic to be less brittle. | The auto-detection logic in REQ-PEM-002 ("any one signal triggers PIPELINE mode") is brittle. A user might add a single field like `service_metadata` to a standalone seed for other reasons, unintentionally triggering pipeline mode and its stricter checks, leading to confusing failures. | Modify the rules in REQ-PEM-002 to require a primary signal (e.g., `ingestion_metrics.generator`) or a combination of secondary signals to trigger `PIPELINE` mode. | Create test cases with "ambiguous" seeds (e.g., only one weak signal present) and verify the auto-detection resolves to the least surprising mode (`STANDALONE`). |
| R6-S10 | traceability | low | Add a section tracing "Alternatives Considered". | The project maintains a list of rejected suggestions. To prevent re-litigating old decisions and to preserve design rationale for future architects, the main document should explicitly link to the appendix containing rejected ideas. | Add a new section at the end of the document, "Design Rationale and Alternatives Considered," that briefly summarizes key decisions and links to Appendix B for details on rejected proposals. | The new section and a hyperlink to Appendix B are added to the document. |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:23:35 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | completeness | high | REQ-PEM-004 references ValidationConfig but doesn't define it | The ContextResolutionStrategy protocol returns `ValidationConfig` from `resolve_validation_config()`, but this type is never specified. Without knowing the structure (validators list, severity levels, skip conditions), implementations cannot satisfy the protocol. | REQ-PEM-004 or new REQ-PEM-004a: add ValidationConfig dataclass definition with fields like `validators: List[ValidatorCallable]`, `fail_on_warning: bool`, `skip_validators: List[str]` | Review: ValidationConfig has complete field specification; implementers can satisfy protocol without guessing |
| R5-F2 | clarity | high | REQ-PEM-007 resolve_task_context structure lacks field optionality specification | The pipeline context structure lists 8 enriched sections but doesn't specify which are mandatory vs. optional when data is present. Should `protocol_guidance` be omitted entirely if `service_metadata` is empty, or included with placeholder text? | REQ-PEM-007: for each structured section, specify: "MUST include if [condition], otherwise MUST omit" or "MUST include with [default] if data absent" | Implementation review: verify each section follows specified presence/absence rules |
| R5-F3 | testability | medium | REQ-PEM-006 "byte-identical" acceptance criterion is unverifiable | The requirement states "Output is byte-identical to current behavior" but LLM outputs are non-deterministic and dict serialization order varies. This criterion cannot be tested as written. Should specify structural equivalence for context building (pre-LLM) vs. behavioral equivalence for full workflow. | REQ-PEM-006 acceptance criteria: replace "byte-identical" with "structurally equivalent: resolve_task_context() produces dict with identical keys and values (order-independent) for identical inputs" | Unit test compares dicts using equality, not serialized bytes |
| R5-F4 | architecture | medium | REQ-PEM-012 manifest schema version lacks migration/compatibility requirements | The manifest includes `schema_version: "1.0.0"` but no requirements specify how to handle version mismatches (newer manifest read by older code, or vice versa). This will cause failures when schema evolves. | REQ-PEM-012: add acceptance criterion "System MUST handle manifests with unknown schema versions by: [logging warning and skipping staleness check / failing with descriptive error / attempting best-effort parse]" | Test: create manifest with version "2.0.0", verify defined handling behavior |
| R5-F5 | clarity | medium | REQ-PEM-003 ModeConfig lacks specification for OTel span behavior | The behavior table in REQ-PEM-003 lists 7 behaviors but REQ-PEM-011 mentions "OTel spans: Only if instrumentor configured (STANDALONE) / Yes (PIPELINE)" which isn't in ModeConfig. Either OTel is controlled by ModeConfig (add field) or it's external (clarify in REQ-PEM-011). | REQ-PEM-003: add `emit_otel_spans: bool` to ModeConfig or clarify in REQ-PEM-011 that OTel configuration is independent of ModeConfig | Review: OTel behavior is traceable to exactly one configuration source |

#### Review Round R6

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:24:36 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | consistency | critical | Reconcile the conflicting acceptance criteria in REQ-PEM-005 stating `SeedContext` is "immutable thereafter" with REQ-PEM-017's requirement for working property setters. | The requirements document is internally inconsistent. While the implementation plan found a workaround, the requirements themselves should not contain direct contradictions. One of these requirements must be rephrased to reflect the intended (mutable-during-setup) behavior. | Update the acceptance criteria of REQ-PEM-005 to clarify the lifecycle: "is populated once during workflow initialization and is treated as immutable after the execution phase begins." | The text of the two requirements is no longer contradictory. |
| R6-F2 | clarity | high | In REQ-PEM-007, specify the behavior for handling context fields that are present but empty (e.g., `service_metadata: {}`). | The requirement is ambiguous. It's unclear if an empty but present field should result in an empty "## Protocol Guidance" section in the prompt (which adds noise) or if the section should be omitted entirely. Explicitly requiring omission for empty data will improve prompt quality. | Add an acceptance criterion to REQ-PEM-007: "Context sections for which the source data is present but empty (e.g., an empty dictionary or list) MUST be omitted from the final `gen_context`." | A test using a seed with `service_metadata: {}` verifies that the `protocol_guidance` key is absent from the `gen_context` dictionary. |
| R6-F3 | completeness | high | Add requirements for handling I/O errors during the writing of the `generation-manifest.json` file in REQ-PEM-012. | The manifest is a critical output for pipeline integration, but the requirements do not specify what should happen if writing the file fails (e.g., disk full, permissions error). This could lead to silent failures or unhandled exceptions. The behavior (fail workflow vs. log warning) must be defined. | Add an acceptance criterion to REQ-PEM-012: "A failure to write `generation-manifest.json` due to an I/O error MUST be logged as an error but MUST NOT cause the entire workflow to fail." | A test uses a mock to raise an `IOError` during the manifest write operation and verifies that an error is logged and the workflow completes with a non-zero exit code but without an unhandled exception. |
| R6-F4 | ambiguity | critical | Define the `ValidationConfig` type referenced in REQ-PEM-004. | The `ContextResolutionStrategy` protocol requires a method `resolve_validation_config` that returns a `ValidationConfig` object. However, this type is never defined in the requirements or the implementation plan, making the protocol's signature incomplete and unimplementable as specified. | Add a definition for `ValidationConfig` near REQ-PEM-004, specifying its structure (e.g., a `TypedDict` or `dataclass` containing a list of validator callables and their configurations). | The implementation in Phase 2 includes a concrete `ValidationConfig` class definition that matches the new specification. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 21:15:29 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | consistency | high | Specify thread-safety guarantees for `ContextResolutionStrategy` implementations when used with parallel feature generation | REQ-PC-010 requires parallel generation support, but REQ-PEM-004's strategy protocol has no guidance on thread-safety. `PipelineContextStrategy.resolve_task_context()` may share mutable state (e.g., caching resolved context files). If the strategy caches or mutates internal state, concurrent calls for different features could corrupt context. | REQ-PEM-004, add requirement: "Strategy implementations MUST be thread-safe or stateless. Shared mutable state requires synchronization primitives." | Test: Run parallel generation with 10 features, verify no context corruption or race conditions |
| R7-S2 | completeness | high | Define behavior when `context_files` entries reference the same file path multiple times | REQ-PEM-005 defines `ContextFileEntry` list but doesn't specify handling of duplicate paths. If the same file appears with different `type` values or is listed twice, should it be loaded once or multiple times? This affects memory usage and potentially context ordering. | REQ-PEM-005, add: "Duplicate file paths in `context_files` MUST be deduplicated by path; the first entry's metadata is preserved." | Test: Seed with duplicate context_file paths verifies single load and first-entry metadata retention |
| R7-S3 | feasibility | medium | Clarify `fcntl.flock` availability and fallback for Windows and cross-platform state file locking | REQ-PEM-018 mandates `fcntl.flock` for state file locking, but `fcntl` is Unix-only. Windows developers testing locally would encounter ImportError. The document should specify a cross-platform locking strategy or explicitly scope state locking to Unix-like systems. | REQ-PEM-018, modify: "MUST use file-level locking via `filelock` library or equivalent cross-platform mechanism" | Test: State file locking works on both Linux CI and Windows local development |
| R7-S4 | testability | medium | Test #16 "matching checksum reuses" lacks specification of HOW reuse is verified | Test strategy specifies that matching checksums should reuse cached results, but doesn't define observable behavior to verify. Does "reuse" mean no LLM calls? No file writes? Specific log message? Without observable criteria, the test cannot be implemented deterministically. | Test Strategy table, Test #16: Add "Reuse verified by: zero LLM API calls, no file modifications in output directory, log message 'Staleness check: current (checksum match)'" | Updated test passes when all three observables are present |
| R7-S5 | ambiguity | medium | `effective_config` in manifest vs. `ModeConfig` serialization format not specified | REQ-PEM-012 shows `effective_config` JSON but REQ-PEM-003 defines `ModeConfig` as a frozen dataclass. How the dataclass serializes to JSON (field names, boolean representation, custom fields from CLI overrides) is unspecified. Could lead to schema drift between manifest versions. | REQ-PEM-012, add: "`effective_config` MUST serialize via `dataclasses.asdict(mode_config)` with no transformations. Field names match `ModeConfig` attribute names exactly." | Test: `ModeConfig` round-trips through manifest serialization/deserialization |
| R7-S6 | traceability | medium | No REQ-PEM requirement traces to REQ-PC-010 (parallel generation support) | The traceability matrix maps REQ-PEM to REQ-PC but omits REQ-PC-010 entirely. Since parallel generation could interact with context resolution and state persistence, this gap may mask integration risks. | Traceability Matrix, add row: "REQ-PEM-004, REQ-PEM-005 | REQ-PC-010 | Context strategy and SeedContext must support concurrent access for parallel generation" | Matrix audit confirms all REQ-PC requirements have at least one REQ-PEM mapping |
| R7-S7 | consistency | medium | `ValidationResult.severity` uses different vocabulary than REQ-PEM-014's "pass/warn/fail counts" | REQ-PEM-004 defines `severity: str` with values `"pass" \| "warn" \| "fail"`, but these aren't severity levels — they're outcomes. Meanwhile REQ-PEM-014 references "pass/warn/fail counts" implying the same vocabulary. The field name `severity` is misleading; it should be `outcome` or `status`. | REQ-PEM-004, rename: `severity: str` → `outcome: Literal["pass", "warn", "fail"]` with explicit Literal type annotation | Code review confirms field naming consistency across all validation-related code |
| R7-S8 | completeness | low | No guidance on handling `requirements_text` that exceeds context window limits | REQ-PEM-007 injects `requirements_text` from `feature.metadata` but doesn't address truncation or chunking when requirements are very long. Pipeline mode with detailed requirements could exceed model context limits. | REQ-PEM-007, add: "If `requirements_text` exceeds 4000 tokens, truncate with `[truncated: N tokens omitted]` suffix and log a warning." | Test: 10000-token requirements text produces truncated context and warning log |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R6-F1: Validates an important end-to-end integration risk; pipeline mode's OTel integration should be verified against real ContextCoreInstrumentor to catch configuration mismatches early.

#### Review Round R8
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 21:16:05 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | consistency | high | On resume, validate the current seed's checksum against a checksum stored in `.prime_contractor_state.json`. | REQ-PEM-001 requires persisting the mode for resume, but not the context itself. If the seed file is altered between runs, resuming could lead to an inconsistent state (new context, old progress). The state file must be bound to the specific seed version it was created with. | REQ-PEM-001 | Create a state file, modify the original seed, attempt to resume, and assert that the workflow fails with an informative error about the checksum mismatch. |
| R8-S2 | feasibility | medium | Augment workflow-level staleness detection with feature-level cache invalidation. | REQ-PEM-013 specifies an all-or-nothing cache invalidation based on the entire seed's checksum. A minor, non-code-related change (e.g., a typo fix in `project_objectives`) would needlessly invalidate all cached features, increasing cost and latency. | REQ-PEM-013 | Create a test where only a single feature's spec is changed in the seed. Verify that upon re-running, only that specific feature is regenerated, while others are reused from the cache. |
| R8-S3 | completeness | medium | Define and enforce dependencies between validators. | REQ-PEM-007 treats validators as independent. However, some checks may be meaningless or produce misleading results if a prerequisite check fails (e.g., checking Dockerfile coherence if protocol fidelity validation fails). This can hide the root cause of issues. | REQ-PEM-004 | Define a validator (`V2`) that depends on another (`V1`). Create a test case where `V1` fails. Assert that `V2` is marked as 'skipped' in the validation results, with a note about its failed dependency. |
| R8-S4 | ambiguity | high | Enforce `SeedContext` immutability programmatically after execution begins. | REQ-PEM-017 states that property setters "SHOULD NOT be called" mid-execution, and the behavior is "undefined." This is too weak and can lead to subtle, hard-to-debug state corruption bugs. The contract should be enforced with a runtime error. | REQ-PEM-017 | Write a unit test that calls a workflow property setter (e.g., `workflow.seed_onboarding = {}`) after the first feature has been processed. The test must assert that a `RuntimeError` is raised. |
| R8-S5 | completeness | critical | The system prompt must explicitly instruct the LLM to treat content within safe delimiters as non-instructional context. | REQ-PEM-018 requires wrapping user input in delimiters (e.g., XML tags) to mitigate prompt injection. This mitigation is incomplete and far less effective without a corresponding system instruction telling the model *how* to interpret those tags (i.e., as passive data, not commands). | REQ-PEM-018 | A static code review of the final system prompts used for generation must confirm the presence of an instruction telling the model to not interpret content within the context delimiters as instructions. |
| R8-S6 | consistency | high | Remove `ingestion_metrics.generator` as a signal for pipeline mode auto-detection. | REQ-PEM-002 creates a brittle coupling to the specific name of an upstream workflow (`PlanIngestionWorkflow`). Renaming that workflow would break detection. The presence of enriched data structures (`onboarding`, `service_metadata`, etc.) is a far more robust and decoupled signal of pipeline mode. | REQ-PEM-002 | Remove this rule. Verify that existing tests for pipeline mode auto-detection still pass based on the presence of structural data like `onboarding` or `architectural_context` in the seed. |
| R8-S7 | consistency | low | The graceful degradation for missing files in standalone mode should be explicitly applied to all optional file paths from the seed. | REQ-PEM-006 specifies that missing `context_files` should result in a warning, not an error. This behavior is not explicitly defined for other file paths like `artifacts.plan_document_path`. Inconsistent error handling for similar inputs can be confusing for users. | REQ-PEM-006 | Create a standalone test with a seed that points to a non-existent `plan_document_path`. Verify that the workflow runs to completion, a warning is logged, and the `plan_document_text` context is empty. |
| R8-S8 | traceability | high | Add a `toolchain` object to `generation-manifest.json` to record software versions. | REQ-PEM-012's manifest is missing key information for reproducibility and debugging. Without knowing the version of the generator code, libraries, and validators used, it's difficult to trace bugs or understand why a past generation produced a specific output. | REQ-PEM-012 | In a pipeline mode test, inspect the generated `generation-manifest.json` and assert the presence of a `toolchain` key containing non-empty version strings for the application and its key components. |
| R8-S9 | traceability | medium | Record the use of `--force-regenerate` in the `generation-manifest.json`. | REQ-PEM-013 and REQ-PEM-016 define the `--force-regenerate` flag but do not specify its effect on provenance. The manifest should reflect that regeneration was forced, as this is critical context for auditing and understanding why a cache was bypassed. | REQ-PEM-012 | Run the workflow in pipeline mode with the `--force-regenerate` flag. Inspect the output `generation-manifest.json` and assert that a field like `"regeneration_forced": true` is present. |
| R8-S10 | completeness | medium | Add a `global_settings` field to the `SeedContext` dataclass for workflow-level configuration. | REQ-PEM-005 defines `SeedContext` but omits a formal place for global settings from the seed (e.g., `model_selection`, `temperature`). This forces a split configuration model (some from seed, some from CLI/constructor), complicating pipeline orchestration which relies on the seed as the single source of truth. | REQ-PEM-005 | Add a `global_settings` field to a seed file. Initialize the workflow from this seed and verify that the settings (e.g., model selection) are correctly applied to the generation process, overriding any code defaults. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 21:21:54 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-PEM-012 manifest schema lacks per-feature `model` field data flow specification | The manifest example shows `"model": "anthropic:claude-sonnet-4-20250514"` per feature, but requirements don't specify how this data flows from the generator. Is it returned by `CodeGenerator.generate()`? Read from config? This creates implementation ambiguity. | REQ-PEM-012, add: "Per-feature `model` field MUST be populated from the `CodeGenerator.generate()` return value. Generator implementations MUST expose the model spec used." | Review confirms generator interface returns model info |
| R7-F2 | consistency | medium | REQ-PEM-007 architectural context "formatted not raw JSON" lacks transformation specification | Requirements state architectural_context should be "formatted, not raw JSON" but don't define the transformation. Is it Markdown? Prose? The implementation plan adds detail but requirements should be self-contained. | REQ-PEM-007, add: "Raw JSON architectural_context MUST be transformed to Markdown: top-level keys → headers, arrays → bullet lists, nested objects → indented sub-sections." | Transformation is fully specified in requirements |
| R7-F3 | testability | medium | REQ-PEM-006 "byte-identical" acceptance criterion conflicts with dict ordering variability | Requirements state "Output is byte-identical to current behavior" but Python dicts don't guarantee order. The implementation plan addresses this with "structurally equivalent" but the requirements text remains ambiguous. | REQ-PEM-006, change: "Output is byte-identical" → "Output is structurally equivalent (identical dict keys and values, order-independent comparison)" | Acceptance criterion is testable without false negatives from ordering |
| R7-F4 | completeness | medium | REQ-PEM-018 path traversal protection lacks specification of the sanitization function | Requirements mandate path validation but don't specify the mechanism. "Uses the existing `sanitize_path()` utility" references code that may not exist or may have different semantics. | REQ-PEM-018, add: "Path sanitization MUST resolve symlinks and verify the canonical path is within project root. Paths containing `..` or symlinks escaping root MUST be rejected." | Security test suite covers path traversal edge cases |

#### Review Round R8

- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 21:22:57 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | ambiguity | high | Clarify the schema for `validator_results` in the `generation-manifest.json`. | REQ-PEM-012's manifest example (`"validator_results": { "...": "pass|warn|fail" }`) is a simple summary, which conflicts with the `ValidationResult` type in REQ-PEM-004 that includes a `findings: List[str]`. Downstream consumers need to know if they will receive the full findings or just the outcome. | Update the JSON schema example in REQ-PEM-012 to reflect the full `ValidationResult` structure, or explicitly state that only the summary outcome is stored. | The acceptance criteria for REQ-PEM-012 should be updated to require a test that validates the manifest against the clarified, more detailed schema. |
| R8-F2 | completeness | medium | The `generation-manifest.json` schema in REQ-PEM-012 should support multiple models per feature. | The schema allows a single string for the `model` field. A complex feature might use different models for different stages (e.g., planning vs. coding). The current schema cannot accurately capture this provenance. | Modify the `model` field in the REQ-PEM-012 schema to be a `Dict[str, str]` (e.g., `{"coder": "model-a", "reviewer": "model-b"}`) or a `List[str]`. | A test for a feature that uses two mock models verifies that both model identifiers are correctly recorded in the manifest. |
| R8-F3 | testability | medium | The definition of when "execution begins" in REQ-PEM-017 is not precise enough to be testable. | The requirement to raise a `RuntimeError` for property setters used after execution begins depends on a clear, non-ambiguous definition of that event. "After execution begins" is a concept, not a specific event. | Add a sentence to REQ-PEM-017: "For the purpose of this requirement, 'execution begins' is defined as the first invocation of the internal `_generate_code()` method." | A test case can now be written to deterministically call a setter immediately before and immediately after the first call to `_generate_code` and assert the specified behavior. |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-21 00:54:46 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | interfaces | high | REQ-PEM-007's `gen_context` structure is specified but the boundary with `CodeGenerator.generate()` is not — requirements don't specify whether the generator expects named sections or a flat dict | The strategy builds structured context; the generator consumes it. Without defining this interface contract, implementations could build perfect context that the generator ignores or misinterprets. This is a critical architectural boundary that the requirements leave undefined. | Add interface contract to REQ-PEM-004 or new REQ-PEM-004a specifying gen_context schema expectations for CodeGenerator | Review CodeGenerator.generate() signature and verify gen_context keys are documented |
| R1-F2 | completeness | high | Requirements lack partial failure recovery semantics — REQ-PEM-012 shows per-feature status but no requirement governs crash recovery, partial manifest persistence, or resumability interaction with staleness | If the workflow crashes after generating 5 of 10 features, the cost is lost and staleness detection cannot leverage partial results. This is a significant operational gap for pipeline deployments where failures are common. | REQ-PEM-012: add partial manifest write behavior; REQ-PEM-013: add partial manifest staleness semantics | Test: crash at feature N, resume, verify features 1..N-1 are reused |
| R1-F3 | security | high | REQ-PEM-018 lacks resource exhaustion protections — no size limits on seed fields, context_files count, or JSON depth | A denial-of-service vector exists through oversized seed files. Path traversal and prompt injection are addressed but resource exhaustion is not. | REQ-PEM-018: add maximum size/count/depth constraints for all seed-sourced inputs | Test with oversized seed payloads; verify rejection with descriptive errors |
| R1-F4 | ops | medium | REQ-PEM-012 manifest write is not specified as atomic — concurrent readers or crash mid-write produces corrupt files | The requirement specifies permissions but not write atomicity. Since REQ-PEM-013 reads this file, and pipeline stages may run concurrently, a non-atomic write creates a race condition. | REQ-PEM-012: add atomic write requirement (temp file + rename) | Concurrent read/write test; crash-during-write test |
| R1-F5 | ambiguity | medium | REQ-PEM-014 `--strict-validation` exit behavior is underspecified — does it exit after ALL features are processed or immediately on first validation failure? | The requirement says "causes the workflow to exit with non-zero status code" but doesn't specify early-exit vs. complete-then-fail semantics. Early exit saves cost but loses information; complete-then-fail provides comprehensive validation results. | REQ-PEM-014: specify "workflow MUST process all features, then exit with non-zero status if any feature has severity 'fail'" | Test: 3 features, feature 1 fails validation, verify features 2-3 still processed before non-zero exit |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-22 00:09:35 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | interfaces | high | REQ-PEM-007's structured `gen_context` sections are built by the strategy but the consumer contract with `CodeGenerator.generate()` is unspecified — the generator may flatten, ignore, or reorder sections | This is the same architectural boundary issue as R1-S1. The requirements specify context *production* in detail but not context *consumption*. Without a generator-side contract, the structured sections may be rendered as a single blob, defeating the purpose of structured context. The fix is to either (a) specify that `gen_context` keys map to labeled prompt sections, or (b) require the strategy to produce a pre-formatted string. | REQ-PEM-004 or REQ-PEM-007: add note specifying how `gen_context` dict is rendered in the final LLM prompt | Integration test: inject known `gen_context` dict, capture prompt sent to LLM, verify sections appear with labels |
| R1-F2 | interfaces | high | `ContextResolutionStrategy` protocol lacks a defined mechanism for strategies to signal that context resolution itself failed (vs. producing degraded context) | `resolve_seed_context()` can return a `SeedContext` with empty fields (graceful degradation), but what if the seed JSON is malformed, a required file is locked, or a critical transformation fails? The protocol has no error contract — should strategies raise exceptions, return a sentinel, or set error flags on SeedContext? Without this, error handling is implementation-specific and untestable. | REQ-PEM-004: add error semantics: "Strategy methods MUST raise `ContextResolutionError` (subclass of `RuntimeError`) for unrecoverable resolution failures. The workflow MUST catch this and fail with exit code 1." | Test: strategy raises ContextResolutionError; verify workflow exits with code 1 and descriptive message |
| R1-F3 | completeness | medium | REQ-PEM-008 (Spec-to-Draft Validation) specifies modifications to `lead_contractor_workflow.py` but the source file in REQ-PEM-008 header doesn't match the actual code organization — the header says `src/startd8/workflows/builtin/lead_contractor_workflow.py` but this file was explicitly listed as "untouched" in earlier implementation plan discussions | This creates confusion about where the spec-to-draft validation should be implemented. If the lead contractor workflow is not modified, the validation must happen elsewhere (e.g., in PrimeContractorWorkflow between spec and draft phases). The requirements should clarify the implementation locus. | REQ-PEM-008: clarify whether validation hooks into lead_contractor_workflow.py or is implemented within PrimeContractorWorkflow's orchestration of the spec→draft pipeline | Review implementation to confirm validation is in the correct module |
| R1-F4 | completeness | medium | REQ-PEM-009 lists nine specific enrichment fields but doesn't specify behavior when the enriched seed contains fields that conflict with FeatureSpec's built-in attributes (e.g., if enrichment includes `name` or `description` that differs from the feature's primary fields) | The requirement says "MUST preserve all keys" but FeatureSpec likely has `name`, `description` as first-class fields. If enrichment metadata includes these same keys with different values, the round-trip behavior is ambiguous — does metadata override, does the primary field win, or is it an error? | REQ-PEM-009: add conflict resolution rule: "If enrichment metadata contains keys that match FeatureSpec primary fields (`name`, `description`, `target_files`), the primary field value takes precedence and the metadata key is dropped with a warning." | Test: enrichment with conflicting `name`; verify primary field preserved and warning logged |
| R1-F5 | security | medium | REQ-PEM-018 prompt injection mitigation specifies XML-tag wrapping with escaping, but doesn't address nested context (e.g., `architectural_context` containing `requirements_text` excerpts that themselves contain escaped delimiters) | When multiple context sections are wrapped independently, a user could craft content in one section that, when combined with content in another section, reconstructs a valid closing delimiter. The defense-in-depth claim requires considering cross-section interactions, not just per-section escaping. The content-hash-based delimiter alternative mentioned in REQ-PEM-018 is stronger but optional — it should be the recommended approach. | REQ-PEM-018: strengthen recommendation: "Content-hash-based unique delimiters SHOULD be preferred over static XML tags for production pipeline deployments. Static XML tags with escaping are acceptable for standalone mode." | Security review: attempt cross-section delimiter reconstruction; verify hash-based delimiters prevent it |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-22 15:34:17 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | interfaces | high | REQ-PEM-004 protocol lacks error semantics — no distinction between "resolved successfully with empty data" and "resolution failed due to I/O or parsing error" | The three protocol methods return typed objects but have no error contract. A strategy encountering a corrupt seed file returns the same `SeedContext(onboarding={})` as one processing a seed that simply lacks onboarding. The workflow cannot make informed retry/abort decisions without distinguishing these cases. This gap was identified in prior round R1-F2 (2026-02-22) but was rejected as a "duplicate of R1-S2" — however, the state file concern is different from the strategy error contract concern. | REQ-PEM-004: add paragraph specifying error semantics for protocol methods | Test: strategy encounters I/O error, raises typed exception; workflow catches and exits code 1 |
| R1-F2 | completeness | high | REQ-PEM-009's "preserve all keys" conflicts with FeatureSpec's serialization contract when enrichment contains keys that shadow built-in FeatureSpec fields | REQ-PEM-009 says metadata "MUST preserve all keys present in the enriched seed" but doesn't address conflict with FeatureSpec's own `name`, `description`, `target_files` fields. If enrichment metadata contains `{"name": "different-name", ...}`, the round-trip behavior is ambiguous. This was raised as R1-F4 (2026-02-22) but the resolution (primary field wins, metadata key dropped) was never formally applied to the requirements text. | REQ-PEM-009: add conflict resolution rule for keys that shadow FeatureSpec primary fields | Test: enrichment with conflicting `name` key; verify primary field preserved and warning logged |
| R1-F3 | architecture | medium | REQ-PEM-008 `find_missing_parameters()` specification doesn't address false positives from common English words appearing as parameter values | The function uses "case-insensitive substring search" to detect parameter values in spec text. If a parameter resolves to a common word like "service", "data", or "model", the function will always find it regardless of whether the spec actually incorporates the parameter meaningfully. This reduces the utility of the spec completeness check to near-zero for generic parameter names. | REQ-PEM-008: add note: "Parameters whose resolved values are shorter than 4 characters or match common English stop words SHOULD be excluded from the completeness check to reduce false positives." | Test: parameter value "API" (3 chars) excluded from check. Test: parameter value "PostgreSQL 16.2" correctly detected. |
| R1-F4 | security | medium | REQ-PEM-018 file locking via `fcntl.flock` has known limitations — advisory locks don't prevent other processes from ignoring the lock, and NFS filesystems don't support flock reliably | The requirement mandates `fcntl.flock` for state file locking but this is advisory-only on Linux and broken on NFS. Pipeline deployments may use network filesystems. The requirement should either mandate mandatory locking (impractical) or acknowledge the limitation and specify the defense: check-and-warn for concurrent access rather than relying solely on flock. | REQ-PEM-018: soften to "MUST use file-level locking (e.g., `fcntl.flock` or `filelock` library) as a best-effort concurrency guard. On filesystems where advisory locking is unreliable (e.g., NFS), the system SHOULD log a warning at startup." | Test: concurrent access with flock; verify lock acquired. Test: NFS detection and warning (mock filesystem type check). |
| R1-F5 | completeness | medium | REQ-PEM-013 staleness detection doesn't specify behavior when `--force-regenerate` is used together with a matching checksum — should it still log the match before bypassing? | The requirement says `--force-regenerate` bypasses staleness check, but operators debugging cache behavior need to know whether the cache *would have* been valid. Without logging the comparison result before bypassing, operators cannot distinguish "cache was stale anyway" from "cache was valid but force-bypassed." | REQ-PEM-013: add: "When `--force-regenerate` is active, staleness comparison MUST still be performed and logged, followed by: 'Force regenerate active — bypassing cache despite {match\|mismatch}'" | Test: force-regenerate with matching checksum; verify log shows both the match and the bypass |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-23 03:10:54 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | interfaces | high | REQ-PEM-004 `ContextResolutionStrategy` protocol method `resolve_task_context()` returns `dict` but REQ-PEM-007 specifies structured sections with ordering semantics — the return type should be `OrderedDict` or a typed dataclass, not bare `dict` | Python `dict` preserves insertion order since 3.7, but this is an implementation detail, not a semantic contract. If context section ordering matters for LLM prompt quality (primacy/recency effects), the return type should enforce ordering explicitly. A bare `dict` return type communicates "order doesn't matter" to implementers. | REQ-PEM-004: change return type of `resolve_task_context()` to `OrderedDict[str, str]` or define a `TaskContext` dataclass with ordered fields | Implementation review: verify context sections maintain specified order through to prompt assembly |
| R1-F2 | completeness | high | REQ-PEM-003 ModeConfig table lists 8 behaviors but `ModeConfig` dataclass definition is never shown — implementers must infer fields from the behavior table, risking omissions | The acceptance criteria say "Configuration is a `ModeConfig` frozen dataclass derived from the `ExecutionMode` via `ModeConfig.for_mode()`" but unlike `SeedContext`, `ValidationConfig`, and `ContextFileEntry`, `ModeConfig` has no concrete field listing. This is the only core dataclass without a schema definition, creating an asymmetry that forces implementers to reverse-engineer fields from prose. | REQ-PEM-003: add explicit `ModeConfig` dataclass definition with fields corresponding to each behavior row | Implementation: verify `ModeConfig` fields match behavior table 1:1 |
| R1-F3 | architecture | medium | REQ-PEM-007 specifies `plan_context` as "feature-specific excerpt from plan document" but doesn't define the extraction algorithm — how is the relevant excerpt identified from a potentially large plan document? | The plan document could be thousands of lines. "Feature-specific excerpt" implies some selection/filtering but the mechanism is undefined. Is it keyword search? Section heading match? Full document inclusion? Without specification, implementations will diverge, some including the entire plan (wasting tokens) and others implementing brittle heuristics. | REQ-PEM-007: add: "Feature-specific plan excerpt MUST be extracted by searching for the feature name (case-insensitive) in plan document section headings. If no matching section is found, include the first 2000 characters of the plan document as fallback." | Test: plan document with multiple feature sections; verify correct section extracted for each feature |
| R1-F4 | validation | medium | REQ-PEM-008 `find_missing_parameters()` has no specification for what constitutes `resolved_parameters` — where does this dict come from and what keys/values does it contain? | The function signature shows `resolved_parameters: Dict[str, str]` but no requirement specifies how this dict is populated. Is it derived from `feature.metadata["_enrichment"]`? Constructed from `SeedContext` fields? The data flow from enrichment → resolved_parameters → find_missing_parameters is unspecified. | REQ-PEM-008: add: "The `resolved_parameters` dict is constructed from `feature.metadata['_enrichment']` by extracting all key-value pairs where the value is a non-empty string. If `_enrichment` is absent or empty, the spec completeness check is skipped." | Test: feature with _enrichment containing 3 parameters; verify all 3 are checked against spec text |
| R1-F5 | ops | medium | REQ-PEM-012 specifies `generation-manifest.json` written after "all features are processed" but doesn't address incremental manifest updates for long-running workflows | A 50-feature pipeline run could take hours. If the manifest is only written at the end, operators have no visibility into progress. An incremental manifest (updated after each feature) provides real-time monitoring and enables partial result recovery. The current requirement explicitly says "after all features are processed" which prevents this. | REQ-PEM-012: consider changing to "MUST be updated after each feature completes, with a final write after all features are processed" or add a separate progress file | Test: after feature N completes, manifest on disk reflects features 1..N with accurate status |
| R1-F6 | completeness | medium | REQ-PEM-017 property accessors delegate to SeedContext but no requirement specifies what happens when `workflow.seed_context` itself is None (e.g., before seed loading) | The property accessors assume `self.seed_context` exists, but during workflow construction before `load_seed_context()` is called, the attribute may not be set. Accessing `workflow.seed_onboarding` before initialization should have defined behavior (return empty dict, raise AttributeError, or lazy-initialize). | REQ-PEM-017: add: "Property accessors MUST return empty defaults (empty dict for dict fields, None for optional fields) if SeedContext has not yet been initialized. This supports code that checks seed properties during construction." | Test: access `workflow.seed_onboarding` before seed loading; verify returns `{}` not raises |

#### Review Round R1

- **Reviewer**: claude-4 (claude-opus-4-6)
- **Date**: 2026-02-23 17:19:49 UTC
- **Scope**: Architecture-focused review (Feature Requirements)

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | interfaces | high | REQ-PEM-004 error recovery in pipeline mode says `resolve_task_context` failure should "continue with degraded context" but doesn't define what degraded context looks like — is it the standalone strategy's output, an empty dict, or the partially-resolved dict up to the failure point? | The fallback behavior on per-feature context resolution failure directly affects generation quality. "Degraded context" could mean anything from "empty gen_context" (which would produce garbage) to "standalone-equivalent context" (which would produce lower-quality but functional output). Without specification, implementations will diverge. | REQ-PEM-004: add: "On `resolve_task_context` failure in pipeline mode, the workflow MUST mark the feature as `failed` (not attempt generation with degraded context), log the error, and continue to the next feature. Generation with incomplete context risks producing subtly wrong code that passes compilation but violates domain constraints." | Test: pipeline mode, resolve_task_context raises ContextResolutionError; verify feature is marked failed, no generation attempted, next feature proceeds |
| R1-F2 | validation | high | REQ-PEM-008 spec-to-draft validation is specified for pipeline mode only, with source file `lead_contractor_workflow.py`, but the actual integration point is ambiguous — does the Prime Contractor invoke this validation, or does the lead contractor workflow invoke it independently? | The "Source files" header says `lead_contractor_workflow.py` but the requirement is under the Prime Contractor Execution Modes document. If the lead contractor workflow is a separate component that the Prime Contractor delegates to, the validation should be documented as a callback or hook point. If the Prime Contractor owns this validation, the source file is wrong. | REQ-PEM-008: clarify integration architecture: "This validation is invoked by `PrimeContractorWorkflow` during its spec-to-draft transition, regardless of which contractor workflow implementation handles the actual spec/draft generation. The Prime Contractor passes the `resolved_parameters` to the validation function and injects findings into the drafter's context." | Implementation review: verify validation is called from Prime Contractor, not embedded in lead contractor |
| R1-F3 | security | medium | REQ-PEM-018 requires file permissions 0o600 for the manifest but doesn't specify permissions for `.prime_contractor_state.json`, which contains execution state including mode, checksum, and feature queue status | The state file contains operational data that could be exploited in a pipeline environment (e.g., modifying the state file to skip features or change the execution mode). If the manifest warrants 0o600 for cost data sensitivity, the state file warrants similar protection for integrity. | REQ-PEM-018: add: "`.prime_contractor_state.json` MUST be written with restrictive permissions (0o600) to prevent tampering with execution state in pipeline deployments." | Test: state file permissions after write are 0o600; test: state file with wrong permissions on read triggers warning |
| R1-F4 | completeness | medium | REQ-PEM-012 manifest `validator_results` shows simple string outcomes (`"pass"`, `"warn"`) per validator, but `ValidationResult` dataclass in REQ-PEM-004 includes `findings: List[str]` — the manifest schema doesn't capture findings, losing diagnostic information for downstream consumers | Stage 7 validators and developers debugging failed runs need access to the specific findings (e.g., "Missing import: `os.path`"), not just pass/fail status. The manifest is the only persistent record of validation results, so omitting findings creates an observability gap. | REQ-PEM-012: expand `validator_results` schema to include findings: `"import_dependency": {"outcome": "warn", "findings": ["Missing import: os.path in generated auth.py"]}` | Test: validation produces findings; verify manifest includes full findings array per validator |
| R1-F5 | ops | medium | REQ-PEM-013 staleness detection reads `generation-manifest.json` but doesn't specify the timing relative to feature queue initialization — if staleness is checked before features are loaded, the system can't do per-feature staleness; if checked after, it may have already loaded features unnecessarily | The requirement says "before reusing cached generation results" but doesn't anchor this to a specific point in the workflow lifecycle. Early staleness detection (before feature loading) enables fast skip of the entire workflow. Late detection (per-feature) enables partial reuse. The current requirement implies all-or-nothing via seed checksum, but the lifecycle position should be explicit. | REQ-PEM-013: add: "Staleness detection MUST be performed after seed loading and before feature generation begins. If the seed checksum matches the manifest, the workflow MUST skip all feature generation and exit with success, preserving the existing output files." | Test: matching checksum; verify zero features processed, existing output untouched, exit code 0 |

