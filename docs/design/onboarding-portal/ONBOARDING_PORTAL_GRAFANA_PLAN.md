# Onboarding Portal — Grafana-First Implementation Plan

> **Version:** 2.0.0
> **Date:** 2026-03-23
> **Requirements:** [ONBOARDING_PORTAL_REQUIREMENTS.md](./ONBOARDING_PORTAL_REQUIREMENTS.md) v0.3.0
> **Supersedes:** [ONBOARDING_PORTAL_IMPLEMENTATION_PLAN.md](./ONBOARDING_PORTAL_IMPLEMENTATION_PLAN.md) v2.0.0 (static HTML approach)
> **Key Insight:** The `DashboardCreatorWorkflow` and `/dbrd-cr8r` pipeline — which did not exist when the requirements were drafted (2026-03-21) — provide a direct path to Grafana-native portal generation. Text panels render markdown natively; the portal lives alongside operational dashboards instead of as an external HTML file.

---

## 1. Why Grafana-First

The original plan recommended "Start with static HTML, add Grafana portal as v2." Three capabilities now available change the calculus:

| Capability | What It Enables |
|---|---|
| **`DashboardCreatorWorkflow`** (DC-200) | Declarative YAML spec → Jsonnet → Grafana JSON, including provisioning |
| **`PanelType.TEXT`** with markdown | Portal content sections render natively in Grafana |
| **`layout.auto_group_rows()`** (DC-108) | Collapsible section rows from `group: "+Section Name"` |
| **Dashboard links** with `includeVars`, `keepTime` | Portal → operational dashboard navigation in one click |
| **Batch generation** (`batch.run_batch()`) | Multiple persona portals from one command |

### Grafana vs Static HTML

| Dimension | Static HTML (original plan) | Grafana Dashboard (this plan) |
|---|---|---|
| Hosting | Needs a web server or file:// | Already running Grafana |
| Live metrics | Impossible (static content) | Stat/gauge panels with live PromQL |
| Navigation | External links, new tabs | Dashboard links with variable forwarding |
| Stakeholder access | Share a file URL | Share a Grafana URL (already has auth) |
| Updates | Regenerate file, redistribute | Regenerate + provision (API call) |
| Co-located with dashboards | Separate system | Same sidebar, same theme, same search |
| Offline / no-Grafana | Works | Doesn't work |

**Decision:** Grafana-first via the existing Jsonnet pipeline. Static HTML as a deferred fallback (not in this plan).

---

## 2. Architecture

### 2.1 Portal as DashboardSpec → Jsonnet → Grafana JSON

The portal generator produces a `DashboardSpec` dict — the same model consumed by all `/dbrd-cr8r` dashboards. No new infrastructure. Same pipeline, same mixin, same provisioning, same validation.

```
onboarding-metadata.json
    │
    ├── artifact_generator.py  → alerts/, dashboards/, slos/  (existing)
    │
    └── portal_spec_builder.py (NEW)
            │
            ├── build_portal_spec(business, services, report, metadata)
            │       → DashboardSpec dict
            │
            └── DashboardCreatorWorkflow.run(spec)
                    │  1. Parse spec
                    │  2. Discover mixin (startd8-mixin/ — already in repo)
                    │  3. Enforce UID
                    │  4. Merge config (datasource UIDs, refresh, timezone)
                    │  5. Validate spec
                    │  5.5 Apply layout (auto_group_rows + auto_layout)
                    │  6. Generate Jsonnet (panels.text(), panels.stat(), etc.)
                    │  7. Compile Jsonnet → JSON
                    │  8. Validate JSON
                    │  9. Persist → portal/{project_id}-portal.json
                    │  10. Provision to Grafana (optional)
                    ▼
              Grafana dashboard in "Portal" folder
```

### 2.2 Why Jsonnet (Not Direct JSON)

The `startd8-mixin/` directory already exists in this repo with `vendor/`, `config.libsonnet`, `lib/panels.libsonnet`. The Jsonnet toolchain (`go-jsonnet`) is already installed. Zero setup cost.

Using the Jsonnet path provides:

