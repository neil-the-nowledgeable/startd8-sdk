"""Unit tests for the R3-M2 transport-agnostic journey spec (fleet.journey) — NO transport.

Pins the canonical 5-step journey (JOURNEY_DESIGN §2.1), its per-step service-attribution sets, the
locust task weights (§1), and the canonical checkout payload's guaranteed-future card expiry.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.fleet import journey as J

pytestmark = pytest.mark.unit


def test_five_steps_in_canonical_order():
    assert [s.name for s in J.JOURNEY] == ["browse", "setCurrency", "addToCart", "viewCart", "checkout"]


def test_weights_match_locust_mix():
    # JOURNEY_DESIGN §1: browse 10 dominates; viewCart 3; setCurrency/addToCart 2; checkout 1.
    w = {s.name: s.weight for s in J.JOURNEY}
    assert w == {"browse": 10, "setCurrency": 2, "addToCart": 2, "viewCart": 3, "checkout": 1}
    assert max(w, key=w.get) == "browse"  # the dominant, discriminating read step


def test_checkout_is_the_six_dep_fanout():
    checkout = J.JOURNEY_BY_NAME["checkout"]
    # dialing service first, then exactly the 6 PlaceOrder deps.
    assert checkout.services[0] == "checkoutservice"
    assert set(checkout.services[1:]) == {
        "productcatalogservice", "cartservice", "currencyservice",
        "shippingservice", "paymentservice", "emailservice",
    }


def test_step_service_attribution_sets():
    by = J.JOURNEY_BY_NAME
    assert by["setCurrency"].services == ("currencyservice",)
    assert set(by["addToCart"].services) == {"productcatalogservice", "cartservice"}
    assert "shippingservice" in by["viewCart"].services  # viewCart computes a shipping quote


def test_currency_whitelist_is_iso_codes():
    assert "USD" in J.CURRENCY_WHITELIST  # identity-safe code is present
    assert all(len(c) == 3 and c.isalpha() and c.isupper() for c in J.CURRENCY_WHITELIST)


def test_canonical_payload_expiry_is_future():
    p = J.canonical_checkout_payload(now_year=2026)
    assert p.credit_card_expiration_year == 2031  # now_year + 5, guaranteed future
    assert p.credit_card_number == "4111111111111111"  # Luhn-valid (payment must accept)
    assert p.quantity == 2 and p.sku == J.CANONICAL_SKU


def test_services_exercised_excludes_enrichers():
    svc = J.services_exercised()
    # the journey's critical path is the 6 checkout deps + checkout; recommendation/ad are read-side
    # enrichers NOT on any step's attribution set.
    assert "recommendationservice" not in svc and "adservice" not in svc
    assert {"checkoutservice", "paymentservice", "emailservice", "shippingservice"} <= svc
