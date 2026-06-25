"""M3 live validation: run Adapter B over the reference mesh + 2 broken meshes, score each result,
and assert honest per-service attribution. macOS Docker.

Reuses validate_m2's fleet + driver machinery; adds host-side scoring (fleet.score) and the
break-catalog mesh. The driver image is force-rebuilt so it emits the per-step `culprit` the scorer
needs. A "broken mesh" is produced by `docker compose stop <service>` (the m2 `--no-deps` driver run
keeps the stopped service down) — the cheapest deterministic fault injection.

Exit (PLAN M3): reference mesh -> 100% coverage, no model-fault; break payment -> payment model-fault
+ checkout PROPAGATED (not charged); break catalog -> catalog model-fault + checkout propagated. A
downstream break is never charged to the entry service.

Run:  PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m3
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import yaml

from startd8.benchmark_matrix.fleet.adapter_b import JourneyResult, StepResult
from startd8.benchmark_matrix.fleet.compose import FLEET_NETWORK, generate_compose_dict
from startd8.benchmark_matrix.fleet.containerize import docker_available
from startd8.benchmark_matrix.fleet.score import score_journey, Scorecard
from startd8.benchmark_matrix.fleet.validate_m1 import PROBE, _await_ready, _build_one, _compose, _subset_specs
from startd8.benchmark_matrix.fleet.validate_m2 import (
    DRIVER_IMAGE, DRIVER_SERVICE, FULL_SUBSET, _build_driver_image, _run_driver,
)


def _score(d: dict) -> Scorecard:
    """Reconstruct a JourneyResult from the driver's JSON + score it host-side."""
    r = JourneyResult()
    for st in d["steps"]:
        r.steps.append(StepResult(st["name"], st["passed"], st["detail"], st["weight"], st.get("culprit")))
    return score_journey(r)


def _report(label: str, sc: Scorecard) -> None:
    print(f"[m3] {label}: coverage={sc.unweighted_coverage:.2f} completed={sc.journey_completed} "
          f"confidence={sc.confidence}", flush=True)
    for f in sc.faults:
        via = f" via {f.via}" if f.via else ""
        print(f"      {f.classification}: {f.service} (step {f.step}{via})", flush=True)


def main() -> int:
    if not docker_available():
        print("docker absent — skip", flush=True)
        return 0

    specs = _subset_specs(FULL_SUBSET)
    contestant = [s for s in specs if not s.is_infra]
    print(f"[m3] fleet = {[s.name for s in specs]}", flush=True)

    # force-rebuild the driver (adapter_b now emits per-step culprit) + build-if-missing backends.
    subprocess.run(["docker", "rmi", "-f", DRIVER_IMAGE], capture_output=True)
    if not _build_driver_image():
        print("=== M3 FAIL: driver build failed ===", flush=True)
        return 1
    for s in contestant:
        if not _build_one(s.name):
            print(f"=== M3 FAIL: {s.name} build failed ===", flush=True)
            return 1

    compose = generate_compose_dict(specs)
    compose["services"][PROBE] = {"image": "alpine:3.20", "command": "sleep infinity",
                                  "networks": [FLEET_NETWORK], "depends_on": [s.name for s in specs]}
    compose["services"][DRIVER_SERVICE] = {"image": DRIVER_IMAGE, "networks": [FLEET_NETWORK],
                                           "depends_on": [s.name for s in contestant], "profiles": ["driver"]}
    workdir = Path(tempfile.mkdtemp(prefix="m3-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))

    failures: list[str] = []
    try:
        print("[m3] docker compose up -d ...", flush=True)
        _compose(workdir, "up", "-d", timeout=300)
        for s in contestant:
            if not _await_ready(workdir, s.name, s.dial_port):
                failures.append(f"{s.name} never ready")
        if failures:
            raise RuntimeError("fleet not ready")

        # 1) REFERENCE mesh -> 100% coverage, journey completed, NO model-fault.
        ref = _run_driver(workdir)
        sc = _score(ref) if ref else None
        if sc is None:
            failures.append("no driver result (reference)")
        else:
            _report("reference", sc)
            if sc.unweighted_coverage != 1.0:
                failures.append(f"reference coverage {sc.unweighted_coverage} != 1.0")
            if sc.model_faulted_services:
                failures.append(f"reference mesh wrongly model-faulted {sc.model_faulted_services}")

        # 2) BREAK payment -> payment model-fault + checkout PROPAGATED (not charged).
        print("[m3] stop paymentservice ...", flush=True)
        _compose(workdir, "stop", "paymentservice", check=False, timeout=60)
        sc = _score(_run_driver(workdir))
        _report("break-payment", sc)
        if sc.model_faulted_services != {"paymentservice"}:
            failures.append(f"break-payment: model-faulted {sc.model_faulted_services} != {{payment}}")
        if "checkoutservice" not in sc.propagated_services:
            failures.append("break-payment: checkout not classified propagated")
        if "checkoutservice" in sc.model_faulted_services:
            failures.append("break-payment: checkout WRONGLY charged model-fault for upstream break")
        _compose(workdir, "start", "paymentservice", check=False, timeout=60)
        _await_ready(workdir, "paymentservice", 50051)

        # 3) BREAK catalog -> catalog model-fault + checkout propagated.
        print("[m3] stop productcatalogservice ...", flush=True)
        _compose(workdir, "stop", "productcatalogservice", check=False, timeout=60)
        sc = _score(_run_driver(workdir))
        _report("break-catalog", sc)
        if sc.model_faulted_services != {"productcatalogservice"}:
            failures.append(f"break-catalog: model-faulted {sc.model_faulted_services} != {{catalog}}")
        if "checkoutservice" in sc.model_faulted_services:
            failures.append("break-catalog: checkout WRONGLY charged model-fault for upstream break")

    finally:
        print("[m3] tearing down ...", flush=True)
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)

    print("[m3] RESULT: " + json.dumps({"failures": failures, "ok": not failures}), flush=True)
    if failures:
        for f in failures:
            print("   x " + f, flush=True)
        print("=== M3 FAIL ===", flush=True)
        return 1
    print("=== M3 PASS: per-service attribution correct on reference + break-payment + break-catalog ===",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