| Benefit | Details |
|---|---|
| **Config-driven datasource UIDs** | `config.libsonnet` manages datasource references per environment — portal inherits automatically |
| **Shared panel definitions** | `panels.text()`, `panels.stat()`, `panels.gauge()` in `lib/panels.libsonnet` already produce correct Grafana JSON with all required fields (fieldConfig, options, thresholds) |
| **Future `${metrics.*}` references** | When portals evolve to show live operational metrics, config variable interpolation is already available |
| **Mixin integration** | Portal `.libsonnet` can be persisted alongside operational dashboards, included in `make generate`, and tracked in golden file tests |
| **Theme/style inheritance** | Mixin config controls default refresh, timezone, color schemes |

A direct JSON renderer (~120 lines) could be added later for mixin-free environments if needed. The `DashboardSpec` model is the contract — both paths consume it, so `portal_spec_builder.py` wouldn't change.

### 2.3 Insertion Points

```
artifact_generator.py (existing)
  _GENERATORS = [                          # Per-service loop
      (generate_alert_rules, ...),
      (generate_dashboard_spec, ...),
      (generate_slo_definitions, ...),
  ]

  # After per-service loop, before _write_artifacts():
  if portal_enabled:                       # NEW (REQ-OBP-103d: --portal flag)
      from startd8.observability.portal_spec_builder import build_portal_spec
      portal_spec = build_portal_spec(business, services, report, metadata)
      # Route through DashboardCreatorWorkflow for Jsonnet → JSON + provisioning
      portal_result = _generate_portal(portal_spec, output_dir, provision)
      report.artifacts.append(portal_result)
```

---

## 3. Phased Delivery

### Phase 1: Portal Spec Builder — Service Inventory (~120 lines)

**New file:** `src/startd8/observability/portal_spec_builder.py`

**Goal:** Generate a `DashboardSpec` dict with the two most useful sections: Project Overview and Service Inventory.

```python
def build_portal_spec(
    business: BusinessContext,
    services: List[ServiceHints],
    report: GenerationReport,
    metadata: Dict[str, Any],
    *,
    persona: str = "operator",
    provision_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a DashboardSpec dict for the onboarding portal (REQ-OBP-100).

    Returns a dict consumable by DashboardCreatorWorkflow.
    $0.00 — no LLM calls. All content from structured pipeline data.
    """
```

**Panels produced:**

| Panel | Type | Content | Source | Group |
|---|---|---|---|---|
| Project Overview | `text` | Project name, ID, criticality badge, owner, description, generation timestamp | `business` + `report.generated_at` | `+Project Overview` |
| Service Inventory | `text` | Markdown table: Service, Protocol, Language, Metrics, Databases | `services` (filtered, no phantoms) | `+Service Inventory` |
| Service Count | `stat` | Number of real services | Literal PromQL (`vector(N)`) | `+Service Inventory` |
| Artifact Count | `stat` | Alerts + dashboards + SLOs generated | Literal PromQL (`vector(N)`) | `+Service Inventory` |

**Dashboard-level metadata:**

```python
{
    "title": f"{business.project_id} — Onboarding Portal",
    "uid": f"portal-{business.project_id}",
    "description": "Auto-generated onboarding portal from pipeline context",
    "tags": ["portal", "onboarding", business.project_id],
    "links": [
        # Link to each service's generated dashboard
        {"title": f"{svc.service_id} Dashboard",
         "url": f"/d/cc-obs-{svc.service_id}/", ...}
        for svc in services
    ],
}
```

**Section renderers (composable):**

Each `_build_*_panels()` function returns a `List[dict]` (panel spec dicts) or empty list if data is absent:

```python
def _build_project_overview_panels(business, report) -> List[dict]: ...
def _build_service_inventory_panels(services) -> List[dict]: ...
```

**Done when:** `python3 scripts/generate_observability_artifacts.py --portal` produces a Grafana dashboard JSON via `DashboardCreatorWorkflow`, viewable at `http://localhost:3000/d/portal-{project_id}/`.

---

### Phase 2: Content Sections (~100 lines)

Add section builders to `portal_spec_builder.py`:

