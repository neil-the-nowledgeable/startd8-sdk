# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Runtime observability-fidelity — the pieces the behavioral cell orchestrates (B1 runtime).

The static B1 term reads the generated *source* and is optimistic. The runtime form runs the
service, instruments it, lets it emit spans, derives the RED metrics through an OTel Collector
(span-metrics connector), and checks binding against the service's **own live telemetry** — the
strongest observability signal.

This module is the reusable substance (parser + descriptor binding + instrumentation resolver +
collector lifecycle); the behavioral executor orchestrates them behind a flag. Everything is
injectable (launcher / scrape fn), so the logic is unit-tested with a fixtured `/metrics` — no live
collector required. Spec: `docs/design/benchmark-observability-runtime/`.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CollectorUnavailable(Exception):
    """The collector binary is missing or never became ready (→ degraded, not a fail)."""


# ─────────────────────────── collector config ──────────────────────────────

#: The span-metrics collector config validated by the spike. The 4 load-bearing knobs
#: (`namespace: ""`, no explicit span.kind dimension, `resource_to_telemetry_conversion`,
#: `telemetry.metrics.level: none`) are what make `calls_total{service_name,status_code}`
#: appear unprefixed — the exact `span-metrics-connector` descriptor surface. Ship verbatim.
def collector_config(otlp_endpoint: str = "127.0.0.1:4317", prom_endpoint: str = "127.0.0.1:8889") -> str:
    return f"""receivers:
  otlp:
    protocols:
      grpc:
        endpoint: {otlp_endpoint}
connectors:
  spanmetrics:
    namespace: ""
    histogram:
      explicit:
        buckets: [2ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2s]
    metrics_flush_interval: 1s
exporters:
  prometheus:
    endpoint: {prom_endpoint}
    resource_to_telemetry_conversion:
      enabled: true
    enable_open_metrics: false
    add_metric_suffixes: true
service:
  telemetry:
    metrics:
      level: none
    logs:
      level: warn
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [spanmetrics]
    metrics:
      receivers: [spanmetrics]
      exporters: [prometheus]
"""


# ───────────────────────────── /metrics parser ─────────────────────────────

_LINE = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(\{(?P<labels>[^}]*)\})?\s+(?P<val>.+)$")
_LBL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def parse_prometheus_text(text: str) -> Dict[str, List[Dict[str, str]]]:
    """Prometheus exposition text → ``{metric_name: [ {label: value, ...}, ... ]}``."""
    out: Dict[str, List[Dict[str, str]]] = {}
    for line in (text or "").splitlines():
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        labels = dict(_LBL.findall(m.group("labels") or ""))
        out.setdefault(m.group("name"), []).append(labels)
    return out


# ─────────────────────── descriptor binding (scrape-and-match) ──────────────


@dataclass
class RuntimeBinding:
    outcome: str  # "bound" | "no_telemetry" | "degraded"
    coverage: Optional[float]  # None for no_telemetry / degraded (excluded, not 0.0)
    axes: Dict[str, bool] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"outcome": self.outcome, "coverage": self.coverage, "axes": self.axes, "reason": self.reason}


def check_descriptor_binding(parsed: Dict[str, List[Dict[str, str]]], descriptor, service_id: str) -> RuntimeBinding:
    """Presence-check the descriptor's RED axes against a parsed `/metrics` (FR-4).

    Four axes: throughput metric name, latency-bucket name, the service-identity **label**
    bound to *service_id*, and the error-selector **label key** present on the throughput
    series (the KEY, not a specific error value — whether an error occurred is traffic-
    dependent, not a binding property). Coverage = bound / 4.
    """
    tp = descriptor.throughput_metric
    tp_series = parsed.get(tp, [])
    axes: Dict[str, bool] = {}
    axes["throughput_metric"] = tp in parsed
    axes["latency_bucket"] = descriptor.latency_bucket_metric in parsed
    value = descriptor.service_label_value_tpl.format(service_id=service_id)
    axes["service_identity"] = any(s.get(descriptor.service_label_key) == value for s in tp_series)
    err_key = (descriptor.error_selector or "").split("=", 1)[0].split("=~", 1)[0].strip()
    axes["error_selector"] = bool(err_key) and any(err_key in s for s in tp_series)
    bound = sum(1 for v in axes.values() if v)
    return RuntimeBinding(outcome="bound", coverage=round(bound / len(axes), 4), axes=axes)


