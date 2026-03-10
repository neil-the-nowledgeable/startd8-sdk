# Keiyaku A2A Boundary Contracts (REQ-MP-5xx Addendum)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Partially implemented
> **Version:** 1.0.0
> **Created:** 2026-03-10
> **Design principle:** [KEIYAKU_DESIGN_PRINCIPLE.md](../../design-princples/KEIYAKU_DESIGN_PRINCIPLE.md)
> **Gap analysis:** [KEIYAKU_GAP_ANALYSIS.md](./KEIYAKU_GAP_ANALYSIS.md)

---

## Overview

This document formalizes the Keiyaku boundary contracts implemented in the Micro Prime engine.
Each requirement defines a typed JSON contract at an agent-to-agent boundary,
replacing unstructured prose or implicit conventions.

These requirements were derived from the gap analysis in `KEIYAKU_GAP_ANALYSIS.md`.
Batch 1 implemented 4 contracts (K-6, K-7, K-9, K-10). This document captures the
formal requirements for each, plus the compliance gate (REQ-MP-1010) that prevents
future violations.

---

## Requirements

### REQ-MP-504: Semantic Verification Output Contract (K-7)

**Status:** contract defined (not yet wired)
**Priority:** High
**Implements:** Gap A-2 in KEIYAKU_GAP_ANALYSIS.md

When semantic verification (Capability Audit A2) is wired, the LLM verifier
MUST produce output conforming to `SemanticVerificationResult` in
`src/startd8/micro_prime/models.py`.

**Schema (v1.0.0, frozen):**

The JSON schema is defined in the `SemanticVerificationResult` docstring in `models.py`.

**Validation rules (Keiyaku Rule 5):**
- Unknown verdicts auto-correct to `"inconclusive"`
- Confidence clamped to [0.0, 1.0]
- Missing fields get safe defaults (severity → `"medium"`, category → `"unknown"`)
- Parse via `validate_semantic_verification_json()` in `models.py`

**Acceptance criteria:**
- [ ] LLM prompt includes JSON schema example
- [ ] Response parsed via `validate_semantic_verification_json()`
- [ ] Auto-corrections logged at WARNING
- [ ] Round-trip test: `from_json(to_dict(result)) == result`

---

### REQ-MP-513: Structured Escalation Handoff Contract (K-6)

**Status:** implemented
**Priority:** Medium
**Implements:** Gap A-1 in KEIYAKU_GAP_ANALYSIS.md

When a SIMPLE element escalates to cloud, the escalation context MUST be
constructed as an `EscalationHandoff` in `src/startd8/micro_prime/models.py`
and attached to `EscalationContext.escalation_handoff`.

**Contract fields:**
- `element_fqn`, `original_tier`, `local_model`, `attempt_count`
- `failure_category` (matches `EscalationReason` enum), `failure_message`
- `raw_output_lines`
- `repair`: Optional `EscalationRepairOutcome` (K-9)
- `element_signature`, `element_kind`, `parent_class`

**Serialization:**
- `to_dict()` → JSON-compatible dict
- `to_prompt_section()` → structured prompt with JSON block + human-readable summary

**Wiring (3 escalation sites in `_handle_simple`):**
1. AST failure after repair → `EscalationReason.AST_FAILURE`
2. Structural verification failure → `EscalationReason.STRUCTURAL_MISMATCH`
3. Semantic verification failure → `EscalationReason.SEMANTIC_FAILURE`

**Acceptance criteria:**
- [ ] All 3 escalation sites construct `EscalationHandoff`
- [ ] `prime_adapter.py` uses `to_prompt_section()` when handoff present
- [ ] Backward compat: prose fallback when no handoff (legacy path)

---

### REQ-MP-604: Repair Outcome Boundary Contract (K-9)

**Status:** implemented
**Priority:** Medium
**Implements:** Gap A-4 in KEIYAKU_GAP_ANALYSIS.md

Repair pipeline results crossing the escalation boundary MUST use
`EscalationRepairOutcome` in `src/startd8/micro_prime/models.py`.

