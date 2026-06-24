"""Gated live oracle self-validation for the productcatalogservice suite (Track-2 expansion).

Mirrors ``test_checkout_e2e_go.py`` but for a stateful-LOCAL LEAF: build the reference Go catalog
server, provision the harness-owned ``products.json``, launch it, and score ``run_catalog_suite`` over
loopback.

  - ``catalog_reference`` (correct, NOT_FOUND on absent id)  → coverage 1.00 (proves the oracle).
  - ``catalog_broken``    (zero Product on absent id)        → the get_product_absent_not_found case
    fails ONLY (proves per-RPC attribution).

The first block drives the binary directly; the second proves the dedicated ``run_behavioral_cell``
leaf path (registration + products.json provisioning + Go serve) end-to-end through the real sandbox.

Gated on ``go`` on PATH; skips cleanly otherwise. Set ``STARTD8_RUN_INTEGRATION=1`` to run.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral.catalog_suite import (
    PRODUCTS_FILENAME,
    products_json,
    run_catalog_suite,
)
from startd8.benchmark_matrix.behavioral.provision import setup_go_stubs

_FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCE = _FIXTURES / "catalog_reference"
_BROKEN = _FIXTURES / "catalog_broken"

pytestmark = [
    pytest.mark.skipif(os.environ.get("STARTD8_RUN_INTEGRATION") != "1",
                       reason="gated: set STARTD8_RUN_INTEGRATION=1"),
    pytest.mark.skipif(shutil.which("go") is None, reason="go not on PATH"),
]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _build_catalog(fixture_dir: Path, workdir: Path) -> Path:
    """Replicate the harness Go provisioning + state provisioning: vendor stubs, build, write
    products.json into the service dir (the server's cwd)."""
    svc_dir = workdir / "src" / "productcatalogservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "main.go", svc_dir / "main.go")
    shutil.copy(fixture_dir / "go.mod", svc_dir / "go.mod")
    (svc_dir / PRODUCTS_FILENAME).write_text(products_json())
    err = setup_go_stubs(workdir, svc_dir)
    assert err is None, f"go-stub provisioning failed: {err}"
    env = {**os.environ, "GOFLAGS": "-mod=mod"}
    proc = subprocess.run(
        ["sh", "-c", "go mod tidy && go build -o .bin/server ."],
        cwd=str(svc_dir), env=env, capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, f"go build failed:\n{proc.stdout}\n{proc.stderr}"
    binary = svc_dir / ".bin" / "server"
    assert binary.is_file()
    return binary


def _run_and_score(binary: Path):
    port = _free_port()
    env = {**os.environ, "PORT": str(port)}
    proc = subprocess.Popen([str(binary)], env=env, cwd=str(binary.parent.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ch = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(ch).result(timeout=30.0)
        ch.close()
        return run_catalog_suite(port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_reference_catalog_scores_full_coverage(tmp_path):
    binary = _build_catalog(_REFERENCE, tmp_path)
    suite = _run_and_score(binary)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"


def test_broken_catalog_fails_only_not_found_case(tmp_path):
    binary = _build_catalog(_BROKEN, tmp_path)
    suite = _run_and_score(binary)
    failed = {r.name for r in suite.results if not r.passed}
    assert failed == {"get_product_absent_not_found"}, [r.__dict__ for r in suite.results]
    assert suite.coverage == 4 / 5


# --------------------------------------------------------------------------- via run_behavioral_cell
# Prove the dedicated leaf path: registration + products.json provisioning + Go serve drive the SAME
# real binary through the real sandbox, scored from the live RPC responses.
_SEED = {
    "service_metadata": {"language": "go"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/productcatalogservice && exec ./.bin/server"],
        "port_env": "PORT",
        "readiness": "tcp",
    },
}
_TARGETS = ["src/productcatalogservice/server.go"]


def _stage_source(fixture_dir: Path, workdir: Path) -> None:
    """Drop the fixture's Go source where the branch's own provisioning expects it (it builds).
    The harness itself writes products.json (provision_catalog_state) — we do NOT pre-stage it."""
    svc_dir = workdir / "src" / "productcatalogservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "main.go", svc_dir / "server.go")
    shutil.copy(fixture_dir / "go.mod", svc_dir / "go.mod")


def test_reference_catalog_full_coverage_via_run_behavioral_cell(tmp_path):
    _stage_source(_REFERENCE, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "productcatalogservice", _TARGETS)
    assert res.has_suite and not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 1.0, res.provenance.get("suite")
    # The harness provisioned the ground-truth catalog (oracle-first).
    assert res.provenance.get("catalog_state_files")


def test_broken_catalog_real_miss_via_run_behavioral_cell(tmp_path):
    _stage_source(_BROKEN, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "productcatalogservice", _TARGETS)
    assert not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 4 / 5, res.provenance.get("suite")
