"""Pure-Python end-to-end tests for the FR-CO-EXEC checkout orchestration branch.

These exercise ``execute._run_checkout_cell`` (via ``run_behavioral_cell("checkoutservice", …)``)
WITHOUT Go: ``run_service_sandboxed`` is monkeypatched with a faithful in-process **fake Go SUT** — a
tiny Python CheckoutService orchestrator that reads the six ``*_SERVICE_ADDR`` env vars the branch
injected and dials the real :class:`CheckoutStubHarness` loopback stubs over gRPC, exactly as the Go
binary would. So the branch's real wiring (stub bring-up → addr_map → extra_env → SUT → call_counts
snapshot → per-step scorer → teardown) is proven, including:

  - full coverage when the SUT dials all six injected stub addresses;
  - DEGRADE (not 0) on a readiness failure (FR-CO-16);
  - a real MISS (partial coverage, NOT degrade) when one injected address is corrupted so a stub is
    never dialed (FR-CO-17);
  - stubs ALWAYS torn down — on success AND when the launch path raises (FR-CO-3).

The Go-gated live oracle (real ``./.bin/server``) stays in ``test_checkout_e2e_go.py``.
"""
from __future__ import annotations

import socket
import threading
from concurrent import futures
from typing import Dict, Optional

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import demo_pb2, demo_pb2_grpc, execute
from startd8.benchmark_matrix.behavioral.checkout_stubs import (
    DEP_ENV_NAMES,
    ENV_CART,
    ENV_CURRENCY,
    ENV_EMAIL,
    ENV_PAYMENT,
    ENV_PRODUCT_CATALOG,
    ENV_SHIPPING,
)
from startd8.benchmark_matrix.sandbox import ServiceResult

# The re-authored seed already carries the startup block + the six declared dep-env names (FR-CO-9).
_SEED = {
    "service_metadata": {"language": "go"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/checkoutservice && exec ./.bin/server"],
        "port_env": "PORT",
        "readiness": "tcp",
        "dependency_addr_env": list(DEP_ENV_NAMES),
    },
}
_TARGETS = ["src/checkoutservice/main.go"]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


class _FakeCheckout(demo_pb2_grpc.CheckoutServiceServicer):
    """A correct in-process CheckoutService that dials the six dependency stubs from the injected env.

    ``corrupt`` lets a test redirect ONE dependency address to a dead port (simulating a checkout that
    ignores the injected addr / dials the wrong place) so the matching stub is never called → real miss.
    """

    def __init__(self, env: Dict[str, str], corrupt: Optional[str] = None):
        self._env = env
        self._corrupt = corrupt

    def _addr(self, name: str) -> str:
        if name == self._corrupt:
            return f"127.0.0.1:{_free_port()}"  # nothing listening here → dial fails / never reaches stub
        return self._env[name]

    def PlaceOrder(self, request, context):
        catalog = demo_pb2_grpc.ProductCatalogServiceStub(
            grpc.insecure_channel(self._addr(ENV_PRODUCT_CATALOG)))
        cart = demo_pb2_grpc.CartServiceStub(grpc.insecure_channel(self._addr(ENV_CART)))
        currency = demo_pb2_grpc.CurrencyServiceStub(grpc.insecure_channel(self._addr(ENV_CURRENCY)))
        shipping = demo_pb2_grpc.ShippingServiceStub(grpc.insecure_channel(self._addr(ENV_SHIPPING)))
        payment = demo_pb2_grpc.PaymentServiceStub(grpc.insecure_channel(self._addr(ENV_PAYMENT)))
        email = demo_pb2_grpc.EmailServiceStub(grpc.insecure_channel(self._addr(ENV_EMAIL)))

        c = cart.GetCart(demo_pb2.GetCartRequest(user_id=request.user_id), timeout=5.0)
        items = []
        for ci in c.items:
            prod = catalog.GetProduct(demo_pb2.GetProductRequest(id=ci.product_id), timeout=5.0)
            usd = demo_pb2.Money(currency_code="USD",
                                 units=prod.price_usd.units * ci.quantity,
                                 nanos=prod.price_usd.nanos * ci.quantity)
            conv_req = demo_pb2.CurrencyConversionRequest(to_code=request.user_currency)
            getattr(conv_req, "from").CopyFrom(usd)
            cost = currency.Convert(conv_req, timeout=5.0)
            items.append(demo_pb2.OrderItem(
                item=demo_pb2.CartItem(product_id=ci.product_id, quantity=ci.quantity), cost=cost))

        quote = shipping.GetQuote(demo_pb2.GetQuoteRequest(address=request.address), timeout=5.0)
        ship_conv = demo_pb2.CurrencyConversionRequest(to_code=request.user_currency)
        getattr(ship_conv, "from").CopyFrom(quote.cost_usd)
        ship_cost = currency.Convert(ship_conv, timeout=5.0)
        tracking = shipping.ShipOrder(
            demo_pb2.ShipOrderRequest(address=request.address), timeout=5.0).tracking_id

        total_nanos = sum(it.cost.units * 1_000_000_000 + it.cost.nanos for it in items)
        total_nanos += ship_cost.units * 1_000_000_000 + ship_cost.nanos
        amount = demo_pb2.Money(currency_code=request.user_currency,
                                units=total_nanos // 1_000_000_000,
                                nanos=total_nanos % 1_000_000_000)
        # A checkout that dials a WRONG (corrupted) address gets UNAVAILABLE; a resilient orchestrator
        # swallows it and still returns the order (mirrors the `checkout_broken` fixture: the step is a
        # real miss via the never-incremented stub counter, not a whole-RPC crash).
        try:
            payment.Charge(demo_pb2.ChargeRequest(amount=amount, credit_card=request.credit_card),
                           timeout=5.0)
        except grpc.RpcError:
            pass

        order = demo_pb2.OrderResult(
            order_id="fake-order-0001", shipping_tracking_id=tracking,
            shipping_cost=ship_cost, items=items)
        try:
            email.SendOrderConfirmation(
                demo_pb2.SendOrderConfirmationRequest(email=request.email, order=order), timeout=5.0)
        except grpc.RpcError:
            pass
        return demo_pb2.PlaceOrderResponse(order=order)


