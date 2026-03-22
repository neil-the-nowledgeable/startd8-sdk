# Review Feedback Loop — Implementation Plan

**Version:** 2.0.0
**Created:** 2026-03-22
**Updated:** 2026-03-22 (v2.0 — review adapter, iterative delivery, upstream amplification)
**Requirements:** `REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md` v2.0

---

## Iteration 1: Plumbing + Review (Low Risk, Ship First)

**Goal:** Persist existing signals, add log-only review step. No behavioral change to generation.
**Estimated:** ~250 lines production, ~200 lines test
**LLM Cost:** +1 call per feature (review)

### Step 1.1: Persist DiskComplianceResult (REQ-RFL-100)

**File:** `src/startd8/contractors/integration_engine.py`
**Method:** `_run_semantic_checks()` (void, side-effect method)

After existing `logger.warning()` for semantic issues, accumulate:
```python
compliance_results = {}
for fpath in integrated_files:
    result = validate_disk_compliance(str(fpath), project_root)
    # ... existing warning logging unchanged ...
    if (result.semantic_issues or result.stubs_remaining > 0
            or result.import_completeness < 1.0 or result.contract_compliance < 1.0):
        rel = str(fpath.relative_to(project_root))
        compliance_results[rel] = {
            "ast_valid": result.ast_valid,
            "stubs_remaining": result.stubs_remaining,
            "duplicate_definitions": result.duplicate_definitions,
            "import_completeness": result.import_completeness,
            "contract_compliance": result.contract_compliance,
            "semantic_issues": [
                {"category": si.get("category", "unknown"),
                 "severity": si.get("severity", "warning"),
                 "message": str(si.get("message", ""))[:200]}
                for si in (result.semantic_issues or [])
            ],
        }
```

Thread to integration result metadata in `integrate()`:
```python
if hasattr(unit, "_compliance_results") and unit._compliance_results:
    result_obj.metadata["disk_compliance"] = unit._compliance_results
```

### Step 1.2: Persist RepairOutcome Summary (REQ-RFL-105)

**File:** `src/startd8/contractors/integration_engine.py`

New helper:
```python
def _condense_repair_outcome(self, outcome, phase: str) -> dict:
    return {
        "phase": phase,
        "total_repairs": len(outcome.repaired_files) if outcome.repaired_files else 0,
        "steps_applied": list(outcome.steps_applied) if outcome.steps_applied else [],
        "any_modified": bool(outcome.any_modified),
    }
```

After each repair call, store in metadata:
```python
repair_summaries = result_obj.metadata.setdefault("repair_summaries", [])
if pre_merge_outcome:
    repair_summaries.append(self._condense_repair_outcome(pre_merge_outcome, "pre_merge"))
```

### Step 1.3: Extract compute_disk_quality_score() (REQ-RFL-110)

**From:** `src/startd8/contractors/prime_postmortem.py`
**To:** `src/startd8/forward_manifest_validator.py`

1. Copy function to `forward_manifest_validator.py` after `DiskComplianceResult` class.
2. In `prime_postmortem.py`: `from startd8.forward_manifest_validator import compute_disk_quality_score`
3. Verify no instance-state dependencies (already confirmed: pure function using getattr).

### Step 1.4: Compute Score at Integration Time (REQ-RFL-115)

**File:** `src/startd8/contractors/integration_engine.py`

After Step 1.1's compliance storage:
```python
if compliance_results:
    from types import SimpleNamespace
    from startd8.forward_manifest_validator import compute_disk_quality_score
    scores = [compute_disk_quality_score(SimpleNamespace(**d)) for d in compliance_results.values()]
    result_obj.metadata["disk_quality_score"] = min(scores)
```

### Step 1.5: Prime Review Adapter (REQ-RFL-120)

**New file:** `src/startd8/contractors/prime_review.py` (~100 lines)

