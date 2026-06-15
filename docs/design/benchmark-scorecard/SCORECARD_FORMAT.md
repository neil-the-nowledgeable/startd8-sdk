# Benchmark Scorecard Format

**Version:** 1.0
**Date:** 2026-06-15
**Status:** Defined
**Scope:** Summer 2026 Online Boutique model benchmark (`benchmark_matrix`).

A **scorecard** is one markdown document per run that ranks models across every scoring dimension the
benchmark measures. It unifies signals that today live in separate artifacts (`build_matrix_markdown`
leaderboard, `contamination-probe.json`, behavioral results, `model_comparison` spine check) into a
single human-readable view.

## Why this format (what existed before)

The repo already had `benchmark_matrix/aggregate.py:build_matrix_markdown` — a leaderboard covering
**quality / consistency / cost / by-language**. It predates the newer scoring signals and omits them.
This format **supersedes** it by adding three dimensions and making every dimension *degrade-honest*:

| Dimension | Was in `build_matrix_markdown`? | Source artifact |
|-----------|-------------------------------|-----------------|
| Quality (composite) | ✅ | matrix aggregate (`aggregate_cells`) |
| Consistency | ✅ | matrix aggregate |
| Cost | ✅ | matrix aggregate / `prime-result.json` |
| By-language | ✅ | matrix aggregate |
| **Credibility (contamination)** | ❌ NEW | `contamination-probe.json` (`benchmark_matrix.contamination`) |
| **Behavioral (functional)** | ❌ NEW | Track-2 behavioral results (`behavioral/execute.py`) |
| **Determinism boundary** | ❌ NEW | `model_comparison` `spine_check_status` |

## Principles

1. **One section per dimension**, each a per-model table + a one-line interpretation.
2. **Degrade-honest:** if a run did not compute a dimension, the section is **present but marked
   `not computed for this run`** — never silently dropped (FR-32 parity). A reader must be able to
   tell "model scored low" from "we didn't measure it."
3. **Credibility is a control, not a quality term.** Contamination CodeBLEU must NOT be folded into the
   composite quality (the composite already folds compile + structural + behavioral + defects). It is
   reported separately as a *leaderboard-integrity* signal — high similarity to public upstream ⇒
   likely memorization, which *discredits* a high quality score rather than improving it.
4. **Coverage is first-class.** Every table shows `n` (cells scored) and the run's total, so small-N or
   partially-degraded dimensions are read with appropriate caution.

## Header (required)

```
# Benchmark Scorecard — <spec name>
spec <hash[:12]> · generated <UTC> · repair <on|off> · micro-prime <on|off>
matrix: <S> services × <M> models × <R> reps = <N> cells · scored <n>/<N>
```

## Sections (in order)

### 1. Quality leaderboard (by median composite, then cost)
`| Rank | Model | quality (median) | IQR | pass-rate | catastrophic | cost $ |`
> Quality = median composite (structural + compile-gate + behavioral fold + defect penalty);
> catastrophic = $0/failed/timeout/integrity-fail, reported separately (FR-17).

### 2. Consistency (most reliable first)
`| Rank | Model | pass-rate | quality IQR | scored/n | catastrophic |`
> Reliability over peak: pass-rate then tightest spread — the axis near-equal flagships differ on (FR-K1).

### 3. Credibility — contamination / memorization (lower = more credible)
`| Rank | Model | mean CodeBLEU | max (worst cell) | n | flag |`
> CodeBLEU similarity of generated code to the **public** Online Boutique upstream. Higher ⇒ more
> likely reproduced from pretraining than solved. **Flag** ≥0.50 = elevated, ≥0.70 = likely verbatim.
> Ranked **ascending** (least memorized first). NOT a quality term — a credibility control (FR-47).
> Clean signal requires a repair-OFF run (repair polishing perturbs verbatim regurgitation).

### 4. Behavioral (functional coverage) — *where Track-2 ran*
`| Model | functional coverage | cells run | degraded |`
> Fraction of behavioral RPC contracts the live service satisfied (e.g. Charge: valid/invalid/expired).
> Gated on spend; `not computed for this run` when the behavioral track was off.

### 5. Determinism boundary (spine in-sync) — *backend-codegen targets only*
`| Model | spine in-sync rate | drift | error |`
> Did the model drift an owned ($0-generated) skeleton file instead of only adding glue
> (`generate backend --check`). N/A for non-backend-codegen seeds.

### 6. By language (polyglot view)
`| Language | quality (median) | pass-rate | mean CodeBLEU | cost $ |`

## Generation

A scorecard is built from a run's artifacts: the matrix aggregate (dimensions 1/2/6 + cost) and the
side-channel JSONs (`contamination-probe.json` → §3; behavioral results → §4; `comparison-report.json`
`spine_check_status` → §5). Each section is emitted independently; a missing source ⇒ the
`not computed` marker, not an error. Recommended home: a renderer
`benchmark_matrix.scorecard.build_scorecard(run_dir) -> str` that supersedes `build_matrix_markdown`,
and a `scripts/build_scorecard.py <run_dir>` CLI writing `<run_dir>/SCORECARD.md`.

## Dashboard relationship

The scorecard (markdown, $0, point-in-time) complements — does not replace — the live Grafana views:
- `benchmark_matrix/metrics_export.py` → Prometheus `.prom` textfile.
- `benchmark_matrix/observability.py:build_run_dashboard_spec` → execution-run SRE dashboard (via
  `/dbrd-cr8r` → `dashboard_creator`). **Per the repo hard rule, Grafana JSON is built only through the
  dbrd-cr8r pipeline, never hand-authored.** A "Scorecard" Grafana dashboard (leaderboard +
  contamination panels) would be a `/dbrd-cr8r` DashboardSpec, out of scope for this markdown format.
