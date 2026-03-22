# Prime Pipeline Unified Execution Plan

**Version:** 1.0.0
**Created:** 2026-03-22
**Findings:** `PRIME_PIPELINE_AUDIT_FINDINGS.md`
**Requirements:** `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md` v2.0 + `MOTTAINAI_SIGNAL_RECOVERY_REQUIREMENTS.md` v1.0
**Total Scope:** 36 requirements, ~760 lines production, ~510 lines test, 60 tests

---

## Execution Philosophy

1. **Signal preservation before signal consumption.** Persist the data before building features that consume it.
2. **Zero-risk changes first.** Metadata additions can't break anything — ship them to build confidence.
3. **Verify review quality before wiring behavioral changes.** Log-only review in Phase 2 proves the review is useful before Phase 3 trusts it for gating.
4. **Each phase is independently shippable.** No phase requires a subsequent phase to deliver value.

---

## Phase Overview

| Phase | Name | Reqs | Prod Lines | Tests | Risk | LLM Cost | Verify With |
|-------|------|------|------------|-------|------|----------|-------------|
| **1** | Signal Preservation | 12 | ~160 | 22 | None | 0 | Unit tests + postmortem enrichment |
| **2** | Review Step (Log-Only) | 3 | ~130 | 8 | Low | +1 call/feat | Single-feature run |
| **3** | Quality Gate + Feedback | 7 | ~200 | 15 | Medium | +1 call/gate | Multi-feature run |
| **4** | Upstream Amplification | 5 | ~150 | 7 | Low | 0 | Full pipeline run |
| **5** | Calibration & Observability | 5 | ~120 | 8 | Low | 0 | Dashboard review |

---

## Phase 1: Signal Preservation (Zero Risk, Zero LLM Cost)

**Goal:** Stop discarding computed signals. Every fix is an additive metadata key — no behavioral change, no API calls, no return type changes (except budget.py).

**Ship criterion:** All existing tests still pass. Postmortem can access new metadata keys.

### Step 1.1: Integration Engine Metadata (7 changes, 1 file)

**File:** `src/startd8/contractors/integration_engine.py`

All changes follow the same pattern: after the existing `logger.warning()` or `logger.info()`, add a dict to `result_obj.metadata`.

| Change | Req | Location | Metadata Key | Format |
|--------|-----|----------|-------------|--------|
| Disk compliance | RFL-100 | `_run_semantic_checks()` | `disk_compliance` | `{rel_path: {ast_valid, stubs, imports, compliance, issues[]}}` |
| Repair summary | RFL-105 | `_attempt_pre_merge_repair()`, `_attempt_repair()` | `repair_summaries` | `[{phase, total, steps[], modified}]` |
| Merge conflicts | MSR-100 | post-merge (~2474) | `merge_conflicts` | `[{file, type, detail}]` |
| Checkpoint details | MSR-120 | post-checkpoint (~2554) | `checkpoint_details` | `[{check_name, passed, message, diagnostics[]}]` |
| Contract violations | MSR-220 | `validate_against_manifest()` (~1805) | `contract_violations` | `[{expected, actual, severity, repaired}]` (cap 20) |
| Skipped files | MSR-300 | skip accumulation (~2425) | `skipped_files` | `[{file, reason}]` (already on IntegrationResult, persist to history) |
| Language warnings | MSR-330 | language cleanup (~2528) | `language_warnings` | `[{language, category, message}]` |

**Pre-merge repair asymmetry fix (MSR-350):** In `_attempt_pre_merge_repair()`, populate same metadata structure as post-merge.

**Element registry export (MSR-310):** At end of `integrate()`, export summary:
```python
result_obj.metadata["element_repair_summary"] = {
    "total_elements": N, "repaired": M, "repair_by_type": {...}
}
```

**Implementation detail:** `_run_semantic_checks()` returns None (void). Store compliance results on the unit via `unit._compliance_results = {}` then copy to `result_obj.metadata` in `integrate()`.

### Step 1.2: Extract compute_disk_quality_score() (RFL-110)

