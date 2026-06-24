# Round 3 — Frontend Journey-Facing HTTP Contract (the substitution seam)

**Version:** 0.1 (design/contract — NO implementation)
**Date:** 2026-06-24
**Status:** Contract spec. The deliverable is the journey-facing HTTP contract that **BOTH** the
contestant-generated frontend and the canonical upstream frontend satisfy, plus the **health/contract
gate** the harness uses to decide *use-generated* vs *substitute-canonical*. This contract is the
**substitution seam**: because both frontends honor it, the Adapter-A HTTP journey driver is
frontend-agnostic.
**Owner SDK area:** Round-3 fleet orchestrator + journey driver (Adapter A) + the frontend gate.
**Parents:**
- `docs/design/round3-full-app/JOURNEY_DESIGN.md` (v0.2 — the transport-agnostic journey + bonus model)
- `docs/design/round3-full-app/FRONTEND_LANE_SCOPING.md` (the generated-frontend seed/lane)
**Canonical reference (derived, not invented):**
- `~/Documents/dev/micro-service-demo/microservices-demo-latest/src/frontend/main.go` (router setup),
  `handlers.go` (route handlers + form fields + response/redirect shapes), `rpc.go` (the gRPC fan-out
  each handler makes).
- `.../src/loadgenerator/locustfile.py` (the journey task set + exact form payloads + product fixtures).

