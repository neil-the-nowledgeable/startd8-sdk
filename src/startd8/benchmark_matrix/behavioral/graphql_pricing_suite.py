"""GraphQL pricing-calculator behavioral ground-truth suite (GraphQL lane / FR-4 / FR-6 / FR-10).

The GraphQL counterpart to the gRPC + REST pricing suites — a **hybrid**: a single `basket(input)`
operation (the pure-calculator carve — all inputs explicit, deterministic) returning a graph of
**computed fields** the server must resolve (real GraphQL idiom). Asserted with httpx (already a core
dep) over `POST /graphql`, honoring the GraphQL convention: **always HTTP 200**; success = `data`
present + no top-level `errors`; failure = `errors` present.

Two layers:
  L1 (cross-protocol core) — the same G1–G7 + roll-up pricing ground truth as gRPC/REST, over a FIXED
     full selection, so the core stays comparable across protocols.
  L2 (GraphQL hardening, FR-10 — the memorization-resistance lever gRPC/REST lack):
     - selection-driven computation (a query asking only `netPayable` must return only that field);
     - the `adjustment.tierPercents` / `effectivePercent` derivation fields (expose the arithmetic AS
       data — `effectivePercent` discriminates CHAIN 19.00 vs ADDITION 20.00 for the same tiers);
     - partial-error paths (one invalid line → HTTP 200, partial `data`, `errors[].path` at that line).

FR-47 rename: types/fields are neutral ("adjustment"/"tierFactors", not "discount"/proto names) so the
schema matches neither Liferay nor a pricing tutorial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import httpx

SUITE_VERSION = "graphql-pricing-suite/1"

# Canonical SDL — single source of truth. The gen script embeds it in the seed; the oracle test builds
# its schema from it. Money/quantities are decimal STRINGS (exact-decimal; Double fails the rounding).
SCHEMA_SDL = """
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

_FULL = """query($input: BasketInput!) {
  basket(input: $input) {
    lines { sku netPayable netPayableWithTax taxValue priceOnApplication
            adjustment { amount effectivePercent tierPercents } }
    subtotalNetPayable subtotalNetPayableWithTax
  }
}"""
_SEL_NET = "query($input: BasketInput!){ basket(input:$input){ lines { netPayable } } }"
_SEL_DERIV = "query($input: BasketInput!){ basket(input:$input){ lines { adjustment { effectivePercent tierPercents } } } }"


@dataclass
class RpcResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SuiteResult:
    suite_version: str
    results: List[RpcResult] = field(default_factory=list)
    connect_error: str = ""

    @property
    def coverage(self) -> float:
        return (sum(1 for r in self.results if r.passed) / len(self.results)) if self.results else 0.0

    def to_dict(self) -> dict:
        return {"suite_version": self.suite_version, "coverage": self.coverage,
                "connect_error": self.connect_error, "results": [r.__dict__ for r in self.results]}


def _ccy(scale=2, rounding="HALF_UP", code="USD"):
    return {"code": code, "scale": scale, "rounding": rounding}


def _adj(kind, tiers, maximum_amount=None):
    d = {"kind": kind, "tierFactors": list(tiers)}
    if maximum_amount is not None:
        d["maximumAmount"] = maximum_amount
    return d


def _line(sku="A", quantity="1", unit_price="10.00", offer_unit_price=None,
          price_on_application=False, adjustments=None, tax_rate=None):
    d = {"sku": sku, "quantity": quantity, "unitPrice": unit_price,
         "priceOnApplication": price_on_application, "adjustments": list(adjustments or [])}
    if offer_unit_price is not None:
        d["offerUnitPrice"] = offer_unit_price
    if tax_rate is not None:
        d["taxRate"] = tax_rate
    return d


def _input(lines, *, strategy="CHAIN", currency=None, calculate_tax=False, adjustments_pre_tax=True):
    return {"lines": list(lines), "strategy": strategy, "currency": currency or _ccy(),
            "calculateTax": calculate_tax, "adjustmentsPreTax": adjustments_pre_tax}


