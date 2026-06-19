"""Validate the GraphQL pricing suite against a correct graphql-core reference server
(GraphQL lane / FR-4 / FR-6 / FR-10).

The reference uses graphql-core with LAZY field resolvers (so a single invalid line errors only that
line's field — partial-error paths — instead of null-propagating the whole response) and decimal-exact
pricing. It proves (a) the GraphQL ground truth is self-consistent (coverage 1.0 across L1 core + L2
hardening), (b) selection-driven computation returns only selected fields, (c) the tierPercents/
effectivePercent derivation fields discriminate CHAIN vs ADDITION, and (d) partial-error paths work.

Gated on graphql-core (the repo's importorskip pattern); the model's GraphQL server would also use it.
"""
from __future__ import annotations

import json
import socket
import threading
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

graphql = pytest.importorskip("graphql")
from graphql import GraphQLError, build_schema, graphql_sync  # noqa: E402

from startd8.benchmark_matrix.readiness import wait_ready  # noqa: E402
from startd8.benchmark_matrix.behavioral.graphql_pricing_suite import (  # noqa: E402
    SCHEMA_SDL, run_graphql_pricing_suite,
)


def _q(scale):
    return Decimal(1).scaleb(-scale)


def _round(d, scale, mode):
    return d.quantize(_q(scale), rounding=ROUND_HALF_EVEN if mode == "HALF_EVEN" else ROUND_HALF_UP)


def _fmt(d, scale):
    return str(d.quantize(_q(scale)))


def price_line(line: dict, ctx: dict) -> dict:
    """Compute one priced line (decimal-exact). Raise GraphQLError on a line-level invalid input."""
    scale = int(ctx.get("currency", {}).get("scale", 2))
    mode = ctx.get("currency", {}).get("rounding", "HALF_UP")
    strategy = ctx.get("strategy", "")
    if line.get("priceOnApplication"):
        return {"sku": line.get("sku", ""), "netPayable": "", "netPayableWithTax": "", "taxValue": "",
                "priceOnApplication": True,
                "_adj": {"amount": "", "effectivePercent": "", "tierPercents": []},
                "netI": Decimal(0), "netTaxI": Decimal(0)}
    try:
        qty = Decimal(line["quantity"])
        unit = Decimal(line["unitPrice"])
    except (InvalidOperation, KeyError):
        raise GraphQLError("malformed decimal")
    if qty <= 0 or unit < 0:
        raise GraphQLError("non-positive quantity or negative price")
    base_unit = unit
    offer = line.get("offerUnitPrice")
    if offer:
        od = Decimal(offer)
        if od > 0 and od < unit:
            base_unit = od
    line_base = base_unit * qty
    adjustments = line.get("adjustments") or []
    for a in adjustments:
        if not (1 <= len(a.get("tierFactors") or []) <= 4):
            raise GraphQLError("tiers must number 1..4")

    def apply(base):
        running = base
        for a in adjustments:
            kind = a.get("kind")
            if kind == "PERCENTAGE":
                tiers = [Decimal(t) for t in a["tierFactors"]]
                if strategy == "CHAIN":
                    dd = running
                    for t in tiers:
                        dd = dd - dd * (t / Decimal(100))
                else:
                    dd = running * (Decimal(1) - sum(tiers, Decimal(0)) / Decimal(100))
                amt = running - dd
            elif kind == "FIXED_AMOUNT":
                amt = Decimal(a["tierFactors"][0])
                if amt > running:
                    amt = running
            else:
                raise GraphQLError("adjustment kind required")
            mx = a.get("maximumAmount")
            if mx and amt > Decimal(mx):
                amt = Decimal(mx)
            running = running - amt
        return running

    rate = Decimal(line["taxRate"]) if line.get("taxRate") else Decimal(0)
    if not ctx.get("calculateTax", False):
        disc = apply(line_base)
        net = _round(disc, scale, mode); net_tax = net; tax = Decimal(0); db, da = line_base, disc
    elif ctx.get("adjustmentsPreTax", True):
        disc = apply(line_base)
        net = _round(disc, scale, mode)
        tax = _round(net * rate / Decimal(100), scale, mode)
        net_tax = net + tax; db, da = line_base, disc
    else:
        gross = line_base * (Decimal(1) + rate / Decimal(100))
        dg = apply(gross)
        net_tax = _round(dg, scale, mode)
        net = _round(net_tax / (Decimal(1) + rate / Decimal(100)), scale, mode)
        tax = net_tax - net; db, da = gross, dg

    eff = _round((line_base - da) / line_base * Decimal(100), scale, mode) if line_base > 0 else Decimal(0)
    tiers_out = []
    for a in adjustments:
        if a.get("kind") == "PERCENTAGE":
            tiers_out += list(a["tierFactors"])
        elif a.get("kind") == "FIXED_AMOUNT":
            tiers_out.append(_fmt(eff, scale))
    return {"sku": line.get("sku", ""), "netPayable": _fmt(net, scale),
            "netPayableWithTax": _fmt(net_tax, scale), "taxValue": _fmt(tax, scale),
            "priceOnApplication": False,
            "_adj": {"amount": _fmt(_round(db - da, scale, mode), scale),
                     "effectivePercent": _fmt(eff, scale), "tierPercents": tiers_out},
            "netI": net, "netTaxI": net_tax}


