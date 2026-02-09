# StartD8 SDK Grafana Dashboards

Pre-built Grafana dashboards for monitoring the StartD8 SDK via OpenTelemetry.

## Dashboards

| Dashboard | File | Description |
|-----------|------|-------------|
| SDK Overview | `startd8-sdk-overview.json` | Request rate, latency, tokens, errors, logs |
| Cost Tracking | `startd8-cost-tracking.json` | Spend by model, cost per request, budget alerts |

## Prerequisites

- **Grafana** 9.0+
- **Tempo** datasource (traces)
- **Mimir** or Prometheus datasource (metrics)
- **Loki** datasource (logs)
- **Alloy** or OTel Collector receiving on `localhost:4317` (gRPC)

## Import via Grafana UI

1. Open Grafana → **Dashboards** → **Import**
2. Click **Upload JSON file** and select the dashboard JSON
3. Select your Tempo, Mimir, and Loki datasources when prompted
4. Click **Import**

## Import via Provisioning

Copy the JSON files to your Grafana provisioning directory:

```bash
cp dashboards/*.json /etc/grafana/provisioning/dashboards/
```

Add a provisioning config at `/etc/grafana/provisioning/dashboards/startd8.yaml`:

```yaml
apiVersion: 1
providers:
  - name: startd8
    type: file
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: false
```

Restart Grafana to load the dashboards.

## Datasource Variables

Both dashboards use templated datasource variables:

- `${DS_TEMPO}` — Tempo datasource for traces
- `${DS_MIMIR}` — Mimir/Prometheus datasource for metrics
- `${DS_LOKI}` — Loki datasource for logs

On import, Grafana will prompt you to map these to your actual datasource names.

## Activating OTel in the SDK

```bash
export STARTD8_OTEL=enabled
# or
export STARTD8_OTEL=auto  # only if OTel packages are installed
```

Or programmatically:

```python
from startd8.framework import AgentFramework
fw = AgentFramework(enable_otel=True)
```

## Trace ↔ Log Drill-Down

The dashboards support trace-to-log correlation:

1. Click a trace in Tempo → see correlated logs in Loki via `trace_id`
2. Click a `trace_id` in Loki → jump to the full trace in Tempo
