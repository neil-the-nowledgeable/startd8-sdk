# compare-live — Next Steps

**Updated:** 2026-07-24 · **Status:** v1 shipped; expanded subject coverage **spec CRP-triaged (v0.4) — ready to build, no open decisions**

A roadmap/orientation for the `compare-live` effort — where it stands and the sequenced build. Points to
the authoritative specs rather than restating them. **The design gate is cleared** (CRP R1 triaged, OQ-B
resolved); the next move is implementation.

---

## Where it stands

| Layer | State | Source |
|---|---|---|
| **Tier-B live replay engine** (`run_validation`) | **shipped** — replays derived PromQL against a live Prometheus, verdict taxonomy, CI gate | `validate_promql.py`, `compare.py` |
| **Single-image standup** (boot 1 subject + Prometheus, warm-up-gate on scrape) | **shipped v1** | `REQUIREMENTS.md`, `live_standup.py` |
| **CLI** `startd8 observability {compare, compare-live, contrast}` | **shipped** | `cli.py:398/433/306` |
| **Gate metrics/histograms** | **shipped** (concurrent) | `compare_live_metrics.py` |
| **Expanded subject coverage** — Inc-1 multi-container, Inc-2 span-metrics | **spec v0.4 — CRP R1 triaged, ready to build** | `SUBJECT_COVERAGE_REQUIREMENTS.md` |
| **Traffic driver for Inc-2** (FR-8) | **speced + reuse-mapped** (zero new engine) | `TRAFFIC_DRIVER_REUSE_MAP.md` |

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

1. **Inc-1 — multi-container standup** (**M-L**). **Build `observability/live_compose.py`** (OQ-B: reuse
   `compose.py` patterns, don't import `benchmark_matrix`) + the topology input parser (`--subject-compose`,
   lean YAML, single-scrape-target boundary + schema per FR-1) → compose (`internal:true` fleet + `edge`,
   service-DNS, Prometheus-as-ingress-on-both-nets) → boot in dep order → `_await_scrape` gate →
   N-container best-effort `tear_down` (FR-7 contract).
2. **FR-8 — warm-up traffic** (**S**, build alongside Inc-1). Drive bounded traffic before the readiness
   gate so lazily-registered RED series (and Inc-2 span-metrics) materialize. **Reuse an existing driver**
   by subject shape — `run_smoke` (generic OpenAPI) / `run_journey_http` (OB HTTP) / `run_journey` (OB
   gRPC). Gate on **non-zero samples AND driver terminal success** (not series-count settling — FR-8/R1-F3/F8);
   driver-can't-exercise ⇒ `unknown` naming the driver. Options: `TRAFFIC_DRIVER_REUSE_MAP.md` +
   `~/Documents/tools/load-generators/`.
3. **Inc-2 — span-metrics preset** (**M** on top of Inc-1). `--subject-metrics-mode span-metrics`: a 3-node
   preset (subject → `otel/opentelemetry-collector-contrib` running the reused `collector_config` text →
   Prometheus scrapes `collector:8889`). **Depends on FR-8** — without traffic it degrades to always-`unknown`.
   Fail-loud (FR-5).

**Effort:** M-L + S + M — *not* the "2×L from scratch" the backlog implied; the reuse map + FR-8 de-risk the
hardest part (traffic).

## Open decisions / risks
- **OQ-A** — topology input format: bespoke lean YAML vs a docker-compose subset. **Lean-YAML for v1**
  (FR-1 pins a concrete schema); revisit if operators want compose-subset familiarity.
- **FR-8 shape** — host-side driver loop (v1, zero new deps) vs an in-compose locust sidecar (realistic
  load, rides the Inc-1 compose). **Recommend host-side loop for v1**, sidecar as the upgrade.
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
- Authoritative spec: **`SUBJECT_COVERAGE_REQUIREMENTS.md`** (v0.3.2). Parent: `REQUIREMENTS.md` (shipped v1).
- Traffic reuse: **`TRAFFIC_DRIVER_REUSE_MAP.md`** + `~/Documents/tools/load-generators/README.md`.
- SLI surfaces already speced/shipped in this dir: `DECLARED_FUNCTIONAL_SLI_*`, `SPANMETRICS_SLI_BINDING_*`,
  `SYNTHETIC_PROBE_P0/P1P3_*`.
- How-to + history: `HOWTO_COMPARE_LIVE.md`, `RETROSPECTIVE.md`, `ENHANCEMENT_BACKLOG.md`, `CRP_FOCUS.md`.
