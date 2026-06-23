# Liferay Pricing Lane Integration — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-23
**Status:** Draft

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning).
> The planning pass read the operational runners, the suite provenance, and the seed indexes —
> and revealed that the **operational side is already done**; the real gap is the **scorecard**.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Pricing lane isn't in any canonical run; needs a new runner or roster (FR-1/2/3) | `scripts/run_flagship_benchmark.py:74-88` `_load_seeds()` iterates **all** `hardened-index.json` seeds, which contains **all 4** pricing services, and runs **behavioral ON** by default (`--no-behavioral` to disable). The pricing lane is **already in the canonical run.** | FR-1/2/3 are **mostly satisfied**. Narrowed to: fix the stale docstring (says "pricingservice" singular; code loads all 4) + a lane-named grouping for reporting. No new runner. |
| Per-case (G3/G4/G5) visibility is a nice-to-have (FR-5 SHOULD) | The suites already persist **per-case named results** into `CellResult.behavioral["suite"]["results"]` → `cells.json`. The S2 suite names are explicit discriminators (`sum_strategy_adds_percent_levels_once`, `half_even_is_default_rounding_mode`, `half_up_rounding_mode_is_honored`, `fixed_reductions_apply_after_all_percent_reductions`, …). The data is **already on disk**; only the scorecard doesn't read it. | FR-5 promoted **SHOULD → MUST**. This is the highest-value, lowest-cost change — and the place flagship separation actually shows (a model can score 0.9 coverage while failing *exactly* the spec-reasoning cases). |
| Hardened seeds exist for pricing → show baseline-vs-hardened delta (FR-6) | There is **no `seed-resolvedpriceservice.hardened.json`** (only currency + payment have `.hardened.json`). The 4 pricing seeds **are** the hardened tier by construction (`hardened-index.json`, axes B/C/E). There is no baseline pricing variant to diff against. | FR-6 **reframed**: the discriminating contrast is **pricing-lane vs OB-leaf-lane** (pricing de-saturates where the leaf services saturate), not baseline-vs-hardened on one service. |
| The scorecard might just need a filter on the existing Section D | Section D (`scorecard.py:300-313`) groups by **model only**, mean coverage, no by-service/by-lane axis. Section G is "by language." There is **no lane/service grouping** to filter. | FR-4 is the **core new build**: a dedicated pricing-lane scorecard section (per-model, ranked) + per-case table, both reading existing persisted data. |

**Resolved open questions:**
- **OQ-1 → Use the existing `run_flagship_benchmark.py`.** It is the canonical OB+pricing runner with behavioral ON. No new script; at most a `--services <pricing subset>` convenience and a doc fix.
- **OQ-2 → No hardened pricing seed; pricing IS the hardened tier.** FR-6 reframed (see above).
- **OQ-3 → Per-case results are already persisted** in `CellResult.behavioral["suite"]["results"]`. FR-5 is feasible at scorecard-read cost only.
- **OQ-4 → All 4 pricing services are already in the roster.** Whether to *lead* the report with `resolvedpriceservice` (the richest, 31 cases) is a reporting/ordering choice, not a roster gap.
- **OQ-5 → Single canonical run** (`run_flagship_benchmark.py` runs OB + pricing together). `build_combined_scorecard.py` already exists for cross-run merges if lanes are ever run separately.
- **OQ-6 → All 4 pricing services are in `hardened-index.json`** and discoverable by the run spec.

---

## 1. Problem Statement

The Summer 2026 model benchmark's headline finding is that **flagship models do not
differentiate on structural scoring** — structural quality + compile gate saturate near 1.0
for Opus / GPT-5.5 / Gemini-2.5-pro. The behavioral (Track 2) functional-coverage term was
built to de-saturate the ceiling, but the **operational benchmark runs the stateless leaf
RPCs** (paymentservice et al.) where flagships also converge.

The team carved a **Liferay-Commerce-derived complex pricing calculator** (4-level discounts,
chain-vs-addition stacking, net-vs-gross tax ordering, max-discount caps, BigDecimal rounding)
into a deterministic gRPC/REST/GraphQL service family. Its ground-truth cases (G3/G4/G5) are
explicitly designed to *"separate a model that reasons about the spec from one that
pattern-matches a generic 'apply a discount'"* (`docs/design/liferay-pricing-seed/SPIKE_LIFERAY_PRICING_CARVE.md:162`).
**This is the discriminator the benchmark needs** — but it is built-and-tested yet **not
promoted** into the operational surface.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `resolvedpriceservice` behavioral suite | Built, registered (`behavioral/execute.py:42`), 31 cases, unit-tested | Not in any canonical/operational run roster |
| `pricingservice` / `rest-pricingservice` / `graphql-pricingservice` | Built, registered, tested | Not in canonical roster |
| `run_behavioral_pilot.py` | Defaults to `PILOT_SERVICE = "paymentservice"` only (`:40`) | No pricing-lane run; pricing only via ad-hoc `--services` |
| Behavioral term in runner | Default-OFF (`runner.py:242`) | Pricing lane needs it ON to produce a discriminating signal |
| Scorecard Section D (Behavioral) | Generic `functional coverage (mean)` per model (`SCORECARD_FORMAT.md:114`, `scorecard.py:300`) | Does not surface the pricing lane as a distinct discriminator, nor the per-case (G3/G4/G5) breakdown, nor baseline-vs-hardened |
| `checkoutservice` Tier-C orchestrator suite | **Does not exist** (no `checkout_suite.py`; seed has no `startup`) | Phase 2 — net-new, out of Phase-1 scope |

