"""Tests for the R3-M4 frontend gate + HTTP journey (fleet.frontend_gate) — real HTTP loopback, NO docker.

Drives the gate against in-process MOCK frontends: a CORRECT one (PASS → use generated) and a
SUBTLY-BROKEN one that renders a checkout confirmation WITHOUT a real order id (FAIL at the decisive
JOURNEY stage → substitute canonical). This is the behavioral gate the contract demands (route-presence
saturates; only the stateful checkout-with-an-order-id discriminates).
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from startd8.benchmark_matrix.fleet import frontend_contract as FC
from startd8.benchmark_matrix.fleet import frontend_gate as G
from startd8.benchmark_matrix.fleet import journey as J

pytestmark = pytest.mark.unit

_SKU = J.CANONICAL_SKU


def _make_handler(*, broken_checkout: bool = False, missing_route: str | None = None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, code, body="ok", ctype="text/html"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _redirect(self, to):
            self.send_response(302)
            self.send_header("Location", to)
            self.end_headers()

        def _form(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            return {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}

        def do_GET(self):
            p = self.path
            if p == missing_route:
                return self._send(404, "missing")
            if p == "/_healthz":
                return self._send(200, "ok")
            if p == "/":
                return self._send(200, "<ul><li class=product>OLJCESPC7Z — 10.00 USD</li></ul>")
            if p == "/product/":
                return self._send(400, "missing id")
            if p.startswith("/product/"):
                return self._send(200, "<h1 id=product-name>Widget</h1><p id=price>9.99 EUR</p>")
            if p == "/cart":
                return self._send(200, f"<ul id=cart-items><li>{_SKU} x2 — 19.98 EUR</li></ul>"
                                       "<p id=shipping>Shipping: 9.99 USD</p><p id=total>Total: 29.97 EUR</p>")
            return self._send(404, "nope")

        def do_POST(self):
            p, form = self.path, self._form()
            if p == missing_route:
                return self._send(404, "missing")
            if p == "/setCurrency":
                return self._redirect(self.headers.get("Referer") or "/")
            if p == "/cart":
                if not form.get("product_id"):
                    return self._send(422, "bad add")
                return self._redirect("/cart")
            if p == "/cart/checkout":
                need = ("email", "credit_card_number", "zip_code", "credit_card_expiration_year")
                if any(k not in form for k in need):
                    return self._send(422, "bad checkout")
                if broken_checkout:  # confirmation WITHOUT a real order id (the subtle defect)
                    return self._send(200, "<h1>Order Confirmed</h1><p>Thank you for shopping!</p>")
                return self._send(200, "<h1>Order Confirmed</h1><p id=order-id>Order ID: ORD-ABC-123</p>")
            return self._send(404, "nope")

    return H


class _MockFrontend:
    def __init__(self, **kw):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(**kw))
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return f"http://127.0.0.1:{self.port}"

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()


def test_correct_frontend_passes_and_uses_generated():
    with _MockFrontend() as base:
        res = G.run_gate(base, now_year=2026)
    assert res.verdict.passed and res.verdict.mounted == "generated"
    assert all(res.stage_results[s] for s in FC.BLOCKING_STAGES)
    assert res.order_id == "ORD-ABC-123"
    assert res.orchestration_fidelity == 1.0


def test_subtly_broken_checkout_fails_journey_and_substitutes_canonical():
    """The decisive case: routes all respond correctly, but checkout renders NO real order id → the
    JOURNEY stage fails → substitute the canonical frontend (the exit-criterion defense)."""
    with _MockFrontend(broken_checkout=True) as base:
        res = G.run_gate(base, now_year=2026)
    assert not res.verdict.passed
    assert res.verdict.failing_stage == "journey"   # passed boot+routes, failed the stateful journey
    assert res.verdict.mounted == "canonical-substituted"
    assert res.stage_results[FC.GateStage.ROUTES] is True
    assert res.stage_results[FC.GateStage.JOURNEY] is False
    assert res.order_id == ""


def test_missing_route_fails_at_routes_stage():
    with _MockFrontend(missing_route="/cart") as base:  # GET/POST /cart 404
        res = G.run_gate(base)
    assert res.verdict.failing_stage == "routes"
    assert res.verdict.mounted == "canonical-substituted"


def test_dead_frontend_fails_at_boot():
    # nothing listening on this port → boot poll exhausts the (short) startup deadline → fail at boot
    res = G.run_gate("http://127.0.0.1:1", timeout=1.0, startup_timeout=1.0)
    assert res.verdict.failing_stage == "boot"


def test_extract_order_id():
    assert G.extract_order_id('<p id="order-id">Order ID: ORD-ABC-123</p>') == "ORD-ABC-123"
    assert G.extract_order_id("<p>Thank you for shopping!</p>") == ""
    assert G.extract_order_id("Order ID: ") == ""  # blank → not a real id
