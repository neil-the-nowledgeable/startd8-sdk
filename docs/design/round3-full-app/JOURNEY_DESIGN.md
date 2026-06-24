# Round 3 — Journey & Topology Design

**Version:** 0.2 (design — NO implementation)
**Date:** 2026-06-24
**Status:** Design/decision doc. Deliverables: the canonical user-journey set (source of truth for
Round-3 cross-service scoring), the **transport-agnostic journey + bonus-frontend model** (the journey
is defined ONCE and run over two adapters; the frontend is a scored BONUS service that is substituted by
the canonical upstream frontend on gate failure so evaluation never stalls), and the canonical
service→port + dependency-env topology cross-checked against the startup contracts.

**v0.2 supersedes v0.1's §2 fork.** v0.1 framed an either/or "Option A vs Option B" decision and
*rejected* A1 (contestant-generated frontend) as all-or-nothing. The settled design is **unified, not a
fork**: the journey is transport-agnostic and BOTH adapters run; the generated frontend (old A1) is now
a **first-class BONUS** that can never zero a model, because a health/contract-gate failure cleanly
**substitutes the canonical frontend** (old A2) and the HTTP journey + all backend scoring continue. So
A1 is no longer rejected — it is pure upside, with A2 as its always-available fallback. The companion
spec is `FRONTEND_OPENAPI_CONTRACT.md` (the substitution seam) and `FRONTEND_LANE_SCOPING.md` (the
generated-frontend seed/lane).
**Owner SDK area:** `startd8.benchmark_matrix.behavioral` (suites + startup contracts) + the Round-3
fleet orchestrator + journey driver.
**Parents:**
- `docs/design/round3-full-app/REQUIREMENTS.md` (Round 3 system round; v0.2)
- `docs/design/round3-full-app/CONTAINERIZATION_SCOPING.md` (the fleet the journey runs against)
- `docs/design/round3-full-app/COMPOSE_FLEET_PROTOTYPE.md` (validated compose-fleet prototype)
**Canonical reference:** `~/Documents/dev/micro-service-demo/microservices-demo-latest/` — the
authoritative, k8s-native Online Boutique. `src/loadgenerator/locustfile.py` is the canonical journey
source of truth; `release/kubernetes-manifests.yaml` is the canonical topology. **There is no
docker-compose upstream** (the demo is k8s-native), so kind/k8s is the most faithful substrate and
compose is a derived approximation — the journey design must stay substrate-parameterized.

---

## 1. Canonical user journeys (source of truth)

From `src/loadgenerator/locustfile.py` — these are **HTTP flows against the FRONTEND** (port 8080,
exposed as Service port 80). The frontend orchestrates the backend gRPC fleet; the loadgen never speaks
gRPC directly. This is the authoritative definition of "a real Online Boutique user journey."

### Task set + weights (`UserBehavior.tasks`)

| Task | Weight | HTTP call(s) | Backend gRPC fan-out (via frontend) |
|---|---|---|---|
| `index` | **1** | `GET /` | productcatalog.ListProducts, currency, ad, recommendation |
| `setCurrency` | **2** | `POST /setCurrency {currency_code}` (∈ EUR/USD/JPY/CAD/GBP/TRY) | currency.GetSupportedCurrencies/Convert |
| `browseProduct` | **10** | `GET /product/{id}` | productcatalog.GetProduct, currency.Convert, recommendation, ad |
| `viewCart` | **3** | `GET /cart` | cart.GetCart, productcatalog, currency, shipping.GetQuote, recommendation |
| `addToCart` | **2** | `GET /product/{id}` then `POST /cart {product_id, quantity 1..10}` | productcatalog.GetProduct, cart.AddItem |
| `checkout` | **1** | `addToCart` then `POST /cart/checkout {…}` | **checkout.PlaceOrder** → catalog+cart+currency+shipping+payment+email (the 6-dep orchestration) |

Also defined but **not in the active weighted set**: `empty_cart` (`POST /cart/empty` → cart.EmptyCart)
and `logout` (`GET /logout`). `on_start` calls `index`. `WebsiteUser` is a `FastHttpUser` with
`wait_time = between(1, 10)`. Product IDs are the **canonical 9-SKU fixture set**:
`0PUK6V6EV0, 1YMWWN1N4O, 2ZYFJ3GM2N, 66VCHSJNUP, 6E92ZMYYFZ, 9SIQT8TOJO, L9ECAV7KIM, LS4PSXUNUM, OLJCESPC7Z`.

