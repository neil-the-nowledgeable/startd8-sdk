"""Measure collector boot-to-ready (readiness = /metrics port accepts loopback),
sandboxed via run_service_sandboxed. Client just times the moment it's invoked
(sandbox calls client only after readiness), giving boot ≈ readiness time.
We instrument by having client capture time and comparing to a start marker
passed through a shared list via closure; the sandbox's own readiness poll is the
truth, so we time from Popen to client-called by subtracting client work=0.
"""
import sys, time, statistics
from pathlib import Path

sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-sdk/src")
from startd8.benchmark_matrix.sandbox import run_service_sandboxed, SandboxConfig

BIN = "/tmp/collector_spike/otelcol-contrib"
CFG = "/tmp/collector_spike/collector-config.yaml"
WS = Path("/tmp/collector_spike/workspace")
N = 5
boots = []

for i in range(N):
    marker = {}
    def client(port, marker=marker):
        marker["ready_at"] = time.monotonic()  # sandbox called us => server was ready
        return "ok"
    cfg = SandboxConfig(no_network=True, wall_timeout_s=40.0)
    start = time.monotonic()
    res = run_service_sandboxed(server_cmd=[BIN, "--config", CFG], workspace=WS,
                               port=8889, client=client, cfg=cfg, readiness_timeout_s=20.0)
    if res.ready and "ready_at" in marker:
        boots.append(marker["ready_at"] - start)
    print(f"trial {i}: ready={res.ready} boot_to_ready={marker.get('ready_at', 0)-start:.3f}s")
    time.sleep(0.5)

if boots:
    print(f"\nBOOT_TO_READY (sandboxed): min={min(boots):.3f} "
          f"median={statistics.median(boots):.3f} max={max(boots):.3f} s (n={len(boots)})")
