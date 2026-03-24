# Capability Delivery Pipeline — Demo Planning (Harbor Tour)

> **Date:** 2026-03-23
> **Status:** PLANNING
> **Audience:** Internal — demo preparation and next-steps alignment

---

## 1. Pipeline Overview (High Level)

The **Capability Delivery Pipeline** (`cap-dev-pipe`) is a 7-stage provenance-tracked pipeline that transforms business intent into generated observability artifacts. It orchestrates two systems:

```
 ContextCore (Stages 0–4)                startd8-sdk (Stages 5–7)
┌─────────────────────────────┐         ┌──────────────────────────────┐
│ 0. ProjectContext CRD        │         │ 5. Plan Ingestion            │
│ 1. Artifact Manifest         │────────▶│ 6. Code Generation           │
│ 2. Quality Validation        │         │ 7. Artifact Delivery +       │
│ 3. Instrumentation Hints     │         │    TODO Completion           │
│ 4. Onboarding Metadata Export│         └──────────────────────────────┘
└─────────────────────────────┘
```

**Embedded in projects** via symlinks to canonical `~/Documents/dev/cap-dev-pipe/`.

**7 Generation Profiles** target different audiences:

| Profile | Audience | Key Artifacts |
|---------|----------|---------------|
| `source` | Developer | Code-generation context only |
| `monitoring` | Machine | Prometheus/Loki rules, ServiceMonitor |
| `operator` | SRE | + runbooks, dashboards |
| `sponsor` | Business | Business dashboards, SLO definitions |
| `practitioner` | Marketing/Sales | Portal dashboards (zero Grafana literacy) |
| `observability` | All ops | All observability artifacts |
| `full` | Everyone | Everything (default) |

---

## 2. Demo Narrative (3 Acts)

### Act 1 — "From Code to Observability Artifacts"
Starting with ProjectContext CRDs for Online Boutique's 11 microservices, the pipeline analyzes code and generates:
- **Grafana Dashboard Specs** (per-service metrics visualization)
- **Prometheus Alert Rules** (latency + availability thresholds from requirements)
- **OpenSLO Definitions** → k6 load tests + Chaos Mesh experiments
- **ServiceMonitors** (criticality-mapped scrape intervals)
- **Runbooks** (operational procedures, escalation contacts)

All artifacts carry provenance — every output traces back to its source CRD field.

### Act 2 — "Completing the Instrumentation"
After code generation, the pipeline scans for instrumentation gaps:
- **TODO Scanner** classifies gaps: Category A (uncomment blocks), B (instrument from contract), C (human review)
- **Phase 0.5 Shortcut** completes Category A tasks at $0.00 (deterministic uncomment, no LLM)
- **Category B** tasks get instrumentation contract injected into LLM context for completion
- Before/after diffs show logging, tracing, and metrics added to generated code

### Act 3 — "Stakeholder Onboarding Portals"
The pipeline's onboarding metadata (41+ fields) gets rendered into navigable HTML portals tailored per audience:
- **SRE**: Alert inventory, SLO summary, runbook links, service communication graph
- **Engineering Manager**: Quality metrics, security posture, Kaizen scores
- **Marketing Manager**: Project overview, service inventory, availability targets
- **New Engineer**: Architecture overview, dashboard links, getting-started guide

---

## 3. Corrected Capability Inventory

### What EXISTS and WORKS Today

