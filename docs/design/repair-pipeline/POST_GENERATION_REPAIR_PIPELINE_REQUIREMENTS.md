# Post-Generation Repair Pipeline Requirements

**Document ID:** REQ-RPL
**Version:** 1.0.0
**Status:** Draft
**Author:** Claude (agent-authored)
**Date:** 2026-03-03

---

## 1. Preamble

### 1.1 Purpose

This document specifies a **post-generation repair pipeline** that intercepts checkpoint failures in the Artisan and PrimeContractor code generation workflows, applies targeted deterministic fixes using structured checkpoint diagnostics, and re-validates — only escalating to full LLM regeneration when repair is not cost-effective.

### 1.2 Scope

The repair pipeline sits between checkpoint failure detection and rollback/regeneration in both:

- **PrimeContractor** (`prime_contractor.py`) — feature-level code generation with error-informed retry
- **Artisan Contractor** (`integration_engine.py`) — phase-level IMPLEMENT → INTEGRATE flow

It reuses proven patterns from the micro-prime `repair.py` 7-step pipeline, which already demonstrates non-destructive repair at the element level.

### 1.3 Relationship to Design Principles

**Mottainai (waste elimination):** Generated code that fails checkpoint validation for fixable reasons (syntax errors, missing imports, lint violations) is currently discarded and regenerated from scratch. Each regeneration costs ~$0.50–1.00 in LLM API calls and 10–30 seconds of wall-clock time. Deterministic repair costs ~$0 and <1 second.

**Prime Contractor Paradigm:** The existing `process_feature()` flow already preserves `error_message` across retries (`queue.py:385–392`) and injects it as LLM feedback (`prime_contractor.py:1957–1962`). The repair pipeline adds a deterministic repair step before this LLM-dependent retry, reducing unnecessary API spend.

### 1.4 Current Failure Flow

```
                        CURRENT FLOW
                        ============

  GENERATE ──► MERGE ──► CHECKPOINT ──► fail
                                          │
                              ┌───────────┘
                              ▼
                          ROLLBACK
                              │
                              ▼
                    flatten error_message
                              │
                              ▼
                   re-GENERATE (full LLM call)
                              │
                              ▼
                     MERGE ──► CHECKPOINT ──► pass/fail
```

**Problems with current flow:**

1. Rich checkpoint diagnostics (specific errors, line numbers, module names) are reduced to a flat `error_message` string
2. Fixable issues (markdown fences, missing imports, indent errors) trigger full LLM regeneration
3. No cost tracking distinguishes between repairable vs. non-repairable failures
4. Rollback discards all generated code, even portions that are valid

### 1.5 Proposed Failure Flow

```
                       PROPOSED FLOW
                       =============

  GENERATE ──► MERGE ──► CHECKPOINT ──► fail
                                          │
                              ┌───────────┘
                              ▼
                   ┌──── ROUTE (classify) ────┐
                   │                          │
                   ▼                          ▼
              repairable?              not repairable
                   │                   (test regression)
                   ▼                          │
          REPAIR (staging copy)               │
                   │                          │
                   ▼                          │
            re-CHECKPOINT                     │
                   │                          │
              ┌────┴────┐                     │
              ▼         ▼                     │
            pass      fail                    │
              │         │                     │
              ▼         ▼                     ▼
           ACCEPT   ROLLBACK ──► error-informed REGEN
                        │         (with repair details)
                        ▼
                  tier escalation ──► FAIL
```

### 1.6 Key References