# ─────────────────────── instrumentation resolution (FR-2) ──────────────────


@dataclass
class InstrumentationSpec:
    argv_prefix: List[str]
    env: Dict[str, str]


def resolve_instrumentation(language: str, *, otlp_endpoint: str, service_id: str) -> Optional[InstrumentationSpec]:
    """The launch-time auto-instrument wrapper for *language*, or None if unsupported.

    Harness-injected (a deployment property, not model skill — NR-3). Python-first
    (`opentelemetry-instrument`), Node via `NODE_OPTIONS`. Languages with no runtime
    auto-instrument agent (Go) return None ⇒ the cell is `degraded`, never blamed (FR-7).
    """
    base = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://{otlp_endpoint}",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_SERVICE_NAME": service_id,
    }
    lang = (language or "").lower()
    if lang == "python":
        return InstrumentationSpec(["opentelemetry-instrument"], base)
    if lang in ("node", "nodejs"):
        return InstrumentationSpec(
            [], {**base, "NODE_OPTIONS": "--require @opentelemetry/auto-instrumentations-node/register"}
        )
    return None


# ──────────────────────────── collector lifecycle ──────────────────────────


def find_collector_binary(explicit: Optional[str] = None) -> Optional[str]:
    """Locate ``otelcol-contrib`` — an explicit path, ``$OTELCOL_CONTRIB_BIN``, or PATH."""
    for cand in (explicit, os.environ.get("OTELCOL_CONTRIB_BIN")):
        if cand and Path(cand).is_file():
            return cand
    from shutil import which
    return which("otelcol-contrib")


