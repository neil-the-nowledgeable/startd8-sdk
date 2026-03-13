# Kaizen Investigation: Run 005 — Online Boutique Demo

**Date:** 2026-03-07
**Run:** `run-005-20260307T1309` (online-boutique-demo)
**Pipeline:** `.cap-dev-pipe/pipeline-output/online-boutique/latest/`
**Command:** `./run-prime-contractor.sh --provenance pipeline-output/online-boutique/latest/run-provenance.json --max-features 4 --kaizen --force-regenerate`
**Features processed:** PI-003, PI-004, PI-005, PI-006 (4 features, `--max-features 4`)
**Prior runs:** PI-001/PI-002 processed in earlier sub-runs (not regenerated)
**Prior analysis:** [KAIZEN_INVESTIGATION_RUN004_ONLINE_BOUTIQUE.md](./KAIZEN_INVESTIGATION_RUN004_ONLINE_BOUTIQUE.md), [KAIZEN_RUN004_SUBRUN5_ANALYSIS.md](./KAIZEN_RUN004_SUBRUN5_ANALYSIS.md)

---

## 1. Executive Summary

Run 005 processes 4 features with `--force-regenerate`, producing **4/4 usable files on disk**. All Python files pass AST validation, no skeleton markers remain, no spurious root-level files. This continues the trend from Run 004 Sub-Run 5: the pipeline is functionally correct for the Online Boutique demo.

However, the Micro Prime escalation rate is **48.6%** (17 of 35 elements escalated), up significantly from 20% in the previous run. The escalation is driven by two factors: (1) moderate-tier gRPC service methods marked `not_decomposable` (10 elements), and (2) complex-tier elements exceeding Micro Prime's ceiling (7 elements). All escalated elements were handled by cloud fallback successfully.

| Metric | Run 004 Sub-Run 5 (6 features) | **Run 005 (4 features)** | Delta |
|---|---|---|---|
| Reported success | 6/6 (100%) | 4/4 (100%) | -- |
| Actual usable files | 6/6 (100%) | **4/4 (100%)** | -- |
| Broken skeletons | 0 | 0 | -- |
| Spurious root files | 0 | 0 | -- |
| Total cost | $1.19 | $0.96 | -$0.23 |
| Cost/feature | $0.198 | **$0.241** | +$0.043 |
| Total elements | 10 | 35 | +25 |
| Escalation rate | 20% | **48.6%** | +28.6pp |
| Ollama net value | 0 files | 0 files | -- |

**Key finding: Prior-run artifact contamination (INV-12).** The element count jumped from 10 to 35 because `SourceReconciler` (SOURCE_RECONCILE stage) AST-parsed the files on disk — which are **output from Run 004 Sub-Run 5's cloud fallback** — and merged their elements into the ForwardManifest. Of the 35 elements, only **11 are plan-derived**; the other **24 were injected from prior-run output**. These AST-derived elements are predominantly class methods that classify as MODERATE/COMPLEX, inflating the escalation rate from ~20% to 48.6%. Since cloud fallback regenerates the entire file anyway, all element-level work on these injected elements is wasted compute.

| File | Plan Elements | AST-Injected (from Run 004) | Total | Inflation |
|---|---|---|---|---|
| `email_server.py` | 8 | 11 | 19 | +137% |
| `recommendation_server.py` | 2 | 11 | 13 | +550% |
| `email_client.py` | 1 | 2 | 3 | +200% |
| **Total** | **11** | **24** | **35** | **+218%** |

---

## 2. Per-Feature Analysis

### 2.1 PI-003: Email Service — gRPC Server ($0.248)

| Metric | Run 004 Sub-Run 5 | Run 005 |
|---|---|---|
| Route | MP (1 fail) -> fallback | MP (8 pass, 11 fail) -> fallback |
| Elements | 4 | **19** |
| File on disk | 333 lines | **348 lines** |
| Cost | $0.219 | $0.248 |
| Review score | 97/100 PASS | 97/100 PASS |