**From:** `src/startd8/contractors/prime_postmortem.py`
**To:** `src/startd8/forward_manifest_validator.py`

1. Copy pure function to `forward_manifest_validator.py` after `DiskComplianceResult` class.
2. In `prime_postmortem.py`: `from startd8.forward_manifest_validator import compute_disk_quality_score`
3. No behavior change. Both import paths work.

### Step 1.3: Compute Disk Quality Score at Integration Time (RFL-115)

**File:** `src/startd8/contractors/integration_engine.py`

After Step 1.1's compliance storage:
```python
if "disk_compliance" in result_obj.metadata:
    from types import SimpleNamespace
    from startd8.forward_manifest_validator import compute_disk_quality_score
    scores = [compute_disk_quality_score(SimpleNamespace(**d))
              for d in result_obj.metadata["disk_compliance"].values()]
    if scores:
        result_obj.metadata["disk_quality_score"] = min(scores)
```

### Step 1.4: Repair Effectiveness API (RFL-128)

**File:** `src/startd8/repair/orchestrator.py`

```python
def get_step_effectiveness_summary() -> dict[str, dict]:
    return {
        name: {"attempts": e.attempts,
               "success_rate": e.modifications / max(e.attempts, 1),
               "contributed_to_success": e.contributed_to_success}
        for name, e in _step_effectiveness.items()
    }
```

### Step 1.5: Budget Decision Tracking (MSR-110)

**File:** `src/startd8/implementation_engine/budget.py`

Change `enforce_prompt_budget()` return from `str` to `tuple[str, dict]`:
```python
def enforce_prompt_budget(prompt, budget_tokens, sections) -> tuple[str, dict]:
    decision = {"tokens_before": ..., "sections_dropped": [], "sections_truncated": []}
    # ... existing logic, append to decision lists ...
    decision["tokens_after"] = ...
    return result_prompt, decision
```

**Call site updates** (2–3 locations in spec_builder.py and drafter.py):
```python
# Before: prompt = enforce_prompt_budget(...)
# After:  prompt, budget_decision = enforce_prompt_budget(...)
#         context["_budget_decision"] = budget_decision
```

### Step 1.6: Context Resolution Field Skips (MSR-200)

**File:** `src/startd8/contractors/context_resolution.py`

After sanitization skip:
```python
resolution_metadata.setdefault("skipped_fields", []).append(
    {"field": field_name, "reason": reason}
)
```

Return metadata alongside context via `resolved["_resolution_metadata"] = resolution_metadata`.

### Step 1.7: Seed Metadata Preservation (MSR-210)

**File:** `src/startd8/contractors/queue.py`

In `add_features_from_seed()`, after existing field mapping:
```python
seed_meta = {}
for f in ("priority", "effort_estimate", "acceptance_criteria", "labels", "created_at"):
    val = getattr(task, f, None)
    if val is not None:
        seed_meta[f] = val
if seed_meta:
    feature.metadata["seed_metadata"] = seed_meta
```

### Step 1.8: Domain Validation Persistence (MSR-340)

**File:** `src/startd8/contractors/prime_contractor.py`

After domain validation:
```python
if domain_issues:
    feature.metadata["domain_validation"] = {
        "passed": len(domain_issues) == 0,
        "issues": [str(i)[:200] for i in domain_issues[:10]],
        "domain": feature.metadata.get("domain", "general"),
    }
```

### Step 1.9: Tests

**New file:** `tests/unit/contractors/test_signal_preservation.py`

```
# Integration engine metadata (Steps 1.1, 1.3)
test_disk_compliance_persisted
test_disk_compliance_clean_omitted
test_repair_summary_persisted
test_repair_summary_serializable
test_merge_conflicts_persisted
test_merge_conflicts_absent_when_clean
test_checkpoint_details_persisted
test_checkpoint_details_truncated
test_contract_violations_persisted
test_contract_violations_capped
test_skipped_files_persisted
test_language_warnings_persisted
test_pre_merge_repair_metadata
test_element_repair_summary
test_disk_quality_score_at_integration
test_disk_quality_score_none_non_python

# Utility extraction (Step 1.2, 1.4)
test_quality_score_import_validator
test_quality_score_import_postmortem_reexport
test_quality_score_boundary_values
test_effectiveness_api_format

# Budget + context (Steps 1.5, 1.6)
test_budget_decision_returned
test_budget_sections_dropped_tracked

# Queue + prime (Steps 1.7, 1.8)
test_seed_metadata_preserved
test_domain_validation_persisted
```

