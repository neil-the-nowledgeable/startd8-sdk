# Checkout Orchestrator Behavioral Suite — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-23
**Status:** Updated per reflective-requirements PHASES 3–4 (planning insights folded back). No implementation.
**Owner SDK area:** `startd8.benchmark_matrix.behavioral` (suite + dependency-stub harness) + seeds
**Parent scope:** `docs/design/pricing-lane-integration/CHECKOUT_PHASE2_SCOPE.md` (C-1..C-6, CQ-1..4)
**Parent reqs:** `docs/design/benchmark-scoring/FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md`
(FR-X4-*, E4/E6) — this is **Tier C** of that roster.

---

## 0. Planning Insights (Self-Reflective Update)

The PLAN.md pass against the **real** behavioral-suite infra (`execute.py`, `contract.py`,
`sandbox.py`, `demo_pb2_grpc.py`, `provision.py`, the seed) revealed that most of the v0.1 scope was
already shipped infrastructure to be **reused**, not built. The net effect is **scope-reducing**: the
only genuinely net-new complexity is the **execute.py orchestration branch** (stub bring-up + runtime
address injection before the SUT launches). The corrections below are folded into the FRs in §3.

### Discoveries (v0.1 assumption → planning discovery → impact)

| # | v0.1 assumption | Planning discovery | Impact |
|---|-----------------|--------------------|--------|
| 1 | A Go serve launcher may need building (C-5). | The Go launcher **already exists** (`contract.py:_go_default` → `["sh","-c","cd <dir> && exec ./.bin/server"]`, `$PORT` injected, registered in `_DEFAULTS`). | **Narrow** the launcher FR to "add dependency-address env injection to the existing launcher path" — no launcher is built. (FR-CO-9, FR-CO-10) |
| 2 | Stubs run "alongside" the SUT; sibling-vs-in-process unclear. | The suite client runs **outside** the seatbelt sandbox (`sandbox.py:335`); only the SUT is sandboxed, and the sandboxed Go service reaches loopback (loopback-allowed / egress-denied). | **Settled architectural decision:** stubs are **in-process Python gRPC servers** on loopback started by the harness before the SUT launches. **No sibling-process orchestration.** Simplifies FR-CO-2/3. |
| 3 | The 6 dependency stubs need proto/gRPC codegen. | **All 6 servicers already exist** in `demo_pb2_grpc.py` (`add_{ProductCatalog,Cart,Currency,Shipping,Payment,Email}ServiceServicer_to_server`). | **Zero** new proto/codegen work — FRs say "**subclass** the existing servicers," not "generate stubs." (FR-CO-1) |
| 4 | Dependency addresses live in the seed `startup` block. | Stub ports are allocated at **suite runtime** (`_free_port`), so addresses are **runtime-injected via `extra_env`**; the seed `startup` block carries env **names** only. | Reframe the address FRs: seed declares names (`PRODUCT_CATALOG_SERVICE_ADDR`, …); `execute.py` allocates ports + injects the actual `*_SERVICE_ADDR` values before launch. (FR-CO-9, FR-CO-10) |
| 5 | A leaf-style `client(port)` suite contract suffices. | The shipped `client(port)` contract is **insufficient** for checkout: it must bring up 6 stubs + inject addresses **before** the SUT launches, then tear down. | **A dedicated `execute.py` branch is required** — the **complexity locus** and the **riskiest step** (elevated to a headline FR and the top plan risk). Assertions are comparatively easy. (FR-CO-EXEC, FR-CO-7) |
| 6 | Per-step coverage is observable from the response. | `payment.transaction_id` is opaque and `email` returns `Empty`; those steps are **not response-observable**. | **Stub call-counters are a HARD requirement** (not optional) to attribute the payment/email steps. (FR-CO-8) |
| 7 | `_PROTO_BY_SERVICE` may need a checkout entry. | Checkout uses the shared `demo.proto` default. | **No `_PROTO_BY_SERVICE` change** — drop any FR implying a proto-map edit. (FR-CO-14) |
| 8 | The seed just needs a `startup` block added. | **Biggest blocker:** `seed-checkoutservice.json` has **no `startup` block at all** — it must be **re-authored**, and its env-name contract **co-defined** with the execute.py injection branch. | **Gating prerequisite (B1).** (FR-CO-9) |
| 9 | The stubs validate themselves trivially. | Stub self-validation needs a **committed correct Go reference checkout** (a real 6-way orchestrator). | A **real authoring cost (B3)** — note it as a one-time committed fixture. (FR-CO-12) |

### Resolved open questions (CQ-1..4)

