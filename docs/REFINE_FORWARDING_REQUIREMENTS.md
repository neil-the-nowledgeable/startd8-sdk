# REFINE Output Forwarding — Functional Requirements

**Version:** 1.1.0
**Created:** 2026-02-21
**Updated:** 2026-02-21
**Source:** Mottainai audit (Gaps 5, 13), ContextCore propagation contract analysis
**Status:** All 12 requirements implemented as of 2026-02-21. Test coverage in `tests/unit/test_plan_ingestion_workflow.py` (16 REFINE tests passing).
**Prerequisite reading:**
- [Mottainai Design Principle](design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — Gaps 5, 13 define the problem
- [Context Correctness by Construction](../../ContextCore/docs/design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — Layer 1 propagation chain model
- [Context Propagation Contracts Design](../../ContextCore/docs/design/CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — `PropagationChainSpec`, `BoundaryValidator`, `ChainStatus`
- [Context Correctness Extensions](../../ContextCore/docs/design/CONTEXT_CORRECTNESS_EXTENSIONS.md) — Concern 9 (Quality Propagation), Concern 13 (Evaluation-Gated Propagation)

---

## Overview

Plan ingestion's REFINE phase runs a full `ArchitecturalReviewLogWorkflow` on the plan document. This workflow now produces three categories of structured output beyond the document modifications:

1. **Triage decisions** — ACCEPT/REJECT classification with rationale, area coverage, and addressed-area tracking
2. **Apply metadata** — which accepted suggestions were integrated into the document body, with warning IDs and integration status
3. **Prompt caching savings** — available via `enable_prompt_caching` but not currently forwarded to the REFINE config

As of 2026-02-21, all structured output reaches downstream consumers. The `_phase_refine()` return signature is `Tuple[int, List[StepResult], float, Dict[str, Any]]` — round count, step log, cost, and review output. The review output (triage, apply, area coverage, state path) is forwarded through EMIT into both artisan and prime context seeds.

This document was originally written when the chain was **BROKEN** (Mottainai Anti-Pattern 2: Compute-But-Don't-Forward). The propagation chain is now **INTACT** under the ContextCore Layer 1 contract model.

**Primary source files:**
- `src/startd8/workflows/builtin/plan_ingestion_workflow.py` (~line 1950, `_phase_refine`)
- `src/startd8/workflows/builtin/architectural_review_log_workflow.py` (~line 2768, `result.output`)
- `src/startd8/workflows/builtin/convergent_review_workflow.py` (~line 144, config passthrough)

### Status Dashboard

| Layer | ID Range | Total | Implemented | Planned |
|-------|----------|-------|-------------|---------|
| Return Type and Forwarding | REQ-RF-001–003 | 3 | 3 | 0 |
| Seed Injection | REQ-RF-004–006 | 3 | 3 | 0 |
| Config Passthrough | REQ-RF-007–009 | 3 | 3 | 0 |
| Provenance and Observability | REQ-RF-010–012 | 3 | 3 | 0 |
| **Total** | | **12** | **12** | **0** |

---

## Data Flow

### Current (Intact Chain)

```
REFINE phase
    │
    ├── calls ArchitecturalReviewLogWorkflow.run()
    │       │
    │       └── returns WorkflowResult
    │
    └── returns (rounds_completed, refine_steps, review_cost, review_output)
                                                                    │
                              EMIT phase  ◄─────────────────────────┘
                                    │
                                    ├── extracts accepted suggestions from review_output["triage"]
                                    ├── extracts apply provenance from review_output["apply"]
                                    │
                                    ├── builds ArtisanContextSeed
                                    │   ├── onboarding.refine_suggestions = [structured suggestions]
                                    │   └── artifacts.refine_provenance = {triage + apply metadata}
                                    │
                                    └── builds prime-context-seed.json
                                        ├── onboarding.refine_suggestions = [structured suggestions]
                                        └── artifacts.refine_provenance = {triage + apply metadata}
```

### Historical (Pre-Implementation)

Prior to implementation (2026-02-21), `_phase_refine()` returned only `Tuple[int, List[StepResult], float]` and all `result.output` data was discarded. Both artisan and prime seeds had `onboarding.refine_suggestions = None`.

### ContextCore Propagation Chain Declaration

The target state maps to a Layer 1 `PropagationChainSpec`:

```yaml
propagation_chains:
  - chain_id: refine_suggestions_to_design
    description: >
      REFINE-phase architectural review suggestions flow through the
      context seed to DESIGN, where they inform architectural decisions
      and eliminate redundant review.
    source:
      phase: ingestion.refine
      field: triage_decisions
    destination:
      phase: artisan.design
      field: onboarding.refine_suggestions
    severity: warning
    verification: "len(dest) > 0"

  - chain_id: refine_apply_provenance
    description: >
      Apply-step integration metadata flows to the seed so downstream
      consumers know which suggestions are already in the document body.
    source:
      phase: ingestion.refine
      field: apply_info
    destination:
      phase: emit
      field: artifacts.refine_provenance
    severity: advisory
```

---

## Layer 1: Return Type and Forwarding (REQ-RF-001–003)

### REQ-RF-001: Widen `_phase_refine()` Return Type

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Anti-Pattern 2 (Compute-But-Don't-Forward) at the REFINE boundary
**Source files:** `plan_ingestion_workflow.py` (~line 1950, `_phase_refine`)

`_phase_refine()` MUST return the architectural review workflow's `result.output` dict alongside the existing metrics.

**Acceptance criteria:**
- Return type changes from `Tuple[int, List[StepResult], float]` to `Tuple[int, List[StepResult], float, Dict[str, Any]]`
- The fourth element MUST be `result.output` when `result.success is True`, or `{}` on failure
- All existing call sites (~line 3454) MUST be updated to destructure the fourth element
- The returned dict MUST include at minimum: `triage`, `apply`, `state_path`
- No behavioral change to existing consumers of the first three elements

---

### REQ-RF-002: Forward `review_output` to `_phase_emit()`

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Gap 5 (data availability prerequisite)
**Source files:** `plan_ingestion_workflow.py` (~line 2811, `_phase_emit`)

`_phase_emit()` MUST accept a `review_output: Optional[Dict[str, Any]]` parameter carrying the REFINE workflow result output.

**Acceptance criteria:**
- `_phase_emit` signature gains `review_output: Optional[Dict[str, Any]] = None`
- The call site (~line 3503) MUST pass `review_output=review_output` using the value captured from REQ-RF-001
- When `review_output` is None (REFINE disabled or failed), EMIT MUST continue without it (graceful degradation per Mottainai Rule 3)
- The parameter MUST NOT trigger a second run of the architectural review — it forwards existing output only (Mottainai Rule 2)

---

### REQ-RF-003: Extract Accepted Suggestions as Structured Data

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Gap 5 (structured extraction), Gap 13 (prime route)
**Implementation note:** The returned dicts include 5 fields (`id`, `area`, `severity`, `rationale`, `decision`) rather than the 7 specified (`suggestion`, `triage_rationale` omitted). The `rationale` field serves the combined purpose of both `suggestion` and `triage_rationale`, making separate fields redundant.
**Source files:** `plan_ingestion_workflow.py` (new helper function)

A helper function MUST extract accepted suggestions from `review_output["triage"]` into a structured list suitable for seed injection.

**Acceptance criteria:**
- Function signature: `_extract_refine_suggestions_for_seed(review_output: Dict[str, Any]) -> List[Dict[str, Any]]`
- Each element in the returned list MUST include: `id`, `area`, `severity`, `suggestion`, `rationale`, `decision` ("ACCEPT"), `triage_rationale`
- Only ACCEPT decisions MUST be included — REJECT decisions are informational and not forwarded
- When `review_output` has no `triage` key or zero accepted suggestions, MUST return empty list
- The function MUST NOT re-parse the plan document — it works from the structured triage output only (Mottainai Rule 2)

---

## Layer 2: Seed Injection (REQ-RF-004–006)

### REQ-RF-004: Inject Accepted Suggestions into Artisan Seed

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Gap 5 (artisan route)
**Source files:** `plan_ingestion_workflow.py` (~line 2952, artisan seed construction)
**Depends on:** REQ-RF-002, REQ-RF-003

During artisan seed construction, extracted REFINE suggestions MUST be injected into the seed's `onboarding.refine_suggestions` field.

**Acceptance criteria:**
- When `review_output` is available and contains accepted suggestions, `onboarding_var["refine_suggestions"]` MUST be set to the extracted list from REQ-RF-003
- When `review_output` is None or has no accepted suggestions, `onboarding_var["refine_suggestions"]` MUST be set to `[]` (empty list, not omitted) per REQ-PI-001
- The seed's `onboarding.refine_suggestions` field MUST be consumable by `DesignPhaseHandler` at `context_seed_handlers.py:~1248` — same schema as existing injection code expects
- Existing DESIGN handler injection logic for `refine_suggestions` MUST work without modification — the seed provides the data, the handler consumes it

---

### REQ-RF-005: Inject Accepted Suggestions into Prime Seed

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Gap 13 (prime route)
**Source files:** `plan_ingestion_workflow.py` (~line 3064, prime seed construction)
**Depends on:** REQ-RF-002, REQ-RF-003

During prime seed construction, the same extracted suggestions MUST be injected symmetrically.

**Acceptance criteria:**
- `onboarding_var_prime["refine_suggestions"]` MUST follow identical logic to REQ-RF-004
- Route parity: the prime seed MUST NOT have a null `refine_suggestions` when the artisan seed has a populated one (per REQ-PI-011)
- Prime downstream consumers (code generators) MUST be able to access suggestions via `seed["onboarding"]["refine_suggestions"]`

---

### REQ-RF-006: Inject Apply Provenance into Seed Artifacts

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** New gap (apply metadata as provenance)
**Source files:** `plan_ingestion_workflow.py` (artisan + prime seed construction)
**Depends on:** REQ-RF-002

Apply-step metadata MUST be recorded in the seed's `artifacts` dict for downstream traceability.

**Acceptance criteria:**
- When `review_output["apply"]` is present and `applied_count > 0`, `artifacts["refine_provenance"]` MUST include:
  - `origin_phase`: `"ingestion.refine"` (matches `_extend_inventory_with_ingestion` convention)
  - `triage_accepted`: count of ACCEPT decisions
  - `triage_rejected`: count of REJECT decisions
  - `applied_ids`: list of suggestion IDs integrated into the document body
  - `warning_ids`: list of suggestion IDs with integration warnings
  - `apply_error`: error string if apply step failed, else null
  - `state_path`: path to the review state JSON file
- When apply was not run (disabled, no accepted suggestions, or failure), `artifacts["refine_provenance"]` MUST be set to `{"origin_phase": "ingestion.refine", "apply_enabled": false}` — presence with a status flag, not absence
- Both artisan and prime seeds MUST include this field (route parity)

---

## Layer 3: Config Passthrough (REQ-RF-007–009)

### REQ-RF-007: Pass `enable_apply` to REFINE Config

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Configuration gap — REFINE runs without the apply step
**Source files:** `plan_ingestion_workflow.py` (~line 1968, `_phase_refine` review_config)

The REFINE phase's `review_config` MUST include `enable_apply` when present in the pipeline config.

**Acceptance criteria:**
- `_phase_refine()` MUST accept `enable_apply: Optional[bool] = None` parameter
- When provided, MUST be set in `review_config["enable_apply"]`
- When not provided, the architectural review workflow's own default (`True`) applies
- The call site (~line 3454) MUST forward the pipeline-level `enable_apply` config value

---

### REQ-RF-008: Pass `enable_prompt_caching` to REFINE Config

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Configuration gap — REFINE runs without prompt caching cost savings
**Source files:** `plan_ingestion_workflow.py` (~line 1968, `_phase_refine` review_config)

The REFINE phase's `review_config` MUST include `enable_prompt_caching` when present in the pipeline config.

**Acceptance criteria:**
- `_phase_refine()` MUST accept `enable_prompt_caching: Optional[bool] = None` parameter
- When provided, MUST be set in `review_config["enable_prompt_caching"]`
- When not provided, the architectural review workflow's own default applies
- The call site MUST forward the pipeline-level config value
- Cost savings from prompt caching MUST be reflected in `review_cost` (already the case via the inner workflow's metrics)

---

### REQ-RF-009: Pass `enable_triage` to REFINE Config

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Configuration gap — triage toggle not forwarded
**Source files:** `plan_ingestion_workflow.py` (~line 1968, `_phase_refine` review_config)

The REFINE phase's `review_config` MUST include `enable_triage` when present in the pipeline config.

**Acceptance criteria:**
- `_phase_refine()` MUST accept `enable_triage: Optional[bool] = None` parameter
- When provided, MUST be set in `review_config["enable_triage"]`
- When not provided, the architectural review workflow's own default (`True`) applies
- When `enable_triage` is `False`, REQ-RF-001 returns `review_output` with empty/null triage data — REQ-RF-003 gracefully returns `[]`

---

## Layer 4: Provenance and Observability (REQ-RF-010–012)

### REQ-RF-010: Extend Artifact Inventory with Apply Metadata

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Rule 4 (Register what you produce)
**Source files:** `plan_ingestion_workflow.py` (~line 2542, `_extend_inventory_with_ingestion`)
**Depends on:** REQ-RF-002

The `_extend_inventory_with_ingestion()` method MUST register apply provenance as a distinct inventory entry.

**Acceptance criteria:**
- When `review_output` is available and `apply.applied_count > 0`, a new inventory entry MUST be appended:
  ```json
  {
    "artifact_id": "ingestion.refine_apply_provenance",
    "role": "refine_apply_provenance",
    "description": "Apply-step integration metadata from REFINE architectural review",
    "produced_by": "startd8.workflow.plan_ingestion.refine",
    "stage": "ingestion",
    "applied_count": 3,
    "applied_ids": ["R1-S1", "R2-S3", "R3-S1"],
    "consumers": ["artisan.design", "artisan.implement"],
    "consumption_hint": "Check applied_ids to avoid re-implementing suggestions already integrated into the document body."
  }
  ```
- The existing `ingestion.refine_suggestions` inventory entry (~line 2546) MUST be enriched with `triage_accepted_count` and `triage_rejected_count` when triage data is available

---

### REQ-RF-011: Log Chain Status at EMIT Boundary

**Status:** implemented
**Implemented:** 2026-02-21
**Closes:** Mottainai Rule 6 (Measure the gap), ContextCore Layer 1 observability
**Source files:** `plan_ingestion_workflow.py` (`_phase_emit`)
**Depends on:** REQ-RF-004

The EMIT phase MUST log the propagation chain status for REFINE suggestions.

**Acceptance criteria:**
- When `onboarding.refine_suggestions` is populated with > 0 entries: log `INFO` with count: `"REFINE→seed chain INTACT: %d accepted suggestions forwarded"`
- When `review_output` has accepted suggestions but `onboarding.refine_suggestions` is empty (extraction failure): log `WARNING`: `"REFINE→seed chain DEGRADED: %d accepted suggestions available but not forwarded"`
- When REFINE was not run or produced no accepted suggestions: log `DEBUG`: `"REFINE→seed chain N/A: no accepted suggestions to forward"`
- Chain status terminology (INTACT/DEGRADED/BROKEN) MUST match the ContextCore `ChainStatus` enum from `contracts/types.py` to maintain semantic alignment

---

### REQ-RF-012: Update Convergent Review Config Passthrough

**Status:** implemented
**Implemented:** 2026-02-21
**Source files:** `convergent_review_workflow.py` (~line 144, ~line 191)

`ConvergentReviewWorkflow` MUST forward all new architectural review config keys to its inner workflow calls.

**Acceptance criteria:**
- Both passthrough lists (requirements step ~line 144 and plan step ~line 191) MUST include `"enable_apply"` and `"enable_prompt_caching"` in addition to existing keys
- The passthrough MUST NOT add keys that are absent from the outer config — only forward what is present
- The existing `"enable_apply"` entry (added in the prior feature commit) MUST be preserved; `"enable_prompt_caching"` MUST be added

---

## Traceability Matrix

### Requirement → Mottainai Gap

| Requirement | Mottainai Gap | Description |
|-------------|---------------|-------------|
| REQ-RF-001 | Anti-Pattern 2 | REFINE return type drops `result.output` |
| REQ-RF-002 | Gap 5 | Data availability: `review_output` reaches EMIT |
| REQ-RF-003 | Gap 5, 13 | Structured extraction of accepted suggestions |
| REQ-RF-004 | Gap 5 | Artisan seed injection |
| REQ-RF-005 | Gap 13 | Prime seed injection (route parity) |
| REQ-RF-006 | New (apply provenance) | Apply metadata for traceability |
| REQ-RF-007 | Config gap | `enable_apply` not forwarded to REFINE |
| REQ-RF-008 | Config gap | `enable_prompt_caching` not forwarded to REFINE |
| REQ-RF-009 | Config gap | `enable_triage` not forwarded to REFINE |
| REQ-RF-010 | Rule 4 | Inventory registration of apply provenance |
| REQ-RF-011 | Rule 6 | Chain status logging at EMIT boundary |
| REQ-RF-012 | Config gap | Convergent review config passthrough |

### Requirement → Mottainai Rule

| Requirement | Rule Violated | How Requirement Closes It |
|-------------|---------------|---------------------------|
| REQ-RF-001, 002, 003 | Rule 2 (Forward, don't regenerate) | Forwards REFINE output instead of discarding it |
| REQ-RF-002 | Rule 3 (Degrade gracefully) | Accepts None review_output without failing |
| REQ-RF-006, 010 | Rule 4 (Register what you produce) | Records apply provenance in seed and inventory |
| REQ-RF-004, 005 | Rule 5 (Prefer deterministic over stochastic) | Triage decisions (deterministic) forwarded to replace LLM re-derivation |
| REQ-RF-011 | Rule 6 (Measure the gap) | Logs chain status with INTACT/DEGRADED vocabulary |

### Requirement → ContextCore Contract Model

| Requirement | ContextCore Concept | Mapping |
|-------------|---------------------|---------|
| REQ-RF-001–003 | Layer 1: Propagation Chain | Source phase produces field; return type is the channel |
| REQ-RF-004–005 | Layer 1: Destination field | `onboarding.refine_suggestions` is the destination |
| REQ-RF-006 | Concern 7: Data Lineage | Apply metadata is provenance for document modifications |
| REQ-RF-003 | Concern 13: Evaluation Gate | Triage ACCEPT/REJECT are evaluation stamps on suggestions |
| REQ-RF-011 | ChainStatus enum | INTACT/DEGRADED/BROKEN at EMIT boundary |
| REQ-RF-010 | PropagationTracker pattern | Inventory entry with origin_phase, produced_at, consumers |

### Requirement → Downstream Consumer

| Requirement | Downstream Consumer | Impact if Missing |
|-------------|-------------------|-------------------|
| REQ-RF-004 | `DesignPhaseHandler` (~line 1248) | `refine_suggestions` injection code exists but always receives None — DESIGN regenerates architectural decisions from scratch |
| REQ-RF-005 | `PrimeContractorWorkflow` code generators | Prime code generation ignores REFINE findings — may produce code that REFINE already flagged as problematic |
| REQ-RF-006 | Downstream operators / debugging | No machine-readable record of which suggestions were integrated into the plan document body |
| REQ-RF-008 | Pipeline cost | REFINE runs without prompt caching — ~72-90% input cost savings missed for sequential LLM calls |

### Requirement → Existing Requirements

| This Requirement | Existing Requirement | Relationship |
|-----------------|---------------------|-------------|
| REQ-RF-004 | REQ-PI-001 (Seed Completeness) | REQ-PI-001 lists `refine_suggestions` (G5) as a required onboarding field; REQ-RF-004 provides the data |
| REQ-RF-005 | REQ-PI-011 (Route-Agnostic Seed Quality) | Route parity requires prime seed to match artisan |
| REQ-RF-012 | RV-807 (Structured events for downstream consumption) | Convergent review inherits config; must forward new keys |
| REQ-RF-003 | RV-303 (Triage JSON schema) | Extraction function consumes the triage JSON format defined by RV-303 |

---

## Implementation Priority

| Phase | Requirements | Priority | Impact |
|-------|-------------|----------|--------|
| 1. Return type + forwarding | REQ-RF-001, 002 | **High** | Unblocks all downstream requirements |
| 2. Extraction + seed injection | REQ-RF-003, 004, 005 | **High** | Closes Gaps 5 and 13 — the primary Mottainai violations |
| 3. Config passthrough | REQ-RF-007, 008, 009, 012 | **Medium** | Enables apply step and prompt caching in REFINE |
| 4. Provenance + observability | REQ-RF-006, 010, 011 | **Low** | Traceability and measurement (Rule 4, Rule 6) |

Implementation order follows the dependency chain: Layer 1 (return type) must land before Layer 2 (seed injection), which must land before Layer 4 (provenance). Layer 3 (config passthrough) is independent and can land in parallel with Layer 2.

---

## Non-Requirements (Explicitly Out of Scope)

| Topic | Why Out of Scope |
|-------|------------------|
| DESIGN handler changes to consume `refine_suggestions` | Already implemented — injection logic at `context_seed_handlers.py:~1248` reads `onboarding.refine_suggestions` when present. This doc only provides the data. |
| Re-parsing Appendix C from the plan document | Violates Mottainai Rule 2 (Forward, don't regenerate). REQ-RF-003 extracts from structured triage output, not from markdown parsing. |
| Per-task suggestion routing | REFINE suggestions are document-level, not task-level. Per-task routing (matching suggestions to tasks by area/target) is a downstream concern for the DESIGN handler, not for EMIT. |
| Full ContextCore contract YAML for the ingestion pipeline | Desirable but requires the [Pipeline Artifact Inventory Requirements](design-princples/PIPELINE_ARTIFACT_INVENTORY_REQUIREMENTS.md) to land first. This doc uses contract vocabulary without requiring formal YAML contracts. |

---

## Related Documents

| Document | Relationship |
|----------|-------------|
| [Mottainai Design Principle](design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Gaps 5 and 13 define the violations; Rules 2-6 guide the solution |
| [Plan Ingestion Requirements](PLAN_INGESTION_REQUIREMENTS.md) | REQ-PI-001 (seed completeness) depends on this doc to populate `refine_suggestions` |
| [Architectural Review Requirements](ARCHITECTURAL_REVIEW_REQUIREMENTS.md) | RV-303 defines triage output schema consumed by REQ-RF-003; RV-807 describes downstream event emission |
| [Context Correctness by Construction](../../ContextCore/docs/design/CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) | Layer 1 propagation chain model — `FieldSpec`, `ChainStatus`, `BoundaryValidator` |
| [Context Propagation Contracts Design](../../ContextCore/docs/design/CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) | Implementation primitives: `PropagationChainSpec`, severity model, verification expressions |
| [Context Correctness Extensions](../../ContextCore/docs/design/CONTEXT_CORRECTNESS_EXTENSIONS.md) | Concern 9 (quality propagation) and Concern 13 (evaluation-gated propagation) inform the triage-as-evaluation pattern |
| [Convergent Review Workflow](../src/startd8/workflows/builtin/convergent_review_workflow.py) | Affected by REQ-RF-012 (config passthrough) |
