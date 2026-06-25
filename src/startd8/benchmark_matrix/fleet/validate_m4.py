"""M4 live validation: build the frontend image → boot it (correct + a break-order-id variant) on the
live backend fleet → run the health/contract gate → prove the substitution seam. macOS Docker.

Exit (PLAN M4): a subtly-broken generated frontend (confirmation WITHOUT a real order id) FAILS the
gate and falls to canonical cleanly; Adapter A then completes the journey over the canonical frontend;
a correct generated frontend PASSES and earns the frontend bonus. Here the CORRECT frontend image
stands in as the "canonical" fallback (a known-good frontend; a real run uses the upstream src/frontend).

Both frontends share the r3/frontend:go image (the broken one toggles FRONTEND_BREAK_ORDER_ID=1) and
sit on BOTH the internal `fleet` net (to dial backends by service-DNS) and an `edge` bridge (published
to a host loopback port so the host-run gate's httpx can reach them — the OB ingress pattern).

Run:  PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m4
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
import yaml

from startd8.benchmark_matrix.fleet import frontend_contract as FC
from startd8.benchmark_matrix.fleet import services as S
from startd8.benchmark_matrix.fleet.compose import FLEET_NETWORK, generate_compose_dict
from startd8.benchmark_matrix.fleet.containerize import build_service_image, docker_available
from startd8.benchmark_matrix.fleet.frontend_gate import run_gate, run_journey_http
from startd8.benchmark_matrix.fleet.validate_m1 import PROBE, _await_ready, _build_one, _compose, _subset_specs
from startd8.benchmark_matrix.fleet.validate_m2 import FULL_SUBSET

WT = Path(__file__).resolve().parents[4]
FIX = WT / "tests/unit/benchmark_matrix/behavioral/fixtures"
FRONTEND_IMAGE = "r3/frontend:go"
EDGE = "edge"
# the backends the frontend fans out to (its *_SERVICE_ADDR env).
FRONTEND_DEPS = ("productcatalogservice", "currencyservice", "cartservice",
                 "shippingservice", "checkoutservice", "recommendationservice")
GOOD_PORT, BROKEN_PORT = 18101, 18102


def _image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def _build_frontend() -> bool:
    if _image_exists(FRONTEND_IMAGE):
        print(f"[m4] {FRONTEND_IMAGE} present — skip", flush=True)
        return True
    wd = Path(tempfile.mkdtemp(prefix="m4-frontend-"))
    ref = FIX / "frontend_reference"
    for f in ("main.go", "go.mod"):
        shutil.copy(ref / f, wd / f)
    print("[m4] building r3/frontend:go ...", flush=True)
    res = build_service_image("frontend", wd, "go", target_files=["main.go"], tag=FRONTEND_IMAGE)
    if not res.ok:
        print(f"[m4] frontend build FAILED\n{(res.log or '')[-1500:]}", flush=True)
    return res.ok


def _frontend_env(extra: dict | None = None) -> dict:
    env = {"PORT": "8080"}
    for d in FRONTEND_DEPS:
        s = S.get_service(d)
        env[s.addr_env] = f"{s.name}:{s.dial_port}"
    if extra:
        env.update(extra)
    return env


def _frontend_service(host_port: int, env: dict, deps: list[str]) -> dict:
    return {
        "image": FRONTEND_IMAGE, "environment": env,
        "depends_on": deps, "networks": [FLEET_NETWORK, EDGE],
        "ports": [f"127.0.0.1:{host_port}:8080"],
    }


def _await_http(port: int, timeout: float = 60.0) -> bool:
    url = f"http://127.0.0.1:{port}/_healthz"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=3.0).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(2.0)
    return False


def main() -> int:
    if not docker_available():
        print("docker absent — skip", flush=True)
        return 0

    specs = _subset_specs(FULL_SUBSET)
    contestant = [s for s in specs if not s.is_infra]
    print(f"[m4] backend fleet = {[s.name for s in specs]}", flush=True)

    if not _build_frontend():
        print("=== M4 FAIL: frontend build failed ===", flush=True)
        return 1
    for s in contestant:
        if not _build_one(s.name):
            print(f"=== M4 FAIL: {s.name} build failed ===", flush=True)
            return 1

    compose = generate_compose_dict(specs)
    compose["networks"][EDGE] = {"driver": "bridge"}
    compose["services"][PROBE] = {"image": "alpine:3.20", "command": "sleep infinity",
                                  "networks": [FLEET_NETWORK], "depends_on": [s.name for s in specs]}
    deps = [s.name for s in contestant]
    compose["services"]["frontend"] = _frontend_service(GOOD_PORT, _frontend_env(), deps)
    compose["services"]["frontend-broken"] = _frontend_service(
        BROKEN_PORT, _frontend_env({"FRONTEND_BREAK_ORDER_ID": "1"}), deps)
    workdir = Path(tempfile.mkdtemp(prefix="m4-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))

    good_url, broken_url = f"http://127.0.0.1:{GOOD_PORT}", f"http://127.0.0.1:{BROKEN_PORT}"
    failures: list[str] = []
    try:
        print("[m4] docker compose up -d ...", flush=True)
        _compose(workdir, "up", "-d", timeout=300)
        for s in contestant:
            if not _await_ready(workdir, s.name, s.dial_port):
                failures.append(f"{s.name} never ready")
        if failures:
            raise RuntimeError("backends not ready")
        if not _await_http(GOOD_PORT) or not _await_http(BROKEN_PORT):
            failures.append("frontend(s) never became HTTP-ready")
            raise RuntimeError("frontends not ready")

        # 1) CORRECT frontend → gate PASS → mount generated, earns bonus.
        good = run_gate(good_url)
        bonus = FC.frontend_bonus(good.verdict, good.orchestration_fidelity)
        print(f"[m4] generated: verdict={good.verdict.mounted} stages={ {k.value: v for k, v in good.stage_results.items()} } "
              f"order_id={good.order_id!r} bonus={bonus:.3f}", flush=True)
        if not (good.verdict.passed and good.verdict.mounted == "generated"):
            failures.append(f"correct frontend did not PASS the gate ({good.detail})")
        if not good.order_id:
            failures.append("correct frontend rendered no order id")
        if bonus <= 0:
            failures.append("correct frontend earned no frontend bonus")

        # 2) SUBTLY-BROKEN frontend (confirmation w/o a real order id) → gate FAIL@journey → substitute.
        broken = run_gate(broken_url)
        print(f"[m4] broken: verdict={broken.verdict.mounted} failing_stage={broken.verdict.failing_stage} "
              f"stages={ {k.value: v for k, v in broken.stage_results.items()} }", flush=True)
        if broken.verdict.passed:
            failures.append("subtly-broken frontend wrongly PASSED the gate")
        if broken.verdict.failing_stage != "journey":
            failures.append(f"broken frontend failed at {broken.verdict.failing_stage}, expected journey")
        if broken.verdict.mounted != "canonical-substituted":
            failures.append("broken frontend was not substituted to canonical")

        # 3) FALL TO CANONICAL: Adapter A completes the journey over the canonical (here: the known-good
        #    generated frontend) — proving fail-to-canonical-cleanly + Adapter-A-over-canonical.
        with httpx.Client(base_url=good_url, follow_redirects=False, timeout=10.0) as c:
            jo = run_journey_http(c)
        print(f"[m4] adapter-A over canonical: completed={jo.completed} order_id={jo.order_id!r}", flush=True)
        if not jo.completed:
            failures.append("Adapter A did not complete the journey over the canonical frontend")

    finally:
        print("[m4] tearing down ...", flush=True)
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)

    print("[m4] RESULT: " + json.dumps({"failures": failures, "ok": not failures}), flush=True)
    if failures:
        for f in failures:
            print("   x " + f, flush=True)
        print("=== M4 FAIL ===", flush=True)
        return 1
    print("=== M4 PASS: generated frontend gates GREEN + earns bonus; subtly-broken → substitute "
          "canonical; Adapter A green over canonical ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