**Element breakdown (19 total):**
- 4 TRIVIAL: All `__init__` methods -> template match (`pass`), 0ms
- 3 SIMPLE (pass): `_disable_dummy`, `dummy_mode`, `logger` — Ollama generated, 1-15s each
- 5 MODERATE (fail): `BaseEmailService` (decomposed, 1ms), `Check`, `SendOrderConfirmation` x2, `Watch`, `start` — all `not_decomposable`, 0ms generation
- 7 COMPLEX (fail): `DummyEmailService`, `EmailService`, `HealthCheck`, `SendOrderConfirmation`, `initStackdriverProfiling`, `send_email` — all `tier_too_high`

**Element inflation from prior-run artifacts (INV-12):** The plan specifies only **8 elements** for this file. The remaining **11 elements** (all `[AST]`-tagged: `SendOrderConfirmation` x3, `__init__` x3, `Check`, `Watch`, `_disable_dummy`, `dummy_mode`, `logger`) were injected by `SourceReconciler` during plan ingestion. SOURCE_RECONCILE AST-parsed the 333-line `email_server.py` on disk — which was **output from Run 004 Sub-Run 5's cloud fallback** — and merged its AST-discovered elements into the ForwardManifest. These prior-run artifacts inflated the element count by 137% and drove the MODERATE/COMPLEX escalation rate up. All escalated elements were handled by cloud fallback, which regenerated the complete 348-line file regardless.

**Repair steps:** `import_completion` applied to `logger` element (1 of 19).

**Requirement score:** 0.42 (`FAIL:low_element_fill_rate`) at the element level — but the cloud fallback file is complete and correct. The postmortem correctly reports `success: true` at the feature level.

### 2.2 PI-004: Email Service — Test Client ($0.111)

| Metric | Run 004 Sub-Run 5 | Run 005 |
|---|---|---|
| Route | MP -> cloud fallback | MP -> cloud fallback |
| Elements | 1 | **3** |
| File on disk | 83 lines | **89 lines** |
| Cost | $0.112 | $0.111 |
| Review score | N/A | **99/100 PASS** |

**Element breakdown (3 total):**
- 1 SIMPLE (pass): `logger` — Ollama generated with `import_completion` repair (757ms)
- 1 SIMPLE (pass): `sample_order` — Ollama generated clean (711ms)
- 1 MODERATE (fail): `send_confirmation_email` — `not_decomposable`, escalated to cloud

PI-004 was the feature that previously generated an SMTP sender instead of a gRPC client (INV-8). Cloud fallback continues to produce the correct gRPC implementation. The Ollama `send_confirmation_email` element would likely still generate the wrong thing (SMTP pattern), but it's moot since the moderate tier triggers escalation.

**New in this run:** Review phase now runs (99/100 PASS) — previously PI-004 had no review artifacts as a `micro_prime_only` feature.

### 2.3 PI-005: Email Service — Jinja2 Template ($0.375)

| Metric | Run 004 Sub-Run 5 | Run 005 |
|---|---|---|
| Route | Cloud only (HTML) | Cloud only (HTML) |
| Elements | 0 | 0 |
| File on disk | 438 lines | **453 lines** |
| Cost | $0.465 | **$0.375** |

HTML template — no Micro Prime elements. Cloud fallback generates the full file. Cost decreased by $0.09 vs previous run. Still the most expensive feature at 39% of total spend.

PI-005 has `has_existing_files: true` and `existing_files` in context keys — the pipeline correctly detects and handles the pre-existing template. Draft went through 2 iterations (draft-1 + draft-2) with 2 review rounds (review-1 at 7KB, review-2 at 6KB).

### 2.4 PI-006: Recommendation Service — gRPC Server ($0.229)

| Metric | Run 004 Sub-Run 5 | Run 005 |
|---|---|---|
| Route | MP -> cloud fallback | MP (8 pass, 5 fail) -> fallback |
| Elements | 1 | **13** |
| File on disk | 256 lines | **232 lines** |
| Cost | $0.187 | $0.229 |
| Review score | N/A | Review ran |

