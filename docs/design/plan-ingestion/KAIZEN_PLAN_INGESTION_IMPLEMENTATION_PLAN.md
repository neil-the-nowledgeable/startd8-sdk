# Kaizen for Plan Ingestion — Implementation Plan

> **Version:** 0.2.0
> **Status:** IMPLEMENTED (Layers 1–6 SDK-side complete; cap-dev-pipe integration pending for REQ-KPI-102, 502)
> **Date:** 2026-03-09
> **Requirements:** [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](./KAIZEN_PLAN_INGESTION_REQUIREMENTS.md)

---

## Phasing Strategy

Four implementation phases, ordered by value and dependency:

| Phase | Focus | Requirements | LLM Calls | Risk |
|-------|-------|-------------|-----------|------|
| **P0** | Diagnostic report + quality metrics | L1 + L3 | 0 | Low — deterministic, read-only |
| **P1** | Prompt-response capture | L2 | 0 | Low — opt-in, write-only |
| **P2** | Cross-run analysis + feedback | L4 + L5 | 0 | Medium — new scripts + config format |
| **P3** | Pipeline integration | L6 | 0 | Medium — touches cap-dev-pipe |

**P0 and P1 are independent** and can be developed in parallel. P2 depends on P0 (needs diagnostic reports to aggregate). P3 depends on P0 (needs quality score to gate on).

---

## Phase 0: Diagnostic Report + Quality Metrics

**Goal:** Every plan ingestion run produces a structured `plan-ingestion-diagnostic.json` with per-phase metrics and quality scores. Zero runtime cost beyond JSON serialization.

**Estimated scope:** ~350 lines new code + ~200 lines tests.

### Step 1: Diagnostic dataclass module

**File:** `src/startd8/workflows/builtin/plan_ingestion_diagnostics.py` (new)

Create typed dataclasses for the diagnostic report:

```python
@dataclass
class PhaseDiagnostic:
    """Per-phase diagnostic metrics."""
    phase: str
    success: bool
    time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    code_extraction_fallback: bool = False
    quality_signals: dict = field(default_factory=dict)

@dataclass
class IngestionDiagnostic:
    """Complete diagnostic report for a plan ingestion run."""
    schema_version: str = "1.0.0"
    run_timestamp: str = ""
    plan_source: str = ""
    plan_checksum: str = ""
    route: str = ""
    overall_success: bool = False
    phases: dict[str, PhaseDiagnostic] = field(default_factory=dict)
    totals: dict[str, Any] = field(default_factory=dict)
    seed_quality_score: float = 0.0
    quality_warnings: list[str] = field(default_factory=list)
```

Follow the `micro_prime/reporting.py` pattern (dataclass + `persist_diagnostic()` with advisory I/O):

```python
def persist_diagnostic(diag: IngestionDiagnostic, output_dir: Path) -> None:
    """Write diagnostic report. Advisory — never fails a successful run."""
    try:
        path = output_dir / "plan-ingestion-diagnostic.json"
        path.write_text(json.dumps(asdict(diag), indent=2, default=str))
    except OSError as err:
        logger.warning("Diagnostic write failed: %s", err)
```

**Closes:** REQ-KPI-100

### Step 2: PARSE quality signals

**File:** `plan_ingestion_diagnostics.py`

Add `compute_parse_quality(parsed_plan: ParsedPlan) -> dict`:

```python
def compute_parse_quality(parsed: ParsedPlan) -> dict:
    features = parsed.features
    total = len(features) or 1  # avoid div/0
    return {
        "features_extracted": len(features),
        "files_mentioned": len(parsed.mentioned_files),
        "features_with_targets": sum(1 for f in features if f.target_files),
        "features_with_deps": sum(1 for f in features if f.dependencies),
        "multi_file_features": sum(1 for f in features if len(f.target_files) > 1),
        "features_with_signatures": sum(1 for f in features if f.api_signatures),
        "dep_graph_coverage": len(parsed.dependency_graph) / total,
    }
```

No new imports needed — `ParsedPlan` is already defined in `plan_ingestion_models.py`.

**Closes:** REQ-KPI-300

### Step 3: ASSESS quality signals

**File:** `plan_ingestion_diagnostics.py`

