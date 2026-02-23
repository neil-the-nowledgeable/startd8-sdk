# Prime Contractor Execution Modes — Implementation Plan

**Version:** 1.1.0
**Created:** 2026-02-20
**Updated:** 2026-02-23
**Implements:** `PRIME_EXECUTION_MODES_REQUIREMENTS.md` (REQ-PEM-000–018)
**Progress:** Phase 0, 0a, 1 complete — Phase 2–5 remaining

---

## Overview

This plan introduces a two-mode execution model for the Prime Contractor: **standalone** (current behavior, zero-change) and **pipeline** (full context exploitation from the Capability Delivery Pipeline). The design uses a Strategy pattern for context resolution, keeping the workflow code unified while varying behavior based on mode.

**Objectives:** Enable the Prime Contractor to exploit rich pipeline context (onboarding metadata, architectural context, design calibration) when available, while preserving exact standalone behavior as the zero-change default. Deliver this through a Strategy pattern that keeps a single workflow loop, mode-specific configuration, generation provenance, and post-generation validation hookpoints.

### Scope

**In scope:**
- `ExecutionMode` enum and `ModeConfig` dataclass
- `SeedContext` typed container (replaces ad-hoc instance attributes)
- `ContextResolutionStrategy` protocol with two implementations
- Feature queue metadata preservation
- Generation manifest + staleness detection (pipeline mode)
- Post-generation validation hookpoint (pipeline mode)
- Script and backward-compatibility changes

**Out of scope (deferred):**
- Implementing the actual Gate 3b validators (AR-143–AR-149 equivalents) — these are registered as validation hooks but the validator implementations are a separate body of work
- Plan ingestion upstream changes (REQ-PI-*) — the pipeline strategy consumes whatever the seed provides; it doesn't fix the seed
- Artisan convergence — making Prime's 4-stage flow (spec→draft→review→integrate) match artisan's 8-phase flow is not a goal

### Key Design Decisions

1. **Strategy pattern, not subclassing.** Two strategies (`StandaloneContextStrategy`, `PipelineContextStrategy`) are composed into the workflow at construction time. This avoids a `StandalonePrimeWorkflow` / `PipelinePrimeWorkflow` class split.

2. **SeedContext as single source of truth.** The five `workflow.seed_*` attributes are replaced by one `SeedContext` dataclass. Property accessors maintain backward compatibility.

3. **Mode-specific behavior via ModeConfig, not if/else.** Each behavior difference (logging, validation, provenance) is a boolean/config value in `ModeConfig`, looked up at the point of use. No `if mode == PIPELINE:` scattered through the codebase.

4. **Validation as hookpoints, not inline code.** Post-generation validation is a list of callable validators in `ValidationConfig`. Pipeline mode populates this list; standalone mode leaves it empty. The validation loop is mode-agnostic.

5. **Auto-detect default, explicit override.** The system infers mode from seed content but the user can force a mode. This prevents surprise behavior changes while enabling convenience.

---

## Functional Requirements

| ID | Requirement | Acceptance Criteria | Phase | Status |
|----|-------------|---------------------|-------|--------|
| FR-000 | Edit-first smoke test: trivial constant addition to existing `prime_contractor.py` | `_EDIT_FIRST_VALIDATED = True` added; diff ≤10 lines; all existing tests pass; no existing code altered | 0 | ✅ Complete |
| FR-000a | Full-depth OTel tracing verification via Phase 0 trace | All 13 TraceQL queries pass; span hierarchy matches spec; context correctness validated programmatically | 0a | ✅ Complete |
| FR-001 | ExecutionMode enum with STANDALONE/PIPELINE values | Enum defined, string-valued, importable from prime_contractor | 1 | ✅ Complete |
| FR-002 | ModeConfig frozen dataclass with per-mode defaults | `ModeConfig.for_mode()` returns correct config; `dataclasses.replace()` works | 1 | ✅ Complete |
| FR-003 | SeedContext typed container replaces ad-hoc attributes | Property accessors delegate to SeedContext; backward compatibility preserved | 1 | ✅ Complete |
| FR-004 | ContextResolutionStrategy protocol with two implementations | Both strategies are protocol-compliant; standalone produces equivalent output to current code | 1–2 | ✅ Protocol complete (Phase 1); implementations pending (Phase 2) |
| FR-005 | StandaloneContextStrategy extracts current context logic | `gen_context` dict structurally equivalent to current `_generate_code()` output | 2 | Pending |
| FR-006 | PipelineContextStrategy builds structured prompt sections | IMP-P1 through IMP-P5 sections present when seed data is enriched | 2 | Pending |
| FR-007 | Feature queue metadata preservation | `FeatureSpec.from_dict(spec.to_dict()) == spec` for all fields including metadata | 3 | Pending |
| FR-008 | Generation manifest with provenance (pipeline mode) | `generation-manifest.json` written with effective_config, per-feature model, source_checksum | 4 | Pending |
| FR-009 | Staleness detection via source_checksum comparison | Matching checksum reuses; mismatch regenerates; `--force-regenerate` bypasses | 4 | Pending |
| FR-010 | Post-generation validation hookpoint | Validators called when configured; results collected in feature metadata | 4 | Pending |
| FR-011 | CLI --mode flag with auto-detection default | `--mode standalone`, `--mode pipeline`, or auto-detect from seed signals | 5 | Pending |
| FR-012 | Security: path traversal prevention and prompt injection mitigation | All seed file paths validated against project root; user data wrapped in safe delimiters | 2 | Pending |

---

## Implementation Phases

### Phase 0: Edit-First Validation (Smoke Test) ✅ COMPLETE

**Status:** Complete
**Goal:** Prove the Artisan pipeline can surgically edit `prime_contractor.py` without rewriting it from scratch. This is a blocking prerequisite for all subsequent phases.

**Motivation:** Every prior attempt to implement this plan via the Artisan 8-phase pipeline has failed because the IMPLEMENT phase generates `prime_contractor.py` from scratch (~1800 lines of production code destroyed and replaced with a partial reimplementation). The PCA-5xx edit-first requirements (PCA-500–505) and PCA-6xx enforcement requirements (PCA-600–604) exist specifically to prevent this, but have not been validated against SDK-internal target files. This phase is the smallest possible validation: a single constant addition that proves the pipeline can read, preserve, and minimally modify the existing file.

**Files modified:**

| File | Change |
|------|--------|
| `src/startd8/contractors/prime_contractor.py` | Add `_EDIT_FIRST_VALIDATED = True` module-level constant |

**Steps:**

1. **Configure the Artisan task** with a single task targeting `prime_contractor.py`:
   - `target_files`: `["src/startd8/contractors/prime_contractor.py"]`
   - Task description: "Add module-level constant `_EDIT_FIRST_VALIDATED = True` with a comment referencing REQ-PEM-000. Do not modify any existing code."
   - The task MUST trigger edit-mode classification (not greenfield) because the target file exists

2. **Run the Artisan pipeline** (PLAN → SCAFFOLD → DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE)

3. **Validate the output:**
   - `git diff src/startd8/contractors/prime_contractor.py` shows ONLY the constant addition (±5 lines)
   - No existing imports, classes, methods, or docstrings are altered
   - File line count increases by ≤3 lines
   - All existing tests pass: `pytest tests/unit/contractors/ -v`

4. **If validation fails** (file rewritten from scratch):
   - Do NOT proceed to Phase 1
   - Diagnose the edit-first pipeline failure — check:
     - Did `_classify_edit_mode()` return `edit`? (PCA-600)
     - Did `_build_prompt()` include the `## Existing Files` section? (PCA-503)
     - Did `_build_prompt()` include the `## Edit-First Directive`? (PCA-503)
     - Did the LLM response contain the full existing file or just the delta?
   - Fix the edit-first pipeline and re-run Phase 0 until it passes

**Tests:**
- Existing tests pass unchanged
- `_EDIT_FIRST_VALIDATED` constant is importable from `startd8.contractors.prime_contractor`
- File diff is ≤10 lines

**Deliverables:**
- [x] `src/startd8/contractors/prime_contractor.py` — contains `_EDIT_FIRST_VALIDATED = True` with only the constant added

**Commit gate:** `git diff --stat` shows 1 file changed, ≤3 insertions. All existing tests pass.

**Exit criteria for proceeding to Phase 0a:** Phase 0 MUST pass before Phase 0a begins. If the Artisan pipeline cannot add a single constant without rewriting the file, the OTel trace will be meaningless (it would trace a destructive rewrite, not a valid edit).

---

### Phase 0a: Full-Depth OTel Tracing Verification ✅ COMPLETE

**Status:** Complete
**Goal:** Use the trace produced by Phase 0's Artisan run to programmatically verify that the full-depth OTel instrumentation (OT-1xx through OT-6xx, 25 implemented requirements) produces a correct, complete span hierarchy — and that the `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md` design principle is empirically validated via trace queries.

**Motivation:** Phase 0's hello world edit runs through all 8 Artisan phases (PLAN → SCAFFOLD → DESIGN → IMPLEMENT → INTEGRATE → TEST → REVIEW → FINALIZE) with a single task targeting one file. This is the simplest possible end-to-end pipeline execution, making it the ideal controlled environment for verifying that:

1. The full span hierarchy (§4 of `ARTISAN_OTEL_FULL_DEPTH_TRACING_REQUIREMENTS.md`) is emitted correctly — workflow → phase → gate → task → design/implement/test spans
2. Thread context propagation (OT-103, OT-104) correctly parents design and implement phase spans inside their task spans (no orphaned spans)
3. Gate boundary spans (OT-200, OT-201) contain `gate.passed` and `gate.propagation_status` attributes at every phase transition — proving that context correctness is *observable* at every boundary, not invisible
4. Contract events (`context.boundary.entry`, `context.boundary.exit`) are nested inside gate spans — proving that the contract system's signals are navigable in Tempo's waterfall view
5. Per-task span attributes (`task.id`, `task.status`, `task.cost`, `task.domain`) are set (OT-301–304)
6. LLM call span events (`llm.call.start`, `llm.call.complete`) are present in design and implement phases (OT-400)
7. No error spans exist for a successful run (OT-507)

This validates the core claim of `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md`: *"Silent degradation — no errors, reduced quality — is the hardest failure mode to detect. A contract system makes it structurally impossible for context to degrade without generating a signal."* If the trace shows gate spans with propagation status at every boundary, silent degradation at those boundaries is indeed impossible without a signal.

**Prerequisites:**
- Phase 0 has passed (REQ-PEM-000 satisfied)
- Grafana/Tempo stack is running (`docker-compose.loki-stack.yml`)
- Tempo datasource is configured (OT-600: `scripts/configure_tempo_datasource.sh`)

**Files created:**

| File | Purpose |
|------|---------|
| `scripts/verify_otel_trace.py` | Programmatic trace verification script |

**Steps:**

1. **Capture the trace ID** from Phase 0's Artisan run output. The workflow root span's trace ID is logged at workflow start and available via `workflow.{workflow_id}` span.

2. **Create `scripts/verify_otel_trace.py`** — a verification script that:
   - Accepts a trace ID as CLI argument
   - Retrieves the trace from Tempo via the HTTP API (`GET /api/traces/{traceId}`)
   - Parses the span hierarchy from the trace response
   - Executes 13 verification checks (V-1 through V-13) against the span data:

   | # | Check | Validates | Expected |
   |---|-------|-----------|----------|
   | V-1 | Root `workflow.*` span exists | AR-600 | 1 span |
   | V-2 | All 8 `phase.*` spans present (plan, scaffold, design, implement, integrate, test, review, finalize) | AR-601 | 8 spans |
   | V-3 | `gate.entry` spans with `gate.passed` and `gate.propagation_status` attributes | OT-200 | ≥8 spans |
   | V-4 | `gate.exit` spans with `gate.passed` attribute | OT-201 | ≥8 spans |
   | V-5 | `task.*` spans with `task.id` and `task.status` attributes | OT-301–304 | ≥4 spans |
   | V-6 | `design.iteration.*` spans exist | OT-404 | ≥1 span |
   | V-7 | `design.generate` span exists | OT-401 | ≥1 span |
   | V-8 | `implement.chunk.*` span with `chunk.status` attribute | OT-305 | 1 span |
   | V-9 | `test.generate` span exists | OT-405 | 1 span |
   | V-10 | `design.review.*` span exists | OT-402 | ≥1 span |
   | V-11 | No `status = error` spans (successful run) | OT-507 | 0 spans |
   | V-12 | `design.generate` spans have a `task.*` ancestor (not orphaned) | OT-103 | Parent chain intact |
   | V-13 | `implement.chunk.*` spans have a `task.*` ancestor (not orphaned) | OT-104 | Parent chain intact |

   - Reports pass/fail per check with diagnostic output
   - Produces summary: `"Context Correctness Verification: {passed}/13 checks passed"`
   - Exits with code 0 on all-pass, code 1 on any failure

3. **Run the verification script:**
   ```bash
   python3 scripts/verify_otel_trace.py --trace-id <trace_id_from_phase_0>
   ```

4. **Context Correctness by Construction validation** — the script's output provides empirical evidence for four claims from `CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md`:

   | Principle | Evidence | Checks |
   |-----------|----------|--------|
   | "Silent degradation is structurally impossible when contracts generate signals" | Gate spans with `gate.propagation_status` at every phase boundary | V-3, V-4 |
   | "Prescriptive over descriptive" | Gate attributes declare expected state (`gate.passed=true`) and record actual state — a mismatch is a prescriptive signal | V-3 |
   | "Observable contracts over invisible guarantees" | `context.boundary.*` events nested inside gate spans → navigable in Tempo waterfall | V-3, V-4 |
   | "Context flow through service boundaries shares the same structure as data flow through a type system" | Every phase transition has a boundary validator (gate span), analogous to a type checker at every function call site | V-2, V-3, V-4 |

5. **If verification fails:**
   - For missing spans: Check whether the corresponding OT-xxx requirement is truly implemented — the unit tests may pass with mocks but the real pipeline may not execute the instrumented code path
   - For orphaned spans (V-12, V-13 fail): Thread context propagation (OT-103, OT-104) is broken — `capture_context()` / `attach_context()` / `detach_context()` may not be called on the actual thread path
   - For missing gate attributes: `validate_phase_boundary()` may not be called, or `emit_boundary_result()` may not emit inside the gate span
   - Fix the instrumentation and re-run Phase 0 + Phase 0a

**Tests:**
- The verification script itself is tested: mock Tempo API responses for pass/fail scenarios
- The script is reusable for any Artisan run — not specific to Phase 0

**Deliverables:**
- [x] `scripts/verify_otel_trace.py` — Programmatic trace verification script (accepts trace ID, queries Tempo, validates 13 checks, reports pass/fail)
- [x] Phase 0 trace passes all 13 verification checks

**Commit gate:** `verify_otel_trace.py` exits with code 0 for the Phase 0 trace. All 13 checks pass.

**Exit criteria for proceeding to Phase 1:** Phase 0 AND Phase 0a MUST both pass before Phase 1 begins. Phase 0 proves the Artisan can edit files. Phase 0a proves the OTel instrumentation correctly traces the edit — establishing that context correctness by construction is not just a design principle but an empirically verified property of the pipeline. Together, they provide confidence that Phase 1's more complex changes (ExecutionMode enum, ModeConfig, SeedContext) will be both correctly applied AND fully observable.

---

### Phase 1: Foundation (Mode + SeedContext) ✅ COMPLETE

**Status:** Complete
**Goal:** Introduce the mode abstraction and typed context without changing any behavior.

**Files modified:**

| File | Change |
|------|--------|
| `src/startd8/contractors/prime_contractor.py` | `ExecutionMode` enum, `ModeConfig` dataclass, `SeedContext` dataclass, property accessors |
| `src/startd8/contractors/protocols.py` | `ContextResolutionStrategy` protocol definition |

**Steps:**

1. **Define `ExecutionMode` enum** in `prime_contractor.py`:
   ```python
   class ExecutionMode(str, Enum):
       STANDALONE = "standalone"
       PIPELINE = "pipeline"
   ```

2. **Define `ModeConfig` dataclass** (frozen — CLI overrides use `dataclasses.replace()`):
   ```python
   @dataclass(frozen=True)
   class ModeConfig:
       log_missing_context: bool      # Warn on missing onboarding/arch fields
       run_validators: bool           # Post-generation Gate 3b validators
       emit_provenance: bool          # Write generation-manifest.json
       detect_staleness: bool         # Check source_checksum before reuse
       log_context_injection: bool    # Log injected vs missing fields
       emit_otel_spans: bool          # Emit OTel spans for pipeline observability
       strict_validation: bool = False # Non-zero exit on validation failures

       @classmethod
       def for_mode(cls, mode: ExecutionMode) -> "ModeConfig": ...
   ```
   Note: `structured_context` removed — the choice of `ContextResolutionStrategy` IS the policy for context structure (standalone strategy = flat, pipeline strategy = structured). No dual-control needed.

   **CLI overrides:** Since `ModeConfig` is frozen, CLI flag overrides produce a new instance:
   ```python
   config = ModeConfig.for_mode(mode)
   if args.validate:
       config = dataclasses.replace(config, run_validators=True)
   if args.strict_validation:
       config = dataclasses.replace(config, strict_validation=True)
   ```