**Total:** 22 tests, ~300 lines

---

## Phase 2: Review Step — Log-Only (Low Risk)

**Goal:** Add per-feature LLM review to Prime Contractor. Review produces score, verdict, and issues. Results are logged and stored — but do NOT gate or trigger re-draft. This lets you verify review quality before wiring behavioral changes.

**Ship criterion:** Run with `review_enabled=True`, see review scores in logs. Verify scores are reasonable. Run with `review_enabled=False`, behavior identical to current.

### Step 2.1: Prime Review Adapter (RFL-120)

**New file:** `src/startd8/contractors/prime_review.py` (~100 lines)

Core class `PrimeReviewAdapter`:
- `review_feature(feature, project_root, integration_metadata) → dict`
- Maps `FeatureSpec` → synthetic `SeedTask` (field mapping: id→task_id, name→title, etc.)
- Reads generated files from disk into concatenated code string
- Packs disk compliance + repair data into `test_results` dict (zero ReviewPhaseHandler modification)
- Calls `ReviewPhaseHandler._review_task(task, generated_code, test_results)`
- Returns `{score, verdict, issues, suggestions, cost_usd, tokens}`
- Graceful failure: returns `{verdict: "ERROR"}` on exception, logs WARNING

### Step 2.2: Wire Review into PrimeContractor (RFL-125)

**File:** `src/startd8/contractors/prime_contractor.py`

Config additions:
```python
self.review_enabled = config.get("review_enabled", True)  # On by default
self._review_adapter = None  # Lazy init
```

After `integrate_feature()` succeeds:
```python
if self.review_enabled:
    review = self._review_feature(feature, integration_metadata)
    feature.metadata["review"] = review
    self.review_results[feature.id] = review
    logger.info("Review: %s score=%s verdict=%s",
                feature.name, review.get("score"), review.get("verdict"))
```

Helper:
```python
def _review_feature(self, feature, integration_metadata):
    if self._review_adapter is None:
        from startd8.contractors.prime_review import PrimeReviewAdapter
        self._review_adapter = PrimeReviewAdapter(
            review_agent=self.config.get("review_agent"),
            lead_agent=self.config.get("lead_agent"),
        )
    return self._review_adapter.review_feature(
        feature, self.project_root, integration_metadata,
    )
```

### Step 2.3: Review Issue Classification (RFL-210)

**File:** `src/startd8/contractors/prime_review.py`

Keyword-based classification added to review results:
```python
_ISSUE_KEYWORDS = {
    "syntax": ["syntax", "parse", "indentation", "bracket"],
    "semantics": ["import", "undefined", "unused", "unreachable", "dead code", "stub"],
    "design": ["architecture", "coupling", "cohesion", "separation"],
    "naming": ["naming", "convention", "camelCase", "snake_case"],
    "testing": ["test", "coverage", "assertion", "mock"],
    "performance": ["performance", "complexity", "O(n", "inefficient"],
    "security": ["security", "injection", "sanitiz", "credential"],
}
```

Added to review output as `classified_issues: list[dict]`.

### Step 2.4: Tests

**New file:** `tests/unit/contractors/test_prime_review.py`

```
test_feature_to_seed_task_mapping
test_read_generated_code
test_pack_validation_as_test_results
test_review_graceful_failure
test_review_skip_no_code
test_review_enabled_default
test_review_disabled_config
test_classify_issues_keywords
```

**Total:** 8 tests, ~120 lines

---

## Phase 3: Quality Gate + Within-Run Feedback (Medium Risk)

