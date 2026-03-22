# Semantic Repair — Requirements

**Date:** 2026-03-17
**Status:** Draft — Layer 4 (Implementation Plan)
**Author:** Human + Agent collaboration
**Iteration:** 4 of 4 (high-level capabilities → detailed specifications)
**Derived From:** Run-062 post-mortem (0.99 score, 7 semantic issues uncaught), SEMANTIC_VALIDATION_V2 gap analysis, KZ-Q2

---

## 0. Document Evolution Strategy

This document follows an iterative deepening approach:

| Layer | Focus | Status |
|-------|-------|--------|
| **1. Capability Vision** | What can we fix? Why? What's the boundary? | **Complete** |
| **2. Architecture** | Where does repair sit in the pipeline? What are the interfaces? | **Complete** |
| **3. Category Specifications** | Per-category repair strategies, triggers, and constraints | **Complete** |
| **4. Implementation Plan** | Files, functions, tests, execution order | **This iteration** |

Each layer builds on the previous. We don't descend until the current layer is validated.

---

## 1. Problem Statement

The pipeline now detects semantic issues in generated code (L1–L10, Phases A–E). Run-062 demonstrates the gap:

| Feature | Semantic Issues | Disk Score | Impact |
|---------|----------------|------------|--------|
| PI-009 (locustfile.py) | `self.index()` method resolution, 2 orphaned functions | 0.94 | Runtime error on `on_start()` |
| PI-003 (email_server.py) | Discarded `os.environ.get` return | 0.96 | Silent config loss |
| PI-004 (email_client.py) | 2 unresolvable imports, 1 unreachable function | 0.86 | Import crash on load |

These issues are **detected, scored, and reported** — but they ship to disk unchanged. The current pipeline ends at diagnosis:

```
generate → repair (syntax/AST only) → semantic checks (detect) → score → commit
```

The missing capability:

```
generate → repair (syntax/AST) → semantic checks (detect) → SEMANTIC REPAIR → re-score → commit
```

---

## 2. Relationship to V2 Philosophy

SEMANTIC_VALIDATION_V2_REQUIREMENTS.md (REQ-SV2-1100) states:

> "Stage 3 does not auto-edit generated code. It fixes the inputs (prompts, seeds, context) that produce bad outputs."

This was the right philosophy when detection accuracy was low (~60% L1 true positive rate). The concern was valid: repairing based on unreliable signals teaches the Kaizen system wrong lessons.

**What has changed:**

1. **Detection accuracy improved.** L9 method resolution and L10 unreachable function have ~0% false positive rates across 20 runs. L1 import resolution is at ~80% TP after GCP alias fixes.
2. **Some defect classes are structural, not prompt-fixable.** `self.index()` in `locustfile.py` is a scope confusion error that no prompt instruction can reliably prevent — the LLM generates the class body referencing module-level names with `self.` because it sees them as "available functions."
3. **Upstream and downstream repair are complementary, not exclusive.** Prompt improvements (REQ-SV2-1300/1400) reduce defect frequency. Semantic repair catches residual defects. Both improve quality; neither alone is sufficient.

**The revised position:** Semantic repair is permitted for categories where:
- Detection false positive rate < 5% (per REQ-SV2-1000 gate)
- The repair is **deterministic and verifiable** (AST transform, not LLM re-generation)
- The repair preserves the file's overall intent (does not change functionality beyond fixing the specific defect)

Categories that require LLM re-generation (e.g., "generate a better implementation of this function") remain in the upstream-only camp per REQ-SV2-1100.

---

## 3. Capabilities

### Capability 1: Deterministic AST-Based Repair

**What:** Fix semantic issues that have a single, unambiguous correct transformation expressible as an AST rewrite.

**Why:** These are the safest repairs — no LLM involved, deterministic output, verifiable by re-running the same semantic check.

**Candidate categories:**

| Category | Issue | Repair Transform | Confidence |
|----------|-------|-----------------|------------|
| `method_resolution` | `self.index()` where `index` is module-level | Rewrite to `index(self)` | High — unambiguous when class has no `index` method |
| `discarded_return` | `os.environ.get("KEY")` as bare statement | Infer variable name from arg: `key = os.environ.get("KEY")` | Medium — variable naming is heuristic |
| `duplicate_main_guard` | Two `if __name__ == "__main__"` blocks | Remove the second block | High — always incorrect |

**Boundary:** This capability does NOT cover issues that require understanding intent (e.g., "which function should `empty_cart` be wired into?"). Those stay as warnings.

### Capability 2: Import Path Repair

**What:** Fix import statements that don't resolve, when the correct import path can be derived from project structure.

**Why:** Import resolution errors (PI-004: `from emailservice.email_server import EmailServiceStub`) are the highest-severity semantic defect — they crash on `import`. When the correct module exists as a sibling file, the fix is deterministic.

**Candidate categories:**

| Category | Issue | Repair Transform | Confidence |
|----------|-------|-----------------|------------|
| `import_resolution` (local namespace) | `from emailservice.email_server import X` | Rewrite to `from email_server import X` (flat layout) or `import email_server; X = email_server.X` | High — when sibling file exists and exports the symbol |
| `import_resolution` (proto stub) | `from emailservice import demo_pb2` | Rewrite to `import demo_pb2` | High — proto stubs are always top-level in generated projects |

**Boundary:** This capability does NOT fix imports from unknown third-party packages. If we can't find the target module in the project layout, the import stays flagged as an error.

### Capability 3: Dead Code Pruning

**What:** Remove or relocate functions that are defined but never referenced.

**Why:** Orphaned functions (`empty_cart`, `logout` in locustfile.py) indicate incomplete generation. They waste space and confuse readers, but removing them is safe because by definition nothing calls them.

**Candidate categories:**

| Category | Issue | Repair Transform | Confidence |
|----------|-------|-----------------|------------|
| `unreachable_function` | Module-level function never called | **Option A:** Delete the function. **Option B:** Add to `__all__` if it looks like a public API. | Low-Medium — deletion is destructive; the function may be intended for external callers |

**Boundary:** This is the lowest-confidence capability. Default behavior should be warning-only, with repair only when explicitly enabled. Wrong deletion is worse than dead code.

### Capability 4: LLM-Assisted Semantic Repair (Deferred)

**What:** Re-prompt the LLM with the specific semantic issue and ask for a targeted fix.

**Why:** Some defects (e.g., "function should be wired into TaskSet.tasks dict") require understanding intent that pure AST transforms can't capture.

**This capability is NOT part of the initial implementation.** It is documented here to define the boundary between what we build now (Capabilities 1–3) and what we defer. It maps to KZ-Q2 ("two-pass file-whole generation") and will be specified when Capabilities 1–3 are operational and we have data on residual defect rates.

---

## 4. Design Constraints

### DC-1: Repair Must Be Verifiable

Every repair is validated by re-running the same semantic check that flagged the issue. If the check still fires after repair, the repair is rolled back and the original issue is preserved.

### DC-2: Repair Must Be Attributable

Every repaired file carries metadata:
- Which semantic check triggered the repair
- What the original code was
- What the repaired code is
- Whether the repair was verified (re-check passed)

This feeds the Kaizen system: "repair X was applied N times across M runs" enables tracking whether upstream prompt fixes are reducing the need for downstream repair.

### DC-3: Repair Does Not Change Scores Silently

The postmortem report shows both pre-repair and post-repair scores. A file that scores 0.86 pre-repair and 1.0 post-repair is reported differently from a file that scores 1.0 natively. This prevents the Kaizen system from conflating "code was generated correctly" with "code was repaired to correctness."

### DC-4: Repair Is Opt-In Per Category

Each semantic repair category has an independent enable/disable flag. Default: disabled. Categories are enabled as their detection accuracy meets the gate criteria (FP rate < 5%, 10+ runs).

### DC-5: Repair Integrates with Existing Pipeline

Semantic repair uses the same `repair/` infrastructure (staging, rollback, attribution) as syntax repair. It does not create a parallel repair path.

---

## 5. Success Criteria (Layer 1)

These are capability-level success criteria. Per-category metrics will be defined in Layer 3.

| Criterion | Target |
|-----------|--------|
| Semantic repair reduces `PARTIAL:semantic` verdicts | ≥50% reduction (from current ~6% of features to ~3%) |
| No false repairs (repair introduces new defect) | 0 across 10 consecutive runs |
| Repair attribution visible in postmortem | 100% of repairs show pre/post scores |
| Kaizen trend distinguishes native quality from repaired quality | `avg_assembly_delta` computed on pre-repair scores, not post-repair |
| Pipeline latency increase | < 500ms per file (semantic repair is AST transforms, not LLM calls) |

---

## 6. Non-Goals