Add `compute_assess_quality(score: ComplexityScore, threshold: int) -> dict`:

```python
def compute_assess_quality(score: ComplexityScore, threshold: int) -> dict:
    dims = [
        score.feature_count, score.cross_file_deps, score.api_surface,
        score.test_complexity, score.integration_depth,
        score.domain_novelty, score.ambiguity,
    ]
    return {
        "composite_score": score.composite,
        "route_decision": score.route.value,
        "route_margin": abs(score.composite - threshold),
        "dimension_spread": max(dims) - min(dims) if dims else 0,
    }
```

**Closes:** REQ-KPI-301

### Step 4: TRANSFORM + EMIT quality signals (seed quality score)

**File:** `plan_ingestion_diagnostics.py`

Add `compute_seed_quality(seed_dict: dict) -> tuple[float, list[str]]`:

```python
def compute_seed_quality(seed_dict: dict) -> tuple[float, list[str]]:
    """Compute weighted seed quality score (0.0–1.0) and warning list.

    Leverages _validate_seed_field_coverage() for field-coverage checks.
    """
    tasks = seed_dict.get("tasks", [])
    total = len(tasks) or 1

    # Task description coverage (weight 0.3)
    tasks_with_desc = sum(
        1 for t in tasks
        if t.get("config", {}).get("task_description")
    )
    desc_ratio = tasks_with_desc / total

    # Target file coverage (weight 0.3)
    tasks_with_targets = sum(
        1 for t in tasks
        if t.get("config", {}).get("context", {}).get("target_files")
    )
    target_ratio = tasks_with_targets / total

    # Schema validity (weight 0.2) — reuse existing validator
    schema_valid = _validate_context_seed(seed_dict)
    schema_score = 1.0 if schema_valid else 0.0

    # Field coverage (weight 0.2) — reuse existing advisory validator
    warnings = _validate_seed_field_coverage(seed_dict)
    # 6 possible optional field checks
    coverage_score = max(0.0, 1.0 - len(warnings) / 6)

    score = (
        0.3 * desc_ratio
        + 0.3 * target_ratio
        + 0.2 * schema_score
        + 0.2 * coverage_score
    )
    return score, warnings
```

Note: `_validate_context_seed` and `_validate_seed_field_coverage` already exist in `plan_ingestion_workflow.py`. Either import them or extract to a shared location. Prefer extracting to `plan_ingestion_diagnostics.py` to keep the diagnostics module self-contained (move the functions; leave backward-compatible re-exports in the workflow).

**Closes:** REQ-KPI-302, REQ-KPI-303

### Step 5: REFINE quality signals

**File:** `plan_ingestion_diagnostics.py`

Add `compute_refine_quality(review_output: dict) -> dict`:

```python
def compute_refine_quality(review_output: Optional[dict]) -> dict:
    if not review_output:
        return {"rounds_completed": 0, "suggestions_total": 0, "acceptance_rate": 0.0}
    triage = review_output.get("triage", {})
    accepted = len(triage.get("accepted", []))
    rejected = len(triage.get("rejected", []))
    total = accepted + rejected
    return {
        "rounds_completed": review_output.get("rounds_completed", 0),
        "suggestions_total": total,
        "suggestions_accepted": accepted,
        "suggestions_rejected": rejected,
        "acceptance_rate": accepted / total if total else 0.0,
    }
```

**Closes:** REQ-KPI-304

### Step 6: Wire diagnostic assembly into `_execute()`

**File:** `plan_ingestion_workflow.py`

At the end of `_execute()`, after the EMIT phase (or in the `_fail()` path for error cases), assemble and persist the diagnostic:

```python
# --- DIAGNOSTIC (Kaizen Layer 1+3) ---
from .plan_ingestion_diagnostics import (
    IngestionDiagnostic, PhaseDiagnostic,
    compute_parse_quality, compute_assess_quality,
    compute_seed_quality, compute_refine_quality,
    persist_diagnostic,
)

diag = IngestionDiagnostic(
    run_timestamp=started_at.isoformat(),
    plan_source=str(plan_path),
    plan_checksum=_sha256_file_hex(plan_path),
    route=state.route.value if state.route else "",
    overall_success=state.current_phase == IngestionPhase.COMPLETE,
)
# ... assemble PhaseDiagnostic for each phase from StepResults ...
persist_diagnostic(diag, output_dir)
```

