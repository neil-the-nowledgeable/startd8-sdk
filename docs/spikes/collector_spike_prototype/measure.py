"""Repeatable measurement: boot-to-ready, convergence lag, RSS — sandboxed via
run_service_sandboxed. N trials, report min/median/max.
"""
import sys, time, subprocess, urllib.request, statistics
from pathlib import Path

sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-sdk/src")
from startd8.benchmark_matrix.sandbox import run_service_sandboxed, SandboxConfig

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
OTLP = "http://127.0.0.1:4317"
METRICS_URL = "http://127.0.0.1:8889/metrics"
WS = Path("/tmp/collector_spike/workspace")
N = 3

boot_times, conv_times, rss_vals = [], [], []


def rss_mb_of_otelcol():
    try:
        out = subprocess.run(["pgrep", "-f", "otelcol-contrib --config"],
                             capture_output=True, text=True, timeout=5).stdout.split()
        if not out:
            return None
        pid = out[0]
        rss = subprocess.run(["ps", "-o", "rss=", "-p", pid],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return int(rss) / 1024.0
    except Exception:
        return None


def make_client(store):
    def client(port):
        t_ready = time.monotonic()  # server already ready when client called
        store["rss"] = rss_mb_of_otelcol()
        t_emit = time.monotonic()
        subprocess.run([sys.executable, "/tmp/collector_spike/emit_spans.py",
                        "checkoutservice", "8", "3", OTLP],
                       capture_output=True, text=True, timeout=60)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(METRICS_URL, timeout=1.0) as r:
                    body = r.read().decode()
            except Exception:
                body = ""
            if any(l.startswith("calls_total") and not l.rstrip().endswith(" 0")
                   for l in body.splitlines()):
                store["conv"] = time.monotonic() - t_emit
                return "ok"
            time.sleep(0.05)
        store["conv"] = None
        return "no-converge"
    return client


for i in range(N):
    store = {}
    cfg = SandboxConfig(no_network=True, wall_timeout_s=60.0)
    t0 = time.monotonic()
    res = run_service_sandboxed(
        server_cmd=[BIN, "--config", CFG], workspace=WS, port=8889,
        client=make_client(store), cfg=cfg, readiness_timeout_s=20.0,
    )
    # boot-to-ready ≈ time until readiness probe passed; res.duration includes client.
    # Recompute boot by re-reading: we approximate boot as duration - conv - emit overhead
    # but cleaner: measure readiness separately below. Here capture what we have.
    if res.ready and store.get("conv") is not None:
        conv_times.append(store["conv"])
    if store.get("rss"):
        rss_vals.append(store["rss"])
    print(f"trial {i}: ready={res.ready} conv={store.get('conv')} rss={store.get('rss')} "
          f"total_dur={res.duration_s:.2f} isolation={res.isolation_level}")
    time.sleep(0.5)


def stat(name, xs, unit):
    if not xs:
        print(f"{name}: n/a")
        return
    print(f"{name}: min={min(xs):.3f} median={statistics.median(xs):.3f} "
          f"max={max(xs):.3f} {unit}  (n={len(xs)})")


print()
stat("CONVERGENCE_LAG (span->calls_total nonzero, sandboxed)", conv_times, "s")
stat("COLLECTOR_RSS", rss_vals, "MB")