- **LLM-backed repair** — deferred to Capability 4 / KZ-Q2
- **Cross-file repair** — repairing file A based on content of file B (e.g., fixing imports by reading sibling modules' `__all__`). This is architecturally complex and deferred.
- **Replacing upstream prompt fixes** — semantic repair is a safety net, not a substitute for better prompts. REQ-SV2-1300/1400 remain active.
- **Repairing non-Python files** — Dockerfiles, requirements.in, YAML, HTML are out of scope for this iteration. **Note (2026-03-22):** C# deterministic repair (SQL parameterization) is now in scope via REQ-KZ-CS-402a–c in `KAIZEN_CSHARP_REQUIREMENTS.md`. The `.py`-only filter in `run_semantic_repair()` must be extended to dispatch by file extension.

---

## 7. Open Questions (for Layer 2)

| # | Question | Impacts |
|---|----------|---------|
| Q1 | Should semantic repair run before or after the existing syntax repair pipeline? | Pipeline ordering, staging interaction |
| Q2 | Should repair metadata live in `DiskComplianceResult` or in a new `SemanticRepairResult` structure? | Data model, postmortem integration |
| Q3 | For `discarded_return` repair, how do we infer the variable name? `key = os.environ.get("KEY")` vs `gcp_project_id = os.environ.get("GCP_PROJECT_ID")`? | Naming heuristic complexity |
| Q4 | For `import_resolution` repair, do we need to verify the target symbol exists in the sibling file (e.g., `email_server.py` actually exports `EmailServiceStub`)? | Repair confidence, cross-file analysis scope |
| Q5 | Should dead code pruning (Capability 3) be in the initial release, given its lower confidence? | Scope of v1 |
| Q6 | How does semantic repair interact with the resume cache? Does a repaired file produce a different checksum that invalidates cache? | Cache coherence |

---

## 8. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_V2_REQUIREMENTS.md](SEMANTIC_VALIDATION_V2_REQUIREMENTS.md) | Detection system this repair builds on; REQ-SV2-1000 gate criteria apply |
| [SEMANTIC_VALIDATION_V2_IMPLEMENTATION_PLAN.md](SEMANTIC_VALIDATION_V2_IMPLEMENTATION_PLAN.md) | Phases 5–7 detection hardening (must complete before repair activates) |
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Phase A-E validation; KZ-Q2 definition |
| [POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md](../repair-pipeline/POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md) | Existing repair infrastructure (DC-5: integrate, don't duplicate) |
| `src/startd8/repair/` | Implementation target — extend with semantic repair steps |
| `src/startd8/contractors/forward_manifest_validator.py` | Detection source — `validate_disk_compliance()` provides inputs |
| `src/startd8/contractors/prime_postmortem.py` | Scoring integration — pre/post-repair dual scoring (DC-3) |

---

## Layer 2: Architecture

---

## 9. Current Pipeline Topology

Understanding the existing flow is essential before deciding where semantic repair slots in. Two independent repair/validation paths exist today:

### Path A: Integration Engine (Contractor Pipeline)

```
IntegrationEngine._integrate_feature()
  │
  ├─ Step 1: pre-validate (checkpoint)
  │    └─ if FAILED → _attempt_pre_merge_repair()        ← syntax repair (pre-merge)
  │
  ├─ Step 2-4: merge loop (copy generated files → project root)
  │
  ├─ Step 5: post-merge checkpoint
  │    └─ if FAILED → _attempt_repair()                   ← syntax repair (post-merge)
  │                     └─ repair/orchestrator.py
  │                         └─ route_failures() → ordered steps → apply
  │
  ├─ Step 6: contract violation repair
  │
  ├─ Step 7: _run_semantic_checks()                       ← DETECT ONLY (warnings to log)
  │    └─ semantic_checks.run_semantic_checks()
  │    └─ [NO repair, NO scoring, NO feedback to pipeline]
  │
  └─ Step 8: advisory downgrade
```

### Path B: Post-Mortem (Scoring Pipeline)

```
PrimePostMortemEvaluator.evaluate()
  │
  ├─ _evaluate_disk_quality()                             ← runs validate_disk_compliance()
  │    └─ forward_manifest_validator.validate_disk_compliance()
  │         └─ AST parse, stubs, imports, duplicates, semantic issues
  │    └─ compute_disk_quality_score(compliance)
  │    └─ assembly_delta = requirement_score - disk_quality_score
  │
  └─ _detect_cross_feature_patterns()
       └─ assembly_quality_gap pattern (delta > 0.2)
```

### The Disconnect

Path A detects semantic issues but doesn't repair them and doesn't score them. Path B scores them but runs too late (post-mortem, after files are committed). There is no path where detection → repair → re-score happens in sequence on the same file before it's committed.

---

## 10. Architectural Decision: Where Semantic Repair Lives

### Option A: Extend Path A (Integration Engine)

Insert semantic repair between Step 7 (detect) and Step 8 (advisory downgrade):

```
Step 7:  _run_semantic_checks()         → detect issues
Step 7b: _attempt_semantic_repair()     → fix issues (NEW)
Step 7c: _re_run_semantic_checks()      → verify fixes (NEW)
Step 8:  advisory downgrade
```

**Pros:** Repairs happen before commit. Files on disk are already fixed. Postmortem scores reflect repaired state.
**Cons:** Integration engine is already ~1900 lines. Adds complexity to the hot path. Semantic checks currently use `semantic_checks.py` (simple), not `forward_manifest_validator.py` (full compliance suite).

### Option B: New Phase Between Integration and Postmortem

Add a semantic repair phase that runs after integration commits but before postmortem scoring:

```
INTEGRATE phase → files committed to disk
  ↓
SEMANTIC_REPAIR phase (NEW)
  ├─ validate_disk_compliance() on each file
  ├─ for each repairable issue: apply AST transform
  ├─ re-validate to confirm fix
  ├─ overwrite file on disk if verified
  └─ emit repair attribution metadata
  ↓
POST-MORTEM → scores reflect repaired state
```

**Pros:** Clean separation. Doesn't bloat integration engine. Uses the full `validate_disk_compliance()` suite (not the limited `semantic_checks.py`). Can run independently.
**Cons:** Files are committed-then-rewritten (two disk writes). Phase coordination overhead.

### Option C: Extend the Existing Repair Pipeline (repair/)

Add semantic repair steps to the existing `repair/` routing table and step registry. Semantic diagnostics from `validate_disk_compliance()` are translated to `SemanticDiagnostic` objects and fed through `route_failures()` → standard repair flow.

```
_attempt_repair()
  ├─ existing syntax/import/lint steps (unchanged)
  ├─ new: semantic_import_fix step
  ├─ new: semantic_method_resolution_fix step
  ├─ new: semantic_discarded_return_fix step
  └─ ast_validate (terminal step, unchanged)
```

**Pros:** Reuses all existing infrastructure (routing, staging, attribution, OTel, circuit breaker). `SemanticDiagnostic` already exists in `models.py`. `SemanticMethodFixStep` already exists as a pattern. Consistent with DC-5.
**Cons:** Requires bridging `forward_manifest_validator` output → `Diagnostic` objects. Current repair runs before semantic checks — need to add a second repair pass or reorder.

### Decision: **Option C (Extend Repair Pipeline) with a Second Pass**

**Rationale:**

1. **Infrastructure reuse.** The repair pipeline already has routing, staging, rollback, attribution, OTel metrics, circuit breaker, step effectiveness tracking, and the `RepairStep` protocol. Building a parallel system violates DC-5 and duplicates ~400 LOC of orchestration.

2. **`SemanticDiagnostic` and `SemanticMethodFixStep` already exist.** The routing table already has a `"semantic"` category entry. We're extending an existing pattern, not inventing a new one.

3. **Second pass is architecturally clean.** The integration engine already calls `_attempt_repair()` (syntax pass) and `_run_semantic_checks()` (detect pass) in sequence. Adding `_attempt_semantic_repair()` as a third step that feeds semantic check results back through the repair pipeline is a natural extension:

```
Step 5:  _attempt_repair()              → syntax/import/lint repair (existing)
Step 6:  contract violation repair       → (existing)
Step 7:  _run_semantic_checks()         → detect semantic issues (existing)
Step 7b: _attempt_semantic_repair()     → repair semantic issues (NEW)
Step 7c: _re_run_semantic_checks()      → verify repairs (NEW)
Step 8:  advisory downgrade             → (existing)
```

---

## 11. Data Flow Architecture

### 11.1 Detection → Diagnostic Translation

The semantic checks produce `SemanticIssue` objects (from `semantic_checks.py`) and issue dicts (from `forward_manifest_validator.py`). These need to be translated to `SemanticDiagnostic` objects for the repair pipeline.

```
forward_manifest_validator.validate_disk_compliance()
  → DiskComplianceResult.semantic_issues: List[Dict]
     │
     ▼
translate_to_diagnostics(semantic_issues, file_path)           (NEW)
  → List[SemanticDiagnostic]
     │
     ▼
route_failures(diagnostics, config)                            (EXISTING)
  → RepairRoute(steps=["semantic_import_fix", ...])
     │
     ▼
create_steps_from_route(route)                                 (EXISTING)
  → [SemanticImportFixStep(), ...]
     │
     ▼
orchestrator.run_element_repair() or run_file_repair()         (EXISTING)
  → RepairOutcome with attribution
```

### 11.2 New Diagnostic Subtype

Extend `SemanticDiagnostic` to carry the semantic issue category:

```python
@dataclass
class SemanticDiagnostic(Diagnostic):
    defect_type: str = ""        # existing: "missing_self", "datetime_confusion"
    semantic_category: str = ""  # NEW: "method_resolution", "import_resolution", "discarded_return"
    severity: str = "warning"    # NEW: from semantic issue dict
    symbol: str = ""             # NEW: the specific symbol involved
    line: int = 0                # NEW: source line number
```

### 11.3 Routing Extension

Extend the routing table to dispatch semantic diagnostics by `semantic_category`:

```python
# New routing entries (appended to _ROUTING_TABLE)
("semantic", "method_resolution",  ["semantic_method_resolution_fix", "ast_validate"], "HIGH"),
("semantic", "import_resolution",  ["semantic_import_fix", "ast_validate"],           "HIGH"),
("semantic", "discarded_return",   ["semantic_discarded_return_fix", "ast_validate"], "MEDIUM"),
("semantic", "duplicate_main",     ["semantic_duplicate_main_fix", "ast_validate"],   "HIGH"),
```

The existing `("semantic", "semantic_error", ...)` entry handles the pre-existing `SemanticMethodFixStep` (missing self, datetime confusion). The new entries use `semantic_category` for finer-grained dispatch.

**Routing table change:** The current table matches on `Diagnostic.category`. To support per-semantic-category routing, extend `route_failures()` to also match on `SemanticDiagnostic.semantic_category` when the category is `"semantic"`. This is a ~5-line change.

### 11.4 Canonical Step Order Extension

```python
_CANONICAL_ORDER = [
    "fence_strip",
    "future_import_reorder",
    "indent_normalize",
    "bracket_balance",
    "class_body_dedup",
    "definition_order_fix",
    "import_completion",
    "variable_initialization",
    "duplicate_removal",
    "extended_lint_fix",
    "dunder_all_fix",
    "unused_variable_removal",
    "semantic_method_fix",           # existing
    "semantic_import_fix",           # NEW — Capability 2
    "semantic_method_resolution_fix",# NEW — Capability 1
    "semantic_discarded_return_fix", # NEW — Capability 1
    "semantic_duplicate_main_fix",   # NEW — Capability 1
    "ast_validate",                  # terminal (unchanged)
]
```

Semantic repair steps run after all structural repair steps (fence strip, indent, imports, lint) but before final AST validation. This ensures the code is structurally sound before attempting semantic fixes.

---

## 12. Integration Engine Changes

### 12.1 New Method: `_attempt_semantic_repair()`

```python
def _attempt_semantic_repair(
    self,
    integrated_files: List[Path],
    unit: IntegrationUnit,
) -> Tuple[int, int]:
    """Run semantic detection → repair → verify cycle.

    Returns:
        (issues_found, issues_repaired) counts for attribution.
    """
```

**Responsibilities:**
1. Run `validate_disk_compliance()` on each integrated `.py` file
2. Filter to repairable categories (per `RepairConfig.semantic_repair_categories`)
3. Translate `DiskComplianceResult.semantic_issues` → `List[SemanticDiagnostic]`
4. Route through existing `route_failures()` → `create_steps_from_route()`
5. Apply repair steps via existing orchestrator
6. Re-run `validate_disk_compliance()` to verify each fix
7. Roll back any repair that doesn't eliminate its triggering issue
8. Emit OTel attributes: `semantic_repair.issues_found`, `semantic_repair.issues_repaired`, `semantic_repair.issues_unfixable`

### 12.2 Pipeline Position

```python
# In _integrate_feature(), after line ~1911:

# ── Semantic checks (Phase D — Kaizen Quality) ──
self._run_semantic_checks(integrated_files, unit)

# ── Semantic repair (Phase D+ — NEW) ──
if self._repair_config and self._repair_config.repair_enabled:
    issues_found, issues_repaired = self._attempt_semantic_repair(
        integrated_files, unit,
    )
    if issues_repaired > 0:
        # Re-run semantic checks to update warning state
        self._run_semantic_checks(integrated_files, unit)
```

### 12.3 Configuration Extension

```python
@dataclass(frozen=True)
class RepairConfig:
    # ... existing fields ...

    # NEW: Per-category enable for semantic repair (DC-4)
    semantic_repair_categories: frozenset[str] = frozenset()  # default: NONE enabled

    # NEW: Maximum semantic repairs per file (safety bound)
    max_semantic_repairs_per_file: int = 5
```

Default is `frozenset()` (empty) — no semantic repair categories enabled out of the box. Categories are opted in explicitly as they meet the gate criteria (DC-4).

---

## 13. Attribution and Scoring Architecture

### 13.1 Dual Scoring (DC-3)

The postmortem must report both pre-repair and post-repair quality. This requires capturing the pre-repair score before semantic repair modifies the file.

**Approach:** `_attempt_semantic_repair()` captures `validate_disk_compliance()` results *before* repair. These feed into the postmortem as `pre_semantic_repair_score`. The postmortem runs `validate_disk_compliance()` again after repair for `disk_quality_score` (post-repair).

```python
@dataclass
class FeaturePostMortem:
    # ... existing fields ...
    disk_quality_score: Optional[float] = None          # post-repair (existing)
    pre_semantic_repair_score: Optional[float] = None   # NEW: pre-repair baseline
    semantic_repairs_applied: int = 0                    # NEW: count
    semantic_repair_categories: List[str] = field(default_factory=list)  # NEW: which categories
```

### 13.2 Kaizen Separation

`avg_assembly_delta` must use `pre_semantic_repair_score` (not `disk_quality_score`) for the Kaizen feedback loop. This ensures the Kaizen system sees "how good is the generator?" not "how good is the generator + repair pipeline?"

```python
# In _evaluate_disk_quality():
kaizen_delta = requirement_score - pre_semantic_repair_score  # for Kaizen trend analysis
display_delta = requirement_score - disk_quality_score         # for user-facing report
```

This separation is critical. Without it, successful repairs mask generator regressions — the Kaizen system would see improving scores while the generator is actually degrading, because repairs are compensating.

### 13.3 Repair Attribution (DC-2)

Each semantic repair produces a `SemanticRepairAttribution` record:

```python
@dataclass
class SemanticRepairAttribution:
    """Per-file semantic repair attribution."""
    file_path: str
    issues_detected: int
    issues_repaired: int
    issues_unfixable: int
    repairs: List[SemanticRepairRecord]

@dataclass
class SemanticRepairRecord:
    """Single repair action."""
    category: str          # "method_resolution", "import_resolution", etc.
    symbol: str            # the specific symbol repaired
    line: int              # original line number
    original_code: str     # the line(s) before repair
    repaired_code: str     # the line(s) after repair
    verified: bool         # re-check passed?
    step_name: str         # which RepairStep applied
```

These records attach to the `RepairOutcome` from the orchestrator and flow through to the postmortem report's `FeaturePostMortem.semantic_repair_attribution` field.

---

## 14. New Repair Steps (Interface Contracts)

Each step follows the existing `RepairStep` protocol:

```python
class RepairStep(Protocol):
    name: str
    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult: ...
```

### 14.1 `SemanticImportFixStep`

**Input:** Code with `import_resolution` semantic diagnostics in `RepairContext.diagnostics`.
**Output:** Code with import paths rewritten to resolve against project layout.
**Context needed:** `RepairContext.project_root` (to find sibling files), `RepairContext.service_metadata` (to know flat vs package layout).

### 14.2 `SemanticMethodResolutionFixStep`

**Input:** Code with `method_resolution` diagnostics.
**Output:** Code with `self.func()` → `func(self)` rewrites where `func` is module-level.
**Context needed:** None beyond the code itself (self-contained AST analysis).

### 14.3 `SemanticDiscardedReturnFixStep`

**Input:** Code with `discarded_return` diagnostics.
**Output:** Code with `os.environ.get("KEY")` → `key = os.environ.get("KEY")` rewrites.
**Context needed:** None beyond the code (variable name inferred from argument).

### 14.4 `SemanticDuplicateMainFixStep`

**Input:** Code with `duplicate_main_guard` diagnostics.
**Output:** Code with second `if __name__ == "__main__"` block removed.
**Context needed:** None.

---

## 15. Answers to Layer 1 Open Questions

| # | Question | Answer |
|---|----------|--------|
| Q1 | Before or after existing repair? | **After.** Syntax repair runs first (Step 5), then semantic detect (Step 7), then semantic repair (Step 7b). This ensures structurally sound code before semantic analysis. |
| Q2 | `DiskComplianceResult` or new structure? | **Both.** Detection stays in `DiskComplianceResult`. Repair attribution goes in new `SemanticRepairAttribution` on `FeaturePostMortem`. They serve different purposes (detection vs repair tracking). |
| Q3 | Variable naming for `discarded_return`? | **Heuristic from argument string.** `os.environ.get("GCP_PROJECT_ID")` → `gcp_project_id`. Transform: lowercase, replace non-alnum with `_`. Fallback: `_result`. Deferred to Layer 3 for full specification. |
| Q4 | Verify target symbol in sibling file? | **Not in v1.** Import repair rewrites the path structure (package → flat) but does not verify the symbol exists. This keeps repair single-file and avoids cross-file analysis scope. Add symbol verification in v2 if false repairs emerge. |
| Q5 | Dead code pruning in v1? | **No.** Capability 3 is deferred to v2. Low confidence, destructive (deletion), and the benefit (removing 2-3 lines of dead code) doesn't justify the risk of false pruning. |
| Q6 | Resume cache interaction? | **Semantic repair runs after cache check.** Cached files skip generation but still run through semantic detect+repair. The repaired file's checksum replaces the cached checksum, so the next run's cache check sees the repaired version. |

---

## 16. Answers to Layer 2 Open Questions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q7 | `self.index()` + tasks dict update? | **Fix `self.` call only, leave `tasks` dict alone.** | The `tasks = {index: 1}` dict correctly references the module-level function by name — this is idiomatic Locust. Only the `self.index()` call is wrong. |
| Q8 | Flat vs package layout detection? | **Check `__init__.py` on disk, default to flat.** | `(project_root / service_dir / "__init__.py").exists()` is 1 line and definitive. `project_root` already in `RepairContext`. Flat default is safer — `import X` works in more contexts than `from pkg.X import Y`. |
| Q9 | Multi-line `discarded_return`? | **Single-line repair in v1.** Detect multi-line via AST `Expr` node but only repair when `end_lineno == lineno`. Log multi-line as "detected but not repaired." | 100% of observed cases across 20 runs are single-line. Multi-line extends in v2 if needed. |
| Q10 | OTel span naming? | **`semantic_repair.attempt` parent + `semantic_repair.file` children.** Parent always created. Child spans only for files with repairable issues. | Consistent with existing `repair.attempt` pattern. Aggregate and detail views without noise. |
| Q11 | Circuit breaker isolation? | **Separate breaker for semantic repair pass.** `semantic_repair_circuit_breaker_threshold: int = 3` on `RepairConfig`. | Syntax repair failures shouldn't disable semantic repair — independent failure domains. Per-category breakers deferred to v2. |
| Q12 | Cross-step interaction? | **No special handling.** Semantic detect runs after syntax repair, so it only sees surviving issues. Natural pipeline ordering handles dedup without explicit coordination. | If syntax `import_completion` fixes a bad import, the semantic check simply won't flag it. Zero CPU wasted on dedup logic. |

---

## 17. Architecture Summary Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Integration Engine                         │
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────┐   │
│  │ Step 5:      │   │ Step 7:      │   │ Step 7b:      │   │
│  │ Syntax Repair│──▶│ Semantic     │──▶│ Semantic      │   │
│  │ (existing)   │   │ Detect       │   │ Repair (NEW)  │   │
│  └──────┬───────┘   │ (existing)   │   └───────┬───────┘   │
│         │           └──────┬───────┘           │           │
│         │                  │                    │           │
│         ▼                  ▼                    ▼           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              repair/ Infrastructure                   │   │
│  │  ┌─────────┐ ┌─────────┐ ┌──────────────────────┐   │   │
│  │  │ routing │ │ staging │ │ steps/                │   │   │
│  │  │ table   │ │ +rollbk │ │ ├ fence_strip         │   │   │
│  │  │         │ │         │ │ ├ indent_normalize    │   │   │
│  │  │ syntax──┼─┤         │ │ ├ import_completion   │   │   │
│  │  │ import──┤ │         │ │ ├ semantic_method_fix │   │   │
│  │  │ lint────┤ │         │ │ ├ semantic_import_fix │◀──NEW │
│  │  │ semntc──┤ │         │ │ ├ semantic_method_res │◀──NEW │
│  │  │         │ │         │ │ ├ semantic_discard_ret│◀──NEW │
│  │  │         │ │         │ │ └ ast_validate        │   │   │
│  │  └─────────┘ └─────────┘ └──────────────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────┐          ┌────────────────────────┐       │
│  │ Step 7c:     │          │ Postmortem             │       │
│  │ Re-validate  │─────────▶│ pre_repair_score       │       │
│  │ (NEW)        │          │ disk_quality_score     │       │
│  └──────────────┘          │ semantic_repair_attrib │       │
│                             └────────────────────────┘       │
└─────────────────────────────────────────────────────────────┘

Data Flow:
  DiskComplianceResult.semantic_issues
    → translate_to_diagnostics()
      → SemanticDiagnostic[]
        → route_failures()
          → RepairRoute
            → RepairStep.__call__()
              → RepairStepResult
                → verify (re-run semantic check)
                  → commit or rollback
```

---
---

## Layer 3: Category Specifications

---

## 18. Overview

Layer 3 specifies each semantic repair category in full: trigger conditions, AST transform, edge cases, verification, and per-category success criteria. Three categories ship in v1; one is deferred.

| Category | Step Name | Capability | v1 Scope |
|----------|-----------|------------|----------|
| `method_resolution` | `semantic_method_resolution_fix` | Cap 1 (Deterministic AST) | **Yes** |
| `import_resolution` | `semantic_import_fix` | Cap 2 (Import Path) | **Yes** |
| `discarded_return` | `semantic_discarded_return_fix` | Cap 1 (Deterministic AST) | **Yes** |
| `duplicate_main_guard` | `semantic_duplicate_main_fix` | Cap 1 (Deterministic AST) | **Yes** |
| `unreachable_function` | (none) | Cap 3 (Dead Code Pruning) | **Deferred to v2** |

---

## 19. REQ-SR-100: `method_resolution` — Self-Dot Module Function Repair

### 19.1 Trigger

The semantic validator emits:
```json
{"category": "method_resolution", "severity": "warning",
 "message": "'self.index()' called but 'index' is a module-level function, not a method of 'UserBehavior'",
 "line": 46, "symbol": "index"}
```

The repair step activates when `semantic_category == "method_resolution"` appears in `RepairContext.diagnostics`.

### 19.2 AST Transform

**Input pattern:**
```python
def index(l):              # module-level function
    l.client.get("/")

class UserBehavior(TaskSet):
    def on_start(self):
        self.index()       # BUG: should be index(self)
    tasks = {index: 1}     # CORRECT: not touched
```

**Transform:** For each `ast.Attribute` node where:
1. `node.value` is `ast.Name(id='self')`
2. `node.attr` matches a module-level function name
3. `node.attr` is NOT a method on the enclosing class

Rewrite `self.<name>(args...)` → `<name>(self, args...)`.

**AST mechanics:**
- The `self.index()` call is an `ast.Call` whose `func` is `ast.Attribute(value=Name('self'), attr='index')`
- Replace with `ast.Call(func=Name('index'), args=[Name('self')] + original_args)`
- Use `ast.unparse()` (Python 3.9+) on the modified subtree, then splice back into the source lines

**Why not full-file `ast.unparse()`:** Full-file unparse destroys formatting, comments, and string quoting style. Line-level splice preserves the file's character except for the repaired line.

### 19.3 Line-Level Splice Strategy

```python
# 1. Identify the source line(s) containing the call
target_line = lines[node.lineno - 1]

# 2. Find the self.<name>( substring
pattern = re.compile(r'\bself\.' + re.escape(symbol) + r'\s*\(')
match = pattern.search(target_line)

# 3. Replace: self.index( → index(self,  OR  index(self)
# If no other args:  self.index()    → index(self)
# If has args:       self.index(x)   → index(self, x)
if match:
    # Extract everything between the parens to determine if there are other args
    call_start = match.start()
    paren_start = target_line.index('(', match.start())
    # Find matching close paren (handle nested parens)
    depth, i = 1, paren_start + 1
    while i < len(target_line) and depth > 0:
        if target_line[i] == '(': depth += 1
        elif target_line[i] == ')': depth -= 1
        i += 1
    inner_args = target_line[paren_start + 1 : i - 1].strip()

    if inner_args:
        replacement = f"{symbol}(self, {inner_args})"
    else:
        replacement = f"{symbol}(self)"

    new_line = target_line[:call_start] + replacement + target_line[i:]
    lines[node.lineno - 1] = new_line
```

### 19.4 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| `self.index()` where `index` IS a method on a parent class | **Skip.** The check only fires when the name is NOT in the class's method set. We don't resolve parent class methods (conservative). If the class inherits `index`, the semantic validator wouldn't flag it. |
| Multiple `self.<name>()` calls on the same line | Process left-to-right. Each match is independent. Offset tracking not needed because we rebuild the full line. |
| `self.index` used as a reference (not a call) | E.g., `callback = self.index`. The semantic check flags `self.<name>()` calls specifically (the `()` is part of the detection). Bare references are not flagged and not repaired. |
| `await self.index()` | The `self.` prefix is still present. Rewrite to `await index(self)`. The `await` keyword is outside the match region and preserved. |
| Chained: `self.index().result` | The inner `self.index()` is rewritten. The `.result` chain is outside the splice region and preserved. |

### 19.5 Scope Exclusion

**The `tasks` dict is NOT modified.** The `tasks = {index: 1, ...}` pattern correctly references the module-level function by name. Locust's `TaskSet` uses this dict to invoke the functions with the `TaskSet` instance as the first argument. The repair only touches `self.<name>()` call sites.

### 19.6 Verification

After repair, re-run `_validate_method_resolution()` on the modified code. The `self.index()` pattern should no longer appear. If it does, rollback.

### 19.7 Success Criteria

| Criterion | Target |
|-----------|--------|
| PI-009 `self.index()` repaired | `index(self)` in output |
| No change to `tasks` dict | `tasks = {index: 1, ...}` unchanged |
| AST valid after repair | `ast.parse()` succeeds |
| Semantic check clears after repair | `method_resolution` issue count = 0 |
| Zero false repairs across 10 runs | No valid `self.method()` calls rewritten |

---

## 20. REQ-SR-200: `import_resolution` — Local Namespace Import Repair

### 20.1 Trigger

The semantic validator emits:
```json
{"category": "import_resolution", "severity": "error",
 "message": "Unresolvable import: 'emailservice.email_server' is not stdlib, not in requirements.in, not a local module, and not a protobuf stub",
 "line": 4, "symbol": "emailservice.email_server"}
```

The repair step activates when `semantic_category == "import_resolution"` and the import symbol matches the **local namespace-as-package pattern**: the first segment of the import path is a sibling directory name.

### 20.2 Pattern Classification

Not all `import_resolution` errors are repairable. The step classifies each diagnostic:

| Pattern | Example | Repairable? | Strategy |
|---------|---------|-------------|----------|
| **Local namespace-as-package** | `from emailservice.email_server import X` | Yes | Rewrite to flat import |
| **Local namespace bare** | `from emailservice import demo_pb2` | Yes | Rewrite to `import demo_pb2` |
| **Proto stub** | `import demo_pb2` flagged as unresolvable | No | Already handled by import_completion step or proto stub detection |
| **Unknown third-party** | `from phantom_pkg import X` | No | Leave as error — can't determine correct import |

**Classification heuristic:**
```python
def _is_local_namespace_import(symbol: str, project_root: Path, file_path: Path) -> bool:
    """Check if the import's first segment is a sibling directory."""
    parts = symbol.split(".")
    if len(parts) < 2:
        return False
    first_segment = parts[0]
    file_dir = Path(file_path).parent
    # Check if first_segment is a sibling directory (not the file's own directory)
    candidate = project_root / file_dir.parts[0] if file_dir.parts else project_root
    # Walk up to find the service root
    for parent in [file_dir, file_dir.parent]:
        sibling = parent / first_segment
        if sibling.is_dir() and sibling != file_dir:
            return True
    return False
```

### 20.3 Layout Detection (Q8 Decision)

```python
def _detect_layout(service_dir: Path) -> str:
    """Detect flat vs package layout for a service directory."""
    if (service_dir / "__init__.py").exists():
        return "package"
    return "flat"  # default: safer
```

### 20.4 AST Transform

**Flat layout (no `__init__.py`):**

| Original | Repaired | Rule |
|----------|----------|------|
| `from emailservice.email_server import X` | `from email_server import X` | Strip the directory prefix; target module is a sibling file |
| `from emailservice.logger import getJSONLogger` | `from logger import getJSONLogger` | Same — `logger.py` is a sibling file |
| `from emailservice import demo_pb2` | `import demo_pb2` | Bare import — `demo_pb2.py` is in the same directory |
| `from recommendationservice.logger import X` | `from logger import X` | Cross-service import — strip to bare module name |

**Package layout (has `__init__.py`):**

No repair — the original import may be correct. The issue is likely a missing `__init__.py` in the `__init__.py` (re-export), which is a generation issue, not an import path issue.

### 20.5 Implementation

```python
class SemanticImportFixStep:
    """Fix local namespace-as-package imports for flat-layout projects."""

    name: str = "semantic_import_fix"

    def __call__(self, code, context, file_path, element_context=None):
        diagnostics = [
            d for d in context.diagnostics
            if isinstance(d, SemanticDiagnostic)
            and d.semantic_category == "import_resolution"
        ]
        if not diagnostics:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        project_root = context.project_root or file_path.parent
        lines = code.splitlines(keepends=True)
        fixes = []

        for diag in diagnostics:
            symbol = diag.symbol  # e.g., "emailservice.email_server"
            parts = symbol.split(".")

            if len(parts) < 2:
                continue

            service_dir_name = parts[0]
            service_dir = project_root / service_dir_name

            # Only repair if it's a known sibling directory with flat layout
            if not service_dir.is_dir():
                continue
            if _detect_layout(service_dir) != "flat":
                continue

            target_line_idx = diag.line - 1
            if target_line_idx < 0 or target_line_idx >= len(lines):
                continue

            line = lines[target_line_idx]
            module_path = ".".join(parts[1:])  # "email_server" or "logger"

            # Case 1: from <pkg>.<module> import <names>
            pattern_from = re.compile(
                r'^(\s*from\s+)' + re.escape(symbol) + r'(\s+import\s+.+)$'
            )
            m = pattern_from.match(line)
            if m:
                new_line = f"{m.group(1)}{module_path}{m.group(2)}"
                lines[target_line_idx] = new_line
                fixes.append(f"from {symbol} → from {module_path}")
                continue

            # Case 2: from <pkg> import <module>  (e.g., from emailservice import demo_pb2)
            pattern_bare = re.compile(
                r'^(\s*)from\s+' + re.escape(service_dir_name)
                + r'\s+import\s+(\w+)(.*)$'
            )
            m = pattern_bare.match(line)
            if m:
                indent = m.group(1)
                imported_name = m.group(2)
                rest = m.group(3)
                new_line = f"{indent}import {imported_name}{rest}\n"
                lines[target_line_idx] = new_line
                fixes.append(f"from {service_dir_name} import {imported_name} → import {imported_name}")
                continue

        modified = len(fixes) > 0
        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(lines),
            metrics={"fixes": fixes},
        )
```

### 20.6 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| `from emailservice.email_server import X, Y, Z` | Full `import` clause preserved. Only the `from` module path changes. |
| `from emailservice.subpkg.module import X` | Three segments: strip first. Result: `from subpkg.module import X`. Only applies if `subpkg/` exists as a subdirectory. |
| Import inside `try/except ImportError` | Not flagged by the semantic validator (already excluded). No repair attempted. |
| Aliased import: `from emailservice.logger import getJSONLogger as log` | The `as log` clause is outside the module path. Preserved by the regex. |
| Service importing from itself: `from emailservice.email_server import X` in `emailservice/email_client.py` | This is valid — repair to `from email_server import X` (sibling file in same directory). Correct behavior. |
| Cross-service import: `from recommendationservice.logger import X` in `emailservice/email_client.py` | The sibling directory check confirms `recommendationservice/` exists. Repair to `from logger import X`. **Risk:** this may resolve to the wrong `logger.py` (emailservice's own). **Mitigation:** Log a warning when the target module exists in both directories. |

### 20.7 Cross-Service Import Ambiguity

When `emailservice/email_client.py` imports `from recommendationservice.logger import X`, and both `emailservice/logger.py` and `recommendationservice/logger.py` exist, the flat-layout rewrite to `from logger import X` would resolve to `emailservice/logger.py` (same directory), not `recommendationservice/logger.py`.

**Resolution:** Skip repair for cross-service imports where the target module name also exists in the importing file's own directory. Log as "ambiguous cross-service import — not repaired."

```python
# In the repair loop, after determining module_path:
importing_dir = file_path.parent
if (importing_dir / f"{module_path}.py").exists() and service_dir != importing_dir:
    logger.warning(
        "Ambiguous cross-service import: %s exists in both %s and %s — skipping repair",
        module_path, importing_dir.name, service_dir_name,
    )
    continue
```

### 20.8 Verification

After repair, re-run `_validate_import_resolution()` on the modified code. The repaired imports should resolve (sibling file exists, or module is in `_STDLIB_MODULES`). If they don't, rollback.

### 20.9 Success Criteria

| Criterion | Target |
|-----------|--------|
| PI-004 `from emailservice.email_server import X` repaired | `from email_server import X` |
| PI-004 `from emailservice.logger import X` repaired | `from logger import X` |
| Cross-service ambiguity detected and skipped | Warning logged, not repaired |
| Package-layout directories not modified | No repair when `__init__.py` present |
| AST valid after repair | `ast.parse()` succeeds |
| Semantic check clears after repair | `import_resolution` error count reduced |

---

## 21. REQ-SR-300: `discarded_return` — Bare Expression Statement Repair

### 21.1 Trigger

The semantic validator emits:
```json
{"category": "discarded_return", "severity": "warning",
 "message": "Return value of 'os.environ.get' is discarded",
 "line": 33, "symbol": "os.environ.get"}
```

### 21.2 Scope (Q9 Decision)

**v1:** Single-line expressions only (`node.end_lineno == node.lineno`).
**Multi-line:** Detected by AST but logged as "detected, not repaired." Extended in v2.

### 21.3 Variable Name Inference

The key heuristic: infer a meaningful variable name from the function's first string argument.

**Rules:**
1. If first argument is a string constant: lowercase, replace non-alphanumeric with `_`, strip leading/trailing `_`
2. If the result is a Python keyword or empty: use `_result`
3. If the variable name already exists in scope: append `_value` suffix
4. If no string argument: use `_result`

**Examples:**
```python
os.environ.get("GCP_PROJECT_ID")           → gcp_project_id = os.environ.get("GCP_PROJECT_ID")
os.environ.get("PORT", "8080")             → port = os.environ.get("PORT", "8080")
os.environ.get("ALLOYDB_TABLE_NAME")       → alloydb_table_name = os.environ.get("ALLOYDB_TABLE_NAME")
os.path.join(base, "data")                 → _result = os.path.join(base, "data")
os.getenv("DEBUG")                         → debug = os.getenv("DEBUG")
```

**Implementation:**
```python
import keyword

def _infer_variable_name(call_node: ast.Call, existing_names: set[str]) -> str:
    """Infer a variable name from the first string argument of a call."""
    if (
        call_node.args
        and isinstance(call_node.args[0], ast.Constant)
        and isinstance(call_node.args[0].value, str)
    ):
        raw = call_node.args[0].value.lower()
        # Replace non-alnum with underscore, strip edges
        name = re.sub(r'[^a-z0-9]', '_', raw).strip('_')
        # Collapse multiple underscores
        name = re.sub(r'_+', '_', name)

        if not name or keyword.iskeyword(name) or name in ('true', 'false', 'none'):
            return "_result"
        if name in existing_names:
            return f"{name}_value"
        return name

    return "_result"
```

### 21.4 AST Transform

**Input:**
```python
os.environ.get('GCP_PROJECT_ID')    # line 33 — bare Expr statement
```

**Output:**
```python
gcp_project_id = os.environ.get('GCP_PROJECT_ID')    # line 33
```

**Mechanics:**
```python
def _fix_discarded_return(code: str, diagnostics: list) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    lines = code.splitlines(keepends=True)
    fixes = []

    # Collect existing variable names in scope
    existing_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            existing_names.add(node.id)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            existing_names.add(node.name)

    # Process diagnostics in reverse line order (stable line numbers)
    targets = []
    for diag in diagnostics:
        if diag.semantic_category != "discarded_return":
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and node.lineno == diag.line
                and node.end_lineno == node.lineno  # single-line only (Q9)
            ):
                var_name = _infer_variable_name(node.value, existing_names)
                existing_names.add(var_name)  # prevent duplicates
                targets.append((node.lineno - 1, var_name))
                break

    for line_idx, var_name in sorted(targets, reverse=True):
        if line_idx < len(lines):
            line = lines[line_idx]
            # Preserve indentation
            indent = len(line) - len(line.lstrip())
            stripped = line.lstrip()
            lines[line_idx] = " " * indent + var_name + " = " + stripped
            fixes.append(f"assigned discarded return to '{var_name}'")

    return "".join(lines), fixes