**Weight reading (the discriminating signal):** `browseProduct` (10) dominates, then `viewCart` (3),
`setCurrency` (2), `addToCart` (2), and `index`/`checkout` (1 each). So the canonical journey mix is
**read-heavy browse traffic with a single low-frequency-but-deep checkout** — the checkout is the rare,
high-value path that exercises the full 6-service orchestration. Round-3 cross-service scoring should
weight per-step coverage by this canonical mix (or report both weighted and unweighted), since a model
that nails browse but fails checkout looks very different under canonical weighting.

### Canonical checkout payload (`checkout()` → `POST /cart/checkout`)

The exact form-encoded body the frontend expects (the contract the SDK journey driver must reproduce):

```
email                          = <faker email>
street_address                 = <faker street_address>
zip_code                       = <faker zipcode>
city                           = <faker city>
state                          = <faker state_abbr>
country                        = <faker country>
credit_card_number             = <faker visa number>
credit_card_expiration_month   = randint(1, 12)
credit_card_expiration_year    = randint(year+1, year+71)   # always future
credit_card_cvv                = "<randint(100,999)>"        # string
```

`checkout()` always prepends an `addToCart` (so the cart is non-empty when PlaceOrder fires). The
expiration year is forced **future** (`datetime.now().year + 1` floor) — a journey driver that emits a
past expiry would trip a legitimate decline and mis-score the payment step.

---

## 2. The unified model — transport-agnostic journey + two adapters + bonus frontend

Round 3 scores **cross-service journeys**. The settled design defines the journey **ONCE**, abstracted
from how it reaches the fleet, and runs it over **two transport adapters**. The frontend is a **scored
BONUS service** with a **canonical-substitution** safety net so evaluation never depends on it.

### 2.1 The transport-agnostic journey spec (defined once)

The journey is a sequence of **logical steps** with **expected outcomes**, independent of transport:

| # | Logical step | Logical intent | Expected outcome (transport-independent) | Backend services exercised |
|---|---|---|---|---|
| 1 | **browse** | list + view products, prices localized | products returned; a product's price renders in the active currency | productcatalog, currency, (ad, recommendation) |
| 2 | **setCurrency** | change active currency to a whitelisted code | subsequent prices reflect the new currency | currency |
| 3 | **addToCart** | add a known SKU (qty 1..10) to the session cart | item is in the cart | productcatalog, cart |
| 4 | **viewCart** | read the cart back with totals + shipping quote | cart shows the added item; a shipping quote + total compute | cart, productcatalog, currency, shipping, (recommendation) |
| 5 | **checkout** | place an order with the canonical payment+address payload | an order id is returned; the 6-dep orchestration succeeds | checkout → productcatalog, cart, currency, shipping, payment, email |

This is the **single source of truth**. Step inputs (the 9-SKU fixture set, the whitelisted currencies,
the future-dated checkout payload) come from §1 and are reused **verbatim** by both adapters — only the
*encoding* differs (gRPC message vs form POST). The expected-outcome column is what per-step coverage
scores against, regardless of which adapter ran it.

### 2.2 Adapter B — direct-gRPC driver (always-on diagnostic)

An SDK-authored driver dials the contestant backends' gRPC endpoints directly, replaying the journey's
*fan-out* (the §1 gRPC map). It reuses the validated behavioral-suite machinery (the checkout suite
already dials PlaceOrder with the 6 deps; cart/catalog/currency suites exist).

- **Contestant-pure** — every service in the scored path is contestant-generated; no reference code in
  the measured surface. This adapter is **always run** and is the **diagnostic backbone**: it isolates
  whether the *backends compose* independent of any frontend. It owns the orchestration logic the
  frontend would normally own, so it proves composition but not the HTTP→gRPC translation.

### 2.3 Adapter A — HTTP driver over a frontend (canonical journey)