**Element breakdown (13 total):**
- 7 SIMPLE (pass): `ENABLE_TRACING`, `PORT`, `PRODUCT_CATALOG_SERVICE_ADDR`, `channel`, `log`, `product_catalog_stub`, `tracer_provider` — Ollama generated, 1-7s each
- 4 MODERATE (3 fail, 1 pass): `RecommendationService` (pass, 2ms decomposed), `Check`, `ListRecommendations`, `Watch`, `serve` — `not_decomposable`
- 1 COMPLEX (fail): `initStackdriverProfiling` — `tier_too_high`

PI-006 was a former broken skeleton (INV-1). Now produces a complete 232-line gRPC server. Slightly shorter than Run 004 Sub-Run 5 (256 lines) — cosmetic variation from cloud regeneration.

**Element inflation (INV-12):** Plan specifies only **2 elements** (`RecommendationService`, `initStackdriverProfiling`). The remaining 11 were AST-injected from Run 004's 256-line `recommendation_server.py` — a +550% inflation.

**Repair steps:** `import_completion` applied to 3 elements (`channel`, `log`, `tracer_provider`).

**Requirement score:** 0.62 (`PARTIAL`) at element level — **artificially low** due to AST-injected elements in the denominator. Based on plan-derived elements only (2), the fill rate would be ~50% (1 of 2 decomposed). Cloud fallback completes the file regardless.

---

## 3. Micro Prime Analysis

### 3.1 Element Statistics

| Metric | Run 004 Sub-Run 5 | **Run 005** |
|---|---|---|
| Total elements | 10 | **35** |
| Successful (element-level) | 8 | **18** |
| Escalated | 2 | **17** |
| Template hits | 1 | 4 |
| Ollama generations | 7 | **14** |
| Avg generation time | 6,055ms | **950ms** |

### 3.2 Tier Distribution

| Tier | Count | Success | Fail | Notes |
|---|---|---|---|---|
| TRIVIAL | 4 | 4 | 0 | All `__init__` template matches |
| SIMPLE | 12 | 12 | 0 | All Ollama-generated, all pass |
| MODERATE | 12 | 2 | 10 | 2 decomposed (class stubs), 10 `not_decomposable` |
| COMPLEX | 7 | 0 | 7 | All `tier_too_high` — beyond Micro Prime ceiling |

### 3.3 Escalation Reasons

| Reason | Count | Affected Features |
|---|---|---|
| `not_decomposable` | 10 | PI-003 (5), PI-004 (1), PI-006 (4) |
| `tier_too_high` | 7 | PI-003 (6), PI-006 (1) |

The `not_decomposable` elements are predominantly gRPC service methods (`Check`, `Watch`, `SendOrderConfirmation`, `ListRecommendations`, `serve`, `start`). These are moderate-complexity methods that the decomposer cannot break into simpler sub-elements because they contain sequential orchestration logic (setup -> call -> respond).

The `tier_too_high` elements are full class definitions (`EmailService`, `DummyEmailService`, `HealthCheck`) and complex functions (`send_email`, `initStackdriverProfiling`). These correctly exceed the MODERATE ceiling.

### 3.4 Repair Step Distribution

| Step | Count | Notes |
|---|---|---|
| `import_completion` | 5 | Adds missing imports to Ollama-generated elements |

No `over_generation_trim` or `bare_statement_wrap` in this run — a notable improvement. In Run 004, all 7 Ollama generations exhibited the nested-duplicate pattern requiring these repair steps. The absence here suggests either:
1. The SIMPLE-tier elements in this run are simpler (variables/constants vs functions), or
2. The Ollama model has improved for these specific element types

### 3.5 Ollama Net Value Assessment

Of the 14 Ollama-generated elements that passed, **none survived to the final file unchanged** — all 4 files were ultimately written by cloud fallback. The 4 TRIVIAL template hits (`pass` stubs) and 12 SIMPLE Ollama elements are all discarded when the post-assembly gate delegates to cloud.

