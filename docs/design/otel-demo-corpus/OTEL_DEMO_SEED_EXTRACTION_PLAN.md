# OpenTelemetry Demo — Benchmark Seed-Extraction Plan

**Version:** 1.0 (Draft)
**Date:** 2026-06-17
**Tracks:** a second benchmark corpus alongside Online Boutique (OB)
**Mirrors:** `scripts/gen_ob_benchmark_seeds.py` → new `scripts/gen_otel_benchmark_seeds.py`
**Related:** `docs/design/model-benchmark/`, [[project_summer2026_model_benchmark]],
[[reference_edge_brains_contamination_probe]] (FR-47)

---

## 1. Goal & scope

Add the **OpenTelemetry Demo** ("Astronomy Shop", `open-telemetry/opentelemetry-demo`, Apache-2.0) as
a second benchmark corpus. It is the closest possible profile match to OB — it is *descended from* OB
(same `// Copyright 2020 Google LLC` proto header), uses a **single shared `pb/demo.proto`**, and has
the same per-service "implement one gRPC service from the contract" shape — but it covers **all five
SDK languages with real services** and adds genuinely new tasks. The deliverable is a seed generator
that emits seeds **byte-schema-identical** to the OB seeds so the existing
`benchmark_matrix` runner/scorer and `run_jetson_lane.py` consume them with **zero code changes**.

**In scope:** the gRPC services whose language is one of the 5 covered (Python, Go, Node.js, Java, C#).
**Out of scope (v1):** non-covered languages (currency=C++, email=Ruby, shipping=Rust,
fraud-detection=Kotlin, quote=PHP), non-gRPC services (accounting=Kafka consumer), the UI (frontend=TS),
and the new AI/flag services that don't fit the deterministic-RPC profile (see §5).

---

## 2. Source facts (verified 2026-06-17)

- Proto: `pb/demo.proto`, **package `oteldemo`**, 354 lines, Apache-2.0 header preserved.
  **sha256 `712594c1e1a144c2211ff0695d8db05864b4ddccfad2e9862cadff8ce311225f`** (pin like OB's
  `proto_sha256`).
- Services in the proto: Cart, Recommendation, ProductCatalog, **ProductReview (new)**, Shipping,
  Currency, Payment, Email, Checkout, Ad, **FeatureFlag (new)**.
- For shared services the **RPCs are identical to OB** (CartService=AddItem/GetCart/EmptyCart;
  ProductCatalog=ListProducts/GetProduct/SearchProducts; Recommendation=ListRecommendations;
  Payment=Charge; Checkout=PlaceOrder; Ad=GetAds) — so OB's curated `SERVICES` mapping mostly transfers.

### Covered-service inventory (the v1 seed set)

| Service dir | proto_service | lang | RPCs | target_file (confirm exact) | notes |
|---|---|---|---|---|---|
| `src/checkout` | CheckoutService | go | PlaceOrder | `src/checkout/main.go` ✅ | orchestrator; many deps |
| `src/product-catalog` | ProductCatalogService | go | ListProducts, GetProduct, SearchProducts | `src/product-catalog/main.go` ✅ | leaf |
| `src/recommendation` | RecommendationService | python | ListRecommendations | `src/recommendation/recommendation_server.py` ✅ | depends on product-catalog |
| `src/product-reviews` | ProductReviewService | python | GetProductReviews, GetAverageProductReviewScore | `src/product-reviews/product_reviews_server.py` ✅ | **NEW vs OB**; has a DB dep; **omit `AskProductAIAssistant`** (§5) |
| `src/cart` | CartService | csharp | AddItem, GetCart, EmptyCart | `src/cart/src/services/CartService.cs` (confirm) | Valkey/Redis dep |
| `src/ad` | AdService | java | GetAds | `src/ad/src/main/java/oteldemo/AdService.java` (confirm) | Gradle |
| `src/payment` | PaymentService | nodejs | Charge | `src/payment/charge.js` (confirm vs index.js) | leaf |

**Spread:** 2 Go · 2 Python · 1 C# · 1 Java · 1 Node — notably **bolsters Java + C#** (OB has only
one thin service each) and adds a **second Python** task that is *new* (product-reviews), not a
restatement of an OB service.

---

## 3. What transfers from `gen_ob_benchmark_seeds.py` vs what changes

The OB generator (251 lines) is a **curated `SERVICES` list + proto embed**, not an auto-parser. Reuse
its shape verbatim; change only the data.

| Element | OB | OTel change |
|---|---|---|
| Seed schema (`schema_version`, `service_metadata`, `startup`, `tasks`, `_task_description`, `_requirements_text`) | — | **Keep identical** (schema parity is the whole point) |
| Proto file | `seeds/demo.proto` (hipstershop) | vendor `seeds-otel/demo.proto` (oteldemo), new sha256 |
| `_requirements_text` header strings | "Online Boutique … package hipstershop" | "OpenTelemetry Demo … package oteldemo" + correct attribution |
| `SERVICES` list | 9 OB services | the 7 covered services above (new target_file paths, ProductReviewService added) |
| `target_file` paths | `src/cartservice/...` | OTel layout `src/cart/...`, `src/checkout/main.go`, … |
| `dependencies` per service | OB deps | OTel deps (cart→Valkey, recommendation→product-catalog, product-reviews→DB, checkout→many) |
| `startup` block (cmd/port_env/readiness) | OB per-service | **derive from each service's Dockerfile/README** (§5 — the hard part) |
| Output dir | `docs/design/model-benchmark/seeds/` | `docs/design/model-benchmark/seeds-otel/` + its own `seeds-index.json` |

