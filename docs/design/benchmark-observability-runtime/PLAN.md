# Runtime Observability-Fidelity — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-10
**Requirements:** [REQUIREMENTS.md](REQUIREMENTS.md) (v0.3.1)
**Precedent:** the shipped static B1 (`observability_fidelity_static`, `CellResult.observability_coverage`, scorecard D6) and the behavioral harness (`benchmark_matrix/behavioral/execute.py`, `sandbox.py`).

---

## Topology (v1, loopback only, no Prometheus binary)

```
generated service (gRPC, 127.0.0.1:$PORT)
   │  launched WRAPPED in its OTel auto-instrument agent (FR-2)
   │  env: OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:$OTLP  OTEL_TRACES_EXPORTER=otlp
   ▼ OTLP/gRPC traces (server spans from the behavioral suite's traffic)
otelcol-contrib sidecar (127.0.0.1:$OTLP)  — OTLP receiver → spanmetrics connector → prometheus exporter :$PROM/metrics
   ▼ scrape /metrics (FR-4 scrape-and-match — no Prometheus)
descriptor-driven presence check (shared verification binding logic) → runtime_observability_coverage
```

## Steps

### Step 0 — Preconditions / provisioning (OQ-4)
- Vendor `otelcol-contrib` (has the `spanmetrics` connector) per platform, provisioned at prepare time like the Go stubs. A static span-metrics collector config (OTLP receiver → spanmetrics → prometheus exporter on loopback).
- Confirm the Python (`opentelemetry-instrument`) / Node auto-instrument agents are installable/available under the sandbox caps. **Python-first.**
- Confirm/hoist `extract_service_hints` so the behavioral harness can build the descriptor (§Reference-Audit).

### Step 1 — Instrument the launch (FR-2)
- `behavioral/contract.py` `resolve_serve_command`: add a language-keyed **auto-instrument wrapper** (Python: prefix `opentelemetry-instrument`; Node: `--require @opentelemetry/auto-instrumentations-node/register`). Languages without an agent (Go) return "not instrumentable" → FR-7 degraded.
- `execute.py`: when `runtime_observability` is on, inject `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_TRACES_EXPORTER` into `extra_env` (after the env-scrub, like `$PORT`).

### Step 2 — Collector sidecar lifecycle (FR-3)
- In `run_behavioral_cell` (behind the flag): start the collector subprocess in the sandbox (loopback, scrubbed env, resource caps) BEFORE the service; await its `/metrics` (or health) readiness; ensure teardown of BOTH in the existing `finally` (SIGTERM→SIGKILL group).

### Step 3 — Converge + scrape-and-match (FR-4, FR-8)
- After the behavioral suite runs (its RPC traffic = the spans), **poll** the collector `/metrics` until the descriptor's throughput series appears or timeout (FR-8).
- Parse `/metrics` (Prometheus text) into (name → set of label-sets). Reuse the **shared `verification`/descriptor binding logic**: for each RED axis (throughput name, service-identity label, error selector), check presence. `runtime_observability_coverage` = bound RED axes / total.

### Step 4 — Referenced descriptor (FR-5)
- Reconstruct the service's `MetricDescriptor` from the seed/onboarding via `resolve_descriptor` (the generator's own resolution). Synthesize the RED expectation (throughput, latency bucket, error selector) — the same template the generator emits.

### Step 5 — Result + honesty (FR-6, FR-7)
- `CellResult`: add `runtime_observability_coverage: Optional[float]` + `observability_runtime: Optional[Dict]` (profile, traces_received, metrics_seen, per-axis, outcome ∈ {bound, no-telemetry, degraded}).
- FR-7: `degraded` (collector/agent/convergence failure) ⇒ `coverage=None` (excluded, NOT 0.0); `no-telemetry` (zero traces) ⇒ a real low signal; else the bound coverage. Reported-not-scored — never touches `quality`.

### Step 6 — Surface (reuse D6)
- Extend the scorecard's observability section to show the runtime coverage alongside static (static readiness vs runtime fidelity), reported-not-scored. A static-high / runtime-low gap = "wired but not actually emitting" — a headline insight.

### Step 7 — Tests
- Unit: `/metrics` parser + descriptor presence check (fixtures of real collector output). Auto-instrument wrapper resolution per language (incl. Go → not-instrumentable). FR-7 outcomes (degraded vs no-telemetry vs bound). All without a live collector (fixture the scrape).
- One integration test behind a marker (real collector + a tiny instrumented Python service) if a vendored collector is available in CI; else skipped, degrade-honest.

## Sequencing & risk

0 → 1 → 2 → 3 → 4 → 5 → 6 → 7. **Highest risk = Step 0/2** (collector provisioning + sidecar lifecycle in the sandbox) — spike it first with a throwaway before wiring the executor. Everything is behind `runtime_observability` (default off), so the default fleet is untouched (FR-1) and the executor's hot path is unchanged unless opted in. The scrape-and-match choice (no Prometheus) removes the single biggest moving part.

## Requirements coverage

| FR | Step |
|----|------|
| FR-1 opt-in | 5 (flag) / all gated |
| FR-2 auto-inject | 1 |
| FR-3 collector sidecar | 0, 2 |
| FR-4 scrape-and-match | 3 |
| FR-5 descriptor referenced | 4 |
| FR-6 reported-not-scored result | 5, 6 |
| FR-7 three-way degrade-honest | 5 |
| FR-8 convergence gate | 3 |
| FR-9 bounded cost | 2, 3 (timeouts) |

*v0.1 — grounded in the behavioral harness + sandbox; ready to pair with the v0.3.1 requirements for CRP.*
