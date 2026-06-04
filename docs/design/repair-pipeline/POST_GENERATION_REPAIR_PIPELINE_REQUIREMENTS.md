# Post-Generation Repair Pipeline Requirements

**Document ID:** REQ-RPL
**Version:** 1.4.0
**Status:** Draft — Mottainai Alignment Review
**Author:** Claude (agent-authored)
**Date:** 2026-03-03
**Revision:** v1.4.0 — Added Round R7: Mottainai & Forward Manifest Alignment suggestions (Gaps 1-8 below); leverages SCAFFOLD and ManifestRegistry for repair fidelity

---

## 1. Preamble

### 1.1 Purpose

This document specifies a **post-generation repair pipeline** that intercepts checkpoint failures in LLM-driven code generation workflows, applies targeted deterministic fixes using structured checkpoint diagnostics, and re-validates — only escalating to full LLM regeneration when repair is not cost-effective.

**The primary use case is PrimeContractor and Artisan Contractor code generation**, where each failed checkpoint triggers a full LLM regeneration costing ~$0.50–1.00 per attempt. Deterministic repair of fixable failures (syntax errors, missing imports, lint violations) avoids this spend entirely. The repair pipeline is designed to be the largest single lever for reducing wasted LLM cost in the generation loop.

### 1.2 Scope

The repair pipeline is an **abstract capability** that operates at two distinct levels within the SDK:

| Level | Workflow | Granularity | Cost per Failure | ROI of Repair |
|-------|----------|-------------|------------------|---------------|
| **Contractor** (primary) | PrimeContractor, Artisan | Multi-file features | ~$0.50–1.00 LLM regen | **High** — each successful repair saves a full LLM call |
| **Micro-prime** (proof of concept) | `micro_prime/repair.py` | Single code strings | ~$0 (local inference) | **Low** — but proves the abstraction cheaply |

The pipeline sits between checkpoint failure detection and rollback/regeneration in:

- **PrimeContractor** (`prime_contractor.py`) — feature-level code generation with error-informed retry
- **Artisan Contractor** (`integration_engine.py`) — phase-level IMPLEMENT → INTEGRATE flow
- **Micro-prime** (`micro_prime/repair.py`) — element-level repair (existing, to be refactored into the shared abstraction)

### 1.2.1 Architectural Relationship: Micro-Prime vs. Contractor

The existing micro-prime `repair.py` 7-step pipeline demonstrates non-destructive repair at the element level. This document specifies a **new contractor-level repair pipeline** that is architecturally distinct from micro-prime but shares core patterns through a common abstraction layer.

**What is shared** (the abstraction):

- `RepairStep` protocol — callable interface for individual repair steps
- Non-destructive guard — before/after validity check with per-step revert
- Routing table — pattern-match failure diagnostics to repair step sequences
- `RepairStepResult` / `RepairAttribution` — step-level result and attribution models
- Observability — OTel spans and metrics per repair attempt

**What differs** (per-level adaptation):

| Concern | Micro-prime | Contractor |
|---------|-------------|------------|
| Input | Single code string + `ForwardFileSpec` | `dict[Path, str]` + `CheckpointResult` |
| Import source | Manifest-declared (`ForwardFileSpec.imports`) | Checkpoint error parsing + project import map |
| Validation | `ast.parse()` / `_try_parse()` on element | `IntegrationCheckpoint.run_all_checkpoints()` on files |
| Staging | In-memory (code string) | Filesystem staging directory |
| Integration hook | Inline in `run_repair_pipeline()` | `process_feature()` / `IntegrationEngine.integrate()` |

**Design principle:** The abstraction layer is designed top-down from the contractor use case (the harder, higher-value problem). Micro-prime adapts to this abstraction, not the other way around. This prevents the protocol from being shaped too tightly around micro-prime's simpler model.

### 1.2.2 Implementation Strategy

Development follows a **bottom-up implementation, top-down design** approach:

1. **Phase 0 (Proof of Concept):** Refactor the existing `micro_prime/repair.py` into the abstract `RepairStep` protocol, routing table, and `RepairConfig`. Validate the abstraction against micro-prime's existing test suite. This phase is low-risk (refactoring working code) and low-cost (micro-prime calls are effectively free).

2. **Phase 1 (Contractor MVP):** Implement contractor-level adaptations — `CheckpointResult` parsing, multi-file orchestration, filesystem staging, and `process_feature()` hook. This is the high-value phase where each successful repair saves ~$0.50–1.00.

3. **Phase 2–3:** Structured diagnostics, Artisan integration, observability, cost tracking, and optimization (see Section 11 for full phasing).

**Rationale for micro-prime first:** The repair steps themselves (fence strip, indent normalize, import completion, AST validate) are algorithmically identical at both levels — they operate on a code string and return a modified code string. Proving them correct at the micro-prime level (where problems are smaller, iterations are faster, and failures are free) de-risks the contractor integration. The adaptation work for contractor is primarily integration plumbing (multi-file orchestration, checkpoint parsing, staging), not repair logic.

### 1.3 Relationship to Design Principles

**Mottainai (waste elimination):** Generated code that fails checkpoint validation for fixable reasons (syntax errors, missing imports, lint violations) is currently discarded and regenerated from scratch. At the contractor level, each regeneration costs ~$0.50–1.00 in LLM API calls and 10–30 seconds of wall-clock time. Deterministic repair costs ~$0 and <1 second. Across a typical pipeline run of 15–40 features, even a 30% repair success rate saves $2–12 in direct LLM costs and 1–5 minutes of wall-clock time per run.

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

### 1.6 PrimeContractor Design Drivers

The PrimeContractor is the primary target for this pipeline. Its characteristics shape the repair abstraction in ways that micro-prime does not:

#### 1.6.1 Multi-File Features

A single PrimeContractor feature typically generates 2–8 files (implementation, tests, config, Dockerfile, requirements manifest). When a checkpoint fails:

- **Multiple files may have errors** — a syntax error in `handler.py` and a missing import in `__init__.py` are independent failures within the same feature. The repair pipeline must route and repair per-file, not per-feature.
- **Files may have cross-dependencies** — `handler.py` imports from `models.py`, both generated in the same feature. Repairing `models.py` (e.g., adding a missing class) may resolve an `ImportError` in `handler.py` without touching it. The pipeline must handle cascading fixes.
- **Partial validity is common** — 6 of 8 files may pass checkpoint while 2 fail. The current flow discards all 8 and regenerates from scratch. The repair pipeline should repair only the failing files and preserve the valid ones.
- **Staging is filesystem-based** — unlike micro-prime (in-memory string), contractor repair operates on real files in a staging directory. Atomic swap, cleanup lifecycle, and path safety all apply.

#### 1.6.2 Checkpoint Richness

Micro-prime validation is a single `ast.parse()` call. PrimeContractor checkpoints run a full suite via `IntegrationCheckpoint.run_all_checkpoints()`:

| Checkpoint | What it catches | Repair-relevant? |
|------------|----------------|-----------------|
| Syntax check | `SyntaxError`, `IndentationError` | Yes — fence strip, indent normalize, bracket balance |
| Import check | `ModuleNotFoundError`, `ImportError` | Yes — import completion |
| Lint check (ruff) | Rule violations (`E7xx`, `F4xx`, `F811`, etc.) | Partially — auto-fixable rules only |
| Test regression | Previously-passing tests now fail | No — escalate to regeneration |
| Size regression | Generated file is <60% of target size | Conditional — see REQ-RPL-301 |

The routing table (Section 8) maps these checkpoint results to repair step sequences. This multi-checkpoint routing does not exist at the micro-prime level.

#### 1.6.3 Cost Asymmetry

| Concern | Micro-prime | PrimeContractor |
|---------|-------------|-----------------|
| Generation cost per failure | ~$0 (local inference or cached) | ~$0.50–1.00 (full LLM API call) |
| Retry budget | Generous (cheap to retry) | Constrained (6 attempts default, each costly) |
| Repair ROI | Low (saves negligible cost) | High (each repair saves a full LLM call) |
| Failure feedback | Direct (element context is small) | Lossy (rich diagnostics flattened to `error_message` string) |

This cost asymmetry is why the repair pipeline is designed top-down from the PrimeContractor use case: the contractor is where repair generates measurable savings.

#### 1.6.4 Integration Complexity

Micro-prime repair is a function call inside a single pipeline. PrimeContractor repair must integrate with:

- **Queue state management** — `feature.integration_attempts`, `feature.status`, `feature.error_message` (see `queue.py:335–391`)
- **Snapshot/restore lifecycle** — `_pre_integration_snapshots` dict + `.pre_integration` sidecar files (see `integration_engine.py:421–488`)
- **Error-informed retry** — if repair fails, the enriched error context must flow to the LLM retry path (`prime_contractor.py:1613–1619`)
- **Callback hooks** — `on_checkpoint_failed` callback must be aware of repair attempts
- **Cost tracking** — `CostTracker` must distinguish repair ($0) from regeneration (~$0.50–1.00)

None of these concerns exist at the micro-prime level. The abstraction layer handles them through the `RepairConfig` and `RepairPipelineResult` interfaces, keeping the shared `RepairStep` implementations decoupled from contractor plumbing.

#### 1.6.5 Concurrency Assumptions

The PrimeContractor currently processes features sequentially (`prime_contractor.py:2239–2268`). The repair pipeline assumes single-threaded feature processing. `IntegrationEngine` stores snapshots in an in-memory dict (`_pre_integration_snapshots`) — if future parallelism is introduced, staging directories and snapshot state require external synchronization. This assumption does not apply to micro-prime, which is inherently single-invocation.

### 1.7 Key References

