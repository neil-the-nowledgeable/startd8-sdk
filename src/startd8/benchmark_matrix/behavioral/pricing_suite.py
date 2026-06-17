"""PricingService.ComputeBasket behavioral ground-truth suite (M-T2.3 / FR-T2-SUITE / FR-T2-PROV).

SDK-authored, language-agnostic over the gRPC wire — it talks to a live PricingService on
``127.0.0.1:<port>`` regardless of what language the server was generated in. It asserts the
*arithmetic* of the ComputeBasket contract (Liferay-derived pricing calculator,
docs/design/liferay-pricing-seed/), which is what discriminates frontier models: exact-decimal
math with an explicit rounding mode, chain-vs-addition tier combination, promo-min selection,
tax/discount ordering, a discount cap, POA pass-through, and input validation.

The canonical algorithm each assertion encodes (per line item, non-POA):
  base_unit  = min(unit_price, offer_unit_price>0)            # promo-min
  line_base  = base_unit * quantity                           # exact decimal
  for each discount (applied to the running amount):
    PERCENTAGE: CHAIN  -> d = d - d*(tier/100) per tier
                ADDITION -> d = d * (1 - sum(tiers)/100)
    FIXED_AMOUNT: discount_amt = tier_factors[0] (per-line), <= running
    cap: discount_amt = min(discount_amt, maximum_amount)
  discounts_pre_tax=true : round net, then tax = round(net*rate); with_tax = net + tax
  discounts_pre_tax=false: discount the GROSS (line_base*(1+rate)), with_tax = round(gross');
                           net = round(gross'/(1+rate)); tax = with_tax - net

``coverage`` ∈ [0,1] = passing checks / total; provenance carries the suite version + per-check results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import grpc

from . import pricing_pb2 as pb
from . import pricing_pb2_grpc

SUITE_VERSION = "pricing-suite/1"


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


def _ccy(scale: int = 2, rounding=pb.HALF_UP, code: str = "USD"):
    return pb.Currency(code=code, scale=scale, rounding=rounding)


def _disc(kind, tiers, maximum_amount: str = ""):
    return pb.Discount(kind=kind, tier_factors=list(tiers), maximum_amount=maximum_amount)


def _item(sku="A", quantity="1", unit_price="10.00", offer_unit_price="",
          price_on_application=False, discounts=None, tax_rate=""):
    return pb.LineItem(
        sku=sku, quantity=quantity, unit_price=unit_price, offer_unit_price=offer_unit_price,
        price_on_application=price_on_application, discounts=list(discounts or []), tax_rate=tax_rate,
    )


def _req(items, *, strategy=pb.CHAIN, currency=None, calculate_tax=False, discounts_pre_tax=True):
    return pb.ComputeBasketRequest(
        items=list(items), strategy=strategy, currency=currency or _ccy(),
        calculate_tax=calculate_tax, discounts_pre_tax=discounts_pre_tax,
    )


def run_pricing_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0) -> SuiteResult:
    """Connect to a live PricingService and run the ComputeBasket ground-truth checks."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite

    stub = pricing_pb2_grpc.PricingServiceStub(channel)

    def ok(req, timeout=5.0):
        return stub.ComputeBasket(req, timeout=timeout)

    def check(name: str, fn):
        try:
            suite.results.append(RpcResult(name, *fn()))
        except grpc.RpcError as e:
            suite.results.append(RpcResult(name, False, f"unexpected RPC error: {e.code()}"))
        except Exception as e:  # noqa: BLE001
            suite.results.append(RpcResult(name, False, f"{type(e).__name__}: {e}"))

    def expect_invalid(name: str, req):
        try:
            ok(req)
            suite.results.append(RpcResult(name, False, "accepted an invalid request"))
        except grpc.RpcError as e:
            good = e.code() == grpc.StatusCode.INVALID_ARGUMENT
            suite.results.append(RpcResult(name, good,
                                           "INVALID_ARGUMENT" if good else f"wrong code {e.code()}"))

    try:
        # G1 — sanity: qty 2 x 10.00, no discount, no tax.
        def g1():
            r = ok(_req([_item(quantity="2", unit_price="10.00")]))
            li = r.items[0]
            return (li.net_payable == "20.00" and r.subtotal_net_payable == "20.00",
                    f"net={li.net_payable} subtotal={r.subtotal_net_payable}")
        check("g1_sanity", g1)

        # G2a — promo lower replaces unit price.
        def g2a():
            r = ok(_req([_item(unit_price="10.00", offer_unit_price="8.00")]))
            return (r.items[0].net_payable == "8.00", f"net={r.items[0].net_payable}")
        check("g2a_promo_lower_wins", g2a)

        # G2b — promo higher is ignored.
        def g2b():
            r = ok(_req([_item(unit_price="10.00", offer_unit_price="12.00")]))
            return (r.items[0].net_payable == "10.00", f"net={r.items[0].net_payable}")
        check("g2b_promo_higher_ignored", g2b)

        # G3 — CHAIN: 100 -> 90 -> 81.
        def g3_chain():
            r = ok(_req([_item(unit_price="100.00", discounts=[_disc(pb.PERCENTAGE, ["10", "10"])])],
                        strategy=pb.CHAIN))
            return (r.items[0].net_payable == "81.00", f"net={r.items[0].net_payable}")
        check("g3_chain_81", g3_chain)

        # G3 — ADDITION: 100 * (1 - 0.20) = 80.
        def g3_add():
            r = ok(_req([_item(unit_price="100.00", discounts=[_disc(pb.PERCENTAGE, ["10", "10"])])],
                        strategy=pb.ADDITION))
            return (r.items[0].net_payable == "80.00", f"net={r.items[0].net_payable}")
        check("g3_addition_80", g3_add)

        # G4 — HALF_UP boundary: 0.25 * 50% off -> raw 0.125 -> 0.13.
        def g4_up():
            r = ok(_req([_item(unit_price="0.25", discounts=[_disc(pb.PERCENTAGE, ["50"])])],
                        currency=_ccy(rounding=pb.HALF_UP)))
            return (r.items[0].net_payable == "0.13", f"net={r.items[0].net_payable}")
        check("g4_half_up_013", g4_up)

        # G4 — HALF_EVEN boundary: 0.125 -> 0.12.
        def g4_even():
            r = ok(_req([_item(unit_price="0.25", discounts=[_disc(pb.PERCENTAGE, ["50"])])],
                        currency=_ccy(rounding=pb.HALF_EVEN)))
            return (r.items[0].net_payable == "0.12", f"net={r.items[0].net_payable}")
        check("g4_half_even_012", g4_even)

        # G5 — tax/discount ordering, pre-tax (net-target): 100 -15 = 85; +20% tax = 102.
        def g5_pre():
            r = ok(_req([_item(unit_price="100.00", discounts=[_disc(pb.FIXED_AMOUNT, ["15"])],
                               tax_rate="20")], calculate_tax=True, discounts_pre_tax=True))
            li = r.items[0]
            return (li.net_payable == "85.00" and li.net_payable_with_tax == "102.00"
                    and li.tax_value == "17.00",
                    f"net={li.net_payable} w/tax={li.net_payable_with_tax} tax={li.tax_value}")
        check("g5_pretax_85_102", g5_pre)

        # G5 — post-tax (gross-target): gross 120 -15 = 105; net = 105/1.2 = 87.50.
        def g5_post():
            r = ok(_req([_item(unit_price="100.00", discounts=[_disc(pb.FIXED_AMOUNT, ["15"])],
                               tax_rate="20")], calculate_tax=True, discounts_pre_tax=False))
            li = r.items[0]
            return (li.net_payable_with_tax == "105.00" and li.net_payable == "87.50"
                    and li.tax_value == "17.50",
                    f"net={li.net_payable} w/tax={li.net_payable_with_tax} tax={li.tax_value}")
        check("g5_posttax_105_8750", g5_post)

        # G6 — max-discount cap: 50% of 100 = 50, capped at 30 -> net 70, discount 30.
        def g6():
            r = ok(_req([_item(unit_price="100.00",
                               discounts=[_disc(pb.PERCENTAGE, ["50"], maximum_amount="30")])]))
            li = r.items[0]
            return (li.net_payable == "70.00" and li.discount_value.amount == "30.00",
                    f"net={li.net_payable} disc={li.discount_value.amount}")
        check("g6_cap_70", g6)

        # G7 — POA pass-through: flagged, no numeric price.
        def g7_poa():
            r = ok(_req([_item(price_on_application=True, unit_price="99.00")]))
            li = r.items[0]
            return (li.price_on_application and li.net_payable == "",
                    f"poa={li.price_on_application} net='{li.net_payable}'")
        check("g7_poa_passthrough", g7_poa)

        # G7 — invalid inputs -> INVALID_ARGUMENT.
        expect_invalid("g7_negative_quantity", _req([_item(quantity="-1", unit_price="10.00")]))
        expect_invalid("g7_unspecified_strategy",
                       _req([_item(unit_price="100.00", discounts=[_disc(pb.PERCENTAGE, ["10", "10"])])],
                            strategy=pb.DISCOUNT_STRATEGY_UNSPECIFIED))
        expect_invalid("g7_too_many_tiers",
                       _req([_item(unit_price="100.00",
                                   discounts=[_disc(pb.PERCENTAGE, ["1", "2", "3", "4", "5"])])]))

        # Multi-line subtotal roll-up (OQ-3): 10.00 + (20.00 - 10%) = 10.00 + 18.00 = 28.00.
        def rollup():
            r = ok(_req([_item(sku="A", unit_price="10.00"),
                         _item(sku="B", unit_price="20.00",
                               discounts=[_disc(pb.PERCENTAGE, ["10"])])]))
            return (r.subtotal_net_payable == "28.00", f"subtotal={r.subtotal_net_payable}")
        check("subtotal_rollup_28", rollup)
    finally:
        channel.close()
    return suite
