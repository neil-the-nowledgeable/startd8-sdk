# Kaizen Investigation: Run-023 (online-boutique)

**Run ID:** `run-023-20260309T2305`
**Date:** 2026-03-10
**Previous investigation:** [Run-019](KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md)
**Pipeline stage:** Plan Ingestion (pre-contractor)
**Kaizen requirements:** [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md)

---

## 1. Executive Summary

Run-023 is the first plan ingestion run after the G-1 deterministic contract enrichment fix (commits `b0e1689`, `0df514c`). Seed quality is **stable at 0.9485** — the G-1 fix works. But the run reveals a new problem:

1. **REFINE failed silently, wasting $0.355 (40% of total cost).** The arc-review sub-workflow consumed 13,852 output tokens but produced zero accepted suggestions and reported `success: false`.
2. **Enrichment-aware REFINE was not active.** The run predates commit `eba8894` — no enrichment scope, no custom review profile, no plan markdown in context files. REFINE ran with an empty `scope` and generic configuration.
3. **Route margin is still 0.** `composite_score: 40` vs `threshold: 40` — identical to run-020. The plan is unambiguously prime but the scorer doesn't reflect that.
4. **No REFINE kaizen capture.** Prompt/response persistence covers PARSE/ASSESS/TRANSFORM but not REFINE review rounds. Fixed in subsequent commit but unavailable for this run's root cause analysis.

**Net assessment:** The deterministic enrichment (G-1) holds — all 17 tasks above 500 chars, seed quality 0.9485. But REFINE is broken, costing $0.355 per run with zero return. The enrichment-dependent improvements (code examples on 13 tasks, negative scope on all 17, requirements refs on 3 tasks) cannot be delivered until REFINE works.

---

## 2. Run Metrics

| Metric | run-020 | run-023 | Delta | Trend |
|--------|---------|---------|-------|-------|
| Seed quality score | 0.9485 | 0.9485 | 0 | Stable |
| Total cost | $0.504 | $0.889 | +$0.385 (+76%) | Degraded |
| Total time | 348s | 673s | +325s (+93%) | Degraded |
| Features extracted | 17 | 17 | 0 | Stable |
| LLM calls | 3 | 3 | 0 | Stable (REFINE not counted — failed) |
| REFINE cost | $0.00 | $0.355 | +$0.355 | New cost |
| REFINE rounds completed | 0 | 0 | 0 | No improvement |
| REFINE success | — | false | — | **Failure** |

### Cost Breakdown

| Phase | run-020 | run-023 | Delta |
|-------|---------|---------|-------|
| PARSE | $0.181 | $0.205 | +$0.024 (token variance) |
| ASSESS | $0.008 | $0.009 | +$0.001 |
| TRANSFORM | $0.315 | $0.320 | +$0.005 |
| REFINE | $0.000 | $0.355 | +$0.355 (**all waste**) |
| EMIT | $0.000 | $0.000 | $0 |
| **Total** | **$0.504** | **$0.889** | **+$0.385** |

### Cost-per-Quality-Point (Principle P3)

| Run | Cost | Quality | Cost/Quality |
|-----|------|---------|-------------|
| run-020 | $0.504 | 0.9485 | $0.531 |
| run-023 | $0.889 | 0.9485 | $0.937 |

Run-023 is **76% more expensive** for identical quality. The entire increase is the REFINE failure.

---

## 3. Phase-by-Phase Analysis

### 3.1 PARSE — Healthy

| Signal | Value | Assessment |
|--------|-------|------------|
| features_extracted | 17 | Expected for this plan |
| features_with_targets | 17 | 100% — all features have output files |
| features_with_deps | 14 | 82% (up from 13 in run-020) |
| features_with_signatures | 7 | 41% — only gRPC/Flask services |
| multi_file_features | 0 | Clean — no multi-file violations |
| dep_graph_coverage | 1.0 | Complete |
| code_extraction_fallback | false | Clean JSON extraction |
| Cost | $0.205 | Acceptable |

**REQ-KPI-300 compliance:** All signals present and healthy. No regressions.

### 3.2 ASSESS — Borderline Routing Persists

| Signal | Value | Assessment |
|--------|-------|------------|
| composite_score | 40 | Exactly at threshold |
| route_decision | prime | Correct |
| route_margin | 0 | **WARNING** — routes by accident |
| dimension_spread | 22 | Down from 30 in run-020 |