```

### 21.5 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Multiple discarded returns on consecutive lines | Each processed independently. Variable names deduped via `existing_names` tracking. `os.environ.get("A")` → `a`, `os.environ.get("B")` → `b`. |
| Already-assigned return: `x = os.environ.get("KEY")` | Not an `ast.Expr` node — it's an `ast.Assign`. Semantic validator doesn't flag it. No repair attempted. |
| Return value intentionally discarded: `print("hello")` | The semantic validator only flags pure functions (`os.environ.get`, `os.getenv`, `os.path.*`). Side-effecting functions like `print` are not flagged. |
| Variable name collision: `port = 8080` already exists, then `os.environ.get("PORT")` | Inferred name `port` collides → becomes `port_value`. |
| Non-string first argument: `os.environ.get(key_var)` | `_infer_variable_name` returns `_result`. Less descriptive but safe. |
| Multi-line expression (v1 scope) | `node.end_lineno != node.lineno` → logged as "detected, not repaired." No modification. |

### 21.6 Verification

After repair, re-run `_validate_discarded_returns()` on the modified code. The bare expression should now be an assignment statement (`ast.Assign`), not an `ast.Expr`. If the check still fires, rollback.

### 21.7 Success Criteria

| Criterion | Target |
|-----------|--------|
| PI-003 `os.environ.get('GCP_PROJECT_ID')` repaired | `gcp_project_id = os.environ.get('GCP_PROJECT_ID')` |
| Variable name is descriptive | Derived from argument string, not generic `_result` |
| No collisions with existing variables | Suffix `_value` appended when name exists |
| Multi-line expressions not modified | Logged, not repaired |
| AST valid after repair | `ast.parse()` succeeds |

---

## 22. REQ-SR-400: `duplicate_main_guard` — Second Guard Block Removal

### 22.1 Trigger

The semantic validator emits:
```json
{"category": "duplicate_main_guard", "severity": "warning",
 "message": "Multiple 'if __name__ == \"__main__\"' guards found (2)",
 "line": 85, "symbol": "__main__"}
