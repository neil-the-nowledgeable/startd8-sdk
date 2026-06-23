# Benchmark Scorecard Format

**Version:** 2.2
**Date:** 2026-06-23
**Status:** Defined
**Scope:** Summer 2026 Online Boutique model benchmark (`benchmark_matrix`).

> **v2.2 change — the Liferay pricing lane is surfaced as a first-class discriminator.** Flagship
> models do not differentiate on structural quality (it saturates). The Liferay-derived complex-pricing
> suites already *run* (via `run_flagship_benchmark.py`, behavioral ON) but were buried in the generic
> Section D. v2.2 adds **D2 (pricing lane + lane-vs-leaf contrast)** and **D3 (per-case discriminators)**,
> both reading already-persisted `cells.json` ($0-recomputable). See
> `docs/design/pricing-lane-integration/`.

> **v2.1 change — speed is a first-class dimension, measured two ways.** The benchmark's mandate is
> quality **/ cost / speed**, but speed was captured (`latency_s`) and never surfaced. v2.1 adds an
> explicit **Speed** section and distinguishes two time measures — **pipeline wall-clock** and **pure
> model time** — so a fast model isn't penalized for harness/repair overhead, and vice-versa. See
> "Speed dimensions" below and Section E. New requirements: **FR-SPEED-1..4** (mirror into the master
> model-benchmark requirements doc).

A **scorecard** is one document per run (markdown + HTML) that ranks models across every scoring
dimension the benchmark measures. It unifies signals that live in separate artifacts
(`cells.json` aggregate, `contamination-probe.json`, behavioral results, `comparison-report.json`).

## v2.0 change — inverted-pyramid (journalistic) ordering

The scorecard leads with **the scores**, structured most-important-first (the inverted pyramid):
the headline result, then a **Scoreboard** of provider-grouped leaderboards, then the supporting
dimensions (credibility, consistency, behavioral, determinism, by-language) below the fold. A reader
who stops after the first screen has the result; the rest is depth for those who want it.

## Principles

1. **Scores first.** The Scoreboard (composite quality leaderboards) is the top of the document,
   immediately after the header + one-line headline verdict. Supporting dimensions follow.
2. **One section per dimension** below the Scoreboard, each a per-model table + a one-line interpretation.
3. **Degrade-honest:** if a run did not compute a dimension/table, it is **present but marked
   `not computed for this run`** — never silently dropped (FR-32). A reader must tell "scored low"
   from "not measured."
4. **Every table ranks best → worst** (composite quality desc, then cost asc — `rank_models_by_quality`).
5. **Credibility is a control, not a quality term.** Contamination CodeBLEU is NOT folded into the
   composite or the Scoreboard ranking — it is a separate *leaderboard-integrity* signal.
6. **Coverage is first-class.** Tables show `n` so small-N / partially-degraded tables are read with care.
7. **Speed is reported, never scored.** Like cost, the time dimensions are a separate axis — they are
   NOT folded into composite quality or the Scoreboard ranking (which stays quality-then-cost).

## Speed dimensions (two time measures — keep distinct)

Speed is measured two ways; the scorecard reports both and never conflates them:

- **Pipeline wall-clock** — `CellResult.latency_s`, the full `run_prime_workflow` subprocess duration
  (spec → draft → review → repair → validation + process/sandbox overhead). Answers *"how long to a
  working service through our pipeline."* Throughput = `output_tokens / latency_s`.
- **Pure model time** — `CellResult.model_time_s` = Σ of every LLM call's `GenerateResult.time_ms`
  (÷1000) made while producing the cell, accumulated in the contractor and emitted to
  `prime-result.json` as `total_model_time_ms`. Answers *"how fast is the model itself,"*
  harness-independent. Throughput = `output_tokens / model_time_s` (**`model tok/s`**). This is the
  fairer cross-model speed comparison — it strips repair/validation/process overhead that the
  pipeline wall-clock includes.

The gap between them (`latency_s − model_time_s`, or the ratio) is **harness/repair overhead** — useful
for diagnosing the SDK, not the model.

### Requirements

- **FR-SPEED-1** — The contractor MUST accumulate total pure model API time (Σ `GenerateResult.time_ms`
  across all LLM calls in a run) and emit it to `prime-result.json` as `total_model_time_ms`. Absent
  timing degrades to `null` (FR-32), never 0.
- **FR-SPEED-2** — `extract_metrics` MUST read it; `CellResult` MUST carry `model_time_s` plus a derived
  `model_tokens_per_sec` (= `output_tokens / model_time_s`).
- **FR-SPEED-3** — Aggregation MUST expose `model_time_median_s` and `model_tokens_per_sec_median` per
  model (median, consistent with the distribution-appropriate stats used elsewhere — FR-distribution).
- **FR-SPEED-4** — The scorecard MUST surface model throughput in the Scoreboard and a full breakdown
  (both measures + overhead) in the Speed section. A run lacking model timing shows the Speed columns
  as `not computed` (degrade-honest), never silently as wall-clock.

## Model grouping (Scoreboard)

- **Provider** is the `provider:` prefix of the model id: `anthropic:` → **Anthropic**, `openai:` →
  **OpenAI**, `gemini:`/`google:` → **Google**.
- **Flagships** (the cross-provider headline set): `anthropic:claude-opus-4-8`, `openai:gpt-5.5`,
  `gemini:gemini-2.5-pro`. Defined as a constant (`FLAGSHIP_MODELS`), overridable; a run that lacks a
  flagship id simply shows the flagships it has. A model not matching a known provider falls into "All".