| Section | Panel Type | Content | Source |
|---|---|---|---|
| **Objectives** | `text` | Markdown table: Objective, Metric Key, Target, Unit | `metadata["objectives"]` (OBP-105c: plan-level intent, primary source) |
| **Alert Inventory** | `text` | Markdown table: Service, Alert Name, Severity, Duration | `report.artifacts` where `artifact_type="alert_rule"` |
| **Dashboard Links** | `text` | Markdown table: Service, Dashboard Link (Grafana URL) | `report.artifacts` where `artifact_type="dashboard_spec"` |
| **Communication Graph** | `text` | Markdown table: Service, Calls To, Called By. "No inter-service dependencies detected" when empty | `metadata["service_communication_graph"]` |
| **Provenance** | `text` | Run ID, timestamp, duration, pipeline version | `metadata` + `report` |

Each renderer:
```python
def _build_objectives_panels(metadata) -> List[dict]:
    objectives = metadata.get("objectives")
    if not objectives:
        return []  # Graceful degradation (OBP-101c)
    ...
```

**Dashboard links use Grafana internal routing:**
```python
{"title": "checkoutservice Dashboard",
 "url": "/d/cc-obs-checkoutservice/",
 "type": "link", "targetBlank": False,
 "includeVars": True, "keepTime": True}
```

**Done when:** Portal shows objectives, alert inventory, dashboard links, communication graph, and provenance.

---

### Phase 3: Live Metrics + Quality (~80 lines)

Add panels that query live data (requires Prometheus/Mimir datasource):

| Panel | Type | Content | Source |
|---|---|---|---|
| **Quality Score** | `gauge` | Composite artifact quality score (0–1) | `report` quality_summary |
| **Artifact Health** | `stat` (repeated) | Per-type: generated / errored / skipped counts | `report.artifacts` aggregation |
| **Security Posture** | `text` | Aggregate security score, injection blocked, credential blocked | `kaizen-metrics.json` security section |
| **Quality Breakdown** | `text` | Avg scores per artifact type, total issues, total repairs | `observability-manifest.yaml` quality_summary |

For quality/security: data comes from optional JSON files read at generation time. Rendered as markdown in text panels (static snapshot at generation time) — NOT live PromQL. This satisfies OBP-101b ($0.00, deterministic).

Optional live panels (when Prometheus available):
```python
def _build_live_metrics_panels(business) -> List[dict]:
    """Optional: live KPI panels. Only added when datasource config exists."""
    return [
        {"type": "stat", "title": "SLO Compliance",
         "expr": f'avg(slo_compliance_ratio{{project="{business.project_id}"}})',
         "unit": "percentunit", "group": "+Live Metrics"},
    ]
```

**Done when:** Portal shows quality scores, security posture, and optionally live SLO metrics.

---

### Phase 4: Multi-Persona Portals + Wiring (~60 lines)

#### 4a: Persona Variants

Extend `build_portal_spec()` with `persona` parameter:

| Persona | Sections Included | Sections Excluded |
|---|---|---|
| `operator` (default) | All sections | None |
| `engineer` | Project Overview, Service Inventory, Communication Graph, Dashboard Links | Security Posture, Quality Metrics |
| `manager` | Project Overview, Objectives, Quality Metrics, Artifact Health | Communication Graph, Alert details |

Implementation: each `_build_*_panels()` call is gated by a `_PERSONA_SECTIONS` dict:

```python
_PERSONA_SECTIONS = {
    "operator": {"overview", "services", "objectives", "alerts", "dashboards",
                 "communication", "security", "quality", "provenance", "live"},
    "engineer": {"overview", "services", "communication", "dashboards", "provenance"},
    "manager":  {"overview", "objectives", "quality", "health", "provenance"},
}
```

#### 4b: Batch Generation

Generate all persona portals in one call:

```python
def build_all_portal_specs(business, services, report, metadata) -> List[Dict[str, Any]]:
    """Build portal specs for all personas."""
    return [
        build_portal_spec(business, services, report, metadata, persona=p)
        for p in _PERSONA_SECTIONS
    ]
```

Batch via `DashboardCreatorWorkflow` or `batch.run_batch()`.

#### 4c: CLI + Artifact Generator Wiring

**In `scripts/generate_observability_artifacts.py`:**

