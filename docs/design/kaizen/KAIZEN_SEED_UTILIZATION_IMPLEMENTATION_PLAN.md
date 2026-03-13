# Kaizen Seed Utilization — Implementation Plan

> **Version:** 0.1.0
> **Date:** 2026-03-09
> **Source:** [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) Section 11 (run-020 analysis)
> **Scope:** P0–P6 prioritized recommendations from online-boutique run-020

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Implementation Readiness](#2-implementation-readiness)
3. [Phase 1 — Prompt Enrichment (P0, P1, P4)](#3-phase-1--prompt-enrichment-p0-p1-p4)
4. [Phase 2 — Threshold Stabilization (P2)](#4-phase-2--threshold-stabilization-p2)
5. [Phase 3 — Requirements Traceability (P5, P6)](#5-phase-3--requirements-traceability-p5-p6)
6. [Phase 4 — Element Registry Population (P3)](#6-phase-4--element-registry-population-p3)
7. [Verification](#7-verification)
8. [Risk Register](#8-risk-register)

---

## 1. Executive Summary

Run-020 exposed that plan ingestion produces structurally valid but semantically thin seeds: 17/17 tasks have single-line descriptions, 0 code examples, 0 negative scope, and the route margin is exactly 0. The existing kaizen config infrastructure (REQ-KPI-500/502) already supports prompt suffix injection and threshold override — most fixes require **no code changes**, only config and prompt content.

### Implementation Phases

| Phase | Priorities | Nature | Code Changes | Expected Impact |
|-------|-----------|--------|-------------|-----------------|
| 1 | P0, P1, P4 | Kaizen config + TRANSFORM prompt template | 1 file (prompt template) + 1 config file | Quality score 0.787 → ~0.94 |
| 2 | P2 | Kaizen config only | 0 files (config only) | Eliminates route coin-flip |
| 3 | P5, P6 | PARSE + TRANSFORM prompt suffixes | 0 files (config only) | Improved traceability |
| 4 | P3 | Element registry population | Template registry additions | Unlocks skeleton_fill mode |

---

## 2. Implementation Readiness

### Already Built (Leverage Points)

| Component | Location | Status |
|-----------|----------|--------|
| `PlanIngestionKaizenConfig` dataclass | `plan_ingestion_diagnostics.py:71-78` | IMPLEMENTED |
| `load_kaizen_config()` | `plan_ingestion_diagnostics.py:80-99` | IMPLEMENTED |
| `kaizen_config_path` injection in workflow | `plan_ingestion_workflow.py:4547-4562` | IMPLEMENTED |
| PARSE suffix injection | `plan_ingestion_workflow.py:1960-1961` | IMPLEMENTED |
| ASSESS suffix injection | `plan_ingestion_workflow.py:2106-2107` | IMPLEMENTED |
| TRANSFORM suffix injection | `plan_ingestion_workflow.py:2242-2243` | IMPLEMENTED |
| `complexity_threshold_override` | `plan_ingestion_workflow.py:4559-4562` | IMPLEMENTED |
| `run-plan-ingestion.sh --kaizen-config` | cap-dev-pipe | IMPLEMENTED |
| `compute_density_warnings()` | `plan_ingestion_diagnostics.py` | IMPLEMENTED |
| `TaskDensity.has_negative_scope` | `plan_ingestion_diagnostics.py` | IMPLEMENTED |
| Element registry + pre-assembly | `plan_ingestion_workflow.py:1190-1427` | IMPLEMENTED |
| Template registry (9 templates) | `micro_prime/templates.py:549-609` | IMPLEMENTED |

### What's Missing

| Gap | What's Needed |
|-----|---------------|
| Kaizen config file for online-boutique | JSON file with prompt suffixes and threshold override |
| TRANSFORM prompt template lacks depth guidance | `_TRANSFORM_PRIME_PROMPT` says "thorough task_description" but doesn't specify structure |
| No online-boutique-specific templates | Template registry has 9 generic Python templates; none match Go/gRPC/Dockerfile patterns |

---

## 3. Phase 1 — Prompt Enrichment (P0, P1, P4)

**Addresses:** F-2 (shallow descriptions), F-3 (no code examples), F-4 (no negative scope)

### 3.1 Approach: Dual-Track

Two complementary changes:

1. **Modify `_TRANSFORM_PRIME_PROMPT`** — The base template currently says only `"Each task should have a thorough task_description."` This is too vague. Replace with structured guidance that persists across all runs, not just kaizen-configured ones.

2. **Create kaizen config** — A `transform_prompt_suffix` for online-boutique-specific reinforcement. This stacks on top of the improved base prompt.

### 3.2 TRANSFORM Prompt Template Change

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`
**Location:** `_TRANSFORM_PRIME_PROMPT` (lines 378–415)

**Current (line ~413):**
```
Each task should have a thorough task_description.
```

**Proposed replacement:**
```
Each task_description MUST be a multi-line block (5+ lines minimum) containing:
1. **Implementation steps** — numbered steps describing what to build
2. **Key function signatures** — the primary functions/methods with parameters and return types
3. **Code example** — a fenced ```<language> block showing the core API call, constructor, or pattern
4. **Error handling** — what errors to handle and how
5. **Negative scope** — "This task should NOT: ..." listing explicit exclusions

Do NOT produce single-line descriptions. A one-sentence summary is insufficient.
```

**Why modify the base template (not just kaizen suffix):** Single-line descriptions are universally bad for downstream code generation regardless of project. This is a quality floor, not a project-specific preference. The kaizen suffix adds project-specific reinforcement on top.

### 3.3 Kaizen Config File

**File:** `online-boutique-demo/.cap-dev-pipe/kaizen-config.json` (new)

```json
{
  "plan_ingestion_kaizen": {
    "transform_prompt_suffix": "\n\nADDITIONAL REQUIREMENTS FOR THIS PROJECT:\n- This is a Go/gRPC microservices project. Code examples must use Go syntax.\n- Each task_description must include a ```go code block showing the primary function or handler.\n- negative_scope must list at least 2 exclusions per task.\n- Reference the source requirement (REQ-*) in each task_description where applicable.\n- For gRPC services, include the proto service definition and the Go Servicer method signature.\n- For Dockerfiles, include the multi-stage build pattern.\n"
  }
}
```

### 3.4 Verification

Run plan ingestion on the same plan with the kaizen config:

```bash
cd .cap-dev-pipe
./run-plan-ingestion.sh \
  --provenance pipeline-output/online-boutique/run-020-*/run-provenance.json \
  --kaizen-config kaizen-config.json
```

**Success criteria:**
- 0/17 tasks with `description_chars < 500`
- \>50% tasks have `has_code_examples: true`
- \>50% tasks have `has_negative_scope: true`
- `seed_quality_score >= 0.94`

---

## 4. Phase 2 — Threshold Stabilization (P2)

**Addresses:** F-1 (route margin = 0)

### 4.1 Approach

Add `complexity_threshold_override` to the kaizen config. The existing infrastructure applies this at workflow init time (line 4559).

### 4.2 Config Addition

Update `kaizen-config.json`:

```json
{
  "plan_ingestion_kaizen": {
    "transform_prompt_suffix": "...(from Phase 1)...",
    "complexity_threshold_override": 45
  }
}
```

**Why 45, not higher:** The composite score was 40 with dimension spread 27. Raising to 45 gives a margin of 5, which is enough to absorb minor plan variation while keeping the door open for genuinely complex plans to route to artisan. Going higher risks forcing complex plans into prime where they'd fail.

### 4.3 Alternative: Investigate the Dimension Spread

Before committing to a threshold override, examine the ASSESS output to understand the conflicting signals. The dimension spread of 27 means some dimensions score near 0 while others score near 27+. If this reflects a genuine boundary case, the right fix may be splitting the plan rather than overriding the threshold.

**Action:** Read `run-020` ASSESS response (if kaizen capture was active) or re-run with `--kaizen` flag to persist the response.

### 4.4 Verification

- `route_margin >= 5` in diagnostic report
- Route decision is stable across 2+ re-runs on the same plan

---

## 5. Phase 3 — Requirements Traceability (P5, P6)

**Addresses:** F-5 (12/17 missing req refs), F-7 (7/17 missing API signatures)

### 5.1 Approach

Both are addressed via kaizen config prompt suffixes — no code changes.

### 5.2 PARSE Prompt Suffix (P6)

```json
{
  "plan_ingestion_kaizen": {
    "parse_prompt_suffix": "\n\nFor each feature, extract api_signatures aggressively:\n- For Go functions: package.FunctionName(params) returnType\n- For gRPC: ServiceName/MethodName with request/response types\n- For HTTP handlers: METHOD /path → handler function name\nIf the plan text mentions a function, method, or endpoint, it must appear in api_signatures.\n"
  }
}
```

### 5.3 TRANSFORM Prompt Suffix Addition (P5)

Append to the existing `transform_prompt_suffix` from Phase 1:

```
- Every task_description must reference the source requirement using REQ-XXX format.
  If the plan does not use REQ-* identifiers, synthesize them from section headings (e.g., REQ-AUTH-001 for an authentication section).
```

### 5.4 Verification

- `has_requirements_refs: true` for >80% of tasks
- `features_with_signatures` increases from 7/17 to >12/17

---

## 6. Phase 4 — Element Registry Population (P3)

**Addresses:** F-6 (0/38 elements pre-filled, skeleton_fill unavailable)

### 6.1 Context

The template registry (`micro_prime/templates.py:549-609`) has 9 templates, all Python-centric:
- `config_constant`, `app_instance`, `type_alias`, `property_getter`, `property_setter`, `dunder_method`, `typed_constant_default`, `simple_validation`, `dataclass_boilerplate`

None match Go, gRPC, or Dockerfile patterns. This is why run-020 had 38 registry misses and 0 hits.

### 6.2 Constraint: Template Registry is Python-Only

**Discovery during implementation:** The template registry (`micro_prime/templates.py`) validates all rendered output via `ast.parse()` — Python AST parsing. Go, gRPC proto, and Dockerfile code will fail AST validation. The template registry is architecturally Python-only.

This means **Option A (generic Go templates) is not viable** without adding language-aware AST validation, which is a larger effort than justified here.

### 6.3 Viable Approach: Registry Cache Backfill (Option B)

The element registry has a separate *cache hit* path (lines 1288–1318 in `plan_ingestion_workflow.py`) that is language-agnostic. When an element's `context_checksum` matches a cached entry with stored code, it's a registry hit regardless of language. This path does not use `ast.parse()`.

**Approach:** After a successful Prime Contractor run on online-boutique, backfill generated code into the element registry via `element_registry.put()`. Subsequent plan ingestion runs will get cache hits for unchanged elements.

**Prerequisite:** Requires at least one successful generation run to populate the cache. This is a natural byproduct of running Phases 1–3 first (better seeds → better generation → populated cache).

### 6.4 Effort Estimate

Option B (backfill script): Low effort, but deferred until after a successful run.
Language-aware AST validation: Out of scope for this plan — tracked as a future capability.

### 6.4 Verification

- Re-run plan ingestion → `registry_hits > 0` or `template_fills > 0`
- At least one task activates `skeleton_fill` draft mode in Prime Contractor

---

## 7. Verification

### End-to-End Validation

After all phases, run the full pipeline on online-boutique:

```bash
cd .cap-dev-pipe
./run-cap-delivery.sh \
  --plan /path/to/python-plan.md \
  --requirements /path/to/requirements.md \
  --project online-boutique \
  --name run-021 \
  --kaizen-config kaizen-config.json
```

**Compare run-021 diagnostic vs run-020:**

| Metric | run-020 | run-021 Target |
|--------|---------|---------------|
| seed_quality_score | 0.787 | >= 0.94 |
| descriptions < 500 chars | 17/17 | 0/17 |
| has_code_examples | 0/17 | >= 9/17 |
| has_negative_scope | 0/17 | >= 9/17 |
| has_requirements_refs | 5/17 | >= 14/17 |
| route_margin | 0 | >= 5 |
| elements pre-filled | 0/38 | > 0 (Phase 4 only) |

### Regression Check

Run on a different plan (not online-boutique) without kaizen config to verify the base TRANSFORM prompt improvement helps universally without breaking existing behavior.

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Longer TRANSFORM descriptions increase token cost | High | Low | $0.18 → ~$0.25 per run; acceptable for quality gain |
| TRANSFORM LLM ignores structured description guidance | Medium | High | If first run still produces single-line descriptions, escalate to few-shot examples in the prompt |
| Threshold override masks a genuine boundary case | Medium | Medium | Phase 2 alternative: investigate dimension spread before committing to override |
| Go templates in template registry are too generic | Low | Low | Start with Option A (generic), refine with Option B (backfill) after a successful run |
| Longer prompts hit TRANSFORM budget limits | Low | Medium | Check `TOTAL_SPEC_BUDGET_TOKENS` (4096) and `TOTAL_DRAFT_BUDGET_TOKENS` (8192); TRANSFORM prompt budget is separate and currently uncapped |
| Code examples in descriptions are wrong language | Medium | Medium | Kaizen config suffix specifies Go explicitly; base prompt should not mandate language |

---

## Dependency Graph

```
Phase 1 (P0+P1+P4)  ←── no dependencies, highest impact
    ↓
Phase 2 (P2)         ←── independent, but validate after Phase 1 re-run
    ↓                     (Phase 1 may change composite score)
Phase 3 (P5+P6)      ←── independent, low effort
    ↓
Phase 4 (P3)         ←── independent, medium effort, deferred
```

**Recommended execution:** Phase 1 first, then re-run plan ingestion to measure improvement. Phases 2–3 can go in the same kaizen config file. Phase 4 is a separate effort.