> **Shape note (load-bearing):** the canonical frontend is an **HTML / form-encoded** app, **not** a
> JSON REST API. Endpoints accept `application/x-www-form-urlencoded` bodies and respond with **HTML
> pages** (200) or **302/Found redirects** (`Location:` header). Therefore this contract describes
> **form endpoints + page/redirect responses**, and the gate is **behavioral** ("routes respond + the
> journey completes end-to-end"), NOT a strict JSON-schema match. A generated frontend may use any
> language/framework so long as it reproduces these routes, form fields, fan-out, and response *kinds*.

---

## 1. The journey-facing route contract (what both frontends MUST serve)

Derived from `main.go` router (lines 150–164) + `handlers.go` + `rpc.go`. Only the **journey-critical**
routes are part of the gate; non-journey routes (`/assistant`, `/bot`, `/product-meta/{ids}`, `/logout`,
`/robots.txt`, profiling/branding env behavior) are **optional** for a generated frontend and are NOT
gated.

| # | Method | Path | Request (form fields / path params) | Success response | Notes |
|---|---|---|---|---|---|
| 1 | GET | `/` | — (currency via `shop_currency` cookie) | **200** HTML home (product grid, prices in active currency) | sets `shop_session-id` cookie on first hit |
| 2 | GET | `/product/{id}` | path `id` ∈ 9-SKU fixture set | **200** HTML product page (localized price, recommendations) | `id` empty → 400 |
| 3 | POST | `/setCurrency` | `currency_code` ∈ {USD,EUR,CAD,JPY,GBP,TRY} | **302** → `Referer` (or `/`) | sets `shop_currency` cookie (MaxAge 48h) |
| 4 | POST | `/cart` | `product_id`, `quantity` (1..10) | **302** → `/cart` | invalid payload → **422** |
| 5 | GET | `/cart` | — | **200** HTML cart (items, shipping quote, total) | empty cart still 200 |
| 6 | POST | `/cart/checkout` | the **10-field checkout payload** (§2) | **200** HTML order-confirmation (order id rendered) | invalid payload → **422**; backend failure → 500 |
| (aux) | POST | `/cart/empty` | — | **302** → `/` | defined upstream, **not** in the active weighted journey |
| (health) | GET | `/_healthz` | — | **200** body `ok` | liveness probe (canonical exposes this) |

**Session + currency cookies** (canonical names — a generated frontend SHOULD reproduce, the gate
checks behavior not cookie names):
- `shop_session-id` — set on first request via the `ensureSessionID` middleware; identifies the cart
  owner (passed as `UserId` to cart/checkout). The journey is **stateful**: add-to-cart then view-cart
  then checkout must share a session.
- `shop_currency` — set by `/setCurrency`; read by every price-rendering handler; default `USD`.

---

## 2. The canonical checkout payload (`POST /cart/checkout`)

From `locustfile.py::checkout()` (the request) and `handlers.go::placeOrderHandler` (the fields it
reads via `r.FormValue`). All 10 fields are form-encoded; the journey driver and a generated frontend's
form MUST use these exact field names:

```
email                          = <email>
street_address                 = <string>
zip_code                       = <int>            # ParseInt base10
city                           = <string>
state                          = <string>         # state abbr
country                        = <string>
credit_card_number             = <visa number>
credit_card_expiration_month   = <int 1..12>
credit_card_expiration_year    = <int, FUTURE>    # locust uses now().year+1 floor
credit_card_cvv                = <string "100".."999">
```

The frontend maps these into a `checkout.PlaceOrder` gRPC request: `Email`, `CreditCard{Number, ExpMonth,
ExpYear, Cvv}`, `UserId = session-id`, `UserCurrency = active currency`, `Address{StreetAddress, City,
State, ZipCode(int), Country}`. A success renders the order-confirmation page with the returned
`order_id` and `total_paid`. **Expiration year must be future** — a past expiry trips a legitimate
payment decline and would mis-score the checkout step (a contract-faithfulness requirement, not a bug).

---

## 3. The backend-orchestration map (route → gRPC fan-out)

**This is the spec a generated frontend must implement.** Derived from `handlers.go` + `rpc.go`. Each
journey route fans out to specific backend gRPC calls; a generated frontend earns its bonus by
reproducing this orchestration (and the gate's checkout test exercises the deepest path).

| Route | gRPC fan-out (service.Method) | Source |
|---|---|---|
| `GET /` | Currency.GetSupportedCurrencies · ProductCatalog.ListProducts · Currency.Convert (per product) · Cart.GetCart · Ad.GetAds | `homeHandler` |
| `GET /product/{id}` | ProductCatalog.GetProduct · Currency.GetSupportedCurrencies · Cart.GetCart · Currency.Convert · Recommendation.ListRecommendations (+ProductCatalog.GetProduct per rec) · Ad.GetAds | `productHandler` |
| `POST /setCurrency` | — (sets cookie only; no gRPC) | `setCurrencyHandler` |
| `POST /cart` (add) | ProductCatalog.GetProduct · Cart.AddItem | `addToCartHandler` |
| `GET /cart` | Currency.GetSupportedCurrencies · Cart.GetCart · Recommendation.ListRecommendations · Shipping.GetQuote · (per item) ProductCatalog.GetProduct + Currency.Convert | `viewCartHandler` |
| `POST /cart/checkout` | **Checkout.PlaceOrder** (which itself fans out to productcatalog+cart+currency+shipping+payment+email) · Recommendation.ListRecommendations · Currency.GetSupportedCurrencies | `placeOrderHandler` |
| `POST /cart/empty` | Cart.EmptyCart | `emptyCartHandler` |

**Backend deps the frontend dials** (from `main.go` `mustMapEnv` + `mustConnGRPC`, the 7 journey-relevant
ones; `shoppingassistant` is non-journey and optional): productcatalog, currency, cart, recommendation,
shipping, checkout, ad. Note the frontend does **not** dial payment/email directly — those are reached
*transitively* through `Checkout.PlaceOrder` (the 6-dep checkout orchestration). See
`FRONTEND_LANE_SCOPING.md` for the `*_SERVICE_ADDR` env names.

**Resilience faithfulness (canonical behaviors a faithful frontend mirrors):** recommendations and ads
are **non-critical** — the canonical handlers log-and-continue on their failure (a missing rec/ad does
NOT fail the page). Currency conversion, catalog, cart, shipping, and checkout failures **do** render an
error page (500). A generated frontend that hard-fails the page on a missing ad is *less* faithful but
need not fail the gate (the gate is journey-completion, and ads aren't on the journey's success path).

---

## 4. The health / contract gate (use-generated vs substitute-canonical)

The harness runs the generated frontend through this gate **before** Adapter A uses it. The gate is
**behavioral** (the app is HTML/form, not JSON — there is no strict schema to diff). It runs the
generated frontend wired to a **known-good (canonical) backend fleet** so the gate measures the
frontend in isolation (a backend bug can't fail the frontend's gate).

**Gate stages (all must pass to use the generated frontend):**

1. **Boot / liveness** — the frontend process starts, binds its port, and `GET /_healthz` (or `GET /`)
   returns 200 within the startup deadline. Missing/crash-loop → FAIL.
2. **Route presence + method** — each gated journey route (§1 rows 1–6) responds with an *acceptable*
   status for a well-formed request (200 for GETs and checkout, 302 for the cart/currency POSTs), and
   rejects a malformed checkout/add payload with 4xx (not 500/200). A route that 404s or wrong-methods →
   FAIL.
3. **Stateful journey completion (the decisive stage)** — the harness drives the **full journey in one
   session** against the known-good backends:
   `GET /` → `POST /setCurrency` → `GET /product/{id}` → `POST /cart` (add) → `GET /cart` (item present,
   total computes) → `POST /cart/checkout` (the §2 payload) → **order-confirmation page with an order
   id**. The session cookie must thread through. If checkout does not yield a confirmed order id, or the
   cart doesn't reflect the add, → FAIL.
4. **Orchestration sanity (advisory, not blocking the gate)** — observe (via the known-good fleet's call
   counters) that the journey routes actually fanned out to the expected backends (§3). Used for the
   **frontend service bonus score** (`FRONTEND_LANE_SCOPING.md` §scoring), not as a hard gate stage — a
   frontend that completes the journey but skips a non-critical call (ad/rec) still passes the gate, it
   just scores less bonus.

**Gate verdict → action:**
- **PASS** (stages 1–3 green) → mount the generated frontend for Adapter A; record `frontend=generated`,
  award frontend bonus per orchestration fidelity (stage 4).
- **FAIL** (any of 1–3) → **substitute the canonical upstream frontend** (model-invariant, wired to the
  contestant backends via `*_SERVICE_ADDR`); record `frontend=canonical-substituted` + the failing
  stage + reason; Adapter A runs over the canonical frontend; frontend bonus = 0; **backend scoring is
  unaffected** (it runs over the contestant backends regardless of which frontend is mounted).

**Robustness requirement (OQ-J1):** the gate MUST be strict enough that a *subtly-broken* generated
frontend — one that boots and serves routes but mis-orchestrates (e.g., adds to cart but checkout
silently drops items, or renders a confirmation page **without** a real order id) — **fails stage 3 and
falls to canonical**, rather than passing and producing misleading Adapter-A journey results. The
stateful end-to-end checkout against known-good backends is what catches "looks right but is wrong."
The gate must **fail to canonical cleanly** (no partial-mount, no half-substituted fleet).

---

## 5. Why this contract is the substitution seam

Both the generated and the canonical frontend satisfy §1–§3. So the Adapter-A driver — which only knows
the journey-facing routes + the §2 payload — runs **byte-identically over either frontend**. The harness
swaps the upstream binary in on gate failure with no change to the journey driver, the backend fleet, or
the backend scoring. The contract is the single interface that makes "frontend is a bonus, never a
blocker" mechanically true: a model's frontend is judged against this contract, and the *same* contract
is what the canonical fallback already satisfies, so evaluation proceeds irrespective of the generated
frontend's fate.