```python
"""Lightweight adapter bridging Prime Contractor to Artisan ReviewPhaseHandler."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PrimeReviewAdapter:
    """Reviews Prime Contractor output using Artisan's ReviewPhaseHandler."""

    def __init__(self, review_agent: str | None = None, lead_agent: str | None = None):
        self._review_agent = review_agent
        self._lead_agent = lead_agent
        self._handler = None  # Lazy init

    def _ensure_handler(self):
        if self._handler is not None:
            return
        from startd8.contractors.context_seed.core import ReviewPhaseHandler
        # Minimal HandlerConfig — only review_agent and lead_agent needed
        config = _build_minimal_config(self._review_agent, self._lead_agent)
        self._handler = ReviewPhaseHandler(handler_config=config)

    def review_feature(
        self,
        feature,          # FeatureSpec or similar
        project_root: Path,
        integration_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Review a completed feature. Returns {score, verdict, issues, suggestions, cost_usd}."""
        self._ensure_handler()

        # Build synthetic SeedTask
        task = self._feature_to_seed_task(feature)

        # Read generated code from disk
        generated_code = self._read_generated_code(feature, project_root)
        if not generated_code:
            return {"score": None, "verdict": "SKIP", "issues": [], "suggestions": [],
                    "reason": "no generated code found"}

        # Pack validation signals into test_results (zero-modification path)
        test_results = self._pack_validation_as_test_results(integration_metadata or {})

        # Call review
        try:
            review = self._handler._review_task(
                task=task,
                generated_code=generated_code,
                test_results=test_results,
            )
            return review
        except Exception:
            logger.warning("Review failed for %s", feature.name, exc_info=True)
            return {"score": None, "verdict": "ERROR", "issues": [], "suggestions": []}

    def _feature_to_seed_task(self, feature):
        """Map FeatureSpec fields to synthetic SeedTask."""
        from startd8.seeds.models import SeedTask
        return SeedTask(
            task_id=str(feature.id),
            title=feature.name,
            description=feature.description or "",
            domain=feature.metadata.get("domain", "general") if feature.metadata else "general",
            target_files=list(feature.target_files) if feature.target_files else [],
            prompt_constraints=feature.metadata.get("prompt_constraints", []) if feature.metadata else [],
        )

    def _read_generated_code(self, feature, project_root: Path) -> str:
        """Read generated files from disk into a single code string."""
        parts = []
        for fpath in (feature.generated_files or feature.target_files or []):
            full = project_root / fpath
            if full.is_file():
                try:
                    parts.append(f"# {fpath}\n{full.read_text()}")
                except OSError:
                    continue
        return "\n\n".join(parts)

    def _pack_validation_as_test_results(self, metadata: dict) -> dict:
        """Pack disk compliance + repair data into test_results dict."""
        results = {}
        compliance = metadata.get("disk_compliance")
        if compliance:
            results["validation_results"] = compliance
            results["disk_quality_score"] = metadata.get("disk_quality_score")
        repair = metadata.get("repair_summaries")
        if repair:
            results["repair_summary"] = repair
        return results


def _build_minimal_config(review_agent, lead_agent):
    """Build minimal HandlerConfig for review."""
    # Import lazily to avoid circular deps
    from startd8.contractors.context_seed.core import HandlerConfig
    return HandlerConfig(
        review_agent=review_agent,
        lead_agent=lead_agent,
    )
```

### Step 1.6: Wire Review into PrimeContractor (REQ-RFL-125)

**File:** `src/startd8/contractors/prime_contractor.py`

In `__init__` or config:
```python
self.review_enabled = config.get("review_enabled", True)
self._review_adapter = None  # Lazy init
```

After `integrate_feature()` succeeds:
```python
# Per-feature review (REQ-RFL-125)
if self.review_enabled:
    review = self._review_feature(feature, integration_metadata)
    feature.metadata["review"] = review
    self.review_results[feature.id] = review
    logger.info("Review for %s: score=%s verdict=%s",
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

### Step 1.7: Repair Effectiveness API (REQ-RFL-128)

**File:** `src/startd8/repair/orchestrator.py`

```python
def get_step_effectiveness_summary() -> dict[str, dict]:
    """Read-only snapshot of per-step effectiveness data."""
    return {
        name: {
            "attempts": eff.attempts,
            "success_rate": eff.modifications / max(eff.attempts, 1),
            "contributed_to_success": eff.contributed_to_success,
        }
        for name, eff in _step_effectiveness.items()
    }
```

### Step 1.8: Tests

**New file:** `tests/unit/contractors/test_review_feedback_loop.py`

```
# Phase 0 plumbing
test_compliance_stored_in_metadata
test_compliance_clean_omitted
test_repair_summary_condensed
test_repair_summary_serializable
test_quality_score_extracted
test_quality_score_reexport
test_quality_score_boundary_values
test_effectiveness_api