**Prerequisite:** Phase 2 deployed. Review scores verified as reasonable in ≥1 real run.

**Goal:** Wire review verdict into a quality gate that triggers re-draft with the reviewer's specific issues as corrective guidance. Close the within-run feedback loop so feature B benefits from feature A's signals.

**Ship criterion:** Features with FAIL + low score trigger re-draft. Re-drafted features show measurable score improvement. Subsequent features avoid patterns from prior features.

### Step 3.1: RunQualityAccumulator (RFL-200)

**New file:** `src/startd8/contractors/run_quality_accumulator.py` (~80 lines)

```python
@dataclass
class RunQualityAccumulator:
    semantic_pattern_counts: dict[str, int]
    review_issue_counts: dict[str, int]
    quality_scores: list[float]
    repair_counts: list[int]
    features_processed: int = 0

    def record_integration_result(self, metadata: dict) -> None: ...
    def record_review_result(self, review: dict) -> None: ...
    def get_run_level_patterns(self) -> dict[str, int]: ...  # ≥2 threshold
    def get_quality_trend(self) -> str | None: ...  # "declining" or None
    def build_spec_hints(self, existing_kaizen_categories=None) -> str | None: ...  # ≤500 chars
```

### Step 3.2: Quality Gate (RFL-220, 225, 230)

**File:** `src/startd8/contractors/prime_contractor.py`

After review:
```python
if (self.quality_gate_enabled
        and review.get("verdict") == "FAIL"
        and not getattr(feature, "_redrafted", False)
        and integration_metadata.get("disk_quality_score", 1.0) < self.quality_gate_threshold):

    corrective = self._build_corrective_hint(review)
    feature._redrafted = True
    original_score = integration_metadata.get("disk_quality_score", 0)

    # Re-draft with corrective hint as P0
    redraft_meta = self._redraft_feature(feature, corrective)

    # Mottainai: accept whichever version scores higher
    new_score = redraft_meta.get("disk_quality_score", 0) if redraft_meta else 0
    if new_score <= original_score:
        self._restore_original(feature)
```

Config:
```python
quality_gate_enabled: bool = True  # On by default
quality_gate_threshold: float = 0.5
```

**Corrective hint builder:**
```python
def _build_corrective_hint(self, review: dict) -> str:
    issues = review.get("issues", [])
    blocking = [i for i in issues if "BLOCKING" in i.upper() or "MAJOR" in i.upper()]
    if not blocking:
        blocking = issues[:5]
    hint = "CRITICAL: Previous generation was reviewed and REJECTED.\nFix these issues:\n"
    hint += "\n".join(f"- {i[:150]}" for i in blocking[:8])
    hint += f"\nYour score was {review.get('score', '?')}/100."
    return hint[:800]
```

### Step 3.3: Accumulator Wiring (RFL-240)

**File:** `src/startd8/contractors/prime_contractor.py`

In `run()`:
```python
from startd8.contractors.run_quality_accumulator import RunQualityAccumulator
accumulator = RunQualityAccumulator()
```

After each feature (including re-draft):
```python
accumulator.record_integration_result(integration_metadata)
if review:
    accumulator.record_review_result(review)
```

Before next feature's spec:
```python
hints = accumulator.build_spec_hints(existing_kaizen_categories=...)
if hints:
    context["run_quality_hints"] = hints
```

### Step 3.4: Spec Builder Injection (RFL-250)

**File:** `src/startd8/implementation_engine/spec_builder.py`

In `build_spec_prompt()`:
```python
run_hints = context.get("run_quality_hints")
if run_hints:
    prioritized_sections.append({
        "name": "run_quality_hints",
        "content": f"## Prior Integration Findings (This Run)\n\n{run_hints}",
        "priority": 2,
        "budget": 500,
    })
```

### Step 3.5: Tests

**Extend test files:**

