"""Validate the pricing ground-truth suite against a correct reference server (S7 / FR-9),
and guard the FR-14 invariant that Online Boutique proto provisioning is unchanged.

The reference servicer implements the canonical ComputeBasket algorithm with ``decimal.Decimal``
(exact). If the SDK-authored suite (``run_pricing_suite``) does not reach coverage 1.00 against a
*correct* server, the suite's expected values are internally inconsistent — the test fails loudly
with the offending checks. The benchmarked model writes its own server; this only proves the
ground truth is self-consistent.
"""
from __future__ import annotations

import socket
from concurrent import futures
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral import pricing_pb2 as pb
from startd8.benchmark_matrix.behavioral import pricing_pb2_grpc
from startd8.benchmark_matrix.behavioral.pricing_suite import run_pricing_suite


def _q(scale: int) -> Decimal:
    return Decimal(1).scaleb(-scale)


def _round(d: Decimal, scale: int, mode) -> Decimal:
    rounding = ROUND_HALF_EVEN if mode == pb.HALF_EVEN else ROUND_HALF_UP
    return d.quantize(_q(scale), rounding=rounding)


def _fmt(d: Decimal, scale: int) -> str:
    return str(d.quantize(_q(scale)))


class _ReferencePricing(pricing_pb2_grpc.PricingServiceServicer):
    """A correct ComputeBasket implementation — the oracle the suite is validated against."""

    def ComputeBasket(self, request, context):
        strategy = request.strategy
        scale = request.currency.scale or 2
        mode = request.currency.rounding

        if any(li.discounts for li in request.items) and strategy == pb.DISCOUNT_STRATEGY_UNSPECIFIED:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "strategy required when discounts present")

        resp = pb.ComputeBasketResponse()
        subtotal_net = Decimal(0)
        subtotal_net_tax = Decimal(0)

        for li in request.items:
            out = pb.PricedLineItem(sku=li.sku)
            if li.price_on_application:
                out.price_on_application = True
                resp.items.append(out)
                continue

            try:
                qty = Decimal(li.quantity)
                unit = Decimal(li.unit_price)
            except InvalidOperation:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "malformed decimal")
            if qty <= 0 or unit < 0:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "non-positive quantity or negative price")

            base_unit = unit
            offer = Decimal(li.offer_unit_price) if li.offer_unit_price else None
            if offer is not None and offer > 0 and offer < unit:
                base_unit = offer
            line_base = base_unit * qty

            for d in li.discounts:
                if not (1 <= len(d.tier_factors) <= 4):
                    context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tiers must number 1..4")

            def apply_discounts(base: Decimal) -> Decimal:
                running = base
                for d in li.discounts:
                    if d.kind == pb.PERCENTAGE:
                        tiers = [Decimal(t) for t in d.tier_factors]
                        if strategy == pb.CHAIN:
                            dd = running
                            for t in tiers:
                                dd = dd - dd * (t / Decimal(100))
                        else:  # ADDITION (UNSPECIFIED already rejected above)
                            total = sum(tiers, Decimal(0))
                            dd = running * (Decimal(1) - total / Decimal(100))
                        amt = running - dd
                    elif d.kind == pb.FIXED_AMOUNT:
                        amt = Decimal(d.tier_factors[0])
                        if amt > running:
                            amt = running
                    else:
                        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "discount kind required")
                    if d.maximum_amount:
                        cap = Decimal(d.maximum_amount)
                        if amt > cap:
                            amt = cap
                    running = running - amt
                return running

            rate = Decimal(li.tax_rate) if li.tax_rate else Decimal(0)
            if not request.calculate_tax:
                discounted = apply_discounts(line_base)
                net = _round(discounted, scale, mode)
                net_tax = net
                tax = Decimal(0)
                disc_base, disc_after = line_base, discounted
            elif request.discounts_pre_tax:
                discounted = apply_discounts(line_base)
                net = _round(discounted, scale, mode)
                tax = _round(net * rate / Decimal(100), scale, mode)
                net_tax = net + tax
                disc_base, disc_after = line_base, discounted
            else:
                gross_base = line_base * (Decimal(1) + rate / Decimal(100))
                discounted_gross = apply_discounts(gross_base)
                net_tax = _round(discounted_gross, scale, mode)
                net = _round(net_tax / (Decimal(1) + rate / Decimal(100)), scale, mode)
                tax = net_tax - net
                disc_base, disc_after = gross_base, discounted_gross

            out.unit_price = _fmt(unit, scale)
            if base_unit != unit:
                out.offer_unit_price = _fmt(base_unit, scale)
            out.net_payable = _fmt(net, scale)
            out.net_payable_with_tax = _fmt(net_tax, scale)
            out.tax_value = _fmt(tax, scale)
            out.discount_value.amount = _fmt(disc_base - disc_after, scale)
            resp.items.append(out)

            subtotal_net += net
            subtotal_net_tax += net_tax

        resp.subtotal_net_payable = _fmt(subtotal_net, scale)
        resp.subtotal_net_payable_with_tax = _fmt(subtotal_net_tax, scale)
        return resp


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def reference_server():
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pricing_pb2_grpc.add_PricingServiceServicer_to_server(_ReferencePricing(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    try:
        yield port
    finally:
        server.stop(grace=None)


def test_suite_reaches_full_coverage_against_reference(reference_server):
    """The ground truth is self-consistent: a correct server passes every check (FR-9)."""
    result = run_pricing_suite(reference_server)
    assert result.connect_error == "", result.connect_error
    failing = [(r.name, r.detail) for r in result.results if not r.passed]
    assert result.coverage == 1.0, f"failing checks: {failing}"
    assert len(result.results) == 16  # G1..G7 + rollup



class _BrokenNoCapPricing(_ReferencePricing):
    """Correct in every respect EXCEPT it ignores a discount's ``maximum_amount`` cap — a realistic
    single-bug model error (forgetting one clamp). Used to prove the suite discriminates per-RPC."""

    def ComputeBasket(self, request, context):
        for li in request.items:        # strip the cap so apply_discounts never clamps
            for d in li.discounts:
                d.maximum_amount = ""
        return super().ComputeBasket(request, context)


@pytest.fixture()
def broken_nocap_server():
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    pricing_pb2_grpc.add_PricingServiceServicer_to_server(_BrokenNoCapPricing(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    try:
        yield port
    finally:
        server.stop(grace=None)


def test_suite_fails_exactly_the_capped_discount_check(broken_nocap_server):
    """R2-S3: a single-bug server (ignores the discount cap) must fail EXACTLY ``g6_cap_70`` with the
    wrong net — every other check still passes. This proves the suite discriminates per-RPC for a
    specific reason, not merely on a generic crash/timeout that would fail everything at once."""
    result = run_pricing_suite(broken_nocap_server)
    assert result.connect_error == "", result.connect_error
    by_name = {r.name: r for r in result.results}
    # exactly the capped-discount check fails, and it fails for the RIGHT reason (uncapped 50% of 100
    # = 50 → net 50.00, not the capped 70.00) — not a connect error or a blanket failure.
    assert by_name["g6_cap_70"].passed is False
    assert "50.00" in by_name["g6_cap_70"].detail, by_name["g6_cap_70"].detail
    others = [r for r in result.results if r.name != "g6_cap_70"]
    assert all(r.passed for r in others), [(r.name, r.detail) for r in others if not r.passed]
    assert 0.0 < result.coverage < 1.0   # discriminates: not a total wipeout, not a false pass


def test_fr14_proto_mapping_keeps_ob_on_demo_proto():
    """FR-14: OB services resolve to demo.proto (default), only pricingservice overrides."""
    default = (execute._PROTO, "demo.proto")
    for ob in ("paymentservice", "currencyservice", "shippingservice", "adservice", "checkoutservice"):
        assert execute._PROTO_BY_SERVICE.get(ob, default) == default
    assert execute._PROTO_BY_SERVICE["pricingservice"] == (execute._PRICING_PROTO, "pricing.proto")


@pytest.mark.skipif(not (execute._NODE_RUNTIME / "node_modules").is_dir(),
                    reason="node runtime not vendored — run node_runtime/vendor.sh")
def test_fr14_prepare_node_workdir_writes_named_proto(tmp_path):
    """FR-14: the provisioned proto file honors proto_name; default stays demo.proto."""
    execute.prepare_node_workdir(tmp_path / "ob", ["src/paymentservice/server.js"])
    assert (tmp_path / "ob" / "demo.proto").exists()
    assert not (tmp_path / "ob" / "pricing.proto").exists()

    execute.prepare_node_workdir(tmp_path / "px", ["src/pricingservice/server.js"],
                                 proto_src=execute._PRICING_PROTO, proto_name="pricing.proto")
    assert (tmp_path / "px" / "pricing.proto").exists()
    assert not (tmp_path / "px" / "demo.proto").exists()
