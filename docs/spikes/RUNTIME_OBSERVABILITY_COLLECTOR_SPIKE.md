# Spike: OTel Collector span-metrics under the behavioral sandbox

**Status:** COMPLETE — throwaway prototype, not wired into the runner.
**Date:** 2026-07-10
**Relates to:** `docs/design/benchmark-observability-runtime/{REQUIREMENTS.md,PLAN.md}` (FR-3, FR-4, FR-8, FR-9, OQ-4, OQ-5); `src/startd8/benchmark_matrix/sandbox.py`; `src/startd8/observability/metric_descriptor.py` (`span-metrics-connector` profile).
**Prototype artifacts:** `/tmp/collector_spike/` (collector binary, config, emitter, sandbox drivers). Throwaway — recreatable from this report.

---

## 1. Feasibility verdict

**FEASIBLE — the whole loopback topology works inside the existing behavioral sandbox with no changes to `sandbox.py`.**

`otelcol-contrib` runs under the repo's own `run_service_sandboxed` with the loopback-only Seatbelt profile (`isolation_level = rlimits+seatbelt-loopback`, `network_isolated = True`), binds its OTLP receiver (127.0.0.1:4317) and Prometheus exporter (127.0.0.1:8889) on loopback, receives spans, derives `calls_total` / `duration_milliseconds`, and exposes them on a scrape-able `/metrics` — while external egress is denied. A descriptor-driven scrape-and-match (FR-4) against the real `/metrics` binds **4/4 RED axes** for the `span-metrics-connector` profile.

The load-bearing unknown — *does Seatbelt let the collector's loopback survive while egress stays denied?* — is answered **YES**, verified with a negative control (an in-sandbox outbound connect to `1.1.1.1:443` returns `PermissionError` while loopback bind/accept succeeds in the same profile).

### The load-bearing answers

| Unknown | Result |
|---|---|
| (a) Collector runs under macOS Seatbelt with loopback intact? | **YES.** `ready=True`, `violation=None`, `isolation_level=rlimits+seatbelt-loopback`, egress denied (proven, not asserted). |
| (b) Convergence lag (first span → `calls_total` visible)? | **~2–3s** sandboxed (median 2.7s; cold-start outlier 3.8s). |
| (c) Boot time + memory? | **Boot-to-ready median 0.3s (max 1.5s cold); RSS ~116–138 MB.** |

---

## 2. Environment (pin these)

| Item | Value |
|---|---|
| Host | macOS (Darwin 24.6.0), Apple Silicon **arm64** |
| Collector | **`otelcol-contrib` v0.156.0**, `darwin_arm64`, 97 MB tar.gz → 369 MB binary |
| Download | `https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.156.0/otelcol-contrib_0.156.0_darwin_arm64.tar.gz` |
| SHA256 (asset) | `f5e3a6fbc8cca5e9fc9ce642c5ca16da084b4b6fea3f38a8ad29eea69ddf8e0f` |
| Python | 3.14.5; `opentelemetry-sdk` 1.39.1 + OTLP/gRPC exporter (already present) |
| Sandbox caps | `{rlimits: True, sandbox_exec: True, unshare: False, docker: True}` |

Binary has **no Gatekeeper quarantine block** — only a benign `com.apple.provenance` xattr; it runs directly and under Seatbelt with no `xattr -d` / notarization dance. (If a future host DOES quarantine it, `xattr -dr com.apple.quarantine` at prepare time.)

---

## 3. Working collector config

Two dimensions had to be tuned to match the `span-metrics-connector` descriptor profile (the config gotchas, §7):

```yaml
# Span-metrics spike collector config — loopback only.
# OTLP/gRPC receiver -> spanmetrics connector -> prometheus exporter (/metrics).
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317

connectors:
  spanmetrics:
    # Drop the default "traces.span.metrics" namespace so names are exactly
    # calls_total / duration_milliseconds_* (the descriptor profile expects unprefixed).
    namespace: ""
    histogram:
      explicit:
        buckets: [2ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2s]
    # service.name -> service_name, status.code -> status_code, span.kind/span.name
    # are default/resource-derived dimensions (do NOT list span.kind explicitly —
    # it's a duplicate and fails `validate`).
    metrics_flush_interval: 1s

exporters:
  prometheus:
    endpoint: 127.0.0.1:8889
    resource_to_telemetry_conversion:
      enabled: true          # promotes service.name resource attr -> service_name label
    enable_open_metrics: false
    add_metric_suffixes: true

service:
  telemetry:
    metrics: { level: none }   # don't self-scrape collector internals onto :8889
    logs:    { level: info }
  pipelines:
    traces:  { receivers: [otlp],        exporters: [spanmetrics] }
    metrics: { receivers: [spanmetrics], exporters: [prometheus]  }
```

`otelcol-contrib validate --config collector-config.yaml` → rc 0.

---