3. **Define `SeedContext` dataclass** (mutable during setup, treated as immutable after execution begins):
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
   `SeedContext.execution_mode` is for serialization/round-trip; `workflow.mode` is the runtime authority. These are always synchronized.

4. **Add `ContextResolutionStrategy` protocol and `ValidationConfig`** to `protocols.py`:
   ```python
   @dataclass
   class ValidationResult:
       validator_name: str         # Canonical: "import_dependency", "protocol_fidelity", etc.
       severity: str               # "pass" | "warn" | "fail"
       findings: List[str]

   @dataclass
   class ValidationConfig:
       validators: List[Callable[[List[Path]], ValidationResult]]
       fail_on_warning: bool = False
       skip_validators: List[str] = field(default_factory=list)

   @runtime_checkable
   class ContextResolutionStrategy(Protocol):
       def resolve_seed_context(self, seed_data: dict) -> SeedContext: ...
       def resolve_task_context(self, feature: FeatureSpec, seed_ctx: SeedContext) -> dict: ...
       def resolve_validation_config(self, feature: FeatureSpec) -> ValidationConfig: ...
   ```

   **Error handling contract for strategy methods:**
   - `resolve_seed_context()`: Schema validation errors raise `ValueError` with descriptive message; file read errors are caught and logged (missing files = warning, not fatal)
   - `resolve_task_context()`: Template rendering failures raise `RuntimeError`; workflow aborts the current feature with error status
   - `resolve_validation_config()`: Returns empty `ValidationConfig` on any error (validators are best-effort, not blocking)

5. **Replace instance attributes** on `PrimeContractorWorkflow`:
   - Add `self.seed_context: SeedContext` initialized to defaults
   - Add `self.mode: ExecutionMode` and `self.mode_config: ModeConfig`
   - Add property accessors for `seed_onboarding`, `seed_architectural_context`, etc. that delegate to `self.seed_context`
   - Property setters populate `SeedContext` fields (for `run_prime_workflow.py` compatibility) — valid during initialization phase only
   - Persist `execution_mode` in `.prime_contractor_state.json` for resume consistency

6. **Add auto-detection** in a `_detect_mode()` classmethod.

**Tests:**
- `ExecutionMode` values exist and are strings
- `ModeConfig.for_mode(STANDALONE)` has validators=False, provenance=False, emit_otel_spans=False
- `ModeConfig.for_mode(PIPELINE)` has validators=True, provenance=True, emit_otel_spans=True
- `dataclasses.replace()` on frozen ModeConfig produces new instance (no FrozenInstanceError)
- `SeedContext` defaults match current empty-dict behavior
- `SeedContext.execution_mode` and `workflow.mode` stay synchronized
- Property accessors read/write through `SeedContext` during initialization
- Auto-detect returns `STANDALONE` for empty seed, `PIPELINE` for enriched seed
- Auto-detect log includes actual signal key names
- Forced `--mode pipeline` with minimal seed: proceeds with warnings
- Mode persists in `.prime_contractor_state.json` and is consistent after resume
- `ValidationConfig` and `ValidationResult` are importable with expected fields

**Deliverables:**
- [x] `src/startd8/contractors/prime_contractor.py` — ExecutionMode enum, ModeConfig dataclass, SeedContext dataclass, property accessors
- [x] `src/startd8/contractors/protocols.py` — ContextResolutionStrategy protocol, ValidationConfig, ValidationResult
- [x] `tests/unit/contractors/test_execution_modes.py` — Mode enum, ModeConfig, auto-detection tests

**Commit gate:** All existing tests pass. No behavior change.

---

### Phase 2: Context Resolution Strategies ← NEXT

**Status:** Pending (FR-004 protocol definition done in Phase 1; strategy implementations pending)
**Goal:** Extract `_generate_code()`'s context-building logic into two strategy implementations.

**Files modified/created:**

| File | Change |
|------|--------|
| `src/startd8/contractors/context_resolution.py` | NEW — `StandaloneContextStrategy`, `PipelineContextStrategy` |
| `src/startd8/contractors/prime_contractor.py` | `_generate_code()` delegates to `self.context_strategy` |

**Steps:**

1. **Create `context_resolution.py`** with two classes.

2. **`StandaloneContextStrategy`** — Extract current `_generate_code()` context-building logic (lines 484–560 of `prime_contractor.py`) into `resolve_task_context()`. This is a pure refactor: same logic, same output, different home.

   Key: `resolve_task_context()` must produce a `gen_context` dict structurally equivalent to the current code for the same inputs (identical keys and values, order-independent comparison via `dict.__eq__`).

3. **`PipelineContextStrategy`** — Same interface, richer implementation:
   - `resolve_seed_context()`: checks for key *presence* in raw seed before applying defaults; logs missing keys as warnings per REQ-PC-014; validates `source_checksum` presence (warning if absent); validates all file paths against project root (REQ-PEM-018)
   - `resolve_task_context()`: builds structured sections (IMP-P1), requirements passthrough (IMP-P2), critical parameters (IMP-P3), protocol guidance (IMP-P4), constraint categorization (IMP-P5). **Empty field rule:** sections with empty source data (`{}` or `[]`) are omitted from `gen_context`. User-controlled data wrapped in safe delimiters (`<context type="...">...</context>`) for prompt injection mitigation.
   - `resolve_validation_config()`: returns `ValidationConfig` with validators from a pre-approved registry (code-defined, never from seed). Maps `feature.metadata` enrichment keys to validator names via a `VALIDATOR_REGISTRY` dict:
     ```python
     VALIDATOR_REGISTRY = {
         "import_dependency": ImportDependencyValidator,
         "protocol_fidelity": ProtocolFidelityValidator,
         "placeholder_detection": PlaceholderDetectionValidator,
         "dockerfile_coherence": DockerfileCoherenceValidator,
     }
     ```
     Validators that lack required data are skipped with a warning.

   **Architectural context transformation** (JSON → Markdown):
   - Top-level keys → `### {key}` headers
   - Arrays → bullet lists
   - Nested objects → indented sub-sections
   - Extract to `context_formatters.py` with per-section formatter functions (e.g., `format_architectural_context(data) -> str`) for testability and reuse.

   **Forced pipeline mode with inadequate seed:** When `--mode pipeline` is explicit but seed lacks signals, proceed with degraded quality (warnings logged, not fail fast). This enables iterative pipeline development.

4. **Wire into `PrimeContractorWorkflow`:**
   - Constructor accepts optional `context_strategy: ContextResolutionStrategy`
   - Default: `StandaloneContextStrategy()` when mode=STANDALONE, `PipelineContextStrategy()` when mode=PIPELINE
   - `_generate_code()` calls `self.context_strategy.resolve_task_context()` instead of inline dict building

5. **Pipeline context structure** (the gen_context dict in pipeline mode):
   ```python
   {
       # General (always present)
       "feature_name": "...",
       "target_file": "...",
       "task_description": "...",

       # Pipeline-enriched sections
       "architectural_context": "## Project Architecture\n...",   # Formatted, not raw JSON
       "requirements_context": "## Requirements\n...",            # From requirements_text
       "domain_constraints": "## Constraints\n### Binding\n...",  # Categorized
       "critical_parameters": "## Critical Parameters\n...",      # Elevated
       "protocol_guidance": "## Protocol Guidance\n...",          # From service_metadata
       "plan_context": "## Plan Context\n...",                    # Feature-specific excerpt
       "semantic_conventions": "## Conventions\n...",             # Bullet list
       "scope_boundary": "Generate only what is specified...",    # Instruction

       # Flow-through (same as standalone)
       "implement_max_output_tokens": ...,
       "prior_error_feedback": ...,
       "output_constraint": ...,
       "service_metadata": {...},
   }
   ```

**Tests** (use dependency injection for test isolation — constructor injection for context_files, seed data):
- Standalone strategy produces structurally equivalent gen_context to current code (dict equality, not byte comparison)
- Pipeline strategy includes structured sections when data is present
- Pipeline strategy omits sections when source data is empty (`{}`, `[]`)
- Pipeline strategy logs missing fields (key absent from raw seed)
- Pipeline strategy wraps user-controlled data in safe delimiters
- Pipeline strategy rejects path traversal in context_files
- Both strategies are protocol-compliant (`isinstance(strategy, ContextResolutionStrategy)`)
- Strategy method failures produce defined behavior (ValueError/RuntimeError/empty ValidationConfig)

**Deliverables:**
- [ ] `src/startd8/contractors/context_resolution.py` — StandaloneContextStrategy, PipelineContextStrategy
- [ ] `src/startd8/contractors/context_formatters.py` — Per-section formatter functions (JSON→Markdown)
- [ ] `src/startd8/workflows/builtin/lead_contractor_workflow.py` — REQ-PEM-008 spec-to-draft validation hookpoint
- [ ] `tests/unit/contractors/test_context_resolution.py` — Strategy tests (standalone + pipeline), security tests

**Commit gate:** All existing tests pass. Standalone behavior unchanged. Pipeline strategy has new tests.

**Module import direction** (to prevent circular imports):
- `protocols.py` → defines `ContextResolutionStrategy`, `ValidationConfig`, `ValidationResult` (no imports from prime_contractor)
- `context_resolution.py` → imports from `protocols.py`, `queue.py` (no imports from prime_contractor)
- `prime_contractor.py` → imports from `protocols.py`, `context_resolution.py`
- If shared types are needed by multiple modules, extract to `types.py` to break cycles

---

### Phase 3: Feature Queue Hardening

**Goal:** Ensure enrichment metadata survives the queue boundary in both modes.

**Files modified:**

| File | Change |
|------|--------|
| `src/startd8/contractors/queue.py` | `FeatureSpec` metadata preservation, `add_feature()` convenience method, `to_dict()`/`from_dict()` round-trip |

**Steps:**

1. **Audit `add_features_from_seed()`** — Verify all enrichment fields from the seed task are captured in `FeatureSpec.metadata`. Add any missing fields (cross-reference with `SeedTask` fields).

2. **Add `add_feature()` convenience method** for standalone usage without a seed file. When no seed is provided, `SeedContext` is initialized with all defaults (empty dicts, None, `STANDALONE` mode). Workflow-level config (output_dir, model) comes from constructor params.

3. **Harden `to_dict()` / `from_dict()`** — Ensure `metadata` round-trips completely.

**Tests:**
- `FeatureSpec.from_dict(spec.to_dict()) == spec` for all fields
- `add_feature()` creates valid FeatureSpec with empty metadata
- Enrichment data from seed survives queue serialization

**Deliverables:**
- [ ] `src/startd8/contractors/queue.py` — Metadata preservation, add_feature() convenience method, to_dict()/from_dict() round-trip

**Commit gate:** All existing tests pass. REQ-PC-005, REQ-PC-006 satisfied.

---

### Phase 4: Output Contract (Pipeline Mode)

**Goal:** Pipeline mode produces generation manifest and structured cost report.

**Files modified:**

| File | Change |
|------|--------|
| `src/startd8/contractors/prime_contractor.py` | Manifest writing, staleness detection, validation result collection |

**Steps:**

1. **Generation manifest** — After all features are processed (in `run()` or `_finalize()`), if `mode_config.emit_provenance`, write `generation-manifest.json` to output directory. The manifest includes:
   - `effective_config`: final `ModeConfig` state after CLI overrides (for reproducibility)
   - Per-feature `model` field: captured from `CodeGenerator.generate()` return value (generator MUST expose model spec used)
   - `source_checksum`: SHA-256 of canonical seed JSON
   - Schema version `"1.0.0"` with forward-compatibility rule: consumers encountering unknown versions log warning and skip staleness

2. **Staleness detection** — Before generating a feature, if `mode_config.detect_staleness`:
   - Read existing `generation-manifest.json` (if unparsable/corrupt, log warning and treat as absent)
   - Compare `source_checksum` from manifest against current seed's checksum (SHA-256 over canonical JSON of seed, sorted keys). `workflow_id` is NOT used in comparison — it's for provenance tracking only.
   - **Match:** reuse cached results (log `"Staleness check: current"`)
   - **Mismatch:** regenerate (log `"Staleness check: stale (checksum mismatch)"`)
   - **No manifest/no checksum:** regenerate (log `"Staleness check: no provenance"`)
   - `--force-regenerate` bypasses this check
   - Manifest written with 0o600 permissions (cost data is sensitive)
   - I/O errors during manifest write are logged but do not fail the workflow

3. **Post-generation validation hookpoint** — After `CodeGenerator.generate()` returns, if `mode_config.run_validators`:
   - Call `self.context_strategy.resolve_validation_config(feature)` to get validator list
   - Run each validator against generated files
   - Collect results in `feature_result.metadata["validation"]`
   - Log results with severity

   Note: The actual validator implementations (AR-143–AR-149 equivalents) are a separate task. This phase only wires the hookpoint and result collection.

4. **Structured cost report** — In pipeline mode, `prime-result.json` includes per-feature cost breakdown with model info.

**Tests** (use deterministic test fixtures with pre-computed checksums for staleness tests):
- Manifest written in pipeline mode, not in standalone
- Manifest includes `effective_config` and per-feature `model` field
- Manifest written with 0o600 permissions
- Manifest I/O error logged but workflow continues
- Staleness detection: matching checksum reuses, mismatch regenerates, no manifest regenerates
- Staleness detection: corrupt/unparsable manifest handled gracefully
- Staleness detection: different `workflow_id` with same `source_checksum` still reuses
- `--force-regenerate` bypasses staleness
- Validation results collected when validators configured
- Empty validator list produces no validation output
- `--strict-validation` causes non-zero exit on validation failures

**Deliverables:**
- [ ] `src/startd8/contractors/prime_contractor.py` — Generation manifest writing, staleness detection, validation result collection
- [ ] `tests/unit/contractors/test_generation_manifest.py` — Manifest, staleness, validation hookpoint tests

**Commit gate:** All existing tests pass. Pipeline-mode output enhanced.

---

### Phase 5: Script + CLI Integration

**Goal:** Runner script supports `--mode` flag and behavioral overrides.

**Files modified:**

| File | Change |
|------|--------|
| `scripts/run_prime_workflow.py` | `--mode`, `--validate`, `--no-validate`, `--force-regenerate` flags |

**Steps:**

1. **Add argparse flags:**
   - `--mode {standalone,pipeline}` — optional, default auto-detect. Invalid values produce user-friendly error listing valid modes.
   - `--validate` / `--no-validate` — override `mode_config.run_validators`
   - `--strict-validation` — non-zero exit on validation failures (REQ-PEM-014)
   - `--force-regenerate` — bypass staleness detection + cache
   - **Conflict detection:** `--validate` + `--no-validate` → CLI error. `--strict-validation` + `--no-validate` → CLI error.

2. **Wire mode into workflow construction:**
   - Pass `mode` to `PrimeContractorWorkflow` constructor
   - Let auto-detection run if no explicit mode
   - Apply flag overrides to `ModeConfig` via `dataclasses.replace()` (frozen dataclass — no mutation)
   - **Flag precedence:** CLI flag > ModeConfig profile > ExecutionMode default

3. **Remove ad-hoc context stashing** — Replace:
   ```python
   workflow.seed_onboarding = seed_data.get("onboarding") or {}
   workflow.seed_architectural_context = seed_data.get("architectural_context") or {}
   ...
   ```
   With:
   ```python
   workflow.load_seed_context(seed_data)  # Populates SeedContext via strategy
   ```

**Tests** (parameterized test suite for CLI flag × ModeConfig combinations):
- Script parses `--mode standalone` and `--mode pipeline`
- Script without `--mode` auto-detects from seed
- Invalid `--mode` value produces user-friendly error
- `--validate` forces validation in standalone mode
- `--no-validate` disables validation in pipeline mode
- `--strict-validation` causes non-zero exit on failures
- `--validate` + `--no-validate` raises CLI error
- `--strict-validation` + `--no-validate` raises CLI error
- Forced `--mode pipeline` with minimal seed proceeds with warnings (not failure)

**Deliverables:**
- [ ] `scripts/run_prime_workflow.py` — --mode, --validate, --no-validate, --strict-validation, --force-regenerate flags

**Commit gate:** All existing tests pass. Script backward-compatible.

---

## File Inventory

### New Files

| File | Purpose | Phase |
|------|---------|-------|
| `src/startd8/contractors/context_resolution.py` | `StandaloneContextStrategy` + `PipelineContextStrategy` | 2 |
| `src/startd8/contractors/context_formatters.py` | Per-section formatter functions (JSON→Markdown) | 2 |
| `tests/unit/contractors/test_execution_modes.py` | Mode enum, ModeConfig, auto-detection, CLI flag combinations (parameterized) | 1, 5 |
| `tests/unit/contractors/test_context_resolution.py` | Strategy tests (standalone + pipeline), security tests | 2 |
| `tests/unit/contractors/test_generation_manifest.py` | Manifest, staleness, validation hookpoint tests | 4 |