| Asset | Location | Role |
|-------|----------|------|
| 7-step repair pipeline | `src/startd8/micro_prime/repair.py` | Proven repair pattern (Phase 0 refactoring target) |
| `RepairStepResult` | `src/startd8/micro_prime/models.py:54–64` | Per-step result model |
| `RepairAttribution` | `src/startd8/micro_prime/models.py:37–52` | Granular attribution |
| Non-destructive guard | `repair.py:470–488` | Before/after AST parse pattern |
| `CheckpointResult` | `contractors/checkpoint.py:46–73` | Structured failure diagnostics |
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
    config: RepairConfig,
) -> RepairPipelineResult:
```

This function is invoked after checkpoint failure, **before** rollback. It receives the generated file contents (as a path-to-source mapping), the structured checkpoint results, and a `RepairContext` carrying diagnostic metadata.

**Rationale:** This is a new contractor-level interface inspired by `micro_prime/repair.py:447–464` but architecturally distinct: it operates on multi-file features (not single code strings), consumes `CheckpointResult` diagnostics (not `ForwardFileSpec` manifests), and orchestrates per-file iteration internally. The micro-prime `run_repair_pipeline()` will be refactored to delegate to this same `RepairStep` protocol through an adapter (see Section 1.2.1).

### REQ-RPL-002: Checkpoint-to-Repair Routing Table

**Priority:** P0

The pipeline SHALL include a routing table that maps checkpoint failure patterns to ordered sequences of repair steps with confidence levels. The routing table is defined in Section 7 (Routing Table).

The router SHALL:

- Parse `CheckpointResult.errors` to classify failure patterns (syntax, import, lint)
- **Route and scope per-file**: classify failures based on the filename prefix in the checkpoint error string. Only files implicated by errors SHALL be staged for repair.
- Select the appropriate repair step sequence based on classification
- Skip repair entirely for non-repairable categories (test regressions)
- Return `RepairRoute` with `steps: list[RepairStep]`, `confidence: Confidence`, and `skip_reason: Optional[str]`

**Level-Specific Input:** The router SHALL accept a `list[str]` (standard diagnostics) as input. Contractor passes `CheckpointResult.errors`; micro-prime passes `SyntaxError` message strings or a compatible adapter.

### REQ-RPL-003: Non-Destructive Guarantee

**Priority:** P0

If any repair step causes previously valid code to become invalid, that step's changes SHALL be reverted. This reuses the pattern from `micro_prime/repair.py:470–488`:

1. Before each step: `was_valid = ast_parse(code)`
2. After each step: `is_valid = ast_parse(result.code)`
3. If `was_valid and not is_valid`: revert step (`result.modified = False`, `result.code = original`)

This guarantee operates **per file**: each file's validity is tracked independently.

**Limitations:** The non-destructive guarantee covers **syntax only**. `ast.parse()` validates Python grammar but not semantic correctness (e.g., undefined names or circular imports). Semantic regressions are caught by the final re-checkpoint (REQ-RPL-008).

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

1. Create a **unique staging directory** (e.g., `.startd8/repair-staging/{timestamp}_{feature}/`) with isolated scope.
2. Copy implicated files to the staging directory, following path safety: follow symlinks=False, ensure resolved paths stay under `project_root`.
3. Apply repair steps to staged copies.
4. Run re-checkpoint against staged copies.
5. If re-checkpoint passes: replace originals with staged copies (atomic swap).
6. Cleanup staging directory on completion (success or failure).

**Rationale:** This mirrors the existing snapshot pattern in `integration_engine.py:421–468` (`_snapshot_target` / `_restore_target`).

### REQ-RPL-007: Repair Step Protocol

**Priority:** P1

Each repair step SHALL implement a callable protocol:

```python
class RepairStep(Protocol):
    """Protocol for individual repair steps."""

    name: str

    def __call__(
        self, code: str, context: RepairContext, file_path: Path, element_context: Optional[dict] = None
    ) -> RepairStepResult:
        """Apply repair to code, returning modified code and step result.
        
        Optional element_context carries parent_class/context for micro-prime step adapters.
        """
        ...
```

Steps are composable and ordered. The pipeline executes them in sequence, with the non-destructive guard (REQ-RPL-003) applied between each step.

**Delta guardrails:** If a repair step changes more than a configured percentage of lines in a file (default: 50%), the attempt SHALL be treated as low-confidence and skipped/escalated rather than swapping staged files. A repair that rewrites the majority of a file is not a targeted fix — it is a rewrite that should go through regeneration instead.

### REQ-RPL-008: Re-Checkpoint After Repair

**Priority:** P0

After all repair steps complete, the pipeline SHALL run the **same checkpoint suite** (`IntegrationCheckpoint.run_all_checkpoints()`) against the repaired files:

- **Fail:** Return `RepairPipelineResult(success=False)` with re-checkpoint details for escalation

The re-checkpoint MUST use identical configuration (same lint rules, same test baseline) as the original checkpoint that triggered the repair.

**Level-Specific Validation:** Contractor passes `IntegrationCheckpoint`; micro-prime passes a lightweight `SyntaxValidator` that wraps `ast.parse()`.

**Subprocess hardening:** Re-checkpoint subprocess calls (ruff, pytest) SHALL follow the same hardening rules as REQ-RPL-105: `shell=False`, argv-based paths, sanitized environment.

### REQ-RPL-009: Traceability Comment

**Priority:** P1

The repair pipeline SHALL add a transient header comment to each file in the staging directory that has been modified: `# [REPAIRED BY STARTD8: {steps_applied}]`.

**Rationale:** This distinguishes LLM-authored code from SDK-repaired code during manual review and helps developers identify if a fix was deterministic or generative.

---

## 3. Layer 2: Repair Steps

Individual repair steps that address specific checkpoint failure categories. Steps are ordered from most common/cheapest to most complex.

**Abstraction note:** Each step below operates on a single code string via the `RepairStep` protocol (REQ-RPL-007). The same step implementations are shared between micro-prime and contractor levels — the orchestration layer (single-string vs. multi-file) is what differs, not the steps themselves. During Phase 0, existing micro-prime step functions are refactored into `RepairStep` protocol implementations; during Phase 1, those same implementations are invoked per-file by the contractor-level orchestrator.

### REQ-RPL-100: Fence Strip

**Priority:** P0

Remove markdown code fences (`` ```python ``, `` ``` ``) from generated code.

**Shared implementation:** Refactor `_step_fence_strip` from `micro_prime/repair.py:37–53` into a `RepairStep` protocol implementation. The step logic is identical at both levels (operates on a code string); the orchestration layer handles element-vs-file dispatch.

