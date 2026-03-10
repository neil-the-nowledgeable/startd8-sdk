# Micro Prime — Keiyaku Gap Analysis

**Version:** 1.0.0
**Created:** 2026-03-10
**Parent:** [KEIYAKU_DESIGN_PRINCIPLE.md](../../design-princples/KEIYAKU_DESIGN_PRINCIPLE.md)
**Scope:** All agent-to-agent boundaries in `micro_prime/`, `complexity/`, `implementation_engine/`, and `utils/code_extraction.py`

---

## Classification Framework

The Keiyaku principle targets **agent-to-agent communication** — boundaries where one component produces structured data that another component must interpret to make decisions. Pure code generation output (LLM produces Python source) is a different category: the "contract" there is the programming language itself, validated by `ast.parse()`.

We classify each boundary into three categories:

| Category | Description | Keiyaku Applies? |
|----------|-------------|-----------------|
| **A2A Data** | Structured data exchange (classifications, plans, diagnostics, suggestions) | Yes — schema-first |
| **Code Output** | LLM-generated source code parsed by tooling | Partial — extraction robustness, not schema migration |
| **Internal Typed** | Dataclass/Pydantic handoffs between deterministic components | Already compliant — verify validation |

---

## Boundary Inventory (14 Boundaries)

### Already Keiyaku-Compliant (Internal Typed)

These boundaries use typed dataclasses/enums with deterministic producers. No migration needed — verify validation exists.

| # | Boundary | Format | Status |
|---|----------|--------|--------|
| B1 | `classify_tier()` → Engine | `(ComplexityTier, str)` enum + reason | Compliant |
| B2 | Template match → Engine | `Optional[TemplateMatch]` dataclass | Compliant |
| B5 | Repair pipeline (internal steps) | `RepairStepResult` dataclass chain | Compliant |
| B7 | Decomposer → Engine | `Optional[DecompositionPlan]` dataclass | Compliant |
| B9 | Escalation → Cloud handoff | `EscalationResult` dataclass | Compliant |
| B14 | Import audit → Code patching | `Tuple[str, list[str]]` | Compliant |

**Action:** None. These are positive Keiyaku examples within micro prime.

### Code Output Boundaries (Partial Keiyaku)

These involve LLM-generated source code. The "contract" is the programming language, not a JSON schema. Keiyaku applies to the *extraction and validation* layers, not the code content itself.

| # | Boundary | Current Parser | Risk |
|---|----------|---------------|------|
| B4 | LLM response → `extract_code_from_response()` | Regex (fence detection + heuristic) | Low — 4-layer fallback is robust |
| B6 | Repaired code → Splicer | AST + regex | Low — AST validation is the gold standard |
| B12 | Cloud response → Truncation detection | 3-layer heuristic | Low — multi-source triangulation |
| B13 | Cloud response → `extract_multi_file_code()` | Regex (file markers, fenced blocks, basename matching) | **Medium** — 4-layer heuristic with stub fallback |

**Action:** B13 is the highest-risk code extraction boundary. See Gap C-1 below.

### A2A Data Boundaries (Keiyaku Migration Needed)

These are the boundaries where structured data crosses an agent boundary via unstructured or semi-structured formats:

| # | Boundary | Current Format | Keiyaku Gap |
|---|----------|---------------|-------------|
| B3 | Prompt builder → Ollama | Prose instructions | Gap A-1 |
| B8 | Sub-element generation (decomposer→engine) | Code string per sub-element | Gap A-2 |
| B10 | Drafter system prompt → Cloud | YAML template + mode string | Gap A-3 |
| B11 | Draft prompt → Cloud | Assembled prose with budget | Gap A-4 |

---

## Keiyaku Gaps

### Gap A-1: Escalation Context Is Prose, Not Contract

**Status:** IMPLEMENTED (REQ-MP-513)
**Boundary:** B9 (escalation) → B10/B11 (cloud prompt)
**Requirement Impact:** REQ-MP-502 (escalation flow), REQ-MP-512

**Current state:** When a SIMPLE element escalates to cloud, the escalation context is injected as prose:
```
## Prior Local Model Attempt
- Element: {fqn}
- Local model: {model}
- Error: {error}
- Repair steps applied: {steps}
```

