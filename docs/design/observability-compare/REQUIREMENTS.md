# Observability Derived-vs-Emitted Comparison — Tier B (live fidelity) + CI gate — Requirements

**Version:** 0.3.1 (post reflective-requirements loop + lessons/principle hardening)
**Date:** 2026-07-22
**Status:** Approved for implementation
**Parent proposal:** `docs/design/OBSERVABILITY_DERIVED_VS_EMITTED_COMPARISON.md` (PR #281)
**Tier A (predecessor):** shipped as `startd8 observability compare` (PR #282, `de5f40a3`)

---

## 0. Planning Insights (self-reflective update)

> The planning pass against real code corrected the proposal's framing in four material ways.

| v0.1 assumption (from the proposal) | Planning discovery | Impact |
|---|---|---|
| Tier A is "being prototyped in parallel" (in flight) | Tier A **already landed on `main`** (`de5f40a3`, PR #282): `observability/compare.py` + the `compare` verb, with tests | Tier B treats Tier A as a **read-only dependency**, importing `ComparisonReport`/`build_comparison_report`/`read_fr_coverage`. No collision; no edits to `compare.py`. |
| "reuse `fleet.compose` (relax egress-deny → edge net)" | `generate_compose_dict` is **fleet-ServiceSpec-shaped** (OB 8-service inventory), `internal:true` at `compose.py:115`; **no Prometheus concept exists anywhere** in `src/` | Don't bend the fleet projector. Build a small purpose-built `live_standup.py` (subject `docker run` + a `prom/prometheus` sibling on a shared bridge + generated `prometheus.yml`). |
| Mastodon is the hero subject to *stand up* | Mastodon = Postgres+Redis+Sidekiq+assets = **multi-container**; one `subject_image` can't stand it up | **v1 = single-image subjects.** Mastodon is validated via `--prometheus <existing-backend>` (skip standup). Multi-container standup deferred (NR-1). |
| "wait for a scrape, then invoke validate-promql" | Without a scrape-landed gate, replay runs against an empty TSDB → **every query falsely reads `fail`**, indistinguishable from a genuinely dead SLI | A **load-bearing scrape-ready gate** (`scrape_samples_scraped>0`) is first-class; its timeout maps to `unknown`, never `fail`. |

**Resolved open questions:**
- **OQ-1 (subject network wiring) → `live_standup` owns the subject `docker run`** (threads `--network`), reusing only `_await_port_ready`/`docker_available` *semantics* from `benchmark_matrix/fleet/containerize.py` — no edit to that tracked module. Gate on scrape-ready (it subsumes the subject TCP gate).
- **OQ-2 (CLI shape) → separate `compare-live` verb** (+ new `compare_live.py`). User-confirmed.
- **OQ-3 (subject scope) → single-image v1.** User-confirmed.
- **OQ-4 (scrape signal) → `sum(scrape_samples_scraped{job="subject"})>0`**, `scrape_interval=5s`, `scrape_timeout≈60s`.
- **OQ-5 (status precedence) → Tier B authoritative** — a Tier B `fail` dominates a Tier A pass; Tier A advisory by default (`--strict-tier-a` opt-in).

### 0.1 Lessons-Learned Hardening
Consulted the SDK lessons base. Applied:
- **Phantom-reference audit** — every symbol this spec names (`run_validation`, `FidelityReport`, `redact`, `Auth`, `_is_local_backend`, `_await_port_ready`, `docker_available`, `ComparisonReport`, `read_fr_coverage`) was grep-verified to exist at the cited path before speccing against it (see §Reference Audit).
- **Single-source vocabulary ownership** — the verdict taxonomy (`pass|bound_no_data|fail|error|excluded`) and exit codes (0/2/3) are **owned by `validate_promql.py`** and imported, never restated/redefined here.

### 0.2 Design-Principle Hardening
Checked the `docs/design-princples/` set. Applied:
- **Genchi Genbutsu** — the whole capability *is* this principle: bind derived artifacts to the subject's **real** emission, not a convention/proxy. The scrape-ready gate enforces "go and see the *actual* scraped samples" before judging.
- **Mottainai** — reuse the built engine (`run_validation`) and Tier A (`build_comparison_report`) verbatim; do not re-derive verdicts or re-parse PromQL. One canonical Prometheus client (`prometheus_query`) gets the new `scrape_ready` primitive rather than a second ad-hoc HTTP call.
- **Accidental-complexity anti-principle** — chose one purpose-built standup over bending the fleet projector with a Prometheus special-case; the CI gate is one baseline-diff rule, not an allowlist of accepted-fail services.
- **Context-Correctness-by-Construction** — standup/scrape failure yields `unknown` (fail-loud), never a silent green; teardown runs in `finally` on every path.

---

## 1. Problem Statement

The generator's claim is *"derive real o11y from declared shape."* The only proof is checking derived
SLIs/alerts/dashboards against the subject's **actual emission**. Tier A (shipped) reports *static*
divergence from the manifest's `fr_coverage`. Tier B — this doc — is the **authoritative** check:
replay the derived PromQL against a live Prometheus scraping the real subject and categorize each SLI
`pass` / `bound_no_data` / `fail`. The `fail` verdict is exactly the #274 (dead metric) / #275 (wrong
label) bug class. A CI gate on *new* `fail`s prevents the regression from ever shipping silently again.

| Component | Current state | Gap |
|---|---|---|
| PromQL replay engine | `validate_promql.run_validation` — built, validated 2026-07-22 | none (reused as-is) |
| Prometheus client | `prometheus_query` — built | needs a `scrape_ready` primitive |
| Subject+Prometheus standup | — | **absent** — the real build |
| Tier A static report | `compare.py` — shipped (#282) | reused read-only |
| CI regression gate | — | **absent** — baseline-diff on new `fail`s |

---

## 2. Requirements

- **FR-1 Single-image standup.** Given `--subject-image` (+ `--subject-port`, default 8080), stand up the subject and `prom/prometheus` on a shared per-run bridge; Prometheus scrapes `subject:<port><metrics-path>` by Docker service-DNS.
- **FR-2 Generated scrape config.** `render_prometheus_yml(*, job_name, target_host, target_port, metrics_path="/metrics", scrape_interval="5s") -> str` — pure, unit-testable.
- **FR-3 Warm-up gate (load-bearing).** Two-phase: (1) samples have landed (`sum(scrape_samples_scraped{job=…})>0` via `prometheus_query.scrape_ready`), **and** (2) the job's series set has **settled** — `count({job=…})>0` and unchanged across two consecutive scrapes (`job_series_count`). The poll cadence is `>=` the scrape interval so each stability comparison spans a fresh scrape. This closes the warm-up race (R1-F1/F2): gating on the first landed sample alone would release before lazily-registered SLI series (lazy histograms, first-request counters) appear, surfacing a false `fail`. Timeout → Tier B `unknown` (never `fail`); Tier A gaps still reported.
- **FR-4 Replay via the built engine.** Call `run_validation(...)` against the stood-up URL; consume its `FidelityReport` unchanged. `validate_promql.py` is **not modified** (NR-3).
- **FR-5 Existing-backend path.** `--prometheus <url>` skips standup (the Mastodon/multi-container path). Honors the `--allow-prod` loopback guardrail already in `run_validation`.
- **FR-6 Merge.** `build_live_comparison(comparison, fidelity, standup_status) -> LiveComparisonReport` — pure merge containing Tier A's `ComparisonReport.to_dict()` + Tier B's `FidelityReport.to_dict()`. Rollup severity `unknown > fail > pass`; Tier B authoritative; Tier A advisory unless `--strict-tier-a`.
- **FR-7 CLI.** New `startd8 observability compare-live` verb. Flags: `--manifest/-m`, `--subject-image`, `--subject-port`, `--onboarding-metadata`, `--artifacts-dir`, `--prometheus`, `--allow-prod`, `--keep-up`, `--json`, `--strict-tier-a`, `--baseline`, `--write-baseline`. Exit = `report.exit_code()`. Output redacted via `redact`.
- **FR-8 CI gate.** Verdict identity = `(service, signal, dir-qualified-source, normalized-expr)` (NOT `live_result_count`; dir-qualified to survive same-basename files across artifact dirs — R1-F8). `ci_gate(report, baseline)` → exit **2** on any *new* `fail`, **0** if all fails baselined, **3** if `unknown`. Baseline = committed JSON with a provenance header. `--write-baseline` is explicit-operator-only (NR-4). **Wired in CI** via `.github/workflows/observability-compare-live-gate.yml` → `scripts/compare_live_gate.sh` against a pinned self-scraping `prom/prometheus` reference subject, with the committed baseline + repeatable pilot fixture at `docs/design/observability-compare/pilot-repro/` (reproduces #274 suppression + #275 label).
  - **FR-8a Surface the regression set (EB-1).** On a gate **FAIL** the CLI MUST report *which* verdicts are new-vs-baseline — the regression *this change* introduced — not merely that something is dead. The human path prints a distinct `NEW dead SLI(s) vs baseline` block; `--json` carries a top-level `new_fail_verdicts` array. The set is **already computed** (`ci_gate` → `new_fails` / `new_fail_verdicts`); the requirement is that it **reach the operator**, not be discarded (it currently is — `cli.py` `code, _new = ci_gate(...)`). Output stays secret-redacted (FR-7). *Acceptance:* a `--baseline` run with a new dead SLI prints/emits that SLI's identity; a clean run prints nothing extra and exits 0.
- **FR-8b Apply the diagnosed profile fix (EB-1 sibling).** When a run surfaces a `suggested_metrics_profile` (the one-line fix the report already prints), `compare-live --apply-profile-fix` writes it to `spec.observability.metricsProfile` in `--manifest`, reusing `bind_and_verify.write_project_profile` (the manifest-writer that already exists). It is:
  - **explicit-operator-only** (like `--write-baseline`, NR-4) — never applied implicitly by a gate run; mutating a tracked file is opt-in.
  - **the manifest half, not a full auto-fix** — the confirmation MUST state that regeneration is required for the SLIs to change (writing the profile alone changes no query).
  - **a no-op with a clear message when there is no single suggested profile** (`suggested_metrics_profile == ""`, e.g. the real fix is a per-axis override) — never write an empty/garbage profile.
  - **honest about lossiness** — `write_project_profile` is a plain-YAML round-trip that does not preserve comments; the confirmation MUST warn the operator of this on their real manifest.
  - **project-scope** (the suggestion is a run-wide majority vote, `validate_promql` `_profile_votes.most_common(1)`); per-target overrides are out of v1 scope.
  *Acceptance:* on a run with a suggested profile, `--apply-profile-fix` sets `spec.observability.metricsProfile` in the manifest + prints a "regenerate to take effect" confirmation; on a run with none, it writes nothing and says so.
- **FR-9 Teardown & safety.** `finally` `tear_down(handle)` removes both containers + network + temp yml, best-effort/never-raises, on every path. Per-run `startd8-cmp-<8hex>` names. `--keep-up` prints the exact `docker rm -f` commands. **Operator recovery (R1-F6):** the `startd8-cmp-` prefix is a stable contract — after a SIGKILL/OOM where `finally` never ran, `docker rm -f $(docker ps -aq --filter name=startd8-cmp)` + `docker network rm $(docker network ls -q --filter name=startd8-cmp)` sweeps every orphan.
- **FR-10 Injectable seams.** `standup_fn`, `teardown_fn`, `validate_fn`, `read_fr_coverage_fn`, `scrape_ready_check`, `runner` all injectable — merge/gate/argv logic fully unit-tested with **zero docker** (mirrors `bind_and_verify`).

## 3. Non-Requirements
- **NR-1** Multi-container subject standup (Mastodon PG+Redis+Sidekiq) — deferred; reach via `--prometheus <existing>`.
- **NR-2** OTel-collector-fronted (span-metrics) subjects — that is `runtime_fidelity.SpanMetricsCollector`; v1 = direct `/metrics` scrape only.
- **NR-3** Modifying `validate_promql.py` or `compare.py` — both read-only.
- **NR-4** Automatic baseline updates — the gate must never self-heal.

## 4. Reference Audit (phantom-reference check)
| Symbol | Path | Verified |
|---|---|---|
| `run_validation`, `FidelityReport`, `ExprVerdict`, `redact`, `EXIT_{PASS,FAIL,UNKNOWN}`, `_is_local_backend` | `observability/validate_promql.py` | ✓ |
| `Auth`, `instant_query_count`, `REQUEST_TIMEOUT` | `observability/prometheus_query.py` | ✓ |
| `ComparisonReport`, `build_comparison_report`, `read_fr_coverage` | `observability/compare.py` | ✓ |
| `_await_port_ready`, `docker_available`, `_container_logs` | `benchmark_matrix/fleet/containerize.py` | ✓ |

---

*v0.3.1 — post-planning + lessons + design-principle hardening. 4 assumptions corrected, 5 OQs resolved. Ready to implement.*

*v0.4 — post CRP Round R1 (16 suggestions). Applied 8 (incl. 4 real code bugs: verdict_id cross-dir collision, write-baseline-on-unknown self-heal, write-baseline exit code, missing `--metrics-path`); deferred 4 with rationale (warm-up gate, per-series warmth, digest pin). Dispositions in Appendix A/B.*

*v0.4.1 — closed the deferred warm-up gate (R1-F1/F2): FR-3 is now a two-phase settle gate (samples landed + series-set stable across two consecutive scrapes). Digest-pin (R1-S7) remains the only open deferral.*

*v0.4.2 — added FR-8a (surface the new-vs-baseline regression set on a gate FAIL): the ENHANCEMENT_BACKLOG lead finding — `ci_gate` already computes `new_fails` but the CLI discarded it, so a red gate never said *which* SLIs regressed.*

*v0.4.3 — added FR-8b (`--apply-profile-fix`): apply the diagnosed `metricsProfile` to the manifest via the existing `bind_and_verify.write_project_profile` — closing the diagnose→fix half. Explicit-only, no-op when no single profile fixes it, warns comments aren't preserved, requires regenerate.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F8 / R1-S2 | `verdict_id` cross-dir basename collision | CRP R1 | Fixed: `_source_key` uses the dir-qualified last-two path components, not bare basename. Tests `test_verdict_id_distinguishes_same_basename_different_dirs`, `test_ci_gate_new_fail_in_second_dir_not_masked_by_baseline`. | 2026-07-22 |
| R1-F4 / R1-S3 | `--write-baseline` on `unknown` silently zeroes baseline (NR-4 self-heal) | CRP R1 | Fixed: CLI refuses `--write-baseline` when `report.status == "unknown"`, exits 3, leaves baseline untouched. | 2026-07-22 |
| R1-F5 | `--write-baseline` run inherits `report.exit_code()` → red-X's the baseline commit | CRP R1 | Fixed: authoring exits 0 (not a gate). | 2026-07-22 |
| R1-F3 / R1-S5 | `--metrics-path` not exposed though renderer supports it | CRP R1 | Fixed: added `--metrics-path` flag, threaded through `run_live_comparison` → `stand_up_subject_and_prometheus`. | 2026-07-22 |
| R1-F7 | Freeze `--json` merged-report schema as a versioned contract | CRP R1 | Fixed: `LiveComparisonReport.REPORT_VERSION=1`, emitted as `report_version`. Test `test_report_carries_a_versioned_schema`. | 2026-07-22 |
| R1-S1 | Tier-A gap count must be surfaced on an overall Tier-B `pass` | CRP R1 | Made load-bearing: `_rollup_reason` includes the advisory gap count on pass. Test `test_pass_with_advisory_gaps_surfaces_gap_count`. | 2026-07-22 |
| R1-S6 | Leak check must assert network + tempfile gone, not only containers | CRP R1 | Fixed: integration test asserts `_network_gone` + `prometheus_yml_path` unlinked. | 2026-07-22 |
| R1-S8 | `--allow-prod` is inert on the standup path (comprehension risk) | CRP R1 | Fixed (doc): flag help states it is a no-op on `--subject-image` (Prometheus always loopback). | 2026-07-22 |

### Appendix B: Rejected / Deferred Suggestions (with Rationale)

| ID | Suggestion | Source | Disposition & Rationale | Date |
|----|------------|--------|-------------------------|------|
| R1-F1 / R1-S4 | Gate on **two consecutive** scrapes (warm-up race) | CRP R1 | **Applied 2026-07-23** — `_await_scrape` now requires two consecutive scrapes agreeing on the job's series count (`job_series_count` = `count({job=…})`), polled `>=` the scrape interval so each comparison spans a fresh scrape. Tests `test_await_scrape_waits_for_series_to_settle`, `test_await_scrape_ready_but_series_never_stable_times_out`. | 2026-07-23 |
| R1-F2 | A `fail` must require a **confirmed-live** subject (per-series), else `unknown` | CRP R1 | **Applied 2026-07-23 (via F1)** — the settle gate uses the job's *series-set size stabilizing* as the warm proxy: it will not release while lazy SLI series are still registering, so a not-yet-warm subject stays `unknown` (gate un-passed) rather than replaying into a false `fail`. Full per-metric warmth remains a `validate_promql`-level concern (NR-3, not modified here). | 2026-07-23 |
| R1-F6 | SIGKILL/OOM orphan-recovery contract (naming prefix as a stable sweep contract) | CRP R1 | **Partially accepted** — the network/tempfile leak assertions (S6) applied; the `startd8-cmp-<hex>` naming is documented in FR-9 as a stable operator-recovery prefix (`docker … --filter name=startd8-cmp`). | 2026-07-22 |
| R1-S7 | Pin `prom/prometheus@sha256:…` instead of a floating tag | CRP R1 | **Decision (not now)** — v1 keeps the `:v2.53.0` tag; pinning an unverifiable digest offline is itself risky. Digest-pin + pre-pull is the documented pre-1.0 hardening step (module docstring + FR-9/R3). Not re-propose without an airgapped-CI trigger. | 2026-07-22 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-23 03:20:00 UTC
- **Scope**: Requirements review grounded against the SHIPPED implementation (`live_standup.py`, `compare_live.py`, `prometheus_query.scrape_ready`, `cli.py compare-live`). Weighted per CRP_FOCUS: scrape-ready gate semantics, merge rollup, CI-gate identity stability, teardown/leak safety, localhost/allow-prod guardrail. No prior rounds — this is R1.

##### Focus-file asks (addressed first, per prompt template; orchestrator triages later)

**Ask 1 — Scrape-ready gate signal (`scrape_samples_scraped>0` vs `up==1` vs both).**
- **Summary answer:** partial — `scrape_samples_scraped>0` is the correct *primary* signal, but the gate is under-specified for the warm-up race the focus names.
- **Rationale:** `prometheus_query.scrape_ready` (shipped) gates on `sum(scrape_samples_scraped{job=…})>0`, correctly stronger than `up==1` (which only proves the target responded). But FR-3 does not require that the *specific replayed SLI series* exist — a subject can expose `/metrics` with a positive sample count while the SLI-relevant series appear only after warm-up, so the gate passes and Tier B still reads a false `fail`.
- **Assumptions / conditions:** subjects whose SLI metrics are lazily registered (first request, first GC, first histogram observation) exist among target subjects.
- **Suggested improvements:** see R1-F1 (warm-up second-scrape requirement) and R1-F2 (distinguish "no series at all" from "series absent" in the timeout→unknown mapping).

**Ask 2 — timeout→`unknown` (never `fail`) load-bearing correctness.**
- **Summary answer:** yes, correct and load-bearing — but the *inverse* leak (a subject that scrapes but whose SLIs are all genuinely dead) is indistinguishable from warm-up under the current single-gate spec.
- **Rationale:** §0 row 4 and FR-3 correctly map timeout→`unknown`. The shipped `build_live_comparison` returns `unknown` when `fidelity is None`. The gap is upstream: FR-3 gives no minimum-sample or two-consecutive-scrape criterion, so "one scrape landed" is treated as "fully warm."
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F1.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | FR-3: require the scrape-ready gate to observe **two consecutive scrapes** (or `scrape_samples_scraped>0` sustained across ≥2 poll intervals), not a single landed sample, before declaring ready. State the warm-up caveat explicitly as an acceptance criterion. | Focus Ask 1: a subject can expose `/metrics` with a positive sample count while the specific SLI series register only after warm-up (lazy histograms, first-request counters). A single-scrape gate passes, replay runs, and reads a false `fail` — the exact false-negative Tier B exists to prevent. | FR-3 (§2) | Unit: inject a `scrape_ready_check` returning True on first call but with SLI series still empty; assert the gate does not release until the second confirmation. |
| R1-F2 | Data | medium | FR-8/FR-6: define what a `fail` verdict means when the subject scraped successfully but a series is absent vs. when the whole TSDB is thin. Add an acceptance criterion that a `fail` requires a **confirmed-live subject** (scrape_ready true) — otherwise it must be `unknown`, not `fail`. | The spec asserts timeout→`unknown` but does not close the symmetric case: partial warm-up (scrape_ready true, but the SLI's series never appeared) currently yields `fail`, conflating "generator emitted wrong metric" (#274) with "subject not warm." Ground truth: `build_live_comparison` only branches on `fidelity is None`, never on per-verdict warmth. | FR-3 / FR-6 (§2) | Manual: stand up a subject with a lazily-registered SLI; assert the SLI reports `bound_no_data`/`unknown`, not `fail`, before it is exercised. |
| R1-F3 | Interfaces | medium | FR-7: add `--metrics-path` and `--scrape-interval` flags to the verb, or state explicitly that `/metrics` and `5s` are fixed for v1. `render_prometheus_yml` already parameterizes both, but the CLI hard-codes them (`cli.py` exposes neither). | FR-7's flag list omits `--metrics-path`; many subjects expose `/actuator/prometheus`, `/-/metrics`, etc. The shipped `render_prometheus_yml(metrics_path=…)` supports it but the operator cannot reach it, so any non-`/metrics` subject silently produces an all-`fail`/`unknown` report with no operator recourse. | FR-7 flag list (§2) | Verify `compare-live --metrics-path /actuator/prometheus` threads through to the generated `prometheus.yml` job. |
| R1-F4 | Security | high | FR-8/NR-4: require that `--write-baseline` refuse (error, non-zero) when `report.status != "pass"`-with-fails is `unknown`, i.e. never persist a baseline derived from a run where standup/scrape failed. State: a baseline may only be written from a **confirmed-live** report. | NR-4 says the gate must never self-heal, but the shipped `render_baseline` reads `report.fail_verdicts`, which is **empty on an `unknown` report** (standup failed). `--write-baseline` on a failed standup silently writes `accepted_fail_ids: []` — erasing a real baseline and defeating the gate on the next run. | FR-8 (§2), NR-4 (§3) | Unit: call the baseline writer with an `unknown` report; assert it raises / refuses rather than emitting an empty `accepted_fail_ids`. |
| R1-F5 | Ops | medium | FR-8: specify the **exit code of a `--write-baseline` run**. State it should exit 0 (baseline authoring is not a gate). Currently the CLI runs `report.exit_code()` after writing, so re-baselining a subject that has fails exits 2. | The shipped `cli.py` guards `ci_gate` behind `not write_baseline` (good) but then falls through to `raise typer.Exit(report.exit_code())` — so an operator re-baselining a known-failing subject gets a non-zero exit, which in CI is indistinguishable from a gate failure and will red-X the very commit that records the accepted baseline. | FR-8 (§2) | Verify `compare-live --write-baseline --baseline X` on a subject with dead SLIs exits 0. |
| R1-F6 | Risks | medium | FR-9: add an acceptance criterion that the **temp `prometheus.yml` is removed even when standup returns before `prometheus_yml_path` is set**, and that orphan `startd8-cmp-*` resources from a killed process (no `finally` reached, e.g. SIGKILL) are documented as operator-recoverable via a single `docker … --filter name=startd8-cmp` sweep. | FR-9 covers the `finally` path but not the SIGKILL/OOM path where Python never runs teardown. The per-run `startd8-cmp-<hex>` naming (shipped) makes a bulk sweep possible, but the spec never promises the naming prefix is a **stable, greppable contract** an operator can rely on for recovery. | FR-9 (§2) | Manual: `kill -9` a mid-flight run; verify `docker ps -a --filter name=startd8-cmp` + `docker network ls --filter name=startd8-cmp` surface every leaked resource for a one-command cleanup. |
| R1-F7 | Interfaces | low | FR-6: name and freeze the merged-report JSON schema (the keys `status/reason/total_gaps/fail_verdicts/tier_a/tier_b/standup`) as a versioned contract, since `--json` output is the machine surface CI parses. | `LiveComparisonReport.to_dict()` is the CI-consumed contract but FR-6/FR-7 describe it only prosaically. A downstream CI job keying on `fail_verdicts[].service` will break silently if the shape drifts. Ground: no schema/version field on the emitted dict. | FR-6 / FR-7 (§2) | Add a schema-snapshot test over `to_dict()` keys; bump a `report_version` on change. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Data | medium | FR-8: specify collision behavior for `verdict_id` when two distinct SLIs share `(service, signal, basename)` but differ only in expr, AND when the same SLI moves between two source dirs with the same basename. Require the identity to include a **relative path fragment or a content hash**, not bare `os.path.basename`. | Focus Ask (CI-gate identity): the shipped `verdict_id` uses `os.path.basename(source_file)`, so `alerts/foo.yaml` and `dashboards/foo.yaml` collide; a genuinely-new dead SLI in the second file can normalize onto a baselined id and slip the gate (exit 0 when it should be 2). | FR-8 identity tuple (§2) | Unit: two verdicts with identical basename from different dirs; assert distinct `verdict_id`; assert a new fail in the second is NOT masked by the first's baseline entry. |

