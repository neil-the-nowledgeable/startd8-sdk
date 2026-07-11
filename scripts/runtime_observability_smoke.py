#!/usr/bin/env python3
# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""End-to-end smoke for the runtime observability-fidelity path (B1 runtime).

Vendors `otelcol-contrib` (the version the spike pinned), then exercises the PRODUCTION
code — `SpanMetricsCollector` + `poll_binding` + `check_descriptor_binding` — against a
REAL collector: emit a handful of OTLP server spans, let the span-metrics connector derive
`calls_total`, and bind-check the descriptor RED surface. This is the one confirmation only
a live collector can give; everything else is fixture-tested.

    python3 scripts/runtime_observability_smoke.py            # download (cached) + run
    make runtime-o11y-smoke

Exit 0 = bound (coverage 1.0). 2 = ran but did not fully bind. 3 = skipped (OTel SDK
absent — install `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-grpc`).
"""

from __future__ import annotations

import argparse
import platform
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

DEFAULT_VERSION = "0.156.0"
CACHE = _REPO / ".cache"


def ensure_collector(version: str) -> Path:
    """Download + extract otelcol-contrib for this platform (cached). Returns the binary."""
    sysname = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64", "amd64": "amd64"}.get(
        platform.machine().lower()
    )
    if not sysname or not arch:
        raise SystemExit(f"unsupported platform {platform.system()}/{platform.machine()}")

    dest = CACHE / f"otelcol-contrib-{version}"
    binary = dest / "otelcol-contrib"
    if binary.is_file():
        return binary

    asset = f"otelcol-contrib_{version}_{sysname}_{arch}.tar.gz"
    url = (
        "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/"
        f"download/v{version}/{asset}"
    )
    dest.mkdir(parents=True, exist_ok=True)
    print(f"↓ downloading {asset} …")
    tgz = dest / asset
    urllib.request.urlretrieve(url, tgz)
    with tarfile.open(tgz) as tf:
        tf.extract("otelcol-contrib", dest)  # extract just the binary
    binary.chmod(0o755)
    tgz.unlink(missing_ok=True)
    print(f"✓ collector at {binary}")
    return binary


def emit_server_spans(endpoint: str, service_name: str, ok: int = 8, err: int = 3) -> None:
    """Emit OK + ERROR SERVER spans (the span-metrics connector's RED input) via OTLP/gRPC."""
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.trace import SpanKind, Status, StatusCode

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    tracer = provider.get_tracer("runtime-o11y-smoke")
    for _ in range(ok):
        with tracer.start_as_current_span("Charge", kind=SpanKind.SERVER) as s:
            s.set_status(Status(StatusCode.OK))
    for _ in range(err):
        with tracer.start_as_current_span("Charge", kind=SpanKind.SERVER) as s:
            s.set_status(Status(StatusCode.ERROR))
    provider.force_flush()
    provider.shutdown()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", default=DEFAULT_VERSION)
    ap.add_argument("--service", default="checkoutservice")
    args = ap.parse_args()

    try:
        import opentelemetry.exporter.otlp.proto.grpc.trace_exporter  # noqa: F401
    except Exception:
        print("SKIP: OTel SDK/OTLP exporter not installed "
              "(pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc)")
        return 3

    from startd8.observability.metric_descriptor import profile_for
    from startd8.observability.runtime_fidelity import SpanMetricsCollector

    binary = ensure_collector(args.version)
    descriptor = profile_for("span-metrics-connector")

    with tempfile.TemporaryDirectory() as td:
        print("▶ starting collector (production SpanMetricsCollector) …")
        with SpanMetricsCollector(str(binary), Path(td)) as collector:
            print(f"▶ emitting server spans for {args.service!r} (8 OK + 3 ERROR) …")
            emit_server_spans("127.0.0.1:4317", args.service)
            print("▶ polling collector /metrics for the RED surface …")
            binding = collector.poll_binding(descriptor, args.service, settle_s=8.0, cap_s=15.0)

    print("\n── runtime binding ──────────────────────────────────────────")
    print(f"  outcome  : {binding.outcome}")
    print(f"  coverage : {binding.coverage}")
    for axis, bound in (binding.axes or {}).items():
        print(f"  {'BOUND  ' if bound else 'UNBOUND'}  {axis}")
    if binding.reason:
        print(f"  reason   : {binding.reason}")

    if binding.outcome == "bound" and binding.coverage == 1.0:
        print("\n✓ PASS — the runtime path binds the RED surface against a live collector.")
        return 0
    print("\n✗ did not fully bind (see axes/outcome above).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
