# startd8-sdk Operational Runbook

_Generated: 2026-02-11 via Wayfinder `generate_runbook()` + startd8-specific enhancements_
_Source: ProjectContext CRD (.contextcore.yaml v2.0)_

## Service Overview

| Field | Value |
|-------|-------|
| Project ID | startd8-sdk |
| Package | Beaver (Amik) |
| Owner | platform-engineering |
| Criticality | high |
| Business Value | enabler |
| Cost Center | platform-engineering |
| Slack | #startd8-dev |

**Description**: Multi-LLM provider abstraction SDK with unified interface, cost tracking, token accounting, and OpenTelemetry observability.

## Service Level Objectives

| Metric | Target | Alert Threshold | Alert Name |
|--------|--------|-----------------|------------|
| Availability | 99.9% | < 99.9% | `StartD8AgentRuntimeAvailabilityLow` |
| Latency P99 | 500ms | > 500ms | `StartD8AgentRuntimeLatencyHigh` |
| Truncation Rate | < 5% | > 5% | `StartD8TruncationHigh` |
| Cost Burn | varies | > $10/hour | `StartD8CostBudgetBurn` |
| Throughput | 100 rps | < 80% capacity | _(monitoring only)_ |

**Error Budget**: 0.1% monthly (43.2 minutes of allowed downtime per 30-day window)

## Known Risks & Mitigations

| Risk Type | Priority | Description | Mitigation |
|-----------|----------|-------------|------------|
| availability | P1 | LLM provider API failure cascades to all dependent agents | Provider fallback chain with configurable retry and circuit breaker |
| financial | P2 | Cost tracking drift between SDK estimates and provider invoices | Reconciliation job compares tracked costs with billing API data |
| availability | P2 | OTLP exporter failure silently drops agent telemetry spans | Graceful degradation — TrackedAgentMixin logs warning and continues without telemetry |
| data-integrity | P3 | Token count normalization varies across providers (tiktoken vs provider-native) | Standardize on tiktoken for estimation, record provider-reported tokens as ground truth |

## Dashboards

| Dashboard | Path | Description |
|-----------|------|-------------|
| Overview | `dashboards/startd8-sdk-overview.json` | 12-panel overview with Tempo/Mimir/Loki |
| Cost Tracking | `dashboards/startd8-cost-tracking.json` | Per-model cost breakdowns and budget burn |
| Metrics | `dashboards/startd8-metrics.json` | Detailed metric explorer |
| Lead Contractor | `dashboards/lead-contractor-progress.json` | Code generation workflow progress |

## Key Metrics Reference

### Session Tracking (`src/startd8/session_tracking.py`)
| Metric | Type | Labels |
|--------|------|--------|
| `startd8_requests_total` | Counter | agent_name, model, project_id, status |
| `startd8_response_time_ms` | Histogram | agent_name, model, project_id |
| `startd8_tokens_total` | Counter | agent_name, model, project_id, direction |
| `startd8_cost_total` | Counter | agent_name, model, project_id |
| `startd8_truncations_total` | Counter | agent_name, model, project_id |
| `startd8_active_sessions` | UpDownCounter | agent_name, model, project_id |
| `startd8_context_usage_ratio` | Gauge | session_id, agent_name, model, project_id |

### Cost Tracking (`src/startd8/costs/otel_metrics.py`)
| Metric | Type | Labels |
|--------|------|--------|
| `startd8.cost.total` | Counter | model, provider, project |
| `startd8.cost.input_tokens` | Counter | model, provider, project |
| `startd8.cost.output_tokens` | Counter | model, provider, project |
| `startd8.cost.per_request` | Histogram | model, provider, project |

## Kubernetes Resources

### Resource Status

```bash
# Check resource status
kubectl get service startd8-agent-runtime -n agents

# Describe resources for events
kubectl describe service startd8-agent-runtime -n agents
```

### View Logs

```bash
# Recent logs
kubectl logs -l app=startd8-agent-runtime -n agents --tail=100

# Follow logs
kubectl logs -l app=startd8-agent-runtime -n agents -f

# Previous container logs (if restarted)
kubectl logs -l app=startd8-agent-runtime -n agents --previous

# Error logs only (via Loki)
logcli query '{app="startd8-agent-runtime"} | json | level = "error"' --limit=50
```

