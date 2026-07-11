# OTel + ContextCore Integration Guide

How `run_prime_contractor.py` in **startd8-work** was wired to emit telemetry to the local Wayfinder stack (Grafana/Tempo/Mimir/Loki via Alloy).

## Prerequisites

- Local Wayfinder observability stack running (`kubectl apply -k k8s/observability/`)
- OTLP endpoint available at `localhost:4317` (gRPC, via Alloy)
- `contextcore` package installed (from wayfinder repo)
- `startd8[otel]` installed (brings `opentelemetry-api`, `opentelemetry-sdk`)

## What Was Done

**Single file changed:** `startd8-work/run_prime_contractor.py` (~15 lines added)

### 1. Graceful import block

```python
try:
    from startd8.otel import OTelConfig, ProjectContext, configure_otel
    from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
```

Script works identically without the observability packages installed.

### 2. OTel configuration in `main()`

```python
if OTEL_AVAILABLE:
    configure_otel(
        OTelConfig(
            service_name="startd8-work-prime-contractor",
            project_context=ProjectContext(
                project_id="startd8-work",
                project_name="StartD8 Work — Legal Review",
                task_id="LEGAL-GEN-001",
            ),
            otlp_endpoint="http://localhost:4317",
        )
    )
```

This sets up the OTel TracerProvider and MeterProvider with OTLP gRPC export. The `ProjectContext` injects ContextCore resource attributes (`io.contextcore.project.id`, etc.) into all spans.

### 3. Instrumentor passed to PrimeContractorWorkflow

```python
instrumentor = None
if OTEL_AVAILABLE:
    instrumentor = ContextCoreInstrumentor(
        project_id="startd8-work",
        agent_id="prime-contractor",
    )

return PrimeContractorWorkflow(
    ...,
    instrumentor=instrumentor,
)
```

`PrimeContractorWorkflow` already calls `instrumentor.emit_span()`, `emit_event()`, `emit_metric()`, and `emit_insight()` throughout execution. Without an instrumentor it falls back to `LoggingInstrumentor` (stdout only).

## Dependencies Installed

```bash
# From startd8-work venv:
pip install -e "/path/to/wayfinder[all]"    # contextcore + OTel exporters
pip install "startd8[otel]"                  # OTel API/SDK
```

## Replicating for Another Script

To add observability to any script that uses `PrimeContractorWorkflow` or `LeadContractorWorkflow`:

1. Add the `try/except` import block (step 1 above)
2. Call `configure_otel()` before creating the workflow — set `service_name` to identify your script
3. Pass `instrumentor=ContextCoreInstrumentor(project_id=..., agent_id=...)` to the workflow constructor

## Verification

```bash
# Smoke test (no workflow run needed):
python3 -c "
from startd8.otel import OTelConfig, ProjectContext, configure_otel
from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor
otel = configure_otel(OTelConfig(
    service_name='test',
    project_context=ProjectContext(project_id='test'),
    otlp_endpoint='http://localhost:4317',
))
inst = ContextCoreInstrumentor(project_id='test')
ctx = inst.emit_span('test.span', {'test': True})
print(f'Span emitted: trace_id={ctx.trace_id}')
"

# Confirm in Tempo:
curl -s 'http://localhost:3200/api/search?q=\{+resource.service.name+=+"test"+\}&limit=5' | python3 -m json.tool

# Or in Grafana UI: Explore > Tempo > { resource.service.name = "startd8-work-prime-contractor" }
```

## API Reference

| Component | Location in startd8-sdk |
|-----------|------------------------|
| `OTelConfig` | `src/startd8/otel.py` |
| `ProjectContext` | `src/startd8/otel.py` |
| `configure_otel()` | `src/startd8/otel.py` |
| `ContextCoreInstrumentor` | `src/startd8/contractors/adapters/contextcore.py` |
| `PrimeContractorWorkflow` | `src/startd8/contractors/prime_contractor.py` |

## Date

2026-02-08
