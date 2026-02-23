# Context Propagation — Dedicated Session Brief

**Purpose**: Comprehensive session notes for the upcoming dedicated session on building context propagation as a first-class capability in ContextCore and the Artisan workflow.

**Date**: 2026-02-15
**Status**: Ready for dedicated session

---

## 1. What Happened

During PI-006 through PI-013 execution on the Artisan workflow, we discovered that **domain classification** — a critical upstream decision — was not propagating to downstream phases. The root cause was a missing enrichment step: `DomainPreflightWorkflow` was never run on the seed before the artisan workflow consumed it.

### Timeline

| Time | Event |
|------|-------|
| PI-006 through PI-011 | All showed `Domains: {'unknown': 1}` — went unnoticed initially |
| Investigation | Found `_enrichment` key absent from all tasks in the seed |
| Quick fix | Ran DomainPreflightWorkflow manually → 11 python-package-module, 4 python-test, 7 non-python, 1 unknown |
| Better fix | Added auto-enrichment detection to `run_artisan_workflow.py` |
| Logging fix | Added WARNING/INFO logs for domain classification decisions |
| PI-012 | First run with enriched seed — domain properly propagated |
| PI-013 (first attempt) | Auto-recalibration set 65536 tokens → exceeded haiku's 64K max → 3x failure |
| PI-013 (fix) | Capped top recalibration tier at 64000 → re-running |

### Impact Assessment

- **12 tasks affected** (PI-001 through PI-012) ran without domain-specific constraints
- **Cost**: ~$15-20 in LLM spend on those tasks produced code without domain-optimized prompts
- **Quality**: Code generated without constraints like "use relative imports for intra-package", "include `__init__.py`", "verify parent package exists"
- **Observable**: Zero errors in logs — purely silent degradation

## 2. The Vision

The user wants context propagation to be a **core design responsibility** in ContextCore, not just a bug fix. Specifically:

### 2.1 Early Pipeline Identification

> "I want to be able to leverage the contextcore early pipeline stages to identify where context propagation will take place and account for its proper implementation as a core requirement."

This means:
- During PLAN phase, identify all context propagation boundaries
- During DESIGN phase, document what context flows where
- Make propagation boundaries explicit in the design doc

### 2.2 Task Decomposition

> "I also want the task of successfully building this context propagation capability into the plan as its own separate task and/or sub-task."

This means:
- Context propagation is a **design responsibility** (identify boundaries)
- Context propagation is a **construction task** (implement injection/extraction)
- Context propagation is an **integration task** (verify end-to-end flow)
- Context propagation is a **test task** (assert all fields reach all consumers)
- Context propagation is a **query task** (dashboards to monitor propagation health)

### 2.3 OTel-Native Tracing

> "The artisan workflow itself needs to be threaded with tracing to ensure proper context propagation is baked into the design and is completely traceable as per OTel and ContextCore standards."

This means:
- Span events at each propagation boundary
- TraceQL queries for propagation health
- LogQL queries for broken context detection
- Dashboard panels for propagation completeness metrics

## 3. Current State of Context Propagation in Artisan

### Where It Works (5 points)

1. **Enrichment → SeedTask**: `_enrichment` dict → `SeedTask.from_seed_entry()` (context_seed_handlers.py:260-303)
2. **SeedTask → Design additional_context**: `task.domain` → `additional_context["domain"]` (context_seed_handlers.py:821)
3. **SeedTask → DevelopmentChunk metadata**: `task.domain` → `metadata["domain"]` (context_seed_handlers.py:~1896)
4. **DomainChecklist → development.py context**: `enrichment.domain` → `context["domain"]` (development.py:1903)
5. **Context → Lead Contractor prompt**: `domain_constraints` → prompt template (lead_contractor_workflow.py:830-864)

### Where It Breaks (6 gaps)

| # | Gap | File | Impact |
|---|-----|------|--------|
| 1 | Enrichment step not always run | run_artisan_workflow.py | All domains default "unknown" |
| 2 | Domain not in design_calibration | plan_ingestion_workflow.py:2332-2395 | Token budgets ignore domain complexity |
| 3 | Domain stored but unused in implement constraints | context_seed_handlers.py | Implement phase doesn't leverage domain |
| 4 | Key mismatch: prompt_constraints vs domain_constraints | chunk metadata → lead_contractor | Constraints may not reach LLM prompt |
| 5 | Design insights don't flow back to implement | design → implement boundary | Domain discoveries in design are lost |
| 6 | Validator names mismatch between enrichment and TEST | TEST phase | Validators show as "unknown" |

### The Enrichment Data Structure

Per task in `_enrichment`:
```json
{
  "domain": "python-package-module",
  "domain_reasoning": "Python file in package directory with __init__.py",
  "prompt_constraints": [
    "Use relative imports for intra-package modules",
    "Include __init__.py exports",
    "Follow existing package naming conventions"
  ],
  "environment_checks": [
    "parent_package_exists",
    "python_version_compatible"
  ],
  "post_generation_validators": [
    "relative_imports_valid",
    "deps_available",
    "no_circular_imports",
    "no_markdown_fences",
    "merge_damage"
  ],
  "available_siblings": ["__init__.py", "tracker.py", "logger.py"]
}
```

