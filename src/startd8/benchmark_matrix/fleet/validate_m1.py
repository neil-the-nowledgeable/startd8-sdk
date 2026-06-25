"""M1 live validation: build a fleet's images -> generate compose -> `docker compose up` -> assert
every declared *_SERVICE_ADDR resolves over service-DNS + egress to 1.1.1.1:443 is DENIED from a
pure-backend vantage -> clean teardown. macOS Docker. The N-service generalization of the
2-service compose-prototype's drive_fleet.py.

Effectiveness practices (Lessons_Learned sdk/lessons/01-benchmarking.md):
  * build-if-missing (#10 Mottainai): reuse an already-built r3/<svc>:<lang> image; only build a
    service whose image is absent. Iterate the harness without paying N rebuilds.
  * --subset quick mode (#1): default to the dependency-closed (productcatalog, recommendation) pair
    for harness iteration; pass --subset for a larger fleet.

The service-DNS / egress checks run from a tiny alpine PROBE SIDECAR attached to the `fleet` network,
NOT by exec-ing into the service containers: the M0 service images are minimal (the Go image is
distroless — no /bin/sh, no nc), so an in-container shell probe is impossible. A probe on the
`fleet`-only network is the correct vantage anyway: if it resolves+reaches peer:port, so does any
service on the same network/DNS, and being internal-only it proves the network-layer egress-deny.

SCOPE NOTE: only services with a buildable reference fixture can join the fleet — today
{productcatalog, checkout, cart, email, payment, recommendation}. shippingservice + currencyservice
reference servers do NOT exist yet, so the full 8-service fleet incl. checkout's 6-dep fan-out is
blocked on authoring those two (see NEXT_STEPS / JOURNEY_DESIGN §3).

Run:  PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m1 [--subset a,b,c]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral.recommendation_stubs import recommendation_ground_truth
from startd8.benchmark_matrix.fleet import services as S
from startd8.benchmark_matrix.fleet.compose import FLEET_NETWORK, generate_compose_dict
from startd8.benchmark_matrix.fleet.containerize import build_service_image, docker_available

WT = Path(__file__).resolve().parents[4]
FIX = WT / "tests/unit/benchmark_matrix/behavioral/fixtures"
COMPOSE = ["docker", "compose"]
PROBE = "m1probe"


# --- per-service build recipes (which fixture, files, provisioning) -------------------------------
# Only services with a buildable reference fixture appear here.

def _provision_catalog(wd: Path) -> None:
    # productcatalog serves the recommendation oracle's catalog (so a rec->catalog dial returns the
    # ids the recommendation oracle expects) — the compose-prototype's choice.
    gt = recommendation_ground_truth()
    products = [{
        "id": p.id, "name": p.name, "description": p.name,
        "picture": f"/static/img/products/{p.id}.jpg",
        "priceUsd": {"currencyCode": "USD", "units": p.price_units, "nanos": p.price_nanos},
        "categories": ["fleet"],
    } for p in gt.catalog.values()]
    (wd / "products.json").write_text(json.dumps({"products": products}, indent=2))


_RECIPES = {
    "productcatalogservice": dict(language="go", fixture="catalog_reference",
                                  files=["main.go", "go.mod"], provision=_provision_catalog),
    "recommendationservice": dict(language="python", fixture="recommendation_reference",
                                  files=["server.py"], provision=None),
    "emailservice": dict(language="python", fixture="email_reference", files=["server.py"],
                         provision=lambda wd: execute.provision_email_template(wd, ["server.py"]),
                         extra_pip=["jinja2"]),
    "paymentservice": dict(language="node", fixture="payment_reference",
                           files=["server.js", "package.json"], provision=None),
    "cartservice": dict(language="csharp", fixture="cart_reference",
                        files=["Program.cs", "cartservice.csproj"], provision=None),
    "shippingservice": dict(language="go", fixture="shipping_reference",
                            files=["main.go", "go.mod"], provision=None),
    "currencyservice": dict(language="node", fixture="currency_reference",
                            files=["server.js", "package.json"], provision=None),
    # checkoutservice: the journey's deepest node — dials all 6 deps at runtime via *_SERVICE_ADDR.
    "checkoutservice": dict(language="go", fixture="checkout_reference",
                            files=["main.go", "go.mod"], provision=None),
}

DEFAULT_SUBSET = ["productcatalogservice", "recommendationservice"]


def _image_exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def _build_one(name: str) -> bool:
    recipe = _RECIPES[name]
    lang = recipe["language"]
    tag = f"r3/{name}:{lang}"
    if _image_exists(tag):
        print(f"[build] {name}: {tag} present — skip (build-if-missing)", flush=True)
        return True
    wd = Path(tempfile.mkdtemp(prefix=f"m1-{name}-"))
    ref = FIX / recipe["fixture"]
    for f in recipe["files"]:
        shutil.copy(ref / f, wd / f)
    if recipe["provision"]:
        recipe["provision"](wd)
    print(f"[build] {name}: build_service_image({lang}) ...", flush=True)
    res = build_service_image(name, wd, lang, target_files=[recipe["files"][0]], tag=tag,
                              extra_pip=recipe.get("extra_pip"))
    if not res.ok:
        print(f"[build] {name}: BUILD FAILED\n{(res.log or '')[-1500:]}", flush=True)
    return res.ok


# --- compose lifecycle ----------------------------------------------------------------------------

def _compose(workdir: Path, *args, check=True, timeout=None):
    r = subprocess.run([*COMPOSE, *args], cwd=str(workdir), text=True, capture_output=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"compose {' '.join(args)} failed (rc={r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r


def _subset_specs(names: list[str]) -> tuple[S.ServiceSpec, ...]:
    """The requested services + their dependency-closure, so the compose is complete. Raises if a
    requested service or transitive dep has no build recipe (and isn't infra)."""
    want: set[str] = set()

    def add(n: str) -> None:
        if n in want:
            return
        want.add(n)
        for dep in S.get_service(n).deps:
            add(dep)

    for n in names:
        add(n)
    specs = tuple(s for s in S.default_fleet() if s.name in want)
    for s in specs:
        if not s.is_infra and s.name not in _RECIPES:
            raise SystemExit(f"service {s.name!r} has no build recipe (missing reference fixture) — "
                             f"buildable: {sorted(_RECIPES)}")
    return specs


def _probe(workdir: Path, target: str, port: int, *, label: str, timeout=4) -> bool:
    """nc from the alpine probe sidecar to target:port — True on connect. busybox nc -z -w."""
    sh = f"nc -w {timeout} -z {target} {port} && echo {label}_OK || echo {label}_FAIL"
    r = _compose(workdir, "exec", "-T", PROBE, "sh", "-c", sh, check=False, timeout=timeout + 15)
    out = (r.stdout or "") + (r.stderr or "")
    return f"{label}_OK" in out and f"{label}_FAIL" not in out


def _await_ready(workdir: Path, name: str, port: int, timeout=60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _probe(workdir, name, port, label="RDY"):
            return True
        time.sleep(2.0)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", default=",".join(DEFAULT_SUBSET),
                    help="comma-separated service names (deps auto-included)")
    args = ap.parse_args()

    if not docker_available():
        print("docker absent — skip", flush=True)
        return 0

    names = [n.strip() for n in args.subset.split(",") if n.strip()]
    specs = _subset_specs(names)
    contestant = [s for s in specs if not s.is_infra]
    print(f"[m1] fleet = {[s.name for s in specs]}", flush=True)

    # 1) build images (build-if-missing).
    for s in contestant:
        if not _build_one(s.name):
            print(f"=== M1 FAIL: {s.name} image build failed ===", flush=True)
            return 1

    # 2) generate compose for exactly this subset + inject the alpine probe sidecar on `fleet`.
    compose = generate_compose_dict(specs)
    compose["services"][PROBE] = {
        "image": "alpine:3.20",
        "command": "sleep infinity",
        "networks": [FLEET_NETWORK],  # fleet-only => same vantage as a pure backend (egress-denied)
        "depends_on": [s.name for s in specs],
    }
    workdir = Path(tempfile.mkdtemp(prefix="m1-fleet-"))
    (workdir / "docker-compose.yml").write_text(yaml.safe_dump(compose, sort_keys=False))
    print(f"[m1] compose ({len(specs)} svc + probe) -> {workdir}/docker-compose.yml", flush=True)

    failures: list[str] = []
    try:
        print("[m1] docker compose up -d ...", flush=True)
        _compose(workdir, "up", "-d", timeout=300)

        # 3) readiness: every contestant serving on its dial port (probed over service-DNS).
        for s in contestant:
            if _await_ready(workdir, s.name, s.dial_port):
                print(f"[m1] ready: {s.name}:{s.dial_port}", flush=True)
            else:
                logs = _compose(workdir, "logs", "--no-color", "--tail", "40", s.name, check=False)
                failures.append(f"{s.name} never became ready on :{s.dial_port}")
                print(f"[m1] NOT ready: {s.name}\n{(logs.stdout or '')[-1200:]}", flush=True)

        # 4) every declared *_SERVICE_ADDR resolves over service-DNS (probe each dep edge's target).
        edges = {(dep, S.get_service(dep).dial_port)
                 for s in contestant for dep in s.deps}
        for peer, port in sorted(edges):
            if _probe(workdir, peer, port, label="DNS"):
                print(f"[m1] service-DNS OK: {peer}:{port}", flush=True)
            else:
                failures.append(f"service-DNS failed to resolve/dial {peer}:{port}")

        # 5) egress denied from the fleet-only probe (a pure-backend vantage).
        if _probe(workdir, "1.1.1.1", 443, label="EGRESS", timeout=5):
            failures.append("egress to 1.1.1.1:443 was NOT denied (internal net leaked)")
        else:
            print("[m1] egress to 1.1.1.1:443 DENIED (internal:true contained it)", flush=True)

    finally:
        print("[m1] tearing down ...", flush=True)
        _compose(workdir, "down", "-v", "--remove-orphans", check=False, timeout=120)

    result = {"fleet": [s.name for s in specs], "failures": failures, "ok": not failures}
    print("[m1] RESULT: " + json.dumps(result), flush=True)
    if failures:
        for f in failures:
            print("   x " + f, flush=True)
        print("=== M1 FAIL ===", flush=True)
        return 1
    print("=== M1 PASS: fleet booted, service-DNS resolved, egress denied, clean teardown ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
