# Functional-Correctness Track 2 — All-Service Expansion (M-T2.5) — Implementation Plan

**Version:** 0.1 (paired with expansion requirements v0.1)
**Date:** 2026-06-19
**Status:** Plan — build Tier A first (cheapest, proves state provisioning); CRP R1 before code.

> Grounded in the shipped `behavioral/execute.py` (_SUITES, provisioning, port detection),
> `behavioral/contract.py` (resolve_serve_command), `provision.py`, `scoring.py`/`aggregate.py`
> (functional fold-in), and the 12 seeds. Milestones map 1:1 to M-X.0..M-X.4.

## Approach

Build **bottom-up by statefulness**, cheapest-and-lowest-risk first, and spend LLM budget last. Each
tier is fixture-tested against an SDK reference server (the R2-S3 discipline) **before** any model
output is scored, and each tier's discrimination result gates funding the next. The full re-run
(M-X.4) is the only budget spend and runs only after every suite + the stub harness is proven on
fixtures. Reuse the shipped scoring/aggregation/persistence/port-detection wholesale — this milestone
adds **suites + state fixtures + a dependency-stub harness + seed startup contracts**, not new scoring.

## Milestones

### M-X.0 — Roster lock + per-service ground-truth design (no code)
- Fix the tier order (FR-X1) and, per service, decide the state mechanism (FR-X3-STATE) and the exact
  ground-truth assertions. Write each service's oracle as a short table (RPC → fixed input → asserted
  output) reviewed before coding — the suite is only as good as its oracle.
- *Output:* a per-service oracle table appended here; OQ-X1/X5 resolved.

### M-X.1 — Tier A: stateful single-service suites (fixture-tested, no LLM)
- **productcatalogservice** (seeded state): commit a fixed `products.json`; provision it at the
  conventional paths (extend the FR-T2-PROTO multi-path provisioning to data files); author
  `run_catalog_suite` asserting `ListProducts` count/ids, `GetProduct(id)` fields, `SearchProducts`
  hits against the known catalog. Register in `_SUITES`.
- **cartservice** (drive-and-verify): author `run_cart_suite` — `AddItem`×2 → `GetCart` returns both
  with summed quantities → `EmptyCart` → `GetCart` empty. Self-cleaning (FR-X3-ISO). Register in `_SUITES`.
- *Files:* `behavioral/{catalog_suite,cart_suite}.py`, `behavioral/fixtures/products.json`, `_SUITES`
  + state-fixture provisioning in `execute.prepare_*`/`provision.py`.
- *Tests:* each suite vs a committed **reference** server → coverage 1.00; vs a **known-broken** one
  (catalog: wrong price; cart: drops the 2nd item) → fails exactly those checks (R2-S3 discipline). C#
  cart + Go catalog launchers exercised (or degrade honestly if the toolchain is absent).

### M-X.2 — Tier B: single-dependency suite (recommendationservice)
- SDK **productcatalog stub** (the first dependency stub — reused by M-X.3): a minimal server returning
  a fixed product list. Launch recommendationservice with the stub's loopback addr injected per its
  startup contract. `run_recommendation_suite`: `ListRecommendations(product_ids)` returns valid ids
  from the catalog, excluding the inputs, count within contract bounds.
- *Files:* `behavioral/stubs/` (catalog stub), `behavioral/recommendation_suite.py`, `_SUITES`.
- *Tests:* reference recommendation server → 1.00; broken (returns the input ids / out-of-catalog ids)
  → fails the right checks.

### M-X.3 — Tier C: orchestrator (checkoutservice) + dependency-stub harness (the frontier)
- Generalize M-X.2's stub into a **configurable multi-RPC dependency stub** (FR-X4-STUB) serving fixed
  ground-truth for catalog/cart/currency/shipping/payment/email. One stub process, six servicers.
- Launch the generated checkout with all six stub loopback addresses injected (FR-X4-ADDR). `run_checkout_suite`
  drives `PlaceOrder` and asserts the orchestration contract (FR-X4-ASSERT): total = Σ(price×qty)+shipping
  converted, non-empty tracking_id, transaction_id, email-called — **per-step coverage**.
- *Files:* `behavioral/stubs/dependency_stub.py`, `behavioral/checkout_suite.py`, `_SUITES`.
- *Tests (FR-X4-STUBVERIFY):* reference checkout vs the stub harness → 1.00; broken checkouts (skips
  payment / mis-sums total / drops shipping) → fail exactly the right steps. No model output yet.

### M-X.4 — Seeds + full re-run (spends budget) + decision
- Add `startup` blocks to all 5 expansion seeds (cmd/`$PORT`/readiness; checkout's dependency-addr env).
  Record each stateful service's state mechanism in its seed (FR-X6-CONTRACT).
- Decide the re-run inclusion set (FR-X7-SCOPE): 5 new always; the 7 existing only if their startup
  changed. Produce the fresh cost estimate (OQ-X4) and run under `BudgetGuard`, persisting per-cell
  (R3-S1) to a durable batch root; render the per-service leaderboard with the functional column (R2-S1).
- **Decision gate:** per tier, does behavior discriminate the flagships? Record saturating services;
  they don't gate the rest (FR-X2). Email cut/kept per OQ-X5.
- *Output:* the expanded Round-1 results doc + dispositions; OQ-X3/X4/X6 resolved from data.

## Risks
- **State leakage across reps (FR-X3-ISO):** a drive-and-verify suite that doesn't end empty poisons
  rep N+1. The self-cleaning + fresh-process invariant and the broken-fixture tests gate this.
- **Stub fidelity:** a stub that's too lenient lets a broken checkout pass; too strict false-fails a
  correct one. The known-good/known-broken reference tests (FR-X4-STUBVERIFY) are mandatory before any
  model scoring — same gate that kept the leaf suites honest.
- **Polyglot launcher gaps (E6):** C#/Go offline launch + provisioning is unproven at this scale; a
  genuine toolchain gap must **degrade with the reason**, never crash or false-0 — and must be visible
  in the report (no silent all-degrade masquerading as coverage).
- **Re-spend (FR-X7-SCOPE):** re-running the already-scored 7 without cause burns budget; the explicit
  inclusion set + report line prevents silent re-spend.
- **Orchestrator confounding (NR-X2):** if checkout's deps were *generated* (not stubbed), checkout's
  score would absorb its deps' quality. Stubs keep the signal attributable to checkout alone.

## Sequencing
M-X.0 (design, no code) → M-X.1 Tier A (fixture-tested, no LLM) → M-X.2 Tier B (stub reused) →
M-X.3 Tier C (stub harness; fixture-tested) → **per-tier gates** → M-X.4 seeds + scoped re-run (budget).

## Out of scope (this plan)
Live full-mesh OB (NR-X1); generated dependencies (NR-X2); real persistence backends (NR-X3); error-path
fault injection (NR-X4); kernel isolation (parent NR-T2-2).

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

_(none yet — awaiting CRP R1)_
