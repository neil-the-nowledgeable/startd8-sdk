# Observability Artifact Generation — Gap Analysis & Closure Plan

**Date**: 2026-05-29
**Trigger**: Test run `run-003-20260528T2314` of the cap-dev-pipe observability stage against the `strtd8` project
**Module under review**: `src/startd8/observability/artifact_generator.py`
**Related**: `UNIFIED_OBSERVABILITY_MANIFEST_PLAN.md`, `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`
**Status**: Analysis complete — closure work not yet started

---

## Overview

A test run of the cap-dev-pipe observability stage produced three artifacts for one
service and self-reported a near-perfect quality score (composite **0.9708**). The
headline is misleading. This document records (1) what actually happened in the run,
(2) the gaps that result exposes, and (3) how each gap should be closed. It is a
diagnosis-and-direction doc, not an implementation plan with line-level edits — those
follow once we agree on which gaps to close and in what order.

The single most important finding: **the generated dashboard, alerts, and SLOs use only
generic OTel HTTP metrics and ignore all ten domain-specific metrics the pipeline
already discovered for the service.** The artifacts would be byte-identical for any HTTP
service on earth. The quality score does not detect this because it measures structural
form, not semantic relevance.

---

## 1. What Happened

### 1.1 Inputs

The stage consumed `run-003-20260528T2314/onboarding-metadata.json` (1,874 lines). For the
`strtd8` service, `instrumentation_hints` carried two metric sets:

| Set | Count | Metrics |
|-----|-------|---------|
| `convention_based` | 3 | `http.server.duration`, `http.server.request.body.size`, `http.server.response.body.size` |
| `manifest_declared` | 10 | `startd8_tokens_total`, `startd8_cost_total`, `startd8_active_sessions`, `startd8_context_usage_ratio`, `startd8_truncations_total`, `startd8_requests_total`, `startd8_response_time_ms`, `contextcore_task_progress`, `contextcore_task_status`, `contextcore_install_completeness_percent` |

The same metadata also declared, in `artifact_types` and `coverage`, that **8 artifact
types** were required for the project: `capability_index`, `dashboard`, `loki_rule`,
`notification_policy`, `prometheus_rule`, `runbook`, `service_monitor`, `slo_definition`.
The `coverage` block listed these as gaps for `strtd8`:
`strtd8-dashboard`, `strtd8-prometheus-rules`, `strtd8-service-monitor`,
`strtd8-notification`, `strtd8-loki-rules`, `strtd8-runbook`, `strtd8-slo`, plus a
project-level capability-index.

### 1.2 Outputs

The generator produced **3 artifacts for 1 service** (`strtd8`):

| Artifact | Path (under `observability/`) | Score | Format |
|----------|-------------------------------|-------|--------|
| Alert rules | `alerts/strtd8-alerts.yaml` | 1.0 (22/22) | Prometheus alerting rules |
| Dashboard spec | `dashboards/strtd8-dashboard-spec.yaml` | 0.9167 (11/12) | YAML spec (**not** Grafana JSON) |
| SLO definition | `slos/strtd8-slo.yaml` | 1.0 (22/22) | OpenSLO v1 |

`observability-manifest.yaml` reported: `services_processed: 1`, `services_skipped: 0`,
`artifacts_generated: 3`, `artifacts_skipped: 0`, `artifacts_errored: 0`.
`observability-quality.json` reported composite **0.9708**, total issues **1**, total
repairs **0**.

### 1.3 What worked correctly

- **Service de-duplication.** `service_metadata` and `instrumentation_hints` both
  contained spurious non-service entries — the project id `startd8/run-003-20260528t2314`
  and three requirement ids (`reqcdpobs001servicelevelobjectives`, etc.). All were correctly
  filtered by `_is_non_service_entry` (run-id, requirement-id, and project-id patterns),
  leaving the single real service `strtd8`. This is working as intended.
- **Derivation from the manifest.** Business values flowed through correctly:
  `criticality: high → severity: critical`; `latency_p99: 500ms → expr > 0.5`;
  `availability: 99.9 → error budget < 0.999`. Each output file records its derivation
  provenance in the header and in the manifest's `derivation_rules`.
- **Cross-artifact wiring.** Alerts link to `/d/obs-strtd8`; SLOs reference their alert
  names; the dashboard uid matches the `obs-{service}` convention. The cross-artifact
  checks (`unvisualized_alerts`, `unalerted_slos`, `misaligned_thresholds`) all passed.
- **Structural validity.** All three files are well-formed and pass their respective
  `OBS-100/101/200/710` structural checklists, save one warning.

The triplet that *was* generated is structurally sound. The problems are about
**relevance** and **coverage**, not malformed output.

---

## 2. Gaps Exposed

### Gap 1 — Domain metrics are ignored (highest impact)

