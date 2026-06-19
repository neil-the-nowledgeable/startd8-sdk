# Tier 0 — S4 optional StartD8 fan-out (FR-4 / FR-4a / FR-4b)

This is an **operator patch guide**, not an automated mutator. The default Tier 0 path uses the
OTel Demo's **shipped stack only** (Jaeger + Prometheus + Grafana + OpenSearch [+ Pyroscope]). Fan-out
to StartD8-owned backends is opt-in.

## When to use

- You want demo telemetry in **this repo's Grafana/Loki stack** or a **Tempo** instance without
  replacing the demo's own Jaeger UI.
- You accept **loopback-only** export and TLS for any routable collector endpoint (FR-4a).

## Design constraints (FR-4b)

1. **Dedicated pipelines** — fan-out receivers/exporters must not share queue/backpressure with the
   demo's default pipelines. Add a separate `service.pipelines` entry (e.g. `traces/startd8`,
   `metrics/startd8`).
2. **Bounded queue** — cap the fan-out exporter queue so a slow StartD8 backend cannot stall demo
   export (`sending_queue.queue_size`, `num_consumers`).
3. **No mutation of default demo paths** — append-only patch; keep Jaeger/Prometheus receivers intact.

## Patch sketch

Copy the demo collector config and **append** (adjust hostnames/ports):

```yaml
exporters:
  otlp/startd8:
    endpoint: 127.0.0.1:4317
    tls:
      insecure: true
    sending_queue:
      enabled: true
      queue_size: 256
      num_consumers: 2

service:
  pipelines:
    traces/startd8:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/startd8]
    metrics/startd8:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/startd8]
```

Mount the patched file via compose override:

```yaml
# compose.startd8-fanout.yaml (local only — do not commit secrets)
services:
  otel-collector:
    volumes:
      - ./otelcol-config.startd8.yaml:/etc/otelcol-config.yaml:ro
```

Bring up with:

```bash
docker compose -f compose.yaml -f compose.observability.yaml -f compose.startd8-fanout.yaml up -d
```

## Verification

Fan-out does **not** change the §4 acceptance table — attestation still targets the demo's Jaeger and
Prometheus. After patching, optionally confirm spans arrive at your StartD8 backend separately; do
not wire fan-out into `attest_coverage.py` unless you add explicit FR-4 acceptance rows.

## Security

- Bind fan-out OTLP to `127.0.0.1` unless you terminate TLS on a routable interface (FR-4a).
- Never commit API keys or cloud exporter credentials into the demo tree.