**REQ-KPI-301 compliance:** Signals present. Route margin 0 is below the 10-point warning threshold specified in the requirements. The plan's own reasoning describes the work as "well-specified, reference-anchored... predominantly single-file, low-dependency features" — this should score well below 40, not at 40.

**Recommendation:** Use `complexity_threshold_override: 45` in kaizen config, or investigate why the LLM consistently scores this plan at the boundary.

### 3.3 TRANSFORM — Stable

| Signal | Value | Assessment |
|--------|-------|------------|
| Cost | $0.320 | Stable |
| Time | 250s | Stable |
| Input tokens | 12,274 | Stable |
| Output tokens | 18,884 | Stable |
| code_extraction_fallback | false | Clean |

No quality_signals recorded in diagnostic (expected — TRANSFORM quality is measured via seed quality score and task density in EMIT).

### 3.4 REFINE — Failed, Cost Wasted

| Signal | Value | Assessment |
|--------|-------|------------|
| success | **false** | Failure |
| rounds_completed | 0 | Zero value |
| suggestions_total | 0 | Nothing produced |
| suggestions_accepted | 0 | — |
| acceptance_rate | 0.0 | — |
| cost_usd | $0.355 | **40% of total — all waste** |
| input_tokens | 1,705 | Low — suggests prompt was sent |
| output_tokens | 13,852 | High — LLM generated substantial content |

**Root cause analysis:**

The `review-config.json` reveals what REFINE was configured with:
```json
{
  "scope": "",
  "context_files": ["onboarding-metadata.json"],
  "custom_review_profile": null
}
```

This run predates commit `eba8894` (enrichment-aware REFINE). The REFINE phase ran with:
- **Empty scope** — no direction for the reviewer
- **No plan markdown in context** — reviewer couldn't cross-reference implementation contracts
- **No custom review profile** — used generic architectural review persona
- **No enrichment focus** — reviewer treated the YAML as a design document, not task specifications

The 13,852 output tokens with `success: false` and `rounds_completed: 0` suggests the arc-review sub-workflow's triage/apply pipeline failed to parse or classify the review output. The LLM generated content but it was unusable.

**Missing diagnostic data:** No REFINE prompt/response capture exists for this run. The kaizen-prompts directory contains only `parse_*`, `assess_*`, `transform_*` files. REFINE kaizen capture was added in a subsequent commit — future runs will have `refine_round0_prompt.txt` and `refine_round0_response.txt` for root cause analysis.

### 3.5 EMIT — Clean

| Signal | Value | Assessment |
|--------|-------|------------|
| success | true | Clean |
| cost_usd | $0.00 | Deterministic |
| quality_warnings | `["no project_metadata"]` | Known — criticality/SLO metadata not configured |

---

## 4. Task Density Analysis

| Metric | run-020 | run-023 | Trend |
|--------|---------|---------|-------|
| Min description chars | 743 | 755 | Stable |
| Max description chars | 3,894 | 3,973 | Stable |
| Median description chars | ~1,590 | ~1,582 | Stable |
| Tasks with code examples | 4/17 (24%) | 4/17 (24%) | No improvement |
| Tasks with requirements refs | 14/17 (82%) | 14/17 (82%) | No improvement |
| Tasks with negative scope | 0/17 (0%) | 0/17 (0%) | No improvement |
| Tasks below 500 chars | 0/17 | 0/17 | Stable (G-1 fix holds) |

**What the G-1 fix delivers:** All 17 tasks above the 500-char minimum. Implementation contracts are preserved in task descriptions. This is the floor — deterministic and reliable.

