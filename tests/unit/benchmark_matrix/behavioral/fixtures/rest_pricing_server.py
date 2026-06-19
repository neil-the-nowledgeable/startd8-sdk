#!/usr/bin/env python3
"""Correct stdlib REST pricing server (e2e fixture) — the oracle, runnable as a subprocess.

Reads PORT from env, serves GET /health -> 200 and POST /price (decimal-exact). Zero deps. Used by
test_rest_pricing_e2e to prove the full harness path: provision -> sandbox subprocess -> http
readiness -> run_rest_pricing_suite. The benchmarked model writes its own server; this is the oracle.
"""
import json
import os
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BadRequest(Exception):
    pass


def _q(scale):
    return Decimal(1).scaleb(-scale)


def _round(d, scale, mode):
    return d.quantize(_q(scale), rounding=ROUND_HALF_EVEN if mode == "HALF_EVEN" else ROUND_HALF_UP)


def _fmt(d, scale):
    return str(d.quantize(_q(scale)))


def compute_basket(req):
    strategy = req.get("strategy", "")
    cur = req.get("currency", {})
    scale = int(cur.get("scale", 2))
    mode = cur.get("rounding", "HALF_UP")
    items = req.get("items", [])
    if any(li.get("discounts") for li in items) and strategy not in ("CHAIN", "ADDITION"):
        raise BadRequest("strategy required when discounts present")
    out, sub_net, sub_tax = [], Decimal(0), Decimal(0)
    for li in items:
        o = {"sku": li.get("sku", ""), "unit_price": "", "offer_unit_price": "", "net_payable": "",
             "tax_value": "", "net_payable_with_tax": "", "price_on_application": False,
             "discount_value": {"amount": "", "percentage": "", "factor_percentages": []},
             "discount_value_with_tax": {"amount": "", "percentage": "", "factor_percentages": []}}
        if li.get("price_on_application"):
            o["price_on_application"] = True
            out.append(o)
            continue
        try:
            qty = Decimal(li["quantity"]); unit = Decimal(li["unit_price"])
        except (InvalidOperation, KeyError):
            raise BadRequest("malformed decimal")
        if qty <= 0 or unit < 0:
            raise BadRequest("non-positive quantity or negative price")
        base_unit = unit
        offer = li.get("offer_unit_price", "")
        if offer and Decimal(offer) > 0 and Decimal(offer) < unit:
            base_unit = Decimal(offer)
        line_base = base_unit * qty
        for d in li.get("discounts", []):
            if not (1 <= len(d.get("tier_factors", [])) <= 4):
                raise BadRequest("tiers must number 1..4")

        def apply(base, _li=li):
            running = base
            for d in _li.get("discounts", []):
                if d.get("kind") == "PERCENTAGE":
                    tiers = [Decimal(t) for t in d["tier_factors"]]
                    if strategy == "CHAIN":
                        dd = running
                        for t in tiers:
                            dd = dd - dd * (t / Decimal(100))
                    else:
                        dd = running * (Decimal(1) - sum(tiers, Decimal(0)) / Decimal(100))
                    amt = running - dd
                elif d.get("kind") == "FIXED_AMOUNT":
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
            disc = apply(line_base); net = _round(disc, scale, mode); net_tax = net; tax = Decimal(0); db, da = line_base, disc
        elif req.get("discounts_pre_tax", True):
            disc = apply(line_base); net = _round(disc, scale, mode)
            tax = _round(net * rate / Decimal(100), scale, mode); net_tax = net + tax; db, da = line_base, disc
        else:
            gross = line_base * (Decimal(1) + rate / Decimal(100)); dg = apply(gross)
            net_tax = _round(dg, scale, mode); net = _round(net_tax / (Decimal(1) + rate / Decimal(100)), scale, mode)
            tax = net_tax - net; db, da = gross, dg
        o["unit_price"] = _fmt(unit, scale)
        if base_unit != unit:
            o["offer_unit_price"] = _fmt(base_unit, scale)
        o["net_payable"] = _fmt(net, scale)
        o["tax_value"] = _fmt(tax, scale)
        o["net_payable_with_tax"] = _fmt(net_tax, scale)
        o["discount_value"]["amount"] = _fmt(_round(db - da, scale, mode), scale)
        out.append(o)
        sub_net += net; sub_tax += net_tax
    return {"items": out, "subtotal_net_payable": _fmt(sub_net, scale),
            "subtotal_net_payable_with_tax": _fmt(sub_tax, scale)}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json(200, {}) if self.path == "/health" else self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/price":
            return self._json(404, {"error": "not found"})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            self._json(200, compute_basket(json.loads(body)))
        except BadRequest as e:
            self._json(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            self._json(400, {"error": f"bad request: {e}"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
