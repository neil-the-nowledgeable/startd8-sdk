# Observability Artifact Generation Demo — Runbook

Based on [CONCEPT_DEMO_RUNBOOK.md](wayfinder-demo-retail) with portal generation added.

**Total time:** 15 minutes (3 acts × 5 min)
**Audience:** Any persona — portal adapts per viewer

---

## Pre-Demo Setup Checklist

```bash
# 1. Start observability stack (Kind cluster)
# Docker Desktop must be running — pods auto-recover on restart.
# If Grafana pod is stuck:
kubectl delete pod -n observability -l app=grafana

# 2. Verify stack health
curl -s http://localhost:3000/api/health  # Grafana
curl -s http://localhost:3200/ready       # Tempo
curl -s http://localhost:3100/ready       # Loki

# 3. Generate demo data (3-month project history)
cd ~/Documents/dev/ContextCore
contextcore demo generate --seed 42
contextcore demo load --file ./demo_output/demo_spans.json --endpoint localhost:4317

# 4. Provision ContextCore dashboards
contextcore dashboards provision --grafana-url http://localhost:3000

# 5. Generate + provision portal dashboards (from startd8-sdk root)
cd ~/Documents/dev/startd8-sdk
python3 scripts/demo_portal_prep.py
# Then provision (update password if needed):
for f in ~/Documents/dev/online-boutique-demo/.cap-dev-pipe/pipeline-output/online-boutique/run-101-*/portal/cc-portal-*.json; do
  python3 -c "
import json,sys
with open('$f') as fh: d=json.load(fh)
d['id']=None
print(json.dumps({'dashboard':d,'folderUid':'portal-folder','overwrite':True}))
" | curl -s -u admin:adminadminadmin -X POST http://localhost:3000/api/dashboards/db \
    -H "Content-Type: application/json" -d @- | python3 -c "
import sys,json; d=json.load(sys.stdin); print(d.get('status','?'), d.get('url',''))
"
done
```

### Pre-Open Tabs

| Tab | URL |
|-----|-----|
| Operator Portal | http://localhost:3000/d/cc-portal-online-boutique/ |
| Manager Portal | http://localhost:3000/d/cc-portal-online-boutique-manager/ |
| Engineer Portal | http://localhost:3000/d/cc-portal-online-boutique-engineer/ |
| Executive Portal | http://localhost:3000/d/cc-portal-online-boutique-executive/ |
| Grafana Explore (Tempo) | http://localhost:3000/explore |

---

## Act 1: "From Code to Observability Artifacts" (0:00–5:00)

### Minute 1: The Problem (0:00–1:00)

> "You've got 12 microservices. Each needs dashboards, alerts, SLOs, runbooks. Manually? That's weeks of YAML. And it drifts from reality on day one."
>
> "What if the pipeline that generates your code also generates your observability artifacts — from the same source of truth?"

Show a ProjectContext CRD:
```yaml
# demo/projectcontexts/checkoutservice.yaml
spec:
  business:
    criticality: critical
    value: revenue-primary
    owner: commerce-team
  requirements:
    availability: "99.95"
    latencyP99: "200ms"
```

### Minute 2: Artifact Generation (1:00–2:00)

> "One command. Dashboards, alerts, SLOs — all derived from requirements."

```bash
python3 scripts/generate_observability_artifacts.py \
    --onboarding-metadata pipeline-output/.../onboarding-metadata.json \
    --output-dir pipeline-output/.../observability
```

Show the output:
- `alerts/checkoutservice-alerts.yaml` — latency P99 > 200ms alert
- `dashboards/checkoutservice-dashboard-spec.yaml` — PromQL panels
- `slos/checkoutservice-slo.yaml` — 99.95% availability target

### Minute 3: Quality + Provenance (2:00–3:00)

> "Every artifact is quality-scored and provenance-tracked."

Show `observability-manifest.yaml`:
- Per-artifact quality scores (1.0 for alerts, 0.67 composite)
- Derivation rules: `criticality: critical → severity: critical`
- Source tracing: every value traces back to its CRD field

### Minutes 4–5: The Landscape (3:00–5:00)

> "5 services, 15 artifacts, all generated. Now add portal generation..."

---

## Act 2: "Completing the Instrumentation" (5:00–10:00)

### Minute 6: TODO Scanner (5:00–6:00)

> "Generated code has TODOs where instrumentation should go. The pipeline scans, classifies, and completes them."

Show categories:
- **Category A** (uncomment): `# TODO: uncomment logging setup` → deterministic fix at $0.00
- **Category B** (instrument): `# TODO: add tracing` → LLM with instrumentation contract in context
- **Category C** (human review): Complex cases deferred

