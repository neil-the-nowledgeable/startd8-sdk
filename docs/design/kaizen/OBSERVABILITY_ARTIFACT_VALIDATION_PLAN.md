# Observability Artifact Validation — Implementation Plan

> **Version:** 2.0.0
> **Date:** 2026-03-21
> **Requirements:** [KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md](./KAIZEN_OBSERVABILITY_ARTIFACT_REQUIREMENTS.md) v1.2.0
> **Scope:** REQ-KZ-OBS-700–730 (validation, repair, semantic checks, scoring)

---

## Root Cause Update

Investigation revealed that run-093's SLO target=99.0 bug was caused by running the OLD installed SDK, NOT a wiring or code gap:

- Pipeline `run-atomic.sh` line 474 passes `--manifest` correctly
- `.contextcore.yaml` exists with `spec.requirements.availability: 99.9`
- `load_business_context()` correctly reads `99.9` with current code
- Run-093 used the pre-reinstall SDK — now fixed on system Python 3.14
- Phantom filtering code (`_is_non_service_entry()`) also exists and works — just wasn't installed

**The next run will produce correct SLO targets and zero phantoms without any code changes.**

What remains is building the validation/repair/scoring infrastructure that doesn't exist yet — observability artifacts currently have zero quality gates.

---

## What Already Exists

| Capability | Status | Where |
|-----------|--------|-------|
| Phantom service filtering | **EXISTS** (now installed) | `artifact_generator.py:_is_non_service_entry()` |
| Manifest value reading | **EXISTS** (now installed) | `artifact_generator.py:load_business_context()` |
| OTel→Prometheus name conversion | **EXISTS** | `artifact_generator.py:_prom_name()` |
| `--manifest` passed by pipeline | **EXISTS** | `run-atomic.sh:474` |
| YAML generation | **EXISTS** | 3 generator functions |
| YAML structural validation | **DOES NOT EXIST** |  |
| Semantic checks (RED, alignment) | **DOES NOT EXIST** |  |
| Repair steps | **DOES NOT EXIST** |  |
| Quality scoring | **DOES NOT EXIST** |  |
| Postmortem integration | **DOES NOT EXIST** |  |

---

## Phase 1: Validators + Repair (~250 lines)

### File: `src/startd8/validators/observability_artifact_checks.py`

New file with pure validation + repair functions.

```python
# Validators — return result dataclasses
def validate_dashboard(content: str, file_path: str) -> DashboardValidationResult
def validate_alerts(content: str, file_path: str) -> AlertValidationResult
def validate_slo(content: str, file_path: str, manifest_availability: float = None) -> SloValidationResult

# Repair — take parsed dict, return fixed dict (idempotent)
def repair_slo_target(slo_dict: dict, manifest_availability: float) -> Tuple[dict, List[str]]
def repair_gridpos(dashboard_dict: dict) -> Tuple[dict, List[str]]
def repair_bucket_suffix(dashboard_dict: dict) -> Tuple[dict, List[str]]
def repair_metric_names(artifact_dict: dict) -> Tuple[dict, List[str]]

# Scoring — apply formulas from REQ-KZ-OBS-300–303
def compute_dashboard_score(result: DashboardValidationResult) -> float
def compute_alert_score(result: AlertValidationResult) -> float
def compute_slo_score(result: SloValidationResult) -> float
def compute_service_composite(dashboard: float, alert: float, slo: float) -> float
```

Each repair function returns `(fixed_dict, repairs_applied_list)`. Each validator takes YAML content as string (REQ-KZ-OBS-705a — enables retroactive validation).

### Result Dataclasses

Use simple frozen dataclasses — same pattern as `SemanticIssue` in code generation validators:

```python
@dataclass(frozen=True)
class ObservabilityIssue:
    check: str      # e.g. "OBS-100d"
    severity: str   # "error", "warning", "info"
    message: str

@dataclass
class DashboardValidationResult:
    file_path: str
    yaml_valid: bool
    panel_count: int
    red_coverage: float  # 0.0–1.0 (R/E/D signals present / 3)
    checks_passed: int
    checks_total: int
    issues: List[ObservabilityIssue]

@dataclass
class AlertValidationResult:
    file_path: str
    yaml_valid: bool
    rule_count: int
    rule_coverage: float  # actual/expected rules
    checks_passed: int
    checks_total: int
    issues: List[ObservabilityIssue]

@dataclass
class SloValidationResult:
    file_path: str
    yaml_valid: bool
    target_value: Optional[float]
    target_matches_manifest: bool
    checks_passed: int
    checks_total: int
    issues: List[ObservabilityIssue]
```

---