```

### 22.2 AST Transform

**Input:**
```python
if __name__ == "__main__":
    main()                    # First guard (correct)

# ... other code ...

if __name__ == "__main__":
    setup()                   # Second guard (incorrect)
    run()
```

**Output:**
```python
if __name__ == "__main__":
    main()                    # First guard preserved

# ... other code ...

# Second guard removed entirely
```

**Strategy:** Keep the first `if __name__ == "__main__"` block, remove all subsequent ones.

**Implementation:**
```python
def _fix_duplicate_main_guard(code: str) -> tuple[str, list[str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    # Find all if __name__ == "__main__" blocks
    guards = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If) and _is_main_guard(node):
            guards.append(node)

    if len(guards) < 2:
        return code, []

    # Remove all guards except the first
    lines = code.splitlines(keepends=True)
    fixes = []

    # Process in reverse order to preserve line numbers
    for guard in reversed(guards[1:]):
        start = guard.lineno - 1
        end = guard.end_lineno  # end_lineno is 1-indexed, inclusive
        # Remove the lines
        del lines[start:end]
        fixes.append(f"removed duplicate __main__ guard at line {guard.lineno}")

    return "".join(lines), fixes


def _is_main_guard(node: ast.If) -> bool:
    """Check if an If node is `if __name__ == "__main__"`."""
    test = node.test
    if isinstance(test, ast.Compare) and len(test.ops) == 1:
        if isinstance(test.ops[0], ast.Eq):
            left, right = test.left, test.comparators[0]
            # Check both orderings: __name__ == "__main__" and "__main__" == __name__
            if (
                (isinstance(left, ast.Name) and left.id == "__name__"
                 and isinstance(right, ast.Constant) and right.value == "__main__")
                or
                (isinstance(right, ast.Name) and right.id == "__name__"
                 and isinstance(left, ast.Constant) and left.value == "__main__")
            ):
                return True
    return False
```

### 22.3 Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Two guards with different content | Second removed regardless. The first guard is authoritative. If important code is in the second guard, it's a generation bug (the LLM produced duplicate guards), not a valid pattern. |
| Guard using `!=` or `is` | `_is_main_guard` only matches `==`. Other comparisons are not standard `__main__` guards and are not touched. |
| Reversed comparison: `"__main__" == __name__` | Handled — `_is_main_guard` checks both orderings. |
| Blank lines or comments between guards | Preserved. Only the `if` block lines are removed. |
| Nested `if __name__` inside a function | `ast.iter_child_nodes(tree)` only checks top-level nodes. Nested guards are not detected and not removed. |

### 22.4 Verification

After repair, re-run `check_duplicate_main_guards()`. Should return 0 issues (only one guard remains).

### 22.5 Success Criteria

| Criterion | Target |
|-----------|--------|
| Files with 2+ guards reduced to 1 | Second+ guards removed |
| First guard preserved intact | Content unchanged |
| No removal of non-standard guard patterns | Only `__name__ == "__main__"` matched |
| AST valid after repair | `ast.parse()` succeeds |

---

## 23. Deferred: `unreachable_function` (Capability 3)

**Not implemented in v1.** Dead code pruning is deferred because:

1. **Low confidence.** Module-level functions may be intended for external callers (other files, CLI entry points, test harnesses). Single-file analysis can't distinguish "unused" from "externally used."
2. **Destructive.** Deletion cannot be undone by re-running the semantic check — the function is gone. All other v1 repairs are transformations (the information is preserved, just restructured).
3. **Low impact.** Orphaned functions (`empty_cart`, `logout`) don't break anything. They're cosmetic issues scored as warnings, not errors.

**v2 criteria for activation:**
- Cross-file reachability analysis available (forward manifest call graph)
- OR explicit "prune dead code" flag in pipeline config
- AND FP rate < 5% across 10 runs with the detection layer active

---

## 24. Diagnostic Translation Function

The bridge between the detection system and the repair pipeline:

```python
def translate_to_diagnostics(
    semantic_issues: list[dict],
    file_path: str,
) -> list[SemanticDiagnostic]:
    """Convert forward_manifest_validator semantic issue dicts to SemanticDiagnostics.

    Only translates categories that have registered repair steps.
    """
    _REPAIRABLE_CATEGORIES = frozenset({
        "method_resolution",
        "import_resolution",
        "discarded_return",
        "duplicate_main_guard",
    })

    diagnostics = []
    for issue in semantic_issues:
        if not isinstance(issue, dict):
            continue
        category = issue.get("category", "")
        if category not in _REPAIRABLE_CATEGORIES:
            continue

        diagnostics.append(SemanticDiagnostic(
            category="semantic",
            file=file_path,
            message=issue.get("message", ""),
            defect_type=category,
            semantic_category=category,
            severity=issue.get("severity", "warning"),
            symbol=issue.get("symbol", ""),
            line=issue.get("line", 0),
        ))

    return diagnostics
```

**Key constraint:** Only categories with registered repair steps are translated. Unknown categories stay as detection-only warnings. This prevents the routing table from receiving diagnostics it can't handle.

---

## 25. Observability (Q10 Decision)

### 25.1 OTel Span Structure

```
integration.feature (existing)
  ├── ...
  ├── semantic_checks.run (existing)
  ├── semantic_repair.attempt                    ← NEW (always created)
  │     attributes:
  │       semantic_repair.issues_found: int
  │       semantic_repair.issues_repaired: int
  │       semantic_repair.issues_unfixable: int
  │       semantic_repair.categories: str[]
  │     children (only for files with issues):
  │     ├── semantic_repair.file                 ← NEW
  │     │     attributes:
  │     │       file.path: str
  │     │       semantic_repair.file.issues: int
  │     │       semantic_repair.file.repaired: int
  │     │       semantic_repair.file.categories: str[]
  │     └── semantic_repair.file
  └── semantic_checks.verify (NEW — re-run)
```

### 25.2 Metrics

```python
# Extend existing repair metrics
_semantic_repair_attempts = _meter.create_counter(
    "semantic_repair_attempts_total",
    description="Total semantic repair attempts",
)
_semantic_repair_success = _meter.create_counter(
    "semantic_repair_success_total",
    description="Successful semantic repairs",
)
_semantic_repair_by_category = _meter.create_counter(
    "semantic_repair_by_category",
    description="Semantic repairs per category",
)
```

### 25.3 Loki Logging

```python
# Per-file repair logging (INFO level)
logger.info(
    "Semantic repair: %s — %d/%d issues repaired (categories: %s)",
    file_path.name, repaired, found, ", ".join(categories),
)

# Per-repair detail logging (DEBUG level)
logger.debug(
    "Semantic repair applied: %s line %d — %s → %s (verified: %s)",
    category, line, original_snippet, repaired_snippet, verified,
)
```

---

## 26. Circuit Breaker (Q11 Decision)

Separate circuit breaker for the semantic repair pass:

```python
@dataclass(frozen=True)
class RepairConfig:
    # ... existing fields ...
    semantic_repair_circuit_breaker_threshold: int = 3
```

**Behavior:**
- Counter increments when a semantic repair step raises an exception (not when it produces no modifications — that's normal)
- When counter reaches threshold, `_attempt_semantic_repair()` short-circuits for the remainder of the run
- Counter resets at the start of each integration feature (not shared across features)
- Separate from syntax repair breaker — a broken `indent_normalize` doesn't disable `semantic_import_fix`

---

## 27. Configuration Summary

All new configuration fields on `RepairConfig`:

```python
@dataclass(frozen=True)
class RepairConfig:
    # ... existing fields (repair_enabled, repairable_categories, etc.) ...

    # Semantic repair (Layer 3)
    semantic_repair_categories: frozenset[str] = frozenset()
    # Default: empty (all disabled). Enable categories individually:
    # frozenset({"method_resolution", "import_resolution", "discarded_return", "duplicate_main_guard"})

    max_semantic_repairs_per_file: int = 5
    semantic_repair_circuit_breaker_threshold: int = 3
```

**CLI activation:**
```bash
# Enable all v1 categories
--semantic-repair-categories method_resolution,import_resolution,discarded_return,duplicate_main_guard

# Enable only import repair
--semantic-repair-categories import_resolution
```

---

## 28. Answers to Layer 3 Open Questions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q13 | Where does `translate_to_diagnostics()` live? | **New file `repair/semantic_bridge.py`.** | It's a bridge between two subsystems (`forward_manifest_validator` → `repair/`). Putting it in `models.py` would add a dependency on validator types. Dedicated file keeps the coupling explicit and testable. |
| Q14 | One file per step or grouped? | **One file per step**, matching existing pattern (`fence_strip.py`, `ast_validate.py`, etc.). | Consistency with the 13 existing step files. Each step is independently testable. The `steps/__init__.py` re-exports handle discoverability. |
| Q15 | Test fixtures? | **Synthetic files derived from run-062 patterns.** Each step gets 5-8 test cases covering the edge case table from Layer 3. Reuse actual PI-004/PI-009/PI-003 code as "golden" fixtures. | Synthetic gives control over edge cases. Run-062 files provide real-world validation. Both needed. |
| Q16 | CLI flag scope? | **Both.** `RepairConfig` gets the field (SDK scope). `run_prime_contractor.sh` passes it through via `--semantic-repair-categories` (pipeline scope). | SDK consumers can use the config directly. Pipeline users get the CLI flag. Same pattern as `--repair-enabled`. |
| Q17 | Sequential or all-at-once? | **All infrastructure in one commit, then one commit per step.** Steps ship in order: import → method → discarded → duplicate. | Infrastructure must land first (it's a dependency). Per-step commits allow independent review and easy revert if a step produces false repairs. |

---
---

## Layer 4: Implementation Plan

---

## 29. Commit Plan

6 commits, shipped in order. Each commit is independently testable and deployable.

```
Commit 1: Infrastructure (bridge, routing, config, integration engine method)
    ↓
Commit 2: SemanticImportFixStep (REQ-SR-200) — highest impact
    ↓
Commit 3: SemanticMethodResolutionFixStep (REQ-SR-100)
    ↓
Commit 4: SemanticDiscardedReturnFixStep (REQ-SR-300)
    ↓
Commit 5: SemanticDuplicateMainFixStep (REQ-SR-400)
    ↓
Commit 6: Dual scoring + attribution (postmortem integration)
```

---

## 30. Commit 1: Infrastructure

### 30.1 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/repair/models.py` | Extend `SemanticDiagnostic` with `semantic_category`, `severity`, `symbol`, `line` fields | ~5 |
| `src/startd8/repair/semantic_bridge.py` | **NEW** — `translate_to_diagnostics()` function | ~40 |
| `src/startd8/repair/routing.py` | Extend `route_failures()` to match `SemanticDiagnostic.semantic_category`; add 4 routing entries; extend `_CANONICAL_ORDER` | ~25 |
| `src/startd8/repair/config.py` | Add `semantic_repair_categories`, `max_semantic_repairs_per_file`, `semantic_repair_circuit_breaker_threshold` | ~5 |
| `src/startd8/repair/steps/__init__.py` | Import and re-export new step classes (placeholder until Commits 2-5) | ~5 |
| `src/startd8/contractors/integration_engine.py` | Add `_attempt_semantic_repair()` method + wire into pipeline after `_run_semantic_checks()` | ~80 |
| `src/startd8/repair/orchestrator.py` | Add OTel spans for `semantic_repair.attempt` and `semantic_repair.file` | ~20 |

### 30.2 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `src/startd8/repair/semantic_bridge.py` | Diagnostic translation bridge | ~40 |
| `tests/unit/repair/test_semantic_bridge.py` | Bridge translation tests | ~60 |
| `tests/unit/repair/test_semantic_routing.py` | Routing extension tests | ~40 |

### 30.3 Implementation Details

**`repair/models.py` — Extend `SemanticDiagnostic`:**

```python
@dataclass
class SemanticDiagnostic(Diagnostic):
    """Semantic correctness violation detected by structural verification."""
    defect_type: str = ""            # "missing_self", "datetime_confusion" (existing)
    semantic_category: str = ""      # "method_resolution", "import_resolution", etc. (NEW)
    severity: str = "warning"        # from semantic issue dict (NEW)
    symbol: str = ""                 # the specific symbol involved (NEW)
    line: int = 0                    # source line number (NEW)

    def __post_init__(self) -> None:
        self.category = "semantic"
```

**`repair/routing.py` — Routing extension:**

```python
# Extend route_failures() matching logic:
for cat, pattern, steps, confidence in _ROUTING_TABLE:
    if cat in categories and cat in config.repairable_categories:
        # NEW: for semantic diagnostics, also check semantic_category
        if cat == "semantic" and pattern != "semantic_error":
            # Fine-grained match: only activate if a diagnostic has this semantic_category
            if not any(
                getattr(d, "semantic_category", "") == pattern
                for d in diagnostics
                if d.category == "semantic"
            ):
                continue
        matched_patterns.append(pattern)
        step_names.update(steps)
        ...
```

**`integration_engine.py` — `_attempt_semantic_repair()`:**

```python
def _attempt_semantic_repair(
    self,
    integrated_files: List[Path],
    unit: IntegrationUnit,
) -> Tuple[int, int]:
    """Run semantic detection → repair → verify cycle."""
    from startd8.forward_manifest_validator import validate_disk_compliance
    from startd8.repair.semantic_bridge import translate_to_diagnostics

    if not self._repair_config or not self._repair_config.semantic_repair_categories:
        return 0, 0

    total_found = 0
    total_repaired = 0

    for fpath in integrated_files:
        if fpath.suffix != ".py":
            continue

        # 1. Detect
        try:
            source = fpath.read_text(encoding="utf-8")
            compliance = validate_disk_compliance(
                str(fpath), str(self._project_root),
            )
        except Exception:
            continue

        repairable = [
            issue for issue in (compliance.semantic_issues or [])
            if isinstance(issue, dict)
            and issue.get("category", "") in self._repair_config.semantic_repair_categories
        ]
        if not repairable:
            continue

        total_found += len(repairable)

        # 2. Translate → Route → Repair
        diagnostics = translate_to_diagnostics(repairable, str(fpath))
        route = route_failures(diagnostics, self._repair_config)
        if not route.steps:
            continue

        steps = create_steps_from_route(route)
        context = RepairContext(
            diagnostics=diagnostics,
            config=self._repair_config,
            project_root=self._project_root,
        )

        repaired_code = source
        for step in steps:
            result = step(repaired_code, context, fpath)
            if result.modified:
                repaired_code = result.code

        if repaired_code == source:
            continue

        # 3. Verify — re-run compliance check on repaired code
        fpath.write_text(repaired_code, encoding="utf-8")
        post_compliance = validate_disk_compliance(
            str(fpath), str(self._project_root),
        )
        post_repairable = [
            issue for issue in (post_compliance.semantic_issues or [])
            if isinstance(issue, dict)
            and issue.get("category", "") in self._repair_config.semantic_repair_categories
        ]

        repaired_count = len(repairable) - len(post_repairable)
        if repaired_count > 0:
            total_repaired += repaired_count
            logger.info(
                "Semantic repair: %s — %d/%d issues repaired",
                fpath.name, repaired_count, len(repairable),
            )
        else:
            # Rollback — repair didn't help
            fpath.write_text(source, encoding="utf-8")
            logger.debug(
                "Semantic repair rollback: %s — no issues resolved", fpath.name,
            )

    return total_found, total_repaired
```

### 30.4 Tests

| Test | What it validates |
|------|-------------------|
| `test_translate_repairable_categories_only` | Only `method_resolution`, `import_resolution`, `discarded_return`, `duplicate_main_guard` translated |
| `test_translate_unknown_category_skipped` | `unreachable_function` not translated |
| `test_translate_non_dict_skipped` | Non-dict items in `semantic_issues` ignored |
| `test_routing_semantic_category_dispatch` | `method_resolution` diagnostic routes to `semantic_method_resolution_fix` step |
| `test_routing_mixed_categories` | Multiple semantic categories produce union of steps in canonical order |
| `test_routing_empty_semantic_categories_config` | Empty `semantic_repair_categories` config produces no route |
| `test_circuit_breaker_separate_from_syntax` | Syntax breaker trip doesn't affect semantic repair |

### 30.5 Estimated Effort

~180 impl LOC + ~100 test LOC. One commit.

---

## 31. Commit 2: `SemanticImportFixStep` (REQ-SR-200)

### 31.1 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `src/startd8/repair/steps/semantic_import_fix.py` | Import path repair step | ~90 |
| `tests/unit/repair/test_semantic_import_fix.py` | Import repair tests | ~120 |

### 31.2 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/repair/steps/__init__.py` | Import and re-export `SemanticImportFixStep` | ~2 |
| `src/startd8/repair/routing.py` | Register `"semantic_import_fix"` in `_STEP_FACTORIES` | ~1 |

### 31.3 Step Implementation

Full implementation specified in §20.5 (Layer 3). Key functions:

- `SemanticImportFixStep.__call__()` — main entry point
- `_detect_layout(service_dir)` — `__init__.py` presence check
- `_is_local_namespace_import()` — classification heuristic
- Cross-service ambiguity guard (§20.7)

### 31.4 Test Fixtures

Synthetic Python files derived from run-062 PI-004 (`email_client.py`):

| Fixture | Content | Expected Result |
|---------|---------|-----------------|
| `flat_layout_from_pkg_mod.py` | `from emailservice.email_server import X` with sibling `email_server.py` | `from email_server import X` |
| `flat_layout_from_pkg.py` | `from emailservice import demo_pb2` with sibling `demo_pb2.py` | `import demo_pb2` |
| `package_layout.py` | Same imports but `emailservice/__init__.py` exists | No modification |
| `cross_service_ambiguous.py` | `from recommendationservice.logger import X` with local `logger.py` | No modification + warning |
| `cross_service_safe.py` | `from recommendationservice.client import X` with no local `client.py` | `from client import X` |
| `multi_import.py` | `from emailservice.logger import X, Y, Z` | `from logger import X, Y, Z` |
| `aliased_import.py` | `from emailservice.logger import getJSONLogger as log` | `from logger import getJSONLogger as log` |
| `non_repairable.py` | `from phantom_pkg import X` (not a sibling dir) | No modification |

### 31.5 Estimated Effort

~90 impl LOC + ~120 test LOC. One commit.

---

## 32. Commit 3: `SemanticMethodResolutionFixStep` (REQ-SR-100)

### 32.1 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `src/startd8/repair/steps/semantic_method_resolution_fix.py` | `self.func()` → `func(self)` repair | ~70 |
| `tests/unit/repair/test_semantic_method_resolution_fix.py` | Method resolution tests | ~100 |

### 32.2 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/repair/steps/__init__.py` | Import and re-export `SemanticMethodResolutionFixStep` | ~2 |
| `src/startd8/repair/routing.py` | Register `"semantic_method_resolution_fix"` in `_STEP_FACTORIES` | ~1 |

### 32.3 Step Implementation

Full implementation specified in §19.3 (Layer 3). Key logic:

- Collect module-level function names (pass 1)
- For each class, collect its method names (pass 2)
- Find `self.<name>()` calls where `<name>` is module-level, not a method
- Line-level splice: `self.index()` → `index(self)`, `self.index(x)` → `index(self, x)`

### 32.4 Test Fixtures

| Fixture | Content | Expected Result |
|---------|---------|-----------------|
| `locustfile_self_dot.py` | `self.index()` where `index` is module-level | `index(self)` |
| `self_dot_with_args.py` | `self.index(x, y)` | `index(self, x, y)` |
| `real_method.py` | `self.on_start()` where `on_start` is a class method | No modification |
| `tasks_dict_untouched.py` | `tasks = {index: 1}` | No modification |
| `await_self_dot.py` | `await self.index()` | `await index(self)` |
| `no_module_func.py` | `self.foo()` where `foo` is not defined anywhere | No modification |
| `multiple_classes.py` | Two classes, one with the bug | Only the buggy class repaired |

### 32.5 Estimated Effort

~70 impl LOC + ~100 test LOC. One commit.

---

## 33. Commit 4: `SemanticDiscardedReturnFixStep` (REQ-SR-300)

### 33.1 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `src/startd8/repair/steps/semantic_discarded_return_fix.py` | Bare expression → assignment repair | ~80 |
| `tests/unit/repair/test_semantic_discarded_return_fix.py` | Discarded return tests | ~90 |

### 33.2 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/repair/steps/__init__.py` | Import and re-export `SemanticDiscardedReturnFixStep` | ~2 |
| `src/startd8/repair/routing.py` | Register `"semantic_discarded_return_fix"` in `_STEP_FACTORIES` | ~1 |

### 33.3 Step Implementation

Full implementation specified in §21.3–21.4 (Layer 3). Key functions:

- `_infer_variable_name(call_node, existing_names)` — naming heuristic
- `_fix_discarded_return(code, diagnostics)` — AST `Expr` detection + line splice
- Single-line only guard: `node.end_lineno == node.lineno`

### 33.4 Test Fixtures

| Fixture | Content | Expected Result |
|---------|---------|-----------------|
| `env_get_bare.py` | `os.environ.get('GCP_PROJECT_ID')` | `gcp_project_id = os.environ.get('GCP_PROJECT_ID')` |
| `env_get_with_default.py` | `os.environ.get("PORT", "8080")` | `port = os.environ.get("PORT", "8080")` |
| `getenv_bare.py` | `os.getenv("DEBUG")` | `debug = os.getenv("DEBUG")` |
| `already_assigned.py` | `x = os.environ.get("KEY")` | No modification |
| `name_collision.py` | `port = 8080` then `os.environ.get("PORT")` | `port_value = os.environ.get("PORT")` |
| `non_string_arg.py` | `os.environ.get(key_var)` | `_result = os.environ.get(key_var)` |
| `multiline_skipped.py` | `os.environ.get(\n    "KEY"\n)` | No modification (logged) |
| `print_not_flagged.py` | `print("hello")` | No modification (not flagged by detector) |
| `multiple_consecutive.py` | Three bare `os.environ.get()` on consecutive lines | All three assigned with unique names |

### 33.5 Estimated Effort

~80 impl LOC + ~90 test LOC. One commit.

---

## 34. Commit 5: `SemanticDuplicateMainFixStep` (REQ-SR-400)

### 34.1 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `src/startd8/repair/steps/semantic_duplicate_main_fix.py` | Second `if __name__ == "__main__"` removal | ~50 |
| `tests/unit/repair/test_semantic_duplicate_main_fix.py` | Duplicate main guard tests | ~70 |

### 34.2 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/repair/steps/__init__.py` | Import and re-export `SemanticDuplicateMainFixStep` | ~2 |
| `src/startd8/repair/routing.py` | Register `"semantic_duplicate_main_fix"` in `_STEP_FACTORIES` | ~1 |

### 34.3 Step Implementation

Full implementation specified in §22.2 (Layer 3). Key functions:

- `_is_main_guard(node)` — AST `If` node pattern check (both orderings)
- `_fix_duplicate_main_guard(code)` — keep first, delete subsequent via line removal

### 34.4 Test Fixtures

| Fixture | Content | Expected Result |
|---------|---------|-----------------|
| `two_guards.py` | Two `if __name__ == "__main__"` blocks | Second removed |
| `three_guards.py` | Three guards | Second and third removed |
| `single_guard.py` | One guard | No modification |
| `reversed_comparison.py` | `"__main__" == __name__` | Recognized and handled |
| `nested_guard.py` | Guard inside a function | Not detected (top-level only) |
| `different_content.py` | Two guards with different bodies | Second removed regardless |

### 34.5 Estimated Effort

~50 impl LOC + ~70 test LOC. One commit.

---

## 35. Commit 6: Dual Scoring + Attribution

### 35.1 Files Modified

| File | Change | LOC (est) |
|------|--------|-----------|
| `src/startd8/contractors/prime_postmortem.py` | Add `pre_semantic_repair_score`, `semantic_repairs_applied`, `semantic_repair_categories` to `FeaturePostMortem`. Compute `kaizen_delta` from pre-repair score. | ~30 |
| `scripts/run_prime_postmortem.py` | Emit `pre_semantic_repair_score`, `semantic_repair_summary` in `kaizen-metrics.json` | ~15 |
| `src/startd8/repair/models.py` | Add `SemanticRepairAttribution` and `SemanticRepairRecord` dataclasses | ~20 |
| `src/startd8/contractors/integration_engine.py` | Capture pre-repair compliance before semantic repair; attach attribution to integration result metadata | ~25 |

### 35.2 Files Created

| File | Purpose | LOC (est) |
|------|---------|-----------|
| `tests/unit/contractors/test_semantic_repair_scoring.py` | Dual scoring and attribution tests | ~80 |

### 35.3 Key Logic

**Pre-repair score capture** (in `_attempt_semantic_repair`):

```python
# Before repair:
pre_compliance = validate_disk_compliance(str(fpath), str(self._project_root))
pre_score = compute_disk_quality_score(pre_compliance)

# ... repair ...

# After repair:
post_compliance = validate_disk_compliance(str(fpath), str(self._project_root))
post_score = compute_disk_quality_score(post_compliance)

# Store both for postmortem
unit_metadata["pre_semantic_repair_scores"][str(fpath)] = pre_score
unit_metadata["post_semantic_repair_scores"][str(fpath)] = post_score
```

**Kaizen delta separation** (in `_evaluate_disk_quality`):

```python
# Use pre-repair score for Kaizen trend (measures generator quality)
kaizen_score = pre_semantic_repair_scores.get(file_path, disk_quality_score)
fpm.assembly_delta = fpm.requirement_score - kaizen_score

# Use post-repair score for display (measures output quality)
fpm.disk_quality_score = post_semantic_repair_scores.get(file_path, disk_quality_score)
```

### 35.4 Estimated Effort

~90 impl LOC + ~80 test LOC. One commit.

---

## 36. Total Effort Summary

| Commit | Scope | Impl LOC | Test LOC | Total |
|--------|-------|----------|----------|-------|
| 1. Infrastructure | Bridge, routing, config, engine method | ~180 | ~100 | ~280 |
| 2. Import fix | `SemanticImportFixStep` | ~90 | ~120 | ~210 |
| 3. Method resolution | `SemanticMethodResolutionFixStep` | ~70 | ~100 | ~170 |
| 4. Discarded return | `SemanticDiscardedReturnFixStep` | ~80 | ~90 | ~170 |
| 5. Duplicate main | `SemanticDuplicateMainFixStep` | ~50 | ~70 | ~120 |
| 6. Dual scoring | Attribution + postmortem integration | ~90 | ~80 | ~170 |
| **Total** | | **~560** | **~560** | **~1120** |

---

## 37. Verification Plan

### 37.1 Unit Tests (per commit)

Each commit includes its own test file. Run with:
```bash
pytest tests/unit/repair/test_semantic_*.py -v
```

### 37.2 Integration Test (after all commits)

Replay run-062's generated files through the semantic repair pipeline:

```bash
# 1. Copy run-062 generated files to a temp directory
# 2. Run validate_disk_compliance() on each .py file
# 3. Run semantic repair with all categories enabled
# 4. Re-run validate_disk_compliance()
# 5. Assert:
#    - PI-004 import_resolution errors: 2 → 0
#    - PI-003 discarded_return warnings: 1 → 0
#    - PI-009 method_resolution warnings: 1 → 0
#    - PI-009 unreachable_function warnings: 2 → 2 (unchanged — deferred)
#    - Total semantic issues: 7 → 3
#    - No new AST parse errors introduced
```

### 37.3 Production Validation

Run the online-boutique pipeline with semantic repair enabled:

```bash
./run-prime-contractor.sh \
    --provenance .../run-provenance.json \
    --semantic-repair-categories method_resolution,import_resolution,discarded_return,duplicate_main_guard
```

Compare postmortem scores:
- `pre_semantic_repair_score` should match run-062 scores
- `disk_quality_score` (post-repair) should be higher
- `PARTIAL:semantic` verdict on PI-004 should upgrade to `PASS`
- Kaizen `avg_assembly_delta` should use pre-repair scores (no change from baseline)

---

## 38. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| False repair breaks working code | Every repair verified by re-running semantic check. Rollback on failure. AST `parse()` as terminal step. |
| Import repair resolves to wrong module | Cross-service ambiguity guard (§20.7) skips ambiguous cases. |
| Variable name inference produces invalid Python | `keyword.iskeyword()` check. Fallback to `_result`. |
| Repair masks generator regression | Dual scoring (Commit 6). Kaizen sees pre-repair scores only. |
| Circuit breaker too aggressive | Threshold = 3 per feature. Resets between features. Only exception-raising failures count (not "no modifications"). |
| Semantic repair adds latency to hot path | All transforms are AST-based, no LLM calls. Target: <500ms per file. Typical: <50ms. |

---

## 39. Cross-References (Complete)

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_V2_REQUIREMENTS.md](SEMANTIC_VALIDATION_V2_REQUIREMENTS.md) | Detection system; REQ-SV2-1000 gate criteria |
| [SEMANTIC_VALIDATION_V2_IMPLEMENTATION_PLAN.md](SEMANTIC_VALIDATION_V2_IMPLEMENTATION_PLAN.md) | Detection hardening (Phases 5–7); prerequisite for repair |
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Phase A-E validation; KZ-Q2 definition |
| [POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md](../repair-pipeline/POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md) | Existing repair infrastructure; DC-5 integration target |
| `src/startd8/repair/` | Implementation home — bridge, routing, steps, orchestrator |
| `src/startd8/repair/steps/` | 4 new step files (Commits 2–5) |
| `src/startd8/repair/semantic_bridge.py` | Diagnostic translation (Commit 1) |
| `src/startd8/contractors/integration_engine.py` | `_attempt_semantic_repair()` insertion point |
| `src/startd8/contractors/forward_manifest_validator.py` | Detection source — `validate_disk_compliance()` |
| `src/startd8/contractors/prime_postmortem.py` | Dual scoring + attribution (Commit 6) |
| `src/startd8/repair/config.py` | Configuration extension (Commit 1) |
| `scripts/run_prime_postmortem.py` | Kaizen metrics emission (Commit 6) |