---

## 4. Steps

1. **Vendor the proto.** Save `pb/demo.proto` → `docs/design/model-benchmark/seeds-otel/demo.proto`;
   record sha256 `712594c1…` (fail the build if it drifts, like OB).
2. **Confirm exact target_file + entrypoint per service** (4 unconfirmed: cart .cs path, ad .java
   path/package, payment charge.js-vs-index.js, product-reviews server). One `gh api contents` call each.
3. **Write `scripts/gen_otel_benchmark_seeds.py`** by copying the OB generator and swapping: the
   `SERVICES` list (table §2), the proto path/sha, the corpus name/attribution strings, the output dir.
4. **Per-service `dependencies` + `startup`.** Extract dependencies (downstream gRPC + datastores)
   and a `startup` block (serve command, port env, readiness) from each service's Dockerfile/README.
   For v1, structural-only seeds can ship with `startup` best-effort; behavioral (Track 2) needs it
   correct (§5, OQ-OT-1).
5. **Emit seeds + `seeds-otel/seeds-index.json`** (same index shape as OB: generator, proto,
   proto_sha256, per-service seed_file/seed_sha256/target_file/language).
6. **Wire selection.** The matrix/runner already takes a seeds dir/service list; point a run at
   `seeds-otel/`. No runner change expected (verify the seeds dir is a parameter, not hardcoded).
7. **Contamination probe.** Register the OTel corpus with the FR-47 perturbation/rename probe
   ([[reference_edge_brains_contamination_probe]]) — these are famous public repos; pretraining
   memorization applies exactly as it does to OB (§6).

---

## 5. Hard parts / open questions

- **OQ-OT-1 — `startup` for behavioral (Track 2).** OB seeds carry a `startup` block
  (`cmd`/`port_env`/`readiness`) the behavioral harness uses to boot the generated server. OTel
  services boot differently per language (Gradle for ad, dotnet for cart, node for payment, go run for
  checkout/product-catalog, python for recommendation/product-reviews). v1 can ship **structural-only**
  seeds and defer behavioral until each `startup` is derived + verified. Decide: structural-first, or
  block on full startup.
- **OQ-OT-2 — `product-reviews` realism.** It's new (good — less OB-overlap) but (a) depends on a
  **database** and (b) its `AskProductAIAssistant` RPC calls the `llm` service. **Plan:** include
  ProductReviewService but **omit `AskProductAIAssistant`** (non-deterministic, external LLM dep);
  keep `GetProductReviews` + `GetAverageProductReviewScore`. Confirm the DB dep is declarable, not
  required-at-generation.
- **OQ-OT-3 — checkout breadth.** OTel `CheckoutService.PlaceOrder` fans out to cart, currency,
  product-catalog, shipping, email, payment, + Kafka — heavier than OB's checkout. It's the natural
  "hard orchestration" cell (OB's checkout was the only non-saturating service in Round 1); keep it,
  expect a lower score, that's the signal.
- **OQ-OT-4 — accounting / frontend / FeatureFlag.** accounting=Kafka-consumer (no proto RPC server),
  frontend=UI, FeatureFlagService is infra-ish. Excluded v1; revisit only if we want non-RPC task shapes.
- **OQ-OT-5 — cross-corpus comparability.** Scores from OTel vs OB shouldn't be pooled blindly
  (different services). Report **per-corpus**; the value is breadth + per-language depth, not a merged
  leaderboard.

---

## 6. Contamination caveat (carries over)

OTel-demo is a famous public repo — frontier models have memorized it in pretraining, **same as OB**
(cf. the Jetson firewall residual note). A second corpus buys **task variety + Java/C#/2nd-Python
depth, not contamination resistance.** The FR-47 perturbation probe must run on the OTel corpus too;
publish the per-corpus contamination index alongside scores. If contamination *resistance* is the
goal, that's a different search (low-popularity permissive repos or synthetic specs).

---

## 7. Validation & effort

- **Validation:** generate → assert `seeds-otel/seeds-index.json` lists 7 services; spot-check one seed
  per language embeds the oteldemo proto + correct RPCs; run `run_jetson_lane.py`/matrix **dry-run**
  against `seeds-otel/` and confirm $0 plan with 7 cells (proves schema parity, no runner change).
- **Pilot:** one structural cell per language (5 cells) on a cheap model before any full run.
- **Effort:** ~½ session for structural seeds (the generator is a copy + data swap; proto already
  fetched + sha'd). Behavioral `startup` derivation (OQ-OT-1) is the variable add-on.

---

*Draft 1.0 — grounded in the live OTel `pb/demo.proto` (sha 712594c1, package oteldemo) and the
verified per-service language/layout. Mirrors `gen_ob_benchmark_seeds.py` for byte-schema parity so
the existing runner/scorer/lane-driver consume OTel seeds unchanged.*
