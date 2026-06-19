"""REST pricing-calculator behavioral ground-truth suite (REST lane / FR-3 / FR-6).

The HTTP/REST counterpart to ``pricing_suite.py`` (gRPC). Same Liferay-derived pricing semantics
(G1-G7 + subtotal roll-up), asserted over the wire with **httpx** (already a core SDK dependency) —
``POST /price`` with a JSON basket, asserting status + response JSON; invalid requests must return
HTTP 400. Returns the SAME protocol-neutral ``SuiteResult`` the gRPC suites use, so the registry,
scoring fold, and degrade path are unchanged.

Contract (OpenAPI-derived, embedded in the seed's requirements_text):
  POST /price  {items[], strategy, currency{code,scale,rounding}, calculate_tax, discounts_pre_tax}
    -> 200 {items[]{sku,unit_price,offer_unit_price,net_payable,discount_value{amount,percentage,
            factor_percentages},tax_value,net_payable_with_tax,price_on_application},
            subtotal_net_payable, subtotal_net_payable_with_tax}
    -> 400 on invalid input.  GET /health -> 200.
Enums are JSON strings: strategy CHAIN|ADDITION, discount kind PERCENTAGE|FIXED_AMOUNT,
rounding HALF_UP|HALF_EVEN.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import httpx

SUITE_VERSION = "rest-pricing-suite/1"


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
        return {
            "suite_version": self.suite_version,
            "coverage": self.coverage,
            "connect_error": self.connect_error,
            "results": [r.__dict__ for r in self.results],
        }


def _ccy(scale: int = 2, rounding: str = "HALF_UP", code: str = "USD"):
    return {"code": code, "scale": scale, "rounding": rounding}


def _disc(kind, tiers, maximum_amount: str = ""):
    return {"kind": kind, "tier_factors": list(tiers), "maximum_amount": maximum_amount}


def _item(sku="A", quantity="1", unit_price="10.00", offer_unit_price="",
          price_on_application=False, discounts=None, tax_rate=""):
    return {"sku": sku, "quantity": quantity, "unit_price": unit_price,
            "offer_unit_price": offer_unit_price, "price_on_application": price_on_application,
            "discounts": list(discounts or []), "tax_rate": tax_rate}


def _req(items, *, strategy="CHAIN", currency=None, calculate_tax=False, discounts_pre_tax=True):
    return {"items": list(items), "strategy": strategy, "currency": currency or _ccy(),
            "calculate_tax": calculate_tax, "discounts_pre_tax": discounts_pre_tax}


def run_rest_pricing_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0,
                           tier: str = "baseline") -> SuiteResult:
    """Connect to a live REST PricingService and run the ComputeBasket ground-truth checks over HTTP."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        client = httpx.Client(base_url=f"http://{host}:{port}", timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite

    def price(req):
        return client.post("/price", json=req)

    def check(name: str, fn):
        try:
            suite.results.append(RpcResult(name, *fn()))
        except httpx.HTTPError as e:
            suite.results.append(RpcResult(name, False, f"transport error: {type(e).__name__}: {e}"))
        except Exception as e:  # noqa: BLE001
            suite.results.append(RpcResult(name, False, f"{type(e).__name__}: {e}"))

    def expect_invalid(name: str, req):
        try:
            r = price(req)
            good = r.status_code == 400
            suite.results.append(RpcResult(name, good,
                                           "400 as expected" if good else f"wrong status {r.status_code}"))
        except httpx.HTTPError as e:
            suite.results.append(RpcResult(name, False, f"transport error: {e}"))

    def ok200(req):
        r = price(req)
        if r.status_code != 200:
            raise AssertionError(f"status {r.status_code}: {r.text[:120]}")
        return r.json()

    try:
        # G1 — sanity.
        def g1():
            d = ok200(_req([_item(quantity="2", unit_price="10.00")]))
            li = d["items"][0]
            return (li["net_payable"] == "20.00" and d["subtotal_net_payable"] == "20.00",
                    f"net={li['net_payable']} subtotal={d['subtotal_net_payable']}")
        check("g1_sanity", g1)

        # G2a/G2b — promo-min.
        check("g2a_promo_lower_wins", lambda: (
            (lambda li: (li["net_payable"] == "8.00", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="10.00", offer_unit_price="8.00")]))["items"][0])))
        check("g2b_promo_higher_ignored", lambda: (
            (lambda li: (li["net_payable"] == "10.00", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="10.00", offer_unit_price="12.00")]))["items"][0])))

        # G3 — chain vs addition.
        check("g3_chain_81", lambda: (
            (lambda li: (li["net_payable"] == "81.00", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="100.00", discounts=[_disc("PERCENTAGE", ["10", "10"])])],
                           strategy="CHAIN"))["items"][0])))
        check("g3_addition_80", lambda: (
            (lambda li: (li["net_payable"] == "80.00", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="100.00", discounts=[_disc("PERCENTAGE", ["10", "10"])])],
                           strategy="ADDITION"))["items"][0])))

        # G4 — rounding boundary.
        check("g4_half_up_013", lambda: (
            (lambda li: (li["net_payable"] == "0.13", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="0.25", discounts=[_disc("PERCENTAGE", ["50"])])],
                           currency=_ccy(rounding="HALF_UP")))["items"][0])))
        check("g4_half_even_012", lambda: (
            (lambda li: (li["net_payable"] == "0.12", f"net={li['net_payable']}"))(
                ok200(_req([_item(unit_price="0.25", discounts=[_disc("PERCENTAGE", ["50"])])],
                           currency=_ccy(rounding="HALF_EVEN")))["items"][0])))

        # G5 — tax/discount ordering.
        def g5_pre():
            li = ok200(_req([_item(unit_price="100.00", discounts=[_disc("FIXED_AMOUNT", ["15"])],
                                   tax_rate="20")], calculate_tax=True, discounts_pre_tax=True))["items"][0]
            return (li["net_payable"] == "85.00" and li["net_payable_with_tax"] == "102.00"
                    and li["tax_value"] == "17.00",
                    f"net={li['net_payable']} w/tax={li['net_payable_with_tax']} tax={li['tax_value']}")
        check("g5_pretax_85_102", g5_pre)

        def g5_post():
            li = ok200(_req([_item(unit_price="100.00", discounts=[_disc("FIXED_AMOUNT", ["15"])],
                                   tax_rate="20")], calculate_tax=True, discounts_pre_tax=False))["items"][0]
            return (li["net_payable_with_tax"] == "105.00" and li["net_payable"] == "87.50"
                    and li["tax_value"] == "17.50",
                    f"net={li['net_payable']} w/tax={li['net_payable_with_tax']} tax={li['tax_value']}")
        check("g5_posttax_105_8750", g5_post)

        # G6 — cap.
        def g6():
            li = ok200(_req([_item(unit_price="100.00",
                                   discounts=[_disc("PERCENTAGE", ["50"], maximum_amount="30")])]))["items"][0]
            return (li["net_payable"] == "70.00" and li["discount_value"]["amount"] == "30.00",
                    f"net={li['net_payable']} disc={li['discount_value']['amount']}")
        check("g6_cap_70", g6)

        # G7 — POA pass-through.
        def g7_poa():
            li = ok200(_req([_item(price_on_application=True, unit_price="99.00")]))["items"][0]
            return (li["price_on_application"] and li["net_payable"] == "",
                    f"poa={li['price_on_application']} net='{li['net_payable']}'")
        check("g7_poa_passthrough", g7_poa)

        # G7 — invalid inputs -> 400.
        expect_invalid("g7_negative_quantity", _req([_item(quantity="-1", unit_price="10.00")]))
        expect_invalid("g7_unspecified_strategy",
                       _req([_item(unit_price="100.00", discounts=[_disc("PERCENTAGE", ["10", "10"])])],
                            strategy=""))
        expect_invalid("g7_too_many_tiers",
                       _req([_item(unit_price="100.00",
                                   discounts=[_disc("PERCENTAGE", ["1", "2", "3", "4", "5"])])]))

        # Multi-line subtotal roll-up.
        def rollup():
            d = ok200(_req([_item(sku="A", unit_price="10.00"),
                            _item(sku="B", unit_price="20.00",
                                  discounts=[_disc("PERCENTAGE", ["10"])])]))
            return (d["subtotal_net_payable"] == "28.00", f"subtotal={d['subtotal_net_payable']}")
        check("subtotal_rollup_28", rollup)
    except httpx.HTTPError as e:
        suite.connect_error = f"{type(e).__name__}: {e}"
    finally:
        client.close()
    return suite
