# compare-live — Next Steps

**Updated:** 2026-07-24 · **Status:** ✅ **expanded-subject-coverage roadmap COMPLETE** — v1 + Inc-1 (multi-container) + FR-8 (warm-up traffic) + Inc-2 (span-metrics preset) all shipped. Remaining items are the explicit deferrals (NR-A..D).

A roadmap/orientation for the `compare-live` effort — where it stands and the sequenced build. Points to
the authoritative specs rather than restating them. **All three build-sequence increments (Inc-1, FR-8,
Inc-2) are now shipped**; what remains are the explicit non-goals (NR-A..D) — real-compose ingestion, k8s
standup, cross-service scoring — each an ADR-gated future increment, not a loose end.

---

## Where it stands

| Layer | State | Source |
|---|---|---|
| **Tier-B live replay engine** (`run_validation`) | **shipped** — replays derived PromQL against a live Prometheus, verdict taxonomy, CI gate | `validate_promql.py`, `compare.py` |
| **Single-image standup** (boot 1 subject + Prometheus, warm-up-gate on scrape) | **shipped v1** | `REQUIREMENTS.md`, `live_standup.py` |
| **CLI** `startd8 observability {compare, compare-live, contrast}` | **shipped** | `cli.py:398/433/306` |
| **Gate metrics/histograms** | **shipped** (concurrent) | `compare_live_metrics.py` |
| **Inc-1 — multi-container standup** (`--subject-compose`, lean topology → two-network compose → warm-up gate → N-container teardown) | **shipped** — `live_compose.py`, wired into `run_live_comparison` + CLI | `live_compose.py`, `compare_live.py:262`, `cli.py` |
| **Expanded subject coverage** — Inc-2 span-metrics | **spec v0.4 — CRP R1 triaged, ready to build** | `SUBJECT_COVERAGE_REQUIREMENTS.md` |
| **FR-8 — warm-up traffic** (`--warm-up {smoke,ob-http,ob-grpc}`, bounded driver loop, two-part convergence) | **shipped** — `warmup_traffic.py`, wired into `live_compose` standup + CLI | `warmup_traffic.py`, `live_compose.py`, `TRAFFIC_DRIVER_REUSE_MAP.md` |
| **Inc-2 — span-metrics preset** (`--subject-metrics-mode span-metrics`: subject→collector-contrib→Prometheus scrapes `collector:8889`) | **shipped** — `SpanMetricsWiring` + `stand_up_compose_subject(span_metrics=…)`, reuses `runtime_fidelity.collector_config` + FR-8 warm-up | `live_compose.py`, `cli.py` |

## Design gate — CLEARED (CRP R1 triaged 2026-07-24)

`SUBJECT_COVERAGE_REQUIREMENTS.md` is **v0.4 — ready to build, no open decisions**. CRP R1 (Appendix C) was
triaged, all 9 suggestions applied (Appendix A). Key resolutions:

- **OQ-B RESOLVED → build a new `observability/live_compose.py`** that reuses `compose.py`'s
  net/DNS/ingress/dep-env *patterns* **without** importing `benchmark_matrix`'s OB registry. (CRP corrected
  the coupling: **3** registry sites, not 2 — the dep-edge fan-out `get_service(dep_name)` at
  `compose.py:57` is the one that actually breaks an arbitrary subject.)
- **FR-8 convergence hardened** — gate on `sum(increase(<hist>_count[…]))>0` **AND** driver terminal
  success (not series-count settling, which greens on registered-but-empty histograms); driver-can't-
  exercise ⇒ `unknown` naming the driver.
- **FR-1** single-scrape-target v1 boundary + schema/example; **FR-2** framed as new networking (not reuse
  of the plain-bridge standup); **FR-7** N-container best-effort teardown contract.

