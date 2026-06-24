#!/usr/bin/env python3
"""PROTOTYPE fleet driver — bring up the 2-service compose fleet, score it end-to-end, prove egress
denial, tear down. The docker-compose analogue of the netns smoke (NETNS_SUBSTRATE.md §8).

What it asserts (the substrate claim):
  1. service-DNS gRPC: recommendationservice dials productcatalogservice:8080 by name. We confirm the
     REAL inter-service call happened by counting "DIAL ListProducts" lines in productcatalog's
     container logs (the faithful call-counter that replaces the in-process _CallCounter when
     productcatalog is a real container) and feeding that count to run_recommendation_suite as
     stub_calls — so the suite's catalog_dialed observable reflects the real wire call.
  2. coverage 1.0: run_recommendation_suite against the SUT (recommendation excludes inputs, returns
     ids from the catalog, catalog dialed) — proves the inter-service gRPC call produced correct
     behavior end-to-end.
  3. egress denied: exec into a container on the internal network, attempt a TCP connect to
     1.1.1.1:443 — must FAIL (no route out). Network-layer containment.
  4. clean teardown: `docker compose down -v` always runs (finally).

Run:  python3 drive_fleet.py        (exit 0 = substrate proven; non-zero = a claim failed)
Repeatable + also driven by the gated pytest (test_compose_fleet_prototype.py).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT / "src"))

# REUSE the SDK suite + ground truth — do not re-implement scoring.
from startd8.benchmark_matrix.behavioral.recommendation_suite import (  # noqa: E402
    run_recommendation_suite,
)
from startd8.benchmark_matrix.behavioral.recommendation_stubs import (  # noqa: E402
    ENV_PRODUCT_CATALOG,
    recommendation_ground_truth,
)

REC_HOST_PORT = int(os.environ.get("REC_HOST_PORT", "18080"))
PC_SERVICE = "productcatalogservice"
REC_SERVICE = "recommendationservice"
COMPOSE = ["docker", "compose"]


def _run(args, **kw):
    return subprocess.run(args, cwd=str(HERE), text=True, capture_output=True, **kw)


def _compose(*args, check=True, timeout=None):
    env = {**os.environ, "REC_HOST_PORT": str(REC_HOST_PORT)}
    r = subprocess.run([*COMPOSE, *args], cwd=str(HERE), text=True,
                       capture_output=True, env=env, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"compose {' '.join(args)} failed (rc={r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def _pc_dial_count() -> int:
    """Count real inter-service ListProducts dials from productcatalog's container logs."""
    r = _compose("logs", "--no-color", PC_SERVICE, check=False)
    return (r.stdout + r.stderr).count("DIAL ListProducts")


def _wait_rec_ready(timeout=60.0) -> bool:
    """Poll the host-published recommendation port until the gRPC server accepts a connection."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", REC_HOST_PORT), timeout=2.0):
                return True
        except OSError:
            time.sleep(1.0)
    return False


def _egress_denied() -> bool:
    """Attempt a TCP connect to 1.1.1.1:443 from INSIDE the pure-backend productcatalog container
    (on the internal `fleet` network ONLY) — must FAIL (no route out).

    productcatalog is the strictest case: it has no edge network at all, so a successful connect would
    mean the internal network leaks egress (substrate claim FAILS). Uses busybox `nc` (alpine) with a
    short timeout; nc exits 0 on connect, non-zero on failure/timeout.
    """
    # busybox nc: -w sets connect+io timeout (sec). Probe a well-known external host:port.
    probe = "nc -w 5 -z 1.1.1.1 443 && echo EGRESS_OPEN || echo EGRESS_DENIED"
    r = _compose("exec", "-T", PC_SERVICE, "sh", "-c", probe, check=False, timeout=30)
    out = (r.stdout or "") + (r.stderr or "")
    return "EGRESS_DENIED" in out and "EGRESS_OPEN" not in out


def main() -> int:
    # 0) assemble build contexts (vendored stubs + ground-truth products.json) by reusing SDK sources.
    pr = _run(["bash", str(HERE / "prepare_build_context.sh")])
    print(pr.stdout, pr.stderr)
    if pr.returncode != 0:
        print("prepare_build_context.sh failed", file=sys.stderr)
        return 2

    failures = []
    coverage = None
    dialed = None
    try:
        print("[fleet] building + starting 2-service fleet ...")
        _compose("up", "--build", "-d", timeout=900)

        if not _wait_rec_ready():
            raise RuntimeError("recommendationservice did not become ready on host port")

        # Snapshot dial count, run the suite (which triggers real ListRecommendations -> ListProducts),
        # re-read the count, and synthesize stub_calls from the DELTA — the real inter-service signal.
        before = _pc_dial_count()
        gt = recommendation_ground_truth()
        # stub_calls is read by the suite AFTER its RPCs return — so the lambda reports the REAL number
        # of productcatalog dials observed in the container logs during this suite run (honest delta,
        # never floored). This is the faithful inter-service call-counter for a real-container peer.
        suite = run_recommendation_suite(
            REC_HOST_PORT,
            stub_calls=lambda: {ENV_PRODUCT_CATALOG: _pc_dial_count() - before},
            ground_truth=gt,
            catalog_ids=list(gt.catalog.keys()),
        )
        after = _pc_dial_count()
        dialed = after - before

        coverage = suite.coverage
        print(f"[fleet] recommendation suite coverage = {coverage:.3f}")
        print(f"[fleet] productcatalog real dials during suite = {dialed}")
        for rr in suite.results:
            print(f"    - {rr.name}: {'PASS' if rr.passed else 'FAIL'} ({rr.detail})")
        if suite.connect_error:
            failures.append(f"suite connect_error: {suite.connect_error}")
        if coverage < 1.0:
            failures.append(f"coverage {coverage:.3f} < 1.0 (inter-service gRPC call did not produce correct behavior)")
        if dialed <= 0:
            failures.append("productcatalog was never dialed over service-DNS (no DIAL ListProducts log)")

        print("[fleet] checking egress denial from inside a fleet container ...")
        if _egress_denied():
            print("[fleet] egress to 1.1.1.1:443 DENIED (internal network contained it)")
        else:
            failures.append("egress was NOT denied (internal:true network failed to contain)")

    finally:
        print("[fleet] tearing down ...")
        _compose("down", "-v", "--remove-orphans", check=False, timeout=120)

    result = {
        "substrate": "docker-compose-fleet",
        "services": [PC_SERVICE, REC_SERVICE],
        "coverage": coverage,
        "dialed": dialed,
        "egress_denied": not any("egress" in f for f in failures),
        "failures": failures,
    }
    print("[fleet] RESULT: " + json.dumps(result))
    if failures:
        print("[fleet] SUBSTRATE CLAIM FAILED:")
        for f in failures:
            print("   x " + f)
        return 1
    print("[fleet] SUBSTRATE PROVEN: service-DNS gRPC coverage 1.0 + egress denied + clean teardown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
