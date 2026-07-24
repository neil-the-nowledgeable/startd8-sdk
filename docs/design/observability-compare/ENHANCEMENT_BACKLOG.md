# Enhancement Backlog — Observability Derived-vs-Emitted Comparison

**Date:** 2026-07-23 · **Scope:** `startd8 observability compare` (Tier A) + `compare-live` (Tier B
live runner + CI gate), the pilot-repro fixture + gate workflow, and the #301 declared-series binder.
Code: `src/startd8/observability/{compare,compare_live,live_standup,prometheus_query,validate_promql}.py`,
`scripts/compare_live_gate.sh`, `.github/workflows/observability-compare-live-gate.yml`.

> The pass after shipping: *given what we now have, where's the leverage?* Every item is grounded at
> `file:line`; the signature move is **wire what already exists**, not build new engines.

**Grounding note (belief → actual corrections):**
- *Believed* the gate surfaces the regression set → *actual:* the new-vs-baseline fails are **computed
  then discarded** (`cli.py:514`). That flipped the lead finding from "nice-to-have diff" to a
  built-but-unwired value path.
- *Believed* "regenerate artifacts every gate run" might be wasteful (Mottainai) → *actual:* it's the
  gate's **purpose** (detect generator drift), and it's $0 deterministic — a **decision, not a gap**.

---

## Top findings (do these first)

**1. [Built-but-unwired] The CI gate computes *which* SLIs regressed, then throws it away.** — ✅ **DELIVERED 2026-07-23** (FR-8a): the CLI now prints a `NEW dead SLI(s) vs baseline` block naming each regression, and `--json` carries `new_fail_verdicts`; proven on real telemetry (named the 1 dropped-baseline SLI, exit 2). +3 CLI tests.
`ci_gate()` returns `(exit_code, new_fails)` — the new-vs-baseline regression list
(`compare_live.py:ci_gate`, `new_fail_verdicts`). But the CLI drops it:
`cli.py:514` → `code, _new = ci_gate(report, load_baseline(baseline))` then `raise typer.Exit(code)`.
So a red gate (exit 2) prints the *full* report (every dead SLI via `render_live_report`) and the
operator must **hand-diff against the baseline** to find the actual regression. The discriminating
signal — "these 2 are NEW" — is built and dropped. **Wire `_new` into the output** (print the new-fail
`verdict_id`s, or add them to `--json`) → so a CI failure tells you *what you broke*, not just *that
something is dead*. **Effort: XS–S.** *(This is the gate's whole reason to exist; surfacing it is the
highest value-per-line in the capability.)*

