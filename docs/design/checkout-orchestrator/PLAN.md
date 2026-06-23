# Checkout Orchestrator Behavioral Suite — Implementation Plan

**Version:** 0.2 (Post-reflection — execute.py branch elevated)
**Date:** 2026-06-23
**Pairs with:** `REQUIREMENTS.md` v0.2 (this directory)
**Status:** Planning only. No code written.

This plan maps each FR to concrete files/functions, sequences the build, and records a **discoveries
table** from reading the real infra (`execute.py`, `contract.py`, `charge_suite.py`, `provision.py`,
`sandbox.py`, `demo_pb2_grpc.py`, the seed). The discoveries table is the load-bearing output: it
changed several scope-doc assumptions.

> **v0.2 reflection summary.** The **dedicated `execute.py` orchestration branch** (D5 / FR-CO-EXEC)
> is now the **#1 build step and #1 risk** — it is the single structural divergence from the eight
> shipped suites (bring up 6 stubs + runtime-inject `*_SERVICE_ADDR` **before** the SUT launches, then
> tear down). The seed re-authoring (B1) is sequenced as its **prerequisite** (the env-name contract is
> co-defined with the branch), and the committed Go **reference checkout** (B3) is called out as a real
> authoring cost. Everything else simplified: the **Go launcher already exists** (reuse, don't build),
> the **6 servicers already exist** (subclass, don't codegen), stubs are **in-process Python** on
> loopback (no sibling processes), and checkout uses the **shared `demo.proto`** (no `_PROTO_BY_SERVICE`
> change). The assertions are comparatively easy; the risk is the wiring.

---

## A. Discoveries table (scope-doc assumption → what the code revealed)

| # | What the scope/draft assumed | What reading the code revealed |
|---|------------------------------|--------------------------------|
| D1 | The Go serve launcher may be net-new (C-5). | **It already exists.** `contract.py:_go_default` returns `["sh","-c","cd <dir> && exec ./.bin/server"]` with `PORT` injected, registered in `_DEFAULTS={"nodejs":…, "go":…}`. The launcher is **not** net-new; only the **dep-address env** is missing, and that rides the seed `startup` block + runner-injected `extra_env`, not the launcher. |
| D2 | Stubs run "alongside" the SUT — unclear if as sibling processes or in-process. | `run_service_sandboxed` calls `client(port)` **in the harness's own Python process** (`sandbox.py:335`), NOT inside the seatbelt sandbox. Only the SUT subprocess is sandboxed. So the **stubs can be in-process Python gRPC servers** started by the suite/harness before the SUT launches; the sandboxed Go checkout still reaches them because the seatbelt profile **allows loopback** (`_wrap_loopback_only` re-allows `localhost:*` bind/inbound/outbound). This is the single biggest enabler — no sibling-process orchestration needed. |
| D3 | The 6 dependency stubs need proto/gRPC codegen. | **All six servicers already exist** in `demo_pb2_grpc.py` (`add_{ProductCatalog,Cart,Currency,Shipping,Payment,Email}ServiceServicer_to_server` + `demo_pb2` messages). The stub harness **subclasses the existing servicers** — zero new proto work. |
| D4 | Dependency addresses go in the seed `startup.cmd` / `startup` block. | Stub ports are **allocated at suite runtime** (`_free_port()`), not at seed-author time. `StartupContract.resolve` only substitutes `$PORT` and sets `port_env`. So dep addresses must be injected as **`extra_env` by the execute/runner layer after binding stubs** — the seed declares env *names* only; values are filled at run time. This needs a small **execute.py extension** (today `extra_env` for checkout would be empty). |
| D5 | The suite connects to one server (like `charge_suite`). | The checkout suite must **(a) start 6 stub servers, (b) hand their addresses to the harness for env injection, (c) connect a CheckoutServiceStub to the SUT, (d) tear down all 6 stubs.** Steps (a)/(b) must happen **before** `run_service_sandboxed` launches the SUT (the SUT reads `*_SERVICE_ADDR` at startup). This means the checkout path is **not** a drop-in `client(port)` callable like the leaf suites — `run_behavioral_cell` needs a checkout-specific branch that brings up stubs, injects addresses, then runs the cell. |
| D6 | `_PROTO_BY_SERVICE` needs a checkout entry. | **No.** Checkout uses the shared `demo.proto`; `_PROTO_BY_SERVICE.get(service, (_PROTO,"demo.proto"))` already defaults correctly. Only `_SUITES` needs a key — but see D5, registration alone is insufficient. |
| D7 | The seed just needs a `startup` block added. | True, **and** the seed must declare the six `*_SERVICE_ADDR` env names so the harness knows which to fill, **and** a behavioral re-gen of checkout is required (the seed has no `startup` today → `resolve_serve_command` would fall to the bare Go default with no dep env). |
| D8 | Stub teardown is like the SUT's killpg. | Stubs are **in-process grpc.Server** objects (D2), torn down via `server.stop(grace).wait()` in a `finally`, not killpg. Different mechanism; must be exception-safe so a suite crash never leaks a listener into the next cell/rep (FR-X3-ISO). |
| D9 | Per-step coverage is observable from the `PlaceOrderResponse`. | Only **partially.** Total/tracking/items are in the response, but `payment.Charge`→opaque `transaction_id` (not echoed into the response in a fixed way) and `email.SendOrderConfirmation`→`Empty` are **not observable from the response**. The stubs must **record call counts** (FR-CO-8) to attribute steps 5 (payment) and 6 (email). This is why the stub harness, not just the suite, is the unit of work. |
| D10 | Go `go run` launches the service. | Provisioning **pre-compiles** `./.bin/server` at prepare time (`provision.install_plan` go branch) and the serve runs the prebuilt binary — no compile under the egress-denied sandbox. Checkout inherits this; readiness window is already 30s (`execute.py:273`), adequate for Go binary startup. |
| D11 | One scenario is enough and simple. | The orchestration **happy path is genuinely simple to assert** once stubs record calls — but the **address-injection plumbing (D4) is the real complexity**, not the assertions. Risk concentrates in execute.py wiring, not in the suite logic. |

---

## B. FR → file/function mapping

| FR | File(s) / function(s) | Notes |
|----|------------------------|-------|
| **FR-CO-EXEC (#1, riskiest)** | **`behavioral/execute.py`** — new checkout branch in `run_behavioral_cell`: bind 6 stubs (`checkout_stubs.py`) → read runtime ports → build `*_SERVICE_ADDR` map → merge into `extra_env` **before** `run_service_sandboxed` → `partial`-bind `stub_calls`/`ground_truth` into the suite fn → tear down stubs in `finally`. | The **complexity locus / top risk**. The shipped `client(port)` (`sandbox.py:335`) contract is insufficient; this is the only structural divergence from the 8 leaf suites. Keep it a thin branch delegating to the existing sandbox path. |
| FR-CO-1,4,5,6 | **NEW** `behavioral/checkout_stubs.py` — `DependencyStubHarness` with 6 servicer **subclasses** + a `GroundTruth` fixture dataclass. | **Subclass** the **existing** `demo_pb2_grpc.*ServiceServicer` (D3, no codegen); return `demo_pb2.*` messages from the fixture. |
| FR-CO-2,3,8 | `checkout_stubs.py` — `start()` binds 6 `grpc.server` on `127.0.0.1:0`, returns `{env_name: addr}` + exposes `.calls` counters; `stop()` in a context manager. | In-process Python (D2); `concurrent.futures.ThreadPoolExecutor`; `server.stop(grace=1.0)`. Call-counters mandatory (FR-CO-8). |
| FR-CO-7,8 | **NEW** `behavioral/checkout_suite.py` — `run_checkout_suite(port, *, stub_calls, ground_truth, host, connect_timeout) -> SuiteResult`. Reuses `RpcResult`/`SuiteResult` from `charge_suite`. | Connects `CheckoutServiceStub`, sends one `PlaceOrderRequest`, scores 6 steps using response fields + **mandatory** `stub_calls` counters (payment/email observable only via counters). |
| FR-CO-9,10 | `seed-checkoutservice.json` `startup` block (cmd → **existing** `_go_default` `./.bin/server`, `port_env`, `readiness` + declared dep-env **names**) **+** the FR-CO-EXEC branch fills the values. | **B1 gating prereq.** Seed has NO `startup` block today (re-author). Go launcher **already exists** (`contract.py:_go_default`), not built; address values runtime-injected (D4). |
| FR-CO-11 | `provision.py` (Go path, unchanged) + `setup_go_stubs` — exercised for real for checkout. | No code change expected; this is a *validation* step (e2e gated test). |
| FR-CO-12,13 | **NEW** `tests/unit/benchmark_matrix/behavioral/test_checkout_e2e_go.py` (gated, mirrors `test_pricing_e2e_node.py`) + fixtures `reference_checkout.go` (correct) and `broken_checkout.go`. | Gated on `go` on PATH + vendored go stubs. |
| FR-CO-14,15 | `execute.py:_SUITES["checkoutservice"]` (+ the D5 branch). No `_PROTO_BY_SERVICE` change (D6). No scoring change (folds through `compute_composite`/`aggregate.py`). | |
| FR-CO-16,17,18 | `execute.py` `run_behavioral_cell` — reuse existing degrade returns; the checkout branch maps "stub never dialed" to a **failed step (real miss)**, launch failure to **degrade**, off-contract dep to the existing R3-F3 floor. | Mostly reuse; one new mapping (stub-not-dialed → step fail, not degrade). |
| FR-CO-19,20 | `execute.py` provenance dict (add `deps_dialed`, `dep_addrs`, per-step) + scorecard renderer (the pricing-lane "where models differentiate" view). | Provenance extension is additive. |

---

## C. Sequenced steps (each a decision gate for the next)

> **Ordering rationale (v0.2).** The **execute.py orchestration branch (S1, the #1 step)** is the
> complexity locus and top risk, so it leads the design — but it has a **hard prerequisite**: the
> re-authored seed (S0/B1) must first define the `startup` block + dep-env **names** that the branch
> fills. S0 and S1 are therefore co-defined (one contract, two halves). The pure-Python stub-harness
> and suite (S2/S3) de-risk the *assertion* logic in isolation and feed back into S1's `partial`-bind.

0. **S0 — Seed re-authoring (B1, GATING PREREQUISITE)** (`seed-checkoutservice.json`). The seed has
   **no `startup` block today** — add one: `cmd` → the **existing** `_go_default` `./.bin/server`,
   `port_env: "PORT"`, `readiness: "tcp"`, **plus the six declared `*_SERVICE_ADDR` env names**. Its
   env-name contract is **co-defined with S1**. Nothing can run behaviorally until this lands. (FR-CO-9,10)
1. **S1 — execute.py orchestration branch (THE #1 STEP, riskiest)** (the D5 branch, FR-CO-EXEC).
   `run_behavioral_cell` detects `checkoutservice`: bind the 6 stubs (S2), read runtime ports, build the
   `*_SERVICE_ADDR` env, **merge into `extra_env` before `run_service_sandboxed` launches the SUT**,
   `partial`-bind those + `stub_calls`/`ground_truth` into the suite fn (S3), then **tear down all 6
   stubs in `finally`**. Map degrade vs real-miss vs model-fault (FR-CO-16..18); provenance extension
   (FR-CO-19). This is the single structural divergence from the leaf suites — keep it thin (bind →
   inject → `partial` → delegate to the existing sandbox path). (FR-CO-EXEC, FR-CO-9..11,14..19)
2. **S2 — Ground-truth fixture + stub harness** (`checkout_stubs.py`). 6 in-process servicer
   **subclasses** + a `GroundTruth` fixture + **mandatory** call counters + context-manager lifecycle.
   Unit-tested **standalone**: start harness, dial each servicer directly with a `*ServiceStub`, assert
   fixed responses + counters. Pure Python, no Go, always runs. (FR-CO-1..6,8)
3. **S3 — Checkout suite** (`checkout_suite.py`). `run_checkout_suite` drives one `PlaceOrder` against a
   live CheckoutService, scores the 6 steps from the response + **mandatory** `stub_calls` counters.
   Unit-tested against an **in-process Python reference CheckoutService** (mirrors `test_pricing_suite.py`'s
   in-process oracle): correct checkout → 1.00; a checkout skipping payment → step 5 fails only. Pure
   Python, always runs. (FR-CO-7,8)
4. **S4 — Go reference checkouts (B3, real authoring cost)** — fixtures `reference_checkout.go` (a
   correct 6-way orchestrator) and `broken_checkout.go`. Writing a correct Go orchestrator is non-trivial
   but is a one-time committed fixture (and doubles as the SDK's "this is buildable" proof). (FR-CO-12,13)
5. **S5 — Stub-harness self-validation** (gated e2e). `reference_checkout.go` → 1.00 (proves the whole
   path: provision → go build → sandbox loopback → stubs → suite → S1 branch); `broken_checkout.go` →
   fails the right steps (proves per-step attribution + address injection). (FR-CO-12,13)
6. **S6 — Registration + scorecard** (`_SUITES` key — **no `_PROTO_BY_SERVICE` change**, D6; "integration
   frontier" scorecard sub-section). Mechanical, last. (FR-CO-14,20)

**Test strategy:** S2/S3 are pure-Python in-process (no Go, fast, always run) and de-risk the assertion
logic before S1's branch is fully wired. S5 is the only Go-gated e2e (skips without `go` + vendored
stubs), mirroring the shipped `test_pricing_e2e_node.py` pattern.

---

## D. Latent blockers / risks (ranked — #1 first)

- **R1 / #1 RISK (design, the complexity locus) — execute.py needs a dedicated checkout branch (D5,
  FR-CO-EXEC).** The leaf-suite `client(port)` contract is **insufficient**: 6 stubs must come up and
  their `*_SERVICE_ADDR` addresses must be runtime-injected into `extra_env` **before** the SUT starts,
  then torn down. This is the **single structural divergence** from the 8 shipped suites and where all
  the risk concentrates (the assertions are easy by comparison). Mitigation: keep it a thin branch
  (bind → inject → `partial` → delegate to the existing sandbox path) to avoid a parallel code path.
- **B1 (GATING PREREQUISITE — must land before R1 can run) — seed has no startup block (D7).** Checkout
  cannot run behaviorally until the seed is re-authored (S0). Its env-name contract is **co-defined
  with R1** (the branch fills the names the seed declares). Cheap to author, but it gates S5 and any real
  run.
- **B3 (real authoring cost) — Go reference checkout must exist and be correct.** Without a known-good
  `reference_checkout.go` (a real 6-way orchestrator), FR-CO-12 can't prove the stubs. Writing a correct
  Go orchestrator is **non-trivial** — a genuine authoring cost — but it is a one-time committed fixture
  (and doubles as the SDK's "this is buildable" proof).
- **B4 (port races).** Six stubs + one SUT = 7 ephemeral ports per cell. Bind stubs first, read their
  bound ports, then allocate the SUT port — reuse `_free_port()`; accept the small TOCTOU window the
  shipped harness already tolerates.
- **B5 (cost).** A real grid run is gated by `BudgetGuard` (parent FR-X4-RERUN); this plan delivers the
  **suite + harness + gated self-validation** ($0, no LLM). A scored run is a separate funded step.

*Simplifications confirmed by the discoveries table (no longer risks): the **Go launcher already
exists** (D1, reuse not build), the **6 servicers already exist** (D3, subclass not codegen), stubs are
**in-process Python** on loopback (D2, no sibling-process orchestration), and checkout uses the **shared
`demo.proto`** (D6, no `_PROTO_BY_SERVICE` change).*

---

*v0.2. Build order S0→S6, with the **seed re-author (S0/B1) as the gating prerequisite** for the
**execute.py orchestration branch (S1, the #1 step and #1 risk)**; S2/S3 de-risk the assertion logic
in pure Python; S4 pays the real Go reference-checkout authoring cost (B3) before the Go-gated e2e (S5).
The discoveries table (esp. D2 in-process loopback stubs, D4 runtime address injection, D5 execute.py
branch) is what makes this plannable — the scope doc under-specified where the complexity actually
lives (**execute.py wiring, not the assertions**).*
