"""Prove the loopback-only seatbelt profile actually DENIES external egress while
ALLOWING loopback. Two servers under run_service_sandboxed:
  A. loopback echo server -> client connects on loopback  (should be READY)
  B. server that tries to connect to an EXTERNAL host at startup -> egress blocked
Also does a direct egress probe from inside the profile.
"""
import sys, socket, time
from pathlib import Path

sys.path.insert(0, "/Users/neilyashinsky/Documents/dev/startd8-sdk/src")
from startd8.benchmark_matrix.sandbox import run_service_sandboxed, SandboxConfig

WS = Path("/tmp/collector_spike/workspace")

LOOPBACK_SERVER = r'''
import socket, os
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(os.environ["PORT"]))); s.listen(5)
while True:
    c,_ = s.accept(); c.sendall(b"hello-loopback"); c.close()
'''

# Server that first tries EGRESS to a public IP:443, reports result, then binds loopback.
EGRESS_PROBE_SERVER = r'''
import socket, os, sys
egress_ok = None
try:
    e = socket.create_connection(("1.1.1.1", 443), timeout=3.0)
    egress_ok = True; e.close()
except Exception as ex:
    egress_ok = f"BLOCKED:{type(ex).__name__}"
sys.stderr.write(f"EGRESS_RESULT={egress_ok}\n"); sys.stderr.flush()
# now bind loopback so readiness succeeds and we can report
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(os.environ["PORT"]))); s.listen(5)
while True:
    c,_ = s.accept(); c.close()
'''


def loopback_client(port):
    with socket.create_connection(("127.0.0.1", port), timeout=3.0) as c:
        return c.recv(64).decode()


def noop_client(port):
    return "connected-loopback-ok"


def run_case(name, code, client, port):
    (WS / f"{name}.py").write_text(code)
    cfg = SandboxConfig(no_network=True, wall_timeout_s=30.0)
    res = run_service_sandboxed(
        server_cmd=[sys.executable, str(WS / f"{name}.py")],
        workspace=WS, port=port, client=client, cfg=cfg,
        readiness_timeout_s=10.0, extra_env={"PORT": str(port)},
    )
    print(f"--- {name} ---")
    print("  ready:", res.ready, "| isolation:", res.isolation_level,
          "| egress_denied:", res.network_isolated)
    print("  violation:", res.violation)
    print("  client_outcome:", res.client_outcome)
    # surface the EGRESS_RESULT line if present
    for line in (res.server_stderr or "").splitlines():
        if "EGRESS_RESULT" in line:
            print("  ", line.strip())
    print()


if __name__ == "__main__":
    run_case("loopback_srv", LOOPBACK_SERVER, loopback_client, 45001)
    run_case("egress_probe_srv", EGRESS_PROBE_SERVER, noop_client, 45002)
