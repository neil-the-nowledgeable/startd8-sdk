"""Validate the REST pricing suite against a correct stdlib reference server (S6 / FR-3 / FR-6).

The reference server is a **zero-dependency** Python `http.server` implementing the pricing contract
with `decimal.Decimal` (exact) — proving (a) the REST ground truth is self-consistent (coverage 1.0)
and (b) the http readiness probe (FR-2/FR-11) succeeds against a real REST server. The benchmarked
model writes its own REST server; this fixture is the oracle (the HTTP analog of the gRPC oracle).
"""
from __future__ import annotations

import json
import socket
import threading
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from startd8.benchmark_matrix.readiness import wait_ready
from startd8.benchmark_matrix.behavioral.rest_pricing_suite import run_rest_pricing_suite


class BadRequest(Exception):
    pass


def _q(scale):
    return Decimal(1).scaleb(-scale)


def _round(d, scale, mode):
    return d.quantize(_q(scale), rounding=ROUND_HALF_EVEN if mode == "HALF_EVEN" else ROUND_HALF_UP)


def _fmt(d, scale):
    return str(d.quantize(_q(scale)))


def compute_basket(req: dict) -> dict:
    strategy = req.get("strategy", "")
    currency = req.get("currency", {})
    scale = int(currency.get("scale", 2))
    mode = currency.get("rounding", "HALF_UP")
    items = req.get("items", [])
    if any(li.get("discounts") for li in items) and strategy not in ("CHAIN", "ADDITION"):
        raise BadRequest("strategy required when discounts present")
    out_items = []
    sub_net = Decimal(0)
    sub_tax = Decimal(0)
    for li in items:
        o = {"sku": li.get("sku", ""), "unit_price": "", "offer_unit_price": "", "net_payable": "",
             "tax_value": "", "net_payable_with_tax": "", "price_on_application": False,
             "discount_value": {"amount": "", "percentage": "", "factor_percentages": []},
             "discount_value_with_tax": {"amount": "", "percentage": "", "factor_percentages": []}}
        if li.get("price_on_application"):
            o["price_on_application"] = True
            out_items.append(o)
            continue
        try:
            qty = Decimal(li["quantity"])
            unit = Decimal(li["unit_price"])
        except (InvalidOperation, KeyError):
            raise BadRequest("malformed decimal")
        if qty <= 0 or unit < 0:
            raise BadRequest("non-positive quantity or negative price")
        base_unit = unit
        offer = li.get("offer_unit_price", "")
        if offer:
            offd = Decimal(offer)
            if offd > 0 and offd < unit:
                base_unit = offd
        line_base = base_unit * qty
        for d in li.get("discounts", []):
            if not (1 <= len(d.get("tier_factors", [])) <= 4):
                raise BadRequest("tiers must number 1..4")

        def apply_discounts(base, _li=li):
            running = base
            for d in _li.get("discounts", []):
                kind = d.get("kind")
                if kind == "PERCENTAGE":
                    tiers = [Decimal(t) for t in d["tier_factors"]]
                    if strategy == "CHAIN":
                        dd = running
                        for t in tiers:
                            dd = dd - dd * (t / Decimal(100))
                    else:
                        total = sum(tiers, Decimal(0))
                        dd = running * (Decimal(1) - total / Decimal(100))
                    amt = running - dd
                elif kind == "FIXED_AMOUNT":
                    amt = Decimal(d["tier_factors"][0])
                    if amt > running:
                        amt = running
                else:
                    raise BadRequest("discount kind required")
                mx = d.get("maximum_amount", "")
                if mx and amt > Decimal(mx):
                    amt = Decimal(mx)
                running = running - amt
            return running

        rate = Decimal(li["tax_rate"]) if li.get("tax_rate") else Decimal(0)
        if not req.get("calculate_tax", False):
            disc = apply_discounts(line_base)
            net = _round(disc, scale, mode)
            net_tax = net
            tax = Decimal(0)
            db, da = line_base, disc
        elif req.get("discounts_pre_tax", True):
            disc = apply_discounts(line_base)
            net = _round(disc, scale, mode)
            tax = _round(net * rate / Decimal(100), scale, mode)
            net_tax = net + tax
            db, da = line_base, disc
        else:
            gross = line_base * (Decimal(1) + rate / Decimal(100))
            dg = apply_discounts(gross)
            net_tax = _round(dg, scale, mode)
            net = _round(net_tax / (Decimal(1) + rate / Decimal(100)), scale, mode)
            tax = net_tax - net
            db, da = gross, dg

        o["unit_price"] = _fmt(unit, scale)
        if base_unit != unit:
            o["offer_unit_price"] = _fmt(base_unit, scale)
        o["net_payable"] = _fmt(net, scale)
        o["tax_value"] = _fmt(tax, scale)
        o["net_payable_with_tax"] = _fmt(net_tax, scale)
        o["discount_value"]["amount"] = _fmt(_round(db - da, scale, mode), scale)  # H1: honor request rounding
        out_items.append(o)
        sub_net += net
        sub_tax += net_tax
    return {"items": out_items, "subtotal_net_payable": _fmt(sub_net, scale),
            "subtotal_net_payable_with_tax": _fmt(sub_tax, scale)}


class _Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._json(200, {}) if self.path == "/health" else self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/price":
            return self._json(404, {"error": "not found"})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            result = compute_basket(json.loads(body))
        except BadRequest as e:
            return self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._json(400, {"error": f"bad request: {e}"})
        self._json(200, result)

    def log_message(self, *a):
        pass


@pytest.fixture()
def rest_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield port
    finally:
        srv.shutdown()


def test_http_readiness_succeeds(rest_server):
    """FR-2/FR-11: the shared http readiness probe sees a real REST server as ready."""
    assert wait_ready(rest_server, 3.0, mode="http", health_path="/health") is None


def test_rest_suite_full_coverage(rest_server):
    """FR-3/FR-6: a correct REST server passes every ground-truth check (the REST ground truth is self-consistent)."""
    result = run_rest_pricing_suite(rest_server)
    assert result.connect_error == "", result.connect_error
    failing = [(r.name, r.detail) for r in result.results if not r.passed]
    assert result.coverage == 1.0, f"failing: {failing}"
    assert len(result.results) == 15
