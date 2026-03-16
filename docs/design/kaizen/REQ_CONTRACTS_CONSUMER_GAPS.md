# Requirements: Contracts Consumer Gaps — startd8-sdk

> **Status:** Assessment
> **Date:** 2026-03-16
> **Author:** Observability Team
> **Scope:** startd8-sdk's role as consumer of `contextcore.contracts` — what's wired, what's broken, what's unused
> **Method:** Static analysis of all `contextcore.contracts` imports and forward manifest contract usage
> **Trigger:** `ContextCore Layer 5 validation unavailable: No module named 'contextcore.contracts'` warning in run-054
> **Companion docs:**
> - ContextCore: [REQ_CONTRACTS_GAP_ANALYSIS.md](~/Documents/dev/ContextCore/docs/design/requirements/REQ_CONTRACTS_GAP_ANALYSIS.md)
> - cap-dev-pipe: [REQ_GOVERNANCE_GATE_GAPS.md](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md)

---

## 1. Context

startd8-sdk has **8 integration points** that import from `contextcore.contracts`. All are behind `try/except ImportError` — the system works without ContextCore installed. However, the optional validation these imports enable is currently **never active** due to a namespace package collision.

Additionally, the forward manifest carries 1,236 interface contracts that `binding_constraints_for_task()` attempts to inject into LLM prompts — but the contracts lack the data needed for matching, so bindings are empty for most tasks.

---

## 2. Gap Inventory

### GAP-SDK-001: Namespace Package Collision Prevents contextcore.contracts Import

**Severity:** P3
**Files affected:** All 8 integration points

**Root cause:** startd8-sdk has a partial `contextcore` namespace package at `src/contextcore/generators/`. When the startd8-sdk virtualenv resolves `import contextcore.contracts`, Python finds `src/contextcore/` (which has no `contracts/` subpackage) before the full ContextCore installation.

**Current behavior:** Every pipeline run emits:
```
WARNING - ContextCore Layer 5 validation unavailable: No module named 'contextcore.contracts'
```

**Integration points affected:**

| File | Import | Purpose | Fallback |
|------|--------|---------|----------|
| `contractors/gate_contracts.py:25` | `a2a.models.GateResult` etc. | Structured quality gate emission | Dict with identical shape |
| `contractors/handoff.py:62` | `a2a.models.HandoffContract` etc. | Typed handoff models | `Any` aliases (models never used) |
| `contractors/context_schema.py:611` | `propagation.BoundaryValidator` | Phase boundary validation | Returns `None` (skipped) |
| `contractors/artisan_contractor.py:1908` | `propagation.otel.emit_boundary_result` | OTel emission of boundary results | `pass` (silently skipped) |
| `contractors/artisan_contractor.py:1988` | `propagation.otel.emit_boundary_result` | OTel emission (exit) | `pass` (silently skipped) |
| `contractors/context_seed/core.py:8960` | `propagation.BoundaryValidator` | Propagation tracking | Unknown fallback |
| `workflows/builtin/plan_ingestion_workflow.py:3366` | `capability.validator.CapabilityValidator` | Layer 5 capability validation | Skipped entirely |
| `workflows/registry.py:455` | `propagation.validator.BoundaryValidator` | Optional workflow validation | Skipped entirely |

**Options:**

| Option | Effort | Trade-off |
|--------|--------|-----------|
| **A:** `pip3 install -e ~/Documents/dev/ContextCore` in startd8-sdk venv | 1 command | Works if both packages use implicit namespace packages correctly |
| **B:** Move `src/contextcore/generators/` to `src/startd8/contextcore_generators/` | ~20 lines | Eliminates collision permanently; requires import path update |
| **C:** Document as intentional — contracts are optional | 0 lines | Matches current behavior; warning remains |

**Acceptance:** `from contextcore.contracts.types import TaskStatus` succeeds in the startd8-sdk venv.

---

### GAP-SDK-002: Propagation Boundary Validation Bypassed on Prime Route

**Severity:** P3
**Files:** `contractors/context_schema.py`, `contractors/artisan_contractor.py`

**What exists:**
- `validate_phase_boundary()` calls `BoundaryValidator` + `ContractLoader` for artisan phase transitions
- `artisan-pipeline.contract.yaml` (722 lines) defines entry/exit requirements for 8 artisan phases
- `artisan_contractor.py` emits boundary results to OTel at phase entry/exit
- 7 test files in `tests/contract_validation/` validate behavior

**What's missing:**
- `PipelineContextStrategy` (`context_strategy.py:134`) has no contract validation hooks
- The prime contractor route — used by all current pipeline runs — has no equivalent of `validate_phase_boundary()`
- `plan-ingestion.contract.yaml` exists but its consumer can't import the validator (GAP-SDK-001)

**Impact:** Phase boundary validation only runs on the artisan route. Since current runs use the prime route, this validation is dormant.

**Options:**