### Domain Enum Values

From `domain_preflight_models.py`:
- `python-single-module` — standalone .py file
- `python-package-module` — .py file in a package with `__init__.py`
- `python-test` — test file (test_ prefix or tests/ directory)
- `config-toml` — TOML configuration file
- `config-yaml` — YAML configuration file
- `config-json` — JSON configuration file
- `non-python` — Markdown, shell scripts, Jinja templates, etc.
- `unknown` — classification failed

## 4. Proposed Epic: Workflow Context Propagation (WCP)

### Phase 1: Design & Identification
| Task | Description |
|------|-------------|
| WCP-001 | Define context propagation contract — which fields must propagate through which phases |
| WCP-002 | Map all propagation boundaries in Artisan workflow (extend Section 3 of design-principles/context-propagation.md) |

### Phase 2: Implementation
| Task | Description |
|------|-------------|
| WCP-003 | Instrument propagation boundaries with OTel span events (`context.propagated`, `context.defaulted`) |
| WCP-004 | Add propagation completeness validation to FINALIZE phase |
| WCP-005 | Make `design_calibration` domain-aware (depth tiers, sections, token budgets per domain) |
| WCP-006 | Use domain in implement phase constraint building (build constraints from domain, not just pass-through) |
| WCP-007 | Fix key name mismatch: `prompt_constraints` → `domain_constraints` alignment |
| WCP-008 | Align validator names between enrichment and TEST phase handler |

### Phase 3: Testing & Integration
| Task | Description |
|------|-------------|
| WCP-009 | Integration tests: assert all expected context fields reach all consumers in a mock workflow run |
| WCP-010 | Add context propagation panels to beaver-lead-contractor-progress dashboard (or new dashboard) |
| WCP-011 | Define TraceQL/LogQL queries for propagation health monitoring |

### Proposed OTel Instrumentation

```python
# At each propagation boundary:
span.add_event("context.propagated", attributes={
    "context.field": "domain",
    "context.value": domain_value,
    "context.source_phase": "domain_preflight",
    "context.target_phase": "design",
    "context.task_id": task_id,
})

# When falling back to default:
span.add_event("context.defaulted", attributes={
    "context.field": "domain",
    "context.default_value": "unknown",
    "context.expected_source": "domain_preflight._enrichment",
    "context.task_id": task_id,
})
```

### Proposed Queries

**Propagation completeness (LogQL)**:
```logql
# Count tasks with broken context per phase
sum by (phase) (
  count_over_time({job="artisan"} | json | context_field="domain" | context_value="unknown" [1h])
)
```

**Propagation health (TraceQL)**:
```traceql
# Find all tasks where domain defaulted to unknown
{ span.context.field = "domain" && span.context.default_value = "unknown" }
```

**End-to-end propagation (TraceQL)**:
```traceql
# Verify domain propagated from preflight through finalize
{ name = "context.propagated" && span.context.field = "domain" } | count() > 4
```

## 5. Relationship to ContextCore

This is not just an Artisan bug fix — it's a **design principle of ContextCore itself**:

> ContextCore models tasks as OTel spans. OTel requires context propagation for distributed tracing to work. ContextCore workflows require context propagation for domain-aware processing to work. **They are the same problem at different scales.**

### ADR Candidate

**ADR-003: Workflow Context Propagation as OTel Context Propagation**

> Every multi-phase workflow in the ContextCore ecosystem MUST treat context propagation as a first-class design requirement. Context fields (domain, calibration, constraints) MUST be explicitly injected, carried, and extracted at phase boundaries — mirroring the W3C Trace Context specification's inject/extract model.

## 6. Files to Reference in Dedicated Session

| File | Repo | Purpose |
|------|------|---------|
| `docs/design-principles/context-propagation.md` | wayfinder | Design principle document (this session) |
| `docs/design-principles/context-propagation-session-brief.md` | wayfinder | This brief |
| `lessons/09-agent-infrastructure.md` #27 | Lessons Learned | Lesson learned entry |
| `context_seed_handlers.py` | startd8-sdk | Primary propagation consumer |
| `domain_preflight_workflow.py` | startd8-sdk | Domain classification source |
| `plan_ingestion_workflow.py` | startd8-sdk | Calibration (domain-agnostic) |
| `lead_contractor_workflow.py` | startd8-sdk | Prompt construction with constraints |
| `run_artisan_workflow.py` | startd8-sdk | Auto-enrichment entry point |
| `artisan-context-seed-enriched.json` | wayfinder | Enriched seed example |

## 7. Fixes Already Applied

1. **Auto-enrichment detection** in `run_artisan_workflow.py` — checks for `_enrichment`, runs DomainPreflight when missing
2. **Domain classification logging** in `domain_preflight_workflow.py` — WARNING for unclassified, INFO for classified with reasoning
3. **Max token cap** in `context_seed_handlers.py` — top tier 65536 → 64000 (haiku's actual max)
4. **Warning text accuracy** in `context_seed_handlers.py` — "Token budget will be auto-recalibrated" instead of "may be truncated"