| Capability | Location | Maturity | Notes |
|---|---|---|---|
| **Dashboard spec generation** | `startd8/observability/artifact_generator.py::generate_dashboard_spec()` | Production (1558-line module) | Per-service PromQL dashboards |
| **Alert rule generation** | `artifact_generator.py::generate_alert_rules()` | Production | Latency P99 + availability from requirements |
| **SLO definition generation** | `artifact_generator.py::generate_slo_definitions()` | Production | OpenSLO v1 YAML |
| **SLO test generation (k6)** | `ContextCore/generators/slo_tests.py` | Complete | k6 load + spike tests, Chaos Mesh experiments |
| **ServiceMonitor generation** | `ContextCore/cli/_generators.py` | Complete | Criticality → scrape interval mapping |
| **Runbook generation** | `ContextCore/generators/runbook.py` | Complete | Markdown operational runbooks |
| **Instrumentation hints derivation** | `ContextCore/utils/instrumentation.py` (315 lines) | Complete | Per-service OTel SDK coords, expected metrics, trace spans, DB detection |
| **TODO scanner + classification** | `startd8/validators/todo_scanner.py` (723 lines) | Complete | Categories A/B/C/S, rationale, contract matching |
| **TODO → seed task derivation** | `startd8/seeds/todo_derivation.py` (322 lines) | Complete | Transforms TodoInventory → Prime Contractor seed tasks |
| **TODO completion in-band (v3)** | `startd8/contractors/prime_contractor.py` | Complete (2026-03-21) | Phase 0.5 shortcut + post-gen scan + queue injection |
| **TODO uncomment repair step** | `startd8/repair/steps/todo_uncomment.py` | Complete | Post-LLM cleanup fallback |
| **Instrumentation coverage validator** | `startd8/validators/instrumentation_coverage.py` (234 lines) | Complete | PromQL cross-check, gap reporting |
| **Generation profile extraction** | `startd8/seeds/builder.py`, `seeds/utils.py` | Complete | `is_omitted()`, `safe_onboarding()`, 7 known profiles |
| **Generation profile gating (2 gates)** | Plan ingestion + prime-post-run.py | Complete | Parameter resolvability skip + instrumentation auto-enable |
| **Onboarding metadata export** | `ContextCore/utils/onboarding.py` | Complete | 41+ fields, profile scoping, artifact parameter sources |
| **Demo data generation** | `ContextCore/demo/generator.py` | Complete | 3-month history, 200+ tasks, 11 services, Tempo/Loki loading |
| **Dashboard provisioning** | `ContextCore/dashboards/provisioner.py` | Production | 8-extension auto-discovery, idempotent Grafana API |
| **DashboardSpec → Jsonnet compiler** | `startd8/dashboard_creator/` | Production | 16 panel types, 8 variable types, Grafonnet integration |
| **Pre-built dashboards (14 total)** | startd8-mixin (5) + ContextCore core (9) | Production | Project progress, sprint metrics, cost tracking, etc. |
| **Pipeline orchestration scripts** | `cap-dev-pipe/run-*.sh` | Production | Provenance-tracked, profile-aware |
| **Harbor tour HTML portals (4 personas)** | `ContextCore/docs/website/harbor-tour-*.html` | Manually authored | AI Dev, Platform Eng, Team Lead, generic (860–950 lines each) |
| **Developer portal (startd8)** | `startd8-sdk/docs/developer-portal.html` (1070 lines) | Manually authored | Full-page portal with capabilities grid |
| **Prime Contractor harbor tour** | `startd8-sdk/docs/harbor-tour-prime-contractor.html` (722 lines) | Manually authored | Batch code generation onboarding |
| **Getting-started portal** | `ContextCore/docs/website/getting-started.html` (720 lines) | Manually authored | Tab-based interactive setup guide |

### What Is DESIGNED but NOT YET BUILT

| Capability | Requirements Doc | Status | Effort |
|---|---|---|---|
| **Onboarding Portal Generator** (4th artifact type) | `docs/design/onboarding-portal/ONBOARDING_PORTAL_REQUIREMENTS.md` (v0.3.0, 2026-03-21) | Requirements complete, implementation plan v2.0.0 exists | ~260 lines across 4 phases |
| **Artifact generator refactoring** (AC-1, AC-2, AC-3) | Same doc, REQ-OBP-106 | Prerequisite for portal — extract `_generate_one()` helper + `_VALIDATORS` dispatch dict | Phase 0 (~65 lines saved) |
| **Portal validation (Kaizen)** | REQ-OBP-104 | Specified | Part of portal implementation |

### What Has PARTIAL Integration

| Capability | What Works | What's Missing |
|---|---|---|
| **Generation profile consumption** | Extraction, validation, transport, storage, 2 decision gates | No phase-level behavior changes (IMPLEMENT, TEST, REVIEW are profile-agnostic) |
| **ContextCore dashboard template** (`_generators.py`) | Basic 2-panel (request rate + latency P99) | Very thin compared to startd8's artifact_generator or mixin dashboards |

