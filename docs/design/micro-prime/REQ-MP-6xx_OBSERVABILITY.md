# Layer 6 — Observability & Metrics (REQ-MP-6xx)

> **Parent:** [MICRO_PRIME_REQUIREMENTS.md](./MICRO_PRIME_REQUIREMENTS.md)
> **Status:** Planned

---

## Overview

Micro-prime introduces new code paths (template matching, local model inference, repair pipeline, escalation) that must be observable for tuning and debugging. This layer defines what metrics are collected, how repair steps are attributed, and how costs are tracked.

## Requirements

### REQ-MP-600: Per-Element Generation Metrics

**Status:** planned
**Priority:** P1

Every element processed by the micro-prime pipeline SHALL produce a metrics record.

**Schema:**

```python
@dataclass
class MicroPrimeElementMetrics:
    # Identity
    element_fqn: str
    file_path: str
    element_kind: str           # ElementKind value

    # Routing
    tier: str                   # TRIVIAL | SIMPLE | MODERATE | COMPLEX
    template_name: Optional[str]  # Template used (TRIVIAL only)

    # Generation
    generation_time_ms: int     # Wall-clock time
    generation_tokens: int      # Input + output tokens (0 for TRIVIAL)
    model: Optional[str]        # "startd8-coder" | "claude-haiku-4-5" | etc.

    # Repair
    repair_steps_applied: list[str]  # Step names that modified code
    repair_recovered: bool      # Was the element recovered from invalid → valid?

    # Validation
    ast_valid_before_repair: bool
    ast_valid_after_repair: bool
    verification_verdict: Optional[str]  # pass | fail | skipped

    # Escalation
    escalated: bool
    escalation_reason: Optional[str]  # syntax_error | verification_fail
```

**Acceptance criteria:**
- Metrics emitted for every element regardless of tier
- Metrics serializable to JSON for experiment result files
- Metrics compatible with the existing `ClassifiedElement` dataclass in the experiment script

---

### REQ-MP-601: Repair Step Attribution

**Status:** planned
**Priority:** P2

Each repair step SHALL report whether it modified the code and what it changed.

**Per-step metrics:**

| Step | Metric Fields |
|------|--------------|
| Fence stripping | `fence_stripped: bool` |
| Over-generation trim | `trimmed: bool`, `nodes_removed: int` |
| Bare statement wrap | `bare_wrapped: bool` (REQ-MP-407) |
| Indentation normalize | `indent_normalized: bool`, `indent_source: str` ("skeleton" or "fallback") |
| Signature reconcile | `signature_reconciled: bool`, `params_changed: int`, `return_type_restored: bool` |
| Import completion | `imports_added: int`, `import_names: list[str]` |

**Aggregate metrics (computed from per-element records):**

| Metric | Value |
|--------|-------|
| `total_elements_repaired` | Count where `repair_recovered == True` |
| `most_effective_step` | Step that recovered the most elements |
| `repair_recovery_rate` | `repaired / (repaired + escalated)` |

**Acceptance criteria:**
- After an experiment run, the user can answer: "How many elements were recovered by each repair step?"
- Step attribution is granular enough to identify which steps to invest in improving

---

### REQ-MP-602: Cost Accounting

**Status:** planned
**Priority:** P1

The pipeline SHALL track and report cost per tier, comparing against an all-cloud baseline.

**Cost model:**

```python
@dataclass
class MicroPrimeCostReport:
    # Baseline: what it would cost if all elements used MODERATE tier
    baseline_all_cloud_usd: float

    # Actual costs by tier
    trivial_count: int          # $0.00
    simple_count: int           # $0.00 cloud
    simple_escalated_count: int # Cost of cloud escalation
    moderate_count: int
    complex_count: int

    # Totals
    actual_cloud_usd: float
    savings_usd: float
    savings_pct: float

    # Local model costs (informational — $0.00 but track compute time)
    local_inference_time_total_s: float
    local_tokens_total: int
```

**Baseline estimation:**
- Per-element MODERATE cost ≈ 500 tokens input + 500 tokens output at Haiku/Sonnet pricing
- This is a rough estimate — the purpose is directional comparison, not exact accounting

**Acceptance criteria:**
- Cost report included in experiment output JSON
- Per-tier breakdown shows element counts and cloud costs
- Savings percentage is computed relative to baseline
- Report is human-readable when printed

---

### REQ-MP-603: Experiment Result Schema

**Status:** planned
**Priority:** P1

Experiment runs SHALL produce a versioned JSON result file.

**Schema:**

```json
{
  "schema_version": "1.0.0",
  "run_id": "uuid",
  "timestamp": "2026-03-01T12:00:00Z",
  "config": {
    "model": "startd8-coder",
    "seed": "online-boutique-demo",
    "temperature": 0.1,
    "num_predict": 512,
    "skeleton_first": true,
    "repair_enabled": true,
    "templates_enabled": true
  },
  "summary": {
    "total_elements": 32,
    "trivial": { "count": 3, "passed": 3 },
    "simple": {
      "count": 10,
      "ast_valid_before_repair": 7,
      "ast_valid_after_repair": 9,
      "repair_recovered": 2,
      "verification_pass": 7,
      "escalated": 3
    },
    "moderate": { "count": 15, "passed": 14 },
    "complex": { "count": 4, "passed": 3 }
  },
  "repair_summary": {
    "fence_stripped": 8,
    "trimmed": 2,
    "bare_wrapped": 3,
    "indent_normalized": 4,
    "signature_reconciled": 1,
    "imports_added": 3,
    "total_recovered": 2
  },
  "cost": {
    "baseline_all_cloud_usd": 1.85,
    "actual_cloud_usd": 1.20,
    "savings_pct": 35.1,
    "local_inference_time_s": 50.2
  },
  "elements": [
    {
      "fqn": "JSONFormatter.format",
      "file": "emailservice/logger.py",
      "tier": "SIMPLE",
      "ast_valid": true,
      "verification": "pass",
      "repair_steps": [],
      "generation_time_ms": 4200,
      "generation_tokens": 79
    }
  ]
}
```

**Acceptance criteria:**
- Schema is versioned via `schema_version` field
- Result files from different runs are comparable programmatically
- `elements` array contains one entry per element with full metrics
- Schema validates with a JSON Schema definition (optional, P2)

---

## Integration with Existing Observability

### Experiment Script

The experiment script (`scripts/experiment_local_model_routing.py`) already tracks per-element metrics via the `ClassifiedElement` dataclass. The new metrics extend this with repair attribution and tier information.

### Artisan Pipeline

In production integration, metrics flow through the existing `GateEmitter` pattern:
- `GateEmitter.from_micro_prime_result()` — new factory method
- Emits `QUALITY_GATE_RESULT` event with micro-prime-specific evidence items
- Compatible with the existing EventBus and ContextCore data flow

### Grafana Dashboards (Future)

Micro-prime metrics are suitable for time-series visualization:
- Repair recovery rate over time (as templates and model tuning improve)
- Cost savings trend across seeds
- Per-step effectiveness (which repair steps provide the most value)

This is deferred until the experiment rounds validate the approach.