**2. [Latent capability] The one-line fix is computed and printed, but never applied.**
`compare_live.py:319-320` renders `one-line fix: metricsProfile = <profile>` (from
`validate_promql`'s `suggested_metrics_profile`). There is **no `--apply`/`--fix`** anywhere
(`grep` in `compare_live.py`/`cli.py` finds only the print + the source at `cli.py:205`). The fix is
diagnosed but the operator must manually edit the manifest + regenerate. **Add `compare-live
--apply-profile-fix`** that writes `spec.observability.metricsProfile` into the manifest → closes the
diagnose→fix loop the report already opens. **Effort: M** (writes one manifest key; the profile value
already exists).

**3. [Silent cap] The dead-SLI list is truncated at 20 with no "…N more".**
`compare_live.py:316` → `for v in report.fail_verdicts[:20]:` while `:314` prints
`dead (fail) {len(report.fail_verdicts)}`. A 33-dead-SLI run shows "dead (fail) 33" but lists only 20 —
13 vanish silently. **Append `… and N more` when `len > 20`.** **Effort: XS.**

---

<details>
<summary><b>Backlog appendix</b> — bucketed, ranked (draw from over later increments)</summary>

## ⚡ Quick wins
- **QW-1 — surface `_new` on a gate failure** — *(= Top finding 1)* ✅ **DELIVERED** (FR-8a).
- **QW-2 — "…N more" on truncated dead-SLI list** — *(= Top finding 3)* `compare_live.py:316`. **XS.**
- **QW-3 — link `HOWTO_COMPARE_LIVE.md` from `--help`** — the portable how-to (shipped in #301) is
  not referenced in `cli.py` (`grep HOWTO_COMPARE_LIVE cli.py` → none), so a user in `--help` can't
  find it. Add a one-line "See: docs/design/observability-compare/HOWTO_COMPARE_LIVE.md" to the
  `compare-live` docstring. **XS.** *(dev + user discoverability.)*
- **QW-4 — echo the `report_version` in the human renderer** — `LiveComparisonReport.REPORT_VERSION`
  is in `--json` but `render_live_report` never prints it; a one-line footer helps a human correlate a
  pasted report with a schema. **XS.**

## 🌱 Low-hanging fruit
- **LH-1 — `--baseline` summary line even on PASS** — on a clean gate the operator gets exit 0 and the
  full report but no "0 new / N baselined" confirmation; a one-line roll-up ("gate: 0 new dead SLIs,
  11 baselined") makes the *why-it-passed* legible. Builds on `ci_gate`'s already-computed sets. **S.**
- **LH-2 — skip-guard the vendor/Grafana tests (retire deselects)** — **DELIVERED 2026-07-23 (#304).**
  `test_datasource_uid_binding` + `test_dashboard_renderer_v2` now skip when their toolchain/service is
  absent; the CI deselects were removed. *(Kept here as the Delivered log.)*

## 🚀 Enhanced capabilities
- **EC-1 — `--apply-profile-fix`** — *(= Top finding 2)* `compare_live.py:319`. **M.**
- **EC-2 — multi-container subject standup (NR-1)** — `live_standup` stands up ONE `subject_image`;
  heavy subjects (Mastodon = PG+Redis+Sidekiq) are reachable only via `--prometheus <existing>`. A
  compose-based multi-service standup would let the gate stand up real apps. The fleet's
  `benchmark_matrix/fleet/compose.py` is adjacent plumbing to lean on. **L.** *(Deferred by design;
  documented in REQUIREMENTS NR-1.)*
- **EC-3 — OTel-collector-fronted (span-metrics) subjects (NR-2)** — v1 scrapes `/metrics` directly;
  a span-metrics subject needs the `runtime_fidelity.SpanMetricsCollector` path wired into
  `live_standup`. **L.** *(Deferred by design; NR-2.)*

## 🏗️ Architectural quick win (one, rides on a fresh single-source)
- **AR-1 — pin `prom/prometheus` by digest** — `live_standup.PROMETHEUS_IMAGE = "prom/prometheus:v2.53.0"`
  is a floating tag; a determinism gate deserves a `@sha256:` pin + documented pre-pull (the deferred
  CRP **R1-S7**). Reproducibility + supply-chain. **S.** *(Cite: this is a hardening decision, not a
  defect — the tag works today.)*

## 🔭 Operational / observability (make the gate legible)
- **OP-1 — emit the compare-live verdict as OTel metrics** — the SDK already has an OTel stack
  (`costs/otel_metrics`, `observability/`); emitting `compare_live.dead_sli_count{subject}` +
  `gate.result` would let a Grafana panel trend "derived-vs-emitted fidelity over time" instead of
  reading exit codes. **S–M.** *(Cheapest way to prove the gate's ongoing value.)*
- **OP-2 — upload the merged report as a CI artifact** — `observability-compare-live-gate.yml` runs the
  gate but keeps no record; an `actions/upload-artifact` of the `--json` report (mirrors
  `observability-fidelity.yml`'s `fidelity-report` upload) gives post-hoc diagnosis on a red gate. **S.**

## Honest gaps (decisions, not bugs)
- **Regenerate-every-run is the point.** `compare_live_gate.sh:35-43` regenerates the pilot artifacts
  each run — that's how the gate catches *generator* drift; not a caching opportunity.
- **`compare` and `compare-live` are separate verbs, not `compare --live`.** A deliberate CRP decision
  (Tier A shipped first, #282; the separate verb avoided a concurrent-edit collision). Folding into one
  `--live` flag is optional polish, not a gap.
- **Repo Actions `enabled: false`.** The gate + Tests workflows won't execute in CI until Actions is
  re-enabled — an ops/billing decision, out of this capability's scope (see
  `docs/design/ci-enablement/RETROSPECTIVE.md`).
- **Flaky-tail / rerunfailures widen-backlog** is CI-infra (adjacent), tracked in
  `tests/ci_known_failing.txt` — not part of this capability.

</details>

---

# Addendum — Synthetic-Probe & declared-lane capabilities (#307 / #308)

**Date:** 2026-07-23 · **Scope:** the declared-lane binders shipped after the original backlog —
`#307` span-metrics binding, `#308` synthetic-probe P0 + P1–P3. Code:
`src/startd8/observability/{artifact_generator_generators,compare,compare_live,validate_promql,probe_trace}.py`.

**Grounding note (belief → actual):**
- *Believed* pending probes might be **invisible** in a live run (a broken end-to-end path) → *actual:*
  they **are** surfaced in Tier-A — `ComparisonReport.pending` (`compare.py:98`) flows into the live
  report via `comparison.to_dict()` (`compare_live.py:build_live_comparison` → `tier_a`). That
  **downgraded** the lead finding from "broken" to "the Tier-B *verdict* roll-up is incomplete" — the
  function is orphaned, not the feature.
- *Believed* the R1-F2 "exit-2 leak" the CRP guarded was live in the pipeline → *actual:* `compute_coverage`
  reads only `extract_exprs` verdicts (`validate_promql.py:981`), and P0/P1 write **no** probe SLO file, so
  a pending probe was never in that denominator to begin with — the guard is correct but its risk is latent
  until P2 promotion writes a real SLO. A **decision boundary**, not a bug.

## Top findings (do these first)

**1. [Built-but-unwired] The P2 `pending_probe` verdict is synthesized by a tested function that nothing
calls.** — ✅ **DELIVERED 2026-07-23** (EC-1): `build_live_comparison` now synthesizes the pending verdicts
from `comparison.pending` and merges them into `tier_b["verdicts"]` + a new `pending_verdicts` field
(`--json` `report_version` bumped 1→2); `render_live_report` shows a distinct "Pending probes" block. They
are `pending_probe` (severity 0) — never in `fail_verdicts`/coverage, so they can't flip the gate. +4 tests.
`promote_probe_slo()` remains uncalled by design — its surface is the P2-live `--promote-probes` flag (EC-3).
Original finding: `pending_probe_verdicts()` had **zero callers**; `build_live_comparison` — which already
received `comparison.pending` — never merged them, so a `compare-live` run's Tier-B list never showed pending
probes (they appeared only in Tier-A). *(Not "broken" — Tier-A already showed them; this completed the
Tier-B surface the P2 function was built for.)*

**2. [Enhanced capability] `--promote-probes` — the promotion builder exists; the CLI surface that fires it
doesn't.** `promote_probe_slo()` (`compare_live.py`) builds the `slos/` SLO from a live-confirmed pending
entry (single-sourced off the recorded query), but no `--promote-probes` flag on `compare-live` calls it,
and the ≥2-scrape warm-up gate (NR-5) isn't wired. This is the P2-live surface: wire a flag that, on a
confirmed metric, writes the promoted SLO. **Effort: M** (part of it is external — needs a live subject to
*confirm* — but the flag + warm-up gate + write are unit-testable). *(OQ-2.)*

## Backlog appendix

<details><summary>Bucketed backlog (draw from over later increments)</summary>

### ⚡ Quick wins
- **EC-1 — Wire `pending_probe_verdicts` into `build_live_comparison`** — ✅ **DELIVERED** (Top finding 1);
  merged into `tier_b["verdicts"]` + `pending_verdicts` field + a distinct render block. **XS–S.**
- **EC-2 — A "Pending probes" count in the live rollup reason.** `_rollup_reason` (`compare_live.py`) names
  dead SLIs but not pending probes; add *"· M pending probe(s)"* so a green run still advertises the
  derive-value finding. **XS.**

### 🚀 Enhanced capabilities
- **EC-3 — `--promote-probes` flag + warm-up gate** (Top finding 2). Builder is done; wire the CLI surface.
  **M.** *(OQ-2; part external.)*
- **EC-4 — P3 Tempo trace-file adapter.** `compute_fanout_freshness` (`probe_trace.py`) is a tested pure
  core with **zero callers**; nothing maps real trace JSON → `SpanLite`. Add a `trace_file` adapter (OQ-3
  leans "consume an exported trace file, no live Tempo dep") → link-aware freshness becomes runnable on a
  real export. **M/L.** *(External validation still needs traces with the `:link` edge.)*
- **EC-5 — A concrete runner reference recipe.** P1 emits the `probe-spec.yaml` but OQ-1 deferred the *one*
  concrete runner (a portable Python/HTTP loop) that executes it. Shipping a reference runner turns the spec
  from a description into a thing an operator can actually run. **M.** *(OQ-1.)*

### 🏗️ Architectural quick win (one item — hand off deeper cleanup)
- **EC-6 — Unify the four positive-finding lanes.** `ComparisonReport` now carries
  `bound`/`bound_functional`/`bound_span`/`pending` — four field+build+render+`to_dict` repetitions
  (`compare.py:42-67`), each added by a separate lane (#286/#300/#307/#308). The #300-D2 CRP (R1-F8) and the
  Capability-Delivery-Loop §3 explicitly deferred unification "until the 5th lane." There are now **four** —
  the threshold is met. This is a **`/complexity-distiller` smell (duplicated shape / shotgun-surgery seam)**;
  hand the deeper extraction there. One backlog item, cited, not built here. **S–M.**

### Honest gaps (decisions, not bugs)
- **P2-live and P3-validation are external BY DESIGN** — the spec's §4a Definition-of-Done marks them
  unit-vs-external; the pure functions (verdict synth, promotion builder, delta core) are the unit-tier
  deliverable and are done + tested. Their *callers* (live run, `--promote-probes`, Tempo adapter) are the
  external/P2-live/P3 work above — not a defect that the functions "don't run" today.
- **`declared_probes` / `declared_span_signals` arrive only if the onboarding metadata carries them.**
  `_parse_declared_probes` parses the field when present, but the **ContextCore #58 / REQ-CCL-109 carry**
  (cross-repo) is what makes a real onboarding surface emit it. Until then these lanes fire only on a
  hand-authored fixture — a known cross-repo dependency, not a gap in this repo.

</details>

## Closure-Ledger row (verified defect)

| Item | Now | Gate to next | Value if closed |
|------|-----|--------------|-----------------|
| P2 `pending_probe` verdict wiring | **L3 ✅ DELIVERED** (EC-1, 2026-07-23) — wired into `build_live_comparison`, merged into `tier_b["verdicts"]` + `pending_verdicts` field, rendered distinctly; +4 tests | L4/L5 = live-proven on a real run once a probe runner exists (P2-live, external) | done: a `compare-live` run's Tier-B roll-up is complete — pending probes surface as Tier-B verdicts, not only in Tier-A |
