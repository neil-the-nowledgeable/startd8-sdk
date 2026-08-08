# Metric Activation Taxonomy — SDK consumer reference

> **Owner: ContextCore** (the `activation` field is populated in the subject-surface `groundtruth.json`;
> definition + rollout = **contextcore#406**, paired with **#404** `unit`). This doc is the **SDK
> consumer-side** reference — how the generator/harness *uses* `activation` — a sibling to
> [`CROSS_REPO_VOCABULARY_PARITY_GUARD.md`](./CROSS_REPO_VOCABULARY_PARITY_GUARD.md). It is not the
> normative definition; point up to the canonical repoprobe doc when #406 lands.

## Why it exists — the two-layer problem

Generated observability has two correctness layers:
- **Generation** (static, contract-driven): right series name / unit / kind / target. Correct regardless of load.
- **Liveness** (runtime): does the SLI actually *evaluate*? A Prometheus histogram/summary child series
  (`*_bucket{le,…}` / `{quantile}`) is **lazily registered — it has no data until traffic is observed.**

So a *correct* SLI can be dead purely because no load registered its series. Without a per-metric
activation classification, an **unbound-live SLI is ambiguous** — a real binding bug, or just missing load —
and the pilot pipeline "chases its tail" filing `sdk_code` fixes for what is actually a `workload` gap.

## The four categories (SLO-liveness axis)

| `activation` | Meaning | SLI behavior | Owner if unbound-live |
|---|---|---|---|
| **`boot`** (always-on) | registers at process start; scrape returns a value immediately | live without load | real defect immediately |
| **`load:<step>`** | child series lazily registered on first observation (histogram/summary children, labeled counters) | dead until the matching warm-up traffic runs | **`workload`** if the step wasn't driven; **`sdk_code`/`manifest_data`** only if it *was* driven and still wrong |
| **`state:<condition>`** | series exists but reads trivially (0) until a specific state holds (queue backed up, error, saturation) | evaluates but meaningless; often undrivable by generic load | **generation-layer score only** — liveness = N/A, don't penalize |
| **`flag:<name>`** | only exists if an exporter/feature flag is on | absent unless enabled | omit/gate (RepoProbe's existing `activation` semantics) |

**Grounded (Harbor, 28 metric families):** ~20 `boot` (DB-snapshot gauges) · ~6 `load` (the RED request tail:
summary-quantile latency + labeled request counters) · 2 `state` (`harbor_task_queue_latency/_size`) · 0 `flag`.
The **`load` tail is a minority** — and it's the same tail the unit-sensitive latency fix (F1,
[`REQ-declared-latency-unit-scaling.md`](./REQ-declared-latency-unit-scaling.md)) lives on. `unit` + `activation`
are two properties of that one tail; #404 + #406 pair for that reason.

## The SDK's three roles (what "consume `activation`" means here)

1. **Execution — drive the `load:` traffic.** compare-live already drives warm-up traffic
   (`--warm-up workload` / `--workload-spec`, `live_compose`/`compare_live.py`) so lazily-registered series
   materialize before the scrape gate. `activation=load:<step>` tells the harness *which* workload to drive;
   `state:` with no driver is flagged undrivable, not failed.
2. **Attribution — pick the owner.** The report-card live-binding panel + the Generic Pilot Scoring
   Pipeline's gap→lever `owner ∈ {sdk_code|manifest_data|workload|scoring}` use the table above so an
   unbound-live SLI is attributed to `workload` (drive traffic) instead of a phantom `sdk_code` fix.
3. **Honest offline scoring.** `state:`/undrivable metrics are scored on the generation layer only
   (right name/unit/kind vs groundtruth) — never counted as a liveness failure.

## Status
`activation` exists in the groundtruth schema but is **empty in practice** and its current semantics are
`flag`-only (config-gating → omit). Populating it with `boot`/`load:`/`state:` + threading it to
owner-attribution is **contextcore#406** (not yet built). Until then the SDK name-infers nothing from it;
this doc is the forward reference so the consume-seam is ready when #406 lands.