The cloud LLM reads this as unstructured context. There is no schema for what the cloud model should *do* with this information — it's advisory prose that may or may not influence the generation.

**Keiyaku violation:** The escalation represents a formal handoff from one agent (local Ollama) to another (cloud model). The receiving agent should know:
1. What was attempted (structured: model, tier, attempt count)
2. What failed (structured: error category, error message, AST node if applicable)
3. What was repaired (structured: steps applied, which succeeded/failed)
4. What the expected output shape is (structured: same element spec)

**Proposed contract:**
```json
{
  "escalation": {
    "element_fqn": "module.ClassName.method_name",
    "original_tier": "SIMPLE",
    "local_model": "startd8-coder",
    "attempt_count": 1,
    "failure": {
      "category": "AST_FAILURE",
      "message": "SyntaxError: unexpected indent at line 5",
      "raw_output_lines": 12
    },
    "repair_applied": [
      {"step": "fence_strip", "modified": true},
      {"step": "indent_normalize", "modified": true},
      {"step": "ast_validate", "modified": false, "result": "fail"}
    ],
    "element_spec": {
      "name": "method_name",
      "kind": "METHOD",
      "signature": "def method_name(self, x: int) -> str",
      "parent_class": "ClassName"
    }
  }
}
```

**Priority:** Medium. The escalation path already works (cloud model generates code regardless), but structured context would improve cloud model accuracy by giving it machine-readable failure diagnostics rather than prose it may misinterpret.

**Requirements to update:** REQ-MP-502, REQ-MP-512 — add structured escalation contract schema.

---

### Gap A-2: Semantic Verification Has No Output Contract

**Status:** CONTRACT DEFINED (REQ-MP-504, wiring pending)
**Boundary:** Semantic verifier (LLM) → Engine decision (accept/reject/escalate)
**Requirement Impact:** REQ-MP-503 (structural verification), Capability Audit A2

**Current state:** Semantic verification is implemented but unwired (A2 in Capability Audit). When wired, it will make an LLM call to verify that generated code is semantically correct. The current code returns a `bool` from `structural_verify()`, but the semantic variant would need:
1. Pass/fail verdict
2. Reason (what is semantically wrong)
3. Confidence (how sure the verifier is)
4. Suggested fix (optional — what would correct the issue)

**Keiyaku violation:** This is an agent-to-agent boundary (LLM verifier → engine decision logic) that currently has no defined output contract. When it gets wired, the temptation will be to parse prose from the LLM ("The code looks correct because...") rather than require structured output.

**Proposed contract:**
```json
{
  "verification": {
    "verdict": "fail",
    "confidence": 0.85,
    "issues": [
      {
        "severity": "high",
        "category": "missing_error_handling",
        "description": "Division by total_count without zero check",
        "line_hint": 7,
        "suggested_fix": "Add guard: if total_count == 0: return 0.0"
      }
    ],
    "element_fqn": "module.ClassName.calculate_ratio"
  }
}
```

**Priority:** High. This contract should be defined *before* wiring A2, not after. Defining it now prevents the RV-9xx pattern (implement prose-first, migrate to JSON later).

**Requirements to update:** REQ-MP-503 — add semantic verification output schema. New requirement: REQ-MP-504 (Keiyaku-compliant semantic verification contract).

---

### Gap A-3: Decomposition Planning Lacks LLM-Assisted Contract

**Status:** PLANNED (REQ-MP-903, triggers on first LLM decomposition)
**Boundary:** Decomposer → Engine (sub-element plan)
**Requirement Impact:** REQ-MP-9xx (Moderate Decomposer), FunctionChainStrategy

**Current state:** Both decomposition strategies (ClassDecomposeStrategy, FunctionChainStrategy) are fully deterministic — no LLM calls. They produce `DecompositionPlan` dataclasses, which is Keiyaku-compliant.

**Future risk:** The Simple-to-Trivial Decomposer (Phase 2–3) and potential LLM-assisted clause extraction for FunctionChainStrategy introduce LLM calls into decomposition. If an LLM is asked "break this function into 3 helpers", its response needs a structured contract — not prose that gets regex-parsed into sub-element names.

