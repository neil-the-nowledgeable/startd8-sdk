# Design Principle: Context Propagation in Multi-Phase Workflows

**Status**: Draft — to be refined in dedicated session
**Date**: 2026-02-15
**Origin**: Artisan workflow domain classification failure (PI-006 through PI-013)
**Related**: OTel context propagation, ContextCore tasks-as-spans model

---

## 1. Problem Statement

The Artisan workflow is a 7-phase pipeline (plan → scaffold → design → implement → test → review → finalize) where upstream decisions — particularly **domain classification** — must reach every downstream phase to drive domain-specific behavior (prompt constraints, validators, token budgets, depth tiers).

When the domain preflight enrichment step was missing from the pipeline, **all tasks defaulted to `domain: "unknown"`**, silently disabling:
- Domain-specific prompt constraints (e.g., "use relative imports", "include `__init__.py`")
- Post-generation validators (e.g., `relative_imports_valid`, `deps_available`)
- Environment checks (e.g., verify parent package exists)
- Domain-informed design calibration (depth tiers, section selection)

The system produced output — it didn't fail — but the output lacked the quality benefits that domain-aware processing provides. This is a **silent degradation** pattern: functionally correct, observationally invisible, quality-impacting.

## 2. The CS Concept: Context Propagation

In distributed systems and OpenTelemetry, **context propagation** is the mechanism by which metadata (trace IDs, baggage, sampling decisions) flows across process boundaries so that downstream services can make informed decisions.

The Artisan workflow exhibits the same pattern at the **workflow phase** level:
- Each phase is analogous to a service in a distributed system
- Domain classification, calibration, and enrichment data are analogous to trace context
- Missing propagation causes the same class of problems: downstream phases operate without upstream context

### Formal Definition

> **Workflow Context Propagation**: The reliable transmission of upstream decisions, classifications, and metadata through all phases of a multi-phase workflow, ensuring every downstream consumer receives the context it needs to operate at full capability.

### Related Terms
- **Context injection** — adding context to a carrier (enriching the seed)
- **Context extraction** — reading context from a carrier (loading `_enrichment` from seed)
- **Broken context** — when propagation fails and downstream operates with defaults
- **Silent degradation** — when broken context doesn't cause errors but reduces quality

## 3. Where Context Propagation Occurs in Artisan

### 3.1 Domain Classification → Seed Enrichment

**Source**: `DomainPreflightWorkflow._classify_domain()` (domain_preflight_workflow.py:265-352)
**Carrier**: `_enrichment` dict per task in the seed JSON
**Consumer**: `SeedTask.from_seed_entry()` (context_seed_handlers.py:260-303)

```
DomainPreflightWorkflow                    context_seed_handlers.py
────────────────────                       ────────────────────────
_classify_domain()                         SeedTask.from_seed_entry()
  │                                          │
  ├─ domain (TaskDomain enum)         →      ├─ enrichment.get("domain", "unknown")
  ├─ domain_reasoning (str)           →      ├─ enrichment.get("domain_reasoning", "")
  ├─ prompt_constraints (list)        →      ├─ enrichment.get("prompt_constraints", [])
  ├─ environment_checks (list)        →      ├─ enrichment.get("environment_checks", [])
  └─ post_generation_validators (list)→      └─ enrichment.get("post_generation_validators", [])
```

**Propagation status**: Works when enrichment step runs. Fails silently with defaults when it doesn't.

### 3.2 SeedTask → Design Phase Context

**Source**: `SeedTask` fields
**Consumer**: `DesignPhaseHandler._task_to_feature_context()` (context_seed_handlers.py:792-930)

```python
# Line 821: Domain is CONDITIONALLY added
if task.domain != "unknown":
    additional_context["domain"] = task.domain
```

**Propagation status**: Partial — domain is only propagated when not "unknown". When domain is missing, the design phase receives no domain guidance at all.

### 3.3 SeedTask → Implement Phase Chunks

**Source**: `SeedTask` fields
**Consumer**: `ImplementPhaseHandler._tasks_to_chunks()` (context_seed_handlers.py:~1894)