```
# Accumulator
test_accumulator_record_integration
test_accumulator_record_review
test_accumulator_patterns_threshold
test_accumulator_build_hints_format
test_accumulator_build_hints_dedup
test_accumulator_quality_trend_declining
test_accumulator_quality_trend_stable

# Gate
test_gate_triggers_fail_and_low_score
test_gate_skips_fail_but_high_score
test_gate_skips_pass_and_low_score
test_gate_max_one_redraft
test_gate_accept_better_version
test_corrective_hint_content
test_corrective_hint_cap_800

# Spec injection
test_spec_run_hints_present
```

**Total:** 15 tests, ~250 lines

---

## Phase 4: Upstream Amplification (Low Risk, Zero LLM Cost)

**Prerequisite:** Phase 3 deployed. Within-run feedback producing measurable quality improvement.

**Goal:** Close the cross-run feedback loop at the seed level. Quality signals persist across runs, flow per-task, and work identically for Prime and Artisan.

### Step 4.1: SeedTask.quality_hints Field (RFL-300)

**File:** `src/startd8/seeds/models.py`

```python
quality_hints: list[str] = field(default_factory=list)
```

In `from_seed_entry()`:
```python
quality_hints = context.get("quality_hints", [])
```

### Step 4.2: Plan Ingestion Per-Task Distribution (RFL-310)

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

In transform phase:
```python
def _distribute_kaizen_to_tasks(self, tasks, suggestions):
    for task in tasks:
        matched = self._match_suggestions(task, suggestions)
        task.quality_hints.extend(matched[:3])
```

Matching heuristic: suggestion's `pattern_type` → task's `target_files` or `domain` overlap.

### Step 4.3: Post-Ingestion Enrichment Script (RFL-320)

**New file:** `scripts/enrich_seed_from_postmortem.py`

```bash
python3 scripts/enrich_seed_from_postmortem.py \
    --seed seed.json \
    --postmortem previous-run/kaizen-suggestions.json \
    --output enriched-seed.json
```

Wire into `.cap-dev-pipe/run-prime-contractor.sh` as optional `--postmortem <path>`.

### Step 4.4: Context Resolution Threading (RFL-330)

**File:** `src/startd8/contractors/context_resolution.py`

Both strategies extract and forward `quality_hints`:
```python
quality_hints = meta_enrichment.get("quality_hints", [])
if quality_hints:
    gen_context["quality_hints"] = quality_hints
```

**File:** `src/startd8/implementation_engine/spec_builder.py`

```python
quality_hints = context.get("quality_hints", [])
if quality_hints:
    prioritized_sections.append({
        "name": "quality_hints",
        "content": "## Quality Guidance (From Previous Runs)\n\n"
                   + "\n".join(f"- {h}" for h in quality_hints),
        "priority": 1.5,
        "budget": 600,
    })
```

### Step 4.5: Tests

```
test_seed_task_quality_hints_field
test_seed_task_from_entry_quality_hints
test_distribute_kaizen_to_tasks
test_distribute_kaizen_cap_3
test_enrichment_script_idempotent
test_context_resolution_quality_hints
test_spec_quality_hints_section
```

**Total:** 7 tests, ~100 lines

---

## Phase 5: Calibration & Observability (Low Risk)

### Step 5.1: Repair Effectiveness → Spec Calibration (RFL-270)

**File:** `src/startd8/implementation_engine/spec_builder.py`

```python
try:
    from startd8.repair.orchestrator import get_step_effectiveness_summary
    effectiveness = get_step_effectiveness_summary()
    low_eff = [n for n, d in effectiveness.items()
               if d["attempts"] >= 5 and d["success_rate"] < 0.2]
    if low_eff:
        prioritized_sections.append({
            "name": "repair_calibration",
            "content": f"## Repair Reliability Warning\n\nAuto-repair unreliable for: {', '.join(low_eff)}.",
            "priority": 1,
            "budget": 300,
        })
except ImportError:
    pass
```

### Step 5.2: Quality Trend Warning (RFL-260)

Already implemented in accumulator's `get_quality_trend()`. Wire to spec builder:
```python
trend = accumulator.get_quality_trend() if accumulator else None
if trend == "declining":
    context["_quality_trend_warning"] = True
```

