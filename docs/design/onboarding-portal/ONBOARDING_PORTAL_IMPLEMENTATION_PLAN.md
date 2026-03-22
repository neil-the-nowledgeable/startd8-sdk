# Onboarding Portal — Implementation Plan

> **Version:** 2.0.0
> **Date:** 2026-03-21
> **Requirements:** [ONBOARDING_PORTAL_REQUIREMENTS.md](./ONBOARDING_PORTAL_REQUIREMENTS.md) v0.2.0
> **Estimated:** ~260 lines across 4 phases
> **Accidental Complexity Audit:** 3 items identified in existing code, distilled during implementation

---

## Accidental Complexity in Existing Code

The plan touches `artifact_generator.py` (~1100 lines). Before adding portal code, three patterns of accidental complexity should be addressed:

### AC-1: Copy-Pasted Try/Except Blocks in Orchestrator

Lines 1036–1081 repeat the EXACT same pattern 3 times:

```python
try:
    result = generate_X(service, business)
    result = _repair_and_validate(result, business)
    report.artifacts.append(result)
except Exception:
    logger.exception("X generation failed for %s", service.service_id)
    report.artifacts.append(ArtifactResult(..., status="error"))
```

Adding a 4th copy for the portal would make this worse.

**Distill:** Extract a `_generate_one()` helper:

```python
def _generate_one(gen_fn, service, business, artifact_type, output_prefix):
    try:
        result = gen_fn(service, business)
        return _repair_and_validate(result, business)
    except Exception:
        logger.exception("%s generation failed for %s", artifact_type, service.service_id)
        return ArtifactResult(
            artifact_type=artifact_type, service_id=service.service_id,
            output_path=f"{output_prefix}/{service.service_id}-{output_prefix}.yaml",
            status="error", error_message="Generation raised exception",
        )
```

Then the loop becomes:

```python
_GENERATORS = [
    (generate_alert_rules, "alert_rule", "alerts"),
    (generate_dashboard_spec, "dashboard_spec", "dashboards"),
    (generate_slo_definitions, "slo_definition", "slos"),
]

for service in services:
    for gen_fn, artifact_type, prefix in _GENERATORS:
        report.artifacts.append(_generate_one(gen_fn, service, business, artifact_type, prefix))
```

**Lines saved:** ~30. More importantly, adding the portal doesn't add another copy-paste block.

### AC-2: Growing elif Chain in `_repair_and_validate()`

Currently 3 branches (dashboard, alert, slo). Adding portal makes 4. Each branch has a different import + call + optional content update pattern.

**Distill:** The validation result attachment (lines 979–999) is IDENTICAL for all branches. Only the validator call differs. Extract a dispatch dict:

```python
_VALIDATORS = {
    "dashboard_spec": lambda content, path, avail: validate_dashboard(content, path, autofix=True),
    "alert_rule": lambda content, path, avail: validate_alerts(content, path, manifest_availability=avail),
    "slo_definition": lambda content, path, avail: validate_slo(content, path, manifest_availability=avail, autofix=True),
    "portal": lambda content, path, avail: validate_portal(content, path),
}
```

Then `_repair_and_validate()` becomes ~15 lines instead of ~50.

**Lines saved:** ~35, and adding new artifact types is a 1-line dict entry.

### AC-3: Portal HTML Rendering in a YAML Generator Module

`artifact_generator.py` generates YAML artifacts. Adding 150 lines of HTML template rendering (with CSS design tokens) is a different concern.

**Distill:** Put portal rendering in its own module: `observability/portal.py`. The orchestrator calls it; the HTML rendering lives separately. This keeps `artifact_generator.py` focused on YAML.

---

## Phase 0: Refactor — Distill Accidental Complexity (~-30 lines net)

Before adding portal code, refactor the orchestrator:

1. Extract `_generate_one()` helper (AC-1)
2. Replace 3 copy-pasted try/except blocks with `_GENERATORS` loop
3. Simplify `_repair_and_validate()` dispatch (AC-2)

**This is a refactor-only phase.** Zero new functionality. All existing tests pass unchanged. Net reduction in lines.

**Done when:** `generate_observability_artifacts()` orchestrator loop is ~10 lines instead of ~45.

---

## Phase 1: Portal Module — Service Inventory (~80 lines)

### File: `src/startd8/observability/portal.py` (NEW)

```python
def generate_portal(
    business: BusinessContext,
    services: List[ServiceHints],
    report: GenerationReport,
    metadata: Dict[str, Any],
) -> ArtifactResult:
    """Generate onboarding portal HTML from pipeline context (REQ-OBP-100)."""
```