---

## 4. Key Corrections from Initial Assessment

| Item | Initial Assessment | Corrected Assessment |
|---|---|---|
| **TODO completion** | "Not implemented, needs 1 week" | **Fully implemented (v3, 2026-03-21)**: Scanner (723 lines) + derivation (322 lines) + in-band execution in PrimeContractor + Phase 0.5 shortcut + coverage validator |
| **Onboarding portal pages** | "0% complete, needs building" | **Manually authored exemplars exist** (6 HTML files, 4,500+ lines total). **Auto-generated portal** has complete requirements (v0.3.0) + implementation plan (v2.0.0) but no code yet. ~260 lines to implement. |
| **Dashboard generation** | "Basic 2-panel template" | Two systems: ContextCore CLI generator is basic, but **startd8 `artifact_generator.py`** (1558 lines) has full `generate_dashboard_spec()` with PromQL templates + derivation rules. Plus **14 pre-built dashboard JSONs** across mixins. |
| **Generation profile guards** | "Blocker, needs is_omitted()" | **`is_omitted()` and `safe_onboarding()` already exist** in `seeds/utils.py`. Design phase already logs when omitted fields are skipped. 2 decision gates operational. |
| **Instrumentation code patching** | "Missing entirely" | Category B tasks are LLM-generative with instrumentation contract in context (not patch-based). Category A is deterministic uncomment. The architecture is intentionally generative, not AST-patching. |

---

## 5. What's Actually Needed for Demo

### Tier 1: Can Demo Today (zero new code)

1. **Artifact generation pipeline**: `contextcore generate --all` → dashboards, alerts, ServiceMonitors
2. **SLO test generation**: `contextcore slo-tests generate` → k6 + Chaos Mesh
3. **Demo data**: `contextcore demo generate --seed 42` → 3-month history in Tempo/Loki
4. **Pre-built dashboards**: 14 dashboards across both projects, provisionable via API
5. **Profile scoping**: `contextcore manifest export --profile operator` vs `--profile source` showing data reduction
6. **Manually authored portals**: 6 HTML files demonstrating persona-tailored onboarding
7. **Instrumentation hints**: Show `instrumentation.py` output for a service (OTel SDK coords, expected metrics, trace spans)

### Tier 2: Enhances Demo (small new code)

| Work Item | Effort | What It Adds |
|---|---|---|
| **Onboarding Portal Generator** | ~260 lines (4 phases per implementation plan) | Auto-generated portal from pipeline data — the "fourth artifact type" |
| **Artifact generator refactoring** | Phase 0 prerequisite (~65 lines saved) | Cleaner orchestrator loop + validator dispatch |

### Tier 3: Nice-to-Have

| Work Item | Effort | What It Adds |
|---|---|---|
| Deeper generation profile phase behavior | Medium | IMPLEMENT/TEST/REVIEW adapt per profile |
| Grafana portal dashboard format (v2) | Medium | Portal as Grafana dashboard instead of static HTML |
| Cross-run instrumentation progression | Small | Kaizen tracking of TODO completion rates |

---

## 6. Demo Flow (Recommended)

### Setup (pre-demo)
```bash
# Generate demo data
contextcore demo generate --seed 42
contextcore demo load --file ./demo_output/demo_spans.json --endpoint localhost:4317

# Provision dashboards
contextcore dashboards provision
```

### Live Demo Sequence

**[5 min] Act 1: Code Analysis → Artifacts**
1. Show a ProjectContext CRD (`demo/projectcontexts/checkoutservice.yaml`)
2. Run `contextcore generate --all --emit-report` — watch dashboards, alerts, SLOs appear
3. Open generated dashboard spec — show PromQL derived from requirements
4. Open generated alert rules — show thresholds derived from availability targets
5. Show provenance: `generation-report.json` → every artifact traced to source field