def _build_schema():
    schema = build_schema(SCHEMA_SDL)

    def resolve_basket(root, info, input):
        if any(li.get("adjustments") for li in input["lines"]) and input.get("strategy") not in ("CHAIN", "ADDITION"):
            raise GraphQLError("strategy required when adjustments present")
        return {"_input": input}

    def resolve_lines(basket, info):
        inp = basket["_input"]
        return [{"_line": li, "_ctx": inp} for li in inp["lines"]]

    def sub(key):
        def r(basket, info):
            inp = basket["_input"]
            total = sum((price_line(li, inp)[key] for li in inp["lines"]), Decimal(0))
            return _fmt(total, int(inp.get("currency", {}).get("scale", 2)))
        return r

    def line_field(key):
        def r(parent, info):
            return price_line(parent["_line"], parent["_ctx"])[key]
        return r

    schema.query_type.fields["basket"].resolve = resolve_basket
    pb = schema.type_map["PricedBasket"]
    pb.fields["lines"].resolve = resolve_lines
    pb.fields["subtotalNetPayable"].resolve = sub("netI")
    pb.fields["subtotalNetPayableWithTax"].resolve = sub("netTaxI")
    pl = schema.type_map["PricedLine"]
    pl.fields["sku"].resolve = lambda p, info: p["_line"].get("sku", "")
    for k in ("netPayable", "netPayableWithTax", "taxValue", "priceOnApplication"):
        pl.fields[k].resolve = line_field(k)
    pl.fields["adjustment"].resolve = line_field("_adj")  # returns dict; AdjustmentBreakdown default-resolves
    return schema


_SCHEMA = _build_schema()


class _Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        self._json(200, {}) if self.path == "/health" else self._json(404, {})

    def do_POST(self):  # noqa: N802
        if self.path != "/graphql":
            return self._json(404, {})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        result = graphql_sync(_SCHEMA, body["query"], variable_values=body.get("variables"))
        out = {"data": result.data}
        if result.errors:
            out["errors"] = [e.formatted for e in result.errors]
        self._json(200, out)

    def log_message(self, *a):
        pass


@pytest.fixture()
def gql_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield port
    finally:
        srv.shutdown()


def test_http_readiness(gql_server):
    assert wait_ready(gql_server, 3.0, mode="http", health_path="/health") is None


def test_graphql_suite_full_coverage(gql_server):
    result = run_graphql_pricing_suite(gql_server)
    assert result.connect_error == "", result.connect_error
    failing = [(r.name, r.detail) for r in result.results if not r.passed]
    assert result.coverage == 1.0, f"failing: {failing}"
    assert len(result.results) == 19  # L1 (15: G1-G7 + rollup) + L2 (4 hardening probes)