The real form-encoded HTTP journey (the locustfile mix, §1) run end-to-end against **whichever frontend
is in place** — the generated one if it passes the gate, else the canonical one. Because both frontends
satisfy the **same journey-facing HTTP contract** (`FRONTEND_OPENAPI_CONTRACT.md`), this adapter is
**frontend-agnostic**: the same HTTP driver script runs unchanged over either. This is the literal OB
data path: the real HTTP surface and the real HTTP→gRPC fan-out.

### 2.4 The bonus-frontend + canonical-substitution mechanism

The frontend (10th service) is a **BONUS** the contestant model MAY generate:

1. **If the model generates a frontend**, the harness runs it through a **health + OpenAPI-contract
   gate** (`FRONTEND_OPENAPI_CONTRACT.md` §gate): the frontend must boot, serve the journey-facing
   routes, and complete an end-to-end checkout against a **known-good (canonical) backend fleet**.
2. **Gate PASS** → the generated frontend is used for Adapter A (the real HTTP journey runs through
   contestant code end-to-end) **and** the model earns **frontend bonus credit** (§4).
3. **Gate FAIL** (missing / won't boot / off-contract / checkout fails) → the harness **substitutes the
   canonical upstream `src/frontend`** (the model-invariant reference impl), wired to the contestant
   backends via `*_SERVICE_ADDR`. Adapter A still runs — over the canonical frontend — so the HTTP
   journey + all backend scoring **continue uninterrupted**. The model simply earns **zero frontend
   bonus**; nothing is subtracted.

The **OpenAPI contract is the substitution seam**: because both frontends satisfy the identical
journey-facing HTTP contract, the Adapter-A driver is oblivious to which one is mounted. A model is
**never zeroed for a bad frontend** — the frontend is pure upside.

### 2.5 Why this supersedes the v0.1 fork

v0.1 treated A1/A2/B as mutually exclusive and rejected A1. The unified model dissolves the conflict:
**all three coexist by role.** B is the always-on contestant-pure diagnostic. A2 (canonical frontend) is
no longer a "v2 overlay" but the **always-available fallback** that guarantees Adapter A runs
unconditionally. A1 (generated frontend) is **promoted from rejected to a bonus** because its failure
mode is now contained by substitution rather than poisoning the whole round. The previous all-or-nothing
objection ("a broken generated frontend zeroes all cross-service signal") is exactly what the
substitution seam removes.

---

## 3. Canonical topology — service→port + dependency-env map

From `release/kubernetes-manifests.yaml`. **containerPort** = what the process listens on;
**Service port** = the cluster DNS port other services dial. These differ for emailservice (the one
trap, see ⚠). `*_SERVICE_ADDR` values are the literal env the consumer reads.

| Service | Lang | containerPort | Service (DNS) port | Probe | Consumed-as `*_SERVICE_ADDR` |
|---|---|---|---|---|---|
| frontend | Go | 8080 | 80 (`frontend:80`) | HTTP `/` w/ session cookie | (entry; loadgen → `FRONTEND_ADDR=frontend:80`) |
| productcatalogservice | Go | 3550 | 3550 | grpc 3550 | `PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:3550` |
| checkoutservice | Go | 5050 | 5050 | grpc 5050 | `CHECKOUT_SERVICE_ADDR=checkoutservice:5050` |
| shippingservice | Go | 50051 | 50051 | grpc 50051 | `SHIPPING_SERVICE_ADDR=shippingservice:50051` |
| cartservice | C# | 7070 | 7070 | grpc 7070 | `CART_SERVICE_ADDR=cartservice:7070` |
| currencyservice | Node | 7000 | 7000 | grpc 7000 | `CURRENCY_SERVICE_ADDR=currencyservice:7000` |
| paymentservice | Node | 50051 | 50051 | grpc 50051 | `PAYMENT_SERVICE_ADDR=paymentservice:50051` |
| recommendationservice | Python | 8080 | 8080 | grpc 8080 | `RECOMMENDATION_SERVICE_ADDR=recommendationservice:8080` |
| adservice | Java | 9555 | 9555 | grpc 9555 | `AD_SERVICE_ADDR=adservice:9555` |
| **emailservice** ⚠ | Python | **8080** | **5000** | grpc 8080 | `EMAIL_SERVICE_ADDR=emailservice:5000` |
| redis-cart | (dep) | 6379 | 6379 | tcp 6379 | `REDIS_ADDR=redis-cart:6379` (cartservice backing store) |

**Dependency fan-out (the `*_SERVICE_ADDR` wiring):**
- **frontend** dials: productcatalog, currency, cart, recommendation, shipping, checkout, ad,
  shoppingassistant (8 deps).
- **checkoutservice** dials: productcatalog, shipping, payment, email, currency, cart (the **6 deps**
  the canonical PlaceOrder orchestration fans out to).
- **recommendationservice** dials: productcatalog (1 dep).
- **cartservice** dials: redis-cart (its store, not a gRPC OB service).

### ⚠ Cross-check vs the startup contracts (drift findings)

The scorecard's call-counter is keyed by `*_SERVICE_ADDR` and lists exactly the canonical six checkout
deps (`scorecard.py` `RPC_RESULT_TO_ADDR`):
`PRODUCT_CATALOG_SERVICE_ADDR, CART_SERVICE_ADDR, CURRENCY_SERVICE_ADDR, SHIPPING_SERVICE_ADDR,
PAYMENT_SERVICE_ADDR, EMAIL_SERVICE_ADDR` — **matches the canonical checkout fan-out exactly.** The
checkout-orchestrator suite (`execute.py`) reads the seed's `startup.dependency_addr_env` names and
binds the six stubs, which is the same six. **No drift in the env-NAME set.**

**One topology trap to encode (not a current drift, but a faithfulness requirement):**
- **emailservice port asymmetry** — the process **listens on 8080** but is **dialed on 5000**
  (`EMAIL_SERVICE_ADDR=emailservice:5000`; the k8s Service remaps 5000→8080). In the behavioral suites
  today the email dependency is a **harness stub** bound to a free loopback port, so the asymmetry is
  invisible. But if Option A2 (real frontend) or a full live emailservice ever enters the fleet, the
  fleet wiring must reproduce the **dial-port (5000) ≠ listen-port (8080)** remap, or checkout's email
  step silently misses. Recommend the fleet topology table carry an explicit `(listen_port,
  dial_port)` pair per service rather than assuming they're equal — emailservice is the canonical proof
  they aren't. All other services have listen == dial.
- **cartservice needs redis** — canonical cartservice is **stateful** (`REDIS_ADDR=redis-cart:6379`).
  The behavioral cart suite stubs this; a live-fleet cartservice (Option A2) needs a redis sidecar in
  the compose/kind topology. Flag for the fleet generator: redis-cart is a non-seed infra dependency,
  not a contestant service.

No `*_SERVICE_ADDR` **name** mismatch was found between the canonical manifest and the harness; the
only gaps are **port-remap faithfulness** (email) and **infra deps** (redis) that the current
stub-based suites paper over but a canonical-frontend fleet would expose.

---

## 4. Scoring model — backend layered (always) + additive frontend bonus

How this journey design rides the existing pieces and the **never-subtractive** scoring rule:

- **Compose-fleet prototype** (`COMPOSE_FLEET_PROTOTYPE.md`, validated): supplies the 9-backend fleet
  with `*_SERVICE_ADDR` DNS wiring on an `internal` (egress-denied) network. The §3 table is the
  authoritative wiring it must reproduce; the email `(8080 listen / 5000 dial)` remap and the redis-cart
  infra dep are the two faithfulness items to add. Because there is **no upstream compose**, the prototype
  is a derived approximation of the k8s topology — kind parity (OQ-C7) is where it converges to canonical.
- **Adapter B (direct-gRPC)** dials the fleet's gRPC endpoints replaying the §1 fan-out, reproducing the
  §1 checkout payload as gRPC messages. It reuses the behavioral checkout suite's 6-dep PlaceOrder path
  but now against **live contestant backends** instead of stubs. Always run.
- **Adapter A (HTTP)** runs the real locust mix over the in-place frontend (generated-if-gate-passed,
  else canonical). Always run, because the canonical frontend is always available as fallback.

### 4.1 Backend layered score — runs REGARDLESS of which frontend is in place

The backend score is the **scored model-skill axis** and is computed identically whether the generated
or the canonical frontend is mounted (the frontend is not in the backend-scored surface). Two axes,
both consistent with Scorecard Principle 7 (cross-service journey signal is **reported**; per-service
leaf suites remain the scored skill):

1. **Per-step journey coverage** — for each logical step (browse/setCurrency/addToCart/viewCart/checkout,
   §2.1), did the fleet serve it with the expected outcome? Weight by the §1 canonical mix
   (browse 10 … checkout 1) and/or report unweighted, so a browse-strong/checkout-weak fleet is
   distinguishable. Sourced primarily from **Adapter B** (contestant-pure); confirmed by Adapter A.
2. **Per-service fault attribution** — when a step fails, the `*_SERVICE_ADDR` call-counter (in
   `scorecard.py`) attributes the miss to the specific service that wasn't dialed / errored, decomposing
   a fleet failure into per-contestant-service blame — the per-service skill axis the leaf suites score.

Because Adapter A always runs over *some* frontend, **backend scoring never stalls on a bad generated
frontend**: substitution keeps the HTTP path alive and the backend axes intact.

### 4.2 Frontend bonus — additive, never subtractive

The frontend contributes a **separate, additive bonus** that **only ever raises** a model's total. It is
**not** folded into the per-service backend ranking and **cannot reduce** the backend score. Two
sub-components:

- **(a) Frontend service score** — if the generated frontend passes the gate, score it as its own leaf
  artifact: correct routes, correct HTTP→gRPC orchestration (the §1 route→fan-out map), clean
  redirects/pages. A failed/absent frontend scores **0 bonus** (not negative).
- **(b) `journey_via_generated_frontend` flag** — binary: did the real locust mix complete end-to-end
  **through the contestant's own frontend** (gate passed AND Adapter A green on the generated frontend).
  Earned only when the generated frontend is in place; pure credit.

When the canonical frontend is substituted, Adapter A still produces a **`canonical_journey_completed`**
report flag (the "this fleet is genuinely the real Online Boutique" authenticity seal) — but that flag
is a *fleet-authenticity* signal, **not** frontend bonus credit (it's earned by the reference impl, not
the contestant).

### 4.3 Folding the bonus into the scorecard without distorting backend ranking

The rule: **rank on backend layered score; break ties / annotate with frontend bonus.** Concretely —
report `backend_score` (the ranked axis) and `frontend_bonus` (additive) as **separate columns**; the
headline ranking is by `backend_score` so a model with a brilliant frontend but weak backends never
outranks a strong-backend model. The bonus surfaces as a tie-break and as a labeled "+frontend" credit,
keeping the benchmark's core promise (measure backend/orchestration model-skill) undistorted while
rewarding the harder frontend artifact as upside. (Open question OQ-J3, §5, tracks the exact bonus
magnitude / capping so the additive term can't dominate.)

This keeps Round 3 honest: **the backend layered score grades and ranks** (contestant-pure, frontend-
invariant), **the frontend bonus rewards** (additive, gated, never subtractive), and the canonical
frontend **guarantees Adapter A always runs** so neither axis can be blocked by a broken generated
frontend.

---

## 5. Open questions (journey/frontend)

- **OQ-J1 — gate strictness.** How strict is the frontend health/contract gate before substitution? Too
  loose → a subtly-broken generated frontend produces misleading Adapter-A journey results; too strict →
  near-passing frontends lose deserved bonus. See `FRONTEND_OPENAPI_CONTRACT.md` §gate. Lean strict
  (behavioral end-to-end checkout against known-good backends) so a frontend that "looks right but mis-
  orchestrates" fails cleanly to canonical rather than poisoning the journey.
- **OQ-J2 — Adapter A over the generated frontend vs contestant backends, double-counting.** When the
  generated frontend AND contestant backends both run, an Adapter-A failure could be the frontend's fault
  or a backend's. Adapter B (always-on, contestant-backends-only) is the disambiguator: if B's step
  passed but A failed only on the generated frontend, attribute to the frontend (bonus loss), not the
  backend. Encode this attribution precedence.
- **OQ-J3 — bonus magnitude / capping.** The exact `frontend_bonus` weight and cap so the additive term
  rewards without dominating the backend ranking (§4.3). Must stay a tie-break/annotation, not a
  rank-flipper.
- **OQ-J4 — substitution must be observable.** Every run report must record **which frontend was in
  place** (generated-passed vs canonical-substituted) and the gate verdict + reason, so a substituted run
  is never silently mistaken for a generated-frontend pass.