- **CQ-1 (per-step weighting) — RESOLVED: equal-weight the 6 steps.** No payment/total up-weighting in v1; revisit only if it fails to discriminate the flagships.
- **CQ-2 (stub request assertions) — RESOLVED: call-counters REQUIRED; request-content assertions DEFERRED.** Counters are the only observable for `Empty`/opaque steps (FR-CO-8); content correctness rides the response's total/tracking/items.
- **CQ-3 (failure-injection in v1) — RESOLVED: NO failure-injection.** A single happy-path scenario for v1. The known-broken reference (FR-CO-13) is a harness-validation fixture, not a model scenario.
- **CQ-4 (scorecard placement) — RESOLVED: its OWN "integration frontier" sub-section.** Checkout measures a distinct axis (orchestration wiring) from the pricing lane (arithmetic); per-step coverage is its own story. (FR-CO-20)

---

## 1. Problem Statement

The shipped Track-2 behavioral harness discriminates frontier models on **stateless leaf RPCs**
(`Charge`, `Convert`, `GetQuote`, pricing math). `checkoutservice.PlaceOrder` is categorically
different: it is a **6-way gRPC orchestrator** that only behaves correctly when six dependencies
(productcatalog, cart, currency, shipping, payment, email) answer. It cannot run as a leaf, has **no
behavioral suite**, and its seed carries **no `startup` block**, so a behavioral re-run is impossible
today.

The decided design constraint: the six dependencies are **SDK-authored loopback stubs returning
fixed ground-truth responses** — **never** other models' generated services (that would confound
checkout's score with its dependencies' quality, NR-X2). The generated checkout runs in the sandbox;
the stubs run alongside over loopback with their addresses injected via the real Online Boutique env
convention (`PRODUCT_CATALOG_SERVICE_ADDR`, etc.). A checkout that ignores those addresses and dials
elsewhere is a **real behavioral miss**; a checkout that can't reach a dep because the harness failed
to provision it is a **degrade**.

### Gap table (verified against the code, not assumed)

| # | Gap | Evidence | Consequence |
|---|-----|----------|-------------|
| G1 | No `checkout_suite.py`; `_SUITES` has 8 keys, checkout absent. | `behavioral/execute.py:34-43` | `run_behavioral_cell("checkoutservice", …)` returns `has_suite=False` (no score). |
| G2 | `seed-checkoutservice.json` has **no `startup` block** and no dependency-address env. | seed lines 24-47; `StartupContract.from_seed` returns `None` when `startup` absent. | `resolve_serve_command` falls to the Go default (`./.bin/server`, `PORT` only) — **no dep addresses injected**. Re-author required. |
| G3 | No dependency-stub harness exists. | `checkoutservice` appears only in `demo_pb2_grpc.py` + `contamination.py`. | Nothing for the generated checkout to dial. |
| G4 | The 6 dependency **servicers already exist** in the generated proto stubs (`add_{ProductCatalog,Cart,Currency,Shipping,Payment,Email}ServiceServicer_to_server`). | `demo_pb2_grpc.py` | The stub harness **implements these servicers**; it does not need new proto codegen. |
| G5 | `run_service_sandboxed` runs the **suite client in the harness process**, not inside the sandbox (`sandbox.py:335`); only the SUT is sandboxed (seatbelt loopback-allowed / egress-denied). | `sandbox.py:319-346` | Stubs can be **in-process Python gRPC servers** on loopback started by the harness before the SUT launches — the sandboxed Go checkout reaches them because loopback is allowed. |
| G6 | The Go serve default exists (`_go_default` → `./.bin/server`) and Go provisioning compiles a binary at prepare time. | `contract.py:60-70`, `provision.py:113-117` | The launcher is **not net-new**; but it injects only `PORT`. The seed `startup` block declares the dep-address env **names**; the **values** are runtime-injected by the execute layer (§0-4, FR-CO-EXEC/FR-CO-10) since stub ports bind at run time. |

---

## 2. Goals & Non-Goals

**Goals**
1. An SDK-authored **dependency-stub harness**: six fake gRPC servers (one per dependency) returning
   **fixed ground-truth** responses, started on loopback, torn down deterministically.
2. A `checkout_suite.py` that drives `PlaceOrder` once (happy path) and scores **per-step partial
   coverage** so skipping a dependency scores partial, not all-or-nothing.
3. A re-authored `seed-checkoutservice.json` `startup` block: Go launch + `$PORT` + the six
   `*_SERVICE_ADDR` env vars pointing at the stubs.
4. **Stub-harness self-validation** against a committed known-good reference checkout (coverage 1.00)
   and a known-broken one (fails the right steps).