## 4. The RED surface actually emitted (real `/metrics`)

After emitting 8 OK + 3 ERROR SERVER-kind spans with `service.name=checkoutservice`:

```
calls_total{service_name="checkoutservice",span_kind="SPAN_KIND_SERVER",span_name="/PlaceOrder",status_code="STATUS_CODE_ERROR", ...} 3
calls_total{service_name="checkoutservice",span_kind="SPAN_KIND_SERVER",span_name="/PlaceOrder",status_code="STATUS_CODE_OK",    ...} 8

duration_milliseconds_bucket{service_name="checkoutservice",status_code="STATUS_CODE_ERROR", ...,le="+Inf"} 3
duration_milliseconds_count{ service_name="checkoutservice",status_code="STATUS_CODE_ERROR", ...} 3
duration_milliseconds_bucket{service_name="checkoutservice",status_code="STATUS_CODE_OK",    ...,le="+Inf"} 8
duration_milliseconds_count{ service_name="checkoutservice",status_code="STATUS_CODE_OK",    ...} 8
```

(Full label set also carries `collector_instance_id`, `job`, `otel_scope_*`, `telemetry_sdk_*` — harmless extras; the presence check keys only on the descriptor axes.)

This matches the `span-metrics-connector` profile exactly:

| Descriptor axis | Expected | Observed | Bound |
|---|---|---|---|
| `throughput_metric` | `calls_total` | `calls_total` | ✅ |
| `latency_bucket_metric` | `duration_milliseconds_bucket` | `duration_milliseconds_bucket` | ✅ |
| `service_label_key` = value | `service_name="checkoutservice"` | present | ✅ |
| `error_selector` | `status_code="STATUS_CODE_ERROR"` | present, count=3 | ✅ |

Running the **real** `profile_for("span-metrics-connector")` from `metric_descriptor.py` + a `/metrics` text parser + per-axis presence check:

```
runtime_observability_coverage = 4/4 = 1.00
```

The ERROR series appears **only** because a span carried ERROR status — a no-telemetry/all-OK service would correctly show a lower/empty error surface, so the three-way FR-7 split is observable from this data.

---

## 5. THE critical result — collector under the sandbox

Driver: the repo's own `run_service_sandboxed(server_cmd=[otelcol-contrib, --config, ...], port=8889, client=...)`, `SandboxConfig(no_network=True)`. The client callback (running in the parent) emits spans to 127.0.0.1:4317 and scrapes 127.0.0.1:8889 — all loopback into the sandboxed collector.

```
sandbox_caps: {rlimits: True, sandbox_exec: True, unshare: False, docker: True}
ready:                 True
isolation_level:       rlimits+seatbelt-loopback
network_isolated:      True          # external egress denied
violation:             None
server_returncode:     0             # clean SIGTERM shutdown
convergence_lag_s:     ~2.0
match:                 {throughput: True, latency_bucket: True,
                        service_identity: True, error_series: True}
```

**Egress-denied negative control** (same loopback-only profile):

```
loopback_srv     : ready=True   client_outcome="hello-loopback"        (127.0.0.1 bind+accept+recv OK)
egress_probe_srv : ready=True   EGRESS_RESULT=BLOCKED:PermissionError   (connect 1.1.1.1:443 blocked)
```

So loopback survives Seatbelt **and** egress is genuinely blocked — exactly the `_wrap_loopback_only` contract in `sandbox.py`. No change to `sandbox.py` was needed; the existing `run_service_sandboxed` + `seatbelt-loopback` profile is sufficient for the collector sidecar.

> Note on the FR-3 topology: in the spike, the collector is the sandboxed **server** and the emitter/scraper run in the parent. In the real dimension the service-under-test is the sandboxed process and the collector is a **sibling sidecar** in the same sandbox. Both are loopback-only servers under the identical profile, so this result transfers; the executor work is lifecycle ordering (start collector → ready → start service → suite → settle → scrape → tear both down in one `finally`), not a new isolation question.

---

## 6. Measurements (feed FR-8 / FR-9)

All sandboxed (`rlimits+seatbelt-loopback`), Apple Silicon.

| Metric | min | median | max | n | Notes |
|---|---|---|---|---|---|
| **Boot-to-ready** (Popen → `/metrics` accepts) | 0.21s | **0.32s** | 1.46s | 5 | max = cold first run |
| **Convergence lag** (span emit → `calls_total` nonzero) | 2.67s | **2.71s** | 3.81s | 3 | max = cold first run |
| **Collector RSS** | 116 MB | **136 MB** | 138 MB | 3 | resident during a cell |

Budget math for **FR-9 (≤ +30s/cell)**: boot (~0.3–1.5s) + suite traffic + settle (~3s) + scrape (<0.1s) + teardown (~0.3s) ≈ **well under +30s**. Convergence is the dominant term.

