# Onboarding Portal — Implementation Plan

> **Version:** 1.0.0
> **Date:** 2026-03-21
> **Requirements:** [ONBOARDING_PORTAL_REQUIREMENTS.md](./ONBOARDING_PORTAL_REQUIREMENTS.md) v0.1.0
> **Estimated:** ~280 lines across 4 phases

---

## Data Available

From `onboarding-metadata.json` (41 fields, confirmed in run-093):

| Data | Source Key | Portal Section |
|------|-----------|----------------|
| Project ID | `project_id` | Project Overview |
| Services (9 entries, 2 real) | `instrumentation_hints` | Service Inventory |
| Transport per service | `instrumentation_hints.{svc}.transport` | Service Inventory |
| Language per service | `service_communication_graph.services.{svc}.language` | Service Inventory |
| Service calls graph | `service_communication_graph.services` | Communication Graph |
| Objectives + key results | `objectives` (3 items with availability/latency targets) | SLO Summary |
| Derivation rules | `derivation_rules` | Operational Context |
| Generation profile | `generation_profile` | Run Provenance |
| Generated timestamp | `generated_at` | Run Provenance |

From generated artifacts:
- `slos/{svc}-slo.yaml` → SLO targets, windows, indicators
- `alerts/{svc}-alerts.yaml` → Alert names, severities, thresholds
- `dashboards/{svc}-dashboard-spec.yaml` → Dashboard UIDs for linking

From `kaizen-metrics.json` (when present):
- `security` → Security Prime scores
- `observability_artifacts` → Artifact quality scores
- `success_rate`, `total_cost_usd` → Pipeline quality

From `run-provenance.json` (when present):
- Run ID, start time, duration, environment

---

## Design Tokens (from harbor tour exemplars)

```css
--bg: #0f1117;        --surface: #1a1d27;    --surface-2: #232736;
--border: #2e3346;    --text: #e2e4ea;       --text-muted: #8b8fa4;
--accent: #6c8cff;    --accent-dim: #3d5299;
--green: #4ade80;     --amber: #fbbf24;      --red: #f87171;
--cyan: #22d3ee;      --purple: #a78bfa;
```

Single-file, dark theme, responsive, Inter font. No JavaScript frameworks.

---

## Phase 1: Portal Generator (~150 lines)

### What Ships

A `generate_portal()` function in `artifact_generator.py` that produces a self-contained HTML file from pipeline data.

### Implementation

Add to `artifact_generator.py`:

```python
def generate_portal(
    business: BusinessContext,
    services: List[ServiceHints],
    report: GenerationReport,
    metadata: Dict[str, Any],
    kaizen_path: Optional[Path] = None,
    provenance_path: Optional[Path] = None,
) -> ArtifactResult:
    """Generate an onboarding portal HTML from pipeline context (REQ-OBP-100)."""
```

The function builds HTML using f-strings (no template engine dependency). Sections:

1. **Header** — project name, criticality badge, generated timestamp
2. **Service Inventory** — table: service ID, transport badge, language, metric count
3. **SLO Summary** — table: service, target, window, indicator type (from generated SLO artifacts in `report.artifacts`)
4. **Alert Inventory** — table: service, alert name, severity badge, threshold (from generated alert artifacts)
5. **Run Provenance** — run ID, timestamp, pipeline version, duration

### Wiring

In `generate_observability_artifacts()`, after the per-service loop and before `_write_artifacts()`:

```python
# Portal generation (REQ-OBP-103a)
if not skip_portal:
    portal_result = generate_portal(business, services, report, metadata, ...)
    portal_result = _repair_and_validate(portal_result, business)
    report.artifacts.append(portal_result)
```

### Output

`portal/{project_id}-portal.html` — single HTML file, ~5–15KB depending on service count.

### Done When

Portal HTML generated for run-093 data shows: project overview, 2 real services (after phantom filtering), SLO targets, alert inventory, run provenance.

---

## Phase 2: Communication Graph (~50 lines)

### What Ships

A `_render_communication_graph()` helper that turns the `service_communication_graph` dict into an HTML table showing service-to-service dependencies.

### Implementation

```python
def _render_communication_graph(scg: Dict[str, Any]) -> str:
    """Render service communication graph as HTML table."""
    services = scg.get("services", {})
    rows = []
    for svc_id, svc in services.items():
        calls = svc.get("calls_to", [])
        called_by = svc.get("called_by", [])
        lang = svc.get("language", "—")
        rows.append(f"<tr><td>{svc_id}</td><td>{lang}</td>"
                     f"<td>{', '.join(calls) or '—'}</td>"
                     f"<td>{', '.join(called_by) or '—'}</td></tr>")
    ...
```

For v1: HTML table. No SVG, no JavaScript. The graph structure in run-093 has `calls_to` and `called_by` per service — a table is the natural representation.

### Done When

Portal includes a "Service Dependencies" section with a table showing who calls whom.

---

## Phase 3: Quality + Security Sections (~50 lines)

### What Ships

Read `kaizen-metrics.json` (when present) and render:
- **Quality Metrics**: success rate, cost per feature, assembly delta
- **Security Posture**: aggregate security score, injection/credential blocked counts
- **Artifact Quality**: avg dashboard/alert/SLO scores from `observability_artifacts` section

### Implementation

```python
def _render_quality_section(kaizen_path: Optional[Path]) -> str:
    """Render quality + security metrics from kaizen-metrics.json."""
    if not kaizen_path or not kaizen_path.is_file():
        return ""  # Section omitted when no metrics available
    ...
```

### Done When

Portal shows quality metrics when `kaizen-metrics.json` exists, omits the section gracefully when it doesn't.

---

## Phase 4: Portal Validation (~30 lines)

### What Ships

Add `validate_portal()` to `observability_artifact_checks.py`. Checks:
- HTML content is non-empty
- Contains expected section anchors (project-overview, service-inventory, etc.)
- Service count in HTML matches `instrumentation_hints` service count (post-phantom-filtering)

### Wiring

In `_repair_and_validate()`, add `elif result.artifact_type == "portal":` branch.

### Done When

Portal quality score appears in `observability-manifest.yaml` alongside dashboard/alert/SLO scores.

---

## File Changes

| Phase | File | Change |
|-------|------|--------|
| 1 | `observability/artifact_generator.py` | Add `generate_portal()` + wire into orchestrator |
| 1 | `scripts/generate_observability_artifacts.py` | Add `--skip-portal` flag |
| 2 | `observability/artifact_generator.py` | Add `_render_communication_graph()` |
| 3 | `observability/artifact_generator.py` | Add `_render_quality_section()` |
| 4 | `validators/observability_artifact_checks.py` | Add `validate_portal()` |
| 4 | `observability/artifact_generator.py` | Add portal branch in `_repair_and_validate()` |

**Total: ~280 lines across 2 files.**

---

## Quick Win: Generate Portal for Run-093 Retroactively

Before wiring into the pipeline, the portal generator can be tested standalone:

```python
from startd8.observability.artifact_generator import generate_portal
html = generate_portal(business, services, report, metadata)
Path("portal-test.html").write_text(html.content)
# Open in browser → visual validation
```

This validates the HTML template before any pipeline integration.
