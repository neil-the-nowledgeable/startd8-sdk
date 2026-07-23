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

**1. [Built-but-unwired] The CI gate computes *which* SLIs regressed, then throws it away.**
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
- **QW-1 — surface `_new` on a gate failure** — *(= Top finding 1)* `cli.py:514`. **XS–S.**
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
