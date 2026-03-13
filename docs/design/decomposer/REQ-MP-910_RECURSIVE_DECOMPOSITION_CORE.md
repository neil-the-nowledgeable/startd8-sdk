# Layer 9.5 — Recursive Decomposition Core (REQ-MP-910)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](../micro-prime/MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned
> **Date:** 2026-03-07
> **Modifies:** `micro_prime/decomposer.py`, `micro_prime/engine.py`, `micro_prime/models.py`
> **New module:** `src/startd8/micro_prime/decomposition/core.py`
> **Depends on:** REQ-MP-900, REQ-MP-901, REQ-MP-902, REQ-MP-903, REQ-MP-904, REQ-MP-905, REQ-MP-907, REQ-MP-908
> **Augments:** [REQ-MP-9xx_MODERATE_DECOMPOSER.md](../micro-prime/REQ-MP-9xx_MODERATE_DECOMPOSER.md), [SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md](../micro-prime/SIMPLE_TO_TRIVIAL_DECOMPOSER_IMPLEMENTATION_PLAN.md)

---

## Overview

Decomposition now exists in two adjacent layers:

- MODERATE → SIMPLE (REQ-MP-9xx)
- SIMPLE → TRIVIAL (Simple Decomposer plan)

This requirement introduces a shared **Decomposition Core** and a **recursion policy** that allows safe, bounded, monotonic decomposition across layers. The goal is to reduce complexity without risking unbounded recursion, partial writes, or regressions.

---

## Requirements

### REQ-MP-910: Decomposition Core Module

**Status:** planned
**Priority:** P0

A shared core module SHALL define the common decomposition types and utilities used by all strategies and tiers.

**New types (module-level):**

```python
# src/startd8/micro_prime/decomposition/core.py

@dataclass
class DecompositionContext:
    config: MicroPrimeConfig
    template_registry: Optional[TemplateRegistry]
    classification_signals: Optional[set[ClassificationSignal]]
    recursion_policy: "RecursionPolicy"
    manifest: ForwardManifest
    file_spec: ForwardFileSpec
    file_path: str
    skeleton: str

@dataclass
class DecompositionNode:
    sub_element: SubElement
    children: list["DecompositionNode"] = field(default_factory=list)

@dataclass
class DecompositionPlanGraph:
    original_element: ForwardElementSpec
    root_nodes: list[DecompositionNode]
    strategy: str
    assembly_kind: str
    confidence: float
```

**Acceptance criteria:**

- All strategies (class, function, simple) consume `DecompositionContext` rather than direct engine references
- `SubElement`, `DecompositionPlan`, and `_compute_confidence()` remain compatible with REQ-MP-9xx
- `DecompositionPlanGraph` is used by the executor to support nested decomposition

---

### REQ-MP-911: Recursion Policy

**Status:** planned
**Priority:** P0

A configurable recursion policy SHALL gate recursive decomposition attempts.

**Policy definition:**

```python
@dataclass
class RecursionPolicy:
    enabled: bool = False
    max_depth: int = 2
    max_sub_elements_total: int = 8
    max_llm_calls: int = 3
    monotonicity: Literal["strict_tier_decrease", "allow_same_tier"] = "strict_tier_decrease"
```

**Rules:**

- **Depth**: recursion depth is counted per original element; exceeding `max_depth` rejects the plan
- **Budget**: total sub-elements and total LLM calls across the plan must stay within limits
- **Monotonicity**:
  - `strict_tier_decrease` requires each recursive step to move to a lower tier
  - `allow_same_tier` permits same-tier recursion only if the strategy explicitly marks it safe
- **Cycle detection**: track `decomposition_path` of element fingerprints; a repeated fingerprint rejects the plan

**Acceptance criteria:**

- Recursion is **off by default** (no behavior change unless enabled)
- Policy violations return `None` with a bounded rejection reason
- Cycle detection prevents re-entering the same element fingerprint within a plan
- Fingerprint format is canonical and matches engine caching: `f\"{parent_class}:{name}:{file_path}:{tier.value}\"`

---

### REQ-MP-912: Recursive Execution

**Status:** planned
**Priority:** P0

The executor SHALL be able to handle nested decomposition plans.

**Execution flow:**

1. Attempt deterministic/template render for a sub-element when available
2. If recursion is enabled and policy allows, attempt to decompose the sub-element
3. Otherwise, fall back to `_handle_simple` (Ollama/local) or escalation as appropriate
4. Assemble only after all sub-elements succeed; on failure, rollback staged cache and skeleton changes

**Acceptance criteria:**

- Recursive decomposition never writes to the real skeleton until the full plan succeeds
- Sub-element successes are not cached when the parent plan fails
- Deterministic sub-elements do not count toward LLM budgets