## Common Procedures

### Restart Service

```bash
# Rolling restart
kubectl rollout restart deployment/startd8-agent-runtime -n agents

# Wait for rollout to complete
kubectl rollout status deployment/startd8-agent-runtime -n agents --timeout=5m
```

### Emergency Scale Up

```bash
# Scale to 5 replicas
kubectl scale deployment/startd8-agent-runtime --replicas=5 -n agents

# Verify scaling
kubectl get deployment/startd8-agent-runtime -n agents
```

**Note**: Scale back down after incident resolution.

### Debug Connectivity

```bash
# Check endpoints
kubectl get endpoints startd8-agent-runtime -n agents

# Test from inside cluster
kubectl run debug --rm -it --image=busybox --restart=Never -- sh

# Inside the debug pod:
# wget -qO- http://startd8-agent-runtime.agents.svc.cluster.local/health
```

### Resource Usage

```bash
# Check pod resource usage
kubectl top pods -l app=startd8-agent-runtime -n agents

# Check node resource usage
kubectl top nodes
```

## Alert Response

### AvailabilityLow Alert

**Alert**: `StartD8AgentRuntimeAvailabilityLow` (P2, 5m)
**Condition**: `service:startd8_availability:rate5m < 0.999`

1. Check pod health: `kubectl get pods -l app=startd8-agent-runtime -n agents`
2. Check per-model availability: query `model:startd8_availability:rate5m` in Grafana
3. If a single provider is failing, check provider status page
4. Review error logs: `{app="startd8-agent-runtime"} | json | level = "error"`
5. Review recent deployments: `kubectl rollout history deployment/startd8-agent-runtime -n agents`
6. Consider emergency scale-up if load-related

### LatencyHigh Alert

**Alert**: `StartD8AgentRuntimeLatencyHigh` (P2, 5m)
**Condition**: `service:startd8_latency_p99:rate5m > 500`

1. Check resource utilization: `kubectl top pods -l app=startd8-agent-runtime -n agents`
2. Check per-model latency: query `model:startd8_latency_p99:rate5m` in Grafana
3. Look for provider degradation — slow provider will inflate P99
4. Review recent changes: commits, config updates, model changes
5. Consider scaling or traffic shedding

### Truncation Response

**Alert**: `StartD8TruncationHigh` (P3, 10m)
**Condition**: `service:startd8_truncations:rate5m > 0.05`

1. Check which models/agents are truncating: `sum by (model, agent_name) (rate(startd8_truncations_total[5m]))`
2. Review context usage ratio: `startd8_context_usage_ratio` gauge by session
3. Consider switching agents to models with larger context windows
4. Check if prompt templates have grown unexpectedly

### Cost Anomaly Response

**Alert**: `StartD8CostBudgetBurn` (P3, 15m)
**Condition**: `service:startd8_cost:rate1h > 10`

1. Identify cost source: `model:startd8_cost:rate1h` — which model is burning?
2. Check for request loops or retries: `model:startd8_requests:rate5m`
3. Compare token throughput: `model:startd8_tokens:rate5m` — input vs output ratio
4. If a single model dominates, consider routing to cheaper model
5. Cross-reference with provider billing dashboard for cost accuracy

## Provider Failover Procedure

When a single LLM provider is failing:

1. **Detect**: Check `model:startd8_availability:rate5m` — identify failing provider
2. **Verify**: Check provider status page (Anthropic, OpenAI, Google)
3. **Failover**: If provider fallback chain is configured, verify it activated:
   - Check logs: `{app="startd8-agent-runtime"} | json | event = "provider.fallback"`
4. **Manual override**: If automatic failover is not enabled:
   - Update agent config to use alternate provider
   - Restart pods: `kubectl rollout restart deployment/startd8-agent-runtime -n agents`
5. **Recovery**: When primary provider recovers, revert config and monitor for 15 minutes

## Escalation

| Level | Contact | When |
|-------|---------|------|
| L1 | On-call engineer | Initial response |
| L2 | platform-engineering | Unresolved after 30min |
| L3 | Platform team | Infrastructure issues |
| Vendor | LLM provider support | Provider-side outage |

**Slack Channel**: #startd8-dev