`extract_service_hints` reads **only** `convention_based` metrics:

```python
# artifact_generator.py:256
metrics_raw = hint.get("metrics", {}).get("convention_based", [])
```

The string `manifest_declared` appears **nowhere** in the `observability/` module. As a
result the dashboard, alerts, and SLOs are built entirely from the three generic HTTP
semconv metrics. None of the ten metrics that describe what `strtd8` actually does —
token burn, cost, active sessions, context-usage ratio, truncations, task progress —
appear in any artifact.

**Consequence:** the artifacts are generic boilerplate. For an LLM-orchestration product,
a dashboard with no cost panel and no token-usage panel, and alerts that never fire on a
cost or truncation spike, miss the entire point of observing *this* service. This is the
root cause of low real-world usefulness, and it is invisible in the score.

### Gap 2 — Coverage contract and generator scope are unreconciled

The onboarding metadata declares 8 required artifact types; the generator hardcodes a
3-type triplet:

```python
# artifact_generator.py:1344
_GENERATORS = [
    (generate_alert_rules,     "alert_rule",     "alerts"),
    (generate_dashboard_spec,  "dashboard_spec", "dashboards"),
    (generate_slo_definitions, "slo_definition", "slos"),
]
```

Five declared types are therefore **never produced**: `service_monitor`,
`notification_policy`, `loki_rule`, `runbook`, `capability_index`. Per
`UNIFIED_OBSERVABILITY_MANIFEST_PLAN.md`, the triplet *is* the intended scope of this
module — so the missing five are arguably out of scope for *this* generator. The gap is
not that the module is broken; it is that **nothing in the pipeline reconciles "contract
said 8" with "generator delivered 3."**

**Consequence (a "looks-like-success" failure):** `observability-manifest.yaml` reports
`artifacts_skipped: 0, artifacts_errored: 0` and the quality report shows 0.97. A reader
of those files would reasonably conclude observability is complete. It covers 3 of 8
declared types. The shortfall is real but silent.

### Gap 3 — Quality score is structural, not semantic

The validators in `validators/observability_artifact_checks.py` (checks `OBS-100*`,
`OBS-101*`, `OBS-200*`, `OBS-710*`) verify *form*: YAML parses, title/uid present, panels
have `expr`/`type`/`unit`, severity labels valid, RED coverage present, SLO target matches
availability. **No check verifies that an artifact references the service's actual
metrics, or that all contracted artifact types exist.**

**Consequence:** boilerplate built from 3 generic metrics — ignoring 10 domain metrics and
5 artifact types — still scores 0.97. The score answers "is this well-formed YAML?" and is
read as if it answered "is this useful observability for this service?" The two questions
have very different answers here (≈0.97 vs. arguably ≈0.4).

### Gap 4 — Output format does not match the declared dashboard contract

`onboarding-metadata.json` `artifact_types.dashboard` declares the output as **Grafana
JSON** at `grafana/dashboards/{target}-dashboard.json`. The generator emits a **YAML
spec** at `dashboards/{service}-dashboard-spec.yaml`. The YAML spec is not directly
deployable to Grafana and is not what the `/dbrd-cr8r` dashboard pipeline expects as input
or output.

**Consequence:** an extra, undocumented conversion step sits between "generated" and
"deployable," and the contract's stated path/format is never satisfied.

### Gap 5 — gridPos autofix does not fire

The one quality ding is `OBS-100h: Panels missing gridPos` (dashboard 11/12 = 0.9167). A
repair (`repair_gridpos`) is wired in with `autofix=True` (artifact_generator.py:1121–1134),
but the quality report shows `repairs_applied: []` and the issue persists. Either the
repair returns no changes or validation re-checks un-repaired content.

**Consequence:** minor, but it is a real inconsistency — "we have a repair for this" vs.
"the repair ran" disagree. The generated dashboard ships without panel layout.

---

## 3. How the Gaps Should Be Closed

Ordered by impact-to-effort. Items 1 and 3 deliver the most value per unit of work.

### Closure 1 — Consume `manifest_declared` metrics (closes Gap 1)

- Extend `ServiceHints` to carry declared metrics alongside convention metrics, and have
  `extract_service_hints` populate both sets (read `metrics.manifest_declared` in addition
  to `metrics.convention_based`).
- Teach the three generators to emit domain artifacts:
  - **Dashboard:** add panels for declared metrics, grouped by intent (e.g. a "Cost &
    Tokens" group for `startd8_cost_total` / `startd8_tokens_total`, a "Sessions" group for
    `startd8_active_sessions`, a "Health" group for `startd8_truncations_total` /
    `startd8_context_usage_ratio`). Counters → rate panels; gauges/ratios → timeseries or
    gauge.
  - **Alerts:** derive at least one alert per high-signal declared metric where a threshold
    is inferable (cost spike, truncation rate, context-usage saturation). Where no threshold
    is derivable, emit the rule commented-out or with a TODO threshold rather than omitting it
    silently.
  - **SLOs:** where a declared metric maps to a user-facing objective, add an SLI/SLO
    (e.g. a truncation-rate or success-rate SLO).
