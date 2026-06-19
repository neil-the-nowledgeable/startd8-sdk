#!/usr/bin/env python3
"""Correct GraphQL pricing server (e2e fixture) — the oracle, runnable as a subprocess.

Reads PORT; serves GET /health -> 200 and POST /graphql. Uses graphql-core (declared in the cell's
requirements.txt → installed to .pydeps → importable via the harness PYTHONPATH injection). Embeds the
SDL inline (a subprocess can't import the SDK). Lazy field resolvers + nullable list elements give real
partial-error paths. Used by test_graphql_pricing_e2e to prove the full subprocess + provision + http
readiness path (and that the .pydeps import fix works).
"""
import json
import os
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from graphql import GraphQLError, build_schema, graphql_sync

SDL = """
input AdjustmentInput { kind: String!, tierFactors: [String!]!, maximumAmount: String }
input LineInput {
  sku: String!, quantity: String!, unitPrice: String!, offerUnitPrice: String,
  priceOnApplication: Boolean, adjustments: [AdjustmentInput!], taxRate: String
}
input CurrencyInput { code: String!, scale: Int!, rounding: String! }
input BasketInput {
  lines: [LineInput!]!, strategy: String!, currency: CurrencyInput!,
  calculateTax: Boolean!, adjustmentsPreTax: Boolean!
}
type AdjustmentBreakdown { amount: String!, effectivePercent: String!, tierPercents: [String!]! }
type PricedLine {
  sku: String!, netPayable: String!, netPayableWithTax: String!, taxValue: String!,
  priceOnApplication: Boolean!, adjustment: AdjustmentBreakdown!
}
type PricedBasket { lines: [PricedLine]!, subtotalNetPayable: String!, subtotalNetPayableWithTax: String! }
type Query { basket(input: BasketInput!): PricedBasket! }
"""


def _q(scale):
    return Decimal(1).scaleb(-scale)


def _round(d, scale, mode):
    return d.quantize(_q(scale), rounding=ROUND_HALF_EVEN if mode == "HALF_EVEN" else ROUND_HALF_UP)


def _fmt(d, scale):
    return str(d.quantize(_q(scale)))


def price_line(line, ctx):
    scale = int(ctx.get("currency", {}).get("scale", 2))
    mode = ctx.get("currency", {}).get("rounding", "HALF_UP")
    strategy = ctx.get("strategy", "")
    if line.get("priceOnApplication"):
        return {"sku": line.get("sku", ""), "netPayable": "", "netPayableWithTax": "", "taxValue": "",
                "priceOnApplication": True,
                "_adj": {"amount": "", "effectivePercent": "", "tierPercents": []},
                "netI": Decimal(0), "netTaxI": Decimal(0)}
    try:
        qty = Decimal(line["quantity"]); unit = Decimal(line["unitPrice"])
    except (InvalidOperation, KeyError):
        raise GraphQLError("malformed decimal")
    if qty <= 0 or unit < 0:
        raise GraphQLError("non-positive quantity or negative price")
    base_unit = unit
    offer = line.get("offerUnitPrice")
    if offer and Decimal(offer) > 0 and Decimal(offer) < unit:
        base_unit = Decimal(offer)
    line_base = base_unit * qty
    adjustments = line.get("adjustments") or []
    for a in adjustments:
        if not (1 <= len(a.get("tierFactors") or []) <= 4):
            raise GraphQLError("tiers must number 1..4")

    def apply(base):
        running = base
        for a in adjustments:
            if a.get("kind") == "PERCENTAGE":
                tiers = [Decimal(t) for t in a["tierFactors"]]
                if strategy == "CHAIN":
                    dd = running
                    for t in tiers:
                        dd = dd - dd * (t / Decimal(100))
                else:
                    dd = running * (Decimal(1) - sum(tiers, Decimal(0)) / Decimal(100))
                amt = running - dd
            elif a.get("kind") == "FIXED_AMOUNT":
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
        disc = apply(line_base); net = _round(disc, scale, mode); net_tax = net; tax = Decimal(0); db, da = line_base, disc
    elif ctx.get("adjustmentsPreTax", True):
        disc = apply(line_base); net = _round(disc, scale, mode)
        tax = _round(net * rate / Decimal(100), scale, mode); net_tax = net + tax; db, da = line_base, disc
    else:
        gross = line_base * (Decimal(1) + rate / Decimal(100)); dg = apply(gross)
        net_tax = _round(dg, scale, mode); net = _round(net_tax / (Decimal(1) + rate / Decimal(100)), scale, mode)
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


def _build():
    schema = build_schema(SDL)

    def resolve_basket(root, info, input):
        if any(li.get("adjustments") for li in input["lines"]) and input.get("strategy") not in ("CHAIN", "ADDITION"):
            raise GraphQLError("strategy required when adjustments present")
        return {"_input": input}

    def resolve_lines(b, info):
        return [{"_line": li, "_ctx": b["_input"]} for li in b["_input"]["lines"]]

    def sub(key):
        def r(b, info):
            inp = b["_input"]
            total = sum((price_line(li, inp)[key] for li in inp["lines"]), Decimal(0))
            return _fmt(total, int(inp.get("currency", {}).get("scale", 2)))
        return r

    def line_field(key):
        return lambda p, info: price_line(p["_line"], p["_ctx"])[key]

    schema.query_type.fields["basket"].resolve = resolve_basket
    pb = schema.type_map["PricedBasket"]
    pb.fields["lines"].resolve = resolve_lines
    pb.fields["subtotalNetPayable"].resolve = sub("netI")
    pb.fields["subtotalNetPayableWithTax"].resolve = sub("netTaxI")
    pl = schema.type_map["PricedLine"]
    pl.fields["sku"].resolve = lambda p, info: p["_line"].get("sku", "")
    for k in ("netPayable", "netPayableWithTax", "taxValue", "priceOnApplication"):
        pl.fields[k].resolve = line_field(k)
    pl.fields["adjustment"].resolve = line_field("_adj")
    return schema


SCHEMA = _build()


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json(200, {}) if self.path == "/health" else self._json(404, {})

    def do_POST(self):
        if self.path != "/graphql":
            return self._json(404, {})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        result = graphql_sync(SCHEMA, body["query"], variable_values=body.get("variables"))
        out = {"data": result.data}
        if result.errors:
            out["errors"] = [e.formatted for e in result.errors]
        self._json(200, out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