| Asset | Location | Role |
|-------|----------|------|
| 7-step repair pipeline | `src/startd8/micro_prime/repair.py` | Proven repair pattern to lift |
| `RepairStepResult` | `src/startd8/micro_prime/models.py:54–65` | Per-step result model |
| `RepairAttribution` | `src/startd8/micro_prime/models.py:37–52` | Granular attribution |
| Non-destructive guard | `repair.py:470–488` | Before/after AST parse pattern |
| `CheckpointResult` | `contractors/checkpoint.py:46–74` | Structured failure diagnostics |
| `CheckpointStatus` enum | `contractors/checkpoint.py:37–43` | `PASSED`/`FAILED`/`SKIPPED`/`WARNING` |
| `IntegrationCheckpoint` | `contractors/checkpoint.py:76–565` | Syntax, import, lint, test checks |
| `process_feature()` | `prime_contractor.py:1590–1622` | Error-informed retry entry |
| Error-informed retry | `prime_contractor.py:1613–1619` | Current retry with flattened error |
| `develop_feature()` | `prime_contractor.py:1876–1987` | `prior_error` parameter |
| `on_checkpoint_failed` | `prime_contractor.py:2186–2187` | Callback injection point |
| `integrate_feature()` | `prime_contractor.py:2118–2188` | Integration + checkpoint flow |
| `IntegrationEngine` | `contractors/integration_engine.py` | Merge + checkpoint orchestration |
| Size regression guard | `integration_engine.py:932–982` | Threshold-based size check |
| Pre-merge ruff auto-fix | `integration_engine.py:1073–1088` | `ruff check --fix --select=E7,E9,F` |
| Post-merge checkpoint | `integration_engine.py:1093` | `run_all_checkpoints()` |
| Checkpoint failure rollback | `integration_engine.py:1128–1160` | Rollback + result return |

---

## 2. Layer 1: Core Pipeline

The core repair pipeline defines the entry point, data model, execution contract, and re-validation loop.

### REQ-RPL-001: Pipeline Entry Point

**Priority:** P0

The repair pipeline SHALL expose a single entry point:

```python
def run_repair_pipeline(
    files: dict[Path, str],
    checkpoint_result: list[CheckpointResult],
    context: RepairContext,
) -> RepairPipelineResult:
```

This function is invoked after checkpoint failure, **before** rollback. It receives the generated file contents (as a path-to-source mapping), the structured checkpoint results, and a `RepairContext` carrying diagnostic metadata.

**Rationale:** Mirrors the `run_repair_pipeline()` signature in `micro_prime/repair.py:447–464` but operates at file level rather than element level.

### REQ-RPL-002: Checkpoint-to-Repair Routing Table

**Priority:** P0

The pipeline SHALL include a routing table that maps checkpoint failure patterns to ordered sequences of repair steps with confidence levels. The routing table is defined in Section 7 (Routing Table).

The router SHALL:
- Parse `CheckpointResult.errors` to classify failure patterns (syntax, import, lint)
- Select the appropriate repair step sequence based on classification
- Skip repair entirely for non-repairable categories (test regressions)
- Return `RepairRoute` with `steps: list[RepairStep]`, `confidence: Confidence`, and `skip_reason: Optional[str]`

### REQ-RPL-003: Non-Destructive Guarantee

**Priority:** P0

If any repair step causes previously valid code to become invalid, that step's changes SHALL be reverted. This reuses the pattern from `micro_prime/repair.py:470–488`:

1. Before each step: `was_valid = ast_parse(code)`
2. After each step: `is_valid = ast_parse(result.code)`
3. If `was_valid and not is_valid`: revert step (`result.modified = False`, `result.code = original`)

This guarantee operates **per file**: each file's validity is tracked independently.

### REQ-RPL-004: RepairContext Dataclass

**Priority:** P0

A `RepairContext` dataclass SHALL carry structured checkpoint diagnostics (not flat strings):

```python
@dataclass
class RepairContext:
    """Structured checkpoint diagnostics for repair routing."""

    feature_name: str
    checkpoint_results: list[CheckpointResult]
    syntax_errors: list[SyntaxDiagnostic]       # Parsed from checkpoint errors
    import_errors: list[ImportDiagnostic]        # Module name, import path
    lint_violations: list[LintDiagnostic]        # Rule code, file, line
    test_regressions: list[str]                  # Test names (for skip decision)
    project_root: Path
    existing_imports: dict[Path, list[str]]      # Current import map per file
    attempt_number: int                          # For circuit breaker
```

Each diagnostic sub-type (`SyntaxDiagnostic`, `ImportDiagnostic`, `LintDiagnostic`) SHALL be a typed dataclass parsed from the flat error strings in `CheckpointResult.errors`.

