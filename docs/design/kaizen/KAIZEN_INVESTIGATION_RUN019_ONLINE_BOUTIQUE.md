# Kaizen Investigation: Run-019 (online-boutique)

**Run ID:** `run-019-20260309T1756`
**Date:** 2026-03-09
**Previous investigation:** [Run-017](KAIZEN_INVESTIGATION_RUN017_ONLINE_BOUTIQUE.md)
**Features delivered:** PI-002 through PI-006 (5 of 6 expected)

---

## 1. Executive Summary

Run-019 reports **5/5 PASS** at **$0.6612** (−16% vs run-017's $0.7842), but this masks significant quality issues:

1. **PI-001 vanished from postmortem** — kaizen prompts captured, but feature absent from evaluation. Ghost feature.
2. **PI-004 verdict contradiction** — `success: true` + `verdict: FAIL:low_element_fill_rate`. Aggregate score (1.00) masks this.
3. **PI-002 regression** — PASS→PARTIAL, cache miss forced micro-prime re-generation, `getJSONLogger` failed with `ast_failure`.
4. **PI-006 semantic duplication** — `Check()`, `Watch()`, and `ListRecommendations()` all contain identical product-filtering logic. Health check returns product IDs instead of health status.
5. **Systemic `bare_statement_wrap`** — still hitting 2 features (PI-002, PI-004), same pattern as run-017.

**Net assessment:** The aggregate PASS/1.00 score is **unreliable** — it counts 5/5 success despite two features having sub-1.0 verdicts. The cost reduction is real but attributable to PI-006 cache assembly ($0.00) and PI-005 cost decrease ($0.42→$0.30).

---

## 2. Run Structure

| Feature | Name | Cost | Elements | Req Score | Verdict | Route |
|---------|------|------|----------|-----------|---------|-------|
| PI-001 | Shared JSON Logger — emailservice | — | — | — | **MISSING** | Cloud (prompts captured) |
| PI-002 | Shared JSON Logger — recommendationservice | $0.096 | 3 | 0.667 | PARTIAL | Micro-prime + cloud fallback |
| PI-003 | Email Service — gRPC Server | $0.195 | 13 | 0.923 | PASS | Micro-prime + cloud fallback |
| PI-004 | Email Service — gRPC Test Client | $0.070 | 1 | 0.000 | FAIL:low_element_fill_rate | Micro-prime + cloud fallback |
| PI-005 | Email Service — Order Confirmation HTML | $0.300 | 0 | 1.000 | PASS | Cloud (Lead Contractor) |
| PI-006 | Recommendation Service — gRPC Server | $0.000 | 5 | 1.000 | PASS | Element cache assembly |

**Totals:** $0.6612 across 5 evaluated features (PI-001 excluded)

---

## 3. Run-017 → Run-019 Comparison

| Feature | Run-017 | Run-019 | Delta |
|---------|---------|---------|-------|
| PI-001 | PASS ($0.00, cache) | **MISSING from postmortem** | Regression |
| PI-002 | PASS ($0.00, cache, req=1.0) | PARTIAL ($0.10, 3 elems, req=0.67) | **Regression** — cache miss |
| PI-003 | PASS ($0.19, 13 elems, req=0.85) | PASS ($0.20, 13 elems, req=0.92) | **Improvement** — `send_email` now passes |
| PI-004 | PASS ($0.00, cache, req=1.0) | FAIL ($0.07, 1 elem, req=0.00) | **Regression** — cache miss |
| PI-005 | PASS ($0.42, cloud) | PASS ($0.30, cloud) | **Cost improvement** (−29%) |
| PI-006 | PASS ($0.17, 5 elems, req=0.8) | PASS ($0.00, cache, req=1.0) | **Cost improvement** (−100%) |

**Key observation:** PI-001, PI-002, and PI-004 all hit element cache in run-017 but missed in run-019. The cache was invalidated between runs (likely by L2-L6 fixes from run-017 analysis). Features that lost cache coverage degraded — the cache was masking micro-prime generation quality issues.

---

## 4. Detailed Findings

### 4.1 PI-001 Ghost Feature (L1)

PI-001 ("Shared JSON Logger — emailservice") has a complete kaizen prompt directory with full spec/draft/review responses, but is **absent from the postmortem** (only 5 features evaluated, not 6).

- **Kaizen metadata** confirms: `lead_agent_spec: anthropic:claude-sonnet-4-6`, `drafter_agent_spec: anthropic:claude-haiku-4-5-20251001`, timestamp `22:07:53` (earliest feature processed)
- **Generated file** exists: `emailservice/logger.py` (30 lines, AST valid, no stubs)
- **Postmortem feature list** does not contain `PI-001`

**Root cause hypothesis:** PI-001 may have been processed via a path that generates code and captures kaizen prompts but does not register the result with the postmortem evaluator. This could be:
- (a) Element cache assembly that bypasses postmortem registration (run-017 included cache-assembled features, so this is less likely)
- (b) A timing/ordering issue where PI-001's result was dropped during collection
- (c) Feature deduplication logic that merged PI-001 into another feature

**Impact:** Postmortem coverage gap — 1 of 6 features is not evaluated. The aggregate score (1.00) is calculated over 5, not 6 features.

### 4.2 Aggregate Score Masking (L2)

The postmortem reports `aggregate_score: 1.0` and `successful_features: 5` despite:
- PI-002: verdict `PARTIAL`, requirement_score `0.667`
- PI-004: verdict `FAIL:low_element_fill_rate`, requirement_score `0.0`

**Root cause:** The aggregate score uses the `success` boolean (true for all 5), not the per-feature `verdict` or `requirement_score`. This means `success: true` + `verdict: FAIL` is a valid state — the feature "completed" without error, but the output quality failed validation.

**Impact:** Operators monitoring aggregate score alone will miss quality degradation. The score should incorporate per-feature verdicts.

### 4.3 PI-002 Cache Miss Regression (L3)

In run-017, PI-002 hit the element cache ($0.00, 0 elements, PASS). In run-019, it fell through to micro-prime generation:
- `CustomJsonFormatter` (moderate): **PASS** — 2.9s
- `add_fields` (simple): **PASS** — 4.3s
- `getJSONLogger` (simple): **FAIL** (`ast_failure` → `bare_statement_wrap` repair)

The resulting `recommendationservice/logger.py` (73 lines) is significantly richer than `emailservice/logger.py` (30 lines) — includes docstrings, handler duplication guard, explicit format string, Google copyright header. The quality differential between the two "identical spec" logger implementations is notable: the recommendation logger is production-grade while the email logger is minimal.

### 4.4 PI-003 Improvement: `send_email` Now Passes

In run-017, both `send_email` and `start` elements failed with `not_decomposable`. In run-019:
- `send_email`: **PASS** with `signature_reconcile` repair step
- `start`: Still **FAIL** with `not_decomposable` (`generation_error`/`ollama_generation`)

The `start()` function remains the only `not_decomposable` element. It likely requires orchestration logic (server startup, signal handling) that exceeds moderate decomposer capabilities.

**3 NotImplementedError stubs** in `email_server.py` lines 110-124 are **intentional design** — the `EmailService` class is documented as "Live implementation placeholder: raises immediately to prevent silent misuse." The working implementation is `DummyEmailService`. These are not broken skeleton stubs.

### 4.5 PI-004: Element Fill Rate Failure (L4)

PI-004 has only 1 element (`send_confirmation_email`), which failed with `ast_failure` → `bare_statement_wrap`. Despite this, the file on disk (30 lines) is clean, well-structured code that correctly:
- Creates a gRPC channel
- Sends `SendOrderConfirmation` via the stub
- Handles `grpc.RpcError`
- Closes channel in `finally`

**Paradox:** The element failed (`success: false`) but the feature-level `success: true` and the file on disk is correct. The `requirement_score: 0.0` and `verdict: FAIL:low_element_fill_rate` are based on element-level success (0/1), while the cloud fallback produced a correct file that passed review.

**Root cause:** The `requirement_score` calculation uses element success ratio. When the only element fails but cloud fallback produces correct code, the score bottoms out at 0.0 despite the feature actually working.

### 4.6 PI-006 Semantic Duplication (L5)

PI-006's `recommendation_server.py` (52 lines) has `[REPAIRED BY STARTD8: fence_strip, import_completion]` header and contains three methods with **identical implementation**:

```python
def ListRecommendations(self, request, context):  # correct semantics
def Check(self, request, context):                 # should be health check
def Watch(self, request, context):                 # should be streaming health
```

All three filter products, sample randomly, and return product IDs. `Check` and `Watch` should implement gRPC health checking semantics (return `HealthCheckResponse`), not recommendation logic.

**Root cause:** Element-level generation produced each method independently from the same context. The Ollama model copied `ListRecommendations` logic into the health check methods because the element prompt lacked sufficient type-signature context to differentiate health RPC from recommendation RPC.

The `requirement_score: 1.0` reports this as perfect — but it's semantically wrong. The AST is valid and elements "succeeded", so validation passes despite incorrect behavior.

### 4.7 Systemic `bare_statement_wrap` (L6)

`bare_statement_wrap` repair triggered on 2/22 elements (9%), affecting PI-002 (`getJSONLogger`) and PI-004 (`send_confirmation_email`). Both are simple-tier functions.

Run-017 had the same pattern. The root cause is Ollama producing bare statements outside function scope — the REQ-MP-206 complete-function output mode fix was identified in run-017's investigation but may not be deployed yet.

---

## 5. Kaizen Telemetry Analysis

### 5.1 Metrics Summary

| Metric | Value |
|--------|-------|
| Success rate | 100% (based on `success` boolean) |
| Escalation rate | 13.6% (3/22 elements) |
| Element success | 86.4% (19/22) |
| Tier distribution | simple: 13, moderate: 7, trivial: 2 |
| Avg generation time | 3877ms |
| Total cost | $0.6612 |
| Cost per success | $0.1322 |

### 5.2 Correlation Update

With 22 labeled data points (up from 17 in run-017):

| Feature | ρ (Spearman) | Trend |
|---------|-------------|-------|
| draft_word_count | **+0.280** | ↑ strengthening (was +0.157) |
| spec_word_count | −0.241 | ↑ strengthening (was −0.149) |
| total_prompt_words | +0.074 | → stable |
| review_word_count | +0.024 | → stable |
| context_key_count | −0.013 | → negligible |
| target_file_count | +0.000 | → negligible |

**`draft_word_count` is the strongest positive correlate** — features with more detailed drafts succeed more often. The PASS mean (337 words) vs FAIL mean (88 words) gap is widening. This aligns with the assembly gap analysis: minimal drafts (88 words) are typically micro-prime-only features where element assembly losses corrupt the output.

**`spec_word_count` negative correlation** (−0.241) suggests longer specs may actually hurt — potentially because they overwhelm the Ollama model's context window, or because complex features naturally have longer specs AND higher failure rates (confounded variable).

### 5.3 Cross-Run Trends

| Metric | Value |
|--------|-------|
| Success rate slope | −2.75% per run |
| Cost slope | +$0.039 per run |
| Average cost | $0.3323 |
| Improvement verified | No |
| Accumulated pattern | `repeated_escalation` (ast_failure) — first seen run-019 |

The negative success rate slope is driven entirely by run-018's 0% anomaly (likely a launch error — $0.00 cost). Excluding run-018, the success rate has been 100% for 12 consecutive runs.

### 5.4 Missing Suggestion Template

The CLI log shows: `[kaizen] No suggestion template for pattern type 'repeated_escalation' — skipping.`

This means the kaizen engine detected the `repeated_escalation` pattern but has no template to generate an actionable suggestion. The `kaizen-suggestions.json` file is empty (0 suggestions generated).

---

## 6. Assembly Gap Validation

| File | AST Valid | Stubs | Lines | Notes |
|------|-----------|-------|-------|-------|
| emailservice/logger.py | Yes | 0 | 30 | Minimal but correct |
| emailservice/email_server.py | Yes | 3 (intentional) | 296 | EmailService placeholder stubs by design |
| emailservice/email_client.py | Yes | 0 | 30 | Clean despite FAIL verdict |
| emailservice/templates/confirmation.html | N/A | N/A | 365 | HTML template |
| recommendationservice/logger.py | Yes | 0 | 73 | Production-grade quality |
| recommendationservice/recommendation_server.py | Yes | 0 | 52 | Semantic duplication (Check/Watch copy ListRecs) |

**No broken skeletons** in this run. The assembly gap from run-017 (logger file divergence) is not present — both logger files are in `generated/` under the pipeline output directory. The L6 skeleton-based assembly fix from run-017 was not triggered (PI-001 didn't hit cache assembly for postmortem evaluation, PI-006 did hit cache but its `recommendation_server.py` has a `[REPAIRED]` header suggesting it went through repair, not cache assembly).

**Duplicate `generated_files` entries:** PI-002, PI-003, and PI-004 each have the same path listed twice in `generated_files`. This is cosmetic but indicates the path is registered once during micro-prime generation and again during cloud fallback or file write.

---

## 7. Lessons

| ID | Title | Severity | Ichigo Ichie | Actionable Fix |
|----|-------|----------|-------------|----------------|
| L1 | PI-001 ghost feature — kaizen prompts exist but postmortem excludes feature | High | [GENERAL] | Investigate postmortem feature collection; ensure all features with kaizen prompt dirs are evaluated |
| L2 | Aggregate score masks sub-feature verdicts — 1.00 despite PARTIAL + FAIL | High | [GENERAL] | Incorporate `requirement_score` into aggregate calculation; at minimum, flag `verdict != PASS` features |
| L3 | Cache invalidation exposes latent micro-prime quality issues (PI-002, PI-004) | Medium | [GENERAL] | Cache invalidation should trigger quality regression alerts |
| L4 | `requirement_score` bottoms out when single element fails despite cloud-fallback success | Medium | [GENERAL] | Score should account for fallback success; element-level scores should not override feature-level review scores |
| L5 | Semantic duplication in element-level generation — Check/Watch copy ListRecommendations | Medium | [GENERAL] | Element prompts need type signature and semantic role context to differentiate RPC methods |
| L6 | `bare_statement_wrap` remains systemic (9% of elements, 2 features) | Medium | [GENERAL] | Deploy REQ-MP-206 complete-function output mode |
| L7 | Missing suggestion template for `repeated_escalation` pattern type | Low | [GENERAL] | Add template to kaizen suggestion engine |
| L8 | Duplicate paths in `generated_files` array (cosmetic) | Low | [GENERAL] | Deduplicate during path registration |

### Comparison to Run-017 Lessons

| Run-017 Lesson | Status in Run-019 |
|----------------|-------------------|
| L1: Logger divergence (generated/ vs project root paths) | **Fixed** — all paths now in pipeline output `generated/` |
| L2: Response capture gap (missing draft_raw_response) | **Fixed** — PI-001 through PI-005 have full response files |
| L3: Agent spec metadata not in kaizen metadata | **Fixed** — `lead_agent_spec` + `drafter_agent_spec` present in all metadata.json |
| L4: Correlation label mismatch | **Fixed** — correlation engine now has 22 labeled data points (was 17) |
| L5: Moderate tier overreach | **Not tested** — no COMPLEX tier features in this run |
| L6: Skeleton-based assembly | **Deployed** but not exercised — no cache assembly produced a postmortem entry (PI-001 ghost, PI-006's file has repair header) |

---

## 8. Recommendations

### Immediate (before next run)
1. **Investigate PI-001 ghost** — trace why feature was generated + kaizen-captured but excluded from postmortem
2. **Add `repeated_escalation` suggestion template** to kaizen engine (L7)

### Short-term (next 2-3 runs)
3. **Fix aggregate score calculation** to incorporate per-feature `verdict` and `requirement_score` (L2)
4. **Fix `requirement_score` for fallback features** — element failure should not override successful cloud fallback (L4)
5. **Deploy REQ-MP-206** complete-function output mode to eliminate `bare_statement_wrap` (L6)

### Medium-term
6. **Add semantic validation** to element-level generation — type signature comparison between generated method and forward manifest spec (L5)
7. **Cache invalidation alerting** — when cache is invalidated, compare new results to cached baseline (L3)

---

## 9. Plan Ingestion Seed Analysis

### 9.1 Seed Quality Score

| Metric | Value |
|--------|-------|
| `seed_quality_score` | 0.50 |
| `features_extracted` | 6 |
| `multi_file_features` | 0 |
| `route_margin` | 0 |

### 9.2 Seed Warnings

```
field_coverage_warnings:
  - no design_calibration
  - no service_metadata
  - no context_files
  - no project_metadata
  - 6/6 task(s) missing target_files

density_warnings:
  - no tasks have code examples in descriptions
  - 6/6 task(s) missing requirements references
```

### 9.3 Task Density

| Task | Chars | Lines | Code | Req Refs | Neg Scope |
|------|-------|-------|------|----------|-----------|
| PI-001 | 698 | 16 | No | No | No |
| PI-002 | 701 | 15 | No | No | No |
| PI-003 | 1485 | 26 | No | No | No |
| PI-004 | 739 | 13 | No | No | No |
| PI-005 | 1210 | 18 | No | No | No |
| PI-006 | 1127 | 20 | No | No | No |

### 9.4 Analysis

**Seed quality score: 0.50** — correctly penalizing:
1. **Missing target_files (6/6)** — Tasks have no file path guidance, forcing micro-prime to guess output paths
2. **No code examples** — Descriptions are prose-only, with no code snippets to anchor generation
3. **No requirements references** — No traceability to requirements documents
4. **No negative scope** — No explicit exclusions to prevent scope creep

**What the score does NOT capture:**
- Description *quality* is adequate (all above 500 chars) — the G-1 contract enrichment fix is working
- But descriptions lack *structural richness* that improves generation quality

**REFINE was expected to close this gap** by adding code examples, requirement references, and negative scope through architectural review. But REFINE operates at the document level, not the task level (see §10).

---

## 10. REFINE Phase Investigation

### 10.1 Finding: REFINE Is Not Broken

REFINE is working as designed. The Mottainai Rule 6 chain is INTACT — accepted suggestions flow from REFINE → `onboarding.refine_suggestions` → DESIGN phase prompt as advisory guidance.

### 10.2 Root Cause: Architectural Gap

REFINE operates at the **document level**, producing architectural review suggestions. These are forwarded as advisory text for the downstream DESIGN phase LLM prompt. They **never modify** the seed's per-task fields:
- `config.task_description` — set during PARSE/TRANSFORM, never updated afterward
- `config.context.negative_scope` — not populated (despite `ParsedFeature.negative_scope` being extracted during PARSE and then dropped in `_derive_tasks_from_features()`)
- `config.context.target_files` — empty when PARSE doesn't extract explicit file paths from the plan

**Data flow confirmed:**
```
REFINE → triage.decisions (ACCEPT/REJECT)
       → _extract_refine_suggestions_for_seed() → ACCEPT only
       → seed.onboarding.refine_suggestions
       → DESIGN phase prompt: "**Review suggestions:** ..."
                               ↑ Advisory text — never modifies task fields
```

**Missing step:** No mechanism exists between REFINE and EMIT to enrich individual task descriptions with code examples, requirement references, or negative scope.

### 10.3 Expected vs Actual REFINE Impact

| Signal | Pre-REFINE | Expected Post-REFINE | Actual Post-REFINE |
|--------|-----------|---------------------|-------------------|
| Code examples | 0/6 | 3-4/6 | 0/6 |
| Req references | 0/6 | 4-5/6 | 0/6 |
| Negative scope | 0/6 | 3-4/6 | 0/6 |
| Seed quality score | 0.50 | 0.70-0.80 | 0.50 |

### 10.4 Resolution: Task Density Enrichment

Requirements written: [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](../plan-ingestion/TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md)

Two complementary options:
- **Option A (deterministic, always runs):** Forward `negative_scope` from ParsedFeature, extract `REQ-*` refs from plan text, infer `target_files` via 3-tier fallback, generate API signature stubs, map REFINE suggestions to tasks
- **Option B (LLM-assisted, opt-in):** Single batch LLM call to generate rich task descriptions with code examples and structured context for tasks that Option A couldn't fully enrich
