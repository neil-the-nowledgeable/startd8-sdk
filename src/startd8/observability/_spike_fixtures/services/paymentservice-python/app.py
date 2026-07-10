# SPIKE FIXTURE — a Python HTTP service that emits span-metrics-connector-style
# RED metrics *plus* explicit business instruments. This one is deliberately the
# GOOD case: it is instrumented such that the generated span-metrics PromQL binds.
#
# It uses the OTel Collector span-metrics connector convention indirectly: the
# service itself exports spans, and a collector turns them into `calls_total` /
# `duration_milliseconds`. Because the connector metrics are produced by the
# COLLECTOR, not the service source, we model them here as an explicit declaration
# a real onboarding manifest would carry. For the fixture we make the binding
# work by having the service emit the connector names via an OTel meter (a stand
# in — see the spike report's "collector-produced metrics" limitation).

from opentelemetry import metrics
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from prometheus_client import Counter, Histogram
from flask import Flask

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)  # implies http_server_duration (semconv-http)

meter = metrics.get_meter("paymentservice")

# The span-metrics-connector RED surface, declared on the service so the generated
# alerts (which assume this convention) bind. In production these come from the
# collector; here they are explicit so the fixture is self-contained.
calls = meter.create_counter("calls_total")
duration = meter.create_histogram("duration_milliseconds")

# Explicit business instruments (prometheus_client).
charges_total = Counter("payment_charges_total", "Total charge attempts")
charge_latency = Histogram("payment_charge_latency_seconds", "Charge latency")


@app.route("/charge", methods=["POST"])
def charge():
    charges_total.inc()
    return {"ok": True}