**Key decisions:**
- Diagnostic assembly runs after EMIT (or after failure), so it never interferes with the main pipeline
- Use lazy import to keep the import cost zero when diagnostics are not read
- The `_fail()` closure already calls `_save_state()` — add `persist_diagnostic()` there too for failure cases

**Closes:** REQ-KPI-100, REQ-KPI-101

### Step 7: Code extraction fallback tracking

**File:** `plan_ingestion_workflow.py`

In `_phase_parse`, `_phase_assess`, and `_phase_transform`, after calling `_extract_json_from_response()` or `extract_code_from_response()`, record whether the fallback was used. The simplest approach: add a return flag from the extraction function.

**Option A (minimal):** Check if the response contains `` ``` `` before calling extract. If it doesn't but extract succeeds, `code_extraction_fallback = True`.

```python
# In _phase_parse, after response_text is received:
code_extraction_fallback = "```" not in response_text
```

This is a 1-line addition per phase. Record in the `PhaseDiagnostic.code_extraction_fallback` field.

**Closes:** REQ-KPI-202

### Step 8: Task description density (per-task metrics)

**File:** `plan_ingestion_diagnostics.py`

Add `compute_task_density(tasks: list[dict]) -> list[dict]`:

```python
def compute_task_density(tasks: list[dict]) -> list[dict]:
    results = []
    for t in tasks:
        desc = t.get("config", {}).get("task_description", "")
        results.append({
            "task_id": t.get("task_id", ""),
            "description_chars": len(desc),
            "description_lines": desc.count("\n") + 1 if desc else 0,
            "has_code_examples": "```" in desc,
            "has_requirements_refs": bool(re.search(r"\bREQ[-_]?\w+", desc)),
        })
    return results
```

**Closes:** REQ-KPI-303

### Tests

**File:** `tests/unit/workflows/test_plan_ingestion_diagnostics.py` (new)

| Test | What |
|------|------|
| `test_parse_quality_all_features_have_targets` | All-good plan → 0 multi-file violations |
| `test_parse_quality_multi_file_detected` | Feature with 2 targets → `multi_file_features: 1` |
| `test_assess_quality_route_margin` | Composite 35, threshold 40 → margin 5 |
| `test_seed_quality_score_perfect` | All fields populated → score close to 1.0 |
| `test_seed_quality_score_empty_tasks` | No descriptions → score reflects penalty |
| `test_refine_quality_no_review` | `None` input → zeroed output |
| `test_persist_diagnostic_creates_file` | `tmp_path` → file written with correct keys |
| `test_persist_diagnostic_advisory` | Bad path → no exception raised |
| `test_code_extraction_fallback_detection` | Response without fences → `True` |
| `test_task_density_metrics` | Known descriptions → correct char/line counts |

---

## Phase 1: Prompt-Response Capture

**Goal:** Opt-in persistence of full prompt text and LLM response text for each phase. Enables prompt-quality analysis.

**Estimated scope:** ~120 lines new code + ~80 lines tests.

### Step 1: Kaizen prompt capture utility

**File:** `plan_ingestion_diagnostics.py` (extend)

```python
def persist_prompt_response(
    output_dir: Path,
    phase: str,
    prompt: str,
    response: str,
    max_bytes: int = 2 * 1024 * 1024,
) -> None:
    """Persist prompt and response for a phase. Advisory."""
    kaizen_dir = output_dir / "kaizen-prompts"
    try:
        kaizen_dir.mkdir(parents=True, exist_ok=True)
        _write_with_limit(kaizen_dir / f"{phase}_prompt.txt", prompt, max_bytes)
        _write_with_limit(kaizen_dir / f"{phase}_response.txt", response, max_bytes)
    except OSError as err:
        logger.warning("Kaizen prompt capture failed for %s: %s", phase, err)

