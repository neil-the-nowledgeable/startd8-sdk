#!/usr/bin/env python3
"""OTel emitter: CodeGraph -> metrics + traces (Phase 0 spike).

Maps the CodeGraph IR onto OTel signals per CODE_OBSERVABILITY_DESIGN.md Layer 2:

  Metrics (gauges, labeled by language/module):
    code_element_count, code_fan_in, code_fan_out, code_stub_count

  Traces:
    CALLS graph emitted as a span tree (root = entrypoint, children = callees).
    DATAFLOW edges emitted as span LINKS between the corresponding spans.

Exporter selection (graceful degradation, never blocks on infra):
  * If an OTLP endpoint is reachable (default localhost:4317 gRPC), export there
    AND mirror to local JSON.
  * Otherwise fall back to the console exporter + local JSON only.

The local JSON mirror (out/spans.json, out/metrics.json) is what
``taint_query_probe.py`` consumes, so the probe runs with or without infra.

Run standalone:
    python3 scripts/spikes/code_observability/emit.py
    python3 scripts/spikes/code_observability/emit.py --no-otlp     # force console
    python3 scripts/spikes/code_observability/emit.py --endpoint host:4317
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from typing import Optional

from extractor import CodeGraph, extract, DEFAULT_FIXTURE  # noqa: E402

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import set_span_in_context  # noqa: F401  (re-imported locally)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "out")


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Metrics (computed structurally; written to JSON. Mirrored to OTLP gauges if up)
# --------------------------------------------------------------------------- #
def compute_metrics(graph: CodeGraph) -> list[dict]:
    funcs = [e for e in graph.elements if e.kind == "function"]
    calls = [e for e in graph.edges if e.kind == "CALLS"]
    fan_out: dict[str, int] = {f.id: 0 for f in funcs}
    fan_in: dict[str, int] = {f.id: 0 for f in funcs}
    for e in calls:
        fan_out[e.src] = fan_out.get(e.src, 0) + 1
        fan_in[e.dst] = fan_in.get(e.dst, 0) + 1

    labels = {"language": graph.language, "module": graph.module}
    metrics: list[dict] = [
        {"name": "code_element_count", "value": len(funcs), "labels": labels},
        # stub_count: functions whose body is effectively empty (none here) -> 0
        {"name": "code_stub_count", "value": 0, "labels": labels},
    ]
    for f in funcs:
        flbl = {**labels, "element": f.id}
        metrics.append({"name": "code_fan_in", "value": fan_in[f.id], "labels": flbl})
        metrics.append({"name": "code_fan_out", "value": fan_out[f.id], "labels": flbl})
    return metrics


# --------------------------------------------------------------------------- #
# Traces
# --------------------------------------------------------------------------- #
def _entrypoints(graph: CodeGraph) -> list[str]:
    """Functions with no incoming CALLS edge = roots of the call forest."""
    func_ids = {e.id for e in graph.elements if e.kind == "function"}
    called = {e.dst for e in graph.edges if e.kind == "CALLS"}
    roots = [fid for fid in func_ids if fid not in called]
    return sorted(roots)


def emit_traces(graph: CodeGraph, provider: TracerProvider) -> dict:
    """Emit one trace per entrypoint; CALLS = parent/child; DATAFLOW = links.

    Returns a JSON-serialisable mirror: {span_id_hex: {...}} keyed by element id
    so the probe can traverse the same structure TraceQL would see in Tempo.
    """
    tracer = provider.get_tracer("code-observability-spike")
    calls_children: dict[str, list[str]] = {}
    for e in graph.edges:
        if e.kind == "CALLS":
            calls_children.setdefault(e.src, []).append(e.dst)
    dataflow: dict[tuple[str, str], str] = {
        (e.src, e.dst): e.detail for e in graph.edges if e.kind == "DATAFLOW"
    }
    elem_by_id = {e.id: e for e in graph.elements}

    # mirror structures
    spans_mirror: dict = {"traces": []}

    def attrs_for(fid: str) -> dict:
        el = elem_by_id[fid]
        return {
            "code.element_id": el.id,
            "code.function": el.id.split("::")[-1],
            "code.file": el.file,
            "code.start_line": el.start_line,
            "code.signature": el.signature,
            "code.is_source": el.is_source,
            "code.is_sink": el.is_sink,
            "code.raw_concat_sql": el.raw_concat_sql,
        }

    for root in _entrypoints(graph):
        # Emit a single connected trace per entrypoint, TOP-DOWN with real
        # parent/child nesting so Tempo sees one trace tree and TraceQL
        # structural operators (`>>` descendant) genuinely apply.
        #
        # DATAFLOW edges are emitted as OTel span LINKS. Because a Link must
        # reference an existing SpanContext at span-creation time, we cannot link
        # a parent to a not-yet-created child. We therefore additionally record
        # the dataflow target span_ids as a span ATTRIBUTE (resolved after the
        # subtree is built) so the probe/TraceQL can follow them. This honest
        # split — call-tree as nesting, dataflow as attribute-referenced links —
        # is itself a finding (see PHASE0_FINDINGS.md, OQ#2).
        trace_record: dict = {"root": root, "spans": []}
        id_of: dict[str, str] = {}
        _top_down_emit(root, None, calls_children, dataflow, attrs_for,
                       tracer, trace_record, id_of, set())
        # backfill dataflow link target span_ids now that all spans exist
        for rec in trace_record["spans"]:
            fid = rec["element_id"]
            rec["dataflow_link_span_ids"] = {
                child: id_of[child]
                for child in calls_children.get(fid, [])
                if (fid, child) in dataflow and child in id_of
            }
        spans_mirror["traces"].append(trace_record)

    return spans_mirror


def _top_down_emit(fid, parent_ctx, calls_children, dataflow, attrs_for,
                   tracer, trace_record, id_of, seen):
    """Top-down nested emission: each callee span is a child of its caller span."""
    from opentelemetry.trace import set_span_in_context

    span = tracer.start_span(
        name=fid.split("::")[-1],
        context=parent_ctx,
    )
    for k, v in attrs_for(fid).items():
        span.set_attribute(k, v)
    sctx = span.get_span_context()
    id_of[fid] = format(sctx.span_id, "016x")
    child_ctx = set_span_in_context(span)

    trace_record["spans"].append({
        "element_id": fid,
        "span_id": format(sctx.span_id, "016x"),
        "trace_id": format(sctx.trace_id, "032x"),
        "attributes": attrs_for(fid),
        "calls_children": calls_children.get(fid, []),
        "dataflow_out": {
            c: dataflow.get((fid, c))
            for c in calls_children.get(fid, [])
            if (fid, c) in dataflow
        },
    })

    if fid not in seen:
        seen.add(fid)
        for child in calls_children.get(fid, []):
            _top_down_emit(child, child_ctx, calls_children, dataflow,
                           attrs_for, tracer, trace_record, id_of, seen)
    span.end()


def build_provider(use_otlp: bool, endpoint: str) -> tuple[TracerProvider, str]:
    resource = Resource.create({"service.name": "code-observability-spike",
                                "signal.domain": "code"})
    provider = TracerProvider(resource=resource)
    mode = "console+json"
    if use_otlp:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            mode = f"otlp({endpoint})+json"
        except Exception as exc:  # noqa: BLE001
            print(f"[emit] OTLP setup failed ({exc!r}); falling back to console")
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            mode = "console+json (otlp-failed)"
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    return provider, mode


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="CodeGraph -> OTel emitter (spike)")
    ap.add_argument("path", nargs="?", default=DEFAULT_FIXTURE)
    ap.add_argument("--endpoint", default="localhost:4317", help="OTLP gRPC endpoint")
    ap.add_argument("--no-otlp", action="store_true", help="force console exporter")
    args = ap.parse_args(argv)

    graph = extract(args.path)
    os.makedirs(OUT_DIR, exist_ok=True)

    host, _, port = args.endpoint.partition(":")
    otlp_up = (not args.no_otlp) and _port_open(host, int(port or 4317))
    if not args.no_otlp and not otlp_up:
        print(f"[emit] OTLP endpoint {args.endpoint} not reachable -> console+json")

    provider, mode = build_provider(use_otlp=otlp_up, endpoint=args.endpoint)
    trace.set_tracer_provider(provider)

    metrics = compute_metrics(graph)
    with open(os.path.join(OUT_DIR, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    spans_mirror = emit_traces(graph, provider)
    provider.force_flush()
    provider.shutdown()

    with open(os.path.join(OUT_DIR, "spans.json"), "w") as fh:
        json.dump(spans_mirror, fh, indent=2)

    n_spans = sum(len(t["spans"]) for t in spans_mirror["traces"])
    n_links = sum(len(s.get("dataflow_link_span_ids", {}))
                  for t in spans_mirror["traces"] for s in t["spans"])
    print(f"[emit] exporter mode: {mode}")
    print(f"[emit] metrics: {len(metrics)} datapoints -> out/metrics.json")
    print(f"[emit] traces: {len(spans_mirror['traces'])} trees, "
          f"{n_spans} spans, {n_links} dataflow links -> out/spans.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