**FR-8 settle timeout recommendation:** default **poll up to 8s** for the throughput series (covers the 3.8s cold outlier with ~2× margin), hard cap **15s** → then `no-telemetry`. `metrics_flush_interval: 1s` (set above) keeps the connector→exporter flush tight; the ~2.7s floor is dominated by the OTLP export batch + one Prometheus scrape interval, not the flush. OQ-5's "~1–3s" estimate is confirmed (sandboxed, cold-inclusive: 2.7–3.8s).

---

## 7. Config gotchas (getting the dimensions to match the profile)

1. **Metric-name prefix.** The spanmetrics connector defaults to namespace `traces.span.metrics`, yielding `traces_span_metrics_calls_total` — which does **not** match the descriptor's `calls_total`. Fix: `namespace: ""`.
2. **`span.kind` is a default dimension.** Listing it under `dimensions:` fails `validate` with `duplicate dimension name "span.kind"`. Don't declare it; it (and `span.name`, `status.code`) come for free.
3. **`resource_to_telemetry_conversion.enabled: true`** is required so the `service.name` **resource** attribute becomes the `service_name` **label** on the series. Without it, `service_name` is absent and the identity axis is unbound.
4. **`service.telemetry.metrics.level: none`** — otherwise the collector scrapes its own internal metrics onto the same `/metrics` and clutters the surface (harmless but noisy for a presence check).
5. **Scrape-timing artifact:** on the very first scrape after span arrival, `calls_total` can read `0` for a beat (counter just created, delta not yet accumulated in the snapshot) while the histogram `_count` is already correct. The FR-8 poll must wait for the throughput series to be **nonzero**, not merely **present**, to avoid a false-early read.

---

## 8. Scrape-and-match viability (FR-4)

**Viable and cheap.** A ~20-line Prometheus-text parser (`name -> [label-dicts]`) plus the existing `MetricDescriptor` axes (`throughput_metric`, `latency_bucket_metric`, `service_label_key` + `service_label_value_tpl`, `error_selector`) is enough to compute `runtime_observability_coverage` with **no Prometheus binary**. The check reuses `metric_descriptor.profile_for(...)` directly, so runtime and static/BPI fidelity can't diverge on the metric identity. A later `histogram_quantile` replay would need a real Prometheus, but v1 does not.

`extract_service_hints` (reference-audit item) is confirmed at `src/startd8/observability/artifact_generator_context.py:274` — module-level, importable, no behavioral-harness coupling, so descriptor reconstruction (FR-5) is reachable.

---

## 9. What I could NOT verify (honest gaps)

- **Auto-instrumentation (`opentelemetry-instrument`) bonus.** Not run: the agent isn't installed, and the host Python is PEP-668 externally-managed; a throwaway-venv `pip install` was blocked in this environment. **Impact: low.** The connector only needs SERVER-kind spans with `service.name` + OK/ERROR status over OTLP/gRPC — exactly what the SDK emitter produced and the connector consumed 4/4. Auto-instrumentation is a wrapper that yields those same spans; OQ-3 (Python-first `opentelemetry-instrument`) is a packaging/provisioning question, not a topology one. **Recommend** a follow-up micro-spike: `opentelemetry-instrument python grpc_server.py` under the sandbox to confirm the agent (a) installs/starts under the rlimit caps and (b) emits server spans — but it does not gate feasibility.
- **Linux `unshare -rn` path.** This host has `unshare: False` (macOS). The netns loopback path is untested here; only the Seatbelt path is proven. Linux CI should re-run §5.
- **Real sidecar co-location.** The spike sandboxed the collector alone; it did not run collector + a second sandboxed service in the same sandbox invocation simultaneously (§5 note). Both are loopback servers under one profile, so this is an executor-lifecycle task, not an isolation risk — but it's unproven end-to-end.
- **Sustained/concurrent load.** Only ~11 spans/trial. No throughput or memory-under-load numbers; RSS could grow with cardinality (each distinct `span_name` × `status_code` is a series).

---

## 10. Top blockers / recommendations for productionizing

1. **None fatal.** The topology is feasible as-specified; no `sandbox.py` change required.
2. **Ship the config in §3 verbatim** as the vendored static collector config (OQ-4). The four tuned knobs (`namespace:""`, no explicit `span.kind`, `resource_to_telemetry_conversion`, `telemetry.metrics.level:none`) are the difference between binding and silently unbound — bake them in, don't rediscover them.
3. **FR-8 poll = nonzero-throughput, not present** (§7.5). Default 8s, cap 15s.
4. **Provision at prepare time** (OQ-4): 97 MB download / 369 MB on disk per platform, like the Go stubs; strip any `com.apple.quarantine` xattr on macOS.
5. **Follow-up micro-spike** for `opentelemetry-instrument` under the sandbox (venv-based) to close OQ-3 empirically before wiring Step 1.
6. **Re-run §5 on Linux** to prove the `unshare -rn` loopback path before claiming cross-platform.