class SpanMetricsCollector:
    """Own an ``otelcol-contrib`` span-metrics subprocess on loopback.

    Context manager: writes the config, starts the collector (via ``launcher``), waits for
    ``/metrics`` to answer (else raises :class:`CollectorUnavailable`), and tears the process
    group down on exit. ``launcher`` and ``scrape_fn`` are injectable so tests drive it with a
    fake collector + fixtured ``/metrics`` — no live binary.
    """

    def __init__(
        self,
        collector_bin: str,
        workdir: Path,
        *,
        otlp_endpoint: str = "127.0.0.1:4317",
        prom_endpoint: str = "127.0.0.1:8889",
        launcher: Optional[Callable[..., Any]] = None,
        scrape_fn: Optional[Callable[[str], Optional[str]]] = None,
        ready_timeout_s: float = 5.0,
    ) -> None:
        self.collector_bin = collector_bin
        self.workdir = Path(workdir)
        self.otlp_endpoint = otlp_endpoint
        self.prom_endpoint = prom_endpoint
        self._metrics_url = f"http://{prom_endpoint}/metrics"
        self._launcher = launcher or self._default_launcher
        self._scrape = scrape_fn or self._default_scrape
        self._ready_timeout_s = ready_timeout_s
        self._proc: Any = None

    @staticmethod
    def _default_launcher(argv, cwd):
        import subprocess

        return subprocess.Popen(
            argv, cwd=str(cwd), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _default_scrape(self, url: str) -> Optional[str]:
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                return r.read().decode()
        except Exception:
            return None

    def __enter__(self) -> "SpanMetricsCollector":
        cfg_path = self.workdir / "otelcol-spanmetrics.yaml"
        cfg_path.write_text(collector_config(self.otlp_endpoint, self.prom_endpoint))
        self._proc = self._launcher([self.collector_bin, "--config", str(cfg_path)], self.workdir)
        deadline = time.monotonic() + self._ready_timeout_s
        while time.monotonic() < deadline:
            if self._scrape(self._metrics_url) is not None:
                return self
            time.sleep(0.05)
        self._teardown()
        raise CollectorUnavailable(f"collector /metrics not ready within {self._ready_timeout_s}s")

    def scrape(self) -> Optional[str]:
        return self._scrape(self._metrics_url)

    def poll_binding(self, descriptor, service_id: str, *, settle_s: float = 8.0, cap_s: float = 15.0) -> RuntimeBinding:
        """Poll until the throughput series is present AND non-zero (FR-8), then bind-check.

        A present-but-zero throughput (the counter delta hasn't accumulated on the first scrape)
        is NOT yet converged — poll on. Timeout with no non-zero throughput ⇒ ``no_telemetry``
        (the service emitted nothing usable), never a false pass.
        """
        deadline = time.monotonic() + max(settle_s, cap_s)
        tp = descriptor.throughput_metric
        while time.monotonic() < deadline:
            parsed = parse_prometheus_text(self.scrape() or "")
            if _has_nonzero_throughput(self.scrape() or "", tp):
                return check_descriptor_binding(parsed, descriptor, service_id)
            time.sleep(0.2)
        return RuntimeBinding(outcome="no_telemetry", coverage=None,
                              reason=f"no non-zero {tp!r} within {cap_s}s (service emitted no usable telemetry)")

    def _teardown(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=3)
        except Exception:  # pragma: no cover - best-effort teardown
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass

    def __exit__(self, *exc) -> None:
        self._teardown()


def probe_service_runtime_observability(
    *,
    service_id: str,
    language: str,
    descriptor,
    workdir: Path,
    argv: List[str],
    extra_env: Dict[str, str],
    run_service: Callable[[List[str], Dict[str, str]], Any],
    collector_bin: Optional[str] = None,
    settle_s: float = 8.0,
    cap_s: float = 15.0,
    launcher: Optional[Callable[..., Any]] = None,
    scrape_fn: Optional[Callable[[str], Optional[str]]] = None,
) -> "tuple[Any, Dict[str, Any]]":
    """Run the service under a span-metrics collector and bind-check its live telemetry.

    ``run_service(argv, extra_env)`` is invoked **exactly once** and its return is passed
    back — the behavioral suite must run regardless. When the language isn't
    auto-instrumentable or no collector binary is available, the service runs **plainly**
    (uninstrumented) and the runtime term is ``degraded`` (never a fail, never model-blamed
    — FR-7). Returns ``(service_result, runtime_observability_dict)``.
    """
    def _degraded(reason: str) -> Dict[str, Any]:
        return {"outcome": "degraded", "coverage": None, "profile": getattr(descriptor, "profile", ""),
                "reason": reason}

    spec = resolve_instrumentation(language, otlp_endpoint="127.0.0.1:4317", service_id=service_id)
    binloc = find_collector_binary(collector_bin)
    if spec is None:
        return run_service(argv, extra_env), _degraded(f"language {language!r} not auto-instrumentable")
    if binloc is None:
        return run_service(argv, extra_env), _degraded("otelcol-contrib binary not found")

    argv2 = [*spec.argv_prefix, *argv]
    env2 = {**extra_env, **spec.env}
    try:
        with SpanMetricsCollector(binloc, Path(workdir), launcher=launcher, scrape_fn=scrape_fn) as c:
            sr = run_service(argv2, env2)
            binding = c.poll_binding(descriptor, service_id, settle_s=settle_s, cap_s=cap_s)
        out = binding.to_dict()
        out["profile"] = getattr(descriptor, "profile", "")
        return sr, out
    except CollectorUnavailable as exc:
        # Collector never came up → run the service plainly so behavioral still works.
        return run_service(argv, extra_env), _degraded(str(exc))


def _has_nonzero_throughput(metrics_text: str, throughput_metric: str) -> bool:
    """True if the throughput series is present with a value > 0 (FR-8 convergence)."""
    for line in (metrics_text or "").splitlines():
        if line.startswith("#") or not line.startswith(throughput_metric):
            continue
        m = _LINE.match(line)
        if m and m.group("name") == throughput_metric:
            try:
                if float(m.group("val").split()[0]) > 0:
                    return True
            except ValueError:
                continue
    return False