def _write_with_limit(path: Path, text: str, max_bytes: int) -> None:
    encoded = text.encode("utf-8")
    if len(encoded) > max_bytes:
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        path.write_text(truncated + f"\n<!-- TRUNCATED at {max_bytes} bytes (original: {len(encoded)}) -->")
    else:
        path.write_text(text, encoding="utf-8")
```

**Closes:** REQ-KPI-200, REQ-KPI-201

### Step 2: Wire into `_phase_parse`, `_phase_assess`, `_phase_transform`

**File:** `plan_ingestion_workflow.py`

In each phase method, after `agent.generate(prompt)` returns `response_text`, add:

```python
if self._kaizen_enabled:
    persist_prompt_response(self._output_dir, "parse", prompt, response_text)
```

The `_kaizen_enabled` flag is read from config:

```python
# In _execute(), during config parsing:
self._kaizen_enabled = _as_bool(config.get("kaizen"), False)
self._output_dir = output_dir
```

**Gate:** Only writes when `--kaizen` is explicitly enabled. Zero overhead otherwise.

**Closes:** REQ-KPI-200, REQ-KPI-201

### Step 3: Wire `--kaizen` flag through `run-plan-ingestion.sh`

**File:** `cap-dev-pipe/run-plan-ingestion.sh`

Add `--kaizen` to the argument parser:

```bash
--kaizen)  PASSTHROUGH_ARGS+=("--config-override" "kaizen=true"); shift ;;
```

This passes through to the SDK workflow config. No SDK-side changes needed beyond reading the flag (Step 2).

### Tests

| Test | What |
|------|------|
| `test_persist_prompt_response_creates_files` | Both files created in correct directory |
| `test_persist_prompt_response_truncation` | 3MB prompt → truncated with sentinel |
| `test_persist_prompt_response_advisory` | Bad path → no exception |
| `test_kaizen_disabled_no_files` | `kaizen=False` → no kaizen-prompts directory |

---

## Phase 2: Cross-Run Analysis + Feedback Loop

**Goal:** Scripts to aggregate diagnostics across runs. Config-driven feedback from analysis to next run.

**Estimated scope:** ~200 lines scripts + ~100 lines SDK + ~50 lines tests.

**Depends on:** Phase 0 (diagnostic reports must exist).

### Step 1: Cross-run trend script

**File:** `cap-dev-pipe/run-kaizen-plan-ingestion-trends.sh` (new) or Python script `scripts/plan_ingestion_trends.py`

**Approach:** Python script is more maintainable for JSON parsing. Place in SDK `scripts/` so it works standalone.

**File:** `scripts/plan_ingestion_trends.py` (new)

```
Usage: python3 scripts/plan_ingestion_trends.py --runs-dir pipeline-output/myproject/ [--last N]
```

Logic:
1. Glob for `**/plan-ingestion-diagnostic.json` under the runs directory
2. Sort by `run_timestamp`
3. Extract key metrics per run: route, features_extracted, seed_quality_score, total cost, per-phase times, code_extraction_fallbacks
4. Print tabular comparison (use `tabulate` if available, plain text otherwise)
5. Compute deltas and trend arrows (↑ improving, ↓ degrading, → stable)

**Closes:** REQ-KPI-400, REQ-KPI-401, REQ-KPI-402

### Step 2: Kaizen config file format

**File:** `src/startd8/workflows/builtin/plan_ingestion_models.py` (extend)

```python
@dataclass
class PlanIngestionKaizenConfig:
    """Kaizen overrides for plan ingestion runs."""
    parse_prompt_suffix: str = ""
    assess_prompt_suffix: str = ""
    transform_prompt_suffix: str = ""
    complexity_threshold_override: Optional[int] = None
```

**Loader:** `plan_ingestion_diagnostics.py`

```python
def load_kaizen_config(path: Path) -> PlanIngestionKaizenConfig:
    data = json.loads(path.read_text())
    section = data.get("plan_ingestion_kaizen", {})
    return PlanIngestionKaizenConfig(**{
        k: v for k, v in section.items()
        if k in PlanIngestionKaizenConfig.__dataclass_fields__
    })