```python
parser.add_argument("--portal", action="store_true",
                    help="Generate onboarding portal dashboard (opt-in)")
parser.add_argument("--portal-persona", default="operator",
                    choices=["operator", "engineer", "manager", "all"],
                    help="Portal persona variant (default: operator)")
parser.add_argument("--portal-provision", action="store_true",
                    help="Provision portal to Grafana after generation")
```

**In `artifact_generator.py::generate_observability_artifacts()`:**

After the per-service `_GENERATORS` loop (line ~1251), before `_write_artifacts()`:

```python
# Portal generation (REQ-OBP-103a: after alerts/dashboards/SLOs)
if portal_enabled:
    portal_result = _generate_portal_artifact(
        business, services, report, metadata, output_dir,
        persona=portal_persona, provision_url=portal_provision_url,
    )
    report.artifacts.append(portal_result)
```

**New function `_generate_portal_artifact()`** wraps:
1. `build_portal_spec()` → DashboardSpec dict
2. `DashboardCreatorWorkflow().run({"spec": spec_dict, "output_dir": ..., "provision": ...})` → Grafana JSON
3. Wraps result as `ArtifactResult(artifact_type="portal", ...)`

#### 4d: Validation

**In `validators/observability_artifact_checks.py`:**

```python
def validate_portal(content: str, file_path: str = "") -> PortalValidationResult:
    """Validate portal dashboard JSON — section anchors and panel count."""
    dashboard = json.loads(content)
    panels = dashboard.get("panels", [])
    text_panels = [p for p in panels if p.get("type") == "text"]
    # OBP-104a: check expected sections exist as panel titles
    ...
```

Add `"portal"` to `_repair_and_validate()` dispatch — 1-line elif since the orchestrator refactoring is already done (confirmed: `_generate_one()` + `_GENERATORS` list already exist).

**Done when:** `--portal --portal-persona all` produces 3 portal dashboards, optionally provisioned to Grafana.

---

## 4. File Changes Summary

| Phase | File | Change | Lines |
|---|---|---|---|
| 1 | `observability/portal_spec_builder.py` (NEW) | `build_portal_spec()` + project overview + service inventory | ~120 |
| 2 | `observability/portal_spec_builder.py` | Add 5 content section builders | ~100 |
| 3 | `observability/portal_spec_builder.py` | Quality, security, optional live metrics | ~80 |
| 4 | `observability/portal_spec_builder.py` | Persona gating + batch helper | ~40 |
| 4 | `observability/artifact_generator.py` | `_generate_portal_artifact()` + wiring in orchestrator | ~30 |
| 4 | `scripts/generate_observability_artifacts.py` | `--portal`, `--portal-persona`, `--portal-provision` flags | ~15 |
| 4 | `validators/observability_artifact_checks.py` | `validate_portal()` | ~25 |
| **Total** | | | **~410 lines** |

---

## 5. Requirements Mapping