# Review adapter
test_feature_to_seed_task_mapping
test_read_generated_code
test_pack_validation_as_test_results
test_review_graceful_failure
test_review_skip_no_code

# Wiring
test_review_enabled_default
test_review_disabled_config
test_review_result_stored_in_metadata
```

**Estimated:** 16 tests, ~200 lines

---

## Iteration 2: Gate + Feedback (Medium Risk, After I1 Verified)

**Prerequisite:** I1 deployed, review producing reasonable scores in ≥1 real run.
**Estimated:** ~200 lines production, ~250 lines test
**LLM Cost:** +1 call per gate fire (re-draft re-integration re-review)

### Step 2.1: RunQualityAccumulator (REQ-RFL-200)

**New file:** `src/startd8/contractors/run_quality_accumulator.py` (~80 lines)

See REQ-RFL-200 for full spec. Key methods:
- `record_integration_result(metadata)` — semantic patterns, scores, repair counts
- `record_review_result(review)` — review score, classified issues
- `get_run_level_patterns()` — categories with ≥2 occurrences
- `build_spec_hints(existing_kaizen_categories)` — ≤500 char hint string
- `get_quality_trend()` — "declining" or None

### Step 2.2: Review Issue Classification (REQ-RFL-210)

**File:** `src/startd8/contractors/prime_review.py`

```python
_ISSUE_CATEGORY_KEYWORDS = {
    "syntax": ["syntax", "parse", "indentation", "bracket"],
    "semantics": ["import", "undefined", "unused", "unreachable", "dead code", "stub"],
    "design": ["architecture", "coupling", "cohesion", "separation"],
    "naming": ["naming", "convention", "camelCase", "snake_case"],
    "testing": ["test", "coverage", "assertion", "mock"],
    "performance": ["performance", "complexity", "O(n", "inefficient"],
    "security": ["security", "injection", "sanitiz", "credential"],
}

def classify_review_issues(issues: list[str]) -> list[dict]:
    classified = []
    for text in issues:
        text_lower = text.lower()
        category = "other"
        for cat, keywords in _ISSUE_CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                category = cat
                break
        classified.append({"category": category, "text": text})
    return classified
```

### Step 2.3: Quality Gate (REQ-RFL-220, 225, 230)

**File:** `src/startd8/contractors/prime_contractor.py`

After review in `process_feature()`:
```python
# Quality gate (REQ-RFL-220)
if (self.quality_gate_enabled
        and review.get("verdict") == "FAIL"
        and not feature._redrafted
        and integration_metadata.get("disk_quality_score", 1.0) < self.quality_gate_threshold):

    logger.warning("Quality gate: %s FAIL (score %.2f < %.2f) — re-drafting",
                   feature.name, integration_metadata["disk_quality_score"],
                   self.quality_gate_threshold)

    # Build corrective hint from review issues (REQ-RFL-225)
    corrective = self._build_corrective_hint(review)
    feature._redrafted = True
    feature.metadata["corrective_hint"] = corrective

    # Re-draft: inject corrective hint as P0 context
    original_score = integration_metadata.get("disk_quality_score", 0)
    success = self._redraft_feature(feature, corrective)

    # Accept better version (Mottainai)
    if success:
        new_score = feature.metadata.get("disk_quality_score", 0)
        if new_score <= original_score:
            logger.info("Re-draft scored %.2f ≤ original %.2f — keeping original",
                        new_score, original_score)
            self._restore_original(feature)
```

### Step 2.4: Accumulator Wiring + Spec Injection (REQ-RFL-240, 250)

**File:** `src/startd8/contractors/prime_contractor.py`

In `run()`:
```python
accumulator = RunQualityAccumulator()
```

After each feature completes:
```python
accumulator.record_integration_result(integration_metadata)
accumulator.record_review_result(review)
```

Before next feature's spec:
```python
hints = accumulator.build_spec_hints(existing_kaizen_categories=...)
if hints:
    context["run_quality_hints"] = hints
```

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

### Step 2.5: Tests

```
# Accumulator
test_accumulator_record_signals
test_accumulator_patterns_threshold
test_accumulator_build_hints
test_accumulator_build_hints_dedup
test_accumulator_quality_trend