### Modified Files

| File | Changes | Phase |
|------|---------|-------|
| `src/startd8/contractors/prime_contractor.py` | ExecutionMode, ModeConfig, SeedContext, strategy wiring, manifest, staleness | 1, 2, 4 |
| `src/startd8/contractors/protocols.py` | ContextResolutionStrategy protocol, ValidationConfig, ValidationResult | 1 |
| `src/startd8/contractors/queue.py` | Metadata preservation, add_feature(), round-trip | 3 |
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | REQ-PEM-008 spec-to-draft validation hookpoint | 2 |
| `scripts/run_prime_workflow.py` | --mode, --validate, --strict-validation, --force-regenerate flags | 5 |

### Additionally Modified Files

| File | Changes | Phase |
|------|---------|-------|
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | REQ-PEM-008: spec-to-draft validation hookpoint (pipeline mode only) | 2 |
| `src/startd8/contractors/context_formatters.py` | NEW — Per-section formatter functions for architectural context, etc. | 2 |

**REQ-PEM-008 implementation** (in `lead_contractor_workflow.py`):
- After `_create_spec()` and before `_create_draft()`, if `mode_config.run_validators`:
  - Call `find_missing_parameters(spec_text, feature.metadata.get("resolved_parameters", {}))` from `prompt_utils.py`
  - If missing parameters found, inject `## Spec Completeness Warning` section into drafter feedback
  - In standalone mode (no `mode_config` or `run_validators=False`): skip this check entirely
- This is a text-only check (no LLM call) and adds minimal overhead

### Untouched Files

These files are NOT modified — the abstraction layer sits above them:

- `src/startd8/contractors/generators/lead_contractor.py` — Receives gen_context dict; doesn't know about modes
- `src/startd8/contractors/adapters/` — Instrumentor/MergeStrategy adapters are orthogonal to execution mode
- `src/startd8/contractors/artisan_phases/` — Artisan route is unaffected

---

## Dependency Graph

```
Phase 1: Foundation
  ├── ExecutionMode enum
  ├── ModeConfig dataclass
  ├── SeedContext dataclass
  ├── ContextResolutionStrategy protocol
  └── Property accessors (backward compat)
         │
Phase 2: Context Resolution Strategies
  ├── StandaloneContextStrategy (refactor of existing code)
  ├── PipelineContextStrategy (new, implements IMP-P1..P5)
  ├── context_formatters.py (JSON→Markdown per-section)
  ├── REQ-PEM-008 spec-to-draft hookpoint in lead_contractor_workflow.py
  └── Wire into _generate_code()
         │
Phase 3: Feature Queue Hardening ←── (independent of Phase 2, can parallel)
  ├── Metadata preservation audit
  ├── add_feature() convenience
  └── to_dict()/from_dict() round-trip
         │
Phase 4: Output Contract
  ├── Generation manifest (requires Phase 1 mode_config)
  ├── Staleness detection (requires Phase 1 SeedContext.source_checksum)
  └── Validation hookpoint (requires Phase 2 resolve_validation_config)
         │
Phase 5: Script Integration
  ├── --mode flag
  ├── Behavioral overrides
  └── Replaces ad-hoc context stashing (requires Phase 1 SeedContext)
```

Phases 1→2→4→5 are sequential. Phase 3 can run in parallel with Phase 2.

---

## Validation

Each phase has its own commit gate (all existing tests must pass before proceeding). Beyond per-phase checks, the following document-level validation criteria apply:

1. **Standalone equivalence** — After all phases, standalone mode with identical inputs must produce structurally equivalent output to the pre-implementation baseline (dict equality on gen_context, byte-for-byte output file comparison)
2. **Pipeline mode activation** — Pipeline mode with an enriched seed must activate IMP-P1 through IMP-P5 prompt sections; verify via test assertions on gen_context keys
3. **Mode observability** — Logs must clearly state active mode and list present/missing context fields; verified via captured log assertions
4. **Security hardening** — Path traversal and prompt injection tests pass (adversarial inputs in test fixtures); verified via `test_context_resolution.py` security test class
5. **Round-trip consistency** — `FeatureSpec`, `SeedContext`, and `ModeConfig` survive serialization round-trips; verified via parametric equality assertions
6. **End-to-end pipeline run** — A full pipeline run (stages 0–7) with the test bed produces generated code without errors; verified manually against `cap-dev-pipe-test`

---

## Self-Validating Gap Verification

Each identified context propagation boundary maps to a runtime integration check (SV-*) that must fail before the fix and pass after. These serve as the plan's own test harness — if a gap fix is incomplete, the corresponding SV check catches it during execution.

| ID | Propagation Boundary | Gap Description | Runtime Check | Fails Before | Passes After |
|----|----------------------|-----------------|---------------|--------------|--------------|
| SV-1 | SeedContext → ContextResolutionStrategy | SeedContext fields might not reach strategy `resolve_task_context()` | Assert `gen_context` contains all non-None SeedContext fields when pipeline strategy is active | Strategy receives empty dict for enriched seed fields | Strategy receives all populated SeedContext fields |
| SV-2 | ContextResolutionStrategy → gen_context dict | Pipeline strategy IMP-P1–P5 sections might be silently dropped | Assert `gen_context` keys include `imp_p1_*` through `imp_p5_*` when `ModeConfig.emit_provenance=True` | `gen_context` missing IMP-P* keys in pipeline mode | All 5 IMP-P sections present in gen_context |
| SV-3 | Feature queue → FeatureSpec metadata | Metadata fields added in Phase 3 might not survive `to_dict()`/`from_dict()` round-trip | Assert `FeatureSpec.from_dict(spec.to_dict()) == spec` including pipeline-injected metadata | Pipeline metadata fields silently dropped during serialization | Full round-trip equality including `source_checksum`, `mode`, `validator_results` |
| SV-4 | Generation results → manifest | Per-feature cost/model data might not propagate to `generation-manifest.json` | Assert manifest entry for each feature contains non-null `model` and `cost_usd` fields | Manifest entries missing cost/model provenance | Every feature entry has complete provenance |
| SV-5 | ModeConfig → phase behavior | ModeConfig boolean flags might not reach their point of use (e.g., `run_validators` checked but `ValidationConfig` empty) | Assert that `ModeConfig.run_validators=True` with a registered mock validator produces non-empty `validator_results` | Validators configured but never called | Mock validator called, results in feature metadata |
| SV-6 | CLI --mode flag → workflow.mode | CLI argument might not propagate through to `workflow.mode` and `SeedContext.execution_mode` | Assert `workflow.mode == workflow.seed_context.execution_mode` after CLI-driven initialization | `workflow.mode` and `seed_context.execution_mode` diverge after CLI override | Both synchronized after any initialization path |
| SV-7 | Checkpoint resume → mode consistency | Saved mode in `.prime_contractor_state.json` might conflict with CLI flag on resume | Assert resumed workflow preserves original mode unless explicitly overridden | Resume silently changes mode or ignores saved state | Resume restores saved mode; explicit `--mode` override logged as warning |

**Test location:** `tests/unit/contractors/test_context_propagation_sv.py`

**Execution:** These checks run as standard pytest unit tests. Each SV-* test is parametrized with `(standalone, pipeline)` mode pairs to verify both paths.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| **Standalone behavior regression** | Phase 1 commit gate: all existing tests must pass before proceeding. `StandaloneContextStrategy` is a pure extraction of existing code. |
| **Property accessor edge cases** | Test both read and write paths during initialization phase. Setters update `SeedContext` for scripts that assign attributes directly. |
| **Pipeline strategy untested in production** | Pipeline strategy is only activated by explicit flag or auto-detection from enriched seeds. Standalone is the default — users must opt in. |
| **Validator implementations not ready** | Phase 4 wires hookpoints only. Empty validator list produces no validation output. Actual validators (AR-143 equiv) are a follow-on task. |
| **Plan ingestion upstream gaps** | Pipeline strategy logs missing fields as warnings. Every field is optional with graceful degradation. Quality improves as upstream catches up. |
| **Security: path traversal from seed** | All file paths validated against project root using `sanitize_path()`. Tests with adversarial paths (REQ-PEM-018). |
| **Security: prompt injection** | User-controlled seed data wrapped in safe XML delimiters before prompt injection. Defense-in-depth. |
| **Circular imports** | Explicit module import direction rules. Shared types in `protocols.py` (or dedicated `types.py` if needed). |
| **Frozen ModeConfig mutation** | CLI overrides use `dataclasses.replace()` — no runtime `FrozenInstanceError` risk. |

---

## Success Criteria

1. **All existing tests pass** after each phase (non-negotiable)
2. **Standalone mode produces structurally equivalent output** to current behavior for identical inputs
3. **Pipeline mode activates** all IMP-P1 through IMP-P5 prompt improvements when enriched seed data is present
4. **Pipeline mode emits** generation manifest with provenance for staleness detection
5. **Mode is observable** — logs clearly state which mode is active and which context fields are present/missing
6. **No code duplication** — standalone and pipeline strategies share the same workflow execution loop; only context resolution differs
7. **Security hardened** — path traversal protection, prompt injection mitigation, validator registry lockdown (REQ-PEM-018)
8. **REQ-PEM-008 spec-to-draft validation** operational in pipeline mode via `lead_contractor_workflow.py`

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [`PRIME_EXECUTION_MODES_REQUIREMENTS.md`](PRIME_EXECUTION_MODES_REQUIREMENTS.md) | Requirements this plan implements |
| [`PRIME_CONTRACTOR_REQUIREMENTS.md`](PRIME_CONTRACTOR_REQUIREMENTS.md) | Functional requirements enabled by this work |
| [`PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md`](PRIME_PROMPT_EXTERNALIZATION_REQUIREMENTS.md) | Prompt improvements activated by pipeline mode |
| [`../artisan/ARTISAN_REQUIREMENTS.md`](../artisan/ARTISAN_REQUIREMENTS.md) | Artisan route patterns to follow |

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **architecture**: 11 suggestions applied (R7-S1, R7-S5, R7-S6, R7-S9, R8-S4, R3-S2, R5-S1, R5-S2, R5-S7, R6-S1, R8-S5)
- **clarity**: 5 suggestions applied (R3-S8, R2-S15, R5-S4, R6-S8, R8-S6)
- **completeness**: 8 suggestions applied (R2-S10, R7-S2, R7-S7, R8-S6, R2-S11, R2-S12, R2-S14, R8-S4)
- **maintainability**: 4 suggestions applied (R3-S7, R2-S13, R5-S9, R7-S6)
- **scalability**: 4 suggestions applied (R3-S3, R3-S4, R3-S9, R4-S9)
- **security**: 9 suggestions applied (R7-S3, R7-S10, R8-S5, R3-S1, R3-S10, R3-S5, R4-S1, R4-S2, R4-S7)
- **testability**: 6 suggestions applied (R7-S4, R7-S8, R3-S6, R5-S3, R6-S3, R6-S5)

### Areas Needing Further Review