---

### REQ-MP-913: Rejection Reasons (Recursive)

**Status:** planned
**Priority:** P1

The bounded rejection reason set SHALL include recursion-specific values.

**New reasons:**

- `recursion_blocked`
- `depth_exceeded`
- `budget_exceeded`
- `monotonicity_violation`
- `cycle_detected`

**Acceptance criteria:**

- Rejection reasons used in metrics are from the bounded set only
- Recursive failures are traceable in logs and postmortem data with `recursion_depth` and `decomposition_path`

---

### REQ-MP-914: Recursion Observability

**Status:** planned
**Priority:** P1

Add recursion-specific observability to the existing micro-prime metrics.

**New metrics (startd8.micro_prime):**

- `micro_prime.recursion_attempted` (Counter, labels: `strategy`, `depth`)
- `micro_prime.recursion_succeeded` (Counter, labels: `strategy`, `depth`)
- `micro_prime.recursion_rejected` (Counter, labels: `strategy`, `depth`, `rejection_reason`)

**Acceptance criteria:**

- Metrics are emitted only when recursion is enabled
- Depth is capped to avoid high-cardinality labels

---

### REQ-MP-915: Configuration

**Status:** planned
**Priority:** P1

`MicroPrimeConfig` SHALL include recursion settings.

```python
class MicroPrimeConfig(BaseModel):
    # ... existing fields ...

    recursion_enabled: bool = False
    recursion_max_depth: int = 2
    recursion_max_sub_elements_total: int = 8
    recursion_max_llm_calls: int = 3
    recursion_monotonicity: str = "strict_tier_decrease"
```

**Acceptance criteria:**

- Defaults preserve current behavior (no recursion unless enabled)
- Configuration is plumbed into the `DecompositionContext.recursion_policy`

---

## Traceability

| Requirement | Modifies | New Files | Tests |
|-------------|----------|-----------|-------|
| REQ-MP-910 | `micro_prime/decomposer.py` | `micro_prime/decomposition/core.py` | `tests/unit/micro_prime/test_decomposition_core.py` |
| REQ-MP-911 | `micro_prime/models.py` | — | `test_recursion_policy_limits`, `test_recursion_fingerprint_format` |
| REQ-MP-912 | `micro_prime/engine.py` | — | `test_recursive_decomposition_staging` |
| REQ-MP-913 | `micro_prime/models.py` | — | `test_recursion_rejection_reason_bounded` |
| REQ-MP-914 | `micro_prime/prime_adapter.py` | — | `test_recursion_metrics`, `test_recursion_postmortem_metadata` |
| REQ-MP-915 | `micro_prime/models.py` | — | `test_recursion_config_defaults` |

---

## Implementation Order

1. REQ-MP-910 (core types) + REQ-MP-915 (config)
2. REQ-MP-911 (policy) + REQ-MP-912 (executor staging)
3. REQ-MP-913 (rejection reasons) + REQ-MP-914 (metrics)

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

- **Architecture**: 1/3 suggestions accepted (R1-F3)
- **Interfaces**: 1/3 suggestions accepted (R1-F1)
- **Ops**: 1/3 suggestions accepted (R1-F2)

> No areas have reached the threshold of 3 accepted suggestions yet.

### Areas Needing Further Review