```

**Closes:** REQ-KPI-500 (format), REQ-KPI-501 (threshold override)

### Step 3: Prompt suffix injection

**File:** `plan_ingestion_workflow.py`

In `_phase_parse`, `_phase_assess`, `_phase_transform`, after constructing the prompt from the template, append the kaizen suffix if present:

```python
if self._kaizen_config and self._kaizen_config.parse_prompt_suffix:
    prompt += self._kaizen_config.parse_prompt_suffix
```

Similarly, in `_execute()`, if `complexity_threshold_override` is set, override the `threshold` variable:

```python
if self._kaizen_config and self._kaizen_config.complexity_threshold_override is not None:
    threshold = self._kaizen_config.complexity_threshold_override
    logger.info("Kaizen: complexity threshold overridden to %d", threshold)
```

**Closes:** REQ-KPI-500, REQ-KPI-501

### Step 4: `--kaizen-config` flag in shell script

**File:** `cap-dev-pipe/run-plan-ingestion.sh`

```bash
--kaizen-config)  KAIZEN_CONFIG="$2"; shift 2 ;;
```

Pass as config override: `--config-override "kaizen_config_path=$KAIZEN_CONFIG"`.

The workflow reads `config.get("kaizen_config_path")` in `_execute()` and loads via `load_kaizen_config()`.

**Closes:** REQ-KPI-502

### Tests

| Test | What |
|------|------|
| `test_load_kaizen_config_full` | All fields populated → dataclass correct |
| `test_load_kaizen_config_empty` | Empty JSON → defaults |
| `test_prompt_suffix_applied` | Mock agent, verify prompt includes suffix |
| `test_threshold_override` | Config override → assess uses new threshold |

---

## Phase 3: Pipeline Integration

**Goal:** Plan ingestion communicates seed quality downstream. Contractor can gate on quality score.

**Estimated scope:** ~80 lines SDK + ~30 lines cap-dev-pipe + ~50 lines tests.

**Depends on:** Phase 0 (seed quality score).

### Step 1: Inject `_ingestion_quality` into emitted seed

**File:** `plan_ingestion_workflow.py` → `_phase_emit()`

After the context seed dict is assembled (before `_validate_context_seed` and write), inject the quality metadata:

```python
# In _phase_emit, after seed_dict is fully assembled:
if diag is not None:
    seed_dict["_ingestion_quality"] = {
        "seed_quality_score": diag.seed_quality_score,
        "features_extracted": diag.phases.get("parse", {}).get("quality_signals", {}).get("features_extracted", 0),
        "multi_file_violations": diag.phases.get("parse", {}).get("quality_signals", {}).get("multi_file_features", 0),
        "code_extraction_fallbacks": sum(
            1 for p in diag.phases.values() if p.code_extraction_fallback
        ),
        "route_margin": diag.phases.get("assess", {}).get("quality_signals", {}).get("route_margin", 0),
        "field_coverage_warnings": diag.quality_warnings,
        "diagnostic_report_path": "plan-ingestion-diagnostic.json",
    }
