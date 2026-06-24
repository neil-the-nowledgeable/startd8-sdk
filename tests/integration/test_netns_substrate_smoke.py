"""Linux-GATED live smoke for the shared-netns substrate (OQ-7 — the netns analog of the macOS
Seatbelt repro in CONTAINMENT_SPIKE.md §0).

This is the PROOF the substrate is viable: inside ONE shared rootless netns it spins up two trivial
gRPC peers + a client and asserts BOTH things the macOS Seatbelt profile could not give at once:

  (a) gRPC dial-out between loopback peers WORKS — a client connects to a server over 127.0.0.1
      (the exact thing Seatbelt DENIED), AND
  (b) external egress is UNREACHABLE — a connect to 1.1.1.1:443 from inside the netns times out /
      is refused (containment by construction; the netns has no route out).

It runs ONLY on Linux with a functional rootless ``unshare -rn``. Everywhere else (macOS dev host,
hardened kernels without user namespaces) it SKIPS with a clear reason — it is never a false pass.

The smoke uses raw TCP sockets to STAND IN for "gRPC dial-out" deliberately: under the broken macOS
Seatbelt profile raw loopback connect SUCCEEDED while gRPC FAILED, so a raw-socket loopback success
is the *weaker* claim — if even gRPC works in netns (it does: shared real loopback stack), raw
certainly does. To keep the smoke dependency-light and hermetic, the in-netns cell runner is a
self-contained Python script using only stdlib sockets; it proves the netns property (shared loopback
reachable + egress denied) which is what makes gRPC dial-out work. A heavier gRPC variant can be
layered on the same substrate later without changing the verdict.
"""
from __future__ import annotations

import textwrap

import pytest

from startd8.benchmark_matrix.netns_substrate import (
    netns_available,
    run_cell_in_shared_netns,
)

pytestmark = pytest.mark.integration

# Skip the whole module off-Linux / where rootless netns is not functional, with a precise reason.
if not netns_available():
    import sys

    _reason = (
        "shared-netns smoke requires Linux + functional rootless `unshare -rn`; "
        + (
            "host is Darwin/macOS (`unshare` absent)"
            if sys.platform == "darwin"
            else "`unshare -rn` not functional on this host (kernel may forbid user namespaces)"
        )
    )
    pytest.skip(_reason, allow_module_level=True)


# In-netns cell runner: two loopback peers + a client + an egress probe, all sharing the one netns
# loopback. Emits the marked JSON payload the host parser reads. Pure stdlib — no third-party deps.
_CELL_RUNNER_SRC = textwrap.dedent(
    """
    import json, socket, threading, time

    BEGIN = "<CELL_RESULT_BEGIN>"
    END = "<CELL_RESULT_END>"

    def _serve(ready_evt, port_box):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))            # shared netns loopback
        port_box.append(s.getsockname()[1])
        s.listen()
        ready_evt.set()
        try:
            for _ in range(4):
                conn, _addr = s.accept()
                conn.sendall(b"PEER-OK")
                conn.close()
        except OSError:
            pass

    results = []

    # (a) gRPC-style dial-out between two loopback peers in the SHARED netns.
    peer_reach = False
    detail = ""
    try:
        ready = threading.Event(); box = []
        t = threading.Thread(target=_serve, args=(ready, box), daemon=True)
        t.start()
        if not ready.wait(timeout=5.0):
            raise RuntimeError("peer never bound")
        port = box[0]
        with socket.create_connection(("127.0.0.1", port), timeout=3.0) as c:
            got = c.recv(16)
        peer_reach = (got == b"PEER-OK")
        detail = got.decode(errors="replace")
    except Exception as e:
        detail = "%s: %s" % (type(e).__name__, e)
    results.append({"name": "loopback_peer_reach", "passed": peer_reach, "detail": detail})

    # (b) external egress MUST be unreachable (no route out of the netns).
    egress_denied = False
    egress_detail = ""
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3.0).close()
        egress_detail = "CONNECTED (containment FAILED)"
    except Exception as e:
        egress_denied = True
        egress_detail = "%s: %s" % (type(e).__name__, e)
    results.append({"name": "egress_denied", "passed": egress_denied, "detail": egress_detail})

    coverage = sum(1 for r in results if r["passed"]) / len(results)
    payload = {"coverage": coverage, "results": results}
    print(BEGIN + json.dumps(payload) + END)
    """
).strip()


