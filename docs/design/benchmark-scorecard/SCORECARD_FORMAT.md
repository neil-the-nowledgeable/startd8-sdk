# Benchmark Scorecard Format

**Version:** 2.0
**Date:** 2026-06-15
**Status:** Defined
**Scope:** Summer 2026 Online Boutique model benchmark (`benchmark_matrix`).

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

Each row: `| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ |`.
> Quality = median composite (structural × compile-gate × behavioral fold × defect penalty);
> catastrophic = $0/failed/timeout/integrity-fail (FR-17). The whole Scoreboard degrades together when
> no `cells.json` aggregate was persisted.

### B. Consistency (most reliable first)
`| Rank | Model | pass-rate | quality IQR | scored/n | catastrophic |` — reliability over peak (FR-K1).

### C. Credibility — contamination / memorization (lower = more credible)
`| Rank | Model | mean CodeBLEU | max (worst) | n | flag |` — ascending (least memorized first); flag
≥0.50 elevated, ≥0.70 likely-verbatim. A credibility control, not a quality term (FR-47).

### D. Behavioral (functional coverage) — *where Track-2 ran*
`| Rank | Model | functional coverage (mean) | cells run |`.

### E. Determinism boundary (spine in-sync) — *backend-codegen targets only*
`| Model | spine check |` from `comparison-report.json` `spine_check_status`; N/A for OB microservices.

### F. By language (polyglot view)
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