All areas have reached the substantially addressed threshold.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R3-S1 | Define explicit error handling when pipeline mode is forced but seed lacks critical context fields | claude-4 (claude-opus-4-5) | Critical gap: the plan contradicts itself by logging missing fields as warnings while calling them 'critical'. Must specify fail-fast vs degrade behavior for forced pipeline mode with incomplete seeds. | 2026-02-20 20:00:05 UTC |
| R3-S2 | Add explicit ValidationConfig dataclass definition alongside the protocol in Phase 1 | claude-4 (claude-opus-4-5) | The protocol references ValidationConfig as a return type but it's never defined, which will cause implementation failure in Phase 4. | 2026-02-20 20:00:05 UTC |
| R3-S3 | Define initialization path for seedless add_feature() workflow execution | claude-4 (claude-opus-4-5) | Phase 3 adds add_feature() convenience method but doesn't specify how SeedContext is initialized without a seed file, creating an implementation gap. | 2026-02-20 20:00:05 UTC |
| R3-S4 | Specify the exact transformation for formatted architectural context in pipeline strategy | claude-4 (claude-opus-4-5) | Phase 2 shows formatted output but lacks the JSON-to-Markdown transformation algorithm, leaving implementation ambiguous. | 2026-02-20 20:00:05 UTC |
| R3-S6 | Replace byte-identical output claim with verifiable structural equivalence criteria | claude-4 (claude-opus-4-5) | LLM non-determinism makes byte-identical claims unverifiable; structural equivalence (keys, types, non-empty values) is testable. | 2026-02-20 20:00:05 UTC |
| R3-S7 | Define CLI flag precedence rules and conflict resolution | claude-4 (claude-opus-4-5) | Without explicit precedence rules, passing conflicting flags like --validate --no-validate produces undefined behavior. | 2026-02-20 20:00:05 UTC |
| R3-S8 | Add explicit mode state serialization for workflow resume scenarios | claude-4 (claude-opus-4-5) | Mode must persist across resume/retry but the state file serialization isn't updated to include execution mode. | 2026-02-20 20:00:05 UTC |
| R3-S9 | Specify source_checksum requirement tier for pipeline mode | claude-4 (claude-opus-4-5) | Field is Optional[str] but pipeline mode validates it; must clarify if missing checksum is warning or error in pipeline mode. | 2026-02-20 20:00:05 UTC |
| R3-S10 | Add error handling tests for context_files with missing or unreadable files | claude-4 (claude-opus-4-5) | Plan includes context_files but specifies no error handling for non-existent files, which is a common failure mode. | 2026-02-20 20:00:05 UTC |
| R2-S11 | Define data flow for populating model field in generation-manifest.json | gemini-2.5 (gemini-2.5-pro) | Manifest schema requires LLM model name but neither requirements nor plan specify how to capture and pass this information. | 2026-02-20 20:00:05 UTC |
| R2-S12 | Add --strict-validation flag omitted from Phase 5 | gemini-2.5 (gemini-2.5-pro) | REQ-PEM-014 requires this flag to control exit code behavior; omitting it means required functionality won't be implemented. | 2026-02-20 20:00:05 UTC |
| R2-S13 | Specify immutable update pattern for applying CLI overrides to frozen ModeConfig | gemini-2.5 (gemini-2.5-pro) | Plan defines ModeConfig with frozen=True but suggests mutating it, which will cause runtime FrozenInstanceError. | 2026-02-20 20:00:05 UTC |
| R2-S14 | Specify mechanism for mapping feature.metadata to validators in PipelineContextStrategy | gemini-2.5 (gemini-2.5-pro) | Plan states validators are selected based on metadata but provides no concrete pattern (registry, mapping dict) for implementation. | 2026-02-20 20:00:05 UTC |
| R2-S15 | Define behavior when context sources are present but empty | gemini-2.5 (gemini-2.5-pro) | Clarifying whether empty context results in omitted keys vs empty strings ensures clean prompts and consistent behavior. | 2026-02-20 20:00:05 UTC |
| R3-S5 | Specify file permissions for generation-manifest.json containing cost data | claude-4 (claude-opus-4-5) | High severity security concern. Cost data is sensitive business information. Specifying file permissions (e.g., 0600) is a reasonable security measure for pipeline deployments. | 2026-02-20 20:06:22 UTC |
| R4-S1 | Mandate path traversal protection for file inputs from seed | gemini-2.5 (gemini-2.5-pro) | Critical security issue. Reading file paths from seed (context_files, plan_document_path) without validation enables path traversal attacks. Must validate paths are within project root. | 2026-02-20 20:06:22 UTC |
| R4-S2 | Implement context sanitization for prompt injection mitigation | gemini-2.5 (gemini-2.5-pro) | High security risk. User-controlled data from seed is injected directly into prompts. Standard practice requires isolation or safe delimiters to prevent prompt injection attacks. | 2026-02-20 20:06:22 UTC |
| R4-S7 | Enforce code-defined registry for post-generation validators | gemini-2.5 (gemini-2.5-pro) | High security concern. If validators can be specified by seed, it creates RCE risk. Validators must come from pre-approved internal registry only. | 2026-02-20 20:06:22 UTC |
| R4-S9 | Specify concurrency-safe state management for feature queue | gemini-2.5 (gemini-2.5-pro) | Medium scalability concern. File-based .prime_contractor_state.json is prone to race conditions. At minimum, file-locking strategy should be specified for resumability feature. | 2026-02-20 20:06:22 UTC |
| R5-S1 | Define the ValidationConfig type referenced in ContextResolutionStrategy protocol | claude-4 (claude-opus-4-5) | The protocol is incomplete without this type definition. Implementation cannot proceed without knowing what validators receive and return. | 2026-02-20 20:25:40 UTC |
| R5-S2 | Specify the error propagation model for strategy method failures | claude-4 (claude-opus-4-5) | Without defined error handling contracts, implementations will handle errors inconsistently, leading to unpredictable behavior and debugging difficulties. | 2026-02-20 20:25:40 UTC |
| R5-S3 | Add test isolation strategy for PipelineContextStrategy dependencies | claude-4 (claude-opus-4-5) | Testing strategies with filesystem dependencies requires injection points. Without this, tests will be flaky or require real files, violating unit test principles. | 2026-02-20 20:25:40 UTC |
| R5-S4 | Define transformation rules for architectural_context JSON to Markdown | claude-4 (claude-opus-4-5) | The plan shows formatted output but doesn't specify transformation rules. Without this contract, implementations will produce inconsistent output. | 2026-02-20 20:25:40 UTC |
| R5-S7 | Clarify relationship between SeedContext.execution_mode and workflow.mode | claude-4 (claude-opus-4-5) | Having mode in two places without documented relationship creates potential for inconsistency and confusion. Need to clarify which is authoritative. | 2026-02-20 20:25:40 UTC |
| R5-S9 | Add explicit module import direction rules to prevent circular imports | claude-4 (claude-opus-4-5) | Bidirectional dependencies between context_resolution.py and prime_contractor.py risk circular imports. Explicit dependency rules prevent this common Python issue. | 2026-02-20 20:25:40 UTC |
| R6-S3 | Abstract manifest I/O behind ProvenanceStore protocol | gemini-2.5 (gemini-2.5-pro) | This enables proper unit testing of staleness detection without filesystem coupling. Aligns with the accepted R5-S3 test isolation suggestion. | 2026-02-20 20:25:40 UTC |
| R6-S5 | Mandate parameterized test suite for CLI flag and ModeConfig combinations | gemini-2.5 (gemini-2.5-pro) | The interaction between mode detection, explicit flags, and behavioral overrides creates many permutations that need exhaustive testing. Parameterized tests are the right approach. | 2026-02-20 20:25:40 UTC |
| R6-S8 | Remove redundant structured_context flag from ModeConfig | gemini-2.5 (gemini-2.5-pro) | The strategy choice IS the context structure policy. Having both creates confusing dual-control. Single source of truth is better design. | 2026-02-20 20:25:40 UTC |
| R6-S1 | Correct Untouched Files list for REQ-PEM-008 | gemini-2.5 (gemini-2.5-pro) | **TRIAGE CORRECTION:** Previously rejected as "duplicate of R4-S1" — but R4-S1 is path traversal, not this issue. `lead_contractor_workflow.py` moved out of Untouched, REQ-PEM-008 step added to plan. | 2026-02-20 |
| R2-S10 | Resolve contradiction between implementation plan and REQ-PEM-008 regarding lead_contractor_workflow.py | gemini-2.5 (gemini-2.5-pro) | Critical gap - the plan explicitly excludes a file that REQ-PEM-008 requires modifications to. Must add implementation step for spec-to-draft validation. | 2026-02-20 21:24:18 UTC |
| R7-S1 | Define contract between CodeGenerator.generate() and manifest's model field | claude-4 (claude-opus-4-5) | Critical dependency on generator interface change is unstated. Plan must specify this requirement to avoid implementation failure. | 2026-02-20 21:24:18 UTC |
| R7-S2 | Add implementation step for context_formatters.py module | claude-4 (claude-opus-4-5) | Valid gap - file is in inventory but no implementation step creates it. This would cause Phase 2 to fail. | 2026-02-20 21:24:18 UTC |
| R7-S3 | Specify VALIDATOR_REGISTRY handling for unknown validator names | claude-4 (claude-opus-4-5) | Security and debuggability concern. Unknown names must be handled explicitly to prevent injection attacks and aid debugging. | 2026-02-20 21:24:18 UTC |
| R7-S4 | Specify observable verification criteria for staleness reuse test #16 | claude-4 (claude-opus-4-5) | The test strategy lacks actionable verification criteria. Specifying zero LLM calls, no file modifications, and specific log message makes the test implementable and deterministic. | 2026-02-20 21:24:18 UTC |
| R7-S5 | Add module import direction rules to prevent circular imports | claude-4 (claude-opus-4-5) | Cross-module dependencies without import direction rules will cause circular import errors during implementation. | 2026-02-20 21:24:18 UTC |
| R7-S6 | Define error handling contract for ContextResolutionStrategy methods | claude-4 (claude-opus-4-5) | Undefined error handling leads to inconsistent implementations. Specifying exception types for each method enables proper error propagation. | 2026-02-20 21:24:18 UTC |
| R7-S7 | Add implementation detail for CLI flag conflict detection | claude-4 (claude-opus-4-5) | Phase 5 mentions conflict detection but doesn't specify mechanism. Clear implementation guidance prevents bugs. | 2026-02-20 21:24:18 UTC |
| R7-S8 | Specify parameterized test strategy for CLI flag combinations | claude-4 (claude-opus-4-5) | Combinatorial explosion of flag × mode combinations needs systematic coverage strategy to avoid exponential test count. | 2026-02-20 21:24:18 UTC |
| R7-S9 | Clarify SeedContext.execution_mode vs workflow.mode synchronization | claude-4 (claude-opus-4-5) | The synchronization mechanism affects state persistence and resume behavior. Must be explicit. | 2026-02-20 21:24:18 UTC |
| R7-S10 | Specify manifest file permissions for pipeline mode | claude-4 (claude-opus-4-5) | Cost data in manifest may be sensitive. Restrictive permissions are appropriate defense-in-depth. | 2026-02-20 21:24:18 UTC |
| R8-S4 | Enforce SeedContext immutability with runtime error after execution begins instead of undefined behavior | claude-4 (claude-opus-4-5) | Undefined behavior is a bug waiting to happen. A clear RuntimeError provides a fail-fast contract that prevents subtle state corruption. This strengthens the lifecycle constraint already specified. | 2026-02-20 21:24:18 UTC |
| R8-S6 | Specify source_checksum computation logic within implementation plan | gemini-2.5 (gemini-2.5-pro) | Checksum must be computed from canonical JSON before parsing to ensure determinism. This detail is critical for staleness detection correctness. | 2026-02-20 21:24:18 UTC |
| R8-S5 | Add system prompt instruction telling LLM to treat delimited content as non-instructional data | claude-4 (claude-opus-4-5) | The mitigation is incomplete without the model instruction. Simply wrapping in tags is insufficient - the model must be told to interpret the tags correctly. This is critical for effective prompt injection defense. | 2026-02-20 21:24:18 UTC |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R4-S3 | Abstract filesystem I/O behind StorageProvider protocol | gemini-2.5 (gemini-2.5-pro) | Over-engineering for current scope. The plan explicitly targets local filesystem operations. Cloud storage abstraction is a valid future enhancement but adds significant complexity without immediate benefit. | 2026-02-20 20:06:22 UTC |
| R4-S4 | Consolidate all mode-specific logic into ContextResolutionStrategy | gemini-2.5 (gemini-2.5-pro) | The separation between ModeConfig (configuration) and Strategy (behavior) follows established patterns. ModeConfig holds declarative flags; strategies implement behavior. Merging them would conflate concerns. | 2026-02-20 20:06:22 UTC |
| R4-S5 | Relocate core types to dedicated types.py module | gemini-2.5 (gemini-2.5-pro) | While generally good practice, this is a refactoring preference, not a defect. The current placement in prime_contractor.py is acceptable for the scope of this implementation. Can be addressed in future cleanup. | 2026-02-20 20:06:22 UTC |
| R4-S6 | Mandate snapshot testing for generated gen_context | gemini-2.5 (gemini-2.5-pro) | Snapshot testing is a test implementation choice, not an architectural requirement. The plan already specifies strategy tests in Phase 2. Teams can adopt snapshot testing as they see fit. | 2026-02-20 20:06:22 UTC |
| R4-S8 | Decouple validator resolution from context strategy | gemini-2.5 (gemini-2.5-pro) | Premature separation. The current design where strategy returns validation config is coherent - the strategy knows what validation applies to its mode. Separating creates unnecessary indirection for the current scope. | 2026-02-20 20:06:22 UTC |
| R4-S10 | Consolidate prime-result.json and generation-manifest.json | gemini-2.5 (gemini-2.5-pro) | These serve different purposes: prime-result.json is the workflow result, generation-manifest.json is provenance for staleness detection. Merging conflates concerns and complicates downstream consumers expecting specific formats. | 2026-02-20 20:06:22 UTC |
| R5-S5 | Consolidate mode-specific behavior into ModeConfigBuilder | claude-4 (claude-opus-4-5) | The current design with ModeConfig.for_mode() is already reasonably centralized. Adding a builder pattern increases complexity without proportional benefit for the current scope. | 2026-02-20 20:25:40 UTC |
| R5-S6 | Specify fixture strategy for staleness detection tests | claude-4 (claude-opus-4-5) | This is a duplicate of R3-F3 which was already accepted. Both address the same fixture generation problem. | 2026-02-20 20:25:40 UTC |
| R5-S8 | Specify checksum computation inputs and algorithm | claude-4 (claude-opus-4-5) | This is a duplicate of R3-F3 which was already accepted. Both address checksum specification. | 2026-02-20 20:25:40 UTC |
| R5-S10 | Replace 'byte-identical' with 'structurally equivalent' in Phase 2 | claude-4 (claude-opus-4-5) | R5-F3 addresses the same issue for the requirements. Accepting both would be redundant. | 2026-02-20 20:25:40 UTC |
| ~~R6-S1~~ | ~~Correct implementation plan's Untouched Files list for REQ-PEM-008~~ | ~~gemini-2.5 (gemini-2.5-pro)~~ | **TRIAGE ERROR — MOVED TO APPENDIX A.** Original rejection rationale ("duplicate of R4-S1") was incorrect — R4-S1 addresses path traversal security, not REQ-PEM-008 coverage. This suggestion was valid and has been applied: `lead_contractor_workflow.py` moved out of Untouched Files, REQ-PEM-008 implementation step added. | 2026-02-20 |
| R6-S2 | Decompose PipelineContextStrategy.resolve_task_context into smaller builders | gemini-2.5 (gemini-2.5-pro) | This is premature optimization. The method can be refactored later if it becomes unwieldy. The current design is clear and the suggestion adds complexity without proven need. | 2026-02-20 20:25:40 UTC |
| R6-S4 | Formalize SeedContext state lifecycle with explicit immutability transition | gemini-2.5 (gemini-2.5-pro) | R5-S7 was already accepted to clarify the mode relationship. Adding formal lifecycle management with freezing adds complexity. The property setters solution is pragmatic for backward compatibility. | 2026-02-20 20:25:40 UTC |
| R6-S6 | Make pipeline mode auto-detection signals declarative/configurable | gemini-2.5 (gemini-2.5-pro) | This is over-engineering for the current scope. The detection signals are unlikely to change frequently, and code changes are acceptable when they do. | 2026-02-20 20:25:40 UTC |
| R6-S7 | Refactor ModeConfig to generic key-value configuration | gemini-2.5 (gemini-2.5-pro) | The strongly-typed dataclass approach is clearer and provides better IDE support and type checking. The number of behaviors is bounded and well-known. | 2026-02-20 20:25:40 UTC |
| R6-S9 | Add ContextSanitizer stage to prevent sensitive data leakage | gemini-2.5 (gemini-2.5-pro) | R4-S9 was already accepted for security considerations. Additionally, sanitization is an implementation detail that should be handled at the logging/manifest writing layer, not as a separate pipeline stage. | 2026-02-20 20:25:40 UTC |
| R6-S10 | Introduce context snippet builder fixtures for testing | gemini-2.5 (gemini-2.5-pro) | This is a test implementation detail that doesn't need to be in the architecture plan. Test authors can create appropriate fixtures during implementation. | 2026-02-20 20:25:40 UTC |
| R8-S2 | Add CodeGenerator protocol changes for cost reporting | gemini-2.5 (gemini-2.5-pro) | R7-S1 was already accepted which addresses the generator interface change. Additionally, the plan already states cost is captured from generator return value. | 2026-02-20 21:24:18 UTC |
| R8-S3 | Define validator lifecycle to avoid redundant initializations | gemini-2.5 (gemini-2.5-pro) | This is an optimization detail. The current design treating validators as per-feature is simpler and sufficient for the initial implementation. Caching can be added later if performance issues arise. | 2026-02-20 21:24:18 UTC |
| R8-S5 | Define interaction between load_seed_context() and seedless add_feature() | claude-4 (claude-opus-4-5) | These are two independent initialization paths. The plan already specifies that seedless mode initializes SeedContext with defaults. The suggested state machine adds complexity for a minor edge case. | 2026-02-20 21:24:18 UTC |
| R8-S7 | Re-evaluate manifest read-path security vs functionality | gemini-2.5 (gemini-2.5-pro) | The 0o600 permissions are appropriate for single-user pipeline runs. Multi-user pipeline scenarios with different privilege levels are out of scope for this design. | 2026-02-20 21:24:18 UTC |
| R8-S8 | Clarify 'template rendering failures' in error handling contract | gemini-2.5 (gemini-2.5-pro) | The context formatters do transform data, which is analogous to template rendering. The current language is acceptable and the error type (RuntimeError) is appropriate. | 2026-02-20 21:24:18 UTC |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1
- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 19:57:21 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | completeness | critical | Define explicit error handling when `--mode pipeline` is forced but seed lacks critical context fields (onboarding, architectural_context) | Applied R1-S1 and R2-S4 identified this gap but the plan doesn't specify the implementation. Should pipeline mode fail fast, emit warnings, or degrade? The plan's "logs missing fields as warnings" under Risk Assessment contradicts the concept of "critical" fields from R2-S4. | Phase 2, `PipelineContextStrategy.resolve_seed_context()` implementation | Test: force `--mode pipeline` with minimal seed, verify defined behavior (exception, warning level, or degraded output) |
| R3-S2 | architecture | high | Add explicit `ValidationConfig` dataclass definition alongside the protocol in Phase 1 | `ContextResolutionStrategy.resolve_validation_config()` returns `ValidationConfig` but this type is never defined. Without the dataclass definition, Phase 4 cannot implement the validation hookpoint correctly. | Phase 1, Step 4, alongside `ContextResolutionStrategy` protocol | Verify `ValidationConfig` is importable and used in Phase 4 tests |
| R3-S3 | completeness | high | Define initialization path for seedless `add_feature()` workflow execution described in REQ-PEM-010 | Applied R2-S2 flagged this gap. Phase 3 adds `add_feature()` convenience method but doesn't specify how `SeedContext` is initialized when no seed file is provided. Current workflow assumes seed-based initialization. | Phase 3, Step 2, with new "seedless initialization" subsection | Test: construct workflow without seed, use `add_feature()`, verify `SeedContext` has safe defaults |
| R3-S4 | clarity | high | Specify the exact transformation for "formatted, not raw JSON" architectural context in pipeline strategy | Applied R2-S3 identified this ambiguity. Phase 2's pipeline context structure shows `"architectural_context": "## Project Architecture\n..."` but doesn't define the JSON→Markdown transformation algorithm. | Phase 2, Step 3, add transformation pseudocode or reference implementation | Unit test verifying specific JSON input produces expected formatted output |
| R3-S5 | consistency | medium | Resolve immutability vs setter contradiction for `SeedContext` | Applied R2-S1 identified the contradiction. Phase 1 Step 5 says "Property setters populate `SeedContext` fields" but `SeedContext` should be immutable per REQ-PEM-005. The plan must specify: (a) make `SeedContext` mutable, (b) deprecate setters, or (c) replace-whole-object pattern. | Phase 1, Step 3 and Step 5, add explicit mutability decision | Test: attempt to modify `SeedContext` after workflow starts, verify defined behavior |
| R3-S6 | testability | medium | Replace "byte-identical output" claim with verifiable structural equivalence criteria | Applied R1-S2 noted LLM non-determinism makes byte-identical claims unverifiable. Phase 2 test "Standalone strategy produces identical gen_context to current code" needs concrete verification scope: JSON structure, key presence, value types vs literal values. | Phase 2 Tests section, refine first bullet point | Test with fixed inputs, verify structural properties (keys, types, non-empty values) rather than exact content |
| R3-S7 | completeness | medium | Define CLI flag precedence rules and conflict resolution | Applied R1-S10 and R2-S8 both identified missing precedence rules. Phase 5 adds `--validate/--no-validate` but doesn't specify what happens when both are passed, or how `--mode standalone --validate` overrides `ModeConfig`. | Phase 5, Step 2, add "Flag Precedence" subsection | Test: pass conflicting flags, verify deterministic behavior (error or defined precedence) |
| R3-S8 | maintainability | medium | Add explicit mode state serialization for workflow resume scenarios | Applied R1-S4 identified that mode must persist across resume/retry. Phase 1 adds `self.mode` but `.prime_contractor_state.json` serialization isn't updated to include execution mode. | Phase 1, after Step 6, add state serialization update | Test: interrupt workflow, resume, verify mode remains consistent |
| R3-S9 | completeness | medium | Specify `source_checksum` requirement tier for pipeline mode | Applied R1-S5 noted `source_checksum` is `Optional[str]` but pipeline mode validates it. The plan should clarify: is missing checksum a warning (degrade) or error (fail fast) in pipeline mode? | Phase 1, Step 3, annotate field with mode-specific requirements | Test: pipeline mode with/without `source_checksum`, verify staleness detection behavior |
| R3-S10 | testability | low | Add error handling tests for `context_files` with missing or unreadable files | Applied R1-S6 identified undefined file access error behavior. Phase 2 includes `context_files` in `SeedContext` but no error handling is specified when files don't exist. | Phase 2 Tests section, add negative test cases | Test: provide seed with non-existent file path in `context_files`, verify graceful handling |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | ambiguity | high | REQ-PEM-007 references `find_missing_parameters()` from `prompt_utils.py` but this function is not defined in the requirements or the plan | The spec-to-draft validation in REQ-PEM-008 depends on a shared utility that isn't specified anywhere. Implementation cannot proceed without this definition. | REQ-PEM-008 or new appendix defining shared utilities | Define function signature, input/output, and location |
| R3-F2 | completeness | medium | REQ-PEM-003 `ModeConfig` lacks specification for individual behavior override mechanism | Requirements state "Individual behaviors can be overridden via CLI flags" but don't define which ModeConfig fields are overridable or the override syntax | REQ-PEM-003 acceptance criteria | Add table mapping CLI flags to ModeConfig fields |
| R3-F3 | consistency | medium | REQ-PEM-011 lists "OTel spans" as STANDALONE="Only if instrumentor configured" but REQ-PEM-001 doesn't include OTel configuration in mode declaration | OTel behavior varies by mode but isn't part of ExecutionMode enum or ModeConfig specification in REQ-PEM-003 | REQ-PEM-003 ModeConfig table | Add `emit_otel_spans: bool` to ModeConfig specification |
| R3-F4 | ambiguity | medium | REQ-PEM-007 specifies `feature.metadata["requirements_text"]` but REQ-PEM-009 lists `requirements_text` as a top-level enrichment field, not nested under `metadata` | Inconsistent field path specification will cause implementation confusion | Reconcile REQ-PEM-007 and REQ-PEM-009 | Define canonical path for requirements_text |
| R3-F5 | testability | low | Verification Test #6 claims "Standalone strategy produces identical gen_context" but this is unverifiable without fixed LLM responses | Test strategy doesn't account for non-deterministic components in context building | Test Strategy table, Test #6 | Specify mock/fixture strategy for deterministic testing |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| REQ-PEM-001: ExecutionMode Enum | Phase 1, Step 1 | Full | None |
| REQ-PEM-002: Mode Auto-Detection | Phase 1, Step 6 | Partial | Explicit logging format for detection signals not specified |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1, Step 2 | Partial | Missing individual override mechanism, OTel configuration |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1, Step 4 | Partial | `ValidationConfig` type not defined |
| REQ-PEM-005: SeedContext Dataclass | Phase 1, Step 3 | Full | None |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2, Steps 1-2 | Full | None |
| REQ-PEM-007: PipelineContextStrategy | Phase 2, Step 3 | Partial | Architectural context formatting undefined, critical vs optional field distinction missing |
| REQ-PEM-008: Spec-to-Draft Validation | Not addressed | None | No plan phase covers IMP-P6 spec completeness check; `find_missing_parameters()` undefined |
| REQ-PEM-009: Unified Feature Loading | Phase 3, Step 1 | Full | None |
| REQ-PEM-010: Standalone Feature Construction | Phase 3, Step 2 | Partial | SeedContext initialization for seedless path undefined |
| REQ-PEM-011: Mode-Specific Output | Phase 4, Steps 1-4 | Full | None |
| REQ-PEM-012: Generation Manifest | Phase 4, Step 1 | Full | None |
| REQ-PEM-013: Staleness Detection | Phase 4, Step 2 | Partial | workflow_id comparison logic unclear per R2-S5 |
| REQ-PEM-014: Validation Results in Output | Phase 4, Step 3 | Full | None |
| REQ-PEM-015: Zero-Change Standalone | Phase 1 commit gate, Phase 2 tests | Full | None |
| REQ-PEM-016: Script Compatibility | Phase 5, Steps 1-2 | Partial | Flag precedence rules missing, invalid mode error handling unspecified |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1, Step 5 | Partial | Setter behavior contradicts SeedContext immutability |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- None remaining — all prior suggestions from R1 and R2 have been triaged to Appendix A or B.