- Keep the convention-based RED triplet as the baseline; declared metrics are additive.
- **Validation:** a run against this same `strtd8` metadata should produce a dashboard
  that contains `startd8_cost_total` and `startd8_tokens_total` panels.

### Closure 2 — Add a semantic-coverage check (closes Gap 3; makes Gap 1 measurable)

- New validator dimension: **metric-coverage** = fraction of the service's declared +
  convention metrics that are referenced by at least one generated artifact.
- Surface it in `observability-quality.json` as a distinct field (e.g.
  `metric_coverage_score`) and fold it into the composite, so the headline number drops
  when domain metrics are ignored.
- Optionally add an **artifact-type-coverage** dimension: declared types produced ÷
  declared types required.
- **Validation:** re-scoring the *current* run-003 artifacts should yield a low
  metric-coverage score (3 of 13 metrics referenced), proving the check bites.

### Closure 3 — Reconcile the coverage contract (closes Gap 2)

Pick one of two postures and make the pipeline honest about it:

- **(A) Honest scope.** Keep the triplet as scope, but have the generator emit explicit
  `status: skipped` entries (with a reason like `"not implemented by triplet generator"`)
  for the declared-but-unimplemented types, so `observability-manifest.yaml` shows
  `artifacts_skipped: 5` instead of `0`, and the quality report stops implying full
  coverage.
- **(B) Expand scope.** Implement generators for the missing types (`service_monitor`,
  `notification_policy`, `loki_rule`, `runbook`, `capability_index`). Larger effort; only
  justified if downstream actually deploys these.

Recommended: **(A) now**, **(B) later and only per demonstrated need.** The unacceptable
state is the current one, where the gap exists but is reported as success.

### Closure 4 — Align the dashboard output contract (closes Gap 4)

- Decide the single source of truth: either the generator emits Grafana JSON at the
  contracted path, or the onboarding metadata's `artifact_types.dashboard` is updated to
  declare the YAML-spec format/path and an explicit downstream conversion step (e.g. via
  `/dbrd-cr8r`).
- Whichever is chosen, make the generator output and the metadata contract agree, and
  document the hand-off to the dashboard pipeline.

### Closure 5 — Fix the gridPos autofix (closes Gap 5)

- Verify that `repair_gridpos` mutates the parsed dashboard and that re-validation runs on
  the repaired content; ensure `repairs_applied` is populated when a fix is made.
- **Validation:** a regenerated dashboard contains `gridPos` on every panel and
  `OBS-100h` no longer appears.

---

## 4. Evidence Index

| Claim | Source |
|-------|--------|
| Only `convention_based` read | `artifact_generator.py:256`; `grep manifest_declared src/startd8/observability/` → no matches |
| Triplet hardcoded | `artifact_generator.py:1344` (`_GENERATORS`) |
| 8 declared types / coverage gaps | `run-003-…/onboarding-metadata.json` → `artifact_types`, `coverage.gaps` |
| 10 domain metrics for strtd8 | `onboarding-metadata.json` → `instrumentation_hints.strtd8.metrics.manifest_declared` |
| Scores & single warning | `run-003-…/observability/observability-quality.json` (composite 0.9708, OBS-100h) |
| Clean-success manifest | `run-003-…/observability/observability-manifest.yaml` (`artifacts_skipped: 0`) |
| Structural-only checks | `validators/observability_artifact_checks.py` (OBS-100/101/200/710) |
| Dashboard format contract | `onboarding-metadata.json` → `artifact_types.dashboard` (`grafana/dashboards/{target}-dashboard.json`) |
| gridPos autofix wired but inert | `artifact_generator.py:1121–1134`; quality report `repairs_applied: []` with OBS-100h present |
| Intended scope = triplet | `UNIFIED_OBSERVABILITY_MANIFEST_PLAN.md` Overview |

---

## 5. Open Questions

1. Are the five missing artifact types (`service_monitor`, `notification_policy`,
   `loki_rule`, `runbook`, `capability_index`) deployed by any downstream consumer today?
   If not, Closure 3(A) is sufficient and 3(B) can be deferred indefinitely.
2. Is the YAML dashboard-spec format consumed by anything (a `/dbrd-cr8r` step?), or is
   Grafana JSON the real target? This decides the direction of Closure 4.
3. Should `manifest_declared` thresholds (for cost, truncations, context usage) come from
   the manifest, from defaults, or be left as TODO when absent? This shapes how aggressive
   Closure 1's alert generation should be.