5. Registration into `_SUITES` (the shared `demo.proto` default means **no `_PROTO_BY_SERVICE`
   change**, §0-7), reusing the existing scoring/aggregation path — plus the FR-CO-EXEC branch, since
   registration alone is insufficient (§0-5).
6. Orchestrator-appropriate **model-fault vs degrade** classification.

**Non-Goals**
- No real generated dependencies (NR-X2) and no live full-mesh Online Boutique deploy (NR-X1).
- No auto-orchestrator / generation-path changes.
- No fault-injection of dependencies in v1 (stubs are well-behaved — NR-X4); deferred to CQ-3.
- No new scoring logic — fold through existing `compute_composite` / `aggregate.py` (FR-X8-REUSE).
- Kernel-level isolation (inherits the parent's best-effort host controls, recorded honestly).

---

## 3. Functional Requirements

### Dependency-stub harness (C-1)
- **FR-CO-1 (stub servers — subclass existing servicers).** The SDK ships fake gRPC servers for all
  six PlaceOrder dependencies by **subclassing the already-existing servicers** (§0-3)
  (`ProductCatalogServiceServicer`, `CartServiceServicer`, `CurrencyServiceServicer`,
  `ShippingServiceServicer`, `PaymentServiceServicer`, `EmailServiceServicer` from `demo_pb2_grpc`).
  Each returns **fixed ground-truth** for the suite's single PlaceOrder input. **Zero new proto/codegen
  work** — reuse `demo_pb2`/`demo_pb2_grpc` as-is.
- **FR-CO-2 (loopback, in-process).** Stubs run as **in-process Python gRPC servers** bound to
  `127.0.0.1:<ephemeral>` in the harness process (which is outside the seatbelt sandbox per G5), so
  the sandboxed Go checkout can dial them over loopback while external egress stays denied. Each stub
  gets a free port via the existing `_free_port()` discipline.
- **FR-CO-3 (deterministic teardown).** All six stub servers are **guaranteed stopped** (gRPC
  `server.stop(grace)`) after the suite returns, even on exception — paralleling
  `run_service_sandboxed`'s killpg guarantee. No orphaned listeners across cells/reps (FR-X3-ISO).
- **FR-CO-4 (single configurable harness).** One stub-harness module configures all six servicers
  with one ground-truth fixture (per OQ-X2 lean: a single configurable harness, less to maintain),
  not six bespoke modules.

### Ground-truth fixture (C-3)
- **FR-CO-5 (fixed catalog + responses).** The harness defines a fixed ground-truth: a small product
  catalog (id → name → `price_usd`), a fixed cart for the suite's `user_id` (product ids ×
  quantities), a deterministic currency conversion (identity or a fixed rate for `user_currency`), a
  fixed shipping quote + non-empty `tracking_id`, a fixed `transaction_id` from payment, and an email
  `Empty` ack. These values are the suite's oracle.
- **FR-CO-6 (computable expected order).** From the fixture the expected `PlaceOrderResponse.order`
  is **deterministically computable**: `order.items` = the cart's items priced from the catalog;
  `order.shipping_cost` / `order.shipping_tracking_id` from the shipping stub; total (for assertion)
  = Σ(catalog price × quantity) converted to `user_currency` + shipping. The suite asserts the
  response against this, not against leaf arithmetic re-derivation.

### Per-step PlaceOrder coverage (C-3)
- **FR-CO-7 (per-step scoring).** `coverage ∈ [0,1]` = passing steps / total steps, where each step
  is an independently-observable orchestration obligation. Skipping a dependency fails only that
  step, scoring partial. Minimum step set:
  1. **catalog priced** — order items carry catalog-sourced prices (productcatalog dialed).
  2. **cart honored** — order items match the fixed cart's product ids × quantities (cart dialed).
  3. **currency converted** — totals are in `user_currency` per the fixed rate (currency dialed).
  4. **shipping applied** — `order.shipping_tracking_id` non-empty + `shipping_cost` set (shipping dialed).
  5. **payment charged** — order produced (a non-empty `order.order_id`), implying payment succeeded
     (payment dialed; see CQ-2 on whether to also assert the stub *saw* a Charge).
  6. **email confirmed** — confirmation path exercised (email dialed; see CQ-2/E5 — observable only
     via the stub recording the call, since `SendOrderConfirmation` returns `Empty`).
