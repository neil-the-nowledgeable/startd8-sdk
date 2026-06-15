# Track 2 M-T2.5 — Behavioral Expansion Scoping

**Status:** Scoping (pre-requirements) · **Date:** 2026-06-15 · **Owner area:** `startd8.benchmark_matrix.behavioral`
**Predecessor:** the paymentservice pilot (M-T2.1–M-T2.4) — behavior *discriminated* the flagships
(Opus 1.00 validates cards vs gpt-5.5/gemini 0.33 lenient mocks), so expansion is justified.
**Purpose:** frame the work to go from **1 service / 1 language / 1 RPC** → the full benchmark, and
surface the decisions before writing requirements. Not a commitment to "all 9 × 5 languages."

---

## 1. What the pilot already gives us (reusable, in `main`)
Sandbox service primitive (secure loopback fixed), startup contract + **Node** serve hook, dependency
**closure vendoring**, proto-path multiplexing, composite functional term, **persist-then-$0-rescore**
loop, degrade-not-zero discipline. The execution *machinery* is proven; expansion is mostly
**breadth** (more suites, more languages, more dependency/state handling), not new machinery.

## 2. The benchmark surface (grounded in the seeds)

| Service | Lang | RPCs | State / deps | Difficulty |
|---|---|---|---|---|
| paymentservice | node | Charge | none | ✅ done (pilot) |
| shippingservice | go | GetQuote, ShipOrder | none (pure compute) | **easy** |
| adservice | java | GetAds | none (static ads) | **easy** (but Java serve hook) |
| currencyservice | node | GetSupportedCurrencies, Convert | ECB rates **data file** (pinnable) | easy–med |
| productcatalogservice | go | ListProducts, GetProduct, SearchProducts | products.json **data file** (pinnable) | med |
| cartservice | csharp | AddItem, GetCart, EmptyCart | **Redis** (stateful across calls) | hard (state + C#) |
| recommendationservice | python | ListRecommendations | **calls catalog** (1 downstream) | hard (downstream) |
| emailservice | python | SendOrderConfirmation | Jinja2 template; side-effecty (sends/logs) | med (weak ground truth) |
| checkoutservice | go | PlaceOrder | **calls 6 services** (orchestration) | **hardest** |

Languages needing a serve hook beyond Node: **Go (3), Python (2), C# (1), Java (1).**

## 3. Scope dimensions (what expansion actually requires)

- **D1 — Generalized dependency provisioning (the #1 prerequisite, OQ-T2-5).** Even within *one* Node
  service we hit pino → uuid → pino-pretty by hand. That doesn't scale. Need: install each cell's
  **declared** deps (`package.json`/`go.mod`/`requirements.txt`/`*.csproj`) at **prepare time**
  (network allowed, before the no-egress sandbox), plus a curated common set. Until D1 exists, every
  new service is whack-a-mole.
- **D2 — Per-language serve hooks + gRPC runtime.** Go (`go run`/build + module cache), Python
  (`python server.py` + pip + grpcio), C# (`dotnet run` + restore), Java (gradle/`java` + grpc-java).
  Heavier than Node; C#/Java involve a compile/restore step inside prepare.
- **D3 — Per-service SDK-authored suites.** Ground-truth client per RPC (~18 RPCs). The hard part is
  *defining correct behavior* — some RPCs have crisp truth (Charge validation, shipping quote
  formula, currency conversion math), some are weak (email "sends" — observable only as a logged
  side effect), some saturate (a GetAds that returns *any* ad may be "correct").
- **D4 — Stateful services (NR-T2-3, was deferred).** cart needs Redis (real ephemeral vs in-mem
  mock); catalog/currency need pinned data files; suites must exercise state across calls.
- **D5 — Orchestration (checkout).** PlaceOrder calls 6 services — needs them running or mocked.
  This is a different-magnitude harness (multi-service compose). Strong candidate to **defer** or
  test against stubbed downstreams only.
- **D6 — Startup contracts for all seeds** (per service/language) → a benchmark **re-gen**.
- **D7 — Composite weighting decision (OQ-F4).** Once coverage is broad, does functional *replace*
  structural as primary, or stay a weighted term? Revisit `FUNCTIONAL_WEIGHT`.

## 4. Proposed phasing (smallest valuable increments first)

- **P1 — Dependency provisioning (D1).** Prepare-time install of declared deps + common set; honest
  degrade naming the missing module (already partial). *Unblocks everything; pure infra, $0.*
- **P2 — Stateless breadth across languages (D2+D3, no state).** shipping (Go), ad (Java), currency
  (Node, pinned ECB). Proves behavioral scoring works **polyglot**, cheaply. Adds Go+Java serve hooks.
- **P3 — Data-file-stateful (D4 light).** catalog (Go, pinned products.json). Read-only state.
- **P4 — Real-stateful + Python (D2+D4).** cart (C#, ephemeral Redis/mock), email/recommendation
  (Python; recommendation mocks catalog). Weak-ground-truth RPCs flagged.
- **P5 — Orchestration (D5).** checkout against stubbed downstreams — or **defer** pending P1–P4 value.
- **P6 — Full run + composite decision (D6+D7).** Startup contracts for all seeds, full Round-1
  generation, fold functional weighting decision.

Each phase is **pilot-then-expand**: run one service once to confirm its RPCs *discriminate* before
funding N reps × roster — some RPCs will saturate (like structural did) and aren't worth the spend.

## 5. Cost & the strategic question
Generation is the only real $ (full Round-1 ≈ 10×9×5 = **450 cells, ~$150–200, one-time**); behavioral
scoring is **$0 and re-runnable** (persist-then-rescore). So expansion cost is mostly **SDK
suite-authoring + per-language harness effort**, not LLM spend.

**Decision for the user:** the goal isn't necessarily *all 9 services*. The pilot discriminated on a
**single** validation-heavy RPC. A **curated set of discriminating RPCs** (validation/correctness-rich,
pure where possible) likely yields most of the ranking signal at a fraction of the effort. Recommend:
do **P1 + P2** (polyglot stateless breadth), measure how many RPCs actually discriminate, then decide
whether stateful/orchestration (P3–P5) are worth it — rather than committing to full coverage up front.

## 6. Open questions
- **OQ-M5-1** Dep provisioning: per-cell declared-dep install vs per-service vendored closures (D1).
- **OQ-M5-2** Stateful strategy: real ephemeral Redis vs in-mem mock vs skip stateful (D4).
- **OQ-M5-3** Checkout: stub the 6 downstreams, run-all, or defer (D5)?
- **OQ-M5-4** Weak-ground-truth RPCs (email side effects, "any ad" GetAds) — score behaviorally or
  leave on structural+compile? (avoid rewarding verbosity, the Track 1 failure mode).
- **OQ-M5-5** Curated-discriminating-subset vs full-coverage (the §5 decision).
- **OQ-M5-6** Composite: functional-as-primary vs weighted term once coverage is broad (D7/OQ-F4).

---

*Scoping only — no requirements committed yet. Next: run `/reflective-requirements` on the chosen
phase set (recommend P1+P2), then CRP. The expansion is breadth over proven machinery; the real risk
is scope (all-9 vs curated) and weak-ground-truth RPCs, not the harness.*
