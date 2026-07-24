# Deploying the collector_enrichment artifact

The generator emits `collector-enrichment/otelcol-business-enrichment.yaml` — a **partial** OTel
Collector config fragment, not a standalone config. It carries two sections you merge into your
existing collector config:

1. a `processors.transform/business` block (stamps `business.criticality` / `business.owner` onto
   spans, keyed by `service.name`), and
2. a `connectors.spanmetrics.dimensions` fragment (promotes `business.criticality` to a queryable
   metric label — emitted only when at least one service has a criticality).

## The three-step merge

Given a generated fragment like:

```yaml
processors:
  transform/business:
    error_mode: ignore
    trace_statements:
      - context: span
        statements:
          - set(attributes["business.criticality"], "critical") where resource.attributes["service.name"] == "frontend"
          - set(attributes["business.owner"], "commerce-team") where resource.attributes["service.name"] == "cartservice"
connectors:
  spanmetrics:
    dimensions:
      - name: business.criticality
```

**1. Add the processor** — copy `processors.transform/business` into your config's `processors:`.

**2. Wire it into the traces pipeline** — add `transform/business` to the traces pipeline's
`processors:` list, **before** whatever consumes the spans (the spanmetrics connector / your trace
exporter), so the attributes are stamped first:

```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [transform/business, batch]   # transform/business added here
      exporters: [spanmetrics, otlp/jaeger]
```

**3. Append the spanmetrics dimension** — merge the `dimensions:` entries into your **existing**
spanmetrics connector (append, don't replace):

```yaml
connectors:
  spanmetrics:
    # ...your existing spanmetrics config...
    dimensions:
      - name: business.criticality      # appended
```

After a collector reload, spans carry `business.criticality` / `business.owner`, and
`calls_total{business_criticality="critical"}` becomes queryable in Prometheus.

## Verify the cutover (parity gate)

Before deleting any hand-written `transform/business` block, confirm the generated one is equivalent:

```bash
startd8 observability enrichment-parity \
  --generated collector-enrichment/otelcol-business-enrichment.yaml \
  --reference path/to/your/hand-written-collector-config.yaml
# exit 0 = parity (safe to retire the mirror) · 1 = mismatch · 2 = unreadable input
```

Parity is **semantic**, not byte-for-byte: a one-statement-per-service generated block matches a
value-grouped hand-written block (`… == "a" or … == "b"`) as long as the resolved
`{service.name: {criticality, owner}}` maps are equal.

## Notes

- **Only `business.criticality` is a metric dimension** (4-value enum, bounded cardinality). `owner`
  is intentionally left as a span attribute only — promoting free-text owners to metric labels would
  explode series cardinality. Use it for trace-level RCA, not aggregation.
- **Regeneration is deterministic** — a re-run with the same manifest is byte-identical. The
  `# provenance: sha256:` header + the `collector_enrichment` block in the run report
  (`fr_coverage`) let you detect when a regen actually changed anything.
- **A manifest with no business context emits no file** — absence is byte-identical to a
  pre-feature run.
