# Functional-Correctness Track 2 — All-Service Expansion (M-T2.5) — Requirements

**Version:** 0.1 (Draft — opens the milestone the pilot gate unblocked)
**Date:** 2026-06-19
**Status:** Draft — for CRP review (R1) before implementation. No code yet.
**Owner SDK area:** `startd8.benchmark_matrix.behavioral` (suites + state/dep provisioning) + seeds
**Parent:** `FUNCTIONAL_CORRECTNESS_TRACK2_BEHAVIORAL_REQUIREMENTS.md` (v0.3) — this promotes its
**NR-T2-1** (all-service expansion + full re-run) and **NR-T2-3** (stateful services) from deferred to
a buildable, milestone-decomposed spec, now that the pilot decision gate (FR-T2-PILOT) has **passed**.
**Consumers:** Summer 2026 benchmark — extend the only trustworthy frontier discriminator to the whole
Online Boutique grid.

---

## 0. Grounding Insights (from the shipped harness + the seeds, read before drafting)

> The parent shipped a 7-suite, 3-transport harness on **stateless, single-service** RPCs. Reading the
> seeds and the `demo.proto` service set surfaces the concrete realities that make expansion *different
> in kind*, not just *more of the same* — captured here so the milestones are buildable.

| # | Reality | Evidence | Impact |
|---|---------|----------|--------|
| E1 | **5 services have seeds but no behavioral suite**: `cartservice`, `productcatalogservice`, `recommendationservice`, `checkoutservice`, `emailservice`. The shipped 7 are payment/currency/shipping/ad/pricing(+rest+graphql). | `execute._SUITES` (7 keys) vs `seeds/` (12 services) | The expansion roster is these **5** — and every one is **stateful or multi-service**, unlike the shipped stateless RPCs. |
| E2 | **The remaining seeds carry NO `startup` block.** | `seed-{cart,catalog,checkout,recommendation,email}service.json` → `startup: None` | A full re-run (FR-T2-CONTRACT) is impossible until each gets a startup contract → **a re-gen is required** (already accepted at the Track-2 level, but now spans 5 more services × the roster). |
| E3 | **Stateful services need provisioned state, not just a launch.** `cartservice` depends on a store (Redis); `productcatalogservice` reads a `products.json` catalog file. | seed `dependencies` fields | The suite cannot assert correctness against an *unknown* catalog/cart. We need either SDK-provisioned **state fixtures** (a fixed `products.json`) or **drive-and-verify** RPC sequences (cart: `AddItem`→`GetCart`→`EmptyCart`). NR-T2-3 made concrete. |
| E4 | **`checkoutservice` is a 6-way orchestrator**, not a leaf service. | `seed-checkoutservice.json` deps: productcatalog, cart, currency, shipping, payment, email | A behavioral `PlaceOrder` cannot run without its dependencies. The parent's non-goal ("single service, deps mocked") now becomes a **first-class requirement**: SDK-authored **dependency stubs** the generated checkout dials over loopback. This is the integration frontier. |
| E5 | **`emailservice.SendOrderConfirmation` returns `Empty`** (a side effect: renders + "sends" an email). | `demo.proto` | Low behavioral discrimination — there's no return value to assert. Verifying it needs a **captured-output** hook (the rendered HTML) or it is **deprioritized/cut** (OQ-X5). |
| E6 | **Polyglot at last.** The 5 span C# (cart), Go (catalog, checkout), Python (recommendation, email). The shipped suites are Node + Python servers. | seed `language` fields | The run hook (`resolve_serve_command`) has Node+Go defaults; **C#/Python launchers** + their offline dep/state provisioning (`provision.py`) must be exercised for real here (FR-T2-HOOK's "others degrade" is no longer acceptable for the roster). |

---

## 1. Problem Statement

The shipped Track 2 harness discriminates frontier models on **stateless leaf RPCs** (Charge, Convert,
GetQuote, pricing math). That covers 7 of the 12 Online Boutique services. The remaining 5 — the
**stateful** (cart, catalog), **dependency-bearing** (recommendation), **orchestrating** (checkout),
and **side-effecting** (email) services — are exactly where buildability and integration correctness
(not just arithmetic) separate models, and they are currently **un-scored behaviorally**. Expanding
requires the two capabilities the parent deferred: **state provisioning** and **dependency stubbing**.

## 2. Goals & Non-Goals

**Goals:**
1. Author SDK ground-truth behavioral suites for the prioritized expansion services, with **state
   fixtures** (catalog) and **drive-and-verify** sequences (cart) so correctness is assertable.
2. A **dependency-stub harness**: SDK-authored fake dependency servers (loopback, offline) that an
   orchestrating service (`checkoutservice`) dials, so `PlaceOrder` is behaviorally testable in isolation.
3. **Startup contracts** in all expansion seeds + the **full Round-1 re-run** across the whole grid
   (service × model × repetition × tier), folding the new functional terms into the leaderboard.