v0 quick win (OBP-105a): ONLY project overview + service inventory. ~80 lines:
- `_render_html_shell()` — doctype, CSS design tokens (copy from harbor tour), nav
- `_render_project_overview()` — project ID, criticality badge, timestamp
- `_render_service_inventory()` — filtered service table: ID, transport, language
- `_render_placeholder()` — "Section available in future version" for unimplemented sections

Services are FILTERED using the same `_is_non_service_entry()` from `artifact_generator.py`.

**Done when:** `portal/test-portal.html` opens in browser showing 2 real services (not 9).

---

## Phase 2: Content Sections (~100 lines)

Add to `portal.py`:

- `_render_objectives()` — from `metadata["objectives"]` (plan-level intent with key results). Primary SLO source per OBP-105c.
- `_render_alert_inventory()` — from `report.artifacts` where `artifact_type="alert_rule"`. Parse YAML content for rule names + severity.
- `_render_dashboard_links()` — relative `../dashboards/{svc}-dashboard-spec.yaml` links
- `_render_communication_graph()` — HTML table from `service_communication_graph.services`. "No inter-service dependencies detected" when no edges.
- `_render_provenance()` — run ID, timestamp, duration from `run-provenance.json`

Each renderer returns an HTML string or empty string (graceful degradation). Main function assembles non-empty sections.

**Done when:** Portal shows objectives, alerts, dashboard links, communication table (or placeholder), provenance.

---

## Phase 3: Quality + Security Sections (~50 lines)

Add to `portal.py`:

- `_render_quality_section()` — reads `quality_summary` from `observability-manifest.yaml` (already computed by Phase 2 validation). Does NOT re-compute.
- `_render_security_section()` — reads `security` from `kaizen-metrics.json`. Shows aggregate score, injection blocked, credential blocked.

Both return empty string when data unavailable.

**Done when:** Portal shows quality scores when metrics exist, omits gracefully when they don't.

---

## Phase 4: Validation + Wiring (~30 lines)

### In `validators/observability_artifact_checks.py`:

```python
def validate_portal(content: str, file_path: str = "") -> PortalValidationResult:
    """Validate portal HTML — checks section anchors and service count."""
```

Checks: HTML non-empty, contains `id="project-overview"`, `id="service-inventory"`, service count matches filtered `instrumentation_hints`.

### In `artifact_generator.py`:

Add `"portal"` entry to the `_VALIDATORS` dispatch dict (from AC-2 refactor).

### In `generate_observability_artifacts()`:

After the per-service artifact loop, before `_write_artifacts()`:

```python
if portal_enabled:
    from startd8.observability.portal import generate_portal
    portal_result = generate_portal(business, services, report, metadata)
    portal_result = _repair_and_validate(portal_result, business)
    report.artifacts.append(portal_result)
```

### In `scripts/generate_observability_artifacts.py`:

Add `--portal` flag (opt-in for v1 per OBP-103d).

**Done when:** `--portal` flag generates portal, quality score appears in manifest.

---

## File Changes

| Phase | File | Change | Lines |
|-------|------|--------|-------|
| 0 | `artifact_generator.py` | Extract `_generate_one()`, simplify orchestrator loop + `_repair_and_validate()` dispatch | ~-30 net |
| 1 | `observability/portal.py` (NEW) | `generate_portal()` + service inventory renderer | ~80 |
| 2 | `observability/portal.py` | Add 5 content section renderers | ~100 |
| 3 | `observability/portal.py` | Add quality + security renderers | ~50 |
| 4 | `validators/observability_artifact_checks.py` | Add `validate_portal()` | ~20 |
| 4 | `artifact_generator.py` | Add portal to dispatch dict + orchestrator call | ~10 |
| 4 | `scripts/generate_observability_artifacts.py` | Add `--portal` flag | ~5 |
| **Total** | | | **~235 new + ~30 refactored** |

---

## Key Design Decisions

1. **Separate `portal.py` module** — HTML rendering doesn't belong in a YAML generator. Clean separation of concerns.
2. **Phase 0 refactor FIRST** — Distill existing accidental complexity before adding new code. The portal benefits from the cleaner orchestrator.
3. **v0 quick win = service inventory only** — 80 lines validates the entire template + wiring chain. Additional sections are purely additive.
4. **Each section renderer returns a string** — Composable, independently testable, gracefully degradable (empty string = section omitted).
5. **Opt-in for v1** — `--portal` flag, not `--skip-portal`. Flip after 5+ successful runs.