- **FR-CO-8 (stub call-counters — HARD requirement, not optional).** Each stub **must** increment a
  per-servicer call counter; the suite records, per step, **whether the stub was actually called**.
  This is **mandatory** (§0-6, CQ-2): `payment.transaction_id` is opaque and `email` returns `Empty`,
  so steps 5 (payment) and 6 (email) are **not response-observable** — call-counters are their **only**
  observable. Counters also distinguish "checkout computed the right total" from "checkout actually
  dialed currency". (Request-content assertions are DEFERRED per CQ-2.)

### Execute.py orchestration branch — the complexity locus (C-2, C-5) — HEADLINE
- **FR-CO-EXEC (dedicated checkout branch in `execute.py`) — HEADLINE / riskiest FR.** The shipped
  leaf-suite `client(port)` contract is **insufficient** for checkout (D5/§0-5). `run_behavioral_cell`
  needs a **dedicated checkout branch** that, in order: (a) binds the six in-process stubs (FR-CO-1..4);
  (b) reads their runtime-allocated loopback ports and builds the `*_SERVICE_ADDR` env map; (c) merges
  that map into `extra_env` **before** `run_service_sandboxed` launches the SUT (the Go checkout reads
  `*_SERVICE_ADDR` at startup); (d) partial-binds `stub_calls`/`ground_truth` into the suite fn;
  (e) tears down all six stubs in a `finally`. This branch is the **single structural divergence** from
  the eight shipped suites and the **top implementation risk** (see PLAN.md B1/#1-risk); it is kept thin
  (bind → inject → `partial` → delegate to the existing sandbox path) to avoid a parallel code path.

### Startup contract + existing Go launcher + address injection (C-2, C-5)
- **FR-CO-9 (re-authored seed — GATING PREREQUISITE).** `seed-checkoutservice.json` currently has
  **no `startup` block at all** (§0-8, B1) and must be **re-authored**. The new block: `cmd` launching
  the **already-existing** compiled Go binary (the `_go_default` `./.bin/server` convention — the
  launcher is **not** built, only reused), `port_env: "PORT"`, `readiness: "tcp"`, **plus** the six
  declared dependency-address env **names**. The block is authoritative over the Go default
  (`StartupContract.from_seed` wins in `resolve_serve_command`). Its env-name contract is **co-defined**
  with the FR-CO-EXEC injection branch.
- **FR-CO-10 (dependency-address env injection — NARROWED to the existing launcher path).** No new
  launcher is built; FR-CO-EXEC adds **runtime address injection** to the existing `_go_default` launch
  path. The harness injects the six stubs' loopback addresses as `extra_env` via the real OB convention:
  `PRODUCT_CATALOG_SERVICE_ADDR`, `CART_SERVICE_ADDR`, `CURRENCY_SERVICE_ADDR`, `SHIPPING_SERVICE_ADDR`,
  `PAYMENT_SERVICE_ADDR`, `EMAIL_SERVICE_ADDR` (each `127.0.0.1:<stubport>`). Because stub ports are
  allocated at suite runtime (`_free_port`, not seed-author time), the **values are injected by the
  execute/runner layer** (FR-CO-EXEC), never hardcoded in the seed `startup.cmd` — the seed declares the
  env *names*, the harness fills *values* after binding stubs.
- **FR-CO-11 (Go provisioning exercised — reused unchanged).** The existing Go prepare-time path
  (`go mod tidy && go build -o .bin/server`, `setup_go_stubs` vendoring `demo.pb.go`/`demo_grpc.pb.go`)
  is exercised for real for checkout with **no code change** — it is a *validation* step. A missing
  protocol/infra dep degrades with the path named; an off-contract framework is a model-fault floor
  (R3-F3 reused).

### Stub-harness self-validation (C-4)
- **FR-CO-12 (known-good reference).** A committed **reference Go checkout** (correct orchestration)
  scored against the stub harness yields **coverage 1.00** (gated e2e test, mirroring
  `test_pricing_e2e_node.py`). Anything less is a **harness defect**, not a model defect.
- **FR-CO-13 (known-broken reference).** A committed broken checkout (e.g. never dials payment, or
  hardcodes a wrong dep addr) fails the **expected** steps and not others — proving per-step
  attribution and address-injection both work (the R2-S3 discipline generalized to orchestration).

### Registration & scoring (C-6)
- **FR-CO-14 (registration — no `_PROTO_BY_SERVICE` change).** `_SUITES["checkoutservice"] =
  run_checkout_suite`. Checkout uses the shared `demo.proto`, so **`_PROTO_BY_SERVICE` is NOT touched**
  (§0-7) — it inherits the `(_PROTO, "demo.proto")` default. Note: registration **alone is
  insufficient** — the suite does **not** slot in identically to the leaf suites; it requires the
  FR-CO-EXEC branch (stub bring-up + address injection before launch).
- **FR-CO-15 (no new scoring path).** Coverage folds through the existing `compute_composite`
  (compile floor → functional term) and `aggregate.py`; no parallel scoring (FR-X8-REUSE).

### Model-fault vs degrade for an orchestrator
- **FR-CO-16 (degrade taxonomy).** A checkout that **cannot be launched** for a harness reason
  (Go toolchain absent, stub vendoring missing, never-ready) → **degrade** (FR-32), as today.
- **FR-CO-17 (real-miss taxonomy).** A checkout that **launches and is reached** but produces a wrong
  order (wrong total, missing tracking id, skipped a dep) → **real behavioral coverage** (partial),
  **not** a degrade. Dialing a wrong/invented dependency address (so a stub is never called) is a
  **real miss** on that step, not a degrade — the stubs are present and reachable; checkout chose not
  to use the injected address.
- **FR-CO-18 (off-contract floor reuse).** A checkout that abandons gRPC for the wrong wire protocol
  (an off-contract framework dep) is the existing R3-F3 model-fault floor — reused unchanged.

### Provenance & scorecard
- **FR-CO-19 (provenance).** Each checkout cell records: suite version, per-step pass/fail, **which
  of the six stubs were actually dialed** (call counters, FR-CO-8), the injected dep addresses,
  isolation level, and available-vs-degraded-vs-model-fault — persisted per FR-T2-PERSIST.
- **FR-CO-20 (scorecard surfacing).** Checkout's functional column is surfaced on the leaderboard
  alongside the leaf suites (see CQ-4 for whether it gets its own "integration frontier" discriminator
  section or folds into the pricing-lane hard-lane view).

---

## 4. Non-Requirements

- **NR-CO-1** No generated dependencies — stubs only (NR-X2).
- **NR-CO-2** No live full-mesh OB deploy (NR-X1).
- **NR-CO-3** No auto-orchestrator; no generation-path changes.
- **NR-CO-4** No dependency fault-injection in v1 (stubs well-behaved); CQ-3 may add one error
  scenario if cheap.
- **NR-CO-5** No real Redis/DB for cart state — the cart **stub** answers from the fixture; the SUT
  is the only thing under test (its own cart dependency is stubbed, so checkout never needs a store).

---

## 5. Open Questions — RESOLVED (CQ-1..4)

As of v0.2 these are **resolved**; the canonical resolutions live in **§0 "Resolved open questions"**
and are repeated here for traceability:

- **CQ-1 — per-step weighting.** **RESOLVED: equal-weight, 6 steps** for v1 (matches OQ-X6 lean),
  revisit only if it fails to discriminate the flagships.
- **CQ-2 — do stubs assert request shapes?** **RESOLVED: call-counters REQUIRED (FR-CO-8);
  request-content assertions DEFERRED.** Counters are the only observable for `Empty`/opaque steps;
  content correctness rides the `PlaceOrderResponse` total/tracking/items.
- **CQ-3 — failure-injection in v1?** **RESOLVED: NO** — one happy-path scenario for v1 (NR-CO-4). The
  known-broken reference (FR-CO-13) is a harness-validation fixture, not a model scenario.
- **CQ-4 — scorecard placement.** **RESOLVED: its OWN "integration frontier" sub-section** — checkout
  measures a different axis (orchestration wiring) than the pricing lane (arithmetic), and per-step
  coverage is its own story.

---

*v0.2 (post-planning, self-reflective). The novelty over the shipped harness narrows to two things:
the in-process loopback **dependency-stub harness** (FR-CO-1..4) and the **execute.py orchestration
branch** (FR-CO-EXEC, the new headline/riskiest FR) that brings up stubs and runtime-injects
`*_SERVICE_ADDR` before launch; orchestrator **per-step coverage** (FR-CO-7) rides on mandatory stub
call-counters (FR-CO-8). Everything else reuses shipped infra (the **existing** Go launcher, sandbox
loopback, the **existing** servicers, the shared `demo.proto`, scoring, model-fault floor).*

*v0.1→v0.2 reflective delta: **1 FR elevated/added** (FR-CO-EXEC, headline); **4 FRs narrowed**
(FR-CO-1 subclass-only, FR-CO-9 seed re-author as gating prereq, FR-CO-10 narrowed to the existing
launcher + runtime injection, FR-CO-14 no proto-map change); **1 FR hardened** (FR-CO-8 call-counters
now mandatory, not optional); **4 open questions resolved** (CQ-1..4). No FR superseded/deleted — the
scope reduced by reusing shipped infra, not by removing obligations. 21 FRs total (FR-CO-1..20 +
FR-CO-EXEC).*