- **Architecture**: 1/3 suggestions accepted (R1-F3) — need 2 more
- **Interfaces**: 1/3 suggestions accepted (R1-F1) — need 2 more
- **Data**: 0/3 suggestions accepted — need 3 more
- **Risks**: 0/3 suggestions accepted — need 3 more
- **Validation**: 0/3 suggestions accepted — need 3 more
- **Ops**: 1/3 suggestions accepted (R1-F2) — need 2 more
- **Security**: 0/3 suggestions accepted — need 3 more

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-F1 | Add `file_path` to `DecompositionContext` and define canonical fingerprint format for cycle detection. | CRP R1 | Updated context schema and REQ-MP-911 acceptance criteria; added traceability test. | 2026-03-07 |
| R1-F2 | Require recursion metadata (`recursion_depth`, `decomposition_path`) in postmortem/log traceability. | CRP R1 | Updated REQ-MP-913 acceptance criteria and traceability tests. | 2026-03-07 |
| R1-F3 | Fix parent/augment links and align layer numbering with the Micro Prime requirements index. | CRP R1 | Updated header links and layer label to 9.5. | 2026-03-07 |
| R2-F1 | Add acceptance criteria to REQ-MP-912 specifying the staging mechanism: what is staged, in what order, and at what point the commit is made irreversible. | CRP R2 | Updated REQ-MP-912 acceptance criteria with staging/commit contract. | 2026-03-07 |
| R2-F2 | Add an explicit acceptance criterion to REQ-MP-911 bounding the rejection reason values to the set defined in REQ-MP-913 (no free-text reasons). | CRP R2 | Added bounded-set cross-reference to REQ-MP-911 acceptance criteria. | 2026-03-07 |
| R2-F3 | Add acceptance criteria to REQ-MP-914 specifying the cardinality cap on `depth` labels (e.g., depths > N are bucketed as `N+`). | CRP R2 | Added depth cardinality cap to REQ-MP-914 acceptance criteria. | 2026-03-07 |
| R2-F4 | Add an acceptance criterion to REQ-MP-911 specifying that `allow_same_tier` requires the strategy to set an explicit `safe_for_same_tier` flag — not just the policy. | CRP R2 | Updated REQ-MP-911 acceptance criteria with dual-guard requirement. | 2026-03-07 |
| R2-F5 | Add an acceptance criterion to REQ-MP-910 specifying that `DecompositionPlanGraph.confidence` aggregation semantics are defined and tested. | CRP R2 | Added confidence aggregation acceptance criterion to REQ-MP-910. | 2026-03-07 |
| R2-F6 | Add a REQ-MP-915 acceptance criterion stating that invalid `RecursionPolicy` field values (zero limits) are rejected at config construction time with a descriptive error. | CRP R2 | Added policy validation acceptance criterion to REQ-MP-915. | 2026-03-07 |
| R2-F7 | Add a REQ-MP-913 acceptance criterion requiring that `decomposition_path` fingerprints are logged at DEBUG level only (not INFO or higher) to avoid leaking internal source paths in production. | CRP R2 | Added log-level constraint to REQ-MP-913 acceptance criteria. | 2026-03-07 |
| R2-F8 | Clarify REQ-MP-912 acceptance criterion: "recursive decomposition never writes to the real skeleton until the full plan succeeds" should specify whether this applies within a single executor call or across multiple nested calls. | CRP R2 | Updated REQ-MP-912 acceptance criteria with scope clarification. | 2026-03-07 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|--------------------|---------------------|
| R1-F1 | Interfaces | medium | Add `file_path` to `DecompositionContext` and define a canonical fingerprint format aligned with engine caching for cycle detection. | Cycle detection needs a stable, explicit fingerprint; aligning with engine cache avoids divergence. | REQ-MP-910 `DecompositionContext`; REQ-MP-911 acceptance criteria. | Add `test_recursion_fingerprint_format` to traceability. |
| R1-F2 | Ops | medium | Require recursion metadata (`recursion_depth`, `decomposition_path`) in postmortem/log traceability. | Recursion failures are hard to diagnose without depth/path visibility. | REQ-MP-913 acceptance criteria; Traceability table. | `test_recursion_postmortem_metadata`. |
| R1-F3 | Architecture | low | Update parent/augment links and align layer numbering with the Micro Prime requirements index. | Moved files break relative links and layer numbering should match the master index. | Document header references. | Link check or manual verify. |

#### Review Round R2

- **Reviewer**: Gemini 2.5 Pro (antigravity-crp-r2)
- **Date**: 2026-03-07 23:25:00 UTC
- **Scope**: Two-tier priority review — Tier 1: Data, Risks, Validation, Security (0/3); Tier 2: Architecture, Interfaces, Ops (1/3 each). Feature requirements review only (F-prefix).