def run_graphql_pricing_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0,
                              tier: str = "baseline") -> SuiteResult:
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        client = httpx.Client(base_url=f"http://{host}:{port}", timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite

    def post(query, variables):
        return client.post("/graphql", json={"query": query, "variables": variables})

    def ok(query, variables):
        r = post(query, variables)
        if r.status_code != 200:
            raise AssertionError(f"status {r.status_code}: {r.text[:120]}")
        body = r.json()
        if body.get("errors"):
            raise AssertionError(f"unexpected errors: {body['errors'][:1]}")
        return body["data"]["basket"]

    def check(name, fn):
        try:
            suite.results.append(RpcResult(name, *fn()))
        except httpx.HTTPError as e:
            suite.results.append(RpcResult(name, False, f"transport error: {e}"))
        except Exception as e:  # noqa: BLE001
            suite.results.append(RpcResult(name, False, f"{type(e).__name__}: {e}"))

    def expect_errors(name, variables):
        # GraphQL invalid input: HTTP 200 + top-level `errors` present (never a 4xx).
        try:
            r = post(_FULL, variables)
            body = r.json()
            good = r.status_code == 200 and bool(body.get("errors"))
            suite.results.append(RpcResult(name, good,
                                           "200 + errors[]" if good else f"status={r.status_code} errors={bool(body.get('errors'))}"))
        except httpx.HTTPError as e:
            suite.results.append(RpcResult(name, False, f"transport error: {e}"))

    try:
        # ---- L1: cross-protocol core (G1-G7 + rollup over the full selection) ----
        def g1():
            b = ok(_FULL, {"input": _input([_line(quantity="2", unit_price="10.00")])})
            li = b["lines"][0]
            return (li["netPayable"] == "20.00" and b["subtotalNetPayable"] == "20.00",
                    f"net={li['netPayable']} sub={b['subtotalNetPayable']}")
        check("g1_sanity", g1)
        check("g2a_promo_lower", lambda: ((lambda li: (li["netPayable"] == "8.00", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="10.00", offer_unit_price="8.00")])})["lines"][0])))
        check("g2b_promo_higher_ignored", lambda: ((lambda li: (li["netPayable"] == "10.00", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="10.00", offer_unit_price="12.00")])})["lines"][0])))
        check("g3_chain_81", lambda: ((lambda li: (li["netPayable"] == "81.00", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                       strategy="CHAIN")})["lines"][0])))
        check("g3_addition_80", lambda: ((lambda li: (li["netPayable"] == "80.00", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                       strategy="ADDITION")})["lines"][0])))
        check("g4_half_up_013", lambda: ((lambda li: (li["netPayable"] == "0.13", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="0.25", adjustments=[_adj("PERCENTAGE", ["50"])])],
                                       currency=_ccy(rounding="HALF_UP"))})["lines"][0])))
        check("g4_half_even_012", lambda: ((lambda li: (li["netPayable"] == "0.12", li["netPayable"]))(
            ok(_FULL, {"input": _input([_line(unit_price="0.25", adjustments=[_adj("PERCENTAGE", ["50"])])],
                                       currency=_ccy(rounding="HALF_EVEN"))})["lines"][0])))

        def g5_pre():
            li = ok(_FULL, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("FIXED_AMOUNT", ["15"])],
                            tax_rate="20")], calculate_tax=True, adjustments_pre_tax=True)})["lines"][0]
            return (li["netPayable"] == "85.00" and li["netPayableWithTax"] == "102.00" and li["taxValue"] == "17.00",
                    f"net={li['netPayable']} wt={li['netPayableWithTax']} tax={li['taxValue']}")
        check("g5_pretax_85_102", g5_pre)

        def g5_post():
            li = ok(_FULL, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("FIXED_AMOUNT", ["15"])],
                            tax_rate="20")], calculate_tax=True, adjustments_pre_tax=False)})["lines"][0]
            return (li["netPayableWithTax"] == "105.00" and li["netPayable"] == "87.50" and li["taxValue"] == "17.50",
                    f"net={li['netPayable']} wt={li['netPayableWithTax']} tax={li['taxValue']}")
        check("g5_posttax_105_8750", g5_post)

        def g6():
            li = ok(_FULL, {"input": _input([_line(unit_price="100.00",
                            adjustments=[_adj("PERCENTAGE", ["50"], maximum_amount="30")])])})["lines"][0]
            return (li["netPayable"] == "70.00" and li["adjustment"]["amount"] == "30.00",
                    f"net={li['netPayable']} adj={li['adjustment']['amount']}")
        check("g6_cap_70", g6)

        def g7_poa():
            li = ok(_FULL, {"input": _input([_line(price_on_application=True, unit_price="99.00")])})["lines"][0]
            return (li["priceOnApplication"] and li["netPayable"] == "",
                    f"poa={li['priceOnApplication']} net='{li['netPayable']}'")
        check("g7_poa", g7_poa)

        expect_errors("g7_negative_quantity", {"input": _input([_line(quantity="-1", unit_price="10.00")])})
        expect_errors("g7_unspecified_strategy",
                      {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                       strategy="")})
        expect_errors("g7_too_many_tiers",
                      {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["1", "2", "3", "4", "5"])])])})

        def rollup():
            b = ok(_FULL, {"input": _input([_line(sku="A", unit_price="10.00"),
                                            _line(sku="B", unit_price="20.00", adjustments=[_adj("PERCENTAGE", ["10"])])])})
            return (b["subtotalNetPayable"] == "28.00", b["subtotalNetPayable"])
        check("subtotal_rollup_28", rollup)

        # ---- L2: GraphQL hardening probes (FR-10) ----
        def h1_selection_only():
            # Ask ONLY netPayable — the response must contain only that field (selection-driven).
            r = post(_SEL_NET, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                                 strategy="CHAIN")})
            li = r.json()["data"]["basket"]["lines"][0]
            return (li.get("netPayable") == "81.00" and set(li.keys()) == {"netPayable"},
                    f"keys={sorted(li.keys())} net={li.get('netPayable')}")
        check("h1_selection_only_netpayable", h1_selection_only)

        def h2_deriv_chain():
            li = ok(_SEL_DERIV, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                                 strategy="CHAIN")})["lines"][0]
            a = li["adjustment"]
            return (a["effectivePercent"] == "19.00" and a["tierPercents"] == ["10", "10"],
                    f"eff={a['effectivePercent']} tiers={a['tierPercents']}")
        check("h2_derivation_chain_19", h2_deriv_chain)

        def h3_deriv_addition():
            li = ok(_SEL_DERIV, {"input": _input([_line(unit_price="100.00", adjustments=[_adj("PERCENTAGE", ["10", "10"])])],
                                                 strategy="ADDITION")})["lines"][0]
            return (li["adjustment"]["effectivePercent"] == "20.00", li["adjustment"]["effectivePercent"])
        check("h3_derivation_addition_20", h3_deriv_addition)

        def h4_partial_error_path():
            # Line 1 (index 1) is invalid; line 0 valid. Expect HTTP 200, partial data, errors[].path at line 1.
            r = post(_SEL_NET, {"input": _input([_line(sku="A", unit_price="10.00"),
                                                 _line(sku="B", quantity="-1", unit_price="20.00")])})
            body = r.json()
            errs = body.get("errors") or []
            paths = [e.get("path") for e in errs]
            has_path = any(p and len(p) >= 3 and p[0] == "basket" and p[1] == "lines" and p[2] == 1 for p in paths)
            line0_ok = (((body.get("data") or {}).get("basket") or {}).get("lines") or [{}])[0].get("netPayable") == "10.00"
            return (r.status_code == 200 and has_path and line0_ok,
                    f"status={r.status_code} paths={paths} line0={line0_ok}")
        check("h4_partial_error_path", h4_partial_error_path)
    except httpx.HTTPError as e:
        suite.connect_error = f"{type(e).__name__}: {e}"
    finally:
        client.close()
    return suite