```

**Threading:** The `IngestionDiagnostic` object must be passed into `_phase_emit()` or be available on `self`. Simplest: compute diagnostics before emit and pass as a parameter. This requires reordering — diagnostic assembly moves from "after emit" to "before emit, after transform+refine."

**Alternative:** Compute quality signals independently (they only need `parsed_plan`, `complexity`, and `seed_dict` — all available before emit), then inject. The full diagnostic report is written after emit as before.

**Closes:** REQ-KPI-600

### Step 2: Quality gate in `run-cap-delivery.sh`

**File:** `cap-dev-pipe/run-cap-delivery.sh`

After plan ingestion completes and before contractor invocation, check the seed quality:

```bash
# After plan ingestion, before contractor
SEED_FILE="$OUTPUT_DIR/artisan-context-seed.json"
if [ -f "$SEED_FILE" ]; then
    QUALITY_CHECK=$(python3 -c "
import json, sys
seed = json.loads(open('$SEED_FILE').read())
q = seed.get('_ingestion_quality', {})
score = q.get('seed_quality_score', 1.0)
threshold = float(sys.argv[1])
if score < threshold:
    warnings = q.get('field_coverage_warnings', [])
    print(f'WARN|{score:.2f}|{\";\".join(warnings)}')
else:
    print('OK')
" "${SEED_QUALITY_THRESHOLD:-0.5}")

    if [[ "$QUALITY_CHECK" == WARN* ]]; then
        IFS='|' read -r _ SCORE WARNINGS <<< "$QUALITY_CHECK"
        echo ""
        echo "⚠ Plan ingestion seed quality score: $SCORE (threshold: ${SEED_QUALITY_THRESHOLD:-0.5})"
        echo "  Warnings: $WARNINGS"
        echo ""
        read -p "  Continue to contractor? [y/N] " CONFIRM
        if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
            echo "Aborted by operator."
            exit 1
        fi
    fi
fi
```

**Closes:** REQ-KPI-601

### Step 3: Archive diagnostic in run directory

**File:** `cap-dev-pipe/run-plan-ingestion.sh` (or `run-atomic.sh` Phase 5)

After plan ingestion completes, copy diagnostic to the run archive:

```bash
# Archive diagnostic report
DIAG_FILE="$OUTPUT_DIR/plan-ingestion-diagnostic.json"
if [ -f "$DIAG_FILE" ] && [ -n "$RUN_DIR" ]; then
    cp "$DIAG_FILE" "$RUN_DIR/"
fi
```

**Closes:** REQ-KPI-102

### Tests

| Test | What |
|------|------|
| `test_ingestion_quality_in_seed` | Emitted seed contains `_ingestion_quality` block |
| `test_ingestion_quality_score_matches` | Score in seed matches independently computed score |
| `test_quality_gate_passes_high_score` | Score 0.9, threshold 0.5 → no warning |
| `test_quality_gate_warns_low_score` | Score 0.3, threshold 0.5 → warning message |

---

## Dependency Graph

```
Phase 0 ──────────┬──→ Phase 2 (needs diagnostic reports)
                   │
                   └──→ Phase 3 (needs quality score)

Phase 1 ──────────────→ (independent, can parallel with P0)
```

---

## Implementation Order (Recommended)

| Order | What | Why First |
|-------|------|-----------|
| 1 | P0 Steps 1–5 | Diagnostic dataclass + quality metrics — foundation for everything |
| 2 | P0 Steps 6–8 | Wire into `_execute()` — makes diagnostics live |
| 3 | P0 Tests | Verify foundation before building on it |
| 4 | P1 Steps 1–2 | Prompt capture — directly addresses the observed warning |
| 5 | P1 Tests | Verify capture works |
| 6 | P2 Steps 1–4 | Cross-run analysis + kaizen config — enables the feedback loop |
| 7 | P3 Steps 1–3 | Pipeline integration — connects plan ingestion to downstream |

**Checkpoint after P0+P1:** Run plan ingestion on a real plan. Verify diagnostic JSON is written, quality score is reasonable, and prompts are captured with `--kaizen`. This validates the foundation before investing in cross-run tooling.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Diagnostic assembly adds latency | Low | Low | All computations are O(N) over features list; JSON write is advisory |
| `_validate_seed_field_coverage` changes break quality score | Medium | Medium | Pin the 6-field check count as a constant; add regression test |
| Kaizen prompt files leak sensitive plan content | Medium | High | Gate behind `--kaizen` flag (opt-in); document in README |
| Cross-run script finds no diagnostic files (pre-P0 runs) | High | Low | Script gracefully skips runs without diagnostic files; warns on stderr |
| Quality gate blocks pipeline on borderline seeds | Medium | Medium | Default threshold 0.5 is conservative; operator can override with `SEED_QUALITY_THRESHOLD` env var |

---

## Success Metrics

After P0+P1, verify:
1. `plan-ingestion-diagnostic.json` is written for every run (success and failure)
2. `seed_quality_score` correlates with downstream contractor success (manual validation on 3+ runs)
3. `code_extraction_fallback: true` correctly identifies the "No code blocks found" warning scenario
4. `kaizen-prompts/` directory contains prompt+response pairs when `--kaizen` is active

After P2:
5. Trend script shows improvement after a prompt suffix fix for the code-fence issue
6. Kaizen config successfully overrides complexity threshold

After P3:
7. Quality gate fires on a deliberately thin seed (missing descriptions)
8. Downstream contractor reads `_ingestion_quality` from seed (even if it doesn't act on it yet)