**Proposed contract (for LLM-assisted decomposition):**
```json
{
  "decomposition_plan": {
    "strategy": "function_chain",
    "confidence": 0.78,
    "original_element": "process_order",
    "sub_elements": [
      {
        "name": "_validate_order_items",
        "kind": "helper",
        "responsibility": "Validate all order items exist in inventory",
        "depends_on": [],
        "estimated_lines": 8,
        "signature_hint": "def _validate_order_items(self, items: list[OrderItem]) -> bool"
      },
      {
        "name": "_calculate_totals",
        "kind": "helper",
        "responsibility": "Sum item prices with tax and discount",
        "depends_on": ["_validate_order_items"],
        "estimated_lines": 12,
        "signature_hint": "def _calculate_totals(self, items: list[OrderItem]) -> Decimal"
      }
    ],
    "dispatch_body": {
      "description": "Call validate, then calculate, then persist",
      "estimated_lines": 5
    }
  }
}
```

**Priority:** Medium. No LLM-assisted decomposition exists today, but the requirements (Phase 2–3 of Simple-to-Trivial, D1/D2 in audit) anticipate it. Defining the contract now prevents prose-parsing later.

**Requirements to update:** REQ-MP-901, REQ-MP-902 — add note that any future LLM-assisted decomposition must use this contract. New requirement: REQ-MP-903 (Keiyaku decomposition output contract for LLM-assisted strategies).

---

### Gap A-4: Repair Diagnostics Are Step-Lists, Not Actionable Contracts

**Status:** IMPLEMENTED (REQ-MP-604)
**Boundary:** Repair pipeline → Engine decision → Observability
**Requirement Impact:** REQ-MP-400–407 (repair pipeline), REQ-MP-600–603 (observability)

**Current state:** `RepairResult` is a typed dataclass with `steps_applied: list[str]` and per-step `RepairStepResult`. This is already semi-structured. However:

1. The `steps_applied` field is a flat string list (`["fence_strip", "indent_normalize"]`), not a structured record of what each step did and why.
2. The escalation path (Gap A-1) serializes repair results as prose rather than forwarding the structured `RepairResult`.
3. The observability output (REQ-MP-601) defines per-step metrics but doesn't define a JSON contract for the experiment result that downstream tools (Kaizen analysis, dashboard) consume.

**Keiyaku violation:** The repair pipeline's internal contract (`RepairStepResult`) is good. The violation is at the *output boundaries* — when repair results are forwarded to escalation (prose) or observability (flat metrics). The structured detail exists internally but degrades at the boundary.

**Proposed enhancement:**
```json
{
  "repair_outcome": {
    "element_fqn": "module.Class.method",
    "ast_valid_before": false,
    "ast_valid_after": true,
    "steps": [
      {
        "name": "fence_strip",
        "modified": true,
        "ast_valid_after": false,
        "detail": "Removed ```python fence (3 lines stripped)"
      },
      {
        "name": "over_generation_trim",
        "modified": true,
        "ast_valid_after": false,
        "detail": "Removed 2 extra functions (helper_a, helper_b) not matching target FQN"
      },
      {
        "name": "indent_normalize",
        "modified": true,
        "ast_valid_after": true,
        "detail": "Re-indented from 2-space to 4-space (skeleton hint)"
      }
    ],
    "final_verdict": "recovered",
    "lines_before": 18,
    "lines_after": 12
  }
}
```

**Priority:** Low-Medium. The repair pipeline works well internally. This gap matters most for Kaizen analysis (REQ-MP-603 experiment results) and escalation context (Gap A-1).

**Requirements to update:** REQ-MP-601 (per-step attribution) — add JSON output contract. REQ-MP-603 (experiment results) — reference schema version.

---

### Gap C-1: Multi-File Extraction Uses 4-Layer Heuristic

**Boundary:** B13 — Cloud LLM response → `extract_multi_file_code()`
**Requirement Impact:** Impacts PrimeContractor and LeadContractor output parsing

**Current state:** `extract_multi_file_code()` uses 4 layers of regex/heuristic matching to identify which code block belongs to which file:
1. File-path marker lines (`// path/to/file.ts`, `# path/to/file.py`)
2. Fenced code blocks with language tags
3. Content heuristics (`__init__.py` detection)
4. Stub generation for unmatched files