**Ollama value: zero net contribution to final output for the 3rd consecutive run.**

Local compute overhead: ~13.3s total across 14 generations (avg 950ms, down from 6,055ms — likely because SIMPLE-tier variable/constant elements are faster than function-body elements).

---

## 4. Cross-Run Trend Analysis

### 4.1 Success Rate Progression

| Run | Features | Reported | Actual Usable | Cost | Cost/Usable |
|---|---|---|---|---|---|
| Run 004 Pre-Fix (7 features) | 7 | 7/7 (100%) | 3/7 (43%) | $0.76 | $0.255 |
| Run 004 Post-Fix #1 (6 features) | 6 | 6/6 (100%) | 4/6 (67%) | $0.76 | $0.190 |
| Run 004 Sub-Run 5 (6 features) | 6 | 6/6 (100%) | 6/6 (100%) | $1.19 | $0.198 |
| **Run 005 (4 features)** | 4 | 4/4 (100%) | **4/4 (100%)** | $0.96 | **$0.241** |

### 4.2 Cost Trends

The kaizen-trends.json reports a cost slope of **+$0.857/run** across the 2 runs it analyzed. This is misleading — it's comparing a 1-feature plan-ingestion run ($0.10) with a 4-feature prime run ($0.96). The per-feature cost is the better metric:

| Feature | Run 004 Sub-Run 5 | Run 005 | Delta |
|---|---|---|---|
| PI-003 | $0.219 | $0.248 | +$0.029 |
| PI-004 | $0.112 | $0.111 | -$0.001 |
| PI-005 | $0.465 | $0.375 | **-$0.090** |
| PI-006 | $0.187 | $0.229 | +$0.042 |

PI-005 (HTML template) cost dropped significantly. PI-003 and PI-006 increased slightly — consistent with `--force-regenerate` causing full cloud fallback rather than reusing cached results.

### 4.3 Accumulated Failure Patterns

The kaizen system detected 1 accumulated pattern:

| Pattern | Count | Features | Status |
|---|---|---|---|
| `repeated_escalation` (`not_decomposable`) | 5 occurrences across 3 features | PI-003, PI-004, PI-006 | Unresolved |
| `repeated_escalation` (`tier_too_high`) | 2 occurrences across 2 features | PI-003, PI-006 | Unresolved |

These are **expected escalations** given the nature of gRPC service methods. The moderate decomposer correctly identifies these as non-decomposable orchestration methods. The pattern is structural, not a bug.

---

## 5. Investigation Item Status (Carried from Run 004)

| INV | Priority | Run 004 Status | Run 005 Evidence |
|---|---|---|---|
| INV-1 | Critical | VERIFIED FIXED | Confirmed: 0 broken skeletons, all 4 files complete |
| INV-2 | High | VERIFIED FIXED | N/A (PI-001/PI-002 not in this batch) |
| INV-3 | Medium | VERIFIED FIXED | Confirmed: 0 spurious root-level files |
| INV-4 | High | NOT TESTED | Still not tested (PI-007 not in batch). `--max-features 4` stops at PI-006. |
| INV-5 | High | VERIFIED FIXED | Confirmed: All 4 features have review artifacts, scores align with file quality |
| INV-6 | Critical | VERIFIED FIXED | Confirmed: PI-003 (11 fail), PI-004 (1 fail), PI-006 (5 fail) all escalate to cloud correctly |
| INV-7 | Low | STILL PRESENT | **Possibly improved:** No `over_generation_trim` or `bare_statement_wrap` in repair logs. SIMPLE-tier elements generate cleaner output. |
| INV-8 | Medium | MOOT | Confirmed moot: PI-004 moderate element escalates to cloud, correct gRPC client produced |
| INV-9 | Low | IMPROVED | N/A (PI-001/PI-002 not regenerated) |
| INV-10 | Low | UNKNOWN | **Still present:** Correlation report shows 0 data points. Path construction error persists (doubled directory segments in skipped-run reasons). |
| INV-11 | Low | UNKNOWN | **Still present:** All 6 features have `lead_agent_spec: "unknown"`, `drafter_agent_spec: "unknown"` in kaizen metadata |

