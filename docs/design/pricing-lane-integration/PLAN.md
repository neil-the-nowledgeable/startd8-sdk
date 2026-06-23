# Liferay Pricing Lane Integration — Implementation Plan

**Version:** 1.0 (matches REQUIREMENTS v0.2)
**Date:** 2026-06-23
**Status:** Draft

---

## Summary

Planning revealed the operational run already executes the pricing lane (all 4 services,
behavioral ON) via `scripts/run_flagship_benchmark.py`. The work is therefore **scorecard
surfacing + one doc fix**, reading data already persisted in `cells.json`. No new runner, no
new generation, no suite changes. This keeps the change $0-recomputable (FR-7).

## Traceability

| Req | Plan step |
|-----|-----------|
| FR-1 (named lane) | S1 |
| FR-2 (doc fix) | S2 |
| FR-3 (pricing-lane section) | S3, S5 |
| FR-4 (per-case discriminator table) | S4, S5 |
| FR-5 (lane contrast) | S3 |
| FR-6 (degrade-honest) | S3, S4 (follow Principle 3) |
| FR-7 ($0 from cells.json) | S0 (verify), all steps read-only of persisted data |
| FR-8 (checkout scope) | S7 (separate doc, scope-only) |

## Steps

### S0 — Verify the persisted shape (de-risk before building)
Confirm `CellResult.behavioral` round-trips through `cells.json` with `suite.results` intact
(per-case `{name, passed, detail}`). Read `benchmark_matrix/runner.py` persistence + a real
`cells.json` if one exists under `results/` or `out/`. **Gate:** if per-case names are NOT in
the persisted JSON (only the scalar coverage), FR-4 needs a runner change too — re-open scope.
- Files: `src/startd8/benchmark_matrix/runner.py` (CellResult serialization), any `results/*/cells.json`.

### S1 — Define the pricing lane constant (FR-1)
Add `PRICING_LANE` (the 4 service names) sourced from `hardened-index.json` provenance, not a
scattered literal. Single home, imported by the scorecard.
- Files: `src/startd8/benchmark_matrix/__init__.py` or a small `lanes.py`; derive from
  `docs/design/model-benchmark/seeds/hardened-index.json` `derived_from` containing "Liferay".

### S2 — Fix the stale runner docstring (FR-2)
`run_flagship_benchmark.py:2-8,75` says "pricingservice" singular; the code loads all 4. Correct
the module docstring + `_load_seeds()` docstring to name the lane and confirm behavioral ON.
- Files: `scripts/run_flagship_benchmark.py`.

### S3 — Scorecard: pricing-lane section + lane contrast (FR-3, FR-5)
New section (between D and E per OQ-8) in `scorecard.py`:
- Per-model functional coverage **restricted to `PRICING_LANE` cells**, ranked best→worst, with `n`.
- A one-line **lane contrast**: pricing-lane mean coverage vs OB-leaf mean coverage per model
  (the "where models differentiate" headline).
- Degrade-honest: `not computed` when no pricing cells ran (Principle 3).
- Mirror into the HTML builder (`build_scorecard_html`).
- Files: `src/startd8/benchmark_matrix/scorecard.py` (md + html), `SCORECARD_FORMAT.md` (document the new section).

### S4 — Scorecard: per-case discriminator table (FR-4)
Read `c.behavioral["suite"]["results"]` for pricing cells; for each (service, case name) compute
per-model pass-rate across reps. Render per-service blocks (OQ-7 lean). Mark `not computed` if
behavioral provenance absent.
- Files: `src/startd8/benchmark_matrix/scorecard.py`.

### S5 — Tests (degrade paths + happy path)
Unit tests with synthetic `cells.json` fixtures: (a) pricing cells present → section + per-case
table render and rank; (b) no pricing cells → `not computed`; (c) behavioral provenance missing →
per-case table degrades, coverage section still renders. Reuse existing scorecard test patterns.
- Files: `tests/unit/benchmark_matrix/test_scorecard*.py` (extend).

### S6 — Update `SCORECARD_FORMAT.md` (spec of record)
Add the pricing-lane section + per-case table to the documented section list (between D and E),
note it is reported-not-scored (Principle 7), and reference `PRICING_LANE`.
- Files: `docs/design/benchmark-scorecard/SCORECARD_FORMAT.md`.

### S7 — Phase 2 scope doc (FR-8, scope-only)
Write a short scoping doc for the checkout orchestrator suite that defers to and refines
`FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md` FR-X4 (stub harness, startup contract,
per-step PlaceOrder ground truth, stub self-validation). No code.
- Files: `docs/design/pricing-lane-integration/CHECKOUT_PHASE2_SCOPE.md` (new).

## Risks / Notes
- **R1 (S0 gate):** if per-case data isn't in `cells.json`, FR-4 expands to a runner change + a
  re-run (not $0). S0 must run first.
- **R2:** don't touch the Scoreboard ranking or the composite — behavioral stays reported, the
  pricing lane is a *view*, not a new scored term (Scorecard Principle 7; NR-6).
- **R3:** per-case names differ across the 4 suites (OQ-7) — render per-service, don't force a union.

## Out of scope (this plan)
Checkout implementation (FR-8 is scope-only), any suite/coverage-math changes (NR-1), generation
path (NR-2), Grafana JSON (NR-5).