**Keiyaku analysis:** This is a *code output* boundary, not an A2A data boundary. The LLM is producing code files, not structured data. However, the *file routing* metadata (which code belongs to which file) IS structured data that could be expressed as a contract:

**Proposed structured output format (for cloud LLM prompts):**
```json
{
  "files": [
    {
      "path": "src/services/payment.py",
      "language": "python",
      "action": "create",
      "code": "import stripe\n\nclass PaymentService:\n    ..."
    },
    {
      "path": "src/services/order.py",
      "language": "python",
      "action": "edit",
      "code": "# ... full file content ..."
    }
  ]
}
```

**Complexity:** High. This would require changing the cloud LLM prompt format for code generation (affects `drafter.py`, `spec_builder.py`, and all downstream consumers). The 4-layer heuristic has accumulated significant robustness through Kaizen runs. A JSON-first approach would need a dual-format transition period.

**Priority:** Low (for now). The 4-layer heuristic is battle-tested and handles edge cases well. The Keiyaku migration here would be a major refactor of the entire code generation prompt pipeline. Flag for future consideration when the next multi-file extraction failure occurs (Kaizen trigger).

**Requirements to update:** No immediate changes. Add to the Keiyaku candidate boundary list (K-5 in the design principle).

---

### Gap D-1: FunctionChainStrategy Signal Plumbing (D1 in Audit)

**Status:** IMPLEMENTED (`ClassificationResult` in `complexity/models.py`)
**Boundary:** Classifier signals → Decomposer strategy selection
**Requirement Impact:** REQ-MP-9xx (D1 in Capability Audit)

**Current state:** `classify_tier()` returns `(ComplexityTier, str)` — a tier and a reason string. The reason string is human-readable prose ("Score -2: heuristic_score=-2, no external API imports"). The decomposer needs the *signals* (blast_radius, caller_count, has_dynamic_dispatch, etc.) to make strategy decisions, but only receives the tier.

**Keiyaku violation:** The classification signals are a typed `TaskComplexitySignals` dataclass at the classifier, but they are lost at the tier boundary. The decomposer receives only the tier enum, losing the signal detail that would inform strategy selection (e.g., "blast_radius > 3 → FunctionChainStrategy" vs "mro_depth > 1 → ClassDecomposeStrategy").

**Proposed fix:** Thread `TaskComplexitySignals` through to the decomposer alongside the tier:

```python
# Current: classify_tier returns (tier, reason_str)
tier, reason = classify_tier(signals)

# Proposed: signals travel with the tier
@dataclass
class ClassificationResult:
    tier: ComplexityTier
    reason: str
    signals: TaskComplexitySignals
```

