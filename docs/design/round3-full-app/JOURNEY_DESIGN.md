# Round 3 — Journey & Topology Design

**Version:** 0.1 (design — NO implementation)
**Date:** 2026-06-24
**Status:** Design/decision doc. Deliverables: the canonical user-journey set (source of truth for
Round-3 cross-service scoring), the frontend-vs-direct-gRPC entry-point fork (framed for a decision +
recommendation), and the canonical service→port + dependency-env topology cross-checked against the
startup contracts.
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

## 2. The entry-point fork (decision required)

Round 3 scores **cross-service journeys**, but the canonical journeys above are HTTP-against-frontend.
The frontend is **not a benchmark seed** (NR-2 — it's SDK-authored, not contestant-generated). So
"run the canonical journey" forces a fork:

### Option A — include a FRONTEND in the fleet (canonical entry)

Run the real locust HTTP journeys end-to-end against a frontend that orchestrates the contestant
backends over gRPC.

- **A1 (contestant generates the frontend):** add frontend as a 10th seed. **Rejected for v1** — it's
  net-new seed authoring, it's a Go HTML/template app (a different skill axis than the gRPC backends),
  and it couples every journey's success to one contestant artifact (a broken generated frontend zeroes
  *all* cross-service signal even if the backends are perfect). Conflates frontend skill with
  orchestration skill.
- **A2 (canonical frontend as a fixed harness driver):** drop the upstream `src/frontend` binary into
  the fleet as a **harness-owned, model-invariant** driver, wired to the contestant backends via
  `*_SERVICE_ADDR`. The locustfile runs unmodified against it. **Most canonical** — it's the real OB
  data path, the real HTTP surface, the real gRPC fan-out. Cost: the harness must build+run the Go
  frontend (one more image, but model-invariant so it builds once), keep its `*_SERVICE_ADDR` env in
  lockstep with the fleet (§3), and the frontend's own correctness is a fixed constant (fine — it's the
  reference impl).

### Option B — SDK journey driver calling backend gRPC directly

No frontend. An SDK-authored driver dials the contestant backends' gRPC endpoints directly, replaying
the journey's *fan-out* (catalog browse → cart add → currency convert → checkout.PlaceOrder → …).

- **Most contestant-pure** — every service in the scored path is contestant-generated; nothing in the
  measured surface is reference code. Reuses the existing behavioral-suite machinery (the checkout suite
  already dials PlaceOrder with the 6 deps; cart/catalog/currency suites already exist).
- **Less canonical** — it's the gRPC fan-out the frontend *would* make, not the literal HTTP journey;
  the SDK driver owns the orchestration logic the frontend normally owns, so it tests "do the backends
  compose" but not "does the canonical HTTP→gRPC translation hold." The journey payload (§1) is
  reproduced as gRPC messages, not the form POST.

### Recommendation

**Ship v1 on Option B (direct-gRPC SDK driver) as the scored path; add Option A2 (canonical frontend as
fixed harness driver) as a v2 "canonical-journey-completed" overlay.**

Rationale: B keeps the **entire scored surface contestant-generated** (the benchmark's whole point —
measure model skill, not reference-frontend skill), reuses the validated behavioral suites + the
compose-fleet prototype + the 6-dep checkout orchestration that already exists, and avoids coupling
cross-service signal to a Go-frontend build. A2 is strictly more canonical and is the right way to earn
a **binary `canonical_journey_completed` flag** (did the real locust mix pass end-to-end against the
fleet) — but it's an overlay/credibility signal, not the per-step scored axis. So: **B is the
graded harness; A2 is the canonical seal of authenticity layered on top once the fleet is stable.**
Never adopt A1 (contestant frontend) — it conflates two skills and creates an all-or-nothing failure
mode.

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

## 4. Composition with the compose-fleet prototype + layered scoring

How this journey design rides the existing pieces:

- **Compose-fleet prototype** (`COMPOSE_FLEET_PROTOTYPE.md`, validated): supplies the 9-backend fleet
  with `*_SERVICE_ADDR` DNS wiring on an `internal` (egress-denied) network. The §3 table is the
  authoritative wiring it must reproduce; the email `(8080 listen / 5000 dial)` remap and the redis-cart
  infra dep are the two faithfulness items to add. Because there is **no upstream compose**, the prototype
  is a derived approximation of the k8s topology — kind parity (OQ-C7) is where it converges to canonical.
- **Journey driver = Option B** dials the fleet's gRPC endpoints replaying the §1 fan-out, reproducing
  the §1 checkout payload as gRPC messages. It reuses the behavioral checkout suite's 6-dep PlaceOrder
  path but now against **live contestant backends** instead of stubs.
- **Layered scoring** composes three independent axes (all consistent with Scorecard Principle 7 —
  cross-service journey signal is **reported**, the per-service leaf suites remain the scored skill):
  1. **Per-step journey coverage** — for each canonical task (index/browse/viewCart/addToCart/checkout),
     did the fleet serve it? Weight by the §1 canonical mix (browse 10 … checkout 1) and/or report
     unweighted, so a browse-strong/checkout-weak fleet is distinguishable.
  2. **Per-service attribution** — when a journey step fails, the `*_SERVICE_ADDR` call-counter (already
     in `scorecard.py`) attributes the miss to the specific service that wasn't dialed / errored, so a
     fleet failure decomposes into per-contestant-service blame (which is the per-service skill axis the
     leaf suites already score — the journey just confirms they *compose*).
  3. **`canonical_journey_completed` flag** — a binary credibility seal: did the **canonical locust mix**
     (Option A2, real frontend, unmodified locustfile) complete end-to-end against the fleet. Reported,
     never folded into the ranking — it's the "this fleet is genuinely the real Online Boutique"
     authenticity check, earned only via the canonical frontend overlay.

This keeps Round 3 honest: **B grades** (contestant-pure per-step + per-service), **A2 certifies**
(canonical journey actually runs), and the per-service leaf suites remain the scored model-skill axis —
the journey layer reports whether the independently-scored services **compose into a working store**.
