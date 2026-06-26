"""Round-3 frontend journey-facing HTTP contract + gate spec + bonus model (M4/M5 foundation).

The single executable encoding of FRONTEND_OPENAPI_CONTRACT.md: the journey-critical HTTP routes both
frontends (the contestant-generated one and the canonical upstream `src/frontend`) MUST serve, the
route→backend gRPC fan-out (§3), the health/contract **gate** (§4) the harness uses to decide
use-generated vs substitute-canonical, and the M5 **bonus** model (additive, capped — never a
backend-rank-flipper). Pure data — the gate runner, Adapter A (HTTP driver), and the bonus scorer all
import this so the contract lives in ONE place (the substitution seam).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import journey as J


@dataclass(frozen=True)
class Route:
    """One journey-critical HTTP route (FRONTEND_OPENAPI_CONTRACT §1)."""
    method: str
    path: str                       # may contain a `{id}` placeholder
    form_fields: tuple[str, ...]    # required form fields for a well-formed request
    ok_status: int                  # acceptable status for a well-formed request (200 GET/checkout, 302 POST)
    bad_status: int | None          # status a MALFORMED request must yield (4xx); None when N/A
    fanout: tuple[str, ...]         # backend services this route fans out to (§3) — the bonus-fidelity set
    handler: str                    # the upstream handler name (reference)


# The 6 gated journey routes (§1 rows 1–6). Status expectations: GETs + checkout → 200; the
# cart/currency POSTs → 302 redirect; malformed add/checkout → 422 (not 500/200).
JOURNEY_ROUTES: tuple[Route, ...] = (
    Route("GET", "/", (), 200, None,
          ("currencyservice", "productcatalogservice", "cartservice"), "homeHandler"),
    Route("GET", "/product/{id}", (), 200, 400,
          ("productcatalogservice", "currencyservice", "cartservice", "recommendationservice"),
          "productHandler"),
    Route("POST", "/setCurrency", ("currency_code",), 302, None,
          (), "setCurrencyHandler"),
    Route("POST", "/cart", ("product_id", "quantity"), 302, 422,
          ("productcatalogservice", "cartservice"), "addToCartHandler"),
    Route("GET", "/cart", (), 200, None,
          ("currencyservice", "cartservice", "recommendationservice", "shippingservice",
           "productcatalogservice"), "viewCartHandler"),
    Route("POST", "/cart/checkout", (
        "email", "street_address", "zip_code", "city", "state", "country",
        "credit_card_number", "credit_card_expiration_month", "credit_card_expiration_year",
        "credit_card_cvv"), 200, 422,
          ("checkoutservice", "currencyservice", "recommendationservice"), "placeOrderHandler"),
)

# Liveness probe (canonical exposes GET /_healthz → 200 "ok"; a generated frontend may fall back to GET /).
HEALTH_ROUTE = Route("GET", "/_healthz", (), 200, None, (), "health")

ROUTE_BY_KEY = {(r.method, r.path): r for r in JOURNEY_ROUTES}

# Canonical cookies the journey threads (§1): a generated frontend SHOULD reproduce these names.
SESSION_COOKIE = "shop_session-id"
CURRENCY_COOKIE = "shop_currency"


class GateStage(Enum):
    """The §4 gate stages, in order. BOOT/ROUTES/JOURNEY are BLOCKING (all must pass to use the
    generated frontend); ORCHESTRATION is advisory → feeds the M5 bonus, never blocks the gate."""
    BOOT = "boot"                    # process binds + GET /_healthz (or /) → 200 within the deadline
    ROUTES = "routes"               # each gated route returns an acceptable status; malformed → 4xx
    JOURNEY = "journey"             # DECISIVE: full one-session journey → order-confirmation w/ order id
    ORCHESTRATION = "orchestration"  # advisory: routes fanned out to the expected backends (§3)


BLOCKING_STAGES: tuple[GateStage, ...] = (GateStage.BOOT, GateStage.ROUTES, GateStage.JOURNEY)

# The stateful journey sequence the gate's decisive stage (and Adapter A) drive in ONE session.
JOURNEY_SEQUENCE: tuple[tuple[str, str], ...] = (
    ("GET", "/"), ("POST", "/setCurrency"), ("GET", "/product/{id}"),
    ("POST", "/cart"), ("GET", "/cart"), ("POST", "/cart/checkout"),
)


@dataclass(frozen=True)
class FrontendVerdict:
    """The gate outcome → which frontend Adapter A runs over (the substitution seam)."""
    passed: bool                     # all BLOCKING stages green
    failing_stage: str | None        # the first blocking stage that failed (None on PASS)
    reason: str = ""
    mounted: str = "generated"       # "generated" (PASS) | "canonical-substituted" (FAIL)


def make_verdict(stage_results: dict[GateStage, bool]) -> FrontendVerdict:
    """Resolve the gate: PASS iff every BLOCKING stage passed → mount generated; else substitute the
    canonical upstream frontend (backend scoring is unaffected either way), bonus = 0."""
    for stage in BLOCKING_STAGES:
        if not stage_results.get(stage, False):
            return FrontendVerdict(False, stage.value,
                                   reason=f"gate failed at {stage.value}",
                                   mounted="canonical-substituted")
    return FrontendVerdict(True, None, reason="all blocking stages passed", mounted="generated")


# --- M5 bonus model -------------------------------------------------------------------------------
# The frontend bonus is ADDITIVE and CAPPED so it stays a tie-break/annotation and NEVER flips the
# backend ranking (OQ-J3): a brilliant-frontend/weak-backend model can't outrank a strong-backend one.
FRONTEND_BONUS_CAP = 0.10


def frontend_bonus(verdict: FrontendVerdict, orchestration_fidelity: float) -> float:
    """Bonus = fidelity × cap, but ONLY when the gate passed (generated frontend mounted). A
    substituted/failed frontend earns 0 (the bonus rewards the contestant's own frontend code).
    ``orchestration_fidelity`` ∈ [0,1] = fraction of the §3 expected fan-out the routes reproduced."""
    if not verdict.passed:
        return 0.0
    return max(0.0, min(1.0, orchestration_fidelity)) * FRONTEND_BONUS_CAP


def checkout_form(payload: J.CheckoutPayload | None = None, *, now_year: int | None = None) -> dict[str, str]:
    """The §2 10-field checkout form body (POST /cart/checkout), encoded from the canonical journey
    payload (reused verbatim — only the encoding differs from Adapter B's gRPC PlaceOrderRequest)."""
    p = payload or J.canonical_checkout_payload(now_year=now_year)
    return {
        "email": p.email, "street_address": p.street_address, "zip_code": str(p.zip_code),
        "city": p.city, "state": p.state, "country": p.country,
        "credit_card_number": p.credit_card_number,
        "credit_card_expiration_month": str(p.credit_card_expiration_month),
        "credit_card_expiration_year": str(p.credit_card_expiration_year),
        "credit_card_cvv": str(p.credit_card_cvv),
    }
