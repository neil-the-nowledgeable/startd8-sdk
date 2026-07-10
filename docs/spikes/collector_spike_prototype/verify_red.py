"""Boot collector with fixed config, emit spans, settle, confirm exact RED surface:
calls_total{service_name,status_code} nonzero for ERROR + OK, duration_milliseconds_bucket.
"""
import subprocess, time, sys, urllib.request, os, signal

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
METRICS_URL = "http://127.0.0.1:8889/metrics"


def scrape():
    try:
        with urllib.request.urlopen(METRICS_URL, timeout=1.0) as r:
            return r.read().decode()
    except Exception:
        return None


proc = subprocess.Popen([BIN, "--config", CFG], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True, start_new_session=True)
try:
    for _ in range(200):
        if scrape() is not None:
            break
        time.sleep(0.05)
    subprocess.run([sys.executable, "/tmp/collector_spike/emit_spans.py",
                    "checkoutservice", "8", "3"], capture_output=True, text=True, timeout=60)
    # settle: wait for calls_total to become nonzero (counter delta accumulation)
    body = None
    for _ in range(60):
        body = scrape()
        if body and any(l.startswith("calls_total") and not l.rstrip().endswith(" 0")
                        for l in body.splitlines()):
            break
        time.sleep(0.1)
    print("=== calls_total lines ===")
    for l in (body or "").splitlines():
        if l.startswith("calls_total"):
            print(l)
    print("\n=== duration_milliseconds_bucket (le=+Inf only) + count ===")
    for l in (body or "").splitlines():
        if l.startswith("duration_milliseconds_bucket") and 'le="+Inf"' in l:
            print(l)
        if l.startswith("duration_milliseconds_count"):
            print(l)
finally:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        pass
