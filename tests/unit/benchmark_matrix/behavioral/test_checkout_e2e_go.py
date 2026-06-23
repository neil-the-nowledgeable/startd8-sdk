"""Gated live oracle self-validation for the checkout stub harness (FR-CO-12, FR-CO-13).

Mirrors ``test_pricing_e2e_node.py``: exercises the REAL path the benchmark uses for a Go
orchestrator — vendor the go stubs (``setup_go_stubs``), ``go build`` the binary, launch it wired to
the in-process :class:`CheckoutStubHarness` via the six ``*_SERVICE_ADDR`` env vars, then score
``PlaceOrder`` over loopback.

  - ``reference_checkout`` (correct 6-way orchestrator)  -> coverage 1.00 (proves the oracle).
  - ``checkout_broken`` (never dials payment)            -> step 5 fails ONLY (proves per-step
    attribution + address injection both work).

This deliberately does NOT go through ``run_behavioral_cell`` — the dedicated execute.py checkout
branch (FR-CO-EXEC) is the NEXT step. This test proves the harness + ground-truth + reference oracle
independently, so the execute branch has a known-good target to wire to.

Gated on ``go`` on PATH; skips cleanly otherwise. Set ``STARTD8_RUN_INTEGRATION=1`` to run.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc
from startd8.benchmark_matrix.behavioral.checkout_stubs import (
    CheckoutStubHarness,
    GroundTruth,
)
from startd8.benchmark_matrix.behavioral.checkout_suite import score_placeorder
from startd8.benchmark_matrix.behavioral.provision import setup_go_stubs

_FIXTURES = Path(__file__).parent / "fixtures"
_REFERENCE = _FIXTURES / "checkout_reference"
_BROKEN = _FIXTURES / "checkout_broken"

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


def _build_checkout(fixture_dir: Path, workdir: Path) -> Path:
    """Replicate the harness's Go provisioning: vendor stubs, `go build -o .bin/server`."""
    svc_dir = workdir / "src" / "checkoutservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "main.go", svc_dir / "main.go")
    shutil.copy(fixture_dir / "go.mod", svc_dir / "go.mod")
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


def _run_and_score(binary: Path, harness: CheckoutStubHarness, gt: GroundTruth):
    addr_map = harness.start()
    port = _free_port()
    env = {**os.environ, "PORT": str(port), **addr_map}
    proc = subprocess.Popen([str(binary)], env=env, cwd=str(binary.parent),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        # wait for readiness (port listening)
        ch = grpc.insecure_channel(f"127.0.0.1:{port}")
        grpc.channel_ready_future(ch).result(timeout=30.0)
        stub = demo_pb2_grpc.CheckoutServiceStub(ch)
        req = demo_pb2.PlaceOrderRequest(
            user_id=gt.user_id, user_currency=gt.user_currency, email=gt.email,
            address=demo_pb2.Address(street_address="1600 Amphitheatre Pkwy", city="MV",
                                     state="CA", country="USA", zip_code=94043),
            credit_card=demo_pb2.CreditCardInfo(credit_card_number="4111111111111111",
                                                credit_card_cvv=123,
                                                credit_card_expiration_year=2030,
                                                credit_card_expiration_month=12))
        order = None
        try:
            resp = stub.PlaceOrder(req, timeout=20.0)
            order = resp.order if resp.HasField("order") else demo_pb2.OrderResult()
        except grpc.RpcError:
            order = None
        ch.close()
        suite = score_placeorder(order, ground_truth=gt, stub_calls=harness.call_counts)
        return suite
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        harness.stop()


def test_reference_checkout_scores_full_coverage(tmp_path):
    gt = GroundTruth()
    binary = _build_checkout(_REFERENCE, tmp_path)
    suite = _run_and_score(binary, CheckoutStubHarness(gt), gt)
    failing = [r.__dict__ for r in suite.results if not r.passed]
    assert suite.coverage == 1.0, f"coverage={suite.coverage}; failing={failing}"


def test_broken_checkout_fails_only_payment_step(tmp_path):
    gt = GroundTruth()
    binary = _build_checkout(_BROKEN, tmp_path)
    harness = CheckoutStubHarness(gt)
    suite = _run_and_score(binary, harness, gt)
    failed = {r.name for r in suite.results if not r.passed}
    # payment never dialed -> step 5 fails; all others pass (per-step attribution + injection work).
    assert "payment_charged" in failed, [r.__dict__ for r in suite.results]
    assert failed == {"payment_charged"}, [r.__dict__ for r in suite.results]
    assert harness.call_counts["PAYMENT_SERVICE_ADDR"] == 0
    assert time.time()  # touch import


# --------------------------------------------------------------------------- FR-CO-EXEC end-to-end
# The above prove the harness/oracle directly. These prove the dedicated execute.py checkout branch
# (run_behavioral_cell → _run_checkout_cell) drives the SAME real Go binary through the real sandbox:
# the branch provisions + builds, binds the six stubs, injects *_SERVICE_ADDR, launches the sandboxed
# SUT, and scores per-step coverage from the live call-counters — the full integration path.
_SEED = {
    "service_metadata": {"language": "go"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/checkoutservice && exec ./.bin/server"],
        "port_env": "PORT",
        "readiness": "tcp",
        "dependency_addr_env": [
            "PRODUCT_CATALOG_SERVICE_ADDR", "CART_SERVICE_ADDR", "CURRENCY_SERVICE_ADDR",
            "SHIPPING_SERVICE_ADDR", "PAYMENT_SERVICE_ADDR", "EMAIL_SERVICE_ADDR",
        ],
    },
}
_TARGETS = ["src/checkoutservice/main.go"]


def _stage_source(fixture_dir: Path, workdir: Path) -> None:
    """Drop the fixture's Go source where the branch's own provisioning expects it (it builds)."""
    svc_dir = workdir / "src" / "checkoutservice"
    svc_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture_dir / "main.go", svc_dir / "main.go")
    shutil.copy(fixture_dir / "go.mod", svc_dir / "go.mod")


def test_reference_checkout_full_coverage_via_run_behavioral_cell(tmp_path):
    from startd8.benchmark_matrix.behavioral import execute

    _stage_source(_REFERENCE, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)
    assert res.has_suite and not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 1.0, res.provenance.get("suite")
    counts = res.provenance["checkout_call_counts"]
    assert all(counts[n] > 0 for n in _SEED["startup"]["dependency_addr_env"]), counts


def test_broken_checkout_real_miss_via_run_behavioral_cell(tmp_path):
    from startd8.benchmark_matrix.behavioral import execute

    _stage_source(_BROKEN, tmp_path)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)
    # Launched + reached but never dials payment → real MISS (partial), NOT degrade (FR-CO-17).
    assert not res.degraded and not res.model_fault, res.provenance
    assert res.functional == 5 / 6, res.provenance.get("suite")
    assert res.provenance["checkout_call_counts"]["PAYMENT_SERVICE_ADDR"] == 0