| Requirement | Status | How Satisfied |
|---|---|---|
| **OBP-100** Portal content sections | Phase 1–3 | Each section is a `_build_*_panels()` returning `List[dict]` |
| **OBP-101a** Accept onboarding-metadata + optional inputs | Phase 1 | `build_portal_spec()` signature accepts all inputs |
| **OBP-101b** Deterministic, $0.00 | All phases | No LLM calls — structured data → DashboardSpec dict → Jsonnet → JSON |
| **OBP-101c** Graceful degradation | All phases | Each builder returns `[]` when data absent |
| **OBP-101d** Generated-at timestamp + pipeline version | Phase 1 | Text panel in Project Overview |
| **OBP-101e** Filtered service list (no phantoms) | Phase 1 | Uses `services` already filtered by `_is_non_service_entry()` |
| **OBP-101f** Objectives from onboarding metadata | Phase 2 | `_build_objectives_panels()` reads `metadata["objectives"]` |
| **OBP-101g** Quality from manifest, not re-computed | Phase 3 | Reads `quality_summary` from existing report/manifest |
| **OBP-102a** Self-contained output | Phase 1 | Grafana JSON — single file, no external deps beyond Grafana |
| **OBP-102b** Harbor tour design tokens | N/A | Grafana theme handles styling — no custom CSS needed |
| **OBP-102c** Responsive | N/A | Grafana's built-in responsive layout |
| **OBP-102d** Navigable sections | Phase 1 | Row panels with collapsible groups (`group: "+Section"`) |
| **OBP-102e** Communication graph as table | Phase 2 | Markdown table in text panel |
| **OBP-102f** Relative artifact links | Phase 2 | Grafana dashboard links (`/d/{uid}/`) — better than relative file paths |
| **OBP-103a** Called after dashboards/alerts/SLOs | Phase 4 | Wired after `_GENERATORS` loop in `generate_observability_artifacts()` |
| **OBP-103b** ArtifactResult with type="portal" | Phase 4 | `_generate_portal_artifact()` wraps as ArtifactResult |
| **OBP-103c** Output path | Phase 4 | `portal/{project_id}-portal.json` |
| **OBP-103d** Opt-in for v1 | Phase 4 | `--portal` flag |
| **OBP-104a** Validation checks | Phase 4 | `validate_portal()` checks panels, titles, section count |
| **OBP-104b** Quality score | Phase 4 | `checks_passed / checks_total` |
| **OBP-105a** v0 quick win | Phase 1 | Service inventory only — validates template + wiring |
| **OBP-105b** Readable placeholders | All phases | Empty data renders as "—" or descriptive message |
| **OBP-105c** Objectives as primary SLO source | Phase 2 | Objectives panel uses `metadata["objectives"]`, not parsed SLO YAML |
| **OBP-106a** Separate module | Phase 1 | `portal_spec_builder.py`, not in `artifact_generator.py` |
| **OBP-106b** Orchestrator loop refactor | Already done | `_generate_one()` + `_GENERATORS` already exist (confirmed 2026-03-23) |
| **OBP-106c** Validator dispatch refactor | Deferred | Current 3-branch elif is minimal; portal adds 1 branch |
| **OBP-106d** Refactor-first delivery | Already done | Phase 0 from original plan was completed during initial implementation |

---

## 6. Differences from Original Plan

| Aspect | Original Plan (v2.0.0) | This Plan (v2.0.0) |
|---|---|---|
| **Output format** | Static HTML (f-string templates) | Grafana dashboard JSON (via DashboardCreatorWorkflow + Jsonnet) |
| **Rendering engine** | Custom `portal.py` with CSS design tokens | DashboardSpec model → `panels.text()` / `panels.stat()` in startd8-mixin |
| **Phase 0 refactoring** | Required (copy-paste cleanup) | Already done — `_generate_one()` + `_GENERATORS` exist |
| **Infrastructure** | None (browser only) | Grafana instance + startd8-mixin (both already in repo) |
| **Live metrics** | Impossible | Optional stat/gauge panels with PromQL |
| **Multi-persona** | Not in original plan | Phase 4: operator / engineer / manager variants |
| **Navigation** | Anchor links + relative file paths | Grafana dashboard links with variable forwarding |
| **Provisioning** | Manual file distribution | `--portal-provision` pushes to Grafana API |
| **Test strategy** | Open HTML in browser | Validate JSON structure + provision to test Grafana |
| **Lines of code** | ~260 (portal.py + wiring) | ~410 (more features: personas, live metrics, provisioning) |
| **Future extensibility** | Would need Grafana path added separately | Config variables, `${metrics.*}` refs, mixin integration available from day 1 |

---

## 7. Dependencies

| Dependency | Status | Notes |
|---|---|---|
| `DashboardCreatorWorkflow` | Exists | `src/startd8/dashboard_creator/workflow.py` |
| `DashboardSpec` / `PanelSpec` models | Exists | `src/startd8/dashboard_creator/models.py` — TEXT type supported |
| `layout.auto_group_rows()` | Exists | `src/startd8/dashboard_creator/layout.py` |
| `startd8-mixin/` directory | Exists | In repo root with `vendor/`, `config.libsonnet`, `lib/panels.libsonnet` |
| Jsonnet toolchain | Exists | `go-jsonnet` in PATH (`~/go/bin/jsonnet`) |
| `panels.text(title, content)` | Exists | `startd8-mixin/lib/panels.libsonnet` line 438 |
| `panels.stat(title, expr, ...)` | Exists | `startd8-mixin/lib/panels.libsonnet` line 4 |
| `panels.gauge(title, expr, ...)` | Exists | `startd8-mixin/lib/panels.libsonnet` line 40 |
| `artifact_generator._GENERATORS` loop | Exists | Already refactored (confirmed 2026-03-23) |
| `artifact_generator._is_non_service_entry()` | Exists | Phantom filtering at line 180 |
| `BusinessContext` / `ServiceHints` / `ArtifactResult` | Exists | `artifact_generator.py` dataclasses |
| `observability_artifact_checks` validators | Exists | `validators/observability_artifact_checks.py` |
| Grafana instance | Exists | localhost:3000 in all environments |