# Gate
test_gate_triggers_fail_and_low_score
test_gate_skips_fail_but_high_score
test_gate_skips_pass_and_low_score
test_gate_max_one_redraft
test_gate_budget_guard
test_gate_accept_better_version

# Classification
test_classify_issues_keywords
test_classify_issues_other

# Spec injection
test_spec_run_hints_present
test_spec_run_hints_first_feature_absent
test_spec_coexist_kaizen
```

**Estimated:** 15 tests, ~250 lines

---

## Iteration 3: Upstream Amplification (Low Risk, After I2 Verified)

**Prerequisite:** I2 deployed, within-run feedback producing measurable quality improvement.
**Estimated:** ~150 lines production, ~100 lines test

### Step 3.1: SeedTask.quality_hints (REQ-RFL-300)

**File:** `src/startd8/seeds/models.py`

Add field:
```python
quality_hints: list[str] = field(default_factory=list)
```

In `from_seed_entry()`:
```python
quality_hints = context.get("quality_hints", [])
```

### Step 3.2: Plan Ingestion Distribution (REQ-RFL-310)

**File:** `src/startd8/workflows/builtin/plan_ingestion_workflow.py`

In transform phase, after task derivation:
```python
def _distribute_kaizen_to_tasks(self, tasks, suggestions):
    """Match kaizen suggestions to tasks by pattern affinity."""
    for task in tasks:
        matched = self._match_suggestions(task, suggestions)
        task.quality_hints.extend(matched[:3])  # Cap at 3 per task
```

### Step 3.3: Post-Ingestion Enrichment Script (REQ-RFL-320)

**New file:** `scripts/enrich_seed_from_postmortem.py`

```bash
python3 scripts/enrich_seed_from_postmortem.py \
    --seed seed.json \
    --postmortem previous-run/kaizen-suggestions.json \
    --output enriched-seed.json
```

Wire into `.cap-dev-pipe/run-prime-contractor.sh`:
```bash
if [ -n "$POSTMORTEM_PATH" ]; then
    python3 scripts/enrich_seed_from_postmortem.py \
        --seed "$SEED_PATH" --postmortem "$POSTMORTEM_PATH" --output "$ENRICHED_SEED"
    SEED_PATH="$ENRICHED_SEED"
fi
```

### Step 3.4: Context Resolution Threading (REQ-RFL-330)

**File:** `src/startd8/contractors/context_resolution.py`

In both `StandaloneContextStrategy` and `PipelineContextStrategy`:
```python
quality_hints = meta_enrichment.get("quality_hints", [])
if quality_hints:
    gen_context["quality_hints"] = quality_hints
```

In spec builder, render as separate section:
```python
quality_hints = context.get("quality_hints", [])
if quality_hints:
    prioritized_sections.append({
        "name": "quality_hints",
        "content": "## Quality Guidance (From Previous Runs)\n\n" + "\n".join(f"- {h}" for h in quality_hints),
        "priority": 1.5,  # Between kaizen P1 and run hints P2
        "budget": 600,
    })
```

### Step 3.5: Tests

```
test_seed_task_quality_hints_field
test_seed_task_from_entry_quality_hints
test_distribute_kaizen_to_tasks
test_distribute_kaizen_cap
test_enrichment_script_idempotent
test_context_resolution_quality_hints
test_spec_quality_hints_section
```

**Estimated:** 7 tests, ~100 lines

---

## Execution Summary

| Iteration | Files Modified | Files Created | Tests | Prod Lines | Risk |
|-----------|---------------|---------------|-------|------------|------|
| I1 | integration_engine.py, forward_manifest_validator.py, prime_postmortem.py, repair/orchestrator.py, prime_contractor.py | prime_review.py, test_review_feedback_loop.py | 16 | ~250 | Low |
| I2 | prime_contractor.py, spec_builder.py, prime_review.py | run_quality_accumulator.py | 15 | ~200 | Medium |
| I3 | seeds/models.py, plan_ingestion_workflow.py, context_resolution.py, spec_builder.py | enrich_seed_from_postmortem.py | 7 | ~150 | Low |
| **Total** | **8 modified** | **4 created** | **38** | **~600** | |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial plan |
| 1.1.0 | 2026-03-22 | human:neil + agent:claude-code | Corrected for Prime architecture |
| 2.0.0 | 2026-03-22 | human:neil + agent:claude-code | Review adapter, Option C gate, iterative delivery, upstream amplification |