## Header (required)

```
# Benchmark Scorecard — <spec name>
spec <hash[:12]> · generated <UTC> · micro-prime <on|off>
matrix: <S> services × <M> models × <R> reps  [· cells <N>]  [· contamination <n>/<N>]
```
Followed by a one-line **headline verdict** — the flagship winner on composite quality (or, when
quality is not computed, the cleanest-credibility note), so the lede states the result.

## Sections (in order — inverted pyramid)

### A. Scoreboard (composite quality, best → worst) — TOP
Five leaderboard tables, in this order, each ranked best→worst by composite quality:

1. **Flagship comparison** — the `FLAGSHIP_MODELS` set only (the headline cross-provider result).
2. **Anthropic models** — `anthropic:*` only.
3. **Google models** — `gemini:*`/`google:*` only.
4. **OpenAI models** — `openai:*` only.
5. **All models** — every model.

Each row: `| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ | model tok/s med |`.
> Quality = median composite (structural × compile-gate × behavioral fold × defect penalty);
> catastrophic = $0/failed/timeout/integrity-fail (FR-17); `model tok/s med` = median pure-model
> throughput (FR-SPEED-2), the headline speed number — full breakdown in Section E. The whole
> Scoreboard degrades together when no `cells.json` aggregate was persisted; `model tok/s` shows
> `N/A` when model timing was not captured (FR-SPEED-4).

### B. Consistency (most reliable first)
`| Rank | Model | pass-rate | quality IQR | scored/n | catastrophic |` — reliability over peak (FR-K1).

### C. Credibility — contamination / memorization (lower = more credible)
`| Rank | Model | mean CodeBLEU | max (worst) | n | flag |` — ascending (least memorized first); flag
≥0.50 elevated, ≥0.70 likely-verbatim. A credibility control, not a quality term (FR-47).

### D. Behavioral (functional coverage) — *where Track-2 ran*
`| Rank | Model | functional coverage (mean) | cells run |`.

### D2. Pricing lane (Liferay-derived discriminator) — *the flagship-separating dimension*
`| Model | pricing coverage (mean) | cells | OB-leaf (mean) | leaf Δ |`, ranked best→worst.
Functional coverage restricted to the **`PRICING_LANE`** services (`resolvedpriceservice`,
`pricingservice`, `rest-`/`graphql-pricingservice`) — the Liferay-derived complex-pricing carve
(chain-vs-addition stacking, rounding-mode, tax/discount ordering). This lane **de-saturates where
the OB-leaf services (Section D) saturate**, so it is where near-equal flagships differentiate.
`leaf Δ = pricing-lane mean − OB-leaf mean` for the same model (negative ⇒ the lane is harder, as
intended). There is **no baseline pricing seed** — the lane *is* the hardened tier (axes B/C/E), so
the contrast is lane-vs-leaf, not baseline-vs-hardened. **Reported, never scored** (Principle 7);
degrade-honest `not computed` when no pricing cells ran. Reads only persisted `cells.json`
(`functional_coverage` + `service`), so it is $0-recomputable.

### D3. Pricing discriminators (per-case, by model) — *what aggregate coverage hides*
Per-service blocks; each a matrix of `| Case | <model> … |` with per-cell `passed/reps`. Reads the
**named per-case results** persisted at `cell.behavioral["suite"]["results"]` (`{name, passed,
detail}`). Aggregate coverage can read even while a model fails *exactly* the spec-reasoning cases
(e.g. `half_even_is_default_rounding_mode`, `sum_strategy_adds_percent_levels_once`,
`fixed_reductions_apply_after_all_percent_reductions`); this table exposes that. Case names are not
1:1 across the protocol variants, so the table is **per-service**, not a forced union. Degrade-honest
`not computed` when no pricing cell persisted suite results (degraded run / suite never ran). $0.

### E. Speed (generation time) — two measures, ranked by pure-model throughput
`| Rank | Model | model time med (s) | model tok/s med | pipeline wall med (s) | pipeline tok/s med | harness overhead |`
where `harness overhead = (pipeline wall − model time) / pipeline wall` (share of time outside the
model — repair/validation/process). Ranked by `model tok/s` desc (fastest model first). Pure-model
columns show `not computed` when `total_model_time_ms` is absent (FR-SPEED-4). Speed is reported, not
scored (Principle 7).

### F. Determinism boundary (spine in-sync) — *backend-codegen targets only*
`| Model | spine check |` from `comparison-report.json` `spine_check_status`; N/A for OB microservices.

### G. By language (polyglot view)
`| Language | quality (median) | pass-rate | mean CodeBLEU | cost $ |`.

## Generation

`benchmark_matrix.scorecard`:
- `build_scorecard(run_dir) -> str` (markdown), `build_scorecard_html(run_dir) -> str` (self-contained HTML).
- `write_scorecard(run_dir)` / `write_scorecard_html(run_dir)` → `<run_dir>/SCORECARD.{md,html}`.
- CLI `scripts/build_scorecard.py <run_dir> [--format both|md|html]`.

Each section/table reads its source independently; a missing source ⇒ the `not computed` marker, not an
error. The Scoreboard's five tables share one aggregate (`aggregate_cells`) filtered by group.

## Dashboard relationship

The scorecard (markdown + self-contained HTML, $0, point-in-time) complements the live Grafana views
(`metrics_export.py` Prometheus textfile; `observability.py:build_run_dashboard_spec` SRE dashboard via
`/dbrd-cr8r`). **Grafana JSON is built only through the dbrd-cr8r pipeline, never hand-authored.**