**Trigger:** `SyntaxError` where code starts with `` ``` `` or contains fence patterns.

### REQ-RPL-101: Indent Normalize

**Priority:** P0

Fix mixed tabs/spaces indentation that causes `IndentationError` or `TabError`.

**Shared implementation:** Refactor `_step_indent_normalize` from `micro_prime/repair.py:180–245` into `RepairStep` protocol. Standardize to 4-space indentation.

**Trigger:** `IndentationError`, `TabError`, or mixed whitespace detected.

### REQ-RPL-102: Import Completion

**Priority:** P0

Add missing imports identified by the checkpoint import check (`IntegrationCheckpoint.check_imports()`, `checkpoint.py:219–300`).

**Two implementations, one protocol:**

1. **ManifestImportCompletion** (micro-prime): Uses `ForwardFileSpec.imports` (explicit manifest data).
2. **ErrorDrivenImportCompletion** (contractor): Parses `ModuleNotFoundError`/`ImportError` from checkpoint results.

**Contractor-level discovery mechanism (Phase 1):**

- Parse `ModuleNotFoundError: No module named 'X'` from checkpoint errors to extract module name
- Parse `ImportError: cannot import name 'Y' from 'X'` for specific name imports
- Consult `RepairContext.existing_imports` to avoid duplicate imports
- Handle relative imports within the project package

**Trigger:** `ModuleNotFoundError`, `ImportError` in checkpoint results.

### REQ-RPL-103: Bracket/Paren Balance

**Priority:** P1

Fix unclosed delimiters (`(`, `[`, `{`, and their closing counterparts) from truncated generation.

**Implementation:** Count delimiter pairs; if imbalanced, append/remove closing delimiters at the appropriate scope level using **token-level scanning with scope tracking** (not naive string append). AST analysis is not possible for code with unclosed delimiters.

**Trigger:** `SyntaxError: unexpected EOF while parsing`, `SyntaxError: '(' was never closed`.

### REQ-RPL-104: Duplicate Removal

**Priority:** P2

Detect and remove duplicate function or class definitions that arise from merge conflict artifacts or repeated generation.

**Implementation:**

- Parse AST to find duplicate `def` / `class` names at the same scope level
- Keep the last definition (most likely the intended version)
- Remove duplicate **imports** that bind the same name (keep the first)
- **Cross-kind F811 (added — run-028):** when a name is bound by **both an import and a
  module-level `def`/`class`** (e.g. `from app.matching import resolve_matches` then
  `def resolve_matches(...)`), remove the **shadowed import** and keep the local definition.
  Safe because `F811 redefinition of *unused* name` fires only when the import binding has no
  use before the redefinition, so dropping it cannot break a caller. (Implemented by pre-seeding
  the import-dedup `seen` set with module-level def/class names.)
- Log removed duplicates in `RepairStepResult.metrics`

**Trigger:** `F811 redefinition of unused name` in lint checkpoint results — covers
import↔import, def↔def, **and import↔def** collisions.

### REQ-RPL-105: Extended Lint Fix

**Priority:** P1

Apply `ruff check --fix --unsafe-fixes` for checkpoint-identified lint violations beyond the current `E7,E9,F` selection (`integration_engine.py:1081–1082`).

**Implementation:**

- Parse lint violation codes from `CheckpointResult.errors`
- Run `ruff check --fix --select={codes}` targeting only the identified violations
- Capture ruff's output for attribution

**Trigger:** Lint checkpoint failures with auto-fixable rule codes.

**Constraint:** Only apply to rules that ruff can auto-fix. Non-fixable rules are escalated.

**Subprocess hardening:** All subprocess calls (ruff, py_compile) SHALL use `shell=False` with argv-based path passing (no shell interpolation) and a sanitized environment that does not inherit secrets (strip `*_API_KEY`, `*_SECRET`, `*_TOKEN` from `env`).

### REQ-RPL-106: AST Validate

**Priority:** P0

Verify the final repaired code parses without `SyntaxError` via `ast.parse()`.

**Shared implementation:** Refactor `_step_ast_validate` from `micro_prime/repair.py:415–428` into `RepairStep` protocol.

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

**Parsing Patterns:**

- **Syntax:** `^  File "(?P<file>.+)", line (?P<line>\d+).*\n(?P<message>.+)$`
- **Import:** `^(?P<file>.+): ModuleNotFoundError: No module named '(?P<module>.+)'$`
- **Lint:** `^(?P<file>.+):(?P<line>\d+):(?P<col>\d+): (?P<rule>\w+) (?P<message>.+)$`

### REQ-RPL-203: Successful Repair Does Not Consume Retry

**Priority:** P1

If the repair pipeline succeeds (re-checkpoint passes), the feature SHALL be marked `COMPLETE` without incrementing `feature.integration_attempts` or consuming a retry slot.

**Rationale:** Deterministic repair is not an "attempt" — it is a correction. Consuming a retry slot for a $0 fix reduces the budget available for genuine LLM-dependent retries. **A failed repair attempt DOES increment the attempt counter** as it precedes regeneration.

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

**Diagnostic sanitization:** Before logging or persisting diagnostic strings (in retry context, repair artifacts, or OTel spans), the pipeline SHALL strip control characters (ANSI escape sequences), truncate lines exceeding 500 characters, and redact patterns matching common secret formats (`*_API_KEY=...`, `*_SECRET=...`, `*_TOKEN=...`).

### REQ-RPL-205: Standalone Repair Command

**Priority:** P1

The SDK CLI SHALL expose a `startd8 repair [FILES]` command that invokes the repair pipeline directly on local files.

**Rationale:** Enables manual "cleanup" of files or offline repair without triggering a full generation workflow.

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

**Execution Order:** Pre-checkpoint repair SHALL run **after merge** (`_merge_files`) and **before** the existing ruff auto-fix.

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
| `repair_attempts_total` | Counter | `outcome`, `error_category` | Total repair attempts (outcome: `success`/`failure`/`skipped`). Per-feature detail in span attributes. |
| `repair_success_total` | Counter | `error_category` | Successful repairs (subset of attempts). |
| `repair_steps_applied` | Counter | `step_name`, `outcome` | Per-step application count (outcome: `applied`/`reverted`/`no_change`) |
| `repair_cost_avoided_usd` | Counter | — | Total estimated regeneration cost avoided. |
| `repair_wall_clock_ms` | Histogram | `feature` | Wall-clock time per repair attempt (Histogram allows higher cardinality). |

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

**Per-file repair frequency:** The manifest SHALL track `repair_count` and `last_repair_date` per file that undergoes repair. Files with high repair frequency are candidates for manual refactoring (the LLM consistently produces repairable-but-not-clean output for these paths).

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

### REQ-RPL-404: Repair Attempt Artifact

**Priority:** P2

Each repair attempt SHALL persist a `repair_attempt.json` artifact to the staging directory containing:

- `RepairContext` (structured checkpoint diagnostics)
- Matched routing patterns and selected steps
- Per-step diffs/metrics and attribution
- Re-checkpoint errors (if repair failed)

The artifact path SHALL be included in the error context passed to the LLM retry path (REQ-RPL-204), enabling richer post-mortem analysis without re-parsing logs.

**Rationale:** Complements OTel spans (REQ-RPL-400) for environments where OTel is not configured. Enables offline debugging and pattern analysis of repair failures.

**Diagnostic sanitization:** The persisted artifact SHALL apply the same sanitization rules as REQ-RPL-204: strip control characters, truncate long lines, redact secrets.

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

1. **Wall-clock budget:** The repair pipeline SHALL not increase wall-clock time by more than **5 seconds per feature** for deterministic-only steps (no LLM calls)
2. **Steps are deterministic:** No repair step SHALL make LLM API calls. All fixes are deterministic (AST manipulation, regex, subprocess calls to ruff)
3. **Per-step timeout:** Each repair step SHALL enforce a hard timeout (default: 2 seconds). Steps exceeding the timeout SHALL be aborted and reported as `skipped` with reason `timeout`. The total repair attempt SHALL enforce a hard cap tied to the 5-second wall-clock budget.
4. **Timeout surfacing:** Timeout-induced skips SHALL be reported as a distinct `skipped_reason` in `RepairPipelineResult` and increment `repair_attempts_total{outcome="skipped"}` in metrics.

### 9.3 Observability Requirements

1. **Repair visibility:** Every repair attempt SHALL produce at minimum a log line at INFO level with feature name, steps applied, and outcome
2. **Metrics emission:** `repair_attempts_total` and `repair_success_total` counters SHALL be emitted after each repair attempt (when OTel is configured)

### 9.4 Integration Requirements

1. **PrimeContractor integration:** Repair pipeline SHALL be callable from `process_feature()` without modifying the `FeatureSpec` data model
2. **Artisan integration:** Repair pipeline SHALL be callable from `IntegrationEngine.integrate()` without modifying `IntegrationResult`
3. **Shared abstraction:** At least 4 repair steps SHALL be `RepairStep` protocol implementations shared between micro-prime and contractor levels (fence_strip, indent_normalize, import_completion, ast_validate)
4. **Micro-prime regression:** After Phase 0 refactoring, all existing `micro_prime/repair.py` tests SHALL pass against the new `RepairStep` protocol implementations with no behavioral changes

---

## 10. Abstraction & Reuse Summary

The repair pipeline introduces a **shared abstraction layer** between micro-prime and contractor levels. Existing micro-prime assets are refactored into this abstraction during Phase 0; contractor-level assets are consumed during Phase 1.

### 10.1 Shared Abstraction (refactored from micro-prime → shared `repair/` module)

| Existing Asset | Current Location | Becomes |
|----------------|-----------------|---------|
| `_step_fence_strip` | `micro_prime/repair.py:37–53` | `RepairStep` implementation (REQ-RPL-100) |
| `_step_indent_normalize` | `micro_prime/repair.py:180–245` | `RepairStep` implementation (REQ-RPL-101) |
| `_step_import_completion` | `micro_prime/repair.py:340–412` | `RepairStep` implementation (REQ-RPL-102), extended for contractor |
| `_step_ast_validate` | `micro_prime/repair.py:415–428` | `RepairStep` implementation (REQ-RPL-106) |
| Non-destructive guard | `micro_prime/repair.py:470–488` | Shared guard in pipeline orchestrator (REQ-RPL-003) |
| `RepairStepResult` | `micro_prime/models.py:54–64` | Shared model (REQ-RPL-005) |
| `RepairAttribution` | `micro_prime/models.py:37–52` | Shared model (REQ-RPL-403) |
| `build_repair_attribution()` | `micro_prime/repair.py:493–525` | Shared attribution builder (REQ-RPL-403) |
| `run_repair_pipeline()` | `micro_prime/repair.py:447–451` | Architectural inspiration; contractor version is a new interface (REQ-RPL-001) |

### 10.2 Contractor-Level Integration Points (Phase 1)

| Asset | Location | Role in Repair Pipeline |
|-------|----------|------------------------|
| `CheckpointResult` | `checkpoint.py:46–73` | Source of structured diagnostics (REQ-RPL-004) |
| `CheckpointStatus` enum | `checkpoint.py:37–43` | Routing table key (REQ-RPL-002) |
| `IntegrationCheckpoint` | `checkpoint.py:76–565` | Re-checkpoint execution (REQ-RPL-008) |
| `process_feature()` | `prime_contractor.py:1590–1622` | PrimeContractor hook point (REQ-RPL-200) |
| `on_checkpoint_failed` | `prime_contractor.py:2186–2187` | Callback injection point (REQ-RPL-200) |
| Error-informed retry | `prime_contractor.py:1613–1619` | Fallback when repair fails (REQ-RPL-204) |
| `IntegrationEngine` | `integration_engine.py` | Artisan hook point (REQ-RPL-300) |
| Size regression guard | `integration_engine.py:932–982` | Hook point for merge repair (REQ-RPL-301) |
| Pre-merge ruff auto-fix | `integration_engine.py:1073–1088` | Extended pre-checkpoint fix (REQ-RPL-302) |

### 10.3 Shared Module Layout

The shared pipeline code SHALL reside in `src/startd8/repair/`.

- `src/startd8/repair/orchestrator.py` — Pipeline entry points
- `src/startd8/repair/steps/` — Step protocol implementations
- `src/startd8/repair/models.py` — Shared dataclasses
- `src/startd8/repair/routing.py` — Routing table logic

---

## 11. Appendix: Priority Summary

| Priority | Count | Scope |
|----------|-------|-------|
| P0 | 15 | MVP repair loop: entry point, routing, non-destructive guarantee, core steps, integration hooks, escalation |
| P1 | 14 | Production-ready: step protocol, traceability, structured diagnostics, retry enrichment, standalone CLI, observability, cost tracking |
| P2 | 6 | Optimization: duplicate removal, circuit breaker, cost-benefit measurement, manifest (with per-file repair frequency), handoff attribution, repair attempt artifact |
| **Total** | **35** | |

### Implementation Order (recommended)

1. **Phase 0 (Proof of Concept — micro-prime):** Refactor existing `micro_prime/repair.py` steps into `RepairStep` protocol implementations. Extract shared models (`RepairStepResult`, `RepairAttribution`) to a common `repair/` module. Validate abstraction against existing micro-prime tests. Introduce `RepairConfig` and routing table at micro-prime level. **Cost: ~$0 (no LLM calls). Risk: low (refactoring working code).**

2. **Phase 1 (Contractor MVP — P0):** Implement contractor-level orchestrator: multi-file `run_repair_pipeline()`, `CheckpointResult` parsing into structured diagnostics, filesystem staging, `process_feature()` hook, re-checkpoint loop. This is the high-value phase. **Cost: standard dev. Risk: medium (new integration plumbing).**

3. **Phase 2 (Production-ready — P1):** Remaining steps (bracket balance, duplicate removal, extended lint fix) + Artisan `IntegrationEngine` hook + OTel spans/metrics + structured retry enrichment.

4. **Phase 3 (Optimization — P2):** Circuit breaker + cost-benefit tracking + manifest attribution + handoff attribution.

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Areas Substantially Addressed

- **Architecture**: 7 suggestions applied (R1-S1, R2-S1, R2-S5, R3-S2, R3-S3, R3-S4, R3-S6)
- **Interfaces**: 5 suggestions applied (R1-S2, R2-S3, R2-S6, R3-S1/7, R4-S1)
- **Data**: 3 suggestions applied (R2-S4, R3-S1/7, R1-S3)
- **Risks**: 3 suggestions applied (R2-S2, R5-S1, R5-S2)
- **Validation**: 3 suggestions applied (R1-S5, R2-S8, R3-S5)
- **Ops**: 6 suggestions applied (R1-S6, R2-S10, R3-S8, R4-S3, R4-S4, R4-S5)
- **Security**: 3 suggestions applied (R1-S7, R5-S3, R5-S4)

### Areas Needing Further Review

All 7 areas have reached the substantially addressed threshold (>= 3 accepted suggestions). The review is **converged**.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Per-file routing | Codex R1 | Added explicit scoping to REQ-RPL-002 | 2026-03-03 |
| R1-S2 | `RepairConfig` | Codex R1 | Added to REQ-RPL-001/004 | 2026-03-03 |
| R1-S5 | Routing test criteria | Codex R1 | Added to Section 9 (see REQ-RPL-1101) | 2026-03-03 |
| R1-S6 | Staging lifecycle | Codex R1 | Updated REQ-RPL-006 with isolation/unique paths | 2026-03-03 |
| R1-S7 | Path safety | Codex R1 | Updated REQ-RPL-006 with travertine guards | 2026-03-03 |
| R2-S1 | Import discovery | Claude R2 | Specified patterns in REQ-RPL-102 | 2026-03-03 |
| R2-S2 | Syntax-only guard | Claude R2 | Added limitation note to REQ-RPL-003 | 2026-03-03 |
| R2-S3 | Signature divergence | Claude R2 | Refined REQ-RPL-001 and Rationale | 2026-03-03 |
| R2-S4 | Parsing rules | Claude R2 | Added regex patterns to REQ-RPL-202 | 2026-03-03 |
| R2-S5 | Integration sequencing | Claude R2 | Specified order in REQ-RPL-302 | 2026-03-03 |
| R2-S6 | Retry consumption | Claude R2 | Clarified success/failure logic in REQ-RPL-203 | 2026-03-03 |
| R2-S8 | Bracket balance algorithm | Claude R2 | Fixed REQ-RPL-103 to use token scanning | 2026-03-03 |
| R2-S10 | Line references | Claude R2 | Updated Section 1.7 calibration | 2026-03-03 |
| R3-S1/7 | Protocol compatibility | Claude R3 | Added element_context to REQ-RPL-007 | 2026-03-03 |
| R3-S2 | Dual import algorithms | Claude R3 | Updated REQ-RPL-102 with implementation split | 2026-03-03 |
| R3-S3 | Level-aware validation | Claude R3 | Updated REQ-RPL-008 with Validator protocol | 2026-03-03 |
| R3-S4 | Abstract diagnostic input | Claude R3 | Added level-specific note to REQ-RPL-002 | 2026-03-03 |
| R3-S5 | Phase 0 exit criteria | Claude R3 | Updated Section 1.2.2 criteria | 2026-03-03 |
| R3-S6 | Module location | Claude R3 | Added Section 10.3 layout | 2026-03-03 |
| R3-S8 | Bounded cardinality | Claude R3 | Optimized labels in REQ-RPL-401 | 2026-03-03 |
| R4-S1 | Traceability comment | Antigravity R4 | Added REQ-RPL-009 | 2026-03-03 |
| R4-S3 | Standalone repair command | Antigravity R4 | Added REQ-RPL-205 | 2026-03-03 |
| R4-S4 | Diff visualization | Antigravity R4 | Added to REQ-RPL-401 description | 2026-03-03 |
| R1-S3 | Repair attempt JSON artifact | Codex R1 | Added REQ-RPL-404 (P2) | 2026-03-03 |
| R4-S5 | Per-file repair frequency metadata | Antigravity R4 | Extended REQ-RPL-402 with repair_count/last_repair_date per file | 2026-03-03 |
| R5-S1 | Repair delta guardrails | Codex R5 | Added delta guardrails note to REQ-RPL-007 (50% line change threshold) | 2026-03-03 |
| R5-S2 | Per-step and total repair timeouts | Codex R5 | Added items 3-4 to Section 9.2 (2s per-step, 5s total hard cap) | 2026-03-03 |
| R5-S3 | Subprocess hardening | Codex R5 | Added subprocess hardening notes to REQ-RPL-105 and REQ-RPL-008 | 2026-03-03 |
| R5-S4 | Diagnostic sanitization | Codex R5 | Added sanitization rules to REQ-RPL-204 and REQ-RPL-404 | 2026-03-03 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S4 | Snapshot hash integrity | Codex R1 | Deferred to Phase 3; overkill for MVP staging isolation. | 2026-03-03 |
| R2-S7 | Concurrency assumptions | Claude R2 | Already addressed by explicit Section 1.6.5 addition. | 2026-03-03 |
| R2-S9 | Property test bounds | Claude R2 | Complexity exceeds Phase 0 ROI; deferred to Phase 4 optimization. | 2026-03-03 |
| R3-S9 | Micro-prime flow diagram | Claude R3 | Section 1.2.1 narrative + "What differs" table already communicates the two-level architecture; a second ASCII diagram is documentation polish, not a requirement improvement. | 2026-03-03 |
| R4-S2 | Interactive repair flag | Antigravity R4 | Interactive prompts conflict with automated batch pipelines (PrimeContractor processes 15-40 features sequentially). The accepted standalone `startd8 repair` command (REQ-RPL-205) covers the manual debugging use case without blocking automation. | 2026-03-03 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: Codex
- **Date**: 2026-03-03 16:50:26 UTC
- **Scope**: Initial CRP pass focused on scoping, configuration surfaces, and operational safeguards

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Define per-file routing and scoping so repair steps run only on files implicated by checkpoint diagnostics, with routing computed per file and unchanged files excluded from staging swap. | Prevents unintended edits to unrelated files and reduces repair surface area in multi-file features. | Section 2 (REQ-RPL-002/REQ-RPL-004) and Section 3 preface | Unit test with two files where only one has syntax/import errors; assert only that file is modified and swapped. |
| R1-S2 | Interfaces | medium | Introduce a `RepairConfig` dataclass passed into `run_repair_pipeline` and integration hooks (PrimeContractor/IntegrationEngine) to centralize toggles like `repair_enabled`, `repairable_categories`, `pre_checkpoint_repair`, `staging_root`, and circuit breaker settings. | Avoids hidden globals and ensures consistent behavior across both integration points. | Section 2 near REQ-RPL-001 and Section 4/5 integration requirements | Unit tests that toggle config flags and verify repair is skipped or enabled accordingly. |
| R1-S3 | Data | medium | Persist a `repair_attempt.json` artifact per attempt containing `RepairContext`, matched patterns, selected steps, per-step diffs/metrics, and re-checkpoint errors; include its path in retry context. | Enables post-mortem analysis and richer regeneration context without re-parsing logs. | Section 6 (Observability & Attribution) | Integration test that artifact is created on failure and is readable/complete. |
| R1-S4 | Risks | high | Add a snapshot integrity guard: hash input files at checkpoint time and verify hashes before repair; if mismatched, skip repair and escalate. | Prevents applying repairs to stale or drifted code, which can corrupt valid changes. | Section 2 (Core Pipeline) near REQ-RPL-006 | Unit test where file changes after checkpoint; repair is skipped with a clear reason. |
| R1-S5 | Validation | medium | Add acceptance criteria and tests for routing union/dedup ordering and per-file scoping, plus a test that non-repairable categories skip without staging side effects. | Ensures routing determinism and prevents silent scope creep. | Section 9 (Acceptance Criteria) | Unit tests for step order and skip behavior; verify no staging dir created on skip. |
| R1-S6 | Ops | medium | Specify staging and artifact directory lifecycle: unique per feature+attempt (timestamp/uuid), cleanup on success/failure, and optional retention window for debugging. | Avoids collisions in concurrent runs and limits disk bloat over time. | Section 2 (REQ-RPL-006) or Section 6 (Observability) | Integration test verifies unique staging path and cleanup/retention behavior. |
| R1-S7 | Security | high | Enforce path traversal and symlink safeguards when copying to staging: reject absolute/parent paths, ensure resolved paths stay under `project_root`, and copy with `follow_symlinks=False`. | Prevents overwriting arbitrary files and reduces risk from generated path injection. | Section 2 (REQ-RPL-006) or new Security requirement | Security unit tests with `../` paths and symlinked files that must be rejected. |

#### Review Round R2

- **Reviewer**: Claude Opus 4.6 (convergent review)
- **Date**: 2026-03-03
- **Scope**: Code-validated review focused on signature fidelity, semantic gaps in the non-destructive guarantee, import completion feasibility, checkpoint error parseability, and integration sequencing

**Endorsements from R1:**

- **R1-S1** (per-file routing): Strongly endorsed — source code confirms `CheckpointResult.errors` entries are prefixed with filename (e.g., `"email_server.py: ModuleNotFoundError: ..."`), making per-file routing both feasible and necessary.
- **R1-S2** (RepairConfig): Endorsed — codebase uses `@dataclass` config pattern extensively (`ModeConfig` at `prime_contractor.py:222`, `WorkflowConfig` at `artisan_contractor.py:386`, `FinalTestingConfig` at `final_testing.py:244`). A `RepairConfig` following the `ModeConfig.for_mode()` factory pattern would be idiomatic.
- **R1-S4** (snapshot integrity guard): Endorsed — `_snapshot_target` uses `shutil.copy2()` without hash verification (`integration_engine.py:440`). Process crash between snapshot write and dict registration (line 441) can leave stale sidecars with no integrity check.
- **R1-S6** (staging lifecycle): Endorsed — current staging at `.startd8/staging/` is shared; repair needs isolated per-feature+attempt directories to avoid collisions and enable post-mortem analysis.
- **R1-S7** (path traversal): Endorsed — `sanitize_path()` exists in `integration_engine.py` but staging copy paths are not yet validated through it.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Feasibility | critical | REQ-RPL-102 (Import Completion) understates adaptation complexity. The micro-prime `_step_import_completion` (`repair.py:340–412`) is **manifest-bound**: it only adds imports listed in `ForwardFileSpec.imports`. At the contractor level, there is no `ForwardFileSpec` — imports missing from the manifest are silently dropped. The requirement MUST specify the import discovery mechanism: (a) infer from `CheckpointResult.errors` regex parsing of `ModuleNotFoundError`/`ImportError` strings, (b) consult a project-level import map, or (c) explicitly scope to known-module imports only and document the limitation. | Without specifying the import source, implementers will either build an unbounded discovery system (over-engineering) or silently skip most import errors (under-delivering). The current micro-prime approach works because manifests enumerate all imports; contractor-level repair has no manifest equivalent. | REQ-RPL-102 body, replace "Reuse: Lift and extend" paragraph with explicit import source specification | Unit test: inject `ModuleNotFoundError: No module named 'grpc'` into checkpoint errors; verify import_completion adds `import grpc` — this test cannot pass without specifying the import discovery mechanism. |
| R2-S2 | Completeness | critical | The non-destructive guarantee (REQ-RPL-003) is **syntax-only**: `ast.parse()` validates Python grammar but not semantic correctness. A repair step can pass the guard while introducing undefined names, broken type contracts, or circular imports. The requirement MUST either: (a) acknowledge this limitation explicitly ("non-destructive guarantee covers syntax only; semantic regressions are caught by re-checkpoint"), or (b) extend the guard to include an import-check step between each repair step. | The current micro-prime guard (`repair.py:474–488`) uses `_try_parse()` which wraps code in `class _Wrapper:` for methods and does bare `ast.parse()` for functions — purely syntactic. Implementers may assume "non-destructive" means "no regressions of any kind," leading to undertested semantic paths. | REQ-RPL-003 body, add a "Limitations" subsection after the 3-step guard description | Property test: generate valid Python with all imports resolved; apply `_step_import_completion` that adds a duplicate import; verify guard does NOT revert (because code still parses) — proving semantic regressions pass the guard. |
| R2-S3 | Interfaces | high | REQ-RPL-001 signature (`run_repair_pipeline(files, checkpoint_result, context)`) diverges from the micro-prime signature it claims to mirror (`run_repair_pipeline(code, element, file_spec)`). The micro-prime version operates on a single code string with element+file metadata; the proposed version operates on a `dict[Path, str]` with checkpoint results. This is not a "lift" — it is a new interface. The requirement should drop the "mirrors micro_prime" claim and instead specify: (a) how per-file iteration is orchestrated, (b) whether steps receive all files or one file at a time, (c) how cross-file dependencies (e.g., one file imports from another) are handled during repair. | Claiming "mirrors" sets an expectation of minimal adaptation. In reality, the adaptation is substantial: element→file promotion, manifest→checkpoint context switch, single-string→multi-file orchestration. Understating this creates estimation risk. | REQ-RPL-001 Rationale paragraph and Section 10 (Key Reuse Summary) row for `run_repair_pipeline` | Review: verify the Rationale no longer claims "mirrors" but instead describes the concrete adaptations required. |
| R2-S4 | Data | high | `CheckpointResult.errors` is a `List[str]` of unstructured stderr text (`checkpoint.py:53`). The format varies by check type: import checks prefix with filename (`"email_server.py: ModuleNotFoundError: ..."`), syntax checks use Python's traceback format, lint checks use ruff's `{file}:{line}:{col}: {code} {message}` format. REQ-RPL-202 proposes structured diagnostics but does not specify the **parsing rules** for each checkpoint type. Add a regex/pattern specification per checkpoint type so the parser is deterministic and testable. | Without explicit patterns, each implementer will write different regexes, creating fragile parsing. The current `check_imports()` at `checkpoint.py:265–267` already extracts only the last stderr line — information is lost. Specifying patterns up front prevents both over-parsing (brittle) and under-parsing (lossy). | REQ-RPL-202 body, add a "Parsing Patterns" table mapping checkpoint name → error format → extraction regex | Unit tests per checkpoint type: feed known error strings, verify parsed `SyntaxDiagnostic`/`ImportDiagnostic`/`LintDiagnostic` fields match expected values. |
| R2-S5 | Sequencing | high | REQ-RPL-302 (Extended Pre-Merge Auto-Fix) proposes running repair steps BEFORE the existing ruff auto-fix, but the actual integration point matters: the current ruff fix runs at `integration_engine.py:1076–1088` AFTER merge and BEFORE checkpoint. If repair steps also run after merge but before ruff, their output will be further modified by ruff's `--unsafe-fixes`. If repair steps run before merge, they operate on generated files that haven't been placed in context yet. The requirement MUST specify the exact insertion point relative to: (1) merge (`_merge_files`, line ~1052), (2) ruff auto-fix (line ~1076), and (3) checkpoint (`run_all_checkpoints`, line 1093). | The three operations (merge, lint-fix, checkpoint) interact: repair before ruff means ruff may undo repairs; repair after ruff means ruff's changes are in scope for the non-destructive guard. The ordering affects both correctness and attribution. | REQ-RPL-302, add "Execution Order" subsection specifying placement relative to merge/ruff/checkpoint | Integration test: inject a file with both fence artifacts and lint violations; verify repair+ruff+checkpoint produce correct output regardless of ordering. |
| R2-S6 | Completeness | medium | REQ-RPL-203 states "successful repair does not consume retry" but does not address the inverse: **does a failed repair consume a retry?** The current retry counter is `feature.integration_attempts` (incremented at `queue.py:364` via `integrating_feature()`). If repair is attempted inside `integrate_feature()` (REQ-RPL-200), the attempt counter has already been incremented before repair runs. Specify whether: (a) repair failure is a distinct counter (`repair_attempts`), (b) repair failure increments the existing counter (current implicit behavior), or (c) the attempt counter is decremented on repair-only failure. | Ambiguity here means implementers may accidentally double-count attempts (once for integration, once for repair) or never count them (if repair swallows the failure). This directly affects the max-retry budget calculation. | REQ-RPL-203 body, add "Failed Repair" handling specification | Unit test: trigger 3 repair failures + 3 regen failures; verify total attempts tracked matches specification (not 6, not 3, but whatever the requirement specifies). |
| R2-S7 | Risks | medium | The requirements assume sequential feature processing (which is currently true — `prime_contractor.py:2239–2268` processes features one-by-one). However, `integration_engine.py` stores snapshots in an in-memory dict (`_pre_integration_snapshots`), and if future parallelism is introduced, repair's staging copies + integration's snapshot copies would race. Add an explicit **concurrency assumption** statement: "The repair pipeline assumes single-threaded feature processing. If parallelism is introduced, staging directories and snapshot state require external synchronization." | Without this statement, future developers may parallelize feature processing and encounter silent corruption from concurrent snapshot/staging writes. Documenting the assumption prevents a class of future bugs. | Section 1 (Preamble), new subsection "1.7 Concurrency Assumptions" | Code review: verify no thread pool or async usage in process_feature path; verify assumption holds against current codebase. |
| R2-S8 | Completeness | medium | REQ-RPL-103 (Bracket/Paren Balance) specifies "AST-aware insertion" but the actual AST is unparseable when brackets are unbalanced (that's why there's a `SyntaxError`). The requirement contradicts itself: you cannot use AST analysis on code that fails to parse due to bracket imbalance. Specify the actual algorithm: (a) token-level scanning with scope tracking, (b) line-by-line delimiter counting, or (c) heuristic append of closing delimiters at EOF. Each has different failure modes. | "AST-aware insertion" is aspirational but technically impossible for the exact case this step is designed to handle. Implementers will discover this contradiction during implementation and make ad-hoc decisions. | REQ-RPL-103 Implementation paragraph, replace "AST-aware insertion" with the actual algorithm specification | Unit test: inject code with unclosed `(` at line 50 of 100; verify the closing `)` is inserted at the correct scope level (not just appended at EOF). |
| R2-S9 | Validation | medium | Section 9.1 item 2 specifies "property-based test (e.g., Hypothesis) SHALL verify that no repair step sequence makes valid Python code invalid." This is underspecified: (a) what constitutes "valid Python" — syntactically valid (`ast.parse`) or semantically valid (imports resolve, names defined)? (b) what is the input domain — arbitrary valid Python, or only code patterns the LLM typically generates? (c) what step sequences — all permutations, or only routing-table-specified sequences? Without bounds, this test is either trivial (syntax only, single steps) or intractable (semantic validity, all permutations). | Unbounded property tests are either never written (too complex) or written trivially (too weak). Specifying the exact property, input domain, and sequence space makes the test achievable and meaningful. | Section 9.1 item 2, expand with input domain, validity definition, and sequence constraints | Meta-test: verify the property test runs in <30 seconds with 200 examples and covers all routing-table sequences. |
| R2-S10 | Consistency | low | Minor line reference discrepancies found during source validation: `CheckpointResult` ends at line 73 (not 74), `RepairStepResult` ends at line 64 (not 65), `_snapshot_target` ends at line 448 (not 468 — the range 421–468 encompasses both `_snapshot_target` and `_restore_target`). These don't affect correctness but should be corrected to maintain document credibility for future reviewers who cross-reference. | Inaccurate line references erode trust in the document and waste reviewer time on re-verification. | Section 1.6 (Key References) table, update 3 line ranges | Grep for each function name; verify line numbers match. |

#### Review Round R3

- **Reviewer**: Claude Opus 4.6 (convergent review, round 2)
- **Date**: 2026-03-03
- **Scope**: Post-v1.1.0 review focused on shared-abstraction feasibility, protocol compatibility with actual micro-prime step signatures, Phase 0 boundary clarity, and re-validation pluggability

**Prior suggestions addressed by v1.1.0:**

- **R2-S3** (drop "mirrors" claim): **ADDRESSED** — REQ-RPL-001 rationale now says "architecturally distinct" and describes concrete adaptations. Candidate for Appendix A.
- **R2-S7** (concurrency assumptions): **ADDRESSED** — Section 1.6.5 now explicitly documents the sequential processing assumption. Candidate for Appendix A.

**Endorsements from R1/R2 (still untriaged):**

- **R1-S1** (per-file routing): Still endorsed — Section 1.6.1 discusses it narratively, but no requirement body (REQ-RPL-002/004) has been updated to mandate per-file routing.
- **R1-S2** (RepairConfig): Still endorsed — mentioned in strategy sections but no REQ-RPL requirement specifies the dataclass.
- **R2-S1** (import completion feasibility): **Strongly re-endorsed** — R3 source validation confirms the gap is even wider than R2 reported (see R3-S2 below).
- **R2-S4** (checkpoint parsing rules): Still endorsed — no change in v1.1.0.
- **R2-S8** (bracket balance contradiction): Still endorsed — no change in v1.1.0.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Feasibility | critical | The `RepairStep` protocol signature `(code: str, context: RepairContext, file_path: Path) -> RepairStepResult` is **incompatible with 2 of the 4 "shared" steps**. Source validation confirms: `_step_indent_normalize` (`repair.py:194`) accesses `element.parent_class` to wrap methods in `class _Wrapper:` for AST parsing. `_step_ast_validate` (`repair.py:421`) does the same. Without `parent_class`, method-level code fails validation. The proposed `RepairContext` has no element metadata field. **Resolution options:** (a) Add `Optional[ElementContext]` to `RepairContext` carrying `parent_class`, `element_kind`, `element_name` for micro-prime; contractor sets it to `None` and uses file-level `ast.parse()` instead of element-level `_try_parse()`. (b) Make the non-destructive guard and ast_validate level-aware: use `_try_parse(code, element)` at micro-prime, use `ast.parse(code)` at contractor. (c) Accept that only `fence_strip` is truly "shared unchanged" and the other 3 require level-specific adapters. | The document claims "The same step implementations are shared between micro-prime and contractor levels" (Section 3 preface). Source code proves this is false for 3 of 4 steps. Overstating shareability creates estimation risk and Phase 0 surprises. Each micro-prime step function has signature `(code, element: ForwardElementSpec, file_spec: Optional[ForwardFileSpec])` — not `(code, context: RepairContext, file_path: Path)`. | Section 1.2.1 "What is shared" list, Section 3 preface "Abstraction note", and REQ-RPL-007 protocol definition. Revise to specify which steps are truly shared vs. which need level-specific adapters. | Unit test: run `_step_indent_normalize` on method-level code (e.g., `def foo(self):`) through the proposed protocol with `RepairContext(parent_class=None)` — verify it fails or produces wrong indentation because the method wrapper context is missing. |
| R3-S2 | Feasibility | critical | `_step_import_completion` is **two completely different algorithms** behind the same name. Micro-prime iterates `ForwardImportSpec` objects from `file_spec.imports` (`repair.py:382–396`), accessing `.kind`, `.module`, `.names`, `.alias` — structured manifest data that enumerates every expected import. Contractor-level must parse `ModuleNotFoundError`/`ImportError` strings from `CheckpointResult.errors` — unstructured stderr text with no manifest. These share zero implementation code. Calling this a "shared implementation refactored into RepairStep protocol" is misleading. **Resolution:** Specify that `import_completion` has TWO implementations behind the `RepairStep` interface: `ManifestImportCompletion` (micro-prime, uses `ForwardFileSpec.imports`) and `ErrorDrivenImportCompletion` (contractor, parses checkpoint errors). The protocol is shared; the implementation is not. | The document says "Shared implementation: Refactor `_step_import_completion`" (REQ-RPL-102). But the micro-prime function accesses `imp.kind`, `imp.module`, `imp.names`, `imp.alias` from `ForwardImportSpec` objects — none of which exist in the proposed `RepairContext`. The contractor algorithm (parse error strings) is fundamentally different. Pretending this is one shared function will cause Phase 0 to fail or produce a lowest-common-denominator implementation that works at neither level. | REQ-RPL-102 body. Replace "Shared implementation" framing with "Two implementations, one protocol" framing. Specify both algorithms explicitly. | Unit test: verify `ManifestImportCompletion` works with `ForwardFileSpec.imports` input; verify `ErrorDrivenImportCompletion` works with `CheckpointResult.errors` input; verify both return `RepairStepResult` through the same protocol. |
| R3-S3 | Architecture | high | REQ-RPL-008 (Re-Checkpoint After Repair) specifies `IntegrationCheckpoint.run_all_checkpoints()` which is **contractor-only infrastructure**. Source validation confirms: `IntegrationCheckpoint.__init__()` (`checkpoint.py:92–112`) requires `project_root` (filesystem), `src_dirs` for module resolution, and runs subprocesses (`py_compile`, `ruff`, `pytest`). Micro-prime operates on in-memory code strings with no filesystem anchor. Micro-prime's post-repair validation is `_structural_verify()` (`engine.py:573+`) — a single `ast.parse()` call. **Resolution:** Make REQ-RPL-008 level-aware. Define a `Validator` protocol: contractor passes `IntegrationCheckpoint`, micro-prime passes a lightweight `SyntaxValidator` that wraps `_structural_verify()`. Add this to the "What differs" table in Section 1.2.1. | REQ-RPL-008 is marked P0 but cannot be implemented at the micro-prime level as written. Phase 0 (micro-prime PoC) will hit this immediately: there's no `IntegrationCheckpoint` to call. Either Phase 0 skips REQ-RPL-008 (leaving a core P0 requirement unvalidated) or it implements a micro-prime-specific validator (not specified in the requirements). | REQ-RPL-008 body. Add level-specific validation specifications. Update Section 1.2.1 "What differs" table to include the Validator row explicitly. | Integration test at micro-prime level: run repair pipeline end-to-end; verify post-repair validation uses `ast.parse()` (not `IntegrationCheckpoint`). Integration test at contractor level: verify `IntegrationCheckpoint.run_all_checkpoints()` is invoked. |
| R3-S4 | Completeness | high | The routing table (Section 8, REQ-RPL-002) maps `CheckpointResult.errors` patterns, but **micro-prime has no `CheckpointResult`**. Micro-prime validation produces a `SyntaxError` exception (or success) from `ast.parse()`. The routing table's input is contractor-specific. For Phase 0 to work, specify the micro-prime routing input: (a) `SyntaxError` message strings from `ast.parse()`, (b) `_structural_verify()` boolean result, or (c) a micro-prime-specific `MicroPrimeCheckResult` adapter that wraps parse errors into a `CheckpointResult`-compatible structure. Without this, Phase 0 cannot implement the routing table. | Phase 0 introduces the routing table at the micro-prime level (Section 11: "Introduce RepairConfig and routing table at micro-prime level"). But the routing table's defined input (`CheckpointResult.errors`) doesn't exist at micro-prime level. This is a chicken-and-egg problem: the routing table can't be validated at micro-prime without specifying what it routes ON at that level. | Section 8 (Routing Table) header — add a "Level-Specific Input" note. REQ-RPL-002 — specify that the router accepts an abstracted diagnostic input, not raw `CheckpointResult`. | Unit test: feed a `SyntaxError("unexpected EOF while parsing")` (micro-prime style) into the router; verify it selects `fence_strip → bracket_balance → ast_validate`. |
| R3-S5 | Completeness | high | **Phase 0 has no exit criteria.** Section 1.2.2 says "Validate the abstraction against micro-prime's existing test suite" and Section 9.4 item 12 says "all existing micro_prime/repair.py tests SHALL pass." But Phase 0 also introduces NEW capabilities (RepairConfig, routing table, RepairStep protocol). There are no acceptance criteria for: (a) the shared module existing at a specified location, (b) `RepairConfig` being functional, (c) the routing table producing correct step sequences, (d) at least one step (fence_strip) working through the protocol end-to-end. Without exit criteria, Phase 0 is unbounded — you can't tell when it's done. | Phase 0 is the proof of concept that de-risks Phase 1. If the exit criteria are only "regression tests pass," the refactoring could be trivially done (just rename the module) without proving the abstraction actually works. Specific deliverables and tests for new capabilities make Phase 0 a genuine proof of concept. | Section 1.2.2 Phase 0 description. Add a numbered exit criteria list. Also add Phase 0 acceptance criteria to Section 9. | Review: verify all Phase 0 exit criteria are testable and Phase 0 deliverables are enumerated. |
| R3-S6 | Architecture | medium | **Shared module location unspecified.** Section 10.1 says "shared `repair/` module" but doesn't specify the Python package path. This matters for imports, test discovery, and whether micro-prime imports from the shared module or vice versa. Options: (a) `src/startd8/repair/` — new top-level package, clean separation, (b) `src/startd8/shared/repair/` — grouped with other shared modules if any, (c) expand `src/startd8/micro_prime/repair.py` into `src/startd8/micro_prime/repair/` package — minimal import path changes but muddies the "shared" framing. The choice affects whether contractor code imports from `startd8.repair` or `startd8.micro_prime.repair`. | Import paths are a public API surface. Choosing the wrong location in Phase 0 means a breaking import path change in Phase 1 (when contractors start importing from it). Deciding now avoids churn. | Section 10.1 header or new subsection "10.0 Module Layout". | Code review: verify the chosen path doesn't conflict with existing modules; verify both micro-prime and contractor code can import from it cleanly. |
| R3-S7 | Data | medium | **The "shared steps" claim should be quantified honestly.** Source validation shows: (1) `fence_strip` — truly shared, no element metadata needed. (2) `indent_normalize` — needs `parent_class` for method context; requires adapter or protocol extension. (3) `import_completion` — completely different algorithm at each level (manifest vs. error-driven); two implementations behind one interface. (4) `ast_validate` — needs `parent_class`; same adapter issue as indent_normalize. **Net: 1 step is truly shared, 2 need adapters, 1 needs two implementations.** Section 9.4 item 11 ("At least 4 repair steps SHALL be RepairStep protocol implementations shared between micro-prime and contractor levels") should be revised to reflect this. | Overstating shareability leads to underestimated Phase 0 scope. If 3 of 4 "shared" steps require adapters or dual implementations, that's significant work beyond a simple refactor. Honest accounting lets you plan Phase 0 accurately. | Section 9.4 item 11. Revise to: "At least 4 repair steps SHALL implement the RepairStep protocol. Of these, fence_strip is shared unchanged; indent_normalize and ast_validate require level-specific element context adapters; import_completion requires level-specific implementations behind the shared interface." | Review: verify the characterization matches source code analysis. |
| R3-S8 | Observability | medium | REQ-RPL-401 metrics use `feature` as a label on `repair_attempts_total`, `repair_success_total`, and `repair_wall_clock_ms`. In a pipeline run with 15–40 uniquely-named features, this creates **unbounded label cardinality** — a well-known Prometheus anti-pattern that causes high memory usage in Mimir/Prometheus and slow queries. **Resolution:** (a) Replace `feature` label with bounded labels: `error_category` (syntax/import/lint), `route_confidence` (high/medium/low), `step_name`. (b) Use `feature` only on the histogram (`repair_wall_clock_ms`) where cardinality is less harmful. (c) Record per-feature detail in the OTel span attributes (REQ-RPL-400) where cardinality is not a concern, and keep Prometheus metrics bounded. | The existing SDK metrics (in `CostTracker`) use bounded labels like `provider`, `model`, `operation` — not per-feature labels. Following the established pattern prevents observability infrastructure issues. | REQ-RPL-401 metrics table. Replace `feature` label with bounded alternatives on counter metrics; keep per-feature detail in span attributes only. | Query test: simulate 40 features, verify Prometheus scrape response stays under 1KB for repair metrics (bounded cardinality). |
| R3-S9 | Architecture | low | Section 1.5 "Proposed Failure Flow" diagram still shows only the contractor flow (GENERATE → MERGE → CHECKPOINT). Now that v1.1.0 establishes micro-prime as the Phase 0 proof of concept, consider adding a parallel micro-prime flow diagram showing GENERATE → VALIDATE → REPAIR → RE-VALIDATE, so readers can see both levels side by side. | The document now has extensive narrative about two levels (Sections 1.2.1, 1.6) but only one flow diagram. A micro-prime diagram would make the architectural relationship concrete and visual. | Section 1.5, add a second diagram labeled "MICRO-PRIME FLOW" after the existing contractor diagram. | Visual review: verify both diagrams use consistent terminology and the level differences are apparent. |

#### Review Round R4 (Low-Hanging Fruit)

- **Reviewer**: Antigravity
- **Date**: 2026-03-03
- **Scope**: Outsized-value extensions to the repair UX and operational utility.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-S1 | UX | medium | **Traceability Comment:** Add a transient header comment to repaired files in the staging area: `# [REPAIRED BY STARTD8: {steps}]`. | Clearly distinguishes between LLM-authored code and SDK-repaired code during the manual review phase. | Section 3 (Layer 2: Repair Steps) | Unit test: run repair, verify header exists in `repaired_code` but not in `original_code`. |
| R4-S2 | CLI | low | **Interactive Repair Flag:** Introduce `--interactive-repair` in the CLI. When a repair is possible, show a `git diff` style preview and prompt: `Repairable error detected. Apply fix? [y/N]`. | Empowers developers to audit deterministic changes before they are committed to the project, building trust in the pipeline. | Section 5 (Artisan Integration) or Section 8 (Routing Table) | Manual verification: run CLI with flag, observe diff preview and prompt. |
| R4-S3 | Ops | low | **Standalone Repair Command:** Add `startd8 repair [FILES]` as a direct CLI command that runs the pipeline on local files (ignoring the checkpoint-trigger loop). | Useful for manually fixing files that failed in a previous run or for "cleaning up" files before commit without running a full workflow. | Section 2 (Core Pipeline) or Section 5 (Artisan Integration) | Manual verification: run `startd8 repair path/to/file.py` and verify syntax/fences are fixed. |
| R4-S4 | Observability | low | **Diff Visualization in Logs:** For successful repairs, print a compact "Summary of Changes" in the terminal (e.g., `+ Added 'import typing' to line 1`). | Provides immediate feedback on what the repair pipeline actually did, reducing reliance on searching through logs or spans. | Section 6 (Observability & Attribution) | Unit test: verify log output contains specific fix summaries. |
| R4-S5 | Maintenance | low | **"Repair-Ready" Metadata:** Include a `repair_count` and `last_repair_date` in the `DashboardRef` or `ObservabilityManifest` for files that undergo repair. | Helps identify "stable but brittle" code that frequently requires automatic patching, highlighting candidates for manual refactoring. | Section 6 (Observability & Attribution) | Integration test: verify manifest tracks repair counters for implicated files. |

#### Review Round R5

- **Reviewer**: Codex
- **Date**: 2026-03-03 22:39:38 UTC
- **Scope**: Focused on remaining gaps in Risks and Security; checked other areas for cross-cutting gaps

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-S1 | Risks | high | Add repair delta guardrails: if a repair step changes more than a configured percentage or line count in a file, treat the attempt as low-confidence and skip/escalate rather than swapping staged files. | Prevents deterministic repair from making large unintended edits that masquerade as "fixes" and protects against silent semantic drift. | Section 2 (Core Pipeline) near REQ-RPL-006/007 | Unit test: a step that changes >50% of lines triggers a skip with a clear `skipped_reason` and no staged swap. |
| R5-S2 | Risks | medium | Enforce per-step and total repair timeouts (hard caps) and surface timeout as a distinct skip reason; tie defaults to the 5s wall-clock budget. | Prevents runaway steps or subprocess hangs from stalling the workflow while keeping deterministic repairs within the promised performance envelope. | Section 9.2 (Performance Requirements) and REQ-RPL-008 | Integration test with a step that sleeps beyond the cap; verify timeout aborts repair and increments `repair_attempts_total{outcome=skipped}`. |
| R5-S3 | Security | high | Require subprocess hardening for ruff/py_compile/pytest: `shell=False`, argv-based path passing (no shell interpolation), and a sanitized environment that does not inherit secrets. | Generated filenames or environment leakage should not be able to trigger shell injection or secret exposure during repair and re-checkpoint. | REQ-RPL-105 and REQ-RPL-008 | Security test using a file path containing shell metacharacters; verify no shell execution and subprocess argv is safe. |
| R5-S4 | Security | medium | Sanitize and redact diagnostic strings before logging or persisting (repair attempt artifacts and retry context): strip control characters, truncate long lines, and redact obvious secrets. | Prevents log injection, terminal control abuse, and accidental secret leakage from test output or error strings. | Section 6 (Observability) and REQ-RPL-204 | Unit test with ANSI control codes and a fake API key in stderr; verify stored/logged text is sanitized and redacted. |

#### Review Round R6

- **Reviewer**: Claude Opus 4.6 (convergent review, round 3)
- **Date**: 2026-03-03
- **Scope**: Post-triage v1.2.0 review focused on repair-routing feasibility against actual checkpoint flow (advisory downgrade conflict), hook location accuracy vs. rollback timing, RepairConfig specification gap, Phase 0 scope for micro-prime-only steps, and REQ-RPL-009/205 underspecification

**Triage validation (Appendix A/B):**

- Appendix A (24 applied): Spot-checked 8 entries against requirement bodies — all applied as claimed. The `element_context` addition to REQ-RPL-007 (R3-S1/7) is correctly reflected. The dual-import split in REQ-RPL-102 (R3-S2) is accurately captured.
- Appendix B (5 rejected): Rationale is sound. R1-S4 (snapshot hash integrity) rejection is reasonable given Phase 0 scope, though R5-S1 (repair delta guardrails) covers a related safety concern from a different angle.

**Endorsements from R5 (untriaged):**

- **R5-S1** (repair delta guardrails): **Endorsed** — reasonable safety net. Suggest the threshold be per-step (not cumulative), since a sequence of 5 small changes may each be individually acceptable but cumulatively large. A per-step `max_delta_lines` or `max_delta_pct` on `RepairStep` protocol would be more precise.
- **R5-S2** (per-step timeouts): **Strongly endorsed** — source validation confirms existing checkpoint subprocesses have timeouts (`_SYNTAX_CHECK_TIMEOUT_SECONDS=30`, `_IMPORT_CHECK_TIMEOUT_SECONDS=30`, `_LINT_CHECK_TIMEOUT_SECONDS=60` at `checkpoint.py:31–34`). Repair steps that spawn subprocesses (e.g., `extended_lint_fix` via `ruff`) need their own timeouts. Given the 5s total wall-clock budget (Section 9.2), individual step timeouts should be ~1–2s.
- **R5-S3** (subprocess hardening): **Endorsed with qualification** — source validation confirms all subprocess calls use `shell=False` (good — no shell injection risk from filenames). However, `check_imports()` at `checkpoint.py:254` explicitly spreads `os.environ` (`env={**os.environ, "PYTHONPATH": pythonpath}`), and all other subprocess calls inherit the parent environment by default. The shell injection concern is LOW risk, but the environment inheritance concern is MEDIUM risk — API keys in env vars would be visible to subprocesses. Suggest focusing the requirement on env sanitization rather than shell hardening.
- **R5-S4** (diagnostic sanitization): **Endorsed** — important for REQ-RPL-404 (repair attempt artifact) which persists diagnostics to disk, and for REQ-RPL-204 (retry context enrichment) which passes diagnostics to LLM prompts.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R6-S1 | Feasibility | critical | **Advisory checkpoint downgrade blocks repair routing for import and lint errors.** `integration_engine.py:1097–1110` downgrades Import Check and Lint Check from `FAILED` → `WARNING` before `summarize_results()`. This means `all_passed` returns `True` even when import/lint errors exist, and the rollback block (line 1128) never triggers. Since PrimeContractor delegates to the same engine (`self._engine.integrate()` at `prime_contractor.py:2166`), this applies to BOTH contractor flows. **The repair pipeline would never be triggered for import or lint failures** — its two highest-value repair targets (REQ-RPL-102, REQ-RPL-105). The advisory downgrade was added as a workaround because third-party packages aren't installed in the SDK venv (Run 1 lesson). **Resolution:** Make the advisory downgrade conditional: `if not config.repair_enabled: downgrade_to_warning()`. When repair is enabled, let import/lint failures remain FAILED so the repair pipeline can attempt a fix. If repair fails, THEN apply the advisory downgrade before escalating to regeneration. This preserves backward compatibility when repair is disabled. | Without this fix, the repair pipeline cannot reach 2 of its 3 primary use cases (import errors, lint errors). Only syntax errors (which are not advisory) would trigger repair. The entire ROI model in Section 1.3 assumes import and lint repair — if those are hidden by advisory downgrade, the pipeline's measurable savings drop dramatically. | REQ-RPL-300 (Artisan hook), REQ-RPL-200 (PrimeContractor hook), and a new "Advisory Downgrade Interaction" subsection in Section 1.6 or Section 4. | Integration test: enable `repair_enabled=True`, inject a file with `ModuleNotFoundError` in checkpoint results; verify the repair pipeline is invoked (not bypassed by advisory downgrade). Verify with `repair_enabled=False`, the existing advisory downgrade behavior is preserved. |
| R6-S2 | Architecture | critical | **REQ-RPL-200 hook location is post-rollback — repair needs pre-rollback access to files.** REQ-RPL-200 proposes hooking into `integrate_feature()` at `prime_contractor.py:2185–2188`. But `integrate_feature()` delegates entirely to `self._engine.integrate(unit, ...)` at line 2166, which handles the full checkpoint+rollback lifecycle internally (`integration_engine.py:1128–1160`). By the time line 2185 executes, the files have ALREADY been rolled back (line 1142–1148). The repair pipeline needs access to the generated files BEFORE rollback. **Resolution:** Either: (a) The repair hook must be inside `IntegrationEngine.integrate()` between checkpoint failure and rollback — consistent with REQ-RPL-300's placement. This means REQ-RPL-200 and REQ-RPL-300 are the SAME hook point, not two separate ones. Or (b) `IntegrationEngine.integrate()` must be refactored to return checkpoint results WITHOUT rolling back when repair is enabled, letting the caller decide. Option (a) is simpler and avoids refactoring the engine's public interface. | The proposed code in REQ-RPL-200 cannot work as written — `result.checkpoint_results` is returned from `_engine.integrate()` which has already rolled back. Attempting repair on rolled-back files would repair the pre-generation originals, not the generated code. This is a showstopper for the Phase 1 contractor MVP. | REQ-RPL-200 proposed flow code block and surrounding text. Align with REQ-RPL-300 so both hooks share the same integration point inside `IntegrationEngine.integrate()`. | Code review: trace the execution path from `integrate_feature()` through `_engine.integrate()` to the rollback block; verify the proposed hook has access to un-rolled-back files. |
| R6-S3 | Completeness | high | **`RepairConfig` dataclass has no field specification.** Appendix A says R1-S2 (RepairConfig) was applied ("Added to REQ-RPL-001/004"), and REQ-RPL-001 adds `config: RepairConfig` as a parameter. But no requirement defines the `RepairConfig` fields. The fields are scattered across 4 sections: `repair_enabled: bool` (REQ-RPL-201), `repairable_categories: set[str]` (REQ-RPL-201), `pre_checkpoint_repair: bool` (REQ-RPL-302), `repair_circuit_breaker_threshold: int` (REQ-RPL-502), `staging_root: Path` (implied by REQ-RPL-006). **Resolution:** Add a dedicated `RepairConfig` dataclass definition — either in REQ-RPL-004 (alongside RepairContext) or as a new REQ-RPL-010. Following the codebase's `ModeConfig.for_mode()` factory pattern (`prime_contractor.py:222`), include a `for_level()` factory that returns micro-prime defaults vs. contractor defaults. | Phase 0 implementers need to know what fields `RepairConfig` contains before they can implement it. Scattered field mentions across multiple sections create ambiguity and risk incomplete implementations. The R1-S2 triage says "applied" but the dataclass body was never written. | New requirement REQ-RPL-010 or expand REQ-RPL-004 with a `RepairConfig` subsection. | Review: verify the `RepairConfig` definition includes all fields mentioned across the document (grep for `config.` and `RepairConfig` to find implicit references). |
| R6-S4 | Completeness | high | **Phase 0 scope gap: 3 micro-prime-only steps not addressed.** Micro-prime has 7 repair steps (`repair.py:436–444`): fence_strip, over_generation_trim, bare_statement_wrap, indent_normalize, signature_reconcile, import_completion, ast_validate. The document discusses 4 as shared but says nothing about the other 3 (`over_generation_trim`, `bare_statement_wrap`, `signature_reconcile`). These are element-level-specific (they access `element.name`, `element.kind`, `element.signature`, `element.bases`). During Phase 0 refactoring, do they: (a) implement `RepairStep` protocol but live in a `micro_prime/steps/` subpackage, (b) remain as non-protocol private functions in `micro_prime/repair.py`, or (c) move to the shared module marked as micro-prime-only? This affects shared module layout (Section 10.3), test coverage expectations, and whether micro-prime's `run_repair_pipeline()` calls through the protocol for all 7 steps or only for the 4 shared ones. | Phase 0 is a refactoring exercise. If 3 of 7 steps are unaddressed, the refactoring is incomplete and the micro-prime regression test (Section 9.4 item 4: "all existing tests SHALL pass") may pass trivially without actually exercising the protocol for all steps. This creates a false sense of validation. | Section 1.2.2 Phase 0 description, and Section 10.1 (Shared Abstraction table). Add rows for the 3 micro-prime-only steps with explicit "remains in micro_prime" or "adapts to protocol" disposition. | Review: verify all 7 steps in `_REPAIR_STEPS` list (`repair.py:436–444`) have an explicit disposition (shared, adapted, or micro-prime-only). |
| R6-S5 | Completeness | high | **REQ-RPL-009 "transient" comment has no removal specification.** The requirement adds `# [REPAIRED BY STARTD8: {steps_applied}]` to repaired files in staging. REQ-RPL-006 step 5 says "replace originals with staged copies (atomic swap)" on success. This means the comment persists in the codebase after repair. But REQ-RPL-009 calls it "transient" without specifying when/how it's removed. Options: (a) stripped during atomic swap (truly transient — only visible during staging), (b) left in place for human review and removed manually, (c) overwritten by the next LLM generation cycle, (d) stripped by a post-repair cleanup step. Each has different implications for code hygiene and downstream tools. | If left unspecified, the comment will accumulate across repair cycles (each repair adds a new header). After 3 repairs, a file could have 3 `# [REPAIRED BY STARTD8: ...]` lines. If option (a), the comment never reaches the codebase and only aids debugging of the staging directory. The requirement should specify which behavior is intended. | REQ-RPL-009 body. Add a "Lifecycle" subsection specifying when the comment is removed. | Unit test: run repair twice on the same file; verify comment count matches the specified lifecycle (exactly 1 if replaced, 0 if stripped on swap, 2 if accumulated). |
| R6-S6 | Completeness | medium | **REQ-RPL-205 standalone CLI needs check-before-route specification.** `startd8 repair [FILES]` operates on local files outside the checkpoint-trigger loop. The routing table (Section 8) maps `CheckpointResult.errors` to repair step sequences. Without a preceding checkpoint, the CLI has no `CheckpointResult` to route on. Specify: (a) the CLI runs `check_syntax()` + `check_imports()` + `check_lint()` on the input files first, then routes based on the results; or (b) the CLI runs all repair steps in the canonical sequence without routing (simpler but wasteful); or (c) the CLI accepts a `--steps` flag to select specific steps (most flexible, most complex). | Without this specification, the CLI implementation will be ad-hoc. Option (a) is most consistent with the rest of the pipeline. Option (c) adds a useful debugging capability. The choice affects whether `IntegrationCheckpoint` is a dependency of the CLI command. | REQ-RPL-205 body. Add an "Input Discovery" subsection specifying how the CLI determines what's wrong without an existing checkpoint result. | Manual test: run `startd8 repair file_with_mixed_tabs.py`; verify the CLI detects the indentation issue and applies `indent_normalize` without requiring a prior checkpoint run. |
| R6-S7 | Data | medium | **RepairAttribution model framework mismatch: BaseModel vs. @dataclass.** The existing `RepairAttribution` at `models.py:37–52` is a Pydantic `BaseModel` with micro-prime-specific fields (`fence_stripped`, `trimmed`, `nodes_removed`, `bare_wrapped`, `params_changed`, `return_type_restored`). The proposed `FeatureRepairAttribution` in REQ-RPL-403 is an `@dataclass` with contractor-specific fields (`files_repaired`, `imports_added`, `lint_fixes`). The document says "extending micro_prime/models.py:37–52" but: (a) the fields are completely different, and (b) the base class is different. Specify whether the shared module uses Pydantic BaseModel (consistent with existing micro-prime models) or @dataclass (consistent with proposed contractor models), and whether `FeatureRepairAttribution` contains a `per_file: dict[str, RepairAttribution]` that reuses the existing micro-prime model or a new shared model. | Framework inconsistency between the existing model and the proposed model creates import confusion and serialization mismatches. If `RepairAttribution` stays as BaseModel and `FeatureRepairAttribution` is a dataclass, the `per_file` field nesting requires a serialization adapter. Note: the existing module already mixes BaseModel (`RepairAttribution`) and dataclass (`RepairStepResult`) at `models.py:37–64`, so this inconsistency is inherited, not new — but the shared module is an opportunity to unify. | REQ-RPL-403 body and Section 10.1 row for `RepairAttribution`. Specify the target framework (BaseModel or dataclass) for the shared module. | Code review: verify the chosen framework is consistent across all models in `src/startd8/repair/models.py`. |
| R6-S8 | Completeness | medium | **Phase 0 exit criteria still lack numbered testable deliverables.** ... | Replace aspirational text with a numbered checklist. | Section 1.2.2 Phase 0 description. | Review: verify each exit criterion is independently testable. |

#### Review Round R7: Mottainai & Forward Manifest Alignment

- **Reviewer**: Antigravity (Mottainai Audit)
- **Date**: 2026-03-03
- **Scope**: Reverse-engineering previous gaps to identify "low-hanging fruit" leveraging existing SDK capabilities (SCAFFOLD, ManifestRegistry, FLCM).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R7-S1 | Interfaces | high | **Inject `ForwardManifest` (FLCM) into `RepairContext`.** Repair steps must be aware of [BINDING] contracts to avoid "fixing" code into a state that violates a prescriptive interface. | Prevents repair-induced contract drift. Alignment with Mottainai Gap 10/40. | `RepairContext` (REQ-RPL-004) | Verify repair steps (e.g., Import Completion) prefer [BINDING] names/paths over LLM-derived ones. |
| R7-S2 | Correctness | medium | **Leverage SCAFFOLD Module Inventory in `ErrorDrivenImportCompletion`.** Use the pre-computed project module mapping (from SCAFFOLD) to resolve imports instead of broad grep or LLM inference. | Prevents hallucinated imports. Alignment with Mottainai Gap 39. | `ErrorDrivenImportCompletion` (REQ-RPL-102) | Unit test: missing local module is resolved correctly using the existing inventory. |
| R7-S3 | Efficiency | medium | **Use `ManifestRegistry` for Duplicate Removal (REQ-RPL-104).** Instead of ad-hoc AST parses, use the already-built (but often discarded) ManifestRegistry to identify redefinitions. | Leverages existing deterministic data. Alignment with Mottainai Gap 19. | `DuplicateRemoval` implementation | Verify duplicate detection uses the registry instead of re-parsing. |
| R7-S4 | Validation | high | **Add FLCM Contract Validation to Re-Checkpoint (REQ-RPL-008).** The re-checkpoint must verify that the repaired code still honors FLCM [BINDING] contracts. | Ensures the fix doesn't break interfaces. 04_FORWARD_MANIFEST Goal 3. | `Re-Checkpoint` (REQ-RPL-008) | Integration test: repair that violates a [BINDING] contract is caught by re-checkpoint. |
| R7-S5 | Traceability | low | **Include active Forward Contracts in `repair_attempt.json`.** Record which [BINDING] constraints were active during the repair attempt for auditability. | Provides a full provenance chain for repairs. Alignment with Mottainai Gap 20/27. | `RepairAttemptArtifact` (REQ-RPL-404) | Verify `repair_attempt.json` contains a `contracts` section. |
| R7-S6 | Context | medium | **Include `service_metadata` in `RepairContext`.** Protocol-aware repairs (e.g., OTel, gRPC vs HTTP) should be driven by the deterministically-derived service metadata. | Prevents protocol mismatches during repair. Alignment with Gap 16. | `RepairContext` (REQ-RPL-004) | Verify protocol-dependent steps read the metadata. |
| R7-S7 | Ops | low | **Update `ManifestRegistry` post-repair success.** If a repair adds/removes elements, the in-memory registry must be synchronized before subsequent feature processing. | Prevents stale registry data from affecting downstream blast-radius analysis. | `run_repair_pipeline` / `IntegrationEngine` hook | Verify registry is fresh after a repair that adds a function. |
| R7-S8 | Validation | high | **Validate repairs against `onboarding-metadata` parameter sources.** Check that deterministic values (ports, timeouts) are honored by the repair. | Prevents stochastic repair from overriding deterministic parameters. Alignment with Gap 2/3. | `RepairStep` protocol / `RepairContext` | Verify repair doesn't "invent" a port number different from the resolved one. |