---
---

## Post-Review Findings and Plan Updates (2026-03-17)

---

## 40. Review Methodology

Each layer reviewed independently for internal quality, then all layers reviewed together for coherence. Code that will be modified was analyzed for accidental vs essential complexity. Two independent validation systems (`semantic_checks.py` vs `forward_manifest_validator.py`) were discovered and reconciled.

---

## 41. Critical Finding: Two Semantic Check Systems

### 41.1 The Problem

The plan assumes a single detection source (`forward_manifest_validator.py`). In reality, **two independent systems** detect semantic issues:

| System | File | Output Format | Called By | Checks |
|--------|------|--------------|-----------|--------|
| **A** | `validators/semantic_checks.py` | `SemanticIssue` (frozen dataclass with `.check`, `.severity`, `.message`, `.line`, `.file_path`) | `IntegrationEngine._run_semantic_checks()` | 4: duplicate main, duplicate defs, bare except pass, phantom deps |
| **B** | `forward_manifest_validator.py` | `Dict[str, object]` (with `category`, `severity`, `message`, `line`, `symbol`) | `PrimePostMortemEvaluator._evaluate_disk_quality()` | 7+: import resolution, method resolution, discarded return, unreachable function, service identity, factory return, cross-scope duplicates |

System A runs during integration (before commit). System B runs during postmortem (after commit). The semantic repair bridge in the plan (§24, §30) only handles System B's dict format.