---

### INV-12: SOURCE_RECONCILE Contaminates Manifest with Prior-Run Artifacts [HIGH]

**Symptom:** Element count jumped from 10 (Run 004 Sub-Run 5) to 35 (Run 005). Escalation rate rose from 20% to 48.6%. 24 of 35 elements are AST-derived from on-disk files that were **generated by the previous run's cloud fallback**, not from the plan document.

**Root cause:** `SourceReconciler._reconcile_file()` (`forward_manifest_extractor.py:1400`) AST-parses files at `project_root / relpath`. For greenfield features, these files are output from prior pipeline runs, not production source code. SOURCE_RECONCILE's gap-fill logic (`if key not in existing_element_keys`) adds every AST-discovered class/method/variable to the ForwardManifest. The plan originally specified 11 elements; SOURCE_RECONCILE added 24 more.

**Evidence chain:**
1. Run 004 Sub-Run 5 writes `email_server.py` (333 lines) to `src/emailservice/` via cloud fallback
2. Run 005 plan ingestion runs SOURCE_RECONCILE, which reads this file and discovers 11 AST elements not in the plan
3. The enriched manifest has 19 elements for `email_server.py` (8 plan + 11 AST)
4. Element provenance: all 24 extra elements have `source_contract_id` starting with `flcm-ast-` (AST origin), while plan elements lack this prefix

**Impact:**
- 24 unnecessary elements classified and dispatched (13s Ollama compute, all discarded)
- Escalation rate inflated from ~20% to 48.6% (misleading Kaizen metrics)
- `requirement_score` artificially low (0.42 for PI-003, 0.62 for PI-006) because the denominator includes AST-injected elements that Micro Prime can't handle
- Kaizen trend analysis comparing element counts across runs is invalid

**Design tension:** SOURCE_RECONCILE is correct for **edit-mode** features where the file is production code. But for **greenfield features with `--force-regenerate`**, the on-disk files are prior-run output, not ground truth. The reconciler cannot distinguish these cases.