```python
metadata={
    "domain": task.domain,                          # Stored but not actionable
    "prompt_constraints": prompt_constraints,        # Enhanced with format/init constraints
    "environment_checks": env_checks,
    "post_generation_validators": task.post_generation_validators,
}
```

**Propagation status**: Domain is stored in chunk metadata but NOT used to build additional implement-phase constraints.

### 3.4 Chunk Metadata → Lead Contractor Prompt

**Source**: DevelopmentChunk metadata
**Consumer**: `lead_contractor_workflow.py` spec prompt (lines 830-864)

```python
raw_constraints = context.pop("domain_constraints", None)
# ... formatted into prompt as domain_constraints_str
```

**Propagation status**: Works when `domain_constraints` key exists. The key name mismatch (`prompt_constraints` in chunk vs `domain_constraints` expected by lead contractor) is a propagation gap.

### 3.5 Design Calibration (NOT domain-aware)

**Source**: `plan_ingestion_workflow._derive_design_calibration()` (lines 2332-2395)
**Structure**: `{task_id: {depth_tier, sections, max_output_tokens, implement_max_output_tokens, complexity}}`

**Propagation status**: Domain is NOT included in calibration. Depth tiers, sections, and token budgets are domain-agnostic. This is a **missing propagation point**.

## 4. Identified Propagation Gaps

| # | Gap | Location | Impact | Status |
|---|-----|----------|--------|--------|
| 1 | Enrichment step not always run | run_artisan_workflow.py | All domains default to "unknown" | **FIXED** — auto-enrichment detection added |
| 2 | Domain not in design_calibration | plan_ingestion_workflow.py:2332-2395 | Token budgets and depth tiers ignore domain complexity | Open (WCP-005) |
| 3 | DomainChecklist not wired through ImplementPhaseHandler | context_seed_handlers.py:2365-2375 | DevelopmentPhase.domain_checklist is always None | Open (WCP-006) |
| 4 | Key name mismatch: prompt_constraints vs domain_constraints | chunk metadata → lead_contractor | Resolved-by-design — DomainChecklist path uses domain_constraints consistently | **RESOLVED** — verified WCP-007 |
| 5 | Design insights don't flow back to implement | design → implement boundary | Domain discoveries in design phase are lost | Out of scope (future WCP) |
| 6 | Validator names from enrichment don't match handler expectations | TestPhaseHandler._resolve_validator_command() | All 10 enrichment validators return None (skipped) | Open (WCP-008) |

**Note (2026-02-15 plan session)**: Gap #3 was refined — the issue is not that DomainChecklist lacks capability (it works when used directly), but that `ImplementPhaseHandler.execute()` at line 2370 creates `DevelopmentPhase` without passing `domain_checklist`. Gap #4 was verified as already resolved — the `DomainChecklist` code path at development.py:1903 consistently uses `domain_constraints` as the context key, matching the lead contractor's expected key at lead_contractor_workflow.py:830.

## 5. Fixes Applied (2026-02-15)

### Fix 1: Auto-Enrichment Detection (Quick + Better)
- **Quick**: Ran `DomainPreflightWorkflow` on the seed to produce `artisan-context-seed-enriched.json`
- **Better**: Added auto-detection in `run_artisan_workflow.py` — checks for `_enrichment` key and runs DomainPreflight automatically when missing

### Fix 2: Domain Classification Logging
- Added WARNING-level logs for unclassified domains in `domain_preflight_workflow.py`
- Added INFO-level logs for successful classifications with reasoning
- Pattern: `DOMAIN unclassified: {task_id} ({title}) → unknown. target={file}, labels={labels}, reasoning={reason}`

### Fix 3: Max Token Cap
- Auto-recalibration top tier changed from 65536 → 64000 (lowest common denominator across lead/drafter models)
- `claude-haiku-4-5` max is 64000, not 65536

## 6. Design Principles (Proposed)

### DP-1: Context Propagation as a First-Class Requirement

Every multi-phase workflow MUST treat context propagation as a first-class design requirement, not an implementation detail. Context propagation tasks should be:
- **Identified** during early pipeline stages (plan/design)
- **Specified** as explicit sub-tasks in the work breakdown
- **Implemented** with tracing to verify propagation at each boundary
- **Tested** with assertions that downstream phases received upstream context
- **Queried** via existing dashboards to track propagation health