### 41.2 Impact on Plan

- **`_run_semantic_checks()` in integration engine calls System A** — it runs 4 basic checks and logs warnings. It does NOT call System B (the one with the checks we want to repair: import resolution, method resolution, discarded return).
- **The plan's `_attempt_semantic_repair()` calls `validate_disk_compliance()` (System B)** — this is correct for detection, but it means the integration engine now has two independent validation calls: one via System A (existing) and one via System B (new).
- **Duplication risk:** `check_duplicate_main_guards()` exists in BOTH systems. `check_duplicate_definitions()` overlaps with `_detect_cross_scope_duplicates()`.

### 41.3 Resolution

**Replace System A call with System B in the integration engine.** `_run_semantic_checks()` currently calls `semantic_checks.run_semantic_checks()` (4 checks). The new `_attempt_semantic_repair()` calls `validate_disk_compliance()` (7+ checks, superset). Running both is redundant.

**Updated plan:** Commit 1 should:
1. Replace `_run_semantic_checks()` body to call `validate_disk_compliance()` instead of `semantic_checks.run_semantic_checks()`
2. Log all semantic issues as warnings (preserving existing behavior)
3. Feed repairable issues to the repair pipeline
4. This eliminates the dual-system confusion and the need for two different format bridges

---

## 42. Accidental Complexity in Existing Code