4. Exercise the **C#/Go/Python** server launchers + offline provisioning for real (E6), degrading
   honestly where a toolchain is genuinely absent (FR-32).
5. Reuse — not re-build — the shipped infra: model-fault flooring (R3-F3), functional aggregation
   (R2-S1), durable per-cell persistence (R3-S1), hardcoded-port detection (R2-S2), multi-transport
   readiness, and the hardened-tier superset.

**Non-Goals:**
- Load/perf/soak testing; chaos/failure-injection of dependencies (stubs are well-behaved unless a
  case explicitly probes an error path).
- A *live full-mesh* Online Boutique (all 11 real services co-running). Orchestrator deps are
  **SDK stubs**, not generated services (NR-X2).
- Grading model-written tests; replacing the compile gate; kernel-level isolation (inherits the
  parent's NR-T2-2 — best-effort host controls, recorded honestly).
- Re-running the already-scored 7 stateless services *unless* the startup-contract change forces it
  (scope the re-gen to what actually changed — OQ-X3).

## 3. Requirements

### Roster & prioritization (M-X.0)
- **FR-X1** The expansion roster is the 5 un-suited services, **tiered by buildable discrimination
  value** (build in this order; each tier is a decision gate for the next):
  - **Tier A — self-contained state (highest value, lowest risk):** `productcatalogservice`
    (seed a fixed `products.json`; assert `ListProducts`/`GetProduct`/`SearchProducts` against it),
    `cartservice` (drive-and-verify: `AddItem`→`GetCart` returns the item; `EmptyCart` clears).
  - **Tier B — single dependency:** `recommendationservice` (`ListRecommendations` reads the catalog;
    stub the one productcatalog dependency, assert recommendations are valid product ids ≠ the input).
  - **Tier C — orchestrator (the frontier):** `checkoutservice.PlaceOrder` against the dependency-stub
    harness (FR-X4).
  - **Tier D — side-effecting (lowest value):** `emailservice` — only if a captured-output hook proves
    worthwhile; otherwise **cut** and recorded as "no behavioral suite" (honest partial coverage). (OQ-X5)
- **FR-X2** Each tier ships and is evaluated before the next is funded; a tier that does **not
  discriminate** the flagships (saturates, like the parent's premise risk) is recorded and does not
  gate the others.

### State provisioning (M-X.1) — NR-T2-3 made concrete
- **FR-X3-STATE** Stateful services get correctness-assertable state by one of two SDK-owned mechanisms,
  chosen per service and recorded in provenance:
  - **State fixture:** the harness provisions a fixed data file into the cell workdir at the
    conventional path(s) the server reads (e.g. `products.json` — same multi-path discipline as
    FR-T2-PROTO), and the suite asserts against that known data. Best-effort + self-reporting: a server
    that can't find/load it **degrades** with the path named (FR-T2-2), never a false 0.
  - **Drive-and-verify:** the suite establishes state through the service's own RPCs and asserts the
    round-trip (cart: add two items → `GetCart` returns both with correct quantities → `EmptyCart` →
    `GetCart` empty). No external store assumed; if the impl hard-requires one (e.g. Redis) and it's
    absent, that is **infra** (degrade) unless the dep is off-contract (then model-fault floor, R3-F3).
- **FR-X3-ISO** State must not leak across cells/reps: each cell gets a fresh workdir + fresh server
  process (already guaranteed by `run_service_sandboxed` teardown); drive-and-verify suites must also
  be **self-cleaning within a run** (end empty) so repetition N+1 sees no residue from N.

### Dependency-stub harness (M-X.2) — the orchestrator frontier
- **FR-X4-STUB** An SDK-authored, **offline, loopback** dependency-stub harness: minimal fake servers
  for the dependencies a `checkoutservice.PlaceOrder` calls (productcatalog, cart, currency, shipping,
  payment, email), each returning **fixed ground-truth responses** for the suite's PlaceOrder inputs.
  The generated checkout is launched with the stubs' loopback addresses injected via its startup
  contract (env/flags), exactly as it would receive real service addresses.
- **FR-X4-ADDR** Dependency addresses are injected the way the startup contract specifies (env vars per
  the real OB convention, e.g. `PRODUCT_CATALOG_SERVICE_ADDR`); a checkout that ignores them and
  hardcodes/invents addresses **degrades** (can't reach the stubs) unless it reached for an off-contract
  transport (model-fault floor). Detection mirrors R2-S2's port handling.
- **FR-X4-ASSERT** The `PlaceOrder` suite asserts the **orchestration contract**, not the leaf math:
  the order total = Σ(catalog prices × cart quantities) converted + shipping, a non-empty
  `order.tracking_id` (shipping called), a charged `transaction_id` (payment called), and a confirmation
  path (email called). Per-step coverage so a checkout that skips one dependency scores partial.
- **FR-X4-STUBVERIFY** The stub harness is itself validated against a **known-good reference checkout**
  (committed fixture) → coverage 1.00, and a **known-broken one** → fails the right steps (the R2-S3
  discipline, generalized to orchestration).

### Launchers & provisioning for the roster languages (M-X.3)
- **FR-X5-LANG** `resolve_serve_command` + `provision.py` must launch and offline-provision **C#**
  (cartservice), **Go** (catalog, checkout), and **Python** (recommendation, email) servers for real.
  Where a secure offline launcher genuinely cannot be built (e.g. a toolchain needing network), the
  cell **degrades** with the reason named — never crashes, never false-0 (FR-T2-2 / FR-T2-HOOK).
- **FR-X5-DEPS** Each service's full offline dependency closure is provisioned at prepare time (the
  FR-T2-DEPS discipline extended): catalog's data file, recommendation's catalog client, email's
  templating lib, checkout's gRPC client stubs. Missing protocol/infra dep → degrade; off-contract
  framework → model-fault floor (R3-F3, already shipped).

### Startup contracts + full re-run (M-X.4)
- **FR-X6-CONTRACT** Add a `startup` block to each expansion seed (cmd, port/`$PORT`, readiness mode,
  dependency-address env for checkout). For stateful services, record the state-provisioning mechanism
  (FR-X3-STATE) in the seed so the harness provisions deterministically.
- **FR-X7-RERUN** Execute the **full Round-1 grid** for the expansion roster × the flagship roster × N
  × tier, under the fail-closed budget (`BudgetGuard`), persisting per-cell atomically (R3-S1) to a
  durable batch root, and rendering the leaderboard with the functional column (R2-S1) per service.
- **FR-X7-SCOPE** Re-run **only what the contract change touched**: the 5 new services always; the
  existing 7 **only if** their seeds gained/changed a `startup` block (else their prior cells stand —
  Mottainai, don't re-spend). State the inclusion set explicitly in the run report (no silent re-spend).

### Reuse & provenance (cross-cutting)
- **FR-X8-REUSE** No new scoring path: the functional coverage from every new suite folds through the
  **existing** `compute_composite` (gates floor first; model-fault floors; degrade-not-zero) and
  aggregates through the **existing** `aggregate.py` functional terms. No parallel scoring logic.
- **FR-X9-PROV** Every expansion cell records (FR-T2-PROV, extended): suite version, per-step coverage,
  **state mechanism + fixture path** (stateful), **dependency-stub addresses + which deps were actually
  dialed** (orchestrator), isolation level, and available-vs-degraded-vs-model-fault — persisted per
  FR-T2-PERSIST.

## 4. Non-Requirements / Deferred
- **NR-X1** Live full-mesh OB (all real services co-running) — stubs only; full mesh is a separate
  integration-benchmark spec if ever justified.
- **NR-X2** Generated dependencies for the orchestrator — checkout's deps are **SDK stubs**, never other
  models' generated services (that would confound checkout's score with its deps' quality).
- **NR-X3** Stateful **persistence backends** (real Redis/DB) — drive-and-verify or in-process state
  only; a service that hard-requires an external store and can't run without one degrades (recorded).
- **NR-X4** Error-path / fault-injection suites (timeouts, partial failures) — the stubs are well-behaved
  in v1; adversarial dependency behavior is a follow-up.

## 5. Open Questions
- **OQ-X1** Tier A first service — catalog (pure seeded-state, cleanest) vs cart (drive-and-verify,
  proves the stateful pattern). Lean **catalog first** (lower risk), cart second (proves drive-and-verify).
- **OQ-X2** Dependency stubs: one reusable multi-RPC stub server vs per-dependency stubs. Lean a single
  configurable stub that serves all six dependency RPCs with fixed responses (less to maintain).
- **OQ-X3** Re-gen scope: does adding a `startup` block to the *already-scored 7* invalidate their
  cells? If the block is purely additive and the prior cells were scored without it, decide whether to
  re-run them for consistency or keep them (FR-X7-SCOPE). Lean **keep** unless the launch path changed.
- **OQ-X4** Full-grid cost at N=5 across 12 services × roster (parent estimated ~$150–200 for the
  original grid; the 5 new + any re-run changes this) — produce a fresh estimate before FR-X7.
- **OQ-X5** Is `emailservice` worth a suite at all (E5 — `Empty` return)? A captured-output hook (assert
  the rendered confirmation contains the order id/total) vs cutting it. Lean **cut** unless the hook is cheap.
- **OQ-X6** Should checkout's per-step coverage **weight** steps (e.g. payment correctness > email
  called), or treat each dialed dependency equally? Lean equal-weight for v1, revisit if it doesn't
  discriminate.

---

*v0.1 — Draft opening M-T2.5. The pilot gate passed; the expansion's novelty over the shipped harness is
**state provisioning** (FR-X3) and **dependency stubbing** (FR-X4), not more leaf-RPC suites. Tiered so a
non-discriminating service never gates the rest, and scoped so the re-run doesn't re-spend on the 7
already scored. Ready for CRP R1.*

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
