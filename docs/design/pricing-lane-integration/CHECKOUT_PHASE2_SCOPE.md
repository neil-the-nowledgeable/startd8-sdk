# Phase 2 Scope — Checkout Orchestrator Behavioral Suite

**Version:** 0.1 (Scope only — no implementation)
**Date:** 2026-06-23
**Status:** Scoping
**Parent:** `docs/design/benchmark-scoring/FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md` (FR-X4)

---

## Why this is separate from Phase 1

Phase 1 (the pricing lane) was *surfacing an already-built, already-running* discriminator — a
scorecard change reading persisted data. The checkout orchestrator is the opposite: **net-new code**
with no suite, no startup contract, and a hard architectural problem (a service that only behaves
correctly when six dependencies answer). It is the Track-2 "integration frontier" and deserves its
own reflective-requirements pass before any build. This document scopes it; it does **not** specify
the implementation.

## Verified current state (the gap)

- **No `checkout_suite.py`.** `_SUITES` (`behavioral/execute.py:34-43`) has 8 entries; checkout is
  not one. `checkoutservice` appears only in proto stubs (`demo_pb2_grpc.py`) + `contamination.py`.
- **`seed-checkoutservice.json` has no `startup` block** → a behavioral re-run is impossible until
  one is authored (Expansion-Reqs E2).
- **`checkoutservice.PlaceOrder` is a 6-way orchestrator** (deps: productcatalog, cart, currency,
  shipping, payment, email) — it cannot run as a leaf (Expansion-Reqs E4).
- Language is **Go** (Expansion-Reqs E6) — exercises the Go serve hook + offline provisioning that
  the shipped Node/Python suites don't.

## Scope (what a Phase 2 build must deliver)

| ID | Item | Note |
|----|------|------|
| C-1 | **SDK-authored loopback dependency stubs** for the 6 deps, each returning **fixed ground-truth** responses for the suite's `PlaceOrder` inputs. | Per FR-X4-STUB. Stubs are SDK code, **never** other models' generated services (NR-X2 — would confound the score). |
| C-2 | **`startup` contract** for `seed-checkoutservice.json` injecting the stubs' loopback addresses via the real OB env convention (`PRODUCT_CATALOG_SERVICE_ADDR`, etc.). A checkout that ignores them and dials elsewhere fails to connect → real behavioral miss, not a degrade. | Per FR-X4-STUB. |
| C-3 | **Per-step PlaceOrder ground truth** — partial coverage so a checkout that skips a dependency (e.g. never calls payment, never sends email) scores partial, not all-or-nothing. | Per FR-X4-COVERAGE. |
| C-4 | **Stub-harness self-validation** against a known-good reference checkout — proves the stubs are correct before any model is judged against them. | Per FR-X4-STUBVERIFY. |
| C-5 | **Go serve launcher + offline provisioning** exercised for real (the shipped `resolve_serve_command` Go default + proto placement). | Per FR-X4-HOOK / E6. |
| C-6 | **`_SUITES` + `_PROTO_BY_SERVICE` registration** for `checkoutservice` once C-1..C-5 exist. | Mechanical, last. |

## Open questions for the Phase 2 reflective pass

- **CQ-1** — Weight per-step coverage (payment correctness > email-sent), or equal-weight steps?
  (Expansion-Reqs OQ-X6.)
- **CQ-2** — Do the stubs need to assert the checkout *called them correctly* (request-shape checks),
  or only return canned responses and let the final `PlaceOrder` response carry the verdict?
- **CQ-3** — Is one orchestration scenario (happy-path PlaceOrder) enough for v1, or do we need
  failure-injection (a stub returns an error → does checkout handle it)?
- **CQ-4** — Scorecard: does the orchestrator get its own discriminator section, or fold into the
  pricing-lane "where models differentiate" view as a second hard lane?

## Non-scope (Phase 2)

- No full multi-service Online Boutique deployment (the benchmark stays per-cell isolated — stubs,
  not real generated dependencies). This is the standing Track-2 boundary, reaffirmed.
- No generation-path changes.

---

*Scope 0.1 — feeds a future `/reflective-requirements` pass. Not yet planned or built.*
