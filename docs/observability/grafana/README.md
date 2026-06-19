# Grafana — StartD8 inter-context outbound (Role 3)

Import `startd8-context-outbound.json` into Grafana when Tempo span-metrics are configured.

**Panels:**
- Outbound request rate by `io.startd8.context.producer_id`
- 5xx error ratio per producer
- p95 latency per producer

**Prerequisites:** Tempo metrics generator or span-metrics connector emitting `traces_spanmetrics_*` series with StartD8 context attributes (`io.startd8.context.producer_id`, `io.startd8.context.outbound`).

**Import:**
```bash
# Grafana UI → Dashboards → Import → upload startd8-context-outbound.json
# Or via API if GRAFANA_URL and API key are configured
```
