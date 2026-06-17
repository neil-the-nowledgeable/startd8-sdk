# Liferay-derived Pricing-Calculator Benchmark Seed — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-17
**Status:** Draft (planning-corrected; pre-implementation)
**Grounding:** `docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md`
**Plan:** `docs/design/liferay-pricing-seed/PRICING_SEED_PLAN.md`
**Scope:** Phase 1 — one additive hardened-tier gRPC seed for the Summer 2026 model benchmark.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after reading the real behavioral harness
> (`src/startd8/benchmark_matrix/behavioral/`). The planning pass produced 6 corrections — the
> headline one falsifies a v0.1 non-requirement.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| **No harness changes** (non-req) | Harness is hardcoded to OB's single `demo.proto` (`execute.py:_PROTO`, `prepare_node_workdir`, committed `demo_pb2`/`go_stubs`, `contamination.py`, `scoring.py`). A new proto can't reuse it. | Non-req struck. **New FR-14** (parameterize proto provisioning, default-`demo.proto` so OB is byte-unchanged). |
| Suite "just registers" in `_SUITES` | Suites import committed stubs (`from . import demo_pb2`); `pricing_pb2`/`pricing_pb2_grpc` don't exist and there's no gen script. | **New FR-15** (generate + commit pinned-version stubs; document the protoc command). |
| FR-13 scoring needs wiring | Overspecified — `scoring.py:300-303` folds `functional` automatically; degraded → no penalty. | FR-13 narrowed to "verify, build nothing." |
| FR-11 = scored contamination probe | `contamination.py` CodeBLEU needs a canonical **upstream reference**; a synthetic service has none → the CodeBLEU *score* is N/A. | FR-11 reframed: rename pass is **hygiene/neutralization**, not a scored metric for this seed (OQ-6 resolved). |
| Money = decimal strings, no friction | House style is `Money{units,nanos}`; decimal strings are a deliberate divergence (better for FR-7 rounding). | FR-7 keeps decimal strings, now documented as an explicit divergence. |
| `language_rationale` ≈ canonical language | No canonical upstream language for a synthetic seed. | Field meaning shifts to "harness-proven offline runtime closure" (noted in FR-12). |

**Resolved open questions:**
- **OQ-1 → HALF_UP default** when `rounding` is unspecified; the service must honor an explicit mode.
- **OQ-2 → Single flat tax rate per line.** Tax categories deferred.
- **OQ-3 → Multi-line cart with subtotal roll-up**, ≤ 3 lines per suite case (tests aggregation cheaply).
- **OQ-4 → ~220 LOC** target; comfortably single-file.
- **OQ-5 → Rename map locked** (see FR-11): `level1..4 → tierFactor1..4`, `finalPrice → netPayable`, `promoPrice → offerUnitPrice`, `discounts_target_net_price → applyAdjustmentsPreTax`, `PriceCart → ComputeBasket`.
- **OQ-6 → CodeBLEU contamination score N/A** for this synthetic seed (no upstream reference); rename hygiene + the perturbation memorization check are the only applicable Axis-E measures, and baseline contamination is low by construction.

---

## 1. Problem Statement

The Summer 2026 model benchmark builds Online Boutique (9 gRPC services, one file each). Its
discriminating signal is the Track 2 behavioral suite, but only a few stateless OB services have
suites and their behavioral bar is shallow (e.g. `paymentservice.Charge` = 3 assertions). The new
hardened-difficulty tier (`docs/design/benchmark-task-difficulty/`) wants seeds that discriminate
frontier models on **arithmetic precision from a stringent spec** (Axis C) via a **discriminating
behavioral suite** (Axis B), with **contamination resistance** (Axis E).

The spike established that Liferay Commerce's price calculation, with its *resolution layer moved
upstream*, is a clean stateless pure function — a strong candidate for such a seed.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Hardened-tier seeds | None authored | Need a first concrete seed |
| Behavioral suites | 4 OB services, shallow | Need a deep, discriminating suite |
| Domain richness | OB toy services | Liferay commerce pricing is genuinely hard |

## 2. Requirements

**FR-1 — Seed conforms to the benchmark seed contract.** A single seed JSON conforming to the real
schema (`docs/design/model-benchmark/seeds/seed-paymentservice.json`): top-level `generator`,
`schema_version`, `service_metadata`, `startup`, `tasks`, `version`; the proto embedded in
`tasks[0].config.requirements_text`; `target_files` a single file.

**FR-2 — Pure calculator, resolution upstream.** One RPC `PriceCart(PriceCartRequest) →
PriceCartResponse`. All price-list selection, discount eligibility, coupon validation, and
address→tax-rate resolution are passed in as resolved parameters. No DB, no network, no hidden state.

**FR-3 — 4-level discounts with strategy flag.** Support `level1..level4` magnitudes and a
`DiscountStrategy` flag: `CHAIN` (each level applies to the running discounted amount) and `ADDITION`
(levels summed, applied once). Both strategies in a single flag-driven service.

