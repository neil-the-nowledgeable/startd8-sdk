# Observability Artifact Validation — Implementation Plan

> **Version:** 1.0.0
> **Date:** 2026-03-21
> **Requirements:** [KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md](./KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md) v1.1.0
> **Scope:** REQ-KZ-OBS-700–730 (Layer 7: validation, repair, semantic checks, scoring)

---

## Root Cause Discovery

Before planning implementation, the planning process exposed the **actual root cause** of the SLO target=99.0 bug:

**The `--manifest` flag is not passed to `generate_observability_artifacts.py` by the pipeline.** The `.contextcore.yaml` manifest HAS `spec.requirements.availability: 99.9` (confirmed in run-093). But `load_business_context()` receives `manifest_path=None`, so `BusinessContext.availability` is `None`, and `_resolve_threshold()` falls back to `_DEFAULT_THRESHOLDS["availability"] = "99"`.

**This means the SLO target bug is NOT a generation logic error — it's a pipeline wiring gap.** The fix is passing `--manifest` to the generation script, not rewriting the generator. A "repair step" that reads the manifest and overwrites the SLO target would be working around a wiring bug.

**Quick Win discovered:** Fix the pipeline to pass `--manifest` and the SLO target bug disappears — no new code in the SDK. The repair step (OBS-710a) becomes a safety net for edge cases, not the primary fix.

---

## What Already Exists vs. What's Needed

