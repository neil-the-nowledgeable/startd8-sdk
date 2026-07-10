"""Emit a handful of SERVER-kind spans with service.name + mixed OK/ERROR status.

Exports OTLP/gRPC to 127.0.0.1:4317 (the collector's receiver). This is the
minimal proof that exercises the spanmetrics connector — no full gRPC service
needed. Usage: python3 emit_spans.py [service_name] [n_ok] [n_err] [endpoint]
"""
import sys
import time

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import SpanKind, Status, StatusCode

service_name = sys.argv[1] if len(sys.argv) > 1 else "checkoutservice"
n_ok = int(sys.argv[2]) if len(sys.argv) > 2 else 8
n_err = int(sys.argv[3]) if len(sys.argv) > 3 else 3
endpoint = sys.argv[4] if len(sys.argv) > 4 else "http://127.0.0.1:4317"

resource = Resource.create({"service.name": service_name})
provider = TracerProvider(resource=resource)
exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
# SimpleSpanProcessor exports each span immediately (tighter convergence measurement).
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("spike")

first_span_wall = None
for i in range(n_ok):
    with tracer.start_as_current_span("/PlaceOrder", kind=SpanKind.SERVER) as span:
        span.set_attribute("rpc.system", "grpc")
        span.set_attribute("rpc.service", "checkout.CheckoutService")
        span.set_status(Status(StatusCode.OK))
        time.sleep(0.01)
    if first_span_wall is None:
        first_span_wall = time.time()

for i in range(n_err):
    with tracer.start_as_current_span("/PlaceOrder", kind=SpanKind.SERVER) as span:
        span.set_attribute("rpc.system", "grpc")
        span.set_status(Status(StatusCode.ERROR, "simulated failure"))
        time.sleep(0.01)

provider.force_flush()
provider.shutdown()
print(f"EMITTED service={service_name} ok={n_ok} err={n_err} -> {endpoint}")
print(f"FIRST_SPAN_EXPORTED_AT={first_span_wall:.3f}")