**Zero new dependencies.** All infrastructure is in place.

---

## 8. Demo Script

After implementation, the demo flow for Act 3 becomes:

```bash
# Generate observability artifacts WITH portal
python3 scripts/generate_observability_artifacts.py \
    --onboarding-metadata pipeline-output/run-XXX/onboarding-metadata.json \
    --output-dir pipeline-output/run-XXX/observability \
    --portal \
    --portal-persona all \
    --portal-provision

# Three portals provisioned to Grafana:
#   /d/portal-online-boutique-operator/
#   /d/portal-online-boutique-engineer/
#   /d/portal-online-boutique-manager/

# Open in browser
open http://localhost:3000/d/portal-online-boutique-operator/
```

In Grafana:
1. **Operator portal** — Collapsible sections: Project Overview, Service Inventory (11 services table), Objectives (availability + latency targets), Alert Inventory, Dashboard Links (click → service dashboard), Communication Graph, Quality Metrics, Provenance
2. **Manager portal** — Project Overview, Objectives, Quality Scores (gauge panel), Artifact Health (stat panels)
3. **Engineer portal** — Project Overview, Service Inventory, Communication Graph, Dashboard Links

All three share Grafana's theme, auth, search, and sidebar navigation. Dashboard links from portal → service dashboards → alerts work with one click.

---

## 9. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Text panel markdown rendering varies across Grafana versions | Low | Test on localhost:3000; markdown is stable since Grafana 9+ |
| Portal JSON too large for Grafana API (many services) | Low | Online Boutique has 11 services; even 100 services would be <500KB JSON |
| Persona sections create maintenance burden | Low | `_PERSONA_SECTIONS` dict is declarative; adding/removing sections is 1-line change |
| No-Grafana environments need portals | Medium | Add direct JSON renderer (~120 lines) later; `portal_spec_builder.py` output is path-agnostic |
| Mixin not available in CI/test environments | Low | `startd8-mixin/` is committed to repo; `go-jsonnet` available via pip (`gojsonnet` package) |

---

## 10. Resolved Design Decisions

### Q1: Jsonnet Path (Not Direct JSON)

**Decision:** Use the existing Jsonnet pipeline via `DashboardCreatorWorkflow`. No direct JSON renderer needed.

**Rationale:**
- `startd8-mixin/` already exists in repo with `vendor/`, `config.libsonnet`, all panel constructors
- Jsonnet toolchain (`go-jsonnet`) already installed
- Portal panels (text, stat, gauge, row) are fully supported by `panels.libsonnet`
- Config-driven datasource UIDs, refresh intervals, and timezone inherited automatically
- Future `${metrics.*}` references available from day 1 when portals evolve toward live operational content
- `.libsonnet` source can be persisted alongside operational dashboards, included in `make generate`

**Deferred:** Direct JSON renderer (~120 lines) can be added later if mixin-free environments need portal generation. The `DashboardSpec` dict is the contract — `portal_spec_builder.py` doesn't change regardless of rendering path.

### Q2: Portal UID Convention

**Decision:** `portal-{project_id}[-persona]`

Examples:
- `portal-online-boutique` (default operator)
- `portal-online-boutique-operator`
- `portal-online-boutique-engineer`
- `portal-online-boutique-manager`

This diverges from the `cc-{pack}-{slug}` convention used for mixin dashboards but is intentional — portal dashboards are project-scoped, not pack-scoped. The `portal-` prefix makes them easily discoverable via Grafana search.

### Q3: Provisioning Folder

**Decision:** Separate "Portal" folder in Grafana.

Portals serve a different audience (onboarding, orientation) than operational dashboards (monitoring, alerting). Co-locating them with service dashboards would bury them. A dedicated folder makes them findable by new team members — which is the entire point.