### 42.1 Dead Code to Remove (Commit 0 — prerequisite refactor)

| Item | File | Lines | Why Dead |
|------|------|-------|----------|
| Existing `SemanticDiagnostic.defect_type` field | `repair/models.py` | 97 | Never instantiated anywhere in codebase. `grep -rn "SemanticDiagnostic(" src/` returns 0 results. |
| Existing `("semantic", "semantic_error", ...)` routing entry | `repair/routing.py` | 57 | Unreachable — no code creates `SemanticDiagnostic` objects to trigger it. |
| `RepairContext.forward_manifest` | `repair/models.py` | 204 | Zero reads in non-test code. Phase 2 placeholder. |
| `RepairContext.service_metadata` | `repair/models.py` | 205 | Zero reads in non-test code. Phase 2 placeholder. |
| `RepairContext.skeleton_content` | `repair/models.py` | 209 | Zero reads anywhere. |
| `RepairContext.test_regressions` | `repair/models.py` | 208 | Zero reads anywhere. |

**Action:** Add a **Commit 0** to the plan that removes dead code before building on top of it. Building semantic repair on dead infrastructure creates confusion ("is this the old path or the new path?").

### 42.2 Duplicate `element_context` Parameter

The `RepairStep` protocol passes `element_context` as both:
- A field on `RepairContext` (`context.element_context`)
- A separate `__call__` parameter (`element_context=None`)