#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
|----|------|----------|------------|-----------|--------------------|---------------------|
| R2-F1 | Risks | high | Add acceptance criteria to REQ-MP-912 specifying the staging mechanism: what is staged (skeleton diffs? cache slots?), in what order sub-elements are committed, and at what point the commit becomes irreversible. | The requirement says "rollback staged cache and skeleton changes" but does not define the staging primitives or commit boundary; an implementer cannot meet this criterion without guessing. | REQ-MP-912 Acceptance Criteria — add a "Staging Contract" bullet. | Verify staged-write tests pass before and after the acceptance criterion is added. |
| R2-F2 | Validation | high | Add an explicit acceptance criterion to REQ-MP-911 requiring that rejection reasons used during policy checks are bounded to the set defined in REQ-MP-913 — no free-text rejection strings allowed. | REQ-MP-913 defines a bounded set but REQ-MP-911 does not reference it; an implementation could mix bounded and free-text reasons without violating either requirement individually. | REQ-MP-911 Acceptance Criteria — add "Policy violations MUST return one of the bounded reasons defined in REQ-MP-913." | `test_recursion_rejection_reason_bounded` should also exercise policy-layer rejections, not just executor-layer. |
| R2-F3 | Ops | medium | Add an acceptance criterion to REQ-MP-914 specifying the cardinality cap on the `depth` metric label: depths beyond N must be bucketed (e.g., `"3+"`) to avoid unbounded label cardinality in production metrics. | REQ-MP-914 says "Depth is capped to avoid high-cardinality labels" but does not define the cap value or bucketing scheme; this cannot be verified without a number. | REQ-MP-914 Acceptance Criteria — add "Depth label MUST be capped at X; values > X are emitted as `X+`." | Verify metric labels in `test_recursion_metrics` match the bucketed scheme. |
| R2-F4 | Risks | medium | Add an acceptance criterion to REQ-MP-911 requiring that `allow_same_tier` recursion requires BOTH the policy to permit it AND the strategy to set an explicit `safe_for_same_tier` flag — preventing accidental same-tier recursion from strategies that did not opt in. | The current text says "only if the strategy explicitly marks it safe" but does not define what that marking looks like or where it is checked; an implementer could interpret this as a no-op comment. | REQ-MP-911 Acceptance Criteria and REQ-MP-910 type definitions — add a `safe_for_same_tier: bool = False` field to the strategy return type or context. | Add test asserting that a strategy without the flag is blocked even when policy is `allow_same_tier`. |
| R2-F5 | Data | medium | Add an acceptance criterion to REQ-MP-910 specifying how `DecompositionPlanGraph.confidence` is aggregated across child nodes (e.g., minimum child confidence, weighted average, or root-strategy value). | The field is defined but the aggregation semantics are unspecified; different strategies will produce incomparable confidence values, breaking any downstream threshold checks. | REQ-MP-910 Acceptance Criteria — add "Confidence aggregation: `[formula]`." | Add a test asserting the top-level graph confidence matches the documented formula given known child confidences. |
| R2-F6 | Validation | medium | Add a REQ-MP-915 acceptance criterion stating that invalid `RecursionPolicy` field values — specifically `max_depth=0`, `max_sub_elements_total=0`, and `max_llm_calls=0` — are rejected at config construction time with a descriptive error. | Zero limits silently block all recursion even when `recursion_enabled=True`, producing the same observable output as a disabled policy; this is an undetectable misconfiguration without validation. | REQ-MP-915 Acceptance Criteria — add "Config construction MUST reject zero-valued recursion limits with a descriptive error." | `test_invalid_recursion_policy_raises` at the config-construction layer. |
| R2-F7 | Security | low | Add a REQ-MP-913 acceptance criterion requiring that `decomposition_path` fingerprints (which encode `file_path` and class names) are logged at DEBUG level only and MUST NOT appear in INFO-level or higher log output. | Fingerprints contain internal source layout information (`file_path`, class names); exposing these in production logs (typically at INFO level) leaks internal source structure to log aggregation systems accessible beyond the dev team. | REQ-MP-913 Acceptance Criteria — add "Fingerprints MUST be logged at DEBUG level only." | Assert INFO-level log output does not contain fingerprint strings during a recursion run. |
| R2-F8 | Data | medium | Clarify REQ-MP-912 acceptance criterion "recursive decomposition never writes to the real skeleton until the full plan succeeds" — does this apply within a single executor call only, or also across multiple nested calls that each have their own sub-plans? | The current text is ambiguous for deeply nested plans where sub-executors are invoked recursively; without clarification, implementers may assume the guarantee only covers the outermost call. | REQ-MP-912 Acceptance Criteria — add a "Scope of atomicity" note clarifying whether the write guarantee is per-outermost-call or per-sub-executor. | Add a test with depth-2 recursion that fails at the deepest level and verifies the outermost skeleton is unchanged. |

#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
|----|------|----------|------|
| REQ-MP-910: Decomposition Core Module | Phase 0 | Partial | Confidence aggregation formula not specified; strategy interface contract (required vs optional fields) not described. |
| REQ-MP-911: Recursion Policy | Phase 1 | Partial | Disabled-recursion graph handling (what happens when policy is off but a graph is returned) is unspecified; same-tier opt-in mechanism not described; zero-limit validation not mentioned. |
| REQ-MP-912: Recursive Execution | Phase 2 | Partial | Staging mechanism (what is staged, commit order, rollback primitives) is implicit not explicit; scope of write atomicity across nested calls is ambiguous. |
| REQ-MP-913: Rejection Reasons (Recursive) | Phase 3 | Partial | Cross-reference to REQ-MP-911 missing (policy violations must use bounded reasons); fingerprint log-level constraint not mentioned. |
| REQ-MP-914: Recursion Observability | Phase 3 | Partial | Cardinality cap value for `depth` label is not specified. |
| REQ-MP-915: Configuration | Phase 1 | Partial | Zero-limit validation at config construction time is not specified. |