| Option | Effort | Trade-off |
|--------|--------|-----------|
| **A:** Add boundary validation to `PipelineContextStrategy.resolve_context()` | ~30 lines | Parity with artisan; requires GAP-SDK-001 fix first |
| **B:** Acknowledge as artisan-only | 0 lines | Matches current architecture; prime route has simpler phase model |
| **C:** Create `prime-pipeline.contract.yaml` + hook into prime task loop | ~100 lines | Full prime coverage; unclear if warranted |

---

### GAP-SDK-003: Forward Manifest Contracts Return Empty Bindings

**Severity:** P2
**Files:** `forward_manifest.py`, `implementation_engine/drafter.py`, `contractors/context_resolution.py`

**What exists:**
- `binding_constraints_for_task(task_id)` called by `drafter.py:723` and `context_resolution.py:812`
- Forward manifest carries 1,236 `InterfaceContract` objects (752 `function_name`, 207 `class_name`)
- Binding text is injected into LLM prompts as `## Interface Contract Bindings`

**What's missing:**
- None of the 1,236 contracts have a `file_path` field set
- `contracts_for_task()` matches by `applicable_task_ids` but returns 0 contracts for most tasks
- The contracts duplicate data already present in `file_specs.elements`
- ~400KB seed overhead with no generation impact

**Impact:** The constraint injection mechanism (`drafter.py:723`) falls through to the generic `forward_contracts` fallback. LLM prompts receive no task-specific interface contract bindings, contributing to the proto import hallucination problem identified in the [Cross-Cutting Context Loss Analysis](CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md).

**Options:**

| Option | Effort | Trade-off |
|--------|--------|-----------|
| **A:** Populate `file_path` + `applicable_task_ids` during forward manifest construction | ~30 lines | Bindings start working; contracts become useful |
| **B:** Deprecate contracts, derive bindings from `file_specs.elements` | ~50 lines | Eliminates 400KB overhead; single source of truth |
| **C:** Keep as-is | 0 lines | Proto import hallucination persists for dependent tasks |

**Recommendation:** Option B aligns with the Cross-Cutting Context Loss Analysis §7 Question 4 assessment.

---

### GAP-SDK-004: Dead Handoff Contract Imports

**Severity:** P4
**File:** `contractors/handoff.py:62-75`

**What exists:**
```python
try:
    from contextcore.contracts.a2a.models import (
        HandoffContract, HandoffPriority, HandoffContractStatus, ExpectedOutput,
    )
    CONTEXTCORE_AVAILABLE = True
except ImportError:
    CONTEXTCORE_AVAILABLE = False
    HandoffContract = Any
    ...
```

**What's missing:** None of the imported types (`HandoffContract`, `HandoffPriority`, `HandoffContractStatus`, `ExpectedOutput`) are referenced in any active code path. Handoff validation uses `HANDOFF_SCHEMA` (JSON Schema dict at line 78), not Pydantic models.

**Impact:** Zero. The imports fail silently and the code works.

**Options:**

| Option | Effort | Trade-off |
|--------|--------|-----------|
| **A:** Remove dead imports | 2 lines | Clean signal; re-add when typed handoffs are implemented |
| **B:** Implement typed handoff validation (REQ-CID P2 004-006) | ~100 lines | Replaces JSON Schema with Pydantic; more type safety |

---

## 3. Priority Summary

| Gap | Severity | Effort | Recommendation |
|-----|----------|--------|----------------|
| GAP-SDK-001 (namespace collision) | P3 | Low | Option C (document) or Option A (pip install) |
| GAP-SDK-002 (prime route bypass) | P3 | Medium | Option B (acknowledge artisan-only) |
| GAP-SDK-003 (empty bindings) | P2 | Medium | Option B (derive from file_specs) |
| GAP-SDK-004 (dead imports) | P4 | Trivial | Option A (remove) |

---

## 4. Cross-References

| Document | Relationship |
|----------|-------------|
| [ContextCore: REQ_CONTRACTS_GAP_ANALYSIS.md](~/Documents/dev/ContextCore/docs/design/requirements/REQ_CONTRACTS_GAP_ANALYSIS.md) | ContextCore-scoped gaps (dormant layers, essential components) |
| [cap-dev-pipe: REQ_GOVERNANCE_GATE_GAPS.md](~/Documents/dev/cap-dev-pipe/design/REQ_GOVERNANCE_GATE_GAPS.md) | Pipeline gate wiring gaps |
| [Cross-Cutting Context Loss Analysis](CROSS_CUTTING_CONTEXT_LOSS_ANALYSIS.md) | §6-7: Forward manifest contracts overhead, Question 4 |
| [Kaizen Seed Utilization Requirements](KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | §1.3: Seed field consumption map |
| [Service Communication Graph Consumption](SERVICE_COMMUNICATION_GRAPH_CONSUMPTION_REQUIREMENTS.md) | REQ-SIG-200/201: Graph-based import injection (complementary fix) |