#### Review Round R2
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 19:58:16 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S10 | consistency | critical | Resolve the contradiction between the implementation plan and REQ-PEM-008. The plan lists `lead_contractor_workflow.py` in "Untouched Files," but the requirement explicitly places the "Spec-to-Draft Validation" logic within that file. | This is a direct conflict between the plan and requirements for a P2 feature. The plan is guaranteed to fail acceptance criteria for REQ-PEM-008 if this is not corrected. Either the plan must be updated to modify the file, or the requirement must be moved. | Implementation Plan: "Untouched Files" and add a new step in a relevant Phase. | Add a test case specifically for `lead_contractor_workflow.py` that verifies the spec completeness check is performed in pipeline mode and skipped in standalone mode, as per REQ-PEM-008. |
| R2-S11 | completeness | high | The data flow for populating the `model` field in `generation-manifest.json` (REQ-PEM-012) is undefined. | The manifest schema requires the LLM model name, but neither the requirements nor the plan specify how this information is captured from the generator and passed back to the workflow to be included in the manifest. | REQ-PEM-012, Implementation Plan Phase 4 | Modify the `CodeGenerator.generate()` return signature to include model information. Update Phase 4 tests to assert the `model` field in the manifest matches the one used for generation. |
| R2-S12 | completeness | medium | The implementation plan for the runner script (Phase 5) omits the `--strict-validation` flag required by REQ-PEM-014. | The requirements state that validation severity should not affect the exit code *unless* this flag is passed. Omitting it from the plan means a required piece of functionality will not be implemented. | Implementation Plan Phase 5 | Add a test case that runs a pipeline-mode generation with a failing validator. Assert the script exits with code 0 without the flag, and with a non-zero code when `--strict-validation` is passed. |
| R2-S13 | maintainability | medium | The plan's approach for applying CLI overrides to the `ModeConfig` (Phase 5) implies mutating a frozen dataclass, which will fail at runtime. | The plan defines `ModeConfig` with `frozen=True` (Phase 1) but later suggests modifying it. This is not only a technical error but also poor practice. An immutable update pattern should be specified. | Implementation Plan Phase 5, Step 2 | The test for CLI overrides (e.g., `--validate` in standalone mode) should verify that the `ModeConfig` instance used by the workflow has the correct, overridden values without raising a `FrozenInstanceError`. |
| R2-S14 | completeness | medium | The mechanism for mapping `feature.metadata` to a list of validators in `PipelineContextStrategy.resolve_validation_config()` is unspecified. | REQ-PEM-007 and the plan state that validators are selected based on enrichment metadata, but the "how" is missing. A concrete pattern (e.g., a validator registry, a dictionary mapping metadata keys to callables) is needed for implementation. | Implementation Plan Phase 2, Step 3 | Create a unit test for `PipelineContextStrategy.resolve_validation_config()` that provides a `FeatureSpec` with specific metadata and asserts that the correct list of validator functions is returned. |
| R2-S15 | clarity | low | Define the behavior of `PipelineContextStrategy` when a context source is present but empty (e.g., `architectural_context: {}`). | To ensure clean and efficient prompts, the system should specify whether an empty context source results in an omitted section in the `gen_context` dict, or a key with an empty string/header. Omitting the key is preferable. | Implementation Plan Phase 2, Step 5 (gen_context structure) | Add a test case where a pipeline seed has an empty `architectural_context` dict, and assert that the corresponding key is absent from the final `gen_context` passed to the generator. |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | ambiguity | medium | The structure of the `Dict[str, Any]` for each item in `context_files` (REQ-PEM-005) is undefined. | To implement context file loading, developers need to know the expected keys and value types in this dictionary (e.g., `{'path': str, 'name': str, 'type': str}`). Leaving it as `Any` creates implementation ambiguity and risks integration failures. | REQ-PEM-005, `SeedContext` dataclass definition | A schema validation test should be added for the seed file, asserting that `context_files` entries conform to the newly defined structure. |
| R2-F2 | clarity | low | Clarify the sequence of operations between "default mode" (REQ-PEM-001) and "auto-detection" (REQ-PEM-002). | The requirements are slightly confusing. It should be explicitly stated that the effective mode is determined in a specific order: 1) explicit CLI flag, 2) if no flag, auto-detection from seed, 3) `STANDALONE` is the result of auto-detection if no signals are found. | REQ-PEM-001 or REQ-PEM-002 | The existing test cases for auto-detection and explicit override cover this, but the requirement's text should be sharpened to reflect this procedural logic. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps / Notes |
|---|---|---|---|
| REQ-PEM-001: ExecutionMode Enum | Phase 1 | Full | Covered. |
| REQ-PEM-002: Mode Auto-Detection | Phase 1, 5 | Full | Covered. |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1, 5 | Full | Covered. |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1 | Full | Covered. |
| REQ-PEM-005: SeedContext Dataclass | Phase 1 | Full | Covered, but inherits the immutability vs. setter conflict identified in R2-S1 (applied). |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2 | Full | Covered. |
| REQ-PEM-007: PipelineContextStrategy | Phase 2, 4 | Full | Covered. |
| **REQ-PEM-008: Spec-to-Draft Validation** | **(None)** | **None** | **Critical Gap:** The plan explicitly marks the target file (`lead_contractor_workflow.py`) as "untouched," directly contradicting this requirement. |
| REQ-PEM-009: Unified Feature Loading | Phase 3 | Full | Covered. |
| REQ-PEM-010: Standalone Feature Construction | Phase 3 | Full | Covered. |
| REQ-PEM-011: Mode-Specific Output | Phase 4 | Full | Covered. |
| REQ-PEM-012: Generation Manifest | Phase 4 | Partial | **Gap:** The plan does not specify the data flow for capturing the required `model` field. |
| REQ-PEM-013: Staleness Detection | Phase 4 | Full | Covered. |
| REQ-PEM-014: Validation Results in Output | Phase 4, 5 | Partial | **Gap:** The plan omits the implementation of the required `--strict-validation` flag. |
| REQ-PEM-015: Zero-Change Standalone | All | Full | The plan is structured around preserving standalone behavior. |
| REQ-PEM-016: Script Compatibility | Phase 5 | Partial | **Gap:** The plan omits the implementation of the required `--strict-validation` flag. |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1 | Full | Covered, but inherits the immutability vs. setter conflict identified in R2-S1 (applied). |

#### Review Round R3

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:03:28 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | security | critical | Define input validation and sanitization requirements for context fields injected into LLM prompts | Pipeline mode injects `architectural_context`, `requirements_text`, `plan_context` etc. directly into prompts. No validation is specified against prompt injection, malformed content, or excessively large inputs that could cause token overflow or unexpected LLM behavior. | New section in Phase 2 under PipelineContextStrategy specifying input sanitization rules | Add tests with adversarial inputs (special characters, excessive length, nested prompts) to verify sanitization |
| R3-S2 | architecture | high | Define interface boundary for ValidationConfig and validator callable signature | Phase 4 references `ValidationConfig` and "validator callables" but neither the type definition nor the expected signature (`(files: List[Path]) -> ValidationResult`?) is specified. Implementations cannot proceed without this contract. | Phase 1 or Phase 4 with explicit `ValidationConfig` dataclass and `Validator` protocol definitions | Protocol compliance test verifies validator implementations match expected signature |
| R3-S3 | scalability | high | Address memory footprint for large context files in SeedContext | `SeedContext.context_files` loads file contents into memory. For pipeline mode with multiple large design documents, this could cause memory exhaustion. No lazy loading or size limits are specified. | Phase 1 SeedContext definition: add optional lazy loading or size thresholds with configurable limits | Load test with 10+ context files of 1MB each; verify memory stays bounded or graceful failure occurs |
| R3-S4 | scalability | high | Define concurrent feature generation model for pipeline mode | The plan states "same workflow execution loop" but doesn't address whether features can be generated in parallel. For large seeds with 50+ features, sequential processing becomes a bottleneck. Pipeline mode should specify parallelization strategy. | New subsection in Phase 4 or Overview addressing feature processing concurrency model | Benchmark test comparing sequential vs parallel generation time for 20+ features |
| R3-S5 | security | high | Specify access control for generation-manifest.json containing cost data | The manifest includes `cost_usd` per feature and total cost. This sensitive business data is written to the output directory without access control considerations. Pipeline deployments may need restricted permissions. | Phase 4 manifest writing section: specify file permissions (e.g., 0600) and optional encryption-at-rest flag | Verify manifest file permissions after write; test that non-owner cannot read |
| R3-S6 | testability | high | Define deterministic testing strategy for `resolve_task_context()` output comparison | Phase 2 test "Standalone strategy produces identical gen_context" requires comparing dict outputs, but dicts with nested structures and optional fields are prone to ordering/comparison issues. No comparison strategy (structural, hash-based, schema-validated) is specified. | Phase 2 Tests section: specify comparison approach (e.g., `deepdiff` with ignore_order, JSON canonical form) | Test utility function that compares gen_context outputs with defined equivalence semantics |
| R3-S7 | maintainability | high | Centralize structured context section formatting into reusable template functions | Phase 2 shows inline formatting (e.g., `"## Project Architecture\n..."`) for 8+ context sections. This duplicates formatting logic and makes prompt evolution difficult. Extract to `prompt_templates.py` or similar. | Phase 2 PipelineContextStrategy: extract section builders into `context_formatters.py` with functions like `format_architectural_context(data) -> str` | Each formatter has dedicated unit test; changing a template requires one edit |
| R3-S8 | clarity | high | Specify error handling and logging strategy when context_strategy methods fail | The plan doesn't address what happens if `resolve_seed_context()` raises (e.g., schema validation error) or `resolve_validation_config()` returns invalid validators. Should workflow abort, continue with defaults, or log and skip? | Phase 2 Strategy wiring section: add error handling clause with defined fallback behavior | Test strategy method exceptions and verify workflow responds per specification |
| R3-S9 | scalability | medium | Define caching strategy for expensive context resolution operations | `PipelineContextStrategy.resolve_task_context()` may perform repeated formatting operations per feature. For 100-feature seeds, this becomes expensive. No memoization or caching layer is specified. | Phase 2 PipelineContextStrategy: specify caching for seed-level computations (computed once, reused per feature) | Profile context resolution with 50+ features; verify seed-level computations happen once |
| R3-S10 | security | medium | Validate source_checksum against tampering before staleness comparison | Phase 4 staleness detection trusts the `source_checksum` from the seed. A malicious actor could forge a checksum to force cache reuse of stale results. Verify checksum is computed, not just copied from input. | Phase 4 staleness detection: specify that checksum is recomputed from seed contents, not read from seed metadata | Test: modify seed content but preserve declared checksum; verify staleness detection catches mismatch |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | completeness | high | REQ-PEM-012 manifest schema lacks `schema_version` migration strategy | The manifest includes `schema_version: "1.0.0"` but no requirement specifies how consumers should handle version mismatches or how to migrate manifests when schema evolves. This will cause integration failures when schema changes. | REQ-PEM-012 acceptance criteria: add version compatibility rules | Test: attempt to read 1.0.0 manifest with 1.1.0 reader; verify graceful handling |
| R3-F2 | clarity | medium | REQ-PEM-007 structured sections lack maximum length specifications | Pipeline context sections (`architectural_context`, `plan_context`, etc.) have no size limits. Uncontrolled growth could exceed LLM context windows and cause generation failures. | REQ-PEM-007 resolve_task_context: add maximum token/character limits per section with truncation strategy | Test with oversized context; verify truncation occurs and generation succeeds |
| R3-F3 | testability | medium | Verification Test #15-16 for staleness detection lack checksum computation details | Tests specify "matching checksum reuses" but don't define how to create test fixtures with known checksums, making tests non-reproducible. | Verification section: add fixture generation strategy for deterministic checksum testing | Provide example test seed with pre-computed checksum |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---------------------|--------------|----------|------|
| REQ-PEM-001 (ExecutionMode Enum) | Phase 1 Step 1 | Full | None |
| REQ-PEM-002 (Mode Auto-Detection) | Phase 1 Step 6 | Full | None |
| REQ-PEM-003 (Mode-Specific Configuration) | Phase 1 Step 2 | Partial | ModeConfig fields don't enumerate all 7 behaviors from requirements table |
| REQ-PEM-004 (ContextResolutionStrategy Protocol) | Phase 1 Step 4 | Full | None |
| REQ-PEM-005 (SeedContext Dataclass) | Phase 1 Step 3, 5 | Full | None |
| REQ-PEM-006 (StandaloneContextStrategy) | Phase 2 Step 2 | Full | None |
| REQ-PEM-007 (PipelineContextStrategy) | Phase 2 Step 3, 5 | Partial | Missing `find_missing_parameters()` implementation referenced in requirements |
| REQ-PEM-008 (Spec-to-Draft Validation) | Not addressed | None | No plan step implements IMP-P6 spec completeness check |
| REQ-PEM-009 (Unified Feature Loading) | Phase 3 Step 1 | Full | None |
| REQ-PEM-010 (Standalone Feature Construction) | Phase 3 Step 2 | Full | None |
| REQ-PEM-011 (Mode-Specific Output) | Phase 4 | Partial | Cost reporting format difference not detailed |
| REQ-PEM-012 (Generation Manifest) | Phase 4 Step 1 | Full | None |
| REQ-PEM-013 (Staleness Detection) | Phase 4 Step 2 | Full | None |
| REQ-PEM-014 (Validation Results in Output) | Phase 4 Step 3 | Full | None |
| REQ-PEM-015 (Zero-Change Standalone) | All Phases (commit gates) | Full | None |
| REQ-PEM-016 (Script Compatibility) | Phase 5 | Full | None |
| REQ-PEM-017 (Property Accessor Compatibility) | Phase 1 Step 5 | Full | None |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F4: Requirements text path inconsistency between REQ-PEM-007 and REQ-PEM-009 creates genuine implementation ambiguity that will surface during Phase 2 development
- R3-F3: OTel behavior divergence between REQ-PEM-011 and ModeConfig specification needs reconciliation before Phase 1 ModeConfig is finalized