**Proposed fixes:**
1. **Fingerprint guard:** If `--force-regenerate` is set, skip SOURCE_RECONCILE for target files (they'll be regenerated anyway)
2. **Provenance filter:** Tag prior-run-generated files (via `.startd8/` metadata) and exclude them from reconciliation
3. **Staleness check:** Compare file mtime against the seed's creation timestamp — files written after the plan was created are likely pipeline output, not source

**Where to look:**
- `src/startd8/forward_manifest_extractor.py:1400` — `_reconcile_file()` method
- `src/startd8/contractors/prime_contractor.py:1517-1542` — fallback SOURCE_RECONCILE at load time
- Plan ingestion's SOURCE_RECONCILE call site (runs during seed construction)

---

## 6. Kaizen System Health

### 6.1 Correlation Engine: Still Non-Functional

The correlation report (`kaizen-correlation.md`) shows **0 data points** with 3 skipped runs. The skip reasons all show path construction errors:

```
run-005-20260307T1309: prompts dir missing: .../run-005-20260307T1309/plan-ingestion/kaizen-prompts/run-005-20260307T1309
```

The kaizen-prompts directory actually lives at `.../plan-ingestion/kaizen-prompts/standalone/PI-XXX/`, but the correlation engine looks for `.../kaizen-prompts/<run_id>/`. This is INV-10, still unresolved.

**Impact:** No PASS/FAIL group means, no prompt-feature correlations, no data-driven suggestions. The correlation engine is a dead code path until the directory lookup is fixed.

### 6.2 Trend Engine: Functional but Limited

The trend engine (`kaizen-trends.json`) successfully analyzed 2 of 4 runs and correctly identified:
- 100% success rate across both runs
- Cost slope of +$0.857/run (misleading — different feature counts)
- `repeated_escalation` pattern accumulation

### 6.3 Suggestions Engine: Empty

`kaizen-suggestions.json` has 0 suggestions. Expected — 100% success rate means no failures to analyze. The system lacks visibility into sub-feature quality metrics (escalation rate, Ollama net value, element fill rate).

### 6.4 Missing Kaizen Metrics

The following metrics would improve Kaizen's analytical power:

| Metric | Current | Needed |
|---|---|---|
| `post_assembly_escalation_count` | Not tracked | Count of files escalated after element-level pass |
| `ollama_net_value_ratio` | Not tracked | Files where Ollama output survived to final / total |
| `element_fill_rate` | In postmortem only | Should surface in trends for cross-run comparison |
| `repair_step_frequency` | In postmortem only | Cross-run repair step trend (are repairs increasing?) |
| `agent_spec` in metadata | `"unknown"` | Actual model used (for cost/quality correlation) |
| Per-feature cost trend | Aggregate only | Feature-level cost delta across runs |

---

## 7. New Observations (Run 005 Specific)

### OBS-1: Element Count Explosion from Prior-Run Artifact Contamination (INV-12)

The manifest contains 35 elements (vs 10 in Run 004 Sub-Run 5) for the same 4 features. **This is not caused by `--force-regenerate` re-decomposition.** The inflation occurs during plan ingestion's SOURCE_RECONCILE stage, which AST-parses files on disk that were written by Run 004's cloud fallback. Of 35 total elements, only 11 are plan-derived; 24 were injected from prior-run output. See INV-12 for full analysis.

**Implication:** All element-level Kaizen metrics for this run are contaminated. Escalation rate (48.6%), tier distribution, and requirement scores reflect the prior run's code structure, not the plan's intrinsic complexity.

### OBS-2: MODERATE Decomposed Classes (2 Successes)

Two MODERATE elements succeeded without cloud fallback:
- `BaseEmailService` (PI-003): 1.1ms, decomposed into stub
- `RecommendationService` (PI-006): 2.0ms, decomposed into stub

These are class definitions that the decomposer successfully broke into sub-elements. The class shell (with method stubs) was generated deterministically, while the method bodies were handled as separate elements. This is the decomposer working as designed — the moderate strategy successfully handles class-level decomposition.

### OBS-3: No `over_generation_trim` or `bare_statement_wrap` Repairs

In Run 004, all 7 Ollama generations needed these repair steps to handle the nested-duplicate pattern (INV-7). In Run 005, the 14 Ollama generations only needed `import_completion` (5 times). Possible explanations:
1. The SIMPLE-tier elements in this run are predominantly variables/constants (not function bodies), which don't trigger the over-generation pattern
2. The startd8-coder model may have been retrained/updated between runs

To verify: check whether any SIMPLE-tier function/method elements were generated by Ollama in this run. If all Ollama generations were variable declarations, the absence of over-generation is expected (not a model improvement).

### OBS-4: Incremental Prime Results (3 Result Files)

The `plan-ingestion/` directory contains 3 `prime-result-*.json` files:
1. `PI-001-...-PI-017.json` (8.7KB) — PI-001 processed
2. `PI-002-...-PI-017.json` (8.8KB) — PI-002 processed
3. `PI-003-...-PI-017.json` (60KB) — PI-003 through PI-006 processed (the `--max-features 4` batch)

The first two files are from earlier sub-runs (PI-001 and PI-002 were not regenerated by `--force-regenerate` since they completed in prior sub-runs). The third file contains the current run's 4-feature batch.

### OBS-5: PI-005 Draft Iteration

PI-005 (HTML template) is the only feature with 2 draft iterations and 2 review rounds. This matches the `has_existing_files: true` flag — the pipeline's iterative refinement loop runs an additional pass when editing existing content. Cost for PI-005 is proportionally higher but the output quality justifies it (453 lines, complete Jinja2 template).

---

## 8. Actionable Recommendations

### Immediate (High Impact)

1. **Fix INV-12: SOURCE_RECONCILE prior-run contamination** — The highest-impact issue. SOURCE_RECONCILE injects 24 elements from prior-run output into the manifest, inflating escalation rates and wasting Ollama compute. Three options (see INV-12 for details):
   - Skip reconciliation for target files when `--force-regenerate` is set
   - Tag pipeline-generated files and exclude them from reconciliation
   - Staleness check: skip files whose mtime is newer than the plan creation timestamp

2. **Fix INV-10: Kaizen correlation path bug** — The prompts directory lookup uses `kaizen-prompts/<run_id>/` but the actual path is `kaizen-prompts/standalone/<feature_id>/`. This renders the correlation engine non-functional. Fix: update path construction in `prime_postmortem.py`.

3. **Fix INV-11: Populate `agent_spec` in kaizen metadata** — All features show `"unknown"` for both lead and drafter agent specs. Without this, prompt quality cannot be correlated with model choice.

### Medium Term

4. **Add Ollama net value metric** — Track `ollama_files_survived_to_final / total_files` per run. Three consecutive runs at 0% signals that Ollama is pure overhead for this project type.

5. **Add element provenance tracking to Kaizen metrics** — Report `plan_derived_elements` vs `ast_injected_elements` per feature so that cross-run comparisons are not distorted by reconciliation variance.

6. **Add post-assembly escalation count** — Distinguish element-level pass from file-level pass. The current `escalation_rate` (48.6%) is inflated by AST-injected elements.

### Longer Term

7. **Evaluate Ollama skip strategy** — For gRPC server features, Ollama has contributed zero net value across 3 runs. A kaizen-driven skip list (feature types where local generation always fails) would eliminate ~13s overhead per feature and reduce noise in metrics.

8. **Test INV-4 (garbled merge)** — PI-007 has never been tested since the AST merge fix (commit `a89f060`). Include it in the next run (`--max-features 5` or explicit `--features PI-007`).

---

## 9. Cost Summary

| Feature | Ollama Cost | Cloud Fallback | Total | Route |
|---|---|---|---|---|
| PI-003 | $0.00 | $0.248 | $0.248 | MP -> fallback |
| PI-004 | $0.00 | $0.111 | $0.111 | MP -> fallback |
| PI-005 | -- | $0.375 | $0.375 | Cloud only (HTML) |
| PI-006 | $0.00 | $0.229 | $0.229 | MP -> fallback |
| **Total** | **$0.00** | **$0.962** | **$0.962** | |

All cost is cloud fallback. Zero Ollama cost (local compute only). Zero wasted spend — all files are usable.

---

## 10. Conclusions

1. **Pipeline reliability is stable.** 4/4 features produce correct, AST-valid files. All Run 004 investigation fixes (INV-1 through INV-6) remain verified.

2. **SOURCE_RECONCILE prior-run contamination is the top new finding (INV-12).** 24 of 35 elements were AST-injected from Run 004's cloud-fallback output, inflating escalation rate from ~20% to 48.6% and wasting ~13s of Ollama compute. The pipeline still produces correct output (cloud fallback handles everything), but Kaizen metrics are distorted.

3. **Ollama provides zero net value for the 3rd consecutive run.** All final files are cloud-generated. The local compute overhead is not justified for this project type, and is amplified by the AST-injected elements.

4. **The Kaizen correlation engine is non-functional (INV-10).** Three runs of prompt data exist but cannot be analyzed due to a path construction bug.

5. **Review quality has improved.** PI-004 now gets reviewed (99/100) and PI-003 maintains 97/100. No review-score vs actual-quality gaps observed (the INV-5 issue from Run 004).

6. **Cost is stable at ~$0.24/feature** for Python files, ~$0.38 for HTML templates. Total $0.96 for 4 features — no cost outliers beyond the expected HTML template premium.
