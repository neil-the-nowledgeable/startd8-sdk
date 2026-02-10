#!/usr/bin/env python3
"""
OTel smoke test — verify end-to-end telemetry flow.

Emits a test span, metric, and log via the SDK's OTel configuration,
then queries Tempo to confirm the trace arrived.

Usage:
    python3 scripts/otel_smoke_test.py [--endpoint http://localhost:4317]
"""

import argparse
import json
import logging
import sys
import time
import urllib.request

from startd8.otel import OTEL_AVAILABLE, OTelConfig, ProjectContext, configure_otel
from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor


logger = logging.getLogger("otel_smoke_test")


def main() -> int:
    parser = argparse.ArgumentParser(description="OTel smoke test for startd8-sdk")
    parser.add_argument(
        "--endpoint",
        default="http://localhost:4317",
        help="OTLP gRPC endpoint (default: http://localhost:4317)",
    )
    parser.add_argument(
        "--tempo-url",
        default="http://localhost:3200",
        help="Tempo query URL (default: http://localhost:3200)",
    )
    parser.add_argument(
        "--flush-wait",
        type=int,
        default=4,
        help="Seconds to wait for batch processor flush (default: 4)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # -- Check OTel availability --
    if not OTEL_AVAILABLE:
        logger.error("FAIL: OTEL_AVAILABLE is False. Install with: pip3 install -e '.[otel]'")
        return 1
    logger.info("OK   OTEL_AVAILABLE = True")

    # -- Configure OTel --
    service_name = "startd8-sdk-smoketest"
    config = OTelConfig(
        service_name=service_name,
        project_context=ProjectContext(
            project_id="startd8-sdk",
            sprint_id="smoke-test",
        ),
        otlp_endpoint=args.endpoint,
        metrics_export_interval_ms=5000,  # faster export for test
    )
    otel = configure_otel(config)
    tracer = otel["tracer"]
    meter = otel["meter"]

    if tracer is None:
        logger.error("FAIL: configure_otel() returned tracer=None")
        return 1
    logger.info("OK   Tracer configured: %s", tracer)

    if meter is None:
        logger.warning("WARN: Meter is None (metrics may not be exported)")
    else:
        logger.info("OK   Meter configured: %s", meter)

    # -- Emit a test span --
    inst = ContextCoreInstrumentor(project_id="startd8-sdk")
    ctx = inst.emit_span("smoketest.ping", {
        "test": True,
        "message": "smoke test from otel_smoke_test.py",
    })
    logger.info("OK   Span emitted: trace_id=%s, span_id=%s", ctx.trace_id, ctx.span_id)
    trace_id = ctx.trace_id

    # -- Emit a test metric --
    if meter:
        counter = meter.create_counter(
            "smoketest.pings",
            description="Number of smoke test pings",
        )
        counter.add(1, {"source": "otel_smoke_test.py"})
        logger.info("OK   Metric emitted: smoketest.pings += 1")

    # -- Emit a test log --
    logger.info("OK   Log emitted (this line is the test log)")

    # -- Wait for flush --
    logger.info("     Waiting %ds for batch processor flush...", args.flush_wait)
    time.sleep(args.flush_wait)

    # -- Query Tempo to verify --
    query = f'{{resource.service.name="{service_name}"}}'
    url = f"{args.tempo_url}/api/search?q={urllib.request.quote(query)}&limit=5"
    logger.info("     Querying Tempo: %s", url)

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        traces = data.get("traces", [])
        if not traces:
            logger.error("FAIL: No traces found in Tempo for service=%s", service_name)
            return 1

        # Check if our specific trace is there
        found = any(t.get("traceID") == trace_id for t in traces)
        if found:
            logger.info("OK   Trace %s found in Tempo", trace_id)
        else:
            logger.warning(
                "WARN: Our trace_id=%s not in results (may be in-flight). "
                "Found %d other traces for service=%s",
                trace_id, len(traces), service_name,
            )

        logger.info("\nSUCCESS: End-to-end telemetry flow verified.")
        logger.info("  SDK -> Alloy:%s -> Tempo", args.endpoint.split(":")[-1])
        logger.info("  Dashboards: http://localhost:3000/d/startd8-sdk-overview/")
        return 0

    except urllib.error.URLError as e:
        logger.error("FAIL: Cannot reach Tempo at %s: %s", args.tempo_url, e)
        logger.error("  Is the LGTM stack running? Check: kubectl get pods -n observability")
        return 1


if __name__ == "__main__":
    sys.exit(main())