def _fake_sandbox(*, corrupt: Optional[str] = None, never_ready: bool = False):
    """Build a monkeypatch replacement for run_service_sandboxed that stands up _FakeCheckout."""

    def _impl(server_cmd, workspace, port, client, cfg=None, *, extra_env=None,
              readiness_timeout_s=15.0, readiness_mode="tcp", health_path="/health"):
        if never_ready:
            return ServiceResult(ready=False, server_stderr="server never bound",
                                 isolation_level="seatbelt-loopback", network_isolated=True)
        # Assert the branch injected all six *_SERVICE_ADDR before launch (FR-CO-10).
        for name in DEP_ENV_NAMES:
            assert name in (extra_env or {}), f"{name} not injected into extra_env"
        srv = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        demo_pb2_grpc.add_CheckoutServiceServicer_to_server(
            _FakeCheckout(extra_env, corrupt=corrupt), srv)
        srv.add_insecure_port(f"127.0.0.1:{port}")
        srv.start()
        try:
            outcome = client(port)  # the suite snapshots harness.call_counts AFTER PlaceOrder here
        finally:
            srv.stop(0).wait(timeout=2.0)
        return ServiceResult(ready=True, client_outcome=outcome,
                             isolation_level="seatbelt-loopback", network_isolated=True)

    return _impl


@pytest.fixture(autouse=True)
def _no_provision(monkeypatch):
    # The fake SUT needs no Go toolchain / proto vendoring — neutralize provisioning so the branch's
    # wiring is what's under test, not the (separately-tested) Go provision path.
    import startd8.benchmark_matrix.behavioral.provision as provision

    class _OkProv:
        ok = True
        language = "go"
        degraded_reason = ""

    monkeypatch.setattr(provision, "provision_workdir", lambda *a, **k: _OkProv())


def test_checkout_full_coverage_when_all_deps_dialed(tmp_path, monkeypatch):
    monkeypatch.setattr(execute, "run_service_sandboxed", _fake_sandbox())
    res = execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)

    assert res.has_suite is True and res.degraded is False and res.model_fault is False
    assert res.functional == 1.0, res.provenance.get("suite")
    # FR-CO-19 provenance: all six stubs were dialed; injected addrs + per-step results recorded.
    counts = res.provenance["checkout_call_counts"]
    assert all(counts[n] > 0 for n in DEP_ENV_NAMES), counts
    assert set(res.provenance["checkout_injected_addrs"]) == set(DEP_ENV_NAMES)
    assert res.provenance["suite_kind"] == "checkout-orchestrator"
    assert res.provenance["isolation_level"] == "seatbelt-loopback"