| Capability | Code Gen Pipeline | Observability Artifacts | Gap |
|-----------|------------------|------------------------|-----|
| Structural validation | `validate_syntax()` per language | `yaml.safe_load()` (implicit — YAML parse failure = exception) | No explicit validation result |
| Semantic checks | `run_semantic_checks()` (4 Python, 8+ C#) | Zero | **Complete gap** |
| Repair pipeline | `repair/orchestrator.py` (fence strip, AST, lint, import) | Zero | **Complete gap** |
| Quality scoring | `compute_disk_quality_score()` (5 components) | Zero | **Complete gap** |
| Quality gate | Anzen gate (Security Prime) | Zero | **Complete gap** |
| Postmortem | Per-feature score in `prime-postmortem-report.json` | Zero for artifacts | **Complete gap** |
| Non-service filtering | N/A | `_is_non_service_entry()` — **EXISTS but wasn't installed** | Pipeline install gap (now fixed) |
| Manifest value consumption | N/A | `_resolve_threshold()` — **EXISTS but `--manifest` not passed** | Pipeline wiring gap |

---

## Phase 0: Pipeline Wiring Fixes (0 lines of SDK code)

These are NOT SDK changes — they're pipeline script fixes. But they resolve the two highest-impact issues.

**Fix A: Pass `--manifest` to `generate_observability_artifacts.py`**

The pipeline script that calls the artifact generator needs to pass `--manifest /path/to/.contextcore.yaml`. This makes `BusinessContext.availability = "99.9"` instead of `None` → default `"99"`.

**Fix B: Reinstall SDK (done)**

The phantom service filtering and Security Prime are now installed on system Python 3.14. The next run will filter all 7 phantoms.

**These two fixes alone change the grade from D+ to B+** — phantom filtering eliminates 21 worthless artifacts, and manifest wiring fixes the SLO target mismatch.

---

## Phase 1: Validators (~200 lines)

Create `src/startd8/validators/observability_artifact_checks.py` with three validation functions matching the requirements checklists.

```
src/startd8/validators/observability_artifact_checks.py
├── validate_dashboard(yaml_content, file_path) → DashboardValidationResult
├── validate_alerts(yaml_content, file_path) → AlertValidationResult
├── validate_slo(yaml_content, file_path, manifest_availability) → SloValidationResult
└── validate_artifact(yaml_content, file_path, artifact_type, ...) → dispatcher
```

Each validator returns a result dataclass with `checks_passed`, `checks_total`, `issues[]`.

**Implementation approach:** Pure functions. Each takes YAML content (string), calls `yaml.safe_load()`, checks the structural + semantic criteria from REQ-KZ-OBS-100/101/102/200/201/202, returns a result. No LLM calls. No external tool dependencies. Just YAML parsing + dict key checks.

**Quick win insight:** The validators can also be used retroactively — run them against run-093 artifacts to produce scores without re-running the pipeline. This validates the scoring formula against known outputs.

---

## Phase 2: Repair Steps (~100 lines)

Add repair functions to `observability_artifact_checks.py` (or a separate `observability_artifact_repair.py`):

```
├── repair_slo_target(yaml_dict, manifest_availability) → yaml_dict
├── repair_metric_names(yaml_dict) → yaml_dict  # OTel→Prometheus
├── repair_gridpos(yaml_dict) → yaml_dict        # inject default layout
├── repair_bucket_suffix(yaml_dict) → yaml_dict   # _bucket in histogram_quantile
```

Each is idempotent. Each takes a parsed YAML dict and returns a fixed dict. Applied BEFORE validation (so repaired artifacts pass validation).

**Quick win insight:** `repair_slo_target` is the safety net for when `--manifest` isn't passed. But with Fix A (Phase 0), it should rarely fire. `repair_metric_names` uses the existing `_otel_to_prom()` function in `artifact_generator.py` — no new conversion logic needed.

---

## Phase 3: Wire into Generator (~50 lines)

Modify `generate_observability_artifacts()` in `artifact_generator.py` to:
1. After each `generate_*()` call, run the repair steps
2. After repair, run the validator
3. Attach validation result to `ArtifactResult`
4. Log warnings for validation issues
5. In `--strict` mode, set `status="error"` for validation failures

**Insertion point:** Lines 941–980 of `artifact_generator.py` — the per-service loop. After each `generate_*()` returns an `ArtifactResult`, add:

```python
# Repair + validate
result = _repair_and_validate(result, business)
```

---

## Phase 4: Quality Scoring (~80 lines)

Add `compute_artifact_quality()` that applies the scoring formulas from REQ-KZ-OBS-300/301/302/303:

```
├── compute_dashboard_score(validation_result) → float
├── compute_alert_score(validation_result) → float
├── compute_slo_score(validation_result) → float
├── compute_service_composite(dashboard, alert, slo) → float
```

Write results to `{output_dir}/observability-quality.json`. Print summary in the generation script.

---

## Phase 5: Postmortem Integration (~50 lines)

Modify `kaizen-metrics.json` write in `generate_observability_artifacts.py` to include the `observability_artifacts` section per REQ-KZ-OBS-500. Consumed by existing trend scripts.

---

## Plan-Derived Insights → Requirements Reflection

### Insight 1: The SLO target bug is a wiring gap, not a generator bug

The requirements (OBS-710a) specify a repair step that overwrites SLO targets from the manifest. But the root cause is that the manifest isn't passed to the generator. The repair step is a safety net, not the primary fix.

**Requirements impact:** Add a new requirement:

> **REQ-KZ-OBS-704: Manifest Path Propagation**
> The pipeline script that invokes `generate_observability_artifacts.py` MUST pass `--manifest` pointing to `.contextcore.yaml`. Without this, `BusinessContext` falls back to hardcoded defaults (availability=99), producing systematically wrong SLO targets. This is a P0 pipeline wiring requirement, not an SDK validation requirement.

### Insight 2: Validators should work retroactively

The validators are pure functions that take YAML content. They can be run against ALREADY-GENERATED artifacts from prior runs. This means we can:
1. Score run-092 and run-093 retroactively
2. Validate that the scoring formula produces expected grades
3. Build a baseline BEFORE any generator fixes

**Requirements impact:** Add to verification strategy:

> **REQ-KZ-OBS-705: Retroactive Validation**
> Validators MUST accept YAML content as input (not file paths only). This enables retroactive scoring of prior run artifacts and A/B comparison across generator versions.

### Insight 3: The repair pipeline should be optional and auditable

Code generation repair is wired deep into `integration_engine.py`. Observability artifact repair should be simpler — repair functions called in the generator before write. No separate orchestrator needed. But repairs MUST be logged and trackable.

**Requirements impact:** Clarify OBS-710e:

> OBS-710e (revised): Repair steps run inline in the generator loop (not via a separate orchestrator). Each repair that modifies content SHALL log at INFO with the field changed and old→new values. ArtifactResult SHALL gain a `repairs_applied: List[str]` field tracking which repairs fired.

### Insight 4: `ArtifactResult` needs validation + repair fields

The current `ArtifactResult` has `status`, `content`, `derivations`, `error_message`. It needs:
- `validation: Optional[dict]` — validation result
- `repairs_applied: List[str]` — which repairs fired
- `quality_score: Optional[float]` — per-artifact score

**Requirements impact:** Add:

> **REQ-KZ-OBS-706: ArtifactResult Extension**
> `ArtifactResult` SHALL gain: `validation` (dict from validation result), `repairs_applied` (list of repair step names that modified content), `quality_score` (float 0.0–1.0, None if not computed).

### Insight 5: The generator already has the metric name converter

`_otel_to_prom()` (line 356) already converts OTel dot notation to Prometheus underscore notation. The repair step (OBS-710b) just needs to call this existing function on metric names found in artifact YAML. No new conversion logic.

**Requirements impact:** Note in OBS-710b:

> OBS-710b (revised): Uses the existing `_otel_to_prom()` function in `artifact_generator.py`. No new conversion logic needed.

### Insight 6: Phase 0 (pipeline wiring) delivers 80% of the value

The phantom filtering code exists. The manifest reading code exists. The SLO target resolution code exists. The only failures are:
1. SDK wasn't installed on the right Python (now fixed)
2. `--manifest` wasn't passed (pipeline wiring fix)

**These two non-code fixes change the grade from D+ to B+.** Phases 1–5 (validators, repair, scoring) take it from B+ to A. But Phase 0 is 80% of the improvement for 0% of the code.

**Requirements impact:** Phase 0 should be called out as the critical path. Add:

> **REQ-KZ-OBS-700a (P0 — Quick Win):** Before implementing validation/repair/scoring, verify that:
> (a) `generate_observability_artifacts.py` receives `--manifest` pointing to `.contextcore.yaml`
> (b) The SDK is installed from the latest source (phantom filtering + Security Prime active)
> These two wiring fixes resolve the phantom service and SLO target mismatch issues without any new code.

### Insight 7: Alert count adequacy reveals a generator gap, not just a scoring gap

The alert generator produces exactly 1 rule per service (latency only). The scoring formula (OBS-301 `rule_coverage`) would score this 0.33 when 3 rules are expected. But the scoring doesn't FIX the gap — it just measures it. The generator itself needs to produce error rate and availability alerts.

This is a generator logic gap, not a validator/repair gap. The repair pipeline can't add missing alerts — it can only fix existing ones.

**Requirements impact:** This is out of scope for OBS-710 (repair) but should be tracked:

> **REQ-KZ-OBS-711: Generator Alert Coverage (Future)**
> The alert generator SHOULD produce at minimum: latency P99 alert + error rate alert + availability alert when the manifest specifies `availability` requirement. This is a generator enhancement, not a repair step. Tracked for future implementation.

---

## Summary: Implementation Priorities

| Priority | Phase | Effort | Impact | What Changes |
|----------|-------|--------|--------|-------------|
| **P0** | Phase 0: Pipeline wiring | 0 SDK lines | D+ → B+ | Pass `--manifest`, confirm SDK installed |
| **P1** | Phase 1: Validators | ~200 lines | Visibility | Structural + semantic validation with scored results |
| **P2** | Phase 3: Wire into generator | ~50 lines | Enforcement | Validation runs automatically on every generation |
| **P2** | Phase 2: Repair steps | ~100 lines | Quality | SLO target, metric names, gridPos, bucket suffix |
| **P3** | Phase 4: Scoring | ~80 lines | Measurement | Per-artifact + composite scores |
| **P3** | Phase 5: Postmortem | ~50 lines | Kaizen loop | Scores in kaizen-metrics.json, trends |
| **Future** | Generator alert coverage | ~100 lines | Completeness | Error rate + availability alerts |

**Total: ~480 lines of new SDK code across Phases 1–5.**
**Phase 0 (pipeline wiring) delivers the most impact with 0 SDK lines.**