**FR-4 — Promo-min selection.** A promo price replaces the unit price as the base iff it exists, is
`> 0`, and is lower than the unit price.

**FR-5 — Tax/discount ordering flag.** `discounts_target_net_price`: `true` → discount net then add
tax; `false` → convert to gross (tax-inclusive), discount the gross, strip tax back to net.

**FR-6 — Max-discount cap.** `maximum_discount_amount` caps the per-discount amount.

**FR-7 — Decimal-string money + explicit rounding.** All amounts/quantities are decimal strings
(never floats) — a *deliberate divergence* from the house `Money{units,nanos}` type, justified
because exact-decimal + explicit rounding is the discriminating skill here. `Currency{code, scale,
rounding}` with `rounding ∈ {HALF_UP, HALF_EVEN}`, default **HALF_UP** when unspecified (OQ-1); the
service honors the requested mode at the currency scale.

**FR-8 — POA + error taxonomy.** `price_on_application` items return a flagged result with no numeric
price (not an error). Malformed/negative quantity or price, unspecified strategy, or > 4 levels →
gRPC `INVALID_ARGUMENT`.

**FR-9 — SDK-authored behavioral suite.** A `run_pricing_suite(port, *, host, connect_timeout) →
SuiteResult` registered in the `_SUITES` dict (`benchmark_matrix/behavioral/execute.py`),
implementing ground-truth assertions G1–G7 from the spike. `SuiteResult` contract per `charge_suite.py`
(suite_version, results[RpcResult], connect_error, `.coverage`, `.to_dict()`).

**FR-10 — Startup contract.** Seed `startup` block: `cmd`, `port_env`, `readiness: "tcp"`.

**FR-11 — Contamination rename pass (FR-47), reframed as hygiene.** Apply the locked deterministic
rename map (OQ-5) neutralizing Liferay-verbatim tells (`level1..4 → tierFactor1..4`, `finalPrice →
netPayable`, `promoPrice → offerUnitPrice`, `discounts_target_net_price → applyAdjustmentsPreTax`,
`PriceCart → ComputeBasket`) before the seed ships. **Not** a scored contamination metric: the
`contamination.py` CodeBLEU probe needs a canonical upstream reference, which a synthetic service
lacks (OQ-6). Baseline contamination is low by construction; the rename is neutralization hygiene.

**FR-12 — Language pinning.** Pin the first seed to **nodejs** — chosen for the harness's proven
vendored offline runtime closure (`node_runtime/`, dynamic `@grpc/proto-loader`), not a canonical
upstream language (none exists for a synthetic seed). A Python variant is a follow-on.

**FR-13 — Scoring integration (verify only).** Behavioral coverage folds into the composite via the
existing `FUNCTIONAL_WEIGHT` path (`scoring.py:300-303`) once `run_behavioral_cell` returns coverage;
degraded → `missing`, no penalty. **Nothing to build** — this requirement is a verification check.

**FR-14 — Parameterize proto provisioning (harness change).** Generalize `prepare_node_workdir` /
`execute.py:_PROTO` so the provisioned proto filename derives from the seed/service, defaulting to
`demo.proto` so all OB cells remain byte-identical. Guard with a regression test asserting OB
provisioning is unchanged.

**FR-15 — Generate + commit pricing stubs.** Produce `pricing_pb2.py` / `pricing_pb2_grpc.py` via
`grpc_tools.protoc`, pinning the protobuf/grpc-tools version to match `demo_pb2.py`'s generator
(avoid wire/runtime skew). Document the generation command in the behavioral README (no gen script
exists today).

## 3. Non-Requirements

- **No resolution layer** — price-list discovery, eligibility hierarchy, coupon usage limits,
  address→rate are out of scope (upstream).
- **No multi-currency conversion** — single currency, no exchange rates.
- **No REST/HTTP** — Phase 2.
- ~~**No harness changes**~~ — **struck (v0.2).** A bounded, additive proto-provisioning
  generalization is required (FR-14/FR-15); OB cells stay byte-identical. No *new harness subsystem*
  (no REST lane, no scoring change) — that boundary holds.
- **No multi-file / orchestration** — single file only.

## 4. Open Questions

All v0.1 open questions were resolved by the planning pass — see §0. None remain blocking.
Implementation-time confirmations:
- **CQ-1** Confirm `grpc_tools`/protobuf version parity with `demo_pb2.py` before committing stubs (FR-15).
- **CQ-2** Confirm a hand-written reference Node server passes G1–G7 before the seed is considered done (validation S7).

---

*v0.2 — Post-planning self-reflective update. 1 requirement added-major (FR-14) + 1 added (FR-15),
2 narrowed (FR-11, FR-13), 1 non-requirement struck (no harness changes), 6 open questions resolved.
The loop earned its keep: the proto-coupling discovery would otherwise have surfaced mid-implementation.*