def test_checkout_degrades_on_readiness_failure(tmp_path, monkeypatch):
    # FR-CO-16: the SUT never becomes ready (a harness/launch reason) → DEGRADE, never a 0.
    monkeypatch.setattr(execute, "run_service_sandboxed", _fake_sandbox(never_ready=True))
    res = execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)

    assert res.degraded is True and res.model_fault is False
    assert res.functional is None


def test_wrong_dep_address_is_real_miss_not_degrade(tmp_path, monkeypatch):
    # FR-CO-17: the checkout comes up + is reached but dials a WRONG payment address (ignores the
    # injected one) → the payment stub is never called → step 5 a REAL miss (partial coverage), the
    # cell is NOT degraded (stubs were present + reachable; checkout chose not to use the address).
    monkeypatch.setattr(execute, "run_service_sandboxed",
                        _fake_sandbox(corrupt=ENV_PAYMENT))
    res = execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)

    assert res.degraded is False and res.model_fault is False
    assert res.functional is not None
    assert 0.0 < res.functional < 1.0, res.functional      # partial, not all-or-nothing
    assert res.functional == pytest.approx(5 / 6)          # only payment_charged fails
    assert res.provenance["checkout_call_counts"][ENV_PAYMENT] == 0
    suite = res.provenance["suite"]
    failed = {r["name"] for r in suite["results"] if not r["passed"]}
    assert failed == {"payment_charged"}, suite["results"]


def test_stubs_torn_down_on_success(tmp_path, monkeypatch):
    # FR-CO-3: after a successful cell, no stub loopback port is left listening.
    captured = {}
    real_start = execute.CheckoutStubHarness.start

    def _spy_start(self):
        addr_map = real_start(self)
        captured["addrs"] = dict(addr_map)
        return addr_map

    monkeypatch.setattr(execute.CheckoutStubHarness, "start", _spy_start)
    monkeypatch.setattr(execute, "run_service_sandboxed", _fake_sandbox())
    execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)

    for addr in captured["addrs"].values():
        host, p = addr.rsplit(":", 1)
        with pytest.raises(OSError):  # connection refused → the stub server is gone
            socket.create_connection((host, int(p)), timeout=0.5).close()


def test_stubs_torn_down_when_launch_raises(tmp_path, monkeypatch):
    # FR-CO-3 (the critical path): an exception in the launch path must STILL tear the stubs down.
    captured = {}
    stop_calls = {"n": 0}
    real_start = execute.CheckoutStubHarness.start
    real_stop = execute.CheckoutStubHarness.stop

    def _spy_start(self):
        addr_map = real_start(self)
        captured["addrs"] = dict(addr_map)
        return addr_map

    def _spy_stop(self):
        stop_calls["n"] += 1
        return real_stop(self)

    def _boom(*a, **k):
        raise RuntimeError("simulated SUT-launch explosion")

    monkeypatch.setattr(execute.CheckoutStubHarness, "start", _spy_start)
    monkeypatch.setattr(execute.CheckoutStubHarness, "stop", _spy_stop)
    monkeypatch.setattr(execute, "run_service_sandboxed", _boom)

    with pytest.raises(RuntimeError, match="simulated SUT-launch explosion"):
        execute.run_behavioral_cell(_SEED, tmp_path, "checkoutservice", _TARGETS)

    assert stop_calls["n"] >= 1  # finally: harness.stop() ran despite the exception
    for addr in captured["addrs"].values():
        host, p = addr.rsplit(":", 1)
        with pytest.raises(OSError):
            socket.create_connection((host, int(p)), timeout=0.5).close()


def test_no_startup_block_degrades(tmp_path, monkeypatch):
    # FR-CO-9: a seed missing the startup block degrades (doesn't crash) — no stubs leaked.
    monkeypatch.setattr(execute, "run_service_sandboxed", _fake_sandbox())
    seed = {"service_metadata": {"language": "go"}}  # no startup block
    res = execute.run_behavioral_cell(seed, tmp_path, "checkoutservice", _TARGETS)
    assert res.degraded is True and res.functional is None
    assert "startup block" in res.provenance["reason"]


def test_threading_import_touch():
    assert threading  # keep the import meaningful across refactors
