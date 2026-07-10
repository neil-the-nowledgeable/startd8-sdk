"""THE CRITICAL TEST: run otelcol-contrib UNDER the repo's run_service_sandboxed.

The collector is the long-lived 'server'. run_service_sandboxed wraps it in the
seatbelt loopback-only profile (egress denied, 127.0.0.1 allowed), waits for the
/metrics port (readiness), then the client(port) callback:
  1. emits spans to 127.0.0.1:4317 (loopback OTLP connect)
  2. scrapes 127.0.0.1:8889/metrics (loopback connect)
  3. runs the descriptor scrape-and-match
If seatbelt blocks the collector's loopback BIND, readiness fails and the cell
degrades (violation set) -- that would be the topology-killer. This proves it does not.
"""
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

REPO_SRC = "/Users/neilyashinsky/Documents/dev/startd8-sdk/src"
sys.path.insert(0, REPO_SRC)

from startd8.benchmark_matrix.sandbox import run_service_sandboxed, SandboxConfig, sandbox_caps
from startd8.observability.metric_descriptor import profile_for

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
PROM_PORT = 8889          # readiness = collector's /metrics port
OTLP_ENDPOINT = "http://127.0.0.1:4317"
METRICS_URL = "http://127.0.0.1:8889/metrics"


def parse_and_match(text):
    import re
    _LINE = re.compile(r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(\{(?P<labels>[^}]*)\})?\s+(?P<val>.+)$')
    _LBL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
    parsed = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        parsed.setdefault(m.group("name"), []).append(dict(_LBL.findall(m.group("labels") or "")))
    desc = profile_for("span-metrics-connector")
    tp = parsed.get(desc.throughput_metric, [])
    val = desc.service_label_value_tpl.format(service_id="checkoutservice")
    key, _, expected = desc.error_selector.partition("=")
    expected = expected.strip('"')
    return {
        "throughput_present": desc.throughput_metric in parsed,
        "latency_bucket_present": desc.latency_bucket_metric in parsed,
        "service_identity_bound": any(l.get(desc.service_label_key) == val for l in tp),
        "error_series_present": any(l.get(key) == expected for l in tp),
    }


def client(port):
    """Runs against the LIVE sandboxed collector. All connects are loopback."""
    out = {}
    # 1. emit spans over loopback OTLP/gRPC to 127.0.0.1:4317
    t_emit = time.monotonic()
    er = subprocess.run([sys.executable, "/tmp/collector_spike/emit_spans.py",
                         "checkoutservice", "8", "3", OTLP_ENDPOINT],
                        capture_output=True, text=True, timeout=60)
    out["emit_rc"] = er.returncode
    out["emit_stdout"] = er.stdout.strip()
    out["emit_stderr"] = er.stderr.strip()[-500:]
    if er.returncode != 0:
        return out
    # 2. poll /metrics (convergence) via loopback scrape on readiness port
    body = None
    conv = None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(METRICS_URL, timeout=1.0) as r:
                body = r.read().decode()
        except Exception:
            body = None
        if body and any(l.startswith("calls_total") and not l.rstrip().endswith(" 0")
                        for l in body.splitlines()):
            conv = time.monotonic() - t_emit
            break
        time.sleep(0.1)
    out["convergence_lag_s"] = conv
    out["match"] = parse_and_match(body) if body else None
    return out


def main():
    caps = sandbox_caps()
    print("sandbox_caps:", caps)
    workspace = Path("/tmp/collector_spike/workspace")
    cfg = SandboxConfig(no_network=True, wall_timeout_s=120.0, mem_mb=2048)
    # server_cmd: the collector. Loopback-only seatbelt profile applied by the sandbox.
    server_cmd = [BIN, "--config", CFG]
    t0 = time.monotonic()
    result = run_service_sandboxed(
        server_cmd=server_cmd,
        workspace=workspace,
        port=PROM_PORT,               # readiness = collector /metrics port bound on loopback
        client=client,
        cfg=cfg,
        readiness_timeout_s=20.0,
    )
    print("\n=== ServiceResult ===")
    print("ready:", result.ready)
    print("isolation_level:", result.isolation_level)
    print("network_isolated (egress denied):", result.network_isolated)
    print("violation:", result.violation)
    print("server_returncode:", result.server_returncode)
    print("duration_s:", round(result.duration_s, 2))
    if result.server_stderr:
        print("server_stderr tail:", result.server_stderr[-800:])
    print("\n=== client_outcome ===")
    co = result.client_outcome or {}
    for k, v in co.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
