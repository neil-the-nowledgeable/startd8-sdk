"""Prove the scrape-and-match binding check works against the real /metrics.

Reconstructs the span-metrics-connector MetricDescriptor from the SDK, parses a
saved /metrics scrape into (name -> list of label dicts), and checks each RED
axis (throughput name, service-identity label, error selector) is PRESENT.
This is the FR-4 scrape-and-match viability probe.
"""
import re
import sys
import subprocess
import time
import urllib.request
import os
import signal

sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-sdk/src")
from startd8.observability.metric_descriptor import profile_for

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
METRICS_URL = "http://127.0.0.1:8889/metrics"

_LINE = re.compile(r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(\{(?P<labels>[^}]*)\})?\s+(?P<val>.+)$')
_LBL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def parse_metrics(text):
    """text -> {metric_name: [ {label:val,...}, ... ]}"""
    out = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name = m.group("name")
        labels = dict(_LBL.findall(m.group("labels") or ""))
        out.setdefault(name, []).append(labels)
    return out


def scrape():
    try:
        with urllib.request.urlopen(METRICS_URL, timeout=1.0) as r:
            return r.read().decode()
    except Exception:
        return None


def check_axis_presence(parsed, desc, service_id):
    """Emulate the descriptor-driven presence check (FR-4)."""
    results = {}
    # axis 1: throughput metric name present
    results["throughput_metric_present"] = desc.throughput_metric in parsed
    # axis 2: latency bucket present
    results["latency_bucket_present"] = desc.latency_bucket_metric in parsed
    # axis 3: service-identity label present on the throughput series
    tp_series = parsed.get(desc.throughput_metric, [])
    val = desc.service_label_value_tpl.format(service_id=service_id)
    results["service_identity_bound"] = any(
        lbls.get(desc.service_label_key) == val for lbls in tp_series
    )
    # axis 4: error selector present (status_code="STATUS_CODE_ERROR")
    key, _, expected = desc.error_selector.partition("=")
    expected = expected.strip('"')
    results["error_series_present"] = any(
        lbls.get(key) == expected for lbls in tp_series
    )
    return results


def main():
    desc = profile_for("span-metrics-connector")
    print(f"Descriptor: profile={desc.profile}")
    print(f"  throughput_metric      = {desc.throughput_metric!r}")
    print(f"  latency_bucket_metric  = {desc.latency_bucket_metric!r}")
    print(f"  service_label_key      = {desc.service_label_key!r}")
    print(f"  error_selector         = {desc.error_selector!r}")
    print(f"  selector(checkout,err) = {desc.selector('checkoutservice', error=True)}")

    proc = subprocess.Popen([BIN, "--config", CFG], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        for _ in range(200):
            if scrape() is not None:
                break
            time.sleep(0.05)
        subprocess.run([sys.executable, "/tmp/collector_spike/emit_spans.py",
                        "checkoutservice", "8", "3"], capture_output=True, text=True, timeout=60)
        body = None
        for _ in range(60):
            body = scrape()
            if body and "calls_total" in body:
                break
            time.sleep(0.1)
        parsed = parse_metrics(body or "")
        res = check_axis_presence(parsed, desc, "checkoutservice")
        print("\nSCRAPE-AND-MATCH RESULT (FR-4 binding, span-metrics-connector profile):")
        bound = sum(1 for v in res.values() if v)
        for k, v in res.items():
            print(f"  {'BOUND  ' if v else 'UNBOUND'}  {k}")
        print(f"\n  runtime_observability_coverage = {bound}/{len(res)} = {bound/len(res):.2f}")
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    main()