## Phase 2: Wire into Generator (~50 lines)

### Modify: `src/startd8/observability/artifact_generator.py`

**a) Extend ArtifactResult** (REQ-KZ-OBS-706):

```python
@dataclass
class ArtifactResult:
    # ... existing fields ...
    validation: Optional[Dict] = None       # validation result as dict
    repairs_applied: List[str] = field(default_factory=list)
    quality_score: Optional[float] = None
```

**b) Add repair+validate call in the per-service loop** (~30 lines):

After each `generate_*()` call in `generate_observability_artifacts()`, call:

```python
def _repair_and_validate(result: ArtifactResult, business: BusinessContext) -> ArtifactResult:
    """Apply repairs, validate, compute score. Modifies result in-place."""
    if result.status != "generated" or not result.content:
        return result

    try:
        from startd8.validators.observability_artifact_checks import (
            validate_dashboard, validate_alerts, validate_slo,
            repair_slo_target, repair_gridpos, repair_bucket_suffix,
            compute_dashboard_score, compute_alert_score, compute_slo_score,
        )
    except ImportError:
        return result  # validators not available — degrade gracefully

    parsed = yaml.safe_load(result.content)
    repairs = []

    # Apply repairs based on artifact type
    if result.artifact_type == "dashboard_spec":
        parsed, r = repair_gridpos(parsed)
        repairs.extend(r)
        parsed, r = repair_bucket_suffix(parsed)
        repairs.extend(r)
        result.content = yaml.dump(parsed, default_flow_style=False)
        vr = validate_dashboard(result.content, result.output_path)
        result.quality_score = compute_dashboard_score(vr)
    elif result.artifact_type == "alert_rule":
        vr = validate_alerts(result.content, result.output_path)
        result.quality_score = compute_alert_score(vr)
    elif result.artifact_type == "slo_definition":
        avail = float(business.availability) if business.availability else None
        parsed, r = repair_slo_target(parsed, avail)
        repairs.extend(r)
        result.content = yaml.dump(parsed, default_flow_style=False)
        vr = validate_slo(result.content, result.output_path, avail)
        result.quality_score = compute_slo_score(vr)

    result.repairs_applied = repairs
    result.validation = dataclasses.asdict(vr) if vr else None
    # Log repairs and issues
    ...
    return result
```

---

## Phase 3: Quality Report + Postmortem (~80 lines)

**a) Write `observability-quality.json`** after all artifacts generated:

```python
quality_report = {
    "services": {svc_id: {
        "dashboard_score": ..., "alert_score": ..., "slo_score": ...,
        "composite": compute_service_composite(...),
    }},
    "aggregate_score": min(composites),  # weakest link
    "phantom_services_detected": ...,
    "repairs_applied_total": ...,
}
```

**b) Print quality summary** in `generate_observability_artifacts.py` script output.

**c) Append to `kaizen-metrics.json`** (REQ-KZ-OBS-500):

```python
existing["observability_artifacts"] = {
    "avg_dashboard_score": ...,
    "avg_alert_score": ...,
    "avg_slo_score": ...,
    "avg_composite_score": ...,
    "phantom_services_detected": ...,
    "services_evaluated": ...,
}
```

---

## Dependency Graph

```
Phase 1: Validators + Repair (~250 lines, 1 new file)
  │
  └──▶ Phase 2: Wire into Generator (~50 lines, modify artifact_generator.py)
        │
        └──▶ Phase 3: Quality Report + Postmortem (~80 lines)
```

**Total: ~380 lines across 1 new file + 1 modified file.**

---

## Validation Milestones

| After Phase | Validation | Expected Result |
|-------------|-----------|-----------------|
| **1** | Run validators retroactively on run-093 artifacts | cartservice dashboard: B- (missing RED, no gridPos), SLO: C+ (target matches NOW), alerts: B+ |
| **2** | Next pipeline run with generator wiring | Artifacts written with `validation` + `quality_score` fields in manifest |
| **3** | Quality report in run output | `observability-quality.json` with per-service scores, `kaizen-metrics.json` with `observability_artifacts` section |

---

## What We Chose NOT to Build (and Why)

| Capability | Why Not Now |
|-----------|-------------|
| Separate repair orchestrator | Repair runs inline — 4 simple functions, no orchestration needed |
| LLM-based artifact review | All checks are deterministic YAML analysis — LLM adds cost without value |
| Alert count generator fix (OBS-711) | Validator measures the gap; generator fix is a separate feature |
| Standalone validation script (OBS-705b) | Phase 1 validators are importable — a script is trivial to add later |
| Cross-artifact consistency checks (OBS-400–403) | Build after per-artifact validation is stable |
