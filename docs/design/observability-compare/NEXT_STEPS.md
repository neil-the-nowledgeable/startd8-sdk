# compare-live — Next Steps

**Updated:** 2026-07-24 · **Status:** v1 shipped; expanded subject coverage speced (ready for CRP, one open decision)

A roadmap/orientation for the `compare-live` effort — where it stands, the one gate to clear next, and
the sequenced build. Points to the authoritative specs rather than restating them.

---

## Where it stands

| Layer | State | Source |
|---|---|---|
| **Tier-B live replay engine** (`run_validation`) | **shipped** — replays derived PromQL against a live Prometheus, verdict taxonomy, CI gate | `validate_promql.py`, `compare.py` |
| **Single-image standup** (boot 1 subject + Prometheus, warm-up-gate on scrape) | **shipped v1** | `REQUIREMENTS.md`, `live_standup.py` |
| **CLI** `startd8 observability {compare, compare-live, contrast}` | **shipped** | `cli.py:398/433/306` |
| **Gate metrics/histograms** | **shipped** (concurrent) | `compare_live_metrics.py` |
| **Expanded subject coverage** — Inc-1 multi-container, Inc-2 span-metrics | **speced v0.3.2, ready for CRP** | `SUBJECT_COVERAGE_REQUIREMENTS.md` |
| **Traffic driver for Inc-2** (FR-8) | **speced + reuse-mapped** (zero new engine) | `TRAFFIC_DRIVER_REUSE_MAP.md` |

## The one gate before building: CRP on SUBJECT_COVERAGE

`SUBJECT_COVERAGE_REQUIREMENTS.md` v0.3.2 is CRP-ready **but carries one open decision that must be
resolved first (§0.3):**

- **OQ-B / FR-6 contradiction — DECIDE THIS.** FR-6 says "reuse the generalized `generate_compose_dict`,"
  but OQ-B leans toward a **new leaner `observability/live_compose.py`** that reuses only the
  net/DNS/ingress patterns. The coupling is real: `generate_compose_dict` (`benchmark_matrix/fleet/compose.py:79`) validates `ingress` against the **global OB `_SERVICES` registry** (`:94` → `services.py:88`),
  which an arbitrary compare-live subject fails. **Recommendation: the new-leaner-module path** — don't
  couple compare-live to `benchmark_matrix`; generalizing in place would fork the registry validation.
- Also for CRP: multi-container × span-metrics composition (FR-1 topology + FR-4 preset interaction) and
  the Prometheus-is-ingress-on-two-networks detail (both flagged §0.3 Low).

**Action:** run `/new-cnvrg-rvw-prmpt` on `SUBJECT_COVERAGE_REQUIREMENTS.md` (+ this dir's `CRP_FOCUS.md`),
resolve OQ-B, align FR-6, then unblock the build.

## Build sequence (post-CRP)

Each increment reuses the shipped Tier-B replay unchanged; the work is standup topology.

1. **Inc-1 — multi-container standup** (**M-L**). Topology input parser (`--subject-compose`, lean YAML) →
   compose (fleet net + service-DNS + Prometheus-as-ingress) → boot in dep order → reuse `_await_scrape`
   gate → generalized `tear_down`. Landing point for OQ-B (build the leaner `live_compose` here).
2. **FR-8 — warm-up traffic** (**S**, build alongside Inc-1). Drive bounded traffic before the readiness
   gate so lazily-registered RED series (and Inc-2 span-metrics) materialize. **Reuse an existing driver**
   by subject shape — `run_smoke` (generic OpenAPI) / `run_journey_http` (OB HTTP) / `run_journey` (OB
   gRPC). No new engine. Full options: `TRAFFIC_DRIVER_REUSE_MAP.md` + `~/Documents/tools/load-generators/`.
3. **Inc-2 — span-metrics preset** (**M** on top of Inc-1). `--subject-metrics-mode span-metrics`: a 3-node
   preset (subject → `otel/opentelemetry-collector-contrib` running the reused `collector_config` text →
   Prometheus scrapes `collector:8889`). **Depends on FR-8** — without traffic it degrades to always-`unknown`.
   Fail-loud (FR-5).

**Effort:** M-L + S + M — *not* the "2×L from scratch" the backlog implied; the reuse map + FR-8 de-risk the
hardest part (traffic).

## Open decisions / risks (carry into CRP)
- **OQ-B** (above) — the load-bearing architecture call.
- **OQ-A** — topology input format: bespoke lean YAML vs a docker-compose subset. Lean-YAML for v1.
- **FR-8 shape** — host-side driver loop (v1, zero new deps) vs an in-compose locust sidecar (realistic
  load, rides the Inc-1 compose). Recommend host-side loop for v1, sidecar as the upgrade.

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