In spec builder:
```python
if context.get("_quality_trend_warning"):
    prioritized_sections.append({
        "name": "quality_trend",
        "content": "## Quality Trend Warning\n\nQuality scores declining across recent features. "
                   "Take extra care with imports, stubs, and contract compliance.",
        "priority": 1,
        "budget": 200,
    })
```

### Step 5.3: OTel Attributes (RFL-500)

**File:** `src/startd8/contractors/integration_engine.py`

```python
span.set_attribute("integration.disk_quality_score", metadata.get("disk_quality_score", -1))
span.set_attribute("integration.semantic_issue_count", sum(...))
span.set_attribute("integration.repair_steps_applied", len(...))
```

**File:** `src/startd8/contractors/prime_contractor.py`

```python
span.set_attribute("review.score", review.get("score", -1))
span.set_attribute("review.verdict", review.get("verdict", "N/A"))
span.set_attribute("quality_gate.triggered", gate_fired)
```

**File:** `src/startd8/implementation_engine/spec_builder.py`

```python
span.set_attribute("spec.run_quality_hints.present", bool(run_hints))
span.set_attribute("spec.quality_hints.count", len(quality_hints))
```

### Step 5.4: Tests

```
test_repair_calibration_low_effectiveness
test_repair_calibration_high_effectiveness
test_repair_calibration_insufficient_data
test_quality_trend_spec_warning
test_otel_integration_attributes
test_otel_review_attributes
test_otel_spec_attributes
test_otel_quality_gate_attributes
```

**Total:** 8 tests, ~120 lines

---

## Consolidated File Change Map

| File | Phase | Changes |
|------|-------|---------|
| `integration_engine.py` | 1, 5 | Persist 9 metadata keys + quality score + OTel |
| `forward_manifest_validator.py` | 1 | Receive `compute_disk_quality_score()` |
| `prime_postmortem.py` | 1 | Re-export quality score function |
| `repair/orchestrator.py` | 1 | Public effectiveness API |
| `budget.py` | 1 | Return `tuple[str, dict]` |
| `context_resolution.py` | 1, 4 | Field skip tracking + quality_hints threading |
| `queue.py` | 1 | Seed metadata preservation |
| `spec_builder.py` | 1, 3, 4, 5 | Budget decision, run hints, quality hints, calibration, OTel |
| `drafter.py` | 1 | Budget decision |
| `prime_contractor.py` | 1, 2, 3, 5 | Domain validation, review wiring, gate, accumulator, OTel |
| **prime_review.py** (NEW) | 2 | Review adapter (~100 lines) |
| **run_quality_accumulator.py** (NEW) | 3 | Accumulator (~80 lines) |
| `seeds/models.py` | 4 | quality_hints field |
| `plan_ingestion_workflow.py` | 4 | Per-task kaizen distribution |
| **enrich_seed_from_postmortem.py** (NEW) | 4 | Post-ingestion enrichment script |
| **test_signal_preservation.py** (NEW) | 1 | 22 tests |
| **test_prime_review.py** (NEW) | 2 | 8 tests |
| test_review_feedback_loop.py (extend) | 3 | 15 tests |
| test_upstream_amplification.py (extend) | 4, 5 | 15 tests |

---

## Risk Summary

| Phase | Risk | Mitigations |
|-------|------|-------------|
| 1 | None (additive metadata) | All changes are `.metadata[key] = dict`. No behavioral change. |
| 1 | Low (budget.py return type) | Only 2–3 call sites. Update simultaneously. |
| 2 | Low (new LLM call) | Graceful failure → `{verdict: "ERROR"}`. Log-only, no gating. |
| 3 | Medium (re-draft loop) | Max 1 re-draft per feature. Budget guard disables gate. Accept-better-version (Mottainai). |
| 4 | Low (seed model change) | New field defaults to `[]`. No existing tests break. |
| 5 | Low (OTel + calibration) | All additive. Try/except guards on OTel. |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial unified plan from pipeline audit |
