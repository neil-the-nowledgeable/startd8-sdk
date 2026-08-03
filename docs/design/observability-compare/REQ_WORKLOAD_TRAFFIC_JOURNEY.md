# REQ — Declarative workload-traffic journey (FR-8 extension)

**Status:** proposed · **Extends:** `SUBJECT_COVERAGE_REQUIREMENTS.md` FR-8 (warm-up traffic) ·
**Module:** `src/startd8/observability/warmup_traffic.py` (shape registry) ·
**Origin:** Harbor CNCF pilot (Pilot 1) — full-topology live-binding hit a ceiling because per-component
metrics only register after *domain operations*, which no shipped driver drives.
**Reusability intent:** the engine is **subject-agnostic and lives in the SDK**; each subject supplies a
declarative profile (data, not code). Harbor/Thanos/Istio all reuse it.

---

## Problem (grounded)

FR-8 resolved the *ingress* false-ready path: `smoke`/`ob-http`/`ob-grpc` drive bounded traffic so
lazily-registered RED series exist before the gate. But a real multi-component subject also has metrics
that register **only after specific domain operations**, not generic ingress CRUD:

- Harbor `harbor_jobservice_task_*` → only after a GC / replication / scan / retention **job runs**.
- Harbor `registry_*` (Distribution) → only after an image **push/pull** (a non-HTTP action).
- GC / retention success gauges → only after those **cron jobs execute**.

`smoke` is schema-driven CRUD against one ingress — it cannot trigger these. `ob-http`/`ob-grpc` are
**hardcoded to the Online-Boutique fleet**, not reusable for another subject. So on a full Harbor
stand-up, jobservice/registry/cron services score **0 not because generation is wrong but because their
metrics were never exercised** — the exact FR-8 false-empty path, one layer deeper (per-component, domain).

**Consequence:** live binding on the full topology is understated; those services can't be scored at all.

---

## Principle (unchanged from FR-8)

**Add no load engine.** This is *not* k6/locust. It adds **one more reusable driver shape** —
`SHAPE_WORKLOAD` — that *loops an authored sequence of operations*, reusing `drive_warmup`'s bounded loop
and `evaluate_warmup`'s two-part convergence verbatim. The novelty is only that the sequence is
**declarative + subject-supplied**, so it generalizes `smoke` (auto-discovered CRUD) to
`authored domain workflow` without hardcoding a fleet.

---

## Functional Requirements

- **FR-9.1 (declarative WorkloadSpec).** A subject-agnostic `WorkloadSpec` (loadable from JSON/YAML) is a
  named, ordered list of **steps**, each `{name, kind, registers_metric?, expect_status?, optional?}`:
  - `kind: http` → `{method, path, body?, auth_ref?}` — an authenticated HTTP call at the subject ingress.
  - `kind: command` → `{argv, env?}` — a whitelisted host command (e.g. `docker push …`) for non-HTTP
    effects (registry push/pull). Command steps are **opt-in** and **fail-loud-disabled** unless the run
    passes `--allow-workload-commands` (a subject can drive registry metrics only when the operator opts in).
  - `registers_metric` names the histogram/counter `_count`/`_total` the step is expected to make non-zero
    — the per-step convergence hook.

- **FR-9.2 (reuse the loop + convergence).** `run_workload_journey(spec, *, base_url, auth, runner_fns)`
  returns a `WarmupOutcome` (same dataclass): `exercised` = ≥1 step produced a success; `terminal_success`
  = every non-`optional` step reached its `expect_status`. It plugs into the existing bounded loop
  (`WarmupSpec.max_iterations`, `request_interval`) and **`evaluate_warmup`** — convergence is unchanged:
  driver terminal success **AND** `samples_landed` for the **union of the steps' `registers_metric`**.

- **FR-9.3 (shape-registry citizen).** `SHAPE_WORKLOAD` joins `VALID_SHAPES`; `--warm-up workload` +
  `--workload-spec <path>` select it. `HOST_DRIVABLE_SHAPES` includes it (HTTP steps are host-drivable;
  command steps run host-side too). Everything stays injectable (`runner_fns`) → unit-tested with zero
  network / zero docker (mirrors the existing `DriverFns` pattern).

- **FR-9.4 (auth block).** A spec-level `auth: {kind: basic|bearer|none, user?, password_env?, token_env?}`
  referenced by steps via `auth_ref`. Credentials come from the **environment only** and are redacted in
  logs/reports (mirror bind-and-verify's credential rule).

- **FR-9.5 (fail-loud, never silent-proceed).** A spec that exercises nothing (all steps skipped/failed),
  or whose `registers_metric` union stays zero after the loop, resolves the run to **`unknown` naming the
  spec + the empty metric(s)** — never a green proceed. Per-step failures are reported, not swallowed.

- **FR-9.6 (no coupling to a subject).** The SDK ships **no** subject spec. Specs live with the subject
  (pilot workspace) or a catalog. The engine imports nothing subject-specific.

## Non-goals

- No sustained/benchmark load, no concurrency model, no throughput targets (that's `benchmark_matrix`).
- No orchestration of the subject's *deployment* (that's `live_compose`/`live_standup`); the journey drives
  an **already-running** ingress.
- No new metric identity logic (that's `metric_descriptor`); the spec only *names* the metric to gate on.

## Acceptance criteria

- **AC-1:** `run_workload_journey` with an injected all-pass runner + a `query_fn` returning >0 → `ready`.
- **AC-2:** a step-fails-loud spec → `WarmupOutcome.terminal_success=False`, reason names the step; the
  run maps to `unknown`, not `fail`.
- **AC-3:** union-of-`registers_metric` all-zero after a terminal-success loop → `unknown` naming the empty
  metrics (FR-9.5).
- **AC-4:** existing `smoke`/`ob-http`/`ob-grpc` behavior byte-unchanged (additive shape only).
- **AC-5:** command steps are no-ops unless `--allow-workload-commands`; redaction verified on auth.

---

## Implementation plan (SDK — bounded, additive)

1. `warmup_traffic.py`: add `SHAPE_WORKLOAD`, a `WorkloadSpec`/`WorkloadStep` dataclass + `load_workload_spec`
   (JSON/YAML), and `run_workload_journey(...)` returning `WarmupOutcome`. Extend `_run_once`/`drive_warmup`
   dispatch (or a sibling loop that reuses the same bound + convergence). ~150 LoC, no new deps beyond httpx
   (already used) + `subprocess` for command steps.
2. `cli.py`: `--warm-up workload`, `--workload-spec PATH`, `--allow-workload-commands` on `compare-live` +
   `bind-and-verify`; thread through to `evaluate_warmup` with the spec's metric union as `count_metric`s.
3. Tests: `tests/observability/test_warmup_workload.py` — AC-1..AC-5 with injected fns (zero network/docker).
4. Docs: this REQ + a one-line pointer from `SUBJECT_COVERAGE_REQUIREMENTS.md` FR-8 ("FR-9 extends this for
   domain-workload registration").

**Split:** everything above is **SDK-owned/generic**. The subject's `WorkloadSpec` (which endpoints, which
metrics, which `docker` commands) is **subject-owned** — see the Harbor profile
(`OSS/Harbor/analysis/compare-live/HARBOR_FULL_TOPOLOGY_WORKLOAD.md`).