**What REFINE should deliver (but didn't):**
- Code examples for 13 tasks currently without them (PI-001 through PI-013)
- Negative scope for all 17 tasks (currently 0)
- Requirements refs for 3 tasks currently without them (PI-001, PI-002, PI-009)

These enrichments require a working REFINE phase with the enrichment-aware configuration from commit `eba8894`.

### Task Density Distribution

| Tier | Tasks | Task IDs | Description |
|------|-------|----------|-------------|
| Deep (>2000 chars) | 6 | PI-003 to PI-008 | Multi-file features with full implementation contracts |
| Medium (1000–2000 chars) | 7 | PI-009 to PI-013, PI-014 to PI-017* | Services and Dockerfiles |
| Adequate (500–1000 chars) | 4 | PI-001, PI-002, PI-014 to PI-017* | Shared utilities and Dockerfiles with code examples |
| Thin (<500 chars) | 0 | — | None (G-1 fix) |

*PI-014 through PI-017 have code examples (Dockerfiles) which contribute to richness despite lower char counts.

---

## 5. Kaizen Requirements Compliance

### Layer 1: Run Diagnostics (REQ-KPI-1xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-100 | PASS | `plan-ingestion-diagnostic.json` written with all fields |
| REQ-KPI-101 | PASS | All 6 phases have timing/token/cost breakdown |
| REQ-KPI-102 | PASS | File archived in `run-023-20260309T2305/plan-ingestion/` |

### Layer 2: Prompt-Response Pairing (REQ-KPI-2xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-200 | **PARTIAL** | PARSE/ASSESS/TRANSFORM captured; REFINE missing |
| REQ-KPI-201 | **PARTIAL** | Same gap — no REFINE response capture |
| REQ-KPI-202 | PASS | All phases `code_extraction_fallback: false` |

**Gap closed post-run:** REFINE prompt/response capture added in subsequent commit. Next run will have full coverage.

### Layer 3: Output Quality Metrics (REQ-KPI-3xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-300 | PASS | All PARSE signals present and healthy |
| REQ-KPI-301 | PASS with WARNING | `route_margin: 0` below 10-point alert threshold |
| REQ-KPI-302 | PASS | Seed quality 0.9485 (6-component formula) |
| REQ-KPI-303 | PASS | 17 tasks measured, 0 below 500-char threshold |
| REQ-KPI-304 | **DEGRADED** | REFINE failed — 0 rounds, 0 suggestions, $0.355 wasted |

**Gap:** REQ-KPI-304 reports the metrics correctly (the measurement works), but there is no quality warning generated when REFINE fails. The diagnostic should surface `"REFINE failed with $X.XX cost and 0 rounds completed"` as a quality warning.

### Layer 4: Cross-Run Aggregation (REQ-KPI-4xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-400 | AVAILABLE | Trend script exists; this run extends the dataset |
| REQ-KPI-401 | AVAILABLE | Phase-level drill-down supported |
| REQ-KPI-402 | AVAILABLE | Cost trajectory shows +76% regression from REFINE |

### Layer 5: Feedback Loop (REQ-KPI-5xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-500 | PASS | Kaizen config mechanism works; REFINE fields added post-run |
| REQ-KPI-501 | AVAILABLE | `complexity_threshold_override` available for route margin fix |
| REQ-KPI-502 | AVAILABLE | `--kaizen-config` flag accepted by pipeline |

**Post-run improvement:** `PlanIngestionKaizenConfig` now includes `refine_scope_override`, `refine_review_profile`, and `refine_rounds_override` — enabling kaizen tuning of the REFINE phase.

### Layer 6: Pipeline Integration (REQ-KPI-6xx)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-KPI-600 | PASS | `_ingestion_quality` metadata in seed |
| REQ-KPI-601 | PASS | Score 0.9485 > 0.5 threshold — gate passes |

---

## 6. Findings and Recommendations

### F-1: REFINE Failure Is a $0.355/run Cost Leak (Critical)

**Evidence:** `success: false`, 13,852 output tokens consumed, 0 rounds completed, 0 suggestions.

**Root cause:** Run predates enrichment-aware REFINE (commit `eba8894`). REFINE ran with empty scope and no plan context — the arc-review sub-workflow couldn't produce actionable results from an undirected review of a YAML task file.

**Fix:** Already committed (`eba8894`). Next run will have:
- Enrichment scope directing reviewer to add code examples, negative scope, error handling patterns, requirements refs
- Custom review profile (senior software engineer preparing task specs for code generator)
- Plan markdown as context file for cross-referencing
- `enable_apply=True` + `enable_triage=True` for prime route

**Verification:** Run-024 should show `refine.success: true`, `rounds_completed: >= 1`, and improvement in task density metrics (code_examples, negative_scope, requirements_refs).

### F-2: REFINE Failure Not Surfaced as Quality Warning (Medium)

**Evidence:** The `quality_warnings` array contains only `["no project_metadata"]`. The REFINE failure ($0.355, 40% of total cost) is invisible in the warning list.

**Root cause:** `compute_seed_quality()` and `compute_density_warnings()` do not check REFINE phase success or cost-effectiveness. A failed REFINE that consumed significant budget is not flagged.

**Recommendation:** Add a quality warning when REFINE fails with non-zero cost: `"REFINE failed: $0.355 consumed, 0 rounds completed"`. This makes the cost leak visible in the diagnostic without requiring the operator to inspect phase-level details.

### F-3: Route Margin 0 Is Persistent (Low)

**Evidence:** `composite_score: 40` vs `threshold: 40` in both run-020 and run-023. `route_margin: 0` both times.

**Root cause:** The LLM's complexity scoring consistently lands on the threshold for this plan. The `dimension_spread` narrowed (30 → 22) but the composite didn't change — different dimension distributions, same aggregate.

**Options:**
1. `complexity_threshold_override: 45` in kaizen config — adds 5-point margin
2. Add explicit `Route: prime` declaration in plan (G-2 from pipeline Kaizen — deferred)
3. Accept it — the route is correct even at margin 0; cost is $0.009/run

**Recommendation:** Accept for now. The route is always correct for this plan. Revisit if a plan routes incorrectly.

### F-4: No Negative Scope on Any Task (Low — Blocked by F-1)

**Evidence:** `has_negative_scope: false` on all 17 tasks across both run-020 and run-023.

**Root cause:** Negative scope is not present in the plan's `**Implementation contract:**` sections (which the G-1 fix extracts). It exists in the plan's `**Note:**` and `**Dependencies:**` sections, but those are not extracted by the deterministic assembler.

**Options:**
1. Extend `_extract_implementation_contracts()` to also extract `**Note:**` sections as negative scope
2. Let REFINE add negative scope (enrichment scope already directs this)
3. Both — deterministic extraction as floor, REFINE as ceiling

**Recommendation:** Option 2 first — let REFINE handle it once F-1 is fixed. If REFINE consistently misses negative scope, consider option 3.

### F-5: REFINE Kaizen Capture Gap Closed (Informational)

**What changed:** `PlanIngestionKaizenConfig` now includes:
- `refine_scope_override` — replaces hardcoded enrichment scope
- `refine_review_profile` — replaces hardcoded persona/focus/areas
- `refine_rounds_override` — overrides `--review-rounds` CLI arg

REFINE review rounds now persist to `kaizen-prompts/refine_round0_prompt.txt` and `refine_round0_response.txt`.

**Impact:** Future REFINE failures will have full prompt/response capture for root cause analysis. This run's REFINE failure was uninvestigable without this data.

---

## 7. Action Items

| ID | Action | Priority | Status |
|----|--------|----------|--------|
| A-1 | Verify enrichment-aware REFINE works in run-024 | High | PENDING — blocked on next pipeline run |
| A-2 | Add quality warning for REFINE failure with non-zero cost | Medium | PENDING |
| A-3 | Verify REFINE kaizen capture produces files in run-024 | Medium | PENDING — code committed |
| A-4 | Evaluate negative scope extraction from `**Note:**` sections | Low | DEFERRED — wait for REFINE results |
| A-5 | Route margin acceptance — no action unless misrouting occurs | Low | ACCEPTED |

---

## 8. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_CAPABILITY_DELIVERY_PIPELINE.md](../../../cap-dev-pipe/design/KAIZEN_CAPABILITY_DELIVERY_PIPELINE.md) | Pipeline-level Kaizen — G-1 fix validated by this run |
| [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md) | Requirements assessed in Section 5 |
| [KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md](KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Previous investigation (contractor-side) |
| `plan_ingestion_diagnostics.py` | REFINE kaizen config fields added post-run |
| `plan_ingestion_workflow.py` | Enrichment-aware REFINE (commit `eba8894`), REFINE kaizen capture added |
| `run-023-20260309T2305/plan-ingestion/plan-ingestion-diagnostic.json` | Source diagnostic for this analysis |
| `run-023-20260309T2305/plan-ingestion/review-config.json` | REFINE configuration evidence (empty scope) |