# Real-gRPC cell runner — the claim that ACTUALLY matters. Under the broken macOS Seatbelt profile a
# raw loopback connect SUCCEEDED while gRPC's connect FAILED, so the raw-socket runner above is the
# *weaker* proof. This variant stands up a real gRPC server + client over the shared-netns loopback and
# asserts the channel goes ready (the exact thing Seatbelt denied) AND egress stays denied. Validated on
# Linux 2026-06-24 (coverage 1.0). Skips when grpcio is absent rather than weakening the assertion.
_GRPC_CELL_RUNNER_SRC = textwrap.dedent(
    """
    import json, socket
    import grpc
    from concurrent import futures

    BEGIN = "<CELL_RESULT_BEGIN>"; END = "<CELL_RESULT_END>"
    results = []

    srv = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    port = srv.add_insecure_port("127.0.0.1:0")   # shared netns loopback
    srv.start()
    ok, detail = False, ""
    try:
        ch = grpc.insecure_channel("127.0.0.1:%d" % port)
        grpc.channel_ready_future(ch).result(timeout=6.0)
        ok, detail = True, "gRPC channel ready over shared-netns 127.0.0.1"
        ch.close()
    except Exception as e:
        detail = "%s: %s" % (type(e).__name__, e)
    results.append({"name": "grpc_loopback_connect", "passed": ok, "detail": detail})

    egress_denied, ed = False, ""
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=3.0).close()
        ed = "CONNECTED (containment FAILED)"
    except Exception as e:
        egress_denied, ed = True, "%s: %s" % (type(e).__name__, e)
    results.append({"name": "egress_denied", "passed": egress_denied, "detail": ed})

    coverage = sum(1 for r in results if r["passed"]) / len(results)
    print(BEGIN + json.dumps({"coverage": coverage, "results": results}) + END)
    """
).strip()


def test_shared_netns_grpc_loopback_works_and_egress_denied(tmp_path):
    """The verdict test: in one shared netns, loopback peers reach each other AND egress is denied."""
    runner = tmp_path / "cell_runner.py"
    runner.write_text(_CELL_RUNNER_SRC)

    res = run_cell_in_shared_netns(["python3", str(runner)], timeout=60.0)

    # Substrate launched (we only reach here on Linux with functional unshare).
    assert res.available, f"netns substrate should be available here; violation={res.violation}"
    assert res.network_isolated, "cell must report running inside a fresh netns"
    assert res.violation is None, f"unexpected cell violation: {res.violation}\nstderr={res.stderr}"
    assert res.payload is not None, f"no payload parsed; stdout tail:\n{res.stdout[-2000:]}"

    by_name = {r["name"]: r for r in res.payload["results"]}

    # (a) gRPC-loopback analog: peers reach each other over the shared netns 127.0.0.1.
    assert by_name["loopback_peer_reach"]["passed"], (
        "loopback peer dial-out failed in the shared netns "
        f"(detail={by_name['loopback_peer_reach']['detail']})"
    )
    # (b) containment by construction: external egress is unreachable.
    assert by_name["egress_denied"]["passed"], (
        "external egress was REACHABLE inside the netns — containment broken "
        f"(detail={by_name['egress_denied']['detail']})"
    )

    # Both true → the substrate gives gRPC-loopback + egress-deny SIMULTANEOUSLY (what Seatbelt can't).
    assert res.payload["coverage"] == 1.0


def test_shared_netns_REAL_grpc_connects_and_egress_denied(tmp_path):
    """The strong verdict: a REAL gRPC channel goes ready over the shared-netns loopback (the exact
    thing macOS Seatbelt denied) while egress stays denied. Skips if grpcio is not installed."""
    pytest.importorskip("grpc", reason="grpcio not installed; raw-socket smoke covers the substrate")
    runner = tmp_path / "grpc_cell_runner.py"
    runner.write_text(_GRPC_CELL_RUNNER_SRC)

    res = run_cell_in_shared_netns(["python3", str(runner)], timeout=60.0)

    assert res.available and res.network_isolated and res.violation is None, (
        f"netns cell failed: violation={res.violation}\nstderr={res.stderr}"
    )
    assert res.payload is not None, f"no payload; stdout tail:\n{res.stdout[-2000:]}"
    by_name = {r["name"]: r for r in res.payload["results"]}
    assert by_name["grpc_loopback_connect"]["passed"], (
        "REAL gRPC channel did NOT go ready in the shared netns "
        f"(detail={by_name['grpc_loopback_connect']['detail']})"
    )
    assert by_name["egress_denied"]["passed"], (
        "external egress was REACHABLE inside the netns — containment broken "
        f"(detail={by_name['egress_denied']['detail']})"
    )
    assert res.payload["coverage"] == 1.0
