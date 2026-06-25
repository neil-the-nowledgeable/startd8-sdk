"""M6 live capstone: drive Adapter B over the live fleet in three configurations, score each, build
the ranked round3-system-report.{json,md}, and exercise the advisory decision gate. macOS Docker.

This proves the END-TO-END M0→M6 pipeline produces a system report from LIVE Scorecards. The three
"finalists" here are configurations of the SDK-reference fleet — healthy, payment-stopped,
catalog-stopped — used as a harness SELF-TEST (distinct, discriminating system scores + a live
attribution-trustworthiness signal). A real benchmark run feeds DISTINCT MODEL fleets (each model's
own r3/<model>/<svc> images) into the same report path; the report/ranking/gate machinery
(``fleet.report``) is identical.

Writes ``round3-system-report.{json,md}`` to a temp run dir (Mottainai: the JSON is re-renderable $0).

Run:  PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m6
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
from startd8.benchmark_matrix.fleet.report import FinalistScore, build_system_report
from startd8.benchmark_matrix.fleet.score import score_journey
from startd8.benchmark_matrix.fleet.validate_m1 import PROBE, _await_ready, _build_one, _compose, _subset_specs
from startd8.benchmark_matrix.fleet.validate_m2 import (
    DRIVER_IMAGE, DRIVER_SERVICE, FULL_SUBSET, _build_driver_image, _run_driver,
)


def _score(d: dict):
    r = JourneyResult()
    for st in d["steps"]:
        r.steps.append(StepResult(st["name"], st["passed"], st["detail"], st["weight"], st.get("culprit")))
    return score_journey(r)


def _bring_up_fleet(image_namespace: str):
    """Build the driver (if missing) + start the ``image_namespace`` fleet (reference backends are
    built-if-missing; a model namespace's images are assumed pre-built). Returns (workdir, specs,
    contestant) with all contestants ready. Caller MUST teardown the workdir's compose."""
    specs = _subset_specs(FULL_SUBSET)
    contestant = [s for s in specs if not s.is_infra]
    _build_driver_image()
    if image_namespace == "r3":
        for s in contestant:
            _build_one(s.name)
    compose = generate_compose_dict(specs, image_namespace=image_namespace)
    compose["services"][PROBE] = {"image": "alpine:3.20", "command": "sleep infinity",
                                  "networks": [FLEET_NETWORK], "depends_on": [s.name for s in specs]}
    compose["services"][DRIVER_SERVICE] = {"image": DRIVER_IMAGE, "networks": [FLEET_NETWORK],
                                           "depends_on": [s.name for s in contestant], "profiles": ["driver"]}
    workdir = Path(tempfile.mkdtemp(prefix="m6-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))
    _compose(workdir, "up", "-d", timeout=300)
    for s in contestant:
        if not _await_ready(workdir, s.name, s.dial_port):
            raise RuntimeError(f"{s.name} never became ready")
    return workdir, specs, contestant


def score_namespace_fleet(image_namespace: str = "r3"):
    """Bring up the ``image_namespace`` fleet, drive Adapter B once (healthy), return the Scorecard.
    Reusable per-finalist scorer for the round3 CLI. Tears the fleet down on every path."""
    workdir, _, _ = _bring_up_fleet(image_namespace)
    try:
        return _score(_run_driver(workdir))
    finally:
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)


def reference_attribution_trustworthy() -> bool:
    """Bring up the reference fleet, break payment then catalog, and confirm each is attributed to the
    right service with checkout exonerated — the harness-level attribution-trustworthiness signal the
    decision gate consumes."""
    workdir, _, _ = _bring_up_fleet("r3")
    try:
        _compose(workdir, "stop", "paymentservice", check=False, timeout=60)
        nopay = _score(_run_driver(workdir))
        ok_pay = (nopay.model_faulted_services == {"paymentservice"}
                  and "checkoutservice" not in nopay.model_faulted_services)
        _compose(workdir, "start", "paymentservice", check=False, timeout=60)
        _await_ready(workdir, "paymentservice", 50051)
        _compose(workdir, "stop", "productcatalogservice", check=False, timeout=60)
        nocat = _score(_run_driver(workdir))
        ok_cat = (nocat.model_faulted_services == {"productcatalogservice"}
                  and "checkoutservice" not in nocat.model_faulted_services)
        return ok_pay and ok_cat
    finally:
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)