**Rationale:** The current flow reduces rich checkpoint output to a flat `error_message` string (`prime_contractor.py:1957–1962`). Structured diagnostics enable precise repair routing.

### REQ-RPL-005: FileRepairResult

**Priority:** P0

Each repaired file SHALL produce a `FileRepairResult`:

```python
@dataclass
class FileRepairResult:
    """Per-file repair outcome with attribution."""

    file_path: Path
    success: bool
    original_code: str
    repaired_code: str
    ast_valid_before: bool
    ast_valid_after: bool
    steps_applied: list[RepairStepResult]       # Reuse from micro_prime/models.py
    attribution: RepairAttribution               # Reuse from micro_prime/models.py
```

The aggregate `RepairPipelineResult` SHALL contain:

```python
@dataclass
class RepairPipelineResult:
    """Aggregate result from the repair pipeline."""

    success: bool                                # All files pass re-checkpoint
    file_results: dict[Path, FileRepairResult]
    recheckpoint_results: list[CheckpointResult] # Re-validation results
    wall_clock_ms: float                         # Total repair time
    skipped_reason: Optional[str]                # If repair was skipped entirely
```

### REQ-RPL-006: Staging Copy

**Priority:** P0

The repair pipeline SHALL operate on **copies** of the generated files, not the originals. Original files remain untouched until re-checkpoint passes.

Implementation:
1. Copy each file to a staging directory (e.g., `.startd8/repair-staging/`)
2. Apply repair steps to staged copies
3. Run re-checkpoint against staged copies
4. If re-checkpoint passes: replace originals with staged copies
5. If re-checkpoint fails: discard staged copies, proceed to escalation

**Rationale:** This mirrors the existing snapshot pattern in `integration_engine.py:421–468` (`_snapshot_target` / `_restore_target`).

### REQ-RPL-007: Repair Step Protocol

**Priority:** P1

Each repair step SHALL implement a callable protocol:

```python
class RepairStep(Protocol):
    """Protocol for individual repair steps."""

    name: str

    def __call__(
        self, code: str, context: RepairContext, file_path: Path
    ) -> RepairStepResult:
        """Apply repair to code, returning modified code and step result."""
        ...
```

Steps are composable and ordered. The pipeline executes them in sequence, with the non-destructive guard (REQ-RPL-003) applied between each step.

### REQ-RPL-008: Re-Checkpoint After Repair

**Priority:** P0

After all repair steps complete, the pipeline SHALL run the **same checkpoint suite** (`IntegrationCheckpoint.run_all_checkpoints()`) against the repaired files:

- **Pass:** Accept repaired files, return `RepairPipelineResult(success=True)`
- **Fail:** Return `RepairPipelineResult(success=False)` with re-checkpoint details for escalation

The re-checkpoint MUST use identical configuration (same lint rules, same test baseline) as the original checkpoint that triggered the repair.

---

## 3. Layer 2: Repair Steps

Individual repair steps that address specific checkpoint failure categories. Steps are ordered from most common/cheapest to most complex.

### REQ-RPL-100: Fence Strip

**Priority:** P0

Remove markdown code fences (`` ```python ``, `` ``` ``) from generated code.

**Reuse:** Lift `_step_fence_strip` from `micro_prime/repair.py:37–53`. Adapt from element-level to file-level operation.

