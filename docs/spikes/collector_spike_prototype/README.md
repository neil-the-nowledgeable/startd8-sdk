# Collector span-metrics spike — throwaway prototype

Supporting scripts for `../RUNTIME_OBSERVABILITY_COLLECTOR_SPIKE.md`. **Throwaway** —
kept for reproducibility, NOT wired into the benchmark runner.

## Reproduce

```bash
# 1. Vendor the collector (v0.156.0, darwin_arm64) into /tmp/collector_spike/
mkdir -p /tmp/collector_spike
curl -sL -o /tmp/collector_spike/otelcol.tar.gz \
  https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.156.0/otelcol-contrib_0.156.0_darwin_arm64.tar.gz
python3 -c "import tarfile; tarfile.open('/tmp/collector_spike/otelcol.tar.gz').extractall('/tmp/collector_spike', filter='data')"

# 2. Copy these scripts + config next to the binary
cp *.py collector-config.yaml /tmp/collector_spike/

# 3. Run (needs opentelemetry-sdk + otlp grpc exporter on the driving python)
python3 /tmp/collector_spike/run_sandboxed.py        # THE critical test: collector under the sandbox
python3 /tmp/collector_spike/descriptor_match.py     # 4/4 descriptor scrape-and-match
python3 /tmp/collector_spike/test_egress_denied.py   # loopback allowed / egress denied control
python3 /tmp/collector_spike/measure_boot.py         # boot-to-ready
python3 /tmp/collector_spike/measure.py              # convergence lag + RSS
```

## Files

| File | Purpose |
|---|---|
| `collector-config.yaml` | The working span-metrics config (loopback-only, tuned to the `span-metrics-connector` descriptor profile). |
| `emit_spans.py` | OTel-SDK emitter: SERVER-kind spans, `service.name`, mixed OK/ERROR → OTLP/gRPC 127.0.0.1:4317. |
| `run_sandboxed.py` | **Critical.** Runs the collector under the repo's `run_service_sandboxed` (seatbelt loopback-only) + client emit/scrape/match. |
| `descriptor_match.py` | Reconstructs the real `MetricDescriptor` and runs the FR-4 scrape-and-match presence check. |
| `test_egress_denied.py` | Negative control: loopback bind/recv works, external `1.1.1.1:443` connect is `PermissionError`. |
| `measure_boot.py` / `measure.py` | Boot-to-ready, convergence lag, RSS (sandboxed). |
| `run_unsandboxed.py` / `verify_red.py` | Baseline (no sandbox) RED-surface confirmation. |
