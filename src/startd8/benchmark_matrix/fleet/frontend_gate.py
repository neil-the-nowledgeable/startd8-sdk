"""Round-3 frontend health/contract GATE + the HTTP journey core (M4).

Runs a frontend (the contestant-generated one or the canonical upstream) through the
FRONTEND_OPENAPI_CONTRACT §4 gate stages against a KNOWN-GOOD backend fleet, then resolves
``make_verdict`` → use-generated vs substitute-canonical. The decisive stage is BEHAVIORAL (a real
stateful one-session HTTP journey that must yield a real order id) — route-presence saturates, only
the executed journey discriminates (lessons #5/#28; lean strict, R2/OQ-J1).

``run_journey_http`` is the stateful one-session driver shared by the gate's JOURNEY stage AND
Adapter A (the contract is the seam — the same journey, HTTP-encoded; mirror of Adapter B). Pure HTTP
over httpx — testable against any frontend reachable at a base URL (a live container OR an in-process
mock), no docker.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import httpx

from . import frontend_contract as FC
from . import journey as J

# the rendered order id on the confirmation page (a real, non-empty token — not a placeholder/blank).
# Require the label-colon form ("Order ID: <token>", the canonical OB confirmation phrasing) so the
# `id="order-id"` HTML attribute and the word "Order" don't false-match; lean strict (a confirmation
# that doesn't clearly render an order id falls to canonical, which is the safe direction).
_ORDER_ID_RE = re.compile(r"order[\s_\-]*id\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9\-_]{2,})", re.IGNORECASE)


def extract_order_id(html: str) -> str:
    """The order id rendered on a confirmation page, or '' if absent/blank — the decisive signal."""
    m = _ORDER_ID_RE.search(html or "")
    return m.group(1) if m else ""


@dataclass
class JourneyOutcome:
    completed: bool                      # full journey reached a confirmation with a real order id
    order_id: str
    signals: dict[str, bool] = field(default_factory=dict)  # per-step observability (orchestration fidelity)

    @property
    def fidelity(self) -> float:
        return (sum(self.signals.values()) / len(self.signals)) if self.signals else 0.0


def run_journey_http(client: httpx.Client, *, now_year: int | None = None) -> JourneyOutcome:
    """Drive the canonical journey over HTTP in ONE session (the gate's decisive stage + Adapter A):
    GET / → POST /setCurrency → GET /product/{id} → POST /cart → GET /cart → POST /cart/checkout.
    The session cookie threads via the client's cookie jar. Scores each step's observable outcome."""
    sku = J.CANONICAL_SKU
    sig: dict[str, bool] = {}

    home = _safe(client, "GET", "/")
    sig["browse"] = home.status_code == 200 and "product" in home.text.lower()

    target = next((c for c in J.CURRENCY_WHITELIST if c != "USD"), "EUR")
    sc = _safe(client, "POST", "/setCurrency", data={"currency_code": target})
    sig["setCurrency"] = sc.status_code in (302, 303)

    prod = _safe(client, "GET", f"/product/{sku}")
    sig["product"] = prod.status_code == 200

    add = _safe(client, "POST", "/cart", data={"product_id": sku, "quantity": "2"})
    sig["addToCart"] = add.status_code in (302, 303)

    cart = _safe(client, "GET", "/cart")
    sig["viewCart"] = cart.status_code == 200 and sku in cart.text

    co = _safe(client, "POST", "/cart/checkout", data=FC.checkout_form(now_year=now_year))
    oid = extract_order_id(co.text)
    sig["checkout"] = co.status_code == 200 and bool(oid)

    return JourneyOutcome(completed=sig["checkout"], order_id=oid, signals=sig)


@dataclass
class GateResult:
    verdict: FC.FrontendVerdict
    stage_results: dict[FC.GateStage, bool]
    orchestration_fidelity: float        # advisory → the M5 bonus fidelity
    order_id: str = ""
    detail: str = ""


def _safe(client: httpx.Client, method: str, path: str, **kw) -> httpx.Response:
    try:
        return client.request(method, path, **kw)
    except httpx.HTTPError as e:  # a transport error reads as an empty 599 (stage will fail)
        return httpx.Response(599, text=f"transport error: {e}")


def _stage_boot(client: httpx.Client, *, startup_timeout: float) -> bool:
    """process binds + GET /_healthz (or /) → 200 **within the startup deadline** (§4 stage 1). The
    gate owns the readiness wait — it boots a freshly-started frontend, so a single check would flake
    on a slow boot; poll until ready or the deadline (a dead frontend fails fast: each GET errors
    immediately)."""
    deadline = time.monotonic() + max(0.0, startup_timeout)
    while True:
        if _safe(client, "GET", FC.HEALTH_ROUTE.path).status_code == 200:
            return True
        if _safe(client, "GET", "/").status_code == 200:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def _stage_routes(client: httpx.Client) -> bool:
    """each gated route returns an acceptable status for a well-formed request, and 4xx for a
    malformed add/checkout (a 404/wrong-method/200-on-garbage → FAIL)."""
    sku = J.CANONICAL_SKU
    ok = (
        _safe(client, "GET", "/").status_code == 200
        and _safe(client, "GET", f"/product/{sku}").status_code == 200
        and _safe(client, "POST", "/setCurrency", data={"currency_code": "EUR"}).status_code in (302, 303)
        and _safe(client, "POST", "/cart", data={"product_id": sku, "quantity": "1"}).status_code in (302, 303)
        and _safe(client, "GET", "/cart").status_code == 200
    )
    # malformed must be rejected (4xx), not 200/500
    ok = ok and 400 <= _safe(client, "POST", "/cart", data={}).status_code < 500
    ok = ok and 400 <= _safe(client, "POST", "/cart/checkout", data={}).status_code < 500
    ok = ok and _safe(client, "GET", "/product/").status_code == 400  # empty id → 400
    return ok


def run_gate(base_url: str, *, timeout: float = 10.0, startup_timeout: float = 30.0,
             now_year: int | None = None) -> GateResult:
    """Run the §4 gate against the frontend at ``base_url`` (wired to a known-good backend fleet) and
    resolve the substitution verdict. BOOT→ROUTES→JOURNEY are blocking; ORCHESTRATION is advisory.
    ``startup_timeout`` bounds the BOOT readiness poll (the gate owns the boot wait); ``timeout`` is the
    per-request deadline."""
    results: dict[FC.GateStage, bool] = {}
    fidelity = 0.0
    order_id = ""
    with httpx.Client(base_url=base_url, follow_redirects=False, timeout=timeout) as client:
        results[FC.GateStage.BOOT] = _stage_boot(client, startup_timeout=startup_timeout)
        results[FC.GateStage.ROUTES] = _stage_routes(client) if results[FC.GateStage.BOOT] else False
        if results[FC.GateStage.ROUTES]:
            # a FRESH session for the stateful journey (the route checks above mutated the cookie jar)
            with httpx.Client(base_url=base_url, follow_redirects=False, timeout=timeout) as jc:
                jo = run_journey_http(jc, now_year=now_year)
            results[FC.GateStage.JOURNEY] = jo.completed
            fidelity = jo.fidelity
            order_id = jo.order_id
        else:
            results[FC.GateStage.JOURNEY] = False
        # ORCHESTRATION (advisory): the journey fanned out to the expected backends (fidelity proxy).
        results[FC.GateStage.ORCHESTRATION] = fidelity >= 1.0

    verdict = FC.make_verdict(results)
    detail = (f"order_id={order_id!r} fidelity={fidelity:.2f}" if verdict.passed
              else f"{verdict.reason}; fidelity={fidelity:.2f}")
    return GateResult(verdict=verdict, stage_results=results, orchestration_fidelity=fidelity,
                      order_id=order_id, detail=detail)