### Minute 7: Instrumentation Hints (6:00–7:00)

> "ContextCore derives per-service instrumentation guidance from the communication graph."

Show `instrumentation_hints` for checkoutservice:
- Expected metrics: `rpc.server.duration`, `rpc.server.request.size`
- Trace spans: `{service}/{method}` with `rpc.system`, `rpc.service` attributes
- OTel SDK: Go package coordinates, interceptor packages
- Detected databases: PostgreSQL

### Minutes 8–10: Before/After (7:00–10:00)

Show a generated function:
```python
# BEFORE (TODO stub)
def handle_request(request):
    # TODO: add structured logging
    # TODO: add tracing span
    return process(request)

# AFTER (instrumented)
@tracer.start_as_current_span("handle_request")
def handle_request(request):
    logger.info("Processing request", extra={"request_id": request.id})
    return process(request)
```

> "Category A at $0.00. Category B via cheap-model generation with full instrumentation contract."

---

## Act 3: "Stakeholder Onboarding Portals" (10:00–15:00)

### Minute 11: The Portal Concept (10:00–11:00)

> "Same pipeline data. Different view per audience. No new tools — same Grafana."

Open the **Operator Portal**: http://localhost:3000/d/cc-portal-online-boutique/

Walk through sections:
1. **Project Overview** — criticality, owner, generation timestamp
2. **Why This Portal** — "$247K/yr pain: incidents arrive without context"
3. **Service Inventory** — 5 services with protocol, language, databases
4. **Alert Inventory** — per-service alert names, severity, duration
5. **Communication Graph** — who calls whom

### Minute 12: Persona Comparison (11:00–12:00)

Switch to **Manager Portal**: http://localhost:3000/d/cc-portal-online-boutique-manager/

> "Same data. Different lens. The manager sees objectives, quality scores, artifact health — not alert YAML."

Compare side-by-side with operator portal:
- Manager: Objectives + Quality Gauge + Artifact Health stats
- Operator: Alerts + Communication Graph + Security

### Minute 13: Executive View (12:00–13:00)

Open **Executive Portal**: http://localhost:3000/d/cc-portal-online-boutique-executive/

> "Four panels. That's it. Project criticality, objectives, quality score. Everything an executive needs."

Show the aggregate pain: "$1.3M/yr across all personas — this portal addresses it."

### Minutes 14–15: The Full Picture (13:00–15:00)

> "From a ProjectContext CRD, the pipeline produces: dashboards, alerts, SLOs, instrumented code, AND stakeholder portals. All provenance-tracked. All persona-aware."

Show the Grafana sidebar:
- **Portal** folder → 4 persona dashboards
- **ContextCore** folder → project-progress, sprint-metrics, project-operations
- Service dashboards linked from portal → one-click drill-down

### Closing

> "Business observability + artifact generation + stakeholder portals. One pipeline. Same Grafana. Every persona gets what they need."

---

## Transition to Deep-Dives

After the 15-minute demo, offer persona-specific deep-dives:

| Persona | Pain | Duration | Source |
|---------|------|----------|--------|
| Developer | $475K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/developer.md` |
| Project Manager | $117K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/project-manager.md` |
| Engineering Leader | $258K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/engineering-leader.md` |
| Operator / SRE | $247K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/operator-sre.md` |
| Compliance Officer | $206K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/compliance.md` |
| AI Agent | $205K/yr | 5 min | `wayfinder-demo-retail/demo/persona-views/ai-agent.md` |

**Combined time:** 15 min (demo) + 5 min (persona deep-dive) = ~20 min total

---

## Pre-Written Queries

See `wayfinder-demo-retail/demo/DEMO_QUERIES.md` for TraceQL/LogQL queries organized by persona.

Key queries for the demo:

```
# Find task spans with lifecycle events
{span.task.id != ""} | select(span.task.id, span.task.title, span.task.status) | limit(5)

# Agent decisions with high confidence
{span.insight.type = "decision" && span.insight.confidence >= 0.8} | select(span.insight.summary, span.insight.confidence) | limit(3)

# Tasks blocked right now
{span.task.status = "blocked"} | select(span.task.id, span.task.title) | limit(10)
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Grafana not reachable | `kubectl delete pod -n observability -l app=grafana` then wait 30s |
| Portal folder empty | Re-run `python3 scripts/demo_portal_prep.py` from startd8-sdk root |
| Dashboard shows "No data" | Verify Tempo datasource; re-load demo data |
| TraceQL returns nothing | `contextcore demo generate --seed 42 && contextcore demo load` |
| Portal panels half-width | Regenerate: `rm portal/*.json && python3 scripts/demo_portal_prep.py` |