13 step implementations carry this redundancy. Only 2-3 actually use it.

**Action:** Defer this cleanup to after semantic repair ships. It touches 13 files and is orthogonal to semantic repair. Document as tech debt.

### 42.3 `_attempt_semantic_repair()` Does Too Much

The pseudocode in §30.3 is ~80 LOC of inline logic in the integration engine: file I/O, validation, translation, routing, step execution, verification, rollback. This violates single-responsibility.

**Action:** Extract the core detect→repair→verify loop into `repair/orchestrator.py` as `run_semantic_repair()`. The integration engine method becomes a thin wrapper that iterates files and calls the orchestrator.

---

## 43. Low-Hanging Quality Improvements

### 43.1 Missing Test Fixtures (7 gaps from Layer 3 edge cases)

| # | Category | Edge Case | Missing Fixture |
|---|----------|-----------|-----------------|
| 1 | `method_resolution` | Inherited parent class method | Class inheriting `index` from parent — should NOT repair |
| 2 | `import_resolution` | Three-segment import path | `from emailservice.subpkg.module import X` |
| 3 | `import_resolution` | Import inside `try/except ImportError` | Validator excludes these, but test should verify step handles gracefully |
| 4 | `import_resolution` | Cross-service with both dirs having target module | `emailservice/logger.py` + `recommendationservice/logger.py` both exist |
| 5 | `discarded_return` | Python keyword as inferred name | `os.environ.get("CLASS")` → should use `_result` not `class` |
| 6 | `discarded_return` | Multi-line with backslash continuation | `os.environ.get(\` on two lines |
| 7 | `duplicate_main_guard` | Guard inside function | `def setup(): if __name__ == "__main__":` — should NOT remove |

### 43.2 Step Factory Validation Test

The `_STEP_FACTORIES` dict in `routing.py` must stay in sync with imports in `steps/__init__.py`. No test enforces this. A missing entry causes silent skip — the step is routed but never instantiated.

**Action:** Add to Commit 1:
```python
def test_all_routed_steps_have_factories():
    for _, _, steps, _ in _ROUTING_TABLE:
        for step_name in steps:
            assert step_name in _STEP_FACTORIES, f"Missing factory: {step_name}"
```

### 43.3 Commit 6 Attribution Threading

The plan is vague about how `pre_semantic_repair_score` propagates from integration engine to postmortem. Two options:

**Option A (simpler):** Write a sidecar JSON file (`.startd8/state/semantic_repair_scores.json`) alongside existing generation results. Postmortem reads it if present.

**Option B (cleaner):** Thread through `IntegrationResult.metadata` dict, which already flows to postmortem via `context_seed` handlers.

**Action:** Use Option B. The `result_obj_metadata` dict in `_integrate_feature()` already flows through to the postmortem evaluator. Add `pre_semantic_repair_scores` and `semantic_repair_attribution` keys.

---

## 44. Updated Commit Plan

```
Commit 0: Prerequisite Cleanup (remove dead code, unify semantic check call)
    ↓
Commit 1: Infrastructure (bridge, routing, config, orchestrator method)
    ↓
Commit 2: SemanticImportFixStep (REQ-SR-200)
    ↓
Commit 3: SemanticMethodResolutionFixStep (REQ-SR-100)
    ↓
Commit 4: SemanticDiscardedReturnFixStep (REQ-SR-300)
    ↓
Commit 5: SemanticDuplicateMainFixStep (REQ-SR-400)
    ↓
Commit 6: Dual scoring + attribution (postmortem integration)
```

### 44.1 Commit 0: Prerequisite Cleanup (NEW)

| File | Change | LOC |
|------|--------|-----|
| `repair/models.py` | Remove 4 unused `RepairContext` fields (`forward_manifest`, `service_metadata`, `skeleton_content`, `test_regressions`). Reset `SemanticDiagnostic` to clean slate (remove `defect_type`, will re-add with new fields in Commit 1). | -15 |
| `repair/routing.py` | Remove dead `("semantic", "semantic_error", ...)` routing entry. | -1 |
| `contractors/integration_engine.py` | Replace `_run_semantic_checks()` body: call `validate_disk_compliance()` instead of `semantic_checks.run_semantic_checks()`. Preserve warning logging behavior. | ~20 (net: +5, replacing 30 LOC with 25) |
| Tests | Update any tests that reference removed fields. Add `test_all_routed_steps_have_factories()`. | ~30 |

**Estimated effort:** ~30 impl + ~30 test = ~60 LOC. One commit.

### 44.2 Revised Commit 1: Infrastructure

**Changes from original:**

1. **`_attempt_semantic_repair()` moves to `repair/orchestrator.py`** as `run_semantic_repair(files, config, project_root)`. Integration engine calls it as a thin wrapper. This follows the existing pattern where `run_file_repair()` and `run_element_repair()` live in the orchestrator.

2. **Single detection source.** Since Commit 0 unifies the integration engine to use `validate_disk_compliance()`, the bridge only handles dict-format issues. No `SemanticIssue` dataclass conversion needed.

3. **Revised files:**

| File | Change | LOC (est) |
|------|--------|-----------|
| `repair/models.py` | Rebuild `SemanticDiagnostic` with `semantic_category`, `severity`, `symbol`, `line` | ~10 |
| `repair/semantic_bridge.py` | **NEW** — `translate_to_diagnostics()` (dict → `SemanticDiagnostic` only) | ~30 |
| `repair/routing.py` | Add 4 routing entries + extend `route_failures()` for `semantic_category` matching | ~25 |
| `repair/config.py` | Add 3 new fields | ~5 |
| `repair/orchestrator.py` | Add `run_semantic_repair()` function (extracted from §30.3 pseudocode) | ~60 |
| `contractors/integration_engine.py` | Thin wrapper calling `run_semantic_repair()` after `_run_semantic_checks()` | ~15 |

**Net effect:** ~145 impl LOC (down from ~180) + ~100 test LOC. Orchestrator owns the detect→repair→verify loop, integration engine stays thin.

### 44.3 Updated Commit 2-5: Add Missing Test Fixtures

Each step commit adds the 1-2 missing fixtures from §43.1:

- **Commit 2 (import):** Add fixtures #2, #3, #4 → 11 total (was 8)
- **Commit 3 (method):** Add fixture #1 → 8 total (was 7)
- **Commit 4 (discarded):** Add fixtures #5, #6 → 11 total (was 9)
- **Commit 5 (duplicate main):** Add fixture #7 → 7 total (was 6)

### 44.4 Updated Commit 6: Attribution Threading

Use `result_obj_metadata` dict (Option B from §43.3):

```python
# In _attempt_semantic_repair() wrapper (integration_engine.py):
result_obj_metadata["semantic_repair"] = {
    "pre_scores": {str(fpath): pre_score for fpath, pre_score in pre_scores.items()},
    "post_scores": {str(fpath): post_score for fpath, post_score in post_scores.items()},
    "attribution": [record.to_dict() for record in attribution_records],
}

# In prime_postmortem.py _evaluate_disk_quality():
semantic_repair_data = metadata.get("semantic_repair", {})
pre_scores = semantic_repair_data.get("pre_scores", {})
# ... use pre_scores for kaizen_delta, post_scores for display_delta
```

---

## 45. Revised Total Effort Summary

| Commit | Scope | Impl LOC | Test LOC | Total |
|--------|-------|----------|----------|-------|
| **0. Cleanup** | Remove dead code, unify detection | ~30 | ~30 | ~60 |
| 1. Infrastructure | Bridge, routing, config, orchestrator | ~145 | ~100 | ~245 |
| 2. Import fix | `SemanticImportFixStep` + 3 extra fixtures | ~90 | ~140 | ~230 |
| 3. Method resolution | `SemanticMethodResolutionFixStep` + 1 extra fixture | ~70 | ~110 | ~180 |
| 4. Discarded return | `SemanticDiscardedReturnFixStep` + 2 extra fixtures | ~80 | ~110 | ~190 |
| 5. Duplicate main | `SemanticDuplicateMainFixStep` + 1 extra fixture | ~50 | ~80 | ~130 |
| 6. Dual scoring | Attribution via `result_obj_metadata` threading | ~90 | ~80 | ~170 |
| **Total** | | **~555** | **~650** | **~1205** |

Delta from original: +85 LOC (mostly test fixtures), +1 commit (cleanup). The cleanup commit pays for itself by eliminating confusion during implementation.

---

## 46. Deferred Tech Debt

| Item | Rationale | When to Address |
|------|-----------|----------------|
| Duplicate `element_context` parameter on `RepairStep` protocol | Touches 13 step files. Orthogonal to semantic repair. | After semantic repair ships, as a standalone refactor commit. |
| `RepairConfig` frozen dataclass | Frozen=True is defensive but adds test friction. Document intent rather than change. | Low priority — cosmetic. |
| `semantic_checks.py` module deprecation | After Commit 0 unifies detection to `validate_disk_compliance()`, the `validators/semantic_checks.py` module becomes unused by the integration engine. Keep it for standalone use but mark as superseded. | After semantic repair validated in production. |
| Step factory validation gap | `_STEP_FACTORIES` dict has no validation that all entries match imports. | Commit 1 adds the test (§43.2). |