def main() -> int:
    if not docker_available():
        print("docker absent — skip", flush=True)
        return 0

    specs = _subset_specs(FULL_SUBSET)
    contestant = [s for s in specs if not s.is_infra]
    print(f"[m6] fleet = {[s.name for s in specs]}", flush=True)

    subprocess.run(["docker", "rmi", "-f", DRIVER_IMAGE], capture_output=True)
    if not _build_driver_image():
        print("=== M6 FAIL: driver build failed ===", flush=True)
        return 1
    for s in contestant:
        if not _build_one(s.name):
            print(f"=== M6 FAIL: {s.name} build failed ===", flush=True)
            return 1

    compose = generate_compose_dict(specs)
    compose["services"][PROBE] = {"image": "alpine:3.20", "command": "sleep infinity",
                                  "networks": [FLEET_NETWORK], "depends_on": [s.name for s in specs]}
    compose["services"][DRIVER_SERVICE] = {"image": DRIVER_IMAGE, "networks": [FLEET_NETWORK],
                                           "depends_on": [s.name for s in contestant], "profiles": ["driver"]}
    workdir = Path(tempfile.mkdtemp(prefix="m6-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))

    finalists: list[FinalistScore] = []
    attribution_ok = True
    try:
        print("[m6] docker compose up -d ...", flush=True)
        _compose(workdir, "up", "-d", timeout=300)
        for s in contestant:
            if not _await_ready(workdir, s.name, s.dial_port):
                print(f"=== M6 FAIL: {s.name} never ready ===", flush=True)
                return 1

        # finalist 1: reference (healthy) — the system score ceiling.
        ref = _score(_run_driver(workdir))
        finalists.append(FinalistScore("reference", ref))
        print(f"[m6] reference: system_score={ref.weighted_coverage:.3f}", flush=True)

        # finalist 2: reference with payment stopped — attribution must blame payment (not checkout).
        _compose(workdir, "stop", "paymentservice", check=False, timeout=60)
        nopay = _score(_run_driver(workdir))
        finalists.append(FinalistScore("reference-no-payment", nopay))
        attribution_ok &= (nopay.model_faulted_services == {"paymentservice"}
                           and "checkoutservice" not in nopay.model_faulted_services)
        print(f"[m6] reference-no-payment: score={nopay.weighted_coverage:.3f} "
              f"faults={sorted(nopay.model_faulted_services)}", flush=True)
        _compose(workdir, "start", "paymentservice", check=False, timeout=60)
        _await_ready(workdir, "paymentservice", 50051)

        # finalist 3: reference with catalog stopped — attribution must blame catalog (not checkout).
        _compose(workdir, "stop", "productcatalogservice", check=False, timeout=60)
        nocat = _score(_run_driver(workdir))
        finalists.append(FinalistScore("reference-no-catalog", nocat))
        attribution_ok &= (nocat.model_faulted_services == {"productcatalogservice"}
                           and "checkoutservice" not in nocat.model_faulted_services)
        print(f"[m6] reference-no-catalog: score={nocat.weighted_coverage:.3f} "
              f"faults={sorted(nocat.model_faulted_services)}", flush=True)

    finally:
        print("[m6] tearing down ...", flush=True)
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)

    report, md = build_system_report(finalists, attribution_trustworthy=attribution_ok)
    run_dir = Path(tempfile.mkdtemp(prefix="m6-report-"))
    (run_dir / "round3-system-report.json").write_text(json.dumps(report, indent=2))
    (run_dir / "round3-system-report.md").write_text(md)
    print(f"\n{md}", flush=True)
    print(f"[m6] report -> {run_dir}/round3-system-report.{{json,md}}", flush=True)

    gate = report["decision_gate"]
    # the 3 configs have distinct scores (1.0 > no-payment > no-catalog) and attribution held -> GO.
    ok = gate["verdict"] == "GO" and attribution_ok
    print("=== M6 " + ("PASS" if ok else "FAIL") +
          f": decision gate {gate['verdict']} ({gate['note']}) ===", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