**Trigger:** `SyntaxError` where code starts with `` ``` `` or contains fence patterns.

### REQ-RPL-101: Indent Normalize

**Priority:** P0

Fix mixed tabs/spaces indentation that causes `IndentationError` or `TabError`.

**Reuse:** Lift `_step_indent_normalize` from `micro_prime/repair.py:180–245`. Standardize to 4-space indentation.

**Trigger:** `IndentationError`, `TabError`, or mixed whitespace detected.

### REQ-RPL-102: Import Completion

**Priority:** P0

Add missing imports identified by the checkpoint import check (`IntegrationCheckpoint.check_imports()`, `checkpoint.py:219–300`).

**Reuse:** Lift and extend `_step_import_completion` from `micro_prime/repair.py:340–412`.

**Extensions beyond micro-prime:**
- Parse `ModuleNotFoundError: No module named 'X'` from checkpoint errors to extract module name
- Parse `ImportError: cannot import name 'Y' from 'X'` for specific name imports
- Consult `RepairContext.existing_imports` to avoid duplicate imports
- Handle relative imports within the project package

**Trigger:** `ModuleNotFoundError`, `ImportError` in checkpoint results.

### REQ-RPL-103: Bracket/Paren Balance

**Priority:** P1

Fix unclosed delimiters (`(`, `[`, `{`, and their closing counterparts) from truncated generation.

**Implementation:** Count delimiter pairs; if imbalanced, append/remove closing delimiters at the appropriate scope level using AST-aware insertion (not naive string append).

**Trigger:** `SyntaxError: unexpected EOF while parsing`, `SyntaxError: '(' was never closed`.

### REQ-RPL-104: Duplicate Removal

**Priority:** P2

Detect and remove duplicate function or class definitions that arise from merge conflict artifacts or repeated generation.

**Implementation:**
- Parse AST to find duplicate `def` / `class` names at the same scope level
- Keep the last definition (most likely the intended version)
- Log removed duplicates in `RepairStepResult.metrics`

**Trigger:** `F811 redefinition of unused name` in lint checkpoint results.

### REQ-RPL-105: Extended Lint Fix

**Priority:** P1

Apply `ruff check --fix --unsafe-fixes` for checkpoint-identified lint violations beyond the current `E7,E9,F` selection (`integration_engine.py:1081–1082`).

**Implementation:**
- Parse lint violation codes from `CheckpointResult.errors`
- Run `ruff check --fix --select={codes}` targeting only the identified violations
- Capture ruff's output for attribution

**Trigger:** Lint checkpoint failures with auto-fixable rule codes.

**Constraint:** Only apply to rules that ruff can auto-fix. Non-fixable rules are escalated.

### REQ-RPL-106: AST Validate

**Priority:** P0

Verify the final repaired code parses without `SyntaxError` via `ast.parse()`.

**Reuse:** Lift `_step_ast_validate` from `micro_prime/repair.py:415–428`.

This step runs **last** in every repair sequence as a final gate. It does not modify code — it validates and reports.

---

## 4. Layer 3: PrimeContractor Integration

Integration points within the PrimeContractor workflow.

### REQ-RPL-200: Hook into process_feature()

**Priority:** P0

The repair pipeline SHALL be invoked in `process_feature()` (`prime_contractor.py:1590–1622`) between checkpoint failure detection and rollback.

**Current flow (lines 2185–2188):**
```python
else:
    if result.checkpoint_results and self.on_checkpoint_failed:
        self.on_checkpoint_failed(feature, result.checkpoint_results)
    return False
```

**Proposed flow:**
```python
else:
    if result.checkpoint_results:
        repair_result = self._attempt_repair(feature, result)
        if repair_result and repair_result.success:
            # Repair succeeded — accept without consuming retry
            return True
        # Repair failed or skipped — fall through to existing error path
        if self.on_checkpoint_failed:
            self.on_checkpoint_failed(feature, result.checkpoint_results)
    return False
```

### REQ-RPL-201: Repair Decision Logic

**Priority:** P0

The pipeline SHALL only attempt repair when checkpoint failures are in repairable categories:

| Category | Repairable | Action |
|----------|-----------|--------|
| Syntax errors | Yes | Route to fence_strip → indent_normalize → bracket_balance → ast_validate |
| Import errors | Yes | Route to import_completion → ast_validate |
| Lint violations (auto-fixable) | Yes | Route to extended_lint_fix → ast_validate |
| Lint violations (not auto-fixable) | No | Skip — escalate to regeneration |
| Test regressions | No | Skip — escalate to regeneration |
| Size regression | Conditional | See REQ-RPL-301 |

The decision logic SHALL be configurable via a `repair_enabled: bool` flag (default `True`) and a `repairable_categories: set[str]` configuration.

### REQ-RPL-202: Structured CheckpointDiagnostics

**Priority:** P1

`CheckpointResult` diagnostics SHALL be parsed into structured `RepairContext` rather than flattened to `error_message` string.

**Current pattern** (`prime_contractor.py:1957–1962`):
```python
prior_error_feedback = _fmt_ctx(
    "prime_context", "prior_error_feedback", prior_error=prior_error,
)
```

**Proposed:** Before formatting for LLM retry, parse `CheckpointResult.errors` into typed diagnostics:
- `SyntaxDiagnostic(file, line, col, message)`
- `ImportDiagnostic(module, name, file)`
- `LintDiagnostic(rule, file, line, message, fixable)`

### REQ-RPL-203: Successful Repair Does Not Consume Retry

**Priority:** P1

If the repair pipeline succeeds (re-checkpoint passes), the feature SHALL be marked `COMPLETE` without incrementing `feature.integration_attempts` or consuming a retry slot.

**Rationale:** Deterministic repair is not an "attempt" — it is a correction. Consuming a retry slot for a $0 fix reduces the budget available for genuine LLM-dependent retries.

### REQ-RPL-204: Failed Repair Enriches Retry Context

**Priority:** P1

If repair fails, the repair attempt details SHALL be appended to the error context for the subsequent LLM-informed retry:

```python
error_context = {
    "checkpoint_errors": checkpoint_result.errors,
    "repair_attempted": True,
    "repair_steps_applied": [s.step_name for s in repair_result.steps],
    "repair_steps_failed": [s for s in repair_result.steps if not s.modified],
    "remaining_errors": repair_result.recheckpoint_results,
}
```

This gives the LLM richer context than the current flat `error_message` string, potentially improving regeneration quality.

---

## 5. Layer 4: Artisan Integration

Integration points within the Artisan Contractor workflow.

### REQ-RPL-300: Hook into IMPLEMENT → INTEGRATE Checkpoint Flow

**Priority:** P0

The repair pipeline SHALL hook into `IntegrationEngine.integrate()` at the checkpoint failure point (`integration_engine.py:1128–1160`).

**Current flow (line 1126–1160):**
```
run_all_checkpoints() → summarize_results() → if failed → rollback → return failure
```

**Proposed flow:**
```
run_all_checkpoints() → summarize_results() → if failed →
    route(checkpoint_results) →
    if repairable → repair(staged_copies) → re-checkpoint →
        if pass → accept
        if fail → rollback → return failure (with repair details)
    if not repairable → rollback → return failure
```

**Hook location:** Between `checkpoint.summarize_results(results)` (line 1126) and the rollback block (lines 1142–1148).

### REQ-RPL-301: Size Regression Merge Repair

**Priority:** P1

When the size regression guard (`integration_engine.py:932–982`) blocks a file because `source_lines / target_lines < threshold` (default 0.60), but the generated code is spec-compliant, the repair pipeline SHALL offer a merge-based repair option:

1. Diff the generated file against the target
2. If the generated file is a **subset** of the target (missing sections, not wrong sections), attempt to merge the generated changes into the target rather than replacing it
3. If the generated file contradicts the target, skip repair and escalate

**Confidence:** LOW — this step is advisory and requires human review flag.

### REQ-RPL-302: Extended Pre-Merge Auto-Fix

**Priority:** P1

The existing pre-merge auto-fix (`integration_engine.py:1073–1088`) currently runs only `ruff check --fix --select=E7,E9,F`. The repair pipeline SHALL extend this to:

1. Run the full repair step sequence (fence_strip → indent_normalize → import_completion) **before** the existing ruff auto-fix
2. The existing ruff auto-fix remains as-is (backward compatible)
3. This pre-checkpoint repair is a **best-effort optimization** — if it fixes issues before the checkpoint even runs, the checkpoint passes on the first try

**Configuration:** `pre_checkpoint_repair: bool` (default `False` initially, `True` after validation).

### REQ-RPL-303: Handoff Attribution

**Priority:** P2

Repair actions SHALL be recorded in the Artisan handoff file so downstream phases (TEST, REVIEW, FINALIZE) are aware that code was repaired rather than generated as-is.

Handoff entry format:
```yaml
repairs:
  - file: "src/mymodule/handler.py"
    steps: ["fence_strip", "import_completion"]
    lines_modified: 3
    imports_added: ["from typing import Optional"]
```

---

## 6. Layer 5: Observability & Attribution

Telemetry integration for repair pipeline visibility.

### REQ-RPL-400: OTel Span per Repair Attempt

**Priority:** P1

Each repair attempt SHALL be wrapped in an OTel span:

- **Span name:** `repair.attempt`
- **Attributes:**
  - `repair.feature_name`: Feature being repaired
  - `repair.file_count`: Number of files in repair scope
  - `repair.route_confidence`: Routing confidence level
  - `repair.success`: Boolean outcome
- **Events:** One span event per repair step applied:
  - `repair.step.{step_name}` with attributes `modified`, `reverted`, step-specific metrics

### REQ-RPL-401: Repair Metrics

**Priority:** P1

The following Prometheus-compatible counters SHALL be emitted:

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `repair_attempts_total` | Counter | `feature`, `outcome` | Total repair attempts (outcome: `success`/`failure`/`skipped`) |
| `repair_success_total` | Counter | `feature` | Successful repairs (subset of attempts) |
| `repair_steps_applied` | Counter | `step_name`, `outcome` | Per-step application count (outcome: `applied`/`reverted`/`no_change`) |
| `repair_cost_avoided_usd` | Counter | `feature` | Estimated regeneration cost avoided by successful repair |
| `repair_wall_clock_ms` | Histogram | `feature` | Wall-clock time per repair attempt |

### REQ-RPL-402: Manifest Attribution

**Priority:** P2

Repair actions SHALL be noted in the OTel observability manifest (generated by `scripts/generate_observability_manifest.py`):

```yaml
repair_pipeline:
  spans:
    - name: repair.attempt
      attributes: [repair.feature_name, repair.file_count, repair.success]
  metrics:
    - name: repair_attempts_total
      type: counter
    - name: repair_success_total
      type: counter
    - name: repair_steps_applied
      type: counter
```

### REQ-RPL-403: RepairAttribution Dataclass

**Priority:** P1

A `RepairAttribution` dataclass (extending `micro_prime/models.py:37–52`) SHALL capture per-step deltas:

```python
@dataclass
class FeatureRepairAttribution:
    """Per-feature repair attribution for observability."""

    feature_name: str
    files_repaired: int
    total_steps_applied: int
    total_steps_reverted: int
    lines_added: int
    lines_removed: int
    imports_added: list[str]
    fences_stripped: int
    indent_fixes: int
    brackets_balanced: int
    duplicates_removed: int
    lint_fixes: int
    wall_clock_ms: float
    per_file: dict[str, RepairAttribution]   # Reuse micro-prime RepairAttribution
```

---

## 7. Layer 6: Escalation & Cost Optimization

Escalation flow and cost-benefit tracking.

### REQ-RPL-500: Escalation Flow

**Priority:** P0

The full escalation sequence SHALL be:

```
CHECKPOINT fail
    │
    ├──► ROUTE: classify failure patterns
    │       │
    │       ├── repairable → REPAIR (deterministic, ~$0, <1s)
    │       │       │
    │       │       ├── re-CHECKPOINT pass → ACCEPT
    │       │       │
    │       │       └── re-CHECKPOINT fail → continue to error-informed regen
    │       │
    │       └── not repairable → skip repair
    │
    ├──► ERROR-INFORMED REGEN (LLM call, ~$0.50–1.00, 10–30s)
    │       │
    │       ├── CHECKPOINT pass → ACCEPT
    │       │
    │       └── CHECKPOINT fail → continue to tier escalation
    │
    ├──► TIER ESCALATION (higher-capability model, ~$1.00–3.00)
    │       │
    │       ├── CHECKPOINT pass → ACCEPT
    │       │
    │       └── CHECKPOINT fail → FAIL
    │
    └──► FAIL (feature marked FAILED, error preserved for manual review)
```

Each stage is attempted only if the previous stage did not resolve the failure.

### REQ-RPL-501: Cost Tracking

**Priority:** P1

The repair pipeline SHALL track costs at each escalation stage:

| Stage | Estimated Cost | Tracked By |
|-------|---------------|------------|
| Repair (deterministic) | ~$0.00 | `repair_cost_avoided_usd` metric |
| Error-informed regen | ~$0.50–1.00 | Existing `CostTracker` |
| Tier escalation | ~$1.00–3.00 | Existing `CostTracker` |

A `repair_cost_avoided_usd` counter SHALL be incremented by the estimated regeneration cost whenever repair succeeds, enabling ROI measurement of the repair pipeline.

### REQ-RPL-502: Circuit Breaker

**Priority:** P2

After N consecutive repair failures on the same error pattern (default N=3), the pipeline SHALL skip repair for that pattern and proceed directly to regeneration.

**State:** Per-pattern failure count, reset on successful repair.

**Configuration:** `repair_circuit_breaker_threshold: int` (default 3).

**Rationale:** Prevents wasting wall-clock time on repair steps that consistently fail for a particular error pattern (e.g., a novel syntax error that no deterministic step can fix).

### REQ-RPL-503: Cost-Benefit Measurement

**Priority:** P2

The pipeline SHALL track per-step success rates over time to enable pruning of ineffective steps:

```python
@dataclass
class StepEffectiveness:
    """Tracks per-step success rate for cost-benefit analysis."""

    step_name: str
    attempts: int
    modifications: int           # Times step actually changed code
    reverts: int                 # Times step was reverted (broke valid code)
    contributed_to_success: int  # Times step was in a successful repair sequence
    effectiveness_rate: float    # contributed_to_success / attempts
```

Steps with `effectiveness_rate` below a configurable threshold (default 0.05) MAY be disabled with a warning log.

---

## 8. Routing Table

Maps checkpoint failure patterns to repair step sequences.

| Checkpoint | Failure Pattern | Repair Steps | Confidence |
|------------|----------------|--------------|------------|
| Syntax | `SyntaxError: unexpected EOF while parsing` | fence_strip → bracket_balance → ast_validate | HIGH |
| Syntax | `SyntaxError: invalid syntax` | fence_strip → indent_normalize → ast_validate | MEDIUM |
| Syntax | `IndentationError` / `TabError` | indent_normalize → ast_validate | HIGH |
| Import | `ModuleNotFoundError: No module named 'X'` | import_completion → ast_validate | HIGH |
| Import | `ImportError: cannot import name 'Y' from 'X'` | import_completion → ast_validate | MEDIUM |
| Lint | `E999 SyntaxError` | fence_strip → indent_normalize → ast_validate | HIGH |
| Lint | `F811 redefinition of unused name` | duplicate_removal → ast_validate | MEDIUM |
| Lint | `E7xx` (statement issues) | extended_lint_fix → ast_validate | HIGH |
| Lint | `F4xx` (import issues) | extended_lint_fix → ast_validate | HIGH |
| Lint | Non-auto-fixable rules | SKIP — escalate to regeneration | N/A |
| Test | Test regression (previously passing test fails) | SKIP — not repairable, escalate to regeneration | N/A |
| Size | Ratio < threshold (0.60) | SKIP or merge_repair (REQ-RPL-301) | LOW |

**Confidence levels:**

- **HIGH:** Pattern reliably maps to a deterministic fix. Expected success rate >80%.
- **MEDIUM:** Pattern is likely fixable but may require multiple steps or have edge cases. Expected success rate 40–80%.
- **LOW:** Pattern may or may not be fixable. Repair is speculative. Expected success rate <40%.

**Pattern matching:** Error patterns are matched via regex against `CheckpointResult.errors` entries. Multiple matching patterns result in the **union** of their repair steps, deduplicated and ordered by the canonical step sequence (REQ-RPL-100 through REQ-RPL-106).

---

## 9. Acceptance Criteria

### 9.1 Functional Requirements

1. **P0 unit tests:** All P0 requirements (REQ-RPL-001, 002, 003, 004, 005, 006, 008, 100, 101, 102, 106, 200, 201, 300, 500) SHALL have corresponding unit tests
2. **Non-destructive property test:** A property-based test (e.g., Hypothesis) SHALL verify that no repair step sequence makes valid Python code invalid, across randomized valid Python inputs
3. **Round-trip test:** For each entry in the routing table with confidence HIGH, a test SHALL demonstrate: inject known failure → repair → re-checkpoint passes
4. **Backward compatibility:** When `repair_enabled=False`, the existing checkpoint → rollback → retry flow SHALL be unchanged (no behavioral difference)

### 9.2 Performance Requirements

5. **Wall-clock budget:** The repair pipeline SHALL not increase wall-clock time by more than **5 seconds per feature** for deterministic-only steps (no LLM calls)
6. **Steps are deterministic:** No repair step SHALL make LLM API calls. All fixes are deterministic (AST manipulation, regex, subprocess calls to ruff)

### 9.3 Observability Requirements

7. **Repair visibility:** Every repair attempt SHALL produce at minimum a log line at INFO level with feature name, steps applied, and outcome
8. **Metrics emission:** `repair_attempts_total` and `repair_success_total` counters SHALL be emitted after each repair attempt (when OTel is configured)

### 9.4 Integration Requirements

9. **PrimeContractor integration:** Repair pipeline SHALL be callable from `process_feature()` without modifying the `FeatureSpec` data model
10. **Artisan integration:** Repair pipeline SHALL be callable from `IntegrationEngine.integrate()` without modifying `IntegrationResult`
11. **Micro-prime reuse:** At least 4 repair steps SHALL reuse logic from `micro_prime/repair.py` (fence_strip, indent_normalize, import_completion, ast_validate)

---

## 10. Key Reuse Summary

| Existing Asset | Location | Reuse in Repair Pipeline |
|----------------|----------|--------------------------|
| 7-step repair pipeline | `micro_prime/repair.py:447–464` | Architecture pattern, entry point signature |
| `_step_fence_strip` | `repair.py:37–53` | REQ-RPL-100: Fence strip step |
| `_step_indent_normalize` | `repair.py:180–245` | REQ-RPL-101: Indent normalize step |
| `_step_import_completion` | `repair.py:340–412` | REQ-RPL-102: Import completion step (extended) |
| `_step_ast_validate` | `repair.py:415–428` | REQ-RPL-106: AST validation step |
| Non-destructive guard | `repair.py:470–488` | REQ-RPL-003: Before/after AST parse pattern |
| `RepairStepResult` | `micro_prime/models.py:54–65` | REQ-RPL-005: Per-step result model |
| `RepairAttribution` | `micro_prime/models.py:37–52` | REQ-RPL-403: Per-file attribution |
| `build_repair_attribution()` | `repair.py:493–525` | REQ-RPL-403: Attribution builder |
| `CheckpointResult` | `checkpoint.py:46–74` | REQ-RPL-004: Source of structured diagnostics |
| `CheckpointStatus` enum | `checkpoint.py:37–43` | REQ-RPL-002: Routing table key |
| `IntegrationCheckpoint` | `checkpoint.py:76–565` | REQ-RPL-008: Re-checkpoint execution |
| Size regression guard | `integration_engine.py:932–982` | REQ-RPL-301: Hook point for merge repair |
| Error-informed retry | `prime_contractor.py:1613–1619` | REQ-RPL-204: Fallback when repair fails |
| `on_checkpoint_failed` | `prime_contractor.py:2186–2187` | REQ-RPL-200: Injection point |
| Pre-merge ruff auto-fix | `integration_engine.py:1073–1088` | REQ-RPL-302: Extended pre-checkpoint fix |

---

## 11. Appendix: Priority Summary

| Priority | Count | Scope |
|----------|-------|-------|
| P0 | 15 | MVP repair loop: entry point, routing, non-destructive guarantee, core steps, integration hooks, escalation |
| P1 | 12 | Production-ready: step protocol, structured diagnostics, retry enrichment, observability, cost tracking |
| P2 | 6 | Optimization: duplicate removal, circuit breaker, cost-benefit measurement, manifest, handoff attribution |
| **Total** | **33** | |

### Implementation Order (recommended)

1. **Phase 1 (P0):** Core pipeline + 4 reused steps + PrimeContractor hook + re-checkpoint loop
2. **Phase 2 (P1):** Structured diagnostics + remaining steps + Artisan hook + OTel spans/metrics
3. **Phase 3 (P2):** Circuit breaker + cost-benefit tracking + duplicate removal + manifest + handoff