### DP-2: No Silent Defaults for Critical Context

When a phase requires upstream context (like domain classification), it MUST:
1. Log a WARNING when falling back to defaults
2. Include the default value and what was expected
3. Provide enough detail to diagnose the missing propagation

### DP-3: Trace Context Propagation with OTel Spans

Each context propagation boundary should be instrumented as an OTel span event:
```
span.add_event("context.propagated", attributes={
    "context.field": "domain",
    "context.value": "python-package-module",
    "context.source": "domain_preflight_workflow",
    "context.consumer": "design_phase",
})
```

This enables TraceQL queries like:
```
{ span.context.field = "domain" && span.context.value = "unknown" }
```

### DP-4: Propagation Completeness Validation

At workflow finalization, validate that all expected context fields were propagated:
```python
REQUIRED_CONTEXT = ["domain", "domain_reasoning", "prompt_constraints"]
for field in REQUIRED_CONTEXT:
    if task.get(field) in (None, "", "unknown", []):
        logger.warning("Context field '%s' not propagated for task %s", field, task_id)
```

## 7. Proposed Task Decomposition for Context Propagation Capability

### Epic: Workflow Context Propagation (WCP)

| Task | Type | Description |
|------|------|-------------|
| WCP-001 | Design | Define context propagation contract — which fields must propagate through which phases |
| WCP-002 | Design | Map all propagation boundaries in Artisan workflow (this document, Section 3) |
| WCP-003 | Implement | Instrument propagation boundaries with OTel span events |
| WCP-004 | Implement | Add propagation completeness validation to FINALIZE phase |
| WCP-005 | Implement | Make design_calibration domain-aware (Gap #2) |
| WCP-006 | Implement | Use domain in implement phase constraint building (Gap #3) |
| WCP-007 | Implement | Fix key name mismatch: prompt_constraints → domain_constraints (Gap #4) |
| WCP-008 | Implement | Align validator names between enrichment and TEST phase (Gap #6) |
| WCP-009 | Test | Integration tests for end-to-end context propagation |
| WCP-010 | Integration | Add context propagation panels to existing Grafana dashboards |
| WCP-011 | Query | Define TraceQL/LogQL queries for propagation health monitoring |

### Dashboard Queries (Proposed)

**Propagation completeness rate**:
```logql
sum(count_over_time({job="artisan"} | json | context_field != "" [1h]))
/
sum(count_over_time({job="artisan"} | json | phase="finalize" [1h]))
```

**Tasks with broken context**:
```traceql
{ span.context.field = "domain" && span.context.value = "unknown" }
```

## 8. Relationship to ContextCore Standard

This principle aligns directly with ContextCore's core insight: **tasks share the same structure as distributed trace spans**. Just as OTel requires context propagation (W3C Trace Context, Baggage) for distributed tracing to work, ContextCore workflows require context propagation for domain-aware processing to work.

The Artisan workflow's domain classification failure is isomorphic to a microservice that drops trace context — downstream services still function, but correlation, sampling, and routing decisions are lost.

**ADR Candidate**: Consider formalizing this as ADR-003: "Workflow Context Propagation as OTel Context Propagation" in the contextcore-spec repo.

---

## Appendix: File Reference

| File | Repo | Key Lines | Role |
|------|------|-----------|------|
| `domain_preflight_workflow.py` | startd8-sdk | 265-352 | Domain classification |
| `context_seed_handlers.py` | startd8-sdk | 260-303, 820-829, 1894-1916 | Context extraction and forwarding |
| `plan_ingestion_workflow.py` | startd8-sdk | 2332-2395 | Design calibration (domain-agnostic) |
| `lead_contractor_workflow.py` | startd8-sdk | 830-864 | Prompt construction with constraints |
| `run_artisan_workflow.py` | startd8-sdk | 429-443 | Auto-enrichment detection |
| `artisan-context-seed-enriched.json` | wayfinder | per-task `_enrichment` | Enriched carrier |