**Factory:** `to_escalation_repair_outcome()` in `repair.py` converts
internal `RepairResult` + step results into the boundary contract.

**Verdict logic:**
- `"recovered"` — AST invalid before, valid after repair
- `"failed"` — AST still invalid after repair
- `"unchanged"` — no steps modified the code

**Per-step detail derivation:**
- Step metrics (e.g., `nodes_removed`, `import_names`) converted to
  human-readable `detail` strings

**Acceptance criteria:**
- [ ] `to_escalation_repair_outcome()` tested with all 3 verdict paths
- [ ] Step details derived from metrics, not hardcoded
- [ ] `to_dict()` produces valid JSON

---

### REQ-MP-903: LLM-Assisted Decomposition Contract (K-8)

**Status:** planned (contract not yet needed — no LLM decomposition exists)
**Priority:** Medium
**Implements:** Gap A-3 in KEIYAKU_GAP_ANALYSIS.md

If any future decomposition strategy uses LLM calls to plan sub-element
breakdown, the LLM MUST produce output conforming to a typed
`DecompositionPlanContract` schema.

**Trigger:** This requirement activates when:
- FunctionChainStrategy adds LLM-assisted clause extraction
- Simple-to-Trivial Decomposer Phase 2-3 adds LLM planning
- Any new strategy calls an LLM during `decompose()`

**Minimum contract fields:**
- `strategy`: string (strategy name)
- `confidence`: float [0.0, 1.0]
- `original_element`: string (element being decomposed)
- `sub_elements[]`: array of `{name, kind, responsibility, depends_on, estimated_lines, signature_hint}`
- `dispatch_body`: optional `{description, estimated_lines}`

**Implementation must follow Keiyaku Rule 4 (dual-format transition)** if
replacing an existing deterministic decomposer with an LLM-assisted variant.

**Acceptance criteria:**
- [ ] Schema defined in `micro_prime/models.py` before first LLM decomposition PR
- [ ] JSON schema included in LLM prompt
- [ ] Consumer validates via dedicated parser with safe defaults
- [ ] Deterministic fallback when LLM output fails validation

---

### REQ-MP-1010: Keiyaku Compliance Gate (Cross-Cutting)

**Status:** active (policy requirement)
**Priority:** High
**Scope:** All Micro Prime modules

**Policy:** All new agent-to-agent boundaries that involve LLM calls MUST
define a typed JSON input/output contract BEFORE implementation begins.

**Definition of "agent-to-agent boundary":**

A function or method where:
1. An LLM is called and its output parsed for structured data (not code), OR
2. Structured data produced by one agent is consumed by another agent's decision logic

**NOT an A2A boundary:**
- Code generation output parsed by `extract_code_from_response()` (the contract is the programming language)
- Template rendering (deterministic, no LLM)
- Internal dataclass construction within a single module

**Compliance checklist** (from KEIYAKU_DESIGN_PRINCIPLE.md):
- [ ] JSON schema defined in prompt
- [ ] Consumer validates before processing
- [ ] Validation errors include reason + next_action
- [ ] Human-readable rendering separate from validation
- [ ] Format used emitted as telemetry attribute

**Enforcement:** Code review must verify Keiyaku compliance for any PR that
adds or modifies an LLM-calling boundary in `micro_prime/`.

---

## Files

| File | Purpose |
|------|---------|
| `src/startd8/micro_prime/models.py` | `SemanticVerificationResult`, `EscalationHandoff`, `EscalationRepairOutcome` contracts |
| `src/startd8/micro_prime/repair.py` | `to_escalation_repair_outcome()` factory |
| `src/startd8/micro_prime/prime_adapter.py` | `to_prompt_section()` consumption for escalation |
| `src/startd8/micro_prime/engine.py` | Escalation sites in `_handle_simple` |
| `src/startd8/complexity/models.py` | `ClassificationResult` dataclass (K-10, Gap D-1) |