**No further review needed to start.** (An optional second-model CRP R2 on v0.4 is available for
cross-model coverage of the OQ-B call, but R1's findings were grounded corrections and the spec is solid.)

## Build sequence

Each increment reuses the shipped Tier-B replay unchanged; the work is standup topology.

1. **Inc-1 — multi-container standup** (**M-L**). ✅ **SHIPPED.** `observability/live_compose.py` (new leaner
   compose builder — reuses `compose.py`'s net/DNS/ingress/dep-env *patterns*, does **not** import
   `benchmark_matrix`) + the topology input parser (`--subject-compose`, lean YAML, single-scrape-target
   boundary + FR-1 schema, fail-loud `TopologyError`) → two-network compose (`internal:true` fleet + `edge`,
   service-DNS, Prometheus-as-ingress-on-both-nets) → `docker compose up -d` in dep order → the **reused**
   `_await_scrape` gate → N-container best-effort `tear_down_compose` (FR-7: project name = sole ownership
   key, leaked-count not raise). Wired as Tier-B Path 2 in `run_live_comparison` (precedence: `--prometheus`
   > `--subject-compose` > `--subject-image`). Zero-docker unit tests: `test_live_compose.py` (23) +
   compose-orchestration cases in `test_compare_live.py`.
2. **FR-8 — warm-up traffic** (**S**). ✅ **SHIPPED.** `observability/warmup_traffic.py` selects an existing
   driver by subject shape (`run_smoke` generic OpenAPI / `run_journey_http` OB HTTP / `run_journey` OB gRPC),
   drives a **bounded loop** at the subject ingress, and returns `WarmupOutcome(exercised, terminal_success)`.
   `evaluate_warmup` is the two-part gate: driver **terminal success** AND `sum(increase(<metric>[1m]))>0`
   (never series-count settling — FR-8/R1-F3/F8); driver-can't-exercise ⇒ `unknown` naming the driver (R1-F5).
   Wired into `stand_up_compose_subject` (`--warm-up` publishes the `metrics_service` as a host ingress; HTTP
   shapes drive host-side, `ob-grpc` deferred to an in-fleet driver) + `--warm-up`/`--warm-up-metric` CLI.
   Zero-network unit tests: `test_warmup_traffic.py` + standup-warm-up cases in `test_live_compose.py`.
3. **Inc-2 — span-metrics preset** (**M** on top of Inc-1). ✅ **SHIPPED.**
   `--subject-metrics-mode span-metrics`: the 3-node preset (subject with
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317` → `otel/opentelemetry-collector-contrib` running the
   reused `runtime_fidelity.collector_config` text → Prometheus scrapes `collector:8889`, not the subject).
   `SpanMetricsWiring` + `stand_up_compose_subject(span_metrics=True, otlp_app=…)`; the collector config is
   written with `0.0.0.0` endpoints so peers reach it. Pairs with the shipped FR-8 warm-up + a span-metric
   `--warm-up-metric` (e.g. `traces_spanmetrics_calls_total`); no traffic ⇒ `unknown`, fail-loud (FR-5).

**Effort (actual):** M-L + S + M, all shipped — *not* the "2×L from scratch" the backlog implied; the reuse
map + FR-8 de-risked the hardest part (traffic), and Inc-2 was a thin preset over Inc-1's mechanism.

## Open decisions / risks
- **OQ-A** — topology input format: bespoke lean YAML vs a docker-compose subset. **Lean-YAML for v1**
  (FR-1 pins a concrete schema); revisit if operators want compose-subset familiarity.
- *(FR-8 shape RESOLVED — host-side driver loop shipped for v1 (HTTP shapes: `smoke`/`ob-http`); `ob-grpc`
  and the in-compose locust sidecar remain the realistic-load upgrade.)*
- *(OQ-B resolved by CRP R1 — new `live_compose.py`; see the design-gate section.)*

## Deferred (explicit non-goals for now)
- **NR-A / Inc-3** — consuming a real `docker-compose.yml` verbatim (volumes/healthchecks/build).
- **NR-B** — Kubernetes / non-docker standup.
- **NR-C/D** — changing the Tier-B engine / verdict taxonomy; cross-service scoring (that's the round-3
  fleet benchmark, not compare-live).

## Notes / gotchas for whoever picks this up
- **Run tests with the OTel SDK ENABLED.** `test_compare_live_metrics.py::test_records_gate_runs_and_histograms` needs the meter provider — `OTEL_SDK_DISABLED=true` makes `resource_metrics` `None` and the test
  falsely "fails." (This masqueraded as a flaky failure until grounded 2026-07-24.)
- **The traffic mechanism is proven** — see the Mastodon runbook in `TRAFFIC_DRIVER_REUSE_MAP.md §3`:
  "POST N× → `traces_spanmetrics_*` histograms materialize." That *is* FR-8's warm-up.
- **Formatting:** don't run `black` on touched files ad-hoc — the repo has no enforced black standard
  (issue #334); a stray reformat churns unrelated lines. Match surrounding style until #334 lands.
- **Concurrency:** this area sees multiple agents (the #328/#332 merges). Branch off `origin/main`,
  keep diffs logic-only, verify `gh pr view … mergeable` before merging.

## Pointers
- Authoritative spec: **`SUBJECT_COVERAGE_REQUIREMENTS.md`** (v0.4). Parent: `REQUIREMENTS.md` (shipped v1).
- Traffic reuse: **`TRAFFIC_DRIVER_REUSE_MAP.md`** + `~/Documents/tools/load-generators/README.md`.
- SLI surfaces already speced/shipped in this dir: `DECLARED_FUNCTIONAL_SLI_*`, `SPANMETRICS_SLI_BINDING_*`,
  `SYNTHETIC_PROBE_P0/P1P3_*`.
- How-to + history: `HOWTO_COMPARE_LIVE.md`, `RETROSPECTIVE.md`, `ENHANCEMENT_BACKLOG.md`, `CRP_FOCUS.md`.