## 2. Requirements

### Phase 1 — Surface the pricing lane in the scorecard (now)

> Reframed post-planning: the operational run already covers the pricing lane. Phase 1 is now
> **scorecard-centric** — make the existing discriminating signal *visible*.

- **FR-1 — Pricing lane as a named group.** The benchmark MUST define the pricing lane as an
  explicit, named set of services so the scorecard/aggregation can group by it:
  `resolvedpriceservice`, `pricingservice`, `rest-pricingservice`, `graphql-pricingservice`
  (a constant, e.g. `PRICING_LANE`, sourced from `hardened-index.json` provenance, not hardcoded
  service strings scattered across files).
- **FR-2 — Canonical run already covers the lane (doc-correctness only).** `run_flagship_benchmark.py`
  already merges all 4 pricing services (via `hardened-index.json`) with behavioral ON. The only
  required change is **correcting its stale docstring** ("pricingservice" singular → all 4 pricing
  services) so operators know the lane runs. No new runner.
- **FR-3 — Scorecard pricing-lane section (core deliverable).** The scorecard MUST add a
  **distinct, labeled pricing-lane section**: per-model functional coverage over the pricing
  services only, ranked best→worst, so flagship separation is visible where the OB-leaf Section D
  hides it. It MUST NOT alter the existing Scoreboard ranking (behavioral stays a reported axis).
- **FR-4 — Per-case discriminator table (MUST).** The scorecard MUST surface, per model, the
  pass/fail of the **named discriminator cases** read from `CellResult.behavioral["suite"]["results"]`
  (e.g. `sum_strategy_adds_percent_levels_once`, `half_even_is_default_rounding_mode`,
  `half_up_rounding_mode_is_honored`, `fixed_reductions_apply_after_all_percent_reductions`).
  Aggregate coverage hides that a model fails *exactly* the spec-reasoning cases; this table exposes it.
- **FR-5 — Lane contrast (reframed from baseline-vs-hardened).** The scorecard SHOULD show the
  **pricing-lane vs OB-leaf-lane** coverage contrast per model — the headline "where models
  differentiate" number — since the pricing lane de-saturates where the leaf lane saturates.
  (There is no baseline pricing seed to diff against; pricing *is* the hardened tier.)
- **FR-6 — Degrade-honest.** Every new pricing-lane table MUST follow the existing degrade rule
  (FR-32 / Scorecard Principle 3): present-but-`not computed` when a run didn't measure it, never
  silently dropped; show `n` for coverage.
- **FR-7 — $0 re-score reuse.** The new scorecard sections MUST read only already-persisted
  `cells.json` data so they are recomputable for $0 (no re-generation), consistent with the
  Mottainai persist-then-rescore loop (`rescore_behavioral.py`).

### Phase 2 — Checkout orchestrator (scope only, no implementation this pass)

- **FR-8 — Checkout suite scoping.** Produce a scoped requirement set for the net-new
  `checkoutservice` Tier-C orchestrator: SDK-authored loopback dependency stubs (productcatalog,
  cart, currency, shipping, payment, email), a `startup` contract for `seed-checkoutservice.json`,
  per-step PlaceOrder ground truth, and stub-harness self-validation against a known-good
  reference checkout (per `FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md` FR-X4).
  Phase 2 is **scoped, not built**, in this effort.

## 3. Non-Requirements

- **NR-1** — No changes to how individual suites compute coverage (the suites are complete).
- **NR-2** — No new generation logic; this is benchmark-surface promotion, not model-path work.
- **NR-3** — No multi-service end-to-end app deployment (the benchmark stays per-cell isolated).
- **NR-4** — No checkout implementation this pass (Phase 2 is scope-only).
- **NR-5** — No Grafana dashboard JSON hand-authoring (defer to `/dbrd-cr8r` if needed).
- **NR-6** — Speed/cost remain reported-not-scored (Scorecard Principle 7) — unchanged.

## 4. Open Questions

> OQ-1 through OQ-6 from v0.1 were **all resolved by the planning pass** (see §0). Remaining:

- **OQ-7** — Per-case naming differs across pricing suites (`resolved_pricing_suite` uses the S2
  case names; `pricing_suite`/`rest`/`graphql` use their own). Should the per-case table (FR-4)
  show a **union of case names across the lane**, or a **per-service block**? (Leaning per-service
  block, since case names aren't 1:1 across protocol variants.)
- **OQ-8** — Should the pricing-lane section live in the existing `SCORECARD.md` (new section
  between D and E) or in a dedicated `PRICING_SCORECARD.md`? (Leaning: a new section in the main
  scorecard so the discriminator sits next to the saturated Section D for contrast.)
- **OQ-9** — Does the per-case table need a **consistency view** (a model that passes a
  discriminator case in 3/5 reps is different from 5/5)? Or is mean-pass-rate per case enough for v1?

---

*v0.2 — Post-planning self-reflective update. 3 requirements narrowed (FR-1/2/3 → operational
side already done), 1 reframed (FR-6 baseline-vs-hardened → lane contrast), 1 promoted
SHOULD→MUST (per-case discriminators), 6 open questions resolved, 3 new ones surfaced.*
