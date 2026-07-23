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
- **FR-3 Scrape-ready gate (load-bearing).** Poll `sum(scrape_samples_scraped{job=…})>0` via new `prometheus_query.scrape_ready`, with timeout. Timeout → Tier B `unknown` (never `fail`); Tier A gaps still reported.
- **FR-4 Replay via the built engine.** Call `run_validation(...)` against the stood-up URL; consume its `FidelityReport` unchanged. `validate_promql.py` is **not modified** (NR-3).
- **FR-5 Existing-backend path.** `--prometheus <url>` skips standup (the Mastodon/multi-container path). Honors the `--allow-prod` loopback guardrail already in `run_validation`.
- **FR-6 Merge.** `build_live_comparison(comparison, fidelity, standup_status) -> LiveComparisonReport` — pure merge containing Tier A's `ComparisonReport.to_dict()` + Tier B's `FidelityReport.to_dict()`. Rollup severity `unknown > fail > pass`; Tier B authoritative; Tier A advisory unless `--strict-tier-a`.
- **FR-7 CLI.** New `startd8 observability compare-live` verb. Flags: `--manifest/-m`, `--subject-image`, `--subject-port`, `--onboarding-metadata`, `--artifacts-dir`, `--prometheus`, `--allow-prod`, `--keep-up`, `--json`, `--strict-tier-a`, `--baseline`, `--write-baseline`. Exit = `report.exit_code()`. Output redacted via `redact`.
- **FR-8 CI gate.** Verdict identity = `(service, signal, source_file-basename, normalized-expr)` (NOT `live_result_count`). `ci_gate(report, baseline)` → exit **2** on any *new* `fail`, **0** if all fails baselined, **3** if `unknown`. Baseline = committed JSON with a provenance header (image digest, date). `--write-baseline` is explicit-operator-only (NR-4).
- **FR-9 Teardown & safety.** `finally` `tear_down(handle)` removes both containers + network + temp yml, best-effort/never-raises, on every path. Per-run `startd8-cmp-<8hex>` names. `--keep-up` prints the exact `docker rm -f` commands.
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