This is already a typed boundary — the gap is that the signals are computed, used for classification, then discarded before reaching the decomposer. This is a Mottainai violation (discarding computed data) expressed through a Keiyaku lens (the decomposer can't make informed decisions without the signals).

**Priority:** High. This is the D1 gap in the Capability Audit and blocks FunctionChainStrategy from using blast_radius/caller_count for strategy selection.

**Requirements to update:** REQ-MP-500 — return `ClassificationResult` instead of `(tier, str)`. REQ-MP-901/902 — consume `ClassificationResult.signals` for strategy selection.

---

## Requirements Update Summary

### Existing Requirements Needing Keiyaku Amendments

| Requirement | Current State | Amendment |
|-------------|---------------|-----------|
| **REQ-MP-500** | Returns `(ComplexityTier, str)` | Return `ClassificationResult` dataclass with signals (Gap D-1) |
| **REQ-MP-502** | Escalation as prose injection | Define structured escalation contract JSON schema (Gap A-1) |
| **REQ-MP-503** | Structural verify returns `bool` | Add semantic verification output contract when wiring A2 (Gap A-2) |
| **REQ-MP-512** | Escalation context as "## Prior Local Model Attempt" section | Reference escalation contract from A-1 |
| **REQ-MP-601** | Per-step metrics as flat attributes | Add JSON output contract for repair diagnostics (Gap A-4) |
| **REQ-MP-603** | Experiment result JSON schema defined | Add schema_version field; reference repair contract from A-4 |
| **REQ-MP-901** | ClassDecomposeStrategy deterministic | Add note: LLM-assisted variants must use decomposition contract (Gap A-3) |
| **REQ-MP-902** | FunctionChainStrategy deterministic | Same as REQ-MP-901; consume ClassificationResult.signals |

### New Requirements Proposed

| Requirement | Scope | Description |
|-------------|-------|-------------|
| **REQ-MP-504** | Semantic verification | Keiyaku-compliant JSON output contract for LLM-based verification (verdict, confidence, issues, suggested_fix) |
| **REQ-MP-513** | Escalation | Structured escalation handoff contract (JSON) replacing prose "## Prior Local Model Attempt" injection |
| **REQ-MP-604** | Observability | Repair outcome JSON contract with per-step detail for Kaizen analysis and escalation forwarding |
| **REQ-MP-903** | Decomposer | Keiyaku decomposition output contract for any future LLM-assisted decomposition strategy |
| **REQ-MP-1010** | Cross-cutting | Keiyaku compliance gate: all new LLM-calling boundaries must define JSON input/output contracts before implementation |

---

## Implementation Priority

### Tier 1 — Wire Before Build (Prevent Future Violations)

| Gap | Priority | Status | Rationale |
|-----|----------|--------|-----------|
| **A-2** (Semantic verification contract) | **High** | CONTRACT DEFINED (REQ-MP-504) | Contract defined in `models.py`; wiring pending on A2 activation |
| **D-1** (Signal plumbing) | **High** | IMPLEMENTED | `ClassificationResult` in `complexity/models.py` threads signals to decomposer |
| **REQ-MP-1010** (Compliance gate) | **High** | ACTIVE | Policy requirement — prevents future prose-first implementations |

### Tier 2 — Improve Existing Boundaries

| Gap | Priority | Status | Rationale |
|-----|----------|--------|-----------|
| **A-1** (Escalation contract) | **Medium** | IMPLEMENTED (REQ-MP-513) | `EscalationHandoff` + `to_prompt_section()` in `models.py` |
| **A-4** (Repair diagnostics contract) | **Medium** | IMPLEMENTED (REQ-MP-604) | `EscalationRepairOutcome` + `to_escalation_repair_outcome()` in `repair.py` |
| **A-3** (Decomposition contract) | **Medium** | PLANNED (REQ-MP-903) | No LLM decomposition yet; triggers on first LLM decomposition strategy |

### Tier 3 — Monitor via Kaizen

| Gap | Priority | Status | Rationale |
|-----|----------|--------|-----------|
| **C-1** (Multi-file extraction) | **Low** | Unchanged | Battle-tested heuristic; migrate only if Kaizen runs surface failures |

---

## Relationship to Keiyaku Design Principle

This gap analysis adds micro prime-specific boundaries to the Keiyaku candidate list:

| Keiyaku ID | Boundary | Source |
|------------|----------|--------|
| K-1 | DESIGN → IMPLEMENT handoff | Keiyaku principle (existing) |
| K-2 | IMPLEMENT → INTEGRATE validation | Keiyaku principle (existing) |
| K-3 | REVIEW → FINALIZE report | Keiyaku principle (existing) |
| K-4 | Plan ingestion PARSE → ASSESS | Keiyaku principle (existing) |
| **K-5** | **Multi-file code extraction** | Gap C-1 (this document) |
| **K-6** | **Local → Cloud escalation** | Gap A-1 (this document) |
| **K-7** | **Semantic verification output** | Gap A-2 (this document) |
| **K-8** | **LLM-assisted decomposition** | Gap A-3 (this document) |
| **K-9** | **Repair diagnostics at boundary** | Gap A-4 (this document) |
| **K-10** | **Classification signals threading** | Gap D-1 (this document) |