**[5 min] Act 2: Instrumentation TODO Completion**
1. Show code with TODO stubs (generated output from a Prime Contractor run)
2. Show `instrumentation_hints` for the service (metrics, traces, SDK packages)
3. Run TODO scanner — show classification (A: uncomment, B: instrument, C: review)
4. Show Phase 0.5 completing Category A at $0.00
5. Show Category B task with instrumentation contract in LLM context
6. Before/after diff: bare function → function with `@tracer.start_as_current_span()` + structured logging

**[5 min] Act 3: Stakeholder Portals**
1. Open `harbor-tour-platform-engineer.html` — SRE-focused operational view
2. Open `harbor-tour-team-lead.html` — management metrics + time-savings analysis
3. Open `harbor-tour-ai-developer.html` — agent memory + cross-session context
4. Point: "All this data exists in `onboarding-metadata.json` — the portal generator will produce these automatically"
5. *(If built)* Run portal generator, show auto-generated HTML alongside hand-crafted exemplar

**[3 min] Wrap-up: The Full Picture**
1. Show Grafana with pre-built dashboards (project progress, sprint metrics, cost tracking)
2. Show 3-month demo history in Tempo (tasks as spans, epic→story→task hierarchy)
3. Key message: "From a ProjectContext CRD, the pipeline produces dashboards, alerts, SLOs, instrumented code, and stakeholder portals — all provenance-tracked"

---

## 7. Architecture Reference

### Artifact Generator (startd8-sdk)
```
src/startd8/observability/artifact_generator.py (1558 lines)
├── generate_alert_rules(service, business)      → alerts/*.yaml
├── generate_dashboard_spec(service, business)   → dashboards/*.yaml
├── generate_slo_definitions(service, business)  → slos/*.yaml
└── generate_observability_artifacts(...)         → orchestrates all 3 + report
    [PLANNED: generate_portal() as 4th type]
```

### TODO Completion Pipeline (startd8-sdk, v3 in-band)
```
ContextCore (Stage 4)
  └── instrumentation.py → instrumentation_hints (per-service guidance)
        ↓
startd8-sdk (Stage 6, Prime Contractor)
  ├── validators/todo_scanner.py       → scan + classify (A/B/C/S)
  ├── seeds/todo_derivation.py         → TodoInventory → seed tasks
  ├── contractors/prime_contractor.py  → in-band execution:
  │     ├── Phase 0.5: uncomment shortcut ($0.00)
  │     ├── Post-gen scan + queue injection
  │     └── Category B: LLM with instrumentation contract
  ├── repair/steps/todo_uncomment.py   → post-LLM cleanup
  └── validators/instrumentation_coverage.py → gap reporting
```

### Onboarding Portal (planned)
```
Inputs:
  ├── onboarding-metadata.json (41+ fields)
  ├── kaizen-metrics.json (optional, quality scores)
  ├── run-provenance.json (optional, run metadata)
  ├── observability-manifest.yaml (optional, quality summary)
  └── Generated artifacts (alerts/, dashboards/, slos/)
        ↓
observability/portal.py (NEW, ~260 lines)
        ↓
Output: portal/{project_id}-portal.html
  Sections: Project Overview, Service Inventory, Objectives,
            Communication Graph, Alert Inventory, Dashboard Links,
            Security Posture, Quality Metrics, Run Provenance
```

### Existing Portal HTML (manually authored exemplars)
```
ContextCore/docs/website/
  ├── harbor-tour.html                    (863 lines, generic)
  ├── harbor-tour-ai-developer.html       (948 lines)
  ├── harbor-tour-platform-engineer.html  (866 lines)
  ├── harbor-tour-team-lead.html          (909 lines)
  ├── getting-started.html                (720 lines)
  └── index.html                          (551 lines, landing page)

startd8-sdk/docs/
  ├── developer-portal.html               (1070 lines)
  └── harbor-tour-prime-contractor.html   (722 lines)
```

---

## 8. Next Steps

1. **Decide demo scope**: Full 3-act demo or focused single-act?
2. **Build portal generator?**: ~260 lines, requirements + plan already written. Would let Act 3 show auto-generation instead of only exemplars.
3. **Prepare demo data**: Ensure Online Boutique ProjectContexts + seed file produce clean artifact generation run.
4. **Script the walkthrough**: Pre-stage terminal commands, pre-open HTML files, pre-provision Grafana dashboards.