#### Review Round R4
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:04:22 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | security | critical | Mandate path traversal protection for all file inputs from the seed. | The plan involves reading file paths from the seed (`context_files`, `plan_document_path`) without mentioning any security validation. This creates a severe path traversal vulnerability, allowing a malicious seed to read sensitive files from the system (e.g., `../../etc/passwd`). | Phase 2, in both `StandaloneContextStrategy` and `PipelineContextStrategy` file-reading logic. | Unit test the context resolution with malicious paths containing `..` or absolute paths outside the project root; assert that an error is raised. |
| R4-S2 | security | high | Implement context sanitization to mitigate prompt injection risks. | The plan injects user-controlled data from the seed (e.g., `project_objectives`) directly into prompts. This exposes the system to prompt injection, where malicious instructions could hijack the LLM's behavior. Standard practice is to isolate or escape such inputs. | Phase 2, `PipelineContextStrategy.resolve_task_context`. | A test case with a seed containing adversarial instructions (e.g., "ignore prior instructions") should verify that the input is wrapped in safe delimiters (e.g., XML tags) within the final `gen_context`. |
| R4-S3 | scalability | high | Abstract all filesystem I/O behind a `StorageProvider` protocol. | The plan hardcodes all I/O to a local filesystem, which will not scale in a cloud-native or distributed environment where artifacts are stored in object storage (S3, GCS). Introducing an abstraction layer now prevents a costly future refactoring. | Architectural decision affecting all Phases. Introduce protocol in Phase 1; implement `FileSystemStorageProvider` as the default. | Instantiate the workflow with a mock `StorageProvider` and verify that all file read/write operations (for seeds, outputs, manifests) are routed through the mock's methods. |
| R4-S4 | architecture | high | Consolidate all mode-specific logic into the `ContextResolutionStrategy`. | The current design splits mode-specific behavior between `ModeConfig` (workflow-level flags) and the `Strategy` pattern (context-level logic). This violates the single source of truth principle. All mode-dependent decisions should be delegated to the strategy. | Phase 1. Eliminate `ModeConfig` and add its methods (e.g., `should_emit_provenance()`) to the `ContextResolutionStrategy` protocol. | Code review confirms `ModeConfig` is removed and workflow logic calls methods on `self.context_strategy` instead of checking a separate config object. |
| R4-S5 | maintainability | medium | Relocate core types (`ExecutionMode`, `SeedContext`) to a dedicated `types.py` module. | Placing core data structures inside a large implementation file (`prime_contractor.py`) creates tight coupling and high risk of future circular import errors. A dedicated types module is a standard architectural pattern for maintainability. This revisits R4-S9 with a stronger architectural rationale. | Phase 1. Create `src/startd8/contractors/types.py` and move relevant definitions there. | Static analysis and code review confirm that the workflow, strategies, and CLI script all import from the new shared module without introducing circular dependencies. |
| R4-S6 | testability | medium | Mandate snapshot testing for the generated `gen_context` from `PipelineContextStrategy`. | The complex, multi-part textual context generated by the pipeline strategy is critical for quality but brittle and hard to validate with simple assertions. Snapshot tests provide a robust way to detect and approve any changes to this critical output. | Phase 2, Test Strategy for `test_context_resolution.py`. | Implement a snapshot test for `resolve_task_context`. The test fails if the generated context string changes, requiring explicit approval to update the baseline snapshot. |
| R4-S7 | security | high | Enforce a secure, code-defined registry for all post-generation validators. | The plan is ambiguous about how validators are loaded. If the seed file can specify a validator to load (e.g., by class name or path), it creates a remote code execution (RCE) vulnerability. The system must only run validators from a pre-approved, internal list. | Phase 2, `PipelineContextStrategy.resolve_validation_config`. | A test using a seed that attempts to specify a custom/arbitrary validator name must show that the request is rejected or ignored, not dynamically loaded and executed. |
| R4-S8 | architecture | medium | Decouple validator resolution from the context strategy. | The plan has `resolve_validation_config` returning validator callables, mixing the responsibilities of context resolution and validator instantiation. This violates the Single Responsibility Principle. The strategy should return a declarative configuration, and a separate factory should build the validators. | Phase 2. The strategy should return a `ValidationConfig` data object. A new `ValidatorRegistry` service should consume this config to create validator instances. | Unit tests for the strategy confirm it produces the correct config object. Separate tests for the registry confirm it correctly instantiates validators from the config. |
| R4-S9 | scalability | medium | Specify a concurrency-safe state management mechanism for the feature queue. | The plan mentions `.prime_contractor_state.json` for resumability, but this file-based approach is prone to race conditions and corruption in parallel or distributed environments. The design must specify a robust state management approach that can scale. | Phase 3, Feature Queue Hardening. | The plan should be updated to specify either a file-locking strategy or, preferably, an abstraction that allows for a database or key-value store backend for state tracking. |
| R4-S10 | clarity | medium | Consolidate `prime-result.json` and `generation-manifest.json` into a single output artifact. | Maintaining two separate but overlapping JSON output files in pipeline mode is redundant and confusing for downstream consumers. A single, canonical, machine-readable manifest should be the sole source of truth for a run's results. | Phase 4, Output Contract. | The plan should be updated to merge all fields from `prime-result.json` into the manifest schema. Tests for pipeline mode should verify only one JSON artifact is produced. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Defining the structure for `context_files` is essential for implementation; `Dict[str, Any]` is too ambiguous.
- R3-F1: The plan is blocked without a definition for the `find_missing_parameters()` function, which is a required dependency.
- R3-F3: OTel configuration is a mode-specific behavior and should be consistently managed via the primary mode configuration mechanism for clarity.

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | consistency | high | Resolve contradiction between `SeedContext` defaults and pipeline mode warnings. | REQ-PEM-005 specifies `default_factory=dict` for context fields, which means they are never "missing". However, REQ-PEM-007 requires logging warnings for missing fields. The requirements should state that pipeline mode checks for key *presence* in the raw seed before applying defaults. | REQ-PEM-005 and REQ-PEM-007. | A test for pipeline mode should use a seed where `onboarding` key is absent, and verify a warning is logged. |
| R4-F2 | completeness | high | Enhance staleness detection to be code-version aware. | REQ-PEM-013's staleness check is based only on the input `source_checksum`. It is blind to changes in the generator code itself (e.g., updated prompt templates, bug fixes). A stale artifact could be reused incorrectly, propagating old bugs. | REQ-PEM-012, REQ-PEM-013. | Add a `generator_version` (e.g., a git commit hash) to the `generation-manifest.json` and include it in the staleness comparison. |
| R4-F3 | completeness | critical | The implementation plan completely omits REQ-PEM-008. | The plan's "Untouched Files" section explicitly excludes `lead_contractor_workflow.py`, but REQ-PEM-008 (Spec-to-Draft Validation) requires modifications to this file. This is a major gap where a P2 requirement is entirely unaddressed. | Add a new step to the implementation plan, likely in Phase 4, to implement the spec completeness check. | Add test cases #9 and #10 from the requirements doc to the implementation plan's test suite. |
| R4-F4 | security | critical | Add an explicit requirement for secure handling of external inputs. | The requirements document lacks any mention of security. Critical vulnerabilities like path traversal and prompt injection are not forbidden by the current requirements, making it possible to have a compliant but insecure implementation. | Add a new top-level requirement (e.g., REQ-PEM-018: Secure Input Handling). | Security-focused code reviews and penetration tests should be added to the verification strategy. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps / Notes |
|---|---|---|---|
| REQ-PEM-001: ExecutionMode Enum | Phase 1, Step 1 | Full | |
| REQ-PEM-002: Mode Auto-Detection | Phase 1, Step 6; Phase 5, Step 2 | Full | |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1, Step 2; Phase 5, Step 2 | Full | Suggestion R4-S4 proposes refactoring this into the Strategy. |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1, Step 4 | Full | |
| REQ-PEM-005: SeedContext Dataclass | Phase 1, Step 3 & 5 | Full | |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2, Step 2 | Full | |
| REQ-PEM-007: PipelineContextStrategy | Phase 2, Step 3 | Full | |
| REQ-PEM-008: Spec-to-Draft Validation | **None** | **None** | **CRITICAL GAP:** This requirement is not addressed anywhere in the implementation plan. The plan incorrectly lists the target file as "Untouched". |
| REQ-PEM-009: Unified Feature Loading | Phase 3, Step 1 & 3 | Full | |
| REQ-PEM-010: Standalone Feature Construction | Phase 3, Step 2 | Full | |
| REQ-PEM-011: Mode-Specific Output | Phase 4, Step 1 | Full | |
| REQ-PEM-012: Generation Manifest | Phase 4, Step 1 | Full | |
| REQ-PEM-013: Staleness Detection | Phase 4, Step 2 | Full | |
| REQ-PEM-014: Validation Results in Output | Phase 4, Step 3 | Full | |
| REQ-PEM-015: Zero-Change Standalone | All Phases (Commit Gates) | Full | |
| REQ-PEM-016: Script Compatibility | Phase 5 | Full | |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1, Step 5 | Full | |

#### Review Round R5

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 20:22:22 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | architecture | critical | Define the ValidationConfig type referenced in ContextResolutionStrategy protocol but never specified | Phase 1 defines `ContextResolutionStrategy.resolve_validation_config()` returning `ValidationConfig`, but this type is never defined anywhere in the plan. The protocol is incomplete without specifying what validators receive and return (input types, result schema, callable signature). This is a blocking gap for Phase 2 and Phase 4 implementation. | Phase 1 Steps, after ModeConfig definition: add `ValidationConfig` dataclass with `validators: List[Callable[[GeneratedFile], ValidationResult]]` and `ValidationResult` schema | Unit test: `ValidationConfig` is importable; validators are callable with defined signature; results conform to schema |
| R5-S2 | architecture | high | Specify the error propagation model for strategy method failures | The plan describes two strategies with `resolve_*` methods but doesn't specify what happens when resolution fails (e.g., file read error in `resolve_seed_context`, template rendering failure in `resolve_task_context`). Should exceptions propagate? Be caught and logged? Trigger fallback to standalone? Without this, error handling will be inconsistent across implementations. | Phase 2 Steps: add error handling contract for each strategy method specifying exception types, logging requirements, and recovery behavior | Test: inject file read failure into PipelineContextStrategy; verify defined error behavior (exception type, log message, workflow state) |
| R5-S3 | testability | high | Add test isolation strategy for PipelineContextStrategy's external dependencies | `PipelineContextStrategy.resolve_task_context()` depends on file system (context_files), seed structure (onboarding, architectural_context), and potentially templates. The plan has no strategy for mocking these dependencies in unit tests, making pipeline strategy tests either flaky (real files) or untestable (no injection points). | Phase 2 Tests section: specify dependency injection approach (constructor injection or test fixtures) for context_files, seed data, and template loading | Tests use injected mock context_files and seed data; no file system access in unit tests |
| R5-S4 | clarity | high | Define the canonical structure for formatted architectural_context output | Phase 2 Step 5 shows `"architectural_context": "## Project Architecture\n..."` but doesn't specify the transformation from raw JSON input to formatted Markdown output. What sections are generated? How are nested structures handled? Without a defined transformation contract, implementations will produce inconsistent output. | Phase 2 Step 5: add subsection specifying transformation rules (e.g., JSON keys → Markdown headers, arrays → bullet lists, nested objects → indented sections) | Unit test: given canonical JSON input, verify formatted output matches expected Markdown structure |
| R5-S5 | maintainability | high | Consolidate mode-specific behavior configuration into a single location | The plan distributes mode behavior across three mechanisms: `ModeConfig` (Phase 1), strategy selection (Phase 2), and CLI flag overrides (Phase 5). This creates maintenance burden when adding new mode-specific behaviors — developers must update multiple locations. A registry or builder pattern would centralize this configuration. | Phase 1 Steps: add `ModeConfigBuilder` that accepts CLI overrides and produces final `ModeConfig`, or document the canonical "add new mode behavior" procedure in implementation notes | Review: adding a new mode-specific behavior requires changes to exactly N files (define N); test validates builder produces correct config from flag combinations |
| R5-S6 | testability | high | Specify fixture strategy for staleness detection tests (Tests #15-16) | Phase 4 tests reference "matching checksum" and "mismatch" scenarios but don't specify how to create deterministic test fixtures with known checksums. Without a fixture generation strategy, tests cannot reliably validate staleness detection behavior. | Phase 4 Tests section: add fixture generation procedure — specify checksum algorithm (SHA-256), provide example seed with pre-computed checksum, define "modify seed to change checksum" procedure | Test fixtures include pre-computed checksums; tests verify checksum computation matches expected values before testing staleness logic |
| R5-S7 | architecture | medium | Define the relationship between SeedContext.execution_mode and workflow.mode | `SeedContext` includes `execution_mode: ExecutionMode` field, and the workflow also has `self.mode: ExecutionMode`. The plan doesn't clarify whether these are always synchronized, which is authoritative, or why both exist. This duplication creates potential for inconsistency and confusion about where to read mode. | Phase 1 Step 3 or Step 5: clarify that `SeedContext.execution_mode` is for serialization/round-trip and `workflow.mode` is the runtime authority, or consolidate to single source | Test: modify one mode value, verify the other reflects (or doesn't reflect) the change; document expected behavior |
| R5-S8 | clarity | medium | Specify the checksum computation inputs and algorithm for staleness detection | Phase 4 Step 2 references "current seed's checksum" but doesn't specify what's hashed (entire seed JSON? specific fields? canonical form?) or the algorithm. Different implementations could produce incompatible checksums, breaking cross-version staleness detection. | Phase 4 Step 2: specify algorithm (SHA-256), inputs (canonical JSON of entire seed), and implementation location (upstream provider or Prime Contractor computes on load) | Integration test: serialize seed, compute checksum, deserialize, recompute; verify identical |
| R5-S9 | maintainability | medium | Add explicit module boundaries and import direction rules | The plan introduces `context_resolution.py` importing from `prime_contractor.py` (for SeedContext, ExecutionMode), while `prime_contractor.py` imports from `context_resolution.py` (for strategies). This bidirectional dependency risks circular imports. The dependency direction should be explicit. | Phase 2 Files section: add import dependency diagram showing allowed import directions; consider extracting shared types to `types.py` to break cycles | Static analysis: verify no circular imports; import graph is acyclic |
| R5-S10 | testability | medium | Define acceptance criteria for "byte-identical" claim in Phase 2 Step 2 | Phase 2 requires `StandaloneContextStrategy.resolve_task_context()` to produce output "byte-identical" to current code. Given dict ordering variations across Python versions and potential whitespace differences, this is unverifiable as stated. Clarify scope: structural equivalence? JSON serialization equivalence? | Phase 2 Step 2: replace "byte-identical" with "structurally equivalent: identical keys, identical values, order-independent comparison via `dict.__eq__`" | Test uses dict equality, not string/byte comparison; explicitly ignores key ordering |

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | completeness | high | REQ-PEM-004 references ValidationConfig but doesn't define it | The ContextResolutionStrategy protocol returns `ValidationConfig` from `resolve_validation_config()`, but this type is never specified. Without knowing the structure (validators list, severity levels, skip conditions), implementations cannot satisfy the protocol. | REQ-PEM-004 or new REQ-PEM-004a: add ValidationConfig dataclass definition with fields like `validators: List[ValidatorCallable]`, `fail_on_warning: bool`, `skip_validators: List[str]` | Review: ValidationConfig has complete field specification; implementers can satisfy protocol without guessing |
| R5-F2 | clarity | high | REQ-PEM-007 resolve_task_context structure lacks field optionality specification | The pipeline context structure lists 8 enriched sections but doesn't specify which are mandatory vs. optional when data is present. Should `protocol_guidance` be omitted entirely if `service_metadata` is empty, or included with placeholder text? | REQ-PEM-007: for each structured section, specify: "MUST include if [condition], otherwise MUST omit" or "MUST include with [default] if data absent" | Implementation review: verify each section follows specified presence/absence rules |
| R5-F3 | testability | medium | REQ-PEM-006 "byte-identical" acceptance criterion is unverifiable | The requirement states "Output is byte-identical to current behavior" but LLM outputs are non-deterministic and dict serialization order varies. This criterion cannot be tested as written. Should specify structural equivalence for context building (pre-LLM) vs. behavioral equivalence for full workflow. | REQ-PEM-006 acceptance criteria: replace "byte-identical" with "structurally equivalent: resolve_task_context() produces dict with identical keys and values (order-independent) for identical inputs" | Unit test compares dicts using equality, not serialized bytes |
| R5-F4 | architecture | medium | REQ-PEM-012 manifest schema version lacks migration/compatibility requirements | The manifest includes `schema_version: "1.0.0"` but no requirements specify how to handle version mismatches (newer manifest read by older code, or vice versa). This will cause failures when schema evolves. | REQ-PEM-012: add acceptance criterion "System MUST handle manifests with unknown schema versions by: [logging warning and skipping staleness check / failing with descriptive error / attempting best-effort parse]" | Test: create manifest with version "2.0.0", verify defined handling behavior |
| R5-F5 | clarity | medium | REQ-PEM-003 ModeConfig lacks specification for OTel span behavior | The behavior table in REQ-PEM-003 lists 7 behaviors but REQ-PEM-011 mentions "OTel spans: Only if instrumentor configured (STANDALONE) / Yes (PIPELINE)" which isn't in ModeConfig. Either OTel is controlled by ModeConfig (add field) or it's external (clarify in REQ-PEM-011). | REQ-PEM-003: add `emit_otel_spans: bool` to ModeConfig or clarify in REQ-PEM-011 that OTel configuration is independent of ModeConfig | Review: OTel behavior is traceable to exactly one configuration source |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---------------------|--------------|----------|------|
| REQ-PEM-001: ExecutionMode Enum | Phase 1 Step 1 | Full | None |
| REQ-PEM-002: Mode Auto-Detection | Phase 1 Step 6 | Full | None |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1 Step 2 | Partial | OTel span behavior not in ModeConfig; behavior table rows not individually identified |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1 Step 4, Phase 2 | Partial | ValidationConfig type undefined in plan |
| REQ-PEM-005: SeedContext Dataclass | Phase 1 Step 3 | Full | None |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2 Step 2 | Full | "byte-identical" unverifiable (see R5-S10) |
| REQ-PEM-007: PipelineContextStrategy | Phase 2 Steps 3, 5 | Partial | Transformation rules for formatted context undefined; field optionality unspecified |
| REQ-PEM-008: Spec-to-Draft Validation | NOT COVERED | None | Plan "Untouched Files" excludes lead_contractor_workflow.py where REQ-PEM-008 must be implemented |
| REQ-PEM-009: Unified Feature Loading | Phase 3 Step 1 | Full | None |
| REQ-PEM-010: Standalone Feature Construction | Phase 3 Step 2 | Full | None |
| REQ-PEM-011: Mode-Specific Output | Phase 4 Steps 1, 4 | Full | None |
| REQ-PEM-012: Generation Manifest | Phase 4 Step 1 | Partial | Schema version migration strategy undefined |
| REQ-PEM-013: Staleness Detection | Phase 4 Step 2 | Partial | Checksum algorithm/inputs unspecified |
| REQ-PEM-014: Validation Results in Output | Phase 4 Step 3 | Full | None |
| REQ-PEM-015: Zero-Change Standalone | Phase 1-5 Commit Gates | Full | None |
| REQ-PEM-016: Script Compatibility | Phase 5 Steps 1-2 | Full | None |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1 Step 5 | Full | None |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F1 (Round R3): The `find_missing_parameters()` function is referenced in REQ-PEM-007 and REQ-PEM-008 but never defined — this is a blocking gap for spec-to-draft validation implementation.
- R4-F3 (Round R4): Critical gap — the plan explicitly excludes `lead_contractor_workflow.py` but REQ-PEM-008 requires spec-to-draft validation logic in that file; this requirement has zero plan coverage.
- R3-F3 (Round R3): Staleness detection tests #15-16 cannot be implemented without a fixture generation strategy for deterministic checksums.

