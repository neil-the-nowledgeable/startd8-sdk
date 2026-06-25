"""M0 live validation: build_service_image -> boot_and_probe -> one RPC, per language. macOS Docker."""
import sys
import shutil
import tempfile
import time
import subprocess
from pathlib import Path
from startd8.benchmark_matrix.fleet.containerize import build_service_image, boot_and_probe, docker_available
from startd8.benchmark_matrix.behavioral import catalog_suite, email_suite, execute

WT = Path(__file__).resolve().parents[4]  # repo/worktree root
FIX = WT / "tests/unit/benchmark_matrix/behavioral/fixtures"

def _run(service, language, fixture, files, provision, probe, port, extra_pip=None):
    if not docker_available():
        print(f"[{language}] docker absent — skip", flush=True)
        return None
    wd = Path(tempfile.mkdtemp(prefix=f"m0-{language}-"))
    ref = FIX / fixture
    for f in files:
        (wd / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ref / f, wd / f)
    if provision:
        provision(wd)
    print(f"[{language}] build_service_image({service})...", flush=True)
    res = build_service_image(service, wd, language, target_files=[files[0]], tag=f"r3/{service}:{language}",
                              extra_pip=extra_pip)
    print(f"[{language}] build ok={res.ok} tag={res.tag}", flush=True)
    if not res.ok:
        print(f"[{language}] BUILD LOG:\n{(res.log or '')[-2000:]}", flush=True)
        return False
    boot = boot_and_probe(res.tag, service, language, host_port=port, run=True)
    print(f"[{language}] boot ok={boot.ok} {(boot.log or '')[-200:]}", flush=True)
    name = f"r3-{service}-{language}"
    try:
        if not boot.ok:
            return False
        time.sleep(5)
        cov = probe(port)
        print(f"[{language}] PROBE coverage={cov}", flush=True)
        return bool(cov and cov > 0)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

def go():
    return _run("productcatalogservice", "go", "catalog_reference", ["main.go", "go.mod"],
                lambda wd: (wd / "products.json").write_text(catalog_suite.products_json()),
                lambda p: catalog_suite.run_catalog_suite(p).coverage, 18081)

def python():
    # emailservice — simplest Python leaf (stateless SendOrderConfirmation over gRPC). The harness
    # owns the jinja2 confirmation.html the OB server renders from, provisioned into the cell workdir
    # (svc dir == workdir root here, since server.py is staged flat) — the analogue of catalog's
    # products.json.
    return _run("emailservice", "python", "email_reference", ["server.py"],
                lambda wd: execute.provision_email_template(wd, ["server.py"]),
                lambda p: email_suite.run_email_suite(p).coverage, 18082,
                extra_pip=["jinja2"])

if __name__ == "__main__":
    lang = sys.argv[1] if len(sys.argv) > 1 else "go"
    fn = {"go": go, "python": python}[lang]
    ok = fn()
    print(f"=== {lang} M0: {'PASS' if ok else ('SKIP' if ok is None else 'FAIL')} ===", flush=True)
