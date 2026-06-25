"""M2 live validation: build the m2driver image + the full fleet -> bring the fleet up -> run
Adapter B (the in-fleet driver container) over the live mesh -> assert 100% step coverage on the
reference mesh, then break payment and assert ONLY the checkout step fails (live per-service
attribution). macOS Docker.

Driver-container-on-fleet (the chosen wiring): Adapter B runs as a one-off container ON the internal
`fleet` network and dials peers by service-DNS, so M1's egress-deny is preserved (the driver never
needs host access — it prints its per-step JSON to stdout, which `docker compose run` captures).

Reuses validate_m1's build recipes + compose generation; adds the m2driver image + the two journey
runs (healthy + payment-stopped).

Run:  PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m2
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from startd8.benchmark_matrix.fleet.compose import FLEET_NETWORK, generate_compose_dict
from startd8.benchmark_matrix.fleet.containerize import docker_available
from startd8.benchmark_matrix.fleet.validate_m1 import (
    PROBE, _await_ready, _build_one, _compose, _subset_specs,
)

WT = Path(__file__).resolve().parents[4]
SRC = WT / "src"
DRIVER_IMAGE = "r3/m2driver:latest"
DRIVER_SERVICE = "m2driver"

# The full backend fleet (checkout's closure + recommendation = all 8 backends + redis).
FULL_SUBSET = ["checkoutservice", "recommendationservice"]


def _image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def _build_driver_image() -> bool:
    """Build the m2driver image: a python+grpc container running fleet.adapter_b on the fleet net.
    Stages a MINIMAL package tree (empty __init__ overrides) so importing adapter_b does not pull the
    heavy real fleet/behavioral __init__ cascade — just demo_pb2 + journey + services + adapter_b."""
    if _image_exists(DRIVER_IMAGE):
        print(f"[m2] driver image {DRIVER_IMAGE} present — skip", flush=True)
        return True
    ctx = Path(tempfile.mkdtemp(prefix="m2-driver-"))
    pkg = ctx / "app" / "startd8" / "benchmark_matrix"
    (pkg / "behavioral").mkdir(parents=True)
    (pkg / "fleet").mkdir(parents=True)
    for d in (ctx / "app" / "startd8", pkg, pkg / "behavioral", pkg / "fleet"):
        (d / "__init__.py").write_text("")  # empty overrides — no heavy import cascade
    beh, fleet = SRC / "startd8/benchmark_matrix/behavioral", SRC / "startd8/benchmark_matrix/fleet"
    for f in ("demo_pb2.py", "demo_pb2_grpc.py"):
        shutil.copy(beh / f, pkg / "behavioral" / f)
    for f in ("journey.py", "services.py", "adapter_b.py"):
        shutil.copy(fleet / f, pkg / "fleet" / f)
    (ctx / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "RUN pip install --no-cache-dir grpcio protobuf typing_extensions\n"
        "COPY app /app\n"
        "ENV PYTHONPATH=/app\n"
        'ENTRYPOINT ["python", "-m", "startd8.benchmark_matrix.fleet.adapter_b"]\n'
    )
    print("[m2] building m2driver image ...", flush=True)
    r = subprocess.run(["docker", "build", "-t", DRIVER_IMAGE, str(ctx)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[m2] driver build FAILED\n{(r.stderr or '')[-1500:]}", flush=True)
    return r.returncode == 0


def _run_driver(workdir: Path) -> dict | None:
    """Run the m2driver one-off on the fleet network; parse its per-step JSON from stdout.

    ``--no-deps`` is REQUIRED: m2driver depends_on the backends, and without it `compose run` would
    (re)start the driver's dependencies — reviving a service we deliberately stopped for the
    break-payment attribution test. The backends are already up (via `up -d` + the readiness wait), so
    the driver just attaches to the fleet network and runs."""
    r = _compose(workdir, "run", "--rm", "--no-deps", DRIVER_SERVICE, check=False, timeout=120)
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    print(f"[m2] driver produced no JSON. stdout:\n{r.stdout}\nstderr:\n{r.stderr}", flush=True)
    return None


def main() -> int:
    if not docker_available():
        print("docker absent — skip", flush=True)
        return 0

    specs = _subset_specs(FULL_SUBSET)
    contestant = [s for s in specs if not s.is_infra]
    print(f"[m2] fleet = {[s.name for s in specs]}", flush=True)

    # 1) build the driver image + all backend images (build-if-missing).
    if not _build_driver_image():
        print("=== M2 FAIL: driver image build failed ===", flush=True)
        return 1
    for s in contestant:
        if not _build_one(s.name):
            print(f"=== M2 FAIL: {s.name} image build failed ===", flush=True)
            return 1

    # 2) generate compose + inject the probe (readiness) and the m2driver (profile => not auto-started).
    compose = generate_compose_dict(specs)
    compose["services"][PROBE] = {
        "image": "alpine:3.20", "command": "sleep infinity",
        "networks": [FLEET_NETWORK], "depends_on": [s.name for s in specs],
    }
    compose["services"][DRIVER_SERVICE] = {
        "image": DRIVER_IMAGE, "networks": [FLEET_NETWORK],
        "depends_on": [s.name for s in contestant], "profiles": ["driver"],
    }
    workdir = Path(tempfile.mkdtemp(prefix="m2-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))

    failures: list[str] = []
    try:
        print("[m2] docker compose up -d (backends + probe) ...", flush=True)
        _compose(workdir, "up", "-d", timeout=300)
        for s in contestant:
            if not _await_ready(workdir, s.name, s.dial_port):
                logs = _compose(workdir, "logs", "--no-color", "--tail", "30", s.name, check=False)
                failures.append(f"{s.name} never ready")
                print(f"[m2] NOT ready: {s.name}\n{(logs.stdout or '')[-800:]}", flush=True)
        if failures:
            raise RuntimeError("fleet not ready")

        # 3) HEALTHY mesh -> Adapter B must score 100% step coverage.
        print("[m2] running Adapter B over the healthy mesh ...", flush=True)
        healthy = _run_driver(workdir)
        if healthy is None:
            failures.append("driver produced no result (healthy)")
        else:
            print(f"[m2] healthy: coverage={healthy['unweighted_coverage']:.2f} "
                  f"failed={healthy['failed_steps']}", flush=True)
            for st in healthy["steps"]:
                print(f"    - {st['name']}: {'PASS' if st['passed'] else 'FAIL'} ({st['detail']})", flush=True)
            if healthy["unweighted_coverage"] != 1.0:
                failures.append(f"healthy mesh coverage {healthy['unweighted_coverage']} != 1.0")

        # 4) BREAK payment -> ONLY checkout's step must fail (live per-service attribution).
        print("[m2] stopping paymentservice -> re-running Adapter B (attribution) ...", flush=True)
        _compose(workdir, "stop", "paymentservice", check=False, timeout=60)
        broken = _run_driver(workdir)
        if broken is None:
            failures.append("driver produced no result (payment-broken)")
        else:
            print(f"[m2] payment-broken: failed={broken['failed_steps']}", flush=True)
            if broken["failed_steps"] != ["checkout"]:
                failures.append(f"break-payment attribution: expected only [checkout] to fail, "
                                f"got {broken['failed_steps']}")

    finally:
        print("[m2] tearing down ...", flush=True)
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)

    result = {"failures": failures, "ok": not failures}
    print("[m2] RESULT: " + json.dumps(result), flush=True)
    if failures:
        for f in failures:
            print("   x " + f, flush=True)
        print("=== M2 FAIL ===", flush=True)
        return 1
    print("=== M2 PASS: Adapter B 100% on the reference mesh; break-payment -> only checkout failed ===",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