#### Review Round R6
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 20:23:35 UTC
- **Scope**: Architecture-focused review
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | architecture | critical | Correct the implementation plan's "Untouched Files" list, which incorrectly includes `lead_contractor_workflow.py` and omits the work required by REQ-PEM-008. | The plan explicitly states `lead_contractor_workflow.py` is untouched, but REQ-PEM-008 mandates adding spec-to-draft validation logic within that specific workflow. This is a critical gap where a P2 requirement is completely missing from the implementation plan. This was noted in accepted suggestion R6-F3 but never integrated into the plan. | Modify the "Untouched Files" table and add a new step in Phase 4 or 5 to implement the spec completeness check in `lead_contractor_workflow.py`. | The implementation plan is updated to include a task for REQ-PEM-008, and test cases #9 and #10 from the requirements are explicitly covered. |
| R6-S2 | maintainability | high | Decompose the monolithic `PipelineContextStrategy.resolve_task_context` method into a set of smaller, single-purpose context block builders. | As written, this method will assemble 8+ context sections, making it a future maintenance bottleneck that violates the Single Responsibility Principle. A better design uses a Builder or Chain of Responsibility pattern where each context block (e.g., `ArchitecturalContextBuilder`) is a small, independently testable class, orchestrated by the main strategy. | In Phase 2, instead of one large method, define a pattern where `PipelineContextStrategy` composes and calls a series of smaller `ContextBlockBuilder` objects. | Each context block builder has its own unit tests, and the main strategy test verifies the correct orchestration of builders. |
| R6-S3 | testability | high | Abstract filesystem I/O for the generation manifest behind a `ProvenanceStore` protocol. | Phase 4's staleness detection logic directly reads/writes `generation-manifest.json`, coupling the core workflow to the filesystem. This makes unit testing slow and complex. Abstracting I/O allows using an `InMemoryProvenanceStore` for fast, dependency-free unit tests of the staleness logic. | In Phase 4, introduce a `ProvenanceStore` protocol and have the workflow use it. The default implementation will be a `FileSystemProvenanceStore`. | Unit tests for staleness detection (Tests #15, #16) are written against an in-memory mock store, removing any dependency on disk I/O. |
| R6-S4 | clarity | high | Formalize the `SeedContext` state lifecycle, explicitly defining when it transitions from mutable (during setup) to immutable (during execution). | The plan resolves the immutability conflict by allowing setters, but it's unclear when modifications should cease. This ambiguity risks bugs where context is modified mid-workflow. The design should explicitly "finalize" or "freeze" the context after initial loading. | Add a step in Phase 5, where `workflow.load_seed_context()` is called, to document that this method finalizes the context. The implementation could enforce this by replacing the mutable `SeedContext` with a frozen copy. | Add a test that attempts to call a property setter on the workflow after the main execution loop has begun and asserts that it raises an `IllegalStateError`. |
| R6-S5 | testability | medium | Mandate a parameterized test suite for the complex matrix of CLI flags and their effect on the final `ModeConfig`. | The interaction between the default mode, auto-detection, explicit `--mode`, and behavioral overrides (`--validate`, `--no-validate`) creates many permutations. A single "happy path" test is insufficient. A parameterized test is needed to exhaustively verify this critical configuration logic. | Add a new test to Phase 5's test plan: "Parameterized test for `ModeConfig` derivation from all CLI flag combinations". | The test suite includes cases for `(cli_args, seed_type, expected_config)` and verifies that the workflow is initialized with the correct `ModeConfig` in each case. |
| R6-S6 | architecture | medium | Make the pipeline mode auto-detection signals declarative rather than hardcoded in the workflow. | The current design hardcodes the list of "pipeline signals" inside the `_detect_mode()` method. This creates a maintenance burden, requiring a code change every time a new signal is added. A better architecture would load these signals (e.g., a list of JSONPaths) from a configuration file. | In Phase 1, modify `_detect_mode()` to iterate over a configurable list of signal definitions instead of a hardcoded if/elif chain. | Add a test that modifies the signal configuration at runtime (without changing code) and verifies that the auto-detection behavior changes accordingly. |
| R6-S7 | maintainability | medium | Refactor `ModeConfig` from a dataclass with hardcoded fields to a more generic, key-value configuration object to avoid future SRP violations. | The `ModeConfig` dataclass directly couples the configuration object's schema to the set of currently known behaviors. As new mode-dependent behaviors are added, this class will constantly grow. A generic config object (e.g., backed by a dict with schema validation) is more extensible and maintainable. | In Phase 1, replace the `ModeConfig` dataclass with a class that provides methods like `get_bool('run_validators')` and loads its data from a dictionary, decoupling the class from the specific configuration keys. | A new mode-dependent behavior is added to the system, which only requires a configuration change and no modification to the `ModeConfig` class itself. |
| R6-S8 | clarity | medium | Remove the redundant `structured_context` flag from `ModeConfig` and clarify that the choice of `ContextResolutionStrategy` IS the policy for context structure. | The plan introduces a `structured_context` flag in `ModeConfig` and also a `PipelineContextStrategy` whose sole purpose is to create structured context. This creates a confusing dual-control mechanism. The choice of strategy should be the single source of truth for how context is structured. | In Phase 1 and 2, remove the `structured_context` flag from `ModeConfig`. The decision to use structured context is made entirely by selecting the `PipelineContextStrategy`. | The implementation of `PipelineContextStrategy` does not contain any conditional logic based on a `structured_context` flag; its behavior is inherent to the class. |
| R6-S9 | architecture | high | Add a `ContextSanitizer` stage to the pipeline context resolution to prevent accidental leakage of sensitive data into logs and manifests. | The plan introduces extensive logging and a detailed `generation-manifest.json`, which will include data from the seed. If the seed contains sensitive information (e.g., API keys in `service_metadata`), it will be leaked. This is a second-order security risk. | Add a new step to `PipelineContextStrategy.resolve_seed_context` in Phase 2 to pass the context through a sanitizer that redacts known sensitive fields before it is stored or logged. | Create a test seed containing a known sensitive key (e.g., `service_metadata.api_key`). Verify that the key's value is redacted in the `generation-manifest.json` and in verbose log output. |
| R6-S10 | testability | medium | Introduce "Context Snippet" builder fixtures to simplify the setup for testing `PipelineContextStrategy`. | Testing the `PipelineContextStrategy` requires constructing complex `SeedContext` and `FeatureSpec` objects. This makes test setup verbose and brittle. A test fixture system (e.g., `build_seed_context(with_rest_api=True)`) would make tests more readable and maintainable by abstracting away the boilerplate. | In Phase 2, as part of `tests/unit/contractors/test_context_resolution.py`, create a `conftest.py` with helper functions or fixtures for building test-specific context objects. | Tests for the pipeline strategy are rewritten using the new fixtures, and the resulting test code is significantly shorter and more focused on the specific behavior being tested. |

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-F1 | consistency | critical | Reconcile the conflicting acceptance criteria in REQ-PEM-005 stating `SeedContext` is "immutable thereafter" with REQ-PEM-017's requirement for working property setters. | The requirements document is internally inconsistent. While the implementation plan found a workaround, the requirements themselves should not contain direct contradictions. One of these requirements must be rephrased to reflect the intended (mutable-during-setup) behavior. | Update the acceptance criteria of REQ-PEM-005 to clarify the lifecycle: "is populated once during workflow initialization and is treated as immutable after the execution phase begins." | The text of the two requirements is no longer contradictory. |
| R6-F2 | clarity | high | In REQ-PEM-007, specify the behavior for handling context fields that are present but empty (e.g., `service_metadata: {}`). | The requirement is ambiguous. It's unclear if an empty but present field should result in an empty "## Protocol Guidance" section in the prompt (which adds noise) or if the section should be omitted entirely. Explicitly requiring omission for empty data will improve prompt quality. | Add an acceptance criterion to REQ-PEM-007: "Context sections for which the source data is present but empty (e.g., an empty dictionary or list) MUST be omitted from the final `gen_context`." | A test using a seed with `service_metadata: {}` verifies that the `protocol_guidance` key is absent from the `gen_context` dictionary. |
| R6-F3 | completeness | high | Add requirements for handling I/O errors during the writing of the `generation-manifest.json` file in REQ-PEM-012. | The manifest is a critical output for pipeline integration, but the requirements do not specify what should happen if writing the file fails (e.g., disk full, permissions error). This could lead to silent failures or unhandled exceptions. The behavior (fail workflow vs. log warning) must be defined. | Add an acceptance criterion to REQ-PEM-012: "A failure to write `generation-manifest.json` due to an I/O error MUST be logged as an error but MUST NOT cause the entire workflow to fail." | A test uses a mock to raise an `IOError` during the manifest write operation and verifies that an error is logged and the workflow completes with a non-zero exit code but without an unhandled exception. |
| R6-F4 | ambiguity | critical | Define the `ValidationConfig` type referenced in REQ-PEM-004. | The `ContextResolutionStrategy` protocol requires a method `resolve_validation_config` that returns a `ValidationConfig` object. However, this type is never defined in the requirements or the implementation plan, making the protocol's signature incomplete and unimplementable as specified. | Add a definition for `ValidationConfig` near REQ-PEM-004, specifying its structure (e.g., a `TypedDict` or `dataclass` containing a list of validator callables and their configurations). | The implementation in Phase 2 includes a concrete `ValidationConfig` class definition that matches the new specification. |

#### Requirements Coverage
| Feature Doc Section | Plan Step(s) | Coverage | Gaps / Notes |
|---|---|---|---|
| REQ-PEM-001: ExecutionMode Enum | Phase 1 | Full | Covered by `ExecutionMode` enum and `ModeConfig` dataclass. |
| REQ-PEM-002: Mode Auto-Detection | Phase 1, Phase 5 | Full | Covered by `_detect_mode()` method and CLI wiring. |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1, Phase 5 | Full | Covered by `ModeConfig` and CLI overrides. |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1 | Full | Protocol defined in `protocols.py`. R6-F4 notes `ValidationConfig` is undefined. |
| REQ-PEM-005: SeedContext Dataclass | Phase 1 | Full | `SeedContext` dataclass replaces instance attributes. |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2 | Full | Logic extracted from existing code into the new strategy class. |
| REQ-PEM-007: PipelineContextStrategy | Phase 2 | Full | New strategy implements all specified context-building logic. |
| REQ-PEM-008: Spec-to-Draft Validation | **None** | **None** | **Critical Gap.** Plan's "Untouched Files" list explicitly and incorrectly excludes the file (`lead_contractor_workflow.py`) that this requirement must modify. (See R6-S1). |
| REQ-PEM-009: Unified Feature Loading | Phase 3 | Full | Covered by `FeatureQueue` hardening. |
| REQ-PEM-010: Standalone Feature Construction | Phase 3 | Full | Covered by new `add_feature()` convenience method. |
| REQ-PEM-011: Mode-Specific Output | Phase 4 | Full | Handled by checks against `mode_config` before writing outputs. |
| REQ-PEM-012: Generation Manifest | Phase 4 | Full | Implemented as part of the pipeline-mode output contract. |
| REQ-PEM-013: Staleness Detection | Phase 4 | Full | Implemented as part of the pipeline-mode output contract. |
| REQ-PEM-014: Validation Results in Output | Phase 4 | Full | Validation hookpoint collects results for inclusion in manifest. |
| REQ-PEM-015: Zero-Change Standalone | Phase 1-5 | Full | Core principle of the phased rollout and verified by commit gates. |
| REQ-PEM-016: Script Compatibility | Phase 5 | Full | All specified CLI flags are added to the runner script. |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1 | Full | Property accessors are added to delegate to `SeedContext`. |

#### Review Round R7

