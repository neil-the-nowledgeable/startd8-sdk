"""Round-3 transport-agnostic user-journey spec (M2) — defined ONCE, consumed by both adapters.

The journey is a sequence of **logical steps** with **transport-independent expected outcomes**
(JOURNEY_DESIGN §2.1). Adapter B (direct gRPC, `fleet.adapter_b`) and Adapter A (HTTP, later)
reproduce the SAME steps + payloads; only the *encoding* differs (gRPC message vs form POST). The
expected-outcome of each step is what per-step coverage scores (M3).

This module is pure data + deterministic payload builders — NO transport, NO grpc — so it is the
shared contract both adapters and the scorer import. The step→services map drives M3's per-service
fault attribution (which service a failed step exercises).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

# Whitelisted currency codes the journey's setCurrency step rotates through (JOURNEY_DESIGN §1
# setCurrency task). All must be in the currencyservice's supported set.
CURRENCY_WHITELIST: tuple[str, ...] = ("EUR", "USD", "JPY", "CAD", "GBP", "TRY")

# A known SKU the addToCart/browse steps use (productcatalog must return it). OLJCESPC7Z is the
# canonical OB sample SKU the shipping suite also uses.
CANONICAL_SKU = "OLJCESPC7Z"


@dataclass(frozen=True)
class JourneyStep:
    """One logical step of the canonical journey.

    name:     stable step id (the per-step coverage key).
    intent:   transport-independent description of what the step does.
    outcome:  the transport-independent expected outcome an adapter asserts to score the step.
    services: the backend services this step exercises — the attribution set M3 uses to map a failed
              step to the responsible service (the dialing service is listed first for checkout).
    weight:   the canonical locust task weight (JOURNEY_DESIGN §1) for weighted per-step coverage.
    """

    name: str
    intent: str
    outcome: str
    services: tuple[str, ...]
    weight: int


# The canonical 5-step journey (JOURNEY_DESIGN §2.1), weights from the §1 locust task mix
# (browse 10 dominates; checkout 1 is the rare deep step).
JOURNEY: tuple[JourneyStep, ...] = (
    JourneyStep(
        "browse", "list + view products, prices localized to the active currency",
        "products are returned and a product's price renders in the active currency",
        ("productcatalogservice", "currencyservice"), weight=10),
    JourneyStep(
        "setCurrency", "change the active currency to a whitelisted code",
        "the code is supported and subsequent prices reflect the new currency",
        ("currencyservice",), weight=2),
    JourneyStep(
        "addToCart", "add a known SKU (qty 1..10) to the session cart",
        "the item is present in the cart",
        ("productcatalogservice", "cartservice"), weight=2),
    JourneyStep(
        "viewCart", "read the cart back with totals + a shipping quote",
        "the cart shows the added item and a shipping quote + total compute",
        ("cartservice", "productcatalogservice", "currencyservice", "shippingservice"), weight=3),
    JourneyStep(
        "checkout", "place an order with the canonical payment + address payload",
        "an order id is returned and the 6-dep PlaceOrder orchestration succeeds",
        # dialing service first, then its fan-out — the attribution order M3 reads.
        ("checkoutservice", "productcatalogservice", "cartservice", "currencyservice",
         "shippingservice", "paymentservice", "emailservice"), weight=1),
)

JOURNEY_BY_NAME = {s.name: s for s in JOURNEY}


@dataclass(frozen=True)
class CheckoutPayload:
    """The canonical checkout inputs (JOURNEY_DESIGN §1), reused verbatim by both adapters — Adapter B
    encodes them into a gRPC PlaceOrderRequest, Adapter A into a form POST. The expiry year is forced
    FUTURE so a correct paymentservice does not legitimately decline (which would mis-score payment)."""

    user_id: str = "r3-journey-user"
    user_currency: str = "USD"
    email: str = "r3-journey@example.com"
    street_address: str = "1600 Amphitheatre Pkwy"
    city: str = "Mountain View"
    state: str = "CA"
    country: str = "USA"
    zip_code: int = 94043
    credit_card_number: str = "4111111111111111"  # Luhn-valid Visa test PAN
    credit_card_cvv: int = 672
    credit_card_expiration_month: int = 1
    # filled by canonical_checkout_payload() to a guaranteed-future year (never hardcode-stale).
    credit_card_expiration_year: int = 0
    sku: str = CANONICAL_SKU
    quantity: int = 2


def canonical_checkout_payload(*, now_year: int | None = None) -> CheckoutPayload:
    """The canonical checkout payload with a guaranteed-future card expiry (now_year + 5 by default).
    Deterministic given ``now_year`` (pass it for reproducible records; defaults to the current year)."""
    year = (now_year if now_year is not None else datetime.now().year) + 5
    return CheckoutPayload(credit_card_expiration_year=year)


def services_exercised(steps: Sequence[JourneyStep] = JOURNEY) -> set[str]:
    """The union of backend services the journey exercises (sanity: should equal the contestant fleet
    minus recommendation/ad, which are read-side enrichers not on the critical journey path)."""
    return {svc for step in steps for svc in step.services}