- **Reviewer**: claude-4 (claude-opus-4-5)
- **Date**: 2026-02-20 21:20:47 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | architecture | high | Define the contract between `CodeGenerator.generate()` return value and manifest's per-feature `model` field | Phase 4 Step 1 states the manifest includes per-feature `model` captured from `CodeGenerator.generate()` return value, but the plan doesn't modify `CodeGenerator` or define what this return value looks like. The existing generator may not expose model info, creating an unstated dependency on generator interface changes. | Phase 4 Step 1, add: "Prerequisite: `CodeGenerator.generate()` MUST return or expose the model spec used (e.g., `anthropic:claude-sonnet-4-20250514`). If unavailable, use `"unknown"`." | Code review confirms generator interface change or graceful fallback |
| R7-S2 | completeness | high | Phase 2 `context_formatters.py` referenced but not specified in implementation plan | Phase 2 mentions "Per-section formatter functions (JSON→Markdown)" and references `context_formatters.py` in the Additionally Modified Files table, but no implementation step describes creating this module, its functions, or their signatures. This is a gap between the file inventory and the implementation steps. | Phase 2 Steps, add: "Extract architectural context transformation to `context_formatters.py` with per-section formatter functions (e.g., `format_architectural_context(data: dict) -> str`) for testability and reuse." | File inventory matches implementation steps; formatters have dedicated tests |
| R7-S3 | security | high | `VALIDATOR_REGISTRY` lookup lacks specification for handling unknown validator names | Phase 2 Step 3 defines `VALIDATOR_REGISTRY` dict mapping names to validators, but doesn't specify behavior when `feature.metadata` requests a validator name not in the registry. Silent skip? Warning? Error? This affects both security (injection of unknown names) and debuggability. | Phase 2 Step 3, add: "Unknown validator names from seed metadata MUST be logged as warnings and skipped, NOT dynamically loaded. Registry is code-defined only." | Test: seed with unknown validator name logs warning, does not crash or load external code |
| R7-S4 | testability | high | Phase 4 staleness detection tests (#16-#17) lack determinism strategy for checksum comparison | Tests specify "matching checksum reuses" but the plan doesn't explain how to create test fixtures with known, stable checksums. JSON serialization order affects checksums, and without canonical JSON (sorted keys), tests could be flaky. | Phase 4 Tests, add: "Use deterministic test fixtures with pre-computed checksums. Checksum is SHA-256 over canonical JSON (sorted keys, no whitespace)." | Staleness tests pass consistently across multiple runs without flakiness |
| R7-S5 | architecture | medium | Module import direction rules missing from plan despite cross-module dependencies | Phase 2 creates `context_resolution.py` importing from `protocols.py` and `queue.py`, but no rule prevents circular imports if `prime_contractor.py` imports back. The plan should specify import direction to prevent cycles during implementation. | Phase 2, add subsection "Module Import Direction": "`protocols.py` → no imports from prime_contractor; `context_resolution.py` → imports from protocols, queue; `prime_contractor.py` → imports from protocols, context_resolution" | CI lint or manual review confirms no circular imports |
| R7-S6 | maintainability | medium | Error handling contract for `ContextResolutionStrategy` methods is undefined | The plan specifies what each strategy method returns but not what happens on errors. Does `resolve_seed_context()` raise on schema validation failure? Does `resolve_task_context()` return partial context on file read error? Undefined error handling leads to inconsistent implementations. | Phase 2, add to protocol definition: "Error handling: `resolve_seed_context()` raises `ValueError` on schema validation failure; `resolve_task_context()` raises `RuntimeError` on template failures; `resolve_validation_config()` returns empty config on any error (validators are best-effort)." | Unit tests verify each error path produces specified exception/behavior |
| R7-S7 | completeness | medium | Phase 5 flag conflict detection missing implementation detail | REQ-PEM-016 specifies `--validate` + `--no-validate` must raise CLI error, and REQ-PEM-014 adds `--strict-validation` + `--no-validate` as conflicting. Phase 5 mentions "Conflict detection" but doesn't specify where/how this is implemented (argparse mutual exclusion? post-parse validation?). | Phase 5 Step 1, add: "Use argparse mutually exclusive groups or post-parse validation to detect conflicting flags. Conflicting combinations: [`--validate`, `--no-validate`], [`--strict-validation`, `--no-validate`]." | Test: conflicting flags produce user-friendly error message and non-zero exit |
| R7-S8 | testability | medium | Parameterized test strategy for CLI flag × ModeConfig combinations not specified | Phase 5 tests cover individual flags but the combinatorial space (6+ flags × 2 modes × various ModeConfig states) creates explosion. Plan should specify parameterized testing strategy to ensure coverage without exponential test count. | Phase 5 Tests, add: "Use parameterized test suite (pytest.mark.parametrize) for CLI flag × ModeConfig combinations. Cover: each flag in isolation, known conflict pairs, mode override scenarios." | Test coverage report shows flag combinations without 2^n individual tests |
| R7-S9 | architecture | medium | `SeedContext.execution_mode` vs `workflow.mode` synchronization mechanism undefined | REQ-PEM-005 states both must stay synchronized, but the plan doesn't specify how. Is `SeedContext.execution_mode` derived from `workflow.mode` on serialization? Set once at construction? Property that delegates? This affects state persistence and resume. | Phase 1 Step 3, add: "`SeedContext.execution_mode` is for serialization/round-trip; `workflow.mode` is the runtime authority. On `SeedContext` construction, set `execution_mode = workflow.mode`. On resume, `workflow.mode` is restored from persisted state." | Test: serialize/deserialize SeedContext maintains mode; resume uses persisted mode |
| R7-S10 | security | medium | Generation manifest file permissions not specified for pipeline mode | REQ-PEM-012 requires manifest for provenance but doesn't specify file permissions. In pipeline deployments, the manifest contains cost data that may be sensitive. Default permissions could expose this data. | Phase 4 Step 1, add: "Write `generation-manifest.json` with 0o600 permissions (owner read/write only) to protect cost data in multi-user pipeline environments." | Manifest file created with expected permissions; test verifies mode bits |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R8-S1: The seed checksum validation on resume is a critical integrity check that complements mode persistence — without it, a modified seed could produce inconsistent state during resume.
- R8-S4: Enforcing SeedContext immutability with a RuntimeError is stronger than "undefined behavior" and aligns with the lifecycle constraint in REQ-PEM-005.
- R8-S5: The system prompt instruction to treat delimited content as non-instructional is essential for the prompt injection mitigation to be effective — wrapping alone is insufficient.
- R8-S9: Recording `force_regenerate` in the manifest is important provenance information that explains why cache was bypassed.

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-F1 | completeness | high | REQ-PEM-012 manifest schema lacks per-feature `model` field data flow specification | The manifest example shows `"model": "anthropic:claude-sonnet-4-20250514"` per feature, but requirements don't specify how this data flows from the generator. Is it returned by `CodeGenerator.generate()`? Read from config? This creates implementation ambiguity. | REQ-PEM-012, add: "Per-feature `model` field MUST be populated from the `CodeGenerator.generate()` return value. Generator implementations MUST expose the model spec used." | Review confirms generator interface returns model info |
| R7-F2 | consistency | medium | REQ-PEM-007 architectural context "formatted not raw JSON" lacks transformation specification | Requirements state architectural_context should be "formatted, not raw JSON" but don't define the transformation. Is it Markdown? Prose? The implementation plan adds detail but requirements should be self-contained. | REQ-PEM-007, add: "Raw JSON architectural_context MUST be transformed to Markdown: top-level keys → headers, arrays → bullet lists, nested objects → indented sub-sections." | Transformation is fully specified in requirements |
| R7-F3 | testability | medium | REQ-PEM-006 "byte-identical" acceptance criterion conflicts with dict ordering variability | Requirements state "Output is byte-identical to current behavior" but Python dicts don't guarantee order. The implementation plan addresses this with "structurally equivalent" but the requirements text remains ambiguous. | REQ-PEM-006, change: "Output is byte-identical" → "Output is structurally equivalent (identical dict keys and values, order-independent comparison)" | Acceptance criterion is testable without false negatives from ordering |
| R7-F4 | completeness | medium | REQ-PEM-018 path traversal protection lacks specification of the sanitization function | Requirements mandate path validation but don't specify the mechanism. "Uses the existing `sanitize_path()` utility" references code that may not exist or may have different semantics. | REQ-PEM-018, add: "Path sanitization MUST resolve symlinks and verify the canonical path is within project root. Paths containing `..` or symlinks escaping root MUST be rejected." | Security test suite covers path traversal edge cases |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
| --- | --- | --- | --- |
| REQ-PEM-001: ExecutionMode Enum | Phase 1 Step 1 | Full | None |
| REQ-PEM-002: Mode Auto-Detection | Phase 1 Step 6 | Full | None |
| REQ-PEM-003: Mode-Specific Configuration | Phase 1 Step 2 | Full | None |
| REQ-PEM-004: ContextResolutionStrategy Protocol | Phase 1 Step 4, Phase 2 Step 1 | Partial | Protocol defined but error handling contract undefined |
| REQ-PEM-005: SeedContext Dataclass | Phase 1 Step 3 | Partial | `execution_mode` vs `workflow.mode` sync mechanism not specified |
| REQ-PEM-006: StandaloneContextStrategy | Phase 2 Step 2 | Full | None |
| REQ-PEM-007: PipelineContextStrategy | Phase 2 Step 3 | Partial | `context_formatters.py` referenced but not implemented in steps |
| REQ-PEM-008: Spec-to-Draft Validation | Phase 2 (Additionally Modified Files) | Partial | Listed in file inventory but no implementation step |
| REQ-PEM-009: Unified Feature Loading | Phase 3 Step 1 | Full | None |
| REQ-PEM-010: Standalone Feature Construction | Phase 3 Step 2 | Full | None |
| REQ-PEM-011: Mode-Specific Output | Phase 4 Step 1-3 | Full | None |
| REQ-PEM-012: Generation Manifest | Phase 4 Step 1 | Partial | Model field data source unspecified; file permissions unspecified |
| REQ-PEM-013: Staleness Detection | Phase 4 Step 2 | Partial | Test determinism strategy for checksums not specified |
| REQ-PEM-014: Validation Results in Output | Phase 4 Step 3 | Full | None |
| REQ-PEM-015: Zero-Change Standalone | Phase 1 Commit gate | Full | None |
| REQ-PEM-016: Script Compatibility | Phase 5 Steps 1-3 | Partial | Flag conflict detection mechanism not specified |
| REQ-PEM-017: Property Accessor Compatibility | Phase 1 Step 5 | Full | None |
| REQ-PEM-018: Secure Input Handling | Phase 2 Step 3 (partial) | Partial | VALIDATOR_REGISTRY unknown name handling not specified |

#### Review Round R8
- **Reviewer**: gemini-2.5 (gemini-2.5-pro)
- **Date**: 2026-02-20 21:21:54 UTC
- **Scope**: Architecture-focused review

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-S1 | security | critical | Implement state file locking mechanism from REQ-PEM-018. | The plan completely omits the mandatory requirement for state file locking (`fcntl.flock` or equivalent). Without this, concurrent workflow executions targeting the same output directory could lead to state file corruption, causing unpredictable resume behavior or data loss. | Add a new step in Phase 1 to wrap state file I/O with a file-locking mechanism. | A test case attempts to run two workflows concurrently against the same state file; it must demonstrate that one process blocks until the other releases the lock, preventing corruption. |
| R8-S2 | completeness | high | Plan for changes to the `CodeGenerator` protocol to support cost reporting. | The plan states the manifest's `cost_usd` field is "captured from `CodeGenerator.generate()` return value" (Phase 4), but no steps are included to modify the `CodeGenerator` protocol or its implementations to return this cost data. This is a critical unaddressed dependency. | Add a step to Phase 4 to modify the `CodeGenerator` protocol to return a tuple of `(generated_code, metadata: dict)` where metadata includes cost and model info. Update mock generators for testing. | Unit tests for `_generate_code` verify that the cost and model information returned by a mock generator are correctly propagated to the `feature_result` and later to the manifest. |
| R8-S3 | scalability | medium | Define the validator lifecycle to avoid redundant initializations. | The plan implies validators are resolved per-feature via `resolve_validation_config`. If a validator requires expensive setup (e.g., loading a large data model), this per-feature resolution is inefficient. The design should clarify if validators are instantiated once per workflow or on-demand. | Add a design note to Phase 4 specifying that the `ContextResolutionStrategy` should cache validator instances for the lifetime of the workflow to prevent re-initialization for each feature. | A test with a mock validator that logs its `__init__` call is run against multiple features; the test asserts that `__init__` is called only once. |
| R8-S4 | completeness | high | Implement the `RuntimeError` check for property setters used after execution begins. | REQ-PEM-017 mandates that property setters must raise a `RuntimeError` if called after execution starts. The plan only mentions "treated as immutable" which is a convention, not an enforcement. This is a failure to meet a mandatory requirement. | Add a step to Phase 1: `PrimeContractorWorkflow` must set an internal flag (e.g., `self._execution_started = True`) at the beginning of the `run()` method. Property setters must check this flag and raise `RuntimeError` if it is set. | Add Test #34 from the requirements doc to the plan: A test calls a property setter after the workflow has started processing features and asserts that a `RuntimeError` is raised. |
| R8-S5 | architecture | medium | Define the interaction between `load_seed_context()` and seedless `add_feature()`. | The plan introduces two initialization paths: one from a seed file, another programmatically. It's unclear what happens if a user mixes these calls (e.g., `add_feature()` then `load_seed_context()`). This ambiguity could lead to inconsistent or overwritten `SeedContext`. | Add a design note to Phase 3 clarifying the state machine: `load_seed_context()` can only be called once, before any calls to `add_feature()`. Subsequent calls should raise an `InvalidStateError`. | A test attempts to call `load_seed_context` after `add_feature` and asserts that the specified error is raised. |
| R8-S6 | clarity | medium | Specify the `source_checksum` computation logic within the implementation plan. | The plan mentions the checksum is used but is vague on the implementation details. For this critical feature to be correct, the plan must specify *when* it's computed (e.g., inside `load_seed_context`), *from what* (the raw JSON string, not the parsed dict), and how the raw input is obtained. | Add a note to Phase 1, Step 5, clarifying that `load_seed_context` should accept the raw seed file content as an optional argument to compute the checksum before parsing, ensuring a canonical hash. | A test verifies that loading a seed from a file and from a pre-read string produces the identical `source_checksum` in `SeedContext`. |
| R8-S7 | security | medium | Re-evaluate the read-path security model for `generation-manifest.json`. | The plan mandates 0o600 permissions to protect sensitive cost data. However, this may prevent legitimate, less-privileged downstream services from reading the manifest for staleness checks. This creates an operational conflict between security and functionality. | Add a risk assessment item in the plan: "Manifest permissions (0o600) may block downstream readers. Mitigation: Consider splitting cost data into a separate, more restricted file, leaving the main manifest readable by the pipeline group." | An integration test simulates a downstream process running as a different user (but same group) and verifies it can successfully read the manifest for staleness checks. |
| R8-S8 | clarity | low | Clarify the meaning of "Template rendering failures" in the strategy's error handling contract. | The Phase 1 error contract for `resolve_task_context()` mentions "Template rendering failures raise `RuntimeError`". However, the plan describes this method as building a dictionary, not rendering templates. This language is confusing and likely incorrect. | Update the error contract in Phase 1 to be more precise: "Failures during context transformation (e.g., in `context_formatters.py`) raise `ValueError`." | Unit tests for `context_formatters.py` verify that malformed input data raises the specified exception. |

#### Feature Requirements Suggestions
| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R8-F1 | ambiguity | high | Clarify the schema for `validator_results` in the `generation-manifest.json`. | REQ-PEM-012's manifest example (`"validator_results": { "...": "pass|warn|fail" }`) is a simple summary, which conflicts with the `ValidationResult` type in REQ-PEM-004 that includes a `findings: List[str]`. Downstream consumers need to know if they will receive the full findings or just the outcome. | Update the JSON schema example in REQ-PEM-012 to reflect the full `ValidationResult` structure, or explicitly state that only the summary outcome is stored. | The acceptance criteria for REQ-PEM-012 should be updated to require a test that validates the manifest against the clarified, more detailed schema. |
| R8-F2 | completeness | medium | The `generation-manifest.json` schema in REQ-PEM-012 should support multiple models per feature. | The schema allows a single string for the `model` field. A complex feature might use different models for different stages (e.g., planning vs. coding). The current schema cannot accurately capture this provenance. | Modify the `model` field in the REQ-PEM-012 schema to be a `Dict[str, str]` (e.g., `{"coder": "model-a", "reviewer": "model-b"}`) or a `List[str]`. | A test for a feature that uses two mock models verifies that both model identifiers are correctly recorded in the manifest. |
| R8-F3 | testability | medium | The definition of when "execution begins" in REQ-PEM-017 is not precise enough to be testable. | The requirement to raise a `RuntimeError` for property setters used after execution begins depends on a clear, non-ambiguous definition of that event. "After execution begins" is a concept, not a specific event. | Add a sentence to REQ-PEM-017: "For the purpose of this requirement, 'execution begins' is defined as the first invocation of the internal `_generate_code()` method." | A test case can now be written to deterministically call a setter immediately before and immediately after the first call to `_generate_code` and assert the specified behavior. |

#### Requirements Coverage

| Feature Doc Section | Plan Step(s) | Coverage | Gaps |
|---|---|---|---|
| REQ-PEM-001–003 (Layer 1: Mode) | Phase 1, Phase 5 | Full | None. |
| REQ-PEM-004–008 (Layer 2: Context) | Phase 1, Phase 2 | Full | None. |
| REQ-PEM-009–010 (Layer 3: Loading) | Phase 3 | Full | None. |
| REQ-PEM-011–014 (Layer 4: Output) | Phase 4 | Partial | Plan omits the necessary changes to the `CodeGenerator` protocol required to provide the cost data for the manifest (REQ-PEM-012). |
| REQ-PEM-015–017 (Layer 5: Compat) | Phase 1, Phase 5, Commit Gates | Partial | Plan omits implementation of the `RuntimeError` check required by REQ-PEM-017 for property setters used after execution begins. |
| REQ-PEM-018 (Layer 6: Security) | Phase 2, Phase 4 | Partial | Plan completely omits the state file locking mechanism required by REQ-PEM-018. |
